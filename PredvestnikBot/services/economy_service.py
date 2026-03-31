"""
Economy service — handles all payment and wallet operations.

Usage:
    from services.economy_service import process_payment
    new_balance = await process_payment(user_id, chat_id, 100, wallet_type="personal")

    # or family wallet:
    new_balance = await process_payment(
        user_id, chat_id, 100, wallet_type="family", description="Покупка в магазине"
    )
"""
from database.db import (
    get_total_family_balance,
    deduct_family_pool,
    log_family_transaction,
)
from .exceptions import NotEnoughMoraError, NotMarriedError


async def process_payment(
    user_id: int,
    chat_id: int,
    amount: int,
    wallet_type: str = "personal",
    description: str = "",
) -> int:
    """Deduct *amount* from the specified wallet.

    Parameters
    ----------
    user_id     : Telegram user id.
    chat_id     : Group chat id (context for family wallet).
    amount      : Amount to deduct (must be > 0).
    wallet_type : ``"personal"`` (default) or ``"family"``.
    description : Optional note logged to family_wallet_log when wallet_type=="family".

    Returns
    -------
    int  New balance after the deduction.

    Raises
    ------
    NotMarriedError      If ``wallet_type=="family"`` but the user has no partner.
    NotEnoughMoraError   If the chosen wallet has insufficient funds.
    """
    if wallet_type == "family":
        total_bal, _my_bal, partner_id = await get_total_family_balance(chat_id, user_id)
        if partner_id is None:
            raise NotMarriedError()
        if total_bal < amount:
            raise NotEnoughMoraError(have=total_bal, need=amount)
        new_total = await deduct_family_pool(chat_id, user_id, partner_id, amount)
        if description:
            await log_family_transaction(chat_id, user_id, "purchase", amount, description)
        return new_total

    # personal wallet
    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (amount, user_id, amount),
        )
        if cursor.rowcount == 0:
            from database.db import get_mora
            mora_row = await get_mora(user_id, chat_id)
            have = mora_row["balance"] if mora_row else 0
            raise NotEnoughMoraError(have=have, need=amount)
        await db.commit()
        async with db.execute(
            "SELECT COALESCE(balance, 0) FROM users WHERE user_id=?",
            (user_id,),
        ) as c:
            row = await c.fetchone()
        new_bal = row[0] if row else 0
    return new_bal
