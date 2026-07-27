# Changelog

What changed in the code, and — more usefully — **what broke and how we found
out**. Most of the entries below were discovered by running the thing, not by
reading it, and several looked healthy right up until they didn't.

Conventions:
- Newest first. One heading per working session, dated.
- **Broke / Fixed** entries name the *symptom first*, because that is what you
  will be searching for at 2am.
- Every behaviour change should have a test; where one exists it is named.
- Infrastructure and third-party facts live in `docs/RUNBOOK.md` and
  `docs/LANDMINES.md`; this file is for the Python.

---

## 2026-07-27 (evening) — Saathi moves to an Indian number

No Python changed. Configuration and Meta-side state only, but it changes what
the product *is*: Saathi now answers on **+91 8071 581 944** as **"Indofolk AI"**,
not on a +1 Canadian number as an unnamed sender.

### Verified live

A real WhatsApp message reached the product end to end: inbound "Hii" at
04:41:50 → `POST /webhook/whatsapp` 200 → user row created → deterministic
onboarding replied with the bilingual consent prompt and three quick-replies,
rendered correctly on the handset. Worker heartbeat kept flowing across the
switch.

### Changed

- `WA_PHONE_NUMBER_ID` → `1266402176549539`, `WA_BUSINESS_ACCOUNT_ID` →
  `1687148075730227`, **in Secrets Manager** — editing `.env` alone would have
  been silently reverted by the next `saathi-env-sync`. Old ids retained as
  `*_OLD_CA` rather than dropped.
- Four templates re-submitted on the new WABA under the **same names**, so no
  code change: `turns.py` references them as string literals. All four came back
  `UTILITY`, not MARKETING — the anchoring wording from the first fight held.

### Found

- **Onboarding never records outbound messages** (PR-31). The first exchange
  every user has, including the consent text, is absent from `messages` — the
  table the backups actually protect. 1 inbound, 0 outbound after a conversation
  the user could see on screen.
- **Template quick-replies return button *text*, not a payload.** `reminder_fire_v2`
  carries `Ho gaya` / `15 min baad` as approved QUICK_REPLY buttons, so
  `pipeline.handle_ack` — which parses `ack:{id}` — can never match. That refines
  PR-4b: the fix is a `button` component with a dynamic payload, or matching on
  the text.
- Vobiz briefly held webhook access to every inbound message (PR-29), removed.

Decision recorded as **D-M**.

---

## 2026-07-27 (later still)

**314 tests passing.**

### Broke

- **A forwarded advert silently stopped someone's medication reminders.** No
  error, no bounce, nothing in the logs — the reminders just never arrived
  again. `commands` runs at priority 22, long before the agent, and matched on
  raw text without asking who wrote it. STOP matches `\bunsubscribe\b` as a
  *substring*, and nearly every forwarded marketing message carries that word in
  its footer. Matching set `users.paused = true`, and `worker/turns._handle`
  silently declines to send to a paused user. It needed no attacker — one
  relative forwarding a promo did it, and it persisted until the user happened
  to say "resume". Found by Codex's security scan (SEC-2); the `unsubscribe`
  substring and the reminder consequence were traced while fixing it.

### Fixed

- `saathi/capabilities.py` — the priority-22 matcher now requires `c.trusted`.
  The check lives in the *matcher*, not the handler: an unmatched capability
  falls through to the agent, which already fences relayed text and withholds
  mutating tools, so the safe behaviour is reused rather than reinvented.
  Relayed text is still read and explained — just never obeyed.
- Priorities 20/21 unchanged: they key on `button_id`, and a tap is first-party.
- Onboarding (10) deliberately **not** guarded — gating it would drop an
  un-onboarded user to the agent and break "onboarding never calls the model",
  which is what makes an open door safe.

### Tests

`tests/test_relayed_commands.py` (9). Verified they fail without the guard —
4 of the 9 go red when it is reverted, so they test the thing they claim to.

---

## 2026-07-27 (later)

Alerting built (PR-3). **305 tests passing.**

### Added

- `saathi/metrics.py` — CloudWatch publisher that never raises. A metrics outage
  must not stop a reminder going out, so `emit` swallows everything and returns
  a bool. It logs at ERROR rather than WARNING, because the heartbeat alarm
  treats missing data as breaching: when this module fails, the alarm starts
  lying, and whoever gets paged needs that line.
- `saathi/worker/__main__.py` — publishes `WorkerHeartbeat` and `TurnsDispatched`
  *after* a successful tick, so the signal means "the worker did its job", not
  "the process exists". Runs in a thread because boto3 is synchronous and
  blocking the loop delays every reminder in the batch.
- `ops/alerting/` — `saathi-alert` (OnFailure publisher), `saathi-metric` (one
  datapoint, for units that are not Python), the systemd template, and an
  idempotent `install.sh`.

### Learned

- **`OnFailure=` barely applies to `saathi-worker`.** It is `Restart=always`
  with `StartLimitBurst=5`, so a crashing worker re-enters `active`, not
  `failed`, and a crash-loop looks alive. The heartbeat alarm is what actually
  catches it. Discovered by reading the unit rather than assuming.
- **`%n` already includes `.service`.** `OnFailure=saathi-alert@%n.service`
  instantiates `saathi-alert@saathi-worker.service.service`. It resolves, but
  `%N` is the suffix-less form and is what you want.
- **A topic with no confirmed subscriber accepts publishes happily.**
  `NumberOfMessagesPublished` goes up, every call returns a MessageId, and
  nobody is told anything. Check `list-subscriptions-by-topic` for
  `PendingConfirmation` before believing alerting works.

### Tests

`tests/test_metrics.py` (4) — pins both directions of the failure mode: a
metrics outage never raises, and it is always logged at ERROR.

---

## 2026-07-27

Control plane adopted; the reminder delivery path fixed. **301 tests passing.**

### Broke

- **A reminder created through the assistant would never fire.** No error, no
  failed row, nothing in the logs — the reminder simply never arrived.
  `_create_reminder` inserted into `reminder_fires`; the worker
  (`worker/__main__.py`) claims only from `scheduled_turns`; and
  `worker/reminder_scheduler.py`, the one module that reads `reminder_fires`,
  is imported by nothing. Migration 006 moved the queue and back-filled the
  existing rows once, but the *creation* path was never moved with it. Latent
  rather than live only because no real reminder existed yet — both tables were
  empty. Found by reading the dispatch path end to end while opening PR-4.
- **A recurring reminder would have fired at most once.** Nothing walked the
  RRULE after the first occurrence. `turns.reminder` now books the next one,
  dedupe-keyed on (reminder, occurrence).
- **A turn claimed by a worker that then died was stranded forever.**
  `claim_due` marks `sent` and commits before the handler runs, so the row is
  never retried (claiming reads only `pending`) and never failed (nothing
  raised). `scheduling.sweep_stuck` reclaims them.
- **`sweep_stuck`'s SQL was invalid Postgres while its unit tests were green.**
  `set state = case ... end` yields `text`; the column is the `turn_state` enum.
  The fake connection accepted it happily. Caught only by running the statement
  against the real database. See `docs/LANDMINES.md`.

### Fixed

- `agent/tools/handlers.py` — `_create_reminder` enqueues onto `scheduled_turns`
  and no longer writes to `reminder_fires`. Registration is imported locally to
  break a cycle, and `enqueue` still refuses an unregistered kind loudly.
- `worker/turns.py` — recurrence rescheduling; a deliberate no-send (paused user
  or no active handle) is marked `skipped`, so the sweep can tell "chose not to
  send" from "the send died".
- `scheduling.py` — `sweep_stuck`, guarded on `wa_message_id is null` so a
  delivered reminder is never resent. `run_once` sweeps before it claims.
- `tests/test_scheduling.py` — the fake's `returning id` match was too broad and
  fed `sweep_stuck` a one-column row. Narrowed to INSERTs.

Tests: `tests/test_reminder_delivery.py` (7 new).

### Known still broken

- **The ack path is unreachable** — lane PR-4b. `wa.send_template` sends no
  button component, so the `ack:`/`snooze:` payloads `handle_ack` parses are
  never produced; `handle_ack` updates `reminder_fires`, which no longer
  receives fires; and nothing calls `enqueue(..., "nudge", ...)`. §15's
  acknowledgement metric is structurally zero, not low.
- Nothing pages a human when dispatch stops (PR-3, blocked on IAM).

---

## 2026-07-26

First working session. PRD → live webhook. **82 tests passing**, 11 commits.

### Added

- `db/schema.sql` — 11 tables. `sessions.window_expires_at` makes WhatsApp's
  24-hour window first-class; `reminders` (RRULE definition) is split from
  `reminder_fires` (queue rows) so ack/snooze/nudge is a state machine on one
  table. `bb16dba`
- `wa/window.py` — the 24-hour gate. `assert_can_send` refuses free-form outside
  the window rather than discovering it from Meta. `bb16dba`
- `worker/reminder_scheduler.py` — Postgres `SKIP LOCKED` queue, 30 s poll,
  claim-and-mark in one statement. `bb16dba`
- `agent/loop.py`, `agent/prompt.py`, `agent/tools/` — tool loop on `zai.glm-5`,
  prefix budget enforced in code. `54dfb16`
- `safety/classifier.py` — deterministic pre-LLM classifier, Hindi + English +
  Hinglish. `tests/test_safety.py`. `54dfb16`
- `speech/audio.py` — ffmpeg both directions. `54dfb16`
- `wa/client.py` — Cloud API; every outbound path funnels through `_send`, which
  calls the window guard first. `54dfb16`
- `memory.py` — facts, ASR entity-bias vocabulary, hard erasure. `1615eb1`
- `agent/stream.py` — ConverseStream; yields complete sentences so TTS can start
  on sentence one instead of queueing behind full generation. `1615eb1`
- Tools `what_you_know`, `forget_everything`, `set_preference`,
  `snooze_reminder`. `1615eb1`
- `speech/correct.py`, `speech/stt.py` — entity correction and Saaras.
  `tests/test_correct.py`. `7cecf59`
- `wa/templates.py`, `scripts/submit_templates.py` — templates as versioned code
  with a local validator. `869dbc1`
- `pipeline.py` — the inbound path end to end. `tests/test_pipeline_order.py`
  asserts the *ordering*, not just the outcome. `161f42a`
- `worker/send_reminder.py`, `worker/__main__.py` — reminders actually fire.
  `161f42a`

### Broke / Fixed

- **`/healthz` returned `AttributeError: module 'saathi.db' has no attribute
  'pool'`.** A `saathi/db/` package and a `saathi/db.py` module both existed; the
  package shadowed the module. Deleted the package — the schema lives in the
  top-level `db/`. `fc496cd`

- **Schema applied but every table was owned by `postgres`, leaving the app role
  unable to write.** Root cause was `psql: Permission denied` on
  `/home/ubuntu/...` (mode 0750) for the `postgres` user, and the obvious fix —
  run the whole file as `postgres` — silently produced the ownership problem.
  Split into `db/extensions.sql` (superuser, `pg_trgm` is untrusted) and
  `db/schema.sql` (run as the owner). `3598f70`

- **Sarvam rejected 2.5 seconds of audio with "exceeds the maximum limit of 30
  seconds".** ffmpeg cannot seek backwards on a pipe, so WAV written to stdout
  carries the `0xFFFFFFFF` streaming placeholder in both the RIFF and `data`
  length fields, and Sarvam read that as near-infinite. **Every inbound voice
  note would have failed in production while `ffmpeg -version` looked perfectly
  healthy.** Output now goes to a temp file so the header is patched.
  Regression test asserts the size fields are real. `0d382b9`

- **The entity-correction pass repaired nothing, ever, with no error.** Saaras
  `mode=codemix` — the PRD's recommended default — returns Devanagari, and the
  correction pass matches Latin tokens against the user's medicine names, so
  there was nothing to match. Default changed to `indic-en`; the same audio then
  gives `bomlodipin` → `Amlodipine`. `0d382b9`

- **The model published its chain of thought as the user-facing reply**, in
  English, and then failed to call the tool: *"Let me parse the time: • sawa
  aath = 8:15"*. Our own clock-word instructions had invited the narration.
  Prompt now forbids visible workings and requires acting over describing.
  `1615eb1`

- **`raat ko paune gyarah` resolved to 08:45 instead of 22:45** — a wrong dose
  time, the highest-severity failure this product has. Added explicit Hindi
  clock-word rules (`sawa` / `saade` / `paune` / `dedh` / `dhai` + part of day).
  Now 8/8 through the full stack. Notably the read-back rule had already caught
  it before it reached a reminder. `1615eb1`

- **Persona gender flipped between turns** — `rakhunga` then `rakhungi` then
  `jaanti hoon`. Disorienting for this audience specifically. Pinned female,
  with a test. `1615eb1`

- **Entity-bias vocabulary stored whole sentences.** `"Priya, Pune mein rehti
  hai"` is worthless as an ASR bias hint; `Priya` and `Pune` are the tokens that
  get mangled. Now extracts proper nouns. `1615eb1`

- **GLM-5 emits `**bold**` regardless of instruction** and WhatsApp renders it
  literally, so an elder sees asterisks. Stripped in code (`wa/format.py`)
  rather than asked for in the prompt — a deterministic transformation should
  not depend on instruction-following. `1615eb1`

- **The agent used the user's name and never stored it**, so a later session
  would not know who it was talking to. The name arrives free on every webhook
  in the contact profile; it simply never reached the prompt. Rendered as its
  own line rather than pushed into `facts`, because the user never asked us to
  remember it. `19d6ec9`

### Test-suite fixes (our tests were wrong, not the code)

- `test_fact_block_renders_and_is_capped` asserted 39 occurrences of `"\n- "`
  for 40 items. The header's trailing newline means all 40 match. `19d6ec9`
- `test_pipeline_order` fakes returned a 3-tuple for the users row after
  `upsert_user` began returning four. `19d6ec9`
- The Hinglish clock eval scored only whether a tool fired on turn 1, which
  **punished the product for confirming** — the read-back behaviour §6.3
  requires. Rewritten to answer the confirmation and score turn 2. Score went
  from 6/8 to 8/8 without touching product code. `0d382b9`

### Changed

- Default model `zai.glm-5`; prompt caching removed as a requirement — it does
  not exist for this model, so the cost lever is a tight prefix instead
  (`SAATHI_PREFIX_TOKEN_BUDGET`, measured ~1,330 of 3,000). See `DECISIONS.md`
  D-D.
- Template names are `reminder_fire_v2` / `reminder_nudge_v2`. The originals are
  burned: Meta holds a deleted template name for up to four weeks. `869dbc1`

---

## 2026-07-26 (later) — identity, channels, admission

**100 tests passing.** The system now has a user model rather than a phone
number, and WhatsApp is one transport rather than the architecture.

### Added

- `db/migrations/002_identity_and_channels.sql` — `user_channels`,
  `channel_link_codes`, `conversations`; `messages` gains `channel`,
  `conversation_id`, `deleted_at`, `redacted_at`. Existing users backfilled a
  verified primary WhatsApp handle.
- `identity.py` — resolve / revoke / link. **A phone number is not an identity**;
  it is a revocable claim on one. Dormant handles (60 d, inside India's ~90-day
  recycling window) return `needs_reverification` so a recycled number cannot
  inherit an elder's medicines, doctor and family.
- `channels/` — `Transport` protocol plus `Capabilities` as *data*
  (`has_session_window`, `max_quick_replies`, `supports_voice_notes`, `markup`).
  Channels differ in ways that change product behaviour, not just wire format —
  WhatsApp has a 24 h window and 3 buttons, Telegram has neither limit — so the
  pipeline asks the transport instead of branching on a channel name.
- `conversation.py` — threads, cross-channel history for prompt context, and
  message deletion. Redaction (`redacted_at`, content nulled, row kept) is
  distinct from erasure (hard delete), so acknowledgement rates and the safety
  audit trail stay honest when a user deletes a message.
- `db/migrations/003_admission_control.sql` + admission gate — **pattern taken
  from OpenClaw's `channels.<name>.dmPolicy: pairing | open`.**

### Changed

- `pipeline.handle_message` takes `channel` and resolves a `Transport`. All
  sends, media fetches and text formatting go through it. Session-window
  handling is now conditional on `capabilities.has_session_window`.
- The agent receives conversation history, so a turn is no longer stateless.

### Security

- **Admission control.** Previously *any* number that messaged us created an
  identity and got a full agent turn — an open cost vector (LLM + STT on our
  bill), a safety surface on an eldercare agent, and junk identities. Unknown
  handles are now `pending`: they get one rate-limited, bilingual, actionable
  reply and no model turn. Default policy is `pairing`, not `open`.

### Test-suite fixes (ours, not the code's)

- Fake cursor lacked `rowcount`; fake conn truncated captured SQL at 60 chars so
  redaction assertions could not see the clauses they were checking.
- Pipeline fakes still patched `pipeline.wa` and returned a 6-column handle row
  after the refactor added `status`.
- `Resolved` briefly had a defaulted field before a non-defaulted one.

---

## 2026-07-26 (evening) — architecture, capabilities, provenance

**224 tests passing.**

### Changed — capabilities register instead of branching

`handle_message` was an if/elif ladder growing a branch per feature. A capability
is now `(priority, matches, handle)` registered in `capabilities.py`, which read
top to bottom *is* the spec of the inbound path. Safety holds priority 0 and a
test asserts it cannot be overtaken; a handler that raises is logged and skipped
rather than killing the turn. Empty text now falls off the end of the chain
instead of needing its own branch.

### Added

- `vision.py` — medicine packs, letters, photos. `qwen.qwen3-vl-235b-a22b`,
  chosen because it is *regional* to ap-south-1: a photograph of a prescription
  must not leave India, and the Anthropic vision models here are global-only.
  Health-adjacent answers carry their disclaimer by construction.
- `documents.py` — PDF text layer first, rasterise page one as fallback.
- `onboarding.py` — deterministic, button-driven, **no model call**, which is
  what makes an open door safe.
- `commands.py` — stop/resume/help/what-you-know/clear/delete, model-free, so a
  DPDP erasure request works even when Bedrock does not.
- `net_policy.py` — SSRF blocking and secret redaction (ported MIT from
  OpenClaw). Root logger filter, so redaction does not depend on anyone
  remembering.
- `provenance.py` — forwarded messages, quoted replies and text lifted from
  media are `RELAYED`: content, never command. State-mutating tools are withheld
  for the turn. Withholding beats filtering because an absent capability does not
  care how the attack is phrased.

### Broke / Fixed

- Transport spy in the onboarding tests captured button **IDs** instead of
  labels, so a length assertion was checking the wrong strings.
- `band karo` did not match STOP: `\bband kar\b` requires a boundary that
  "karo" does not provide.
- `Resolved` briefly had a defaulted field before a non-defaulted one.
- Onboarding tests reached the real `send_buttons` because the spy only patched
  `send_text`, so the window guard raised on a fake connection.
