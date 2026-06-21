"""
infrastructure/repositories/relics.py
Реликвии (Implementation Block 13) — сток для Тёмной Моры.
Уникальные коллекционные предметы; эффект — суммарный +% к моро-награде экспедиций.
"""
from core.registry import RELICS

# колонка баланса для каждой валюты цены (whitelisted)
_PRICE_COLS = {
    "mora": "user_balance_mora",
    "diamonds": "user_balance_diamonds",
    "dark_mora": "user_balance_dark_mora",
}
_PRICE_ICON = {"mora": "🪙", "diamonds": "💎", "dark_mora": "🌑"}


def price_str(price: dict) -> str:
    return " + ".join(f"{int(v)} {_PRICE_ICON.get(k, k)}" for k, v in price.items())


async def list_owned(db, user_id: int) -> set[str]:
    async with db.execute(
        "SELECT relic_id FROM user_relics WHERE user_id = ?", (user_id,)
    ) as c:
        return {r[0] for r in await c.fetchall()}


async def get_expedition_mora_bonus(db, user_id: int) -> float:
    """Суммарный +% к моро-награде экспедиций от всех реликвий игрока (0.0..)."""
    owned = await list_owned(db, user_id)
    return sum(RELICS[r]["exp_mora_pct"] for r in owned if r in RELICS)


async def buy_relic(db, user_id: int, relic_id: str) -> tuple[bool, str]:
    """Купить реликвию (атомарно, мультивалютно). Реликвии уникальны — раз во владение."""
    relic = RELICS.get(relic_id)
    if not relic:
        return False, "Неизвестная реликвия."
    price: dict = relic["price"]
    try:
        async with db.connection.transaction():
            await db.execute(
                "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,)
            )
            # уже есть?
            async with db.execute(
                "SELECT 1 FROM user_relics WHERE user_id = ? AND relic_id = ?",
                (user_id, relic_id),
            ) as c:
                if await c.fetchone():
                    return False, "Эта реликвия уже в вашей коллекции."

            # читаем нужные балансы FOR UPDATE
            cols = [_PRICE_COLS[k] for k in price]
            async with db.execute(
                f"SELECT {', '.join('COALESCE(%s,0)' % c for c in cols)} "
                "FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            balances = {k: float(row[i]) for i, k in enumerate(price)}
            for k, amount in price.items():
                if balances[k] < amount:
                    return False, f"Недостаточно: {_PRICE_ICON[k]} (нужно {int(amount)})."

            # списываем все валюты
            for k, amount in price.items():
                col = _PRICE_COLS[k]
                await db.execute(
                    f"UPDATE users SET {col} = COALESCE({col},0) - ? WHERE user_tg_id = ?",
                    (amount, user_id),
                )
            await db.execute(
                "INSERT INTO user_relics (user_id, relic_id) VALUES (?, ?)",
                (user_id, relic_id),
            )
        return True, f"🏛 Реликвия получена: {relic['name']}!"
    except Exception as e:
        return False, f"Ошибка: {e}"
