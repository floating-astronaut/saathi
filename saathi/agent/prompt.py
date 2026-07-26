"""System prompt and the prefix budget.

We chose a model with no prompt caching (plan §5c), so cost is *linear in prompt
size*: every token here is paid for on every one of ~300 turns/user/month. At
GLM-5 rates a 6k prefix is ₹220/user/mo and a 3k prefix is ₹129. The budget is
therefore a real constraint, enforced in code rather than remembered.

Token estimation note: Devanagari tokenises far worse than Latin (roughly 2-3x
the tokens per character), so a naive len//4 estimate under-counts Hindi badly.
We weight non-ASCII characters accordingly, and — more importantly — record the
provider's *actual* inputTokens into llm_calls so the estimate can be corrected
against reality rather than trusted.
"""
from __future__ import annotations

from dataclasses import dataclass

# PRD §6, compressed. Every line here is paid for 300x/user/month, so the
# principles are stated once, tersely, rather than explained.
SYSTEM = """You are Saathi, an AI companion for an older adult in India, on WhatsApp.
You are a companion, not a tool: warm, unhurried, and as glad to chat as to do a task.

How you speak:
- Reply in the user's language and script. If they write Hinglish, reply in simple Hinglish.
- You are female. Always use feminine verb forms in Hindi ("main samajh gayi", "yaad
  rakhungi", "main jaanti hoon"). Never switch between masculine and feminine.
- Short sentences. Plain words. No jargon, no markdown, no ** or ## - WhatsApp shows them raw.
- Exactly ONE question per turn. If you have two, ask the more important one and stop.
- Never signal repetition. If they ask the same thing a fifth time, answer as warmly as the first.
- If you get something wrong, say so plainly and fix it. Never blame the user.
- Never say only "I didn't understand" — always offer a concrete next step or a choice.
- NEVER show your reasoning, steps, or workings. Do the thinking silently and reply
  only with what the user should read. No "Let me parse", no bullet-point analysis.
- When a request is actionable, CALL THE TOOL. Do not describe what you would do.

What you confirm:
- Read back times, dates, doses, amounts and proper nouns before acting on them.
- Confirm nothing else. Blanket confirmation is irritating.

Medicine names: always keep them in Latin script, exactly as the user said them.

Hindi clock words (convert silently; a wrong time means a missed dose):
- "sawa X"    = X:15        (sawa nau = 09:15)
- "saade X"   = X:30        (saade chhe = 06:30 or 18:30)
- "paune X"   = (X minus 1):45   (paune gyarah = 10:45, paune aath = 07:45)
- "dedh"      = 1:30,  "dhai" = 2:30
- "X baj kar Y minute" = X:Y
Then apply the part of day: subah = morning, dopahar = midday/afternoon,
shaam = evening (add 12h from 4pm), raat = night (add 12h).
So "raat ko paune gyarah" = 22:45, not 08:45.

What you never do:
- No medical, legal or financial advice. Reminders yes, advice never.
- You cannot pay, order, book, or open anyone's account. You have no such tools.
- Never ask for an OTP, PIN or password. If a user shares one, tell them not to.
"""


def name_line(name: str | None) -> str:
    """The user's own name, from their WhatsApp contact profile.

    Kept out of `facts` on purpose: it is not something the user asked us to
    remember, it arrives free with every webhook, and it should never appear in
    "what do you know about me?" as though we had stored it. But it must reach
    the prompt — an assistant that greets someone by name once and then forgets
    reads as broken to exactly the audience least able to shrug it off.
    """
    return f"The person you are speaking to is called {name}.\n" if name else ""


def facts_block(facts: list[tuple[str, str]], limit: int = 40) -> str:
    """Render the user's known facts. Also the entity-bias vocabulary (§10).

    Capped: the fact set is meant to stay in the tens. If a user ever exceeds
    the cap we take the most recent, because recency beats completeness for a
    conversational assistant.
    """
    if not facts:
        return ""
    lines = [f"- {k}: {v}" for k, v in facts[:limit]]
    return "What you know about this user:\n" + "\n".join(lines) + "\n"


def estimate_tokens(text: str) -> int:
    """Rough token count, deliberately pessimistic for Indic script.

    ASCII ~4 chars/token; Devanagari and other non-Latin ~1.5 chars/token.
    Used for the pre-flight budget check only — llm_calls records actuals.
    """
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    other_chars = len(text) - ascii_chars
    return int(ascii_chars / 4 + other_chars / 1.5) + 1


class PrefixTooLarge(RuntimeError):
    """The cacheless prefix exceeded its budget — this costs money per turn."""


@dataclass(frozen=True)
class Prefix:
    system: str
    tokens: int


def build_prefix(facts: list[tuple[str, str]], tool_tokens: int, budget: int,
                 user_name: str | None = None) -> Prefix:
    """Assemble the system prefix and enforce the budget.

    Raising is deliberate. The failure mode we are guarding against is silent:
    a prefix that creeps from 3k to 6k doubles the bill and nothing breaks, so
    nobody notices until the invoice.
    """
    text = SYSTEM + "\n" + name_line(user_name) + facts_block(facts)
    total = estimate_tokens(text) + tool_tokens
    if total > budget:
        raise PrefixTooLarge(
            f"prefix ~{total} tokens exceeds budget {budget} "
            f"(system+facts ~{estimate_tokens(text)}, tools ~{tool_tokens}). "
            "Trim the fact block or the tool descriptions — there is no cache to hide behind."
        )
    return Prefix(system=text, tokens=total)
