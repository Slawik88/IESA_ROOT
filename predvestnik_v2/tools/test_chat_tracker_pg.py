#!/usr/bin/env python3
"""PostgreSQL proof for private, searchable and stable chat tracking."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import asyncpg
from fastapi import HTTPException

from bot.core.database import _init_users_and_chats
from FastAPI.routers.profile import my_chat_tracker
from infrastructure.pg_adapter import PGAdapter


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    transaction = connection.transaction()
    await transaction.start()
    try:
        await _init_users_and_chats(db)
        user_id, foreign_id = 978201, 978202
        chats = [(-978211, "Лунный штаб"), (-978212, "Альфа"), (-978213, "Бета"), (-978214, "Старый чат")]
        for chat_id, title in chats:
            await db.execute("INSERT INTO chat_settings(chat_id,chat_title) VALUES (?,?) ON CONFLICT (chat_id) DO UPDATE SET chat_title=EXCLUDED.chat_title", (chat_id, title))
        common = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.execute(
            "INSERT INTO user_chat_stats(user_tg_id,chat_tg_id,user_level,local_rank,user_messages_count_per_day,"
            "user_messages_count_per_week,user_messages_count_all_time,last_message_at,warnings,is_left) VALUES "
            "(?,?,5,2,4,18,120,?,1,FALSE),(?,?,3,1,2,9,40,?,0,FALSE),"
            "(?,?,7,NULL,2,9,80,?,0,FALSE),(?,?,9,5,99,999,9999,?,0,TRUE),"
            "(?,?,8,5,50,500,5000,?,0,FALSE)",
            (user_id, chats[0][0], common, user_id, chats[1][0], common,
             user_id, chats[2][0], common, user_id, chats[3][0], common,
             foreign_id, chats[0][0], common),
        )
        today = datetime.now(timezone.utc).date()
        for age in range(3):
            await db.execute(
                "INSERT INTO daily_user_stats(user_id,chat_id,date,message_count) VALUES (?,?,?,1)",
                (user_id, chats[0][0], (today - timedelta(days=age)).isoformat()),
            )
        await db.execute(
            "INSERT INTO moderation_logs(chat_id,user_id,admin_id,action,created_at) VALUES (?,?,777,'warn',?), (?,?,888,'mute',?)",
            (chats[0][0], user_id, common - timedelta(days=2), chats[0][0], user_id, common - timedelta(days=1)),
        )

        first = await my_chat_tracker(limit=2, offset=0, query="", sort="week", db=db, user={"id": user_id})
        assert first["summary"] == {"chat_count": 3, "messages_all_time": 240, "messages_week": 36}
        assert first["filtered_count"] == 3 and first["next_offset"] == 2
        # Same week count is resolved by recent time and then opaque chat id;
        # the transport response itself must never disclose that id.
        assert [item["chat_title"] for item in first["items"]] == ["Лунный штаб", "Бета"]
        assert first["items"][0]["activity_streak_days"] == 3
        assert [item["action"] for item in first["items"][0]["sanction_history"]] == ["mute", "warn"]
        assert "chat_tg_id" not in repr(first) and "admin_id" not in repr(first)

        second = await my_chat_tracker(limit=2, offset=2, query="", sort="week", db=db, user={"id": user_id})
        assert [item["chat_title"] for item in second["items"]] == ["Альфа"] and second["next_offset"] is None
        found = await my_chat_tracker(limit=12, offset=0, query="лун", sort="recent", db=db, user={"id": user_id})
        assert found["filtered_count"] == 1 and found["items"][0]["chat_title"] == "Лунный штаб"
        literal_wildcard = await my_chat_tracker(limit=12, offset=0, query="%", sort="recent", db=db, user={"id": user_id})
        assert literal_wildcard["filtered_count"] == 0, "search wildcards must be treated as literal text"
        ranked = await my_chat_tracker(limit=12, offset=0, query="", sort="rank", db=db, user={"id": user_id})
        assert [item["chat_title"] for item in ranked["items"]] == ["Лунный штаб", "Альфа", "Бета"], "legacy NULL ranks belong last"
        try:
            await my_chat_tracker(limit=12, offset=0, query="", sort="unsupported", db=db, user={"id": user_id})
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError("unknown sort must fail closed")
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("Chat tracker: isolation/search/paging/streak/moderation proof OK")
