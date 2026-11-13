"""S13b: real screens on 320/390/430, legal retry, classic pets and game return.

--existing captures the unchanged running stand for a before/after comparison.
Only the synthetic loopback persona is used; no Telegram or production access.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))

from playwright.sync_api import sync_playwright
from ui_smoke import FREEZE, PROFILE_READY, chromium_path, open_app
from ui_stand import DEFAULT_DSN, Stand, _env


def shot(page, directory: Path, name: str, width: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    page.add_style_tag(content=FREEZE)
    page.screenshot(path=str(directory / f"{name}-{width}.png"))


def check_width(page) -> None:
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "horizontal overflow"


def screens(stand, browser, args) -> None:
    for width in (320, 390, 430):
        ctx, page, probe = open_app(stand, browser, width)
        page.wait_for_function("!document.getElementById('preloader')")
        page.evaluate("openChatTracker()")
        page.locator('#pg-chat-tracker h1').wait_for()
        shot(page, args.shots, 'tracker', width)
        if not args.existing:
            assert page.locator('#pg-chat-tracker .v3-head').count() == 1
            check_width(page)
        page.evaluate("_sysFlags.pets_v2=false; _trClassic()")
        page.locator('#pg-pets .pet-tabs').wait_for()
        page.wait_for_timeout(500)
        shot(page, args.shots, 'pets-classic', width)
        if not args.existing:
            assert page.locator('#pg-pets .v3-head').count() == 1
            assert page.locator('#pg-pets .pt-main').first.bounding_box()['y'] < 544, 'main action below the 320×640 first screen'
            assert page.locator('#pg-pets .pet-pass').count() == 1, 'season-pass entry lost with the header'
            check_width(page)
        page.get_by_role('tab', name='Бестиарий', exact=False).click()
        shot(page, args.shots, 'pets-bestiary', width)
        check_width(page)
        if not args.existing:
            page.route('**/pets-v1/me', lambda route: route.fulfill(status=503, json={'detail': 'Нет связи.'}))
            page.evaluate('_trClassic()')
            page.locator('#pg-pets [role="alert"]').wait_for()
            assert page.locator('#pg-pets .v3-head').count() == 1
            assert all('http 503:' in item and '/pets-v1/me' in item for item in probe.take())
            page.unroute('**/pets-v1/me')
            page.get_by_role('button', name='Повторить', exact=True).click()
            page.locator('#pg-pets .pet-tabs').wait_for()
        page.goto(stand.base + '/', wait_until='domcontentloaded')
        page.wait_for_function(PROFILE_READY)
        page.wait_for_function("!document.getElementById('preloader')")
        page.evaluate('_tosGate({tos_accepted:false})')
        page.locator('#tos-gate').wait_for()
        shot(page, args.shots, 'tos', width)
        if not args.existing:
            check_width(page)
            for _ in range(5):
                page.keyboard.press('Tab')
                assert page.evaluate("document.getElementById('tos-gate').contains(document.activeElement)")
            pending = []
            page.route('**/legal/accept', lambda route: pending.append(route))
            page.get_by_role('button', name='Принять и играть', exact=True).click()
            page.wait_for_function("document.querySelector('#tos-gate button[onclick^=\"_tosAccept\"]').disabled")
            page.keyboard.press('Tab')
            assert page.evaluate("document.getElementById('tos-gate').contains(document.activeElement)")
            pending[0].fulfill(status=503, json={'detail': 'Нет связи. Попробуй ещё раз.'})
            page.wait_for_function("!document.querySelector('#tos-gate button[onclick^=\"_tosAccept\"]').disabled")
            assert page.locator('#tos-gate').is_visible(), "failed acceptance must keep the gate"
            failures = probe.take()
            assert failures and all('http 503:' in item and '/legal/accept' in item for item in failures), failures
            page.unroute('**/legal/accept')
        page.evaluate("document.getElementById('tos-gate').remove(); showLoginScreen('browser')")
        shot(page, args.shots, 'login', width)
        if not args.existing:
            assert page.locator('.login-orb svg').count() == 1
            check_width(page)
        for path in ('/rhythm-v2', '/minesweeper', '/league?game=rhythm'):
            page.goto(stand.base + path, wait_until='domcontentloaded')
            page.locator('#lg-title').wait_for()
            page.wait_for_timeout(1200)
            shot(page, args.shots, path.split('?')[0].strip('/'), width)
            if not args.existing:
                check_width(page)
                assert page.evaluate("getComputedStyle(document.body).getPropertyValue('--lg-gold').trim() == getComputedStyle(document.body).getPropertyValue('--v3-acc').trim()")
        if not args.existing:
            assert not probe.problems, probe.problems
        ctx.close()
        print(f'OK screens @{width}', flush=True)


def returns(stand, browser, warm=True) -> None:
    ctx, page, probe = open_app(stand, browser, 390)
    page.wait_for_function("!document.getElementById('preloader')")
    page.evaluate("switchPage('arena'); window.qaReturnSentinel='still-alive'")
    page.evaluate('openRhythmV2Game()')
    page.locator('#lg-title').wait_for()
    def new_pass(route):
        response = route.fetch()
        data = response.json()
        for season in data.get('seasons', []):
            if season.get('current'):
                season['level'] = 5
        route.fulfill(response=response, json=data)
    page.route('**/league-demo/api/pass', new_pass)
    started = time.perf_counter()
    page.locator('#lg-back-link').click()
    page.wait_for_function("typeof _activePage !== 'undefined' && _activePage === 'arena'")
    if not warm:
        assert page.evaluate("window.qaReturnSentinel !== 'still-alive'")
        print('OK evicted source → same Games screen after normal loading', flush=True)
        page.goto(stand.base + '/?startapp=guide_first-day', wait_until='domcontentloaded')
        page.wait_for_function("typeof _GV !== 'undefined' && _GV.topic === 'first-day'")
        page.evaluate('openPetsV1()')
        page.wait_for_function("typeof _tr !== 'undefined' && !!_tr.me")
        page.evaluate("leaveForGame('/rhythm-v2','pets')")
        page.locator('#lg-title').wait_for()
        def slow_profile(route):
            response = route.fetch()
            time.sleep(.7)
            route.fulfill(response=response)
        page.route('**/profile/me', slow_profile)
        page.locator('#lg-back-link').click()
        page.wait_for_function("typeof _activePage !== 'undefined' && _activePage === 'pets' && typeof _tr !== 'undefined' && !!_tr.me")
        assert not page.locator('#pg-pets .pet-tabs').count(), 'cold return ignored Trail flag'
        page.wait_for_timeout(600)
        assert page.evaluate('_activePage') == 'pets', 'old launch topic replaced the return screen'
        print('OK cold Pets return waits for flags and overrides the original guide launch', flush=True)
        ctx.close()
        return
    cached = page.evaluate("window.qaReturnSentinel === 'still-alive'")
    print(f'OK menu → game → same menu: {(time.perf_counter()-started)*1000:.0f} ms; restored from memory={cached}', flush=True)
    page.wait_for_function("document.querySelector('.v3-league-lv i')?.textContent === '5'")
    page.unroute('**/league-demo/api/pass')
    print('OK pass level refreshes after return', flush=True)
    page.evaluate("openGuide('rhythm')")
    page.wait_for_function("_GV.view === 'topic' && _GV.topic === 'rhythm'")
    page.evaluate("_gvLeave('/rhythm-v2','Ритм')")
    page.locator('#lg-title').wait_for()
    page.locator('#lg-mode button[data-gmode="ranked"]').wait_for()
    page.locator('#lg-mode button[data-gmode="ranked"]').click()
    page.wait_for_url('**/league?game=rhythm')
    page.reload(wait_until='domcontentloaded')
    page.locator('#lg-back-link').click()
    page.wait_for_function("typeof _GV !== 'undefined' && _GV.topic === 'rhythm' && _GV.view === 'topic'")
    print('OK guide → game → mode switch → refresh → same topic', flush=True)
    # A direct visit has no pending trip: stale sessionStorage cannot hijack Back.
    page.goto(stand.base + '/minesweeper', wait_until='domcontentloaded')
    assert page.locator('#lg-back-link').get_attribute('href') == stand.base.removeprefix(f'http://127.0.0.1:{stand.port}') + '/?startapp=games'
    page.locator('#lg-back-link').click()
    page.wait_for_function(PROFILE_READY)
    print('OK direct game visit → Games fallback', flush=True)
    ctx.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn', default=os.getenv('DATABASE_URL', DEFAULT_DSN))
    parser.add_argument('--port', type=int, default=18433)
    parser.add_argument('--shots', type=Path, required=True)
    parser.add_argument('--existing', action='store_true')
    parser.add_argument('--returns-only', action='store_true')
    args = parser.parse_args()
    stand = Stand(args.port, args.dsn, skin='void', tier='SSS', rich=True)
    if args.existing:
        _env(args.port, args.dsn)
    with nullcontext(stand) if args.existing else stand:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chromium_path(), ignore_default_args=['--disable-back-forward-cache'])
            if not args.existing or args.returns_only:
                returns(stand, browser)
            if not args.returns_only:
                screens(stand, browser, args)
            browser.close()
            if not args.existing:
                cold_browser = pw.chromium.launch(executable_path=chromium_path())
                returns(stand, cold_browser, warm=False)
                cold_browser.close()


if __name__ == '__main__':
    main()
