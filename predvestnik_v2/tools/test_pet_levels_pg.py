"""Real PostgreSQL proof for pet level-ups: all-or-nothing payment, replay and the dark flag."""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.pet_levels_v1 import FLAG
from core.pets_v1 import PetPolicyError
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import chests_v1 as chest_repo
from infrastructure.repositories import economy_ledger, system_flags
from infrastructure.repositories import pets_v1 as repo
from infrastructure.repositories import skins_v3 as essence_repo
from services import pet_levels_v1, pets_v1


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def must_reject(coro, exc=PetPolicyError):
    try:
        await coro
    except exc:
        return
    raise AssertionError("Expected %s" % exc.__name__)


async def mora(db, user: int) -> int:
    async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id=?", (user,)) as c:
        return int((await c.fetchone())[0])


async def cards(db, user: int, species: str) -> int:
    return (await repo.card_balances(db, user)).get(species, 0)


async def run(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    await economy_ledger.ensure_tables(db)
    await chest_repo.ensure_tables(db)
    await repo.ensure_tables(db)
    await essence_repo.ensure_tables(db)
    await system_flags.ensure_table(db)
    tx = conn.transaction()
    await tx.start()
    try:
        user, other = 976701, 976702
        for uid in (user, other):
            await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT(user_tg_id) DO NOTHING", (uid,))
        await db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?),(?,?,?,?)",
                         (user, "A", "cat", "common", other, "B", "cat", "common"))
        async with db.execute("SELECT id FROM pets WHERE owner_id=? ORDER BY id", (user,)) as c:
            pet = (await c.fetchone())[0]
        async with db.execute("SELECT id FROM pets WHERE owner_id=? ORDER BY id", (other,)) as c:
            foreign = (await c.fetchone())[0]
        await economy_ledger.apply_balance_change(
            db, user, {"mora": 100}, reason_code="quest_reward", idempotency_key="lvl-test-fund",
            source_type="quest", reference_type="quest_reward", reference_id="lvl-test-fund", note="test")

        # the flag is dark by default
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key=?", (FLAG,))
        await must_reject(pet_levels_v1.level_up_pet(db, user_id=user, pet_id=pet, action_id="off-1"))
        assert (await pets_v1.overview(db, user))["level_up"]["enabled"] is False
        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (FLAG,))

        # no cards -> nothing is charged
        await must_reject(pet_levels_v1.level_up_pet(db, user_id=user, pet_id=pet, action_id="nocards"))
        assert await mora(db, user) == 100
        await db.execute("INSERT INTO chest_pet_card_balances_v1(user_id,species_id,quantity) VALUES (?,?,?)", (user, "cat", 400))

        # a foreign pet is refused
        await must_reject(pet_levels_v1.level_up_pet(db, user_id=user, pet_id=foreign, action_id="foreign"))

        # step 1 -> 2 costs 70 cards + 6 Mora
        first = await pet_levels_v1.level_up_pet(db, user_id=user, pet_id=pet, action_id="up-1")
        assert first["level_after"] == 2 and first["cost"] == {"cards": 70, "mora": 6, "essence": 0}
        assert first["cards_left"] == 330 and await cards(db, user, "cat") == 330 and await mora(db, user) == 94
        replay = await pet_levels_v1.level_up_pet(db, user_id=user, pet_id=pet, action_id="up-1")
        assert replay["idempotent_replay"] and await cards(db, user, "cat") == 330 and await mora(db, user) == 94
        await must_reject(pet_levels_v1.level_up_pet(db, user_id=user, pet_id=foreign, action_id="up-1"), pets_v1.PetConflict)
        shown = await pets_v1.overview(db, user)
        step = shown["level_up"]["steps"][pet]
        assert shown["level_up"]["enabled"] and step["level_after"] == 3 and step["cards"] == 290 and step["cards_have"] == 330
        assert [p for p in shown["pets"] if p["id"] == pet][0]["level"] == 2

        # not enough Mora: the cards stay (all or nothing)
        await db.execute("UPDATE chest_pet_card_balances_v1 SET quantity=5000 WHERE user_id=? AND species_id='cat'", (user,))
        await economy_ledger.apply_balance_change(
            db, user, {"mora": -(await mora(db, user)) + 10}, reason_code="shop_purchase", idempotency_key="lvl-test-drain",
            source_type="shop", reference_type="shop_purchase", reference_id="lvl-test-drain", note="test")
        await must_reject(pet_levels_v1.level_up_pet(db, user_id=user, pet_id=pet, action_id="no-mora-1"))
        await must_reject(pet_levels_v1.level_up_pet(db, user_id=user, pet_id=pet, action_id="no-mora-2"))
        assert await cards(db, user, "cat") == 5000 and await mora(db, user) == 10

        # the step into level 5 needs 20 Essence
        await db.execute("UPDATE pet_v1_state SET level=4 WHERE user_id=? AND pet_id=?", (user, pet))
        await economy_ledger.apply_balance_change(
            db, user, {"mora": 100}, reason_code="quest_reward", idempotency_key="lvl-test-fund-2",
            source_type="quest", reference_type="quest_reward", reference_id="lvl-test-fund-2", note="test")
        await must_reject(pet_levels_v1.level_up_pet(db, user_id=user, pet_id=pet, action_id="no-essence"))
        assert await cards(db, user, "cat") == 5000 and await mora(db, user) == 110
        await essence_repo.essence_apply(db, user, 25, reason="test", reference=None, idempotency_key="lvl-test-essence")
        up = await pet_levels_v1.level_up_pet(db, user_id=user, pet_id=pet, action_id="up-5")
        assert up["level_after"] == 5 and up["cost"]["essence"] == 20
        assert await essence_repo.essence_balance(db, user) == 5 and await cards(db, user, "cat") == 5000 - 1160

        # the maximum level is a wall
        await db.execute("UPDATE pet_v1_state SET level=16 WHERE user_id=? AND pet_id=?", (user, pet))
        await must_reject(pet_levels_v1.level_up_pet(db, user_id=user, pet_id=pet, action_id="max"))
        assert (await pets_v1.overview(db, user))["level_up"]["steps"][pet] is None
        async with db.execute("SELECT COUNT(*) FROM pet_v1_level_ups WHERE user_id=?", (user,)) as c:
            assert (await c.fetchone())[0] == 2                    # only the two paid steps are on record
        print("OK: pet level-ups are dark by default, paid all-or-nothing, replay-safe and capped")
    finally:
        await tx.rollback()
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    asyncio.run(run(parser.parse_args().dsn))
