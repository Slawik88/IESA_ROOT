#!/usr/bin/env python3
"""Regression contract for retained chat-settings callback authorization."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "123456:offline-settings-test")
os.environ.setdefault("BOT_USERNAME", "offline_settings_test")
os.environ.setdefault("MINIAPP_URL", "https://preprod.invalid/predvestnik")
os.environ.setdefault("DATABASE_URL", "postgresql://offline@127.0.0.1:55432/offline")

ROOT = Path(__file__).resolve().parents[1]

from bot.handlers import chat_settings
from bot.middlewares.module_check_mw import module_disabled_reason


class Query:
    def __init__(self):
        self.from_user = SimpleNamespace(id=77)
        self.message = SimpleNamespace(chat=SimpleNamespace(id=-100700, type="supergroup"))
        self.answers: list[str] = []

    async def answer(self, text: str, **_kwargs):
        self.answers.append(text)


class Bot:
    def __init__(self, status: str, can_manage: bool = False):
        self.status = status
        self.can_manage = can_manage
        self.calls = 0

    async def get_chat_member(self, _chat_id: int, _user_id: int):
        self.calls += 1
        return SimpleNamespace(status=self.status, can_manage_chat=self.can_manage)


async def run() -> None:
    original_owner = chat_settings.check_callback_owner
    original_stats = chat_settings.chat_repo.get_chat_stats
    original_gate = chat_settings._can_use_settings_callback
    original_update = chat_settings.mod_db.update_chat_settings
    try:
        async def owned(_query, _owner_id):
            return True

        chat_settings.check_callback_owner = owned
        callback = chat_settings.ChatSettingsCB(action="toggle", key="events_enabled", user_id=77)

        async def rank_four(_db, _user_id, _chat_id):
            return {"local_rank": 4}

        chat_settings.chat_repo.get_chat_stats = rank_four
        demoted = Query()
        bot = Bot("administrator", True)
        assert not await chat_settings._can_use_settings_callback(demoted, callback, object(), bot)
        assert bot.calls == 0
        assert "текущий ранг" in demoted.answers[0]

        async def rank_five(_db, _user_id, _chat_id):
            return {"local_rank": 5}

        chat_settings.chat_repo.get_chat_stats = rank_five
        revoked = Query()
        bot = Bot("member")
        assert not await chat_settings._can_use_settings_callback(revoked, callback, object(), bot)
        assert bot.calls == 1
        assert "Telegram" in revoked.answers[0]

        current = Query()
        bot = Bot("administrator", True)
        assert await chat_settings._can_use_settings_callback(current, callback, object(), bot)
        assert bot.calls == 1
        assert current.answers == []

        # Retained Telegram cards can outlive a product change.  A former
        # auction-rank button must fail closed before it reaches the generic
        # settings writer, even when its owner still has valid admin rights.
        async def allowed_gate(*_args, **_kwargs):
            return True

        writes: list[dict] = []

        async def record_write(_db, _chat_id, **updates):
            writes.append(updates)

        chat_settings._can_use_settings_callback = allowed_gate
        chat_settings.mod_db.update_chat_settings = record_write
        stale = Query()
        await chat_settings.cb_set_rank(
            stale,
            chat_settings.ChatSettingsCB(
                action="set_rank", key="auction_min_rank", user_id=77,
            ),
            object(), Bot("administrator", True),
        )
        assert writes == []
        assert stale.answers and "больше не используется" in stale.answers[0]

        assert set(chat_settings._MODULE_SETTINGS) == {
            "module_mafia", "module_rhythm", "module_pets",
            "module_quests", "module_warps", "module_echo",
        }
        assert set(chat_settings._TOGGLE_SETTINGS) == {
            "nsfw_warps_allowed", "include_in_global_top",
        }

        class Cursor:
            def __init__(self, row):
                self.row = row
            async def __aenter__(self):
                return self
            async def __aexit__(self, *_args):
                return None
            async def fetchone(self):
                return self.row

        class MissingGlobalRowDB:
            def __init__(self):
                self.calls = 0
            def execute(self, _sql, _args=()):
                self.calls += 1
                # Chat has no local override; global row is also absent.
                return Cursor(None)

        assert "не включён глобально" in await module_disabled_reason(
            MissingGlobalRowDB(), -100700, "module_echo"
        )
        assert await module_disabled_reason(
            MissingGlobalRowDB(), -100700, "module_mafia"
        ) is None

        admin_ui = (ROOT / "FastAPI" / "static" / "app.07.js").read_text(encoding="utf-8")
        assert "module_catalog" in admin_ui
        assert "'module_mafia','module_rhythm','module_pets','module_quests','module_warps','module_echo'" in admin_ui
        assert "tog('module_games'" not in admin_ui
        assert "tog('module_auction'" not in admin_ui
        assert "tog('module_expeditions'" not in admin_ui
        assert "tog('notif_auction'" not in admin_ui
        console_ui = (ROOT / "FastAPI" / "static" / "app.08.js").read_text(encoding="utf-8")
        assert "d.catalog||[]" in console_ui
        assert "module_shop','🛒'" not in console_ui
        assert "/admin/dev/global-modules" in console_ui
        assert "devCommitChatMod" in console_ui and "Отключить модуль в чате?" in console_ui
        repo_source = (ROOT / "infrastructure" / "repositories" / "chat_module_audit.py").read_text(encoding="utf-8")
        assert "pg_advisory_xact_lock" in repo_source
        assert "DROP TRIGGER" not in repo_source
        admin_source = (ROOT / "FastAPI" / "routers" / "admin.py").read_text(encoding="utf-8")
        assert "async with db.connection.transaction():" in admin_source
    finally:
        chat_settings.check_callback_owner = original_owner
        chat_settings.chat_repo.get_chat_stats = original_stats
        chat_settings._can_use_settings_callback = original_gate
        chat_settings.mod_db.update_chat_settings = original_update


asyncio.run(run())
print("chat settings callback authorization: contract OK")
