"""C1: EV-ИИ детерминирован; защита реально снижает урон; бой завершается. Временный."""
import sys, pathlib, copy
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from services import battle3 as b3
from services import battle_grid as g
from core.units import UNITS

ally = [{"unit_id": uid, "level": 8, "slot": i} for i, uid in enumerate(list(UNITS)[:3])]

# 1) Детерминизм: одинаковый state → одинаковая фаза врага
st1 = b3.new_battle_state(ally, b3.gates_enemy_squad(3), "gates", {"floor": 3, "seed": 11})
st2 = copy.deepcopy(st1)
b3._enemy_phase(st1, [])
b3._enemy_phase(st2, [])
hp1 = [u["hp"] for u in st1["ally"]["units"]]
hp2 = [u["hp"] for u in st2["ally"]["units"]]
assert hp1 == hp2, f"ИИ врага НЕ детерминирован: {hp1} != {hp2}"
print("enemy_ai: детерминизм фазы врага  OK")

# 2) Защита реально снижает урон (B4_DEFEND_MULT наконец работает)
base = b3.new_battle_state(ally, b3.gates_enemy_squad(3), "gates", {"floor": 3, "seed": 11})
guarded = copy.deepcopy(base)
# ставим первого союзника вплотную к первому врагу в обоих; в guarded — он в защите
for st in (base, guarded):
    e0 = st["enemy"]["units"][0]
    a0 = st["ally"]["units"][0]
    a0["pos"] = {"x": max(0, e0["pos"]["x"] - 1), "y": e0["pos"]["y"]}
    # уводим прочих союзников подальше, чтобы враг метил в a0
    for k, a in enumerate(st["ally"]["units"][1:], 1):
        a["pos"] = {"x": 0, "y": 4}
guarded["ally"]["units"][0]["defending"] = True
hp_a0_before = base["ally"]["units"][0]["hp"]
b3._enemy_phase(base, [])
b3._enemy_phase(guarded, [])
dmg_plain = hp_a0_before - base["ally"]["units"][0]["hp"]
dmg_guard = hp_a0_before - guarded["ally"]["units"][0]["hp"]
assert dmg_plain > 0, "враг не ударил незащищённого союзника"
assert dmg_guard < dmg_plain, f"защита не снизила урон: guard={dmg_guard} plain={dmg_plain}"
print(f"enemy_ai: защита снижает урон ({dmg_guard} < {dmg_plain})  OK")

# 3) Полный бой с EV-ИИ завершается (жадный игрок)
st = b3.new_battle_state(ally, b3.gates_enemy_squad(2), "gates", {"floor": 2, "seed": 5})
guard = 0
while st["status"] == "active" and guard < 150:
    guard += 1
    st["crit_qte_used"] = True
    for ui, u in enumerate(st["ally"]["units"]):
        if not u["alive"]:
            continue
        alive_e = [i for i, e in enumerate(st["enemy"]["units"]) if e["alive"]]
        if not alive_e:
            break
        ti = min(alive_e, key=lambda i: g.chebyshev((u["pos"]["x"], u["pos"]["y"]),
                 (st["enemy"]["units"][i]["pos"]["x"], st["enemy"]["units"][i]["pos"]["y"])))
        r = b3.apply_action(st, {"type": "attack", "unit_i": ui, "target_i": ti})
        if r.get("ok"):
            continue
        tgt = st["enemy"]["units"][ti]
        reach = g.reachable(st["grid"], (u["pos"]["x"], u["pos"]["y"]), u["ap"],
                            b3._occupied(st, exclude=u))
        if reach:
            best = min(reach, key=lambda c: g.chebyshev(c, (tgt["pos"]["x"], tgt["pos"]["y"])))
            b3.apply_action(st, {"type": "move", "unit_i": ui, "cell": {"x": best[0], "y": best[1]}})
    if st["status"] == "active":
        b3.apply_action(st, {"type": "end_turn"})
assert st["status"] in ("won", "lost"), f"бой с EV-ИИ не завершился (guard={guard})"
print(f"enemy_ai: полный бой с EV-ИИ завершён '{st['status']}' за {guard} ходов  OK")
print("ALL ENEMY-AI TESTS PASSED")
