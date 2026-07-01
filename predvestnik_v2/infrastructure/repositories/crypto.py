# infrastructure/repositories/crypto.py — крипто-биржа: портфель + сделки (атомарно).
import math

from core.constants import (
    CRYPTO_TRADE_FEE, CRYPTO_MIN_TRADE_MORA, CRYPTO_MAX_HOLDING, CRYPTO_AMOUNT_DECIMALS,
)
from infrastructure.repositories.wallet_log import log_wallet


async def ensure_tables(db) -> None:
    """Идемпотентно создать таблицы биржи (нужно веб-процессу до init_db бота)."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS crypto_holdings (
            user_id       BIGINT NOT NULL,
            coin_id       TEXT   NOT NULL,
            amount        FLOAT8 DEFAULT 0,
            avg_buy_price FLOAT8 DEFAULT 0,
            PRIMARY KEY (user_id, coin_id)
        )
    """)
    # Идемпотентная миграция для старых инсталляций без avg_buy_price
    await db.execute(
        "ALTER TABLE crypto_holdings ADD COLUMN IF NOT EXISTS avg_buy_price FLOAT8 DEFAULT 0"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS crypto_trades (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT NOT NULL,
            coin_id    TEXT   NOT NULL,
            action     TEXT   NOT NULL,
            amount     FLOAT8 NOT NULL,
            price      FLOAT8 NOT NULL,
            total_mora FLOAT8 NOT NULL,
            traded_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_ct_user_coin ON crypto_trades(user_id, coin_id, traded_at DESC)"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS crypto_watchlist (
            user_id BIGINT NOT NULL,
            coin_id TEXT   NOT NULL,
            PRIMARY KEY (user_id, coin_id)
        )
    """)
    await db.commit()


async def get_holdings(db, user_id: int) -> dict[str, dict]:
    """Возвращает {coin_id: {amount, avg_buy}} для позиций > 0."""
    try:
        async with db.execute(
            "SELECT coin_id, amount, COALESCE(avg_buy_price, 0) FROM crypto_holdings "
            "WHERE user_id = ? AND amount > 0",
            (user_id,),
        ) as c:
            return {r[0]: {"amount": float(r[1]), "avg_buy": float(r[2])} for r in await c.fetchall()}
    except Exception:
        # avg_buy_price ещё не мигрирован — fallback без P&L
        async with db.execute(
            "SELECT coin_id, amount FROM crypto_holdings WHERE user_id = ? AND amount > 0",
            (user_id,),
        ) as c:
            return {r[0]: {"amount": float(r[1]), "avg_buy": 0.0} for r in await c.fetchall()}


async def get_trade_history(db, user_id: int, coin_id: str | None = None, limit: int = 50) -> list[dict]:
    try:
        if coin_id:
            q = ("SELECT coin_id, action, amount, price, total_mora, traded_at "
                 "FROM crypto_trades WHERE user_id = ? AND coin_id = ? "
                 "ORDER BY traded_at DESC LIMIT ?")
            args: tuple = (user_id, coin_id, limit)
        else:
            q = ("SELECT coin_id, action, amount, price, total_mora, traded_at "
                 "FROM crypto_trades WHERE user_id = ? ORDER BY traded_at DESC LIMIT ?")
            args = (user_id, limit)
        async with db.execute(q, args) as c:
            rows = await c.fetchall()
        return [
            {"coin_id": r[0], "action": r[1], "amount": float(r[2]),
             "price": float(r[3]), "total_mora": float(r[4]), "traded_at": str(r[5])[:16]}
            for r in rows
        ]
    except Exception:
        return []


async def get_watchlist(db, user_id: int) -> set[str]:
    try:
        async with db.execute(
            "SELECT coin_id FROM crypto_watchlist WHERE user_id = ?", (user_id,)
        ) as c:
            return {r[0] for r in await c.fetchall()}
    except Exception:
        return set()


async def toggle_watchlist(db, user_id: int, coin_id: str) -> bool:
    """Добавляет/убирает монету из избранного. Возвращает True если добавлена."""
    try:
        async with db.execute(
            "SELECT 1 FROM crypto_watchlist WHERE user_id = ? AND coin_id = ?", (user_id, coin_id)
        ) as c:
            exists = await c.fetchone()
        if exists:
            await db.execute(
                "DELETE FROM crypto_watchlist WHERE user_id = ? AND coin_id = ?", (user_id, coin_id)
            )
            await db.commit()
            return False
        await db.execute(
            "INSERT INTO crypto_watchlist (user_id, coin_id) VALUES (?, ?)", (user_id, coin_id)
        )
        await db.commit()
        return True
    except Exception:
        return False


async def trade(db, user_id: int, coin_id: str, action: str,
                amount: float, unit_price: float) -> tuple[bool, str]:
    """Купить/продать монету за Мору по серверной цене unit_price. Атомарно + защита экономики."""
    if not math.isfinite(amount) or amount <= 0:
        return False, "Некорректное количество."
    if not math.isfinite(unit_price) or unit_price <= 0:
        return False, "Некорректная цена."
    amount = round(float(amount), CRYPTO_AMOUNT_DECIMALS)
    if amount <= 0:
        return False, "Слишком маленькое количество."
    gross = amount * unit_price
    if gross < CRYPTO_MIN_TRADE_MORA:
        return False, f"Минимальная сделка — {CRYPTO_MIN_TRADE_MORA:.0f} 🪙."
    amt_txt = f"{amount:g}"
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT user_balance_mora FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            bal = float(row[0]) if row else 0.0
            async with db.execute(
                "SELECT amount, COALESCE(avg_buy_price, 0) FROM crypto_holdings "
                "WHERE user_id = ? AND coin_id = ? FOR UPDATE",
                (user_id, coin_id),
            ) as c:
                hr = await c.fetchone()
            have = float(hr[0]) if hr else 0.0
            old_avg = float(hr[1]) if hr else 0.0

            if action == "buy":
                cost = round(gross * (1 + CRYPTO_TRADE_FEE), 2)
                if bal < cost:
                    return False, "Недостаточно Моры для покупки."
                if have + amount > CRYPTO_MAX_HOLDING:
                    return False, "Достигнут лимит по этой монете."
                # Средневзвешенная цена покупки
                new_avg = (have * old_avg + amount * unit_price) / (have + amount)
                await db.execute(
                    "UPDATE users SET user_balance_mora = user_balance_mora - ? WHERE user_tg_id = ?",
                    (cost, user_id),
                )
                await db.execute(
                    "INSERT INTO crypto_holdings (user_id, coin_id, amount, avg_buy_price) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (user_id, coin_id) DO UPDATE "
                    "SET amount = crypto_holdings.amount + ?, avg_buy_price = ?",
                    (user_id, coin_id, amount, new_avg, amount, new_avg),
                )
                await db.execute(
                    "INSERT INTO crypto_trades (user_id, coin_id, action, amount, price, total_mora) "
                    "VALUES (?, ?, 'buy', ?, ?, ?)",
                    (user_id, coin_id, amount, unit_price, cost),
                )
                await log_wallet(db, user_id, delta_mora=-cost, source="crypto_buy",
                                 note=f"{coin_id} ×{amt_txt}")
                return True, f"Куплено {amt_txt} {coin_id} за {cost:.0f} 🪙 (комиссия {int(CRYPTO_TRADE_FEE * 100)}%)."

            if action == "sell":
                if have + 1e-9 < amount:
                    return False, "Недостаточно монет для продажи."
                sell_amt = min(amount, have)
                payout = round(sell_amt * unit_price * (1 - CRYPTO_TRADE_FEE), 2)
                new_have = max(0.0, have - sell_amt)
                await db.execute(
                    "UPDATE crypto_holdings SET amount = ? WHERE user_id = ? AND coin_id = ?",
                    (new_have, user_id, coin_id),
                )
                await db.execute(
                    "UPDATE users SET user_balance_mora = user_balance_mora + ? WHERE user_tg_id = ?",
                    (payout, user_id),
                )
                await db.execute(
                    "INSERT INTO crypto_trades (user_id, coin_id, action, amount, price, total_mora) "
                    "VALUES (?, ?, 'sell', ?, ?, ?)",
                    (user_id, coin_id, sell_amt, unit_price, payout),
                )
                await log_wallet(db, user_id, delta_mora=payout, source="crypto_sell",
                                 note=f"{coin_id} ×{sell_amt:g}")
                return True, f"Продано {sell_amt:g} {coin_id} за {payout:.0f} 🪙 (спред {int(CRYPTO_TRADE_FEE * 100)}%)."

            return False, "Неизвестное действие."
    except Exception as e:
        return False, f"Ошибка: {e}"
