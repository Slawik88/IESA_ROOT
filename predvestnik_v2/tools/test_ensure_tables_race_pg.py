"""Race proof: parallel first requests must not break ensure_tables (production, 2026-10-18).

A dyno restart makes the first requests call ensure_tables at the same moment.  The
former DROP TRIGGER + CREATE TRIGGER pairs turned that into "trigger ... already
exists": /quests-v1/me answered 500 and a finished Rune Rhythm run could not settle
(its quest recording calls chests_v1.ensure_tables).  Every append-only trigger is now
created through the guarded DO block, so two concurrent installers both succeed and
the trigger exists exactly once.
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import achievements_v1, chests_v1, echo_shards_v1, economy_ledger
from infrastructure.repositories import gifts_v2, pets_v1, quests_v1, rhythm_v2, shop_v1


REPOS = (
    ("chests_v1", chests_v1.ensure_tables, (
        ("chest_account_retirements_v1", "chest_account_retirements_v1_append_only"),
        ("chest_key_grants_v1", "chest_key_grants_v1_append_only"),
        ("chest_key_ledger_v1", "chest_key_ledger_v1_append_only"),
        ("chest_opens_v1", "chest_opens_v1_append_only"),
        ("chest_key_spends_v1", "chest_key_spends_v1_append_only"),
        ("chest_reveals_v1", "chest_reveals_v1_append_only"),
        ("chest_key_purchases_v1", "chest_key_purchases_v1_append_only"),
        ("chest_key_allocations_v1", "chest_key_allocations_v1_append_only"),
        ("chest_key_refunds_v1", "chest_key_refunds_v1_append_only"),
        ("chest_key_revocations_v1", "chest_key_revocations_v1_append_only"),
        ("chest_pet_unlocks_v1", "chest_pet_unlocks_v1_append_only"),
        ("chest_deliveries_v1", "chest_deliveries_v1_append_only"),
        ("chest_key_offer_purchases_v1", "chest_key_offer_purchases_v1_append_only"),
    )),
    ("quests_v1", quests_v1.ensure_tables, (
        ("quest_v1_reward_receipts", "quest_v1_reward_receipts_append_only"),
    )),
    ("rhythm_v2", rhythm_v2.ensure_tables, (
        ("rhythm_v2_integrity_reviews", "rhythm_v2_integrity_reviews_append_only"),
    )),
    ("achievements_v1", achievements_v1.ensure_tables, (
        ("achievement_v1_metric_receipts", "achievement_v1_metric_receipts_append_only"),
        ("achievement_v1_active_weeks", "achievement_v1_active_weeks_append_only"),
        ("achievement_v1_reward_receipts", "achievement_v1_reward_receipts_append_only"),
    )),
    ("pets_v1", pets_v1.ensure_tables, (
        ("pet_v1_activity_rewards", "pet_v1_activity_rewards_append_only"),
        ("pet_v1_duplicate_sources", "pet_v1_duplicate_sources_append_only"),
        ("pet_v1_duplicate_progressions", "pet_v1_duplicate_progressions_append_only"),
    )),
    ("shop_v1", shop_v1.ensure_tables, (
        ("shop_purchases_v1", "shop_purchases_v1_append_only"),
    )),
    ("gifts_v2", gifts_v2.ensure_tables, (
        ("gift_sends_v2", "gift_sends_v2_append_only"),
    )),
    ("echo_shards_v1", echo_shards_v1.ensure_tables, (
        ("echo_shard_ledger_v1", "echo_shard_ledger_append_only_v1"),
        ("echo_shard_compensations_v1", "echo_shard_compensations_append_only_v1"),
    )),
)


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {'postgres', 'postgresql'} or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise argparse.ArgumentTypeError('only a loopback PostgreSQL DSN is allowed')
    return value


async def _assert_race_safe(dsn: str, name: str, ensure, pairs: tuple[tuple[str, str], ...]) -> None:
    main = await asyncpg.connect(dsn)
    try:
        db = PGAdapter(main)
        await ensure(db)  # cold install
        await ensure(db)  # a repeat request must stay a no-op
        for table, trigger in pairs:
            # The production state: the schema is installed, the trigger is (re)missing
            # when the very first parallel requests land.
            await db.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        cold = [await asyncpg.connect(dsn) for _ in range(3)]
        try:
            await asyncio.gather(*(ensure(PGAdapter(conn)) for conn in cold))
        finally:
            for conn in cold:
                await conn.close()
        for table, trigger in pairs:
            async with db.execute(
                "SELECT COUNT(*) FROM pg_trigger WHERE tgname=? AND tgrelid=?::regclass AND NOT tgisinternal",
                (trigger, table),
            ) as cursor:
                created = int((await cursor.fetchone())[0])
            assert created == 1, f"{name}: {trigger} must exist exactly once after the race, got {created}"
        print(f"race_ok {name} triggers={len(pairs)}")
    finally:
        await main.close()


async def run(dsn: str) -> None:
    admin = await asyncpg.connect(dsn)
    try:
        # economic_operations is the FK root of the chest/gift/shop receipts.
        await economy_ledger.ensure_tables(PGAdapter(admin))
    finally:
        await admin.close()
    for name, ensure, pairs in REPOS:
        await _assert_race_safe(dsn, name, ensure, pairs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dsn', type=local_dsn, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.dsn))
    print('test_ensure_tables_race_pg: OK')
