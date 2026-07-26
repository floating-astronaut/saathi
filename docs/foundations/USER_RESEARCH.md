# User research — Indian adults 60+

Product/domain foundation, not architecture. See `docs/foundations/README.md`
for how this fits with `docs/PRD.md`.

**This doc corrects several PRD §2 statistics.** The PRD's citation for its
adoption numbers is internally inconsistent — it names an academic paper that
does not contain the numbers attributed to it. Read this before quoting PRD §2
in anything user-facing.

---

## 1. Correcting PRD §2's numbers

The PRD cites "Tech-Savvy Seniors: ICT Adoption among Senior Citizens in Urban
India" (RSIS/IJRISS) for "~40% own smartphones," "66% find digital tools
confusing," and "51% fear making errors." **That paper does not contain any of
these three figures.** It is a real, small study (n=155, Delhi only, 2025) with
its own numbers: 52% comfortable using the internet, 53% report adequate
internet knowledge, 69% need help with internet services.¹

The 40% / 66% / 51% figures are real, but belong to a different, larger study:

> **HelpAge India, "Understanding Inter-generational Dynamics & Perceptions on
> Ageing"** (June 2025, n=5,798, ~30% aged 60+, 10 metro and non-metro
> cities).² Reports: **41%** of seniors use/own a smartphone; **66%** find
> digital tools confusing; **51%** fear making errors; additionally 44% feel
> embarrassed asking for help, 24% fear damaging the device, and 54%/52%
> name children/grandchildren respectively as their digital guide.

**Action:** re-cite HelpAge India (2025) for these three numbers instead of the
RSIS paper. The RSIS paper is still usable, but for its own (different, more
modest) figures.

**"77% text-savvy"** — could not verify. Secondary mentions attribute it to a
"State of Seniors" study by Antara Senior Living + Access Media International,
but no report, press release, or PDF could be located — only a Medium post
repeating the number.³ **Unverified. Drop it or mark it explicitly as
unsourced** rather than repeat it as fact.

**"~615M WhatsApp users in India; 56+ is ~13% of the base; 55–64 is the
fastest-growing segment globally"** — **unverified, likely unreliable.** Meta
does not publish country- or age-segmented WhatsApp usage data for India; every
number in circulation traces to third-party estimators, not a primary source.
Total-user estimates for 2026 range 535.8M–615M depending on which blog you
read.⁴ Fetching the PRD's own cited source directly shows it gives **9% for the
55+ segment**, not 13%, and cites no source at all for its age breakdown.⁵ The
"55–64 fastest-growing globally" line appears near-verbatim across several
unrelated marketing blogs — a recycled claim, not a traceable finding.

**What to do with this:** do not lead a pitch deck or the PRD summary with the
WhatsApp-user-count claim. It is *probably* directionally true (WhatsApp
dominance among Indian internet users generally is well established) but the
specific age-segment numbers are not supportable. Use "WhatsApp is the
dominant messaging app for Indian smartphone users of all ages" as the
defensible version, and cite HelpAge India for anything about the 60+ segment
specifically.

---

## 2. Digital confidence and barriers (HelpAge India, 2025)²

- 66% find digital tools/apps confusing to use.
- 51% fear making errors while using a device or app.
- 44% feel embarrassed asking for help.
- 24% fear damaging the device itself.
- 54% name their children, 52% their grandchildren, as who they turn to for
  digital help.
- 41% use/own a smartphone (this is the base rate the other percentages sit
  on top of — a minority-adoption population, not a majority one).

This is the strongest single source for the "who sets up the phone" and
"barriers are confidence, not access" claims in the PRD. It directly supports
PRD's framing that the interface is the product, not the device.

---

## 3. Literacy, script, and code-mixing

**Unverified as a population-specific finding — flagged as a real research
gap, not filled in with a guess.** General Hindi/English code-mixing (Hinglish)
corpora and NLP research exist and confirm the *phenomenon* is real and heavily
studied at the language level (PHINC⁶, HiACC⁷), and Gboard supports
Hindi-transliteration and Hinglish input on Android. But no age-segmented study
of *which script* Indian seniors specifically type in (Devanagari vs. Latin
transliteration vs. English) was found, nor any elder-specific typing-behavior
data.

**What this means for Saathi, stated as inference, not evidence:** the
existing safety classifier (`saathi/safety/classifier.py`) already assumes
Latin-script Hinglish alongside Devanagari and English — e.g. `"seene? me[ni]?n?
dard"`, `"khudkushi"`, `"otp"` — which is a reasonable prior given general
Hinglish-corpus research, but is not itself validated against how *this*
population types. Treat it as a working assumption to be corrected by real
usage data (the classifier hit-rate is measurable once live), not as
literature-backed fact.

---

## 4. Vision and motor constraints

**Vision.** India has high, poorly corrected presbyopia: uncorrected
presbyopia affects roughly **a third of the population nationally**, rising to
**42.9% in a rural Haryana sample**; spectacle coverage for presbyopia is only
**23.9–25.8%**.⁸ Practical reading: a meaningful share of the target users are
looking at the screen with worse effective vision than "elderly" alone implies
— font size and contrast matter more than for an equivalent Western elder
population with better-corrected vision, and more than typical UI guidance
assumes.

**Motor.** No India-specific touchscreen-motor study was found. Generalizable
aging-HCI research (not India-specific, but not disputed) shows: smaller
touch targets increase corrective sub-movements and slow reaction time in older
adults⁹; tremor degrades tap accuracy more than swipe/drag gestures¹⁰.
Practical reading: prefer large tap targets and swipe/button confirmation over
precise taps, and don't assume a missed or double-tap is user error rather than
a motor-precision limit.

---

## 5. Who sets up the phone

HelpAge India (2025) is again the load-bearing source: **54% of adult children
and 52% of grandchildren** act as the elder's "digital guide."² This directly
supports PRD's framing of the adult child as installer/onboarder (D1) — but
note the study measures *ongoing* help-seeking, not specifically *initial
setup*, so "who installs the app" and "who the elder calls when confused" may
not be the same person in every household. Treat the onboarding-is-for-the-
child design decision as well-supported in spirit, not literally proven for
the exact moment of install.

General (non-India) "use-by-proxy" literature on older adults delegating
technology setup to family exists¹¹ but wasn't found in an India-specific form
beyond HelpAge.

---

## 6. Voice notes vs. typing

**Unverified as hard data.** No quantitative Indian telecom/OTT/WhatsApp usage
study with actual percentages of voice-note-vs-typed-message use by seniors was
found. The directional claim (elders prefer voice notes over typing, for
literacy, vision, and expressiveness reasons) is widely repeated in
industry-blog commentary but not backed by a cited survey anywhere located.
**This is a genuine gap** — worth instrumenting from week 1 rather than
assumed, since PRD §15 already tracks "voice-note share of inbound" without a
target, which is the right call given there is no baseline to target against.

---

## 7. Metro vs. smaller cities — a real, supportable distinction

Unlike most of the numbers above, this split has decent evidence behind it and
should be treated as real, not speculative:

- IAMAI–Kantar's ICUBE report: **rural India is now 57% (≈548M) of India's
  active internet base**, and growing faster than urban.¹²
- A rural telehealth study (DAHLIA)¹³ found ~50% mobile *ownership* among
  rural elderly but very low smartphone/internet *use* — under 10% used the
  internet to contact a health service — a much starker access gap than
  HelpAge's urban-skewed 41% smartphone-use figure.

**Practical reading:** HelpAge's 41%/66%/51% figures should be read as
describing the more digitally-engaged, metro-and-non-metro-city population
they sampled (10 cities) — not rural India, where basic smartphone/internet
use among elders is markedly lower. If Saathi's early cohort is urban/tier-1
(consistent with adult-child-as-buyer, D1), the HelpAge numbers are the right
reference population. If the product later expands toward smaller towns or
rural users, expect materially worse baseline digital confidence and possibly
a device-ownership floor to solve first, not just a UX problem.

---

## Sources

1. Tech-Savvy Seniors: ICT Adoption among Senior Citizens in Urban India (RSIS
   International, IJRISS, 2025) — https://rsisinternational.org/journals/ijriss/articles/tech-savvy-seniors-ict-adoption-and-social-connectivity-among-senior-citizens-in-urban-india/
2. HelpAge India, "Understanding Inter-generational Dynamics & Perceptions on
   Ageing" (June 2025), as reported by Business Standard —
   https://www.business-standard.com/technology/tech-news/senior-citizens-struggle-with-digital-technology-helpage-india-study-125061300809_1.html
   and Communications Today — https://www.communicationstoday.co.in (June 2025 coverage)
3. "You Won't Believe How Seniors Are Using Technology Better Than
   Millennials" (Medium, secondary repetition of an untraceable "77%"
   figure) — https://girishs307.medium.com/you-wont-believe-how-seniors-are-using-technology-better-than-millennials-6cf1c33683fd
4. World Population Review, WhatsApp user estimates —
   https://worldpopulationreview.com ; GrabOn blog, WhatsApp India stats —
   https://grabon.in
5. Hyperleap, "WhatsApp statistics 2026 — India user base & age segments"
   (source cited by PRD §2; direct fetch shows 9% for 55+, no source given
   for the age table) — https://hyperleap.ai/blog/whatsapp-statistics-india-2026
6. PHINC: A Parallel Hinglish Social Media Code-Mixed Corpus for Machine
   Translation — https://arxiv.org/pdf/2004.09447
7. HiACC — Hindi-English code-mixed corpus study —
   https://pmc.ncbi.nlm.nih.gov/articles/PMC12329218
8. Presbyopia prevalence and spectacle coverage in India — Nature Scientific
   Reports — https://www.nature.com/articles/s41598-023-50288-w ; IOVS
   rural Haryana study — https://iovs.arvojournals.org/article.aspx?articleid=2125147
9. Touch-target size and older-adult reaction time — Springer HCII —
   https://link.springer.com/chapter/10.1007/978-3-540-73279-2_104 ; ACM
   study — https://dl.acm.org/doi/10.1145/2384916.2384939
10. Tremor and touchscreen tap accuracy in older adults — PMC —
    https://ncbi.nlm.nih.gov/pmc/articles/PMC8431526
11. Technology delegation / "use by proxy" among older adults (general,
    not India-specific) — https://tandfonline.com/doi/full/10.1080/10447318.2025.2577782
12. IAMAI–Kantar ICUBE, rural internet base overtaking urban —
    https://www.business-standard.com/industry/news/indian-internet-user-base-crosses-950-million-in-2025-iamai-report-126012901048_1.html
13. DAHLIA rural telehealth / elderly digital-health-access study (PMC) —
    https://pmc.ncbi.nlm.nih.gov/articles/PMC8938771

## What could not be verified (summary)

- "77% text-savvy" — no primary source found.
- "615M WhatsApp users, 56+ ≈13% of base, 55–64 fastest-growing globally" —
  no primary source; the PRD's own cited page gives 9%, not 13%, with no
  source for the age table at all.
- Any quantitative India-specific data on voice-note vs. typed-message
  preference among seniors.
- Any age-segmented study of which script (Devanagari / Latin / English)
  Indian seniors actually type in.
- India-specific touchscreen motor-precision research (relied on
  non-India aging-HCI literature instead).
