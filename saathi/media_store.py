"""Short-lived storage for inbound voice notes.

Why keep audio at all, when the safest thing is to keep none: **India is not one
language.** Hindi shifts across state lines, every language carries several
dialects, and an elder in Nagpur does not sound like one in Gwalior. When the
entity-accuracy number moves, a transcript alone cannot tell you whether the
model mis-heard, the audio was poor, or the speaker used a regional form. The
audio is the only artefact that answers that.

So it is kept — deliberately, briefly, and with the deletion enforced by
something more reliable than us:

**The 7-day expiry is an S3 lifecycle rule, not a cron job.** If every worker on
the box died tomorrow, voice notes would still be deleted on day 7. A privacy
promise that depends on our code running is a weaker promise than one the
platform keeps. The retention worker below only tidies the database rows.

Stored in `ap-south-1`, encrypted, in a bucket whose `voice/` prefix the box can
write and read and nothing else can reach. Consistent with the rest of the
residency argument: a recording of someone's voice is at least as personal as
the transcript of it.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

import boto3

from .config import settings

log = logging.getLogger("saathi.media")

#: Must match the bucket lifecycle rule. Kept here only so the DB row's
#: delete_after agrees with what S3 will actually do.
RETENTION_DAYS = 7


def _s3():
    return boto3.client("s3", region_name=settings.bedrock_region)


def key_for(user_id: int, message_id: str | None, data: bytes) -> str:
    """Content-addressed under a per-user prefix.

    The digest means a re-delivered webhook overwrites rather than duplicating,
    and the date prefix makes a manual sweep by day trivial if the lifecycle
    rule is ever changed.
    """
    day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    digest = hashlib.sha256(data).hexdigest()[:16]
    return f"voice/{day}/u{user_id}/{message_id or digest}.ogg"


async def put_voice(conn, user_id: int, data: bytes, message_id: int | None = None,
                    wa_message_id: str | None = None, mime: str = "audio/ogg") -> str | None:
    """Store one voice note and record it. Returns the key, or None if disabled.

    Failure here must never cost the user their reply — debugging audio is our
    convenience, not their feature — so it logs and returns None rather than
    raising into the pipeline.
    """
    if not settings.saathi_audio_bucket:
        return None
    key = key_for(user_id, wa_message_id, data)
    try:
        _s3().put_object(
            Bucket=settings.saathi_audio_bucket, Key=key, Body=data,
            ContentType=mime, ServerSideEncryption="AES256",
            # Belt and braces: even if the lifecycle rule were removed, this
            # records when the object was meant to die.
            Metadata={"delete-after": (datetime.now(timezone.utc)
                                       + timedelta(days=RETENTION_DAYS)).isoformat()},
        )
    except Exception:  # noqa: BLE001
        log.exception("voice upload failed for user %s", user_id)
        return None

    await conn.execute(
        """insert into media_blobs (user_id, message_id, storage_key, bytes, mime,
                                    delete_after)
           values (%s,%s,%s,%s,%s, now() + (%s || ' days')::interval)""",
        (user_id, message_id, key, len(data), mime, str(RETENTION_DAYS)))
    log.info("stored voice %s (%s bytes) for user %s", key, len(data), user_id)
    return key


async def purge_expired(conn, limit: int = 500) -> int:
    """Tidy database rows for objects S3 has already expired.

    S3 owns object deletion. This only stops `media_blobs` growing without
    bound, and deletes the object too in case the lifecycle rule was changed.
    """
    rows = await (await conn.execute(
        """select id, storage_key from media_blobs
            where delete_after < now() and deleted_at is null
            limit %s""", (limit,))).fetchall()
    if not rows:
        return 0
    s3 = _s3()
    for blob_id, key in rows:
        try:
            if settings.saathi_audio_bucket:
                s3.delete_object(Bucket=settings.saathi_audio_bucket, Key=key)
        except Exception:  # noqa: BLE001 - already gone is the normal case
            pass
        await conn.execute(
            "update media_blobs set deleted_at = now() where id = %s", (blob_id,))
    log.info("purged %s expired media rows", len(rows))
    return len(rows)


async def erase_for_user(conn, user_id: int) -> int:
    """Delete a user's audio immediately, for a DPDP erasure request.

    Erasure cannot wait seven days for a lifecycle rule.
    """
    rows = await (await conn.execute(
        "select storage_key from media_blobs where user_id = %s and deleted_at is null",
        (user_id,))).fetchall()
    s3 = _s3()
    for (key,) in rows:
        try:
            if settings.saathi_audio_bucket:
                s3.delete_object(Bucket=settings.saathi_audio_bucket, Key=key)
        except Exception:  # noqa: BLE001
            log.exception("failed deleting %s during erasure", key)
    await conn.execute(
        "update media_blobs set deleted_at = now() where user_id = %s", (user_id,))
    return len(rows)
