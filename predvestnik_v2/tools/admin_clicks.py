"""Касания на типовых задачах админки (S10): Playwright проходит каждую задачу настоящими нажатиями на стенде
(фикстуры admin_stand_fixtures.py, без входа и сервера) и считает касания до результата, проверяя, что ушёл нужный запрос.

    python tools/admin_clicks.py                          # текущая админка (FastAPI/static/bot-admin)
    python tools/admin_clicks.py --static DIR --old       # старая админка (папка bot-admin из базовой ревизии) — сценарии «до»

Касание = нажатие или выбор в поле (ввод текста в поле, на котором уже стоит курсор, касанием не считается).
Старт: задачи по игроку — из его карточки, остальные — из раздела «Игроки». Отмена через 10 секунд ускорена до 0,3 с.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(__file__))
from admin_stand_fixtures import CHAT, PURGE_VIEW, ROUTES  # noqa: E402

HOST = "http://stand.local"
UID, CID = 5000, CHAT["id"]

# Шаг: ("tap", селектор) — касание; ("type", селектор, текст) — касание поля и ввод; ("keys", селектор, текст) — ввод без касания
# (курсор уже в поле: окно ставит его само); ("expect", путь, поле, значение) — ушёл такой POST (касанием не считается).
OLD = {
    "Найти игрока": ("people", [("type", "#pplq", "anna"), ("tap", f'[data-player="{UID}"]'), ("seen", "#pacts")]),
    "Выдать валюту": ("card", [("tap", "#pacts"), ("tap", '[data-act="balance"]'), ("type", "#famount", "500"), ("type", "#freason", "приз"),
                               ("tap", "#sok"), ("tap", "#sok"), ("expect", f"/player/{UID}/action", "action", "balance")]),
    "Мут в чате": ("card", [("tap", "#pacts"), ("tap", '[data-mact="mute"]'), ("tap", "#sok"), ("expect", f"/player/{UID}/action", "action", "mute")]),
    "Бан в чате": ("card", [("tap", "#pacts"), ("tap", '[data-mact="ban"]'), ("tap", "#sok"), ("tap", "#sok"), ("expect", f"/player/{UID}/action", "action", "ban")]),
    "Бан во всех чатах": ("card", [("tap", "#pacts"), ("tap", '[data-act="global_ban"]'), ("tap", "#sok"), ("type", "#fconfirm", str(UID)), ("tap", "#sok"),
                                   ("expect", f"/player/{UID}/action", "action", "global_ban")]),
    "Жалоба: наказать": ("people", [("tap", '#tabs [data-tab="reports"]'), ("tap", '[data-punish="mute"][data-rid="100"]'), ("tap", "#sok"),
                                    ("expect", "/reports/100/punish", "action", "mute")]),
    "Чистка чата": ("chat", [("tap", 'a[href*="startapp=purge_"]'), ("left", "уходит из админки в Mini App: страница перезагружается")]),
    "Рассылка": ("people", [("tap", "#tabs [data-more]"), ("tap", '[data-go="broadcast"]'), ("type", "#btext", "Привет!"), ("tap", "#bgo"), ("tap", "#sok"),
                            ("expect", "/broadcasts", "", "")]),
}
NEW = {
    **OLD,
    "Выдать валюту": ("card", [("tap", '[data-quick="balance"]'), ("keys", "#famount", "500"), ("tap", '[data-reason-pick="приз"]'), ("tap", "#sok"),
                               ("expect", f"/player/{UID}/action", "action", "balance")]),
    "Мут в чате": ("card", [("tap", '[data-quick="mute"]'), ("tap", "#sok"), ("wait_undo",), ("expect", f"/player/{UID}/action", "action", "mute")]),
    "Бан в чате": ("card", [("tap", '[data-quick="ban"]'), ("tap", "#sok"), ("wait_undo",), ("expect", f"/player/{UID}/action", "action", "ban")]),
    "Бан во всех чатах": ("card", [("tap", "#pacts"), ("tap", '[data-act="global_ban"]'), ("keys", "#fconfirm", str(UID)), ("tap", "#sok"),
                                   ("expect", f"/player/{UID}/action", "action", "global_ban")]),
    "Чистка чата": ("chat", [("tap", "[data-purge]"), ("seen", "#purgeview .meter")]),
}
# Проверки поведения, не замер: «Отменить» не отправляет ничего; решение в «Чистке» уходит на общий сервер после отсчёта.
CHECKS = {
    "Мут: «Отменить»": ("card", [("tap", '[data-quick="mute"]'), ("tap", "#sok"), ("tap", ".undo button"), ("wait_undo",), ("expect_none",)]),
    "Мут: дважды подряд": ("card", [("js", "window.ADMIN_UNDO_MS = 3000"), ("tap", '[data-quick="mute"]'), ("tap", "#sok"), ("tap", '[data-quick="mute"]'), ("tap", "#sok"), ("pause", 3500),
                                     ("expect_one", f"/player/{UID}/action")]),
    "Чистка: решение": ("chat", [("tap", "[data-purge]"), ("tap", '[data-pgu="6001"]'), ("tap", '[data-pgdo="mute"]'), ("wait_undo",),
                                 ("expect", f"/purge-v1/chats/{CID}/decision", "action", "mute")]),
}


def read(static: str, name: str) -> str:
    with open(os.path.join(static, name), encoding="utf-8") as f:
        return f.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--static", default=os.path.join(os.path.dirname(__file__), "..", "FastAPI", "static", "bot-admin"))
    ap.add_argument("--old", action="store_true", help="сценарии старой админки")
    ap.add_argument("--json", help="куда записать итог")
    args = ap.parse_args()
    scenarios = OLD if args.old else {**NEW, **CHECKS}
    from playwright.sync_api import sync_playwright

    html = read(args.static, "index.html").replace("{{BASE}}", HOST).replace("{{VER}}", "stand")
    posts: list[tuple[str, dict]] = []

    def handle(route):
        url = urlparse(route.request.url)
        if url.netloc != "stand.local":
            return route.abort()
        path = url.path
        if route.request.method == "POST":
            body = json.loads(route.request.post_data or "{}")
            posts.append((path, body))
            return route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "message": "Готово", "done": 1, "failed": []}))
        if path.startswith("/bot-admin/api/"):
            key = path[len("/bot-admin/api"):]
            if key in ROUTES:
                status, body = ROUTES[key] if isinstance(ROUTES[key], tuple) else (200, ROUTES[key])
                return route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
            return route.fulfill(status=404, content_type="application/json", body='{"detail":"нет фикстуры"}')
        if path.startswith(f"/purge-v1/chats/{CID}"):
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(PURGE_VIEW))
        name = path.rsplit("/", 1)[-1]
        if name.startswith("admin") and name.endswith(".js") and os.path.exists(os.path.join(args.static, name)):
            return route.fulfill(status=200, content_type="text/javascript", body=read(args.static, name))
        if name.endswith(".json") and os.path.exists(os.path.join(args.static, name)):
            return route.fulfill(status=200, content_type="application/json", body=read(args.static, name))
        if name.startswith("admin") and name.endswith(".css"):
            return route.fulfill(status=200, content_type="text/css", body=read(args.static, name))
        return route.fulfill(status=200, content_type="text/html", body=html)

    results, bad = {}, []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        for title, (start, steps) in scenarios.items():
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
            ctx.add_init_script("window.ADMIN_UNDO_MS = 300")
            ctx.route("**/*", handle)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{HOST}/bot-admin/")
            page.wait_for_selector('#tabs [data-tab="people"]')
            page.wait_for_function("() => !document.querySelector('.admin-load')", timeout=8000)
            if start == "card":
                page.evaluate(f"playerView(document.getElementById('main'), {UID})")
                page.wait_for_selector("#pacts")
            elif start == "chat":
                page.evaluate(f"chatView(document.getElementById('main'), {CID})")
                page.wait_for_selector("#pback")
            posts.clear()
            taps, note = 0, ""
            try:
                for step in steps:
                    kind = step[0]
                    if kind == "tap":
                        page.locator(step[1]).first.click(timeout=4000)
                        taps += 1
                    elif kind == "type":
                        page.locator(step[1]).first.click(timeout=4000)
                        page.keyboard.type(step[2])
                        taps += 1
                    elif kind == "keys":
                        assert page.evaluate(f"document.activeElement === document.querySelector({json.dumps(step[1])})"), f"курсор не в {step[1]}"
                        page.keyboard.type(step[2])
                    elif kind == "seen":
                        page.wait_for_selector(step[1], timeout=4000)
                    elif kind == "js":
                        page.evaluate(step[1])
                    elif kind == "pause":
                        page.wait_for_timeout(step[1])
                    elif kind == "wait_undo":
                        page.wait_for_timeout(700)
                    elif kind == "expect_one":
                        assert len([p for p, _ in posts if p.endswith(step[1])]) == 1, f"ждали один запрос: {posts}"
                    elif kind == "expect_none":
                        assert not posts, f"после «Отменить» ушёл запрос: {posts}"
                    elif kind == "left":
                        note = step[1]
                    elif kind == "expect":
                        page.wait_for_timeout(300)
                        path, field, value = step[1:]
                        ok = any(p.endswith(path) and (not field or b.get(field) == value) for p, b in posts)
                        assert ok, f"не ушёл запрос {path} {field}={value}: {posts}"
                results[title] = {"taps": taps, "note": note}
            except Exception as exc:   # сценарий не прошёл — это результат замера, а не падение инструмента
                bad.append(f"{title}: {str(exc).splitlines()[0][:200]}")
                results[title] = {"taps": None, "note": "не прошёл"}
            bad += [f"{title}: ошибка JS: {e}" for e in errors]
            ctx.close()
        browser.close()
    width = max(len(t) for t in results)
    for title, r in results.items():
        print(f"{title:<{width}}  {r['taps'] if r['taps'] is not None else '—':>3}  {r['note']}")
    for line in bad:
        print("✗", line)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
