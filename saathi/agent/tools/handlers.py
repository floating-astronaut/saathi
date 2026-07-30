"""Tool side effects. The only code that mutates state on the model's behalf."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

from ... import commercial_actions, memory
from ...lookup import base as lookup

_DAYS = {"mon": "MO", "tue": "TU", "wed": "WE", "thu": "TH",
         "fri": "FR", "sat": "SA", "sun": "SU"}


def to_rrule(recurrence: str, time_24h: str) -> str | None:
    """Translate the model's recurrence vocabulary into an RFC-5545 RRULE.

    Returns None for one-off reminders, which carry a concrete date instead.
    """
    hh, mm = (int(x) for x in time_24h.split(":", 1))
    rec = (recurrence or "").strip().lower()
    if rec in ("once", "", "one-off"):
        return None
    if rec == "daily":
        return f"FREQ=DAILY;BYHOUR={hh};BYMINUTE={mm};BYSECOND=0"
    if rec.startswith("weekly:"):
        day = _DAYS.get(rec.split(":", 1)[1][:3])
        if not day:
            raise ValueError(f"unknown weekday in {recurrence!r}")
        return f"FREQ=WEEKLY;BYDAY={day};BYHOUR={hh};BYMINUTE={mm};BYSECOND=0"
    if rec.startswith("monthly:"):
        dom = int(rec.split(":", 1)[1])
        return f"FREQ=MONTHLY;BYMONTHDAY={dom};BYHOUR={hh};BYMINUTE={mm};BYSECOND=0"
    raise ValueError(f"unsupported recurrence {recurrence!r}")


def next_fire(rrule: str | None, tz: str, after: datetime | None = None,
              date: str | None = None, time_24h: str | None = None) -> datetime:
    """Next occurrence, computed in the user's timezone then returned as UTC.

    Timezone matters more than it looks: 'every morning at 8' must mean 8am
    where the user lives, across DST-free but offset Asia/Kolkata, and the
    queue stores UTC.
    """
    zone = ZoneInfo(tz)
    now_local = (after or datetime.now(zone)).astimezone(zone)
    if rrule is None:
        if not (date and time_24h):
            raise ValueError("one-off reminder needs date and time_24h")
        hh, mm = (int(x) for x in time_24h.split(":", 1))
        y, mo, d = (int(x) for x in date.split("-"))
        return datetime(y, mo, d, hh, mm, tzinfo=zone).astimezone(ZoneInfo("UTC"))
    # dateutil needs a naive dtstart to keep the local wall-clock semantics
    nxt = rrulestr(rrule, dtstart=now_local.replace(tzinfo=None)).after(
        now_local.replace(tzinfo=None), inc=False
    )
    return nxt.replace(tzinfo=zone).astimezone(ZoneInfo("UTC"))


class Handlers:
    """Bound to one user; `handle` is what the agent loop calls."""

    def __init__(self, conn, user_id: int, tz: str = "Asia/Kolkata"):
        self.conn, self.user_id, self.tz = conn, user_id, tz

    async def handle(self, name: str, args: dict) -> dict:
        fn = getattr(self, f"_{name}", None)
        if fn is None:
            raise ValueError(f"unknown tool {name}")
        return await fn(args)

    # --- reminders ---------------------------------------------------------

    async def _create_reminder(self, a: dict) -> dict:
        rrule = to_rrule(a["recurrence"], a["time_24h"])
        when = next_fire(rrule, self.tz, date=a.get("date"), time_24h=a["time_24h"])
        row = await (await self.conn.execute(
            """insert into reminders (user_id, title, rrule, tz, next_fire_at)
               values (%s,%s,%s,%s,%s) returning id""",
            (self.user_id, a["title"], rrule, self.tz, when),
        )).fetchone()
        rid = row[0]
        # Onto the queue the worker actually reads.
        #
        # This used to insert into `reminder_fires`. Migration 006 made
        # `scheduled_turns` the single dispatch queue and back-filled the
        # existing fires once — but this write was never moved, and
        # `worker/reminder_scheduler.py`, the only reader of `reminder_fires`,
        # is not referenced anywhere. So every reminder created after that
        # migration was written to a table nothing reads and never fired.
        #
        # Imported here rather than at module scope: `worker.turns` imports the
        # rrule helpers above, so a top-level import would be circular. The
        # import is what registers the kinds, and `enqueue` refuses an
        # unregistered kind loudly — in the web process nothing else pulls
        # `worker.turns` in.
        from ...worker import turns  # noqa: F401
        from ... import scheduling

        await scheduling.enqueue(
            self.conn, self.user_id, "reminder", when,
            payload={"reminder_id": rid},
            dedupe_key=f"reminder:{rid}:{when.isoformat()}",
        )
        return {"reminder_id": rid, "title": a["title"],
                "next_fire_at_local": when.astimezone(ZoneInfo(self.tz)).strftime("%Y-%m-%d %H:%M"),
                "recurrence": a["recurrence"]}

    async def _list_reminders(self, _a: dict) -> dict:
        rows = await (await self.conn.execute(
            """select id, title, rrule, next_fire_at from reminders
                where user_id=%s and status='active' and deleted_at is null
                order by next_fire_at""",
            (self.user_id,),
        )).fetchall()
        return {"reminders": [
            {"id": r[0], "title": r[1], "recurring": r[2] is not None,
             "next": r[3].astimezone(ZoneInfo(self.tz)).strftime("%Y-%m-%d %H:%M") if r[3] else None}
            for r in rows]}

    async def _cancel_reminder(self, a: dict) -> dict:
        await self.conn.execute(
            "update reminders set status='cancelled' where id=%s and user_id=%s",
            (a["reminder_id"], self.user_id),
        )
        await self.conn.execute(
            "update reminder_fires set state='skipped' where reminder_id=%s and state='pending'",
            (a["reminder_id"],),
        )
        return {"cancelled": a["reminder_id"]}

    # --- memory ------------------------------------------------------------

    @staticmethod
    def _bias_forms(value: str) -> list[str]:
        """Extract the tokens ASR actually mangles: proper nouns and drug names.

        Storing the whole sentence as a bias phrase is worthless - biasing works
        on the specific rare token, so we pull capitalised words and any long
        non-Hindi-stopword token, and keep the full value as a fallback.
        """
        stop = {"Dr", "Mr", "Mrs", "Ms", "The", "Aapka", "Meri", "Mere"}
        toks = re.findall(r"[A-Z][A-Za-z]{2,}", value)
        names = [t for t in toks if t not in stop]
        return list(dict.fromkeys(names)) or [value]

    async def _remember(self, a: dict) -> dict:
        await self.conn.execute(
            """insert into facts (user_id, kind, key, value, surface_forms)
               values (%s,%s,%s,%s,%s)
               on conflict (user_id, kind, key) where deleted_at is null
               do update set value=excluded.value, updated_at=now()""",
            (self.user_id, a["kind"], a["key"], a["value"], self._bias_forms(a["value"])),
        )
        return {"stored": {a["key"]: a["value"]}}

    async def _forget(self, a: dict) -> dict:
        cur = await self.conn.execute(
            "update facts set deleted_at=now() where user_id=%s and key=%s and deleted_at is null",
            (self.user_id, a["key"]),
        )
        return {"forgotten": a["key"], "rows": cur.rowcount}

    # --- cart --------------------------------------------------------------

    async def _build_cart(self, a: dict) -> dict:
        # Tier 0 is the contract: a clean numbered list, always. Provider links
        # are visible handoffs only; no checkout/session/account state exists.
        handoff = commercial_actions.build_cart_handoff(
            a.get("items", []), note=a.get("note"), kind=a.get("kind") or "grocery",
        )
        return {
            "items": handoff.items,
            "list": handoff.list,
            "note": a.get("note"),
            "query": handoff.query,
            "provider_links": [p.__dict__ for p in handoff.providers],
            "omitted_from_links": handoff.omitted_from_links,
            "boundary": "I made links to search/open the provider. I did not order, book or pay.",
        }

    # --- introspection & control (C1, §13, D4) -----------------------------

    async def _what_you_know(self, _a: dict) -> dict:
        return await memory.describe(self.conn, self.user_id)

    async def _forget_everything(self, a: dict) -> dict:
        # The model must have confirmed first; the tool refuses otherwise.
        # "Forget everything about me" has to actually work (§13), so this is
        # a hard delete, not a tombstone.
        if not a.get("confirmed"):
            return {"error": "not confirmed - ask the user to confirm first"}
        return await memory.erase(self.conn, self.user_id, hard=True)

    async def _set_preference(self, a: dict) -> dict:
        sets, vals = [], []
        if a.get("voice_replies"):
            sets.append("voice_reply_pref = %s"); vals.append(a["voice_replies"])
        if a.get("language"):
            sets.append("lang_pref = %s"); vals.append(a["language"])
        if not sets:
            return {"error": "nothing to change"}
        vals.append(self.user_id)
        await self.conn.execute(f"update users set {', '.join(sets)} where id = %s", vals)
        return {"updated": {k: v for k, v in a.items() if v}}

    async def _snooze_reminder(self, a: dict) -> dict:
        mins = max(1, min(int(a.get("minutes", 15)), 24 * 60))
        cur = await self.conn.execute(
            """update reminder_fires
                  set state = 'snoozed', snoozed_to = now() + (%s || ' minutes')::interval
                where reminder_id = %s and user_id = %s
                  and state in ('sent', 'nudged', 'pending')""",
            (str(mins), a["reminder_id"], self.user_id))
        return {"snoozed_minutes": mins, "fires_updated": cur.rowcount}

    # --- looking things up -------------------------------------------------

    async def _look_up(self, a: dict) -> dict:
        """Answer from the world, via a registered provider.

        The provider's text comes back fenced: it is third-party content, and a
        search result saying "ignore previous instructions" must be as inert as
        a forwarded WhatsApp message.
        """
        from ...lookup import weather, wiki, web  # noqa: F401 - registers providers
        kind = (a.get("kind") or "fact").lower()
        query = (a.get("query") or "").strip()
        # Weather falls back to web search: if the forecast provider can't resolve
        # a place (a phrase, an obscure town), Google-grounded search still answers
        # "temp in Toronto" rather than the turn giving up (AGENT-1). Fact/web
        # already cross-cover each other.
        order = {"weather": ["weather", "web"],
                 "fact": ["wikipedia", "web"],
                 "web": ["web", "wikipedia"]}.get(kind, ["wikipedia", "web"])

        city = None
        if kind == "weather":
            row = await (await self.conn.execute(
                """select value from facts
                    where user_id = %s and deleted_at is null
                      and (kind = 'place' or key ilike '%%city%%' or key ilike '%%shehar%%')
                    order by updated_at desc limit 1""", (self.user_id,))).fetchone()
            city = row[0] if row else None
            if not city and not query:
                return {"need": "city",
                        "say": "Aap kis shehar mein rehte hain? Bata dijiye, main yaad "
                               "rakh lungi aur aage se mausam bata dungi."}

        for name in order:
            p = lookup.get(name)
            if not p or not p.available():
                continue
            try:
                ans = await p.lookup(query, city=city)
            except Exception as exc:  # noqa: BLE001 - a dead provider must not kill the turn
                continue
            if ans:
                return {"found": True, "provider": name, "content": ans.fenced(),
                        "url": ans.url}
        return {"found": False,
                "say": "Yeh main abhi pata nahi kar payi. Kuch aur poochhna ho to bataiye."}
