"""Score one transcript against one labelled sample.

Pure given a `Transcript`: the audio→transcript step (Sarvam, ffmpeg) happens in
`run.py` and is injected, so scoring is tested without touching either.

Every sample is scored at two stages — `transcript.raw` (straight from Sarvam)
and `transcript.text` (after the entity-correction pass). The gap between the two
is the measured value of correction (PRD §10's `bomlodipin → Amlodipine` claim).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..speech.stt import Transcript
from .corpus import Sample
from .metrics import cer, entity_present, wer


@dataclass
class EntityScore:
    text: str
    type: str
    present_raw: bool
    present_corrected: bool


@dataclass
class SampleScore:
    id: str
    lang: str
    conditions: list[str] = field(default_factory=list)
    wer_raw: float = 0.0
    cer_raw: float = 0.0
    wer_corrected: float = 0.0
    cer_corrected: float = 0.0
    entities: list[EntityScore] = field(default_factory=list)

    @property
    def n_entities(self) -> int:
        return len(self.entities)

    @property
    def entities_kept_raw(self) -> int:
        return sum(1 for e in self.entities if e.present_raw)

    @property
    def entities_kept_corrected(self) -> int:
        return sum(1 for e in self.entities if e.present_corrected)


def score_sample(sample: Sample, transcript: Transcript) -> SampleScore:
    ref = sample.reference
    ent_scores = [
        EntityScore(
            text=e.text,
            type=e.type,
            present_raw=entity_present(e.text, transcript.raw),
            present_corrected=entity_present(e.text, transcript.text),
        )
        for e in sample.entities
    ]
    return SampleScore(
        id=sample.id,
        lang=sample.lang,
        conditions=list(sample.conditions),
        wer_raw=wer(ref, transcript.raw),
        cer_raw=cer(ref, transcript.raw),
        wer_corrected=wer(ref, transcript.text),
        cer_corrected=cer(ref, transcript.text),
        entities=ent_scores,
    )
