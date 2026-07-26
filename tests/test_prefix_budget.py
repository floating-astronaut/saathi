"""The prefix budget is the cost control now that there is no prompt caching."""
import pytest
from saathi.agent.prompt import build_prefix, estimate_tokens, PrefixTooLarge
from saathi.agent.tools.specs import assert_no_forbidden_tools


def test_devanagari_costs_more_than_latin_per_char():
    # A naive len//4 estimate would under-count Hindi badly.
    assert estimate_tokens("अ" * 100) > estimate_tokens("a" * 100)


def test_realistic_prefix_fits_budget():
    facts = [("doctor", "Dr Mehta, Apollo"), ("medicine", "Amlodipine 5mg"),
             ("daughter", "Priya, Pune"), ("city", "Nagpur")]
    p = build_prefix(facts, tool_tokens=600, budget=3000)
    assert p.tokens < 3000


def test_oversized_fact_block_raises_rather_than_silently_costing_money():
    facts = [(f"key{i}", "x" * 400) for i in range(40)]
    with pytest.raises(PrefixTooLarge):
        build_prefix(facts, tool_tokens=600, budget=3000)


def test_no_transactional_tools_exist():
    assert_no_forbidden_tools()
