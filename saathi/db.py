"""Connection pool. Postgres is both the store and the job queue."""
from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from .config import settings

_pool: AsyncConnectionPool | None = None


def pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(settings.saathi_db_dsn, min_size=1, max_size=8, open=False)
    return _pool


async def healthcheck() -> str:
    async with pool().connection() as conn:
        row = await (await conn.execute("select current_setting('server_version')")).fetchone()
        return row[0]
