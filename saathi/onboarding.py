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
from datetime import datetime, timezone

from . import capi, training
from .config import settings
from .speech import sarvam_lang

log = logging.getLogger("saathi.onboarding")


async def _voice_user(conn, user_id: int) -> bool:
    """Has this person ever spoken to us? A voice note in their history means we
    should onboard them by voice too — many elders talk far more easily than they
    read (VOICE-2). Reads the `messages` log, so no new state is needed."""
    row = await (await conn.execute(
        "select 1 from messages where user_id = %s and direction = 'in' "
        "and kind = 'audio' limit 1", (user_id,))).fetchone()
    return row is not None


async def _maybe_voice(conn, transport, user_id: int, handle: str,
                       text: str, lang: str) -> None:
    """Speak an onboarding message too, for a voice user. Additive to the text +
    buttons and best-effort: the message has already gone, and TTS is a vendor
    call on our own fixed copy (not the model), so this does not touch the
    "onboarding never calls the model" boundary. Fixed strings hit the phrase
    cache, so it is nearly free. Buttons/lists can't ride a voice note, so the
    text+buttons stay the primary; the voice is an accessibility layer on top."""
    if not settings.saathi_tts_enabled:
        return
    if not await _voice_user(conn, user_id):
        return
    try:
        await transport.send_voice(conn, user_id, handle, text, sarvam_lang(lang))
    except Exception:  # noqa: BLE001 -- voice must never break onboarding
        log.exception("onboarding voice failed for user %s", user_id)

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
    "नमस्ते! 🙏 Namaste! / Hello! / નમસ્તે / നമസ്കാരം\n\n"
    "अपनी भाषा चुनें / Choose your language:"
)

#: The label on the button that opens the language list (WhatsApp caps it at 20
#: chars).
LANG_LIST_BUTTON = "भाषा / Language"

#: The languages we offer. This outgrew WhatsApp's three-quick-reply limit when
#: Gujarati and Malayalam were added (LANG-2), so the picker is a **list message**
#: (up to 10 rows), not buttons — see `begin()`.
#:
#: "हिंदी" and "Hinglish" are the same language in two scripts, and the split is
#: not pedantry: reading and typing are different skills for this audience.
#: Each label is written in the script it selects, so the choice is legible
#: without being explained.
LANG_ROWS = [
    ("ob:lang:hi", "हिंदी"),
    ("ob:lang:hi-en", "Hinglish"),
    ("ob:lang:en", "English"),
    ("ob:lang:gu", "ગુજરાતી"),
    ("ob:lang:ml", "മലയാളം"),
]

COPY: dict[str, dict[str, str]] = {
    "hi": {
        "welcome": (
            "नमस्ते! 🙏 मैं *Indofolk AI* हूँ — आपकी साथी।\n\n"
            "मैं आपके साथ हूँ — बात करने के लिए भी, और याद रखने के लिए भी। "
            "दवा का समय, डॉक्टर का अपॉइंटमेंट, सामान की सूची।\n\n"
            "मैं कभी पैसे नहीं माँगती, कभी OTP नहीं माँगती, और कभी आपके खाते में "
            "कुछ नहीं करती।\n\n"
            "शुरू करें?"
        ),
        "consent_detail": (
            "मैं यह याद रखती हूँ: आपका नाम, आपके संदेश, और जो आप मुझे याद रखने को "
            "कहते हैं (जैसे दवा का नाम या डॉक्टर का नाम)।\n\n"
            "आपकी आवाज़ की रिकॉर्डिंग 7 दिन बाद मिट जाती है। आपका डेटा *भारत* में "
            "रहता है। कभी भी 'सब कुछ भूल जाओ' कहकर सब हटा सकते हैं।\n\n"
            "पूरी जानकारी: https://n8nworld.store/privacy/"
        ),
        "ask_name": "बहुत अच्छा! मैं आपको क्या कहकर बुलाऊँ?",
        "confirm_name": "मैं आपको *{name}* कहकर बुलाऊँ?",
        "ask_reminders": (
            "{name} जी, क्या मैं आपको चीज़ें याद दिलाऊँ — जैसे दवा का समय?"
        ),
        "ask_improve": (
            "आख़िरी सवाल। क्या मैं आपकी बातों से सीख सकती हूँ, ताकि हिंदी और "
            "दवाइयों के नाम बेहतर समझ सकूँ?\n\n"
            "मैं आपका नाम, या किसी व्यक्ति का नाम, कभी नहीं रखती — सिर्फ़ शब्द "
            "जैसे दवा के नाम। आप 'नहीं' कह सकते हैं, कोई फ़र्क नहीं पड़ेगा।"
        ),
        "done": (
            "हो गया, {name} जी! 🌼\n\n"
            "अब आप मुझसे कुछ भी कह सकते हैं। जैसे:\n"
            "• \"रोज़ सुबह आठ बजे दवा का रिमाइंडर लगा दो\"\n"
            "• \"मेरे डॉक्टर का नाम याद रखना — Dr Sharma\"\n"
            "• \"यह संदेश समझ नहीं आया, समझाओ\"\n\n"
            "बोलकर भी भेज सकते हैं — voice note।"
        ),
        "lang_changed": "ठीक है, अब मैं हिंदी में बात करूँगी। 🌼",
        "declined": (
            "कोई बात नहीं। जब भी मन करे, 'शुरू करें' लिख दीजिएगा।"
        ),
    },
    "hi-en": {
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
    # ⚠️ gu/ml copy below is a first draft (LANG-2, 2026-07-30) and NEEDS NATIVE
    # ELDER-AUDIENCE REVIEW before it can be considered final — see
    # docs/PROD_READINESS.md (LANG-2) and D-AF. Structure mirrors hi/en exactly.
    "gu": {
        "welcome": (
            "નમસ્તે! 🙏 હું *Indofolk AI* છું — તમારી સાથી.\n\n"
            "હું તમારી સાથે છું — વાત કરવા માટે પણ, અને યાદ રાખવા માટે પણ. "
            "દવાનો સમય, ડૉક્ટરની એપોઇન્ટમેન્ટ, સામાનની યાદી.\n\n"
            "હું ક્યારેય પૈસા નથી માંગતી, ક્યારેય OTP નથી માંગતી, અને ક્યારેય "
            "તમારા ખાતામાં કંઈ કરતી નથી.\n\n"
            "શરૂ કરીએ?"
        ),
        "consent_detail": (
            "હું આ યાદ રાખું છું: તમારું નામ, તમારા સંદેશા, અને જે તમે મને યાદ "
            "રાખવા કહો છો (જેમ કે દવાનું નામ કે ડૉક્ટરનું નામ).\n\n"
            "તમારા અવાજની રેકોર્ડિંગ 7 દિવસ પછી ભૂંસાઈ જાય છે. તમારો ડેટા "
            "*ભારત*માં રહે છે. ગમે ત્યારે 'બધું ભૂલી જા' કહીને બધું હટાવી શકો છો.\n\n"
            "પૂરી માહિતી: https://n8nworld.store/privacy/"
        ),
        "ask_name": "બહુ સરસ! હું તમને શું કહીને બોલાવું?",
        "confirm_name": "હું તમને *{name}* કહીને બોલાવું?",
        "ask_reminders": (
            "{name}, શું હું તમને વસ્તુઓ યાદ કરાવું — જેમ કે દવાનો સમય?"
        ),
        "ask_improve": (
            "છેલ્લો સવાલ. શું હું આપણી વાતોમાંથી શીખી શકું, જેથી ગુજરાતી અને "
            "દવાઓના નામ વધુ સારી રીતે સમજી શકું?\n\n"
            "હું તમારું નામ, કે કોઈ વ્યક્તિનું નામ, ક્યારેય રાખતી નથી — ફક્ત "
            "શબ્દો જેમ કે દવાના નામ. તમે 'ના' કહી શકો છો, કોઈ ફરક નહીં પડે."
        ),
        "done": (
            "થઈ ગયું, {name}! 🌼\n\n"
            "હવે તમે મને કંઈ પણ કહી શકો છો. જેમ કે:\n"
            "• \"રોજ સવારે આઠ વાગ્યે દવાનું રિમાઇન્ડર મૂકી દો\"\n"
            "• \"મારા ડૉક્ટરનું નામ યાદ રાખજો — Dr Sharma\"\n"
            "• \"આ સંદેશ સમજાયો નહીં, સમજાવો\"\n\n"
            "બોલીને પણ મોકલી શકો છો — voice note."
        ),
        "lang_changed": "ઠીક છે, હવે હું ગુજરાતીમાં વાત કરીશ. 🌼",
        "declined": (
            "કોઈ વાંધો નહીં. જ્યારે પણ મન થાય, 'શરૂ કરીએ' લખી દેજો."
        ),
    },
    "ml": {
        "welcome": (
            "നമസ്കാരം! 🙏 ഞാൻ *Indofolk AI* ആണ് — നിങ്ങളുടെ കൂട്ടുകാരി.\n\n"
            "ഞാൻ നിങ്ങളോടൊപ്പമുണ്ട് — സംസാരിക്കാനും ഓർത്തുവയ്ക്കാനും. "
            "മരുന്നിന്റെ സമയം, ഡോക്ടറുടെ അപ്പോയിന്റ്മെന്റ്, സാധനങ്ങളുടെ പട്ടിക.\n\n"
            "ഞാൻ ഒരിക്കലും പണം ചോദിക്കില്ല, OTP ചോദിക്കില്ല, നിങ്ങളുടെ "
            "അക്കൗണ്ടിൽ ഒന്നും ചെയ്യില്ല.\n\n"
            "തുടങ്ങാമോ?"
        ),
        "consent_detail": (
            "ഞാൻ ഇവ ഓർത്തുവയ്ക്കുന്നു: നിങ്ങളുടെ പേര്, നിങ്ങളുടെ സന്ദേശങ്ങൾ, "
            "ഓർക്കാൻ നിങ്ങൾ പറയുന്നവ (മരുന്നിന്റെ പേര് അല്ലെങ്കിൽ ഡോക്ടറുടെ പേര് "
            "പോലെ).\n\n"
            "നിങ്ങളുടെ ശബ്ദ റെക്കോർഡിംഗ് 7 ദിവസത്തിനു ശേഷം മായ്ക്കപ്പെടും. "
            "നിങ്ങളുടെ ഡാറ്റ *ഇന്ത്യയിൽ* തന്നെ നിൽക്കും. എപ്പോൾ വേണമെങ്കിലും "
            "'എല്ലാം മറന്നുകളയൂ' എന്ന് പറഞ്ഞ് എല്ലാം നീക്കം ചെയ്യാം.\n\n"
            "പൂർണ്ണ വിവരങ്ങൾ: https://n8nworld.store/privacy/"
        ),
        "ask_name": "വളരെ നല്ലത്! ഞാൻ നിങ്ങളെ എന്ത് വിളിക്കണം?",
        "confirm_name": "ഞാൻ നിങ്ങളെ *{name}* എന്ന് വിളിക്കട്ടെ?",
        "ask_reminders": (
            "{name}, കാര്യങ്ങൾ ഞാൻ ഓർമ്മിപ്പിക്കണോ — മരുന്നിന്റെ സമയം പോലെ?"
        ),
        "ask_improve": (
            "അവസാന ചോദ്യം. നമ്മുടെ സംഭാഷണങ്ങളിൽ നിന്ന് ഞാൻ പഠിക്കട്ടെ, "
            "മലയാളവും മരുന്നുകളുടെ പേരുകളും നന്നായി മനസ്സിലാക്കാൻ?\n\n"
            "നിങ്ങളുടെ പേരോ ആരുടെയെങ്കിലും പേരോ ഞാൻ ഒരിക്കലും സൂക്ഷിക്കില്ല — "
            "മരുന്നിന്റെ പേര് പോലുള്ള വാക്കുകൾ മാത്രം. 'വേണ്ട' എന്ന് പറയാം, ഒരു "
            "മാറ്റവുമില്ല."
        ),
        "done": (
            "കഴിഞ്ഞു, {name}! 🌼\n\n"
            "ഇനി നിങ്ങൾക്ക് എന്നോട് എന്തും പറയാം. ഉദാഹരണത്തിന്:\n"
            "• \"എല്ലാ ദിവസവും രാവിലെ എട്ട് മണിക്ക് മരുന്ന് ഓർമ്മിപ്പിക്കൂ\"\n"
            "• \"എന്റെ ഡോക്ടറുടെ പേര് ഓർത്തുവയ്ക്കൂ — Dr Sharma\"\n"
            "• \"ഈ സന്ദേശം മനസ്സിലായില്ല, വിശദീകരിക്കൂ\"\n\n"
            "വോയ്സ് നോട്ടായും അയയ്ക്കാം."
        ),
        "lang_changed": "ശരി, ഇനി ഞാൻ മലയാളത്തിൽ സംസാരിക്കാം. 🌼",
        "declined": (
            "കുഴപ്പമില്ല. എപ്പോൾ വേണമെങ്കിലും 'തുടങ്ങാം' എന്ന് എഴുതൂ."
        ),
    },
}

BTN: dict[str, dict[str, str]] = {
    "hi": {"yes_start": "हाँ, शुरू करें", "more": "और बताइए", "not_now": "अभी नहीं",
           "ok_start": "ठीक है, शुरू", "yes": "हाँ", "other_name": "दूसरा नाम",
           "yes_send": "हाँ, भेजिए", "yes_fine": "हाँ, ठीक है", "no": "नहीं"},
    "hi-en": {"yes_start": "Haan, shuru", "more": "Aur bataiye", "not_now": "Abhi nahi",
           "ok_start": "Theek hai, shuru", "yes": "Haan", "other_name": "Doosra naam",
           "yes_send": "Haan, bhejiye", "yes_fine": "Haan, theek hai", "no": "Nahi"},
    "en": {"yes_start": "Yes, let's start", "more": "Tell me more", "not_now": "Not now",
           "ok_start": "Alright, start", "yes": "Yes", "other_name": "Another name",
           "yes_send": "Yes, please", "yes_fine": "Yes, that's fine", "no": "No"},
    # ⚠️ gu/ml labels are a first draft (LANG-2) pending native review. Each must
    # stay within WhatsApp's 20-char quick-reply button limit.
    "gu": {"yes_start": "હા, શરૂ કરીએ", "more": "વધુ કહો", "not_now": "હમણાં નહીં",
           "ok_start": "ઠીક છે, શરૂ", "yes": "હા", "other_name": "બીજું નામ",
           "yes_send": "હા, મોકલો", "yes_fine": "હા, ઠીક છે", "no": "ના"},
    "ml": {"yes_start": "അതെ, തുടങ്ങാം", "more": "കൂടുതൽ പറയൂ", "not_now": "ഇപ്പോൾ വേണ്ട",
           "ok_start": "ശരി, തുടങ്ങാം", "yes": "അതെ", "other_name": "മറ്റൊരു പേര്",
           "yes_send": "അതെ, അയയ്ക്കൂ", "yes_fine": "അതെ, ശരി", "no": "വേണ്ട"},
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


async def _grant_free_allowance(conn, user_id: int) -> None:
    """Queue the free $5 key, now that someone has actually finished onboarding.

    **Queued, never minted here.** Onboarding makes no model call and no
    third-party call — that property is exactly what lets the door stay open —
    and a blocking HTTP request to OpenRouter on this path would regress it.
    The queue does the vendor work; once it lands, the account's own key is
    used for model turns.

    Placed at *completion* rather than at first contact on purpose. The free
    grant is real money, and a number that probes us once and never answers
    should get an account row and nothing billable.

    Failure here is swallowed deliberately: the person finished onboarding and
    is waiting on a reply. Losing the key costs them nothing they can see —
    the provisioning row can be backfilled and retried — while losing the reply
    would be the last thing that happened to them.
    """
    from . import accounts, openrouter, scheduling
    from .worker import turns  # noqa: F401 — registers the `provision_key` kind
    try:
        account_id = await accounts.ensure_for_user(conn, user_id)
        await scheduling.enqueue(
            conn, user_id, "provision_key", datetime.now(timezone.utc),
            payload={"account_id": account_id},
            dedupe_key=openrouter.provision_dedupe_key(account_id))
        log.info("queued free allowance for user %s (account %s)", user_id, account_id)
    except Exception:
        log.exception("could not queue the free allowance for user %s", user_id)


async def begin(conn, transport, user_id: int, handle: str) -> dict:
    """First contact. Ask which language, before anything else.

    This is the only message sent in multiple languages. Everything after it
    speaks one, because the first thing a 70-year-old reads should not be several
    times as long as it needs to be. A **list**, not buttons: five languages
    exceeds WhatsApp's three-quick-reply limit (LANG-2).
    """
    await transport.send_list(conn, user_id, handle, ASK_LANG,
                              LANG_LIST_BUTTON, list(LANG_ROWS))
    return {"onboarding": "new"}


async def _welcome(conn, transport, user_id: int, handle: str, lang: str) -> dict:
    """Explain, then ask for consent — in the chosen language."""
    await conn.execute("update users set onboarding = 'consent' where id = %s", (user_id,))
    await transport.send_buttons(conn, user_id, handle, t(lang, "welcome"), _buttons(
        ("ob:consent:yes", b(lang, "yes_start")),
        ("ob:consent:info", b(lang, "more")),
        ("ob:consent:no", b(lang, "not_now")),
    ))
    await _maybe_voice(conn, transport, user_id, handle, t(lang, "welcome"), lang)
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
            await _maybe_voice(conn, transport, user_id, handle, t(lang, "lang_changed"), lang)
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
            await _maybe_voice(conn, transport, user_id, handle, t(lang, "consent_detail"), lang)
            return {"onboarding": "consent"}
        if choice == "no":
            await conn.execute("update users set onboarding = 'new' where id = %s", (user_id,))
            await transport.send_text(conn, user_id, handle, t(lang, "declined"))
            await _maybe_voice(conn, transport, user_id, handle, t(lang, "declined"), lang)
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
            await _maybe_voice(conn, transport, user_id, handle,
                               t(lang, "confirm_name", name=display_name), lang)
        else:
            await transport.send_text(conn, user_id, handle, t(lang, "ask_name"))
            await _maybe_voice(conn, transport, user_id, handle, t(lang, "ask_name"), lang)
        return {"onboarding": "name"}

    if step == "name":
        if choice == "other":
            await transport.send_text(conn, user_id, handle, t(lang, "ask_name"))
            await _maybe_voice(conn, transport, user_id, handle, t(lang, "ask_name"), lang)
            return {"onboarding": "name"}
        return await _ask_reminders(conn, transport, user_id, handle, display_name)

    if step == "rem":
        await conn.execute(
            "update users set paused = %s, onboarding = 'improve' where id = %s",
            (choice == "no", user_id))
        await transport.send_buttons(
            conn, user_id, handle, t(lang, "ask_improve"), _buttons(
                ("ob:imp:yes", b(lang, "yes_fine")), ("ob:imp:no", b(lang, "no"))))
        await _maybe_voice(conn, transport, user_id, handle, t(lang, "ask_improve"), lang)
        return {"onboarding": "improve"}

    if step == "imp":
        await training.set_consent(conn, user_id, choice == "yes")
        await conn.execute(
            "update users set onboarding = 'done', onboarded_via = 'self' where id = %s",
            (user_id,))
        await _grant_free_allowance(conn, user_id)
        # Attribution (CAPI-1): if this signup came from a click-to-WhatsApp ad,
        # report the conversion. No-op for organic signups and when disabled;
        # never raises, so it cannot cost the person their completion reply.
        await capi.report_lead(conn, user_id)
        name = await _name(conn, user_id)
        await transport.send_text(conn, user_id, handle, t(lang, "done", name=name))
        await _maybe_voice(conn, transport, user_id, handle, t(lang, "done", name=name), lang)
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
    await _maybe_voice(conn, transport, user_id, handle, t(lang, "ask_reminders", name=nm), lang)
    return {"onboarding": "reminders"}


async def _name(conn, user_id: int) -> str:
    row = await (await conn.execute(
        "select display_name from users where id = %s", (user_id,))).fetchone()
    return (row[0] if row and row[0] else "Aap")
