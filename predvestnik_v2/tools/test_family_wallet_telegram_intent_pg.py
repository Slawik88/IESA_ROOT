#!/usr/bin/env python3
"""Real PostgreSQL rollback proof for Telegram family-wallet choice intents."""
from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.family_wallet_v1 import (
    FamilyTransferIntentError,
    consume_telegram_transfer_intent,
    create_telegram_transfer_intent,
)


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def scalar(db, sql: str, params: tuple) -> object:
    async with db.execute(sql, params) as cursor:
        return (await cursor.fetchone())[0]


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    transaction = connection.transaction()
    await transaction.start()
    try:
        db = PGAdapter(connection)
        actor, spouse, outsider = 941000000001, 941000000002, 941000000003
        await db.execute(
            "INSERT INTO users (user_tg_id, user_balance_zarniki) VALUES (?, ?), (?, ?), (?, ?)",
            (actor, 10, spouse, 0, outsider, 0),
        )
        async with db.execute(
            "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) "
            "VALUES (?, ?, 'intent-a', ?, 'intent-b') RETURNING id",
            (-941001, actor, spouse),
        ) as cursor:
            marriage_id = int((await cursor.fetchone())[0])
        await db.execute(
            "INSERT INTO marriage_members (user_id, marriage_id) VALUES (?, ?), (?, ?)",
            (actor, marriage_id, spouse, marriage_id),
        )

        intent_id = await create_telegram_transfer_intent(
            db, actor_id=actor, action="deposit", amount=5,
        )
        try:
            await consume_telegram_transfer_intent(
                db, intent_id=intent_id, actor_id=outsider, currency="zarniki",
            )
        except FamilyTransferIntentError:
            pass
        else:
            raise AssertionError("a foreign Telegram callback must not consume an intent")
        assert str(await scalar(db, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (actor,))) == "10.0"

        applied = await consume_telegram_transfer_intent(
            db, intent_id=intent_id, actor_id=actor, currency="zarniki",
        )
        replay = await consume_telegram_transfer_intent(
            db, intent_id=intent_id, actor_id=actor, currency="zarniki",
        )
        assert applied.applied and not replay.applied and replay.operation_id == applied.operation_id
        assert str(await scalar(db, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (actor,))) == "5.0"
        assert str(await scalar(db, "SELECT zarniki FROM family_wallet_balances WHERE marriage_id = ?", (marriage_id,))) == "5.000000"
        assert int(await scalar(db, "SELECT COUNT(*) FROM family_wallet_operations WHERE marriage_id = ?", (marriage_id,))) == 1

        expired = await create_telegram_transfer_intent(
            db, actor_id=actor, action="deposit", amount=1,
        )
        await db.execute(
            "UPDATE family_wallet_telegram_intents SET expires_at = NOW() - INTERVAL '1 second' WHERE id = ?",
            (expired,),
        )
        try:
            await consume_telegram_transfer_intent(
                db, intent_id=expired, actor_id=actor, currency="zarniki",
            )
        except FamilyTransferIntentError:
            pass
        else:
            raise AssertionError("an expired choice must not move value")
        assert str(await scalar(db, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (actor,))) == "5.0"
    finally:
        await transaction.rollback()
        await connection.close()


async def run_concurrent_callback_proof(dsn: str) -> None:
    """Two independently delivered callbacks for one card debit exactly once."""
    actor = 800_000_000_000 + (uuid4().int % 100_000_000_000)
    spouse = actor + 1
    marriage_id: int | None = None
    admin = await asyncpg.connect(dsn)
    try:
        db = PGAdapter(admin)
        await db.execute(
            "INSERT INTO users (user_tg_id, user_balance_zarniki) VALUES (?, ?), (?, ?)",
            (actor, 10, spouse, 0),
        )
        async with db.execute(
            "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) "
            "VALUES (?, ?, 'race-a', ?, 'race-b') RETURNING id",
            (-941002, actor, spouse),
        ) as cursor:
            marriage_id = int((await cursor.fetchone())[0])
        await db.execute(
            "INSERT INTO marriage_members (user_id, marriage_id) VALUES (?, ?), (?, ?)",
            (actor, marriage_id, spouse, marriage_id),
        )
        intent_id = await create_telegram_transfer_intent(
            db, actor_id=actor, action="deposit", amount=5,
        )

        async def deliver_once():
            connection = await asyncpg.connect(dsn)
            try:
                return await consume_telegram_transfer_intent(
                    PGAdapter(connection), intent_id=intent_id, actor_id=actor, currency="zarniki",
                )
            finally:
                await connection.close()

        first, second = await asyncio.gather(deliver_once(), deliver_once())
        assert sorted((first.applied, second.applied)) == [False, True]
        assert first.operation_id == second.operation_id
        assert str(await scalar(db, "SELECT user_balance_zarniki FROM users WHERE user_tg_id = ?", (actor,))) == "5.0"
        assert int(await scalar(db, "SELECT COUNT(*) FROM family_wallet_operations WHERE marriage_id = ?", (marriage_id,))) == 1
    finally:
        if marriage_id is not None:
            # Exact disposable rows only; the probe never touches player records.
            await admin.execute("DELETE FROM marriage_members WHERE marriage_id = $1", marriage_id)
            await admin.execute("DELETE FROM family_wallet_telegram_intents WHERE marriage_id = $1", marriage_id)
            await admin.execute("DELETE FROM family_wallet_ledger WHERE marriage_id = $1", marriage_id)
            await admin.execute("DELETE FROM family_wallet_operations WHERE marriage_id = $1", marriage_id)
            await admin.execute("DELETE FROM family_wallet_balances WHERE marriage_id = $1", marriage_id)
            await admin.execute("DELETE FROM marriages WHERE id = $1", marriage_id)
        await admin.execute("DELETE FROM users WHERE user_tg_id = ANY($1::bigint[])", [actor, spouse])
        await admin.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
asyncio.run(run_concurrent_callback_proof(args.dsn))
print("family wallet Telegram intent: real PostgreSQL rollback proof OK")
