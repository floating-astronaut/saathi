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
