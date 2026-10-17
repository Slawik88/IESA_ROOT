"""Browser-side checks and the screen list of tools/ui_smoke.py (kept apart so the runner stays short).

Admin screens are deliberately absent: the admin panel is being rewritten in another session.
"""
from datetime import datetime, timedelta, timezone


def _days(n: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=n)).isoformat()


def _pass_screen(edit: str) -> str:
    """The pass page on the answer of the real stand, edited on the spot (the stand holds one scenario at a time): `me` is the answer, `s` is its current season. The page draws from `_sp.me`, so the edited copy is stored there."""
    return ("const real = _spLoad; window._spLoad = f => real.call(null, f).then(me => { me = JSON.parse(JSON.stringify(me)); const s = me.seasons[0]; "
            + edit + " _sp.me = me; return me; }); openSeasonPass()")


_PASS_ALL = "s.points = 9400; s.level = 30; s.points_to_next = 0; "

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
    # Тропа питомцев (флаг pets_v2): подэкраны и окна на питомцах стенда (tools/ui_stand.py, seed_trail). Ничего не меняют на сервере: награда рисуется из готового ответа
    ("trail-pet", "openPetsV1().then(() => { const p = _tr.me && (_tr.me.pets.find(q => q.calling) || _tr.me.pets[0]); if (p) trailPet(p.id); })"),
    ("trail-pet-busy", "openPetsV1().then(() => { const p = _tr.me && _tr.me.pets.find(q => q.run_id); if (p) trailPet(p.id); })"),
    ("trail-send", "openPetsV1().then(() => { if (_tr.me) trailSend(); })"),
    ("trail-send-expedition", "openPetsV1().then(() => { if (_tr.me) { trailSend(); trailSendSet('kind', 'expedition'); } })"),
    ("trail-decision", "openPetsV1().then(() => { const b = document.querySelector('[data-run=\"stand-run-exp\"]'); if (b) trailRun(b); })"),
    ("trail-result", "openPetsV1().then(() => { const a = _tr.me && _trAct('stand-run-exp'), p = a && _trPet(a.pet_id); if (p) _trResult(a, p, {ok: true, outcome: 'success', path: 'bold', chance: 48, reward_mult: 1.8, xp_credited: 188, daily_credited: 600, level_before: 9, level_after: 10, ceiling: 10, bond_days: 13, energy: 70, energy_loss: 0, finds: {mora: 14, diamond: 1, essence: 3, treat: 2, talisman: 1}, key: 1, stage_essence: 10}); })"),
    ("trail-build", "openPetsV1().then(() => { const p = _tr.me && _tr.me.pets.find(q => !q.run_id && q.calling); if (p) trailBuild(p.id); })"),
    ("trail-feed", "openPetsV1().then(() => { const p = _tr.me && _tr.me.pets.find(q => !q.run_id); if (p) trailFeed(p.id); })"),
    ("trail-camp", "openPetsV1().then(() => { if (_tr.me) trailGo('camp'); })"),
    ("trail-track", "openPetsV1().then(() => { if (_tr.me) trailGo('track'); })"),
    ("trail-trial", "openPetsV1().then(() => { if (_tr.me) trailGo('trial'); })"),
    ("inventory", "openInventory()"),
    ("promo", "openPromoSheet()"),
    ("achievements", "openAchievementsV1()"),
    ("help", "switchPage('help')"),
    ("store-zarniki", "openStoreV3('zarniki')"),
    ("store-vip", "openStoreV3('vip')"),
    ("exchange", "openPlayerExchangeV1()"),
    ("news", "openWhatsNew()"),
    # «Что нового» в трёх состояниях. «Прочитано» задаётся до открытия: страница читает его в момент захода, а потом отмечает всё прочитанным
    ("news-first", "if (_profileData) _profileData.whatsnew_seen_id = ''; try { localStorage.removeItem('wn_seen_id'); } catch (e) {} openWhatsNew()"),
    ("news-new", "_wnFetch().then(l => { if (_profileData) _profileData.whatsnew_seen_id = (l[6] || l[l.length - 1]).id; openWhatsNew(); })"),
    ("news-open", "_wnFetch().then(l => { if (_profileData) _profileData.whatsnew_seen_id = (l[3] || l[l.length - 1]).id; openWhatsNew(); setTimeout(() => { const b = document.querySelector('#pg-news .wn-it--fresh [data-wn-toggle]'); if (b) b.click(); }, 900); })"),
    # Пропуск сезона (флаг season_pass_v1). Первый экран идёт по настоящему ответу стенда (три уровня к получению), остальные правят этот ответ на месте
    ("pass", "openSeasonPass()"),
    ("pass-new", _pass_screen("me.account = {eligible: false, eligible_from: '" + _days(9) + "', min_days: 14};")),
    ("pass-idle", _pass_screen("s.claimed_level = s.level; s.claimable_levels = 0; s.claimable = {mora: 0, essence: 0}; s.points_today = s.points_today_cap;")),
    ("pass-finish", _pass_screen(_PASS_ALL + "s.claimed_level = 24; s.claimable_levels = 6; s.claimable = {mora: 240, essence: 60};")),
    ("pass-max", _pass_screen(_PASS_ALL + "s.claimed_level = 30; s.claimable_levels = 0; s.claimable = {mora: 0, essence: 0};")),
    ("pass-prev", _pass_screen("const old = JSON.parse(JSON.stringify(s)); Object.assign(old, {current: false, season: 1, level: 11, points: 3410, points_to_next: 190, claimed_level: 4, claimable_levels: 7, "
                               "claimable: {mora: 280, essence: 70}, ends_at: '" + _days(-10) + "', claim_until: '" + _days(20) + "', points_today: 0}); "
                               "Object.assign(s, {season: 2, starts_at: '" + _days(-10) + "', ends_at: '" + _days(200) + "', points: 640, level: 2, points_to_next: 260, claimed_level: 2, claimable_levels: 0, claimable: {mora: 0, essence: 0}}); "
                               "me.seasons = [old, s];")),
    ("pass-refused", "openSeasonPass(); setTimeout(() => _spShowError(1, 'Нет новых уровней для получения.'), 1200)"),
    ("pass-closed", "window._spLoad = () => { _sp.me = {enabled: false}; _sp.at = Date.now(); return Promise.resolve(_sp.me); }; openSeasonPass()"),
    ("pass-error", "window._spLoad = () => Promise.reject('Сервер прилёг отдохнуть. Попробуй через минуту.'); openSeasonPass()"),
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
DOCK_TABS = ("profile", "arena", "pets", "questlog", "looks", "chests", "more")

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
BLOCKS = """() => { const out = []; const allow = /(^|\\s)(nav|nb|v3-bar|v3-bar-me|v3-bell|v3-chip|toast|tv-|tg-|sheet|lk-sheet|cf-sheet|mclose|ap-|lk-mini|lk-hero|v3-fx|sv-ava|sv-radio|v3-ring|v3-ava|tr-ic|cn-|mk-tile|lk-pring|lk-rank-ring|pl-|v3-burst|v3-fly|sg-|st-seg|v3-scope|tos-gate)/;
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
SKIP_CLICK = r"подтверд|удалить|отправить|принять и|выйти|сбросить|оплат|продолжить и|да, |забрать|выбрать (осторожный|ровный|рискованный)|улучшить|перековать|сдать|дать|начать|сохранить сборку|открыть за одно очко"

# Visible controls of the current screen as [index among all candidates, label], skipping dangerous ones.
CANDIDATES = """(skip) => { const re = new RegExp(skip, 'i'); const out = [];
  [...document.querySelectorAll('button, summary, [onclick], a[href]')].forEach((e, i) => { const r = e.getBoundingClientRect(); if (!r.width || !r.height || r.top > innerHeight * 2 || r.bottom < 0) return;
    if (e.closest('.nav, [hidden]') || getComputedStyle(e).visibility === 'hidden' || e.disabled) return;
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
  const gpu = new Set(['offset', 'computedOffset', 'easing', 'composite', 'transform', 'opacity', 'filter', 'translate', 'rotate', 'scale']);   // what the compositor can animate by itself
  let main = 0;
  run.forEach(a => { try { if (a.effect.getKeyframes().some(k => Object.keys(k).some(p => !gpu.has(p)))) main++; } catch (e) {} });
  res({anims: run.length, main, lite: document.body.classList.contains('ap-lite')}); }, 2500))"""
# Budget of a look at SSS in the full mode (`--perf --device high`; measured with the scenes, ~60-75 animated layers, with headroom): beyond this the page jitters in the Telegram WebView.
# Everything animated is transform / opacity on the compositor; frames stay at 16.7 ms under a 4x slowed CPU. A mid phone (`--device mid`, .ap-lite) runs about two thirds of it.
# `passes`, `area` and `bmf` come from Chromium's own compositor (ui_smoke.compositor_cost), the numbers that decide how a phone copes and that fps on a desktop never shows:
# render passes per drawn frame (a mask or filter on a box that holds moving things, and every polygon clip-path, is an offscreen surface; 34 clipped sparks were 34 of them),
# the summed area of the composited layers in screens (memory x DPR squared) and main-thread frames a second (`ProxyMain::BeginMainFrame`: each one restyles EVERY running animation, so one animation
# that cannot run on the compositor, like the old background glint, lifted it from the healthy 11 to 55-60 and made all the others dearer). `main` counts running animations that animate anything but
# transform / opacity / filter. Counting masked or filtered animated elements, as this budget once did, says nothing about any of them.
BUDGET = {"anims": 95, "main": 0, "passes": 14, "area": 24, "bmf": 24}
