#!/usr/bin/env python3
"""PostgreSQL contract for canonical module switches and immutable receipts."""
from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

import asyncpg

from bot.core.database import _init_users_and_chats
from core.chat_modules import CHAT_MODULE_KEYS, chat_module_default
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import chat_module_audit


def loopback_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    outer = connection.transaction()
    await outer.start()
    db = PGAdapter(connection)
    try:
        await _init_users_and_chats(db)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS global_module_toggles(
                module_key TEXT PRIMARY KEY, enabled INTEGER DEFAULT 1,
                disabled_reason TEXT, updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await chat_module_audit.install_schema(db)
        # Startup schema installation must be safe to repeat without briefly
        # removing the append-only protection.
        await chat_module_audit.install_schema(db)
        actor, chat = 9_940_001, -9_940_002
        await db.execute(
            "INSERT INTO users(user_tg_id,user_tg_username) VALUES (?,?) "
            "ON CONFLICT(user_tg_id) DO UPDATE SET user_tg_username=EXCLUDED.user_tg_username",
            (actor, "module_operator"),
        )

        assert {item["key"] for item in chat_module_audit.catalog()} == CHAT_MODULE_KEYS
        assert chat_module_default("module_echo") is False
        assert next(item for item in chat_module_audit.catalog() if item["key"] == "module_echo")["default_enabled"] is False
        first = await chat_module_audit.set_chat_module(
            db, chat_id=chat, module_key="module_mafia", enabled=False,
            actor_id=actor, source="contract_test",
        )
        assert first == {"changed": True, "before": 1, "after": 0}
        replay = await chat_module_audit.set_chat_module(
            db, chat_id=chat, module_key="module_mafia", enabled=False,
            actor_id=actor, source="contract_test",
        )
        assert replay["changed"] is False
        chat_rows = await chat_module_audit.recent(db, scope="chat", chat_id=chat)
        assert len(chat_rows) == 1 and chat_rows[0]["actor_name"] == "module_operator"

        global_change = await chat_module_audit.set_global_module(
            db, module_key="module_echo", enabled=True, actor_id=actor,
            reason=None, source="contract_test",
        )
        assert global_change == {"changed": True, "before": 0, "after": 1}
        global_rows = await chat_module_audit.recent(db, scope="global")
        assert len(global_rows) == 1 and global_rows[0]["module_key"] == "module_echo"

        savepoint = connection.transaction()
        await savepoint.start()
        try:
            await connection.execute("DELETE FROM chat_module_audit WHERE id=$1", chat_rows[0]["id"])
        except asyncpg.RaiseError:
            await savepoint.rollback()
        else:
            raise AssertionError("append-only audit row was deleted")
    finally:
        await outer.rollback()
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True, type=loopback_dsn)
    args = parser.parse_args()
    asyncio.run(run(args.dsn))
    print("chat module audit: contract OK")


if __name__ == "__main__":
    main()
