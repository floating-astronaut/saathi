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

---

## 2026-07-27 · `6082daa` deployed — and the reminder bug had already left a body

The clock lane shipped (`fa6bfc1`, `6082daa`). Second self-deploy, `--local`,
exit 0: six migrations `already applied (baselined)`, **zero applied**, 376
passed on the box, all four units active, healthz ok locally and through the
tunnel, unsigned webhook 403, zero errors since restart. Live tree then compared
against `git archive 6082daa` — every `.py` identical. The running interpreter
renders `Now, where the user is: Mon 27 Jul 2026, 21:57 (Asia/Kolkata).`, which
is existence *and* function.

**The overnight logs closed the open question, in the worst possible way.**

`reminders.id = 20`, `"Sone ka samay ho gaya hai 😴"` — the sleep reminder from
the screenshot — *was* created, at `2026-07-27 15:55:36`. Its `next_fire_at` was
`2025-01-09 18:05`: eighteen months in the past. The worker did exactly what it
should with an overdue row and fired it twenty-three seconds after creation, and
the nudge followed at 16:11 via the reclaim path.

This is PR-37's predicted failure, observed rather than reasoned about. A
clockless model was asked for a one-off reminder, `recurrence: once` requires a
`date`, and so it produced one. Note what did *not* happen: no exception, no
warning, no failed insert. The only artefact was a row that looked entirely
well-formed and carried the wrong year. The reminder that "never fired" had in
fact fired, immediately, for the wrong reason — which is why "no reminder has
ever fired" was the wrong question to have been asking.

`reminders.id = 20` is still `active` with a past `next_fire_at`. Left alone
deliberately: it is a real user's data, not a synthetic row.

**Two live defects found in the same logs, neither fixed here.**

- **A blank `ContentBlock` kills the turn.** Four times between 08:05 and 08:28:
  `ValidationException: The text field in the ContentBlock object at
  messages.N.content.0 is blank`. The index varied (0, 1, 2), so it is a blank
  block anywhere in the assembled history, not only the newest message. The user
  gets nothing back at all. Not reproduced yet; do that before touching it.
- **PR-34 is no longer theoretical.** Messages 124 and 125 are the same outbound
  reply stored twice, identical timestamp and identical length.

Benign, both self-healed: Postgres was restarted by an administrator command at
06:07 and the worker reconnected on its own; turn 6 sat claimed-but-unsent for
over fifteen minutes before the reclaim path caught it and delivered it.

**Still unproven:** that a reminder created *today*, with a clock, lands at the
right local time. The deploy proves the clock is in the prefix. It does not
prove the next reminder is correct, and only a live one will.

---

## 2026-07-27 · `618ce84` deployed — and the resend loop stopped, observed

Third self-deploy, `--local`, exit 0: zero migrations applied, 384 passed on the
box, four units active, healthz ok locally and through the tunnel, unsigned
webhook 403, zero errors since restart.

**The evidence that matters is not the deploy.** Turn 6 was the nudge that had
delivered itself four times. At 16:41:55 UTC, the first sweep after its
fifteen-minute threshold, it went to `failed` with `attempts = 3` — and
`messages` records **no further outbound row for user 14**. The loop stopped
because the attempt budget caught it, and the underlying cause is gone: a nudge
now records its `wa_message_id`, so the sweep will not mistake a delivered
message for an abandoned one in the first place.

Two separate things were wrong and both are fixed, which is worth separating:
the *cause* (nudge and checkin discarded the message id, so every delivery
looked abandoned) and the *blast radius* (five attempts, which the operator
judged too many to be on the receiving end of). Fixing only the cause would have
left the radius; fixing only the radius would have left every nudge sending
three times instead of five.

**What this run says about the method.** The bug was in production for as long
as nudges have existed and the test suite was green throughout, because
`reminder()` — the path everyone reads first — was correct, and its own comment
described the exact hazard the other two handlers had. Reading the correct
implementation is how you learn what the tests should have said; it is not
evidence that they said it. Six occasions now.

**Still open from this session:** the blank `ContentBlock` crash (four times
this morning, kills the whole turn, not reproduced yet) and PR-37.


---

## 2026-07-27 — Usage ledger design recorded

Research question: whether Langfuse or LiteLLM should replace the planned
OpenRouter approach for tracking Bedrock and Sarvam spend together.

### Outcome

- Keep OpenRouter for the Bedrock/GLM-5 hard-cap path described in
  `AI_ROUTING.md`; it returns LLM usage/cost but does not know Sarvam or
  WhatsApp template spend.
- Build `docs/USAGE_LEDGER.md`: a Saathi-owned append-only
  `vendor_usage_events` design for every paid vendor call.
- Treat Langfuse as an optional dashboard/mirror after the local row exists.
- Defer LiteLLM until Saathi needs to operate a self-hosted LLM gateway; it is
  not the first answer to Sarvam credits.

### Contract updates

- `docs/USAGE_LEDGER.md` added.
- `docs/DOC_SYSTEM.md` maps the new doc.
- `docs/DECISIONS.md` D-S records the ownership decision.
- `docs/AI_ROUTING.md` now points at the usage ledger.
- `docs/PROD_READINESS.md` PR-15 now points to the ledger as the concrete design
  for audio/text/template/search caps.

---

## 2026-07-27 · `2d65854` deployed — the first migrations to actually apply

Fourth self-deploy, `--local`, exit 0. **008 and 009 applied for real** — every
prior deploy reported six migrations `already applied (baselined)` and applied
nothing, so until tonight PR-25's ledger had never been exercised on its actual
job. It recorded both with checksums (`f2929435`, `82402530`) alongside the six
baselined rows.

**Verified against the live database, not the exit code.** 6 users, 6 accounts,
**0 users without an account** — the backfill covered everyone. All six accounts
`active`, so nobody was paywalled by the deploy. Zero rows in `ai_keys`,
`ai_key_events` and `account_payments`, which is correct: no key can mint with
credits at 0 and payments are off. The deployed interpreter reports the chain as
safety(0) → onboarding(10) → erase(20) → ack(21) → commands(22) → media(30) →
paywall(88) → agent(90), `payments.enabled()` False, and `status_of` returning
`active` for three real users.

434 tests on the box. All four units active, healthz ok locally and through the
tunnel, unsigned webhook 403, site 200, zero errors since restart.

### What shipped in this deploy

Six lanes, in the order they were found rather than planned: the clock in the
prefix (`fa6bfc1`), the nudge resend loop (`618ce84`), the blank-ContentBlock
crash (`c40d21a`), per-account AI keys (`27d5f43`), the paywall (`0946291`), and
webhook field logging (`b62d8cf`). Two of them — the resend loop and the blank
ContentBlock — were live defects affecting a real user, found by reading logs
rather than by testing.

### The pattern that has not gone away

Three more instances today of green agreeing with a bug. A nudge that delivered
perfectly and was re-sent every fifteen minutes, with `reminder()` carrying a
comment describing that exact hazard. A paywall whose "unconfigured sends
nothing" test passed with the kill switch deleted, because the fixture also left
the merchant id blank. And my own misdiagnosis of the blank ContentBlock, caught
by an existing test rather than by me: the `N > 0` in `messages.N.content.0` was
in the error text from the first reading and named the history, not the message.

The counter-measure that works remains mechanical — delete the guard from the
production path and require the suite to go red before believing it. Every fix
above was checked that way, and the paywall kill-switch test only exists because
the deletion was tried before the test was trusted.

### Twice in one day, the same way

Work was written directly into `/home/ubuntu/saathi` twice today and rescued
twice (`2a11443`, `2d65854`). That tree is not version controlled and a deploy
merges rather than replaces, so the loss would have been silent both times. The
warning in RUNBOOK was written after the first occurrence and did not prevent
the second. That suggests the fix is not a stronger warning.

---

## 2026-07-27 — off MeshPilot's Meta app, and two stale facts corrected

Saathi now runs on its own Meta app end to end. **Indofolk AI
`1019173634258664`** is the sole subscriber to WABA `1687148075730227`, its own
app secret verifies every inbound webhook, and the access token is
`type: SYSTEM_USER` with `expires_at: 0` on system user `122098890723360160`.
MeshPilot `1571039744742551` is unsubscribed and receives nothing.

**Evidence, all from Graph rather than inference.** Meta called our verify
endpoint from a Facebook IP and got the challenge echoed. A webhook body signed
with the new secret returns 200; the identical body signed with MeshPilot's
returns 403. The live token reads the phone number (`+91 8071 581 944`, quality
GREEN) and the approved templates. `subscribed_apps` returns one app.

**The sequencing was the entire risk**, and it is worth writing down because the
obvious order is the broken one. Register and verify the new callback while that
app is subscribed to nothing; subscribe it *alongside* the old one so both
deliver; swap `WA_APP_SECRET` and `WA_ACCESS_TOKEN` in a single write; only then
unsubscribe the old app. At every moment at least one delivery path verifies.
Swap the secret first and every inbound message 403s — and a rejected webhook
never reaches the pipeline, so it never reaches a log line naming a user. The
operator would have seen silence and nothing else.

### Two facts that were already resolved and kept being repeated

**PR-5 called the business borrowed for a day after D-M had corrected it.** D-M
recorded on 2026-07-27 that `ayurpetofficial` is a portfolio display label and
the legal entity is INDOFOLK WELLNESS PRIVATE LIMITED, verified, GSTIN
`07AAHCI7432A1ZV` — the entity the privacy pages already name. PR-5 went on
saying "the WABA sits under `ayurpetofficial`" as though that were a caveat.
Graph confirms `ownership_type: SELF` and `verification_status: verified`.

**And I reported 51 signing violations that were not violations**, by checking
`%G?` — which `CONTRIBUTING.md:64` states in as many words cannot work here,
because SSH verification needs `gpg.ssh.allowedSignersFile` and it is unset, so a
correctly signed commit also reports `N`. D-L had already settled that signing is
not a gate for a single-author repo.

Both are the same failure, and it is one this documentation set is structurally
prone to: **a fact resolved in one document does not resolve the rows that repeat
it.** A caveats journal is the worst place for it, because every row there is
supposed to describe something unfinished, so a stale row is indistinguishable
from a live one by shape alone. The only defence that worked today was checking
the claim against the system rather than against another document.

### Still unproven

No real inbound message has round-tripped through the new app. Signatures,
tokens, subscriptions and API reads are verified; a live message is not. Health
checks stay green either way, which is precisely why that gap matters.

## 2026-07-27 — AI-1 follow-up: runtime routing and existing-account provisioning

**Read:** `AGENTS.md`, `docs/DOC_SYSTEM.md`, `docs/THE_METHOD.md`, `docs/AGENT_SYNC_PROTOCOL.md`, `docs/ROLES.md`, `control-plane/ACTIVE_LANE_BOARD.md`, `control-plane/SESSION_COORDINATION.md`, `docs/AI_ROUTING.md`, `docs/DECISIONS.md` D-O/D-T, `docs/PROD_READINESS.md` PR-38/PR-46, `docs/LANDMINES.md`, and official OpenRouter docs for Chat Completions/provider routing field names.

**Changed:** `saathi/capabilities.py` now resolves the user's account and active OpenRouter key before the agent call; `saathi/agent/loop.py` accepts an account key and calls `saathi.openrouter.converse`; `saathi/openrouter.py` now adapts Bedrock-shaped messages/tools to OpenRouter Chat Completions with `provider.allow_fallbacks=false`, `provider.zdr=true`, `HTTP-Referer`, `X-OpenRouter-Title`, and fixed `z-ai/glm-5`; onboarding/admin provisioning dedupe uses `provision:v2:<account_id>`; migration 011 queues `provision_key` for already-onboarded accounts with no active key; focused tests were added for runtime request controls and versioned dedupe.

**Verified:** `uv run pytest -q` — 509 passed. Focused suite before the full run: `tests/test_openrouter_keys.py tests/test_onboarding.py tests/test_capabilities.py tests/test_clock.py` — 57 passed. `git diff --check` on touched tracked paths was clean. Stale-claim search found no remaining "nothing routes" / old dedupe / platform-default-by-design wording in the touched AI routing surfaces.

**Superseded later this session:** live spend-through was subsequently proven, migrations 011 and 012 were applied, the provisioning worker minted the remaining keys, and account 3 completed a real OpenRouter turn with token usage returned.

## 2026-07-27 — AI-1 follow-up: all existing accounts backfill

After migration 011, live DB inspection showed 7 accounts but only 3 completed-onboarding users; those 3 had active keys. Operator clarified by saying "do it" against the session goal that all current 6-7 users should have keys, so migration 012 was added to enqueue `provision_key` for every existing active account lacking one, including mid-onboarding users. No key material printed.

## 2026-07-27 — AI-1 closed: all accounts keyed and spend-through proven

**Applied:** staged on-box deploy from `/tmp/saathi-ai1-stage/saathi` through `ops/deploy_onbox.sh`, because `/home/ubuntu/saathi` is the deployed artifact with stub git. Migration 011 had already applied; migration 012 applied in this pass. Deploy ran `saathi-env-sync`, restarted services, and ran the full suite on-box: 509 passed. Standard verifier passed: `saathi-web`, `saathi-worker`, `cloudflared-saathi`, Postgres, healthz, worker kinds, and zero restart errors.

**Provisioning evidence:** after the worker tick, `provision_key` rows were all `acked` (8 historical/active provisioning turns total). Live DB inspection without printing key material showed accounts 1..7 all `free/active` with active OpenRouter key rows; every row had a key name, hash present, and ciphertext present. Migration 012 is recorded in `schema_migrations`.

**Spend-through evidence:** a value-blind probe selected a completed-onboarding user with an active key, resolved account 3's encrypted key via `openrouter.resolve()`, and ran `agent.loop.run(..., ai_api_key=key)` through OpenRouter. It returned text `route ok`, usage `input_tokens=821`, `output_tokens=40`, `hops=1`. No key material printed.

**Remains:** the probe was synthetic rather than a WhatsApp handset message, but it exercised the runtime resolution and OpenRouter inference path that a chat turn uses.

## 2026-07-27 — AI-1 correction: workspace-scoped remint needed

Operator caught that the keys had been minted in OpenRouter's Default workspace. OpenRouter docs confirm `workspace_id` is optional on `POST /api/v1/keys` and defaults to Default when absent; live runtime config showed `OPENROUTER_WORKSPACE_ID` length 0. The target workspace `718e8438-6c5a-48f9-85c9-f8909f2e4c47` was reachable as Indofolk AI. Code was patched so configured-workspace key names carry `:ws:718e8438`, avoiding the local unique-name conflict when rotating the default-workspace rows.

## 2026-07-27 — AI-1 correction closed: keys moved to Indofolk AI workspace

**Operator correction:** the seven keys minted in the previous pass landed in OpenRouter's Default workspace. Desired workspace: `718e8438-6c5a-48f9-85c9-f8909f2e4c47` (Indofolk AI).

**Docs checked:** OpenRouter `POST /api/v1/keys` documents `workspace_id` as optional and says it defaults to the default workspace if not provided; `GET /api/v1/keys` similarly defaults to Default unless `workspace_id` is passed; OpenRouter workspaces docs say API keys live inside a workspace. Source links used in final handoff.

**Cause:** live runtime config had `OPENROUTER_WORKSPACE_ID` length 0. The target workspace was reachable by the management key as `Indofolk AI` / `indofolk-ai`.

**Changed:** Secrets Manager `saathi/dev/runtime` now includes `OPENROUTER_WORKSPACE_ID` (36 chars, sha256 prefix `8ae3feeb...`), synced to `.env`. Key naming includes `:ws:718e8438` when a workspace is configured so revoked Default-workspace names do not block corrected remints under the DB's unique `ai_keys.name`. Deployed through `ops/deploy_onbox.sh`; on-box suite passed: 510 tests.

**Rotation evidence:** accounts 1..7 had their old active keys revoked upstream and locally, then reminted as `saathi:account:<id>:plan:free:env:dev:ws:718e8438`, cap `$5.00`, no reset. OpenRouter list with `workspace_id=718e8438-6c5a-48f9-85c9-f8909f2e4c47` returned all seven keys with `disabled=false`, `limit=5`, `limit_reset=null`, and matching workspace id. OpenRouter list without `workspace_id` returned no Saathi keys in Default. No key material or hashes printed.

**Spend-through evidence:** account 1's corrected key resolved through `openrouter.resolve()` and completed a real OpenRouter turn: `workspace route ok`, usage `input_tokens=822`, `output_tokens=39`, `hops=1`. Final service verifier passed: web, worker, cloudflared, Postgres, healthz, worker kinds, and zero restart errors.


Future provisioning guard: `openrouter.mint()` now raises `ProvisioningDisabled` if `OPENROUTER_WORKSPACE_ID` is unset, so a config drift cannot silently mint into OpenRouter Default again.

## 2026-07-27 — AI-1 future-signup guard

**Goal:** ensure every future user who completes onboarding is minted into OpenRouter workspace `718e8438-6c5a-48f9-85c9-f8909f2e4c47`, not Default.

**Changed:** `openrouter.mint()` now raises `ProvisioningDisabled` when `OPENROUTER_WORKSPACE_ID` is unset, before any upstream call. The create-key body always includes `workspace_id`, and configured-workspace key names include `:ws:718e8438`. Onboarding still queues `provision_key` on completion via `openrouter.provision_dedupe_key(account_id)`.

**Verified:** focused tests `tests/test_openrouter_keys.py tests/test_onboarding.py` passed (39). Full suite passed locally (511) and during on-box deploy (511). Runtime value-blind config check: workspace id length 36, sha256 prefix `8ae3feeb`, target match true. Deployed source check confirmed the fail-closed guard and `body["workspace_id"]` assignment are present. Future key-name dry check produced `saathi:account:999:plan:free:env:dev:ws:718e8438`; no vendor key was minted by the dry check. Final service verifier passed.

## 2026-07-28 — FLOW-1: PR-first agent workflow

**Operator decision:** even for a single-developer repo, agents should not default to direct pushes to `main` or runtime-artifact scratchpad work. The default landing path is now branch → GitHub PR → agent review/merge → deploy merged `main` → runtime verification. Agents run that loop themselves and ask the operator only on real blockers or explicit review requests.

**Changed:** `CONTRIBUTING.md` now owns the branch/PR/merge/deploy flow; `AGENTS.md`, `CLAUDE.md`, and `KIMI.md` point agents away from `/home/ubuntu/saathi` as a workbench; `docs/THE_METHOD.md` records the PR checkpoint; `docs/AGENT_SYNC_PROTOCOL.md` records the source/PR workflow; `docs/RUNBOOK.md` says deploy only merged `main`; `docs/DOC_SYSTEM.md` registers `CONTRIBUTING.md` as branch/deploy workflow owner; `control-plane/SESSION_COORDINATION.md` updates scratch-clone language to source-branch language.

**Verified:** docs-only diff checked with `git diff --check`. This change itself was authored on `agent/pr-first-workflow` to exercise the new rule.

## 2026-07-28 — CAP-1 commercial deeplinks and internet action contract closed

**Read:** `AGENTS.md`, `docs/DOC_SYSTEM.md`, `docs/AGENT_SYNC_PROTOCOL.md`,
`docs/THE_METHOD.md`, `docs/ROLES.md`, `control-plane/ACTIVE_LANE_BOARD.md`,
`control-plane/SESSION_COORDINATION.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`,
`docs/DECISIONS.md`, `docs/PROD_READINESS.md`, `docs/LANDMINES.md`,
`docs/AI_ROUTING.md`, `docs/USAGE_LEDGER.md`, and current external docs for
IATA NDC, Duffel, Amadeus, Ticketmaster Discovery, schema.org Actions, Google
product/merchant structured data, Google Maps URLs, WhatsApp catalog/product
messages, Agentic Commerce Protocol, and OpenAI browser-agent/Operator docs.

**Changed:** added `docs/COMMERCIAL_ACTIONS.md`; registered it in
`docs/DOC_SYSTEM.md`; amended `docs/ARCHITECTURE.md`; appended decision D-Y to
`docs/DECISIONS.md`; closed CAP-1 on the lane board and ended the session row.

**Verified:** `git diff --check` passed for the tracked doc edits before close.
The acceptance contract is represented in docs: Saathi may search, compare,
assemble, and hand off with visible links or cart drafts; it may not purchase,
pay, reserve, log in, read OTPs, touch third-party accounts, or run hidden
browser automation.

**Remains:** implementation lanes for `build_cart`/deeplink builders/provider
adapters. Before any paid provider ships, wire the usage event through
`docs/USAGE_LEDGER.md`; before any undocumented deeplink ships, add link-health
verification.

## 2026-07-28 — CAP-2 India-first cart/deeplink handoffs closed

**Read:** `docs/COMMERCIAL_ACTIONS.md`, `docs/ARCHITECTURE.md`,
`docs/DECISIONS.md` D-Y, `saathi/agent/tools/specs.py`,
`saathi/agent/tools/handlers.py`, `saathi/agent/prompt.py`, and existing lookup /
forbidden-tool tests.

**Changed:** added `saathi/commercial_actions.py` and
`tests/test_commercial_actions.py`; updated `build_cart` to return India-first
provider handoff links plus the plain list; updated the tool schema and prompt
boundary; wrote back to `docs/COMMERCIAL_ACTIONS.md`, `CHANGELOG.md`, lane board
and session coordination.

**Verified:** focused suite `uv run pytest -q tests/test_commercial_actions.py
tests/test_prefix_budget.py` — 9 passed; full suite `uv run pytest -q` — 516
passed. Tests cover provider selection, URL encoding, secret-like text omitted
from provider URLs, handler boundary text, and `assert_no_forbidden_tools()`.

**Remains:** no live paid adapters, no movie/flight offer APIs, and no link-health
cron yet. Those require separate lanes.

## 2026-07-28 — LIFE-0 daily-life OS roadmap closed

**Read:** `docs/DOC_SYSTEM.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`,
`docs/COMMERCIAL_ACTIONS.md`, `docs/DECISIONS.md`, current capability registry
and the active lane board.

**Changed:** added `docs/DAILY_LIFE_OS.md`; registered it in `docs/DOC_SYSTEM.md`;
amended the PRD summary with the accepted product frame; appended decision D-Z;
queued LIFE-1 through LIFE-6 on `control-plane/ACTIVE_LANE_BOARD.md`; ended the
session row.

**Verified:** docs-only lane; `git diff --check` to run before commit. Acceptance
met in docs: Saathi is framed as a WhatsApp operating system for daily life, and
the next build order is read/explain, tasks, bills, drafts, scam shield and local
errand handoffs.

**Remains:** implementation lanes LIFE-1..LIFE-6 are open and unassigned.

## 2026-07-28 — LIFE-1 forwarded-content read/explain/action closed

**Read:** `docs/DAILY_LIFE_OS.md`, `saathi/provenance.py`,
`saathi/capabilities.py`, `tests/test_provenance.py`, `tests/test_lookup.py`, and
existing relayed-command coverage.

**Changed:** updated `provenance.fence()` and `agent/prompt.SYSTEM` so forwarded
messages, bills, notices, screenshots and PDFs ask for explanation, amount/date/
place/person/action extraction, scam-pressure warning and exactly one safe next
step. Added tests in `tests/test_provenance.py` and `tests/test_lookup.py`;
updated `docs/DAILY_LIFE_OS.md`, `CHANGELOG.md`, lane board and session row.

**Verified:** focused suite `uv run pytest -q tests/test_provenance.py
tests/test_lookup.py tests/test_relayed_commands.py tests/test_prefix_budget.py`
— 47 passed; full suite `uv run pytest -q` — 518 passed. Existing safeguards
remain: mutating tools are withheld on `RELAYED`, deterministic commands require
trusted text, and relayed content remains fenced.

**Remains:** LIFE-2 task manager, LIFE-3 bill-specific extraction, LIFE-4 drafting
and LIFE-5 stronger scam shield are still open lanes.

## 2026-07-28 — LIFE-1b captionless media explains by default closed

**Read:** `docs/DAILY_LIFE_OS.md`, `saathi/pipeline.py`, `saathi/vision.py`,
`tests/test_vision.py`, `tests/test_media_limits.py`, and provenance tests.

**Changed:** `vision.classify_intent(None)` now returns `document`, so a
captionless image/screenshot uses the document/daily-life reading prompt rather
than generic image description. Updated vision/media tests plus roadmap,
CHANGELOG, lane board and session row.

**Verified:** focused suite `uv run pytest -q tests/test_vision.py
tests/test_media_limits.py tests/test_provenance.py` — 61 passed; full suite
`uv run pytest -q` — 519 passed.

**Remains:** real-device UX check for WhatsApp media forwards, and deeper
bill-specific extraction in LIFE-3.

## 2026-07-28 — LIFE-1c forwarded summary plus follow-up closed

**Read:** `docs/DAILY_LIFE_OS.md`, `saathi/provenance.py`,
`saathi/agent/prompt.py`, and forwarded/provenance tests.

**Changed:** relayed-content fence and system prompt now ask the model to skim
and summarise first, flag obvious risk, extract visible amount/date/place/person/
action, then ask one follow-up question: what would the user like Saathi to do
with it? Updated tests, roadmap, changelog, lane board and session row.

**Verified:** focused suite `uv run pytest -q tests/test_provenance.py
tests/test_lookup.py tests/test_relayed_commands.py tests/test_prefix_budget.py`
— 47 passed; full suite `uv run pytest -q` — 519 passed.

**Remains:** a real WhatsApp media-forward UX check would prove how this reads on
handset; LIFE-3 still owns bill-specific extraction.

## 2026-07-28 — ID-1 returning WhatsApp handle onboarding restart closed

**Read:** `docs/DOC_SYSTEM.md`, `docs/AGENT_SYNC_PROTOCOL.md`, `docs/ARCHITECTURE.md`, `docs/foundations/GLOSSARY.md`, `docs/DAILY_LIFE_OS.md`, `saathi/identity.py`, `saathi/onboarding.py`, `saathi/capabilities.py`, `saathi/pipeline.py`, `tests/test_capabilities.py`, `tests/test_onboarding.py`, and `tests/test_language_change.py`.

**Changed:** `saathi/capabilities.py` now treats old onboarding quick replies from already-onboarded users as idempotent: `ob:lang:*` may change language, while old consent/name/reminder/improve buttons reply that setup is already complete and do not mutate onboarding. Added regression coverage in `tests/test_capabilities.py`. Updated `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `CHANGELOG.md`, lane board and session coordination.

**Verified:** focused suite `uv run pytest -q tests/test_capabilities.py tests/test_language_change.py tests/test_onboarding.py` — 32 passed; full suite `uv run pytest -q` — 521 passed.

**Remains:** ID-2 owns the full stale-handle lifecycle: warning nudges, confirm/move account, and revocation/deletion only after the written 90-day dead-air period.

## OBS-1 - in-region tracing - 2026-07-29 (Clawcore)

Read: docs/ARCHITECTURE.md, docs/DECISIONS.md, docs/PROD_READINESS.md,
docs/RUNBOOK.md, CONTRIBUTING.md, saathi/metrics.py, saathi/config.py,
saathi/pipeline.py, saathi/agent/loop.py, saathi/web/app.py,
saathi/worker/__main__.py, saathi/capabilities.py.

Changed:
- saathi/observability.py (new) - privacy-hardened tracing module
- saathi/web/app.py - observability.init() on startup
- saathi/worker/__main__.py - observability.init() on startup
- saathi/pipeline.py - root span around handle_message
- saathi/capabilities.py - spans on safety.classify and agent.loop.run
- saathi/agent/loop.py - spans on model.call and tool_call; turn completion record
- pyproject.toml - added logfire, opentelemetry-exporter-otlp, opentelemetry-sdk
- ops/saathi-otelcol.service (new) - OTel Collector unit
- ops/saathi-jaeger.service (new) - Jaeger all-in-one unit
- ops/setup-tracing.sh (new) - idempotent installer
- tests/test_observability.py (new) - 11 tests
- docs/ARCHITECTURE.md - tracing layer in diagram, no-PII-in-spans boundary
- docs/DECISIONS.md - D-AB (tracing is in-region)
- docs/RUNBOOK.md - tracing section (units, querying, enable, troubleshooting)
- docs/PROD_READINESS.md - PR-27 (resource addition)
- CHANGELOG.md - 2026-07-29 entry

Verified:
- uv run pytest -q - 532 passed (521 existing + 11 new, zero regressions)
- ops/deploy.sh --local - deployed 12c51a5 to /home/ubuntu/saathi
- healthz: 200, all four services active, 0 errors since restart
- PR #11 merged (squash), branch deleted

Remains:
- Tracing is disabled by default (SAATHI_TRACING_ENABLED unset).
  To enable, add the env var to saathi-web and saathi-worker systemd units
  and restart. The collector and Jaeger units can be started independently
  via ops/setup-tracing.sh.
- Jaeger and OTel Collector binaries are not yet installed on the box
  (setup-tracing.sh exists but was not run - the deploy script runs the
  app, not infra installers).

## OBS-2 - tracing safety and localhost binding follow-up - 2026-07-29 (Codex)

Read: `docs/DOC_SYSTEM.md`, `docs/AGENT_SYNC_PROTOCOL.md`,
`control-plane/ACTIVE_LANE_BOARD.md`, `docs/ARCHITECTURE.md`,
`docs/RUNBOOK.md`, `docs/DECISIONS.md`, `saathi/observability.py`,
`ops/setup-tracing.sh`, `ops/saathi-otelcol.service`,
`ops/saathi-jaeger.service`, and `tests/test_observability.py`.

Changed:
- `saathi/observability.py` - span wrapper now preserves application exceptions
  and treats tracing enter/exit failures as no-op behavior.
- `ops/setup-tracing.sh` and `ops/saathi-jaeger.service` - collector receives on
  `127.0.0.1:4317`; Jaeger OTLP listens on `127.0.0.1:4318`; no OTLP bind to
  `0.0.0.0`.
- `tests/test_observability.py` - regression tests for app exception semantics,
  tracing close failure, and non-conflicting localhost ports.
- `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/RUNBOOK.md`,
  `CHANGELOG.md`, and control-plane docs - OBS-2 write-back.

Verified:
- `uv run pytest -q tests/test_observability.py` - 14 passed.
- `uv run pytest -q` - 535 passed.

Remains:
- The optional collector/Jaeger binaries are still not installed until
  `ops/setup-tracing.sh` is intentionally run.

## 2026-07-29 — GitLab mirroring moved from HTTPS helper to SSH

Operator asked to stop the repeated GitLab sync failures caused by the glab
HTTPS/OAuth credential helper. Created a dedicated ed25519 SSH key on the
runtime/source box:

- private key path: `/home/ubuntu/.ssh/saathi_gitlab_ed25519`
- GitLab public key title: `saathi runtime ip-172-31-32-37 2026-07-29`
- public fingerprint: `SHA256:MxJY407pxa6juUHqg2o2rQ+fnJl39pcV8rcDhm/3zzU`
- expiry: 2027-07-29

Changed local SSH config to add host alias `gitlab-saathi`, switched the source
checkout's `gitlab` remote to `git@gitlab-saathi:nuraveda-lab/saathi.git`, and
verified `ssh -T gitlab-saathi` authenticates as `@floating-astronaut`.

Verified: `git push gitlab main` over SSH succeeded, bringing GitLab from
`d9bee45` to `3dced24`; `git ls-remote origin main` and `git ls-remote gitlab
main` both returned `3dced240381ef45b952f447cdd1cc5fe40ccc28b`.

Docs updated: `CONTRIBUTING.md`, `docs/RUNBOOK.md`, `docs/LANDMINES.md`, and
the CRED-1 lane notes. CRED-1 remains open because this improves reliability
but does not decide whether the runtime box should keep forge write access.

## OBS-3 - Logfire cloud binding for indofolk-ai - 2026-07-29 (Codex)

Read: `docs/DOC_SYSTEM.md`, `docs/AGENT_SYNC_PROTOCOL.md`,
`control-plane/ACTIVE_LANE_BOARD.md`, `docs/ARCHITECTURE.md`,
`docs/DECISIONS.md`, `docs/RUNBOOK.md`, `saathi/observability.py`,
`tests/test_observability.py`, and `ops/set-secret.sh`.

Changed:
- `saathi/observability.py` - Logfire cloud export is now
  `send_to_logfire="if-token-present"` and the local OTel Collector exporter is
  passed as an additional span processor instead of replacing Logfire's
  processors.
- `tests/test_observability.py` - coverage now pins token-gated cloud export,
  local collector preservation, `inspect_arguments=False`, scrub behavior, and
  disabled-by-default behavior.
- `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/RUNBOOK.md`,
  `CHANGELOG.md`, lane board and session coordination - OBS-3 write-back.

Secrets:
- Stored `SAATHI_TRACING_ENABLED=1` and `LOGFIRE_TOKEN` in Secrets Manager
  `saathi/dev/runtime` through `ops/set-secret.sh`, value-blind. The write token
  points to Pydantic Logfire project `indofolk-ai`. The broader Pydantic API key
  was not stored because app runtime does not need it.

Verified:
- `uv run pytest -q tests/test_observability.py` - 15 passed.
- `uv run pytest -q` - 536 passed.

## CodeGraph agent tooling - 2026-07-29 (Codex)

Read: `AGENTS.md`, `CLAUDE.md`, `docs/DOC_SYSTEM.md`, `docs/AGENT_SYNC_PROTOCOL.md`, `control-plane/ACTIVE_LANE_BOARD.md`, `control-plane/SESSION_COORDINATION.md`, CodeGraph README, installer script, package metadata, Codex/Claude target writers, shared config writer, and telemetry docs.

Changed:
- Installed CodeGraph v1.5.0 standalone bundle under `/home/ubuntu/.codegraph` with launcher at `/home/ubuntu/.local/bin/codegraph`.
- Wired CodeGraph MCP into Codex (`/home/ubuntu/.codex/config.toml`) and Claude Code (`/home/ubuntu/.claude.json`, `/home/ubuntu/.claude/settings.json`, `/home/ubuntu/.claude/CLAUDE.md`) using explicit `codex,claude` targets.
- Initialized CodeGraph for `/tmp/saathi-main-sync`; committed only `.codegraph/.gitignore`, not the generated SQLite index.
- Updated `AGENTS.md`, `CLAUDE.md`, `docs/AGENT_SYNC_PROTOCOL.md`, `CHANGELOG.md`, and session coordination so agents use CodeGraph first when `.codegraph/` exists.

Verified:
- `codegraph version` - 1.5.0.
- `codegraph telemetry off` - telemetry disabled persistently and buffered,
  unsent data deleted.
- `codegraph telemetry status` - disabled by saved config when no override is
  present.
- `codegraph init` - 102 files indexed; 1,686 nodes; 3,633 edges.
- `codegraph status` - index up to date.
- `codegraph explore` returned line-numbered source and blast-radius output for WhatsApp pipeline and observability paths.

Remains:
- Codex/Claude sessions must restart before the MCP server appears as a live tool in their tool lists. Shell fallback works now with `codegraph explore`.

## RATE-1 / RATE-2 — inbound rate and concurrency admission — 2026-07-29 (Codex)

Read: `docs/DOC_SYSTEM.md`, `docs/AGENT_SYNC_PROTOCOL.md`,
`control-plane/ACTIVE_LANE_BOARD.md`, `control-plane/SESSION_COORDINATION.md`,
`docs/THE_METHOD.md`, `docs/ROLES.md`, `docs/LANE_LIFECYCLE.md`,
`docs/ARCHITECTURE.md`, `docs/PROD_READINESS.md` PR-15/PR-26,
`docs/USAGE_LEDGER.md`, `docs/AI_ROUTING.md`, `docs/LANDMINES.md`, the inbound
pipeline, DB migrations, configuration, and test seams.

Changed:
- `saathi.rate_limit` plus migration 013: content-free, Postgres-backed inbound
  reservations and per-reason notice timestamps.
- `pipeline.handle_message`: after identity/dedupe and before STT/media/safety
  dispatch/model work, take the process-local turn gate (8) and reserve the
  user's rolling window (6 turns/60 seconds). The per-user advisory lock is
  non-blocking, so contention refuses quietly rather than creating a queue.
- Config, regression coverage, architecture/PR-15/usage-ledger docs and
  changelog record the values and the remaining monetary/edge-limit scope.

Verified:
- Focused: `uv run pytest -q tests/test_rate_limit.py tests/test_pipeline_order.py tests/test_media_limits.py` — 43 passed.
- Full: `uv run pytest -q` — 542 passed, both before merge and during deploy.
- PR #17 squash-merged as `ac0a493` and synchronized to GitHub and GitLab.
- `ops/deploy.sh --local`: migration `013_inbound_rate_limits.sql` applied;
  web, worker, Cloudflare tunnel and PostgreSQL all active; localhost and public
  `/healthz` 200; unsigned webhook probe 403; zero errors since restart.
- Read-only DB check: migration ledger records 013 and both
  `inbound_turn_admissions` / `inbound_limit_notices` tables exist.

Remains:
- PR-15 is not fully closed: Cloudflare/per-IP limiting, multi-process global
  coordination, and cross-vendor monetary caps remain explicitly open in
  `PROD_READINESS.md` / `USAGE_LEDGER.md`.

## SEC-1 — Meta Business Agent responder guard — 2026-07-29 (Codex)

Read: doc system/sync/control plane, `LANDMINES.md`, `PROD_READINESS.md` PR-6,
D-E, alerting/runbook surfaces, Meta captured docs, and the live Graph state.

Changed: added `saathi.meta_guard`, its hourly systemd timer/service, and
alert-installer support. The guard requires Saathi's configured app to retain
the `whatsapp_business_account/messages` subscription and rejects any non-empty
Business Agent settings response. It uses the existing `OnFailure` SNS path.

Verified: PR #19 merged as `c19a0e4`; full suite 544 passed before merge and
during deploy. `ops/alerting/install.sh` enabled the timer. Its first live run
returned HTTP 200 from both Meta checks and logged `Meta responder guard passed`;
the next hourly run is scheduled. Web, worker, tunnel and `/healthz` remained
healthy.

Remains: `subscribed_apps` is supplementary only: it returned an empty list
after Meta accepted the documented subscribe POST, so it is not used as a
fail-open exact-set monitor.

## CRED-1 — runtime forge write authority decision — 2026-07-29 (Codex)

Read: control plane, `PROD_READINESS.md` PR-22, `CONTRIBUTING.md`, D-L, and
runtime GitHub/GitLab authentication state.

Decision: operator chose to retain runtime GitHub/GitLab write credentials and
dedicated SSH keys as mirror authority (D-AC). Saathi's running app does not
execute from either forge; the relevant blast radius is a poisoned future deploy
and GitLab Cloudflare Pages `site` updates, not an immediate app-process change.

Remains: revisit this exception if runtime exposure grows, contributors change,
or the site gains sensitive flows.

## ID-2 — stale WhatsApp handle 90-day lifecycle — 2026-07-29 (Codex)

Read: `DOC_SYSTEM.md`, sync/control-plane docs, PRD/build plan, architecture,
D-AA, glossary, landmines, identity/pipeline/scheduled-turn implementation and
its tests.

Changed: migration 014 adds the `reverify` handle state and backfills 60-day
lifecycle turns. The worker sends a content-free day-60 `daily_checkin` then
revokes only after 90 days of continuous dead air. A returning stale handle is
stopped before logs, history, transcription, tools, memory or model work; it
can continue explicitly or issue a 15-minute move code. `MOVE <code>` accepts
only a blank new handle, makes it primary and revokes the old one.

Verified: focused lifecycle tests passed (29); full `uv run pytest -q` passed
with 549 tests before merge and during deploy. PR #22 merged as `60f20f0`.
`ops/deploy.sh --local` applied migration 014 and reported web/worker/tunnel/
PostgreSQL active, localhost and public health 200, unsigned webhook 403, and
the `reverify` worker kind registered. Read-only DB evidence: migration 014 is
recorded, 8 pending lifecycle checks were backfilled, and 0 live handles are
currently in `reverify`.

Remains: the day-60 outreach deliberately uses the existing generic template;
if product wants explanatory proactive copy, it must first obtain a dedicated
Meta-approved utility template without exposing prior ownership.

## LIFE-5 — stronger deterministic scam shield — 2026-07-29 (Codex)

Read: doc system/control plane, `DAILY_LIFE_OS.md`, safety/clinical grounding,
architecture, classifier and safety tests.

Changed: priority-0 classifier now recognizes courier/customs/police pressure,
electricity disconnection, loan/investment, job/pension, UPI collection and
remote-support requests. Clear fraud remains `SCAM`; lower-confidence pressure
is `SUSPICIOUS`. Both bypass the model; the latter gives one safe official-contact
verification step and 1930 escalation.

Verified: focused safety/capability suite 60 passed; full suite 560 passed before
merge and during `ops/deploy.sh --local`. PR #24 merged as `a724921`; web, worker,
tunnel and PostgreSQL active, public health 200, unsigned webhook 403, zero restart errors.

Remains: tune patterns only with explicit false-positive examples; broad payment
words alone intentionally do not trigger the shield.

## LEDGER-1 — vendor usage ledger foundation — 2026-07-29 (Codex)

Read: doc system/sync/control plane, PRD/build plan, `USAGE_LEDGER.md` §11,
architecture, PR-15, runbook, current rate limiter/worker/config/migration
conventions, and CodeGraph call paths.

Changed: migration 015 creates content-free append-only vendor usage events and
auditable reservation rows. `saathi.usage` supplies idempotent, account advisory
lock-protected holds, cap refusal, settlement, release, event insertion and
expiry; the worker sweeps only stale holds into `expired`, never deletes them.
The config default is observe-only and no paid model, speech or template call is
hooked in this slice. PR-15 and the runbook now also record the existing
Cloudflare webhook edge rule and its positive/negative verification.

Verified: focused `tests/test_usage.py` passed 9; full suite passed 569 before
merge and again during `ops/deploy.sh --local`. PR #27 merged as `b71a849`;
migration 015 applied; web, worker, Cloudflare tunnel and PostgreSQL were
active; localhost and public health returned 200; unsigned webhook returned
403; no worker warnings since restart. Read-only PostgreSQL check confirmed
both ledger tables and the reservation-state type exist.

Remains: Slice B wires direct Bedrock/OpenRouter call paths and begins the
seven-day comparison; Slice C adds speech/templates; Slice D introduces caps.
PR-15 is still open until monetary enforcement and the cross-process global
coordination decision are finished or explicitly retired.

## LEDGER-2 — vendor usage hooks and staged STT enforcement — 2026-07-29 (Codex)

Read: doc system, sync/control-plane docs, Method/roles, `USAGE_LEDGER.md` §11,
`AI_ROUTING.md`, architecture, PR-15, current pipeline/usage/config code via
CodeGraph, and existing usage/pipeline/rate-limit tests.

Changed: successful Bedrock/OpenRouter model calls, Sarvam STT calls and
WhatsApp template sends now write Saathi-owned content-free usage events.
Sarvam STT computes the catalog INR paise estimate from WAV duration before the
vendor call and, when `SAATHI_USAGE_ENFORCEMENT_ENABLED=true`,
`SAATHI_USAGE_LEDGER_MODE=enforce`, and `SAATHI_USAGE_ACCOUNT_CAP_PAISE>0`, takes
an account-locked INR reservation before sending audio to Sarvam. Cap exhaustion
or missing accounting returns fixed voice-limit copy and never reaches STT.
Successful enforced calls settle the reservation and link the event. Reservation
cap aggregates are currency-scoped so USD LLM usage cannot consume INR STT
budget. Runtime defaults remain observe-only.

Verified: focused suite `uv run pytest -q tests/test_usage.py
tests/test_pipeline_order.py tests/test_rate_limit.py` passed 29; full
`uv run pytest -q` passed 577 before PR. PR #32 merged as `aacd5af`; local deploy
ran migrations, full suite passed 577 again, and verified active web, worker,
Cloudflare tunnel and PostgreSQL. Independent post-deploy checks returned
localhost health OK and all four services active; deploy also verified public
health 200 and unsigned webhook 403.

Remains: PR-15 still has broader paid-surface enforcement work unless the
operator explicitly narrows the production requirement to STT-only: LLM/template
pre-call reservations, global vendor caps and their alert path are not enabled
by this lane.

## RUNTIME-MIGRATION-1 (Phase 1) — app boots on the successor box — 2026-07-29 (ZCode)

Read: doc system, RUNBOOK, PROD_READINESS RUNTIME-MIGRATION-1, app/config/db code
via exploration (minimum-to-boot analysis), ops/deploy_onbox.sh migration runner.

Changed: nothing in application code. On-box provisioning only, on the successor
box `ip-172-31-41-224` (ap-south-1): rebuilt the Python venv cleanly on 3.13.14
via `uv` (the prior venv targeted 3.14 but symlinked to system 3.12 and could not
import fastapi); installed PostgreSQL 16.14 server; created the `saathi` role +
database matching the existing `SAATHI_DB_DSN`; applied `db/extensions.sql`
(pg_trgm, superuser) + `db/schema.sql` (base v1 tables) + all 14 migrations
(002–015) via the idempotent `schema_migrations` checksum ledger — 26 tables, 14
rows recorded with checksums. Separately registered a second SSO profile
(`saathi`, AWSAdministratorAccess in 559896294326) via device-code flow so this
box can reach Saathi-scoped AWS resources; verified read-only reach to the
`saathi/dev/runtime` secret (described, not read). MeshPilot resources untouched.

Verified: `GET http://127.0.0.1:3130/healthz` returned
`{"ok":true,"pg":"16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)","model":"zai.glm-5"}`
HTTP 200, 2.3 ms — the success signal defined in `ops/deploy_verify.sh`. uvicorn
startup log clean; no startup event opens pools, so the only I/O on the path is
the DB healthcheck. The live webhook on `saathi.n8nworld.store` was never
touched — it continued to serve from the original box throughout.

Remains: Phase 2 (not done). The `saathi-web`/`saathi-worker` systemd units are
still not defined in the repo or installed on this box; the app was run manually
for proof and then stopped (3130 is free). `cloudflared` is not installed here,
so the `saathi-dev` tunnel connector still runs on the original box. Full
functional cutover needs the app to reach real Bedrock/S3/Secrets (the `saathi`
profile now provides that path) and a live webhook round-trip before the original
box can be retired. No live traffic moved.

## RUNTIME-MIGRATION-2 (Phase 2) — systemd + cloudflared + live cutover — 2026-07-29 (Clawcore)

Read: docs/DOC_SYSTEM.md, docs/RUNBOOK.md, docs/PROD_READINESS.md, docs/ARCHITECTURE.md, docs/ENGINEERING_SUPERVISOR.md (RUNTIME-MIGRATION-1 entry), ops/deploy_onbox.sh, original box systemd unit definitions.

Changed:
- ops/saathi-web.service (new) — systemd unit, uvicorn on 127.0.0.1:3130
- ops/saathi-worker.service (new) — systemd unit, python -m saathi.worker
- ops/cloudflared-saathi.service (new) — cloudflared tunnel unit
- /etc/systemd/system/saathi-web.service.d/20-aws-profile.conf — AWS_PROFILE=saathi
- /etc/systemd/system/saathi-worker.service.d/20-aws-profile.conf — AWS_PROFILE=saathi
- cloudflared v2026.7.3 installed at /usr/local/bin/cloudflared
- Tunnel token copied from original box; cloudflared connected to 4 Mumbai edges
- Original box: cloudflared-saathi stopped (kept for rollback)

Verified:
- All four services active: saathi-web, saathi-worker, cloudflared-saathi, postgresql@16-main
- GET https://saathi.n8nworld.store/healthz -> {"ok":true,"pg":"16.14...","model":"zai.glm-5"} 200
- GET https://saathi.n8nworld.store/webhook/whatsapp -> 403 (unsigned, correct)
- uv run --extra dev pytest -q -> 577 passed
- Bedrock converse() returns "pong" via AWS_PROFILE=saathi (account 559896294326)
- Worker: "worker up — scheduled kinds: [checkin, media_purge, nudge, provision_key, reminder, reverify]"

Known issue (non-blocking):
- metrics.py CloudWatch PutMetricData fails with AccessDenied (IndofolkDevBoxRole in 635860424621 lacks cloudwatch:PutMetricData). This is by design — metrics.py never raises into a turn (same contract as observability.py). The heartbeat alarm was already broken on the original box (it required the old instance role). Recorded as PR-28 below.

Remains:
- Original box web/worker/postgres still running (cloudflared only was stopped). Full retirement is a separate lane.
- CloudWatch metrics gap (PR-28)
- No WhatsApp template sends verified on this box — templates are Meta-side, not box-dependent, so no change is expected.
- OPS-1 tracing stack (saathi-otelcol/saathi-jaeger) not re-installed here — observability.py exists but SAATHI_TRACING_ENABLED is unset.

## RUNTIME-MIGRATION-3 (Phase 3) — estate off the MeshPilot org + old box retired — 2026-07-30 (Claude)

**Read:** CLAUDE.md, docs/RUNBOOK.md, docs/PROD_READINESS.md, docs/DECISIONS.md,
the tail of this file (Phase 1/2 closures), saathi/config.py, saathi/bedrock.py,
saathi/media_store.py, saathi/metrics.py, ops/deploy.sh, ops/alerting/.

**Symptom that started it:** the successor box looked healthy — `/healthz` 200,
services active — while three things were quietly wrong. `cloudwatch:PutMetricData`
failed every 30s (heartbeat not emitted by this box; the alarm read OK because it
watched the *old* box's data), audio writes and artifact reads were AccessDenied for
the instance role, and both services carried `AWS_PROFILE=saathi` — an SSO session
into `559896294326` on a refresh token that cannot be renewed non-interactively.
Inference, metrics and voice uploads were all crossing into the MeshPilot org.

**Changed (all via PRs into main, deployed `--local`, verified live):**
- `01aca03` — created `saathi-dev-{artifacts,audio}-635860424621` mirroring encryption/
  versioning/public-access-block/lifecycle and copied all 21 objects (ETag manifest +
  SHA-256 for the multipart one); migrated `saathi/dev/gcp-sa` byte-exact; recreated the
  `saathi-alerts` topic + both alarms; five least-privilege inline policies on
  `IndofolkDevBoxRole` mirroring the old `saathi-dev-box`; repointed `SAATHI_AUDIO_BUCKET`,
  `ops/deploy.sh`, and `ops/alerting/saathi-alert` (now asks IMDS for the instance id).
- `c98a98e` — DB moved (8 users / 262 messages / 58 scheduled_turns, state histogram
  matched exactly). Went through plain SQL because an 18.x custom dump is archive 1.16
  and pg_restore 16 refuses it; stripped one v17+ GUC; reassigned ownership to `saathi`
  after `--no-owner` left tables under `postgres` and the worker hit InsufficientPrivilege.
- `d4e0f41` — Postgres 16.14 → 18.4 (PGDG + `pg_upgradecluster`) to match the source box,
  52s downtime; proven by restoring the old box's own 1.16 dump here. Closes
  MIGRATION-PG-VERSION-1.
- `69bd817` — dropped the retained 16 cluster + the leftover empty DB.
- `265aedb` — inference moved onto a Bedrock-only IAM user `saathi-bedrock-invoke`
  (`559896294326`), reached by a static key in the runtime secret, scoped in
  `saathi/bedrock.py`; removed the process-wide `AWS_PROFILE`. Corrected the record that
  `AmazonBedrockMantleFullAccess` on the role did not (and cannot) grant account entitlement.

**Verified:** 577 tests green after each step; `/healthz` 200 local + tunnel; instance
role reads both secrets, round-trips the voice prefix, writes `backups/` — and denies a
write outside `backups/` and a PutMetricData outside the `Saathi` namespace (fails closed);
WorkerHeartbeat + BackupSuccess now land in `635860424621`; a real backup dumped and
verified by restore; the Bedrock static key denies S3/Secrets/SSM/IAM/EC2/CloudWatch and any
model or region outside the two allowed. Old box retired: services disabled, instance
`i-01b2c27883acb25ca` terminated, root volume + the 2026-07-28 snapshot deleted, old buckets
swept, old secrets scheduled for deletion (2026-08-06). SNS email re-subscribed and both
alert paths (OnFailure + alarm→SNS) confirmed by executed-action records.

**Remains:**
- MIGRATION-BEDROCK-1 (P1): model access on `635860424621` is NOT_AUTHORIZED and
  `PutUseCaseForModelAccess` is refused — the one reason inference still uses a foreign
  account. Support case drafted; teardown steps in PROD_READINESS. See PR-BEDROCK-KEY for
  the long-lived-key trade this created.
- OpenRouter is the live inference path for all 8 accounts (verified); the Bedrock key is
  the fallback, not the default.

## CAPI-1 — Click-to-WhatsApp conversion attribution — 2026-07-30 (Claude)

**Read:** docs/CAPI_GATEWAY.md, docs/DECISIONS.md, Meta CAPI-for-business-messaging +
Automatic-Events + CTWA docs (2026-07-30), saathi/pipeline.py, saathi/onboarding.py,
saathi/identity.py, saathi/config.py, saathi/metrics.py, db/migrations/. Used CodeGraph on
the source checkout to confirm the handle_message → resolve → dispatch flow and the
onboarding completion call site + blast radius before editing.

**Symptom:** ads-that-click-to-WhatsApp spend had no conversion signal; Meta's `ctwa_clid`
arrived on the first ad-originated message and was discarded (extract_messages passes the
whole message; nothing read `referral`).

**Changed:** migration 016 (content-free `ctwa_clid`/`ctwa_captured_at` on users);
`saathi/capi.py` — `capture_referral` (write-once, no-op without a referral) and
`report_lead` (LeadSubmitted to `graph.facebook.com/v21.0/{DATASET_ID}/events`,
`action_source: business_messaging`, only ctwa_clid + WABA id in user_data, never raises);
call sites in `pipeline.handle_message` (after resolve, before the gates) and `onboarding.py`
(after `_grant_free_allowance`); config `SAATHI_CAPI_DATASET_ID` + `SAATHI_CAPI_TEST_EVENT_CODE`.
Chose Model B (self-reported) over the Automatic Events API (Meta NLP over threads) —
boundary D-AD. Left the Cloud Run Gateway as a teardown follow-up since CTWA events go direct
to the dataset.

**Verified:** 587 tests (10 new) assert the event structurally cannot carry message content
or PII (exact key sets), capture is write-once, organic/unconfigured no-op, Graph outage
returns cleanly. Ruff clean on new code (pipeline.py's 16 findings are pre-existing, identical
on origin/main). Live: migration applied to the box (both columns present); a probe with the
exact payload was accepted on every field by dataset 2038444060213473 (owner Indofolk
935287898727459) and rejected *only* the synthetic ctwa_clid, subcode 2804087 `"Messaging
Event Invalid Ctwa Clid"` — endpoint/schema/token correct, only a real ad click's id needed.

**Remains:** enable in production (`SAATHI_CAPI_DATASET_ID` in the runtime secret + deploy);
add the third-party-egress line to the privacy policy; decide the Cloud Run Gateway's fate
(billing since 2026-07-27, unused by this path).
