"""Durable receipts/state for v1 long-horizon achievements."""
from __future__ import annotations

import json
from typing import Any


def _snapshot_value(value: Any) -> dict[str, Any]:
    """Normalise asyncpg's JSONB decode modes before replay comparison."""
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise RuntimeError("Achievement terminal source snapshot is malformed.")
    return value


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS achievement_v1_metric_receipts (
            user_id BIGINT NOT NULL, family TEXT NOT NULL, source_event_id TEXT NOT NULL,
            source_kind TEXT NOT NULL, source_snapshot JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, family, source_event_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS achievement_v1_active_weeks (
            user_id BIGINT NOT NULL, family TEXT NOT NULL, week_key DATE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, family, week_key)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS achievement_v1_progress (
            user_id BIGINT NOT NULL, family TEXT NOT NULL,
            completed_events INTEGER NOT NULL DEFAULT 0 CHECK(completed_events >= 0),
            active_weeks INTEGER NOT NULL DEFAULT 0 CHECK(active_weeks >= 0),
            level INTEGER NOT NULL DEFAULT 0 CHECK(level BETWEEN 0 AND 40),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, family)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS achievement_v1_reward_receipts (
            user_id BIGINT NOT NULL, family TEXT NOT NULL, level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 40),
            amount_mora BIGINT NOT NULL CHECK(amount_mora > 0), policy_version TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, family, level)
        )
    """)
    await db.execute("""
        CREATE OR REPLACE FUNCTION reject_achievement_v1_receipt_rewrite()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'achievement v1 receipts are append-only'; END;
        $$
    """)
    for table, trigger in (("achievement_v1_metric_receipts", "achievement_v1_metric_receipts_append_only"),
                           ("achievement_v1_active_weeks", "achievement_v1_active_weeks_append_only"),
                           ("achievement_v1_reward_receipts", "achievement_v1_reward_receipts_append_only")):
        await db.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        await db.execute(f"""
            CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_achievement_v1_receipt_rewrite()
        """)


async def lock_user(db, user_id: int) -> None:
    async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as cursor:
        await cursor.fetchone()


async def save_metric_receipt(db, *, user_id: int, family: str, source_event_id: str,
                              source_kind: str, source_snapshot: dict[str, Any]) -> bool:
    encoded = json.dumps(source_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    async with db.execute(
        "INSERT INTO achievement_v1_metric_receipts(user_id,family,source_event_id,source_kind,source_snapshot) "
        "VALUES (?,?,?,?,?::jsonb) ON CONFLICT DO NOTHING RETURNING 1",
        (int(user_id), family, source_event_id, source_kind, encoded),
    ) as cursor:
        inserted = await cursor.fetchone()
    if inserted:
        return True
    async with db.execute(
        "SELECT source_kind,source_snapshot FROM achievement_v1_metric_receipts WHERE user_id=? AND family=? AND source_event_id=?",
        (int(user_id), family, source_event_id),
    ) as cursor:
        row = await cursor.fetchone()
    if not row or str(row[0]) != source_kind or _snapshot_value(row[1]) != source_snapshot:
        raise RuntimeError("Achievement terminal source identity conflict.")
    return False


async def save_active_week(db, *, user_id: int, family: str, week_key) -> bool:
    async with db.execute(
        "INSERT INTO achievement_v1_active_weeks(user_id,family,week_key) VALUES (?,?,?) ON CONFLICT DO NOTHING RETURNING 1",
        (int(user_id), family, week_key),
    ) as cursor:
        return bool(await cursor.fetchone())


async def lock_progress(db, *, user_id: int, family: str) -> dict[str, Any]:
    await db.execute("INSERT INTO achievement_v1_progress(user_id,family) VALUES (?,?) ON CONFLICT DO NOTHING", (int(user_id), family))
    async with db.execute("SELECT * FROM achievement_v1_progress WHERE user_id=? AND family=? FOR UPDATE", (int(user_id), family)) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("Achievement progress row was not created.")
    return dict(row)


async def save_progress(db, *, user_id: int, family: str, completed_events: int, active_weeks: int, level: int) -> None:
    await db.execute(
        "UPDATE achievement_v1_progress SET completed_events=?,active_weeks=?,level=?,updated_at=NOW() WHERE user_id=? AND family=?",
        (int(completed_events), int(active_weeks), int(level), int(user_id), family),
    )


async def reserve_reward(db, *, user_id: int, family: str, level: int, amount_mora: int, policy_version: str) -> bool:
    async with db.execute(
        "INSERT INTO achievement_v1_reward_receipts(user_id,family,level,amount_mora,policy_version) VALUES (?,?,?,?,?) "
        "ON CONFLICT DO NOTHING RETURNING 1",
        (int(user_id), family, int(level), int(amount_mora), policy_version),
    ) as cursor:
        return bool(await cursor.fetchone())


async def list_progress(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute("SELECT * FROM achievement_v1_progress WHERE user_id=? ORDER BY family", (int(user_id),)) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def list_rewards(db, user_id: int) -> dict[tuple[str, int], dict[str, Any]]:
    async with db.execute(
        "SELECT family,level,amount_mora,policy_version FROM achievement_v1_reward_receipts WHERE user_id=?",
        (int(user_id),),
    ) as cursor:
        return {(str(row[0]), int(row[1])): {"amount_mora": int(row[2]), "policy_version": str(row[3])}
                for row in await cursor.fetchall()}
