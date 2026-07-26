"""Entity correction — R1 is the product risk, so this is scored hard."""
import pytest
from saathi.speech.correct import correct, THRESHOLD

MEDS = ["Amlodipine 5mg", "Telmisartan", "Clopidogrel", "Levothyroxine", "Metformin"]
PEOPLE = ["Dr Mehta", "Priya", "Apollo Nagpur"]


@pytest.mark.parametrize("heard,want", [
    ("Emlodipin ki goli lena", "Amlodipine"),
    ("Telmisartin roz subah", "Telmisartan"),
    ("Clopidogril raat ko", "Clopidogrel"),
    ("Levothyroxin khali pet", "Levothyroxine"),
    ("Metformine ke saath", "Metformin"),
])
def test_mangled_drug_names_repaired(heard, want):
    got = correct(heard, MEDS)
    assert want in got.text, f"{heard!r} -> {got.text!r}"
    assert got.changed


def test_people_and_places_repaired():
    got = correct("Doctor Mehtaa se milna hai Apolo Nagpur mein", MEDS + PEOPLE)
    assert "Mehta" in got.text and "Apollo" in got.text


def test_correct_transcript_left_alone():
    got = correct("Amlodipine ki goli roz subah", MEDS)
    assert not got.changed and got.text == "Amlodipine ki goli roz subah"


def test_unrelated_words_not_dragged_to_entities():
    # "paani" must not become "Priya" just because they share letters.
    got = correct("roz paani peena hai", PEOPLE)
    assert "Priya" not in got.text, got.corrections


def test_no_entities_is_a_noop():
    assert correct("kuch bhi", []).text == "kuch bhi"


def test_hindi_common_words_are_never_corrected():
    got = correct("roz subah goli lena hai", MEDS + PEOPLE)
    assert not got.changed


def test_threshold_is_conservative():
    # Swapping one real drug for another is worse than leaving it wrong.
    assert THRESHOLD >= 0.75
    got = correct("Ramipril lena hai", MEDS)   # a real, different drug
    assert "Ramipril" in got.text, got.corrections
