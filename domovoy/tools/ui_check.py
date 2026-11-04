"""Проверка интерфейса сайта: сквозные сценарии и автоаудит на разных размерах и языках.

    python tools/ui_check.py [--only flows|audit]

Сам поднимает демо-стенд на свежей базе (tools/demo_server.py), по завершении останавливает; выходит с кодом 1 при нарушениях.
Нужны playwright и Chromium: python -m pip install playwright && python -m playwright install chromium
Скриншоты и скачанные файлы — в data/ui-check/ (в git не попадают).
"""
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

import ui_audit
import ui_flows

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "data" / "ui-check"
START_TIMEOUT_S = 30
# Длинные языки проверяются на самом узком экране, где переполнение вероятнее всего.
LANGUAGE_RUNS = (("de", ("320x568",)), ("fr", ("320x568",)), ("uk", ("320x568",)))
# Светлая тема (Telegram в светлом режиме): контраст и вид на телефоне, планшете и широком экране.
LIGHT_SIZES = ("320x568", "390x844", "768x1024", "1280x800")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start_demo_server(port: int) -> subprocess.Popen:
    server = subprocess.Popen([sys.executable, str(ROOT / "tools" / "demo_server.py"), "--fresh", "--port", str(port)], cwd=ROOT)
    deadline = time.time() + START_TIMEOUT_S
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1).close()
            return server
        except OSError:
            time.sleep(0.4)
    server.terminate()
    raise RuntimeError("Демо-стенд не запустился")


def main() -> int:
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    SHOTS.mkdir(parents=True, exist_ok=True)
    port = free_port()
    base = f"http://127.0.0.1:{port}/"
    server = start_demo_server(port)
    failures = []
    try:
        with sync_playwright() as playwright:
            if only in (None, "audit"):
                # Аудит идёт до сценариев: база ещё в исходном виде. Дом 3 — крайние значения.
                for house in (1, 3):
                    violations, report = ui_audit.audit(playwright, base, house=house)
                    print(*report, sep="\n")
                    failures += violations
                for house in (1, 3):
                    violations, report = ui_audit.audit(playwright, base, sizes=LIGHT_SIZES, house=house, theme="light")
                    print(*report, sep="\n")
                    failures += violations
                for language, sizes in LANGUAGE_RUNS:
                    violations, report = ui_audit.audit(playwright, base, sizes=sizes, language=language)
                    print(*report, sep="\n")
                    failures += violations
                for size, state, kind, detail in failures:
                    print(f"НАРУШЕНИЕ [{size} / {state}] {kind}: {detail}")
            report = ui_flows.Report()
            if only in (None, "flows"):
                ui_flows.run_all(playwright, base, report, SHOTS)
    finally:
        server.terminate()
        server.wait(timeout=10)
    broken = len(failures) + len(report.failed)
    print(f"\nСценарии: {len(report.results) - len(report.failed)}/{len(report.results)}; нарушений аудита: {len(failures)}")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
