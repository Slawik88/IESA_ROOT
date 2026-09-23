#!/usr/bin/env python3
"""Account recovery commands remain callable after legacy profile removal."""
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

module_path = Path(__file__).resolve().parents[1] / "bot" / "handlers" / "account.py"
spec = importlib.util.spec_from_file_location("release_account_handler", module_path)
assert spec and spec.loader
account = importlib.util.module_from_spec(spec)
spec.loader.exec_module(account)


class FakeMessage:
    def __init__(self, user_id: int = 42):
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


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
    message = FakeMessage()
    db = object()

    await account.cmd_cancel_deletion(message, db)
    await account.cmd_restore_account(message, db)

    assert calls == [("cancel", db, 42), ("restore", db, 42)]
    assert message.answers[0] == ("Отмена подтверждена", {"parse_mode": "HTML"})
    assert "бот я" in message.answers[1][0]
    assert message.answers[1][1] == {"parse_mode": "HTML"}


asyncio.run(main())
print("OK: Telegram account cancel/restore commands call the canonical service")
