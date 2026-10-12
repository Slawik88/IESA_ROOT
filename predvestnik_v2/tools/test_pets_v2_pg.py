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
        # поля для экранов: значок и любимая еда вида, свободная замена, ступень Связи, теги Испытания, выслеживание, еда, Пара, числа правил
        cat_view = next(p for p in view["pets"] if p["id"] == cat)
        assert cat_view["icon"] and cat_view["favorite_food"] == rules.favorite_food("moss_cat") and not cat_view["fed_favorite"] and not cat_view["fed_today"]
        assert cat_view["swap_free"] == {"calling": True, "traits": True} and cat_view["next_gate_days"] == 2 and cat_view["stars"] == 0
        assert set(cat_view["trial"]["hits"]) == {"route", "tempo", "style"} and cat_view["trial"]["matches"] == sum(cat_view["trial"]["hits"].values())
        assert view["track"] == {"attempts_left": rules.TRACK_DAILY, "open": None}
        assert [f["id"] for f in view["foods"]] == ["food_basic", "food_fried", "food_stew", "food_elite", "food_feast"] and all(f["quantity"] == 0 for f in view["foods"])
        assert view["pair"] == {"species": 4, "need": rules.PAIR_MIN_SPECIES, "unlocked": False}
        assert view["rules"]["energy"]["run"] == {"3": 15, "6": 30, "9": 45} and view["rules"]["energy"]["pair"] == rules.PAIR_ENERGY
        assert view["rules"]["paths"]["bold"] == {"reward": [1.8, 0.7, 0.0], "energy_loss": 15} and view["rules"]["camp"]["workshop"] == [1, 1, 2, 2, 3, 3]
        assert view["rules"]["camp"]["lounge"] == [0, 4, 8, 12, 16, 20] and view["rules"]["camp"]["markers"][0] == 0.75 and view["rules"]["xp"]["run"]["6"] == 95
        assert set(view["rules"]["traits"]) == set(view["traits"]) and view["now"] > "2020" and view["rules"]["xp"]["expedition"] == rules.EXPEDITION_MULT
        assert set(view["rules"]["calling_texts"]) == set(view["callings"]) and view["rules"]["calling_texts"]["guardian"][1] is None and all(texts[0] for texts in view["rules"]["calling_texts"].values())
        assert (view["rules"]["daily_soft_rate"], view["rules"]["pair_share"], view["rules"]["affinity_bonus"]) == (rules.SOFT_RATE, rules.PAIR_COMPANION_SHARE, rules.AFFINITY_BONUS)
        assert view["rules"]["talisman"]["plus"] == {"1": 10, "2": 15, "3": 20} and view["rules"]["talisman"]["minus"] == 10 and set(view["rules"]["talisman"]["kinds"]) == set(rules.TALISMANS)
        assert all(pet["find_bias"] == rules.SPECIES[pet["species_id"]][4] for pet in view["pets"])
        assert all(pet["track_points"] == rules.track_points(pet["level"], pet["species_id"]) for pet in view["pets"]) and view["rules"]["seal"] == {"days": [10, 30, 60, 120, 240], "bonus": 4}
        assert [rules.next_gate_days(d) for d in (0, 1, 2, 20, 21, 50, 90, 139, 140, 500)] == [2, 2, 21, 21, 50, 90, 140, 140, None, None]
        async with db.execute("SELECT COUNT(*) FROM pet_v2_tracks WHERE user_id=?", (user,)) as c:
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
        assert 1 <= keys <= rules.KEYS_PER_DAY_MAX, f"1-2 keys per day, got {keys}"
        # недельный лимит: ещё несколько «дней» подряд не дают больше KEYS_PER_WEEK_MAX
        await db.execute("UPDATE pet_v2_daily SET finds=jsonb_set(finds,'{key}',to_jsonb(?::int)) WHERE user_id=?", (rules.KEYS_PER_WEEK_MAX, user))
        await db.execute("UPDATE pet_v2_state SET energy=? WHERE user_id=? AND pet_id=?", (rules.energy_max(1, "stone_beetle"), user, beetle))
        capped = await service.start_run(db, user_id=user, pet_id=beetle, kind="trek", hours=3, route="pass", action_id="kcap")
        await finish_now(db, capped["run_id"])
        assert (await service.claim_run(db, user_id=user, run_id=capped["run_id"], action_id="kcapc", rng=rng))["key"] == 0, "weekly key cap"
        keys += 0
        async with db.execute("SELECT COALESCE(SUM(balance),0) FROM chest_key_accounts_v1 WHERE user_id=?", (user,)) as c:
            assert (await c.fetchone())[0] == keys
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
        fox_swap = next(p for p in (await service.overview(db, user))["pets"] if p["id"] == fox)["swap_free"]
        assert fox_swap == {"calling": False, "traits": True}, "замена призвания в эту неделю уже использована, черты — нет"
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
        resumed = (await service.overview(db, user))["track"]
        assert resumed["attempts_left"] == 1 and resumed["open"]["id"] == begun["track"]["id"] and "hidden" not in resumed["open"]
        assert resumed["open"]["opened"] == begun["track"]["opened"], "выслеживание можно продолжить после выхода"
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
        assert (await service.overview(db, user))["track"] == {"attempts_left": 1, "open": None}
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
        # Испытание недели
        week = service._week_start((await repo.clock(db))["day"])
        tags = rules.weekly_trial(week.toordinal())
        full_traits = ["night_walk" if tags["tempo"] == 9 else "sprinter", "careful" if tags["style"] == "careful" else "reckless"]
        route_kind = next(k for k, (plus, _) in rules.TALISMANS.items() if plus == tags["route"])
        await repo.add_talisman(db, user, "tr-t", route_kind, 1)
        await db.execute("UPDATE pet_v2_state SET level=25 WHERE user_id=? AND pet_id=?", (user, fox))
        await db.execute("DELETE FROM pet_v2_runs WHERE user_id=?", (user,))
        await rejects(service.submit_trial(db, user_id=user, pet_id=beetle, difficulty=3, action_id="tl0"))
        await service.set_build(db, user_id=user, pet_id=fox, calling=None, traits=full_traits, talisman_ids=["tr-t"], action_id="tb")
        before = await skins_v3.essence_balance(db, user)
        solved = await service.submit_trial(db, user_id=user, pet_id=fox, difficulty=3, action_id="tl1")
        assert solved["matches"] == 3 and solved["essence"] == 20
        assert next(p for p in (await service.overview(db, user))["pets"] if p["id"] == fox)["trial"] == {"matches": 3, "hits": {"route": True, "tempo": True, "style": True}}
        assert await skins_v3.essence_balance(db, user) >= before + 20
        assert (await service.submit_trial(db, user_id=user, pet_id=fox, difficulty=3, action_id="tl1"))["idempotent_replay"]
        try:
            async with db.connection.transaction():
                await service.submit_trial(db, user_id=user, pet_id=fox, difficulty=1, action_id="tl2")
        except service.PetV2Conflict:
            pass
        else:
            raise AssertionError("one trial per week")
        # Пара: нужны 5 видов, Спутник тратит 10 энергии и получает 30% Следов
        await db.execute("DELETE FROM pet_v2_runs WHERE user_id=?", (user,))
        await db.execute("DELETE FROM pet_v2_daily WHERE user_id=?", (user,))
        await db.execute("UPDATE pet_v2_state SET energy=70+2*level WHERE user_id=?", (user,))
        try:
            async with db.connection.transaction():
                await service.start_run(db, user_id=user, pet_id=cat, kind="trek", hours=3, route="forest", action_id="p0", companion_id=beetle)
        except rules.PetV2PolicyError:
            pass
        else:
            raise AssertionError("pair needs 5 species")
        await db.execute(
            "INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?),(?,?,?,?)",
            (user, "М", "ash_moth", "common", user, "З", "dusk_hare", "common"),
        )
        assert (await service.overview(db, user))["pair"] == {"species": 6, "need": rules.PAIR_MIN_SPECIES, "unlocked": True}
        async with db.execute("SELECT energy FROM pet_v2_state WHERE user_id=? AND pet_id=?", (user, beetle)) as c:
            e_before = (await c.fetchone())[0]
        paired = await service.start_run(db, user_id=user, pet_id=cat, kind="trek", hours=3, route="forest", action_id="p1", companion_id=beetle)
        async with db.execute("SELECT energy FROM pet_v2_state WHERE user_id=? AND pet_id=?", (user, beetle)) as c:
            assert abs(e_before - (await c.fetchone())[0] - rules.PAIR_ENERGY) < 0.5
        try:
            async with db.connection.transaction():
                await service.start_run(db, user_id=user, pet_id=beetle, kind="trek", hours=3, route="pass", action_id="p2")
        except service.PetV2Conflict:
            pass
        else:
            raise AssertionError("companion is busy")
        await finish_now(db, paired["run_id"])
        async with db.execute("SELECT xp FROM pet_v2_state WHERE user_id=? AND pet_id=?", (user, beetle)) as c:
            xp0 = (await c.fetchone())[0]
        pair_done = await service.claim_run(db, user_id=user, run_id=paired["run_id"], action_id="pc1", rng=rng)
        async with db.execute("SELECT xp,level FROM pet_v2_state WHERE user_id=? AND pet_id=?", (user, beetle)) as c:
            xp1, lvl1 = await c.fetchone()
        assert xp1 > xp0 or lvl1 > 1, "companion must earn Следы"
        assert pair_done["daily_credited"] <= rules.DAILY_MAX
        # кормление: еда возвращает энергию, любимая даёт флаг, Следы раз в сутки
        await db.execute("DELETE FROM pet_v2_daily WHERE user_id=?", (user,))
        await db.execute("DELETE FROM pet_v2_runs WHERE user_id=?", (user,))
        await db.execute("INSERT INTO chest_food_balances_v1(user_id,food_id,quantity) VALUES (?, 'food_basic', 3) ON CONFLICT(user_id,food_id) DO UPDATE SET quantity=3", (user,))
        await db.execute("UPDATE pet_v2_state SET energy=20, energy_at=NOW() WHERE user_id=? AND pet_id=?", (user, cat))
        fed = await service.feed_pet(db, user_id=user, pet_id=cat, food_id="food_basic", action_id="f1")
        assert fed["favorite"] and fed["remaining"] == 2 and fed["energy"] >= 35 and fed["xp_credited"] > 0
        assert (await service.feed_pet(db, user_id=user, pet_id=cat, food_id="food_basic", action_id="f1"))["idempotent_replay"]
        again = await service.feed_pet(db, user_id=user, pet_id=cat, food_id="food_basic", action_id="f2")
        assert again["xp_credited"] == 0 and again["remaining"] == 1, "Следы за кормление — раз в сутки"
        await rejects(service.feed_pet(db, user_id=user, pet_id=cat, food_id="food_feast", action_id="f3"))
        view = await service.overview(db, user)
        fed_view = next(p for p in view["pets"] if p["id"] == cat)
        assert fed_view["fed_favorite"] and fed_view["fed_today"], "кормление дня видно в обзоре"
        assert {f["id"]: f["quantity"] for f in view["foods"]}["food_basic"] == 1 and view["foods"][4]["quantity"] == 0
        print("OK: pets v2 PG flow, daily cap, idempotency and hints verified")
    finally:
        await tx.rollback()
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True, type=local_dsn)
    asyncio.run(run(parser.parse_args().dsn))
