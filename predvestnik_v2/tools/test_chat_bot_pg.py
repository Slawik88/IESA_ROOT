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
    await purge_flow(db, bot)


async def purge_flow(db, bot):
    from datetime import timedelta
    from bot.chat import purge
    from bot.chat.tracking import local_now
    # Участники: 2001 молчал, 2002 писал, 2003 с иммунитетом, beta — админ (пишет в чистку).
    today = local_now().date()
    for uid, name in ((2001, "silent"), (2002, "talker"), (2003, "immune")):
        await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) ON CONFLICT DO NOTHING", (uid, name))
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, membership_since) "
                         "VALUES (?, -100, NOW() - INTERVAL '30 days') ON CONFLICT DO NOTHING", (uid,))
    await db.execute("UPDATE user_chat_stats SET is_immune = TRUE WHERE user_tg_id = 2003")
    await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (2002, -100, ?, 50)",
                     ((today - timedelta(days=2)).isoformat(),))
    a, b = today - timedelta(days=7), today - timedelta(days=1)
    span = f"{a.strftime('%d.%m.%Y')}-{b.strftime('%d.%m.%Y')}"
    out = await run(db, bot, f"бот чистка, 10 {span}", uid=1002, username="beta")
    assert "нет права" in out, out
    await asyncio.sleep(0)
    out = await run(db, bot, f"бот чистка, 10 {span}")
    assert "Чистка началась" in out, out
    vs = await purge.find_violators(db, -100, purge.Plan(10, a, b))
    ids = {v.user_id for v in vs}
    assert 2001 in ids and 2002 not in ids and 2003 not in ids and 1002 not in ids and 1001 not in ids, ids
    await asyncio.sleep(1.5)       # досье уходят фоном
    assert any("Досье" in t for _, t, _ in bot.sent), [t[:30] for _, t, _ in bot.sent]
    m = FakeMessage("болтаю", 2002, "talker")
    assert await purge.purge_gate(db, bot, m) and m.deleted
    m = FakeMessage("я админ", 1002, "beta")
    assert not await purge.purge_gate(db, bot, m)
    s = await purge.active_session(db, -100)
    await db.execute("UPDATE purge_targets SET verdict = 'kick' WHERE session_id = ? AND user_id = 2001", (s[0],))
    out = await run(db, bot, "бот чистка статус")
    assert "Кикнуто: 1" in out, out
    from bot.chat import registry
    from bot.chat.framework import dispatch
    m = FakeMessage("бот чистка стоп", 1001, "alpha")
    answers = []
    async def answer(text, **kw):
        answers.append(text)
    m.answer = answer
    assert await dispatch(registry, m, bot, db)
    assert answers and "чат открыт" in answers[0] and "Кикнуто: 1" in answers[0], answers
    assert await purge.active_session(db, -100) is None
    await sanctions_flow(db, bot)


async def sanctions_flow(db, bot):
    from bot.chat import sanctions
    out = await run(db, bot, "бот бан, @silent 3д")
    assert "забанен" in out, out
    out = await run(db, bot, "бот мут, @talker 1ч")
    out = await run(db, bot, "бот варн, @talker")
    text, kb = await sanctions.list_view(db, 1001, -100, "ban", 0)
    assert "silent" in text, text
    text, _ = await sanctions.list_view(db, 1001, -100, "mute", 0)
    assert "talker" in text, text
    text, _ = await sanctions.list_view(db, 1001, -100, "warn", 0)
    assert "talker" in text, text
    text, _ = await sanctions.list_view(db, 1001, -100, "shield", 0)
    assert "иммунитет" in text, text
    text, _ = await sanctions.list_view(db, 1001, -100, "kick", 0)
    assert "silent" not in text or "Кики" in text
    text, kb = await sanctions.card_view(db, 1001, -100, "mute", 0, 2002)
    assert "Мут" in text and "Варнов: 1" in text, text
    await sanctions._apply(bot, db, -100, 2002, 1001, "unmute")
    await sanctions._apply(bot, db, -100, 2002, 1001, "unwarn")
    await sanctions._apply(bot, db, -100, 2001, 1001, "unban")
    text, _ = await sanctions.card_view(db, 1001, -100, "mute", 0, 2002)
    assert "нет" in text, text
    text, _ = await sanctions.list_view(db, 1001, -100, "ban", 0)
    assert "silent" not in text, text
    out = await run(db, bot, "бот санкции", uid=2002, username="talker")
    assert "нет права" in out, out
    await profile_flow(db, bot)


async def profile_flow(db, bot):
    await db.execute("UPDATE users SET user_balance_mora = 1500, user_balance_diamonds = 12.5 WHERE user_tg_id = 2002")
    await db.execute("INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name, marriage_date) "
                     "VALUES (-100, 2002, 'Talker', 1001, 'Alpha', NOW())")
    out = await run(db, bot, "бот я", uid=2002, username="talker")
    assert "@talker" in out and "1 500" in out and "12.5" in out and "Сообщения" in out, out
    assert "@\u200balpha" in out and "@alpha" not in out, out          # партнёр без пинга
    assert "ID:" not in out, out                                        # обычный игрок ID не видит
    out = await run(db, bot, "бот кто, @talker", uid=42, username="devuser")
    assert "ID: <code>2002</code>" in out and "Создатель" not in out, out
    out = await run(db, bot, "бот кто @nobody_here")
    assert "Не нашёл" in out, out
    out = await run(db, bot, "бот баланс", uid=2002, username="talker")
    assert "Мора" in out and "Зарники" in out and "Тёмная" not in out, out
    await transfer_flow(db, bot)


async def transfer_flow(db, bot):
    from bot.chat import transfer
    out = await run(db, bot, "бот перевод, @alpha 300", uid=2002, username="talker")
    assert "Какую валюту" in out, out

    class Call:
        def __init__(self, uid, cur, amount="300", msg_id=77):
            self.from_user = SimpleNamespace(id=uid)
            self.data_cb = transfer.TransferCB(uid=2002, to=1001, amount=amount, cur=cur)
            self.edited, self.alerts = [], []
            async def edit_text(text, **kw):
                self.edited.append(text)
            self.message = SimpleNamespace(chat=SimpleNamespace(id=-100), message_id=msg_id, edit_text=edit_text)
        async def answer(self, text=None, show_alert=False):
            self.alerts.append(text)

    async def bal(uid):
        async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id = ?", (uid,)) as cur:
            return float((await cur.fetchone())[0] or 0)

    a0, b0 = await bal(2002), await bal(1001)
    c = Call(1001, "mora")
    await transfer.on_transfer(c, c.data_cb, db)
    assert "не ваш" in c.alerts[0]                                   # чужая кнопка
    c = Call(2002, "zarniki")
    await transfer.on_transfer(c, c.data_cb, db)
    assert "нельзя" in c.alerts[0]
    c = Call(2002, "mora")
    await transfer.on_transfer(c, c.data_cb, db)
    assert "Переведено" in c.edited[0], (c.edited, c.alerts)
    c = Call(2002, "mora")                                            # повторное нажатие той же кнопки
    await transfer.on_transfer(c, c.data_cb, db)
    assert await bal(2002) == a0 - 300 and await bal(1001) == b0 + 300
    c = Call(2002, "mora", amount="99999", msg_id=78)
    await transfer.on_transfer(c, c.data_cb, db)
    assert "Не хватает" in c.alerts[0] and await bal(2002) == a0 - 300
    c = Call(2002, "mora", amount="1.5", msg_id=79)
    await transfer.on_transfer(c, c.data_cb, db)
    assert "целым" in c.alerts[0]
    assert transfer.parse_amount("@ник 12,5") == transfer.Decimal("12.5") and transfer.parse_amount("0") is None
    await streak_flow(db, bot)


async def streak_flow(db, bot):
    from datetime import timedelta
    from bot.chat import streak
    from bot.chat.tracking import local_now, record_message
    today = local_now().date()
    await record_message(db, msg(3001, -100, "streaker"))
    assert (await streak.streak_of(db, 3001, today))[:2] == (1, 1)
    await record_message(db, msg(3001, -100, "streaker"))             # тот же день — не растёт
    assert (await streak.streak_of(db, 3001, today))[0] == 1
    await db.execute("UPDATE daily_login SET last_login = last_login - INTERVAL '1 day' WHERE user_id = 3001")
    await record_message(db, msg(3001, -200, "streaker", "Другой"))  # вчера был — +1, любой чат
    assert (await streak.streak_of(db, 3001, today))[:3] == (2, 2, True)
    await db.execute("UPDATE daily_login SET last_login = last_login - INTERVAL '3 days' WHERE user_id = 3001")
    assert (await streak.streak_of(db, 3001, today))[:2] == (0, 2)   # пропуск обнуляет показ
    await record_message(db, msg(3001, -100, "streaker"))
    assert (await streak.streak_of(db, 3001, today))[:2] == (1, 2)
    out = await run(db, bot, "бот стрик", uid=3001, username="streaker")
    assert "стрик: 1" in out and "Лучший: 2" in out and "🟥" in out, out


asyncio.run(main())
