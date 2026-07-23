"""Блок 13: две новые ачивки — 🎨 Модник (косметика) и 🏰 Покоритель Врат (PvE).
Проверяем схему в реестре и что метрики реально инкрементятся в коде
(cosmetics.py::buy и battle.py::_gates_reward), иначе ачивка «мёртвая»."""
import re
import sys
import pathlib

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.registry import ACHIEVEMENTS, ACHIEVEMENT_LEVEL_REWARDS

NEW = {
    "fashionista": "cosmetics_bought",
    "gate_conqueror": "gates_battles_won",
}

for ach_id, metric in NEW.items():
    a = ACHIEVEMENTS.get(ach_id)
    assert a, f"ачивка {ach_id} не найдена в реестре"
    assert a["metric"] == metric, f"{ach_id}: метрика {a['metric']} != {metric}"
    assert a.get("icon") and a.get("name"), f"{ach_id}: нет icon/name"
    assert len(a["thresholds"]) == 10, f"{ach_id}: ожидалось 10 порогов, {len(a['thresholds'])}"
    assert a["thresholds"] == sorted(a["thresholds"]), f"{ach_id}: пороги не возрастают"

# Награды уровней 1..10 существуют (новые ачивки используют общий стол наград)
for lvl in range(1, 11):
    assert lvl in ACHIEVEMENT_LEVEL_REWARDS, f"нет награды за уровень {lvl}"

# Метрики реально инкрементятся в коде (не только объявлены)
cos_src = (ROOT / "services" / "cosmetics.py").read_text(encoding="utf-8")
assert re.search(r'increment_metric\(\s*db\s*,\s*user_id\s*,\s*"cosmetics_bought"', cos_src), \
    "cosmetics.py::buy не инкрементит cosmetics_bought — ачивка Модник была бы мёртвой"

bat_src = (ROOT / "FastAPI" / "routers" / "battle.py").read_text(encoding="utf-8")
assert re.search(r'increment_metric\(\s*db\s*,\s*uid\s*,\s*"gates_battles_won"', bat_src), \
    "battle.py::_gates_reward не инкрементит gates_battles_won — ачивка мёртвая"

print("OK: 🎨 Модник (cosmetics_bought) и 🏰 Покоритель Врат (gates_battles_won) "
      "объявлены и реально инкрементятся в коде (покупка косметики / победа во Вратах)")
