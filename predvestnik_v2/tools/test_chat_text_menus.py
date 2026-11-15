"""Text menu entrypoints and neighbouring deep links after retiring HTML cards."""
import asyncio
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:local-test")
os.environ.setdefault("DATABASE_URL", "postgresql://local/test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiogram.filters import CommandObject
from aiogram.types import Message
from fastapi import FastAPI
from bot.chat import mafia, notify, payments, registry
from FastAPI.routers.bot_admin import router as admin_router


async def run():
    message = Message.model_validate({"message_id": 1, "date": 1, "chat": {"id": 101, "type": "private"},
                                      "from": {"id": 101, "is_bot": False, "first_name": "QA"}, "text": "/start plan"})
    with (patch.object(notify, "_quiet", AsyncMock(return_value=False)),
          patch.object(notify.dm_push, "confirm_contact", AsyncMock()) as contact,
          patch.object(notify, "plan_view", AsyncMock(return_value=("План дня", None))) as plan,
          patch.object(Message, "answer", AsyncMock()) as answer):
        await payments.cmd_start(message, CommandObject(command="start", args="plan"), object(), object())
        assert plan.await_count == contact.await_count == 1
        assert answer.call_args.args[0] == "План дня"
    with patch.object(mafia, "handle_start_payload", AsyncMock(return_value=True)) as start:
        for payload in ("mrules", "mr", "mj123"):
            await payments.cmd_start(message, CommandObject(command="start", args=payload), object(), object())
            assert start.call_args.args[1] == payload
        assert start.await_count == 3
    with patch.object(payments, "_send_packages_menu", AsyncMock()) as packages:
        await payments.cmd_start(message, CommandObject(command="start", args="buyzarniki"), object(), object())
        packages.assert_awaited_once()
    ctx = SimpleNamespace(command=SimpleNamespace(name="план"), message=SimpleNamespace(chat=SimpleNamespace(type="supergroup")),
                          bot=SimpleNamespace(me=AsyncMock(return_value=SimpleNamespace(username="qa_bot"))), reply=AsyncMock())
    await notify.cmd_plan(ctx)
    assert ctx.reply.call_args.kwargs["reply_markup"].inline_keyboard[0][0].url == "https://t.me/qa_bot?start=plan"
    assert registry.get("табло") is None and registry.get("сапёр") is None
    app = FastAPI()
    app.include_router(admin_router)
    assert not any("widgets" in path for path in app.openapi()["paths"])
    print("PASS: text plan deep link, private contact, group plan link, mafia ready/rules/join links, purchase menu, retired commands and admin endpoint")


if __name__ == "__main__":
    asyncio.run(run())
