#!/usr/bin/env python3
"""Real PostgreSQL proof (audit A02): account finalization is all-or-nothing.

Runs in autocommit mode, exactly like the scheduler connection, because a
failure inside an outer test transaction would hide the production behaviour.
Only a loopback DSN is accepted. Test accounts use a fresh id range per run;
append-only chest retirement receipts written by the final successful pass are
left in the disposable database on purpose (they cannot be deleted).
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("BOT_TOKEN", None)   # _tg() must never reach Telegram from this test

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import chests_v1 as chest_repo
from infrastructure.repositories import economy_ledger
from services import account_deletion
from services.account_deletion import _finalize, daily_tick, restore_account

# First, middle and last statements of the cleanup plus the status write itself.
FAILURE_POINTS = [
    ("chest_key_accounts_v1", "UPDATE"),
    ("pets", "DELETE"),
    ("inventory", "DELETE"),
    ("clan_members", "DELETE"),
    ("user_chat_stats", "UPDATE"),
    ("users", "UPDATE"),
    ("account_deletions", "UPDATE"),
]


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def scalar(db, sql: str, params: tuple = ()) -> object:
    async with db.execute(sql, params) as cursor:
        return (await cursor.fetchone())[0]


async def seed_expired_deletion(db, user_id: int) -> None:
    """A deleted account whose restore window has already expired."""
    await db.execute(
        "INSERT INTO users (user_tg_id, user_balance_mora, deleted_at) "
        "VALUES (?, 500, NOW() - INTERVAL '20 days')",
        (user_id,),
    )
    await db.execute(
        "INSERT INTO pets (owner_id, name, species_id, rarity) VALUES (?, 'a02', 'cat', 'common')",
        (user_id,),
    )
    await db.execute(
        "INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, 'a02_item', 3)", (user_id,)
    )
    await db.execute(
        "INSERT INTO account_deletions (user_id, source, status, deleted_at, restore_deadline) "
        "VALUES (?, 'self', 'pending_restore', NOW() - INTERVAL '20 days', NOW() - INTERVAL '1 day')",
        (user_id,),
    )


async def snapshot(db, user_id: int) -> dict:
    return {
        "status": await scalar(db, "SELECT status FROM account_deletions WHERE user_id=?", (user_id,)),
        "mora": await scalar(db, "SELECT user_balance_mora FROM users WHERE user_tg_id=?", (user_id,)),
        "deleted": await scalar(db, "SELECT deleted_at IS NOT NULL FROM users WHERE user_tg_id=?", (user_id,)),
        "pets": await scalar(db, "SELECT COUNT(*) FROM pets WHERE owner_id=?", (user_id,)),
        "inventory": await scalar(db, "SELECT COUNT(*) FROM inventory WHERE user_id=?", (user_id,)),
        "retirements": await scalar(
            db, "SELECT COUNT(*) FROM chest_account_retirements_v1 WHERE user_id=?", (user_id,)),
    }


INTACT = {"status": "pending_restore", "mora": 500, "deleted": True, "pets": 1, "inventory": 1, "retirements": 0}
FINAL = {"status": "finalized", "mora": 0, "deleted": True, "pets": 0, "inventory": 0, "retirements": 1}


async def inject_failure(db, table: str, op: str) -> None:
    await db.execute(
        "CREATE OR REPLACE FUNCTION a02_injected_failure() RETURNS trigger LANGUAGE plpgsql AS "
        "$$ BEGIN RAISE EXCEPTION 'a02 injected failure on %', TG_TABLE_NAME; END $$"
    )
    await db.execute(
        f"CREATE TRIGGER a02_injected_failure BEFORE {op} ON {table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION a02_injected_failure()"
    )


async def clear_failure(db, table: str) -> None:
    await db.execute(f"DROP TRIGGER IF EXISTS a02_injected_failure ON {table}")


async def cleanup(db, user_ids: list[int]) -> None:
    for sql in (
        "DELETE FROM pets WHERE owner_id = ANY(?::bigint[])",
        "DELETE FROM inventory WHERE user_id = ANY(?::bigint[])",
        "DELETE FROM account_deletions WHERE user_id = ANY(?::bigint[])",
        "DELETE FROM chest_key_accounts_v1 WHERE user_id = ANY(?::bigint[])",
        "DELETE FROM users WHERE user_tg_id = ANY(?::bigint[])",
    ):
        await db.execute(sql, (user_ids,))


async def check_every_failure_point(db, base: int, used: list[int]) -> None:
    for offset, (table, op) in enumerate(FAILURE_POINTS):
        user_id = base + offset
        used.append(user_id)
        await seed_expired_deletion(db, user_id)
        await inject_failure(db, table, op)
        try:
            await daily_tick(db)   # must not raise: one bad account cannot stop the tick
        finally:
            await clear_failure(db, table)
        state = await snapshot(db, user_id)
        assert state == INTACT, f"failure at {table} {op} left a partial account: {state}"

        await daily_tick(db)   # retry after the fault is gone
        state = await snapshot(db, user_id)
        assert state == FINAL, f"retry after {table} {op} failure did not finish: {state}"


async def check_restore_wins_race(dsn: str, db, user_id: int, used: list[int]) -> None:
    """Restore holds the per-user lock first; finalize must then do nothing."""
    used.append(user_id)
    await seed_expired_deletion(db, user_id)
    restorer_conn = await asyncpg.connect(dsn)
    finalizer_conn = await asyncpg.connect(dsn)
    try:
        restorer = PGAdapter(restorer_conn)
        tx = restorer_conn.transaction()
        await tx.start()
        await scalar(restorer, "SELECT pg_advisory_xact_lock(?)", (user_id,))
        finalize_task = asyncio.create_task(_finalize(PGAdapter(finalizer_conn), user_id))
        await asyncio.sleep(0.5)
        assert not finalize_task.done(), "finalize must wait for the per-user lock"
        ok, _ = await restore_account(restorer, user_id)
        assert ok, "restore inside the window must succeed"
        await tx.commit()
        await asyncio.wait_for(finalize_task, 10)
    finally:
        await restorer_conn.close()
        await finalizer_conn.close()
    state = await snapshot(db, user_id)
    assert state["status"] == "restored" and not state["deleted"], state
    assert state["pets"] == 1 and state["inventory"] == 1 and state["mora"] == 500, state
    assert state["retirements"] == 0, state


async def check_finalize_wins_race(dsn: str, db, user_id: int, used: list[int]) -> None:
    """Finalize holds the per-user lock first; a late restore must be refused."""
    used.append(user_id)
    await seed_expired_deletion(db, user_id)
    finalizer_conn = await asyncpg.connect(dsn)
    restorer_conn = await asyncpg.connect(dsn)
    try:
        finalizer = PGAdapter(finalizer_conn)
        tx = finalizer_conn.transaction()
        await tx.start()
        await _finalize(finalizer, user_id)   # nested: holds the lock until the outer commit
        restore_task = asyncio.create_task(restore_account(PGAdapter(restorer_conn), user_id))
        await asyncio.sleep(0.5)
        assert not restore_task.done(), "restore must wait for the per-user lock"
        await tx.commit()
        ok, _ = await asyncio.wait_for(restore_task, 10)
        assert not ok, "restore after finalization must be refused"
    finally:
        await finalizer_conn.close()
        await restorer_conn.close()
    state = await snapshot(db, user_id)
    assert state == FINAL, state


async def check_not_due_is_untouched(db, user_id: int, used: list[int]) -> None:
    """A direct call for an account that is no longer pending must change nothing."""
    used.append(user_id)
    await seed_expired_deletion(db, user_id)
    await db.execute("UPDATE account_deletions SET status='restored' WHERE user_id=?", (user_id,))
    await db.execute("UPDATE users SET deleted_at=NULL WHERE user_tg_id=?", (user_id,))
    await _finalize(db, user_id)
    state = await snapshot(db, user_id)
    assert state["status"] == "restored" and state["pets"] == 1 and state["mora"] == 500, state


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    used: list[int] = []
    base = 930_000_000_000 + (int(time.time()) % 100_000) * 100
    try:
        await economy_ledger.ensure_tables(db)
        await chest_repo.ensure_tables(db)
        await check_every_failure_point(db, base, used)
        await check_restore_wins_race(dsn, db, base + 50, used)
        await check_finalize_wins_race(dsn, db, base + 51, used)
        await check_not_due_is_untouched(db, base + 52, used)
    finally:
        for table, _ in FAILURE_POINTS:
            await clear_failure(db, table)
        await db.execute("DROP FUNCTION IF EXISTS a02_injected_failure()")
        await cleanup(db, used)
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("account deletion atomic finalization: real PostgreSQL proof OK")
