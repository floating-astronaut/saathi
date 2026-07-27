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

### DOC-1 — three docs claim no inbound port is open; SSH is open   [OPEN]
Owner: unassigned        Opened: 2026-07-27
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
  could not be read from the runtime box — its instance role has no
  `ec2:DescribeInstances` — so confirm the exact CIDR from the dev box or console.
  **Under `docs/LANE_LIFECYCLE.md` §5 the lane that opened SSH is still OPEN, not
  closed: it changed infrastructure and never wrote back.**

### CRED-1 — runtime box now holds write credentials for both forges   [OPEN]
Owner: unassigned        Opened: 2026-07-27
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

### SEC-1 — Meta Business Agent is subscribed to our WABA   [OPEN]
Owner: unassigned        Opened: 2026-07-26 (migrated from supervisor Queued)
Reading: docs/LANDMINES.md, docs/PROD_READINESS.md (PR-6), docs/DECISIONS.md (D-E)
Acceptance: app `1143680903703001` is unsubscribed from WABA `1023945910495878`,
  **or** a dated decision records that it stays with `rollout.enabled = false`
  plus a check that alerts if the flag flips.
Write-back: docs/DECISIONS.md, docs/PROD_READINESS.md, docs/LANDMINES.md
Notes: operator decision — not taken unilaterally, since the subscription was not
  created by the lane that found it. Enabling it makes Meta's model the primary
  responder, so inbound messages never reach the deterministic priority-0 safety
  classifier (R7). **Appeared in two separate supervisor `Queued` blocks and was
  never closed — this board exists because of failures like this one.**

### PR-4 — reminders have no delivery guarantee   [OPEN]
Owner: unassigned        Opened: 2026-07-26 (from PROD_READINESS)
Reading: docs/PROD_READINESS.md (PR-4), docs/ARCHITECTURE.md, saathi/scheduling.py
Acceptance: a stuck-fire sweep detects fires left in `sent` without an ack; an
  alert fires when dispatch count is zero over a window where it should not be;
  both covered by tests.
Write-back: docs/ARCHITECTURE.md, docs/PROD_READINESS.md, CHANGELOG.md
Notes: P0. A missed cardiac dose is this product's worst failure and it is
  currently invisible. Pairs naturally with PR-3 — the sweep is worthless if
  nothing can page a human.

### PR-3 — no alerting on anything   [OPEN]
Owner: unassigned        Opened: 2026-07-26 (from PROD_READINESS)
Reading: docs/PROD_READINESS.md (PR-3), docs/RUNBOOK.md
Acceptance: backup failure and `saathi-worker` inactive both reach a human;
  demonstrated by inducing each condition, not by inspecting config.
Write-back: docs/RUNBOOK.md, docs/PROD_READINESS.md
Notes: P0. The backup timer logs to `journalctl` and nobody reads `journalctl`.

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
