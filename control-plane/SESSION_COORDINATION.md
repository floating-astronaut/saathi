# Session Coordination

> Who is active right now, and on what. The point is collision avoidance: before
> you claim a lane or touch a surface, check here that no other agent is already
> on it. Update when a session starts, switches lanes, or ends.
>
> Rules: `docs/AGENT_SYNC_PROTOCOL.md` §4. Lane states: `docs/LANE_LIFECYCLE.md`.

## Active sessions

| Agent | Box | Started | Lane | Surface (files/dirs) | Status |
|-------|-----|---------|------|----------------------|--------|
| Claude | runtime `i-01b2c27883acb25ca` | 2026-07-27 | PR-4 | `saathi/scheduling.py`, `saathi/worker/turns.py`, `saathi/agent/tools/handlers.py`, `tests/test_reminder_delivery.py`, `tests/test_scheduling.py` | **ended** — closed at `64a520b`, surfaces released |
| Codex | — | 2026-07-27 | SEC-2 | `SECURITY.md` (new, owns it outright) | **ended** — closed SEC-2 at scan `c4b34ba`, surfaces released |
| Claude | runtime `i-01b2c27883acb25ca` | 2026-07-27 | PR-3 | `saathi/metrics.py`, `saathi/worker/__main__.py`, `ops/alerting/`, `tests/test_metrics.py` | **ended** — closed, surfaces released |

**Base commit is `0f46069`** (2026-07-27, end of day). `main` moved **51 times**
on 2026-07-27, so any figure written here goes stale within the hour — do not
trust this line, run:

    git ls-remote https://github.com/Nuraveda-Labs/saathi.git main

Rebase before committing if your session started earlier. Concurrent sessions
rebased without a conflict on 2026-07-27 because each declared its surfaces
here first — but note that codex twice wrote directly into `/home/ubuntu/saathi`
without a row here, and both times the work had to be rescued by hand
(`2a11443`, `2d65854`). Declaring surfaces only helps if everyone does it.

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
    scratch clones             created by sessions for a clean base. Stale within
                               hours. Delete when the lane closes.

This has already misled once: on 2026-07-27 the deployed tree read three commits
behind, and the honest conclusion from `git log` there was that work was missing
when it was not. **Trust `git ls-remote`, not a local HEAD:**

    git ls-remote https://github.com/Nuraveda-Labs/saathi.git main
    git ls-remote https://gitlab.com/nuraveda-lab/saathi.git main

If you create a scratch clone, remove it when you are done. A clone nobody owns
is a tree the next session will read and believe.

## Recent handoffs

> When you hand a lane to another agent, note it here so they have context.

- _none yet_
