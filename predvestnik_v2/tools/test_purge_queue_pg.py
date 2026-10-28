#!/usr/bin/env python3
"""Real PostgreSQL proof (roadmap S05): «Чистка» runs as a background queue and does not slow anything down.

Telegram is a fake session behind the production outbound middlewares (bot/dispatcher.attach_outbound); every call
takes TG_DELAY seconds and is counted. The Mini App side is the real router with the real lazy get_db on a small pool.

1. Web start with ``background=1`` answers 202 at once; the list is prepared in the background, the view shows it.
2. The dossier queue lives in the database: a process killed mid-queue loses nothing, resume_dossiers finishes it.
3. Polling the purge view makes no getChatMember after the first read (45 s cache); an unchanged view answers 304.
4. Live viewers (``live=1``) get data_changed{scope:'purge'} over the WebSocket queue; old screens get no events.
5. A ban decision checks actor, bot and target in Telegram afresh, and no connection is held during the slow ban:
   Mini App requests and purge polls answer at once with a 2-connection pool.
6. Messages in the closed chat are deleted with deleteMessages: one call per 0.4 s window, at most 100 ids each.
7. The pre-S05 screen contract still works: start without ``background`` answers 200 with the session.
Only a loopback DSN is accepted.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from collections import Counter
from datetime import timedelta
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True)
args = parser.parse_args()
if urlparse(args.dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("only a loopback PostgreSQL DSN is allowed")
os.environ["DATABASE_URL"] = args.dsn
os.environ.pop("PREDVESTNIK_DATABASE_URL", None)
os.environ["DB_POOL_MAX_SIZE"] = "4"   # process total: 2 pooled + 2 direct
os.environ["DB_ACQUIRE_TIMEOUT_SEC"] = "2"
os.environ.setdefault("BOT_TOKEN", "1:purge-queue-test")

import httpx
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import ChatMemberAdministrator, ChatMemberMember, ChatMemberOwner, User
from fastapi import FastAPI

from bot.chat import purge as bridge
from bot.chat.tracking import local_now
from bot.dispatcher import attach_outbound
from FastAPI import notifications, purge_live
from FastAPI.deps import get_db, require_tg_user
from FastAPI.routers import purge_v1
from FastAPI.routers.bot_admin.people import set_bot
from infrastructure.database import create_pool

TG_DELAY = 0.3
BOT_ID, OWNER, OTHER = 999, 1001, 1002
CHAT, CHAT_OLD = -1_005_500_000_001, -1_005_500_000_002
MEMBERS = list(range(3001, 3007))


class FakeTelegram(BaseSession):
    """Answers like Telegram after ``delay`` seconds and counts every method."""

    def __init__(self) -> None:
        super().__init__()
        self.delay = TG_DELAY
        self.calls: Counter[str] = Counter()
        self.sent: list[tuple[int, str]] = []
        self.deleted: list[list[int]] = []
        self.slow: dict[str, float] = {}

    async def close(self) -> None:
        return None

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    def member(self, user_id: int):
        if user_id == BOT_ID:
            return ChatMemberAdministrator(
                user=User(id=BOT_ID, is_bot=True, first_name="bot"), can_be_edited=False, is_anonymous=False,
                can_manage_chat=True, can_delete_messages=True, can_manage_video_chats=False, can_restrict_members=True,
                can_promote_members=False, can_change_info=False, can_invite_users=True, can_post_stories=False,
                can_edit_stories=False, can_delete_stories=False)
        if user_id == OWNER:
            return ChatMemberOwner(user=User(id=OWNER, is_bot=False, first_name="owner"), is_anonymous=False)
        return ChatMemberMember(user=User(id=user_id, is_bot=False, first_name=f"p{user_id}"))

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        self.calls[name] += 1
        await asyncio.sleep(self.slow.get(name, self.delay))
        if name == "GetMe":
            return User(id=BOT_ID, is_bot=True, first_name="bot", username="predvestnik_bot")
        if name == "GetChatAdministrators":
            return [self.member(OWNER), self.member(BOT_ID)]
        if name == "GetChatMember":
            return self.member(int(method.user_id))
        if name == "SendMessage":
            self.sent.append((int(method.chat_id), method.text))
            return method.__returning__.model_validate(
                {"message_id": len(self.sent), "date": int(time.time()), "chat": {"id": method.chat_id, "type": "supergroup"},
                 "text": method.text}, context={"bot": bot})
        if name == "DeleteMessages":
            self.deleted.append(list(method.message_ids))
        return True


async def seed(db, chat_id: int) -> None:
    await db.execute("DELETE FROM purge_targets WHERE session_id IN (SELECT id FROM purge_sessions WHERE chat_id = ?)", (chat_id,))
    await db.execute("DELETE FROM purge_sessions WHERE chat_id = ?", (chat_id,))
    await db.execute("INSERT INTO chat_settings (chat_id, chat_title, is_purging) VALUES (?, 'Очередь', FALSE) "
                     "ON CONFLICT (chat_id) DO UPDATE SET chat_title = EXCLUDED.chat_title, is_purging = FALSE", (chat_id,))
    for uid in [OWNER, OTHER, *MEMBERS]:
        await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) ON CONFLICT DO NOTHING", (uid, f"q{uid}"))
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, membership_since, joined_at, is_left) "
                         "VALUES (?, ?, NOW() - INTERVAL '40 days', NOW() - INTERVAL '40 days', FALSE) "
                         "ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE SET is_left = FALSE, is_bot = FALSE", (uid, chat_id))
    await db.execute("UPDATE user_chat_stats SET chat_rank = 9 WHERE chat_tg_id = ? AND user_tg_id = ?", (chat_id, OTHER))


def plan_body(action_id: str) -> dict:
    today = local_now().date()
    return {"norm": 10, "date_from": (today - timedelta(days=7)).isoformat(),
            "date_to": (today - timedelta(days=1)).isoformat(), "action_id": action_id}


async def until(check, timeout: float, what: str):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = await check()
        if value:
            return value
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out: {what}")


async def dossiers_sent(db, sid: int) -> int:
    async with db.execute("SELECT COUNT(*) FROM purge_targets WHERE session_id = ? AND dossier_sent", (sid,)) as cursor:
        return int((await cursor.fetchone())[0])


async def main() -> None:
    await create_pool()
    telegram = FakeTelegram()
    bot = Bot(token="1:purge-queue-test", session=telegram)
    attach_outbound(telegram)
    set_bot(bot)
    app = FastAPI()
    app.include_router(purge_v1.router)
    user = {"id": OWNER}
    app.dependency_overrides[require_tg_user] = lambda: user
    agen = get_db()
    db = await agen.__anext__()
    try:
        for chat in (CHAT, CHAT_OLD):
            await seed(db, chat)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as client:
            # 1. Background start: 202 at once, the list appears in the view.
            telegram.slow["SendMessage"] = 0.4
            started = time.perf_counter()
            response = await client.post(f"/purge-v1/chats/{CHAT}/start?background=1", json=plan_body("bg-1"))
            start_ms = (time.perf_counter() - started) * 1000
            assert response.status_code == 202 and response.json()["job"]["state"] == "preparing", response.text
            first = await client.get(f"/purge-v1/chats/{CHAT}?live=1")
            assert first.status_code == 200
            assert first.json()["active"] or first.json()["preparing"]["state"] in {"preparing", "started"}, first.text

            async def active_view():
                view = (await client.get(f"/purge-v1/chats/{CHAT}?live=1")).json()
                return view if view["active"] else None
            view = await until(active_view, 10, "background start finished")
            sid, total = int(view["session"]["id"]), int(view["counts"]["total"])
            assert total == len(MEMBERS), view["counts"]
            print(f"  background start answered in {start_ms:.0f} ms (Telegram {TG_DELAY * 1000:.0f} ms per call)")

            # 2. Kill the queue mid-way (deploy), then resume from the database alone.
            await until(lambda: dossiers_sent(db, sid), 10, "first dossier")
            bridge._dossier_tasks[sid].cancel()
            await asyncio.sleep(0.05)
            assert not bridge.dossier_queue_running(sid)
            before = await dossiers_sent(db, sid)
            assert 0 < before < total, before
            assert await bridge.resume_dossiers(bot) == 1
            await until(lambda: _equals(dossiers_sent(db, sid), total), 15, "all dossiers after restart")
            receivers = Counter(int(text.split("tg://user?id=")[1].split('"')[0]) for _, text in telegram.sent if "Досье" in text)
            assert set(receivers) == set(MEMBERS) and max(receivers.values()) <= 2, receivers
            print(f"  queue killed after {before}/{total} dossiers, resumed: {total}/{total} sent, none lost")

            # 3. Polling makes no Telegram calls; an unchanged view is 304.
            telegram.calls.clear()
            etag = None
            for _ in range(5):
                answer = await client.get(f"/purge-v1/chats/{CHAT}?live=1")
                assert answer.status_code == 200
                etag = answer.headers["etag"]
            assert telegram.calls["GetChatMember"] == 0, telegram.calls
            unchanged = await client.get(f"/purge-v1/chats/{CHAT}?live=1", headers={"If-None-Match": etag})
            assert unchanged.status_code == 304 and not unchanged.content, unchanged.status_code
            print("  5 polls of the purge view: 0 getChatMember, unchanged view answers 304")

            # 4. Live push to viewers only.
            watcher, old_screen = asyncio.Queue(), asyncio.Queue()
            notifications.register(OWNER, watcher)
            notifications.register(OTHER, old_screen)   # has a WebSocket, never asked for live=1
            bridge.live_changed(CHAT)
            event = await asyncio.wait_for(watcher.get(), 3)
            assert event == {"type": "data_changed", "scope": "purge", "chat_id": CHAT, "revision": event["revision"]}, event
            for _ in range(5):   # a burst is merged into one push per PUSH_EVERY_SEC
                bridge.live_changed(CHAT)
            await asyncio.sleep(purge_live.PUSH_EVERY_SEC + 0.3)
            assert watcher.qsize() == 1 and old_screen.empty(), (watcher.qsize(), old_screen.qsize())
            print("  live viewer got data_changed{scope:'purge'}, a burst of 5 merged into 1, old screen got nothing")

            # 5. A slow ban: fresh rights, no connection held, everything else answers at once.
            telegram.calls.clear()
            telegram.slow["BanChatMember"] = 2.0
            decision = asyncio.create_task(client.post(f"/purge-v1/chats/{CHAT}/decision", json={
                "session_id": sid, "user_id": MEMBERS[0], "action": "ban", "action_id": "ban-slow"}))
            await until(lambda: _true(telegram.calls["BanChatMember"]), 5, "ban reached Telegram")
            waits = []
            for _ in range(5):
                began = time.perf_counter()
                inner = get_db()
                probe = await inner.__anext__()
                async with probe.execute("SELECT 1") as cursor:
                    await cursor.fetchone()
                await inner.aclose()
                assert (await client.get(f"/purge-v1/chats/{CHAT}?live=1")).status_code == 200
                waits.append(time.perf_counter() - began)
            result = await decision
            assert result.status_code == 200 and result.json()["verdict"] == "ban", result.text
            assert telegram.calls["GetChatMember"] == 3, telegram.calls   # actor, bot and target: no cache before a ban
            assert max(waits) < 0.5, f"a request waited for a connection held over Telegram: {waits}"
            print(f"  2 s ban in Telegram: Mini App + purge poll answer in ≤ {max(waits) * 1000:.0f} ms (2-connection pool)")

            # 6. Deletions in the closed chat go in batches of at most 100.
            telegram.deleted.clear()
            for n in range(150):
                message = SimpleNamespace(chat=SimpleNamespace(id=CHAT, type="supergroup"), message_id=10_000 + n,
                                          from_user=SimpleNamespace(id=MEMBERS[1], is_bot=False))
                assert await bridge.purge_gate(db, bot, message)
            await until(lambda: _equals_value(sum(map(len, telegram.deleted)), 150), 5, "deletions flushed")
            assert len(telegram.deleted) <= 15 and max(map(len, telegram.deleted)) <= 100, list(map(len, telegram.deleted))
            print(f"  150 messages in the closed chat: {len(telegram.deleted)} deleteMessages calls")

            # 7. The screen shipped before S05: start without background, plain JSON view.
            old = await client.post(f"/purge-v1/chats/{CHAT_OLD}/start", json=plan_body("old-1"))
            assert old.status_code == 200 and old.json()["ok"] and old.json()["active"], old.text
            plain = (await client.get(f"/purge-v1/chats/{CHAT_OLD}")).json()
            assert plain["active"] and "preparing" not in plain and plain["counts"]["total"] == len(MEMBERS), plain
            finish = await client.post(f"/purge-v1/chats/{CHAT_OLD}/finish", json={"session_id": plain["session"]["id"]})
            assert finish.status_code == 200, finish.text
            await client.post(f"/purge-v1/chats/{CHAT}/finish", json={"session_id": sid})
            print("  pre-S05 screen contract: start 200 with session, plain view, finish")
        print("PASS: background start, durable dossier queue, cached polls + 304, live push, no connection over Telegram, "
              "batched deletes, old screen contract")
    finally:
        purge_live.reset()
        for chat in (CHAT, CHAT_OLD):
            await db.execute("DELETE FROM purge_targets WHERE session_id IN (SELECT id FROM purge_sessions WHERE chat_id = ?)", (chat,))
            await db.execute("DELETE FROM purge_sessions WHERE chat_id = ?", (chat,))
            await db.execute("DELETE FROM moderation_logs WHERE chat_id = ?", (chat,))
            await db.execute("DELETE FROM chat_blacklist WHERE chat_id = ?", (chat,))
            await db.execute("DELETE FROM user_chat_stats WHERE chat_tg_id = ?", (chat,))
            await db.execute("DELETE FROM chat_settings WHERE chat_id = ?", (chat,))
        await agen.aclose()


async def _equals(awaitable, expected):
    return (await awaitable) == expected


async def _equals_value(value, expected):
    return value == expected


async def _true(value):
    return bool(value)


if __name__ == "__main__":
    asyncio.run(main())
