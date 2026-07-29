# Regulatory — India (DPDP) and WhatsApp Business Platform

This corrects two specific numbers in PRD §13 and adds the WhatsApp Business
Platform policy constraints the PRD doesn't cover at all. Read alongside
`docs/DECISIONS.md` D-B (Postgres in Mumbai from the first schema write) and
D-K (the training-corpus privacy design), both of which anticipate this.

**Sourcing note:** the Gazette PDF itself (meity.gov.in) and the PIB press
release PDF could not be fetched as readable text during this research —
findings below rest on the PIB press-release *page* (primary, one level
removed from the Gazette) plus law-firm secondary summaries where marked.
Anything not explicitly marked "primary" should be treated as secondary and
re-verified against the Gazette text before being relied on for a compliance
decision.

---

## 1. When the DPDP Rules 2025 actually notified

**There's a one-day discrepancy that resolves cleanly, not a real dispute.**
Several law-firm summaries cite Gazette Notification **G.S.R. 846(E), dated
13 November 2025**; the Ministry's own PIB press release states the Rules
"were notified on **14 November 2025**."¹ This is the ordinary India pattern
of gazette-publication-date vs. next-day-announcement-date. **Use 13 Nov
2025 as the legal/gazette date**, and note 14 Nov as the date it was
publicly announced, if precision matters for a filing.

## 2. Phased enforcement timeline — PRD §13's dates are correct, attribution needs tightening

The PIB release itself confirms an **18-month phased rollout**.¹ The
granular rule-by-rule mapping (secondary-sourced, via a law-firm summary, not
verified against the Gazette text directly) is:

| Date | What takes effect |
|---|---|
| 13/14 Nov 2025 | Rules 1, 2, 17–21 — Data Protection Board formation and administration only. **No obligations on Data Fiduciaries yet.** |
| 13/14 Nov 2026 (+12 mo) | **Rule 4 only** — Consent Manager *registration* opens. This is narrower than "consent-manager provisions kick in" — it's registration for entities wanting to *operate as* a Consent Manager, not a general obligation on an ordinary Data Fiduciary like Saathi. |
| 13/14 May 2027 (+18 mo) | Rules 3, 5–16, 22–23 — the substantive obligations: itemized notice, consent mechanics, data-principal rights, breach reporting, security safeguards, cross-border rules, Significant Data Fiduciary obligations. |

**Confirms PRD §13's claim** that full operational compliance — standalone
notice in prescribed languages, 72-hour breach reporting — begins 13 May
2027. **Correction to PRD §13's framing of the Nov 2026 milestone**: reword
"consent-manager provisions kick in Nov 2026" to specify it is Consent
Manager *registration*, not a compliance obligation that touches Saathi
directly.

## 3. Consent (Section 6)

Verbatim, consent must be **"free, specific, informed, unconditional and
unambiguous with a clear affirmative action,"** limited to the personal data
necessary for the specified purpose, given only after the itemized notice
required by Section 5, and must be **as easy to withdraw as to give**.²
Directly actionable: Saathi's onboarding consent flow (PRD §13) needs an
equally easy withdrawal path, not just an easy grant path — "forget
everything about me" (already a stated day-one requirement) is the right
shape for this.

## 4. Data Fiduciary obligations and Significant Data Fiduciary status

Section 10 lets government designate specific entities as **Significant Data
Fiduciaries (SDF)** based on volume/sensitivity of data, risk to
data-principal rights, and sovereignty/security/public-order factors.³ **No
quantitative thresholds have been formally notified** — SDF status is
assigned by government notification, not self-assessment. Secondary
commentary flags health/biometric/financial data at scale and 10M+ data
principals as likely triggers, but this is illustrative, not codified. **At
current scale, Saathi is very unlikely to be designated an SDF** — but this
should be revisited if the user base or data-sharing scope grows
significantly, since designation is not something you can rule out by
policy alone.

## 5. Grievance Officer

Section 8(9)–(10) requires every Data Fiduciary to publish grievance-officer
contact details and respond to complaints.⁴ Secondary sources converge on a
**90-day** response window, but this figure was not independently confirmed
against the Gazette text — **treat as probably-right, not verified.**

## 6. Cross-border transfer (§16) — correcting a common mischaracterization

**Section 16(1) is a blacklist model, not a whitelist.** Verbatim: *"The
Central Government may, by notification, restrict the transfer of personal
data by a Data Fiduciary for processing to such country or territory outside
India as may be so notified."*⁵ Transfer is **permitted by default**
everywhere; the government can name specific restricted destinations. One
secondary aggregator's interpretation notes mislabel this as a whitelist
approach — that reading is wrong against the statutory text itself. **As of
this research, no countries have been blacklisted.** Since Saathi's
infrastructure is already entirely within India (D-B), Section 16 currently
imposes no practical restriction either way — but if any future integration
sends data to a non-Indian processor (e.g. a US-based API), re-check this
list at that time.

## 7. Health data — no special tier exists under DPDPA

**Important correction to how PRD §13 frames this.** DPDPA has **no
GDPR-style "special category" tier and no SPDI-style "sensitive personal
data" tier** carried forward from the old IT Rules regime — all personal
data is regulated uniformly under DPDPA.⁶ Health/medical data gets no
automatic heightened statutory obligation, except as a *factor* feeding into
SDF designation (§4 above) and as a practical driver of the Section 8(5)
"reasonable security safeguards" obligation, which is risk-proportionate by
its own terms.

**PRD §13 already says "treat as sensitive by policy even where not required
by law" — that framing turns out to be exactly correct**, and this doc makes
explicit why it's necessary rather than optional caution: there is no legal
floor doing this work for you. **Do not describe Saathi's medicine/
appointment data as "sensitive personal data" under Indian law in any
external-facing document** — that term doesn't mean anything under DPDPA and
using it invites a category error with GDPR-trained readers.

## 8. Penalties — correcting which figure attaches to what

**Two distinct figures exist and PRD §13 conflates them.** **₹250 crore** is
the maximum penalty for breach of **Section 8(5)** — failing to implement
reasonable security safeguards to *prevent* a breach in the first place. A
**separate ₹200 crore** maximum applies specifically to **failure to notify**
the Board/Data Principals of a breach that already happened (Rule 7).⁷ If
PRD §13 cites ₹250 crore for "breach reporting" failure specifically, that's
the wrong figure paired with the wrong obligation — ₹250 crore is for the
underlying security failure, ₹200 crore is for failing to report it.
**Correct PRD §13 to cite both figures separately.**

Breach notification itself: initial intimation without delay, detailed
report to the Board within **72 hours** (extendable on written request) —
this specific figure is secondary-sourced only, matching PRD §13's existing
claim, but not independently verified against the Gazette.

---

## 9. WhatsApp Business Platform policy constraints

### Health/telemedicine restriction — the one that matters most, and is genuinely ambiguous
Meta's WhatsApp Business Messaging Policy, Section 3 ("Protect Data and
Comply with Law"), states verbatim: **"Don't use WhatsApp for telemedicine or
to send or request any health related information, if applicable
regulations prohibit distribution of such information to systems that do
not meet heightened requirements to handle health related information."**⁸
This is conditioned entirely on "applicable regulations" — and finding #7
above establishes that **DPDPA does not currently impose GDPR-style
heightened health-data-handling requirements.** The practical bite of this
Meta clause under Indian law is genuinely unclear from the text alone.
**This is a real open question for counsel, not something this doc can
resolve** — Saathi stores medicine names and appointment reminders, which
sit close to this line even if not clearly over it.

### Utility template category (directly relevant to reminders)
Confirmed rules: a Utility template must be non-promotional and either
specifically requested by the user or "essential/critical" (the allowed
buckets include account alerts, payment/plan reminders, and health
emergencies/fraud warnings).⁹ Routine medicine/appointment reminders
plausibly fit the account-alert/critical-reminder bucket — this is
consistent with `docs/LANDMINES.md`'s finding that anchoring reminder copy
to the user's own prior action ("aapne jo reminder set kiya tha...") got
Saathi's templates classified UTILITY rather than the 7.5×-costlier
MARKETING. Any future template copy should keep that anchoring — it isn't
just a cost optimization, it's what keeps the template inside the
non-promotional definition at all.

### No age/vulnerable-user provisions
Meta's WhatsApp Business Messaging Policy has **no elderly or
vulnerable-user category at all.** The only age-gating anywhere in the
policy is an under-18 restriction tied to Regulated Verticals (alcohol,
gambling, OTC drugs) — irrelevant to an eldercare product for adults 60+.
**There is no special extra protection or extra restriction that applies
specifically to messaging elderly users** as such under this policy.

### Data handling for Business Solution Providers
Confirmed: a BSP may not use data obtained through WhatsApp about a person
"other than the content of message threads, for any purpose other than as
reasonably necessary to support messaging with that person," and chats may
not be forwarded or shared with other customers.⁸ **No explicit retention
period or clarification of End-to-End-encryption implications for a bot
reading message content was found in this policy text** — this needs a
follow-up read of Meta's separate Cloud API / Business API data-processing
terms if a specific retention window needs to be defended to a regulator or
auditor.

---

## Sources

1. Digital Personal Data Protection Rules 2025, PIB press release (primary) —
   https://www.pib.gov.in/PressReleasePage.aspx?PRID=2190655 ; phased-timeline
   detail (secondary) — S.S. Rana & Co., https://ssrana.in/articles/meity-notifies-final-digital-personal-data-protection-rules-2025/
   ; MeitY Rules page (primary location, not fully readable via fetch) —
   https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa
2. DPDPA 2023, Section 6 (consent) — https://www.dpdpa.com/dpdpa2023/chapter-2/section6.html
3. DPDPA 2023, Section 10 (Significant Data Fiduciary) — secondary commentary,
   Vakilsearch — https://vakilsearch.com/article/significant-data-fiduciary-sdf/
4. DPDPA 2023, Section 8(9)–(10) (grievance officer) —
   https://www.dpdpa.com/dpdpa2023/chapter-2/section8.html
5. DPDPA 2023, Section 16 (cross-border transfer) —
   https://www.dpdpa.com/dpdpa2023/chapter-4/section16.html ; blacklist-model
   confirmation — https://ksandk.com/data-protection-and-data-privacy/dpdp-act-2023-whitelist-blacklist-rules-for-data/
6. DPDPA health-data treatment (no special category) — JSA Prism —
   https://www.jsalaw.com/wp-content/uploads/2025/01/JSA-Prism_Data-Privacy-DPDPA_Edition-12.Final_.pdf
   ; SNR Law — https://www.snrlaw.in/sense-and-sensitivity-sensitive-information-under-indias-new-data-regime/
7. Breach-notification penalty structure (₹250cr vs ₹200cr) — DPDPA Edu, Rule 7 —
   https://dpdpaedu.org/docs/DPDPA%20Rules/Intimation%20of%20Personal%20Data%20Breach/
   ; RingSafe penalty explainer — https://ringsafe.in/dpdp-penalties-explained/
8. WhatsApp Business Messaging Policy (official; whatsapp.com/legal/business-policy/
   redirects here) — https://whatsappbusiness.com/policy/
9. Meta, WhatsApp template categorization (Utility category rules) —
   https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization

## What could not be verified

- The Gazette PDF and PIB press-release PDF themselves — all findings above
  rest on the PIB press-release *page* and secondary law-firm summaries;
  re-verify against the primary Gazette text before relying on this for an
  actual filing or compliance defense.
- The exact 90-day grievance-response window — secondary-sourced only.
- Any explicit Meta-stated retention period for message content held by a
  Business Solution Provider, or a clear statement of how E2E encryption
  interacts with a bot reading message content on Meta's side.
- Whether the WhatsApp health/telemedicine restriction (§9) actually
  constrains Saathi in practice — this hinges on an unresolved question
  (whether DPDPA counts as "applicable regulations prohibiting distribution
  ... to systems that do not meet heightened requirements") that this doc
  cannot resolve and should go to counsel.
