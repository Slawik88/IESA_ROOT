"""Current-design functional audit against real services and disposable PostgreSQL.

The audit reuses the canonical browser fixture in an isolated database schema.
The report includes actual rendered geometry and screenshots from this run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from playwright.sync_api import sync_playwright

from mafia_online_audit_stand import DSN, audit_app


def run(dsn, out, functional_only=False):
    out.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(audit_app(dsn), host="127.0.0.1", port=port, log_level="error"))
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{port}"
    errors, checks, geometry = [], [], []

    def check(condition, label):
        if not condition:
            raise AssertionError(label)
        checks.append(label)

    def settled(page):
        # A received JSON response precedes both automatic private-channel entry and
        # the shared sheet's opening animation. Measure the finished view only.
        page.wait_for_function("MO.data?.me?.id>0 && MO.data.channel===MO.channel && MO.statusKey && !MO.busy")
        page.evaluate("""async () => {
          const animations=document.getAnimations().filter(a=>Number.isFinite(a.effect?.getComputedTiming().iterations));
          await Promise.all(animations.map(a=>a.finished.catch(()=>{})));
          await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        }""")

    def tab(page, name):
        page.locator(f'[data-mo-tab="{name}"]').click()
        page.locator(f'#mo-panel-{name}').wait_for(state="visible")

    try:
        for _ in range(150):
            if server.started or not worker.is_alive():
                break
            time.sleep(.1)
        check(server.started, "disposable real-API server started")
        with httpx.Client(base_url=base) as client, sync_playwright() as pw:
            items = {item["key"]:item for item in client.get("/__qa/scenarios").json()["scenarios"]}
            browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
            viewports=() if functional_only else ((320,844),(390,844),(430,844),(320,500),(390,500),(430,500))
            for width, height in viewports:
                context = browser.new_context(viewport={"width":width, "height":height}, reduced_motion="reduce")
                page = context.new_page()
                page.on("pageerror", lambda error:errors.append(str(error)))
                page.goto(base+"/?user=999001")
                page.locator("#mo-quick").wait_for()
                page.evaluate("""async()=>{await Promise.all(document.getAnimations().filter(a=>Number.isFinite(a.effect?.getComputedTiming().iterations)).map(a=>a.finished.catch(()=>{})));}""")
                check(page.locator("#mo-quick").is_visible(), f"{width}: one-button hub entry visible")
                check(page.evaluate("document.documentElement.scrollWidth<=innerWidth"), f"{width}: hub no horizontal overflow")
                page.screenshot(path=str(out/f"hub-{width}x{height}.png"), full_page=True)
                for name in items:
                    item = items[name]
                    page.goto(base+item["url"])
                    settled(page)
                    check(page.evaluate("MO.room")==item["room_id"], f"{width}:{name}: correct room")
                    check(page.evaluate("document.documentElement.scrollWidth<=innerWidth"), f"{width}:{name}: no horizontal overflow")
                    check(page.locator("#mo-text").is_disabled() == (not page.evaluate("MO.data.me.can_write")), f"{width}:{name}: compose matches server access")
                    if name in ("mafia", "dead"):
                        expected = "mafia" if name=="mafia" else "afterlife"
                        page.wait_for_function("expected=>MO.channel===expected", arg=expected)
                        check(page.evaluate("MO.channel")==expected, f"{width}:{name}: correct private channel selected")
                    check(not page.evaluate("MO.data.players.some(p=>p.role) && !['finished','cancelled'].includes(MO.data.phase)"), f"{width}:{name}: unrevealed roles remain private")
                    measured=page.evaluate("""() => {
                      const box=id=>{const e=document.getElementById(id);if(!e)return null;const r=e.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height,visible:r.width>0&&r.height>0};};
                      const smallButtons=[...document.querySelectorAll('button')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&(r.width<44||r.height<44);}).map(e=>({label:e.getAttribute('aria-label')||e.textContent.trim(),width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}));
                      return {chat:box('mo-chat'),compose:box('mo-compose'),status:box('mo-status'),bodyScroll:document.scrollingElement.scrollHeight,viewport:innerHeight,smallButtons};
                    }""")
                    geometry.append({"width":width,"height":height,"scenario":name,"room":item["room_id"], **measured})
                    check(measured["compose"]["y"]+measured["compose"]["height"]<=height+1, f"{width}x{height}:{name}: composer fits viewport")
                    check(measured["chat"]["height"]>=100, f"{width}x{height}:{name}: chat retains 100px readable space")
                    check(page.locator("#mo-tabs").is_visible(), f"{width}x{height}:{name}: navigation remains visible")
                    page.screenshot(path=str(out/f"{name}-{width}x{height}.png"), full_page=True)
                    if width==390 and height==844:
                        tab(page,"players")
                        check(page.locator("#mo-player-search").is_visible(), f"{name}: player search available")
                        check(page.locator("#mo-players-list").is_visible(), f"{name}: player list available")
                        tab(page,"table")
                        if name not in ("finished","cancelled","postexpired"):
                            check(page.locator("#mo-table-controls").is_visible(), f"{name}: table controls available")
                        if name=="lobby":
                            check(page.locator("#mo-settings-form").is_visible(), "host lobby settings visible in table tab")
                        tab(page,"chat")
                        check(page.locator("#mo-compose").is_visible(), f"{name}: returning to chat restores composer")
                context.close()
            if not functional_only:
                (out/"geometry.json").write_text(json.dumps(geometry,ensure_ascii=False,indent=2),encoding="utf-8")
                print(f"LAYOUT PASS: {len(checks)} checks; {len(geometry)} settled phase views",flush=True)

            context = browser.new_context(viewport={"width":390,"height":844})
            page = context.new_page()
            page.on("pageerror", lambda error:errors.append(str(error)))
            day=items["day"]
            page.goto(base+day["url"])
            settled(page)
            page.wait_for_function("MO.data?.me.can_write")
            check(page.locator("#mo-send").is_disabled(), "empty message cannot be sent")
            check("600" in page.locator("#mo-counter").inner_text(), "visible character limit")
            message="Проверка <img src=x onerror=alert(1)> и перенос\nвторой строки"
            page.locator("#mo-text").fill(message)
            page.evaluate("moRefresh()")
            settled(page)
            check(page.locator("#mo-text").input_value()==message, "poll retains composed text")
            page.reload()
            settled(page)
            check(page.locator("#mo-text").input_value()==message, "reload restores session draft")
            page.locator("#mo-send").click()
            page.wait_for_function("document.getElementById('mo-text').value===''")
            page.get_by_text(message, exact=True).wait_for()
            check(page.locator("#mo-messages img[src=x]").count()==0, "message markup escaped")
            check(page.evaluate("[...MO.messages.values()].filter(m=>m.body.startsWith('Проверка <img')).length")==1, "message sent once")
            sent=page.evaluate("[...MO.messages.values()].find(m=>m.body.startsWith('Проверка <img')).id")
            page.locator(f'[data-msg="{sent}"] .mo-msg-menu').click()
            page.locator("#mo-sheet").get_by_role("button",name="Ответить",exact=True).click()
            check(page.locator("#mo-reply").inner_text().strip()!="", "reply preview shown")
            page.reload()
            settled(page)
            check(page.evaluate("MO.reply?.id")==sent, "reply restored after reload")
            page.locator('#mo-reply button[aria-label="Отменить ответ"]').click()
            check(page.evaluate("MO.reply===null"), "reply can be cancelled")
            page.locator("#mo-text").fill("Строка 1")
            line_height=page.locator("#mo-text").bounding_box()["height"]
            page.locator("#mo-text").press("Shift+Enter")
            page.locator("#mo-text").press("T")
            check("\n" in page.locator("#mo-text").input_value(), "Shift Enter inserts newline")
            page.locator("#mo-text").fill("Строка 1\nСтрока 2\nСтрока 3")
            check(page.locator("#mo-text").bounding_box()["height"]>line_height, "multiline composer grows with text")
            page.locator("#mo-text").fill("🙂"*600)
            check(page.evaluate("[...document.getElementById('mo-text').value].length")==600, "600 Unicode characters fit the composer")
            check("600" in page.locator("#mo-counter").inner_text(), "counter counts Unicode characters")
            page.locator("#mo-text").fill("")
            # The server accepts a message, but the network drops its acknowledgement.
            # Retry must reuse the saved nonce and must retain a visible send state.
            def lose_ack(route):
                response=route.fetch()
                check(response.status==200,"lost-ack fixture really committed the first send")
                route.abort("failed")
            page.wait_for_timeout(1600)  # Separate this delivery check from the global chat rate limit.
            page.route("**/mafia-online/rooms/*/messages", lose_ack)
            retry_text="Ответ потерялся, сообщение остаётся одним"
            page.locator("#mo-text").fill(retry_text)
            page.locator("#mo-send").click()
            page.wait_for_function("text=>!MO.busy && !MO.sending?.size && moPendingMessage()?.text===text",arg=retry_text)
            check(page.locator("#mo-text").input_value()==retry_text, "lost acknowledgement retains text")
            check(page.locator("#mo-send-state").inner_text().strip()!="", "failed send exposes a visible message state")
            page.unroute("**/mafia-online/rooms/*/messages",lose_ack)
            # Edit a second message while the first acknowledgement is uncertain.
            # The old immutable send is retried, while the new draft/reply must survive.
            page.locator(f'[data-msg="{sent}"] .mo-msg-menu').click()
            page.locator("#mo-sheet").get_by_role("button",name="Ответить",exact=True).click()
            newer_draft="Новый текст "*50
            page.locator("#mo-text").fill(newer_draft)
            page.set_viewport_size({"width":320,"height":500})
            page.locator("#mo-text").focus()
            measured=page.evaluate("""() => {
              const panel=document.getElementById('mo-panel-chat'),compose=document.getElementById('mo-compose').getBoundingClientRect();
              return {bottom:compose.bottom,chat:document.getElementById('mo-chat').getBoundingClientRect().height,
                      noClip:panel.scrollHeight<=panel.clientHeight+1};
            }""")
            check(measured["bottom"]<=501 and measured["chat"]>=100 and measured["noClip"], "320x500 long draft + reply + uncertain send fit without clipping")
            page.screenshot(path=str(out/"composite-keyboard-320x500.png"),full_page=True)
            page.locator("#mo-send").click()
            page.locator("#mo-sheet").get_by_role("button",name="Повторить без дубля",exact=True).click()
            page.wait_for_function("!MO.sending?.size && !moPendingMessage()")
            check(page.locator("#mo-text").input_value()==newer_draft, "acknowledging the previous send preserves a newer edited draft")
            check(page.evaluate("MO.reply?.id")==sent, "acknowledging the previous send preserves a newer reply")
            check(page.evaluate("text=>[...MO.messages.values()].filter(m=>m.body===text).length",retry_text)==1, "retry after lost acknowledgement does not duplicate message")
            page.locator("#mo-text").fill("")
            page.locator('#mo-reply button[aria-label="Отменить ответ"]').click()
            page.set_viewport_size({"width":390,"height":844})

            # Actual role actions are submitted to the real API, then checked after a refresh.
            for name in ("doctor","detective","mafia","voting"):
                item=items[name]
                page.goto(base+item["url"])
                settled(page)
                page.locator("#mo-action-open").click()
                page.locator("#mo-sheet").wait_for(state="visible")
                page.locator("[data-mo-target]").first.wait_for()
                own=str(item["user_id"])
                check(page.locator(f'[data-mo-target="{own}"]').count()==(1 if name=="doctor" else 0), f"{name}: own-seat target follows role rules")
                if name=="mafia":
                    check(page.locator(f'[data-mo-target="{item["users"][1]}"]').count()==0, "mafia teammate excluded from night targets")
                page.keyboard.press("Escape")
                check(not page.locator("#mo-sheet").is_visible(), f"{name}: Escape closes action sheet")
                page.emulate_media(reduced_motion="reduce")
                page.locator("#mo-action-open").click()
                button=page.locator("[data-mo-target]").first
                target=button.get_attribute("data-mo-target")
                button.click()
                page.wait_for_function("MO.data?.me.action!==null && MO.data?.me.action!==undefined")
                check(str(page.evaluate("MO.data.me.action.target"))==target, f"{name}: selected target accepted by server")
                page.locator('#mo-event[data-kind="choice"]').wait_for(state="visible")
                check(page.locator("#mo-event").evaluate("e=>e.getAnimations({subtree:true}).length")==0, f"{name}: reduced motion retains event text without animations")
                check(page.evaluate("document.activeElement.id")=="mo-action-open", f"{name}: game event does not steal move focus")
                page.locator('#mo-event button').click()
                check(not page.locator('#mo-event').is_visible(), f"{name}: event can be dismissed")
                page.reload()
                settled(page)
                check(not page.locator('#mo-event').is_visible(), f"{name}: reconnect does not replay an old event")
                check(str(page.evaluate("MO.data.me.action.target"))==target, f"{name}: target survives reconnect")
                if name=="mafia":
                    check(page.locator('#mo-council').is_visible(), "night council is directly available to the mafia")
                    check(page.locator('#mo-compose-label').inner_text()==page.locator('#mo-text').get_attribute('aria-label'), "private composer label matches its actual recipient")
                    page.get_by_role("button",name=re.compile(r"^Общий")).click()
                    settled(page)
                    page.evaluate("moLatest()")
                    read_id=page.evaluate("MO.read.table")
                    page.reload()
                    settled(page)
                    check(page.evaluate("MO.read.table")>=read_id, "read markers survive reconnect per room and user")
                    check(page.locator('#mo-channels button').filter(has_text="Общий").locator('.mo-unread').count()==0, "reconnect does not label already-read conversation as unread")
                    response=client.post(f"/mafia-online/rooms/{item['room_id']}/control",headers={"x-test-user":str(item['user_id'])},json={"command":"pause"})
                    check(response.status_code==200, "host pauses through actual API")
                    page.locator('#mo-event[data-kind="pause"]').wait_for(state="visible")
                    settled(page)
                    check(page.evaluate("MO.channel")=="table", "pause selects the available public conversation")
                    check(page.evaluate("(()=>{const c=document.getElementById('mo-chat');return c.scrollHeight-c.scrollTop-c.clientHeight<4})()"), "returning from private chat follows the latest public event")
                    page.get_by_role("button",name="Продолжить",exact=True).click()
                    settled(page)
                    page.locator('#mo-event[data-kind="resume"]').wait_for(state="visible")
                    check(page.evaluate("MO.channel")=="mafia", "resume restores the authorized night conversation")
                    check(not page.locator('#mo-toast').is_visible(), "automatic channel change does not duplicate the event with a generic toast")

            twenty=items["twenty"]
            page.goto(base+twenty["url"])
            settled(page)
            tab(page,"players")
            page.locator("#mo-player-search").fill("Длинное")
            check("Длинное" in page.locator("#mo-players-list").inner_text(), "player search finds a long name")
            check("Мартин" not in page.locator("#mo-players-list").inner_text(), "player search filters unrelated seats")
            page.evaluate("moRefresh()")
            settled(page)
            check(page.locator("#mo-player-search").input_value()=="Длинное", "poll retains player search")
            check(page.evaluate("document.activeElement.id")=="mo-player-search", "poll retains player-search keyboard focus")
            tab(page,"chat")
            page.locator("#mo-action-open").click()
            page.locator("#mo-target-search").fill("Длинное")
            check(page.locator('[data-mo-target]:not([data-mo-target="none"])').count()==1, "target search narrows 20-player choice")
            check("Длинное" in page.locator('[data-mo-target]:not([data-mo-target="none"])').inner_text(), "target search finds intended player")
            page.keyboard.press("Escape")
            context.close()
            browser.close()
            check(not errors, "no browser JavaScript exceptions: "+str(errors))
        result={"ok":True,"checks":checks,"count":len(checks),"geometry":geometry,"errors":errors,"sources":{name:hashlib.sha256((Path(__file__).resolve().parents[1]/"FastAPI/static"/name).read_bytes()).hexdigest() for name in ("app.55.js","app.56.js","mafia-online-v3.css")}}
        (out/("functional-report.json" if functional_only else "report.json")).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"PASS mafia audit UI: {len(checks)} checks; screenshots/report {out}")
    finally:
        server.should_exit=True
        worker.join(timeout=10)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--dsn",default=DSN)
    parser.add_argument("--out",type=Path,default=Path("output/playwright/mafia-online-audit"))
    parser.add_argument("--functional-only",action="store_true")
    args=parser.parse_args()
    run(args.dsn,args.out,args.functional_only)
