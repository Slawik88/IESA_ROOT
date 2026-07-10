# services/battle3.py — Боёвка 3.0 «Руны отряда» (BATTLE_REWORK_CONCEPT.md).
#
# Server-authoritative движок: колода/рука/ярость/фокус/позиции/телеграф/QTE
# живут ТОЛЬКО в state (battles.state_json). Клиент шлёт порядок рун, цели и
# сырые tap_offset_ms — грейдит сервер (grade_tap из battle.py, анти-чит там же).
#
# Раунд: фаза игрока (3 руны в выбранном порядке) → фаза врага (по телеграфу).
# QTE только на критах (первый прок за раунд) и ультах — пауза pending/resume.
import json
import random
import time

from core.constants import (
    B3_HAND_SIZE, B3_FOCUS_START, B3_FOCUS_PER_ROUND, B3_FOCUS_CAP,
    B3_FOCUS_REROLL_COST, B3_FOCUS_CRIT_COST,
    B3_RAGE_MAX, B3_RAGE_PER_HIT_OUT, B3_RAGE_PER_HIT_IN, B3_RAGE_HIT_CAP,
    B3_RAGE_COMEBACK_50, B3_RAGE_COMEBACK_25,
    B3_CRIT_MULT, B3_ULT_MULT,
    B3_INTERCEPT_REAR, B3_INTERCEPT_FLANK, B3_INTERCEPT_FALLBACK,
    B3_INTERCEPT_TANK_BONUS,
    B3_ESCALATION_FROM_ROUND, B3_ESCALATION_STEP, B3_ESCALATION_CAP,
    B3_TRIAD_MULT, WAR_WALL_SEGMENT_HP,
)
from core.units import (
    UNITS, unit_stats, element_mult, ELEMENT_META, ELEMENT_SYNERGY, ELEMENTS, _BEATS,
)
from services.battle import qte_window, grade_tap

B3_SUDDEN_DEATH_ROUND = 20   # с этого раунда обе стороны теряют HP каждый раунд

RUNE_KINDS = ("atk", "def", "skill")
RUNE_EMOJI = {"atk": "⚔️", "def": "🛡", "skill": "✨"}


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
    state = {
        "mode": mode, "round": 0, "status": "active",
        "ally": {"units": allies, "rage": 0, "focus": B3_FOCUS_START,
                 "synergy": syn, "triad_available": meta["triad"],
                 "rebirth_used": False},
        "enemy": {"units": enemies, "rage": 0, "intents": [], "skip_next": False},
        "deck": [], "discard": [], "hand": [], "hand_size_next": B3_HAND_SIZE,
        "pending": None, "qte": None, "zero_streak": 0,
        "log": [], "dmg_total": 0,
        **(ctx or {}),
    }
    _rebuild_deck(state)
    begin_round(state)
    return state


def _rebuild_deck(state: dict) -> None:
    deck = []
    for i, u in enumerate(state["ally"]["units"]):
        if u["alive"]:
            for kind in RUNE_KINDS:
                deck.append({"u": i, "k": kind})
    random.shuffle(deck)
    state["deck"], state["discard"], state["hand"] = deck, [], []


def _draw(state: dict, n: int) -> None:
    for _ in range(n):
        if not state["deck"]:
            state["deck"] = [r for r in state["discard"]
                             if state["ally"]["units"][r["u"]]["alive"]]
            random.shuffle(state["deck"])
            state["discard"] = []
        if not state["deck"]:
            break
        state["hand"].append(state["deck"].pop())


def _purge_dead_runes(state: dict, side: str, idx: int) -> None:
    """Смерть юнита игрока — его руны изымаются из колоды/сброса/руки."""
    if side != "ally":
        return
    for pile in ("deck", "discard", "hand"):
        state[pile] = [r for r in state[pile] if r["u"] != idx]


# ── Раунд: начало, телеграф ───────────────────────────────────────────────────

def begin_round(state: dict) -> None:
    state["round"] += 1
    a = state["ally"]
    a["focus"] = min(B3_FOCUS_CAP, a["focus"] + (B3_FOCUS_PER_ROUND if state["round"] > 1 else 0))
    state["hand"] = []
    _draw(state, state.get("hand_size_next", B3_HAND_SIZE))
    state["hand_size_next"] = B3_HAND_SIZE
    state["crit_qte_used"] = False
    # Порождение Бездны: стихия подстраивается под слабость первого живого врага
    tgt = _first_alive(state["enemy"]["units"])
    if tgt is not None:
        enemy_el = state["enemy"]["units"][tgt].get("element")
        for u in a["units"]:
            if u["uid"] == "u_porozhdenie" and u["alive"] and enemy_el:
                u["element"] = next((el for el, beats in _BEATS.items()
                                     if beats == enemy_el), None) or "dark"
    _roll_intents(state)


def _first_alive(units: list[dict]) -> int | None:
    for i, u in enumerate(units):
        if u["alive"]:
            return i
    return None


def _alive_idx(units: list[dict]) -> list[int]:
    return [i for i, u in enumerate(units) if u["alive"]]


def _roll_intents(state: dict) -> None:
    """Телеграф: намерения врага на ЕГО следующую фазу — игрок видит их заранее."""
    e, a = state["enemy"], state["ally"]
    intents = []
    if e.get("skip_next"):
        e["intents"] = [{"i": i, "kind": "frozen"} for i in _alive_idx(e["units"])]
        return
    ally_alive = _alive_idx(a["units"])
    ult_assigned = e["rage"] >= B3_RAGE_MAX
    for i in _alive_idx(e["units"]):
        u = e["units"][i]
        if u["statuses"].get("frozen") or u["statuses"].get("stunned"):
            intents.append({"i": i, "kind": "frozen"})
            continue
        if ult_assigned:
            intents.append({"i": i, "kind": "ult",
                            "t": random.choice(ally_alive) if ally_alive else None})
            ult_assigned = False
            continue
        if u.get("boss") and state["round"] % 3 == 0:
            intents.append({"i": i, "kind": "aoe"})
            continue
        role = u.get("role", "dd")
        hurt = [j for j in _alive_idx(e["units"])
                if e["units"][j]["hp"] < e["units"][j]["hp_max"] * 0.7]
        if role == "support" and hurt:
            intents.append({"i": i, "kind": "heal", "t": min(
                hurt, key=lambda j: e["units"][j]["hp"] / e["units"][j]["hp_max"])})
        elif role == "tank" and random.random() < 0.4:
            intents.append({"i": i, "kind": "def"})
        elif u.get("atk", 0) > 0 and ally_alive:
            intents.append({"i": i, "kind": "atk", "t": random.choice(ally_alive)})
        else:
            intents.append({"i": i, "kind": "def"})
    e["intents"] = intents


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
    _purge_dead_runes(state, side, idx)


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


# ── Руны игрока ───────────────────────────────────────────────────────────────

def _rune_steps(state: dict, order: list[int], targets: dict) -> list[dict]:
    """Рука → очередь шагов (по одному на руну), в порядке игрока."""
    steps = []
    for hi in order:
        rune = state["hand"][hi]
        steps.append({"hi": hi, "u": rune["u"], "k": rune["k"],
                      "t": targets.get(str(hi), targets.get(hi)),
                      "forced_crit": bool(rune.get("forced_crit"))})
    return steps


def _exec_attack(state: dict, u_i: int, tgt: int | None, events: list,
                 crit_mult: float = 1.0, power: float = 1.0) -> None:
    a = state["ally"]["units"][u_i]
    t = _pick_target(state, "enemy", tgt)
    if t is None:
        return
    dst = state["enemy"]["units"][t]
    raw = a["atk"] * power * crit_mult
    tag = " КРИТ!" if crit_mult > 1.0 else ""
    dmg = _apply_damage(state, "ally", u_i, "enemy", t, raw, events, elem=a["element"])
    events.append(f"⚔️ {a['emoji']} {a['name']} бьёт {dst['emoji']} {dst['name']}: −{dmg}{tag}")


def _exec_defense(state: dict, u_i: int, events: list) -> None:
    a = state["ally"]["units"][u_i]
    shield = int(round(a["def"] * 2.5 + a["hp_max"] * 0.10))
    a["shield"] = a.get("shield", 0) + shield
    _gain_rage(state, "ally", 6)
    events.append(f"🛡 {a['emoji']} {a['name']}: щит +{shield}")


def _exec_skill(state: dict, u_i: int, tgt: int | None, events: list) -> None:
    a_units = state["ally"]["units"]
    e_units = state["enemy"]["units"]
    a = a_units[u_i]
    code = UNITS[a["uid"]]["skill"]["code"]
    ev = events

    def enemy_t() -> int | None:
        return _pick_target(state, "enemy", tgt)

    if code == "burn":
        t = enemy_t()
        if t is not None:
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"] * 0.9, ev, elem=a["element"])
            e_units[t]["statuses"]["burn"] = {"dmg": int(a["atk"] * 0.25), "rounds": 3}
            ev.append(f"🔥 {e_units[t]['name']} горит (3 раунда)")
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
        a["statuses"]["chill_aura"] = {"rounds": 1}   # атакующие теряют 6 ярости врага
        ev.append(f"🧊 {a['name']} принимает удары на себя (обмерзание)")
    elif code == "frost_bite":
        t = enemy_t()
        if t is not None:
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"], ev, elem=a["element"])
            if e_units[t]["alive"] and random.random() < 0.20:
                e_units[t]["statuses"]["frozen"] = True
                ev.append(f"❄️ {e_units[t]['name']} заморожен — пропустит действие!")
    elif code == "ice_shield":
        alive = [u for u in a_units if u["alive"]]
        w = min(alive, key=lambda u: u["hp"] / u["hp_max"])
        w["shield"] = w.get("shield", 0) + int(w["hp_max"] * 0.30)
        ev.append(f"🦌 Наледь: щит {w['name']} +{int(w['hp_max'] * 0.30)}")
    elif code == "chain":
        t = enemy_t()
        if t is not None:
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"], ev, elem=a["element"])
            others = [i for i in _alive_idx(e_units) if i != t]
            if others:
                j = random.choice(others)
                d2 = _apply_damage(state, "ally", u_i, "enemy", j, a["atk"] * 0.4, ev,
                                   elem=a["element"])
                ev.append(f"⚡ Молния перескакивает на {e_units[j]['name']}: −{d2}")
    elif code == "counter_stance":
        a["shield"] = a.get("shield", 0) + int(a["hp_max"] * 0.20)
        a["statuses"]["counter"] = {"frac": 0.80, "rounds": 1}
        ev.append(f"🦂 {a['name']}: разрядная стойка (щит + контрудар)")
    elif code == "tailwind":
        _gain_rage(state, "ally", 10)
        state["hand_size_next"] = max(state.get("hand_size_next", 3), 4)
        ev.append("🕊 Попутный ветер: +10 ярости, в следующем раунде 4 руны!")
    elif code == "taunt_all":
        a["statuses"]["intercept_all"] = {"rounds": 1}
        a["statuses"]["def_up"] = {"add": 0.5, "rounds": 1}
        ev.append(f"🗿 {a['name']} — бастион: принимает ВСЕ удары (+50% защиты)")
    elif code == "pierce":
        t = enemy_t()
        if t is not None:
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"] * 1.1, ev,
                          elem=a["element"], ignore_def=0.4)
            ev.append("🪨 Пробитие: 40% защиты цели проигнорировано")
    elif code == "regrow":
        for u in a_units:
            if u["alive"]:
                _heal(u, int(u["hp_max"] * 0.10), ev)
                u["statuses"]["regen"] = {"frac": 0.05, "rounds": 2}
        ev.append("🌿 Прорастание: отряд регенерирует 2 раунда")
    elif code == "drain":
        t = enemy_t()
        if t is not None:
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"], ev,
                          elem=a["element"], lifesteal=0.35)
    elif code == "web":
        alive = _alive_idx(e_units)
        if alive:
            t = tgt if tgt in alive else max(
                alive, key=lambda i: e_units[i].get("atk", 0))
            e_units[t]["statuses"]["web"] = True
            a["shield"] = a.get("shield", 0) + int(a["hp_max"] * 0.15)
            ev.append(f"🕷 Паутина на {e_units[t]['name']}: его атака −50%")
    elif code == "grief":
        stolen = min(12, state["enemy"]["rage"])
        state["enemy"]["rage"] -= stolen
        _gain_rage(state, "ally", stolen)
        ev.append(f"🌑 Скорбь: украдено {stolen} ярости врага")
    elif code == "void_strike":
        t = enemy_t()
        if t is not None:
            _apply_damage(state, "ally", u_i, "enemy", t, a["atk"] * 1.15, ev,
                          elem=a["element"])
            el = ELEMENT_META.get(a["element"], {}).get("emoji", "🌈")
            ev.append(f"🐉 Удар Пустоты {el}: стихия под слабость врага")


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
            # руны воскресшего возвращаются в сброс (рука не трогается)
            idx = a_units.index(u)
            state["discard"].extend({"u": idx, "k": k} for k in RUNE_KINDS)
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
        state["hand_size_next"] = 5
        state["ally"]["focus"] = min(B3_FOCUS_CAP, state["ally"]["focus"] + 1)
        ev.append("🕊 Второе дыхание: следующий раунд — 5 рун и +1 🧿!")
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

def play_round(state: dict, order: list[int], targets: dict) -> dict:
    """Запуск фазы игрока. Возвращает {phase:'qte'|'done', ...}. Валидация —
    в роутере (это чистая логика)."""
    events = []
    steps = _rune_steps(state, order, targets)
    played = [state["hand"][hi] for hi in sorted(order, reverse=True)]
    for hi in sorted(order, reverse=True):
        state["hand"].pop(hi)
    state["discard"].extend(played)
    state["queue"] = steps
    state["events_round"] = events
    return _process_queue(state)


def _process_queue(state: dict) -> dict:
    """Крутим очередь шагов; крит-прок → пауза QTE (1 раз за раунд)."""
    events = state["events_round"]
    while state["queue"]:
        step = state["queue"][0]
        u = state["ally"]["units"][step["u"]]
        if not u["alive"]:
            state["queue"].pop(0)
            continue
        if step["k"] == "atk":
            syn_crit = state["ally"]["synergy"].get("crit", 0)
            if step.get("forced_crit"):
                state["queue"].pop(0)
                _exec_attack(state, step["u"], step["t"], events,
                             crit_mult=B3_CRIT_MULT["perfect"])
                continue
            if (not state.get("crit_qte_used")
                    and random.random() < (u["crit"] + syn_crit)
                    and not u["statuses"].get("no_crit")):
                # пауза: клиент должен подтвердить крит тапом
                state["crit_qte_used"] = True
                state["pending"] = {"type": "crit", "step": step}
                state["queue"].pop(0)
                state["qte"] = qte_window(2)
                return {"phase": "qte", "qte_kind": "crit", "hits": state.pop("hits_round", [])}
            state["queue"].pop(0)
            _exec_attack(state, step["u"], step["t"], events)
        elif step["k"] == "def":
            state["queue"].pop(0)
            _exec_defense(state, step["u"], events)
        else:
            state["queue"].pop(0)
            _exec_skill(state, step["u"], step["t"], events)
        if _battle_over(state):
            return _finish_round(state, skip_enemy=True)
    return _finish_round(state)


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
        step = pend["step"]
        mult = B3_CRIT_MULT.get(grade, 1.0)
        if mult > 1.0:
            events.append(f"🎯 Крит подтверждён ({grade})!")
        _exec_attack(state, step["u"], step["t"], events, crit_mult=mult)
        if _battle_over(state):
            return {**_finish_round(state, skip_enemy=True), "grade": grade}
        return {**_process_queue(state), "grade": grade}
    if pend.get("type") == "ult":
        mult = B3_ULT_MULT.get(grade, 1.0)
        state["ally"]["rage"] = 0
        _exec_ult(state, pend["u"], mult, events)
        if _battle_over(state):
            return {**_finish_round(state, skip_enemy=True), "grade": grade}
        # ульта вне очереди рун: если очередь пуста и рука пуста — доигрываем фазу врага
        if not state["queue"] and not state["hand"]:
            return {**_finish_round(state), "grade": grade}
        state["log"] = (state.get("log", []) + events)[-30:]
        state["events_round"] = []
        return {"phase": "mid", "grade": grade, "hits": state.pop("hits_round", [])}
    return {"phase": "mid", "grade": grade, "hits": state.pop("hits_round", [])}


def request_ult(state: dict, unit_i: int) -> dict:
    """Ульта по кнопке (ярость 100): ставит QTE-паузу."""
    state["pending"] = {"type": "ult", "u": unit_i}
    state["qte"] = qte_window(1)
    state.setdefault("events_round", [])
    return {"phase": "qte", "qte_kind": "ult"}


def reroll_rune(state: dict, hand_i: int) -> bool:
    """Фокус: переброс одной руны руки."""
    a = state["ally"]
    if a["focus"] < B3_FOCUS_REROLL_COST or not (0 <= hand_i < len(state["hand"])):
        return False
    a["focus"] -= B3_FOCUS_REROLL_COST
    state["discard"].append(state["hand"].pop(hand_i))
    _draw(state, 1)
    return True


def mark_forced_crit(state: dict, hand_i: int) -> bool:
    """Фокус: гарантированный крит на руну-атаку."""
    a = state["ally"]
    if a["focus"] < B3_FOCUS_CRIT_COST or not (0 <= hand_i < len(state["hand"])):
        return False
    if state["hand"][hand_i]["k"] != "atk" or state["hand"][hand_i].get("forced_crit"):
        return False
    a["focus"] -= B3_FOCUS_CRIT_COST
    state["hand"][hand_i]["forced_crit"] = True
    return True


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


# ── Фаза врага и конец раунда ─────────────────────────────────────────────────

def _enemy_phase(state: dict, events: list) -> None:
    e, a = state["enemy"], state["ally"]
    if e.get("skip_next"):
        e["skip_next"] = False
        events.append("🧊 Враг скован — фаза пропущена!")
        return
    for intent in e.get("intents", []):
        i = intent["i"]
        u = e["units"][i]
        if not u["alive"]:
            continue
        if u["statuses"].pop("frozen", None) or u["statuses"].pop("stunned", None):
            events.append(f"❄️ {u['name']} пропускает действие")
            continue
        kind = intent.get("kind")
        acts = 2 if u.get("boss") and kind == "atk" else 1
        for _ in range(acts):
            if kind == "atk":
                t = _pick_target(state, "ally", intent.get("t"))
                if t is None:
                    return
                tgt_u = a["units"][t]
                dmg = _apply_damage(state, "enemy", i, "ally", t, u["atk"], events,
                                    elem=u.get("element"))
                events.append(f"💢 {u['emoji']} {u['name']} бьёт {tgt_u['name']}: −{dmg}")
                # контрудар/обмерзание защитных стоек
                cnt = tgt_u["statuses"].get("counter")
                if cnt and tgt_u["alive"] and u["alive"]:
                    back = max(1, int(tgt_u["atk"] * cnt["frac"]))
                    _apply_damage(state, "ally", t, "enemy", i, back, events,
                                  no_reflect=True)
                    events.append(f"🦂 Контрудар: −{back} {u['name']}")
                if tgt_u["statuses"].get("chill_aura"):
                    e["rage"] = max(0, e["rage"] - 6)
            elif kind == "aoe":
                events.append(f"💥 {u['emoji']} {u['name']}: СОКРУШАЮЩИЙ УДАР по всем!")
                for t in _alive_idx(a["units"]):
                    _apply_damage(state, "enemy", i, "ally", t, u["atk"] * 0.7, events,
                                  elem=u.get("element"))
            elif kind == "ult":
                e["rage"] = 0
                t = _pick_target(state, "ally", intent.get("t"))
                if t is not None:
                    events.append(f"💥 УЛЬТА ВРАГА: {u['emoji']} {u['name']}!")
                    _apply_damage(state, "enemy", i, "ally", t, u["atk"] * 1.8, events,
                                  elem=u.get("element"))
            elif kind == "heal":
                t = intent.get("t")
                if t is not None and e["units"][t]["alive"]:
                    _heal(e["units"][t], int(e["units"][t]["hp_max"] * 0.18), events)
            else:  # def
                u["shield"] = u.get("shield", 0) + int(u["hp_max"] * 0.15)
                events.append(f"🛡 {u['name']} укрепляется")
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
    if won or lost:
        state["status"] = "won" if won else "lost"
        return {"phase": "over", "won": won, "lost": lost, "hits": hits}
    begin_round(state)
    return {"phase": "round", "won": False, "lost": False, "hits": hits}


# ── Генераторы врагов ─────────────────────────────────────────────────────────

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
    return {"name": u["name"], "emoji": u["emoji"], "element": u.get("element"),
            "element_emoji": el.get("emoji", ""), "role": u.get("role"),
            "slot": u.get("slot", 0), "hp": u["hp"], "hp_max": u["hp_max"],
            "shield": u.get("shield", 0), "alive": u["alive"],
            "boss": bool(u.get("boss")),
            "fx": [k for k in ("burn", "frozen", "stunned", "reflect", "regen",
                               "weaken", "invuln", "intercept_all", "web",
                               "armor_break", "dmg_bonus") if stt.get(k)]}


def public_state(state: dict, battle_id: int) -> dict:
    a, e = state["ally"], state["enemy"]
    hand = []
    for r in state.get("hand", []):
        u = a["units"][r["u"]]
        meta = UNITS[u["uid"]]
        hand.append({"k": r["k"], "emoji": RUNE_EMOJI[r["k"]],
                     "unit_emoji": u["emoji"], "unit_name": u["name"],
                     "unit_i": r["u"], "element": u.get("element"),
                     "forced_crit": bool(r.get("forced_crit")),
                     "label": {"atk": "Удар", "def": "Защита",
                               "skill": meta["skill"]["name"]}[r["k"]],
                     "desc": meta["skill"]["desc"] if r["k"] == "skill" else ""})
    q = state.get("qte") or {}
    pend = state.get("pending") or {}
    return {
        "battle_id": battle_id, "status": state.get("status", "active"),
        "mode": state.get("mode"), "round": state.get("round", 1),
        "ally": {"units": [dict(_pub_unit(u), uid=u["uid"], atk=u["atk"],
                                level=u.get("level", 1),
                                ult_name=UNITS[u["uid"]]["ult"]["name"],
                                ult_desc=UNITS[u["uid"]]["ult"]["desc"])
                           for u in a["units"]],
                 "rage": a["rage"], "focus": a["focus"],
                 "synergy": a.get("synergy", {}),
                 "triad_available": a.get("triad_available", False)},
        "enemy": {"units": [_pub_unit(u) for u in e["units"]],
                  "rage": e["rage"],
                  "intents": e.get("intents", [])},
        "hand": hand, "deck_left": len(state.get("deck", [])),
        "pending": {"type": pend.get("type")} if pend else None,
        "qte": ({"ring_ms": q.get("ring_ms", 1400),
                 "perfect_ms": q.get("perfect_ms", 120),
                 "good_ms": q.get("good_ms", 350)} if q else None),
        "escalation": round(_escalation(state) - 1.0, 2),
        "log": state.get("log", [])[-8:],
        "rage_max": B3_RAGE_MAX,
        "focus_costs": {"reroll": B3_FOCUS_REROLL_COST, "crit": B3_FOCUS_CRIT_COST},
    }


def dumps(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False)


def loads(raw: str) -> dict:
    return json.loads(raw or "{}")


def now() -> float:
    return time.time()
