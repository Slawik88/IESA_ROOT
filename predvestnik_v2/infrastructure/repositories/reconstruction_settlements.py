"""Immutable receipt boundary for a future real Reconstruction reward settlement.

The table is deliberately separate from ``economy_shadow_rewards``: a shadow
decision is evidence and must remain wallet-free forever, while a committed
receipt links one terminal result to exactly one ledger operation and one XP
bundle.  The service does not call this repository while the build gate remains
shadow-only.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def canonical_json(value: Mapping[str, Any]) -> str:
    """Stable JSON used both for audit storage and replay-conflict detection."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def receipt_fingerprint(
    *,
    terminal_result_id: str,
    user_id: int,
    run_id: int,
    policy_version: str,
    difficulty_snapshot: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> str:
    payload = canonical_json({
        "terminal_result_id": terminal_result_id,
        "user_id": int(user_id),
        "run_id": int(run_id),
        "policy_version": policy_version,
        "difficulty_snapshot": difficulty_snapshot,
        "decision": decision,
    })
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def ensure_table(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reconstruction_reward_settlements (
            terminal_result_id       TEXT PRIMARY KEY,
            run_id                   BIGINT NOT NULL UNIQUE,
            user_id                  BIGINT NOT NULL,
            game_version             TEXT NOT NULL,
            balance_version          TEXT NOT NULL,
            policy_version           TEXT NOT NULL,
            difficulty_profile_id    TEXT NOT NULL,
            difficulty_policy_version TEXT NOT NULL,
            difficulty_snapshot_json JSONB NOT NULL,
            decision_json            JSONB NOT NULL,
            receipt_fingerprint      TEXT NOT NULL UNIQUE,
            status                   TEXT NOT NULL DEFAULT 'pending'
                                     CHECK (status IN ('pending', 'settled')),
            ledger_operation_id      TEXT UNIQUE NULL,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            settled_at               TIMESTAMPTZ NULL,
            CHECK ((status = 'pending' AND ledger_operation_id IS NULL)
                OR (status = 'settled' AND ledger_operation_id IS NOT NULL))
        )
    """)
    # A unique terminal reference protects against a future accidental second
    # writer with another idempotency key.  Refuse a dirty legacy database before
    # DDL rather than letting CREATE INDEX abort the shared startup transaction.
    async with db.execute(
        "SELECT user_id, reference_id, COUNT(*) AS duplicate_count "
        "FROM economic_operations WHERE reference_type = 'reconstruction_terminal' "
        "GROUP BY user_id, reference_id HAVING COUNT(*) > 1 LIMIT 1"
    ) as cursor:
        duplicate = await cursor.fetchone()
    if duplicate:
        raise RuntimeError(
            "Reconstruction settlement preflight found duplicate terminal ledger references."
        )
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS economic_operations_reconstruction_terminal_unique
            ON economic_operations (user_id, reference_type, reference_id)
            WHERE reference_type = 'reconstruction_terminal'
    """)
    await db.commit()


async def create_or_get_receipt(
    db,
    *,
    terminal_result_id: str,
    user_id: int,
    run_id: int,
    game_version: str,
    balance_version: str,
    policy_version: str,
    difficulty_profile_id: str,
    difficulty_policy_version: str,
    difficulty_snapshot: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Insert an immutable pending receipt or return its exact replay.

    The caller must already hold the player lock and an outer transaction.  A
    conflicting retry is a safety failure, never an invitation to recompute
    money from a mutable content manifest.
    """
    if not terminal_result_id or run_id < 1 or user_id < 1:
        raise ValueError("Settlement receipt identity is invalid.")
    fingerprint = receipt_fingerprint(
        terminal_result_id=terminal_result_id,
        user_id=user_id,
        run_id=run_id,
        policy_version=policy_version,
        difficulty_snapshot=difficulty_snapshot,
        decision=decision,
    )
    snapshot_json = canonical_json(difficulty_snapshot)
    decision_json = canonical_json(decision)
    async with db.execute(
        "INSERT INTO reconstruction_reward_settlements "
        "(terminal_result_id, run_id, user_id, game_version, balance_version, policy_version, "
        " difficulty_profile_id, difficulty_policy_version, difficulty_snapshot_json, "
        " decision_json, receipt_fingerprint) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?) "
        "ON CONFLICT (terminal_result_id) DO NOTHING RETURNING terminal_result_id",
        (
            terminal_result_id, int(run_id), int(user_id), game_version, balance_version,
            policy_version, difficulty_profile_id, difficulty_policy_version, snapshot_json,
            decision_json, fingerprint,
        ),
    ) as cursor:
        inserted = await cursor.fetchone()
    async with db.execute(
        "SELECT terminal_result_id, run_id, user_id, policy_version, receipt_fingerprint, "
        "status, ledger_operation_id FROM reconstruction_reward_settlements "
        "WHERE terminal_result_id = ? FOR UPDATE",
        (terminal_result_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("Settlement receipt disappeared after insert.")
    result = dict(row)
    expected = (int(run_id), int(user_id), policy_version, fingerprint)
    actual = (
        int(result["run_id"]), int(result["user_id"]),
        str(result["policy_version"]), str(result["receipt_fingerprint"]),
    )
    if actual != expected:
        raise RuntimeError("Settlement receipt idempotency conflict.")
    result["created"] = bool(inserted)
    return result


async def mark_settled(
    db,
    *,
    terminal_result_id: str,
    ledger_operation_id: str,
) -> dict[str, Any]:
    """Attach the one ledger operation after the XP bundle has succeeded."""
    if not terminal_result_id or not ledger_operation_id:
        raise ValueError("Settlement receipt identity is invalid.")
    async with db.execute(
        "UPDATE reconstruction_reward_settlements SET status = 'settled', "
        "ledger_operation_id = ?, settled_at = NOW() "
        "WHERE terminal_result_id = ? AND status = 'pending' "
        "RETURNING status, ledger_operation_id",
        (ledger_operation_id, terminal_result_id),
    ) as cursor:
        row = await cursor.fetchone()
    if row:
        return {"status": row[0], "ledger_operation_id": row[1], "applied": True}
    async with db.execute(
        "SELECT status, ledger_operation_id FROM reconstruction_reward_settlements "
        "WHERE terminal_result_id = ?",
        (terminal_result_id,),
    ) as cursor:
        replay = await cursor.fetchone()
    if not replay or replay[0] != "settled" or replay[1] != ledger_operation_id:
        raise RuntimeError("Settlement receipt cannot be marked with a different ledger operation.")
    return {"status": replay[0], "ledger_operation_id": replay[1], "applied": False}
