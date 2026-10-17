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

        # DEFAULT новых строк chat_settings выровнен на стандарт 1/1/2: пустой
        # INSERT больше не создаёт «легаси» пороги 3/4/5 (до выравнивания DDL).
        fresh_chat = -9_940_009
        await db.execute("INSERT INTO chat_settings(chat_id) VALUES (?)", (fresh_chat,))
        fresh_cursor = await db.execute(
            "SELECT rank_mute, rank_kick, rank_ban FROM chat_settings WHERE chat_id=?",
            (fresh_chat,),
        )
        fresh = await fresh_cursor.fetchone()
        assert (int(fresh[0]), int(fresh[1]), int(fresh[2])) == (1, 1, 2)

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

        # Глобальные состояния читаются поверх global_module_toggles (дефолт = реестр).
        states = await chat_module_audit.global_states(db)
        assert set(states) == set(CHAT_MODULE_KEYS)
        assert states["module_echo"] == {"enabled": True, "disabled_reason": None}
        assert states["module_mafia"]["enabled"] is True  # локальный выключатель ≠ глобальный

        # Скалярный аудит настроек: no-op не пишется, изменение — пишется (с подписью).
        from infrastructure.repositories import chat_settings_audit, chat_settings_reset
        assert await chat_settings_audit.record(
            db, chat_id=chat, setting_key="rank_warn", before=2, after=2,
            actor_id=actor, source="contract_test",
        ) is False
        assert await chat_settings_audit.record(
            db, chat_id=chat, setting_key="rank_warn", before=2, after=5,
            actor_id=actor, source="contract_test",
        ) is True
        setting_rows = await chat_settings_audit.recent(db, chat_id=chat, limit=5)
        assert len(setting_rows) == 1
        assert setting_rows[0]["setting_key"] == "rank_warn"
        assert setting_rows[0]["label"].startswith("⚠️")
        assert setting_rows[0]["actor_name"] == "module_operator"

        # Сброс к стандарту: rank_warn возвращается к 2, выключенный module_mafia — к вкл.
        # Сначала выравниваем скалярные значения к дефолтам: preprod-БД могла хранить
        # строку chat_settings, созданную до выравнивания DDL (легаси-пороги 3/4/5).
        from core.chat_settings_defaults import CHAT_SETTING_DEFAULTS
        from infrastructure.repositories.moderation import (
            get_chat_settings, update_chat_settings,
        )
        for key, default in CHAT_SETTING_DEFAULTS.items():
            await update_chat_settings(db, chat, **{key: default})
        await update_chat_settings(db, chat, rank_warn=5)
        reset_result = await chat_settings_reset.reset_chat_settings_to_defaults(
            db, chat_id=chat, actor_id=actor, source="contract_test",
        )
        assert reset_result == {"modules_changed": 1, "settings_changed": 1}
        restored = await get_chat_settings(db, chat)
        assert int(restored["rank_warn"]) == 2 and int(restored["module_mafia"]) == 1

        # Отвязка админ-чата: DELETE маршрута + чек в журнал настроек.
        await db.execute(
            "CREATE TABLE IF NOT EXISTS chat_links("
            "main_chat_id BIGINT PRIMARY KEY, admin_chat_id BIGINT, "
            "added_at TIMESTAMP DEFAULT NOW())"
        )
        await db.execute(
            "CREATE TABLE IF NOT EXISTS purge_sessions("
            "id BIGSERIAL PRIMARY KEY, chat_id BIGINT, status TEXT)"
        )
        await db.execute(
            "INSERT INTO chat_links(main_chat_id, admin_chat_id) VALUES (?, ?) "
            "ON CONFLICT(main_chat_id) DO UPDATE SET admin_chat_id=EXCLUDED.admin_chat_id",
            (chat, -9_940_003),
        )
        from infrastructure.repositories import routing
        assert await routing.unbind_admin_chat(
            db, main_chat_id=chat, actor_id=actor, source="contract_test",
        ) == -9_940_003
        assert await routing.get_admin_chat(db, chat) is None
        unbind_rows = await chat_settings_audit.recent(db, chat_id=chat, limit=5)
        assert unbind_rows[0]["setting_key"] == "admin_chat"

        savepoint = connection.transaction()
        await savepoint.start()
        try:
            await connection.execute("DELETE FROM chat_module_audit WHERE id=$1", chat_rows[0]["id"])
        except asyncpg.RaiseError:
            await savepoint.rollback()
        else:
            raise AssertionError("append-only audit row was deleted")

        savepoint = connection.transaction()
        await savepoint.start()
        try:
            await connection.execute(
                "DELETE FROM chat_settings_audit WHERE id=$1", setting_rows[0]["id"])
        except asyncpg.RaiseError:
            await savepoint.rollback()
        else:
            raise AssertionError("append-only settings audit row was deleted")
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
