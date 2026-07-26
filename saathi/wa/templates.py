"""WhatsApp message templates, as code.

Templates are the week-1 critical path: Meta's review takes days and nothing
else can be parallelised around it. Keeping them versioned here (rather than
clicked into Business Manager) means the copy is reviewable, diffable, and
re-submittable after a rejection without anyone remembering what we sent.

Rules encoded here, learned from Meta's rejection patterns:
  * UTILITY only. Marketing is 7.5x the cost and wrong for reminders anyway.
  * A body may not start or end with a variable -- instant rejection.
  * Quick-reply button labels: 20 characters hard limit.
  * A template's job is not to say everything. It is to GET A REPLY, which
    reopens the free 24-hour window (PRD s11).
  * **Never delete a template to fix it.** Meta holds a deleted name for up to
    four weeks before it can be recreated, and the category cannot be changed
    while the old content is still deleting. reminder_fire/reminder_nudge were
    lost this way; the live ones are the _v2 names. Submit a new name instead.

Copy rules from PRD s6, which matter more here than anywhere else because
this is the text an elder sees cold, with no conversational context:
  * Never signal repetition. No "you missed yesterday's", no "reminder again".
  * One question. Warm, plain, short.
"""
from __future__ import annotations

TEMPLATES: list[dict] = [
    {
        "name": "reminder_fire_v2",
        "language": "en",
        "category": "UTILITY",
        "components": [
            # Meta recategorised the earlier copy ("Namaste! {{1}} ka time ho gaya
            # hai") as MARKETING at 7.5x the price. UTILITY requires the message
            # to visibly follow from something the user themselves requested, so
            # the body now points at their own prior action.
            {"type": "BODY",
             "text": "Aapne jo reminder set kiya tha \u2014 {{1}} ka time ho gaya hai.",
             "example": {"body_text": [["Amlodipine ki goli lene"]]}},
            {"type": "BUTTONS", "buttons": [
                {"type": "QUICK_REPLY", "text": "Ho gaya"},
                {"type": "QUICK_REPLY", "text": "15 min baad"},
            ]},
        ],
    },
    {
        # Deliberately NOT "you missed it". A gentle check, never a reproach.
        "name": "reminder_nudge_v2",
        "language": "en",
        "category": "UTILITY",
        "components": [
            {"type": "BODY",
             "text": "Aapke reminder ke baare mein: kya aapne {{1}} kar liya?",
             "example": {"body_text": [["Amlodipine ki goli lena"]]}},
            {"type": "BUTTONS", "buttons": [
                {"type": "QUICK_REPLY", "text": "Ho gaya"},
                {"type": "QUICK_REPLY", "text": "Abhi karta hoon"},
            ]},
        ],
    },
    {
        # Utility-shaped on purpose: a bare "how can I help?" reads as MARKETING
        # to Meta's reviewers and gets recategorised at 7.5x the price.
        "name": "daily_checkin",
        "language": "en",
        "category": "UTILITY",
        "components": [
            {"type": "BODY",
             "text": "Namaste! Aaj aapke {{1}} reminder set hain. Kuch aur jodna hai?",
             "example": {"body_text": [["3"]]}},
            {"type": "BUTTONS", "buttons": [
                {"type": "QUICK_REPLY", "text": "Haan"},
                {"type": "QUICK_REPLY", "text": "Nahi, theek hai"},
            ]},
        ],
    },
    {
        "name": "session_resume",
        "language": "en",
        "category": "UTILITY",
        "components": [
            {"type": "BODY",
             "text": "Namaste! Hum {{1}} ke baare mein baat kar rahe the. Aage badhein?",
             "example": {"body_text": [["dawa ka reminder"]]}},
            {"type": "BUTTONS", "buttons": [
                {"type": "QUICK_REPLY", "text": "Haan, chaliye"},
                {"type": "QUICK_REPLY", "text": "Baad mein"},
            ]},
        ],
    },
]


def validate() -> list[str]:
    """Catch the rejection causes we can catch locally, before Meta does."""
    problems: list[str] = []
    for t in TEMPLATES:
        if t["category"] != "UTILITY":
            problems.append(f"{t['name']}: category must be UTILITY")
        body = next(c for c in t["components"] if c["type"] == "BODY")["text"]
        if body.strip().startswith("{{"):
            problems.append(f"{t['name']}: body starts with a variable")
        if body.strip().endswith("}}"):
            problems.append(f"{t['name']}: body ends with a variable")
        for c in t["components"]:
            for b in c.get("buttons", []):
                if len(b["text"]) > 20:
                    problems.append(f"{t['name']}: button '{b['text']}' exceeds 20 chars")
        for bad in ("missed", "bhool", "phir se", "again"):
            if bad in body.lower():
                problems.append(f"{t['name']}: copy signals repetition ('{bad}') - PRD s6.5")
    return problems
