"""Worker entrypoint: `python -m saathi.worker`.

Runs alongside the web process (systemd unit two of two). Postgres is the queue,
so there is nothing else to stand up.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from psycopg_pool import AsyncConnectionPool

from .. import net_policy
from ..config import settings
from . import turns  # noqa: F401 - registers the scheduled kinds
from .. import scheduling

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s — %(message)s")
# Redact at the root: a capability that logs an exception containing a presigned
# URL must not leak it by forgetting to call redact() itself.
logging.getLogger().addFilter(net_policy.RedactingFilter())
log = logging.getLogger("saathi.worker")


async def main() -> None:
    pool = AsyncConnectionPool(settings.saathi_db_dsn, min_size=1, max_size=4, open=False)
    await pool.open()
    log.info("worker up — scheduled kinds: %s", scheduling.registered())
    try:
        while True:
            started = datetime.now(timezone.utc)
            try:
                n = await scheduling.run_once(pool)
                if n:
                    log.info("dispatched %s scheduled turn(s)", n)
            except Exception:  # noqa: BLE001
                log.exception("scheduler tick failed")
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            await asyncio.sleep(max(1.0, scheduling.POLL_SECONDS - elapsed))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
