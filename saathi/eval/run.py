"""Run the STT eval over a corpus and render a report.

    uv run python -m saathi.eval.run --corpus /path/to/corpus --out evals/report

Pipeline per sample:  audio file -> WAV16k (ffmpeg) -> Sarvam -> Transcript ->
score.  The decode and transcribe steps are injectable so the runner is testable
with a fake transcriber (no ffmpeg, no network, no spend).

The honesty gate lives here: an empty corpus yields **no aggregate accuracy
number**. The runner says so and exits 0. A number appears only when real audio
is behind it (see docs/STT_EVAL.md §0).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..speech.audio import ogg_to_wav16k
from ..speech.stt import Transcript, transcribe
from .corpus import Sample, load_corpus
from .score import SampleScore, score_sample

log = logging.getLogger("saathi.eval.run")

DecodeFn = Callable[[Sample], Awaitable[bytes]]
TranscribeFn = Callable[[bytes, list[str], str], Awaitable[Transcript]]


async def default_decode(sample: Sample) -> bytes:
    """Read the sample's audio and return 16 kHz mono WAV bytes."""
    raw = sample.audio.read_bytes()
    if sample.audio.suffix.lower() in (".ogg", ".opus", ".oga"):
        return await ogg_to_wav16k(raw)
    if sample.audio.suffix.lower() == ".wav":
        # Trusted to already be 16k mono per the collection protocol; transcode
        # anyway so a stray sample rate cannot skew a number silently.
        return await ogg_to_wav16k(raw)
    raise ValueError(f"{sample.id}: unsupported audio type {sample.audio.suffix!r}")


async def default_transcribe(wav: bytes, entities: list[str], lang: str) -> Transcript:
    return await transcribe(wav, entities=entities, language=lang)


@dataclass
class Report:
    n_samples: int
    scores: list[SampleScore] = field(default_factory=list)

    # None until there is at least one real sample — never a fabricated 0.0.
    entity_accuracy_raw: float | None = None
    entity_accuracy_corrected: float | None = None
    mean_wer_raw: float | None = None
    mean_wer_corrected: float | None = None
    by_language: dict = field(default_factory=dict)
    by_condition: dict = field(default_factory=dict)
    by_entity_type: dict = field(default_factory=dict)

    @property
    def has_claim(self) -> bool:
        return self.n_samples > 0


def _accuracy(kept: int, total: int) -> float | None:
    return (kept / total) if total else None


def _aggregate(scores: list[SampleScore]) -> Report:
    report = Report(n_samples=len(scores), scores=scores)
    if not scores:
        return report

    total_ent = sum(s.n_entities for s in scores)
    report.entity_accuracy_raw = _accuracy(
        sum(s.entities_kept_raw for s in scores), total_ent)
    report.entity_accuracy_corrected = _accuracy(
        sum(s.entities_kept_corrected for s in scores), total_ent)
    report.mean_wer_raw = sum(s.wer_raw for s in scores) / len(scores)
    report.mean_wer_corrected = sum(s.wer_corrected for s in scores) / len(scores)

    # Slice entity accuracy (corrected) by language and by condition, so we learn
    # *where* accuracy falls, not just that it did.
    lang_kept: dict = defaultdict(lambda: [0, 0])
    for s in scores:
        lang_kept[s.lang][0] += s.entities_kept_corrected
        lang_kept[s.lang][1] += s.n_entities
    report.by_language = {
        lang: {"entity_accuracy": _accuracy(k, t), "entities": t}
        for lang, (k, t) in sorted(lang_kept.items())
    }

    cond_kept: dict = defaultdict(lambda: [0, 0])
    for s in scores:
        for cond in (s.conditions or ["(untagged)"]):
            cond_kept[cond][0] += s.entities_kept_corrected
            cond_kept[cond][1] += s.n_entities
    report.by_condition = {
        cond: {"entity_accuracy": _accuracy(k, t), "entities": t}
        for cond, (k, t) in sorted(cond_kept.items())
    }

    type_kept: dict = defaultdict(lambda: [0, 0, 0])  # kept_corrected, kept_raw, total
    for s in scores:
        for e in s.entities:
            type_kept[e.type][0] += int(e.present_corrected)
            type_kept[e.type][1] += int(e.present_raw)
            type_kept[e.type][2] += 1
    report.by_entity_type = {
        etype: {
            "entity_accuracy": _accuracy(kc, t),
            "entity_accuracy_raw": _accuracy(kr, t),
            "entities": t,
        }
        for etype, (kc, kr, t) in sorted(type_kept.items())
    }
    return report


async def run(
    corpus_dir: str | Path,
    *,
    languages: list[str] | None = None,
    decode_fn: DecodeFn = default_decode,
    transcribe_fn: TranscribeFn = default_transcribe,
) -> Report:
    samples = load_corpus(corpus_dir)
    if languages:
        samples = [s for s in samples if s.lang in languages]

    scores: list[SampleScore] = []
    for s in samples:
        entities = [e.text for e in s.entities]
        wav = await decode_fn(s)
        transcript = await transcribe_fn(wav, entities, s.lang)
        scores.append(score_sample(s, transcript))
        log.info("scored %s (%s): %d/%d entities kept (corrected)",
                 s.id, s.lang, scores[-1].entities_kept_corrected, scores[-1].n_entities)
    return _aggregate(scores)


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def render_markdown(report: Report) -> str:
    if not report.has_claim:
        return (
            "# STT eval — no claim\n\n"
            "**0 real samples in the corpus, so no accuracy can be claimed.**\n\n"
            "This is the honest default state, not a failure. Populate "
            "`evals/corpus/` with real, consented elder voice notes and their hand "
            "transcripts (see `docs/STT_EVAL.md`), then re-run. Until then, "
            "Saathi's real-world STT accuracy is *unmeasured* — do not quote a "
            "number from synthetic audio.\n"
        )
    lines = [
        "# STT eval report",
        "",
        f"Samples: **{report.n_samples}**",
        "",
        "## Entity accuracy (the metric that matters — PRD §15)",
        "",
        f"- Corrected transcript: **{_pct(report.entity_accuracy_corrected)}** (target >95%)",
        f"- Raw transcript (pre-correction): {_pct(report.entity_accuracy_raw)}",
        "",
        "## Diagnostics (WER — do not gate on these)",
        "",
        f"- Mean WER, corrected: {_pct(report.mean_wer_corrected)}",
        f"- Mean WER, raw: {_pct(report.mean_wer_raw)}",
        "",
        "## By language",
        "",
        "| Language | Entity accuracy | Entities |",
        "|---|---|---|",
    ]
    for lang, d in report.by_language.items():
        lines.append(f"| {lang} | {_pct(d['entity_accuracy'])} | {d['entities']} |")
    lines += ["", "## By entity type", "",
              "| Type | Corrected | Raw | Count |", "|---|---|---|---|"]
    for etype, d in report.by_entity_type.items():
        lines.append(f"| {etype} | {_pct(d['entity_accuracy'])} | "
                     f"{_pct(d['entity_accuracy_raw'])} | {d['entities']} |")
    lines += ["", "## By condition", "",
              "| Condition | Entity accuracy | Entities |", "|---|---|---|"]
    for cond, d in report.by_condition.items():
        lines.append(f"| {cond} | {_pct(d['entity_accuracy'])} | {d['entities']} |")
    lines.append("")
    return "\n".join(lines)


def to_dict(report: Report) -> dict:
    return {
        "n_samples": report.n_samples,
        "has_claim": report.has_claim,
        "entity_accuracy_corrected": report.entity_accuracy_corrected,
        "entity_accuracy_raw": report.entity_accuracy_raw,
        "mean_wer_corrected": report.mean_wer_corrected,
        "mean_wer_raw": report.mean_wer_raw,
        "by_language": report.by_language,
        "by_entity_type": report.by_entity_type,
        "by_condition": report.by_condition,
        "samples": [
            {
                "id": s.id, "lang": s.lang, "conditions": s.conditions,
                "wer_corrected": s.wer_corrected, "wer_raw": s.wer_raw,
                "entities_kept_corrected": s.entities_kept_corrected,
                "entities_kept_raw": s.entities_kept_raw,
                "n_entities": s.n_entities,
            }
            for s in report.scores
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the STT eval over a corpus.")
    ap.add_argument("--corpus", default="evals/corpus",
                    help="directory of *.json manifests + audio (default: evals/corpus)")
    ap.add_argument("--out", default=None,
                    help="write report.md and report.json under this dir")
    ap.add_argument("--lang", action="append", default=None,
                    help="restrict to a language (repeatable)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    report = asyncio.run(run(args.corpus, languages=args.lang))
    md = render_markdown(report)
    print(md)

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(md, encoding="utf-8")
        (out / "report.json").write_text(
            json.dumps(to_dict(report), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {out}/report.md and report.json")

    # Exit 0 on an empty corpus: "no claim" is a valid, honest outcome, not an
    # error. A non-empty corpus that scored below target is the caller's to judge.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
