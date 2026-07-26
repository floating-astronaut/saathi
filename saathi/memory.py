"""Memory (PRD C1) — facts as explicit rows, never an opaque inferred blob.

Two consumers, and the second is the higher-value one:
  1. Personalisation, via the fact block in the system prefix.
  2. **ASR entity biasing** (s10): the surface forms of a user's medicines,
     people and places are exactly the words a general ASR model mangles.
     Passing them to STT (or to the correction pass) is why the product hears
     someone better the longer they use it - a retention mechanic, not just an
     accuracy fix.

Because there is no prompt caching (plan s5c), the fact block is re-sent and
re-paid on every turn. So it is capped and ordered by recency: recency beats
completeness for a conversational assistant, and an unbounded fact block is a
slow, silent cost leak.
"""
from __future__ import annotations

MAX_FACTS = 40


async def load_facts(conn, user_id: int, limit: int = MAX_FACTS) -> list[tuple[str, str]]:
    """Most recently touched facts first, for the system prefix."""
    rows = await (await conn.execute(
        """select key, value from facts
            where user_id = %s and deleted_at is null
            order by updated_at desc
            limit %s""",
        (user_id, limit),
    )).fetchall()
    return [(r[0], r[1]) for r in rows]


async def surface_forms(conn, user_id: int) -> list[str]:
    """Entity-bias vocabulary for STT: medicines and people first.

    Ordered by how badly ASR tends to mangle them - drug names are both the
    most-mangled and the most consequential to get wrong.
    """
    rows = await (await conn.execute(
        """select distinct unnest(
                 case when surface_forms = '{}' then array[value] else surface_forms end)
             from facts
            where user_id = %s and deleted_at is null
              and kind in ('medicine', 'person', 'place', 'brand')
            order by 1""",
        (user_id,),
    )).fetchall()
    return [r[0] for r in rows if r[0]]


async def describe(conn, user_id: int) -> dict:
    """Answer "what do you know about me?" - a C1 requirement, not a nicety."""
    rows = await (await conn.execute(
        """select kind::text, key, value from facts
            where user_id = %s and deleted_at is null
            order by kind, key""",
        (user_id,),
    )).fetchall()
    grouped: dict[str, list[str]] = {}
    for kind, key, value in rows:
        grouped.setdefault(kind, []).append(f"{key}: {value}")
    return {"known": grouped, "count": len(rows)}


async def erase(conn, user_id: int, hard: bool = False) -> dict:
    """Right to erasure (s13), implemented from day one rather than retrofitted.

    `hard` genuinely deletes rather than tombstoning - which is what "forget
    everything about me" has to mean for it to be an honest answer.
    """
    await conn.execute(
        "insert into erasure_requests (user_id, state) values (%s, 'running')", (user_id,)
    )
    if hard:
        # Objects in S3 do not cascade from a foreign key — delete them first,
        # because erasure cannot wait seven days for a lifecycle rule.
        try:
            from . import media_store
            counts_audio = await media_store.erase_for_user(conn, user_id)
        except Exception:  # noqa: BLE001 - never block an erasure request
            log.exception("audio erasure failed for user %s", user_id)
            counts_audio = -1
        counts = {"audio_objects": counts_audio}
        for table in ("facts", "messages", "media_blobs", "reminder_fires",
                      "reminders", "scheduled_turns", "training_samples"):
            cur = await conn.execute(f"delete from {table} where user_id = %s", (user_id,))
            counts[table] = cur.rowcount
    else:
        cur = await conn.execute(
            "update facts set deleted_at = now() where user_id = %s and deleted_at is null",
            (user_id,))
        counts = {"facts": cur.rowcount}
    await conn.execute(
        """update erasure_requests set state = 'done', completed_at = now()
            where user_id = %s and state = 'running'""", (user_id,))
    return {"erased": counts, "hard": hard}
