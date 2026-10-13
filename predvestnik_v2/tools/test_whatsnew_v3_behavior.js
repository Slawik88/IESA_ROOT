// Behaviour of «Что нового» (FastAPI/static/app.42.js): the real script runs in a vm with a stub page. Started by tools/test_whatsnew_v3_contract.py, or alone: node tools/test_whatsnew_v3_behavior.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const STATIC = path.join(__dirname, '..', 'FastAPI', 'static');
const SOURCE = fs.readFileSync(path.join(STATIC, 'app.42.js'), 'utf8');
const ESCAPER = /^function _profileEsc\(.*$/m.exec(fs.readFileSync(path.join(STATIC, 'app.02.js'), 'utf8'));
assert.ok(ESCAPER, 'app.02.js defines _profileEsc, app.42.js escapes everything through it');
const NOW = new Date(2026, 9, 12, 12, 0, 0).getTime();   // 12 октября 2026, полдень по местному времени
class FixedDate extends Date {
  constructor(...a) { if (a.length) super(...a); else super(NOW); }
  static now() { return NOW; }
}
const plain = x => JSON.parse(JSON.stringify(x));   // результат vm живёт в другом мире объектов: сравниваем через JSON
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
let sections = 0;
const section = async (name, fn) => { try { await fn(); sections++; } catch (err) { err.message = `[${name}] ${err.message}`; throw err; } };

// Страница-заглушка: id → элемент, кнопки дока, localStorage, журнал вызовов экранов
function boot(extra = {}) {
  const els = {}, buttons = [], store = {}, calls = [], handlers = {}, appended = [];
  const ctx = vm.createContext(Object.assign({
    document: {
      getElementById: id => els[id] || null,
      querySelector: sel => { const m = /^\.nb\[data-page="([\w-]+)"\]$/.exec(sel); return m ? buttons.find(b => b.dataset.page === m[1]) || null : null; },
      querySelectorAll: sel => sel === '.nb[data-page]' ? buttons : [],
      addEventListener: (type, fn) => { handlers[type] = fn; },
      createElement: () => ({ style: {}, setAttribute() {}, remove() {} }),
      body: { appendChild: node => appended.push(node) },
    },
    window: { scrollX: 0, scrollY: 0, innerWidth: 390 },
    console, Date: FixedDate, Math, JSON, Object, Array, Set, Promise, RegExp, String, Number,
    localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
    _sysFlags: {}, _navStack: [], _loaded: new Set(),
    el: id => els[id] || null, v3EnterSync() {}, v3GlintMark: t => `<span class="ap-gl" aria-hidden="true"><span data-t="${t}"></span></span>`, _haptic() {},
    switchPage: p => calls.push(['switchPage', p]), navBack: () => calls.push(['navBack']),
    openLooksModal: () => calls.push(['openLooksModal']), openQuestsV1: () => calls.push(['openQuestsV1']), openChestsV1: () => calls.push(['openChestsV1']),
    openPetsV1: () => calls.push(['openPetsV1']), openTopV3: () => calls.push(['openTopV3']), openInventory: () => calls.push(['openInventory']),
    openAchievementsV1: () => calls.push(['openAchievementsV1']), openPromoSheet: () => calls.push(['openPromoSheet']),
    openStoreV3: tab => calls.push(['openStoreV3', tab]), openSettingsModal: () => calls.push(['openSettingsModal']), openChatTracker: () => calls.push(['openChatTracker']), openSeasonPass: () => calls.push(['openSeasonPass']),
    _wnFetch: () => Promise.resolve([]), _wnSeenId: () => '', _wnMarkSeen: list => calls.push(['mark', list.length]),
  }, extra));
  vm.runInContext(ESCAPER[0], ctx);
  vm.runInContext(SOURCE + `
;globalThis.__wn = { _WN_AREA, _WN_GO, _WN_GROUPS, _wnSplit, _wnDetail, _wnDayLabel, _wnEntry, _wnArea, _wnKind, _wnGroupOf, _wnRender, _wnHistory, _wnChips, _wnPaint,
  _wnTabDots, _wnTabVisit, _wnLinkTerms, _wnGoTo, _wnGo, _wnFilter, _wnTermTap, get state() { return _wn; } };`, ctx);
  return { ctx, els, buttons, store, calls, handlers, appended, wn: ctx.__wn };
}

// Записи: даты по убыванию, по две на день
const mk = (id, date, o = {}) => Object.assign({ id, date, tag: 'Новое', title: 'Запись ' + id, summary: 'Первое предложение записи достаточной длины. Вторая часть записи.', details: ['🏠 Главный экран: что изменилось', 'Просто строка'] }, o);
const day = i => new Date(Date.UTC(2026, 9, 12 - (i >> 1))).toISOString().slice(0, 10);
const AREAS = ['games', 'pets', 'chests', 'inventory', 'looks', 'quests', 'top', 'profile', 'wallet', 'chat', 'app', 'games'];
const GO = new Set(['games', 'pets', 'chests', 'inventory', 'looks', 'quests', 'top', 'profile']);   // у этих разделов есть куда вести «Открыть»
const feed = n => Array.from({ length: n }, (_, i) => mk('e' + i, day(i), { area: AREAS[i % AREAS.length], ...(GO.has(AREAS[i % AREAS.length]) ? { open: AREAS[i % AREAS.length] } : {}), ...(i === 2 ? { tag: 'Исправления' } : {}) }));
const count = (html, needle) => html.split(needle).length - 1;

(async () => {
  await section('_wnSplit: строка списка и остаток', () => {
    const { wn } = boot();
    assert.deepEqual(plain(wn._wnSplit({ short: ' Строка ', summary: 'Полный текст.' })), { short: 'Строка', rest: 'Полный текст.' });
    assert.deepEqual(plain(wn._wnSplit({ summary: 'Первое предложение достаточной длины. Второе предложение.' })), { short: 'Первое предложение достаточной длины.', rest: 'Второе предложение.' });
    assert.deepEqual(plain(wn._wnSplit({ summary: 'Коротко.' })), { short: 'Коротко.', rest: '' });
    const long = 'Очень '.repeat(40) + 'длинное первое предложение. И второе.';
    assert.deepEqual(plain(wn._wnSplit({ summary: long })), { short: long, rest: '' }, 'первое предложение длиннее 150 знаков не режется');
    assert.deepEqual(plain(wn._wnSplit({})), { short: '', rest: '' });
  });

  await section('_wnDetail: значок, выделенное начало, экранирование', () => {
    const { wn } = boot();
    const d = wn._wnDetail('🏠 Главный экран: что изменилось', []);
    assert.match(d, /<span class="wn-d-ic" aria-hidden="true">🏠<\/span>/);
    assert.match(d, /<b>Главный экран:<\/b> что изменилось/);
    const bare = wn._wnDetail('Просто строка', []);
    assert.match(bare, /wn-d-ic" aria-hidden="true">•</);
    assert.ok(!bare.includes('<b>'));
    assert.ok(!wn._wnDetail('Очень длинное начало строки без точки, которое тянется дальше: хвост', []).includes('<b>'), 'двоеточие далеко: начало не выделяется');
    assert.ok(!wn._wnDetail('Готово. Теперь: так', []).includes('<b>'), 'перед двоеточием целое предложение: не выделяется');
    assert.match(wn._wnDetail('2 новых образа: в коллекции', []), /wn-d-ic" aria-hidden="true">•</, 'цифра в начале не значок');
    for (const attack of ['<img src=x onerror=alert(1)> Текст', '"><script>alert(1)</script>', '🏠 <script>alert(1)</script>: x']) {
      const html = wn._wnDetail(attack, []);
      assert.ok(!/<img|<script/i.test(html), `разметка из текста не проходит: ${attack}`);
    }
  });

  await section('_wnLinkTerms: термины, один проход, спецсимволы, кавычки', () => {
    const { wn } = boot();
    const html = wn._wnLinkTerms('Мора нужна для покупок', [{ term: 'Мора', definition: 'Валюта "игры"' }]);
    assert.match(html, /<span class="wn-term" role="button" tabindex="0" data-def="Валюта &quot;игры&quot;">Мора<\/span> нужна/);
    const quote = wn._wnLinkTerms('Мора', [{ term: 'Мора', definition: '" onmouseover="alert(1)' }]);
    assert.ok(!quote.includes('" onmouseover="'), 'определение не выходит из атрибута');
    assert.match(quote, /data-def="&quot; onmouseover=&quot;alert\(1\)"/);
    const once = wn._wnLinkTerms('Мора', [{ term: 'Мора', definition: 'x' }, { term: 'а', definition: 'y' }]);
    assert.equal(count(once, 'class="wn-term"'), 1, 'длинный термин раньше короткого, вложенных нет');
    assert.match(once, /data-def="x"/);
    const special = wn._wnLinkTerms('цена (в $) и [x] a.b', [{ term: '(в $)', definition: 'd' }, { term: '[x]', definition: 'e' }, { term: 'a.b', definition: 'f' }]);
    assert.equal(count(special, 'class="wn-term"'), 3, 'символы регулярных выражений в терминах не ломают разбор');
    assert.equal(wn._wnLinkTerms('<b>x</b>', []), '&lt;b&gt;x&lt;/b&gt;');
    assert.equal(wn._wnLinkTerms('a', [{ term: '', definition: 'x' }, null]), 'a', 'пустые и битые термины пропускаются');
  });

  await section('_wnDayLabel: сегодня, вчера, дата, год', () => {
    const { wn } = boot(), today = new Date(2026, 9, 12);
    assert.equal(wn._wnDayLabel('2026-10-12', today), 'Сегодня, 12 октября');
    assert.equal(wn._wnDayLabel('2026-10-11', today), 'Вчера, 11 октября');
    assert.equal(wn._wnDayLabel('2026-10-09', today), '9 октября');
    assert.equal(wn._wnDayLabel('2025-12-31', today), '31 декабря 2025');
    assert.equal(wn._wnDayLabel('не дата', today), 'не дата');
    assert.equal(wn._wnDayLabel('', today), '');
    assert.equal(wn._wnDayLabel('2026-10-12'), 'Сегодня, 12 октября', 'без аргумента берётся сегодняшний день');
  });

  await section('_wnArea / _wnKind: запасные значения для старых записей', () => {
    const { wn } = boot();
    assert.equal(wn._wnArea({ area: 'games' }), 'games');
    assert.equal(wn._wnArea({ area: 'нет такого', tag: 'Чат' }), 'chat', 'неизвестный раздел берётся из тега');
    assert.equal(wn._wnArea({ tag: 'VIP' }), 'wallet');
    assert.equal(wn._wnArea({ tag: 'Что угодно' }), 'app');
    assert.equal(wn._wnArea({ area: '__proto__' }), 'app', 'служебные имена не считаются разделом');
    for (const tag of ['Исправления', 'Исправлено', 'Фикс', 'Стабильность']) assert.equal(wn._wnKind({ tag }), 'fix', tag);
    assert.equal(wn._wnKind({ kind: 'fix', tag: 'Новое' }), 'fix');
    assert.equal(wn._wnKind({ tag: 'Новое' }), 'new');
  });

  await section('_wnEntry: крупная запись, строка истории, исправление, чужие ключи', () => {
    const { wn } = boot();
    const e = (u, o) => wn._wnEntry(Object.assign(mk('x1', '2026-10-12', { area: 'games', open: 'games', where: 'Игры › Ритм' }), u), o);
    const loud = e({}, { fresh: true, isNew: true, day: 'Сегодня' });
    assert.match(loud, /class="wn-it wn-it--fresh"/);
    assert.match(loud, /<button type="button" class="v3-pill v3-pill--sm" data-wn-go="games" aria-label="Открыть Игры: Запись x1">Открыть Игры<svg/);
    assert.match(loud, /<span class="wn-new">Новое<\/span>/);
    assert.ok(loud.indexOf('wn-where') > 0 && loud.indexOf('wn-where') < loud.indexOf('class="wn-x"'), 'у крупной записи «Где искать» на виду, не в подробностях');
    const row = e({}, {});
    assert.match(row, /class="wn-go" data-wn-go="games"/, 'в истории «Открыть» тихой ссылкой');
    assert.ok(row.indexOf('wn-where') > row.indexOf('class="wn-x"'), 'в строке истории «Где искать» лежит в подробностях');
    assert.ok(!/class="wn-new"/.test(row), 'без isNew метки нет');
    for (const fix of [{ tag: 'Исправления' }, { kind: 'fix' }]) {
      const quiet = e(fix, { fresh: true });
      assert.ok(!quiet.includes('data-wn-go'), 'у исправления нет «Открыть»');
      assert.match(quiet, /wn-it wn-it--fix/);
      assert.match(quiet, /<span class="wn-fx">Исправлено<\/span>/);
      assert.ok(quiet.indexOf('wn-where') > quiet.indexOf('class="wn-x"'), '«Где искать» исправления лежит в подробностях');
    }
    for (const key of ['nope', '__proto__', 'constructor', 'toString', 'hasOwnProperty', '', null, 7]) {
      assert.ok(!e({ open: key }, { fresh: true }).includes('data-wn-go'), `ключ ${String(key)} не ведёт никуда`);
    }
    const hostile = e({ id: 'a"b', title: '<img src=x onerror=1>', short: '"><svg onload=1>', where: '<i>путь</i>', details: ['Просто строка'], summary: '<u>текст</u>' }, { fresh: true });
    assert.ok(!/<img|<svg onload|<i>|<u>/.test(hostile), 'текст записи не становится разметкой');
    assert.match(hostile, /data-id="a&quot;b"/);
    const m = /aria-expanded="false" aria-controls="(wn-x-\d+)"/.exec(loud);
    assert.ok(m && loud.includes(`id="${m[1]}" hidden`), 'кнопка раскрытия связана с панелью и панель закрыта');
    wn.state.open.add('x1');
    const opened = e({}, { fresh: true });
    assert.match(opened, /wn-it--fresh is-open/);
    assert.match(opened, /aria-expanded="true"/);
    assert.ok(!/class="wn-x" id="wn-x-\d+" hidden/.test(opened) && !/id="wn-x-\d+" hidden/.test(opened), 'открытая панель не скрыта');
    wn.state.open.clear();
    const bare = e({ details: [], summary: 'Коротко.', where: '' }, {});
    assert.ok(!bare.includes('data-wn-toggle') && !bare.includes('class="wn-x"'), 'нечего раскрывать: кнопки и панели нет');
    assert.match(bare, /<div class="wn-hd">/);
  });

  await section('_wnRender: первый заход, есть новое, всё прочитано, пусто', () => {
    const t = boot(), { wn, els } = t, list = feed(12);
    els['pg-news'] = { innerHTML: '', contains: () => true };
    wn._wnRender(list, '');
    let html = els['pg-news'].innerHTML;
    assert.equal(wn.state.first, true);
    assert.deepEqual(plain(wn.state.hero.map(u => u.id)), ['e0', 'e1', 'e3'], 'новичку три последних новинки, исправление остаётся в истории');
    assert.match(html, /Последние обновления/);
    assert.match(html, /Всё, что менялось в приложении/);
    assert.equal(count(html, 'class="wn-new"'), 0, 'новичку «Новое» не рисуется');
    assert.match(html, /История · 9/);
    assert.match(html, /class="wn-chips" role="group" aria-label="Фильтр по разделам"/);

    wn._wnRender(list, 'e4');
    html = els['pg-news'].innerHTML;
    assert.equal(wn.state.first, false);
    assert.deepEqual(plain(wn.state.hero.map(u => u.id)), ['e0', 'e1', 'e2', 'e3'], 'новое для игрока: всё, что выше прочитанного, исправления тише внутри блока');
    assert.match(html, /Новое для вас · 4/);
    assert.match(html, /С прошлого раза: 4 обновления\./);
    assert.equal(count(html, 'class="wn-new"'), 4);
    assert.equal(count(html, 'wn-it--fresh'), 3, 'исправление в крупном блоке не крупное');
    assert.equal(count(html, 'wn-it--fix'), 1);
    const cut = html.indexOf('aria-labelledby="wn-h-hist"'), top = html.slice(0, cut), rest = html.slice(cut);
    assert.equal(count(top, 'v3-pill v3-pill--sm'), 3, 'кнопка «Открыть» в крупном блоке только у новинок с переходом');   // e0 games, e1 pets, e3 inventory (e2 исправление)
    assert.equal(count(rest, 'class="wn-go"'), 5, 'в истории «Открыть» тихой ссылкой');   // e4 looks, e5 quests, e6 top, e7 profile, e11 games

    const many = feed(20);
    wn._wnRender(many, 'e7');
    html = els['pg-news'].innerHTML;
    assert.equal(wn.state.hero.length, 5, 'крупно не больше пяти');
    assert.equal(count(html, 'class="wn-new"'), 7, 'остальные новые идут в историю с пометкой «Новое»');
    assert.match(html, /Новое для вас · 7/);

    wn._wnRender(list, 'e0');
    html = els['pg-news'].innerHTML;
    assert.ok(!html.includes('wn-sec--fresh') && wn.state.hero.length === 0);
    assert.match(html, /Вы в курсе всех обновлений/);
    assert.match(html, /История · 12/);

    wn._wnRender(list, 'такого id нет');
    assert.equal(wn.state.first, true, 'прочитанное, которого нет в ленте, ведёт себя как первый заход');

    wn._wnRender([], 'x');
    html = els['pg-news'].innerHTML;
    assert.match(html, /Пока тихо/);
    assert.match(html, /Что нового/);
    assert.ok(!html.includes('wn-chips'));

    wn._wnRender(feed(1), 'e0');
    assert.match(els['pg-news'].innerHTML, /Вы в курсе всех обновлений/);
    assert.match(els['pg-news'].innerHTML, /1 обновление|Вы в курсе/);
  });

  await section('Чужой текст в любом поле записи не становится разметкой', () => {
    const t = boot(), { wn, els } = t, evil = '"><img src=x onerror=alert(1)><script>alert(2)</script>';
    els['pg-news'] = { innerHTML: '', contains: () => true };
    const hostile = Object.fromEntries(['id', 'date', 'tag', 'area', 'kind', 'open', 'where', 'short', 'title', 'summary', 'flag'].map(k => [k, evil]));
    hostile.details = [evil, `🏠 ${evil}: ${evil}`]; hostile.terms = [{ term: evil, definition: evil }];
    const newest = [Object.assign({}, hostile, { id: 'h0', date: '2026-10-12' }), Object.assign({}, hostile, { id: 'h1', date: evil }), mk('h2', '2026-10-10'), mk('h3', '2026-10-09')];
    for (const seen of ['', 'h3', 'h0']) {
      wn._wnRender(newest, seen);
      const html = els['pg-news'].innerHTML;
      assert.ok(!/<img|<script|onerror=alert/i.test(html.replace(/&lt;img[^]*?&gt;/g, '')), `seen=${seen || 'пусто'}: в разметку попал чужой тег`);
    }
    wn.state.open.add('h0'); wn._wnRender(newest, 'h3');
    assert.ok(!/<img|<script/i.test(els['pg-news'].innerHTML), 'раскрытая запись тоже безопасна');
    wn.state.open.clear();
  });

  await section('_wnRender: склонение «обновление / обновления / обновлений»', () => {
    const t = boot(), { wn, els } = t;
    els['pg-news'] = { innerHTML: '', contains: () => true };
    const list = feed(30);
    for (const [seenAt, word] of [[1, 'обновление'], [2, 'обновления'], [5, 'обновлений'], [11, 'обновлений'], [21, 'обновление']]) {
      wn._wnRender(list, 'e' + seenAt);
      assert.match(els['pg-news'].innerHTML, new RegExp(`С прошлого раза: ${seenAt} ${word}\\.`), `${seenAt} ${word}`);
    }
  });

  await section('История: дни, фильтр, «Показать ещё»', () => {
    const t = boot(), { wn, els } = t, list = feed(40);
    els['pg-news'] = { innerHTML: '', contains: () => true };
    els['wn-list'] = { innerHTML: '' }; els['wn-more'] = { hidden: true, textContent: '' };
    wn._wnRender(list, '');   // три в крупном блоке, 37 в истории
    let h = wn._wnHistory();
    assert.equal(count(h.html, '<article'), 14, 'за раз 14 записей');
    assert.equal(h.left, 37 - 14);
    assert.match(els['pg-news'].innerHTML, /Показать ещё · 23/);
    assert.equal(count(h.html, '<h3 class="wn-day">'), 8, 'записи собраны по дням: вчера одна (e2), дальше по две, последний день неполный');
    assert.match(h.html, /<h3 class="wn-day">Вчера, 11 октября <b>1<\/b><\/h3>/, 'у дня подписан его день и сколько в нём записей');
    assert.match(h.html, /<h3 class="wn-day">10 октября <b>2<\/b><\/h3>/);
    wn.state.limit += 14; wn._wnPaint();
    assert.equal(count(els['wn-list'].innerHTML, '<article'), 28);
    assert.equal(els['wn-more'].textContent, 'Показать ещё · 9');
    assert.equal(els['wn-more'].hidden, false);
    wn.state.limit += 14; wn._wnPaint();
    assert.equal(count(els['wn-list'].innerHTML, '<article'), 37);
    assert.equal(els['wn-more'].hidden, true, 'всё показано: кнопки нет');

    wn.state.limit = 14; wn.state.filter = 'looks';
    h = wn._wnHistory();
    const rows = wn.state.list.filter(u => !wn.state.hero.includes(u) && wn._wnGroupOf(u) === 'looks');
    assert.equal(count(h.html, '<article'), Math.min(rows.length, 14));
    assert.ok(rows.length > 0 && !/Открыть Игры/.test(h.html), 'фильтр оставляет только свою группу');
    wn._wnFilter('zzz');
    assert.equal(wn.state.filter, 'looks', 'неизвестный фильтр игнорируется');
    wn._wnFilter('all');
    assert.equal(wn.state.filter, 'all');
    assert.equal(wn.state.limit, 14, 'смена фильтра начинает список заново');
  });

  await section('_wnChips: фильтр только когда есть что фильтровать', () => {
    const t = boot(), { wn, els } = t;
    els['pg-news'] = { innerHTML: '', contains: () => true };
    wn._wnRender(feed(10), 'e9');   // 9 строк истории не получится: крупно 9, в истории 1
    assert.equal(wn._wnChips(), '', 'меньше восьми строк: чипов нет');
    wn._wnRender(feed(12), '');
    const chips = wn._wnChips();
    assert.equal(count(chips, 'data-wn-filter='), 1 + wn._WN_GROUPS.filter(g => wn.state.list.some(u => wn._wnGroupOf(u) === g[0])).length);
    assert.match(chips, /data-wn-filter="all" aria-pressed="true">Всё<b>9<\/b>/);
    const oneGroup = Array.from({ length: 12 }, (_, i) => mk('g' + i, day(i), { area: 'games' }));
    wn._wnRender(oneGroup, '');
    assert.equal(wn._wnChips(), '', 'одна группа: фильтровать нечего');
  });

  await section('Нажатия: «Открыть», раскрытие, фильтр, «Показать ещё», термин', () => {
    const t = boot(), { wn, els, calls, handlers, appended } = t;
    els['pg-news'] = { innerHTML: '', contains: () => true };
    els['wn-list'] = { innerHTML: '' }; els['wn-more'] = { hidden: true, textContent: '' };
    wn._wnRender(feed(40), '');
    const click = btn => handlers.click({ target: { closest: sel => sel === '.wn-term' ? null : btn } });
    click({ hasAttribute: n => n === 'data-wn-go', getAttribute: () => 'games' });
    assert.deepEqual(plain(calls), [['switchPage', 'arena']], '«Открыть» вызывает записанный в таблице переход');
    calls.length = 0;
    click({ hasAttribute: n => n === 'data-wn-go', getAttribute: () => '__proto__' });
    click({ hasAttribute: n => n === 'data-wn-go', getAttribute: () => 'нет такого' });
    assert.deepEqual(plain(calls), [], 'чужой ключ ничего не вызывает');
    // раскрытие
    const panel = { hidden: true }, art = { dataset: { id: 'e1' }, classList: { toggle(c, on) { this.on = on; } }, querySelector: () => panel };
    const btn = { hasAttribute: n => n === 'data-wn-toggle', closest: () => art, setAttribute(k, v) { this[k] = v; } };
    click(btn);
    assert.equal(panel.hidden, false); assert.equal(btn['aria-expanded'], 'true'); assert.equal(art.classList.on, true); assert.ok(wn.state.open.has('e1'));
    click(btn);
    assert.equal(panel.hidden, true); assert.equal(btn['aria-expanded'], 'false'); assert.ok(!wn.state.open.has('e1'));
    // фильтр и «Показать ещё»
    click({ hasAttribute: n => n === 'data-wn-filter', getAttribute: () => 'looks' });
    assert.equal(wn.state.filter, 'looks');
    click({ hasAttribute: () => false });
    assert.equal(wn.state.limit, 28, '«Показать ещё» добавляет страницу');
    // кнопка вне страницы ленты не считается
    els['pg-news'].contains = () => false;
    click({ hasAttribute: n => n === 'data-wn-go', getAttribute: () => 'vip' });
    assert.deepEqual(plain(calls), [], 'нажатие вне страницы ленты обработчик не трогает');
    els['pg-news'].contains = () => true;
    // термин: поповер с экранированным текстом
    const term = { textContent: '<b>Мора</b>', getAttribute: () => '"def"', getBoundingClientRect: () => ({ left: 20, bottom: 100 }) };
    handlers.click({ stopPropagation() {}, target: { closest: sel => sel === '.wn-term' ? term : null } });
    assert.equal(appended.length, 1);
    assert.ok(appended[0].innerHTML.includes('&lt;b&gt;Мора&lt;/b&gt;') && appended[0].innerHTML.includes('&quot;def&quot;') && !appended[0].innerHTML.includes('<b>Мора'), 'термин и определение в поповере экранированы');
  });

  await section('Переходы: каждый ключ ведёт на свой экран', () => {
    const t = boot(), { wn, calls } = t;
    const expected = {
      games: ['switchPage', 'arena'], pass: ['openSeasonPass'], looks: ['openLooksModal'], quests: ['openQuestsV1'], chests: ['openChestsV1'], pets: ['openPetsV1'], top: ['openTopV3'],
      profile: ['switchPage', 'profile'], inventory: ['openInventory'], achievements: ['openAchievementsV1'], promo: ['openPromoSheet'],
      zarniki: ['openStoreV3', 'zarniki'], vip: ['openStoreV3', 'vip'], settings: ['openSettingsModal'], chats: ['openChatTracker'], help: ['switchPage', 'help'],
    };
    assert.deepEqual(Object.keys(plain(wn._WN_GO)).sort(), Object.keys(expected).sort(), 'таблица переходов и тест описывают одни и те же ключи');
    for (const [key, call] of Object.entries(expected)) {
      calls.length = 0; wn._wnGoTo(key);
      assert.deepEqual(plain(calls), [call], key);
      assert.ok(wn._WN_GO[key].cta && wn._WN_GO[key].cta.length <= 24, `подпись кнопки ${key} короткая`);
    }
    calls.length = 0; wn._wnGoTo('__proto__'); wn._wnGoTo('constructor'); wn._wnGoTo(undefined);
    assert.deepEqual(plain(calls), []);
  });

  await section('Вход и выход: openWhatsNew, wnBack', () => {
    const t = boot(), { ctx, calls } = t;
    ctx._loaded.add('news');
    ctx.openWhatsNew();
    assert.equal(ctx._loaded.has('news'), false, 'каждое открытие читает ленту заново');
    assert.deepEqual(plain(calls), [['switchPage', 'news']]);
    calls.length = 0; ctx._navStack.length = 0; ctx.wnBack();
    assert.deepEqual(plain(calls), [['switchPage', 'profile']], 'без истории «Назад» ведёт в профиль');
    calls.length = 0; ctx._navStack.push('arena'); ctx.wnBack();
    assert.deepEqual(plain(calls), [['navBack']], 'с историей «Назад» ведёт туда, откуда пришли');
  });

  await section('loadWhatsNew: скелет, один запрос, «прочитано» после показа, ошибка и повтор', async () => {
    const t = boot(), { ctx, els, calls, wn } = t, list = feed(12);
    els['pg-news'] = { innerHTML: '', contains: () => true };
    let fetches = 0, seen = 'e4';
    ctx._wnFetch = () => { fetches++; return Promise.resolve(list); };
    ctx._wnSeenId = () => seen;
    ctx.loadWhatsNew(); ctx.loadWhatsNew();
    assert.match(els['pg-news'].innerHTML, /class="sk"/, 'пока грузится, виден скелет');
    assert.equal(fetches, 1, 'второй заход во время загрузки не стартует');
    await tick();
    assert.match(els['pg-news'].innerHTML, /Новое для вас · 4/, '«Новое» считается от прочитанного на момент захода');
    assert.deepEqual(plain(calls), [['mark', 12]], 'после показа всё отмечено прочитанным, один раз');
    assert.equal(wn.state.loading, false);
    // после отметки прочитанное сдвинулось: следующий заход видит всё прочитанным
    seen = 'e0'; ctx.loadWhatsNew(); await tick();
    assert.match(els['pg-news'].innerHTML, /Вы в курсе всех обновлений/);

    ctx._wnFetch = () => Promise.reject('Нет <связи>');
    calls.length = 0; ctx.loadWhatsNew(); await tick();
    assert.match(els['pg-news'].innerHTML, /Лента не загрузилась/);
    assert.match(els['pg-news'].innerHTML, /role="alert"/);
    assert.match(els['pg-news'].innerHTML, /onclick="loadWhatsNew\(\)">Повторить</);
    assert.ok(els['pg-news'].innerHTML.includes('Нет &lt;связи&gt;') && !els['pg-news'].innerHTML.includes('<связи>'), 'текст ошибки экранирован');
    assert.deepEqual(plain(calls), [], 'при ошибке прочитанным ничего не отмечается');
    assert.equal(wn.state.loading, false, 'после ошибки можно повторить');
    ctx._wnFetch = () => Promise.resolve(list);
    ctx.loadWhatsNew(); await tick();
    assert.match(els['pg-news'].innerHTML, /История · /, 'повтор показывает ленту');
  });

  await section('Точки на вкладках дока', () => {
    const t = boot(), { wn, ctx, buttons, store } = t;
    const mkBtn = page => { const b = { dataset: { page }, html: '', querySelector(sel) { return sel === '.wn-sr' && this.html ? { remove: () => { this.html = ''; } } : null; }, insertAdjacentHTML(_, h) { this.html += h; } }; buttons.push(b); return b; };
    const [looks, pets, arena, top] = ['looks', 'pets', 'arena', 'top'].map(mkBtn);
    const list = [
      mk('n0', '2026-10-12', { area: 'looks', open: 'looks' }),                          // свежая запись про вкладку «Образы»: точка
      mk('n1', '2026-10-11', { area: 'pets', open: 'pets', tag: 'Исправления' }),         // исправление: точки нет
      mk('n2', '2026-10-11', { area: 'inventory', open: 'inventory' }),                  // ведёт не на вкладку дока: точки нет
      mk('n3', '2026-10-10', { area: 'games', open: 'games' }),                          // точка на «Игры»
      mk('n4', '2026-09-20', { area: 'top', open: 'top' }),                              // старше 14 дней: точки нет
      mk('seen', '2026-09-19'), mk('old', '2026-09-01'),
    ];
    ctx._wnSeenId = () => 'seen';
    wn._wnTabDots(list);
    assert.equal(looks.dataset.wn, '1'); assert.equal(arena.dataset.wn, '1');
    assert.ok(looks.html.includes('class="sr-only wn-sr"') && looks.html.includes('есть новое'), 'точка озвучена для чтения с экрана');
    assert.equal(pets.dataset.wn, undefined, 'исправление не зажигает точку'); assert.equal(top.dataset.wn, undefined, 'старая запись не зажигает точку');
    wn._wnTabDots(list);
    assert.equal(count(looks.html, 'wn-sr'), 1, 'повторный расчёт не плодит подписи');
    wn._wnTabVisit('looks');
    assert.equal(looks.dataset.wn, undefined); assert.equal(looks.html, '');
    assert.ok(JSON.parse(store.wn_dot_ack).includes('n0'), 'закрытая точка запомнена');
    wn._wnTabDots(list);
    assert.equal(looks.dataset.wn, undefined, 'вкладку открывали: точка не возвращается'); assert.equal(arena.dataset.wn, '1');
    wn._wnTabVisit('questlog'); wn._wnTabVisit('looks');   // вкладка без точки ничего не ломает
    ctx._wnSeenId = () => 'n0';   // ничего нового выше прочитанного
    wn._wnTabDots(list);
    assert.equal(arena.dataset.wn, undefined, 'всё прочитано: точки гаснут');
    ctx._wnSeenId = () => '';   // игрок ни разу не открывал ленту: прошлое для него не «новое»
    wn._wnTabDots(list);
    assert.ok(buttons.every(b => b.dataset.wn === undefined));
    ctx._wnSeenId = () => 'нет такого';
    wn._wnTabDots(list);
    assert.ok(buttons.every(b => b.dataset.wn === undefined));
  });

  await section('Точки без localStorage (приватный режим)', () => {
    const broken = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };
    const t = boot({ localStorage: broken }), { wn, ctx, buttons } = t;
    const b = { dataset: { page: 'looks' }, html: '', querySelector(sel) { return sel === '.wn-sr' && this.html ? { remove: () => { this.html = ''; } } : null; }, insertAdjacentHTML(_, h) { this.html += h; } };
    buttons.push(b);
    const list = [mk('n0', '2026-10-12', { area: 'looks', open: 'looks' }), mk('seen', '2026-09-19')];
    ctx._wnSeenId = () => 'seen';
    wn._wnTabDots(list);
    assert.equal(b.dataset.wn, '1');
    wn._wnTabVisit('looks');
    wn._wnTabDots(list);
    assert.equal(b.dataset.wn, undefined, 'хранилище недоступно: закрытая точка помнится до закрытия приложения');
  });

  console.log(`OK: «Что нового» (app.42.js) ведёт себя как задумано: ${sections} разделов проверки`);
})().catch(err => { console.error(err && err.stack || err); process.exit(1); });
