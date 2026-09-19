"""Refund outbox for direct Stars cosmetics; Telegram calls stay outside SQL transactions."""
from __future__ import annotations

import hashlib
from uuid import uuid4

from aiogram.exceptions import TelegramBadRequest

from infrastructure.repositories import reconstruction as lock_repo
from infrastructure.repositories import supporter_cosmetics_v1 as repo


def request_id(order_id: str) -> str:
    return "supporter-refund:" + hashlib.sha256(order_id.encode()).hexdigest()[:32]


async def refund(bot, db, order_id: str) -> dict:
    oid = str(order_id or "").strip().lower()
    if len(oid) != 32 or any(ch not in "0123456789abcdef" for ch in oid):
        raise ValueError("invalid_order_id")
    rid = request_id(oid)
    async with db.connection.transaction():
        row = await repo.get_order(db, oid)
        if not row:
            raise ValueError("unknown_order")
        await lock_repo.lock_user(db, int(row["payer_user_id"]))
        if int(row["beneficiary_user_id"]) != int(row["payer_user_id"]):
            await lock_repo.lock_user(db, int(row["beneficiary_user_id"]))
        if row["status"] == "refunded":
            return {"status": "refunded", "replayed": True, "order_id": oid}
        row, attempt, _ = await repo.prepare_refund(db, order_id=oid, request_id=rid)
        lease_token = uuid4().hex
        if not await repo.acquire_refund_lease(db, attempt["attempt_id"], lease_token):
            return {"status": "refund_pending", "replayed": True, "order_id": oid}
    try:
        await bot.refund_star_payment(
            user_id=int(row["payer_user_id"]),
            telegram_payment_charge_id=str(row["telegram_charge_id"]),
        )
    except TelegramBadRequest as exc:
        # Telegram does not expose stable machine codes for an already-refunded
        # charge. Any post-send BadRequest is therefore ambiguous, never proof
        # that Stars were not moved; transaction history resolves it.
        async with db.connection.transaction():
            await repo.mark_refund_review(db, oid, attempt["attempt_id"],
                                          type(exc).__name__, lease_token, ambiguous=True)
        raise
    except Exception as exc:
        async with db.connection.transaction():
            await repo.mark_refund_review(db, oid, attempt["attempt_id"],
                                          type(exc).__name__, lease_token, ambiguous=True)
        raise
    async with db.connection.transaction():
        current = await repo.get_order(db, oid)
        await lock_repo.lock_user(db, int(current["payer_user_id"]))
        await repo.finalize_refund(db, oid, attempt["attempt_id"], lease_token)
    return {"status": "refunded", "replayed": False, "order_id": oid}


async def reconcile_authoritative_refund(db, *, charge_id: str, user_id: int,
                                         amount: int) -> tuple[dict, bool] | None:
    """Accept only an exact outgoing Telegram-history refund projection."""
    async with db.connection.transaction():
        charge = await repo.get_charge(db, charge_id)
        if not charge:
            return None
        if (int(charge["payer_user_id"]) != int(user_id)
                or int(amount) != -int(charge["stars_amount"])):
            raise RuntimeError("authoritative_refund_contract_conflict")
        await lock_repo.lock_user(db, int(user_id))
        return await repo.confirm_authoritative_refund(db, charge_id=charge_id)
