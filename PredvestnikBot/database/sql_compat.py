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

    if re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", normalized, flags=re.IGNORECASE):
        normalized = re.sub(
            r"\bINSERT\s+OR\s+IGNORE\s+INTO\b",
            "INSERT INTO",
            normalized,
            flags=re.IGNORECASE,
        )
        if "ON CONFLICT" not in normalized.upper():
            normalized = normalized.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    normalized = _convert_placeholders(normalized)
    return normalized


class _PgCursor:
    def __init__(self, rows: list[Any] | None = None):
        self._rows = rows or []

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

        if is_select:
            rows = await self._conn._raw.fetch(transformed, *self._params)
            self._cursor = _PgCursor(list(rows))
        else:
            await self._conn._raw.execute(transformed, *self._params)
            self._cursor = _PgCursor([])
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


class _PgConnectCtx:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._raw = None

    async def __aenter__(self):
        import asyncpg

        self._raw = await asyncpg.connect(self._dsn)
        return _PgConnection(self._raw)

    async def __aexit__(self, exc_type, exc, tb):
        if self._raw is not None:
            await self._raw.close()
        return False


class _CompatAioSqlite:
    Row = _sqlite.Row

    @staticmethod
    def connect(path_or_dsn: str):
        if _is_postgres_dsn(path_or_dsn):
            return _PgConnectCtx(path_or_dsn)
        return _sqlite.connect(path_or_dsn)


aiosqlite_compat = _CompatAioSqlite()
