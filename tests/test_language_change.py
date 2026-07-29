"""The language must be changeable after onboarding.

It was asked once, stored, and had no way back — no command, and nothing in the
copy said it was changeable. The person most likely to mistap the first button
is exactly the elder this product is for (PR-32).
"""
from saathi import commands, pipeline
from saathi import onboarding


class Cur:
    def __init__(self, rows=None): self._rows = rows or []
    async def fetchone(self): return self._rows[0] if self._rows else None
    async def fetchall(self): return self._rows


class Conn:
    def __init__(self, lang="hi", onboard="done"):
        self.sql = []; self.lang = lang; self.onboard = onboard
    async def execute(self, q, params=None):
        low = " ".join(q.split()); self.sql.append(low)
        if "select lang_pref" in low.lower(): return Cur([(self.lang,)])
        if "select onboarding" in low.lower(): return Cur([(self.onboard,)])
        if "select display_name" in low.lower(): return Cur([("Kamala",)])
        return Cur()
    def wrote(self, n): return any(n in s for s in self.sql)


class T:
    channel = "whatsapp"
    def __init__(self): self.texts = []; self.buttons = []
    async def send_text(self, conn, uid, handle, text): self.texts.append(text); return "m"
    async def send_buttons(self, conn, uid, handle, body, buttons):
        self.buttons.append((body, [l for _, l in buttons])); return "m"


# --- the request is recognised -----------------------------------------------

def test_language_requests_are_recognised():
    for s in ("/language", "language", "bhasha", "bhasha badlo",
              "english mein baat karo", "switch to hindi"):
        assert commands.parse(s).command is commands.Command.LANGUAGE, s


def test_a_statement_about_someone_else_does_not_switch_language():
    """A bare "english mein baat kar" substring would match "mera beta english
    mein baat karta hai" — a fact about a son, not a request. PR-23 showed what
    substring matching costs."""
    for s in ("mera beta english mein baat karta hai",
              "meri bahu hindi mein baat karti hai",
              "doctor english mein baat karte hain"):
        assert commands.parse(s).command is None, s


# --- it re-offers the same choice --------------------------------------------

async def test_the_command_re_offers_both_languages():
    conn, t = Conn(), T()
    out = await pipeline._run_command(conn, t, 1, "91", commands.Command.LANGUAGE)
    assert out == {}
    body, btns = t.buttons[0]
    assert btns == ["हिंदी", "Hinglish", "English"]


# --- and changing it does not un-onboard you ---------------------------------

async def test_changing_language_when_done_does_not_restart_onboarding():
    """`_welcome` sets onboarding='consent'. Reusing it here would silently send
    someone back through consent because they wanted English."""
    conn, t = Conn(lang="hi", onboard="done"), T()
    out = await onboarding.handle_button(conn, t, 1, "91", "ob:lang:en", None)
    assert out["onboarding"] == "done"
    assert conn.wrote("update users set lang_pref")
    assert not conn.wrote("onboarding = 'consent'"), "changing language un-onboarded the user"
    assert t.texts, "no confirmation sent"


async def test_a_new_user_still_goes_through_consent():
    """The guard must not skip onboarding for someone who has not consented."""
    conn, t = Conn(lang="hi", onboard="new"), T()
    out = await onboarding.handle_button(conn, t, 1, "91", "ob:lang:en", None)
    assert out["onboarding"] == "consent"


# --- replies speak one language ----------------------------------------------

async def test_command_replies_are_not_bilingual():
    """Onboarding stopped saying everything twice; the commands still did."""
    conn, t = Conn(lang="en"), T()
    await pipeline._run_command(conn, t, 1, "91", commands.Command.STOP)
    said = t.texts[0]
    for hindi in ("Theek hai", "bhejungi", "chalu karo"):
        assert hindi not in said, f"English reply still carries {hindi!r}"
