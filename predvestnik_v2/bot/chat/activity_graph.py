"""График активности игрока по дням — картинка вверху карточки «бот я / бот кто».

База: matplotlib рисует PNG. Тема по умолчанию — «Космос» (ночь, фиолетовые
столбики со скруглением, последняя неделя золотом); всё оформление живёт в
THEMES, чтобы косметику можно было менять, не трогая логику.

Что на картинке:
  * столбики по дням (окно DAYS), последняя неделя — золотом, выходные —
    тихими полосами (объяснены в легенде);
  * линия среднего за период — ориентир «выше/ниже нормы»;
  * две строки цифр вверху: сегодня · динамика · в среднем / лучший день;
    внизу: всего · активных дней · текущая серия;
  * масштаб оси подстраивается под данные (без пустоты сверху).

Размер полотна рассчитан на телефон: фото в чате показывается шириной около
560 dp, поэтому canvas 1120×960 (figsize 5.6×4.8 при DPI 200) — это «2×» и
для резкости краёв, и для крупных подписей: текст на картинке читается с
телефона без увеличения.

Скорость: рендер идёт в отдельном потоке, результат кэшируется на день
(повторные «бот я» в тот же день картинку не перерисовывают). matplotlib и
фирменный шрифт прогреваются один раз при старте бота (prewarm).

Данные: daily_counts тянет два окна одним запросом — текущие DAYS дней для
графика и предыдущие DAYS для «динамики». Все остальные цифры считаются из
уже полученного списка, без дополнительных запросов к базе.

Шрифт: Onest (лицензия OFL, файлы в bot/chat/assets/fonts). Если файлов нет —
тихо падаем на шрифт matplotlib по умолчанию, картинка всё равно рисуется.
"""
from __future__ import annotations

import asyncio
import io
import math
import threading
from datetime import date, timedelta
from pathlib import Path

from bot.chat.tracking import local_now

DAYS = 30                       # окно графика, дней
DEFAULT_THEME = "cosmos"
MAX_CACHE = 256                 # картинок в памяти; ключ включает день, старые вытесняются
DPI = 200                       # полотно 1120×960: 2× от показа на телефоне, ~140 КБ на PNG
FIG_W, FIG_H = 5.6, 4.8         # дюймы: ширина подобрана так, чтобы текст читался с телефона

# Пропорции полотна: поля subplots_adjust (левое — с запасом под пятизначные
# подписи оси) и левый край текстового блока шапки. Нужны, чтобы радиусы
# скругления столбиков оставались «на глаз» одинаковыми при любом масштабе
# данных (px считаем от размера полотна, а не от значений оси).
X_TEXT = 0.08
_LEFT, _RIGHT = 0.105, 0.975
_TOP, _BOTTOM = 0.635, 0.175
_PLOT_W_PX = (_RIGHT - _LEFT) * FIG_W * DPI
_PLOT_H_PX = (_TOP - _BOTTOM) * FIG_H * DPI

_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_FILES = ("Onest-400.ttf", "Onest-500.ttf", "Onest-700.ttf")
_FAMILY: str | None = None      # None → шрифт по умолчанию (файлов нет / addfont упал)
_font_lock = threading.Lock()
_fonts_done = False

_LEGEND_AVG = "среднее"
_LEGEND_WEEKEND = "выходные"

# Оформление: цвета и подписи. Косметику правим здесь, не трогая рендер.
# Ключи: bg_* — фон-градиент, bar/bar_last — столбики, grid/baseline/avg —
# линии, band* — подсветка выходных, title/value/foot/dates/label/sep/y_label/
# x_label — текст, green/red — динамика, legend — подпись золотой недели.
THEMES = {
    "cosmos": {
        "bg": "#0a0c16",
        "bg_top": "#0c0f1d",
        "bg_bot": "#08090f",
        "bar": "#8b6cf0",
        "bar_last": "#e8b54d",
        "grid": (139 / 255, 108 / 255, 240 / 255, 0.12),
        "baseline": "#3a4266",
        "avg": "#6a73a6",
        "band": (1.0, 1.0, 1.0, 0.021),
        "band_sample": (1.0, 1.0, 1.0, 0.10),
        "title": "#f1f3fa",
        "value": "#e9ecf7",
        "foot": "#d9dfee",
        "dates": "#bac2da",
        "label": "#8b94ae",
        "sep": "#525a75",
        "y_label": "#7e88a4",
        "x_label": "#98a2bd",
        "green": "#74c98a",
        "red": "#e08585",
        "legend": "последняя неделя",
    },
    "gold": {
        "bg": "#0c0e16",
        "bg_top": "#10121c",
        "bg_bot": "#0a0c13",
        "bar": "#e8b54d",
        "bar_last": "#f5d488",
        "grid": (1, 1, 1, 0.07),
        "baseline": "#3d4152",
        "avg": "#8a8fa8",
        "band": (1.0, 1.0, 1.0, 0.02),
        "band_sample": (1.0, 1.0, 1.0, 0.09),
        "title": "#f1f3fa",
        "value": "#e9ecf7",
        "foot": "#d9dfee",
        "dates": "#bac2da",
        "label": "#9aa3bc",
        "sep": "#565a6e",
        "y_label": "#8a93ad",
        "x_label": "#a2abc4",
        "green": "#74c98a",
        "red": "#e08585",
        "legend": None,
    },
    "light": {
        "bg": "#ffffff",
        "bg_top": "#ffffff",
        "bg_bot": "#f6f8fd",
        "bar": "#d09b2e",
        "bar_last": "#e8b54d",
        "grid": "#eef1f7",
        "baseline": "#dfe4ee",
        "avg": "#98a0bd",
        "band": (0.0, 0.0, 0.0, 0.018),
        "band_sample": (0.0, 0.0, 0.0, 0.06),
        "title": "#10161c",
        "value": "#2a3140",
        "foot": "#3c4356",
        "dates": "#454c5e",
        "label": "#5f6b85",
        "sep": "#b9c0d0",
        "y_label": "#7a839c",
        "x_label": "#5f6b85",
        "green": "#3f9e5e",
        "red": "#cc5f5f",
        "legend": "последняя неделя",
    },
}

_cache: dict[tuple, bytes] = {}


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
    return 10000


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


def render(counts: list[int], start: date, *, theme: str = DEFAULT_THEME,
           prev_avg: float | None = None) -> bytes:
    """PNG-байты графика. Синхронный: вызывать из потока (asyncio.to_thread).

    Без pyplot: Figure и FigureCanvasAgg не трогают глобальное состояние
    matplotlib, поэтому параллельные рендеры в потоках не мешают друг другу.

    prev_avg — среднее за предыдущее окно (для «динамики»); None — группа
    динамики не показывается (нет истории).
    """
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.collections import LineCollection
    from matplotlib.colors import to_rgba
    from matplotlib.figure import Figure
    from matplotlib.legend_handler import HandlerPatch
    from matplotlib.lines import Line2D
    from matplotlib.patches import FancyBboxPatch, Patch, PathPatch

    _ensure_fonts()

    st = THEMES.get(theme) or THEMES[DEFAULT_THEME]
    n = len(counts)
    top = max(counts, default=0)
    step = _step(top)
    ceill = _ceiling(top, step)

    total = sum(counts)
    avg = total / n if n else 0.0
    avg_r = int(round(avg))
    peak_i = counts.index(top) if top > 0 else 0
    peak_date = (start + timedelta(days=peak_i)).strftime("%d.%m")
    today_v = counts[-1] if n else 0
    active = sum(1 for c in counts if c > 0)
    streak = 0
    for c in reversed(counts):
        if c > 0:
            streak += 1
        else:
            break

    trend_s: str | None = None
    trend_c = st["label"]
    if prev_avg:
        trend = avg / prev_avg - 1.0
        if trend > 0.005:
            trend_s, trend_c = f"+{trend * 100:.0f}%", st["green"]
        elif trend < -0.005:
            trend_s, trend_c = f"{trend * 100:.0f}%", st["red"]
        else:
            trend_s = "0%"

    fig = Figure(figsize=(FIG_W, FIG_H), dpi=DPI)
    FigureCanvasAgg(fig)
    fig.patch.set_facecolor(st["bg"])

    # ── фон: мягкий вертикальный градиент + дизеринг (без бандинга) ─────────
    bg = fig.add_axes([0, 0, 1, 1], zorder=0)
    bg.set_axis_off()
    rows = 2048
    v = np.linspace(0.0, 1.0, rows)[:, None]
    bg_img = np.zeros((rows, 1, 3))
    bg_img[:, 0, :] = np.array(_rgb(st["bg_top"])) * (1 - v) + np.array(_rgb(st["bg_bot"])) * v
    noise = np.random.default_rng(7).uniform(-2, 2, size=(rows, 1)) / 255.0
    bg_img = np.clip(bg_img + noise[:, :, None], 0, 1)
    bg.imshow(bg_img, extent=(0, 1, 0, 1), aspect="auto", interpolation="bilinear")

    ax = fig.add_subplot(111, zorder=1)
    ax.patch.set_visible(False)
    fig.subplots_adjust(left=_LEFT, right=_RIGHT, top=_TOP, bottom=_BOTTOM)

    # ── выходные: тихие полосы по всему полю ────────────────────────────────
    for i in range(n):
        if (start + timedelta(days=i)).weekday() >= 5:
            ax.axvspan(i - 0.5, i + 0.5, color=st["band"], zorder=0.5, linewidth=0)

    # ── сетка, среднее, база ────────────────────────────────────────────────
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_axisbelow(True)
    for y in range(step, int(ceill) + 1, step):
        ax.axhline(y, color=st["grid"], linewidth=0.6, linestyle=(0, (2, 4)),
                   zorder=0.9)
    ax.axhline(avg, color=st["avg"], linewidth=0.9, linestyle=(0, (3, 5)), zorder=1.05)

    br, bg_c, bb = to_rgba(st["baseline"])[:3]
    bl_x = np.linspace(-0.7, n - 0.25, 121)
    t = np.linspace(0.0, 1.0, bl_x.size)
    s = np.clip(np.minimum(t, 1 - t) / 0.08, 0, 1)
    alpha = s * s * (3 - 2 * s)
    segs = [[(bl_x[i], 0), (bl_x[i + 1], 0)] for i in range(bl_x.size - 1)]
    ax.add_collection(LineCollection(
        segs, colors=[(br, bg_c, bb, float(a)) for a in alpha[:-1]],
        linewidths=1.0, zorder=2.6))

    # ── столбики: скруглённые верхушки + градиент ───────────────────────────
    x_pad = 0.36
    rx = 10.0 * (n + 0.45) / _PLOT_W_PX
    ry = 10.0 * float(ceill) / _PLOT_H_PX
    for i, h in enumerate(counts):
        if h <= 0:
            continue
        base = _rgb(st["bar_last"] if i >= n - 7 else st["bar"])
        path = _bar_path(i - x_pad, i + x_pad, h, rx, ry)
        under = PathPatch(path, facecolor=_mix(base, (1.0, 1.0, 1.0), 0.10),
                          edgecolor="none", linewidth=0,
                          transform=ax.transData, zorder=3)
        ax.add_patch(under)
        im = ax.imshow(_gradient(base), extent=(i - x_pad, i + x_pad, 0, h),
                       origin="lower", aspect="auto", interpolation="bilinear",
                       zorder=3.1)
        im.set_clip_path(under)

    # ── подпись пика ────────────────────────────────────────────────────────
    if top > 0:
        ax.text(peak_i, top + 0.01 * float(ceill), _fmt(top), ha="center",
                va="bottom", fontsize=11, color=st["label"], zorder=4,
                **_ff("normal"))

    # ── оси; последняя метка — «сегодня» ────────────────────────────────────
    ax.set_ylim(0, ceill)
    yticks = list(range(0, int(ceill) + 1, step))
    ax.set_yticks(yticks)
    ax.set_yticklabels([_fmt(y) for y in yticks])
    ax.set_xlim(-0.7, n - 0.25)

    ticks = list(range(0, n, 5))
    if ticks and n - 1 not in ticks:
        if n - 1 - ticks[-1] < 5:      # «14.10» и «сегодня» не должны слипаться
            ticks.pop()
        ticks.append(n - 1)
    ax.set_xticks(ticks)
    xlabels = [(start + timedelta(days=i)).strftime("%d.%m") for i in ticks]
    if start + timedelta(days=n - 1) == local_now().date():
        xlabels[-1] = "сегодня"
    ax.set_xticklabels(xlabels)
    ax.tick_params(axis="both", length=0, labelsize=11)
    ax.tick_params(axis="y", colors=st["y_label"])
    ax.tick_params(axis="x", colors=st["x_label"])
    ax.get_xticklabels()[-1].set_ha("right")   # иначе «сегодня» режется о правый край
    if _FAMILY:
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            lbl.set_fontfamily(_FAMILY)

    renderer = fig.canvas.get_renderer()
    scale = 1.0 / (fig.get_figwidth() * fig.dpi)

    # ── шапка: заголовок, окно дат, две строки цифр ─────────────────────────
    fig.text(X_TEXT, 0.975, f"Активность за {n} дней", color=st["title"],
             fontsize=19, ha="left", va="top", **_ff("bold"))
    end = start + timedelta(days=n - 1)
    t_dates = fig.text(X_TEXT, 0.906, f"{start:%d.%m.%Y} — {end:%d.%m.%Y}",
                       color=st["dates"], fontsize=12.5, ha="left", va="top",
                       **_ff("medium"))
    w_px = t_dates.get_window_extent(renderer=renderer).width
    fig.text(X_TEXT + w_px * scale + 0.008, 0.906, "· сообщений в день",
             color=st["label"], fontsize=12.5, ha="left", va="top", **_ff("medium"))

    def _row(items, y_base, *, start_x=None, end_x=None):
        """Строка из кусочков «подпись значение · …»; выравнивание слева/справа.

        Ширины меряются рендерером — паддинги задаём сами (пробелы в тексте
        matplotlib в расчёт ширины не берёт).
        """
        texts, widths = [], []
        for label, color, fontsize, weight, _pad in items:
            tt = fig.text(0, y_base, label, color=color, fontsize=fontsize,
                          ha="left", va="baseline", **_ff(weight))
            texts.append(tt)
            widths.append(tt.get_window_extent(renderer=renderer).width)
        total_px = sum(w + p for (_, _, _, _, p), w in zip(items, widths))
        cur = (end_x - total_px * scale) if end_x is not None else start_x
        for (_, _, _, _, pad), w, tt in zip(items, widths, texts):
            tt.set_position((cur, y_base))
            cur += (w + pad) * scale
        return total_px

    # строка 1: сегодня · динамика; строка 2: в среднем · лучший день
    w1 = _row([("сегодня", st["label"], 12, "normal", 6),
               (_fmt(today_v), st["value"], 17, "medium", 16)], 0.833,
              start_x=X_TEXT)
    if trend_s is not None:
        _row([("·", st["sep"], 12, "normal", 16),
              ("динамика", st["label"], 12, "normal", 6),
              (trend_s, trend_c, 17, "medium", 0)], 0.833,
             start_x=X_TEXT + w1 * scale)
    _row([("в среднем", st["label"], 12, "normal", 6),
          (f"{_fmt(avg_r)}/день", st["value"], 17, "medium", 16),
          ("·", st["sep"], 12, "normal", 16),
          ("лучший день", st["label"], 12, "normal", 6),
          (f"{peak_date} · {_fmt(top)}", st["value"], 17, "medium", 0)], 0.768,
         start_x=X_TEXT)

    # нижняя строка: всего · активных дней · серия
    _row([("всего", st["label"], 11, "normal", 6),
          (_fmt(total), st["foot"], 13, "medium", 16),
          ("·", st["sep"], 11, "normal", 16),
          ("активных дней", st["label"], 11, "normal", 6),
          (f"{active} из {n}", st["foot"], 13, "medium", 16),
          ("·", st["sep"], 11, "normal", 16),
          ("серия", st["label"], 11, "normal", 6),
          (f"{streak} дней", st["foot"], 13, "medium", 0)],
         0.045, start_x=X_TEXT)

    # ── легенда: неделя + среднее + выходные ────────────────────────────────
    class _MiniBarSwatch(HandlerPatch):
        """Мини-столбик в легенде; центрируется в своём слоте."""

        def create_artists(self, legend, orig_handle, xdescent, ydescent,
                           width, height, fontsize, trans):
            bw = min(width, height * 0.5)
            patch = FancyBboxPatch(
                (xdescent + (width - bw) / 2.0, ydescent), bw, height,
                boxstyle="round,pad=0,rounding_size=%.3f" % (min(bw, height) * 0.28),
                facecolor=orig_handle.get_facecolor(), edgecolor="none",
                transform=trans)
            return [patch]

    handles = []
    if st.get("legend"):
        handles.append(Patch(facecolor=st["bar_last"], edgecolor="none",
                             label=st["legend"]))
    handles.append(Line2D([], [], color=st["avg"], linestyle=(0, (2.2, 2.2)),
                          linewidth=1.2, label=_LEGEND_AVG))
    handles.append(Patch(facecolor=st["band_sample"], edgecolor="none",
                         label=_LEGEND_WEEKEND))
    legend = ax.legend(
        handles=handles, handler_map={Patch: _MiniBarSwatch()},
        loc="upper left", bbox_to_anchor=(X_TEXT, 0.712),
        bbox_transform=fig.transFigure,
        frameon=False, fontsize=12, handlelength=1.3, handleheight=1.2,
        ncol=len(handles), columnspacing=1.3, borderpad=0, labelspacing=0,
        handletextpad=0.5)
    for text in legend.get_texts():
        text.set_color(st["label"])
        if _FAMILY:
            text.set_fontfamily(_FAMILY)
            text.set_fontweight("medium")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=to_rgba(st["bg_bot"]))
    return buf.getvalue()


async def daily_counts(db, user_id: int, chat_id: int | None = None,
                       days: int = DAYS) -> tuple[date, list[int]]:
    """(начало окна, сообщений по дням от старых к свежим). chat_id=None — все чаты."""
    today = local_now().date()
    start = today - timedelta(days=days - 1)
    if chat_id is None:
        sql = ("SELECT date, COALESCE(SUM(message_count), 0) FROM daily_user_stats "
               "WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY date")
        args: tuple = (user_id, start.isoformat(), today.isoformat())
    else:
        sql = ("SELECT date, COALESCE(SUM(message_count), 0) FROM daily_user_stats "
               "WHERE chat_id = ? AND user_id = ? AND date BETWEEN ? AND ? GROUP BY date")
        args = (chat_id, user_id, start.isoformat(), today.isoformat())
    async with db.execute(sql, args) as cur:
        rows = await cur.fetchall()
    by_date: dict[str, int] = {}
    for r in rows:
        by_date[str(r[0])[:10]] = int(r[1] or 0)   # ключ — местная дата
    counts = [by_date.get((start + timedelta(days=i)).isoformat(), 0) for i in range(days)]
    return start, counts


async def get_graph(db, user_id: int, chat_id: int | None = None, *,
                    days: int = DAYS, theme: str = DEFAULT_THEME) -> bytes | None:
    """PNG для карточки или None, если рисовать нечего (ни одного сообщения в окне).

    Одним запросом тянется двойное окно: свежие days — для графика, предыдущие
    days — для «динамики» (сравнение по средним, чтобы неполная история не врала).
    """
    today = local_now().date().isoformat()
    key = (user_id, chat_id or 0, days, theme, today)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    start, span = await daily_counts(db, user_id, chat_id, days * 2)
    counts = span[days:]
    prev = span[:days]
    if not any(counts):
        return None
    prev_avg = (sum(prev) / len(prev)) if any(prev) else None
    png = await asyncio.to_thread(render, counts, start + timedelta(days=days),
                                  theme=theme, prev_avg=prev_avg)
    _cache[key] = png
    while len(_cache) > MAX_CACHE:
        _cache.pop(next(iter(_cache)))
    return png


def prewarm() -> None:
    """Прогреть matplotlib и кэш шрифтов при старте бота (вызывать в потоке)."""
    _ensure_fonts()
    render([1, 4, 2, 6, 0, 3, 5, 1, 0, 2], local_now().date() - timedelta(days=9))
