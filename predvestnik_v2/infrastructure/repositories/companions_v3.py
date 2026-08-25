"""Isolated persistence for Reconstruction 3.0 companions.

The legacy ``pets`` and ``active_expeditions`` tables are read, never rewritten.
New role/Bond state lives in companion-v3 tables so cutover remains reversible.
"""
from __future__ import annotations

import json
from typing import Any


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS companion_v3_profiles (
            user_id             BIGINT PRIMARY KEY,
            active_pet_id       BIGINT NULL,
            selected_role_id    TEXT NULL,
            unlocked_roles_json TEXT NOT NULL DEFAULT '[]',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS companion_v3_bond (
            user_id          BIGINT NOT NULL,
            pet_id           BIGINT NOT NULL,
            bond_points      INTEGER NOT NULL DEFAULT 0 CHECK (bond_points >= 0),
            care_bank        INTEGER NOT NULL DEFAULT 1 CHECK (care_bank BETWEEN 0 AND 7),
            bank_updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_care_action TEXT NULL,
            last_care_at     TIMESTAMPTZ NULL,
            PRIMARY KEY (user_id, pet_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS companion_v3_actions (
            user_id       BIGINT NOT NULL,
            action_id     TEXT NOT NULL,
            action_type   TEXT NOT NULL,
            request_json  TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, action_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS companion_v3_expeditions (
            id             BIGSERIAL PRIMARY KEY,
            user_id        BIGINT NOT NULL,
            pet_id         BIGINT NOT NULL,
            duration_hours INTEGER NOT NULL CHECK (duration_hours IN (2, 6, 12)),
            route_id       TEXT NOT NULL,
            fixed_mora     INTEGER NOT NULL CHECK (fixed_mora >= 0),
            seed_digest    TEXT NOT NULL,
            discovery_id   TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'active',
            starts_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ends_at        TIMESTAMPTZ NOT NULL,
            claimed_at     TIMESTAMPTZ NULL,
            settled        BOOLEAN NOT NULL DEFAULT FALSE,
            CHECK (status IN ('active', 'ready', 'claimed', 'cancelled')),
            CHECK (settled = FALSE)
        )
    """)
    await db.execute(
        "ALTER TABLE companion_v3_expeditions ADD COLUMN IF NOT EXISTS "
        "discovery_id TEXT NOT NULL DEFAULT 'unassigned'"
    )
    await db.execute(
        "ALTER TABLE companion_v3_expeditions ADD COLUMN IF NOT EXISTS "
        "settled BOOLEAN NOT NULL DEFAULT FALSE"
    )
    await db.execute(
        "ALTER TABLE companion_v3_expeditions ALTER COLUMN status SET DEFAULT 'active'"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_companion_v3_expeditions_user_status "
        "ON companion_v3_expeditions(user_id, status, ends_at)"
    )
    await db.commit()


async def lock_user(db, user_id: int) -> None:
    async with db.execute("SELECT pg_advisory_xact_lock(?)", (int(user_id),)) as cursor:
        await cursor.fetchone()


async def list_owned_pets(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT id, name, species_id, rarity, placement, fatigue, "
        "COALESCE(pet_level,1) AS legacy_level, "
        "COALESCE(duplicates_collected,0) AS legacy_duplicates, "
        "COALESCE(copy_index,1) AS copy_index, created_at "
        "FROM pets WHERE owner_id = ? ORDER BY "
        "CASE placement WHEN 'active' THEN 0 WHEN 'passive' THEN 1 ELSE 2 END, "
        "created_at, id",
        (int(user_id),),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_owned_pet(db, user_id: int, pet_id: int) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT id, name, species_id, rarity, placement, fatigue, "
        "COALESCE(pet_level,1) AS legacy_level, "
        "COALESCE(duplicates_collected,0) AS legacy_duplicates, "
        "COALESCE(copy_index,1) AS copy_index, created_at "
        "FROM pets WHERE owner_id = ? AND id = ?",
        (int(user_id), int(pet_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_profile(db, user_id: int) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM companion_v3_profiles WHERE user_id = ?", (int(user_id),)
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return None
    data = dict(row)
    data["unlocked_roles"] = json.loads(data.pop("unlocked_roles_json") or "[]")
    return data


async def ensure_profile(db, user_id: int, default_pet_id: int | None) -> dict[str, Any]:
    await db.execute(
        "INSERT INTO companion_v3_profiles (user_id, active_pet_id) VALUES (?, ?) "
        "ON CONFLICT (user_id) DO NOTHING",
        (int(user_id), default_pet_id),
    )
    profile = await get_profile(db, user_id)
    if not profile:
        raise RuntimeError("Не удалось создать профиль спутника.")
    return profile


async def count_meaningful_days(db, user_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(DISTINCT (created_at AT TIME ZONE 'UTC')::date) "
        "FROM economy_shadow_rewards WHERE user_id = ? AND eligible = TRUE",
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def save_profile_roles(
    db, user_id: int, *, selected_role_id: str, unlocked_roles: list[str]
) -> None:
    await db.execute(
        "UPDATE companion_v3_profiles SET selected_role_id = ?, unlocked_roles_json = ?, "
        "updated_at = NOW() WHERE user_id = ?",
        (
            selected_role_id,
            json.dumps(unlocked_roles, ensure_ascii=False, separators=(",", ":")),
            int(user_id),
        ),
    )


async def save_active_pet(db, user_id: int, pet_id: int) -> None:
    await db.execute(
        "UPDATE companion_v3_profiles SET active_pet_id = ?, updated_at = NOW() "
        "WHERE user_id = ?",
        (int(pet_id), int(user_id)),
    )


async def list_bond_states(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT *, NOW() AS server_now FROM companion_v3_bond WHERE user_id = ?",
        (int(user_id),),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_bond_state(db, user_id: int, pet_id: int) -> dict[str, Any]:
    await db.execute(
        "INSERT INTO companion_v3_bond (user_id, pet_id) VALUES (?, ?) "
        "ON CONFLICT (user_id, pet_id) DO NOTHING",
        (int(user_id), int(pet_id)),
    )
    async with db.execute(
        "SELECT *, NOW() AS server_now FROM companion_v3_bond "
        "WHERE user_id = ? AND pet_id = ? FOR UPDATE",
        (int(user_id), int(pet_id)),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("Не удалось создать Bond питомца.")
    return dict(row)


async def save_care(
    db, user_id: int, pet_id: int, *, bond_points: int, care_bank: int,
    bank_updated_at, action: str,
) -> None:
    await db.execute(
        "UPDATE companion_v3_bond SET bond_points = ?, care_bank = ?, "
        "bank_updated_at = ?, last_care_action = ?, last_care_at = NOW() "
        "WHERE user_id = ? AND pet_id = ?",
        (bond_points, care_bank, bank_updated_at, action, int(user_id), int(pet_id)),
    )


async def get_cached_action(db, user_id: int, action_id: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT request_json, response_json FROM companion_v3_actions "
        "WHERE user_id = ? AND action_id = ?",
        (int(user_id), action_id),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return None
    return {"request": json.loads(row[0]), "response": json.loads(row[1])}


async def save_action(
    db, user_id: int, action_id: str, action_type: str,
    request: dict[str, Any], response: dict[str, Any],
) -> None:
    await db.execute(
        "INSERT INTO companion_v3_actions "
        "(user_id, action_id, action_type, request_json, response_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            int(user_id), action_id, action_type,
            json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        ),
    )


async def list_legacy_expeditions(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT e.pet_id, e.duration_hours, e.ends_at, COALESCE(e.early_finish,FALSE) AS early_finish, "
        "p.name AS pet_name, p.species_id, "
        "CAST(EXTRACT(EPOCH FROM (e.ends_at - NOW())) AS BIGINT) AS remaining_sec "
        "FROM active_expeditions e JOIN pets p ON p.id = e.pet_id "
        "WHERE p.owner_id = ? ORDER BY e.ends_at",
        (int(user_id),),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def has_second_expedition_slot(db, user_id: int, game_version: str, encounter_id: str) -> bool:
    async with db.execute(
        "SELECT completed_json FROM gameplay_progress WHERE user_id = ? AND game_version = ?",
        (int(user_id), game_version),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return False
    try:
        return encounter_id in json.loads(row[0] or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


async def list_expeditions(db, user_id: int) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT id, pet_id, duration_hours, route_id, fixed_mora, discovery_id, "
        "CASE WHEN status = 'active' AND ends_at <= NOW() THEN 'ready' ELSE status END AS status, "
        "starts_at, ends_at, claimed_at, "
        "CAST(EXTRACT(EPOCH FROM (ends_at - NOW())) AS BIGINT) AS remaining_sec "
        "FROM companion_v3_expeditions WHERE user_id = ? "
        "AND (status IN ('active','ready') OR "
        "(status = 'claimed' AND claimed_at >= NOW() - INTERVAL '7 days')) "
        "ORDER BY CASE status WHEN 'ready' THEN 0 WHEN 'active' THEN 1 ELSE 2 END, ends_at DESC",
        (int(user_id),),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def count_open_expeditions(db, user_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM companion_v3_expeditions "
        "WHERE user_id = ? AND status IN ('active','ready')",
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def pet_has_open_expedition(db, user_id: int, pet_id: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM companion_v3_expeditions WHERE user_id = ? AND pet_id = ? "
        "AND status IN ('active','ready') LIMIT 1",
        (int(user_id), int(pet_id)),
    ) as cursor:
        return await cursor.fetchone() is not None


async def reserved_mora_last_7_days(db, user_id: int) -> int:
    async with db.execute(
        "SELECT COALESCE(SUM(fixed_mora),0) FROM companion_v3_expeditions "
        "WHERE user_id = ? AND ((status IN ('active','ready')) OR "
        "(status = 'claimed' AND claimed_at >= NOW() - INTERVAL '7 days'))",
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def create_expedition(
    db, *, user_id: int, pet_id: int, duration_hours: int, route_id: str,
    fixed_mora: int, seed_digest: str, discovery_id: str,
) -> dict[str, Any]:
    async with db.execute(
        "INSERT INTO companion_v3_expeditions "
        "(user_id, pet_id, duration_hours, route_id, fixed_mora, seed_digest, discovery_id, ends_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NOW() + (? * INTERVAL '1 hour')) "
        "RETURNING id, starts_at, ends_at",
        (
            int(user_id), int(pet_id), int(duration_hours), route_id, int(fixed_mora),
            seed_digest, discovery_id, int(duration_hours),
        ),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        raise RuntimeError("Не удалось зафиксировать поход.")
    return dict(row)


async def mark_ready_and_claim(db, user_id: int) -> list[dict[str, Any]]:
    await db.execute(
        "UPDATE companion_v3_expeditions SET status = 'ready' "
        "WHERE user_id = ? AND status = 'active' AND ends_at <= NOW()",
        (int(user_id),),
    )
    async with db.execute(
        "UPDATE companion_v3_expeditions SET status = 'claimed', claimed_at = NOW() "
        "WHERE user_id = ? AND status = 'ready' "
        "RETURNING id, pet_id, duration_hours, route_id, fixed_mora, discovery_id, claimed_at",
        (int(user_id),),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]
