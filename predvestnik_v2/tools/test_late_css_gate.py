#!/usr/bin/env python3
"""The screen stylesheets that the first screen does not need load without blocking (index.html, media="print" + pvLateCss); the splash, the windows
over it and a link from the chat wait for them, so a slow network never shows an unstyled screen.

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers BOT_TOKEN=1:x PYTHONPATH=. python tools/test_late_css_gate.py [--dsn …]

Runs the production-topology stand (tools/ui_stand.py, needs PostgreSQL) in Chromium:
1. quests-v3.css is held back and the app is opened by the link «quests»: the splash fades and the quests page is built only after it arrived;
   a window opened meanwhile is invisible and not clickable, then shows up.
2. quests-v3.css fails: the gate opens on the error, long before the 12 s fallback.
3. the browser never reports the load (handlers stripped): the fallback opens the gate after 12 s and switches every late sheet on.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from ui_smoke import DEVICES, INIT, chromium_path  # noqa: E402
from ui_stand import DEFAULT_DSN, Stand  # noqa: E402

LATE = ("mafia-online-v3", "settings-v3", "looks-v3", "collect-v3", "toast-gift-v3", "quests-v3", "inventory-v3", "promo-v3", "achievements-v3", "chests-v3",
        "trail-v3", "guide-v3", "news-v3", "pass-v3", "store-v3", "confirm-v3", "monolith-v3", "pets-v3", "casino-v3", "coin-market-v2")
# what the page saw, in performance.now() milliseconds: when the splash started to fade, when the quests page got its markup
WATCH = """
window.__t = {};
new MutationObserver(() => {
  const p = document.getElementById('preloader'), q = document.getElementById('pg-questlog');
  if (p && p.classList.contains('pl-done') && !__t.splash) __t.splash = performance.now();
  if (q && q.children.length && !__t.quests) __t.quests = performance.now();
}).observe(document, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});
"""
STRIP = """
new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => {
  if (n.tagName === 'LINK' && /pvLateCss/.test(n.getAttribute('onload') || '')) { n.onload = n.onerror = null; }
}))).observe(document, {subtree: true, childList: true});
"""


def check_markup() -> None:
    index = (ROOT / "FastAPI/static/index.html").read_text(encoding="utf-8")
    late = re.findall(r'<link rel="stylesheet" href="\{\{BASE\}\}/static/([\w-]+)\.css\?v=\{\{ASSET_VER\}\}" media="print" onload="pvLateCss\(this\)" onerror="pvLateCss\(this\)"/>', index)
    assert tuple(sorted(late)) == tuple(sorted(LATE)), sorted(set(late) ^ set(LATE))
    assert index.index("window.pvLateCss") < index.index('href="{{BASE}}/static/app.css'), "the gate is defined before any stylesheet"
    css = (ROOT / "FastAPI/static/app.css").read_text(encoding="utf-8")
    assert "html.pv-css-wait dialog[open]:not(.pv-support) { opacity: 0; pointer-events: none; }" in css
    js = (ROOT / "FastAPI/static/app.02.js").read_text(encoding="utf-8")
    assert "pvLateCss.then(_plSkip)" in js and "pvLateCss.then(go)" in js


def open_app(stand: Stand, browser, *, route=None, extra: str = "", deep: str = ""):
    ctx = browser.new_context(viewport={"width": 390, "height": 780}, is_mobile=True, has_touch=True)
    ctx.route("**/*", lambda r: r.abort() if any(h in r.request.url for h in ("telegram.org", "fonts.g")) else (route(r) if route else r.continue_()))
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(INIT + stand.browser_init + ";localStorage.setItem('v3_lite','0');" + DEVICES["mid"] + WATCH + extra)
    page.goto(stand.base + "/" + (f"?startapp={deep}" if deep else ""), wait_until="commit", timeout=60000)
    return ctx, page, errors


def held_quests(held: list):
    """quests-v3.css gets no answer until the test releases it (an unanswered route simply waits)."""
    def handle(r):
        if "/static/quests-v3.css" in r.request.url:
            held.append(r)
        else:
            r.continue_()
    return handle


def scenario_slow(stand: Stand, browser) -> None:
    held: list = []
    ctx, page, errors = open_app(stand, browser, route=held_quests(held), deep="quests")
    page.wait_for_function("() => document.readyState !== 'loading' && typeof OM === 'function' && typeof _profileData !== 'undefined' && !!_profileData", timeout=60000)
    page.wait_for_timeout(2500)        # the splash timer (1.3 s) and the link (0.38 s) are long due
    state = page.evaluate("""() => { const waiting = !pvLateCss.ready() && document.documentElement.classList.contains('pv-css-wait');
        OM('Проверка', '<p>окно</p>', []); const m = getComputedStyle(document.getElementById('modal'));
        return [waiting, !__t.splash, !__t.quests, m.opacity, m.pointerEvents]; }""")
    assert held and state == [True, True, True, "0", "none"], state
    released = page.evaluate("() => performance.now()")
    route = held.pop()
    route.fulfill(response=route.fetch())
    page.wait_for_function("() => pvLateCss.ready()", timeout=30000)
    shown = page.evaluate("() => getComputedStyle(document.getElementById('modal')).opacity")
    assert shown == "1", shown
    page.evaluate("() => CM()")
    page.wait_for_function("() => __t.splash && __t.quests", timeout=30000)
    t = page.evaluate("() => __t")
    assert t["splash"] >= released and t["quests"] >= released, (t, released)
    applied = page.evaluate("() => [...document.querySelectorAll('link[onload^=\"pvLateCss\"]')].every(l => l.media === 'all')")
    assert applied and page.evaluate("() => document.querySelector('#pg-questlog').classList.contains('active')"), "the link opened the quests page"
    assert not errors, errors
    ctx.close()
    print(f"OK slow sheet: released {released:.0f} ms, splash {t['splash']:.0f} ms, quests {t['quests']:.0f} ms, the window was hidden until then")


def scenario_failed(stand: Stand, browser) -> None:
    ctx, page, errors = open_app(stand, browser, route=lambda r: r.abort() if "/static/quests-v3.css" in r.request.url else r.continue_())
    page.wait_for_function("() => window.__t && __t.splash", timeout=60000)
    splash = page.evaluate("() => __t.splash")
    assert splash < 11000, splash
    assert not errors, errors
    ctx.close()
    print(f"OK failed sheet: the gate opened on the error, splash {splash:.0f} ms")


def scenario_no_load_event(stand: Stand, browser) -> None:
    ctx, page, errors = open_app(stand, browser, extra=STRIP)
    page.wait_for_function("() => window.__t && __t.splash", timeout=60000)
    splash = page.evaluate("() => __t.splash")
    assert splash >= 12000, splash
    assert page.evaluate("() => [...document.querySelectorAll('link[onload^=\"pvLateCss\"]')].every(l => l.media === 'all')"), "the fallback switched the sheets on"
    assert not errors, errors
    ctx.close()
    print(f"OK no load event: the fallback opened the gate at {splash:.0f} ms")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--port", type=int, default=8414)
    args = parser.parse_args()
    check_markup()
    print(f"OK markup: {len(LATE)} late sheets, gate first")
    from playwright.sync_api import sync_playwright
    with Stand(port=args.port, dsn=args.dsn) as stand, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_path())
        scenario_slow(stand, browser)
        scenario_failed(stand, browser)
        scenario_no_load_event(stand, browser)
        browser.close()


if __name__ == "__main__":
    main()
