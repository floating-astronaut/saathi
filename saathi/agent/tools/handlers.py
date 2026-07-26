"""Tool side effects. The only code that mutates state on the model's behalf."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

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
        await self.conn.execute(
            """insert into reminder_fires (reminder_id, user_id, scheduled_for)
               values (%s,%s,%s) on conflict do nothing""",
            (rid, self.user_id, when),
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

    async def _remember(self, a: dict) -> dict:
        await self.conn.execute(
            """insert into facts (user_id, kind, key, value, surface_forms)
               values (%s,%s,%s,%s,%s)
               on conflict (user_id, kind, key) where deleted_at is null
               do update set value=excluded.value, updated_at=now()""",
            (self.user_id, a["kind"], a["key"], a["value"], [a["value"]]),
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
        # Tier 3 of PRD §C4 is the contract: a clean numbered list, always.
        items = [str(i).strip() for i in a.get("items", []) if str(i).strip()]
        listing = "\n".join(f"{n}. {item}" for n, item in enumerate(items, 1))
        return {"items": items, "list": listing, "note": a.get("note")}
