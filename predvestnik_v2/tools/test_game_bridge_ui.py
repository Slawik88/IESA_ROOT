"""Real browser script ordering with a slow Telegram CDN and no launch hash/cookie."""
import asyncio
import json
import mimetypes
from pathlib import Path
import sys
from urllib.parse import urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from FastAPI.game_shell import render

STATIC = ROOT / 'FastAPI/static'
BRIDGE = "window.Telegram={WebApp:{initData:'signed-test',initDataUnsafe:{user:{id:101}},version:'8.0',ready(){},expand(){},onEvent(){}}};"


async def main():
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
                    await route.fulfill(body=BRIDGE, content_type='application/javascript')
                elif path == '/' + page_name:
                    html = render((STATIC / file).read_text(encoding='utf-8'), base='', version='qa', eyebrow='Игра', title='Игра', game=game, mode='ranked' if page_name == 'league' else 'casual')
                    await route.fulfill(body=html, content_type='text/html')
                elif '/api/' in path or path.startswith(('/skins-v3/', '/minesweeper-v2/', '/rhythm-v2/')):
                    calls.append((path, request.headers.get('x-init-data')))
                    await route.fulfill(status=401, body=json.dumps({'detail': 'Тестовый ответ'}), content_type='application/json')
                elif path.startswith('/static/'):
                    asset = STATIC / Path(path).name
                    if asset.is_file():
                        source = asset.read_bytes()
                        if asset.name == 'local-games-v1.js':
                            source += b"\n{const Real=PVLocal.Store;PVLocal.Store=class extends Real{constructor(...args){super(...args);window.qaStoreKey=this.key;}};}"
                        await route.fulfill(body=source, content_type='application/javascript' if asset.suffix == '.js' else mimetypes.guess_type(asset.name)[0] or 'application/octet-stream')
                    else:
                        await route.fulfill(status=404)
                else:
                    await route.abort()

            await context.route('**/*', route_request)
            await page.goto('http://game.test/' + page_name, wait_until='load')
            await page.wait_for_timeout(150)
            assert calls and all(auth == 'signed-test' for _, auth in calls), (page_name, calls)
            if page_name != 'league':
                assert await page.evaluate('window.qaStoreKey') == f'pv-local-v1:{game}:101'
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
    print('PASS delayed bridge: authenticated first reads, correct local owner, refreshed retry credentials on both casual games and League')


if __name__ == '__main__':
    asyncio.run(main())
