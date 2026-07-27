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

### D-L · The runtime box may author and push; signing is not a gate · 2026-07-27
Operator decision, stated plainly: *"this is single person github account and I
only work here, that rule is cosmetic."*

The signing requirement was inherited from the MeshPilot habit set, where it
distinguishes commits from several contributors. Saathi has one author and two
private remotes on accounts he alone controls, so a signature proves something
nobody needs proved, while the rule's real cost was concrete — it blocked work
authored on the runtime box from ever landing, which is how the SSH change ended
up live with three docs still claiming no inbound port was open.

So: **the dev box signs because it has the key; the runtime box pushes unsigned.**
Both are legitimate. `CONTRIBUTING.md` is amended to match.

What does *not* change:
- Every commit is still authored `Tejas Karan Agrawal <help.nuraveda@gmail.com>`.
- Every commit still goes to **both** remotes.
- `ops/deploy.sh` still refuses a dirty tree or a non-`main` branch, and deploys
  are still artifact-shipped rather than pulled on the box.
- PR-22 still stands: the runtime box holding forge write credentials is a real
  blast-radius question, and this decision widens it rather than resolving it.

**Reverse this if a second contributor appears.** At that point signatures start
carrying information again, and the runtime box should drop to read-only tokens.

### D-M · Saathi moves to an Indian number on a second WABA · 2026-07-27
The product now runs on **+91 8071 581 944** (`phone_number_id 1266402176549539`)
under WABA `1687148075730227`, display name **"Indofolk AI"**, currency **INR**.

The old number was **+1 437-539-7958** — Canadian. PR-5 recorded that as blocking
*pricing*, because India messaging rates and template pacing key off the sender's
country, so §14's cost model never held. It also blocked *trust*: this product's
own priority-0 classifier teaches elders to distrust unknown foreign numbers, and
we were asking them to accept exactly that.

**The two WABAs sit under the same verified business.** `ayurpetofficial`
(`935287898727459`) is only the portfolio's display label; its legal entity is
**INDOFOLK WELLNESS PRIVATE LIMITED**, verified 19 Feb 2026, GSTIN
`07AAHCI7432A1ZV` — the same entity our privacy and terms pages already name. So
this is a second WABA, not a second company, and business verification carried
over without re-submission.

**Why the display name is "Indofolk AI" and not "Saathi".** "Saathi" was declined.
The reason is structural, not linguistic: Meta checks whether the name relates to
the verified business, and the business's *registered website* is
`indofolkwellness.com` — a B2B pet products company, with zero mentions of Saathi
or of elders. Nothing on record connected the word to the business. "Indofolk AI"
matches the legal name and passed first time.

This is a knowing trade. An elder receives medication reminders from a company
name rather than the companion they talk to, which costs exactly the familiarity
the PRD argues for. **Reversible:** put a Saathi page on `indofolkwellness.com`,
then re-submit "Saathi" — an approved display name can be changed, subject to a
further review.

**Vobiz is the telco, not the BSP — D-A survives.** The Indian DID came from Vobiz
(`Ilailimitado Private Limited`), ₹100 setup + ₹500/month, voice-only. Their
WhatsApp product is a Tech Provider arrangement: their docs promise "instant
setup, no verification needed", which works because *they* onboard the number
onto your WABA through their Meta app, and messages then bill per conversation on
their balance. That is precisely what **D-A** rejected. So the number was verified
onto **our own** WABA by voice OTP and registered on Cloud API ourselves. Vobiz
supplies a number; nothing else.

Their embedded-signup flow did briefly subscribe Vobiz's app to the WABA's
webhooks, giving them a copy of every inbound message. Removed the same day — see
`PROD_READINESS.md` PR-29.

### D-N · The assistant is named Indofolk AI, in chat as well as on the header · 2026-07-27
Operator decision, made after "Indofolk AI" was approved as the WhatsApp display
name (D-M). A user was otherwise shown three names at once: the sender header,
the greeting, and the policy pages each said something different.

**Scope: user-facing copy only.** `onboarding.py`, `identity.py`, `agent/prompt.py`,
and the policy pages. The repo, database, box, GCP project, prefix-budget env var
and the CloudWatch namespace stay `saathi` — no user sees them, and renaming the
metrics namespace in particular would break the alarms silently, since the IAM
grant is scoped to it by condition.

**The Hindi keeps `saathi` as a common noun.** It means *companion*, so
"Main *Indofolk AI* hoon — aapki saathi" reads naturally where a bare substitution
would have a company introducing itself in the first person. PRD §2 argues the
product's value is a familiar companion; the name changed, the register did not.

**Cost, accepted knowingly:** "Saathi" was a warm Hindi word an elder recognises.
"Indofolk AI" is a company name. D-M records why — the display name had to relate
to the verified business, and the business's registered site is a pet-products
company with no mention of Saathi. Reversible if that site ever presents Saathi
as its product.

### D-O · OpenRouter routes to our own Mumbai Bedrock; fallbacks are disabled · 2026-07-27
Saathi will call `z-ai/glm-5` through OpenRouter instead of `boto3` → Bedrock
directly. Design in `AI_ROUTING.md`. **Not built yet** — this records the choice
and its conditions before the code exists.

**Why at all.** Per-account API keys with hard USD caps, minted programmatically.
That is `PROD_READINESS.md` PR-15's fix: today an onboarded user can send
unlimited voice notes and nothing enforces §14's cap. Spend becomes attributable
per paying household and a runaway loop burns one cap, not the balance.

**What does not change, and this is the point.** The BYOK credential on the
Indofolk AI workspace (`718e8438-…`) is `amazon-bedrock`, named "Indian Box",
`sort_order: 0`, `is_fallback: false` — **the same Mumbai `ap-south-1` account
Saathi already uses**. And `z-ai/glm-5` is the same model as `zai.glm-5`.

So **D-D survives intact**: the model that scored 8/8 on Hindi fractional time
words is the model still answering, and inference still happens in India.
OpenRouter is a router and a meter, not a new inference location. If either the
slug or the region ever changes, D-D's bakeoff must be re-run — it was measured
on that model, and `paune gyarah → 22:45` being wrong means a missed dose.

**The condition that makes it safe.** Every request sends
`provider: {allow_fallbacks: false}`, as a constant in the client and not a
setting. Without it, a Bedrock outage silently reroutes an elder's medication
conversation to a US provider and nothing says so. With it the request fails and
Saathi surfaces an error. Same reasoning as D-F: a deterministic guarantee must
not depend on instruction-following or on someone remembering a flag.

**What is honestly given up.** D-D's claim was "inference stays in India". That
remains true. But the prompt now **transits OpenRouter's infrastructure** to
reach Mumbai, so "the data never leaves India" is no longer accurate and the
privacy policy must not imply it. That is a real change in processors under DPDP,
accepted knowingly, and it is the reason this decision is written down rather
than treated as a config change.

**Reverse it** by pointing the client back at `boto3`. The model, region and
account are unchanged, so reversal costs nothing but the metering.
