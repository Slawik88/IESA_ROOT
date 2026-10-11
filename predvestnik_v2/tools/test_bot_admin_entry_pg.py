"""Путь в админку: команда «бот админка» в личке и в группе, кнопка, отказ не-персоналу и ссылка из группы.

Запуск: python tools/test_bot_admin_entry_pg.py --dsn postgresql://... (пустая тестовая БД!)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
dsn = ap.parse_args().dsn
os.environ["DATABASE_URL"] = dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "1001"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from types import SimpleNamespace  # noqa: E402

DEV, HELPER, PLAYER = 1001, 3003, 2002


class FakeBot:
    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")


class FakeMessage:
    def __init__(self, text, uid, chat):
        self.text, self.caption, self.entities = text, None, []
        self.from_user = SimpleNamespace(id=uid, is_bot=False, username=f"u{uid}", full_name=f"U{uid}", first_name=f"U{uid}")
        self.chat = SimpleNamespace(id=chat, type="supergroup" if chat < 0 else "private", title="Тест")
        self.reply_to_message = None
        self.replies = []

    async def reply(self, text, **kw):
        self.replies.append((text, kw))

    async def answer(self, text, **kw):
        self.replies.append((text, kw))

    def button(self):
        markup = self.replies[-1][1].get("reply_markup")
        return markup.inline_keyboard[0][0] if markup else None


async def run():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat import registry
    from bot.chat.framework import dispatch
    from bot.chat.schema import ensure_chat_schema
    from bot.startup_schema import ensure_runtime_schema

    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    await ensure_chat_schema()
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for uid, rank in ((DEV, 0), (HELPER, 3), (PLAYER, 0)):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, ?, ?)", (uid, f"u{uid}", rank))

        async def say(uid, chat, text="бот админка"):
            msg = FakeMessage(text, uid, chat)
            await dispatch(registry, msg, FakeBot(), db)
            return msg

        # Личка: кнопка web_app прямо на /bot-admin (хвост адреса и слеши не мешают)
        for url in ("https://iesasport.ch", "https://iesasport.ch/", "https://iesasport.ch/?x=1#top"):
            os.environ["MINIAPP_URL"] = url
            os.environ["MINIAPP_SHORT_NAME"] = "app"
            for who in (DEV, HELPER):
                msg = await say(who, who)
                btn = msg.button()
                assert btn is not None and btn.web_app is not None and btn.web_app.url == "https://iesasport.ch/bot-admin", (url, msg.replies)
                assert "Админка Предвестника" in msg.replies[-1][0]
        # Те же слова без «бот» в личке и синонимы
        for text in ("бот админ панель", "бот панель", "Бот Админка"):
            assert (await say(HELPER, HELPER, text)).button() is not None, text

        # Группа: web_app-кнопки там запрещены, ведём ссылкой на Mini App с параметром admin
        msg = await say(HELPER, -100)
        btn = msg.button()
        assert btn.url == "https://t.me/predvestnik_bot/app?startapp=admin" and btn.web_app is None, msg.replies
        # Нет короткого имени Mini App: ссылка в браузер и подсказка про личку
        os.environ["MINIAPP_SHORT_NAME"] = ""
        msg = await say(HELPER, -100)
        assert msg.button().url == "https://iesasport.ch/bot-admin" and "бот админка" in msg.replies[-1][0], msg.replies
        os.environ["MINIAPP_SHORT_NAME"] = "app"

        # Не персонал: отказ без кнопки, и в личке, и в группе
        for chat in (PLAYER, -100):
            msg = await say(PLAYER, chat)
            assert msg.replies and msg.button() is None and "только персоналу" in msg.replies[-1][0], msg.replies
        # Адрес сайта не настроен
        os.environ["MINIAPP_URL"] = ""
        msg = await say(DEV, DEV)
        assert msg.button() is None and "MINIAPP_URL" in msg.replies[-1][0], msg.replies
        os.environ["MINIAPP_URL"] = "http://insecure.example"   # не https: кнопку не даём
        msg = await say(DEV, DEV)
        assert msg.button() is None, msg.replies


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    print("OK: opening path of the admin from chat (private button, group link, access denied)")


main()
