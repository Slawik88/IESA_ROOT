#!/usr/bin/env python3
"""Real PostgreSQL proof (roadmap S03): a slow Telegram does not starve the database pool.

The bot and the Mini App share one process and one small pool. Before S03 every bot update held a
connection for the whole handler, including its Telegram calls and the wait for the per-chat send slot,
so ten stuck Telegram calls left the Mini App waiting for a free connection.

1. Ten bot handlers (production db middleware + production outbound middlewares) do SQL and then hang
   on a slow sendMessage; meanwhile Mini App requests (FastAPI get_db) still answer at once with a
   4-connection pool.
2. The same through FastAPI: endpoints on get_db that call Telegram (admin, purge) give the connection back.
3. Lazy handle semantics: a transaction keeps its connection across a Telegram call; a background task copied
   from the handler's context never releases the handler's connection; BEGIN/COMMIT through execute works;
   a full pool answers PoolBusy after DB_ACQUIRE_TIMEOUT_SEC instead of hanging.
4. The single-instance advisory lock and the LISTEN for live player events use their own connections outside
   the pool; the lock waits longer than statement_timeout; LISTEN reconnects after its connection is killed.
5. Read-only and moderation methods (getChatMember, deleteMessage, banChatMember) do not wait for the
   per-chat send slot; sendMessage still keeps 1 message per second per chat.
Only a loopback DSN is accepted.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True)
args = parser.parse_args()
if urlparse(args.dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("only a loopback PostgreSQL DSN is allowed")
os.environ["DATABASE_URL"] = args.dsn
os.environ["DB_POOL_MAX_SIZE"] = "6"   # process total: 4 pooled + 2 direct (lock, LISTEN)
os.environ["DB_ACQUIRE_TIMEOUT_SEC"] = "1"
os.environ["DB_STATEMENT_TIMEOUT_MS"] = "1000"     # the advisory lock below must outlive it
os.environ.setdefault("BOT_TOKEN", "1:pool-test")

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import ChatMemberMember, User

from bot.dispatcher import attach_outbound
from bot.middlewares.db import db_middleware
import httpx
from fastapi import Depends, FastAPI

from FastAPI.deps import get_db
from infrastructure import lazy_db
from FastAPI import notifications
from infrastructure.database import PoolBusy, connect_direct, create_pool, get_pool
from infrastructure.repositories import balance_events

SLOW_SEC = 2.0
CHAT = -1_009_300_000_001


class SlowTelegram(BaseSession):
    """Answers like Telegram, but every call takes ``delay`` seconds; records when each call started."""

    def __init__(self, delay: float) -> None:
        super().__init__()
        self.delay = delay
        self.started: list[tuple[str, float]] = []

    async def close(self) -> None:
        return None

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        self.started.append((name, time.monotonic()))
        await asyncio.sleep(self.delay)
        if name == "SendMessage":
            return method.__returning__.model_validate(
                {"message_id": 1, "date": int(time.time()), "chat": {"id": method.chat_id, "type": "supergroup"},
                 "text": method.text}, context={"bot": bot})
        if name == "GetChatMember":
            return ChatMemberMember(user=User(id=method.user_id, is_bot=False, first_name="p"))
        return True


def production_bot(delay: float) -> tuple[Bot, SlowTelegram]:
    session = SlowTelegram(delay)
    bot = Bot(token="1:pool-test", session=session)
    attach_outbound(session)                      # exactly what bot/__main__.py installs
    return bot, session


async def miniapp_request() -> float:
    started = time.perf_counter()
    agen = get_db()
    db = await agen.__anext__()
    try:
        async with db.execute("SELECT 1") as cursor:
            await cursor.fetchone()
    finally:
        await agen.aclose()
    return time.perf_counter() - started


async def stuck_telegram_does_not_starve_miniapp() -> None:
    bot, _ = production_bot(SLOW_SEC)

    async def handler(event, data):
        db = data["db"]
        async with db.execute("SELECT 1") as cursor:
            await cursor.fetchone()
        await bot.send_message(event, "ответ")      # a different chat each: only the slow Telegram matters

    handlers = [asyncio.create_task(db_middleware(handler, CHAT - n, {})) for n in range(10)]
    await asyncio.sleep(0.3)                         # every handler is now inside its Telegram call
    waits = [await miniapp_request() for _ in range(5)]
    await asyncio.gather(*handlers)
    assert max(waits) < 0.5, f"Mini App waited for a free connection: {[round(w, 2) for w in waits]} s"
    print(f"  10 stuck Telegram calls, Mini App answers in ≤ {max(waits) * 1000:.0f} ms")


async def fastapi_endpoints_release_before_telegram() -> None:
    bot, _ = production_bot(SLOW_SEC)
    app = FastAPI()

    @app.post("/notify/{n}")
    async def notify(n: int, db=Depends(get_db)):
        async with db.execute("SELECT 1") as cursor:
            await cursor.fetchone()
        await bot.send_message(CHAT - 100 - n, "уведомление")
        async with db.execute("SELECT 2") as cursor:      # the handle keeps working after Telegram
            return {"value": (await cursor.fetchone())[0]}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        calls = [asyncio.create_task(client.post(f"/notify/{n}")) for n in range(10)]
        await asyncio.sleep(0.3)
        waits = [await miniapp_request() for _ in range(5)]
        answers = await asyncio.gather(*calls)
    assert all(r.status_code == 200 and r.json() == {"value": 2} for r in answers), [r.text for r in answers]
    assert max(waits) < 0.5, f"FastAPI endpoints held connections over Telegram: {[round(w, 2) for w in waits]} s"
    print(f"  10 admin-like requests stuck in Telegram, Mini App answers in ≤ {max(waits) * 1000:.0f} ms")


async def lazy_handle_semantics() -> None:
    pool = get_pool()
    bot, _ = production_bot(0.2)
    async with lazy_db.lazy_connection(pool, source="bot") as db:
        assert not db.holds_connection, "a connection was taken before any SQL"
        async with db.connection.transaction():
            await db.connection.execute("CREATE TEMP TABLE IF NOT EXISTS s03_probe (v int) ON COMMIT DROP")
            await bot.send_message(CHAT, "внутри транзакции")
            assert db.holds_connection and db.connection.is_in_transaction()
            async with db.connection.transaction():        # savepoint on the same connection
                await db.connection.execute("INSERT INTO s03_probe VALUES (1)")
            assert await db.connection.fetchval("SELECT count(*) FROM s03_probe") == 1
        await bot.send_message(CHAT, "после транзакции")
        assert not db.holds_connection, "idle connection kept over a Telegram call"

        await db.execute("BEGIN")
        await db.execute("SELECT 1")
        await bot.send_message(CHAT, "внутри BEGIN")
        assert db.holds_connection, "BEGIN through execute lost its connection"
        await db.execute("COMMIT")

        await db.execute("SELECT 1")
        async def background():
            await bot.send_message(CHAT, "фон")             # copied context: sees the handler's handle
        await asyncio.create_task(background())
        assert db.holds_connection, "a background task released the handler's connection"
    assert pool.get_idle_size() == pool.get_size(), "a lazy handle leaked its connection"

    held = [await pool.acquire() for _ in range(pool.get_max_size())]
    try:
        started = time.perf_counter()
        try:
            await miniapp_request()
        except PoolBusy:
            pass
        else:
            raise AssertionError("a full pool did not answer PoolBusy")
        assert 0.9 < time.perf_counter() - started < 2.0
        from FastAPI.main import _pool_busy
        app = FastAPI()
        app.add_exception_handler(PoolBusy, _pool_busy)

        @app.get("/read")
        async def read(db=Depends(get_db)):
            async with db.execute("SELECT 1") as cursor:
                return {"value": (await cursor.fetchone())[0]}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            busy = await client.get("/read")
        assert busy.status_code == 503 and busy.headers.get("retry-after") == "2" and "занят" in busy.json()["detail"], busy.text
    finally:
        for conn in held:
            await pool.release(conn)
    print("  transaction and BEGIN keep their connection, background tasks do not release it, full pool → PoolBusy in 1 s (HTTP 503)")


async def long_lived_connections_outside_the_pool() -> None:
    pool = get_pool()
    holder = await connect_direct()
    waiter = await connect_direct(statement_timeout_ms=0)     # what bot/__main__.py uses for the lock
    try:
        await holder.execute("SELECT pg_advisory_lock(990003)")
        wait = asyncio.create_task(waiter.execute("SELECT pg_advisory_lock(990003)"))
        await asyncio.sleep(1.6)                               # longer than DB_STATEMENT_TIMEOUT_MS
        assert not wait.done(), "the lock wait was cancelled by statement_timeout"
        await holder.execute("SELECT pg_advisory_unlock(990003)")
        await asyncio.wait_for(wait, 2)
    finally:
        await holder.close()
        await waiter.close()

    assert await notifications.ensure_balance_listener()
    held = [await pool.acquire() for _ in range(pool.get_max_size())]   # the whole pool is free for work
    try:
        pid = await held[0].fetchval(
            "SELECT pid FROM pg_stat_activity WHERE application_name = 'predvestnik' AND query LIKE 'LISTEN%'")
        assert pid and pid not in {c.get_server_pid() for c in held}, "LISTEN sits in the pool"
        notifications.LISTENER_RETRY_SEC = (0.1,)
        assert await held[0].fetchval("SELECT pg_terminate_backend($1)", pid)
        for _ in range(50):
            await asyncio.sleep(0.1)
            if notifications._balance_listener_ready.is_set():
                new_pid = await held[0].fetchval(
                    "SELECT pid FROM pg_stat_activity WHERE application_name = 'predvestnik' AND query LIKE 'LISTEN%'")
                if new_pid and new_pid != pid:
                    break
        else:
            raise AssertionError("LISTEN did not reconnect after its connection was killed")
        queue = asyncio.Queue()
        notifications.register(990_003_001, queue)
        try:
            await held[0].execute("SELECT pg_notify($1, $2)", balance_events.CHANNEL,
                                  '{"user_id": 990003001, "type": "balance_changed"}')
            event = await asyncio.wait_for(queue.get(), 3)
        finally:
            notifications.unregister(990_003_001, queue)
        assert event["type"] == "balance_changed", event
    finally:
        for conn in held:
            await pool.release(conn)
    print("  lock waits past statement_timeout; LISTEN outside the pool, back after its connection was killed")


async def read_calls_skip_the_send_slot() -> None:
    bot, session = production_bot(0.0)
    started = time.monotonic()
    await asyncio.gather(*(bot.get_chat_member(CHAT, 100 + n) for n in range(10)),
                         bot.delete_message(CHAT, 5), bot.ban_chat_member(CHAT, 200))
    spread = max(t for _, t in session.started) - started
    assert spread < 0.3, f"getChatMember/deleteMessage/banChatMember waited for the send slot: {spread:.2f} s"
    session.started.clear()
    await asyncio.gather(*(bot.send_message(CHAT, f"m{n}") for n in range(3)))
    times = sorted(t for _, t in session.started)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert min(gaps) >= 1.0, f"sendMessage broke 1 message per second per chat: gaps {gaps}"
    print(f"  12 read/moderation calls started within {spread * 1000:.0f} ms; sendMessage gaps {[round(g, 2) for g in gaps]} s")


async def main() -> None:
    await create_pool()
    try:
        await stuck_telegram_does_not_starve_miniapp()
        await fastapi_endpoints_release_before_telegram()
        await lazy_handle_semantics()
        await long_lived_connections_outside_the_pool()
        await read_calls_skip_the_send_slot()
    finally:
        if notifications._balance_listener_task:
            notifications._balance_listener_task.cancel()
        await get_pool().close()
    print("OK: slow Telegram holds no database connection and no send slot for read calls")


if __name__ == "__main__":
    asyncio.run(main())
