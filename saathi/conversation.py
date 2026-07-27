"""Conversation state and the message lifecycle.

The persistence property the operator asked for — "if I chat on my PC I see it
on mobile" — is not something WhatsApp gives us. WhatsApp syncs *its own*
transcript across the user's devices; it tells us nothing about deletions and
gives us no history API. So the ChatGPT property has to come from our side:

    our store is the source of truth, keyed to the identity, not the device
    and not the channel.

Consequences, both of which are design obligations rather than side effects:

  * **A user deleting the chat on their phone changes nothing here.** Meta sends
    no deletion webhook. Their memory, reminders and history survive — which is
    what makes the product feel continuous, and is also exactly the thing a user
    might not expect.
  * **So deletion must exist inside the product.** We have removed the user's
    normal way to erase things, so we owe them a real one: per-message delete,
    per-conversation clear, and the full erasure already in `memory.erase`.

Redaction vs deletion:
  deleted_at  — hidden from the user and excluded from prompt context
  redacted_at — content actually removed; the row survives so counts, the
                acknowledgement-rate metric and the safety audit trail stay
                honest
  DPDP erasure — hard DELETE, because "forget everything about me" has to mean it
"""
from __future__ import annotations

import logging

log = logging.getLogger("saathi.conversation")

#: A gap longer than this starts a new conversation thread. Long enough that an
#: elder replying the next morning continues yesterday's thread rather than
#: opening a confusing new one.
IDLE_HOURS = 24


async def current(conn, user_id: int, channel: str) -> int:
    """Return the open conversation for this user+channel, creating if needed."""
    row = await (await conn.execute(
        """select id from conversations
            where user_id = %s and channel = %s and closed_at is null
              and last_message_at > now() - (%s || ' hours')::interval
            order by last_message_at desc limit 1""",
        (user_id, channel, str(IDLE_HOURS)),
    )).fetchone()
    if row:
        return row[0]
    row = await (await conn.execute(
        """insert into conversations (user_id, channel) values (%s,%s) returning id""",
        (user_id, channel))).fetchone()
    return row[0]


async def touch(conn, conversation_id: int) -> None:
    await conn.execute(
        "update conversations set last_message_at = now() where id = %s", (conversation_id,))


async def history(conn, user_id: int, limit: int = 12) -> list[dict]:
    """Recent turns for prompt context, newest last.

    Crosses channels on purpose: the identity is the thread, not the transport.
    Someone who starts on WhatsApp and later arrives on Telegram should not be
    met by an assistant with amnesia.
    """
    # `btrim(...) <> ''` and not merely `is not null`. An empty string is not
    # null, and Bedrock rejects a blank ContentBlock outright:
    #
    #     ValidationException: The text field in the ContentBlock object at
    #     messages.N.content.0 is blank.
    #
    # That exception escapes the whole turn, so the user gets *nothing* — and it
    # keeps happening on every subsequent turn until the blank row falls out of
    # this window. One image sent without a caption on 2026-07-27 08:02 stored
    # `body_text = ''` and broke that user's next four conversations.
    rows = await (await conn.execute(
        """select direction::text, coalesce(transcript, body_text)
             from messages
            where user_id = %s and deleted_at is null
              and btrim(coalesce(transcript, body_text)) <> ''
            order by created_at desc limit %s""",
        (user_id, limit),
    )).fetchall()
    out: list[dict] = []
    for direction, text in reversed(rows):
        role = "user" if direction == "in" else "assistant"
        out.append({"role": role, "content": [{"text": text}]})
    # A tool loop rejects a trailing assistant turn with nothing after it, and
    # rejects two same-role turns in a row; collapse to keep the shape legal.
    cleaned: list[dict] = []
    for m in out:
        if cleaned and cleaned[-1]["role"] == m["role"]:
            cleaned[-1] = m
        else:
            cleaned.append(m)
    while cleaned and cleaned[-1]["role"] == "assistant":
        cleaned.pop()
    return cleaned


async def delete_message(conn, user_id: int, message_id: int, redact: bool = True) -> bool:
    """User-initiated delete of a single message.

    Redacts content by default. The row survives so that acknowledgement rates
    and safety events stay countable — deleting a message should not quietly
    rewrite the record of whether a reminder was acknowledged.
    """
    cur = await conn.execute(
        """update messages
              set deleted_at = now(),
                  redacted_at = case when %s then now() else redacted_at end,
                  body_text  = case when %s then null else body_text end,
                  transcript = case when %s then null else transcript end,
                  transcript_raw = case when %s then null else transcript_raw end
            where id = %s and user_id = %s and deleted_at is null""",
        (redact, redact, redact, redact, message_id, user_id))
    return cur.rowcount > 0


async def delete_last(conn, user_id: int, n: int = 1) -> int:
    """"Delete that" — the user's most recent messages, newest first."""
    cur = await conn.execute(
        """update messages set deleted_at = now(), redacted_at = now(),
               body_text = null, transcript = null, transcript_raw = null
            where id in (select id from messages
                          where user_id = %s and direction = 'in' and deleted_at is null
                          order by created_at desc limit %s)""",
        (user_id, n))
    return cur.rowcount


async def clear_conversation(conn, user_id: int, conversation_id: int | None = None) -> int:
    """Clear a thread. Facts, reminders and consent are untouched.

    Deliberately separate from `memory.erase`: "clear this chat" and "forget
    everything about me" are different requests, and conflating them would either
    destroy a user's reminders by accident or fail to honour a real erasure.
    """
    if conversation_id is None:
        conversation_id = await current(conn, user_id, "whatsapp")
    cur = await conn.execute(
        """update messages set deleted_at = now(), redacted_at = now(),
               body_text = null, transcript = null, transcript_raw = null
            where user_id = %s and conversation_id = %s and deleted_at is null""",
        (user_id, conversation_id))
    await conn.execute(
        "update conversations set closed_at = now() where id = %s", (conversation_id,))
    log.info("cleared conversation %s for user %s (%s messages)",
             conversation_id, user_id, cur.rowcount)
    return cur.rowcount
