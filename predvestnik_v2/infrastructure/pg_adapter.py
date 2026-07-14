"""
infrastructure/pg_adapter.py
Wraps asyncpg.Connection to provide an aiosqlite-compatible API.

Auto-coercion: timestamp strings ('YYYY-MM-DD HH:MM:SS') are converted to
datetime objects before passing to asyncpg, since asyncpg requires datetime
for TIMESTAMP columns (unlike aiosqlite which accepted strings).

Automatic translations:
  ?            → $1, $2, $3 ...
  INSERT OR IGNORE INTO  → INSERT INTO ... ON CONFLICT DO NOTHING
  datetime('now')        → NOW()
  datetime('now', '-N day') → NOW() - INTERVAL 'N day'
  datetime('now', $N)    → NOW() + $N::INTERVAL
"""
import re
from datetime import datetime as _datetime, timezone
import asyncpg
from loguru import logger

# Only convert FULL datetime strings (with time component) to datetime objects.
# Date-only strings like '2026-05-31' stay as str — they go to TEXT columns
# (daily_deal_purchases.purchase_date, daily_quests.date, etc.) and asyncpg
# requires str for TEXT.  TIMESTAMP columns receive full '2026-05-31 HH:MM:SS'.
_TS_RE = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?$')


def _coerce_args(args: list) -> list:
    """Convert full datetime strings to datetime objects for asyncpg TIMESTAMP columns."""
    result = []
    for a in args:
        if isinstance(a, _datetime):
            if a.tzinfo is not None:
                a = a.astimezone(timezone.utc).replace(tzinfo=None)
            result.append(a)
            continue
        if isinstance(a, str) and _TS_RE.match(a):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    result.append(_datetime.strptime(a, fmt))
                    break
                except ValueError:
                    continue
            else:
                result.append(a)
        else:
            result.append(a)
    return result


# ── SQL translators ────────────────────────────────────────────────────────────

_PLACEHOLDER_RE = re.compile(r'\?')
_INSERT_OR_IGNORE_RE = re.compile(r'INSERT\s+OR\s+IGNORE\s+INTO', re.IGNORECASE)
# M4: детект RETURNING по границе слова (а не по подстроке — иначе ложные
# срабатывания на словах/литералах, содержащих 'returning').
_RETURNING_RE = re.compile(r'\bRETURNING\b', re.IGNORECASE)

# datetime('now') → NOW()
_DATETIME_NOW_RE = re.compile(r"datetime\('now'\)", re.IGNORECASE)
# datetime('now', '-2 days')  → NOW() - INTERVAL '2 days'
_DATETIME_NOW_MINUS_RE = re.compile(
    r"datetime\('now',\s*'(-[\d.]+\s+\w+)'\)", re.IGNORECASE
)
# datetime('now', '+2 hours') → NOW() + INTERVAL '2 hours'
_DATETIME_NOW_PLUS_RE = re.compile(
    r"datetime\('now',\s*'\+?([\d.]+\s+\w+)'\)", re.IGNORECASE
)
# datetime('now', $N) → NOW() + $N::INTERVAL
_DATETIME_NOW_PARAM_RE = re.compile(
    r"datetime\('now',\s*(\$\d+)\)", re.IGNORECASE
)
# strftime('%Y-%m-%d', 'now', $N) → TO_CHAR(NOW() + $N::INTERVAL, 'YYYY-MM-DD')
# strftime('%Y-%m-%d', 'now')     → TO_CHAR(NOW(), 'YYYY-MM-DD')
_STRFTIME_YYYYMMDD_NOW_RE = re.compile(
    r"strftime\('%Y-%m-%d',\s*'now'(?:,\s*(\$\d+))?\)", re.IGNORECASE
)
# strftime('%Y-%m-%d', col, $N) → TO_CHAR(col + $N::INTERVAL, 'YYYY-MM-DD')
_STRFTIME_YYYYMMDD_COL_RE = re.compile(
    r"strftime\('%Y-%m-%d',\s*(\w+)(?:,\s*(\$\d+))?\)", re.IGNORECASE
)
# strftime('%W', col, $N)  → TO_CHAR(col + $N::INTERVAL, 'IW')
_STRFTIME_WEEK_RE = re.compile(
    r"strftime\('%W',\s*(\w+)(?:,\s*(\$\d+))?\)", re.IGNORECASE
)
# strftime('%m', col, $N)  → TO_CHAR(col + $N::INTERVAL, 'MM')
_STRFTIME_MONTH_RE = re.compile(
    r"strftime\('%m',\s*(\w+)(?:,\s*(\$\d+))?\)", re.IGNORECASE
)


def _pg_sql(sql: str) -> str:
    """Translate SQLite SQL to PostgreSQL SQL."""
    has_insert_or_ignore = bool(_INSERT_OR_IGNORE_RE.search(sql))
    sql = _INSERT_OR_IGNORE_RE.sub('INSERT INTO', sql)

    # Translate ? placeholders to $1, $2, ...
    counter = [0]
    def _ph(m):
        counter[0] += 1
        return f'${counter[0]}'
    sql = _PLACEHOLDER_RE.sub(_ph, sql)

    # Date/time function translations
    sql = _DATETIME_NOW_RE.sub('NOW()', sql)
    sql = _DATETIME_NOW_MINUS_RE.sub(lambda m: f"NOW() - INTERVAL '{m.group(1)}'", sql)
    sql = _DATETIME_NOW_PLUS_RE.sub(lambda m: f"NOW() + INTERVAL '{m.group(1)}'", sql)
    sql = _DATETIME_NOW_PARAM_RE.sub(lambda m: f"NOW() + {m.group(1)}::INTERVAL", sql)

    def _sf_yyyymmdd_now(m):
        param = m.group(1)
        if param:
            return f"TO_CHAR(NOW() + {param}::INTERVAL, 'YYYY-MM-DD')"
        return "TO_CHAR(NOW(), 'YYYY-MM-DD')"
    sql = _STRFTIME_YYYYMMDD_NOW_RE.sub(_sf_yyyymmdd_now, sql)

    def _sf_yyyymmdd_col(m):
        col, param = m.group(1), m.group(2)
        if param:
            return f"TO_CHAR({col} + {param}::INTERVAL, 'YYYY-MM-DD')"
        return f"TO_CHAR({col}, 'YYYY-MM-DD')"
    sql = _STRFTIME_YYYYMMDD_COL_RE.sub(_sf_yyyymmdd_col, sql)

    def _sf_week(m):
        col, param = m.group(1), m.group(2)
        if param:
            return f"TO_CHAR({col} + {param}::INTERVAL, 'IW')"
        return f"TO_CHAR({col}, 'IW')"
    sql = _STRFTIME_WEEK_RE.sub(_sf_week, sql)

    def _sf_month(m):
        col, param = m.group(1), m.group(2)
        if param:
            return f"TO_CHAR({col} + {param}::INTERVAL, 'MM')"
        return f"TO_CHAR({col}, 'MM')"
    sql = _STRFTIME_MONTH_RE.sub(_sf_month, sql)

    # INSERT ... ON CONFLICT DO NOTHING (only if no ON CONFLICT clause already present)
    if has_insert_or_ignore and 'ON CONFLICT' not in sql.upper():
        sql = sql.rstrip(';').rstrip() + ' ON CONFLICT DO NOTHING'

    return sql


# ── Cursor ─────────────────────────────────────────────────────────────────────

class _Cursor:
    """Mimics aiosqlite cursor (supports fetchone, fetchall, iteration)."""
    __slots__ = ('_rows', 'rowcount')

    def __init__(self, rows=None, status: str = ''):
        self._rows: list = list(rows) if rows else []
        try:
            self.rowcount = int(status.split()[-1]) if status else len(self._rows)
        except (ValueError, IndexError, AttributeError):
            self.rowcount = 0

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def __await__(self):
        async def _s():
            return self
        return _s().__await__()


# ── Lazy execute object ────────────────────────────────────────────────────────

class _Execute:
    """
    Returned by PGAdapter.execute().
    Both awaitable (await db.execute(...)) and async context manager
    (async with db.execute(...) as cursor:).
    """
    __slots__ = ('_adapter', '_conn', '_sql', '_args', '_cursor', '_done')

    def __init__(self, adapter: 'PGAdapter', conn, sql, args):
        self._adapter = adapter
        self._conn = conn
        self._sql = sql
        self._args = args
        self._cursor = None
        self._done = False

    async def _run(self) -> _Cursor:
        if self._done:
            return self._cursor
        self._done = True

        sql_upper = self._sql.strip().upper()

        # Handle explicit BEGIN / COMMIT / ROLLBACK via adapter
        if sql_upper in ('BEGIN', 'BEGIN TRANSACTION', 'BEGIN IMMEDIATE', 'BEGIN DEFERRED'):
            await self._adapter._begin()
            self._cursor = _Cursor()
            return self._cursor
        if sql_upper == 'COMMIT':
            await self._adapter.commit()
            self._cursor = _Cursor()
            return self._cursor
        if sql_upper == 'ROLLBACK':
            await self._adapter.rollback()
            self._cursor = _Cursor()
            return self._cursor

        pg_sql = _pg_sql(self._sql)
        args = _coerce_args(list(self._args) if self._args else [])

        try:
            is_select = (
                pg_sql.strip().upper().startswith(('SELECT', 'WITH')) or
                _RETURNING_RE.search(pg_sql) is not None
            )
            if is_select:
                rows = await self._conn.fetch(pg_sql, *args)
                self._cursor = _Cursor(rows)
            else:
                status = await self._conn.execute(pg_sql, *args)
                self._cursor = _Cursor(status=status or '')
        except Exception as exc:
            logger.error(f"PG error: {exc}\nSQL: {pg_sql}\nArgs: {args}")
            raise

        return self._cursor

    def __await__(self):
        return self._run().__await__()

    async def __aenter__(self):
        return await self._run()

    async def __aexit__(self, *_):
        pass

    async def fetchone(self):
        return await (await self._run()).fetchone()

    async def fetchall(self):
        return await (await self._run()).fetchall()


# ── Main adapter ───────────────────────────────────────────────────────────────

class PGAdapter:
    """Drop-in replacement for aiosqlite.Connection backed by asyncpg."""

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn
        self._tx = None        # active asyncpg transaction
        self.row_factory = None  # compatibility shim (ignored)

    # Public interface ─────────────────────────────────────────────────────────

    def execute(self, sql: str, args=()):
        return _Execute(self, self._conn, sql, args)

    async def commit(self):
        if self._tx:
            await self._tx.__aexit__(None, None, None)
            self._tx = None
        # In auto-commit mode (no active tx) this is a no-op.

    async def rollback(self):
        if self._tx:
            try:
                raise RuntimeError("explicit rollback")
            except RuntimeError as exc:
                await self._tx.__aexit__(type(exc), exc, exc.__traceback__)
            self._tx = None

    async def _begin(self):
        """Start explicit transaction (called by BEGIN TRANSACTION handling)."""
        if self._tx is None:
            self._tx = self._conn.transaction()
            await self._tx.__aenter__()

    @property
    def connection(self) -> asyncpg.Connection:
        return self._conn
