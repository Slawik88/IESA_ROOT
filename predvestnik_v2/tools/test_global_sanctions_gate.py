#!/usr/bin/env python3
"""Contract tests for the pre-writer global-sanctions gate."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "123456:offline-sanctions-test")
os.environ.setdefault("BOT_USERNAME", "offline_sanctions_test")
os.environ.setdefault("MINIAPP_URL", "https://preprod.invalid/predvestnik")
os.environ.setdefault("DATABASE_URL", "postgresql://offline@127.0.0.1:55432/offline")

from aiogram.types import Update

from bot.middlewares import db as db_middleware_module
from bot.middlewares import global_sanctions_mw as sanctions


def text_update(text: str) -> Update:
    return Update.model_validate({
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": -100501, "type": "supergroup", "title": "Test"},
            "from": {"id": 501, "is_bot": False, "first_name": "Player"},
            "text": text,
        },
    })


class EmptyCursor:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def fetchone(self):
        return None


class EmptyDatabase:
    def execute(self, *_args, **_kwargs):
        return EmptyCursor()


async def run() -> None:
    original_rank = sanctions.get_global_rank
    original_user_ban = sanctions.global_moderation.is_user_banned
    original_chat_ban = sanctions.global_moderation.is_chat_banned
    original_chat_restriction = sanctions.global_moderation.get_chat_restriction
    original_user_restriction = sanctions.global_moderation.get_user_restriction
    try:
        async def rank(_db, _user_id):
            return 0

        async def user_banned(_db, _user_id):
            return True

        async def chat_banned(_db, _chat_id):
            return False

        async def no_restriction(_db, _entity_id):
            return None

        sanctions.get_global_rank = rank
        sanctions.global_moderation.is_user_banned = user_banned
        sanctions.global_moderation.is_chat_banned = chat_banned
        sanctions.global_moderation.get_chat_restriction = no_restriction
        sanctions.global_moderation.get_user_restriction = no_restriction

        denied_data = {
            "event_from_user": SimpleNamespace(id=501),
            "event_chat": SimpleNamespace(id=-100501),
        }
        assert not await sanctions.evaluate_global_sanctions(
            EmptyDatabase(), text_update("ordinary text"), denied_data
        )
        assert denied_data["_sanctions_blocked"]

        appeal_data = {
            "event_from_user": SimpleNamespace(id=501),
            "event_chat": SimpleNamespace(id=-100501),
        }
        assert await sanctions.evaluate_global_sanctions(
            EmptyDatabase(), text_update("бот апелляция, причина"), appeal_data
        )
        assert appeal_data["user_banned"]

        # Once evaluated, the later middleware must reuse exactly the same
        # result rather than create a second authorization decision.
        assert await sanctions.evaluate_global_sanctions(
            EmptyDatabase(), text_update("ordinary text"), appeal_data
        )

        writer_calls: list[tuple] = []
        original_pool = db_middleware_module.get_pool
        original_adapter = db_middleware_module.PGAdapter
        original_evaluate = db_middleware_module.evaluate_global_sanctions
        original_update_user = db_middleware_module.users.update_user
        try:
            @asynccontextmanager
            async def acquire():
                yield object()

            class Pool:
                def acquire(self):
                    return acquire()

            async def allowed_but_banned(_db, _event, data):
                data["user_banned"] = True
                return True

            async def record_update(*args):
                writer_calls.append(args)

            db_middleware_module.get_pool = lambda: Pool()
            db_middleware_module.PGAdapter = lambda _connection: EmptyDatabase()
            db_middleware_module.evaluate_global_sanctions = allowed_but_banned
            db_middleware_module.users.update_user = record_update

            called = False

            async def handler(_event, _data):
                nonlocal called
                called = True

            event = text_update("бот помощь")
            await db_middleware_module.db_middleware(
                handler,
                event,
                {
                    "event_from_user": SimpleNamespace(id=501, username="player", is_bot=False),
                    "event_chat": SimpleNamespace(id=-100501, type="supergroup", title="Test"),
                },
            )
            assert called
            assert writer_calls == []
        finally:
            db_middleware_module.get_pool = original_pool
            db_middleware_module.PGAdapter = original_adapter
            db_middleware_module.evaluate_global_sanctions = original_evaluate
            db_middleware_module.users.update_user = original_update_user
    finally:
        sanctions.get_global_rank = original_rank
        sanctions.global_moderation.is_user_banned = original_user_ban
        sanctions.global_moderation.is_chat_banned = original_chat_ban
        sanctions.global_moderation.get_chat_restriction = original_chat_restriction
        sanctions.global_moderation.get_user_restriction = original_user_restriction


asyncio.run(run())
print("global sanctions gate: contract OK")
