"""
Прямая работа с PostgreSQL без слоя совместимости
Совместимость с aiosqlite API: поддерживает и await, и async with db.execute()
"""

import re
import asyncpg
from datetime import datetime
from typing import Any, List, Dict
from config import DATABASE_PATH


_pg_pool = None

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


async def get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        if not DATABASE_PATH.startswith(('postgresql://', 'postgres://')):
            raise RuntimeError(f"DATABASE_PATH должен быть PostgreSQL DSN, получен: {DATABASE_PATH}")
        _pg_pool = await asyncpg.create_pool(
            DATABASE_PATH, min_size=2, max_size=20,
            server_settings={'application_name': 'PredvestnikBot', 'timezone': 'UTC'}
        )
    return _pg_pool


async def close_pg_pool():
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None


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
        if sql_upper.startswith(('SELECT', 'WITH')) or 'RETURNING' in sql_upper:
            self._rows = list(await self._conn.fetch(sql, *params))
            self._status = f"SELECT {len(self._rows)}"
        else:
            self._status = await self._conn.execute(sql, *params)  # e.g. "UPDATE 3"
            self._rows = []

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
            except (KeyError, IndexError, TypeError):
                pass
        return None

    @property
    def rowcount(self):
        # asyncpg returns status like "UPDATE 3", "DELETE 1", "INSERT 0 1"
        if self._status:
            try:
                return int(str(self._status).split()[-1])
            except (IndexError, ValueError):
                pass
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

    async def fetch(self, sql, params=None):
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        sql, params = _convert_placeholders(sql, params)
        return await self._conn.fetch(sql, *params)

    async def fetchone(self, sql, params=None):
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        sql, params = _convert_placeholders(sql, params)
        return await self._conn.fetchrow(sql, *params)

    async def fetchval(self, sql, params=None):
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        sql, params = _convert_placeholders(sql, params)
        return await self._conn.fetchval(sql, *params)

    async def executemany(self, sql, params_list):
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        for params in params_list:
            sql_conv, params_conv = _convert_placeholders(sql, params)
            await self._conn.execute(sql_conv, *params_conv)

    async def commit(self):
        pass  # auto-commit in __aexit__

    async def rollback(self):
        if self._tx:
            await self._tx.rollback()


async def execute_query(sql, *params):
    async with PostgresConnection() as db:
        return await db.execute(sql, list(params) if params else None)


async def fetch_all(sql, *params):
    async with PostgresConnection() as db:
        return await db.fetch(sql, list(params) if params else None)


async def fetch_one(sql, *params):
    async with PostgresConnection() as db:
        return await db.fetchone(sql, list(params) if params else None)


async def fetch_value(sql, *params):
    async with PostgresConnection() as db:
        return await db.fetchval(sql, list(params) if params else None)


connect = PostgresConnection


class PostgresDDLConnection:
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

    async def execute(self, sql, params=None):
        if not self._conn:
            raise RuntimeError("Соединение не установлено")
        sql, params = _convert_placeholders(sql, params)
        return await self._conn.execute(sql, *params)


ddl_connect = PostgresDDLConnection

Row = asyncpg.Record
