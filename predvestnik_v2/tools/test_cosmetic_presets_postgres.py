#!/usr/bin/env python3
"""PostgreSQL integration contract for saved-look serialization.

Run with ``COSMETIC_TEST_DATABASE_URL`` pointing at an isolated local database.
The test creates and drops its own schema; it never uses an application schema
or production credentials.
"""
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys

import asyncpg
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.pg_adapter import PGAdapter, _pg_sql  # noqa: E402
from services.cosmetics import apply_preset, equip, save_preset  # noqa: E402


TITLE_A = "cos_title_forest_wanderer"
TITLE_B = "cos_title_thicket_child"
FRAME_A = "cos_avatar_frame_oak"
BACKGROUND_A = "cos_profile_bg_forest"


async def _exec(adapter: PGAdapter, sql: str, args=()):
    """Run a statement through the same adapter used by bot and FastAPI."""
    await adapter.execute(sql, args)


async def _rows(adapter: PGAdapter, sql: str, args=()):
    async with adapter.execute(sql, args) as cursor:
        return await cursor.fetchall()


async def _seed_owned(adapter: PGAdapter, user_id: int) -> None:
    for cosmetic_id in (TITLE_A, TITLE_B, FRAME_A, BACKGROUND_A):
        await _exec(
            adapter,
            "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?)",
            (user_id, cosmetic_id),
        )


async def _create_schema(connection: asyncpg.Connection, schema: str) -> None:
    await connection.execute(f'CREATE SCHEMA "{schema}"')
    await connection.execute(f'SET search_path TO "{schema}"')
    await connection.execute(
        "CREATE TABLE users (user_tg_id BIGINT PRIMARY KEY)"
    )
    await connection.execute(
        "CREATE TABLE user_cosmetics ("
        "user_id BIGINT NOT NULL, cosmetic_id TEXT NOT NULL, "
        "PRIMARY KEY (user_id, cosmetic_id))"
    )
    await connection.execute(
        "CREATE TABLE user_cosmetic_loadout ("
        "user_id BIGINT NOT NULL, slot TEXT NOT NULL, cosmetic_id TEXT NOT NULL, "
        "PRIMARY KEY (user_id, slot))"
    )
    await connection.execute(
        "CREATE TABLE cosmetic_presets ("
        "id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, name TEXT NOT NULL, "
        "loadout TEXT NOT NULL, created_at TIMESTAMP DEFAULT NOW())"
    )


async def _save_race(first: PGAdapter, second: PGAdapter) -> None:
    """Two adapters at four presets may produce exactly one fifth preset."""
    user_id = 700_001
    await _seed_owned(first, user_id)
    for index in range(4):
        await _exec(
            first,
            "INSERT INTO cosmetic_presets (user_id, name, loadout) VALUES (?, ?, ?)",
            (user_id, f"Старый {index}", "{}"),
        )
    gate = asyncio.Event()

    async def save(adapter: PGAdapter, name: str):
        await gate.wait()
        return await save_preset(adapter, user_id, name)

    first_task = asyncio.create_task(save(first, "Пятый A"))
    second_task = asyncio.create_task(save(second, "Пятый B"))
    gate.set()
    outcomes = await asyncio.gather(first_task, second_task)
    assert sum(ok for ok, _, _ in outcomes) == 1, outcomes
    assert sum(not ok for ok, _, _ in outcomes) == 1, outcomes
    rows = await _rows(first, "SELECT id FROM cosmetic_presets WHERE user_id = ?", (user_id,))
    assert len(rows) == 5, rows


async def _apply_equip_race(first: PGAdapter, second: PGAdapter) -> None:
    """Apply is an all-or-nothing replacement even beside a concurrent equip."""
    user_id = 700_002
    await _seed_owned(first, user_id)
    await _exec(
        first,
        "INSERT INTO user_cosmetic_loadout (user_id, slot, cosmetic_id) VALUES (?, ?, ?)",
        (user_id, "title", TITLE_A),
    )
    await _exec(
        first,
        "INSERT INTO user_cosmetic_loadout (user_id, slot, cosmetic_id) VALUES (?, ?, ?)",
        (user_id, "profile_bg", BACKGROUND_A),
    )
    async with first.execute(
        "INSERT INTO cosmetic_presets (user_id, name, loadout) VALUES (?, ?, ?) RETURNING id",
        (user_id, "Только титул", json.dumps({"title": TITLE_B})),
    ) as cursor:
        (preset_id,) = await cursor.fetchone()

    gate = asyncio.Event()

    async def apply():
        await gate.wait()
        return await apply_preset(first, user_id, preset_id)

    async def put_on_frame():
        await gate.wait()
        return await equip(second, user_id, FRAME_A)

    apply_task = asyncio.create_task(apply())
    equip_task = asyncio.create_task(put_on_frame())
    gate.set()
    apply_result, equip_result = await asyncio.gather(apply_task, equip_task)
    assert apply_result[0] and equip_result[0], (apply_result, equip_result)
    rows = await _rows(
        first,
        "SELECT slot, cosmetic_id FROM user_cosmetic_loadout WHERE user_id = ? ORDER BY slot",
        (user_id,),
    )
    loadout = dict(rows)
    assert loadout.get("title") == TITLE_B, loadout
    assert "profile_bg" not in loadout, loadout
    assert set(loadout).issubset({"title", "avatar_frame"}), loadout


async def _apply_rolls_back(first: PGAdapter) -> None:
    """A failed target insert must restore every old wearable slot."""
    user_id = 700_003
    await _seed_owned(first, user_id)
    for slot, cosmetic_id in (("title", TITLE_A), ("profile_bg", BACKGROUND_A)):
        await _exec(
            first,
            "INSERT INTO user_cosmetic_loadout (user_id, slot, cosmetic_id) VALUES (?, ?, ?)",
            (user_id, slot, cosmetic_id),
        )
    async with first.execute(
        "INSERT INTO cosmetic_presets (user_id, name, loadout) VALUES (?, ?, ?) RETURNING id",
        (user_id, "Ошибка записи", json.dumps({"title": TITLE_B, "avatar_frame": FRAME_A})),
    ) as cursor:
        (preset_id,) = await cursor.fetchone()
    await first.connection.execute(
        "ALTER TABLE user_cosmetic_loadout "
        "ADD CONSTRAINT reject_frame "
        f"CHECK (user_id <> {user_id} OR slot <> 'avatar_frame')"
    )
    logger.disable("infrastructure.pg_adapter")
    try:
        try:
            await apply_preset(first, user_id, preset_id)
        except asyncpg.CheckViolationError:
            pass
        else:
            raise AssertionError("the forced write fault must propagate")
    finally:
        logger.enable("infrastructure.pg_adapter")
    rows = await _rows(
        first,
        "SELECT slot, cosmetic_id FROM user_cosmetic_loadout WHERE user_id = ? ORDER BY slot",
        (user_id,),
    )
    assert dict(rows) == {"profile_bg": BACKGROUND_A, "title": TITLE_A}, rows


async def main() -> None:
    database_url = os.environ.get("COSMETIC_TEST_DATABASE_URL")
    if not database_url:
        print("SKIP: set COSMETIC_TEST_DATABASE_URL to run PostgreSQL cosmetic integration")
        return
    assert _pg_sql("VALUES (?, ?, ?, ?, ?, ?, ?)") == (
        "VALUES ($1, $2, $3, $4, $5, $6, $7)"
    )
    schema = f"cosmetic_preset_test_{secrets.token_hex(8)}"
    first_connection = await asyncpg.connect(database_url)
    second_connection = await asyncpg.connect(database_url)
    try:
        await _create_schema(first_connection, schema)
        await second_connection.execute(f'SET search_path TO "{schema}"')
        first, second = PGAdapter(first_connection), PGAdapter(second_connection)
        await _save_race(first, second)
        await _apply_equip_race(first, second)
        await _apply_rolls_back(first)
    finally:
        await second_connection.close()
        await first_connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await first_connection.close()
    print("OK: PostgreSQL preset locking, rollback and placeholder contract")


if __name__ == "__main__":
    asyncio.run(main())
