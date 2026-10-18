"""Черновик рендера графика активности игрока (референсы для «бот я / бот кто»).

Рисует три варианта графика за 365 дней в стилистике Предвестника («Deep Space Gold»):
  A. «Ночное золото» — золотые столбики на тёмном
  B. «Космос»        — фиолетовые столбики, последняя неделя золотом
  C. «Светлая метрика» — светлый вариант с фирменным золотом

Это макет: замеряет время рендера, чтобы проверить бюджет скорости.
Продовая версия будет в bot/chat/ (рендер в фоне + кэш по дню).
"""
from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "img"
OUT.mkdir(exist_ok=True)

N = 365
END = dt.date(2026, 10, 18)
START = END - dt.timedelta(days=N - 1)
DAYS = np.array([START + dt.timedelta(days=i) for i in range(N)])

INK, MUTED, DIM = "#f1f3fa", "#9aa3bc", "#6b7280"
GOLD, GOLD2, VIOLET = "#e8b54d", "#f5d488", "#8b6cf0"


def fake_counts(seed: int = 17) -> np.ndarray:
    """Правдоподобная история года: тихий старт → весенний взрыв → летние всплески → отпуск → возвращение."""
    anchors = [
        ("2025-10-18", 12), ("2025-11-17", 30), ("2025-12-17", 55),
        ("2026-01-01", 70), ("2026-01-31", 95), ("2026-02-15", 120), ("2026-03-02", 140),
        ("2026-03-17", 300), ("2026-03-22", 480), ("2026-03-29", 510),
        ("2026-04-06", 380), ("2026-04-16", 250), ("2026-04-26", 320),
        ("2026-05-06", 150), ("2026-05-21", 110),
        ("2026-06-05", 95), ("2026-06-15", 40), ("2026-06-23", 55), ("2026-06-30", 210),
        ("2026-07-07", 90), ("2026-07-15", 75), ("2026-07-30", 120), ("2026-08-02", 230),
        ("2026-08-10", 60), ("2026-08-18", 30), ("2026-08-24", 6),
        ("2026-09-01", 10), ("2026-09-10", 14), ("2026-09-18", 12), ("2026-09-21", 25), ("2026-09-27", 8),
        ("2026-10-01", 20), ("2026-10-05", 90), ("2026-10-08", 135), ("2026-10-10", 120),
        ("2026-10-13", 60), ("2026-10-15", 35), ("2026-10-18", 85),
    ]
    xs = (np.array([(dt.date.fromisoformat(d) - START).days for d, _ in anchors]))
    ys = np.array([v for _, v in anchors], dtype=float)
    base = np.interp(np.arange(N), xs, ys)
    rng = np.random.default_rng(seed)
    vals = np.clip(base * rng.normal(1.0, 0.18, N), 0, None)
    # затишья как в жизни: тихая неделя в августе и «отпуск» в конце сентября
    quiet = [(dt.date(2026, 8, 20), dt.date(2026, 8, 27), 6), (dt.date(2026, 9, 22), dt.date(2026, 9, 27), 0)]
    for a, b, cap in quiet:
        i, j = (a - START).days, (b - START).days
        vals[i:j] = np.minimum(vals[i:j], cap)
    vals = np.round(vals)
    # демо-данные: держим пик ~520, чтобы шкала выглядела как в референсе
    if vals.max() > 530:
        vals = np.round(vals * (530.0 / vals.max()))
    return vals


def base_figure(bg: str):
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=100)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.subplots_adjust(left=0.075, right=0.975, top=0.84, bottom=0.16)
    return fig, ax


def draw_common(fig, ax, vals, *, title_color, sub_color, label_color, grid_color, wordmark_color):
    ax.yaxis.set_major_locator(MultipleLocator(100))
    ax.grid(axis="y", color=grid_color, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", colors=label_color, labelsize=8, length=0)
    ax.set_xlim(DAYS[0] - dt.timedelta(days=1), DAYS[-1] + dt.timedelta(days=1))
    ax.set_ylim(0, max(500, np.ceil(vals.max() / 50) * 50))
    ticks = ["2025-10-18", "2025-12-01", "2026-01-15", "2026-03-01", "2026-04-15",
             "2026-06-01", "2026-07-15", "2026-09-01", "2026-10-18"]
    ax.set_xticks([dt.date.fromisoformat(t) for t in ticks])
    ax.set_xticklabels([dt.date.fromisoformat(t).strftime("%d.%m") for t in ticks])
    fig.text(0.075, 0.935, "Активность за 365 дней", color=title_color,
             fontsize=14.5, fontweight="bold", ha="left", va="top")
    fig.text(0.075, 0.878, "Иван Грозный · 18.10.2025 — 18.10.2026 · сообщений в день",
             color=sub_color, fontsize=9, ha="left", va="top")
    fig.text(0.975, 0.935, "ПРЕДВЕСТНИК", color=wordmark_color, fontsize=8, ha="right", va="top")
    total = int(vals.sum())
    active = int((vals > 0).sum())
    peak_i = int(vals.argmax())
    fig.text(0.5, 0.035,
             f"всего {total:,} · активных дней {active} · пик {int(vals.max())} ({DAYS[peak_i].strftime('%d.%m')})"
             .replace(",", " "),
             color=sub_color, fontsize=8.5, ha="center", va="bottom")


def render(vals: np.ndarray, path: Path, style: str) -> float:
    t0 = time.perf_counter()
    if style == "gold":
        bg = "#0e1019"
        fig, ax = base_figure(bg)
        ax.bar(DAYS, vals, width=0.86, color=GOLD, linewidth=0, zorder=3)
        draw_common(fig, ax, vals, title_color=INK, sub_color=MUTED,
                    label_color=MUTED, grid_color=(1, 1, 1, 0.07), wordmark_color="#a8842f")
    elif style == "cosmos":
        bg = "#0a0c16"
        fig, ax = base_figure(bg)
        colors = [GOLD if i >= N - 7 else VIOLET for i in range(N)]
        ax.bar(DAYS, vals, width=0.86, color=colors, linewidth=0, zorder=3)
        draw_common(fig, ax, vals, title_color=INK, sub_color=MUTED,
                    label_color=MUTED, grid_color=(139 / 255, 108 / 255, 240 / 255, 0.12), wordmark_color="#a8842f")
        legend = ax.legend(handles=[matplotlib.patches.Patch(facecolor=GOLD, edgecolor="none", label="последняя неделя")],
                           loc="upper right", bbox_to_anchor=(1.0, 1.075), frameon=False,
                           fontsize=8, handlelength=1.0, handleheight=0.9, borderpad=0, labelspacing=0)
        for text in legend.get_texts():
            text.set_color(MUTED)
    else:  # light
        bg = "#ffffff"
        fig, ax = base_figure(bg)
        ax.bar(DAYS, vals, width=0.86, color="#d09b2e", linewidth=0, zorder=3)
        draw_common(fig, ax, vals, title_color="#10161c", sub_color="#5f6b85",
                    label_color="#5f6b85", grid_color="#eef1f7", wordmark_color="#c99f3f")
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return (time.perf_counter() - t0) * 1000


def main() -> None:
    vals = fake_counts()
    print(f"дней: {len(vals)} · сумма: {int(vals.sum())} · пик: {int(vals.max())} "
          f"({DAYS[int(vals.argmax())].strftime('%d.%m.%Y')}) · активных: {int((vals > 0).sum())}")
    for style, name in (("gold", "chart-gold.png"), ("cosmos", "chart-cosmos.png"), ("light", "chart-light.png")):
        render(vals, OUT / "_warm.png", style)  # первый рендер греет кэш шрифтов matplotlib
        ms = render(vals, OUT / name, style)
        size = (OUT / name).stat().st_size / 1024
        print(f"{name:20s} рендер+сохранение: {ms:6.0f} мс · {size:6.1f} КБ")
    (OUT / "_warm.png").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
