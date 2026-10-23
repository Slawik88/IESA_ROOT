"""Real local dust shop proof: narrow screens, arbitrary days, lost committed response."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import asyncpg
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ui_stand import PERSONA_ID, Stand
from ui_smoke import INIT,PROFILE_READY,chromium_path
from test_pets_v2_pg import local_dsn
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import star_dust, system_flags


async def seed(dsn):
    conn=await asyncpg.connect(dsn,server_settings={'search_path':'predvestnik,public'})
    try:
        db=PGAdapter(conn);await star_dust.ensure_tables(db)
        await system_flags.set_flag(db,'star_dust_v1',True)
        await system_flags.set_flag(db,'pets_v2',True)
        await conn.execute('INSERT INTO star_dust_accounts(user_id,balance) VALUES($1,2000) ON CONFLICT(user_id) DO UPDATE SET balance=2000',PERSONA_ID)
        await conn.execute("UPDATE vip_subscriptions SET expires_at=NOW()-INTERVAL '1 day' WHERE user_id=$1",PERSONA_ID)
    finally:await conn.close()


async def state(dsn):
    conn=await asyncpg.connect(dsn,server_settings={'search_path':'predvestnik,public'})
    try:return tuple(await conn.fetchrow('SELECT balance,(SELECT COUNT(*) FROM star_dust_vip_receipts WHERE user_id=$1) FROM star_dust_accounts WHERE user_id=$1',PERSONA_ID))
    finally:await conn.close()


def task(fn,*args):
    with ThreadPoolExecutor(max_workers=1) as pool:return pool.submit(asyncio.run,fn(*args)).result()


def run(dsn,shots):
    shots.mkdir(parents=True,exist_ok=True)
    with Stand(8403,dsn,skin='void',tier='SSS',rich=True) as stand,sync_playwright() as pw:
        task(seed,dsn)
        browser=pw.chromium.launch(executable_path=chromium_path())
        ctx=browser.new_context(viewport={'width':390,'height':780},is_mobile=True,has_touch=True)
        page=ctx.new_page();page.add_init_script(INIT);errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(stand.url,wait_until='domcontentloaded');page.wait_for_function(PROFILE_READY,timeout=30000)
        page.locator('#preloader').wait_for(state='hidden',timeout=15000)
        page.evaluate('openStarDust()');page.wait_for_function('() => _sd.me && document.getElementById("sd-content")')
        for width in (320,390,430):
            for height in (640,780):
                page.set_viewport_size({'width':width,'height':height})
                page.evaluate('_sdRender()')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                assert 'до 20' in page.locator('label[for="sd-days"]').inner_text()
                page.screenshot(path=str(shots/f'dust-{width}-{height}.png'),full_page=False)
        # Invalid input is actionable and keeps keyboard focus; Enter submits the form.
        for value in ('0','1.5','21'):
            page.locator('#sd-days').fill(value);page.locator('#sd-days').press('Enter')
            assert page.locator('#sd-days').get_attribute('aria-invalid')=='true'
            assert page.locator('#sd-days-error').inner_text()
            assert page.locator('#sd-days').evaluate('(e)=>e===document.activeElement')
        page.locator('#sd-days').fill('5')
        page.locator('details[data-detail="dust-rules"] summary').click()
        page.locator('[data-f="dust-refresh"]').click();page.wait_for_function('() => !_sd.refreshing')
        assert page.locator('#sd-days').input_value()=='5'
        assert page.locator('details[data-detail="dust-rules"]').get_attribute('open') is not None
        page.route('**/star-dust/me',lambda r:r.fulfill(status=503,content_type='application/json',body='{"detail":"Нет связи"}'))
        page.locator('[data-f="dust-refresh"]').click();page.wait_for_function('() => !_sd.refreshing')
        assert page.locator('#sd-days').input_value()=='5' and page.evaluate('_sd.me.balance')==2000
        assert 'Последние данные сохранены' in page.locator('#sd-content').inner_text()
        page.unroute('**/star-dust/me')
        page.locator('[data-f="dust-refresh"]').click();page.wait_for_function('() => !_sd.refreshing')
        assert 'Не удалось обновить' not in page.locator('#sd-content').inner_text()
        page.locator('#sd-days').fill('15');page.locator('#sd-days').press('Enter')
        assert page.locator('[data-f="dust-confirm"]').evaluate('(e)=>e===document.activeElement')
        page.locator('[data-f="dust-back"]').click()
        assert page.locator('#sd-days').input_value()=='15'
        page.locator('#sd-days').press('Enter')
        assert '1500' in page.locator('#sd-content').inner_text().replace(' ','').replace('\xa0','')
        before=task(state,dsn);bodies=[]
        def lose(route):
            bodies.append(route.request.post_data_json)
            response=route.fetch();assert response.ok
            route.abort()
        page.route('**/star-dust/vip',lose)
        page.locator('[data-f="dust-confirm"]').click()
        page.wait_for_function('() => !_sd.busy && _sd.pending')
        after=task(state,dsn);assert after==(before[0]-1500,before[1]+1)
        page.unroute('**/star-dust/vip')
        page.reload(wait_until='domcontentloaded');page.wait_for_function(PROFILE_READY,timeout=30000)
        page.locator('#preloader').wait_for(state='hidden',timeout=15000)
        page.evaluate('openStarDust()');page.wait_for_function('() => _sd.pending && document.getElementById("sd-content")')
        saved=page.evaluate('({..._sd.pending})');assert saved==bodies[0]
        page.route('**/star-dust/vip',lambda r:r.fulfill(status=429,content_type='application/json',body='{"detail":"Повторите позже"}'))
        page.locator('[data-f="dust-retry"]').click();page.wait_for_function('() => !_sd.busy')
        assert page.evaluate('_sd.pending.action_id')==saved['action_id']
        page.unroute('**/star-dust/vip')
        page.locator('[data-f="dust-retry"]').click();page.wait_for_function('() => !_sd.busy && !_sd.pending')
        assert task(state,dsn)==after
        assert 'VIP активен до' in page.locator('.sd-vip-status').inner_text()
        page.screenshot(path=str(shots/'dust-exchanged.png'),full_page=False)
        # A same-owner reopen GET snapshots the pre-write balance; never apply it after the receipt.
        race_before=task(state,dsn);posts=[];reads=[]
        page.locator('[data-f="dust-1"]').click()
        page.route('**/star-dust/vip',lambda r:posts.append(r))
        page.locator('[data-f="dust-confirm"]').click();page.wait_for_function('() => _sd.busy')
        def hold_first_read(route):
            if not reads:reads.append((route,route.fetch()))
            else:route.continue_()
        page.route('**/star-dust/me',hold_first_read)
        page.evaluate('void openStarDust()')
        for _ in range(40):
            if reads:break
            page.wait_for_timeout(50)
        assert reads,'reopen read must be held before the write'
        response=posts[0].fetch();assert response.ok
        posts[0].fulfill(response=response)
        page.wait_for_function('() => !_sd.busy')
        reads[0][0].fulfill(response=reads[0][1])
        page.wait_for_function('() => _sd.readySeq===_sd.seq && _sd.me.balance===400')
        assert task(state,dsn)==(race_before[0]-100,race_before[1]+1)
        assert page.locator('.sd-balance').inner_text().find('400')>=0
        page.unroute('**/star-dust/me');page.unroute('**/star-dust/vip')
        # Empty wallets still explain fractional progress instead of hiding earned dust.
        page.evaluate('Object.assign(_sd.me,{balance:99,pet_fraction:.8});_sd.me.vip.max_days=0;_sdRender()')
        assert '0,2 пыли' in page.locator('#sd-content').inner_text()
        assert page.locator('.sd-progress').get_attribute('value')=='99.8'
        page.screenshot(path=str(shots/'dust-progress.png'))
        page.evaluate('trailClose(true); openTrail()')
        page.wait_for_function("() => _tr.me && document.querySelector('#pg-pets button[onclick^=openStarDust]')")
        assert not errors,errors
        browser.close()
    print('PASS: dust UI 6 visible layouts, validation/Enter/focus/draft, refresh failure, VIP/fraction, arbitrary days, lost commit/reload/429/replay, stale reopen read race, pet entry')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dsn',required=True,type=local_dsn);p.add_argument('--shots',type=Path,default=ROOT/'.local/dust-ui')
    a=p.parse_args();run(a.dsn,a.shots)
