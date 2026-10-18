# -*- coding: utf-8 -*-
"""Референс дизайна графика активности (визуальный эталон, «телефон-первый»).

Рендерится прямо прод-модулем `bot/chat/activity_graph.py` на фиксированном
мок-наборе (два пустых дня, пик 660, сегодня 495), поэтому картинка не может
разойтись с тем, что уходит в Telegram. Полотно — 1120×960: это 2× от показа
на телефоне, подписи крупные и читаются без увеличения.

Запуск из корня проекта (шрифт берётся из bot/chat/assets/fonts):
    .venv\\Scripts\\python.exe docs/design-refs/render_activity_polish_final_preview.py

Результат: docs/design-refs/img/activity-polish-final.png (1120×960).
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

# Мок: 19.09–18.10.2026, два пустых дня (23.09 и 10.10), пик 660, сегодня 495.
COUNTS = [400, 380, 260, 510, 0, 230, 130, 380, 660, 440, 360, 250, 390, 340, 305, 95,
          130, 355, 250, 155, 340, 0, 185, 160, 175, 155, 245, 290, 320, 495]
START = date(2026, 9, 19)
PREV_AVG = 240.0   # заглушка: у мока нет истории до 19.09

png = activity_graph.render(COUNTS, START, theme="cosmos", prev_avg=PREV_AVG)
OUT.write_bytes(png)
print(f"saved: {OUT} ({len(png) // 1024} KB)")
