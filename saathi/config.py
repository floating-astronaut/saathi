"""Settings. Values come from the environment; nothing secret is defaulted."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    saathi_env: str = "dev"
    saathi_db_dsn: str = "postgresql:///saathi"

    # WhatsApp Cloud API (Meta direct)
    wa_phone_number_id: str = ""
    wa_business_account_id: str = ""
    wa_access_token: str = ""
    wa_webhook_verify_token: str = ""
    wa_app_secret: str = ""

    # Bedrock — regional ap-south-1, inference stays in India (plan §5c)
    bedrock_region: str = "ap-south-1"
    saathi_model_id: str = "zai.glm-5"
    # No prompt caching on this model, so cost is linear in prompt size.
    # The agent asserts against this before every call.
    saathi_prefix_token_budget: int = 3000

    #: Speech-to-text only. Operator decision 2026-07-27 (D-S): Sarvam is
    #: likely to become our largest vendor, but it offers no per-account
    #: sub-key, so spend on it cannot be attributed to a household or capped
    #: per tenant. Until it can, it stays on the one path where the cost is
    #: bounded by the length of an audio file rather than by a model's appetite.
    sarvam_api_key: str = ""

    # --- OpenRouter: per-account keys (AI-1) --------------------------------
    #: The *provisioning* key. It mints capped sub-keys and is never used to
    #: serve a turn — see `docs/AI_ROUTING.md` §5. Empty means provisioning is
    #: disabled and `provision.mint` refuses; it never falls back to spending
    #: on this key directly, because that is the one credential with no cap.
    openrouter_master_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    #: The Indofolk AI workspace minted keys belong to. Wrong workspace means a
    #: key that works and bills the wrong ledger, which is worse than a failure.
    openrouter_workspace_id: str = ""

    #: Fernet key for secrets at rest — today, minted OpenRouter keys. Empty
    #: means provisioning refuses rather than storing a plaintext, because an
    #: unencrypted API key in a table is a worse outcome than no key at all.
    saathi_secrets_key: str = ""

    #: Voice notes are kept briefly for debugging: India is not one language,
    #: and a transcript alone cannot tell you whether the model mis-heard or the
    #: speaker used a regional form. Deletion is enforced by an S3 lifecycle
    #: rule, not by our code. Empty disables storage entirely.
    saathi_audio_bucket: str = ""

    #: General web search, via Gemini's Google Search grounding. AWS has no
    #: equivalent — Bedrock accepts only tools we implement, and Kendra indexes
    #: our own documents rather than the web. Empty means the provider reports
    #: itself unavailable and the agent does not offer it, which is a config
    #: fact rather than a bug.
    saathi_gemini_api_key: str = ""

    #: Saathi's own GCP service account (project saathi-ai-503623). Preferred
    #: over the API key: it reaches Vertex in asia-south1, so the request is
    #: served from India rather than a global endpoint.
    saathi_gcp_sa_file: str = ""
    saathi_gcp_project: str = "saathi-ai-503623"

    # Admission control (pattern from OpenClaw's dmPolicy). "pairing" means an
    # unknown handle must redeem a code before the agent will talk to it; "open"
    # lets anyone in. Default is pairing: an unknown sender otherwise gets free
    # LLM turns and STT minutes on our bill, and this is an eldercare agent.
    # "open" now that onboarding exists and is deterministic: an unknown sender
    # walks a scripted, model-free path, so anyone may start by messaging us
    # without opening a cost vector. "pairing" remains available for a closed
    # pilot.
    saathi_dm_policy: str = "open"
    #: How many times we will explain the pairing requirement to one unknown
    #: handle before going silent. Each reply costs money.
    saathi_admission_max_replies: int = 2

    # --- inbound media limits (PR-26) ---------------------------------------
    # Admission is open, so "a valid sender" is a low bar and none of these may
    # assume good faith. Every number below is a bound on what *one* inbound
    # message may cost this box — 2 vCPU and 8 GiB, shared with the reminder
    # worker, whose worst failure is a missed dose.

    #: Photographs. Equal to what the vision model itself accepts, so the two
    #: cannot drift apart and produce a blob we downloaded and then cannot use.
    #: WhatsApp's own inbound image ceiling is 5 MB, so this refuses nothing a
    #: user could actually send as a photo.
    saathi_max_image_bytes: int = 5 * 1024 * 1024
    #: PDFs. We only ever read the first `documents.MAX_PAGES` pages, and a
    #: 300-dpi colour scan of one A4 page is 2-5 MiB — so 8 MiB covers anything
    #: we would actually read, while bounding what a single message can hold in
    #: memory. WhatsApp permits documents up to 100 MB; we do not.
    saathi_max_document_bytes: int = 8 * 1024 * 1024
    #: Voice notes. `fetch_media` refuses to run without a limit, and this is
    #: the honest one for audio: WhatsApp's own inbound ceiling, so it refuses
    #: nothing a phone can send while still bounding the blob we hold and hand
    #: to ffmpeg. Tightening it is a speech-lane decision, not this one.
    saathi_max_audio_bytes: int = 16 * 1024 * 1024

    #: How many inbound **image and document** messages may be in flight at
    #: once, process-wide. The webhook detaches every message with
    #: `asyncio.create_task`, so without this the number of simultaneous
    #: multi-MiB blobs is whatever the sender chooses. Four is far above real
    #: demand (a handful of elders, a few photos a day).
    #:
    #: It does **not** bound all inbound media: voice notes are fetched by
    #: `pipeline.transcribe_voice`, which never passes through this gate, so
    #: audio concurrency is still unbounded and audio is the *primary*
    #: modality. Gating it is a speech-lane decision, not this one — see
    #: `PROD_READINESS.md` PR-26. So the honest ceiling here is 4 x 8 MiB of
    #: photos and PDFs, plus however many voice notes are arriving.
    saathi_media_concurrency: int = 4
    #: How many *documents* may be parsed or rasterised at once. One, not two:
    #: PDF parsing is CPU-bound and holds the GIL, the box has 2 vCPU, and the
    #: same event loop also runs the safety classifier and every other user's
    #: turn. One in flight leaves a core for everything else. The second
    #: document is refused with a message rather than queued — an unbounded
    #: queue would answer minutes after the person gave up, and would itself be
    #: the memory leak this limit exists to prevent.
    #:
    #: ⚠️ **Raising this is not just a throughput knob.** `documents._parse_pool`
    #: is sized to this value, and at 1 that is what guarantees no pypdf thread
    #: is running when `render_first_page` forks with a `preexec_fn`. At 2 the
    #: window opens and the child can deadlock on a malloc lock the fork
    #: orphaned. Do not raise it without removing `preexec_fn` and enforcing the
    #: renderer's limits some other way. See `LANDMINES.md`.
    saathi_doc_concurrency: int = 1

    #: Refuse a PDF declaring more pages than this before *extracting or
    #: rendering* any of them. We read 3; 200 is well past any bill, statement
    #: or report an elder is sent.
    #:
    #: It does not stop the page tree being walked — counting the pages is the
    #: walk. A 7 MiB file of 60,000 pages costs 4.6s and 295 MiB before this can
    #: fire, which the pool, the document gate and the parse clock contain
    #: between them. See `documents._extract_blocking`.
    saathi_pdf_max_pages: int = 200
    #: Wall clock for the pypdf text pass, which runs in a bounded thread pool
    #: rather than on the event loop. A legitimate three-page extraction is
    #: milliseconds; 8s is several hundred times that and still short enough
    #: that a hostile file is dropped before it matters.
    saathi_pdf_parse_timeout_s: float = 8.0
    #: Wall clock for `pdftoppm`. One page at this size renders in well under a
    #: second; 15s covers a genuinely heavy vector page on a busy 2-vCPU box.
    saathi_pdf_render_timeout_s: float = 15.0
    #: Longest edge of the rasterised page, in pixels. Bounds the raster by the
    #: *output* rather than by DPI, because the page's declared size is
    #: attacker-controlled and `-r 150` on a 200-inch page is not bounded at
    #: all. 1700px matches what 150 dpi gave for A4, which the vision model
    #: downsamples anyway.
    saathi_pdf_render_max_px: int = 1700
    #: RLIMIT_AS for pdftoppm. A legitimate A4 raster working set is ~10 MiB;
    #: 512 MiB is 50x that and far below the point where a decompression bomb
    #: could push this box into swap and take the reminder worker with it.
    saathi_pdf_render_max_mem_mb: int = 512
    #: RLIMIT_FSIZE for pdftoppm — the only part of this path that writes to
    #: disk. A 1700px PNG is 1-3 MiB.
    saathi_pdf_render_max_output_mb: int = 32


settings = Settings()
