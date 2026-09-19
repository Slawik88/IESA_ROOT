"""PostgreSQL repository for the 28-day Scar Map."""
from __future__ import annotations

import json
from typing import Any

from core.scar_map_v1 import DURATION_DAYS, POLICY_VERSION


def _dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row else None


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reconstruction_scar_maps_v1 (
            user_id BIGINT NOT NULL,
            cycle_no INTEGER NOT NULL,
            policy_version TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ends_at TIMESTAMPTZ NOT NULL,
            counters_json TEXT NOT NULL DEFAULT '{}',
            encounters_json TEXT NOT NULL DEFAULT '[]',
            completed_at TIMESTAMPTZ NULL,
            archived_at TIMESTAMPTZ NULL,
            PRIMARY KEY (user_id, cycle_no),
            CHECK (cycle_no > 0)
        )
    """)
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_scar_map_v1_active
        ON reconstruction_scar_maps_v1(user_id) WHERE archived_at IS NULL
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reconstruction_scar_map_contributions_v1 (
            user_id BIGINT NOT NULL,
            cycle_no INTEGER NOT NULL,
            trigger_type TEXT NOT NULL,
            reference_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, cycle_no, trigger_type, reference_id),
            FOREIGN KEY (user_id, cycle_no)
              REFERENCES reconstruction_scar_maps_v1(user_id, cycle_no)
        )
    """)
    await db.execute(
        "ALTER TABLE reconstruction_scar_map_contributions_v1 "
        "ADD COLUMN IF NOT EXISTS fingerprint TEXT NOT NULL DEFAULT ''"
    )
    await db.commit()


async def active(db, user_id: int) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM reconstruction_scar_maps_v1 WHERE user_id=? AND archived_at IS NULL",
        (int(user_id),),
    ) as cursor:
        return _dict(await cursor.fetchone())


async def completed_cycles(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT * FROM reconstruction_scar_maps_v1 "
        "WHERE user_id=? AND completed_at IS NOT NULL ORDER BY cycle_no",
        (int(user_id),),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def archive_if_expired(db, user_id: int) -> bool:
    async with db.execute(
        "UPDATE reconstruction_scar_maps_v1 SET archived_at=NOW() "
        "WHERE user_id=? AND archived_at IS NULL AND ends_at<=NOW() RETURNING cycle_no",
        (int(user_id),),
    ) as cursor:
        return bool(await cursor.fetchone())


async def create_cycle(db, user_id: int) -> dict[str, Any]:
    async with db.execute(
        "SELECT COALESCE(MAX(cycle_no),0)+1 FROM reconstruction_scar_maps_v1 WHERE user_id=?",
        (int(user_id),),
    ) as cursor:
        cycle_no = int((await cursor.fetchone())[0])
    async with db.execute(
        "INSERT INTO reconstruction_scar_maps_v1 "
        "(user_id,cycle_no,policy_version,ends_at) "
        "VALUES (?,?,?,NOW()+(? * INTERVAL '1 day')) RETURNING *",
        (int(user_id), cycle_no, POLICY_VERSION, DURATION_DAYS),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("Failed to create Scar Map cycle")
    return dict(row)


def decode_state(row: dict[str, Any]) -> tuple[dict[str, int], set[str]]:
    counters = json.loads(row.get("counters_json") or "{}")
    encounters = set(json.loads(row.get("encounters_json") or "[]"))
    return ({str(k): max(0, int(v or 0)) for k, v in counters.items()}, {str(v) for v in encounters})


async def record_contribution(db, *, user_id: int, cycle_no: int,
                              trigger_type: str, reference_id: str, fingerprint: str) -> bool:
    async with db.execute(
        "INSERT INTO reconstruction_scar_map_contributions_v1 "
        "(user_id,cycle_no,trigger_type,reference_id,fingerprint) VALUES (?,?,?,?,?) "
        "ON CONFLICT DO NOTHING RETURNING reference_id",
        (int(user_id), int(cycle_no), trigger_type, reference_id, fingerprint),
    ) as cursor:
        inserted = await cursor.fetchone()
    if inserted:
        return True
    async with db.execute(
        "SELECT fingerprint FROM reconstruction_scar_map_contributions_v1 "
        "WHERE user_id=? AND cycle_no=? AND trigger_type=? AND reference_id=?",
        (int(user_id), int(cycle_no), trigger_type, reference_id),
    ) as cursor:
        existing = await cursor.fetchone()
    if not existing or str(existing[0]) != fingerprint:
        raise ValueError("Scar Map contribution idempotency conflict")
    return False


async def save_state(db, *, user_id: int, cycle_no: int,
                     counters: dict[str, int], encounters: set[str], completed: bool) -> dict[str, Any]:
    async with db.execute(
        "UPDATE reconstruction_scar_maps_v1 SET counters_json=?,encounters_json=?,"
        "completed_at=CASE WHEN ? THEN COALESCE(completed_at,NOW()) ELSE completed_at END "
        "WHERE user_id=? AND cycle_no=? AND archived_at IS NULL RETURNING *",
        (json.dumps(counters, sort_keys=True, separators=(",", ":")),
         json.dumps(sorted(encounters), separators=(",", ":")), bool(completed),
         int(user_id), int(cycle_no)),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("Scar Map cycle changed during update")
    return dict(row)
