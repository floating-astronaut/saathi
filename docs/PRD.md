# PRD — WhatsApp AI Assistant for Elders (*Saathi*)

> ## §0 — Status of this document
>
> **This PRD is research, not scripture.** It is the original product argument,
> preserved as written on 2026-07-27 so the reasoning stays legible. Several of
> its *technical* claims have since been measured and found wrong. The product
> argument — voice-first, Indic-first, memory + reminders, never transact — has
> held up completely.
>
> Corrections established by measurement, each recorded in `DECISIONS.md`:
>
> | PRD says | Measured reality |
> |---|---|
> | §7 Claude Sonnet 5; §14 prompt caching **mandatory** | `zai.glm-5` on Bedrock **ap-south-1**, a *regional* endpoint so inference stays in India. It has **no prompt caching** — so the cost lever is a tight prefix, not a cache. Sonnet is `global.`-only here, which would send prompts out of India. |
> | §14 LLM ≈ ₹135/user/mo | Measured ≈ **₹60** at ~1,750 input tokens/turn |
> | §9 Saaras modes `transcribe/translate/verbatim/transliterate/codemix`, default `codemix` | Real enum is `transcribe / translate / **indic-en** / verbatim / translit / codemix`. `codemix` returns **Devanagari**, which makes the entity-correction pass structurally dead. Default is **`indic-en`**. |
> | §10 entity biasing via ASR keyword boosting is "the single biggest win" | API-side bias changed 1 of 3 transcripts, and that change was noise. The **local correction pass is the mechanism**, not the fallback. |
> | §8 Duffel / flight search | **Cut from v1** (decision D-C) |
> | §11 five templates in week 1 | Four. `search_ready` went with flights. |
> | §16 week 1 = submit templates | Business verification precedes it. On the *right* business it was already done. |
>
> Read `DECISIONS.md` for the reasoning and `LANDMINES.md` for what these cost
> to discover.

---


**Version** 0.1 · **Date** 2026-07-27 · **Status** Draft for review
**Author** Tejas Karan Agrawal

---

## 1. Summary

A WhatsApp-native AI assistant, voice-first and Indic-language-first, that does four
things for older adults: **remembers**, **reminds**, **searches**, and **assembles**.

It never takes a transactional action. Every task ends in a message the user can act on
themselves — a reminder, an answer, a shortlist, or a link they tap. No payment
credentials, no OTPs, no account access, no agent-initiated spend.

The bet: for this user, the hard part was never the transaction. It was *articulating the
request, remembering the details, and navigating an interface built for 25-year-olds.*
An agent that removes those three frictions is valuable even with zero purchasing power.


**Amended 2026-07-28 — product frame.** Saathi is best understood as a
**WhatsApp operating system for daily life** for non-tech-savvy 40+ and elder
users in India. The core verbs are read, explain, remind, draft, remember, check
safety and open the right place. Shopping/cart and travel links are subordinate
to that frame, not the center of the product. `DAILY_LIFE_OS.md` owns the current
roadmap.

---

## 2. Problem & evidence

Indian seniors are online but poorly served:

- India has ~615M WhatsApp users; the 56+ segment is ~13% of the base, and 55–64 is the
  fastest-growing segment globally. WhatsApp is already installed, already understood,
  already daily.
- ~40% of Indian seniors own smartphones, and 77% are described as "text-savvy."
- But **66% find digital tools confusing** and **51% fear making errors** — barriers are
  interface complexity, small fonts, and navigation, not device access.

So the distribution problem is solved (WhatsApp) and the interface problem is the product.

Research on conversational agents for older adults converges on a few findings that
directly shape the spec:

- **Errorless learning beats trial-and-error.** The exploratory "just try things and see"
  model of general AI assistants conflicts with how older adults prefer to learn. When a
  prompt fails, users are often forced to restart with no feedback on what went wrong.
- **Repair matters more than accuracy.** Recurring design levers are slower pacing,
  longer permitted turns, sincere ownership of mistakes, and both system- and
  user-initiated repair (confirmation, rephrasing, explicit clarification).
- **But avoid generic repetition.** Structured follow-ups that re-ask what was already
  answered are a documented frustration. Confirmation must be targeted, not blanket.
- **Control is the core emotional need.** Older adults' desire to feel in control is a
  recurring finding — which is an argument *for* the no-transaction design, not against it.
- **Reminders work, modestly and durably.** Meta-analysis of SMS medication reminders in
  T2DM (9 RCTs, n=1,121) found a pooled effect size of **0.36** vs. usual care, with
  *larger* effects in interventions running longer than six months. Retention compounds
  the benefit — this is a subscription-shaped product, not a one-shot tool.

---

## 3. Users

| | |
|---|---|
| **Primary user** | 60+, metro/tier-1 India, WhatsApp-fluent, low app-fluency, prefers voice notes, speaks code-mixed Hindi/English |
| **Secondary user** | Adult child, 30–45 — likely the one who installs, onboards, and pays |
| **Buyer** | Assume the adult child. See Open Decision D1. |

**Explicit non-goal for v1:** the family thread. No dual-thread coordination, no guardian
approvals, no digests. One user, one thread. (Deferred, not discarded — §17.)

---

## 4. Scope

**In scope (v1)**

1. Conversational assistant in WhatsApp, text + voice notes
2. Persistent memory of user facts, preferences, people, routines
3. Reminders — one-off and recurring, with acknowledgement and snooze
4. Flight search → shortlist + booking link
5. Cart assembly → itemised list + best-available deep link
6. General Q&A / explain-this-message

**Out of scope (v1)**

- Placing orders, making payments, holding credentials, handling OTPs
- Family/caregiver thread, escalation to relatives, health monitoring
- Voice *calls* (only voice notes)
- Medical, legal, or financial advice
- Any browser or app automation on a third party's account

---

## 5. Core capabilities

### C1 — Memory
Stores facts explicitly, via a tool call, never inferred silently into an opaque blob.
User can ask "what do you know about me" and "forget that". Facts are used for (a)
personalisation and (b) **ASR entity biasing** (§10), which is the higher-value use.

### C2 — Reminders
Natural-language creation ("remind me to take the BP tablet every morning at 8"), fired as
a WhatsApp utility template, acknowledged with a reply button, snoozeable. Recurrence via
RRULE. Timezone-aware (assume Asia/Kolkata, but store per user).

**Design rule:** never signal that a reminder is repetitive or that the user forgot. No
"you missed yesterday's."

### C3 — Search (flights first)
Slot-filling conversation → live search → 2–3 options as an interactive message → CTA URL
button to a booking page. Results cached with a TTL; expired results are re-fetched on tap,
never shown stale.

### C4 — Cart assembly
Conversation + memory ("the usual, plus atta") → itemised list → best available link.
Graceful degradation, in order:
1. Real pre-filled share-cart link, where the platform supports it
2. Per-item deep links into the app's search
3. Always: a clean numbered list, readable and forwardable

**Note:** Blinkit/Zepto share-cart URL schemes are undocumented and change without notice.
Tier 3 is the contract; tiers 1–2 are best-effort. Verify current behaviour before building
UX around them, and re-verify monthly. See Risk R3.

---

## 6. Design principles (non-negotiable)

1. **Voice in, voice + text out.** Always send text alongside audio — re-readable,
   searchable, works when audio can't play.
2. **One question per turn.** Never a multi-part question.
3. **Confirm consequential slots, nothing else.** Times, dates, dosages, amounts, proper
   nouns get read back. Everything else does not — blanket confirmation is a documented
   frustration.
4. **Own errors plainly.** "I got that wrong, sorry — let me try again." Never blame the
   user, never say "I didn't understand" without offering a concrete next step.
5. **Never signal repetition.** The fourth time the same question is asked, answer it as
   warmly as the first.
6. **Errorless by default.** Offer the likely options rather than requiring the user to
   guess the magic phrasing. Prefer buttons over free text wherever a choice is bounded.
7. **The user is always in control.** Nothing happens without them tapping or saying yes.

---

## 7. Architecture

```
WhatsApp ──webhook──▶ FastAPI (web)
                        │
                        ├─ media fetch ──▶ ffmpeg ──▶ Sarvam STT
                        ├─ entity-bias / correction pass
                        ├─ Claude Sonnet 5 (tool loop)
                        ├─ TTS (swappable) ──▶ ffmpeg ──▶ OGG/Opus
                        └─ Postgres
                             ▲
              worker  ───────┘   (reminder scheduler, poll 30s,
                                  SELECT … FOR UPDATE SKIP LOCKED)
```

**Stack**

| Layer | Choice | Rationale |
|---|---|---|
| Channel | WhatsApp Cloud API via Indian BSP | Meta direct is cheaper; BSP is faster to launch |
| Runtime | Python 3.12 + FastAPI | LLM tooling maturity |
| Store | Postgres 17 | Also the job queue — **no Redis in v1** |
| Agent | Claude Sonnet 5, tool loop, prompt caching **mandatory** | See §14 |
| STT | **Sarvam Saaras v3** | Best-in-class Indic + code-mix |
| TTS | Swappable interface, default cheap-and-good (Google/Azure Indic neural) | Commodity — see §9 |
| Flights | **Duffel** | See §8 |
| Deploy | Single VM, 2 processes (web + worker), systemd | Sized for <5k users |

### Why no Redis, no Temporal, no vector DB in v1

- **Redis:** Postgres `SKIP LOCKED` handles the reminder queue to well past 10k users.
- **Temporal:** justified only for money sagas with human approval steps. Those are out of
  scope now.
- **Vector DB:** current memory research recommends starting with working-memory-in-context
  plus external retrieval, instrumenting it, and only graduating to tiered/learned memory
  when data shows it helps. Our fact set per user is small (tens to low hundreds of rows) —
  it fits in the prompt. Postgres full-text + recency ordering is sufficient. Revisit at
  scale.

---

## 8. Flight provider: Duffel (decided)

**Amadeus Self-Service is not an option.** Its developer portal closed on **17 July 2026**
and self-service keys have stopped working. Traditional GDS (Amadeus, Sabre, Travelport)
run $50k–200k+/year plus per-segment fees — not viable at this stage.

**Duffel:** ~$3 per confirmed order, 1% of order value for managed content, ~$0.005 per
search beyond a 1,500:1 search-to-book ratio. Since v1 does **not** book, we are pure
search — so watch the search-to-book ratio, which will be effectively infinite.

> **Action required:** confirm with Duffel that search-only usage is acceptable under their
> commercial terms, and what the excess-search charge works out to at our volume. This is a
> real commercial risk if unaddressed. See Risk R2.

---

## 9. Speech: what to invest in, and what not to

**STT is the product. TTS is a commodity.** Inbound speech is an open set — disfluent,
code-mixed, noisy, with proper nouns no general model has seen. Outbound speech is a
closed set of maybe 50 phrase templates.

**Sarvam Saaras v3** — modes: `transcribe`, `translate`, `verbatim`, `transliterate`,
`codemix`. `codemix` is the right default for Hinglish. Note Saarika v2.5 is being
deprecated; use Saaras v3 with `mode=transcribe`. APIs: REST (<30s audio), Batch (up to
2h), Streaming. Voice notes are almost always <30s → REST path. **₹30/hour.**

**TTS:** pick on voice quality alone, because caching makes latency irrelevant. Cache key
`hash(text + voice + lang)`; pre-generate the top ~50 phrases at deploy. Expect >80% hit
rate — reminder text is byte-identical every day. Sarvam TTS is ₹15–30/10K chars but this
is a swappable interface; A/B two or three providers by playing samples to three actual
elders and letting them choose.

**Optional, high-upside:** record the fixed phrase bank with a human voice artist. Fifty
phrases, one afternoon. Structure phrases so dynamic parts (times, names) are a *separate
sentence* — splicing human and synthetic mid-utterance sounds wrong.

**Audio format gotchas (both directions):**
- Inbound WhatsApp voice notes are **OGG/Opus**; media URLs expire in minutes — fetch
  immediately. Transcode to WAV/PCM for Sarvam.
- Outbound: send **OGG/Opus** or WhatsApp renders it as a file attachment instead of a
  voice-note bubble with a waveform. For an elder that is the difference between
  "I understand this" and "what is this."
- ffmpeg is in the hot path both ways. Budget for it.

---

## 10. The critical path: transcript → validated tool call

This is where the product lives or dies, and it is *not* solved by ASR accuracy alone.

```
audio ─▶ Saaras v3 (codemix)
      ─▶ entity bias / correction pass
      ─▶ LLM intent + slot extraction
      ─▶ targeted confirmation on consequential slots
      ─▶ tool call
```

**Entity biasing.** Pass the user's known entities from `facts` on every STT call —
medicine names, family names, city, doctor, usual brands. *Check whether Saaras v3 supports
keyword boosting / custom vocabulary; if it does, this is the single biggest accuracy win
available.*

**Correction pass (fallback if boosting is unsupported).** Send the raw transcript plus the
user's known entities to the LLM and ask it to repair likely misrecognitions before intent
extraction. "Emlodipin" → matched against their actual medicine list → "Amlodipine."

This has a compounding property worth stating explicitly: **the longer someone uses the
product, the better it hears them.** That is a retention mechanic, not just an accuracy fix.

**The rule on the wall:** *never act on a number or proper noun straight from STT without
reading it back.* ASR reliably mangles exactly what matters — times, dosages, dates,
amounts, medicine names. "Ten thirty" / "ten thirteen."

---

## 11. WhatsApp mechanics

**The 24-hour window.** A user message opens a 24-hour customer-service window. Inside it,
free-form and interactive messages are **unrestricted and free**. Outside it, only
pre-approved templates. The timer resets on every user message.

**Consequence for design:** a template's job is not to say everything — it is to **get a
reply**, which reopens the free window. Structure the day around 1–2 template-initiated
sessions rather than sprinkling messages.

**India rates (Meta, effective 1 Jan 2026), before BSP markup and 18% GST:**

| Category | Rate |
|---|---|
| Service (user-initiated + replies in window) | **Free** |
| Utility | ~₹0.115 / msg |
| Authentication | ~₹0.115 / msg |
| Marketing | ₹0.8631 / msg (+10% on 1 Jan 2026) |

**Everything we send proactively must be Utility category.** Marketing is 7.5× the cost and
inappropriate for reminders anyway.

**Interactive limits:** up to 3 quick-reply buttons (20 chars each) or 2 CTA buttons. Use
CTA URL buttons for booking/cart links so the raw URL never appears in the body.

**Templates to submit in week 1** (Meta review is the long pole — days, sometimes with
rejections):

| Template | Category | Purpose |
|---|---|---|
| `reminder_fire` | Utility | One variable slot; serves every reminder |
| `reminder_nudge` | Utility | No acknowledgement after N minutes |
| `search_ready` | Utility | Flight results ready |
| `daily_checkin` | Utility | Opens the free window once a day |
| `session_resume` | Utility | "Still there?" / continue an interrupted task |

Design templates and the interactive card UX **together**, not sequentially — some
interactive types are template-only outside the window.

---

## 12. Safety

**Deterministic, pre-LLM classifier** on every inbound message. Runs before the model
sees anything; not a prompt instruction.

| Trigger | Response |
|---|---|
| Medical emergency phrasing (chest pain, breathlessness, fall, stroke signs) | Emergency numbers + "call someone now", in their language. No LLM turn. |
| Self-harm / severe distress | Helpline numbers, warm handoff copy, flag for human review |
| Request for medical/dosage advice | Decline, redirect to their doctor. Reminders yes, advice never. |
| Scam-shaped forwarded message | Explicit warning, "do not share OTP/PIN with anyone" |

**Hard prohibitions in the system prompt, enforced by absence of tools:** no tool can move
money, no tool can read or store an OTP, no tool can access a third-party account. Prompt
injection via a product listing or a forwarded message should be *structurally* incapable
of causing harm, because the capability does not exist.

---

## 13. Privacy & DPDP

India's DPDP Rules were notified 13 Nov 2025 with phased enforcement. **Full operational
compliance — standalone notice in prescribed languages, and 72-hour breach reporting —
begins 13 May 2027.** Consent-manager provisions kick in Nov 2026. Penalties reach ₹250
crore for security failures.

We are building through that window, so:

- **Consent at onboarding**, in the user's language, stated plainly — free, specific,
  informed, unambiguous. Not buried.
- **Voice retention policy:** keep raw audio only for debugging, with a hard TTL (proposal:
  7 days), then delete. Keep the transcript long-term, not the waveform.
- **Right to erasure** implemented from day one, not retrofitted — "forget everything about
  me" must actually work.
- Health-adjacent data (medicine names, appointments) deserves stricter handling than the
  minimum. Treat as sensitive by policy even where not required by law.
- Data resident in India.

---

## 14. Unit economics (estimate)

Assumptions: 4 min inbound voice/day, ~10 LLM turns/day, 3 reminders/day, 1 daily check-in,
85% TTS cache hit, prompt caching on.

| Cost | Monthly / user |
|---|---|
| WhatsApp utility templates (~120 msgs, +BSP markup +GST) | ~₹20 |
| Sarvam STT (2 hrs @ ₹30/hr) | ~₹60 |
| TTS (85% cached) | ~₹30 |
| Claude Sonnet 5 (300 turns, prompt caching on) | ~₹135 |
| **Total variable** | **~₹245 (~$2.90)** |

**Two conclusions:**

1. **WhatsApp is not the cost driver — speech and inference are.** Utility messaging is
   ~8% of variable cost. Do not over-optimise message volume; do optimise STT minutes and
   prompt size.
2. **Prompt caching is mandatory, not an optimisation.** Without it the LLM line roughly
   triples to ~₹450–500 and the unit economics stop working. Cache the system prompt, tool
   definitions, and the user's fact block.

Implied pricing: ₹499/month works with healthy margin. ₹199/month is tight and requires
capping voice minutes. Free tier must be hard-capped on STT minutes specifically.

*All figures are estimates from published rate cards; re-derive from actuals after week 4.*

---

## 15. Success metrics

**Primary:** D30 retention of *daily active* users. This product either becomes a habit or
it is nothing.

| Metric | Target (by week 8) |
|---|---|
| D30 retention (DAU) | >40% |
| Reminder acknowledgement rate | >70% |
| **Entity accuracy** on times/dates/medicine names | >95% |
| Turns to complete a reminder creation | <3 |
| Voice-note share of inbound | tracked, not targeted |
| Task abandonment (started, never completed) | <15% |

**Score entity accuracy, not WER.** A transcript can be 92% word-accurate and still have
the medicine name wrong — which is the only error that matters. WER will actively mislead
you here.

**Eval set:** 50–100 real voice notes per language, hand-transcribed, deliberately
including the messy ones — background TV, a grandchild shouting, a bad line. Build it in
week 2, before the first model-version decision.

---

## 16. Milestones

| Week | Deliverable | Gate |
|---|---|---|
| **1** | **Submit all templates to Meta.** Webhook, user record, message log, STT pipeline, plain conversation with memory. | Templates submitted; 5 internal users talking to it |
| **2** | Reminders end to end: scheduler, template firing, ack, snooze, recurrence. Eval set built. | A reminder fires correctly for 3 consecutive days |
| **3** | `search_flights` (Duffel) + `build_cart`. Interactive cards + CTA buttons. | Both produce a working link |
| **4** | Safety classifier, consent flow, retention job. 20 external users recruited via their children. | Live with strangers' parents |
| **5–8** | Instrument, measure, cut. | Hit the §15 targets or re-scope |

**Week 1 is template submission.** Everything else can be parallelised; Meta's review
queue cannot.

---

## 17. Open decisions

| # | Decision | Recommendation | Why it matters |
|---|---|---|---|
| **D1** | Who is the buyer — elder or adult child? | **Adult child.** Elder is the user, child pays and onboards. | Drives onboarding flow, pricing page, and whether the family thread returns in v2 |
| **D2** | Launch languages | **11 Indian locales for v1:** Hindi (`hi-IN`), Bengali (`bn-IN`), Tamil (`ta-IN`), Telugu (`te-IN`), Gujarati (`gu-IN`), Kannada (`kn-IN`), Malayalam (`ml-IN`), Marathi (`mr-IN`), Punjabi (`pa-IN`), Odia (`od-IN`), English (`en-IN`). | Operator decision, 2026-07-27. This makes Sarvam the likely load-bearing speech/language vendor and means eval, phrase bank, safety classifier, consent/onboarding copy, and TTS voice choice must report per-locale results rather than a Hindi/English aggregate. |
| **D3** | Reminders opt-in or default-on? | **Opt-in, prompted during onboarding.** | Drives template volume and therefore per-user cost; also an errorless-learning consideration — unexpected messages erode trust |
| **D4** | Voice replies default-on or toggle? | **Toggle, default ON for users who send voice notes**, off for users who type. | Latency + cost; mirrors the user's own modality |
| **D5** | Does the family thread come back in v2? | Defer to week 8 data. If users repeatedly forward our lists to their children manually, that is the signal. | It was the strongest earlier concept; v1 deliberately tests whether it is needed |
| **D6** | Does WhatsApp Cloud API Calling enter v1.1? | **Defer; not v1.** Keep v1 to chat, voice notes, and TTS replies. Revisit only after consent, call-rate limits, call-hours policy, retention, and caregiver expectations are designed. | Calls are more interruptive than messages and create a real-time support promise; the attached Meta note makes the path possible, not automatically safe. |

---

## 18. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | STT entity accuracy insufficient for medicine names | High | Entity biasing + correction pass + mandatory read-back. Measure from week 2, not week 8. |
| **R2** | Duffel commercial terms penalise search-only usage | Medium | Clarify before building. Fall back to a metasearch affiliate link if terms are hostile. |
| **R3** | Cart deep links break without notice | Medium | Tier-3 (plain list) is always the contract. Automated weekly link-health check. |
| **R4** | Meta rejects templates or delays approval | Medium | Submit week 1. Draft alternates. Have a plain-text fallback template ready. |
| **R5** | Elders don't adopt without a family member setting it up | High | Assume they won't. Design onboarding *for the child*, first-run experience for the elder. This is D1 restated as a product risk. |
| **R6** | Retention comes from companionship, not utility — and we built utility | Medium | Instrument conversational (non-task) turns from day one. If they dominate, that's the product telling you something. |
| **R7** | A user has a medical emergency and the agent mishandles it | Critical | Deterministic pre-LLM classifier, shipped week 4 before external users. Non-negotiable gate. |

---

## 19. Sources

- [WhatsApp Business API Pricing India (Jul 2026) rate card](https://whautomate.com/whatsapp-business-api-pricing-india)
- [WhatsApp Business API Pricing 2026 — per-message costs & billing](https://www.uptail.ai/blog/whatsapp-business-api-pricing-2026-what-it-costs-and-how-billing-works)
- [Meta — Service messages & the customer service window](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages)
- [Sarvam AI — API pricing](https://www.sarvam.ai/api-pricing)
- [Sarvam AI — Saaras speech model docs](https://docs.sarvam.ai/api-reference-docs/models/saaras)
- [Sarvam AI — Saarika ASR docs](https://docs.sarvam.ai/api-reference-docs/models/saarika)
- [Amadeus vs Duffel vs Skyscanner — flight API comparison 2026](https://www.reactflights.com/blog/best-flight-apis-comparison)
- [Amadeus Self-Service alternatives (portal closure 17 Jul 2026)](https://tripgic.com/playbook/amadeus-self-service-api-alternatives/)
- [Text message reminders & medication adherence — systematic review & meta-analysis (BMC Endocrine Disorders)](https://link.springer.com/article/10.1186/s12902-023-01268-8)
- [Age-Sensitive Usability in Conversational AI Agents: A Systematic Review](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12761613/)
- [Designing Conversational AI for Aging: A Systematic Review (CHI 2025)](https://dl.acm.org/doi/10.1145/3706598.3713578)
- [Situated Understanding of Errors in Older Adults' Interactions with Voice Assistants (month-long in-home study)](https://arxiv.org/abs/2403.02421)
- [Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers](https://arxiv.org/html/2603.07670v1)
- [Tech-Savvy Seniors: ICT Adoption among Senior Citizens in Urban India](https://rsisinternational.org/journals/ijriss/articles/tech-savvy-seniors-ict-adoption-and-social-connectivity-among-senior-citizens-in-urban-india/)
- [WhatsApp statistics 2026 — India user base & age segments](https://hyperleap.ai/blog/whatsapp-statistics-india-2026)
- [India's DPDP Rules — phased enforcement timeline](https://www.privacyworld.blog/2025/11/india-passes-the-digital-personal-data-protection-rules-ushering-in-a-new-digital-age-in-india/)
