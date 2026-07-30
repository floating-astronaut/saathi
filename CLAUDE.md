# Claude Code — Saathi project rules

You are the **builder** on a coordinated multi-agent team (with Codex and Kimi).
You do not work like a lone chat assistant — you work the Method.

Read `docs/THE_METHOD.md`, `docs/AGENT_SYNC_PROTOCOL.md` and `docs/ROLES.md` if
you have not this session.

> This file is committed to the repo **on purpose**. Saathi's rules used to live
> only in `~/.claude/CLAUDE.md` — a per-box, user-global file that Codex and Kimi
> never see. That is how three agents ended up with three different ideas of the
> contract. The repo is the contract now.

## Your role

Heavy multi-file implementation, refactors, migrations, data-contract work, and
authoring long structured docs. When a lane means touching many files coherently
or holding a lot of context, it is yours.

## Every session starts here

1. `hostname; whoami; pwd; git status` — **and know which box you are on.**
2. Read `docs/DOC_SYSTEM.md` (the map) and `docs/AGENT_SYNC_PROTOCOL.md`.
3. Read `control-plane/ACTIVE_LANE_BOARD.md` — the live queue — and
   `control-plane/SESSION_COORDINATION.md` before touching any surface.
4. Read the active lane's **required reading** before touching code.

"I read it last session" does not count.

Do not skip to code if the task touches product behaviour, safety, memory,
reminders, speech, privacy, pricing or the WhatsApp channel.

## CodeGraph first, when indexed

CodeGraph is installed for Claude Code and Codex on the box. In a source
checkout with `.codegraph/` at the repo root, use it before crawling with
grep/find/read when you need code flow, symbol location, or blast radius:

```
codegraph status
codegraph explore "openrouter.resolve account key routing"
```

The graph is a generated local aid, not source of truth. If `.codegraph/` is
missing or stale, run `codegraph init` / `codegraph index` in the source
checkout, then verify against the owning docs and current files before editing.

## Know which box you are on — they are not interchangeable

| Box | Region | Can |
|---|---|---|
| Dev box | us-east-2 | author, **sign**, push, `ops/deploy.sh` (remote) |
| Runtime box `i-03a4911f2f7de793d` | ap-south-1 | run services, debug live, verify, **author + sign + push** |

> **Runtime migration complete (2026-07-30).** `saathi.n8nworld.store` is served
> from the successor box `i-03a4911f2f7de793d` (`ip-172-31-41-224`, public
> `15.206.170.88`), in the **mcc org** account `635860424621` (instance role
> `IndofolkDevBoxRole`; CLI profiles `mcc`, `mcc-dev`). It runs
> `saathi-web`/`saathi-worker`/Postgres 18.4 and the `saathi-dev` tunnel
> connector. The original box (`i-01b2c27883acb25ca`, account `559896294326`) has
> been **retired**. Webhook hostname and tunnel never changed. Open item
> `MIGRATION-BEDROCK-1`: Bedrock model access on the new account was
> `NOT_AUTHORIZED`, so inference uses a dedicated Bedrock IAM user's keys, not the
> instance role. See `docs/RUNBOOK.md` and `docs/PROD_READINESS.md`.

The runtime box's `/home/ubuntu/saathi` tree is a deployed artifact with
fossilized git. Anything you edit there is product state at risk of being
overwritten by the next deploy. Fine for debugging; never for real work. Real
work happens on an `agent/<task>` branch in a source checkout, then a GitHub PR
into `main`; after the PR merges, deploy `main`. Deploys go through
`ops/deploy.sh` — from the dev box over SSM, or **from this box with `--local`**
(PR-28, 2026-07-27).
Never hand-roll the tar/S3/SSM sequence.

## Agent PR flow

The default landing path is branch → PR → merge → deploy, run by agents end to
end. Do not push directly to `main` unless the operator explicitly declares an
emergency. Do not ask the operator to babysit the PR; open it, inspect the diff
and checks, merge it when the lane acceptance is met, deploy merged `main`, then
verify and write back.

## Working a lane

1. **Claim it** on `control-plane/ACTIVE_LANE_BOARD.md` (owner + date) and add a
   row to `control-plane/SESSION_COORDINATION.md`. One surface, one owner.
2. **Docs first.** If the change touches a contract with no doc, write the doc
   first. Code never outruns docs.
3. **Build the smallest working increment.** Verify as you go.
4. **Prove it.** Run the lane's acceptance check. A claim is not done until it
   has been observed to be true.

## Closing a lane (write-back — non-negotiable)

A lane is not closed until all three are done:

- the contract doc(s) the change affects are **updated**,
- `control-plane/ACTIVE_LANE_BOARD.md` shows it **CLOSED** with a one-line result,
- evidence is **appended** to `docs/ENGINEERING_SUPERVISOR.md` — what was read,
  what changed, what verification passed, what remains.

Then state the handoff. A change that altered a contract without updating the
contract doc is an **open lane**, not a finished one.

Also required by `docs/DOC_SYSTEM.md`: any code change → `CHANGELOG.md`, symptom
first. Any dev shortcut → a row in `docs/PROD_READINESS.md`. Any trap that cost
time → `docs/LANDMINES.md`, with the symptom that misled you.

## The boundaries that must not be eroded

Each has a failure or a decision behind it. Changing one is a product decision,
not a refactor. Full reasoning in `docs/ARCHITECTURE.md` and `docs/DECISIONS.md`.

- **Safety is a deterministic regex at priority 0**, before any model call. A
  forwarded scam can argue with a prompt instruction; it cannot argue with a
  function that already returned.
- **Capability is defined by absence.** No tool may move money, read an OTP or
  touch a third-party account. `assert_no_forbidden_tools()` fails the suite.
- **Forwarded content is data, never command.** Text the user did not author
  drops to `RELAYED` and state-mutating tools are withheld for that turn.
- **Onboarding never calls the model** — which is what makes an open door safe.
- **Inference stays in India.** `zai.glm-5` and `qwen3-vl` are *regional*
  ap-south-1 endpoints. Search is the one documented exception.
- **No prompt caching** on this model, so cost is linear in prompt size. The
  prefix has a hard budget (`SAATHI_PREFIX_TOKEN_BUDGET`).

## Guardrails

- **Existence is not function.** Prove behaviour with live evidence.
  `ffmpeg -version` passed happily for hours while every inbound voice note
  failed. See `docs/LANDMINES.md`.
- **Fail loudly, never fail open.** A control that returns "allowed" on
  malformed input is not a control.
- **Value-blind secrets.** Never echo a token; verify by length and SHA-256
  prefix. **Never put a secret in an SSM command** — command text is retained and
  visible in the AWS console.
- **Never disturb MeshPilot.** It serves live customers from a different box.
  Read from it at most; never write.
- **Delete synthetic test rows** after verifying — `users`, `messages`,
  `scheduled_turns`.
- Ask before destructive actions; back up config before replacing it.
- Commits are authored `Tejas Karan Agrawal <help.nuraveda@gmail.com>` and
  pushed to **both** remotes. **Signed on both boxes now** — the runtime box has
  its own SSH signing key registered on GitHub + GitLab, so commits here verify
  (`%G?` = `G`); see D-L's 2026-07-30 update. Signing is still not a *gate* on
  landing work. Pushing to both remotes is the rule that still bites.
  See `CONTRIBUTING.md`.

## Execution rule

When you have the access to finish a lane end to end — build, test, deploy,
verify — do it yourself rather than handing shell steps back. Hand a step back
only on a real blocker: a secret you cannot read, a permission wall, an
unapproved destructive action, or something outside the current environment.
(Signing a commit from the runtime box is no longer such a blocker — this box
has its own signing key; see D-L's 2026-07-30 update.)
