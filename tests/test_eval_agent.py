"""Agent tool-use eval scoring. The model is never called here — the runner is
faked; live runs happen via `python -m saathi.eval.agent`."""
from saathi.agent.loop import Turn
from saathi.eval import agent


def _turn(text, tools=()):
    return Turn(text=text, tool_calls=[(t, {}) for t in tools])


def _case(**kw):
    base = {"id": "x", "category": "c", "question": "q",
            "expect_tool": None, "expect_contains": [], "should_answer": True}
    base.update(kw)
    return base


def test_good_case_scores_good():
    r = agent.score(_case(expect_tool="look_up", expect_contains=["Carney"]),
                    _turn("The Prime Minister is Mark Carney.", ["look_up"]))
    assert r.tool_ok and r.answer_ok and not r.gave_up and r.good


def test_missing_required_tool_is_not_good():
    r = agent.score(_case(expect_tool="look_up"),
                    _turn("It is Mark Carney.", []))       # answered from memory, no tool
    assert not r.tool_ok and not r.good


def test_giving_up_is_caught():
    for said in ("Sorry, I couldn't find it.",
                 "Mujhe Toronto ka mausam pata nahi kar payi.",
                 "Abhi information nahi hai.",
                 "I don't have access to that."):
        r = agent.score(_case(expect_tool="look_up"), _turn(said, ["look_up"]))
        assert r.gave_up and not r.good, said


def test_a_correct_answer_is_not_a_give_up():
    # regression: "insulin kaam nahi kar paati" explains diabetes — not a surrender
    good = ("Diabetes ek condition hai jismein insulin theek se kaam nahi kar "
            "paati aur blood sugar high ho jaata hai.")
    r = agent.score(_case(expect_tool="look_up"), _turn(good, ["look_up"]))
    assert not r.gave_up


def test_direct_answer_needs_no_tool():
    r = agent.score(_case(expect_tool=None, expect_contains=["42"]),
                    _turn("That's 42.", []))
    assert r.tool_ok and r.answer_ok and r.good


def test_a_tool_call_is_never_penalised_when_none_required():
    # answering "capital of France" via search is fine, not a failure
    r = agent.score(_case(expect_tool=None, expect_contains=["Paris"]),
                    _turn("It is Paris.", ["look_up"]))
    assert r.tool_ok and r.good


async def test_run_aggregates_over_the_case_set():
    cases = [
        _case(id="a", question="pm?", expect_tool="look_up", expect_contains=["Carney"]),
        _case(id="b", question="temp?", expect_tool="look_up"),   # will give up
    ]
    canned = {
        "pm?": _turn("It's Mark Carney.", ["look_up"]),
        "temp?": _turn("Sorry, I couldn't find it.", ["look_up"]),
    }

    async def fake_runner(question, facts, handle_tool, tz, lang):
        return canned[question]

    rep = await agent.run(cases, runner=fake_runner)
    assert rep.n == 2
    assert rep.answered_well == 0.5          # one good, one gave up
    assert rep.give_up_rate == 0.5
    assert "Agent tool-use eval" in agent.render_markdown(rep)
