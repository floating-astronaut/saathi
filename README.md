# saathi-site — the `site` branch

Public website for Saathi: the landing page plus the three policy pages Meta app
review checks — `/privacy/`, `/terms/`, `/data-deletion/`.

> ## ⚠️ You are on the `site` branch
>
> This repo holds **two different products on two branches**.
>
> | Branch | Contains | Deploys to |
> |---|---|---|
> | `main` | the application — Python, FastAPI, agent, worker | the ap-south-1 box |
> | **`site`** ← you are here | this website — Next.js static export | Cloudflare Pages → `n8nworld.store` |
>
> **Do not put application code here, and do not put site code on `main`.**
> Cloudflare Pages builds `site` only (`preview_branch_excludes: ["main"]`).
> If a Pages build fails with *"Couldn't find any `pages` or `app` directory"*,
> it is building `main` — fix the Pages branch setting rather than adding a
> Next.js app to `main`.

Adapted from [bundui/waitly](https://github.com/bundui/waitly) (MIT) — Next.js +
Tailwind + shadcn/ui — configured for **static export** so Pages serves it with
no Node runtime and no `next-on-pages` adapter.

## Develop

    pnpm install
    pnpm dev            # http://localhost:3000
    pnpm build          # -> out/   (must succeed before you push)

## Deploy

Push to `site`. Cloudflare Pages builds and publishes automatically.

    git push origin site && git push gitlab site

Direct upload still works for emergencies, but git is the normal path — one
story about how the live site got there:

    pnpm dlx wrangler@4 pages deploy out --project-name saathi-site --branch site

## Cloudflare

| | |
|---|---|
| Project | `saathi-site` |
| Production branch | `site` |
| Build command | `npx next build` |
| Output directory | `out` |
| Domains | `n8nworld.store`, `www.n8nworld.store` |

`saathi.n8nworld.store` is the **WhatsApp webhook** — a Cloudflare Tunnel to the
ap-south-1 box. It is not part of this project. Do not point it here.

## Editing the policy pages

The operating entity is defined once in `components/operator.tsx` and rendered
on all three pages, so they cannot drift apart on who is legally responsible.
It must match the business verified in Meta Business Manager — a reviewer
cross-checks them, and a mismatch reads as impersonation.

The policy text describes what the system **actually does** (7-day voice
retention, data in Mumbai, no payments or OTP handling by design, the real
deletion phrases). If you change product behaviour on `main`, check whether
these pages are still true.
