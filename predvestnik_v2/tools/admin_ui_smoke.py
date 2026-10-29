"""Админка на фикстурах: 8 экранов × 3 ширины × 8 образов, строгая тема и отказы листов.

Запуск через ui_smoke.py --only admin-search,admin-player,admin-reports,admin-journal,admin-broadcast,admin-access.
Не использует Telegram, прод или базу. Новый экран добавляется в ADMIN_SCREENS и OPENERS.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import urlparse

import admin_stand
from admin_stand_fixtures import ROUTES, PURGE_VIEW, CHAT
from core.skins_v3_catalog import SKINS

from ui_smoke_checks import ADMIN_SCREENS
LOOKS = ("forest", "dune", "frost", "hanami", "void", "aurora", "solar", "crimson_dark")
OPENERS = {"admin-purge": f"purgeView(document.querySelector('#main'), {CHAT['id']}, 'Тестовый чат')","admin-search": "open('people')", "admin-player": "playerView(document.querySelector('#main'), 5000)",
           **{f"admin-{tab}": f"open('{tab}')" for tab in ("reports", "journal", "broadcast", "access", "metrics")}}
PROBE = """() => {
  const fails = [], w = innerWidth;
  const native = document.createElement('button'); document.body.append(native);
  const nativeBg = getComputedStyle(native).backgroundColor; native.remove();
  const visible = n => n.getClientRects().length && !n.closest('[hidden],details:not([open]) > :not(summary)');
  const scrollParent = n => { for (let p=n.parentElement;p && p!==document.body;p=p.parentElement) {
    if (['auto','scroll'].includes(getComputedStyle(p).overflowX) && p.scrollWidth>p.clientWidth) return p;
  } return null; };
  for (const n of document.querySelectorAll('main *, .top *, .nav *, .sheet *')) {
    if (!visible(n)) continue;
    const r=n.getBoundingClientRect(), css=getComputedStyle(n), scroll=scrollParent(n);
    if (r.width && !scroll && (r.left < -1 || r.right > w+1)) fails.push('overflow '+n.tagName+'.'+n.className);
    const interactive=n.matches('button,a[href],input,select,textarea,summary,[onclick],[role=button]') || (typeof n.onclick==='function' && !n.matches('div,section,main,nav'));
    if (n.matches('button') && !n.disabled && css.backgroundColor === nativeBg) fails.push('native button '+n.className);
    if (interactive && !n.disabled && (r.width <43.5 || r.height <43.5)) fails.push('target '+n.tagName+'.'+n.className+' '+Math.round(r.width)+'x'+Math.round(r.height));
    if (n.matches('input,select,textarea') && parseFloat(css.fontSize)<16) fails.push('font '+n.tagName+' '+css.fontSize);
  }
  const css=getComputedStyle(document.body), c=k=>css.getPropertyValue(k).trim();
  for (const bg of ['--v3-bg','--v3-sheet']) {
    if (adminContrast(c('--v3-dim'),c(bg))<5.2) fails.push('contrast dim '+bg);
    if (adminContrast(c('--v3-ink'),c(bg))<4.5) fails.push('contrast ink '+bg);
  }
  if (document.documentElement.scrollWidth>w) fails.push('wide document');
  return [...new Set(fails)];
}"""


def run_admin_smoke(widths, only=None, shots=None):
    from playwright.sync_api import sync_playwright

    selected = [name for name in ADMIN_SCREENS if not only or name in only]
    if not selected:
        raise ValueError("Не выбран ни один сценарий админки")
    results = {}
    html = admin_stand.read("index.html").replace("{{BASE}}", admin_stand.HOST).replace("{{VER}}", "stand")
    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
    fallbacks = set()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for skin in LOOKS:
            fixture = copy.deepcopy(ROUTES)
            data = SKINS[skin]
            look = {"id": skin, "tier": "SSS", "tokens": data["tokens"], "pal": list(data["pal"]), "kinds": data["kinds"]}
            fixture["/me"]["look"] = look
            fixture["/player/5000"]["look"] = look

            def handle(route):
                url = urlparse(route.request.url)
                if url.netloc != "stand.local":
                    return route.abort()
                if url.path.startswith("/bot-admin/api/"):
                    key = url.path[len("/bot-admin/api"):]
                    status, body = fixture.get(key, (404, {"detail": "нет фикстуры"})), None
                    if isinstance(status, tuple):
                        status, body = status
                    else:
                        status, body = 200, status
                    return route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
                if url.path.startswith("/purge-v1/chats/"):
                    return route.fulfill(content_type="application/json", body=json.dumps(PURGE_VIEW))
                name = url.path.rsplit("/", 1)[-1]
                if (name.startswith("admin") or name in admin_stand.SHARED) and name.endswith((".js", ".css")):
                    return route.fulfill(content_type="text/javascript" if name.endswith(".js") else "text/css", body=admin_stand.read(name))
                if name.endswith(".json"):
                    return route.fulfill(content_type="application/json", body=admin_stand.read(name))
                return route.fulfill(content_type="text/html", body=html)

            for width in widths:
                ctx = browser.new_context(viewport={"width": width, "height": 740}, has_touch=True, is_mobile=True, reduced_motion="reduce")
                ctx.add_init_script("""window._backHandlers = new Set(); window.Telegram={WebApp:{
                  initData:'',ready(){},expand(){},disableVerticalSwipes(){},
                  BackButton:{show(){},onClick(f){_backHandlers.add(f)},offClick(f){_backHandlers.delete(f)}}
                }};""")
                ctx.route("**/*", handle)
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(admin_stand.HOST + "/bot-admin/")
                page.wait_for_selector("#tabs [data-tab]")
                if page.evaluate("adminThemeFallback"):
                    fallbacks.add(skin)
                for name in selected:
                    page.evaluate(OPENERS[name])
                    page.wait_for_function("() => !document.querySelector('.admin-load')")
                    page.wait_for_timeout(60)
                    fails = page.evaluate(PROBE) + errors
                    errors.clear()
                    if name == "admin-player":
                        if page.locator(".stats.balances").bounding_box()["y"] + page.locator(".stats.balances").bounding_box()["height"] > 666:
                            fails.append("балансы не помещаются над меню")
                        # Фото всем; оформление только VIP. Используем общий рендер рамки Mini App.
                        assert page.locator(".profile-head .ap-frame").count() == 1
                        assert "ap-frame" not in page.evaluate("ava({name:'Обычный',avatar:'/photo',look:ME.look})")
                    if shots and width in (320, 390) and skin in ("forest", "solar"):
                        page.screenshot(path=str(Path(shots) / f"{name}-{skin}-{width}.png"), full_page=True)
                    if shots and name == 'admin-player' and width == 390:
                        page.screenshot(path=str(Path(shots) / f"theme-{skin}.png"))
                    results[f"{name}/{skin}/{width}"] = (fails, [])
                results[f"admin-sheets/{skin}/{width}"] = (sheet_checks(page, look) + errors, [])
                ctx.close()
        browser.close()
    print("Тема автоматически заменена строгой: " + (", ".join(sorted(fallbacks)) or "нет"))
    return results


def sheet_checks(page, look):
    fails = []
    # Ответ старого окна не закрывает новое; ошибка после закрытия не ищет исчезнувшую кнопку.
    page.evaluate("""() => {
      window.doneA=null; sheet('A','<input id="old-field"/>','Отправить',()=>new Promise(resolve=>{doneA=resolve}));
      document.querySelector('#sok').click(); adminCloseSheet(); sheet('B','<input id="new-field"/>','Готово',()=>{});
      doneA();
    }""")
    page.wait_for_timeout(30)
    if page.locator("#new-field").count() != 1:
        fails.append("старый ответ закрыл новое окно")
    fails += page.evaluate(PROBE)
    page.evaluate("[..._backHandlers].forEach(f=>f())")
    if not page.locator("#sheet").evaluate("n=>n.hidden"):
        fails.append("Назад не закрыл лист")
    page.evaluate("""() => {
      sheet('A','','Отправить',()=>new Promise((_,reject)=>{window.failA=reject}));
      document.querySelector('#sok').click(); adminCloseSheet(); failA(new Error('Нет связи'));
    }""")
    page.wait_for_timeout(30)
    # Клавиатура уменьшает visualViewport, поле и подтверждение остаются в видимой области.
    page.evaluate("""() => {
      sheet('Клавиатура','<textarea id="keyboard-field"></textarea>','Готово',()=>{});
      Object.defineProperty(visualViewport,'height',{value:400,configurable:true});
      visualViewport.dispatchEvent(new Event('resize'));
    }""")
    page.wait_for_timeout(120)
    if page.locator('#sok').bounding_box()['y'] + page.locator('#sok').bounding_box()['height'] > 401:
        fails.append('клавиатура перекрыла подтверждение')
    page.evaluate("delete visualViewport.height; visualViewport.dispatchEvent(new Event('resize'))")
    grip = page.locator('.sheet-grip').bounding_box()
    page.mouse.move(grip['x'] + 40, grip['y'] + 10)
    page.mouse.down()
    page.mouse.move(grip['x'] + 40, grip['y'] + 100, steps=6)
    page.mouse.up()
    if not page.locator('#sheet').evaluate('n=>n.hidden'):
        fails.append('свайп не закрыл лист')
    # Контрастный отказ, испорченные токены, возврат к образу и полная очистка старых токенов.
    page.evaluate("PREFS.set('admin.look','strict'); applyTheme()")
    strict = page.evaluate("getComputedStyle(document.body).getPropertyValue('--v3-bg')")
    page.evaluate("ME.look={tokens:{'--v3-bg':'#ffffff','--v3-dim':'#ffffff','--v3-ink':'#ffffff','--v3-acc':'url(https://bad.local)'}}; PREFS.set('admin.look','own'); applyTheme()")
    if not page.evaluate("adminThemeFallback") or page.evaluate("getComputedStyle(document.body).getPropertyValue('--v3-bg')") != strict:
        fails.append("небезопасная тема не откатилась")
    page.evaluate("look=>{ME.look=look;applyTheme()}", look)
    page.evaluate("themeSheet()")
    page.locator('[data-look="strict"]').click()
    page.locator('[data-look="own"]').click()
    page.keyboard.press("Escape")
    return fails
