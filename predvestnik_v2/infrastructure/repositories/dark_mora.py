"""Spend-only compatibility repository for archived Dark Mora balances."""
from datetime import datetime, timezone
import math

from core.economy_contract import IdempotencyConflict, InsufficientBalance
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.economy_ledger import apply_balance_change


async def get_dark_mora_balance(db: PGAdapter, user_id: int) -> float:
    await db.execute(
        "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user_id,)
    )
    async with db.execute(
        "SELECT COALESCE(user_balance_dark_mora, 0) FROM users WHERE user_tg_id = ?",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    return float(row[0]) if row else 0.0


async def add_dark_mora(
    db: PGAdapter, user_id: int, amount: float, source: str,
    note: str | None = None, *, idempotency_key: str | None = None,
):
    """Compatibility writer: only spend/correction downward remains allowed."""
    if amount > 0:
        raise ValueError("Новые начисления Тёмной Моры закрыты правилами экономики v3.")
    if not math.isfinite(amount) or amount == 0:
        return None
    return await apply_balance_change(
        db, user_id, {"dark_mora": amount}, reason_code=source,
        idempotency_key=idempotency_key, source_type="legacy_archive",
        reference_type="dark_mora_spend", reference_id=note or source,
        note=note,
    )


async def spend_dark_mora(
    db: PGAdapter, user_id: int, amount: float, source: str,
    note: str | None = None, *, idempotency_key: str | None = None,
) -> tuple[bool, str]:
    """Spend an existing archive balance through the canonical ledger."""
    if not math.isfinite(amount) or amount <= 0:
        return False, "Некорректная сумма."
    try:
        mutation = await apply_balance_change(
            db, user_id, {"dark_mora": -amount}, reason_code=source,
            idempotency_key=idempotency_key, source_type="legacy_archive",
            reference_type="dark_mora_spend", reference_id=note or source,
            note=note,
        )
        if not mutation.applied:
            return True, "Эта покупка уже была обработана."
        return True, ""
    except InsufficientBalance:
        balance = await get_dark_mora_balance(db, user_id)
        return False, f"Недостаточно Тёмной Моры ({balance:.0f} < {amount:.0f})."
    except IdempotencyConflict:
        return False, "Этот ключ запроса уже использован для другой покупки."
    except ValueError as e:
        return False, str(e)
    except Exception:
        return False, "Операция не выполнена. Баланс не изменён."


async def get_cooldown(db: PGAdapter, user_id: int, action: str) -> datetime | None:
    """Returns when the cooldown expires, or None if no cooldown."""
    async with db.execute(
        "SELECT available_from FROM dark_mora_cooldowns WHERE user_id = ? AND action = ?",
        (user_id, action),
    ) as c:
        row = await c.fetchone()
    if not row:
        return None
    val = row[0]
    if isinstance(val, str):
        val = datetime.strptime(val[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    elif val.tzinfo is None:
        val = val.replace(tzinfo=timezone.utc)
    return val


async def set_cooldown(db: PGAdapter, user_id: int, action: str, available_from: datetime):
    await db.execute(
        "INSERT INTO dark_mora_cooldowns (user_id, action, available_from) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, action) DO UPDATE SET available_from = EXCLUDED.available_from",
        (user_id, action, available_from.strftime("%Y-%m-%d %H:%M:%S")),
    )
