"""Block 6 (первый фикс): таунт танка (intercept_all) теперь РЕАЛЬНО тянет удар
вражеского ИИ. Раньше intercept_all читался только в _pick_target (ульты союзника),
а _best_enemy_plan его игнорировал — таунт был мёртвым кодом.

Сценарий: два союзника вплотную к врагу (оба достижимы+в LoS). Смотрим естественную
цель врага, затем вешаем таунт на ДРУГОГО достижимого союзника — враг обязан
переключиться на него."""
import sys
import pathlib

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from services import battle3 as b3
from core.units import UNITS

ally = [{"unit_id": uid, "level": 8, "slot": i} for i, uid in enumerate(list(UNITS)[:3])]
st = b3.new_battle_state(ally, b3.gates_enemy_squad(2), "gates", {"floor": 2, "seed": 7})

e0 = st["enemy"]["units"][0]
ex, ey = e0["pos"]["x"], e0["pos"]["y"]

# Два союзника вплотную к врагу слева (враги спавнятся справа) — оба chebyshev 1,
# достижимы и в LoS. Прочих уводим далеко, чтобы не мешали.
by = ey - 1 if ey - 1 >= 0 else ey + 1
st["ally"]["units"][0]["pos"] = {"x": max(0, ex - 1), "y": ey}
st["ally"]["units"][1]["pos"] = {"x": max(0, ex - 1), "y": by}
for a in st["ally"]["units"][2:]:
    a["pos"] = {"x": 0, "y": 6}
for a in st["ally"]["units"]:
    a.setdefault("statuses", {}).pop("intercept_all", None)

# 1) Естественная цель врага (без таунта)
plan_no = b3._best_enemy_plan(st, 0)
assert plan_no and plan_no["kind"] == "attack", f"враг не нашёл цель: {plan_no}"
natural = plan_no["target"]
assert natural in (0, 1), f"естественная цель вне двух достижимых: {natural}"
print(f"taunt: без таунта естественная цель врага — idx{natural}  OK")

# 2) Вешаем таунт на ДРУГОГО достижимого союзника → враг обязан переключиться
taunter = 1 if natural == 0 else 0
st["ally"]["units"][taunter]["statuses"]["intercept_all"] = True
plan_taunt = b3._best_enemy_plan(st, 0)
assert plan_taunt and plan_taunt["kind"] == "attack", f"нет цели под таунтом: {plan_taunt}"
assert plan_taunt["target"] == taunter, (
    f"таунт не сработал: должен бить таунтера idx{taunter}, а метит в {plan_taunt['target']}")
assert taunter != natural, "тест вырожден: таунтер совпал с естественной целью"
print(f"taunt: под таунтом враг переключился с idx{natural} на таунтера idx{taunter}  OK")

# 3) Таунтер ВНЕ досягаемости — таунт не должен ломать выбор (обычная цель)
st["ally"]["units"][taunter]["statuses"]["intercept_all"] = True
st["ally"]["units"][taunter]["pos"] = {"x": 0, "y": 6}   # увели таунтера далеко
plan_far = b3._best_enemy_plan(st, 0)
assert plan_far and plan_far["kind"] in ("attack", "defend"), f"враг завис: {plan_far}"
if plan_far["kind"] == "attack":
    assert plan_far["target"] != taunter, "враг ломанулся к недостижимому таунтеру"
print("taunt: недостижимый таунтер не ломает выбор врага  OK")

print("ALL TAUNT TESTS PASSED — intercept_all больше не мёртвый код")
