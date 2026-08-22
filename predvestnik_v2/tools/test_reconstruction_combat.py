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
    while state["status"] == "active" and not state["challenge"]["active"]:
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

# Public-state является копией, а не возможностью мутировать server state.
view = combat.public_state(perfect)
snapshot = copy.deepcopy(perfect)
view["team"]["tap_power"] = 99999
assert perfect == snapshot

print("reconstruction_clicker: accuracy+anti-spam+gold-window+run  OK")
