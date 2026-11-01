"""
infrastructure/db.py
Тонкий адаптер доступа к данным «Домового»: aiosqlite в разработке, asyncpg в проде.

SQL везде пишется с плейсхолдерами `?` и явно перечисленными колонками; для
PostgreSQL плейсхолдеры переводятся в $1..$N. Строки — отображения по имени
колонки. Деньги — целые копейки, даты — строки 'YYYY-MM-DD' (UTC).
"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import aiosqlite
import asyncpg
from loguru import logger

from core import config


class DB:
    """Единая точка доступа к БД. Пул — для PostgreSQL, одно соединение — для sqlite."""

    def __init__(self) -> None:
        self._url = config.database_url()
        self._is_pg = self._url.startswith(("postgres://", "postgresql://"))
        self._pool: asyncpg.Pool | None = None
        self._sqlite: aiosqlite.Connection | None = None
        self._sqlite_lock = asyncio.Lock()

    @property
    def is_postgres(self) -> bool:
        """Текущий диалект: True — PostgreSQL, False — sqlite."""
        return self._is_pg

    # ── Жизненный цикл ───────────────────────────────────────────────────────
    async def connect(self) -> None:
        if self._is_pg:
            self._pool = await asyncpg.create_pool(self._url, min_size=1, max_size=5, timeout=30)
            logger.info("🐘 Домовой: PostgreSQL-пул готов")
        else:
            # sqlite://F:\path\domovoy.db — urlparse съедает букву диска, режем вручную.
            path = self._url
            for prefix in ("sqlite://", "sqlite:"):
                if path.startswith(prefix):
                    path = path[len(prefix):]
                    break
            self._sqlite = await aiosqlite.connect(path)
            self._sqlite_lock = asyncio.Lock()
            self._sqlite.row_factory = aiosqlite.Row
            await self._sqlite.execute("PRAGMA journal_mode=WAL")
            await self._sqlite.execute("PRAGMA foreign_keys=ON")
            await self._sqlite.commit()
            logger.info(f"📄 Домовой: sqlite готов ({path})")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
        if self._sqlite is not None:
            await self._sqlite.close()

    # ── Соединение ───────────────────────────────────────────────────────────
    @asynccontextmanager
    async def acquire(self):
        """Отдаёт адаптер соединения; для pg — из пула, для sqlite — единственное."""
        if self._is_pg:
            async with self._pool.acquire() as conn:
                yield _PgConn(conn)
        else:
            # Одно соединение нельзя делить с чужой незавершённой транзакцией.
            async with self._sqlite_lock:
                yield _SqliteConn(self._sqlite)

    @asynccontextmanager
    async def transaction(self):
        """Многошаговая операция — одна транзакция (CLEAN_CODE 5.4)."""
        async with self.acquire() as conn:
            if self._is_pg:
                async with conn._conn.transaction():
                    yield conn
            else:
                await conn._conn.execute("BEGIN")
                conn._in_tx = True
                try:
                    yield conn
                except BaseException:
                    await conn._conn.execute("ROLLBACK")
                    raise
                else:
                    await conn._conn.execute("COMMIT")
                finally:
                    conn._in_tx = False


class _BaseConn:
    """Общий контракт: fetch/fetchrow/execute/insert + JSON-помощники."""

    async def fetch(self, sql: str, *args) -> list:
        raise NotImplementedError

    async def fetchrow(self, sql: str, *args):
        raise NotImplementedError

    async def execute(self, sql: str, *args) -> int:
        """UPDATE/DELETE/DDL → число затронутых строк."""
        raise NotImplementedError

    async def insert(self, sql: str, *args) -> int:
        """INSERT без RETURNING → id новой строки."""
        raise NotImplementedError

    @staticmethod
    def dumps(value) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def loads(raw, default):
        return json.loads(raw) if raw is not None else default


class _PgConn(_BaseConn):
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def fetch(self, sql: str, *args) -> list:
        return await self._conn.fetch(_to_pg(sql), *args)

    async def fetchrow(self, sql: str, *args):
        return await self._conn.fetchrow(_to_pg(sql), *args)

    async def execute(self, sql: str, *args) -> int:
        status = await self._conn.execute(_to_pg(sql), *args)
        return _pg_rowcount(status)

    async def insert(self, sql: str, *args) -> int:
        return await self._conn.fetchval(_to_pg(sql) + " RETURNING id", *args)


class _SqliteConn(_BaseConn):
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn
        self._in_tx = False  # True, пока открыта явная транзакция: коммитит только transaction()

    async def fetch(self, sql: str, *args) -> list:
        cur = await self._conn.execute(sql, args)
        return list(await cur.fetchall())

    async def fetchrow(self, sql: str, *args):
        cur = await self._conn.execute(sql, args)
        return await cur.fetchone()

    async def execute(self, sql: str, *args) -> int:
        cur = await self._conn.execute(sql, args)
        if not self._in_tx:
            await self._conn.commit()
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    async def insert(self, sql: str, *args) -> int:
        cur = await self._conn.execute(sql, args)
        if not self._in_tx:
            await self._conn.commit()
        return cur.lastrowid


def _to_pg(sql: str) -> str:
    """`?` → `$1..$N` (вне строковых литералов — SQL «Домового» литералов не склеивает)."""
    if "?" not in sql:
        return sql
    out, index = [], 0
    in_literal = False
    for ch in sql:
        if ch == "'":
            in_literal = not in_literal
        if ch == "?" and not in_literal:
            index += 1
            out.append(f"${index}")
        else:
            out.append(ch)
    return "".join(out)


def _pg_rowcount(status: str) -> int:
    try:
        return int(status.split()[-1])
    except (ValueError, IndexError):
        return 0


def now_utc() -> str:
    """Метка времени для TEXT-колонок: naive UTC 'YYYY-MM-DD HH:MM:SS'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


db = DB()
