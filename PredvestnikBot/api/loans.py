"""
api/loans.py — unified loan (долг) operations.

All functions are async; the mini app wraps them with async_to_sync.
"""
from datetime import datetime, timezone
import logging
_log = logging.getLogger(__name__)


async def get_loans(uid: int, chat_id: int) -> dict:
    """Return all active and pending loans for the user.

    Returns {borrowed, lent, pending_incoming, pending_outgoing}.
    """
    from database.postgres import connect as postgres_connect
    from database.db import get_user

    async with postgres_connect() as db:
        # Borrowed (accepted, not repaid)
        async with db.execute(
            "SELECT id, lender_id, amount, loaned_at FROM mora_loans "
            "WHERE borrower_id=? AND chat_id=? AND repaid_at IS NULL "
            "AND COALESCE(status,'accepted')='accepted' ORDER BY id",
            (uid, chat_id),
        ) as c:
            borrowed_rows = await c.fetchall()

        # Pending incoming (someone wants to lend me money)
        async with db.execute(
            "SELECT id, lender_id, amount, loaned_at FROM mora_loans "
            "WHERE borrower_id=? AND chat_id=? AND repaid_at IS NULL "
            "AND status='pending' ORDER BY id",
            (uid, chat_id),
        ) as c:
            pending_in_rows = await c.fetchall()

        # Lent out (accepted, not repaid)
        async with db.execute(
            "SELECT id, borrower_id, amount, loaned_at FROM mora_loans "
            "WHERE lender_id=? AND chat_id=? AND repaid_at IS NULL "
            "AND COALESCE(status,'accepted')='accepted' ORDER BY id",
            (uid, chat_id),
        ) as c:
            lent_rows = await c.fetchall()

        # Pending outgoing (I offered a loan, waiting for borrower)
        async with db.execute(
            "SELECT id, borrower_id, amount, loaned_at FROM mora_loans "
            "WHERE lender_id=? AND chat_id=? AND repaid_at IS NULL "
            "AND status='pending' ORDER BY id",
            (uid, chat_id),
        ) as c:
            pending_out_rows = await c.fetchall()

    # Batch-resolve names
    user_ids = set()
    for r in borrowed_rows + pending_in_rows:
        user_ids.add(r[1])  # lender_id
    for r in lent_rows + pending_out_rows:
        user_ids.add(r[1])  # borrower_id

    names: dict[int, str] = {}
    for uid2 in user_ids:
        u = await get_user(uid2)
        names[uid2] = u["full_name"] if u else f"Игрок {uid2}"

    def _fmt(row, other_key: str) -> dict:
        other_id = row[1]
        loaned_at = row[3]
        return {
            "id": row[0],
            f"{other_key}_id": other_id,
            f"{other_key}_name": names.get(other_id, f"Игрок {other_id}"),
            "amount": row[2],
            "loaned_at": loaned_at.isoformat() if hasattr(loaned_at, "isoformat") else str(loaned_at),
        }

    return {
        "ok": True,
        "borrowed": [_fmt(r, "lender") for r in borrowed_rows],
        "lent": [_fmt(r, "borrower") for r in lent_rows],
        "pending_incoming": [_fmt(r, "lender") for r in pending_in_rows],
        "pending_outgoing": [_fmt(r, "borrower") for r in pending_out_rows],
    }


async def create_loan(uid: int, target_id: int, chat_id: int, amount: int) -> dict:
    """Create a pending loan offer from uid (lender) to target_id (borrower).

    Money is NOT deducted until the borrower accepts.
    Raises ValueError on validation errors.
    Returns {ok, loan_id, amount, new_balance, pending}.
    """
    from database.db import get_mora
    from database.postgres import connect as postgres_connect

    try:
        from config import LOAN_MAX_AMOUNT, LOAN_MAX_ACTIVE
    except Exception:
        LOAN_MAX_AMOUNT, LOAN_MAX_ACTIVE = 2000, 5

    if uid == target_id:
        raise ValueError("Нельзя давать в долг самому себе")
    if amount <= 0 or amount > LOAN_MAX_AMOUNT:
        raise ValueError(f"Сумма: 1–{LOAN_MAX_AMOUNT} 🪙")

    async with postgres_connect() as db:
        # Check borrower's active loan count
        async with db.execute(
            "SELECT COUNT(*) FROM mora_loans "
            "WHERE borrower_id=? AND chat_id=? AND repaid_at IS NULL",
            (target_id, chat_id),
        ) as c:
            active = (await c.fetchone())[0]
        if active >= LOAN_MAX_ACTIVE:
            raise ValueError(
                f"У заёмщика уже {active} активных долгов (максимум {LOAN_MAX_ACTIVE})"
            )

        # Check lender balance (informational — money moves on accept)
        mora_row = await get_mora(uid, chat_id)
        balance = mora_row["balance"] if mora_row else 0
        if balance < amount:
            raise ValueError(f"Недостаточно Моры. У тебя {balance} 🪙")

        now = datetime.now(timezone.utc)
        cursor = await db.execute(
            "INSERT INTO mora_loans (lender_id, borrower_id, chat_id, amount, loaned_at, status) "
            "VALUES (?,?,?,?,?,'pending') RETURNING id",
            (uid, target_id, chat_id, amount, now),
        )
        row = await cursor.fetchone()
        loan_id = row[0] if row else 0
        await db.commit()

    return {
        "ok": True,
        "loan_id": loan_id,
        "amount": amount,
        "new_balance": balance,
        "pending": True,
    }


async def repay_loan(uid: int, chat_id: int, loan_id: int) -> dict:
    """Repay an accepted loan. Deducts from borrower, credits lender.

    Raises ValueError on error.
    Returns {ok, loan_id, amount, new_balance}.
    """
    from database.db import add_mora, get_mora
    from database.postgres import connect as postgres_connect

    # Atomic: check ownership + sufficient balance + mark as repaid + deduct all in one transaction
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT id, lender_id, amount FROM mora_loans "
            "WHERE id=? AND borrower_id=? AND chat_id=? AND repaid_at IS NULL "
            "AND COALESCE(status,'accepted')='accepted'",
            (loan_id, uid, chat_id),
        ) as c:
            loan = await c.fetchone()
        if not loan:
            raise ValueError("Долг не найден или уже погашен")

        lender_id = loan[1]
        amount = loan[2]

        # Atomically deduct + mark repaid in same transaction
        cursor = await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (amount, uid, amount),
        )
        if cursor.rowcount == 0:
            mora_row = await get_mora(uid, chat_id)
            balance = mora_row["balance"] if mora_row else 0
            raise ValueError(f"Недостаточно Моры. Нужно {amount} 🪙, у тебя {balance}")

        await db.execute(
            "UPDATE mora_loans SET repaid_at=NOW() WHERE id=?",
            (loan_id,),
        )

    await add_mora(lender_id, chat_id, amount)

    new_mora = await get_mora(uid, chat_id)
    new_balance = new_mora["balance"] if new_mora else 0

    # Log repayment
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(uid, chat_id, "expense", amount, "loan_repay",
                            f"Погашение долга #{loan_id}")
        await log_wallet_tx(lender_id, chat_id, "income", amount, "loan_repay",
                            f"Возврат долга #{loan_id}")
    except Exception:
        pass

    return {
        "ok": True,
        "loan_id": loan_id,
        "amount": amount,
        "new_balance": new_balance,
    }


async def respond_to_loan(uid: int, chat_id: int, loan_id: int, action: str) -> dict:
    """Accept or reject a pending loan as the borrower.

    On accept: deducts from lender → credits borrower.
    Raises ValueError on error.
    Returns {ok, action, loan_id, amount, new_balance?}.
    """
    from database.db import get_mora
    from database.postgres import connect as postgres_connect

    if action not in ("accept", "reject"):
        raise ValueError("action must be accept or reject")

    if action == "reject":
        async with postgres_connect() as db:
            async with db.execute(
                "UPDATE mora_loans SET status='rejected', repaid_at=NOW() "
                "WHERE id=? AND borrower_id=? AND chat_id=? AND status='pending' "
                "RETURNING id",
                (loan_id, uid, chat_id),
            ) as c:
                row = await c.fetchone()
            if not row:
                raise ValueError("Заявка не найдена или уже обработана")
            await db.commit()
        return {"ok": True, "action": "rejected"}

    # Accept: atomically check + deduct from lender + activate loan in one transaction
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT id, lender_id, amount FROM mora_loans "
            "WHERE id=? AND borrower_id=? AND chat_id=? AND status='pending' AND repaid_at IS NULL",
            (loan_id, uid, chat_id),
        ) as c:
            loan = await c.fetchone()
        if not loan:
            raise ValueError("Заявка не найдена или уже обработана")

        lender_id = loan[1]
        amount = loan[2]

        # Atomically deduct from lender + mark accepted in same transaction
        cursor = await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (amount, lender_id, amount),
        )
        if cursor.rowcount == 0:
            mora_row = await get_mora(lender_id, chat_id)
            lender_bal = mora_row["balance"] if mora_row else 0
            raise ValueError(f"У кредитора недостаточно Моры ({lender_bal}/{amount} 🪙)")

        # Credit borrower IN THE SAME TRANSACTION so lender deduction and
        # borrower credit are atomic — no money can disappear if one side fails.
        await db.execute(
            """UPDATE users SET
                   balance      = GREATEST(0, COALESCE(balance, 0) + ?),
                   total_earned = COALESCE(total_earned, 0) + ?
               WHERE user_id = ?""",
            (amount, amount, uid),
        )

        await db.execute(
            "UPDATE mora_loans SET status='accepted' WHERE id=?",
            (loan_id,),
        )

        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?", (uid,)
        ) as c:
            bal_row = await c.fetchone()
        new_balance = bal_row[0] if bal_row else 0

    # Log loan acceptance
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(lender_id, chat_id, "expense", amount, "loan_give",
                            f"Выдан заём #{loan_id}")
        await log_wallet_tx(uid, chat_id, "income", amount, "loan_receive",
                            f"Получен заём #{loan_id}")
    except Exception:
        pass

    return {
        "ok": True,
        "action": "accepted",
        "loan_id": loan_id,
        "amount": amount,
        "new_balance": new_balance,
    }


async def cancel_loan(uid: int, chat_id: int, loan_id: int) -> dict:
    """Cancel a pending outgoing loan (lender cancels).

    Raises ValueError on error.
    Returns {ok, action}.
    """
    from database.postgres import connect as postgres_connect

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT id FROM mora_loans "
            "WHERE id=? AND lender_id=? AND chat_id=? AND status='pending' AND repaid_at IS NULL",
            (loan_id, uid, chat_id),
        ) as c:
            loan = await c.fetchone()
        if not loan:
            raise ValueError("Заявка не найдена или уже обработана")

        now = datetime.now(timezone.utc)
        await db.execute(
            "UPDATE mora_loans SET status='cancelled', repaid_at=? WHERE id=?",
            (now, loan_id),
        )
        await db.commit()

    return {"ok": True, "action": "cancelled"}
