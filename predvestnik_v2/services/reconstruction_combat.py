"""Детерминированный server-authoritative движок точного автокликера.

Центр показывает руну, игрок выбирает совпадающую среди трёх перемешанных.
Каждый сигнал одноразовый: спам одной координаты, повтор старого запроса и
высокая частота не дают преимущества. Между волнами выбирается одно усиление.
Время приходит в атомарном ``frame``-действии, поэтому бой реплеится без БД и
wall clock; production-адаптер дополнительно ограничивает частоту запросов.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from core.reconstruction import (
    BALANCE_VERSION,
    CLICKER_UPGRADES,
    ENCOUNTERS,
    GAME_VERSION,
    STARTER_SQUAD,
    STARTER_UNITS,
    validate_content,
)


FRAME_MAX_MS = 500
CHARGE_MAX = 100.0
RUNE_SYMBOLS = ("◇", "△", "○")
RUNE_SLOTS = ("left", "center", "right")
_SLOT_BAGS = (
    (0, 1, 2), (0, 2, 1), (1, 0, 2),
    (1, 2, 0), (2, 0, 1), (2, 1, 0),
)

WAVES: tuple[dict[str, Any], ...] = (
    {
        "id": "echo_shell", "name": "Безымянный отголосок",
        "subtitle": "Услышь знак и найди его отражение", "emoji": "◉",
        "hp": 950.0, "duration_ms": 20000, "signal_ms": 1200,
    },
    {
        "id": "bell_thief", "name": "Похититель звона",
        "subtitle": "Руны меняются быстрее, спам ломает серию", "emoji": "◈",
        "hp": 1400.0, "duration_ms": 24000, "signal_ms": 1050,
    },
    {
        "id": "drowned_archivist", "name": "Архивариус глубин",
        "subtitle": "Последний звон решит исход", "emoji": "♜",
        "hp": 1900.0, "duration_ms": 29000, "signal_ms": 950,
    },
)

REWARD_POOLS: tuple[tuple[str, ...], ...] = (
    ("heavy_echo", "quick_current", "golden_seam"),
    ("deep_discharge", "last_bell", "hungry_pattern"),
)


def _round_number(value: float) -> float:
    return round(float(value), 2)


def _mix(seed: int, sequence: int) -> int:
    value = (int(seed) ^ (sequence * 0x9E3779B1)) & 0xFFFFFFFF
    value ^= value << 13 & 0xFFFFFFFF
    value ^= value >> 17
    value ^= value << 5 & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def _challenge_data(state: dict[str, Any], sequence: int) -> tuple[str, list[dict[str, str]], int]:
    value = _mix(state["seed"] + state["round"] * 977, sequence)
    offset = value % len(RUNE_SYMBOLS)
    symbols = [RUNE_SYMBOLS[(index + offset) % len(RUNE_SYMBOLS)] for index in range(3)]
    # Каждая тройка сигналов использует все три позиции ровно по разу, но в
    # псевдослучайном порядке. Поэтому фиксированная координата математически не
    # может получить удачную серию из-за перекоса seed.
    block = (sequence - 1) // len(RUNE_SLOTS)
    position = (sequence - 1) % len(RUNE_SLOTS)
    bag_value = _mix(state["seed"] + state["round"] * 1597, block + 1)
    correct_index = _SLOT_BAGS[bag_value % len(_SLOT_BAGS)][position]
    target = symbols[correct_index]
    options = [{"slot": slot, "symbol": symbol} for slot, symbol in zip(RUNE_SLOTS, symbols)]
    delay = 430 + (value >> 11) % 330
    return target, options, delay


def _schedule_challenge(state: dict[str, Any], *, first: bool = False) -> None:
    previous = state.get("challenge") or {}
    sequence = int(previous.get("id", 0)) + 1
    target, options, delay = _challenge_data(state, sequence)
    now = int(state["wave"]["elapsed_ms"])
    if first:
        delay = 650
    opens_at = now + delay
    state["challenge"] = {
        "id": sequence,
        "active": False,
        "target_symbol": target,
        "options": options,
        "scheduled_at_ms": now,
        "opens_at_ms": opens_at,
        "expires_at_ms": opens_at + max(
            620,
            int(WAVES[state["round"] - 1]["signal_ms"])
            + int(state["team"]["signal_window_bonus_ms"]),
        ),
    }


def _wave_runtime(
    index: int, round_bonus_ms: int, *, mistake_guard: bool = False
) -> dict[str, Any]:
    meta = WAVES[index]
    return {
        "id": meta["id"], "name": meta["name"], "subtitle": meta["subtitle"],
        "emoji": meta["emoji"], "hp": meta["hp"], "hp_max": meta["hp"],
        "duration_ms": int(meta["duration_ms"]) + int(round_bonus_ms),
        "elapsed_ms": 0,
        "last_stand_used": False,
        "mistake_guard_available": bool(mistake_guard),
    }


def new_encounter(encounter_id: str = "e01_two_bells", *, seed: int = 1) -> dict[str, Any]:
    errors = validate_content()
    if errors:
        raise ValueError("Некорректный реестр Reconstruction 3.0: " + "; ".join(errors))
    encounter = ENCOUNTERS.get(encounter_id)
    if not encounter:
        raise ValueError(f"Неизвестная встреча: {encounter_id}")
    if not encounter.get("implemented"):
        raise ValueError(f"Встреча {encounter_id} ещё не включена в игровой срез.")
    team: dict[str, Any] = {
        "tap_power": 65.0,
        "auto_dps": 3.0,
        "charge": 0.0,
        "charge_max": CHARGE_MAX,
        "charge_per_hit": 25.0,
        "overdrive_power": 120.0,
        "critical_multiplier": 1.55,
        "critical_window_ms": 300,
        "signal_window_bonus_ms": 0,
        "combo_step_multiplier": 1.0,
        "round_bonus_ms": 0,
        "wrong_heal_bonus": 0,
        "reset_charge_on_wrong": False,
        "mistake_guard": False,
        "units": [
            {
                "id": unit_id, "name": STARTER_UNITS[unit_id]["short_name"],
                "emoji": STARTER_UNITS[unit_id]["emoji"], "role": STARTER_UNITS[unit_id]["role"],
            }
            for unit_id in STARTER_SQUAD
        ],
    }
    state: dict[str, Any] = {
        "game_version": GAME_VERSION,
        "balance_version": BALANCE_VERSION,
        "encounter_id": encounter_id,
        "seed": int(seed),
        "round": 1,
        "status": "active",
        "outcome_reason": None,
        "wave": _wave_runtime(0, 0),
        "team": team,
        "combo": {"count": 0, "max": 0},
        "challenge": None,
        "seam_ready": False,
        "upgrades": [],
        "reward_options": [],
        "mastery": {
            "total_taps": 0, "correct_taps": 0, "mistakes": 0, "missed_signals": 0,
            "critical_taps": 0, "discharges": 0, "seam_hits": 0,
            "damage_taps": 0.0, "damage_auto": 0.0, "damage_discharge": 0.0,
            "elapsed_ms": 0,
        },
        "last_event": {"kind": "start", "label": "Слушай первый сигнал"},
        "event_seq": 0,
        "log": ["🔔 Центр показывает знак. Нажми такую же руну вокруг него."],
    }
    _schedule_challenge(state, first=True)
    return state


def _emit(state: dict[str, Any], kind: str, label: str, **payload: Any) -> None:
    state["event_seq"] += 1
    state["last_event"] = {"id": state["event_seq"], "kind": kind, "label": label, **payload}


def _deal(state: dict[str, Any], amount: float, source: str) -> float:
    if state["status"] != "active" or amount <= 0:
        return 0.0
    wave = state["wave"]
    dealt = min(float(wave["hp"]), float(amount))
    wave["hp"] = _round_number(max(0.0, float(wave["hp"]) - dealt))
    metric = {"tap": "damage_taps", "auto": "damage_auto", "discharge": "damage_discharge"}.get(source)
    if metric:
        state["mastery"][metric] = _round_number(state["mastery"][metric] + dealt)
    if wave["hp"] <= 0:
        _complete_wave(state)
    return dealt


def _complete_wave(state: dict[str, Any]) -> None:
    state["log"].append(f"✦ {state['wave']['name']} рассыпается. Волна {state['round']} пройдена.")
    state["challenge"] = None
    if state["round"] >= len(WAVES):
        state["status"] = "won"
        state["outcome_reason"] = "all_echoes_broken"
        _emit(state, "victory", "Колокол отвечает тебе")
        return
    state["reward_options"] = [
        {"id": upgrade_id, **copy.deepcopy(CLICKER_UPGRADES[upgrade_id])}
        for upgrade_id in REWARD_POOLS[state["round"] - 1]
    ]
    state["status"] = "reward"
    _emit(state, "wave_complete", "Выбери усиление", wave=state["round"])


def _start_next_wave(state: dict[str, Any]) -> None:
    state["round"] += 1
    state["status"] = "active"
    state["wave"] = _wave_runtime(
        state["round"] - 1,
        state["team"]["round_bonus_ms"],
        mistake_guard=state["team"]["mistake_guard"],
    )
    state["reward_options"] = []
    state["seam_ready"] = False
    state["combo"] = {"count": 0, "max": state["combo"]["max"]}
    state["challenge"] = None
    _schedule_challenge(state, first=True)
    state["log"].append(f"⚔️ Волна {state['round']}: {state['wave']['name']}.")
    _emit(state, "wave_start", state["wave"]["name"], wave=state["round"])


def _critical_active(state: dict[str, Any]) -> bool:
    challenge = state.get("challenge")
    if not challenge or not challenge["active"]:
        return False
    remaining = int(challenge["expires_at_ms"]) - int(state["wave"]["elapsed_ms"])
    return 0 <= remaining <= int(state["team"]["critical_window_ms"])


def _combo_multiplier(state: dict[str, Any]) -> float:
    steps = min(max(0, int(state["combo"]["count"]) - 1), 20)
    return 1.0 + steps * 0.04 * float(state["team"]["combo_step_multiplier"])


def _miss_signal(state: dict[str, Any], *, wrong_tap: bool) -> None:
    guarded = False
    if wrong_tap:
        state["mastery"]["mistakes"] += 1
        state["mastery"]["total_taps"] += 1
        guarded = bool(state["wave"].get("mistake_guard_available"))
        if guarded:
            state["wave"]["mistake_guard_available"] = False
            label = "КЛЯТВА УДЕРЖАЛА УДАР"
            state["team"]["charge"] = _round_number(float(state["team"]["charge"]) * 0.5)
            state["log"].append("◌ Клятва поглотила лечение цели и сохранила половину заряда.")
        else:
            label = "НЕ ТА РУНА"
            restored = 35 + state["round"] * 5 + int(state["team"]["wrong_heal_bonus"])
            state["wave"]["hp"] = min(
                state["wave"]["hp_max"], _round_number(state["wave"]["hp"] + restored)
            )
            state["log"].append(f"× Неверная руна: серия оборвалась, цель вернула {restored} HP.")
            if state["team"]["reset_charge_on_wrong"]:
                state["team"]["charge"] = 0.0
    else:
        state["mastery"]["missed_signals"] += 1
        label = "СИГНАЛ УШЁЛ"
    state["combo"]["count"] = 0
    if not guarded and not (wrong_tap and state["team"]["reset_charge_on_wrong"]):
        state["team"]["charge"] = max(0.0, float(state["team"]["charge"]) - 10.0)
    _emit(state, "miss", label)
    _schedule_challenge(state)


def _advance_time(state: dict[str, Any], delta_ms: int) -> None:
    if delta_ms <= 0 or state["status"] != "active":
        return
    wave = state["wave"]
    wave["elapsed_ms"] += delta_ms
    state["mastery"]["elapsed_ms"] += delta_ms
    _deal(state, state["team"]["auto_dps"] * delta_ms / 1000.0, "auto")
    if state["status"] != "active":
        return
    challenge = state["challenge"]
    if challenge and not challenge["active"] and wave["elapsed_ms"] >= challenge["opens_at_ms"]:
        challenge["active"] = True
        _emit(state, "signal", f"Найди {challenge['target_symbol']}", challenge_id=challenge["id"])
    if challenge and challenge["active"] and wave["elapsed_ms"] >= challenge["expires_at_ms"]:
        _miss_signal(state, wrong_tap=False)
    if wave["elapsed_ms"] < wave["duration_ms"]:
        return
    hp_ratio = float(wave["hp"]) / float(wave["hp_max"])
    if hp_ratio <= 0.12 and not wave["last_stand_used"]:
        wave["last_stand_used"] = True
        wave["duration_ms"] += 3000
        state["log"].append("⏳ Последний звон: ещё 3 секунды — цель почти разбита!")
        _emit(state, "last_stand", "Ещё 3 секунды")
        return
    state["status"] = "lost"
    state["outcome_reason"] = "echo_faded"
    state["challenge"] = None
    _emit(state, "defeat", "Эхо погасло")


def _discharge(state: dict[str, Any]) -> float:
    state["team"]["charge"] -= CHARGE_MAX
    damage = float(state["team"]["overdrive_power"])
    if state["seam_ready"]:
        damage += 35.0
        state["seam_ready"] = False
        state["mastery"]["seam_hits"] += 1
    dealt = _deal(state, damage, "discharge")
    state["mastery"]["discharges"] += 1
    state["log"].append(f"⚡ Разряд пробивает цель на {int(round(dealt))}.")
    _emit(state, "discharge", "РАЗРЯД", damage=int(round(dealt)))
    return dealt


def _strike(state: dict[str, Any], challenge_id: int, slot: str) -> dict[str, Any]:
    challenge = state.get("challenge")
    if not challenge or not challenge["active"]:
        return {"accepted": False, "correct": False, "reason": "no_active_signal"}
    if int(challenge_id) != int(challenge["id"]):
        return {"accepted": False, "correct": False, "reason": "stale_signal"}
    option = next((item for item in challenge["options"] if item["slot"] == slot), None)
    if not option:
        return {"accepted": False, "correct": False, "reason": "unknown_slot"}
    correct = option["symbol"] == challenge["target_symbol"]
    if not correct:
        _miss_signal(state, wrong_tap=True)
        return {"accepted": True, "correct": False, "reason": "wrong_rune"}

    state["mastery"]["total_taps"] += 1
    state["mastery"]["correct_taps"] += 1
    state["combo"]["count"] += 1
    state["combo"]["max"] = max(state["combo"]["max"], state["combo"]["count"])
    critical = _critical_active(state)
    multiplier = _combo_multiplier(state)
    if critical:
        multiplier *= float(state["team"]["critical_multiplier"])
        state["mastery"]["critical_taps"] += 1
        state["seam_ready"] = True
    damage = float(state["team"]["tap_power"]) * multiplier
    if state["combo"]["count"] % 5 == 0:
        damage += float(state["team"]["tap_power"]) * 0.75
    dealt = _deal(state, damage, "tap")
    state["team"]["charge"] = min(
        CHARGE_MAX * 2 - 0.01,
        state["team"]["charge"] + float(state["team"]["charge_per_hit"]),
    )
    discharged = False
    if state["status"] == "active" and state["team"]["charge"] >= CHARGE_MAX:
        _discharge(state)
        discharged = True
    if state["status"] == "active":
        if not discharged:
            _emit(
                state, "critical" if critical else "hit", "ТОЧНО" if not critical else "ЗОЛОТОЙ УДАР",
                damage=int(round(dealt)), combo=state["combo"]["count"],
            )
        _schedule_challenge(state)
    return {
        "accepted": True, "correct": True, "critical": critical,
        "damage": _round_number(dealt), "discharged": discharged,
    }


def _choose_upgrade(state: dict[str, Any], upgrade_id: str) -> dict[str, Any]:
    if state["status"] != "reward":
        return {"ok": False, "error": "Сейчас нельзя выбирать усиление."}
    if upgrade_id not in {option["id"] for option in state["reward_options"]}:
        return {"ok": False, "error": "Это усиление не предложено после текущей волны."}
    upgrade = CLICKER_UPGRADES[upgrade_id]
    effect = upgrade["effect"]
    team = state["team"]
    for key in (
        "tap_power", "charge_per_hit", "critical_window_ms", "critical_multiplier",
        "overdrive_power", "round_bonus_ms", "signal_window_ms", "wrong_heal_bonus",
    ):
        if key not in effect:
            continue
        target_key = "signal_window_bonus_ms" if key == "signal_window_ms" else key
        team[target_key] += effect[key]
    if "auto_dps_multiplier" in effect:
        team["auto_dps"] = _round_number(team["auto_dps"] * effect["auto_dps_multiplier"])
    if "combo_step_multiplier" in effect:
        team["combo_step_multiplier"] *= effect["combo_step_multiplier"]
    if effect.get("mistake_guard"):
        team["mistake_guard"] = True
    if effect.get("reset_charge_on_wrong"):
        team["reset_charge_on_wrong"] = True
    state["upgrades"].append(upgrade_id)
    state["log"].append(f"{upgrade['emoji']} Получено усиление «{upgrade['name']}».")
    _start_next_wave(state)
    return {"ok": True, "phase": "wave_started", "upgrade_id": upgrade_id}


def apply_action(state: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {"ok": False, "error": "Действие должно быть объектом."}
    action_type = str(action.get("type") or "")
    if action_type == "choose_upgrade":
        return _choose_upgrade(state, str(action.get("upgrade_id") or ""))
    if state["status"] != "active":
        return {"ok": False, "error": "Раунд сейчас не активен."}
    if action_type not in {"frame", "strike"}:
        return {"ok": False, "error": "Неизвестное действие точного автокликера."}
    try:
        delta_ms = int(action.get("delta_ms", 0 if action_type == "strike" else 100))
    except (TypeError, ValueError):
        return {"ok": False, "error": "delta_ms должен быть целым числом."}
    if delta_ms < 0:
        return {"ok": False, "error": "Время кадра не может быть отрицательным."}

    applied_delta = min(delta_ms, FRAME_MAX_MS)
    # Elapsed time is resolved before an optional tap.  Otherwise a client could
    # wait past the visible signal window and still have the stale tap judged
    # against the pre-request state.
    if state["status"] == "active":
        _advance_time(state, applied_delta)

    strike_result = None
    slot = action.get("target_slot")
    if slot is not None:
        try:
            challenge_id = int(action.get("challenge_id"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "challenge_id обязателен для нажатия."}
        strike_result = _strike(state, challenge_id, str(slot))
    return {
        "ok": True, "phase": state["status"], "delta_ms": applied_delta,
        "strike": strike_result,
    }


def public_state(state: dict[str, Any]) -> dict[str, Any]:
    view = copy.deepcopy(state)
    # Wall-clock internals are persistence metadata, not part of the client
    # authority contract.  The per-turn response exposes only bounded timing.
    view.pop("_server_clock", None)
    wave = view["wave"]
    wave["time_left_ms"] = max(0, int(wave["duration_ms"]) - int(wave["elapsed_ms"]))
    challenge = view.get("challenge")
    if challenge:
        elapsed = int(wave["elapsed_ms"])
        if challenge["active"]:
            duration = max(1, challenge["expires_at_ms"] - challenge["opens_at_ms"])
            view["signal_progress"] = min(1.0, max(0.0, (elapsed - challenge["opens_at_ms"]) / duration))
        else:
            duration = max(1, challenge["opens_at_ms"] - challenge["scheduled_at_ms"])
            view["signal_progress"] = min(1.0, max(0.0, (elapsed - challenge["scheduled_at_ms"]) / duration))
            challenge["target_symbol"] = None
            challenge["options"] = []
    else:
        view["signal_progress"] = 0.0
    view["critical_active"] = _critical_active(state) if state["status"] == "active" else False
    view["waves_total"] = len(WAVES)
    correct = int(view["mastery"]["correct_taps"])
    wrong = int(view["mastery"]["mistakes"])
    missed = int(view["mastery"]["missed_signals"])
    resolved_signals = correct + wrong + missed
    physical_taps = int(view["mastery"]["total_taps"])
    view["signals_resolved"] = resolved_signals
    view["accuracy"] = round(correct / resolved_signals * 100, 1) if resolved_signals else None
    view["tap_accuracy"] = round(correct / physical_taps * 100, 1) if physical_taps else None
    return view


def dumps(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads(payload: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        return copy.deepcopy(payload)
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("Состояние боя должно быть JSON-объектом.")
    return value
