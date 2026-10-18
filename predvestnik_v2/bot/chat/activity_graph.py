"""Компактный график «бот я / бот кто»: столбики по дням, сегодня и сумма за период.

Телефонный формат 1120×700: заголовок и итог слева, крупное число за сегодня
справа. Только последний столбик выделен золотом. Без легенды, сравнений,
серии, выходных и дополнительных KPI; на оси — три даты и редкая сетка.

Рендер — в отдельном потоке, кэш на минуту, общий рендер для одновременных
запросов и не более четырёх незавершённых задач. Предыдущая картинка доступна
во время обновления. Холодный рендер ждём до 0,75 секунды; затем карточка идёт
текстом, а готовая картинка остаётся для следующего запроса. Бюджет рендера
не включает SQL и отправку в Telegram. Фоновая задача не использует соединение
БД. Данные — один запрос только за видимое окно, без истории для сравнений.
"""
from __future__ import annotations

import asyncio
import io
import math
import threading
import time
from loguru import logger
from datetime import date, timedelta
from pathlib import Path

from bot.chat.tracking import local_now

DAYS = 30                       # окно графика, дней
DEFAULT_THEME = "cosmos"
MAX_CACHE = 256                 # картинок в памяти; ключ включает день, старые вытесняются
CACHE_TTL_SEC = 60
MAX_PENDING_RENDERS = 4
RENDER_BUDGET_SEC = 0.75
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
        "headline": "#8a5d10",
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
_cached_at: dict[tuple, float] = {}
_pending: dict[tuple, asyncio.Task] = {}


async def _render_cached(key, counts, start, *, theme, prev_avg):
    png = await asyncio.to_thread(render, counts, start, theme=theme, prev_avg=prev_avg)
    _cache[key] = png
    _cached_at[key] = time.monotonic()
    while len(_cache) > MAX_CACHE:
        oldest = next(iter(_cache))
        _cache.pop(oldest, None)
        _cached_at.pop(oldest, None)
    return png


def _render_done(key, task):
    if _pending.get(key) is task:
        _pending.pop(key, None)
    if not task.cancelled() and task.exception() is not None:
        logger.warning("Activity graph render failed: {}", type(task.exception()).__name__)


async def _wait_render(task, fallback):
    try:
        return await asyncio.wait_for(asyncio.shield(task), RENDER_BUDGET_SEC)
    except Exception:
        return fallback


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


def render(counts: list[int], start: date, *, theme: str = DEFAULT_THEME,
           prev_avg: float | None = None) -> bytes:
    """Phone-first PNG: daily bars, today's count and one period total.

    prev_avg remains an accepted argument for older callers; comparisons are
    deliberately absent from the compact card. No pyplot/global figure state.
    """
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.collections import LineCollection
    from matplotlib.colors import to_rgba
    from matplotlib.figure import Figure
    from matplotlib.patches import PathPatch

    _ensure_fonts()
    st = THEMES.get(theme) or THEMES[DEFAULT_THEME]
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
    if n and start+timedelta(days=n-1) == local_now().date():
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

    Одним запросом читается только видимое окно; при медленном рендере
    возвращается предыдущая картинка либо None для текстовой карточки.
    """
    today = local_now().date().isoformat()
    key = (user_id, chat_id or 0, days, theme, today)
    hit = _cache.get(key)
    if hit is not None and time.monotonic() - _cached_at.get(key, 0) < CACHE_TTL_SEC:
        return hit
    task = _pending.get(key)
    if task is not None:
        return hit if hit is not None else await _wait_render(task, hit)
    if len(_pending) >= MAX_PENDING_RENDERS:
        return hit
    start, counts = await daily_counts(db, user_id, chat_id, days)
    if not any(counts):
        _cache.pop(key, None)
        _cached_at.pop(key, None)
        return None
    # Recheck after the SQL await: another request may already have started the
    # same render. Background work receives only numbers, never a borrowed DB.
    task = _pending.get(key)
    if task is None:
        if len(_pending) >= MAX_PENDING_RENDERS:
            return hit
        task = asyncio.create_task(_render_cached(key, counts, start, theme=theme, prev_avg=None))
        _pending[key] = task
        task.add_done_callback(lambda done: _render_done(key, done))
    return hit if hit is not None else await _wait_render(task, hit)


def prewarm() -> None:
    """Прогреть matplotlib и кэш шрифтов при старте бота (вызывать в потоке)."""
    _ensure_fonts()
    render([1, 4, 2, 6, 0, 3, 5, 1, 0, 2], local_now().date() - timedelta(days=9))
