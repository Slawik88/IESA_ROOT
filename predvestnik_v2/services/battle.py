# services/battle.py — R2: Боёвка 2.0 (Hybrid: Stats + QTE), GDD_REBUILD_PLAN.md.
#
# Пошаговый бой питомца против волн монстров. Server-authoritative:
# состояние боя, статы врага и грейдинг QTE-тайминга живут ТОЛЬКО на сервере —
# клиент шлёт стойку и сырой tap_offset_ms, оценку (perfect/good/miss) считает
# сервер. Используется Вратами 2.0 (mode='gates'), Бездной клана (mode='abyss')
# и Войнами за узлы (mode='war').
import json
import random
import time

from core.constants import (
    COMBAT_BASE_HP, COMBAT_BASE_STAMINA, COMBAT_BASE_ATK, COMBAT_BASE_DEF,
    COMBAT_LEVEL_SCALE,
    BATTLE_QTE_PERFECT_MS, BATTLE_QTE_GOOD_MS, BATTLE_QTE_MULT, BATTLE_BLOCK_EFF,
    BATTLE_STAMINA_COST_FRAC, BATTLE_FOCUS_RESTORE_FRAC,
    BATTLE_ACTION_MIN_INTERVAL_SEC,
)

STANCES = ("attack", "block", "focus")


# ── Статы ─────────────────────────────────────────────────────────────────────

def pet_battle_stats(rarity: str, level: int) -> dict:
    """Паспортные боевые статы питомца (та же база, что CP/старый combat)."""
    level = max(1, min(10, int(level or 1)))
    k = 1.0 + COMBAT_LEVEL_SCALE * (level - 1)
    return {
        "hp_max": int(COMBAT_BASE_HP.get(rarity, 100) * k),
        "st_max": int(COMBAT_BASE_STAMINA.get(rarity, 200) * k),
        "atk": int(COMBAT_BASE_ATK.get(rarity, 10) * k),
        "def": int(COMBAT_BASE_DEF.get(rarity, 5) * k),
    }


def gates_enemy(floor: int, wave: int) -> dict:
    """Монстр Врат 2.0: этаж растит статы, волна внутри этажа — слегка.
    Балансировка: legendary Lv5 уверенно тащит этаж 4–5, common Lv1 — этаж 1."""
    f = max(1, int(floor))
    scale = 1.0 + 0.08 * wave
    return {
        "name": random.choice(["Тень Бездны", "Пожиратель", "Страж Врат", "Мгла"]),
        "emoji": random.choice(["👁", "👹", "🗿", "💀"]),
        "hp_max": int(70 * (f ** 1.3) * scale),
        "atk": int((4 + 5.5 * f) * scale),
        "def": int(2 + 2.5 * f),
    }


def gates_waves(floor: int) -> int:
    return 1 if floor <= 2 else (2 if floor <= 4 else 3)


# ── QTE ───────────────────────────────────────────────────────────────────────

def qte_window(difficulty: int = 1) -> dict:
    """Параметры QTE-кольца: полное время сжатия и окна точности.
    Сложность (этаж) слегка ускоряет кольцо."""
    ring_ms = max(800, 1400 - 80 * (difficulty - 1))
    return {"ring_ms": ring_ms,
            "perfect_ms": BATTLE_QTE_PERFECT_MS,
            "good_ms": BATTLE_QTE_GOOD_MS,
            "issued_at": time.time()}


def grade_tap(state_qte: dict, tap_offset_ms: int, zero_streak: int) -> tuple[str, int]:
    """Серверный грейдинг: offset от идеального момента → perfect/good/miss.
    Анти-чит: 3+ «идеальных нулей» подряд физически невозможны → принудительно
    good; отрицательные/абсурдные значения → miss."""
    try:
        off = abs(int(tap_offset_ms))
    except Exception:
        return "miss", zero_streak
    if off > 5000:
        return "miss", zero_streak
    if off == 0:
        zero_streak += 1
        if zero_streak >= 3:
            return "good", zero_streak
    else:
        zero_streak = 0
    if off <= state_qte.get("perfect_ms", BATTLE_QTE_PERFECT_MS):
        return "perfect", zero_streak
    if off <= state_qte.get("good_ms", BATTLE_QTE_GOOD_MS):
        return "good", zero_streak
    return "miss", zero_streak


# ── Ход боя (чистая логика, без БД) ───────────────────────────────────────────

def resolve_turn(state: dict, stance: str, grade: str) -> dict:
    """Один ход: действие игрока + контр-ход врага. Мутирует state, возвращает
    итог хода для клиента. state: {pet:{hp,st,hp_max,st_max,atk,def},
    enemy:{hp,hp_max,atk,def,...}, wave_idx, waves:[...], floor, log:[]}."""
    pet, enemy = state["pet"], state["enemy"]
    mult = BATTLE_QTE_MULT.get(grade, 0.3)
    events = []

    st_cost = int(pet["st_max"] * BATTLE_STAMINA_COST_FRAC)
    exhausted = pet["st"] < st_cost
    if exhausted and stance != "focus":
        stance = "focus"          # без стамины доступна только Концентрация
        events.append("😮‍💨 Нет выносливости — вынужденная Концентрация")

    dmg_out = 0
    block_frac = 0.0
    if stance == "attack":
        pet["st"] = max(0, pet["st"] - st_cost)
        dmg_out = max(1, int(pet["atk"] * mult - enemy["def"] * 0.5))
        enemy["hp"] = max(0, enemy["hp"] - dmg_out)
        events.append(f"⚔️ Удар ({grade}): −{dmg_out} HP врагу")
    elif stance == "block":
        pet["st"] = max(0, pet["st"] - st_cost)
        block_frac = BATTLE_BLOCK_EFF.get(grade, 0.2)
        events.append(f"🛡 Блок ({grade}): −{int(block_frac * 100)}% входящего")
    else:  # focus
        restore = int(pet["st_max"] * BATTLE_FOCUS_RESTORE_FRAC)
        pet["st"] = min(pet["st_max"], pet["st"] + restore)
        events.append(f"🧘 Концентрация: +{restore} выносливости")

    wave_cleared = battle_won = False
    if enemy["hp"] <= 0:
        state["wave_idx"] += 1
        if state["wave_idx"] >= len(state["waves"]):
            battle_won = True
            events.append("🏆 Все волны зачищены!")
        else:
            wave_cleared = True
            state["enemy"] = dict(state["waves"][state["wave_idx"]])
            state["enemy"]["hp"] = state["enemy"]["hp_max"]
            events.append(f"➡️ Волна {state['wave_idx'] + 1}: {state['enemy']['name']}")
    else:
        # Контр-ход врага (простой ИИ; стены в war не атакуют — atk=0)
        if enemy.get("atk", 0) > 0:
            dmg_in = max(1, int(enemy["atk"] - pet["def"] * 0.5))
            dmg_in = max(1, int(dmg_in * (1.0 - block_frac)))
            pet["hp"] = max(0, pet["hp"] - dmg_in)
            events.append(f"💢 {enemy.get('name', 'Враг')} бьёт: −{dmg_in} HP")

    battle_lost = pet["hp"] <= 0
    if battle_lost:
        events.append("☠️ Питомец пал…")

    state["log"] = (state.get("log", []) + events)[-14:]
    return {"events": events, "dmg_out": dmg_out, "grade": grade,
            "wave_cleared": wave_cleared, "battle_won": battle_won,
            "battle_lost": battle_lost}


def new_gates_battle_state(pet_row: dict, floor: int) -> dict:
    """Начальное состояние боя Врат 2.0 (все волны сгенерены заранее)."""
    stats = pet_battle_stats(pet_row["rarity"], pet_row.get("pet_level", 1))
    waves = [gates_enemy(floor, w) for w in range(gates_waves(floor))]
    enemy = dict(waves[0])
    enemy["hp"] = enemy["hp_max"]
    return {
        "pet": {**stats, "hp": stats["hp_max"], "st": stats["st_max"],
                "name": pet_row.get("name") or pet_row.get("species_id", "Питомец")},
        "waves": waves, "wave_idx": 0, "enemy": enemy,
        "floor": floor, "qte": qte_window(floor), "zero_streak": 0, "log": [],
    }


def public_state(state: dict, battle_id: int, status: str = "active") -> dict:
    """Состояние для клиента: без zero_streak/issued_at-потрохов."""
    q = state.get("qte", {})
    return {
        "battle_id": battle_id, "status": status,
        "pet": state["pet"], "enemy": state["enemy"],
        "wave": state["wave_idx"] + 1, "waves_total": len(state["waves"]),
        "floor": state.get("floor"),
        "qte": {"ring_ms": q.get("ring_ms", 1400),
                "perfect_ms": q.get("perfect_ms", BATTLE_QTE_PERFECT_MS),
                "good_ms": q.get("good_ms", BATTLE_QTE_GOOD_MS)},
        "log": state.get("log", []),
    }


def rate_limited(last_action_ts: float | None) -> bool:
    return bool(last_action_ts) and (time.time() - last_action_ts) < BATTLE_ACTION_MIN_INTERVAL_SEC


def dumps(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False)


def loads(raw: str) -> dict:
    return json.loads(raw or "{}")