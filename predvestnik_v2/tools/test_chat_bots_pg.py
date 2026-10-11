#!/usr/bin/env python3
"""Боты среди участников на настоящем PostgreSQL: откуда берётся признак «бот» и почему боты не попадают в чистку, топ и списки.

Запуск: python tools/test_chat_bots_pg.py --dsn postgresql://... (пустая тестовая БД!)
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
dsn = ap.parse_args().dsn
os.environ["DATABASE_URL"] = dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "42"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CHAT = -300
OWN, ADMIN_BOT, OTHER_BOT, LATE_BOT, SERVICE = 999, 3001, 4001, 4002, 777000


def message(uid, username, is_bot=False, text="привет", chat_id=CHAT):
    """Настоящий Message из aiogram."""
    from aiogram.types import Chat, Message, User
    return Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=chat_id, type="supergroup", title="Тест"),
                   from_user=User(id=uid, is_bot=is_bot, first_name=username.title(), username=username), text=text)


class FakeBot:
    def __init__(self):
        self.sent, self.bots, self.asked = [], {OTHER_BOT, LATE_BOT}, []   # bots: кого Telegram называет ботом

    async def me(self):
        return SimpleNamespace(id=OWN, username="predvestnik_bot")

    async def get_chat_administrators(self, chat_id):
        return [SimpleNamespace(status="creator", user=SimpleNamespace(id=1001, is_bot=False)),
                SimpleNamespace(status="administrator", user=SimpleNamespace(id=ADMIN_BOT, is_bot=True))]

    async def get_chat(self, chat_id):
        return SimpleNamespace(permissions=None)

    async def get_chat_member(self, chat_id, user_id):
        self.asked.append(user_id)
        return SimpleNamespace(status="member", can_delete_messages=False, tag=None,
                               user=SimpleNamespace(id=user_id, is_bot=user_id in self.bots))

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text, kw))

    def __getattr__(self, name):
        async def call(*a, **kw):
            return None
        return call


class FakeMessage:
    def __init__(self, text, uid, username, chat=CHAT):
        self.text, self.caption, self.entities = text, None, []
        self.from_user = SimpleNamespace(id=uid, is_bot=False, username=username, full_name=username, first_name=username.title())
        self.chat = SimpleNamespace(id=chat, type="supergroup", title="Тест")
        self.content_type, self.sender_tag = "text", None
        self.reply_to_message = None
        self.replies = []

    async def reply(self, text, **kw):
        self.replies.append(text)

    async def answer(self, text, **kw):
        self.replies.append(text)

    async def delete(self):
        pass


async def run(db, bot, text, uid=1001, username="alpha"):
    from bot.chat import registry
    from bot.chat.framework import dispatch
    m = FakeMessage(text, uid, username)
    assert await dispatch(registry, m, bot, db)
    return " | ".join(m.replies)


async def flag(db, uid, chat=CHAT):
    async with db.execute("SELECT is_bot, user_messages_count_all_time FROM user_chat_stats "
                          "WHERE chat_tg_id = ? AND user_tg_id = ?", (chat, uid)) as cur:
        row = await cur.fetchone()
    return None if row is None else (bool(row[0]), int(row[1] or 0))


async def seed(db, uid, username, count=3, chat=CHAT):
    """Строка участника без признака «бот»: так выглядят старые записи, сделанные до того, как признак стали сохранять."""
    await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) ON CONFLICT (user_tg_id) DO NOTHING", (uid, username))
    await db.execute(
        "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time, is_left, is_bot, "
        "membership_since, joined_at) VALUES (?, ?, ?, FALSE, FALSE, NOW() - INTERVAL '60 days', NOW() - INTERVAL '60 days') "
        "ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE SET is_bot = FALSE, is_left = FALSE, user_messages_count_all_time = EXCLUDED.user_messages_count_all_time",
        (uid, chat, count))
    await db.commit()


def pure():
    from aiogram.types import User
    from services import chat_bots
    assert chat_bots.is_bot(User(id=5, is_bot=True, first_name="B"))
    assert not chat_bots.is_bot(User(id=5, is_bot=False, first_name="H"))
    assert chat_bots.is_bot(SimpleNamespace(id=SERVICE, is_bot=False))   # «Telegram» подписывает посты из канала и ботом не назван
    assert chat_bots.is_bot(SimpleNamespace(id=1087968824))                # анонимный админ
    assert not chat_bots.is_bot(None) and not chat_bots.is_bot(SimpleNamespace(id=7))


async def capture(db, bot):
    """Признак «бот» запоминается из сообщений, событий участников, списка админов и при запуске."""
    from bot.chat import members, ranks
    from bot.chat.tracking import record_message
    from services import chat_bots
    for uid, name in ((OTHER_BOT, "rosebot"), (ADMIN_BOT, "adminbot"), (OWN, "predvestnik_bot"), (SERVICE, "Telegram"), (3003, "joinbot")):
        await seed(db, uid, name)
    await seed(db, 2001, "silent", 0)
    await seed(db, 2002, "talker", 2)
    # Сообщение бота: счётчик не растёт, но признак ставится
    await record_message(db, message(OTHER_BOT, "rosebot", is_bot=True))
    assert await flag(db, OTHER_BOT) == (True, 3), await flag(db, OTHER_BOT)
    # Служебный аккаунт Telegram формально не бот, но человеком не является
    await record_message(db, message(SERVICE, "Telegram", is_bot=False))
    assert await flag(db, SERVICE) == (True, 3), await flag(db, SERVICE)
    # Люди учитываются как раньше
    await record_message(db, message(2002, "talker"))
    assert await flag(db, 2002) == (False, 3)
    # Новый бот в чате: строки участника ему не заводится
    await record_message(db, message(5555, "newbot", is_bot=True))
    assert await flag(db, 5555) is None
    # Событие участника: бот вошёл — пометка, но не участник
    joined = SimpleNamespace(chat=SimpleNamespace(id=CHAT, type="supergroup"),
                             old_chat_member=SimpleNamespace(status="left", user=SimpleNamespace(id=3003, is_bot=True)),
                             new_chat_member=SimpleNamespace(status="member", user=SimpleNamespace(id=3003, is_bot=True, username="joinbot")))
    await members.on_member_change(joined, bot, db)
    assert await flag(db, 3003) == (True, 3)
    # Список администраторов: бот-админ найден одним запросом
    await ranks.sync_owner(db, bot, CHAT, force=True)
    assert await flag(db, ADMIN_BOT) == (True, 3), await flag(db, ADMIN_BOT)
    # При запуске бот узнаёт самого себя
    chat_bots._marked.clear()
    await chat_bots.startup(db, bot)
    assert await flag(db, OWN) == (True, 3), await flag(db, OWN)
    # Помеченные известны базе; люди — нет
    assert await chat_bots.known(db, [OTHER_BOT, OWN, 2001, 2002]) == {OTHER_BOT, OWN}


async def purge_flow(db, bot):
    """Чистка не заносит в нарушители ботов — ни помеченных, ни тех, кого база ещё не знает."""
    from bot.chat import purge
    from bot.chat.tracking import local_now
    from services import chat_bots
    today = local_now().date()
    a, b = today - timedelta(days=7), today - timedelta(days=1)
    span = f"{a.strftime('%d.%m.%Y')}-{b.strftime('%d.%m.%Y')}"
    # Старые записи ботов без признака: Предвестник сам, чужой бот, ещё один чужой
    for uid in (OWN, OTHER_BOT, LATE_BOT):
        await seed(db, uid, f"bot{uid}", 1)
    await seed(db, 2001, "silent", 0)
    await seed(db, 2002, "talker", 2)
    chat_bots._marked.clear()
    vs = await purge.find_violators(db, CHAT, purge.Plan(10, a, b))
    ids = {v.user_id for v in vs}
    assert {2001, 2002} <= ids and SERVICE not in ids and ADMIN_BOT not in ids, ids   # служебные и помеченные уже отсеяны
    assert {OWN, OTHER_BOT, LATE_BOT} <= ids, ids                                      # непомеченные пока в списке: их найдёт проверка
    # Проверка перед чисткой: Telegram называет ботами своего и чужих
    kept, skipped = await purge.screen_violators(bot, db, CHAT, vs)
    assert skipped == 3 and {v.user_id for v in kept} == {2001, 2002}, (skipped, [v.user_id for v in kept])
    for u in (OWN, OTHER_BOT, LATE_BOT):
        assert (await flag(db, u))[0] is True, f"бот {u} не запомнен"
    assert (await flag(db, 2001))[0] is False, "людей проверка не метит"
    # Полная команда: боты не в досье и не в итогах
    for uid in (OWN, OTHER_BOT, LATE_BOT):
        await seed(db, uid, f"bot{uid}", 1)
    chat_bots._marked.clear()
    bot.sent.clear()
    out = await run(db, bot, f"бот чистка, 10 {span}")
    assert "Чистка началась" in out and "Не набрали норму: <b>2</b>" in out and "Боты не считаются: 3" in out, out
    await asyncio.sleep(1.5)
    dossiers = " ".join(t for _, t, _ in bot.sent if "Досье" in t)
    assert "silent" in dossiers and "talker" in dossiers and "bot4001" not in dossiers and "bot999" not in dossiers, dossiers
    s = await purge.active_session(db, CHAT)
    async with db.execute("SELECT user_id FROM purge_targets WHERE session_id = ?", (s[0],)) as cur:
        assert {int(r[0]) for r in await cur.fetchall()} == {2001, 2002}
    await run(db, bot, "бот чистка стоп")

    # Бот, до которого проверка не дошла (много нарушителей / сбой связи): отсеивается при отправке досье
    await seed(db, LATE_BOT, "bot4002", 1)
    chat_bots._marked.clear()
    old_limit, chat_bots.SCREEN_LIMIT = chat_bots.SCREEN_LIMIT, 0
    bot.sent.clear()
    try:
        out = await run(db, bot, f"бот чистка, 10 {span}")
        assert "Не набрали норму: <b>3</b>" in out, out                        # в списке он ещё есть
        await asyncio.sleep(2.0)
    finally:
        chat_bots.SCREEN_LIMIT = old_limit
    dossiers = " ".join(t for _, t, _ in bot.sent if "Досье" in t)
    assert "silent" in dossiers and "talker" in dossiers and "bot4002" not in dossiers, dossiers
    assert (await flag(db, LATE_BOT))[0] is True                                # и запомнен для следующих раз
    s = await purge.active_session(db, CHAT)
    async with db.execute("SELECT verdict FROM purge_targets WHERE session_id = ? AND user_id = ?", (s[0], LATE_BOT)) as cur:
        assert (await cur.fetchone())[0] == "skip"
    out = await run(db, bot, "бот чистка статус")
    assert "Не набрали норму: 2" in out, out                                    # пропущенный в итог не входит
    done = await run(db, bot, "бот чистка стоп")
    assert "Не набрали норму: 2" in done, done


async def lists(db, bot):
    """В топе, составе чата и карточке чата в админке боты не показываются."""
    from bot.chat import ranks, top
    from bot.chat.tracking import local_now
    day = local_now().date().isoformat()
    for uid, n in ((2002, 5), (OTHER_BOT, 50), (OWN, 40), (ADMIN_BOT, 30)):
        await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (?, ?, ?, ?) "
                         "ON CONFLICT (user_id, chat_id, date) DO UPDATE SET message_count = EXCLUDED.message_count",
                         (uid, CHAT, day, n))
    await db.commit()
    text, _ = await top.build(db, "c", "d", 0, CHAT)
    assert "talker" in text and "bot4001" not in text and "bot999" not in text and "adminbot" not in text, text
    text, _ = await top.build(db, "g", "d", 0, CHAT)
    assert "talker" in text and "bot4001" not in text and "bot999" not in text, text
    await ranks.store_rank(db, CHAT, OTHER_BOT, 3)
    await ranks.store_rank(db, CHAT, 2002, 3)
    out = await run(db, bot, "бот ранги")
    assert "talker" in out and "bot4001" not in out, out
    from services import admin_people
    card = await admin_people.chat(db, CHAT)
    assert all(x["id"] not in (OTHER_BOT, OWN, ADMIN_BOT) for x in card["top"]), card["top"]


async def main():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema

    await create_pool()
    await init_db()
    await ensure_chat_schema()
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        pure()
        bot = FakeBot()
        await capture(db, bot)
        await purge_flow(db, bot)
        await lists(db, bot)
    print("OK: bots among members (capture, purge, lists)")


asyncio.run(main())
