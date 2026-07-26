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

## Deploying

```bash
ops/deploy.sh
```

Never hand-roll the tar/S3/SSM sequence — that is how a migration step gets
skipped at the wrong moment. The script refuses a dirty tree or a non-`main`
branch on purpose.

## Every commit

- Authored `Tejas Karan Agrawal <help.nuraveda@gmail.com>`
- **SSH-signed.** `git log --pretty='%h %G? %s'` — `%G?` must show `G`.
- Pushed to **both** remotes:
  ```
  git push origin <branch> && git push gitlab <branch>
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
