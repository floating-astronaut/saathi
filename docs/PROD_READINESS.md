# Production readiness — the caveats journal

Running log of things that are **acceptable in dev and not acceptable in
production**. Everything below is a deliberate shortcut, not an oversight: it
was the right call at the time and it is written down so it cannot quietly
become permanent.

**Today's posture:** AWS account `559896294326` is *Mesh Pilot Dev*. One box,
one Postgres, no redundancy, no alerting, no on-call. That is fine for internal
testing and would be negligent with a hundred elders' medication reminders.

Add a row when you take a shortcut. Move it to **Resolved** when it is genuinely
fixed, with evidence. Do not delete rows — the history of what we accepted and
why is the useful part.

Severity: **P0** blocks first external user · **P1** blocks paid launch ·
**P2** should be fixed before scale.

---

## P0 — must be resolved before a stranger's parent uses this

### PR-1 · Dev AWS account
Running in *Mesh Pilot Dev* (`559896294326`), which shares an org with MeshPilot
and has no production controls. Real users' health-adjacent data should not live
in an account named "dev".
**Fix:** dedicated Saathi production account, ap-south-1, with its own budget
alarms and SCPs.

### PR-2 · Box loss is unrecovered
Backups protect against *data* loss. If the instance dies, there is no
infrastructure-as-code to rebuild it — the box was built by hand this session
(security group, IAM role, cloudflared, systemd units, poppler, uv, Postgres).
Recovery today means repeating that from `docs/RUNBOOK.md` by hand.
**Fix:** CloudFormation or Terraform for the whole box, in the repo. The v2
MeshPilot lane already learned this — see `ops/v2-infra` there, and law L3 in
its supervisor log.

### PR-3 · No alerting — RESOLVED 2026-07-27
Detection is built and proven: `saathi-alert@.service` drop-ins on all four
units, a `WorkerHeartbeat` published after every successful worker tick, and two
CloudWatch alarms (`saathi-worker-heartbeat-missing`, `saathi-backup-stale`)
wired to SNS topic `saathi-alerts`. Both treat missing data as breaching. See
`RUNBOOK.md`.

**Proven by inducing the outage, not by inspecting config.** `saathi-worker`
stopped 01:44:05Z → alarm ALARM 02:04:59Z → SNS `NumberOfNotificationsDelivered`
8→9 with `NumberOfNotificationsFailed` 0, to the confirmed subscriber
`support@glitchexecutor.com`. `saathi-backup-stale` was separately observed
transitioning ALARM→OK as `BackupSuccess` data arrived, so both directions work.

**Residual, deliberately left open:** detection latency is **~21 minutes**, not
the 10 the alarm config implies (see `RUNBOOK.md`). Whether that is acceptable
for a medication product is a product decision, not a bug. `cloudwatch:
DescribeAlarmHistory` is also still denied to the box, so alarm transitions can
be observed live but not audited afterwards.

### PR-4 · Reminders had no delivery guarantee — partly resolved 2026-07-27
The original row understated it. Reminders were not merely unguaranteed, they
were **never dispatched**: `_create_reminder` wrote to `reminder_fires`, the
worker read only `scheduled_turns`, and `worker/reminder_scheduler.py` — the
sole reader of `reminder_fires` — was referenced nowhere in the repo. Latent
rather than live, because no real reminder had been created yet.

**Resolved:** creation now enqueues onto `scheduled_turns`; recurring reminders
book their next occurrence; a deliberate no-send (paused user, no active handle)
is marked `skipped`; and `scheduling.sweep_stuck` reclaims turns claimed but
never sent. Proven end to end against the live database, not only against fakes.

**Still open, and the reason this row stays P0:** nothing yet pages a human when
dispatch stops. The sweep records the failure; no one is told. Depends on PR-3,
which is itself blocked on `cloudwatch:PutMetricAlarm` and SNS (see PR-22).
Acknowledgement is separately broken — lane PR-4b.

### PR-5 · Meta app and WhatsApp number are borrowed
The app (`1571039744742551`) and the ayurpet system-user token are MeshPilot's;
the number is **+1 Canadian** and the WABA sits under `ayurpetofficial`
(decision D-J, made knowingly). India messaging rates, quality rating and
template pacing all key off the sender's country, so §14's cost model does not
hold on this number.
**Fix:** Saathi's own Meta app, its own system user scoped to WhatsApp only, and
an **Indian** phone number before pricing means anything.

### PR-6 · Meta Business Agent is one toggle from taking over
`GET /{waba}/subscribed_apps` shows Meta's Business Agent app
(`1143680903703001`) subscribed to our WABA alongside ours, with
`rollout.enabled = false` but `ai_audience: EVERYONE`. If enabled, Meta's model
becomes the primary responder and inbound messages never reach our deterministic
§12 classifier — risk R7.
**Fix:** unsubscribe it, or confirm deliberately that it stays disabled and add a
check that alerts if it flips.

---

## P1 — before anyone pays

### PR-7 · Single Postgres on the box, no PITR
Backups every 6 hours, verified by restore. But recovery point is up to 6 hours
and there is no point-in-time recovery or failover. Consent records and
onboarding state now live here.
**Fix:** RDS or Aurora Serverless v2 in ap-south-1. Deferred deliberately
(operator decision, 2026-07-26) — the on-box backup story was built instead.

### PR-8 · No TTS — a voice-first product that only writes back
PRD §9 and decision D4 call for voice replies to users who send voice notes.
Inbound speech works; outbound is text only. For a user with poor eyesight this
is most of the value missing.
**Fix:** TTS behind the swappable interface, OGG/Opus out (not a file
attachment), with the phrase-bank caching in §9.

### PR-9 · No real eval corpus — every STT number so far is synthetic
Entity accuracy was measured on **TTS-generated speech**, not on real elders.
Synthetic audio is cleaner and differently distorted than a 70-year-old on a bad
line with a television on. R1 is the product risk and it is currently unmeasured
against reality.
**Fix:** PRD §15's corpus — 50–100 real voice notes per language, hand
transcribed, deliberately including the messy ones. Build it before trusting any
accuracy claim.

### PR-11 · Template names burned
`reminder_fire` and `reminder_nudge` were deleted to fix their category. Meta
holds a deleted name for up to four weeks. Live templates are `_v2`.
**Fix:** nothing to do but wait; recorded so nobody wonders why the names are
odd. See `LANDMINES.md`.

### PR-12 · No log retention
Everything is `journalctl` on one box. Logs die with the instance, and there is
no way to answer "what did we send this user last Tuesday" after a rebuild.
**Fix:** ship logs off-box. The `messages` table is the product record, but
operational logs are not backed up at all.

### PR-22 · The runtime box can push to `main` on both remotes
`gh` and `glab` were authenticated on `i-01b2c27883acb25ca` on 2026-07-27
(operator instruction, lane OPS-1). GitHub scopes `gist, read:org, repo,
workflow` give repo permissions `admin/maintain/push`; the GitLab OAuth grant
carries `write_repository` + `api` at group access level 50 (Owner). Both are
wired into git as credential helpers.

So the **internet-facing** box now holds write access to the source of truth for
a product it also runs. It has no signing key, so anything it pushed would break
`CONTRIBUTING.md:44` (`%G?` must be `G`) — meaning the realistic failure is not
an honest mistake but a compromise of the tunnel-exposed box turning into a
push to `main`.

Filed P1 rather than P0 because deploys are still manual from the dev box, so a
pushed commit does not reach users on its own. Upgrade it if that stops being
true.
**Fix:** decide whether the runtime box keeps write access or is reduced to
read-only (a token with `read_api` / `read_repository` and no `repo` scope).
Tracked as `CRED-1` on `control-plane/ACTIVE_LANE_BOARD.md`.

### PR-23 · Forwarded text can still trigger deterministic state changes
`provenance.py` correctly treats forwarded, quoted, image, and document text as
relayed content: it fences the text for the agent and withholds mutating tools.
But deterministic commands run before the agent capability and do not check
provenance. A forwarded message whose body is exactly `stop`, `clear chat`, or a
matching Hinglish command can still pause the user or clear their conversation
without the user authoring that instruction.

This is narrower than the already-resolved forwarded-tool-call risk, because it
does not reach the LLM tool loop. It is still a security boundary failure: the
product rule is that relayed content may be read, explained, or warned about,
but must not be obeyed.

**Fix:** make the deterministic command capability provenance-aware. Relayed
content should be summarized or warned about, not routed to state-changing
commands; interactive button payloads can remain trusted because the user
pressed a first-party control.

### PR-25 · Deploy restarts services even when a migration fails
`ops/deploy.sh` runs every migration with `psql -v ON_ERROR_STOP=1`, but the
loop masks a nonzero exit with `|| echo ... FAILED`. The script then continues
to install the artifact and restart `saathi-web` and `saathi-worker`.

That is fail-open at the deployment boundary: code can be rolled forward against
an incomplete schema. For this product, the realistic impact is silent breakage
of reminder delivery, safety-event writes, onboarding/consent state, or erasure
paths rather than a clean failed deploy.

**Fix:** make any failed migration abort the deploy before service restart. Keep
the migration output visible, but do not consume the nonzero exit status.

### PR-26 · Inbound PDFs have no size or concurrency limit before parsing
A valid WhatsApp sender can send a document, and the webhook detaches processing
with `asyncio.create_task`. The PDF branch downloads the media blob, runs
`pypdf` over the in-memory bytes, and may write/rasterise the full PDF with
`pdftoppm`. The 5 MiB guard in the vision path is too late to protect this
branch.

With default open onboarding, repeated large or expensive PDFs can burn memory,
CPU, disk, and worker/event-loop capacity, degrading normal message handling and
safety-sensitive reminder work.

**Fix:** add explicit media byte limits, PDF parser/rasterisation resource
limits, and an application-level concurrency/backpressure guard before parsing
or spawning document work.

---

## P2 — before scale

### SEC-2 reservation note
PR-23 was held for lane SEC-2 during concurrent DOC-1 work. SEC-2 consumed it
above for the forwarded-text deterministic-command finding.

### PR-24 · SSH is open to the operator's Mac
`sg-0f805961424175e66` permits TCP 22 from `207.219.25.137/32` — a single
residential IP — and `sshd` accepts one ED25519 key with
`passwordauthentication no`. Correct for a dev box operated by one person, and
genuinely narrow.

It is recorded because **three docs claimed the opposite for a day** (`README.md`,
`ARCHITECTURE.md`, `RUNBOOK.md` all said no inbound port was open / zero inbound
rules), and because it is a real attack surface that the tunnel-only story hides:
Cloudflare fronts `:3130`, but it does not front `:22`.
**Fix before production:** SSM Session Manager only, and drop the rule. That was
the original design; SSH was added for convenience and the docs never caught up.

### PR-13 · Cloudflare token is IP-locked to the EIP
`saathi-box-canonical` is locked to `15.252.75.191/32`. Correct, and it means
**changing the EIP silently breaks the box's Cloudflare access**.

### PR-14 · No secret rotation story
Secrets Manager holds them and the box fetches them, which is right. But nothing
rotates, and the WhatsApp token never expires by design.

### PR-15 · No rate limiting beyond admission
Admission control stops unknown handles cheaply, but an *onboarded* user can
send unlimited voice notes, each costing STT minutes and a model turn. §14 caps
free-tier STT minutes; nothing enforces it.

### PR-17 · Training corpus produces nothing until 5 users overlap
By design (k-anonymity), but it means the learning loop is unmeasurable during
internal testing and will look broken to anyone who does not know why.

### PR-18 · Onboarding consent version is hardcoded
`CONSENT_VERSION = "2026-07-26.v1"` in two modules. When the policy text
changes, nothing forces a re-consent or notices the drift.

---

## Resolved

| Was | Resolved |
|---|---|
| No backups at all | 2026-07-26 — 6-hourly dump, **verified by restoring into a scratch DB before it counts as success**, encrypted to S3, versioned, 90-day expiry. Recovery drill from S3 restored 16 tables, 8 enums, 33 indexes, schema identical to live. |
| Webhook unreachable by Meta | 2026-07-26 — tunnel, signature verification, callback registered, all four templates APPROVED as UTILITY. |
| Anyone messaging us got a free model turn | 2026-07-26 — onboarding is deterministic and model-free, so an open door costs templated replies and nothing else. |
| Forwarded messages could drive tool calls | 2026-07-26 — `provenance.py`; state-mutating tools withheld on relayed content. |
| Secrets could leak into logs | 2026-07-26 — `net_policy.RedactingFilter` on the root logger in both entrypoints. |
| Privacy policy claimed 7-day voice retention that did not exist | 2026-07-26 — retention now real and the promise is kept by an **S3 lifecycle rule**, not by our code: if every worker died, voice notes would still expire on day 7. Kept deliberately because India is not one language and a transcript alone cannot tell you whether the model mis-heard or the speaker used a regional form. Erasure deletes objects immediately rather than waiting for the rule. |
| Search ran on MeshPilot's Gemini key, on a global endpoint (was PR-21) | 2026-07-26 — Saathi's own GCP project `saathi-ai-503623` with its own service account, billing linked, and search served from **Vertex asia-south1**. The service account reaches the box via Secrets Manager, never SSM. AI Studio remains a fallback so an unpaid project or a bad key file cannot cost a user their answer. |
| Scheduler was reminder-shaped (was PR-16) | 2026-07-26 — `scheduled_turns` is a general queue; kinds register. Worker reports `['checkin', 'media_purge', 'nudge', 'reminder']` and a test asserts it names none of them. |

### PR-20 · Google's search index is global, even when the request is not
Search now runs on **Vertex AI in `asia-south1` (Mumbai)**, so the request is
served from India like everything else. What cannot be regionalised is Google's
index itself — the crawl is global, and the query reaches Google.

That is as good as this gets without building an index, and it is a meaningful
improvement on the AI Studio global endpoint. But "is this medicine safe with
that one" is still a health-adjacent query leaving our control.
**Fix:** state it plainly in the privacy policy, and keep `look_up` narrow.

### PR-19 · Audio retention has no consent toggle
Voice notes are now stored for 7 days for debugging, which onboarding consent
and the privacy policy both cover. But there is no per-user opt-out short of
declining the service, and no way to say "keep my transcripts, not my voice".
**Fix:** a preference, once there is evidence anyone wants it. Recorded so the
absence is deliberate rather than forgotten.
