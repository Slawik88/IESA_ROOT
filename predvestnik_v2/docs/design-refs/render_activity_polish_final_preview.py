# -*- coding: utf-8 -*-
"""Референс финального дизайна графика активности (визуальный эталон полировки).

Этот дизайн внедрён в `bot/chat/activity_graph.py`; скрипт оставлен как
исполняемый снимок внешнего вида: те же параметры, тот же мок-набор данных
(с двумя пустыми днями), тот же шрифт из репозитория.

Запуск из корня проекта (шрифт берётся из bot/chat/assets/fonts):
    .venv\\Scripts\\python.exe docs/design-refs/render_activity_polish_final_preview.py

Результат: docs/design-refs/img/activity-polish-final.png (1000×560, из рендера 2×).
"""
from __future__ import annotations

import io
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from matplotlib import font_manager as fm
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.legend_handler import HandlerPatch
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Patch, PathPatch
from matplotlib.path import Path as MPath
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "img" / "activity-polish-final.png"
FONTS = HERE.parents[1] / "bot" / "chat" / "assets" / "fonts"
for fname in ("Onest-400.ttf", "Onest-500.ttf", "Onest-700.ttf"):
    fm.fontManager.addfont(str(FONTS / fname))

BG_TOP, BG_BOT = "#0c0f1d", "#08090f"
BAR, GOLD = "#8b6cf0", "#e8b54d"
GRID = (139 / 255, 108 / 255, 240 / 255, 0.12)
BAND = (1.0, 1.0, 1.0, 0.021)
BAND_SAMPLE = (1.0, 1.0, 1.0, 0.10)
BASELINE = "#3a4266"
AVG_C = "#6a73a6"
TITLE_C = "#f1f3fa"
VALUE_C = "#e9ecf7"
FOOT_C = "#d9dfee"
DATES_C = "#bac2da"
MUTED = "#8b94ae"
SEP_C = "#525a75"
GREEN = "#74c98a"
Y_LBL, X_LBL = "#7e88a4", "#98a2bd"

COUNTS = [400, 380, 260, 510, 0, 230, 130, 380, 660, 440, 360, 250, 390, 340, 305, 95,
          130, 355, 250, 155, 340, 0, 185, 160, 175, 155, 245, 290, 320, 495]
START = date(2026, 9, 19)
PREV_AVG = 240.0  # заглушка: у мока нет истории до 19.09

DPI = 200


def _rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _fmt(v: int) -> str:
    return f"{v:,}".replace(",", " ")


WHITE, BLACK = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)


def _bar_path(x0, x1, h, rx, ry):
    ry = min(ry, h * 0.38)
    verts = [(x0, 0), (x0, h - ry), (x0, h), (x0 + rx, h), (x1 - rx, h),
             (x1, h), (x1, h - ry), (x1, 0), (x0, 0)]
    codes = [MPath.MOVETO, MPath.LINETO, MPath.CURVE3, MPath.CURVE3, MPath.LINETO,
             MPath.CURVE3, MPath.CURVE3, MPath.LINETO, MPath.CLOSEPOLY]
    return MPath(verts, codes)


def _gradient(base, rows=512):
    top = _mix(base, WHITE, 0.20)
    bot = _mix(base, BLACK, 0.20)
    u = np.linspace(0.0, 1.0, rows)[:, None] ** 0.85
    img = np.zeros((rows, 1, 4))
    img[:, 0, 0:3] = np.array(bot) * (1 - u) + np.array(top) * u
    img[:, 0, 3] = 1.0
    return img


class _MiniBarSwatch(HandlerPatch):
    def create_artists(self, legend, orig_handle, xdescent, ydescent, width, height, fontsize, trans):
        bw = min(width, height * 0.5)
        bx = xdescent + (width - bw) / 2.0
        patch = FancyBboxPatch(
            (bx, ydescent), bw, height,
            boxstyle="round,pad=0,rounding_size=%.3f" % (min(bw, height) * 0.28),
            facecolor=orig_handle.get_facecolor(), edgecolor="none", transform=trans,
        )
        return [patch]


n = len(COUNTS)
top = max(COUNTS)
total = sum(COUNTS)
avg = total / n
avg_r = int(round(avg))
peak_i = COUNTS.index(top)
peak_date = (START + timedelta(days=peak_i)).strftime("%d.%m")
today_v = COUNTS[-1]
active = sum(1 for c in COUNTS if c > 0)
streak = 0
for c in reversed(COUNTS):
    if c > 0:
        streak += 1
    else:
        break
trend = avg / PREV_AVG - 1.0
trend_s, trend_c = f"+{trend * 100:.0f}%", GREEN
print(f"total={total} avg={avg:.1f}->{avg_r} peak={top}@{peak_date} today={today_v} "
      f"active={active} streak={streak} trend={trend_s}")

step = next(s for s in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000) if top <= s * 6)
headroom = max(step * 0.15, top * 0.05)
quant = step / 4
ceiling_f = quant * -(-(top + headroom) // quant)
ceiling = int(ceiling_f) if abs(ceiling_f - round(ceiling_f)) < 1e-9 else ceiling_f

fig = Figure(figsize=(10, 5.6), dpi=DPI)
FigureCanvasAgg(fig)

# фон: градиент + дизеринг
bg = fig.add_axes([0, 0, 1, 1], zorder=0)
bg.set_axis_off()
rows = 2048
v = np.linspace(0.0, 1.0, rows)[:, None]
bg_img = np.zeros((rows, 1, 3))
bg_img[:, 0, :] = np.array(_rgb(BG_TOP)) * (1 - v) + np.array(_rgb(BG_BOT)) * v
noise = np.random.default_rng(7).uniform(-2, 2, size=(rows, 1)) / 255.0
bg_img = np.clip(bg_img + noise[:, :, None], 0, 1)
bg.imshow(bg_img, extent=(0, 1, 0, 1), aspect="auto", interpolation="bilinear")

ax = fig.add_subplot(111, zorder=1)
ax.patch.set_visible(False)
fig.subplots_adjust(left=0.075, right=0.975, top=0.84, bottom=0.16)

# выходные — тихие полосы
for i in range(n):
    if (START + timedelta(days=i)).weekday() >= 5:
        ax.axvspan(i - 0.5, i + 0.5, color=BAND, zorder=0.5, linewidth=0)

# сетка, среднее, база
for spine in ax.spines.values():
    spine.set_visible(False)
ax.set_axisbelow(True)
for y in range(step, int(ceiling) + 1, step):
    ax.axhline(y, color=GRID, linewidth=0.75, linestyle=(0, (2, 4)), zorder=0.9)
ax.axhline(avg, color=AVG_C, linewidth=0.9, linestyle=(0, (3, 5)), zorder=1.05)

bl_x = np.linspace(-0.7, n - 0.25, 121)
t = np.linspace(0.0, 1.0, bl_x.size)
s = np.clip(np.minimum(t, 1 - t) / 0.08, 0, 1)
alpha = s * s * (3 - 2 * s)
rgb = _rgb(BASELINE)
segs = [[(bl_x[i], 0), (bl_x[i + 1], 0)] for i in range(bl_x.size - 1)]
ax.add_collection(LineCollection(
    segs, colors=[(*rgb, float(a)) for a in alpha[:-1]], linewidths=1.0, zorder=2.6))

# столбики
x_pad, rx, ry = 0.36, 0.19, 12.0
for i, h in enumerate(COUNTS):
    if h <= 0:
        continue
    base = _rgb(GOLD if i >= n - 7 else BAR)
    path = _bar_path(i - x_pad, i + x_pad, h, rx, ry)
    under = PathPatch(path, facecolor=_mix(base, WHITE, 0.10), edgecolor="none",
                      linewidth=0, transform=ax.transData, zorder=3)
    ax.add_patch(under)
    im = ax.imshow(_gradient(base), extent=(i - x_pad, i + x_pad, 0, h),
                   origin="lower", aspect="auto", interpolation="bilinear", zorder=3.1)
    im.set_clip_path(under)

# подпись пика
ax.text(peak_i, top + 7, str(top), ha="center", va="bottom", fontsize=8.5,
        color=MUTED, fontfamily="Onest", zorder=4)

# оси; последняя метка — «сегодня»
ax.set_ylim(0, ceiling)
ax.set_yticks([y for y in range(0, int(ceiling) + 1, step)])
ax.set_xlim(-0.7, n - 0.25)
ticks = list(range(0, n, 5))
if n - 1 not in ticks:
    ticks.append(n - 1)
ax.set_xticks(ticks)
xlabels = [(START + timedelta(days=i)).strftime("%d.%m") for i in ticks]
xlabels[-1] = "сегодня"
ax.set_xticklabels(xlabels)
ax.tick_params(axis="both", length=0, labelsize=9.5)
ax.tick_params(axis="y", colors=Y_LBL)
ax.tick_params(axis="x", colors=X_LBL)
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_fontfamily("Onest")

renderer = fig.canvas.get_renderer()
scale = 1.0 / (fig.get_figwidth() * fig.dpi)

# заголовок и двухтоновый подзаголовок
fig.text(0.075, 0.935, f"Активность за {n} дней", color=TITLE_C, fontsize=16,
         fontweight="bold", fontfamily="Onest", ha="left", va="top")
end = START + timedelta(days=n - 1)
t_dates = fig.text(0.075, 0.878, f"{START:%d.%m.%Y} — {end:%d.%m.%Y}",
                   color=DATES_C, fontsize=10, fontfamily="Onest",
                   fontweight="medium", ha="left", va="top")
w_px = t_dates.get_window_extent(renderer=renderer).width
fig.text(0.075 + w_px * scale + 0.007, 0.878, "· сообщений в день",
         color=MUTED, fontsize=10, fontfamily="Onest", fontweight="medium",
         ha="left", va="top")


def _row(items, y_base, *, start_x=None, end_x=None):
    texts, widths = [], []
    for label, color, fs, weight, _pad in items:
        tt = fig.text(0, y_base, label, color=color, fontsize=fs,
                      fontfamily="Onest", fontweight=weight, ha="left", va="baseline")
        texts.append(tt)
        widths.append(tt.get_window_extent(renderer=renderer).width)
    total_px = sum(w + p for (_, _, _, _, p), w in zip(items, widths))
    cur = (end_x - total_px * scale) if end_x is not None else start_x
    for (_, _, _, _, pad), w, tt in zip(items, widths, texts):
        tt.set_position((cur, y_base))
        cur += (w + pad) * scale


_row([("сегодня", MUTED, 9.5, "normal", 5),
      (str(today_v), VALUE_C, 12, "medium", 16),
      ("·", SEP_C, 9.5, "normal", 16),
      ("динамика", MUTED, 9.5, "normal", 5),
      (trend_s, trend_c, 12, "medium", 16),
      ("·", SEP_C, 9.5, "normal", 16),
      ("в среднем", MUTED, 9.5, "normal", 5),
      (f"{avg_r}/день", VALUE_C, 12, "medium", 16),
      ("·", SEP_C, 9.5, "normal", 16),
      ("лучший день", MUTED, 9.5, "normal", 5),
      (f"{peak_date} · {top}", VALUE_C, 12, "medium", 0)],
     y_base=0.913, end_x=0.975)

_row([("всего", MUTED, 9, "normal", 5),
      (_fmt(total), FOOT_C, 11, "medium", 13),
      ("·", SEP_C, 9, "normal", 13),
      ("активных дней", MUTED, 9, "normal", 5),
      (f"{active} из {n}", FOOT_C, 11, "medium", 13),
      ("·", SEP_C, 9, "normal", 13),
      ("серия", MUTED, 9, "normal", 5),
      (f"{streak} дней", FOOT_C, 11, "medium", 0)],
     y_base=0.058, start_x=0.075)

# легенда
legend = ax.legend(
    handles=[
        Patch(facecolor=GOLD, edgecolor="none", label="последняя неделя"),
        Line2D([], [], color=AVG_C, linestyle=(0, (2.2, 2.2)), linewidth=1.2, label="среднее"),
        Patch(facecolor=BAND_SAMPLE, edgecolor="none", label="выходные"),
    ],
    handler_map={Patch: _MiniBarSwatch()},
    loc="upper right", bbox_to_anchor=(0.975, 0.9), bbox_transform=fig.transFigure,
    frameon=False, fontsize=9.5, handlelength=1.35, handleheight=1.25,
    ncol=3, columnspacing=1.3, borderpad=0, labelspacing=0, handletextpad=0.5,
)
for text in legend.get_texts():
    text.set_color(MUTED)
    text.set_fontfamily("Onest")
    text.set_fontweight("medium")

buf = io.BytesIO()
fig.savefig(buf, format="png", facecolor=_rgb(BG_BOT))
img = Image.open(buf)
img.resize((1000, 560), Image.LANCZOS).save(OUT)
print("saved:", OUT)
