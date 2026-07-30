# Architecture

```
WhatsApp ──webhook──▶ cloudflared ──▶ saathi-web (FastAPI, 127.0.0.1:3130)
                                          │
                                          ├─ signature check (HMAC, fails closed)
                                          ├─ dedupe on wa_message_id
                                          ├─ window touch (24h timer)
                                          ├─ SAFETY classifier ── deterministic, pre-LLM
                                          ├─ audio? ─▶ fetch media ─▶ ffmpeg ─▶ Saaras
                                          │            └─▶ entity correction (local)
                                          ├─ agent loop ─▶ zai.glm-5 (Bedrock ap-south-1)
                                          ├─ Postgres 18
                                          └─ tracing ─▶ OTel Collector ─▶ Jaeger
                                               ▲
                       saathi-worker ──────────┘  reminder scheduler,
                                                  poll 30s, SKIP LOCKED
```

Everything runs on `i-01b2c27883acb25ca` in **ap-south-1**. No inbound port is
open to the application — traffic arrives only through the tunnel. The box has
one inbound rule, TCP 22 from `207.219.25.137/32`, for operator SSH. See
`RUNBOOK.md`.

## The boundaries that matter

**Safety is a regex, not a prompt rule.** `safety/classifier.py` runs before the
model is constructed. A forwarded scam message is untrusted input that will try
to argue its way past an instruction; it cannot argue with a function that has
already returned. `tests/test_pipeline_order.py` fails if the agent is ever
reached on an emergency message.

The scam shield has two deterministic outcomes. Clear credential, transfer,
digital-arrest and lottery indicators return `SCAM`; pressure-shaped courier /
customs / police, electricity-disconnect, fee-for-loan/job, pension, UPI and
remote-support-app indicators return `SUSPICIOUS`. Both block the model. The
latter deliberately says *may be a scam* and gives one safe next step: do not
pay/click/install/share a screen; independently find the organisation's
official contact. Both provide 1930 for money already lost. This distinction
avoids asserting fraud as fact while still refusing to let a risky message
drive an open-ended model turn.

**Capability is defined by absence.** PRD §12's guarantee — that prompt
injection cannot cause harm — lives in `agent/tools/specs.py`, in what is *not*
in the tool list. No tool can move money, read an OTP, or touch a third-party
account. `assert_no_forbidden_tools()` fails the suite if one is added.

**Commercial internet actions stop at handoff.** Shopping, flights, movie tickets,
local directions and similar tasks may search, compare, assemble an itemised
list, and generate a provider deeplink or booking URL. They may not purchase,
reserve, pay, log in, read OTPs, operate a third-party account, or automate a
hidden browser flow. The detailed contract is `COMMERCIAL_ACTIONS.md`: provider
APIs are used for offer/search/discovery, and the user completes the transaction
in the provider surface they open.

**A returning WhatsApp handle is not a new signup.** The phone number/`wa_id` is
a revocable channel handle, not the account, but while that handle is active it
must resolve to the same `users.id` and keep `users.onboarding = 'done'`. Old
WhatsApp quick-reply payloads from onboarding are therefore harmless after setup:
language buttons may change `lang_pref`, but consent/name/reminder/improve buttons
reply that setup is already complete instead of restarting signup or changing
state. Bare greetings such as `start`, `hi` or `namaste` from onboarded users fall
through to normal conversation. A separate identity-lifecycle lane owns the full
90-day stale-handle policy: warn during dormancy, let the user confirm or move
the account, then revoke/delete only after the written window expires.

**Stale WhatsApp-handle lifecycle (ID-2).** A handle is evidence of control of
a delivery address, never the account or a durable proof of the human. On its
last positive inbound message we book a 60-day lifecycle check. At 60 days of
silence the worker sends the existing content-free `daily_checkin` template;
the template does not name the person or disclose that an account exists. At
90 days of *continuous* silence it revokes the handle and removes its primary
claim. The user record and its data are retained so the real person can move
the account through a verified channel; the recycled handle cannot read them.

If a handle returns after 60 days, identity resolution changes it to
`reverify` before any session touch, transcription, message log, conversation,
capability, memory lookup or model work. The only allowed responses are the
fixed confirmation/move controls. Confirming restores `active` and schedules a
fresh 60-day check. Moving issues a 15-minute, six-digit code to the gated old
chat; a **brand-new** WhatsApp handle must send `MOVE <code>`, then becomes the
primary active handle while the old one is revoked. A bare number is never a
code, and a code entered from an established account is refused. This confirms
continued control of the old chat, not legal identity; the privacy control is
the no-data gate plus the dead-air revocation, not a claim that phone numbers
cannot be recycled.

**Forwarded content is data, never command.** Text the user did not author —
forwarded, quoted, or lifted out of an image or PDF — is `RELAYED`, and is
enforced in **two** places, because withholding tools only ever covered the
agent:

- `agent` (priority 90) — `provenance.allowed_tools` withholds every mutating
  tool, and `fence()` presents the text as material rather than as the user
  speaking.
- `commands` (priority 22) — the *matcher* requires `c.trusted`. Relayed text
  simply does not match, and falls through to the agent that already fences it.
  This was missed originally, and it mattered: STOP matches `\bunsubscribe\b`
  as a substring, so a forwarded advert set `users.paused = true` and silently
  stopped that user's reminders.

Buttons (20/21) stay trusted — provenance describes text, and a tap is a
first-party control the user physically pressed. Onboarding (10) is deliberately
exempt: gating it would drop an un-onboarded user through to the agent and break
"onboarding never calls the model", which is what makes an open door safe.

**Tracing is privacy-hardened and token-gated.** Spans go through the logfire
SDK to the local OTel Collector receiver on `127.0.0.1:4317`, then from the
collector to local Jaeger OTLP on `127.0.0.1:4318`. If `LOGFIRE_TOKEN` is
present, the same scrubbed spans also go to the operator's Pydantic Logfire
project (`indofolk-ai` as of 2026-07-29). Jaeger stores locally with badger
storage (7-day TTL, 4 GiB cap), and its UI is available only via SSH tunnel to
`127.0.0.1:16686`. Only a fixed allow-list of attributes reaches spans: kind,
latency, tokens, tool name, hop count, model id, error class, trigger enum.
Message text, transcripts, names, medicines and query parameters are scrubbed
(`saathi/observability.py`). Tracing is best-effort: collector, exporter,
Logfire, or Jaeger failures never block a turn and no new inbound port is
opened.

**The 24-hour window is a hard gate, not a convention.** `wa/window.py` refuses
free-form sends outside the window. Every outbound path funnels through
`wa/client.py::_send`, which calls the guard first — so it is not possible to
send by forgetting to check.

**Speaking back is additive and best-effort (PR-8, D-AE).** When enabled
(`SAATHI_TTS_ENABLED`, off by default), a reply is also spoken as a Sarvam Bulbul
voice note — but only after the text reply has already gone. Policy (whether to
speak) lives in `core/context.should_voice`: gated by the flag, then the user's
`voice_reply_pref`, defaulting to voice-in→voice-out; onboarding stays text-only.
Mechanism lives in the channel (`send_voice`), so SMS degrades to text rather than
erroring. Two boundaries hold: TTS input is Saathi's *own* reply text, never the
user's inbound content, and stays in India (Sarvam), preserving the inference-in-
India rule; and every synthesis is metered through the usage ledger like STT. A
TTS failure, cap refusal, or outage can never take down the turn — the text reply
already succeeded.

**Onboarding is voiced too, for voice users (VOICE-2).** If someone has ever sent
a voice note (`onboarding._voice_user` reads the `messages` log — no new state),
each onboarding message is also spoken. This does **not** breach "onboarding never
calls the model": TTS is a Sarvam call on our own fixed copy, not the LLM, and the
fixed strings are phrase-cached. Buttons/lists stay the primary; voice is an
accessibility layer for elders who read with difficulty.

**Memory serves ASR, not just personalisation.** `facts.surface_forms` is the
entity-bias vocabulary for the correction pass. This is why the product hears
someone better the longer they use it — a retention mechanic, not an accuracy
patch. Bias forms are extracted proper nouns; a whole sentence is worthless as a
bias hint.

**Recurrence and firing are separate tables.** `reminders` holds the RRULE
definition; **`scheduled_turns` is the queue** — one queue for every kind of
scheduled work, since migration 006. Firing a recurring reminder books its own
next occurrence, dedupe-keyed on (reminder, occurrence), because nothing else
walks the RRULE.

`reminder_fires` is the **old** queue and is no longer written or read. It
survives only as the table `pipeline.handle_ack` still updates, which is why the
ack path is currently unreachable — see lane PR-4b. Do not add writes to it.

**A claim is committed before the send.** `claim_due` marks a turn `sent` and
commits, so two workers can never double-send. The cost is that a crash between
claim and send strands the row: never retried, because claiming reads only
`pending`, and never failed, because nothing raised. `scheduling.sweep_stuck`
reclaims those, guarded on `wa_message_id is null` — set only after a send
returns an id, so a reclaimed turn provably never reached WhatsApp.

**Cost is linear in prompt size.** The chosen model has no prompt caching, so
there is no cache to hide a bloated prefix behind. `agent/prompt.py` raises
`PrefixTooLarge` rather than let it creep — the failure mode being guarded
against is silent, not loud.

## Layout

    saathi/web/       FastAPI — webhook (verify + signed receive), healthz
    saathi/wa/        Cloud API client, window guard, templates, text formatter
    saathi/speech/    ffmpeg transcode, Saaras STT, entity correction, Bulbul TTS
    saathi/agent/     tool loop, streaming, prompt + prefix budget, tools
    saathi/safety/    deterministic pre-LLM classifier
    saathi/worker/    reminder scheduler, reminder sender
    saathi/memory.py  facts, bias vocabulary, erasure
    saathi/pipeline.py  the inbound path, start to finish
    db/               extensions.sql (superuser), schema.sql (owner)

## Why Postgres is also the queue

`SKIP LOCKED` holds well past 10k users, and it is the pattern already proven
across ~20 workers on the MeshPilot box. No Redis, no Temporal, no vector DB in
v1 — the fact set per user is tens of rows and fits in the prompt.

Two correctness notes that cost money to learn elsewhere: the row locks only
hold inside an explicit transaction, and claim-and-mark must be a single
statement so there is no window where a row is claimed but unmarked.

## Capabilities are registered, not branched

The inbound path used to be an `if/elif` ladder that grew a branch per feature.
That shape stops being reviewable at about six capabilities: every new one edits
the same function, ordering becomes implicit, and nobody can say what runs
before what without reading all of it. It is the failure mode that breaks
products of this kind at scale.

A capability is now an object with three things:

    priority  — lower runs first; ordering is data, not source order
    matches() — cheap, side-effect-free "is this mine?"
    handle()  — returns a result to claim the message, or None to fall through

`saathi/capabilities.py` read top to bottom *is* the specification of what
happens to an inbound message. Adding web search, weather, or a new document
type is a `register(...)` there — never an edit to `pipeline.handle_message`, and
a test asserts the dispatcher does not name any individual capability.

Priority bands keep the ordering legible as this grows:

| Band | For |
|---|---|
| 0–9 | safety and admission — must not be overtakeable |
| 10–19 | onboarding — a new user is not a general query |
| 20–29 | deterministic commands — unambiguous, model-free |
| 30–49 | media and modality |
| 50–89 | specific capabilities |
| 90–99 | the agent, as the catch-all |

Two properties are enforced by tests rather than convention: **safety is
priority 0** and cannot be overtaken (R7), and **a handler that raises is logged
and skipped** rather than killing the turn — one broken capability must not take
the assistant down for someone asking about their medicine.

## Seeing and reading

`vision.py` uses **`qwen.qwen3-vl-235b-a22b`**, chosen because it is a
*regional* ap-south-1 model: a photograph of someone's prescription must not
leave India, and the Anthropic vision models here are `global.`-only. GLM-5 has
no vision at all.

Health-adjacent answers carry their disclaimer **by construction** — the caller
cannot obtain the text without it, because `Reading.rendered()` attaches it.
PRD §12's line holds: naming what is printed on a pack is information; saying
whether or how much to take is advice, and we never cross it.

`documents.py` tries a PDF's text layer first (most bills, statements and
e-tickets have one, and extraction is exact and free), falling back to
rasterising page one for scans. Page count is bounded — an elder wants the gist
and the deadline, and an unbounded document is an unbounded bill.

**Inbound media is admitted, not merely accepted.** The webhook acks Meta and
detaches the work with `asyncio.create_task`, so without a ceiling the number of
messages being processed at once is chosen by whoever is sending them — and
onboarding is open, so that is anyone. Four things bound it, and each sits in
the path a real message takes rather than in a helper somebody must remember to
call:

- **The download carries its own limit.** `fetch_media(media_id, max_bytes)` has
  no default; a call site must say what it can afford. Meta's advertised
  `file_size` refuses the worst cases before a byte moves, and the body is
  streamed and abandoned at the cap rather than buffered and measured. A size we
  could not determine is not treated as small.
- **Two gates** (`core/backpressure.py`): four image-or-document messages in
  flight, one document being parsed. The document gate is 1 because this box has
  2 vCPU and the same event loop runs the safety classifier; PDF parsing is
  CPU-bound and holds the GIL. It covers the CPU half only and is released
  before the model call, which is a network wait rather than work this box does.
  The (N+1)th is **refused with a message, not queued** — a queue in front of
  CPU-bound work is unbounded growth that also answers too late to be useful.
  Voice notes are fetched outside both gates, which is why the resident-media
  ceiling is a statement about photos and PDFs and not about all inbound media.
- **The parser is not on the event loop.** `pypdf` is synchronous, so it runs in
  a thread pool sized to the document gate, under a wall clock.
- **The renderer is a subprocess with kernel limits.** `pdftoppm` gets CPU,
  address-space and file-size rlimits via `preexec_fn`, a timeout, and — this
  was missing — a kill when the timeout fires, because `wait_for` cancels our
  wait and not the child.

**A refusal is a reply.** Every exit from the media path sends something: too
large, too long, busy, or unreadable, bilingual and naming what would work
instead. The person on the other end may have photographed their prescription by
accident, and silence is indistinguishable from the product being broken.

**Inbound turns are admitted before paid work.** After identity resolution and
webhook deduplication, `pipeline.handle_message` first takes the process-local
`turn` gate (default 8), then atomically reserves one of the sender's six
rolling one-minute slots in Postgres. The reservation is recorded before audio
transcription, so a voice-note burst cannot spend Sarvam minutes before the
limit notices it. A transaction-scoped *non-blocking* advisory lock prevents two
same-user webhooks both observing an open slot; lock contention is refused
quietly rather than queued. The short-lived admission rows hold only `user_id`
and time, never message content. One bilingual retry-later notice is allowed
per reason every ten minutes; later over-limit traffic is silent, because a
refusal is itself a paid outbound message. The global gate does not consume a
user's quota. These are availability/fairness controls, not the future
cross-vendor monetary ledger in `USAGE_LEDGER.md`.

**Vendor accounting is content-free and staged.** Migration 015 creates
append-only `vendor_usage_events` and auditable `vendor_usage_reservations`.
Successful LLM, Sarvam STT and WhatsApp template calls now emit usage events
without prompts, transcripts, phone numbers, raw media or API responses.
`saathi.usage.reserve` takes a transaction-scoped account advisory lock, expires
stale holds, applies an optional same-currency cap and commits an idempotent hold
before a paid vendor call; settlement/release never delete the hold. The default
is still observe-only. Sarvam STT is the first staged enforcement path: it can
reserve INR paise before bytes reach Sarvam and refuse with fixed copy if the
account cap is exhausted, but only when the explicit enforcement flag, `enforce`
mode and a positive approved cap are all set. Other paid surfaces remain
observe-only until their pre-call reservation paths are built.

**Meta is not allowed to become a responder.** The hourly
`saathi-meta-guard.timer` requires the configured Saathi app to retain its
`whatsapp_business_account/messages` webhook subscription and fails if Meta's
Business Agent settings appear for the configured phone number. A failed check
uses the normal `OnFailure` SNS path. The WABA `subscribed_apps` read is logged
as supplementary evidence only: on 2026-07-29 it returned an empty list even
after Meta accepted the documented subscribe POST, so treating that endpoint's
empty response as a healthy exact-set assertion would fail open.

One consequence worth stating: **WhatsApp's wire types are a longer list than
the `msg_kind` enum**, and `pipeline` coerces before writing. It did not, which
made `document` an aborted transaction and the whole media capability
unreachable for PDFs. See `PROD_READINESS.md` PR-26.
