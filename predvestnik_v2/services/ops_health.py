"""«Здоровье»: what slows the service down and which errors players hit, with numbers over 1 h / 24 h / 7 days.

Sources (all in-process, see ``core/ops_metrics.py``):
  http           request time per route template (FastAPI/ops_middleware.py), http_4xx / http_5xx counters
  pool_wait      waiting for a database connection: http (FastAPI/deps.get_db), bot (bot/middlewares/db.py)
  pool_busy      busy connections, sampled every POOL_SAMPLE_EVERY seconds
  db_server      connections open on the whole database server (total, ours, limit), every DB_SERVER_SAMPLE_EVERY s;
                 db_refused counts samples the server refused for lack of free connections
  loop_lag       event-loop delay, sampled every second
  throttle_wait  waiting for the outbound Telegram throttler, per Bot API method
  auth_401       why the Mini App refused a request (FastAPI/deps.py, AUTH_REASONS)
  client         anonymous events from the Mini App (POST /telemetry), stored per event for 14 days
  bot_error      exceptions in aiogram handlers, per handler and exception type (bot/dispatcher.py)

``run`` drains the window every FLUSH_EVERY seconds into ``ops_metrics_5m`` and sends owner alerts.
"""
from __future__ import annotations

import asyncio
import html
import re
import time
import traceback
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger

from core import ops_metrics
from infrastructure.repositories import ops_telemetry as repo

SAMPLE_EVERY = 1.0
POOL_SAMPLE_EVERY = 10.0
DB_SERVER_SAMPLE_EVERY = 60.0
BUFFER_FLUSH_EVERY = 10.0
FLUSH_EVERY = 300
CLEANUP_EVERY = 3600.0
PERIOD_HOURS = (1, 24, 168)

AUTH_REASONS = ("no_header", "malformed", "bad_hash", "stale_auth_date", "user_missing",
                "no_bot_token", "bad_session", "expired_session")

# ── anonymous client telemetry: limits ────────────────────────────────────────
CLIENT_TYPES = ("js_error", "unhandled_rejection", "fetch_fail", "sdk_missing", "boot_timing")
CLIENT_ERROR_TYPES = ("js_error", "unhandled_rejection", "fetch_fail", "sdk_missing")
MAX_BODY_BYTES = 16 * 1024
MAX_EVENTS_PER_REQUEST = 10
PER_IP_PER_MINUTE = 60
PER_SID_PER_HOUR = 40
GLOBAL_PER_MINUTE = 300
STORED_PER_DAY = 20_000
MAX_TRACKED_KEYS = 20_000   # distinct IPs or sids tracked per window; more are refused, not remembered

# ── alerts to the owner ───────────────────────────────────────────────────────
ALERT_COOLDOWN = 3600.0
LOOP_LAG_P95_MS = 1000
POOL_WAIT_P95_MS = 1000
DB_SERVER_SPARE = 3          # alert when fewer free connections are left on the database server
HTTP_5XX_MIN = 20
HTTP_5XX_SHARE = 0.05
CLIENT_ERRORS_MIN = 50
BOT_ERRORS_MIN = 10

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FRAME = re.compile(r"[\w.-]{1,80}\.js:\d{1,7}:\d{1,7}")
_SCRUB = (
    (re.compile(r"(?:https?|wss?)://\S+", re.I), "[ссылка]"),
    (re.compile(r"(?i)(?:tgWebAppData|initData|x-init-data|x-session-token|hash|token|password)\s*[=:]\s*\S+"), "[скрыто]"),
    (re.compile(r"\b\d{5,}\b"), "#"),
    (re.compile(r"[\u0000-\u001f]"), " "),
)


def scrub(text: object, limit: int) -> str:
    """Short single-line text without links, credentials or long numbers (ids)."""
    value = str(text or "")[:2048]
    for pattern, replacement in _SCRUB:
        value = pattern.sub(replacement, value)
    return value.strip()[:limit]


def _route_path(path: object) -> str:
    """API path without query and with numeric/long segments replaced: /u/:value/stats."""
    raw = str(path or "").split("?", 1)[0][:200]
    parts = [p if re.fullmatch(r"[a-z0-9_.:{}-]{1,40}", p) and not re.search(r"\d{3,}", p) else ":value"
             for p in raw.split("/") if p]
    return ("/" + "/".join(parts[:8]))[:120]


@dataclass
class _Limits:
    minute_start: float = 0.0
    hour_start: float = 0.0
    day: str = ""
    global_minute: int = 0
    stored_today: int = 0

    def __post_init__(self) -> None:
        self.per_ip: dict[str, int] = {}
        self.per_sid: dict[str, int] = {}

    def roll(self, now: float) -> None:
        if now - self.minute_start >= 60:
            self.minute_start, self.global_minute, self.per_ip = now, 0, {}
        if now - self.hour_start >= 3600:
            self.hour_start, self.per_sid = now, {}
        today = datetime.now(timezone.utc).date().isoformat()
        if today != self.day:
            self.day, self.stored_today = today, 0

    def take(self, table: dict[str, int], key: str, limit: int) -> bool:
        used = table.get(key)
        if used is None and len(table) >= MAX_TRACKED_KEYS:
            return False
        if (used or 0) >= limit:
            return False
        table[key] = (used or 0) + 1
        return True


_limits = _Limits()
_client_buffer: deque[dict] = deque(maxlen=2000)
_bot_error_buffer: deque[dict] = deque(maxlen=500)
_bot_error_stored_at: dict[tuple[str, str], float] = {}
_last_sample_at = 0.0
_last_flush_at = 0.0
_alerted_at: dict[str, float] = {}


def record_auth_failure(reason: str) -> None:
    ops_metrics.count("auth_401", reason if reason in AUTH_REASONS else "malformed")


def accept_client_events(ip: str, payload: dict) -> tuple[int, bool]:
    """Validate, limit and buffer client events. Returns (accepted, limited).

    The payload is already size-checked and parsed; fields not listed here are ignored."""
    now = time.time()
    _limits.roll(now)
    sid = str(payload.get("sid") or "")
    if not re.fullmatch(r"[a-z0-9]{6,16}", sid):
        ops_metrics.count("client_dropped", "bad_sid")
        return 0, False
    events = payload.get("events")
    if not isinstance(events, list):
        return 0, False
    common = {"sid": sid, "version": scrub(payload.get("version"), 32), "device": scrub(payload.get("device"), 40)}
    accepted, limited = 0, False
    for raw in events[:MAX_EVENTS_PER_REQUEST]:
        if not isinstance(raw, dict) or raw.get("type") not in CLIENT_TYPES:
            ops_metrics.count("client_dropped", "bad_event")
            continue
        if (_limits.global_minute >= GLOBAL_PER_MINUTE or not _limits.take(_limits.per_ip, ip or "?", PER_IP_PER_MINUTE)
                or not _limits.take(_limits.per_sid, sid, PER_SID_PER_HOUR)):
            ops_metrics.count("client_dropped", "rate_limited")
            limited = True
            continue
        _limits.global_minute += 1
        event = _client_event(raw, common, now)
        ops_metrics.count("client", event["type"])
        accepted += 1
        if _limits.stored_today >= STORED_PER_DAY:
            ops_metrics.count("client_dropped", "daily_cap")
            continue
        _limits.stored_today += 1
        _client_buffer.append(event)
    return accepted, limited


def _client_event(raw: dict, common: dict, now: float) -> dict:
    status = raw.get("status")
    detail = {}
    for key in ("ms", "ready_ms", "ttfb_ms", "dom_ms", "load_ms"):
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 600_000:
            detail[key] = round(float(value))
    if isinstance(raw.get("timeout"), bool):
        detail["timeout"] = raw["timeout"]
    path = str(raw.get("path") or "")
    if not (raw["type"] in ("js_error", "unhandled_rejection") and _FRAME.fullmatch(path)):
        path = _route_path(path)   # API route; a script error keeps its file:line:column
    return {**common, "at": datetime.fromtimestamp(now, timezone.utc), "type": raw["type"],
            "screen": _route_path(raw.get("screen")), "path": path,
            "status": int(status) if isinstance(status, int) and not isinstance(status, bool) and 0 <= status <= 999 else None,
            "message": scrub(raw.get("message"), 200), "detail": detail or None}


# ── bot handler errors ────────────────────────────────────────────────────────

def _project_frames(tb) -> list[traceback.FrameSummary]:
    frames = []
    for frame in traceback.extract_tb(tb):
        try:
            relative = Path(frame.filename).resolve().relative_to(_PROJECT_ROOT)
        except ValueError:
            continue
        frame.filename = relative.as_posix()
        frames.append(frame)
    return frames


def handler_name(tb) -> str:
    """The aiogram handler that failed: the first project frame past the dispatcher and middlewares."""
    frames = [f for f in _project_frames(tb) if not f.filename.startswith(("bot/middlewares/", "bot/dispatcher.py"))]
    chosen = next((f for f in frames if f.filename.startswith("bot/")), frames[0] if frames else None)
    return f"{chosen.filename[:-3].replace('/', '.')}:{chosen.name}"[:120] if chosen else "unknown"


def short_trace(tb) -> str:
    """Last project frames as file:line in function — no locals, no exception message (it may quote a player)."""
    return " ← ".join(f"{f.filename}:{f.lineno} {f.name}" for f in reversed(_project_frames(tb)[-6:]))[:600]


def record_bot_error(exc: BaseException, update_type: str = "") -> str:
    handler = handler_name(exc.__traceback__)
    exc_type = type(exc).__name__[:80]
    ops_metrics.count("bot_error", f"{handler}|{exc_type}")
    now = time.time()
    key = (handler, exc_type)
    if now - _bot_error_stored_at.get(key, 0.0) >= 60:   # one stored example per handler and type a minute
        if len(_bot_error_stored_at) > 2000:
            _bot_error_stored_at.clear()
        _bot_error_stored_at[key] = now
        _bot_error_buffer.append({"at": datetime.fromtimestamp(now, timezone.utc), "handler": handler,
                                  "update_type": str(update_type or "")[:40], "exc_type": exc_type,
                                  "trace": short_trace(exc.__traceback__)})
    return handler


# ── background loop ───────────────────────────────────────────────────────────

async def flush_buffers(db) -> None:
    client = [_client_buffer.popleft() for _ in range(len(_client_buffer))]
    errors = [_bot_error_buffer.popleft() for _ in range(len(_bot_error_buffer))]
    try:
        await repo.insert_client_events(db, client)
        await repo.insert_bot_errors(db, errors)
    except Exception:
        _client_buffer.extendleft(reversed(client))
        _bot_error_buffer.extendleft(reversed(errors))
        raise


def _bucket_start(started: float) -> datetime:
    return datetime.fromtimestamp(started - started % FLUSH_EVERY, timezone.utc)


def _trim(buckets: list[int]) -> list[int]:
    """Drop trailing empty buckets: most timings are fast, so stored rows stay short."""
    end = len(buckets)
    while end > 1 and not buckets[end - 1]:
        end -= 1
    return buckets[:end]


async def flush_window(db) -> ops_metrics.Window:
    global _last_flush_at
    window = ops_metrics.registry.drain()
    timings = [(k, n, s.count, s.total, s.peak, _trim(s.buckets)) for (k, n), s in window.timings.items()]
    counters = [(k, n, c) for (k, n), c in window.counters.items()]
    try:
        await repo.save_window(db, _bucket_start(window.started), timings, counters)
    except Exception:
        ops_metrics.registry.restore(window)
        raise
    _last_flush_at = time.time()
    return window


async def _sample_loop() -> None:
    global _last_sample_at
    loop = asyncio.get_running_loop()
    next_pool = 0.0
    while True:
        expected = loop.time() + SAMPLE_EVERY
        await asyncio.sleep(SAMPLE_EVERY)
        ops_metrics.observe("loop_lag", "event_loop", max(0.0, loop.time() - expected) * 1000)
        _last_sample_at = time.time()
        if loop.time() >= next_pool:
            next_pool = loop.time() + POOL_SAMPLE_EVERY
            try:
                from infrastructure.database import get_pool
                pool = get_pool()
                ops_metrics.observe("pool_busy", "connections", pool.get_size() - pool.get_idle_size())
            except RuntimeError:   # pool not created yet
                pass


async def _db_server_loop() -> None:
    """How full the shared database server is: the site and the bot draw from the same connection limit."""
    import asyncpg
    from infrastructure.database import get_pool, server_connection_usage
    while True:
        await asyncio.sleep(DB_SERVER_SAMPLE_EVERY)
        try:
            async with get_pool().acquire(timeout=5) as conn:
                usage = await asyncio.wait_for(server_connection_usage(conn), 5)
        except asyncpg.TooManyConnectionsError:
            ops_metrics.count("db_refused", "server_full")
            continue
        except Exception as exc:   # a sample is optional: never let a dropped connection stop the health loops
            logger.warning(f"database server usage not sampled: {type(exc).__name__}: {exc}")
            continue
        for name, value in usage.items():
            ops_metrics.observe("db_server", name, value)


async def _flush_loop(db_factory, bot) -> None:
    loop = asyncio.get_running_loop()
    next_window = loop.time() + FLUSH_EVERY
    next_cleanup = loop.time() + 60
    while True:
        await asyncio.sleep(BUFFER_FLUSH_EVERY)
        try:
            async with db_factory() as db:
                await flush_buffers(db)
                if loop.time() >= next_window:
                    next_window = loop.time() + FLUSH_EVERY
                    window = await flush_window(db)
                    await check_alerts(db, window, bot)
                if loop.time() >= next_cleanup:
                    next_cleanup = loop.time() + CLEANUP_EVERY
                    await repo.cleanup(db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"ops health flush failed: {type(exc).__name__}: {exc}")


async def run(db_factory, bot=None) -> None:
    """Sampler and writer; started once by the bot process (bot/__main__.py)."""
    await asyncio.gather(_sample_loop(), _db_server_loop(), _flush_loop(db_factory, bot))


# ── alerts ────────────────────────────────────────────────────────────────────

def alerts_for(window: ops_metrics.Window) -> list[tuple[str, str]]:
    """(key, text) for every threshold the closed window crossed."""
    found = []
    lag = window.timings.get(("loop_lag", "event_loop"))
    if lag and lag.count >= 30 and ops_metrics.percentile(lag.buckets, 0.95, lag.peak) > LOOP_LAG_P95_MS:
        found.append(("loop_lag", f"Сервер подтормаживает: задержка обработки (p95) {ops_metrics.percentile(lag.buckets, 0.95, lag.peak) / 1000:.1f} с за 5 минут."))
    waits = ops_metrics.Series()
    for (kind, _), series in window.timings.items():
        if kind == "pool_wait":
            waits.merge(series)
    if waits.count >= 10 and ops_metrics.percentile(waits.buckets, 0.95, waits.peak) > POOL_WAIT_P95_MS:
        found.append(("pool_wait", f"Не хватает соединений с базой: запросы ждут до {ops_metrics.percentile(waits.buckets, 0.95, waits.peak) / 1000:.1f} с (p95)."))
    total, limit = window.timings.get(("db_server", "total")), window.timings.get(("db_server", "limit"))
    refused = window.counters.get(("db_refused", "server_full"), 0)
    if refused or (total and limit and total.peak >= limit.peak - DB_SERVER_SPARE):
        ours = window.timings.get(("db_server", "ours"))
        busy = f"занято до {total.peak:.0f} из {limit.peak:.0f}, из них Предвестник — {ours.peak if ours else 0:.0f}" if total and limit else "сервер базы отказал в соединении"
        found.append(("db_server", f"На сервере базы кончаются соединения: {busy}. Остальные держат другие подключения к той же базе (сайт IESA)."))
    requests = sum(s.count for (kind, _), s in window.timings.items() if kind == "http")
    errors_5xx = sum(c for (kind, _), c in window.counters.items() if kind == "http_5xx")
    if errors_5xx >= HTTP_5XX_MIN and errors_5xx >= HTTP_5XX_SHARE * max(requests, 1):
        found.append(("http_5xx", f"Всплеск ошибок сервера: {errors_5xx} ответов 5xx из {requests} запросов за 5 минут."))
    client = sum(c for (kind, name), c in window.counters.items() if kind == "client" and name in CLIENT_ERROR_TYPES)
    if client >= CLIENT_ERRORS_MIN:
        found.append(("client", f"Всплеск ошибок у игроков в приложении: {client} за 5 минут."))
    bot_errors = {name: c for (kind, name), c in window.counters.items() if kind == "bot_error"}
    if sum(bot_errors.values()) >= BOT_ERRORS_MIN:
        top = max(bot_errors, key=bot_errors.get)
        found.append(("bot_error", f"Всплеск ошибок бота: {sum(bot_errors.values())} за 5 минут, чаще всего {html.escape(top)}."))
    return found


async def check_alerts(db, window: ops_metrics.Window, bot=None) -> list[str]:
    from services import admin_security
    now = time.time()
    sent = []
    for key, text in alerts_for(window):
        if now - _alerted_at.get(key, 0.0) < ALERT_COOLDOWN:
            continue
        _alerted_at[key] = now
        sent.append(key)
        await admin_security.alert(db, text + "\nПодробности: админка → «Состояние» → «Здоровье».", title="Здоровье сервиса")
    return sent


# ── read side ─────────────────────────────────────────────────────────────────

def _merge_live(series: list[dict], counters: list[tuple[str, str, int]]) -> tuple[dict, dict]:
    """Stored aggregates plus the current, not yet written window."""
    timings: dict[tuple[str, str], ops_metrics.Series] = {}
    for item in series:
        merged = ops_metrics.Series(count=item["count"], total=item["total_ms"], peak=item["peak_ms"])
        for index, amount in item["buckets"].items():
            if 0 <= index < len(merged.buckets):
                merged.buckets[index] = amount
        timings[(item["kind"], item["name"])] = merged
    totals = {(k, n): c for k, n, c in counters}
    live = ops_metrics.registry.window
    for key, s in live.timings.items():
        timings.setdefault(key, ops_metrics.Series()).merge(s)
    for key, c in live.counters.items():
        totals[key] = totals.get(key, 0) + c
    return timings, totals


def _stat(s: ops_metrics.Series) -> dict:
    return {"count": s.count, "p50": ops_metrics.percentile(s.buckets, 0.5, s.peak),
            "p95": ops_metrics.percentile(s.buckets, 0.95, s.peak), "p99": ops_metrics.percentile(s.buckets, 0.99, s.peak),
            "max": round(s.peak, 1)}


async def dashboard(db, hours: int) -> dict:
    hours = hours if hours in PERIOD_HOURS else 1
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    await flush_buffers(db)
    timings, counters = _merge_live(await repo.timing_series(db, since), await repo.counter_totals(db, since))

    def by_kind(kind: str) -> dict[str, ops_metrics.Series]:
        return {name: s for (k, name), s in timings.items() if k == kind}

    def counts(kind: str) -> dict[str, int]:
        return {name: c for (k, name), c in counters.items() if k == kind and c}

    lag = timings.get(("loop_lag", "event_loop"), ops_metrics.Series())
    busy = timings.get(("pool_busy", "connections"), ops_metrics.Series())
    e4, e5 = counts("http_4xx"), counts("http_5xx")
    routes = [{"route": name, **_stat(s), "e4": e4.get(name, 0), "e5": e5.get(name, 0)}
              for name, s in by_kind("http").items()]
    routes.sort(key=lambda r: (r["e5"] > 0, r["p95"], r["count"]), reverse=True)
    bot_errors = sorted(({"handler": name.split("|")[0], "exc": name.split("|")[-1], "count": c}
                         for name, c in counts("bot_error").items()), key=lambda r: r["count"], reverse=True)
    return {
        "hours": hours,
        "loop_lag": _stat(lag),
        "pool_wait": [{"name": n, **_stat(s)} for n, s in sorted(by_kind("pool_wait").items())],
        "pool_busy": {"avg": round(busy.total / busy.count, 1) if busy.count else 0, "max": round(busy.peak)},
        "db_server": {name: round(timings.get(("db_server", name), ops_metrics.Series()).peak)
                      for name in ("total", "ours", "limit")} | {"refused": sum(counts("db_refused").values())},
        "throttle": sorted(({"method": n, **_stat(s)} for n, s in by_kind("throttle_wait").items()),
                           key=lambda r: (r["p95"], r["count"]), reverse=True)[:6],
        "routes": routes[:12],
        "http_total": sum(r["count"] for r in routes), "http_5xx": sum(e5.values()), "http_4xx": sum(e4.values()),
        "auth_401": sorted(({"reason": n, "count": c} for n, c in counts("auth_401").items()),
                           key=lambda r: r["count"], reverse=True),
        "client": {**await repo.client_summary(db, since), "dropped": counts("client_dropped")},
        "bot_errors": {"total": sum(r["count"] for r in bot_errors), "top": bot_errors[:10],
                       "recent": await repo.recent_bot_errors(db, since)},
        "fresh": {"sampled_seconds_ago": round(time.time() - _last_sample_at) if _last_sample_at else None,
                  "written_seconds_ago": round(time.time() - _last_flush_at) if _last_flush_at else None},
    }


async def deep_check(timeout: float = 2.0) -> tuple[int, dict]:
    """/api/health/deep: a bounded database ping plus whether the metrics sampler is alive."""
    from infrastructure.database import create_pool
    started = time.perf_counter()
    body: dict = {"status": "ok"}
    try:
        pool = await asyncio.wait_for(create_pool(), timeout)
        async with pool.acquire(timeout=timeout) as conn:
            await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout)
        body["database"] = {"ok": True, "ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:
        body["status"] = "down"
        body["database"] = {"ok": False, "error": type(exc).__name__}
    age = time.time() - _last_sample_at if _last_sample_at else None
    body["metrics"] = {"sampled_seconds_ago": round(age) if age is not None else None, "fresh": age is not None and age < 10}
    if body["status"] == "ok" and not body["metrics"]["fresh"]:
        body["status"] = "degraded"
    return (200 if body["database"]["ok"] else 503), body
