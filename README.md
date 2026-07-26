# saathi-site

Public site for Saathi — landing page plus the policy pages Meta app review
checks: `/privacy/`, `/terms/`, `/data-deletion/`.

Adapted from [bundui/waitly](https://github.com/bundui/waitly) (Next.js +
Tailwind + shadcn/ui), configured for **static export** so Cloudflare Pages
serves it with no Node runtime and no `next-on-pages` adapter.

## Why this lives on the `site` branch

The application is on `main`. Cloudflare Pages builds from **`site`** only, so
ordinary application pushes never trigger a site rebuild — and a site change
never redeploys the app.

    pnpm install
    pnpm build          # -> out/
    pnpm dlx wrangler@4 pages deploy out --project-name saathi-site --branch site

## Cloudflare

| | |
|---|---|
| Project | `saathi-site` |
| Production branch | `site` |
| Build command | `pnpm build` |
| Output directory | `out` |
| Domain | `n8nworld.store` |

`saathi.n8nworld.store` is the WhatsApp webhook and is **not** part of this
project — it is a Cloudflare Tunnel to the ap-south-1 box. Do not point it here.
