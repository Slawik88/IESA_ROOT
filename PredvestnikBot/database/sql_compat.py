import re
from typing import Any, Iterable

import aiosqlite as _sqlite


def _is_postgres_dsn(value: str) -> bool:
    v = (value or "").lower()
    return v.startswith("postgres://") or v.startswith("postgresql://")


def _convert_placeholders(sql: str) -> str:
    out: list[str] = []
    idx = 1
    for ch in sql:
        if ch == "?":
            out.append(f"${idx}")
            idx += 1
        else:
            out.append(ch)
    return "".join(out)


def _normalize_sql_for_postgres(sql: str) -> str | None:
    s = sql.strip()
    if not s:
        return s

    # SQLite-only pragma.
    if s.upper().startswith("PRAGMA "):
        return None

    normalized = sql
    normalized = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "BIGSERIAL PRIMARY KEY",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+COLLATE\s+NOCASE", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bMAX\s*\(\s*0\s*,", "GREATEST(0,", normalized, flags=re.IGNORECASE)

    # Telegram IDs can exceed PostgreSQL's int32 range (~2.1 billion).
    # Convert all INTEGER columns to BIGINT (int64). BIGSERIAL (from AUTOINCREMENT
    # handling above) is unaffected since it no longer contains the word INTEGER.
    normalized = re.sub(r"\bINTEGER\b", "BIGINT", normalized, flags=re.IGNORECASE)

    # Make ALTER TABLE ... ADD COLUMN idempotent: column-already-exists would abort
    # the whole PostgreSQL transaction (try/except in Python doesn't roll it back).
    normalized = re.sub(
        r"\bADD\s+COLUMN\s+(?!IF\s+NOT\s+EXISTS\b)",
        "ADD COLUMN IF NOT EXISTS ",
        normalized,
        flags=re.IGNORECASE,
    )

    if re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", normalized, flags=re.IGNORECASE):
        normalized = re.sub(
            r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
            "INSERT INTO",
            normalized,
            flags=re.IGNORECASE,
        )
        if "ON CONFLICT" not in normalized.upper():
            normalized = normalized.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    # Handle INSERT OR REPLACE for channel_types table
    if re.search(r"\bINSERT\s+OR\s+REPLACE\s+INTO\s+channel_types\b", normalized, flags=re.IGNORECASE):
        normalized = re.sub(
            r"\bINSERT\s+OR\s+REPLACE\s+INTO\s+channel_types\s+\(type,\s*chat_id\)",
            "INSERT INTO channel_types (type, chat_id)",
            normalized,
            flags=re.IGNORECASE,
        )
        if "ON CONFLICT" not in normalized.upper():
            normalized = normalized.rstrip().rstrip(";") + " ON CONFLICT (type) DO UPDATE SET chat_id = EXCLUDED.chat_id"

    # Convert SQLite datetime/date functions to PostgreSQL equivalents
    # datetime('now') → NOW()
    normalized = re.sub(r"\bdatetime\s*\(\s*'now'\s*\)", "NOW()", normalized, flags=re.IGNORECASE)
    
    # datetime('now', '-N unit') → NOW() - INTERVAL 'N unit'
    # datetime('now', '+N unit') → NOW() + INTERVAL 'N unit'
    def replace_datetime_offset(match):
        sign = match.group(1)[0]  # + or -
        number = match.group(1)[1:]  # Remove sign
        unit = match.group(2)
        return f"NOW() {sign} INTERVAL '{number} {unit}'"
    
    normalized = re.sub(
        r"\bdatetime\s*\(\s*'now'\s*,\s*'([+-]\d+)\s+(days?|hours?|minutes?|seconds?)'\s*\)",
        replace_datetime_offset,
        normalized,
        flags=re.IGNORECASE,
    )
    
    # date('now') → CURRENT_DATE
    normalized = re.sub(r"\bdate\s*\(\s*'now'\s*\)", "CURRENT_DATE", normalized, flags=re.IGNORECASE)
    
    # date('now', '-N days') → CURRENT_DATE - INTERVAL 'N days'
    # date('now', '+N days') → CURRENT_DATE + INTERVAL 'N days'
    def replace_date_offset(match):
        sign = match.group(1)[0]  # + or -
        number = match.group(1)[1:]  # Remove sign
        return f"CURRENT_DATE {sign} INTERVAL '{number} days'"
    
    normalized = re.sub(
        r"\bdate\s*\(\s*'now'\s*,\s*'([+-]\d+)\s+days?'\s*\)",
        replace_date_offset,
        normalized,
        flags=re.IGNORECASE,
    )

    normalized = _convert_placeholders(normalized)
    return normalized


class _PgCursor:
    def __init__(self, rows: list[Any] | None = None, rowcount: int = 0,
                 lastrowid: int | None = None):
        self._rows = rows or []
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    async def fetchall(self):
        return self._rows

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class _PgExecuteOp:
    def __init__(self, conn: "_PgConnection", sql: str, params: Iterable[Any] | None = None):
        self._conn = conn
        self._sql = sql
        self._params = tuple(params or ())
        self._cursor: _PgCursor | None = None

    async def _run(self) -> _PgCursor:
        if self._cursor is not None:
            return self._cursor

        transformed = _normalize_sql_for_postgres(self._sql)
        if transformed is None:
            self._cursor = _PgCursor([])
            return self._cursor

        stmt = transformed.lstrip().lower()
        is_select = stmt.startswith("select") or stmt.startswith("with")
        has_returning = "returning" in stmt

        if is_select or has_returning:
            rows = await self._conn._raw.fetch(transformed, *self._params)
            row_list = list(rows)
            lastrowid = None
            if has_returning and row_list:
                # Extract first column of first row as lastrowid
                first = row_list[0]
                lastrowid = first[0] if first else None
            self._cursor = _PgCursor(row_list, lastrowid=lastrowid)
        else:
            status = await self._conn._raw.execute(transformed, *self._params)
            # asyncpg returns status strings like "DELETE 1", "UPDATE 3", "INSERT 0 1"
            rowcount = 0
            try:
                rowcount = int(str(status).split()[-1])
            except (ValueError, IndexError, AttributeError):
                pass
            self._cursor = _PgCursor([], rowcount=rowcount)
        return self._cursor

    def __await__(self):
        return self._run().__await__()

    async def __aenter__(self):
        return await self._run()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _PgConnection:
    def __init__(self, raw_conn):
        self._raw = raw_conn
        self.row_factory = None

    def execute(self, sql: str, params: Iterable[Any] | None = None):
        return _PgExecuteOp(self, sql, params)

    async def commit(self):
        # asyncpg auto-commits each statement outside explicit transactions.
        return None


_pg_pool = None
_pg_pool_dsn: str | None = None


async def _get_pg_pool(dsn: str):
    """Return a module-level asyncpg connection pool, creating it on first call."""
    global _pg_pool, _pg_pool_dsn
    if _pg_pool is None or _pg_pool_dsn != dsn:
        import asyncpg
        _pg_pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
        _pg_pool_dsn = dsn
    return _pg_pool


class _PgConnectCtx:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn = None   # PoolConnectionProxy
        self._tx = None     # explicit transaction

    async def __aenter__(self):
        pool = await _get_pg_pool(self._dsn)
        self._conn = await pool.acquire()
        # Start an explicit transaction so all statements in the `async with`
        # block are atomic — matching aiosqlite's transaction semantics where
        # db.commit() finalises the work.
        self._tx = self._conn.transaction()
        await self._tx.start()
        return _PgConnection(self._conn)

    async def __aexit__(self, exc_type, exc, tb):
        if self._tx is not None:
            if exc_type is None:
                await self._tx.commit()
            else:
                await self._tx.rollback()
            self._tx = None
        if self._conn is not None:
            pool = await _get_pg_pool(self._dsn)
            await pool.release(self._conn)
            self._conn = None
        return False


class _CompatAioSqlite:
    Row = _sqlite.Row

    @staticmethod
    def connect(path_or_dsn: str, timeout: float = 20.0):
        if _is_postgres_dsn(path_or_dsn):
            return _PgConnectCtx(path_or_dsn)
        # timeout=20.0 — SQLite will wait up to 20 s for a write lock instead
        # of raising "database is locked" immediately (default timeout=0).
        return _sqlite.connect(path_or_dsn, timeout=timeout)


aiosqlite_compat = _CompatAioSqlite()
