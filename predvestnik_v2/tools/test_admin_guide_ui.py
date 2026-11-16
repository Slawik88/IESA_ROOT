#!/usr/bin/env python3
"""The administration guide in the admin page, per role, on the fixture stand (tools/admin_stand.py routes, no server, no login). S09.

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. python tools/test_admin_guide_ui.py [--shots DIR]

For roles 2, 4, 5, 6 and a chat owner, at 320/390/430: the guide shows exactly the topics the role can use (the rule of admin-guide.js
computed here from the code: section thresholds and min_rank); «?» in the header opens the topic of the current section in one tap and
«Назад» returns to that section; «Что это значит?» of a dangerous action opens its topic; nothing is wider than the screen.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("DATABASE_URL", "postgresql://guide@127.0.0.1:5433/guide")

import admin_stand  # noqa: E402
from admin_stand_fixtures import OWNER_ROUTES, ROUTES  # noqa: E402
from FastAPI.routers.bot_admin.auth import SECTIONS  # noqa: E402
from ui_smoke import chromium_path  # noqa: E402

GUIDE = json.loads((ROOT / "FastAPI/static/bot-admin/guide-admin.json").read_text(encoding="utf-8"))
NAMES = {2: "🌱 Младший хелпер", 4: "🎓 Старший хелпер", 5: "🛠 Разработчик", 6: "👑 Создатель"}


def me(rank: int) -> dict:
    sections = [{"key": k, "title": t, "min_rank": r} for k, (t, r) in SECTIONS.items() if rank >= r]
    return {"user_id": 5000, "rank": rank, "rank_name": NAMES[rank], "sections": sections, "creator": rank >= 6, "ranks": list(NAMES.values())}


def expected(rank: int | None) -> list[str]:
    if rank is None:
        return [t["id"] for t in GUIDE["topics"] if t.get("owner")]
    allowed = {k for k, (_t, r) in SECTIONS.items() if rank >= r}
    return [t["id"] for t in GUIDE["topics"] if rank >= t["min_rank"] and (not t.get("section") or t["section"] in allowed or t["section"] == "mychats")]


def run(browser, rank: int | None, width: int, shots: str | None) -> None:
    routes = OWNER_ROUTES if rank is None else {**ROUTES, "/me": me(rank)}
    html = admin_stand.read("index.html").replace("{{BASE}}", admin_stand.HOST).replace("{{VER}}", "stand")

    def handle(route):
        from urllib.parse import urlparse
        url = urlparse(route.request.url)
        if url.netloc != "stand.local":
            return route.abort()
        if url.path.startswith("/bot-admin/api/"):
            key = url.path[len("/bot-admin/api"):]
            if key in routes:
                status, body = routes[key] if isinstance(routes[key], tuple) else (200, routes[key])
                return route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
            return route.fulfill(status=404, content_type="application/json", body='{"detail":"нет фикстуры"}')
        name = url.path.rsplit("/", 1)[-1]
        if name.endswith(".json"):
            return route.fulfill(status=200, content_type="application/json", body=admin_stand.read(name))
        if (name.startswith("admin") or name in admin_stand.SHARED) and name.endswith((".js", ".css")):
            return route.fulfill(status=200, content_type="text/javascript" if name.endswith(".js") else "text/css", body=admin_stand.read(name))
        return route.fulfill(status=200, content_type="text/html", body=html)

    who = "owner" if rank is None else f"rank{rank}"
    ctx = browser.new_context(viewport={"width": width, "height": 800}, device_scale_factor=2 if shots else 1)
    ctx.route("**/*", handle)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{admin_stand.HOST}/bot-admin/")
    page.wait_for_selector("#tabs .nb", timeout=10000)
    page.wait_for_function("() => !document.querySelector('.admin-load')", timeout=10000)
    first = page.evaluate("() => currentSection()")
    assert page.locator(".top .hbtn.help").count() == 1, "значок «?» в шапке"

    # 1. «?» из текущего раздела: тема этого раздела, «Назад» — обратно в раздел (одно касание туда, одно обратно)
    page.click(".top .hbtn.help")
    page.wait_for_function("() => currentSection() === 'guide' && !document.querySelector('.admin-load')", timeout=10000)
    page.wait_for_selector("#main .page-head", timeout=10000)
    topic = page.evaluate("() => AG.view === 'topic' ? AG.topic : ''")
    sec_topics = [t["id"] for t in GUIDE["topics"] if t.get("section") == first and t["id"] in expected(rank)]
    assert (topic in sec_topics) if sec_topics else topic == "", (who, first, topic, sec_topics)
    if shots:
        page.screenshot(path=f"{shots}/{who}-{width}-context.png", full_page=False)
    if topic:
        page.click("#ag-back")
        page.wait_for_function(f"() => currentSection() === '{first}'", timeout=8000)

    # 2. Раздел «Справка»: ровно темы роли
    page.evaluate("() => openAdminGuide()")
    page.wait_for_selector("#ag-q", timeout=10000)
    visible = page.evaluate("() => agTopics().map(t => t.id)")
    assert visible == expected(rank), (who, sorted(set(visible) ^ set(expected(rank))))
    shown_rows = page.evaluate("() => [...document.querySelectorAll('#ag-home [data-ag]')].map(b => b.dataset.ag).filter((v, i, a) => a.indexOf(v) === i)")
    assert set(shown_rows) <= set(expected(rank)), (who, set(shown_rows) - set(expected(rank)))
    res = page.evaluate(admin_stand.OVERFLOW_JS)
    assert res["scrollW"] <= res["w"] and not res["bad"], (who, width, res)
    small = page.evaluate("() => [...document.querySelectorAll('#main button')].filter(b => b.offsetParent && b.getBoundingClientRect().height < 44).map(b => b.className + ':' + b.textContent.trim().slice(0, 20)).slice(0, 5)")
    assert not small, (who, width, "кнопки ниже 44 px", small)
    if shots:
        page.screenshot(path=f"{shots}/{who}-{width}-hub.png", full_page=True)

    # 3. Поиск с опечаткой и тема с содержанием
    if rank is not None and rank >= 3:
        page.fill("#ag-q", "замутть")
        page.wait_for_selector("#ag-results [data-ag='sanctions']", timeout=5000)
        page.fill("#ag-q", "сантции")   # опечатка: «санкции»
        page.wait_for_selector("#ag-results [data-ag='chat-commands']", timeout=5000)
        page.fill("#ag-q", "замутить")
        page.wait_for_selector("#ag-results [data-ag='sanctions']", timeout=5000)
        page.click("#ag-results [data-ag='sanctions']")
        page.wait_for_selector(".ag-crumbs", timeout=5000)
        res = page.evaluate(admin_stand.OVERFLOW_JS)
        assert res["scrollW"] <= res["w"] and not res["bad"], (who, width, "тема", res)
        if shots:
            page.screenshot(path=f"{shots}/{who}-{width}-topic.png", full_page=True)
        # «Что это значит?» опасного действия
        page.evaluate("() => { open('people'); }")
        page.wait_for_function("() => currentSection() === 'people'", timeout=8000)
        page.evaluate("() => agWhy('ban')")
        page.wait_for_function("() => currentSection() === 'guide' && AG.topic === 'sanctions'", timeout=8000)
    assert not errors, (who, width, errors)
    ctx.close()
    print(f"OK {who} @{width}: {len(visible)} topics, «?» from «{first}» → {topic or 'главная справки'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shots", default=None)
    ap.add_argument("--widths", type=lambda s: [int(x) for x in s.split(",")], default=[320, 390, 430])
    args = ap.parse_args()
    if args.shots:
        os.makedirs(args.shots, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_path())
        for rank in (2, 4, 5, 6, None):
            for width in args.widths:
                run(browser, rank, width, args.shots)
        browser.close()


if __name__ == "__main__":
    main()
