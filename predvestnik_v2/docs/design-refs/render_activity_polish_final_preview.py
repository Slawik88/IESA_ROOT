# -*- coding: utf-8 -*-
"""Референс дизайна графика активности (визуальный эталон, «телефон-первый»).

Рендерится прямо прод-модулем `bot/chat/activity_graph.py` на фиксированном
мок-наборе (сумма 1194, пик 91, сегодня 44), поэтому картинка не может
разойтись с тем, что уходит в Telegram. Полотно — 1120×700: это 2× от показа
на телефоне, подписи крупные и читаются без увеличения.

Запуск из корня проекта (шрифт берётся из bot/chat/assets/fonts):
    .venv\\Scripts\\python.exe docs/design-refs/render_activity_polish_final_preview.py

Результат: docs/design-refs/img/activity-polish-final.png (1120×700).
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "img" / "activity-polish-final.png"
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")

from bot.chat import activity_graph  # noqa: E402

# Демонстрационные данные, одинаковые у трёх тем; реальных игроков здесь нет.
COUNTS = [0, 24, 38, 11, 7, 60, 45, 14, 12, 35, 80, 42, 22, 9, 31,
          48, 61, 29, 42, 18, 34, 80, 91, 50, 12, 40, 72, 55, 88, 44]
START = date(2026, 9, 19)
PREV_AVG = 240.0   # заглушка: у мока нет истории до 19.09

png = activity_graph.render(COUNTS, START, theme="cosmos", prev_avg=PREV_AVG)
OUT.write_bytes(png)
print(f"saved: {OUT} ({len(png) // 1024} KB)")
for theme in activity_graph.THEMES:
    target = HERE / "img" / f"activity-{theme}-mobile.png"
    target.write_bytes(activity_graph.render(COUNTS, START, theme=theme, prev_avg=PREV_AVG))
    print(f"theme reference: {target.name}")
