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

CONSENT_VERSION = "2026-07-26.v1"

# --- copy --------------------------------------------------------------------
# Hindi first in Latin script, English after. Short lines: this is read on a
# phone, often at arm's length.

WELCOME = (
    "Namaste! 🙏 Main *Saathi* hoon.\n\n"
    "Main aapke saath hoon — baat karne ke liye bhi, aur yaad rakhne ke liye bhi. "
    "Dawa ka time, doctor ka appointment, saamaan ki list. Aap mujhse Hindi ya "
    "English mein, likh kar ya bol kar baat kar sakte hain.\n\n"
    "Main kabhi paisa nahi maangti, kabhi OTP nahi maangti, aur kabhi aapke "
    "account mein kuch nahi karti.\n\n"
    "*I'm Saathi.* I'm here for company as much as for reminders — medicines, "
    "appointments, lists, or just a chat. Talk to me in Hindi or English, by "
    "typing or voice note. I never ask for money or OTPs, and never touch your "
    "accounts.\n\n"
    "Shuru karein? / Shall we start?"
)

CONSENT_DETAIL = (
    "Main yeh yaad rakhti hoon: aapka naam, aapke messages, aur jo aap mujhe "
    "yaad rakhne ko kehte hain (jaise dawa ka naam ya doctor ka naam).\n\n"
    "Aapki awaaz ki recording 7 din baad delete ho jaati hai. Aapka data "
    "*India* mein rehta hai. Kabhi bhi 'sab kuch bhool jao' kehkar sab hata "
    "sakte hain.\n\n"
    "I store your name, your messages, and what you ask me to remember. Voice "
    "recordings are deleted after 7 days. Your data stays in India. You can say "
    "\"forget everything\" at any time.\n\n"
    "Poori jaankari: https://n8nworld.store/privacy/"
)

ASK_NAME = (
    "Bahut achha! Main aapko kya kehkar bulaaun?\n\n"
    "Lovely. What should I call you?"
)

ASK_REMINDERS = (
    "{name} ji, kya main aapko cheezein yaad dilaaun — jaise dawa ka time?\n\n"
    "Would you like me to send you reminders, for example when it's time for a "
    "medicine?"
)

ASK_IMPROVE = (
    "Aakhri sawaal. Kya main aapki baaton se seekh sakti hoon, taaki Hindi aur "
    "dawaiyon ke naam behtar samajh sakoon?\n\n"
    "Main aapka naam, ya kisi vyakti ka naam, kabhi nahi rakhti — sirf shabd "
    "jaise dawa ke naam. Aap 'nahi' keh sakte hain, koi farak nahi padega.\n\n"
    "Last question. May I learn from our chats to understand Hindi and medicine "
    "names better? I never keep your name or anyone's name — only words like "
    "medicine names. Saying no changes nothing."
)

DONE = (
    "Ho gaya, {name} ji! 🌼\n\n"
    "Ab aap mujhse kuch bhi keh sakte hain. Jaise:\n"
    "• \"Roz subah aath baje dawa ka reminder laga do\"\n"
    "• \"Mere doctor ka naam yaad rakhna — Dr Sharma\"\n"
    "• \"Yeh message samajh nahi aaya, samjhao\"\n\n"
    "Bolkar bhi bhej sakte hain — voice note. Kuch bhi puchhna ho, bas likhiye."
)

DECLINED = (
    "Koi baat nahi. Jab bhi mann kare, 'shuru karein' likh dijiyega.\n\n"
    "No problem at all. Just say \"start\" whenever you'd like to begin."
)


def _buttons(*pairs: tuple[str, str]) -> list[tuple[str, str]]:
    return list(pairs)


async def begin(conn, transport, user_id: int, handle: str) -> dict:
    """First contact. Explain, then ask for consent."""
    await conn.execute("update users set onboarding = 'consent' where id = %s", (user_id,))
    await transport.send_buttons(conn, user_id, handle, WELCOME, _buttons(
        ("ob:consent:yes", "Haan, shuru"),
        ("ob:consent:info", "Aur bataiye"),
        ("ob:consent:no", "Abhi nahi"),
    ))
    return {"onboarding": "consent"}


async def handle_button(conn, transport, user_id: int, handle: str,
                        button_id: str, display_name: str | None) -> dict | None:
    """Advance the machine on a button press. Returns None if not ours."""
    if not button_id.startswith("ob:"):
        return None
    _, step, choice = button_id.split(":", 2)

    if step == "consent":
        if choice == "info":
            await transport.send_buttons(conn, user_id, handle, CONSENT_DETAIL, _buttons(
                ("ob:consent:yes", "Theek hai, shuru"),
                ("ob:consent:no", "Abhi nahi"),
            ))
            return {"onboarding": "consent"}
        if choice == "no":
            await conn.execute("update users set onboarding = 'new' where id = %s", (user_id,))
            await transport.send_text(conn, user_id, handle, DECLINED)
            return {"onboarding": "declined"}
        # granted
        await conn.execute(
            """insert into consent_log (user_id, version, lang, granted)
               values (%s,%s,'hi-en',true)""", (user_id, CONSENT_VERSION))
        await conn.execute(
            """update users set consent_at = now(), consent_version = %s,
                   onboarding = 'name' where id = %s""", (CONSENT_VERSION, user_id))
        # If WhatsApp gave us a profile name, confirm it rather than asking cold —
        # one less thing to type for someone who finds typing hard.
        if display_name:
            await transport.send_buttons(
                conn, user_id, handle,
                f"Main aapko *{display_name}* kehkar bulaaun?\n\nShall I call you {display_name}?",
                _buttons(("ob:name:yes", "Haan"), ("ob:name:other", "Doosra naam")))
        else:
            await transport.send_text(conn, user_id, handle, ASK_NAME)
        return {"onboarding": "name"}

    if step == "name":
        if choice == "other":
            await transport.send_text(conn, user_id, handle, ASK_NAME)
            return {"onboarding": "name"}
        return await _ask_reminders(conn, transport, user_id, handle, display_name)

    if step == "rem":
        await conn.execute(
            "update users set paused = %s, onboarding = 'improve' where id = %s",
            (choice == "no", user_id))
        await transport.send_buttons(conn, user_id, handle, ASK_IMPROVE, _buttons(
            ("ob:imp:yes", "Haan, theek hai"), ("ob:imp:no", "Nahi")))
        return {"onboarding": "improve"}

    if step == "imp":
        await training.set_consent(conn, user_id, choice == "yes")
        await conn.execute(
            "update users set onboarding = 'done', onboarded_via = 'self' where id = %s",
            (user_id,))
        name = await _name(conn, user_id)
        await transport.send_text(conn, user_id, handle, DONE.format(name=name))
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
        # guessing — guessing at consent is exactly what we must not do.
        await begin(conn, transport, user_id, handle)
        return {"onboarding": "consent"}
    return None


async def _ask_reminders(conn, transport, user_id, handle, name):
    await conn.execute("update users set onboarding = 'reminders' where id = %s", (user_id,))
    nm = name or await _name(conn, user_id)
    await transport.send_buttons(conn, user_id, handle, ASK_REMINDERS.format(name=nm),
                                 _buttons(("ob:rem:yes", "Haan, bhejiye"),
                                          ("ob:rem:no", "Abhi nahi")))
    return {"onboarding": "reminders"}


async def _name(conn, user_id: int) -> str:
    row = await (await conn.execute(
        "select display_name from users where id = %s", (user_id,))).fetchone()
    return (row[0] if row and row[0] else "Aap")
