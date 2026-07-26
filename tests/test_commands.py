"""Inline commands must be unambiguous and must never steal a real task."""
import pytest
from saathi.commands import parse, Command as C


@pytest.mark.parametrize("text,cmd", [
    ("forget everything about me", C.DELETE_ALL),
    ("sab kuch bhool jao", C.DELETE_ALL),
    ("mera data delete karo", C.DELETE_ALL),
    ("clear this chat", C.CLEAR_CHAT),
    ("what do you know about me", C.WHAT_YOU_KNOW),
    ("mere baare mein kya jaante ho", C.WHAT_YOU_KNOW),
    ("stop", C.STOP),
    ("band karo", C.STOP),
    ("help", C.HELP),
    ("namaste", C.START),
    ("/delete", C.DELETE_ALL),
    ("/stop", C.STOP),
])
def test_recognised(text, cmd):
    assert parse(text).command is cmd


@pytest.mark.parametrize("text", [
    "roz subah aath baje amlodipine ka reminder laga do",
    "can you help me set a reminder",          # contains 'help' — still a task
    "mujhe doodh aur atta chahiye",
    "aaj mausam kaisa hai",
    "mere doctor Dr Mehta hain",
    "stop the reminder for telmisartan",       # a task about stopping, not STOP
    "",
])
def test_real_tasks_are_not_swallowed(text):
    assert parse(text).command is None, f"{text!r} was wrongly taken as a command"


def test_bare_help_only():
    assert parse("help").command is C.HELP
    assert parse("help me remember my medicine").command is None


def test_erasure_works_without_the_model():
    """A DPDP erasure request must not depend on Bedrock being reachable."""
    assert parse("forget everything").command is C.DELETE_ALL
