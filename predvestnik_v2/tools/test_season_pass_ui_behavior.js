// Behaviour of the season pass screen (FastAPI/static/app.43.js): the real script runs in a vm with a stub page and a stub server. Started by tools/test_season_pass_ui_contract.py, or alone: node tools/test_season_pass_ui_behavior.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const STATIC = path.join(__dirname, '..', 'FastAPI', 'static');
const SOURCE = fs.readFileSync(path.join(STATIC, 'app.43.js'), 'utf8');
const ESCAPER = /^function _profileEsc\(.*$/m.exec(fs.readFileSync(path.join(STATIC, 'app.02.js'), 'utf8'));
assert.ok(ESCAPER, 'app.02.js defines _profileEsc, app.43.js escapes every server string through it');
const NOW = Date.UTC(2026, 9, 13, 12, 0, 0);   // 13 октября 2026, полдень по UTC: идёт сезон 1 (с 11 октября 2026 до 11 мая 2027)
class FixedDate extends Date {
  constructor(...a) { if (a.length) super(...a); else super(NOW); }
  static now() { return NOW; }
}
const plain = x => JSON.parse(JSON.stringify(x));   // результат vm живёт в другом мире объектов: сравниваем через JSON
const flat = s => String(s).replace(/[\u00a0\u202f]/g, ' ');   // числа по-русски разделены неразрывным пробелом
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const settle = async () => { for (let i = 0; i < 8; i++) await tick(); };
const count = (html, needle) => html.split(needle).length - 1;
let sections = 0;
const section = async (name, fn) => { try { await fn(); sections++; } catch (err) { err.message = `[${name}] ${err.message}`; throw err; } };

// Ответ сервера (docs/SEASON_PASS_UI.md): текущий сезон, три уровня к получению
const season = (o = {}) => Object.assign({
  season: 1, starts_at: '2026-10-11T00:00:00+00:00', ends_at: '2027-05-11T00:00:00+00:00', claim_until: '2027-06-10T00:00:00+00:00',
  points: 1820, level: 6, levels: 30, points_per_level: 300, points_to_next: 280, claimed_level: 3, claimable_levels: 3, claimable: { mora: 120, essence: 30 },
  per_level: { mora: 40, essence: 10 }, full_track: { mora: 1200, essence: 300 }, points_per_game: 10, points_today: 40, points_today_cap: 100, current: true,
}, o);
const answer = (o = {}, ...seasons) => Object.assign({ enabled: true, account: { eligible: true, eligible_from: '2026-09-01T00:00:00+00:00', min_days: 14 }, seasons: seasons.length ? seasons : [season()] }, o);
const DONE = { claimed_level: 6, claimable_levels: 0, claimable: { mora: 0, essence: 0 } };   // те же три уровня, уже полученные

// Страница-заглушка: страница пропуска, строка в хабе, вкладка «Игры», кнопки и строки ошибок получения, журнал запросов к серверу
function boot(extra = {}) {
  const log = [], gifts = [], toasts = [], calls = [], net = { me: answer(), meFail: null, claim: null, requests: [] };
  const page = { _html: '', get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); log.push('render'); } };
  const tab = { dataset: {}, notes: 0, insertAdjacentHTML() { this.notes++; }, querySelector(sel) { return sel === '.sp-sr' && this.notes ? { remove: () => { this.notes = 0; } } : null; } };
  const buttons = {}, errors = {};
  const hub = { html: '', small: '', list: null };
  hub.list = { insertAdjacentHTML: (pos, html) => { assert.equal(pos, 'beforeend'); hub.html = html; log.push('hub-insert'); } };
  const host = {
    querySelector: sel => sel === '.v3-games--hub' ? hub.list
      : sel === '.sp-hub' ? (hub.html ? { set outerHTML(v) { hub.html = v; log.push('hub-replace'); }, remove() { hub.html = ''; log.push('hub-remove'); } } : null)
      : sel === '.sp-hub small' ? (hub.html ? { set textContent(v) { hub.small = v; } } : null) : null,
  };
  const els = { 'pg-pass': page, 'game-hub': host };
  const ctx = vm.createContext(Object.assign({
    document: {
      querySelector: sel => {
        if (sel === '.nb[data-page="arena"]') return tab;
        let m = /^\.sp-claim\[data-season="(\d+)"\] button$/.exec(sel);
        if (m) return buttons[m[1]] || (buttons[m[1]] = { disabled: false });
        m = /^\.sp-claim\[data-season="(\d+)"\] \.sp-err$/.exec(sel);
        if (m && (net.noErrorLine !== true)) return errors[m[1]] || (errors[m[1]] = { _t: '', hidden: true, get textContent() { return this._t; }, set textContent(v) { this._t = v; log.push('error:' + v); } });
        return null;
      },
    },
    console, Date: FixedDate, Math, JSON, Object, Array, Set, Promise, RegExp, String, Number,
    _sysFlags: { season_pass_v1: true }, _navStack: [], _loaded: new Set(),
    el: id => els[id] || null, v3EnterSync() {}, v3GlintMark: t => `<span class="ap-gl" data-t="${t}"></span>`, _haptic: kind => log.push('haptic:' + kind),
    fmt: n => Number(n).toLocaleString('ru'),
    switchPage: p => { calls.push(['switchPage', p]); if (!ctx._loaded.has(p)) { ctx._loaded.add(p); if (p === 'pass') ctx.loadSeasonPass(); } },   // как в app.01.js: страница помечается загруженной до вызова загрузчика
    navBack: () => calls.push(['navBack']),
    toast: (msg, ok) => toasts.push([msg, ok]), v3GiftToast: payloads => gifts.push(plain(payloads)),
    api: (route, opts = {}) => {
      net.requests.push(opts.method ? `${opts.method} ${route} ${opts.body}` : `GET ${route}`);
      if (route === '/season-pass/me') return net.meFail ? Promise.reject(net.meFail) : Promise.resolve(plain(net.me));
      if (route === '/season-pass/claim') return net.claim();
      return Promise.reject('unexpected route ' + route);
    },
  }, extra));
  vm.runInContext(ESCAPER[0], ctx);
  vm.runInContext(SOURCE + `
;globalThis.__sp = { _spWord, _spLevels, _spPoints, _spDate, _spGain, _spSeasons, _spReady, _spCanClaim, _spLoad, _spDock, _spDockSync, _spHubHtml, _spRender, _spRepaint,
  _spClaimBlock, _spTrack, _spHow, _spShowError, _spCelebrate, passCheck, passHubRow, openSeasonPass, loadSeasonPass, spBack, spClaim, get state() { return _sp; } };`, ctx);
  return { ctx, sp: ctx.__sp, page, tab, hub, host, buttons, errors, log, gifts, toasts, calls, net, els };
}
const render = (t, me) => { t.net.me = me; t.sp.state.me = plain(me); t.sp._spRender(); return flat(t.page.innerHTML); };
const text = html => flat(html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ')).trim();

(async () => {
  await section('Слова и числа: склонения, награда строкой, даты по UTC', () => {
    const { sp } = boot();
    for (const [n, word] of [[0, 'уровней'], [1, 'уровень'], [2, 'уровня'], [4, 'уровня'], [5, 'уровней'], [11, 'уровней'], [14, 'уровней'], [21, 'уровень'], [22, 'уровня'], [100, 'уровней'], [111, 'уровней'], [112, 'уровней']]) {
      assert.equal(flat(sp._spLevels(n)), `${n} ${word}`);
    }
    assert.equal(flat(sp._spPoints(1)), '1 очко');
    assert.equal(flat(sp._spPoints(3)), '3 очка');
    assert.equal(flat(sp._spPoints(280)), '280 очков');
    assert.equal(flat(sp._spPoints(1820)), '1 820 очков');
    assert.equal(flat(sp._spGain({ mora: 120, essence: 30 })), '120 🪙 Моры и 30 💧 Эссенции');
    assert.equal(flat(sp._spGain({ mora: 40, essence: 0 })), '40 🪙 Моры');
    assert.equal(flat(sp._spGain({ mora: 0, essence: 10 })), '10 💧 Эссенции');
    assert.equal(flat(sp._spGain({ mora: 1200, essence: 300 })), '1 200 🪙 Моры и 300 💧 Эссенции');
    for (const empty of [null, undefined, {}, { mora: 0, essence: 0 }, { mora: '<b>', essence: -5 }]) assert.equal(sp._spGain(empty), '', 'нулевая награда не пишется');
    assert.equal(sp._spDate('2027-05-11T00:00:00+00:00'), '11 мая 2027', 'чужой год пишется');
    assert.equal(sp._spDate('2026-11-02T00:00:00+00:00'), '2 ноября', 'нынешний год не пишется');
    assert.equal(sp._spDate('2026-12-31T23:30:00-05:00'), '1 января 2027', 'день считается по UTC, как у сервера');
    for (const bad of ['не дата', '', null, undefined, '<img src=x>']) assert.equal(sp._spDate(bad), '', 'битая дата даёт пустую строку, а не разметку');
  });

  await section('Разбор ответа: сезоны, что можно забрать', () => {
    const { sp } = boot();
    const prev = season({ season: 1, current: false, claimable_levels: 7 }), cur = season({ season: 2 });
    assert.deepEqual(plain(sp._spSeasons(answer({}, prev, cur))), { cur: plain(cur), prev: plain(prev) });
    assert.deepEqual(plain(sp._spSeasons(answer())), { cur: plain(season()), prev: null });
    assert.deepEqual(plain(sp._spSeasons(null)), { cur: null, prev: null });
    assert.deepEqual(plain(sp._spSeasons({ enabled: false })), { cur: null, prev: null });
    assert.equal(sp._spReady(answer()), 3);
    assert.equal(sp._spReady(answer({}, prev, cur)), 7 + 3, 'по всем сезонам');
    assert.equal(sp._spReady({ enabled: false }), 0);
    assert.equal(sp._spReady(null), 0);
    assert.equal(sp._spReady(answer({}, season({ claimable_levels: 'мусор' }))), 0, 'мусор вместо числа не считается наградой');
    assert.equal(sp._spCanClaim(answer()), true);
    assert.equal(sp._spCanClaim(answer({ account: { eligible: false } })), false);
    assert.equal(sp._spCanClaim(answer({ account: undefined })), true, 'нет сведений об аккаунте: кнопку не прячем, решает сервер');
    assert.equal(sp._spCanClaim(null), true);
  });

  await section('Страница: обычный день, три уровня к получению', () => {
    const t = boot(), html = render(t, answer());
    assert.match(html, /<div class="eyebrow-row"><button type="button" class="v3-link" onclick="spBack\(\)" aria-label="Назад">‹ Назад<\/button><\/div>/);
    assert.match(html, /<span class="v3-eyebrow">Сезон 1 · до 11 мая 2027<\/span>/);
    assert.match(html, /<h1 class="v3-title">Пропуск сезона<span class="ap-gl" data-t="Пропуск сезона"><\/span><\/h1>/);
    assert.match(html, /<section class="sp-sec sp-hero" aria-label="Уровень 6 из 30">/);
    assert.match(html, /<b>6<\/b><span>из 30 уровней<\/span>/);
    assert.match(html, /role="progressbar" aria-label="Очки до следующего уровня" aria-valuemin="0" aria-valuemax="300" aria-valuenow="20"><span><i style="--p:0\.0667">/);
    assert.match(html, /До 7 уровня: <b>280 очков<\/b>/);
    assert.match(html, /Всего 1 820 очков/);
    assert.match(html, /<div class="sp-claim" data-season="1">\s*<button type="button" class="v3-pill v3-pill--full" onclick="spClaim\(1\)" >Забрать 3 уровня<\/button>/);
    assert.match(html, /<p class="sp-gain">120 🪙 Моры и 30 💧 Эссенции<\/p>/);
    assert.ok(!/sp-note">Награды выдаются/.test(html) && !html.includes('disabled'), 'аккаунт подходит: кнопка не выключена, пояснения нет');
    assert.match(html, /<p class="v3-err sp-err" role="alert" hidden><\/p>/, 'строка отказа есть и скрыта');
    assert.ok(!html.includes('sp-next'), 'пока есть что забрать, «следующая награда» не пишется');
    // путь: 3 получены, 3 можно забрать, 7-й следующий, остальные впереди
    const dots = html.match(/<li class="sp-lv is-(\w+)">/g).map(x => /is-(\w+)/.exec(x)[1]);
    assert.equal(dots.length, 30);
    assert.deepEqual([...new Set(dots)].map(s => dots.filter(d => d === s).length), [3, 3, 1, 23]);
    assert.deepEqual(dots.slice(0, 8), ['got', 'got', 'got', 'ready', 'ready', 'ready', 'next', 'lock']);
    assert.match(html, /<span class="sr-only">Уровень 1, получен<\/span><span aria-hidden="true"><svg/, 'у полученного галочка, а для чтения с экрана подпись');
    assert.match(html, /<span class="sr-only">Уровень 4, можно забрать<\/span><span aria-hidden="true">4<\/span>/);
    assert.match(html, /<span class="sr-only">Уровень 7, следующий<\/span>/);
    assert.match(html, /<span class="sr-only">Уровень 30, впереди<\/span>/);
    assert.match(html, /<ol class="sp-track" role="list" aria-label="Уровни пропуска">/);
    assert.match(text(html), /Каждый уровень: 40 🪙 Моры и 10 💧 Эссенции\. Весь путь: 1 200 🪙 Моры и 300 💧 Эссенции\./);
    // как копить очки
    assert.match(text(html), /\+10 за каждую зачётную игру, до 100 очков в сутки\./);
    assert.match(html, /aria-label="Очки за сегодня" aria-valuemin="0" aria-valuemax="100" aria-valuenow="40"><span><i style="--p:0\.4000">/);
    assert.match(text(html), /Сегодня 40 из 100/);
    assert.ok(!html.includes('Новые очки откроются'), 'до предела дня ещё далеко');
    assert.match(text(html), /Ритм: чистый забег, от 20 верных нажатий\./);
    assert.match(text(html), /Сапёр: победа\./);
    assert.match(text(html), /Награды за места в таблице сезона платятся отдельно и в пропуск не входят\./);
    assert.ok(!html.includes('закончился'), 'прошлого сезона нет');
  });

  await section('Страница: предел дня выбран', () => {
    const t = boot(), html = render(t, answer({}, season({ points_today: 100 })));
    assert.match(html, /Сегодня <b>100<\/b> из 100<\/span><span>Новые очки откроются в \d\d:\d\d<\/span>/);
    assert.match(html, /aria-valuenow="100"><span><i style="--p:1\.0000">/);
    const over = render(t, answer({}, season({ points_today: 140 })));
    assert.match(over, /--p:1\.0000/, 'шкала дня не вылезает за край, даже если сервер отдал больше предела');
    assert.match(over, /Новые очки откроются/);
    const zero = render(t, answer({}, season({ points_today: 0 })));
    assert.match(zero, /Сегодня <b>0<\/b> из 100/);
    assert.match(zero, /aria-valuenow="0"><span><i style="--p:0\.0000">/);
  });

  await section('Страница: нечего забирать, путь пройден, тридцатый уровень', () => {
    const t = boot();
    let html = render(t, answer({}, season(DONE)));
    assert.ok(!html.includes('class="sp-claim"') && !html.includes('spClaim('), 'нечего забирать: кнопки нет');
    assert.match(text(html), /Следующая награда: 40 🪙 Моры и 10 💧 Эссенции на 7 уровне\./);
    assert.deepEqual(plain(html.match(/is-(got|ready|next|lock)/g).filter((x, i, a) => a.indexOf(x) === i)), ['is-got', 'is-next', 'is-lock']);
    // дошли до конца, но не всё забрано
    const top = { points: 9400, level: 30, points_to_next: 0, claimed_level: 24, claimable_levels: 6, claimable: { mora: 240, essence: 60 } };
    html = render(t, answer({}, season(top)));
    assert.match(html, /<b>30<\/b><span>из 30 уровней<\/span>/);
    assert.match(html, /<span>Весь путь пройден<\/span><span>Всего 9 400 очков<\/span>/);
    assert.match(html, /aria-valuenow="300"><span><i style="--p:1\.0000">/, 'на последнем уровне шкала полная');
    assert.match(html, />Забрать 6 уровней<\/button>/);
    assert.match(html, /240 🪙 Моры и 60 💧 Эссенции/);
    assert.ok(!html.includes('Все награды сезона получены') && !html.includes('sp-next'));
    assert.equal(count(html, 'is-ready'), 6);
    assert.equal(count(html, 'is-next'), 0, 'после тридцатого «следующего» нет');
    // всё забрано
    html = render(t, answer({}, season({ ...top, claimed_level: 30, claimable_levels: 0, claimable: { mora: 0, essence: 0 } })));
    assert.ok(!html.includes('spClaim('));
    assert.match(text(html), /Все награды сезона получены\./);
    assert.equal(count(html, 'class="sp-lv is-got"'), 30);
    // новичок: очков нет
    html = render(t, answer({}, season({ points: 0, level: 0, points_to_next: 300, claimed_level: 0, claimable_levels: 0, claimable: { mora: 0, essence: 0 }, points_today: 0 })));
    assert.match(html, /<b>0<\/b>/);
    assert.match(html, /До 1 уровня: <b>300 очков<\/b>/);
    assert.match(html, /aria-valuenow="0"><span><i style="--p:0\.0000">/);
    assert.match(text(html), /Следующая награда: 40 🪙 Моры и 10 💧 Эссенции на 1 уровне\./);
    assert.equal(count(html, 'class="sp-lv is-next"'), 1);
  });

  await section('Страница: аккаунт моложе 14 дней', () => {
    const t = boot();
    const young = (account) => render(t, answer({ account }));
    let html = young({ eligible: false, eligible_from: '2026-10-22T00:00:00+00:00', min_days: 14 });
    assert.match(html, /<button type="button" class="v3-pill v3-pill--full" onclick="spClaim\(1\)" disabled aria-disabled="true">Забрать 3 уровня<\/button>/);
    assert.match(text(html), /Награды выдаются аккаунтам, которые в боте не меньше 14 дней\. Очки копятся, забрать можно с 22 октября\./);
    assert.match(text(html), /120 🪙 Моры и 30 💧 Эссенции/, 'что ждёт игрока, видно и до срока');
    html = young({ eligible: false, min_days: 1 });
    assert.match(text(html), /не меньше 1 дня\. Очки копятся, забрать можно позже\./);
    html = young({ eligible: false, min_days: 22 });
    assert.match(text(html), /не меньше 22 дней\./);
    html = young({ eligible: false });
    assert.match(text(html), /которые уже достаточно давно в боте\. Очки копятся, забрать можно позже\./, 'без чисел от сервера: общая фраза, а не «undefined»');
    assert.ok(!/undefined|NaN|null/.test(html));
  });

  await section('Страница: прошлый сезон', () => {
    const t = boot();
    const prev = (o = {}) => season({ season: 1, current: false, level: 11, points: 3410, points_to_next: 190, claimed_level: 4, claimable_levels: 7, claimable: { mora: 280, essence: 70 }, ends_at: '2026-10-03T00:00:00+00:00', claim_until: '2026-11-12T00:00:00+00:00', points_today: 0, ...o });
    const cur = season({ season: 2, points: 640, level: 2, points_to_next: 260, claimed_level: 2, claimable_levels: 0, claimable: { mora: 0, essence: 0 } });
    let html = render(t, answer({}, prev(), cur));
    assert.match(html, /<span class="v3-eyebrow">Сезон 2 · до 11 мая 2027<\/span>/, 'шапка про текущий сезон');
    assert.match(html, /<b>2<\/b>/);
    assert.match(html, /<span class="v3-eyebrow" id="sp-h-prev">Сезон 1 закончился<\/span>/);
    assert.match(text(html), /Не забранные награды лежат до 12 ноября\. Пройдено 11 уровней из 30\./);
    assert.equal(count(html, 'class="sp-claim"'), 1, 'кнопка только у прошлого сезона');
    assert.ok(html.indexOf('id="sp-h-prev"') > 0 && html.indexOf('id="sp-h-prev"') < html.indexOf('id="sp-h-track"'), 'награды, которые скоро сгорят, стоят выше пути, а не в конце длинной страницы');
    assert.match(html, /<div class="sp-claim" data-season="1">\s*<button type="button" class="v3-pill v3-pill--full" onclick="spClaim\(1\)" >Забрать 7 уровней<\/button>/);
    assert.match(text(html), /280 🪙 Моры и 70 💧 Эссенции/);
    // у обоих сезонов есть что забрать: две кнопки, каждая за свой сезон
    html = render(t, answer({}, prev(), { ...cur, claimed_level: 0, claimable_levels: 2, claimable: { mora: 80, essence: 20 } }));
    assert.equal(count(html, 'class="sp-claim"'), 2);
    assert.match(html, /onclick="spClaim\(2\)"/);
    assert.match(html, /onclick="spClaim\(1\)"/);
    // всё получено
    html = render(t, answer({}, prev({ claimed_level: 11, claimable_levels: 0, claimable: { mora: 0, essence: 0 } }), cur));
    assert.match(text(html), /Пройдено 11 уровней из 30, все награды получены\./);
    assert.ok(!html.includes('spClaim(1)'));
    assert.ok(html.indexOf('id="sp-h-prev"') > html.indexOf('id="sp-h-how"'), 'справка о закончившемся сезоне идёт в самом конце');
    // не играли: блока нет
    html = render(t, answer({}, prev({ level: 0, points: 0, claimed_level: 0, claimable_levels: 0, claimable: { mora: 0, essence: 0 } }), cur));
    assert.ok(!html.includes('закончился') && !html.includes('sp-prev'), 'сезон без очков не показываем');
    // аккаунт не успеет повзрослеть до конца срока выдачи: кнопка выключена, причина названа прямо
    html = render(t, answer({ account: { eligible: false, eligible_from: '2026-11-20T00:00:00+00:00', min_days: 14 } }, prev(), cur));
    assert.match(html, /onclick="spClaim\(1\)" disabled aria-disabled="true"/);
    assert.match(text(html), /Этот сезон забрать уже не получится: срок выдачи закончится раньше, чем аккаунту исполнится нужный возраст\./);
    // успеет: обычное пояснение с датой
    html = render(t, answer({ account: { eligible: false, eligible_from: '2026-11-01T00:00:00+00:00', min_days: 14 } }, prev(), cur));
    assert.match(text(html), /забрать можно с 1 ноября\./);
    assert.ok(!html.includes('уже не получится'));
  });

  await section('Страница: закрытый пропуск, пустой ответ', () => {
    const t = boot();
    for (const me of [{ enabled: false }, null, { enabled: true, seasons: [] }, { enabled: true, seasons: [season({ current: false })] }]) {
      t.sp.state.me = me; t.sp._spRender();
      const html = flat(t.page.innerHTML);
      assert.match(html, /<b>Пропуск пока закрыт<\/b>Загляните позже/, JSON.stringify(me));
      assert.match(html, /<span class="v3-eyebrow">Сезон игр<\/span>/);
      assert.ok(!html.includes('spClaim('));
    }
    const lonely = boot({ el: () => null });
    lonely.sp.state.me = answer(); lonely.sp._spRender();   // страницы нет в разметке: ничего не падает
  });

  await section('Чужой текст и мусор вместо чисел не становятся разметкой', () => {
    const t = boot(), evil = '"><img src=x onerror=alert(1)><script>alert(2)</script>';
    const hostile = season({ season: evil, starts_at: evil, ends_at: evil, claim_until: evil, claimable: { mora: evil, essence: 5 }, per_level: { mora: evil, essence: evil }, full_track: { mora: evil, essence: evil },
      points: evil, level: 6, points_to_next: evil, points_today: evil, points_per_game: evil });
    for (const me of [answer({ account: { eligible: false, eligible_from: evil, min_days: evil } }, hostile), answer({}, { ...hostile, current: false }, { ...hostile, current: true })]) {
      const html = render(t, me);
      assert.ok(!/<img|<script|onerror=alert/i.test(html), 'в разметку попал чужой тег');
      assert.ok(!html.includes(evil), 'чужая строка не попала в разметку целиком');
    }
    const lost = boot();
    lost.net.meFail = evil; lost.sp.state.me = null;
    lost.sp.loadSeasonPass();
    return settle().then(() => {
      const html = lost.page.innerHTML;
      assert.ok(!/<img|<script/i.test(html), 'текст ошибки экранируется');
      assert.match(html, /<b>Пропуск не загрузился<\/b><span>&quot;&gt;&lt;img src=x onerror=alert\(1\)&gt;/);
    });
  });

  await section('Чтение: кэш на минуту, принудительное чтение, повтор', async () => {
    const t = boot();
    assert.deepEqual(plain(await t.sp._spLoad(false)), plain(answer()));
    await t.sp._spLoad(false);
    assert.deepEqual(t.net.requests, ['GET /season-pass/me'], 'в пределах минуты ответ берётся из памяти');
    await t.sp._spLoad(true);
    assert.equal(t.net.requests.length, 2, 'принудительное чтение идёт на сервер');
    t.sp.state.at = NOW - 61000;
    await t.sp._spLoad(false);
    assert.equal(t.net.requests.length, 3, 'через минуту читаем заново');
    t.net.meFail = 'Сервер прилёг отдохнуть. Попробуй через минуту.';
    await assert.rejects(t.sp._spLoad(true), /Сервер прилёг/);
    assert.deepEqual(plain(t.sp.state.me), plain(answer()), 'сбой чтения не стирает прежние данные');
  });

  await section('Точка на вкладке «Игры» и проверка при заходе', async () => {
    const t = boot();
    t.sp.passCheck(); await settle();
    assert.equal(t.tab.dataset.sp, '1', 'есть что забрать и аккаунт подходит: точка горит');
    assert.equal(t.tab.notes, 1, 'для чтения с экрана к вкладке добавлена подпись');
    t.sp._spDockSync(answer()); t.sp._spDockSync(answer());
    assert.equal(t.tab.notes, 1, 'подпись добавляется один раз');
    t.sp._spDockSync(answer({}, season(DONE)));
    assert.equal(t.tab.dataset.sp, undefined, 'забрать нечего: точка погасла');
    assert.equal(t.tab.notes, 0, 'вместе с подписью');
    t.sp._spDockSync(answer({ account: { eligible: false } }));
    assert.equal(t.tab.dataset.sp, undefined, 'аккаунт не может забрать: точки нет, она бы обманывала');
    t.sp._spDockSync({ enabled: false }); t.sp._spDockSync(null);
    assert.equal(t.tab.dataset.sp, undefined);
    // два захода подряд читают сервер один раз
    const quick = boot();
    quick.sp.passCheck(); quick.sp.passCheck(); quick.sp.passCheck(); await settle();
    assert.deepEqual(quick.net.requests, ['GET /season-pass/me']);
    quick.sp.passCheck(); await settle();
    assert.equal(quick.net.requests.length, 1, 'свежие данные не перечитываются');
    // флаг выключен: сервера никто не спрашивает, старая точка гаснет
    const off = boot({ _sysFlags: { season_pass_v1: false } });
    off.tab.dataset.sp = '1'; off.tab.notes = 1;
    off.sp.passCheck(); await settle();
    assert.deepEqual(off.net.requests, []);
    assert.equal(off.tab.dataset.sp, undefined);
    const unset = boot({ _sysFlags: {} });
    unset.sp.passCheck(); await settle();
    assert.deepEqual(unset.net.requests, [], 'флага нет в ответе профиля: пропуск закрыт');
    // сервер не ответил: тихо, без ошибок и точки
    const down = boot(); down.net.meFail = 'Ошибка сервера';
    down.sp.passCheck(); await settle();
    assert.equal(down.tab.dataset.sp, undefined);
    assert.equal(down.sp.state.checking, false, 'после сбоя проверка снова возможна');
    down.net.meFail = null; down.sp.state.at = 0;
    down.sp.passCheck(); await settle();
    assert.equal(down.tab.dataset.sp, '1');
  });

  await section('Строка в хабе «Игры»', async () => {
    const stateOf = t => ({ html: flat(t.hub.html), text: text(flat(t.hub.html)) });
    // данные уже в памяти: строка сразу с числами
    let t = boot(); t.sp.state.me = plain(answer()); t.sp.state.at = NOW;
    t.sp.passHubRow(t.host);
    let h = stateOf(t);
    assert.match(h.html, /<button type="button" class="v3-game sp-hub is-hot" data-pass onclick="openSeasonPass\(\)">/);
    assert.equal(h.text, 'Пропуск сезона К получению: 3 уровня Забрать');
    await settle();
    assert.equal(t.net.requests.length, 0, 'свежие данные не перечитываются');
    // данных нет: строка с входом, потом числа
    t = boot();
    t.sp.passHubRow(t.host);
    assert.equal(stateOf(t).text, 'Пропуск сезона Загружаем пропуск… Открыть', 'пока сервер молчит, строка уже ведёт на страницу');
    assert.ok(!stateOf(t).html.includes('is-hot'));
    await settle();
    assert.equal(stateOf(t).text, 'Пропуск сезона К получению: 3 уровня Забрать');
    assert.equal(t.tab.dataset.sp, '1', 'то же чтение зажгло точку на вкладке');
    // нечего забирать: уровень и сколько до следующего
    t = boot(); t.net.me = answer({}, season(DONE));
    t.sp.passHubRow(t.host); await settle();
    h = stateOf(t);
    assert.equal(h.text, 'Пропуск сезона Уровень 6 из 30 · до следующего 280 очков Открыть');
    assert.ok(!h.html.includes('is-hot'));
    t = boot(); t.net.me = answer({}, season({ ...DONE, level: 30, claimed_level: 30, points: 9400, points_to_next: 0 }));
    t.sp.passHubRow(t.host); await settle();
    assert.equal(stateOf(t).text, 'Пропуск сезона Весь путь пройден Открыть');
    // аккаунт не может забрать: строка не зовёт «Забрать» и не горит
    t = boot(); t.net.me = answer({ account: { eligible: false, eligible_from: '2026-10-22T00:00:00+00:00', min_days: 14 } });
    t.sp.passHubRow(t.host); await settle();
    assert.equal(stateOf(t).text, 'Пропуск сезона Уровень 6 из 30 · до следующего 280 очков Открыть');
    assert.ok(!stateOf(t).html.includes('is-hot'));
    // пропуск закрыт на сервере: строка исчезает
    t = boot(); t.net.me = { enabled: false };
    t.sp.passHubRow(t.host); await settle();
    assert.equal(t.hub.html, '', 'сервер говорит «закрыт»: строки нет');
    // сбой чтения: строка остаётся со входом
    t = boot(); t.net.meFail = 'Ошибка сервера';
    t.sp.passHubRow(t.host); await settle();
    assert.equal(t.hub.small, 'Откройте, чтобы посмотреть уровни');
    // флаг выключен или хаба нет: ничего не рисуется
    t = boot({ _sysFlags: { season_pass_v1: false } });
    t.sp.passHubRow(t.host); await settle();
    assert.equal(t.hub.html, ''); assert.deepEqual(t.net.requests, []);
    t = boot(); t.sp.passHubRow(null); t.sp.passHubRow(undefined); await settle();
    assert.deepEqual(t.net.requests, []);
    // перерисовка хаба не плодит строки: вторая строка заменяет первую
    t = boot(); t.sp.state.me = plain(answer()); t.sp.state.at = NOW;
    t.sp.passHubRow(t.host); t.sp.passHubRow(t.host);
    assert.equal(count(t.log.join(), 'hub-insert'), 1, 'строка вставляется один раз, дальше заменяется');
  });

  await section('Открытие страницы, загрузка, ошибка, «Назад»', async () => {
    let t = boot();
    t.sp.openSeasonPass();
    assert.deepEqual(plain(t.calls), [['switchPage', 'pass']]);
    assert.match(t.page.innerHTML, /class="sk"/, 'пока сервер думает, скелет');
    t.sp.loadSeasonPass();   // второй вызов, пока идёт чтение, ничего не запрашивает
    await settle();
    assert.equal(t.net.requests.length, 1);
    assert.match(t.page.innerHTML, /<b>6<\/b>/, 'после чтения нарисована страница');
    assert.equal(t.sp.state.loading, false);
    t.net.me = answer({}, season(DONE));
    t.sp.openSeasonPass(); await settle();
    assert.equal(t.net.requests.length, 2, 'страница читает данные заново при каждом открытии, а не из памяти');
    assert.match(flat(t.page.innerHTML), /Следующая награда/, 'и рисует свежие числа');
    // сбой: сообщение и «Повторить»; повтор читает заново
    t = boot(); t.net.meFail = 'Нет связи с сервером';
    t.sp.openSeasonPass(); await settle();
    assert.match(flat(t.page.innerHTML), /<div class="v3-empty" role="alert"><b>Пропуск не загрузился<\/b><span>Нет связи с сервером<\/span> <button type="button" class="v3-link" onclick="loadSeasonPass\(\)">Повторить<\/button>/);
    assert.match(t.page.innerHTML, /onclick="spBack\(\)"/, 'из ошибки можно уйти назад');
    t.net.meFail = null;
    t.sp.loadSeasonPass(); await settle();
    assert.match(t.page.innerHTML, /<b>6<\/b>/, 'повтор прошёл');
    // связь потеряна: fetch отвечает английской ошибкой, игрок видит русскую фразу
    t = boot(); t.net.meFail = new TypeError('Failed to fetch');
    t.sp.openSeasonPass(); await settle();
    assert.match(flat(t.page.innerHTML), /<b>Пропуск не загрузился<\/b><span>Нет связи\. Проверьте интернет и попробуйте ещё раз\.<\/span>/);
    assert.ok(!t.page.innerHTML.includes('Failed to fetch') && !t.page.innerHTML.includes('TypeError'), 'английский текст ошибки не показывается');
    // «Назад»
    t = boot(); t.ctx._navStack.push('arena'); t.sp.spBack();
    assert.deepEqual(plain(t.calls), [['navBack']]);
    t = boot(); t.sp.spBack();
    assert.deepEqual(plain(t.calls), [['switchPage', 'arena']], 'без истории возвращаем в «Игры»');
    // игрок успел уйти со страницы, пока шло чтение: перерисовка всё равно идёт, а не оставляет скелет
    t = boot(); t.ctx._loaded.add('pass'); t.sp.state.me = plain(answer());
    t.sp._spRepaint();
    assert.match(t.page.innerHTML, /<b>6<\/b>/);
    t = boot(); t.sp.state.me = plain(answer());
    t.sp._spRepaint();
    assert.equal(t.page.innerHTML, '', 'страница в этой сессии не открывалась: не рисуем её зря');
  });

  await section('Получение: успех', async () => {
    const t = boot();
    t.sp.state.me = plain(answer()); t.ctx._loaded.add('pass'); t.sp.state.at = NOW; t.sp._spRender(); t.sp._spDockSync(t.sp.state.me);
    assert.equal(t.tab.dataset.sp, '1');
    t.net.claim = () => { t.net.me = answer({}, season(DONE)); return Promise.resolve({ season: 1, claimed_levels: '4-6', mora: 120, essence: 30, claimed_level: 6 }); };
    t.sp.spClaim(1);
    assert.equal(t.buttons[1].disabled, true, 'пока идёт запрос, кнопка выключена');
    assert.equal(t.sp.state.busy, true);
    t.sp.spClaim(1); t.sp.spClaim(1); t.sp.spClaim('1');   // повторные нажатия
    await settle();
    assert.deepEqual(t.net.requests, ['POST /season-pass/claim {"season":1}', 'GET /season-pass/me'], 'один запрос на получение, потом перечитывание');
    assert.deepEqual(t.gifts, [[{ title: 'Пропуск сезона', from: 'Уровни 4-6', glyph: '🏁', gifts: [{ label: '🪙 Мора', amount: 120 }, { label: '💧 Эссенция', amount: 30 }] }]], 'подарок показывает то, что вернул сервер');
    assert.equal(t.sp.state.busy, false);
    assert.ok(!t.page.innerHTML.includes('spClaim('), 'после получения страница без кнопки');
    assert.match(flat(t.page.innerHTML), /Следующая награда: 40 🪙 Моры и 10 💧 Эссенции на 7 уровне\./);
    assert.equal(t.tab.dataset.sp, undefined, 'точка на вкладке погасла');
    assert.deepEqual(t.toasts, []);
    // другое действие после этого снова возможно
    t.net.claim = () => Promise.reject('Нет новых уровней для получения.');
    t.sp.spClaim(1); await settle();
    assert.equal(t.net.requests.filter(r => r.startsWith('POST')).length, 2);
    // мусор вместо номера сезона: запрос не уходит
    const bad = boot();
    for (const x of [0, NaN, undefined, null, 'abc', -3 * 0]) bad.sp.spClaim(x);
    assert.deepEqual(bad.net.requests, []);
    assert.equal(bad.sp.state.busy, false);
  });

  await section('Получение подтверждено, обновление не удалось: только повтор чтения', async () => {
    const t = boot(); t.sp.state.me = plain(answer()); t.ctx._loaded.add('pass');
    t.net.claim = () => { t.net.meFail = new Error('offline'); return Promise.resolve({season:1,claimed_levels:'4-6',claimed_level:6,mora:120,essence:30}); };
    t.sp.spClaim(1); await settle();
    assert.match(t.page.innerHTML, /Награды получены/);
    assert.match(t.page.innerHTML, /onclick="loadSeasonPass\(\)"/);
    assert.ok(!t.page.innerHTML.includes('spClaim('));
    t.sp.spClaim(1); await settle();
    assert.equal(t.net.requests.filter(r => r.startsWith('POST')).length, 1);
    t.net.meFail = null; t.net.me = answer({}, season(DONE));
    t.sp.loadSeasonPass(); await settle();
    assert.equal(t.sp.state.refreshNotice, '');
    assert.equal(t.net.requests.filter(r => r.startsWith('POST')).length, 1);
    assert.equal(t.gifts.length, 1);
  });

  await section('Получение: только Мора или только Эссенция, пустой ответ', async () => {
    let t = boot(); t.net.claim = () => Promise.resolve({ season: 1, claimed_levels: '7', mora: 40, essence: 0, claimed_level: 7 });
    t.sp.spClaim(1); await settle();
    assert.deepEqual(t.gifts[0][0].gifts, [{ label: '🪙 Мора', amount: 40 }], 'нулевая часть не рисуется');
    t = boot(); t.net.claim = () => Promise.resolve({ season: 1, claimed_levels: '', mora: 0, essence: 0 });
    t.sp.spClaim(1); await settle();
    assert.deepEqual(t.gifts, [], 'пустой ответ не показывает подарок на ноль');
    t = boot(); t.net.claim = () => Promise.resolve({ season: 1, mora: 80, essence: 20 });
    t.sp.spClaim(1); await settle();
    assert.equal(t.gifts[0][0].from, 'Награды уровней', 'нет списка уровней: запасная подпись');
    t = boot(); t.net.claim = () => Promise.resolve({ season: 1, claimed_levels: '1-2', mora: '<b>80', essence: 'x' });
    t.sp.spClaim(1); await settle();
    assert.deepEqual(t.gifts, [], 'нечисловые награды не показываются');
  });

  await section('Получение: отказ сервера показывается как есть', async () => {
    for (const refusal of ['Нет новых уровней для получения.', 'Награды пропуска выдаются аккаунтам, которые в боте не меньше 14 дней. Очки копятся, получить можно позже.', 'Срок получения наград этого сезона истёк.', 'Сервер прилёг отдохнуть. Попробуй через минуту.']) {
      const t = boot();
      t.sp.state.me = plain(answer()); t.ctx._loaded.add('pass'); t.sp._spRender();
      t.net.claim = () => Promise.reject(refusal);
      t.sp.spClaim(1); await settle();
      assert.deepEqual(t.gifts, [], 'подарка нет');
      assert.equal(t.errors[1].textContent, refusal, 'текст сервера без изменений');
      assert.equal(t.errors[1].hidden, false);
      assert.equal(t.log[t.log.length - 1].startsWith('haptic:error') ? t.log[t.log.length - 2] : t.log[t.log.length - 1], 'error:' + refusal, 'ошибка показана после перерисовки страницы, а не стёрта ею');
      assert.ok(t.log.includes('haptic:error'));
      assert.equal(t.sp.state.busy, false, 'после отказа можно нажать снова');
      assert.deepEqual(t.toasts, []);
    }
  });

  await section('Получение: отказ после того, как уровни забрали с другого устройства', async () => {
    // сервер честно отказал («Нет новых уровней»), а пока шёл запрос, награда ушла с другого телефона: подарка здесь не показываем, но страница обновляется
    const t = boot();
    t.sp.state.me = plain(answer()); t.ctx._loaded.add('pass'); t.sp._spRender();
    t.net.claim = () => { t.net.me = answer({}, season(DONE)); return Promise.reject('Нет новых уровней для получения.'); };
    t.sp.spClaim(1); await settle();
    assert.deepEqual(t.gifts, [], 'ложного подарка нет');
    assert.equal(t.errors[1].textContent, 'Нет новых уровней для получения.');
    assert.ok(!t.page.innerHTML.includes('spClaim('), 'страница показывает, что уровни уже получены');
  });

  await section('Получение: обрыв связи', async () => {
    // ответ потерялся, но уровни уже выданы: игрок видит подарок, а не ошибку
    let t = boot();
    t.sp.state.me = plain(answer()); t.ctx._loaded.add('pass'); t.sp._spRender();
    t.net.claim = () => { t.net.me = answer({}, season(DONE)); return Promise.reject(new Error('Failed to fetch')); };
    t.sp.spClaim(1); await settle();
    assert.deepEqual(t.gifts, [[{ title: 'Пропуск сезона', from: 'Награды уровней', glyph: '🏁', gifts: [{ label: '🪙 Мора', amount: 120 }, { label: '💧 Эссенция', amount: 30 }] }]], 'награда считается как уровни × награда за уровень');
    assert.ok(!t.log.some(x => x.startsWith('error:')), 'ошибки нет');
    assert.ok(!t.page.innerHTML.includes('spClaim('));
    // связь пропала до сервера: ничего не выдано, сказано честно
    t = boot();
    t.sp.state.me = plain(answer()); t.ctx._loaded.add('pass'); t.sp._spRender();
    t.net.claim = () => Promise.reject(new TypeError('Failed to fetch'));
    t.sp.spClaim(1); await settle();
    assert.deepEqual(t.gifts, []);
    assert.equal(t.errors[1].textContent, 'Нет связи. Проверьте интернет и попробуйте ещё раз.');
    assert.equal(t.errors[1].hidden, false);
    assert.equal(t.sp.state.busy, false);
    // и перечитать не вышло: кнопка снова доступна, причина показана
    t = boot();
    t.sp.state.me = plain(answer()); t.ctx._loaded.add('pass'); t.sp._spRender();
    t.net.claim = () => { t.net.meFail = new Error('Failed to fetch'); return Promise.reject(new Error('Failed to fetch')); };
    t.sp.spClaim(1); await settle();
    assert.equal(t.buttons[1].disabled, false, 'кнопка не остаётся мёртвой');
    assert.equal(t.errors[1].textContent, 'Нет связи. Проверьте интернет и попробуйте ещё раз.');
    assert.equal(t.sp.state.busy, false);
    // строки ошибки на странице нет (ушли с неё): тост
    t = boot({}); t.net.noErrorLine = true;
    t.sp._spShowError(1, 'Что-то не так');
    assert.deepEqual(t.toasts, [['Что-то не так', false]]);
  });

  await section('Подарок: подпись и числа', () => {
    const t = boot();
    t.sp._spCelebrate('4-6', 120, 30);
    t.sp._spCelebrate('', 40, 0);
    t.sp._spCelebrate('7', 0, 0);
    assert.equal(t.gifts.length, 2, 'на ноль подарка нет');
    assert.equal(t.gifts[0][0].from, 'Уровни 4-6');
    assert.equal(t.gifts[1][0].from, 'Награды уровней');
    assert.deepEqual(t.gifts[1][0].gifts, [{ label: '🪙 Мора', amount: 40 }]);
  });

  console.log(`OK: the season pass screen behaves (${sections} sections)`);
})().catch(err => { console.error(err); process.exit(1); });
