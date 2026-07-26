"""Network policy: what may be fetched, and what may be logged.

Ported from OpenClaw's `packages/net-policy` (MIT, © 2026 OpenClaw Foundation)
— specifically the curated sensitive-query-parameter list and the blocked-IP
range set. Reimplemented in Python on the stdlib `ipaddress` module; the value
taken is the *lists*, which are the part someone had to learn the hard way.

Two controls, both needed before we fetch anything a user or a web search hands
us:

**Redaction.** Credentials travel in URLs far more than people expect —
`?access_token=`, S3 presigned `X-Amz-Signature`, OAuth `code=`. A URL that
reaches a log, an exception, or a database row takes the credential with it.
This project has already been bitten once: a Graph API response was printed
whole during development and contained a page access token. "Be careful" is not
a control. `redact()` is.

**SSRF.** The moment we follow a user-supplied link — and web search means we
will — an attacker can aim us at `169.254.169.254` (cloud metadata),
`127.0.0.1`, or anything on our private network. The box requires IMDSv2, which
helps, but defence in depth is the point.

Both fail **loudly**. OpenClaw's own comment on this is worth keeping in mind:
a silent `undefined` in an SSRF check skips the check. A security control that
degrades to "allow" on malformed input is not a control, so these raise.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# --- redaction ---------------------------------------------------------------

#: Query parameters that commonly carry credentials.
#: Ported from OpenClaw net-policy/redact-sensitive-url.ts (MIT).
SENSITIVE_PARAMS: frozenset[str] = frozenset({
    "token", "key", "api_key", "apikey", "secret", "access_token", "auth_token",
    "password", "pass", "passwd", "auth", "jwt", "session", "id_token", "code",
    "client_secret", "app_secret", "hook_token", "refresh_token", "signature",
    "x_amz_signature", "x_amz_security_token", "x_amz_credential",
    "private_key", "credential", "authorization", "sig", "sas",
})

REDACTED = "[redacted]"

#: Token shapes we handle ourselves, so a bare token in a log line is caught
#: even when it is not inside a URL.
_TOKEN_SHAPES = [
    re.compile(r"\bEA[A-Za-z0-9]{20,}\b"),                 # Meta access tokens
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),             # OpenAI-style
    re.compile(r"\bshp(at|ca|pa|ss)_[A-Za-z0-9]{16,}\b"),  # Shopify
    re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b"),           # Stripe live
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                   # AWS access key id
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),               # GitHub PAT
]

_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def redact_url(url: str) -> str:
    """Strip credential-bearing query parameters from a URL."""
    if not url:
        return url
    try:
        p = urlparse(url)
    except ValueError:
        return REDACTED
    if not p.query:
        cleaned = p
    else:
        kept = [(k, REDACTED if k.lower().replace("-", "_") in SENSITIVE_PARAMS else v)
                for k, v in parse_qsl(p.query, keep_blank_values=True)]
        cleaned = p._replace(query=urlencode(kept))
    # userinfo (https://user:pass@host) is always a credential
    if cleaned.username or cleaned.password:
        host = cleaned.hostname or ""
        if cleaned.port:
            host = f"{host}:{cleaned.port}"
        cleaned = cleaned._replace(netloc=f"{REDACTED}@{host}")
    return urlunparse(cleaned)


def redact(text: str) -> str:
    """Redact URLs and bare tokens anywhere in a blob of text.

    Use before logging, before storing an error, and before showing anything
    provider-shaped to a human.
    """
    if not text:
        return text
    out = _URL_RE.sub(lambda m: redact_url(m.group(0)), text)
    for shape in _TOKEN_SHAPES:
        out = shape.sub(REDACTED, out)
    return out


class RedactingFilter:
    """logging.Filter that redacts every record before it is emitted.

    Attached at the root, so a capability that logs an exception containing a
    presigned URL cannot leak it by forgetting to call `redact` itself.
    """

    def filter(self, record) -> bool:  # noqa: D102 - logging.Filter protocol
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                record.args = tuple(
                    redact(a) if isinstance(a, str) else a for a in record.args
                ) if isinstance(record.args, tuple) else record.args
        except Exception:  # noqa: BLE001 - logging must never raise
            pass
        return True


# --- SSRF --------------------------------------------------------------------

ALLOWED_SCHEMES = frozenset({"http", "https"})


class UnsafeTarget(ValueError):
    """Raised rather than returning False, so a caller cannot ignore it."""


def _blocked(ip: ipaddress._BaseAddress) -> str | None:
    """Why this address must not be fetched, or None if it is fine."""
    if ip.is_loopback:
        return "loopback"
    if ip.is_private:
        return "private"
    if ip.is_link_local:
        return "link-local (cloud metadata lives here)"
    if ip.is_multicast:
        return "multicast"
    if ip.is_reserved:
        return "reserved"
    if ip.is_unspecified:
        return "unspecified"
    if isinstance(ip, ipaddress.IPv4Address):
        # Carrier-grade NAT — reachable inside some hosting networks.
        if ip in ipaddress.ip_network("100.64.0.0/10"):
            return "carrier-grade NAT"
    if isinstance(ip, ipaddress.IPv6Address):
        # IPv4 smuggled inside IPv6 (::ffff:127.0.0.1, 64:ff9b::/96) bypasses a
        # naive v4-only check. OpenClaw calls this out explicitly; it is the
        # classic miss.
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            return _blocked(mapped) or None
        if ip in ipaddress.ip_network("64:ff9b::/96"):
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
            return _blocked(embedded) or None
    return None


def assert_safe_url(url: str, *, resolve: bool = True) -> str:
    """Validate a URL we are about to fetch. Raises `UnsafeTarget` if not safe.

    `resolve=False` skips DNS (useful in tests); note that skipping it also
    skips the DNS-rebinding protection, so production callers must not.
    """
    if not url or not url.strip():
        raise UnsafeTarget("empty URL")
    try:
        p = urlparse(url.strip())
    except ValueError as exc:
        raise UnsafeTarget(f"unparseable URL: {exc}") from exc

    if p.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeTarget(f"scheme {p.scheme!r} not allowed")
    if p.username or p.password:
        raise UnsafeTarget("credentials embedded in URL")
    host = p.hostname
    if not host:
        raise UnsafeTarget("no host")

    # A literal IP needs no DNS.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        why = _blocked(ip)
        if why:
            raise UnsafeTarget(f"{host} is {why}")
        return url

    if not resolve:
        return url
    try:
        infos = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeTarget(f"cannot resolve {host}: {exc}") from exc
    if not infos:
        # Fail loudly. An empty result must not read as "nothing blocked".
        raise UnsafeTarget(f"{host} resolved to nothing")
    for info in infos:
        addr = info[4][0]
        why = _blocked(ipaddress.ip_address(addr))
        if why:
            raise UnsafeTarget(f"{host} resolves to {addr}, which is {why}")
    return url


def is_safe_url(url: str, *, resolve: bool = True) -> bool:
    """Boolean form, for places where raising is genuinely wrong."""
    try:
        assert_safe_url(url, resolve=resolve)
        return True
    except UnsafeTarget:
        return False
