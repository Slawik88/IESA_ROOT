#!/usr/bin/env python3
"""Новый чат-бот на настоящем PostgreSQL: учёт сообщений, «бот топ», ранги.

Запуск: python tools/test_chat_bot_pg.py --dsn postgresql://... (пустая тестовая БД!)
"""
import argparse
import asyncio
import os
import sys
from types import SimpleNamespace

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
dsn = ap.parse_args().dsn
os.environ["DATABASE_URL"] = dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "42"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def msg(uid, chat, username, title="Тест"):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=uid, is_bot=False, username=username),
        chat=SimpleNamespace(id=chat, type="supergroup", title=title),
    )


async def main():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema
    from bot.chat.tracking import record_message
    from bot.chat import ranks, top

    await create_pool()
    await init_db()
    await ensure_chat_schema()
    await ensure_chat_schema()   # повторный запуск безопасен
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for _ in range(3):
            await record_message(db, msg(1001, -100, "alpha"))
        await record_message(db, msg(1002, -100, "beta"))
        await record_message(db, msg(1002, -200, "beta", "Другой"))

        text, pages = await top.build(db, "c", "d", 0, -100)
        assert pages == 1 and text.index("alpha") < text.index("beta"), text
        assert "3" in text
        text, _ = await top.build(db, "g", "w", 0, -100)
        assert "beta" in text and "alpha" in text
        text, _ = await top.build(db, "k", "d", 0, -100)
        assert text.index("Тест") < text.index("Другой"), text
        text, _ = await top.build(db, "c", "lw", 0, -100)
        assert "Пока тихо" in text

        # Ранги с нуля: старый local_rank не читается; владелец, права.
        await db.execute("UPDATE user_chat_stats SET local_rank = 5 WHERE user_tg_id = 1001")
        assert await ranks.get_rank(db, -100, 1001) == 0
        await ranks.store_rank(db, -100, 1002, 6)
        assert await ranks.get_rank(db, -100, 1002) == 6
        await ranks.set_owner(db, -100, 1001)
        assert await ranks.get_rank(db, -100, 1001) == ranks.OWNER
        assert await ranks.can(db, -100, 1002, "ban") and not await ranks.can(db, -100, 1002, "rights")
        await ranks.set_right(db, -100, "ban", 7, 1001)
        assert not await ranks.can(db, -100, 1002, "ban")
        assert await ranks.can(db, -100, 42, "rights")          # разработчик
        assert await ranks.get_rank(db, -100, 42) == ranks.DEV_LEVEL
        await moderation_flow(db)
    print("OK: chat bot on PostgreSQL")


class FakeBot:
    def __init__(self):
        self.calls, self.sent = [], []

    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    async def get_chat_administrators(self, chat_id):
        return [SimpleNamespace(status="creator", user=SimpleNamespace(id=1001))]

    async def get_chat(self, chat_id):
        return SimpleNamespace(permissions=None)

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text, kw))

    def __getattr__(self, name):   # restrict/ban/unban_chat_member
        async def call(*a, **kw):
            self.calls.append((name, a, kw))
        return call


class FakeMessage:
    def __init__(self, text, uid, username, chat=-100, reply_to=None):
        self.text, self.caption, self.entities = text, None, []
        self.from_user = SimpleNamespace(id=uid, is_bot=False, username=username, full_name=username)
        self.chat = SimpleNamespace(id=chat, type="supergroup", title="Тест")
        self.reply_to_message = reply_to
        self.replies, self.deleted = [], False

    async def reply(self, text, **kw):
        self.replies.append(text)

    async def delete(self):
        self.deleted = True


async def run(db, bot, text, uid=1001, username="alpha", **kw):
    from bot.chat import registry
    from bot.chat.framework import dispatch
    m = FakeMessage(text, uid, username, **kw)
    assert await dispatch(registry, m, bot, db)
    return " | ".join(m.replies)


async def moderation_flow(db):
    from bot.chat import moderation, ranks
    bot = FakeBot()
    await ranks.sync_owner(db, bot, -100, force=True)
    # owner 1001 (alpha), 1002 (beta) — Администратор (6); 42 — разработчик.
    await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (42, 'devuser'), (1003, 'gamma') ON CONFLICT DO NOTHING")
    await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id) VALUES (1003, -100) ON CONFLICT DO NOTHING")

    out = await run(db, bot, "бот лимит варнов, 2")
    assert "Лимит варнов: <b>2" in out, out
    out = await run(db, bot, "бот варн, @gamma 7д флуд")
    assert "(1/2)" in out and "флуд" in out, out
    out = await run(db, bot, "бот варн @gamma")
    assert "(2/2)" in out and "бессрочный" in out, out
    assert bot.sent and "Лимит варнов превышен" in bot.sent[-1][1], bot.sent   # ушло админам
    out = await run(db, bot, "бот варны @gamma")
    assert "2/2" in out, out
    out = await run(db, bot, "бот снять варн, @gamma")
    assert "Осталось: 1" in out, out
    out = await run(db, bot, "бот варн, @devuser")
    assert "разработчику" in out, out
    out = await run(db, bot, "бот варн, @alpha", uid=1002, username="beta")
    assert "не ниже" in out, out                                    # админ не наказывает владельца
    out = await run(db, bot, "бот варн, @alpha", uid=42, username="devuser")
    assert "(1/2)" in out, out                                      # разработчик может всех
    out = await run(db, bot, "бот мут, @gamma")
    assert "Срок обязателен" in out, out
    out = await run(db, bot, "бот мут, @gamma 2ч спам")
    assert "2ч" in out and bot.calls[-1][0] == "restrict_chat_member", out
    out = await run(db, bot, "бот мут, @gamma 5х")
    assert "Не понял срок" in out, out
    out = await run(db, bot, "бот бан, @gamma 5д")
    assert "5д" in out and await moderation.is_blacklisted(db, -100, 1003), out
    out = await run(db, bot, "бот снять бан @gamma")
    assert not await moderation.is_blacklisted(db, -100, 1003), out
    out = await run(db, bot, "бот защита, @gamma навсегда")
    assert "иммунитет" in out, out
    out = await run(db, bot, "бот иммунитет @gamma")
    assert "иммунитет" in out, out
    out = await run(db, bot, "-чат")
    assert "закрыт" in out, out
    m = FakeMessage("привет", 1003, "gamma")
    assert await moderation.closed_gate(db, bot, m) and m.deleted
    m = FakeMessage("привет", 1002, "beta")
    assert not await moderation.closed_gate(db, bot, m)               # админ пишет
    out = await run(db, bot, "+чат", uid=1003, username="gamma")
    assert out == "", out                                            # без «бот» и без права — молча
    out = await run(db, bot, "+чат")
    assert "открыт" in out, out
    out = await run(db, bot, "бот ранг, @gamma модератор", uid=1002, username="beta")
    assert "нет права выдавать" in out, out                          # по умолчанию с 7-го ранга
    await ranks.set_right(db, -100, "set_rank", 6, 1001)
    out = await run(db, bot, "бот ранг, @gamma модератор", uid=1002, username="beta")
    assert "Модератор" in out, out
    out = await run(db, bot, "бот ранг, @gamma администратор", uid=1002, username="beta")
    assert "ниже вашего" in out, out
    out = await run(db, bot, "бот ранги")
    assert "Владелец" in out and "beta" in out and "gamma" not in out, out   # gamma вне чата после бана
    out = await run(db, bot, "бот привязать админ чат")
    token = out.split("<code>бот админ чат ")[1].split("</code>")[0]
    out = await run(db, bot, f"бот админ чат {token}", chat=-555)
    assert "админ-чатом" in out, out
    from bot.chat.admin_chat import admin_chat_of
    assert await admin_chat_of(db, -100) == -555
    out = await run(db, bot, "бот бтп")
    assert "бот топ" in out, out


asyncio.run(main())
