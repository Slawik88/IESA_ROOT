"""Real browser script ordering with a slow Telegram CDN and no launch hash/cookie."""
import asyncio
import argparse
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlencode, urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from FastAPI.game_shell import render
from FastAPI.auth import verify_webapp_data

STATIC = ROOT / 'FastAPI/static'
BRIDGE = "window.Telegram={WebApp:{initData:'signed-test',initDataUnsafe:{user:{id:101}},version:'8.0',ready(){},expand(){},onEvent(){}}};"


async def main(sdk_path=None, baseline_ref=None):
    real_sdk = Path(sdk_path).read_bytes() if sdk_path else None
    os.environ.setdefault('BOT_TOKEN','123456:offline-sdk-test')
    fields={'auth_date':str(int(time.time())),'user':json.dumps({'id':101,'first_name':'QA'})}
    secret=hmac.new(b'WebAppData',os.environ['BOT_TOKEN'].encode(),hashlib.sha256).digest()
    fields['hash']=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest()
    init_data=urlencode(fields) if real_sdk else 'signed-test'
    def source(asset):
        if baseline_ref:
            return subprocess.check_output(['git','show',f'{baseline_ref}:predvestnik_v2/FastAPI/static/{asset.relative_to(STATIC).as_posix()}'],cwd=ROOT.parent)
        return asset.read_bytes()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        for page_name, file, game in (('minesweeper', 'minesweeper-v2.html', 'minesweeper'),
                                      ('rhythm-v2', 'rhythm-v2.html', 'rhythm'),
                                      ('league', 'league-demo.html', 'minesweeper')):
            context = await browser.new_context(service_workers='block')
            page = await context.new_page()
            calls = []

            async def route_request(route):
                request = route.request
                path = urlparse(request.url).path
                if request.url.startswith('https://telegram.org/js/'):
                    await asyncio.sleep(.8)
                    await route.fulfill(body=real_sdk or BRIDGE, content_type='application/javascript')
                elif path == '/launch':
                    await route.fulfill(body='<script src="https://telegram.org/js/telegram-web-app.js"></script>',content_type='text/html')
                elif path == '/' + page_name:
                    html = render(source(STATIC / file).decode('utf-8'), base='', version='qa', eyebrow='Игра', title='Игра', game=game, mode='ranked' if page_name == 'league' else 'casual')
                    await route.fulfill(body=html, content_type='text/html')
                elif '/api/' in path or path.startswith(('/skins-v3/', '/minesweeper-v2/', '/rhythm-v2/')):
                    calls.append((path, request.headers.get('x-init-data')))
                    valid=verify_webapp_data(request.headers.get('x-init-data','')) if real_sdk else None
                    await route.fulfill(status=200 if valid else 401, body=json.dumps({} if valid else {'detail': 'Требуется авторизация через Telegram.'}), content_type='application/json')
                elif path.startswith('/static/'):
                    asset = STATIC / path.removeprefix('/static/')
                    if not asset.is_file():
                        asset = STATIC / Path(path).name  # game asset routes share flat sources
                    if asset.is_file():
                        data = source(asset)
                        if asset.name == 'local-games-v1.js':
                            data += b"\n{const Real=PVLocal.Store;PVLocal.Store=class extends Real{constructor(...args){super(...args);window.qaStoreKey=this.key;}};}"
                        await route.fulfill(body=data, content_type='application/javascript' if asset.suffix == '.js' else mimetypes.guess_type(asset.name)[0] or 'application/octet-stream')
                    else:
                        await route.fulfill(status=404)
                else:
                    await route.abort()

            await context.route('**/*', route_request)
            if real_sdk:
                # A real Telegram launch stores initData in the official SDK.
                # A same-tab game navigation then has no hash and no login cookie.
                await page.goto('http://game.test/launch#'+urlencode({'tgWebAppData':init_data,'tgWebAppVersion':'8.0','tgWebAppPlatform':'tdesktop'}),wait_until='load')
                assert await page.evaluate('Telegram.WebApp.initData') == init_data
            await page.goto('http://game.test/' + page_name, wait_until='load')
            await page.wait_for_timeout(150)
            assert not await context.cookies()
            if baseline_ref:
                assert calls and any(not auth for _,auth in calls),(page_name,calls)
                if page_name != 'league':
                    key=await page.evaluate('window.qaStoreKey')
                    assert key and key.startswith(f'pv-local-v1:{game}:') and key != f'pv-local-v1:{game}:101',key
                await context.close()
                continue
            assert calls and all(auth == init_data for _, auth in calls), (page_name, calls)
            if page_name != 'league':
                assert await page.evaluate('window.qaStoreKey') == f'pv-local-v1:{game}:101'
                if real_sdk:
                    await context.close()
                    continue
                calls.clear()
                await page.evaluate("Telegram.WebApp.initData='renewed-test';window.dispatchEvent(new Event('online'))")
                await page.wait_for_timeout(100)
                assert calls and all(auth == 'renewed-test' for _, auth in calls), (page_name, calls)
                calls.clear()
                await page.evaluate("Telegram.WebApp.initData='';window.dispatchEvent(new Event('online'))")
                await page.wait_for_timeout(100)
                assert calls and all(auth is None for _, auth in calls), 'removed credentials must not fall back to a captured owner'

            await context.close()
        await browser.close()
    print('PASS real SDK launch -> same-tab hashless game: '+('baseline loses auth/owner' if baseline_ref else 'authenticated first reads and correct local owner') if real_sdk else 'PASS delayed bridge: authenticated first reads, correct local owner, refreshed retry credentials on both casual games and League')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--telegram-sdk',help='Official downloaded telegram-web-app.js; never executes from a production session')
    parser.add_argument('--baseline-ref',help='Read-only git revision for the failing half of an A/B proof')
    args=parser.parse_args()
    if args.baseline_ref and not args.telegram_sdk:
        parser.error('--baseline-ref requires --telegram-sdk')
    asyncio.run(main(args.telegram_sdk,args.baseline_ref))
