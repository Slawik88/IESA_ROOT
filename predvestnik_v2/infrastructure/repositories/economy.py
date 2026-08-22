"""
infrastructure/repositories/economy.py

ВАЖНО про атомарность (аудит H1/H2):
`add_balance` теперь всегда проходит через canonical economic ledger: операция,
`SELECT … FOR UPDATE`, обновление баланса, ledger и совместимый wallet_log
фиксируются одной транзакцией. Внешний `atomic()` всё ещё нужен операциям,
которые вместе с балансом меняют инвентарь/квоты/прогрессию.
Параметр `commit=` у add_balance — НЕ управляет транзакцией (в autocommit это
no-op); оставлен для совместимости вызовов. Внешний `atomic()` объединяет ledger
со связанными изменениями других таблиц в одну общую транзакцию.
"""
from contextlib import asynccontextmanager
from core.economy_contract import IdempotencyConflict, InsufficientBalance
from infrastructure.repositories.wallet_log import log_wallet
from infrastructure.repositories.economy_ledger import apply_balance_change, BalanceMutation
from infrastructure.pg_adapter import PGAdapter
from core.economy_v3 import (
    EconomyV3PolicyError,
    quote_zarniki_to_mora,
    validate_exchange_route,
)


@asynccontextmanager
async def atomic(db: PGAdapter, *user_ids: int):
    """Транзакция + блокировка строк указанных игроков (FOR UPDATE).

    Единый образец для всех «прочитал баланс → списал» операций (аудит H1).
    Использование:

        async with eco.atomic(db, user_id):
            bal = await get_balance(db, user_id)   # уже под локом строки
            if bal["user_balance_mora"] < cost: ...
            await add_balance(db, user_id, mora=-cost)

    Блокирует строки в порядке возрастания id (профилактика дедлоков при
    нескольких игроках, напр. перевод/дуэль).
    """
    async with db.connection.transaction():
        for uid in sorted(set(user_ids)):
            await db.execute(
                "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (uid,)
            )
            async with db.execute(
                "SELECT 1 FROM users WHERE user_tg_id = ? FOR UPDATE", (uid,)
            ) as _c:
                await _c.fetchone()
        yield


async def get_balance(db: PGAdapter, user_id: int) -> dict:
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,)
    )
    async with db.execute(
        "SELECT user_balance_mora, user_balance_diamonds, "
        "COALESCE(user_balance_dark_mora, 0) AS user_balance_dark_mora, "
        "COALESCE(user_balance_zarniki, 0) AS user_balance_zarniki "
        "FROM users WHERE user_tg_id = ?",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else {
        "user_balance_mora": 0.0,
        "user_balance_diamonds": 0.0,
        "user_balance_dark_mora": 0.0,
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
    *,
    idempotency_key: str | None = None,
    source_type: str = "game",
    reference_type: str | None = None,
    reference_id: str | int | None = None,
    metadata: dict | None = None,
    allow_negative: bool = False,
) -> BalanceMutation | None:
    """Credit or debit currency through the canonical append-only ledger.

    ``commit`` remains a no-op compatibility argument.  A caller-supplied
    idempotency key makes retries return the original operation without applying
    the deltas twice.  Calls without a key are treated as distinct operations.
    """
    if mora == 0 and diamonds == 0 and zarniki == 0:
        await db.execute(
            "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,)
        )
        return None
    return await apply_balance_change(
        db,
        user_id,
        {"mora": mora, "diamonds": diamonds, "zarniki": zarniki},
        reason_code=source,
        idempotency_key=idempotency_key,
        source_type=source_type,
        reference_type=reference_type,
        reference_id=reference_id,
        metadata=metadata,
        allow_negative=allow_negative,
        chat_id=chat_id,
        note=note,
    )


add_reward = add_balance  # alias


async def exchange_zarniki(
    db: PGAdapter, user_id: int, amount: float, to: str,
    chat_id: int | None = None,
    idempotency_key: str | None = None,
) -> tuple[bool, str]:
    """Необратимо обменять целое число Зарников на Мору по owner-v3."""
    try:
        validate_exchange_route("zarniki", to)
        quote = quote_zarniki_to_mora(amount)
        mutation = await add_balance(
            db, user_id, mora=quote.mora_received, zarniki=-quote.zarniki_spent,
            source="paid_exchange", source_type="exchange",
            idempotency_key=(
                f"exchange:zarniki:mora:{idempotency_key}" if idempotency_key else None
            ),
            reference_type="currency_pair", reference_id="zarniki_mora",
            metadata={
                "policy_version": "owner-v3-provisional-1",
                "provenance": quote.provenance,
                "rate": quote.rate,
                "reversible": quote.reversible,
            },
            chat_id=chat_id,
            note=f"✨{quote.zarniki_spent}→🪙{quote.mora_received}",
        )
        if mutation and not mutation.applied:
            return True, "✅ Этот обмен уже был обработан."
        return True, f"✅ {quote.zarniki_spent} ✨ → {quote.mora_received:,} 🪙"
    except EconomyV3PolicyError:
        if str(to).strip().lower() == "diamonds":
            return False, "Алмазы нельзя купить Зарниками — они выдаются за испытания и сезонные рубежи."
        return False, "Введите целое число Зарников больше нуля."
    except InsufficientBalance:
        current = await get_balance(db, user_id)
        return False, f"Недостаточно ✨ (есть {current['user_balance_zarniki']:.0f})."
    except IdempotencyConflict:
        return False, "Этот ключ запроса уже использован для другого обмена."
    except Exception as e:
        return False, f"Ошибка: {e}"


# Labels remain for legacy wallet history and stale callback rendering. Direct
# player-to-player balance transfers are closed by the approved economy rules.
TRANSFER_CURRENCIES: dict[str, dict] = {
    "mora":      {"col": "user_balance_mora",      "delta": "delta_mora",      "icon": "🪙", "label": "Мора"},
    "diamonds":  {"col": "user_balance_diamonds",  "delta": "delta_diamonds",  "icon": "💎", "label": "Алмазы"},
    "dark_mora": {"col": "user_balance_dark_mora", "delta": "delta_dark_mora", "icon": "🌑", "label": "Тёмная Мора"},
    "zarniki":   {"col": "user_balance_zarniki",   "delta": "delta_zarniki",   "icon": "✨", "label": "Зарники"},
}


async def transfer_currency(
    db: PGAdapter,
    sender_id: int,
    receiver_id: int,
    currency: str,
    amount: float,
    chat_id: int | None = None,
) -> tuple[bool, str]:
    """Reject legacy balance transfers without mutating either account."""
    return False, (
        "Прямые переводы валют отключены. Конкретную косметику можно подарить "
        "во вкладке «Внешний вид», а разрешённые предметы продать через аукцион."
    )


async def transfer_mora(
    db: PGAdapter,
    sender_id: int,
    receiver_id: int,
    amount: float,
    chat_id: int | None = None,
) -> tuple[bool, str]:
    """Обратная совместимость: перевод Моры = transfer_currency(..., 'mora')."""
    return await transfer_currency(db, sender_id, receiver_id, "mora", amount, chat_id)


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
    idempotency_key: str | None = None,
) -> tuple[bool, str]:
    """Deduct Mora through the canonical ledger exactly once when keyed."""
    if amount <= 0:
        return False, "Сумма <= 0"
    try:
        await add_balance(
            db, user_id, mora=-amount, source=source, chat_id=chat_id, note=note,
            idempotency_key=idempotency_key, source_type="spend",
        )
        return True, "OK"
    except InsufficientBalance:
        return False, "Недостаточно Моры."
    except IdempotencyConflict:
        return False, "Этот запрос уже использован для другой операции."
    except Exception as e:
        return False, f"Ошибка: {e}"


async def spend_diamonds(
    db: PGAdapter,
    user_id: int,
    amount: float,
    source: str = "spend",
    chat_id: int | None = None,
    note: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[bool, str]:
    """Deduct Diamonds through the canonical ledger exactly once when keyed."""
    if amount <= 0:
        return False, "Сумма <= 0"
    try:
        await add_balance(
            db, user_id, diamonds=-amount, source=source, chat_id=chat_id, note=note,
            idempotency_key=idempotency_key, source_type="spend",
        )
        return True, "OK"
    except InsufficientBalance:
        return False, "Недостаточно Алмазов."
    except IdempotencyConflict:
        return False, "Этот запрос уже использован для другой операции."
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
    idempotency_key: str | None = None,
) -> tuple[bool, str]:
    """Atomically charge the listed currencies and grant inventory.

    Owner-v3 deliberately forbids hidden premium shortfall coverage.  A player
    may explicitly exchange whole Zarniki to Mora in the wallet, but a shop
    purchase never converts currencies on their behalf.
    """
    if qty <= 0:
        return False, "Количество должно быть больше нуля."
    total_m = p_mora * qty
    total_d = p_dia * qty
    total_z = p_zarniki * qty
    deltas = {
        code: -amount
        for code, amount in (
            ("mora", total_m), ("diamonds", total_d), ("zarniki", total_z)
        )
        if amount > 0
    }
    if not deltas:
        return False, "Этот предмет нельзя купить."
    try:
        async with db.connection.transaction():
            mutation = await apply_balance_change(
                db, user_id, deltas,
                reason_code="shop_purchase",
                idempotency_key=idempotency_key,
                source_type="shop",
                reference_type="item",
                reference_id=item_id,
                metadata={"item_id": item_id, "quantity": qty},
                chat_id=chat_id,
                note=f"{item_id}×{qty}",
            )
            if mutation.applied:
                await db.execute(
                    "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = inventory.quantity + ?",
                    (user_id, item_id, qty, qty),
                )
        return True, "Покупка завершена." if mutation.applied else "Эта покупка уже обработана."
    except InsufficientBalance:
        return False, "Недостаточно средств."
    except IdempotencyConflict:
        return False, "Этот запрос уже использован для другой покупки."
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
