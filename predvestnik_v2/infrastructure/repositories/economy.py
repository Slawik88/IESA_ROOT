# infrastructure/repositories/economy.py
# Canonical data-access layer for economy: balances, inventory, shop transactions.
# Every balance change is logged to wallet_log (B9).
import aiosqlite

from infrastructure.repositories.wallet_log import log_wallet


async def get_balance(db: aiosqlite.Connection, user_id: int) -> dict:
    """Получить баланс. Если юзера нет — создать его."""
    await db.execute("INSERT OR IGNORE INTO users (user_tg_id) VALUES (?)", (user_id,))
    async with db.execute(
        "SELECT user_balance_mora, user_balance_diamonds FROM users WHERE user_tg_id = ?",
        (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else {"user_balance_mora": 0.0, "user_balance_diamonds": 0.0}


async def add_balance(
    db: aiosqlite.Connection,
    user_id: int,
    mora: float = 0,
    diamonds: float = 0,
    commit: bool = True,
    source: str = "system",
    chat_id: int | None = None,
    note: str | None = None,
):
    """Начислить или списать валюту. Каждый вызов логируется в wallet_log."""
    await db.execute("INSERT OR IGNORE INTO users (user_tg_id) VALUES (?)", (user_id,))
    await db.execute(
        "UPDATE users SET user_balance_mora = user_balance_mora + ?, "
        "user_balance_diamonds = user_balance_diamonds + ? WHERE user_tg_id = ?",
        (mora, diamonds, user_id)
    )
    await log_wallet(db, user_id, delta_mora=mora, delta_diamonds=diamonds,
                     source=source, chat_id=chat_id, note=note)
    if commit:
        await db.commit()


# Alias — same semantics as add_balance.
add_reward = add_balance


async def transfer_mora(
    db: aiosqlite.Connection,
    sender_id: int,
    receiver_id: int,
    amount: float,
    chat_id: int | None = None,
) -> tuple[bool, str]:
    """Атомарный перевод Моры между игроками. Логирует обе стороны."""
    if amount <= 0:
        return False, "Сумма <= 0"
    sender_bal = await get_balance(db, sender_id)
    if sender_bal["user_balance_mora"] < amount:
        return False, "Недостаточно Моры."
    try:
        await db.execute(
            "UPDATE users SET user_balance_mora = user_balance_mora - ? WHERE user_tg_id = ?",
            (amount, sender_id)
        )
        await db.execute("INSERT OR IGNORE INTO users (user_tg_id) VALUES (?)", (receiver_id,))
        await db.execute(
            "UPDATE users SET user_balance_mora = user_balance_mora + ? WHERE user_tg_id = ?",
            (amount, receiver_id)
        )
        await log_wallet(db, sender_id, delta_mora=-amount, source="transfer_out",
                         chat_id=chat_id, target_id=receiver_id, note=f"→{receiver_id}")
        await log_wallet(db, receiver_id, delta_mora=amount, source="transfer_in",
                         chat_id=chat_id, target_id=sender_id, note=f"←{sender_id}")
        await db.commit()
        return True, "Перевод успешен."
    except Exception as e:
        await db.rollback()
        return False, f"Ошибка: {e}"


async def get_inventory(db: aiosqlite.Connection, user_id: int) -> list[dict]:
    async with db.execute(
        "SELECT item_id, quantity FROM inventory WHERE user_id = ? AND quantity > 0", (user_id,)
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def add_item(db: aiosqlite.Connection, user_id: int, item_id: str, quantity: int = 1):
    await db.execute(
        "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + ?",
        (user_id, item_id, quantity, quantity)
    )
    await db.commit()


async def remove_item(
    db: aiosqlite.Connection, user_id: int, item_id: str, quantity: int = 1, commit: bool = True
) -> bool:
    async with db.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?", (user_id, item_id)
    ) as cursor:
        row = await cursor.fetchone()
        if not row or row[0] < quantity:
            return False

    await db.execute(
        "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ?",
        (quantity, user_id, item_id)
    )
    await db.execute("DELETE FROM inventory WHERE user_id = ? AND quantity <= 0", (user_id,))
    if commit:
        await db.commit()
    return True


async def get_item_quantity(db: aiosqlite.Connection, user_id: int, item_id: str) -> int:
    async with db.execute(
        "SELECT quantity FROM inventory WHERE user_id = ? AND item_id = ?", (user_id, item_id)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def spend_mora(
    db: aiosqlite.Connection,
    user_id: int,
    amount: float,
    source: str = "spend",
    chat_id: int | None = None,
    note: str | None = None,
) -> tuple[bool, str]:
    """Списать Мору. Логируется."""
    if amount <= 0:
        return False, "Сумма <= 0"
    balance = await get_balance(db, user_id)
    if balance["user_balance_mora"] < amount:
        return False, "Недостаточно Моры."
    await db.execute(
        "UPDATE users SET user_balance_mora = user_balance_mora - ? WHERE user_tg_id = ?",
        (amount, user_id)
    )
    await log_wallet(db, user_id, delta_mora=-amount, source=source,
                     chat_id=chat_id, note=note)
    await db.commit()
    return True, "OK"


async def spend_diamonds(
    db: aiosqlite.Connection,
    user_id: int,
    amount: float,
    source: str = "spend",
    chat_id: int | None = None,
    note: str | None = None,
) -> tuple[bool, str]:
    """Списать Алмазы. Логируется."""
    if amount <= 0:
        return False, "Сумма <= 0"
    balance = await get_balance(db, user_id)
    if balance["user_balance_diamonds"] < amount:
        return False, "Недостаточно Алмазов."
    await db.execute(
        "UPDATE users SET user_balance_diamonds = user_balance_diamonds - ? WHERE user_tg_id = ?",
        (amount, user_id)
    )
    await log_wallet(db, user_id, delta_diamonds=-amount, source=source,
                     chat_id=chat_id, note=note)
    await db.commit()
    return True, "OK"


async def buy_item(
    db: aiosqlite.Connection,
    user_id: int,
    item_id: str,
    p_mora: float,
    p_dia: float,
    qty: int,
    chat_id: int | None = None,
) -> tuple[bool, str]:
    total_m = p_mora * qty
    total_d = p_dia * qty
    bal = await get_balance(db, user_id)
    if bal["user_balance_mora"] < total_m or bal["user_balance_diamonds"] < total_d:
        return False, "Недостаточно средств."
    try:
        await db.execute(
            "UPDATE users SET user_balance_mora = user_balance_mora - ?, "
            "user_balance_diamonds = user_balance_diamonds - ? WHERE user_tg_id = ?",
            (total_m, total_d, user_id)
        )
        await db.execute(
            "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + ?",
            (user_id, item_id, qty, qty)
        )
        if total_m > 0:
            await log_wallet(db, user_id, delta_mora=-total_m, source="shop_purchase",
                             chat_id=chat_id, note=f"{item_id}×{qty}")
        if total_d > 0:
            await log_wallet(db, user_id, delta_diamonds=-total_d, source="shop_purchase",
                             chat_id=chat_id, note=f"{item_id}×{qty}")
        await db.commit()
        return True, "Покупка успешна."
    except Exception as e:
        await db.rollback()
        return False, f"Ошибка: {e}"


async def set_balance(
    db: aiosqlite.Connection,
    user_id: int,
    mora: float,
    diamonds: float,
    chat_id: int | None = None,
):
    """Установить баланс (admin). Логируется как manual_admin."""
    old = await get_balance(db, user_id)
    await db.execute("INSERT OR IGNORE INTO users (user_tg_id) VALUES (?)", (user_id,))
    await db.execute(
        "UPDATE users SET user_balance_mora = ?, user_balance_diamonds = ? WHERE user_tg_id = ?",
        (mora, diamonds, user_id)
    )
    delta_m = mora - old["user_balance_mora"]
    delta_d = diamonds - old["user_balance_diamonds"]
    await log_wallet(db, user_id, delta_mora=delta_m, delta_diamonds=delta_d,
                     source="manual_admin", chat_id=chat_id)
    await db.commit()
