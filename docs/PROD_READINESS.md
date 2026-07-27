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

### PR-3 · No alerting on anything
A failed backup, a dead worker, a Postgres that stopped, a webhook returning 500
— all silent until someone looks. The backup timer logs to `journalctl` and
nobody reads `journalctl`.
**Fix:** at minimum, backup failure and `saathi-worker` inactive → an alert that
reaches a human. CloudWatch alarms on the instance plus a heartbeat from the
worker would cover the realistic failures.

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

---

## P2 — before scale

### PR-23 · reserved for lane SEC-2 (Codex security review)
Held so two concurrent sessions cannot claim the same id. If SEC-2 closes without
needing it, leave the gap — renumbering a journal is worse than a hole in it.

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
