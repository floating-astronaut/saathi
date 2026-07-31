"""Deterministic pre-LLM safety classifier (PRD §12, risk R7).

Runs on every inbound message **before the model sees anything**. This is not a
prompt instruction — a prompt instruction can be argued with, and a forwarded
scam message is untrusted input that will try. Regex cannot be talked round.

Design rules:
  * Match Hindi, English and romanised Hinglish. Elders code-mix mid-sentence.
  * Prefer a false positive over a false negative. Wrongly showing an emergency
    number is a mild annoyance; missing a stroke is not.
  * Every hit short-circuits the LLM turn entirely and returns fixed copy.

LANGUAGE COVERAGE (SAFE-LANG-1, 2026-07-30): patterns now cover Hindi, English,
romanised Hinglish, **and native-script Gujarati + Malayalam** — emergencies,
hypoglycemia, self-harm, medical-advice, and native pressure phrases for scam/
suspicious (the mechanical scam markers — OTP, PIN, CVV, KYC, AnyDesk, UPI brand
names — are Latin and already caught for every language). Non-Latin scripts are
case-less, so `re.I`/lowercasing in `_normalise` is a no-op for them and matching
works unchanged.

⚠️ The gu/ml patterns are a **first pass and still want native-speaker review** —
they follow the "prefer a false positive over a false negative" rule and use fuzzy
`.{0,N}` gaps to tolerate spelling/dialect variation, but a native pass may add
phrasings and catch over-broad matches. This is a real improvement over the prior
zero deterministic coverage for gu/ml, not the final word. Tracked to completion on
SAFE-LANG-1.

Numbers used are the real Indian services:
  112    national emergency (police/fire/ambulance)
  108    state ambulance services
  14416  Tele-MANAS, Government of India mental-health helpline
  1800-599-0019  KIRAN mental-health helpline
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


class Trigger(str, Enum):
    MEDICAL_EMERGENCY = "medical_emergency"
    SELF_HARM = "self_harm"
    HYPOGLYCEMIA = "hypoglycemia"
    MEDICAL_ADVICE = "medical_advice"
    SCAM = "scam"
    SUSPICIOUS = "suspicious"


@dataclass(frozen=True)
class Verdict:
    trigger: Trigger | None
    matched: str | None = None
    reply: str | None = None

    @property
    def blocks_llm(self) -> bool:
        # Medical-advice requests still need a warm human-sounding decline, but
        # they must not reach the tool loop; emergencies bypass everything.
        return self.trigger is not None


# --- patterns ---------------------------------------------------------------
# Written as alternations of whole words so "gir" does not match "girna sikha".

_EMERGENCY = [
    # chest / cardiac
    r"seene? me[ni]?n? dard", r"chhati me[ni]?n? dard", r"chest pain",
    r"heart attack", r"dil ka daura",
    # breathing
    r"saans nahi aa", r"saans phool", r"saans ruk", r"can'?t breathe",
    r"cannot breathe", r"breathless", r"dam ghut",
    # fall
    # "gir gaya" means fell — but "sugar gir gaya" means blood sugar dropped,
    # which needs glucose, not an ambulance. Without these lookbehinds a
    # diabetic reporting a hypo gets sent to 112 and told to call someone,
    # while the thing that would actually help goes unsaid.
    r"(?<!sugar )(?<!bp )(?<!pressure )(?<!shakkar )gir ga(ya|yi|ye)",
    r"\bfell down\b", r"\bhad a fall\b", r"utha nahi ja",
    # stroke
    r"muh tedha", r"bolne me[ni]?n? dikkat", r"ek taraf sunn",
    r"\bstroke\b", r"\bparalysis\b", r"lakwa",
    # bleeding / unconscious
    r"bahut khoon", r"heavy bleeding", r"behosh", r"unconscious",
    # --- Gujarati (SAFE-LANG-1, provisional — native review recommended) ---
    r"છાતી.{0,4}(દુખાવો|દર્દ|દુખે)",          # chest pain
    r"હાર્ટ એટેક", r"હૃદય.{0,6}હુમલો",          # heart attack
    r"શ્વાસ.{0,10}(નથી|તકલીફ|લેવા|રૂંધા|ચડ)",  # can't breathe
    r"પડી ગય",                                  # fell (gu "sugar" drop uses ઓછી, not પડી)
    r"બેભાન", r"બેહોશ",                          # unconscious
    r"લકવો", r"પક્ષઘાત",                        # stroke / paralysis
    r"બહુ લોહી", r"લોહી વહે",                    # heavy bleeding
    # --- Malayalam (SAFE-LANG-1, provisional — native review recommended) ---
    r"നെഞ്ച.{0,4}വേദന",                         # chest pain
    r"ഹൃദയാഘാത", r"ഹാർട്ട്.{0,4}അറ്റാക്ക്",     # heart attack
    r"ശ്വാസം.{0,8}(കിട്ട|മുട്ട|ഇല്ല|തടസ)",      # can't breathe
    r"വീണു", r"വീണ് പോയി",                       # fell (ml sugar drop uses കുറഞ്ഞു)
    r"ബോധം കെട്ട", r"അബോധ",                     # unconscious
    r"പക്ഷാഘാത", r"തളർവാത",                     # stroke / paralysis
    r"ധാരാളം രക്ത", r"രക്തസ്രാവ",                # heavy bleeding
]

# Low blood sugar. Kept separate from MEDICAL_EMERGENCY because the correct
# first action is glucose, not an ambulance — and many users on medication
# reminders are diabetic, so this is a likely event rather than an edge case.
# Severe cases (unconscious, cannot swallow) match the emergency patterns above,
# which run first.
_HYPOGLYCEMIA = [
    r"sugar (gir|kam|low) (gaya|gayi|ho)", r"sugar low", r"low sugar",
    r"\bhypoglycemia\b", r"\bhypoglycaemia\b", r"sugar bahut kam",
    r"chakkar.{0,20}pasina", r"pasina.{0,20}chakkar",
    r"haath (kaanp|kamp).{0,20}sugar", r"sugar.{0,20}haath (kaanp|kamp)",
    r"shaky.{0,15}sweat", r"sweating.{0,15}shak",
    # Gujarati / Malayalam (SAFE-LANG-1, provisional)
    r"(સુગર|બ્લડ સુગર).{0,8}(ઓછી|ઓછું|ઘટી|ઘટ|લો)",
    r"(പഞ്ചസാര|ഷുഗർ|ഗ്ലൂക്കോസ്).{0,8}(കുറഞ്ഞ|കുറവ്|താഴ്ന്ന|ലോ)",
]

_SELF_HARM = [
    r"marna chahta", r"marna chahti", r"jeene ka mann nahi", r"jeena nahi chahta",
    r"khudkushi", r"aatmhatya", r"\bsuicide\b", r"kill myself", r"end my life",
    r"khatam kar du[ni]?", r"no reason to live",
    # Gujarati / Malayalam (SAFE-LANG-1, provisional)
    r"મરવું છે", r"મરી જવું", r"જીવવું નથી", r"જીવવાની ઇચ્છા નથી",
    r"આપઘાત", r"આત્મહત્યા",
    r"മരിക്കണം", r"മരിക്കാൻ.{0,8}തോന്ന", r"ജീവിക്കാൻ.{0,10}(തോന്നുന്നില്ല|വയ്യ|ഇഷ്ടമില്ല)",
    r"ആത്മഹത്യ", r"ജീവിതം അവസാനിപ്പിക്ക",
]

_MEDICAL_ADVICE = [
    r"kitni goli", r"kitne mg", r"dose kitn", r"dawa badal", r"davai badal",
    r"should i (take|stop)", r"\bincrease\b.*\bdose\b", r"\bstop taking\b",
    r"goli band kar", r"is (it|this) safe to take", r"can i take .* with",
    # Gujarati / Malayalam (SAFE-LANG-1, provisional)
    r"કેટલી ગોળી", r"દવા બદલ", r"ગોળી બંધ", r"ડોઝ.{0,6}(કેટલો|વધાર|ઘટાડ)",
    r"എത്ര ഗുളിക", r"മരുന്ന്.{0,4}മാറ്റ", r"ഗുളിക.{0,4}നിർത്ത", r"ഡോസ്.{0,6}(കൂട്ട|കുറയ്ക്ക)",
]

_SCAM = [
    # Digital arrest: fraudsters posing as CBI/police/ED over a video call.
    # No Indian agency conducts an arrest or demands money over WhatsApp.
    r"digital arrest", r"cbi se baat", r"police video call",
    r"girftar kar l", r"parcel mein drug", r"court se warrant",
    r"\bed\b.{0,15}(notice|case)", r"money laundering case",
    r"\botp\b", r"one time password", r"\bpin\b.*(bat|share|send|de do)",
    r"\bcvv\b", r"lottery", r"lucky draw", r"\bkbc\b", r"crore jeet",
    r"account (block|band)", r"kyc update", r"click (this|is) link",
    r"paisa transfer kar", r"send money urgently",
    # Gujarati / Malayalam native pressure (OTP/PIN/KYC/link/lottery above are
    # Latin and already catch for everyone). SAFE-LANG-1, provisional.
    r"ગિરફ્તાર", r"પૈસા.{0,8}(મોકલ|ટ્રાન્સફર|ભરો|મોકલો)", r"ખાતું બંધ",
    r"તાત્કાલિક.{0,8}પૈસા", r"વોરંટ",
    r"അറസ്റ്റ്", r"പണം.{0,8}(അയക്ക|ട്രാൻസ്ഫർ|അടയ്ക്ക)", r"അക്കൗണ്ട്.{0,6}(ബ്ലോക്ക്|അടച്ച)",
    r"അടിയന്തിര.{0,10}പണം", r"വാറന്റ്",
]

# These are pressure-shaped fraud pretexts rather than proof that every sender
# is malicious.  They still stop the model: a warm deterministic warning and
# one safe verification step is safer than letting a plausible scam persuade a
# user through an open-ended conversation.
_SUSPICIOUS = [
    # Courier, customs and police/case threats.
    r"(?:courier|parcel|delivery).{0,35}(?:customs|duty|hold|fee|fine|police)",
    r"(?:customs|custom).{0,35}(?:parcel|duty|fee|fine|release)",
    r"(?:police|thana|crime branch).{0,35}(?:case|fine|payment|urgent)",
    # Electricity disconnection pressure.
    r"(?:bijli|electricity|power).{0,35}(?:kat|band|disconnect|cut|bill due)",
    r"(?:bill due|outstanding bill).{0,25}(?:bijli|electricity|power)",
    # Loan/investment/lottery-style guaranteed-money bait.
    r"(?:loan|credit).{0,35}(?:release|approve|processing fee|advance fee)",
    r"(?:guaranteed|double).{0,25}(?:return|profit|money|paisa)",
    r"(?:investment|invest).{0,35}(?:guaranteed|quick profit|double|return)",
    # Fake job and pension "verification" / fee demands.
    r"(?:job|naukri|recruitment).{0,35}(?:registration fee|processing fee|offer letter|deposit)",
    r"(?:pension|pensioner).{0,35}(?:update|verify|band|stop|kyc)",
    # UPI collection pressure and remote-control software.
    r"(?:upi|gpay|phonepe|paytm).{0,35}(?:collect|request|approve|urgent|pay now)",
    r"(?:anydesk|teamviewer|quick support|quicksupport|remote access|screen share)",
    # Gujarati / Malayalam native pressure (SAFE-LANG-1, provisional). AnyDesk/UPI
    # brand names above are Latin and catch for everyone.
    r"વીજળી.{0,10}(કપાઈ|કપાશે|બંધ|કાપ|ડિસ્કનેક્ટ)",   # electricity cut-off threat
    r"કુરિયર.{0,30}(કસ્ટમ|પાર્સલ|ફી|દંડ|પોલીસ)",       # courier/customs
    r"વૈദ്യുതി.{0,12}(വിച്ഛേദ|കട്ട്|നിർത്ത|ബന്ധിപ്പിക്കും)",
    r"കറന്റ്.{0,6}കട്ട്",
    r"കൊറിയർ.{0,30}(കസ്റ്റം|പാർസൽ|ഫീസ്|പിഴ|പോലീസ്)",
]

_COMPILED: dict[Trigger, list[re.Pattern[str]]] = {
    Trigger.MEDICAL_EMERGENCY: [re.compile(p, re.I) for p in _EMERGENCY],
    Trigger.SELF_HARM: [re.compile(p, re.I) for p in _SELF_HARM],
    Trigger.HYPOGLYCEMIA: [re.compile(p, re.I) for p in _HYPOGLYCEMIA],
    Trigger.MEDICAL_ADVICE: [re.compile(p, re.I) for p in _MEDICAL_ADVICE],
    Trigger.SCAM: [re.compile(p, re.I) for p in _SCAM],
    Trigger.SUSPICIOUS: [re.compile(p, re.I) for p in _SUSPICIOUS],
}

# Order matters: a message can look like several things at once, and we always
# want the most urgent reading. "seene mein dard, kitni goli lu" is an emergency.
_PRIORITY = [
    Trigger.MEDICAL_EMERGENCY,   # unconscious / chest pain / stroke wins outright
    Trigger.SELF_HARM,
    Trigger.HYPOGLYCEMIA,        # before MEDICAL_ADVICE: "sugar low" is not a dosage question
    Trigger.SCAM,
    Trigger.SUSPICIOUS,
    Trigger.MEDICAL_ADVICE,
]

# --- replies ----------------------------------------------------------------
# Plain, short, no hedging, action first. Never "I am only an AI, but...".

_REPLIES = {
    Trigger.MEDICAL_EMERGENCY: (
        "यह इमरजेंसी हो सकती है। अभी 112 या 108 पर कॉल कीजिए, "
        "और घर में किसी को तुरंत बुलाइए।\n\n"
        "This may be an emergency. Please call 112 or 108 now, and call "
        "someone at home to be with you."
    ),
    Trigger.SELF_HARM: (
        "आप अकेले नहीं हैं, और मैं आपकी बात सुन रही हूँ। "
        "कृपया अभी Tele-MANAS 14416 पर बात कीजिए — वे 24 घंटे उपलब्ध हैं।\n\n"
        "You are not alone. Please talk to someone now: Tele-MANAS 14416, "
        "or KIRAN 1800-599-0019. Both are free and open all day and night."
    ),
    Trigger.HYPOGLYCEMIA: (
        "अभी तुरंत कुछ मीठा खाइए — चीनी, ग्लूकोज़, जूस या दो-तीन "
        "टॉफ़ी। फिर 15 मिनट बाद दोबारा शुगर जाँच कीजिए।\n\n"
        "अगर बेहोशी जैसा लगे, बोलने में दिक्कत हो, या ठीक न लगे — 112 पर "
        "कॉल कीजिए और घर में किसी को अभी बुलाइए।\n\n"
        "_Eat or drink something sugary right now — sugar, glucose, juice. Check "
        "again after 15 minutes. If you feel faint, confused, or it does not "
        "improve, call 112 and get someone to come to you._"
    ),
    Trigger.MEDICAL_ADVICE: (
        "दवा की मात्रा या बदलाव के बारे में मैं सलाह नहीं दे सकती — "
        "यह सिर्फ़ आपके डॉक्टर बता सकते हैं। "
        "मैं आपको दवा लेने का रिमाइंडर ज़रूर लगा सकती हूँ।\n\n"
        "I can't advise on doses or changing medicines — only your doctor can. "
        "I can set a reminder for you, though."
    ),
    Trigger.SCAM: (
        "सावधान — यह संदेश धोखा हो सकता है। "
        "अपना OTP, PIN या बैंक डिटेल किसी को मत बताइए, चाहे वह बैंक से होने का "
        "दावा करे। किसी लिंक पर क्लिक मत कीजिए।\n\n"
        "कोई भी असली पुलिस, CBI या बैंक WhatsApp वीडियो कॉल पर गिरफ़्तारी की "
        "बात नहीं करता। यह सब झूठ होता है।\n\n"
        "अगर पैसे चले गए हैं — *1930* पर तुरंत कॉल कीजिए (साइबर फ्रॉड "
        "हेल्पलाइन), और घर में किसी को अभी बताइए।\n\n"
        "Careful — this looks like a scam. Never share your OTP, PIN or bank "
        "details, even if the caller says they are from the bank or the police. "
        "No real agency arrests anyone over a video call. If money has already "
        "gone, call 1930 immediately."
    ),
    Trigger.SUSPICIOUS: (
        "सावधान — यह दबाव डालने वाला संदेश धोखा हो सकता है। कोई पैसा मत भेजिए, "
        "लिंक मत खोलिए और कोई ऐप इंस्टॉल या स्क्रीन शेयर मत कीजिए। उस संस्था का "
        "आधिकारिक नंबर/ऐप खुद ढूँढकर वहीं से जाँच कीजिए।\n\n"
        "Careful — this pressure message may be a scam. Do not pay, open its link, "
        "install an app, or share your screen. Find the organisation's official "
        "number or app yourself and verify there. If money has gone, call 1930 now."
    ),
}


def _normalise(text: str) -> str:
    """Fold to a comparable form: NFKC, lowercase, collapse whitespace.

    Devanagari and Latin both survive this; it mainly kills the zero-width and
    combining-character tricks that a forwarded scam message may carry.
    """
    text = unicodedata.normalize("NFKC", text or "")
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("Cf"))
    return re.sub(r"\s+", " ", text).strip().lower()


def classify(text: str) -> Verdict:
    """Return the most urgent trigger present, or an empty verdict."""
    norm = _normalise(text)
    if not norm:
        return Verdict(None)
    for trigger in _PRIORITY:
        for pattern in _COMPILED[trigger]:
            m = pattern.search(norm)
            if m:
                return Verdict(trigger, m.group(0), _REPLIES[trigger])
    return Verdict(None)
