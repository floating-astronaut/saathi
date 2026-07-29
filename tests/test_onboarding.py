"""Onboarding must never call the model — that is what makes 'open' safe."""
import inspect
import pytest
from saathi import onboarding


class Cur:
    rowcount = 1
    def __init__(self, row=None): self._row = row
    async def fetchone(self): return self._row
    async def fetchall(self): return []


class Conn:
    def __init__(self, name="Kamala", lang="hi"):
        self.sql = []; self.name = name; self.lang = lang
    async def execute(self, q, params=None):
        self.sql.append(" ".join(q.split()))
        low = q.lower()
        if "select display_name" in low:
            return Cur((self.name,))
        if "select lang_pref" in low:
            return Cur((self.lang,))
        return Cur(None)


class T:
    """Transport spy."""
    channel = "whatsapp"
    def __init__(self): self.texts = []; self.buttons = []
    async def send_text(self, conn, uid, handle, text):
        self.texts.append(text); return "m"
    async def send_buttons(self, conn, uid, handle, body, buttons):
        self.buttons.append((body, [label for _, label in buttons])); return "m"


def test_no_model_import_anywhere_in_onboarding():
    """The safety property in one assertion: if onboarding could reach the agent
    loop, an unknown sender could burn tokens before consenting."""
    src = inspect.getsource(onboarding)
    for forbidden in ("agent", "bedrock", "loop.run", "converse"):
        assert forbidden not in src, f"onboarding references {forbidden!r}"


async def test_first_message_asks_the_language_and_nothing_else():
    """One bilingual message, then never repeat yourself. A wall of text is the
    interface complexity PRD §2 names as the barrier."""
    conn, t = Conn(), T()
    out = await onboarding.begin(conn, t, 1, "91")
    body, btns = t.buttons[0]
    assert out == {"onboarding": "new"}        # language is not consent
    # Three scripts, which is also WhatsApp's hard limit of three buttons.
    assert btns == ["हिंदी", "Hinglish", "English"]
    assert "consent" not in " ".join(conn.sql)


async def test_welcome_states_what_we_never_do():
    conn, t = Conn(), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:lang:hi", None)
    body, btns = t.buttons[0]
    # The two promises that matter most, now in Devanagari. "OTP" stays Latin
    # on purpose — it is what the scam callers themselves say.
    assert "OTP" in body and "पैसे" in body
    assert len(btns) <= 3                      # WhatsApp quick-reply limit
    assert all(len(b) <= 20 for b in btns)     # label length limit


async def test_english_welcome_is_english_only():
    """The point of the language step: no Hindi tail on an English welcome."""
    conn, t = Conn(lang="en"), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:lang:en", None)
    body, _ = t.buttons[0]
    assert "OTP" in body
    for hindi in ("Namaste", "maangti", "hoon"):
        assert hindi not in body, f"English welcome still carries {hindi!r}"


async def test_language_choice_is_stored():
    conn, t = Conn(), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:lang:en", None)
    assert "update users set lang_pref" in " ".join(conn.sql)


async def test_consent_is_recorded_before_anything_is_stored():
    conn, t = Conn(), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:consent:yes", "Kamala")
    sql = " ".join(conn.sql)
    assert "insert into consent_log" in sql and "consent_at = now()" in sql


async def test_declining_leaves_the_door_open():
    conn, t = Conn(), T()
    out = await onboarding.handle_button(conn, t, 1, "91", "ob:consent:no", None)
    assert out == {"onboarding": "declined"}
    # The restart phrase must actually restart. In Hindi it said "shuru karein",
    # which matched no command until 2026-07-27 — a dead end for exactly the
    # users this product is for, hidden while the copy was bilingual. It broke
    # a second time on 2026-07-27 when the copy became Devanagari and the parser
    # was still Latin-only, so this now reads the phrase out of whatever the
    # copy actually says rather than hard-coding one script.
    import re

    from saathi import commands
    said = t.texts[0]
    quoted = re.findall(r"['\"“”‘’]([^'\"“”‘’]{2,30})['\"“”‘’]", said)
    assert quoted, f"the declined message quotes no phrase to type: {said!r}"
    for phrase in quoted:
        assert commands.parse(phrase).command is not None, (
            f"declined message tells the user to type {phrase!r}, which does nothing")
    assert "onboarding = 'new'" in " ".join(conn.sql)   # can restart later


async def test_reminders_are_opt_in_not_default():
    """Decision D3: unexpected proactive messages erode trust."""
    conn, t = Conn(), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:consent:yes", "Kamala")
    body, btns = t.buttons[-1]
    # after consent we confirm the name; drive on to the reminders question
    await onboarding.handle_button(conn, t, 1, "91", "ob:name:yes", "Kamala")
    body, btns = t.buttons[-1]
    # The contract is that declining is offered, not that the copy contains an
    # English word — the Hindi asks "kya main aapko cheezein yaad dilaaun".
    assert any(w in body.lower() for w in ("याद", "yaad", "remind"))
    assert len(btns) == 2, "opt-in needs a real choice, not one button"
    assert any(x in " ".join(btns).lower() for x in ("नहीं", "nahi", "not now"))


async def test_reminders_are_opt_in_in_english_too():
    """The same guarantee must survive the translation."""
    conn, t = Conn(lang="en"), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:rem:no", "Kamala")
    assert "paused = true" in " ".join(conn.sql).lower().replace("%s", "true")  \
        or "set paused" in " ".join(conn.sql).lower()


async def test_training_consent_is_asked_last_and_separately():
    conn, t = Conn(), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:rem:yes", "Kamala")
    body, _ = t.buttons[-1]
    assert "सीख" in body or "learn" in body.lower()
    # and it must promise not to keep names
    assert "नाम" in body


async def test_typing_instead_of_tapping_reoffers_the_buttons():
    """Never guess at consent."""
    conn, t = Conn(), T()
    out = await onboarding.handle_text(conn, t, 1, "91", "consent", "haan theek hai")
    assert out == {"onboarding": "consent"}
    assert t.buttons                                    # re-offered, not inferred


async def test_name_step_accepts_free_text():
    conn, t = Conn(), T()
    out = await onboarding.handle_text(conn, t, 1, "91", "name", "  Kamala Devi  ")
    assert out == {"onboarding": "reminders"}
    assert "display_name = %s" in " ".join(conn.sql)


async def test_unrelated_button_is_not_claimed():
    conn, t = Conn(), T()
    assert await onboarding.handle_button(conn, t, 1, "91", "ack:42", None) is None


async def test_finishing_onboarding_queues_the_versioned_free_key(monkeypatch):
    calls = []

    async def fake_account(conn, user_id):
        return 6

    async def fake_enqueue(conn, user_id, kind, when, payload=None, dedupe_key=None):
        calls.append((user_id, kind, payload, dedupe_key))
        return 42

    monkeypatch.setattr("saathi.accounts.ensure_for_user", fake_account)
    monkeypatch.setattr("saathi.scheduling.enqueue", fake_enqueue)
    await onboarding._grant_free_allowance(Conn(), user_id=12)

    assert calls == [(12, "provision_key", {"account_id": 6}, "provision:v2:6")]
