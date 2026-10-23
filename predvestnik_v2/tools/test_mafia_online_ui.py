"""Browser integration against the real online services and isolated PostgreSQL.

Test-only server on loopback; production CSS, shared header/dialog functions, online JS.
python tools/test_mafia_online_ui.py --dsn postgresql://...@127.0.0.1:55439/... --out output/playwright/mafia-online
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import socket
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import asyncpg
import httpx
import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from playwright.sync_api import sync_playwright

from FastAPI.deps import get_db
from FastAPI.routers import mafia_online as api
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import mafia_online as repo
from services import mafia_online_scheduler as scheduler


def function(file, name):
    source = (ROOT / "FastAPI/static" / file).read_text(encoding="utf-8")
    match = re.search(rf"^function {name}\(.*?^\}}", source, re.M | re.S)
    assert match, name
    return match.group()


def html():
    # Actual shared components rather than a second implementation of the game's UI.
    helpers = """const BASE='',tg=null;const el=id=>document.getElementById(id);
      const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
      const _uid=Number(new URLSearchParams(location.search).get('user')||'101');
      const hdrs=()=>({'x-test-user':String(_uid),'content-type':'application/json'});
      let _modalReturnFocus=null;const _MF_VARIANT={primary:'',ghost:' v3-pill--ghost'};
      const CM=()=>el('modal').close();function v3GlintMark(){return '';}function openMafiaStats(){CM();}
    """
    helpers += function("app.01.js", "OM") + function("app.20.js", "v3Head")
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
      <link rel="stylesheet" href="/static/app.css"><link rel="stylesheet" href="/static/shell-v3.css">
      <link rel="stylesheet" href="/static/shell-v3-home.css"><link rel="stylesheet" href="/static/mafia-online-v3.css">
      <body><button class="v3-pill" id="entry" onclick="openMafiaOnline()">Мафия · онлайн</button>
      <dialog id="modal" aria-labelledby="mt"><div class="sheet"><div class="sheet-grip"></div><div class="mhead"><span id="mt" class="mtitle"></span>
      <button class="mclose" onclick="CM()" aria-label="Закрыть">×</button></div><div id="mb" class="mbody"></div><div id="mf" class="mfoot"></div></div></dialog>
      <script>{helpers}</script><script src="/static/app.55.js"></script><script src="/static/app.56.js"></script></body></html>"""


def build_app(dsn):
    schema = "mafia_ui_qa_" + uuid.uuid4().hex[:12]

    @asynccontextmanager
    async def lifespan(app):
        conn = await asyncpg.connect(dsn)
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.close()
        app.state.pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5, server_settings={"search_path": schema})
        async with app.state.pool.acquire() as c:
            await repo.ensure_tables(PGAdapter(c))
        try:
            yield
        finally:
            await app.state.pool.close()
            conn = await asyncpg.connect(dsn)
            await conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await conn.close()

    app = FastAPI(lifespan=lifespan)

    async def database():
        async with app.state.pool.acquire() as conn:
            yield PGAdapter(conn)

    async def user(request: Request):
        uid = int(request.headers.get("x-test-user", "101"))
        return {"id": uid, "first_name": f"Игрок {uid}"}

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[api.participant] = user
    app.dependency_overrides[api.router.dependencies[0].dependency] = lambda: None
    app.include_router(api.router)

    @app.get("/")
    async def page():
        return HTMLResponse(html())

    @app.get("/static/{name:path}")
    async def asset(name: str):
        path = (ROOT / "FastAPI/static" / name).resolve()
        assert path.is_relative_to((ROOT / "FastAPI/static").resolve())
        return FileResponse(path)

    @app.post("/__qa/expire/{room_id}")
    async def expire(room_id: int, db=Depends(database)):
        async with db.connection.transaction():
            state = await repo.load(db, room_id, lock=True)
            state["deadline"] = await repo.now(db) - 1
            await repo.save(db, state)
        await scheduler.tick(db)
        return {"ok": True}

    @app.post("/__qa/history/{room_id}")
    async def history(room_id: int, db=Depends(database)):
        for i in range(101):
            await repo.message(db, room_id, 'table', f'Поток {i}', user_id=101, name='Игрок 101', seat=1)
        return {"ok": True}

    return app


def check(dsn, out):
    out.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(build_app(dsn), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            if server.started:
                break
            time.sleep(.1)
        assert server.started
        with httpx.Client(base_url=base) as http, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
            errors = []
            for width in (320, 390, 430):
                context = browser.new_context(viewport={"width": width, "height": 740})
                page = context.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base)
                page.locator("#entry").click()
                page.locator("#mo-quick").wait_for()
                assert page.locator("#mo-quick").bounding_box()["y"] < 640
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(out / f"hub-{width}.png"), full_page=True)
                context.close()
            a, b = [browser.new_context(viewport={"width": 390, "height": 844}) for _ in range(2)]
            pa, pb = a.new_page(), b.new_page()
            for p in (pa, pb):
                p.on("pageerror", lambda e: errors.append(str(e)))
            pa.goto(base + "?user=101")
            pa.locator("#entry").click()
            pa.locator("#mo-quick").click()
            pa.locator("#mo-text").wait_for()
            room = pa.evaluate("MO.room")
            pb.goto(base + "?user=102")
            pb.locator("#entry").click()
            pb.locator("#mo-quick").click()
            pb.locator("#mo-text").wait_for()
            assert pb.evaluate("MO.room") == room
            for width in (320,390,430):
                pa.set_viewport_size({'width':width,'height':640})
                pa.screenshot(path=str(out/f'lobby-{width}-640.png'),full_page=True)
                assert pa.evaluate("document.getElementById('mo-status').scrollHeight<=document.getElementById('mo-status').clientHeight+1"), 'lobby status must not hide controls in a nested scroller'
                assert pa.locator('#mo-info-toggle').is_visible()
                assert pa.locator('#mo-chat').bounding_box()['height']>=140
                assert pa.locator('#mo-send').bounding_box()['y']+pa.locator('#mo-send').bounding_box()['height']<=640
            pa.locator('#mo-text').focus()
            pa.set_viewport_size({'width':320,'height':360})
            pa.screenshot(path=str(out/'keyboard-320-360.png'),full_page=True)
            assert pa.locator('#mo-send').bounding_box()['y']+pa.locator('#mo-send').bounding_box()['height']<=360
            assert pa.locator('#mo-chat').bounding_box()['height']>=60
            pa.locator('#mo-text').blur();pa.set_viewport_size({'width':390,'height':844})
            def lose_response(route):
                route.fetch()  # Real server commits; the browser never receives the acknowledgement.
                route.abort("failed")
            pa.route("**/mafia-online/rooms/*/messages", lose_response)
            pa.locator("#mo-text").fill("Привет из другого чата <b>без HTML</b>")
            pa.locator("#mo-send").click()
            pa.get_by_text("Нет связи. Текст сохранён — отправьте снова.", exact=True).wait_for()
            assert pa.locator("#mo-text").input_value().startswith("Привет")
            pa.unroute("**/mafia-online/rooms/*/messages", lose_response)
            pa.locator('#mo-text').fill('Новый текст после потерянного ответа')
            pa.locator("#mo-send").click()
            pa.get_by_text('Сначала проверьте доставку прошлого сообщения. Новый текст сохранён.',exact=True).wait_for()
            pa.reload();pa.locator('#entry').click();pa.locator('#mo-text').wait_for()
            assert pa.locator('#mo-text').input_value()=='Новый текст после потерянного ответа'
            pa.locator('#mo-message-pending').get_by_role('button',name='Проверить',exact=True).click()
            pb.get_by_text("Привет из другого чата <b>без HTML</b>", exact=True).wait_for()
            pa.wait_for_function("!document.getElementById('mo-message-pending').textContent")
            assert pa.locator('#mo-text').input_value()=='Новый текст после потерянного ответа'
            pa.locator('#mo-text').fill('')
            assert sum(m["body"].startswith("Привет") for m in http.get(f"/mafia-online/rooms/{room}", headers={"x-test-user":"101"}).json()["messages"]) == 1
            assert pb.locator("#mo-messages b").filter(has_text="без HTML").count() == 0
            pa.evaluate("window.qaMessage=document.querySelector('.mo-msg:not(.system)')")
            pa.evaluate("moRefresh()")
            assert pa.evaluate("qaMessage===document.querySelector('.mo-msg:not(.system)')"), 'unchanged messages retain their DOM nodes'
            assert http.post(f'/__qa/history/{room}').status_code == 200
            pa.wait_for_function("[...MO.messages.values()].filter(m=>m.body.startsWith('Поток ')).length===101")
            pa.evaluate("document.getElementById('mo-chat').scrollTop=0")
            pa.evaluate("moMessages([{id:999999,user_id:102,name:'Другой игрок',seat:2,body:'Новый внизу',time:Date.now()/1000}],false)")
            assert pa.locator('#mo-new').is_visible()
            pa.locator('#mo-new').click()
            assert pa.locator('#mo-new').is_hidden()
            # Discard the synthetic UI-only row before further real-server polling.
            pa.evaluate("MO.messages.delete(999999);document.querySelector('[data-msg=\"999999\"]').remove()")
            pa.locator('#mo-info-toggle').click()
            pa.locator('.mo-controls > summary').click()
            # Confirmations and service errors remain visible in the info panel.
            pa.locator('.mo-controls').get_by_role('button',name='Закрыть партию',exact=True).click()
            assert pa.locator('#mo-error').is_visible()
            pa.locator('#mo-error').get_by_role('button',name='Отмена',exact=True).click()
            pa.locator('.mo-controls').get_by_role('button',name='Выйти из партии',exact=True).click()
            assert pa.locator('#mo-error').is_visible()
            pa.locator('#mo-error').get_by_role('button',name='Отмена',exact=True).click()
            def forbidden_control(route):
                route.fulfill(status=403,content_type='application/json',body='{"detail":"Только хозяин может начать партию."}')
            pa.route('**/mafia-online/rooms/*/control',forbidden_control)
            pa.evaluate("moControl('start')")
            pa.locator('#mo-control-pending').get_by_role('button',name='Не повторять',exact=True).wait_for()
            assert pa.locator('#mo-error').is_visible()
            pa.locator('#mo-control-pending').get_by_role('button',name='Не повторять',exact=True).click()
            pa.wait_for_function('moPendingCommand()===null&&!MO.busy')
            pa.unroute('**/mafia-online/rooms/*/control',forbidden_control)
            pa.locator('#mo-settings-form select[name="tempo"]').focus()
            # A second window edits the server while this window keeps an old focused form.
            assert http.post(f'/mafia-online/rooms/{room}/control', headers={'x-test-user':'101'},
                             json={'command':'settings','settings':{'tempo':'slow'}}).status_code == 200
            pa.evaluate('moRefresh()')
            assert pa.locator('#mo-settings-form select[name="tempo"]').input_value() == 'normal'
            pa.locator('#mo-settings-form button').click()  # Save unchanged stale fields.
            pa.wait_for_function("document.getElementById('mo-error').textContent.includes('Стол изменился')&&!MO.busy")
            assert pa.locator('#mo-settings-form select[name="tempo"]').input_value() == 'slow'
            pa.locator('#mo-settings-form select[name="tempo"]').focus()
            assert http.post(f'/mafia-online/rooms/{room}/control', headers={'x-test-user':'101'},
                             json={'command':'settings','settings':{'tempo':'normal'}}).status_code == 200
            pa.evaluate('moRefresh()')
            pa.locator('#mo-settings-form select[name="seats"]').select_option('10')
            pa.locator('#mo-settings-form button').click()
            pa.wait_for_function("document.getElementById('mo-error').textContent.includes('Стол изменился')&&!MO.busy")
            assert pa.locator('#mo-settings-form select[name="tempo"]').input_value() == 'normal'
            assert pa.locator('#mo-settings-form select[name="seats"]').input_value() == '8'
            pa.locator('#mo-settings-form select[name="tempo"]').focus()
            pa.locator('#mo-settings-form select[name="tempo"]').select_option('slow')
            pa.evaluate('moRefresh()')
            assert pa.locator('#mo-settings-form select[name="tempo"]').input_value() == 'slow'
            pa.locator('#mo-settings-form select[name="tempo"]').blur()
            pa.evaluate('moRefresh()')
            assert pa.locator('#mo-settings-form select[name="tempo"]').input_value() == 'slow'
            # Open vote disclosure must survive the next accepted vote/version update.
            pa.locator('#mo-settings-form select[name="vote_mode"]').select_option('open')
            pa.locator('#mo-settings-form button').click()
            pa.wait_for_function("MO.data.vote_mode==='open'")
            pb.locator("#mo-text").fill("Этот черновик переживёт обновление")
            pb.reload()
            pb.locator("#entry").click()
            pb.locator("#mo-text").wait_for()
            assert pb.locator("#mo-text").input_value() == "Этот черновик переживёт обновление"
            for uid in (103, 104):
                response = http.post(f"/mafia-online/rooms/{room}/join", headers={"x-test-user": str(uid)}, json={})
                assert response.status_code == 200, response.text
            pa.locator('#mo-info-toggle').click()
            pa.get_by_role("button", name="Начать партию", exact=True).click()
            pa.wait_for_function("MO.data?.phase==='night'")
            assert pa.evaluate("MO.data.players.every(p=>!('role' in p))")
            for width in (320, 390, 430):
                pa.set_viewport_size({"width": width, "height": 740})
                pa.screenshot(path=str(out / f"night-{width}.png"), full_page=True)
                assert pa.evaluate("document.documentElement.scrollWidth <= innerWidth")
            pa.route('**/mafia-online/rooms/*/control', lose_response)
            pa.evaluate("moControl('pause')")
            pa.get_by_role('button', name='Проверить', exact=True).wait_for()
            pa.unroute('**/mafia-online/rooms/*/control', lose_response)
            pa.reload();pa.locator('#entry').click()
            pa.get_by_role('button', name='Проверить', exact=True).click()
            pa.wait_for_function("MO.data?.phase==='paused'&&!document.getElementById('mo-control-pending').textContent")
            assert sum('поставил игру на паузу' in m['body'] for m in http.get(f'/mafia-online/rooms/{room}',headers={'x-test-user':'101'}).json()['messages']) == 1
            pa.evaluate("moControl('resume')")
            pa.wait_for_function("MO.data?.phase==='night'")
            assert http.post(f"/__qa/expire/{room}").status_code == 200
            pa.wait_for_function("MO.data?.phase==='discussion'")
            pb.wait_for_function("MO.data?.phase==='discussion'")
            pa.screenshot(path=str(out / "day-430.png"), full_page=True)
            roles = {uid: http.get(f"/mafia-online/rooms/{room}", headers={"x-test-user": str(uid)}).json()["me"]["role"]
                     for uid in (101, 102, 103, 104)}
            mafioso = next(uid for uid, role in roles.items() if role == "mafia")
            phase = pa.evaluate("MO.data.phase_number")
            assert http.post(f"/mafia-online/rooms/{room}/control", headers={"x-test-user":"101"},
                             json={"command":"skip", "phase_number":phase}).status_code == 200
            chooser, uid = (pa, 101) if mafioso != 101 else (pb, 102)
            chooser.wait_for_function("MO.data?.phase==='voting'")
            chooser.locator('.mo-open-votes summary').click()
            phase = chooser.evaluate("MO.data.phase_number")
            alternative = next(x for x in roles if x not in (uid, mafioso))
            chooser.locator(f'[data-mo-target="{alternative}"]').click()
            chooser.wait_for_function("arg => MO.data?.me.action?.target===arg", arg=alternative)
            assert chooser.locator('.mo-open-votes').evaluate('(e)=>e.open')
            assert chooser.locator(".mo-target[disabled]").count() == 0, "a vote remains changeable"
            chooser.locator(f'[data-mo-target="{mafioso}"]').click()
            chooser.wait_for_function("arg => MO.data?.me.action?.target===arg", arg=mafioso)
            for voter in roles:
                if voter != uid:
                    r = http.post(f"/mafia-online/rooms/{room}/action", headers={"x-test-user":str(voter)},
                                  json={"kind":"vote", "phase_number":phase, "target":None if voter == mafioso else mafioso})
                    assert r.status_code == 200, r.text
            assert http.post(f"/__qa/expire/{room}").status_code == 200
            pa.wait_for_function("MO.data?.phase==='finished'")
            pb.wait_for_function("MO.data?.phase==='finished'")
            assert pa.evaluate("MO.data.players.every(p=>'role' in p)")
            pa.screenshot(path=str(out / "result-430.png"), full_page=True)
            # A stale response from the first room cannot paint over the hub.
            pa.locator(".mo-room-head button").first.click()
            pa.locator("#mo-quick").wait_for()
            pa.wait_for_timeout(2300)
            assert pa.locator(".mo-hub").count() == 1 and pa.locator("#mo-compose").count() == 0
            pa.locator(".mclose").click()
            assert pa.evaluate("MO.timer===null||!document.querySelector('#modal').open")
            # Hold an old history page while a moderator hides one of its messages.
            newer = http.post('/mafia-online/rooms',headers={'x-test-user':'101'},json={}).json()['room_id']
            assert http.post(f'/__qa/history/{newer}').status_code==200
            pa.evaluate('openMafiaOnline()')
            pa.wait_for_function('MO.data?.phase===\'lobby\'')
            before = pa.evaluate('Math.min(...MO.messages.keys())')
            old_rows = http.get(f'/mafia-online/rooms/{newer}?before={before}',headers={'x-test-user':'101'}).json()['messages']
            hidden = next(m for m in old_rows if m['body']=='Поток 0')
            def stale_history(route):
                response=route.fetch()
                assert any(m['id']==hidden['id'] for m in response.json()['messages'])
                assert http.post(f'/mafia-online/rooms/{newer}/moderation',headers={'x-test-user':'101'},
                                 json={'kind':'hide','message_id':hidden['id']}).status_code==200
                pa.evaluate('moRefresh()')
                route.fulfill(response=response)
            pa.route('**/mafia-online/rooms/*?*before=*',stale_history)
            pa.evaluate('moOlder()')
            assert pa.get_by_text('Поток 0',exact=True).count()==0, 'stale history must not restore a redacted body'
            pa.unroute('**/mafia-online/rooms/*?*before=*',stale_history)
            pa.evaluate('moOlder()')
            assert pa.get_by_text('Сообщение скрыто',exact=True).count()==1
            # A live private channel disappears at dawn; its unsent text must stay private.
            for extra in range(102,109):
                assert http.post(f'/mafia-online/rooms/{newer}/join',headers={'x-test-user':str(extra)},json={}).status_code==200
            people={extra:http.get(f'/mafia-online/rooms/{newer}',headers={'x-test-user':str(extra)}).json()
                    for extra in range(101,109)}
            mafioso=next(uid for uid,d in people.items() if d['me']['role']=='mafia')
            target=next(p['id'] for p in people[mafioso]['players'] if people[p['id']]['me']['role']=='citizen')
            private_context=browser.new_context(viewport={'width':390,'height':844})
            pm=private_context.new_page();pm.on('pageerror',lambda e:errors.append(str(e)))
            pm.goto(base+f'?user={mafioso}');pm.locator('#entry').click()
            pm.wait_for_function("MO.data?.phase==='night'")
            pm.locator(f'[data-mo-target="{target}"]').click()
            pm.wait_for_function('MO.data?.me.action!==null')
            assert http.post(f'/mafia-online/rooms/{newer}/control',headers={'x-test-user':str(target)},json={'command':'leave'}).status_code==200
            pm.get_by_text('Цель вышла · выберите заново',exact=True).wait_for()
            pm.evaluate("moChannel('mafia')")
            pm.wait_for_function("MO.data?.channel==='mafia'")
            pm.locator('#mo-text').fill('Личный черновик команды')
            pm.screenshot(path=str(out/'night-private-390.png'),full_page=True)
            assert http.post(f'/__qa/expire/{newer}').status_code==200
            pm.wait_for_function("MO.data?.phase==='discussion'&&MO.channel==='table'")
            assert pm.locator('#mo-text').input_value()==''
            assert pm.get_by_text('Личный черновик команды',exact=True).count()==0
            assert pm.evaluate("JSON.parse(sessionStorage.getItem(`pv_mo_${_uid}_${MO.room}_mafia`)).text")== 'Личный черновик команды'
            private_context.close()
            pa.evaluate("openMafiaOnline(999999,'bad')")
            pa.get_by_role("button", name="К столам", exact=True).wait_for()
            pa.get_by_role("button", name="К столам", exact=True).click()
            pa.locator("#mo-quick").wait_for()
            assert not errors, errors
            a.close(); b.close(); browser.close()
        print("PASS browsers: chat burst/scroll/DOM, focused settings conflict, lost control ACK/reload, votes, stale history after redaction, departed target, private draft at dawn, mobile/navigation")
    finally:
        server.should_exit = True
        thread.join(timeout=15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", type=Path, default=Path("output/playwright/mafia-online"))
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("loopback PostgreSQL required")
    check(args.dsn, args.out)
