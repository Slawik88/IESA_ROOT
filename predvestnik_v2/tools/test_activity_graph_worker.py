"""Рисовальщик графика в отдельном процессе: ответ, простой, падение, зависание, запасной путь (без базы).

Зачем: matplotlib держал в процессе бота 60–80 МиБ из 512 МБ контейнера; теперь он живёт в `activity_graph_render.py --worker`.
Запуск: python tools/test_activity_graph_worker.py
"""
from __future__ import annotations

import os
import sys
import time
from datetime import timedelta
from unittest.mock import patch

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.pop("ACTIVITY_GRAPH_INPROCESS", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.chat import activity_graph as g       # noqa: E402
from bot.chat.tracking import local_now        # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n"
SAMPLE = [0, 5, 12, 3, 0, 8, 40, 2, 1, 7, 15, 22, 0, 0, 3, 9, 11, 6, 2, 0, 4, 18, 25, 7, 3, 1, 0, 12, 9, 5]
START = local_now().date() - timedelta(days=len(SAMPLE) - 1)


def alive() -> bool:
    return g._worker.warm


def main() -> None:
    g._worker._kill()
    assert not alive(), "до первого запроса рисовальщика нет"

    png = g.render(SAMPLE, START)
    assert png.startswith(PNG) and len(png) > 5000, "картинка пришла из рисовальщика"
    assert alive(), "рисовальщик остаётся жить между запросами"
    pid = g._worker._proc.pid
    assert g.render(SAMPLE, START).startswith(PNG) and g._worker._proc.pid == pid, "второй запрос — тот же процесс"

    # В процессе бота matplotlib не появляется: он не нужен, пока рисует рисовальщик.
    assert "matplotlib" not in sys.modules, "matplotlib загружен в процесс бота"

    # Каждая тема, включая тему из скина (её регистрирует skin_card прямо в THEMES) — палитра едет в запросе.
    g.THEMES["__t"] = {**g.THEMES[g.DEFAULT_THEME], "bar": "#ff0000", "legend": None}
    try:
        for theme in list(g.THEMES):
            assert g.render(SAMPLE, START, theme=theme).startswith(PNG), theme
    finally:
        g.THEMES.pop("__t", None)

    # Рисовальщик убит снаружи → следующий запрос поднимает новый процесс и отвечает.
    g._worker._proc.kill()
    g._worker._proc.wait()
    assert g.render(SAMPLE, START).startswith(PNG), "после падения поднимается заново"
    assert g._worker._proc.pid != pid

    # Плохой запрос не роняет рисовальщик и не отдаёт мусор: ошибка наружу, процесс перезапускается чисто.
    try:
        g._worker.render({"counts": "x", "start": "bad", "today": "bad", "style": {}})
    except RuntimeError:
        pass
    else:
        raise AssertionError("ошибка рисовальщика должна дойти до вызывающего")
    assert g.render(SAMPLE, START).startswith(PNG), "после ошибки снова рисует"

    # Простой: процесс завершается сам и память возвращается системе.
    with patch.object(g, "WORKER_IDLE_SEC", 0.4):
        g.render(SAMPLE, START)
        proc = g._worker._proc
        deadline = time.monotonic() + 10
        while g._worker._proc is not None and time.monotonic() < deadline:
            time.sleep(0.1)
    assert g._worker._proc is None, "рисовальщик не завершился после простоя"
    proc.wait(timeout=10)      # kill уже отправлен; ждём, пока система его подберёт

    # Зависший рисовальщик убивается по таймауту, а render() всё равно отдаёт картинку запасным путём в процессе.
    with patch.object(g, "WORKER_RENDER_TIMEOUT_SEC", 0.001):
        t0 = time.monotonic()
        png = g.render(SAMPLE, START)
        assert png.startswith(PNG), "запасной путь не нарисовал"
        assert time.monotonic() - t0 < 30
    g._worker._kill()

    # Нельзя поднять процесс (нет интерпретатора) → рисуем в процессе, как раньше.
    with patch.object(g.sys, "executable", os.path.join(os.path.dirname(__file__), "no-such-python")):
        assert g.render(SAMPLE, START).startswith(PNG), "без рисовальщика график должен рисоваться в процессе"
    g._worker._kill()
    print("OK: activity graph worker — запрос, повтор, темы, падение, ошибка, простой, таймаут, запасной путь")


main()
