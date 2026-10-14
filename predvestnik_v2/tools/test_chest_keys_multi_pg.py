"""Real PostgreSQL proof for multi-key events (ECO-02): the VIP milestone key, extras and replays."""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from datetime import date
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.chests_v1 import (
    CATALOG_VERSION, KEY_SOURCE_COUNTS, POLICY_VERSION, canonical_snapshot_fingerprint, catalog_digest,
    key_grant_event_ids,
)
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import chests_v1 as repo
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import vip_v2 as vip_repo
from services import vip


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def _grant(db, user: int, kind: str, event: str) -> int:
    snapshot = {"test": event}
    digest = canonical_snapshot_fingerprint(snapshot)
    account = await repo.lock_account(db, user)
    after = await repo.apply_grant(
        db, grant_id=f"g-{kind}-{event}".replace(" ", "")[:60], user_id=user, source_kind=kind,
        source_event_id=event, amount=1, policy_version=POLICY_VERSION, source_snapshot=snapshot,
        source_snapshot_hash=digest, balance_before=int(account["balance"]),
        account_epoch=int(account["account_epoch"]),
    )
    return await repo.apply_bonus_grants(
        db, user_id=user, source_kind=kind, source_event_id=event, policy_version=POLICY_VERSION,
        source_snapshot=snapshot, source_snapshot_hash=digest, balance_before=after,
        account_epoch=int(account["account_epoch"]),
    )


async def run(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    await economy_ledger.ensure_tables(db)
    await repo.ensure_tables(db)
    await vip_repo.ensure_tables(db)
    tx = conn.transaction()
    await tx.start()
    try:
        # The release constraint must accept every source kind the policy knows (the VIP milestone was missing).
        for index, kind in enumerate(KEY_SOURCE_COUNTS):
            user = 971000 + index
            await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT(user_tg_id) DO NOTHING", (user,))
            if kind == "zarniki_purchase":
                continue  # purchases are covered by test_chests_v1_mixed_pg
            total = await _grant(db, user, kind, f"event-{kind}")
            assert total == KEY_SOURCE_COUNTS[kind] == await repo.get_balance(db, user), kind
            ids = key_grant_event_ids(kind, f"event-{kind}")
            async with db.execute(
                "SELECT source_event_id FROM chest_key_grants_v1 WHERE user_id=? ORDER BY source_event_id", (user,),
            ) as cursor:
                assert [row[0] for row in await cursor.fetchall()] == sorted(ids), kind
            assert await repo.grant_total(db, user_id=user, source_kind=kind, source_event_id=f"event-{kind}") == total

        # LIKE wildcards in an event id must not pull in a neighbour's grants.
        user = 971100
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT(user_tg_id) DO NOTHING", (user,))
        await _grant(db, user, "quest_daily_set_complete", "daily:a_b")
        await _grant(db, user, "quest_daily_set_complete", "daily:aXb")
        assert await repo.grant_total(db, user_id=user, source_kind="quest_daily_set_complete", source_event_id="daily:a_b") == 2
        assert await repo.get_balance(db, user) == 4

        # ECO-04 PR-A: a paid key bought under a retired catalog is a tier-1 key and
        # opens under the current tables; nothing is reported as locked.
        stale_user = 971150
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT(user_tg_id) DO NOTHING", (stale_user,))
        stale_snapshot = {"purchase_id": "old", "catalog_version": "chests-mixed-s1-v2", "catalog_digest": "0" * 64}
        account = await repo.lock_account(db, stale_user)
        after = await repo.apply_grant(
            db, grant_id="g-stale-paid", user_id=stale_user, source_kind="zarniki_purchase",
            source_event_id="stale-purchase", amount=1, policy_version=POLICY_VERSION,
            source_snapshot=stale_snapshot, source_snapshot_hash=canonical_snapshot_fingerprint(stale_snapshot),
            balance_before=int(account["balance"]), account_epoch=int(account["account_epoch"]),
        )
        await _grant(db, stale_user, "quest_daily_set_complete", "daily:stale")
        assert await repo.get_balance(db, stale_user) == 3
        epoch = int(account["account_epoch"])
        oldest = await repo.next_unspent_grant(db, user_id=stale_user, account_epoch=epoch, key_tier=1)
        assert oldest["source_kind"] == "zarniki_purchase"
        args = dict(catalog_version=CATALOG_VERSION, catalog_digest=catalog_digest())
        assert await repo.locked_paid_keys(db, user_id=stale_user, **args) == 0
        assert await repo.openable_balance(db, stale_user, **args) == 3
        assert (await repo.tier_balances(db, stale_user))[1] == 3

        # The VIP seventh-day milestone: real service path, replay writes nothing more.
        vip_user = 971200
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT(user_tg_id) DO NOTHING", (vip_user,))
        await db.execute(
            "INSERT INTO vip_subscriptions(user_id,tier,expires_at,total_days) VALUES (?,'vip',NOW()+INTERVAL '7 days',7)",
            (vip_user,),
        )
        await db.execute(
            "INSERT INTO vip_v2_daily_progress(user_id,completed_count) VALUES (?,6)", (vip_user,),
        )
        day_key = date.today().isoformat()
        first = await vip.complete_daily_mission_from_game(
            db, user_id=vip_user, day_key=day_key, source_event_id="rhythm_completed:milestone",
        )
        assert first and first["completion_no"] == 7 and first["key_reward"] is True
        assert await repo.get_balance(db, vip_user) == KEY_SOURCE_COUNTS["vip_daily_milestone"] == 2
        replay = await vip.complete_daily_mission_from_game(
            db, user_id=vip_user, day_key=day_key, source_event_id="rhythm_completed:other",
        )
        assert replay and replay["already_completed"] and replay["key_reward"] is True
        assert await repo.get_balance(db, vip_user) == 2
        async with db.execute(
            "SELECT COUNT(*) FROM chest_key_grants_v1 WHERE user_id=? AND source_kind='vip_daily_milestone'", (vip_user,),
        ) as cursor:
            assert (await cursor.fetchone())[0] == 2
    finally:
        await tx.rollback()
        await conn.close()
    print("OK: multi-key events write one single-key grant each, VIP milestone key lands, replays add nothing")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    asyncio.run(run(parser.parse_args().dsn))
