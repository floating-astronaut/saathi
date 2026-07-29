"""Identity is not the phone number. These tests are the guarantee."""
import pytest
from saathi import identity
from saathi.channels import registry
from saathi.channels.base import Capabilities, Transport


def test_dormancy_window_is_inside_indian_recycling_period():
    """India permits recycling a disconnected number after ~90 days. We must
    re-verify well inside that, or a recycled number inherits an elder's
    medicine list, doctor and family."""
    assert identity.DORMANT_AFTER.days < 90
    assert identity.DORMANT_AFTER.days >= 30      # not so twitchy it nags


def test_revocation_waits_for_the_full_written_dead_air_window():
    assert identity.DORMANT_AFTER.days == 60
    assert identity.REVOKE_AFTER.days == 90
    assert identity.REVOKE_AFTER > identity.DORMANT_AFTER


def test_move_code_is_explicit_and_never_a_bare_six_digits():
    assert identity.MOVE_CODE_RE.match("MOVE 123456")
    assert not identity.MOVE_CODE_RE.match("123456")


def test_link_codes_expire_quickly():
    assert identity.LINK_CODE_TTL.total_seconds() <= 30 * 60


def test_whatsapp_is_registered_and_conforms_to_the_protocol():
    t = registry.get("whatsapp")
    assert isinstance(t, Transport)
    assert t.channel == "whatsapp"


def test_unknown_channel_fails_loudly_with_what_is_available():
    with pytest.raises(ValueError) as e:
        registry.get("telegram")
    assert "telegram" in str(e.value) and "whatsapp" in str(e.value)


def test_whatsapp_capabilities_encode_the_platform_limits():
    c = registry.get("whatsapp").capabilities
    assert c.has_session_window and c.session_window_hours == 24
    assert c.requires_templates
    assert c.max_quick_replies == 3          # PRD §11
    assert c.quick_reply_label_len == 20
    assert c.supports_voice_notes
    assert c.markup == "whatsapp"            # *bold*, not **bold**


def test_a_channel_without_a_window_needs_no_templates():
    """The shape a Telegram transport would take: no window, so no template
    machinery, so the pipeline must not assume either exists."""
    c = Capabilities(has_session_window=False, requires_templates=False,
                     max_quick_replies=8, supports_voice_notes=True, markup="markdown")
    assert not c.has_session_window and not c.requires_templates
    assert c.max_quick_replies > registry.get("whatsapp").capabilities.max_quick_replies


def test_transport_format_text_is_channel_specific():
    assert registry.get("whatsapp").format_text("**bold**") == "*bold*"


def test_open_policy_is_safe_because_onboarding_never_calls_the_model():
    """The default is now `open` so anyone can start by messaging the number.

    That is only safe because an unknown sender walks a deterministic onboarding
    script with no model call — see tests/test_onboarding.py. If onboarding ever
    reaches the agent, `open` becomes a way for anyone to spend our tokens, and
    this pairing option is the fallback.
    """
    import inspect
    from saathi import onboarding
    from saathi.config import Settings
    assert Settings().saathi_dm_policy in ("open", "pairing")
    assert "loop.run" not in inspect.getsource(onboarding)


def test_admission_reply_is_bilingual_and_actionable():
    """PRD §6.4: never refuse without a concrete next step. A confused elder
    who is told only 'no' is exactly the failure this product exists to avoid."""
    r = identity.ADMISSION_REPLY
    assert "code" in r.lower()
    assert "Namaste" in r and "Hello" in r
