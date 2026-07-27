"""Understanding what an elder photographs or forwards.

This is the capability people actually want: *"what does this say?"* — a
prescription, a bank letter, a strip of tablets, a forwarded PDF, a bill in
English when they read Hindi.

Model choice is not arbitrary. `zai.glm-5` has no vision at all, and the
Anthropic vision models here are `global.`-only, which would send photographs of
someone's prescription out of India. `qwen.qwen3-vl-235b-a22b` is a **regional**
ap-south-1 model and read a test image correctly, so images stay in the country
for the same reason text does (decision D-D).

**Every health-adjacent answer carries a disclaimer, by construction.** Not
because the prompt asks for one — the caller cannot get an answer without it,
because `describe_medicine` returns the disclaimer attached to the text. PRD §12
draws a hard line at advice: naming what is printed on a box is information;
saying whether to take it, or how much, is advice, and we never cross it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import boto3

from .config import settings

log = logging.getLogger("saathi.vision")

#: Regional ap-south-1 vision model — images stay in India.
VISION_MODEL = "qwen.qwen3-vl-235b-a22b"

#: The model's own ceiling, and the same number the download is capped at, so a
#: photo cannot be fetched under one limit and then refused by another (PR-26).
MAX_IMAGE_BYTES = settings.saathi_max_image_bytes

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
    return _client


# --- disclaimers -------------------------------------------------------------
# Bilingual, and phrased as a reason rather than a legal shield: "check with your
# doctor" is advice an elder can act on; "we accept no liability" is not.

MEDICINE_DISCLAIMER = (
    "⚠️ *Yeh sirf jaankari hai, salah nahi.* Main sirf woh padh sakti hoon jo "
    "dabbe par likha hai. Kaunsi dawa leni hai, kitni leni hai — yeh sirf aapke "
    "doctor ya chemist bata sakte hain. Dawa lene se pehle unse zaroor "
    "poochhiye.\n"
    "_This is information, not advice. I can only read what is printed on the "
    "pack. Always check with your doctor or pharmacist before taking anything._"
)

DOCUMENT_DISCLAIMER = (
    "_Maine yeh document padhne ki koshish ki hai. Zaroori kaagaz ke liye kisi "
    "bharose ke vyakti se bhi confirm kar lijiye._\n"
    "_I've read this as carefully as I can. For anything important, please have "
    "someone you trust check it too._"
)

MONEY_DISCLAIMER = (
    "⚠️ *Kisi ko OTP, PIN ya bank details mat bataiye* — chahe woh bank se hone "
    "ka daava kare. Main kabhi nahi maangungi.\n"
    "_Never share an OTP, PIN or bank details with anyone, even if they say they "
    "are from the bank._"
)


@dataclass
class Reading:
    text: str
    disclaimer: str | None = None
    kind: str = "general"

    def rendered(self) -> str:
        """What the user actually sees. The disclaimer cannot be dropped."""
        return f"{self.text}\n\n{self.disclaimer}" if self.disclaimer else self.text


def _fmt(mime: str | None) -> str:
    m = (mime or "").lower()
    for f in ("png", "jpeg", "webp", "gif"):
        if f in m:
            return f
    if "jpg" in m:
        return "jpeg"
    return "jpeg"


async def _ask(prompt: str, image: bytes, mime: str | None, max_tokens: int = 500) -> str:
    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError("image too large")
    resp = client().converse(
        modelId=VISION_MODEL,
        messages=[{"role": "user", "content": [
            {"image": {"format": _fmt(mime), "source": {"bytes": image}}},
            {"text": prompt},
        ]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.1},
    )
    return "".join(b.get("text", "") for b in resp["output"]["message"]["content"]).strip()


# --- the four things people actually send -----------------------------------

async def describe_medicine(image: bytes, mime: str | None = None) -> Reading:
    """Read a medicine pack. Names what is printed; never advises."""
    text = await _ask(
        "This is a photo of a medicine pack or strip sent by an older adult in India.\n"
        "Read ONLY what is printed on it and report:\n"
        "- the medicine name exactly as printed, in Latin script\n"
        "- the strength if printed (e.g. 5mg)\n"
        "- the expiry date if visible\n"
        "- what this type of medicine is generally for, in one short plain sentence\n\n"
        "Do NOT say whether to take it, when, or how much. Do NOT suggest any "
        "change. If the photo is unclear, say so and ask for a clearer picture of "
        "the front of the pack.\n"
        "Reply in simple Hinglish, short lines, no markdown.",
        image, mime)
    return Reading(text, MEDICINE_DISCLAIMER, "medicine")


async def read_document(image: bytes, mime: str | None = None,
                        question: str | None = None) -> Reading:
    """A letter, bill, report or notice — photographed or a PDF page."""
    ask = question or "What does this say? Summarise the important parts."
    text = await _ask(
        "This is a document an older adult in India has received and wants "
        f"explained. The person asks: {ask!r}\n\n"
        "Explain in simple Hinglish, short lines. Lead with what it is and what "
        "if anything they need to DO, then any date or deadline, then any amount. "
        "If it asks for money, an OTP, a PIN or bank details, say clearly that "
        "this is a common scam pattern. Do not invent anything not visible.",
        image, mime, max_tokens=700)
    low = text.lower()
    money = any(w in low for w in ("otp", "pin", "bank", "payment", "upi", "account"))
    return Reading(text, MONEY_DISCLAIMER if money else DOCUMENT_DISCLAIMER, "document")


async def describe_image(image: bytes, mime: str | None = None,
                         question: str | None = None) -> Reading:
    """Anything else — a photo, a screenshot, a forwarded picture."""
    ask = question or "What is in this picture?"
    text = await _ask(
        f"An older adult in India sent this picture and asks: {ask!r}\n"
        "Describe it simply and warmly in Hinglish, in a few short lines. "
        "If it is a message or screenshot asking for money, an OTP or bank "
        "details, warn them it looks like a scam.",
        image, mime)
    low = text.lower()
    return Reading(text,
                   MONEY_DISCLAIMER if any(w in low for w in ("otp", "pin", "bank", "scam"))
                   else None, "image")


def classify_intent(caption: str | None) -> str:
    """Pick the reading mode from whatever the user typed with the picture."""
    c = (caption or "").lower()
    if any(w in c for w in ("dawa", "goli", "medicine", "tablet", "davai", "capsule")):
        return "medicine"
    if any(w in c for w in ("padho", "padh", "likha", "read", "kya likha",
                            "samjha", "explain", "document", "letter", "bill")):
        return "document"
    return "image"
