"""Per-account OpenRouter keys (AI-1).

The two assertions here that are not about correctness but about blast radius:

* **The `saathi:` prefix guard.** This OpenRouter org also holds MeshPilot's
  keys, and `DELETE /keys/{hash}` works on all of them. MeshPilot serves live
  customers from a different box. A bug in a sync or revoke loop must fail
  loudly rather than delete someone else's production credential.
* **Refuse-if-unconfigured, checked before minting.** A key minted and then
  found unstorable is live, billable, and unrevokable by us — strictly worse
  than never minting at all.
"""
from decimal import Decimal

import pytest

from saathi import accounts, crypto, openrouter
from saathi.config import settings


class Cur:
    def __init__(self, rows=None): self._rows = rows or []
    async def fetchone(self): return self._rows[0] if self._rows else None
    async def fetchall(self): return self._rows


class Conn:
    def __init__(self, rows=None):
        self.sql: list[str] = []
        self.params: list[tuple] = []
        self.rows = rows or {}

    async def execute(self, q, params=None):
        flat = " ".join(q.split())
        self.sql.append(flat)
        self.params.append(params or ())
        for needle, rows in self.rows.items():
            if needle in flat:
                return Cur(rows)
        if flat.lower().startswith("insert") and "returning id" in flat.lower():
            return Cur([(99,)])
        return Cur()

    def wrote(self, needle): return any(needle in s for s in self.sql)
    def all_params(self): return [p for row in self.params for p in row]


@pytest.fixture
def configured(monkeypatch):
    """A fully configured install: master key present, Fernet key usable."""
    from cryptography.fernet import Fernet
    monkeypatch.setattr(settings, "openrouter_master_key", "sk-or-test", raising=False)
    monkeypatch.setattr(settings, "saathi_secrets_key",
                        Fernet.generate_key().decode(), raising=False)
    monkeypatch.setattr(settings, "saathi_env", "test", raising=False)


# --- the MeshPilot guard ----------------------------------------------------

def test_a_key_we_did_not_mint_is_refused():
    # MeshPilot's keys live in this same org and DELETE works on all of them.
    with pytest.raises(openrouter.NotOurKey):
        openrouter.assert_ours("meshpilot:prod:worker")


def test_a_missing_name_is_refused_rather_than_treated_as_ours():
    # A control that returns falsy on malformed input is how the check is
    # skipped. These raise.
    for bad in (None, "", "account:1:plan:beta"):
        with pytest.raises(openrouter.NotOurKey):
            openrouter.assert_ours(bad)


def test_our_own_key_name_passes_the_guard():
    name = openrouter.key_name(7, "beta", env="dev")
    assert openrouter.assert_ours(name) == name
    assert name.startswith("saathi:")


def test_the_key_name_identifies_the_tenant_from_a_dashboard():
    # This string is the only join back to an account during an incident.
    name = openrouter.key_name(42, "beta", env="prod")
    assert name == "saathi:account:42:plan:beta:env:prod"


async def test_revoking_refuses_a_foreign_key_before_calling_delete():
    conn = Conn({"from ai_keys": [(1, "meshpilot:prod", "hash123", "ct", Decimal(5))]})
    with pytest.raises(openrouter.NotOurKey):
        await openrouter.revoke(conn, account_id=1)
    assert not conn.wrote("update ai_keys set status='revoked'")


# --- refuse rather than mint-and-hope ---------------------------------------

async def test_minting_refuses_when_there_is_no_master_key(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_master_key", "", raising=False)
    conn = Conn({"from ai_keys": []})
    with pytest.raises(openrouter.ProvisioningDisabled):
        await openrouter.mint(conn, account_id=1)


async def test_minting_refuses_when_secrets_are_unavailable(monkeypatch):
    """The order matters: this must be caught *before* the upstream call.

    A key minted and then found unstorable is live at the vendor, billable, and
    revokable only by a human with the dashboard.
    """
    monkeypatch.setattr(settings, "openrouter_master_key", "sk-or-test", raising=False)
    monkeypatch.setattr(settings, "saathi_secrets_key", "", raising=False)
    conn = Conn({"from ai_keys": []})
    with pytest.raises(openrouter.ProvisioningDisabled):
        await openrouter.mint(conn, account_id=1)
    assert not conn.wrote("insert into ai_keys")


# --- idempotency -------------------------------------------------------------

async def test_calling_twice_mints_once(configured):
    existing = [(1, "saathi:account:1:plan:beta:env:test", "h", "ct", Decimal(5))]
    conn = Conn({"from ai_keys": existing})
    out = await openrouter.mint(conn, account_id=1)
    assert out["minted"] is False
    assert not conn.wrote("insert into ai_keys")


# --- tier caps fail safe -----------------------------------------------------

def test_an_unknown_tier_gets_the_lowest_cap_never_the_highest():
    # A tier added to the enum and forgotten here must cost nothing.
    assert accounts.tier_cap("enterprise-unlimited") == accounts.TIER_CAPS["free"]
    assert accounts.tier_cap(None) == accounts.TIER_CAPS["free"]


def test_the_free_tier_mints_no_key_at_all():
    """Admission is open by design; arriving must not hand a stranger a budget."""
    assert accounts.tier_cap("free") is None


def test_beta_testers_get_the_agreed_five_dollar_cap():
    assert accounts.tier_cap("beta") == Decimal("5.00")


async def test_a_free_account_is_not_an_error_it_is_the_platform_default(configured):
    conn = Conn({"from ai_keys": [], "from accounts": [("free",)]})
    out = await openrouter.mint(conn, account_id=1)
    assert out["minted"] is False
    assert not conn.wrote("insert into ai_keys")


# --- key material never leaks -----------------------------------------------

def test_a_stored_secret_round_trips(configured):
    ct = crypto.encrypt("sk-or-v1-plaintext")
    assert "sk-or-v1-plaintext" not in ct
    assert crypto.decrypt(ct) == "sk-or-v1-plaintext"


def test_decrypting_with_the_wrong_key_raises_rather_than_returning_garbage(
        configured, monkeypatch):
    from cryptography.fernet import Fernet
    ct = crypto.encrypt("sk-or-v1-plaintext")
    monkeypatch.setattr(settings, "saathi_secrets_key",
                        Fernet.generate_key().decode(), raising=False)
    with pytest.raises(crypto.SecretsUnavailable):
        crypto.decrypt(ct)


async def test_resolution_never_downgrades_a_broken_key_to_the_shared_one(configured):
    """A quiet downgrade is how you find out on the invoice, a month later."""
    conn = Conn({"from ai_keys": [(1, "saathi:account:1:plan:beta:env:test",
                                   "h", "not-a-valid-ciphertext", Decimal(5))]})
    with pytest.raises(openrouter.ByokMissing):
        await openrouter.resolve(conn, account_id=1)


async def test_an_account_with_no_key_resolves_to_the_platform_default(configured):
    conn = Conn({"from ai_keys": []})
    assert await openrouter.resolve(conn, account_id=1) is None


# --- the response-shape quirk ------------------------------------------------

def test_both_documented_response_shapes_yield_a_key_and_hash():
    """POST /keys returns either {key, data:{hash}} or flat {key, hash}."""
    nested = openrouter._extract({"key": "sk-a", "data": {"hash": "h1"}})
    flat = openrouter._extract({"key": "sk-b", "hash": "h2"})
    assert nested == ("sk-a", "h1")
    assert flat == ("sk-b", "h2")


def test_a_missing_hash_is_reported_so_the_caller_can_re_read():
    """Without the hash the key can never be rotated or revoked."""
    assert openrouter._extract({"key": "sk-c"}) == ("sk-c", None)
