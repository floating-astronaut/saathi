# Contributing to Saathi

## Branches — the one thing to get right

This repo holds **two different products on two branches**. Mixing them is the
mistake that costs an afternoon.

```
main  ──▶  the application  ──▶  ap-south-1 box  (S3 artifact + SSM + systemctl)
site  ──▶  the public site  ──▶  Cloudflare Pages → n8nworld.store  (git push)
```

| | `main` | `site` |
|---|---|---|
| Language | Python 3.14, FastAPI | TypeScript, Next.js static export |
| Contents | agent, worker, schema, tests | landing page, privacy, terms, data-deletion |
| Deployed by | artifact upload + `systemctl restart` | Cloudflare Pages, on push |
| Tests | `uv run pytest -q` | `pnpm build` must succeed |

**Rules**

1. Application code never lands on `site`. Site code never lands on `main`.
2. Cloudflare Pages builds **only** `site` (`production_branch: site`,
   `preview_branch_excludes: ["main"]`). If you see Pages running
   `npx next build` and complaining *"Couldn't find any `pages` or `app`
   directory"*, it is building `main` — fix the Pages branch settings, do not
   add a Next.js app to `main`.
3. Preview builds are allowed for `site-*` branches. Use them to review copy
   before it is public.


## Agent workflow — branch, PR, merge, deploy

Agents do **not** normally push straight to `main`, and they do not author real
work in `/home/ubuntu/saathi`. The default flow for application work is:

1. Start from current `main` in a real source checkout. On the runtime box, make
   a fresh scratch clone such as `/tmp/saathi-<lane>`; `/home/ubuntu/saathi` is
   the deployed artifact, not a workbench.
2. Create a task branch named `agent/<lane-or-task>`.
3. Claim/update the lane and session coordination docs before editing shared
   surfaces.
4. Make the change, update required docs, and run the relevant tests on the
   branch.
5. Push the branch and open a GitHub PR into `main`. The agent opens it; the
   operator does not need to be kept in the loop unless there is a real blocker.
6. The agent reviews the PR diff/checks itself, then merges it to `main` when the
   lane acceptance is met. Use a normal merge/squash/merge-commit as appropriate;
   do not leave unmerged agent branches carrying product state.
7. Deploy **only from `main` after the PR is merged**, then verify on the runtime
   box and write back closure evidence.

Direct pushes to `main` are for explicit operator emergencies only, and the
reason must be written in `docs/ENGINEERING_SUPERVISOR.md`.

## Deploying

Which box you are on decides the flag, and nothing else:

```bash
ops/deploy.sh            # from the dev box (us-east-2): tar -> S3 -> SSM
ops/deploy.sh --local    # from the runtime box (ap-south-1): no S3, no SSM
```

`--local` skips the transport and **nothing else** — same clean-tree gate, same
`uv sync`, same tests, same ledgered migrations, same restart, same
verification, from the same `ops/deploy_onbox.sh` the artifact path runs. It
exists because until 2026-07-27 there was no way to deploy from the box, and a
session that had to fixed a live vulnerability by copying four modules in by
hand instead. Do not do that again; run the script.

You cannot pick the wrong one silently: each mode checks the instance ID and
refuses on the other box, with a message that names the flag you wanted.

Never hand-roll the tar/S3/SSM sequence, and never hand-roll the local
equivalent either — that is how a migration step gets skipped at the wrong
moment. Deploy still only accepts `main`: after the PR is merged, deploy that
merged `main` commit. Both modes refuse a dirty tree or a non-`main` branch on
purpose;
`--local` also refuses a source with no saathi remote, which is what the
vestigial `.git` inside `/home/ubuntu/saathi` looks like. See `docs/RUNBOOK.md`
for that trap, for rehearsing a deploy against a scratch target, and for putting
the previous tree back.

## Every commit

- Authored `Tejas Karan Agrawal <help.nuraveda@gmail.com>`
- **SSH-signed when authored on the dev box**, which holds the signing key.
  Commits from the runtime box are unsigned by necessity — see `DECISIONS.md`
  D-L. Signing is not a gate on landing work here.
- `%G?` is **not** a usable check on either box: SSH signature *verification*
  needs `gpg.ssh.allowedSignersFile`, which is unset, so correctly signed commits
  report `N`. To test whether a commit is signed at all:
  ```
  git cat-file commit HEAD | grep -q '^gpgsig' && echo signed
  ```
- Pushed to **both** remotes, and **verified on both**. On the runtime/source
  box, the `gitlab` remote uses the SSH alias `gitlab-saathi`; do not switch it
  back to HTTPS. The old HTTPS/OAuth helper path expires and has repeatedly left
  GitHub ahead of GitLab. See `docs/LANDMINES.md`.
  ```
  git push origin <branch> && git push gitlab <branch>
  git ls-remote origin <branch> | cut -c1-7; git ls-remote gitlab <branch> | cut -c1-7
  ```
- Never a token in a remote URL. Never a secret in a commit, a log line, or an
  SSM command.

## Before you write code

Read, in this order — every session, not once:

1. [`docs/DOC_SYSTEM.md`](docs/DOC_SYSTEM.md)
2. [`docs/PRD.md`](docs/PRD.md) — including §0, which lists what has since been
   measured wrong
3. the tail of [`docs/ENGINEERING_SUPERVISOR.md`](docs/ENGINEERING_SUPERVISOR.md)
4. [`docs/LANDMINES.md`](docs/LANDMINES.md) — **before touching Meta,
   Cloudflare or audio**

## When you land work

| You changed | Also update |
|---|---|
| behaviour | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) **and** a test |
| something hard to reverse | [`docs/DECISIONS.md`](docs/DECISIONS.md) |
| infrastructure | [`docs/RUNBOOK.md`](docs/RUNBOOK.md) |
| anything in the Python | [`CHANGELOG.md`](CHANGELOG.md) — symptom first |
| a trap that cost you time | [`docs/LANDMINES.md`](docs/LANDMINES.md) |
| a shortcut you took "because this is dev" | [`docs/PROD_READINESS.md`](docs/PROD_READINESS.md) |
| a lane closing | [`docs/ENGINEERING_SUPERVISOR.md`](docs/ENGINEERING_SUPERVISOR.md), with evidence |

## Adding a capability

Register it in `saathi/capabilities.py`. Do **not** add a branch to
`pipeline.handle_message` — a test asserts the dispatcher never names an
individual capability, and that test exists because the pipeline was once an
if/elif ladder that nobody could reason about.

```python
register(simple("weather", 60,
                lambda ctx: "mausam" in ctx.text.lower(),
                handle_weather))
```

If your capability adds a **tool**, classify it in `saathi/provenance.py` as
read-only or state-mutating. A test fails the build otherwise, because an
unclassified tool would silently be allowed to run on forwarded content.

## Non-negotiables

These are not style preferences. Each one has a failure behind it.

- **No tool may move money, read an OTP, or access a third-party account.**
  This is what makes prompt injection harmless rather than merely discouraged.
- **Safety runs before the model.** Always. It is priority 0 and it is a regex.
- **Prove it works.** `ffmpeg -version` passed for hours while every inbound
  voice note failed. Existence is not function.
- **Fail loudly.** A control that returns "allowed" on malformed input is not a
  control.
- **Never disturb MeshPilot.** `/home/ubuntu/glitch-grow-ads-agent-private`
  serves live customers. Read from it at most; never write.
