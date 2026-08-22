"""Регрессии точного автокликера Reconstruction 3.0."""
from __future__ import annotations

import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.reconstruction import CLICKER_UPGRADES, ENCOUNTERS, STARTER_UNITS, validate_content
from services import reconstruction_combat as combat


def act(state, **action):
    result = combat.apply_action(state, action)
    assert result.get("ok"), f"действие отклонено: {action} -> {result}"
    return result


def open_signal(state):
    while state["status"] == "active" and not (state.get("challenge") or {}).get("active"):
        act(state, type="frame", delta_ms=100)
    return state.get("challenge")


def correct_slot(challenge):
    return next(
        option["slot"] for option in challenge["options"]
        if option["symbol"] == challenge["target_symbol"]
    )


def take_upgrade(upgrade_id, *, after_wave=1):
    state = combat.new_encounter(seed=404 + after_wave)
    state["round"] = after_wave
    state["status"] = "reward"
    state["challenge"] = None
    state["reward_options"] = [{"id": upgrade_id}]
    act(state, type="choose_upgrade", upgrade_id=upgrade_id)
    return state


# Контент и новый режим имеют цель/усиления, а не скрыто используют старую сетку.
assert validate_content() == []
assert len(STARTER_UNITS) == 3
assert len(CLICKER_UPGRADES) >= 6
assert ENCOUNTERS["e01_two_bells"]["objective"]["type"] == "rush"

# Состояние детерминировано и переживает JSON round-trip.
left = combat.new_encounter(seed=703)
right = combat.new_encounter(seed=703)
assert combat.dumps(left) == combat.dumps(right)
assert combat.loads(combat.dumps(left)) == left

# Клиент не видит правильную руну до открытия серверного сигнала.
hidden = combat.public_state(left)
assert hidden["challenge"]["active"] is False
assert hidden["challenge"]["target_symbol"] is None
assert hidden["challenge"]["options"] == []
assert hidden["accuracy"] is None and hidden["tap_accuracy"] is None
assert hidden["signals_resolved"] == 0

# Один сигнал принимает ровно одну попытку; повтор старого correct-click бесполезен.
single = combat.new_encounter(seed=22)
challenge = open_signal(single)
slot = correct_slot(challenge)
first = act(single, type="strike", challenge_id=challenge["id"], target_slot=slot)
damage_after_first = single["mastery"]["damage_taps"]
replay = act(single, type="strike", challenge_id=challenge["id"], target_slot=slot)
assert first["strike"]["correct"] is True
assert isinstance(first["strike"]["reaction_ms"], int)
assert first["strike"]["reaction_ms"] >= 0
assert replay["strike"] == {"accepted": False, "correct": False, "reason": "no_active_signal"}
assert single["mastery"]["damage_taps"] == damage_after_first

# Ошибка не маскируется частотой: неправильная руна сбрасывает точную серию.
mistake = combat.new_encounter(seed=9)
challenge = open_signal(mistake)
act(mistake, type="strike", challenge_id=challenge["id"], target_slot=correct_slot(challenge))
challenge = open_signal(mistake)
wrong = next(option["slot"] for option in challenge["options"] if option["symbol"] != challenge["target_symbol"])
act(mistake, type="strike", challenge_id=challenge["id"], target_slot=wrong)
assert mistake["combo"]["count"] == 0
assert mistake["mastery"]["mistakes"] == 1
assert mistake["mastery"]["correct_taps"] == 1
mistake_view = combat.public_state(mistake)
assert mistake_view["signals_resolved"] == 2
assert mistake_view["accuracy"] == 50.0
assert mistake_view["tap_accuracy"] == 50.0

# Пропущенный знак входит в игровую точность, но не притворяется физическим
# нажатием: два показателя имеют разные, проверяемые определения.
missed = combat.new_encounter(seed=10)
challenge = open_signal(missed)
while missed["mastery"]["missed_signals"] == 0:
    act(missed, type="frame", delta_ms=500)
missed_view = combat.public_state(missed)
assert missed_view["mastery"]["total_taps"] == 0
assert missed_view["mastery"]["missed_signals"] == 1
assert missed_view["signals_resolved"] == 1
assert missed_view["accuracy"] == 0.0
assert missed_view["tap_accuracy"] is None

# Время запроса применяется до удара: просроченный правильный символ не может
# быть принят только потому, что клиент прислал его вместе с поздним frame.
late = combat.new_encounter(seed=11)
challenge = open_signal(late)
remaining = challenge["expires_at_ms"] - late["wave"]["elapsed_ms"]
while remaining > 1:
    act(late, type="frame", delta_ms=min(500, remaining - 1))
    remaining = late["challenge"]["expires_at_ms"] - late["wave"]["elapsed_ms"]
late_result = act(
    late,
    type="frame",
    delta_ms=1,
    challenge_id=challenge["id"],
    target_slot=correct_slot(challenge),
)
assert late_result["strike"]["accepted"] is False
assert late_result["strike"]["reason"] in {"no_active_signal", "stale_signal"}
assert late["mastery"]["correct_taps"] == 0
assert late["mastery"]["missed_signals"] == 1

# Простой автоклик по одной координате не проходит первую волну ни на одном из
# проверяемых seed: позиции выдаются перемешанными сбалансированными тройками.
for seed in range(1, 33):
    fixed_clicker = combat.new_encounter(seed=seed)
    guard = 0
    while fixed_clicker["status"] == "active" and guard < 500:
        guard += 1
        challenge = open_signal(fixed_clicker)
        if fixed_clicker["status"] != "active":
            break
        act(fixed_clicker, type="strike", challenge_id=challenge["id"], target_slot="left")
    assert fixed_clicker["status"] == "lost", f"fixed clicker survived seed={seed}"
    assert fixed_clicker["mastery"]["correct_taps"] < fixed_clicker["mastery"]["mistakes"]

# Поздняя, но правильная попытка попадает в необязательное золотое окно.
gold = combat.new_encounter(seed=31)
challenge = open_signal(gold)
remaining = challenge["expires_at_ms"] - gold["wave"]["elapsed_ms"]
while remaining > 220:
    act(gold, type="frame", delta_ms=min(100, remaining - 220))
    remaining = gold["challenge"]["expires_at_ms"] - gold["wave"]["elapsed_ms"]
challenge = gold["challenge"]
result = act(gold, type="strike", challenge_id=challenge["id"], target_slot=correct_slot(challenge))
assert result["strike"]["critical"] is True
assert gold["mastery"]["critical_taps"] == 1

# Межволновые усиления — это сборки с реальной ценой выбора, а не шесть
# одинаковых «+число»: каждый эффект меняет движок и виден в состоянии.
heavy = take_upgrade("heavy_echo")
assert heavy["team"]["tap_power"] == 83
assert heavy["team"]["signal_window_bonus_ms"] == -160
assert heavy["challenge"]["expires_at_ms"] - heavy["challenge"]["opens_at_ms"] == 890

current = take_upgrade("quick_current")
assert current["team"]["auto_dps"] == 9.6
assert current["team"]["charge_per_hit"] == 20

seam = take_upgrade("golden_seam")
assert seam["team"]["tap_power"] == 55
assert seam["team"]["critical_multiplier"] == 2.05
assert seam["team"]["critical_window_ms"] == 480

discharge = take_upgrade("deep_discharge", after_wave=2)
assert discharge["team"]["overdrive_power"] == 215
assert discharge["team"]["tap_power"] == 57

guarded = take_upgrade("last_bell", after_wave=2)
guarded["team"]["charge"] = 80
guard_challenge = open_signal(guarded)
hp_before_guard = guarded["wave"]["hp"]
wrong_guard = next(
    option["slot"] for option in guard_challenge["options"]
    if option["symbol"] != guard_challenge["target_symbol"]
)
act(guarded, type="strike", challenge_id=guard_challenge["id"], target_slot=wrong_guard)
assert guarded["wave"]["hp"] == hp_before_guard
assert guarded["team"]["charge"] == 40
assert guarded["wave"]["mistake_guard_available"] is False

hungry = take_upgrade("hungry_pattern", after_wave=2)
hungry["team"]["charge"] = 80
hungry_challenge = open_signal(hungry)
hp_before_hungry = hungry["wave"]["hp"]
wrong_hungry = next(
    option["slot"] for option in hungry_challenge["options"]
    if option["symbol"] != hungry_challenge["target_symbol"]
)
act(hungry, type="strike", challenge_id=hungry_challenge["id"], target_slot=wrong_hungry)
assert hungry["wave"]["hp"] == min(hungry["wave"]["hp_max"], hp_before_hungry + 105)
assert hungry["team"]["charge"] == 0
assert hungry["team"]["combo_step_multiplier"] == 1.8

# Точный игрок проходит весь короткий забег; между волнами выбор реально меняет статы.
perfect = combat.new_encounter(seed=703)
selected = []
guard = 0
while perfect["status"] not in {"won", "lost"} and guard < 1000:
    guard += 1
    if perfect["status"] == "reward":
        upgrade_id = perfect["reward_options"][0]["id"]
        selected.append(upgrade_id)
        act(perfect, type="choose_upgrade", upgrade_id=upgrade_id)
        continue
    challenge = open_signal(perfect)
    if perfect["status"] != "active":
        continue
    act(perfect, type="strike", challenge_id=challenge["id"], target_slot=correct_slot(challenge))
assert perfect["status"] == "won"
assert combat.public_state(perfect)["accuracy"] == 100.0
assert perfect["mastery"]["correct_taps"] == perfect["mastery"]["total_taps"]
assert perfect["combo"]["max"] >= 8
assert perfect["upgrades"] == selected and len(selected) == 2

# Вторая встреча — не перекрашенный первый бой: Фонарь имеет собственную
# прочность, восстанавливается за чистую серию и может погаснуть от ошибок.
lantern = combat.new_encounter("e02_shattered_causeway", seed=904)
assert lantern["objective_state"]["lantern_integrity"] == 100
challenge = open_signal(lantern)
wrong = next(
    option["slot"] for option in challenge["options"]
    if option["symbol"] != challenge["target_symbol"]
)
act(lantern, type="strike", challenge_id=challenge["id"], target_slot=wrong)
assert lantern["objective_state"]["lantern_integrity"] == 82
for _ in range(5):
    challenge = open_signal(lantern)
    act(lantern, type="strike", challenge_id=challenge["id"], target_slot=correct_slot(challenge))
assert lantern["objective_state"]["lantern_integrity"] == 89
assert lantern["objective_state"]["recoveries"] == 1

extinguished = combat.new_encounter("e02_shattered_causeway", seed=905)
while extinguished["status"] == "active":
    challenge = open_signal(extinguished)
    if extinguished["status"] != "active":
        break
    wrong = next(
        option["slot"] for option in challenge["options"]
        if option["symbol"] != challenge["target_symbol"]
    )
    act(extinguished, type="strike", challenge_id=challenge["id"], target_slot=wrong)
assert extinguished["status"] == "lost"
assert extinguished["outcome_reason"] == "lantern_extinguished"

lantern_perfect = combat.new_encounter("e02_shattered_causeway", seed=906)
guard = 0
while lantern_perfect["status"] not in {"won", "lost"} and guard < 1600:
    guard += 1
    if lantern_perfect["status"] == "reward":
        act(
            lantern_perfect,
            type="choose_upgrade",
            upgrade_id=lantern_perfect["reward_options"][0]["id"],
        )
        continue
    challenge = open_signal(lantern_perfect)
    if lantern_perfect["status"] == "active":
        act(
            lantern_perfect,
            type="strike",
            challenge_id=challenge["id"],
            target_slot=correct_slot(challenge),
        )
assert lantern_perfect["status"] == "won"
assert lantern_perfect["outcome_reason"] == "lantern_delivered"
assert combat.public_state(lantern_perfect)["accuracy"] == 100.0

# Развилка Хроники даёт две разные грамматики, а не две перекрашенные HP-линии.
ink = combat.new_encounter("e03_ink_path", seed=1001)
while ink["objective_state"]["reflection_cue"] is None:
    act(ink, type="frame", delta_ms=50)
ink_view = combat.public_state(ink)
assert ink_view["objective_state"]["reflection_cue"]["symbol"] != ink["challenge"]["target_symbol"]
assert ink_view["challenge"]["target_symbol"] is None
for _ in range(4):
    challenge = open_signal(ink)
    wrong = next(
        option["slot"] for option in challenge["options"]
        if option["symbol"] != challenge["target_symbol"]
    )
    act(ink, type="strike", challenge_id=challenge["id"], target_slot=wrong)
assert ink["status"] == "lost" and ink["outcome_reason"] == "lost_in_reflections"

ash = combat.new_encounter("e03_ash_path", seed=1002)
initial_fire = ash["objective_state"]["fire_integrity"]
ash["challenge"]["opens_at_ms"] = 5000
ash["challenge"]["expires_at_ms"] = 6000
for _ in range(20):
    act(ash, type="frame", delta_ms=100)
assert ash["objective_state"]["fire_integrity"] == initial_fire - 1

for encounter_id, outcome_reason in (
    ("e03_ink_path", "true_names_read"),
    ("e03_ash_path", "fire_carried"),
):
    path = combat.new_encounter(encounter_id, seed=1003)
    for _ in range(1800):
        if path["status"] in {"won", "lost"}:
            break
        if path["status"] == "reward":
            act(path, type="choose_upgrade", upgrade_id=path["reward_options"][0]["id"])
            continue
        challenge = open_signal(path)
        act(
            path, type="strike", challenge_id=challenge["id"],
            target_slot=correct_slot(challenge),
        )
    assert path["status"] == "won", (encounter_id, path["outcome_reason"])
    assert path["outcome_reason"] == outcome_reason

# Четвёртая встреча проверяет память, а не поиск видимого совпадения. Сервер
# показывает цепочку по одному знаку, затем скрывает ответ и принимает только
# правильный порядок. Повтор старого challenge_id не получает второго шанса.
names = combat.new_encounter("e04_drowned_names", seed=1401)
first_sequence = list(names["objective_state"]["sequence"])
assert len(first_sequence) == 2
assert "sequence" not in combat.public_state(names)["objective_state"]
seen_preview = []
while names["objective_state"]["phase"] == "preview":
    act(names, type="frame", delta_ms=100)
    symbol = names["objective_state"].get("preview_symbol")
    if symbol and (not seen_preview or seen_preview[-1] != symbol):
        seen_preview.append(symbol)
assert seen_preview == first_sequence
challenge = open_signal(names)
hidden_recall = combat.public_state(names)
assert hidden_recall["challenge"]["target_symbol"] is None
assert len(hidden_recall["challenge"]["options"]) == 3
first_id = challenge["id"]
wrong = next(
    option["slot"] for option in challenge["options"]
    if option["symbol"] != challenge["target_symbol"]
)
act(names, type="strike", challenge_id=first_id, target_slot=wrong)
assert names["objective_state"]["phase"] == "preview"
assert names["objective_state"]["attempts_left"] == 2
assert names["objective_state"]["sequence"] == first_sequence
challenge = open_signal(names)
assert challenge["id"] > first_id
stale = act(names, type="strike", challenge_id=first_id, target_slot=correct_slot(challenge))
assert stale["strike"]["accepted"] is False
assert stale["strike"]["reason"] == "stale_signal"

names_perfect = combat.new_encounter("e04_drowned_names", seed=1402)
for _ in range(1800):
    if names_perfect["status"] in {"won", "lost"}:
        break
    if names_perfect["status"] == "reward":
        act(
            names_perfect, type="choose_upgrade",
            upgrade_id=names_perfect["reward_options"][0]["id"],
        )
        continue
    challenge = names_perfect.get("challenge")
    if not challenge or not challenge["active"]:
        act(names_perfect, type="frame", delta_ms=100)
        continue
    act(
        names_perfect, type="strike", challenge_id=challenge["id"],
        target_slot=correct_slot(challenge),
    )
assert names_perfect["status"] == "won"
assert names_perfect["outcome_reason"] == "drowned_names_released"
assert names_perfect["objective_state"]["anchors_broken"] == 3
assert names_perfect["objective_state"]["replays"] == 0
assert names_perfect["mastery"]["correct_taps"] == 8

# Первый рубеж мастерства меняет решения, а не только числа.
vow = combat.new_encounter(seed=1201, unit_branches={"r_oath_bell": "bell_broken_vow"})
vow["team"]["charge"] = 80
challenge = open_signal(vow)
wrong = next(
    option["slot"] for option in challenge["options"]
    if option["symbol"] != challenge["target_symbol"]
)
act(vow, type="strike", challenge_id=challenge["id"], target_slot=wrong)
decision = vow["branch_state"]["decision"]
assert decision["kind"] == "mistake_recovery_choice" and vow["challenge"] is None
blocked = combat.apply_action(vow, {"type": "frame", "delta_ms": 100})
assert blocked["ok"] is False and "Клятвы" in blocked["error"]
act(vow, type="branch_action", command="vow_keep", decision_id=decision["id"])
assert vow["team"]["charge"] == 40
assert vow["challenge"]["expires_at_ms"] - vow["challenge"]["opens_at_ms"] == 1020

silent = combat.new_encounter(seed=1202, unit_branches={"r_oath_bell": "bell_silent_release"})
silent["team"]["charge"] = 75
challenge = open_signal(silent)
hit = act(silent, type="strike", challenge_id=challenge["id"], target_slot=correct_slot(challenge))
assert hit["strike"]["discharged"] is False
assert silent["branch_state"]["manual_discharge"]["signals_left"] == 2
challenge = open_signal(silent)
released = act(silent, type="branch_action", command="manual_discharge")
assert released["branch"] == "bell_silent_release"
assert silent["mastery"]["discharges"] == 1 and silent["team"]["charge"] < 100

cross = combat.new_encounter(seed=1203, unit_branches={"r_red_seam": "seam_cross_stitch"})
challenge = open_signal(cross)
remaining = challenge["expires_at_ms"] - cross["wave"]["elapsed_ms"]
while remaining > 220:
    act(cross, type="frame", delta_ms=min(100, remaining - 220))
    remaining = cross["challenge"]["expires_at_ms"] - cross["wave"]["elapsed_ms"]
challenge = cross["challenge"]
critical_slot = correct_slot(challenge)
act(cross, type="strike", challenge_id=challenge["id"], target_slot=critical_slot)
assert cross["branch_state"]["stored_seam_slot"] == critical_slot
challenge = open_signal(cross)
next_slot = correct_slot(challenge)
cross["branch_state"]["stored_seam_slot"] = next(
    slot for slot in combat.RUNE_SLOTS if slot != next_slot
)
stitched = act(cross, type="strike", challenge_id=challenge["id"], target_slot=next_slot)
assert stitched["strike"]["seam_result"] == "broken"

forbidden = combat.new_encounter(seed=1204, unit_branches={"r_red_seam": "seam_forbidden_repeat"})
act(forbidden, type="branch_action", command="forbidden_toggle", enabled=True)
challenge = open_signal(forbidden)
slot = correct_slot(challenge)
forbidden["combo"]["count"] = 10
forbidden["branch_state"]["forbidden_slot"] = slot
forced = act(forbidden, type="strike", challenge_id=challenge["id"], target_slot=slot)
assert forced["strike"]["forbidden_result"] == "forced_break"
assert forbidden["combo"]["count"] == 1

shifted = combat.new_encounter(seed=1205, unit_branches={"r_tide_cartographer": "tide_hidden_swap"})
challenge = open_signal(shifted)
slot_before = correct_slot(challenge)
swap = act(shifted, type="branch_action", command="tide_swap")
slot_after = correct_slot(shifted["challenge"])
assert swap["branch"] == "tide_hidden_swap" and slot_after != slot_before
assert shifted["branch_state"]["hide_signal_timer"] is True
repeated_swap = combat.apply_action(shifted, {"type": "branch_action", "command": "tide_swap"})
assert repeated_swap["ok"] is False

chart = combat.new_encounter(seed=1206, unit_branches={"r_tide_cartographer": "tide_early_chart"})
while chart["branch_state"]["family_preview"] is None:
    act(chart, type="frame", delta_ms=50)
chart_view = combat.public_state(chart)
assert chart_view["branch_state"]["family_preview"] in {"круг", "углы"}
assert chart_view["challenge"]["target_symbol"] is None


def finish_with_branch_policy(seed, selected=None):
    unit_branches = {selected[0]: selected[1]} if selected else None
    state = combat.new_encounter(seed=seed, unit_branches=unit_branches)
    if selected and selected[1] == "seam_forbidden_repeat":
        act(state, type="branch_action", command="forbidden_toggle", enabled=True)
    for _ in range(1600):
        if state["status"] in {"won", "lost"}:
            return state
        if state["status"] == "reward":
            act(state, type="choose_upgrade", upgrade_id=state["reward_options"][0]["id"])
            continue
        decision = state["branch_state"].get("decision")
        if decision:
            act(state, type="branch_action", command="vow_keep", decision_id=decision["id"])
            continue
        challenge = open_signal(state)
        if state["branch_state"].get("manual_discharge"):
            act(state, type="branch_action", command="manual_discharge")
            if state["status"] != "active":
                continue
        if selected and selected[1] == "tide_hidden_swap" and not state["branch_state"]["tide_swap_used"]:
            act(state, type="branch_action", command="tide_swap")
            challenge = state["challenge"]
        act(
            state, type="strike", challenge_id=challenge["id"],
            target_slot=correct_slot(challenge),
        )
    raise AssertionError("Branch balance simulation exceeded guard")


branch_pairs = (
    ("r_oath_bell", "bell_broken_vow"),
    ("r_oath_bell", "bell_silent_release"),
    ("r_red_seam", "seam_cross_stitch"),
    ("r_red_seam", "seam_forbidden_repeat"),
    ("r_tide_cartographer", "tide_hidden_swap"),
    ("r_tide_cartographer", "tide_early_chart"),
)
meaningful_difference_seen = False
for seed in range(101, 109):
    baseline = finish_with_branch_policy(seed)
    assert baseline["status"] == "won"
    baseline_taps = baseline["mastery"]["correct_taps"]
    for pair in branch_pairs:
        candidate = finish_with_branch_policy(seed, pair)
        assert candidate["status"] == "won"
        candidate_taps = candidate["mastery"]["correct_taps"]
        advantage = (baseline_taps - candidate_taps) / baseline_taps
        assert advantage <= 0.25, (seed, pair, advantage)
        meaningful_difference_seen |= candidate_taps != baseline_taps
assert meaningful_difference_seen, "All branch policies collapsed to the base kit"

# Public-state является копией, а не возможностью мутировать server state.
view = combat.public_state(perfect)
snapshot = copy.deepcopy(perfect)
view["team"]["tap_power"] = 99999
assert perfect == snapshot

print("reconstruction_clicker: accuracy+anti-spam+gold-window+run  OK")
