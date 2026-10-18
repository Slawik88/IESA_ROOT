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
        self.bot_admin = False   # права бота в чате: тесты включают их там, где они нужны (чистка, санкции)

    async def me(self):
        return SimpleNamespace(id=999, username="predvestnik_bot")

    async def get_chat_administrators(self, chat_id):
        return [SimpleNamespace(status="creator", user=SimpleNamespace(id=1001))]

    async def get_chat(self, chat_id):
        return SimpleNamespace(permissions=None)

    async def get_chat_member(self, chat_id, user_id):
        if user_id == 999:   # сам бот: как в живом чате — либо админ с удалением, либо обычный участник
            return SimpleNamespace(status="administrator" if self.bot_admin else "member",
                                   can_delete_messages=self.bot_admin, can_restrict_members=self.bot_admin)
        return SimpleNamespace(status="member", can_delete_messages=False)

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text, kw))
        return SimpleNamespace(message_id=len(self.sent))

    def __getattr__(self, name):   # restrict/ban/unban_chat_member
        async def call(*a, **kw):
            self.calls.append((name, a, kw))
        return call


class FakeMessage:
    _next_id = 1000

    def __init__(self, text, uid, username, chat=-100, reply_to=None, chat_type="supergroup"):
        FakeMessage._next_id += 1
        self.message_id = FakeMessage._next_id
        self.text, self.caption, self.entities = text, None, []
        self.from_user = SimpleNamespace(id=uid, is_bot=False, username=username, full_name=username,
                                         first_name=username.title())
        self.chat = SimpleNamespace(id=uid if chat_type == "private" else chat, type=chat_type,
                                    title=None if chat_type == "private" else "Тест")
        self.reply_to_message = reply_to
        self.replies, self.deleted = [], False

    async def reply(self, text, **kw):
        self.replies.append(text)

    async def answer(self, text, **kw):
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
    out = await run(db, bot, "бот ранг, @gamma владелец", uid=1002, username="beta")
    assert "только через Telegram" in out, out
    out = await run(db, bot, "бот ранг, @gamma Владелец", uid=42, username="devuser")
    assert "владелец этого чата" in out, out                          # разработчику бота можно всё
    assert await ranks.sync_owner(db, bot, -100, force=True) == 1003   # Telegram не перебивает назначение
    assert await ranks.get_rank(db, -100, 1001) < ranks.OWNER
    out = await run(db, bot, "бот снять ранг, @gamma", uid=42, username="devuser")
    assert await ranks.sync_owner(db, bot, -100, force=True) == 1001, out
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
    bot.bot_admin = True           # для чистки боту выдали админку с правом удаления (как в живом чате)
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
    # Решение по досье принимается один раз: повторное нажатие (или второй модератор) не выдаёт второй варн.
    for _ in range(2):
        c = Call(1001)
        c.message.html_text = "Досье"
        await purge.on_verdict(c, purge.PurgeCB(act="warn", s=s[0], u=2001), bot, db)
    assert "уже принято" in (c.alerts[0] or ""), c.alerts
    async with db.execute("SELECT COUNT(*) FROM user_warnings WHERE chat_id = -100 AND user_id = 2001 AND revoked_at IS NULL") as cur:
        assert (await cur.fetchone())[0] == 1
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
    # Снимать нечего: бот говорит об этом, а не «разбанен», и журнал не пополняется.
    async def logged(action):
        async with db.execute("SELECT COUNT(*) FROM moderation_logs WHERE chat_id = -100 AND action = ?", (action,)) as cur:
            return (await cur.fetchone())[0]
    unbans, unmutes = await logged("unban"), await logged("unmute")
    out = await run(db, bot, "бот снять бан, @silent")
    assert "нет в чёрном списке" in out and "разбанен" not in out, out
    out = await run(db, bot, "бот снять мут, @talker")
    assert "нет действующего мута" in out and "снова может" not in out, out
    assert await logged("unban") == unbans and await logged("unmute") == unmutes
    # Мут тому, кого в этом чате ещё не учитывали, всё равно виден в списке санкций.
    from datetime import timedelta
    from bot.chat import moderation
    await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (2090, 'newcomer') ON CONFLICT DO NOTHING")
    await moderation.do_mute(bot, db, -100, 2090, 1001, timedelta(hours=1))
    text, _ = await sanctions.list_view(db, 1001, -100, "mute", 0)
    assert "newcomer" in text, text
    out = await run(db, bot, "бот санкции", uid=2002, username="talker")
    assert "нет права" in out, out
    await migration_flow(db, bot)
    await profile_flow(db, bot)


async def migration_flow(db, bot):
    """Группа стала супергруппой: настройки, статистика и санкции едут на новый ID, пара первых сообщений в новом чате не мешает."""
    from bot.chat import migration
    old, new = -4001, -1004001
    await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (?, 'Старая'), (?, 'Новая')", (old, new))
    for uid in (2001, 2002):
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time) VALUES (?, ?, 50)", (uid, old))
    await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, user_messages_count_all_time) VALUES (2001, ?, 1)", (new,))
    await db.execute("INSERT INTO chat_blacklist (chat_id, user_id, reason) VALUES (?, 2003, 'спам')", (old,))
    msg = SimpleNamespace(chat=SimpleNamespace(id=old, type="group"), migrate_to_chat_id=new)
    sent = len(bot.sent)
    await migration.on_migrated(msg, bot, db)
    async def count(table, col, chat):
        async with db.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", (chat,)) as cur:
            return (await cur.fetchone())[0]
    assert await count("chat_settings", "chat_id", old) == 0 and await count("chat_settings", "chat_id", new) == 1
    assert await count("user_chat_stats", "chat_tg_id", new) == 2 and await count("user_chat_stats", "chat_tg_id", old) == 0
    assert await count("chat_blacklist", "chat_id", new) == 1
    async with db.execute("SELECT chat_title FROM chat_settings WHERE chat_id = ?", (new,)) as cur:
        assert (await cur.fetchone())[0] == "Старая"                 # данные старого чата сильнее случайных строк нового
    async with db.execute("SELECT user_messages_count_all_time FROM user_chat_stats WHERE chat_tg_id = ? AND user_tg_id = 2001", (new,)) as cur:
        assert (await cur.fetchone())[0] == 50
    assert len(bot.sent) == sent + 1 and bot.sent[-1][0] == new, bot.sent[sent:]
    assert await migration.migrate_chat(db, new, new) == {}


async def profile_flow(db, bot):
    await db.execute("UPDATE users SET user_balance_mora = 1500, user_balance_diamonds = 12.5 WHERE user_tg_id = 2002")
    from infrastructure.repositories import skins_v3 as skins_v3_repo
    await skins_v3_repo.essence_apply(db, 2002, 7, reason="test", reference=None, idempotency_key="test-essence-0")
    async with db.execute("INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name, marriage_date) "
                          "VALUES (-100, 2002, 'Talker', 1001, 'Alpha', NOW()) RETURNING id") as cur:
        mid = (await cur.fetchone())[0]
    await db.execute("INSERT INTO marriage_members (user_id, marriage_id) VALUES (2002, ?), (1001, ?)", (mid, mid))
    out = await run(db, bot, "бот я", uid=2002, username="talker")
    assert "@talker" in out and "1 500" in out and "12.5" in out and "Сообщения" in out and "Кошелёк" in out, out
    assert "@\u200balpha" in out and "@alpha" not in out, out          # партнёр без пинга
    assert "ID:" not in out and "🆔" not in out, out                    # обычный игрок ID не видит
    # Новые блоки: место в чате за месяц и уровни достижений (данные кладём руками).
    from bot.chat.achievements_data import ACHIEVEMENTS
    from bot.chat.tracking import local_now
    await db.execute("INSERT INTO daily_user_stats (user_id, chat_id, date, message_count) VALUES (2002, -100, ?, 999) "
                     "ON CONFLICT (user_id, chat_id, date) DO UPDATE SET message_count = 999", (local_now().date().isoformat(),))
    await db.execute("INSERT INTO chat_achievement_levels (user_id, achievement, level) VALUES (2002, 'messages', 23) "
                     "ON CONFLICT (user_id, achievement) DO UPDATE SET level = 23")
    levels_max = sum(a.max_level for a in ACHIEVEMENTS)
    out = await run(db, bot, "бот я", uid=2002, username="talker")
    assert "место <b>#1</b>" in out and f"достижения <b>23/{levels_max}</b>" in out, out
    out = await run(db, bot, "бот кто, @talker", uid=42, username="devuser")
    assert "🆔 2002" in out and "Создатель" not in out, out
    out = await run(db, bot, "бот кто @nobody_here")
    assert "Не нашёл" in out, out
    out = await run(db, bot, "бот баланс", uid=2002, username="talker")
    assert "Мора" in out and "Зарники" in out and "Эссенция" in out and "Тёмная" not in out, out
    await presence_flow(db, bot)
    await transfer_flow(db, bot)


async def presence_flow(db, bot):
    """«В чате с …»: дата миграции колонки не должна выдавать старожила за новичка."""
    from datetime import datetime, timedelta, timezone
    from bot.chat.tracking import local_now, presence_of, record_message
    today = local_now().date()
    now = datetime.now(timezone.utc)
    migrated = (now.replace(tzinfo=None), now)                       # joined_at и membership_since = «сегодня»
    first_day = (today - timedelta(days=40)).isoformat()             # а писал уже 40 дней назад
    p = presence_of(*migrated, None, first_day)
    assert p.days == 40 and p.since == today - timedelta(days=40) and not p.rejoined, p
    p = presence_of(*migrated, now - timedelta(days=3), first_day)
    assert p.days == 3 and p.rejoined and p.first_seen == today - timedelta(days=40), p
    p = presence_of(*migrated, None, None)
    assert p.days == 0 and p.since == today, p
    assert presence_of(None, None, None, None) is None

    # В БД: строка 2002 в чате -100 заведена 100 дней назад, колонка membership_since — «сегодня».
    # joined_at у бота — наивный UTC (см. tracking), поэтому пишем время в UTC: с NOW() на кластере
    # с не-UTC часовым поясом счёт съезжает на день.
    await db.execute("UPDATE user_chat_stats SET joined_at = (NOW() AT TIME ZONE 'UTC') - INTERVAL '100 days', "
                     "membership_since = NOW(), "
                     "rejoined_at = NULL, is_left = FALSE WHERE user_tg_id = 2002 AND chat_tg_id = -100")
    out = await run(db, bot, "бот я", uid=2002, username="talker")
    assert "В чате <b>10" in out and "Вернулся" not in out, out      # 100 или 101 день, смотря на часовой пояс
    # Ушёл и вернулся (сообщением): отсчёт идёт с возвращения, первое появление помнится.
    await db.execute("UPDATE user_chat_stats SET is_left = TRUE WHERE user_tg_id = 2002 AND chat_tg_id = -100")
    await record_message(db, msg(2002, -100, "talker"))
    out = await run(db, bot, "бот я", uid=2002, username="talker")
    assert "В чате с сегодняшнего дня" in out and "Вернулся в чат" in out, out
    await record_message(db, msg(2002, -100, "talker"))              # обычное сообщение возврат не сбрасывает
    async with db.execute("SELECT rejoined_at, is_left FROM user_chat_stats WHERE user_tg_id = 2002 "
                          "AND chat_tg_id = -100") as cur:
        back, left = await cur.fetchone()
    assert back is not None and left is False, (back, left)
    await db.execute("UPDATE user_chat_stats SET joined_at = NOW() - INTERVAL '30 days', rejoined_at = NULL "
                     "WHERE user_tg_id = 2002 AND chat_tg_id = -100")


async def transfer_flow(db, bot):
    from bot.chat import transfer
    out = await run(db, bot, "бот перевод, @alpha 300", uid=2002, username="talker")
    assert "Какую валюту" in out, out

    class Call:
        def __init__(self, uid, cur, amount="300", msg_id=77, private=False):
            self.from_user = SimpleNamespace(id=uid, username=None, full_name=f"U{uid}")
            self.bot = bot
            self.data_cb = transfer.TransferCB(uid=2002, to=1001, amount=amount, cur=cur)
            self.edited, self.alerts = [], []
            async def edit_text(text, **kw):
                self.edited.append(text)
            self.message = SimpleNamespace(chat=SimpleNamespace(id=uid if private else -100, type="private" if private else "supergroup"),
                                           message_id=msg_id, edit_text=edit_text)
        async def answer(self, text=None, show_alert=False):
            self.alerts.append(text)

    async def bal(uid):
        async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id = ?", (uid,)) as cur:
            return float((await cur.fetchone())[0] or 0)

    a0, b0 = await bal(2002), await bal(1001)
    c = Call(1001, "mora")
    await transfer.on_transfer(c, c.data_cb, db)
    assert "не ваш" in c.alerts[0]                                   # чужая кнопка
    for cur in ("zarniki", "essence"):
        c = Call(2002, cur)
        await transfer.on_transfer(c, c.data_cb, db)
        assert "нельзя" in c.alerts[0], (cur, c.alerts)
    out = await run(db, bot, "бот баланс", uid=2002, username="talker")
    assert "Эссенция: <b>7</b>" in out, out                          # тот же счёт, что в Mini App
    c = Call(2002, "mora")
    await transfer.on_transfer(c, c.data_cb, db)
    assert "Переведено" in c.edited[0], (c.edited, c.alerts)
    c = Call(2002, "mora")                                            # повторное нажатие той же кнопки
    await transfer.on_transfer(c, c.data_cb, db)
    assert await bal(2002) == a0 - 300 and await bal(1001) == b0 + 300
    assert not bot.sent or bot.sent[-1][0] != 1001                      # из группы уведомление в личку не нужно
    c = Call(2002, "mora", amount="99999", msg_id=78)
    await transfer.on_transfer(c, c.data_cb, db)
    assert "Не хватает" in c.alerts[0] and await bal(2002) == a0 - 300
    # из лички получатель ничего не видит в чате: ему уходит сообщение от бота
    bot.sent.clear()
    c = Call(2002, "mora", amount="10", msg_id=90, private=True)
    await transfer.on_transfer(c, c.data_cb, db)
    assert "Переведено" in c.edited[0], (c.edited, c.alerts)
    assert bot.sent and bot.sent[-1][0] == 1001 and "Вам перевели" in bot.sent[-1][1] and "10" in bot.sent[-1][1], bot.sent
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
    await warps_flow(db, bot)


async def warps_flow(db, bot):
    from bot.chat import registry
    from bot.chat.framework import dispatch
    from bot.chat.warps_data import WARPS
    assert len(WARPS) >= 120 and sum(w.adult for w in WARPS) >= 15, len(WARPS)

    async def say(text, uid=1001, username="alpha", **kw):
        m = FakeMessage(text, uid, username, **kw)
        await dispatch(registry, m, bot, db)
        return " | ".join(m.replies)

    out = await say("бот обнять, @talker")
    assert 'tg://user?id=1001' in out and 'tg://user?id=2002' in out, out
    target = FakeMessage("привет", 2002, "talker")
    out = await say("обнять", reply_to=target)                        # без «бот», ответом
    assert 'tg://user?id=2002' in out, out
    out = await say("Обнимашки @talker крепко-крепко")                # алиас, @ник и подпись
    assert "💬" in out and "крепко-крепко" in out, out
    assert await say("обнять") == ""                                  # просто слово в разговоре
    assert await say("обнять бы кого-нибудь сегодня вечером под пледом", reply_to=target) == ""
    out = await say("бот обнять")
    assert "Формат" in out, out
    out = await say("бот обнять, @alpha")
    assert "сам(а) себя" in out, out

    # 18+: только если цель разрешила, и чат не запретил.
    out = await say("бот шлёпнуть, @talker")
    assert "не разрешил" in out, out
    assert await say("шлепнуть", reply_to=target) == ""                # без «бот» — молча
    out = await say("бот 18+ вкл", uid=2002, username="talker")
    assert "разрешены" in out, out
    out = await say("бот шлепнуть, @talker")
    assert 'tg://user?id=2002' in out, out
    await db.execute("UPDATE chat_settings SET nsfw_warps_allowed = 0 WHERE chat_id = -100")
    out = await say("бот шлёпнуть, @talker")
    assert "выключены" in out, out
    await db.execute("UPDATE chat_settings SET nsfw_warps_allowed = 1 WHERE chat_id = -100")
    out = await say("бот 18+", uid=2002, username="talker")
    assert "включены" in out, out
    out = await say("бот варпы")
    assert "обнять" in out and "шлёпнуть" not in out, out
    out = await say("бот варпы 18+")
    assert "шлёпнуть" in out and "обнять" not in out, out
    await family_flow(db, bot)


class Call:
    _next_id = 1

    def __init__(self, uid, msg_id=500):
        Call._next_id += 1
        self.id = f"callback-{Call._next_id}"
        self.from_user = SimpleNamespace(id=uid, full_name=f"U{uid}")
        self.edited, self.alerts = [], []
        async def edit_text(text, **kw):
            self.edited.append(text)
        from datetime import datetime, timezone
        self.message = SimpleNamespace(chat=SimpleNamespace(id=-100), message_id=msg_id, edit_text=edit_text,
                                       date=datetime.now(timezone.utc))

    async def answer(self, text=None, show_alert=False):
        self.alerts.append(text)


async def family_flow(db, bot):
    from bot.chat import family
    from bot.chat.tracking import record_message

    # Старые браки: у 5001 их два — остаётся самый ранний, остальные строки не трогаем.
    rows = [(5001, 5002, "2020-01-01 10:00:00"), (5001, 5003, "2021-01-01 10:00:00"),
            (5003, 5004, "2022-01-01 10:00:00")]
    ids = []
    for a, b, when in rows:
        async with db.execute("INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name, marriage_date) "
                              "VALUES (-100, ?, 'a', ?, 'b', ?) RETURNING id", (a, b, when)) as cur:
            ids.append((await cur.fetchone())[0])
    await db.execute("DELETE FROM bot_settings WHERE key = ?", (family.BACKFILL_KEY,))
    await family._backfill_registry(db)
    assert (await family.family_id_of(db, 5001)) == (ids[0], True)
    assert (await family.family_id_of(db, 5003)) == (ids[2], True)
    async with db.execute("SELECT COUNT(*) FROM marriages WHERE id = ? AND ended_at IS NULL", (ids[1],)) as cur:
        assert (await cur.fetchone())[0] == 1                           # конфликтный брак не тронут
    await family._backfill_registry(db)                                # повторно — ничего не меняет
    assert await family.wallet_ready(db)

    for uid, name in ((6001, "mom_x"), (6002, "dad_x"), (6003, "kid_x"), (6004, "kid_y")):
        await record_message(db, msg(uid, -100, name))
    await db.execute("UPDATE users SET user_balance_mora = 1000 WHERE user_tg_id = 6001")
    from infrastructure.repositories import skins_v3 as skins_v3_repo
    await skins_v3_repo.essence_apply(db, 6001, 11, reason="test", reference=None, idempotency_key="test-essence-6001")

    async def say(text, uid, username, **kw):
        from bot.chat import registry
        from bot.chat.framework import dispatch
        m = FakeMessage(text, uid, username, **kw)
        m.reply_markup = None
        async def reply(text, **kw):
            m.replies.append(text)
            m.reply_markup = kw.get("reply_markup")
        m.reply = reply
        await dispatch(registry, m, bot, db)
        return " | ".join(m.replies), m.reply_markup

    def cb_of(markup, row=0, col=0):
        return markup.inline_keyboard[row][col].callback_data

    out, kb = await say("бот брак, @dad_x", 6001, "mom_x")
    assert "предложение" in out, out
    yes = family.ProposalCB.unpack(cb_of(kb))
    c = Call(6001); await family.on_proposal(c, yes, db)
    assert "не вам" in c.alerts[0]
    c = Call(6002); await family.on_proposal(c, yes, db)
    assert "семья" in c.edited[0], (c.edited, c.alerts)
    c = Call(6002); await family.on_proposal(c, yes, db)              # повторное нажатие
    assert "не действует" in c.alerts[0]
    out, _ = await say("бот брак, @kid_x", 6001, "mom_x")
    assert "уже" in out, out

    out, kb = await say("бот усыновить, @kid_x", 6002, "dad_x")
    adopt = family.AdoptCB.unpack(cb_of(kb))
    from datetime import timedelta
    c = Call(6003); c.message.date -= timedelta(hours=30); await family.on_adopt(c, adopt, db)
    assert "больше" in (c.alerts[0] or "") and not c.edited, (c.edited, c.alerts)   # приглашение живёт сутки
    c = Call(6002); await family.on_adopt(c, family.AdoptCB(**{**adopt.model_dump(), "act": "y"}), db)
    assert "Согласиться должен" in (c.alerts[0] or ""), c.alerts                    # за ребёнка соглашаться нельзя
    c = Call(6003); await family.on_adopt(c, adopt, db)
    assert "в семье" in c.edited[0], (c.edited, c.alerts)
    out, _ = await say("бот брак, @mom_x", 6003, "kid_x")
    assert "уже в браке" in out, out                                   # ребёнок может жениться, но не на занятом
    out, _ = await say("бот семья роль, @kid_x дочь", 6001, "mom_x")
    assert "дочь" in out, out
    out, _ = await say("бот семья роль, жена", 6001, "mom_x")
    assert "жена" in out, out
    out, _ = await say("бот семья роль, @mom_x муж", 6003, "kid_x")
    assert "только родители" in out, out
    out, _ = await say("бот семья", 6003, "kid_x")
    assert "mom_x" in out and "жена" in out and "дочь" in out and "1/6" in out, out
    out, _ = await say("бот я", 6003, "kid_x")
    assert "👪 В семье" in out and "дочь" in out, out

    out, kb = await say("бот семья положить, 100", 6001, "mom_x")
    w = family.WalletCB.unpack(cb_of(kb))
    c = Call(6001); await family.on_wallet(c, w, db)
    assert "Положено" in c.edited[0], (c.edited, c.alerts)
    c = Call(6001); await family.on_wallet(c, w, db)                  # повтор — без второго списания
    async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id = 6001") as cur:
        assert float((await cur.fetchone())[0]) == 900
    out, kb = await say("бот семья положить, 11", 6001, "mom_x")
    w = family.WalletCB.unpack(cb_of(kb))
    c = Call(6001); await family.on_wallet(c, w.model_copy(update={"cur": "essence"}), db)
    assert "Эссенция" in c.edited[0], (c.edited, c.alerts)
    out, kb = await say("бот семья положить, 1.5", 6001, "mom_x")
    w = family.WalletCB.unpack(cb_of(kb)).model_copy(update={"cur": "essence"})
    c = Call(6001); await family.on_wallet(c, w, db)
    assert "целым" in c.alerts[0], (c.edited, c.alerts)
    out, _ = await say("бот семья", 6002, "dad_x")
    assert "Эссенция: <b>11</b>" in out, out
    out, _ = await say("бот семья положить, 100", 6003, "kid_x")
    assert "родители" in out, out

    out, kb = await say("бот развод", 6002, "dad_x")
    assert "бот развод " in out and "15 минут" in out, out
    out, _ = await say("бот развод неправильная фраза 1234", 6002, "dad_x")
    assert "не совпала" in out, out
    async with db.execute("SELECT id FROM divorce_intents WHERE actor_id = 6002 AND status = 'pending'") as cur:
        intent = (await cur.fetchone())[0]
    out, _ = await say("бот развод " + family.divorce_phrase(intent).upper(), 6002, "dad_x")
    assert "развелись" in out, out
    assert await family.family_id_of(db, 6001) is None and await family.family_id_of(db, 6003) is None
    async with db.execute("SELECT user_tg_id, user_balance_mora FROM users WHERE user_tg_id IN (6001, 6002) "
                          "ORDER BY user_tg_id") as cur:
        assert [float(r[1]) for r in await cur.fetchall()] == [950, 50]
    assert [await skins_v3_repo.essence_balance(db, u) for u in (6001, 6002)] == [6, 5]
    out, _ = await say("бот брак, @kid_y", 6003, "kid_x")             # ребёнок свободен после развода
    assert "предложение" in out, out
    print("OK: family")
    await generations_flow(db, bot, say, cb_of)
    await games_flow(db, bot)


async def generations_flow(db, bot, say, cb_of):
    """Семьи в несколько поколений: дед+бабушка -> сын+невестка -> внук; запрет браков в роду; развод в цепочке."""
    from bot.chat import family
    from bot.chat.tracking import record_message
    people = {7001: "grandpa", 7002: "grandma", 7003: "son_x", 7004: "bride_x", 7005: "grandson", 7006: "daughter", 7007: "stranger"}
    for uid, name in people.items():
        await record_message(db, msg(uid, -100, name))

    async def marry(a, b):
        out, kb = await say(f"бот брак, @{people[b]}", a, people[a])
        assert kb is not None, out
        c = Call(b); await family.on_proposal(c, family.ProposalCB.unpack(cb_of(kb)), db)
        assert c.edited and "семья" in c.edited[0], (c.edited, c.alerts)

    async def adopt(parent, child):
        out, kb = await say(f"бот усыновить, @{people[child]}", parent, people[parent])
        assert kb is not None, out
        c = Call(child); await family.on_adopt(c, family.AdoptCB.unpack(cb_of(kb)), db)
        assert c.edited, c.alerts

    await marry(7001, 7002)
    await adopt(7001, 7003)
    await adopt(7002, 7006)
    out, _ = await say("бот брак, @daughter", 7003, "son_x")
    assert "одного рода" in out, out                                  # брат и сестра
    await marry(7003, 7004)                                           # сын женится, оставаясь сыном
    assert await family.parent_family_id(db, 7003) == await family.spouse_family_id(db, 7001)
    await adopt(7003, 7005)
    out, _ = await say("бот брак, @grandpa", 7005, "grandson")
    assert "в браке" in out, out
    out, _ = await say("бот брак, @grandma", 7006, "daughter")
    assert "в браке" in out, out
    out, _ = await say("бот усыновить, @grandson", 7001, "grandpa")
    assert "уже есть родители" in out, out
    out, _ = await say("бот усыновить, @grandpa", 7003, "son_x")
    assert "родственник" in out, out                                  # цикл в роду
    out, _ = await say("бот усыновить, @son_x", 7004, "bride_x")
    assert "уже есть родители" in out, out
    out, _ = await say("бот семья", 7003, "son_x")
    assert "bride_x" in out and "grandson" in out and "grandpa" not in out, out   # своя семья важнее родительской
    out, _ = await say("бот семья роль, сын", 7003, "son_x")
    assert "В родительской семье" in out, out
    out, _ = await say("бот древо", 7005, "grandson")
    assert "Бабушки и дедушки" in out and "grandpa" in out and "Родители" in out and "son_x" in out, out
    out, _ = await say("бот родословная, @grandpa", 7006, "daughter")
    assert "Потомки</b> · 3" in out and "grandson" in out and "bride_x" in out, out
    out, _ = await say("бот древо", 7007, "stranger")
    assert "нет родни" in out, out

    # Сын уходит из родительской семьи: его брак и внук остаются с ним.
    out, _ = await say("бот семья выйти", 7003, "son_x")
    assert "Ваш брак и ваши дети остаются" in out, out
    assert await family.parent_family_id(db, 7003) is None and await family.spouse_family_id(db, 7003)
    assert await family.parent_family_id(db, 7005) == await family.spouse_family_id(db, 7003)
    await adopt(7001, 7003)                                           # и может вернуться
    # Развод деда и бабушки: дети выходят из их семьи, брак сына и внук не трогаются.
    out, _ = await say("бот развод", 7001, "grandpa")
    assert "браки и внуки остаются" in out, out
    async with db.execute("SELECT id FROM divorce_intents WHERE actor_id = 7001 AND status = 'pending'") as cur:
        intent = (await cur.fetchone())[0]
    out, _ = await say("бот развод " + family.divorce_phrase(intent), 7001, "grandpa")
    assert "развелись" in out, out
    assert await family.parent_family_id(db, 7003) is None and await family.parent_family_id(db, 7006) is None
    son_family = await family.spouse_family_id(db, 7003)
    assert son_family and await family.parent_family_id(db, 7005) == son_family
    out, _ = await say("бот древо", 7005, "grandson")
    assert "grandpa" not in out and "son_x" in out and "bride_x" in out, out
    out, _ = await say("бот семья выйти", 7006, "daughter")
    assert "не в семье" in out, out
    out, _ = await say("бот выйти из семьи", 7004, "bride_x")
    assert "только через развод" in out, out
    print("OK: family generations")


async def games_flow(db, bot):
    from bot.chat import mafia
    await db.execute("INSERT INTO system_flags (key, enabled) VALUES ('game_mafia_v1', 1) "
                     "ON CONFLICT (key) DO UPDATE SET enabled = 1")
    m = FakeMessage("бот игры", 1001, "alpha")
    from bot.chat import registry
    from bot.chat.framework import dispatch
    await dispatch(registry, m, bot, db)
    assert "Игры Предвестника" in m.replies[0], m.replies
    bot.bot_admin = False          # мафия проверяет права бота: без админки ждём предупреждение
    m = FakeMessage("бот мафия", 1001, "alpha")
    m.message_thread_id = None
    await dispatch(registry, m, bot, db)
    assert "права администратора" in m.replies[0], m.replies              # у бота нет прав на удаление
    m = FakeMessage("обычное сообщение", 1001, "alpha")
    m.message_thread_id = None
    assert not await mafia.gate_message(db, bot, m) and not m.deleted     # партии нет — писать можно
    print("OK: games")
    await private_flow(db, bot)
    await membership_flow(db, bot)
    await achievements_flow(db, bot)


async def private_flow(db, bot):
    """Личка с ботом и группа: что работает где, слово «бот» в личке, справка, молчание на чужие фразы."""
    from bot.chat import registry
    from bot.chat.framework import dispatch

    async def dm(text, uid=1001, **kw):
        m = FakeMessage(text, uid, "alpha", chat_type="private", **kw)
        handled = await dispatch(registry, m, bot, db)
        return handled, " | ".join(m.replies)

    # группа: каждая команда с private=False в личке отвечает «только в группе», когда написано «бот …»
    for name in ("бан", "жалоба", "обнять", "брак", "усыновить", "чистка", "ранги", "привязать админ чат"):
        handled, out = await dm(f"бот {name} @beta")
        assert handled and out.startswith("Эта команда работает только в группе."), (name, out)
    # те же слова без «бот» в личке не команды: молчим (иначе «чай» или «ждать» в разговоре получали бы отписку)
    for text in ("чай", "обнять @beta", "ждать", "бан"):
        assert await dm(text) == (False, ""), text
    # личные команды: слово «бот» не нужно, но только для точного названия
    for text, expect in (("помощь", "личка с ботом"), ("баланс", "Баланс"), ("топ", "Топ"), ("я", "<b>"),
                         ("бот баланс", "Баланс")):
        handled, out = await dm(text)
        assert handled and expect in out, (text, out)
    assert await dm("я устал сегодня") == (False, "")                   # фраза, а не команда
    assert await dm("баланс покажи") == (False, "")
    # справка в личке не показывает группового: модерации, чистки, настроек чата
    handled, out = await dm("помощь")
    kb = FakeMessage("x", 1, "x")   # клавиатуру читаем через реестр
    from bot.chat import help as help_mod
    sections = set(help_mod._by_section(True))
    assert "moderation" not in sections and "purge" not in sections and "settings" not in sections, sections
    assert {"moderation", "purge"} <= set(help_mod._by_section(False))
    assert all(c.private for cs in help_mod._by_section(True).values() for c in cs)
    handled, out = await dm("бот помощь бан")
    assert "только в группе" in out, out
    out = await run(db, bot, "бот помощь бан")
    assert "только в группе" not in out, out
    # в группе всё как раньше
    assert "Эта команда работает только в группе." not in await run(db, bot, "бот обнять @beta")
    print("OK: private chat vs group")


async def membership_flow(db, bot):
    """my_chat_member: бота добавили, повысили, понизили, удалили; игрок заблокировал бота и вернулся."""
    from bot.chat import members, registry
    from bot.chat.tracking import record_message

    def event(chat_id, chat_type, status, **rights):
        return SimpleNamespace(chat=SimpleNamespace(id=chat_id, type=chat_type, title="Новый чат" if chat_id < 0 else None),
                               new_chat_member=SimpleNamespace(status=status, **rights),
                               from_user=SimpleNamespace(id=abs(chat_id)))

    async def row(chat_id):
        async with db.execute("SELECT bot_left_at IS NOT NULL, bot_is_admin, bot_can_moderate, chat_title FROM chat_settings "
                              "WHERE chat_id = ?", (chat_id,)) as cur:
            return await cur.fetchone()

    await members.on_bot_membership(event(-777, "supergroup", "member"), bot, db)
    assert tuple(await row(-777)) == (False, False, False, "Новый чат")        # добавили без прав
    await members.on_bot_membership(event(-777, "supergroup", "administrator", can_delete_messages=True, can_restrict_members=False), bot, db)
    assert tuple(await row(-777))[1:3] == (True, False)                        # админ, но без права блокировать
    await members.on_bot_membership(event(-777, "supergroup", "administrator", can_delete_messages=True, can_restrict_members=True), bot, db)
    assert tuple(await row(-777))[1:3] == (True, True)
    await members.on_bot_membership(event(-777, "supergroup", "kicked"), bot, db)
    assert tuple(await row(-777))[:3] == (True, False, False)                  # удалили
    await members.on_bot_membership(event(-778, "supergroup", "left"), bot, db)  # из чата, о котором бот ещё не знал
    assert (await row(-778))[0] is True
    await record_message(db, msg(1001, -777, "alpha", "Новый чат"))             # пишут в чат: бот в нём
    assert (await row(-777))[0] is False
    await members.on_bot_membership(event(-777, "channel", "kicked"), bot, db)  # каналы не трогаем
    assert (await row(-777))[0] is False
    # личка: заблокировал бота и вернулся
    async def blocked(uid):
        async with db.execute("SELECT dm_blocked_at IS NOT NULL FROM users WHERE user_tg_id = ?", (uid,)) as cur:
            return (await cur.fetchone())[0]
    await members.on_bot_membership(event(1002, "private", "kicked"), bot, db)
    assert await blocked(1002) is True
    await members.on_bot_membership(event(1002, "private", "member"), bot, db)
    assert await blocked(1002) is False
    await members.on_bot_membership(event(1002, "private", "kicked"), bot, db)
    m = FakeMessage("привет", 1002, "beta", chat_type="private")                # написал боту — значит, не блокировал
    from bot.chat import on_message
    await on_message(m, bot, db)
    assert await blocked(1002) is False
    print("OK: bot membership")


async def achievements_flow(db, bot):
    from bot.chat import achievements as ach
    from bot.chat.tracking import record_message
    from bot.chat.achievements_data import ACHIEVEMENTS, MAX_LEVELS, MIN_LEVELS
    for a in ACHIEVEMENTS:                                              # 20–80 уровней, пороги растут
        assert MIN_LEVELS <= a.max_level <= MAX_LEVELS, (a.id, a.max_level)
        assert list(a.thresholds) == sorted(set(a.thresholds)) and a.thresholds[0] > 0, a.id
    assert len({a.id for a in ACHIEVEMENTS}) == len(ACHIEVEMENTS) == len(ach.SOURCES)
    assert ach.find("Болтун").id == "messages" and ach.find("сапер").id == "minesweeper_wins"

    async def say(text, uid=7001, username="achiever", **kw):
        from bot.chat import registry
        from bot.chat.framework import dispatch
        m = FakeMessage(text, uid, username, **kw)
        await dispatch(registry, m, bot, db)
        return " | ".join(m.replies)

    await record_message(db, msg(7001, -100, "achiever"))
    await db.execute("UPDATE user_chat_stats SET user_messages_count_all_time = 99 WHERE user_tg_id = 7001")
    assert await ach.evaluate(db, 7001) == []                           # первый подсчёт — тихий
    await db.execute("UPDATE user_chat_stats SET user_messages_count_all_time = 150 WHERE user_tg_id = 7001")
    ach._last_full.clear(); ach._last_chat.clear()
    m = FakeMessage("ещё одно", 7001, "achiever")
    await ach.after_message(db, m)
    assert len(m.replies) == 1 and "Болтун — ур. 3/49" in m.replies[0], m.replies
    assert "@\u200bachiever" in m.replies[0], m.replies               # без пинга
    await ach.after_message(db, m)                                      # чаще раза в минуту — не считаем
    assert len(m.replies) == 1, m.replies
    assert await ach.evaluate(db, 7001) == []                           # уровень уже объявлен

    await db.execute("UPDATE user_chat_stats SET user_messages_count_all_time = 50 WHERE user_tg_id = 7001")
    out = await say("бот достижения")
    assert "Ваши достижения" in out and "Болтун</b> — ур. 3/49" in out, out   # уровень не падает
    out = await say("бот достижение болтун")
    assert "Следующие пороги: 200 → 250" in out and "50</b> сообщений" in out, out
    out = await say("бот достижение ерунда")
    assert "Нет такого достижения" in out, out

    await ach.evaluate(db, 7001)
    await db.execute("INSERT INTO chat_achievement_counters (user_id, counter, value) VALUES (7001, 'warps_sent', 9)")
    out = await say("бот обнять, @talker")
    assert "Заводила — ур. 1/" in out, out                             # 10-й варп
    out = await say("бот достижения @achiever", uid=2002, username="talker")
    assert "@\u200bachiever достижения" in out and "Заводила</b> — ур. 1/" in out, out

    async with db.execute(
        "INSERT INTO mafia_v1_matches (chat_id, initiator_id, ruleset_version, max_players, vote_mode, phase, "
        "winner, started_at, finished_at) VALUES (-100, 7001, 't', 4, 'open', 'finished', 'town', NOW(), NOW()) "
        "RETURNING id") as cur:
        match = (await cur.fetchone())[0]
    await db.execute("INSERT INTO mafia_v1_players (match_id, user_id, join_order, display_name, role) "
                     "VALUES (?, 7001, 1, 'A', 'citizen'), (?, 7002, 2, 'B', 'mafia')", (match, match))
    ups = {u.achievement.id: u.level for u in await ach.evaluate(db, 7001, {"games"})}
    assert ups == {"mafia_games": 1, "mafia_wins": 1}, ups
    ups = {u.achievement.id: u.level for u in await ach.evaluate(db, 7002, {"games"})}
    assert ups == {}, ups                                               # 7002 — первый подсчёт
    assert await ach.value_of(db, 7002, ach.BY_ID["mafia_wins"]) == 0

    # Эссенция за вехи: 10-й уровень — 10, 20-й — 20; первый подсчёт платит молча; повтор не платит.
    from bot.chat.achievements_data import milestone_essence
    from infrastructure.repositories import skins_v3 as skins_v3_repo
    assert milestone_essence(0, 9) == [] and milestone_essence(9, 21) == [10, 20] and milestone_essence(10, 19) == []
    await record_message(db, msg(7003, -100, "veteran"))
    await db.execute("UPDATE user_chat_stats SET user_messages_count_all_time = 4000 WHERE user_tg_id = 7003")
    assert await ach.evaluate(db, 7003, {"chat"}) == []                 # ур. 19 из истории — без объявления
    assert await skins_v3_repo.essence_balance(db, 7003) == 10
    await db.execute("UPDATE user_chat_stats SET user_messages_count_all_time = 70000 WHERE user_tg_id = 7003")
    ups = await ach.evaluate(db, 7003, {"chat"})
    assert [(u.achievement.id, u.level, u.essence) for u in ups] == [("messages", 34, 50)], ups
    assert "+50 🔮" in ach.announcement("x", ups)
    await db.execute("UPDATE chat_achievement_levels SET level = 5 WHERE user_id = 7003 AND achievement = 'messages'")
    ups = await ach.evaluate(db, 7003, {"chat"})                        # уровень снова поднят — вехи уже оплачены
    assert [u.essence for u in ups] == [0], ups
    assert await skins_v3_repo.essence_balance(db, 7003) == 60
    out = await say("бот достижение болтун", uid=7003, username="veteran")
    assert "на 40-м уровне — 40 🔮" in out, out

    # Вкладка «Достижения» в Mini App: все достижения чата, только чтение — ни уровней, ни эссенции.
    await db.execute("UPDATE user_chat_stats SET user_messages_count_all_time = 90000 WHERE user_tg_id = 7003")
    view = await ach.overview(db, 7003)
    assert [i["id"] for i in view["achievements"]] == [a.id for a in ACHIEVEMENTS]
    msgs = next(i for i in view["achievements"] if i["id"] == "messages")
    assert msgs["value"] == 90000 and msgs["level"] == 36 and msgs["next_threshold"] == 100000, msgs
    assert msgs["prev_threshold"] == 90000 and msgs["next_reward"] == {"level": 40, "essence": 40}, msgs
    assert view["summary"]["count"] == len(ACHIEVEMENTS) and view["summary"]["total_levels"] >= 36, view["summary"]
    assert (await ach.stored_levels(db, 7003))["messages"] == 34                # просмотр ничего не записал
    assert await skins_v3_repo.essence_balance(db, 7003) == 60
    empty = await ach.overview(db, 7999)
    assert all(i["level"] == 0 and i["prev_threshold"] == 0 for i in empty["achievements"]), empty
    assert await ach.stored_levels(db, 7999) == {}
    print("OK: achievements")
    await vip_flow(db, bot)


async def vip_flow(db, bot):
    from bot.chat import vip
    from infrastructure.repositories import vip_v2 as vip_v2_repo
    await vip_v2_repo.ensure_tables(db)

    async def say(text, uid=7001, username="achiever"):
        from bot.chat import registry
        from bot.chat.framework import dispatch
        m = FakeMessage(text, uid, username)
        kbs = []
        async def reply(text, **kw):
            m.replies.append(text); kbs.append(kw.get("reply_markup"))
        m.reply = reply
        await dispatch(registry, m, bot, db)
        return " | ".join(m.replies), kbs[0] if kbs else None

    await db.execute("UPDATE users SET user_balance_zarniki = 1000 WHERE user_tg_id = 7001")
    out, kb = await say("бот вип")
    assert "VIP не активен" in out and "140 ✨" in kb.inline_keyboard[0][0].text, out
    pick = vip.VipCB.unpack(kb.inline_keyboard[0][0].callback_data)
    c = Call(7002); await vip.on_vip(c, pick, db)
    assert "не ваша" in c.alerts[0]
    c = Call(7001, msg_id=900); await vip.on_vip(c, pick, db)
    assert "за <b>140</b>" in c.edited[0], c.edited
    confirm = pick.model_copy(update={"ok": True})
    c = Call(7001, msg_id=900); await vip.on_vip(c, confirm, db)
    assert "VIP продлён на 7 дней" in c.edited[0], (c.edited, c.alerts)
    c = Call(7001, msg_id=900); await vip.on_vip(c, confirm, db)        # повторное нажатие — без второго списания
    async with db.execute("SELECT user_balance_zarniki FROM users WHERE user_tg_id = 7001") as cur:
        assert float((await cur.fetchone())[0]) == 860
    big = vip.VipCB(uid=7001, days=365, ok=True)
    c = Call(7001, msg_id=901); await vip.on_vip(c, big, db)
    assert "Не хватает Зарников" in c.alerts[0], c.alerts
    out, _ = await say("бот вип")
    assert "VIP до" in out and ("осталось 7 дней" in out or "осталось 8 дней" in out), out
    out, _ = await say("бот я")
    assert "👑 VIP" in out, out
    out, _ = await say("бот вип @achiever", uid=2002, username="talker")
    assert "@\u200bachiever: 👑 VIP до" in out, out
    print("OK: vip")
    await targets_flow(db, bot)


async def targets_flow(db, bot):
    """Кого касается команда: упоминания с эмодзи, темы форума, посты из канала, старые ники, неизвестный @ник."""
    from bot.chat.targets import NOT_FOUND, resolve_target
    from bot.chat.tracking import record_message

    # Смещения упоминаний Telegram считает в UTF-16: эмодзи в имени раньше сдвигали срез, и «1ч» терялся из срока.
    m = FakeMessage("бот бан 🔥Вася🔥 1ч спам", 1001, "alpha")
    m.entities = [SimpleNamespace(type="text_mention", offset=8, length=8,
                                  user=SimpleNamespace(id=4010, username=None, full_name="🔥Вася🔥"))]
    target, rest = await resolve_target(db, m, "🔥Вася🔥 1ч спам")
    assert target.user_id == 4010 and rest == "1ч спам", (target, rest)

    # Ответ на служебное сообщение темы форума или на автопересылку из канала — не цель команды.
    author = SimpleNamespace(id=4020, is_bot=False, username="topicmaker", full_name="Topic Maker")
    for extra in ({"forum_topic_created": SimpleNamespace(name="Тема")}, {"is_automatic_forward": True}):
        m = FakeMessage("бот мут 2ч", 1001, "alpha", reply_to=SimpleNamespace(from_user=author, **extra))
        assert (await resolve_target(db, m, "2ч"))[0] is None, extra
    m = FakeMessage("бот мут 2ч", 1001, "alpha", reply_to=SimpleNamespace(
        from_user=SimpleNamespace(id=777000, is_bot=False, username="Telegram", full_name="Telegram")))
    assert (await resolve_target(db, m, "2ч"))[0] is None
    m = FakeMessage("бот мут 2ч", 1001, "alpha", reply_to=SimpleNamespace(from_user=author))
    assert (await resolve_target(db, m, "2ч"))[0].user_id == 4020

    # Ник один на весь Telegram: после смены владельца старый теряет его, а при споре берётся тот, кто писал позже.
    await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (4001, 'cool_one'), (4002, 'cool_one')")
    await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, last_message_at) "
                     "VALUES (4001, -100, NOW() - INTERVAL '30 days'), (4002, -100, NOW())")
    target, _ = await resolve_target(db, FakeMessage("x", 1001, "alpha"), "@cool_one спам")
    assert target.user_id == 4002, target
    await record_message(db, msg(4003, -100, "cool_one"))
    async with db.execute("SELECT user_tg_id FROM users WHERE LOWER(user_tg_username) = 'cool_one'") as cur:
        assert [r[0] for r in await cur.fetchall()] == [4003]

    # Неизвестный @ник не превращается в «покажи мне самого себя».
    for text in ("бот стрик @nosuchperson", "бот варны @nosuchperson", "бот ранг @nosuchperson", "бот вип @nosuchperson",
                 "бот семья @nosuchperson", "бот достижения @nosuchperson"):
        assert NOT_FOUND in await run(db, bot, text), text
    # Имя без @ника попадает в разметку ответа: ломающие символы экранируются.
    from bot.chat import registry
    from bot.chat.framework import dispatch
    m = FakeMessage("бот стрик Tom", 1001, "alpha")
    m.entities = [SimpleNamespace(type="text_mention", offset=9, length=3,
                                  user=SimpleNamespace(id=4030, username=None, full_name="Tom <3 & <b>x"))]
    assert await dispatch(registry, m, bot, db)
    assert "Tom &lt;3 &amp; &lt;b&gt;x стрик" in m.replies[0], m.replies
    print("OK: targets")
    await rank_guard_flow(db, bot)


async def rank_guard_flow(db, bot):
    """Снятие санкций и кнопки под сообщениями подчиняются рангам так же, как сами санкции."""
    from bot.chat import moderation, ranks
    chat = -300
    await ranks.sync_owner(db, bot, chat, force=True)   # владелец 1001
    for uid, name, rank in ((3101, "mod4", 4), (3102, "adm7", 7), (3103, "plain", 0)):
        await db.execute("INSERT INTO users (user_tg_id, user_tg_username) VALUES (?, ?) ON CONFLICT DO NOTHING", (uid, name))
        await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (uid, chat))
        await ranks.store_rank(db, chat, uid, rank)
    await moderation.do_warn(db, chat, 3102, 1001, None, "x")
    await moderation.do_warn(db, chat, 3103, 1001, None, "x")
    await moderation.do_warn(db, chat, 3101, 1001, None, "x")
    out = await run(db, bot, "бот снять варны @adm7", uid=3101, username="mod4", chat=chat)
    assert "не ниже" in out and len(await moderation.active_warns(db, chat, 3102)) == 1, out
    out = await run(db, bot, "бот снять варн @mod4", uid=3101, username="mod4", chat=chat)
    assert "К себе" in out and len(await moderation.active_warns(db, chat, 3101)) == 1, out
    out = await run(db, bot, "бот снять мут @adm7", uid=3101, username="mod4", chat=chat)
    assert "не ниже" in out, out
    out = await run(db, bot, "бот снять варны @plain", uid=3101, username="mod4", chat=chat)
    assert "снято варнов: 1" in out, out
    out = await run(db, bot, "бот снять варны @adm7", uid=1001, username="alpha", chat=chat)   # владелец может всё
    assert "снято варнов: 1" in out, out

    # Кнопка «Простить» под уведомлением о лимите: нажать её на того, кто не ниже рангом, нельзя.
    await moderation.do_warn(db, chat, 3102, 1001, None, "x")
    await ranks.set_right(db, chat, "ban", 4, 1001)
    for act, expect in (("forgive", "не ниже"), ("ban", "не ниже")):
        c = Call(3101)
        c.message.html_text = "Лимит"
        await moderation.on_warn_limit(c, moderation.WarnLimitCB(act=act, chat=chat, user=3102), bot, db)
        assert expect in (c.alerts[0] or ""), (act, c.alerts)
    assert len(await moderation.active_warns(db, chat, 3102)) == 1
    c = Call(3101)
    c.message.html_text = "Лимит"
    await moderation.on_warn_limit(c, moderation.WarnLimitCB(act="forgive", chat=chat, user=3103), bot, db)
    assert c.alerts[-1] == "Готово", c.alerts

    # Админ-чат нельзя назначить из чата, где у вас нет права: служебные сообщения ушли бы в чужой чат.
    from bot.chat.admin_chat import admin_chat_of
    token = (await run(db, bot, "бот привязать админ чат", chat=chat)).split("<code>бот админ чат ")[1].split("</code>")[0]

    class Foreign(FakeBot):
        async def get_chat_administrators(self, chat_id):
            return [SimpleNamespace(status="creator", user=SimpleNamespace(id=9999))]
    out = await run(db, Foreign(), f"бот админ чат {token}", chat=-877)
    assert "нет права назначать" in out and await admin_chat_of(db, chat) is None, out
    out = await run(db, bot, f"бот админ чат {token}", chat=-878)
    assert "админ-чатом" in out and await admin_chat_of(db, chat) == -878, out
    # Чат, уже служащий другому, отбирать нельзя без прав и на том чате.
    token2 = (await run(db, bot, "бот привязать админ чат", chat=-301)).split("<code>бот админ чат ")[1].split("</code>")[0]
    out = await run(db, bot, f"бот админ чат {token2}", chat=-878, uid=3102, username="adm7")
    assert "нет права" in out and await admin_chat_of(db, chat) == -878, out


asyncio.run(main())
