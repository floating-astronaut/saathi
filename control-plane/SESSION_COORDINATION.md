# Session Coordination

> Who is active right now, and on what. The point is collision avoidance: before
> you claim a lane or touch a surface, check here that no other agent is already
> on it. Update when a session starts, switches lanes, or ends.
>
> Rules: `docs/AGENT_SYNC_PROTOCOL.md` §4. Lane states: `docs/LANE_LIFECYCLE.md`.

## Active sessions

| Agent | Box | Started | Lane | Surface (files/dirs) | Status |
|-------|-----|---------|------|----------------------|--------|
| _none_ | | | | | |

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
| Dev box | us-east-2 | author, **sign**, push, `ops/deploy.sh` |
| Runtime box `i-01b2c27883acb25ca` | ap-south-1 | run services, debug live, verify — **cannot sign** |

Edits made in the runtime box's checkout are committed nowhere and are
overwritten by the next deploy. If you are working there, say so in your row —
otherwise the next agent will assume your changes exist in git and they do not.

## Recent handoffs

> When you hand a lane to another agent, note it here so they have context.

- _none yet_
