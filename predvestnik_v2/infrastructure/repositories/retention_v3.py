"""Persistence for the optional daily Rhythm contract."""
from __future__ import annotations

import json
from datetime import date
from typing import Any


def _date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reconstruction_daily_contracts (
            user_id              BIGINT NOT NULL,
            game_version         TEXT NOT NULL,
            day_key              DATE NOT NULL,
            offer_ids_json       TEXT NOT NULL,
            selected_contract_id TEXT NULL,
            progress             INTEGER NOT NULL DEFAULT 0,
            target               INTEGER NULL,
            completed            BOOLEAN NOT NULL DEFAULT FALSE,
            selected_at          TIMESTAMPTZ NULL,
            completed_at         TIMESTAMPTZ NULL,
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, game_version, day_key)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reconstruction_contract_contributions (
            user_id       BIGINT NOT NULL,
            game_version  TEXT NOT NULL,
            day_key       DATE NOT NULL,
            run_id        BIGINT NOT NULL,
            contract_id   TEXT NOT NULL,
            delta         INTEGER NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, game_version, run_id)
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_reconstruction_contract_days "
        "ON reconstruction_daily_contracts(user_id, day_key DESC)"
    )
    await db.commit()


def _decode(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    data["offer_ids"] = json.loads(data.pop("offer_ids_json") or "[]")
    data["day_key"] = str(data["day_key"])
    data["completed"] = bool(data["completed"])
    return data


async def get_day(db, user_id: int, game_version: str, day_key: str) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM reconstruction_daily_contracts "
        "WHERE user_id = ? AND game_version = ? AND day_key = ?",
        (int(user_id), game_version, _date(day_key)),
    ) as cursor:
        return _decode(await cursor.fetchone())


async def ensure_day(
    db, user_id: int, game_version: str, day_key: str, offer_ids: list[str]
) -> dict[str, Any]:
    await db.execute(
        "INSERT INTO reconstruction_daily_contracts "
        "(user_id, game_version, day_key, offer_ids_json) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (user_id, game_version, day_key) DO NOTHING",
        (int(user_id), game_version, _date(day_key), json.dumps(offer_ids, separators=(",", ":"))),
    )
    row = await get_day(db, user_id, game_version, day_key)
    if not row:
        raise RuntimeError("Failed to create daily contract board")
    return row


async def select_contract(
    db, user_id: int, game_version: str, day_key: str, contract_id: str, target: int
) -> dict[str, Any] | None:
    async with db.execute(
        "UPDATE reconstruction_daily_contracts SET "
        "selected_contract_id = ?, target = ?, selected_at = COALESCE(selected_at, NOW()), "
        "updated_at = NOW() WHERE user_id = ? AND game_version = ? AND day_key = ? "
        "AND (selected_contract_id IS NULL OR selected_contract_id = ?) RETURNING *",
        (contract_id, int(target), int(user_id), game_version, _date(day_key), contract_id),
    ) as cursor:
        return _decode(await cursor.fetchone())


async def record_contribution(
    db,
    *,
    user_id: int,
    game_version: str,
    day_key: str,
    run_id: int,
    contract_id: str,
    delta: int,
) -> bool:
    async with db.execute(
        "INSERT INTO reconstruction_contract_contributions "
        "(user_id, game_version, day_key, run_id, contract_id, delta) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING RETURNING run_id",
        (int(user_id), game_version, _date(day_key), int(run_id), contract_id, int(delta)),
    ) as cursor:
        return (await cursor.fetchone()) is not None


async def add_progress(
    db, user_id: int, game_version: str, day_key: str, delta: int
) -> dict[str, Any] | None:
    async with db.execute(
        "UPDATE reconstruction_daily_contracts SET "
        "progress = LEAST(target, progress + ?), "
        "completed = (progress + ? >= target), "
        "completed_at = CASE WHEN progress + ? >= target THEN COALESCE(completed_at, NOW()) ELSE completed_at END, "
        "updated_at = NOW() WHERE user_id = ? AND game_version = ? AND day_key = ? "
        "AND selected_contract_id IS NOT NULL AND completed = FALSE RETURNING *",
        (int(delta), int(delta), int(delta), int(user_id), game_version, _date(day_key)),
    ) as cursor:
        return _decode(await cursor.fetchone())


async def count_completed_since(
    db, user_id: int, game_version: str, since_day_key: str
) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM reconstruction_daily_contracts "
        "WHERE user_id = ? AND game_version = ? AND day_key >= ? AND completed = TRUE",
        (int(user_id), game_version, _date(since_day_key)),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def count_completed_total(db, user_id: int, game_version: str) -> int:
    """Count distinct meaningful dates without imposing a streak."""
    async with db.execute(
        "SELECT COUNT(*) FROM reconstruction_daily_contracts "
        "WHERE user_id = ? AND game_version = ? AND completed = TRUE",
        (int(user_id), game_version),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def count_completed_total_all_versions(db, user_id: int) -> int:
    """Count durable completed dates once even when a game version changes."""
    async with db.execute(
        "SELECT COUNT(DISTINCT day_key) FROM reconstruction_daily_contracts "
        "WHERE user_id = ? AND completed = TRUE",
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0
