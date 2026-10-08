"""Real PostgreSQL proof for pets v2 «Тропа»: норма, находки, энергия, исходы, идемпотентность."""
from __future__ import annotations
import argparse, asyncio, pathlib, random, sys
from urllib.parse import urlparse
import asyncpg
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from core import pets_v2 as rules
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import (
    achievements_v1, chests_v1, pets_v2 as repo, quests_v1 as quests_repo, skins_v3, vip_v2,
)
from services import pets_v2 as service
from services import quests_v1


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def finish_now(db, run_id: str) -> None:
    await db.execute("UPDATE pet_v2_runs SET ends_at=NOW()-INTERVAL '1 minute' WHERE id=?", (run_id,))


async def balance(db, user: int, column: str) -> float:
    async with db.execute(f"SELECT {column} FROM users WHERE user_tg_id=?", (user,)) as c:
        row = await c.fetchone()
    return float(row[0] or 0) if row else 0.0


async def run(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    tx = conn.transaction()
    await tx.start()
    try:
        for module in (chests_v1, achievements_v1, skins_v3, vip_v2, quests_repo, repo):
            await module.ensure_tables(db)
        user, other = 977201, 977202
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?),(?) ON CONFLICT DO NOTHING", (user, other))
        await db.execute(
            "INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?),(?,?,?,?),(?,?,?,?),(?,?,?,?)",
            (user, "Кот", "moss_cat", "common", user, "Сова", "mirror_owl", "rare", user, "Лис", "salt_fox", "uncommon", user, "Жук", "stone_beetle", "common"),
        )
        async with db.execute("SELECT id FROM pets WHERE owner_id=? ORDER BY id", (user,)) as c:
            cat, owl, fox, beetle = [r[0] for r in await c.fetchall()]
        rng = random.Random(7)

        # обзор только читает
        view = await service.overview(db, user)
        assert len(view["pets"]) == 4 and view["pets"][0]["energy"] == rules.energy_max(1, "moss_cat")
        async with db.execute("SELECT COUNT(*) FROM pet_v2_state WHERE user_id=?", (user,)) as c:
            assert (await c.fetchone())[0] == 0

        # старт, повтор, чужой питомец, занят, слоты
        started = await service.start_run(db, user_id=user, pet_id=cat, kind="trek", hours=3, route="forest", action_id="s1")
        assert started["energy"] == rules.energy_max(1, "moss_cat") - 15
        again = await service.start_run(db, user_id=user, pet_id=cat, kind="trek", hours=3, route="forest", action_id="s1")
        assert again["idempotent_replay"] and again["run_id"] == started["run_id"]
        async with db.execute("SELECT energy FROM pet_v2_state WHERE user_id=? AND pet_id=?", (user, cat)) as c:
            assert (await c.fetchone())[0] == started["energy"], "replay must not debit energy twice"
        for bad in (
            service.start_run(db, user_id=other, pet_id=cat, kind="trek", hours=3, route="forest", action_id="x1"),
            service.start_run(db, user_id=user, pet_id=cat, kind="trek", hours=6, route="forest", action_id="x2"),
            service.start_run(db, user_id=user, pet_id=owl, kind="trek", hours=4, route="forest", action_id="x3"),
            service.start_run(db, user_id=user, pet_id=cat, kind="trek", hours=3, route="forest", action_id="s1b"),
        ):
            try:
                async with db.connection.transaction():
                    await bad
            except rules.PetV2PolicyError:
                continue
            raise AssertionError("must reject")
        await service.start_run(db, user_id=user, pet_id=owl, kind="expedition", hours=3, route="ruins", action_id="s2")
        await service.start_run(db, user_id=user, pet_id=fox, kind="watch", hours=12, route=None, action_id="s3")
        try:
            async with db.connection.transaction():
                await service.start_run(db, user_id=user, pet_id=beetle, kind="trek", hours=3, route="pass", action_id="s4")
        except service.PetV2Conflict:
            pass
        else:
            raise AssertionError("slots must be limited")

        # нельзя забрать раньше срока
        try:
            async with db.connection.transaction():
                await service.claim_run(db, user_id=user, run_id=started["run_id"], action_id="c0", rng=rng)
        except service.PetV2Conflict:
            pass
        else:
            raise AssertionError("claim before ends_at")

        # поход: Следы, находки, ночь связи, повтор возврата
        await finish_now(db, started["run_id"])
        done = await service.claim_run(db, user_id=user, run_id=started["run_id"], action_id="c1", rng=rng)
        assert done["xp_credited"] > 0 and done["bond_days"] == 1
        replay = await service.claim_run(db, user_id=user, run_id=started["run_id"], action_id="c1", rng=rng)
        assert replay["idempotent_replay"] and replay["xp_credited"] == done["xp_credited"]
        async with db.execute("SELECT credited,raw FROM pet_v2_daily WHERE user_id=?", (user,)) as c:
            row = await c.fetchone()
        assert abs(row[0] - done["xp_credited"]) < 1e-6
        try:
            async with db.connection.transaction():
                await service.claim_run(db, user_id=user, run_id=started["run_id"], action_id="c1-other", rng=rng)
        except service.PetV2Conflict:
            pass
        else:
            raise AssertionError("a finished run must not be claimed twice")

        # экспедиция: путь обязателен, подсказка сервера соответствует правилам
        await db.execute("UPDATE pet_v2_runs SET ends_at=NOW()-INTERVAL '1 minute' WHERE status='active'")
        view = await service.overview(db, user)
        decision = next(a for a in view["activities"] if a["kind"] == "expedition")["decision"]
        assert decision["detail"] == "exact" and set(decision["paths"]) == set(rules.PATHS)
        exp_id = next(a["id"] for a in view["activities"] if a["kind"] == "expedition")
        try:
            async with db.connection.transaction():
                await service.claim_run(db, user_id=user, run_id=exp_id, action_id="e0", rng=rng)
        except rules.PetV2PolicyError:
            pass
        else:
            raise AssertionError("expedition needs a path")
        result = await service.claim_run(db, user_id=user, run_id=exp_id, action_id="e1", path="steady", rng=rng)
        assert result["outcome"] in ("success", "partial", "fail") and 5 <= result["chance"] <= 95
        assert abs(result["chance"] - decision["paths"]["steady"]["chance"]) < 0.11, "hint must equal the real chance"

        # суточная норма не пробивается
        await db.execute("UPDATE pet_v2_runs SET status='claimed' WHERE user_id=? AND status='active'", (user,))
        for i in range(12):
            await db.execute("UPDATE pet_v2_state SET energy=? WHERE user_id=? AND pet_id=?", (rules.energy_max(1, "stone_beetle"), user, beetle))
            run_started = await service.start_run(db, user_id=user, pet_id=beetle, kind="trek", hours=9, route="pass", action_id=f"n{i}")
            await finish_now(db, run_started["run_id"])
            await service.claim_run(db, user_id=user, run_id=run_started["run_id"], action_id=f"nc{i}", rng=rng)
        async with db.execute("SELECT credited,raw FROM pet_v2_daily WHERE user_id=?", (user,)) as c:
            credited, raw = await c.fetchone()
        assert credited <= rules.DAILY_MAX + 1e-6, f"daily cap broken: {credited}"
        assert raw > credited
        # находки не выше суточных потолков
        async with db.execute("SELECT finds FROM pet_v2_daily WHERE user_id=?", (user,)) as c:
            import json
            finds = (await c.fetchone())[0]
        finds = json.loads(finds) if isinstance(finds, str) else finds
        assert finds.get("mora", 0) <= rules.FIND_DAILY_CAP["mora"]
        assert finds.get("diamond", 0) <= rules.FIND_DAILY_CAP["diamond"]
        assert finds.get("essence", 0) <= rules.FIND_DAILY_CAP["essence"]
        async with db.execute("SELECT COUNT(*) FROM economic_operations WHERE user_id=? AND reason_code='pet_find'", (user,)) as c:
            assert (await c.fetchone())[0] >= 1, "mora finds must go through the economy ledger"
        # потолок ступени: без дней Связи выше 5 не поднимется
        async with db.execute("SELECT level FROM pet_v2_state WHERE user_id=? AND pet_id=?", (user, beetle)) as c:
            assert (await c.fetchone())[0] <= rules.ceiling(1)
        print("OK: pets v2 PG flow, daily cap, idempotency and hints verified")
    finally:
        await tx.rollback()
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True, type=local_dsn)
    asyncio.run(run(parser.parse_args().dsn))
