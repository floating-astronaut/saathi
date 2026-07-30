"""Corpus loader + runner. Builds throwaway corpora in tmp_path; no real audio,
no Sarvam, no ffmpeg — the transcribe/decode steps are injected."""
import json

import pytest

from saathi.eval.corpus import CorpusError, load_corpus
from saathi.eval.run import _aggregate, render_markdown, run
from saathi.eval.score import score_sample
from saathi.speech.stt import Transcript


def _write_sample(d, sid, **overrides):
    manifest = {
        "id": sid,
        "audio": f"{sid}.wav",
        "lang": "hi-IN",
        "reference": "roz subah aath baje Amlong ki goli",
        "entities": [{"text": "Amlong", "type": "medicine"},
                     {"text": "aath", "type": "time"}],
        "conditions": ["elder"],
        "consent": f"consent-{sid}",
    }
    manifest.update(overrides)
    (d / f"{sid}.wav").write_bytes(b"not-real-audio")  # existence is all the loader checks
    (d / f"{sid}.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_empty_corpus_loads_to_nothing_and_makes_no_claim(tmp_path):
    assert load_corpus(tmp_path) == []
    report = _aggregate([])
    assert report.n_samples == 0
    assert report.has_claim is False
    assert report.entity_accuracy_corrected is None
    assert "no accuracy can be claimed" in render_markdown(report)


def test_missing_dir_returns_empty_not_error(tmp_path):
    assert load_corpus(tmp_path / "does-not-exist") == []


def test_loader_reads_and_sorts(tmp_path):
    _write_sample(tmp_path, "hi-002")
    _write_sample(tmp_path, "hi-001")
    samples = load_corpus(tmp_path)
    assert [s.id for s in samples] == ["hi-001", "hi-002"]
    assert samples[0].entities[0].text == "Amlong"


def test_loader_fails_loudly_on_bad_entity_type(tmp_path):
    _write_sample(tmp_path, "hi-001",
                  entities=[{"text": "x", "type": "not-a-type"}])
    with pytest.raises(CorpusError):
        load_corpus(tmp_path)


def test_loader_fails_loudly_on_missing_audio(tmp_path):
    (tmp_path / "hi-001.json").write_text(json.dumps({
        "id": "hi-001", "audio": "gone.wav", "lang": "hi-IN", "reference": "x",
    }), encoding="utf-8")
    with pytest.raises(CorpusError):
        load_corpus(tmp_path)


def test_loader_rejects_duplicate_ids(tmp_path):
    _write_sample(tmp_path, "dup")
    (tmp_path / "dup2.json").write_text(json.dumps({
        "id": "dup", "audio": "dup.wav", "lang": "hi-IN", "reference": "x",
    }), encoding="utf-8")
    with pytest.raises(CorpusError):
        load_corpus(tmp_path)


def test_score_sample_measures_correction_lift(tmp_path):
    _write_sample(tmp_path, "hi-001")
    sample = load_corpus(tmp_path)[0]
    # raw mishears the drug badly; the correction pass restores it
    transcript = Transcript(
        raw="roz subah aath baje Xylong ki goli",
        text="roz subah aath baje Amlong ki goli",
    )
    score = score_sample(sample, transcript)
    amlong = next(e for e in score.entities if e.text == "Amlong")
    assert amlong.present_corrected is True
    assert amlong.present_raw is False          # the measured lift of correction
    assert score.entities_kept_corrected == 2   # Amlong + aath


async def test_run_end_to_end_with_injected_transcriber(tmp_path):
    _write_sample(tmp_path, "hi-001")
    _write_sample(tmp_path, "en-001", lang="en-IN",
                  reference="take Metformin at eight",
                  entities=[{"text": "Metformin", "type": "medicine"}],
                  conditions=["bad_line"])

    async def fake_decode(sample):
        return b"wav"  # never actually decoded

    async def fake_transcribe(wav, entities, lang):
        # perfect hearing -> everything survives
        ref = {"hi-IN": "roz subah aath baje Amlong ki goli",
               "en-IN": "take Metformin at eight"}[lang]
        return Transcript(raw=ref, text=ref)

    report = await run(tmp_path, decode_fn=fake_decode, transcribe_fn=fake_transcribe)
    assert report.n_samples == 2
    assert report.has_claim is True
    assert report.entity_accuracy_corrected == 1.0
    assert report.by_language["en-IN"]["entity_accuracy"] == 1.0
    assert report.by_entity_type["medicine"]["entity_accuracy"] == 1.0
    md = render_markdown(report)
    assert "Entity accuracy" in md and "100.0%" in md
