"""Стенд админки: открывает bot-admin на фикстурах (без входа и сервера) и снимает вкладки на 320/390/430 в двух темах.

    python tools/admin_stand.py [--out DIR] [--tabs metrics,health]

Запросы /bot-admin/api/* подменяются данными из admin_stand_fixtures.py, внешние адреса (шрифты, telegram-web-app.js) блокируются.
Выходной код 1, если на какой-то ширине страница шире экрана: админка режет лишнее (overflow-x: clip), и без этой проверки
обрезанная колонка остаётся незамеченной. Нужен playwright (pip install playwright, браузер из PLAYWRIGHT_BROWSERS_PATH).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(__file__))
from admin_stand_fixtures import OWNER_ROUTES, ROUTES  # noqa: E402

STATIC = os.path.join(os.path.dirname(__file__), "..", "FastAPI", "static", "bot-admin")
HOST = "http://stand.local"
WIDTHS = (320, 390, 430)
THEMES = ("dark", "light")
OVERFLOW_JS = """() => {
  const w = document.documentElement.clientWidth, bad = [];
  document.querySelectorAll('main *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (el.closest('[hidden], details:not([open]) > :not(summary)')) return;
    const cut = el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0 && getComputedStyle(el).overflowX === 'visible' && !['TABLE', 'TR', 'TBODY', 'DETAILS', 'SUMMARY'].includes(el.tagName);
    if (r.width && (r.right > w + 1 || r.left < -1 || cut)) bad.push(el.tagName + '.' + el.className + ' ' + Math.round(r.right) + (cut ? ' текст шире блока' : ''));
  });
  return {scrollW: document.documentElement.scrollWidth, w, bad: bad.slice(0, 6)};
}"""


def read(name: str) -> str:
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


# Слой Путеводителя администрации (S09b): страница guide.html и файлы экрана игрока, которые отдаёт страница админки (page._SHARED).
SHARED = ("shell-v3.css", "shell-v3-home.css", "guide-v3.css", "app.20.js", "app.57.js")


def guide_file(name: str):
    """(тип, текст) для страницы слоя и её файлов или None."""
    if name == "guide":
        return "text/html", read("guide.html").replace("{{BASE}}", HOST).replace("{{VER}}", "stand")
    if name == "guide-host.js":
        return "text/javascript", read(name)
    if name in SHARED:
        return ("text/css" if name.endswith(".css") else "text/javascript"), read(os.path.join("..", name))
    return None


def handler(routes: dict):
    """Ответы стенда: фикстуры API, файлы админки и слоя Путеводителя с диска, всё внешнее — отказ (его же берёт tools/test_admin_guide_ui.py)."""
    html = read("index.html").replace("{{BASE}}", HOST).replace("{{VER}}", "stand")

    def handle(route):
        url = urlparse(route.request.url)
        if url.netloc != "stand.local":
            return route.abort()
        path = url.path
        if path.startswith("/bot-admin/api/"):
            key = path[len("/bot-admin/api"):]
            if key in routes:
                status, body = routes[key] if isinstance(routes[key], tuple) else (200, routes[key])
                return route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
            return route.fulfill(status=404, content_type="application/json", body='{"detail":"нет фикстуры"}')
        # После разделения ядра на admin*.js стенд должен отдавать все части, а не только admin.js.
        name = path.rsplit("/", 1)[-1]
        shared = guide_file(name) if path.startswith("/bot-admin/") else None
        if shared:
            return route.fulfill(status=200, content_type=shared[0], body=shared[1])
        if name.startswith("admin") and name.endswith(".js"):
            return route.fulfill(status=200, content_type="text/javascript", body=read(name))
        if name.endswith(".json"):   # данные справки (guide-admin.json, S09) и книга игрока в слое (/guide-v3.json Mini App)
            return route.fulfill(status=200, content_type="application/json", body=read(name if path.startswith("/bot-admin/") else os.path.join("..", name)))
        if name.startswith("admin") and name.endswith(".css"):
            return route.fulfill(status=200, content_type="text/css", body=read(name))
        return route.fulfill(status=200, content_type="text/html", body=html)
    return handle


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="admin-stand-out")
    ap.add_argument("--tabs", default="metrics,health")
    ap.add_argument("--owner", action="store_true", help="войти как владелец чата (вкладка mychats)")
    args = ap.parse_args()
    tabs = [t for t in args.tabs.split(",") if t]
    os.makedirs(args.out, exist_ok=True)
    from playwright.sync_api import sync_playwright

    problems: list[str] = []
    handle = handler(ROUTES if not args.owner else OWNER_ROUTES)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        for theme in THEMES:
            for width in WIDTHS:
                ctx = browser.new_context(viewport={"width": width, "height": 800}, device_scale_factor=1)
                ctx.add_init_script(f"localStorage.setItem('pv_admin_prefs', JSON.stringify({{theme: '{theme}'}}))")
                ctx.route("**/*", handle)
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                for tab in tabs:
                    page.goto(f"{HOST}/bot-admin/")
                    page.wait_for_selector(f'#tabs [data-tab="{tab}"], #tabs [data-more]')
                    page.evaluate(f"open('{tab}')")
                    page.wait_for_function("() => !document.querySelector('.admin-load')", timeout=8000)
                    page.wait_for_timeout(350)
                    page.screenshot(path=os.path.join(args.out, f"{tab}-{theme}-{width}.png"), full_page=True)
                    res = page.evaluate(OVERFLOW_JS)
                    if res["scrollW"] > res["w"] or res["bad"]:
                        problems.append(f"{tab} {theme} {width}px: ширина {res['scrollW']} при {res['w']}, {res['bad']}")
                problems += [f"{theme} {width}px: ошибка JS: {e}" for e in errors]
                ctx.close()
        browser.close()
    for p in problems:
        print("✗", p)
    print(f"снимки: {os.path.abspath(args.out)}; проблем: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
