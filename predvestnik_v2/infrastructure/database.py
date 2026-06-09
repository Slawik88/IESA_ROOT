"""
infrastructure/database.py
asyncpg connection pool — shared across bot and scheduler.

IMPORTANT: asyncpg calls RESET ALL when returning connections to the pool,
which resets search_path to PostgreSQL default. We fix this via:
  1. server_settings sends search_path as a startup param (survives RESET ALL)
  2. init callback sets it again when connection is first created
  3. init_db() calls ALTER ROLE to make predvestnik the permanent default
"""
import asyncio
import os
import ssl
import asyncpg
from loguru import logger

from infrastructure.pg_adapter import PGAdapter

_pool: asyncpg.Pool | None = None
_SCHEMA = "predvestnik"

# DigitalOcean Managed PostgreSQL uses an internal CA not present in the
# default system bundle. Passing an explicit ssl= context instead of relying
# on sslmode= in the DSN avoids a 60-second SSL-handshake hang on asyncpg.
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def _clean_url(url: str) -> str:
    """Strip sslmode= from DSN — we pass ssl= explicitly to avoid conflicts."""
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    parsed = urlparse(url)
    if not parsed.query:
        return url
    params = parse_qs(parsed.query, keep_blank_values=True)
    params.pop("sslmode", None)
    new_query = urlencode({k: v[0] for k, v in params.items()})
    return urlunparse(parsed._replace(query=new_query))


async def create_pool() -> asyncpg.Pool:
    """Idempotent — returns the existing pool if already initialised.
    Retries up to 3 times with 5 s backoff for transient network hiccups."""
    global _pool
    if _pool is not None:
        return _pool
    url = _clean_url(os.environ["DATABASE_URL"])
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            _pool = await asyncpg.create_pool(
                url,
                ssl=_ssl_ctx,
                min_size=1,
                max_size=15,
                statement_cache_size=0,   # required for DO managed PG / pgbouncer
                # Fail fast per-connection so the retry loop stays within the
                # DO App Platform health-check window (~90s total).
                timeout=15,
                # server_settings are sent as PostgreSQL startup parameters;
                # they survive RESET ALL (which asyncpg issues on pool release).
                server_settings={"search_path": f"{_SCHEMA},public"},
                init=_set_schema,
            )
            logger.info(f"✅ PostgreSQL pool готов (min=1 max=15, schema={_SCHEMA})")
            return _pool
        except Exception as exc:
            last_exc = exc
            logger.warning(f"⚠️  Попытка {attempt}/3 подключения к PostgreSQL: {exc}")
            if attempt < 3:
                await asyncio.sleep(5)
    raise last_exc  # type: ignore[misc]


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
