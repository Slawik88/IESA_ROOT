#!/usr/bin/env python3
"""The administration guide is the player Guide screen of the Mini App (admin book), per role. S09, S09b.

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. python tools/test_admin_guide_ui.py [--shots DIR] [--widths 320,390,430]

1. Mini App on the production-topology stand (tools/ui_stand.py, the persona gets bot roles 2, 4, 5 in turn;
   role 6 is DEVELOPER_ID only, its book is checked by test_admin_guide_contract.py): the player Guide shows staff
   the entry «Путеводитель администрации»; the admin book has exactly the topics of the role (the rule of services/admin_guide.py computed
   here from the code), search with a typo, a topic with «Открыть» into its admin section; nothing is wider than the screen.
   A player without a role gets «this book is for staff», not an error.
2. Admin page on the fixture stand (tools/admin_stand.py): «?» opens the Mini App topic of the current section, «Что это значит?» of a
   dangerous action opens its topic, the «Путеводитель» tab opens the hub; «Назад» there returns to that section (pv_admin_tab).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import admin_stand  # noqa: E402
from admin_stand_fixtures import ROUTES  # noqa: E402
from ui_smoke import chromium_path, go, open_app, settle  # noqa: E402
from ui_smoke_checks import GEOMETRY  # noqa: E402
from ui_stand import DEFAULT_DSN, PERSONA_ID, Stand  # noqa: E402

GUIDE = json.loads((ROOT / "FastAPI/static/bot-admin/guide-admin.json").read_text(encoding="utf-8"))
NAMES = {2: "🌱 Младший хелпер", 4: "🎓 Старший хелпер", 5: "🛠 Разработчик", 6: "👑 Создатель"}


def sections(rank: int) -> set[str]:
    from FastAPI.routers.bot_admin.auth import SECTIONS
    return {k for k, (_t, r) in SECTIONS.items() if rank >= r} | {"mychats"}


def expected(rank: int) -> list[str]:
    allowed = sections(rank)
    return [t["id"] for t in GUIDE["topics"] if rank >= t["min_rank"] and (not t.get("section") or t["section"] in allowed)]


def set_rank(dsn: str, rank: int) -> None:
    async def write() -> None:
        import asyncpg
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute("UPDATE users SET bot_rank = $1 WHERE user_tg_id = $2", rank, PERSONA_ID)
        finally:
            await conn.close()
    thread = threading.Thread(target=lambda: asyncio.run(write()))
    thread.start(); thread.join()


def miniapp(stand: Stand, browser, rank: int, width: int, shots: str | None) -> None:
    set_rank(stand.dsn, rank)
    ctx, page, probe = open_app(stand, browser, width)
    try:
        who = f"rank{rank}"
        # The stand logs the persona in with a test cookie that the admin API does not take; in Telegram the app sends initData.
        from FastAPI.auth import create_session_token
        page.evaluate("token => localStorage.setItem('pv_sess', token)", create_session_token(PERSONA_ID))
        page.evaluate("() => openGuide()")
        page.wait_for_selector(".gv-scope h1", timeout=10000)
        settle(page)
        entry = page.locator(".gv-book")
        if not rank:
            assert entry.count() == 0, "у игрока без роли входа в книгу администрации нет"
            page.evaluate("() => openAdminGuide()")
            page.wait_for_selector(".gv-scope .v3-empty", timeout=10000)
            assert "для персонала" in page.inner_text(".gv-scope .v3-empty"), page.inner_text(".gv-scope")
            print(f"OK player @{width}: no entry, the admin book answers «для персонала»")
            return
        assert entry.count() == 1, "персоналу — вход в Путеводитель администрации внизу Путеводителя игрока"
        entry.click()
        page.wait_for_function("() => _GV.book === 'admin' && _GV.data && document.querySelector('.gv-scope h1')?.textContent.includes('администрации')", timeout=10000)
        settle(page)
        topics = page.evaluate("() => _GV.data.topics.map(t => t.id)")
        assert topics == expected(rank), (who, sorted(set(topics) ^ set(expected(rank))))
        fails = page.evaluate(GEOMETRY, width)
        assert not fails, (who, width, "главная", fails)
        if shots:
            page.screenshot(path=f"{shots}/{who}-{width}-hub.png", full_page=True)

        page.fill("#gv-q", "замутить" if rank >= 3 else "жалоба")
        page.wait_for_selector("#gv-results .gv-row", timeout=5000)
        if rank >= 3:
            page.fill("#gv-q", "сантции")   # опечатка: «санкции»
            page.wait_for_selector("#gv-results .gv-row", timeout=5000)
        target = "sanctions" if rank >= 3 else "reports"
        page.evaluate(f"() => gvOpen('{target}')")
        page.wait_for_selector(".gv-where", timeout=5000)
        assert page.locator(".gv-where .v3-pill").count() == 1, "у темы раздела — кнопка «Открыть» в админку"
        assert "gvAdmin(" in page.get_attribute(".gv-where .v3-pill", "onclick")
        fails = page.evaluate(GEOMETRY, width)
        assert not fails, (who, width, "тема", fails)
        if shots:
            page.screenshot(path=f"{shots}/{who}-{width}-topic.png", full_page=True)
        problems = probe.take()
        assert not problems, (who, width, problems)
        print(f"OK {who} @{width}: {len(topics)} topics, entry from the player Guide, search, topic «{target}» with «Открыть»")
    finally:
        ctx.close()


def admin_entries(browser) -> None:
    """The admin page only opens the Mini App book: the address and the section to come back to."""
    me = {"user_id": 5000, "rank": 4, "rank_name": NAMES[4], "creator": False, "ranks": list(NAMES.values()),
          "sections": [{"key": k, "title": k, "min_rank": 2} for k in ("mychats", *[s for s in sections(4) if s != "mychats"])]}
    routes = {**ROUTES, "/me": me}
    html = admin_stand.read("index.html").replace("{{BASE}}", admin_stand.HOST).replace("{{VER}}", "stand")
    leaving: list[str] = []

    def handle(route):
        url = urlparse(route.request.url)
        if url.netloc != "stand.local":
            return route.abort()
        if "startapp=adminguide" in url.query:
            leaving.append(url.query)
            return route.fulfill(status=200, content_type="text/html", body="<p>mini app</p>")
        if url.path.startswith("/bot-admin/api/"):
            key = url.path[len("/bot-admin/api"):]
            body = routes.get(key)
            if body is None:
                return route.fulfill(status=404, content_type="application/json", body='{"detail":"нет фикстуры"}')
            status, body = body if isinstance(body, tuple) else (200, body)
            return route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
        name = url.path.rsplit("/", 1)[-1]
        if name.endswith(".json"):
            return route.fulfill(status=200, content_type="application/json", body=admin_stand.read(name))
        if name.startswith("admin") and name.endswith((".js", ".css")):
            return route.fulfill(status=200, content_type="text/javascript" if name.endswith(".js") else "text/css", body=admin_stand.read(name))
        return route.fulfill(status=200, content_type="text/html", body=html)

    ctx = browser.new_context(viewport={"width": 390, "height": 800})
    ctx.route("**/*", handle)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    def start(section: str) -> None:
        page.goto(f"{admin_stand.HOST}/bot-admin/")
        page.wait_for_selector("#tabs .nb", timeout=10000)
        page.evaluate(f"() => open('{section}')")
        page.wait_for_function(f"() => currentSection() === '{section}' && !document.querySelector('.admin-load')", timeout=10000)

    def leave(action: str) -> tuple[str, str]:
        with page.expect_navigation(timeout=10000):
            page.evaluate(action)
        return leaving[-1], page.evaluate("() => localStorage.getItem('pv_admin_tab')")

    start("people")
    assert page.locator(".top .hbtn.help").count() == 1, "значок «?» в шапке"
    query, tab = leave("() => document.querySelector('.top .hbtn.help').click()")
    assert "startapp=adminguide_find_people" in query and tab == "people", (query, tab)
    start("reports")
    query, tab = leave("() => agWhy('ban')")
    assert "startapp=adminguide_sanctions_reports" in query and tab == "reports", (query, tab)
    start("journal")
    query, tab = leave("() => document.querySelector('#tabs [data-tab=\"guide\"], #tabs [data-more]').click() || document.querySelector('[data-go=\"guide\"]')?.click()")
    assert "startapp=adminguide__journal" in query and tab == "journal", (query, tab)
    assert not errors, errors
    ctx.close()
    print("OK admin page: «?» → topic of the section, «Что это значит?» → topic of the action, tab «Путеводитель» → hub; «Назад» returns to the section")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shots", default=None)
    ap.add_argument("--widths", type=lambda s: [int(x) for x in s.split(",")], default=[320, 390, 430])
    ap.add_argument("--dsn", default=DEFAULT_DSN)
    ap.add_argument("--port", type=int, default=8403)
    args = ap.parse_args()
    if args.shots:
        os.makedirs(args.shots, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with Stand(args.port, args.dsn, skin="void", tier="SSS", rich=True) as stand, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_path())
        try:
            admin_entries(browser)
            for rank in (2, 4, 5, 0):   # роль 6 — только DEVELOPER_ID: её книгу (все темы) сверяет test_admin_guide_contract.py
                for width in args.widths:
                    miniapp(stand, browser, rank, width, args.shots)
        finally:
            set_rank(stand.dsn, 0)
            browser.close()


if __name__ == "__main__":
    main()
