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
import socket
import asyncpg
from loguru import logger
from urllib.parse import urlparse

from infrastructure.pg_adapter import PGAdapter

_pool: asyncpg.Pool | None = None
_SCHEMA = "predvestnik"


def _mask_url(url: str) -> str:
    try:
        p = urlparse(url)
        return url.replace(p.password, "***") if p.password else url
    except Exception:
        return "<unparseable>"


async def _diagnose(host: str, port: int) -> None:
    """DNS lookup + raw TCP connect test — runs before asyncpg to pinpoint failures."""
    loop = asyncio.get_running_loop()

    # ── DNS ──────────────────────────────────────────────────────────────────
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ips = [i[4][0] for i in infos]
        logger.info(f"🔍 DNS  {host} → {ips}")
    except Exception as exc:
        logger.error(f"❌ DNS  FAIL {host}: {type(exc).__name__}: {exc}")
        return

    # ── Raw TCP (no SSL, no PostgreSQL protocol) ──────────────────────────────
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=10
        )
        writer.close()
        await writer.wait_closed()
        logger.info(f"✅ TCP  {host}:{port} → соединение установлено (raw)")
    except asyncio.TimeoutError:
        logger.error(f"❌ TCP  {host}:{port} → TIMEOUT 10s — хост недоступен (firewall/VPC?)")
    except ConnectionRefusedError:
        logger.error(f"❌ TCP  {host}:{port} → CONNECTION REFUSED — порт закрыт")
    except OSError as exc:
        logger.error(f"❌ TCP  {host}:{port} → OSError: {exc}")


async def create_pool() -> asyncpg.Pool:
    """Idempotent — returns the existing pool if already initialised.
    Retries up to 3 times with 5 s backoff for transient network hiccups."""
    global _pool
    if _pool is not None:
        return _pool

    url = os.environ["DATABASE_URL"]
    masked = _mask_url(url)
    logger.info(f"🔌 DATABASE_URL = {masked}")

    # Log asyncpg version for debugging
    logger.info(f"📦 asyncpg version: {asyncpg.__version__}")

    # Parse host/port for diagnostics
    try:
        _p = urlparse(url)
        _host = _p.hostname or "unknown"
        _port = _p.port or 5432
        logger.info(f"🌐 Цель: {_host}:{_port} (db={_p.path.lstrip('/')})")
    except Exception as exc:
        logger.warning(f"⚠️  Не удалось распарсить URL: {exc}")
        _host, _port = "unknown", 5432

    # DNS + TCP diagnostic before attempting asyncpg
    logger.info("🔬 Диагностика сети...")
    await _diagnose(_host, _port)
    logger.info("🔬 Диагностика завершена, пробуем asyncpg...")

    last_exc: Exception | None = None
    for attempt in range(1, 4):
        logger.info(f"🐘 asyncpg create_pool — попытка {attempt}/3 (timeout=30s)...")
        try:
            _pool = await asyncpg.create_pool(
                url,
                min_size=1,
                max_size=15,
                statement_cache_size=0,   # required for DO managed PG / pgbouncer
                timeout=30,
                server_settings={"search_path": f"{_SCHEMA},public"},
                init=_set_schema,
            )
            logger.info(f"✅ PostgreSQL pool готов (min=1 max=15, schema={_SCHEMA})")
            return _pool
        except Exception as exc:
            last_exc = exc
            logger.warning(
                f"⚠️  Попытка {attempt}/3 ПРОВАЛЕНА: {type(exc).__name__}: {exc!r}"
            )
            if attempt < 3:
                logger.info(f"⏳ Ждём 5с перед попыткой {attempt + 1}...")
                await asyncio.sleep(5)

    logger.error(f"💀 Все 3 попытки подключения провалились. Последняя ошибка: {last_exc!r}")
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
