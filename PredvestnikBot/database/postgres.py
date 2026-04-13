"""
Прямая работа с PostgreSQL без слоя совместимости
Совместимость с aiosqlite API: поддерживает и await, и async with db.execute()
"""

import asyncio
import logging
import re
import threading
import time
import asyncpg
from datetime import datetime
from config import DATABASE_PATH

_log = logging.getLogger("db.postgres")


# ─── Per-event-loop pool registry ────────────────────────────────────────────
# Each asyncio event loop (bot loop, Daphne/Django ASGI loop, etc.) gets its
# own dedicated connection pool so that asyncpg sockets are never shared across
# loops ("attached to a different loop" crash).
_pg_pools: dict[int, asyncpg.Pool] = {}
_pg_pool_locks: dict[int, asyncio.Lock] = {}
_pg_meta_lock = threading.Lock()   # protects the dicts themselves

def _maybe_datetime(val):
    """Convert ISO datetime strings to datetime objects for asyncpg TIMESTAMPTZ columns.
    Uses structural validation instead of regex to avoid any ambiguity."""
    if not isinstance(val, str) or len(val) < 19:
        return val
    if val[4] != '-' or val[7] != '-' or val[10] not in ('T', ' '):
        return val
    if val[13] != ':' or val[16] != ':':
        return val
    try:
        return datetime.fromisoformat(val.replace(' ', 'T').replace('Z', '+00:00'))
    except Exception:
        return val


async def get_pg_pool() -> asyncpg.Pool:
    """Return the asyncpg pool bound to the currently running event loop.

    Creates a fresh pool on first call per loop so that the bot's pool and
    the Django/Daphne ASGI pool are always separate objects living on their
    own loops — preventing "attached to a different loop" errors.
    """
    loop = asyncio.get_running_loop()
    loop_id = id(loop)

    # Fast path — pool already initialised for this loop
    if loop_id in _pg_pools:
        return _pg_pools[loop_id]

    # Ensure a per-loop asyncio.Lock exists (thread-safe dict update)
    with _pg_meta_lock:
        if loop_id not in _pg_pool_locks:
            _pg_pool_locks[loop_id] = asyncio.Lock()

    # Slow path — create pool (coroutine-safe within THIS loop via asyncio.Lock)
    async with _pg_pool_locks[loop_id]:
        if loop_id not in _pg_pools:
            if not DATABASE_PATH.startswith(('postgresql://', 'postgres://')):
                raise RuntimeError(
                    f"DATABASE_PATH должен быть PostgreSQL DSN, получен: {DATABASE_PATH}"
                )
            pool = await asyncpg.create_pool(
                DATABASE_PATH,
                min_size=2,
                max_size=20,
                server_settings={
                    'application_name': 'PredvestnikBot',
                    'timezone': 'UTC',
                    'client_encoding': 'UTF8',
                },
            )
            _pg_pools[loop_id] = pool
            _log.info("PG pool created for loop %d (min=2 max=20)", loop_id)

    return _pg_pools[loop_id]
def _convert_placeholders(sql, params):
    if params is None:
        params_list = []
    elif isinstance(params, dict):
        params_list = list(params.values())
    else:
        params_list = list(params)
    # Auto-convert ISO datetime strings to datetime objects for asyncpg
    params_list = [_maybe_datetime(p) for p in params_list]
    if not params_list or '?' not in sql:
        return sql, params_list
    counter = [0]
    def replacer(m):
        counter[0] += 1
        return f'${counter[0]}'
    converted = re.sub(r'\?', replacer, sql)
    return converted, params_list


class _ExecuteContext:
    __slots__ = ('_conn', '_sql', '_params', '_rows', '_status', '_executed')

    def __init__(self, conn, sql, params):
        self._conn = conn
        self._sql = sql
        self._params = params
        self._rows = None
        self._status = None
        self._executed = False

    async def _do_execute(self):
        if self._executed:
            return
        self._executed = True
        sql, params = _convert_placeholders(self._sql, self._params)
        sql_upper = sql.strip().upper()
        _t0 = time.monotonic()
        try:
            if sql_upper.startswith(('SELECT', 'WITH')) or 'RETURNING' in sql_upper:
                self._rows = list(await self._conn.fetch(sql, *params))
                self._status = f"SELECT {len(self._rows)}"
            else:
                self._status = await self._conn.execute(sql, *params)  # e.g. "UPDATE 3"
                self._rows = []
        except Exception as _exc:
            _ms = int((time.monotonic() - _t0) * 1000)
            _log.error(
                "SQL ERROR (%dms) %s | params=%r | error=%s",
                _ms, sql.split()[0].upper(), params, _exc,
            )
            raise
        _ms = int((time.monotonic() - _t0) * 1000)
        _log.debug(
            "SQL %s (%dms) — %s | params=%r",
            self._status, _ms,
            sql.strip().split('\n')[0].strip()[:120],
            params,
        )

    def __await__(self):
        return self._await_impl().__await__()

    async def _await_impl(self):
        await self._do_execute()
        return self

    async def __aenter__(self):
        await self._do_execute()
        return self

    async def __aexit__(self, *args):
        pass

    async def fetchall(self):
        if not self._executed:
            await self._do_execute()
        return self._rows or []

    async def fetchone(self):
        if not self._executed:
            await self._do_execute()
        rows = self._rows or []
        return rows[0] if rows else None

    @property
    def lastrowid(self):
        if self._rows:
            row = self._rows[0]
            try:
                return row['id']
            except (KeyError, IndexError, TypeError) as _e:
                _log.debug("%s", _e)
        return None

    @property
    def rowcount(self):
        # asyncpg returns status like "UPDATE 3", "DELETE 1", "INSERT 0 1"
        if self._status:
            try:
                return int(str(self._status).split()[-1])
            except (IndexError, ValueError) as _e:
                _log.debug("%s", _e)
        return len(self._rows) if self._rows else 0

    def __iter__(self):
        return iter(self._rows or [])


class PostgresConnection:
    def __init__(self):
        self._conn = None
        self._tx = None

    async def __aenter__(self):
        pool = await get_pg_pool()
        self._conn = await pool.acquire()
        self._tx = self._conn.transaction()
        await self._tx.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._tx:
            if exc_type is None:
                await self._tx.commit()
            else:
                await self._tx.rollback()
            self._tx = None
        if self._conn:
            pool = await get_pg_pool()
            await pool.release(self._conn)
            self._conn = None

    def execute(self, sql, params=None):
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        return _ExecuteContext(self._conn, sql, params)

    @staticmethod
    def _resolve_params(args, params):
        """Normalise *args / params keyword so callers may use either:

        Both of these are equivalent:
            fetchone(sql, user_id, chat_id)       # individual positional args
            fetchone(sql, (user_id, chat_id))     # pre-packed tuple / list

        Without this helper, passing a single tuple creates a double-wrap:
            args = ((user_id, chat_id),)   →  params_list = [(user_id, chat_id)]
        which causes asyncpg to receive a tuple instead of individual scalars —
        that is the root cause of the 'tuple object cannot be interpreted as int'
        and 'server expects 2 arguments, 1 was passed' family of errors.
        """
        if params is not None:
            return params
        if not args:
            return None
        # Single positional argument that is itself a sequence → unwrap
        if len(args) == 1 and isinstance(args[0], (tuple, list)):
            return args[0]
        return args  # multiple scalar positional args

    async def fetch(self, sql, *args, params=None):
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        params = self._resolve_params(args, params)
        sql, params = _convert_placeholders(sql, params)
        return await self._conn.fetch(sql, *params)

    async def fetchone(self, sql, *args, params=None):
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        params = self._resolve_params(args, params)
        sql, params = _convert_placeholders(sql, params)
        return await self._conn.fetchrow(sql, *params)

    # Alias for code that uses raw asyncpg calling convention
    fetchrow = fetchone

    async def fetchval(self, sql, *args, params=None):
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        params = self._resolve_params(args, params)
        sql, params = _convert_placeholders(sql, params)
        return await self._conn.fetchval(sql, *params)
    async def commit(self):
        pass  # auto-commit in __aexit__

    async def rollback(self):
        if self._tx:
            await self._tx.rollback()
        self._conn = None


class PostgresDDLConnection:
    """Connection without explicit transaction — each statement auto-commits.

    Used for DDL operations (CREATE TABLE IF NOT EXISTS, ALTER TABLE …) where
    individual statement failures must not roll back previously applied DDL.
    """

    def __init__(self):
        self._conn = None

    async def __aenter__(self):
        pool = await get_pg_pool()
        self._conn = await pool.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            pool = await get_pg_pool()
            await pool.release(self._conn)
            self._conn = None

    def execute(self, sql, params=None):
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        return _ExecuteContext(self._conn, sql, params)

    async def commit(self):
        pass  # asyncpg auto-commits outside explicit transactions


connect = PostgresConnection
ddl_connect = PostgresDDLConnection

Row = asyncpg.Record
