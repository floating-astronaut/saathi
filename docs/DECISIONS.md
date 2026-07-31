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

### D-J · Meta app shared with MeshPilot · 2026-07-26 — SUPERSEDED 2026-07-27
Saathi used Meta app `1571039744742551` and the ayurpet per-BM system-user token
under business `ayurpetofficial` (verified), which owns the `Saatih AI APP` WABA.
Operator decision, made knowingly: it coupled the two products at the credential
layer, in exchange for a verified business and a CLOUD_API number today. A
Saathi-owned app remained the clean end state.

**Superseded by D-X.** The clean end state arrived: Saathi has its own app, its
own app secret, and its own permanent system user token. Nothing is shared with
MeshPilot at the credential layer any more.

### D-X · Saathi's own Meta app; the business was never borrowed · 2026-07-27
The migration off `1571039744742551`, and the correction of a thing three
documents had been repeating.

**Own app.** **Indofolk AI `1019173634258664`** is the sole subscriber to WABA
`1687148075730227`. Its app secret verifies every inbound webhook — a body signed
with it returns 200, the identical body signed with MeshPilot's returns 403. The
access token is `type: SYSTEM_USER` with `expires_at: 0`, on system user
`122098890723360160`, scoped to `whatsapp_business_messaging` and
`whatsapp_business_management`. MeshPilot is unsubscribed.

**Sequenced so inbound never had a gap:** register and verify the new callback
while that app was subscribed to nothing → subscribe it *alongside* MeshPilot so
both delivered → swap `WA_APP_SECRET` and `WA_ACCESS_TOKEN` in one write →
unsubscribe MeshPilot. At every point at least one delivery path verified. Do it
in any other order and inbound fails silently, which for this product means an
elder receiving nothing and no log line naming them.

**The business was never borrowed, and D-M said so first.** `ayurpetofficial`
(`935287898727459`) is a display label. The legal entity is **INDOFOLK WELLNESS
PRIVATE LIMITED**, verified, GSTIN `07AAHCI7432A1ZV` — the entity the privacy and
terms pages already name. Graph agrees: `verification_status: verified` on the
business, `ownership_type: SELF` on the WABA. PR-5 nonetheless called it borrowed
for a further day after D-M recorded the truth.

That is the part worth remembering. **A fact resolved in one document does not
resolve the rows that repeat it**, and a caveats journal is exactly where a stale
repetition survives longest, because every row there is *supposed* to describe
something unfinished. Both were reconciled 2026-07-27.

**Reverse it** only by a deliberate move back to a shared app, which would
recouple two products at the credential layer for no remaining benefit.

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

**Update · 2026-07-30 — the runtime box now signs too.** It was given its own
SSH signing key (`~/.ssh/saathi_github_ed25519`), git configured to sign by
default (`gpg.format=ssh`, `commit.gpgsign=true`,
`gpg.ssh.allowedSignersFile=~/.config/git/allowed_signers`), and the public key
registered as a **signing** key on both GitHub and GitLab. So the operative line
above — *"the runtime box pushes unsigned"* — no longer holds: commits authored
on either box are SSH-signed and verify (`%G?` = `G`). Signing is still **not a
gate** on landing work; this only removes the friction that blocked
runtime-authored commits, and the false `N`-means-unsigned reading of `%G?` (that
was a missing `allowedSignersFile`, now set). What this does *not* soften is the
blast-radius point in PR-22 — it sharpens it: the runtime box now holds a signing
key **and** forge write credentials, so a compromise of this box can push *signed*
commits. The "drop to read-only tokens if a second contributor appears" trigger
stands, and is now more important, not less.

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
Saathi calls `z-ai/glm-5` through OpenRouter instead of `boto3` → Bedrock
directly when an active account key exists. Design in `AI_ROUTING.md`. Runtime
routing, workspace-scoped key minting, and a real spend-through turn were all
proven live on 2026-07-27.

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

**The transit, stated and accepted.** Inference stays in India. The prompt
transits OpenRouter's infrastructure to reach Mumbai. Operator decision,
2026-07-27: accepted, and **not** a blocker.

The privacy policy already draws exactly this line and needs no amendment —
"your message text may be processed outside India during the reply. Your stored
data … stays in India." Written before OpenRouter was considered, and accurate
for it. Recorded here so a future reader does not re-litigate a settled point, or
assume the policy overclaims when it does not.

**ZDR narrows the residual.** Amended 2026-07-27: every request also sends the
`provider.zdr` parameter. OpenRouter routes only to endpoints with zero-retention
policies, and **blocks** rather than silently choosing a retaining one. Combined
with `allow_fallbacks: false` the guarantee becomes: *our Mumbai Bedrock or the
request fails, and the prompt is never retained in transit.* That does not undo
the transit itself — the wording above stands — but it is the difference between
"passes through a US processor" and "passes through a US processor that keeps a
copy".

**Reverse it** by pointing the client back at `boto3`. The model, region and
account are unchanged, so reversal costs nothing but the metering.

### D-P · Deploying is transport-agnostic; the on-box half is one file · 2026-07-27
`ops/deploy.sh` gained `--local` so the runtime box can deploy itself (PR-28).
The reversible part is the flag. The part worth recording is the shape.

**Everything that happens on the target is `ops/deploy_onbox.sh`**, run from the
tree being installed, by both transports. The alternative — a local branch that
re-implements sync, migrate, test, restart — was rejected outright: PR-25's
migration ledger was verified against real Postgres across seven scenarios, and
a second copy of it would drift. The copy that drifts is always the one nobody
tested. A pleasant side effect is that the SSM heredoc shrank from ~120 delicate
`\$`-escaped lines to five with no dollar signs and no backticks at all, which
is the class of bug that once made the heredoc run `su - ubuntu` on the *dev*
box at generation time.

**Mode is an explicit flag, checked against the machine.** Autodetection alone
would deploy from a guess; a flag alone would let `--local` run on the dev box.
So: `--local` must positively match the instance ID from IMDS, and an unreadable
ID refuses — only the affirmative claim needs proof. The default transport
refuses *on* the target, where it would otherwise fail with
`AccessDenied: ssm:SendCommand` and read as a broken setup.

**Rehearsal is bound to the target, not to a flag.** `--repo` anywhere other
than `/home/ubuntu/saathi` skips `saathi-env-sync` and the restart, because both
are global and would reach production from a scratch directory. Inverted — a
`--no-restart` flag — the same mechanism would let someone ask for a production
deploy that skips the restart, and a deploy control that can be talked out of
its own safety step is not a control.

**Reverse it** by deleting the flag and the two instance-ID branches;
`deploy_onbox.sh` is what the artifact path runs either way, so nothing about
the remote deploy depends on local mode existing.

### D-Q · WhatsApp Cloud API Calling is a future channel, not v1 · 2026-07-27
Meta's WhatsApp Business Calling API can initiate and receive VoIP calls on the
same Cloud API business number, with Graph/webhook signaling by default and SIP
as an explicit integration path. Captured vendor transcript:
`docs/vendor/meta/cloud-api-calling.md`. It is strategically relevant to Saathi because
it keeps calling and chat in the same verified WhatsApp thread instead of adding
a separate PSTN/call-center identity.

It does **not** change v1. Saathi v1 remains WhatsApp chat plus inbound voice
notes, with outbound TTS as PR-8. Live voice calls introduce a different safety
surface: call permissions, calling hours, unanswered/rejected-call restrictions,
possible voicemail/record retention, real-time escalation expectations, and a
higher abuse cost if an onboarded handle can trigger repeated calls.

Implementation prerequisites to re-check before any lane starts:

- the number must be on WhatsApp Cloud API, not the WhatsApp Business app;
- the app must subscribe to the `calls` webhook field unless SIP is chosen;
- the same app must be subscribed to the WABA and have
  `whatsapp_business_messaging` for the business number;
- production business-initiated calling needs the required account capability
  and a daily messaging limit of at least 2,000 unique recipients;
- calling must be enabled in phone-number call settings, including call icon,
  business hours, callback and restriction controls;
- business-initiated calling availability depends on the business phone
  number's country; the current vendor note excludes US, Canada, Egypt,
  Vietnam and Nigeria business numbers.

Public test numbers can exercise calling features, but sandbox accounts are for
Tech Partners. Treat that as a testing constraint, not a product dependency.

**Reverse/advance condition:** advance this only with a dedicated v1.1+ lane that
adds consent language, rate limits, audit records, retention rules, caregiver
expectations, and a safety review for real-time calls. Until then, CallerDesk or
Cloud API Calling credentials may exist, but they stay inert.

### D-R · V1 language scope expands to eleven Indian locales · 2026-07-27
Operator decision: Saathi v1 focuses on Hindi (`hi-IN`), Bengali (`bn-IN`), Tamil (`ta-IN`), Telugu (`te-IN`), Gujarati (`gu-IN`), Kannada (`kn-IN`), Malayalam (`ml-IN`), Marathi (`mr-IN`), Punjabi (`pa-IN`), Odia (`od-IN`), and English (`en-IN`).

This overturns the earlier D2 posture of Hindi + English only. The reason is
not that the product suddenly became translation-first; it is that the channel
and user promise are language-first, and Sarvam appears likely to be the
load-bearing vendor for speech, normalization, evaluation, and possibly OCR.
The vendor source shelf starts at `docs/vendor/sarvam/github-repos.md`.

Consequences:

- every STT/entity/time/reminder eval must report per-locale scores, not just an
  aggregate;
- onboarding, consent, safety classifier phrases, reminder templates, and TTS
  voice choices need locale ownership before external users in that locale;
- Hindi fractional-time scar tissue remains necessary but is no longer
  sufficient; each language needs its own medicine/time/person failure set;
- Sarvam examples and tools are source material, not architecture. Runtime
  safety, budgets, redaction, and tool dispatch remain Saathi-owned controls.

**Reverse it** only by cutting a named locale out of v1 with the reason recorded;
otherwise future work should assume all eleven locales are in scope.

### D-S · Sarvam is STT-only until its spend can be attributed · 2026-07-27
Operator decision. D-R records the expectation that Sarvam becomes Saathi's
largest vendor; this bounds where it may be used until one specific problem is
solved.

**The problem: we cannot tell whose spend is whose.** A single Sarvam API key
serves every user. There is no per-account sub-key, so there is no vendor-side
way to attribute a rupee to a household, and no way to cap one household's
usage without capping everyone's. That is exactly the gap AI-1 closes for
OpenRouter — a minted sub-key per account gives attribution *and* a hard cap, so
a runaway loop burns one tester's five dollars instead of the platform balance.
Sarvam offers no equivalent today.

So Sarvam stays on **speech-to-text only**. STT is the one path where cost is
bounded by something we already measure and limit — the length of an audio file
(`saathi_max_audio_bytes`) — rather than by a model's appetite for tokens. A
per-turn cost that cannot exceed a known ceiling is attributable enough to run
without sub-keys; a conversational one is not.

Not adopted for: chat/LLM turns, translation, OCR, evaluation, or embeddings,
however good the benchmarks are. This is not a quality judgement.

**Reverse it** when either (a) Sarvam ships per-account keys or spend reporting
we can join to an account id, or (b) we build our own metering that prices
`llm_calls` rows per vendor and enforces a cap *before* the call rather than
discovering it on the invoice. (b) is the more likely path and is worth doing
anyway — `llm_calls` already records per-user model, tokens and latency; what it
lacks is price.

**(b) now has a design: D-V and `docs/USAGE_LEDGER.md`.** Written independently
the same day and arriving at the same conclusion from the other direction — no
gateway can meter what it does not route, so the ledger has to be ours. Treat
that document as the implementation path for reversing this decision.

### D-T · Five dollars free per user, once, then a paywall · 2026-07-27
Operator decision: "first $5 free per user then we will paywall." Supersedes the
`free`-tier posture recorded earlier the same day, which minted no key at all.

**The cap is not the decision — the reset is.** A $5 cap that resets monthly is
not "$5 free", it is $5 every month in perpetuity, and admission is deliberately
open. So the free grant is minted with **no `limit_reset`**, which makes it a
lifetime total rather than an allowance: `TIER_RESET["free"] is None`. `beta`
resets monthly, because those are testers an operator chose on purpose and wants
to keep working.

**Minting waits for onboarding to complete**, not first contact. The grant is
real money and the door is open, so a number that probes us once and never
answers gets an account row and nothing billable. Onboarding still makes no
model call and no third-party call — the mint is *queued* onto `scheduled_turns`
from the completion step, never performed inline.

An unknown tier gets no reset at all, for the same reason it gets the lowest
cap: a typo must produce spend that stops, not spend that renews.

**What this decision does not yet include: the paywall itself.** When the $5 is
gone the key simply stops authorising, and today that surfaces as a failed turn
rather than as a conversation about paying. An elder being told nothing, or
shown an error, at the moment their assistant stops working is a worse outcome
than the spend. See PR-40.

**Reverse it** by changing the grant to an allowance only with a deliberate
decision about abuse: at $5 renewing monthly, the cost of a throwaway number is
capped only by how many someone cares to acquire.

### D-U · The paywall lives in WhatsApp, and the model can never invoice · 2026-07-27
Operator decision: "paywall we need to build, whole point of app is being
controlled via WhatsApp — that is okay, if they want to use they need to pay."
This overrides the recommendation to collect via a link-out.

The reasoning is sound and worth recording rather than merely accepting: a
WhatsApp-native product that sends people to a browser to keep using it has
broken its own premise for the users least able to follow the detour.

**What this costs, stated plainly.** Saathi's promise has been that it never
transacts, and the scam it exists to blunt is not a stolen transfer — it is a
trusted voice asking an elder to pay. After this, Saathi can ask for money. That
is a real reduction in the guarantee and it should not be described as anything
else.

**What is kept.** The reduction is bounded to a single deterministic path:

- No payment tool exists. `send_invoice`, `request_payment`, `order_details`,
  `charge` and `refund` are in `FORBIDDEN_TOOL_NAMES`, so the suite fails if one
  is ever added to `TOOLS`. The model cannot invoice, cannot be argued into it,
  and cannot be prompt-injected into it, because the capability is absent rather
  than guarded — the same argument as the safety regex at priority 0.
- One caller, one price. `capabilities._paywall_handle` is the only caller, and
  the amount is `accounts.CONTINUE_PRICE_MINOR`. No amount is ever derived from
  anything that read user text.
- The paywall sits at priority 88 — above the agent, below everything
  deterministic. An account out of allowance keeps safety, onboarding, data
  erasure, reminder acknowledgement and every command including STOP. Those are
  rights, not features to be sold back to someone.
- **Reminders keep firing.** They run from the worker queue and never enter the
  chain. An unpaid bill is not a reason to stop telling someone to take their
  heart medication. Changing that must be a written decision, not a side effect
  of where a capability sits.

**Razorpay collects, we do not.** They will not take a payment without a phone
number or email, so payer identity stays with them; we keep only the join
(`accounts.psp_customer_id`) so a captured payment credits the right household.
No card, no UPI handle, no contact detail we did not already hold.

Off by default (`SAATHI_PAYMENTS_ENABLED=false`). An unconfigured install tells
the user their trial ended and sends nothing — a half-working paywall either
takes money without delivering or promises without charging.

**Reverse it** by disabling the flag; the copy degrades to an explanation with
no invoice, which is a safe resting state.


### D-V · Paid-vendor usage is Saathi-owned, not gateway-owned · 2026-07-27
Build `docs/USAGE_LEDGER.md` into the product before relying on any one vendor's
meter for user spend. OpenRouter remains the Bedrock/GLM-5 router and hard cap
for model calls, but it cannot account for Sarvam STT/TTS/OCR or WhatsApp
paid templates. Langfuse is a good mirror/dashboard once local rows exist.
LiteLLM is deferred until Saathi actually needs to operate its own LLM gateway.

The invariant: every paid vendor call gets one Saathi row with user/message
attribution, vendor/service/operation, units, cost, request id, status and
latency. Vendor dashboards reconcile invoices; they do not define product
causality.

This is the concrete implementation path for PR-15's widened requirement: rate
limits must cover audio, text, templates and future paid search, not just model
turns.

### D-W · Three scripts: हिंदी, Hinglish, English · 2026-07-27
Operator: "people who chose hindi should get text back in devanagari", then
"keep hinglish (romanized hindi), english and hindi until we not add new lang".

**The bug being fixed.** The onboarding button has always read **"हिंदी"**, in
Devanagari, and every message after it arrived romanised. The prompt rule said
"reply in the user's language and script", which made the model mirror whatever
it was sent — and since the deterministic copy was romanised, and an elder with
an English keyboard types "dawai" rather than "दवाई", it mirrored Latin forever.

**Reading and typing are different skills**, and for this audience they diverge
sharply. Someone who reads Devanagari comfortably may only have a Latin
keyboard. So script is a **stored choice**, stated to the model on every turn
(`prompt.script_line`), never inferred from the last message.

`hi-en` stops being a legacy value and becomes a first-class option, because it
would otherwise have fallen through `COPY` to `hi` and switched existing
Hinglish users to Devanagari without asking. Three choices is also WhatsApp's
hard limit of three quick replies, so a fourth language cannot be added to that
step without redesigning it.

**What it costs.** Devanagari tokenises at roughly **1.77x** Latin for the same
sentence — measured, not estimated: the welcome message is 77 tokens romanised
and 136 in Devanagari. There is no prompt caching, and replies re-enter the
prompt as history, so this compounds. It is a real cost increase on the $5 free
grant (D-T) and worth revisiting if the grant proves tight.

**Numerals stay international** (112, 108, 1930, "15 मिनट"), not Devanagari
numerals. Helpline numbers are dialled: १०८ on an emergency line is a hazard,
not a nicety.

**Not converted: the Meta-approved templates.** `reminder_fire_v2`,
`reminder_nudge_v2` and `daily_checkin` carry romanised Hindi in body text Meta
has approved, and a template cannot be edited — it needs a new name, and Meta
holds a deleted name for four weeks (`LANDMINES.md`). **So reminders and nudges
still arrive romanised for everyone.** That is the largest remaining gap and it
is the core of the product. See PR-44.

### D-Y · Commercial internet actions stop at deeplink handoff · 2026-07-28
Saathi will support shopping, cart assembly, flights, movie/event tickets and
other internet action capabilities only up to the point where the user receives
a visible shortlist, list, cart draft, provider search URL, deeplink, directions
URL or booking URL. The transaction itself remains outside Saathi.

This preserves the original product promise in `PRD.md` §1/§4: the hard part for
the elder is articulating the request and navigating the interface, not handing
an agent power to spend. The agent can make the next step obvious; the user and
the merchant still complete it.

Research on 2026-07-28 shows the industry has largely converged on two patterns:
structured offer/search/discovery APIs, and browser/computer-use agents. The
first is acceptable here when used only for search and links: IATA NDC, Duffel
and Amadeus separate flight offers from order creation, Ticketmaster separates
event discovery from partner transactions, Google Maps exposes URL builders, and
schema.org/Google structured data describes products and potential actions that
can be linked to. The second is explicitly not v1 for Saathi: a browser agent
that can fill forms, preserve cookies and request sensitive takeover is too broad
for an elder WhatsApp thread whose safety guarantee is capability absence.

`COMMERCIAL_ACTIONS.md` is the source of truth. Future tools may be named
`search_flights`, `search_events`, `build_cart`, `make_maps_link` or similar.
They must not be named or behave like `checkout`, `place_order`, `buy_ticket`,
`book_flight`, `charge`, `login`, `read_otp` or equivalents. Any reversal needs a
new dated decision that says exactly which boundary is being reduced and why.

This does not change D-C: flight search is still out of v1 because it is not a
daily-retention capability and has commercial/search-volume risk. It does define
how flights come back in v1.1: offer search + shortlist + official handoff link,
not booking.

**Amended 2026-07-28: India-first and no new paid vendors by default.** The
implementation path starts from the GCP/Google search stack already wired for
Saathi, official URL builders such as Google Maps URLs, and popular Indian app
or web handoffs. Duffel, Amadeus, Ticketmaster and ACP remain useful research
patterns, but they are not defaults for this product now. New vendor APIs require
a specific India use case, acceptable terms, usage-ledger accounting and a fresh
implementation lane.

### D-Z · Saathi is a WhatsApp operating system for daily life · 2026-07-28
Operator accepted the framing: Saathi is a WhatsApp operating system for daily
life for non-tech-savvy 40+ and elder users in India. This supersedes the weaker
mental model of a generic chatbot with some reminders, and it prevents the
commercial-action lanes from pulling the product toward shopping or booking as
the center of gravity.

The durable verbs are: read this, explain this, remind me, draft this, remember
this, is this safe, open the right place, and tell me the next step. This matches
how the target user already lives: WhatsApp is the inbox, document tray, family
thread, notice board and support channel.

Roadmap order follows daily recurrence and safety value: forwarded-message
reading, task management, bill/due-date extraction, message drafting and scam
shield outrank rare-event sophistication such as flight search or full cart
automation. `DAILY_LIFE_OS.md` owns the lane list and acceptance shape.

This decision does not weaken the no-transaction boundary. It strengthens it:
the product value is navigation and comprehension, not autonomous spend.

### D-AB - Tracing uses Logfire with a hard no-PII rule - 2026-07-29
Tracing uses the logfire Python SDK configured with inspect_arguments=False
(no automatic function-argument capture) and exported to a local OTel Collector
at 127.0.0.1:4317. The collector exports to local Jaeger OTLP on
127.0.0.1:4318, so the two services do not bind the same port. Jaeger runs on
the same box with badger storage (7-day TTL, 4 GiB cap). saathi/observability.py
enforces a fixed allow-list of span attributes: kind, latency, tokens,
tool_name, hop_count, model_id, error_class, trigger. Message text, transcripts,
names, medicines and query parameters are scrubbed before they leave the process.

Operator update 2026-07-29: when `LOGFIRE_TOKEN` is present, the same scrubbed
spans may also be sent to the operator's Pydantic Logfire project `indofolk-ai`.
Cloud export is token-gated (`send_to_logfire="if-token-present"`), not
unconditional. The same failure contract as metrics.py applies: publishing must
not raise, and a collector or Logfire outage never blocks a turn. Local traces
remain queryable via SSH tunnel to localhost:16686.


### D-AA · Returning WhatsApp handles do not restart signup · 2026-07-28
A WhatsApp number is still only a revocable handle, not the account, but an
active handle that has already completed onboarding must not be treated as a new
signup when the user taps an old entrypoint or onboarding quick reply in the same
chat. The handler may let an old language button update `lang_pref`; every other
old onboarding button replies that setup is already complete and leaves
`users.onboarding = 'done'`.

The number-recycling protection remains a lifecycle rule, not an excuse to lose
the user immediately: stale handles should be warned and reverified through a
written window, with account move/confirm paths, before revocation or deletion
after the 90-day dead-air period.

**Implemented lifecycle, 2026-07-29 (ID-2).** `60 days` without inbound is the
warning/re-verification threshold and `90 days` of continuous dead air is the
revocation threshold. The day-60 worker uses only the generic, content-free
`daily_checkin` template, because WhatsApp permits no free-form proactive text
outside the session and the notification must not leak prior ownership. A
returning stale handle is `reverify` and is stopped before any stored-data or
model path. It can explicitly continue, or receive a short-lived move code for
a new, blank handle. At day 90 the old handle is revoked; the user identity is
not deleted merely because its delivery address went quiet.

### D-AC · Runtime forge write access is retained as mirror authority · 2026-07-29

Operator decision: retain GitHub/GitLab write credentials and the dedicated SSH
keys on the runtime box. The Saathi application does not execute from either
forge: a running process changes only through the documented deploy path. The
forges are source mirrors/backups for the application. GitLab's `site` branch is
the explicit exception: Cloudflare Pages deploys it on push, so a compromise can
alter the public site immediately.

This does not make the credential surface harmless. A runtime compromise can
poison a future application deploy or the public site, so the PR checkpoint,
two-remote synchronization, deploy verification, and explicit source-branch
workflow remain required. Revisit the decision if the runtime box becomes more
exposed, a second contributor appears, or the site branch gains sensitive flows.

### D-AD · Attribution sends signals to Meta, never builds a cross-Meta identity graph · 2026-07-30

Operator decision, made explicit because it governs a boundary. Saathi reports
Click-to-WhatsApp conversions to Meta's Conversions API so ad spend can be
attributed — but only as a **one-way signal**, and only the marketing funnel.

What is allowed: on onboarding completion, one `LeadSubmitted` carrying the
`ctwa_clid` Meta itself minted on the ad click, plus an event name and a time.
Meta's own `ctwa_clid` is the match key, so the event contains **nothing about the
elder** — no phone, no message content, no thread. Chosen over Meta's Automatic
Events API precisely because that alternative would have Meta run NLP over elders'
WhatsApp conversations; we send our own signal instead.

What is refused: Saathi does **not** build or read a graph linking a person's
Facebook identity, phone number and WhatsApp together. Meta does not expose the FB
identity behind a number anyway, but the point stands as a boundary — the product's
value is being the *trusted, Indianised, safer layer over* the Meta ecosystem, not
a thinner copy of Meta's identity linking. The moat is the shield, not the graph.
The feature is off unless `SAATHI_CAPI_DATASET_ID` is set, and it fails closed:
capture and report both no-op without it, and a Graph outage never touches a turn.

### D-AE · Sarvam adopted for TTS (Bulbul), reversing D-S's STT-only scope · 2026-07-30

Operator decision (chose "Sarvam Bulbul, reverse D-S" over Google Cloud TTS).
D-S confined Sarvam to speech-to-text because its single shared key gave no way
to **attribute or cap** spend per household — and named the reversal condition:
*"(b) we build our own metering that prices vendor calls per account and enforces
a cap before the call."* That metering now exists — the usage ledger (D-V,
LEDGER-1/2, `USAGE_LEDGER.md`), with `reserve`/`settle`/`record_event` already
capping STT. So the condition D-S set is met, and TTS may ride Sarvam too.

Why Sarvam over Google TTS: it keeps the **"inference stays in India"** boundary
clean (Bulbul is an in-India endpoint, verified our key has access 2026-07-30);
it gives the best Indic/code-mix elder voice; and it reuses a vendor already
wired for STT rather than adding one. Google Cloud TTS would have sidestepped the
D-S question but is a new vendor with weaker in-India residency guarantees.

What this authorises: outbound TTS on Sarvam Bulbul (`bulbul:v2`), **metered
through the ledger exactly like STT** — every synthesis records a content-free
`vendor=sarvam, service=tts` event with character units, and when the global
usage-enforcement flag is on, a pre-call reservation caps it per account. TTS
input is Saathi's *own* reply text (which may contain a user's name), never the
user's inbound content; the ledger event stays content-free (counts, not text).

What this does **not** change: the "it never transacts" boundary; STT stays the
STT lane. TTS ships behind `SAATHI_TTS_ENABLED` (default off) and, when on,
defaults to voice-in→voice-out (`voice_reply_pref='auto'`). The one open item is
price: Sarvam's per-character TTS rate is not in a captured doc, so the ledger's
cost is a labelled estimate until reconciled against an invoice (see
`USAGE_LEDGER.md`), the same path STT pricing took. The durable record — the
character count — is exact regardless.

**Reverse it** only if Sarvam TTS residency or spend-attribution assumptions break.

### D-AF · Gujarati and Malayalam added as full languages, with a documented safety gap · 2026-07-30

Operator decision. Saathi now offers five languages: Hindi (Devanagari),
Hinglish (romanised), English, **Gujarati**, and **Malayalam**. What this
touched: the onboarding picker, reply-script rules, STT/TTS language codes
(verified live — Sarvam Saaras/Bulbul serve `gu-IN` and `ml-IN`), and the ack/
command/paywall copy.

**The picker is now a list, not buttons.** Five languages exceeds WhatsApp's
three-quick-reply limit, so the language step (the one message shown in multiple
scripts) is a WhatsApp *list message* (up to 10 rows). Onboarding still asks
language first, before anything else — that was always true; it just needed a
wider control.

**The safety boundary gap is accepted and documented, not hidden.** The
priority-0 deterministic safety classifier (medical emergencies + scams, before
any model call) covers Hindi/English/Hinglish only. Gujarati/Malayalam native-
*script* emergencies and scams are **not** caught deterministically yet — they
fall through to the model, which still responds but without the priority-0
guarantee. Forwarded Hindi/English scams (the common case) are still caught for
these users. Operator chose to **ship the languages now with the gap documented**
rather than block them, because the value to a Gujarati/Malayalam-speaking elder
is real today and the common scam vector is still covered. Closing the gap needs
native-verified patterns — lane **SAFE-LANG-1**. Per "fail loudly, never fail
open," this is a *known* hole, recorded in `safety/classifier.py`,
`PROD_READINESS.md` (LANG-2) and here — not a silent one.

**Also provisional:** the Gujarati/Malayalam onboarding/reply copy is a first
draft and needs native elder-audience review before it is final (flagged in the
code and PROD_READINESS). It ships because wrong-but-reviewed beats absent, and
the strings are legible and correct-script; polish follows.

**Reverse/narrow** only by removing a language from the picker rows — the code
falls back to Hindi for any `lang_pref` it does not recognise, so a removed
language degrades safely rather than breaking.

### D-AE addendum (2026-07-30) — moved to bulbul:v3, per-language voices

TTS shipped on `bulbul:v2` but sounded muddy/robotic in production (VOICE-1). Not
a vendor problem: v2 at 22050 Hz forced a bad resample into 48 kHz Opus, and no
preprocessing hurt code-mixed pronunciation. Moved to **`bulbul:v3`** (native
48 kHz, higher quality, `enable_preprocessing` on), a cleaner 48 kbps Opus encode,
and a **per-language speaker map** (voices are multilingual but the natural choice
differs by language: hi/hi-en `ritu`, gu `priya`, ml `kavitha`, en `neha`). This
is a quality tuning *within* D-AE — same vendor, same in-India residency — not a
new decision. v3 has its own speaker roster, so the v2 `anushka` default retired.

### D-AF addendum (2026-07-30) — the gu/ml safety gap is now closed (first pass)

D-AF shipped Gujarati/Malayalam with the priority-0 safety classifier still
Hindi/English-only, as a documented gap (lane SAFE-LANG-1). That lane is now done:
native-script gu/ml patterns cover emergency, hypoglycemia, self-harm, medical-
advice, and scam/suspicious pressure phrases; verified live to fire across all
families with no benign false-positives in the test set. The patterns are a first
pass and still want a native-speaker review pass (flagged in `safety/classifier.py`),
but gu/ml users now have a real priority-0 net rather than none.
