#!/usr/bin/env python3
"""Real PostgreSQL rollback proof: account deletion cannot erase a marriage."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from urllib.parse import urlparse

import asyncpg
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import global_skins_v1 as global_skins_repo
from infrastructure.repositories import chests_v1 as chest_repo
from infrastructure.repositories import economy_ledger
from core.chests_v1 import CATALOG_VERSION, catalog_digest
from services import chests_v1
from FastAPI.deps import require_tg_user
from services.account_deletion import _finalize, _mark_deleted, request_deletion


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
        await economy_ledger.ensure_tables(db)
        await chest_repo.ensure_tables(db)
        married, partner, single = 920000000001, 920000000002, 920000000003
        await db.execute("INSERT INTO users (user_tg_id) VALUES (?), (?), (?)", (married, partner, single))
        await db.execute(
            "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name) "
            "VALUES (?, ?, 'deletion-a', ?, 'deletion-b') RETURNING id",
            (-920001, married, partner),
        )
        async with db.execute(
            "SELECT id FROM marriages WHERE chat_id = ?", (-920001,)
        ) as cursor:
            marriage_id = int((await cursor.fetchone())[0])
        await db.execute(
            "INSERT INTO marriage_members (user_id, marriage_id) VALUES (?, ?), (?, ?)",
            (married, marriage_id, partner, marriage_id),
        )
        ok, _ = await request_deletion(db, married)
        assert not ok, "married account must not even enter deletion confirmation"
        assert not await _mark_deleted(db, married)
        assert await scalar(db, "SELECT deleted_at IS NULL FROM users WHERE user_tg_id = ?", (married,))

        await db.execute("UPDATE users SET deleted_at = NOW() WHERE user_tg_id = ?", (married,))
        await db.execute(
            "INSERT INTO account_deletions (user_id, source, status) VALUES (?, 'self', 'pending_restore')",
            (married,),
        )
        await _finalize(db, married)
        assert await scalar(db, "SELECT deleted_at IS NULL FROM users WHERE user_tg_id = ?", (married,))
        assert await scalar(db, "SELECT status = 'cancelled' FROM account_deletions WHERE user_id = ?", (married,))
        assert await scalar(db, "SELECT COUNT(*) FROM marriages WHERE user1_id = ? OR user2_id = ?", (married, married)) == 1

        assert await _mark_deleted(db, single)
        assert await scalar(db, "SELECT deleted_at IS NOT NULL FROM users WHERE user_tg_id = ?", (single,))
        await global_skins_repo.ensure_tables(db)
        await global_skins_repo.grant(db, single, "lunar_archive", source="deletion_test")
        await global_skins_repo.set_selection(db, single, "lunar_archive")
        account = await chest_repo.lock_account(db, single)
        await db.execute(
            "UPDATE chest_key_accounts_v1 SET balance=1 WHERE user_id=?", (single,),
        )
        await chest_repo.create_open(
            db, open_id="deletion-pending-open", user_id=single,
            action_id="deletion-open", request_hash="a" * 64,
            catalog_version=CATALOG_VERSION, catalog_digest=catalog_digest(),
            roll=100, stars=1, reward_kind="mora", reward_amount=20,
            key_balance_before=1, account_epoch=int(account['account_epoch']),
        )
        await _finalize(db, single)
        assert await scalar(db, "SELECT COUNT(*) = 0 FROM global_skin_v1_owned WHERE user_id = ?", (single,))
        assert await scalar(db, "SELECT COUNT(*) = 0 FROM global_skin_v1_selection WHERE user_id = ?", (single,))
        chest_state = await chests_v1.overview(db, user_id=single)
        assert chest_state['key_balance'] == 0 and chest_state['pending_open'] is None
        assert await scalar(
            db, "SELECT COUNT(*)=1 FROM chest_account_retirements_v1 WHERE user_id=? "
            "AND balance_before=0 AND balance_after=0 AND new_epoch=old_epoch+1",
            (single,),
        )
        try:
            await require_tg_user(user={'id': single}, db=db)
        except HTTPException as exc:
            assert exc.status_code == 403 and 'ACCOUNT_DELETED' in str(exc.detail)
        else:
            raise AssertionError("finalized account session must be rejected by gameplay auth")
        try:
            await chests_v1.reveal(db, user_id=single, open_id="deletion-pending-open")
        except chests_v1.ChestKeyConflict:
            pass
        else:
            raise AssertionError("finalized account must not reveal a pre-finalization chest")
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("account deletion family guard: real PostgreSQL rollback proof OK")
