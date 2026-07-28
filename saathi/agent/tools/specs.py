"""Tool definitions for the agent loop.

The safety property in PRD §12 is *structural*: prompt injection via a
forwarded message cannot cause harm because no tool can move money, read an
OTP, or touch a third-party account. That guarantee lives here — in what is
absent from this list — not in the system prompt. Keep it that way.

Descriptions are terse on purpose: they are part of the cacheless prefix and
are re-sent on every turn (plan §5c).
"""
from __future__ import annotations

TOOLS: list[dict] = [
    {
        "toolSpec": {
            "name": "create_reminder",
            "description": (
                "Create a reminder. Use for medicines, appointments, tasks. "
                "Keep medicine names in Latin script exactly as spoken."
            ),
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "what to remind about"},
                    "time_24h": {"type": "string", "description": "HH:MM, 24-hour"},
                    "recurrence": {
                        "type": "string",
                        "description": "daily | weekly:mon..sun | monthly:<day> | once",
                    },
                    "date": {"type": "string", "description": "YYYY-MM-DD, only if recurrence=once"},
                },
                "required": ["title", "time_24h", "recurrence"],
            }},
        }
    },
    {
        "toolSpec": {
            "name": "list_reminders",
            "description": "List the user's active reminders.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "cancel_reminder",
            "description": "Cancel a reminder by its id, as shown by list_reminders.",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {"reminder_id": {"type": "integer"}},
                "required": ["reminder_id"],
            }},
        }
    },
    {
        "toolSpec": {
            "name": "remember",
            "description": (
                "Store a durable fact about the user: people, medicines, places, "
                "brands, preferences, routines. Store medicine and people names "
                "in Latin script."
            ),
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["person", "medicine", "place", "brand",
                                 "preference", "routine", "other"],
                    },
                    "key": {"type": "string", "description": "short label, e.g. 'doctor'"},
                    "value": {"type": "string"},
                },
                "required": ["kind", "key", "value"],
            }},
        }
    },
    {
        "toolSpec": {
            "name": "forget",
            "description": "Delete a stored fact by its key. Use when the user asks you to forget.",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            }},
        }
    },
    {
        "toolSpec": {
            "name": "build_cart",
            "description": (
                "Compile a numbered shopping list plus India-first provider "
                "search/deeplink handoffs. Does NOT order, book or pay."
            ),
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "string"}},
                    "note": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["grocery", "food", "events", "travel"],
                        "description": "grocery by default; food/restaurants, events/movies, or travel",
                    },
                },
                "required": ["items"],
            }},
        }
    },
    {
        "toolSpec": {
            "name": "what_you_know",
            "description": (
                "List everything stored about the user. Use when they ask what "
                "you know or remember about them."
            ),
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    },
    {
        "toolSpec": {
            "name": "forget_everything",
            "description": (
                "Permanently delete everything stored about the user. Only after "
                "they clearly ask, and only after you have confirmed once."
            ),
            "inputSchema": {"json": {
                "type": "object",
                "properties": {"confirmed": {"type": "boolean"}},
                "required": ["confirmed"],
            }},
        }
    },
    {
        "toolSpec": {
            "name": "set_preference",
            "description": "Change how the assistant behaves: voice replies on/off, language.",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "voice_replies": {"type": "string", "enum": ["auto", "always", "never"]},
                    "language": {"type": "string", "description": "hi | en | hi-en"},
                },
            }},
        }
    },
    {
        "toolSpec": {
            "name": "look_up",
            "description": (
                "Look something up in the world: today's weather, or a factual "
                "question about a person, place or thing. Use when the answer "
                "depends on current or external information you cannot know. "
                "Does NOT browse arbitrary websites."
            ),
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "what to look up"},
                    "kind": {"type": "string", "enum": ["weather", "fact", "web"],
                             "description": "weather for forecasts, fact for who/what questions"},
                },
                "required": ["query", "kind"],
            }},
        }
    },
    {
        "toolSpec": {
            "name": "snooze_reminder",
            "description": "Push a reminder later by N minutes when the user taps snooze.",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {"reminder_id": {"type": "integer"},
                               "minutes": {"type": "integer"}},
                "required": ["reminder_id", "minutes"],
            }},
        }
    },
]

TOOL_CONFIG = {"tools": TOOLS}

# Deliberately absent, and must stay absent (PRD §12):
#   pay / transfer / place_order / book / read_otp / login / open_account
FORBIDDEN_TOOL_NAMES = frozenset({
    "pay", "make_payment", "transfer_money", "place_order", "checkout",
    "book_flight", "read_otp", "get_otp", "login", "open_account",
    # Added 2026-07-27 with the paywall. Saathi *can* now send an invoice, but
    # only `capabilities._paywall_handle` may, for one fixed price, in reply to
    # a message from an account that is out of allowance. Keeping these names
    # forbidden is what stops the next lane exposing it to the model, where a
    # forwarded scam could talk it into billing someone.
    "send_invoice", "request_payment", "order_details", "charge", "refund",
})


def assert_no_forbidden_tools() -> None:
    """Guard against a future commit quietly adding a transactional capability."""
    names = {t["toolSpec"]["name"] for t in TOOLS}
    bad = names & FORBIDDEN_TOOL_NAMES
    if bad:
        raise AssertionError(f"transactional tools are forbidden by PRD §12: {sorted(bad)}")
