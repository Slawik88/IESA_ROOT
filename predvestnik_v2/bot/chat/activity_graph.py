"""Компактный график «бот я / бот кто»: столбики по дням, сегодня и сумма за период.

Телефонный формат 1120×700: заголовок и итог слева, крупное число за сегодня
справа. Только последний столбик выделен золотом. Без легенды, сравнений,
серии, выходных и дополнительных KPI; на оси — три даты и редкая сетка.

Рисует отдельный процесс (activity_graph_render.py): matplotlib не живёт в памяти бота, а картинки идут
по одной — четыре параллельных рендера в процессе бота давали всплеск памяти в 512-мегабайтном контейнере.
Рендер — в отдельном потоке, кэш на минуту, общий рендер для одновременных
запросов и не более четырёх незавершённых задач. Предыдущая картинка доступна
во время обновления. SQL и холодную отрисовку ждём суммарно до 0,75 секунды;
затем карточка идёт текстом, а готовая картинка остаётся для следующего запроса.
Отмена SQL дожидается отката savepoint; отправка в Telegram в бюджет не входит.
Фоновая задача не использует соединение
БД. Данные — один запрос только за видимое окно, без истории для сравнений.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from loguru import logger
from datetime import date, timedelta
from pathlib import Path

from bot.chat import activity_graph_render
from bot.chat.activity_graph_render import DPI, FIG_H, FIG_W  # noqa: F401  (размеры картинки — для скинов и макетов)
from bot.chat.tracking import local_now

DAYS = 30                       # окно графика, дней
DEFAULT_THEME = "cosmos"
MAX_CACHE = 48                  # картинок в памяти (≈ 80 КБ каждая); ключ включает день, старые вытесняются
CACHE_TTL_SEC = 60
MAX_PENDING_RENDERS = 4
RENDER_BUDGET_SEC = 0.75        # бюджет при уже запущенном рисовальщике
COLD_RENDER_BUDGET_SEC = 3.0    # …и при холодном: matplotlib заново грузится в новом процессе
WORKER_IDLE_SEC = 30            # без запросов рисовальщик завершается и возвращает память системе
WORKER_RENDER_TIMEOUT_SEC = 20  # зависший рисовальщик убивается, запрос получает ошибку
WORKER_MAX_RENDERS = 25         # после стольких картинок процесс заменяется новым: matplotlib понемногу разрастается

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

class _RenderWorker:
    """Процесс `activity_graph_render.py --worker`: matplotlib живёт в нём, а не в боте.

    Запускается по первому запросу, обслуживает их по одному и завершается после WORKER_IDLE_SEC тишины.
    Вызывается из потоков (asyncio.to_thread), поэтому всё под одной блокировкой.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._idle: threading.Timer | None = None
        self._done = 0

    @property
    def warm(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None

    def _spawn(self) -> subprocess.Popen:
        self._done = 0
        env = dict(os.environ)
        env.update(MPLBACKEND="Agg", MALLOC_ARENA_MAX="2",
                   MPLCONFIGDIR=os.path.join(tempfile.gettempdir(), "pv-mplconfig"))   # кэш шрифтов переживает перезапуск рисовальщика
        return subprocess.Popen(
            [sys.executable, str(Path(activity_graph_render.__file__).resolve()), "--worker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, close_fds=True)

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.kill()
        except OSError:
            pass
        for pipe in (proc.stdin, proc.stdout):
            try:
                if pipe:
                    pipe.close()
            except OSError:
                pass
        try:
            proc.wait(timeout=5)
        except Exception:      # noqa: BLE001
            pass

    def _arm_idle(self) -> None:
        if self._idle is not None:
            self._idle.cancel()
        self._idle = threading.Timer(WORKER_IDLE_SEC, self._stop_if_idle)
        self._idle.daemon = True
        self._idle.start()

    def _stop_if_idle(self) -> None:
        if self._lock.acquire(blocking=False):    # идёт рисование — его конец сам заведёт таймер заново
            try:
                self._kill()
            finally:
                self._lock.release()

    def start(self) -> None:
        """Поднять процесс заранее (пока читается SQL), если он ещё не работает."""
        if self.warm or not self._lock.acquire(blocking=False):
            return
        try:
            if not self.warm:
                self._proc = self._spawn()
                self._arm_idle()
        except OSError:
            self._proc = None
        finally:
            self._lock.release()

    def render(self, request: dict) -> bytes:
        payload = json.dumps(request, ensure_ascii=False).encode() + b"\n"
        with self._lock:
            if self._idle is not None:
                self._idle.cancel()
            try:
                if not self.warm:
                    self._kill()
                    self._proc = self._spawn()
                proc = self._proc
                watchdog = threading.Timer(WORKER_RENDER_TIMEOUT_SEC, self._kill_proc, args=(proc,))
                watchdog.daemon = True
                watchdog.start()
                try:
                    proc.stdin.write(payload)
                    proc.stdin.flush()
                    head = proc.stdout.readline().split()
                    if len(head) == 2 and head[0] == b"OK":
                        png = proc.stdout.read(int(head[1]))
                        if len(png) == int(head[1]):
                            self._done += 1
                            if self._done >= WORKER_MAX_RENDERS:
                                self._kill()
                            return png
                    raise RuntimeError("render worker: " + (b" ".join(head).decode(errors="replace") or "no answer"))
                finally:
                    watchdog.cancel()
            except BaseException:
                self._kill()
                raise
            finally:
                if self._proc is not None:
                    self._arm_idle()

    @staticmethod
    def _kill_proc(proc: subprocess.Popen) -> None:
        try:
            proc.kill()
        except OSError:
            pass


_worker = _RenderWorker()


def _worker_enabled() -> bool:
    return os.environ.get("ACTIVITY_GRAPH_INPROCESS") != "1"      # =1 — рисовать в процессе (тесты, макеты)


def render(counts: list[int], start: date, *, theme: str = DEFAULT_THEME,
           prev_avg: float | None = None) -> bytes:
    """Phone-first PNG: daily bars, today's count and one period total.

    Рисует отдельный процесс (activity_graph_render.py); не вышло поднять его — рисует тут же, как раньше.
    prev_avg remains an accepted argument for older callers; comparisons are deliberately absent from the compact card.
    """
    style = THEMES.get(theme) or THEMES[DEFAULT_THEME]
    today = local_now().date()
    if _worker_enabled():
        try:
            return _worker.render({"counts": list(counts), "start": start.isoformat(),
                                   "today": today.isoformat(), "style": style})
        except Exception as exc:      # noqa: BLE001 — картинка важнее, чем способ её нарисовать
            logger.warning("Activity graph worker failed ({}); rendering in-process", type(exc).__name__)
    return activity_graph_render.render_png(counts, start, today, style)


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


async def _wait_render(task, fallback, *, budget_sec=None):
    try:
        return await asyncio.wait_for(asyncio.shield(task),
            RENDER_BUDGET_SEC if budget_sec is None else max(0, budget_sec))
    except Exception:
        return fallback


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


async def _read_counts(db, user_id, chat_id, days, deadline):
    # Query cancellation must not abort a caller's surrounding transaction.
    # The read stays on the borrowed connection and is fully cleaned up before
    # returning; only the subsequent PNG render may continue in the background.
    async with db.connection.transaction():
        # Time out only the query, never BEGIN/ROLLBACK themselves: interrupting
        # a transaction boundary could leave a borrowed connection inside a tx.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise asyncio.TimeoutError
        return await asyncio.wait_for(daily_counts(db, user_id, chat_id, days), remaining)


async def get_graph(db, user_id: int, chat_id: int | None = None, *,
                    days: int = DAYS, theme: str = DEFAULT_THEME) -> bytes | None:
    """PNG для карточки или None, если рисовать нечего (ни одного сообщения в окне).

    Одним запросом читается только видимое окно; при медленном SQL или рендере
    возвращается предыдущая картинка либо None для текстовой карточки.
    """
    today = local_now().date().isoformat()
    key = (user_id, chat_id or 0, days, theme, today)
    hit = _cache.get(key)
    if hit is not None and time.monotonic() - _cached_at.get(key, 0) < CACHE_TTL_SEC:
        return hit
    task = _pending.get(key)
    if task is not None:
        await db.release_if_idle()   # wait for someone else's render without holding a connection
        return hit if hit is not None else await _wait_render(task, hit)
    if len(_pending) >= MAX_PENDING_RENDERS:
        return hit
    cold = _worker_enabled() and not _worker.warm
    if cold:
        _worker.start()    # matplotlib грузится в новом процессе, пока читается SQL
    deadline = time.monotonic() + (COLD_RENDER_BUDGET_SEC if cold else RENDER_BUDGET_SEC)
    try:
        start, counts = await _read_counts(db, user_id, chat_id, days, deadline)
    except asyncio.TimeoutError:
        return hit
    if not any(counts):
        _cache.pop(key, None)
        _cached_at.pop(key, None)
        return None
    # Recheck after the SQL await: another request may already have started the
    # same render. Background work receives only numbers, never a borrowed DB.
    # The render may take the whole budget: give the connection back while we wait.
    await db.release_if_idle()
    task = _pending.get(key)
    if task is None:
        if len(_pending) >= MAX_PENDING_RENDERS:
            return hit
        task = asyncio.create_task(_render_cached(key, counts, start, theme=theme, prev_avg=None))
        _pending[key] = task
        task.add_done_callback(lambda done: _render_done(key, done))
    return hit if hit is not None else await _wait_render(
        task, hit, budget_sec=deadline - time.monotonic())

