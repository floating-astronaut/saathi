# Saathi Doc System

Last updated: 2026-07-26
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
2. `PRD.md` — the research and the product argument
3. `BUILD_PLAN.md` — what was decided, measured, and why
4. the tail of `ENGINEERING_SUPERVISOR.md` — recent closures and queued work
5. `LANDMINES.md` — **read this before touching Meta, Cloudflare or ffmpeg**

"I read it last session" does not count. A lane is **not closed** until the
contract docs are updated and evidence is appended to `ENGINEERING_SUPERVISOR.md`.

## Precedence

1. direct operator instruction
2. this file
3. product law — `PRD.md`, `ARCHITECTURE.md`
4. decisions — `DECISIONS.md`
5. execution — `BUILD_PLAN.md`, `ENGINEERING_SUPERVISOR.md`, `RUNBOOK.md`
6. current code
7. prior claims in chat

**The PRD is research, not scripture.** It is the best available argument for
why this product should exist, and several of its technical claims have been
measured and found wrong (see `PRD.md` §0 and `LANDMINES.md`). Where the PRD and
a measurement disagree, the measurement wins and `DECISIONS.md` records it.

## Doc map

| Doc | Owns |
|---|---|
| `PRD.md` | The problem, the user, the research, the product argument. Amended, never silently overwritten. |
| `ARCHITECTURE.md` | How the system is built and why each boundary exists. |
| `DECISIONS.md` | Every decision that would be expensive to reverse, with its reason and date. |
| `BUILD_PLAN.md` | The plan, the measurements, the running log of what shipped. |
| `RUNBOOK.md` | How to deploy, verify, and recover. Infrastructure IDs live here. |
| `LANDMINES.md` | Traps already paid for. Read before Meta / Cloudflare / audio work. |
| `ENGINEERING_SUPERVISOR.md` | Append-only lane log. Evidence, not intentions. |
| `PROD_READINESS.md` | Dev shortcuts that must be fixed before production, with severity. **Add a row when you take one.** |
| `../CHANGELOG.md` | What changed in the Python, and what broke finding out. |
| [`foundations/README.md`](foundations/README.md) | Product/domain research underneath the PRD — user research, accessibility, clinical/safety grounding, competitive landscape, DPDP/WhatsApp regulatory detail, glossary. Checks the PRD's *research* claims against primary sources the way §0 checks its technical ones. |

## What must be updated when work lands

- Behaviour change → `ARCHITECTURE.md` **and** a test
- Hard-to-reverse choice → `DECISIONS.md`
- Infrastructure change → `RUNBOOK.md`
- A trap that cost time → `LANDMINES.md`, with the symptom that misled you
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
