"""Пути админки 3.0 в настоящем браузере на фикстурах стенда (без сервера и базы): что уходит на сервер и когда.

    python tools/test_bot_admin_ui_flows.py

Проверяется: адреса и «назад»; деньги — итог, ввод ID, «‹» к форме без потери полей, один request_id на окно
(и при повторе после сбоя); бан из жалобы — с итогом и закрытием жалобы; отмена выключения всего бота ничего
не пишет; владелец находит участника поиском, а не по ID; ошибок страницы нет. Нужен playwright и Chromium
(CHROMIUM_PATH или PLAYWRIGHT_BROWSERS_PATH).
"""
from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(__file__))
from admin_stand import HOST, TYPES, read  # noqa: E402
from admin_stand_fixtures import OWNER_ROUTES, ROUTES  # noqa: E402


def run(owner: bool = False):
    from playwright.sync_api import sync_playwright
    posts: list[tuple[str, dict]] = []
    fail_next: list[str] = []
    html = read("index.html").replace("{{BASE}}", HOST).replace("{{VER}}", "t")
    routes = OWNER_ROUTES if owner else ROUTES

    def handle(route):
        req, url = route.request, urlparse(route.request.url)
        if url.netloc != "stand.local":
            return route.abort()
        path = url.path
        if path.startswith("/bot-admin/api/"):
            key = path[len("/bot-admin/api"):]
            if req.method != "GET" and key not in ("/broadcasts/preview",):
                posts.append((key, json.loads(req.post_data or "{}")))
                if fail_next and fail_next[0] == key:
                    fail_next.pop(0)
                    return route.fulfill(status=502, content_type="application/json", body='{"detail":"Сеть оборвалась"}')
                return route.fulfill(status=200, content_type="application/json", body='{"ok":true,"message":"Готово","failed":[]}')
            if key in routes:
                status, body = routes[key] if isinstance(routes[key], tuple) else (200, routes[key])
                return route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
            return route.fulfill(status=404, content_type="application/json", body='{"detail":"нет фикстуры"}')
        name = path.rsplit("/", 1)[-1]
        if name in TYPES:
            return route.fulfill(status=200, content_type="text/css" if name.endswith(".css") else "text/javascript", body=read(name))
        if path.startswith("/bot-admin/avatar/"):
            return route.fulfill(status=404, body="")
        return route.fulfill(status=200, content_type="text/html", body=html)

    pw = sync_playwright().start()
    browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
    ctx = browser.new_context(viewport={"width": 390, "height": 800})
    ctx.route("**/*", handle)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return pw, browser, page, posts, fail_next, errors


def settle(page):
    page.wait_for_function("() => document.querySelector('#main').getAttribute('aria-busy') !== 'true' && document.querySelector('#main .view')", timeout=8000)
    page.wait_for_timeout(200)


def top(page, sel):
    return page.locator(f".sheet.is-top {sel}")


def staff_flows():
    pw, browser, page, posts, fail_next, errors = run()
    page.goto(f"{HOST}/bot-admin/")
    settle(page)
    assert page.evaluate("location.hash") == "#/home", page.evaluate("location.hash")

    # Адреса и «назад»: главная → игроки → карточка → назад к списку
    page.click('#tabs [data-tab="people"]'); settle(page)
    assert page.evaluate("location.hash").startswith("#/people")
    page.click('a.row[href="#/player/500"]'); settle(page)
    assert page.evaluate("location.hash").startswith("#/player/500")
    assert "Очень длинное имя" in page.inner_text("#ttl")
    page.click("#hback"); settle(page)
    assert page.evaluate("location.hash").startswith("#/people"), "«назад» ведёт туда, откуда пришёл"
    page.go_forward(); settle(page)

    # Деньги: форма → итог с вводом ID → «‹» к форме (поля на месте) → неверный ID не уходит → сбой сети → повтор с тем же ключом
    page.click('[data-on="acts"]')
    top(page, '[data-k="balance"]').click()
    top(page, "#famount").fill("100000")
    top(page, "#freason").fill("компенсация")
    top(page, '[data-sa="0"]').click()
    assert "станет" in top(page, ".sum").inner_text()
    top(page, '[data-sh="back"]').click()
    assert top(page, "#famount").input_value() == "100000", "назад с итога вернул пустую форму"
    top(page, '[data-sa="0"]').click()
    top(page, "#fconfirm").fill("123")
    top(page, '[data-sa="0"]').click()
    page.wait_for_timeout(150)
    assert "ID не совпал" in top(page, ".err").inner_text() and not posts, "неверный ID не должен уходить на сервер"
    top(page, "#fconfirm").fill("500")
    fail_next.append("/player/500/action")
    top(page, '[data-sa="0"]').click()
    page.wait_for_timeout(300)
    assert "Сеть оборвалась" in top(page, ".err").inner_text(), "ошибка видна в шторке"
    top(page, '[data-sa="0"]').click()
    page.wait_for_timeout(300)
    (k1, b1), (k2, b2) = posts[0], posts[1]
    assert k1 == k2 == "/player/500/action" and b1["action"] == "balance" and b1["confirm"] == "500" and b1["amount"] == "100000"
    assert b1["request_id"] and b1["request_id"] == b2["request_id"], "повтор после сбоя обязан идти с тем же request_id"
    assert page.locator(".sheet").count() == 0, "после успеха шторки закрыты"
    settle(page)
    posts.clear()

    # Новое окно — новый ключ
    page.click('[data-on="acts"]'); top(page, '[data-k="balance"]').click()
    top(page, "#famount").fill("5"); top(page, "#freason").fill("тест"); top(page, '[data-sa="0"]').click(); top(page, '[data-sa="0"]').click()
    page.wait_for_timeout(300)
    assert posts[0][1]["request_id"] != b1["request_id"]
    settle(page); posts.clear()

    # Причина-чип и срок-чип попадают в запрос; мут не опасный — без итога
    page.click('[data-on="acts"]'); top(page, '[data-k="warn"]').click()
    top(page, '.chip[data-on="freason"][data-v="Спам"]').click()
    top(page, '.chip[data-on="fdur"][data-v="1440"]').click()
    top(page, '[data-sa="0"]').click(); page.wait_for_timeout(300)
    assert posts[0][1] == {"action": "warn", "minutes": 1440, "reason": "Спам", "chat_id": -100}, posts[0]
    settle(page); posts.clear()

    # Esc закрывает только верхнюю шторку
    page.click('[data-on="acts"]'); top(page, '[data-k="ban"]').click()
    page.keyboard.press("Escape")
    assert page.locator(".sheet").count() == 1
    page.keyboard.press("Escape")
    assert page.locator(".sheet").count() == 0 and not posts

    # Бан из жалобы: «Решить» → «Забанить» → итог → запрос с закрытием жалобы
    page.goto(f"{HOST}/bot-admin/#/reports"); settle(page)
    page.locator('[data-on="decide"]').first.click()
    top(page, '[data-on="pun"][data-k="ban"]').click()
    assert top(page, "#freason").input_value().startswith("Оскорбления"), "причина подставляется из жалобы"
    top(page, '[data-sa="0"]').click()
    assert "Жалоба" in top(page, ".sum").inner_text() and not posts
    top(page, '[data-sa="0"]').click(); page.wait_for_timeout(300)
    assert posts[0][0] == "/reports/100/punish" and posts[0][1]["action"] == "ban" and posts[0][1]["close"] is True and posts[0][1]["minutes"] == 0, posts
    settle(page); posts.clear()

    # Выключение всего бота: отмена не пишет и оставляет включённым; подтверждение пишет с причиной
    page.goto(f"{HOST}/bot-admin/#/switches"); settle(page)
    box = page.locator('input[data-k="all"]')
    box.click()
    assert box.is_checked() and page.locator(".sheet").count() == 1
    top(page, '[data-sa="1"]').click()
    assert box.is_checked() and not posts, "отмена не должна выключать"
    box.click()
    top(page, '.chip[data-on="sr"]').first.click()
    top(page, '[data-sa="0"]').click(); page.wait_for_timeout(300)
    assert posts[0] == ("/switches", {"feature": "all", "chat_id": 0, "enabled": False, "reason": "Чиним, вернём скоро"}), posts
    settle(page); posts.clear()

    # Глобальный поиск открывает карточку и закрывается
    page.keyboard.press("/")
    top(page, "#gq").fill("nick")
    page.wait_for_selector('.sheet.is-top a.row[href="#/player/500"]')
    top(page, 'a.row[href="#/player/500"]').click(); settle(page)
    assert page.evaluate("location.hash").startswith("#/player/500") and page.locator(".sheet").count() == 0

    assert not errors, errors
    browser.close()
    pw.stop()


def owner_flow():
    pw, browser, page, posts, fail_next, errors = run(owner=True)
    page.goto(f"{HOST}/bot-admin/")
    settle(page)
    assert page.evaluate("location.hash") == "#/mychats" and page.locator("#hsearch").is_hidden(), "владельцу — свой чат, без поиска по базе"
    page.click('[data-on="punish"]')
    top(page, "#omq").fill("mem")
    page.wait_for_selector('.sheet.is-top [data-on="m"]')
    top(page, '[data-on="m"]').click()
    top(page, '[data-k="ban"]').click()
    top(page, '[data-sa="0"]').click()
    assert "Участник Чата" in top(page, ".sum").inner_text() and not posts
    top(page, '[data-sa="0"]').click(); page.wait_for_timeout(300)
    assert posts[0][0] == "/owner/chat/-100/member/800/action" and posts[0][1]["action"] == "ban", posts
    assert not errors, errors
    browser.close()
    pw.stop()


if __name__ == "__main__":
    staff_flows()
    owner_flow()
    print("OK: адреса и «назад», деньги с вводом ID и одним ключом, бан из жалобы, отмена выключения бота, владелец без ID")
