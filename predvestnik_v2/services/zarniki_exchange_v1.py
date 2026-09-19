"""One authoritative Zarniki exchange writer for HTTP and Telegram."""
from __future__ import annotations

from core.economy_contract import IdempotencyConflict, InsufficientBalance
from core.zarniki_exchange_v1 import DAILY_ZARNIKI_CAP, ZarnikiExchangePolicyError, quote
from infrastructure.repositories import economy_ledger, star_payments_v1, zarniki_exchange_v1 as repo


class ZarnikiExchangeConflict(ZarnikiExchangePolicyError):
    """An exchange is valid in form but forbidden by durable state."""


async def exchange(db, *, user_id: int, zarniki: int, target: str, action_id: str) -> dict:
    """Atomically debit paid currency, credit one target and consume shared quota."""
    action_id = str(action_id or "").strip()
    if not action_id:
        raise ZarnikiExchangePolicyError("Idempotency-Key обязателен.")
    exchange_quote = quote(zarniki=zarniki, target=target)
    currency_delta = {"zarniki": -exchange_quote.zarniki_spent, exchange_quote.target: exchange_quote.amount_received}
    reason = f"zarniki_exchange_{exchange_quote.target}"
    async with db.connection.transaction():
        await repo.lock_user(db, user_id)
        replay = await economy_ledger.find_balance_replay(
            db, user_id, currency_delta, reason_code=reason, idempotency_key=action_id,
            source_type="zarniki_exchange", reference_type="exchange_request", reference_id=action_id,
        )
        if replay:
            return _response(exchange_quote, replay, used_today=None, replayed=True)
        if await star_payments_v1.has_open_premium_hold(db, user_id):
            raise ZarnikiExchangeConflict("Обмен временно недоступен: платёж ожидает ручной проверки.")
        used = await repo.usage_today(db, user_id)
        if used + exchange_quote.zarniki_spent > DAILY_ZARNIKI_CAP:
            raise ZarnikiExchangeConflict(
                f"На сегодня осталось {max(0, DAILY_ZARNIKI_CAP - used)}✨ лимита обмена."
            )
        mutation = await economy_ledger.apply_balance_change(
            db, user_id, currency_delta, reason_code=reason, idempotency_key=action_id,
            source_type="zarniki_exchange", reference_type="exchange_request", reference_id=action_id,
            metadata={
                "policy_version": exchange_quote.policy_version,
                "target": exchange_quote.target,
                "zarniki_spent": exchange_quote.zarniki_spent,
                "amount_received": str(exchange_quote.amount_received),
                "daily_zarniki_cap": DAILY_ZARNIKI_CAP,
                "utc_day": "server-current-date",
                "irreversible_after_delivery": True,
            },
            note=f"✨ {exchange_quote.zarniki_spent} → {exchange_quote.target}",
        )
        used_after = await repo.add_usage_today(db, user_id, exchange_quote.zarniki_spent)
    return _response(exchange_quote, mutation, used_today=used_after, replayed=False)


def _response(exchange_quote, mutation, *, used_today: int | None, replayed: bool) -> dict:
    return {
        "ok": True,
        "idempotent_replay": replayed,
        "operation_id": mutation.operation_id,
        "target": exchange_quote.target,
        "zarniki_spent": exchange_quote.zarniki_spent,
        "amount_received": float(exchange_quote.amount_received),
        "daily_cap": DAILY_ZARNIKI_CAP,
        "used_today": used_today,
        "policy_version": exchange_quote.policy_version,
    }
