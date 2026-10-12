#!/usr/bin/env python3
"""Хаб «Игры» (app.04.js): одинаковые строки, независимые загрузки, нет гонок, возврат из игр ведёт к хабу."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "FastAPI" / "static"
js = (ROOT / "app.04.js").read_text(encoding="utf-8")
hub = js[js.index("function loadActivitiesHub()"):js.index("function loadArena()")]

assert "v3-lead" in hub and "Игры временно недоступны" in hub, "пустое состояние «игры закрыты» пропало"
assert "_hubRow(g,chev)" in hub and "open.map" in hub, "все включённые игры рисуются одинаковыми строками"
assert "const [lead" not in hub, "лид-игры больше нет"
assert "++_hubSeq" in hub and "mine!==_hubSeq" in hub, "ответ устаревшей отрисовки должен отбрасываться"
assert ".catch(()=>null)" in hub, "сбой одной игры не должен ломать остальные"
assert "_hubTime(" in js and "best_elapsed_ms" in js, "у Сапёра лучший результат это время"
assert "Date.now()-(_hubAt" in js, "хаб не дёргает таблицу чаще раза в минуту"
assert "Ещё не играл" in js and "Результат пока недоступен" in js, "нет данных показываются явно"
assert "method:" not in hub, "хаб только читает"
for page in ("rhythm-v2.html", "minesweeper-v2.html"):
    assert 'href="/?startapp=games"' in (ROOT / page).read_text(encoding="utf-8"), f"{page}: «‹» ведёт не к хабу игр"
assert "'games'" in (ROOT / "app.02.js").read_text(encoding="utf-8"), "диплинк games"
print("OK: games hub rows, race guard, per-game failure isolation and back link")
