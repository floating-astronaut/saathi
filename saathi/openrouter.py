"""Per-account OpenRouter keys: minting, naming, and the guard that matters.

One master **provisioning key** mints a capped sub-key per account. Two things
follow that are worth the extra moving part: spend becomes attributable to a
household, and a runaway loop burns that household's cap instead of the
platform balance. `docs/AI_ROUTING.md` §4-§8.

**This OpenRouter org also holds MeshPilot's keys, and `DELETE /keys/{hash}`
works on all of them.** So every operation that could touch a key it did not
mint asserts the `saathi:` prefix first. Not a convention — an assertion, in
the code, like `assert_no_forbidden_tools()`. A shared account means the guard
cannot live in the discipline of whoever runs it next.
"""
from __future__ import annotations

import logging
from decimal import Decimal

import httpx

from . import accounts, crypto
from .config import settings

log = logging.getLogger("saathi.openrouter")

#: Every key we mint carries this. Nothing without it may be listed, revoked or
#: synced by this module.
NAME_PREFIX = "saathi:"


class ProvisioningDisabled(RuntimeError):
    """Provisioning is not configured. Refuse; never mint and hope.

    Two distinct causes, both fatal to the operation: no master key (we cannot
    mint) or no Fernet key (we could mint but could not store the result
    safely, which is worse — it would leave a live billable credential at the
    vendor that we can neither use nor revoke).
    """


class NotOurKey(RuntimeError):
    """A key without the `saathi:` prefix. Refuse to act on it.

    This is the MeshPilot guard. It is a hard error rather than a skip so that
    a sync bug shows up as a stack trace rather than as somebody else's
    production key quietly disappearing.
    """


def key_name(account_id: int, tier: str, env: str | None = None) -> str:
    """`saathi:account:<id>:plan:<tier>:env:<env>`

    Self-describing because this string is the only join back to a tenant when
    you are staring at the OpenRouter dashboard during an incident.
    """
    return f"{NAME_PREFIX}account:{account_id}:plan:{tier}:env:{env or settings.saathi_env}"


def assert_ours(name: str | None) -> str:
    """Gate every list/revoke/sync operation. Raises rather than returning False.

    A control that returns a falsy value on malformed input is how the check
    gets skipped — `net_policy` makes the same argument at more length.
    """
    if not name or not name.startswith(NAME_PREFIX):
        raise NotOurKey(f"refusing to act on a key not minted by Saathi: {name!r}")
    return name


def _headers() -> dict[str, str]:
    if not settings.openrouter_master_key:
        raise ProvisioningDisabled("OPENROUTER_MASTER_KEY is not set")
    return {"Authorization": f"Bearer {settings.openrouter_master_key}",
            "Content-Type": "application/json"}


def _extract(payload: dict) -> tuple[str | None, str | None]:
    """Pull `(plaintext, hash)` out of either response shape.

    `POST /keys` returns **either** `{key, data: {hash, ...}}` **or** a flat
    `{key, hash, ...}`. Both are real; the prose docs describe one and the
    generated client the other. Without the hash a key can never be rotated or
    revoked, so the caller re-reads `GET /keys` when it is missing — that
    fallback is not paranoia.
    """
    data = payload.get("data") or {}
    return (payload.get("key") or data.get("key"),
            data.get("hash") or payload.get("hash"))


async def _find_hash_by_name(http: httpx.AsyncClient, name: str) -> str | None:
    """Last resort when the mint response carried no hash."""
    resp = await http.get(f"{settings.openrouter_base_url}/keys", headers=_headers())
    resp.raise_for_status()
    for item in (resp.json().get("data") or []):
        if item.get("name") == name:
            return item.get("hash")
    return None


async def _audit(conn, account_id: int, action: str, outcome: str, detail: str) -> None:
    await conn.execute(
        """insert into ai_key_events (account_id, action, outcome, detail)
           values (%s, %s, %s, %s)""",
        (account_id, action, outcome, detail[:500]))


async def active_key_row(conn, account_id: int):
    return await (await conn.execute(
        """select id, name, key_hash, key_ciphertext, monthly_cap_usd
             from ai_keys
            where account_id = %s and provider = 'openrouter' and status = 'active'""",
        (account_id,))).fetchone()


async def mint(conn, account_id: int) -> dict:
    """Mint this account's capped key, or return the one it already has.

    The order is the whole design (`AI_ROUTING.md` §5) and each step earns its
    place:

    1. **Idempotency first.** Calling twice must not create two keys or two
       charges. The database also enforces this with a partial unique index, so
       it holds even if two workers race — an application-level check alone
       would not be a guarantee, only a habit.
    2. **Refuse if unconfigured**, *before* any upstream call.
    3. Mint with the tier cap and a monthly reset.
    4. **On failure, audit then re-raise.** "Did this account ever get a key,
       and why not" must be answerable months later, when the exception text is
       long gone.
    5. Encrypt immediately. The plaintext never outlives this function and
       never reaches a log line, not even a prefix.
    """
    existing = await active_key_row(conn, account_id)
    if existing:
        log.info("account %s already has an active key; minting nothing", account_id)
        return {"account_id": account_id, "minted": False, "name": existing[1]}

    if not settings.openrouter_master_key:
        raise ProvisioningDisabled("OPENROUTER_MASTER_KEY is not set")
    if not crypto.available():
        # Checked before minting, not after: a key minted and then unstorable
        # is live, billable, and unrevokable by us.
        raise ProvisioningDisabled("SAATHI_SECRETS_KEY is unusable — refusing to mint")

    tier = await accounts.tier_of(conn, account_id)
    cap = accounts.tier_cap(tier)
    if cap is None:
        # A free account runs on the platform default. Not an error: it is the
        # answer to "should merely arriving cost us money".
        log.info("account %s is tier %s — no key minted by design", account_id, tier)
        return {"account_id": account_id, "minted": False, "name": None, "tier": tier}

    name = key_name(account_id, tier)
    body = {"name": name, "limit": float(cap), "limit_reset": "monthly"}
    if settings.openrouter_workspace_id:
        body["workspace_id"] = settings.openrouter_workspace_id

    try:
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(f"{settings.openrouter_base_url}/keys",
                                   headers=_headers(), json=body)
            resp.raise_for_status()
            plaintext, key_hash = _extract(resp.json())
            if plaintext and not key_hash:
                key_hash = await _find_hash_by_name(http, name)
    except Exception as exc:
        await _audit(conn, account_id, "mint", "error", f"{type(exc).__name__}: {exc}")
        log.error("minting failed for account %s: %s", account_id, type(exc).__name__)
        raise

    if not plaintext:
        await _audit(conn, account_id, "mint", "error", "response carried no key")
        raise RuntimeError("OpenRouter returned no key material")

    ciphertext = crypto.encrypt(plaintext)
    del plaintext  # not a security control; a statement of the intended lifetime

    await conn.execute(
        """insert into ai_keys
             (account_id, name, key_hash, key_ciphertext, monthly_cap_usd)
           values (%s, %s, %s, %s, %s)""",
        (account_id, name, key_hash, ciphertext, cap))
    await _audit(conn, account_id, "mint", "ok", f"tier={tier} cap={cap} hash={key_hash}")
    # Account, tier and cap. No key material, and no prefix of it.
    log.info("minted key for account %s (tier %s, cap %s)", account_id, tier, cap)
    return {"account_id": account_id, "minted": True, "name": name, "cap": cap}


async def revoke(conn, account_id: int) -> bool:
    """Revoke this account's key upstream and locally.

    Asserts the prefix on the *stored* name before calling DELETE, because the
    row is the only thing standing between this function and MeshPilot's keys.
    """
    row = await active_key_row(conn, account_id)
    if not row:
        return False
    key_id, name, key_hash = row[0], row[1], row[2]
    assert_ours(name)
    if not key_hash:
        # Nothing we can call. Say so loudly: the upstream key stays live and
        # billable, and only a human with the dashboard can finish this.
        await _audit(conn, account_id, "revoke", "error", f"no hash stored for {name}")
        raise RuntimeError(f"cannot revoke {name}: no key hash stored")

    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.delete(f"{settings.openrouter_base_url}/keys/{key_hash}",
                                 headers=_headers())
        resp.raise_for_status()

    await conn.execute(
        "update ai_keys set status='revoked', revoked_at=now() where id=%s", (key_id,))
    await _audit(conn, account_id, "revoke", "ok", name)
    log.info("revoked key for account %s", account_id)
    return True


# --- resolution: no silent fallback ------------------------------------------

class AiNotConfigured(RuntimeError):
    """`runtime_ai_not_configured` — no account key and no platform default."""
    code = "runtime_ai_not_configured"


class ByokMissing(RuntimeError):
    """`runtime_ai_byok_missing` — a key row exists but its ciphertext will not open."""
    code = "runtime_ai_byok_missing"


async def resolve(conn, account_id: int) -> str | None:
    """The key this account's turns should spend on, or None for the default.

    Returns None *only* when the account is deliberately on the platform
    default. It never downgrades a broken account key to a shared one: a quiet
    downgrade is how you find out at the end of the month, on the invoice,
    about a tenant whose spend was never attributed.
    """
    row = await active_key_row(conn, account_id)
    if not row:
        return None
    ciphertext = row[3]
    if not ciphertext:
        raise ByokMissing(f"account {account_id} has a key row with no ciphertext")
    try:
        return crypto.decrypt(ciphertext)
    except crypto.SecretsUnavailable as exc:
        raise ByokMissing(str(exc)) from exc


def cap_of(row) -> Decimal | None:
    return row[4] if row else None
