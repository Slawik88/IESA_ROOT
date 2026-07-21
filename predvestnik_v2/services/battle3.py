# services/battle3.py — Боёвка 4.0: сетка/AP-действия (B1) + ярость/QTE (B2a).
#
# Server-authoritative движок: позиции на сетке/AP/ярость/телеграф/QTE живут
# ТОЛЬКО в state (battles.state_json). Клиент шлёт action {type, unit_i, ...}
# и сырые tap_offset_ms на QTE — грейдит сервер (grade_tap из battle.py, анти-чит там же).
# Рунный/Фокус-движок Боёвки 3.0 снят в B2a (см. BATTLE_REWORK_CONCEPT.md — история).
#
# Ход: игрок тратит AP отряда действиями (move/attack/defend/skill) → end_turn →
# фаза врага (по телеграфу). QTE только на критах (1 раз за раунд) и ультах —
# пауза pending/resume.
import json
import random
import time

from core.constants import (
    B3_RAGE_MAX, B3_RAGE_PER_HIT_OUT, B3_RAGE_PER_HIT_IN, B3_RAGE_HIT_CAP,
    B3_RAGE_COMEBACK_50, B3_RAGE_COMEBACK_25,
    B3_CRIT_MULT, B3_ULT_MULT,
    B3_INTERCEPT_REAR, B3_INTERCEPT_FLANK, B3_INTERCEPT_FALLBACK,
    B3_INTERCEPT_TANK_BONUS,
    B3_ESCALATION_FROM_ROUND, B3_ESCALATION_STEP, B3_ESCALATION_CAP,
    B3_TRIAD_MULT, WAR_WALL_SEGMENT_HP,
    GRID_W, GRID_H, B4_AP_BY_ROLE, B4_AP_LEGENDARY_BONUS, B4_RANGE_BY_ROLE,
    B4_ENEMY_MOVE,
)
from core.units import (
    UNITS, unit_stats, element_mult, ELEMENT_META, ELEMENT_SYNERGY, ELEMENTS, _BEATS,
)
from services.battle import qte_window, grade_tap
from services import battle_grid as grid_mod

B3_SUDDEN_DEATH_ROUND = 20   # с этого раунда обе стороны теряют HP каждый раунд

# ── Построение сторон ─────────────────────────────────────────────────────────

def _mk_ally(unit_row: dict) -> dict:
    u = UNITS[unit_row["unit_id"]]
    st = unit_stats(unit_row["unit_id"], unit_row["level"])
    return {
        "uid": unit_row["unit_id"], "name": u["name"], "emoji": u["emoji"],
        "element": u["element"], "role": u["role"], "slot": unit_row["slot"],
        "level": unit_row["level"],
        "hp": st["hp_max"], "hp_max": st["hp_max"], "atk": st["atk"], "def": st["def"],
        "crit": st["crit"], "shield": 0, "alive": True, "statuses": {},
    }


def _squad_synergy(units: list[dict]) -> dict:
    """2+ одной стихии → пассив; 3 разных → триада."""
    els = [u["element"] for u in units if u["element"]]
    syn = {}
    for el in set(els):
        if els.count(el) >= 2:
            syn = dict(ELEMENT_SYNERGY[el])
            syn["element"] = el
            break
    triad = len(units) >= 3 and len(set(els)) == len(els) == 3
    return {"synergy": syn, "triad": triad}


def new_battle_state(ally_rows: list[dict], enemies: list[dict], mode: str,
                     ctx: dict | None = None) -> dict:
    """ally_rows: barracks.squad_units() (+level/slot); enemies: см. генераторы."""
    allies = [_mk_ally(r) for r in ally_rows]
    meta = _squad_synergy(allies)
    syn = meta["synergy"]
    if syn.get("hp"):
        for a in allies:
            a["hp_max"] = int(a["hp_max"] * (1 + syn["hp"]))
            a["hp"] = a["hp_max"]
    for e in enemies:
        e.setdefault("hp", e["hp_max"])
        e.setdefault("shield", 0)
        e.setdefault("alive", True)
        e.setdefault("statuses", {})
        e.setdefault("crit", 0.10)
    ally_pts, enemy_pts = spawn_positions(len(allies), len(enemies))
    for u, p in zip(allies, ally_pts):
        u["pos"] = {"x": p[0], "y": p[1]}
        u["ap_max"] = _unit_ap_max(u)
        u["ap"] = u["ap_max"]
        u["cd"] = {"skill": 0}
        u["defending"] = False
    for u, p in zip(enemies, enemy_pts):
        u["pos"] = {"x": p[0], "y": p[1]}
        u.setdefault("cd", {"skill": 0})
    seed = int((ctx or {}).get("seed") or random.randint(1, 2**31 - 1))
    battle_grid_data = grid_mod.gen_grid(seed, ally_pts + enemy_pts)
    state = {
        "mode": mode, "round": 0, "status": "active",
        "grid": battle_grid_data, "seed": seed,
        "ally": {"units": allies, "rage": 0,
                 "synergy": syn, "triad_available": meta["triad"],
                 "rebirth_used": False},
        "enemy": {"units": enemies, "rage": 0, "intents": [], "skip_next": False},
        "pending": None, "qte": None, "zero_streak": 0,
        "log": [], "dmg_total": 0,
        **(ctx or {}),
    }
    begin_round(state)
    return state


# ── Раунд: начало, телеграф ───────────────────────────────────────────────────

def begin_round(state: dict) -> None:
    state["round"] += 1
    a = state["ally"]
    state["crit_qte_used"] = False
    # Порождение Бездны: стихия подстраивается под слабость первого живого врага
    tgt = _first_alive(state["enemy"]["units"])
    if tgt is not None:
        enemy_el = state["enemy"]["units"][tgt].get("element")
        for u in a["units"]:
            if u["uid"] == "u_porozhdenie" and u["alive"] and enemy_el:
                u["element"] = next((el for el, beats in _BEATS.items()
                                     if beats == enemy_el), None) or "dark"
    _roll_telegraph(state)


def _first_alive(units: list[dict]) -> int | None:
    for i, u in enumerate(units):
        if u["alive"]:
            return i
    return None


def _alive_idx(units: list[dict]) -> list[int]:
    return [i for i, u in enumerate(units) if u["alive"]]


def _strongest_enemy(state: dict) -> int | None:
    """Индекс живого врага с макс. атакой (для вражеской ульты). Стена (atk 0) исключена."""
    best, bi = 0, None
    for i, e in enumerate(state["enemy"]["units"]):
        if e["alive"] and e.get("atk", 0) > best:
            best, bi = e["atk"], i
    return bi


def _roll_telegraph(state: dict) -> None:
    """Намерения врага на его следующую фазу (для UI): кого и как он ударит."""
    intents = []
    # Ярость врага полна → телеграфируем ульту сильнейшего (см. _enemy_phase).
    ult_i = _strongest_enemy(state) if state["enemy"].get("rage", 0) >= B3_RAGE_MAX else None
    for ei, e in enumerate(state["enemy"]["units"]):
        if not e["alive"]:
            continue
        if ei == ult_i:
            intents.append({"i": ei, "kind": "ult"})
            continue
        if e.get("boss") and state["round"] % 3 == 0:
            intents.append({"i": ei, "kind": "aoe"})
            continue
        plan = _best_enemy_plan(state, ei)
        if plan and plan["kind"] == "attack":
            intents.append({"i": ei, "kind": "atk", "target": plan["target"]})
        elif plan:
            intents.append({"i": ei, "kind": plan["kind"]})
    state["enemy"]["intents"] = intents


# ── Урон/лечение/ярость ───────────────────────────────────────────────────────

def _escalation(state: dict) -> float:
    extra = max(0, state["round"] - B3_ESCALATION_FROM_ROUND + 1) * B3_ESCALATION_STEP
    return 1.0 + min(B3_ESCALATION_CAP, extra)


def _team_hp_frac(units: list[dict]) -> float:
    tot = sum(u["hp_max"] for u in units) or 1
    return sum(max(0, u["hp"]) for u in units) / tot


def _gain_rage(state: dict, side: str, base: int, receiving: bool = False) -> None:
    """receiving=True — ярость за ПОЛУЧЕННЫЙ урон, с камбэк-кривой по HP отряда."""
    s = state[side]
    if receiving:
        frac = _team_hp_frac(s["units"])
        mult = B3_RAGE_COMEBACK_25 if frac < 0.25 else (
            B3_RAGE_COMEBACK_50 if frac < 0.50 else 1.0)
        base = int(round(base * mult))
    s["rage"] = min(B3_RAGE_MAX, s["rage"] + min(B3_RAGE_HIT_CAP, base))


def _apply_damage(state: dict, src_side: str, src_i: int | None, dst_side: str,
                  dst_i: int, raw: float, events: list, elem: str | None = None,
                  lifesteal: float = 0.0, ignore_def: float = 0.0,
                  no_reflect: bool = False) -> int:
    """Универсальное нанесение урона с щитами/отражением/яростью/логом."""
    src = state[src_side]["units"][src_i] if src_i is not None else None
    dst = state[dst_side]["units"][dst_i]
    if not dst["alive"]:
        return 0
    if dst["statuses"].get("invuln"):
        events.append(f"🛡 {dst['name']}: неуязвимость!")
        return 0
    dmg = raw
    if elem:
        dmg *= element_mult(elem, dst.get("element"))
    dmg *= _escalation(state)
    # статусы источника/цели
    if src:
        stt = src["statuses"]
        if stt.get("weaken"):
            dmg *= stt["weaken"]["mult"]
        if stt.get("dmg_bonus"):
            dmg *= 1 + stt["dmg_bonus"]["add"]
        if stt.pop("web", None):
            dmg *= 0.5
            events.append(f"🕸 {src['name']} скован паутиной: урон −50%")
    syn = state["ally"]["synergy"]
    if src_side == "ally" and syn.get("dmg_out"):
        dmg *= 1 + syn["dmg_out"]
    if dst_side == "ally" and syn.get("dmg_in"):
        dmg *= 1 + syn["dmg_in"]
    dfn = dst["def"] * (1 - ignore_def)
    if dst["statuses"].get("armor_break"):
        dfn *= 1 - dst["statuses"]["armor_break"]["frac"]
    if dst["statuses"].get("def_up"):
        dfn *= 1 + dst["statuses"]["def_up"]["add"]
    dmg = max(1, int(round(dmg - dfn * 0.5)))
    # щит
    if dst.get("shield", 0) > 0:
        absorbed = min(dst["shield"], dmg)
        dst["shield"] -= absorbed
        dmg -= absorbed
        if absorbed:
            events.append(f"🛡 Щит {dst['name']} поглотил {absorbed}")
    if dmg > 0:
        dst["hp"] = max(0, dst["hp"] - dmg)
        # VFX (Блок 2 «улучшения боя»): структурированный след урона за раунд —
        # state.log хранит только готовую текстовую строку, а фронту для чисел
        # урона/пульса атакующего нужны координаты сторон, не парсинг русского текста.
        state.setdefault("hits_round", []).append(
            {"side": dst_side, "i": dst_i, "dmg": dmg, "elem": elem,
             "src_side": src_side, "src_i": src_i})
        _gain_rage(state, src_side, B3_RAGE_PER_HIT_OUT)
        _gain_rage(state, dst_side, B3_RAGE_PER_HIT_IN, receiving=True)
        if dst_side == "enemy":
            state["dmg_total"] = state.get("dmg_total", 0) + dmg
        # вампиризм (навык + тёмная синергия)
        ls = lifesteal + (syn.get("lifesteal", 0) if src_side == "ally" else 0)
        if src and ls > 0 and src["alive"]:
            heal = int(round(dmg * ls))
            if heal:
                src["hp"] = min(src["hp_max"], src["hp"] + heal)
        # отражение
        refl = dst["statuses"].get("reflect")
        if refl and src and not no_reflect and src["alive"]:
            back = max(1, int(round(dmg * refl["frac"])))
            src["hp"] = max(0, src["hp"] - back)
            events.append(f"↩️ {dst['name']} отражает {back} в {src['name']}")
            if src["hp"] <= 0:
                _kill(state, src_side, src_i, events)
    if dst["hp"] <= 0:
        _kill(state, dst_side, dst_i, events)
    return dmg


def _kill(state: dict, side: str, idx: int, events: list) -> None:
    u = state[side]["units"][idx]
    if not u["alive"]:
        return
    u["alive"] = False
    u["hp"] = 0
    u["statuses"] = {}
    events.append(f"☠️ {u['emoji']} {u['name']} пал!")


def _heal(unit: dict, amount: int, events: list) -> None:
    if not unit["alive"] or amount <= 0:
        return
    before = unit["hp"]
    unit["hp"] = min(unit["hp_max"], unit["hp"] + amount)
    if unit["hp"] > before:
        events.append(f"💚 {unit['name']}: +{unit['hp'] - before} HP")


def _pick_target(state: dict, side_def: str, want: int | None) -> int | None:
    """Позиции: удар по флангу/тылу может перехватить фронт (мягкий шанс)."""
    units = state[side_def]["units"]
    alive = _alive_idx(units)
    if not alive:
        return None
    t = want if (want in alive) else alive[0]
    slot_of = {i: units[i].get("slot", i) for i in alive}
    tgt_slot = slot_of[t]
    if tgt_slot == 0 or len(alive) == 1:
        return t
    front = next((i for i in alive if slot_of[i] == 0), None)
    flank = next((i for i in alive if slot_of[i] == 1), None)
    if front is not None:
        ch = B3_INTERCEPT_REAR if tgt_slot == 2 else B3_INTERCEPT_FLANK
        if units[front].get("role") == "tank":
            ch += B3_INTERCEPT_TANK_BONUS
        if units[front]["statuses"].get("intercept_all"):
            ch = 1.0
        if random.random() < ch:
            return front
    elif flank is not None and tgt_slot == 2:
        if random.random() < B3_INTERCEPT_FALLBACK:
            return flank
    return t


# ── Ульты ─────────────────────────────────────────────────────────────────────

def _exec_ult(state: dict, u_i: int, mult: float, events: list) -> None:
    a_units = state["ally"]["units"]
    e_units = state["enemy"]["units"]
    a = a_units[u_i]
    code = UNITS[a["uid"]]["ult"]["code"]
    ev = events
    ev.append(f"💥 УЛЬТА: {UNITS[a['uid']]['ult']['name']}!")

    if code == "erupt":
        for t in _alive_idx(e_units):
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"] * 1.3 * mult, ev,
                          elem=a["element"])
            if e_units[t]["alive"]:
                e_units[t]["statuses"]["burn"] = {"dmg": int(a["atk"] * 0.25), "rounds": 3}
    elif code == "flame_wall":
        for u in a_units:
            if u["alive"]:
                u["shield"] = u.get("shield", 0) + int(u["hp_max"] * 0.20 * mult)
                u["statuses"]["reflect"] = {"frac": 0.35, "rounds": 1}
        ev.append("🔥 Стена пламени: щиты + отражение отряду")
    elif code == "rebirth":
        dead = [u for u in a_units if not u["alive"]]
        if dead and not state["ally"].get("rebirth_used"):
            u = dead[0]
            u["alive"] = True
            u["hp"] = int(u["hp_max"] * 0.30 * max(0.6, mult))
            state["ally"]["rebirth_used"] = True
            ev.append(f"🦅 {u['name']} ВОЗРОЖДЁН с {u['hp']} HP!")
        else:
            for u in a_units:
                if u["alive"]:
                    _heal(u, int(u["hp_max"] * 0.25 * mult), ev)
    elif code == "absolute_zero":
        state["enemy"]["skip_next"] = True
        ev.append("🧊 Абсолютный ноль: враг пропускает следующую фазу!")
    elif code == "ice_storm":
        t = _pick_target(state, "enemy", None)
        if t is not None:
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"] * 1.5 * mult, ev,
                          elem=a["element"])
            if e_units[t]["alive"]:
                e_units[t]["statuses"]["frozen"] = True
                ev.append(f"❄️ {e_units[t]['name']} заморожен!")
    elif code == "nast":
        for u in a_units:
            if u["alive"]:
                u["shield"] = u.get("shield", 0) + int(u["hp_max"] * 0.25 * mult)
        ev.append("❄️ Наст: щиты всему отряду")
    elif code == "groza":
        for t in _alive_idx(e_units):
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"] * 1.1 * mult, ev,
                          elem=a["element"])
    elif code == "shell_shock":
        t = _pick_target(state, "enemy", None)
        if t is not None:
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"] * mult, ev,
                          elem=a["element"])
            if e_units[t]["alive"]:
                e_units[t]["statuses"]["stunned"] = True
                ev.append(f"⚡ {e_units[t]['name']} оглушён!")
    elif code == "second_wind":
        # TODO(B2b/баланс): старый эффект был рунный (рука 5 рун + Фокус) — снят
        # вместе с рунным движком (B2a), нужна замена под AP-модель.
        ev.append("🕊 Второе дыхание!")
    elif code == "bastion":
        for u in a_units:
            if u["alive"]:
                u["statuses"]["invuln"] = {"rounds": 1}
        ev.append("🗿 Бастион: отряд неуязвим на фазу врага!")
    elif code == "shatter":
        t = _pick_target(state, "enemy", None)
        if t is not None:
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"] * 1.2 * mult, ev,
                          elem=a["element"])
            if e_units[t]["alive"]:
                e_units[t]["statuses"]["armor_break"] = {"frac": 0.40}
                ev.append(f"🪨 Броня {e_units[t]['name']} расколота (−40% до конца боя)")
    elif code == "roots":
        for u in a_units:
            if u["alive"]:
                _heal(u, int(u["hp_max"] * 0.20 * mult), ev)
        t = _first_alive(e_units)
        if t is not None:
            e_units[t]["statuses"]["weaken"] = {"mult": 0.5, "rounds": 1}
            ev.append(f"🌿 {e_units[t]['name']} скован корнями (−50% урона)")
    elif code == "nightmare":
        t = _pick_target(state, "enemy", None)
        if t is not None:
            missing = e_units[t]["hp_max"] - e_units[t]["hp"]
            raw = max(a["atk"] * 0.8, missing * 0.20) * mult
            _apply_damage(state, "ally", u_i, "enemy", t, raw, ev,
                          elem=a["element"], lifesteal=0.35)
    elif code == "cocoon":
        t = _first_alive(e_units)
        if t is not None:
            e_units[t]["statuses"]["weaken"] = {"mult": 0.5, "rounds": 2}
            e_units[t]["statuses"]["no_crit"] = {"rounds": 2}
            ev.append(f"🕷 {e_units[t]['name']} в коконе: −50% урона, 2 раунда")
    elif code == "requiem":
        state["enemy"]["rage"] = 0
        for u in a_units:
            if u["alive"]:
                u["statuses"]["dmg_bonus"] = {"add": 0.15, "rounds": 2}
        ev.append("🌑 Реквием: ярость врага обнулена, отряд +15% урона")
    elif code == "abyss_call":
        alive = _alive_idx(e_units)
        for k in range(5):
            alive = _alive_idx(e_units)
            if not alive:
                break
            t = random.choice(alive)
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"] * 0.45 * mult, ev,
                          elem=ELEMENTS[k])
        ev.append("🐉 Зов Бездны: пять стихий разом!")


# ── Фаза игрока ───────────────────────────────────────────────────────────────

def resume_qte(state: dict, tap_offset_ms: int) -> dict:
    """Продолжение после QTE (крит или ульта)."""
    pend = state.get("pending") or {}
    grade, zs = grade_tap(state.get("qte") or {}, tap_offset_ms,
                          int(state.get("zero_streak", 0)))
    state["zero_streak"] = zs
    state["qte"] = None
    state["pending"] = None
    events = state.setdefault("events_round", [])
    if pend.get("type") == "crit":
        from core.constants import B3_CRIT_MULT
        mult = B3_CRIT_MULT.get(grade, 1.0)
        _do_attack(state, pend["atk_i"], pend["tgt_i"], events, crit_mult=mult)
        if _battle_over(state):
            state["status"] = "won" if not _alive_idx(state["enemy"]["units"]) else "lost"
            return {"phase": "over", "grade": grade, "hits": state.pop("hits_round", [])}
        return {"phase": "resolved", "grade": grade, "hits": state.pop("hits_round", [])}
    if pend.get("type") == "ult":
        mult = B3_ULT_MULT.get(grade, 1.0)
        state["ally"]["rage"] = 0
        _exec_ult(state, pend["u"], mult, events)
        if _battle_over(state):
            state["status"] = "won" if not _alive_idx(state["enemy"]["units"]) else "lost"
            return {"phase": "over", "grade": grade, "hits": state.pop("hits_round", [])}
        return {"phase": "resolved", "grade": grade, "hits": state.pop("hits_round", [])}
    return {"phase": "resolved", "grade": grade, "hits": state.pop("hits_round", [])}


def request_ult(state: dict, unit_i: int) -> dict:
    """Ульта по кнопке (ярость 100): ставит QTE-паузу."""
    state["pending"] = {"type": "ult", "u": unit_i}
    state["qte"] = qte_window(1)
    state.setdefault("events_round", [])
    return {"phase": "qte", "qte_kind": "ult"}


def use_triad(state: dict) -> bool:
    """«Триада» (3 разные стихии): раз в бой AoE 120% средней атаки."""
    a = state["ally"]
    if not a.get("triad_available"):
        return False
    a["triad_available"] = False
    events = state.setdefault("events_round", [])
    alive = [u for u in a["units"] if u["alive"]]
    if not alive:
        return False
    avg_atk = sum(u["atk"] for u in alive) / len(alive)
    events.append("🌈 ТРИАДА СТИХИЙ!")
    src_i = a["units"].index(alive[0])
    for t in _alive_idx(state["enemy"]["units"]):
        _apply_damage(state, "ally", src_i, "enemy", t, avg_atk * B3_TRIAD_MULT, events)
    state["log"] = (state.get("log", []) + events)[-30:]
    state["events_round"] = []
    return True


# ── Фаза врага: EV-скоринг (детерминированный ИИ, C1) ──────────────────────────

def _expected_damage(state, src, ally_i) -> int:
    """Оценка урона врага src по союзнику ally_i БЕЗ мутаций (для EV-скоринга).
    Зеркалит боевую формулу: стихия, эскалация, укрытие(ranged), защита/вскрытая оборона, def."""
    from services.battle_grid import CELL_COVER
    from core.constants import B4_COVER_RANGED_MULT, B4_DEFEND_MULT, B4_EXPOSED_DEF_MULT
    ally = state["ally"]["units"][ally_i]
    raw = src["atk"] * element_mult(src.get("element"), ally.get("element")) * _escalation(state)
    ax, ay = _pos(ally)
    in_cover = state["grid"][ay][ax] == CELL_COVER
    ranged = _atk_range(src) >= 2
    if ranged and in_cover:
        raw *= B4_COVER_RANGED_MULT
    if ally.get("defending"):
        raw *= B4_DEFEND_MULT
    elif not in_cover:
        raw *= B4_EXPOSED_DEF_MULT
    return max(1, int(round(raw - ally["def"] * 0.5)))


def _threat_at(state, cell) -> float:
    """Суммарная угроза союзников для клетки cell: атака тех, кто в СЛЕДУЮЩИЙ ход
    дотянется до неё (грубая оценка = дальность хода AP + дальность атаки)."""
    from core.constants import B4_MOVE_AP
    total = 0.0
    for u in state["ally"]["units"]:
        if not u["alive"]:
            continue
        reach = (u["ap_max"] // max(1, B4_MOVE_AP)) + _atk_range(u)
        if grid_mod.manhattan(_pos(u), cell) <= reach:
            total += u["atk"]
    return total


def _best_enemy_plan(state, ei):
    """Перебор (клетка × цель) + защита. EV = урон + стратегия + выживание − риск.
    Детерминированный tie-break: EV → роль цели (dd>support>tank) → меньший индекс цели
    → меньшая стоимость хода. Возвращает план-словарь или None."""
    from services.battle_grid import reachable, line_of_sight, CELL_COVER, CELL_DANGER
    e = state["enemy"]["units"][ei]
    role_pref = {"dd": 3, "support": 2, "tank": 1}
    reach = reachable(state["grid"], _pos(e), B4_ENEMY_MOVE, _occupied(state, exclude=e))
    reach[_pos(e)] = 0                      # остаться на месте — тоже вариант
    low_hp_self = e["hp"] / max(1, e["hp_max"]) < 0.30
    best = None                            # (key_tuple, plan)
    allies = state["ally"]["units"]
    for cell, movecost in reach.items():
        cx, cy = cell
        cell_cover = state["grid"][cy][cx] == CELL_COVER
        cell_danger = state["grid"][cy][cx] == CELL_DANGER
        threat = _threat_at(state, cell)
        for ti, ally in enumerate(allies):
            if not ally["alive"]:
                continue
            if grid_mod.chebyshev(cell, _pos(ally)) > _atk_range(e):
                continue
            if not line_of_sight(state["grid"], cell, _pos(ally)):
                continue
            gain = _expected_damage(state, e, ti)
            strat = 0.0
            if ally["hp"] / max(1, ally["hp_max"]) < 0.35:
                strat += gain * 0.5                        # добить раненого
            if ally.get("role") == "support":
                strat += e["atk"] * 0.3                     # давить саппорта
            # threat — ОГРАНИЧЕННЫЙ штраф за опасную клетку, а не доминанта: он выбирает
            # между атакующими клетками (безопаснее = лучше), но не запрещает атаковать.
            # Сырой atk союзников (~55) несопоставим с митигированным уроном (~8), поэтому
            # берём малый вес; при низком HP врага вес растёт — тогда он предпочтёт отступить.
            threat_w = 0.15 if low_hp_self else 0.02
            surv = (e["atk"] * 0.2 if cell_cover else 0.0) - threat * threat_w
            cost = e["atk"] * 0.5 if cell_danger else 0.0
            ev = gain + strat + surv - cost
            key = (round(ev, 3), role_pref.get(ally.get("role"), 0), -ti, -movecost)
            if best is None or key > best[0]:
                best = (key, {"kind": "attack", "cell": cell, "target": ti})
    # запасной вариант — защита (встать в оборону), особенно если ранен и нет цели
    defend_ev = e["atk"] * 0.1 + (e["atk"] * 0.5 if low_hp_self else 0.0)
    defend_key = (round(defend_ev, 3), 0, 0, 0)
    if best is None or defend_key > best[0]:
        best = (defend_key, {"kind": "defend", "cell": _pos(e)})
    return best[1]


def _enemy_attack(state, ei, ti, events, mult=1.0):
    """Реальный удар врага по союзнику: укрытие/защита/вскрытая оборона + контрудар/обмерзание."""
    from services.battle_grid import CELL_COVER
    from core.constants import B4_COVER_RANGED_MULT, B4_DEFEND_MULT, B4_EXPOSED_DEF_MULT
    e = state["enemy"]["units"][ei]
    ally = state["ally"]["units"][ti]
    ax, ay = _pos(ally)
    in_cover = state["grid"][ay][ax] == CELL_COVER
    ranged = _atk_range(e) >= 2
    raw = e["atk"] * mult
    if ranged and in_cover:
        raw *= B4_COVER_RANGED_MULT
    if ally.get("defending"):
        raw *= B4_DEFEND_MULT
    elif not in_cover:
        raw *= B4_EXPOSED_DEF_MULT
    dmg = _apply_damage(state, "enemy", ei, "ally", ti, raw, events, elem=e.get("element"))
    events.append(f"💢 {e['emoji']} {e['name']} → {ally['name']}: −{dmg}")
    # контрудар защитной стойки союзника / обмерзание
    cnt = ally["statuses"].get("counter")
    if cnt and ally["alive"] and e["alive"]:
        back = max(1, int(ally["atk"] * cnt["frac"]))
        _apply_damage(state, "ally", ti, "enemy", ei, back, events, no_reflect=True)
        events.append(f"🦂 Контрудар: −{back} {e['name']}")
    if ally["statuses"].get("chill_aura"):
        state["enemy"]["rage"] = max(0, state["enemy"]["rage"] - 6)


def _beat(state, ei, kind, from_pos=None, to_pos=None, hits_from=None, text=""):
    """Онбординг боя: добавляет бит в «ленту хода врага» (state['timeline_round']) для
    пошаговой анимации на клиенте. Лента транзиентна (в БД не пишется — попается в
    _end_round). hits_from — индекс в hits_round, с которого этот бит нанёс урон:
    срез становится beat['hits'] (клиент проигрывает FX только по ним, без дублей)."""
    tl = state.get("timeline_round")
    if tl is None:
        return
    beat = {"actor": {"side": "enemy", "i": ei}, "kind": kind,
            "from": {"x": from_pos[0], "y": from_pos[1]} if from_pos else None,
            "to": {"x": to_pos[0], "y": to_pos[1]} if to_pos else None,
            "text": text}
    if hits_from is not None:
        beat["hits"] = list(state.get("hits_round", [])[hits_from:])
    tl.append(beat)


def _execute_enemy_plan(state, ei, plan, events):
    e = state["enemy"]["units"][ei]
    cell = plan.get("cell")
    old = _pos(e)
    if cell and cell != old:
        e["pos"] = {"x": cell[0], "y": cell[1]}
        _beat(state, ei, "move", from_pos=old, to_pos=cell,
              text=f"{e['emoji']} {e['name']} перемещается")
    if plan["kind"] == "attack":
        h0 = len(state.get("hits_round", []))
        _enemy_attack(state, ei, plan["target"], events)
        tgt = state["ally"]["units"][plan["target"]]
        _beat(state, ei, "attack", hits_from=h0,
              text=f"{e['emoji']} {e['name']} → {tgt['name']}")
    elif plan["kind"] == "defend":
        e["shield"] = e.get("shield", 0) + int(e["hp_max"] * 0.15)
        events.append(f"🛡 {e['name']} укрепляется")
        _beat(state, ei, "defend", text=f"🛡 {e['name']} укрепляется")


def _enemy_aoe(state, ei, events):
    e = state["enemy"]["units"][ei]
    events.append(f"💥 {e['emoji']} {e['name']}: СОКРУШАЮЩИЙ УДАР по всем!")
    h0 = len(state.get("hits_round", []))
    for ti in _alive_idx(state["ally"]["units"]):
        _enemy_attack(state, ei, ti, events, mult=0.7)
    _beat(state, ei, "aoe", hits_from=h0,
          text=f"{e['emoji']} {e['name']}: СОКРУШАЮЩИЙ УДАР!")


# ── Фаза врага и конец раунда ─────────────────────────────────────────────────

def _enemy_phase(state: dict, events: list) -> None:
    # Онбординг боя: открываем ленту битов на эту фазу (пошаговая анимация фронта).
    state["timeline_round"] = []
    # «Абсолютный ноль» и подобные ульты выставляют skip_next — вся фаза врага пропущена.
    if state["enemy"].get("skip_next"):
        state["enemy"]["skip_next"] = False
        events.append("🧊 Враг скован — фаза пропущена!")
        return
    # Ярость врага полна → ульта сильнейшего по самому раненому союзнику (1.8×);
    # ярость сбрасывается, а сам ультовавший враг пропускает обычное действие
    # (ульта = его ход). Делает шкалу «ярость врага» осмысленной угрозой (БЛ4).
    ult_ei = None
    if state["enemy"].get("rage", 0) >= B3_RAGE_MAX:
        ei = _strongest_enemy(state)
        alive_a = _alive_idx(state["ally"]["units"])
        if ei is not None and alive_a:
            ult_ei = ei
            state["enemy"]["rage"] = 0
            e = state["enemy"]["units"][ei]
            ti = min(alive_a, key=lambda i: state["ally"]["units"][i]["hp"])
            events.append(f"💥 УЛЬТА ВРАГА: {e['emoji']} {e['name']}!")
            h0 = len(state.get("hits_round", []))
            _enemy_attack(state, ei, ti, events, mult=1.8)
            _beat(state, ei, "ult", hits_from=h0,
                  text=f"💥 УЛЬТА: {e['emoji']} {e['name']}!")
            if _battle_over(state):
                return
    enemies = state["enemy"]["units"]
    for ei, e in enumerate(enemies):
        if not e["alive"] or ei == ult_ei:
            continue
        # Стена узла (Войны) и прочие статичные цели с atk 0 — НЕ ходят и не бьют
        # (по спеке стена — объект-цель, EV-ИИ ей не нужен).
        if not e.get("atk"):
            continue
        if e["statuses"].pop("frozen", None) or e["statuses"].pop("stunned", None):
            events.append(f"❄️ {e['name']} пропускает действие")
            _beat(state, ei, "skip", text=f"❄️ {e['name']} скован")
            continue
        is_boss = bool(e.get("boss"))
        if is_boss and state["round"] % 3 == 0:
            _enemy_aoe(state, ei, events)
            if _battle_over(state):
                return
            continue
        acts = 2 if is_boss else 1
        for _ in range(acts):
            if not e["alive"] or not _alive_idx(state["ally"]["units"]):
                break
            plan = _best_enemy_plan(state, ei)
            if plan is None:
                break
            _execute_enemy_plan(state, ei, plan, events)
            if _battle_over(state):
                return


def _tick_statuses(state: dict, events: list) -> None:
    # «Внезапная смерть»: бой не может длиться вечно (щиты/хилы в пат) —
    # с 20-го раунда обе стороны теряют растущий % HP, мимо щитов
    if state["round"] >= B3_SUDDEN_DEATH_ROUND:
        frac = 0.05 * (state["round"] - B3_SUDDEN_DEATH_ROUND + 1)
        events.append(f"⏳ Бездна поглощает арену: все теряют {int(frac * 100)}% HP!")
        for side in ("ally", "enemy"):
            for idx, u in enumerate(state[side]["units"]):
                if u["alive"]:
                    u["hp"] = max(0, u["hp"] - max(1, int(u["hp_max"] * frac)))
                    if u["hp"] <= 0:
                        _kill(state, side, idx, events)
    for side in ("ally", "enemy"):
        for idx, u in enumerate(state[side]["units"]):
            if not u["alive"]:
                continue
            st = u["statuses"]
            if st.get("burn"):
                d = st["burn"]["dmg"]
                u["hp"] = max(0, u["hp"] - d)
                events.append(f"🔥 {u['name']} горит: −{d}")
                st["burn"]["rounds"] -= 1
                if st["burn"]["rounds"] <= 0:
                    st.pop("burn")
                if u["hp"] <= 0:
                    _kill(state, side, idx, events)
                    continue
            if st.get("regen"):
                _heal(u, int(u["hp_max"] * st["regen"]["frac"]), events)
                st["regen"]["rounds"] -= 1
                if st["regen"]["rounds"] <= 0:
                    st.pop("regen")
            for key in ("reflect", "weaken", "dmg_bonus", "def_up",
                        "intercept_all", "invuln", "no_crit", "counter", "chill_aura"):
                if st.get(key) and isinstance(st[key], dict) and "rounds" in st[key]:
                    st[key]["rounds"] -= 1
                    if st[key]["rounds"] <= 0:
                        st.pop(key)


def _battle_over(state: dict) -> bool:
    return (not _alive_idx(state["ally"]["units"])
            or not _alive_idx(state["enemy"]["units"])
            or state["mode"] == "war" and not _alive_idx(state["enemy"]["units"]))


def _finish_round(state: dict, skip_enemy: bool = False) -> dict:
    events = state.get("events_round", [])
    if not skip_enemy and not _battle_over(state):
        _enemy_phase(state, events)
    if not _battle_over(state):
        _tick_statuses(state, events)
    state["log"] = (state.get("log", []) + events)[-30:]
    state["events_round"] = []
    won = not _alive_idx(state["enemy"]["units"])
    lost = not _alive_idx(state["ally"]["units"])
    hits = state.pop("hits_round", [])
    state.pop("timeline_round", None)   # онбординг боя: не даём ленте утечь в state (старый движок)
    if won or lost:
        state["status"] = "won" if won else "lost"
        return {"phase": "over", "won": won, "lost": lost, "hits": hits}
    begin_round(state)
    return {"phase": "round", "won": False, "lost": False, "hits": hits}


# ── AP-действия (Боёвка 4.0, замена раунда-руны, B1) ──────────────────────────
# ДОБАВЛЕНО в задаче B1: сосуществует со старым рунным кодом выше (снимет B2).

def _pos(u: dict) -> tuple:
    p = u["pos"]
    return (p["x"], p["y"])


def _occupied(state: dict, exclude=None) -> set:
    s = set()
    for side in ("ally", "enemy"):
        for u in state[side]["units"]:
            if u["alive"] and u is not exclude:
                s.add(_pos(u))
    return s


def _atk_range(unit: dict) -> int:
    from core.constants import B4_RANGE_BY_ROLE
    return B4_RANGE_BY_ROLE.get(unit.get("role"), 2)


def _skill_target_ok(state, ui, ti):
    """Целевой навык: цель — живой враг в дальности ≤2 и в линии видимости."""
    if ti is None:
        return False
    enemies = state["enemy"]["units"]
    if not (0 <= ti < len(enemies)) or not enemies[ti]["alive"]:
        return False
    u = state["ally"]["units"][ui]
    tgt = enemies[ti]
    return (grid_mod.chebyshev(_pos(u), _pos(tgt)) <= 2
            and grid_mod.line_of_sight(state["grid"], _pos(u), _pos(tgt)))


def _in_cell_type(state, u, cell_type) -> bool:
    x, y = _pos(u)
    return state["grid"][y][x] == cell_type


def begin_player_turn(state: dict) -> None:
    from services.battle_grid import CELL_DANGER
    from core.constants import B4_DANGER_HP_FRAC
    events = state.setdefault("events_round", [])
    for u in state["ally"]["units"]:
        if not u["alive"]:
            continue
        u["ap"] = u["ap_max"]
        u["defending"] = False
        if u["cd"].get("skill", 0) > 0:
            u["cd"]["skill"] -= 1
        if _in_cell_type(state, u, CELL_DANGER):
            dmg = max(1, int(u["hp_max"] * B4_DANGER_HP_FRAC))
            u["hp"] = max(0, u["hp"] - dmg)
            events.append(f"🔥 {u['name']} на опасной клетке: −{dmg}")
            if u["hp"] <= 0:
                _kill(state, "ally", state["ally"]["units"].index(u), events)


def apply_action(state: dict, action: dict) -> dict:
    """Одно действие игрока. Валидация AP/дальности/LoS — здесь (server-authoritative)."""
    from services.battle_grid import reachable, line_of_sight, CELL_COVER
    from core.constants import (B4_MOVE_AP, B4_ATK_AP, B4_DEF_AP,
                                B4_COVER_RANGED_MULT, B4_DEFEND_MULT, B4_EXPOSED_DEF_MULT)
    if state.get("pending"):
        return {"ok": False, "err": "Сначала заверши QTE."}
    typ = action.get("type")
    if typ == "end_turn":
        return end_player_turn(state)
    if typ == "triad":
        if not use_triad(state):
            return {"ok": False, "err": "Триада недоступна (нужны 3 разные стихии, раз в бой)."}
        if _battle_over(state):
            state["status"] = "won" if not _alive_idx(state["enemy"]["units"]) else "lost"
        return {"ok": True, "hits": state.pop("hits_round", [])}
    ui = action.get("unit_i")
    units = state["ally"]["units"]
    if not isinstance(ui, int) or not (0 <= ui < len(units)) or not units[ui]["alive"]:
        return {"ok": False, "err": "Юнит недоступен."}
    u = units[ui]
    events = state.setdefault("events_round", [])

    if typ == "move":
        cell = action.get("cell") or {}
        dst = (cell.get("x"), cell.get("y"))
        reach = reachable(state["grid"], _pos(u), u["ap"], _occupied(state, exclude=u))
        cost = reach.get(dst)
        if cost is None:
            return {"ok": False, "err": "Клетка недостижима."}
        u["ap"] -= cost * B4_MOVE_AP
        u["pos"] = {"x": dst[0], "y": dst[1]}
        return {"ok": True, "hits": state.pop("hits_round", []), "ap": u["ap"]}

    if typ == "defend":
        if u["ap"] < B4_DEF_AP:
            return {"ok": False, "err": "Недостаточно AP."}
        u["ap"] -= B4_DEF_AP
        u["defending"] = True
        events.append(f"🛡 {u['name']} встаёт в защиту")
        return {"ok": True, "ap": u["ap"]}

    if typ == "attack":
        if u["ap"] < B4_ATK_AP:
            return {"ok": False, "err": "Недостаточно AP."}
        ti = action.get("target_i")
        enemies = state["enemy"]["units"]
        if not isinstance(ti, int) or not (0 <= ti < len(enemies)) or not enemies[ti]["alive"]:
            return {"ok": False, "err": "Цель недоступна."}
        tgt = enemies[ti]
        if grid_mod.chebyshev(_pos(u), _pos(tgt)) > _atk_range(u):
            return {"ok": False, "err": "Цель вне дальности."}
        if not line_of_sight(state["grid"], _pos(u), _pos(tgt)):
            return {"ok": False, "err": "Нет линии видимости."}
        u["ap"] -= B4_ATK_AP
        syn_crit = state["ally"]["synergy"].get("crit", 0)
        if (not state.get("crit_qte_used") and random.random() < (u["crit"] + syn_crit)
                and not u["statuses"].get("no_crit")):
            state["crit_qte_used"] = True
            state["pending"] = {"type": "crit", "atk_i": ui, "tgt_i": ti}
            state["qte"] = qte_window(2)
            return {"ok": True, "phase": "qte", "qte_kind": "crit",
                    "hits": state.pop("hits_round", [])}
        _do_attack(state, ui, ti, events, crit_mult=1.0)
        if _battle_over(state):
            state["status"] = "won" if not _alive_idx(enemies) else "lost"
        return {"ok": True, "hits": state.pop("hits_round", []), "ap": u["ap"]}

    if typ == "skill":
        return _do_skill_action(state, ui, action.get("target_i"))
    return {"ok": False, "err": "Неизвестное действие."}


def _do_attack(state, atk_i, tgt_i, events, crit_mult=1.0, ranged=None):
    from services.battle_grid import CELL_COVER
    from core.constants import B4_COVER_RANGED_MULT, B4_EXPOSED_DEF_MULT
    u = state["ally"]["units"][atk_i]
    tgt = state["enemy"]["units"][tgt_i]
    if ranged is None:
        ranged = _atk_range(u) >= 2
    raw = u["atk"] * crit_mult
    if ranged and _in_cell_type(state, tgt, CELL_COVER):
        raw *= B4_COVER_RANGED_MULT
        events.append(f"🪨 {tgt['name']} в укрытии: урон −30%")
    if not tgt.get("defending") and not _in_cell_type(state, tgt, CELL_COVER):
        raw *= B4_EXPOSED_DEF_MULT
    dmg = _apply_damage(state, "ally", atk_i, "enemy", tgt_i, raw, events,
                        elem=u.get("element"))
    if crit_mult > 1.0:
        events.append(f"🎯 Крит! {u['name']} → {tgt['name']}: −{dmg}")
    else:
        events.append(f"⚔️ {u['name']} → {tgt['name']}: −{dmg}")


def end_player_turn(state: dict) -> dict:
    events = state.setdefault("events_round", [])
    _enemy_phase(state, events)            # пока СТАРЫЙ (intents); C1 заменит EV-ИИ
    if _battle_over(state):
        return _end_round(state, over=True)
    return _end_round(state, over=False)


def _end_round(state: dict, over: bool) -> dict:
    events = state.setdefault("events_round", [])
    _tick_statuses(state, events)
    state["log"] = (state.get("log", []) + events)[-30:]
    state["events_round"] = []
    hits = state.pop("hits_round", [])
    timeline = state.pop("timeline_round", [])   # онбординг боя: лента хода врага
    if _battle_over(state) or over:
        state["status"] = ("won" if not _alive_idx(state["enemy"]["units"]) else "lost")
        return {"ok": True, "phase": "over", "hits": hits, "timeline": timeline}
    begin_round(state)                     # пока СТАРЫЙ intents; C1 упростит telegraph
    begin_player_turn(state)               # новый AP-reset
    if _battle_over(state):
        state["status"] = ("won" if not _alive_idx(state["enemy"]["units"]) else "lost")
        return {"ok": True, "phase": "over", "hits": hits, "timeline": timeline}
    return {"ok": True, "phase": "next", "hits": hits, "timeline": timeline}


# ── Генераторы врагов ─────────────────────────────────────────────────────────

def spawn_positions(n_ally: int, n_enemy: int):
    """Отряд — колонки 0–1, враги — 5–6. Ряды по центру поля. Детерминировано."""
    rows = [2, 1, 3, 0, 4]  # порядок заполнения: центр наружу
    ally = [(0 if i % 2 == 0 else 1, rows[i]) for i in range(n_ally)]
    enemy = [(6 if i % 2 == 0 else 5, rows[i]) for i in range(n_enemy)]
    return ally[:n_ally], enemy[:n_enemy]


def _unit_ap_max(unit: dict) -> int:
    ap = B4_AP_BY_ROLE.get(unit.get("role"), 5)
    if UNITS.get(unit.get("uid"), {}).get("rarity") == "legendary":
        ap += B4_AP_LEGENDARY_BONUS
    return ap


_ENEMY_NAMES = {
    "dd":      [("Тень Бездны", "👁"), ("Пожиратель", "👹"), ("Мгла", "💀")],
    "tank":    [("Страж Врат", "🗿"), ("Панцирник", "🐢"), ("Голем Мглы", "🪨")],
    "support": [("Шёпот Тьмы", "🌫"), ("Костоправ", "🦴"), ("Пиявка", "🧿")],
}


def _mk_enemy(role: str, element: str, hp: int, atk: int, dfn: int,
              slot: int, boss: bool = False, name: str | None = None,
              emoji: str | None = None) -> dict:
    nm, em = random.choice(_ENEMY_NAMES[role])
    return {"name": name or nm, "emoji": emoji or em, "element": element,
            "role": role, "slot": slot, "hp_max": hp, "hp": hp,
            "atk": atk, "def": dfn, "boss": boss, "alive": True,
            "shield": 0, "statuses": {}, "crit": 0.10}


def gates_enemy_squad(floor: int) -> list[dict]:
    """Врата: 2 врага на этажах 1–2, дальше 3. Стихии случайны за бой."""
    f = max(1, int(floor))
    n = 2 if f <= 2 else 3
    hp = int(55 * (f ** 1.25))
    atk = int(4 + 4.5 * f)
    dfn = int(2 + 2.0 * f)
    roles = ["tank", "dd", "support"][:n] if n == 3 else ["tank", "dd"]
    random.shuffle(roles)
    els = random.sample(ELEMENTS, n)
    out = []
    for slot, (role, el) in enumerate(zip(roles, els)):
        k = {"tank": (1.5, 0.7, 1.4), "dd": (0.9, 1.3, 0.8),
             "support": (1.1, 0.9, 1.0)}[role]
        out.append(_mk_enemy(role, el, int(hp * k[0]), int(atk * k[1]),
                             int(dfn * k[2]), slot))
    return out


def abyss_enemy_squad(floor: int) -> list[dict]:
    return gates_enemy_squad(floor)


def abyss_boss(floor: int) -> list[dict]:
    f = max(1, int(floor))
    return [_mk_enemy("dd", random.choice(ELEMENTS),
                      hp=int(340 * (f ** 1.3)), atk=int(7 + 6 * f),
                      dfn=int(3 + 2.5 * f), slot=0, boss=True,
                      name="БОСС Бездны", emoji="👑")]


def war_wall(remaining_hp: float) -> list[dict]:
    seg = int(min(max(1.0, remaining_hp), WAR_WALL_SEGMENT_HP))
    w = _mk_enemy("tank", None, hp=seg, atk=0, dfn=8, slot=0,
                  name="Стена узла", emoji="🧱")
    w["element"] = None
    return [w]


# ── Публичное состояние ───────────────────────────────────────────────────────

def _pub_unit(u: dict) -> dict:
    el = ELEMENT_META.get(u.get("element")) or {}
    stt = u.get("statuses", {})
    p = u.get("pos") or {}
    return {"name": u["name"], "emoji": u["emoji"], "element": u.get("element"),
            "element_emoji": el.get("emoji", ""), "role": u.get("role"),
            "pos": {"x": p.get("x", 0), "y": p.get("y", 0)},
            "hp": u["hp"], "hp_max": u["hp_max"],
            "shield": u.get("shield", 0), "alive": u["alive"],
            "boss": bool(u.get("boss")),
            "defending": bool(u.get("defending")),
            "fx": [k for k in ("burn", "frozen", "stunned", "reflect", "regen",
                               "weaken", "invuln", "intercept_all", "web",
                               "armor_break", "dmg_bonus", "counter", "def_up",
                               "chill_aura") if stt.get(k)]}


def public_state(state: dict, battle_id: int) -> dict:
    from core.constants import B4_MOVE_AP, B4_ATK_AP, B4_SKILL_AP, B4_DEF_AP
    a, e = state["ally"], state["enemy"]
    q = state.get("qte") or {}
    pend = state.get("pending") or {}

    def ally_unit(u):
        meta = UNITS[u["uid"]]
        return dict(
            _pub_unit(u), uid=u["uid"], atk=u["atk"], level=u.get("level", 1),
            ap=u.get("ap", 0), ap_max=u.get("ap_max", 0), range=_atk_range(u),
            skill_cd=u.get("cd", {}).get("skill", 0),
            skill_name=meta["skill"]["name"], skill_desc=meta["skill"]["desc"],
            ult_name=meta["ult"]["name"], ult_desc=meta["ult"]["desc"])

    return {
        "battle_id": battle_id, "status": state.get("status", "active"),
        "mode": state.get("mode"), "round": state.get("round", 1),
        "grid": state.get("grid", []),
        "ally": {"units": [ally_unit(u) for u in a["units"]],
                 "rage": a["rage"],
                 "synergy": a.get("synergy", {}),
                 "triad_available": a.get("triad_available", False)},
        "enemy": {"units": [_pub_unit(u) for u in e["units"]],
                  "rage": e["rage"],
                  "intents": e.get("intents", [])},
        "pending": {"type": pend.get("type")} if pend else None,
        "qte": ({"ring_ms": q.get("ring_ms", 1400),
                 "perfect_ms": q.get("perfect_ms", 120),
                 "good_ms": q.get("good_ms", 350)} if q else None),
        "escalation": round(_escalation(state) - 1.0, 2),
        "log": state.get("log", [])[-8:],
        "rage_max": B3_RAGE_MAX,
        "ap_costs": {"move": B4_MOVE_AP, "attack": B4_ATK_AP,
                     "skill": B4_SKILL_AP, "defend": B4_DEF_AP},
    }


def dumps(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False)


def loads(raw: str) -> dict:
    return json.loads(raw or "{}")


def now() -> float:
    return time.time()


_SKILL_TARGET_CODES = {"burn", "frost_bite", "chain", "pierce", "drain", "void_strike", "web"}


def _do_skill_action(state, ui, target_i):
    from core.constants import B4_SKILL_AP, B4_SKILL_CD
    u = state["ally"]["units"][ui]
    if u["ap"] < B4_SKILL_AP:
        return {"ok": False, "err": "Недостаточно AP для навыка."}
    if u["cd"].get("skill", 0) > 0:
        return {"ok": False, "err": f"Навык на кулдауне ({u['cd']['skill']})."}
    code = UNITS[u["uid"]]["skill"]["code"]
    if code in _SKILL_TARGET_CODES and not _skill_target_ok(state, ui, target_i):
        return {"ok": False, "err": "Цель навыка вне дальности или нет линии видимости."}
    events = state.setdefault("events_round", [])
    u["ap"] -= B4_SKILL_AP
    u["cd"]["skill"] = B4_SKILL_CD
    _apply_skill_effect(state, ui, target_i, code, events)
    if _battle_over(state):
        state["status"] = "won" if not _alive_idx(state["enemy"]["units"]) else "lost"
    return {"ok": True, "hits": state.pop("hits_round", []), "ap": u["ap"]}


def _apply_skill_effect(state, u_i, ti, code, ev):
    a_units = state["ally"]["units"]
    e_units = state["enemy"]["units"]
    a = a_units[u_i]

    if code == "burn":
        _apply_damage(state, "ally", u_i, "enemy", ti, a["atk"] * 0.9, ev, elem=a["element"])
        if e_units[ti]["alive"]:
            e_units[ti]["statuses"]["burn"] = {"dmg": int(a["atk"] * 0.25), "rounds": 3}
            ev.append(f"🔥 {e_units[ti]['name']} горит (3 раунда)")
    elif code == "ember_shell":
        a["shield"] = a.get("shield", 0) + int(a["hp_max"] * 0.25)
        a["statuses"]["reflect"] = {"frac": 0.30, "rounds": 1}
        ev.append(f"🐗 {a['name']}: раскалённый панцирь (щит + отражение 30%)")
    elif code == "mend":
        hurt = [u for u in a_units if u["alive"] and u["hp"] < u["hp_max"]]
        if hurt:
            w = min(hurt, key=lambda u: u["hp"] / u["hp_max"])
            _heal(w, int(w["hp_max"] * 0.25), ev)
    elif code == "chill_taunt":
        a["statuses"]["intercept_all"] = {"rounds": 1}
        a["statuses"]["chill_aura"] = {"rounds": 1}
        ev.append(f"🧊 {a['name']} принимает удары на себя (обмерзание)")
    elif code == "frost_bite":
        _apply_damage(state, "ally", u_i, "enemy", ti, a["atk"], ev, elem=a["element"])
        if e_units[ti]["alive"] and random.random() < 0.20:
            e_units[ti]["statuses"]["frozen"] = True
            ev.append(f"❄️ {e_units[ti]['name']} заморожен — пропустит действие!")
    elif code == "ice_shield":
        alive = [u for u in a_units if u["alive"]]
        w = min(alive, key=lambda u: u["hp"] / u["hp_max"])
        w["shield"] = w.get("shield", 0) + int(w["hp_max"] * 0.30)
        ev.append(f"🦌 Наледь: щит {w['name']} +{int(w['hp_max'] * 0.30)}")
    elif code == "chain":
        _apply_damage(state, "ally", u_i, "enemy", ti, a["atk"], ev, elem=a["element"])
        others = [i for i in _alive_idx(e_units) if i != ti]
        if others:
            j = random.choice(others)
            d2 = _apply_damage(state, "ally", u_i, "enemy", j, a["atk"] * 0.4, ev, elem=a["element"])
            ev.append(f"⚡ Молния перескакивает на {e_units[j]['name']}: −{d2}")
    elif code == "counter_stance":
        a["shield"] = a.get("shield", 0) + int(a["hp_max"] * 0.20)
        a["statuses"]["counter"] = {"frac": 0.80, "rounds": 1}
        ev.append(f"🦂 {a['name']}: разрядная стойка (щит + контрудар)")
    elif code == "tailwind":
        _gain_rage(state, "ally", 10)
        a["statuses"]["dmg_bonus"] = {"add": 0.15, "rounds": 1}
        ev.append(f"🕊 Попутный ветер: +10 ярости, {a['name']} бьёт сильнее в этом раунде")
    elif code == "taunt_all":
        a["statuses"]["intercept_all"] = {"rounds": 1}
        a["statuses"]["def_up"] = {"add": 0.5, "rounds": 1}
        ev.append(f"🗿 {a['name']} — бастион: принимает ВСЕ удары (+50% защиты)")
    elif code == "pierce":
        _apply_damage(state, "ally", u_i, "enemy", ti, a["atk"] * 1.1, ev,
                      elem=a["element"], ignore_def=0.4)
        ev.append("🪨 Пробитие: 40% защиты цели проигнорировано")
    elif code == "regrow":
        for u in a_units:
            if u["alive"]:
                _heal(u, int(u["hp_max"] * 0.10), ev)
                u["statuses"]["regen"] = {"frac": 0.05, "rounds": 2}
        ev.append("🌿 Прорастание: отряд регенерирует 2 раунда")
    elif code == "drain":
        _apply_damage(state, "ally", u_i, "enemy", ti, a["atk"], ev, elem=a["element"], lifesteal=0.35)
    elif code == "web":
        e_units[ti]["statuses"]["web"] = True
        a["shield"] = a.get("shield", 0) + int(a["hp_max"] * 0.15)
        ev.append(f"🕷 Паутина на {e_units[ti]['name']}: его атака −50%")
    elif code == "grief":
        stolen = min(12, state["enemy"]["rage"])
        state["enemy"]["rage"] -= stolen
        _gain_rage(state, "ally", stolen)
        ev.append(f"🌑 Скорбь: украдено {stolen} ярости врага")
    elif code == "void_strike":
        _apply_damage(state, "ally", u_i, "enemy", ti, a["atk"] * 1.15, ev, elem=a["element"])
        el = ELEMENT_META.get(a["element"], {}).get("emoji", "🌈")
        ev.append(f"🐉 Удар Пустоты {el}: стихия под слабость врага")
