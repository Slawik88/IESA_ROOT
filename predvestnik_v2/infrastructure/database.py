"""
infrastructure/database.py
asyncpg connection pool — shared across bot and scheduler.

IMPORTANT: asyncpg calls RESET ALL when returning connections to the pool,
which resets search_path to PostgreSQL default. We fix this via:
  1. server_settings sends search_path as a startup param (survives RESET ALL)
  2. init callback sets it again when connection is first created
  3. init_db() calls ALTER ROLE to make predvestnik the permanent default
"""
import os
import asyncpg
from loguru import logger

from infrastructure.pg_adapter import PGAdapter

_pool: asyncpg.Pool | None = None
_SCHEMA = "predvestnik"


async def create_pool() -> asyncpg.Pool:
    """Idempotent — returns the existing pool if already initialised."""
    global _pool
    if _pool is not None:
        return _pool
    url = os.environ["DATABASE_URL"]
    _pool = await asyncpg.create_pool(
        url,
        min_size=3,
        max_size=15,
        statement_cache_size=0,   # required for DO managed PG / pgbouncer
        # server_settings are sent as PostgreSQL startup parameters;
        # they survive RESET ALL (which asyncpg issues on pool release).
        server_settings={"search_path": f"{_SCHEMA},public"},
        init=_set_schema,
    )
    logger.info(f"✅ PostgreSQL pool готов (min=3 max=15, schema={_SCHEMA})")
    return _pool


async def _set_schema(conn: asyncpg.Connection):
    """Called when a new connection is added to the pool."""
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
