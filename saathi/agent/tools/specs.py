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
                "Compile a numbered shopping list the user can read or forward. "
                "Does NOT order or pay for anything."
            ),
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "string"}},
                    "note": {"type": "string"},
                },
                "required": ["items"],
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
})


def assert_no_forbidden_tools() -> None:
    """Guard against a future commit quietly adding a transactional capability."""
    names = {t["toolSpec"]["name"] for t in TOOLS}
    bad = names & FORBIDDEN_TOOL_NAMES
    if bad:
        raise AssertionError(f"transactional tools are forbidden by PRD §12: {sorted(bad)}")
