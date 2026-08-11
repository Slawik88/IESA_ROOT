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

# Один сигнал принимает ровно одну попытку; повтор старого correct-click бесполезен.
single = combat.new_encounter(seed=22)
challenge = open_signal(single)
slot = correct_slot(challenge)
first = act(single, type="strike", challenge_id=challenge["id"], target_slot=slot)
damage_after_first = single["mastery"]["damage_taps"]
replay = act(single, type="strike", challenge_id=challenge["id"], target_slot=slot)
assert first["strike"]["correct"] is True
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
