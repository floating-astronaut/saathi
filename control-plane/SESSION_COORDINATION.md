# Session Coordination

> Who is active right now, and on what. The point is collision avoidance: before
> you claim a lane or touch a surface, check here that no other agent is already
> on it. Update when a session starts, switches lanes, or ends.
>
> Rules: `docs/AGENT_SYNC_PROTOCOL.md` §4. Lane states: `docs/LANE_LIFECYCLE.md`.

## Active sessions

| Agent | Box | Started | Lane | Surface (files/dirs) | Status |
|-------|-----|---------|------|----------------------|--------|
| Claude | runtime `ip-172-31-41-224` | 2026-07-30 | VOICE-1 | `saathi/speech/tts.py`, `saathi/speech/audio.py`, `saathi/speech/__init__.py`, `saathi/config.py`, `docs/vendor/sarvam/text-to-speech.md`, `docs/DECISIONS.md`, `CHANGELOG.md`, `docs/PROD_READINESS.md`, `control-plane/*`, `tests/test_tts.py` | **ended** — TTS voice quality: bulbul:v3 + 48 kHz + preprocessing + clean Opus + per-language voices. PR-8 round-trip observed → CLOSED. 624 tests. Branch `agent/tts-voice-quality` → PR + deploy. |
| Claude | runtime `ip-172-31-41-224` | 2026-07-30 | LANG-2 | `saathi/onboarding.py`, `saathi/pipeline.py`, `saathi/capabilities.py`, `saathi/agent/prompt.py`, `saathi/speech/__init__.py`, `saathi/core/context.py`, `saathi/wa/client.py`, `saathi/channels/`, `saathi/safety/classifier.py` (comment), `docs/DECISIONS.md`, `docs/PROD_READINESS.md`, `CHANGELOG.md`, `docs/ENGINEERING_SUPERVISOR.md`, `control-plane/*`, `tests/test_languages.py` + spies | **ended** — gu/ml added as full languages; list picker; STT/TTS lang threading (fixed hardcoded hi-IN); safety gap documented (SAFE-LANG-1 opened). 622 tests. Branch `agent/add-gujarati-malayalam` → PR. |
| Claude | runtime `ip-172-31-41-224` | 2026-07-30 | PR-8 | `saathi/speech/tts.py` (new), `saathi/wa/client.py`, `saathi/core/context.py`, `saathi/channels/base.py`+`whatsapp.py`, `saathi/usage.py`, `saathi/config.py`, `docs/DECISIONS.md`, `docs/ARCHITECTURE.md`, `docs/USAGE_LEDGER.md`, `docs/vendor/sarvam/`, `docs/PROD_READINESS.md`, `CHANGELOG.md`, `docs/ENGINEERING_SUPERVISOR.md`, `control-plane/ACTIVE_LANE_BOARD.md`, `tests/test_tts.py` | **ended** — Sarvam Bulbul TTS BUILT, INERT behind `SAATHI_TTS_ENABLED` (off); voice-in→voice-out; D-AE reverses D-S; 614 tests, live OGG proof. Branch `agent/tts-voice-replies` → PR. |
| Claude | runtime `ip-172-31-41-224` | 2026-07-30 | PR-9 | `docs/STT_EVAL.md` (new), `saathi/eval/` (new), `evals/`, `docs/DOC_SYSTEM.md`, `docs/PROD_READINESS.md`, `CHANGELOG.md`, `docs/ENGINEERING_SUPERVISOR.md`, `control-plane/ACTIVE_LANE_BOARD.md`, `tests/test_eval_*.py` | **ended** — harness + protocol shipped; 602 tests, honesty gate proven; PR-9 CLOSED, corpus collection split to DATA-1. Branch `agent/stt-eval-harness` → PR. PR-8 (TTS) next, separate branch. |
| Claude | runtime `ip-172-31-41-224` | 2026-07-30 | RUNTIME-MIGRATION-3 | `saathi/config.py`, `saathi/bedrock.py`, `ops/deploy.sh`, `ops/alerting/`, `ops/backup/`, `docs/RUNBOOK.md`, `docs/PROD_READINESS.md`, `CHANGELOG.md`, `docs/ENGINEERING_SUPERVISOR.md`, `control-plane/ACTIVE_LANE_BOARD.md` | **ended** — Phase 3: estate moved to `635860424621`, PG18, inference on a Bedrock-only IAM user, old box terminated. Closed at `265aedb` + retirement; docs closure on branch `agent/runtime-migration-3-docs`. |
| Clawcore | dev `ip-172-31-41-224` | 2026-07-29T20:53Z | RUNTIME-MIGRATION-2 | `ops/saathi-web.service`, `ops/saathi-worker.service`, `ops/cloudflared/`, `docs/RUNBOOK.md`, `docs/ARCHITECTURE.md`, `docs/PROD_READINESS.md`, `CHANGELOG.md`, control-plane/session write-back | **ended** — Phase 2 cutover done; confirmed live during Phase 3 (board flipped to CLOSED) |
| ZCode | successor `ip-172-31-41-224` (ap-south-1) | 2026-07-29T20:05Z | RUNTIME-MIGRATION-1 (docs) | `README.md`, `docs/RUNBOOK.md`, `docs/PROD_READINESS.md`, `AGENTS.md`, `CLAUDE.md`, `KIMI.md`, `CHANGELOG.md`, `control-plane/SESSION_COORDINATION.md` | **in progress** — documenting the runtime-box migration; no app code touched. Webhook host `saathi.n8nworld.store` was briefly mispointed at Pages and reverted; `/healthz` confirmed live via the original box's tunnel. Branch `agent/runtime-migration-docs`. |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-29T16:30Z | LEDGER-2 | `saathi/agent/loop.py`, `saathi/openrouter.py`, `saathi/capabilities.py`, `saathi/pipeline.py`, `saathi/usage.py`, usage tests and routing/ledger docs | **ended** — PR #32 deployed at `aacd5af`; LLM/STT/template events live, STT pre-call enforcement gate built but disabled by default |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-29T13:10Z | LEDGER-1 | `saathi/usage.py`, `saathi/config.py`, `saathi/worker/__main__.py`, migration/tests, usage-ledger and PR-15 docs | **ended** — PR #27 deployed; migration 015 and 569 tests verified; observe-only by design |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-29T12:45Z | LIFE-5 | `saathi/safety/classifier.py`, safety tests, safety/product/architecture docs | **ended** — PR #24 deployed; 560 tests and public health/webhook probes passed |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-29T12:15Z | ID-2 | `saathi/identity.py`, `saathi/pipeline.py`, `saathi/worker/turns.py`, migration/tests and lifecycle docs | **ended** — PR #22 deployed; migration 014, 549 tests and live health verified |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-29T11:20Z | SEC-1 | `saathi/meta_guard.py`, `ops/saathi-meta-guard.*`, alert installer, Meta/docs/tests | **ended** — PR #19 deployed; first live guard passed and hourly timer enabled |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-29T10:35Z | RATE-1/RATE-2 | `saathi/pipeline.py`, `saathi/rate_limit.py`, `saathi/config.py`, `db/migrations/`, rate-limit tests, PR-15 docs/write-back | **ended** — merged as PR #17 / `ac0a493`, deployed locally; migration 013, 542 tests, health, services and tunnel verified |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-29T10:22Z | CodeGraph agent tooling | `~/.codegraph`, `~/.codex/config.toml`, `~/.claude.json`, repo agent docs, `.codegraph/.gitignore` | **ended** — CodeGraph v1.5.0 installed, wired for Codex and Claude Code, source checkout indexed and queried |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-29T10:05Z | OBS-3 | `saathi/observability.py`, `tests/test_observability.py`, tracing docs, Secrets Manager/runtime env | **ended** — Logfire project binding implemented and verified; branch ready for PR |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-29T09:48Z | CRED-1 follow-up | SSH config plus `CONTRIBUTING.md`, `docs/RUNBOOK.md`, `docs/LANDMINES.md`, CRED-1 notes | **ended** — GitLab SSH key configured; GitLab mirror synced over SSH; docs branch ready |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-29T08:55Z | OBS-2 | `saathi/observability.py`, `tests/test_observability.py`, `ops/setup-tracing.sh`, `ops/saathi-jaeger.service`, `ops/saathi-otelcol.service`, docs/write-back | **ended** — OBS-2 implemented and verified; branch ready for PR |
| Clawcore | runtime i-01b2c27883acb25ca | 2026-07-29T08:38Z | OBS-1 | saathi/observability.py etc | ended - OBS-1 implemented, PRs #11+#12 merged, deployed, verified |

| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-28T20:26Z | ID-1 | `saathi/capabilities.py`, `saathi/onboarding.py`, `saathi/identity.py`, `tests/test_capabilities.py`, docs/write-back | **ended** — ID-1 implemented and verified; branch ready for PR |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-28T20:11Z | LIFE-1c | `saathi/provenance.py`, `saathi/agent/prompt.py`, `tests/test_provenance.py`, `tests/test_lookup.py`, docs/write-back | **ended** — LIFE-1c implemented and verified; branch ready for PR |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-28T20:05Z | LIFE-1b | `saathi/vision.py`, `tests/test_vision.py`, `docs/DAILY_LIFE_OS.md`, `CHANGELOG.md`, supervisor/control-plane write-back | **ended** — LIFE-1b implemented and verified; branch ready for PR |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-28T19:13Z | LIFE-1 | `saathi/provenance.py`, `saathi/agent/prompt.py`, `tests/test_provenance.py`, `tests/test_lookup.py`, docs/write-back | **ended** — LIFE-1 implemented and verified; branch ready for PR |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-28T19:05Z | LIFE-0 | `docs/DAILY_LIFE_OS.md`, `docs/DOC_SYSTEM.md`, `docs/PRD.md`, `docs/DECISIONS.md`, control-plane write-back | **ended** — LIFE-0 roadmap written and queued implementation lanes |
| Codex | runtime `i-01b2c27883acb25ca` | 2026-07-28T18:43Z | CAP-2 | `saathi/commercial_actions.py`, `saathi/agent/tools/handlers.py`, `saathi/agent/tools/specs.py`, `saathi/agent/prompt.py`, `tests/test_commercial_actions.py`, docs/write-back | **ended** — CAP-2 implemented and verified; branch ready for PR |
| Codex | dev `ip-172-31-32-37` | 2026-07-28T18:00Z | CAP-1 | `docs/DOC_SYSTEM.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, new/updated commercial capability docs, control-plane write-back | **ended** — CAP-1 contract written; branch ready for PR |
| Claude | runtime `i-01b2c27883acb25ca` | 2026-07-27 | PR-4 | `saathi/scheduling.py`, `saathi/worker/turns.py`, `saathi/agent/tools/handlers.py`, `tests/test_reminder_delivery.py`, `tests/test_scheduling.py` | **ended** — closed at `64a520b`, surfaces released |
| Codex | — | 2026-07-27 | SEC-2 | `SECURITY.md` (new, owns it outright) | **ended** — closed SEC-2 at scan `c4b34ba`, surfaces released |
| Claude | runtime `i-01b2c27883acb25ca` | 2026-07-27 | PR-3 | `saathi/metrics.py`, `saathi/worker/__main__.py`, `ops/alerting/`, `tests/test_metrics.py` | **ended** — closed, surfaces released |
| Codex | dev `ip-172-31-32-37` | 2026-07-27T23:04Z | AI-1 follow-up | `saathi/openrouter.py`, `saathi/agent/loop.py`, `saathi/capabilities.py`, `saathi/onboarding.py`, `saathi/admin/grant.py`, `db/migrations/`, `tests/test_openrouter_keys.py`, `tests/test_onboarding.py`, docs/AI routing write-back | **ended** — runtime routing wired; migration 011 queues existing-account provisioning; live spend-through remains |

**Base commit is `6dd6e72`+** (2026-07-27, end of day; it moved again after). `main` moved **51 times**
on 2026-07-27, so any figure written here goes stale within the hour — do not
trust this line, run:

    git ls-remote https://github.com/Nuraveda-Labs/saathi.git main

Create an `agent/<task>` branch from current `main` before committing. Concurrent
sessions still declare their surfaces here first, but product state lands through
GitHub PRs into `main`; direct writes to `/home/ubuntu/saathi` are runtime
debugging only and must be copied back to a source branch before they count.

## Rules

- **Claim before you touch.** Add your row before editing a surface another
  session might also touch.
- **One surface, one session.** If a surface is already listed, coordinate or
  pick a different lane — don't edit it concurrently.
- **Clear your row on exit.** A stale "active" row blocks others. Remove it (or
  mark `ended`) when you stop.
- **This is presence, not history.** Closed-lane evidence goes to
  `docs/ENGINEERING_SUPERVISOR.md`, not here.

## Saathi-specific: name the box, not just the agent

This product runs on two machines and they are not interchangeable. A row that
says "Claude" without saying which box is useless, because the two boxes can do
different things:

| Box | Region | Can |
|---|---|---|
| Dev box | us-east-2 | author, **sign**, push, `ops/deploy.sh` (remote transport) |
| Runtime box `i-01b2c27883acb25ca` | ap-south-1 | author, push, `ops/deploy.sh --local`, run services, debug live, verify — **cannot sign** |

**Updated 2026-07-27:** the runtime box is no longer verify-only. PR-28 gave it
`--local`, and D-L settled that signing is not a gate ("single person github
account… that rule is cosmetic"). All 51 commits and all four deploys that day
were authored, pushed and deployed from the runtime box, unsigned by design.

Do not use `%G?` to check any of this — SSH verification needs
`gpg.ssh.allowedSignersFile`, which is unset, so a correctly signed commit also
reports `N`. `CONTRIBUTING.md:64` gives the check that works. This has now
misled twice, most recently on 2026-07-27 when a session reported 51 signing
violations that were not violations.

Edits made in the runtime box's checkout are committed nowhere and are
overwritten by the next deploy. If you are working there, say so in your row —
otherwise the next agent will assume your changes exist in git and they do not.

**Check which checkout you are in before believing anything.** There are usually
several on the runtime box at different commits, and only one is current:

    /home/ubuntu/saathi        the deployed artifact. Its files are live, but its
                               git metadata is fossilised — HEAD reads far behind
                               main and that is expected, not a problem to fix.
    source clones              created by sessions for `agent/<task>` branches.
                               Push a PR, merge to `main`, deploy, then delete
                               when the lane closes.

This has already misled once: on 2026-07-27 the deployed tree read three commits
behind, and the honest conclusion from `git log` there was that work was missing
when it was not. **Trust `git ls-remote`, not a local HEAD:**

    git ls-remote https://github.com/Nuraveda-Labs/saathi.git main
    git ls-remote https://gitlab.com/nuraveda-lab/saathi.git main

If you create a source clone, remove it when you are done. A clone nobody owns is
a tree the next session will read and believe.

## Recent handoffs

> When you hand a lane to another agent, note it here so they have context.

- **CAPI-1** (Claude, 2026-07-30) — claimed on branch `agent/meta-capi-gcs-bridge`.
  Docs-first increment (`docs/CAPI_GATEWAY.md`) landed: the Meta Conversions API
  Gateway is verified live on Cloud Run, credentials work, the app simply never
  emits events. The lane is **blocked on the operator** for the whose-data/which-
  events decision and three identifiers (Gateway URL, pixel/dataset ID, Gateway
  token). No code written yet — deliberately, it touches the privacy boundary.
