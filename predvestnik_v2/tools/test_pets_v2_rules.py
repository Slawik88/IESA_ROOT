"""Контракт чистых правил питомцев v2: числа должны совпадать с PETS_V2_DESIGN.md и симуляторами."""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import pets_v2 as p


def must_fail(fn):
    try:
        fn()
    except p.PetV2PolicyError:
        return
    raise AssertionError("Expected PetV2PolicyError")


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    p.validate()
    # цена уровней как в документе
    assert [p.level_cost(n) for n in (1, 4, 9, 14, 19, 24, 29)] == [40, 422, 1676, 3552, 5970, 8880, 12250]
    assert p.level_cost(10, "legendary") == round(p.level_cost(10) * 1.8)
    must_fail(lambda: p.level_cost(30)); must_fail(lambda: p.level_cost(0)); must_fail(lambda: p.level_cost(5, "mythic"))
    # потолки по Связи
    assert [p.ceiling(d) for d in (0, 1, 2, 20, 21, 49, 50, 89, 90, 139, 140, 199, 200)] == [5, 5, 10, 10, 15, 15, 20, 20, 25, 25, 30, 30, 30]
    assert [p.seal_stars(d) for d in (0, 9, 10, 30, 239, 240, 999)] == [0, 0, 1, 2, 4, 5, 5]
    # суточная норма: 500 по полной, +500 сырых по 25 %, дальше 0
    assert p.DAILY_MAX == 625
    assert p.pool_credit(0, 160) == 160
    assert p.pool_credit(450, 160) == 50 + 110 * 0.25
    assert p.pool_credit(1000, 100) == 0
    assert p.pool_credit(0, 5000) == 625
    must_fail(lambda: p.pool_credit(-1, 5))
    # Следы похода
    assert p.run_xp_raw(9) == 160 and p.run_xp_raw(3, expedition=True) == 40 * 1.2
    assert p.run_xp_raw(6, repeats_today=2) == 95 * 0.75 ** 2
    assert abs(p.run_xp_raw(9, favorite_route=True, stars=5) - 160 * 1.4) < 1e-9
    must_fail(lambda: p.run_xp_raw(4)); must_fail(lambda: p.watch_xp_raw(9))
    # «Попутный ветер» не пробивает общую норму
    assert p.apply_wind(100, 0) == 125 and p.apply_wind(100, 560) == 65 and p.apply_wind(50, 625) == 0
    # энергия: свой запас и отдых у каждого питомца
    assert p.energy_max(1, "moss_cat") == 72 and p.energy_max(30, "star_dragon") == 150 and p.energy_max(1, "ash_moth") == 62
    assert p.energy_regen_per_hour(1, "moss_cat") == 4 and p.energy_regen_per_hour(30, "star_dragon") == 7.5
    assert p.energy_regen_per_hour(10, "frost_stag") == 3.5
    assert p.energy_after_rest(0, hours=100, level=1, species_id="moss_cat") == 72
    assert p.spend_energy(72, "run", 9) == 27
    must_fail(lambda: p.spend_energy(44, "run", 9)); must_fail(lambda: p.spend_energy(100, "run", 4))
    # шансы и подсказки как в таблице документа
    assert p.path_chance(12, 12, "steady") == 50 and p.path_chance(12, 12, "careful") == 78 and p.path_chance(12, 12, "bold") == 22
    assert p.path_chance(40, 0, "careful") == 95 and p.path_chance(0, 40, "bold") == 5
    assert p.path_chance(12, 12, "steady", pity=1) == 55 and p.path_chance(12, 12, "steady", pity=9) == 65
    assert [p.chance_sign(x) for x in (95, 85, 84, 65, 64, 40, 39, 20, 19, 5)] == [
        "Надёжно", "Надёжно", "Скорее удастся", "Скорее удастся", "Как повезёт", "Как повезёт", "Рискованно", "Рискованно", "Отчаянно", "Отчаянно"]
    assert [p.hint_detail(l, "moss_cat") for l in (1, 3, 4, 7, 8, 11, 12)] == ["sign", "sign", "factors", "factors", "range", "range", "exact"]
    assert p.hint_detail(1, "mirror_owl") == "exact"
    lo, hi = p.chance_range(57); assert lo <= 57 <= hi and hi - lo <= 25
    # исходы
    assert [p.decide_outcome(50, r) for r in (0, 49.9, 50, 74.9, 75, 99.9)] == ["success", "success", "partial", "partial", "fail", "fail"]
    assert p.decide_outcome(95, 97) == "partial" and p.decide_outcome(95, 99.9) == "partial" and p.decide_outcome(60, 99.9) == "fail"
    must_fail(lambda: p.decide_outcome(50, 100)); must_fail(lambda: p.decide_outcome(50, -1))
    assert p.outcome_reward_mult("bold", "success") == 1.8 and p.outcome_reward_mult("bold", "fail") == 0
    assert p.outcome_reward_mult("careful", "fail") == 0.4 and p.outcome_reward_mult("steady", "fail", guardian=True) == 0.25 * 1.25
    assert p.next_pity(0, 50, "fail") == 1 and p.next_pity(3, 50, "fail") == 3 and p.next_pity(2, 30, "fail") == 2 and p.next_pity(2, 80, "success") == 0
    # Выдержка питомца
    assert p.resilience(1, 72, "moss_cat") == 21
    assert p.resilience(10, 40, "moss_cat", terrain_match=True, guardian=True, favorite_treat=True) > p.resilience(10, 40, "moss_cat")
    must_fail(lambda: p.resilience(1, 999, "moss_cat"))
    # какой путь выгоднее — как в симуляторе
    sim = load("pets_v2_decision_sim")
    for gap in range(-12, 17, 2):
        for path in p.PATHS:
            assert abs(p.path_chance(gap + 20, 20, path) - sim.chance(gap, path)) < 1e-9
        best = max(p.PATHS, key=lambda x: sum(a * b for a, b in zip(sim.outcome_probs(p.path_chance(gap + 20, 20, x)), p.PATHS[x][1])))
        assert best == max(sim.PATHS, key=lambda x: sim.expected(gap, x))
    # находки: нулевая сумма, лимиты уровня, потолки
    shares = p.find_shares(level=1)
    assert abs(sum(shares.values()) - 1) < 1e-9 and shares["diamond"] == 0 and shares["essence"] == 0
    base = p.find_shares(level=8)
    boosted = p.find_shares({"essence": 2.5}, level=8)
    assert boosted["essence"] > base["essence"] * 2 and boosted["mora"] < base["mora"]
    assert p.find_shares({"mora": 99}, level=8) == p.find_shares({"mora": 2.5}, level=8)   # потолок ×2.5
    assert p.cap_find("mora", 6, today=58) == 2 and p.cap_find("diamond", 1, today=0, this_week=2) == 0 and p.cap_find("essence", 3, today=4) == 0
    # Лагерь и сборки
    assert p.camp_upgrade_cost("lounge", 5) == {"mora": 1200, "essence": 170, "hours": 48}
    assert sum(p.CAMP_COST_MORA) * 3 == 7800 and sum(p.CAMP_COST_ESSENCE) * 3 == 1230
    assert p.camp_bonus("lounge", 5) == 0.2 and p.camp_bonus("markers", 3) == 0.15
    must_fail(lambda: p.camp_upgrade_cost("tower", 1)); must_fail(lambda: p.camp_upgrade_cost("lounge", 6))
    assert [p.trait_slots(l) for l in (1, 5, 14, 15, 24, 25, 30)] == [0, 1, 1, 2, 2, 3, 3]
    assert abs(p.trait_xp_multiplier(("night_walk", "nose"), 9) - 1.15 * 0.95) < 1e-9
    assert sum(p.STAGE_ESSENCE.values()) == 80
    assert p.markers_decay(0) == 0.75 and abs(p.markers_decay(5) - 0.85) < 1e-9
    assert [p.workshop_max_tier(l) for l in range(6)] == [1, 1, 2, 2, 3, 3] and p.reforge_cost(1) == 10 and p.reforge_cost(2) == 20
    assert p.run_xp_raw(3, repeats_today=2, repeat_decay=0.85) > p.run_xp_raw(3, repeats_today=2)
    assert [p.track_points(l, "moss_cat") for l in (1, 8, 16)] == [3, 4, 5] and p.track_points(1, "mirror_owl") == 4
    assert p.track_heat(4, 4) == "found" and p.track_heat(4, 0) == "warm" and p.track_heat(0, 8) == "cold" and p.track_heat(0, 2) == "cold"
    must_fail(lambda: p.track_heat(9, 0))
    trial = p.weekly_trial(740000)
    assert trial == p.weekly_trial(740000) and trial["route"] in p.ROUTES and trial["tempo"] in (3, 9)
    full = {"route": "forest", "tempo": 9, "style": "careful"}
    assert p.trial_matches(full, "forest", ("night_walk", "careful")) == 3 and p.trial_matches(full, "pass", ()) == 0
    assert p.trial_matches(full, "pass", (), (("forest_fang", 1),)) == 1 and p.trial_matches(full, "any", ("sprinter",)) == 1
    assert abs(p.companion_find_mod("salt_fox")["mora"] - 1.2) < 1e-9 and p.PAIR_ENERGY == 10
    assert abs(p.build_effects(None, ("loner",))["xp_mult"] - 1.10) < 1e-9 and abs(p.build_effects(None, ("loner",), paired=True)["xp_mult"] - 0.90) < 1e-9
    # применение билда
    plain = p.build_effects(None, (), hours=9, route="forest")
    assert plain["xp_mult"] == 1.0 and plain["find_mods"] == {} and not plain["guardian"]
    seeker = p.build_effects("seeker", ("meticulous",), hours=3, route="pass")
    assert seeker["find_mods"]["diamond"] == 1.8 * 1.8 and seeker["find_mods"]["bonus_xp"] == 0.7
    assert abs(p.build_effects(None, ("night_walk",), hours=9)["xp_mult"] - 1.15) < 1e-9
    fang = p.build_effects(None, (), (("forest_fang", 2), ("forest_fang", 3)), hours=3, route="forest")
    assert abs(fang["xp_mult"] - 1.15 * 1.20 * 1.05) < 1e-9
    assert abs(p.build_effects(None, (), (("forest_fang", 1),), route="swamp")["xp_mult"] - 0.9) < 1e-9
    hardy = p.build_effects(None, ("hardy",))
    assert hardy["energy_bonus"] == 15 and hardy["regen_delta"] == -1
    assert p.energy_max(1, "moss_cat", 15) == p.energy_max(1, "moss_cat") + 15 and p.energy_regen_per_hour(1, "moss_cat", delta=-1) == 3
    must_fail(lambda: p.build_effects("tamer", ())); must_fail(lambda: p.build_effects(None, ("hardy", "hardy"))); must_fail(lambda: p.build_effects(None, (), (("x", 1),)))
    assert p.build_effects(None, ("careful",))["chance_bonus"]["bold"] == -10
    # прокачка совпадает с балансным симулятором
    bal = load("pets_v2_balance_sim")
    assert all(bal.level_cost(l) == p.level_cost(l) for l in range(1, 30))
    assert all(bal.ceiling(d) == p.ceiling(d) for d in range(0, 260))
    for before in (0, 300, 499, 500, 700, 1000, 1200):
        for raw in (0, 40, 160, 800):
            assert abs(bal.pool_apply(before, raw) - p.pool_credit(before, raw)) < 1e-9
    print("OK: pets v2 rules (levels, daily cap, energy, risk, finds, camp) match the design and simulators")


if __name__ == "__main__":
    main()
