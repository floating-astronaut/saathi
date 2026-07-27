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

### PR-4 · Reminders had no delivery guarantee — resolved 2026-07-28
The original row understated it. Reminders were not merely unguaranteed, they
were **never dispatched**: `_create_reminder` wrote to `reminder_fires`, the
worker read only `scheduled_turns`, and `worker/reminder_scheduler.py` — the
sole reader of `reminder_fires` — was referenced nowhere in the repo. Latent
rather than live, because no real reminder had been created yet.

**Resolved:** creation now enqueues onto `scheduled_turns`; recurring reminders
book their next occurrence; a deliberate no-send (paused user, no active handle)
is marked `skipped`; and `scheduling.sweep_stuck` reclaims turns claimed but
never sent. Proven end to end against the live database, not only against fakes.

**Alerting resolved** 2026-07-27 (PR-3) — a stopped worker now pages a human,
proven by inducing the outage. **Acknowledgement resolved** 2026-07-28 (PR-4b) —
a fired reminder now carries per-message payloads, the tap reaches the
deterministic handler, and an unacknowledged reminder books a nudge.

The loop is closed end to end: created → enqueued → dispatched → acknowledged or
nudged → rescheduled, with a sweep for turns abandoned mid-flight. What remains
is not a gap in the machinery but the absence of real users to run through it.

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

### PR-23 · Forwarded text could trigger deterministic state changes — RESOLVED 2026-07-27
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

**Worse than first reported.** STOP matches `\bunsubscribe\b` as a *substring*,
and nearly every forwarded marketing message carries that word in its footer.
`STOP` sets `users.paused = true`, and `worker/turns._handle` silently declines
to send reminders to a paused user. So a relative forwarding an advert stopped
someone's medication reminders indefinitely — no error, no bounce, and with the
ack path unreachable (PR-4b) nothing to reveal it. No attacker required.

**Resolved:** the priority-22 matcher now requires `c.trusted`. Relayed text
falls through to the agent, which already fences it and withholds mutating
tools, so it is still read and explained — just never obeyed. Priorities 20/21
stay unguarded because they key on `button_id`, and a tap is a first-party
control. Onboarding (10) is deliberately **not** guarded: gating it would drop
an un-onboarded user to the agent and break "onboarding never calls the model".
Regression cover in `tests/test_relayed_commands.py`, verified to fail without
the guard.


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

### PR-27 · The runtime box can now rewrite Secrets Manager
`secretsmanager:PutSecretValue` (and `DescribeSecret`) were attached to
`saathi-dev-box` on 2026-07-27 so CallerDesk keys could be stored from the box.

Reading the 13 secrets was already a confidentiality exposure if the box is
compromised. Writing is an **integrity** one, and worse in a way that matters: a
credential quietly repointed at an attacker's endpoint is far harder to notice
than one stolen. The box is the internet-facing machine.

**Fix:** drop back to read-only once CallerDesk is wired. If the grant was
`secretsmanager:*` rather than `PutSecretValue` on that one resource ARN, narrow
it now — this needed exactly one action on one secret. Related: PR-22.

### PR-28 · `ops/deploy.sh` cannot be run from the runtime box
It is written to run on the **dev box** and reach in over SSM: it exports
`AWS_PROFILE=mp-dev` and calls `ssm send-command`. On the runtime box neither
exists — `ssm:SendCommand` is denied to `saathi-dev-box` (correctly), and there
is no `mp-dev` profile.

So an agent working on the runtime box cannot deploy, even though it is standing
on the target. The 2026-07-27 deploy of `117896b` was done by copying the four
changed modules into `/home/ubuntu/saathi` by hand, then `uv sync`, `pytest`,
`systemctl restart`, and the same verification block `deploy.sh` runs. That is
exactly the hand-rolling `CONTRIBUTING.md` warns against, done knowingly because
the alternative was leaving a live forwarded-command vulnerability in place.

**Fix:** either give `deploy.sh` a local mode that skips the S3/SSM transport
when it is already on the target, or make deploying a dev-box-only action and
say so in `CONTRIBUTING.md` instead of implying any session can run it.

### PR-25 · Deploy restarts services even when a migration fails — RESOLVED 2026-07-27
Confirmed in detail 2026-07-27 while reading the script. `remote.sh` runs with
`set -uo pipefail` — **no `-e`** — and the migration loop was:

    su - ubuntu -c "psql ... -f $m" >/dev/null 2>&1 \
      && echo "  migration ok" || echo "  migration FAILED"

Three separate problems: the failure did not stop the run, **stderr was
discarded** so the reason was never seen, and `systemctl restart` executed
regardless. Services then run against a schema they do not match.

**The row's second paragraph was too kind, and that turned out to be the worse
half.** It said the migrations "rely on being idempotent". Two of them are not,
and re-running them is not a no-op — it is a silent state change on live rows:

- `003_admission_control.sql` ends with
  `update user_channels set status = 'active' where status = 'pending';`
- `005_onboarding.sql` ends with
  `update users set onboarding = 'done' where onboarding = 'new' and created_at < now();`

Both were correct *once*, as backfills for rows that predated the feature. Run
again they admit every pending unknown sender and mark every half-onboarded
user as consented. The old loop ran them on **every deploy**. Measured, not
inferred: a schema-only copy of the live database plus one pending channel and
one `onboarding='new'` user, run through the old loop, came out `done / active`
— all six migrations reporting "ok".

**Fixed.** `ops/deploy.sh`:

- `ON_ERROR_STOP=1` was already passed; psql's stderr is no longer thrown away,
  so the actual error text appears in the deploy log next to the failure.
- Any failure — bad DSN, ledger unavailable, migration error, ledger write
  error, checksum mismatch — prints `MIGRATION ABORT` and `exit 1` **before**
  `systemctl restart`. Nothing restarts against a schema it does not match.
- A `schema_migrations` ledger (`db/schema_migrations.sql`) records
  `version, checksum, applied_at, origin, note`. Version is the filename;
  checksum is the sha256 of the file as applied. An already-recorded migration
  is skipped, and a recorded migration whose file has since changed aborts the
  deploy rather than being silently skipped.
- The six migrations already on the box are **baselined, not asserted**: each
  is claimed only if a sentinel object that exists if and only if that file
  committed is visible right now (`user_channels`, `user_channels.status`,
  `training_samples`, `users.onboarding`, `scheduled_turns`, and
  `safety_events_trigger_check` admitting `hypoglycemia`). Each migration file
  is a single `begin/commit`, so a visible sentinel means the whole file
  committed. Baselined rows carry `origin='baselined'` and a **NULL checksum**,
  because nobody watched them run and we will not pretend to know the bytes.

Verified against scratch databases on the box (dropped afterwards; the live
database was only ever read, via `pg_dump --schema-only`): fresh bootstrap
applies all six and records them; a second run applies none; a pre-ledger fully
migrated database baselines all six and leaves the canary rows above at
`new / pending`; a *partially* migrated pre-ledger database baselines only
002–004 and applies 005–007; an edited migration aborts with the two checksums
printed; an injected failing migration prints the psql error, aborts, records
nothing, and never reaches the restart.

**Residuals, deliberately left open:**

- **The ledger write is not in the migration's transaction.** Each migration
  file ends with its own `commit;`, so recording it is a second statement. A
  crash in that window leaves a migration applied but unrecorded, and the next
  deploy will try it again. No worse than today's behaviour, and now loud for
  the non-idempotent ones — but it is a window.
- **Baselined rows cannot be checksum-checked**, by construction. An edit to
  002–007 will therefore never be caught on the ap-south-1 box, only on a
  database that saw them applied. This decays on its own as new migrations
  arrive.
- **A deploy still restarts when the on-box test run fails.** Same missing `-e`,
  same shape, different line — `uv run pytest -q | tail -2` cannot fail the
  script. Out of scope for this change and left as-is rather than fixed
  silently.
- The ledger is deploy bookkeeping, so `db/schema_migrations.sql` is not itself
  a migration; a database bootstrapped by hand from `README.md` gets its ledger
  on the first deploy, via the baseline.

### PR-29 · Vobiz briefly received every inbound WhatsApp message
Completing Vobiz's embedded-signup flow subscribed their app
(`1247920013487973`) to WABA `1687148075730227`'s webhooks, alongside ours. For
the window it was in place, every inbound message on the Saathi number — voice
notes, prescription photos, medicine names — was delivered to a third party.

Nobody decided this; it is what `featureType: only_waba_sharing` does. It sits
badly against the rest of the privacy design, which goes to real lengths:
inference kept inside India on regional endpoints, narrow pre-storage redaction,
7-day voice retention enforced by S3 lifecycle rather than our code, a
k-anonymised opt-in corpus. A silent third-party copy of raw message content is
a larger exposure than anything those controls address, and under DPDP it is a
processor relationship requiring a basis and a contract.

**Removed 2026-07-27** — `subscribed_apps` on that WABA now lists our app only.
No real users existed during the window, so no user data was actually disclosed.

**Standing risk:** re-running any Vobiz connect flow re-subscribes them.
`DELETE /{waba}/subscribed_apps` removes the app tied to the *access token*, so
our token can only unsubscribe **us** — removal must be done in WhatsApp Manager.
**Fix:** check `subscribed_apps` after any change on the Vobiz side, the same way
`LANDMINES.md` says to check it after any Business Manager change.

### PR-30 · Templates on the new WABA are unreviewed, and the app is already on it
`.env` now points at the Indian number, but the four templates were re-submitted
on the new WABA on 2026-07-27 and are `PENDING`. Until they are APPROVED,
**every reminder, nudge and check-in will fail** — the send path needs a template
outside the 24-hour window.

Acceptable only because no real reminders exist. Both `scheduled_turns` and
`reminder_fires` are empty.
**Fix:** confirm all four are APPROVED before a single real user is onboarded.
Templates do not migrate between WABAs; the old WABA's four remain approved and
unused.

### PR-31 · Onboarding messages were never recorded — RESOLVED 2026-07-27
`pipeline.py` and `worker/send_reminder.py` both insert outbound sends into
`messages`. **`onboarding.py` does not.** Proven on the first real conversation
(2026-07-27): the user's "Hii" was recorded, the onboarding reply the user
visibly received was not — `messages` held 1 inbound, 0 outbound.

`messages` is described elsewhere as *the product record*, and it is the thing
the 6-hourly backup actually protects. So the entire onboarding exchange — the
first thing every user ever sees — is outside it.

The sharp edge is **consent**. Consent is captured during onboarding. The `users`
row keeps `consent_at` and `consent_version`, but not the text that was shown. If
a user or a regulator asks *what exactly were they told and when*, the answer is
reconstructed from a hardcoded string in a source file at some past commit, not
from a record. `CONSENT_VERSION` is also hardcoded in two modules (PR-18), so the
drift risk compounds.
**Resolved** by recording at `wa/client._send` — the single wire path — rather
than in the onboarding path. Fixing only onboarding would have left the next send
helper free to make the same omission; every caller reaching WhatsApp goes
through `_send`, so recording there cannot be forgotten. `kind`, `body_text` and
`template_name` are derived from the wire payload, not passed in, for the same
reason.

Recording never raises: the message has already gone out, and failing the caller
would invite a resend of something the user has read. A failure logs at ERROR.
`on conflict (wa_message_id) do nothing` absorbs `pipeline`'s existing insert.

Cover in `tests/test_outbound_record.py` (8), including one that fails if `_send`
stops calling the recorder — the others exercise it directly and would stay green
if the call were deleted.

### PR-33 · D-D's model bakeoff was eight utterances
D-D chose `zai.glm-5` — the model Saathi runs on, at roughly a 60% cost premium
over the runner-up — on **8 code-mixed reminder utterances**:

    zai.glm-5      8/8 time, 8/8 drug     ~₹220/user/mo est
    deepseek.v3.2  7/8, 7/8               ~₹135
    zai.glm-4.7    6/8, 8/8               ~₹133
    qwen3-235b     4/8, 8/8               ~₹48
    glm-4.7-flash  3/8, 8/8               ~₹16

The gap between 8/8 and 7/8 is **one sentence**. At n=8 the confidence intervals
on the top two overlap almost entirely; a single differently-mumbled `saade`
flips the ranking. For comparison, `search-benchmarks` grades 100 tasks per cell
and still declines to name a winner among its leaders because the intervals
overlap.

**This does not make D-D wrong.** The 3/8 versus 8/8 gap is almost certainly
real, and the reasoning — that Hindi fractional time words are where a missed
dose comes from — is sound. What is thin is the evidence separating **glm-5 from
deepseek**, and that difference is currently justifying the premium.

It matters now because AI-1 makes model routing configurable. The moment routing
is a config value, "is glm-5 actually better than the ₹135 option" becomes a
question someone will ask, and today the honest answer is "we measured eight
sentences."
**Fix:** fold into PR-9. Re-run the bakeoff on the real elder corpus, scored on
D-D's metric (times and medicine names, not WER), reported with confidence
intervals. See `PATTERNS_TO_BORROW.md` on the harness shape.

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

### PR-32 · Language is asked once and never revisited — RESOLVED 2026-07-28
Onboarding asks Hindi or English, stores it in `users.lang_pref`, and there is no
way to change it afterwards — no `/language` command, and nothing in the copy
says it is changeable. A user who taps the wrong button on first contact is stuck
in the wrong language, and the person most likely to mistap is the one this
product is for.

Also: `lang_pref` is free text with an old default of `'hi-en'`. Users created
before 2026-07-28 carry that value; `_lang()` maps anything unrecognised to Hindi,
so they get Hindi rather than an error. Fine, but it means the column now holds
two vocabularies.
**Resolved.** `/language` (also `bhasha`, "change language", "switch to
english", "english mein baat karo") re-offers the same two buttons, and is
registered with WhatsApp so it appears in the `/` menu.

Two things found while fixing it:

- **Changing language would have un-onboarded the user.** `ob:lang:*` routed
  straight into `_welcome`, which sets `onboarding = 'consent'` — so an elder who
  only wanted English would have been sent back through the consent flow. Guarded
  on `onboarding = 'done'`.
- **Every command reply was still bilingual.** Onboarding stopped saying things
  twice; `/stop`, `/resume`, `/clear` and the rest did not, so a user who chose
  English still got a Hindi paragraph. Same complaint, later in the journey. Now
  localised via `CMD_COPY`.

`lang_pref` still holds the legacy `'hi-en'` for users created before
2026-07-28; `_lang()` maps anything unrecognised to Hindi. Whether `hi-en` is
retired or kept as a third option is still undecided.

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
