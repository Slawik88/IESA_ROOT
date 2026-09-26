#!/usr/bin/env python3
"""Loopback PostgreSQL proof for VIP purchase and daily-reward serialization."""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.economy_contract import InsufficientBalance
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import vip_v2 as vip_repo
from services import vip


SCHEMA = "vip_v2_contract"


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {
        "127.0.0.1", "localhost", "::1",
    }:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def _connect(dsn: str) -> tuple[asyncpg.Connection, PGAdapter]:
    connection = await asyncpg.connect(dsn)
    await connection.execute(f'SET search_path TO "{SCHEMA}"')
    return connection, PGAdapter(connection)


async def _prepare(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
        await connection.execute(f'CREATE SCHEMA "{SCHEMA}"')
        await connection.execute(f'SET search_path TO "{SCHEMA}"')
        await connection.execute(
            """
            CREATE TABLE users (
                user_tg_id BIGINT PRIMARY KEY,
                user_tg_username TEXT,
                user_balance_mora NUMERIC(24,6) NOT NULL DEFAULT 0,
                user_balance_diamonds NUMERIC(24,6) NOT NULL DEFAULT 0,
                user_balance_dark_mora NUMERIC(24,6) NOT NULL DEFAULT 0,
                user_balance_zarniki NUMERIC(24,6) NOT NULL DEFAULT 0
            );
            CREATE TABLE vip_subscriptions (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_tg_id),
                tier TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                last_probnik_at TIMESTAMPTZ,
                expiry_notified BOOLEAN NOT NULL DEFAULT FALSE,
                total_days INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE wallet_log (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT,
                delta_mora NUMERIC(24,6) NOT NULL DEFAULT 0,
                delta_diamonds NUMERIC(24,6) NOT NULL DEFAULT 0,
                delta_dark_mora NUMERIC(24,6) NOT NULL DEFAULT 0,
                delta_zarniki NUMERIC(24,6) NOT NULL DEFAULT 0,
                balance_mora_after NUMERIC(24,6) NOT NULL DEFAULT 0,
                balance_diamonds_after NUMERIC(24,6) NOT NULL DEFAULT 0,
                balance_dark_mora_after NUMERIC(24,6) NOT NULL DEFAULT 0,
                balance_zarniki_after NUMERIC(24,6) NOT NULL DEFAULT 0,
                source TEXT NOT NULL,
                target_id BIGINT,
                note TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE user_reserve (
                user_id BIGINT PRIMARY KEY,
                reserved_mora NUMERIC(24,6) NOT NULL DEFAULT 0
            )
            """
        )
        db = PGAdapter(connection)
        await economy_ledger.ensure_tables(db)
        await vip_repo.ensure_tables(db)
    finally:
        await connection.close()


async def _purchase(dsn: str, user_id: int, days: int, action_id: str) -> dict:
    connection, db = await _connect(dsn)
    try:
        return await vip.purchase_vip(
            db, user_id=user_id, package_days=days, action_id=action_id,
        )
    finally:
        await connection.close()


async def _daily(dsn: str, user_id: int, day_key: str, source_event_id: str) -> dict | None:
    connection, db = await _connect(dsn)
    try:
        async with connection.transaction():
            await vip_repo.lock_user(db, user_id)
            return await vip.complete_daily_mission_from_game(
                db, user_id=user_id, day_key=day_key, source_event_id=source_event_id,
            )
    finally:
        await connection.close()


async def run(dsn: str) -> None:
    await _prepare(dsn)
    connection, db = await _connect(dsn)
    try:
        buyer = 982601
        await db.execute(
            "INSERT INTO users(user_tg_id,user_tg_username,user_balance_zarniki) VALUES (?,?,?)",
            (buyer, "vip_contract", 3000),
        )

        same = await asyncio.gather(
            _purchase(dsn, buyer, 30, "same-delivery"),
            _purchase(dsn, buyer, 30, "same-delivery"),
        )
        assert sorted(result["applied"] for result in same) == [False, True]
        assert same[0]["purchase_id"] == same[1]["purchase_id"]

        distinct = await asyncio.gather(
            _purchase(dsn, buyer, 7, "different-a"),
            _purchase(dsn, buyer, 90, "different-b"),
        )
        assert all(result["applied"] for result in distinct)
        async with db.execute(
            "SELECT user_balance_zarniki FROM users WHERE user_tg_id=?", (buyer,),
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 460
        async with db.execute(
            "SELECT tier,total_days,expires_at-NOW() FROM vip_subscriptions WHERE user_id=?", (buyer,),
        ) as cursor:
            subscription = await cursor.fetchone()
        assert subscription[0] == "vip" and int(subscription[1]) == 127
        assert timedelta(days=126) < subscription[2] < timedelta(days=128)
        async with db.execute(
            "SELECT COUNT(*) FROM vip_v2_purchases WHERE user_id=?", (buyer,),
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 3
        async with db.execute(
            "SELECT COUNT(*) FROM economic_operations WHERE user_id=? AND reason_code='vip_purchase'",
            (buyer,),
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 3

        try:
            await vip.purchase_vip(
                db, user_id=buyer, package_days=7, action_id="same-delivery",
            )
        except vip.VipConflict:
            pass
        else:
            raise AssertionError("one action id must not describe another package")

        poor = 982602
        await db.execute(
            "INSERT INTO users(user_tg_id,user_tg_username,user_balance_zarniki) VALUES (?,?,?)",
            (poor, "vip_poor", 139),
        )
        try:
            await vip.purchase_vip(db, user_id=poor, package_days=7, action_id="too-poor")
        except InsufficientBalance:
            pass
        else:
            raise AssertionError("insufficient Zarniki must fail closed")
        async with db.execute(
            "SELECT COUNT(*) FROM vip_v2_purchases WHERE user_id=?", (poor,),
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 0
        assert not await vip.is_vip_active(db, poor)

        day_key = date.today().isoformat()
        daily = await asyncio.gather(
            _daily(dsn, buyer, day_key, "rhythm_completed:one"),
            _daily(dsn, buyer, day_key, "minesweeper_completed:two"),
        )
        assert sorted(result["already_completed"] for result in daily if result) == [False, True]
        async with db.execute(
            "SELECT user_balance_mora FROM users WHERE user_tg_id=?", (buyer,),
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 20
        async with db.execute(
            "SELECT COUNT(*),MIN(completion_no),MIN(mora_reward) "
            "FROM vip_v2_daily_receipts WHERE user_id=?", (buyer,),
        ) as cursor:
            receipt = await cursor.fetchone()
        assert tuple(map(int, receipt)) == (1, 1, 20)

        reminder_user = 982603
        await db.execute(
            "INSERT INTO users(user_tg_id,user_tg_username) VALUES (?,?)",
            (reminder_user, "vip_reminder"),
        )
        await db.execute(
            "INSERT INTO vip_subscriptions(user_id,tier,expires_at,total_days) "
            "VALUES (?,'vip',NOW()+INTERVAL '7 days',7)",
            (reminder_user,),
        )
        before_evening = datetime(2026, 9, 26, 17, 59, tzinfo=timezone.utc)
        assert await vip.daily_reminder_candidates(db, now=before_evening) == []
        first_evening = datetime(2026, 9, 26, 18, 0, tzinfo=timezone.utc)
        assert reminder_user in await vip.daily_reminder_candidates(db, now=first_evening)
        await vip.record_daily_reminder_sent(db, user_id=reminder_user, now=first_evening)
        assert reminder_user not in await vip.daily_reminder_candidates(db, now=first_evening)
        second_evening = first_evening + timedelta(days=1)
        await vip.record_daily_reminder_sent(db, user_id=reminder_user, now=second_evening)
        third_evening = second_evening + timedelta(days=1)
        assert reminder_user not in await vip.daily_reminder_candidates(db, now=third_evening)

        for statement in (
            "UPDATE vip_v2_purchases SET price_zarniki=1 WHERE user_id=?",
            "DELETE FROM vip_v2_daily_receipts WHERE user_id=?",
        ):
            try:
                async with connection.transaction():
                    await db.execute(statement, (buyer,))
            except asyncpg.RaiseError as error:
                assert "append-only" in str(error)
            else:
                raise AssertionError("VIP receipts must reject mutation")
    finally:
        await connection.close()
    print("OK: VIP purchase replay, concurrent extension, insufficient funds and daily serialization")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.dsn))
