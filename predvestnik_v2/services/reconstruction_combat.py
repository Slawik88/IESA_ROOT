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
from core.reconstruction_progression import branch_by_id
from core.companions_v3 import COMPANION_ROLES


FRAME_MAX_MS = 500
CHARGE_MAX = 100.0
RUNE_SYMBOLS = ("◇", "△", "○")
RUNE_SLOTS = ("left", "center", "right")
_SLOT_BAGS = (
    (0, 1, 2), (0, 2, 1), (1, 0, 2),
    (1, 2, 0), (2, 0, 1), (2, 1, 0),
)

E01_WAVES: tuple[dict[str, Any], ...] = (
    {
        "id": "echo_shell", "name": "Безымянный отголосок",
        "subtitle": "Услышь знак и найди его отражение", "emoji": "◉",
        "hp": 950.0, "duration_ms": 20000, "signal_ms": 1200, "rail": "Эхо",
    },
    {
        "id": "bell_thief", "name": "Похититель звона",
        "subtitle": "Руны меняются быстрее, спам ломает серию", "emoji": "◈",
        "hp": 1400.0, "duration_ms": 24000, "signal_ms": 1050, "rail": "Похититель",
    },
    {
        "id": "drowned_archivist", "name": "Архивариус глубин",
        "subtitle": "Последний звон решит исход", "emoji": "♜",
        "hp": 1900.0, "duration_ms": 29000, "signal_ms": 950, "rail": "Архивариус",
    },
)

E02_WAVES: tuple[dict[str, Any], ...] = (
    {
        "id": "lantern_wake", "name": "След фонаря",
        "subtitle": "Ошибки гасят свет, чистая серия возвращает его", "emoji": "◌",
        "hp": 1450.0, "duration_ms": 30000, "signal_ms": 1150, "rail": "Фонарь",
    },
    {
        "id": "split_causeway", "name": "Расколотый пролёт",
        "subtitle": "Сохрани точность, когда течение ускорится", "emoji": "⌁",
        "hp": 1900.0, "duration_ms": 36000, "signal_ms": 980, "rail": "Пролёт",
    },
    {
        "id": "toll_gate", "name": "Затонувшие ворота",
        "subtitle": "Последняя длинная серия решает судьбу Фонаря", "emoji": "◇",
        "hp": 2450.0, "duration_ms": 42000, "signal_ms": 880, "rail": "Ворота",
    },
)

E03_INK_WAVES: tuple[dict[str, Any], ...] = (
    {
        "id": "ink_reflection", "name": "Чернильное отражение",
        "subtitle": "Отражение приходит раньше настоящего знака", "emoji": "◆",
        "hp": 1650.0, "duration_ms": 34000, "signal_ms": 1100, "rail": "Отражение",
    },
    {
        "id": "ink_mask", "name": "Маска переписчика",
        "subtitle": "Не отвечай на первый увиденный символ", "emoji": "◐",
        "hp": 2200.0, "duration_ms": 40000, "signal_ms": 980, "rail": "Маска",
    },
    {
        "id": "ink_archive", "name": "Архив ложных имён",
        "subtitle": "Читай открытый сигнал, а не его предвестник", "emoji": "▣",
        "hp": 2900.0, "duration_ms": 46000, "signal_ms": 850, "rail": "Архив",
    },
)

E03_ASH_WAVES: tuple[dict[str, Any], ...] = (
    {
        "id": "ash_ember", "name": "Остывающий уголь",
        "subtitle": "Точный темп поддерживает огонь", "emoji": "·",
        "hp": 1550.0, "duration_ms": 32000, "signal_ms": 1050, "rail": "Уголь",
    },
    {
        "id": "ash_wind", "name": "Пепельный ветер",
        "subtitle": "Поздний золотой ответ возвращает больше жара", "emoji": "≈",
        "hp": 2100.0, "duration_ms": 38000, "signal_ms": 900, "rail": "Ветер",
    },
    {
        "id": "ash_keeper", "name": "Хранитель костра",
        "subtitle": "Удержи огонь, не превращая риск в угадывание", "emoji": "△",
        "hp": 2850.0, "duration_ms": 45000, "signal_ms": 780, "rail": "Костёр",
    },
)

E04_WAVES: tuple[dict[str, Any], ...] = (
    {
        "id": "name_anchor", "name": "Якорь без имени",
        "subtitle": "Запомни два знака и повтори их без подсказки", "emoji": "⌁",
        "hp": 1500.0, "duration_ms": 28000, "signal_ms": 1450, "rail": "Имя",
    },
    {
        "id": "debt_anchor", "name": "Якорь старого долга",
        "subtitle": "Три знака: порядок важнее скорости", "emoji": "⟁",
        "hp": 2100.0, "duration_ms": 35000, "signal_ms": 1300, "rail": "Долг",
    },
    {
        "id": "choir_anchor", "name": "Якорь утонувшего хора",
        "subtitle": "Последняя цепочка не простит слепого клика", "emoji": "♢",
        "hp": 2850.0, "duration_ms": 42000, "signal_ms": 1150, "rail": "Хор",
    },
)

E05_WAVES: tuple[dict[str, Any], ...] = (
    {
        "id": "first_mirror", "name": "Зеркало первого шага",
        "subtitle": "Выбранная позиция станет запретной для следующего знака", "emoji": "◫",
        "hp": 1700.0, "duration_ms": 30000, "signal_ms": 1350, "rail": "Шаг",
    },
    {
        "id": "copyist_mirror", "name": "Зеркало Переписчика",
        "subtitle": "Следи за знаком и не возвращайся в отмеченную ячейку", "emoji": "▱",
        "hp": 2350.0, "duration_ms": 37000, "signal_ms": 1150, "rail": "Переписчик",
    },
    {
        "id": "courtyard_mirror", "name": "Сердце Зеркального двора",
        "subtitle": "Последняя печать проверяет выбор, а не скорость", "emoji": "▣",
        "hp": 3150.0, "duration_ms": 45000, "signal_ms": 980, "rail": "Двор",
    },
)

E06_WAVES: tuple[dict[str, Any], ...] = (
    {
        "id": "archivist_record", "name": "Фаза I · Запись",
        "subtitle": "Архивариус запоминает прошлую позицию", "emoji": "⌑",
        "hp": 2100.0, "duration_ms": 34000, "signal_ms": 1300, "rail": "Запись",
    },
    {
        "id": "archivist_tide", "name": "Фаза II · Прилив",
        "subtitle": "Короткие и длинные окна объявляются заранее", "emoji": "≈",
        "hp": 2850.0, "duration_ms": 43000, "signal_ms": 1100, "rail": "Прилив",
    },
    {
        "id": "archivist_name", "name": "Фаза III · Последнее имя",
        "subtitle": "Запомни две руны и верни имя в правильном порядке", "emoji": "◉",
        "hp": 3800.0, "duration_ms": 50000, "signal_ms": 1050, "rail": "Имя",
    },
)

ENCOUNTER_WAVES: dict[str, tuple[dict[str, Any], ...]] = {
    "e01_two_bells": E01_WAVES,
    "e02_shattered_causeway": E02_WAVES,
    "e03_ink_path": E03_INK_WAVES,
    "e03_ash_path": E03_ASH_WAVES,
    "e04_drowned_names": E04_WAVES,
    "e05_mirror_courtyard": E05_WAVES,
    "e06_archivist": E06_WAVES,
}

SEQUENCE_LENGTHS = tuple(ENCOUNTERS["e04_drowned_names"]["objective"]["sequence_lengths"])
SEQUENCE_PREVIEW_MS = 650
SEQUENCE_RECALL_DELAY_MS = 350


def _waves(state: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    try:
        return ENCOUNTER_WAVES[state["encounter_id"]]
    except KeyError as exc:
        raise ValueError("Для встречи не задан проверенный набор волн.") from exc

REWARD_POOLS: tuple[tuple[str, ...], ...] = (
    ("heavy_echo", "quick_current", "golden_seam"),
    ("deep_discharge", "last_bell", "hungry_pattern"),
)


def _round_number(value: float) -> float:
    return round(float(value), 2)


def _branch_state(state: dict[str, Any]) -> dict[str, Any]:
    branch = state.setdefault("branch_state", {})
    defaults = {
        "decision": None, "broken_vow_used": False, "manual_discharge": None,
        "stored_seam_slot": None, "forbidden_mode": False,
        "forbidden_slot": None, "tide_swap_used": False,
        "hide_signal_timer": False, "family_preview": None,
        "next_signal_penalty_ms": 0,
    }
    for key, value in defaults.items():
        branch.setdefault(key, value)
    return branch


def _has_branch(state: dict[str, Any], branch_id: str) -> bool:
    return any(
        branch_id in (value if isinstance(value, list) else [value])
        for value in (state.get("unit_branches") or {}).values()
    )


def _has_companion_role(state: dict[str, Any], role_id: str) -> bool:
    return state.get("companion_role_id") == role_id


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


def _forced_challenge_data(
    state: dict[str, Any], sequence: int, target: str
) -> tuple[str, list[dict[str, str]], int]:
    """Place a remembered target into the same balanced slot schedule."""
    generated_target, generated, delay = _challenge_data(state, sequence)
    generated_target_index = next(
        index for index, option in enumerate(generated)
        if option["symbol"] == generated_target
    )
    remaining = [symbol for symbol in RUNE_SYMBOLS if symbol != target]
    if _mix(state["seed"] + 811, sequence) % 2:
        remaining.reverse()
    symbols = list(remaining)
    symbols.insert(generated_target_index, target)
    return target, [
        {"slot": slot, "symbol": symbol}
        for slot, symbol in zip(RUNE_SLOTS, symbols)
    ], delay


def _is_sequence_objective(objective: dict[str, Any]) -> bool:
    return bool(
        objective.get("kind") == "drowned_sequence"
        or (
            objective.get("kind") == "archivist_boss"
            and objective.get("phase") in {"preview", "recall"}
        )
    )


def _sequence_for_wave(state: dict[str, Any]) -> list[str]:
    objective = state.get("objective_state") or {}
    length = 2 if objective.get("kind") == "archivist_boss" else SEQUENCE_LENGTHS[int(state["round"]) - 1]
    result: list[str] = []
    for index in range(length):
        value = _mix(state["seed"] + int(state["round"]) * 4099, index + 1)
        symbol = RUNE_SYMBOLS[value % len(RUNE_SYMBOLS)]
        if result and symbol == result[-1]:
            symbol = RUNE_SYMBOLS[(RUNE_SYMBOLS.index(symbol) + 1 + value % 2) % len(RUNE_SYMBOLS)]
        result.append(symbol)
    return result


def _begin_sequence_preview(state: dict[str, Any], *, replay: bool = False) -> None:
    objective = state["objective_state"]
    if not replay:
        objective["sequence"] = _sequence_for_wave(state)
    objective.update({
        "phase": "preview",
        "preview_started_at_ms": int(state["wave"]["elapsed_ms"]) + (300 if replay else 0),
        "preview_index": -1,
        "preview_symbol": None,
        "answer_index": 0,
        "sequence_length": len(objective["sequence"]),
    })
    state["challenge"] = None


def _begin_archivist_phase(state: dict[str, Any]) -> None:
    objective = state["objective_state"]
    if int(state["round"]) == 1:
        objective.update({
            "phase": "record", "recorded_slot": None, "tide_window": None,
        })
        _schedule_challenge(state, first=True)
    elif int(state["round"]) == 2:
        objective.update({
            "phase": "tide", "recorded_slot": None, "tide_window": "long",
        })
        _schedule_challenge(state, first=True)
    else:
        objective.update({"phase": "last_name", "attempts_left": 3, "attempts_max": 3})
        _begin_sequence_preview(state)


def _schedule_challenge(state: dict[str, Any], *, first: bool = False) -> None:
    previous_id = int((state.get("challenge") or {}).get("id", 0))
    sequence = max(int(state.get("challenge_seq", 0)), previous_id) + 1
    state["challenge_seq"] = sequence
    objective = state.get("objective_state") or {}
    if _is_sequence_objective(objective):
        target = objective["sequence"][int(objective["answer_index"])]
        target, options, delay = _forced_challenge_data(state, sequence, target)
    else:
        target, options, delay = _challenge_data(state, sequence)
    blocked_slot = (
        objective.get("forbidden_slot")
        if objective.get("kind") == "mirror_rule"
        else objective.get("recorded_slot")
        if objective.get("kind") == "archivist_boss" and objective.get("phase") == "record"
        else None
    )
    if blocked_slot:
        correct_index = next(
            index for index, option in enumerate(options)
            if option["symbol"] == target
        )
        forbidden_index = RUNE_SLOTS.index(str(blocked_slot))
        if correct_index == forbidden_index:
            swap_index = (forbidden_index + 1 + _mix(state["seed"] + 1771, sequence) % 2) % 3
            options[correct_index]["symbol"], options[swap_index]["symbol"] = (
                options[swap_index]["symbol"], options[correct_index]["symbol"],
            )
    now = int(state["wave"]["elapsed_ms"])
    if first:
        delay = 420 if _is_sequence_objective(objective) else 650
    opens_at = now + delay
    branch = _branch_state(state)
    penalty_ms = max(0, int(branch.get("next_signal_penalty_ms", 0)))
    state["challenge"] = {
        "id": sequence,
        "active": False,
        "target_symbol": target,
        "options": options,
        "scheduled_at_ms": now,
        "opens_at_ms": opens_at,
        "expires_at_ms": opens_at + max(
            620,
            int(_waves(state)[state["round"] - 1]["signal_ms"])
            + int(state["team"]["signal_window_bonus_ms"])
            - penalty_ms,
        ),
    }
    if objective.get("kind") == "archivist_boss" and objective.get("phase") == "tide":
        tide_window = "short" if sequence % 2 else "long"
        window_ms = 760 if tide_window == "short" else 1580
        state["challenge"]["expires_at_ms"] = opens_at + max(
            620, window_ms + int(state["team"]["signal_window_bonus_ms"])
        )
        objective["tide_window"] = tide_window
    if _has_companion_role(state, "lantern"):
        decoys = [
            option for option in state["challenge"]["options"]
            if option["symbol"] != target and option["slot"] != blocked_slot
        ]
        if decoys:
            marked = decoys[_mix(state["seed"] + 2707, sequence) % len(decoys)]
            marked["companion_hint"] = "decoy"
            state["companion_state"]["lantern_marks"] = int(
                state["companion_state"].get("lantern_marks", 0)
            ) + 1
    branch["next_signal_penalty_ms"] = 0
    branch["hide_signal_timer"] = False
    branch["family_preview"] = None
    if objective.get("kind") == "ink_decipher":
        objective["reflection_cue"] = None


def _wave_runtime(
    state: dict[str, Any], index: int, round_bonus_ms: int, *, mistake_guard: bool = False
) -> dict[str, Any]:
    meta = _waves(state)[index]
    return {
        "id": meta["id"], "name": meta["name"], "subtitle": meta["subtitle"],
        "emoji": meta["emoji"], "hp": meta["hp"], "hp_max": meta["hp"],
        "duration_ms": int(meta["duration_ms"]) + int(round_bonus_ms),
        "elapsed_ms": 0,
        "last_stand_used": False,
        "mistake_guard_available": bool(mistake_guard),
    }


def new_encounter(
    encounter_id: str = "e01_two_bells",
    *,
    seed: int = 1,
    unit_branches: dict[str, str | list[str]] | None = None,
    companion_role_id: str | None = None,
) -> dict[str, Any]:
    errors = validate_content()
    if errors:
        raise ValueError("Некорректный реестр Reconstruction 3.0: " + "; ".join(errors))
    encounter = ENCOUNTERS.get(encounter_id)
    if not encounter:
        raise ValueError(f"Неизвестная встреча: {encounter_id}")
    if not encounter.get("implemented"):
        raise ValueError(f"Встреча {encounter_id} ещё не включена в игровой срез.")
    if companion_role_id is not None:
        role = COMPANION_ROLES.get(str(companion_role_id))
        if not role or not role.get("implemented"):
            raise ValueError("Роль спутника ещё не поддерживается боевым движком.")
        companion_role_id = str(companion_role_id)
    selected_branches: dict[str, list[str]] = {}
    for unit_id, raw_branch_ids in (unit_branches or {}).items():
        branch_ids = raw_branch_ids if isinstance(raw_branch_ids, list) else [raw_branch_ids]
        normalized: list[str] = []
        for branch_id in branch_ids:
            found = branch_by_id(str(branch_id))
            if not found or found[0] != unit_id:
                raise ValueError("Ветка мастерства не принадлежит выбранному юниту.")
            normalized.append(str(branch_id))
        selected_branches[str(unit_id)] = list(dict.fromkeys(normalized))
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
        "wave": {},
        "team": team,
        "combo": {"count": 0, "max": 0},
        "challenge": None,
        "challenge_seq": 0,
        "seam_ready": False,
        "unit_branches": selected_branches,
        "companion_role_id": companion_role_id,
        "companion_state": {
            "lantern_marks": 0,
            "guardian_used_rounds": [],
            "guardian_active_challenge": None,
        },
        "branch_state": {
            "decision": None,
            "broken_vow_used": False,
            "manual_discharge": None,
            "stored_seam_slot": None,
            "forbidden_mode": False,
            "forbidden_slot": None,
            "tide_swap_used": False,
            "hide_signal_timer": False,
            "family_preview": None,
        },
        "upgrades": [],
        "reward_options": [],
        "mastery": {
            "total_taps": 0, "correct_taps": 0, "mistakes": 0, "missed_signals": 0,
            "critical_taps": 0, "discharges": 0, "seam_hits": 0,
            "reaction_total_ms": 0, "reaction_count": 0,
            "max_combo_after_mistake": 0,
            "damage_taps": 0.0, "damage_auto": 0.0, "damage_discharge": 0.0,
            "elapsed_ms": 0,
        },
        "last_event": {"kind": "start", "label": "Слушай первый сигнал"},
        "event_seq": 0,
        "log": ["🔔 Центр показывает знак. Нажми такую же руну вокруг него."],
    }
    if encounter_id == "e02_shattered_causeway":
        state["objective_state"] = {
            "kind": "lantern_escort",
            "lantern_integrity": 100,
            "lantern_integrity_max": 100,
            "minimum_accuracy": 75,
            "recoveries": 0,
        }
        state["log"] = [
            "🏮 Фонарь гаснет от ошибок. Каждые пять точных знаков подряд возвращают свет."
        ]
    elif encounter_id == "e03_ink_path":
        state["objective_state"] = {
            "kind": "ink_decipher",
            "clarity": 100,
            "clarity_max": 100,
            "reflection_cue": None,
        }
        state["log"] = [
            "◆ Отражение показывается раньше. Нажимай только после открытия настоящего сигнала."
        ]
    elif encounter_id == "e03_ash_path":
        state["objective_state"] = {
            "kind": "ash_fire",
            "fire_integrity": 100,
            "fire_integrity_max": 100,
            "decay_ticks": 0,
            "golden_recoveries": 0,
        }
        state["log"] = [
            "🔥 Огонь медленно гаснет. Точные знаки поддерживают его, золотые возвращают больше."
        ]
    elif encounter_id == "e04_drowned_names":
        state["objective_state"] = {
            "kind": "drowned_sequence",
            "anchors_broken": 0,
            "anchors_total": 3,
            "attempts_left": 3,
            "attempts_max": 3,
            "replays": 0,
            "sequence": [],
        }
        state["log"] = [
            "⌁ Запомни цепочку, затем повтори её по порядку. Во время ответа подсказки исчезнут."
        ]
    elif encounter_id == "e05_mirror_courtyard":
        state["objective_state"] = {
            "kind": "mirror_rule",
            "forbidden_slot": None,
            "wards": 3,
            "wards_max": 3,
            "repeat_violations": 0,
        }
        state["log"] = [
            "◫ После точного ответа выбранная позиция закрывается до следующего знака."
        ]
    elif encounter_id == "e06_archivist":
        state["objective_state"] = {
            "kind": "archivist_boss",
            "phase": "record",
            "phases_completed": 0,
            "phases_total": 3,
            "recorded_slot": None,
            "tide_window": None,
            "sequence_replays": 0,
        }
        state["log"] = [
            "⌑ Архивариус меняет правило после каждой фазы. Сначала он записывает выбранную позицию."
        ]
    state["wave"] = _wave_runtime(state, 0, 0)
    if encounter_id == "e04_drowned_names":
        _begin_sequence_preview(state)
    elif encounter_id == "e06_archivist":
        _begin_archivist_phase(state)
    else:
        _schedule_challenge(state, first=True)
    return state


def _emit(state: dict[str, Any], kind: str, label: str, **payload: Any) -> None:
    state["event_seq"] += 1
    state["last_event"] = {"id": state["event_seq"], "kind": kind, "label": label, **payload}


def _deal(state: dict[str, Any], amount: float, source: str) -> float:
    if state["status"] != "active" or amount <= 0:
        return 0.0
    wave = state["wave"]
    objective = state.get("objective_state") or {}
    if (
        _is_sequence_objective(objective)
        and int(objective.get("answer_index", 0)) < int(objective.get("sequence_length", 1))
    ):
        # Отряд помогает, но не может разорвать якорь вместо правильного ответа.
        amount = min(float(amount), max(0.0, float(wave["hp"]) - 1.0))
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
    objective = state.get("objective_state") or {}
    if objective.get("kind") == "archivist_boss":
        objective["phases_completed"] = max(
            int(objective.get("phases_completed", 0)), int(state["round"])
        )
    if state["round"] >= len(_waves(state)):
        correct = int(state["mastery"]["correct_taps"])
        resolved = correct + int(state["mastery"]["mistakes"]) + int(
            state["mastery"]["missed_signals"]
        )
        accuracy = correct / resolved * 100 if resolved else 0
        if (
            objective.get("kind") == "lantern_escort"
            and accuracy < float(objective["minimum_accuracy"])
        ):
            state["status"] = "lost"
            state["outcome_reason"] = "lantern_accuracy_failed"
            _emit(state, "defeat", "Фонарь не принял неточный путь")
        else:
            state["status"] = "won"
            outcomes = {
                "lantern_escort": ("lantern_delivered", "Фонарь достиг ворот"),
                "ink_decipher": ("true_names_read", "Настоящие имена прочитаны"),
                "ash_fire": ("fire_carried", "Огонь сохранён"),
                "drowned_sequence": ("drowned_names_released", "Имена освобождены"),
                "mirror_rule": ("courtyard_crossed", "Переписчик отступил"),
                "archivist_boss": ("archivist_defeated", "Архивариус отпустил имя"),
            }
            outcome_reason, victory_label = outcomes.get(
                str(objective.get("kind")), ("all_echoes_broken", "Колокол отвечает тебе")
            )
            state["outcome_reason"] = outcome_reason
            _emit(
                state,
                "victory",
                victory_label,
            )
        return
    state["reward_options"] = [
        {"id": upgrade_id, **copy.deepcopy(CLICKER_UPGRADES[upgrade_id])}
        for upgrade_id in REWARD_POOLS[state["round"] - 1]
    ]
    if _has_companion_role(state, "lantern"):
        # Фонарь даёт информацию в каждом сигнале, но между волнами оставляет
        # только два усиления.  Seed выбирает скрытый вариант, чтобы роль не
        # всегда удаляла одну и ту же сборку.
        remove_index = _mix(state["seed"] + 3907, state["round"]) % len(state["reward_options"])
        state["reward_options"].pop(remove_index)
    state["status"] = "reward"
    _emit(state, "wave_complete", "Выбери усиление", wave=state["round"])


def _start_next_wave(state: dict[str, Any]) -> None:
    state["round"] += 1
    state["status"] = "active"
    state["wave"] = _wave_runtime(
        state,
        state["round"] - 1,
        state["team"]["round_bonus_ms"],
        mistake_guard=state["team"]["mistake_guard"],
    )
    state["reward_options"] = []
    state["seam_ready"] = False
    state["combo"] = {"count": 0, "max": state["combo"]["max"]}
    state["challenge"] = None
    branch = _branch_state(state)
    branch["decision"] = None
    branch["manual_discharge"] = None
    branch["stored_seam_slot"] = None
    branch["forbidden_slot"] = None
    branch["tide_swap_used"] = False
    branch["hide_signal_timer"] = False
    branch["family_preview"] = None
    objective = state.get("objective_state") or {}
    if objective.get("kind") == "drowned_sequence":
        objective["attempts_left"] = int(objective["attempts_max"])
        _begin_sequence_preview(state)
    elif objective.get("kind") == "archivist_boss":
        _begin_archivist_phase(state)
    else:
        if objective.get("kind") == "mirror_rule":
            objective["forbidden_slot"] = None
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


def _consume_manual_discharge_window(state: dict[str, Any], challenge_id: int) -> None:
    branch = _branch_state(state)
    armed = branch.get("manual_discharge")
    if not isinstance(armed, dict) or challenge_id <= int(armed.get("armed_at", 0)):
        return
    armed["signals_left"] = max(0, int(armed.get("signals_left", 0)) - 1)
    if armed["signals_left"] > 0:
        return
    state["team"]["charge"] = _round_number(float(state["team"]["charge"]) * 0.5)
    branch["manual_discharge"] = None
    state["log"].append("◌ Безмолвный разряд не выпущен: половина Импульса ушла.")


def _miss_signal(
    state: dict[str, Any], *, wrong_tap: bool, selected_slot: str | None = None
) -> None:
    challenge_id = int((state.get("challenge") or {}).get("id", 0))
    charge_before = float(state["team"]["charge"])
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
    objective = state.get("objective_state") or {}
    if objective.get("kind") == "lantern_escort":
        loss = 18 if wrong_tap else 12
        objective["lantern_integrity"] = max(
            0, int(objective["lantern_integrity"]) - loss
        )
        if objective["lantern_integrity"] <= 0:
            state["status"] = "lost"
            state["outcome_reason"] = "lantern_extinguished"
            state["challenge"] = None
            _emit(state, "defeat", "Фонарь погас")
            return
    elif objective.get("kind") == "ink_decipher":
        loss = 25 if wrong_tap else 15
        objective["clarity"] = max(0, int(objective["clarity"]) - loss)
        if objective["clarity"] <= 0:
            state["status"] = "lost"
            state["outcome_reason"] = "lost_in_reflections"
            state["challenge"] = None
            _emit(state, "defeat", "Чернила скрыли настоящий знак")
            return
    elif objective.get("kind") == "ash_fire":
        loss = 18 if wrong_tap else 11
        objective["fire_integrity"] = max(
            0, int(objective["fire_integrity"]) - loss
        )
        if objective["fire_integrity"] <= 0:
            state["status"] = "lost"
            state["outcome_reason"] = "fire_extinguished"
            state["challenge"] = None
            _emit(state, "defeat", "Костёр погас")
            return
    elif objective.get("kind") == "drowned_sequence":
        objective["attempts_left"] = max(0, int(objective["attempts_left"]) - 1)
        if objective["attempts_left"] <= 0:
            state["status"] = "lost"
            state["outcome_reason"] = "names_forgotten"
            state["challenge"] = None
            _emit(state, "defeat", "Цепочка утрачена")
            return
        objective["replays"] = int(objective.get("replays", 0)) + 1
        _begin_sequence_preview(state, replay=True)
        _consume_manual_discharge_window(state, challenge_id)
        _emit(state, "miss", "ЦЕПОЧКА СНАЧАЛА")
        return
    elif (
        objective.get("kind") == "archivist_boss"
        and objective.get("phase") in {"preview", "recall"}
    ):
        objective["attempts_left"] = max(0, int(objective["attempts_left"]) - 1)
        if objective["attempts_left"] <= 0:
            state["status"] = "lost"
            state["outcome_reason"] = "last_name_lost"
            state["challenge"] = None
            _emit(state, "defeat", "Последнее имя стёрто")
            return
        objective["sequence_replays"] = int(objective.get("sequence_replays", 0)) + 1
        _begin_sequence_preview(state, replay=True)
        _consume_manual_discharge_window(state, challenge_id)
        _emit(state, "miss", "ИМЯ НУЖНО ВСПОМНИТЬ СНАЧАЛА")
        return
    elif objective.get("kind") == "mirror_rule":
        objective["wards"] = max(0, int(objective["wards"]) - 1)
        repeated = bool(
            wrong_tap and selected_slot and selected_slot == objective.get("forbidden_slot")
        )
        if repeated:
            objective["repeat_violations"] = int(objective.get("repeat_violations", 0)) + 1
            label = "ЗЕРКАЛО НАКАЗАЛО ПОВТОР"
        if objective["wards"] <= 0:
            state["status"] = "lost"
            state["outcome_reason"] = "mirror_wards_broken"
            state["challenge"] = None
            _emit(state, "defeat", "Зеркала сомкнулись")
            return
    _consume_manual_discharge_window(state, challenge_id)
    branch = _branch_state(state)
    if (
        wrong_tap
        and _has_branch(state, "bell_broken_vow")
        and not branch["broken_vow_used"]
    ):
        branch["broken_vow_used"] = True
        branch["decision"] = {
            "id": f"broken-vow:{challenge_id}",
            "kind": "mistake_recovery_choice",
            "charge_before": _round_number(charge_before),
            "options": ("keep", "release"),
        }
        state["challenge"] = None
        _emit(state, "branch_decision", "РЕШЕНИЕ КЛЯТВЫ")
        return
    _emit(state, "miss", label)
    _schedule_challenge(state)


def _advance_time(state: dict[str, Any], delta_ms: int) -> None:
    if delta_ms <= 0 or state["status"] != "active":
        return
    wave = state["wave"]
    wave["elapsed_ms"] += delta_ms
    state["mastery"]["elapsed_ms"] += delta_ms
    challenge = state.get("challenge")
    branch = _branch_state(state)
    objective = state.get("objective_state") or {}
    if _is_sequence_objective(objective) and objective.get("phase") == "preview":
        relative = int(wave["elapsed_ms"]) - int(objective["preview_started_at_ms"])
        sequence = objective["sequence"]
        if relative < 0:
            objective["preview_index"] = -1
            objective["preview_symbol"] = None
        else:
            preview_index = relative // SEQUENCE_PREVIEW_MS
            if preview_index < len(sequence):
                objective["preview_index"] = preview_index
                objective["preview_symbol"] = sequence[preview_index]
            elif relative >= len(sequence) * SEQUENCE_PREVIEW_MS + SEQUENCE_RECALL_DELAY_MS:
                objective["phase"] = "recall"
                objective["preview_symbol"] = None
                _schedule_challenge(state, first=True)
            else:
                objective["preview_symbol"] = None
    if objective.get("kind") == "ash_fire":
        target_ticks = int(state["mastery"]["elapsed_ms"]) // 2000
        new_ticks = max(0, target_ticks - int(objective.get("decay_ticks", 0)))
        if new_ticks:
            objective["decay_ticks"] = target_ticks
            objective["fire_integrity"] = max(
                0, int(objective["fire_integrity"]) - new_ticks
            )
            if objective["fire_integrity"] <= 0:
                state["status"] = "lost"
                state["outcome_reason"] = "fire_extinguished"
                state["challenge"] = None
                _emit(state, "defeat", "Костёр погас")
                return
    if objective.get("kind") == "ink_decipher" and challenge and not challenge["active"]:
        until_open = int(challenge["opens_at_ms"]) - int(wave["elapsed_ms"])
        if 0 < until_open <= 420:
            reflections = [symbol for symbol in RUNE_SYMBOLS if symbol != challenge["target_symbol"]]
            objective["reflection_cue"] = {
                "symbol": reflections[_mix(state["seed"], int(challenge["id"])) % len(reflections)],
            }
        else:
            objective["reflection_cue"] = None
    preview_active = bool(
        _has_branch(state, "tide_early_chart")
        and challenge
        and not challenge["active"]
        and 0 < int(challenge["opens_at_ms"]) - int(wave["elapsed_ms"]) <= 420
    )
    if preview_active:
        symbol = challenge["target_symbol"]
        branch["family_preview"] = "круг" if symbol == "○" else "углы"
    else:
        branch["family_preview"] = None
    auto_factor = 2 / 3 if preview_active else 1.0
    _deal(state, state["team"]["auto_dps"] * auto_factor * delta_ms / 1000.0, "auto")
    if state["status"] != "active":
        return
    challenge = state["challenge"]
    if challenge and not challenge["active"] and wave["elapsed_ms"] >= challenge["opens_at_ms"]:
        challenge["active"] = True
        branch["family_preview"] = None
        if objective.get("kind") == "ink_decipher":
            objective["reflection_cue"] = None
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
    reaction_ms = max(
        0,
        int(state["wave"]["elapsed_ms"]) - int(challenge["opens_at_ms"]),
    )
    correct = option["symbol"] == challenge["target_symbol"]
    if not correct:
        _miss_signal(state, wrong_tap=True, selected_slot=slot)
        return {
            "accepted": True,
            "correct": False,
            "reason": "wrong_rune",
            "reaction_ms": reaction_ms,
        }

    state["mastery"]["total_taps"] += 1
    state["mastery"]["correct_taps"] += 1
    state["mastery"]["reaction_total_ms"] = (
        int(state["mastery"].get("reaction_total_ms", 0)) + reaction_ms
    )
    state["mastery"]["reaction_count"] = int(
        state["mastery"].get("reaction_count", 0)
    ) + 1
    _consume_manual_discharge_window(state, int(challenge["id"]))
    branch = _branch_state(state)
    state["combo"]["count"] += 1
    forbidden_result = None
    if _has_branch(state, "seam_forbidden_repeat") and branch["forbidden_mode"]:
        prior_forbidden = branch.get("forbidden_slot")
        if prior_forbidden == slot:
            state["combo"]["count"] = 1
            forbidden_result = "forced_break"
        elif prior_forbidden:
            state["combo"]["count"] += 1
            forbidden_result = "respected"
        branch["forbidden_slot"] = slot
    state["combo"]["max"] = max(state["combo"]["max"], state["combo"]["count"])
    if state["mastery"]["mistakes"] > 0:
        state["mastery"]["max_combo_after_mistake"] = max(
            int(state["mastery"].get("max_combo_after_mistake", 0)),
            state["combo"]["count"],
        )
    objective = state.get("objective_state") or {}
    if _is_sequence_objective(objective):
        objective["answer_index"] = int(objective["answer_index"]) + 1
        if (
            objective.get("kind") == "drowned_sequence"
            and objective["answer_index"] >= int(objective["sequence_length"])
        ):
            objective["anchors_broken"] = min(
                int(objective["anchors_total"]), int(objective["anchors_broken"]) + 1
            )
    elif objective.get("kind") == "mirror_rule":
        objective["forbidden_slot"] = slot
    elif objective.get("kind") == "archivist_boss" and objective.get("phase") == "record":
        objective["recorded_slot"] = slot
    if (
        objective.get("kind") == "lantern_escort"
        and state["combo"]["count"] % 5 == 0
        and int(objective["lantern_integrity"]) < int(objective["lantern_integrity_max"])
    ):
        before = int(objective["lantern_integrity"])
        objective["lantern_integrity"] = min(
            int(objective["lantern_integrity_max"]), before + 7
        )
        objective["recoveries"] = int(objective.get("recoveries", 0)) + 1
    critical = _critical_active(state)
    multiplier = _combo_multiplier(state)
    seam_result = None
    seam_bonus = 0.0
    if _has_branch(state, "seam_cross_stitch"):
        stored_slot = branch.get("stored_seam_slot")
        if stored_slot:
            if stored_slot != slot:
                seam_bonus = 90.0
                seam_result = "broken"
            else:
                seam_result = "wasted"
            branch["stored_seam_slot"] = None
    if critical:
        multiplier *= float(state["team"]["critical_multiplier"])
        state["mastery"]["critical_taps"] += 1
        if _has_branch(state, "seam_cross_stitch"):
            branch["stored_seam_slot"] = slot
        else:
            state["seam_ready"] = True
    if objective.get("kind") == "ash_fire":
        recovery = 7 if critical else 1
        before = int(objective["fire_integrity"])
        objective["fire_integrity"] = min(
            int(objective["fire_integrity_max"]), before + recovery
        )
        if critical and objective["fire_integrity"] > before:
            objective["golden_recoveries"] = int(
                objective.get("golden_recoveries", 0)
            ) + 1
    damage = float(state["team"]["tap_power"]) * multiplier + seam_bonus
    if state["combo"]["count"] % 5 == 0:
        damage += float(state["team"]["tap_power"]) * 0.75
    companion_result = None
    companion_state = state.get("companion_state") or {}
    if (
        _has_companion_role(state, "guardian")
        and int(companion_state.get("guardian_active_challenge") or 0) == int(challenge["id"])
    ):
        damage *= 0.8
        companion_result = "guardian_wide_window"
        companion_state["guardian_active_challenge"] = None
    dealt = _deal(state, damage, "tap")
    if (
        _is_sequence_objective(objective)
        and objective["answer_index"] >= int(objective["sequence_length"])
        and state["status"] == "active"
    ):
        dealt = _round_number(dealt + _deal(state, state["wave"]["hp"], "tap"))
    state["team"]["charge"] = min(
        CHARGE_MAX * 2 - 0.01,
        state["team"]["charge"] + float(state["team"]["charge_per_hit"]),
    )
    discharged = False
    if state["status"] == "active" and state["team"]["charge"] >= CHARGE_MAX:
        if _has_branch(state, "bell_silent_release"):
            if not branch.get("manual_discharge"):
                branch["manual_discharge"] = {
                    "armed_at": int(challenge["id"]), "signals_left": 2,
                }
        else:
            _discharge(state)
            discharged = True
    if state["status"] == "active":
        if not discharged:
            _emit(
                state, "critical" if critical else "hit", "ТОЧНО" if not critical else "ЗОЛОТОЙ УДАР",
                damage=int(round(dealt)), combo=state["combo"]["count"],
            )
        if not _is_sequence_objective(objective) or (
            objective["answer_index"] < int(objective["sequence_length"])
        ):
            _schedule_challenge(state)
    return {
        "accepted": True, "correct": True, "critical": critical,
        "damage": _round_number(dealt), "discharged": discharged,
        "reaction_ms": reaction_ms, "seam_result": seam_result,
        "forbidden_result": forbidden_result, "companion_result": companion_result,
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


def _branch_action(state: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    command = str(action.get("command") or "")
    branch = _branch_state(state)
    decision = branch.get("decision")
    if command == "companion_guardian_window":
        challenge = state.get("challenge")
        companion = state.get("companion_state") or {}
        used_rounds = companion.setdefault("guardian_used_rounds", [])
        if not _has_companion_role(state, "guardian"):
            return {"ok": False, "error": "Роль Стража не выбрана."}
        if int(state["round"]) in used_rounds:
            return {"ok": False, "error": "Страж уже расширял окно в этой волне."}
        if (
            not challenge
            or not challenge.get("active")
            or int(state["wave"]["elapsed_ms"]) >= int(challenge["expires_at_ms"])
        ):
            return {"ok": False, "error": "Сейчас нет окна, которое можно расширить."}
        challenge["expires_at_ms"] = int(challenge["expires_at_ms"]) + 320
        companion["guardian_active_challenge"] = int(challenge["id"])
        used_rounds.append(int(state["round"]))
        _emit(state, "companion", "СТРАЖ РАСШИРИЛ ОКНО", role="guardian")
        return {
            "ok": True, "phase": state["status"], "branch": "companion_guardian",
            "result": "window_extended", "challenge_id": int(challenge["id"]),
        }
    if command in {"vow_keep", "vow_release"}:
        if not isinstance(decision, dict) or decision.get("kind") != "mistake_recovery_choice":
            return {"ok": False, "error": "Сейчас нет решения Клятвы."}
        expected_id = str(action.get("decision_id") or "")
        if expected_id != decision["id"]:
            return {"ok": False, "error": "Решение Клятвы уже изменилось."}
        if command == "vow_keep":
            state["team"]["charge"] = _round_number(float(decision["charge_before"]) * 0.5)
            branch["next_signal_penalty_ms"] = 180
            result = "charge_kept"
            state["log"].append("🔔 Половина Импульса сохранена; следующее окно уже.")
        else:
            state["team"]["charge"] = 0.0
            result = "charge_released"
            state["log"].append("◌ Импульс отпущен; следующее окно осталось полным.")
        branch["decision"] = None
        _schedule_challenge(state)
        _emit(state, "branch", "КЛЯТВА ПРИНЯТА", result=result)
        return {"ok": True, "phase": state["status"], "branch": "bell_broken_vow", "result": result}

    if command == "manual_discharge":
        armed = branch.get("manual_discharge")
        challenge = state.get("challenge")
        if (
            not _has_branch(state, "bell_silent_release")
            or not isinstance(armed, dict)
            or not challenge
            or not challenge.get("active")
        ):
            return {"ok": False, "error": "Безмолвный разряд сейчас недоступен."}
        branch["manual_discharge"] = None
        damage = _discharge(state)
        return {
            "ok": True, "phase": state["status"], "branch": "bell_silent_release",
            "result": "released", "damage": _round_number(damage),
        }

    if command == "forbidden_toggle":
        if not _has_branch(state, "seam_forbidden_repeat"):
            return {"ok": False, "error": "Запретный стежок не выбран."}
        enabled = bool(action.get("enabled"))
        branch["forbidden_mode"] = enabled
        if not enabled:
            branch["forbidden_slot"] = None
        result = "enabled" if enabled else "disabled"
        _emit(state, "branch", "ЗАПРЕТНЫЙ СТЕЖОК", result=result)
        return {
            "ok": True, "phase": state["status"], "branch": "seam_forbidden_repeat",
            "result": result,
        }

    if command == "tide_swap":
        challenge = state.get("challenge")
        if (
            not _has_branch(state, "tide_hidden_swap")
            or branch["tide_swap_used"]
            or not challenge
            or not challenge.get("active")
        ):
            return {"ok": False, "error": "Сдвиг течения сейчас недоступен."}
        options = list(challenge["options"])
        shift = 1 + (_mix(state["seed"], int(challenge["id"])) % 2)
        symbols = [option["symbol"] for option in options]
        rotated = symbols[-shift:] + symbols[:-shift]
        for option, symbol in zip(options, rotated):
            option["symbol"] = symbol
        branch["tide_swap_used"] = True
        branch["hide_signal_timer"] = True
        _emit(state, "branch", "СДВИГ ТЕЧЕНИЯ", result="positions_shifted")
        return {
            "ok": True, "phase": state["status"], "branch": "tide_hidden_swap",
            "result": "positions_shifted",
        }

    return {"ok": False, "error": "Неизвестное действие ветви мастерства."}


def apply_action(state: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {"ok": False, "error": "Действие должно быть объектом."}
    action_type = str(action.get("type") or "")
    if action_type == "choose_upgrade":
        return _choose_upgrade(state, str(action.get("upgrade_id") or ""))
    if state["status"] != "active":
        return {"ok": False, "error": "Раунд сейчас не активен."}
    if action_type == "branch_action":
        command = str(action.get("command") or "")
        if command not in {"vow_keep", "vow_release"}:
            try:
                delta_ms = int(action.get("delta_ms", 0))
            except (TypeError, ValueError):
                return {"ok": False, "error": "delta_ms должен быть целым числом."}
            if delta_ms < 0:
                return {"ok": False, "error": "Время кадра не может быть отрицательным."}
            _advance_time(state, min(delta_ms, FRAME_MAX_MS))
            if state["status"] != "active":
                branch_id = {
                    "manual_discharge": "bell_silent_release",
                    "forbidden_toggle": "seam_forbidden_repeat",
                    "tide_swap": "tide_hidden_swap",
                    "companion_guardian_window": "companion_guardian",
                }.get(command, "unknown")
                return {
                    "ok": True, "phase": state["status"], "branch": branch_id,
                    "result": "expired_before_action",
                }
        return _branch_action(state, action)
    if _branch_state(state).get("decision"):
        return {"ok": False, "error": "Сначала прими решение Клятвы."}
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
    view.pop("_integrity", None)
    view.pop("challenge_seq", None)
    wave = view["wave"]
    wave["time_left_ms"] = max(0, int(wave["duration_ms"]) - int(wave["elapsed_ms"]))
    challenge = view.get("challenge")
    objective = view.get("objective_state") or {}
    if _is_sequence_objective(objective):
        objective.pop("sequence", None)
        objective.pop("preview_started_at_ms", None)
    if challenge:
        elapsed = int(wave["elapsed_ms"])
        if challenge["active"]:
            duration = max(1, challenge["expires_at_ms"] - challenge["opens_at_ms"])
            view["signal_progress"] = min(1.0, max(0.0, (elapsed - challenge["opens_at_ms"]) / duration))
            if _is_sequence_objective(objective):
                challenge["target_symbol"] = None
        else:
            duration = max(1, challenge["opens_at_ms"] - challenge["scheduled_at_ms"])
            view["signal_progress"] = min(1.0, max(0.0, (elapsed - challenge["scheduled_at_ms"]) / duration))
            challenge["target_symbol"] = None
            challenge["options"] = []
    else:
        view["signal_progress"] = 0.0
    view["critical_active"] = _critical_active(state) if state["status"] == "active" else False
    view["waves_total"] = len(_waves(state))
    view["wave_labels"] = [str(wave.get("rail") or wave["name"]) for wave in _waves(state)]
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
