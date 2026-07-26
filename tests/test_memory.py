"""Memory shape checks that do not need a database."""
from saathi.agent.prompt import facts_block, build_prefix
from saathi.agent.tools.specs import TOOLS


def test_fact_block_renders_and_is_capped():
    facts = [(f"k{i}", f"v{i}") for i in range(100)]
    out = facts_block(facts, limit=40)
    assert out.count("\n- ") == 40 and out.startswith("What you know")


def test_empty_facts_costs_nothing():
    assert facts_block([]) == ""


def test_new_capabilities_present():
    names = {t["toolSpec"]["name"] for t in TOOLS}
    assert {"what_you_know", "forget_everything", "set_preference", "snooze_reminder"} <= names


def test_erasure_tool_requires_confirmation_field():
    spec = next(t["toolSpec"] for t in TOOLS if t["toolSpec"]["name"] == "forget_everything")
    assert spec["inputSchema"]["json"]["required"] == ["confirmed"]


def test_prefix_still_fits_with_bigger_toolset():
    facts = [("doctor", "Dr Mehta"), ("medicine", "Amlodipine 5mg"), ("city", "Nagpur")]
    assert build_prefix(facts, tool_tokens=803, budget=3000).tokens < 3000


def test_bias_forms_extract_names_not_sentences():
    from saathi.agent.tools.handlers import Handlers
    f = Handlers._bias_forms
    assert f("Dr Mehta, Apollo Nagpur") == ["Mehta", "Apollo", "Nagpur"]
    assert f("Priya, Pune mein rehti hai") == ["Priya", "Pune"]
    assert f("Telmisartan 40mg") == ["Telmisartan"]
    # nothing extractable -> keep the raw value rather than storing nothing
    assert f("subah walk") == ["subah walk"]


def test_prompt_forbids_visible_reasoning():
    from saathi.agent.prompt import SYSTEM
    assert "NEVER show your reasoning" in SYSTEM
    assert "CALL THE TOOL" in SYSTEM


def test_persona_gender_is_pinned():
    # An assistant that switches gender mid-conversation is disorienting for
    # this audience; the prompt must state one and only one.
    from saathi.agent.prompt import SYSTEM
    assert "You are female" in SYSTEM and "rakhungi" in SYSTEM
