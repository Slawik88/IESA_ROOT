"""B2b: каждый из 16 навыков применяется без краха; целевой навык уважает дальность. Временный."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from services import battle3 as b3
from services import battle_grid as g
from core.units import UNITS

TARGET = {"burn", "frost_bite", "chain", "pierce", "drain", "void_strike", "web"}

# 1) Для каждого юнита: собрать отряд из него ×3, поставить рядом с врагом, применить навык
for uid, u in UNITS.items():
    code = u["skill"]["code"]
    ally = [{"unit_id": uid, "level": 10, "slot": i} for i in range(1)]
    st = b3.new_battle_state(ally, b3.gates_enemy_squad(1), "gates", {"floor": 1, "seed": 3})
    a = st["ally"]["units"][0]
    # поставить атакующего вплотную к первому врагу (для целевых навыков — дальность/LoS ок)
    e0 = st["enemy"]["units"][0]
    a["pos"] = {"x": max(0, e0["pos"]["x"] - 1), "y": e0["pos"]["y"]}
    a["ap"] = a["ap_max"]
    a["cd"]["skill"] = 0
    r = b3.apply_action(st, {"type": "skill", "unit_i": 0, "target_i": 0})
    assert r.get("ok"), f"навык '{code}' ({uid}) не применился: {r}"
    assert a["ap"] == a["ap_max"] - 3, f"навык '{code}' не списал 3 AP"
    assert a["cd"]["skill"] == 2, f"навык '{code}' не поставил КД"
print(f"skills_b2b: все {len(UNITS)} навыков применяются, AP/КД списываются  OK")

# 2) Целевой навык вне дальности → отказ, AP/КД не тратятся
uid = next(x for x, uu in UNITS.items() if uu["skill"]["code"] == "burn")
st = b3.new_battle_state([{"unit_id": uid, "level": 10, "slot": 0}],
                         b3.gates_enemy_squad(1), "gates", {"floor": 1, "seed": 3})
a = st["ally"]["units"][0]
a["pos"] = {"x": 0, "y": 0}
for e in st["enemy"]["units"]:
    e["pos"] = {"x": 6, "y": 4}   # далеко
ap0 = a["ap"]
r = b3.apply_action(st, {"type": "skill", "unit_i": 0, "target_i": 0})
assert not r.get("ok"), "целевой навык вне дальности должен отказать"
assert a["ap"] == ap0 and a["cd"]["skill"] == 0, "отказ навыка не должен тратить AP/КД"
print("skills_b2b: целевой навык уважает дальность (отказ без траты)  OK")

# 3) Триада: 3 разные стихии → доступна раз в бой
elems = {}
for uid, u in UNITS.items():
    elems.setdefault(u["element"], uid)
three = list(elems.values())[:3]
if len(three) == 3:
    st = b3.new_battle_state([{"unit_id": t, "level": 10, "slot": i} for i, t in enumerate(three)],
                             b3.gates_enemy_squad(1), "gates", {"floor": 1, "seed": 3})
    r1 = b3.apply_action(st, {"type": "triad"})
    assert r1.get("ok"), f"Триада должна быть доступна при 3 разных стихиях: {r1}"
    r2 = b3.apply_action(st, {"type": "triad"})
    assert not r2.get("ok"), "Триада доступна только раз в бой"
    print("skills_b2b: Триада — раз в бой при 3 стихиях  OK")
print("ALL SKILL TESTS PASSED")
