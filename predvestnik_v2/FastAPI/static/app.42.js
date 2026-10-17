// ── «Что нового» · лента обновлений ──────────────────────────────────────────────────
// Данные, «прочитано» и точка на кнопке живут в app.02.js (_wnFetch, _wnNewCount, _wnMarkSeen, checkWhatsNewBadge), здесь только показ. Запись ленты
// (FastAPI/static/updates.json): id, date, tag, title, summary и details обязательны (tools/audit_release_whatsnew.py). Необязательные поля, без них запись
// всё равно читается: short (строка для списка), area (раздел: значок, подпись, фильтр), open (куда ведёт «Открыть»), where (путь словами), flag, terms.
// Формат и правила: docs/WHATS_NEW_V3.md. Стили: news-v3.css.
const _WN_MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const _WN_PAGE = 14;       // записей истории за один раз
const _WN_HERO_MAX = 5;    // сколько новых показывать крупно; остальные идут в историю с пометкой «Новое»
const _WN_DOT_DAYS = 14;   // точка на вкладке дока горит только у записей не старше этого срока
const _WN_SVG = body => `<svg viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
const _WN_ARROW = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';

// Раздел записи: значок тот же, что у вкладки внизу или строки меню, подпись и группа фильтра. Новый раздел добавляют здесь.
const _WN_AREA = {
  games:     { name: 'Игры', group: 'games', ic: '<path d="M8 5.5v13l10.5-6.5z"/>' },
  pets:      { name: 'Питомцы', group: 'stuff', ic: '<circle cx="6.5" cy="11" r="1.7"/><circle cx="10" cy="6.5" r="1.7"/><circle cx="14" cy="6.5" r="1.7"/><circle cx="17.5" cy="11" r="1.7"/><path d="M12 12.5c-3 0-5 2.7-4 4.6.8 1.5 2.4 1.2 4 1.2s3.2.3 4-1.2c1-1.9-1-4.6-4-4.6z"/>' },
  chests:    { name: 'Сундуки', group: 'stuff', ic: '<path d="M4 11V8a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v3M4 11h16v7.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5zM4 14h16"/><path d="M12 12.5v3"/>' },
  inventory: { name: 'Инвентарь', group: 'stuff', ic: '<path d="M9 5.2V4.5a3 3 0 0 1 6 0v.7"/><path d="M6.5 5.2h11A2.5 2.5 0 0 1 20 7.7v10.8a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 18.5V7.7a2.5 2.5 0 0 1 2.5-2.5z"/><path d="M4 11.5h16M10.5 11.5v2.5h3v-2.5"/>' },
  looks:     { name: 'Образы', group: 'looks', ic: '<path d="M6.2 4h11.6L21 9l-9 11L3 9z"/><path d="M3 9h18M9.2 4 12 9l2.8-5M12 9v11"/>' },
  quests:    { name: 'Задания', group: 'me', ic: '<path d="m4.5 6.5 1.6 1.6L9 5M4.5 12.5l1.6 1.6L9 11M4.5 18.5l1.6 1.6L9 17M13 7h6.5M13 13h6.5M13 19h6.5"/>' },
  top:       { name: 'Топ', group: 'me', ic: '<path d="M4.5 20v-7h4.5v7M9.8 20V5h4.4v15M15 20v-9.5h4.5V20"/>' },
  profile:   { name: 'Профиль', group: 'me', ic: '<circle cx="12" cy="8" r="3.6"/><path d="M5 20c.8-3.6 3.6-5.4 7-5.4s6.2 1.8 7 5.4"/>' },
  wallet:    { name: 'Зарники и VIP', group: 'me', ic: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>' },
  chat:      { name: 'Бот в чате', group: 'chat', ic: '<path d="M5 18l-2 3v-5.5A8 8 0 1 1 6 19z"/>' },
  app:       { name: 'Приложение', group: 'me', ic: '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8"/>' },
};
// Чипы фильтра истории: группа → подпись (порядок как на экране)
const _WN_GROUPS = [['games', 'Игры'], ['stuff', 'Питомцы и вещи'], ['looks', 'Образы'], ['me', 'Профиль'], ['chat', 'Бот в чате']];
// Раздел старых записей без поля area берётся из тега; тег исправления делает запись тихой строкой
const _WN_TAG_AREA = { 'Чат': 'chat', 'Семья': 'chat', 'Админка': 'chat', 'VIP': 'wallet' };
const _WN_FIX_TAGS = ['Исправления', 'Исправлено', 'Фикс', 'Стабильность'];

// Куда ведёт «Открыть»: ключ из поля open записи. tab — вкладка дока, на которой зажигается точка, пока запись свежая. Выполняется только то, что записано здесь, а не то, что пришло в JSON.
const _WN_GO = {
  games:        { cta: 'Открыть Игры', tab: 'arena', run: () => switchPage('arena') },
  pass:         { cta: 'Открыть Пропуск', tab: 'arena', run: () => openSeasonPass() },
  looks:        { cta: 'Открыть Образы', tab: 'looks', run: () => openLooksModal() },
  quests:       { cta: 'Открыть Задания', tab: 'questlog', run: () => openQuestsV1() },
  chests:       { cta: 'Открыть Сундуки', tab: 'chests', run: () => openChestsV1() },
  pets:         { cta: 'Открыть Питомцы', tab: 'pets', run: () => openPetsV1() },
  top:          { cta: 'Открыть Топ', tab: 'top', run: () => openTopV3() },
  profile:      { cta: 'Открыть Профиль', tab: 'profile', run: () => switchPage('profile') },
  family:       { cta: 'Открыть Родословную', tab: 'profile', run: () => openFamilyTree() },
  inventory:    { cta: 'Открыть Инвентарь', run: () => openInventory() },
  achievements: { cta: 'Открыть Достижения', run: () => openAchievementsV1() },
  promo:        { cta: 'Ввести промокод', run: () => openPromoSheet() },
  zarniki:      { cta: 'Открыть Зарники', run: () => openStoreV3('zarniki') },
  vip:          { cta: 'Открыть VIP', run: () => openStoreV3('vip') },
  settings:     { cta: 'Открыть Настройки', run: () => openSettingsModal() },
  chats:        { cta: 'Открыть Мои чаты', run: () => openChatTracker() },
  help:         { cta: 'Как пользоваться', run: () => switchPage('help') },
};
const _wnOwn = (table, key) => typeof key === 'string' && Object.prototype.hasOwnProperty.call(table, key);   // ключи из JSON не должны дотянуться до служебных свойств объекта (__proto__, constructor)
const _wnGo = key => _wnOwn(_WN_GO, key) ? _WN_GO[key] : null;

// Состояние страницы: что сейчас крупно, какой фильтр, какие записи раскрыты. Пока идёт загрузка, второй заход не стартует.
let _wn = { list: [], hero: [], unseen: new Set(), first: false, filter: 'all', open: new Set(), limit: _WN_PAGE, loading: false };
let _wnUid = 0;

const _wnWord = (n, one, few, many) => { const m = Math.abs(n) % 100, d = m % 10; return m > 10 && m < 20 ? many : d === 1 ? one : d > 1 && d < 5 ? few : many; };
const _wnArea = u => _wnOwn(_WN_AREA, u.area) ? u.area : (_wnOwn(_WN_TAG_AREA, u.tag) ? _WN_TAG_AREA[u.tag] : 'app');
const _wnKind = u => (u.kind === 'fix' || _WN_FIX_TAGS.includes(u.tag)) ? 'fix' : 'new';
const _wnGroupOf = u => _WN_AREA[_wnArea(u)].group;

// Строка для списка и остаток summary для раскрытой записи: своя short, иначе первое предложение summary
function _wnSplit(u) {
  const text = String(u.summary || '').trim();
  if (u.short) return { short: String(u.short).trim(), rest: text };
  const m = /^([\s\S]{20,}?[.!?…])\s+([\s\S]+)$/.exec(text);
  return m && m[1].length <= 150 ? { short: m[1], rest: m[2] } : { short: text, rest: '' };
}

// «Сегодня, 12 октября», «Вчера, 11 октября», дальше «9 октября» (с годом, если он не нынешний). today нужен только тестам
function _wnDayLabel(iso, today) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || ''); if (!m) return String(iso || '');
  const now = today || new Date(), day = `${+m[3]} ${_WN_MONTHS[+m[2] - 1] || ''}`;
  const diff = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(+m[1], +m[2] - 1, +m[3])) / 864e5);
  return diff === 0 ? `Сегодня, ${day}` : diff === 1 ? `Вчера, ${day}` : (+m[1] !== now.getFullYear() ? `${day} ${m[1]}` : day);
}

const _wnDayShort = (iso, today) => _wnDayLabel(iso, today).replace(/^(Сегодня|Вчера), .*$/, '$1');   // в крупном блоке дата без числа, если это сегодня или вчера

// Подсветка терминов в тексте: один проход по экранированной строке (вставленные span не сканируются повторно), длинные термины раньше коротких.
function _wnLinkTerms(text, terms) {
  const html = _profileEsc(text), list = (terms || []).filter(t => t && t.term);
  if (!list.length) return html;
  const map = {}; list.forEach(t => { map[_profileEsc(t.term)] = t.definition || ''; });
  const keys = Object.keys(map).sort((a, b) => b.length - a.length);
  const re = new RegExp('(' + keys.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'g');
  return html.replace(re, hit => `<span class="wn-term" role="button" tabindex="0" data-def="${_profileEsc(map[hit])}">${hit}</span>`);
}
// Пункт подробностей: значок из начала строки (эмодзи) становится маркером, а короткое начало до двоеточия («Главный экран:») выделяется
function _wnDetail(text, terms) {
  let ic = '•', body = String(text || '').trim();
  const m = /^(\S{1,8})\s+([\s\S]+)$/.exec(body);
  if (m && !/[0-9A-Za-zА-Яа-яЁё«»"'(\[]/.test(m[1])) { ic = m[1]; body = m[2]; }
  const at = body.indexOf(':'), lead = at > 0 && at <= 34 && !/[.!?]/.test(body.slice(0, at)) ? body.slice(0, at + 1) : '';
  const html = lead ? `<b>${_wnLinkTerms(lead, terms)}</b>${_wnLinkTerms(body.slice(lead.length), terms)}` : _wnLinkTerms(body, terms);
  return `<li class="wn-d"><span class="wn-d-ic" aria-hidden="true">${_profileEsc(ic)}</span><span>${html}</span></li>`;
}

// Одна запись. fresh: крупно и с кнопкой (новое для игрока), иначе строка истории; исправления тише и без «Открыть».
function _wnEntry(u, o = {}) {
  const meta = _WN_AREA[_wnArea(u)], fix = _wnKind(u) === 'fix', go = fix ? null : _wnGo(u.open);
  const { short, rest } = _wnSplit(u), terms = u.terms || [], pid = 'wn-x-' + (++_wnUid), isOpen = _wn.open.has(u.id);
  const details = (u.details || []).map(d => _wnDetail(d, terms)).join('');
  const where = u.where ? `<p class="wn-where"><span>Где искать</span> ${_profileEsc(u.where)}</p>` : '', loud = o.fresh && !fix;   // «Где» у новой записи на виду, у строки истории и исправления лежит в подробностях
  const panel = (loud ? '' : where) + (rest ? `<p class="wn-rest">${_wnLinkTerms(rest, terms)}</p>` : '') + (details ? `<ul class="wn-ds">${details}</ul>` : '');
  const tags = `<span class="wn-ar">${_profileEsc(meta.name)}</span>${o.day ? `<span>${_profileEsc(o.day)}</span>` : ''}${fix ? '<span class="wn-fx">Исправлено</span>' : ''}${o.isNew ? '<span class="wn-new">Новое</span>' : ''}`;
  const head = `<span class="wn-meta">${tags}</span><b class="wn-t">${_profileEsc(u.title)}</b><span class="wn-sh">${_profileEsc(short)}</span>`;
  const cta = go ? `<div class="wn-act"><button type="button" class="${loud ? 'v3-pill v3-pill--sm' : 'wn-go'}" data-wn-go="${_profileEsc(u.open)}" aria-label="${_profileEsc(`${go.cta}: ${u.title}`)}">${_profileEsc(go.cta)}${_WN_ARROW}</button></div>` : '';
  return `<article class="wn-it${loud ? ' wn-it--fresh' : fix ? ' wn-it--fix' : ''}${isOpen ? ' is-open' : ''}" data-id="${_profileEsc(u.id)}">
    <span class="wn-ic" aria-hidden="true">${_WN_SVG(meta.ic)}</span>
    <div class="wn-bd">
      ${panel ? `<button type="button" class="wn-hd" data-wn-toggle aria-expanded="${isOpen}" aria-controls="${pid}">${head}<i class="wn-chev" aria-hidden="true"></i></button>` : `<div class="wn-hd">${head}</div>`}
      ${loud ? where : ''}${cta}
      ${panel ? `<div class="wn-x" id="${pid}"${isOpen ? '' : ' hidden'}>${panel}</div>` : ''}
    </div>
  </article>`;
}
// История: всё, что не показано крупно, по дням; фильтр по группе раздела; «Показать ещё» по _WN_PAGE записей
const _wnRows = () => { const skip = new Set(_wn.hero.map(u => u.id)); return _wn.list.filter(u => !skip.has(u.id)); };
function _wnHistory() {
  const rows = _wnRows().filter(u => _wn.filter === 'all' || _wnGroupOf(u) === _wn.filter), shown = rows.slice(0, _wn.limit), days = [];
  shown.forEach(u => { const last = days[days.length - 1]; if (last && last.date === u.date) last.items.push(u); else days.push({ date: u.date, items: [u] }); });
  const html = days.map(d => `<section class="wn-dg"><h3 class="wn-day">${_profileEsc(_wnDayLabel(d.date))} <b>${rows.filter(u => u.date === d.date).length}</b></h3>${d.items.map(u => _wnEntry(u, { isNew: _wn.unseen.has(u.id) })).join('')}</section>`).join('');
  return { html, left: rows.length - shown.length };
}
function _wnChips() {
  const rows = _wnRows(), by = {}; rows.forEach(u => { const g = _wnGroupOf(u); by[g] = (by[g] || 0) + 1; });
  const groups = _WN_GROUPS.filter(g => by[g[0]]);
  if (rows.length < 8 || groups.length < 2) return '';
  const chip = (key, name, count) => `<button type="button" class="wn-chip" data-wn-filter="${key}" aria-pressed="${_wn.filter === key}">${_profileEsc(name)}<b>${count}</b></button>`;
  return `<div class="wn-chips" role="group" aria-label="Фильтр по разделам">${chip('all', 'Всё', rows.length)}${groups.map(g => chip(g[0], g[1], by[g[0]])).join('')}</div>`;
}
function _wnPaint() {
  const list = el('wn-list'), more = el('wn-more'); if (!list) return;
  const h = _wnHistory();
  list.innerHTML = h.html;
  if (more) { more.hidden = h.left <= 0; more.textContent = `Показать ещё · ${h.left}`; }
}

function _wnRender(list, seen) {
  const root = el('pg-news'); if (!root) return;
  const known = !!seen && list.some(u => u.id === seen), count = known ? list.findIndex(u => u.id === seen) : 0;
  _wn.list = list; _wn.first = !known; _wn.unseen = new Set(list.slice(0, count).map(u => u.id));
  _wn.hero = known ? list.slice(0, Math.min(count, _WN_HERO_MAX)) : list.filter(u => _wnKind(u) !== 'fix').slice(0, 3);   // новичку показываем три последних новинки, исправления остаются в истории
  if (!['all', ..._WN_GROUPS.map(g => g[0])].includes(_wn.filter)) _wn.filter = 'all';
  const sub = !known ? 'Всё, что менялось в приложении. Сверху самое свежее.'
    : count ? `С прошлого раза: ${count} ${_wnWord(count, 'обновление', 'обновления', 'обновлений')}. «Открыть» ведёт сразу на нужный экран.`
    : 'Вы в курсе всех обновлений. Новое появится здесь.';
  const head = `<div class="eyebrow-row"><button type="button" class="v3-link" onclick="wnBack()" aria-label="Назад">‹ Назад</button></div>
    <header class="v3-screen-head"><span class="v3-eyebrow">Обновления Предвестника</span><h1 class="v3-title">Что нового${v3GlintMark('Что нового')}</h1><p class="v3-sub">${_profileEsc(sub)}</p></header>`;
  if (!list.length) { root.innerHTML = head + '<div class="v3-empty"><b>Пока тихо</b>Обновления появятся здесь.</div>'; v3EnterSync(root); return; }
  const fresh = _wn.hero.length ? `<section class="wn-sec wn-sec--fresh" aria-labelledby="wn-h-fresh"><div class="v3-sec"><span class="v3-eyebrow" id="wn-h-fresh">${known ? `Новое для вас · ${count}` : 'Последние обновления'}</span></div>${_wn.hero.map(u => _wnEntry(u, { fresh: true, isNew: known, day: _wnKind(u) === 'fix' ? '' : _wnDayShort(u.date) })).join('')}</section>` : '';
  const h = _wnHistory(), rows = _wnRows().length;
  const hist = rows ? `<section class="wn-sec" aria-labelledby="wn-h-hist"><div class="v3-sec"><span class="v3-eyebrow" id="wn-h-hist">История · ${rows}</span></div>${_wnChips()}<div id="wn-list">${h.html}</div><button type="button" class="v3-pill v3-pill--ghost v3-pill--full wn-more" id="wn-more" data-wn-more${h.left > 0 ? '' : ' hidden'}>Показать ещё · ${h.left}</button></section>` : '';
  root.innerHTML = head + fresh + hist;
  v3EnterSync(root);
}

// Нажатия одним обработчиком на документе: раскрыть запись, «Открыть», фильтр, «Показать ещё», термин
function _wnOnClick(e) {
  const t = e.target && e.target.closest ? e.target : null; if (!t) return;
  const term = t.closest('.wn-term');
  if (term) { _wnTermTap(e, term); return; }
  _wnClosePop();
  const btn = t.closest('[data-wn-toggle],[data-wn-go],[data-wn-filter],[data-wn-more]');
  if (!btn || !el('pg-news') || !el('pg-news').contains(btn)) return;
  if (btn.hasAttribute('data-wn-toggle')) _wnToggle(btn);
  else if (btn.hasAttribute('data-wn-go')) _wnGoTo(btn.getAttribute('data-wn-go'));
  else if (btn.hasAttribute('data-wn-filter')) _wnFilter(btn.getAttribute('data-wn-filter'));
  else { _wn.limit += _WN_PAGE; _wnPaint(); _haptic('select'); }
}
document.addEventListener('click', _wnOnClick);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') _wnClosePop();
  else if ((e.key === 'Enter' || e.key === ' ') && e.target && e.target.classList && e.target.classList.contains('wn-term')) { e.preventDefault(); e.target.click(); }
});
function _wnToggle(btn) {
  const art = btn.closest('.wn-it'), panel = art && art.querySelector('.wn-x'); if (!panel) return;
  const open = panel.hidden;   // скрыта сейчас, значит открываем
  panel.hidden = !open; btn.setAttribute('aria-expanded', String(open)); art.classList.toggle('is-open', open);
  if (open) _wn.open.add(art.dataset.id); else _wn.open.delete(art.dataset.id);
  _haptic('select');
}
function _wnGoTo(key) { const go = _wnGo(key); if (!go) return; _haptic('select'); go.run(); }
function _wnFilter(key) {
  if (key !== 'all' && !_WN_GROUPS.some(g => g[0] === key)) return;
  _wn.filter = key; _wn.limit = _WN_PAGE;
  document.querySelectorAll('.wn-chip').forEach(c => c.setAttribute('aria-pressed', String(c.dataset.wnFilter === key)));
  _wnPaint(); _haptic('select');
}

// Мини-поповер с объяснением термина: маленький, на месте, закрывается нажатием в любом месте или Esc
function _wnClosePop() { const pop = document.querySelector('.wn-pop'); if (pop) pop.remove(); }
function _wnTermTap(e, term) {
  e.stopPropagation(); _wnClosePop();
  const pop = document.createElement('div'); pop.className = 'wn-pop'; pop.setAttribute('role', 'status');
  pop.innerHTML = `<b class="wn-pop-t">${_profileEsc(term.textContent)}</b><span class="wn-pop-d">${_profileEsc(term.getAttribute('data-def') || '')}</span>`;
  document.body.appendChild(pop);
  const r = term.getBoundingClientRect(), left = Math.max(10, Math.min(r.left + window.scrollX, window.innerWidth - pop.offsetWidth - 10));
  pop.style.left = left + 'px'; pop.style.top = (r.bottom + window.scrollY + 6) + 'px';
}

// «Назад» ведёт туда, откуда пришли (меню рюкзака открывает ленту с любого экрана), а без истории в профиль
function wnBack() { if (_navStack.length) navBack(); else switchPage('profile'); }
// Лента читается заново при каждом открытии: что игрок уже видел, то больше не «новое». Возврат кнопкой «Назад» страницу не трогает.
function openWhatsNew() { _loaded.delete('news'); switchPage('news'); }
function loadWhatsNew() {
  const box = el('pg-news'); if (!box || _wn.loading) return;
  _wn.loading = true; _wn.filter = 'all'; _wn.open = new Set(); _wn.limit = _WN_PAGE;
  const seen = _wnSeenId();   // «прочитано» на момент захода: _wnMarkSeen ниже сдвинет его, а «Новое» должно остаться на этом экране
  box.innerHTML = '<div class="eyebrow-row"><button type="button" class="v3-link" onclick="wnBack()" aria-label="Назад">‹ Назад</button></div><div class="sk" style="height:84px;border-radius:18px;margin-top:12px"></div><div class="sk" style="height:150px;border-radius:18px;margin-top:18px"></div><div class="sk" style="height:150px;border-radius:18px;margin-top:18px"></div>';
  v3EnterSync(box);
  _wnFetch().then(list => {
    _wn.loading = false;
    _wnRender(list, seen);
    _wnMarkSeen(list);   // открыл ленту: всё прочитано, точки гаснут
    _wnTabDots(list);
  }).catch(err => {
    _wn.loading = false;
    box.innerHTML = `<div class="eyebrow-row"><button type="button" class="v3-link" onclick="wnBack()" aria-label="Назад">‹ Назад</button></div><div class="v3-empty" role="alert"><b>Лента не загрузилась</b><span>${_profileEsc(err)}</span> <button type="button" class="v3-link" onclick="loadWhatsNew()">Повторить</button></div>`;
  });
}

// Точка на вкладке дока: здесь лежит свежая запись (поле open ведёт на эту вкладку). Гаснет, когда игрок открыл вкладку (switchPage зовёт _wnTabVisit) или ленту.
// Для игрока, который ещё не открывал ленту, точек нет: прошлое для него не «новое». Закрытые точки помнятся в localStorage, если он доступен.
let _wnDots = {};   // страница дока → id записей, из-за которых горит точка
const _wnAckMem = new Set();   // то же, что в localStorage, на случай если он недоступен
const _wnAcked = () => { try { return [...JSON.parse(localStorage.getItem('wn_dot_ack') || '[]'), ..._wnAckMem]; } catch (_) { return [..._wnAckMem]; } };
function _wnDotSet(btn, on) {
  if (on) { btn.dataset.wn = '1'; if (!btn.querySelector('.wn-sr')) btn.insertAdjacentHTML('beforeend', '<i class="sr-only wn-sr">, есть новое</i>'); }
  else { delete btn.dataset.wn; const note = btn.querySelector('.wn-sr'); if (note) note.remove(); }
}
function _wnTabDots(list) {
  const seen = _wnSeenId(), at = (list || []).findIndex(u => u.id === seen), ack = new Set(_wnAcked()), now = Date.now(), next = {};
  if (at > 0) list.slice(0, at).forEach(u => {
    const go = _wnGo(u.open), age = (now - Date.parse(u.date + 'T00:00:00')) / 864e5;
    if (go && go.tab && _wnKind(u) !== 'fix' && age <= _WN_DOT_DAYS && !ack.has(u.id)) (next[go.tab] = next[go.tab] || []).push(u.id);
  });
  _wnDots = next;
  _wnPaintDots();
}
function _wnPaintDots() {
  document.querySelectorAll('.nb[data-page]').forEach(btn => {
    const pages = btn.dataset.page === 'more' ? ['more', 'top', 'store', 'shop', 'promo'] : [btn.dataset.page];
    _wnDotSet(btn, pages.some(p => (_wnDots[p] || []).length));
  });
  document.querySelectorAll('[data-wn-page]').forEach(btn => _wnDotSet(btn, !!(_wnDots[btn.dataset.wnPage] || []).length));
}
function _wnTabVisit(page) {
  const ids = _wnDots[page]; if (!ids) return;
  delete _wnDots[page]; ids.forEach(id => _wnAckMem.add(id));
  _wnPaintDots();
  try { localStorage.setItem('wn_dot_ack', JSON.stringify([...new Set([...ids, ..._wnAcked()])].slice(0, 80))); } catch (_) {}
}
