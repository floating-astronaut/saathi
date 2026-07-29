"""The model's clock, and what happens to `create_reminder` without one.

The bug these guard: a user sent a voice note asking to be reminded in five
minutes, and got asked for a wall-clock time twice instead. The prefix carried
no date, no time and no zone, so "5 minute baad" was not a computation the
model could perform — and for a one-off reminder it would have had to *guess*
`date`, which fires on the wrong day without anything looking broken.

These assertions are written from the contract ("the reply must be timed where
the user lives"), not from the rendering, because five separate bugs have now
shipped here with tests that agreed with the implementation.
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from saathi.agent import loop as agent_loop
from saathi.agent.prompt import build_prefix, clock_line, estimate_tokens
from saathi.agent.tools.specs import TOOLS

KOLKATA = ZoneInfo("Asia/Kolkata")


def _prefix(now_local=None, facts=None):
    return build_prefix(facts or [], agent_loop.tool_tokens(), 3000,
                        now_local=now_local)


class _FakeBedrock:
    """Records the toolConfig it was handed, then ends the turn."""

    def __init__(self):
        self.tool_configs = []
        self.systems = []

    def converse(self, **kw):
        self.tool_configs.append(kw["toolConfig"])
        self.systems.append(kw["system"][0]["text"])
        return {"output": {"message": {"role": "assistant",
                                       "content": [{"text": "theek hai"}]}},
                "usage": {"inputTokens": 1, "outputTokens": 1}}


@pytest.fixture
def bedrock(monkeypatch):
    fake = _FakeBedrock()
    monkeypatch.setattr(agent_loop, "_client", fake)
    return fake


async def _no_tools(name, args):  # pragma: no cover - never called here
    raise AssertionError("no tool should run in these turns")


def _run(tz):
    return asyncio.run(agent_loop.run("yaad dila dena", [], _no_tools, tz=tz))


def _offered(fake):
    return {t["toolSpec"]["name"] for t in fake.tool_configs[0]["tools"]}


# --- the clock says where the user is, not where the server is ---------------

def test_clock_is_the_users_local_time_not_the_servers():
    # One instant, two people. The line must differ, or it is a server clock
    # wearing a user's name.
    instant = datetime(2026, 7, 27, 20, 30, tzinfo=ZoneInfo("UTC"))
    india = clock_line(instant.astimezone(KOLKATA))
    new_york = clock_line(instant.astimezone(ZoneInfo("America/New_York")))
    assert india != new_york
    assert "02:00" in india          # next day, 2am IST
    assert "28 Jul" in india
    assert "16:30" in new_york       # same instant, still the 27th
    assert "27 Jul" in new_york


def test_clock_carries_the_date_so_a_one_off_reminder_need_not_be_guessed():
    p = _prefix(datetime(2026, 7, 27, 14, 5, tzinfo=KOLKATA))
    for fragment in ("2026", "Jul", "27", "14:05", "Asia/Kolkata"):
        assert fragment in p.system, fragment


def test_no_clock_means_no_clock_rather_than_a_default():
    # Inventing a zone would be worse than omitting one: it would be wrong
    # silently, for everyone outside that zone.
    assert clock_line(None) == ""
    assert not _prefix(None).has_clock


# --- it has to stay cheap: there is no prompt caching on this model ----------

def test_the_clock_is_one_line_and_costs_under_25_tokens():
    line = clock_line(datetime(2026, 7, 27, 14, 5, tzinfo=KOLKATA))
    assert line.count("\n") == 1
    assert estimate_tokens(line) < 25


def test_the_clock_does_not_push_a_realistic_prefix_over_budget():
    facts = [("doctor", "Dr Mehta, Apollo"), ("medicine", "Amlodipine 5mg"),
             ("daughter", "Priya, Pune"), ("city", "Nagpur")]
    p = _prefix(datetime(2026, 7, 27, 14, 5, tzinfo=KOLKATA), facts)
    assert p.tokens < 3000


# --- capability by absence: no clock, no create_reminder --------------------

def test_a_turn_with_a_timezone_may_create_reminders(bedrock):
    _run("Asia/Kolkata")
    assert "create_reminder" in _offered(bedrock)


def test_a_turn_without_a_timezone_withholds_create_reminder(bedrock):
    _run(None)
    assert "create_reminder" not in _offered(bedrock)


def test_withholding_create_reminder_does_not_disarm_the_rest(bedrock):
    # The failure to avoid is over-correction: a clockless turn should lose the
    # one tool that needs a date, not the ability to talk or to remember.
    _run(None)
    offered = _offered(bedrock)
    every = {t["toolSpec"]["name"] for t in TOOLS}
    assert offered == every - agent_loop.CLOCK_DEPENDENT_TOOLS


def test_snooze_survives_a_clockless_turn_because_it_takes_an_offset(bedrock):
    _run(None)
    assert "snooze_reminder" in _offered(bedrock)


def test_a_clockless_turn_still_carries_the_system_prompt(bedrock):
    _run(None)
    assert "Indofolk AI" in bedrock.systems[0]
