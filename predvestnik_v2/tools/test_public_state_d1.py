"""D1: public_state сериализуется под сетку (снят деплой-гейт focus KeyError). Временный."""
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from services import battle3 as b3
from core.units import UNITS
from core.constants import GRID_W, GRID_H

ally = [{"unit_id": uid, "level": 8, "slot": i} for i, uid in enumerate(list(UNITS)[:3])]
st = b3.new_battle_state(ally, b3.gates_enemy_squad(2), "gates", {"floor": 2, "seed": 9})

ps = b3.public_state(st, 42)                      # раньше падал KeyError: 'focus'
raw = json.dumps(ps, ensure_ascii=False)          # обязано быть JSON-сериализуемо
assert "focus" not in ps["ally"], "focus остался в public_state"
assert "hand" not in ps and "deck_left" not in ps, "рунные поля остались"
assert len(ps["grid"]) == GRID_H and len(ps["grid"][0]) == GRID_W, "grid не отдан"
for u in ps["ally"]["units"]:
    assert "pos" in u and "ap" in u and "ap_max" in u and "range" in u, "нет боевых полей ally"
for u in ps["enemy"]["units"]:
    assert "pos" in u, "нет pos у врага"
assert "ap_costs" in ps and ps["ap_costs"]["attack"] == 2, "нет/неверные ap_costs"
print("public_state_d1: сериализуется, сетка+pos+ap отданы, focus/hand убраны  OK")

# после хода в бою public_state всё ещё сериализуется (телеграф/intents)
b3.apply_action(st, {"type": "end_turn"})
json.dumps(b3.public_state(st, 42), ensure_ascii=False)
print("public_state_d1: сериализуется и после хода (телеграф ок)  OK")
print("ALL PUBLIC_STATE TESTS PASSED")
