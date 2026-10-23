"""Casino browser proof against the real local app/PostgreSQL, including a lost committed response.

Run after bootstrap_test_db.py: python tools/verify_casino_ui.py --dsn <loopback DSN>
Uses the repository's UI stand and Playwright. CHROMIUM_PATH may select an installed browser.
Only the synthetic UI-stand persona is funded; never accepts a remote database.
"""
from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import asyncpg
from playwright.sync_api import sync_playwright
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import casino_v1, system_flags
from ui_stand import PERSONA_ID, Stand
from ui_smoke import GEOMETRY, INIT, PROFILE_READY, chromium_path


async def seed(dsn):
    conn = await asyncpg.connect(dsn, server_settings={"search_path": "predvestnik,public"})
    try:
        db = PGAdapter(conn)
        await casino_v1.ensure_tables(db)
        await system_flags.set_flag(db, 'game_casino_v1', True)
        async with conn.transaction():
            await conn.execute("SELECT set_config('predvestnik.casino_wallet_version','2',true)")
            await conn.execute("INSERT INTO casino_v1_wallets(user_id,chips,redeemable_chips,wallet_version) VALUES($1,20000,10000,2) "
                               "ON CONFLICT(user_id) DO UPDATE SET chips=20000,redeemable_chips=10000,wallet_version=2,bought_today=0", PERSONA_ID)
    finally:
        await conn.close()


async def round_count(dsn):
    conn = await asyncpg.connect(dsn, server_settings={"search_path": "predvestnik,public"})
    try:
        return await conn.fetchval('SELECT COUNT(*) FROM casino_v1_rounds WHERE user_id=$1', PERSONA_ID)
    finally:
        await conn.close()


def count_rounds(dsn):
    # Sync Playwright owns this thread's loop; database probes use their own loop.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, round_count(dsn)).result()


async def purchase_state(dsn):
    conn = await asyncpg.connect(dsn, server_settings={"search_path": "predvestnik,public"})
    try:
        return tuple(await conn.fetchrow('SELECT (SELECT COUNT(*) FROM casino_v1_purchases WHERE user_id=$1), '
                                        '(SELECT user_balance_mora FROM users WHERE user_tg_id=$1)', PERSONA_ID))
    finally:
        await conn.close()


def purchases(dsn):
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, purchase_state(dsn)).result()


async def withdrawal_state(dsn):
    conn = await asyncpg.connect(dsn, server_settings={"search_path": "predvestnik,public"})
    try:
        return tuple(await conn.fetchrow('SELECT (SELECT COUNT(*) FROM casino_v1_withdrawals WHERE user_id=$1), '
                                        '(SELECT user_balance_mora FROM users WHERE user_tg_id=$1), '
                                        '(SELECT redeemable_chips FROM casino_v1_wallets WHERE user_id=$1)', PERSONA_ID))
    finally:
        await conn.close()


def withdrawals(dsn):
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, withdrawal_state(dsn)).result()


def ready(page, stand):
    page.goto(stand.url, wait_until='domcontentloaded')
    page.wait_for_function(PROFILE_READY, timeout=30000)
    page.locator('#preloader').wait_for(state='hidden',timeout=15000)
    page.evaluate('openCasino()')
    page.wait_for_function('() => _cs.me && document.querySelector("#cs-go")', timeout=15000)


def idle(page):
    page.wait_for_function('() => !_cs.busy', timeout=20000)


def run(dsn, shots):
    shots.mkdir(parents=True, exist_ok=True)
    asyncio.run(seed(dsn))
    with Stand(8403, dsn, skin='void', tier='SSS', rich=True) as stand, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_path())
        errors = []
        ctx = browser.new_context(viewport={'width':390, 'height':780}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.add_init_script(INIT)
        page.on('pageerror', lambda e: errors.append(str(e)))
        ready(page, stand)
        # Both pools/all games on narrow phones, primary CTA above the dock at 320x640.
        for width in (320,390,430):
            for height in (640,780):
                page.set_viewport_size({'width':width, 'height':height})
                for game in ('slots','wheel','dice'):
                    for funds in ('bonus', 'redeemable'):
                        page.evaluate('([game,funds]) => { casinoGame(game); casinoFunds(funds); }', [game,funds])
                        assert not page.evaluate(GEOMETRY, width)
                        go, dock = page.locator('#cs-go').bounding_box(), page.locator('.nav').bounding_box()
                        if go['y'] + go['height'] > dock['y']:
                            page.screenshot(path=str(shots / f'overflow-{game}-{funds}-{width}-{height}.png'))
                        assert go['y'] + go['height'] <= dock['y'], (width,height,game,funds,go,dock)
                    if height == 780:
                        page.screenshot(path=str(shots / f'{game}-{width}.png'), full_page=True)
        page.set_viewport_size({'width':390,'height':780})
        # Draft, accordion and focus survive ordinary rerenders and rejected money actions.
        page.evaluate("casinoFunds('redeemable'); document.querySelector('.cs-exchange').open=true; document.querySelector('[data-cs-detail=rules]').open=true")
        page.locator('#cs-withdraw-amount').fill('73')
        page.evaluate("casinoGame('dice');casinoChance(25);casinoStake(50)")
        assert page.locator('#cs-withdraw-amount').input_value()=='73'
        assert page.locator('.cs-exchange').get_attribute('open') is not None
        assert page.locator('[data-cs-detail=rules]').get_attribute('open') is not None
        page.locator('#cs-withdraw-amount').fill('999999')
        page.locator('#cs-withdraw-amount').press('Enter')
        assert 'Доступно' in page.locator('#cs-withdraw-message').inner_text()
        assert page.locator('#cs-withdraw-amount').evaluate('(e)=>e===document.activeElement')
        assert not page.evaluate('!!_cs.pending.withdraw')
        page.locator('#cs-withdraw-amount').fill('73')
        page.route('**/casino-v1/withdraw',lambda r:r.fulfill(status=409,content_type='application/json',body='{"detail":"Обновите сумму вывода"}'))
        page.locator('.cs-exchange button[type="submit"]').click();idle(page)
        assert page.locator('#cs-withdraw-amount').input_value()=='73'
        assert 'Обновите' in page.locator('#cs-withdraw-message').inner_text()
        assert page.locator('.cs-exchange button[type="submit"]').evaluate('(e)=>e===document.activeElement')
        page.unroute('**/casino-v1/withdraw')
        held=[]
        page.route('**/casino-v1/withdraw',lambda r:held.append(r))
        page.locator('.cs-exchange button[type="submit"]').click();page.wait_for_function('() => _cs.busy')
        page.locator('.cs-exchange summary').click()
        assert page.locator('.cs-exchange').get_attribute('open') is None
        held[0].fulfill(status=409,content_type='application/json',body='{"detail":"Проверьте сохранённую сумму"}');idle(page)
        assert page.locator('.cs-exchange').get_attribute('open') is not None
        assert 'сохранённую' in page.locator('#cs-withdraw-message').inner_text()
        assert page.locator('#cs-withdraw-amount').input_value()=='73'
        page.screenshot(path=str(shots/'cashout-inline-error.png'))
        page.unroute('**/casino-v1/withdraw')
        page.locator('#cs-withdraw-amount').fill('75')
        page.locator('.cs-shop:not(.cs-exchange)').evaluate('(e)=>e.open=true')
        page.route('**/casino-v1/buy',lambda r:r.fulfill(status=409,content_type='application/json',body='{"detail":"Покупка пока недоступна"}'))
        page.locator('button[onclick="casinoBuy(this,100)"]').click();idle(page)
        assert 'Покупка' in page.locator('#cs-buy-message').inner_text()
        assert page.locator('.cs-shop:not(.cs-exchange)').get_attribute('open') is not None
        page.unroute('**/casino-v1/buy')
        page.evaluate("casinoGame('slots'); casinoFunds('bonus')")
        page.locator('#cs-go').click()
        page.wait_for_function('() => _cs.busy')
        assert page.locator('.cs-reel.spin').count() == 3
        first = page.locator('.cs-strip').first.evaluate('(e) => getComputedStyle(e).transform')
        page.wait_for_timeout(80)
        second = page.locator('.cs-strip').first.evaluate('(e) => getComputedStyle(e).transform')
        assert first != second, 'strips must physically scroll'
        assert page.locator('.cs-tabs button:not(:disabled)').count() == 0
        page.screenshot(path=str(shots / 'rolling.png'))
        idle(page)
        assert page.evaluate('() => _cs.last.detail.reels.every((s,i) => document.querySelector("#cs-reel-"+i+" .cs-strip").children[1].dataset.symbol === s)')
        assert page.locator('.cs-strip').evaluate_all('(es) => es.every(e => !e.getAnimations().length)')
        page.screenshot(path=str(shots / 'result.png'), full_page=True)

        # Server commits, but the response is lost: reload and retry the SAME frozen body/id.
        before = count_rounds(dsn)
        page.evaluate("casinoFunds('redeemable')")
        requests = []
        def lose_response(route):
            requests.append(route.request.post_data_json)
            response = route.fetch()
            assert response.status == 200
            route.abort('failed')
        page.route('**/casino-v1/play', lose_response)
        page.locator('#cs-go').click()
        idle(page)
        assert page.evaluate('() => !!_cs.pending.play')
        assert page.locator('.cs-funds button:not(:disabled)').count() == 0
        page.evaluate("casinoFunds('bonus')")
        assert page.evaluate("() => _cs.funds === 'redeemable'")
        assert 'не спишет' in page.locator('#cs-note').inner_text()
        assert count_rounds(dsn) == before + 1
        page.unroute('**/casino-v1/play')
        ready(page, stand)  # same tab/sessionStorage survives navigation
        assert page.locator('#cs-go').inner_text() == 'Проверить результат'
        assert page.evaluate("() => _cs.funds === 'redeemable' && _cs.pending.play.funds === 'redeemable'")
        # An expired session before replay lookup must not discard the committed action id.
        def expired(route):
            requests.append(route.request.post_data_json)
            route.fulfill(status=401, content_type='application/json', body='{"detail":"Войдите снова."}')
        page.route('**/casino-v1/play', expired)
        page.locator('#cs-go').click(); idle(page)
        assert page.evaluate('() => !!_cs.pending.play')
        page.unroute('**/casino-v1/play')
        ready(page, stand)
        def retry_response(route):
            requests.append(route.request.post_data_json)
            route.continue_()
        page.route('**/casino-v1/play', retry_response)
        page.locator('#cs-go').click()
        idle(page)
        assert requests[0] == requests[1] == requests[2]
        assert count_rounds(dsn) == before + 1
        assert page.evaluate('() => !_cs.pending.play')
        page.unroute('**/casino-v1/play')

        # Purchases also retain their identity through a lost response and a temporary gate.
        bought_before, mora_before = purchases(dsn)
        buys = []
        def lose_purchase(route):
            buys.append(route.request.post_data_json)
            assert route.fetch().status == 200
            route.abort('failed')
        page.route('**/casino-v1/buy', lose_purchase)
        page.locator('.cs-shop:not(.cs-exchange)').evaluate('(e)=>e.open=true')
        page.locator('button[onclick="casinoBuy(this,100)"]').click(); idle(page)
        assert page.evaluate('() => !!_cs.pending.buy')
        assert purchases(dsn) == (bought_before+1, mora_before-100)
        page.unroute('**/casino-v1/buy')

        ready(page, stand)
        def throttled(route):
            buys.append(route.request.post_data_json)
            route.fulfill(status=429, content_type='application/json', body='{"detail":"Попробуйте позже."}')
        page.route('**/casino-v1/buy', throttled)
        page.locator('button[onclick="casinoBuy(this,100)"]').click(); idle(page)
        assert page.evaluate('() => !!_cs.pending.buy')
        page.unroute('**/casino-v1/buy')
        def retry_purchase(route):
            buys.append(route.request.post_data_json); route.continue_()
        page.route('**/casino-v1/buy', retry_purchase)
        page.locator('button[onclick="casinoBuy(this,100)"]').click(); idle(page)
        assert buys[0] == buys[1] == buys[2]
        assert purchases(dsn) == (bought_before+1, mora_before-100)
        assert page.evaluate('() => !_cs.pending.buy')
        page.unroute('**/casino-v1/buy')

        # A committed cashout survives reload plus throttle/auth failures without a second debit or Mora credit.
        page.evaluate("casinoFunds('redeemable')")
        withdrawn_before, mora_before, real_before = withdrawals(dsn)
        cashouts = []
        def lose_cashout(route):
            cashouts.append(route.request.post_data_json)
            assert route.fetch().status == 200
            route.abort('failed')
        page.route('**/casino-v1/withdraw', lose_cashout)
        page.locator('.cs-exchange').evaluate('(e)=>e.open=true')
        page.locator('#cs-withdraw-amount').fill('75')
        for width in (320,390,430):
            for height in (640,780):
                page.set_viewport_size({'width':width,'height':height})
                page.locator('.cs-exchange').evaluate('(e) => e.scrollIntoView({block:"center",behavior:"instant"})')
                form=page.locator('.cs-exchange').bounding_box()
                submit=page.locator('.cs-exchange button[type="submit"]').bounding_box()
                dock=page.locator('.nav').bounding_box()
                assert form['y']>=50 and submit['y']+submit['height']<=dock['y'],(width,height,form,submit,dock)
                page.screenshot(path=str(shots / f'cashout-expanded-{width}-{height}.png'))
        page.set_viewport_size({'width':390,'height':780})
        page.locator('.cs-exchange').evaluate('(e) => e.scrollIntoView({block:"center",behavior:"instant"})')
        page.screenshot(path=str(shots / 'cashout-expanded.png'))
        page.locator('.cs-exchange button[type="submit"]').click(); idle(page)
        expected = (withdrawn_before + 1, mora_before + 75, real_before - 75)
        assert withdrawals(dsn) == expected
        assert page.evaluate('() => _cs.pending.withdraw.chips === 75')
        assert page.locator('.cs-funds button:not(:disabled)').count() == 0
        assert page.locator('#cs-withdraw-amount').is_disabled()
        page.evaluate("casinoFunds(_cs.funds === 'bonus' ? 'redeemable' : 'bonus')")
        assert page.evaluate("() => _cs.funds === 'redeemable'")
        page.unroute('**/casino-v1/withdraw')
        for status in (429,401):
            ready(page, stand)
            assert page.locator('#cs-withdraw-amount').input_value() == '75'
            assert page.locator('#cs-withdraw-amount').is_disabled()
            def reject_cashout(route, _request=None, response_status=status):
                cashouts.append(route.request.post_data_json)
                route.fulfill(status=response_status, content_type='application/json', body='{"detail":"Повторите позже."}')
            page.route('**/casino-v1/withdraw', reject_cashout)
            page.locator('.cs-exchange button[type="submit"]').click(); idle(page)
            assert page.evaluate('() => _cs.pending.withdraw.chips === 75')
            assert withdrawals(dsn) == expected
            page.unroute('**/casino-v1/withdraw')
        ready(page, stand)
        def retry_cashout(route):
            cashouts.append(route.request.post_data_json); route.continue_()
        page.route('**/casino-v1/withdraw', retry_cashout)
        page.locator('.cs-exchange button[type="submit"]').click(); idle(page)
        assert len(cashouts) == 4 and all(body == cashouts[0] for body in cashouts)
        assert withdrawals(dsn) == expected
        assert page.evaluate('() => !_cs.pending.withdraw')
        page.unroute('**/casino-v1/withdraw')
        page.screenshot(path=str(shots / 'cashout.png'), full_page=True)

        # Navigate away during rolling: request finishes, decorations stop, return shows final state.
        page.locator('#cs-go').click()
        page.wait_for_function('() => _csAnimations.some(a => a.effect.getTiming().iterations === 1)')
        page.wait_for_timeout(200)
        page.evaluate("switchPage('profile')")
        idle(page)
        assert page.locator('.cs-strip').evaluate_all('(es) => es.every(e => !e.getAnimations().length)')
        page.evaluate('openCasino()')
        page.wait_for_function('() => _cs.me && !_cs.busy')
        page.evaluate('openAchievementsV1()')
        page.wait_for_function('() => !!document.querySelector("#ach-tab-casino")')
        page.locator('#ach-tab-casino').click()
        page.wait_for_function('() => document.querySelectorAll("#ach-panel .ach-row").length === 6')
        assert 'награда появится позже' not in page.locator('#pg-achievements-v1').inner_text().lower()
        page.screenshot(path=str(shots / 'achievements.png'), full_page=True)
        page.locator('#ach-panel .ach-row').first.click()
        assert 'Валютной награды нет' in page.locator('.ach-sheet').inner_text()
        page.evaluate('CM()')
        assert not errors, errors
        ctx.close()

        # System reduced motion: same server outcome, no reel animations.
        calm = browser.new_context(viewport={'width':320,'height':640}, reduced_motion='reduce')
        page = calm.new_page(); page.add_init_script(INIT)
        page.on('pageerror', lambda e: errors.append(str(e)))
        ready(page, stand)
        page.locator('#cs-go').click(); idle(page)
        assert page.locator('.cs-strip').evaluate_all('(es) => es.every(e => !e.getAnimations().length)')
        assert page.locator('#cs-out small').count() == 1
        calm.close(); browser.close()
        assert not errors, errors
    print('OK: casino UI — 36 visible layouts/CTA, draft/inline errors/focus/closed-during-request, reels/landing, lost bet/purchase/cashout + reload + 401/429 + exact replay, frozen pool/amount, braking cancellation, 6 badges, reduced motion')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn', required=True)
    parser.add_argument('--shots', type=Path, default=ROOT.parent/'output/playwright/casino-proof')
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in {'127.0.0.1','localhost','::1'}:
        raise SystemExit('loopback database only')
    run(args.dsn, args.shots)
