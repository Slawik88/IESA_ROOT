"""infrastructure/lazy_db.py — a pool connection held only while SQL runs (roadmap S03).

The bot and the Mini App share one process and one small pool. A bot update or an HTTP request used to hold
its connection from start to finish, including every Telegram call and the wait for a Telegram send slot:
ten slow Telegram calls were enough to leave the Mini App without connections.

``LazyPGAdapter`` behaves like ``PGAdapter`` (same ``execute``/``commit``/``connection`` API), but:
  * the connection is taken on the first SQL statement, not when the update or request arrives;
  * ``release_current()`` gives it back to the pool whenever no statement and no transaction is open.
    The bot calls it before every Telegram request (``bot/middlewares/db.py``), so a handler never waits for
    Telegram with a connection in hand; the next statement simply takes a connection again.
A transaction (``db.connection.transaction()`` or ``BEGIN`` through ``execute``) keeps its connection until it
ends: that is the only state code may rely on across statements. Session-level state (``SET``, session advisory
locks) must not span a Telegram call — wrap such work in a transaction instead.
Only the task that took the connection may release it early: a background task copied from the handler's
context sees the same adapter and must not pull the connection out from under it.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncIterator

import asyncpg

from infrastructure.database import acquire_connection
from infrastructure.pg_adapter import PGAdapter, _Execute

_current: ContextVar["LazyPGAdapter | None"] = ContextVar("lazy_db_current", default=None)


class LazyPGAdapter(PGAdapter):
    def __init__(self, pool: asyncpg.Pool, *, source: str) -> None:
        super().__init__(None)
        self._pool = pool
        self._source = source        # pool_wait metric name: "bot" or "http"
        self._lock = asyncio.Lock()
        self._busy = 0               # statements in flight
        self._pins = 0               # open transactions started through .connection.transaction()
        self._owner: asyncio.Task | None = None
        self._closed = False

    # ── connection lifecycle ────────────────────────────────────────────────
    async def _ensure(self) -> asyncpg.Connection:
        if self._closed:   # SQL after the update or request ended would take a connection nobody gives back
            raise RuntimeError("database handle used after its update or request ended")
        if self._conn is None:
            async with self._lock:
                if self._conn is None:
                    self._conn = await acquire_connection(self._pool, self._source)
                    self._owner = asyncio.current_task()
        return self._conn

    @asynccontextmanager
    async def _statement(self) -> AsyncIterator[asyncpg.Connection]:
        conn = await self._ensure()
        self._busy += 1
        try:
            yield conn
        finally:
            self._busy -= 1

    @property
    def holds_connection(self) -> bool:
        return self._conn is not None

    async def release_if_idle(self) -> bool:
        """Give the connection back if nothing uses it now. True when it was released."""
        if self._conn is None or self._busy or self._pins or self._tx is not None:
            return False
        if asyncio.current_task() is not self._owner:
            return False
        conn, self._conn = self._conn, None
        await self._pool.release(conn)
        return True

    async def close(self) -> None:
        """End of the update or request: always give the connection back (an open transaction is rolled back)."""
        conn, self._conn, self._tx = self._conn, None, None
        self._closed = True
        if conn is not None:
            await self._pool.release(conn)

    # ── PGAdapter API ───────────────────────────────────────────────────────
    def execute(self, sql: str, args=()):
        return _LazyExecute(self, None, sql, args)

    async def _begin(self):
        await self._ensure()
        await super()._begin()

    @property
    def connection(self) -> "_LazyConnection":
        return _LazyConnection(self)


class _LazyExecute(_Execute):
    async def _run(self):
        if self._done:
            return self._cursor
        async with self._adapter._statement() as conn:
            self._conn = conn
            return await super()._run()


class _LazyConnection:
    """The subset of asyncpg.Connection the code base uses on ``db.connection``."""
    __slots__ = ("_db",)

    def __init__(self, db: LazyPGAdapter) -> None:
        self._db = db

    async def fetch(self, *args, **kwargs):
        async with self._db._statement() as conn:
            return await conn.fetch(*args, **kwargs)

    async def fetchrow(self, *args, **kwargs):
        async with self._db._statement() as conn:
            return await conn.fetchrow(*args, **kwargs)

    async def fetchval(self, *args, **kwargs):
        async with self._db._statement() as conn:
            return await conn.fetchval(*args, **kwargs)

    async def execute(self, *args, **kwargs):
        async with self._db._statement() as conn:
            return await conn.execute(*args, **kwargs)

    async def executemany(self, *args, **kwargs):
        async with self._db._statement() as conn:
            return await conn.executemany(*args, **kwargs)

    def is_in_transaction(self) -> bool:
        conn = self._db._conn
        return bool(conn is not None and conn.is_in_transaction())

    def transaction(self, **kwargs) -> "_LazyTransaction":
        return _LazyTransaction(self._db, kwargs)


class _LazyTransaction:
    __slots__ = ("_db", "_kwargs", "_tx")

    def __init__(self, db: LazyPGAdapter, kwargs: dict) -> None:
        self._db, self._kwargs, self._tx = db, kwargs, None

    async def __aenter__(self):
        conn = await self._db._ensure()
        self._db._pins += 1
        try:
            self._tx = conn.transaction(**self._kwargs)
            return await self._tx.__aenter__()
        except BaseException:
            self._db._pins -= 1
            raise

    async def __aexit__(self, *exc):
        try:
            return await self._tx.__aexit__(*exc)
        finally:
            self._db._pins -= 1


@asynccontextmanager
async def lazy_connection(pool: asyncpg.Pool, *, source: str) -> AsyncIterator[LazyPGAdapter]:
    """A lazy adapter for one bot update, HTTP request or background step; the current one for this context."""
    db = LazyPGAdapter(pool, source=source)
    token = _current.set(db)
    try:
        yield db
    finally:
        try:
            _current.reset(token)
        except ValueError:          # entered and left in different contexts (FastAPI dependency): just clear
            if _current.get() is db:
                _current.set(None)
        await db.close()


async def release_current() -> bool:
    """Called right before a Telegram request: no connection is held while Telegram answers."""
    db = _current.get()
    return bool(db is not None and await db.release_if_idle())
