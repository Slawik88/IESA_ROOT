#!/usr/bin/env python3
"""Скины в чате на настоящем PostgreSQL: карточка, знак в топе, выключатель, новости о покупке и SSS.

Запуск: python tools/test_skins_chat_pg.py --dsn postgresql://...  (локальная тестовая база)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
os.environ["DATABASE_URL"] = ap.parse_args().dsn
os.environ.setdefault("BOT_TOKEN", "123456:offline-skins-chat")
os.environ.setdefault("DEVELOPER_ID", "101")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

A, B, C, D = 984101, 984102, 984103, 984104          # A: VIP в SSS, B: SSS без VIP, C: без скина, D: покупает
MAIN, OLD, ADMIN, LEFT, GONE, OFF = -984001, -984002, -984003, -984004, -984005, -984006
USERS, CHATS = (A, B, C, D), (MAIN, OLD, ADMIN, LEFT, GONE, OFF)
RUN = uuid.uuid4().hex[:8]   # ключи повтора покупок живут в журнале экономики: у каждого запуска свои


class FakeBot:
    def __init__(self, fail_for: set[int] | None = None):
        self.sent: list[tuple[int, str, object]] = []
        self.fail_for = fail_for or set()

    async def send_message(self, chat_id, text, **kw):
        if chat_id in self.fail_for:
            raise RuntimeError("Forbidden: bot was kicked from the supergroup chat")
        self.sent.append((chat_id, text, kw.get("reply_markup")))


async def cleanup(db) -> None:
    await db.execute("DELETE FROM skin_chat_news_sent WHERE news_id IN (SELECT id FROM skin_chat_news WHERE user_id = ANY(?::bigint[]))", (list(USERS),))
    await db.execute("DELETE FROM skin_chat_news WHERE user_id = ANY(?::bigint[])", (list(USERS),))
    for table, col in (("skins_v3_equipped", "user_id"), ("skins_v3_owned", "user_id"), ("skins_v3_essence_ledger", "user_id"),
                       ("skins_v3_essence_accounts", "user_id"), ("vip_subscriptions", "user_id"), ("daily_user_stats", "user_id"),
                       ("user_chat_stats", "user_tg_id")):
        await db.execute(f"DELETE FROM {table} WHERE {col} = ANY(?::bigint[])", (list(USERS),))
    await db.execute("DELETE FROM chat_links WHERE main_chat_id = ANY(?::bigint[])", (list(CHATS),))
    await db.execute("DELETE FROM chat_settings WHERE chat_id = ANY(?::bigint[])", (list(CHATS),))


async def seed(db) -> None:
    from infrastructure.repositories import skins_v3 as skins_repo
    for uid in USERS:
        await db.execute("INSERT INTO users(user_tg_id, user_tg_username, user_balance_zarniki) VALUES (?,?,?) "
                         "ON CONFLICT (user_tg_id) DO UPDATE SET user_tg_username = EXCLUDED.user_tg_username, user_balance_zarniki = EXCLUDED.user_balance_zarniki",
                         (uid, f"p{uid}", 100_000))
    for cid in CHATS:
        await db.execute("INSERT INTO chat_settings(chat_id, chat_title) VALUES (?, ?)", (cid, f"chat {cid}"))
    await db.execute("UPDATE chat_settings SET bot_left_at = NOW() WHERE chat_id = ?", (GONE,))
    await db.execute("UPDATE chat_settings SET module_cosmetics = 0 WHERE chat_id = ?", (OFF,))
    await db.execute("INSERT INTO chat_links(main_chat_id, admin_chat_id) VALUES (?, ?)", (MAIN, ADMIN))
    rows = [(D, MAIN, "NOW()", False), (D, OLD, "NOW() - INTERVAL '40 days'", False), (D, ADMIN, "NOW()", False),
            (D, LEFT, "NOW()", True), (D, GONE, "NOW()", False), (D, OFF, "NOW()", False)]
    rows += [(u, MAIN, "NOW()", False) for u in (A, B, C)]
    for uid, cid, at, left in rows:
        await db.execute(f"INSERT INTO user_chat_stats(user_tg_id, chat_tg_id, last_message_at, is_left) VALUES (?, ?, {at}, ?)", (uid, cid, left))
    from bot.chat.tracking import local_now
    for uid, n in ((A, 30), (B, 20), (C, 10)):
        await db.execute("INSERT INTO daily_user_stats(user_id, chat_id, date, message_count) VALUES (?, ?, ?, ?)",
                         (uid, MAIN, local_now().date().isoformat(), n))
    await db.execute("INSERT INTO vip_subscriptions(user_id, tier, expires_at) VALUES (?, 'vip', NOW() + INTERVAL '10 days')", (A,))
    for uid in (A, B):
        await skins_repo.grant(db, uid, "frost")
        await skins_repo.set_tier(db, uid, "frost", "SSS")
        await skins_repo.set_equipped(db, uid, "frost")


async def looks_and_card(db) -> None:
    from bot.chat import profile, top
    from bot.chat.targets import Target
    from services import skins_chat
    looks = await skins_chat.looks(db, [A, B, C], MAIN)
    assert looks[A].tier == "SSS" and looks[B].tier == "SS" and C not in looks, looks   # SSS без VIP показывается как SS
    look = await skins_chat.card_look(db, A, MAIN)
    text = await profile.card(db, MAIN, Target(A, f"p{A}", "Игрок А"), A, True, look)
    assert text.startswith("⊱⟡┄┄꧁༺ ❄ ༻꧂┄┄⟡⊰") and "┊꧁ ❄️ <b>Игрок А</b> ꧂┊" in text and "🧊<b>СООБЩЕНИЯ</b>" in text, text
    assert "┊ день <b>30</b>" in text and "꧁༺ <b>SSS</b> ༻꧂" in text and "«Мороз рисует узоры" in text and "<i>Дитя Стужи · Изморозь</i>" in text, text
    plain = await profile.card(db, MAIN, Target(C, f"p{C}", "Игрок В"), C, True, None)
    assert "👤 <b>Игрок В</b>" in plain and "💬 <b>Сообщения</b>" in plain and "❄" not in plain, plain
    assert profile.caption_len(text) <= profile.CAPTION_LIMIT
    board, _ = await top.build(db, "c", "d", 0, MAIN)
    assert f'❄️ <a href="https://t.me/p{A}">' in board and f'❄️ <a href="https://t.me/p{B}">' in board, board
    assert f'<a href="https://t.me/p{C}">' in board and f'❄️ <a href="https://t.me/p{C}">' not in board, board


async def switch(db) -> None:
    from bot.chat import cosmetics, top
    from services import skins_chat
    replies: list[str] = []

    async def reply(text, **kw):
        replies.append(text)
    ctx = lambda uid, args: SimpleNamespace(db=db, args=args, user_id=uid, reply=reply, message=SimpleNamespace(chat=SimpleNamespace(id=MAIN)))  # noqa: E731
    await cosmetics.cmd_cosmetics(ctx(C, "выкл"))
    assert "настраивает права" in replies[-1] and await skins_chat.looks(db, [A], MAIN), replies   # без права ничего не меняется
    await cosmetics.cmd_cosmetics(ctx(101, "выкл"))   # разработчик может всё
    assert "<b>выключена</b>" in replies[-1] and not await skins_chat.looks(db, [A], MAIN), replies
    board, _ = await top.build(db, "c", "d", 0, MAIN)
    assert "❄️" not in board, board
    await cosmetics.cmd_cosmetics(ctx(101, "выкл"))
    assert "уже <b>выключена</b>" in replies[-1], replies
    await cosmetics.cmd_cosmetics(ctx(C, ""))
    assert "Косметика в этом чате: <b>выключена</b>" in replies[-1], replies
    await cosmetics.cmd_cosmetics(ctx(101, "вкл"))
    assert "<b>включена</b>" in replies[-1] and await skins_chat.looks(db, [A], MAIN), replies


async def other_commands(db) -> None:
    """«бот баланс» и «бот достижения»: со скином — разделы скина, без скина — как раньше."""
    from bot.chat import achievements, profile
    from services import skins_chat
    replies: list[str] = []

    async def reply(text, **kw):
        replies.append(text)
    for uid in (A, C):
        await profile.cmd_balance(SimpleNamespace(db=db, user_id=uid, reply=reply, message=SimpleNamespace(chat=SimpleNamespace(id=MAIN))))
    assert "🌨<b>КОШЕЛЁК</b>" not in replies[0] and "<b>КОШЕЛЁК</b>" in replies[0] and "«Мороз рисует" in replies[0], replies[0]
    assert replies[1].startswith("💰 <b>Баланс</b>\n<blockquote>"), replies[1]
    styled = await achievements.card(db, A, "Ваши", await skins_chat.card_look(db, A, MAIN))
    plain = await achievements.card(db, C, "Ваши")
    assert "❄️ <b>Ваши достижения</b>" in styled and "<b>ОБЩЕНИЕ</b>" in styled and "┊ ╰ ур. " in styled, styled
    assert plain.startswith("🏆 <b>Ваши достижения</b> · уровней:") and "┊" not in plain, plain


async def age(db, user_id: int, seconds: int) -> None:
    await db.execute("UPDATE skin_chat_news SET created_at = NOW() - make_interval(secs => ?) WHERE user_id = ? AND done_at IS NULL", (seconds, user_id))


async def purchases(db) -> None:
    from infrastructure.repositories import skins_v3 as skins_repo
    from services import skins_v3
    await skins_v3.buy(db, D, "frost", idempotency_key=f"sc-buy-1-{RUN}")
    await skins_v3.buy(db, D, "frost", idempotency_key=f"sc-buy-1-{RUN}")   # повтор запроса: новость одна
    await skins_v3.buy(db, D, "sakura_storm", idempotency_key=f"sc-buy-2-{RUN}")
    await skins_repo.essence_apply(db, D, 1_000_000, reason="test", reference="t", idempotency_key=f"sc-essence-{RUN}")
    await db.execute("INSERT INTO vip_subscriptions(user_id, tier, expires_at) VALUES (?, 'vip', NOW() + INTERVAL '10 days')", (D,))
    for step in range(6):   # D → SSS
        await skins_v3.upgrade(db, D, "frost", idempotency_key=f"sc-up-{step}-{RUN}")
    async with db.execute("SELECT skin_id, kind, tier FROM skin_chat_news WHERE user_id = ? ORDER BY id", (D,)) as cur:
        news = [tuple(r) for r in await cur.fetchall()]
    assert news == [("frost", "buy", "D"), ("sakura_storm", "buy", "D"), ("frost", "sss", "SSS")], news


async def delivery(db) -> None:
    from services import broadcasts, skin_chat_news
    pool_db = broadcasts.pool_db_factory()
    bot = FakeBot()
    assert await skin_chat_news.tick(bot, pool_db) == 0 and not bot.sent   # свежие покупки ждут тишины: вдруг будет ещё
    await age(db, D, 120)
    assert await skin_chat_news.tick(bot, pool_db) == 1, bot.sent
    chat_id, text, markup = bot.sent[0]
    assert chat_id == MAIN, bot.sent   # не старый чат, не админ-чат, не вышел, не без бота, не с выключенной косметикой
    assert "🎨<b>КОЛЛЕКЦИЯ</b>" in text and "пополняет коллекцию" in text and "Изморозь</b> · новый" in text and "Лепестковый Вихрь</b>" in text and "Изморозь</b> · SSS" in text, text
    assert "startapp=looks" in markup.inline_keyboard[0][0].url
    assert await skin_chat_news.tick(bot, pool_db) == 0 and len(bot.sent) == 1   # отправленное не повторяется
    # одна новость — свой текст; две доставки одновременно — одно сообщение
    from services import skins_chat
    await skins_chat.news(db, D, "inferno", "buy", "D")
    await age(db, D, 120)
    racing = FakeBot()
    await asyncio.gather(skin_chat_news.deliver_user(racing, pool_db, D), skin_chat_news.deliver_user(racing, pool_db, D))
    assert len(racing.sent) == 1 and "┊ ╰ новый образ\n┊ <b>Инферно</b>" in racing.sent[0][1] and "редкость B" in racing.sent[0][1], racing.sent
    # старое не новость; ошибка чата записывается и не повторяется
    await skins_chat.news(db, D, "void", "sss", "SSS")
    await age(db, D, 3 * 24 * 3600)
    stale = FakeBot()
    assert await skin_chat_news.tick(stale, pool_db) == 0 and not stale.sent
    await skins_chat.news(db, D, "solar", "buy", "D")
    await age(db, D, 120)
    broken = FakeBot(fail_for={MAIN})
    assert await skin_chat_news.tick(broken, pool_db) == 0
    async with db.execute("SELECT s.status, s.error FROM skin_chat_news_sent s JOIN skin_chat_news n ON n.id = s.news_id "
                          "WHERE n.user_id = ? AND n.skin_id = 'solar'", (D,)) as cur:
        assert tuple(await cur.fetchone()) == ("failed", "chat_gone")
    async with db.execute("SELECT COUNT(*) FROM skin_chat_news WHERE user_id = ? AND done_at IS NULL", (D,)) as cur:
        assert (await cur.fetchone())[0] == 0
    single = skin_chat_news.text(D, f"p{D}", [{"skin_id": "frost", "kind": "sss"}])
    assert "👑<b>SSS</b>" in single and "<b>Изморозь</b> теперь <b>SSS</b>" in single and "«Мороз рисует" in single, single


async def main() -> None:
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema
    from bot.startup_schema import ensure_runtime_schema
    await create_pool()
    await init_db()
    await ensure_chat_schema()
    await ensure_runtime_schema(get_pool())
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await cleanup(db)
        try:
            await seed(db)
            await looks_and_card(db)
            await switch(db)
            await other_commands(db)
            await purchases(db)
            await delivery(db)
        finally:
            await cleanup(db)
    print("skins chat pg: OK")


if __name__ == "__main__":
    asyncio.run(main())
