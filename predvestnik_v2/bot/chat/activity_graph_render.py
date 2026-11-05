"""Рисование графика активности — отдельно от бота, чтобы matplotlib жил вне его процесса.

Зачем: matplotlib с numpy держат в памяти 60–80 МиБ, а контейнер ботов — всего 512 МБ на двух ботов и мини-приложение
(в обычное время занято 79–85 %). Бот (bot/chat/activity_graph.py) запускает этот файл как короткоживущий процесс
`python activity_graph_render.py --worker`: он рисует картинки по запросам и сам завершается, когда запросов нет, —
память возвращается системе. Модуль намеренно ничего не импортирует из бота (aiogram, база, настройки): процесс должен
стоить только matplotlib.

Протокол по stdin/stdout: запрос — одна строка JSON {"counts", "start", "today", "style"};
ответ — строка «OK <байт>» и PNG либо «ERR <причина>». EOF на stdin — завершение.
"""
from __future__ import annotations

import io
import json
import math
import sys
import threading
from datetime import date, timedelta
from pathlib import Path

DPI = 200                       # 1120×700, компактная карточка для телефона
FIG_W, FIG_H = 5.6, 3.5         # дюймы: ширина подобрана так, чтобы текст читался с телефона

# Пропорции полотна: поля subplots_adjust (левое — с запасом под пятизначные
# подписи оси) и левый край текстового блока шапки. Нужны, чтобы радиусы
# скругления столбиков оставались «на глаз» одинаковыми при любом масштабе
# данных (px считаем от размера полотна, а не от значений оси).
X_TEXT = 0.08
_LEFT, _RIGHT = 0.105, 0.975
_TOP, _BOTTOM = 0.68, 0.14
_PLOT_W_PX = (_RIGHT - _LEFT) * FIG_W * DPI
_PLOT_H_PX = (_TOP - _BOTTOM) * FIG_H * DPI

_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_FILES = ("Onest-400.ttf", "Onest-500.ttf", "Onest-700.ttf")
_FAMILY: str | None = None      # None → шрифт по умолчанию (файлов нет / addfont упал)
_font_lock = threading.Lock()
_fonts_done = False


def _ensure_fonts() -> None:
    """Зарегистрировать Onest один раз на процесс. Нет файлов — молча мимо."""
    global _FAMILY, _fonts_done
    if _fonts_done:
        return
    with _font_lock:
        if _fonts_done:
            return
        try:
            if all((_FONT_DIR / name).exists() for name in _FONT_FILES):
                from matplotlib import font_manager
                for name in _FONT_FILES:
                    font_manager.fontManager.addfont(str(_FONT_DIR / name))
                _FAMILY = "Onest"
        except Exception:      # noqa: BLE001 — шрифт не повод не рисовать график
            _FAMILY = None
        _fonts_done = True


def _ff(weight: str) -> dict:
    """Аргументы шрифта для Text: фирменный, если он доступен."""
    if _FAMILY:
        return {"fontfamily": _FAMILY, "fontweight": weight}
    return {} if weight == "normal" else {"fontweight": weight}


def _step(top: int) -> int:
    """Шаг сетки: около шести подписей по вертикали."""
    for step in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000):
        if top <= step * 6:
            return step
    scale = 10000
    while top > scale * 6:
        scale *= 10
    return next(value for value in (scale // 5, scale // 2, scale) if top <= value * 6)


def _ceiling(top: int, step: int) -> float:
    """Потолок оси: максимум + воздух (5–15%), округлённый до четверти шага.

    Так столбики заполняют полотно, а пустоты сверху не остаётся: при
    максимуме 660 и шаге 200 потолок выходит 700, а не 800.
    """
    if top <= 0:
        return float(step)
    headroom = max(step * 0.15, top * 0.05)
    quant = step / 4
    value = quant * math.ceil((top + headroom) / quant)
    return int(value) if abs(value - round(value)) < 1e-9 else value


def _rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _fmt(value: int) -> str:
    """8385 → «8 385» (узкий пробел-разделитель разрядов)."""
    return f"{value:,}".replace(",", " ")


def _bar_path(x0, x1, height, rx, ry):
    """Контур столбика: низ прямой, верхушка со скруглением."""
    from matplotlib.path import Path as MPath
    ry = min(ry, height * 0.38)
    verts = [(x0, 0), (x0, height - ry), (x0, height), (x0 + rx, height),
             (x1 - rx, height), (x1, height), (x1, height - ry), (x1, 0), (x0, 0)]
    codes = [MPath.MOVETO, MPath.LINETO, MPath.CURVE3, MPath.CURVE3, MPath.LINETO,
             MPath.CURVE3, MPath.CURVE3, MPath.LINETO, MPath.CLOSEPOLY]
    return MPath(verts, codes)


def _gradient(base, rows=512):
    """Вертикальный градиент столбика: светлее к верхушке (гамма-кривая)."""
    import numpy as np
    top = _mix(base, (1.0, 1.0, 1.0), 0.20)
    bot = _mix(base, (0.0, 0.0, 0.0), 0.20)
    u = np.linspace(0.0, 1.0, rows)[:, None] ** 0.85
    img = np.zeros((rows, 1, 4))
    img[:, 0, 0:3] = np.array(bot) * (1 - u) + np.array(top) * u
    img[:, 0, 3] = 1.0
    return img


def render_png(counts: list[int], start: date, today: date, st: dict) -> bytes:
    """Phone-first PNG: daily bars, today's count and one period total.

    st — готовая палитра темы (activity_graph.THEMES[...]); today — местная дата для подписи «сегодня».
    No pyplot/global figure state.
    """
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.collections import LineCollection
    from matplotlib.colors import to_rgba
    from matplotlib.figure import Figure
    from matplotlib.patches import PathPatch

    _ensure_fonts()
    n = len(counts)
    top = max(counts, default=0)
    step = _step(top) * 2
    ceill = _ceiling(top, step)
    total = sum(counts)
    today_v = counts[-1] if n else 0
    fig = Figure(figsize=(FIG_W, FIG_H), dpi=DPI)
    FigureCanvasAgg(fig)
    fig.patch.set_facecolor(st["bg"])

    bg = fig.add_axes([0, 0, 1, 1], zorder=0)
    bg.set_axis_off()
    rows = 1024
    v = np.linspace(0.0, 1.0, rows)[:, None]
    bg_img = np.zeros((rows, 1, 3))
    bg_img[:, 0, :] = np.array(_rgb(st["bg_top"])) * (1-v) + np.array(_rgb(st["bg_bot"])) * v
    noise = np.random.default_rng(7).uniform(-2, 2, size=(rows, 1)) / 255.0
    bg.imshow(np.clip(bg_img + noise[:, :, None], 0, 1), extent=(0, 1, 0, 1),
              aspect="auto", interpolation="bilinear")

    # Two visual anchors: title + period total at left, today's number at right.
    # No legend, date paragraph, secondary KPIs or text below the plot.
    fig.text(X_TEXT, .94, "Активность", color=st["title"], fontsize=19,
             ha="left", va="top", **_ff("bold"))
    fig.text(X_TEXT, .83, f"{_fmt(total)} сообщений · {n} дней", color=st["dates"],
             fontsize=12.5, ha="left", va="top", **_ff("medium"))
    fig.text(.95, .945, _fmt(today_v), color=st.get("headline", st["bar_last"]), fontsize=28 if today_v < 1_000_000 else 23,
             ha="right", va="top", **_ff("bold"))
    fig.text(.95, .79, "сегодня", color=st["dates"], fontsize=12.5,
             ha="right", va="top", **_ff("medium"))

    ax = fig.add_subplot(111, zorder=1)
    ax.patch.set_visible(False)
    fig.subplots_adjust(left=_LEFT, right=_RIGHT, top=_TOP, bottom=_BOTTOM)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for y in range(step, int(ceill)+1, step):
        ax.axhline(y, color=st["grid"], linewidth=.6, linestyle=(0, (2, 4)), zorder=.9)
    br, bg_c, bb = to_rgba(st["baseline"])[:3]
    bl_x = np.linspace(-.7, n-.25, 121)
    t = np.linspace(0.0, 1.0, bl_x.size)
    fade = np.clip(np.minimum(t, 1-t)/.08, 0, 1)
    alpha = fade*fade*(3-2*fade)
    ax.add_collection(LineCollection(
        [[(bl_x[i], 0), (bl_x[i+1], 0)] for i in range(bl_x.size-1)],
        colors=[(br, bg_c, bb, float(a)) for a in alpha[:-1]], linewidths=1, zorder=2.6))

    x_pad = .34
    rx = 9.0 * (n+.45) / _PLOT_W_PX
    ry = 9.0 * float(ceill) / _PLOT_H_PX
    for i, height in enumerate(counts):
        if height <= 0:
            continue
        # One highlighted day, corresponding to the single headline KPI.
        base = _rgb(st["bar_last"] if i == n-1 else st["bar"])
        path = _bar_path(i-x_pad, i+x_pad, height, rx, ry)
        under = PathPatch(path, facecolor=_mix(base, (1., 1., 1.), .10),
                          edgecolor="none", linewidth=0, transform=ax.transData, zorder=3)
        ax.add_patch(under)
        im = ax.imshow(_gradient(base), extent=(i-x_pad, i+x_pad, 0, height),
                       origin="lower", aspect="auto", interpolation="bilinear", zorder=3.1)
        im.set_clip_path(under)

    ax.set_ylim(0, ceill)
    yticks = list(range(0, int(ceill)+1, step))
    ax.set_yticks(yticks)
    ax.set_yticklabels([_fmt(y) for y in yticks])
    ax.set_xlim(-.7, max(.25, n-.25))
    ticks = sorted({0, max(0, (n-1)//2), max(0, n-1)})
    ax.set_xticks(ticks)
    labels = [(start+timedelta(days=i)).strftime("%d.%m") for i in ticks]
    if n and start+timedelta(days=n-1) == today:
        labels[-1] = "сегодня"
    ax.set_xticklabels(labels)
    ax.tick_params(axis="both", length=0, labelsize=12)
    ax.tick_params(axis="y", colors=st["y_label"], pad=7)
    ax.tick_params(axis="x", colors=st["dates"], pad=9)
    ax.get_xticklabels()[-1].set_ha("right")
    if _FAMILY:
        for label in ax.get_xticklabels()+ax.get_yticklabels():
            label.set_fontfamily(_FAMILY)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=to_rgba(st["bg_bot"]))
    return buf.getvalue()


def _serve() -> None:
    """Цикл процесса-рисовальщика: строка запроса → PNG, пока бот не закроет stdin."""
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    while True:
        line = stdin.readline()
        if not line:
            return
        try:
            req = json.loads(line)
            png = render_png([int(c) for c in req["counts"]], date.fromisoformat(req["start"]),
                             date.fromisoformat(req["today"]), req["style"])
            stdout.write(b"OK %d\n" % len(png) + png)
        except Exception as exc:      # noqa: BLE001 — любая ошибка рисования уходит боту текстом, цикл живёт дальше
            stdout.write(("ERR %s\n" % type(exc).__name__).encode())
        stdout.flush()


if __name__ == "__main__":
    if "--worker" in sys.argv[1:]:
        _serve()
