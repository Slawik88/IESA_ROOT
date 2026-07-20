import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from services import battle3 as b3
from core.constants import GRID_W, GRID_H
from core.units import UNITS

ally = [{"unit_id": uid, "level": 1, "slot": i}
        for i, uid in enumerate(list(UNITS)[:3])]
enemies = b3.gates_enemy_squad(1)
st = b3.new_battle_state(ally, enemies, "gates", {"floor": 1, "seed": 42})
assert len(st["grid"]) == GRID_H and len(st["grid"][0]) == GRID_W, "размер сетки"
for u in st["ally"]["units"]:
    assert "pos" in u and 0 <= u["pos"]["x"] < GRID_W and 0 <= u["pos"]["y"] < GRID_H, "pos ally"
    assert u["ap"] == u["ap_max"] >= 4, "ap ally"
for u in st["enemy"]["units"]:
    assert "pos" in u, "pos enemy"
poss = [(u["pos"]["x"], u["pos"]["y"]) for u in st["ally"]["units"] + st["enemy"]["units"]]
assert len(poss) == len(set(poss)), "коллизия спавнов"
st2 = b3.new_battle_state(ally, enemies, "gates", {"floor": 1, "seed": 42})
assert st["grid"] == st2["grid"], "grid недетерминирован по seed"
print("battle_state: сетка+позиции+AP+детерминизм  OK")
