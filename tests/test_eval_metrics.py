"""Metrics are the provable core of the STT eval — pin them hard."""
from saathi.eval.metrics import cer, entity_present, wer


def test_wer_counts_word_substitutions():
    # one of three reference words wrong -> 1/3
    assert wer("a b c", "a x c") == 1 / 3


def test_wer_perfect_and_empty():
    assert wer("roz subah goli", "roz subah goli") == 0.0
    assert wer("", "") == 0.0
    # model invented words against an empty reference -> full error, not div/0
    assert wer("", "hello") == 1.0


def test_cer_is_character_level():
    # "goli" vs "gol" = one deletion over four chars
    assert cer("goli", "gol") == 0.25


def test_entity_present_exact_and_fuzzy():
    # exact survival
    assert entity_present("Amlong", "roz subah Amlong ki goli")
    # near-miss within the pipeline's 0.78 threshold still counts as present,
    # because the correction pass would resolve it
    assert entity_present("Amlodipine", "subah Amlodipin ki goli")


def test_entity_absent_when_mangled_past_threshold():
    assert not entity_present("Glycomet", "raat ko koi aur dawa")


def test_multiword_entity_needs_every_significant_word():
    assert entity_present("Dr Mehta", "kal Dr Mehta se milna hai")
    # surname dropped -> not present
    assert not entity_present("Dr Mehta", "kal Dr se milna hai")


def test_numeric_entity_must_match_exactly():
    # a wrong number is a wrong time; fuzzy string similarity must not wave it in
    assert entity_present("8", "subah 8 baje")
    assert not entity_present("8", "subah 9 baje")
