"""Secrets at rest.

One job: an API key we mint on a user's behalf must never sit in a table as
plaintext, and must never reach a log line — not even a prefix, because a
prefix is enough to identify a key in a vendor dashboard and nowhere near
enough to be worth the risk.

Deliberately not a general-purpose crypto module. Fernet is the whole
implementation: authenticated, key-rotation-capable, and impossible to use in
the several wrong ways a raw cipher offers.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


class SecretsUnavailable(RuntimeError):
    """No usable `SAATHI_SECRETS_KEY`.

    Raised rather than degraded. The caller's correct response is to refuse the
    operation, never to store the plaintext and carry on — see
    `docs/AI_ROUTING.md` §5, step 2.
    """


def available() -> bool:
    """Can we encrypt at all? Checked *before* minting anything upstream.

    Minting first and discovering this second would leave a live, billable key
    at the vendor that we cannot store, cannot use and cannot revoke.
    """
    try:
        _fernet()
    except SecretsUnavailable:
        return False
    return True


def _fernet() -> Fernet:
    raw = settings.saathi_secrets_key
    if not raw:
        raise SecretsUnavailable("SAATHI_SECRETS_KEY is not set")
    try:
        return Fernet(raw.encode())
    except (ValueError, TypeError) as exc:
        # A malformed key is a configuration error, not a runtime condition.
        # Failing loudly here is the difference between "provisioning is off"
        # and "provisioning silently stores garbage".
        raise SecretsUnavailable(f"SAATHI_SECRETS_KEY is not a valid Fernet key: {exc}") from exc


def encrypt(plaintext: str) -> str:
    """Encrypt for storage. The ciphertext is safe to put in a row."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt for use. Raises `SecretsUnavailable` on a wrong or rotated key.

    `InvalidToken` is translated because the caller cannot do anything useful
    with a cryptography-specific exception, and because the two failures it
    conflates — wrong key, tampered row — both mean the same thing here: this
    credential cannot be used, do not guess.
    """
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise SecretsUnavailable(
            "stored secret could not be decrypted — wrong or rotated SAATHI_SECRETS_KEY"
        ) from exc
