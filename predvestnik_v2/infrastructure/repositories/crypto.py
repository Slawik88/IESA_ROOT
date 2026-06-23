# infrastructure/repositories/crypto.py — крипто-биржа: портфель + сделки (атомарно).
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
    """Купить/продать монету за Мору по серверной цене unit_price. Атомарно."""
    if amount <= 0:
        return False, "Количество должно быть больше нуля."
    cost = round(amount * unit_price, 2)
    amt_txt = f"{amount:g}"
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT user_balance_mora FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            bal = float(row[0]) if row else 0.0
            if action == "buy":
                if bal < cost:
                    return False, "Недостаточно Моры для покупки."
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
                async with db.execute(
                    "SELECT amount FROM crypto_holdings WHERE user_id = ? AND coin_id = ? FOR UPDATE",
                    (user_id, coin_id),
                ) as c:
                    hr = await c.fetchone()
                have = float(hr[0]) if hr else 0.0
                if have < amount - 1e-9:
                    return False, "Недостаточно монет для продажи."
                await db.execute(
                    "UPDATE crypto_holdings SET amount = amount - ? WHERE user_id = ? AND coin_id = ?",
                    (amount, user_id, coin_id),
                )
                await db.execute(
                    "UPDATE users SET user_balance_mora = user_balance_mora + ? WHERE user_tg_id = ?",
                    (cost, user_id),
                )
                await log_wallet(db, user_id, delta_mora=cost, source="crypto_sell",
                                 note=f"{coin_id} ×{amt_txt}")
                return True, f"Продано {amt_txt} {coin_id} за {cost:.0f} 🪙."
            return False, "Неизвестное действие."
    except Exception as e:
        return False, f"Ошибка: {e}"
