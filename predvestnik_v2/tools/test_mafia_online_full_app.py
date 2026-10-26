"""Online Mafia through the complete production shell, authentication and real PostgreSQL.

The small isolated UI fixture cannot detect shared headers or dialog styles.
Only the loopback Stand persona and explicitly synthetic peers are used here.
"""
from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

import asyncpg
from playwright.sync_api import sync_playwright
from ui_stand import Stand, PERSONA_ID
from ui_smoke import INIT, PROFILE_READY, chromium_path


def database(dsn, operation, room_id=None):
    async def run():
        from infrastructure.pg_adapter import PGAdapter
        from infrastructure.repositories import mafia_online as repo
        from services import mafia_online as game, mafia_online_phases as phases
        connection = await asyncpg.connect(dsn, server_settings={'search_path': 'predvestnik,public'})
        db = PGAdapter(connection)
        try:
            if operation == 'reset':
                active = await repo.current(db, PERSONA_ID)
                if active:
                    state = await repo.load(db, active)
                    await game.control(db, active, PERSONA_ID, 'cancel' if state['host'] == PERSONA_ID else 'leave')
            elif operation == 'create':
                return await game.create(db, {'id': PERSONA_ID, 'first_name': 'Тестовый хозяин'})
            elif operation == 'peers':
                for offset in range(11, 14):
                    await game.join(db, room_id, {'id': PERSONA_ID + offset, 'first_name': f'Игрок {offset}'})
            elif operation == 'expire':
                async with connection.transaction():
                    state = await repo.load(db, room_id, lock=True)
                    state['deadline'] = await repo.now(db) - 1
                    await repo.save(db, state)
                    await phases.advance(db, state, await repo.now(db))
            else:
                raise AssertionError(operation)
        finally:
            await connection.close()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, run()).result()


def check(dsn, shots, baseline=False, port=8408):
    shots.mkdir(parents=True, exist_ok=True)
    with Stand(port, dsn, skin='void', tier='SSS', rich=True) as stand, sync_playwright() as pw:
        database(dsn, 'reset')
        browser = pw.chromium.launch(executable_path=chromium_path())
        context = browser.new_context(viewport={'width': 390, 'height': 640}, is_mobile=True, has_touch=True)
        context.add_init_script(INIT + stand.browser_init)
        if baseline:
            context.route('**/static/app.js*', lambda route: route.fulfill(
                body=(ROOT / '.local/mafia-baseline-bundle.js').read_text(encoding='utf-8'), content_type='application/javascript'))
            context.route('**/static/mafia-online-v3.css*', lambda route: route.fulfill(
                body=(ROOT / '.local/mafia-baseline.css').read_text(encoding='utf-8'), content_type='text/css'))
        page = context.new_page()
        errors, posts = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('response', lambda response: posts.append({
            'path': urlparse(response.url).path, 'status': response.status,
            'content_type': response.request.headers.get('content-type', '')
        }) if '/mafia-online/' in response.url and response.request.method == 'POST' else None)
        page.goto(stand.url, wait_until='domcontentloaded')
        try:
            page.wait_for_function(PROFILE_READY, timeout=30000)
        except Exception:
            (shots/'startup-failure.json').write_text(json.dumps({'errors':errors,'body':page.locator('body').inner_text()[:1800]},ensure_ascii=False),encoding='utf-8')
            raise
        page.locator('#preloader').wait_for(state='hidden')
        page.evaluate('openMafiaOnline()')
        page.locator('#mo-quick').wait_for()
        page.screenshot(path=str(shots / '01-hub-390.png'))
        if baseline:
            room = database(dsn, 'create')
            page.evaluate('(id) => moEnter(id)', room)
        else:
            page.locator('#mo-quick').click()
        page.wait_for_function('() => MO.data && document.querySelector("#mo-text")', timeout=15000)
        room = page.evaluate('MO.room')
        page.locator('#mo-text').fill('Привет')
        with page.expect_response(lambda r: '/messages' in r.url and r.request.method == 'POST') as sent:
            page.locator('#mo-send').click()
        response = sent.value
        if baseline:
            assert response.status == 422, (response.status, response.text())
            assert response.request.headers['content-type'] == 'application/json, application/json'
            page.wait_for_function('() => !MO.busy')
            page.screenshot(path=str(shots / '02-original-send-failure-390.png'))
            page.set_viewport_size({'width': 320, 'height': 640})
            page.screenshot(path=str(shots / '03-original-send-failure-320.png'))
        else:
            assert response.status == 200, (response.status, response.text())
            assert response.request.headers['content-type'] == 'application/json'
            page.get_by_text('Привет', exact=True).wait_for()
            page.wait_for_function('() => !MO.busy')
            assert page.locator('#mo-text').input_value() == ''
            assert not page.locator('#mo-error').inner_text().strip()
            for width in (320, 390, 430, 900, 1280):
                for height in (640, 430):
                    page.set_viewport_size({'width': width, 'height': height})
                    # The dialog height follows the visualViewport event asynchronously;
                    # measuring before it settles reads the previous size.
                    page.wait_for_function('(h) => Math.abs(document.getElementById("modal").getBoundingClientRect().height - h) < 2', arg=height)
                    geometry = page.evaluate('''() => {
                        const ids=['mo-root','mo-chat','mo-compose','mo-send'];
                        return Object.fromEntries(ids.map(id=>{const e=document.getElementById(id),r=e.getBoundingClientRect();
                          return [id,{x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}];}));
                    }''')
                    for key in ('mo-compose', 'mo-send'):
                        box = geometry[key]
                        assert box['x'] >= 0 and box['right'] <= width + 1, geometry
                        assert box['y'] >= 0 and box['bottom'] <= height + 1, geometry
                    assert geometry['mo-chat']['height'] >= 60, geometry
                    page.screenshot(path=str(shots / f'02-lobby-{width}-{height}.png'))
            page.set_viewport_size({'width': 390, 'height': 640})
            # In the real dialog, host controls and their confirmation must be
            # reachable without squeezing them into the phase/header scrollbar.
            page.locator('#mo-tab-table').click()
            page.get_by_role('button', name='Покинуть город', exact=True).click()
            page.locator('#mo-sheet').get_by_role('button', name='Остаться', exact=True).wait_for(state='visible')
            page.screenshot(path=str(shots / '03-management-confirm-390.png'))
            page.locator('#mo-sheet').get_by_role('button', name='Остаться', exact=True).click()
            page.locator('#mo-tab-chat').click()
            database(dsn, 'peers', room)
            page.evaluate('moRefresh()')
            page.get_by_role('button', name='Начать партию', exact=True).click()
            page.wait_for_function('() => MO.data?.phase === "night" && !MO.busy')
            page.screenshot(path=str(shots / '03-night-390.png'))
            database(dsn, 'expire', room)
            page.evaluate('moRefresh()')
            page.wait_for_function('() => MO.data?.phase === "discussion"')
            page.screenshot(path=str(shots / '04-discussion-390.png'))
            # Losing and restoring the complete app must preserve membership.
            page.reload(wait_until='domcontentloaded')
            page.wait_for_function(PROFILE_READY, timeout=30000)
            page.locator('#preloader').wait_for(state='hidden')
            page.evaluate('openMafiaOnline()')
            page.wait_for_function('(id) => MO.room === id && MO.data?.phase === "discussion"', arg=room)
            page.screenshot(path=str(shots / '05-reentered-390.png'))
            assert posts and all(p['status'] < 400 and p['content_type'] == 'application/json' for p in posts), posts
            # A Telegram invitation opens while /profile/me is still loading.
            # The authoritative first room reply may bind identity0 -> user;
            # a guard must not discard it and freeze all subsequent polling.
            cold = browser.new_context(viewport={'width': 320, 'height': 640}, is_mobile=True, has_touch=True)
            cold.add_init_script(INIT + stand.browser_init + ''';(() => {
              const original=window.fetch.bind(window);let delayed=false;
              window.fetch=async function(input,options){
                if(!delayed&&String(input).includes('/profile/me')){
                  delayed=true;await new Promise(resolve=>setTimeout(resolve,2500));
                }
                return original(input,options);
              };
            })();''')
            invited = cold.new_page()
            invited.on('pageerror', lambda error: errors.append(str(error)))
            invited.goto(f'{stand.base}/?__preprod_ticket={stand.ticket}&startapp=mfo_{room}', wait_until='domcontentloaded')
            invited.wait_for_function('(id) => typeof MO!=="undefined" && MO.data?.id===id', arg=room, timeout=15000)
            invited.wait_for_function(PROFILE_READY, timeout=30000)
            invited.locator('#preloader').wait_for(state='hidden')
            invited.evaluate('moRefresh()')
            invited.wait_for_function('(id) => MO.data?.id===id && MO.owner===MO.data.me.id && MO.data.me.id===_uid', arg=room)
            invited.screenshot(path=str(shots / '06-cold-invitation-320.png'))
            assert invited.evaluate('Boolean(MO.data.launch_url)'), 'sharing must work on a cold invitation entry'
            cold.close()
        assert not errors, errors
        (shots / 'transport.json').write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding='utf-8')
        context.close()
        browser.close()
        database(dsn, 'reset')
    print('PASS reproduced baseline duplicate Content-Type / message422' if baseline else
          'PASS complete production shell: auth, JSON transport, real message, mobile/keyboard geometry, start/night/discussion/reload')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dsn', required=True)
    parser.add_argument('--shots', type=Path, default=ROOT / '.local/mafia-full-app')
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--port', type=int, default=8408)
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise SystemExit('loopback database required')
    check(args.dsn, args.shots, args.baseline, args.port)
