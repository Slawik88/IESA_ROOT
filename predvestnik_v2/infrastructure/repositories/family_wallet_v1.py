"""Schema and migration primitives for the append-only family wallet.

There are deliberately no public transfer writers in this module yet.  The
schema is introduced separately so historical balances can be reconciled before
any money-moving endpoint is un-frozen.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Any
from uuid import uuid4

from core.economy_contract import (
    IdempotencyConflict,
    InvalidEconomicMutation,
    InsufficientBalance,
    as_ledger_amount,
    validate_idempotency_key,
)
from infrastructure.repositories.economy_ledger import apply_balance_change
from infrastructure.repositories.marriage_integrity import (
    audit_family_migration_readiness,
    migration_is_safe,
)


@dataclass(frozen=True, slots=True)
class FamilyTransfer:
    operation_id: str
    marriage_id: int
    currency: str
    amount: Decimal
    action: str
    applied: bool


class FamilyTransferIntentError(InvalidEconomicMutation):
    """A Telegram transfer-choice card is expired, foreign, or already spent."""


_BALANCE_COLUMNS = {
    "mora": "mora",
    "diamonds": "diamonds",
    "dark_mora": "dark_mora",
    "zarniki": "zarniki",
}


def _fingerprint(*, action: str, currency: str, amount: Decimal) -> str:
    payload = json.dumps(
        {"action": action, "currency": currency, "amount": str(amount)},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def transfer_between_personal_and_family(
    db: Any,
    *,
    actor_id: int,
    currency: str,
    amount: int | float | Decimal,
    action: str,
    idempotency_key: str,
) -> FamilyTransfer:
    """Move one currency between the caller and their current family custody.

    The marriage is always resolved from the server-side membership table;
    callers cannot choose a family id.  The outer transaction contains both
    ledger legs and both balance projections, including the only permitted
    positive-Zarniki path (a prior family withdrawal ledger row).
    """
    if currency not in _BALANCE_COLUMNS:
        raise InvalidEconomicMutation("Unknown family wallet currency.")
    if action not in {"deposit", "withdrawal"}:
        raise InvalidEconomicMutation("Family wallet action must be deposit or withdrawal.")
    normalized_amount = as_ledger_amount(amount)
    if normalized_amount <= 0:
        raise InvalidEconomicMutation("Family wallet amount must be positive.")
    if currency == "zarniki" and normalized_amount != normalized_amount.to_integral_value():
        raise InvalidEconomicMutation("Zarniki transfers must use a whole amount.")
    key = validate_idempotency_key(idempotency_key)
    fingerprint = _fingerprint(action=action, currency=currency, amount=normalized_amount)

    async with db.connection.transaction():
        async with db.execute(
            "SELECT marriage_id FROM marriage_members WHERE user_id = ? FOR SHARE",
            (actor_id,),
        ) as cursor:
            member = await cursor.fetchone()
        if not member:
            raise InvalidEconomicMutation("You are not in an active family.")
        marriage_id = int(member[0])

        await db.execute(
            "INSERT INTO family_wallet_balances (marriage_id) VALUES (?) ON CONFLICT DO NOTHING",
            (marriage_id,),
        )
        async with db.execute(
            "SELECT mora, diamonds, dark_mora, zarniki FROM family_wallet_balances "
            "WHERE marriage_id = ? FOR UPDATE",
            (marriage_id,),
        ) as cursor:
            balance_row = await cursor.fetchone()
        if not balance_row:
            raise RuntimeError("Family wallet balance row is missing.")
        before = {name: as_ledger_amount(balance_row[index]) for index, name in enumerate(_BALANCE_COLUMNS)}

        async with db.execute(
            "SELECT id, request_fingerprint, action, currency FROM family_wallet_operations "
            "WHERE marriage_id = ? AND actor_id = ? AND idempotency_key = ?",
            (marriage_id, actor_id, key),
        ) as cursor:
            replay = await cursor.fetchone()
        if replay:
            if str(replay[1]) != fingerprint or str(replay[2]) != action or str(replay[3]) != currency:
                raise IdempotencyConflict("Family wallet idempotency key is bound to a different transfer.")
            return FamilyTransfer(
                operation_id=str(replay[0]), marriage_id=marriage_id, currency=currency,
                amount=normalized_amount, action=action, applied=False,
            )

        if action == "withdrawal" and before[currency] < normalized_amount:
            raise InsufficientBalance("Insufficient family wallet balance.")
        after = dict(before)
        family_delta = normalized_amount if action == "deposit" else -normalized_amount
        after[currency] = as_ledger_amount(before[currency] + family_delta)
        operation_id = f"family:{uuid4().hex}"
        await db.execute(
            "INSERT INTO family_wallet_operations "
            "(id, marriage_id, actor_id, action, currency, idempotency_key, request_fingerprint, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?::jsonb)",
            (operation_id, marriage_id, actor_id, action, currency, key, fingerprint,
             json.dumps({"currency": currency, "amount": str(normalized_amount)}, separators=(",", ":"))),
        )
        await db.execute(
            "INSERT INTO family_wallet_ledger "
            "(operation_id, marriage_id, currency, delta, balance_before, balance_after) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (operation_id, marriage_id, currency, family_delta, before[currency], after[currency]),
        )
        column = _BALANCE_COLUMNS[currency]
        await db.execute(
            f"UPDATE family_wallet_balances SET {column} = ?, updated_at = NOW() WHERE marriage_id = ?",
            (after[currency], marriage_id),
        )
        legacy_column = {
            "mora": "family_balance",
            "diamonds": "family_balance_diamonds",
            "dark_mora": "family_balance_dark_mora",
            "zarniki": "family_balance_zarniki",
        }[currency]
        await db.execute(
            f"UPDATE marriages SET {legacy_column} = ? WHERE id = ?",
            (float(after[currency]), marriage_id),
        )

        personal_delta = -normalized_amount if action == "deposit" else normalized_amount
        personal = await apply_balance_change(
            db, actor_id, {currency: personal_delta},
            reason_code=f"family_transfer_{action}",
            idempotency_key=f"family:{key}",
            source_type="family_wallet",
            reference_type="family_operation",
            reference_id=operation_id,
            metadata={"family_operation_id": operation_id, "marriage_id": marriage_id},
            target_id=marriage_id,
            note=action,
            allow_custody_zarniki_credit=(currency == "zarniki" and action == "withdrawal"),
        )
        await db.execute(
            "UPDATE family_wallet_ledger SET source_personal_operation_id = ? WHERE operation_id = ?",
            (personal.operation_id, operation_id),
        )
    return FamilyTransfer(
        operation_id=operation_id, marriage_id=marriage_id, currency=currency,
        amount=normalized_amount, action=action, applied=True,
    )


async def create_telegram_transfer_intent(
    db: Any,
    *,
    actor_id: int,
    action: str,
    amount: int | float | Decimal,
) -> str:
    """Create a short-lived, server-bound choice card for the Telegram adapter.

    Currency intentionally is not selected yet.  Every button on one card
    shares this intent, so tapping two different currency buttons cannot create
    two transfers.  The active marriage is resolved here and again on consume.
    """
    if action not in {"deposit", "withdrawal"}:
        raise InvalidEconomicMutation("Family wallet action must be deposit or withdrawal.")
    normalized_amount = as_ledger_amount(amount)
    if normalized_amount <= 0:
        raise InvalidEconomicMutation("Family wallet amount must be positive.")
    intent_id = uuid4().hex
    async with db.connection.transaction():
        async with db.execute(
            "SELECT marriage_id FROM marriage_members WHERE user_id = ? FOR SHARE",
            (actor_id,),
        ) as cursor:
            member = await cursor.fetchone()
        if not member:
            raise FamilyTransferIntentError("You are not in an active family.")
        await db.execute(
            "INSERT INTO family_wallet_telegram_intents "
            "(id, actor_id, marriage_id, action, amount, expires_at) "
            "VALUES (?, ?, ?, ?, ?, NOW() + INTERVAL '10 minutes')",
            (intent_id, actor_id, int(member[0]), action, normalized_amount),
        )
    return intent_id


async def consume_telegram_transfer_intent(
    db: Any,
    *,
    intent_id: str,
    actor_id: int,
    currency: str,
) -> FamilyTransfer:
    """Consume one Telegram intent and execute its exact transfer once.

    The intent row is locked through the nested family/personal ledger work.
    Thus two callback deliveries serialize: the second gets the already stored
    operation instead of a second debit.  Failure rolls back the claim, letting
    the player retry while the card is still valid.
    """
    if currency not in _BALANCE_COLUMNS:
        raise InvalidEconomicMutation("Unknown family wallet currency.")
    async with db.connection.transaction():
        async with db.execute(
            "SELECT actor_id, marriage_id, action, amount, expires_at, consumed_operation_id "
            "FROM family_wallet_telegram_intents WHERE id = ? FOR UPDATE",
            (str(intent_id),),
        ) as cursor:
            intent = await cursor.fetchone()
        if not intent:
            raise FamilyTransferIntentError("Перевод не найден. Откройте выбор валюты заново.")
        if int(intent[0]) != int(actor_id):
            raise FamilyTransferIntentError("Этот перевод создан для другого игрока.")
        if intent[5]:
            return FamilyTransfer(
                operation_id=str(intent[5]), marriage_id=int(intent[1]), currency=currency,
                amount=as_ledger_amount(intent[3]), action=str(intent[2]), applied=False,
            )
        async with db.execute(
            "SELECT 1 FROM family_wallet_telegram_intents WHERE id = ? AND expires_at > NOW()",
            (str(intent_id),),
        ) as cursor:
            if not await cursor.fetchone():
                raise FamilyTransferIntentError("Время выбора истекло. Откройте перевод заново.")
        result = await transfer_between_personal_and_family(
            db, actor_id=actor_id, currency=currency, amount=intent[3],
            action=str(intent[2]), idempotency_key=f"telegram-family:{intent_id}",
        )
        if result.marriage_id != int(intent[1]):
            raise FamilyTransferIntentError("Семейный статус изменился. Откройте перевод заново.")
        await db.execute(
            "UPDATE family_wallet_telegram_intents SET consumed_operation_id = ? "
            "WHERE id = ? AND consumed_operation_id IS NULL",
            (result.operation_id, str(intent_id)),
        )
        return result


async def install_family_wallet_schema(db: Any) -> None:
    """Create custody tables and import one immutable opening balance per family.

    Must run in an operator-controlled transaction.  The preflight guarantees
    that float legacy values are neither negative nor non-finite before their
    single conversion to NUMERIC(24, 6).
    """
    # The membership migration owns ``ended_at``.  Historic closed families
    # can legitimately share a former player with their later active family;
    # only active ownership blocks custody setup.
    audit = await audit_family_migration_readiness(db, active_only=True)
    if not migration_is_safe(audit):
        raise RuntimeError(f"family wallet migration blocked: {audit}")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS family_wallet_balances (
            marriage_id BIGINT PRIMARY KEY REFERENCES marriages(id) ON DELETE RESTRICT,
            mora NUMERIC(24, 6) NOT NULL DEFAULT 0 CHECK (mora >= 0),
            diamonds NUMERIC(24, 6) NOT NULL DEFAULT 0 CHECK (diamonds >= 0),
            dark_mora NUMERIC(24, 6) NOT NULL DEFAULT 0 CHECK (dark_mora >= 0),
            zarniki NUMERIC(24, 6) NOT NULL DEFAULT 0 CHECK (zarniki >= 0 AND zarniki = TRUNC(zarniki)),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS family_wallet_operations (
            id TEXT PRIMARY KEY,
            marriage_id BIGINT NOT NULL REFERENCES marriages(id) ON DELETE RESTRICT,
            actor_id BIGINT,
            action TEXT NOT NULL CHECK (action IN ('legacy_opening_balance', 'deposit', 'withdrawal', 'refund_clawback')),
            currency TEXT NOT NULL DEFAULT 'mora' CHECK (currency IN ('mora', 'diamonds', 'dark_mora', 'zarniki')),
            idempotency_key TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (marriage_id, actor_id, idempotency_key)
        )
    """)
    await db.execute(
        "ALTER TABLE family_wallet_operations ADD COLUMN IF NOT EXISTS currency TEXT "
        "NOT NULL DEFAULT 'mora' CHECK (currency IN ('mora', 'diamonds', 'dark_mora', 'zarniki'))"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS family_wallet_ledger (
            id BIGSERIAL PRIMARY KEY,
            operation_id TEXT NOT NULL REFERENCES family_wallet_operations(id) ON DELETE RESTRICT,
            marriage_id BIGINT NOT NULL REFERENCES marriages(id) ON DELETE RESTRICT,
            currency TEXT NOT NULL CHECK (currency IN ('mora', 'diamonds', 'dark_mora', 'zarniki')),
            delta NUMERIC(24, 6) NOT NULL CHECK (delta <> 0),
            balance_before NUMERIC(24, 6) NOT NULL CHECK (balance_before >= 0),
            balance_after NUMERIC(24, 6) NOT NULL CHECK (balance_after >= 0 AND balance_after = balance_before + delta),
            source_personal_operation_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (operation_id, currency)
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_family_wallet_ledger_marriage_created "
        "ON family_wallet_ledger (marriage_id, created_at DESC)"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS family_wallet_telegram_intents (
            id TEXT PRIMARY KEY,
            actor_id BIGINT NOT NULL,
            marriage_id BIGINT NOT NULL REFERENCES marriages(id) ON DELETE RESTRICT,
            action TEXT NOT NULL CHECK (action IN ('deposit', 'withdrawal')),
            amount NUMERIC(24, 6) NOT NULL CHECK (amount > 0),
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_operation_id TEXT NULL REFERENCES family_wallet_operations(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_family_wallet_intents_actor_expiry "
        "ON family_wallet_telegram_intents (actor_id, expires_at DESC)"
    )
    await db.execute(
        "INSERT INTO family_wallet_balances (marriage_id, mora, diamonds, dark_mora, zarniki) "
        "SELECT id, family_balance::numeric(24, 6), "
        "COALESCE(family_balance_diamonds, 0)::numeric(24, 6), "
        "COALESCE(family_balance_dark_mora, 0)::numeric(24, 6), "
        "COALESCE(family_balance_zarniki, 0)::numeric(24, 6) FROM marriages "
        "ON CONFLICT (marriage_id) DO NOTHING"
    )
    await db.execute(
        "INSERT INTO family_wallet_operations "
        "(id, marriage_id, actor_id, action, currency, idempotency_key, request_fingerprint, metadata_json) "
        "SELECT 'legacy-family-opening:' || id, id, NULL, 'legacy_opening_balance', 'mora', "
        "'legacy-opening-v1', 'legacy-opening-v1:' || id, "
        "'{\"provenance\":\"legacy_unattributed\"}'::jsonb FROM marriages "
        "ON CONFLICT (id) DO NOTHING"
    )
    await db.execute("""
        INSERT INTO family_wallet_ledger
            (operation_id, marriage_id, currency, delta, balance_before, balance_after, source_personal_operation_id)
        SELECT 'legacy-family-opening:' || id, id, currency, amount, 0, amount, NULL
        FROM (
            SELECT id, 'mora'::text AS currency, family_balance::numeric(24, 6) AS amount FROM marriages
            UNION ALL SELECT id, 'diamonds', COALESCE(family_balance_diamonds, 0)::numeric(24, 6) FROM marriages
            UNION ALL SELECT id, 'dark_mora', COALESCE(family_balance_dark_mora, 0)::numeric(24, 6) FROM marriages
            UNION ALL SELECT id, 'zarniki', COALESCE(family_balance_zarniki, 0)::numeric(24, 6) FROM marriages
        ) opening WHERE amount <> 0
        ON CONFLICT (operation_id, currency) DO NOTHING
    """)
