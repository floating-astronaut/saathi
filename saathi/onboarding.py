"""Self-serve onboarding: a deterministic, button-driven state machine.

No model call happens anywhere in here. Three reasons, in order:

1. **It makes "anyone can message us" safe.** An unknown or hostile sender walks
   a scripted path that costs a few templated replies and nothing else. That is
   what lets us drop the pairing gate without opening a cost vector.
2. **It is better for the user.** PRD §6.6 — prefer buttons over free text
   wherever the choice is bounded. Every question here is bounded, so an elder
   never has to guess the magic phrasing to get started. This is the moment they
   are most likely to give up (risk R5), so it is the worst possible place to
   ask them to improvise.
3. **It must work when the model is down.** Consent and the explanation of what
   we store are not features that can wait for Bedrock.

Order of questions is deliberate:

    consent -> name -> reminders -> improve -> done

Consent comes first because everything after it stores something. Reminders are
asked explicitly rather than defaulted (decision D3: unexpected messages erode
trust). Training consent is asked **last and separately**, because under DPDP it
is a different purpose from providing the service and must not ride along.
"""
from __future__ import annotations

import logging

from . import training

log = logging.getLogger("saathi.onboarding")

CONSENT_VERSION = "2026-07-27.v2"

# --- copy --------------------------------------------------------------------
# One language at a time. Until 2026-07-27 every onboarding message carried the
# Hindi and the English, one after the other, which doubled the length of the
# first thing a 70-year-old ever reads. PRD §2's finding is that the barrier is
# interface complexity, not device access; a wall of text at the moment someone
# is deciding whether to trust this is exactly that barrier.
#
# So: ask the language first, in both, then never repeat yourself again.

ASK_LANG = (
    "Namaste! 🙏 / Hello!\n\n"
    "Aap kis bhaasha mein baat karna chahenge?\n"
    "Which language would you like to use?"
)

COPY: dict[str, dict[str, str]] = {
    "hi": {
        "welcome": (
            "Namaste! 🙏 Main *Indofolk AI* hoon — aapki saathi.\n\n"
            "Main aapke saath hoon — baat karne ke liye bhi, aur yaad rakhne ke "
            "liye bhi. Dawa ka time, doctor ka appointment, saamaan ki list.\n\n"
            "Main kabhi paisa nahi maangti, kabhi OTP nahi maangti, aur kabhi "
            "aapke account mein kuch nahi karti.\n\n"
            "Shuru karein?"
        ),
        "consent_detail": (
            "Main yeh yaad rakhti hoon: aapka naam, aapke messages, aur jo aap "
            "mujhe yaad rakhne ko kehte hain (jaise dawa ka naam ya doctor ka "
            "naam).\n\n"
            "Aapki awaaz ki recording 7 din baad delete ho jaati hai. Aapka data "
            "*India* mein rehta hai. Kabhi bhi 'sab kuch bhool jao' kehkar sab "
            "hata sakte hain.\n\n"
            "Poori jaankari: https://n8nworld.store/privacy/"
        ),
        "ask_name": "Bahut achha! Main aapko kya kehkar bulaaun?",
        "confirm_name": "Main aapko *{name}* kehkar bulaaun?",
        "ask_reminders": (
            "{name} ji, kya main aapko cheezein yaad dilaaun — jaise dawa ka time?"
        ),
        "ask_improve": (
            "Aakhri sawaal. Kya main aapki baaton se seekh sakti hoon, taaki Hindi "
            "aur dawaiyon ke naam behtar samajh sakoon?\n\n"
            "Main aapka naam, ya kisi vyakti ka naam, kabhi nahi rakhti — sirf "
            "shabd jaise dawa ke naam. Aap 'nahi' keh sakte hain, koi farak nahi "
            "padega."
        ),
        "done": (
            "Ho gaya, {name} ji! 🌼\n\n"
            "Ab aap mujhse kuch bhi keh sakte hain. Jaise:\n"
            "• \"Roz subah aath baje dawa ka reminder laga do\"\n"
            "• \"Mere doctor ka naam yaad rakhna — Dr Sharma\"\n"
            "• \"Yeh message samajh nahi aaya, samjhao\"\n\n"
            "Bolkar bhi bhej sakte hain — voice note."
        ),
        "lang_changed": "Theek hai, ab main Hindi mein baat karungi. 🌼",
        "declined": (
            "Koi baat nahi. Jab bhi mann kare, 'shuru karein' likh dijiyega."
        ),
    },
    "en": {
        "welcome": (
            "Hello! 🙏 I'm *Indofolk AI* — your companion.\n\n"
            "I'm here for company as much as for reminders — medicines, "
            "appointments, lists, or just a chat.\n\n"
            "I never ask for money or OTPs, and never touch your accounts.\n\n"
            "Shall we start?"
        ),
        "consent_detail": (
            "I store your name, your messages, and what you ask me to remember "
            "(such as a medicine name or your doctor's name).\n\n"
            "Voice recordings are deleted after 7 days. Your data stays in "
            "*India*. You can say \"forget everything\" at any time and it all "
            "goes.\n\n"
            "Full details: https://n8nworld.store/privacy/"
        ),
        "ask_name": "Lovely. What should I call you?",
        "confirm_name": "Shall I call you *{name}*?",
        "ask_reminders": (
            "{name}, would you like me to remind you about things — a medicine, "
            "for example?"
        ),
        "ask_improve": (
            "Last question. May I learn from our chats, so I understand Hindi and "
            "medicine names better?\n\n"
            "I never keep your name, or anyone's name — only words like medicine "
            "names. Saying no changes nothing."
        ),
        "done": (
            "All set, {name}! 🌼\n\n"
            "You can ask me anything now. For example:\n"
            "• \"Remind me to take my medicine at 8 every morning\"\n"
            "• \"Remember my doctor's name — Dr Sharma\"\n"
            "• \"I don't understand this message, explain it\"\n\n"
            "You can send a voice note too."
        ),
        "lang_changed": "Done — I will speak English from now on. 🌼",
        "declined": (
            "No problem at all. Just say \"start\" whenever you'd like to begin."
        ),
    },
}

BTN: dict[str, dict[str, str]] = {
    "hi": {"yes_start": "Haan, shuru", "more": "Aur bataiye", "not_now": "Abhi nahi",
           "ok_start": "Theek hai, shuru", "yes": "Haan", "other_name": "Doosra naam",
           "yes_send": "Haan, bhejiye", "yes_fine": "Haan, theek hai", "no": "Nahi"},
    "en": {"yes_start": "Yes, let's start", "more": "Tell me more", "not_now": "Not now",
           "ok_start": "Alright, start", "yes": "Yes", "other_name": "Another name",
           "yes_send": "Yes, please", "yes_fine": "Yes, that's fine", "no": "No"},
}

DEFAULT_LANG = "hi"


def t(lang: str, key: str, **fmt) -> str:
    """Copy in the user's language, falling back rather than failing."""
    table = COPY.get(lang) or COPY[DEFAULT_LANG]
    s = table.get(key) or COPY[DEFAULT_LANG][key]
    return s.format(**fmt) if fmt else s


def b(lang: str, key: str) -> str:
    return (BTN.get(lang) or BTN[DEFAULT_LANG]).get(key, BTN[DEFAULT_LANG][key])


async def _lang(conn, user_id: int) -> str:
    """The language this user chose. 'hi-en' predates the language step."""
    row = await (await conn.execute(
        "select lang_pref from users where id = %s", (user_id,))).fetchone()
    pref = (row[0] if row and row[0] else DEFAULT_LANG)
    return pref if pref in COPY else DEFAULT_LANG


def _buttons(*pairs: tuple[str, str]) -> list[tuple[str, str]]:
    return list(pairs)


async def begin(conn, transport, user_id: int, handle: str) -> dict:
    """First contact. Ask which language, before anything else.

    This is the only message sent in both languages. Everything after it speaks
    one, because the first thing a 70-year-old reads should not be twice as long
    as it needs to be.
    """
    await transport.send_buttons(conn, user_id, handle, ASK_LANG, _buttons(
        ("ob:lang:hi", "हिंदी"),
        ("ob:lang:en", "English"),
    ))
    return {"onboarding": "new"}


async def _welcome(conn, transport, user_id: int, handle: str, lang: str) -> dict:
    """Explain, then ask for consent — in the chosen language."""
    await conn.execute("update users set onboarding = 'consent' where id = %s", (user_id,))
    await transport.send_buttons(conn, user_id, handle, t(lang, "welcome"), _buttons(
        ("ob:consent:yes", b(lang, "yes_start")),
        ("ob:consent:info", b(lang, "more")),
        ("ob:consent:no", b(lang, "not_now")),
    ))
    return {"onboarding": "consent"}


async def handle_button(conn, transport, user_id: int, handle: str,
                        button_id: str, display_name: str | None) -> dict | None:
    """Advance the machine on a button press. Returns None if not ours."""
    if not button_id.startswith("ob:"):
        return None
    _, step, choice = button_id.split(":", 2)

    if step == "lang":
        lang = choice if choice in COPY else DEFAULT_LANG
        await conn.execute(
            "update users set lang_pref = %s where id = %s", (lang, user_id))
        log.info("user %s chose language %s", user_id, lang)
        # An onboarded user changing language must NOT be sent back through
        # consent. `_welcome` sets onboarding='consent', so calling it here
        # would silently un-onboard someone who only wanted English.
        row = await (await conn.execute(
            "select onboarding::text from users where id = %s", (user_id,))).fetchone()
        if row and row[0] == "done":
            await transport.send_text(conn, user_id, handle, t(lang, "lang_changed"))
            return {"onboarding": "done", "language": lang}
        return await _welcome(conn, transport, user_id, handle, lang)

    lang = await _lang(conn, user_id)

    if step == "consent":
        if choice == "info":
            await transport.send_buttons(
                conn, user_id, handle, t(lang, "consent_detail"), _buttons(
                    ("ob:consent:yes", b(lang, "ok_start")),
                    ("ob:consent:no", b(lang, "not_now")),
                ))
            return {"onboarding": "consent"}
        if choice == "no":
            await conn.execute("update users set onboarding = 'new' where id = %s", (user_id,))
            await transport.send_text(conn, user_id, handle, t(lang, "declined"))
            return {"onboarding": "declined"}
        # granted — record the language the consent was actually read in
        await conn.execute(
            """insert into consent_log (user_id, version, lang, granted)
               values (%s,%s,%s,true)""", (user_id, CONSENT_VERSION, lang))
        await conn.execute(
            """update users set consent_at = now(), consent_version = %s,
                   onboarding = 'name' where id = %s""", (CONSENT_VERSION, user_id))
        # If WhatsApp gave us a profile name, confirm it rather than asking cold —
        # one less thing to type for someone who finds typing hard.
        if display_name:
            await transport.send_buttons(
                conn, user_id, handle, t(lang, "confirm_name", name=display_name),
                _buttons(("ob:name:yes", b(lang, "yes")),
                         ("ob:name:other", b(lang, "other_name"))))
        else:
            await transport.send_text(conn, user_id, handle, t(lang, "ask_name"))
        return {"onboarding": "name"}

    if step == "name":
        if choice == "other":
            await transport.send_text(conn, user_id, handle, t(lang, "ask_name"))
            return {"onboarding": "name"}
        return await _ask_reminders(conn, transport, user_id, handle, display_name)

    if step == "rem":
        await conn.execute(
            "update users set paused = %s, onboarding = 'improve' where id = %s",
            (choice == "no", user_id))
        await transport.send_buttons(
            conn, user_id, handle, t(lang, "ask_improve"), _buttons(
                ("ob:imp:yes", b(lang, "yes_fine")), ("ob:imp:no", b(lang, "no"))))
        return {"onboarding": "improve"}

    if step == "imp":
        await training.set_consent(conn, user_id, choice == "yes")
        await conn.execute(
            "update users set onboarding = 'done', onboarded_via = 'self' where id = %s",
            (user_id,))
        name = await _name(conn, user_id)
        await transport.send_text(conn, user_id, handle, t(lang, "done", name=name))
        log.info("user %s finished onboarding (training=%s)", user_id, choice)
        return {"onboarding": "done"}

    return None


async def handle_text(conn, transport, user_id: int, handle: str,
                      state: str, text: str) -> dict | None:
    """Advance on free text. Only the name step expects any."""
    if state == "name":
        name = " ".join(text.split())[:40]
        if not name:
            return {"onboarding": "name"}
        await conn.execute("update users set display_name = %s where id = %s", (name, user_id))
        return await _ask_reminders(conn, transport, user_id, handle, name)

    if state in ("consent", "reminders", "improve"):
        # They typed instead of tapping. Re-offer the buttons rather than
        # guessing — guessing at consent is exactly what we must not do. They
        # have already picked a language, so do not ask again.
        return await _welcome(conn, transport, user_id, handle, await _lang(conn, user_id))
    return None


async def _ask_reminders(conn, transport, user_id, handle, name):
    await conn.execute("update users set onboarding = 'reminders' where id = %s", (user_id,))
    lang = await _lang(conn, user_id)
    nm = name or await _name(conn, user_id)
    await transport.send_buttons(
        conn, user_id, handle, t(lang, "ask_reminders", name=nm),
        _buttons(("ob:rem:yes", b(lang, "yes_send")),
                 ("ob:rem:no", b(lang, "not_now"))))
    return {"onboarding": "reminders"}


async def _name(conn, user_id: int) -> str:
    row = await (await conn.execute(
        "select display_name from users where id = %s", (user_id,))).fetchone()
    return (row[0] if row and row[0] else "Aap")
