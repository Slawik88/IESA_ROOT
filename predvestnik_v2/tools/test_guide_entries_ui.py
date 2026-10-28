#!/usr/bin/env python3
"""Ways into the player guide and its navigation, in Chromium on the production-topology stand (tools/ui_stand.py, needs PostgreSQL). S07.

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. python tools/test_guide_entries_ui.py [--widths 320,390,430] [--shots DIR]

Per width: the welcome window → «Первый день» → «‹» back on the profile; the profile row «Путеводитель» opens the guide in one tap;
💡 on a screen → «Подробнее в Путеводителе» → the topic → «‹» back on that screen (two taps in, one back); a typo finds its topic;
the search on a topic page shows the results and «‹» returns to the topic; the breadcrumbs lead to the group; a long topic has contents;
no page errors, no horizontal scroll. --shots saves the screens for the owner's «ок».
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from ui_smoke import DEVICES, FREEZE, INIT, chromium_path  # noqa: E402
from ui_stand import DEFAULT_DSN, Stand  # noqa: E402

READY = "() => typeof _profileData !== 'undefined' && !!_profileData && !!document.querySelector('#pro-main .v3-id') && pvLateCss.ready()"
ACTIVE = "() => _activePage"
TITLE = "() => document.querySelector('#pg-help h1')?.textContent || ''"


def shot(page, shots: str | None, name: str) -> None:
    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(shots) / f"{name}.png"))


def no_side_scroll(page, where: str) -> None:
    wide = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
    assert wide <= 1, f"{where}: page scrolls sideways by {wide}px"


def run(stand: Stand, browser, width: int, shots: str | None) -> None:
    ctx = browser.new_context(viewport={"width": width, "height": 780}, device_scale_factor=2 if shots else 1, is_mobile=True, has_touch=True)
    ctx.route("**/*", lambda r: r.abort() if any(h in r.request.url for h in ("telegram.org", "fonts.g")) else r.continue_())
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(INIT + stand.browser_init + ";localStorage.setItem('v3_lite','0');localStorage.removeItem('pv_welcomed');localStorage.removeItem('pv_guide_first');" + DEVICES["high"])
    page.goto(stand.base + "/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_function(READY, timeout=60000)
    page.wait_for_function("() => !document.getElementById('preloader')", timeout=20000)
    page.add_style_tag(content=FREEZE)
    tag = f"@{width}"

    # 1. First visit: the welcome window leads to «Первый день»; «‹» comes back to the profile.
    page.evaluate("() => _showWelcome()")
    page.wait_for_selector("dialog#modal[open] button:has-text('Первый день')", timeout=5000)
    shot(page, shots, f"1-welcome-{width}")
    page.click("dialog#modal[open] button:has-text('Первый день')")
    page.wait_for_function(f"() => ({TITLE})().startsWith('Первый день')", timeout=10000)
    assert page.evaluate("() => localStorage.getItem('pv_guide_first')") == "1", "reading «Первый день» hides the newcomer card"
    shot(page, shots, f"2-first-day-{width}")
    page.click("#pg-help .v3-head-back")
    page.wait_for_function(f"() => ({ACTIVE})() === 'profile'", timeout=5000)

    # 2. The profile row: one tap into the guide.
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    row = page.locator("#pg-profile .v3-row", has_text="Путеводитель")
    if shots:
        row.scroll_into_view_if_needed(); shot(page, shots, f"3-profile-row-{width}")
    row.click()
    page.wait_for_function(f"() => ({ACTIVE})() === 'help' && ({TITLE})() === 'Путеводитель'", timeout=10000)
    no_side_scroll(page, f"guide hub {tag}")
    shot(page, shots, f"4-hub-{width}")
    assert page.locator("#gv-group-start[open]").count() == 1 and page.locator("details.gv-group:not([open])").count() >= 5, "groups folded except the first"
    assert page.evaluate("() => parseFloat(getComputedStyle(document.getElementById('gv-q')).fontSize)") >= 16, "the search field is 16 px (no zoom on iOS)"

    # 3. A typo still finds its topic.
    page.fill("#gv-q", "питмоец")
    page.wait_for_selector("#gv-results >> text=Похоже на опечатку", timeout=5000)
    assert page.locator("#gv-results .gv-row", has_text="Питомцы").count() >= 1
    shot(page, shots, f"5-typo-{width}")
    page.fill("#gv-q", "")

    # 4. 💡 on a screen → the topic → back on that screen.
    page.evaluate("() => openInventory()")
    page.wait_for_function(f"() => ({ACTIVE})() === 'inventory' && !!document.querySelector('#pg-inventory .v3-guide-ic')", timeout=10000)
    no_side_scroll(page, f"inventory {tag}")
    shot(page, shots, f"6-inventory-head-{width}")
    page.click("#pg-inventory .v3-guide-ic")
    page.wait_for_selector("#g-sheet >> text=Подробнее в Путеводителе", timeout=5000)
    shot(page, shots, f"7-hint-sheet-{width}")
    page.click("#g-sheet >> text=Подробнее в Путеводителе")
    page.wait_for_function(f"() => ({ACTIVE})() === 'help' && ({TITLE})() !== 'Путеводитель'", timeout=10000)
    page.click("#pg-help .v3-head-back")
    page.wait_for_function(f"() => ({ACTIVE})() === 'inventory'", timeout=5000)

    # 5. A long topic: breadcrumbs, contents, the search right on the page; «‹» returns from the results to the topic.
    page.evaluate("() => openGuide('pass')")
    page.wait_for_function(f"() => ({TITLE})() === 'Пропуск сезона' || !!document.querySelector('#pg-help .gv-crumbs')", timeout=10000)
    assert page.locator("#pg-help .gv-crumbs .gv-crumb").count() == 2, "Путеводитель › Группа"
    page.click("#pg-help .gv-toc summary")
    shot(page, shots, f"8-topic-{width}")
    no_side_scroll(page, f"topic {tag}")
    page.fill("#pg-help #gv-q", "ключи")
    page.wait_for_function("() => _GV.view === 'hub' && !document.getElementById('gv-results').hidden", timeout=5000)
    page.click("#pg-help .v3-head-back")
    page.wait_for_function("() => _GV.view === 'topic' && _GV.topic === 'pass'", timeout=5000)
    page.click("#pg-help .gv-crumbs .gv-crumb[data-gv-key='crumb-group']")
    page.wait_for_function("() => _GV.view === 'hub' && document.getElementById('gv-group-progress').open", timeout=5000)

    assert not errors, errors
    ctx.close()
    print(f"OK {tag}: welcome → «Первый день» → back; profile 1 tap; 💡 → topic → back on the screen; typo; contents, crumbs, search from a topic")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--widths", type=lambda s: [int(x) for x in s.split(",")], default=[320, 390, 430])
    parser.add_argument("--shots", default=None)
    parser.add_argument("--port", type=int, default=8432)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    with Stand(port=args.port, dsn=args.dsn) as stand, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_path())
        for width in args.widths:
            run(stand, browser, width, args.shots)
        browser.close()


if __name__ == "__main__":
    main()
