"""A forwarded message must never drive a deterministic command.

`provenance.py` fences relayed text and withholds mutating *tools* — but the
deterministic command capability runs at priority 22, long before the agent, and
matched on raw text without asking who wrote it.

The concrete failure: STOP matches `\bunsubscribe\b` as a substring, and nearly
every forwarded marketing message carries that word in its footer. Forwarding a
promo set `users.paused = true`, and `worker/turns._handle` silently declines to
send reminders to a paused user. Someone's medication reminders stopped because
a relative forwarded an advert — no error, no bounce, and with the ack path
unreachable (PR-4b) nothing to reveal it.

The product rule is that relayed content may be read, explained or warned about,
but never obeyed.
"""
from saathi import capabilities  # noqa: F401 - registers the chain
from saathi.core import handlers
from saathi.core.context import MessageContext


def _ctx(text: str, provenance: str = "typed", **kw) -> MessageContext:
    return MessageContext(
        conn=None, transport=None, channel="whatsapp", handle="+911",
        msg=kw.pop("msg", {}), user_id=1, display_name=None, tz="Asia/Kolkata",
        voice_pref="auto", onboarding=kw.pop("onboarding", "done"), text=text,
        provenance=provenance, **kw)


def _match(name: str, ctx) -> bool:
    h = next(h for h in handlers.registered() if h.name == name)
    return bool(h.matches(ctx))


# --- the bug -----------------------------------------------------------------

def test_forwarded_unsubscribe_does_not_pause_the_user():
    """The realistic case: a forwarded advert with a footer."""
    body = "MEGA SALE 70% off! Click now. Reply or click here to unsubscribe."
    assert _match("commands", _ctx(body, "typed")), "sanity: it does parse as STOP"
    assert not _match("commands", _ctx(body, "relayed"))


def test_forwarded_stop_does_not_match():
    assert not _match("commands", _ctx("stop", "relayed"))


def test_forwarded_delete_everything_does_not_match():
    assert not _match("commands", _ctx("delete everything", "relayed"))


def test_forwarded_hinglish_stop_does_not_match():
    assert not _match("commands", _ctx("message mat bhejo band kar do", "relayed"))


# --- what must keep working --------------------------------------------------

def test_the_user_typing_stop_still_works():
    """The fix must not cost the user their own off switch."""
    assert _match("commands", _ctx("stop", "typed"))


def test_the_user_speaking_stop_still_works():
    """A voice note is authored by the person in front of us."""
    assert _match("commands", _ctx("band kar do", "spoken"))


def test_relayed_text_still_reaches_the_agent():
    """Not obeyed is not the same as ignored — it must still be explained."""
    assert _match("agent", _ctx("stop", "relayed"))


def test_button_presses_stay_trusted_even_on_a_relayed_turn():
    """A tap is a first-party control; provenance describes text, not buttons."""
    msg = {"interactive": {"button_reply": {"id": "ack:7"}}}
    assert _match("reminder_ack", _ctx("", "relayed", msg=msg))


def test_onboarding_is_not_provenance_gated():
    """Gating it would drop an un-onboarded user to the agent, breaking
    'onboarding never calls the model' — which is what makes an open door safe."""
    assert _match("onboarding", _ctx("anything", "relayed", onboarding="new"))
