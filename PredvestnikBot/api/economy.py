"""
api/economy.py — unified economy operations (transfers, balance, ledger).

All functions are async; the mini app wraps them with async_to_sync.
"""
from datetime import datetime, timezone, timedelta


async def log_wallet_tx(
    uid: int, chat_id: int, direction: str, amount: int,
    source: str, description: str = "",
) -> None:
    """Write one row to wallet_ledger. Silently no-ops if amount <= 0."""
    if amount <= 0:
        return
    try:
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            await db.execute(
                "INSERT INTO wallet_ledger "
                "(chat_id, user_id, direction, amount, source, description, created_at) "
                "VALUES ($1,$2,$3,$4,$5,$6,NOW())",
                (chat_id, uid, direction, amount, source, description or ""),
            )
            await db.commit()
    except Exception:
        pass  # Never break transactions because of ledger


async def transfer_mora(from_uid: int, to_uid: int, chat_id: int, amount: int,
                        cover_vat: bool = True) -> dict:
    """
    Transfer mora with progressive treasury tax.

    cover_vat=True  → sender pays amount+tax, receiver gets amount  (default)
    cover_vat=False → sender pays amount,     receiver gets amount-tax
    Raises ValueError with a Russian message on any error.
    Returns {ok, amount, tax, from_balance, to_balance}

    Atomic: deduct + credit + treasury tax in single transaction.
    """
    from database.db import get_mora
    from database.postgres import connect as postgres_connect

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
    if amount <= 1_000:
        tax_rate = 0.03
    elif amount <= 5_000:
        tax_rate = 0.07
    else:
        tax_rate = 0.08
    tax = max(1, int(amount * tax_rate))

    if cover_vat:
        deduct_total = amount + tax
        credit_amount = amount
    else:
        deduct_total = amount
        credit_amount = max(0, amount - tax)

    # Atomic transaction: deduct sender → credit receiver → tax to treasury
    async with postgres_connect() as db:
        # 1. Deduct from sender (atomic check)
        cursor = await db.execute(
            "UPDATE users SET balance = balance - $1 "
            "WHERE user_id = $1 AND COALESCE(balance,0) >= $2",
            (deduct_total, from_uid, deduct_total),
        )
        if cursor.rowcount == 0:
            mora_row = await get_mora(from_uid, chat_id)
            bal = mora_row["balance"] if mora_row else 0
            hint = f"сумма + налог {tax}" if cover_vat else f"налог {tax} вычтется у получателя"
            raise ValueError(f"Недостаточно Моры. Нужно {deduct_total} 🪙 ({hint})")

        # 2. Credit receiver
        await db.execute(
            "UPDATE users SET balance=COALESCE(balance,0)+$1, total_earned=COALESCE(total_earned,0)+$2 WHERE user_id=$3",
            (credit_amount, credit_amount, to_uid),
        )

        # 3. Tax to treasury
        await db.execute(
            "INSERT INTO chat_treasury (chat_id, balance) VALUES ($1,$2)"
            " ON CONFLICT(chat_id) DO UPDATE SET balance = chat_treasury.balance + excluded.balance",
            (chat_id, tax),
        )
        await db.execute(
            """INSERT INTO treasury_log (chat_id, user_id, amount, source, created_at)
               VALUES ($1,$2,$3,$4,NOW())""",
            (chat_id, from_uid, tax, "transfer"),
        )

        await db.commit()

        # Read final balances
        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM users WHERE user_id=$1",
            (from_uid,),
        ) as c:
            row = await c.fetchone()
        from_bal = row[0] if row else 0

        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM users WHERE user_id=$1",
            (to_uid,),
        ) as c:
            row = await c.fetchone()
        to_bal = row[0] if row else 0

    # Log in ledger (fire-and-forget, never breaks the main transaction)
    # Resolve nicknames for human-readable history
    try:
        from database.db import get_user_name
        to_name = await get_user_name(to_uid) or str(to_uid)
        from_name = await get_user_name(from_uid) or str(from_uid)
    except Exception:
        to_name, from_name = str(to_uid), str(from_uid)

    await log_wallet_tx(from_uid, chat_id, "expense", deduct_total, "transfer_out",
                        f"→ {to_name} -{tax}🪙 налог")
    await log_wallet_tx(to_uid, chat_id, "income", credit_amount, "transfer_in",
                        f"← {from_name}")

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
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT direction, amount, source, description, created_at "
            "FROM wallet_ledger WHERE user_id=$1 AND chat_id=$2 "
            "AND created_at >= $1 "
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


# ─── Chat-global XP buff ──────────────────────────────────────────────────────

CHAT_BUFF_PRICE = 1500        # Мора
CHAT_BUFF_DURATION_MINUTES = 60


async def buy_chat_buff(uid: int, chat_id: int, buff_type: str = "xp_plus10") -> dict:
    """
    Deduct CHAT_BUFF_PRICE mora and activate a global XP buff for the chat.
    Raises ValueError (Russian message) on any failure.
    Returns {"ok", "expires_at", "cost", "new_balance"}.
    """
    from database.db import get_mora, activate_chat_buff, get_active_chat_buff
    from database.postgres import connect as postgres_connect

    existing = await get_active_chat_buff(chat_id, buff_type)
    if existing:
        exp = existing.get("expires_at")
        raise ValueError(f"Баф уже активен до {exp} ⏰")

    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE users SET balance=balance-$1 WHERE user_id=$2 AND COALESCE(balance,0)>=$3",
            (CHAT_BUFF_PRICE, uid, CHAT_BUFF_PRICE),
        )
        if cursor.rowcount == 0:
            mora_row = await get_mora(uid, chat_id)
            bal = mora_row["balance"] if mora_row else 0
            raise ValueError(f"Недостаточно Моры: {bal}/{CHAT_BUFF_PRICE} 🪙")
        await db.commit()
        async with db.execute(
            "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=$1",
            (uid,),
        ) as c:
            row = await c.fetchone()
        new_bal = row[0] if row else 0

    result = await activate_chat_buff(chat_id, buff_type, uid, CHAT_BUFF_DURATION_MINUTES)

    # 5% НДС from chat buff purchases → treasury
    from database.db import add_to_treasury
    buff_tax = max(1, int(CHAT_BUFF_PRICE * 0.05))
    await add_to_treasury(chat_id, buff_tax, "chat_buff", uid)

    return {
        "ok":          True,
        "buff_type":   buff_type,
        "expires_at":  result["expires_at"],
        "cost":        CHAT_BUFF_PRICE,
        "new_balance": new_bal,
    }

