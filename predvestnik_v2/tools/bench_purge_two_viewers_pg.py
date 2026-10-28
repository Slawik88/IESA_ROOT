#!/usr/bin/env python3
"""Load check (roadmap S05): two admins watch one running «Чистка» while its dossiers go out.

Telegram is a fake session behind the production outbound middlewares: every call takes --tg-delay seconds.
A chat with --members silent members is purged through the web start (the request shape every screen sends),
then two clients read the purge view every 2 s (the pre-S05 screen's poll) for --seconds while the dossier queue
runs. Prints start time, per-read latency (p50/p95/max) and Telegram getChatMember calls per read.
Uses only endpoints the pre-S05 code also has, so the same script measures a base checkout and the branch.
Only a loopback DSN is accepted.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from collections import Counter
from datetime import timedelta
from pathlib import Path
import statistics
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True)
parser.add_argument("--members", type=int, default=300)
parser.add_argument("--tg-delay", type=float, default=0.5)
parser.add_argument("--seconds", type=float, default=20.0)
args = parser.parse_args()
if urlparse(args.dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("only a loopback PostgreSQL DSN is allowed")
os.environ["DATABASE_URL"] = args.dsn
os.environ.pop("PREDVESTNIK_DATABASE_URL", None)
os.environ.setdefault("BOT_TOKEN", "1:purge-bench")

import httpx
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import ChatMemberAdministrator, ChatMemberMember, ChatMemberOwner, User
from fastapi import FastAPI

from bot.chat.tracking import local_now
from bot.dispatcher import attach_outbound
from FastAPI.deps import get_db, require_tg_user
from FastAPI.routers import purge_v1
from FastAPI.routers.bot_admin.people import set_bot
from infrastructure.database import create_pool

BOT_ID, OWNER, SECOND = 999, 1001, 1002
CHAT = -1_005_500_000_100


class SlowTelegram(BaseSession):
    def __init__(self, delay: float) -> None:
        super().__init__()
        self.delay = delay
        self.calls: Counter[str] = Counter()

    async def close(self) -> None:
        return None

    async def stream_content(self, *a, **k):  # pragma: no cover
        yield b""

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        self.calls[name] += 1
        await asyncio.sleep(self.delay)
        if name == "GetMe":
            return User(id=BOT_ID, is_bot=True, first_name="bot", username="predvestnik_bot")
        if name in ("GetChatAdministrators", "GetChatMember"):
            uid = int(getattr(method, "user_id", OWNER))
            if name == "GetChatAdministrators" or uid == OWNER:
                owner = ChatMemberOwner(user=User(id=OWNER, is_bot=False, first_name="o"), is_anonymous=False)
                if name == "GetChatMember":
                    return owner
            admin = ChatMemberAdministrator(
                user=User(id=BOT_ID, is_bot=True, first_name="bot"), can_be_edited=False, is_anonymous=False,
                can_manage_chat=True, can_delete_messages=True, can_manage_video_chats=False, can_restrict_members=True,
                can_promote_members=False, can_change_info=False, can_invite_users=True, can_post_stories=False,
                can_edit_stories=False, can_delete_stories=False)
            if name == "GetChatAdministrators":
                return [owner, admin]
            return admin if uid == BOT_ID else ChatMemberMember(user=User(id=uid, is_bot=False, first_name="p"))
        if name == "SendMessage":
            return method.__returning__.model_validate(
                {"message_id": 1, "date": int(time.time()), "chat": {"id": method.chat_id, "type": "supergroup"},
                 "text": method.text}, context={"bot": bot})
        return True


async def seed(db) -> None:
    await db.execute("DELETE FROM purge_targets WHERE session_id IN (SELECT id FROM purge_sessions WHERE chat_id = ?)", (CHAT,))
    await db.execute("DELETE FROM purge_sessions WHERE chat_id = ?", (CHAT,))
    await db.execute("DELETE FROM user_chat_stats WHERE chat_tg_id = ?", (CHAT,))
    await db.execute("INSERT INTO chat_settings (chat_id, chat_title, is_purging) VALUES (?, 'Нагрузка', FALSE) "
                     "ON CONFLICT (chat_id) DO UPDATE SET is_purging = FALSE", (CHAT,))
    ids = [OWNER, SECOND, *range(5_000_000, 5_000_000 + args.members)]
    await db.execute("INSERT INTO users (user_tg_id, user_tg_username) SELECT u, 'b' || u FROM unnest(?::bigint[]) u "
                     "ON CONFLICT DO NOTHING", (ids,))
    await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, membership_since, joined_at, is_left) "
                     "SELECT u, ?, NOW() - INTERVAL '40 days', NOW() - INTERVAL '40 days', FALSE FROM unnest(?::bigint[]) u",
                     (CHAT, ids))
    await db.execute("UPDATE user_chat_stats SET chat_rank = 9 WHERE chat_tg_id = ? AND user_tg_id = ?", (CHAT, SECOND))


async def main() -> None:
    await create_pool()
    telegram = SlowTelegram(args.tg_delay)
    bot = Bot(token="1:purge-bench", session=telegram)
    attach_outbound(telegram)
    set_bot(bot)
    app = FastAPI()
    app.include_router(purge_v1.router)
    agen = get_db()
    db = await agen.__anext__()
    clients = []
    try:
        await seed(db)
        for uid in (OWNER, SECOND):
            sub = FastAPI()
            sub.include_router(purge_v1.router)
            sub.dependency_overrides[require_tg_user] = (lambda u: (lambda: {"id": u}))(uid)
            clients.append(httpx.AsyncClient(transport=httpx.ASGITransport(app=sub), base_url="http://b", timeout=60))
        today = local_now().date()
        body = {"norm": 10, "date_from": (today - timedelta(days=7)).isoformat(),
                "date_to": (today - timedelta(days=1)).isoformat(), "action_id": f"bench-{time.time()}"}
        began = time.perf_counter()
        started = await clients[0].post(f"/purge-v1/chats/{CHAT}/start", json=body)
        start_ms = (time.perf_counter() - began) * 1000
        assert started.status_code == 200, started.text
        latencies: list[float] = []
        reads = 0
        telegram.calls.clear()

        async def watch(client) -> None:
            nonlocal reads
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline:
                t = time.perf_counter()
                response = await client.get(f"/purge-v1/chats/{CHAT}?mode=pending")
                latencies.append(time.perf_counter() - t)
                reads += 1
                assert response.status_code == 200, response.text
                await asyncio.sleep(2.0)

        await asyncio.gather(*(watch(c) for c in clients))
        latencies.sort()
        p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
        print(f"members={args.members} tg_delay={args.tg_delay}s start={start_ms:.0f}ms reads={reads} "
              f"p50={statistics.median(latencies) * 1000:.0f}ms p95={p95 * 1000:.0f}ms max={latencies[-1] * 1000:.0f}ms "
              f"getChatMember_per_read={telegram.calls['GetChatMember'] / max(reads, 1):.2f} "
              f"dossiers_sent={telegram.calls['SendMessage']}")
        view = (await clients[0].get(f"/purge-v1/chats/{CHAT}")).json()
        await clients[0].post(f"/purge-v1/chats/{CHAT}/finish", json={"session_id": view["session"]["id"]})
        await asyncio.sleep(0.5)
    finally:
        for client in clients:
            await client.aclose()
        await db.execute("DELETE FROM purge_targets WHERE session_id IN (SELECT id FROM purge_sessions WHERE chat_id = ?)", (CHAT,))
        await db.execute("DELETE FROM purge_sessions WHERE chat_id = ?", (CHAT,))
        await db.execute("DELETE FROM moderation_logs WHERE chat_id = ?", (CHAT,))
        await db.execute("DELETE FROM user_chat_stats WHERE chat_tg_id = ?", (CHAT,))
        await db.execute("DELETE FROM chat_settings WHERE chat_id = ?", (CHAT,))
        await agen.aclose()


if __name__ == "__main__":
    asyncio.run(main())
