"""
infrastructure/database.py
asyncpg connection pool — shared across bot and scheduler.
"""
import os
import asyncpg
from loguru import logger

from infrastructure.pg_adapter import PGAdapter

_pool: asyncpg.Pool | None = None
_SCHEMA = "predvestnik"


async def create_pool() -> asyncpg.Pool:
    global _pool
    url = os.environ["DATABASE_URL"]
    _pool = await asyncpg.create_pool(
        url,
        min_size=3,
        max_size=15,
        statement_cache_size=0,   # required for pgbouncer / DO managed PG
        init=_set_schema,
    )
    logger.info(f"✅ PostgreSQL pool готов (min=3 max=15, schema={_SCHEMA})")
    return _pool


async def _set_schema(conn: asyncpg.Connection):
    await conn.execute(f"SET search_path TO {_SCHEMA}, public")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool not initialised. Call create_pool() first.")
    return _pool


async def acquire() -> PGAdapter:
    """Acquire a connection from the pool wrapped in PGAdapter."""
    conn = await get_pool().acquire()
    return PGAdapter(conn)


async def release(adapter: PGAdapter):
    await get_pool().release(adapter.connection)
