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
import time
import asyncpg
from loguru import logger
from urllib.parse import urlparse

from core import ops_metrics
from infrastructure.pg_adapter import PGAdapter
from infrastructure.preprod import assert_preprod_environment, is_preprod

_pool: asyncpg.Pool | None = None
_pool_dsn: str | None = None          # the source the pool connected through; direct connections reuse it
_pool_create_lock = asyncio.Lock()
_SCHEMA = "predvestnik"
# Shown in pg_stat_activity: the managed cluster is shared with the IESA site, so its connection count
# can only be split between the two by this name (see server_connection_usage).
APP_NAME = "predvestnik"


# Long-lived connections outside the pool: the bot's single-instance advisory lock and the LISTEN for live
# player events (connect_direct). They used to sit in the pool for good; the process total stays the same.
DIRECT_CONNECTIONS = 2


def _pool_max_size() -> int:
    """Keep one app process inside a small share of managed-Postgres slots: DB_POOL_MAX_SIZE is the
    process total (the cluster limit is shared with the IESA site), the direct connections included."""
    try:
        configured = int(os.environ.get("DB_POOL_MAX_SIZE", "10"))
    except ValueError:
        configured = 10
    return max(2, min(configured, 10) - DIRECT_CONNECTIONS)


def _server_settings(statement_timeout_ms: int) -> dict:
    return {
        "search_path": f"{_SCHEMA},public",
        "statement_timeout": str(statement_timeout_ms),
        "application_name": APP_NAME,
    }


def _acquire_timeout_sec() -> float:
    """How long a bot update or request waits for a free pool connection before giving up with PoolBusy."""
    try:
        return max(1.0, float(os.environ.get("DB_ACQUIRE_TIMEOUT_SEC", "10")))
    except ValueError:
        return 10.0


class PoolBusy(RuntimeError):
    """No free pool connection within DB_ACQUIRE_TIMEOUT_SEC: the caller answers «busy» instead of hanging."""


async def acquire_connection(pool: asyncpg.Pool, source: str) -> asyncpg.Connection:
    """Take a pool connection with a time limit; the wait is measured per source ("http", "bot", …)."""
    started = time.perf_counter()
    timeout = _acquire_timeout_sec()
    try:
        return await pool.acquire(timeout=timeout)
    except asyncio.TimeoutError:
        ops_metrics.count("pool_timeout", source)
        raise PoolBusy(f"no free database connection within {timeout:.0f} s ({source})") from None
    finally:
        ops_metrics.observe("pool_wait", source, (time.perf_counter() - started) * 1000)


def _statement_timeout_ms() -> int:
    """Server-side per-statement cap: зависший запрос не держит соединение пула.
    30с с запасом покрывает самые тяжёлые легитимные запросы (leaderboard/биржа);
    DDL идемпотентного старта состоит из миллисекундных выражений."""
    try:
        return max(1000, int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "30000")))
    except ValueError:
        return 30000


def _mask_url(url: str) -> str:
    try:
        p = urlparse(url)
        return url.replace(p.password, "***") if p.password else url
    except Exception:
        return "<unparseable>"


async def _tcp_test(host: str, port: int, timeout: float = 8.0) -> str:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return "OK"
    except asyncio.TimeoutError:
        return f"TIMEOUT {timeout}s"
    except ConnectionRefusedError:
        return "REFUSED"
    except OSError as exc:
        return f"OSError: {exc}"


async def _diagnose(host: str, port: int, label: str = "") -> None:
    """DNS lookup + multi-port TCP scan — pinpoints whether it's routing or port-specific."""
    loop = asyncio.get_running_loop()
    prefix = f"[{label}] " if label else ""

    # ── DNS ──────────────────────────────────────────────────────────────────
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ips = [i[4][0] for i in infos]
        logger.info(f"🔍 {prefix}DNS  {host} → {ips}")
    except Exception as exc:
        logger.error(f"❌ {prefix}DNS  FAIL {host}: {type(exc).__name__}: {exc}")
        return

    # ── TCP scan: test multiple ports in parallel ─────────────────────────────
    test_ports = sorted({port, 25060, 25061, 5432})
    results = await asyncio.gather(*[_tcp_test(host, p) for p in test_ports])
    for p, r in zip(test_ports, results):
        marker = "✅" if r == "OK" else "❌"
        logger.info(f"{marker} {prefix}TCP  {host}:{p} → {r}")


async def create_pool() -> asyncpg.Pool:
    """Create the process pool once, even under concurrent startup probes."""
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_create_lock:
        if _pool is None:
            _pool = await _create_pool_unlocked()
    return _pool


async def _create_pool_unlocked() -> asyncpg.Pool:
    """Idempotent — returns the existing pool if already initialised.

    Tries every available connection-string source in order:
      1. DATABASE_URL              — DO-managed binding (${db.connection_string}),
                                       refreshed whenever the database is (re)attached
                                       to this component via the App Platform UI.
      2. PREDVESTNIK_DATABASE_URL  — manually-set fallback (private VPC URL).

    For each source we run DNS+TCP diagnostics first, then attempt asyncpg
    connection (2 tries, 5 s backoff). The first source that connects wins.
    """
    global _pool, _pool_dsn
    if _pool is not None:
        return _pool

    if is_preprod():
        # Never try the production-compatible fallback in the test process.
        # This check happens before DNS/TCP diagnostics or an asyncpg call.
        assert_preprod_environment()

    _candidates: list[tuple[str, str]] = []
    _source_names = ("DATABASE_URL",) if is_preprod() else ("DATABASE_URL", "PREDVESTNIK_DATABASE_URL")
    for _name in _source_names:
        _val = os.environ.get(_name, "").strip()
        if _val:
            _candidates.append((_name, _val))

    if not _candidates:
        raise RuntimeError("Нет DATABASE_URL и PREDVESTNIK_DATABASE_URL!")

    logger.info(f"📦 asyncpg version: {asyncpg.__version__}")
    logger.info(
        f"🔬 Источники подключения ({len(_candidates)}): "
        + ", ".join(n for n, _ in _candidates)
    )

    # ── Log + diagnose every candidate up front ────────────────────────────
    for _name, _url in _candidates:
        logger.info(f"🔌 [{_name}] URL (masked) = {_mask_url(_url)}")
        try:
            _p = urlparse(_url)
            _host = _p.hostname or "unknown"
            _port = _p.port or 5432
            logger.info(f"🌐 [{_name}] Цель: {_host}:{_port} (db={_p.path.lstrip('/')})")
            await _diagnose(_host, _port, label=_name)
        except Exception as exc:
            logger.warning(f"⚠️  [{_name}] диагностика провалена: {exc!r}")

    inet = await _tcp_test("8.8.8.8", 53, timeout=5.0)
    logger.info(f"{'✅' if inet == 'OK' else '❌'} Internet  8.8.8.8:53 → {inet}")
    logger.info("🔬 Диагностика завершена, пробуем asyncpg...")

    # ── Try connecting with each candidate in order ────────────────────────
    last_exc: Exception | None = None
    for _name, _url in _candidates:
        logger.info(f"🐘 Пробуем подключиться через [{_name}]...")
        for attempt in range(1, 3):
            logger.info(f"🐘 [{_name}] asyncpg create_pool — попытка {attempt}/2 (timeout=30s)...")
            try:
                pool = await asyncpg.create_pool(
                    _url,
                    min_size=1,
                    max_size=_pool_max_size(),
                    statement_cache_size=0,   # required for DO managed PG / pgbouncer
                    timeout=30,
                    server_settings=_server_settings(_statement_timeout_ms()),
                    init=_set_schema,
                )
                _pool_dsn = _url
                logger.info(
                    f"✅ PostgreSQL pool готов через [{_name}] "
                    f"(min=1 max={_pool_max_size()}, schema={_SCHEMA})"
                )
                return pool
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    f"⚠️  [{_name}] попытка {attempt}/2 ПРОВАЛЕНА: {type(exc).__name__}: {exc!r}"
                )
                if attempt < 2:
                    logger.info(f"⏳ Ждём 5с перед попыткой {attempt + 1}...")
                    await asyncio.sleep(5)
        logger.warning(f"💀 [{_name}] провален, переходим к следующему источнику...")

    logger.error(f"💀 Все источники подключения провалились. Последняя ошибка: {last_exc!r}")
    raise last_exc  # type: ignore[misc]


async def _set_schema(conn: asyncpg.Connection):
    """Called when a new connection is added to the pool."""
    await conn.execute(f"SET search_path TO {_SCHEMA}, public")


async def server_connection_usage(conn: asyncpg.Connection) -> dict:
    """Connections open on the whole database server (all databases and apps), ours, and the limit for
    ordinary roles. When ``total`` reaches ``limit`` the server refuses new connections
    ("remaining connection slots are reserved ...") to everyone, the site included."""
    row = await conn.fetchrow(
        """
        SELECT count(*) FILTER (WHERE usesysid IS NOT NULL) AS total,
               count(*) FILTER (WHERE usesysid IS NOT NULL AND application_name = $1) AS ours,
               current_setting('max_connections')::int
                 - current_setting('superuser_reserved_connections')::int
                 - COALESCE(current_setting('reserved_connections', true), '0')::int AS limit
          FROM pg_stat_activity
        """, APP_NAME)
    return {"total": int(row["total"]), "ours": int(row["ours"]), "limit": int(row["limit"])}


async def connect_direct(*, statement_timeout_ms: int | None = None) -> asyncpg.Connection:
    """A connection outside the pool, through the same source the pool uses (create_pool first).
    statement_timeout_ms=0 lets a statement wait without limit (the advisory lock waits for the old instance)."""
    if _pool_dsn is None:
        raise RuntimeError("Pool not initialised. Call create_pool() first.")
    timeout = _statement_timeout_ms() if statement_timeout_ms is None else statement_timeout_ms
    return await asyncpg.connect(_pool_dsn, statement_cache_size=0, timeout=30,
                                 server_settings=_server_settings(timeout))


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
