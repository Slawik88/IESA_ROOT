#!/usr/bin/env python3
"""Real PostgreSQL proof (roadmap S03): «бан во всех чатах» is a background job, not one long HTTP request.

1. The decision (global blacklist row, journal) is written at once; bans run BAN_PARALLEL chats at a time,
   so 12 slow chats take ~3 rounds, not 12; progress «N из M» is readable while it runs.
2. The admin answer waits at most GLOBAL_JOB_WAIT_SEC: a slow job keeps going after the answer and finishes.
3. Unban lifts the ban only where the global ban put it; chats where Telegram refused are counted as failed.
4. An unban while the ban job still runs stops it first: no chat gets banned after the unban.
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
os.environ.setdefault("BOT_TOKEN", "1:global-ban-test")

from FastAPI.routers.bot_admin import people
from infrastructure import lazy_db
from infrastructure.database import create_pool, get_pool
from services import broadcasts, global_moderation

PLAYER = 990_004_001
ACTOR = 990_004_002
CHATS = [-1_009_400_000_000 - n for n in range(12)]
REFUSING = CHATS[-1]


class SlowBot:
    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.banned: list[int] = []
        self.unbanned: list[int] = []
        self.in_flight = self.peak = 0

    async def _call(self, chat_id: int, log: list[int]) -> bool:
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            if chat_id == REFUSING:
                raise RuntimeError("bot was kicked from the chat")
            log.append(chat_id)
            return True
        finally:
            self.in_flight -= 1

    async def ban_chat_member(self, chat_id, user_id):
        return await self._call(chat_id, self.banned)

    async def unban_chat_member(self, chat_id, user_id, only_if_banned=False):
        return await self._call(chat_id, self.unbanned)


async def main() -> None:
    pool = await create_pool()
    async with pool.acquire() as conn:
        for cid in CHATS:
            await conn.execute("INSERT INTO chat_settings (chat_id) VALUES ($1) ON CONFLICT DO NOTHING", cid)
        await conn.execute("DELETE FROM chat_blacklist WHERE user_id = $1", PLAYER)
        await conn.execute("DELETE FROM moderation_logs WHERE user_id = $1", PLAYER)
        total = await conn.fetchval("SELECT count(*) FROM chat_settings WHERE chat_id < 0")
    try:
        bot = SlowBot(0.3)
        people.GLOBAL_JOB_WAIT_SEC = 0.2
        started = time.perf_counter()
        async with lazy_db.lazy_connection(pool, source="http") as db:
            job = await global_moderation.global_ban(bot, db, broadcasts.pool_db_factory(), PLAYER, ACTOR, "спам")
            answer = await people._global_job_answer(job, "Забанен в чатах")
        assert time.perf_counter() - started < 1.0, "the admin answer waited for the whole job"
        assert "доделаются в фоне" in answer["message"] and not answer["job"]["finished"], answer
        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM chat_blacklist WHERE chat_id = 0 AND user_id = $1", PLAYER) == 1
            assert await conn.fetchval("SELECT count(*) FROM moderation_logs WHERE user_id = $1 AND action = 'global_ban'", PLAYER) == 1
        progress = global_moderation.job_view("global_ban", PLAYER)
        assert progress["total"] == total and progress["done"] + progress["failed"] < total, progress

        assert await global_moderation.wait(job, 30)
        elapsed = time.perf_counter() - started
        assert bot.peak == global_moderation.BAN_PARALLEL, bot.peak
        assert elapsed < total * bot.delay / global_moderation.BAN_PARALLEL + 1.5, f"bans were not parallel: {elapsed:.1f} s"
        view = global_moderation.job_view("global_ban", PLAYER)
        assert view["finished"] and view["done"] == total - 1 and view["failed"] == 1, view
        async with pool.acquire() as conn:
            logged = {r[0] for r in await conn.fetch(
                "SELECT chat_id FROM moderation_logs WHERE user_id = $1 AND action = 'global_ban_chat'", PLAYER)}
        assert logged == set(bot.banned) and REFUSING not in logged

        people.GLOBAL_JOB_WAIT_SEC = 10
        bot.delay = 0.01
        keep = CHATS[0]
        async with pool.acquire() as conn:   # a separate ban in one chat survives the global unban
            await conn.execute("INSERT INTO chat_blacklist (chat_id, user_id, reason) VALUES ($1, $2, 'отдельно')", keep, PLAYER)
        async with lazy_db.lazy_connection(pool, source="http") as db:
            job = await global_moderation.global_unban(bot, db, PLAYER, ACTOR)
            answer = await people._global_job_answer(job, "Бан снят в чатах")
        assert answer["job"]["finished"] and answer["message"] == f"Бан снят в чатах: {len(logged) - 1}.", answer
        assert set(bot.unbanned) == logged - {keep}, (bot.unbanned, keep)
        bot.delay = 0.3
        bot.banned.clear(); bot.unbanned.clear()
        async with lazy_db.lazy_connection(pool, source="http") as db:
            job = await global_moderation.global_ban(bot, db, broadcasts.pool_db_factory(), PLAYER, ACTOR, "ошибка")
        await asyncio.sleep(0.5)                       # a few chats banned, most still waiting
        async with lazy_db.lazy_connection(pool, source="http") as db:
            undo = await global_moderation.global_unban(bot, db, PLAYER, ACTOR)
        banned_before_unban = list(bot.banned)
        assert await global_moderation.wait(undo, 30)
        await asyncio.sleep(0.5)
        assert bot.banned == banned_before_unban, "the ban job kept banning after the unban"
        assert 0 < len(banned_before_unban) < total and set(bot.unbanned) >= set(banned_before_unban)

        closed = lazy_db.LazyPGAdapter(pool, source="http")
        await closed.close()
        try:
            await closed.execute("SELECT 1")
        except RuntimeError:
            pass
        else:
            raise AssertionError("a closed handle silently took a new connection")
        print(f"  {total} chats banned {global_moderation.BAN_PARALLEL} at a time in {elapsed:.1f} s; "
              "answer in < 1 s, progress «N из M», unban only where the global ban put it and stops a running ban")
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM chat_blacklist WHERE user_id = $1", PLAYER)
            await conn.execute("DELETE FROM moderation_logs WHERE user_id = $1", PLAYER)
            await conn.execute("DELETE FROM chat_settings WHERE chat_id = ANY($1::bigint[])", CHATS)
        await get_pool().close()
    print("OK: global ban runs as a background job with progress")


if __name__ == "__main__":
    asyncio.run(main())
