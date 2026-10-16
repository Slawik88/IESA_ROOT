"""Контракт подсказки «лучший выбор» (services/pets_v2_advice.py): числа считаются только по правилам core.

Ожидание путей сверяется с симулятором tools/pets_v2_decision_sim.py (он же — ссылка из PETS_V2_DESIGN).
Запуск: python tools/test_pets_v2_advice.py
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import pets_v2 as p
from services import pets_v2_advice as advice


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plan(pid, *, species="moss_cat", level=10, energy=None, stars=0, busy=False, pity=0, fed=False,
         calling=None, traits=(), talismans=()):
    cap = p.energy_max(level, species, 0)
    return {"id": pid, "busy": busy, "energy": float(cap if energy is None else energy), "level": level, "species_id": species,
            "favorite": p.SPECIES[species][1], "stars": stars, "pity": pity, "fed": fed, "calling": calling,
            "traits": traits, "talismans": talismans, "camp": {}}


def run(plans, repeats=None):
    return advice.build(plans, routes=p.ROUTES, run_hours=p.RUN_HOURS, watch_hours=p.WATCH_HOURS, repeats_by_route=repeats or {})


def main() -> None:
    sim = load("pets_v2_decision_sim")
    # вероятности исходов как в decide_outcome (успех, частично, провал)
    assert advice.outcome_probs(50) == (0.5, 0.25, 0.25)
    assert advice.outcome_probs(80) == (0.8, 0.2, 0.0)
    assert advice.outcome_probs(5) == (0.05, 0.25, 0.70)
    # ожидание пути совпадает с симулятором решения
    for gap in range(-12, 13, 2):
        chances = {path: sim.chance(gap, path) for path in sim.PATHS}
        ev = advice.path_ev(chances)
        for path in sim.PATHS:
            assert abs(ev[path] - sim.expected(gap, path)) < 1e-9, (gap, path)
        assert advice.best_path(chances) == max(sim.PATHS, key=lambda path: sim.expected(gap, path))
    # пустой список питомцев: ни карты, ни связки
    assert run([]) == {"map": {}, "best": {}}

    # карта полная: 3 часа × 4 маршрута × 2 вида занятий + 2 смены дозора
    view = run([plan(1)])
    assert len(view["map"]) == 26 and all(isinstance(pid, int) for pid in view["map"].values())
    assert view["map"]["watch|12|"] == 1 and view["map"]["watch|24|"] == 1 and view["map"]["expedition|9|swamp"] == 1
    assert set(view["best"]) == {"trek", "expedition", "watch"}
    for kind, row in view["best"].items():
        assert set(row) == {"pet_id", "hours", "route"} and isinstance(row["pet_id"], int)
        assert row["hours"] in (p.WATCH_HOURS if kind == "watch" else p.RUN_HOURS)
        assert row["route"] in (("",) if kind == "watch" else p.ROUTES)
    assert view["best"]["trek"] == {"pet_id": 1, "hours": 9, "route": "forest"}      # длинная дистанция по любимому маршруту
    assert view["best"]["watch"] == {"pet_id": 1, "hours": 24, "route": ""}          # смена подлиннее, если сил хватает
    assert json.dumps(view)                                                          # контракт клиента: только числа и строки

    # любимый маршрут и звёзды вида решают на своей клетке
    view = run([plan(1, species="moss_cat"), plan(2, species="rain_finch"), plan(3, stars=2)])
    assert view["map"]["trek|6|forest"] == 3 and view["map"]["trek|6|ruins"] == 2
    assert view["map"]["expedition|6|ruins"] == 2 and view["map"]["trek|6|swamp"] == 3

    # выдержка важна только экспедиции: старший уровень берёт риск
    view = run([plan(1, level=5), plan(2, level=20)])
    assert view["map"]["expedition|9|forest"] == 2
    assert view["map"]["trek|9|forest"] == 1        # на Следы похода уровень не влияет: ничья — первому

    # талисман маршрута работает на своём маршруте и мешает на чужом
    view = run([plan(1, talismans=(("forest_fang", 2),)), plan(2)])
    assert view["map"]["trek|9|forest"] == 1 and view["map"]["trek|9|swamp"] == 2

    # закрытый маршрут дешевеет: свежий становится выгоднее любимого
    assert run([plan(1)])["best"]["trek"]["route"] == "forest"
    assert run([plan(1)], {"forest": 1})["best"]["trek"]["route"] == "pass"

    # не хватает сил и занятые питомцы не попадают в подсказку
    low = run([plan(1, energy=15)])
    assert low["map"]["trek|3|forest"] == 1 and "trek|6|forest" not in low["map"] and "watch|12|" not in low["map"]
    assert low["best"]["trek"]["hours"] == 3 and low["best"]["expedition"]["hours"] == 3 and "watch" not in low["best"]
    assert run([plan(1, busy=True)]) == {"map": {}, "best": {}}

    # дозор: Следы одинаковые, поэтому ценится запас сил
    view = run([plan(1, energy=40), plan(2)])
    assert view["best"]["watch"] == {"pet_id": 2, "hours": 24, "route": ""}
    print("pets_v2 advice: OK")


if __name__ == "__main__":
    main()
