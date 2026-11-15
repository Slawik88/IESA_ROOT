"""Disposable PostgreSQL proof for idle expiry and persistent Telegram reply retention."""
import argparse
import asyncio
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import asyncpg

os.environ.setdefault("BOT_TOKEN", "123456:local-test")
os.environ.setdefault("DATABASE_URL", "postgresql://local/test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import DeleteMessage
from bot.chat import word_chain as ui
from core import word_chain as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import word_chain as repo
from services import word_chain as game


async def run(dsn):
    connections = [await asyncpg.connect(dsn) for _ in range(2)]
    for connection in connections:
        await connection.execute("SET search_path TO predvestnik,public")
    connection, other_connection = connections
    db, other = [PGAdapter(c) for c in connections]
    cid, uid = -98651200, 98651201
    bot = SimpleNamespace(delete_message=AsyncMock(return_value=True))

    async def remember(mid, topic=0, adapter=db):
        sent = SimpleNamespace(chat=SimpleNamespace(id=cid), message_id=mid,
                               message_thread_id=topic, is_topic_message=bool(topic))
        await ui.remember_reply(adapter, bot, sent)

    async def kept(topic=0):
        return list(await connection.fetch("SELECT message_id FROM word_chain_messages WHERE chat_id=$1 AND topic_id=$2 ORDER BY message_id", cid, topic))

    try:
        await repo.ensure_tables(db)
        first = await game.start(db, chat_id=cid, topic_id=0, actor=uid)
        rid = first["round_id"]
        await db.execute("UPDATE word_chain_rounds SET updated_at=CLOCK_TIMESTAMP()-INTERVAL '14 minutes 59 seconds' WHERE id=?", (rid,))
        await game.expire_idle(db)
        assert (await game.status(db, chat_id=cid, topic_id=0))["active"]
        await db.execute("UPDATE word_chain_rounds SET updated_at=CLOCK_TIMESTAMP()-INTERVAL '15 minutes 1 second' WHERE id=?", (rid,))
        await game.expire_idle(db)
        assert await connection.fetchval("SELECT status FROM word_chain_rounds WHERE id=$1", rid) == "expired"
        assert not (await game.status(db, chat_id=cid, topic_id=0))["active"]
        assert (await game.start(db, chat_id=cid, topic_id=0, actor=uid))["round_id"] != rid

        # A sweep's stale candidate must not expire a newly refreshed scope.
        await db.execute("UPDATE word_chain_rounds SET updated_at=CLOCK_TIMESTAMP()-INTERVAL '16 minutes' WHERE chat_id=? AND status='active'", (cid,))
        stale = await repo.idle_scopes(db)
        assert (cid, 0) in stale
        await db.execute("UPDATE word_chain_rounds SET updated_at=CLOCK_TIMESTAMP() WHERE chat_id=? AND status='active'", (cid,))
        with patch.object(repo, "idle_scopes", AsyncMock(return_value=stale)):
            await game.expire_idle(other)
        assert (await game.status(db, chat_id=cid, topic_id=0))["active"]
        assert await game.solo_turn_open(db, chat_id=cid, topic_id=0)
        await db.execute("UPDATE word_chain_rounds SET updated_at=CLOCK_TIMESTAMP()-INTERVAL '12 minutes' WHERE chat_id=? AND status='active'", (cid,))
        assert await game.solo_turn_open(db, chat_id=cid, topic_id=0), "plain DM words work until expiry"

        for mid in range(1, 8):
            await remember(mid)
        assert not bot.delete_message.called
        await remember(8)
        bot.delete_message.assert_awaited_once_with(chat_id=cid, message_id=1)
        assert [r[0] for r in await kept()] == list(range(2, 9))
        # Topic isolation and a second adapter model restart/out-of-order completion.
        await remember(1, topic=7)
        await remember(10, adapter=other)
        await remember(9)
        assert [r[0] for r in await kept()] == list(range(4, 11))
        assert [r[0] for r in await kept(7)] == [1]
        await remember(10)
        assert len(await kept()) == rules.BOT_MESSAGES_KEPT
        # Stopping/restarting a round never resets the message budget.
        await game.stop(db, chat_id=cid, topic_id=0, actor=uid, can_moderate=False)
        await game.start(db, chat_id=cid, topic_id=0, actor=uid)
        await remember(11)
        assert [r[0] for r in await kept()] == list(range(5, 12))

        method = DeleteMessage(chat_id=cid, message_id=5)
        bot.delete_message.side_effect = TelegramNetworkError(method, "connection lost")
        await remember(12)
        assert [r[0] for r in await kept()] == list(range(5, 13)), "failed deletion remains durable"
        bot.delete_message.side_effect = None
        await ui.clean_messages(other, bot)
        assert [r[0] for r in await kept()] == list(range(6, 13))
        bot.delete_message.side_effect = TelegramBadRequest(method, "Bad Request: message to delete not found")
        await remember(13)
        assert [r[0] for r in await kept()] == list(range(7, 14))
        bot.delete_message.side_effect = None
        assert all(call.kwargs["chat_id"] == cid for call in bot.delete_message.await_args_list)
        print("PASS: 15-minute idle expiry, stale sweep/fresh turn, DM 12-minute word, eighth reply deletes first, topics, restart, out-of-order sends, round restart, network retry and already-deleted reply")
    finally:
        await db.execute("DELETE FROM word_chain_messages WHERE chat_id=?", (cid,))
        for table in ("word_chain_moves", "word_chain_words"):
            await db.execute(f"DELETE FROM {table} WHERE round_id IN (SELECT id FROM word_chain_rounds WHERE chat_id=?)", (cid,))
        await db.execute("DELETE FROM word_chain_rounds WHERE chat_id=?", (cid,))
        for connection in connections:
            await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    target = urlparse(args.dsn)
    if target.hostname not in {"localhost", "127.0.0.1", "::1"} or "preprod" not in target.path:
        raise SystemExit("an isolated loopback preprod database is required")
    asyncio.run(run(args.dsn))
