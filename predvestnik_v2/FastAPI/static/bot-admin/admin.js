// Админка Предвестника. Разделы приходят с сервера (/me) — по роли пользователя.
'use strict';

const BASE = window.ADMIN_BASE || '';
const TG = window.Telegram && window.Telegram.WebApp;
const INIT = (TG && TG.initData) || '';
const $ = (sel, root = document) => root.querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const num = n => Number(n).toLocaleString('ru-RU');

// Личные настройки на этом устройстве: последние фильтры, срок, тема, недавние игроки. Без хранилища браузера всё работает как по умолчанию.
const PREFS = (() => {
  let data = {};
  try { data = JSON.parse(localStorage.getItem('pv_admin_prefs') || '{}') || {}; } catch (_) {}
  return {
    get: (key, fallback) => (key in data ? data[key] : fallback),
    set(key, value) { data[key] = value; try { localStorage.setItem('pv_admin_prefs', JSON.stringify(data)); } catch (_) {} },
  };
})();

let ME = null;
const SECTIONS = {};          // key -> render(main)
const SECTION_META = {
  start: ['✦', 'Открываем пульт', 'Проверяем доступ и собираем разделы'],
  people: ['◉', 'Игроки и чаты', 'Поднимаем свежие профили и активность'],
  reports: ['⚑', 'Жалобы', 'Сверяем очередь и решения команды'],
  metrics: ['▥', 'Метрики', 'Собираем показатели без кэшированных цифр'],
  broadcast: ['⌁', 'Рассылка', 'Считаем аудитории и историю отправок'],
  promo: ['✦', 'Промокоды', 'Проверяем коды, награды и ограничения'],
  switches: ['⏻', 'Функции', 'Читаем актуальное состояние переключателей'],
  settings: ['⚙', 'Настройки', 'Загружаем правила бота'],
  health: ['♥', 'Состояние', 'Проверяем бота, базу и очереди'],
};
let _viewAbort = null, _viewRequest = 0, _loadStageTimers = [];

let CURRENT = 'start';   // раздел из «Ещё» не подсвечен в доке, поэтому текущий раздел помним сами
function currentSection() { return CURRENT; }
function clearLoadStages() { _loadStageTimers.forEach(clearTimeout); _loadStageTimers = []; }
function loadingMarkup(key = currentSection()) {
  const [icon, title, hint] = SECTION_META[key] || ['✦', 'Загрузка', 'Получаем свежие данные'];
  return `<section class="admin-load" role="status" aria-live="polite">
    <div class="load-sigil" aria-hidden="true"><i></i><span>${icon}</span></div>
    <div class="load-copy"><small>Предвестник · синхронизация</small><h2>${esc(title)}</h2><p>${esc(hint)}</p></div>
    <div class="load-map" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
    <div class="load-stage"><i></i><span>Подключаемся к серверу</span></div>
  </section>`;
}
function showSectionLoading(main, key = currentSection()) {
  clearLoadStages(); main.setAttribute('aria-busy', 'true'); main.innerHTML = loadingMarkup(key);
  const stage = () => main.querySelector('.load-stage span');
  _loadStageTimers.push(setTimeout(() => { const n = stage(); if (n) n.textContent = 'Читаем актуальные данные'; }, 900));
  _loadStageTimers.push(setTimeout(() => { const n = stage(); if (n) n.textContent = 'Ответ занимает чуть больше времени'; }, 4000));
}
// Экраны «нет входа» и «нет доступа»: то же оформление, что у заставки загрузки, и понятный следующий шаг.
function accessMarkup(error) {
  const code = error?.status, msg = error?.message || '';
  let icon = '↻', small = 'Связь прервалась', title = 'Не удалось открыть админку', text = msg || 'Попробуйте ещё раз.', retry = true;
  if (code === 403) {
    icon = '🛡'; small = 'Нет доступа'; title = 'Только для персонала бота'; retry = false;
    text = msg + (/персонал/.test(msg) ? ' Если вы в команде, попросите создателя выдать вам роль, а потом напишите боту «бот админка».' : '');
  } else if (code === 401) {
    icon = '🔒'; retry = false;
    if (/завершен/i.test(msg)) { small = 'Нужен новый вход'; title = 'Сессия завершена'; text = 'Откройте админку заново: напишите боту в личку «бот админка» и нажмите кнопку.'; }
    else { small = 'Нужен вход'; title = 'Откройте админку из Telegram'; text = 'Напишите боту в личку «бот админка» и нажмите кнопку «🛠 Открыть админку».'; }
  }
  return `<section class="admin-load load-failed${retry ? '' : ' access'}" role="alert">
    <div class="load-sigil" aria-hidden="true"><span>${icon}</span></div>
    <div class="load-copy"><small>${esc(small)}</small><h2>${esc(title)}</h2><p>${esc(text)}</p></div>
    ${retry ? '<button type="button" class="btn primary load-retry">Повторить</button>' : `<a class="btn" href="${esc(BASE)}/">← В Предвестник</a>`}</section>`;
}
function showLoadError(main, key, error, retry) {
  clearLoadStages(); main.setAttribute('aria-busy', 'false');
  if (error?.status === 401 || error?.status === 403) { $('#main').innerHTML = accessMarkup(error); return; }   // повтор не поможет: нужен вход или роль; закрываем весь экран, не одну вставку
  const timedOut = error?.name === 'AbortError';
  main.innerHTML = `<section class="admin-load load-failed" role="alert">
    <div class="load-sigil" aria-hidden="true"><span>↻</span></div>
    <div class="load-copy"><small>Связь прервалась</small><h2>${timedOut ? 'Сервер отвечает слишком долго' : 'Раздел не загрузился'}</h2>
      <p>${esc(timedOut ? 'Мы остановили ожидание, чтобы экран не завис навсегда.' : (error?.message || 'Попробуйте ещё раз.'))}</p></div>
    <button type="button" class="btn primary load-retry">Повторить</button>
  </section>`;
  main.querySelector('.load-retry').onclick = () => { showSectionLoading(main, key); retry(); };
}
async function loadSectionData(main, path, retry, key = currentSection()) {
  if (_viewAbort) _viewAbort.abort();
  const controller = new AbortController(), request = ++_viewRequest;
  _viewAbort = controller;
  const timeout = setTimeout(() => controller.abort(), 15000);
  try { return await api(path, {signal: controller.signal}); }
  catch (error) {
    if (request !== _viewRequest) return null;
    showLoadError(main, key, error, retry); return null;
  } finally {
    clearTimeout(timeout);
    if (request === _viewRequest) { _viewAbort = null; clearLoadStages(); main.setAttribute('aria-busy', 'false'); }
  }
}

// Раздел может нарисоваться и без loadSectionData (игроки): «занято» снимается, как только заставку заменило содержимое.
new MutationObserver(() => {
  const m = $('#main');
  if (m.getAttribute('aria-busy') === 'true' && !m.querySelector('.admin-load:not(.load-failed)')) m.setAttribute('aria-busy', 'false');
}).observe($('#main'), {childList: true});

async function api(path, opts = {}) {
  const headers = {'content-type': 'application/json'};
  if (INIT) headers['x-init-data'] = INIT;
  try { const s = localStorage.getItem('pv_sess'); if (s) headers['x-session-token'] = s; } catch (_) {}
  const res = await fetch(`${BASE}/bot-admin/api${path}`, {...opts, headers});
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw Object.assign(new Error((data && data.detail) || `Ошибка ${res.status}`), {status: res.status});
  return data;
}

function toast(text, bad = false) {
  const t = $('#toast');
  t.textContent = text;
  t.className = 'toast' + (bad ? ' bad' : '');
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 3200);
}

// Копирование в буфер: современный API, а где он закрыт (старые WebView) — через скрытое поле.
async function copyText(text, done = 'Скопировано') {
  try { await navigator.clipboard.writeText(text); toast(done); return true; } catch (_) {}
  try {
    const field = Object.assign(document.createElement('textarea'), {value: text});
    field.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
    document.body.append(field); field.select();
    const ok = document.execCommand('copy');
    field.remove();
    if (ok) { toast(done); return true; }
  } catch (_) {}
  toast('Не удалось скопировать: выделите текст и скопируйте вручную', true);
  return false;
}

// Значки разделов для нижнего дока (тот же штрих, что у дока Mini App).
const ICONS = {
  people: '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c.7-3.2 3-4.8 5.5-4.8s4.8 1.6 5.5 4.8M16 5.5a3 3 0 0 1 0 5.8M17.5 14.6c1.8.5 3 2 3.5 4.4"/>',
  reports: '<path d="M5.5 21V4M5.5 5h11l-2 3.5 2 3.5h-11"/>',
  metrics: '<path d="M4.5 20v-7h4.5v7M9.8 20V5h4.4v15M15 20v-9.5h4.5V20"/>',
  journal: '<path d="M5 5.5h14M5 10.5h14M5 15.5h9M5 20.5h6"/>',
  broadcast: '<path d="M4 10v4h3l7 4V6l-7 4zM17 9.5a3.5 3.5 0 0 1 0 5"/>',
  promo: '<path d="M3.5 12.5v-8h8l9 9-8 8z"/><circle cx="8" cy="9" r="1.2"/>',
  switches: '<rect x="3" y="7" width="18" height="10" rx="5"/><circle cx="16" cy="12" r="2.4"/>',
  settings: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  health: '<path d="M3 12h4l2.5-6 4 12 2.5-6H21"/>',
  more: '<circle cx="6" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="18" cy="12" r="1.2"/>',
};
const icon = key => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[key] || ICONS.more}</svg>`;
const SHORT = {people: 'Игроки', reports: 'Жалобы', metrics: 'Метрики', journal: 'Журнал', broadcast: 'Рассылка', promo: 'Коды', switches: 'Функции', settings: 'Настройки', health: 'Состояние'};
const DOCK_MAX = 5;   // как в Mini App: пять мест, лишнее в «Ещё»

function dockSplit() {
  const all = ME.sections;
  return all.length <= DOCK_MAX ? {main: all, rest: []} : {main: all.slice(0, DOCK_MAX - 1), rest: all.slice(DOCK_MAX - 1)};
}

// Значки на вкладках: пока только число новых жалоб. Обновляются раз в минуту и после действий с жалобами.
let BADGES = {};
function paintBadges() {
  document.querySelectorAll('#tabs .nb[data-tab]').forEach(b => {
    const n = BADGES[b.dataset.tab] || 0;
    let dot = b.querySelector('.badge');
    if (!n) { if (dot) dot.remove(); return; }
    if (!dot) { dot = document.createElement('i'); dot.className = 'badge'; b.append(dot); }
    dot.textContent = n > 99 ? '99+' : n;
  });
}
async function refreshBadges() {
  try { BADGES = await api('/badges'); } catch (_) { return; }
  paintBadges();
}

function tabs(active) {
  CURRENT = active;
  const {main, rest} = dockSplit(), nav = $('#tabs');
  const inRest = rest.some(s => s.key === active);
  const slots = main.length + (rest.length ? 1 : 0);
  nav.hidden = false;
  nav.style.setProperty('--nav-n', slots);
  nav.style.setProperty('--nav-i', Math.max(0, inRest ? main.length : main.findIndex(s => s.key === active)));
  nav.innerHTML = main.map(s =>
    `<button type="button" class="nb ${s.key === active ? 'on' : ''}" data-tab="${s.key}">${icon(s.key)}<span>${esc(SHORT[s.key] || s.title)}</span></button>`).join('')
    + (rest.length ? `<button type="button" class="nb ${inRest ? 'here' : ''}" data-more="1">${icon('more')}<span>Ещё</span></button>` : '');
  paintBadges();
}

function moreSheet() {
  const {rest} = dockSplit(), box = $('#sheet'), active = currentSection();
  box.innerHTML = `<div class="sheet"><h3>Разделы</h3><div class="go-list">${rest.map(s =>
    `<button type="button" data-go="${s.key}" class="${s.key === active ? 'here' : ''}">${icon(s.key)}<span>${esc(s.title)}</span></button>`).join('')}</div></div>`;
  box.hidden = false;
  box.onclick = e => {
    const go = e.target.closest('[data-go]');
    if (go || e.target === box) { box.hidden = true; box.innerHTML = ''; }
    if (go) open(go.dataset.go);
  };
}

// Кнопка «назад» на верхнем уровне ведёт обратно в Предвестник (внутри Telegram и в браузере одинаково).
function goApp() { location.href = (BASE || '') + '/'; }
function rootBack() {
  const bb = TG && TG.BackButton;
  if (!bb) return;
  if (PEOPLE.bb) { bb.offClick(PEOPLE.bb); PEOPLE.bb = null; }
  bb.offClick(goApp); bb.onClick(goApp); bb.show();
}

function open(key) {
  rootBack();
  if (_viewAbort) { _viewRequest++; _viewAbort.abort(); _viewAbort = null; }
  tabs(key);
  try { localStorage.setItem('pv_admin_tab', key); } catch (_) {}
  const render = SECTIONS[key];
  showSectionLoading($('#main'), key);
  if (render) render($('#main'));
}

document.addEventListener('click', e => {
  const tab = e.target.closest('[data-tab]');
  if (tab) { open(tab.dataset.tab); return; }
  if (e.target.closest('[data-more]')) moreSheet();
});

// ── Тема: тёмная (как Mini App), светлая или как в Telegram ─────────────────────

const THEMES = [['auto', '📱 Как в Telegram', 'Сама меняется вслед за темой Telegram'], ['dark', '🌙 Тёмная', 'Как в Предвестнике'], ['light', '☀️ Светлая', 'Для яркого дня']];
const PAGE_COLOR = {dark: '#08090c', light: '#f3f4f8'};
const themePref = () => { const t = PREFS.get('theme', 'auto'); return THEMES.some(z => z[0] === t) ? t : 'auto'; };
function resolveTheme(pref = themePref()) {
  if (pref === 'light' || pref === 'dark') return pref;
  // Вне Telegram SDK всегда отвечает «light», поэтому его схему берём только когда мы действительно внутри Telegram
  const scheme = TG && TG.platform && TG.platform !== 'unknown' ? TG.colorScheme : '';
  if (scheme === 'light' || scheme === 'dark') return scheme;
  return window.matchMedia && matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}
// Шапка, фон и нижняя полоса Telegram того же цвета, что страница.
function paintTmaShell(color) {
  if (!TG) return;
  const call = (method, since) => { try { if (TG[method] && (!TG.isVersionAtLeast || TG.isVersionAtLeast(since))) TG[method](color); } catch (_) {} };
  call('setHeaderColor', '6.1'); call('setBackgroundColor', '6.1'); call('setBottomBarColor', '7.10');
}
function applyTheme() {
  const theme = resolveTheme();
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name=theme-color]');
  if (meta) meta.setAttribute('content', PAGE_COLOR[theme]);
  paintTmaShell(PAGE_COLOR[theme]);
}
function themeSheet() {
  const current = themePref();
  sheet('Оформление', `<div class="go-list">${THEMES.map(([key, title, sub]) =>
    `<button type="button" data-theme-pick="${key}" class="${key === current ? 'here' : ''}"><span>${title}<small class="sub" style="display:block">${sub}</small></span></button>`).join('')}</div>
    <div class="sub" style="margin-top:8px">Хранится на этом устройстве.</div>`, 'Готово', () => {}, {info: true});
  $('#sheet').querySelectorAll('[data-theme-pick]').forEach(btn => btn.onclick = () => {
    PREFS.set('theme', btn.dataset.themePick); applyTheme();
    $('#sheet').querySelectorAll('[data-theme-pick]').forEach(b => b.classList.toggle('here', b === btn));
  });
}
applyTheme();
try { if (TG && TG.onEvent) TG.onEvent('themeChanged', () => { if (themePref() === 'auto') applyTheme(); }); } catch (_) {}
try { if (window.matchMedia) matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { if (themePref() === 'auto') applyTheme(); }); } catch (_) {}

// Оболочка Telegram: смахивание вниз не закрывает админку посреди формы; лёгкий отклик на нажатия, как в приложении.
(function initTmaShell() {
  if (!TG) return;
  try { if (TG.disableVerticalSwipes) TG.disableVerticalSwipes(); } catch (_) {}
  document.addEventListener('click', e => {
    const t = e.target.closest('.nb, .btn');
    if (!t || t.disabled) return;
    try { const h = TG.HapticFeedback; if (h) { t.classList.contains('nb') ? h.selectionChanged() : h.impactOccurred(t.classList.contains('primary') ? 'medium' : 'light'); } } catch (_) {}
  }, true);
})();

// ── Горячие клавиши (компьютер) ───────────────────────────────────────────────

const GO_KEYS = {p: 'people', r: 'reports', m: 'metrics', j: 'journal', b: 'broadcast', c: 'promo', f: 'switches', s: 'settings', h: 'health'};
const HOTKEYS = [['/', 'Искать: игроки и чаты, промокоды'], ['g, затем p', 'Игроки'], ['g, затем r', 'Жалобы'], ['g, затем m', 'Метрики'], ['g, затем j', 'Журнал'],
  ['g, затем b', 'Рассылка'], ['g, затем c', 'Промокоды'], ['g, затем f', 'Функции'], ['g, затем s', 'Настройки'], ['g, затем h', 'Состояние'],
  ['Esc', 'Закрыть окно, убрать курсор из поля, вернуться назад'], ['Ctrl + Enter', 'Подтвердить окно'], ['?', 'Эта подсказка']];
function hotkeysSheet() {
  const mine = key => !/^g, /.test(key) || ME.sections.some(z => z.key === GO_KEYS[key.slice(-1)]);
  sheet('Горячие клавиши', `<div class="keys">${HOTKEYS.filter(([key]) => mine(key)).map(([key, text]) =>
    `<div><kbd>${esc(key)}</kbd><span>${esc(text)}</span></div>`).join('')}</div>`, 'Понятно', () => {}, {info: true});
}
(function initHotkeys() {
  if (!(window.matchMedia && matchMedia('(pointer: fine)').matches)) return;   // на телефоне клавиатуры нет
  let goAt = 0;
  const closeSheet = () => { const box = $('#sheet'); box.hidden = true; box.innerHTML = ''; };
  const focusSearch = () => {
    const field = $('#pplq') || $('#pq');
    if (field) { field.focus(); field.select(); return true; }
    return false;
  };
  document.addEventListener('keydown', e => {
    if (!ME || e.metaKey || e.altKey) return;
    const sheetOpen = !$('#sheet').hidden;
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName || '') || e.target.isContentEditable;
    if (e.key === 'Enter' && e.ctrlKey && sheetOpen) {
      const ok = $('#sok');
      if (ok && !ok.disabled) { e.preventDefault(); ok.click(); }
      return;
    }
    if (e.key === 'Escape') {
      if (sheetOpen) { e.preventDefault(); closeSheet(); }
      else if (typing) e.target.blur();
      else { const back = $('#pback'); if (back) { e.preventDefault(); back.click(); } }
      return;
    }
    if (typing || e.ctrlKey || sheetOpen) return;
    if (goAt && Date.now() - goAt < 1500) {
      goAt = 0;
      const key = GO_KEYS[e.key.toLowerCase()];
      if (key && ME.sections.some(z => z.key === key)) { e.preventDefault(); open(key); }
      return;
    }
    if (e.key === 'g') { goAt = Date.now(); return; }
    if (e.key === '/') {
      e.preventDefault();
      if (!focusSearch() && ME.sections.some(z => z.key === 'people')) { open('people'); setTimeout(focusSearch, 500); }
    } else if (e.key === '?') { e.preventDefault(); hotkeysSheet(); }
  });
})();

// ── Игроки и чаты: поиск, карточки, действия ─────────────────────────────────

const who = (id, username) => username ? '@' + esc(username) : 'id' + id;
// Тег игрока в чате (подпись справа от имени в Telegram): после имени серым, пусто если тега нет
const tagSfx = tag => tag ? ` <span class="sub tag">[${esc(tag)}]</span>` : '';
const PEOPLE = {query: '', filter: '', stack: [], select: false, picked: new Set()};   // stack — откуда пришли (для «Назад»)
const PEOPLE_FILTERS = [['', 'Все'], ['vip', '👑 VIP'], ['banned', '⛔ С баном'], ['warned', '⚠️ С варнами'],
  ['new', '🌱 Новые за 7 дней'], ['watch', '👁 На контроле'], ['staff', '🎖 Персонал']];

function sheet(title, body, submitText, onSubmit, {info = false, cancelText = 'Отмена'} = {}) {
  const box = $('#sheet');
  box.innerHTML = `<div class="sheet"><h3>${esc(title)}</h3>${body}
    <div class="actions" style="margin-top:12px"><button class="btn primary" id="sok">${esc(submitText)}</button>
      ${info ? '' : `<button class="btn" id="scancel">${esc(cancelText)}</button>`}</div></div>`;
  box.hidden = false;
  const close = () => { box.hidden = true; box.innerHTML = ''; };
  if (!info) $('#scancel').onclick = close;
  box.onclick = e => { if (e.target === box) close(); };
  $('#sok').onclick = async () => {
    $('#sok').disabled = true;
    try { if (await onSubmit(box) !== 'keep') close(); } catch (e) { toast(e.message, true); $('#sok').disabled = false; }
  };
}

const DURATIONS = [[15, '15 минут'], [60, '1 час'], [1440, '1 день'], [10080, '7 дней'], [43200, '30 дней'], [0, 'навсегда']];
const durationField = (def = 60) => `<div class="field"><label>Срок</label><select id="fmin">
  ${DURATIONS.map(([m, t]) => `<option value="${m}" ${m === def ? 'selected' : ''}>${t}</option>`).join('')}</select></div>`;
const hint = text => `<div class="sub hint">${text}</div>`;   // короткое пояснение над полями: что произойдёт
const reasonField = (required = false) => `<div class="field"><label>Причина${required ? '' : ' (необязательно)'}</label>
  <input id="freason" maxlength="200"/></div>`;

// Форма под каждое действие: поля + что отправить.
function actionForm(key, ctx) {
  const v = id => ($('#' + id) || {}).value;
  switch (key) {
    case 'warn': return [hint('Варн действует выбранный срок. Когда варнов станет столько, сколько стоит в лимите чата, бот напишет об этом в чат.') + durationField(10080) + reasonField(), () => ({minutes: +v('fmin'), reason: v('freason')})];
    case 'mute': return [hint('Игрок не сможет писать в этом чате до конца срока. Раньше можно снять кнопкой «Снять мут».') + durationField(60) + reasonField(), () => ({minutes: +v('fmin'), reason: v('freason')})];
    case 'ban': return [hint('Игрока уберут из этого чата, вернуться он не сможет. Снимается кнопкой «Снять бан в чате».') + durationField(0) + reasonField(), () => ({minutes: +v('fmin'), reason: v('freason')})];
    case 'kick': case 'global_ban': return [hint(key === 'kick' ? 'Игрок выйдет из чата, но сможет вернуться по ссылке.'
        : 'Бан сразу во всех чатах, где есть бот и у него есть права. Снимается кнопкой «Снять бан во всех чатах». Понадобится ввести ID игрока.') + reasonField(), () => ({reason: v('freason')})];
    case 'block': return [hint('Бот перестанет отвечать игроку и считать его команды. В чатах он остаётся и может писать.') + `<div class="field"><label>На сколько</label><select id="fdays">
        <option value="1">1 день</option><option value="7">7 дней</option><option value="30">30 дней</option>
        <option value="0" selected>пока не снимут</option></select></div>` + reasonField(),
      () => ({days: +v('fdays'), reason: v('freason')})];
    case 'balance': return [hint('Минус спишет. Причина обязательна, она попадёт в журнал. Крупные суммы (от ' + Object.entries(ctx.confirm_rules ? ctx.confirm_rules.balance : {}).map(([c, n]) => `${num(n)} ${({mora: 'мора', diamonds: 'алмазов', essence: 'эссенции', zarniki: 'зарников'})[c] || c}`).join(', ') + ') попросят ввести ID игрока.') + `<div class="grid2"><div class="field"><label>Валюта</label><select id="fcur">
        ${ctx.currencies.map(c => `<option value="${c.code}">${esc(c.title)}</option>`).join('')}</select></div>
        <div class="field"><label>Сумма (минус — списать)</label><input id="famount" inputmode="decimal" placeholder="500 или -500"/></div></div>
        ${reasonField(true)}`,
      () => ({currency: v('fcur'), amount: (v('famount') || '').replace(',', '.').replace(/\s/g, ''), reason: v('freason'),
              request_id: ctx._rid})];
    case 'vip': return [`<div class="field"><label>Дней VIP (добавятся к текущему сроку)</label>
        <input id="fdays" type="number" min="1" max="3650" value="7"/>
        <div class="chips">${[7, 30, 90, 365].map(d => `<span class="chip" onclick="document.getElementById('fdays').value=${d}">${d} дн.</span>`).join('')}</div></div>` + reasonField(),
      () => ({days: +v('fdays'), reason: v('freason'), request_id: ctx._rid})];
    case 'rank': return [hint('Роль открывает разделы админки и права в боте. Выдать можно только роль ниже своей. Понадобится ввести ID игрока.') + `<div class="field"><label>Новая роль</label><select id="frank">
        ${ctx.ranks.map(r => `<option value="${r.rank}" ${r.rank === ctx.rank ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select></div>`
        + reasonField(), () => ({rank: +v('frank'), reason: v('freason')})];
    case 'mark_grant': {
      const have = new Set(ctx.marks.given.map(m => m.id));
      const free = ctx.marks.grantable.filter(m => !have.has(m.id));
      return [`<div class="field"><label>Метка (в профиле — «Регалии»)</label><select id="fmark">
        ${free.map(m => `<option value="${esc(m.id)}">${esc(m.glyph)} ${esc(m.title)} — ${esc(m.desc)}</option>`).join('')}</select></div>`
        + reasonField(true), () => ({mark: v('fmark'), reason: v('freason')})];
    }
    case 'mark_revoke': return [`<div class="field"><label>Какую снять</label><select id="fmark">
        ${ctx.marks.given.map(m => `<option value="${esc(m.id)}">${esc(m.glyph)} ${esc(m.title)}</option>`).join('')}</select></div>`
        + reasonField(true), () => ({mark: v('fmark'), reason: v('freason')})];
    case 'warn_limit': return [hint('Сколько варнов у игрока в этом чате считается пределом: на этом бот напишет в чат.') + `<div class="field"><label>Варнов до наказания</label>
        <input id="fval" type="number" min="1" max="20" value="${ctx.warn_limit || 3}"/></div>`, () => ({value: +v('fval')})];
    case 'message': return [hint('Сообщение сразу уйдёт в чат от имени бота, его увидят все участники.') + `<div class="field"><label>Текст (без разметки)</label><textarea id="ftext" maxlength="3500"></textarea></div>`,
      () => ({text: v('ftext')})];
    default: return ['<div class="sub">Подтвердите действие.</div>', () => ({})];
  }
}

// Опасные действия просят подтверждение с итогом: кому, что именно и что изменится.
const DANGEROUS = new Set(['ban', 'kick', 'global_ban', 'block', 'balance', 'rank', 'vip', 'leave', 'message', 'close', 'revoke_sessions']);
// Самое опасное (бан во всех чатах, роль, крупная сумма) подтверждается ещё и вводом ID игрока: сервер без него откажет.
function needsTypedConfirm(key, payload, ctx) {
  const rules = ctx.confirm_rules;
  if (!rules || ctx.id === undefined || ctx.username === undefined) return false;
  if (rules.actions.includes(key)) return true;
  const limit = key === 'balance' ? rules.balance[payload.currency] : undefined;
  return limit !== undefined && Math.abs(parseFloat(payload.amount)) >= limit;
}
const CONFIRM_TITLE = {ban: '⛔ Бан в чате', kick: '👢 Кик из чата', global_ban: '🚫 Бан во всех чатах', block: '🙈 Бот перестанет отвечать',
  balance: '💰 Изменение баланса', rank: '🎖 Новая глобальная роль', vip: '👑 Выдача VIP', leave: '🚪 Бот уйдёт из чата',
  message: '📣 Сообщение от бота в чат', close: '🔒 Чат закроется', revoke_sessions: '🔒 Сессии админки завершатся'};
function confirmLines(key, payload, ctx, extra) {
  const minutes = m => !m ? 'навсегда' : (DURATIONS.find(([v]) => v === m) || [0, m + ' мин'])[1];
  const lines = [];
  const whom = ctx.username !== undefined ? `Игрок: <b>${who(ctx.id, ctx.username)}</b> · ID ${ctx.id} · ${esc(ctx.rank_name || '')}` : '';
  const chat = extra.chat_title ? `Чат: <b>${esc(extra.chat_title)}</b>` : (ctx.title ? `Чат: <b>${esc(ctx.title)}</b>` : '');
  if (whom) lines.push(whom);
  if (chat) lines.push(chat);
  if (key === 'ban') lines.push(`Срок: <b>${minutes(payload.minutes)}</b>. Игрока удалят из чата, обратно он сам не войдёт.`);
  else if (key === 'kick') lines.push('Игрока удалят из чата, вернуться по ссылке он сможет.');
  else if (key === 'global_ban') lines.push('Игрок потеряет доступ <b>во всех чатах бота</b>. Это видно в его карточке, снимается кнопкой «Снять бан во всех чатах».');
  else if (key === 'block') lines.push(`Бот перестанет отвечать игроку: <b>${payload.days ? payload.days + ' дн.' : 'пока не снимут'}</b>.`);
  else if (key === 'balance') {
    const cur = ctx.currencies.find(c => c.code === payload.currency) || {title: payload.currency};
    const now = (ctx.balances || {})[payload.currency], delta = parseFloat(payload.amount);
    lines.push(`${esc(cur.title)}: <b>${delta > 0 ? '+' : ''}${esc(payload.amount)}</b>${now !== undefined && !isNaN(delta) ? ` · было ${num(now)}, станет ${num(Math.round((now + delta) * 100) / 100)}` : ''}`);
  } else if (key === 'rank') lines.push(`Роль: ${esc(ctx.rank_name || '')} → <b>${esc((ctx.ranks.find(r => r.rank === payload.rank) || {}).name || payload.rank)}</b>`);
  else if (key === 'vip') lines.push(`К VIP добавится <b>${payload.days} дн.</b>${ctx.vip ? ` (сейчас осталось ${ctx.vip.days_left})` : ''}`);
  else if (key === 'leave') lines.push('Бот выйдет из чата, обратно его придётся добавлять заново.');
  else if (key === 'message') lines.push(`Текст увидят все участники чата:<blockquote>${esc(payload.text || '')}</blockquote>`);
  else if (key === 'close') lines.push('Участники не смогут писать, пока чат не откроют.');
  else if (key === 'revoke_sessions') lines.push('Сотрудник выйдет из админки на всех устройствах и откроет её заново. Роль не меняется.');
  if (payload.reason) lines.push(`Причина: ${esc(payload.reason)}`);
  return lines;
}

function runAction(action, target, ctx, extra, after) {
  // Один ключ на открытое окно: повторное «Выполнить» после потерянного ответа не начислит дважды.
  ctx._rid = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()) + Math.random();
  const [body, collect] = actionForm(action.key, ctx);
  const place = extra.chat_title ? `<div class="sub" style="margin-bottom:10px">Чат: ${esc(extra.chat_title)}</div>` : '';
  const perform = async payload => {
    const res = await api(target, {method: 'POST', body: JSON.stringify(payload)});
    toast(res.message || 'Готово');
    const keep = window.scrollY;   // после действия карточка перерисовывается: остаёмся на том же месте, а не наверху
    Promise.resolve(after()).then(() => window.scrollTo(0, keep));
  };
  sheet(action.title, place + body, DANGEROUS.has(action.key) ? 'Далее' : 'Выполнить', async () => {
    const payload = {action: action.key, ...collect(), ...(extra.chat_id ? {chat_id: extra.chat_id} : {})};
    if (!DANGEROUS.has(action.key)) return perform(payload);
    const typed = needsTypedConfirm(action.key, payload, ctx);
    sheet(CONFIRM_TITLE[action.key] || action.title, `<div class="sub" style="margin-bottom:8px">Проверьте перед выполнением:</div>
      <div class="confirm">${confirmLines(action.key, payload, ctx, extra).map(l => `<div>${l}</div>`).join('')}</div>
      ${typed ? `<div class="field" style="margin-top:10px"><label>Для подтверждения введите ID игрока: <b>${ctx.id}</b></label>
        <input id="fconfirm" inputmode="numeric" autocomplete="off"/></div>` : ''}`,
      'Подтвердить', () => {
        if (!typed) return perform(payload);
        const typedId = ($('#fconfirm').value || '').trim();
        if (typedId !== String(ctx.id)) throw new Error('ID не совпал: введите ' + ctx.id);
        return perform({...payload, confirm: typedId});
      });
    return 'keep';
  });
}

function back(main) {
  const prev = PEOPLE.stack.pop();
  if (!prev) return peopleSearch(main, PEOPLE.query);
  return prev.type === 'player' ? playerView(main, prev.id, false) : chatView(main, prev.id, false);
}

function backBar(label = '← Назад') {
  return `<div class="bar"><button class="btn" id="pback">${label}</button>
    <button class="btn" id="psearch">🔍 Поиск</button></div>`;
}

// Длинные списки в карточках (чаты игрока, журнал) показываем по 5 строк, остальное по кнопке: страница не растёт на экраны.
function trim(main, keep = 5) {
  main.querySelectorAll('.card').forEach(card => {
    const rows = [...card.children].filter(n => n.matches('.member, .log'));
    if (rows.length <= keep + 1) return;
    rows.slice(keep).forEach(n => { n.hidden = true; });
    const more = document.createElement('button');
    more.className = 'btn small more'; more.textContent = `Показать ещё ${rows.length - keep}`;
    more.onclick = () => { rows.forEach(n => { n.hidden = false; }); more.remove(); };
    card.appendChild(more);
  });
}

// Кнопка «назад» самого Telegram ведёт по карточкам так же, как «← Назад» на странице.
function nativeBack(main) {
  const bb = TG && TG.BackButton;
  if (!bb) return;
  if (PEOPLE.bb) bb.offClick(PEOPLE.bb);
  bb.offClick(goApp);
  PEOPLE.bb = () => back(main);
  bb.onClick(PEOPLE.bb); bb.show();
}

function wireBack(main) {
  trim(main); nativeBack(main);
  window.scrollTo(0, 0);
  $('#pback').onclick = () => back(main);
  $('#psearch').onclick = () => { PEOPLE.stack = []; peopleSearch(main, PEOPLE.query); };
}

function historyCard(items) {
  if (!items.length) return '<div class="card"><h3>Журнал</h3><div class="sub">Пока пусто.</div></div>';
  return `<div class="card"><h3>Журнал</h3>${items.map(x => `
    <div class="log"><div><b>${esc(x.title)}</b> ${esc(x.text)}</div>${x.reason ? `<div class="sub">Причина: ${esc(x.reason)}</div>` : ''}
      <div class="sub">${when(x.at)} · ${x.actor && x.actor.id ? who(x.actor.id, x.actor.username) : 'бот'}
        ${x.chat ? ' · ' + esc(x.chat.title || x.chat.id) : ''}${x.user ? ' · ' + who(x.user.id, x.user.username) + tagSfx(x.user.tag) : ''}</div></div>`).join('')}</div>`;
}

// Массовые действия над выбранными в списке: каждое открывает шторку и шлёт один запрос на всех.
const BULK_TITLES = {watch: '👁 На контроль', unwatch: 'Снять с контроля', unwarn_all: '🧽 Снять варны везде', mark_grant: '🏅 Выдать метку', mark_revoke: '✖️ Снять метку'};
async function bulkRun(action, ids, after) {
  const count = `Игроков: <b>${ids.length}</b>.`;
  const send = async extra => {
    const res = await api('/players/bulk', {method: 'POST', body: JSON.stringify({action, ids, ...extra})});
    toast(res.message);
    if (res.failed.length) {
      sheet('Не всем получилось', `<div class="sub">${esc(res.message)}</div>${res.failed.map(f =>
        `<div class="log"><b>${who(f.id, f.username)}</b><div class="sub">${esc(f.reason)}</div></div>`).join('')}`, 'Понятно', () => {}, {info: true});
    }
    after();
  };
  if (action === 'watch') return sheet(BULK_TITLES[action], `<div class="sub">${count} Они появятся в фильтре «На контроле».</div>${reasonField()}`,
    'Поставить', () => send({reason: ($('#freason') || {}).value}));
  if (action === 'mark_grant' || action === 'mark_revoke') {
    const marks = await api('/marks');
    return sheet(BULK_TITLES[action], `<div class="sub">${count}</div><div class="field"><label>Метка</label><select id="fmark">
      ${marks.items.map(m => `<option value="${esc(m.id)}">${esc(m.glyph)} ${esc(m.title)}</option>`).join('')}</select></div>${reasonField(true)}`,
    action === 'mark_grant' ? 'Выдать' : 'Снять', () => send({mark: $('#fmark').value, reason: ($('#freason') || {}).value}));
  }
  return sheet(BULK_TITLES[action], `<div class="sub">${count} ${action === 'unwarn_all' ? 'Все действующие варны во всех чатах будут сняты.' : 'Они уйдут из фильтра «На контроле».'}</div>`,
    'Выполнить', () => send({}));
}

async function peopleSearch(main, query = '') {
  PEOPLE.query = query;
  if (!PEOPLE.restored) {   // последний выбранный быстрый фильтр возвращается при следующем открытии
    PEOPLE.restored = true;
    const saved = PREFS.get('people.filter', '');
    if (PEOPLE_FILTERS.some(([key]) => key === saved)) PEOPLE.filter = saved;
  }
  rootBack();
  main.innerHTML = `
    <div class="bar"><input id="pplq" placeholder="ID, @ник, имя, тег или название чата" value="${esc(query)}" autocomplete="off"/></div>
    <div class="chips filters" id="pplf"></div>
    <div id="pplbulk"></div>
    <div id="pplres"><div class="empty">Загрузка…</div></div>`;
  let timer;
  if (!(window.matchMedia && matchMedia('(pointer: coarse)').matches)) $('#pplq').focus();   // с клавиатуры сразу печатать; на телефоне клавиатуру без нужды не поднимаем
  $('#pplq').oninput = e => { clearTimeout(timer); timer = setTimeout(() => load(e.target.value), 250); };
  const drawFilters = () => {
    $('#pplf').innerHTML = PEOPLE_FILTERS.map(([key, title]) =>
      `<span class="chip ${key === PEOPLE.filter ? 'ok' : ''}" data-flt="${key}">${esc(title)}</span>`).join('');
  };
  $('#pplf').onclick = e => {
    const c = e.target.closest('[data-flt]');
    if (!c || c.dataset.flt === PEOPLE.filter) return;
    PEOPLE.filter = c.dataset.flt; PREFS.set('people.filter', PEOPLE.filter); drawFilters(); load($('#pplq').value);
  };
  drawFilters();
  const drawBulk = () => {
    const host = $('#pplbulk'); if (!host) return;
    if (!PEOPLE.select) { host.innerHTML = ''; return; }
    const n = PEOPLE.picked.size, can = key => key !== 'mark_grant' && key !== 'mark_revoke' ? true : ME.rank >= 5;
    host.innerHTML = `<div class="card bulkbar"><div class="head" style="display:flex;justify-content:space-between;gap:8px;align-items:baseline">
        <b>Выбрано: ${n}</b><span class="sub">${n ? '<a href="#" id="bkclear">сбросить</a>' : 'Нажимайте на игроков в списке'}</span></div>
      ${n ? `<div class="actions" style="margin-top:8px">${Object.entries(BULK_TITLES).filter(([key]) => can(key)).map(([key, title]) =>
        `<button class="btn small" data-bulk="${key}">${esc(title)}</button>`).join('')}</div>` : ''}</div>`;
    if (n) {
      $('#bkclear').onclick = e => { e.preventDefault(); PEOPLE.picked.clear(); drawBulk(); markPicked(); };
      host.querySelectorAll('[data-bulk]').forEach(b => b.onclick = () => bulkRun(b.dataset.bulk, [...PEOPLE.picked], () => {
        PEOPLE.picked.clear(); drawBulk(); load($('#pplq').value);
      }).catch(err => toast(err.message, true)));
    }
  };
  const markPicked = () => document.querySelectorAll('#pplres [data-player]').forEach(row => {
    const on = PEOPLE.picked.has(+row.dataset.player);
    row.classList.toggle('picked', on);
    const box = row.querySelector('.pick'); if (box) box.checked = on;
  });
  async function load(q) {
    PEOPLE.query = q;
    const host = $('#pplres'); if (!host) return;
    const data = await loadSectionData(host, `/search?q=${encodeURIComponent(q.trim())}${PEOPLE.filter ? '&filter=' + PEOPLE.filter : ''}`, () => load(q), 'people');
    if (!data) return;
    const {players, chats, total} = data;
    const title = (PEOPLE_FILTERS.find(f => f[0] === PEOPLE.filter) || [])[1];
    const head = q.trim() ? '' : `<div class="sub" style="margin-bottom:8px">${PEOPLE.filter ? esc(title) : 'Недавно активные'}</div>`;
    const showAttn = !q.trim() && !PEOPLE.filter;
    const recent = showAttn ? PREFS.get('recent', []) : [];
    const recentHtml = recent.length ? `<div class="chips recent"><span class="sub">Недавно открывали:</span>${recent.map(r =>
      `<span class="chip" data-recent="${r.id}">${r.u ? '@' + esc(r.u) : 'id' + r.id}</span>`).join('')}</div>` : '';
    $('#pplres').innerHTML = recentHtml + (showAttn ? '<div id="pplonb"></div><div id="pplattn"></div>' : '') + head + `
      <h3 class="sec" style="display:flex;justify-content:space-between;align-items:center">
        <span>Игроки · ${players.length}${total > players.length ? ' из ' + num(total) : ''}</span>
        ${players.length ? `<button class="btn small" id="pplsel">${PEOPLE.select ? 'Готово' : 'Выбрать'}</button>` : ''}</h3>
      <div class="list">${players.map(p => `<div class="row" data-player="${p.id}">
        <div class="head"><b>${PEOPLE.select ? `<input type="checkbox" class="pick" aria-label="Выбрать"/> ` : ''}${who(p.id, p.username)}</b>${p.rank_name ? `<span class="chip">${esc(p.rank_name)}</span>` : ''}</div>
        <div class="sub">${p.name ? esc(p.name) + ' · ' : ''}ID ${p.id} · сообщений ${num(p.messages)}${p.last ? ' · был ' + when(p.last) : ''}</div>
        ${p.tags && p.tags.length ? `<div class="chips tags">${p.tags.map(t => `<span class="chip tag">🏷 ${esc(t)}</span>`).join('')}</div>` : ''}</div>`).join('')
        || '<div class="sub">Никого</div>'}</div>
      ${PEOPLE.filter ? '' : `<h3 class="sec">Чаты · ${chats.length}</h3>
      <div class="list">${chats.map(c => `<div class="row" data-chat="${c.id}">
        <div class="head"><b>${esc(c.title)}</b><span class="sub">${num(c.members)} уч.</span></div>
        <div class="sub">ID ${c.id} · сообщений ${num(c.messages)}${c.last ? ' · активность ' + when(c.last) : ''}</div></div>`).join('')
        || '<div class="sub">Ничего</div>'}</div>`}`;
    markPicked(); drawBulk();
    if (showAttn) api('/chats/onboarding').then(f => {
      const host = $('#pplonb');
      if (!host || !f.added) return;
      host.innerHTML = `<div class="card"><h3>🚪 Подключение чатов · ${f.days} дн.</h3>
        <div class="chips"><span class="chip">добавили ${f.added}</span><span class="chip ok">выдали права ${f.ready}</span>
        ${f.waiting ? `<span class="chip warn">ждут прав ${f.waiting}</span>` : ''}${f.gave_up ? `<span class="chip bad">ушли без прав ${f.gave_up}</span>` : ''}</div>
        <button class="btn small more" id="onbmore">Где застревают</button></div>`;
      $('#onbmore').onclick = () => onboardingSheet(f.days).catch(err => toast(err.message, true));
    }).catch(() => {});
    if (showAttn) api('/chats/attention').then(att => {
      const host = $('#pplattn');
      if (!host || !att.total) return;
      host.innerHTML = `<div class="card"><h3>⚠️ Чаты требуют внимания · ${att.total}</h3><div class="list">${attentionRows(att.items.slice(0, 5))}</div>
        ${att.total > 5 ? '<button class="btn small more" id="attnall">Показать все</button>' : ''}</div>`;
      if ($('#attnall')) $('#attnall').onclick = () => attentionSheet('', '⚠️ Чаты требуют внимания').catch(err => toast(err.message, true));
    }).catch(() => {});
    if ($('#pplsel')) $('#pplsel').onclick = () => { PEOPLE.select = !PEOPLE.select; if (!PEOPLE.select) PEOPLE.picked.clear(); load($('#pplq').value); };
  }
  $('#pplres').onclick = e => {
    const rec = e.target.closest('[data-recent]');
    if (rec) { PEOPLE.stack = []; playerView(main, +rec.dataset.recent); return; }
    const p = e.target.closest('[data-player]'), c = e.target.closest('[data-chat]');
    if (p && PEOPLE.select) {   // в режиме выбора нажатие отмечает игрока, а не открывает карточку
      const id = +p.dataset.player;
      if (PEOPLE.picked.has(id)) PEOPLE.picked.delete(id); else PEOPLE.picked.add(id);
      markPicked(); drawBulk();
      return;
    }
    PEOPLE.stack = [];
    if (p) playerView(main, +p.dataset.player);
    else if (c) chatView(main, +c.dataset.chat);
  };
  load(query);
}

async function playerView(main, id, push = true, from = null) {
  const p = await loadSectionData(main, `/player/${id}`, () => playerView(main, id, push, from), 'people');
  if (!p) return;
  PREFS.set('recent', [{id: p.id, u: p.username || ''}, ...PREFS.get('recent', []).filter(r => r.id !== p.id)].slice(0, 6));
  if (push && from) PEOPLE.stack.push(from);
  const reopen = () => playerView(main, id, false);
  const b = p.balances;
  const fam = p.family;
  const chips = [
    `<span class="chip">${esc(p.rank_name)}</span>`,
    p.vip ? `<span class="chip ok">👑 VIP · ${p.vip.days_left} дн.</span>` : '',
    p.sponsor ? '<span class="chip ok">спонсор</span>' : '',
    p.blocked ? `<span class="chip bad">🙈 бот не отвечает${p.blocked.until ? ' до ' + when(p.blocked.until) : ''}</span>` : '',
    p.global_ban ? '<span class="chip bad">🚫 бан во всех чатах</span>' : '',
    p.deleted_at ? '<span class="chip warn">аккаунт удаляется</span>' : '',
    p.watch ? '<span class="chip warn">👁 на контроле</span>' : '',
  ].join(' ');
  // Глобальные действия — без взаимоисключающих пар.
  const hide = new Set([p.blocked ? 'block' : 'unblock', p.global_ban ? 'global_ban' : 'global_unban']);
  if (!p.rank) hide.add('revoke_sessions');   // сессии админки бывают только у сотрудников
  const mk = p.marks || {given: [], earned: [], grantable: []};
  // Метки выдаются и снимаются в своей карточке ниже, а не общими кнопками.
  const canGrant = p.actions.player.find(a => a.key === 'mark_grant'), canRevoke = p.actions.player.find(a => a.key === 'mark_revoke');
  hide.add('mark_grant'); hide.add('mark_revoke');
  const held = new Set(mk.given.map(m => m.id));
  const free = mk.grantable.filter(m => !held.has(m.id));
  const markRow = (m, btn) => `<div class="sw-row"><div class="t"><b>${esc(m.glyph)} ${esc(m.title)}</b><div class="sub">${esc(m.desc || '')}</div></div>${btn}</div>`;
  const marksCard = `<div class="card"><h3>🏅 Метки · в профиле игрока это «Регалии»</h3>
      <h3 class="sec">Выданы · ${mk.given.length}</h3>
      ${mk.given.length ? mk.given.map(m => markRow(m, canRevoke ? `<button class="btn small" data-unmark="${esc(m.id)}">✖️ Снять</button>` : '')).join('')
        : '<div class="sub">Пока ни одной.</div>'}
      ${mk.earned.length ? `<h3 class="sec">Заработаны сами · ${mk.earned.length}</h3><div class="chips">${mk.earned.map(m =>
        `<span class="chip" title="${esc(m.desc)}">${esc(m.glyph)} ${esc(m.title)}</span>`).join('')}</div>
        <div class="sub">Их выдаёт игра, вручную не снимаются.</div>` : ''}
      ${canGrant ? `<h3 class="sec">Выдать · нажмите на метку</h3>${free.length ? `<div class="mark-grid">${free.map(m =>
        `<button type="button" class="mark-tile" data-mark="${esc(m.id)}"><span class="g">${esc(m.glyph)}</span><b>${esc(m.title)}</b><small>${esc(m.desc || '')}</small></button>`).join('')}</div>`
        : '<div class="sub">Все метки уже выданы.</div>'}` : '<div class="sub">Выдавать метки может роль «Разработчик» и выше.</div>'}
    </div>`;
  const rp = p.reports || {total: 0, open: 0, confirmed: 0, last: []};
  const canReports = ME.sections.some(z => z.key === 'reports');
  const reportsCard = `<div class="card"><h3>📨 Жалобы на игрока · ${rp.total}</h3>
      ${rp.total ? `<div class="chips"><span class="chip ${rp.open ? 'warn' : ''}">открытых: ${rp.open}</span><span class="chip ${rp.confirmed ? 'bad' : ''}">подтверждено: ${rp.confirmed}</span></div>
        ${rp.last.map(r => `<div class="log"><div><b>№${r.id}</b> <span class="chip">${esc(r.status_title)}</span> ${esc(r.reason)}</div>
          <div class="sub">${when(r.created_at)} · ${esc(r.chat)}</div></div>`).join('')}
        ${canReports ? '<div class="sub" style="margin-top:6px">Все жалобы — в разделе «Жалобы». Авторов жалоб здесь не видно: жалобы анонимны.</div>' : ''}`
        : '<div class="sub">Жалоб не было.</div>'}</div>`;
  const noteRow = n => `<div class="log" data-note="${n.id}"><div style="white-space:pre-wrap">${esc(n.text)}</div>
      <div class="sub">${when(n.at)} · ${who(n.author.id, n.author.username)}${n.can_remove ? ` · <a href="#" data-rmnote="${n.id}">убрать</a>` : ''}</div></div>`;
  const notesCard = `<div class="card" id="notescard"><h3>📝 Заметки персонала · ${p.notes.total}</h3>
      <div class="sub" style="margin-bottom:6px">Видят только сотрудники, игрок — нет.</div>
      <div id="notelist">${p.notes.items.map(noteRow).join('') || '<div class="sub">Пока нет заметок.</div>'}</div>
      ${p.notes.next ? '<button class="btn small more" id="notemore">Показать ещё</button>' : ''}
      <div class="field" style="margin-top:10px"><textarea id="notetext" maxlength="1000" placeholder="Что важно знать другим модераторам"></textarea></div>
      <div class="actions"><button class="btn small primary" id="noteadd">Добавить заметку</button></div></div>`;
  const NAME_KINDS = {username: '@ник', name: 'имя'};
  const namesCard = p.names.length || p.nicknames.length ? `<div class="card"><h3>🕘 Ники и имена</h3>
      ${p.names.length ? `<div class="sub" style="margin-bottom:4px">Как игрок назывался в Telegram: бот записывает, когда ник или имя меняются.</div>
        ${p.names.map(n => `<div class="log"><b>${esc(n.kind === 'username' ? '@' + n.value : n.value)}</b>
          <div class="sub">${NAME_KINDS[n.kind] || n.kind} · с ${when(n.at)}</div></div>`).join('')}` : ''}
      ${p.nicknames.length ? `<h3 class="sec">Ники в чатах</h3>${p.nicknames.map(n => `<div class="log"><b>${esc(n.nickname)}</b>
        <div class="sub"><a href="#" data-chat="${n.chat.id}">${esc(n.chat.title)}</a></div></div>`).join('')}` : ''}</div>` : '';
  const tagsCard = p.tag_history && p.tag_history.length ? `<div class="card"><h3>🏷 Теги в чатах</h3>
      <div class="sub" style="margin-bottom:4px">Подпись справа от имени в списке участников. Бот записывает, когда тег меняется.</div>
      ${p.tag_history.map(t => `<div class="log"><b>${t.tag ? esc(t.tag) : '— тег убрали —'}</b>
        <div class="sub"><a href="#" data-chat="${t.chat_id}">${esc(t.chat_title || t.chat_id)}</a> · ${when(t.at)}</div></div>`).join('')}</div>` : '';
  const lk = p.linked;
  const linkRow = (u, extra = '') => `<div class="log"><a href="#" data-player="${u.id}"><b>${who(u.id, u.username)}</b></a>${extra ? `<div class="sub">${extra}</div>` : ''}</div>`;
  const linkedCard = lk ? `<div class="card"><h3>🔗 Возможные связи</h3>
      <div class="sub" style="margin-bottom:4px">Совпадение ника или имени — повод присмотреться, а не доказательство. Устройства и адреса бот не собирает.</div>
      ${lk.invited_by ? `<h3 class="sec">Пришёл по приглашению</h3>${linkRow(lk.invited_by)}` : ''}
      ${lk.invited.total ? `<h3 class="sec">Пригласил · ${lk.invited.total}</h3>${lk.invited.items.map(u => linkRow(u)).join('')}
        ${lk.invited.total > lk.invited.items.length ? `<div class="sub">…и ещё ${lk.invited.total - lk.invited.items.length}</div>` : ''}` : ''}
      ${lk.same_username.length ? `<h3 class="sec">Тот же ник раньше или сейчас</h3>${lk.same_username.map(u => linkRow(u, '@' + esc(u.value))).join('')}` : ''}
      ${lk.same_name.length ? `<h3 class="sec">Такое же имя в Telegram</h3>${lk.same_name.map(u => linkRow(u, esc(u.name))).join('')}` : ''}
      ${!lk.invited_by && !lk.invited.total && !lk.same_username.length && !lk.same_name.length ? '<div class="sub">Связей не найдено.</div>' : ''}</div>` : '';
  const globalActs = p.actions.player.filter(a => !hide.has(a.key));
  const memberActs = c => p.actions.member.filter(a =>
    !(a.key === 'mute' && c.muted) && !(a.key === 'unmute' && !c.muted) && !(a.key === 'unban' && !c.ban)
    && !(a.key === 'ban' && c.ban) && !(a.key === 'kick' && (c.left || c.ban)) && !(a.key === 'unwarn_all' && !c.warns));
  main.innerHTML = `${backBar()}
    <div class="card">
      <div class="head" style="display:flex;justify-content:space-between;gap:8px;align-items:baseline">
        <span style="font-size:20px;font-weight:700">${who(p.id, p.username)}</span><span class="sub">ID ${p.id}</span></div>
      ${p.name ? `<div class="sub">${esc(p.name)}</div>` : ''}
      <div class="chips">${chips}</div>
      <div class="stats">
        <div><span>🪙 Мора</span><b>${num(b.mora)}</b></div><div><span>💎 Алмазы</span><b>${num(b.diamonds)}</b></div>
        <div><span>🔮 Эссенция</span><b>${num(b.essence)}</b></div><div><span>✨ Зарники</span><b>${num(b.zarniki)}</b></div>
        <div><span>💬 Сегодня / 7 дней</span><b>${num(p.messages.today)} / ${num(p.messages.week)}</b></div>
        <div><span>💬 Всего</span><b>${num(p.messages.total)}</b></div>
        <div><span>🔥 Стрик</span><b>${p.streak.current} <small>(лучший ${p.streak.best})</small></b></div>
        <div><span>🏆 Достижения</span><b>${p.achievements.count} <small>· ур. ${p.achievements.levels}</small></b></div>
      </div>
      ${fam ? `<div class="sub" style="margin-top:8px">💞 ${fam.partner
          ? `В браке с <a href="#" data-player="${fam.partner}">${who(fam.partner, fam.partner_username)}</a>${fam.since ? ' с ' + new Date(fam.since).toLocaleDateString('ru-RU') : ''}`
          : 'Ребёнок в семье'}${fam.children ? ` · детей: ${fam.children}` : ''}</div>` : ''}
      ${p.blocked && p.blocked.reason ? `<div class="sub">Блокировка: ${esc(p.blocked.reason)}</div>` : ''}
      ${p.global_ban && p.global_ban.reason ? `<div class="sub">Глобальный бан: ${esc(p.global_ban.reason)}</div>` : ''}
      ${p.watch ? `<div class="sub">На контроле: ${p.watch.reason ? esc(p.watch.reason) + ' · ' : ''}${who(p.watch.by.id, p.watch.by.username)}, ${when(p.watch.at)}</div>` : ''}
      <div class="actions" style="margin-top:12px"><button class="btn small" id="pwatch">${p.watch ? '👁 Снять с контроля' : '👁 Поставить на контроль'}</button></div>
      ${globalActs.length ? `<div class="actions" style="margin-top:8px">${globalActs.map(a =>
        `<button class="btn small ${/ban|block/.test(a.key) && !a.key.startsWith('un') && a.key !== 'global_unban' ? 'danger' : ''}" data-act="${a.key}">${esc(a.title)}</button>`).join('')}</div>` : ''}
    </div>
    ${marksCard}
    ${reportsCard}
    ${notesCard}
    ${namesCard}
    ${tagsCard}
    ${linkedCard}
    <div class="card"><h3>Чаты · ${p.chats.length}</h3>
      ${p.chats.map(c => `<div class="member">
        <div class="head"><a href="#" data-chat="${c.id}"><b>${esc(c.title)}</b></a><span class="sub">${esc(c.rank_name)}</span></div>
        <div class="sub">сообщений ${num(c.messages)}${c.last ? ' · ' + when(c.last) : ''}</div>
        <div class="chips">${c.tag ? `<span class="chip tag" title="Тег в этом чате">🏷 ${esc(c.tag)}</span>` : ''}${c.left ? '<span class="chip off">не в чате</span>' : ''}
          ${c.muted ? `<span class="chip warn">🔇 мут${c.muted_until ? ' до ' + when(c.muted_until) : ' навсегда'}</span>` : ''}
          ${c.ban ? `<span class="chip bad">⛔ бан${c.ban.until ? ' до ' + when(c.ban.until) : ''}</span>` : ''}
          ${c.warns ? `<span class="chip warn">⚠️ варнов: ${c.warns}</span>` : ''}</div>
        ${memberActs(c).length ? `<div class="actions">${memberActs(c).map(a =>
          `<button class="btn small" data-mact="${a.key}" data-cid="${c.id}" data-ctitle="${esc(c.title)}">${esc(a.title)}</button>`).join('')}</div>` : ''}
      </div>`).join('') || '<div class="sub">Не писал ни в одном чате с ботом.</div>'}
    </div>
    ${historyCard(p.history)}`;
  wireBack(main);
  const here = {type: 'player', id};
  $('#pwatch').onclick = () => {
    const done = on => async reason => {
      await api(`/player/${id}/watch`, {method: 'POST', body: JSON.stringify({on, reason})});
      toast(on ? 'Игрок на контроле' : 'Снят с контроля');
      reopen();
    };
    if (p.watch) done(false)('').catch(err => toast(err.message, true));
    else sheet('👁 На контроль', `<div class="sub">Игрок: ${who(p.id, p.username)}. Он об этом не узнает, ограничений нет: список для персонала.</div>${reasonField()}`,
      'Поставить', () => done(true)(($('#freason') || {}).value));
  };
  main.querySelectorAll('[data-act]').forEach(btn => btn.onclick = () =>
    runAction(p.actions.player.find(a => a.key === btn.dataset.act), `/player/${id}/action`, p, {}, reopen));
  const markSheet = (action, m) => sheet(`${action === 'mark_grant' ? 'Выдать' : 'Снять'} метку`, `
      <div class="mark-tile" style="pointer-events:none;margin-bottom:10px"><span class="g">${esc(m.glyph)}</span><b>${esc(m.title)}</b><small>${esc(m.desc || '')}</small></div>
      <div class="sub" style="margin-bottom:8px">Игрок: ${who(p.id, p.username)}</div>${reasonField(true)}`,
    action === 'mark_grant' ? 'Выдать' : 'Снять', async () => {
      const res = await api(`/player/${id}/action`, {method: 'POST', body: JSON.stringify({action, mark: m.id, reason: ($('#freason') || {}).value})});
      toast(res.message || 'Готово');
      const keep = window.scrollY; Promise.resolve(reopen()).then(() => window.scrollTo(0, keep));
    });
  // Заметки: добавить, убрать, «Показать ещё».
  const drawNotes = (data, append = false) => {
    const list = $('#notelist');
    list.innerHTML = (append ? list.innerHTML : '') + (data.items.map(noteRow).join('') || (append ? '' : '<div class="sub">Пока нет заметок.</div>'));
    $('#notescard h3').textContent = `📝 Заметки персонала · ${data.total}`;
    const more = $('#notemore');
    if (more) { if (data.next) more.dataset.next = data.next; else more.remove(); }
    else if (data.next) $('#notelist').insertAdjacentHTML('afterend', '<button class="btn small more" id="notemore">Показать ещё</button>');
    if ($('#notemore')) { $('#notemore').dataset.next = data.next || ''; $('#notemore').onclick = loadMoreNotes; }
  };
  const loadMoreNotes = async () => drawNotes(await api(`/player/${id}/notes?offset=${$('#notemore').dataset.next}`), true);
  if ($('#notemore')) { $('#notemore').dataset.next = p.notes.next; $('#notemore').onclick = loadMoreNotes; }
  $('#noteadd').onclick = async e => {
    const btn = e.currentTarget, text = $('#notetext').value.trim();
    if (!text) return toast('Напишите текст заметки', true);
    if (btn.disabled) return;
    btn.disabled = true;   // двойной клик не должен создавать две одинаковые заметки
    try { drawNotes(await api(`/player/${id}/notes`, {method: 'POST', body: JSON.stringify({text})})); $('#notetext').value = ''; toast('Заметка добавлена'); }
    catch (err) { toast(err.message, true); }
    finally { btn.disabled = false; }
  };
  $('#notescard').onclick = async e => {
    const a = e.target.closest('[data-rmnote]');
    if (!a) return;
    e.preventDefault();
    try { drawNotes(await api(`/player/${id}/notes/${a.dataset.rmnote}`, {method: 'DELETE'})); toast('Заметка убрана'); }
    catch (err) { toast(err.message, true); }
  };
  main.querySelectorAll('[data-mark]').forEach(b => b.onclick = () => markSheet('mark_grant', mk.grantable.find(m => m.id === b.dataset.mark)));
  main.querySelectorAll('[data-unmark]').forEach(b => b.onclick = () => markSheet('mark_revoke', mk.given.find(m => m.id === b.dataset.unmark)));
  main.querySelectorAll('[data-mact]').forEach(btn => btn.onclick = () =>
    runAction(p.actions.member.find(a => a.key === btn.dataset.mact), `/player/${id}/action`, p,
      {chat_id: +btn.dataset.cid, chat_title: btn.dataset.ctitle}, reopen));
  main.querySelectorAll('a[data-chat]').forEach(a => a.onclick = e => { e.preventDefault(); chatView(main, +a.dataset.chat, true, here); });
  main.querySelectorAll('a[data-player]').forEach(a => a.onclick = e => { e.preventDefault(); playerView(main, +a.dataset.player, true, here); });
}

// Настройки чата одним взглядом: кто что может, чистка, модули и флаги. Меняются командами в самом чате и в «Функциях».
function chatSettingsCard(st) {
  if (!st || !st.ranks) return '';
  const flag = (title, on) => `<span class="chip ${on ? 'ok' : 'off'}">${on ? '✓' : '✕'} ${esc(title)}</span>`;
  return `<div class="card"><h3>⚙️ Настройки чата</h3>
    <h3 class="sec">Кто что может (с какого ранга в чате)</h3>
    ${st.ranks.map(r => `<div class="sw-row"><div class="t">${esc(r.title)}</div><span class="sub">${esc(r.name)}</span></div>`).join('')}
    <h3 class="sec">Чистка</h3>
    <div class="sub">${st.purge.on ? 'Включена' : 'Выключена'} · запускает ${esc(st.purge.min_rank)} · действия с ${esc(st.purge.action_rank)}</div>
    ${st.shield_days ? `<div class="sub">Защита от чистки длится ${st.shield_days} дн.</div>` : ''}
    <h3 class="sec">Модули чата</h3><div class="chips">${st.modules.map(m => flag(m.icon + ' ' + m.name, m.on)).join('')}</div>
    <h3 class="sec">Прочее</h3><div class="chips">${st.flags.map(f => flag(f.title, f.on)).join('')}</div></div>`;
}

// Чаты, где что-то не так: бот без прав, тихо 30 дней, бота удалили.
function attentionRows(items) {
  const cls = {no_rights: 'warn', quiet: 'off', left: 'bad'};
  return items.map(x => `<div class="row" data-chat="${x.id}">
    <div class="head"><b>${esc(x.title)}</b><span class="sub">${num(x.members)} уч.</span></div>
    <div class="chips" style="margin-top:4px">${x.problems.map(p => `<span class="chip ${cls[p.key] || ''}">${esc(p.title)}</span>`).join('')}</div>
    <div class="sub">${x.last ? 'последнее сообщение ' + when(x.last) : 'сообщений не было'}</div></div>`).join('');
}
// Воронка подключения: шаги, на которых люди нажимали кнопки мастера, и чаты, где бота так и не сделали админом.
async function onboardingSheet(days) {
  const f = await api(`/chats/onboarding?days=${days}`);
  const stuck = f.stuck.map(x => `<div class="row" data-chat="${x.id}"><div class="head"><b>${esc(x.title)}</b>
    <span class="sub">${x.reminders ? 'напоминаний: ' + x.reminders : 'без напоминаний'}</span></div>
    <div class="sub">добавили ${when(x.added_at)}${x.inviter ? ' · ' + who(x.inviter.id, x.inviter.username) : ''}</div></div>`).join('');
  sheet(`🚪 Подключение чатов · ${f.days} дн.`,
    `<div class="list">${f.events.map(e => `<div class="row"><div class="head"><b>${esc(e.title)}</b>
      <span class="sub">${num(e.count)} раз · чатов ${num(e.chats)}</span></div></div>`).join('') || '<div class="sub">Пока никто не подключал бота.</div>'}</div>
      ${stuck ? `<h3 class="sec">Ждут прав · ${f.waiting}</h3><div class="list">${stuck}</div>` : ''}`,
    'Закрыть', () => {}, {info: true});
  $('#sheet').querySelectorAll('[data-chat]').forEach(r => r.onclick = () => goChat(+r.dataset.chat));
}
function goChat(id) {
  const box = $('#sheet'); box.hidden = true; box.innerHTML = '';
  open('people'); PEOPLE.stack = []; chatView($('#main'), id);
}
async function attentionSheet(kind, title) {
  const data = await api(`/chats/attention?kind=${kind}`);
  sheet(title, data.items.length ? `<div class="list">${attentionRows(data.items)}</div>${data.total > data.items.length ? `<div class="sub" style="margin-top:8px">Показаны ${data.items.length} из ${data.total}: самые людные.</div>` : ''}`
    : '<div class="sub">Таких чатов нет.</div>', 'Закрыть', () => {}, {info: true});
  $('#sheet').querySelectorAll('[data-chat]').forEach(r => r.onclick = () => goChat(+r.dataset.chat));
}

async function chatView(main, id, push = true, from = null) {
  const c = await loadSectionData(main, `/chat/${id}`, () => chatView(main, id, push, from), 'people');
  if (!c) return;
  if (push && from) PEOPLE.stack.push(from);
  const reopen = () => chatView(main, id, false);
  const m = c.messages;
  const acts = c.actions.chat.filter(a => !(a.key === 'close' && c.closed) && !(a.key === 'open' && !c.closed));
  const can = key => c.actions.member.find(a => a.key === key);
  const person = x => `<a href="#" data-player="${x.user}">${who(x.user, x.username)}</a>${tagSfx(x.tag)}`;
  const sanctionRow = (x, line, undo) => `<div class="sw-row"><div class="t">${person(x)}<div class="sub">${line(x)}</div></div>
      ${can(undo) ? `<button class="btn small" data-undo="${undo}" data-uid="${x.user}">${esc(can(undo).title)}</button>` : ''}</div>`;
  const SANCTIONS = {
    bans: ['⛔ Баны', x => (x.until ? 'до ' + when(x.until) : 'навсегда') + (x.reason ? ' · ' + esc(x.reason) : ''), 'unban'],
    mutes: ['🔇 Муты', x => x.until ? 'до ' + when(x.until) : 'навсегда', 'unmute'],
    warns: ['⚠️ Варны', x => 'действующих: ' + x.count, 'unwarn_all'],
  };
  const sanction = kind => {
    const list = c.sanctions[kind], [title, line, undo] = SANCTIONS[kind];
    return list.total ? `<div data-kind="${kind}"><h3 class="sec">${title} · ${list.total}</h3><div class="srows">${list.items.map(x => sanctionRow(x, line, undo)).join('')}</div>
      ${list.next ? `<button class="btn small more" data-more="${kind}" data-next="${list.next}">Показать ещё</button>` : ''}</div>` : '';
  };
  const s = c.sanctions;
  main.innerHTML = `${backBar()}
    <div class="card">
      <div class="head" style="display:flex;justify-content:space-between;gap:8px;align-items:baseline">
        <span style="font-size:20px;font-weight:700">${esc(c.title)}</span><span class="sub">ID ${c.id}</span></div>
      <div class="chips">${c.closed ? '<span class="chip warn">🔒 закрыт</span>' : '<span class="chip ok">открыт</span>'}
        ${c.bot && c.bot.left_at ? `<span class="chip bad">бота удалили · ${when(c.bot.left_at)}</span>` : c.bot && c.bot.can_moderate === false ? '<span class="chip warn">у бота нет прав модерации</span>' : ''}
        <span class="chip">⚠️ лимит варнов ${c.warn_limit}</span>
        ${c.tagged ? `<span class="chip" title="Участников с тегом: бот видит его в каждом сообщении">🏷 с тегом: ${c.tagged}</span>` : ''}
        ${c.switched_off.length ? `<span class="chip warn">выключено функций: ${c.switched_off.length}</span>` : ''}</div>
      <div class="sub" style="margin-top:8px">Владелец: ${c.owner ? `<a href="#" data-player="${c.owner.id}">${who(c.owner.id, c.owner.username)}</a>` : 'неизвестен'}
        ${c.admin_chat ? ` · админ-чат: <a href="#" data-chat="${c.admin_chat.id}">${esc(c.admin_chat.title)}</a>` : ''}</div>
      <div class="stats">
        <div><span>👥 Участников</span><b>${num(c.members)}</b></div><div><span>💬 Всего</span><b>${num(m.total)}</b></div>
        <div><span>Сегодня</span><b>${num(m.today.messages)} <small>· ${m.today.active} чел.</small></b></div>
        <div><span>7 дней</span><b>${num(m.week.messages)} <small>· ${m.week.active} чел.</small></b></div>
        <div><span>30 дней</span><b>${num(m.month.messages)} <small>· ${m.month.active} чел.</small></b></div>
      </div>
      <div class="actions" style="margin-top:12px">${acts.map(a =>
        `<button class="btn small ${a.key === 'leave' ? 'danger' : ''}" data-act="${a.key}">${esc(a.title)}</button>`).join('')}
        ${ME.sections.some(x => x.key === 'switches') ? '<button class="btn small" id="cswitch">⚙️ Функции чата</button>' : ''}</div>
      ${c.switched_off.length ? `<div class="sub" style="margin-top:8px">Выключено: ${c.switched_off.map(x =>
        esc(x.title) + (x.reason ? ` («${esc(x.reason)}»)` : '')).join(', ')}</div>` : ''}
    </div>
    ${chatSettingsCard(c.settings)}
    <div class="card"><h3>Самые активные</h3>${c.top.map((x, i) => `<div class="sw-row"><div class="t">${i + 1}. ${person({user: x.id, username: x.username, tag: x.tag})}</div>
      <span class="sub">${num(x.messages)}</span></div>`).join('') || '<div class="sub">Пока никого.</div>'}</div>
    ${s.bans.total || s.mutes.total || s.warns.total ? `<div class="card" id="sanctions">${sanction('bans')}${sanction('mutes')}${sanction('warns')}</div>` : ''}
    ${historyCard(c.history)}`;
  wireBack(main);
  const here = {type: 'chat', id};
  main.querySelectorAll('[data-act]').forEach(btn => btn.onclick = () =>
    runAction(c.actions.chat.find(a => a.key === btn.dataset.act), `/chat/${id}/action`, c, {}, reopen));
  const wirePlayers = () => main.querySelectorAll('a[data-player]').forEach(a => a.onclick = e => { e.preventDefault(); playerView(main, +a.dataset.player, true, here); });
  const wireUndo = () => main.querySelectorAll('[data-undo]').forEach(btn => btn.onclick = () =>
    runAction(can(btn.dataset.undo), `/player/${btn.dataset.uid}/action`, c, {chat_id: id, chat_title: c.title}, reopen));
  wireUndo(); wirePlayers();
  main.querySelectorAll('a[data-chat]').forEach(a => a.onclick = e => { e.preventDefault(); chatView(main, +a.dataset.chat, true, here); });
  main.querySelectorAll('[data-more]').forEach(btn => btn.onclick = async () => {   // «Показать ещё»: следующая страница списка
    const kind = btn.dataset.more, [, line, undo] = SANCTIONS[kind];
    btn.disabled = true;
    try {
      const page = await api(`/chat/${id}/sanctions?kind=${kind}&offset=${btn.dataset.next}`);
      btn.closest('[data-kind]').querySelector('.srows').insertAdjacentHTML('beforeend', page.items.map(x => sanctionRow(x, line, undo)).join(''));
      if (page.next) { btn.dataset.next = page.next; btn.disabled = false; } else btn.remove();
      wireUndo(); wirePlayers();
    } catch (e) { toast(e.message, true); btn.disabled = false; }
  });
  const sw = $('#cswitch');
  if (sw) sw.onclick = () => { tabs('switches'); switchesView(main, {id: c.id, title: c.title}); };
}

SECTIONS.people = main => { PEOPLE.stack = []; peopleSearch(main, PEOPLE.query); };

// ── Метрики ──────────────────────────────────────────────────────────────────

function dur(sec) {
  sec = Math.round(sec || 0);
  if (sec < 60) return `${sec} с`;
  const m = Math.floor(sec / 60), h = Math.floor(m / 60);
  if (h) return `${num(h)} ч ${m % 60} мин`;
  return m >= 10 || !(sec % 60) ? `${m} мин` : `${m} мин ${sec % 60} с`;
}

function bars(days, daily, field, title) {
  if (days.length < 2) return '';
  const vals = days.map(d => (daily[d] || {})[field] || 0);
  const max = Math.max(1, ...vals);
  return `<div class="sub" style="margin-top:12px">${esc(title)}</div><div class="bars">${days.map((d, i) => `
    <div class="b" title="${d}: ${num(vals[i])}"><i style="height:${Math.round(vals[i] / max * 100)}%"></i>
      ${days.length <= 7 || i % 5 === 0 || i === days.length - 1 ? `<span>${d.slice(8)}.${d.slice(5, 7)}</span>` : '<span></span>'}</div>`).join('')}</div>`;
}

const tile = (label, value, extra = '') => `<div><span>${label}</span><b>${value}</b>${extra}</div>`;

// Сравнение с предыдущим таким же периодом: ▲ выросло, ▼ упало.
function trend(cur, prev) {
  if (prev == null) return '';
  if (!prev && !cur) return '';
  if (!prev) return ' <small class="trend up" title="В прошлом периоде было 0">▲ новое</small>';
  const pct = Math.round((cur - prev) / prev * 100);
  if (!pct) return ' <small class="trend" title="Как в прошлом периоде">＝</small>';
  return ` <small class="trend ${pct > 0 ? 'up' : 'down'}" title="В прошлом периоде: ${num(prev)}">${pct > 0 ? '▲' : '▼'} ${Math.abs(pct)}%</small>`;
}

// Структура вкладок (ADM-01). Новые блоки: заголовок вкладки, акцентные плитки, группа-секция, алерт, таблица.
// `.card` не трогаем: его роли (жалобы, панель выбора, рассылка) держатся на старых правилах.
const FOLD = new Map();   // ключ секции -> раскрыта ли; переживает перерисовку вкладки (main.innerHTML = …)
document.addEventListener('toggle', e => {
  const d = e.target;
  if (d.matches && d.matches('details.section[data-sec]')) FOLD.set(d.dataset.sec, d.open);
}, true);

const pageHead = (icon, title, sub) => `<header class="page-head"><h2><span aria-hidden="true">${icon}</span> ${esc(title)}</h2>${sub ? `<p>${esc(sub)}</p>` : ''}</header>`;
const kpi = (label, value, extra = '', cls = '') => `<div class="kpi ${cls}"><span>${label}</span><b>${value}</b>${extra}</div>`;
const alertBox = (kind, html) => `<div class="alert ${kind}" role="status">${html}</div>`;
// Свёрнутая секция помнит выбор человека; без ключа или без fold это обычная открытая группа.
function section(key, title, body, {fold = false, open = true, count = null} = {}) {
  const cnt = count == null ? '' : ` <small class="cnt">· ${count}</small>`;
  if (!fold) return `<section class="section" data-sec="${key}"><h3 class="sec-h">${title}${cnt}</h3>${body}</section>`;
  const isOpen = FOLD.has(key) ? FOLD.get(key) : open;
  return `<details class="section" data-sec="${key}" ${isOpen ? 'open' : ''}><summary class="sec-h">${title}${cnt}</summary><div class="sec-body">${body}</div></details>`;
}
// Таблица: на узком экране, если колонок больше трёх, строки превращаются в карточки (подписи берутся из шапки).
function tbl(heads, rows) {
  const cards = heads.length > 3 ? ' tbl-cards' : '';
  return `<table class="tbl${cards}"><tr>${heads.map(h => `<th>${h}</th>`).join('')}</tr>${rows.map(r =>
    `<tr>${r.map((c, i) => `<td data-label="${esc(String(heads[i]).replace(/<[^>]*>/g, ''))}">${c}</td>`).join('')}</tr>`).join('')}</table>`;
}

const CURRENCIES = {mora: '🪙 Мора', diamonds: '💎 Алмазы', dark_mora: '🌑 Тёмная мора', zarniki: '✨ Зарники'};
const signed = v => (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(v));

function retentionCard(r) {
  if (!r) return '';
  const names = {d1: 'На следующий день', d7: 'За 7 дней', d30: 'За 30 дней'};
  return section('m-retention', '🔁 Удержание', `<div class="kpis">
    ${Object.entries(names).map(([k, t]) => r[k] && r[k].cohort
      ? kpi(t, r[k].percent + '%', `<small> ${num(r[k].returned)} из ${num(r[k].cohort)}</small>`, 'sm') : kpi(t, '—', '<small> данных пока нет</small>', 'sm')).join('')}</div>
    <p class="sub note">Доля новых людей, которые вернулись. «Новый» — впервые замечен в сообщениях чатов или командах бота;
    у каждого срока своя группа, чтобы нужное время уже прошло у всех. Считается по данным с начала учёта.</p>`, {fold: true, open: false});
}

function funnelCard(f) {
  if (!f || !f.steps || !f.steps[0].users) return section('m-funnel', '🪜 Воронка мини-приложения', '<div class="sub">За период приложение никто не открывал.</div>', {fold: true, open: false});
  return section('m-funnel', '🪜 Воронка мини-приложения', `
    ${f.steps.map(x => x.users == null
      ? `<div class="sub" style="margin-top:10px">${esc(x.title)} — данных пока нет</div>`
      : `<div style="margin-top:10px"><div style="display:flex;justify-content:space-between;gap:8px"><span>${esc(x.title)}</span>
          <b>${num(x.users)}${x.of_first == null ? '' : ` <small class="sub">· ${x.of_first}%</small>`}</b></div>
        <div style="height:8px;border-radius:4px;background:var(--line);margin-top:4px"><i style="display:block;height:100%;width:${Math.max(2, x.of_first || 0)}%;background:var(--accent);border-radius:4px"></i></div>
        ${x.of_prev == null || x.key === 'opened' ? '' : `<div class="sub" style="margin-top:2px">${x.of_prev}% от прошлого шага</div>`}</div>`).join('')}
    ${f.with_bot_percent == null ? '' : `<div class="sub" style="margin-top:12px">Из открывших приложение ещё и пользуются командами бота: ${num(f.with_bot)} (${f.with_bot_percent}%)</div>`}
    <p class="sub note">Каждый шаг входит в предыдущий: считаются одни и те же люди за выбранный период. «Потратили валюту» — любая трата в приложении
    (покупка, ставка, образ, питомец).</p>`, {fold: true, open: false});
}

const staffEco = st => {
  const rows = Object.entries(st || {}).filter(([k]) => CURRENCIES[k]);
  return rows.length ? `<p class="sub note">На аккаунтах команды: ${rows.map(([k, c]) => `${CURRENCIES[k]} выдано ${num(c.issued)}, потрачено ${num(c.spent)}`).join('; ')}.</p>` : '';
};
function economyCard(e) {
  const cur = Object.entries(e || {}).filter(([k, c]) => CURRENCIES[k] && (c.issued || c.spent));
  if (!cur.length) return section('m-economy', '💰 Экономика', '<div class="sub">За период движений валюты не было.</div>', {fold: true, open: false});
  const list = (items, label) => items.length ? `<details style="margin-top:6px"><summary class="sub">${label} · ${items.length}</summary>
    ${tbl(['Что', 'Сумма'], items.map(x => [esc(x.title), num(x.amount)]))}</details>` : '';
  return section('m-economy', '💰 Экономика', `${cur.map(([k, c]) => `
    <div class="sub cur"><b>${CURRENCIES[k]}</b></div>
    <div class="kpis">${kpi('Выдано', num(c.issued), '', 'sm')}${kpi('Потрачено', num(c.spent), '', 'sm')}${kpi('Итого', signed(c.net), '', 'sm')}</div>
    ${list(c.sources, 'Откуда пришло')}${list(c.sinks, 'На что ушло')}`).join('')}
    ${staffEco(e._staff)}
    <p class="sub note">Переводы между игроками не считаются: деньги только переходят от человека к человеку. Аккаунты команды в счёт не входят.</p>`, {fold: true, open: false, count: cur.length});
}

// Выгрузка в CSV: в браузере скачивается файлом, а в Telegram (где файлы не скачать) — копируется в буфер.
async function exportMetrics(days) {
  const headers = {};
  if (INIT) headers['x-init-data'] = INIT;
  try { const s = localStorage.getItem('pv_sess'); if (s) headers['x-session-token'] = s; } catch (_) {}
  const res = await fetch(`${BASE}/bot-admin/api/metrics/export?days=${days}`, {headers});
  if (!res.ok) throw new Error(`Ошибка ${res.status}`);
  const text = await res.text();
  if (window.Telegram?.WebApp?.initData) {
    await navigator.clipboard.writeText(text.replace(/^\ufeff/, ''));
    toast('Таблица скопирована: вставьте её в Excel или Google Таблицы.');
    return;
  }
  const url = URL.createObjectURL(new Blob([text], {type: 'text/csv;charset=utf-8'}));
  const a = Object.assign(document.createElement('a'), {href: url, download: `metrics-${days}d.csv`});
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

async function metricsView(main, days = 1) {
  if (![1, 7, 30].includes(days)) days = 1;
  PREFS.set('metrics.days', days);
  showSectionLoading(main, 'metrics');
  const m = await loadSectionData(main, `/metrics?days=${days}`, () => metricsView(main, days), 'metrics');
  if (!m) return;
  const s = m.site, b = m.bot, c = m.chats, cmp = m.compare || {};
  const period = {1: 'Сегодня', 7: '7 дней', 30: '30 дней'};
  const dmy = d => d.split('-').reverse().join('.');
  main.innerHTML = `
    ${pageHead('▥', 'Метрики', 'Сколько людей и чего происходит в боте и приложении')}
    <div class="scope">${Object.entries(period).map(([d, t]) =>
      `<button class="btn small ${+d === m.days ? 'primary' : ''}" data-days="${d}">${t}</button>`).join('')}
      <span class="sub">${m.days === 1 ? dmy(m.until) : dmy(m.since) + ' — ' + dmy(m.until)}</span>
      <button class="btn small" id="mexport" style="margin-left:auto">⬇ Таблица CSV</button></div>
    <div class="kpis hero">
      ${kpi('👤 Уникальных людей', num(m.everyone), trend(m.everyone, cmp.everyone))}${kpi('📱 В приложении', num(s.visitors), trend(s.visitors, cmp.visitors))}
      ${kpi('🤖 Команд бота', num(b.commands), trend(b.commands, cmp.commands))}${kpi('💬 Сообщений', num(c.messages), trend(c.messages, cmp.messages))}</div>
    <p class="sub note">В базе ${num(m.players_total)} игроков и ${num(m.chats_total)} чатов с ботом. Уникальные — кто открыл приложение, вызвал команду или писал
      в чате с ботом. Стрелки — сравнение с ${m.days === 1 ? 'прошлыми сутками целиком' : `предыдущими ${m.days} днями`}.
      ${m.excluded ? `<br>Без аккаунтов команды (разработчик, создатель): ${num(m.excluded)}. Их действия в метрики не входят.` : ''}</p>
    ${section('m-app', '📱 Мини-приложение', `<div class="kpis">
      ${kpi('Посетителей', num(s.visitors), trend(s.visitors, cmp.visitors), 'sm')}${kpi('Сессий', num(s.sessions), '', 'sm')}${kpi('Открытий вкладок', num(s.visits), '', 'sm')}
      ${kpi('Время всего', dur(s.seconds), '', 'sm')}${kpi('На человека', dur(s.avg_seconds_per_visitor), '', 'sm')}</div>
      ${bars(m.day_list, s.daily, 'users', 'Посетители по дням')}
      ${s.pages.length ? tbl(['Вкладка', 'Открытий', 'Людей', 'Время', 'Среднее'],
        s.pages.map(p => [esc(p.title), num(p.visits), num(p.users), dur(p.seconds), dur(p.avg_seconds)]))
        : '<div class="sub" style="margin-top:8px">За период никто не открывал.</div>'}
      ${s.subpages.length ? `<details class="more-d"><summary class="sub">Разделы внутри вкладок · ${s.subpages.length}</summary>
        ${tbl(['Вкладка', 'Открытий', 'Людей'], s.subpages.map(p => [esc(p.tab), num(p.visits), `${num(p.users)} чел.`]))}</details>` : ''}`)}
    ${section('m-bot', '🤖 Команды бота', `<div class="kpis">
      ${kpi('Команд', num(b.commands), trend(b.commands, cmp.commands), 'sm')}${kpi('В чатах', num(b.commands_group), '', 'sm')}${kpi('В личке', num(b.commands_private), '', 'sm')}
      ${kpi('Людей', num(b.users), trend(b.users, cmp.bot_users), 'sm')}${kpi('Людей в чатах', num(b.users_group), '', 'sm')}${kpi('Людей в личке', num(b.users_private), '', 'sm')}</div>
      ${bars(m.day_list, b.daily, 'users', 'Люди, вызывавшие команды, по дням')}
      ${b.top.length ? tbl(['Команда', 'В чатах', 'В личке', 'Всего'], b.top.map(x => [`бот ${esc(x.command)}`, num(x.group), num(x.private), num(x.total)]))
        : '<div class="sub" style="margin-top:8px">Команд за период не было.</div>'}
      ${b.top_includes_staff ? '<p class="sub note">Рейтинг команд считается без разбивки по людям, поэтому в нём остаются и команды аккаунтов команды. Плитки выше их не включают.</p>' : ''}`)}
    ${section('m-chats', '💬 Чаты', `<div class="kpis">
      ${kpi('Сообщений', num(c.messages), trend(c.messages, cmp.messages), 'sm')}${kpi('Писали', num(c.users) + ' чел.', trend(c.users, cmp.chat_users), 'sm')}${kpi('Активных чатов', num(c.chats), '', 'sm')}</div>
      ${bars(m.day_list, c.daily, 'messages', 'Сообщения по дням')}
      ${c.top.length ? tbl(['Чат', 'Сообщений', 'Писали'], c.top.map(x => [ME.sections.some(z => z.key === 'people') ? `<a href="#" data-chat="${x.id}">${esc(x.title)}</a>` : esc(x.title), num(x.messages), num(x.users)])) : ''}`)}
    ${economyCard(m.economy)}${retentionCard(m.retention)}${funnelCard(m.funnel)}`;
  $('#mexport').onclick = async e => {
    e.target.disabled = true;
    try { await exportMetrics(m.days); } catch (err) { toast(err.message || 'Не удалось выгрузить', true); }
    e.target.disabled = false;
  };
  main.querySelectorAll('table').forEach(t => {   // длинные таблицы (топ команд) по 8 строк, остальное по кнопке
    const rows = [...t.querySelectorAll('tr')].slice(1);
    if (rows.length <= 10) return;
    rows.slice(8).forEach(r => { r.hidden = true; });
    const more = document.createElement('button');
    more.className = 'btn small more'; more.style.marginTop = '8px'; more.textContent = `Показать ещё ${rows.length - 8}`;
    more.onclick = () => { rows.forEach(r => { r.hidden = false; }); more.remove(); };
    t.after(more);
  });
  main.querySelectorAll('[data-days]').forEach(btn => btn.onclick = () => metricsView(main, +btn.dataset.days));
  main.querySelectorAll('a[data-chat]').forEach(a => a.onclick = e => {
    e.preventDefault(); tabs('people'); PEOPLE.stack = []; chatView(main, +a.dataset.chat);
  });
}

SECTIONS.metrics = main => metricsView(main, PREFS.get('metrics.days', 1));

// ── Журнал: все действия персонала ───────────────────────────────────────────

const JOURNAL = {kind: PREFS.get('journal.kind', ''), actor: 0, days: [1, 7, 30, 90].includes(PREFS.get('journal.days', 7)) ? PREFS.get('journal.days', 7) : 7,
  view: PREFS.get('journal.view', 'actions') === 'logins' ? 'logins' : 'actions'};
const saveJournal = () => { PREFS.set('journal.kind', JOURNAL.kind); PREFS.set('journal.days', JOURNAL.days); PREFS.set('journal.view', JOURNAL.view); };
// Создатель видит ещё и входы в админку (адрес и устройство): остальным этой вкладки нет.
const journalTabs = () => !ME.creator ? '' : `<div class="scope" style="margin-bottom:8px">${[['actions', 'Действия'], ['logins', 'Входы']].map(([k, t]) =>
  `<button class="btn small ${k === JOURNAL.view ? 'primary' : ''}" data-jview="${k}">${t}</button>`).join('')}</div>`;
const bindJournalTabs = main => main.querySelectorAll('[data-jview]').forEach(b =>
  b.onclick = () => { JOURNAL.view = b.dataset.jview; saveJournal(); journalView(main); });
async function loginsView(main) {
  const data = await loadSectionData(main, `/logins?days=${JOURNAL.days}`, () => loginsView(main), 'journal');
  if (!data) return;
  const rows = data.items.map(x => `<div class="log"><div><b>${who(x.user.id, x.user.username)}</b> · ${esc(x.device)}</div>
      <div class="sub">${when(x.at)} · адрес ${esc(x.ip || 'неизвестен')}</div></div>`).join('');
  main.innerHTML = `${pageHead('☰', 'Журнал', 'Кто из команды и что сделал')}${journalTabs()}<div class="scope">${[[1, 'Сутки'], [7, '7 дней'], [30, '30 дней'], [90, '90 дней']].map(([d, t]) =>
      `<button class="btn small ${d === JOURNAL.days ? 'primary' : ''}" data-jdays="${d}">${t}</button>`).join('')}</div>
    <section class="section"><h3 class="sec-h">Входы в админку</h3>
      <div class="sub note">Кто и с какого устройства открывал админку. Повторные входы за полчаса с того же места не дублируются.</div>
      ${rows || '<div class="empty">За этот период входов нет.</div>'}</section>`;
  bindJournalTabs(main);
  main.querySelectorAll('[data-jdays]').forEach(b => b.onclick = () => { JOURNAL.days = +b.dataset.jdays; saveJournal(); loginsView(main); });
}
async function journalView(main, more = '') {
  if (ME.creator && JOURNAL.view === 'logins') return loginsView(main);
  const qs = `kind=${encodeURIComponent(JOURNAL.kind)}&actor=${JOURNAL.actor}&days=${JOURNAL.days}${more ? '&before=' + encodeURIComponent(more) : ''}`;
  const data = await loadSectionData(main, `/journal?${qs}`, () => journalView(main, more), 'journal');
  if (!data) return;
  if (JOURNAL.kind && !data.kinds.some(k => k.key === JOURNAL.kind)) { JOURNAL.kind = ''; saveJournal(); return journalView(main); }   // запомненный вид исчез
  const canPeople = ME.sections.some(z => z.key === 'people');
  const person = x => x && x.id ? (canPeople ? `<a href="#" data-player="${x.id}">${who(x.id, x.username)}</a>` : who(x.id, x.username)) + tagSfx(x.tag) : '';
  if (!more) JOURNAL.lastDay = '';   // разделитель дня не повторяется на подгруженной странице
  const dayHead = iso => {
    const d = iso ? new Date(iso).toLocaleDateString('ru-RU', {day: 'numeric', month: 'long', weekday: 'short'}) : '';
    if (!d || d === JOURNAL.lastDay) return '';
    JOURNAL.lastDay = d; return `<div class="day-h">${d}</div>`;
  };
  const rows = data.items.map(x => `${dayHead(x.at)}<div class="log"><div><b>${esc(x.title)}</b> ${esc(x.text)}</div>
      ${x.reason ? `<div class="sub">Причина: ${esc(x.reason)}</div>` : ''}
      <div class="sub">${when(x.at)} · ${x.actor && x.actor.id ? person(x.actor) : 'бот'}${x.user ? ' → ' + person(x.user) : ''}${x.chat ? ' · ' + (canPeople ? `<a href="#" data-chat="${x.chat.id}">${esc(x.chat.title || x.chat.id)}</a>` : esc(x.chat.title || x.chat.id)) : ''}</div></div>`).join('');
  const body = rows || (more ? '' : '<div class="empty">За этот период действий нет.</div>');
  if (more) {
    main.querySelector('#jmore')?.remove();
    main.querySelector('#jlist').insertAdjacentHTML('beforeend', body);
  } else {
    main.innerHTML = `${pageHead('☰', 'Журнал', 'Кто из команды и что сделал')}${journalTabs()}<div class="scope">${[[1, 'Сутки'], [7, '7 дней'], [30, '30 дней'], [90, '90 дней']].map(([d, t]) =>
        `<button class="btn small ${d === JOURNAL.days ? 'primary' : ''}" data-jdays="${d}">${t}</button>`).join('')}</div>
      <div class="grid2 jfilters">
        <div class="field"><label>Что</label><select id="jkind"><option value="">Всё</option>${data.kinds.map(k =>
          `<option value="${k.key}" ${k.key === JOURNAL.kind ? 'selected' : ''}>${esc(k.title)}</option>`).join('')}</select></div>
        <div class="field"><label>Кто</label><select id="jactor"><option value="0">Все</option>${data.actors.map(a =>
          `<option value="${a.id}" ${a.id === JOURNAL.actor ? 'selected' : ''}>${a.username ? '@' + esc(a.username) : 'id' + a.id}</option>`).join('')}</select></div></div>
      <section class="section" id="jlist"><h3 class="sec-h">Действия персонала</h3>${body}</section>`;
    bindJournalTabs(main);
    main.querySelectorAll('[data-jdays]').forEach(b => b.onclick = () => { JOURNAL.days = +b.dataset.jdays; saveJournal(); journalView(main); });
    $('#jkind').onchange = e => { JOURNAL.kind = e.target.value; saveJournal(); journalView(main); };
    $('#jactor').onchange = e => { JOURNAL.actor = +e.target.value; journalView(main); };
    $('#jlist').onclick = e => {
      const p = e.target.closest('a[data-player]'), c = e.target.closest('a[data-chat]');
      if (p) { e.preventDefault(); tabs('people'); PEOPLE.stack = []; playerView(main, +p.dataset.player); }
      else if (c) { e.preventDefault(); tabs('people'); PEOPLE.stack = []; chatView(main, +c.dataset.chat); }
    };
  }
  if (data.more) {
    $('#jlist').insertAdjacentHTML('beforeend', `<button class="btn small more" id="jmore">Показать ещё</button>`);
    $('#jmore').onclick = () => journalView(main, data.next);
  }
}

SECTIONS.journal = main => journalView(main);

// ── Жалобы ──────────────────────────────────────────────────────────────────

const REPORT_PICK = new Set();   // выбранные для массовой чистки жалобы; живёт, пока открыта админка
async function reportsView(main, kind = 'open') {
  if (kind !== 'open' && kind !== 'closed') kind = 'open';
  PREFS.set('reports.kind', kind);
  const data = await loadSectionData(main, `/reports?kind=${kind}`, () => reportsView(main, kind), 'reports');
  if (!data) return;
  refreshBadges();
  const c = data.counts;
  const canPeople = ME.sections.some(z => z.key === 'people');
  const person = p => p ? (canPeople ? `<a href="#" data-player="${p.id}">${esc(p.name)}</a>` : esc(p.name)) + tagSfx(p.tag) : '—';
  const chipCls = {new: 'warn', in_work: '', resolved: 'ok', rejected: 'bad'};
  main.innerHTML = `
    ${pageHead('⚑', 'Жалобы', 'Что прислали игроки и что с этим решили')}
    <div class="kpis">${kpi('Новых', num(c.new), '', c.new ? 'sm warn' : 'sm')}${kpi('В работе', num(c.in_work), '', 'sm')}${kpi('Закрыто', num(c.resolved + c.rejected), '', 'sm')}</div>
    <div class="scope"><button class="btn small ${kind === 'open' ? 'primary' : ''}" data-kind="open">Очередь · ${c.new + c.in_work}</button>
      <button class="btn small ${kind === 'closed' ? 'primary' : ''}" data-kind="closed">Закрытые · ${c.resolved + c.rejected}</button></div>
    <div class="sub note">🔒 Жалобы анонимны. ${data.can_see_reporter ? 'Вам автор виден по настройкам жалоб.' : 'Автора жалобы видит только персонал с доступом.'}</div>
    ${data.repeat && data.repeat.length ? `<section class="section" data-sec="r-repeat"><h3 class="sec-h">🔁 Повторные нарушители <small class="cnt">· ${data.repeat.length}</small></h3>
      <div class="sub note">3 жалобы и больше за 30 дней, отклонённые не считаются.</div>
      ${data.repeat.map(x => `<div class="sw-row"><div class="t">${person({id: x.id, name: x.name})}
        <div class="sub">жалоб: ${x.reports} · от ${x.reporters} ${x.reporters === 1 ? 'игрока' : 'разных игроков'} · открытых: ${x.open} · подтверждено: ${x.confirmed}</div></div>
        ${canPeople ? `<button class="btn small" data-player="${x.id}">👤 Карточка</button>` : ''}</div>`).join('')}</section>` : ''}
    ${kind === 'open' && data.items.length > 1 ? '<div id="repbulk"></div>' : ''}
    ${data.items.length ? data.items.map(r => `<div class="card rep ${r.status}" data-card="${r.id}">
      <div>${kind === 'open' && data.items.length > 1 ? '<input type="checkbox" class="pick" data-pickrep="' + r.id + '" aria-label="Выбрать жалобу"/> ' : ''}<span class="chip ${chipCls[r.status] || ''}">${esc(r.status_title)}</span> <b>№${r.id}</b>
        <span class="sub">· ${when(r.created_at)} · ${esc(r.chat.title)}</span></div>
      <div style="margin-top:8px">На ${person(r.target)}${r.target_reports > 1 ? ` <span class="chip bad">жалоб всего: ${r.target_reports}</span>` : ''}
        <span class="sub">${r.reporter ? 'от ' + person(r.reporter) : '· автор скрыт'}</span></div>
      <div class="rep-why"><b>Причина:</b> ${esc(r.reason)}</div>
      ${r.message_text ? `<blockquote class="rep-msg">${esc(r.message_text)}</blockquote>` : ''}
      ${r.handled_by ? `<div class="sub" style="margin-top:6px">${esc(r.handled_by.name)} · ${when(r.handled_at)}${r.note ? ' · ' + esc(r.note) : ''}</div>` : ''}
      ${kind === 'open' ? `<div class="actions" style="margin-top:10px">
        ${canPeople ? `<button class="btn small" data-player="${r.target.id}">👤 Карточка</button>` : ''}
        ${(data.punish || []).map(a => `<button class="btn small danger" data-punish="${a.key}" data-rid="${r.id}">${esc(a.title)}</button>`).join('')}
        ${r.status === 'new' ? `<button class="btn small" data-rep="${r.id}" data-act="take">🙋 Взять</button>` : ''}
        <button class="btn small primary" data-rep="${r.id}" data-act="resolve">✅ Нарушение</button>
        <button class="btn small" data-rep="${r.id}" data-act="reject">✖️ Отклонить</button></div>` : ''}
    </div>`).join('') : `<div class="empty">${kind === 'open' ? 'Очередь пуста.' : 'Закрытых жалоб пока нет.'}</div>`}`;
  main.querySelectorAll('[data-kind]').forEach(b => b.onclick = () => reportsView(main, b.dataset.kind));
  main.querySelectorAll('[data-player]').forEach(a => a.onclick = e => {
    e.preventDefault(); tabs('people'); PEOPLE.stack = []; playerView(main, +a.dataset.player);
  });
  // Быстрое наказание из жалобы: в том же чате, с закрытием жалобы как подтверждённой.
  main.querySelectorAll('[data-punish]').forEach(b => b.onclick = () => {
    const key = b.dataset.punish, r = data.items.find(x => x.id === +b.dataset.rid);
    const title = (data.punish.find(a => a.key === key) || {}).title || key;
    const [form, collect] = actionForm(key, {});
    sheet(title, `<div class="sub" style="margin-bottom:10px">На ${esc(r.target.name)} · чат «${esc(r.chat.title)}» · жалоба №${r.id}: ${esc(r.reason)}</div>${form}
      <div class="field switch"><input id="fclose" type="checkbox" checked/><label for="fclose" style="margin:0">Закрыть жалобу: нарушение подтверждено</label></div>`,
      key === 'ban' ? 'Далее' : 'Выполнить', async () => {
        const payload = {action: key, ...collect(), close: $('#fclose').checked};
        const send = async () => {
          const res = await api(`/reports/${r.id}/punish`, {method: 'POST', body: JSON.stringify(payload)});
          toast(res.message || 'Готово');
          reportsView(main, kind);
        };
        if (key !== 'ban') return send();
        // Бан — как в карточке игрока: сначала итог, потом подтверждение (по умолчанию он «навсегда»).
        const lines = [`Игрок: <b>${esc(r.target.name)}</b>`, ...confirmLines('ban', payload, {}, {chat_title: r.chat.title}),
          ...(payload.close ? ['Жалоба закроется как подтверждённая.'] : [])];
        sheet(CONFIRM_TITLE.ban, `<div class="sub" style="margin-bottom:8px">Проверьте перед выполнением:</div>
          <div class="confirm">${lines.map(l => `<div>${l}</div>`).join('')}</div>`, 'Подтвердить', send);
        return 'keep';
      });
  });
  // Массовая чистка очереди: отметить несколько жалоб и закрыть их одним действием (наказаний здесь нет).
  const queue = new Set(data.items.map(x => x.id));
  [...REPORT_PICK].forEach(id => { if (kind !== 'open' || !queue.has(id)) REPORT_PICK.delete(id); });
  const BULK_REPORT = {take: ['🙋 Взять', 'Взять в работу'], resolve: ['✅ Нарушение', 'Нарушение подтверждено'], reject: ['✖️ Отклонить', 'Отклонить']};
  const drawRepBulk = () => {
    const host = $('#repbulk'); if (!host) return;
    const n = REPORT_PICK.size;
    main.querySelectorAll('[data-card]').forEach(card => {
      const on = REPORT_PICK.has(+card.dataset.card);
      card.classList.toggle('picked', on);
      const box = card.querySelector('.pick'); if (box) box.checked = on;
    });
    host.innerHTML = `<div class="card bulkbar"><div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline">
        <b>Выбрано: ${n}</b><span class="sub"><a href="#" id="repall">${n === queue.size ? 'снять выбор' : 'выбрать все'}</a></span></div>
      ${n ? `<div class="actions" style="margin-top:8px">${Object.entries(BULK_REPORT).map(([key, [label]]) =>
        `<button class="btn small ${key === 'resolve' ? 'primary' : ''}" data-repbulk="${key}">${label}</button>`).join('')}</div>`
        : '<div class="sub" style="margin-top:4px">Отмечайте жалобы галочкой и закрывайте пачкой.</div>'}</div>`;
    $('#repall').onclick = e => { e.preventDefault(); n === queue.size ? REPORT_PICK.clear() : queue.forEach(id => REPORT_PICK.add(id)); drawRepBulk(); };
    host.querySelectorAll('[data-repbulk]').forEach(b => b.onclick = () => {
      const act = b.dataset.repbulk, ids = [...REPORT_PICK];
      const body = `<div class="sub" style="margin-bottom:8px">Жалоб: <b>${ids.length}</b>. ${act === 'take' ? 'Все они будут помечены как ваши.'
        : 'Авторам бот напишет в личку, чем всё закончилось. Нарушителей это не наказывает: выдать варн, мут или бан можно из самой жалобы.'}</div>
        ${act === 'take' ? '' : '<div class="field"><label>Комментарий (необязательно)</label><input id="fnote" maxlength="300"/></div>'}`;
      sheet(BULK_REPORT[act][1], body, 'Готово', async () => {
        const res = await api('/reports/bulk', {method: 'POST', body: JSON.stringify({action: act, ids, note: ($('#fnote') || {}).value || ''})});
        toast(res.message || 'Готово');
        REPORT_PICK.clear();
        if (res.failed.length) {
          sheet('Не всё получилось', `<div class="sub">${esc(res.message)}</div>${res.failed.map(f =>
            `<div class="log"><b>№${f.id}</b><div class="sub">${esc(f.reason)}</div></div>`).join('')}`, 'Понятно', () => {}, {info: true});
        }
        reportsView(main, kind);
      });
    });
  };
  main.querySelectorAll('[data-pickrep]').forEach(box => box.onchange = () => {
    box.checked ? REPORT_PICK.add(+box.dataset.pickrep) : REPORT_PICK.delete(+box.dataset.pickrep);
    drawRepBulk();
  });
  drawRepBulk();
  const titles = {take: 'Взять жалобу в работу', resolve: 'Нарушение подтверждено', reject: 'Отклонить жалобу'};
  main.querySelectorAll('[data-rep]').forEach(b => b.onclick = () => {
    const act = b.dataset.act;
    const body = act === 'take' ? '<div class="sub">Жалоба будет помечена как ваша.</div>'
      : `<div class="sub" style="margin-bottom:8px">Автору жалобы бот напишет в личку, чем всё закончилось.
         Наказать нарушителя можно кнопкой «Наказать» (карточка игрока).</div>
         <div class="field"><label>Комментарий (необязательно)</label><input id="fnote" maxlength="300"/></div>`;
    sheet(titles[act], body, 'Готово', async () => {
      const res = await api(`/reports/${b.dataset.rep}`, {method: 'POST',
        body: JSON.stringify({action: act, note: ($('#fnote') || {}).value || ''})});
      toast(res.message || 'Готово');
      reportsView(main, kind);
    });
  });
}

SECTIONS.reports = main => reportsView(main, PREFS.get('reports.kind', 'open'));

// ── Рассылка ─────────────────────────────────────────────────────────────────

// Предпросмотр HTML Telegram: всё экранируется, обратно включаются только теги, которые понимает Telegram.
function tgHtml(text) {
  const html = esc(text)
    .replace(/&lt;(\/?)(b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote|tg-spoiler)&gt;/g, '<$1$2>')
    .replace(/&lt;a href=&quot;(https?:\/\/[^&"]*)&quot;&gt;/g, '<a href="$1" target="_blank" rel="noopener">')
    .replace(/&lt;\/a&gt;/g, '</a>');
  // Теги закрываем сами: обрезанный на полуслове текст («<b>жирный…») не должен делать жирными соседние строки.
  const open = [];
  const balanced = html.replace(/<(\/?)([a-z-]+)[^>]*>/g, (m, close, tag) => {
    if (!close) { open.push(tag); return m; }
    const at = open.lastIndexOf(tag);
    if (at < 0) return '';
    return open.splice(at).reverse().map(t => `</${t}>`).join('');
  });
  return balanced + open.reverse().map(t => `</${t}>`).join('');
}

// Выбор людей или чатов поиском: чипы + подсказки. items — массив {id, label}, меняется на месте.
function pickerField(host, {hint, placeholder, search, items, onChange}) {
  host.innerHTML = `<input placeholder="${esc(placeholder)}"/><div class="found"></div><div class="chips"></div>`;
  const input = $('input', host), found = $('.found', host), chips = $('.chips', host);
  const draw = () => {
    chips.innerHTML = items.length
      ? items.map((x, i) => `<span class="chip" data-un="${i}" title="Убрать">${esc(x.label)} ✕</span>`).join('')
      : `<span class="sub">${esc(hint)}</span>`;
  };
  draw();
  chips.onclick = e => { const c = e.target.closest('[data-un]'); if (c) { items.splice(+c.dataset.un, 1); draw(); onChange(); } };
  let timer;
  input.oninput = () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { found.innerHTML = ''; return; }
    timer = setTimeout(async () => {
      try {
        const list = (await search(q)).filter(x => !items.some(y => y.id === x.id));
        found.innerHTML = list.map((x, i) => `<button type="button" data-add="${i}">${esc(x.label)} <span class="sub">${x.id}</span></button>`).join('')
          || '<span class="sub">Не найдено</span>';
        found._list = list;
      } catch (e) { found.innerHTML = `<span class="sub">${esc(e.message)}</span>`; }
    }, 250);
  };
  found.onclick = e => {
    const b = e.target.closest('[data-add]');
    if (!b || !found._list) return;
    items.push(found._list[+b.dataset.add]);
    found.innerHTML = ''; input.value = '';
    draw(); onChange();
  };
}

const searchChats = async q => (await api(`/chats?q=${encodeURIComponent(q)}`)).items.map(c => ({id: c.id, label: c.title}));
const searchPlayers = async q => (await api(`/search?q=${encodeURIComponent(q)}`)).players
  .map(u => ({id: u.id, label: u.username ? '@' + u.username : 'id' + u.id}));

// Черновик живёт, пока открыта админка: обновление списка или ошибка не стирают набранное.
const BC = {kind: 'players', chats: [], players: [], active: '', vip: '', newDays: '', minMsg: '', text: '', html: true,
            btnText: '', btnUrl: '', later: false, at: ''};

function bcSegment() {
  const seg = {kind: BC.kind};
  if (BC.chats.length) seg.chats = BC.chats.map(x => x.id);
  if (+BC.active) seg.active_days = +BC.active;
  if (BC.kind === 'players') {
    if (BC.vip !== '') seg.vip = BC.vip === '1';
    if (+BC.newDays) seg.new_days = +BC.newDays;
    if (+BC.minMsg) seg.min_messages = +BC.minMsg;
    if (BC.players.length) seg.players = BC.players.map(x => x.id);
  }
  return seg;
}
const bcButton = () => (BC.btnText.trim() || BC.btnUrl.trim()) ? {text: BC.btnText.trim(), url: BC.btnUrl.trim()} : null;

function bcHistoryRow(b) {
  const text = b.text.length > 160 ? b.text.slice(0, 160) + '…' : b.text;
  const progress = b.status === 'scheduled' ? `отправится ${when(b.scheduled_at)}` : `${num(b.sent)}/${num(b.total)}${b.failed ? ` · не дошло ${num(b.failed)}` : ''}`;
  const resumable = b.status === 'interrupted' || (b.status === 'stopped' && b.total > b.sent + b.failed);
  return `<div class="log"><div><b>${esc(b.audience_title)}</b> · ${esc(b.status_title)} · ${progress}</div>
    <div class="sub" style="white-space:pre-wrap">${(b.html ? tgHtml : esc)(text)}${b.button ? `\n[ ${esc(b.button.text)} ]` : ''}</div>
    <div class="sub">${when(b.created_at)} · ${esc(b.actor)}</div>
    <div class="actions" style="margin-top:6px">
      ${b.status === 'running' ? `<button class="btn small" data-bstop="${b.id}">⏹ Остановить</button>` : ''}
      ${b.status === 'scheduled' ? `<button class="btn small" data-bstop="${b.id}">✖ Отменить</button>` : ''}
      ${resumable ? `<button class="btn small" data-bresume="${b.id}">▶ Продолжить</button>` : ''}
      ${b.status !== 'scheduled' ? `<button class="btn small" data-breport="${b.id}">📋 Отчёт</button>` : ''}
    </div></div>`;
}

async function bcReport(id, refresh) {
  const rep = await api(`/broadcasts/${id}`);
  const b = rep.broadcast;
  const names = rep.failed_sample.map(x => `<div class="log"><b>${esc(x.name)}</b> <span class="sub">${esc(x.reason)}</span></div>`).join('');
  sheet(`Рассылка №${b.id}`, `
    <div class="sub" style="margin-bottom:6px">${esc(b.audience_title)} · ${esc(b.status_title)}</div>
    <div class="grid2"><div class="card"><div class="sub">Дошло</div><b>${num(rep.sent)}</b></div>
      <div class="card"><div class="sub">Не дошло</div><b>${num(rep.failed)}</b></div></div>
    ${rep.pending ? `<div class="sub">Ещё не отправлено: ${num(rep.pending)}</div>` : ''}
    ${rep.reasons.length ? `<h4>Почему не дошло</h4>${rep.reasons.map(r => `<div class="log">${esc(r.title)} <b>${num(r.count)}</b></div>`).join('')}` : ''}
    ${names ? `<h4>Кому не дошло${rep.failed > rep.failed_sample.length ? ` (первые ${rep.failed_sample.length})` : ''}</h4>${names}` : ''}
    <div class="card" style="white-space:pre-wrap;margin-top:8px">${(b.html ? tgHtml : esc)(b.text)}</div>`,
    rep.failed ? 'Повторить недоставленным' : 'Закрыть', async () => {
      if (!rep.failed) return;
      const res = await api(`/broadcasts/${id}/retry`, {method: 'POST'});
      toast(res.message); refresh();
    });
}

async function broadcastView(main) {
  const data = await loadSectionData(main, '/broadcasts', () => broadcastView(main), 'broadcast');
  if (!data) return;
  let items = data.items, templates = data.templates || [];
  main.innerHTML = `
    <div class="card"><h3>📣 Новая рассылка</h3>
      <div class="field"><label>Шаблон</label><select id="btpl"></select>
        <div class="actions" style="margin-top:6px"><button class="btn small" id="btplsave">💾 Сохранить как шаблон</button>
        <button class="btn small danger" id="btpldel" hidden>Удалить шаблон</button></div></div>
      <div class="field"><label>Кому</label><select id="bkind">${data.audiences.map(a =>
        `<option value="${a.key}" ${a.key === BC.kind ? 'selected' : ''}>${esc(a.title)} · всего ${num(data.sizes[a.key] || 0)}</option>`).join('')}</select></div>
      <div id="bseg"></div>
      <div class="card" id="bcount" style="margin:8px 0">Считаем получателей…</div>
      <div class="field"><label>Текст (до 3500 символов)</label><textarea id="btext" maxlength="3500" rows="6"></textarea></div>
      <div class="field switch"><input type="checkbox" id="bhtml"/><label for="bhtml" style="margin:0">HTML-разметка Telegram</label></div>
      <div class="sub" id="bhelp">Можно: &lt;b&gt;жирный&lt;/b&gt;, &lt;i&gt;курсив&lt;/i&gt;, &lt;u&gt;, &lt;s&gt;, &lt;code&gt;, &lt;blockquote&gt;, &lt;tg-spoiler&gt;, &lt;a href="https://…"&gt;ссылка&lt;/a&gt;.</div>
      <div class="grid2" style="margin-top:8px">
        <div class="field"><label>Кнопка под сообщением: подпись</label><input id="bbtext" maxlength="64" placeholder="Например: Играть"/></div>
        <div class="field"><label>Ссылка кнопки</label><input id="bburl" maxlength="512" placeholder="https://t.me/…"/></div></div>
      <div class="sub" style="margin-top:6px">Предпросмотр</div>
      <div class="card" id="bprev" style="white-space:pre-wrap;min-height:44px"></div>
      <div class="field switch"><input type="checkbox" id="blater"/><label for="blater" style="margin:0">Отправить позже</label></div>
      <div class="field" id="batwrap" hidden><label>Когда (по вашему времени)</label><input type="datetime-local" id="bat"/></div>
      <div class="sub">В личку дойдёт только тем, кто хоть раз открывал диалог с ботом. Заблокированным и забаненным везде не отправляется. Получателей отложенной рассылки бот считает в момент отправки.</div>
      <div class="actions" style="margin-top:10px"><button class="btn" id="btest">✉️ Отправить себе в личку</button>
        <button class="btn primary" id="bgo">Проверить и отправить</button></div>
      <div class="sub" id="bbusy" style="margin-top:6px" hidden>Сейчас идёт другая рассылка: дождитесь её или остановите.</div>
    </div>
    <div class="card"><h3>История</h3><div id="bhist"></div></div>`;

  // ── Сегмент ──
  const refreshCount = (() => {
    let timer, seq = 0;
    return () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const mine = ++seq, box = $('#bcount');
        if (!box) return;
        try {
          const res = await api('/broadcasts/preview', {method: 'POST', body: JSON.stringify({segment: bcSegment()})});
          if (mine === seq && $('#bcount')) { BC.count = res.count; BC.title = res.title; box.innerHTML = `Получателей: <b>${num(res.count)}</b> · <span class="sub">${esc(res.title)}</span>`; }
        } catch (e) { if (mine === seq && $('#bcount')) { BC.count = null; box.innerHTML = `<span class="sub">${esc(e.message)}</span>`; } }
      }, 300);
    };
  })();
  const numberField = (id, label, key, ph) => `<div class="field"><label>${label}</label><input id="${id}" type="number" min="0" inputmode="numeric" value="${esc(BC[key])}" placeholder="${ph}"/></div>`;
  function drawSegment() {
    const players = BC.kind === 'players';
    $('#bseg').innerHTML = `
      <div class="field"><label>${players ? 'Только участники этих чатов (пусто — любых)' : 'Только эти чаты (пусто — все чаты бота)'}</label><div id="bpchats"></div></div>
      ${players ? `<div class="field"><label>Только эти игроки (пусто — любые)</label><div id="bpplayers"></div></div>` : ''}
      <div class="grid2">
        ${numberField('bactive', players ? 'Писали хоть где-то за N дней' : 'Писали в чате за N дней', 'active', 'Любые')}
        ${players ? `<div class="field"><label>VIP</label><select id="bvip">
          ${[['', 'Не важно'], ['1', 'Только с VIP'], ['0', 'Только без VIP']].map(([v, t]) => `<option value="${v}" ${BC.vip === v ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
        ${numberField('bnew', 'Новички: впервые замечены за N дней', 'newDays', 'Любые')}
        ${numberField('bmin', 'Сообщений всего — не меньше', 'minMsg', 'Любые')}` : ''}
      </div>`;
    pickerField($('#bpchats'), {hint: players ? 'Любые чаты' : 'Все чаты бота', placeholder: 'Найти чат по названию или ID', search: searchChats, items: BC.chats, onChange: refreshCount});
    if (players) pickerField($('#bpplayers'), {hint: 'Любые игроки', placeholder: 'Найти игрока по @нику или ID', search: searchPlayers, items: BC.players, onChange: refreshCount});
    const bind = (id, key) => { const el = $('#' + id); if (el) el.oninput = el.onchange = () => { BC[key] = el.value; refreshCount(); }; };
    bind('bactive', 'active'); bind('bvip', 'vip'); bind('bnew', 'newDays'); bind('bmin', 'minMsg');
    refreshCount();
  }
  $('#bkind').onchange = () => { BC.kind = $('#bkind').value; drawSegment(); };
  drawSegment();

  // ── Текст, кнопка, расписание ──
  const draw = () => {
    BC.text = $('#btext').value; BC.html = $('#bhtml').checked; BC.btnText = $('#bbtext').value; BC.btnUrl = $('#bburl').value;
    BC.later = $('#blater').checked; BC.at = $('#bat').value;
    $('#bprev').innerHTML = (BC.html ? tgHtml : esc)(BC.text) + (bcButton() ? `<div style="margin-top:8px"><span class="chip">${esc(BC.btnText || '…')}</span></div>` : '');
    $('#bhelp').hidden = !BC.html;
    $('#batwrap').hidden = !BC.later;
    $('#bgo').textContent = BC.later ? 'Проверить и запланировать' : 'Проверить и отправить';
  };
  $('#btext').value = BC.text; $('#bhtml').checked = BC.html; $('#bbtext').value = BC.btnText; $('#bburl').value = BC.btnUrl;
  $('#blater').checked = BC.later; $('#bat').value = BC.at;
  ['#btext', '#bbtext', '#bburl', '#bat'].forEach(sel => $(sel).oninput = draw);
  $('#bhtml').onchange = $('#blater').onchange = draw;
  draw();

  // ── Шаблоны ──
  const drawTemplates = () => {
    $('#btpl').innerHTML = `<option value="">— без шаблона —</option>` + templates.map(t => `<option value="${t.id}">${esc(t.title)}</option>`).join('');
    $('#btpldel').hidden = true;
  };
  drawTemplates();
  $('#btpl').onchange = () => {
    const t = templates.find(x => String(x.id) === $('#btpl').value);
    $('#btpldel').hidden = !t;
    if (!t) return;
    $('#btext').value = t.text; $('#bhtml').checked = t.html;
    $('#bbtext').value = t.button ? t.button.text : ''; $('#bburl').value = t.button ? t.button.url : '';
    draw();
  };
  $('#btplsave').onclick = () => {
    if (!$('#btext').value.trim()) { toast('Сначала напишите текст.', true); return; }
    sheet('Сохранить как шаблон', `<div class="field"><label>Название</label><input id="btitle" maxlength="60" placeholder="Например: Новости недели"/></div>
      <div class="sub">Сохранятся текст, разметка и кнопка. Получатели и время — нет.</div>`, 'Сохранить', async () => {
      const res = await api('/broadcasts/templates', {method: 'POST', body: JSON.stringify({
        title: $('#btitle').value, text: $('#btext').value.trim(), html: $('#bhtml').checked, button: bcButton()})});
      templates = res.items; drawTemplates(); toast(res.message);
    });
  };
  $('#btpldel').onclick = async () => {
    const t = templates.find(x => String(x.id) === $('#btpl').value);
    if (!t || !confirm(`Удалить шаблон «${t.title}»?`)) return;
    try { templates = (await api(`/broadcasts/templates/${t.id}`, {method: 'DELETE'})).items; drawTemplates(); toast('Шаблон удалён.'); }
    catch (e) { toast(e.message, true); }
  };

  // ── Отправка ──
  $('#btest').onclick = async () => {
    const text = $('#btext').value.trim();
    if (!text) { toast('Напишите текст.', true); return; }
    $('#btest').disabled = true;
    try { toast((await api('/broadcasts/test', {method: 'POST', body: JSON.stringify({text, html: BC.html, button: bcButton()})})).message); }
    catch (e) { toast(e.message, true); }
    $('#btest').disabled = false;
  };
  $('#bgo').onclick = () => {
    const text = BC.text.trim();
    if (!text) { toast('Напишите текст.', true); return; }
    if (BC.later && !BC.at) { toast('Выберите время отправки.', true); return; }
    const rid = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()) + Math.random();
    const who = BC.count == null ? 'Получатели не посчитаны' : `${num(BC.count)} получателей · ${BC.title}`;
    sheet(BC.later ? 'Запланировать рассылку?' : 'Отправить рассылку?', `
      <div class="sub" style="margin-bottom:8px">${esc(who)}${BC.later ? `<br/>Отправится ${when(BC.at)}.` : '<br/>Отменить уже отправленное нельзя.'}</div>
      <div class="card" style="white-space:pre-wrap">${(BC.html ? tgHtml : esc)(text)}${bcButton() ? `<div style="margin-top:8px"><span class="chip">${esc(BC.btnText)}</span> <span class="sub">${esc(BC.btnUrl)}</span></div>` : ''}</div>`,
      BC.later ? 'Запланировать' : 'Отправить', async () => {
        const res = await api('/broadcasts', {method: 'POST', body: JSON.stringify({
          audience: BC.kind, segment: bcSegment(), text, html: BC.html, button: bcButton(), request_id: rid,
          scheduled_at: BC.later ? new Date(BC.at).toISOString() : null})});
        toast(res.message || 'Готово');
        Object.assign(BC, {text: '', btnText: '', btnUrl: '', later: false, at: ''});
        broadcastView(main);
      });
  };

  // ── История: перерисовывается отдельно, пока идёт рассылка (форма остаётся как есть) ──
  const alive = () => document.body.contains(main) && $('#bhist') && currentSection() === 'broadcast';
  let poll;
  function drawHistory() {
    clearTimeout(poll);
    const running = items.some(b => b.status === 'running');
    $('#bgo').disabled = running; $('#bbusy').hidden = !running;
    $('#bhist').innerHTML = items.length ? items.map(bcHistoryRow).join('') : '<div class="sub">Рассылок ещё не было.</div>';
    if (running || items.some(b => b.status === 'scheduled')) {
      poll = setTimeout(async () => {
        if (!alive()) return;
        try { items = (await api('/broadcasts')).items; } catch (_) {}
        if (alive()) drawHistory();
      }, running ? 4000 : 30000);
    }
  }
  const reload = async () => { items = (await api('/broadcasts')).items; drawHistory(); };
  $('#bhist').onclick = async e => {
    const stop = e.target.closest('[data-bstop]'), resume = e.target.closest('[data-bresume]'), report = e.target.closest('[data-breport]');
    try {
      if (stop) { toast((await api(`/broadcasts/${stop.dataset.bstop}/stop`, {method: 'POST'})).message); await reload(); }
      else if (resume) { toast((await api(`/broadcasts/${resume.dataset.bresume}/resume`, {method: 'POST'})).message); await reload(); }
      else if (report) await bcReport(report.dataset.breport, reload);
    } catch (err) { toast(err.message, true); }
  };
  drawHistory();
}

SECTIONS.broadcast = main => broadcastView(main);

// ── Промокоды ────────────────────────────────────────────────────────────────

let OPTIONS = null;

function promoStatus(p) {
  if (p.legacy) return '<span class="chip warn">старый формат</span>';
  const now = Date.now();
  if (!p.is_active) return '<span class="chip off">выключен</span>';
  if (p.valid_until && Date.parse(p.valid_until) < now) return '<span class="chip off">истёк</span>';
  if (p.valid_from && Date.parse(p.valid_from) > now) return '<span class="chip warn">ещё не начался</span>';
  if (p.max_activations && p.activations >= p.max_activations) return '<span class="chip off">исчерпан</span>';
  return '<span class="chip ok">работает</span>';
}

function when(iso) {
  return iso ? new Date(iso).toLocaleString('ru-RU', {dateStyle: 'short', timeStyle: 'short'}) : '';
}

async function promoList(main, query = '') {
  main.innerHTML = `
    <div class="bar"><input id="pq" placeholder="Поиск по коду" value="${esc(query)}"/>
      <button class="btn" id="pbulk" title="Много одноразовых кодов с одной наградой">Пачка</button>
      <button class="btn primary" id="pnew">+ Новый</button></div>
    <div class="list" id="plist"><div class="empty">Загрузка…</div></div>`;
  $('#pnew').onclick = () => promoEdit(main, null);
  $('#pbulk').onclick = () => promoEdit(main, null, {bulk: true});
  let timer;
  $('#pq').oninput = e => { clearTimeout(timer); timer = setTimeout(() => load(e.target.value), 250); };
  async function load(q) {
    const host = $('#plist'); if (!host) return;
    const data = await loadSectionData(host, `/promo?q=${encodeURIComponent(q)}`, () => load(q), 'promo');
    if (!data) return;
    const {items} = data;
    $('#plist').innerHTML = items.length ? items.map(p => `
      <div class="row" data-code="${esc(p.code)}">
        <div class="head"><span class="code">${esc(p.code)}</span>${promoStatus(p)}</div>
        <div class="sub">${p.rewards_text.length ? esc(p.rewards_text.join(' · ')) : 'наград нового формата нет'}</div>
        <div class="sub">Активаций: ${num(p.activations)}${p.max_activations ? ' из ' + num(p.max_activations) : ''}
          ${p.allowed_chats.length ? ' · чатов: ' + p.allowed_chats.length : ' · во всех чатах'}
          ${p.valid_until ? ' · до ' + when(p.valid_until) : ''}</div>
      </div>`).join('') : '<div class="empty">Промокодов нет</div>';
    for (const row of main.querySelectorAll('[data-code]')) row.onclick = () => promoView(main, row.dataset.code);
  }
  load(query);
}

const SPENT_TITLES = [['mora', 'мора'], ['diamonds', 'алмазов'], ['essence', 'эссенции'], ['zarniki', 'зарников'], ['vip_days', 'дн. VIP']];

// Как идёт код: сколько осталось, где и когда активировали, сколько награды уже ушло и что в нём стоит перепроверить.
function promoStats(p) {
  const s = p.stats;
  if (!s) return '';
  const days = s.per_day.map(d => d.day), daily = Object.fromEntries(s.per_day.map(d => [d.day, {n: d.n}]));
  const spent = SPENT_TITLES.filter(([key]) => s.spent && s.spent[key] != null && +s.spent[key] > 0)
    .map(([key, title]) => `${num(s.spent[key])} ${title}`);
  const share = s.limit ? Math.min(100, Math.round(s.activations / s.limit * 100)) : 0;
  return `<div class="card"><h3>Как идёт</h3>
    ${(p.warnings || []).map(w => `<div class="chip warn" style="display:block;margin-bottom:6px;border-radius:12px">${esc(w)}</div>`).join('')}
    ${s.limit ? `<div class="meter" title="${share}%"><i style="width:${share}%"></i></div>` : ''}
    <div class="stats">
      ${tile('Активаций', num(s.activations) + (s.limit ? ` <small>из ${num(s.limit)}</small>` : ''))}
      ${s.left != null ? tile('Осталось', num(s.left)) : ''}
      ${tile('Чатов', num(s.chats))}${tile('В личке', num(s.private))}
    </div>
    <div class="sub" style="margin-top:8px">${s.first_at ? `Первая: ${when(s.first_at)} · последняя: ${when(s.last_at)}` : 'Пока никто не активировал'}</div>
    ${spent.length ? `<div class="sub" style="margin-top:4px">Уже выдано примерно: ${spent.map(esc).join(' · ')}</div>` : ''}
    ${s.activations ? bars(days, daily, 'n', 'Активации за 14 дней') : ''}</div>`;
}

async function promoView(main, code) {
  const p = await loadSectionData(main, `/promo/${encodeURIComponent(code)}`, () => promoView(main, code), 'promo');
  if (!p) return;
  main.innerHTML = `
    <div class="bar"><button class="btn" id="pback">← Все промокоды</button></div>
    <div class="card">
      <div class="head" style="display:flex;justify-content:space-between;gap:8px">
        <span class="code" style="font-size:20px">${esc(p.code)}</span>${promoStatus(p)}</div>
      ${p.note ? `<div class="sub" style="margin-top:6px">${esc(p.note)}</div>` : ''}
      <div class="actions" style="margin-top:8px"><button class="btn small" id="pcopy">Копировать код</button>
        <button class="btn small" id="pcopycmd" title="Что игроку написать в чате">Копировать «бот промокод …»</button></div>
      <div style="margin-top:10px">${p.rewards_text.map(r => `<div>${esc(r)}</div>`).join('') || '<div class="sub">Нет наград нового формата — пересохраните код.</div>'}</div>
      <div class="sub" style="margin-top:10px">Активаций: ${num(p.activations)}${p.max_activations ? ' из ' + num(p.max_activations) : ' (без лимита)'}<br>
        ${p.valid_from ? 'С ' + when(p.valid_from) + ' ' : ''}${p.valid_until ? 'до ' + when(p.valid_until) : (p.valid_from ? '' : 'Без срока')}<br>
        ${p.chats.length ? 'Только в чатах: ' + p.chats.map(c => esc(c.title)).join(', ') : 'Во всех чатах и в личке с ботом'}
        ${p.allowed_users.length ? '<br>Только для ID: ' + p.allowed_users.join(', ') : ''}</div>
      <div class="actions" style="margin-top:12px">
        <button class="btn primary" id="pedit">Изменить</button>
        <button class="btn ${p.is_active ? 'danger' : ''}" id="ptoggle">${p.is_active ? 'Выключить' : 'Включить'}</button>
      </div>
    </div>
    ${promoStats(p)}
    <div class="card"><h3>Кто активировал · ${p.redemptions.length}</h3>
      ${p.redemptions.length ? `<table><tr><th>Игрок</th><th>Где</th><th>Когда</th><th>Получил</th></tr>
        ${p.redemptions.map(r => `<tr><td>${r.username ? '@' + esc(r.username) : r.user_id}<div class="sub">${r.user_id}</div></td>
          <td>${r.chat_id ? esc(r.chat_title || r.chat_id) : 'личка'}</td><td>${when(r.at)}</td>
          <td>${esc((r.granted || []).join(', '))}</td></tr>`).join('')}</table>` : '<div class="sub">Пока никто.</div>'}
    </div>`;
  $('#pback').onclick = () => promoList(main);
  $('#pcopy').onclick = () => copyText(p.code, 'Код скопирован');
  $('#pcopycmd').onclick = () => copyText(`бот промокод ${p.code}`, 'Команда скопирована');
  $('#pedit').onclick = () => promoEdit(main, p);
  $('#ptoggle').onclick = async () => {
    try {
      await api(`/promo/${encodeURIComponent(p.code)}/active`, {method: 'POST', body: JSON.stringify({active: !p.is_active})});
      toast(p.is_active ? 'Выключен' : 'Включён');
      promoView(main, p.code);
    } catch (e) { toast(e.message, true); }
  };
}

function localInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Выбор образа для награды: сетка карточек в цветах палитры образа (фон, кольцо, свечение), фильтр по тиру, поиск по названию.
const SKIN_SLOTS = [['title', 'Титул'], ['name_glow', 'Ник'], ['avatar_frame', 'Рамка'], ['avatar_halo', 'Ореол'], ['profile_bg', 'Фон'], ['card_fx', 'Частицы']];
const FRAME_LINE = {ring: 'solid', dash: 'dashed', double: 'double', seg: 'dotted', drip: 'solid'};
const TIER_TITLES = {D: 'D · обычные', C: 'C · необычные', B: 'B · редкие', A: 'A · очень редкие', S: 'S · эпические', SS: 'SS · легендарные', SSS: 'SSS · высшие'};

// Мини-профиль в цветах образа: фон, рамка аватара, ореол и ник так же, как в приложении.
function skinArt(k) {
  const t = k.tokens || {}, acc = t['--v3-acc'] || (k.pal || [])[0] || '#8b7cf6', bg = t['--v3-bg'] || k.bg || '#0e0f14';
  const ink = t['--v3-ink'] || '#f4f5f8', line = FRAME_LINE[k.frame] || 'solid';
  return `<span class="skin-art" style="background:${t['--v3-wash'] ? esc(t['--v3-wash']) + ',' : ''}${esc(bg)};--sa:${esc(acc)};--sb:${esc(bg)};--si:${esc(ink)};--sl:${line}">
    <i class="skin-av"></i><span class="skin-nick">${esc((k.items && k.items.title) || k.name)}</span><b class="skin-t">${esc(k.tier)}</b></span>`;
}
function skinOwner(k) {
  if (!k.exclusive) return '';
  const h = (k.holders || [])[0];
  return h ? `<span class="chip warn">🌟 личный · у ${esc(h.name)}</span>` : '<span class="chip ok">🌟 личный · свободен</span>';
}
function skinTags(k) {
  return [skinOwner(k), k.set_name ? `<span class="chip">🧩 ${esc(k.set_name)}</span>` : '', k.season ? `<span class="chip warn">🎃 сезонный${k.season_name ? ' · ' + esc(k.season_name) : ''}</span>` : '']
    .filter(Boolean).join('');
}
function skinCard(k, on, dim = false) {
  return `<button type="button" class="skin ${on ? 'on' : ''} ${dim ? 'dim' : ''}" data-skin="${esc(k.id)}" aria-pressed="${on}" ${dim ? 'disabled' : ''}>
    ${skinArt(k)}<span class="skin-n">${esc(k.name)}</span><span class="skin-b">${esc(k.blurb || '')}</span>
    <span class="chips">${skinTags(k)}</span></button>`;
}
function skinDetail(k) {
  if (!k) return '<div class="sub">Нажмите на образ, чтобы посмотреть, из чего он состоит.</div>';
  return `<div class="skin-detail">${skinArt(k)}<div><b>${esc(k.name)}</b> <span class="sub">· ${esc(TIER_TITLES[k.tier] || k.tier)}</span>
    <div class="sub" style="margin:4px 0 6px">${esc(k.blurb || '')}</div><div class="chips">${skinTags(k)}</div>
    ${k.exclusive ? '<div class="sub" style="margin-top:6px">Достаётся одному игроку: промокод на 1 активацию или для одного игрока. Занятый образ сначала отзывают у владельца.</div>' : ''}
    <div class="skin-items">${SKIN_SLOTS.filter(([key]) => k.items && k.items[key]).map(([key, label]) =>
      `<span><small>${label}</small>${esc(k.items[key])}</span>`).join('')}</div></div></div>`;
}
function skinPicker(currentId, onPick, {noPrivate = false} = {}) {
  const box = $('#sheet'), all = OPTIONS.skins, priv = noPrivate ? [] : OPTIONS.private_skins || [], pool = [...all, ...priv];
  const filters = [['all', `Все · ${all.length}`], ...[...new Set(all.map(k => k.tier))].map(t => [t, t]),
    ['season', 'Сезонные'], ['set', 'Наборы'], ...(priv.length ? [['private', `Личные · ${priv.length}`]] : [])];
  let filter = 'all', q = '', chosen = pool.find(k => k.id === currentId) || null;
  const close = () => { box.hidden = true; box.innerHTML = ''; };
  box.innerHTML = `<div class="sheet sheet-skins"><h3>Выберите образ</h3>
    <div id="skd"></div>
    <input id="skq" placeholder="Поиск: название, набор, описание, титул" autocomplete="off"/>
    <div class="chips" id="skt"></div><div id="skg"></div>
    <div class="actions skin-bar"><button class="btn primary" id="sko">Выбрать</button><button class="btn" id="skx">Закрыть</button></div></div>`;
  box.hidden = false;
  const match = k => {
    if (filter === 'season' && !k.season) return false;
    if (filter === 'set' && !k.set) return false;
    if (filter === 'private' && !k.exclusive) return false;
    if (!['all', 'season', 'set', 'private'].includes(filter) && k.tier !== filter) return false;
    const hay = [k.name, k.blurb, k.set_name, k.season_name, ...Object.values(k.items || {})].join(' ').toLowerCase();
    return !q || hay.includes(q);
  };
  const draw = () => {
    $('#skt').innerHTML = filters.map(([key, t]) => `<span class="chip ${key === filter ? 'ok' : ''}" data-f="${esc(key)}">${esc(t)}</span>`).join('');
    const list = filter === 'private' ? [] : all.filter(match), tiers = [...new Set(list.map(k => k.tier))];
    const privList = ['all', 'private'].includes(filter) || q ? priv.filter(match) : [];
    $('#skg').innerHTML = (tiers.map(t => `<h3 class="sec">${esc(TIER_TITLES[t] || t)} · ${list.filter(k => k.tier === t).length}</h3>
      <div class="skin-grid">${list.filter(k => k.tier === t).map(k => skinCard(k, chosen && k.id === chosen.id)).join('')}</div>`).join('')
      || (privList.length ? '' : '<div class="sub" style="margin-top:12px">Ничего не нашлось.</div>'))
      + (privList.length ? `<h3 class="sec">Личные образы · ${privList.length}</h3>
        <div class="sub">У каждого один владелец: промокод с таким образом — на 1 активацию или для одного игрока. Занятый образ сначала отзывают у владельца.</div>
        <div class="skin-grid">${privList.map(k => skinCard(k, chosen && k.id === chosen.id, (k.holders || []).length > 0)).join('')}</div>` : '');
    $('#skd').innerHTML = skinDetail(chosen);
    $('#sko').disabled = !chosen;
  };
  draw();
  $('#skq').oninput = e => { q = e.target.value.trim().toLowerCase(); draw(); };
  $('#skt').onclick = e => { const c = e.target.closest('[data-f]'); if (c) { filter = c.dataset.f; draw(); } };
  $('#skg').onclick = e => {
    const b = e.target.closest('[data-skin]');
    if (b) { chosen = pool.find(k => k.id === b.dataset.skin) || chosen; draw(); const d = $('#skd'); if (d && d.scrollIntoView) d.scrollIntoView({block: 'nearest'}); }
  };
  $('#sko').onclick = () => { if (chosen) { close(); onPick(chosen.id); } };
  $('#skx').onclick = close;
  box.onclick = e => { if (e.target === box) close(); };
}

// Как игрок увидит ответ бота и что стоит перепроверить (код при этом не сохраняется).
const promoWarnings = list => list.map(w => `<div class="chip warn" style="display:block;margin-top:8px;border-radius:12px">${esc(w)}</div>`).join('');
function promoPreviewHtml(pv) {
  return `<div class="sub">Так бот ответит игроку:</div>
    <div class="card" style="margin:8px 0">🎟 Промокод <b>${esc(pv.code)}</b> активирован!
      <div style="border-left:3px solid var(--accent);padding-left:10px;margin-top:6px">${pv.player_text.map(esc).join('<br>')}</div></div>
    <div class="sub">Кто может: ${esc(pv.who_can)}.</div>${promoWarnings(pv.warnings)}`;
}

async function promoEdit(main, p, {bulk = false} = {}) {
  OPTIONS = OPTIONS || await api('/promo-options');
  const isNew = !p;
  bulk = bulk && isNew;
  const state = {
    rewards: p && p.rewards.length ? p.rewards.map(r => ({...r})) : [{type: 'mora', amount: ''}],
    chats: p ? p.chats.map(c => ({...c})) : [],
  };
  main.innerHTML = `
    <div class="bar"><button class="btn" id="pback">← Назад</button></div>
    <div class="card">
      <h3>${bulk ? 'Пачка одноразовых кодов' : isNew ? 'Новый промокод' : 'Промокод ' + esc(p.code)}</h3>
      ${bulk ? `<div class="sub" style="margin-bottom:10px">Много разных кодов с одной наградой. Каждый сработает один раз: удобно раздавать в конкурсах и в подарок.</div>
        <div class="grid2"><div class="field"><label>Начало кода (необязательно)</label>
          <input id="fprefix" maxlength="16" placeholder="например, EVENT" style="text-transform:uppercase"/></div>
        <div class="field"><label>Сколько кодов (1–200)</label><input id="fcount" type="number" min="1" max="200" value="10"/></div></div>`
      : isNew ? `<div class="field"><label>Код (латиница, цифры, - и _)</label>
        <div class="bar" style="margin:0"><input id="fcode" maxlength="32" style="text-transform:uppercase"/>
        <button class="btn" id="fgen">Случайный</button></div></div>` : ''}
      <div class="field"><label>Награды</label><div id="frewards"></div>
        <button class="btn small" id="fadd">+ Награда</button></div>
      <div class="grid2">
        ${bulk ? '' : `<div class="field"><label>Лимит активаций (0 — без лимита)</label><input id="fmax" type="number" min="0" value="${p ? p.max_activations : 0}"/></div>
        <div class="field switch"><input id="factive" type="checkbox" ${!p || p.is_active ? 'checked' : ''}/><label for="factive" style="margin:0">Включён</label></div>`}
        <div class="field"><label>Начало (необязательно)</label><input id="ffrom" type="datetime-local" value="${localInput(p && p.valid_from)}"/></div>
        <div class="field"><label>Конец (необязательно)</label><input id="funtil" type="datetime-local" value="${localInput(p && p.valid_until)}"/></div>
      </div>
      <div class="field"><label>Где активировать: пусто — везде, иначе только в выбранных чатах</label>
        <input id="fchatq" placeholder="Найти чат по названию или ID"/><div class="found" id="fchatfound"></div>
        <div class="chips" id="fchats"></div></div>
      ${bulk ? '' : `<div class="field"><label>Только для игроков: пусто — для всех</label>
        <input id="fuserq" placeholder="Найти игрока по @нику или ID"/><div class="found" id="fuserfound"></div>
        <div class="chips" id="fusers"></div></div>`}
      <div class="field"><label>Заметка для себя</label><textarea id="fnote" maxlength="300">${esc(p ? p.note : '')}</textarea></div>
      <div class="actions"><button class="btn primary" id="fsave">${bulk ? 'Создать пачку' : isNew ? 'Создать' : 'Сохранить'}</button>
        <button class="btn" id="fpreview">Как увидит игрок</button></div>
    </div>`;
  $('#pback').onclick = () => (p ? promoView(main, p.code) : promoList(main));
  if (isNew && !bulk) $('#fgen').onclick = () => {
    const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    $('#fcode').value = Array.from({length: 8}, () => abc[Math.floor(Math.random() * abc.length)]).join('');
  };

  function drawRewards() {
    $('#frewards').innerHTML = state.rewards.map((r, i) => {
      const opt = OPTIONS.rewards.find(o => o.type === r.type) || OPTIONS.rewards[0];
      const value = opt.field === 'id'
        ? `<div class="skin-pick" data-pick="${i}">${(k => k ? skinCard(k, false).replace('<button type="button"', '<div').replace('</button>', '</div>') : '<span class="sub">Образ не выбран</span>')([...OPTIONS.skins, ...(OPTIONS.private_skins || [])].find(x => x.id === r.id))}<span class="btn small">Сменить</span></div>`
        : `<input data-i="${i}" data-k="${opt.field}" type="number" min="0" step="${r.type === 'diamonds' ? '0.01' : '1'}" value="${esc(r[opt.field] ?? '')}" placeholder="Сколько"/>`;
      return `<div class="reward">
        <select data-i="${i}" data-k="type">${OPTIONS.rewards.map(o => `<option value="${o.type}" ${o.type === r.type ? 'selected' : ''}>${esc(o.title)}</option>`).join('')}</select>
        ${value}<button class="btn small danger" data-del="${i}">✕</button></div>`;
    }).join('');
  }
  drawRewards();
  $('#frewards').addEventListener('change', e => {
    const i = +e.target.dataset.i, k = e.target.dataset.k;
    if (k === 'type') { state.rewards[i] = {type: e.target.value}; if (e.target.value === 'skin') state.rewards[i].id = OPTIONS.skins[0]?.id; drawRewards(); }
    else state.rewards[i][k] = e.target.value;
  });
  $('#frewards').addEventListener('input', e => { const i = +e.target.dataset.i; if (e.target.dataset.k && e.target.dataset.k !== 'type') state.rewards[i][e.target.dataset.k] = e.target.value; });
  $('#frewards').addEventListener('click', e => {
    const pk = e.target.closest('[data-pick]');
    if (pk) skinPicker(state.rewards[+pk.dataset.pick].id, id => {
      state.rewards[+pk.dataset.pick].id = id; drawRewards();
      // Личный образ у одного владельца: сами ставим лимит 1, если админ не выбрал игрока.
      if (!bulk && (OPTIONS.private_skins || []).some(k => k.id === id) && !+$('#fmax').value && !users.length) {
        $('#fmax').value = 1; toast('Личный образ: лимит активаций поставлен в 1');
      }
    }, {noPrivate: bulk});
  });
  $('#frewards').addEventListener('click', e => { const d = e.target.closest('[data-del]'); if (d) { state.rewards.splice(+d.dataset.del, 1); drawRewards(); } });
  $('#fadd').onclick = () => { state.rewards.push({type: 'mora', amount: ''}); drawRewards(); };

  function drawChats() {
    $('#fchats').innerHTML = state.chats.length
      ? state.chats.map((c, i) => `<span class="chip" data-unchat="${i}" title="Убрать">${esc(c.title)} ✕</span>`).join('')
      : '<span class="sub">Во всех чатах и в личке с ботом</span>';
  }
  drawChats();
  $('#fchats').onclick = e => { const c = e.target.closest('[data-unchat]'); if (c) { state.chats.splice(+c.dataset.unchat, 1); drawChats(); } };
  let ct;
  $('#fchatq').oninput = e => {
    clearTimeout(ct);
    const q = e.target.value.trim();
    if (!q) { $('#fchatfound').innerHTML = ''; return; }
    ct = setTimeout(async () => {
      const {items} = await api(`/chats?q=${encodeURIComponent(q)}`);
      $('#fchatfound').innerHTML = items.filter(c => !state.chats.some(x => x.id === c.id))
        .map(c => `<button data-addchat="${c.id}" data-title="${esc(c.title)}">${esc(c.title)} <span class="sub">${c.id}</span></button>`).join('')
        || '<span class="sub">Не найдено</span>';
    }, 250);
  };
  $('#fchatfound').onclick = e => {
    const b = e.target.closest('[data-addchat]');
    if (!b) return;
    state.chats.push({id: +b.dataset.addchat, title: b.dataset.title});
    $('#fchatfound').innerHTML = ''; $('#fchatq').value = '';
    drawChats();
  };

  // Игроки-получатели: поиск по нику или ID и чипы, как у чатов (раньше нужно было вписывать ID через запятую).
  const users = ((p && p.allowed_users) || []).map(id => ({id: +id, label: 'id' + id}));
  const drawUsers = () => {
    $('#fusers').innerHTML = users.length
      ? users.map((u, i) => `<span class="chip" data-unuser="${i}" title="Убрать">${esc(u.label)} ✕</span>`).join('')
      : '<span class="sub">Для всех игроков</span>';
  };
  if (!bulk) {
    drawUsers();
    $('#fusers').onclick = e => { const c = e.target.closest('[data-unuser]'); if (c) { users.splice(+c.dataset.unuser, 1); drawUsers(); } };
    let ut;
    $('#fuserq').oninput = e => {
      clearTimeout(ut);
      const q = e.target.value.trim();
      if (!q) { $('#fuserfound').innerHTML = ''; return; }
      ut = setTimeout(async () => {
        const {players} = await api(`/search?q=${encodeURIComponent(q)}`);
        $('#fuserfound').innerHTML = players.filter(u => !users.some(x => x.id === u.id))
          .map(u => `<button data-adduser="${u.id}" data-label="${esc(u.username ? '@' + u.username : 'id' + u.id)}">${u.username ? '@' + esc(u.username) : 'id' + u.id} <span class="sub">${u.id}</span></button>`).join('')
          || '<span class="sub">Не найдено</span>';
      }, 250);
    };
    $('#fuserfound').onclick = e => {
      const b = e.target.closest('[data-adduser]');
      if (!b) return;
      users.push({id: +b.dataset.adduser, label: b.dataset.label});
      $('#fuserfound').innerHTML = ''; $('#fuserq').value = '';
      drawUsers();
    };
  }

  const toIso = v => (v ? new Date(v).toISOString() : null);
  const collect = () => {
    const common = {rewards: state.rewards, valid_from: toIso($('#ffrom').value), valid_until: toIso($('#funtil').value),
      allowed_chats: state.chats.map(c => c.id), note: $('#fnote').value};
    return bulk
      ? {...common, prefix: $('#fprefix').value.trim().toUpperCase(), count: +$('#fcount').value || 0}
      : {...common, code: isNew ? $('#fcode').value.trim().toUpperCase() : p.code, max_activations: +$('#fmax').value || 0,
         is_active: $('#factive').checked, allowed_users: users.map(u => u.id)};
  };
  // Предпросмотр у сервера: он же знает, что считается «слишком много». Сохранять он не мешает.
  const preview = body => api('/promo/preview', {method: 'POST', body: JSON.stringify(bulk ? {...body, max_activations: 1} : body)});

  $('#fpreview').onclick = async () => {
    try {
      const pv = await preview(collect());
      sheet('Как увидит игрок', promoPreviewHtml(pv) + (bulk ? '<div class="sub" style="margin-top:8px">Каждый код сработает один раз.</div>' : ''),
        'Понятно', () => {}, {info: true});
    } catch (err) { toast(err.message, true); }
  };

  $('#fsave').onclick = async e => {
    const btn = e.currentTarget;
    if (btn.disabled) return;
    const body = collect();
    const save = async () => {
      btn.disabled = true;   // повторный клик во время запроса не должен пытаться создать код второй раз
      try {
        if (bulk) {
          const made = await api('/promo/bulk', {method: 'POST', body: JSON.stringify(body)});
          toast(`Создано кодов: ${made.codes.length}`);
          promoBulkDone(main, made, body.prefix);
          return;
        }
        const saved = isNew
          ? await api('/promo', {method: 'POST', body: JSON.stringify(body)})
          : await api(`/promo/${encodeURIComponent(p.code)}`, {method: 'PUT', body: JSON.stringify(body)});
        toast(isNew ? 'Промокод создан' : 'Сохранено');
        promoView(main, saved.code);
      } catch (err) { toast(err.message, true); btn.disabled = false; }
    };
    let warnings = [];
    try { warnings = (await preview(body)).warnings; } catch (err) { toast(err.message, true); return; }
    if (!warnings.length) return save();
    sheet('Проверьте перед сохранением', `<div class="sub">Код сработает, но вот что стоит перепроверить:</div>${promoWarnings(warnings)}`,
      bulk ? 'Всё верно, создать' : 'Всё верно, сохранить', async () => { await save(); }, {cancelText: 'Вернуться'});
  };
}

// Готовая пачка: все коды списком, чтобы сразу скопировать или сохранить файлом и раздать.
function promoBulkDone(main, made, prefix) {
  const text = made.codes.join('\n');
  const canDownload = !window.Telegram?.WebApp?.initData;   // в Telegram файлы не скачать, там только копирование
  main.innerHTML = `
    <div class="bar"><button class="btn" id="pback">← Все промокоды</button></div>
    <div class="card"><h3>Пачка готова · ${made.codes.length}</h3>
      <div>${made.rewards_text.map(r => `<div>${esc(r)}</div>`).join('')}</div>
      <div class="sub" style="margin:6px 0 10px">Каждый код сработает один раз. Игрок пишет боту: «бот промокод КОД».</div>
      <div class="field"><label>Коды (по одному в строке)</label>
        <textarea id="bcodes" readonly rows="${Math.min(12, made.codes.length + 1)}" style="font-family:ui-monospace,Menlo,monospace">${esc(text)}</textarea></div>
      <div class="actions"><button class="btn primary" id="bcopy">Копировать все</button>
        ${canDownload ? '<button class="btn" id="bsave">Скачать .txt</button>' : ''}
        <button class="btn" id="blist">Открыть в списке</button></div>
    </div>`;
  $('#pback').onclick = () => promoList(main);
  $('#blist').onclick = () => promoList(main, prefix || '');
  $('#bcopy').onclick = () => copyText(text, 'Коды скопированы');
  if (canDownload) $('#bsave').onclick = () => {
    const url = URL.createObjectURL(new Blob([text + '\n'], {type: 'text/plain;charset=utf-8'}));
    const a = Object.assign(document.createElement('a'), {href: url, download: `promo-${prefix || 'codes'}-${made.codes.length}.txt`});
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  };
}

SECTIONS.promo = main => promoList(main);

// ── Функции: выключатели бота и сайта ────────────────────────────────────────

async function switchesView(main, chat = null) {
  const data = await loadSectionData(main, `/switches?chat_id=${chat ? chat.id : 0}`, () => switchesView(main, chat), 'switches');
  if (!data) return;
  const off = data.state;   // {global: {key: {reason}}, chat: {...}}
  const scopeName = chat ? `в чате «${esc(chat.title)}»` : 'везде';
  const row = (item, nested = false) => {
    if (!item.key) return '';
    const globalOff = off.global[item.key];
    const localOff = chat ? off.chat[item.key] : globalOff;
    const enabled = !localOff && !(chat && globalOff);
    const locked = chat && globalOff;
    const why = (localOff || globalOff || {}).reason;
    return `<div class="sw-row ${enabled ? '' : 'off'}">
      <div class="t"><b>${esc(item.title)}</b>${item.hint && item.hint !== 'Весь раздел' ? `<div class="sub">${esc(item.hint)}</div>` : ''}
        ${locked ? '<div class="locked">выключено везде — включается только во «Везде»</div>' : ''}
        ${!enabled && why ? `<div class="sub">Причина: ${esc(why)}</div>` : ''}</div>
      <label class="toggle"><input type="checkbox" data-sw="${esc(item.key)}" ${enabled ? 'checked' : ''} ${locked ? 'disabled' : ''}/><span></span></label>
    </div>`;
  };
  const group = item => item.items && item.items.length
    ? `<details class="sw-group"><summary>${row(item) || `<div class="sw-row"><div class="t"><b>${esc(item.title)}</b></div></div>`}</summary>
        <div class="sw-sub">${item.items.map(x => row(x, true)).join('')}</div></details>`
    : row(item);
  // Раскрытые группы запоминаем: после каждого переключателя экран рисуется заново, и они сворачивались.
  const opened = new Set([...main.querySelectorAll('details.sw-group[open] > summary b')].map(b => b.textContent));
  main.innerHTML = `
    <div class="scope"><span class="sub">Где:</span>
      <button class="btn small ${chat ? '' : 'primary'}" id="sglobal">Везде</button>
      ${chat ? `<span class="chip ok">${esc(chat.title)}</span>` : ''}
      <input id="schatq" placeholder="Выбрать чат…" style="flex:1;min-width:140px"/></div>
    <div class="found" id="schatfound"></div>
    <div class="field"><label>Причина для игроков, когда выключаете (необязательно)</label>
      <input id="sreason" maxlength="200" placeholder="Например: чиним, вернём вечером"/></div>
    ${data.catalog.filter(g => !(chat && g.scope === 'site')).map(g => `
      <div class="card"><h3>${esc(g.title)} · ${scopeName}</h3>${g.items.map(group).join('')}</div>`).join('')}
    ${chat ? '<div class="sub">Сайт выключается только целиком для всех — переключитесь на «Везде».</div>' : ''}`;
  main.querySelectorAll('details.sw-group').forEach(d => { if (opened.has(d.querySelector('summary b')?.textContent)) d.open = true; });
  $('#sglobal').onclick = () => switchesView(main, null);
  let t;
  $('#schatq').oninput = e => {
    clearTimeout(t);
    const q = e.target.value.trim();
    if (!q) { $('#schatfound').innerHTML = ''; return; }
    t = setTimeout(async () => {
      const {items} = await api(`/chats?q=${encodeURIComponent(q)}`);
      $('#schatfound').innerHTML = items.map(c => `<button data-pick="${c.id}" data-title="${esc(c.title)}">${esc(c.title)} <span class="sub">${c.id}</span></button>`).join('') || '<span class="sub">Не найдено</span>';
    }, 250);
  };
  $('#schatfound').onclick = e => {
    const b = e.target.closest('[data-pick]');
    if (b) switchesView(main, {id: +b.dataset.pick, title: b.dataset.title});
  };
  main.querySelectorAll('[data-sw]').forEach(input => {
    input.addEventListener('click', e => e.stopPropagation());
    input.onchange = async () => {
      const enabled = input.checked;
      if (!enabled && input.dataset.sw === 'all' || !enabled && input.dataset.sw === 'site') {
        if (!confirm(input.dataset.sw === 'all' ? 'Выключить весь бот ' + (chat ? 'в этом чате' : 'во всех чатах') + '?' : 'Закрыть весь сайт для игроков?')) {
          input.checked = true; return;
        }
      }
      try {
        await api('/switches', {method: 'POST', body: JSON.stringify({
          feature: input.dataset.sw, chat_id: chat ? chat.id : 0, enabled, reason: $('#sreason').value})});
        toast(enabled ? 'Включено' : 'Выключено');
        switchesView(main, chat);
      } catch (err) { toast(err.message, true); input.checked = !enabled; }
    };
  });
}

SECTIONS.switches = main => switchesView(main);

// ── Настройки бота ───────────────────────────────────────────────────────────

function reportSettingsCard(data) {
  const r = data.reports, o = data.report_options;
  const select = (id, value, list, offTitle) => `<select id="${id}">${offTitle ? `<option value="0" ${!value ? 'selected' : ''}>${offTitle}</option>` : ''}
    ${list.map(x => `<option value="${x.value}" ${x.value === value ? 'selected' : ''}>${esc(x.title)}</option>`).join('')}</select>`;
  return `<div class="card" id="repset"><h3>Жалобы</h3>
    <div class="sub" style="margin-bottom:6px">Жалоба анонимна: игроки в чате и нарушитель не видят, кто пожаловался. Бот убирает команду из чата (нужно право удалять сообщения) и отвечает автору в личку.</div>
    <div class="sw-row ${r.to_admin_chat ? '' : 'off'}"><div class="t"><b>Отчёт в админ-чат</b><div class="sub">Если к чату привязан админ-чат, жалоба приходит туда без имени автора.</div></div>
      <label class="toggle"><input type="checkbox" id="rs-admin" ${r.to_admin_chat ? 'checked' : ''}/><span></span></label></div>
    <div class="field"><label>Отчёт в личку модераторам чата — с ранга в чате</label>${select('rs-chat', r.dm_chat_rank, o.chat_ranks, 'Не писать в личку')}</div>
    <div class="field"><label>Отчёт в личку персоналу бота — с роли</label>${select('rs-staff', r.dm_staff_rank, o.staff_ranks, 'Не писать в личку')}</div>
    <div class="field"><label>Автора жалобы в админке видят — с роли</label>${select('rs-see', r.reporter_min_rank, o.staff_ranks, '')}
      <div class="sub">Остальные видят «автор скрыт». В личку пишем только тем, кто открывал диалог с ботом.</div></div>
    <div class="actions"><button class="btn primary" id="rs-save">Сохранить</button></div></div>`;
}
function bindReportSettings(main, data) {
  const save = main.querySelector('#rs-save');
  if (!save) return;
  save.onclick = async () => {
    const body = {to_admin_chat: main.querySelector('#rs-admin').checked, dm_chat_rank: +main.querySelector('#rs-chat').value,
      dm_staff_rank: +main.querySelector('#rs-staff').value, reporter_min_rank: +main.querySelector('#rs-see').value};
    try { await api('/settings/reports', {method: 'POST', body: JSON.stringify(body)}); toast('Сохранено'); settingsView(main); }
    catch (e) { toast(e.message, true); }
  };
}

function securityCard() {
  return `<div class="card" id="secset"><h3>🔐 Безопасность</h3>
    <div class="sub" style="margin-bottom:8px">Если потеряли телефон или вошли с чужого устройства, завершите сессии: админку придётся открыть заново через Telegram.
      Опасные действия (бан во всех чатах, смена роли, крупная выдача) просят ввести ID игрока, а при необычной активности владельцам приходит сообщение в личку.</div>
    <div class="actions"><button class="btn" id="revself">Выйти на всех моих устройствах</button>
      ${ME.creator ? '<button class="btn danger" id="revall">Завершить сессии всех сотрудников</button>' : ''}</div></div>`;
}
function bindSecurityCard(main) {
  const run = (title, text, all) => sheet(title, `<div class="sub">${text}</div>`, 'Завершить', async () => {
    const res = await api('/sessions/revoke', {method: 'POST', body: JSON.stringify({all})});
    main.innerHTML = `<div class="empty">✅ ${esc(res.message)}</div>`;
  });
  const own = main.querySelector('#revself'), all = main.querySelector('#revall');
  if (own) own.onclick = () => run('Выйти на всех устройствах', 'Админка закроется везде, где она открыта, включая этот экран. Роль не меняется.', false);
  if (all) all.onclick = () => run('Сессии всех сотрудников', 'Все сотрудники, включая вас, выйдут из админки и откроют её заново. Роли не меняются.', true);
}

async function settingsView(main) {
  const data = await loadSectionData(main, '/settings', () => settingsView(main), 'settings');
  if (!data) return;
  main.innerHTML = `
    <div class="card"><h3>Переводы между игроками</h3>
      <div class="sub" style="margin-bottom:6px">Какие валюты можно отправить командой «бот перевод».</div>
      ${data.transfer.map(c => `<div class="sw-row ${c.enabled ? '' : 'off'}">
        <div class="t"><b>${esc(c.title)}</b>${c.locked ? '<div class="sub">Переводить нельзя никогда</div>' : ''}</div>
        <label class="toggle"><input type="checkbox" data-cur="${c.code}" ${c.enabled ? 'checked' : ''} ${c.locked ? 'disabled' : ''}/><span></span></label>
      </div>`).join('')}
    </div>
    ${reportSettingsCard(data)}
    ${securityCard()}`;
  bindReportSettings(main, data);
  bindSecurityCard(main);
  main.querySelectorAll('[data-cur]').forEach(input => {
    input.onchange = async () => {
      const currencies = [...main.querySelectorAll('[data-cur]')].filter(x => x.checked && !x.disabled).map(x => x.dataset.cur);
      try { await api('/settings/transfer', {method: 'POST', body: JSON.stringify({currencies})}); toast('Сохранено'); settingsView(main); }
      catch (e) { toast(e.message, true); input.checked = !input.checked; }
    };
  });
}

SECTIONS.settings = main => settingsView(main);

// ── Состояние ────────────────────────────────────────────────────────────────

const duration = sec => {
  const d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600), m = Math.floor(sec % 3600 / 60);
  return d ? `${d} д ${h} ч` : h ? `${h} ч ${m} мин` : `${m} мин`;
};

async function healthView(main) {
  const h = await loadSectionData(main, '/health', () => healthView(main), 'health');
  if (!h) return;
  const tg = h.telegram, dot = ok => `<span class="chip ${ok ? 'ok' : 'bad'}">${ok ? 'работает' : 'не отвечает'}</span>`;
  const row = (title, value, sub = '') => `<div class="log"><div>${title} <b>${value}</b></div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
  const dg = h.digest;
  main.innerHTML = `
    ${pageHead('♥', 'Состояние', 'Живы ли бот, база и очереди')}
    ${tg && !tg.ok ? alertBox('bad', '<b>Telegram не отвечает.</b> Бот не получает и не отправляет сообщения: ' + esc(tg.error || 'причина не указана')) : ''}
    <div class="kpis hero">
      ${kpi('🤖 Telegram', tg ? (tg.ok ? 'работает' : 'не отвечает') : '—', tg && tg.ok ? `<small> ${tg.ms} мс</small>` : '', tg ? (tg.ok ? 'ok' : 'bad') : '')}
      ${kpi('🗄 База', `${h.database.ms} мс`)}${kpi('⏱ Работает', duration(h.process.uptime_seconds))}${kpi('⚠️ Ошибок за сутки', num(h.errors.count_24h))}</div>
    <p class="sub note">Ошибки и время работы считаются с последнего перезапуска: каждый выкат новой версии обнуляет их, поэтому «0» сразу после выката ничего не доказывает.</p>
    <section class="section" data-sec="h-bot"><h3 class="sec-h">🤖 Бот</h3>
      ${row('Telegram', tg ? dot(tg.ok) : '—', tg ? (tg.ok ? `@${esc(tg.username)} · ответ ${tg.ms} мс` : esc(tg.error)) : '')}
      ${row('Работает', duration(h.process.uptime_seconds), `с ${when(h.process.started_at)} · Python ${esc(h.process.python)}${h.process.commit ? ` · версия ${esc(h.process.commit)}` : ''}`)}
      ${row('База данных', `${h.database.ms} мс`, h.database.pool && h.database.pool.size != null ? `соединений занято ${h.database.pool.size - h.database.pool.idle} из ${h.database.pool.size} (максимум ${h.database.pool.max})` : '')}
    </section>
    <section class="section" data-sec="h-err"><h3 class="sec-h">⚠️ Ошибки за сутки <small class="cnt">· ${num(h.errors.count_24h)}</small></h3>
      ${h.errors.recent.length ? h.errors.recent.map(e => `<div class="log"><div>${esc(e.text)}</div><div class="sub">${when(e.at)}</div></div>`).join('')
        : '<div class="sub">Ошибок нет. Считаются с последнего перезапуска.</div>'}
      ${h.errors.count_24h > h.errors.recent.length ? `<div class="sub">Показаны последние ${h.errors.recent.length}.</div>` : ''}
    </section>
    <section class="section" data-sec="h-chats"><h3 class="sec-h">💬 Чаты и игроки</h3>
      ${row('Чатов с ботом', num(h.chats.active))}
      ${row('Бота удалили из чатов', num(h.chats.left), h.chats.left ? 'В рассылки они не попадают. <a href="#" data-attn="left">Какие чаты</a>' : '')}
      ${row('Без прав модерации', num(h.chats.no_rights), h.chats.no_rights ? 'Бот там не админ или не может удалять и блокировать: мут, бан и чистка не сработают. <a href="#" data-attn="no_rights">Какие чаты</a>' : '')}
      ${row('Тихих чатов (30 дней без сообщений)', num(h.chats.quiet), h.chats.quiet ? '<a href="#" data-attn="quiet">Какие чаты</a>' : '')}
      ${row('Игроков', num(h.players.total))}
      ${row('Заблокировали бота', num(h.players.blocked_bot), h.players.blocked_bot ? 'В личку им рассылка не уходит.' : '')}
    </section>
    <section class="section" data-sec="h-queues"><h3 class="sec-h">📬 Очереди</h3>
      ${row('Рассылок идёт', num(h.queues.broadcasts_running))}
      ${row('Рассылок запланировано', num(h.queues.broadcasts_scheduled))}
      ${row('Открытых жалоб', num(h.queues.reports_open))}
    </section>
    <details class="section" data-sec="h-digest" ${FOLD.get('h-digest') ? 'open' : ''}><summary class="sec-h">🌅 Итоги дня владельцу</summary><div class="sec-body">
      <div class="sub" style="margin-bottom:8px">Раз в сутки бот пишет владельцу в личку: новые игроки, сообщения, команды, жалобы, ошибки, чаты без прав.</div>
      <div class="field switch"><input type="checkbox" id="dgon" ${dg.enabled ? 'checked' : ''} ${dg.can_edit ? '' : 'disabled'}/><label for="dgon" style="margin:0">Присылать итоги дня</label></div>
      <div class="field"><label>Во сколько (по времени бота)</label><select id="dghour" ${dg.can_edit ? '' : 'disabled'}>
        ${Array.from({length: 24}, (_, i) => `<option value="${i}" ${i === dg.hour ? 'selected' : ''}>${String(i).padStart(2, '0')}:00</option>`).join('')}</select></div>
      ${dg.can_edit ? '' : '<div class="sub">Настраивает только владелец.</div>'}
      <div class="actions"><button class="btn" id="dgtest">✉️ Прислать мне за вчера</button></div>
    </div></details>`;
  const ATTN_TITLES = {left: 'Бота удалили из чатов', no_rights: 'Без прав модерации', quiet: 'Тихие чаты'};
  main.querySelectorAll('[data-attn]').forEach(a => a.onclick = e => {
    e.preventDefault();
    attentionSheet(a.dataset.attn, ATTN_TITLES[a.dataset.attn]).catch(err => toast(err.message, true));
  });
  const save = async () => {
    try {
      await api('/health/digest', {method: 'POST', body: JSON.stringify({enabled: $('#dgon').checked, hour: +$('#dghour').value})});
      toast('Сохранено');
    } catch (e) { toast(e.message, true); }
  };
  $('#dgon').onchange = save; $('#dghour').onchange = save;
  $('#dgtest').onclick = async () => {
    $('#dgtest').disabled = true;
    try { toast((await api('/health/digest/test', {method: 'POST'})).message); } catch (e) { toast(e.message, true); }
    $('#dgtest').disabled = false;
  };
}

SECTIONS.health = main => healthView(main);

// ── Старт ────────────────────────────────────────────────────────────────────

(async () => {
  if (TG) { try { TG.ready(); TG.expand(); } catch (_) {} }
  showSectionLoading($('#main'), 'start');
  try {
    ME = await api('/me');
  } catch (e) {
    $('#main').innerHTML = accessMarkup(e);
    const again = $('#main .load-retry');
    if (again) again.onclick = () => location.reload();
    return;
  }
  $('#who').textContent = ME.rank_name;
  const top = $('.top');
  const headBtn = (cls, label, text, handler) => { const b = document.createElement('button'); b.type = 'button'; b.className = 'hbtn ' + cls; b.setAttribute('aria-label', label); b.title = label; b.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${text}</svg>`; b.onclick = handler; top.append(b); };
  headBtn('theme', 'Оформление', '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/>', themeSheet);
  if (window.matchMedia && matchMedia('(pointer: fine)').matches) headBtn('keys', 'Горячие клавиши (?)', '<rect x="3" y="6.5" width="18" height="11" rx="2.5"/><path d="M7 10.5h.01M10.5 10.5h.01M14 10.5h.01M17 10.5h.01M8 14h8"/>', hotkeysSheet);
  if (!ME.sections.length) { $('#main').innerHTML = '<div class="empty">Для вашей роли разделов пока нет.</div>'; return; }
  let saved = '';
  try { saved = localStorage.getItem('pv_admin_tab') || ''; } catch (_) {}
  open(ME.sections.some(s => s.key === saved) ? saved : ME.sections[0].key);
  refreshBadges();
  setInterval(() => { if (!document.hidden) refreshBadges(); }, 60000);
})();
