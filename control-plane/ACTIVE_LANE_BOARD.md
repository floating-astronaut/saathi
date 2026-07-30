# Active Lane Board

> The single live queue. Every lane lives here and moves through states. This is
> the assignment surface — agents claim, work, and close lanes here. **If the
> board and reality disagree, fix the board.**
>
> Format and rules: `docs/LANE_LIFECYCLE.md`. Coordination: `docs/AGENT_SYNC_PROTOCOL.md`.

States: `OPEN` · `CLAIMED` · `IN PROGRESS` · `IN VERIFICATION` · `CLOSED`

**This board replaces the `### Queued` blocks in `docs/ENGINEERING_SUPERVISOR.md`.**
That log is append-only evidence of what closed; it cannot represent a queue,
because nothing in it is ever struck off. Queued items from the last two
supervisor entries were migrated here on 2026-07-27.

## Lane format

```
### <ID> — <title>                          [STATE]
Owner: <agent | unassigned>      Opened: <date>
Reading: <docs to read before code>
Acceptance: <verifiable definition of done>
Write-back: <docs to update on close>
Notes: <decisions, blockers, handoff hints>
```

---

## Active

### LEDGER-2 — vendor usage hooks and staged STT enforcement   [CLOSED]
Owner: Codex (source branches `agent/llm-usage-accounting`, `agent/ledger-stt-enforcement`)        Opened: 2026-07-29 · Closed: 2026-07-29
Reading: docs/USAGE_LEDGER.md §11, docs/AI_ROUTING.md, docs/ARCHITECTURE.md, docs/PROD_READINESS.md PR-15, saathi/agent/loop.py, saathi/openrouter.py, saathi/capabilities.py, saathi/usage.py
Acceptance: each direct Bedrock/OpenRouter LLM request emits exactly one content-free usage event with actual reported tokens and latency; successful Sarvam STT and WhatsApp template calls emit content-free usage events; Sarvam STT can reserve before vendor spend and refuse before Sarvam when the explicit enforcement flag, enforce mode and a positive approved INR cap are all set; default runtime behavior remains observe-only; focused/full tests pass.
Write-back: docs/USAGE_LEDGER.md, docs/AI_ROUTING.md, docs/ARCHITECTURE.md, docs/PROD_READINESS.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. PR #29 deployed LLM usage events; PR #30 added STT/template observe-only events; PR #31 added Sarvam pricing; PR #32 (`aacd5af`) added disabled-by-default STT pre-call reservations and cap refusal. Deploy verified 577 tests, active web/worker/tunnel/PostgreSQL, localhost/public health 200 and unsigned webhook 403. Remaining PR-15 work is LLM/template/global vendor cap enforcement unless the operator narrows the requirement to STT-only.

### LEDGER-1 — vendor usage ledger foundation   [CLOSED]
Owner: Codex (source branch `agent/vendor-ledger-foundation`)        Opened: 2026-07-29 · Closed: 2026-07-29
Reading: docs/USAGE_LEDGER.md §11, docs/ARCHITECTURE.md, docs/PROD_READINESS.md (PR-15), db/migrations/, saathi/config.py, saathi/worker/__main__.py
Acceptance: append-only vendor usage events plus idempotent atomic reservation, settlement, release and expiry APIs; observe-only default; fake-connection concurrency tests; no paid-call behavior changes.
Write-back: docs/USAGE_LEDGER.md, docs/ARCHITECTURE.md, docs/PROD_READINESS.md, docs/RUNBOOK.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. PR #27 (`b71a849`) deployed migration 015; 569 tests and live schema/services/health checks passed. Observe-only by design: per-vendor hooks and enforcement remain later slices.

### RATE-1 — bound inbound turn concurrency   [CLOSED]
Owner: Codex (source branch `agent/rate-limit-admission`)        Opened: 2026-07-29 · Closed: 2026-07-29
Reading: docs/DOC_SYSTEM.md, docs/AGENT_SYNC_PROTOCOL.md, docs/ARCHITECTURE.md, docs/PROD_READINESS.md (PR-15, PR-26), docs/USAGE_LEDGER.md, saathi/pipeline.py, saathi/core/backpressure.py, saathi/web/app.py
Acceptance: no more than the configured number of inbound turns may execute in one web process at once; an over-cap valid sender receives at most one quiet retry-later notice during the configured cooldown; no turn is queued, and safety/onboarding/media/model work remains inside the bound.
Write-back: docs/ARCHITECTURE.md, docs/PROD_READINESS.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. Default cap is 8 process-local turns; overload refuses rather than queues, sends one quiet bilingual notice per 10-minute reason cooldown, and does not consume a user's quota. Deployed at `ac0a493`; migration 013 and health/service checks verified live.

### RATE-2 — persistent per-user inbound sliding window   [CLOSED]
Owner: Codex (source branch `agent/rate-limit-admission`)        Opened: 2026-07-29 · Closed: 2026-07-29
Reading: docs/DOC_SYSTEM.md, docs/AGENT_SYNC_PROTOCOL.md, docs/ARCHITECTURE.md, docs/PROD_READINESS.md (PR-15), docs/USAGE_LEDGER.md, db/schema.sql, db/migrations/, saathi/pipeline.py
Acceptance: a Postgres-backed atomic reservation before transcription or dispatch limits one user across text, voice, images and documents; concurrent requests cannot over-admit; one rate-limit notice is sent per cooldown and later requests stay silent; duplicates do not consume quota; focused and full suites pass.
Write-back: docs/ARCHITECTURE.md, docs/PROD_READINESS.md, docs/USAGE_LEDGER.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. Postgres admission reservations apply before STT/dispatch across all modalities: 6 per user per rolling 60 seconds, serialized with a non-blocking advisory lock. Duplicates consume no quota; lock contention/full windows go quiet after one notice. Cross-vendor monetary caps remain the separate `USAGE_LEDGER.md` lane.

### OBS-3 — bind tracing to Pydantic Logfire project   [CLOSED]
Owner: Codex (source branch `agent/logfire-cloud-bind`)        Opened: 2026-07-29 · Closed: 2026-07-29
Reading: docs/DOC_SYSTEM.md, docs/AGENT_SYNC_PROTOCOL.md, docs/ARCHITECTURE.md, docs/DECISIONS.md, docs/RUNBOOK.md, saathi/observability.py, tests/test_observability.py, ops/set-secret.sh
Acceptance: Logfire cloud export is enabled only when `LOGFIRE_TOKEN` is present, keeps `inspect_arguments=False` and the attribute allow-list, preserves local collector export, stores the provided project write token in Secrets Manager value-blind, enables tracing for web/worker, deploys, and verifies without printing secrets.
Write-back: docs/ARCHITECTURE.md, docs/DECISIONS.md, docs/RUNBOOK.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. Runtime secret now has `SAATHI_TRACING_ENABLED=1` and a `LOGFIRE_TOKEN` write token for project `indofolk-ai` (value-blind verified: 55 chars, sha256 prefix recorded by set-secret output only). Code uses `send_to_logfire="if-token-present"`, keeps local collector export, keeps `inspect_arguments=False`, and preserves the scrub allow-list. Focused suite passed: 15. Full suite passed: 536. API key was not stored because app runtime does not need it.

### OBS-2 — tracing follow-up safety and localhost binding   [CLOSED]
Owner: Codex (source branch `agent/fix-obs1-tracing-safety`)        Opened: 2026-07-29 · Closed: 2026-07-29
Reading: docs/DOC_SYSTEM.md, docs/AGENT_SYNC_PROTOCOL.md, docs/ARCHITECTURE.md, docs/RUNBOOK.md, saathi/observability.py, ops/setup-tracing.sh, ops/saathi-otelcol.service, ops/saathi-jaeger.service, tests/test_observability.py
Acceptance: tracing spans preserve application exceptions, tracing enter/exit failures degrade to no-op behavior, OTel Collector and Jaeger do not bind the same OTLP port, Jaeger binds localhost only, and focused/full tests pass.
Write-back: docs/RUNBOOK.md, docs/ARCHITECTURE.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. `observability.span()` now preserves application exceptions and swallows tracing enter/exit failures only. Collector receives on `127.0.0.1:4317`; Jaeger OTLP listens on `127.0.0.1:4318`, with no `0.0.0.0` OTLP bind. Focused suite passed: 14. Full suite passed: 535.

### ID-1 — returning WhatsApp handle must not restart onboarding   [CLOSED]
Owner: Codex (source branch `agent/returning-whatsapp-handle-onboarding`)        Opened: 2026-07-28 · Closed: 2026-07-28
Reading: docs/DOC_SYSTEM.md, docs/AGENT_SYNC_PROTOCOL.md, docs/ARCHITECTURE.md, docs/foundations/GLOSSARY.md, saathi/identity.py, saathi/onboarding.py, saathi/capabilities.py, saathi/pipeline.py, tests/test_capabilities.py, tests/test_onboarding.py
Acceptance: once a WhatsApp handle has an onboarded Saathi user, tapping old onboarding/start controls must not create or restart signup, must not mutate `users.onboarding` away from `done`, and must answer with the same user still active; not-yet-onboarded handles still stay on the deterministic onboarding path. The 90-day stale/recycled-number lifecycle is documented as the next identity lane unless fully implemented here.
Write-back: docs/ARCHITECTURE.md, docs/DECISIONS.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. Already-onboarded users pressing old `ob:*` onboarding buttons cannot restart signup or move `users.onboarding` away from `done`; old language buttons still change language. Focused suite passed: 32. Full suite passed: 521. The 90-day stale-handle warning/confirm/move/delete lifecycle remains queued as a separate identity lane.

### LIFE-1c — forwarded content summary asks follow-up   [CLOSED]
Owner: Codex (source branch `agent/forwarded-summary-followup`)        Opened: 2026-07-28 · Closed: 2026-07-28
Reading: docs/DAILY_LIFE_OS.md, saathi/provenance.py, saathi/agent/prompt.py, tests/test_provenance.py, tests/test_lookup.py
Acceptance: forwarded/relayed content replies first skim/summarize the content, flag obvious risk, and then ask the user what they want to do with it in the same turn; mutating tools remain withheld and the follow-up question does not imply action has been taken.
Write-back: docs/DAILY_LIFE_OS.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. Forwarded content now asks the model to skim/summarize, flag risk, extract visible details, then ask what the user wants to do. Mutating tools remain withheld. `uv run pytest -q` passed: 519.

### LIFE-1b — captionless media explains by default   [CLOSED]
Owner: Codex (source branch `agent/captionless-media-explain`)        Opened: 2026-07-28 · Closed: 2026-07-28
Reading: docs/DAILY_LIFE_OS.md, saathi/pipeline.py, saathi/vision.py, tests/test_vision.py, tests/test_media_limits.py
Acceptance: captionless PDFs/images still get an immediate read/explain answer without waiting for a second user message; captionless images use the document/daily-life reading prompt by default, while medicine-specific interpretation remains caption-driven; tests pin the default.
Write-back: docs/DAILY_LIFE_OS.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. Captionless images now default to document/daily-life reading; PDFs already did. Medicine-specific interpretation remains caption-driven. `uv run pytest -q` passed: 519.

### LIFE-0 — WhatsApp daily-life OS roadmap   [CLOSED]
Owner: Codex (source branch `agent/daily-life-os-roadmap`)        Opened: 2026-07-28 · Closed: 2026-07-28
Reading: docs/PRD.md, docs/ARCHITECTURE.md, docs/COMMERCIAL_ACTIONS.md, docs/DECISIONS.md, current capability registry
Acceptance: repo docs state the product frame as a WhatsApp operating system for daily life for non-tech-savvy 40+/elder users; the next capability lanes are explicitly ordered around read/explain, task management, bills/due dates, drafting, scam shield and local errands; commercial handoff remains subordinate to daily-life utility.
Write-back: docs/DOC_SYSTEM.md, docs/PRD.md, docs/DECISIONS.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. `docs/DAILY_LIFE_OS.md` defines the frame; D-Z records the decision; LIFE-1..LIFE-6 are queued as implementation lanes.


### LIFE-1 — read/explain/action from forwarded content   [CLOSED]
Owner: Codex (source branch `agent/forwarded-content-actions`)        Opened: 2026-07-28 · Closed: 2026-07-28
Reading: docs/DAILY_LIFE_OS.md, docs/ARCHITECTURE.md, docs/PRD.md §4-5, saathi/provenance.py, saathi/documents.py, saathi/vision.py, saathi/capabilities.py
Acceptance: forwarded text/image/PDF/SMS-like content is treated as third-party data, summarized in the user's script, flags amount/date/action/scam risk, and offers exactly one safe next step; forwarded content cannot trigger commands or mutating tools.
Write-back: docs/DAILY_LIFE_OS.md, docs/ARCHITECTURE.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md
Notes: MET. Relayed fence/prompt now asks for explanation, amount/date/place/person/action extraction, scam pressure flag and one safe next step. Mutating tools remain withheld. `uv run pytest -q` passed: 518.

### ID-2 — stale WhatsApp handle 90-day lifecycle   [CLOSED]
Owner: Codex (source branch `agent/stale-whatsapp-handle-lifecycle`)        Opened: 2026-07-28 · Claimed/Closed: 2026-07-29
Reading: docs/ARCHITECTURE.md, docs/foundations/GLOSSARY.md, docs/DECISIONS.md (D-AA), saathi/identity.py, saathi/worker/turns.py, db/migrations/, tests/test_identity.py
Acceptance: a handle with no inbound message for the written stale window is nudged before risk, can confirm continued ownership or move the account to a new number, and is revoked/deleted only after 90 days of dead air according to the recorded lifecycle policy.
Write-back: docs/ARCHITECTURE.md, docs/DECISIONS.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md
Notes: MET. Day-60 content-free check-in/re-verification gate, explicit continuation or 15-minute move code, and day-90 revocation landed in PR #22 (`60f20f0`), migration 014 applied, 549 tests and live service/tunnel checks passed.

### LIFE-2 — lightweight daily task manager   [OPEN]
Owner: unassigned        Opened: 2026-07-28
Reading: docs/DAILY_LIFE_OS.md, docs/ARCHITECTURE.md, docs/PRD.md §5, saathi/agent/tools/specs.py, saathi/agent/tools/handlers.py, db/migrations/
Acceptance: user can create/list/mark-done/postpone tasks by natural language; a task may have no due time; reminders can attach to tasks without making every task a reminder.
Write-back: docs/DAILY_LIFE_OS.md, docs/ARCHITECTURE.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md
Notes: Examples: call plumber, send report, follow up, buy later.

### LIFE-3 — bills and due-date extraction   [OPEN]
Owner: unassigned        Opened: 2026-07-28
Reading: docs/DAILY_LIFE_OS.md, docs/COMMERCIAL_ACTIONS.md, docs/ARCHITECTURE.md, saathi/documents.py, saathi/vision.py, saathi/safety/classifier.py
Acceptance: from forwarded SMS/image/PDF, extract biller, amount and due date; offer reminder; warn on scam-shaped payment pressure; never follows payment links server-side.
Write-back: docs/DAILY_LIFE_OS.md, docs/ARCHITECTURE.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md
Notes: Payment remains outside agent; explanation and reminder only.

### LIFE-4 — draft replies and messages   [OPEN]
Owner: unassigned        Opened: 2026-07-28
Reading: docs/DAILY_LIFE_OS.md, docs/PRD.md §6, saathi/agent/prompt.py, tests/test_devanagari.py
Acceptance: user can ask for short WhatsApp-ready drafts in their selected script for family, landlord, doctor, society, office or support messages; no hidden send action is implied.
Write-back: docs/DAILY_LIFE_OS.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md
Notes: Likely prompt/tool surface only; preserve one-question rule.

### CAPI-1 — dispatch conversion events into the Meta CAPI Gateway   [IN PROGRESS]
Owner: Claude        Opened: 2026-07-30
Reading: docs/CAPI_GATEWAY.md, docs/DECISIONS.md, docs/PRD.md §12, saathi/onboarding.py, saathi/metrics.py, saathi/config.py
Acceptance: on onboarding completion, an ad-originated account emits exactly one `LeadSubmitted` CTWA event to the dataset carrying only its captured `ctwa_clid`; the payload provably carries no message/turn content or elder PII; a Graph outage never raises into a turn; organic (no-ctwa_clid) signups and unconfigured DATASET_ID both no-op; focused tests pass.
Write-back: docs/CAPI_GATEWAY.md, docs/DECISIONS.md (new entry for third-party egress), docs/PROD_READINESS.md (privacy-policy line), CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md
Notes: Goal clarified = Click-to-WhatsApp (CTWA) ad attribution. Docs-first increment done (docs/CAPI_GATEWAY.md), grounded in Meta docs (verified 2026-07-30): capture `ctwa_clid` from the inbound `referral` (already in the payload — pipeline never reads it), send a manual CAPI `LeadSubmitted` to `graph.facebook.com/v21.0/{DATASET_ID}/events` with action_source=business_messaging on onboarding completion. Model B (self-reported events) chosen over Model A (Automatic Events API, where Meta runs NLP over elders' threads) — privacy call. The Cloud Run Gateway + bucket are a web-pixel path this flow does not use; recommend teardown. Token + WABA id already in the secret. BLOCKED only on: (1) confirm Model B; (2) the dataset ID from Events Manager. Then code = capture in pipeline.py + saathi/capi.py + onboarding call site.

### LIFE-5 — stronger scam shield   [CLOSED]
Owner: Codex (source branch `agent/stronger-scam-shield`)        Opened: 2026-07-28 · Claimed/Closed: 2026-07-29
Reading: docs/DAILY_LIFE_OS.md, docs/foundations/SAFETY_AND_CLINICAL.md, docs/ARCHITECTURE.md, saathi/safety/classifier.py, tests/test_safety.py
Acceptance: deterministic patterns cover courier/customs/police, electricity-disconnect threats, loan/investment/lottery, fake job/pension, urgent UPI/payment pressure and remote-support app requests; lower-risk suspicious content gets warning plus safe next step.
Write-back: docs/DAILY_LIFE_OS.md, docs/ARCHITECTURE.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md
Notes: MET. Priority-0 `SCAM` and lower-confidence `SUSPICIOUS` patterns cover every listed pressure family; both block the model and give a safe verification path. PR #24 (`a724921`) deployed; 560 tests and live health/webhook probes passed.

### LIFE-6 — local errand and app handoffs   [OPEN]
Owner: unassigned        Opened: 2026-07-28
Reading: docs/DAILY_LIFE_OS.md, docs/COMMERCIAL_ACTIONS.md, saathi/commercial_actions.py, saathi/lookup/web.py, saathi/net_policy.py
Acceptance: local errands produce free/official Google Maps/search/app handoffs for plumber/electrician/shop/clinic/lab/pharmacy and similar India-first tasks; no paid vendor, login, booking, order or checkout.
Write-back: docs/DAILY_LIFE_OS.md, docs/COMMERCIAL_ACTIONS.md, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md
Notes: Builds on CAP-2; requires real phone link checks before claiming app-open behavior.

### CAP-2 — India-first cart and deeplink handoffs   [CLOSED]
Owner: Codex (source branch `agent/india-cart-links`)        Opened: 2026-07-28 · Closed: 2026-07-28
Reading: docs/COMMERCIAL_ACTIONS.md, docs/ARCHITECTURE.md, docs/DECISIONS.md (D-Y), saathi/agent/tools/specs.py, saathi/agent/tools/handlers.py, saathi/agent/prompt.py
Acceptance: `build_cart` returns the plain numbered list plus safe India-first provider handoff links without any checkout/payment/login/account behavior; tests cover URL encoding, provider selection, no forbidden tools, and prompt-injected/search-like item text remaining inert.
Write-back: docs/COMMERCIAL_ACTIONS.md, docs/ARCHITECTURE.md if boundary changes, CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. `build_cart` returns a numbered list plus India-first provider handoff links through pure URL builders; no paid vendor adapters or transactional surfaces. `uv run pytest -q` passed: 516.

### CAP-1 — commercial deeplinks and internet action capabilities   [CLOSED]
Owner: Codex (source branch `agent/commercial-deeplinks-research`)        Opened: 2026-07-28 · Closed: 2026-07-28
Reading: docs/PRD.md §4-5, docs/ARCHITECTURE.md, docs/DECISIONS.md (D-C, D-E), docs/PROD_READINESS.md, docs/AI_ROUTING.md, current vendor/web research
Acceptance: Saathi has a durable architecture/product contract for shopping, cart-building, flights, movie tickets and similar internet capabilities: allowed outcomes stop at shortlist/list/deeplink/cart draft, forbidden outcomes still include purchase, payment, OTP, credentials, logged-in account automation or hidden third-party actions; implementation sequencing and verification rules are recorded for future agents.
Write-back: docs/DOC_SYSTEM.md, docs/ARCHITECTURE.md, docs/DECISIONS.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: MET. Research captured in `docs/COMMERCIAL_ACTIONS.md`; D-Y records that commercial internet actions stop at visible shortlist/list/deeplink/cart draft. Code follows only after this contract.

### FLOW-1 — agents land work through PRs before deploy   [CLOSED]
Owner: Codex (runtime box)        Opened: 2026-07-28 · Closed: 2026-07-28
Reading: docs/THE_METHOD.md, docs/AGENT_SYNC_PROTOCOL.md, CONTRIBUTING.md, docs/RUNBOOK.md
Acceptance: repo rules say agents author on `agent/<task>` branches, open GitHub
  PRs into `main`, inspect/merge them themselves when acceptance is met, then
  deploy merged `main`; `/home/ubuntu/saathi` remains runtime artifact only.
Write-back: AGENTS.md, CLAUDE.md, KIMI.md, CONTRIBUTING.md, docs/THE_METHOD.md,
  docs/AGENT_SYNC_PROTOCOL.md, docs/RUNBOOK.md, docs/DOC_SYSTEM.md,
  control-plane/SESSION_COORDINATION.md, docs/ENGINEERING_SUPERVISOR.md
Notes: operator decision 2026-07-28: PR flow is preferred even as a single dev,
  but agents should run the loop end to end rather than waiting on the operator.

### DOC-1 — three docs claim no inbound port is open; SSH is open   [CLOSED]
Owner: Claude (runtime box)        Opened: 2026-07-27 · Closed: 2026-07-27
Reading: docs/RUNBOOK.md, docs/ARCHITECTURE.md, docs/PROD_READINESS.md
Acceptance: `README.md:99`, `docs/ARCHITECTURE.md:19` and `docs/RUNBOOK.md:12`
  describe the real ingress (SSH/22 restricted to the operator's Mac,
  `207.219.25.137/32`, plus the Cloudflare tunnel); a PROD_READINESS row records
  the exposure with a severity.
Write-back: README.md, docs/ARCHITECTURE.md, docs/RUNBOOK.md, docs/PROD_READINESS.md
Notes: measured 2026-07-27 — `sshd` listens on `0.0.0.0:22` and an SSH handshake
  from the operator's Mac reaches it (`Permission denied (publickey)` proves TCP
  + banner exchange, so the security group permits 22). `RUNBOOK.md:12` calls
  `sg-0f805961424175e66` "zero inbound rules", which is false. The SG itself
  Resolved once the IAM grant landed: `sg-0f805961424175e66` (`saathi-dev`) has
  **exactly one** ingress rule — TCP 22 from `207.219.25.137/32`, described
  "operator Mac SSH dev only" — and it is the only SG on the instance. Four
  claims corrected, not three: `RUNBOOK.md`'s *Access* row also said "No SSH key
  exists; port 22 was never opened." Recorded as PR-24. PR-23 held for SEC-2.
  **Under `docs/LANE_LIFECYCLE.md` §5 the lane that opened SSH is still OPEN, not
  closed: it changed infrastructure and never wrote back.**

### CRED-1 — runtime box retains forge write credentials by decision   [CLOSED]
Owner: Codex        Opened: 2026-07-27 · Closed: 2026-07-29
Reading: docs/PROD_READINESS.md, CONTRIBUTING.md, docs/DECISIONS.md
Acceptance: a PROD_READINESS row exists for the credential surface; a decision
  is recorded on whether the runtime box keeps forge write access or is reduced
  to read-only.
Write-back: docs/PROD_READINESS.md, docs/DECISIONS.md, docs/RUNBOOK.md
Notes: `gh` 2.46.0 and `glab` 1.53.0 installed on `i-01b2c27883acb25ca` and
  authenticated as `floating-astronaut` (operator instruction, 2026-07-27).
  GitHub scopes `gist, read:org, repo, workflow` → repo permissions
  `admin/maintain/push`. GitLab OAuth scopes `openid profile read_user
  write_repository api` → group access level 50 (Owner). Both wired into git as
  credential helpers, so the internet-facing runtime box can now push to `main`
  on both remotes. It has **no signing key**, so anything it pushed would violate
  `CONTRIBUTING.md:44`. Read access is proven; write is authorised but untested.

  **Untested no longer — 2026-07-27 evening.** 51 commits and 4 `--local`
  deploys were authored, pushed and shipped from this box in one day. The
  signing half of the concern is settled and was never a violation: D-L records
  the operator's decision that signing is cosmetic for a single-author repo, and
  `CONTRIBUTING.md:61` already said runtime-box commits are unsigned by
  necessity.

  **The credential half is not settled and is now larger, not smaller.** An
  internet-facing box that runs the product also holds GitHub `repo` and GitLab
  Owner (level 50) on both remotes, and has demonstrated it can push to `main`
  unattended. The acceptance criterion above — a recorded decision on whether it
  keeps write access or drops to read-only — is still unmet. Deciding it by
  continuing to use it is how the question stops being asked.

  2026-07-29 reliability update: GitLab mirroring now uses a dedicated SSH key
  (`gitlab-saathi`, `/home/ubuntu/.ssh/saathi_gitlab_ed25519`, public key title
  `saathi runtime ip-172-31-32-37 2026-07-29`, expires 2027-07-29) instead of
  the brittle HTTPS/OAuth helper path. This fixes sync reliability, not the
  underlying forge-write-credentials risk.

  **MET — operator decision D-AC:** retain runtime write access as mirror
  authority. Saathi app processes do not execute from a forge; the residual risk
  is future app deploy/source integrity and immediate Cloudflare Pages `site`
  integrity. Revisit on exposure or contributor-model change.

### SEC-1 — Meta Business Agent responder guard   [CLOSED]
Owner: Codex (source branch `agent/meta-subscription-guard`)        Opened: 2026-07-26 · Closed: 2026-07-29
Reading: docs/LANDMINES.md, docs/PROD_READINESS.md (PR-6), docs/DECISIONS.md (D-E)
Acceptance: app `1143680903703001` is unsubscribed from WABA `1023945910495878`,
  **or** a dated decision records that it stays with `rollout.enabled = false`
  plus a check that alerts if the flag flips.
Write-back: docs/DECISIONS.md, docs/PROD_READINESS.md, docs/LANDMINES.md
Notes: MET. D-E rejects Meta Business Agent. The hourly timer verifies Saathi's
  own `whatsapp_business_account/messages` subscription and rejects non-empty
  Agent settings; first live run passed at 2026-07-29T11:20Z. The WABA list
  endpoint remains supplementary because it returned empty after subscribe POST.

### SEC-2 — security review   [CLOSED]
Owner: Codex        Opened: 2026-07-27 · Closed: 2026-07-27
Reading: docs/ARCHITECTURE.md, docs/PROD_READINESS.md, docs/LANDMINES.md, docs/DECISIONS.md
Acceptance: `SECURITY.md` exists at the repo root, registered in
  `docs/DOC_SYSTEM.md`; every finding is either fixed or carries a
  `PROD_READINESS.md` row with a severity. — MET.
  Result: root `SECURITY.md`; doc-map registration; scan report at
  `/tmp/codex-security-scans/saathi-scan/c4b34bab020707c3e4b47103820c43d4225e023a_20260727T012351Z/report.md`; new rows PR-23, PR-25, PR-26.
Write-back: SECURITY.md, docs/DOC_SYSTEM.md, docs/PROD_READINESS.md, docs/ENGINEERING_SUPERVISOR.md
Notes: **Codex owns `SECURITY.md` outright — no other session writes it.**
  Shared surfaces, and how to avoid a collision:
  - `docs/PROD_READINESS.md` — **append new PR-* rows only**; do not renumber or
    reflow existing ones. Next free id is **PR-27** after DOC-1 consumed PR-24 and SEC-2 consumed PR-23, PR-25 and PR-26.
  - `docs/ENGINEERING_SUPERVISOR.md` — append-only, newest at the **bottom**.
  - `control-plane/ACTIVE_LANE_BOARD.md` — edit only this lane's block.
  - `docs/DOC_SYSTEM.md` — add one row to the doc map; leave the precedence
    ladder alone (it changed today).
  Do **not** touch `saathi/scheduling.py`, `saathi/worker/turns.py` or
  `saathi/agent/tools/handlers.py` without re-reading them at `64a520b` — all
  three changed today. Findings against them are welcome; blind edits are not.
  PR-23 was reserved for SEC-2; DOC-1 took PR-24 rather than collide with it.
  Base on `64a520b` or later. Already-known security items are lanes, not new
  findings: SEC-1 (Business Agent on our WABA), CRED-1/PR-22 (forge write
  credentials on the runtime box), and **PR-24 — SSH open to `207.219.25.137/32`**,
  measured and documented by DOC-1 on 2026-07-27. Re-report those only if you
  find something the existing rows miss.

### PR-23 — forwarded text could drive deterministic commands   [CLOSED]
Owner: Claude (runtime box)        Opened: 2026-07-27 (Codex SEC-2) · Closed: 2026-07-27
Reading: saathi/provenance.py, saathi/capabilities.py, saathi/commands.py, docs/ARCHITECTURE.md
Acceptance: relayed text cannot reach a state-changing command; the user's own
  typed/spoken commands still work; button presses stay trusted. — MET.
Result: priority-22 matcher now requires `c.trusted`. 314 tests (+9), and the
  new tests verified to fail without the guard (4 of 9 go red on revert).
Notes: **worse than SEC-2 reported.** STOP matches `\bunsubscribe\b` as a
  substring, and nearly every forwarded advert carries it in the footer. That set
  `users.paused = true`, which `worker/turns._handle` honours by silently not
  sending — so a forwarded promo stopped a user's medication reminders
  indefinitely, with PR-4b guaranteeing nothing would reveal it. No attacker
  needed. Onboarding (10) left unguarded on purpose: gating it would drop an
  un-onboarded user to the agent and break "onboarding never calls the model".

### WA-1 — Saathi is unreachable and unnamed on WhatsApp   [CLOSED]
Owner: Claude (runtime box)        Opened: 2026-07-27 · Closed: 2026-07-27
Reading: docs/LANDMINES.md, docs/DECISIONS.md (D-A, D-J), docs/PROD_READINESS.md (PR-5)
Acceptance: an Indian number, an approved display name, inbound reaching
  `/webhook/whatsapp`, and a real message answered end to end. — MET.
Result: **+91 8071 581 944** "Indofolk AI", CONNECTED on CLOUD_API, WABA
  `1687148075730227`, currency INR. Live message verified on the handset.
  Vobiz supplies the number only — verification and registration were done on our
  own Cloud API, so **D-A survives**. Decision D-M.
Notes: the display name is "Indofolk AI", not "Saathi" — "Saathi" was declined
  because the verified business's registered site (`indofolkwellness.com`) is a
  B2B pet products company with zero mention of Saathi. Reversible once a Saathi
  page exists there. See WA-2.

### WA-2 — make "Saathi" an approvable display name   [PARKED]
Owner: unassigned        Opened: 2026-07-27 · Parked: 2026-07-27
Reading: docs/DECISIONS.md (D-M), docs/PRD.md §2
Acceptance: `indofolkwellness.com` presents Saathi as an Indofolk Wellness
  product; "Saathi" re-submitted and APPROVED; a `wa.me` link published so the
  number is reachable without saving a contact.
Write-back: docs/DECISIONS.md, docs/PROD_READINESS.md
Notes: the WIX_API_KEY is stored and its account covers the site (site id
  `74ab9ac8-1a47-4476-9b59-a67c93636324`). **This is a live company website that
  is not Saathi's** — nothing published without the operator reading it first.
  The product cost of waiting is real: an elder currently receives medication
  reminders from a company name, not from the companion they talk to.

  **Parked 2026-07-27.** Two things changed under it. The display name is now
  **"Indofolk AI"**, approved, on an Indian number — so the elder is no longer
  reading a pet-products company's name. And the operator has said the brand
  itself is provisional: *"naming is cosmetic, I might change brand name at time
  to prod, will decide beta testing."* Chasing approval for "Saathi" before that
  decision would spend a review cycle on a name that may not ship. Revisit when
  the brand is settled.

### WA-3 — surface commands and ice breakers   [CLOSED]
Owner: Claude (runtime box)        Opened: 2026-07-27 · Closed: 2026-07-27
Reading: docs/vendor/meta/conversational-components.md, saathi/commands.py, docs/PRD.md §2
Acceptance: `GET /{phone_number_id}?fields=conversational_automation` returns our
  commands and prompts; a fresh thread shows tappable ice breakers; tapping one
  produces a normal `messages` webhook that the pipeline handles.
Write-back: docs/ARCHITECTURE.md, CHANGELOG.md
Notes: **the handlers already exist.** `commands.py` parses eight slash commands
  (`/start /help /stop /resume /delete /forget /whatyouknow /clear`) that no user
  can discover — registering them with Meta only makes them visible. Currently
  `conversational_automation` is unset on `1266402176549539`.

  Ice breakers matter more than they look here. PRD §2 argues the hard part for
  this user "was never the transaction — it was **articulating the request**".
  Ice breakers replace a blank compose box with up to four tappable openings,
  which is that problem solved directly, for the exact moment a 70-year-old opens
  the thread for the first time.

  Constraints from the vendor doc: 4 ice breakers max, 80 chars each; 30 commands
  max, name ≤32, hint ≤256; **no emoji in either**; and a `wa.me` link carrying
  pre-filled text dismisses the ice breaker UI. Ours (`wa.me/918071581944`) has no
  `?text=`, so it is safe — do not add one.

Result: MET. 8 commands + 4 ice breakers configured on `1266402176549539`,
  verified by read-back. All four ice breakers were run through `commands.parse`
  and the safety classifier first — none trips a command or a trigger by accident.

  **Settled the design question by testing, not by choosing.** The un-onboarded
  tap is still swallowed by onboarding (correct — onboarding must come first), so
  the ice breakers are worded as *openings*. But the menu itself is the payload:
  four tappable lines showing remind / read / remember / just talk is a capability
  demo shown before the user types anything, which is PRD §2's "articulating the
  request" answered by the platform.

  One phrasing changed because of a test: "Mere baare mein aapko kya yaad hai"
  fell through to the **model**, while "Mere baare mein kya jaante hain" matches
  the deterministic WHAT_YOU_KNOW handler. "What do you know about me" is a
  transparency feature and must return an exact list, not a generated answer — so
  the ice breaker is worded to hit the deterministic path.

### META-1 — move off MeshPilot's Meta app   [CLOSED]
Owner: Claude (runtime box)        Opened: 2026-07-27 · Closed: 2026-07-27
Reading: docs/DECISIONS.md (D-J, D-M, D-X), docs/PROD_READINESS.md (PR-5, PR-6)
Acceptance: Saathi's own Meta app is the sole subscriber to the WABA; its own app
  secret verifies inbound; a non-expiring token sends; MeshPilot unsubscribed;
  inbound never gapped during the move. — MET, verified against Graph.
Write-back: DECISIONS.md (D-X, D-J superseded), PROD_READINESS.md (PR-5 resolved,
  PR-6 sharpened, PR-45 opened and resolved), CHANGELOG.md
Notes: app `1019173634258664`, system user `122098890723360160`, token
  `expires_at: 0`. Sequencing was the whole risk — callback registered while
  subscribed to nothing, then subscribed alongside MeshPilot, then both
  credentials swapped in one write, then MeshPilot removed. Any other order
  fails silently, and silent is what an elder experiences as nothing arriving.

  Two corrections came out of it. PR-5 called the business "borrowed" for a day
  after D-M had recorded that `ayurpetofficial` is a display label for INDOFOLK
  WELLNESS PRIVATE LIMITED — our own verified entity. And a session (mine)
  reported 51 signing violations using `%G?`, which `CONTRIBUTING.md:64` says
  cannot work here. Both were repetitions of already-resolved facts, which is the
  failure mode a caveats journal is most prone to.

  **Still unproven and it is the only thing left:** no real inbound message has
  round-tripped through the new app. Signatures, tokens and API reads are all
  verified; a live message is not.

### AI-1 — per-account OpenRouter keys   [CLOSED]
Owner: Codex (runtime box)        Opened: 2026-07-27 · Closed: 2026-07-27
Reading: docs/AI_ROUTING.md, docs/DECISIONS.md (D-D, D-O), docs/vendor/, PR-15
Acceptance: a paying account gets a capped key minted from `scheduled_turns`;
  calling twice mints once; an unconfigured install refuses rather than storing a
  plaintext; every request carries `allow_fallbacks: false`; no list/revoke/sync
  can touch a key without the `saathi:` prefix; audit rows on both outcomes.
Write-back: docs/AI_ROUTING.md, docs/PROD_READINESS.md, CHANGELOG.md
Notes: design doc written first (THE_METHOD §1) — the code follows it, not the
  other way round. Model and region are unchanged (D-O), so D-D's bakeoff stands.

  Residency is **settled**, not open — operator decision 2026-07-27, and the
  privacy policy already draws the stored-data / message-text line correctly.

  ~~**Blocked on credits only.**~~ **Never was — corrected 2026-07-27.** Routing
  is BYOK onto our own Bedrock credential, so a minted key spends on our AWS bill
  and `total_credits: 0` is the expected steady state. This lane, PR-38 and
  AI_ROUTING §9 all named funding as the gate; none of them should have.

  **Mint and revoke are now proven against the live vendor**, unintentionally: a
  user finished onboarding at 22:39 and `provision_key` minted a real key with a
  usable hash. `DELETE /keys/{hash}` then returned `{"deleted": true}`. Runtime
  routing is now wired in code and proven live: user chat turns resolve the
  account key and call OpenRouter with no fallbacks/ZDR when one exists. Migration
  012 queued every existing account; live DB verification showed all 7 accounts
  with active keys; a real probe through account 3 returned `route ok` with token
  usage.

  Confirmed live: workspace `718e8438-…` (Indofolk AI), BYOK `amazon-bedrock`
  "Indian Box" at sort_order 0, `z-ai/glm-5` available, provisioning key valid.
  The SDK's `create()` takes `workspace_id`, `limit_reset` and `expires_at` — the
  prose docs omit all three, so trust `vendor/` and the generated client.

  **Closed 2026-07-27.** Migration 008 added accounts and key tables; 011 queued
  already-onboarded accounts; 012 queued every existing active account. Runtime
  routing now resolves an account key before the agent call. The earlier
  "blocked on credits" and "no real key has been minted" notes were wrong: BYOK
  spends against our Bedrock account, all 7 live accounts now have active
  workspace-scoped keys, and live probes proved both revoke/remint and
  spend-through.

  Two design questions closed while building: every free account gets its own
  one-time $5 key after onboarding completes, and the account tenant had to be
  built first because none existed.

### LANG-1 — a user who chose हिंदी was answered in Latin   [CLOSED]
Owner: Claude (runtime box)        Opened: 2026-07-27 · Closed: 2026-07-27
Reading: docs/DECISIONS.md (D-W), docs/LANDMINES.md (Meta templates)
Acceptance: `hi` is answered in Devanagari, `hi-en` keeps romanised Hindi, `en`
  unchanged; the script is a stored choice rather than mirrored from the user's
  typing; commands parse in all three scripts. — MET at `0f46069`, deployed.
Write-back: DECISIONS.md (D-W), PROD_READINESS.md (PR-44), CHANGELOG.md
Notes: three defects surfaced by the conversion, all worse than cosmetic —
  `commands.parse` was Latin-only, so "सब कुछ भूल जाओ" (the phrase the consent
  screen tells a Hindi reader to use for erasure) matched nothing; `\bchalu kar\b`
  never matched "chalu karo", making RESUME unreachable by its own advertised
  words; and the safety replies used masculine verb forms for a persona the
  SYSTEM prompt defines as female. Devanagari costs ~1.77x the tokens, measured.
  **Reminders still arrive romanised** — templates are Meta-approved and cannot
  be edited. That is PR-44 and it is the largest remaining gap.

### PAY-1 — the paywall, in-thread   [BUILT, INERT]
Owner: Codex (runtime box)        Opened: 2026-07-27 · Closed: 2026-07-27
Reading: docs/DECISIONS.md (D-T, D-U), docs/AI_ROUTING.md
Acceptance: an exhausted account is answered deterministically above the agent;
  no payment tool is reachable by the model; rights (safety, onboarding,
  erasure, ack, STOP) survive the paywall; reminders keep firing. — MET.
Write-back: DECISIONS.md (D-T, D-U), PROD_READINESS.md (PR-40..43), CHANGELOG.md
Notes: inert in both directions on purpose. Nothing sets `status='exhausted'`
  (PR-42) and the payment webhook is unhandled (PR-43), so a user who paid would
  stay locked out. **Do not set `SAATHI_PAYMENTS_ENABLED=true` before PR-43.**
  The boundary that had to be argued rather than coded: Saathi can now ask for
  money, which is a real reduction in "it never transacts". It is bounded to one
  deterministic path — `order_details` and friends are in
  `FORBIDDEN_TOOL_NAMES`, so the model cannot invoice and cannot be
  prompt-injected into it.

### FIX-1 — three live defects found by reading logs, not tests   [CLOSED]
Owner: Claude (runtime box)        Opened: 2026-07-27 · Closed: 2026-07-27
Reading: docs/CHANGELOG.md 2026-07-27 entries
Acceptance: each reproduced, fixed, red-checked by deleting the guard, deployed.
  — MET (`fa6bfc1`, `618ce84`, `c40d21a`).
Write-back: CHANGELOG.md, PROD_READINESS.md (PR-37)
Notes: (1) the agent had no clock, so a reminder asked for "in 5 minutes" was
  dated 2025-01-09 and fired 18 months late, 23 seconds after creation;
  (2) `nudge()` and `checkin()` discarded the WhatsApp message id, so the sweep
  re-sent every delivered nudge every 15 minutes — one user got the same message
  four times; (3) a captionless image stored `body_text=''`, which passed
  `history`'s `is not null` filter and became a blank ContentBlock, killing that
  user's next four turns. All three were green in the suite throughout.

### PR-4b — the reminder ack path is unreachable   [CLOSED]
Owner: Claude (runtime box)        Opened: 2026-07-27 · Closed: 2026-07-28
Reading: docs/LANDMINES.md (Meta template rules), docs/PRD.md §C2, §15
Acceptance: a fired reminder carries quick-reply buttons whose payload identifies
  the turn; pressing one marks that `scheduled_turns` row `acked`; an
  unacknowledged reminder enqueues a nudge; §15's acknowledgement metric reads a
  table that actually receives fires.
Write-back: docs/ARCHITECTURE.md, docs/PROD_READINESS.md, CHANGELOG.md
Notes: found while working PR-4. Three separate breaks, all silent:
  (1) **refined 2026-07-27** — the templates *do* carry approved QUICK_REPLY
  buttons (`Ho gaya`, `15 min baad`). Template-defined quick replies return the
  button **text**, not a payload, so the `ack:{id}` form `handle_ack` parses can
  never appear. Fix is a `button` component with a dynamic payload, or matching
  on the text;
  (2) `handle_ack` updates `reminder_fires`, but reminders now fire from
  `scheduled_turns`, so the row that fired is never marked acked;
  (3) nothing anywhere calls `enqueue(..., "nudge", ...)` — the handler is
  registered and dead, so an unacknowledged reminder is never followed up.
  Consequence: §15's acknowledgement metric is structurally zero, not low.
  Needs a Meta-side decision first — dynamic button payloads require a `button`
  component with `sub_type: quick_reply`, and the approved templates may need
  resubmitting. **Do not delete a template to change it** (`docs/LANDMINES.md`).

### PR-4 — reminders are never dispatched at all   [CLOSED]
Owner: Claude (runtime box)        Opened: 2026-07-26 · Closed: 2026-07-27
Reading: docs/PROD_READINESS.md (PR-4), docs/ARCHITECTURE.md, saathi/scheduling.py
Acceptance: a reminder created through the real handler lands on
  `scheduled_turns`; recurring reminders book the next occurrence; a claimed-but-
  unsent turn is reclaimed; all covered by tests **and** proven against the live
  database. — MET.
  Result: 301 tests passing (+7). End-to-end probe created a reminder, saw it
  enqueued `pending` with dedupe key `reminder:18:2026-07-27T02:30:00+00:00`
  (08:00 IST stored as UTC), `reminder_fires` untouched, synthetic rows deleted.
  **Residual deliberately not in scope:** nothing pages a human yet (PR-3,
  blocked on `PutMetricAlarm`/SNS), and acknowledgement is broken (PR-4b).
Write-back: docs/ARCHITECTURE.md, docs/PROD_READINESS.md, CHANGELOG.md
Notes: P0, and **worse than the PROD_READINESS row says**. Measured 2026-07-27:
  `_create_reminder` (handlers.py:86) writes to `reminder_fires`; the worker
  (`worker/__main__.py`) reads only `scheduled_turns`; and
  `worker/reminder_scheduler.py` — the sole reader of `reminder_fires` — has
  **zero references anywhere in the repo**. Migration 006 back-filled existing
  fires once, at migration time. So a reminder created today is written to a
  table nothing reads and **never fires**. Latent, not live: both tables are
  currently empty, so nothing has been dropped yet.
  Scope of this lane is the delivery core — create → enqueue → dispatch →
  reschedule, plus a stuck-turn sweep and a dispatch heartbeat. Ack/nudge
  wiring is cut out as PR-4b because it needs Meta-side template buttons.

### PR-3 — no alerting on anything   [CLOSED]
Owner: Claude (runtime box)        Opened: 2026-07-26 · Closed: 2026-07-27
Reading: docs/PROD_READINESS.md (PR-3), docs/RUNBOOK.md
Acceptance: backup failure and `saathi-worker` inactive both reach a human;
  demonstrated by inducing each condition, not by inspecting config.
Write-back: docs/RUNBOOK.md, docs/PROD_READINESS.md, CHANGELOG.md
Result: MET. Worker stopped 01:44:05Z → ALARM 02:04:59Z → SNS delivered 8→9,
  failed 0, to confirmed subscriber. `saathi-backup-stale` separately observed
  ALARM→OK. Measured detection latency **~21 min**, not the 10 the config
  implies — recorded in `RUNBOOK.md` rather than quietly rounded.
Notes (history): detection was built and induced:
  heartbeat published after each successful tick, two alarms treating missing
  data as breaching, OnFailure drop-ins on all four units, and `saathi-alert`
  verified publishing to SNS. What is *not* met is the words "reach a human" —
  the SNS email subscription is `PendingConfirmation`, and SNS delivers nothing
  until the recipient clicks the link. Closing on the strength of the alarms
  existing would be the `ffmpeg -version` mistake exactly.
  **To close:** operator runs
  `aws sns subscribe --region ap-south-1 --topic-arn arn:aws:sns:ap-south-1:559896294326:saathi-alerts --protocol email --notification-endpoint support@glitchexecutor.com`
  and clicks confirm; then re-induce and check the mail actually lands.
  Learned on the way: `saathi-worker` is `Restart=always`, so it re-enters
  `active` rather than `failed` and `OnFailure` barely applies to it — a
  crash-looping worker looks alive, and only the heartbeat alarm catches it.

### PR-8 — no TTS; a voice-first product that only writes back   [OPEN]
Owner: unassigned        Opened: 2026-07-26 (from PROD_READINESS)
Reading: docs/PRD.md §9, docs/DECISIONS.md, docs/PROD_READINESS.md (PR-8, PR-5)
Acceptance: a voice reply reaches a real WhatsApp thread as OGG/Opus playable
  inline — **not** a file attachment — behind the swappable interface, with
  phrase-bank caching.
Write-back: docs/ARCHITECTURE.md, docs/DECISIONS.md, docs/PROD_READINESS.md, CHANGELOG.md
Notes: P1, and the biggest felt gap. Blocked on a route decision the operator
  owns: the ElevenLabs key is MeshPilot's (PR-5) and reads as quota-exhausted
  (10.7M used / 5.6M limit), so realistically this is Google `texttospeech` on
  Saathi's own GCP project. Stored voice id is Rachel (English default);
  `ZUrEGyu8GFMwnHbvLhv2` (Monika Sogam) is the better Hinglish start.

### PR-9 — no real eval corpus; every STT number is synthetic   [OPEN]
Owner: unassigned        Opened: 2026-07-26 (from PROD_READINESS)
Reading: docs/PRD.md §15, docs/PROD_READINESS.md (PR-9), docs/LANDMINES.md
Acceptance: 50–100 real elder voice notes per language, hand transcribed,
  deliberately including the messy ones; entity accuracy re-measured against it.
Write-back: docs/PRD.md §0, docs/DECISIONS.md, docs/BUILD_PLAN.md
Notes: P1. R1 is the product risk and it is unmeasured against reality. Every
  accuracy claim so far rests on TTS-generated speech, which is cleaner and
  differently distorted than a 70-year-old on a bad line with a television on.

---

## Recently closed (rolling — prune to `docs/ENGINEERING_SUPERVISOR.md`)

### SETUP-1 — merge the vibe-coding-kit control plane into Saathi   [CLOSED]
Owner: Claude            Opened: 2026-07-27 · Closed: 2026-07-27
Result: control plane added by **merge, not scaffold** — `bin/vibe-scaffold`
  would have written `docs/DOC-SYSTEM.md` and `control-plane/ENGINEERING_SUPERVISOR.md`
  alongside Saathi's existing `docs/DOC_SYSTEM.md` and `docs/ENGINEERING_SUPERVISOR.md`,
  forking two sources of truth and violating the kit's own "amend, don't fork" rule.


OpenRouter workspace correction verified 2026-07-27: `OPENROUTER_WORKSPACE_ID` is set to `718e8438-6c5a-48f9-85c9-f8909f2e4c47`; all seven active Saathi keys list under that workspace with limit 5 and no reset; Default workspace lists no Saathi keys; account 1 completed a real OpenRouter turn returning `workspace route ok` with token usage.

### OBS-1 — in-region tracing (logfire SDK → local collector → Jaeger)   [CLOSED]
Owner: Clawcore (runtime box, source branch agent/in-region-tracing)        Opened: 2026-07-29 · Closed: 2026-07-29
Reading: docs/THE_METHOD.md, docs/ARCHITECTURE.md, docs/DECISIONS.md, docs/PROD_READINESS.md, docs/RUNBOOK.md, CONTRIBUTING.md, saathi/metrics.py, saathi/config.py, saathi/pipeline.py, saathi/agent/loop.py, saathi/web/app.py, saathi/worker/__main__.py
Acceptance: logfire SDK configured with inspect_arguments=False, OTLP exporter to localhost:4317, saathi/observability.py enforces a fixed allow-list of span attributes, tracing spans cover pipeline.handle_message → safety.classify → speech → agent.loop.run → each model call and tool handler, best-effort init, otelcol+jaeger systemd units exist and listen on 127.0.0.1 only, uv run pytest -q passes with no regression.
Write-back: docs/ARCHITECTURE.md (new boundary + no-PII-in-spans rule), docs/DECISIONS.md (D-AB), docs/RUNBOOK.md (two new units + how to query), CHANGELOG.md (symptom first), docs/PROD_READINESS.md (new infra row), docs/ENGINEERING_SUPERVISOR.md (evidence appended), control-plane/SESSION_COORDINATION.md
Notes: MET. PRs #11 (code) + #12 (docs) merged (squash). Deployed 8b2fe16 via ops/deploy.sh --local. 532 tests passed, zero regressions. All spans wired. Tracing disabled by default (SAATHI_TRACING_ENABLED unset). Setup script and systemd units exist but not yet run — infra install is a separate ops/setup-tracing.sh step at enable time.

### RUNTIME-MIGRATION-2 — Phase 2: systemd units + cloudflared + live cutover   [CLAIMED]
Owner: Clawcore (dev box ip-172-31-41-224)        Opened: 2026-07-29
Reading: docs/DOC_SYSTEM.md, docs/RUNBOOK.md, docs/PROD_READINESS.md, docs/ARCHITECTURE.md, docs/ENGINEERING_SUPERVISOR.md, ops/deploy_onbox.sh, ops/deploy.sh, current systemd units on original box
Acceptance: saathi-web.service + saathi-worker.service exist in repo and are installed on the new box; cloudflared installed and saathi-dev tunnel connector moved (nginx-like, proxying saathi.n8nworld.store to this box); app boots under systemd and responds to GET /healthz; a real WhatsApp webhook round-trips through tunnel → web → model → reply; original box can be decommissioned only after live proof.
Write-back: docs/RUNBOOK.md (new box details, systemd units, cloudflared), docs/ARCHITECTURE.md (IP/hostname), docs/PROD_READINESS.md (Phase 2 done), CHANGELOG.md, docs/ENGINEERING_SUPERVISOR.md, control-plane/SESSION_COORDINATION.md
Notes: Builds on Phase 1 (46a537e). Box: ip-172-31-41-224, 7.6 GiB RAM, 96 GB disk, Postgres 16.14, venv on 3.13.14. SSO profile saathi = AWSAdministratorAccess in 559896294326. saathi.n8nworld.store currently points to original box i-01b2c27883acb25ca via cloudflared; cutover means moving the tunnel connector here.

