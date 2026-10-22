"""Read-only pet projections: quote query budget, rounding, busy state and optional baseline parity."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
from pathlib import Path
import random
import sys

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import pet_equipment as gear_rules, pets_v2 as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import pet_equipment as gear_repo, pets_v2 as repo
from services import pets_v2 as service
from tools.test_pets_v2_pg import local_dsn

USER, OTHER = 99862101, 99862102


class ReadProbe:
    def __init__(self, db):
        self.db = db
        self.connection = db.connection
        self.statements = []

    def execute(self, sql, args=()):
        assert sql.lstrip().upper().startswith("SELECT"), f"read path attempted a write: {sql}"
        self.statements.append(sql)
        return self.db.execute(sql, args)


async def run(dsn, baseline=None):
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    await repo.ensure_tables(db)
    tx = conn.transaction()
    await tx.start()
    comparisons = 0
    counts = []
    try:
        for uid in (USER, OTHER):
            await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (uid,))
        pets = []
        for index, species in enumerate([*list(rules.SPECIES)[:4], "legacy_unknown"]):
            async with db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,'common') RETURNING id", (USER, f"Read pet {index}", species)) as cur:
                pets.append(int((await cur.fetchone())[0]))
        primary, companion = pets[:2]
        # The fifth, unsupported species still unlocks a pair, as in the original overview.
        assert len({*list(rules.SPECIES)[:4], "legacy_unknown"}) == rules.PAIR_MIN_SPECIES
        for pet in pets[:3]:
            await repo.ensure_state(db, USER, pet, 100)
        await db.execute("UPDATE pet_v2_state SET level=12,energy=80,energy_at=NOW()-INTERVAL '2 hours',xp=12.34 WHERE user_id=?", (USER,))
        # Raw 14.96 rounds to 15.0: preserve the existing preview eligibility boundary.
        await db.execute("UPDATE pet_v2_state SET energy=14.96,energy_at=NOW() WHERE user_id=? AND pet_id=?", (USER, primary))
        for index, kind in enumerate(list(rules.TALISMANS)[:2]):
            await db.execute("INSERT INTO pet_v2_talismans(id,user_id,kind,tier,pet_id) VALUES (?,?,?,1,?)", (f"read-{primary}-{index}", USER, kind, primary))
        await db.execute("INSERT INTO pet_v2_talismans(id,user_id,kind,tier,pet_id) VALUES (?,?,?,1,NULL)", (f"read-{primary}-loose", USER, next(iter(rules.TALISMANS))))
        await db.execute("INSERT INTO pet_v2_bond_days(user_id,pet_id,day) VALUES (?,?,CURRENT_DATE-1)", (USER, primary))
        await db.execute("INSERT INTO pet_v2_camp(user_id,building,level) VALUES (?,'markers',2)", (USER,))
        await db.execute("INSERT INTO pet_v2_camp_jobs(user_id,building,to_level,ends_at) VALUES (?,'lounge',2,NOW()-INTERVAL '1 hour')", (USER,))

        # Camp projection preserves default, completed, unfinished and lower-target behavior.
        camp_probe = ReadProbe(db)
        assert await repo.camp_levels(camp_probe, USER) == {"lounge": 2, "markers": 2, "workshop": 0}
        assert len(camp_probe.statements) == 1
        assert await repo.camp_levels(ReadProbe(db), OTHER) == {"lounge": 0, "markers": 0, "workshop": 0}
        await db.execute("UPDATE pet_v2_camp_jobs SET ends_at=NOW()+INTERVAL '1 hour' WHERE user_id=?", (USER,))
        assert await repo.camp_levels(ReadProbe(db), USER) == {"lounge": 0, "markers": 2, "workshop": 0}
        await db.execute("UPDATE pet_v2_camp_jobs SET building='markers',to_level=1,ends_at=NOW()-INTERVAL '1 hour' WHERE user_id=?", (USER,))
        assert await repo.camp_levels(ReadProbe(db), USER) == {"lounge": 0, "markers": 2, "workshop": 0}
        await db.execute("UPDATE pet_v2_camp_jobs SET building='lounge',to_level=2 WHERE user_id=?", (USER,))

        async def compare(kwargs):
            nonlocal comparisons
            probe = ReadProbe(db)
            try:
                actual = await service.preview_run(probe, user_id=USER, **kwargs)
            except rules.PetV2PolicyError as error:
                actual = str(error)
            assert len(probe.statements) <= 10, len(probe.statements)
            if baseline:
                old_probe = ReadProbe(db)
                try:
                    expected = await baseline.preview_run(old_probe, user_id=USER, **kwargs)
                except rules.PetV2PolicyError as error:
                    expected = str(error)
                assert actual == expected, (kwargs, actual, expected)
                counts.append((len(old_probe.statements), len(probe.statements)))
            comparisons += 1
            return actual

        async def check_overview():
            nonlocal comparisons
            view = await service.overview(ReadProbe(db), USER)
            if baseline:
                assert view == await baseline.overview(ReadProbe(db), USER)
            assert view["pair"]["unlocked"] and len(view["pets"]) == 4
            assert view["camp"]["levels"] == {"lounge": 2, "markers": 2, "workshop": 0}
            assert pets[4] not in [p["id"] for p in view["pets"]]
            comparisons += 1
            return view

        await check_overview()
        quote = dict(pet_id=primary, kind="trek", hours=3, route="forest")
        assert (await compare(quote))["can_start"], "display rounding must remain unchanged"
        await db.execute("UPDATE pet_v2_state SET energy=14.94 WHERE user_id=? AND pet_id=?", (USER, primary))
        assert (await compare(quote))["reasons"] == ["Не хватает сил."]
        await db.execute("UPDATE pet_v2_state SET energy=80 WHERE user_id=?", (USER,))
        for kind, hours, route in (("trek", 6, "pass"), ("expedition", 9, "ruins"), ("watch", 12, None), ("watch", 24, None)):
            await compare(dict(pet_id=primary, kind=kind, hours=hours, route=route))
        await compare({**quote, "companion_id": companion})
        await compare({**quote, "pet_id": pets[3]})  # no stored state
        for changes in ({"pet_id": pets[4]}, {"pet_id": -1}, {"companion_id": primary}, {"companion_id": pets[4]}, {"companion_id": -1}):
            assert isinstance(await compare({**quote, **changes}), str)

        # Full slots, primary/companion overlap and ready expedition preserve priority and reason order.
        for index, pet in enumerate(pets[:3]):
            await repo.create_run(db, run_id=f"read-run-{primary}-{index}", user_id=USER, pet_id=pet,
                                  kind="expedition" if index == 0 else "trek", hours=3, route="forest",
                                  companion_id=companion if index == 0 else None)
        await db.execute("UPDATE pet_v2_runs SET ends_at=NOW()-INTERVAL '1 minute' WHERE user_id=?", (USER,))
        await db.execute("UPDATE pet_v2_state SET energy=0,energy_at=NOW() WHERE user_id=?", (USER,))
        view = await check_overview()
        assert next(p for p in view["pets"] if p["id"] == companion)["run_id"].endswith("-1")
        assert (await compare({**quote, "companion_id": companion}))["reasons"] == [
            "Питомец или спутник уже в пути.", "Все слоты заняты.", "Не хватает сил.",
        ]
        await db.execute("DELETE FROM pet_v2_runs WHERE user_id=?", (USER,))
        state = gear_rules.new_outing(random.Random(7).sample(range(len(gear_rules.EVENTS)), gear_rules.STEPS), ())
        await gear_repo.create_outing(db, USER, primary, f"read-outing-{primary}", (await repo.clock(db))["day"], state)
        assert (await compare(quote))["reasons"][0] == "Питомец или спутник уже в пути."
        await check_overview()

        # No hidden writes: every observed statement was SELECT; all fixtures roll back.
        print(f"PASS pet read paths: {comparisons} scenarios, SELECT only, quote <=10 queries")
        if counts:
            print("baseline -> optimized query counts:", sorted(set(counts)))
    finally:
        await tx.rollback()
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    parser.add_argument("--baseline", type=Path, help="optional saved pre-change services/pets_v2.py for exact DTO comparison")
    parser.add_argument("--baseline-repository", type=Path, help="optional saved pre-change infrastructure/repositories/pets_v2.py")
    args = parser.parse_args()
    baseline = None
    if args.baseline:
        spec = importlib.util.spec_from_file_location("pets_read_baseline", args.baseline)
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        if args.baseline_repository:
            repo_spec = importlib.util.spec_from_file_location("pets_repo_baseline", args.baseline_repository)
            baseline.repo = importlib.util.module_from_spec(repo_spec)
            repo_spec.loader.exec_module(baseline.repo)
    asyncio.run(run(args.dsn, baseline))
