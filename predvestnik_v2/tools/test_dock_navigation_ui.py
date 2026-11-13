"""S12: real pinned More, search, wallet focus/Back, flags and deep links on the local stand."""
from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from playwright.sync_api import sync_playwright
from ui_smoke import FREEZE, INIT, chromium_path
from ui_stand import Stand, set_game_flags

READY = "() => !!document.querySelector('#pro-main .v3-id') && pvLateCss.ready() && !document.getElementById('preloader')"
TELEGRAM = """window.Telegram={WebApp:{initData:'',ready(){},expand(){},onEvent(){},offEvent(){},isVersionAtLeast(){return false;},
BackButton:{onClick(fn){window.__backHandler=fn;},show(){window.__backVisible=true;},hide(){window.__backVisible=false;}}}};"""


async def flags(dsn: str, exchange: bool, pets: bool, chests: bool) -> None:
    import asyncpg
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import system_flags
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("SET search_path TO predvestnik, public")
        for key, value in (("economy_player_exchange_v1", exchange), ("pets_v2", pets), ("content_chests_v1", chests)):
            await system_flags.set_flag(PGAdapter(conn), key, value)
    finally:
        await conn.close()


def selected(page, key: str) -> None:
    page.wait_for_function("key => document.querySelectorAll('.nb[aria-current=page]').length === 1 && document.querySelector('.nb[aria-current=page]').dataset.page === key", arg=key)
    page.wait_for_function("""() => {const b=document.querySelector('.nb[aria-current=page]'),r=b.getBoundingClientRect(),n=(b.closest('.nav-rail')||b.closest('.nav')).getBoundingClientRect();return r.left>=n.left-1&&r.right<=n.right+1;}""")


def edge_cases(stand, browser) -> None:
    for width in (320,430,768,1280):
        ctx=browser.new_context(viewport={'width':width,'height':640})
        ctx.route('**/*',lambda r:r.abort() if any(h in r.request.url for h in ('telegram.org','fonts.g')) else r.continue_())
        page=ctx.new_page();page.add_init_script(INIT+stand.browser_init)
        page.goto(stand.url,wait_until='domcontentloaded');page.wait_for_function(READY)
        page.locator('#nb-more').click()
        page.locator('#more-search').fill('админ')
        assert page.locator('#v3-admin-entry').is_hidden()
        page.evaluate("el('v3-admin-entry').hidden=false")
        page.wait_for_selector('#v3-admin-entry:not(.nav-filtered)')
        assert page.locator('#more-search-empty').is_hidden()
        page.evaluate("el('v3-admin-entry').hidden=true")
        page.wait_for_selector('#more-search-empty:not([hidden])')
        page.locator('#more-search').fill('досье')
        page.evaluate("""() => {const b=document.createElement('button');b.id='test-late-purge';b.dataset.navKey='purge';b.className='v3-row';b.textContent='Чистка чатов — досье';document.querySelector('[data-nav-group=community]').append(b);orderNavigation();}""")
        page.wait_for_selector('#test-late-purge:visible')
        page.evaluate("el('test-late-purge').remove()")
        page.wait_for_selector('#more-search-empty:not([hidden])')
        page.locator('#more-search').fill('')
        page.evaluate("document.body.style.setProperty('--tg-safe-area-inset-bottom','24px');document.querySelector('.nav-rail').scrollLeft=10000")
        page.wait_for_timeout(250)
        assert page.locator('#nb-more').bounding_box()['y']+page.locator('#nb-more').bounding_box()['height']<=608
        assert page.evaluate("""() => {const t=document.querySelector('.nav-scrollbar').getBoundingClientRect(),b=document.querySelector('.nav-scrollbar span').getBoundingClientRect();return b.right<=t.right+1&&b.left>=t.left-1;}""")
        assert page.evaluate("[...document.querySelectorAll('.nb:not([hidden])')].every(b=>b.getBoundingClientRect().width>=44&&b.getBoundingClientRect().height>=44&&parseFloat(getComputedStyle(b).fontSize)>=11)")
        if width == 768:
            assert page.evaluate("document.querySelector('.nav-rail').scrollWidth<=document.querySelector('.nav-rail').clientWidth+1"), 'A fitting tablet dock needs no scroll'
        ctx.set_offline(True)
        page.evaluate("switchPage('profile');switchPage('more')")
        selected(page,'more')
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        ctx.close()
    print('OK: late role/purge entries, safe area, scroll indicator, offline menu, 320/430/768/1280')


def run(dsn: str, shots: Path | None) -> None:
    asyncio.run(set_game_flags(dsn, True))
    count = 0
    with Stand(18415, dsn, rich=True, name="Искатель") as stand, sync_playwright() as pw, ThreadPoolExecutor(max_workers=1) as worker:
        browser = pw.chromium.launch(executable_path=chromium_path(), headless=True)
        for width, (exchange, pets, chests) in itertools.product((320,390,430), itertools.product((False,True), repeat=3)):
            worker.submit(asyncio.run, flags(dsn, exchange, pets, chests)).result()
            ctx = browser.new_context(viewport={"width":width,"height":640}, device_scale_factor=2 if shots else 1, is_mobile=True, has_touch=True)
            ctx.route("**/*", lambda r: r.abort() if any(h in r.request.url for h in ("telegram.org", "fonts.g")) else r.continue_())
            page=ctx.new_page(); errors=[]
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(INIT + stand.browser_init + ";localStorage.setItem('pv_looks_tour','1');" + TELEGRAM)
            page.goto(stand.url, wait_until="domcontentloaded")
            page.wait_for_function(READY, timeout=30000)
            # Authenticate with the isolated stand, then simulate Telegram chrome only.
            page.evaluate("tg.initData='simulation';_syncBackButton();showCurrModal()")
            selected(page,'wallet')
            assert page.evaluate('window.__backVisible'), 'Telegram Back appears on an initial-profile wallet'
            page.evaluate('window.__backHandler()')
            selected(page,'profile')
            page.wait_for_function("value => document.getElementById('cc-exchange-v1').hidden === !value", arg=exchange)
            more=page.locator('#nb-more'); box=more.bounding_box()
            assert box and box['x']>=0 and box['x']+box['width']<=width, (width,box)
            assert not page.evaluate("document.documentElement.scrollWidth>innerWidth")
            page.evaluate("document.querySelector('.nav-rail').scrollLeft=10000")
            more.click(); selected(page,'more')
            page.locator('#more-search').fill('настройки')
            assert page.locator('[data-nav-key="settings"]:visible').count()==1
            assert page.locator('#pg-more [data-nav-key]:visible').count()==1
            page.locator('#more-search').fill('<img onerror=alert(1)>')
            assert page.locator('#more-search-empty').is_visible()
            assert page.locator('#pg-more img').count()==0
            page.locator('#more-search').fill('')
            assert not page.locator('#more-search-empty').is_visible()
            for key in ('top','inventory','chests','looks','wallet'):
                assert page.locator(f'#pg-more [data-nav-key="{key}"]').count()==0
            # Hidden role entries stay hidden even when the search matches them.
            page.locator('#more-search').fill('админ')
            assert page.locator('#v3-admin-entry').is_hidden()
            page.locator('#more-search').fill('')
            for key, opener in (('arena',"switchPage('arena')"),('pets','openPetsV1()'),('questlog','openQuestsV1()'),('looks','openLooksModal()'),('inventory','openInventory()'),('chests','openChestsV1()'),('top','openTopV3()')):
                page.evaluate(opener); selected(page,key)
            page.wait_for_load_state('networkidle')
            if page.locator('#lk-reveal').count():
                page.keyboard.press('Escape')
            page.evaluate("switchPage('arena')")
            page.evaluate("showCurrModal()")
            selected(page,'wallet')
            page.evaluate('navBack()')
            assert not page.locator('#modal').evaluate('n=>n.open')
            selected(page,'arena')
            assert page.evaluate('_activePage')=='arena', 'Back closes the sheet before consuming page history'
            # Native Escape also restores the page highlight and the source focus.
            wallet_button=page.locator('.nb[data-page="wallet"]');wallet_button.click();selected(page,'wallet')
            page.keyboard.press('Escape'); selected(page,'arena')
            page.wait_for_function("document.activeElement === document.querySelector('.nb[data-page=wallet]')")
            # A replacement sheet must not retain the wallet highlight.
            page.evaluate("showCurrModal();OM('Проверка','Другое окно')")
            selected(page,'arena');page.evaluate('CM()')
            page.evaluate("showCurrModal();CM();OM('Новое окно','Проверка запоздалого закрытия')")
            selected(page,'arena')
            assert page.locator('#modal').evaluate('n=>n.open')
            page.evaluate('CM()')
            page.evaluate("switchPage('exchange-v1');showCurrModal();el('cc-exchange-v1').hidden=true;_dockActive('exchange-v1')")
            selected(page,'wallet')
            page.evaluate('CM()');selected(page,'more')
            page.evaluate("el('cc-exchange-v1').hidden=false;_dockActive('exchange-v1')")
            selected(page,'exchange-v1')
            for target, active in (('inventory','inventory'),('quests','questlog'),('looks','looks'),('exchange','exchange-v1' if exchange else 'more'),('guide_map','more')):
                page.goto(stand.base+f'/?startapp={target}',wait_until='domcontentloaded')
                page.wait_for_function(READY,timeout=30000)
                selected(page,active)
            if shots and not exchange and pets and chests:
                shots.mkdir(parents=True,exist_ok=True)
                page.evaluate("CM();switchPage('profile')")
                page.add_style_tag(content=FREEZE)
                page.screenshot(path=str(shots/f'final-profile-{width}.png'))
                more.click();page.screenshot(path=str(shots/f'final-more-{width}.png'))
            assert not errors, (width,exchange,pets,chests,errors)
            count+=1;ctx.close()
            print(f'pass {width}: exchange={exchange}, pets={pets}, chests={chests}',flush=True)
        edge_cases(stand,browser)
        browser.close()
    asyncio.run(set_game_flags(dsn, True))
    print(f'OK: {count} real navigation combinations; pinned More, search, rights visibility, wallet/Back/focus, deep links')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dsn',required=True)
    parser.add_argument('--shots',type=Path)
    args=parser.parse_args()
    run(args.dsn,args.shots)
