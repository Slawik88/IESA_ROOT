#!/usr/bin/env python3
"""Loopback PostgreSQL proof for atomic player-coin creation."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.economy_contract import IdempotencyConflict, InsufficientBalance
from core.player_exchange_v1 import PlayerExchangePolicyError
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import economy_ledger, player_exchange_v1 as repo, system_flags
from services import player_exchange_v1 as service

SCHEMA = "player_exchange_v1_contract"


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def connect(dsn: str):
    conn = await asyncpg.connect(dsn)
    await conn.execute(f'SET search_path TO "{SCHEMA}"')
    return conn, PGAdapter(conn)


async def prepare(dsn: str):
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
        await conn.execute(f'CREATE SCHEMA "{SCHEMA}"')
        await conn.execute(f'SET search_path TO "{SCHEMA}"')
        await conn.execute("""
            CREATE TABLE users (
                user_tg_id BIGINT PRIMARY KEY,
                user_balance_mora NUMERIC(24,6) NOT NULL DEFAULT 0,
                user_balance_diamonds NUMERIC(24,6) NOT NULL DEFAULT 0,
                user_balance_dark_mora NUMERIC(24,6) NOT NULL DEFAULT 0,
                user_balance_zarniki NUMERIC(24,6) NOT NULL DEFAULT 0
            );
            CREATE TABLE wallet_log (
                id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,chat_id BIGINT,
                delta_mora NUMERIC(24,6) NOT NULL DEFAULT 0,delta_diamonds NUMERIC(24,6) NOT NULL DEFAULT 0,
                delta_dark_mora NUMERIC(24,6) NOT NULL DEFAULT 0,delta_zarniki NUMERIC(24,6) NOT NULL DEFAULT 0,
                balance_mora_after NUMERIC(24,6) NOT NULL DEFAULT 0,balance_diamonds_after NUMERIC(24,6) NOT NULL DEFAULT 0,
                balance_dark_mora_after NUMERIC(24,6) NOT NULL DEFAULT 0,balance_zarniki_after NUMERIC(24,6) NOT NULL DEFAULT 0,
                source TEXT NOT NULL,target_id BIGINT,note TEXT,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE user_reserve (user_id BIGINT PRIMARY KEY,reserved_mora NUMERIC(24,6) NOT NULL DEFAULT 0)
        """)
        db = PGAdapter(conn)
        await economy_ledger.ensure_tables(db)
        await system_flags.ensure_table(db)
        await repo.ensure_tables(db)
        assert await repo.schema_ready(db) is True
        await db.execute("DELETE FROM player_exchange_schema_v1")
        await db.commit()
        assert await repo.schema_ready(db) is False
        await repo.ensure_tables(db)
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (service.FEATURE_FLAG_KEY,))
        await db.execute(
            "INSERT INTO users(user_tg_id,user_balance_mora,user_balance_zarniki) VALUES "
            "(1,100000,10000),(2,100000,10000),(3,100,100),(4,100000,10000),"
            "(5,100000,10000),(6,100000,10000)"
        )
        await db.commit()
    finally:
        await conn.close()


async def create(dsn: str, user: int, name: str, ticker: str, action: str):
    conn, db = await connect(dsn)
    try:
        return await service.create_coin(db, owner_id=user, name=name, ticker=ticker, initial_mora=10000, action_id=action)
    finally:
        await conn.close()


async def main(dsn: str):
    await prepare(dsn)
    first = await create(dsn, 1, "Северная звезда", "STAR", "create-action-0001")
    replay = await create(dsn, 1, "Северная звезда", "STAR", "create-action-0001")
    assert first["id"] == replay["id"] and replay["replayed"] is True
    try:
        await create(dsn, 1, "Другая монета", "OTHER", "create-action-0001")
        raise AssertionError("changed replay was accepted")
    except IdempotencyConflict:
        pass

    results = await asyncio.gather(
        create(dsn, 2, "Лунный свет", "MOON", "create-action-0002"),
        create(dsn, 2, "Солнечный свет", "SUN", "create-action-0003"),
        return_exceptions=True,
    )
    assert sum(not isinstance(item, Exception) for item in results) == 1

    same = await asyncio.gather(
        create(dsn, 5, "Одна операция", "ONCE", "create-action-0005"),
        create(dsn, 5, "Одна операция", "ONCE", "create-action-0005"),
    )
    assert same[0]["id"] == same[1]["id"]

    try:
        await create(dsn, 3, "Бедная монета", "POOR", "create-action-0006")
        raise AssertionError("insufficient balance was accepted")
    except InsufficientBalance:
        pass

    conn, db = await connect(dsn)
    try:
        await db.execute("UPDATE player_coins_v1 SET status='archived' WHERE id=?", (first["id"],))
        await db.commit()
    finally:
        await conn.close()
    try:
        await create(dsn, 4, "Северная звезда", "STAR", "create-action-0007")
        raise AssertionError("archived identifiers were reused")
    except PlayerExchangePolicyError:
        pass

    conn, db = await connect(dsn)
    try:
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key=?", (service.FEATURE_FLAG_KEY,))
        await db.commit()
    finally:
        await conn.close()
    try:
        await create(dsn, 6, "Закрытый рынок", "CLOSE", "create-action-0008")
        raise AssertionError("disabled exchange accepted creation")
    except service.PlayerExchangeUnavailable:
        pass

    conn, _ = await connect(dsn)
    try:
        row = await conn.fetchrow("SELECT user_balance_mora,user_balance_zarniki FROM users WHERE user_tg_id=2")
        assert float(row[0]) == 90000 and float(row[1]) == 8000
        assert await conn.fetchval("SELECT COUNT(*) FROM economic_operations WHERE user_id=2") == 1
        assert await conn.fetchval("SELECT COUNT(*) FROM player_coins_v1 WHERE owner_id=2") == 1
        assert await conn.fetchval("SELECT SUM(available_units) FROM player_coin_accounts_v1 WHERE coin_id=$1", first["id"]) == 1_000_000_000
        assert float(await conn.fetchval("SELECT treasury_mora FROM player_coin_mora_accounts_v1 WHERE coin_id=$1", first["id"])) == 10000
        assert float(await conn.fetchval("SELECT SUM(delta) FROM player_coin_mora_ledger_v1 WHERE coin_id=$1", first["id"])) == 10000
        assert await conn.fetchval("SELECT COUNT(*) FROM economic_operations WHERE user_id=3") == 0
        assert await conn.fetchval("SELECT COUNT(*) FROM economic_operations WHERE user_id=4") == 0
        assert await conn.fetchval("SELECT COUNT(*) FROM economic_operations WHERE user_id=6") == 0
        try:
            await conn.execute("UPDATE player_coin_events_v1 SET event_type='tampered' WHERE coin_id=$1", first["id"])
            raise AssertionError("append-only event was mutable")
        except asyncpg.RaiseError:
            pass
        try:
            await conn.execute("DELETE FROM player_coin_mora_ledger_v1 WHERE coin_id=$1", first["id"])
            raise AssertionError("append-only Mora custody ledger was mutable")
        except asyncpg.RaiseError:
            pass
    finally:
        await conn.close()
    print("PLAYER_EXCHANGE_V1_PG_OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, default="postgresql://postgres:postgres@127.0.0.1:5432/postgres")
    args = parser.parse_args()
    asyncio.run(main(args.dsn))
