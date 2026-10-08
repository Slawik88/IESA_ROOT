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
        # ключ сундука: один в сутки, только при включённых сундуках
        from infrastructure.repositories import system_flags
        await system_flags.ensure_table(db)
        await system_flags.set_flag(db, "content_chests_v1", True)
        await db.execute("DELETE FROM pet_v2_daily WHERE user_id=?", (user,))
        keys = 0
        for i in range(3):
            await db.execute("UPDATE pet_v2_state SET energy=? WHERE user_id=? AND pet_id=?", (rules.energy_max(1, "stone_beetle"), user, beetle))
            started_key = await service.start_run(db, user_id=user, pet_id=beetle, kind="trek", hours=3, route="pass", action_id=f"k{i}")
            await finish_now(db, started_key["run_id"])
            keys += (await service.claim_run(db, user_id=user, run_id=started_key["run_id"], action_id=f"kc{i}", rng=rng))["key"]
        assert keys == 1, f"exactly one key per day, got {keys}"
        async with db.execute("SELECT COALESCE(SUM(balance),0) FROM chest_key_accounts_v1 WHERE user_id=?", (user,)) as c:
            assert (await c.fetchone())[0] == 1
        # билды: слоты, призвание, цена замены, талисманы, идемпотентность
        async def rejects(coro):
            try:
                async with db.connection.transaction():
                    await coro
            except rules.PetV2PolicyError:
                return
            raise AssertionError("build must be rejected")

        await db.execute("UPDATE pet_v2_runs SET status='claimed' WHERE user_id=? AND status='active'", (user,))
        await rejects(service.set_build(db, user_id=user, pet_id=fox, calling="seeker", traits=[], talisman_ids=[], action_id="b0"))
        await rejects(service.set_build(db, user_id=user, pet_id=fox, calling=None, traits=["hardy"], talisman_ids=[], action_id="b1"))
        await db.execute("UPDATE pet_v2_state SET level=15 WHERE user_id=? AND pet_id=?", (user, fox))
        await repo.add_talisman(db, user, "t1", "forest_fang", 2)
        await repo.add_talisman(db, user, "t2", "forest_fang", 3)
        await repo.add_talisman(db, user, "t3", "swamp_lamp", 1)
        built = await service.set_build(db, user_id=user, pet_id=fox, calling="seeker", traits=["hardy", "careful"], talisman_ids=["t1", "t2"], action_id="b2")
        assert built["essence_spent"] == 0
        assert (await service.set_build(db, user_id=user, pet_id=fox, calling="seeker", traits=["hardy", "careful"], talisman_ids=["t1", "t2"], action_id="b2"))["idempotent_replay"]
        view = await service.overview(db, user)
        fox_view = next(p for p in view["pets"] if p["id"] == fox)
        assert fox_view["energy_max"] == rules.energy_max(15, "salt_fox") + 15 and fox_view["calling"] == "seeker"
        # замена призвания: первая в неделю бесплатна, вторая стоит Эссенцию
        free = await service.set_build(db, user_id=user, pet_id=fox, calling="guardian", traits=["hardy", "careful"], talisman_ids=["t1"], action_id="b3")
        assert free["essence_spent"] == 0
        await rejects(service.set_build(db, user_id=user, pet_id=fox, calling="feeder", traits=["hardy", "careful"], talisman_ids=["t1"], action_id="b4"))
        await skins_v3.essence_apply(db, user, 15, reason="test", reference="t", idempotency_key="test-essence")
        paid = await service.set_build(db, user_id=user, pet_id=fox, calling="feeder", traits=["hardy", "careful"], talisman_ids=["t1"], action_id="b5")
        assert paid["essence_spent"] == rules.CALLING_SWAP_ESSENCE
        assert await skins_v3.essence_balance(db, user) < 15, "paid swap must debit essence"
        await rejects(service.set_build(db, user_id=user, pet_id=fox, calling=None, traits=["bogus"], talisman_ids=[], action_id="b6"))
        await rejects(service.set_build(db, user_id=user, pet_id=fox, calling="feeder", traits=["hardy", "careful"], talisman_ids=["zz"], action_id="b7"))
        # Лагерь и перековка
        await rejects(service.camp_upgrade(db, user_id=user, building="lounge", action_id="cu0"))  # нет Моры и Эссенции
        await db.execute("UPDATE skins_v3_essence_accounts SET balance=1000 WHERE user_id=?", (user,))
        await db.execute("UPDATE users SET user_balance_mora=user_balance_mora+5000 WHERE user_tg_id=?", (user,))
        built_camp = await service.camp_upgrade(db, user_id=user, building="workshop", action_id="cu1")
        assert built_camp["to_level"] == 1 and built_camp["cost"]["mora"] == 100
        assert (await service.camp_upgrade(db, user_id=user, building="workshop", action_id="cu1"))["idempotent_replay"]
        try:
            async with db.connection.transaction():
                await service.camp_upgrade(db, user_id=user, building="lounge", action_id="cu2")
        except service.PetV2Conflict:
            pass
        else:
            raise AssertionError("one construction at a time")
        await rejects(service.reforge_talisman(db, user_id=user, talisman_id="t3", action_id="rf0"))   # Мастерская ещё не позволяет
        await db.execute("UPDATE pet_v2_camp_jobs SET ends_at=NOW()-INTERVAL '1 minute' WHERE user_id=?", (user,))
        assert (await repo.camp_levels(db, user))["workshop"] == 1
        await db.execute("UPDATE pet_v2_camp_jobs SET to_level=2 WHERE user_id=?", (user,))
        reforged = await service.reforge_talisman(db, user_id=user, talisman_id="t3", action_id="rf1")
        assert reforged["tier"] == 2 and reforged["essence_spent"] == 10
        assert (await service.reforge_talisman(db, user_id=user, talisman_id="t3", action_id="rf1"))["idempotent_replay"]
        await rejects(service.reforge_talisman(db, user_id=user, talisman_id="t3", action_id="rf2"))  # тир III нужен 4 уровень
        await service.camp_upgrade(db, user_id=user, building="lounge", action_id="cu3")
        view = await service.overview(db, user)
        assert view["camp"]["levels"]["workshop"] == 2 and view["camp"]["job"]["building"] == "lounge"
        # Выслеживание: сервер прячет находку, тайна не утекает, 2 попытки в сутки
        await db.execute("DELETE FROM pet_v2_tracks WHERE user_id=?", (user,))
        t_rng = random.Random(3)
        begun = await service.start_track(db, user_id=user, pet_id=owl, action_id="tr0", rng=t_rng)
        assert "hidden" not in begun["track"] and len(begun["track"]["opened"]) == 3 and begun["track"]["points"] == rules.track_points(1, "mirror_owl")
        assert (await service.start_track(db, user_id=user, pet_id=owl, action_id="tr0", rng=t_rng))["idempotent_replay"]
        try:
            async with db.connection.transaction():
                await service.start_track(db, user_id=user, pet_id=owl, action_id="tr1", rng=t_rng)
        except service.PetV2Conflict:
            pass
        else:
            raise AssertionError("only one open track at a time")
        async with db.execute("SELECT hidden FROM pet_v2_tracks WHERE id=?", (begun["track"]["id"],)) as c:
            hidden = (await c.fetchone())[0]
        seen = {o["cell"] for o in begun["track"]["opened"]}
        assert hidden not in seen
        rest = [c for c in range(9) if c not in seen and c != hidden]
        first = await service.open_track_cell(db, user_id=user, track_id=begun["track"]["id"], cell=rest[0], action_id="to0", rng=t_rng)
        assert first["track"]["points"] == begun["track"]["points"] - 1 and first["track"]["opened"][-1]["heat"] in ("warm", "cold")
        await rejects(service.open_track_cell(db, user_id=user, track_id=begun["track"]["id"], cell=rest[0], action_id="to1", rng=t_rng))
        won = await service.open_track_cell(db, user_id=user, track_id=begun["track"]["id"], cell=hidden, action_id="to2", rng=t_rng)
        assert won["track"]["status"] == "won" and won["track"]["hidden"] == hidden and "finds" in won["track"]["result"]
        second = await service.start_track(db, user_id=user, pet_id=cat, action_id="tr2", rng=t_rng)
        for i, cell in enumerate(c for c in range(9) if c not in {o["cell"] for o in second["track"]["opened"]}):
            res = await service.open_track_cell(db, user_id=user, track_id=second["track"]["id"], cell=cell, action_id=f"tq{i}", rng=t_rng)
            if res["track"]["status"] != "open":
                break
        assert res["track"]["status"] in ("won", "lost")
        try:
            async with db.connection.transaction():
                await service.start_track(db, user_id=user, pet_id=cat, action_id="tr3", rng=t_rng)
        except service.PetV2Conflict:
            pass
        else:
            raise AssertionError("two tracks per day")
        print("OK: pets v2 PG flow, daily cap, idempotency and hints verified")
    finally:
        await tx.rollback()
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True, type=local_dsn)
    asyncio.run(run(parser.parse_args().dsn))
