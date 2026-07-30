"""LANG-2: Gujarati + Malayalam as full languages, and the list-based picker."""
from saathi import onboarding
from saathi.agent.prompt import SCRIPT_RULE
from saathi.core.context import MessageContext
from saathi.speech import sarvam_lang
from saathi.wa import client as wa


class Cur:
    rowcount = 1
    def __init__(self, row=None): self._row = row
    async def fetchone(self): return self._row
    async def fetchall(self): return []


class Conn:
    def __init__(self, name="Meera", lang="gu"):
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
    channel = "whatsapp"
    def __init__(self): self.texts = []; self.buttons = []; self.lists = []
    async def send_text(self, conn, uid, handle, text): self.texts.append(text); return "m"
    async def send_buttons(self, conn, uid, handle, body, buttons):
        self.buttons.append((body, buttons)); return "m"
    async def send_list(self, conn, uid, handle, body, button, rows):
        self.lists.append((body, rows)); return "m"


# --- language -> Sarvam code -----------------------------------------------

def test_sarvam_lang_maps_all_languages():
    assert sarvam_lang("hi") == "hi-IN"
    assert sarvam_lang("hi-en") == "hi-IN"      # romanised Hindi is still Hindi audio
    assert sarvam_lang("en") == "en-IN"
    assert sarvam_lang("gu") == "gu-IN"
    assert sarvam_lang("ml") == "ml-IN"
    assert sarvam_lang(None) == "hi-IN"         # default, never crashes


def test_script_rule_covers_new_languages():
    assert "ગુજરાતી" in SCRIPT_RULE["gu"]
    assert "മലയാളം" in SCRIPT_RULE["ml"]


# --- onboarding picker + selection -----------------------------------------

async def test_picker_offers_five_languages_as_a_list():
    conn, t = Conn(), T()
    await onboarding.begin(conn, t, 1, "91")
    assert not t.buttons                        # not the 3-button picker anymore
    _body, rows = t.lists[0]
    ids = [rid for rid, _ in rows]
    assert ids == ["ob:lang:hi", "ob:lang:hi-en", "ob:lang:en",
                   "ob:lang:gu", "ob:lang:ml"]


async def test_gujarati_selection_stores_and_welcomes_in_gujarati():
    conn, t = Conn(lang="gu"), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:lang:gu", None)
    assert "update users set lang_pref" in " ".join(conn.sql)
    body = t.buttons[0][0]                       # welcome, in the chosen language
    assert "OTP" in body and "પૈસા" in body      # the never-do promise, in Gujarati


async def test_malayalam_selection_welcomes_in_malayalam():
    conn, t = Conn(lang="ml"), T()
    await onboarding.handle_button(conn, t, 1, "91", "ob:lang:ml", None)
    body = t.buttons[0][0]
    assert "OTP" in body and "പണം" in body


# --- list replies are read the same as button replies ----------------------

def _ctx(msg):
    return MessageContext(conn=None, transport=None, channel="whatsapp", handle="h",
                          msg=msg, user_id=1, display_name=None, tz="Asia/Kolkata",
                          voice_pref="auto", onboarding="new")


def test_button_id_reads_list_reply():
    ctx = _ctx({"interactive": {"list_reply": {"id": "ob:lang:ml"}}})
    assert ctx.button_id == "ob:lang:ml"


def test_tts_lang_for_new_languages():
    for lang, code in (("gu", "gu-IN"), ("ml", "ml-IN"), ("hi", "hi-IN"), ("en", "en-IN")):
        ctx = MessageContext(conn=None, transport=None, channel="whatsapp", handle="h",
                             msg={}, user_id=1, display_name=None, tz="Asia/Kolkata",
                             voice_pref="auto", onboarding="done", lang=lang)
        assert ctx._tts_lang() == code


# --- the list wire payload --------------------------------------------------

async def test_send_list_builds_a_list_payload(monkeypatch):
    captured = {}
    async def fake_send(conn, user_id, wa_id, payload, channel):
        captured["payload"] = payload; return "mid"
    monkeypatch.setattr(wa, "_send", fake_send)
    await wa.send_list(None, 1, "91", "pick one", "Language",
                       [("ob:lang:gu", "ગુજરાતી"), ("ob:lang:ml", "മലയാളം")])
    p = captured["payload"]
    assert p["type"] == "interactive"
    assert p["interactive"]["type"] == "list"
    assert p["interactive"]["action"]["button"] == "Language"
    rows = p["interactive"]["action"]["sections"][0]["rows"]
    assert [r["id"] for r in rows] == ["ob:lang:gu", "ob:lang:ml"]
