"""PostgreSQL proof for paid keys and every mixed-loot delivery writer."""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.chests_v1 import CATALOG_VERSION, PET_SPECIES, ChestOutcome, catalog_digest
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import chests_v1 as repo, economy_ledger
from services import chests_v1


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only loopback PostgreSQL is allowed")
    return value


async def direct_key(db, user_id: int, source: str) -> None:
    account = await repo.lock_account(db, user_id)
    snapshot = {"test": source}
    from core.chests_v1 import canonical_snapshot_fingerprint
    await repo.apply_grant(
        db, grant_id=uuid4().hex, user_id=user_id, source_kind="quest_daily_set_complete",
        source_event_id=source, amount=1, policy_version="test", source_snapshot=snapshot,
        source_snapshot_hash=canonical_snapshot_fingerprint(snapshot),
        balance_before=account["balance"], account_epoch=account["account_epoch"],
    )


async def open_as(db, user_id: int, action: str, outcome: ChestOutcome) -> dict:
    original = chests_v1.roll_outcome
    chests_v1.roll_outcome = lambda *_args, **_kwargs: outcome
    try:
        prepared = await chests_v1.prepare_free_open(
            db, user_id=user_id, action_id=action, requested_catalog_version=CATALOG_VERSION,
            requested_catalog_digest=catalog_digest(),
        )
    finally:
        chests_v1.roll_outcome = original
    return await chests_v1.reveal(db, user_id=user_id, open_id=prepared["open_id"])


async def run(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    await economy_ledger.ensure_tables(db)
    await repo.ensure_tables(db)
    tx = conn.transaction()
    await tx.start()
    try:
        user = 986_000_000 + uuid4().int % 1_000_000
        await economy_ledger.apply_balance_change(
            db, user, {"zarniki": 100}, reason_code="stars_purchase",
            idempotency_key=f"mixed-test-fund:{user}", source_type="telegram_stars",
            reference_type="test", reference_id=str(user),
        )
        first = await chests_v1.purchase_key(
            db, user_id=user, action_id="buy-1", requested_catalog_version=CATALOG_VERSION,
            requested_catalog_digest=catalog_digest(),
        )
        replay = await chests_v1.purchase_key(
            db, user_id=user, action_id="buy-1", requested_catalog_version=CATALOG_VERSION,
            requested_catalog_digest=catalog_digest(),
        )
        second = await chests_v1.purchase_key(
            db, user_id=user, action_id="buy-2", requested_catalog_version=CATALOG_VERSION,
            requested_catalog_digest=catalog_digest(),
        )
        assert first["applied"] and not replay["applied"] and replay["purchase_id"] == first["purchase_id"]
        assert second["key_balance"] == 2 and await repo.paid_purchases_today(db, user_id=user) == 2
        try:
            await chests_v1.purchase_key(
                db, user_id=user, action_id="buy-3", requested_catalog_version=CATALOG_VERSION,
                requested_catalog_digest=catalog_digest(),
            )
        except chests_v1.ChestKeyConflict:
            pass
        else:
            raise AssertionError("third UTC-day purchase must fail")
        async with db.execute("SELECT user_balance_zarniki FROM users WHERE user_tg_id=?", (user,)) as cursor:
            assert float((await cursor.fetchone())[0]) == 80

        food = await open_as(db, user, "food", ChestOutcome(0, 1, "food", 1, "food_basic"))
        pet = await open_as(db, user, "pet", ChestOutcome(6200, 3, "pet_card", 4, "moss_cat", "common"))
        assert food["reward"]["ref"] == "food_basic" and pet["reward"]["ref"] == "moss_cat"
        inventory = await repo.inventory_summary(db, user_id=user)
        assert inventory["foods"]["food_basic"] == 1
        assert inventory["pet_cards"]["moss_cat"] == 3 and "moss_cat" in inventory["unlocked_pets"]

        delivery_cases = (
            ChestOutcome(0, 1, "mora", 22), ChestOutcome(9000, 5, "diamonds", 1),
            ChestOutcome(9970, 10, "zarniki", 30), ChestOutcome(9000, 5, "joker", 2, "rare", "rare"),
            ChestOutcome(9970, 10, "pet_card", 5, "moss_cat", "common"),
            ChestOutcome(9970, 10, "vip_days", 4),
            ChestOutcome(9970, 10, "vip_cosmetic", 1, "cos_card_fx_embers", "vip"),
        )
        for index, outcome in enumerate(delivery_cases):
            await direct_key(db, user, f"mixed:{index}")
            result = await open_as(db, user, f"mixed-open:{index}", outcome)
            replayed = await chests_v1.reveal(db, user_id=user, open_id=result["open_id"])
            assert result == replayed and result["reward"]["kind"] == outcome.reward_kind
        inventory = await repo.inventory_summary(db, user_id=user)
        assert inventory["pet_cards"]["moss_cat"] == 8 and inventory["jokers"]["rare"] == 2
        assert PET_SPECIES["moss_cat"]["rarity"] == "common"
        async with db.execute("SELECT COUNT(*) FROM chest_deliveries_v1 WHERE user_id=?", (user,)) as cursor:
            assert int((await cursor.fetchone())[0]) == 9
        async with db.execute("SELECT metric,COUNT(*) FROM quest_v1_metric_receipts WHERE user_id=? GROUP BY metric", (user,)) as cursor:
            metrics = {str(row[0]): int(row[1]) for row in await cursor.fetchall()}
        assert metrics["chest_revealed"] == 9 and "pet_card_found" not in metrics
        async with db.execute("SELECT COUNT(*) FROM achievement_v1_metric_receipts WHERE user_id=? AND family='chests'", (user,)) as cursor:
            assert int((await cursor.fetchone())[0]) == 9
        async with db.execute("SELECT COUNT(*) FROM pet_v1_duplicate_progressions WHERE user_id=?", (user,)) as cursor:
            assert int((await cursor.fetchone())[0]) == 0
        async with db.execute("SELECT COUNT(*) FROM pet_v1_duplicate_sources WHERE user_id=?", (user,)) as cursor:
            assert int((await cursor.fetchone())[0]) == 0

        legacy_user = user + 20
        await db.execute(
            "INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?)",
            (legacy_user, "Старый моховой кот", "moss_cat", "common"),
        )
        await direct_key(db, legacy_user, "legacy-pet")
        legacy_delivery = await open_as(
            db, legacy_user, "legacy-pet-open", ChestOutcome(6200, 3, "pet_card", 4, "moss_cat", "common"),
        )
        assert legacy_delivery["reward"]["amount"] == 4
        async with db.execute("SELECT COUNT(*) FROM pets WHERE owner_id=? AND species_id='moss_cat'", (legacy_user,)) as cursor:
            assert int((await cursor.fetchone())[0]) == 1, "an existing canonical pet must not be unlocked twice"
        legacy_inventory = await repo.inventory_summary(db, user_id=legacy_user)
        assert legacy_inventory["pet_cards"]["moss_cat"] == 4, "legacy ownership must not consume a new unlock card"

        refund_user = user + 1
        await economy_ledger.apply_balance_change(
            db, refund_user, {"zarniki": 20}, reason_code="stars_purchase",
            idempotency_key=f"mixed-refund-fund:{refund_user}", source_type="telegram_stars",
            reference_type="test", reference_id=str(refund_user),
        )
        bought = await chests_v1.purchase_key(
            db, user_id=refund_user, action_id="refund-buy", requested_catalog_version=CATALOG_VERSION,
            requested_catalog_digest=catalog_digest(),
        )
        refunded = await chests_v1.refund_unused_purchase(
            db, user_id=refund_user, purchase_id=bought["purchase_id"], action_id="refund-action",
        )
        refund_replay = await chests_v1.refund_unused_purchase(
            db, user_id=refund_user, purchase_id=bought["purchase_id"], action_id="refund-action",
        )
        assert refunded["applied"] and not refund_replay["applied"] and refunded["key_balance"] == 0
        async with db.execute("SELECT user_balance_zarniki FROM users WHERE user_tg_id=?", (refund_user,)) as cursor:
            assert float((await cursor.fetchone())[0]) == 20
        try:
            await chests_v1.prepare_free_open(
                db, user_id=refund_user, action_id="after-refund", requested_catalog_version=CATALOG_VERSION,
                requested_catalog_digest=catalog_digest(),
            )
        except chests_v1.ChestKeyConflict:
            pass
        else:
            raise AssertionError("refunded entitlement must not remain spendable")
    finally:
        await tx.rollback()
        await conn.close()

    race_user = 987_000_000 + uuid4().int % 1_000_000
    setup = await asyncpg.connect(dsn)
    setup_db = PGAdapter(setup)
    await economy_ledger.apply_balance_change(
        setup_db, race_user, {"zarniki": 100}, reason_code="stars_purchase",
        idempotency_key=f"mixed-race-fund:{race_user}", source_type="telegram_stars",
        reference_type="test", reference_id=str(race_user),
    )
    await setup_db.commit()
    await setup.close()
    connections = [await asyncpg.connect(dsn) for _ in range(3)]

    async def buy(index: int):
        try:
            return await chests_v1.purchase_key(
                PGAdapter(connections[index]), user_id=race_user, action_id=f"race-buy-{index}",
                requested_catalog_version=CATALOG_VERSION, requested_catalog_digest=catalog_digest(),
            )
        except chests_v1.ChestKeyConflict:
            return None

    try:
        results = await asyncio.gather(*(buy(index) for index in range(3)))
        assert sum(result is not None for result in results) == 2
        check = PGAdapter(connections[0])
        assert await repo.get_balance(check, race_user) == 2
        async with check.execute("SELECT user_balance_zarniki FROM users WHERE user_tg_id=?", (race_user,)) as cursor:
            assert float((await cursor.fetchone())[0]) == 80
    finally:
        await asyncio.gather(*(connection.close() for connection in connections))
    print("OK: paid quota/provenance and every mixed reward deliver atomically without compensation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    asyncio.run(run(parser.parse_args().dsn))
