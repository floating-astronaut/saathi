# Vendor API reference — captured, not authored

Third-party API documentation, copied here so a debugging session does not depend
on a vendor's website being reachable, unchanged, or renderable.

Every page in this project's history that we needed under pressure was one of:
JavaScript-rendered and unreadable by any tool (`developers.facebook.com`,
`dev.wix.com` — both returned only a `<title>`), moved without a redirect, or
quietly rewritten so that what we read last month is not what is there now.

## The one rule: these are transcripts

**Capture verbatim. Never improve, summarise, or correct them.** A vendor doc
that has been edited to match what we believe is no longer evidence — it is our
opinion wearing the vendor's clothes, and it will be trusted as fact by whoever
reads it next at 2am.

If the vendor is wrong, say so in **our** docs — `LANDMINES.md` for a trap that
cost time, `DECISIONS.md` for a choice made because of it — and link back here.
That is the same separation `PRD.md` §0 uses: preserve the original claim, record
the measurement beside it.

## Each file carries

- the **source URL** and the **date captured**
- the API **version** it describes, where the vendor states one
- nothing else of ours

## Re-capturing

Vendors change these without notice and without changelogs. When something stops
matching observed behaviour, re-capture the page, keep the old file, and note the
difference — the diff is usually the answer to whatever just broke.

| File | Source | Captured |
|---|---|---|
| `meta/conversational-components.md` | developers.facebook.com — Conversational Components | 2026-07-27 |
| `meta/waba-subscribed-apps.md` | developers.facebook.com — Graph API v25.0 | 2026-07-27 |
| `vobiz/xml-dial.md` | vobiz.ai — Dial XML — **summary, not a transcript** | 2026-07-27 |

## Meta docs need a rendering browser

`developers.facebook.com` and `dev.wix.com` return only a `<title>` to plain HTTP
fetching — they render in JavaScript. Capture them through the browser tooling
(`navigate` then `get_page_text`), not `curl` or a fetch tool. A fetch tool that
*summarises* is worse than one that fails: it returns something plausible that is
not the page, and a summary filed as a transcript is the exact failure this
directory exists to prevent. Mark it loudly when that happens, as
`vobiz/xml-dial.md` does.
