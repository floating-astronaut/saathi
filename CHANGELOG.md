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

## 2026-07-28 (hardening) — an inbound document had no limit, and never arrived

**366 tests passing** (337 before). PR-26.

### Broke

- **Every inbound document failed before it reached the reader.** Send a PDF and
  nothing comes back — no reply, no refusal, just a `failed handling wamid.…`
  in the web log. `handle_message` logs the message before it dispatches, and it
  logged WhatsApp's wire type: `insert into messages … kind = 'document'`, which
  Postgres answers with `invalid input value for enum msg_kind: "document"`.
  The transaction aborts and the whole turn unwinds, so the media capability at
  priority 30 never ran. The `msg_kind` enum has six values and `document` is
  not one of them.

  Not caught by the suite for the reason `LANDMINES.md` already records: the
  fake connection records the SQL string and never parses it. Confirmed against
  the real database instead — `select 'document'::msg_kind` errors.

  Fixed by coercing the wire type at the single write path (`_msg_kind`), which
  logs a warning and records `text`. The row exists for dedupe and for the
  transcript, and both survive the coercion. `MSG_KINDS` is asserted against
  `db/schema.sql` by a test, so the two cannot drift.

- **A timed-out `pdftoppm` was not killed, only abandoned.** `wait_for` cancels
  *our wait*, not the renderer, so an overrunning rasteriser kept a core on a
  two-core box and nothing was left holding a reference to it. It is now killed
  and reaped, and the test asserts the child's exit status is `-9` rather than
  asserting our exception — a shrug and a kill produce the same exception.

- **A killed render left the sender's PDF and a partial PNG in `/tmp`.** Cleanup
  only ran on the success path, and only for the one filename it guessed right.

- **A `.docx` was sent to the vision model as if it were a photograph** — one
  model call spent to produce nothing, and then silence for the user.

- **The rendered page was briefly world-readable.** `pdftoppm` creates the PNG
  itself, under our umask, so someone's prescription or bank letter sat in
  `/tmp` at 0644 until we deleted it. Both files now live in a `mkdtemp` 0700
  directory, which also makes the cleanup one call that cannot miss one.

### Fixed — resource limits on inbound media (PR-26)

Onboarding is open, so "a valid sender" is a low bar. Every limit below is a
bound on what *one* message may cost a box with 2 vCPU and 8 GiB that is also
running the reminder worker.

- **A byte cap before and during the download, not after.**
  `wa.client.fetch_media` now takes `max_bytes` with **no default** — a new call
  site must say what it can afford — and checks three times, cheapest first:
  Meta's own `file_size` from the metadata call (so a 90 MB PDF costs no
  bandwidth at all), `Content-Length`, and then the bytes as they stream, which
  is the only one of the three we supply ourselves. A size we could not
  determine is not treated as small. 8 MiB for PDFs, 5 MiB for photographs —
  which is the vision model's own ceiling, so the two cannot drift and leave us
  holding a blob we already refuse to use.
- **`pypdf` runs off the event loop**, in a thread pool the same size as the
  document gate, with an 8s wall clock. It was synchronous and inline: a content
  stream that took ten seconds to decode took ten seconds of everybody else's
  turns with it.
- **Page count refused before extraction or rasterisation** (200), and extracted
  text capped per page and in total. Note what this does *not* do, since the
  first draft of this entry claimed it did: counting the pages **is** the page
  tree walk (`len(reader.pages)` → `get_num_pages` → `_flatten`), so the guard
  cannot fire until pypdf has visited every node. Measured: 60,000 pages fit in
  7.07 MiB — under the byte cap — and cost 4.63s and 295 MiB of peak RSS to
  count. The pool, the gate and the 8s clock contain that; the guard buys the
  extraction and the render, not the count.
- **`pdftoppm` gets rlimits from the kernel** — CPU, address space, and file
  size, the last being the only part of this path that writes to disk — plus a
  15s timeout and a kill. `-scale-to` replaces `-r 150`, so the raster is
  bounded by our configuration rather than by the page's declared size. Only
  RLIMIT_CPU and RLIMIT_FSIZE arrive as signals; **RLIMIT_AS does not kill
  anything**, it makes `mmap` return ENOMEM, and pdftoppm then exits 127 without
  loading libm. That path fails closed and the user still gets a message, but
  the comment used to say otherwise.
- **Two backpressure gates** (`saathi/core/backpressure.py`): four **image and
  document** messages in flight process-wide, and **one** document being parsed.
  The second document is refused, not queued — a queue in front of CPU-bound
  work is the same unbounded growth wearing a hat. The document gate covers the
  CPU half only and is released before the model call, which is a 10-45s network
  wait; holding a 1-of-1 slot across that would refuse everyone else's document
  to protect an idle core. Voice notes do **not** pass the media gate — audio
  concurrency is still unbounded, and audio is the primary modality.
- **Every refusal is a message**, bilingual and specific, saying what would work
  instead ("send me a photo of just the page that matters"). There is no longer
  any exit from the media path that drops the turn silently.

Proven by running it, not by reading it: real `pypdf` on a real 250-page PDF,
the real `pdftoppm` for the happy path *and* for the kill *and* for the
`RLIMIT_FSIZE` kill (SIGXFSZ, exit `-25`), the real `httpx` stack for the
streaming cap, and an HMAC-signed document webhook POSTed to the real FastAPI
route — which is a committed test, not a scratch script, because the claim
should stay true after the next change. Each guard was then **deleted from the
production path** and the test that covers it confirmed to go red — nine for
nine. `tests/test_media_limits.py`.

`_render_limits` is worth one line on its own: it runs between `fork()` and
`exec()` in a process that has threads, where an allocation can block on a
malloc lock the fork orphaned. It said "nothing here allocates" while computing
`mb * 1024 * 1024` and two tuple literals. The values are now built in the
parent and only indexed in the child. This is also why
`SAATHI_DOC_CONCURRENCY` is not a throughput knob — at 1, no pypdf thread is
running when we fork. `LANDMINES.md` has the long version.

### Still open

Per-user rate limiting. The gates bound how much runs *at once*; they do not
bound how often one sender may ask. Widened onto `PROD_READINESS.md` **PR-15**
— it belongs with admission control, covers audio and text as well as
documents, and needs state that survives a restart.

Every outbound media reply is stored in `messages` **twice** — `pipeline` inserts
it and `wa.client._send` records it again at the wire path, and the `on conflict
(wa_message_id)` that was supposed to absorb the duplicate never fires because
pipeline's row has a NULL id and NULL never conflicts. Pre-existing on the agent
path and now replicated onto the refusal paths. Not fixed here because the two
rows differ — pipeline's is redacted, the wire path's is not — so deleting the
duplicate silently drops redaction from outbound storage. Written up as PR-34.

---

## 2026-07-28 (deploy) — a failed migration used to restart the services anyway

**337 tests passing.** No Python changed; this is `ops/deploy.sh` and two new
files under `db/`.

### Broke

- **A migration could fail and the deploy would carry on and restart the
  services.** `remote.sh` runs with `set -uo pipefail` and no `-e`, and the loop
  was `psql ... >/dev/null 2>&1 && echo ok || echo FAILED`. The failure printed
  a word and changed nothing else. `saathi-web` and `saathi-worker` then came
  up against a schema they did not match.
- **You could not find out why it failed.** `2>&1` to `/dev/null` threw away
  psql's error. The deploy log said `FAILED` and nothing more.
- **Every deploy silently re-ran every migration**, and two of them are not
  idempotent — which is the part nobody had noticed. `003_admission_control`
  ends with `update user_channels set status='active' where status='pending'`
  and `005_onboarding` with
  `update users set onboarding='done' where onboarding='new' and created_at < now()`.
  Correct once, as backfills. Re-run, they **admit every pending unknown sender
  and mark every half-onboarded user as consented** — the admission gate and
  the consent step, both undone by deploying.

  Measured rather than reasoned about: a schema-only copy of the live database,
  one pending `user_channels` row, one `onboarding='new'` user, put through the
  old loop. Both came out `done / active`, with all six migrations reporting
  "ok". Everything looked healthy. It was not.

### Fixed

`ops/deploy.sh` now aborts before the restart. Any of — empty `SAATHI_DB_DSN`,
ledger unavailable, migration error, ledger write error, checksum mismatch —
prints `MIGRATION ABORT` and exits 1, and psql's stderr goes to the deploy log
instead of `/dev/null`.

New `db/schema_migrations.sql` creates the ledger
(`version, checksum, applied_at, origin, note`) and `db/record_migration.sql`
writes a row after each migration commits. Version is the filename; checksum is
the sha256 of the file as applied, so editing a migration after it ran aborts
the next deploy rather than being skipped in silence.

The six migrations already on the box are **baselined, not assumed**: each is
claimed only if a sentinel object that exists if and only if that file
committed is visible right now. Each migration is a single `begin/commit`, so a
visible sentinel means the whole file landed. Baselined rows are marked
`origin='baselined'` with a **NULL checksum** — nobody watched them run, so we
do not claim to know what ran.

Verified on scratch databases on the box, dropped afterwards; the live database
was only read (`pg_dump --schema-only`). Fresh bootstrap applies six and records
six; second run applies none; pre-ledger database baselines six and leaves the
canary rows at `new / pending`; partially migrated pre-ledger database baselines
002–004 and applies 005–007; edited migration aborts with both checksums shown;
injected failing migration prints the psql error, aborts, records nothing, and
never reaches `systemctl restart`. What could not be tested here is the deploy
end to end — it needs the dev box's AWS profile and SSM permissions. The
generated `remote.sh` was extracted and read instead, and `bash -n`'d.

Every psql call in the loop passes **`-X`**. `su - ubuntu` is a login shell, so
psql would otherwise read `~ubuntu/.psqlrc`, and the ledger read is parsed on
its field separator — one `\pset fieldsep ","` there makes every recorded
version stop matching, and migrations that were already applied get applied
again. Proven both ways against a planted `.psqlrc`: without `-X` the read comes
back `002_identity_and_channels.sql","8146f0…` and the loop starts re-applying
from 002; with `-X` all six still report "already applied". No such file exists
on the box today. `-X` is what keeps it from ever mattering.

Known window, written down in `PROD_READINESS.md` rather than smoothed over:
the ledger insert is a separate statement from the migration's own `commit`, so
a crash between the two leaves a migration applied but unrecorded.

---

## 2026-07-28 (later still, again) — the dead reminder path is gone

**337 tests passing.**

### Broke

- **Reading `worker/` told you a lie about how reminders fire.** Two modules
  sat there describing a queue that no longer exists: `send_reminder.py` and
  `reminder_scheduler.py`, both built around `reminder_fires`. Migration 006
  moved dispatch to `scheduled_turns`; neither module was deleted, and neither
  was imported by anything.
- **The cost was paid in reading, not in runtime.** A previous session read
  `reminder_scheduler.py`, believed it was the live scheduler, and had to
  prove by grep that it was never invoked. Dead code that reads like live code
  is a trap laid for the next person.

### Fixed

Deleted `saathi/worker/send_reminder.py` and
`saathi/worker/reminder_scheduler.py`. Nothing imported either — verified by
grepping the whole tree for `import`/`from` statements naming them, and by
checking `ops/`, the systemd units and `pyproject.toml`. The only surviving
mentions are historical ones in `CHANGELOG.md`, `docs/` and the docstring of
`tests/test_reminder_delivery.py`, which is the test that exists *because* of
this confusion and should keep naming it.

The live path is unchanged: `saathi/worker/__main__.py` imports `turns` for the
side effect of registering kinds, and polls `scheduling.run_once`. After the
deletion `scheduling.registered()` still returns
`['checkin', 'media_purge', 'nudge', 'reminder']`.

---

## 2026-07-28 (later still) — the language can be changed

**337 tests passing.**

### Broke

- **The language was asked once and could not be changed.** No command, nothing
  in the copy saying it was changeable. An elder who mistapped the first button
  was stuck in the wrong language — and mistapping is exactly what this user
  does.
- **Changing it would have un-onboarded them.** `ob:lang:*` routed into
  `_welcome`, which sets `onboarding = 'consent'`. Someone who wanted English
  would have been sent back through the consent flow.
- **Command replies were still bilingual.** Onboarding stopped repeating itself
  on 2026-07-28; `/stop`, `/resume`, `/clear`, `/whatyouknow` and the delete
  confirmation did not.

### Fixed

`/language` — plus `bhasha`, `bhasha badlo`, "change language", "switch to
english", "english mein baat karo" — re-offers the same two buttons, and is
registered with WhatsApp so it shows in the `/` menu. The done-state guard stops
it restarting onboarding. Command replies localised through `CMD_COPY`.

### The pattern held again

The obvious phrasing `\b(english|hindi) mein baat kar` would also match "mera
beta english mein baat karta hai" — a fact about someone's son, which would have
silently switched the language. Tightened to imperative and desire forms only,
and there are tests for the three statement forms. PR-23 was the same mistake in
STOP, and it cost a user's reminders.

---

## 2026-07-28 (later) — a fired reminder can come back

**331 tests passing.**

### Broke

- **Acknowledgement never worked.** Not rarely — never. §15's acknowledgement
  rate was structurally zero. Four independent breaks, none of which raised:
  the template carried no per-message payload so a tap returned only its label;
  the arriving `button` message type was never read; the pipeline routed it to
  the model as text; and `handle_ack` updated `reminder_fires`, the table
  migration 006 stopped writing.
- **Nothing enqueued a nudge.** The handler was registered, tested and dead, so
  an unacknowledged reminder was never followed up.
- **Snooze did not snooze.** It marked the row and booked nothing — the user was
  told "later" by a system that then forgot.

### Fixed

`send_template(payloads=[...])`, `button_id` reading both shapes, the pipeline
treating `button` like `interactive`, `handle_ack` on `scheduled_turns` with the
pending nudge cancelled, snooze re-enqueuing, and a nudge booked at +20 min
dedupe-keyed on the origin turn. Replies localised now that language exists.

### Note

`tests/test_pipeline_order.py` contained a test asserting the **old** behaviour —
`reminder_fires` and `acked`. It was holding the bug in place. That is the fourth
time today a passing test agreed with a bug instead of catching it.

---

## 2026-07-28 — ask the language first, then say it once

**326 tests passing.**

### Broke

- **Every onboarding message was sent twice** — Hindi, then English, in one
  bubble. The welcome was **615 characters**. PRD §2 finds the barrier for this
  user is interface complexity, not device access, and the first thing a
  70-year-old reads while deciding whether to trust this was twice as long as it
  needed to be. Reported from a real handset.
- **The Hindi restart phrase did nothing.** The declined message tells a Hindi
  reader to type *"shuru karein"* — which matched no command. It had been broken
  the whole time and was hidden by the bilingual copy: the same message also said
  *"just say start"*, so an English-capable reader could recover. Making the copy
  single-language turned a soft failure into a dead end, for exactly the users
  this product exists for.

### Fixed

- Onboarding now asks the language first — the **only** bilingual message — then
  speaks one language throughout. Welcome is **299 chars in Hindi (51% shorter)**
  and **221 in English (64%)**.
- Copy moved into per-language tables (`COPY`, `BTN`) with `t()` / `b()` helpers
  that fall back rather than raise, so a missing key degrades to Hindi instead of
  breaking onboarding for a real user.
- `commands.py` START now matches `shuru`, `shuru karein`, `shuru karo`,
  `shuru kariye`. **Anchored, not substring** — PR-23 showed what substring
  matching costs, and `"reminder shuru kar do"` correctly still does not match.
- `consent_log.lang` records the language the consent was actually read in,
  instead of a hardcoded `'hi-en'`.
- `CONSENT_VERSION` → `2026-07-27.v2`, because the consent text changed.

### Tests

`tests/test_onboarding.py` 9 → 13. New: the first message asks only the language;
an English welcome carries no Hindi tail; the choice is stored; and — the one that
would have caught the dead end — **the declined message's restart phrase must
actually parse to a command.**

### Note

The Hindi is Latin-script, as it has always been. Whether an elder reads
Devanagari more comfortably than Latin-script Hindi is a real question this does
not answer, and worth deciding separately.

---

## 2026-07-27 (night) — the commands become visible

No Python changed. Meta-side configuration on `1266402176549539`.

`commands.py` has always parsed eight slash commands. **No user could discover
any of them** — there was no menu, and nothing in the copy mentioned them. They
are now registered with Meta, so typing `/` shows them. The handlers were already
written and tested; this only makes them findable.

Four ice breakers added, in Hinglish, emoji-free (the API rejects emoji):

    Dawa ka reminder lagaayein
    Is photo mein kya likha hai, bataayein
    Mere baare mein kya jaante hain
    Bas thodi baat karni hai

### Checked before configuring, not after

Every ice breaker was run through `commands.parse` and the safety classifier. An
ice breaker that accidentally matched `\bunsubscribe\b` or a self-harm trigger
would be a bad way to greet a first-time user, and STOP already matches
substrings — see PR-23.

That test also changed one of them. "Mere baare mein aapko kya yaad hai" routes
to the **model**; "Mere baare mein kya jaante hain" matches the deterministic
WHAT_YOU_KNOW handler. Asking what a system stores about you is a transparency
feature and should return the actual list, not a generated approximation.

### To test

Ice breakers only appear on a **fresh** thread. Clear All Messages, delete the
chat, then start a new one — see `docs/vendor/meta/conversational-components.md`.

Also from that doc, and now a standing constraint: **a `wa.me` link carrying
pre-filled text dismisses the ice breaker UI.** Ours has no `?text=`. Do not add
one.

---

## 2026-07-27 (night, later) — the assistant is called Indofolk AI

Operator decision: **Indofolk AI** is the name, in chat as well as on the WhatsApp
header. Until now a user saw three: "Indofolk AI" as the sender, "Main Saathi
hoon" in the greeting, and "Saathi" 32 times across the policy pages.

### Changed

- `onboarding.py` WELCOME and `identity.py`'s admission-control message — the
  first words an unknown number and a new user respectively ever read.
- `agent/prompt.py` SYSTEM — how the assistant refers to itself in every
  generated reply.

The Hindi keeps **saathi** as the common noun it actually is — *companion*:

    Namaste! 🙏 Main *Indofolk AI* hoon — aapki saathi.

A literal substitution would have produced "Main Indofolk AI hoon" alone, which
is a company introducing itself in the first person. Using the word for its
meaning rather than as a name keeps the warmth §2 argues for.

**Needs a native-speaker check before real users.** I am confident about the
English and not about the gender agreement in "aapki saathi".

### Deliberately unchanged

- **`metrics.py: NAMESPACE = "Saathi"`.** The IAM grant is conditioned on that
  namespace and both CloudWatch alarms query it. Renaming it would have silently
  broken the alerting proved working hours earlier — the metrics would publish to
  a namespace nothing watches, and `treat_missing_data: breaching` would then
  fire an alarm about a healthy worker.
- Repo, database, box, GCP project, `SAATHI_PREFIX_TOKEN_BUDGET`, the FastAPI
  title and the Wikipedia User-Agent. Internal identifiers no user sees; renaming
  them buys nothing and breaks infrastructure.

Prefix budget re-checked — still inside `SAATHI_PREFIX_TOKEN_BUDGET`.

---

## 2026-07-27 (night) — every outbound message is now recorded

**322 tests passing.**

### Broke

- **The first real user received five messages and none were recorded.** After a
  complete onboarding — consent, name, reminders, improvement — `messages` held
  5 inbound and **0 outbound**. Onboarding calls the transport directly, and only
  `pipeline` and the reminder worker remembered to insert afterwards.

  The sharp edge is consent. `users.consent_at` and `consent_version` said the
  user agreed; nothing recorded *what they were shown*. The text lived only in a
  source constant at some past commit, and `CONSENT_VERSION` is hardcoded in two
  modules (PR-18), so the drift compounds. `messages` is the record the 6-hourly
  backup actually protects, and the first exchange every user ever has was
  outside it.

### Fixed

- `wa/client._send` — the documented "single wire path" — now records every
  outbound message. Deliberately not fixed in `onboarding.py`: patching the one
  caller that forgot leaves the next one free to forget too. `kind`, `body_text`
  and `template_name` are derived from the wire payload rather than passed in, so
  a new send helper cannot skip it either.
- Recording never raises. The send already happened; failing the caller would
  invite a resend of something the user has read. Failures log at ERROR.

### Tests

`tests/test_outbound_record.py` (8). Seven exercise the recorder directly — and
would all stay green if the call were deleted from `_send`. The eighth drives the
wire path with a stubbed transport and fails if it stops recording. Verified by
removing the call: exactly that one goes red.

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
