"""Browser-side checks and the screen list of tools/ui_smoke.py (kept apart so the runner stays short).

Admin screens are deliberately absent: the admin panel is being rewritten in another session.
"""

# Every player screen and sheet reachable from the app. (name, JS that opens it)
SCREENS = [
    ("profile", "switchPage('profile')"),
    ("arena", "switchPage('arena')"),
    ("looks", "openLooksModal()"),
    ("looks-album", "openLooksModal();setTimeout(()=>{ if (typeof lkView==='function') lkView('album'); },500)"),
    ("questlog", "openQuestsV1()"),
    ("top", "openTopV3()"),
    ("more", "switchPage('more')"),
    ("settings", "openSettingsModal()"),
    ("chests", "openChestsV1()"),
    ("pets", "openPetsV1()"),
    ("achievements", "openAchievementsV1()"),
    ("help", "switchPage('help')"),
    ("store-zarniki", "openStoreV3('zarniki')"),
    ("store-vip", "openStoreV3('vip')"),
    ("exchange", "openPlayerExchangeV1()"),
    ("news", "openWhatsNew()"),
    ("tracker", "openChatTracker()"),
    ("wallet", "showCurrModal()"),
    ("legal-tos", "openLegalDoc('tos')"),
    ("legal-privacy", "openLegalDoc('privacy')"),
    ("marks", "v3MarksOpenOwn()"),
    ("mafia", "openMafiaStats()"),
    ("gifts", "openPartnerGifts()"),
    ("confirm", "v3Confirm({title:'Покупка', name:'Образ', sub:'Описание', price:300, icon:'✨', have:1200, cta:'Купить'})"),
    ("gift-toast", "v3GiftToast([{label:'VIP', amount:7, unit:'дн.', kind:'vip', glyph:'👑'}], ()=>{})"),
    ("toast", "toast('Готово, всё сохранено')"),
    ("welcome", "_showWelcome()"),
    ("tos-gate", "_tosGate({tos_accepted:false})"),
    ("public", "openPublicCardV3(PEER_ID)"),
]

# Standalone pages outside the single-page app (no dock): the two games and the public legal pages.
PAGES = ("/rhythm-v2", "/minesweeper", "/legal/tos", "/legal/privacy")

# Bottom dock tabs (the bug the owner saw: the dock flew below the screen when switching tabs)
DOCK_TABS = ("arena", "looks", "questlog", "top", "more", "profile")

# Response statuses that are the designed answer of the stand, not bugs: closed exchange.
EXPECTED_HTTP = [
    ("/player-exchange/v1/", 404),
]
# Known open product question (reported to the owner, not a bug of the stand): the /vip router is deliberately not registered (tools/test_release_public_routes.py
# lists /vip as retired), while the Zarniki/VIP page still asks it. Shown as a warning so that it does not hide new findings.
KNOWN_OPEN = [("/vip/", 404)]
# Console noise of the sandbox itself (no internet: web fonts, telegram-web-app.js) and of the cookie-login persona (no socket token).
EXPECTED_CONSOLE = ("ERR_TUNNEL_CONNECTION_FAILED", "ERR_NAME_NOT_RESOLVED", "Failed to load resource", "WebSocket connection")

# Viewport honesty and dock position. `expected` is the emulated device width.
GEOMETRY = """(expected) => {
  const n = document.querySelector('.nav'); const r = n ? n.getBoundingClientRect() : null; const out = [];
  if (innerWidth !== expected) out.push('layout viewport widened: ' + innerWidth + ' instead of ' + expected);
  if (document.documentElement.scrollWidth > expected + 1) out.push('horizontal overflow: scrollWidth ' + document.documentElement.scrollWidth);
  if (scrollX !== 0) out.push('page scrolled sideways: ' + scrollX);
  if (!n) out.push('no dock'); else {
    if (getComputedStyle(n).position !== 'fixed') out.push('dock is not fixed');
    if (r.bottom > innerHeight + 1) out.push('dock below the screen: bottom ' + Math.round(r.bottom) + ' of ' + innerHeight);
    if (r.left < -1 || r.right > expected + 1) out.push('dock past the side: ' + Math.round(r.left) + '..' + Math.round(r.right));
  }
  return out; }"""

# Dock position every frame for `ms` after a tab switch.
DOCK_SAMPLE = """(ms) => new Promise(res => { const n = document.querySelector('.nav'); const out = []; const t0 = performance.now();
  const tick = () => { const r = n.getBoundingClientRect(); out.push([Math.round(r.bottom), Math.round(r.left), innerWidth, innerHeight]);
    if (performance.now() - t0 < ms) requestAnimationFrame(tick); else res(out); }; tick(); })"""

# Controls smaller than a thumb. The hit zone counts: the house style extends small controls with an ::after box. Inline text links are exempt.
TAP = """() => { const out = []; document.querySelectorAll('button, a[href], input:not([type=hidden]), select, summary, [role=button], [onclick]').forEach(e => {
    const r = e.getBoundingClientRect(); if (!r.width || !r.height || r.bottom < 0 || r.top > innerHeight * 3) return;
    const cs = getComputedStyle(e); if (cs.visibility === 'hidden' || cs.pointerEvents === 'none' || e.disabled) return;
    if (e.closest('[hidden], [aria-hidden=true], .ap-orn, .v3-fx')) return;
    if (e.tagName === 'A' && cs.display === 'inline') return;
    const pz = getComputedStyle(e, '::after'); const ext = pz.position === 'absolute' && pz.content !== 'none' ? [parseFloat(pz.width) || 0, parseFloat(pz.height) || 0] : [0, 0];
    if (Math.min(Math.max(r.width, ext[0]), Math.max(r.height, ext[1])) < 32) out.push(e.tagName.toLowerCase() + '.' + String(e.className).trim().split(/\\s+/).slice(0, 2).join('.') + ' ' + Math.round(r.width) + 'x' + Math.round(r.height)); });
  return out.slice(0, 40); }"""

# Cards around every element (the old template look) and browser-default grey buttons (a control that lost its style).
BLOCKS = """() => { const out = []; const allow = /(^|\\s)(nav|nb|v3-bar|v3-bar-me|v3-bell|v3-chip|toast|tv-|tg-|sheet|lk-sheet|cf-sheet|mclose|ap-|lk-mini|lk-hero|v3-fx|sv-ava|sv-radio|v3-ring|v3-ava|cn-|mk-tile|lk-pring|lk-rank-ring|pl-|v3-burst|v3-fly|sg-|st-seg|v3-scope|tos-gate)/;
  document.querySelectorAll('body *').forEach(e => { const r = e.getBoundingClientRect(); if (r.width < 56 || r.height < 28 || r.bottom < 0) return;
    const tag = e.tagName.toLowerCase(); if (/^(button|input|select|textarea|svg|path|img|canvas|summary|label|option|a)$/.test(tag)) return;
    const cls = typeof e.className === 'string' ? e.className : ''; if (allow.test(cls) || e.closest('.nav,#v3-bar,.sheet,.lk-sheet,.cf-sheet,#toast,.toast,dialog,.lk-reveal,#preloader,.v3-fx')) return;
    const cs = getComputedStyle(e); const rad = parseFloat(cs.borderTopLeftRadius) || 0; if (rad < 10 && !(r.width >= 240 && r.height >= 56)) return;   // a big flat slab is a block too, radius or not
    const bg = cs.backgroundColor.match(/rgba?\\(([^)]+)\\)/); const alpha = bg ? (bg[1].split(',').length > 3 ? parseFloat(bg[1].split(',')[3]) : 1) : 0;
    const img = cs.backgroundImage !== 'none'; const bw = parseFloat(cs.borderTopWidth) || 0; const shadow = cs.boxShadow !== 'none';
    if ((alpha >= .03 || img) && (bw > 0 || shadow || alpha >= .06)) out.push('BLOCK ' + tag + (cls ? '.' + cls.trim().split(/\\s+/).slice(0, 3).join('.') : '') + ' ' + Math.round(r.width) + 'x' + Math.round(r.height)); });
  const probe = document.createElement('button'); probe.style.all = 'revert'; probe.style.position = 'fixed'; document.body.appendChild(probe);
  const ua = getComputedStyle(probe).backgroundColor; probe.remove();     // what this browser paints on a button nobody styled (light and dark differ)
  document.querySelectorAll('button, input[type=button], input[type=submit], select').forEach(e => { const r = e.getBoundingClientRect(); if (!r.width || !r.height) return; const cs = getComputedStyle(e);
    if (cs.backgroundColor === ua && cs.backgroundImage === 'none' && cs.appearance !== 'none') out.push('UA-DEFAULT ' + e.tagName.toLowerCase() + '.' + String(e.className).trim().split(/\\s+/).slice(0, 3).join('.') + ' ' + Math.round(r.width) + 'x' + Math.round(r.height)); });
  return out.slice(0, 60); }"""

# Labels of controls the crawler never presses: they spend, delete or leave the account in another state.
SKIP_CLICK = r"подтверд|удалить|отправить|принять и|выйти|сбросить|оплат|продолжить и|да, "

# Visible controls of the current screen as [index among all candidates, label], skipping dangerous ones.
CANDIDATES = """(skip) => { const re = new RegExp(skip, 'i'); const out = [];
  [...document.querySelectorAll('button, summary, [onclick], a[href]')].forEach((e, i) => { const r = e.getBoundingClientRect(); if (!r.width || !r.height || r.top > innerHeight * 2 || r.bottom < 0) return;
    if (e.closest('.nav, [hidden], .development-notice') || getComputedStyle(e).visibility === 'hidden' || e.disabled) return;
    const label = (e.getAttribute('aria-label') || e.textContent || e.className || '').trim().replace(/\\s+/g, ' ');
    if (re.test(label) || !label) return; out.push([i, label]); });
  return out; }"""

# Press the control found at `index` by CANDIDATES, but only when it still has the same label (a list that loads late shifts the order). Returns whether it pressed.
PRESS = """([i, label]) => { const norm = e => (e.getAttribute('aria-label') || e.textContent || e.className || '').trim().replace(/\\s+/g, ' ');
  const all = [...document.querySelectorAll('button, summary, [onclick], a[href]')]; let e = all[i]; if (!e || norm(e) !== label) e = all.find(x => norm(x) === label);
  if (!e) return false; e.click(); return true; }"""

# Frame intervals (ms) of requestAnimationFrame for `ms` milliseconds.
FRAMES = """(ms) => new Promise(res => { const out = []; let last = performance.now(); const t0 = last;
  const tick = now => { out.push(now - last); last = now; if (now - t0 < ms) requestAnimationFrame(tick); else res(out.slice(3)); }; requestAnimationFrame(tick); })"""

# What keeps moving on the screen after it settled: the budget of a look. Elements of a toast are not counted (a toast leaves by itself).
MOTION = """() => new Promise(res => setTimeout(() => {
  const run = document.getAnimations().filter(a => a.playState === 'running' && a.effect && a.effect.target && !a.effect.target.closest('.toast, .v3-toast'));
  const chainFilter = t => { for (let n = t; n && n !== document.body; n = n.parentElement) if (getComputedStyle(n).filter !== 'none') return true; return false; };
  let filter = 0, masked = 0, glint = 0;
  run.forEach(a => { const t = a.effect.target, cs = getComputedStyle(t); if (chainFilter(t)) filter++; if (cs.maskImage !== 'none' || cs.webkitMaskImage !== 'none') masked++;
    try { if (a.effect.getKeyframes().some(k => 'backgroundPositionX' in k)) glint++; } catch (e) {} });
  res({anims: run.length, filter, masked, glint, lite: document.body.classList.contains('ap-lite')}); }, 2500))"""
# Budget of a look at SSS in the full mode (measured after the 2026-10 optimization, with headroom): beyond this the page jitters in the Telegram WebView.
BUDGET = {"anims": 45, "filter": 14, "masked": 20, "glint": 1}
