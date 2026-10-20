"""Стенд админки: открывает bot-admin на фикстурах (без входа и сервера) и снимает экраны на 320/390/430 в двух темах.

    python tools/admin_stand.py [--out DIR] [--tabs home,people,player/500,chat/-100,reports,journal,metrics,broadcast,promo,switches,settings,health,access]
    python tools/admin_stand.py --owner --tabs mychats

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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from admin_stand_fixtures import OWNER_ROUTES, ROUTES  # noqa: E402

TYPES = ("admin.js", "admin-home.js", "admin-people.js", "admin-lists.js", "admin-ops.js", "admin-boot.js", "admin.css")   # как page._TYPES

STATIC = os.path.join(os.path.dirname(__file__), "..", "FastAPI", "static", "bot-admin")
HOST = "http://stand.local"
WIDTHS = (320, 390, 430)
THEMES = ("dark", "light")
OVERFLOW_JS = """() => {
  const w = document.documentElement.clientWidth, bad = [];
  // Ленты с прокруткой вбок (чипы, вкладки, лица) намеренно выходят за край: их содержимое не считается переполнением,
  // а у родителей допускается выход ленты на ширину полей экрана (2 × 16 px).
  const SCROLLER = '.chipset.scroll, .faces, .tabs, .seg';
  document.querySelectorAll('main *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (el.closest('[hidden], details:not([open]) > :not(summary)')) return;
    if (el.parentElement && el.parentElement.closest(SCROLLER)) return;
    const bleed = el.querySelector(SCROLLER) || el.matches(SCROLLER) ? 33 : 1;
    const cut = el.scrollWidth > el.clientWidth + bleed && el.clientWidth > 0 && getComputedStyle(el).overflowX === 'visible' && !['TABLE', 'TR', 'TBODY', 'DETAILS', 'SUMMARY'].includes(el.tagName);
    if (r.width && (r.right > w + (el.matches(SCROLLER) ? 17 : 1) || r.left < (el.matches(SCROLLER) ? -17 : -1) || cut)) bad.push(el.tagName + '.' + el.className + ' ' + Math.round(r.right) + (cut ? ' текст шире блока' : ''));
  });
  return {scrollW: document.documentElement.scrollWidth, w, bad: bad.slice(0, 6)};
}"""


def read(name: str) -> str:
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="admin-stand-out")
    ap.add_argument("--tabs", default="home,people,player/500,chat/-100,reports,journal,metrics,broadcast,promo,promo/AUTUMN2026LONGCODE,promo/new,switches,settings,health,access")
    ap.add_argument("--owner", action="store_true", help="войти как владелец чата (вкладка mychats)")
    args = ap.parse_args()
    tabs = [t for t in args.tabs.split(",") if t]
    os.makedirs(args.out, exist_ok=True)
    from playwright.sync_api import sync_playwright

    html = read("index.html").replace("{{BASE}}", HOST).replace("{{VER}}", "stand")
    problems: list[str] = []

    def handle(route):
        url = urlparse(route.request.url)
        if url.netloc != "stand.local":
            return route.abort()
        path = url.path
        if path == "/bot-admin/api/export" or path.startswith("/bot-admin/api/"):
            key = path[len("/bot-admin/api"):]
            routes = OWNER_ROUTES if args.owner else ROUTES
            if key in routes:
                status, body = routes[key] if isinstance(routes[key], tuple) else (200, routes[key])
                return route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
            return route.fulfill(status=404, content_type="application/json", body='{"detail":"нет фикстуры"}')
        name = path.rsplit("/", 1)[-1]
        if name in TYPES:   # все файлы админки, а не только admin.js: иначе разделы молча не грузятся
            return route.fulfill(status=200, content_type="text/css" if name.endswith(".css") else "text/javascript", body=read(name))
        if path.startswith("/bot-admin/avatar/"):
            return route.fulfill(status=404, body="")
        return route.fulfill(status=200, content_type="text/html", body=html)

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
                    page.goto(f"{HOST}/bot-admin/#/{tab}")
                    page.wait_for_selector("#main .view", timeout=8000)
                    page.wait_for_function("() => document.querySelector('#main').getAttribute('aria-busy') !== 'true'", timeout=8000)
                    page.wait_for_timeout(500)
                    page.screenshot(path=os.path.join(args.out, f"{tab.replace('/', '_')}-{theme}-{width}.png"), full_page=True)
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
