# Accessibility — concrete rules for this population

Not generic WCAG. Saathi has no screen beyond WhatsApp's own UI — the surface
being designed here is the *conversation*: message length, turn structure,
choice count, error recovery, confirmation. Each rule below is tied to a
source. Where the evidence contradicts or complicates PRD §6, that is stated
plainly rather than smoothed over.

See `docs/foundations/USER_RESEARCH.md` for who these rules are for, and
`docs/foundations/README.md` for how this doc relates to the PRD.

---

## 1. Reading level and message length

**Rule:** target below 10th-grade reading level; break any paragraph over
roughly 50 words; one point per sentence.

**Source:** W3C's Cognitive Accessibility (COGA) guidance recommends breaking
text into short paragraphs, one idea per sentence, and targeting a "lower
secondary education" reading level.¹ Health-literacy research (Center for
Health Care Strategies) documents the standard mismatch: most health materials
are written above 10th-grade level while the average adult reads at roughly
8th grade — the mismatch is worse, not better, for a population disproportion-
ately dealing with health-adjacent content (medicines, appointments).²

**Honest gap:** neither source gives a validated number for Hindi/Hinglish
conversational text specifically, and neither is India- or elder-specific.
Treat "below 10th grade" as an imported heuristic from US health-literacy
research, not a number proven for this exact population and language mix.

---

## 2. One question per turn — supported by inference, not by a direct study

**PRD §6.2:** "Never a multi-part question."

Miller's "7±2"³ is about short-term memory *chunk capacity*, not
choices-per-conversational-turn, and is not aging-specific. Cowan's later
revision puts the true limit closer to **~4 chunks** once rehearsal is
controlled for⁴ — more conservative than Miller, and still not elderly- or
conversation-specific.

**No study was found that directly measures "how many choices per turn" for
elderly users in a conversational-AI context.** PRD §6.2's "one question per
turn" is *more* conservative than even Cowan's 4, so it sits comfortably inside
general cognitive-load literature — but state this as **directionally
supported by inference**, not as an evidenced finding. If anyone asks "where's
the citation for exactly one," the honest answer is: there isn't one; the
number is chosen to be safely below the lowest defensible ceiling in the
adjacent literature, not derived from a study of this exact question.

---

## 3. Confirmation and repetition — PRD §6 needs a rewording, not abandoning

This is the one place research pulls in two directions at once, and it's worth
stating both rather than picking the comfortable half.

**PRD §6.3** says confirm only "consequential slots" (times, dates, dosages,
amounts, proper nouns) and nothing else, because "blanket confirmation is a
documented frustration." **PRD §6.5** says never signal that a question is
being repeated.

**What supports this:** a CHI 2025 systematic review of conversational AI for
aging reports older adults wanting the agent to "reflect, confirm, and adjust"
iteratively⁵ — read carelessly this looks like a case *for* more confirmation.
Read precisely, the desire is for the system to check *task outcomes* and
follow through, not to re-ask questions the user already answered. That
distinction matters: PRD §6.3's "consequential slots only" rule is about
*what* gets confirmed, and is not actually contradicted by wanting more
follow-through on outcomes — those are different dialogue acts. But it is a
genuine tension worth flagging rather than resolving by assertion: the CHI
review is qualitative and small-n aggregated, so treat this as a caution to
watch for in real usage, not a settled finding either way.

**What complicates it, more concretely:** Morrow et al. (a controlled *Human
Factors* study, not just a review) found that **repeating** appointment-style
information **improved memory for both older and younger adults**, with older
adults benefiting specifically on recognition-style retrieval.⁶ That's
evidence *for* restating key facts — which is really PRD §6.3's rule already
("confirm consequential slots"), just under a different name. The useful
distinction PRD §6 should make explicit, and currently doesn't:

> **Restating a fact once, to confirm it, is supported and should happen.
> Signaling to the user that *they* repeated *themselves* is a different act,
> is not supported by any evidence found, and should never happen.** §6.3 is
> the first. §6.5 is the second. They are not in tension with each other, but
> the current wording of §6 could be read as if minimizing confirmation and
> minimizing repetition-shaming were the same instinct — they are not, and a
> future edit that "simplifies" the rule by collapsing them would be a
> regression.

**Recommendation:** reword PRD §6 to separate these two rules explicitly
rather than leave them adjacent and implicitly similar.

---

## 4. Error recovery

**Rule:** when a request fails or is misunderstood, prefer offering the likely
correction over asking the user to rephrase; accept a retry in whatever form
it comes.

**Source:** a month-long in-home study of older adults' voice-assistant
errors found that **repetition/reformulation was the recovery strategy users
reached for themselves** more than any other, and that a lack of specific
feedback about *what* went wrong was a recurring frustration.⁷ This directly
supports PRD §6.6's "errorless by default" framing and §6.4's "own errors
plainly" — but the "never blame the user" *language* specifically (as opposed
to giving concrete feedback) was not itself tested in any source found. Treat
that specific framing as good practice by analogy to the feedback finding, not
as independently evidenced.

---

## 5. Multimodality — voice + text together

**PRD §6.1:** "Voice in, voice + text out. Always send text alongside audio."

**Source:** COGA's design guidance treats redundant multimodal presentation as
a general cognitive-accessibility good practice (don't rely on one channel
alone; make content re-findable and re-readable).¹ No elder-specific study
was found quantifying the benefit of this exact pairing for WhatsApp voice
notes, but it is consistent with COGA's general principle and with the
practical constraint that WhatsApp voice notes are not searchable — the
architectural README already gives an independent, non-research reason for
this (a voice reminder can't be scrolled back to and re-read), so this rule is
over-determined rather than resting on any one source.

---

## 6. Task interruption and resumption

**Rule:** when a multi-turn task (like setting up a reminder) is interrupted,
resuming should restate what's already been captured before asking for what's
missing — not restart from question one.

**Source:** COGA's design guidance specifically covers interruption handling:
show what's been completed, what's current, and what's pending; make
interruptions postponable/suppressible except for genuine emergencies.¹ This
is directly actionable and not currently reflected as an explicit rule
anywhere in PRD §6 — worth adding.

**Note:** the WhatsApp `daily_checkin` and `session_resume` templates
(PRD §11) are the right mechanism for this in principle; whether their actual
copy restates prior state or just says "still there?" is an implementation
detail to verify against this rule, not something this doc can check.

---

## 7. What COGA does *not* give you

Worth stating so nobody goes looking for a number that doesn't exist: **W3C
COGA has no published numeric limit on choices-per-screen or
choices-per-turn.** Anyone citing "COGA says N choices max" is citing
something COGA doesn't say. The 50-word paragraph break and "lower secondary
reading level" targets are the only hard numeric-ish guidance in the COGA
documents reviewed.

---

## Sources

1. W3C Cognitive and Learning Disabilities Accessibility Task Force (COGA),
   "Making Content Usable for People with Cognitive and Learning
   Disabilities" — https://www.w3.org/TR/coga-usable/
2. Center for Health Care Strategies, health literacy and plain-language
   guidance — https://www.chcs.org
3. Miller, "The Magical Number Seven, Plus or Minus Two" (1956) — foundational
   short-term-memory-capacity paper, not aging- or dialogue-specific.
4. Cowan, "The magical number 4 in short-term memory: A reconsideration of
   mental storage capacity" (2001) — revises Miller's estimate downward under
   controlled conditions.
5. "Designing Conversational AI for Aging: A Systematic Review," CHI 2025 —
   https://dl.acm.org/doi/10.1145/3706598.3713578 (full text paywalled;
   findings here are from the abstract and secondary summaries only — flagged
   as not independently verified against the full paper)
6. Morrow, D. G. et al., age-related effects of repetition on memory for
   appointment-style messages, *Human Factors* —
   https://journals.sagepub.com/doi/10.1518/001872099779591268
7. "Situated Understanding of Errors in Older Adults' Interactions with Voice
   Assistants" (month-long in-home study, n=15) —
   https://arxiv.org/abs/2403.02421 (also published as
   https://dl.acm.org/doi/full/10.1145/3796236; full text paywalled, findings
   here from abstract and secondary summaries)
8. "Age-Sensitive Usability in Conversational AI Agents: A Systematic Review,"
   *Innovation in Aging* — https://pmc.ncbi.nlm.nih.gov/articles/PMC12761613/
   (real, peer-reviewed, PRISMA-ScR; note it reviews only 15 studies mostly
   using generic SUS scores rather than AI-specific measures — treat its
   conclusions as thin/aggregated, not primary evidence in their own right)

## What could not be verified

- A numeric, evidence-based limit on choices-per-turn specific to elderly
  users (none exists in the literature reviewed — COGA doesn't give one, and
  the Miller/Cowan numbers are general cognitive-capacity findings, not
  dialogue-design findings).
- A validated reading-level target (e.g. a specific Flesch-Kincaid score) for
  Hindi/Hinglish conversational text — the "10th grade" figure is an imported
  English health-literacy heuristic.
- Direct evidence for "never blame the user" as language, as opposed to "give
  concrete feedback on what went wrong," which is evidenced.
- Full text of the CHI 2025 and arXiv 2403.02421 papers — both were paywalled
  or blocked; conclusions here rest on abstracts and secondary summaries and
  should be re-checked against the full text before being treated as settled.
