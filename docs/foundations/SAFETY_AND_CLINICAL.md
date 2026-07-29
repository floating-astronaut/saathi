# Safety and clinical grounding

This doc feeds `saathi/safety/classifier.py` — the deterministic, pre-LLM
regex classifier that runs before the model sees anything (PRD §12, risk R7).
It exists so that additions to the classifier's pattern lists are traceable to
a clinical or evidentiary reason, not vibes. Read `saathi/safety/classifier.py`
alongside this — the two should stay in sync; this doc is not a restatement of
the code, it's the reasoning behind it plus what the code doesn't cover yet.

---

## 1. Medication adherence — does reminding actually work?

**Yes, modestly, and the effect is real but not large.** The PRD's cited
figure is confirmed: a systematic review/meta-analysis of **9 RCTs (n=1,121)**
on SMS medication reminders in type 2 diabetes found a pooled effect of
**SMD 0.36 (95% CI 0.14–0.59)** vs. usual care, with a larger effect
(**SMD 0.45, 95% CI 0.22–0.68**) in the subgroup of interventions running
longer than six months.¹ That's a real, positive, modest, *durable* effect —
consistent with PRD's framing that this is a retention-shaped product, not a
one-shot fix. (Flag: the exact subgroup-vs-outcome-type breakdown in the
source came via automated extraction from a partially paywalled page — worth
a human re-read of the primary PDF before quoting the 0.45 figure in anything
external.)

**Beyond diabetes, the picture is weaker.** A cardiac-disease-specific
meta-analysis shows similarly modest short-term gains,² but a 2024 large trial
found generic reminder texts, behavior-nudge texts, *and* nudge+chatbot texts
**all failed to improve 12-month refill adherence** vs. control.³ Read
together: reminders help in the short-to-medium term and the effect compounds
somewhat with duration, but **don't oversell long-horizon impact** — no
reminder design tested so far reliably beats habituation over a full year.

### What makes reminders fail

- **Message fatigue / habituation** on long-running chronic therapy — the
  same message, forever, stops registering.
- **Genericness.** Personalized/tailored messages outperform generic ones
  consistently across the literature; this is one of the few reliably
  replicated findings in the space.
- **One-way vs. two-way is theorized, not proven** — two-way (ack required)
  is plausible on mechanism but the evidence base for it beating one-way
  specifically is thin.⁴

**Design implication already in the product:** Saathi's reminder flow is
already two-way (acknowledged with a reply button, snoozeable — PRD C2), and
`reminder_fires` tracks ack rate directly (PRD §15 targets >70%). That's the
right shape given the evidence, but the evidence doesn't guarantee it beats
one-way messaging — it's a reasonable bet, not a proven one. **What the
evidence does support clearly:** avoid generic, identical-forever phrasing;
personalize where possible (the medicine name, the person's own words for it).

---

## 2. Phrasing a reminder without giving advice

There is no single codified rule (Indian or otherwise) governing exactly how
an AI system should phrase a medication reminder. The closest available
guidance is the US FDA's enforcement-discretion practice for "general
wellness" tools: reminder-only functionality avoids regulatory scrutiny as
long as it does not make individualized diagnostic or dosing recommendations,
and emerging 2026 commentary (following FDA's first AI warning letter) treats
"don't double a missed dose"-style generic instructions as acceptable but
individualized dose/interaction judgment calls as not.⁵ **This is informal,
emerging guidance, not a binding standard — flagged as such.**

**The line that matters in practice, and that the classifier already
encodes:** a reminder states *that* something is due; it never decides *what*
to do about a missed dose, a dose change, or an interaction question. The
existing `MEDICAL_ADVICE` trigger in `classifier.py` is built exactly on this
line — `"kitni goli"`, `"dose kitn"`, `"should i (take|stop)"` all route to a
decline-and-redirect, never to the model. That's the correct design; this doc
just makes explicit *why* it's the correct line, since "no dosing advice,
ever" is a rule worth being able to defend, not just follow.

---

## 3. Red-flag symptoms — clinical grounding for the classifier

The classifier's `MEDICAL_EMERGENCY` trigger already covers chest pain,
breathing distress, falls, and stroke signs. Below is the clinical basis for
each, plus one gap the code does not currently cover.

### Chest pain / cardiac
AHA guidance: chest pressure/tightness/squeezing lasting more than ~15
minutes, radiating to arm/neck/jaw, with shortness of breath, cold sweat,
nausea, or lightheadedness — treat as an emergency even when uncertain.⁶
Matches `classifier.py`'s `_EMERGENCY` patterns (`seene? me[ni]?n? dard`,
`heart attack`, `dil ka daura`).

### Stroke — FAST
**Face, Arms, Speech, Time** remains the current standard mnemonic (American
Stroke Association), derived from the Cincinnati Prehospital Stroke Scale.
BE-FAST (adding Balance and Eyes) has been studied as a more sensitive
alternative but FAST is still the primary standard in 2025–26 guidance.⁷ No
distinct ICMR/AIIMS mnemonic was found. `classifier.py` covers the Speech
(`bolne me[ni]?n? dikkat`) and a face/sensory proxy (`muh tedha`, `ek taraf
sunn`) but has **no explicit Arms/weakness pattern** (e.g. `"haath me[ni]?n?
kamzori"`, `"ek taraf kamzori"`, `"weakness on one side"`) — worth adding.

### Falls
Emergency-level triggers per clinical guidance: unconsciousness, heavy
bleeding, inability to get up or move, hip pain after a fall (can mask a
fracture painlessly in osteoporotic elders), or any head-injury sign
(confusion, vomiting, severe headache, loss of consciousness).⁸ `classifier.py`
covers the fall event itself (`gir ga(ya|yi|ye)`, `fell down`, `utha nahi ja`)
and unconsciousness (`behosh`, `unconscious`) but **has no explicit head-injury
or hip-pain-after-fall pattern** — a fall message followed by confusion or
severe headache should escalate as hard as the fall itself; currently it would
only match on the fall phrase, not the follow-on severity signal.

### Breathlessness
Emergency red flags: sudden-onset or at-rest dyspnea, inability to speak in
full sentences, chest pain, bluish lips/face, fainting/confusion, coughing
blood, irregular heartbeat.⁹ `classifier.py` covers this well (`saans nahi
aa`, `saans phool`, `saans ruk`, `can'?t breathe`, `dam ghut`).

### Hypoglycemia — a real gap in the current classifier
Given that many users on medication reminders are diabetic, low blood sugar
is a directly relevant emergency category **the classifier does not currently
have a trigger for at all.** ADA thresholds: Level 1 (54–70 mg/dL, mild),
Level 2 (<54 mg/dL, neuroglycopenic symptoms — confusion, slurred speech,
sweating, shakiness), Level 3 (severe — requires help from another person,
including unconsciousness; call emergency services immediately if unconscious
or unable to swallow).¹⁰ **Recommended additions to `_EMERGENCY`** (Hindi/
Hinglish phrasings a user would plausibly type or say):

- `sugar gir gaya`, `sugar low ho gaya`, `sugar kam ho gaya`
- `chakkar aa raha hai aur pasina` (dizziness + sweating together)
- `haath kaanp raha hai aur sugar` (shaking + sugar mentioned)
- `hypoglycemia`, `low sugar`, `sugar low`

This is flagged as a recommendation for the classifier, not applied here —
`saathi/safety/classifier.py` should be updated separately, with its own test
coverage, per `CONTRIBUTING.md`'s rule that behaviour changes need a test.

---

## 4. Indian emergency numbers and mental-health helplines — currency check

All four numbers currently in `classifier.py` were verified as active in
2026:

| Number | Service | Status |
|---|---|---|
| **112** | National emergency (police/fire/ambulance), via 112.gov.in | Active, confirmed |
| **108** | State ambulance services | Active in parallel with 112; not retired |
| **14416** | Tele-MANAS, Govt of India mental-health helpline, 20+ languages | Active, confirmed |
| **1800-599-0019** | KIRAN mental-health helpline | Listed as active, but see caveat below |

**Caveat on KIRAN:** some secondary sources describe KIRAN as being
operationally folded into Tele-MANAS, with 14416 becoming the primary front
door.¹¹ No single authoritative government notification confirming full
consolidation was found — **treat both numbers as valid for now**, but revisit
before the next classifier update in case KIRAN is formally retired.

**One number the classifier doesn't have, and should:** **1930**, India's
dedicated cybercrime/financial-fraud helpline (report a scam, attempt to
freeze a fraudulent transfer fast).¹² This belongs in the `SCAM` reply, not
just the emergency numbers — the current `SCAM` reply text warns not to share
OTP/PIN but gives no number to call if the user already has been scammed or is
mid-scam. **Recommended addition** to the `Trigger.SCAM` reply copy.

---

## 5. Elder fraud patterns in India — for the `SCAM` trigger's wordlist

### Digital arrest
Fraudsters impersonate CBI/police/RBI/TRAI/ED officials over a video call,
claim the victim is under investigation (often a package/drugs/money-
laundering pretext), and coerce "cooperation" — money transfers — to avoid a
fake arrest. No Indian agency ever conducts an arrest, investigation, or
demand for money via WhatsApp video call.¹³ Reported losses: ₹2,140 crore over
18 months nationally; individual elderly victims have lost ₹2–3+ crore in
single incidents.¹⁴ **Hindi/Hinglish phrasings worth adding to the classifier**
(not currently covered — `classifier.py`'s `_SCAM` list is OTP/PIN/KYC/lottery
-focused, not digital-arrest-focused):

- `digital arrest`, `cbi se baat kar raha`, `police video call kar rahi hai`
- `mujhe girftar kar lenge`, `case dark web`, `parcel mein drugs mila`
- `court se warrant aaya hai`

### KYC / UPI / lottery
Already well-covered in `classifier.py` (`kyc update`, `otp`, `pin`, `cvv`,
`lottery`, `kbc`, `crore jeet`, `account (block|band)`). Confirmed still the
dominant fraud shape: QR-code/collect-request UPI fraud is roughly **40% of
FY26 UPI fraud value (₹805 crore)**¹⁵; fake "your KYC has expired, account
will be blocked in 24 hours" messages remain the standard phishing pretext,
and real banks never process KYC via an SMS/WhatsApp link.¹⁶

### Scale
MHA/I4C reported **₹22,495 crore lost to cyber fraud in 2025** (28.15 lakh
cases, +24% YoY nationally).¹⁷ Senior-citizen-specific loss is reported
informally at **over ₹2,000 crore**, but one source notes this figure is not
consistently tracked as its own category in government data — **treat the
elder-specific total as approximate, not precise.**¹⁸

---

## Sources

1. SMS medication reminders in T2DM, systematic review & meta-analysis, BMC
   Endocrine Disorders — https://link.springer.com/article/10.1186/s12902-023-01268-8
   ; full text — https://pmc.ncbi.nlm.nih.gov/articles/PMC9850787/
2. SMS reminders in coronary heart disease, meta-analysis (PMC) —
   https://pmc.ncbi.nlm.nih.gov/articles/PMC6946488/
3. 12-month refill-adherence trial (reminders + chatbot nudges failed to
   move the needle at one year), News-Medical coverage —
   https://www.news-medical.net/news/20241202/Text-message-reminders-fail-to-boost-long-term-medication-adherence.aspx
4. REINFORCE trial, npj Digital Medicine — https://www.nature.com/articles/s41746-024-01028-5
5. FDA oversight of health AI tools / general-wellness enforcement discretion —
   https://bipartisanpolicy.org/issue-brief/fda-oversight-understanding-the-regulation-of-health-ai-tools/
   ; FDA's first AI warning letter (2026) commentary —
   https://teledirectmd.com/health-guides/fda-first-ai-warning-letter-2026/
6. American Heart Association, heart attack warning signs —
   https://www.heart.org/en/health-topics/heart-attack/warning-signs-of-a-heart-attack
7. FAST vs. BE-FAST precision study (PMC) —
   https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11029396/ ; BE-FAST trial,
   Journal of the American Heart Association —
   https://www.ahajournals.org/doi/10.1161/JAHA.123.035696
8. Falls in the elderly — what to do — Village Caregiving —
   https://villagecaregiving.com/blog/what-to-do-after-a-fall/ ; Henry Ford
   Health — https://www.henryford.com/services/senior/after-a-fall
9. Shortness of breath — emergency red flags — VHTC clinical overview —
   https://www.vhtc.org/2025/12/shortness-of-breath-causes-diagnosis-treatment.html
10. American Diabetes Association, severe hypoglycemia thresholds —
    https://diabetes.org/living-with-diabetes/hypoglycemia-low-blood-glucose/severe
11. Tele-MANAS official site — https://telemanas.mohfw.gov.in/ ; KIRAN launch,
    Press Information Bureau — https://www.pib.gov.in/pressreleaseshare.aspx?prid=1652240
12. India's national cybercrime helpline (1930) and 112.gov.in —
    https://112.gov.in/about
13. Digital arrest scam mechanics — Legal Service India —
    https://www.legalserviceindia.com/Legal-Articles/digital-arrest-scams-in-india-cyber-fraud-safety-tips/
14. Digital arrest case example — Deccan Herald —
    https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Felderly-woman-falls-prey-to-digital-arrest-loses-rs-3-09-cr-3674822
15. UPI fraud trends, FY26 — the420.in —
    https://the420.in/india-upi-fraud-data-fy26-parliament-digital-payments/
16. KYC scam examples — ScanTotal —
    https://scantotal.net/blog/kyc-update-scam-india/
17. MHA/I4C 2025 cybercrime figures — Outlook Money —
    https://www.outlookmoney.com/retirement/news/cybercrime-surges-212-per-cent-in-five-years-since-2019-senior-citizen-specific-data-not-tracked
18. Same source as 17 — explicitly notes senior-citizen figures are not
    separately tracked in government data; ScamWatchHQ 2026 India roundup —
    https://scamwatchhq.com/india-scams-2026-digital-arrest-upi-fraud-epidemic/

## What could not be verified

- The exact duration-vs-outcome-type subgroup structure inside the BMC
  meta-analysis (source #1) — extracted via automated fetch of a partially
  paywalled page; re-read the primary PDF before quoting the 0.45 figure
  externally.
- Full KIRAN/Tele-MANAS consolidation status — no single authoritative
  government notification found either way.
- Any Indian-specific (vs. US FDA) regulatory standard for how an AI reminder
  tool may phrase itself without crossing into medical advice — none exists;
  the FDA framing is the best available analogy, not a binding local rule.
- A precise, government-sourced figure for senior-citizen-specific cyber-fraud
  losses in India — the ~₹2,000 crore figure is a secondary estimate, not an
  official breakdown.
