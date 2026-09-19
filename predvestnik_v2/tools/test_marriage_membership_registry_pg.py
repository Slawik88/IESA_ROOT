#!/usr/bin/env python3
"""Real PostgreSQL rollback proof for the marriage-members registry.

The required DSN is deliberately limited to loopback because this creates
temporary test rows (all changes are rolled back) and must never touch prod.
"""
from __future__ import annotations

import argparse
import asyncio
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
from infrastructure.repositories.divorce_v1 import create_intent, install_schema, settle_intent


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
        intent = await create_intent(db, actor_id=910000000006)
        assert intent["marriage_id"] == later_id and intent["partner_id"] == 910000000009
        settled = await settle_intent(db, intent_id=intent["id"], actor_id=910000000006)
        assert settled.applied and settled.marriage_id == later_id
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


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("marriage registry: real PostgreSQL rollback proof OK")
