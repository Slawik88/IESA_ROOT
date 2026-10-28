"""«Здоровье» end to end on a local PostgreSQL: 401 reasons, anonymous telemetry, storage, panel, health endpoints.

    DSN=$(bash docs/roadmap/env-setup.sh --fresh-db pv_test_ops_health)   # from the repository root
    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_ops_health_pg.py --dsn "$DSN"
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import time
from urllib.parse import quote, urlparse


def _assert_loopback(dsn: str) -> None:
    if urlparse(dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("this test writes and deletes rows: loopback databases only")


def _init_data(user: dict | None, *, auth_date: int | None = None, good_hash: bool = True, with_hash: bool = True) -> str:
    params = {"auth_date": str(auth_date if auth_date is not None else int(time.time())), "query_id": "AAEtest"}
    if user is not None:
        params["user"] = json.dumps(user, separators=(",", ":"))
    check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest() if good_hash else "0" * 64
    pairs = [f"{k}={quote(v)}" for k, v in params.items()]
    if with_hash:
        pairs.append(f"hash={digest}")
    return "&".join(pairs)


def _expired_session(user_id: int) -> str:
    from FastAPI.auth import _session_secret
    payload = f"{user_id}:{int(time.time()) - 10}"
    return f"{payload}:{hmac.new(_session_secret(), payload.encode(), hashlib.sha256).hexdigest()}"


async def main(dsn: str) -> None:
    os.environ["DATABASE_URL"] = dsn
    import httpx
    from loguru import logger

    from core import ops_metrics
    from FastAPI.main import app
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import ops_telemetry as repo
    from services import admin_security, feature_switches as fs, ops_health

    await create_pool()
    pool = get_pool()
    async with pool.acquire() as conn:
        db = PGAdapter(conn)
        await repo.ensure_tables(db)
        repo._ready = False
        await repo.ensure_tables(db)     # idempotent: a second run on an existing schema changes nothing
        for table in ("ops_metrics_5m", "client_telemetry_events", "bot_handler_errors"):
            await conn.execute(f"DELETE FROM {table}")
    ops_metrics.registry.drain()

    logs: list[str] = []
    sink = logger.add(lambda m: logs.append(str(m)), level="DEBUG")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ── /api/health and /api/ready keep their behaviour ──────────────────
        health = await client.get("/api/health")
        assert health.status_code == 200 and health.json() == {"status": "ok"}
        ready = await client.get("/api/ready")
        assert ready.status_code in (200, 503)
        if ready.status_code == 503:
            assert ready.json() == {"detail": "Service is not ready."}

        deep = await client.get("/api/health/deep")
        assert deep.status_code == 200 and deep.json()["database"]["ok"] is True
        assert deep.json()["status"] == "degraded"            # no sampler is running in this test process
        ops_health._last_sample_at = time.time()
        assert (await client.get("/api/health/deep")).json()["status"] == "ok"

        # ── every 401 reason is counted, the header is never logged ──────────
        user = {"id": 990_200_001, "first_name": "Ops"}
        stale = _init_data(user, auth_date=int(time.time()) - 90_000)
        cases = {
            "no_header": {},
            "malformed": {"x-init-data": _init_data(user, with_hash=False)},
            "bad_hash": {"x-init-data": _init_data(user, good_hash=False)},
            "stale_auth_date": {"x-init-data": stale},
            "user_missing": {"x-init-data": _init_data(None)},
            "bad_session": {"x-session-token": "garbage"},
            "expired_session": {"x-session-token": _expired_session(990_200_001)},
        }
        for reason, headers in cases.items():
            response = await client.get("/profile/me", headers=headers)
            assert response.status_code == 401, (reason, response.status_code)
        counters = ops_metrics.registry.window.counters
        for reason in cases:
            assert counters.get(("auth_401", reason)) == 1, (reason, counters)
        assert counters.get(("http_4xx", "GET /profile/me")) == len(cases)
        assert ("http", "GET /profile/me") in ops_metrics.registry.window.timings
        assert not any(stale in line or "AAEtest" in line for line in logs), "initData leaked into logs"

        # ── telemetry: limits, garbage, privacy, site switch ─────────────────
        ops_health._limits = ops_health._Limits()
        big = {"sid": "abcdef12", "events": [{"type": "js_error", "message": "x" * 20_000}]}
        assert (await client.post("/telemetry", json=big)).status_code == 413

        async def chunks():
            for _ in range(40):
                yield b"x" * 1024
        assert (await client.post("/telemetry", content=chunks())).status_code == 413   # no Content-Length
        assert (await client.post("/telemetry", content=b"{not json")).status_code == 400
        assert (await client.post("/telemetry", json=[1, 2])).status_code == 400

        async with pool.acquire() as conn:
            await fs.ensure_schema(PGAdapter(conn))
            await fs.set_switch(PGAdapter(conn), fs.GLOBAL, "site", False, actor_id=1, reason="тест")
        try:
            closed = await client.get("/profile/me")
            assert closed.status_code == 503, closed.status_code               # the site is really off
            good = {"sid": "abcdef12", "version": "test-v", "device": "ios/phone", "user_id": 990_200_001,
                    "init_data": stale, "username": "ops_user",
                    "events": [{"type": "js_error", "message": "TypeError: boom", "path": "app.01.js:10:5", "screen": "/profile"},
                               {"type": "fetch_fail", "path": "/profile/me", "status": 401, "ms": 120},
                               {"type": "sdk_missing", "message": "opened in Telegram"},
                               {"type": "boot_timing", "ready_ms": 2400, "ttfb_ms": 300}]}
            sent = await client.post("/telemetry", json=good, headers={"x-forwarded-for": "203.0.113.7"})
            assert sent.status_code == 200 and sent.json() == {"accepted": 4}, sent.text   # telemetry ignores the site switch
        finally:
            async with pool.acquire() as conn:
                await fs.set_switch(PGAdapter(conn), fs.GLOBAL, "site", True, actor_id=1)

        limited = None
        for n in range(ops_health.PER_SID_PER_HOUR + 5):   # one page id runs out of its hourly budget
            limited = await client.post("/telemetry", json={"sid": "abcdef12", "events": [{"type": "js_error", "message": str(n)}]},
                                        headers={"x-forwarded-for": "203.0.113.7"})
        assert limited.status_code == 429, limited.status_code

    # ── bot handler error, flush, panel ──────────────────────────────────────
    def failing_handler():
        raise ValueError("text a player typed")
    try:
        failing_handler()
    except ValueError as exc:
        handler = ops_health.record_bot_error(exc, "message")
    assert handler.endswith(":main") or handler.endswith(":failing_handler"), handler

    async with pool.acquire() as conn:
        db = PGAdapter(conn)
        await ops_health.flush_buffers(db)
        rows = await conn.fetch("SELECT * FROM client_telemetry_events ORDER BY id")
        assert len(rows) >= 4
        dump = json.dumps([dict(r) for r in rows], default=str)
        for secret in ("990200001", "ops_user", "AAEtest", "203.0.113.7", "Ops"):
            assert secret not in dump, f"{secret} stored in telemetry"
        assert {r["sid"] for r in rows} == {"abcdef12"}
        stored_errors = await conn.fetch("SELECT handler, exc_type, trace FROM bot_handler_errors")
        assert len(stored_errors) == 1 and "text a player typed" not in stored_errors[0]["trace"]

        panel_live = await ops_health.dashboard(db, 1)          # before the window is written: live numbers
        window = await ops_health.flush_window(db)
        assert window.counters
        panel = await ops_health.dashboard(db, 1)                # after: the same numbers from the table
        for view in (panel_live, panel):
            reasons = {r["reason"]: r["count"] for r in view["auth_401"]}
            assert all(reasons.get(reason) == 1 for reason in cases), reasons
            types = {t["type"]: t["count"] for t in view["client"]["by_type"]}
            assert types.get("js_error", 0) >= 1 and types.get("fetch_fail") == 1 and types.get("sdk_missing") == 1, types
            assert view["client"]["boot"]["count"] == 1 and view["client"]["boot"]["p50_ms"] == 2400
            assert view["bot_errors"]["total"] == 1 and view["bot_errors"]["top"][0]["exc"] == "ValueError"
            assert any(r["route"] == "GET /profile/me" and r["e4"] == len(cases) for r in view["routes"])
            assert view["client"]["dropped"].get("rate_limited", 0) >= 1
        assert any(r["message"] == "TypeError: boom" and r["path"] == "app.01.js:10:5" and r["screen"] == "/profile" for r in rows)
        assert len(panel["client"]["top"]) <= 10

        # the same 5 minutes written twice (two processes during a deploy) add up instead of failing
        bucket = ops_health._bucket_start(time.time())
        await repo.save_window(db, bucket, [("test", "dup", 2, 10.0, 7.0, [1] + [0] * 18 + [1])], [("testc", "dup", 3)])
        await repo.save_window(db, bucket, [("test", "dup", 1, 5.0, 9.0, [0, 1])], [("testc", "dup", 4)])   # trimmed tail
        row = await conn.fetchrow("SELECT count, total_ms, peak_ms, buckets FROM ops_metrics_5m WHERE kind='test'")
        assert (row["count"], row["total_ms"], row["peak_ms"]) == (3, 15.0, 9.0)
        assert list(row["buckets"]) == [1, 1] + [0] * 17 + [1], row["buckets"]
        assert await conn.fetchval("SELECT count FROM ops_metrics_5m WHERE kind='testc'") == 7

        # retention: 14 days, older rows removed, fresh kept
        await conn.execute("INSERT INTO client_telemetry_events (at, sid, type) VALUES (NOW() - INTERVAL '15 days', 'oldsid01', 'js_error')")
        await conn.execute("INSERT INTO bot_handler_errors (at, handler, exc_type) VALUES (NOW() - INTERVAL '15 days', 'old', 'E')")
        await conn.execute("INSERT INTO ops_metrics_5m (bucket_start, kind, name, count) VALUES (NOW() - INTERVAL '15 days', 'old', 'x', 1)")
        removed = await repo.cleanup(db)
        assert removed == {"ops_metrics_5m": 1, "client_telemetry_events": 1, "bot_handler_errors": 1}, removed
        assert await conn.fetchval("SELECT COUNT(*) FROM client_telemetry_events") == len(rows)

    # ── alerts: thresholds and an hour of silence after each one ─────────────
    sent_alerts: list[str] = []

    async def capture(db, text, *, skip=None, title=""):
        sent_alerts.append(f"{title}: {text}")
    original_alert, admin_security.alert = admin_security.alert, capture
    try:
        loud = ops_metrics.Window()
        loud.counters[("bot_error", "bot.chat.x:handle|KeyError")] = 15
        loud.counters[("client", "js_error")] = 80
        async with pool.acquire() as conn:
            assert await ops_health.check_alerts(PGAdapter(conn), loud) == ["client", "bot_error"]
            assert await ops_health.check_alerts(PGAdapter(conn), loud) == []          # cooldown
        assert len(sent_alerts) == 2 and all(a.startswith("Здоровье сервиса") for a in sent_alerts)
    finally:
        admin_security.alert = original_alert

    # ── metrics fill under load: pool wait, loop lag, throttler ──────────────
    ops_metrics.registry.drain()
    from FastAPI.deps import get_db

    async def hold_connection():
        async for _db in get_db():
            await asyncio.sleep(0.05)
    await asyncio.gather(*(hold_connection() for _ in range(60)))
    waits = ops_metrics.registry.window.timings[("pool_wait", "http")]
    assert waits.count == 60 and waits.peak >= 40, (waits.count, waits.peak)   # 60 holders, 10 connections

    sampler = asyncio.create_task(ops_health._sample_loop())
    await asyncio.sleep(1.1)
    time.sleep(2.5)                       # a blocking call freezes the loop past the next tick
    await asyncio.sleep(1.2)
    sampler.cancel()
    lag = ops_metrics.registry.window.timings[("loop_lag", "event_loop")]
    assert lag.peak >= 1000, lag.peak
    assert ("pool_busy", "connections") in ops_metrics.registry.window.timings

    from aiogram.methods import SendMessage
    from bot.middlewares.outbound_throttle import OutboundThrottleMiddleware
    throttle = OutboundThrottleMiddleware()

    async def make_request(bot, method):
        return True
    await asyncio.gather(*(throttle(make_request, None, SendMessage(chat_id=-100, text="x")) for _ in range(3)))
    waits = ops_metrics.registry.window.timings[("throttle_wait", "SendMessage")]
    assert waits.count == 3 and waits.peak >= 2000, waits.peak

    logger.remove(sink)
    await pool.close()
    print("OK: health panel metrics, 401 reasons, telemetry limits and retention on PostgreSQL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    _assert_loopback(args.dsn)
    asyncio.run(main(args.dsn))
