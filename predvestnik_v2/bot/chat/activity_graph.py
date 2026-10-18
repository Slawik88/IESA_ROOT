"""График активности игрока по дням — картинка вверху карточки «бот я / бот кто».

База: matplotlib рисует PNG. Тема по умолчанию — «Космос» (ночь, фиолетовые
столбики, последняя неделя золотом); всё оформление живёт в THEMES, чтобы
косметику можно было менять, не трогая логику.

Скорость: рендер идёт в отдельном потоке, результат кэшируется на день
(повторные «бот я» в тот же день картинку не перерисовывают), а matplotlib
прогревается один раз при старте бота (prewarm).
"""
from __future__ import annotations

import asyncio
import io
from datetime import date, timedelta

from bot.chat.tracking import local_now

DAYS = 30                       # окно графика, дней
DEFAULT_THEME = "cosmos"
MAX_CACHE = 256                 # картинок в памяти; ключ включает день, старые вытесняются

# Оформление: цвета и подписи. Косметику правим здесь, не трогая рендер.
THEMES = {
    "cosmos": {
        "bg": "#0a0c16",
        "bar": "#8b6cf0",
        "bar_last": "#e8b54d",
        "grid": (139 / 255, 108 / 255, 240 / 255, 0.12),
        "label": "#9aa3bc",
        "title": "#f1f3fa",
        "legend": "последняя неделя",
    },
    "gold": {
        "bg": "#0e1019",
        "bar": "#e8b54d",
        "bar_last": "#f5d488",
        "grid": (1, 1, 1, 0.07),
        "label": "#9aa3bc",
        "title": "#f1f3fa",
        "legend": None,
    },
    "light": {
        "bg": "#ffffff",
        "bar": "#d09b2e",
        "bar_last": "#e8b54d",
        "grid": "#eef1f7",
        "label": "#5f6b85",
        "title": "#10161c",
        "legend": "последняя неделя",
    },
}

_cache: dict[tuple, bytes] = {}


def _step(top: int) -> int:
    """Шаг сетки: около шести подписей по вертикали."""
    for step in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000):
        if top <= step * 6:
            return step
    return 10000


def render(counts: list[int], start: date, *, theme: str = DEFAULT_THEME) -> bytes:
    """PNG-байты графика. Синхронный: вызывать из потока (asyncio.to_thread).

    Без pyplot: Figure и FigureCanvasAgg не трогают глобальное состояние
    matplotlib, поэтому параллельные рендеры в потоках не мешают друг другу.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.patches import Patch
    from matplotlib.ticker import MultipleLocator

    st = THEMES.get(theme) or THEMES[DEFAULT_THEME]
    n = len(counts)
    top = max(counts, default=0)
    step = _step(top)

    fig = Figure(figsize=(10, 5.6), dpi=100)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    fig.patch.set_facecolor(st["bg"])
    ax.set_facecolor(st["bg"])
    fig.subplots_adjust(left=0.075, right=0.975, top=0.84, bottom=0.16)

    colors = [st["bar_last"] if i >= n - 7 else st["bar"] for i in range(n)]
    ax.bar(range(n), counts, width=0.82, color=colors, linewidth=0, zorder=3)

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=st["grid"], linewidth=0.7)
    ax.tick_params(axis="both", colors=st["label"], labelsize=8, length=0)
    ax.yaxis.set_major_locator(MultipleLocator(step))
    ax.set_ylim(0, max(step, -(-top // step) * step))
    ax.set_xlim(-0.7, n - 0.3)

    ticks = list(range(0, n, 5))
    if n - 1 not in ticks:
        ticks.append(n - 1)
    ax.set_xticks(ticks)
    ax.set_xticklabels([(start + timedelta(days=i)).strftime("%d.%m") for i in ticks])

    fig.text(0.075, 0.935, f"Активность за {n} дней", color=st["title"],
             fontsize=14.5, fontweight="bold", ha="left", va="top")
    end = start + timedelta(days=n - 1)
    fig.text(0.075, 0.878, f"{start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')} · сообщений в день",
             color=st["label"], fontsize=9, ha="left", va="top")

    if st.get("legend"):
        legend = ax.legend(
            handles=[Patch(facecolor=st["bar_last"], edgecolor="none", label=st["legend"])],
            loc="upper right", bbox_to_anchor=(1.0, 1.075), frameon=False,
            fontsize=8, handlelength=1.0, handleheight=0.9, borderpad=0, labelspacing=0,
        )
        for text in legend.get_texts():
            text.set_color(st["label"])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
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
    """PNG для карточки или None, если рисовать нечего (ни одного сообщения в окне)."""
    today = local_now().date().isoformat()
    key = (user_id, chat_id or 0, days, theme, today)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    start, counts = await daily_counts(db, user_id, chat_id, days)
    if not any(counts):
        return None
    png = await asyncio.to_thread(render, counts, start, theme=theme)
    _cache[key] = png
    while len(_cache) > MAX_CACHE:
        _cache.pop(next(iter(_cache)))
    return png


def prewarm() -> None:
    """Прогреть matplotlib и кэш шрифтов при старте бота (вызывать в потоке)."""
    render([1, 4, 2, 6, 0, 3, 5, 1, 0, 2], local_now().date() - timedelta(days=9))
