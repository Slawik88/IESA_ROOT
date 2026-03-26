"""
api/economy.py — unified economy operations (transfers, balance, ledger).

All functions are async; the mini app wraps them with async_to_sync.
"""
from datetime import datetime, timezone, timedelta


async def transfer_mora(from_uid: int, to_uid: int, chat_id: int, amount: int,
                        cover_vat: bool = True) -> dict:
    """
    Transfer mora with progressive treasury tax.

    cover_vat=True  → sender pays amount+tax, receiver gets amount  (default)
    cover_vat=False → sender pays amount,     receiver gets amount-tax
    Raises ValueError with a Russian message on any error.
    Returns {ok, amount, tax, from_balance, to_balance}
    """
    from database.db import add_mora, add_to_treasury, deduct_mora, get_mora

    try:
        from config import MORA_TRANSFER_MIN, MORA_TRANSFER_MAX
    except Exception:
        MORA_TRANSFER_MIN, MORA_TRANSFER_MAX = 1, 5_000

    if from_uid == to_uid:
        raise ValueError("Нельзя переводить самому себе")
    if amount < MORA_TRANSFER_MIN:
        raise ValueError(f"Минимальная сумма перевода: {MORA_TRANSFER_MIN} 🪙")
    if amount > MORA_TRANSFER_MAX:
        raise ValueError(f"Максимальная сумма перевода: {MORA_TRANSFER_MAX} 🪙")

    # Progressive tax
    if amount <= 500:
        tax_rate = 0.03
    elif amount <= 2_000:
        tax_rate = 0.07
    else:
        tax_rate = 0.08
    tax = max(1, int(amount * tax_rate))

    mora_row = await get_mora(from_uid, chat_id)
    bal = mora_row["balance"] if mora_row else 0

    if cover_vat:
        deduct_total = amount + tax
        credit_amount = amount
    else:
        deduct_total = amount
        credit_amount = max(0, amount - tax)

    if bal < deduct_total:
        need = deduct_total
        hint = f"сумма + налог {tax}" if cover_vat else f"налог {tax} вычтется у получателя"
        raise ValueError(f"Недостаточно Моры. Нужно {need} 🪙 ({hint})")

    # Deduct from sender atomically
    ok, from_bal = await deduct_mora(from_uid, chat_id, deduct_total)
    if not ok:
        raise ValueError("Не удалось выполнить перевод")

    # Credit receiver
    to_bal = await add_mora(to_uid, chat_id, credit_amount)

    # Tax to treasury
    await add_to_treasury(chat_id, tax, "transfer", from_uid)

    return {
        "ok":           True,
        "amount":       credit_amount,
        "tax":          tax,
        "from_balance": from_bal,
        "to_balance":   to_bal,
    }


async def get_balance(uid: int, chat_id: int) -> int:
    """Returns current personal mora balance."""
    from database.db import get_mora
    mora_row = await get_mora(uid, chat_id)
    return mora_row["balance"] if mora_row else 0


async def wallet_history(uid: int, chat_id: int, days: int = 7) -> list:
    """Returns up to 100 wallet-ledger entries from the last N days."""
    from database.postgres import connect as postgres_connect
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT direction, amount, source, description, created_at "
            "FROM wallet_ledger WHERE user_id=? AND chat_id=? "
            "AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 100",
            (uid, chat_id, cutoff),
        ) as c:
            rows = await c.fetchall()
    return [
        {
            "direction":   r[0],
            "amount":      r[1],
            "source":      r[2],
            "description": r[3] or "",
            "created_at":  str(r[4]),
        }
        for r in rows
    ]
