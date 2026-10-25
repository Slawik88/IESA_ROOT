"""Loopback PostgreSQL proof: real pet actions, demo XP, retries and failure isolation."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
import subprocess
from unittest.mock import patch
from urllib.parse import urlparse

os.environ.setdefault("BOT_TOKEN", "123456:offline-tests")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg

from core.league_pass import PET_XP
from core.league_v1 import DEMO_SEASON, FLAG_KEY
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import league_v1 as repo, pets_v1 as v1, pets_v2 as v2
from services import admin_access, league_v1 as league, pet_actions, pet_equipment, pets_v1, pets_v2

USER, PLAYER = 991221, 991222


def local_dsn(value: str) -> str:
    if urlparse(value).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only loopback PostgreSQL is allowed")
    return value


async def run(dsn: str) -> None:
    # Pet services must remain importable without Telegram credentials/config.
    clean_env = {k: v for k, v in os.environ.items() if k not in {"BOT_TOKEN", "DATABASE_URL", "PREDVESTNIK_DATABASE_URL"}}
    subprocess.run(
        [sys.executable, "-c", "import services.pets_v1, services.pets_v2, services.pet_equipment, services.pet_levels_v1"],
        cwd=Path(__file__).resolve().parents[1], env=clean_env, check=True, capture_output=True,
    )
    connection = await asyncpg.connect(dsn)
    other = await asyncpg.connect(dsn)
    db, db2 = PGAdapter(connection), PGAdapter(other)
    try:
        await v1.ensure_tables(db)
        await v2.ensure_tables(db)
        await repo.ensure_tables(db)
        await admin_access.ensure_schema(db)
        from infrastructure.repositories import league_pass as pass_repo
        await pass_repo.ensure_tables(db)
        for uid, rank in ((USER, 1), (PLAYER, 0)):
            await db.execute("INSERT INTO users(user_tg_id,bot_rank) VALUES (?,?) ON CONFLICT(user_tg_id) DO UPDATE SET bot_rank=EXCLUDED.bot_rank", (uid, rank))
            await repo.reset(db, user_id=uid, season=DEMO_SEASON)
            await db.execute("DELETE FROM pet_v2_runs WHERE user_id=?", (uid,))
            for table in ("pet_v1_actions", "pet_v2_actions"):
                await db.execute(f"DELETE FROM {table} WHERE user_id=?", (uid,))
            for table in ('league_pass_receipts', 'league_pass_days', 'league_pass_progress'):
                await db.execute(f'DELETE FROM {table} WHERE user_id=?', (uid,))
        await db.execute("INSERT INTO admin_role_grants(key,min_rank,updated_by) VALUES (?,1,1) ON CONFLICT(key) DO UPDATE SET min_rank=1", (FLAG_KEY,))
        async with db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,'Demo pet','moss_cat','common') RETURNING id", (USER,)) as cur:
            pet = int((await cur.fetchone())[0])

        async def xp() -> int:
            return await repo.pet_xp(db, user_id=USER, season=DEMO_SEASON)

        async def food(n: int) -> None:
            await db.execute("INSERT INTO chest_food_balances_v1(user_id,food_id,quantity) VALUES (?, 'food_basic',?) "
                             "ON CONFLICT(user_id,food_id) DO UPDATE SET quantity=EXCLUDED.quantity", (USER, n))

        def feeding(action_id: str, adapter=db):
            return pets_v2.feed_pet(adapter, user_id=USER, pet_id=pet, food_id="food_basic", action_id=action_id)

        FEED = PET_XP["feed"]
        # Free toggles never award (core.league_pass.PET_XP): a tap loop is not a farm.
        await pets_v1.select_active_pet(db, USER, pet, "active")
        gear = dict(user_id=USER, pet_id=pet, operation="starter", item=None, expected_tier=0, action_id="same-id")
        await pet_equipment.change(db, **gear)
        assert (await pet_equipment.change(db, **gear))["idempotent_replay"]
        await pets_v2.overview(db, USER)
        await pets_v2.preview_run(db, user_id=USER, pet_id=pet, kind="trek", hours=3, route="forest")
        trip = dict(user_id=USER, pet_id=pet, kind="trek", hours=3, route="forest", action_id="trip")
        await pets_v2.start_run(db, **trip)
        assert (await pets_v2.start_run(db, **trip))["idempotent_replay"]
        assert await xp() == 0, "active pet, starter gear, reads, previews and a Trail start give nothing"

        # Two real feeds race on the existing pet lock with one action id: one award.
        await food(5)
        results = await asyncio.gather(*(feeding("race", adapter) for adapter in (db, db2)))
        assert sum(bool(r.get("idempotent_replay")) for r in results) == 1
        assert await xp() == FEED
        assert (await feeding("race"))["idempotent_replay"] and await xp() == FEED
        try:
            await pets_v2.feed_pet(db, user_id=USER, pet_id=pet + 999999, food_id="food_basic", action_id="invalid")
        except pets_v2.PetV2PolicyError:
            pass
        else:
            raise AssertionError("an unowned pet must be rejected")
        assert await xp() == FEED

        # Optional demo failure leaves the real action committed and connection usable.
        async def fail_award(*args, **kwargs):
            await db.execute("SELECT * FROM intentionally_missing_demo_xp_table")

        with patch.object(repo, "add_pet_xp", side_effect=fail_award):
            result = await feeding("award-failed")
        assert not result.get("idempotent_replay") and await v2.cached_action(db, USER, "award-failed")
        assert await xp() == FEED

        # A later failure in the real writer still rolls back the receipt AND XP.
        try:
            async with connection.transaction():
                await feeding("outer-rollback")
                assert await xp() == 2 * FEED
                raise RuntimeError("rollback original action")
        except RuntimeError:
            pass
        assert await xp() == FEED and not await v2.cached_action(db, USER, "outer-rollback")

        # Threshold changes take effect immediately; ordinary users never earn.
        await db.execute("UPDATE admin_role_grants SET min_rank=5 WHERE key=?", (FLAG_KEY,))
        await feeding("gate-closed")
        await pet_actions.record_pet_event(db, user_id=PLAYER, kind="feed", event_id="ordinary")
        assert await xp() == FEED and await repo.pet_xp(db, user_id=PLAYER, season=DEMO_SEASON) == 0
        await db.execute("UPDATE admin_role_grants SET min_rank=1 WHERE key=?", (FLAG_KEY,))

        # Public launch: the same counted action goes to the real pass, never to the demo.
        from services import league_pass
        with patch.object(pet_actions, "_demo_active", return_value=False), patch.object(repo, "add_pet_xp") as award, \
                patch.object(league_pass, "record_pet") as real:
            await pet_actions.record_pet_event(db, user_id=USER, kind="feed", event_id="public-season")
            await pet_actions.record_pet_event(db, user_id=USER, kind=None, event_id="free-toggle")
            award.assert_not_awaited()
            real.assert_awaited_once_with(db, user_id=USER, kind="feed", event_id="public-season")
        # The response saved for an uncertain/retried action includes the credited pass XP.
        from core import league_pass as pass_rules
        from datetime import datetime, timezone
        if pass_rules.active(datetime.now(timezone.utc)):
            async with connection.transaction():
                await food(2)
                with patch.object(pet_actions, '_demo_active', return_value=False):
                    public = await feeding('public-receipt')
                    replay = await feeding('public-receipt')
                assert public['pass_xp'] == FEED and not public.get('idempotent_replay')
                assert replay['pass_xp'] == FEED and replay['idempotent_replay']
                saved = await v2.cached_action(db, USER, 'public-receipt')
                assert saved['response']['pass_xp'] == FEED
        assert await xp() == FEED

        # Combine game/pet progress without changing game stars/ranks.
        await repo.save_level(db, user_id=USER, season=DEMO_SEASON, game="rhythm", level=1, stars=3, xp=100, best={})
        projection = league.public_profiles.player_projection
        with patch.object(league.public_profiles, "player_projection", wraps=projection) as names:
            view = await league.overview(db, user_id=USER)
            assert names.await_count == 1, "both boards resolve player profiles in one batch"
        assert view["pass"]["xp"] == 100 + FEED and view["pet_xp"] == FEED and view["pets"]["xp"]["feed"] == FEED
        assert view["games"]["rhythm"]["stars"] == 3 and view["pass"]["fake"]

        await league.reset(db, user_id=USER)
        assert (await league.overview(db, user_id=USER))["pass"]["xp"] == 0
        await feeding("race")
        assert await xp() == 0, "old receipts cannot award again after a demo reset"
        await feeding("after-reset")
        assert await xp() == FEED

        # Installed schema performs no DDL; a missing index is repaired without a process cache.
        class Probe:
            connection = db.connection
            statements = []

            def execute(self, sql, args=()):
                self.statements.append(sql)
                return db.execute(sql, args)

        probe = Probe()
        await repo.ensure_tables(probe)
        assert len(probe.statements) == 1 and probe.statements[0].lstrip().startswith("SELECT")
        async with connection.transaction():
            await db.execute("DROP INDEX league_demo_one_active_run")
            assert not await repo._schema_ready(db)
            await repo.ensure_tables(db)
            assert await repo._schema_ready(db)
    finally:
        await other.close()
        await connection.close()
    print("PASS pet XP: only counted actions, concurrent retry, gates, free toggles and reads give nothing, rollback, optional failure, public routing, reset, schema fast path")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    args = parser.parse_args()
    assert not pet_actions._demo_active(pet_actions.league_rules.seasons.SEASON_TWO_START)
    with patch.object(league, "_season", return_value=DEMO_SEASON), patch.object(pet_actions, "_demo_active", return_value=True):
        asyncio.run(run(args.dsn))
