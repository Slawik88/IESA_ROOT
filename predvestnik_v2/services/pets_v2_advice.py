"""Подсказка «лучший выбор» для Тропы питомцев (pets v2).

Чистые функции без БД: считают ожидание по правилам core.pets_v2 — с чертами,
талисманами, Хранителем, мягкой защитой (pity) и повторами маршрута за день.
Отдают два готовых ответа: карту «кто лучший на конкретный выбор» (вид занятия,
часы, маршрут) и рекомендованную связку на каждый вид. Клиент только рисует
звезду — копии формул на фронте не нужны.

Единица измерения — «сырые» Следы: для похода это run_xp_raw, для экспедиции —
run_xp_raw × ожидание лучшего пути, для дозора — запас сил (его Следы от
питомца не зависят, выше ценится тот, кто потянет более долгую смену).
"""
from __future__ import annotations

from core import pets_v2 as rules

_KINDS = ("trek", "expedition", "watch")
_ENERGY_KIND = {"trek": "run", "expedition": "run", "watch": "watch"}
PATHS = tuple(rules.PATHS)


def outcome_probs(chance: float) -> tuple[float, float, float]:
    """Вероятности успеха, частичного исхода и провала при данном шансе (как decide_outcome, без броска)."""
    partial = min(rules.PARTIAL_BAND, 100.0 - chance)
    return chance / 100.0, partial / 100.0, max(0.0, (100.0 - chance - partial) / 100.0)


def path_ev(chances: dict[str, float], reward_mult: dict[str, float] | None = None, *, guardian: bool = False) -> dict[str, float]:
    """Ожидаемая доля награды по каждому пути: вероятность исхода × множитель × поправка сборки (талисманы)."""
    mults = reward_mult or {}
    out: dict[str, float] = {}
    for path, chance in chances.items():
        ps, pp, pf = outcome_probs(chance)
        share = float(mults.get(path, 1.0))
        out[path] = share * (ps * rules.outcome_reward_mult(path, "success", guardian=guardian)
                             + pp * rules.outcome_reward_mult(path, "partial", guardian=guardian)
                             + pf * rules.outcome_reward_mult(path, "fail", guardian=guardian))
    return out


def best_path(chances: dict[str, float], reward_mult: dict[str, float] | None = None, *, guardian: bool = False) -> str | None:
    """Путь с наибольшим ожиданием; при равенстве выигрывает более осторожный (порядок PATHS)."""
    ev = path_ev(chances, reward_mult, guardian=guardian)
    if not ev:
        return None
    return max(PATHS, key=lambda path: (ev.get(path, 0.0), -PATHS.index(path)))


def _plan_score(plan: dict, kind: str, hours: int, route: str | None, repeats: int) -> float | None:
    """Ожидание одной отправки. None — питомец занят или ему не хватает сил на эти часы."""
    if plan["busy"] or plan["energy"] < rules.ACTIVITY_ENERGY[(_ENERGY_KIND[kind], int(hours))]:
        return None
    fx = rules.build_effects(plan["calling"], plan["traits"], plan["talismans"], hours=int(hours), route=route, fed_favorite=plan["fed"])
    if kind == "watch":
        return float(plan["energy"]) + int(hours) * 0.001   # Следы дозора от питомца не зависят: важен запас сил, при равенстве — смена подлиннее
    terrain = bool(route) and plan["favorite"] in (route, "any")
    raw = rules.run_xp_raw(int(hours), expedition=kind == "expedition", repeats_today=max(0, int(repeats)),
                           favorite_route=terrain, stars=int(plan["stars"]), trait_mult=fx["xp_mult"],
                           repeat_decay=rules.markers_decay(plan["camp"].get("markers", 0)))
    if kind == "trek":
        return raw
    cap = rules.energy_max(int(plan["level"]), plan["species_id"], fx["energy_bonus"])
    resilience = rules.resilience(int(plan["level"]), min(plan["energy"], cap), plan["species_id"], terrain_match=terrain,
                                  guardian=fx["guardian"], energy_bonus=fx["energy_bonus"], extra=fx["resilience_extra"],
                                  favorite_treat=plan["fed"])
    chances = {path: rules.path_chance(resilience, rules.event_difficulty(int(hours)), path, pity=int(plan["pity"]),
                                       bonus=fx["chance_bonus"][path]) for path in PATHS}
    return raw * max(path_ev(chances, fx["reward_mult"], guardian=fx["guardian"]).values())


def _top_for_cell(plans: list[dict], kind: str, hours: int, route: str | None, repeats: int) -> tuple[dict | None, tuple | None]:
    """Лучший питомец на клетку. Ничью решает любимый маршрут: он полезнее для находок и понятнее игроку."""
    winner, top = None, None
    for plan in plans:
        score = _plan_score(plan, kind, hours, route, repeats)
        if score is None:
            continue
        mark = (score, 1 if route and plan["favorite"] in (route, "any") else 0)
        if top is None or mark > top:
            winner, top = plan, mark
    return winner, top


def build(plans: list[dict], *, routes, run_hours, watch_hours, repeats_by_route: dict[str, int] | None = None) -> dict:
    """Карта «кто лучший» (ключ «вид|часы|маршрут») и рекомендованная связка на каждый вид занятия."""
    repeats = repeats_by_route or {}
    cells: dict[str, int] = {}
    best: dict[str, dict] = {}
    for kind in _KINDS:
        hours_list = tuple(watch_hours) if kind == "watch" else tuple(run_hours)
        for hours in hours_list:
            for route in ("",) if kind == "watch" else tuple(routes):
                winner, top = _top_for_cell(plans, kind, int(hours), route or None, repeats.get(route, 0))
                if winner is None or top is None:
                    continue
                cells[f"{kind}|{hours}|{route}"] = int(winner["id"])
                if kind not in best or top > best[kind]["score"]:
                    best[kind] = {"score": top, "pet_id": int(winner["id"]), "hours": int(hours), "route": route}
    return {"map": cells, "best": {kind: {key: value for key, value in row.items() if key != "score"} for kind, row in best.items()}}
