#!/usr/bin/env python3
"""Real PostgreSQL rollback proof for the marriage-members registry.

The required DSN is deliberately limited to loopback because this creates
temporary test rows (all changes are rolled back) and must never touch prod.
"""
from __future__ import annotations

import argparse
import asyncio
from uuid import uuid4
from urllib.parse import urlparse

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.marriage_integrity import (
    audit_family_migration_readiness,
    install_membership_registry,
    migration_is_safe,
)
from infrastructure.repositories.marriages import (
    MarriageConflict,
    create_marriage,
    delete_marriage,
    get_user_marriage,
)
from infrastructure.repositories.divorce_v1 import (
    allocate_property, create_intent, install_schema, settle_intent,
)


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    transaction = connection.transaction()
    await transaction.start()
    try:
        db = PGAdapter(connection)
        async with db.execute(
            "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) "
            "VALUES (?, ?, 'migration-test-a', ?, 'migration-test-b') RETURNING id",
            (-910001, 910000000001, 910000000002),
        ) as cursor:
            first_id = int((await cursor.fetchone())[0])
        async with db.execute(
            "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) "
            "VALUES (?, ?, 'migration-test-c', ?, 'migration-test-d') RETURNING id",
            (-910002, 910000000003, 910000000004),
        ) as cursor:
            second_id = int((await cursor.fetchone())[0])

        audit = await audit_family_migration_readiness(db)
        assert migration_is_safe(audit), audit
        await install_membership_registry(db)
        async with db.execute(
            "SELECT COUNT(*) FROM marriage_members WHERE marriage_id IN (?, ?)",
            (first_id, second_id),
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 4

        created_id = await create_marriage(
            db, -910004, 910000000006, "migration-test-f", 910000000007, "migration-test-g"
        )
        async with db.execute(
            "SELECT COUNT(*) FROM marriage_members WHERE marriage_id = ?", (created_id,)
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 2
        try:
            await create_marriage(
                db, -910005, 910000000006, "duplicate", 910000000008, "other"
            )
        except MarriageConflict:
            pass
        else:
            raise AssertionError("concurrent-equivalent second marriage must fail closed")

        # A divorce must retain the immutable marriage/ledger owner, release
        # only the active membership rows, and permit a genuinely later union.
        await db.execute("UPDATE marriages SET family_balance = 1 WHERE id = ?", (created_id,))
        try:
            await delete_marriage(db, 910000000006)
        except MarriageConflict:
            pass
        else:
            raise AssertionError("divorce with family property must fail closed")
        await db.execute("UPDATE marriages SET family_balance = 0 WHERE id = ?", (created_id,))
        assert await delete_marriage(db, 910000000006)
        async with db.execute(
            "SELECT ended_at IS NOT NULL FROM marriages WHERE id = ?", (created_id,)
        ) as cursor:
            assert (await cursor.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM marriage_members WHERE marriage_id = ?", (created_id,)
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 0
        assert await get_user_marriage(db, 910000000006) is None
        later_id = await create_marriage(
            db, -910006, 910000000006, "later", 910000000009, "later-partner"
        )
        assert later_id != created_id
        await install_schema(db)
        await db.execute(
            "UPDATE marriages SET family_balance=5,family_balance_zarniki=3 WHERE id=?",
            (later_id,),
        )
        await db.execute(
            "INSERT INTO family_wallet_balances(marriage_id,mora,zarniki) VALUES (?,5,3) "
            "ON CONFLICT(marriage_id) DO UPDATE SET mora=5,zarniki=3",
            (later_id,),
        )
        async with db.execute(
            "INSERT INTO pets(owner_id,marriage_id,name,species_id,rarity) "
            "VALUES (?,?, 'family-test-pet','cat','common') RETURNING id",
            (910000000006, later_id),
        ) as cursor:
            family_pet_id = int((await cursor.fetchone())[0])
        intent = await create_intent(db, actor_id=910000000006)
        assert intent["marriage_id"] == later_id and intent["partner_id"] == 910000000009
        allocation = await allocate_property(
            db, intent_id=intent["id"], actor_id=910000000006,
        )
        assert allocation.applied
        replayed_allocation = await allocate_property(
            db, intent_id=intent["id"], actor_id=910000000006,
        )
        assert not replayed_allocation.applied and replayed_allocation.receipt_id == allocation.receipt_id
        async with db.execute(
            "SELECT family_balance,family_balance_zarniki FROM marriages WHERE id=?", (later_id,),
        ) as cursor:
            emptied = await cursor.fetchone()
        assert float(emptied[0]) == 0 and float(emptied[1]) == 0
        async with db.execute(
            "SELECT owner_id,marriage_id FROM pets WHERE id=?", (family_pet_id,),
        ) as cursor:
            pet = await cursor.fetchone()
        assert int(pet[0]) == 910000000006 and pet[1] is None
        async with db.execute(
            "SELECT user_tg_id,user_balance_mora,user_balance_zarniki FROM users "
            "WHERE user_tg_id IN (?,?) ORDER BY user_tg_id",
            (910000000006, 910000000009),
        ) as cursor:
            personal = await cursor.fetchall()
        assert [(int(r[0]), float(r[1]), float(r[2])) for r in personal] == [
            (910000000006, 2.5, 2.0), (910000000009, 2.5, 1.0),
        ]
        async with db.execute(
            "SELECT COUNT(*),COUNT(DISTINCT family_operation_id),"
            "COUNT(DISTINCT personal_operation_id),MIN(initiator_id),MAX(initiator_id) "
            "FROM divorce_property_allocation_legs WHERE receipt_id=?",
            (allocation.receipt_id,),
        ) as cursor:
            legs = await cursor.fetchone()
        assert tuple(int(value) for value in legs) == (4, 4, 4, 910000000006, 910000000006)
        savepoint = connection.transaction()
        await savepoint.start()
        try:
            await db.execute(
                "DELETE FROM divorce_property_allocation_legs WHERE receipt_id=?",
                (allocation.receipt_id,),
            )
        except asyncpg.RaiseError:
            await savepoint.rollback()
        else:
            raise AssertionError("allocation legs must be append-only")
        settled = await settle_intent(db, intent_id=intent["id"], actor_id=910000000006)
        assert not settled.applied and settled.marriage_id == later_id
        replay = await settle_intent(db, intent_id=intent["id"], actor_id=910000000006)
        assert not replay.applied and replay.receipt_id == settled.receipt_id
        async with db.execute(
            "SELECT COUNT(*) FROM divorce_receipts WHERE intent_id=?", (intent["id"],)
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 1

        await db.execute(
            "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) "
            "VALUES (?, ?, 'migration-test-conflict', ?, 'migration-test-e')",
            (-910003, 910000000001, 910000000005),
        )
        duplicate_audit = await audit_family_migration_readiness(db)
        assert duplicate_audit["duplicate_members"] >= 1
        try:
            await install_membership_registry(db)
        except RuntimeError:
            pass
        else:
            raise AssertionError("duplicate membership must prevent migration")
    finally:
        await transaction.rollback()
        await connection.close()


async def run_lock_race(dsn: str) -> None:
    """Two-connection proof of membership-before-custody lock ordering."""
    schema = f"divorce_race_{uuid4().hex}"
    admin = await asyncpg.connect(dsn)
    first = await asyncpg.connect(dsn)
    second = await asyncpg.connect(dsn)
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        for conn in (first, second):
            await conn.execute(f'SET search_path TO "{schema}"')
        await first.execute("CREATE TABLE marriages(id BIGINT PRIMARY KEY, ended_at TIMESTAMPTZ)")
        await first.execute("CREATE TABLE marriage_members(user_id BIGINT PRIMARY KEY,marriage_id BIGINT)")
        await first.execute("CREATE TABLE pets(id BIGINT PRIMARY KEY,marriage_id BIGINT)")
        await first.execute("CREATE TABLE family_wallet_balances(marriage_id BIGINT PRIMARY KEY,mora NUMERIC)")

        for offset in (0, 10):
            marriage_id = 7000 + offset
            await first.execute("INSERT INTO marriages VALUES($1,NULL)", marriage_id)
            await first.execute(
                "INSERT INTO marriage_members VALUES($1,$3),($2,$3)",
                8001 + offset, 8002 + offset, marriage_id,
            )
            await first.execute("INSERT INTO family_wallet_balances VALUES($1,1)", marriage_id)
            membership_locked = asyncio.Event()

            async def divorce_path():
                async with first.transaction():
                    await first.fetchrow("SELECT id FROM marriages WHERE id=$1 FOR UPDATE", marriage_id)
                    await first.fetch(
                        "SELECT user_id FROM marriage_members WHERE marriage_id=$1 ORDER BY user_id FOR UPDATE",
                        marriage_id,
                    )
                    membership_locked.set()
                    await asyncio.sleep(0.05)
                    await first.fetch("SELECT id FROM pets WHERE marriage_id=$1 ORDER BY id FOR UPDATE", marriage_id)
                    await first.fetchrow(
                        "SELECT mora FROM family_wallet_balances WHERE marriage_id=$1 FOR UPDATE", marriage_id,
                    )
                    await first.execute("DELETE FROM marriage_members WHERE marriage_id=$1", marriage_id)

            async def concurrent_transfer():
                await membership_locked.wait()
                async with second.transaction():
                    await second.fetchrow(
                        "SELECT marriage_id FROM marriage_members WHERE user_id=$1 FOR SHARE",
                        8001 + offset,
                    )
                    await second.fetchrow(
                        "SELECT mora FROM family_wallet_balances WHERE marriage_id=$1 FOR UPDATE", marriage_id,
                    )

            await asyncio.wait_for(
                asyncio.gather(divorce_path(), concurrent_transfer()), timeout=5,
            )
    finally:
        await first.close()
        await second.close()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
asyncio.run(run_lock_race(args.dsn))
print("marriage registry: real PostgreSQL rollback proof OK")
