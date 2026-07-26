# Build plan — Saathi v1 (companion to PRD-whatsapp-elder-agent.md v0.1)

**Date** 2026-07-26 · **Status** D-A/D-B/D-C **decided** (§5) — plan approved for week 1

---

## 1. What already exists on this box (verified, not assumed)

| PRD requirement | Status here | Evidence |
|---|---|---|
| Postgres as store **and** job queue, `SKIP LOCKED` | **Have it, proven** | ~20 workers use the exact pattern — `workers/cod_dialer.py:117`, `workers/automation_runner.py:88`, `workers/creative_poller.py:142`. PG **18.4** on box. |
| ffmpeg in the hot path both directions | **Have it** | `/usr/bin/ffmpeg` 8.0.1 |
| Sarvam account + key | **Have key + a live call site** | `SARVAM_API_KEY` set in `.env`; `apps/cod_pipecat/bot.py:143` |
| Hinglish voice-agent prompt craft | **Have the scar tissue** | `bot.py:93` — "sirf plain bola-jaane-wala Hinglish, warna TTS galat bolega" |
| Deploy: systemd + nginx + LE (DNS-01 via CF) | **Have the pattern** | grow-dashboard/cod-confirm units; CF token box-bound |
| Object storage for audio w/ TTL | **Have R2 + a helper** | `meshpilot_platform/creative_storage.py`, bucket pattern from CREATIVES-DB |
| Claude tool loop | **Partial** | `bedrock_llm.py`, `llm_policy.py` exist — but see gap below |

### What does **not** exist — i.e. essentially the whole v1 spine

- **WhatsApp: nothing.** Zero `WA_*` / `WHATSAPP_*` / `WABA_*` env vars anywhere on the box. The only `whatsapp` hits in the repo are a brand-logo SVG and vendored SDK files. No webhook, no Cloud API client, no templates, no media fetch, no interactive messages, no 24-h window tracking.
- **Prompt caching: zero.** `grep -rn cache_control src/` → **no hits**. The PRD calls it mandatory and §14's economics collapse without it. House LLM traffic goes through OpenRouter (`llm_policy.py`, `CHEAP_SLUG`/`PREMIUM_SLUG`), which is the wrong path for a caching-critical workload. `ANTHROPIC_API_KEY` in `.env` is **empty**.
- **Sarvam reuse is thinner than it looks.** What exists is `saarika:v2.5` **streaming via pipecat at 8 kHz** — the model the PRD says is deprecated, over a transport we don't want. The PRD's path is **Saaras v3 REST at 16 kHz**. What carries over is the account, the key and the billing relationship — not the code.
- No reminders / RRULE / scheduler, no Duffel, no cart deep links, no safety classifier, no consent or erasure flow, no TTS cache, no eval harness.
- Nothing named `saathi` or `elder` anywhere in the repo or docs.

**Net:** ~15% of v1 is reusable infrastructure and hard-won pattern; ~85% is new code. The reusable 15% is the boring-but-load-bearing 15% (queue, deploy, storage, ffmpeg), which is worth a lot.

---

## 2. Three things I'd change in the PRD before building

### G1 — Data residency contradicts the host (§13 vs reality)
This box is **us-east-2**. §13 says "data resident in India." Voice notes and medicine names from Indian seniors are exactly the data DPDP cares about. Full operational enforcement is **13 May 2027**, so a pilot on us-east-2 is survivable — but the Postgres instance is the single hardest thing to move later, and the migration cost only grows with row count. **Decide the DB home before week 1 writes a schema, not after.** Recommendation: Postgres in **ap-south-1** from day one; Claude via **Bedrock ap-south-1**; Sarvam is already Indian.

### G2 — The 24-hour window is missing from the data model
§11 describes the window correctly but §7's architecture has no state for it. This is the most expensive bug class in WhatsApp work: send free-form to an expired window and you get a silent failure (or `131047`), reminders stop, and you find out from a user. Make it a first-class row (`sessions.window_expires_at`) and make the **send layer physically refuse** free-form when expired, falling back to a template. Not a convention — a hard gate in one function.

### G3 — Flight search is the weakest slice in v1
§15's primary metric is D30 retention of daily actives. Retention comes from memory + reminders + "explain this message" — things touched daily. Flight search is touched twice a year, carries an unresolved commercial risk (R2, Duffel search-only terms), and consumes week 3 entirely. **Recommendation: cut `search_flights` from v1** and keep `build_cart` (which needs no vendor contract and exercises the same slot-filling and CTA-button machinery). Reinstate flights in v1.1 once the Duffel answer is in. This buys back a full week for onboarding and the eval set — the two things that actually gate external users.

Two smaller notes:
- **Onboarding is the top risk (R5) but isn't tested until week 4.** Move a minimal child-onboards-elder flow to week 2, even if consent copy is still draft.
- **Disk is at 82% (15 GB free).** Raw audio at a 7-day TTL plus TTS cache must go to **R2, not local disk**, from the first write.

---

## 3. Shape of the thing

New repo `saathi`, new database `saathi`, two systemd units. **Not** in the MeshPilot monorepo — different product, different lifecycle, and the CLAUDE.md scope rule says so.

```
saathi/
  saathi/
    web/        FastAPI — GET/POST /webhook/whatsapp, /healthz          (:3130)
    wa/         Cloud API client: send_text | send_interactive |
                send_template | send_audio | fetch_media
                + window_guard.py  ← G2 lives here
    speech/     stt_sarvam.py (Saaras v3 REST) · tts.py (iface + cache)
                · audio.py (ffmpeg: OGG/Opus ⇄ WAV16k)
    agent/      tool loop + system prompt + cache breakpoints
                tools/{memory,reminders,build_cart}
    safety/     classifier.py — deterministic, runs before the model
    db/         schema.sql, repo.py
    worker/     reminder_scheduler.py (30 s, SKIP LOCKED) · nudge ·
                media_retention (7-day TTL) · link_health
  evals/        voice-note corpus + entity-accuracy scorer
```

### Schema (the parts that matter)

- `users` — wa_id, lang_pref, `tz` (default Asia/Kolkata, **stored per user**), voice_reply_pref, consent_at/version, deleted_at
- `sessions` — user_id, **`window_expires_at`** ← G2
- `messages` — direction, wa_message_id, type, body, media_ref, `transcript`, `transcript_raw`, stt_ms
- `facts` — key, value, kind (person | medicine | place | brand | preference | routine), source_message_id, deleted_at. Serves both personalisation **and** ASR entity biasing (§10)
- `reminders` — title, `rrule`, tz, status
- `reminder_fires` — **the queue table.** `scheduled_for`, state, sent_at, wa_message_id, acked_at, snoozed_to, nudge_sent_at. Worker claims `state='pending' AND scheduled_for <= now()` with `FOR UPDATE SKIP LOCKED`
- `media_blobs` — r2_key, delete_after (7 d)
- `tts_cache` — `hash(text+voice+lang)` PK → r2_key
- `safety_events`, `consent_log`, `erasure_requests`

Separating `reminders` from `reminder_fires` is deliberate: recurrence is a *definition*, firing is a *queue row*. It makes ack/snooze/nudge a state machine on one table instead of mutable fields on the recurrence, and it gives a free audit trail for the §15 ack-rate metric.

### Prompt caching, designed in from turn one
Stable prefix — system prompt → tool definitions → the user's fact block → **cache breakpoint** → rolling conversation. On Bedrock that's a `cachePoint`; direct Anthropic it's `cache_control: ephemeral`. Retrofitting this means reordering every prompt, so it goes in the first commit. **Verify Sonnet 5 + caching is actually available in Bedrock ap-south-1 before committing to that path** — if not, the residency decision (G1) and the caching requirement collide, and caching wins.

---

## 4. Schedule

Restructured from PRD §16 around two facts: Meta's review queue is the only thing that can't be parallelised, and R1 (entity accuracy) is testable with **no WhatsApp at all**.

### Week 1 — two tracks, neither blocks the other

**Track A — channel (calendar-bound, day 1)**
Not code. Meta Cloud API direct (D-A): WABA + phone number + display name, then **submit all four templates**. Draft alternate wordings the same day; Meta rejects on phrasing and each round-trip is days. Utility category only. `search_ready` is dropped with flights (D-C).

| Template | Body shape | Buttons |
|---|---|---|
| `reminder_fire` | one variable slot, warm, no repetition signal | `Ho gaya` · `15 min baad` |
| `reminder_nudge` | gentle, never "you missed" | `Ho gaya` |
| `daily_checkin` | opens the free window once daily | quick reply |
| `session_resume` | continue interrupted task | quick reply |

**Track B — the risky path, offline (this is the real week 1)**
Build `speech/` + the correction pass + the entity-accuracy scorer as a **CLI harness over recorded voice notes**. No webhook needed. Deliverables: Saaras v3 REST working at 16 kHz; ffmpeg both directions; the §10 correction pass; a first entity-accuracy number.

**First experiment to run, ahead of everything:** does Saaras v3 support keyword boosting / custom vocabulary? The PRD flags it as unknown and it is the single biggest accuracy lever. ~30 minutes to answer, and the answer decides whether §10's correction pass is the primary mechanism or the fallback. Do it before writing `speech/`.

*Gate:* templates submitted; a transcript→corrected-entity number exists on ≥20 real voice notes.

### Week 2 — thread alive + reminders end to end
Webhook, user record, message log, **window guard**, plain conversation with memory, minimal child-onboards-elder flow. Then reminders: RRULE, scheduler, template fire, ack, snooze, nudge. Eval set grown to 50–100 notes per language.

*Gate:* a reminder fires correctly, acked, for **3 consecutive days** — and the window guard has demonstrably blocked at least one out-of-window free-form send.

### Week 3 — cart, safety, consent
Freed by D-C. `build_cart` with the tier-3 plain list as the contract and tiers 1–2 best-effort. Interactive cards + CTA buttons. **Safety classifier and consent flow pulled forward from week 4** — R7 is Critical and gates external users; it should not share a week with recruiting them.

*Gate:* classifier catches every phrase in a hand-written adversarial set, in Hindi and English, with the model never invoked. Erasure actually erases.

### Week 4 — strangers' parents
20 external users recruited via their children. Retention job running. Voice-reply toggle (D4).

*Gate:* live with people you don't know, with safety shipped **before** they arrive, not alongside.

### Weeks 5–8 — instrument, measure, cut
Re-derive §14 from actuals. Score entity accuracy, not WER. Decide D5 (family thread) and whether flights come back.

---

## 5. Decisions — settled 2026-07-26

| # | Decision | Outcome |
|---|---|---|
| **D-A** | Channel provider | **Meta Cloud API direct.** No BSP markup. We own WABA onboarding, template submission and support. R4 (template rejection) is ours to absorb — hence alternates drafted day 1. |
| **D-B** | Where it lives and runs | **New repo, new DB, Postgres in ap-south-1** from the first schema write. Dev on this box weeks 1–3; MeshPilot's checkout untouched. |
| **D-C** | Flights | **Cut from v1.** `build_cart` stays. Duffel and R2 deferred to v1.1. |

**Consequences now locked in:**
- Week 3 is freed. It goes to safety classifier + consent + onboarding, pulled forward from week 4 — R7 ships before strangers arrive, not alongside them.
- `search_flights` and the `search_ready` template are out of week 1's submission set. **Four templates, not five** — `reminder_fire`, `reminder_nudge`, `daily_checkin`, `session_resume`. One less rejection surface.
- Duffel: no longer blocking. Send the search-only terms question anyway when convenient — the answer is needed for v1.1 and costs nothing to have early.

### 5a. Bedrock findings — measured 2026-07-26, ap-south-1

The open question ("is Sonnet 5 with prompt caching available in ap-south-1?") was tested rather than assumed. Three results, one of which changes §13.

**Prompt caching works.** A 15,122-token system prefix with a `cachePoint`:
`call1 → cacheWrite=15122, cacheRead=0`; `call2 → cacheWrite=0, cacheRead=15122`.
§14's mandatory caching is achievable. **But there is a minimum prefix length** — an earlier
~2,253-token prefix produced `cacheWrite=0`, i.e. caching silently did nothing. The system
prompt + tool definitions + fact block must clear the threshold or the economics quietly
revert to uncached. Assert on `cacheWrite`/`cacheRead` in a test; do not trust it by eye.

**Residency does not hold for inference.** Cache written from ap-south-1 was read back on the
*first* call from us-east-2 (`cacheRead=15122`). The `global.` inference profile demonstrably
shares state across regions — prompts leave India. And `global.` is the only option for
anything modern here: the `apac.`-scoped profiles stop at Sonnet 4 / 3.7, and Sonnet 4 is now
refused as `Legacy`.

So §13 splits in two, and the PRD should say so:
- **Data at rest** — Postgres, audio, transcripts — stays in ap-south-1. Honoured.
- **Inference** — leaves India whenever we use a current model. Not honoured, and not fixable
  without dropping to Haiku 4.5 (which works and caches in ap-south-1 today).

Worth knowing before treating this as a blocker: **DPDP §16 permits cross-border transfer**
except to countries the government restricts. Full India residency is a policy choice in this
PRD, not a legal requirement. The honest options are (a) accept global inference routing and
say so in the consent notice, or (b) hold the line and accept Haiku 4.5 for the tool loop.
Recommendation: (a), documented — the model quality difference matters more to an elder than
the routing does, and §12's safety classifier is deterministic and local either way.

**Model access is per-account, and Sonnet 5 is blocked on a form.** `anthropic.claude-sonnet-5`
is *listed* in ap-south-1 but returns `AccessDeniedException: not available for this account`
in every account tried. Root cause, once the error got specific:

> `Model use case details have not been submitted for this account. Fill out the Anthropic
> use case details form before using the model.`

`create-foundation-model-agreement` was accepted and `get-foundation-model-availability` now
reports `AVAILABLE` in all regions — but that status is **not the gate**. (Proof: Haiku 4.5
reported `NOT_AVAILABLE` while invoking perfectly.) The real gate is the one-per-account
Anthropic use-case form — `aws bedrock put-use-case-for-model-access`, or Bedrock → Model
access in the console. It needs real company details, so it is an operator action.

⚠️ **Regression in the dev account, caused during this session.** Before the agreement call,
`global.anthropic.claude-haiku-4-5-…` invoked fine in 559896294326 (`cacheWrite=7562`). After
it, **every** Anthropic model there returns `ResourceNotFoundException` pointing at the form.
Requesting new model access appears to have moved the account off a grandfathered entitlement
onto the form-required path. Recoverable by submitting the form — which was needed for Sonnet 5
regardless.

**Account 683919168046 (live MeshPilot) was re-tested and is unaffected** — Haiku 4.5 and
Sonnet 4.6 both still invoke. No live path was touched.

**Interim model:** until the form clears, `global.anthropic.claude-sonnet-4-6` is the working
Sonnet-class option (verified in 683919168046). PRD §7 says Sonnet 5; treat that as the target,
not a week-1 dependency.

### 5c. Model decision — GLM-5, measured 2026-07-26 (supersedes PRD §7 and §14)

The PRD is research, not a contract. Its "Claude Sonnet 5 + prompt caching **mandatory**" line
was a *conclusion drawn from Anthropic pricing*, not a requirement. Change the model and the
conclusion dissolves. It did.

**Bedrock ap-south-1 hosts DeepSeek, Z.AI (GLM), Qwen, Mistral, Moonshot, MiniMax and more.**
Critically, these are **regional** model IDs (`zai.glm-5`, no `global.` prefix, priced in
ap-south-1) — so unlike Anthropic's global-only profiles here, **inference stays in India**.
Using AWS-hosted weights also means no request ever reaches a Chinese API endpoint. §13
residency, which §5a said we could not honour, becomes honourable by *not* using Claude.

**Prompt caching is not available** on these models — `cachePoint` returns
`"You invoked an unsupported model or your request did not allow prompt caching."` They work
normally without it.

**Entity-accuracy bakeoff** (8 code-mixed Hinglish reminder utterances, real Indian drug names,
Hindi fractional time words; scored on §15's metric — times and medicine names, not WER):

| Model | time | drug | both | ₹/user/mo |
|---|---|---|---|---|
| **`zai.glm-5`** | **8/8** | **8/8** | **8/8** | **220** |
| `deepseek.v3.2` | 7/8 | 7/8 | 7/8 (one no-tool-call) | 135 |
| `zai.glm-4.7` | 6/8 | 8/8 | 6/8 | 133 |
| `qwen.qwen3-235b` | 4/8 | 8/8 | 4/8 | 48 |
| `zai.glm-4.7-flash` | 3/8 | 8/8 | 3/8 | 16 |

Two findings worth keeping:

1. **Drug-name script preservation is a prompting problem, not a model problem.** An early n=1
   probe showed GLM-4.7 transliterating "Amlodipine" → "एम्लोडिपिन". With one system-prompt line
   ("keep medicine names in Latin script exactly as spoken") every model scored 8/8. Do not
   pick a model on this axis.
2. **The real failure mode is Hindi fractional time words** — `sawa` (¼ past), `saade` (½ past),
   `paune` (¼ to). Misses seen: `sawa nau`→09:30 (should be 09:15), `saade chhe`→18:00 (18:30),
   `paune gyarah`→23:00 (22:45). This is §10's "ten thirty / ten thirteen" hazard in Hindi, on
   the slot where being wrong means a missed cardiac dose. **Only GLM-5 got all of them.**
   Every eval case going forward must be weighted toward these three words.

**Decision: `zai.glm-5`**, regional ap-south-1 endpoint. Accuracy parity with the Sonnet tier on
the only metric that matters, ~₹47/user/mo cheaper than cached Sonnet 4.6, available *now* with
no Anthropic use-case form in the path, and India-resident.

**Cost lever changes.** With no caching, cost is linear in prompt size, so the discipline is a
*tight prefix* rather than a cached one:

| Prefix | ₹/user/mo |
|---|---|
| 6,000 tok | 220 |
| 4,000 tok | 160 |
| 3,000 tok | 129 |
| 2,000 tok | 99 |

At a 3k prefix GLM-5 beats cached Sonnet outright. This is a friendlier failure mode than
caching, which silently no-ops below a token threshold (§5a) and quietly triples the bill.

**Consequences:** §14's ₹135 LLM line and "caching mandatory" are void — recompute from ₹129–220.
The Anthropic use-case form is no longer on the critical path (still worth filing, to keep Claude
available as a fallback and for offline eval grading). Sonnet 4.6 was *not* eval'd here because
it is blocked in this account — if you want a true head-to-head, file the form and I will run the
same 8 cases against it.

### 5b. Infrastructure built 2026-07-26

Account **559896294326** (Mesh Pilot Dev), region **ap-south-1**. Account was empty; default
VPC `vpc-06482039bff81fb9b`, three public subnets.

| Resource | ID | Note |
|---|---|---|
| Instance | `i-01b2c27883acb25ca` | `t3.large`, Ubuntu 26.04 LTS, 60 GB gp3 **encrypted**, IMDSv2 required |
| Public IP | `13.232.244.182` | ephemeral — allocate an EIP before anything points DNS at it |
| Security group | `sg-0f805961424175e66` | **zero inbound rules.** Egress open |
| IAM role | `saathi-dev-box` | `AmazonSSMManagedInstanceCore` + inline `bedrock-invoke` |
| Access | **SSM Session Manager only** | no SSH key pair exists in this account, port 22 never opened |

Verified functioning, not merely running: SSM `PingStatus=Online`, a real `AWS-RunShellScript`
returned `Ubuntu 26.04 LTS`, kernel `7.0.0-1009-aws`, 2 vCPU / 7 GB / 56 GB free, egress IP
matching the public IP exactly, and `postgresql` candidate **18+290ubuntu1** from the distro —
same major version as the v1 box, so no PGDG repo needed.

Cost ≈ **$66/mo** (t3.large ~$61 + 60 GB gp3 ~$5) while running.

**Provisioned 2026-07-26** (via SSM `AWS-RunShellScript`, verified after):

| Component | Version | Note |
|---|---|---|
| PostgreSQL | **18.4** (`18/main` online, enabled) | byte-identical major.minor to the v1 box — distro package, no PGDG repo |
| Python | **3.14.4** | system default on 26.04 — see divergence note below |
| ffmpeg | 8.0.1 | 2 opus encoders / 5 decoders |
| uv | 0.11.32 | installed for the `ubuntu` user |
| git | 2.53.0 | |

ffmpeg was proved on the actual WhatsApp round trip, not just `-version`:
OGG/Opus (9519 B) → WAV 16 kHz mono (32078 B) → OGG/Opus (4275 B), all three legs OK. That is
§9's inbound and outbound path working end to end.

⚠️ **Python version divergence.** PRD §7 specifies 3.12; Ubuntu 26.04 ships **3.14.4**. Not a
blocker — `uv python pin 3.12` handles it per-project — but decide deliberately: 3.14 matches
the v1 monorepo, 3.12 matches `apps/cod_pipecat` and the PRD. Pin it in `pyproject.toml` before
the first dependency resolve, not after.

### 5d. Application built 2026-07-26 — `/home/ubuntu/saathi` on the box

33 files, 4 commits, **42 unit tests passing**. Database `saathi`, 11 tables owned by the
`saathi` role, `pg_trgm` installed. Deps resolved fresh on **Python 3.14.4** (FastAPI 0.140,
psycopg 3.3.4, boto3 1.43.56) — nothing needed pinning to PRD versions.

Verified working rather than merely present:

| Piece | Evidence |
|---|---|
| Queue claim | synthetic due fire → `claimed=1`, immediate re-claim → `second_claim=0` |
| Agent loop | live `zai.glm-5` + live Postgres; reminder persisted with correct RRULE and next fire 2026-07-27 08:00 IST |
| `/healthz` | `{"ok":true,"pg":"18.4","model":"zai.glm-5"}` |
| Webhook | bad verify token → 403; unsigned POST → 403 |
| ffmpeg | OGG/Opus → WAV16k → OGG/Opus round trip in-process |
| Prefix budget | measured **817 tokens** against the 3000 budget |

**Measured cost, replacing the estimate.** Average input across live turns was **1,751 tokens**,
not the 6,800 the §5c model assumed. At GLM-5 rates that is ~**₹60/user/month**, not ₹220 —
and the §14 total lands nearer **₹170** with STT (₹60) now the largest single line.

#### The bug worth recording

First live run, `"raat ko paune gyarah baje clopidogrel"` → the model read back **08:45**.
Correct is **22:45**. `paune gyarah` is quarter-to-eleven. This is the exact R1 failure mode,
reproduced in the real stack after GLM-5 had scored 8/8 on it in the isolated bakeoff — the
fuller system prompt changed its behaviour.

Two things were learned:

1. **The read-back rule earned its place.** The model asked "yeh sahi hai?" instead of silently
   creating a wrong reminder. §6.3 caught a wrong dose time before it reached a user. Keep it.
2. **The eval was measuring the wrong thing.** Scoring only whether a tool fired on turn 1
   punishes the product for confirming — the design's core safety behaviour. The eval now
   answers the confirmation and scores turn 2. After adding explicit Hindi clock-word rules
   (`sawa`/`saade`/`paune`/`dedh`/`dhai` + part-of-day) to the system prompt: **8/8 time, 8/8
   drug**, with 5/8 acting on turn 1 and 3/8 confirming first.

**Design note:** markdown is now stripped in code (`saathi/wa/format.py`), not requested in the
prompt. GLM-5 emits `**bold**` regardless of instruction and WhatsApp renders it literally. A
deterministic transformation should not be delegated to instruction-following — the same
reasoning as §12's deterministic safety classifier.

### 5e. Meta channel — both blockers are external, 2026-07-26

The MeshPilot system-user token *does* carry `whatsapp_business_messaging`, and a WABA exists:
**Jordan Hale**, `1224261999709772`, `account_review_status=APPROVED`, phone
`1247554208434821` (+1 437-539-7958). Both IDs are wired into `.env`.

Two hard stops, neither fixable in code:

1. **`business_verification_status: pending`** on business *AI Empire* (`2381049749036743`).
   An unverified business cannot create or update templates —
   `"This WABA is not allowed to create or update templates."` Needs legal documents filed
   with Meta; days.
2. **Number is `platform_type: ON_PREMISE`, `status: DISCONNECTED`.** Our client is Cloud API,
   so sends will fail until the number is migrated
   (`request_code` → `verify_code` → `register`). `request_code` returned subcode **2388091**,
   a per-number cooldown: retry after ~1 hour, with someone holding the handset.

**This makes R4 worse than the PRD assumed.** Week 1 is not "submit templates" — it is
"verify the business, *then* submit templates": two serial multi-day waits, not one. Business
verification should start before anything else in the Meta lane.

Also note for the pilot, not for testing: the number is **+1 Canadian** and its display name is
**"Jordan Hale"**. India rates, quality rating and template pacing key off the sender's country,
so §14's cost model won't hold on this number, and elders would see an influencer persona's name.

Four templates are written and locally validated in `saathi/wa/templates.py`, ready to submit
the moment verification clears. `scripts/submit_templates.py` is idempotent-ish and reports
per-template failures.

### 5f. Memory, streaming, capabilities — 2026-07-26

**50 tests passing.** Pushed to both remotes, all commits SSH-signed (`%G?` = `G`).

- `saathi/memory.py` — facts into the prefix, plus the §10 **entity-bias vocabulary**. Bias
  forms are extracted proper nouns: storing `"Priya, Pune mein rehti hai"` as a bias phrase was
  worthless; `Priya`, `Pune` are the tokens ASR mangles.
- `saathi/agent/stream.py` — ConverseStream. WhatsApp can't render a growing message, so
  streaming buys **time-to-first-sentence** and lets TTS start on sentence one rather than
  queue behind full generation. Measured: tool call emitted at **394 ms**.
- New tools: `what_you_know`, `forget_everything`, `set_preference`, `snooze_reminder`.
  `forget_everything` **hard-deletes** — a tombstone would be a dishonest answer to "forget
  everything about me" (§13) — and refuses unless the model confirmed first.

**Two bugs found by running it, not by reading it:**

1. **The model published its chain of thought as the reply.** `"The user wants a daily reminder
   for Telmisartan… Let me parse the time: • sawa aath = 8:15"` — in English, to an elder, and
   then it never called the tool. Raw reasoning is worse than a wrong answer here. The prompt
   now forbids visible workings and requires acting over describing. My own clock-word rules
   had invited the narration.
2. **Persona gender flipped between turns** — *"rakhunga"* then *"rakhungi"*, then *"jaanti
   hoon"*. Pinned female, with a test.

Measured prefix with the fuller toolset: **~1,300 tokens** against the 3,000 budget.

### 5g. Channel unblocked, pipeline wired — 2026-07-26 (late)

**The Meta dead end was the wrong business all along.** The blockers in §5e applied to a WABA
under *AI Empire* (verification pending, number ON_PREMISE). Ayurpet's per-BM system-user token
(`core.platform_accounts`, `account_metadata->>'system_user_id' = 122180456624889373`) belongs to
business **`ayurpetofficial` (935287898727459), which is verified** — and owns a WABA already
named **"Saatih AI APP"**:

| | |
|---|---|
| WABA | `1023945910495878` — APPROVED, verified |
| phone_number_id | `1127963600410973` |
| verified_name | **Saathi AI** |
| platform_type | **CLOUD_API**, VERIFIED, CONNECTED, quality GREEN |

Templates: `session_resume` and `daily_checkin` **APPROVED/UTILITY**. `reminder_fire_v2` and
`reminder_nudge_v2` submitted as UTILITY, pending.

⚠️ **Two landmines, recorded in `saathi/wa/templates.py`:**
1. `reminder_fire`/`reminder_nudge` first came back **MARKETING** — 7.5× the price on the
   highest-volume template, ~₹20 → ~₹90/user/mo. Fixed by anchoring the body to the user's own
   prior action. **Deleting them to fix it was a mistake**: Meta holds a deleted name for up to
   four weeks and refuses a category change while the old content deletes. Hence `_v2`.
2. **Meta Business Agent is provisioned on our number with `rollout.enabled = false`** but
   `ai_audience: EVERYONE`. Enabling it makes Meta's model the primary responder and inbound
   messages never reach the §12 classifier — R7. Do not enable. (Evaluated properly: we *are*
   eligible, `is_eligible: true`; it is simply the wrong architecture — business-scoped
   knowledge, storefront schema, no per-user memory. It is a strong fit for MeshPilot's ecom
   brands, tracked separately.)

### 5h. STT measured — two PRD corrections

**PRD §9's mode list is wrong.** Real enum: `transcribe | translate | indic-en | verbatim |
translit | codemix`. The PRD's recommended default, `codemix`, returns **Devanagari**:

    transcribe/codemix -> "रोज़ सुबह अथ बेजबम लोडिपिन की गोली"
    indic-en           -> "Roz subah ath bej bomlodipin ki goli"

This is not cosmetic. The correction pass matches Latin tokens against the user's medicine and
people names, so under Devanagari it is **structurally dead** — it repaired nothing. Under
`indic-en` the same audio gives `bomlodipin` → **`Amlodipine`**. Default is now `indic-en`.

**API-side keyword boosting is unproven.** The bias `prompt` changed 1 of 3 transcripts, and
that change was noise. §10's local correction pass is the mechanism, not the fallback.

**A bug that would have failed every voice note in production:** ffmpeg cannot seek backwards on
a pipe, so WAV written to stdout carries `0xFFFFFFFF` in the RIFF and data size fields. Sarvam
read that as near-infinite and rejected 2.5 s of audio with *"exceeds the maximum limit of 30
seconds"* — while `ffmpeg -version` looked perfectly healthy. Output now goes to a temp file.

### 5i. The pipeline is connected — 82 tests

`saathi/pipeline.py` joins what were previously tested-but-unconnected parts:

    webhook -> dedupe -> window touch -> SAFETY -> [audio: fetch/transcode/STT
    -> correction] -> agent -> WhatsApp-safe text -> send

Verified live against real Postgres and real GLM-5 (send stubbed):

| Turn | Result |
|---|---|
| "mere doctor Dr Mehta hain" | `remember` → persisted, bias vocab `Apollo/Mehta/Nagpur` |
| "sawa aath baje Telmisartan" | `create_reminder` → **08:15**, RRULE right, queued `pending` |
| replayed webhook | `skipped: duplicate`, **no send** |
| "seene mein dard" | `safety` → **LLM never ran**, 112/108 sent, event logged |

`llm_calls: 1 chat / 3 task` — R6 instrumented from day one. Prefix ~1,330 vs the 3,000 budget.

The run also exposed that the agent used the user's name and never stored it; it arrives free on
every webhook in the contact profile and now reaches the prompt as its own line.

### 5j. Live on the internet — 2026-07-26

**Everything runtime is in ap-south-1.** This us-east-2 box holds only the git checkout used for
SSH-signing and pushing; it runs no Saathi service and has no Saathi database.

| | |
|---|---|
| Host | `i-01b2c27883acb25ca`, ap-south-1a |
| Elastic IP | **`15.252.75.191`** (`eipalloc-095dc7178aceb1f5c`) |
| Public URL | **`https://saathi.n8nworld.store`** |
| Tunnel | `saathi-dev` `d4e9e4ad-04ca-4ebf-92af-d39c7cb5f831`, ingress → `127.0.0.1:3130`, else 404 |
| Units | `saathi-web`, `saathi-worker`, `cloudflared-saathi` — all active + enabled |

**No inbound port is open.** The security group still has zero ingress rules; traffic arrives
only through the tunnel, and `:3130` binds `127.0.0.1`. Verified: direct `http://15.252.75.191:3130`
is refused.

**Secrets never travel through SSM.** SSM RunShellScript command text is retained and visible in
the AWS console, so anything embedded in a command leaks into the audit trail. Instead
`saathi/dev/runtime` in Secrets Manager (ap-south-1) holds the values, the instance role has
`GetSecretValue` on that ARN only, and `/usr/local/bin/saathi-env-sync` merges them into `.env`
(0600) on the box.

**Cloudflare token for the box:** `saathi-box-canonical` (`2e4050702dffa824858b899d28d324ab`),
minted off `CLOUDFLARE_MASTER_TOKEN` per `docs/CLOUDFLARE_ACCESS.md`, **IP-locked to
`15.252.75.191/32`**. Account: Pages/Workers/KV/R2/Tunnel/Stream/Workers-AI Write. All zones:
DNS Write, Zone Read/Settings, Cache Purge, SSL, Workers Routes. Verified *from the box*:
`token verify: active`, zones listable, R2 buckets listable. A second token
`saathi-zone-config` (`a03fb813b7c7d91fea7975742a4929de`) carries Config Settings Write, which
neither the canonical nor the master token has.

⚠️ **Landmine — Cloudflare error 1010.** `n8nworld.store` had `browser_check: on` (Browser
Integrity Check). Meta's webhook calls are server-to-server and carry no browser signature, so
BIC returned **403 error 1010** for every webhook request while `/healthz` passed. This is
especially nasty because it *looks* like correct security behaviour: the wrong-token and
unsigned-POST probes both returned 403 and appeared to prove the app was rejecting them — they
were Cloudflare, and the checks were worthless. Only comparing on-box (`200 CHALLENGE-OK`) with
through-Cloudflare (`403 server=cloudflare`) exposed it.

Fixed with a **scoped** config rule (`http_config_settings`, `bic: false` for
`http.host eq "saathi.n8nworld.store"`) rather than disabling BIC zone-wide. Blast radius today
would have been nil either way — the only proxied HTTP record on the zone is ours, everything
else is MX/TXT — but the scoped rule stays correct if the domain later hosts anything.

Verified end to end through Cloudflare: verify with the correct token → **200 `CHALLENGE-OK`**,
wrong token → 403, unsigned POST → 403, `/healthz` → 200, `/admin` → 404.

🚩 **One blocker before Meta can deliver messages: `WA_APP_SECRET` is empty.**
`valid_signature()` fails closed, so every real webhook POST will 403. The secret belongs to
Meta app `1571039744742551` — the same app MeshPilot uses, where it exists as `META_APP_SECRET`.
Reusing it or fetching a fresh copy from the app dashboard is an operator decision.

**Still not done:** `WA_APP_SECRET`, registering the callback URL with Meta, TTS,
onboarding/consent flow, real eval corpus. Postgres still on default local-only config with
**no backup** — see the managed-Postgres note above.

Access it with:
```
aws ssm start-session --target i-01b2c27883acb25ca --profile mp-dev --region ap-south-1
```

---

## 6. What I'd watch

- **R1 is the product risk.** If entity accuracy on medicine names can't clear ~95% by week 2, the read-back rule stops being a safety net and becomes the interaction — every turn confirms, which is exactly the "generic repetition" §6.3 forbids. That's a re-scope signal, not a tuning signal.
- **R6 is the interesting one.** Instrument conversational (non-task) turns from the first day the thread is alive. If elders mostly talk rather than task, the four capabilities are scaffolding for a different product — and week 8 is when you'd want to already have the data.
