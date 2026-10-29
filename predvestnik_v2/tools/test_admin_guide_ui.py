#!/usr/bin/env python3
"""The administration guide is the player Guide screen of the Mini App (admin book), per role. S09, S09b.

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. python tools/test_admin_guide_ui.py [--shots DIR] [--widths 320,390,430]

1. Mini App on the production-topology stand (tools/ui_stand.py, the persona gets bot roles 2, 4, 5 in turn;
   role 6 is DEVELOPER_ID only, its book is checked by test_admin_guide_contract.py): the player Guide shows staff
   the entry «Путеводитель администрации»; the admin book has exactly the topics of the role (the rule of services/admin_guide.py computed
   here from the code), search with a typo, a topic with «Открыть» into its admin section; nothing is wider than the screen.
   A player without a role gets «this book is for staff», not an error.
2. Admin page on the fixture stand (tools/admin_stand.py): the same screen as a layer over the admin (bot-admin/guide.html). «?» opens the
   topic of the current section, «Что это значит?» of a dangerous action — its topic, the «Путеводитель» tab — the hub; «Назад» and Esc
   close the layer and what was under it is untouched (search text, the half-filled window, the undo countdown above the layer);
   «Открыть» of a topic switches the admin section; the admin page never reloads.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
from pathlib import Path

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
        assert entry.count() == 1, "персоналу — вход в Путеводитель администрации сверху Путеводителя игрока"
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


def admin_entries(browser, width: int, shots: str | None) -> None:
    """The admin page shows the book as a layer over itself: what was open under it (a card, a half-filled window, the undo countdown) stays."""
    me = {"user_id": 5000, "rank": 5, "rank_name": NAMES[5], "creator": False, "ranks": list(NAMES.values()),   # баланс в карточке — с роли 5
          "sections": [{"key": k, "title": k, "min_rank": 2} for k in ("mychats", *[s for s in sections(5) if s != "mychats"])]}
    from services.admin_guide import for_reader
    routes = {**ROUTES, "/me": me, "/guide": for_reader(rank=5, sections=sections(5))}
    ctx = browser.new_context(viewport={"width": width, "height": 800}, has_touch=True, is_mobile=True)
    ctx.add_init_script("window.ADMIN_UNDO_MS = 4000")
    ctx.route("**/*", admin_stand.handler(routes))
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    left: list[str] = []
    page.on("framenavigated", lambda f: f == page.main_frame and left.append(f.url))
    frame = lambda: page.frame_locator("#guide-layer iframe")  # noqa: E731
    layer_open = "() => { const l = document.querySelector('#guide-layer'); return !!l && !l.hidden; }"

    def shown(title_part: str) -> None:
        page.wait_for_function(layer_open, timeout=5000)
        frame().locator(".gv-scope h1").first.wait_for(timeout=10000)
        page.wait_for_function("t => { const f = document.querySelector('#guide-layer iframe'); const h = f && f.contentDocument.querySelector('.gv-scope h1');"
                               " return h && h.textContent.includes(t); }", arg=title_part, timeout=10000)

    def back() -> None:
        frame().locator(".v3-head-back").first.click()
        page.wait_for_function(f"() => !({layer_open})()", timeout=5000)

    page.goto(f"{admin_stand.HOST}/bot-admin/")
    page.wait_for_selector("#tabs .nb", timeout=10000)
    page.wait_for_function("() => currentSection() === 'mychats' || currentSection() === 'people'")
    page.evaluate("() => open('people')")
    page.wait_for_function("() => currentSection() === 'people' && !document.querySelector('.admin-load')")
    start = page.url
    titles = {t["id"]: t["title"] for t in GUIDE["topics"]}

    # «?» в разделе — его тема одним касанием; поиск в разделе под слоем не трогается
    field = page.locator("#main input").first
    field.fill("анна")
    page.click(".top .hbtn.help")
    shown(titles["find"])
    fails = frame().locator("body").evaluate("() => document.documentElement.scrollWidth > innerWidth ? ['шире экрана'] : []")
    assert not fails, fails
    if shots:
        page.screenshot(path=f"{shots}/layer-find-{width}.png")
    back()
    assert field.input_value() == "анна", "раздел под слоем остался как был"

    # «Что это значит?» в окне опасного действия: окно с набранным остаётся под слоем
    page.evaluate("() => playerView($('#main'), 5000)")
    page.wait_for_selector("[data-quick=balance]", timeout=5000)
    page.click("[data-quick=balance]")
    page.wait_for_selector("#sheet [data-ag-why]", timeout=5000)
    amount = page.locator("#sheet input").first
    amount.fill("777")
    page.click("#sheet [data-ag-why]")
    shown(titles["player-power"])
    if shots:
        page.screenshot(path=f"{shots}/layer-why-{width}.png")
    frame().locator("body").press("Escape")   # клавиша Esc на компьютере — тот же «Назад»
    page.wait_for_function(f"() => !({layer_open})()", timeout=5000)
    assert not page.locator("#sheet").is_hidden() and amount.input_value() == "777", "окно действия и введённое не потерялись"
    page.click("#scancel")

    # Отсчёт «Отменить» виден поверх слоя и не прерывается
    page.click("[data-quick=mute]")
    page.wait_for_selector("#sok", timeout=5000)
    page.click("#sok")
    page.wait_for_selector(".undobar .undo", timeout=5000)
    page.click(".top .hbtn.help")
    page.wait_for_function(layer_open, timeout=5000)
    box = page.locator(".undobar .undo").first.bounding_box()
    on_top = page.evaluate("([x, y]) => !!document.elementFromPoint(x, y)?.closest('.undobar')", [box["x"] + 10, box["y"] + box["height"] / 2])
    assert on_top, "полоса «Отменить» под слоем не видна"
    back()

    # Вкладка «Путеводитель» (здесь — в «Ещё»): главная книги, раздел не меняется; кнопка темы «Открыть» ведёт в раздел админки
    before = page.evaluate("() => currentSection()")
    page.click("#tabs [data-more]")
    page.click("#sheet [data-go='guide']")
    shown("Путеводитель администрации")
    assert page.evaluate("() => currentSection()") == before, "вкладка не уводит из раздела"
    for word in ("заглушить", "пред", "разбан"):   # слова модераторов ведут к теме наказаний
        frame().locator(".gv-search input").fill(word)
        frame().locator("#gv-results .gv-row").first.wait_for(timeout=5000)
        assert titles["sanctions"] in frame().locator("#gv-results").inner_text(), word
    frame().locator(".gv-search input").fill("жалоба")
    frame().locator("#gv-results .gv-row").first.wait_for(timeout=5000)
    frame().locator("body").evaluate("() => gvOpen('reports')")
    frame().locator(".gv-where .v3-pill").first.click()
    page.wait_for_function(f"() => !({layer_open})() && currentSection() === 'reports'", timeout=5000)

    assert left == [start] or not left[1:], f"админка не перезагружалась: {left}"
    # Кнопка из «бот админ помощь» в личке: админка открывается сразу со слоем, под ним — обычный раздел
    page.goto(f"{admin_stand.HOST}/bot-admin?open=guide")
    shown("Путеводитель администрации")
    assert page.evaluate("() => currentSection()") not in ("", "guide")
    assert not errors, errors
    ctx.close()
    print(f"OK admin page @{width}: «?», «Что это значит?», вкладка — слой поверх раздела; поиск, окно с суммой и «Отменить» на месте; «Открыть» — в раздел")


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
            for width in args.widths:
                admin_entries(browser, width, args.shots)
            for rank in (2, 4, 5, 0):   # роль 6 — только DEVELOPER_ID: её книгу (все темы) сверяет test_admin_guide_contract.py
                for width in args.widths:
                    miniapp(stand, browser, rank, width, args.shots)
        finally:
            set_rank(stand.dsn, 0)
            browser.close()


if __name__ == "__main__":
    main()
