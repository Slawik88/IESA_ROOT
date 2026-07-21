"""Онбординг боя (2026-07-21): лента битов хода врага.

Проверяет, что end_turn отдаёт упорядоченный timeline с валидными битами (move —
from/to; attack/aoe/ult — hits-срез), что лента не утекает в сохраняемый state, и
что за несколько раундов враг реально и двигается, и бьёт."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from services import battle3 as b3
from core.constants import GRID_W, GRID_H
from core.units import UNITS

ALLOWED = {"move", "attack", "defend", "aoe", "ult", "skip"}

ally = [{"unit_id": uid, "level": 1, "slot": i}
        for i, uid in enumerate(list(UNITS)[:3])]
enemies = b3.gates_enemy_squad(1)
st = b3.new_battle_state(ally, enemies, "gates", {"floor": 1, "seed": 42})

# Реалистичная стычка: чистим средний ряд и ставим бойца в зону, куда враг ДОЛЖЕН
# сначала шагнуть, а потом ударить (иначе EV-ИИ обороняется на месте — враг ходит
# только ради атаки). Так лента гарантированно содержит и move-, и attack-биты.
st["grid"][2] = [0] * GRID_W
st["ally"]["units"][0]["pos"] = {"x": 3, "y": 2}
st["enemy"]["units"][0]["pos"] = {"x": 6, "y": 2}

kinds_seen = set()
nonempty_rounds = 0
for _round in range(8):
    res = b3.apply_action(st, {"type": "end_turn"})
    assert res.get("ok"), f"end_turn отклонён: {res}"
    tl = res.get("timeline")
    assert isinstance(tl, list), "timeline должен быть списком"
    assert "timeline_round" not in st, "лента не должна утечь в сохраняемый state"
    if tl:
        nonempty_rounds += 1
    for beat in tl:
        assert beat["actor"]["side"] == "enemy", "актор бита — враг"
        assert beat["kind"] in ALLOWED, f"недопустимый kind: {beat['kind']}"
        kinds_seen.add(beat["kind"])
        if beat["kind"] == "move":
            f, t = beat["from"], beat["to"]
            assert f and t, "move-бит без from/to"
            assert 0 <= t["x"] < GRID_W and 0 <= t["y"] < GRID_H, "to вне поля"
            assert (f["x"], f["y"]) != (t["x"], t["y"]), "move-бит без реального сдвига"
        if beat["kind"] in ("attack", "aoe", "ult"):
            assert isinstance(beat.get("hits"), list), f"{beat['kind']} без hits-среза"
    if st.get("status") in ("won", "lost"):
        break

assert nonempty_rounds >= 1, "ни одного непустого таймлайна за 8 раундов"
assert "move" in kinds_seen, "враг ни разу не двигался"
assert "attack" in kinds_seen, "враг ни разу не атаковал"
print(f"battle_timeline: биты={sorted(kinds_seen)} непустых_раундов={nonempty_rounds}  OK")
