"""
infrastructure/repositories/economy.py
All balance-changing functions use explicit asyncpg transactions
to prevent race conditions with concurrent users.
"""
from infrastructure.repositories.wallet_log import log_wallet
from infrastructure.pg_adapter import PGAdapter
from core.constants import ZARNIKI_TO_MORA_RATE, ZARNIKI_TO_DIAMONDS_RATE


async def get_balance(db: PGAdapter, user_id: int) -> dict:
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,)
    )
    async with db.execute(
        "SELECT user_balance_mora, user_balance_diamonds, "
        "COALESCE(user_balance_zarniki, 0) AS user_balance_zarniki "
        "FROM users WHERE user_tg_id = ?",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else {
        "user_balance_mora": 0.0,
        "user_balance_diamonds": 0.0,
        "user_balance_zarniki": 0.0,
    }


async def add_balance(
    db: PGAdapter,
    user_id: int,
    mora: float = 0,
    diamonds: float = 0,
    zarniki: float = 0,
    commit: bool = True,    # kept for API compat — no-op in asyncpg auto-commit
    source: str = "system",
    chat_id: int | None = None,
    note: str | None = None,
):
    """Credit or debit currency. Each call is logged in wallet_log."""
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,)
    )
    await db.execute(
        "UPDATE users SET "
        "user_balance_mora = user_balance_mora + ?, "
        "user_balance_diamonds = user_balance_diamonds + ?, "
        "user_balance_zarniki = COALESCE(user_balance_zarniki, 0) + ? "
        "WHERE user_tg_id = ?",
        (mora, diamonds, zarniki, user_id),
    )
    await log_wallet(
        db, user_id, delta_mora=mora, delta_diamonds=diamonds, delta_zarniki=zarniki,
        source=source, chat_id=chat_id, note=note,
    )


add_reward = add_balance  # alias


async def exchange_zarniki(
    db: PGAdapter, user_id: int, amount: float, to: str,
    chat_id: int | None = None,
) -> tuple[bool, str]:
    """✨ → 🪙 (×ZARNIKI_TO_MORA_RATE) или ✨ → 💎 (×ZARNIKI_TO_DIAMONDS_RATE).
    Одностороннее, без лимита."""
    if amount <= 0 or to not in ("mora", "diamonds"):
        return False, "Некорректные параметры обмена."
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT COALESCE(user_balance_zarniki, 0) FROM users "
                "WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            current = float(row[0]) if row else 0.0
            if current < amount:
                return False, f"Недостаточно ✨ (есть {current:.0f})."

            if to == "mora":
                gained = amount * ZARNIKI_TO_MORA_RATE
                await add_balance(db, user_id, mora=gained, zarniki=-amount,
                                   source="zarniki_exchange", chat_id=chat_id,
                                   note=f"✨{amount:.0f}→🪙{gained:.0f}")
                return True, f"✅ Обменяно ✨{amount:.0f} → 🪙{gained:.0f}"

            gained = amount * ZARNIKI_TO_DIAMONDS_RATE
            await add_balance(db, user_id, diamonds=gained, zarniki=-amount,
                               source="zarniki_exchange", chat_id=chat_id,
                               note=f"✨{amount:.0f}→💎{gained:.2f}")
            return True, f"✅ Обменяно ✨{amount:.0f} → 💎{gained:.2f}"
    except Exception as e:
        return False, f"Ошибка: {e}"


async def transfer_mora(
    db: PGAdapter,
    sender_id: int,
    receiver_id: int,
    amount: float,
    chat_id: int | None = None,
) -> tuple[bool, str]:
    """Atomic mora transfer. Uses explicit transaction to prevent double-spend."""
    if amount <= 0:
        return False, "Сумма <= 0"
    try:
        async with db.connection.transaction():
            # Re-read balance inside the transaction (prevents TOCTOU race)
            async with db.execute(
                "SELECT user_balance_mora FROM users WHERE user_tg_id = ? FOR UPDATE",
                (sender_id,),
            ) as c:
                row = await c.fetchone()
            if not row or row[0] < amount:
                return False, "Недостаточно Моры."

            await db.execute(
                "UPDATE users SET user_balance_mora = user_balance_mora - ? "
                "WHERE user_tg_id = ?",
                (amount, sender_id),
            )
            await db.execute(
                "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING",
                (receiver_id,),
            )
            await db.execute(
                "UPDATE users SET user_balance_mora = user_balance_mora + ? "
                "WHERE user_tg_id = ?",
                (amount, receiver_id),
            )
            await log_wallet(
                db, sender_id, delta_mora=-amount, source="transfer_out",
                chat_id=chat_id, target_id=receiver_id, note=f"→{receiver_id}",
            )
            await log_wallet(
                db, receiver_id, delta_mora=amount, source="transfer_in",
                chat_id=chat_id, target_id=sender_id, note=f"←{sender_id}",
            )
        return True, "Перевод успешен."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def get_inventory(db: PGAdapter, user_id: int) -> list[dict]:
    async with db.execute(
        "SELECT item_id, quantity FROM inventory WHERE user_id = ? AND quantity > 0",
        (user_id,),
    ) as c:
        return [dict(row) for row in await c.fetchall()]


async def add_item(db: PGAdapter, user_id: int, item_id: str, quantity: int = 1):
    await db.execute(
        "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
        (user_id, item_id, quantity, quantity),
    )


async def remove_item(
    db: PGAdapter, user_id: int, item_id: str, quantity: int = 1, commit: bool = True
) -> bool:
    """Atomically remove items. Returns False if insufficient quantity."""
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ? FOR UPDATE",
                (user_id, item_id),
            ) as c:
                row = await c.fetchone()
            if not row or row[0] < quantity:
                return False
            await db.execute(
                "UPDATE inventory SET quantity = quantity - ? "
                "WHERE user_id = ? AND item_id = ?",
                (quantity, user_id, item_id),
            )
            await db.execute(
                "DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0",
                (user_id, item_id),
            )
        return True
    except Exception:
        return False


async def get_item_quantity(db: PGAdapter, user_id: int, item_id: str) -> int:
    async with db.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


async def spend_mora(
    db: PGAdapter,
    user_id: int,
    amount: float,
    source: str = "spend",
    chat_id: int | None = None,
    note: str | None = None,
) -> tuple[bool, str]:
    """Deduct mora atomically. Prevents negative balance under concurrency."""
    if amount <= 0:
        return False, "Сумма <= 0"
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT user_balance_mora FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            if not row or row[0] < amount:
                return False, "Недостаточно Моры."
            await db.execute(
                "UPDATE users SET user_balance_mora = user_balance_mora - ? "
                "WHERE user_tg_id = ?",
                (amount, user_id),
            )
            await log_wallet(db, user_id, delta_mora=-amount, source=source,
                             chat_id=chat_id, note=note)
        return True, "OK"
    except Exception as e:
        return False, f"Ошибка: {e}"


async def spend_diamonds(
    db: PGAdapter,
    user_id: int,
    amount: float,
    source: str = "spend",
    chat_id: int | None = None,
    note: str | None = None,
) -> tuple[bool, str]:
    """Deduct diamonds atomically. Prevents negative balance under concurrency."""
    if amount <= 0:
        return False, "Сумма <= 0"
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT user_balance_diamonds FROM users WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                row = await c.fetchone()
            if not row or row[0] < amount:
                return False, "Недостаточно Алмазов."
            await db.execute(
                "UPDATE users SET user_balance_diamonds = user_balance_diamonds - ? "
                "WHERE user_tg_id = ?",
                (amount, user_id),
            )
            await log_wallet(db, user_id, delta_diamonds=-amount, source=source,
                             chat_id=chat_id, note=note)
        return True, "OK"
    except Exception as e:
        return False, f"Ошибка: {e}"


async def buy_item(
    db: PGAdapter,
    user_id: int,
    item_id: str,
    p_mora: float,
    p_dia: float,
    qty: int,
    chat_id: int | None = None,
    p_zarniki: float = 0,
) -> tuple[bool, str]:
    total_m = p_mora * qty
    total_d = p_dia * qty
    total_z = p_zarniki * qty
    try:
        async with db.connection.transaction():
            async with db.execute(
                "SELECT user_balance_mora, user_balance_diamonds, "
                "COALESCE(user_balance_zarniki, 0) FROM users "
                "WHERE user_tg_id = ? FOR UPDATE",
                (user_id,),
            ) as c:
                bal = await c.fetchone()
            if not bal or bal[0] < total_m or bal[1] < total_d or bal[2] < total_z:
                return False, "Недостаточно средств."

            await db.execute(
                "UPDATE users SET user_balance_mora = user_balance_mora - ?, "
                "user_balance_diamonds = user_balance_diamonds - ?, "
                "user_balance_zarniki = COALESCE(user_balance_zarniki, 0) - ? "
                "WHERE user_tg_id = ?",
                (total_m, total_d, total_z, user_id),
            )
            await db.execute(
                "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
                (user_id, item_id, qty, qty),
            )
            if total_m > 0:
                await log_wallet(db, user_id, delta_mora=-total_m, source="shop_purchase",
                                 chat_id=chat_id, note=f"{item_id}×{qty}")
            if total_d > 0:
                await log_wallet(db, user_id, delta_diamonds=-total_d, source="shop_purchase",
                                 chat_id=chat_id, note=f"{item_id}×{qty}")
            if total_z > 0:
                await log_wallet(db, user_id, delta_zarniki=-total_z, source="shop_purchase",
                                 chat_id=chat_id, note=f"{item_id}×{qty}")
        return True, "Покупка успешна."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def set_balance(
    db: PGAdapter,
    user_id: int,
    mora: float,
    diamonds: float,
    chat_id: int | None = None,
):
    """Set absolute balance (admin). Logged as manual_admin."""
    old = await get_balance(db, user_id)
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,)
    )
    await db.execute(
        "UPDATE users SET user_balance_mora = ?, user_balance_diamonds = ? "
        "WHERE user_tg_id = ?",
        (mora, diamonds, user_id),
    )
    await log_wallet(
        db, user_id,
        delta_mora=mora - old["user_balance_mora"],
        delta_diamonds=diamonds - old["user_balance_diamonds"],
        source="manual_admin", chat_id=chat_id,
    )
