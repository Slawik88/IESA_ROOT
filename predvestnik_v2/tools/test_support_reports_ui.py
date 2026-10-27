"""Real browser: silent problems, offline delivery, account isolation and safe history."""
import argparse
import asyncio
import json
import mimetypes
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse
from uuid import uuid4

from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'FastAPI/static'
sys.path.insert(0,str(ROOT))
from FastAPI.game_shell import render

SDK="""window.Telegram={WebApp:{initData:'signed-user-101',initDataUnsafe:{user:{id:101,photo_url:'https://t.me/i/userpic/320/PRIVATE_PHOTO.jpg'}},platform:'android',version:'8.0',colorScheme:'dark',ready(){},expand(){}}};window.changeOwner=id=>{Telegram.WebApp.initDataUnsafe.user.id=id;Telegram.WebApp.initData='signed-user-'+id;PVDiagnostics.record('lifecycle',{state:'active'});};"""


async def main(shots):
    shots.mkdir(parents=True,exist_ok=True)
    receipts, posts = {}, []
    mode = 'ok'
    held_started, held_release = asyncio.Event(), asyncio.Event()
    admin_status='new'
    profile_owner='101'
    admin_id=str(uuid4())
    def admin_report():
        return {'id':admin_id,'code':'PV-QATEST123456','user_id':101,'category':'avatar','comment':'<img src=x onerror="window.qaXss=true">','status':admin_status,'created_at':'2026-10-27T12:00:00Z',
                'payload':{'captured_at':int(time.time()*1000),'environment':{'model':'QA Phone','telegram_platform':'android','locale_region':'RU'},'events':[],'include_diagnostics':True},
                'server_context':{'vip':True,'telegram_photo_available':True,'diagnostics':{'events':[]}}}
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        async def routing(route):
            nonlocal mode,admin_status
            path=urlparse(route.request.url).path
            if path=='/app':
                html='<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><script src="https://telegram.org/js/telegram-web-app.js"></script><link rel="stylesheet" href="/static/league-demo.css"></head><body style="background:#09070e;color:#eee;font-family:system-ui">{{GAME_HEAD}}<main><h2>Предвестник</h2><button data-support-open>Сообщить о проблеме</button><button data-page="games">Игры</button></main></body></html>'
                html=render(html,base='',version='qa-support',eyebrow='Игры',title='Сапёр')
                await route.fulfill(body=html,content_type='text/html')
            elif route.request.url.startswith('https://telegram.org/js/'):
                await route.fulfill(body=SDK,content_type='application/javascript')
            elif path=='/bot-admin':
                await route.fulfill(body=(STATIC/'bot-admin/index.html').read_text(encoding='utf-8').replace('{{BASE}}','').replace('{{VER}}','qa'),content_type='text/html; charset=utf-8')
            elif path=='/bot-admin/api/me':
                await route.fulfill(json={'user_id':101,'rank':6,'rank_name':'QA Создатель','creator':True,'sections':[{'key':'diagnostics','title':'Проблемы приложения'}]})
            elif path=='/bot-admin/api/badges':
                await route.fulfill(json={'diagnostics':1})
            elif path=='/bot-admin/api/diagnostics':
                await route.fulfill(json={'items':[admin_report()],'total':1,'page':0,'counts':{admin_status:1},'monitor':{'totals':{'requests':100,'avatar_miss':1}}})
            elif path==f'/bot-admin/api/diagnostics/{admin_id}/status':
                admin_status=route.request.post_data_json['status'];await route.fulfill(json={'ok':True})
            elif path in {f'/bot-admin/api/diagnostics/{admin_id}',f'/bot-admin/api/diagnostics/{admin_id}/download'}:
                await route.fulfill(json=admin_report())
            elif path.startswith('/bot-admin/') and '/api/' not in path:
                asset=STATIC/'bot-admin'/Path(path).name
                await route.fulfill(body=asset.read_bytes(),content_type=mimetypes.guess_type(asset.name)[0] or 'application/octet-stream')
            elif path.startswith('/static/'):
                asset=STATIC/path.removeprefix('/static/')
                if asset.is_file(): await route.fulfill(body=asset.read_bytes(),content_type=mimetypes.guess_type(asset.name)[0] or 'application/octet-stream')
                else: await route.fulfill(status=404)
            elif path=='/profile/me':
                await route.fulfill(json={'user_id':int(profile_owner),'is_vip':True,'avatar':None,'private':'PRIVATE_RESPONSE'},headers={'x-support-owner':profile_owner,'x-diagnostic-route':'/profile/me','x-request-id':str(uuid4())})
            elif path=='/support/reports':
                payload=route.request.post_data_json
                owner=route.request.headers.get('x-init-data','')
                posts.append((owner,payload))
                key=(owner,payload['client_report_id'])
                replayed=key in receipts
                receipt=receipts.setdefault(key,{'id':str(uuid4()),'code':'PV-012345ABCDEF','created_at':'2026-10-27T12:00:00Z','status':'new'})
                if mode=='lost_ack':
                    mode='ok';await route.abort();return
                if mode=='hold_ack':
                    mode='ok';held_started.set();await held_release.wait()
                await route.fulfill(json={**receipt,'replayed':replayed,'client_report_id':payload['client_report_id']})
            else: await route.fulfill(status=404)

        async def page_for(width=390,height=740,blocked_storage=False):
            context=await browser.new_context(viewport={'width':width,'height':height},service_workers='block')
            await context.route('**/*',routing)
            if blocked_storage:
                await context.add_init_script("Storage.prototype.setItem=function(){throw new DOMException('quota','QuotaExceededError')}")
            else:
                old={'events':[{'at':int(time.time()*1000)-3600001,'kind':'runtime','data':{'error_kind':'OldError'}}],'started':int(time.time()*1000)-7200000,'dropped':0}
                await context.add_init_script('if(!sessionStorage.getItem("seeded")){localStorage.setItem("pv_support_history_v1:101",'+json.dumps(json.dumps(old))+');sessionStorage.setItem("seeded","1")}')
            page=await context.new_page()
            page.set_default_timeout(7000)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            await page.goto('http://support.test/app?token=SECRET_QUERY#initData=SECRET_HASH',wait_until='load')
            await page.wait_for_function('() => !!window.PVSupport')
            return context,page,errors

        context,page,errors=await page_for()
        await page.evaluate("fetch('/profile/me').then(r=>r.json())")
        await page.wait_for_function("() => true")
        assert not errors and await page.locator('#pv-support-notice').count()==0,'silent photo absence is not a runtime error'
        (shots/'initial-body.txt').write_text(await page.locator('body').inner_text(),encoding='utf-8')
        await page.screenshot(path=str(shots/'initial.png'))
        await page.get_by_role('main').get_by_role('button',name='Сообщить о проблеме',exact=True).click()
        await page.locator('.pv-support select').select_option('avatar')
        await page.locator('.pv-support textarea').fill('VIP есть, фото нет')
        for width,height in ((320,640),(390,740),(430,740),(1280,800),(390,430)):
            await page.set_viewport_size({'width':width,'height':height})
            await page.locator('[data-support-send]').scroll_into_view_if_needed()
            box=await page.locator('[data-support-send]').bounding_box()
            assert box and box['x']>=0 and box['x']+box['width']<=width+1 and box['y']>=0 and box['y']+box['height']<=height+1,box
            dialog_box=await page.locator('.pv-support').bounding_box()
            assert box['y']+box['height']<=dialog_box['y']+dialog_box['height']+1,'sticky footer must not clip inside the dialog'
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            await page.screenshot(path=str(shots/f'form-{width}-{height}.png'))
        await page.set_viewport_size({'width':390,'height':740})
        await page.locator('.pv-support details summary').click()
        await page.locator('[data-support-preview]').click()
        preview=await page.locator('[data-support-details]').inner_text()
        assert 'has_avatar' in preview and 'OldError' not in preview
        assert all(secret not in preview for secret in ('PRIVATE_PHOTO','PRIVATE_RESPONSE','SECRET_QUERY','SECRET_HASH','signed-user'))
        await page.locator('.pv-support details summary').click()
        mode='lost_ack'
        await page.locator('[data-support-send]').click()
        await page.wait_for_function("() => document.querySelector('[data-support-status]').dataset.bad==='true'")
        first=posts[-1][1]
        assert first['category']=='avatar' and first['environment']['telegram_platform']=='android'
        await page.locator('[data-support-send]').click()
        await page.get_by_text(re.compile('Отчёт доставлен')).wait_for()
        assert posts[-1][1]==first and len(receipts)==1,'lost committed ACK must reuse the frozen report id/body'
        await page.screenshot(path=str(shots/'delivered.png'))
        await page.locator('[data-support-close]').click()
        assert await page.locator('.pv-support').count()==0
        await context.close()

        # Startup/online auto-ACK must not mark a newly composed draft delivered.
        context,page,errors=await page_for()
        await page.get_by_role('main').get_by_role('button',name='Сообщить о проблеме',exact=True).click()
        await page.locator('.pv-support textarea').fill('Автоповтор старого снимка')
        await context.set_offline(True)
        await page.locator('[data-support-send]').click()
        await page.get_by_text('Нет сети. Снимок сохранён, отправим после подключения.').wait_for()
        await page.locator('[data-support-close]').click()
        held_started.clear();held_release.clear();mode='hold_ack'
        await context.set_offline(False)
        await asyncio.wait_for(held_started.wait(),3)
        await page.get_by_role('main').get_by_role('button',name='Сообщить о проблеме',exact=True).click()
        await page.locator('[data-support-delete]').click()
        await page.locator('.pv-support textarea').fill('Новая форма ещё не отправлена')
        held_release.set()
        await page.wait_for_function("() => !!localStorage.getItem('pv_support_receipt_v1:101')")
        assert await page.locator('[data-support-send]').is_visible()
        assert await page.locator('.pv-support').get_attribute('data-delivered') is None
        assert 'Новая форма' in await page.evaluate("JSON.parse(localStorage.getItem('pv_support_draft_v1:101')).comment")
        await page.locator('[data-support-send]').click()
        await page.get_by_text(re.compile('Отчёт доставлен')).wait_for()
        assert posts[-1][1]['comment']=='Новая форма ещё не отправлена'
        assert not errors,errors
        await context.close()

        # A receipt for an older in-flight snapshot must never confirm a new one.
        context,page,errors=await page_for()
        await page.evaluate("localStorage.setItem('pv_sess','202:1234567890:stale-session')")
        assert 'x-session-token' not in await page.evaluate('PVDiagnostics.credentials()'),'Telegram A must not fall back to browser B'
        profile_owner='202'
        await page.evaluate("fetch('/profile/me').then(r=>r.json())")
        mismatch=await page.evaluate('PVDiagnostics.snapshot()')
        assert not any(e['kind']=='avatar' or e['data'].get('request_id') for e in mismatch['events']),'foreign authenticated response must not enter A history'
        assert any(e['data'].get('state')=='auth_mismatch' for e in mismatch['events'])
        profile_owner='101'
        await page.get_by_role('main').get_by_role('button',name='Сообщить о проблеме',exact=True).click()
        await page.locator('.pv-support textarea').fill('Первый снимок')
        held_started.clear();held_release.clear();mode='hold_ack'
        await page.locator('[data-support-send]').click()
        await asyncio.wait_for(held_started.wait(),3)
        old_id=posts[-1][1]['client_report_id']
        await page.locator('[data-support-x]').click()
        await page.get_by_role('main').get_by_role('button',name='Сообщить о проблеме',exact=True).click()
        await page.locator('[data-support-delete]').click()
        await page.locator('.pv-support textarea').fill('Второй снимок')
        await page.locator('[data-support-send]').click()
        await page.get_by_text(re.compile('Отчёт доставлен')).wait_for()
        assert posts[-1][1]['comment']=='Второй снимок' and posts[-1][1]['client_report_id']!=old_id
        held_release.set()
        await page.wait_for_timeout(100)
        assert not errors,errors
        await context.close()

        # Offline frozen reports survive reload, but never cross an account switch.
        context,page,errors=await page_for()
        await page.get_by_role('main').get_by_role('button',name='Сообщить о проблеме',exact=True).click()
        await page.locator('.pv-support textarea').fill('Черновик не пропадает')
        await page.locator('[data-support-close]').click()
        await page.get_by_role('main').get_by_role('button',name='Сообщить о проблеме',exact=True).click()
        assert await page.locator('.pv-support textarea').input_value()=='Черновик не пропадает'
        await context.set_offline(True)
        await page.locator('[data-support-send]').click()
        await page.get_by_text('Нет сети. Снимок сохранён, отправим после подключения.').wait_for()
        saved=await page.evaluate("JSON.parse(localStorage.getItem('pv_support_pending_v1:101'))")
        before=len(posts)
        await page.reload(wait_until='load')
        await page.get_by_role('main').get_by_role('button',name='Сообщить о проблеме',exact=True).click()
        assert await page.locator('.pv-support textarea').input_value()=='Черновик не пропадает'
        await page.evaluate('changeOwner(202)')
        assert await page.locator('.pv-support').count()==0
        await context.set_offline(False)
        await page.wait_for_timeout(150)
        assert len(posts)==before,'account B must not upload account A report'
        await page.get_by_role('main').get_by_role('button',name='Сообщить о проблеме',exact=True).click()
        assert await page.locator('.pv-support textarea').input_value()==''
        await page.locator('[data-support-close]').click()
        await page.evaluate('changeOwner(101);window.dispatchEvent(new Event("online"))')
        await page.wait_for_function("() => !localStorage.getItem('pv_support_pending_v1:101')")
        assert posts[-1][0]=='signed-user-101' and posts[-1][1]==saved['payload']
        assert not errors,errors
        await context.close()

        # Disabled/quota-full storage still allows an in-tab offline report.
        context,page,errors=await page_for(blocked_storage=True)
        await page.get_by_role('main').get_by_role('button',name='Сообщить о проблеме',exact=True).click()
        await context.set_offline(True)
        await page.locator('[data-support-send]').click()
        await page.get_by_text('Нет сети. Снимок хранится только в этой вкладке — не закрывай её до отправки.').wait_for()
        await context.set_offline(False)
        await page.get_by_text(re.compile('Отчёт доставлен')).wait_for()
        assert not errors,errors
        await context.close()

        context,page,errors=await page_for()
        await page.evaluate("Telegram.WebApp.initData='';Telegram.WebApp.initDataUnsafe={};PVDiagnostics.record('lifecycle',{state:'active'})")
        await page.get_by_role('main').get_by_role('button',name='Сообщить о проблеме',exact=True).click()
        before=len(posts)
        await page.locator('[data-support-send]').click()
        await page.get_by_text(re.compile('Открой приложение через бота')).wait_for()
        assert len(posts)==before,'no anonymous ingestion fallback'
        await page.evaluate("document.addEventListener('keydown',e=>{if(e.key==='Escape')window.qaGameClosed=true})")
        await page.keyboard.press('Escape')
        assert await page.locator('.pv-support').count()==0
        assert not await page.evaluate('Boolean(window.qaGameClosed)'), 'closing the report must not reach game keyboard controls'
        await context.close()
        # Real admin scripts: triage, escaped player description and authenticated export.
        context=await browser.new_context(viewport={'width':1280,'height':800})
        await context.route('**/*',routing)
        page=await context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto('http://support.test/bot-admin',wait_until='load')
        await page.locator('[data-report]').wait_for()
        await page.screenshot(path=str(shots/'admin-list.png'))
        await page.locator('[data-report]').click()
        await page.locator('[data-support-triage]').wait_for()
        assert not await page.evaluate('Boolean(window.qaXss)')
        await page.screenshot(path=str(shots/'admin-detail.png'))
        async with page.expect_download() as exported:
            await page.locator('[data-support-export]').click()
        assert (await exported.value).suggested_filename=='PV-QATEST123456.json'
        await page.locator('[data-support-triage]').select_option('resolved')
        await page.get_by_role('button',name='Сохранить статус',exact=True).click()
        await page.get_by_text('Статус сохранён',exact=True).wait_for()
        assert admin_status=='resolved' and not errors,errors
        await context.close()
        await browser.close()
    print('PASS browser: manual silent-avatar report, safe last hour, 320/390/430/1280 + keyboard, frozen lost-ACK retry, drafts, offline account A/B isolation, unavailable storage and auth recovery')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--shots',type=Path,required=True);args=parser.parse_args()
    asyncio.run(main(args.shots))
