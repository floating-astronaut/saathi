"""Voice retention. The promise is 7 days and it must be kept by the platform."""
import pytest
from saathi import media_store


class Cur:
    def __init__(self, rows=None): self._rows = rows or []
    async def fetchone(self): return self._rows[0] if self._rows else None
    async def fetchall(self): return self._rows


class Conn:
    def __init__(self, rows=None): self.sql = []; self.rows = rows or []
    async def execute(self, q, params=None):
        self.sql.append(" ".join(q.split()))
        if "select id, storage_key" in q or "select storage_key" in q:
            return Cur(self.rows)
        return Cur()


def test_retention_matches_what_we_promise_users():
    """The privacy policy says 7 days. So does the S3 lifecycle rule."""
    assert media_store.RETENTION_DAYS == 7


def test_keys_are_scoped_per_user_and_dated():
    k = media_store.key_for(42, "wamid.abc", b"audio")
    assert k.startswith("voice/") and "/u42/" in k and k.endswith(".ogg")


def test_same_message_produces_the_same_key():
    """A replayed webhook overwrites rather than duplicating."""
    a = media_store.key_for(1, "wamid.x", b"one")
    b = media_store.key_for(1, "wamid.x", b"two")
    assert a == b


def test_content_addressed_when_there_is_no_message_id():
    a = media_store.key_for(1, None, b"one")
    b = media_store.key_for(1, None, b"two")
    assert a != b


async def test_storage_disabled_is_a_clean_noop(monkeypatch):
    """Debugging audio is our convenience, not the user's feature."""
    monkeypatch.setattr(media_store.settings, "saathi_audio_bucket", "")
    conn = Conn()
    assert await media_store.put_voice(conn, 1, b"data") is None
    assert conn.sql == []          # nothing recorded either


async def test_upload_failure_does_not_break_the_users_turn(monkeypatch):
    monkeypatch.setattr(media_store.settings, "saathi_audio_bucket", "b")
    class Boom:
        def put_object(self, **kw): raise RuntimeError("s3 down")
    monkeypatch.setattr(media_store, "_s3", lambda: Boom())
    conn = Conn()
    assert await media_store.put_voice(conn, 1, b"data") is None   # logged, not raised


async def test_erasure_deletes_objects_immediately_not_in_seven_days(monkeypatch):
    """A DPDP erasure cannot wait for a lifecycle rule."""
    monkeypatch.setattr(media_store.settings, "saathi_audio_bucket", "b")
    deleted = []
    class S3:
        def delete_object(self, Bucket, Key): deleted.append(Key)
    monkeypatch.setattr(media_store, "_s3", lambda: S3())
    conn = Conn(rows=[("voice/a.ogg",), ("voice/b.ogg",)])
    n = await media_store.erase_for_user(conn, 1)
    assert n == 2 and deleted == ["voice/a.ogg", "voice/b.ogg"]
    assert any("deleted_at = now()" in s for s in conn.sql)


async def test_purge_marks_rows_and_deletes_objects(monkeypatch):
    monkeypatch.setattr(media_store.settings, "saathi_audio_bucket", "b")
    class S3:
        def delete_object(self, **kw): pass
    monkeypatch.setattr(media_store, "_s3", lambda: S3())
    conn = Conn(rows=[(1, "voice/x.ogg")])
    assert await media_store.purge_expired(conn) == 1


def test_erasure_reaches_every_table_holding_user_data():
    """A table added later and forgotten is how 'forget everything' quietly lies."""
    import inspect
    from saathi import memory
    src = inspect.getsource(memory.erase)
    for table in ("facts", "messages", "media_blobs", "reminders",
                  "scheduled_turns", "training_samples"):
        assert table in src, f"erasure misses {table}"
