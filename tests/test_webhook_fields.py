"""What arrives on the webhook that we currently throw away.

`extract_messages` reads only `value["messages"]`. Everything else — delivery
`statuses`, and whatever Meta sends for payment status now that WhatsApp Pay is
configured on this WABA — is dropped without a trace.

PR-43 needs the real shape of a payment notification. Guessing it from prose is
how you write a handler that never fires; the cheap alternative is to name the
fields we drop, so the first real one shows up in the log with its keys.

The value itself is never logged. A payment notification may carry a payer's
phone or email, which Razorpay holds precisely so that we do not have to.
"""
from saathi.web import app


def _envelope(field, value):
    return {"entry": [{"changes": [{"field": field, "value": value}]}]}


def test_a_payment_field_is_named_rather_than_dropped_silently():
    seen = app.log_unhandled_fields(_envelope("payments", {"payment": {"id": "pay_1"}}))
    assert seen == ["payments"]


def test_an_ordinary_message_webhook_is_not_reported_as_unhandled():
    # It is handled — by extract_messages. Reporting it would train whoever
    # reads these logs to ignore them.
    seen = app.log_unhandled_fields(
        _envelope("messages", {"messages": [{"id": "w1", "type": "text"}]}))
    assert seen == []


def test_delivery_statuses_are_named_too():
    seen = app.log_unhandled_fields(_envelope("messages", {"statuses": [{"id": "w1"}]}))
    assert seen == ["messages"]


def test_the_payload_value_is_never_logged(caplog):
    """A payment notification may carry a payer's phone or email.

    Razorpay holds the payer identity so that we do not have to — logging it
    here would hand it back to us by the least controlled route available.
    """
    caplog.set_level("INFO")
    app.log_unhandled_fields(_envelope(
        "payments", {"payer": {"phone": "919876543210", "email": "a@b.com"}}))
    text = caplog.text
    assert "919876543210" not in text
    assert "a@b.com" not in text
    assert "payer" in text, "the key names should be there, only the values gone"


def test_a_malformed_envelope_yields_nothing_rather_than_raising():
    # This runs on the webhook path. A crash here delays Meta's ack and earns a
    # retry storm.
    for bad in ({}, {"entry": None}, {"entry": [{}]}, {"entry": [{"changes": None}]}):
        assert app.log_unhandled_fields(bad) == []
