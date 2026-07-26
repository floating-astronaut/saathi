"""The capability chain is the architecture. These tests protect its properties."""
import pytest
from saathi import capabilities  # noqa: F401 - registers the chain
from saathi.core import handlers
from saathi.core.context import MessageContext


def _names():
    return [h.name for h in handlers.registered()]


def test_registration_is_ordered_by_priority_not_import_order():
    prios = [h.priority for h in handlers.registered()]
    assert prios == sorted(prios)


def test_safety_cannot_be_overtaken():
    """R7: nothing may run before the deterministic classifier."""
    hs = handlers.registered()
    assert hs[0].name == "safety" and hs[0].priority == 0


def test_agent_is_the_catch_all_and_runs_last():
    hs = handlers.registered()
    assert hs[-1].name == "agent"
    assert hs[-1].priority >= 90


def test_onboarding_precedes_commands_and_agent():
    n = _names()
    assert n.index("onboarding") < n.index("commands") < n.index("agent")


def test_media_precedes_the_agent():
    n = _names()
    assert n.index("media") < n.index("agent")


def test_every_handler_declares_the_protocol():
    for h in handlers.registered():
        assert isinstance(h.name, str) and isinstance(h.priority, int)
        assert callable(h.matches) and callable(h.handle)


def test_duplicate_names_are_refused():
    """Two capabilities silently sharing a name is how ordering bugs hide."""
    with pytest.raises(ValueError):
        handlers.register(handlers.simple("agent", 95, lambda c: True, None))


async def test_a_broken_capability_does_not_take_down_the_turn():
    """One bad handler must not stop a user asking about their medicine."""
    saved = handlers.registered()
    handlers.clear()
    calls = []

    def boom_match(ctx): raise RuntimeError("matches exploded")
    async def boom_handle(ctx): raise RuntimeError("handle exploded")
    async def ok(ctx): calls.append("ok"); return {"handled": "ok"}

    handlers.register(handlers.simple("boom_match", 1, boom_match, boom_handle))
    handlers.register(handlers.simple("boom_handle", 2, lambda c: True, boom_handle))
    handlers.register(handlers.simple("good", 3, lambda c: True, ok))
    try:
        ctx = MessageContext(conn=None, transport=None, channel="whatsapp", handle="1",
                             msg={}, user_id=1, display_name=None, tz="Asia/Kolkata",
                             voice_pref="auto", onboarding="done", text="hi")
        out = await handlers.dispatch(ctx)
        assert out["handled"] == "ok" and out["handler"] == "good"
        assert calls == ["ok"]
    finally:
        handlers.clear()
        for h in saved:
            handlers.register(h)


async def test_nothing_matched_is_reported_not_crashed():
    saved = handlers.registered()
    handlers.clear()
    try:
        ctx = MessageContext(conn=None, transport=None, channel="whatsapp", handle="1",
                             msg={}, user_id=1, display_name=None, tz="Asia/Kolkata",
                             voice_pref="auto", onboarding="done", text="hi")
        assert (await handlers.dispatch(ctx))["handled"] == "nothing"
    finally:
        handlers.clear()
        for h in saved:
            handlers.register(h)


def test_adding_a_capability_needs_no_pipeline_edit():
    """The architectural claim, asserted: registration is the whole API."""
    import inspect
    from saathi import pipeline
    src = inspect.getsource(pipeline.handle_message)
    # the dispatcher must not name individual capabilities
    for feature in ("classify(", "onboarding.begin", "commands.parse", "vision."):
        assert feature not in src, f"pipeline still hardcodes {feature!r}"
