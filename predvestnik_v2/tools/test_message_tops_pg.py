#!/usr/bin/env python3
"""Focused PostgreSQL contract for deterministic message-top placement/privacy."""
from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

import asyncpg

from bot.core.database import _init_users_and_chats
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import stats


def loopback_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {
        "127.0.0.1", "localhost", "::1",
    }:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    transaction = connection.transaction()
    await transaction.start()
    db = PGAdapter(connection)
    try:
        await _init_users_and_chats(db)
        users = (9_910_001, 9_910_002, 9_910_003)
        chats = (-9_910_011, -9_910_012)
        for user_id in users:
            await db.execute(
                "INSERT INTO users(user_tg_id,user_tg_username) VALUES (?,?) "
                "ON CONFLICT (user_tg_id) DO UPDATE SET user_tg_username=EXCLUDED.user_tg_username",
                (user_id, f"top_user_{user_id}"),
            )
        await db.execute(
            "INSERT INTO chat_settings(chat_id,chat_title,include_in_global_top) VALUES "
            "(?, 'Visible chat', 1),(?, 'Hidden chat', 0) "
            "ON CONFLICT (chat_id) DO UPDATE SET chat_title=EXCLUDED.chat_title,"
            "include_in_global_top=EXCLUDED.include_in_global_top",
            chats,
        )
        rows = (
            (users[0], chats[0], 10), (users[1], chats[0], 10),
            (users[2], chats[0], 5), (users[2], chats[1], 20),
        )
        for user_id, chat_id, count in rows:
            await db.execute(
                "INSERT INTO user_chat_stats(user_tg_id,chat_tg_id,user_messages_count_all_time,is_left) "
                "VALUES (?,?,?,FALSE) ON CONFLICT (user_tg_id,chat_tg_id) DO UPDATE SET "
                "user_messages_count_all_time=EXCLUDED.user_messages_count_all_time,is_left=FALSE",
                (user_id, chat_id, count),
            )
            await db.execute(
                "INSERT INTO daily_user_stats(user_id,chat_id,date,message_count) VALUES (?,?,?,?) "
                "ON CONFLICT (user_id,chat_id,date) DO UPDATE SET message_count=EXCLUDED.message_count",
                (user_id, chat_id, "2099-01-02", count),
            )

        local = await stats.get_message_top_position(
            db, scope="local", entity_id=users[1], chat_id=chats[0],
            date_start="2099-01-02", date_end="2099-01-02",
        )
        assert local and (local["place"], local["msg_count"], local["total_count"]) == (2, 10, 3)

        global_position = await stats.get_message_top_position(
            db, scope="global", entity_id=users[2],
            date_start="2099-01-02", date_end="2099-01-02",
        )
        assert global_position and global_position["place"] == 1
        assert global_position["msg_count"] == 25, "player totals include opted-out chats"

        visible_chat = await stats.get_message_top_position(
            db, scope="chats", entity_id=chats[0],
            date_start="2099-01-02", date_end="2099-01-02",
        )
        hidden_chat = await stats.get_message_top_position(
            db, scope="chats", entity_id=chats[1],
            date_start="2099-01-02", date_end="2099-01-02",
        )
        assert visible_chat and visible_chat["place"] == 1 and visible_chat["total_count"] == 1
        assert hidden_chat is None, "opted-out chat must not receive a leaderboard position"
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=loopback_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("message tops PostgreSQL contract: OK")
