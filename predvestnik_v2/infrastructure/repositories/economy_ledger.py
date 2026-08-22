"""Atomic balance mutations and the append-only economic ledger.

``wallet_log`` remains the player-facing history projection.  This repository is
the accounting source of truth for newly migrated operations: the idempotency
gate, balance update, immutable ledger entries and compatibility projection are
committed (or rolled back) together.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Any, Mapping
from uuid import uuid4

from core.economy_contract import (
    CURRENCY_CODES,
    CURRENCY_SPECS,
    IdempotencyConflict,
    InsufficientBalance,
    InvalidEconomicMutation,
    as_ledger_amount,
    normalize_deltas,
    validate_idempotency_key,
    validate_reason_code,
)
from core.economy_v3 import EconomyV3PolicyError, validate_positive_zarniki_source
from infrastructure.repositories.wallet_log import log_wallet


@dataclass(frozen=True, slots=True)
class BalanceMutation:
    operation_id: str
    idempotency_key: str
    applied: bool
    deltas: Mapping[str, Decimal]
    balances_before: Mapping[str, Decimal]
    balances_after: Mapping[str, Decimal]


async def ensure_tables(db) -> None:
    """Create the canonical ledger schema for bot and standalone web startup."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS economic_operations (
            id                  TEXT PRIMARY KEY,
            user_id             BIGINT NOT NULL,
            idempotency_key     TEXT NOT NULL,
            request_fingerprint TEXT NOT NULL,
            reason_code         TEXT NOT NULL,
            source_type         TEXT NOT NULL,
            reference_type      TEXT,
            reference_id        TEXT,
            metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, idempotency_key)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS economic_ledger (
            id             BIGSERIAL PRIMARY KEY,
            operation_id   TEXT NOT NULL REFERENCES economic_operations(id) ON DELETE RESTRICT,
            user_id        BIGINT NOT NULL,
            currency       TEXT NOT NULL CHECK (
                currency IN ('mora', 'diamonds', 'dark_mora', 'zarniki')
            ),
            delta          NUMERIC(24, 6) NOT NULL CHECK (delta <> 0),
            balance_before NUMERIC(24, 6) NOT NULL,
            balance_after  NUMERIC(24, 6) NOT NULL,
            reason_code    TEXT NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (operation_id, user_id, currency),
            CHECK (balance_after = balance_before + delta)
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_economic_ledger_user_created "
        "ON economic_ledger (user_id, created_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_economic_ledger_reason_created "
        "ON economic_ledger (reason_code, created_at DESC)"
    )


def _request_fingerprint(
    *,
    user_id: int,
    reason_code: str,
    source_type: str,
    reference_type: str | None,
    reference_id: str | None,
    deltas: Mapping[str, Decimal],
) -> str:
    payload = {
        "user_id": int(user_id),
        "reason_code": reason_code,
        "source_type": source_type,
        "reference_type": reference_type,
        "reference_id": reference_id,
        "deltas": {code: str(deltas[code]) for code in CURRENCY_CODES if code in deltas},
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _metadata_json(metadata: Mapping[str, Any] | None) -> str:
    if metadata is None:
        return "{}"
    if not isinstance(metadata, Mapping):
        raise InvalidEconomicMutation("metadata must be a mapping.")
    try:
        encoded = json.dumps(
            dict(metadata), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )
    except (TypeError, ValueError) as exc:
        raise InvalidEconomicMutation("metadata is not JSON serializable.") from exc
    if len(encoded.encode("utf-8")) > 8_192:
        raise InvalidEconomicMutation("metadata exceeds 8 KiB.")
    return encoded


def _validate_premium_origin(
    deltas: Mapping[str, Decimal],
    reason_code: str,
) -> None:
    """Prevent free creation of paid currency after owner-v3 reconciliation."""
    if deltas.get("zarniki", Decimal("0")) <= 0:
        return
    try:
        validate_positive_zarniki_source(reason_code)
    except EconomyV3PolicyError as exc:
        raise InvalidEconomicMutation(
            "Положительные Зарники разрешены только из подтверждённой покупки Stars."
        ) from exc


def _row_get(row, key: str, index: int):
    try:
        return row[key]
    except (KeyError, TypeError):
        return row[index]


async def _load_replayed_mutation(
    db,
    *,
    user_id: int,
    idempotency_key: str,
    request_fingerprint: str,
) -> BalanceMutation:
    async with db.execute(
        "SELECT id, request_fingerprint FROM economic_operations "
        "WHERE user_id = ? AND idempotency_key = ?",
        (user_id, idempotency_key),
    ) as cursor:
        operation = await cursor.fetchone()
    if not operation:
        raise RuntimeError("Idempotency conflict without an economic operation row.")

    operation_id = str(_row_get(operation, "id", 0))
    stored_fingerprint = str(_row_get(operation, "request_fingerprint", 1))
    if stored_fingerprint != request_fingerprint:
        raise IdempotencyConflict(
            "The idempotency key is already bound to a different economic mutation."
        )

    async with db.execute(
        "SELECT currency, delta, balance_before, balance_after "
        "FROM economic_ledger WHERE operation_id = ? ORDER BY currency",
        (operation_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    deltas: dict[str, Decimal] = {}
    before: dict[str, Decimal] = {}
    after: dict[str, Decimal] = {}
    for row in rows:
        code = str(_row_get(row, "currency", 0))
        deltas[code] = as_ledger_amount(_row_get(row, "delta", 1))
        before[code] = as_ledger_amount(_row_get(row, "balance_before", 2))
        after[code] = as_ledger_amount(_row_get(row, "balance_after", 3))

    return BalanceMutation(
        operation_id=operation_id,
        idempotency_key=idempotency_key,
        applied=False,
        deltas=deltas,
        balances_before=before,
        balances_after=after,
    )


async def find_balance_replay(
    db,
    user_id: int,
    deltas: Mapping[str, int | float | Decimal],
    *,
    reason_code: str,
    idempotency_key: str,
    source_type: str = "game",
    reference_type: str | None = None,
    reference_id: str | int | None = None,
) -> BalanceMutation | None:
    """Return and validate a prior operation before retry-sensitive prechecks.

    Call this *inside the same user lock* as quotas/inventory checks.  It lets an
    exact HTTP or Telegram retry succeed even when the original operation has
    already consumed the quota or balance being checked.
    """
    normalized = normalize_deltas(deltas)
    if not normalized:
        raise InvalidEconomicMutation("At least one non-zero currency delta is required.")
    reason = validate_reason_code(reason_code)
    _validate_premium_origin(normalized, reason)
    source = validate_reason_code(source_type)
    ref_type = validate_reason_code(reference_type) if reference_type else None
    ref_id = str(reference_id) if reference_id is not None else None
    key = validate_idempotency_key(idempotency_key)
    fingerprint = _request_fingerprint(
        user_id=user_id,
        reason_code=reason,
        source_type=source,
        reference_type=ref_type,
        reference_id=ref_id,
        deltas=normalized,
    )
    async with db.execute(
        "SELECT 1 FROM economic_operations WHERE user_id = ? AND idempotency_key = ?",
        (user_id, key),
    ) as cursor:
        if not await cursor.fetchone():
            return None
    return await _load_replayed_mutation(
        db,
        user_id=user_id,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )


async def find_reference_replay(
    db,
    user_id: int,
    *,
    reason_code: str,
    idempotency_key: str,
    source_type: str,
    reference_type: str,
    reference_id: str | int,
) -> BalanceMutation | None:
    """Find a prior dynamic-price operation by its immutable request identity.

    Bundle prices may depend on ownership at the moment of purchase. Recomputing
    their deltas after a successful request would produce a different amount, so
    retries first verify the stable reason/source/reference tuple and then load
    the original ledger arithmetic.
    """
    reason = validate_reason_code(reason_code)
    source = validate_reason_code(source_type)
    ref_type = validate_reason_code(reference_type)
    ref_id = str(reference_id)
    key = validate_idempotency_key(idempotency_key)
    async with db.execute(
        "SELECT id, request_fingerprint, reason_code, source_type, reference_type, reference_id "
        "FROM economic_operations WHERE user_id = ? AND idempotency_key = ?",
        (user_id, key),
    ) as cursor:
        operation = await cursor.fetchone()
    if not operation:
        return None
    actual = (
        str(_row_get(operation, "reason_code", 2)),
        str(_row_get(operation, "source_type", 3)),
        str(_row_get(operation, "reference_type", 4)),
        str(_row_get(operation, "reference_id", 5)),
    )
    expected = (reason, source, ref_type, ref_id)
    if actual != expected:
        raise IdempotencyConflict(
            "The idempotency key is already bound to a different economic reference."
        )
    return await _load_replayed_mutation(
        db,
        user_id=user_id,
        idempotency_key=key,
        request_fingerprint=str(_row_get(operation, "request_fingerprint", 1)),
    )


async def apply_balance_change(
    db,
    user_id: int,
    deltas: Mapping[str, int | float | Decimal],
    *,
    reason_code: str,
    idempotency_key: str | None = None,
    source_type: str = "game",
    reference_type: str | None = None,
    reference_id: str | int | None = None,
    metadata: Mapping[str, Any] | None = None,
    allow_negative: bool = False,
    chat_id: int | None = None,
    target_id: int | None = None,
    note: str | None = None,
) -> BalanceMutation:
    """Apply a multi-currency mutation exactly once and record its full arithmetic.

    A caller-provided idempotency key protects retries.  Calls without one remain
    backwards compatible: a unique key is generated, so every invocation is a
    distinct operation while still receiving an immutable ledger record.
    """
    normalized = normalize_deltas(deltas)
    if not normalized:
        raise InvalidEconomicMutation("At least one non-zero currency delta is required.")

    reason = validate_reason_code(reason_code)
    _validate_premium_origin(normalized, reason)
    source = validate_reason_code(source_type)
    ref_type = validate_reason_code(reference_type) if reference_type else None
    ref_id = str(reference_id) if reference_id is not None else None
    operation_id = uuid4().hex
    key = validate_idempotency_key(idempotency_key or f"auto:{operation_id}")
    fingerprint = _request_fingerprint(
        user_id=user_id,
        reason_code=reason,
        source_type=source,
        reference_type=ref_type,
        reference_id=ref_id,
        deltas=normalized,
    )
    metadata_json = _metadata_json(metadata)

    async with db.connection.transaction():
        await db.execute(
            "INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING",
            (user_id,),
        )
        async with db.execute(
            "INSERT INTO economic_operations "
            "(id, user_id, idempotency_key, request_fingerprint, reason_code, "
            " source_type, reference_type, reference_id, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb) "
            "ON CONFLICT (user_id, idempotency_key) DO NOTHING RETURNING id",
            (
                operation_id,
                user_id,
                key,
                fingerprint,
                reason,
                source,
                ref_type,
                ref_id,
                metadata_json,
            ),
        ) as cursor:
            inserted = await cursor.fetchone()

        if not inserted:
            return await _load_replayed_mutation(
                db,
                user_id=user_id,
                idempotency_key=key,
                request_fingerprint=fingerprint,
            )

        balance_sql = ", ".join(
            f"COALESCE({CURRENCY_SPECS[code].balance_column}, 0) AS {code}"
            for code in CURRENCY_CODES
        )
        async with db.execute(
            f"SELECT {balance_sql} FROM users WHERE user_tg_id = ? FOR UPDATE",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise RuntimeError("User row disappeared during an economic mutation.")

        before = {
            code: as_ledger_amount(_row_get(row, code, index))
            for index, code in enumerate(CURRENCY_CODES)
        }
        after = dict(before)
        for code, delta in normalized.items():
            after[code] = as_ledger_amount(before[code] + delta)
            if not allow_negative and after[code] < 0:
                spec = CURRENCY_SPECS[code]
                raise InsufficientBalance(f"Недостаточно валюты: {spec.icon} {spec.label}.")

        # Active auction bids are a real liability, not merely a UI badge.
        # Ordinary spends may use only free Mora; auction settlement removes
        # its winning reserve in the same outer transaction before charging.
        if not allow_negative and normalized.get("mora", Decimal("0")) < 0:
            async with db.execute(
                "SELECT COALESCE(reserved_mora, 0) FROM user_reserve WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                reserve_row = await cursor.fetchone()
            reserved_mora = as_ledger_amount(
                _row_get(reserve_row, "reserved_mora", 0) if reserve_row else 0
            )
            if after["mora"] < reserved_mora:
                free_mora = max(Decimal("0"), before["mora"] - reserved_mora)
                raise InsufficientBalance(
                    f"Недостаточно свободной Моры: доступно {free_mora:.2f}, "
                    f"в ставках {reserved_mora:.2f}."
                )

        assignments = ", ".join(
            f"{CURRENCY_SPECS[code].balance_column} = ?" for code in CURRENCY_CODES
        )
        await db.execute(
            f"UPDATE users SET {assignments} WHERE user_tg_id = ?",
            (*[float(after[code]) for code in CURRENCY_CODES], user_id),
        )

        for code, delta in normalized.items():
            await db.execute(
                "INSERT INTO economic_ledger "
                "(operation_id, user_id, currency, delta, balance_before, balance_after, reason_code) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (operation_id, user_id, code, delta, before[code], after[code], reason),
            )

        await log_wallet(
            db,
            user_id,
            delta_mora=float(normalized.get("mora", 0)),
            delta_diamonds=float(normalized.get("diamonds", 0)),
            delta_dark_mora=float(normalized.get("dark_mora", 0)),
            delta_zarniki=float(normalized.get("zarniki", 0)),
            source=reason,
            chat_id=chat_id,
            target_id=target_id,
            note=note,
        )

    return BalanceMutation(
        operation_id=operation_id,
        idempotency_key=key,
        applied=True,
        deltas=dict(normalized),
        balances_before=before,
        balances_after=after,
    )
