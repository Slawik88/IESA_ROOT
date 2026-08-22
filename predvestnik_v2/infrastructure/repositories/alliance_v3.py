"""Durable shadow contributions for Alliance v3; no wallet dependencies."""
from __future__ import annotations

import json


async def ensure_table(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS alliance_v3_shadow_contributions (
            id BIGSERIAL PRIMARY KEY,
            terminal_result_id TEXT NOT NULL UNIQUE,
            user_id BIGINT NOT NULL,
            run_id BIGINT NOT NULL UNIQUE,
            policy_version TEXT NOT NULL,
            outcome TEXT NOT NULL,
            requested_signals INTEGER NOT NULL,
            accepted_signals INTEGER NOT NULL,
            reason TEXT NOT NULL,
            decision_json TEXT NOT NULL,
            settled BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (requested_signals >= 0),
            CHECK (accepted_signals >= 0),
            CHECK (settled = FALSE)
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_alliance_v3_user_time "
        "ON alliance_v3_shadow_contributions(user_id, policy_version, created_at DESC)"
    )
    await db.commit()


async def get(db, terminal_result_id: str) -> dict | None:
    async with db.execute(
        "SELECT decision_json FROM alliance_v3_shadow_contributions WHERE terminal_result_id = ?",
        (terminal_result_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return json.loads(row[0]) if row else None


async def personal_totals(db, user_id: int, policy_version: str) -> tuple[int, int]:
    async with db.execute(
        "SELECT "
        "COALESCE(SUM(accepted_signals) FILTER (WHERE created_at >= CURRENT_DATE), 0), "
        "COALESCE(SUM(accepted_signals) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days'), 0) "
        "FROM alliance_v3_shadow_contributions WHERE user_id = ? AND policy_version = ?",
        (int(user_id), policy_version),
    ) as cursor:
        row = await cursor.fetchone()
    return (int(row[0]), int(row[1])) if row else (0, 0)


async def save(
    db, *, terminal_result_id: str, user_id: int, run_id: int,
    policy_version: str, outcome: str, decision: dict,
) -> dict:
    payload = json.dumps(decision, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    async with db.execute(
        "INSERT INTO alliance_v3_shadow_contributions "
        "(terminal_result_id,user_id,run_id,policy_version,outcome,requested_signals,"
        "accepted_signals,reason,decision_json) VALUES (?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT (terminal_result_id) DO NOTHING RETURNING id",
        (
            terminal_result_id, int(user_id), int(run_id), policy_version, outcome,
            int(decision["requested"]), int(decision["accepted"]), decision["reason"], payload,
        ),
    ) as cursor:
        inserted = await cursor.fetchone()
    if inserted:
        return decision
    existing = await get(db, terminal_result_id)
    if existing != decision:
        raise RuntimeError("Alliance shadow idempotency conflict.")
    return existing
