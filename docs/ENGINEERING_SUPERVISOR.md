# Engineering Supervisor — Saathi

Append-only lane log. **Evidence, not intentions.** A lane is not closed until
the contract docs are updated and evidence is recorded here.

---

## 2026-07-26 — Lane SAATHI-0: from PRD to a live webhook

Opened against `PRD-whatsapp-elder-agent.md` v0.1. Closed with the product
reachable on the public internet and 82 tests passing.

### Shipped

- **Infrastructure.** `i-01b2c27883acb25ca` (ap-south-1, t3.large, Ubuntu 26.04,
  encrypted EBS, IMDSv2 required), zero inbound rules, SSM-only access, no SSH
  key. Postgres 18.4, Python 3.14.4, ffmpeg 8.0.1, uv 0.11.32.
- **Schema.** 11 tables owned by the `saathi` role; extensions split from schema
  because `pg_trgm` is untrusted and applying it all as `postgres` would have
  left every table owned by the wrong role.
- **Agent.** Tool loop on `zai.glm-5`, 10 tools, prefix budget enforced in code.
- **Memory.** Facts + the ASR entity-bias vocabulary; hard erasure.
- **Speech.** ffmpeg both directions, Saaras `indic-en`, local correction pass.
- **Safety.** Deterministic pre-LLM classifier, Hindi + English + Hinglish.
- **Reminders.** RRULE, timezone-correct, Postgres `SKIP LOCKED` queue.
- **Channel.** WABA `1023945910495878` (`Saatih AI APP`), phone
  `1127963600410973` — CLOUD_API, VERIFIED, CONNECTED, displays as "Saathi AI".
- **Public.** `https://saathi.n8nworld.store` via Cloudflare tunnel; two systemd
  units plus cloudflared, all enabled.

### Evidence

- Queue claims exactly once: synthetic due fire → `claimed=1`, immediate
  re-claim → `second_claim=0`. Synthetic rows deleted.
- Live pipeline against real Postgres and real GLM-5 (send stubbed): reminder
  created at **08:15** from "sawa aath" with correct RRULE and queue row;
  replayed webhook → `skipped: duplicate`, no send; "seene mein dard" → safety
  fired, **agent never ran**, event logged.
- ffmpeg round trip in-process: OGG/Opus → WAV16k → OGG/Opus.
- Entity correction on live Saaras output: `bomlodipin` → `Amlodipine`.
- Webhook through Cloudflare: correct verify token → `200 CHALLENGE-OK`; wrong
  token → 403; correctly signed POST → `200`; tampered / wrong / absent
  signature → 403.
- Box Cloudflare token verified **from the box**: `active`, zones listable, R2
  listable.

### Measured, and it changed decisions

- **`zai.glm-5` 8/8** on Hinglish time + medicine extraction where the cheaper
  models scored 3–7/8. Regional ap-south-1 endpoint, so inference stays in India.
- **LLM cost ≈ ₹60/user/month**, not the PRD's ₹135 — measured at ~1,750 input
  tokens/turn, prefix ~1,330 of a 3,000 budget.
- **`codemix` returns Devanagari**, which makes entity correction structurally
  dead. `indic-en` is the correct mode. PRD §9 was wrong.
- **API-side keyword boosting is noise** — changed 1 of 3 transcripts, not for
  the better. The local correction pass is the mechanism.
- **Templates**: `session_resume`, `daily_checkin` APPROVED/UTILITY;
  `reminder_fire_v2`, `reminder_nudge_v2` submitted UTILITY after the first pair
  came back MARKETING at 7.5× the price.

### Bugs found by running it, not by reading it

1. **ffmpeg pipe WAV header** — `0xFFFFFFFF` length fields; Sarvam rejected 2.5 s
   of audio as ">30 seconds". Every voice note would have failed in production
   while `ffmpeg -version` looked healthy.
2. **Model published its chain of thought** as the user-facing reply, in English,
   then failed to call the tool. Prompt now forbids visible workings.
3. **Persona gender flipped** between turns (`rakhunga` → `rakhungi`). Pinned.
4. **Cloudflare BIC 1010** blocked every webhook while `/healthz` passed — and
   made the security probes *look* like they were passing. See `LANDMINES.md`.
5. **`saathi/db` package shadowed `saathi/db.py`**, breaking `/healthz`.

### Mistakes worth recording

- **Deleted two templates to fix their category.** Meta holds the name for up to
  four weeks; both names are burned and the live ones are `_v2`. Never delete a
  template to fix it.
- **Printed a page access token** by `select *`-ing a Graph response, and later
  **printed live HubSpot / Retell / Shopify credentials** by `select *`-ing
  `core.brand_integrations`, where secrets live inside a JSON blob rather than a
  column named like one. Those credentials need rotation. Project columns; never
  `select *` on anything that might carry a credential.
- **Claimed Business Agent needed allowlisting** after probing the wrong host. It
  is `api.facebook.com`, not `graph.facebook.com`, and we are eligible.
- **Called "no WABA exists"** from an inconclusive probe. There were five, under
  a verified business, including one already named for this product.

### Queued

- `WA_APP_SECRET` landed; **register the callback URL with Meta** so real
  messages arrive.
- Managed Postgres before external users — no backups today.
- TTS, onboarding + consent, real eval corpus of elder voice notes.
- Rotate the credentials exposed above.

---

## 2026-07-26 — Lane SAATHI-1: channel live end to end

### Closed

- **Public site.** `https://n8nworld.store` — landing plus `/privacy/`,
  `/terms/`, `/data-deletion/`, the three URLs Meta app review checks. Next.js
  static export on Cloudflare Pages (`saathi-site`), source on the **`site`
  branch** so application pushes never trigger a site build. Deployed by direct
  upload.
- **Operating entity named**: Indofolk Wellness Private Limited, Greater Kailash
  I, New Delhi, GSTIN `07AAHCI7432A1ZV` — matching the business verified in Meta
  BM. An earlier draft named a different entity (a proprietorship); its GSTIN was
  dropped rather than carried over, since reusing another legal person's tax ID
  would have been false.
- **Domain verified with Meta** — TXT added at the apex without disturbing the
  existing SPF or google-site-verification records.
- **Webhook registered.** App `1571039744742551` subscribed to
  `whatsapp_business_account` → `https://saathi.n8nworld.store/webhook/whatsapp`,
  fields `messages, message_template_status_update, account_update`, active.
  WABA `1023945910495878` subscribed to the app.
- **All four templates APPROVED as UTILITY** — including `reminder_fire_v2` and
  `reminder_nudge_v2`, which had first come back MARKETING at 7.5× the price.
  The rewrite (anchoring the body to the user's own prior action) held through
  review. This settles the ~₹20 vs ~₹90/user/month question in our favour.

### Evidence

- `GET /{app}/subscriptions` → object `whatsapp_business_account`, our callback,
  `active: true`.
- Meta called our verify endpoint synchronously during registration and it
  passed — which exercises the tunnel, the Browser-Integrity-Check rule and the
  verify token in one shot.
- Signed webhook POST → 200; tampered, wrong and absent signature → 403.

### 🚩 Open risk found while verifying

`GET /{waba}/subscribed_apps` returns **two** apps:

    MeshPilot        1571039744742551   (ours)
    Business Agent   1143680903703001   (Meta's)

Meta's Business Agent app is subscribed to our WABA's webhooks. Its
`rollout.enabled` is `false`, so it should not be responding — but a subscribed
app plus one toggle is all that stands between us and Meta's model becoming the
primary responder, which would bypass the deterministic §12 safety classifier
(R7). Recommend unsubscribing it. Not done unilaterally: it was not created by
this lane. See `LANDMINES.md`.

### Queued

- Unsubscribe the Business Agent app from the WABA (operator decision).
- Replace the landing page's template waitlist copy with real product copy.
- Managed Postgres before external users — still no backups.
- TTS, onboarding + consent flow, real eval corpus.

---

## 2026-07-27 — Lane OPS-1: forge CLIs on the runtime box

Operator instruction: authenticate `gh` and `glab` on the runtime box by device
approval flow.

### Closed

- **`gh` 2.46.0 and `glab` 1.53.0 installed** from Ubuntu `resolute/universe`
  rather than the vendors' apt repos, so no third-party signing key was added to
  the box.
- **GitHub — true OAuth device flow.** Authenticated as `floating-astronaut`,
  scopes `gist, read:org, repo, workflow`.
- **GitLab — no device flow exists in this build.** `glab auth login` offers
  `Token` or `Web`, and `Web` is an OAuth authorization-code + PKCE flow with a
  `http://localhost:7171/auth/redirect` callback. Completed on operator
  instruction by delivering the authorization code to the waiting process over
  the box's own loopback. Stored as an OAuth grant (`is_oauth2: true`) with a
  refresh token, not a PAT.

### Evidence

- `git ls-remote` over HTTPS to **both** remotes returned the same SHA for
  `main` (`c497c5ab`) — git transport works through both credential helpers, and
  the two forges are in sync under the existing manual dual-push discipline.
- GitHub repo permissions `admin/maintain/push/pull/triage`; GitLab group access
  level 50 (Owner).
- Both credential stores are `0600`; the transient `*:7171` listener closed when
  the flow completed.

### Mistakes worth recording

- **Drove the device flow through `script(1)` first and it hung silently with a
  zero-byte log.** `gh`'s prompt library emits a cursor-position query (`ESC[6n`)
  and blocks until the terminal answers; a pipe never does. It looked like a
  network stall. `tmux` emulates the response and the flow ran. Recorded in
  `LANDMINES.md`.
- **Reported the repo's commits as unsigned** on the strength of `%G?` returning
  `N`. They are signed — `git cat-file commit HEAD` shows a `gpgsig` block. `N`
  meant git could not *verify* the SSH signature because
  `gpg.ssh.allowedSignersFile` is unset on these boxes. Configuring it is worth
  a lane; until then `%G?` is not a usable check here.

### 🚩 Open risk created by this lane

The runtime box — the internet-facing one — can now push to `main` on both
remotes, and has no signing key, so anything it pushed would violate
`CONTRIBUTING.md:44`. Tracked as **CRED-1** on the board and PR-22 in
`PROD_READINESS.md`.

---

## 2026-07-27 — Lane SETUP-1: adopt the vibe-coding-kit control plane

Operator instruction: adopt `github.com/floating-astronaut/vibe-coding-kit` and
work its protocol, after the previous session did not hold doc discipline.

### Read

`vibe-coding-kit`: `THE-METHOD.md`, `AGENT-SYNC-PROTOCOL.md`, `LANE-LIFECYCLE.md`,
`ROLES.md`, `DOC-SYSTEM.md`, `agent-configs/claude-code/CLAUDE.md`, both
control-plane templates, `INSTALL-PROMPT.md`, `bin/vibe-scaffold`. Saathi:
`DOC_SYSTEM.md`, `PRD.md` §0, `DECISIONS.md`, `LANDMINES.md`,
`PROD_READINESS.md`, the tail of this log, `CONTRIBUTING.md`.

### Closed

- **Merged, not scaffolded.** `bin/vibe-scaffold .` would have written
  `docs/DOC-SYSTEM.md` and `control-plane/ENGINEERING_SUPERVISOR.md` alongside
  the existing `docs/DOC_SYSTEM.md` and `docs/ENGINEERING_SUPERVISOR.md` —
  hyphen vs underscore, different directory — leaving **two doc-system maps and
  two supervisor logs**. Installing the anti-drift kit that way would itself
  have been a drift event, and would have broken the kit's own "amend, don't
  fork" rule.
- **Method docs added** as `docs/THE_METHOD.md`, `docs/AGENT_SYNC_PROTOCOL.md`,
  `docs/ROLES.md`, `docs/LANE_LIFECYCLE.md` — renamed to Saathi's `UPPER_SNAKE`
  convention, with every cross-reference rewritten to Saathi's real paths.
- **Control plane added**: `control-plane/ACTIVE_LANE_BOARD.md` (the live queue)
  and `control-plane/SESSION_COORDINATION.md`.
- **Agent configs committed to the repo**: `CLAUDE.md`, `AGENTS.md`, `KIMI.md`.
  Saathi's rules previously lived only in `~/.claude/CLAUDE.md` — per-box,
  user-global, and read by Claude Code alone. Codex and Kimi never saw the
  contract. That is the structural reason three agents held three different
  ideas of the rules.
- **`DOC_SYSTEM.md` amended**: the control plane is registered, inserted into the
  precedence ladder above historical evidence, and added to the mandatory
  write-back list.

### The queue moved off the append-only log

Seven open items were migrated from scattered `### Queued` blocks in this log
onto the board: `DOC-1`, `CRED-1`, `SEC-1`, `PR-3`, `PR-4`, `PR-8`, `PR-9`.

`AGENT_SYNC_PROTOCOL.md` §6 names this anti-pattern directly. The proof it was
biting: **"unsubscribe the Business Agent app" appears in two separate `Queued`
blocks and is still open.** An append-only log cannot represent a queue, because
nothing in it is ever struck off.

### Remains

- Nothing in this lane. `DOC-1` is the natural next lane and is the oldest
  unwritten-back change on the board.
- **Not rewritten, deliberately:** SAATHI-0 above records "zero inbound rules,
  SSM-only access, no SSH key". That was true when written. This log is
  historical evidence and does not get corrected — `DOC-1` fixes the
  *current-state* docs (`README.md`, `ARCHITECTURE.md`, `RUNBOOK.md`) instead.

### Addendum — how this lane landed

Pushed **from the runtime box, unsigned**, on operator instruction (decision
D-L). The signing rule was blocking runtime-box work from ever landing, which is
itself how the SSH change went live with three docs still claiming no inbound
port was open. `CONTRIBUTING.md` amended in the same commit so the docs and the
practice agree.

---

## 2026-07-27 — Lane PR-4: reminders were never dispatched

### Read

`docs/PROD_READINESS.md` (PR-4), `docs/ARCHITECTURE.md`, `saathi/scheduling.py`,
`saathi/worker/{__main__,turns,reminder_scheduler,send_reminder}.py`,
`saathi/agent/tools/handlers.py`, `saathi/pipeline.py`, `saathi/wa/client.py`,
`db/migrations/006_scheduled_turns.sql`, `tests/test_scheduling.py`.

### What the lane actually found

PR-4 said reminders had no *delivery guarantee*. They had no *delivery*.

`_create_reminder` inserted into `reminder_fires`. The worker claims only from
`scheduled_turns`. `worker/reminder_scheduler.py` — the sole reader of
`reminder_fires` — is referenced **nowhere in the repo**. Migration 006 moved
the queue and back-filled existing rows once, at migration time; the creation
path was never moved with it. Every reminder created since would have been
written to a table nothing reads.

Latent, not live: both tables were empty, so nothing was actually dropped. The
product's worst failure was one real user away and completely silent — no
exception, no failed row, no log line.

### Closed

- Creation enqueues onto `scheduled_turns`; the write to `reminder_fires` is gone.
- Recurring reminders book their next occurrence (dedupe-keyed), which nothing
  did before — a daily reminder would have fired at most once.
- A deliberate no-send (paused, or no active handle) is marked `skipped`, so the
  sweep can distinguish it from a send that died.
- `scheduling.sweep_stuck` reclaims turns claimed-but-unsent, guarded on
  `wa_message_id is null` so a delivered reminder is never resent. `run_once`
  sweeps before it claims.

### Evidence

- **301 tests passing** (294 before; 7 new in `tests/test_reminder_delivery.py`).
- **End to end against the live database**, not fakes: a reminder created through
  the real `Handlers._create_reminder` appeared on `scheduled_turns` as
  `('reminder', 'pending', 'reminder:18:2026-07-27T02:30:00+00:00')` — 08:00 IST
  correctly stored as UTC — with `reminder_fires` at 0 rows. Synthetic user,
  reminder and turn deleted afterwards; re-queried at `(0, 0, 0)`.
- Both new statements executed against real Postgres before being trusted.

### Mistakes worth recording

- **Shipped `sweep_stuck` with SQL Postgres rejects, while its tests were green.**
  `set state = case ... end` yields `text`; the column is the `turn_state` enum.
  The fake connection does not parse SQL, so it certified it. Caught only by
  running the statement against the database. The path only executes *after a
  worker has already crashed*, so this would have failed at the worst moment.
  Recorded in `LANDMINES.md`.
- **Broke two existing tests** by adding the sweep: their fake matched any
  `returning id` and fed the four-column sweep a one-column row. Fixed the fake
  rather than reshaping production SQL around it.

### 🚩 Found while working, cut as its own lane

**PR-4b — the ack path is unreachable**, three independent silent breaks:
`wa.send_template` sends no button component, so the `ack:`/`snooze:` payloads
`pipeline.handle_ack` parses are never produced by anything; `handle_ack`
updates `reminder_fires`, which no longer receives fires; and nothing anywhere
calls `enqueue(..., "nudge", ...)`, so the registered nudge handler is dead.
§15's acknowledgement-rate metric is therefore structurally zero, not low.

### Remains

- PR-4 stays **P0** in `PROD_READINESS.md`: the sweep records a stranded turn,
  but nothing tells a human. That is PR-3, blocked on `cloudwatch:PutMetricAlarm`
  and SNS (PR-22).
- PR-4b, above.

---

## 2026-07-27 — Lane DOC-1: the docs said no inbound port was open

### Read

`README.md`, `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`, `docs/PROD_READINESS.md`,
and the SAATHI-0 entry above.

### Closed

`sg-0f805961424175e66` (`saathi-dev`) has **exactly one** ingress rule: TCP 22
from `207.219.25.137/32`, described *"operator Mac SSH dev only"*. It is the
only security group on the instance. `sshd` accepts one ED25519 key
(`tejas-mac-saathi-ai`) with `passwordauthentication no`.

**Six** claims were wrong, not the three first counted:

- `README.md` — "No inbound port is open"
- `docs/ARCHITECTURE.md` — "No inbound port is open"
- `docs/RUNBOOK.md` — security group "**zero inbound rules**"
- `docs/RUNBOOK.md` — Access: "**SSM only.** No SSH key exists; port 22 was
  never opened." Found only while editing the line above it.

- `docs/BUILD_PLAN.md` — the build table's security-group and access rows
- `docs/BUILD_PLAN.md` — "**No inbound port is open.** The security group still
  has zero ingress rules" — both found by grepping rather than by the original
  count, which is the argument for grepping

The four current-state claims now describe the real ingress, and `RUNBOOK.md`
gains a note that the SSH rule and the Cloudflare token are each pinned to an IP
that breaks silently when it changes.

`BUILD_PLAN.md` was **annotated, not rewritten**. It is a running log of what
shipped, and that section is independently stale already — it records the
*ephemeral* public IP, long since replaced by the EIP. Rewriting it would erase
when the change happened. It gets dated "Superseded 2026-07-27" notes pointing
at `RUNBOOK.md` and PR-24, which is the same convention `PRD.md` §0 already uses
for its own measured-wrong claims. Recorded as **PR-24** in `PROD_READINESS.md`, with the
production fix being SSM Session Manager and dropping the rule.

### Evidence

- `aws ec2 describe-security-groups` → one `IpPermissions` entry, `tcp 22-22`,
  `207.219.25.137/32`.
- `describe-instances` → `sg-0f805961424175e66` is the only group attached.
- Corroborated a day earlier, before the IAM grant existed, by the operator's
  `ssh` returning `Permission denied (publickey)` — an *authentication* failure,
  which proves TCP and the banner exchange already succeeded.

### Not rewritten, deliberately

The SAATHI-0 entry above still reads "zero inbound rules, SSM-only access, no
SSH key". That was **true when written**. This log is historical evidence and
does not get corrected; the current-state docs are what drift. Correcting the
log would destroy the only record of when the change actually happened.

### Note on ids

`PROD_READINESS.md` gains PR-24 and skips PR-23, which is held for lane SEC-2
(Codex, running concurrently). A gap in a journal is cheaper than two sessions
claiming one id.

---

## 2026-07-27 — Lane SEC-2: security policy and scan

### Read

`docs/DOC_SYSTEM.md`, `docs/AGENT_SYNC_PROTOCOL.md`,
`control-plane/ACTIVE_LANE_BOARD.md`, `control-plane/SESSION_COORDINATION.md`,
`docs/ARCHITECTURE.md`, `docs/PROD_READINESS.md`, `docs/LANDMINES.md`,
`docs/DECISIONS.md`, the tail of this log, and the changed security-sensitive
files called out by the board: `saathi/scheduling.py`,
`saathi/worker/turns.py`, and `saathi/agent/tools/handlers.py`.

### Changed

- Added root `SECURITY.md`, owned by Codex under SEC-2.
- Registered `SECURITY.md` in `docs/DOC_SYSTEM.md` doc map only.
- Added `PROD_READINESS.md` rows **PR-23**, **PR-25** and **PR-26** for
  unresolved reportable findings.

### Evidence

- Scan checkout `/home/ubuntu/saathi-scan` was clean at `c4b34ba`, after both
  remotes reported `main = c4b34ba`; this is after the required base `64a520b`.
- `SESSION_COORDINATION.md` shows Codex active only on SEC-2 and owning
  `SECURITY.md`.
- `saathi/capabilities.py` routes deterministic commands at priority 22 before
  the agent at priority 90.
- `saathi/provenance.py` withholds mutating tools from relayed content only when
  building the agent allowed tool set.
- `saathi/commands.py` matches natural-language and slash commands without
  provenance input.

### Closure

Final scan report written to
`/tmp/codex-security-scans/saathi-scan/c4b34bab020707c3e4b47103820c43d4225e023a_20260727T012351Z/report.md`.

Closure evidence:

- `SECURITY.md` exists at the repo root and is registered in `DOC_SYSTEM.md`.
- Generated repository worklist contained 67 source-like rows; `work_ledger.jsonl`
  has 67 completion receipts.
- Reportable findings are tracked in `PROD_READINESS.md`: PR-23, PR-25, PR-26.
- `SEC2-REM-003` was suppressed as duplicate of PR-4b; SEC-1, CRED-1/PR-22 and
  DOC-1 were excluded as already-tracked lanes.
- No source-code fixes were made in SEC-2.

---

## 2026-07-27 — Lane PR-3: something finally tells a human

### Read

`docs/PROD_READINESS.md` (PR-3), `docs/RUNBOOK.md`, the live systemd units, and
`docs/LANDMINES.md` before touching anything that emails out.

### Closed

- `saathi/metrics.py` — CloudWatch publisher that never raises.
- Worker publishes `WorkerHeartbeat` and `TurnsDispatched` **after** a
  successful tick, so the signal means "did its job", not "process exists".
- `ops/alerting/` — `OnFailure` publisher, a non-Python metric shim, the systemd
  template, and an idempotent installer.
- Two alarms → SNS `saathi-alerts`, both treating missing data as **breaching**.

### Evidence — induced, not inspected

- Worker stopped **01:44:05Z** → alarm ALARM **02:04:59Z**, reason *"no
  datapoints were received for 2 periods and 2 missing datapoints were treated
  as [Breaching]"* → SNS `NumberOfNotificationsDelivered` **8→9**,
  `NumberOfNotificationsFailed` **0**, to the confirmed subscriber. Worker
  restored 02:06:02Z.
- `saathi-backup-stale` separately observed ALARM→OK as `BackupSuccess` arrived
  — both directions of the missing-data path exercised.
- Real backup run: dump → verify-by-restore → dropdb, exit 0, `ExecStartPost`
  fired 01:47:19→01:47:20 and published `BackupSuccess`.
- 305 tests passing.

### Measured facts that contradicted the design

- **Detection takes ~21 minutes, not 10.** `Period × EvaluationPeriods` is
  arithmetic, not latency: CloudWatch will not call a period definitively empty
  until its ingestion window settles, costing roughly an extra cycle. I
  predicted ~10 min and said so out loud; the number is 21. `RUNBOOK.md` now
  carries the measured figure and a warning to re-measure after any tuning.
- **`OnFailure=` barely applies to `saathi-worker`.** It is `Restart=always`
  with `StartLimitBurst=5`, so a crashing worker re-enters `active`, not
  `failed`. A crash-loop looks alive; only the heartbeat catches it.
- **`%n` already contains `.service`**, so `saathi-alert@%n.service` instantiates
  `saathi-alert@saathi-worker.service.service`. `%N` is the form you want.
- **A topic with no confirmed subscriber accepts publishes happily** — the
  counter rises, every call returns a MessageId, nobody is told anything. Only
  `NumberOfNotificationsDelivered` distinguishes the two.

### Deliberate choices

- Alerts carry **no log content**. `journalctl` is redacted only inside the
  Python entrypoints; the backup script is not. An alert is a summons, and this
  project has printed a live token once already.
- Missing data is **breaching**, so a metrics outage pages someone about a
  healthy service. That false alarm is the price of never mistaking broken
  monitoring for silence.

### Remains

- Latency of ~21 min is a product decision, not a bug. Tune `Period` and
  re-measure if it is too slow for a medication reminder.
- `cloudwatch:DescribeAlarmHistory` is denied to the box, so transitions can be
  watched live but not audited afterwards. Small read-only IAM ask.
- I left `/saathi/authz-probe` behind earlier in the day when `DeleteLogGroup`
  was denied; the grant has since landed and the group is gone.

---

## 2026-07-27 — Lane PR-23: a forwarded advert stopped someone's reminders

Picked up from Codex's SEC-2 finding.

### Read

`saathi/provenance.py`, `saathi/capabilities.py`, `saathi/commands.py`,
`saathi/core/context.py`, `saathi/pipeline.py` (`_run_command`),
`saathi/worker/turns.py`, `docs/ARCHITECTURE.md`.

### What the lane found beyond the report

SEC-2 reported that a forwarded `stop` or `clear chat` could pause a user. The
realistic case is worse. `STOP` matches `\bunsubscribe\b` as a **substring**,
and nearly every forwarded marketing message on Indian WhatsApp carries that
word in its footer. The full chain:

    forwarded text containing "unsubscribe"
      -> commands capability (priority 22) matches, no provenance check
      -> _run_command STOP -> update users set paused = true
      -> worker/turns._handle sees paused, returns None
      -> reminder never sent, silently, indefinitely

No attacker is required — a relative forwarding a promo is enough. And because
the ack path is unreachable (PR-4b), there is no acknowledgement gap and no
nudge to reveal it. This is the product's worst failure reached by its most
ordinary event.

### Closed

The priority-22 matcher now requires `c.trusted`. The check is in the **matcher**
rather than the handler on purpose: an unmatched capability falls through to the
agent, which already fences relayed text and withholds mutating tools, so the
fix reuses behaviour we already trust instead of inventing a second refusal path.
Relayed text is still read and explained — just never obeyed.

Deliberately unchanged:

- **20/21 (buttons)** key on `button_id`. Provenance describes text; a tap is a
  first-party control the user physically pressed.
- **10 (onboarding)** matches `not c.is_onboarded`. Guarding it would drop an
  un-onboarded user through to the agent, breaking "onboarding never calls the
  model" — the property that makes an open door safe. Gating it would have been
  the intuitive move and the wrong one.

### Evidence

- 314 tests passing (305 before; 9 new in `tests/test_relayed_commands.py`).
- **The new tests were verified to fail without the fix** — reverting the guard
  turns 4 of the 9 red. A regression test that passes either way proves nothing.
- Coverage includes the realistic advert-with-footer case, bare `stop`,
  `delete everything`, Hinglish `band kar`, plus the things that must keep
  working: the user's own typed and spoken commands, relayed text still reaching
  the agent, buttons still trusted on a relayed turn.

### Remains

- `commands.parse` is substring-based for most patterns. Narrowing it is a
  separate question from provenance and was left alone — the guard closes the
  security hole regardless of how loose the patterns are.
- PR-27 recorded: the box gained `secretsmanager:PutSecretValue` today for the
  CallerDesk keys. Reading secrets is a confidentiality exposure; rewriting them
  is an integrity one. Should drop back to read-only once CallerDesk is wired.
- CallerDesk keys are stored and synced but **inert** — nothing references
  `CALLERDESK_*`. Wiring them needs a `DECISIONS.md` entry first, since PRD §4
  puts voice calls out of scope for v1.

---

## 2026-07-27 — Deploy of `117896b` to the runtime box

### What was live before

The box was running the 2026-07-26 23:17 artifact. **PR-23 and PR-4 were both
absent**, so a forwarded advert containing "unsubscribe" could still pause a
user's reminders, and any reminder created still went to a table nothing reads.
Only PR-3's heartbeat was present, because it had been hand-copied earlier.

### How it was deployed, and why not with `ops/deploy.sh`

`ops/deploy.sh` cannot run here. It exports `AWS_PROFILE=mp-dev` and drives the
box over `ssm send-command`; on the runtime box there is no such profile and
`ssm:SendCommand` is denied to the instance role. Recorded as **PR-28**.

Done instead: rollback tarball written, the four changed modules plus the new
tests and `ops/alerting/` copied in (overlay, never mirror-delete — `evals/`
exists only on the box), `uv sync`, `pytest`, `systemctl restart`, then the same
verification block `deploy.sh` itself runs. No migrations changed in this deploy.

### Evidence

- 314 tests passing **on the box, against the live tree**.
- units all active; 0 tracebacks or criticals since restart.
- healthz 200 locally and through the tunnel; unsigned webhook POST 403; site 200.
- worker kinds `['checkin', 'media_purge', 'nudge', 'reminder']`.
- Behaviour checked against the **running** code, not the file: a forwarded
  advert no longer matches the command capability, while a typed `stop` still
  does.

### Found while deploying

- **PR-25 is worse than reported.** `remote.sh` runs without `set -e`, discards
  migration stderr, and restarts services regardless of migration outcome. There
  is no `schema_migrations` table either, so every migration re-runs on every
  deploy and correctness rests entirely on idempotency.
- `handlers.py` still has two dead `update reminder_fires` statements in the
  cancel path. **Not a live bug** — `turns.reminder` re-checks
  `reminders.status = 'active'` at dispatch, so a cancelled reminder is skipped
  correctly — but it is residue of the same split-brain that caused PR-4 and
  should be cleaned up with PR-4b.

---

## 2026-07-27 — Lane WA-1: an Indian number, and a name

### The problem, restated after measuring it

The operator reported the number showing as "Invite to WhatsApp". The number was
fine — `CONNECTED`, `VERIFIED`, quality GREEN. Three other things were not:

- **no click-to-chat link anywhere.** The `site` branch has no `wa.me` and does
  not even print the number; `data-deletion` says "Send Saathi a message on
  WhatsApp" without saying how. The only route in was saving a **+1 Canadian**
  number by hand — which, typed into an Indian phone without the country code,
  resolves to nothing. That is the reported symptom.
- **`name_status: DECLINED`** — the thread showed a raw foreign number.
- profile empty, `vertical: ENTERTAIN`.

### What the display-name rejection actually was

Not the word, and not a generic-Hindi-term rule. `ayurpetofficial` is only a
portfolio label; its verified legal entity is **INDOFOLK WELLNESS PRIVATE
LIMITED** — the same company our privacy pages name, same GSTIN. But its
**registered website** is `indofolkwellness.com`, *"Premium B2B Pet Products"*,
with `saathi` appearing **zero** times. Review asks whether the name relates to
the verified business; nothing on record connected "Saathi" to a pet exporter.

**"Indofolk AI" was approved first time**, because it matches the legal name.

### Closed

- Indian DID bought from Vobiz — **+91 8071 581 944**, ₹100 + ₹500/mo.
- Verified by **voice OTP**, because every Indian DID in their inventory is
  `sms: false`. Routed through a temporary Cloudflare Worker returning Dial XML
  to the operator's mobile, then torn down.
- Registered on **our own** Cloud API (`request_code` → `verify_code` →
  `register`), two-step PIN generated on-box and stored value-blind.
- WABA `1687148075730227`, **currency INR** — §14's cost model finally applies.
- Vobiz unsubscribed from the WABA's webhooks; our app subscribed.
- Four templates re-submitted on the new WABA, same names, all `UTILITY`.
- `.env` switched **via Secrets Manager**, services restarted.

### Evidence

- Live inbound at 04:41:50 → `POST /webhook/whatsapp` **200** → user row created,
  `onboarding = consent` → bilingual onboarding rendered on the handset with all
  three quick-replies, header reading **"Indofolk AI"**.
- Send permission proven without sending: a deliberately nonexistent template
  returned **132001 "Template name does not exist"** — past auth, past
  permission. No new token needed.
- 0 tracebacks since restart; worker heartbeat uninterrupted across the switch.

### Mistakes and traps

- **Deleting the Cloudflare Worker did not stop the forward.** The edge kept
  serving the cached XML, so the business number kept ringing a personal mobile
  after the script was gone. Detaching the number at Vobiz is what stopped it.
  `LANDMINES.md`.
- **Vobiz's "Test URL" failure was CORS**, not the XML. Their message says
  "unreachable or returned invalid XML" and it was neither — the payload was
  correct throughout, verified independently with `curl` before touching it.
- **I twice mis-parsed their API** (`items` key), reporting 0 owned numbers when
  there was 1, and 19 secret keys when there were 18.
- **I asserted `ayurpetofficial` was a different, borrowed company** and repeated
  it across several turns. It is the same legal entity. The docs' "borrowed"
  framing is true of the *app and token*, not the business.

### Remains

- **PR-30** — templates are `PENDING`. Until approved, every reminder, nudge and
  check-in fails. Acceptable only because no reminders exist.
- **PR-31** — onboarding records no outbound message, so the consent text is
  outside the product record.
- **WA-2** — a Saathi page on `indofolkwellness.com`, then re-submit "Saathi",
  plus the `wa.me` link that was the original complaint.

---

## 2026-07-27 — PR-31: the consent text nobody kept

### Found

The first real conversation on the new number completed onboarding: consent,
name, reminders, improvement — four button presses, `onboarding = done`,
`consent_at` set. `messages` held **5 inbound, 0 outbound**.

Every reply the user saw was gone. Including the consent text.

`users` proves *that* they agreed and to which version. Nothing proved *what they
read*. Under DPDP that is the wrong half to keep, and `messages` is precisely the
table the 6-hourly verified backup protects.

### Closed

Recorded at `wa/client._send`, the module's own documented "single wire path",
not in `onboarding.py`. Fixing the caller that forgot would leave the next caller
free to forget: `pipeline` and the reminder worker each remembered separately,
which is exactly the pattern that produced the hole. `kind`, `body_text` and
`template_name` are derived from the payload rather than passed in, so a new send
helper cannot opt out either.

Recording never raises — the send has already happened, and failing the caller
would invite a resend of something the user has read. Failures log at ERROR.

### Evidence

- 322 tests (314 before, 8 new).
- The insert was run against **real Postgres** inside a transaction and rolled
  back — fakes accept SQL that Postgres rejects, which this project has already
  paid for once with `sweep_stuck`.
- **The regression test was verified to fail.** Seven of the eight exercise
  `_record_outbound` directly and stay green if the call is deleted from `_send`;
  the eighth drives the wire path and goes red. I nearly shipped only the seven.

### Remains

- `worker/send_reminder.py` and `worker/reminder_scheduler.py` are both confirmed
  dead — nothing imports either — and both still contain writes to
  `reminder_fires`. Harmless, misleading, worth deleting with PR-4b.
- PR-18 still stands: `CONSENT_VERSION` hardcoded in two modules, with nothing
  forcing a re-consent when the text changes. Now that the text is recorded per
  message, a mismatch is at least detectable after the fact.

---

## 2026-07-28 — Lane PR-4b: the reminder loop closes

### Four breaks, each silent

1. **The template carried no per-message payload.** `reminder_fire_v2` is
   approved *with* quick-replies ("Ho gaya", "15 min baad"), but a template
   quick-reply returns only its **label** unless a `button` component supplies a
   payload per message. Nothing tied a tap to the turn that produced it.
2. **The arriving message type was never read.** Interactive messages we compose
   carry the payload at `interactive.button_reply.id`. A template quick-reply is
   a different type — `button`, with `button.payload` — and `MessageContext`
   only knew the first shape.
3. **The pipeline routed it as text.** `kind == "interactive"` gated both the
   text resolution and the logging, so a `button` message fell through to the
   model as plain text.
4. **`handle_ack` updated `reminder_fires`** — the table migration 006 stopped
   writing. And nothing anywhere enqueued a nudge, so the registered handler was
   dead code.

Consequence: §15's acknowledgement rate was **structurally zero**, not low, and
a missed dose produced no follow-up.

### Closed

- `send_template(..., payloads=[...])` emits `button` components with
  `sub_type: quick_reply` and a per-message payload, in template button order.
  Templates without payloads grow no buttons — a check-in must not sprout
  controls it was not approved with.
- `MessageContext.button_id` reads both shapes.
- The pipeline treats `button` like `interactive` for text resolution and
  logging (`msg_kind` has no `button` member, so both record as interactive).
- `handle_ack` updates `scheduled_turns`, cancels any pending nudge for that
  turn, and **snooze re-enqueues** — marking a row snoozed is not a reminder,
  and without the re-enqueue the user was told "later" by a system that then
  forgot.
- Firing a reminder books a nudge at +20 min, dedupe-keyed on the origin turn.
- Ack and snooze replies are localised, now that language exists.

### Evidence

- 331 tests (326 before; 5 new in `tests/test_ack_loop.py`).
- All three new statements run against **real Postgres** and rolled back —
  including the `payload->>'origin_turn_id'` comparison. `scheduled_turns_user`
  is `(user_id, kind)`, so the nudge-cancel lookup is already indexed; no
  migration.
- `tests/test_pipeline_order.py` had a test asserting the **old** behaviour
  (`reminder_fires` + `acked`). It was pinning the bug in place. Updated, and it
  now also asserts `reminder_fires` is never touched.

### Worth noting

A passing test asserted the broken behaviour. That is the fourth instance today
of tests agreeing with a bug rather than catching it — after `sweep_stuck`'s
invalid SQL, the reminder path writing to a dead table, and outbound messages
never being recorded. The pattern is not bad luck; it is that these tests were
written from the implementation rather than from the contract.

### Remains

- `worker/send_reminder.py` and `worker/reminder_scheduler.py` are still dead and
  still contain writes to `reminder_fires`. Deleting them is a tidy-up lane.
- Untested against a real handset: no reminder has fired on the live number yet.

---

## 2026-07-28 — PR-32: the language can be changed

### Closed

`/language` re-offers the two buttons onboarding used, matched from `/language`,
`/bhasha`, a bare "language" or "bhasha", "change language", "bhasha badlo",
"switch to english|hindi", and "(english|hindi) mein baat karo". Registered with
WhatsApp, so it appears in the `/` menu alongside the other eight.

### Two things found while fixing it

**Changing language would have un-onboarded the user.** `ob:lang:*` fell straight
through to `_welcome`, which sets `onboarding = 'consent'`. An elder who tapped
the wrong button at the start and later asked for English would have been sent
back through the consent flow — and their `consent_at` rewritten. Guarded on
`onboarding = 'done'`, with a test asserting a new user still goes through
consent so the guard cannot swing the other way.

**Every command reply was still bilingual.** Onboarding stopped saying everything
twice that morning; `_run_command` did not. A user who chose English still got a
Hindi paragraph from `/stop`. Same complaint the operator raised, one step later
in the journey. Localised via `CMD_COPY`.

### The substring lesson, third time

The natural pattern `\b(english|hindi) mein baat kar` also matches "mera beta
english mein baat karta hai" — a fact about someone's son. Telling Saathi about
your family would have switched its language. Tightened to imperative and desire
forms (`karo|kariye|karen|karein|karni hai|karna hai`), with tests for three
third-person statements that must not match.

This is the same mistake as PR-23, where STOP matched `\bunsubscribe\b` as a
substring and a forwarded advert paused a user's reminders. Third time a loose
regex nearly reached state-changing behaviour. **Anchor or qualify by default;
substring-match only with a reason.**

### Evidence

337 tests (331 before, 6 new). Deployed, 0 errors, `/language` confirmed present
in `conversational_automation` on the live number.

### Remains

`lang_pref` still holds legacy `'hi-en'` for users created before today, mapped
to Hindi by `_lang()`. Whether to retire it or keep it as a third option is
undecided.

---

## 2026-07-27 — Survey: sibling projects and the OpenRouter ecosystem

No code. A day's worth of "is this useful to us" judgements, written down before
they evaporated. The operator reviewed each one as it was made.

### Read

`Taurus-Ai-Corp/GRIDERA`, `Taurus-Ai-Corp/gridera-comply`,
`Taurus-Ai-Corp/MONAD-Gate-`, `floating-astronaut/monad-project`,
`OpenRouterTeam/{python-sdk, terraform-provider-openrouter, search-benchmarks,
persona-hub, lux, docs}`, and the OpenRouter feature pages for ZDR, response
caching, guardrails, classifiers, plugins, logging, broadcast and attribution.

### Recorded

- `PATTERNS_TO_BORROW.md` — the sibling-project survey, extended with the
  OpenRouter ecosystem. Each entry says what to take **and why the
  impressive-looking things are refused**, because in six months the badges will
  still look impressive and the reasoning would be gone.
- `AI_ROUTING.md` §10 — features considered, deferred and refused.
- **D-O amended** — ZDR added as the mitigation for the transit residual.
- **PR-33** — D-D's bakeoff was eight utterances.

### The two findings that were not on the shopping list

**MONAD-Gate has a verb Saathi is missing.** Its loop is Register → Policy →
Gate → Attest. Saathi has the first three — the account is the liable principal,
`MUTATING_TOOLS` is the policy, `allowed_tools()` is the gate — and **no
attestation at all**. When tools are withheld because a turn was forwarded, no
record survives. That is not academic: it is exactly why PR-23 went unnoticed, a
forwarded advert pausing a user's reminders with nothing anywhere saying a
boundary had been touched.

**D-D rests on eight sentences.** Reading `search-benchmarks` — which grades 100
tasks per cell and still refuses to name a winner because the intervals overlap —
made the sample size in our own founding model decision impossible to unsee. The
8/8 vs 7/8 gap is one utterance, and it is currently justifying a ~60% cost
premium. PR-33.

### Refused, with reasons, so they are not re-proposed

- **Post-quantum crypto** (GRIDERA) — defends against harvesting traffic now to
  break in 2035. Saathi's threats are a compromised box, a leaked backup, an
  insider and DPDP. Impressive in a badge row, moves no risk.
- **Blockchain-anchored consent** (GRIDERA/Hedera) — immutability and DPDP's
  right to erasure are in direct conflict. Their subjects are enterprises proving
  compliance; ours can say "sab kuch bhool jao" and must be obeyed. Take the
  tamper-evidence, refuse the ledger: a hash-chained Postgres table.
- **persona-hub for PR-9** — would scale up the synthetic data that already
  invalidates the numbers, and would feel like progress while doing it.
- **Agent SDKs, server-side tools, LangChain, `lux`** — all move tool execution
  outside the code that enforces PRD §12's guarantee.
- **Response caching** — it is *response* caching, not prompt caching, so D-D's
  prefix budget is untouched. Also unverified whether the cache is scoped per
  account; for elder health content a cross-user hit would be a leak.

### Remains

- Nothing here is scheduled. Each item needs its own lane, and the ones touching
  a contract need a `DECISIONS.md` entry.
- The ordering that actually matters is unchanged and is in
  `PATTERNS_TO_BORROW.md`: PR-27, PR-22, PR-1, PR-7 come before any of it.

---

## 2026-07-27 · `bbb061b` deployed — the first deploy the box ran on itself

Four lanes closed and shipped: the dead `reminder_fires` worker path (`1430905`),
PR-25 (`758c008`), PR-26 (`e78e6ec`, `bd29978`), PR-28 (`f049793`, `bbb061b`).
337 → 366 tests.

**Evidence.** `sudo ops/deploy.sh --local`, exit 0. Six migrations
`already applied (baselined, checksum unknown)`, **zero applied** — which is the
whole point of PR-25, because applying them would have re-run 003's and 005's
backfills. 366 passed on the box. All four units active, `healthz` ok, tunnel
200, unsigned webhook 403, zero errors since restart. Live tree then compared
against `git archive bbb061b`: identical but for the two files PR-36 predicted
would survive.

**Three things were true that nobody had written down.**

1. *Every deploy silently re-ran two destructive backfills.* 003 admits every
   pending channel, 005 marks every `new` user `done`. Correct once, as
   backfills; ruinous on repeat, because they undo the admission gate and the
   consent step. Reproduced twice on a schema-only copy of live.
2. *Inbound documents failed silently in production.* `messages.kind` was written
   with WhatsApp's wire type and `document` is not in the `msg_kind` enum, so the
   insert aborted the transaction before the media capability ran. A user sending
   a prescription PDF got nothing back.
3. *A red test suite deployed.* `uv run pytest -q | tail -2` under a login shell
   with no `pipefail` — the pipeline's status was `tail`'s. Same for `uv sync`
   and `saathi-env-sync`.

Each of the three had passing tests, a healthy `/healthz`, and a deploy that
printed success. **That is now five separate occasions where green agreed with
the bug**, and the common cause has not changed: the assertion was written from
the implementation instead of from the contract. The counter-measure that
actually worked today was mechanical — delete the *call* from the production
path, not the function body, and require the test to go red. Eleven of those on
PR-26; two of them only failed after being rewritten, because the first version
hung instead of failing and the second errored on a syntax fault, which proves
nothing.

**The canary check is weaker than it looks.** After the deploy, `user_channels`
is `active|4, consent|2` and `users` is `done|2`. Nothing flipped — but there
were no `pending` channels and no `new` users to corrupt, so today's run proves
the ledger was *consulted*, not that it *saved* anything. The save is prospective.

**Still not proven, and it is the oldest open item:** no reminder has ever fired
on the live number. The worker registers four kinds and reports them at every
deploy; that is registration, not delivery. `ffmpeg -version` also passed.

**Cost of not fixing PR-36 now:** `worker/send_reminder.py` and
`worker/reminder_scheduler.py` were deleted from the box by hand after this
deploy. Every future deploy that drops a file needs the same manual step.

---

## 2026-07-27 — WhatsApp Cloud API Calling note recorded

Operator supplied Meta's WhatsApp Business Calling API overview. Captured the
vendor transcript at `docs/vendor/meta/cloud-api-calling.md` and recorded it as
future-channel context, not a build commitment.

### Contract updates

- `docs/DECISIONS.md` D-Q now says Cloud API Calling is strategically relevant
  but out of v1. The current product remains WhatsApp chat, inbound voice notes,
  and future TTS replies.
- `docs/PRD.md` open decision D6 now tracks whether Cloud API Calling enters a
  v1.1+ lane.

### Constraints captured

- Calling requires the business number to be on Cloud API, the app subscribed to
  the `calls` webhook field unless SIP is chosen, WABA/app subscription, and
  `whatsapp_business_messaging` permission.
- Production business-initiated calls require the account capability/messaging
  limit threshold and phone-number calling settings. The vendor note lists US,
  Canada, Egypt, Vietnam and Nigeria business numbers as excluded for
  business-initiated calling.
- Any implementation lane must add consent wording, rate limits, call-hours
  policy, retention/audit handling, and explicit caregiver/escalation
  expectations before enabling real-time calls.

---

## 2026-07-27 — V1 languages and Sarvam vendor shelf recorded

Operator set v1 language focus to eleven locales: Hindi (`hi-IN`), Bengali
(`bn-IN`), Tamil (`ta-IN`), Telugu (`te-IN`), Gujarati (`gu-IN`), Kannada
(`kn-IN`), Malayalam (`ml-IN`), Marathi (`mr-IN`), Punjabi (`pa-IN`), Odia
(`od-IN`), and English (`en-IN`).

### Contract updates

- `docs/PRD.md` D2 now reflects the eleven-locale v1 scope instead of Hindi +
  English only.
- `docs/DECISIONS.md` D-R records the operator decision and the consequence:
  evals, phrase banks, safety phrases, consent/onboarding copy, and TTS voice
  choices must be reported per locale.
- `docs/vendor/sarvam/github-repos.md` captures the Sarvam repo shelf called out
  by the operator: `llm_intent_entity`, `sarvam-mcp`, `llm_wer`, `skills`,
  `Gym`, `indic_nlp_library`, and `olmOCR-bench-sarvam-api`.
- `docs/vendor/README.md` indexes the Sarvam shelf and marks it as a source
  index rather than an API transcript.

### Guardrail

Sarvam may become Saathi's biggest vendor, but vendor examples do not move
runtime guarantees out of Saathi. Budgeting, redaction, deterministic safety,
per-turn tool authorization, and per-locale evidence stay ours.
