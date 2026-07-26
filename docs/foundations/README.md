# Foundations

Product and domain research, as distinct from `docs/ARCHITECTURE.md`,
`docs/DECISIONS.md`, and `docs/RUNBOOK.md`, which cover engineering. These
docs answer *who is this for, what does the evidence actually say, what does
the law require* — the ground the product argument in `docs/PRD.md` stands
on, and in a few places corrects.

**Read `docs/PRD.md` §0 first regardless** — it already lists the PRD's
technical claims that were measured and found wrong. These docs go further:
they check the PRD's *research* claims (adoption stats, accessibility
principles, legal dates) against primary sources, the same way §0 checked
its technical ones.

| Doc | Covers | Corrects/sharpens PRD on |
|---|---|---|
| [`USER_RESEARCH.md`](USER_RESEARCH.md) | Who the user is: adoption, literacy, script, vision/motor, who sets up the phone, voice vs. typing, metro vs. smaller cities | §2's adoption stats — the PRD's own cited source doesn't contain the numbers attributed to it |
| [`ACCESSIBILITY.md`](ACCESSIBILITY.md) | Testable conversational-accessibility rules, sourced | §6 — mostly supports it, but shows confirmation and repetition are two different rules that need separating, not one instinct |
| [`SAFETY_AND_CLINICAL.md`](SAFETY_AND_CLINICAL.md) | Medication-adherence evidence, red-flag symptoms, verified emergency numbers, elder-fraud phrasing for the classifier | §12 and `saathi/safety/classifier.py` directly — identifies a hypoglycemia gap and a digital-arrest gap in current pattern coverage |
| [`COMPETITIVE_LANDSCAPE.md`](COMPETITIVE_LANDSCAPE.md) | Indian eldercare, WhatsApp-based assistants, global AI companions for seniors | Not directly cited in the PRD; fills a gap — no competitive analysis existed before this |
| [`REGULATORY_INDIA.md`](REGULATORY_INDIA.md) | DPDP Act/Rules phased timeline, consent, cross-border transfer, health-data tiering, WhatsApp Business policy | §13 — corrects the Section 16 (whitelist vs. blacklist) characterization and the ₹250cr/₹200cr penalty conflation |
| [`GLOSSARY.md`](GLOSSARY.md) | Product vocabulary: companion/assistant/bot, reminder/nudge/check-in, fact/memory, handle/identity/user, capability/tool, relayed/typed | Not a correction — a consistency reference, grounded in current code |

## How these were built

Each doc cites primary sources where they exist (government instruments,
peer-reviewed papers, official platform docs) and marks anything that
couldn't be verified as **unverified**, stated plainly, rather than filled in
with a plausible-sounding number. Where a claim in the PRD turned out to be
unsupported, wrong, or attributed to the wrong source, that's called out by
name in the doc it affects — the same discipline `docs/PRD.md` §0 already
applies to the PRD's technical claims, extended to its research claims.

## What these are not

Not architecture (`docs/ARCHITECTURE.md` owns that), not decisions
(`docs/DECISIONS.md`), not a runbook (`docs/RUNBOOK.md`), and not a
replacement for the PRD — the PRD is still the product argument. These are
the evidence underneath it, checked.
