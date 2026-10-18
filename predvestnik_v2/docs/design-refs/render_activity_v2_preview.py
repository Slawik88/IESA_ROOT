# -*- coding: utf-8 -*-
"""Превью v2 графика «Активность за 30 дней» — референс для косметической волны.

ЧТО ПОКАЗЫВАЕТ (улучшения против текущего v1):
  * KPI-блок справа: всего сообщений, в среднем в день и динамика неделя-к-неделе
    (▲ зелёный / ▼ красный; если прошлой недели нет — строку прятать);
  * линия среднего за 7 дней поверх столбиков — тренд без дневного шума;
  * подпись пика («пик · 660») над лучшим днём (+10% воздуха сверху под неё);
  * последний столбик — «сегодня» вместо даты, чуть светлее (день неполный);
  * мягкая зона последней недели с подписью у столбиков вместо легенды-квадратика;
  * лёгкий блик на столбиках (градиент), пунктирная сетка без верхней линии.

КУДА ВНЕДРЯТЬ: bot/chat/activity_graph.py — новые цвета/подписи в THEMES
(pos/neg/zone_label/today), расчёт KPI и новые слои в render(); сигнатура
render(counts, start) не меняется, БД и кэш не трогаются.

ЗАПУСК: python docs/design-refs/render_activity_v2_preview.py
(рисует img/activity-v2-preview.png на реалистичных моках; не прод-код).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.ticker import MultipleLocator

OUT = Path(__file__).resolve().parent / "img" / "activity-v2-preview.png"

BG = "#0a0c16"
BAR = "#8b6cf0"
GOLD = "#e8b54d"
GOLD_TODAY = "#f6d98a"
GRID = (139 / 255, 108 / 255, 240 / 255, 0.12)
LABEL = "#9aa3bc"
TITLE = "#f1f3fa"
LINE = "#c7cdf4"
POS = "#4cc38a"
NEG = "#f2555a"

# Моки, повторяющие форму текущего графика из отчёта (19.09 — 18.10).
COUNTS = [400, 380, 260, 510, 55, 230, 130, 380, 660, 440, 360, 250, 390, 340, 305, 95,
          130, 355, 250, 155, 340, 85, 185, 160, 175, 155, 245, 290, 320, 495]
START = date(2026, 9, 19)

n = len(COUNTS)
top = max(COUNTS)
step = next(s for s in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000) if top <= s * 6)
ceiling = step * math.ceil(top * 1.10 / step)   # +10% воздуха под подпись пика

fig = Figure(figsize=(10, 5.6), dpi=100)
FigureCanvasAgg(fig)
ax = fig.add_subplot(111)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
fig.subplots_adjust(left=0.075, right=0.975, top=0.84, bottom=0.16)

# Мягкая зона последней недели — заменяет легенду-квадратик.
ax.axvspan(n - 7 - 0.5, n - 0.5, color=GOLD, alpha=0.045, zorder=0.8)

colors = [GOLD if i >= n - 7 else BAR for i in range(n)]
colors[-1] = GOLD_TODAY   # сегодня — чуть светлее
ax.bar(range(n), COUNTS, width=0.82, color=colors, linewidth=0, zorder=3)

# Лёгкий вертикальный блик на столбиках: белый сверху, тень снизу.
u = np.linspace(0.0, 1.0, 256)
alpha = np.where(u > 0.5, (u - 0.5) * 2 * 0.20, (0.5 - u) * 2 * 0.16)
sheen = np.zeros((256, 1, 4))
sheen[:, 0, 3] = alpha
sheen[:, 0, :3] = np.where(u > 0.5, 1.0, 0.0)[:, None]
for i, h in enumerate(COUNTS):
    if h <= 0:
        continue
    im = ax.imshow(sheen, extent=(i - 0.41, i + 0.41, 0, h), origin="lower",
                   aspect="auto", interpolation="bilinear", zorder=3.4)
    im.set_clip_path(Rectangle((i - 0.41, 0), 0.82, h, transform=ax.transData))

# Линия среднего за 7 дней — форма важнее дневного шума.
ma = [sum(COUNTS[max(0, i - 6): i + 1]) / len(COUNTS[max(0, i - 6): i + 1]) for i in range(n)]
ax.plot(range(n), ma, color=LINE, alpha=0.5, linewidth=1.6, zorder=4, solid_capstyle="round")

for spine in ax.spines.values():
    spine.set_visible(False)
ax.set_axisbelow(True)
ax.grid(axis="y", color=GRID, linewidth=0.7, linestyle=(0, (4, 4)))
ax.tick_params(axis="both", colors=LABEL, labelsize=8, length=0)
ax.yaxis.set_major_locator(MultipleLocator(step))
ax.set_ylim(0, ceiling)
ax.set_yticks([v for v in range(0, ceiling, step)])   # без линии на самом потолке
ax.set_xlim(-0.7, n - 0.3)

ticks = list(range(0, n, 5))
if n - 1 not in ticks:
    ticks.append(n - 1)
ax.set_xticks(ticks)
ax.set_xticklabels(["сегодня" if i == n - 1 else (START + timedelta(days=i)).strftime("%d.%m")
                    for i in ticks])

# Подпись пика.
pi = COUNTS.index(top)
if pi >= n - 7:
    ax.annotate(f"пик · {top}", (pi, top), textcoords="offset points", xytext=(-12, 5),
                ha="right", color=LABEL, fontsize=8, zorder=5)
else:
    ax.annotate(f"пик · {top}", (pi, top), textcoords="offset points", xytext=(0, 5),
                ha="center", color=LABEL, fontsize=8, zorder=5)

# Подпись зоны недели — внутри графика, над золотыми столбиками.
ax.text((n - 7 - 0.5 + n - 0.5) / 2, 0.72, "последняя неделя",
        transform=ax.get_xaxis_transform(), ha="center", va="top",
        color=GOLD, alpha=0.75, fontsize=8)

fig.text(0.075, 0.935, f"Активность за {n} дней", color=TITLE, fontsize=14.5,
         fontweight="bold", ha="left", va="top")
end = START + timedelta(days=n - 1)
fig.text(0.075, 0.878,
         f"{START.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')} · сообщений в день"
         " · тонкая линия — среднее за 7 дней",
         color=LABEL, fontsize=9, ha="left", va="top")

# KPI-блок справа: цифра-вывод вместо «просто столбиков».
total = sum(COUNTS)
avg = round(total / n)
last7 = sum(COUNTS[-7:])
prev7 = sum(COUNTS[-14:-7])
fig.text(0.975, 0.930, f"{total:,}".replace(",", " "), color=TITLE, fontsize=20,
         fontweight="bold", ha="right", va="top")
fig.text(0.975, 0.878, f"сообщений · по {avg} в день", color=LABEL, fontsize=9,
         ha="right", va="top")
if prev7:   # нет прошлой недели — строку сравнения просто не рисуем
    pct = round((last7 - prev7) / prev7 * 100)
    if pct > 0:
        delta, dcol = f"▲ +{pct}% к прошлой неделе", POS
    elif pct < 0:
        delta, dcol = f"▼ -{abs(pct)}% к прошлой неделе", NEG
    else:
        delta, dcol = "→ как на прошлой неделе", LABEL
    fig.text(0.975, 0.850, delta, color=dcol, fontsize=9.5, ha="right", va="top")

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("wb") as fh:
    fig.savefig(fh, format="png", facecolor=fig.get_facecolor())
print("saved:", OUT, "| total:", total, "| avg:", avg, "| wow:", round((last7 - prev7) / prev7 * 100))
