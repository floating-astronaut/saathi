# STT evaluation — the corpus, the metric, and the harness

> Owns: how Saathi's speech-to-text accuracy is measured against **reality**, not
> against text-to-speech. The lane is PR-9. Precedence below `PRD.md` §15 (which
> sets the metric) and `LANDMINES.md` (audio traps); this doc is the
> implementation of §15's eval set.

## 0. Why this exists (read before trusting any accuracy number)

Every STT accuracy number Saathi has quoted so far was measured against
**TTS-generated speech** — a machine reading a clean sentence into a clean
microphone. A 70-year-old on a 2G line in Devanagari-speaking India, with a
television on and a grandchild shouting, is a different acoustic universe. TTS
audio is not just *cleaner*; it is *differently distorted*. Optimising against it
can make the real case worse.

So until the corpus below exists and is scored, **the honest statement about
Saathi's real-world STT accuracy is "unmeasured".** This harness exists so that
sentence can be replaced with a number — but only a real number.

**The trap this lane names** (`LANDMINES.md`, "existence is not function"): a
green eval on synthetic audio reads exactly like a green eval on real audio. The
harness therefore refuses to emit an aggregate accuracy figure when the corpus
contains zero real samples — it prints `0 real samples → no accuracy claim` and
exits. A number you can quote only appears when there is real audio behind it.

## 1. The metric: entity accuracy, not WER

From `PRD.md` §15, verbatim: *"Score entity accuracy, not WER. A transcript can
be 92% word-accurate and still have the medicine name wrong — which is the only
error that matters. WER will actively mislead you here."*

- **Primary — entity accuracy.** Of the entities that had to survive
  transcription (medicine names, times, dates, the doctor's name, a place), how
  many did? This is a recall over a hand-labelled set of must-survive tokens, and
  it is the number that maps to whether a reminder fires for the right drug at the
  right time. Target: **>95%** on times/dates/medicine names (PRD §15).
- **Secondary / diagnostic — WER and CER.** Word- and character-error rates are
  computed and reported, but only as diagnostics. They are never the pass/fail
  gate, because a 6% WER that lands entirely on the medicine name is a failure and
  a 30% WER that garbles only filler words is fine.

Entity accuracy is scored the way the pipeline actually resolves entities: the
same normalisation and fuzzy threshold as `saathi/speech/correct.py`
(`SequenceMatcher` ratio ≥ `0.78` over NFKC-folded, punctuation-stripped tokens).
An eval that matched entities more loosely than the product does would report
accuracy the product cannot deliver.

We score entity accuracy at **two stages**, because the lift between them is the
whole thesis of R1:

- on `transcript.raw` — straight from Sarvam, before entity correction;
- on `transcript.text` — after the deterministic correction pass.

The gap between the two is the measured value of the correction pass. PRD §10
claims it turns `bomlodipin → Amlodipine`; this is where that claim gets a number.

## 2. The corpus

Location: `evals/corpus/`. It starts **empty on purpose** — the repo ships the
harness and the protocol, not fabricated audio.

### 2.1 What a good corpus is (PRD §15)

- **50–100 real voice notes per language.** Languages we serve first: `hi-IN`
  (Hindi, code-mixed), `en-IN` (Indian English). Add `hi-en` (heavily romanised
  code-mix) as its own bucket — it is how most users actually talk.
- **Real elder speakers**, not staff reading a script. The target user is 40+,
  often 60+, frequently not tech-fluent.
- **Deliberately include the messy ones.** Background television, a grandchild
  shouting, a bad line, a fan, a mid-sentence restart, a cough. If the corpus is
  all clean audio it is a second TTS set with extra steps.
- **Cover the entities that matter:** real medicine names (Indian brands —
  Amlodipine as *Amlong*, Metformin as *Glycomet*, etc.), times ("subah aath
  baje"), dates, doctor and family names, place names.

### 2.2 Consent and DPDP — non-negotiable

These are recordings of real people's voices, which is personal data, and elder
health-adjacent speech at that. Under DPDP (see `foundations/`):

- Each speaker gives **free, specific, informed consent** to their voice being
  stored and used for evaluating the product's accuracy. This is a *different
  purpose* from providing the service — do not reuse production voice notes or
  onboarding consent to populate the eval set. Collect it explicitly.
- Record consent per sample (`consent` field in the manifest — a reference to the
  signed/recorded consent, not the consent text itself).
- The corpus is **not** committed to git. `evals/corpus/` is git-ignored except
  for its README and schema. Real audio and real transcripts of real elders do
  not belong in a public-ish repo. Store the corpus out of band (the audio S3
  bucket or an access-controlled location) and point the harness at it with
  `--corpus`.
- A speaker withdrawing consent means deleting their samples — mirror the erasure
  discipline in `migration 004` (training corpus): cascade, leave nothing behind.

### 2.3 Manifest format

One JSON file per sample in the corpus directory (audio alongside it, or an
absolute/relative path in the manifest). Schema (also in
`evals/corpus/SCHEMA.md`):

```json
{
  "id": "hi-001",
  "audio": "hi-001.ogg",
  "lang": "hi-IN",
  "reference": "Roz subah aath baje Amlong ki goli aur raat ko Glycomet",
  "entities": [
    {"text": "Amlong",   "type": "medicine"},
    {"text": "Glycomet", "type": "medicine"},
    {"text": "aath baje", "type": "time"}
  ],
  "conditions": ["tv_background", "elder", "code_mixed"],
  "consent": "consent-ref-2026-07-30-hi-001",
  "notes": "speaker restarts once mid-sentence"
}
```

- `reference` is the hand transcript in the **same script the STT mode emits**
  (`indic-en` → Latin), so it is comparable to `transcript.raw`/`.text`. This is a
  measured decision, not cosmetic — see `saathi/speech/stt.py`.
- `entities[].type` is one of `medicine | time | date | person | place | number`.
  Accuracy is reported per-type as well as overall, because a 3% miss on filler is
  not a 3% miss on a drug name.
- `conditions[]` are free-form tags used to slice results (clean vs `tv_background`
  vs `bad_line`), so we can see *where* accuracy falls, not just that it did.

## 3. The harness

Code lives in `saathi/eval/` (importable, unit-tested) with data and reports
under `evals/`.

- `saathi/eval/metrics.py` — pure scoring: `wer`, `cer`, and `entity_present`
  (the §1 fuzzy match, reusing `speech.correct`'s normalisation and threshold).
  No I/O, no audio, no network — this is the part unit tests pin.
- `saathi/eval/corpus.py` — `Sample`/`Entity` dataclasses and `load_corpus()`,
  which validates every manifest and **fails loudly** on a malformed one rather
  than silently skipping it (a skipped sample is a quietly smaller, quietly
  easier eval).
- `saathi/eval/score.py` — `score_sample()`: given a reference, its entities, and
  a produced `Transcript`, compute per-stage entity accuracy + WER/CER. Pure given
  the transcript, so it is tested without touching Sarvam.
- `saathi/eval/run.py` — the runner and CLI: decode each sample's audio
  (`speech.audio.ogg_to_wav16k`), transcribe it (`speech.stt.transcribe`), score
  it, aggregate overall / per-language / per-condition / per-entity-type, and
  render a Markdown + JSON report. The transcribe and decode steps are injectable
  so the runner itself is testable with a fake transcriber.

### 3.1 Running it

```bash
# Against a real corpus (audio + manifests), out of band from git:
uv run python -m saathi.eval.run --corpus /path/to/corpus --out evals/report

# Empty corpus (the default state) — proves the harness runs and refuses to
# invent a number:
uv run python -m saathi.eval.run --corpus evals/corpus
```

Real runs hit Sarvam and therefore cost money and require `SARVAM_API_KEY`. The
runner counts characters/audio-seconds sent so a corpus run's STT spend is
knowable up front — the same cost-bounded property D-S relies on for STT.

## 4. What is done and what remains

- **Done (this lane):** the metric is pinned to entity accuracy; the manifest
  schema, collection protocol, and consent rules are written; the loader, scorer,
  and runner exist and are unit-tested; the runner refuses to emit an aggregate on
  an empty corpus.
- **Remains (a data task, tracked as PR-9's open tail):** collect 50–100 real
  elder voice notes per language under consent, hand-transcribe them, and run the
  harness to produce the first *real* entity-accuracy number. Only then can the
  PRD §15 target (>95%) be claimed or refuted, and only then does the correction
  pass's real-world lift stop being a guess. Do this before the first
  model-version decision (PRD §15: "build it in week 2").
