"""Health-adjacent readings must carry their disclaimer by construction."""
import pytest
from saathi import vision, documents


def test_medicine_reading_cannot_lose_its_disclaimer():
    """The disclaimer is attached to the value, not added by a caller who might
    forget. PRD §12: naming what is printed is information; dose is advice."""
    r = vision.Reading("Amlodipine 5mg", vision.MEDICINE_DISCLAIMER, "medicine")
    out = r.rendered()
    assert "Amlodipine 5mg" in out
    assert "salah nahi" in out and "doctor" in out.lower()


def test_disclaimers_are_bilingual_and_actionable():
    for d in (vision.MEDICINE_DISCLAIMER, vision.MONEY_DISCLAIMER):
        assert any(w in d for w in ("doctor", "chemist", "bank"))
        assert "_" in d          # English half present


def test_money_disclaimer_names_the_actual_scam_pattern():
    d = vision.MONEY_DISCLAIMER
    assert "OTP" in d and "PIN" in d
    assert "bank" in d.lower()


@pytest.mark.parametrize("caption,kind", [
    ("yeh dawa kya hai", "medicine"),
    ("is tablet ka naam batao", "medicine"),
    ("what medicine is this", "medicine"),
    ("ismein kya likha hai", "document"),
    ("please read this bill", "document"),
    ("ye photo dekho", "image"),
    (None, "image"),
])
def test_intent_from_caption(caption, kind):
    assert vision.classify_intent(caption) == kind


def test_vision_model_is_regional_so_photos_stay_in_india():
    """A photograph of someone's prescription must not leave the country. The
    Anthropic vision models here are global-only; this one is regional."""
    assert not vision.VISION_MODEL.startswith("global.")
    assert vision.VISION_MODEL == "qwen.qwen3-vl-235b-a22b"


def test_image_size_is_bounded():
    assert vision.MAX_IMAGE_BYTES <= 8 * 1024 * 1024


def test_pdf_reading_is_page_bounded():
    """An unbounded document is an unbounded bill, and an elder wants the gist."""
    assert documents.MAX_PAGES <= 5


def test_text_layer_detection_threshold():
    assert not documents.has_text_layer("")
    assert not documents.has_text_layer("scan")
    assert documents.has_text_layer("x" * documents.TEXT_LAYER_MIN)


async def test_malformed_pdf_returns_empty_not_an_exception():
    """A corrupt forward must not 500 the reply.

    Async since PR-26: the pypdf pass runs in a bounded thread pool with a wall
    clock rather than on the event loop.
    """
    assert await documents.extract_text(b"this is not a pdf") == ""
