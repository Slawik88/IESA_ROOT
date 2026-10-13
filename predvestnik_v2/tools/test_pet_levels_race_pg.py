"""Concurrency proof for pet level-ups on real commits (a 16-connection pool, a throwaway local database).

Unlike test_pet_levels_pg.py this does not run inside one rolled-back transaction: it leaves its rows behind,
so use it only on a scratch database.  Idea and scenarios: the control probe of the ECO-04 review.
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
import time
from collections import Counter
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import chests_v1 as chest_repo
from infrastructure.repositories import economy_ledger, system_flags
from infrastructure.repositories import pets_v1 as repo
from infrastructure.repositories import skins_v3 as essence_repo
from services import pet_levels_v1 as svc


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    setup = await asyncpg.connect(dsn)
    db0 = PGAdapter(setup)
    await economy_ledger.ensure_tables(db0)
    await chest_repo.ensure_tables(db0)
    await repo.ensure_tables(db0)
    await essence_repo.ensure_tables(db0)
    await system_flags.ensure_table(db0)
    await db0.execute("UPDATE system_flags SET enabled=1 WHERE key='pets_level_up_v1'")
    pool = await asyncpg.create_pool(dsn, min_size=16, max_size=16)
    base = 8_000_000 + int(time.time()) % 1_000_000 * 10

    async def make_user(uid, pets, cards, mora, essence):
        await db0.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (uid,))
        ids = []
        for species, rarity in pets:
            await db0.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?)", (uid, "p", species, rarity))
            async with db0.execute("SELECT max(id) FROM pets WHERE owner_id=?", (uid,)) as c:
                ids.append((await c.fetchone())[0])
        for species, quantity in cards.items():
            await db0.execute("INSERT INTO chest_pet_card_balances_v1(user_id,species_id,quantity) VALUES (?,?,?)", (uid, species, quantity))
        if mora:
            await economy_ledger.apply_balance_change(
                db0, uid, {"mora": mora}, reason_code="quest_reward", idempotency_key=f"race-fund-{uid}",
                source_type="quest", reference_type="quest_reward", reference_id=f"race-fund-{uid}", note="test")
        if essence:
            await essence_repo.essence_apply(db0, uid, essence, reason="test", reference=None, idempotency_key=f"race-ess-{uid}")
        return ids

    async def up(uid, pet_id, action_id):
        conn = await pool.acquire()
        try:
            return await svc.level_up_pet(PGAdapter(conn), user_id=uid, pet_id=pet_id, action_id=action_id)
        except Exception as exc:                                    # a refusal is an outcome here, not a crash
            return exc
        finally:
            await pool.release(conn)

    async def books_balance(uid, species, cards0, mora0, essence0, start_levels=0):
        """What was written down must equal what left the balances, and nothing may go negative or repeat."""
        async with db0.execute("SELECT COUNT(*),COALESCE(SUM(cards),0),COALESCE(SUM(mora),0),COALESCE(SUM(essence),0) "
                               "FROM pet_v1_level_ups WHERE user_id=?", (uid,)) as c:
            steps, cards, mora, essence = [int(x) for x in await c.fetchone()]
        async with db0.execute("SELECT quantity FROM chest_pet_card_balances_v1 WHERE user_id=? AND species_id=?", (uid, species)) as c:
            cards_now = int((await c.fetchone())[0])
        async with db0.execute("SELECT user_balance_mora FROM users WHERE user_tg_id=?", (uid,)) as c:
            mora_now = int((await c.fetchone())[0])
        essence_now = await essence_repo.essence_balance(db0, uid)
        async with db0.execute("SELECT COALESCE(SUM(level-1),0) FROM pet_v1_state WHERE user_id=?", (uid,)) as c:
            levels = int((await c.fetchone())[0])
        async with db0.execute("SELECT COUNT(*) FROM (SELECT pet_id,level_before FROM pet_v1_level_ups WHERE user_id=? "
                               "GROUP BY 1,2 HAVING COUNT(*)>1) t", (uid,)) as c:
            duplicates = int((await c.fetchone())[0])
        assert cards_now == cards0 - cards and mora_now == mora0 - mora and essence_now == essence0 - essence
        assert min(cards_now, mora_now, essence_now) >= 0 and duplicates == 0 and levels - start_levels == steps
        return steps

    try:
        # S1: two pets of one species share a card pool; 60 parallel attempts, Mora covers only part of them
        user = base + 1
        a, b = await make_user(user, [("cat", "common"), ("cat", "common")], {"cat": 6000}, 400, 100)
        results = await asyncio.gather(*[up(user, a if i % 2 else b, f"s1-{i}") for i in range(60)])
        applied = sum(1 for r in results if isinstance(r, dict))
        assert 0 < applied < 60
        assert await books_balance(user, "cat", 6000, 400, 100) == applied

        # S2: the very same action_id twelve times at once: one application, eleven replays
        user = base + 2
        (pet,) = await make_user(user, [("fox", "common")], {"fox": 5000}, 5000, 0)
        results = await asyncio.gather(*[up(user, pet, "same-1") for _ in range(12)])
        kinds = Counter("replay" if isinstance(r, dict) and r["idempotent_replay"] else "ok" if isinstance(r, dict) else "error" for r in results)
        assert kinds == {"ok": 1, "replay": 11}, kinds
        assert await books_balance(user, "fox", 5000, 5000, 0) == 1

        # S3: the step into L5 needs 20 Essence; with 19 nothing is taken
        user = base + 3
        (pet,) = await make_user(user, [("owl", "common")], {"owl": 100_000}, 100_000, 19)
        await db0.execute("INSERT INTO pet_v1_state(user_id,pet_id,level) VALUES (?,?,4) ON CONFLICT(user_id,pet_id) DO UPDATE SET level=4", (user, pet))
        outcome = await up(user, pet, "ess-1")
        assert not isinstance(outcome, dict)
        assert await books_balance(user, "owl", 100_000, 100_000, 19, start_levels=3) == 0
        print("OK: pet level-ups survive 60 parallel attempts, 12 identical action ids and an Essence shortage")
    finally:
        await pool.close()
        await setup.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    asyncio.run(run(parser.parse_args().dsn))
