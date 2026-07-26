"""The derived training corpus.

Records only what makes the *next* user better understood, and only from users
who opted in separately. Nothing here is a transcript.

The compounding idea, which is the reason this exists at all: the entity
correction pass (§10) already produces gold-labelled pairs for free. When the
user confirms a read-back, the pair `heard -> corrected` is *labelled by the
user themselves*. So the corpus builds itself out of ordinary use, with no
annotation and no transcript retention.

Every write passes three gates, in order:
    1. the user opted in                    (training_consent)
    2. the entity kind is trainable         (privacy.TRAINABLE_KINDS)
    3. both tokens are single safe words    (privacy.is_safe_token)
Failing any gate is a silent no-op — the corpus stays small rather than dirty.
"""
from __future__ import annotations

import logging

from . import privacy

log = logging.getLogger("saathi.training")

CONSENT_VERSION = "2026-07-26.v1"


async def has_consent(conn, user_id: int) -> bool:
    row = await (await conn.execute(
        """select granted from training_consent
            where user_id = %s and revoked_at is null""", (user_id,))).fetchone()
    return bool(row and row[0])


async def set_consent(conn, user_id: int, granted: bool) -> None:
    """Opt in or out. Revoking also removes everything already contributed."""
    await conn.execute(
        """insert into training_consent (user_id, granted, version)
           values (%s,%s,%s)
           on conflict (user_id) do update
              set granted = excluded.granted, version = excluded.version,
                  granted_at = now(),
                  revoked_at = case when excluded.granted then null else now() end""",
        (user_id, granted, CONSENT_VERSION))
    if not granted:
        cur = await conn.execute("delete from training_samples where user_id = %s", (user_id,))
        log.info("training consent revoked for %s; purged %s samples", user_id, cur.rowcount)


async def record_correction(conn, user_id: int, heard: str, corrected: str,
                            entity_kind: str) -> bool:
    """Record one ASR repair. Returns whether it was actually stored.

    Gates are checked here rather than by callers so that a future caller cannot
    forget one.
    """
    if not privacy.is_trainable_entity(entity_kind):
        return False                      # person/place names: never, no override
    if not (privacy.is_safe_token(heard) and privacy.is_safe_token(corrected)):
        return False
    if heard.lower() == corrected.lower():
        return False
    if not await has_consent(conn, user_id):
        return False
    await conn.execute(
        """insert into training_samples (user_id, kind, input, output)
           values (%s,'asr_correction',%s,%s)""",
        (user_id, heard.lower(), corrected))
    return True


async def record_clock_word(conn, user_id: int, phrase: str, time_24h: str) -> bool:
    """Record a Hindi fractional-clock resolution — `paune gyarah` -> `22:45`.

    This is the failure mode that separates models (see DECISIONS.md D-D) and it
    carries no identity: the phrase is language, the time is a time. The *pairing
    of a time with a person* would be sensitive, which is exactly why the user id
    is a foreign key for erasure and never part of the exported row.
    """
    phrase = " ".join((phrase or "").lower().split())
    if not phrase or len(phrase) > 40 or any(ch.isdigit() for ch in phrase):
        return False
    if not (len(time_24h) == 5 and time_24h[2] == ":"):
        return False
    if not await has_consent(conn, user_id):
        return False
    await conn.execute(
        """insert into training_samples (user_id, kind, input, output)
           values (%s,'clock_word',%s,%s)""", (user_id, phrase, time_24h))
    return True


async def record_slot_shape(conn, user_id: int, slots: dict, tool: str) -> bool:
    """Record the *shape* of a successful extraction, never its content."""
    shape = privacy.scrub_slots(slots)
    if not shape or not await has_consent(conn, user_id):
        return False
    await conn.execute(
        """insert into training_samples (user_id, kind, input, output)
           values (%s,'slot_shape',%s,%s)""",
        (user_id, tool, repr(sorted(shape.items()))))
    return True


async def export(conn, kind: str | None = None) -> list[dict]:
    """The only sanctioned way data leaves. Reads the k-anonymised view.

    Never `select * from training_samples` for export — the view is the control,
    and bypassing it would ship pairs unique to a single user.
    """
    q = "select kind, input, output, lang, n_users, n_samples from training_export"
    params: tuple = ()
    if kind:
        q += " where kind = %s"
        params = (kind,)
    rows = await (await conn.execute(q + " order by n_users desc", params)).fetchall()
    return [{"kind": r[0], "input": r[1], "output": r[2], "lang": r[3],
             "n_users": r[4], "n_samples": r[5]} for r in rows]
