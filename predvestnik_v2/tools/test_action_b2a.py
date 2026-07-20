"""B2a smoke: полный бой с РАЗРЕШЁННЫМ крит-QTE и ультой на новом движке. Временный."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from services import battle3 as b3
from services import battle_grid as g
from core.units import UNITS

ally = [{"unit_id": uid, "level": 10, "slot": i} for i, uid in enumerate(list(UNITS)[:3])]
st = b3.new_battle_state(ally, b3.gates_enemy_squad(1), "gates", {"floor": 1, "seed": 7})
# рунных полей больше нет
for k in ("deck", "discard", "hand", "hand_size_next"):
    assert k not in st, f"рунное поле {k} осталось в state"
assert "focus" not in st["ally"], "focus остался в ally"

def nearest(u):
    ep = [(i, e) for i, e in enumerate(st["enemy"]["units"]) if e["alive"]]
    if not ep:
        return None
    return min(ep, key=lambda ie: g.chebyshev((u["pos"]["x"], u["pos"]["y"]),
                                              (ie[1]["pos"]["x"], ie[1]["pos"]["y"])))[0]

guard = 0
while st["status"] == "active" and guard < 120:
    guard += 1
    for ui, u in enumerate(st["ally"]["units"]):
        if not u["alive"]:
            continue
        ti = nearest(u)
        if ti is None:
            break
        r = b3.apply_action(st, {"type": "attack", "unit_i": ui, "target_i": ti})
        if r.get("phase") == "qte":               # крит выпал — подтверждаем тапом
            r = b3.resume_qte(st, 100)
            assert r.get("phase") in ("resolved", "over"), f"resume_qte вернул {r}"
            continue
        if r.get("ok"):
            continue
        tgt = st["enemy"]["units"][ti]
        reach = g.reachable(st["grid"], (u["pos"]["x"], u["pos"]["y"]), u["ap"],
                            b3._occupied(st, exclude=u))
        if reach:
            best = min(reach, key=lambda c: g.chebyshev(c, (tgt["pos"]["x"], tgt["pos"]["y"])))
            b3.apply_action(st, {"type": "move", "unit_i": ui,
                                 "cell": {"x": best[0], "y": best[1]}})
    # если ярость полна — пробуем ульту первого живого юнита
    if st["ally"]["rage"] >= 100 and st["status"] == "active":
        first = next((i for i, u in enumerate(st["ally"]["units"]) if u["alive"]), None)
        if first is not None:
            b3.request_ult(st, first)
            rr = b3.resume_qte(st, 100)
            assert rr.get("phase") in ("resolved", "over"), f"ульта вернула {rr}"
    if st["status"] == "active":
        b3.apply_action(st, {"type": "end_turn"})

assert st["status"] in ("won", "lost"), f"бой не завершился (guard={guard})"
print(f"action_b2a: бой '{st['status']}' за {guard} ходов, крит-QTE+ульта на новом движке  OK")
