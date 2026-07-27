# Saathi Doc System

Last updated: 2026-07-27
Repo: `/home/ubuntu/saathi` (checkout on the us-east-2 dev box, for signing/pushing)
Runtime: `i-01b2c27883acb25ca`, **ap-south-1** — see `RUNBOOK.md`

This is the master map. It says which docs are authoritative, in what order to
read them, which doc owns which kind of decision, and what must be updated when
work lands. It mirrors the MeshPilot doc system deliberately — same habits,
different product — but Saathi is a **separate product with a separate repo,
database, AWS account and lifecycle**. Nothing here is shared with MeshPilot
except the Meta app and, for now, the ayurpet system-user token.

## Doc-first rule (hard, anti-drift)

Before any code touching product behaviour, safety, memory, reminders, speech,
pricing or the WhatsApp channel, **every session**, read in order:

1. `DOC_SYSTEM.md` (this file)
2. `AGENT_SYNC_PROTOCOL.md` — the contract every agent on this repo agrees to
3. `../control-plane/ACTIVE_LANE_BOARD.md` — the live queue, and
   `../control-plane/SESSION_COORDINATION.md` — who else is active right now
4. `PRD.md` — the research and the product argument
5. `BUILD_PLAN.md` — what was decided, measured, and why
6. the tail of `ENGINEERING_SUPERVISOR.md` — recent closures and evidence
7. `LANDMINES.md` — **read this before touching Meta, Cloudflare or ffmpeg**

Then read the **required reading** named by the lane you are about to work.

"I read it last session" does not count. A lane is **not closed** until the
contract docs are updated, the board shows it CLOSED, and evidence is appended
to `ENGINEERING_SUPERVISOR.md`. See `LANE_LIFECYCLE.md` §5.

## Precedence

1. direct operator instruction
2. this file
3. product law — `PRD.md`, `ARCHITECTURE.md`
4. decisions — `DECISIONS.md`
5. live control plane — `../control-plane/ACTIVE_LANE_BOARD.md`,
   `../control-plane/SESSION_COORDINATION.md`
6. execution and historical evidence — `BUILD_PLAN.md`,
   `ENGINEERING_SUPERVISOR.md`, `RUNBOOK.md`
7. current code
8. prior claims in chat

The live control plane outranks the supervisor log deliberately: the board says
what is true *now*, the log says what was true *then*. **Never use the supervisor
log as the queue** — it is append-only, so nothing in it is ever struck off, and
that is exactly how "unsubscribe the Business Agent app" sat in two separate
`Queued` blocks without ever being done.

**The PRD is research, not scripture.** It is the best available argument for
why this product should exist, and several of its technical claims have been
measured and found wrong (see `PRD.md` §0 and `LANDMINES.md`). Where the PRD and
a measurement disagree, the measurement wins and `DECISIONS.md` records it.

## Doc map

| Doc | Owns |
|---|---|
| `THE_METHOD.md` | The core loop: docs first → lanes assigned → code → write back → no drift. |
| `AGENT_SYNC_PROTOCOL.md` | The multi-agent contract. Source-of-truth order, handoffs, mandatory write-backs. |
| `ROLES.md` | Division of labour. Claude builds, Codex verifies, Kimi orchestrates. |
| `LANE_LIFECYCLE.md` | How a lane moves from OPEN to CLOSED, and what closing requires. |
| `../control-plane/ACTIVE_LANE_BOARD.md` | **The live queue.** Every lane, its owner, its state. If the board and reality disagree, fix the board. |
| `../control-plane/SESSION_COORDINATION.md` | Who is active right now, on which box, on which surface. Collision avoidance. |
| `../CLAUDE.md`, `../AGENTS.md`, `../KIMI.md` | Per-agent operating rules, committed to the repo so every agent reads the same contract. |
| `PRD.md` | The problem, the user, the research, the product argument. Amended, never silently overwritten. |
| `ARCHITECTURE.md` | How the system is built and why each boundary exists. |
| `DECISIONS.md` | Every decision that would be expensive to reverse, with its reason and date. |
| `BUILD_PLAN.md` | The plan, the measurements, the running log of what shipped. |
| `RUNBOOK.md` | How to deploy, verify, and recover. Infrastructure IDs live here. |
| `LANDMINES.md` | Traps already paid for. Read before Meta / Cloudflare / audio work. |
| `../SECURITY.md` | Security reporting policy, security invariants, severity guide, and public-testing boundaries. |
| `ENGINEERING_SUPERVISOR.md` | Append-only lane log. Evidence, not intentions. |
| `PROD_READINESS.md` | Dev shortcuts that must be fixed before production, with severity. **Add a row when you take one.** |
| `../CHANGELOG.md` | What changed in the Python, and what broke finding out. |
| [`foundations/README.md`](foundations/README.md) | Product/domain research underneath the PRD — user research, accessibility, clinical/safety grounding, competitive landscape, DPDP/WhatsApp regulatory detail, glossary. Checks the PRD's *research* claims against primary sources the way §0 checks its technical ones. |

## What must be updated when work lands

- Behaviour change → `ARCHITECTURE.md` **and** a test
- Hard-to-reverse choice → `DECISIONS.md`
- Infrastructure change → `RUNBOOK.md`
- A trap that cost time → `LANDMINES.md`, with the symptom that misled you
- Any lane state change → `../control-plane/ACTIVE_LANE_BOARD.md`
- Starting, switching or ending a session → `../control-plane/SESSION_COORDINATION.md`
- Process or coordination change → the control plane **and** `AGENT_SYNC_PROTOCOL.md`
- Any lane closing → `ENGINEERING_SUPERVISOR.md`, with evidence
- **Any code change → `CHANGELOG.md` at the repo root.** Especially breakages
  found during testing: record the *symptom* first, since that is what the next
  person will be searching for.

## House rules inherited from the MeshPilot box

- **Existence is not function.** Prove behaviour with live evidence before
  calling it done. `ffmpeg -version` passing told us nothing; every voice note
  was failing. See `LANDMINES.md`.
- **Value-blind secrets.** Never echo a token. Write value-blind, verify by
  length and hash prefix, and delete synthetic test rows after verifying.
- **Never disturb MeshPilot.** Its checkout serves live customers. Saathi reads
  from it at most; it never writes.
