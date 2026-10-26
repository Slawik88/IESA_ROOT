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
from FastAPI.routers.bot_admin import mafia_online as admin
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import mafia_online as repo
from services import admin_people, mafia_online_scheduler as scheduler
from mafia_workspace_checks import check_workspace


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
            await admin_people.ensure_schema(PGAdapter(c))
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
    app.dependency_overrides[admin.staff] = lambda: {'id':9999}
    app.include_router(admin.router)

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
                page.wait_for_function("(() => {const b=document.getElementById('mo-quick');const r=b.getBoundingClientRect();return !b.disabled&&r.y>=0&&r.y<640&&r.bottom<=innerHeight;})()")
                page.screenshot(path=str(out / f"hub-{width}.png"), full_page=True)
                assert page.locator("#mo-quick").bounding_box()["y"] < 640
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
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
            pa.set_viewport_size({'width':320,'height':360})
            pa.wait_for_function("document.getElementById('modal').classList.contains('mo-tiny')")
            assert pa.locator('#mo-send').bounding_box()['y']+pa.locator('#mo-send').bounding_box()['height']<=360
            assert pa.locator('#mo-chat').bounding_box()['height']>=40
            pa.screenshot(path=str(out/'keyboard-320-360.png'),full_page=True)
            pa.set_viewport_size({'width':390,'height':844})
            def lose_response(route):
                route.fetch()  # Real server commits; the browser never receives the acknowledgement.
                route.abort("failed")

            def choose_target(page, target):
                """Choose through the action sheet and wait for the real server acknowledgement."""
                page.locator("#mo-action-open").click()
                page.locator("#mo-sheet").wait_for(state="visible")
                key = "none" if target is None else str(target)
                page.locator(f'#mo-sheet [data-mo-target="{key}"]').click()
                page.wait_for_function(
                    "target => MO.data?.me.action?.target===target && !document.getElementById('mo-sheet').open",
                    arg=target,
                )

            pa.route("**/mafia-online/rooms/*/messages", lose_response)
            pa.locator("#mo-text").fill("Привет из другого чата <b>без HTML</b>")
            pa.locator("#mo-send").click()
            pa.wait_for_function("moPendingMessage() && !MO.sending?.has(moMessageKey())")
            assert 'Привет из другого чата' in pa.locator('#mo-send-state').inner_text()
            assert pa.locator("#mo-send").inner_text() == "Проверить"
            assert pa.locator("#mo-text").input_value().startswith("Привет")
            pa.locator('#mo-text').fill('Новый текст после потерянного ответа')
            pa.locator('#mo-send').click()
            assert 'Привет из другого чата' in pa.locator('#mo-sheet').inner_text()
            pa.locator('#mo-sheet').get_by_role('button',name='Закрыть окно',exact=True).click()
            pa.unroute("**/mafia-online/rooms/*/messages", lose_response)
            pa.locator("#mo-send").click()
            pa.locator("#mo-sheet").get_by_role("button",name="Повторить без дубля",exact=True).click()
            pb.get_by_text("Привет из другого чата <b>без HTML</b>", exact=True).wait_for()
            pa.wait_for_function("!moPendingMessage()")
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
            check_workspace(pa, out)
            pa.locator('#mo-tab-table').click()
            pa.locator('#mo-settings-form').wait_for(state='visible')
            for title in ('Закрыть партию для всех','Покинуть город'):
                pa.get_by_role('button',name=title,exact=True).click()
                pa.locator('#mo-sheet').wait_for(state='visible')
                pa.locator('#mo-sheet').get_by_role('button',name='Остаться',exact=True).click()
                assert pa.evaluate("MO.data.phase==='lobby'")
            def forbidden_control(route):
                route.fulfill(status=403,content_type='application/json',json={'detail':'Только хозяин может начать партию.'})
            pa.route('**/mafia-online/rooms/*/control',forbidden_control)
            pa.evaluate("moControl('start')")
            pa.locator('#mo-control-pending').get_by_role('button',name='Проверить',exact=True).click()
            pa.locator('#mo-sheet').get_by_role('button',name='Не повторять',exact=True).click()
            pa.wait_for_function('moPendingCommand()===null&&!MO.busy')
            pa.unroute('**/mafia-online/rooms/*/control',forbidden_control)
            assert pa.locator('#mo-settings-form [name="roles"]').evaluate_all(
                '(inputs)=>inputs.every(input=>input.disabled)'
            ), 'automatic roles disable ignored manual choices'
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
            # Public votes stay accessible in the Players panel after accepted vote updates.
            pa.locator('#mo-settings-form select[name="vote_mode"]').select_option('open')
            pa.locator('#mo-settings-form button').click()
            pa.wait_for_function("MO.data.vote_mode==='open'")
            pa.locator('#mo-tab-chat').click()
            pb.locator("#mo-text").fill("Этот черновик переживёт обновление")
            pb.reload()
            pb.locator("#entry").click()
            pb.locator("#mo-text").wait_for()
            assert pb.locator("#mo-text").input_value() == "Этот черновик переживёт обновление"
            for uid in (103, 104):
                response = http.post(f"/mafia-online/rooms/{room}/join", headers={"x-test-user": str(uid)}, json={})
                assert response.status_code == 200, response.text
            pa.get_by_role("button", name="Начать партию", exact=True).click()
            pa.wait_for_function("MO.data?.phase==='night'")
            pa.locator('#mo-event[data-kind="role"]').wait_for(state="visible")
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
            pa.locator('#mo-sheet').get_by_role('button',name='Проверить',exact=True).click()
            pa.wait_for_function("MO.data?.phase==='paused'&&!document.getElementById('mo-control-pending').textContent")
            assert sum('поставил игру на паузу' in m['body'] for m in http.get(f'/mafia-online/rooms/{room}',headers={'x-test-user':'101'}).json()['messages']) == 1
            pa.evaluate("moControl('resume')")
            pa.wait_for_function("MO.data?.phase==='night'")
            pa.locator('#mo-event[data-kind="resume"]').wait_for(state="visible")
            assert http.post(f"/__qa/expire/{room}").status_code == 200
            pa.wait_for_function("MO.data?.phase==='discussion'")
            pb.wait_for_function("MO.data?.phase==='discussion'")
            pa.screenshot(path=str(out / "day-430.png"), full_page=True)
            pa.set_viewport_size({'width':390,'height':740})
            pa.evaluate("moHideEvent(); const m=[...MO.messages.values()].find(m=>m.user_id!==null&&!m.hidden);moReply(m.id)")
            pa.wait_for_timeout(80)
            assert pa.locator('#mo-role-open').is_visible()
            assert pa.locator('#mo-chat').bounding_box()['height'] >= 300, 'conversation keeps room even with a reply open'
            pa.screenshot(path=str(out/'day-reply-390.png'))
            pa.evaluate('moCancelReply()')
            pa.set_viewport_size({'width':430,'height':740})

            roles = {uid: http.get(f"/mafia-online/rooms/{room}", headers={"x-test-user": str(uid)}).json()["me"]["role"]
                     for uid in (101, 102, 103, 104)}
            mafioso = next(uid for uid, role in roles.items() if role == "mafia")
            phase = pa.evaluate("MO.data.phase_number")
            assert http.post(f"/mafia-online/rooms/{room}/control", headers={"x-test-user":"101"},
                             json={"command":"skip", "phase_number":phase}).status_code == 200
            chooser, uid = (pa, 101) if mafioso != 101 else (pb, 102)
            chooser.wait_for_function("MO.data?.phase==='voting'")
            chooser.locator('#mo-event[data-kind="vote"]').wait_for(state="visible")
            chooser.locator('#mo-tab-players').click()
            chooser.locator('#mo-public-votes').wait_for(state='visible')
            phase = chooser.evaluate("MO.data.phase_number")
            alternative = next(x for x in roles if x not in (uid, mafioso))
            choose_target(chooser, alternative)
            assert chooser.locator('#mo-tab-players').get_attribute('aria-pressed') == 'true'
            assert chooser.locator('#mo-public-votes').is_visible()
            assert chooser.locator('#mo-action-open').inner_text() == 'Изменить', 'a vote remains changeable'
            choose_target(chooser, mafioso)
            for voter in roles:
                if voter != uid:
                    r = http.post(f"/mafia-online/rooms/{room}/action", headers={"x-test-user":str(voter)},
                                  json={"kind":"vote", "phase_number":phase, "target":None if voter == mafioso else mafioso})
                    assert r.status_code == 200, r.text
            assert http.post(f"/__qa/expire/{room}").status_code == 200
            pa.wait_for_function("MO.data?.phase==='finished'")
            pb.wait_for_function("MO.data?.phase==='finished'")
            pa.locator('#mo-event[data-kind="finale"]').wait_for(state="visible")
            assert pa.evaluate("MO.data.players.every(p=>'role' in p)")
            assert pa.locator('#mo-text').is_enabled()
            pa.locator('#mo-text').fill('Спасибо за партию!')
            pa.locator('#mo-send').click()
            pb.get_by_text('Спасибо за партию!',exact=True).wait_for()
            pa.screenshot(path=str(out / "result-430.png"), full_page=True)
            # A stale response from the first room cannot paint over the hub.
            pa.locator(".mo-room-head button").first.click()
            pa.locator("#mo-quick").wait_for()
            pa.wait_for_timeout(2300)
            assert pa.locator(".mo-hub").count() == 1 and pa.locator("#mo-compose").count() == 0
            pa.locator(".mo-hub .v3-head-back").click()
            pa.wait_for_function("!document.getElementById('modal').open")
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
            pm.wait_for_function("MO.channel==='mafia'&&MO.data?.channel==='mafia'")
            pm.evaluate("moChannel('table')")
            pm.wait_for_function("MO.data?.channel==='table'")
            pm.evaluate('moRefresh()')
            assert pm.evaluate("MO.channel==='table'"), 'manual channel choice persists during the same phase'
            pm.evaluate("moChannel('mafia')")
            pm.wait_for_function("MO.data?.channel==='mafia'")
            assert pm.locator('#mo-invite').is_hidden()
            choose_target(pm, target)
            assert http.post(f'/mafia-online/rooms/{newer}/control',headers={'x-test-user':str(target)},json={'command':'leave'}).status_code==200
            pm.wait_for_function('MO.data?.me.choice_reset && !MO.data.me.action')
            assert 'Прежняя цель вышла' in pm.locator('#mo-actionbar').inner_text()
            assert pm.locator('#mo-action-open').is_enabled()
            pm.evaluate("moChannel('mafia')")
            pm.wait_for_function("MO.data?.channel==='mafia'")
            pm.locator('#mo-text').fill('Личный черновик команды')
            citizen=next(uid for uid,d in people.items() if d['me']['role']=='citizen' and uid!=target)
            citizen_context=browser.new_context(viewport={'width':390,'height':844})
            pc=citizen_context.new_page();pc.on('pageerror',lambda e:errors.append(str(e)))
            pc.goto(base+f'?user={citizen}');pc.locator('#entry').click()
            pc.wait_for_function("MO.data?.phase==='night'")
            survivor=next(uid for uid,d in people.items()
                          if d['me']['role']=='citizen' and uid not in (target,citizen))
            survivor_context=browser.new_context(viewport={'width':390,'height':844})
            ps=survivor_context.new_page();ps.on('pageerror',lambda e:errors.append(str(e)))
            ps.goto(base+f'?user={survivor}');ps.locator('#entry').click()
            ps.wait_for_function("MO.data?.phase==='night' && MO.messages.size>0")
            cached_id=ps.evaluate("""(() => {
                window.qaNightRow=[...MO.messages.values()].find(m=>m.user_id!==null&&!m.hidden);
                window.qaNightId=qaNightRow.id;
                return qaNightId;
            })()""")
            assert not ps.evaluate('moMessagePermissions(qaNightRow).can_reply')
            ps.locator(f'#mo-menu-{cached_id}').click()
            assert ps.locator('#mo-sheet').get_by_role('button',name='Ответить',exact=True).count()==0
            ps.locator('#mo-sheet').get_by_role('button',name='Закрыть окно',exact=True).click()
            phase=people[mafioso]['phase_number']
            for uid,d in people.items():
                if d['me']['role'] in ('mafia','don'):
                    assert http.post(f'/mafia-online/rooms/{newer}/action',headers={'x-test-user':str(uid)},
                                     json={'kind':'mafia_target','target':citizen,'phase_number':phase}).status_code==200
            pm.screenshot(path=str(out/'night-private-390.png'),full_page=True)
            assert http.post(f'/__qa/expire/{newer}').status_code==200
            pm.wait_for_function("MO.data?.phase==='discussion'&&MO.channel==='table'")
            assert pm.locator('#mo-text').input_value()==''
            assert pm.get_by_text('Личный черновик команды',exact=True).count()==0
            assert pm.evaluate("JSON.parse(sessionStorage.getItem(`pv_mo_${_uid}_${MO.room}_mafia`)).text")== 'Личный черновик команды'
            pc.wait_for_function("!MO.data?.me.alive&&MO.channel==='afterlife'&&MO.data?.channel==='afterlife'")
            pc.locator('#mo-event[data-kind="out"]').wait_for(state="visible")
            assert pc.locator('#mo-text').is_enabled()
            ps.wait_for_function("MO.data?.phase==='discussion' && MO.channel==='table'")
            assert ps.evaluate('MO.messages.get(qaNightId)===qaNightRow'), 'dawn reuses the cached table message'
            ps.locator(f'#mo-menu-{cached_id}').click()
            assert ps.locator('#mo-sheet').get_by_role('button',name='Ответить',exact=True).is_visible(), \
                'a night-cached message becomes replyable when the living player can speak at dawn'
            ps.locator('#mo-sheet').get_by_role('button',name='Закрыть окно',exact=True).click()
            survivor_context.close()
            citizen_context.close()
            private_context.close()
            # Full production admin shell -> real report API/PG -> mute -> closed history -> unmute.
            post=http.post(f'/mafia-online/rooms/{newer}/messages',headers={'x-test-user':str(mafioso)},
                           json={'text':'Проверка для персонала','nonce':str(uuid.uuid4())}).json()
            assert 'id' in post, post
            assert http.post(f'/mafia-online/rooms/{newer}/moderation',headers={'x-test-user':str(citizen)},
                             json={'kind':'report','message_id':post['id']}).status_code==200
            from admin_stand_fixtures import ME as STAFF
            admin_context=browser.new_context(viewport={'width':390,'height':844})
            admin_context.add_init_script("localStorage.setItem('pv_admin_prefs',JSON.stringify({theme:'dark'}))")
            def admin_assets(route):
                from urllib.parse import urlsplit
                path=urlsplit(route.request.url).path
                if not route.request.url.startswith(base):return route.abort()
                fixtures={'/bot-admin/api/me':{**STAFF,'sections':[{'key':'reports','title':'Жалобы'}]},
                          '/bot-admin/api/badges':{'reports':1},
                          '/bot-admin/api/reports':{'counts':{'new':1,'in_work':0,'resolved':0,'rejected':0},'items':[],'repeat':[]}}
                if path in fixtures:return route.fulfill(json=fixtures[path])
                if path=='/bot-admin/':
                    source=(ROOT/'FastAPI/static/bot-admin/index.html').read_text(encoding='utf-8').replace('{{BASE}}',base).replace('{{VER}}','test')
                    return route.fulfill(content_type='text/html',body=source)
                name=path.rsplit('/',1)[-1]
                if path.startswith('/bot-admin/') and name.startswith('admin') and name.endswith(('.css','.js')):
                    return route.fulfill(content_type='text/css' if name.endswith('.css') else 'text/javascript',
                        body=(ROOT/'FastAPI/static/bot-admin'/name).read_text(encoding='utf-8'))
                return route.continue_()
            admin_context.route('**/*',admin_assets)
            staff=admin_context.new_page();staff.on('pageerror',lambda e:errors.append(str(e)))
            staff.goto(base+'/bot-admin/')
            staff.get_by_role('button',name='Межчатовая Мафия ›',exact=True).click()
            staff.get_by_role('button',name='Мут в этой партии',exact=True).click()
            staff.locator('#sok').click()
            staff.get_by_text('Открытых жалоб нет.',exact=True).wait_for()
            assert not http.get(f'/mafia-online/rooms/{newer}',headers={'x-test-user':str(mafioso)}).json()['me']['can_write']
            staff.get_by_role('button',name='Решённые',exact=True).click()
            staff.get_by_text('Проверка для персонала',exact=True).wait_for()
            for width in (320,390,430):
                staff.set_viewport_size({'width':width,'height':844})
                assert staff.evaluate('document.documentElement.scrollWidth<=innerWidth')
                staff.screenshot(path=str(out/f'admin-reports-{width}.png'),full_page=True)
            staff.get_by_role('button',name='Снять мут',exact=True).click()
            staff.locator('#sok').click()
            staff.locator('#sheet').wait_for(state='hidden')
            assert http.get(f'/mafia-online/rooms/{newer}',headers={'x-test-user':str(mafioso)}).json()['me']['can_write']
            admin_context.close()
            pa.evaluate("openMafiaOnline(999999,'bad')")
            pa.get_by_role("button", name="В хаб", exact=True).wait_for()
            pa.get_by_role("button", name="В хаб", exact=True).click()
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
