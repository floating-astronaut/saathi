"""Load and validate the STT eval corpus.

A sample is one hand-labelled real voice note: the audio, a hand transcript, and
the entities that had to survive it. Manifests are JSON, one per sample; the
schema is in `docs/STT_EVAL.md` §2.3 and `evals/corpus/SCHEMA.md`.

The loader **fails loudly** on a malformed manifest rather than skipping it. A
silently skipped sample is a quietly smaller, quietly easier eval — the exact
kind of dishonesty this whole lane exists to prevent.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("saathi.eval.corpus")

ENTITY_TYPES = {"medicine", "time", "date", "person", "place", "number"}


class CorpusError(ValueError):
    """A manifest is malformed. Raised, never swallowed."""


@dataclass(frozen=True)
class Entity:
    text: str
    type: str


@dataclass
class Sample:
    id: str
    audio: Path            # resolved path to the audio file
    lang: str
    reference: str         # hand transcript, in the script the STT mode emits
    entities: list[Entity] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    consent: str | None = None
    notes: str | None = None
    manifest: Path | None = None


def _require(obj: dict, key: str, where: str) -> object:
    if key not in obj or obj[key] in (None, ""):
        raise CorpusError(f"{where}: missing required field {key!r}")
    return obj[key]


def _parse_manifest(path: Path) -> Sample:
    where = str(path)
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CorpusError(f"{where}: invalid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise CorpusError(f"{where}: manifest must be a JSON object")

    sid = str(_require(obj, "id", where))
    audio_name = str(_require(obj, "audio", where))
    audio = (path.parent / audio_name).resolve()
    if not audio.exists():
        raise CorpusError(f"{where}: audio file not found: {audio}")

    lang = str(_require(obj, "lang", where))
    reference = str(_require(obj, "reference", where))

    entities: list[Entity] = []
    for i, ent in enumerate(obj.get("entities", [])):
        if not isinstance(ent, dict) or "text" not in ent or "type" not in ent:
            raise CorpusError(f"{where}: entities[{i}] needs 'text' and 'type'")
        etype = str(ent["type"])
        if etype not in ENTITY_TYPES:
            raise CorpusError(
                f"{where}: entities[{i}] type {etype!r} not in {sorted(ENTITY_TYPES)}")
        entities.append(Entity(text=str(ent["text"]), type=etype))

    consent = obj.get("consent")
    if not consent:
        # Not a hard failure at load time (the file may predate the rule), but
        # loud: real elder audio without a consent reference must not sit
        # unnoticed in the corpus. See docs/STT_EVAL.md §2.2 (DPDP).
        log.warning("sample %s (%s) has no consent reference", sid, where)

    return Sample(
        id=sid,
        audio=audio,
        lang=lang,
        reference=reference,
        entities=entities,
        conditions=[str(c) for c in obj.get("conditions", [])],
        consent=str(consent) if consent else None,
        notes=str(obj["notes"]) if obj.get("notes") else None,
        manifest=path,
    )


def load_corpus(corpus_dir: str | Path) -> list[Sample]:
    """Load every `*.json` manifest under `corpus_dir`, sorted by id.

    A missing or empty directory returns an empty list — that is the shipped,
    honest default state, not an error. The runner turns an empty list into a
    "no accuracy claim" report.
    """
    root = Path(corpus_dir)
    if not root.exists():
        log.warning("corpus dir does not exist: %s", root)
        return []
    samples = [_parse_manifest(p) for p in sorted(root.glob("*.json"))]
    ids = [s.id for s in samples]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise CorpusError(f"duplicate sample ids in {root}: {sorted(dupes)}")
    return samples
