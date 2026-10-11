"""Экономика и соцкоманды после поиска багов: переводы, зачёт достижений, раздел имущества, удаление за неактив.

Запуск: python tools/test_bot_economy_review_pg.py --dsn postgresql://... (пустая тестовая БД!)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from decimal import Decimal
from types import SimpleNamespace

ap = argparse.ArgumentParser()
ap.add_argument("--dsn", required=True)
dsn = ap.parse_args().dsn
os.environ["DATABASE_URL"] = dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ["DEVELOPER_ID"] = "1001"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A, B, C, GONE = 3101, 3102, 3103, 3104


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


class Call:
    def __init__(self, bot, transfer, uid, to, cur="mora", amount="10", msg_id=1, private=False, chat=-100):
        self.from_user = SimpleNamespace(id=uid, username=f"u{uid}", full_name=f"U{uid}")
        self.bot = bot
        self.data_cb = transfer.TransferCB(uid=uid, to=to, amount=amount, cur=cur)
        self.edited, self.alerts = [], []

        async def edit_text(text, **kw):
            self.edited.append(text)
        self.message = SimpleNamespace(chat=SimpleNamespace(id=uid if private else chat, type="private" if private else "supergroup"),
                                       message_id=msg_id, edit_text=edit_text)

    async def answer(self, text=None, show_alert=False):
        self.alerts.append(text)


async def scalar(db, sql, params=()):
    async with db.execute(sql, params) as cur:
        row = await cur.fetchone()
    return row[0] if row else None


async def run():
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema
    from bot.startup_schema import ensure_runtime_schema
    from bot.chat import achievements, transfer
    from infrastructure.repositories import divorce_v1
    from infrastructure.repositories.economy_ledger import apply_balance_change
    from services import account_deletion

    await create_pool()
    await init_db()
    await ensure_runtime_schema(get_pool())
    await ensure_chat_schema()
    pool = get_pool()
    bot = FakeBot()

    async with pool.acquire() as conn:
        db = PGAdapter(conn)
        for uid in (A, B, C, GONE):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, user_balance_mora) VALUES (?, ?, 100000)",
                             (uid, f"u{uid}"))
        await db.execute("UPDATE users SET deleted_at = NOW() WHERE user_tg_id = ?", (GONE,))

    async def bal(uid):
        async with pool.acquire() as conn:
            return Decimal(str(await scalar(PGAdapter(conn), "SELECT user_balance_mora FROM users WHERE user_tg_id = ?", (uid,))))

    # ── Перевод игроку, чей аккаунт на удалении, отклоняется ──────────────────────
    async with pool.acquire() as conn:
        db = PGAdapter(conn)
        assert await transfer._recipient_gone(db, GONE) and not await transfer._recipient_gone(db, B)
        c = Call(bot, transfer, A, GONE, msg_id=11)
        await transfer.on_transfer(c, c.data_cb, db)
        assert c.alerts and "удаляет аккаунт" in c.alerts[0] and not c.edited, (c.alerts, c.edited)
    assert await bal(A) == 100000 and await bal(GONE) == 100000

    # ── Повторное нажатие той же кнопки: деньги и уведомление — один раз ───────────
    bot.sent.clear()
    async with pool.acquire() as conn:
        db = PGAdapter(conn)
        for _ in range(2):
            c = Call(bot, transfer, A, B, amount="25", msg_id=22, private=True)
            await transfer.on_transfer(c, c.data_cb, db)
            assert "Переведено" in c.edited[0], (c.edited, c.alerts)
    assert await bal(A) == 100000 - 25 and await bal(B) == 100000 + 25
    assert [chat for chat, _ in bot.sent] == [B], bot.sent                    # «Вам перевели» пришло один раз

    # ── Встречные переводы одновременно не блокируют друг друга ───────────────────
    async def cross(uid, to, amount, msg_id):
        async with pool.acquire() as conn:
            c = Call(bot, transfer, uid, to, amount=str(amount), msg_id=msg_id)
            await transfer.on_transfer(c, c.data_cb, PGAdapter(conn))
            return c
    a0, b0 = await bal(A), await bal(B)
    done = await asyncio.wait_for(asyncio.gather(*(
        cross(A if i % 2 == 0 else B, B if i % 2 == 0 else A, 10 + i, 100 + i) for i in range(16))), timeout=30)
    assert all(c.edited and "Переведено" in c.edited[0] for c in done), [(c.edited, c.alerts) for c in done]
    sent_a = sum(10 + i for i in range(0, 16, 2))
    sent_b = sum(10 + i for i in range(1, 16, 2))
    assert await bal(A) == a0 - sent_a + sent_b and await bal(B) == b0 - sent_b + sent_a

    # ── Достижения: накрутка парой аккаунтов упирается в суточный потолок ──────────
    async with pool.acquire() as conn:
        db = PGAdapter(conn)
        for i in range(5):
            async with db.connection.transaction():
                await apply_balance_change(db, C, {"mora": -3000}, reason_code="player_transfer_out",
                                           idempotency_key=f"cap-test:{i}", source_type="chat",
                                           reference_type="player_transfer", reference_id=f"cap-test:{i}", target_id=B)
        assert await achievements.SOURCES["transfers"](db, C) == achievements.TRANSFERS_PER_DAY
        assert await achievements.SOURCES["mora_given"](db, C) == achievements.MORA_GIVEN_PER_DAY
        for _ in range(achievements.WARPS_PER_DAY + 7):
            await achievements._bump_capped(db, C, "warps_sent", achievements.WARPS_PER_DAY)
        assert await achievements.counter(db, C, "warps_sent") == achievements.WARPS_PER_DAY

    # ── Развод: имущество делится целыми числами ──────────────────────────────────
    split = divorce_v1._split_amount
    assert split(Decimal("101"), 1, 2, "mora") == {1: Decimal("51"), 2: Decimal("50")}
    assert split(Decimal("7"), 1, 2, "zarniki") == {1: Decimal("4"), 2: Decimal("3")}
    assert split(Decimal("1"), 1, 2, "dark_mora") == {1: Decimal("1"), 2: Decimal("0")}
    assert split(Decimal("10.01"), 1, 2, "diamonds") == {1: Decimal("5.01"), 2: Decimal("5.00")}

    # ── Удаление за неактив: предупреждение идёт раньше удаления, а вернувшийся игрок предупреждается заново ──
    sent = []

    async def fake_tg(method, **kw):
        sent.append((kw.get("chat_id"), kw.get("text", "")))
    account_deletion._tg = fake_tg
    warn = account_deletion.ACCOUNT_DELETE_WARN_DAYS
    X, Y, Z = 3201, 3202, 3203
    async with pool.acquire() as conn:
        db = PGAdapter(conn)
        await db.execute("INSERT INTO chat_settings (chat_id, chat_title) VALUES (-300, 'Чат') ON CONFLICT DO NOTHING")
        for uid in (X, Y, Z):
            await db.execute("INSERT INTO users (user_tg_id, user_tg_username, delete_after_days) VALUES (?, ?, 365)",
                             (uid, f"u{uid}"))
        # X: молчит дольше года, предупреждения не было. Y: предупредили давно, потом писал, снова замолчал.
        # Z: молчит дольше года, предупреждён вчера.
        for uid, days in ((X, 400), (Y, 360), (Z, 400)):
            await db.execute("INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, last_message_at) "
                             "VALUES (?, -300, NOW() - make_interval(days => ?))", (uid, days))
        await db.execute("INSERT INTO account_deletions (user_id, source, status, warned_at) "
                         "VALUES (?, 'inactivity', 'confirming', NOW() - INTERVAL '500 days')", (Y,))
        await db.execute("INSERT INTO account_deletions (user_id, source, status, warned_at) "
                         "VALUES (?, 'inactivity', 'confirming', NOW() - INTERVAL '1 day')", (Z,))

        async def alive(uid):
            return await scalar(db, "SELECT deleted_at IS NULL FROM users WHERE user_tg_id = ?", (uid,))

        await account_deletion.daily_tick(db)
        assert await alive(X) and await alive(Y) and await alive(Z), "удалили без достаточного предупреждения"
        warned = {chat for chat, _ in sent}
        assert X in warned and Y in warned and Z not in warned, sent        # X и Y предупреждены, Z уже был
        assert await scalar(db, "SELECT warned_at > NOW() - INTERVAL '1 hour' FROM account_deletions WHERE user_id = ?", (Y,))

        # Прошло больше срока предупреждения — теперь удаляем X (Z и Y ещё нет: Z предупреждён вчера, Y — только что).
        await db.execute("UPDATE account_deletions SET warned_at = NOW() - make_interval(days => ?) WHERE user_id = ?",
                         (warn + 1, X))
        sent.clear()
        await account_deletion.daily_tick(db)
        assert not await alive(X), "после срока предупреждения аккаунт должен удалиться"
        assert await alive(Y) and await alive(Z)

        # Игрок вернулся после предупреждения — удалять нельзя, даже если срок вышел.
        await db.execute("UPDATE account_deletions SET warned_at = NOW() - make_interval(days => ?) WHERE user_id = ?",
                         (warn + 1, Z))
        await db.execute("UPDATE user_chat_stats SET last_message_at = NOW() WHERE user_tg_id = ?", (Z,))
        await account_deletion.daily_tick(db)
        assert await alive(Z)


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run())
    print("OK: economy review fixes on PostgreSQL")


main()
