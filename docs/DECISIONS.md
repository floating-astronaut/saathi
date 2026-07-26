# Decisions

Choices that would be expensive to reverse, with the reason and the date.
Append; do not rewrite. If a decision is overturned, add a new entry that says
so and why — the wrong turn is often the useful part.

---

### D-A · Meta Cloud API direct, no BSP · 2026-07-26
§14 shows messaging is only ~8% of variable cost, so a BSP's per-message markup
buys little. We own WABA onboarding, template submission and support, and absorb
template-rejection risk (R4) ourselves.

### D-B · New repo, new DB, ap-south-1 · 2026-07-26
Saathi is a separate product from MeshPilot and from Glitch Executor: separate
repo, database, AWS account (`559896294326`), lifecycle. Postgres in **Mumbai**
from the first schema write, because moving a database later is the expensive
migration and DPDP full enforcement lands 2027-05-13.

### D-C · Flight search cut from v1 · 2026-07-26
§15's primary metric is D30 retention of daily actives. Reminders and memory are
touched daily; flights twice a year. Cutting it freed week 3 for the safety
classifier and consent — so R7 ships *before* external users rather than
alongside them — and deferred the unresolved Duffel commercial risk.

### D-D · Model is `zai.glm-5` on Bedrock ap-south-1 · 2026-07-26
Chosen on a measured Hinglish entity-accuracy bakeoff, not on price or
reputation — 8 code-mixed reminder utterances scored on times and medicine
names (§15's metric, not WER):

| Model | time | drug | ₹/user/mo |
|---|---|---|---|
| **`zai.glm-5`** | **8/8** | **8/8** | ~220 est. |
| `deepseek.v3.2` | 7/8 | 7/8 (one no-tool-call) | ~135 |
| `zai.glm-4.7` | 6/8 | 8/8 | ~133 |
| `qwen3-235b` | 4/8 | 8/8 | ~48 |
| `glm-4.7-flash` | 3/8 | 8/8 | ~16 |

Accuracy tracked price almost perfectly; the ₹16 option scored 3/8. The failure
mode that separates them is **Hindi fractional time words** — `sawa` (¼ past),
`saade` (½ past), `paune` (¼ to) — where being wrong means a missed cardiac
dose. Only GLM-5 got them all.

It is a **regional** model id (no `global.` prefix), so **inference stays in
India** — which Claude cannot do here, being `global.`-only. Measured cost in
production turned out ≈ **₹60/user/month**, not the ₹220 estimate.

**Overturns PRD §7 and §14.** "Prompt caching is mandatory" was a conclusion
drawn from Anthropic pricing, not a requirement. GLM-5 has no caching; the cost
lever is a tight prefix instead, enforced in code (`SAATHI_PREFIX_TOKEN_BUDGET`,
measured ~1,330 of 3,000).

### D-E · Reject Meta Business Agent for Saathi · 2026-07-26
We are eligible (`is_eligible: true`) and have API access. Rejected anyway: it
becomes the **primary responder**, so inbound messages would never reach the
deterministic pre-LLM safety classifier (R7, Critical). Its knowledge is
business-scoped with a storefront schema and no per-user memory — which is the
entire product. Strong fit for MeshPilot's ecommerce brands; tracked separately.

### D-F · Markdown stripped in code, not requested in the prompt · 2026-07-26
GLM-5 emits `**bold**` regardless of instruction, and WhatsApp renders it
literally. A deterministic transformation should not depend on instruction
following — the same reasoning that makes the safety classifier a regex rather
than a prompt rule. See `wa/format.py`.

### D-G · `mode=indic-en` for STT · 2026-07-26
`transcribe` and `codemix` both return Devanagari, under which the entity
correction pass is structurally dead. `indic-en` returns Latin-script Hinglish
and the same audio then repairs `bomlodipin` → `Amlodipine`. **Overturns PRD §9.**

### D-H · Hostname `saathi.n8nworld.store` · 2026-07-26
Deliberately not a `meshpilot.app` subdomain, to keep the products unbound. The
first attempt used `nuraveda.com`; changed on operator instruction and the
record removed.

### D-I · Secrets via Secrets Manager, never SSM · 2026-07-26
SSM command text is retained and visible in the AWS console. The box fetches its
own secrets with its instance role instead.

### D-J · Meta app shared with MeshPilot · 2026-07-26
Saathi uses Meta app `1571039744742551` and the ayurpet per-BM system-user token
under business `ayurpetofficial` (verified), which owns the `Saatih AI APP` WABA.
Operator decision, made knowingly: it couples the two products at the credential
layer, in exchange for a verified business and a CLOUD_API number today. A
Saathi-owned app remains the clean end state.

### D-K · Training corpus is derived, opt-in, and k-anonymised · 2026-07-26
Operator direction: *"set up training in a way where we do not break any privacy
rule even if training is weak, that is fine."* So privacy holds **by
construction**, not by policy:

- **No transcripts.** The corpus is derived pairs only — `bomlodipin →
  Amlodipine`, `paune gyarah → 22:45`, and slot *shapes* with content stripped.
- **Person and place names are never trainable.** No threshold, no consent flag,
  no override (`privacy.TRAINABLE_KINDS` = medicine, brand).
- **k-anonymity on export.** A pair leaves the box only once ≥5 distinct users
  have produced it, which is what turns "a medicine this person takes" (health
  data about them) into "a word Indian ASR mishears" (a property of the language).
- **Separate opt-in consent.** Under DPDP, improving the model is a different
  purpose from providing the service; it cannot ride on the onboarding consent.
  Revoking purges everything already contributed.
- Dirty or multi-word tokens are **refused, not cleaned** — a cleaner that
  rescues a messy string is where PII leaks in.

The compounding property survives all of this: the correction pass produces
gold-labelled pairs for free, labelled by the user's own read-back confirmation,
so the corpus builds itself from ordinary use with no annotation.
