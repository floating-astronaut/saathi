"""Worker entrypoint: `python -m saathi.worker`.

Runs alongside the web process (systemd unit two of two). Postgres is the queue,
so there is nothing else to stand up.
"""
from __future__ import annotations

import asyncio
import logging

from psycopg_pool import AsyncConnectionPool

from ..config import settings
from .reminder_scheduler import run_forever
from .send_reminder import send

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s — %(message)s")


async def main() -> None:
    pool = AsyncConnectionPool(settings.saathi_db_dsn, min_size=1, max_size=4, open=False)
    await pool.open()
    try:
        await run_forever(pool, send)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
