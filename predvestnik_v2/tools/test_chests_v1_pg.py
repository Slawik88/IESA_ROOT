"""Real PostgreSQL proof for immutable, idempotent chest-key delivery."""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
import time
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.chests_v1 import CATALOG_VERSION, MORA_RANGES, ChestOutcome, catalog_digest
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import chests_v1 as repo
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import quests_v1 as quest_repo
from services import chests_v1


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def insert_receipt(db, user_id: int, reward_kind: str, reward_id: str,
                         amount_mora: int = 20, *, operation_kind: str | None = None,
                         operation_amount: int | None = None,
                         receipt_policy: str = "reward-test-1",
                         operation_policy: str = "reward-test-1") -> None:
    await db.execute(
        "INSERT INTO quest_v1_reward_receipts"
        "(user_id,reward_id,reward_kind,quest_policy_version,reward_policy_version,amount_mora) "
        "VALUES (?,?,?,?,?,?)",
        (user_id, reward_id, reward_kind, "quest-test-1", receipt_policy, amount_mora),
    )
    operation_kind = operation_kind or reward_kind
    operation_amount = amount_mora if operation_amount is None else operation_amount
    await economy_ledger.apply_balance_change(
        db, user_id, {"mora": operation_amount}, reason_code="quest_reward",
        idempotency_key=f"quest-v1:{reward_id}", source_type="quest",
        reference_type="quest_reward", reference_id=reward_id,
        metadata={"policy_version": operation_policy, "reward_kind": operation_kind,
                  "reward_id": reward_id, "amount_mora": operation_amount},
        note="test quest reward",
    )


async def run(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    await economy_ledger.ensure_tables(db)
    await repo.ensure_tables(db)
    await quest_repo.ensure_tables(db)
    tx = conn.transaction()
    await tx.start()
    try:
        user = 976401
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT(user_tg_id) DO NOTHING", (user,))
        grant_args = dict(reward_kind="daily", reward_id="daily:2026-09-12")
        await insert_receipt(db, user, "daily", grant_args["reward_id"])
        first = await chests_v1.grant_quest_completion_key(db, user_id=user, **grant_args)
        replay = await chests_v1.grant_quest_completion_key(db, user_id=user, **grant_args)
        assert first.applied and first.balance_before == 0 and first.balance_after == 1
        assert not replay.applied and replay.grant_id == first.grant_id and replay.balance_after == 1
        assert await repo.get_balance(db, user) == 1

        try:
            await chests_v1.grant_quest_completion_key(
                db, user_id=user, reward_kind="weekly", reward_id=grant_args["reward_id"],
            )
        except ValueError:
            pass
        else:
            raise AssertionError("daily receipt must not mint a weekly key")
        assert await repo.get_balance(db, user) == 1

        await insert_receipt(db, user + 1, "daily", grant_args["reward_id"])
        other = await chests_v1.grant_quest_completion_key(db, user_id=user + 1, **grant_args)
        assert other.applied and other.balance_after == 1

        combined_user = user + 2
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT(user_tg_id) DO NOTHING", (combined_user,))
        await insert_receipt(db, combined_user, "combined", "combined:2026-W37", 75)
        for claimed_kind in ("daily", "weekly"):
            try:
                await chests_v1.grant_quest_completion_key(
                    db, user_id=combined_user, reward_kind=claimed_kind,
                    reward_id="combined:2026-W37",
                )
            except ValueError:
                pass
            else:
                raise AssertionError("combined receipt must not mint daily or weekly keys")

        mismatch_user = user + 3
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT(user_tg_id) DO NOTHING", (mismatch_user,))
        await insert_receipt(
            db, mismatch_user, "daily", "daily:mismatch", 21,
            operation_amount=20, receipt_policy="reward-wrong", operation_policy="reward-test-1",
        )
        try:
            await chests_v1.grant_quest_completion_key(
                db, user_id=mismatch_user, reward_kind="daily", reward_id="daily:mismatch",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("altered receipt policy/amount must not mint a key")

        async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id=?", (user,)) as cursor:
            mora_before = float((await cursor.fetchone())[0])
        original_roll = chests_v1.roll_outcome
        chests_v1.roll_outcome = lambda *_args, **_kwargs: ChestOutcome(0, 1, "mora", 20)
        prepared = await chests_v1.prepare_free_open(
            db, user_id=user, action_id="open-a", requested_catalog_version=CATALOG_VERSION,
            requested_catalog_digest=catalog_digest(),
        )
        chests_v1.roll_outcome = original_roll
        assert prepared["sealed"] and "stars" not in prepared and "reward" not in prepared
        assert prepared["key_balance"] == 0 and await repo.get_balance(db, user) == 0
        async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id=?", (user,)) as cursor:
            assert float((await cursor.fetchone())[0]) == mora_before
        recovered = await chests_v1.overview(db, user_id=user)
        assert recovered["pending_open"] == prepared
        replayed = await chests_v1.prepare_free_open(
            db, user_id=user, action_id="open-a", requested_catalog_version=CATALOG_VERSION,
            requested_catalog_digest=catalog_digest(),
        )
        assert replayed == prepared
        try:
            await chests_v1.prepare_free_open(
                db, user_id=user, action_id="open-a", requested_catalog_version="changed-catalog",
                requested_catalog_digest=catalog_digest(),
            )
        except chests_v1.ChestKeyConflict:
            pass
        else:
            raise AssertionError("same action with changed catalogue must conflict")
        try:
            await chests_v1.prepare_free_open(
                db, user_id=user, action_id="open-a", requested_catalog_version=CATALOG_VERSION,
                requested_catalog_digest="0" * 64,
            )
        except chests_v1.ChestKeyConflict:
            pass
        else:
            raise AssertionError("same version with changed digest must conflict")
        revealed = await chests_v1.reveal(db, user_id=user, open_id=prepared["open_id"])
        reveal_replay = await chests_v1.reveal(db, user_id=user, open_id=prepared["open_id"])
        assert reveal_replay == revealed and revealed["revealed"]
        after_reveal = await chests_v1.overview(db, user_id=user)
        assert after_reveal["pending_open"] is None and after_reveal["last_result"] == revealed
        assert 1 <= revealed["stars"] <= 10 and revealed["reward"]["kind"] == "mora"
        minimum, maximum = MORA_RANGES[revealed["stars"]]
        assert minimum <= revealed["reward"]["amount"] <= maximum
        async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id=?", (user,)) as cursor:
            mora_after = float((await cursor.fetchone())[0])
        assert mora_after >= mora_before + revealed["reward"]["amount"]
        async with db.execute(
            "SELECT l.delta FROM economic_ledger l JOIN economic_operations o ON o.id=l.operation_id "
            "WHERE o.user_id=? AND o.reference_type='chest_open' AND o.reference_id=? AND l.currency='mora'",
            (user, prepared["open_id"]),
        ) as cursor:
            assert float((await cursor.fetchone())[0]) == revealed["reward"]["amount"]
        try:
            await chests_v1.reveal(db, user_id=user + 1, open_id=prepared["open_id"])
        except chests_v1.ChestKeyConflict:
            pass
        else:
            raise AssertionError("another user must not reveal an owned opening")
        try:
            await chests_v1.prepare_free_open(
                db, user_id=user, action_id="open-empty", requested_catalog_version=CATALOG_VERSION,
                requested_catalog_digest=catalog_digest(),
            )
        except chests_v1.ChestKeyConflict:
            pass
        else:
            raise AssertionError("opening without a key must fail")
        assert await repo.get_balance(db, user) == 0

        rollback_user = 976403
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT(user_tg_id) DO NOTHING", (rollback_user,))
        await insert_receipt(db, rollback_user, "weekly", "weekly:rollback", 100)
        await chests_v1.grant_quest_completion_key(
            db, user_id=rollback_user, reward_kind="weekly", reward_id="weekly:rollback",
        )
        async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id=?", (rollback_user,)) as cursor:
            rollback_mora_before = float((await cursor.fetchone())[0])
        original_apply = chests_v1.economy_ledger.apply_balance_change
        original_roll = chests_v1.roll_outcome
        chests_v1.roll_outcome = lambda *_args, **_kwargs: ChestOutcome(0, 1, "mora", 20)

        async def fail_after_reward(*args, **kwargs):
            await original_apply(*args, **kwargs)
            raise RuntimeError("injected failure after reward writer")

        chests_v1.economy_ledger.apply_balance_change = fail_after_reward
        try:
            try:
                prepared_rollback = await chests_v1.prepare_free_open(
                    db, user_id=rollback_user, action_id="rollback-open",
                    requested_catalog_version=CATALOG_VERSION,
                    requested_catalog_digest=catalog_digest(),
                )
                await chests_v1.reveal(db, user_id=rollback_user, open_id=prepared_rollback["open_id"])
            except RuntimeError as exc:
                assert "injected failure" in str(exc)
            else:
                raise AssertionError("fault injection must escape and roll back")
        finally:
            chests_v1.economy_ledger.apply_balance_change = original_apply
            chests_v1.roll_outcome = original_roll
        assert await repo.get_balance(db, rollback_user) == 0
        async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id=?", (rollback_user,)) as cursor:
            assert float((await cursor.fetchone())[0]) == rollback_mora_before
        async with db.execute("SELECT COUNT(*) FROM chest_opens_v1 WHERE user_id=?", (rollback_user,)) as cursor:
            assert (await cursor.fetchone())[0] == 1
        async with db.execute("SELECT COUNT(*) FROM chest_reveals_v1 WHERE user_id=?", (rollback_user,)) as cursor:
            assert (await cursor.fetchone())[0] == 0

        await repo.retire_account(db, user)
        for table in ("chest_account_retirements_v1", "chest_key_grants_v1", "chest_key_ledger_v1", "chest_opens_v1",
                      "chest_key_spends_v1", "chest_reveals_v1"):
            savepoint = conn.transaction()
            await savepoint.start()
            try:
                await db.execute(f"DELETE FROM {table} WHERE user_id=?", (user,))
            except Exception:
                await savepoint.rollback()
            else:
                await savepoint.rollback()
                raise AssertionError(f"{table} must be append-only")

        orphan_user = 976499
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (orphan_user,))
        await db.execute("INSERT INTO chest_key_accounts_v1(user_id,balance) VALUES (?,0)", (orphan_user,))
        await db.execute("ALTER TABLE chest_reveals_v1 ALTER COLUMN economy_operation_id DROP NOT NULL")
        await db.execute(
            "INSERT INTO chest_opens_v1"
            "(id,user_id,action_id,request_hash,catalog_version,catalog_digest,roll,stars,reward_kind,reward_amount,account_epoch) "
            "VALUES ('orphan-reveal',?,'orphan-action',?, ?, ?,0,1,'mora',20,0)",
            (orphan_user, "b" * 64, CATALOG_VERSION, catalog_digest()),
        )
        await db.execute(
            "INSERT INTO chest_key_spends_v1(open_id,user_id,amount,balance_before,balance_after) "
            "VALUES ('orphan-reveal',?,1,1,0)", (orphan_user,),
        )
        await db.execute(
            "INSERT INTO chest_reveals_v1(open_id,user_id,economy_operation_id) "
            "VALUES ('orphan-reveal',?,NULL)", (orphan_user,),
        )
        try:
            await repo.ensure_tables(db)
        except RuntimeError as exc:
            assert "without an economic operation" in str(exc)
        else:
            raise AssertionError("unbackfillable reveal migration must fail closed")
        try:
            await repo.assert_delivery_ready(db)
        except RuntimeError as exc:
            assert "fail-closed" in str(exc)
        else:
            raise AssertionError("chest service must reject an unfinished reveal migration")
        async with db.execute(
            "SELECT COUNT(*) FROM pg_trigger WHERE tgname='chest_reveals_v1_append_only' AND NOT tgisinternal"
        ) as cursor:
            assert (await cursor.fetchone())[0] == 1
        orphan_delete = conn.transaction()
        await orphan_delete.start()
        try:
            await db.execute("DELETE FROM chest_reveals_v1 WHERE open_id='orphan-reveal'")
        except Exception:
            await orphan_delete.rollback()
        else:
            await orphan_delete.rollback()
            raise AssertionError("failed migration must preserve the append-only trigger")
    finally:
        await tx.rollback()
        await conn.close()

    race_user = 980_000_000 + time.time_ns() % 10_000_000
    setup_conn = await asyncpg.connect(dsn)
    setup_db = PGAdapter(setup_conn)
    try:
        await setup_db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT(user_tg_id) DO NOTHING", (race_user,))
        await insert_receipt(setup_db, race_user, "daily", f"daily:race:{race_user}")
        await setup_db.commit()
        await chests_v1.grant_quest_completion_key(
            setup_db, user_id=race_user, reward_kind="daily", reward_id=f"daily:race:{race_user}",
        )
    finally:
        await setup_conn.close()

    race_connections = [await asyncpg.connect(dsn), await asyncpg.connect(dsn)]

    async def attempt(index: int):
        try:
            return await chests_v1.prepare_free_open(
                PGAdapter(race_connections[index]), user_id=race_user,
                action_id=f"race-{index}", requested_catalog_version=CATALOG_VERSION,
                requested_catalog_digest=catalog_digest(),
            )
        except chests_v1.ChestKeyConflict:
            return None

    try:
        race_results = await asyncio.gather(attempt(0), attempt(1))
        assert sum(result is not None for result in race_results) == 1
        check_db = PGAdapter(race_connections[0])
        assert await repo.get_balance(check_db, race_user) == 0
        async with check_db.execute("SELECT COUNT(*) FROM chest_opens_v1 WHERE user_id=?", (race_user,)) as cursor:
            assert (await cursor.fetchone())[0] == 1
    finally:
        await asyncio.gather(*(connection.close() for connection in race_connections))
    print("OK: chest keys/opening are atomic, idempotent, isolated, race- and rollback-safe")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.dsn))
