#!/usr/bin/env python3
"""PostgreSQL proof for atomic, retry-safe paid profile-theme purchases.

Run with ``THEME_TEST_DATABASE_URL`` pointing at an isolated local database.
The test creates and drops only its own random schema; it never touches the
application schema or a production connection.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import secrets
import sys

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.economy_contract import IdempotencyConflict  # noqa: E402
from infrastructure.pg_adapter import PGAdapter  # noqa: E402
from infrastructure.repositories.economy_ledger import ensure_tables  # noqa: E402
from services import themes as theme_service  # noqa: E402


THEMES = {
    "theme_zarniki": {"name": "Проверочная заря", "source": "zarniki", "price_zarniki": 440},
    "theme_dark": {"name": "Проверочная тень", "source": "dark", "price_dark": 100},
}


async def _rows(db: PGAdapter, query: str, args=()):
    async with db.execute(query, args) as cursor:
        return await cursor.fetchall()


async def _value(db: PGAdapter, query: str, args=()):
    rows = await _rows(db, query, args)
    return rows[0][0] if rows else None


async def _create_schema(connection: asyncpg.Connection, schema: str) -> None:
    await connection.execute(f'CREATE SCHEMA "{schema}"')
    await connection.execute(f'SET search_path TO "{schema}"')
    await connection.execute("""
        CREATE TABLE users (
            user_tg_id BIGINT PRIMARY KEY,
            user_balance_mora NUMERIC(24, 6) NOT NULL DEFAULT 0,
            user_balance_diamonds NUMERIC(24, 6) NOT NULL DEFAULT 0,
            user_balance_dark_mora NUMERIC(24, 6) NOT NULL DEFAULT 0,
            user_balance_zarniki NUMERIC(24, 6) NOT NULL DEFAULT 0
        )
    """)
    await connection.execute("""
        CREATE TABLE user_themes (
            user_id BIGINT NOT NULL,
            theme_id TEXT NOT NULL,
            PRIMARY KEY (user_id, theme_id)
        )
    """)
    await connection.execute("""
        CREATE TABLE wallet_log (
            id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, chat_id BIGINT,
            delta_mora NUMERIC(24, 6) NOT NULL DEFAULT 0,
            delta_diamonds NUMERIC(24, 6) NOT NULL DEFAULT 0,
            delta_dark_mora NUMERIC(24, 6) NOT NULL DEFAULT 0,
            delta_zarniki NUMERIC(24, 6) NOT NULL DEFAULT 0,
            balance_mora_after NUMERIC(24, 6) NOT NULL DEFAULT 0,
            balance_diamonds_after NUMERIC(24, 6) NOT NULL DEFAULT 0,
            balance_dark_mora_after NUMERIC(24, 6) NOT NULL DEFAULT 0,
            balance_zarniki_after NUMERIC(24, 6) NOT NULL DEFAULT 0,
            source TEXT NOT NULL, target_id BIGINT, note TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    await ensure_tables(PGAdapter(connection))


async def _seed(db: PGAdapter, user_id: int, *, zarniki: int = 1_000, dark: int = 0) -> None:
    await db.execute(
        "INSERT INTO users (user_tg_id, user_balance_zarniki, user_balance_dark_mora) VALUES (?, ?, ?)",
        (user_id, zarniki, dark),
    )


async def _success_replay_and_conflict(db: PGAdapter) -> None:
    await _seed(db, 101)
    first = await theme_service.purchase_direct_theme(
        db, 101, "theme_zarniki", idempotency_key="theme-test-success"
    )
    assert first.applied and not first.replayed and not first.already_owned
    assert await _value(db, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (101,)) == 560
    assert await _value(db, "SELECT COUNT(*) FROM user_themes WHERE user_id = ?", (101,)) == 1
    assert await _value(db, "SELECT COUNT(*) FROM economic_operations WHERE user_id = ?", (101,)) == 1
    assert await _value(db, "SELECT COUNT(*) FROM economic_ledger WHERE user_id = ?", (101,)) == 1
    assert await _value(db, "SELECT COUNT(*) FROM wallet_log WHERE user_id = ?", (101,)) == 1

    replay = await theme_service.purchase_direct_theme(
        db, 101, "theme_zarniki", idempotency_key="theme-test-success"
    )
    assert replay.replayed and not replay.applied
    assert await _value(db, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (101,)) == 560
    assert await _value(db, "SELECT COUNT(*) FROM economic_operations WHERE user_id = ?", (101,)) == 1

    try:
        await theme_service.purchase_direct_theme(
            db, 101, "theme_dark", idempotency_key="theme-test-success"
        )
    except theme_service.ThemePurchaseError as error:
        assert "другой покупки" in str(error)
    else:
        raise AssertionError("A key must not be reusable for another theme.")


async def _parallel_claim(first: PGAdapter, second: PGAdapter) -> None:
    await _seed(first, 202)
    gate = asyncio.Event()

    async def buy(db: PGAdapter, key: str):
        await gate.wait()
        return await theme_service.purchase_direct_theme(db, 202, "theme_zarniki", idempotency_key=key)

    a = asyncio.create_task(buy(first, "theme-test-parallel-a"))
    b = asyncio.create_task(buy(second, "theme-test-parallel-b"))
    gate.set()
    results = await asyncio.gather(a, b)
    assert sum(result.applied for result in results) == 1, results
    assert sum(result.already_owned for result in results) == 1, results
    assert await _value(first, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (202,)) == 560
    assert await _value(first, "SELECT COUNT(*) FROM user_themes WHERE user_id = ?", (202,)) == 1
    assert await _value(first, "SELECT COUNT(*) FROM economic_operations WHERE user_id = ?", (202,)) == 1


async def _rollback_after_claim(db: PGAdapter) -> None:
    await _seed(db, 303)
    original = theme_service.apply_balance_change

    async def fail_after_claim(*_args, **_kwargs):
        raise RuntimeError("injected ledger failure")

    theme_service.apply_balance_change = fail_after_claim
    try:
        try:
            await theme_service.purchase_direct_theme(
                db, 303, "theme_zarniki", idempotency_key="theme-test-claim-failure"
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("Injected debit failure must escape the service.")
    finally:
        theme_service.apply_balance_change = original

    assert await _value(db, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (303,)) == 1000
    assert await _value(db, "SELECT COUNT(*) FROM user_themes WHERE user_id = ?", (303,)) == 0
    assert await _value(db, "SELECT COUNT(*) FROM economic_operations WHERE user_id = ?", (303,)) == 0


async def _rollback_after_ledger_write(db: PGAdapter) -> None:
    await _seed(db, 404)
    await db.connection.execute(
        "ALTER TABLE wallet_log ADD CONSTRAINT reject_theme_wallet "
        "CHECK (user_id <> 404)"
    )
    try:
        await theme_service.purchase_direct_theme(
            db, 404, "theme_zarniki", idempotency_key="theme-test-wallet-failure"
        )
    except Exception:
        pass
    else:
        raise AssertionError("Injected wallet projection failure must escape the service.")

    assert await _value(db, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (404,)) == 1000
    assert await _value(db, "SELECT COUNT(*) FROM user_themes WHERE user_id = ?", (404,)) == 0
    assert await _value(db, "SELECT COUNT(*) FROM economic_operations WHERE user_id = ?", (404,)) == 0
    assert await _value(db, "SELECT COUNT(*) FROM economic_ledger WHERE user_id = ?", (404,)) == 0


async def main() -> None:
    database_url = os.environ.get("THEME_TEST_DATABASE_URL")
    if not database_url:
        print("SKIP: set THEME_TEST_DATABASE_URL to run PostgreSQL theme-purchase integration")
        return
    schema = f"theme_purchase_test_{secrets.token_hex(8)}"
    first_connection = await asyncpg.connect(database_url)
    second_connection = await asyncpg.connect(database_url)
    original_get = theme_service.get_effective_theme

    async def fixture_theme(_db, theme_id: str):
        theme = THEMES.get(theme_id)
        return dict(theme) if theme else None

    theme_service.get_effective_theme = fixture_theme
    try:
        await _create_schema(first_connection, schema)
        await second_connection.execute(f'SET search_path TO "{schema}"')
        first, second = PGAdapter(first_connection), PGAdapter(second_connection)
        await _success_replay_and_conflict(first)
        await _parallel_claim(first, second)
        await _rollback_after_claim(first)
        await _rollback_after_ledger_write(first)
    finally:
        theme_service.get_effective_theme = original_get
        await second_connection.close()
        await first_connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await first_connection.close()
    print("OK: theme purchase is atomic, replay-safe, race-safe, and rollback-safe")


if __name__ == "__main__":
    asyncio.run(main())
