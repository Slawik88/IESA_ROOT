"""Durable, non-settleable reward decisions for the owner-v3 economy shadow.

This repository deliberately has no wallet imports.  It records what a run
*would* have earned so balance assumptions can be measured before settlement is
enabled.  A terminal result may have exactly one immutable decision.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


async def ensure_table(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS economy_shadow_rewards (
            id                       BIGSERIAL PRIMARY KEY,
            terminal_result_id       TEXT NOT NULL UNIQUE,
            user_id                  BIGINT NOT NULL,
            run_id                   BIGINT NOT NULL UNIQUE,
            game_version             TEXT NOT NULL,
            balance_version          TEXT NOT NULL,
            policy_version           TEXT NOT NULL,
            outcome                  TEXT NOT NULL,
            run_kind                 TEXT NOT NULL,
            seed_fingerprint         TEXT NOT NULL,
            eligible                 BOOLEAN NOT NULL,
            reason                   TEXT NOT NULL,
            accepted_result_ordinal  INTEGER NULL,
            decision_json            TEXT NOT NULL,
            inputs_json              TEXT NOT NULL,
            settled                  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (settled = FALSE)
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_shadow_rewards_user_window "
        "ON economy_shadow_rewards(user_id, policy_version, created_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_shadow_rewards_seed_loss "
        "ON economy_shadow_rewards(user_id, seed_fingerprint, outcome, created_at DESC)"
    )
    await db.commit()


def seed_fingerprint(game_version: str, encounter_id: str, seed: int) -> str:
    raw = f"{game_version}:{encounter_id}:{int(seed)}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def get_decision(db, terminal_result_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT decision_json FROM economy_shadow_rewards WHERE terminal_result_id = ?",
        (terminal_result_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return json.loads(row[0]) if row else None


async def count_accepted_last_7_days(
    db, user_id: int, policy_version: str
) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM economy_shadow_rewards "
        "WHERE user_id = ? AND policy_version = ? AND eligible = TRUE "
        "AND created_at >= NOW() - INTERVAL '7 days'",
        (int(user_id), policy_version),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def count_same_seed_eligible_losses(
    db, user_id: int, fingerprint: str
) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM economy_shadow_rewards "
        "WHERE user_id = ? AND seed_fingerprint = ? AND outcome = 'lost' "
        "AND eligible = TRUE",
        (int(user_id), fingerprint),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def save_decision(
    db,
    *,
    terminal_result_id: str,
    user_id: int,
    run_id: int,
    game_version: str,
    balance_version: str,
    policy_version: str,
    outcome: str,
    run_kind: str,
    fingerprint: str,
    eligible: bool,
    reason: str,
    accepted_result_ordinal: int | None,
    decision: Mapping[str, Any],
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    decision_json = json.dumps(
        dict(decision), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    inputs_json = json.dumps(
        dict(inputs), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    async with db.execute(
        "INSERT INTO economy_shadow_rewards "
        "(terminal_result_id, user_id, run_id, game_version, balance_version, "
        "policy_version, outcome, run_kind, seed_fingerprint, eligible, reason, "
        "accepted_result_ordinal, decision_json, inputs_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (terminal_result_id) DO NOTHING RETURNING id",
        (
            terminal_result_id, int(user_id), int(run_id), game_version,
            balance_version, policy_version, outcome, run_kind, fingerprint,
            bool(eligible), reason, accepted_result_ordinal, decision_json, inputs_json,
        ),
    ) as cursor:
        inserted = await cursor.fetchone()
    if inserted:
        return dict(decision)
    existing = await get_decision(db, terminal_result_id)
    if existing != dict(decision):
        raise RuntimeError("Shadow reward idempotency conflict.")
    return existing
