"""Operational telemetry storage: 5-minute metric aggregates, anonymous client errors, bot handler errors.

All three tables keep RETENTION_DAYS of history (``cleanup``). None of them stores a Telegram id,
initData, a nickname or a message text: client rows carry only a random per-page ``sid``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

RETENTION_DAYS = 14
_ready = False

_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS ops_metrics_5m (
        bucket_start TIMESTAMPTZ NOT NULL,
        kind         TEXT NOT NULL,
        name         TEXT NOT NULL,
        count        BIGINT NOT NULL DEFAULT 0,
        total_ms     DOUBLE PRECISION NOT NULL DEFAULT 0,
        peak_ms      DOUBLE PRECISION NOT NULL DEFAULT 0,
        buckets      INTEGER[],
        PRIMARY KEY (bucket_start, kind, name)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ops_metrics_5m_kind ON ops_metrics_5m (kind, bucket_start)",
    """CREATE TABLE IF NOT EXISTS client_telemetry_events (
        id      BIGSERIAL PRIMARY KEY,
        at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        sid     TEXT NOT NULL,
        type    TEXT NOT NULL,
        version TEXT NOT NULL DEFAULT '',
        screen  TEXT NOT NULL DEFAULT '',
        device  TEXT NOT NULL DEFAULT '',
        status  INTEGER,
        path    TEXT NOT NULL DEFAULT '',
        message TEXT NOT NULL DEFAULT '',
        detail  JSONB
    )""",
    "CREATE INDEX IF NOT EXISTS idx_client_telemetry_at ON client_telemetry_events (at)",
    "CREATE INDEX IF NOT EXISTS idx_client_telemetry_type ON client_telemetry_events (type, at)",
    """CREATE TABLE IF NOT EXISTS bot_handler_errors (
        id          BIGSERIAL PRIMARY KEY,
        at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        handler     TEXT NOT NULL,
        update_type TEXT NOT NULL DEFAULT '',
        exc_type    TEXT NOT NULL,
        trace       TEXT NOT NULL DEFAULT ''
    )""",
    "CREATE INDEX IF NOT EXISTS idx_bot_handler_errors_at ON bot_handler_errors (at)",
)


async def ensure_tables(db) -> None:
    global _ready
    if _ready:
        return
    conn = db.connection
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('ensure_tables:ops_telemetry', 0))")
        for statement in _STATEMENTS:
            await conn.execute(statement)
    _ready = True


# ── writes ────────────────────────────────────────────────────────────────────

async def save_window(db, bucket_start: datetime, timings: list[tuple], counters: list[tuple]) -> None:
    """timings: (kind, name, count, total_ms, peak_ms, buckets — may be shorter than core.ops_metrics.BUCKETS_MS + 1,
    missing tail = zeros); counters: (kind, name, count).

    Adds to an existing row: during a rolling deploy two processes may flush the same 5 minutes."""
    await ensure_tables(db)
    rows = [(bucket_start, k, n, c, t, p, b) for k, n, c, t, p, b in timings]
    rows += [(bucket_start, k, n, c, 0.0, 0.0, None) for k, n, c in counters]
    if not rows:
        return
    await db.connection.executemany(
        """INSERT INTO ops_metrics_5m (bucket_start, kind, name, count, total_ms, peak_ms, buckets)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           ON CONFLICT (bucket_start, kind, name) DO UPDATE SET
               count = ops_metrics_5m.count + EXCLUDED.count,
               total_ms = ops_metrics_5m.total_ms + EXCLUDED.total_ms,
               peak_ms = GREATEST(ops_metrics_5m.peak_ms, EXCLUDED.peak_ms),
               buckets = CASE WHEN EXCLUDED.buckets IS NULL OR ops_metrics_5m.buckets IS NULL
                              THEN COALESCE(ops_metrics_5m.buckets, EXCLUDED.buckets)
                              ELSE ARRAY(SELECT COALESCE(a, 0) + COALESCE(b, 0) FROM unnest(ops_metrics_5m.buckets, EXCLUDED.buckets) AS t(a, b))
                         END""",
        rows)


async def insert_client_events(db, events: list[dict]) -> None:
    if not events:
        return
    await ensure_tables(db)
    await db.connection.executemany(
        """INSERT INTO client_telemetry_events (at, sid, type, version, screen, device, status, path, message, detail)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)""",
        [(e["at"], e["sid"], e["type"], e["version"], e["screen"], e["device"], e["status"], e["path"], e["message"],
          json.dumps(e["detail"]) if e.get("detail") else None) for e in events])


async def insert_bot_errors(db, errors: list[dict]) -> None:
    if not errors:
        return
    await ensure_tables(db)
    await db.connection.executemany(
        "INSERT INTO bot_handler_errors (at, handler, update_type, exc_type, trace) VALUES ($1, $2, $3, $4, $5)",
        [(e["at"], e["handler"], e["update_type"], e["exc_type"], e["trace"]) for e in errors])


async def cleanup(db, days: int = RETENTION_DAYS) -> dict:
    await ensure_tables(db)
    removed = {}
    for table, column in (("ops_metrics_5m", "bucket_start"), ("client_telemetry_events", "at"), ("bot_handler_errors", "at")):
        status = await db.connection.execute(
            f"DELETE FROM {table} WHERE {column} < NOW() - make_interval(days => $1)", days)
        removed[table] = int(status.split()[-1])
    return removed


# ── reads (health panel) ──────────────────────────────────────────────────────

async def timing_series(db, since: datetime) -> list[dict]:
    """Per (kind, name): summed count, total, peak and bucket counts over the period."""
    await ensure_tables(db)
    conn = db.connection
    totals = await conn.fetch(
        "SELECT kind, name, SUM(count)::bigint AS count, SUM(total_ms) AS total_ms, MAX(peak_ms) AS peak_ms "
        "FROM ops_metrics_5m WHERE bucket_start >= $1 AND buckets IS NOT NULL GROUP BY kind, name", since)
    cells = await conn.fetch(
        "SELECT kind, name, u.idx::int AS idx, SUM(u.v)::bigint AS v "
        "FROM ops_metrics_5m, unnest(buckets) WITH ORDINALITY AS u(v, idx) "
        "WHERE bucket_start >= $1 AND buckets IS NOT NULL GROUP BY kind, name, u.idx", since)
    series = {(r["kind"], r["name"]): {"kind": r["kind"], "name": r["name"], "count": int(r["count"]),
                                       "total_ms": float(r["total_ms"]), "peak_ms": float(r["peak_ms"]), "buckets": {}}
              for r in totals}
    for r in cells:
        if (r["kind"], r["name"]) in series:
            series[(r["kind"], r["name"])]["buckets"][r["idx"] - 1] = int(r["v"])
    return list(series.values())


async def counter_totals(db, since: datetime) -> list[tuple[str, str, int]]:
    await ensure_tables(db)
    rows = await db.connection.fetch(
        "SELECT kind, name, SUM(count)::bigint AS count FROM ops_metrics_5m "
        "WHERE bucket_start >= $1 AND buckets IS NULL GROUP BY kind, name", since)
    return [(r["kind"], r["name"], int(r["count"])) for r in rows]


async def client_summary(db, since: datetime, limit: int = 10) -> dict:
    await ensure_tables(db)
    conn = db.connection
    by_type = await conn.fetch(
        "SELECT type, COUNT(*) AS n, COUNT(DISTINCT sid) AS sessions FROM client_telemetry_events "
        "WHERE at >= $1 GROUP BY type ORDER BY n DESC", since)
    by_version = await conn.fetch(
        "SELECT version, COUNT(*) AS n FROM client_telemetry_events WHERE at >= $1 AND type <> 'boot_timing' "
        "GROUP BY version ORDER BY n DESC LIMIT $2", since, limit)
    top = await conn.fetch(
        "SELECT type, message, path, status, COUNT(*) AS n, COUNT(DISTINCT sid) AS sessions, MAX(at) AS last_at "
        "FROM client_telemetry_events WHERE at >= $1 AND type <> 'boot_timing' "
        "GROUP BY type, message, path, status ORDER BY n DESC LIMIT $2", since, limit)
    boot = await conn.fetchrow(
        "SELECT COUNT(*) AS n, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY (detail->>'ready_ms')::float) AS p50, "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY (detail->>'ready_ms')::float) AS p95 "
        "FROM client_telemetry_events WHERE at >= $1 AND type = 'boot_timing' AND detail ? 'ready_ms'", since)
    return {
        "by_type": [{"type": r["type"], "count": int(r["n"]), "sessions": int(r["sessions"])} for r in by_type],
        "by_version": [{"version": r["version"] or "—", "count": int(r["n"])} for r in by_version],
        "top": [{"type": r["type"], "message": r["message"], "path": r["path"], "status": r["status"],
                 "count": int(r["n"]), "sessions": int(r["sessions"]), "last_at": _iso(r["last_at"])} for r in top],
        "boot": {"count": int(boot["n"]), "p50_ms": round(boot["p50"] or 0), "p95_ms": round(boot["p95"] or 0)},
    }


async def recent_bot_errors(db, since: datetime, limit: int = 10) -> list[dict]:
    await ensure_tables(db)
    rows = await db.connection.fetch(
        "SELECT at, handler, update_type, exc_type, trace FROM bot_handler_errors WHERE at >= $1 "
        "ORDER BY at DESC LIMIT $2", since, limit)
    return [{"at": _iso(r["at"]), "handler": r["handler"], "update_type": r["update_type"],
             "exc_type": r["exc_type"], "trace": r["trace"]} for r in rows]


def _iso(value: datetime | None) -> str:
    return value.astimezone(timezone.utc).isoformat() if value else ""
