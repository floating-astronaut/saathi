"""Someone who chose हिंदी must be answered in हिंदी.

The onboarding button has always said **"हिंदी"**, in Devanagari — and every
message after it arrived romanised: "Namaste! Main Indofolk AI hoon". A promise
broken in the first interaction, and for this audience an expensive one.
Romanised Hindi is an SMS-era convention that assumes the reader learned to type
before they learned to read; a 70-year-old in Nagpur very often reads Devanagari
fluently and finds "kehkar bulaaun" harder than "कहकर बुलाऊँ".

Two halves, and the second is the one that used to be wrong:

* the **deterministic copy** — onboarding, buttons, acks, commands, the paywall,
  the safety replies — which is just text in this repo, and
* the **model's output**, which followed a prompt rule saying "reply in the
  user's language and script". That made it mirror whatever it was sent, and
  since an elder with an English keyboard types "dawai" rather than "दवाई", it
  mirrored Latin back forever. Reading and typing are different skills. The
  script is now a stored choice, stated to the model every turn.
"""
import re

import pytest

from saathi import capabilities, onboarding, pipeline
from saathi.agent.prompt import SCRIPT_RULE, build_prefix, estimate_tokens, script_line
from saathi.safety.classifier import _REPLIES

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
#: Latin letters that would betray romanised Hindi. Brand names, medicine names
#: and helpline URLs are deliberately allowed to stay Latin.
ALLOWED_LATIN = re.compile(
    r"Indofolk AI|Dr Sharma|voice note|OTP|PIN|CBI|WhatsApp|Tele-MANAS|"
    r"https?://\S+|[A-Za-z]{1,3}\b")


def _romanised_words(text: str) -> list[str]:
    """Latin words left over once the allowed exceptions are removed."""
    return re.findall(r"[A-Za-z]{4,}", ALLOWED_LATIN.sub(" ", text))


# --- the model is told, not left to guess ------------------------------------

def test_hindi_users_are_told_to_write_devanagari():
    assert "Devanagari" in script_line("hi")
    assert DEVANAGARI.search(script_line("hi")), "say it in the script itself"


def test_the_legacy_hinglish_preference_still_gets_latin():
    """`hi-en` predates the language step. Those accounts keep what they had."""
    assert "romanised" in script_line("hi-en").lower()
    assert "Devanagari" not in script_line("hi-en").replace("not Devanagari", "")


def test_english_users_are_unaffected():
    assert script_line("en") == SCRIPT_RULE["en"] + "\n"


def test_an_unknown_language_falls_back_to_devanagari_not_english():
    """The product is for older adults in India; `DEFAULT_LANG` is already `hi`."""
    # gu/ml are real languages now (LANG-2); ta/kn are still unsupported.
    for unknown in (None, "", "ta", "kn"):
        assert "Devanagari" in script_line(unknown)


def test_the_rule_reaches_the_prefix():
    """Assert the whole rule, not the word "Devanagari".

    The first version of this test checked `"Devanagari" in p.system` and passed
    with `script_line` deleted from `build_prefix` entirely — because SYSTEM's
    own explanation of the rule contains the word. Green for the wrong reason,
    caught by deleting the call and finding the suite still passed.
    """
    hi = build_prefix([], 500, 3000, lang="hi")
    assert script_line("hi").strip() in hi.system


def test_each_script_produces_a_different_prefix():
    """The strongest form: the three choices cannot collapse into one."""
    systems = {lang: build_prefix([], 500, 3000, lang=lang).system
               for lang in ("hi", "hi-en", "en")}
    assert len(set(systems.values())) == 3, "two scripts produced the same prompt"
    assert script_line("hi-en").strip() in systems["hi-en"]
    assert script_line("en").strip() in systems["en"]


def test_the_prompt_no_longer_tells_the_model_to_mirror_the_user():
    """The old rule is why everyone got Hinglish regardless of their choice."""
    p = build_prefix([], 500, 3000, lang="hi")
    assert "If they write Hinglish, reply in simple Hinglish" not in p.system


# --- the deterministic copy --------------------------------------------------

@pytest.mark.parametrize("key", sorted(onboarding.COPY["hi"]))
def test_every_onboarding_string_is_devanagari(key):
    text = onboarding.COPY["hi"][key]
    assert DEVANAGARI.search(text), f"{key} has no Devanagari at all"
    assert not _romanised_words(text), f"{key} still romanised: {_romanised_words(text)}"


@pytest.mark.parametrize("key", sorted(onboarding.BTN["hi"]))
def test_every_hindi_button_is_devanagari(key):
    assert DEVANAGARI.search(onboarding.BTN["hi"][key])


@pytest.mark.parametrize("key", sorted(onboarding.BTN["hi"]))
def test_hindi_buttons_fit_whatsapp_s_twenty_character_limit(key):
    """§11. Devanagari counts by character, and Meta rejects the whole message.

    A label that fits in Latin does not automatically fit once translated.
    """
    assert len(onboarding.BTN["hi"][key]) <= 20


def test_the_ack_and_snooze_replies_are_devanagari():
    assert DEVANAGARI.search(pipeline.ACK_REPLY["hi"])
    assert DEVANAGARI.search(pipeline.SNOOZE_REPLY["hi"])
    assert "{mins}" in pipeline.SNOOZE_REPLY["hi"], "the placeholder was translated away"


@pytest.mark.parametrize("key", sorted(pipeline.CMD_COPY["hi"]))
def test_every_command_reply_is_devanagari(key):
    assert DEVANAGARI.search(pipeline.CMD_COPY["hi"][key])


def test_the_paywall_speaks_devanagari():
    assert DEVANAGARI.search(capabilities.PAYWALL_COPY["hi"])


# --- safety copy: bilingual by design, and she is female ---------------------

@pytest.mark.parametrize("trigger", sorted(_REPLIES, key=str))
def test_safety_replies_keep_both_languages(trigger):
    """Deliberately bilingual. In an emergency, whoever is nearby may read either."""
    text = _REPLIES[trigger]
    assert DEVANAGARI.search(text), "the Hindi half is missing"
    assert re.search(r"[A-Za-z]{4,}", text), "the English half is missing"


@pytest.mark.parametrize("trigger", sorted(_REPLIES, key=str))
def test_saathi_never_refers_to_herself_as_male(trigger):
    """SYSTEM says she is female and to never switch forms.

    The safety replies said "sun raha hoon" and "sakta hoon" — masculine — in the
    most sensitive copy in the product: self-harm and medical advice.
    """
    for masculine in ("रहा हूँ", "सकता हूँ", "करता हूँ", "raha hoon", "sakta hoon"):
        assert masculine not in _REPLIES[trigger], f"masculine form: {masculine}"


# --- what it costs -----------------------------------------------------------

def test_the_script_rule_is_a_cheap_line():
    """There is no prompt caching, so every prefix line is paid ~300x/user/month."""
    assert estimate_tokens(script_line("hi")) < 25


def test_a_hindi_prefix_still_fits_the_budget():
    facts = [("doctor", "Dr Mehta, Apollo"), ("medicine", "Amlodipine 5mg"),
             ("daughter", "Priya, Pune"), ("city", "Nagpur")]
    assert build_prefix(facts, 600, 3000, lang="hi").tokens < 3000


# --- the commands must work in the script we taught people to type -----------

@pytest.mark.parametrize("phrase,expected", [
    # Every one of these is a phrase our own copy tells a Hindi reader to type.
    ("शुरू करें", "start"),
    ("नमस्ते", "start"),
    ("चालू करो", "resume"),
    ("सब कुछ भूल जाओ", "delete_all"),
    ("बंद करो", "stop"),
    ("मदद", "help"),
    ("भाषा", "language"),
    ("चैट साफ करो", "clear_chat"),
    ("मेरे बारे में क्या याद है", "what_you_know"),
])
def test_devanagari_commands_are_understood(phrase, expected):
    """The privacy policy promises erasure on request.

    Until 2026-07-27 the parser was Latin-only, so "सब कुछ भूल जाओ" — the exact
    words the consent screen tells a Hindi reader to use — matched nothing. A
    promise kept only in Latin is not kept.
    """
    from saathi import commands
    got = commands.parse(phrase).command
    assert got is not None, f"{phrase!r} matched no command"
    assert got.value == expected


@pytest.mark.parametrize("phrase,expected", [
    ("shuru karein", "start"),
    ("chalu karo", "resume"),          # never matched before 2026-07-27
    ("sab kuch bhool jao", "delete_all"),
    ("stop", "stop"),
])
def test_latin_commands_still_work(phrase, expected):
    """Voice notes arrive in Latin — Sarvam runs in `indic-en` mode."""
    from saathi import commands
    got = commands.parse(phrase).command
    assert got is not None and got.value == expected


def test_the_resume_phrase_our_copy_advertises_actually_resumes():
    """`\\bchalu kar\\b` never matched "chalu karo": \\b needs a non-word char
    after "kar", and "o" is one. The stop message told people to type exactly
    that, so RESUME was unreachable by its own advertised words."""
    from saathi import commands
    from saathi.pipeline import CMD_COPY
    for lang in ("hi", "hi-en"):
        stopped = CMD_COPY[lang]["stopped"]
        quoted = re.findall(r"['\"“”‘’]([^'\"“”‘’]{2,30})['\"“”‘’]", stopped)
        assert quoted, f"{lang} stop message quotes no phrase"
        for phrase in quoted:
            assert commands.parse(phrase).command is not None, \
                f"{lang} tells the user to type {phrase!r}, which does nothing"
