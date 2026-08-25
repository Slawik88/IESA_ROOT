"""Isolated v3 unit progress; never reads or overwrites legacy ``user_units``."""
from __future__ import annotations

import json
from typing import Any

from core.reconstruction_progression import UNIT_BRANCHES, branch_by_id, unit_progress_view


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reconstruction_unit_progress (
            user_id             BIGINT NOT NULL,
            game_version        TEXT NOT NULL,
            unit_id             TEXT NOT NULL,
            total_xp            BIGINT NOT NULL DEFAULT 0 CHECK (total_xp >= 0),
            branch_choices_json TEXT NOT NULL DEFAULT '{}',
            legacy_mastery      INTEGER NOT NULL DEFAULT 0 CHECK (legacy_mastery >= 0),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, game_version, unit_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reconstruction_unit_xp_events (
            terminal_result_id TEXT NOT NULL,
            unit_id            TEXT NOT NULL,
            user_id            BIGINT NOT NULL,
            game_version       TEXT NOT NULL,
            policy_version     TEXT NOT NULL,
            squad_role         TEXT NOT NULL CHECK (squad_role IN ('lead', 'support')),
            xp_delta           INTEGER NOT NULL CHECK (xp_delta > 0),
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (terminal_result_id, unit_id)
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_reconstruction_unit_xp_user "
        "ON reconstruction_unit_xp_events(user_id, created_at DESC)"
    )
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reconstruction_mastery_proofs (
            user_id             BIGINT NOT NULL,
            game_version        TEXT NOT NULL,
            challenge_id        TEXT NOT NULL,
            terminal_result_id  TEXT NOT NULL,
            encounter_id        TEXT NOT NULL,
            proven_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, game_version, challenge_id),
            UNIQUE (terminal_result_id, challenge_id)
        )
    """)
    await db.commit()


def _decode(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    choices = json.loads(data.pop("branch_choices_json") or "{}")
    return {
        **unit_progress_view(data["unit_id"], int(data["total_xp"]), choices),
        "legacy_mastery": int(data.get("legacy_mastery", 0)),
    }


async def get_progress(
    db, user_id: int, game_version: str, unit_id: str
) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT unit_id, total_xp, branch_choices_json, legacy_mastery "
        "FROM reconstruction_unit_progress "
        "WHERE user_id = ? AND game_version = ? AND unit_id = ?",
        (int(user_id), game_version, unit_id),
    ) as cursor:
        return _decode(await cursor.fetchone())


async def list_progress(db, user_id: int, game_version: str) -> list[dict[str, Any]]:
    async with db.execute(
        "SELECT unit_id, total_xp, branch_choices_json, legacy_mastery "
        "FROM reconstruction_unit_progress WHERE user_id = ? AND game_version = ? "
        "ORDER BY unit_id",
        (int(user_id), game_version),
    ) as cursor:
        rows = await cursor.fetchall()
    return [_decode(row) for row in rows if row]


async def get_mastery_proofs(
    db, user_id: int, game_version: str
) -> dict[str, dict[str, Any]]:
    async with db.execute(
        "SELECT challenge_id, terminal_result_id, encounter_id, proven_at "
        "FROM reconstruction_mastery_proofs "
        "WHERE user_id = ? AND game_version = ? ORDER BY challenge_id",
        (int(user_id), game_version),
    ) as cursor:
        rows = await cursor.fetchall()
    return {
        str(row["challenge_id"]): {
            "terminal_result_id": str(row["terminal_result_id"]),
            "encounter_id": str(row["encounter_id"]),
            "proven_at": row["proven_at"],
        }
        for row in rows
    }


async def record_mastery_proofs(
    db,
    *,
    user_id: int,
    game_version: str,
    terminal_result_id: str,
    encounter_id: str,
    challenge_ids: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    known = {
        str(branch["mastery_challenge"])
        for milestones in UNIT_BRANCHES.values()
        for branches in milestones.values()
        for branch in branches
    }
    unknown = set(challenge_ids) - known
    if unknown:
        raise ValueError(f"Unknown mastery challenge: {sorted(unknown)}")
    for challenge_id in dict.fromkeys(challenge_ids):
        await db.execute(
            "INSERT INTO reconstruction_mastery_proofs "
            "(user_id, game_version, challenge_id, terminal_result_id, encounter_id) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (
                int(user_id), game_version, challenge_id,
                terminal_result_id, encounter_id,
            ),
        )
    return await get_mastery_proofs(db, user_id, game_version)


async def ensure_unit(db, user_id: int, game_version: str, unit_id: str) -> dict[str, Any]:
    # Pure validation rejects unknown/legacy unit identifiers before storage.
    unit_progress_view(unit_id, 0)
    await db.execute(
        "INSERT INTO reconstruction_unit_progress (user_id, game_version, unit_id) "
        "VALUES (?, ?, ?) ON CONFLICT (user_id, game_version, unit_id) DO NOTHING",
        (int(user_id), game_version, unit_id),
    )
    result = await get_progress(db, user_id, game_version, unit_id)
    if result is None:
        raise RuntimeError("Failed to create Reconstruction unit progress.")
    return result


async def apply_xp_once(
    db,
    *,
    terminal_result_id: str,
    user_id: int,
    game_version: str,
    policy_version: str,
    unit_id: str,
    squad_role: str,
    xp_delta: int,
) -> dict[str, Any]:
    """Apply earned XP idempotently; caller must hold the per-user transaction lock."""
    if squad_role not in {"lead", "support"}:
        raise ValueError("squad_role must be lead or support.")
    if isinstance(xp_delta, bool) or not isinstance(xp_delta, int) or xp_delta <= 0:
        raise ValueError("xp_delta must be a positive integer.")
    await ensure_unit(db, user_id, game_version, unit_id)
    async with db.execute(
        "INSERT INTO reconstruction_unit_xp_events "
        "(terminal_result_id, unit_id, user_id, game_version, policy_version, "
        "squad_role, xp_delta) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (terminal_result_id, unit_id) DO NOTHING RETURNING xp_delta",
        (
            terminal_result_id, unit_id, int(user_id), game_version,
            policy_version, squad_role, xp_delta,
        ),
    ) as cursor:
        inserted = await cursor.fetchone()
    if inserted:
        await db.execute(
            "UPDATE reconstruction_unit_progress SET total_xp = total_xp + ?, "
            "updated_at = NOW() WHERE user_id = ? AND game_version = ? AND unit_id = ?",
            (xp_delta, int(user_id), game_version, unit_id),
        )
        applied = True
    else:
        async with db.execute(
            "SELECT user_id, game_version, policy_version, squad_role, xp_delta "
            "FROM reconstruction_unit_xp_events "
            "WHERE terminal_result_id = ? AND unit_id = ?",
            (terminal_result_id, unit_id),
        ) as cursor:
            prior = await cursor.fetchone()
        expected = (int(user_id), game_version, policy_version, squad_role, xp_delta)
        actual = tuple(prior) if prior else None
        if actual != expected:
            raise RuntimeError("Unit XP idempotency conflict.")
        applied = False
    progress = await get_progress(db, user_id, game_version, unit_id)
    if progress is None:
        raise RuntimeError("Unit progress disappeared after XP operation.")
    return {"applied": applied, "progress": progress}


async def choose_branch(
    db,
    *,
    user_id: int,
    game_version: str,
    unit_id: str,
    branch_id: str,
) -> dict[str, Any]:
    """Persist the first free choice after a server-verified mastery challenge."""
    found = branch_by_id(branch_id)
    if not found or found[0] != unit_id:
        raise ValueError("Branch does not belong to this unit.")
    _, level, branch = found
    progress = await ensure_unit(db, user_id, game_version, unit_id)
    existing = progress["branch_choices"].get(str(level))
    if existing == branch_id:
        return {"applied": False, "progress": progress}
    if existing is not None:
        raise ValueError("This milestone already has a branch; use the respec contract.")
    if progress["level"] < level:
        raise ValueError("Branch is locked by unit level.")
    proofs = await get_mastery_proofs(db, user_id, game_version)
    if branch["mastery_challenge"] not in proofs:
        raise ValueError("Required mastery challenge is not proven.")
    choices = {**progress["branch_choices"], str(level): branch_id}
    prior_json = json.dumps(
        progress["branch_choices"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    async with db.execute(
        "UPDATE reconstruction_unit_progress SET branch_choices_json = ?, "
        "updated_at = NOW() WHERE user_id = ? AND game_version = ? AND unit_id = ? "
        "AND branch_choices_json = ? RETURNING branch_choices_json",
        (
            json.dumps(choices, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            int(user_id), game_version, unit_id, prior_json,
        ),
    ) as cursor:
        updated_row = await cursor.fetchone()
    if not updated_row:
        raise RuntimeError("Unit branch choice changed concurrently.")
    updated = await get_progress(db, user_id, game_version, unit_id)
    if updated is None:
        raise RuntimeError("Unit progress disappeared after branch choice.")
    return {"applied": True, "progress": updated}
