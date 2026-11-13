#!/usr/bin/env python3
"""Кто в чате, а кто ушёл, на настоящем PostgreSQL: ушедший не висит в топе, неактивах и чистке.

Сценарии из прода: человек сам вышел из чата, а бот продолжал показывать его в «бот топ» и «бот неактивы»,
хотя кикнуть его было нельзя — в чате его уже нет.

Запуск: python tools/test_chat_membership_pg.py --dsn postgresql://... (пустая тестовая БД!)
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
dsn = ap.parse_args().dsn
os.environ["DATABASE_URL"] = dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "42"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CHAT, PLAIN = -7100, -7200   # PLAIN — чат, где бот не админ
STAY, GHOST, MUTED, BACK, ADMIN = 7001, 7002, 7003, 7004, 7005


def message(uid, username, chat_id=CHAT, text=None, **extra):
    """Настоящий Message из aiogram: так служебные сообщения приходят из Telegram."""
    from aiogram.types import Chat, Message, User
    return Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=chat_id, type="supergroup", title="Тест"),
                   from_user=User(id=uid, is_bot=False, first_name=username.title(), username=username), text=text, **extra)


def user(uid, username, is_bot=False):
    from aiogram.types import User
    return User(id=uid, is_bot=is_bot, first_name=username.title(), username=username)


class FakeBot:
    def __init__(self):
        self.status: dict[int, SimpleNamespace] = {}   # user_id -> ответ getChatMember
        self.asked: list[tuple[int, int]] = []

    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    async def get_chat_member(self, chat_id, user_id):
        self.asked.append((chat_id, user_id))
        return self.status.get(user_id) or SimpleNamespace(status="member", tag=None, user=SimpleNamespace(id=user_id, is_bot=False))


def left(uid):
    return SimpleNamespace(status="left", user=SimpleNamespace(id=uid, is_bot=False))


async def is_left(db, uid, chat=CHAT):
    async with db.execute("SELECT is_left FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?", (chat, uid)) as cur:
        row = await cur.fetchone()
    return None if row is None else bool(row[0])


async def messages(db, uid, chat=CHAT):
    async with db.execute("SELECT user_messages_count_all_time FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?",
                          (chat, uid)) as cur:
        return int((await cur.fetchone())[0] or 0)


async def seed(db):
    from bot.chat.tracking import local_now
    day = local_now().date().isoformat()
    names = {STAY: "stay", GHOST: "xron", MUTED: "muted", BACK: "back", ADMIN: "admin"}
    for chat in (CHAT, PLAIN):
        await db.execute("INSERT INTO chat_settings (chat_id, chat_title, bot_is_admin, bot_can_moderate) VALUES (?, ?, ?, ?) "
                         "ON CONFLICT (chat_id) DO UPDATE SET bot_is_admin = EXCLUDED.bot_is_admin, bot_left_at = NULL",
                         (chat, f"Чат {chat}", chat == CHAT, chat == CHAT))
    for i, (uid, name) in enumerate(names.items()):
        await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) ON CONFLICT DO NOTHING", (uid, name))
        for chat in (CHAT, PLAIN):   # как в проде: писали давно, бот их ни разу не сверял
            await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time, is_left, last_message_at) "
                             "VALUES (?, ?, 50, FALSE, NOW() - INTERVAL '10 days') ON CONFLICT DO NOTHING", (uid, chat))
            await db.execute("INSERT INTO daily_user_stats (date, chat_id, user_id, message_count) VALUES (?, ?, ?, ?) "
                             "ON CONFLICT DO NOTHING", (day, chat, uid, 100 - i))
    await db.commit()


async def service_messages(db):
    """«X покинул группу» — не сообщение X: он уходит из участников, счётчик не растёт. «X вошёл» — возвращает."""
    from bot.chat.tracking import record_message
    from services import membership
    gone = message(GHOST, "xron", left_chat_member=user(GHOST, "xron"))
    assert await membership.observe_service(db, gone)
    await record_message(db, gone)   # так on_message вызывает учёт для любого сообщения
    assert await is_left(db, GHOST) is True, "сам вышел — ушёл"
    assert await messages(db, GHOST) == 50, "служебное сообщение не засчитано как сообщение игрока"

    kicked = message(ADMIN, "admin", left_chat_member=user(BACK, "back"))   # админ удалил BACK: отправитель — админ
    assert await membership.observe_service(db, kicked)
    await record_message(db, kicked)
    assert await is_left(db, BACK) is True and await is_left(db, ADMIN) is False
    assert await messages(db, ADMIN) == 50, "удаление участника — не сообщение админа"

    joined = message(BACK, "back", new_chat_members=[user(BACK, "back"), user(998, "otherbot", is_bot=True)])
    assert await membership.observe_service(db, joined)
    await record_message(db, joined)
    assert await is_left(db, BACK) is False and await messages(db, BACK) == 50, "вернулся — снова в чате"
    async with db.execute("SELECT rejoined_at IS NOT NULL FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = ?",
                          (CHAT, BACK)) as cur:
        assert (await cur.fetchone())[0], "возвращение отмечено"
    assert await is_left(db, 998) is None, "бота в участники не записываем"

    assert not await membership.observe_service(db, message(STAY, "stay", text="привет")), "обычное сообщение — не служебное"
    await record_message(db, message(STAY, "stay", text="привет"))
    assert await messages(db, STAY) == 51

    # Обратно, как было: дальше сценарии со «старыми призраками», которых бот не заметил
    await db.execute("UPDATE user_chat_stats SET is_left = FALSE, last_message_at = NOW() - INTERVAL '10 days' "
                     "WHERE user_tg_id IN (?, ?) AND chat_tg_id = ?", (GHOST, BACK, CHAT))
    await db.commit()


async def lists_drop_ghosts(db):
    """Топ и неактивы сами спрашивают Telegram о тех, кого давно не сверяли, и показывают список без ушедших."""
    from bot.chat import inactive, profile, top
    bot = FakeBot()
    bot.status[GHOST] = left(GHOST)
    bot.status[MUTED] = SimpleNamespace(status="restricted", is_member=False, can_send_messages=False,
                                        user=SimpleNamespace(id=MUTED, is_bot=False))   # замученный, который вышел
    text, _ = await top.build(db, "c", "d", 0, CHAT, bot)
    assert "xron" not in text and "muted" not in text, text
    assert "stay" in text and "back" in text, text
    assert await is_left(db, GHOST) is True and await is_left(db, MUTED) is True
    assert await profile.chat_place(db, CHAT, BACK, "2000-01-01", "2999-01-01") == 2, "место считается без ушедших"

    bot.asked.clear()
    await top.build(db, "c", "d", 0, CHAT, bot)
    assert bot.asked == [], f"сверенных повторно не спрашиваем: {bot.asked}"

    # Неактивы: призрак, которого раньше не сверяли, не попадает в список
    await db.execute("UPDATE user_chat_stats SET is_left = FALSE, membership_checked_at = NULL WHERE user_tg_id = ? AND chat_tg_id = ?",
                     (GHOST, CHAT))
    await db.commit()
    page = await inactive.build(db, bot, CHAT, 86400)
    shown = {m.user_id for m in page.items}
    assert GHOST not in shown and MUTED not in shown and STAY not in shown and ADMIN in shown, shown
    assert await is_left(db, GHOST) is True

    # Общий топ: кто ушёл отовсюду, того там нет; кто ещё в другом чате — есть
    for chat in (CHAT, PLAIN):
        await db.execute("UPDATE user_chat_stats SET is_left = TRUE WHERE user_tg_id = ? AND chat_tg_id = ?", (MUTED, chat))
    await db.commit()
    text, _ = await top.build(db, "g", "d", 0, CHAT, bot)
    assert "muted" not in text and "xron" in text, text


async def plain_chat(db):
    """Где бот не админ, Telegram не обязан честно отвечать про участников: по одному ответу «нет» не помечаем."""
    from services import member_tags
    bot = FakeBot()
    bot.status[GHOST] = left(GHOST)
    assert await member_tags.ensure_fresh(bot, db, PLAIN, [GHOST]) == {GHOST}
    assert await is_left(db, GHOST, PLAIN) is False
    bot.asked.clear()
    assert await member_tags.ensure_fresh(bot, db, PLAIN, [GHOST]) == set() and bot.asked == [], "второй раз в тот же день не спрашиваем"


async def backfill(db):
    """Фоновый обход сам находит ушедших: сначала дольше всех молчащих, тех, кто пишет, не трогает."""
    from services import member_tags
    member_tags._denied.clear()
    await db.execute("UPDATE user_chat_stats SET is_left = FALSE, membership_checked_at = NULL WHERE chat_tg_id = ?", (CHAT,))
    await db.execute("UPDATE user_chat_stats SET membership_checked_at = NOW() WHERE chat_tg_id = ?", (PLAIN,))
    await db.execute("UPDATE user_chat_stats SET last_message_at = NOW() - INTERVAL '40 days' WHERE chat_tg_id = ? AND user_tg_id = ?",
                     (CHAT, GHOST))
    await db.commit()
    bot = FakeBot()
    bot.status[GHOST] = left(GHOST)
    await member_tags.backfill_batch(bot, db)   # в базе бывают и чужие чаты из стартовых данных: считаем только свой
    assert sorted(u for c, u in bot.asked if c == CHAT) == [STAY, GHOST, MUTED, BACK, ADMIN], bot.asked
    assert bot.asked[0] == (CHAT, GHOST), f"дольше всех молчащий — первым: {bot.asked}"
    assert await is_left(db, GHOST) is True and await is_left(db, STAY) is False

    bot.asked.clear()
    assert await member_tags.backfill_batch(bot, db) == 0 and bot.asked == [], "сверенных до завтра не спрашиваем"

    # Через сутки молчащих переспрашиваем, а того, кто писал сегодня, — нет
    await db.execute("UPDATE user_chat_stats SET membership_checked_at = NOW() - INTERVAL '25 hours' WHERE chat_tg_id = ?", (CHAT,))
    await db.execute("UPDATE user_chat_stats SET last_message_at = NOW() WHERE chat_tg_id = ? AND user_tg_id = ?", (CHAT, STAY))
    await db.commit()
    bot.status[BACK] = left(BACK)
    assert await member_tags.backfill_batch(bot, db) == 3
    assert (CHAT, STAY) not in bot.asked and (CHAT, GHOST) not in bot.asked, bot.asked
    assert await is_left(db, BACK) is True


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
        await seed(db)
        await service_messages(db)
        await lists_drop_ghosts(db)
        await plain_chat(db)
        await backfill(db)
    print("OK: chat membership (service messages, top, inactive, place, plain chat, backfill)")


asyncio.run(main())
