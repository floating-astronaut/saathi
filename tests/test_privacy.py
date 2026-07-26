"""Privacy must hold by construction. These tests are the guarantee, not a hope."""
import pytest
from saathi import privacy, training


class Cur:
    rowcount = 0
    def __init__(self, row=None): self._row = row
    async def fetchone(self): return self._row
    async def fetchall(self): return []


class Conn:
    """Records what would be written, and whether consent was granted."""
    def __init__(self, consent=True):
        self.consent = consent
        self.writes = []
    async def execute(self, q, params=None):
        low = q.lower()
        if "from training_consent" in low:
            return Cur((self.consent,))
        if "insert into training_samples" in low:
            self.writes.append(params)
        return Cur(None)


# --- the hard rules ---------------------------------------------------------

@pytest.mark.parametrize("kind", ["person", "place", "other", "preference", "routine"])
def test_identifying_entity_kinds_are_never_trainable(kind):
    assert not privacy.is_trainable_entity(kind)


@pytest.mark.parametrize("kind", ["medicine", "brand"])
def test_shared_vocabulary_is_trainable(kind):
    assert privacy.is_trainable_entity(kind)


async def test_person_name_is_refused_even_with_consent():
    """No threshold, no flag, no override. A family member's name never enters."""
    conn = Conn(consent=True)
    stored = await training.record_correction(conn, 1, "Priyaa", "Priya", "person")
    assert stored is False and conn.writes == []


async def test_medicine_correction_is_recorded_with_consent():
    conn = Conn(consent=True)
    assert await training.record_correction(conn, 1, "bomlodipin", "Amlodipine", "medicine")
    assert len(conn.writes) == 1
    assert conn.writes[0][1] == "bomlodipin" and conn.writes[0][2] == "Amlodipine"


async def test_nothing_is_recorded_without_consent():
    conn = Conn(consent=False)
    assert not await training.record_correction(conn, 1, "bomlodipin", "Amlodipine", "medicine")
    assert not await training.record_clock_word(conn, 1, "paune gyarah", "22:45")
    assert conn.writes == []


async def test_multiword_or_dirty_tokens_are_refused_not_cleaned():
    """A cleaner that rescues a messy string is where PII leaks in."""
    conn = Conn(consent=True)
    for heard in ["Dr Mehta ka clinic", "call 9876543210", "", "  ", "a", "x" * 60]:
        assert not await training.record_correction(conn, 1, heard, "Amlodipine", "medicine")
    assert conn.writes == []


async def test_clock_words_carry_no_identity_and_are_recorded():
    conn = Conn(consent=True)
    assert await training.record_clock_word(conn, 1, "Paune Gyarah", "22:45")
    assert conn.writes[0][1] == "paune gyarah"


async def test_clock_phrase_containing_digits_is_refused():
    conn = Conn(consent=True)
    assert not await training.record_clock_word(conn, 1, "call 9876543210 at", "22:45")


async def test_slot_shapes_discard_content():
    shape = privacy.scrub_slots(
        {"title": "Amlodipine for Dadi", "time_24h": "08:15", "recurrence": "weekly:mon"})
    assert shape["title"] == "<title>"          # content gone
    assert shape["time_24h"] == "08:15"         # the thing being learned
    assert shape["recurrence"] == "weekly"      # day-of-week dropped


# --- redaction safety net ---------------------------------------------------

@pytest.mark.parametrize("raw,gone", [
    ("call me on +91 98765 43210", "98765"),
    ("mail bete ko priya@example.com", "priya@example.com"),
    ("dekho https://scam.example/x", "scam.example"),
    ("otp 483920 aaya hai", "483920"),
    ("₹4,500 bheja", "4,500"),
])
def test_redaction_removes_identifiers(raw, gone):
    assert gone not in privacy.redact(raw)


def test_redaction_leaves_ordinary_hinglish_alone():
    s = "roz subah aath baje goli leni hai"
    assert privacy.redact(s) == s


# --- k-anonymity ------------------------------------------------------------

def test_export_threshold_is_meaningful():
    """Anything unique to one person must never leave the box."""
    assert privacy.K_ANON >= 5


async def test_export_reads_the_kanonymised_view_not_the_raw_table():
    seen = {}
    class C:
        async def execute(self, q, params=None):
            seen["q"] = q
            class R:
                async def fetchall(self_inner): return []
            return R()
    await training.export(C())
    assert "training_export" in seen["q"]
    assert "training_samples" not in seen["q"]
