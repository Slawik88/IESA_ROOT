"""B1 smoke: жадный игрок (move→attack, крит форсим OFF) доигрывает бой. Временный."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from services import battle3 as b3
from services import battle_grid as g
from core.units import UNITS

ally = [{"unit_id": uid, "level": 10, "slot": i} for i, uid in enumerate(list(UNITS)[:3])]
st = b3.new_battle_state(ally, b3.gates_enemy_squad(1), "gates", {"floor": 1, "seed": 7})

def nearest_enemy(u):
    ep = [(i, e) for i, e in enumerate(st["enemy"]["units"]) if e["alive"]]
    if not ep:
        return None
    return min(ep, key=lambda ie: g.chebyshev((u["pos"]["x"], u["pos"]["y"]),
                                              (ie[1]["pos"]["x"], ie[1]["pos"]["y"])))[0]

guard = 0
while st["status"] == "active" and guard < 80:
    guard += 1
    st["crit_qte_used"] = True   # крит-путь обходим (он завязан на QTE, чинится в B2)
    acted = False
    for ui, u in enumerate(st["ally"]["units"]):
        if not u["alive"]:
            continue
        ti = nearest_enemy(u)
        if ti is None:
            break
        # атакуем если можем
        r = b3.apply_action(st, {"type": "attack", "unit_i": ui, "target_i": ti})
        if r.get("ok"):
            acted = True
            assert u["ap"] >= 0, "AP ушёл в минус"
            continue
        # иначе двигаемся к врагу на достижимую клетку, ближайшую к цели
        tgt = st["enemy"]["units"][ti]
        reach = g.reachable(st["grid"], (u["pos"]["x"], u["pos"]["y"]), u["ap"],
                            b3._occupied(st, exclude=u))
        if reach:
            best = min(reach, key=lambda c: g.chebyshev(c, (tgt["pos"]["x"], tgt["pos"]["y"])))
            b3.apply_action(st, {"type": "move", "unit_i": ui,
                                 "cell": {"x": best[0], "y": best[1]}})
            assert u["ap"] >= 0, "AP ушёл в минус после хода"
            acted = True
    res = b3.apply_action(st, {"type": "end_turn"})
    assert "phase" in res, "end_turn без phase"

assert st["status"] in ("won", "lost"), f"бой не завершился (guard={guard})"
print(f"action_b1: бой завершён '{st['status']}' за {guard} ходов, AP-инвариант держится  OK")
