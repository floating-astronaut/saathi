"""Network policy. Both controls fail loudly — a control that degrades to
'allow' on bad input is not a control."""
import logging
import pytest
from saathi import net_policy as np


# --- redaction: the control that would have caught our real leak ------------

def test_the_actual_leak_that_happened_is_caught():
    """A Graph response containing a page access token was printed whole during
    development. This is the control that stops that class of error."""
    leaked = 'me/accounts -> {"access_token": "EAAWU2jHp1JcBSPbvc2u55y5KU81FSLUOwhEwk8VHMPs"}'
    out = np.redact(leaked)
    assert "EAAWU2jHp1Jc" not in out and np.REDACTED in out


@pytest.mark.parametrize("param", [
    "access_token", "token", "api_key", "client_secret", "signature",
    "X-Amz-Signature", "refresh_token", "authorization", "code",
])
def test_credential_query_params_are_stripped(param):
    url = f"https://example.com/x?{param}=SUPERSECRET&page=2"
    out = np.redact_url(url)
    assert "SUPERSECRET" not in out
    assert "page=2" in out            # non-secrets survive


def test_url_userinfo_is_removed():
    out = np.redact_url("https://user:hunter2@example.com/path")
    assert "hunter2" not in out and "example.com" in out


@pytest.mark.parametrize("secret", [
    "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",
    "AKIAIOSFODNN7EXAMPLE",
    "sk-abcdefghijklmnopqrstuvwxyz012345",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
])
def test_bare_tokens_outside_urls_are_redacted(secret):
    assert secret not in np.redact(f"config has {secret} in it")


def test_ordinary_text_and_urls_survive():
    s = "see https://n8nworld.store/privacy/ for details"
    assert np.redact(s) == s


def test_logging_filter_redacts_without_the_caller_remembering(caplog):
    log = logging.getLogger("t.redact")
    log.addFilter(np.RedactingFilter())
    with caplog.at_level(logging.INFO, logger="t.redact"):
        log.info("callback https://x.co/cb?access_token=LEAKME")
    assert "LEAKME" not in caplog.text


# --- SSRF --------------------------------------------------------------------

@pytest.mark.parametrize("url,why", [
    ("http://169.254.169.254/latest/meta-data/", "cloud metadata"),
    ("http://127.0.0.1:3130/healthz", "loopback"),
    ("http://localhost/x", "loopback by name"),
    ("http://10.0.0.5/x", "private"),
    ("http://172.31.32.37/x", "our own VPC"),
    ("http://192.168.1.1/", "private"),
    ("http://[::1]/", "ipv6 loopback"),
    ("http://[::ffff:127.0.0.1]/", "ipv4 smuggled inside ipv6"),
    ("http://100.64.0.1/", "carrier-grade NAT"),
    ("http://0.0.0.0/", "unspecified"),
])
def test_dangerous_targets_are_refused(url, why):
    with pytest.raises(np.UnsafeTarget):
        np.assert_safe_url(url, resolve=(("localhost" in url)))


def test_non_http_schemes_refused():
    for u in ("file:///etc/passwd", "gopher://x", "ftp://x/y", "data:text/html,x"):
        with pytest.raises(np.UnsafeTarget):
            np.assert_safe_url(u, resolve=False)


def test_credentials_in_url_refused():
    with pytest.raises(np.UnsafeTarget):
        np.assert_safe_url("https://user:pw@example.com/", resolve=False)


def test_public_target_allowed():
    assert np.assert_safe_url("https://8.8.8.8/", resolve=False)


def test_empty_and_garbage_raise_rather_than_pass():
    for bad in ("", "   ", "not a url"):
        with pytest.raises(np.UnsafeTarget):
            np.assert_safe_url(bad, resolve=False)


def test_is_safe_url_boolean_form():
    assert np.is_safe_url("https://8.8.8.8/", resolve=False)
    assert not np.is_safe_url("http://169.254.169.254/", resolve=False)
