# infrastructure/repositories/crypto.py — крипто-биржа: портфель + сделки (атомарно).
import math

from core.constants import (
    CRYPTO_TRADE_FEE, CRYPTO_MIN_TRADE_MORA, CRYPTO_MAX_HOLDING, CRYPTO_AMOUNT_DECIMALS,
)
from infrastructure.repositories.wallet_log import log_wallet


async def ensure_tables(db) -> None:
    """Идемпотентно создать таблицу портфеля (нужно веб-процессу до init_db бота)."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS crypto_holdings (
            user_id BIGINT NOT NULL,
            coin_id TEXT   NOT NULL,
            amount  FLOAT8 DEFAULT 0,
            PRIMARY KEY (user_id, coin_id)
        )
    """)


async def get_holdings(db, user_id: int) -> dict[str, float]:
    async with db.execute(
        "SELECT coin_id, amount FROM crypto_holdings WHERE user_id = ? AND amount > 0",
        (user_id,),
    ) as c:
        return {r[0]: float(r[1]) for r in await c.fetchall()}


async def trade(db, user_id: int, coin_id: str, action: str,
                amount: float, unit_price: float) -> tuple[bool, str]:
    """Купить/продать монету за Мору по серверной цене unit_price. Атомарно + защита экономики.

    Защита (после аудита): отвергаем NaN/Inf/неположительное; точность количества режется;
    минимальная стоимость сделки (анти round-to-zero); потолок позиции; на ПРОДАЖЕ —
    спред CRYPTO_TRADE_FEE (биржа = сток). Остаток монет клампится ≥ 0.
    """
    # ── Валидация входа ──
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
            # Лочим строку игрока ПЕРВОЙ (и в buy, и в sell) → сделки сериализуются на юзера.
            async with db.execute(
                "SELECT user_balance_mora FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            bal = float(row[0]) if row else 0.0
            # Текущая позиция (под тем же порядком блокировок: users → holdings).
            async with db.execute(
                "SELECT amount FROM crypto_holdings WHERE user_id = ? AND coin_id = ? FOR UPDATE",
                (user_id, coin_id),
            ) as c:
                hr = await c.fetchone()
            have = float(hr[0]) if hr else 0.0

            if action == "buy":
                cost = round(gross, 2)
                if bal < cost:
                    return False, "Недостаточно Моры для покупки."
                if have + amount > CRYPTO_MAX_HOLDING:
                    return False, "Достигнут лимит по этой монете."
                await db.execute(
                    "UPDATE users SET user_balance_mora = user_balance_mora - ? WHERE user_tg_id = ?",
                    (cost, user_id),
                )
                await db.execute(
                    "INSERT INTO crypto_holdings (user_id, coin_id, amount) VALUES (?, ?, ?) "
                    "ON CONFLICT (user_id, coin_id) DO UPDATE SET amount = crypto_holdings.amount + ?",
                    (user_id, coin_id, amount, amount),
                )
                await log_wallet(db, user_id, delta_mora=-cost, source="crypto_buy",
                                 note=f"{coin_id} ×{amt_txt}")
                return True, f"Куплено {amt_txt} {coin_id} за {cost:.0f} 🪙."

            if action == "sell":
                if have + 1e-9 < amount:
                    return False, "Недостаточно монет для продажи."
                sell_amt = min(amount, have)                 # никогда не уводим в минус
                payout = round(sell_amt * unit_price * (1 - CRYPTO_TRADE_FEE), 2)  # спред
                new_have = max(0.0, have - sell_amt)          # кламп ≥ 0
                await db.execute(
                    "UPDATE crypto_holdings SET amount = ? WHERE user_id = ? AND coin_id = ?",
                    (new_have, user_id, coin_id),
                )
                await db.execute(
                    "UPDATE users SET user_balance_mora = user_balance_mora + ? WHERE user_tg_id = ?",
                    (payout, user_id),
                )
                await log_wallet(db, user_id, delta_mora=payout, source="crypto_sell",
                                 note=f"{coin_id} ×{sell_amt:g}")
                return True, f"Продано {sell_amt:g} {coin_id} за {payout:.0f} 🪙 (спред {int(CRYPTO_TRADE_FEE * 100)}%)."

            return False, "Неизвестное действие."
    except Exception as e:
        return False, f"Ошибка: {e}"
