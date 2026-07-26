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
    def __init__(self, name="Kamala"):
        self.sql = []; self.name = name
    async def execute(self, q, params=None):
        self.sql.append(" ".join(q.split()))
        if "select display_name" in q.lower():
            return Cur((self.name,))
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


async def test_welcome_states_what_we_never_do():
    conn, t = Conn(), T()
    await onboarding.begin(conn, t, 1, "91")
    body, btns = t.buttons[0]
    assert "OTP" in body and "paisa" in body
    assert len(btns) <= 3                      # WhatsApp quick-reply limit
    assert all(len(b) <= 20 for b in btns)     # label length limit


async def test_consent_is_recorded_before_anything_is_stored():
    conn, t = Conn(), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:consent:yes", "Kamala")
    sql = " ".join(conn.sql)
    assert "insert into consent_log" in sql and "consent_at = now()" in sql


async def test_declining_leaves_the_door_open():
    conn, t = Conn(), T()
    out = await onboarding.handle_button(conn, t, 1, "91", "ob:consent:no", None)
    assert out == {"onboarding": "declined"}
    assert "start" in t.texts[0].lower()
    assert "onboarding = 'new'" in " ".join(conn.sql)   # can restart later


async def test_reminders_are_opt_in_not_default():
    """Decision D3: unexpected proactive messages erode trust."""
    conn, t = Conn(), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:consent:yes", "Kamala")
    body, btns = t.buttons[-1]
    # after consent we confirm the name; drive on to the reminders question
    await onboarding.handle_button(conn, t, 1, "91", "ob:name:yes", "Kamala")
    body, btns = t.buttons[-1]
    assert "reminder" in body.lower()
    assert any("nahi" in b.lower() for b in btns)      # declining is offered


async def test_training_consent_is_asked_last_and_separately():
    conn, t = Conn(), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:rem:yes", "Kamala")
    body, _ = t.buttons[-1]
    assert "seekh" in body or "learn" in body.lower()
    # and it must promise not to keep names
    assert "naam" in body


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
