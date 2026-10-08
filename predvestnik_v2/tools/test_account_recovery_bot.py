#!/usr/bin/env python3
"""Команды отмены удаления и восстановления аккаунта зовут канонический сервис."""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://x:y@localhost/z")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.chat import account, registry  # noqa: E402
from bot.chat.framework import dispatch  # noqa: E402


class FakeMessage:
    def __init__(self, text: str, user_id: int = 42):
        self.text, self.caption, self.entities, self.reply_to_message = text, None, [], None
        self.from_user = SimpleNamespace(id=user_id, is_bot=False, username="u", full_name="U")
        self.chat = SimpleNamespace(id=user_id, type="private")
        self.replies = []

    async def reply(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeBot:
    async def me(self):
        return SimpleNamespace(username="predvestnik_bot")


async def main() -> None:
    calls = []

    async def cancel(db, user_id):
        calls.append(("cancel", db, user_id))
        return True, "Отмена подтверждена"

    async def restore(db, user_id):
        calls.append(("restore", db, user_id))
        return True, "Аккаунт восстановлен"

    account.account_deletion.cancel_deletion = cancel
    account.account_deletion.restore_account = restore
    db = object()
    first, second = FakeMessage("бот отменить удаление"), FakeMessage("восстановить аккаунт")
    second.text = "бот восстановить аккаунт"
    await dispatch(registry, first, FakeBot(), db)
    await dispatch(registry, second, FakeBot(), db)

    assert calls == [("cancel", db, 42), ("restore", db, 42)], calls
    assert first.replies[0][0] == "Отмена подтверждена"
    assert "бот я" in second.replies[0][0]


asyncio.run(main())
print("OK: Telegram account cancel/restore commands call the canonical service")
