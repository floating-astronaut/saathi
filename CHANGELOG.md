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
