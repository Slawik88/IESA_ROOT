// Админка Предвестника 3.0 — ядро (docs/audits/ADMIN_V3_REDESIGN_2026-10-20.md).
// Здесь: запросы, роутер с адресами экранов (#/player/123), оболочка (шапка, док, «Ещё»), стек шторок,
// общие компоненты разметки и безопасные действия над людьми. Разделы — в admin-home/people/lists/ops.js,
// старт — admin-boot.js. Разделы приходят с сервера (/me) по роли; каждый запрос проверяется сервером отдельно.
'use strict';

const BASE = window.ADMIN_BASE || '';
const TG = window.Telegram && window.Telegram.WebApp;
const INIT = (TG && TG.initData) || '';
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const num = n => Number(n || 0).toLocaleString('ru-RU');
const coarse = () => !!(window.matchMedia && matchMedia('(pointer: coarse)').matches);
const newRid = () => (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()) + Math.random();

// Склонение: plural(5, 'жалоба', 'жалобы', 'жалоб') → «жалоб».
function plural(n, one, few, many) {
  const a = Math.abs(n) % 100, b = a % 10;
  return a > 10 && a < 20 ? many : b === 1 ? one : b >= 2 && b <= 4 ? few : many;
}
function when(iso) {
  return iso ? new Date(iso).toLocaleString('ru-RU', {dateStyle: 'short', timeStyle: 'short'}) : '';
}
// «5 мин назад», «вчера 14:20», «12 окт» — глазу проще, чем 12.10.2026, 14:20.
function ago(iso) {
  if (!iso) return '';
  const t = new Date(iso), s = (Date.now() - t) / 1000;
  if (Number.isNaN(s)) return '';
  if (s < 0) return 'через ' + left(iso);
  if (s < 60) return 'только что';
  if (s < 3600) return Math.floor(s / 60) + ' мин назад';
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const hm = t.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'});
  if (t >= today) return 'сегодня ' + hm;
  if (t >= today - 864e5) return 'вчера ' + hm;
  if (s < 30 * 86400) return t.toLocaleDateString('ru-RU', {day: 'numeric', month: 'short'}) + ' ' + hm;
  return t.toLocaleDateString('ru-RU', {day: 'numeric', month: 'short', year: 'numeric'});
}
function left(iso) {   // сколько осталось до срока: «2 ч», «3 дн.»
  const s = (new Date(iso) - Date.now()) / 1000;
  if (s <= 0) return 'истёк';
  if (s < 3600) return Math.ceil(s / 60) + ' мин';
  if (s < 86400) return Math.round(s / 3600) + ' ч';
  return Math.round(s / 86400) + ' дн.';
}
// Срок наказания: дата и сколько осталось — «ещё 3 дн.» читается быстрее, чем считать от сегодняшней даты.
const untilText = iso => iso ? 'до ' + new Date(iso).toLocaleString('ru-RU', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}) + ` · ещё ${left(iso)}` : 'навсегда';
// Крупные числа коротко: 1 234 567 → «1,2 млн». Точное значение — в подсказке.
function short(n) {
  n = Number(n || 0);
  const a = Math.abs(n), f = (x, u) => (Math.round(x * 10) / 10).toLocaleString('ru-RU') + ' ' + u;
  return a >= 1e9 ? f(n / 1e9, 'млрд') : a >= 1e6 ? f(n / 1e6, 'млн') : a >= 1e4 ? f(n / 1e3, 'тыс.') : num(n);
}
const isFresh = (iso, hours = 24) => !!iso && Date.now() - new Date(iso) < hours * 3600e3;
function dur(sec) {
  sec = Math.round(sec || 0);
  if (sec < 60) return `${sec} с`;
  const m = Math.floor(sec / 60), h = Math.floor(m / 60);
  if (h) return `${num(h)} ч ${m % 60} мин`;
  return m >= 10 || !(sec % 60) ? `${m} мин` : `${m} мин ${sec % 60} с`;
}

// Личные настройки на этом устройстве: тема, фильтры, недавние люди и причины. Без хранилища всё работает по умолчанию.
const PREFS = (() => {
  let data = {};
  try { data = JSON.parse(localStorage.getItem('pv_admin_prefs') || '{}') || {}; } catch (_) {}
  return {
    get: (key, fallback) => (key in data ? data[key] : fallback),
    set(key, value) { data[key] = value; try { localStorage.setItem('pv_admin_prefs', JSON.stringify(data)); } catch (_) {} },
  };
})();

let ME = null;
const has = key => !!(ME && ME.sections && ME.sections.some(s => s.key === key));

// ── Запросы ──────────────────────────────────────────────────────────────────

async function api(path, opts = {}) {
  const headers = {'content-type': 'application/json'};
  if (INIT) headers['x-init-data'] = INIT;
  try { const s = localStorage.getItem('pv_sess'); if (s) headers['x-session-token'] = s; } catch (_) {}
  const write = opts.method && opts.method !== 'GET';
  // Запись не крутится бесконечно: через 20 с — ошибка и повтор с тем же ключом запроса (сервер не выполнит дважды).
  let timer = null, signal = opts.signal;
  if (write && !signal) { const c = new AbortController(); signal = c.signal; timer = setTimeout(() => c.abort(), 20000); }
  try {
    const res = await fetch(`${BASE}/bot-admin/api${path}`, {...opts, signal, headers});
    let data = null;
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) throw Object.assign(new Error((data && data.detail) || `Ошибка ${res.status}`), {status: res.status});
    if (write && typeof CACHE !== 'undefined') CACHE.clear();   // после любого изменения «назад» не покажет старые данные
    return data;
  } catch (e) {
    if (e.name === 'AbortError' && write) throw Object.assign(new Error('Сервер не ответил за 20 с. Проверьте результат и повторите — дважды не выполнится.'), {status: 0});
    throw e;
  } finally { clearTimeout(timer); }
}
const post = (path, body = {}) => api(path, {method: 'POST', body: JSON.stringify(body)});

// ── Отклик: тост с действием ─────────────────────────────────────────────────

function toast(text, opt = {}) {
  if (opt === true) opt = {bad: true};
  const t = $('#toast');
  t.className = 'toast' + (opt.bad ? ' bad' : opt.ok ? ' ok' : '');
  t.innerHTML = `<span>${esc(text)}</span>${opt.action ? `<button type="button">${esc(opt.action[0])}</button>` : ''}`;
  if (opt.action) t.querySelector('button').onclick = () => { t.hidden = true; opt.action[1](); };
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, opt.bad ? 6500 : opt.action ? 5000 : 3000);   // ошибку дольше: её надо успеть прочитать
  haptic(opt.bad ? 'error' : 'success');
}
function haptic(kind) {
  try {
    const h = TG && TG.HapticFeedback;
    if (!h) return;
    if (kind === 'select') h.selectionChanged();
    else if (kind === 'light' || kind === 'medium') h.impactOccurred(kind);
    else h.notificationOccurred(kind);
  } catch (_) {}
}
// Копирование: современный API, а где он закрыт (старые WebView) — через скрытое поле.
async function copyText(text, done = 'Скопировано') {
  try { await navigator.clipboard.writeText(text); toast(done, {ok: true}); return true; } catch (_) {}
  try {
    const field = Object.assign(document.createElement('textarea'), {value: text});
    field.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
    document.body.append(field); field.select();
    const ok = document.execCommand('copy');
    field.remove();
    if (ok) { toast(done, {ok: true}); return true; }
  } catch (_) {}
  toast('Не удалось скопировать: выделите текст и скопируйте вручную', true);
  return false;
}

// ── Значки ───────────────────────────────────────────────────────────────────

const ICONS = {
  home: '<path d="M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1z"/>',
  people: '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c.7-3.2 3-4.8 5.5-4.8s4.8 1.6 5.5 4.8M16 5.5a3 3 0 0 1 0 5.8M17.5 14.6c1.8.5 3 2 3.5 4.4"/>',
  reports: '<path d="M5.5 21V4M5.5 5h11l-2 3.5 2 3.5h-11"/>',
  metrics: '<path d="M4.5 20v-7h4.5v7M9.8 20V5h4.4v15M15 20v-9.5h4.5V20"/>',
  journal: '<path d="M5 5.5h14M5 10.5h14M5 15.5h9M5 20.5h6"/>',
  broadcast: '<path d="M4 10v4h3l7 4V6l-7 4zM17 9.5a3.5 3.5 0 0 1 0 5"/>',
  promo: '<path d="M3.5 12.5v-8h8l9 9-8 8z"/><circle cx="8" cy="9" r="1.2"/>',
  switches: '<rect x="3" y="7" width="18" height="10" rx="5"/><circle cx="16" cy="12" r="2.4"/>',
  settings: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  health: '<path d="M3 12h4l2.5-6 4 12 2.5-6H21"/>',
  mychats: '<path d="M4 5.5h16v10H9l-5 4z"/>',
  access: '<path d="M12 3.5 5 6v5.5c0 4.2 2.8 7.4 7 9 4.2-1.6 7-4.8 7-9V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
  more: '<circle cx="6" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="18" cy="12" r="1.3"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  back: '<path d="m14.5 5-7 7 7 7"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  copy: '<rect x="8" y="8" width="11" height="11" rx="2.5"/><path d="M5 15.5V6a1 1 0 0 1 1-1h9.5"/>',
  theme: '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/>',
  keys: '<rect x="3" y="6.5" width="18" height="11" rx="2.5"/><path d="M7 10.5h.01M10.5 10.5h.01M14 10.5h.01M17 10.5h.01M8 14h8"/>',
  out: '<path d="M14 5h4a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1h-4M10 16l-4-4 4-4M6 12h9"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  send: '<path d="M4 12 20 4l-4 16-4-6.5z"/>',
  filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  trash: '<path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12"/>',
};
const icon = (key, cls = 'ico') => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[key] || ICONS.more}</svg>`;

// ── Компоненты разметки (строки). Обработчики — через data-on="имя" и on(view, {...}). ──

const hue = id => Math.abs(Number(id) || 0) * 47 % 360;   // один человек — всегда один цвет кружка
const initial = s => (String(s || '?').replace(/^[@#\s]+/, '').trim().charAt(0) || '?').toUpperCase();
const pic = url => url ? esc(BASE + url) : '';
const who = (id, username) => username ? '@' + esc(username) : 'id' + id;
const nameOf = p => p.name || (p.username ? '@' + p.username : 'id' + p.id);
// Лицо человека. Кольцо вокруг — его состояние, видно не читая: красное — бан или «бот молчит»,
// янтарное — мут или предупреждения. Зелёная точка — писал за последние сутки.
function ringOf(p) {
  const f = p.flags;
  if (p.ring) return p.ring;
  if (!f) return '';
  return f.global_ban || f.bans || f.blocked ? 'bad' : f.muted || f.warns ? 'warn' : '';
}
function ava(p, size = '') {
  const photo = p.avatar ? `<img src="${pic(p.avatar)}" alt="" loading="lazy" decoding="async" onerror="this.remove()"/>` : '';
  const ring = ringOf(p);
  const dot = p.dot ? '<i class="dot"></i>' : p.online ? '<i class="dot on"></i>' : '';
  return `<span class="ava ${size}${ring ? ' ring-' + ring : ''}" style="--h:${hue(p.id)}" aria-hidden="true">${esc(initial(p.name || p.username || p.id))}${photo}${dot}</span>`;
}
// Чат — квадрат со скруглением: фото группы, если оно есть, иначе цветная буква (цвет постоянный для чата).
function chatAva(c, size = '') {
  const photo = c.avatar ? `<img src="${pic(c.avatar)}" alt="" loading="lazy" decoding="async" onerror="this.remove()"/>` : '';
  return `<span class="ava chat ${size}${c.ring ? ' ring-' + c.ring : ''}" style="--h:${hue(c.id)}" aria-hidden="true">${esc(initial(c.title))}${photo}</span>`;
}
// Значки состояния в строке: что с человеком сейчас, коротко и с подписью для экранного диктора.
function flagIcons(f) {
  if (!f) return '';
  const list = [f.global_ban ? ['⛔', 'везде', 'bad', 'Бан во всех чатах'] : f.bans ? ['⛔', f.bans > 1 ? f.bans : '', 'bad', `Бан в чатах: ${f.bans}`] : null,
    f.blocked ? ['🙈', '', 'bad', 'Бот не отвечает'] : null, f.muted ? ['🔇', '', 'warn', 'Мут'] : null,
    f.warns ? ['⚠️', f.warns, 'warn', `Предупреждений: ${f.warns}`] : null, f.watch ? ['👁', '', 'warn', 'На контроле'] : null,
    f.vip ? ['👑', '', 'ok', 'VIP'] : null].filter(Boolean);
  const shown = list.slice(0, 3), rest = list.slice(3);   // порядок — от самого серьёзного; лишнее одним «+N»
  return list.length ? `<span class="flags">${shown.map(([g, n, tone, t]) => `<i class="fl ${tone}" title="${esc(t)}" aria-label="${esc(t)}">${g}${n ? `<b>${esc(n)}</b>` : ''}</i>`).join('')}${rest.length
    ? `<i class="fl" title="${esc(rest.map(x => x[3]).join(', '))}" aria-label="${esc(rest.map(x => x[3]).join(', '))}"><b>+${rest.length}</b></i>` : ''}</span>` : '';
}
// Подсветка найденного: глаз сразу видит, почему эта строка в результатах.
function hl(text, q) {
  const t = String(text ?? ''), needle = String(q || '').replace(/^@/, '').trim();
  if (!needle || needle.length < 2) return esc(t);
  const at = t.toLowerCase().indexOf(needle.toLowerCase());
  return at < 0 ? esc(t) : esc(t.slice(0, at)) + '<mark>' + esc(t.slice(at, at + needle.length)) + '</mark>' + esc(t.slice(at + needle.length));
}
// Человек одной строкой (журнал, жалобы): маленькое лицо, имя, @ник. Ссылка на карточку, если раздел открыт.
function person(p, {link = true} = {}) {
  if (!p || !p.id) return '';
  const name = p.name || p.username && '@' + p.username || 'id' + p.id;
  const inner = `${ava(p, 'xs')}<b>${esc(name)}</b>${p.name && p.username ? `<span>@${esc(p.username)}</span>` : ''}${p.tag ? `<span>[${esc(p.tag)}]</span>` : ''}`;
  return link && has('people') ? `<a class="who-i" href="#/player/${p.id}">${inner}</a>` : `<span class="who-i">${inner}</span>`;
}
const chatLink = c => c ? (has('people') ? `<a href="#/chat/${c.id}">${esc(c.title || c.id)}</a>` : esc(c.title || c.id)) : '';
const pill = (text, tone = '', plain = false) => text ? `<span class="pill ${tone}${plain ? ' plain' : ''}">${esc(text)}</span>` : '';
// Строка списка: lead — лицо или значок, end — значение справа. on — имя обработчика, data — data-атрибуты.
function row({lead = '', title, sub = '', pills = '', end = '', on = '', data = {}, href = '', cls = '', chev = !!(on || href), tag = ''}) {
  const attrs = Object.entries(data).map(([k, v]) => ` data-${k}="${esc(v)}"`).join('');
  const t = tag || (href ? 'a' : on ? 'button' : 'div');
  return `<${t} class="row ${cls}"${t === 'button' ? ' type="button"' : ''}${href ? ` href="${esc(href)}"` : ''}${on ? ` data-on="${on}"` : ''}${attrs}>
    ${lead}<span class="row-t"><b>${title}</b>${sub ? `<span>${sub}</span>` : ''}${pills ? `<span class="pills">${pills}</span>` : ''}</span>
    ${end || chev ? `<span class="row-e">${end}${chev ? '<span class="chev" aria-hidden="true">›</span>' : ''}</span>` : ''}</${t}>`;
}
const lead = (glyph, tone = '') => `<span class="lead ${tone ? 'tone-' + tone : ''}" aria-hidden="true">${glyph}</span>`;
const sh = (title, {count = null, link = '', on = ''} = {}) => `<div class="sh"><h3>${title}</h3>${count == null ? '' : `<span class="cnt">${count}</span>`}
  ${link ? `<a href="${esc(link)}">Все ›</a>` : on ? `<button type="button" class="lnk" data-on="${on}">Все ›</button>` : ''}</div>`;
const callout = (tone, glyph, html, btn = '') => `<div class="callout ${tone}"><span class="ci" aria-hidden="true">${glyph}</span><div>${html}</div>${btn}</div>`;
const help = (title, html) => `<details class="help"><summary>${esc(title)}</summary>${html}</details>`;
const emptyBox = (title, text = '') => `<div class="empty"><b>${esc(title)}</b>${esc(text)}</div>`;
function trend(cur, prev) {
  if (prev == null || (!prev && !cur)) return '';
  if (!prev) return '<span class="delta up" title="В прошлом периоде было 0">▲ новое</span>';
  const pct = Math.round((cur - prev) / prev * 100);
  if (!pct) return '<span class="delta flat" title="Как в прошлом периоде">＝</span>';
  return `<span class="delta ${pct > 0 ? 'up' : 'down'}" title="В прошлом периоде: ${num(prev)}">${pct > 0 ? '▲' : '▼'} ${Math.abs(pct)}%</span>`;
}
function spark(values) {
  if (!values || values.length < 2) return '';
  const max = Math.max(1, ...values), w = 100, h = 26, step = w / (values.length - 1);
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(h - 2 - v / max * (h - 4)).toFixed(1)}`).join(' ');
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>`;
}
const stat = (label, value, {tone = '', extra = '', small = '', sparkline = null, on = '', data = {}} = {}) => {
  const attrs = Object.entries(data).map(([k, v]) => ` data-${k}="${esc(v)}"`).join('');
  const t = on ? 'button' : 'div';
  return `<${t} class="stat ${tone}"${on ? ` type="button" data-on="${on}"` : ''}${attrs}><span>${label}</span><b>${value}${extra}</b>${small ? `<small>${small}</small>` : ''}${sparkline ? spark(sparkline) : ''}</${t}>`;
};
// Столбики по дням. Больше недели — подписи только числом дня: «01.10» не помещается под узким столбиком.
function bars(days, daily, field) {
  if (days.length < 2) return '';
  const vals = days.map(d => (daily[d] || {})[field] || 0), max = Math.max(1, ...vals);
  return `<div class="bars">${days.map((d, i) => `<div class="b" title="${d}: ${num(vals[i])}"><i style="height:${Math.round(vals[i] / max * 100)}%"></i>
    <span>${days.length <= 7 ? `${d.slice(8)}.${d.slice(5, 7)}` : i % 5 === 0 || i === days.length - 1 ? d.slice(8) : ''}</span></div>`).join('')}</div>`;
}
const meter = (share, tone = '') => `<div class="meter ${tone}"><i style="width:${Math.max(1, Math.min(100, share))}%"></i></div>`;
// Сегменты: выбор одного из нескольких (период, вид). Кнопки с aria-selected.
const seg = (name, options, current, {cls = ''} = {}) => `<div class="seg ${cls}" role="tablist">${options.map(([v, t, n, tone]) =>
  `<button type="button" role="tab" data-on="${name}" data-v="${esc(v)}" aria-selected="${String(v) === String(current)}">${esc(t)}${n != null ? `<span class="n ${tone || ''}">${esc(n)}</span>` : ''}</button>`).join('')}</div>`;
// Чипы: тот же выбор, но с переносом (сроки, причины, фильтры).
const chipPick = (name, options, current, {scroll = false} = {}) => `<div class="chipset ${scroll ? 'scroll' : ''}">${options.map(([v, t]) =>
  `<button type="button" class="chip" data-on="${name}" data-v="${esc(v)}" aria-pressed="${String(v) === String(current)}">${esc(t)}</button>`).join('')}</div>`;
const field = (label, control, hintText = '', forId = '') => `<div class="field">${label ? `<label${forId ? ` for="${forId}"` : ''}>${label}</label>` : ''}${control}${hintText ? `<div class="hint">${hintText}</div>` : ''}</div>`;
const toggle = (attrs, on, label, disabled = false) => `<label class="toggle"><input type="checkbox" ${attrs} aria-label="${esc(label)}" ${on ? 'checked' : ''} ${disabled ? 'disabled' : ''}/><span aria-hidden="true"></span></label>`;
const skeleton = (rows = 6, {stats = false} = {}) => `<div aria-hidden="true"><div class="sk sk-title"></div>${stats ? '<div class="sk-stats"><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i></div>' : ''}
  ${Array.from({length: rows}, () => '<div class="sk-row"><i class="sk"></i><div><i class="sk"></i><i class="sk"></i></div></div>').join('')}</div>`;

// Делегирование: один обработчик на экран. data-on — нажатие, data-change / data-input — поля.
function on(root, handlers) {
  const pick = (e, attr) => {
    const el = e.target.closest(`[${attr}]`);
    if (!el || !root.contains(el)) return;
    const fn = handlers[el.getAttribute(attr)];
    if (fn) { if (el.tagName === 'A' && !el.getAttribute('href')?.startsWith('#/')) e.preventDefault(); fn(el, e); }
  };
  root.addEventListener('click', e => pick(e, 'data-on'));
  root.addEventListener('change', e => pick(e, 'data-change'));
  root.addEventListener('input', e => pick(e, 'data-input'));
}
// Кнопка «занята», пока идёт запрос: второй тап ничего не делает.
async function busy(btn, fn) {
  if (btn && btn.disabled) return;
  if (btn) { btn.disabled = true; btn.classList.add('busy'); }
  try { return await fn(); }
  catch (e) { toast(e.message, true); }
  finally { if (btn && btn.isConnected) { btn.disabled = false; btn.classList.remove('busy'); } }
}

// ── Роутер: у каждого экрана свой адрес, «назад» везде одинаковый ─────────────
// Адрес — #/путь?параметры. Глубину своей истории храним в history.state.adm: на нулевой «назад» ведёт
// из админки в Предвестник, иначе — history.back(). Хэш Telegram (#tgWebAppData=…) роутом не считается.

const ROUTES = [];
const NAV = {seq: 0, depth: 0, ctrl: null, path: '', scroll: new Map()};
const CACHE = new Map();   // путь API -> {at, data}: мгновенный «назад» без заставки
const SECTION_META = {
  home: ['Главная', 'Что требует внимания сейчас'], people: ['Игроки и чаты'], reports: ['Жалобы'], metrics: ['Метрики'], journal: ['Журнал'],
  broadcast: ['Рассылка'], promo: ['Промокоды'], switches: ['Функции'], settings: ['Настройки'], health: ['Состояние'], access: ['Права'], mychats: ['Мои чаты'],
};
const SHORT = {home: 'Главная', people: 'Игроки', reports: 'Жалобы', metrics: 'Метрики', journal: 'Журнал', broadcast: 'Рассылка', promo: 'Коды',
  switches: 'Функции', settings: 'Настройки', health: 'Состояние', mychats: 'Мои чаты', access: 'Права'};
const SECTION_HINT = {people: 'Поиск, карточки, наказания', reports: 'Очередь и решения', metrics: 'Люди, команды, экономика', journal: 'Кто что сделал',
  broadcast: 'Сообщения игрокам и в чаты', promo: 'Коды и награды', switches: 'Включить и выключить', settings: 'Переводы, жалобы, сессии',
  health: 'Бот, база, ошибки', access: 'Кто что может', mychats: 'Ваши чаты'};

function route(pattern, opts) {
  const keys = [];
  const re = new RegExp('^' + pattern.replace(/:(\w+)/g, (_, k) => { keys.push(k); return '([^/]+)'; }) + '$');
  ROUTES.push({re, keys, ...opts});
}
function parseHash() {
  const raw = location.hash.startsWith('#/') ? location.hash.slice(2) : '';
  const [path, qs] = raw.split('?');
  return {path: decodeURIComponent(path || ''), query: new URLSearchParams(qs || '')};
}
function match(path) {
  // Точные адреса раньше адресов с параметрами: «promo/new» — экран создания, а не код NEW.
  for (const r of [...ROUTES].sort((x, y) => x.keys.length - y.keys.length)) {
    const m = r.re.exec(path);
    if (m) return {r, params: Object.fromEntries(r.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]))};
  }
  return null;
}
const homePath = () => (ME && ME.owner ? 'mychats' : 'home');
function go(path, {replace = false} = {}) {
  NAV.scroll.set(NAV.path, window.scrollY);
  if (replace) history.replaceState({adm: NAV.depth}, '', '#/' + path);
  else { NAV.depth++; history.pushState({adm: NAV.depth}, '', '#/' + path); }
  render('push');
}
// Тот же экран с другими параметрами (фильтр, вкладка) — без новой записи в истории.
function setQuery(params) {
  const {path, query} = parseHash();
  Object.entries(params).forEach(([k, v]) => (v === '' || v == null ? query.delete(k) : query.set(k, v)));
  const qs = query.toString();
  history.replaceState({adm: NAV.depth}, '', '#/' + path + (qs ? '?' + qs : ''));
}
function goBack() {
  if (SHEETS.length) { popSheet(); return; }
  if (NAV.depth > 0) { history.back(); return; }
  const {path} = parseHash(), m = match(path);
  if (m && !m.r.root) { go(m.r.up ? m.r.up(m.params) : (m.r.section === 'home' ? homePath() : m.r.section), {replace: true}); return; }
  location.href = (BASE || '') + '/';   // корень админки: обратно в Предвестник
}
window.addEventListener('popstate', e => {
  NAV.scroll.set(NAV.path, window.scrollY);
  NAV.depth = (e.state && e.state.adm) || 0;
  if (SHEETS.length) closeSheets();
  render('pop');
});

// Данные экрана: отмена прошлого запроса, тайм-аут 15 с, кэш для «назад».
async function load(ctx, path, {cache = true} = {}) {
  const hit = CACHE.get(path);
  if (ctx.mode === 'pop' && !ctx.mounted && cache && hit && Date.now() - hit.at < 120000) {   // только первая загрузка после «назад»
    ctx.revalidate.push(path);
    return hit.data;
  }
  const controller = new AbortController();
  ctx.ctrls.push(controller);
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const data = await api(path, {signal: controller.signal});
    if (cache) CACHE.set(path, {at: Date.now(), data});
    return data;
  } finally { clearTimeout(timer); }
}

function sectionTitle(key) { return (ME && (ME.sections.find(s => s.key === key) || {}).title) || (SECTION_META[key] || [key])[0]; }

// Можно ли обновить экран самому (вернулись в приложение, появилась сеть): нет, если открыта шторка,
// человек печатает или на экране есть несохранённые правки (любой ввод после отрисовки).
function canAutoRefresh() {
  const main = $('#main'), a = document.activeElement;
  return !!ME && !SHEETS.length && main.dataset.dirty !== '1' && !(a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName));
}
['input', 'change'].forEach(t => $('#main').addEventListener(t, e => {
  if (e.target.closest('.search')) return;   // поиск — не правка
  $('#main').dataset.dirty = '1';
}));

async function render(mode = 'push') {
  const {path, query} = parseHash();
  const found = match(path);
  if (!found) { go(homePath(), {replace: true}); return; }
  const {r, params} = found;
  NAV.path = location.hash;
  const seq = ++NAV.seq;
  if (NAV.ctrls) NAV.ctrls.forEach(c => c.abort());
  const main = $('#main');
  delete main.dataset.dirty;
  const ctx = {mode, params, query, seq, ctrls: [], revalidate: [], main, alive: () => seq === NAV.seq};
  NAV.ctrls = ctx.ctrls;
  ctx.view = Object.assign(document.createElement('div'), {className: 'view'});
  ctx.$ = sel => ctx.view.querySelector(sel);
  ctx.load = (p, o) => load(ctx, p, o);
  ctx.mount = () => { if (ctx.alive() && ctx.view.parentNode !== main) main.replaceChildren(ctx.view); };
  ctx.refresh = () => { if (ctx.alive()) render('soft'); };
  ctx.title = (t, sub = '') => { if (ctx.alive()) setTitle(t, sub); };
  // Липкая панель главного действия экрана: создаётся заново на каждую отрисовку, обработчики — этого экрана.
  ctx.bar = (html, handlers = {}, cls = '') => {
    let b = $('#actbar');
    if (!ctx.alive()) return null;
    if (!html) { if (b) b.remove(); main.classList.remove('with-bar'); return null; }
    if (!b || b.dataset.seq !== String(seq)) {
      if (b) b.remove();
      b = Object.assign(document.createElement('div'), {id: 'actbar'});
      b.dataset.seq = seq; document.body.append(b); on(b, handlers);
    }
    b.className = 'actbar ' + cls; b.innerHTML = html; main.classList.add('with-bar');
    return b;
  };
  if (mode !== 'soft') { const b = $('#actbar'); if (b) b.remove(); main.classList.remove('with-bar'); }
  const section = r.section;
  dock(section);
  setTitle(r.title ? r.title(params) : sectionTitle(section), '');
  backButton(!!r.root);
  if (section !== 'home' && section !== 'mychats' && !has(section)) {
    main.replaceChildren(stateEl('🛡', 'Раздел закрыт', 'Для вашей роли этот раздел недоступен.', ['На главную', () => go(homePath(), {replace: true})]));
    return;
  }
  if (mode === 'push') { main.setAttribute('aria-busy', 'true'); main.innerHTML = skeleton(7, {stats: !!r.stats}); window.scrollTo(0, 0); }
  try {
    await r.render(ctx);
    if (!ctx.alive()) return;
    ctx.mount();
    ctx.mounted = true;
    const stale = $('#actbar');   // панель от прошлой отрисовки, которую новая не заменила, — убрать
    if (stale && stale.dataset.seq !== String(seq)) { stale.remove(); main.classList.remove('with-bar'); }
    if (mode === 'pop' || mode === 'soft') {
      const y = mode === 'soft' ? window.scrollY : NAV.scroll.get(location.hash) || 0;
      requestAnimationFrame(() => window.scrollTo(0, y));
    }
    // Вернулись «назад» на данные из кэша — тихо проверяем свежие; перерисуем, только если что-то изменилось и человек ничего не печатает.
    if (ctx.revalidate.length) setTimeout(async () => {
      try {
        const fresh = await Promise.all(ctx.revalidate.map(p => api(p)));
        if (!ctx.alive()) return;
        const changed = ctx.revalidate.some((p, i) => JSON.stringify((CACHE.get(p) || {}).data) !== JSON.stringify(fresh[i]));
        ctx.revalidate.forEach((p, i) => CACHE.set(p, {at: Date.now(), data: fresh[i]}));
        if (changed && canAutoRefresh()) render('soft');
      } catch (_) {}
    }, 50);
  } catch (e) {
    if (!ctx.alive()) return;
    const b = $('#actbar'); if (b) { b.remove(); main.classList.remove('with-bar'); }   // кнопки прошлого экрана над ошибкой не нужны
    showError(main, e, () => render('push'));
  } finally {
    if (ctx.alive()) main.setAttribute('aria-busy', 'false');
  }
}
function stateEl(glyph, title, text, btn = null, tone = '') {
  const el = Object.assign(document.createElement('section'), {className: 'state ' + tone});
  el.setAttribute('role', tone === 'bad' ? 'alert' : 'status');
  el.innerHTML = `<div class="si" aria-hidden="true">${glyph}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>${btn ? `<button type="button" class="btn primary">${esc(btn[0])}</button>` : ''}`;
  if (btn) el.querySelector('button').onclick = btn[1];
  return el;
}
// Экраны «нет входа» и «нет доступа»: повтор не поможет — нужен вход из Telegram или роль.
function accessMarkup(error) {
  const code = error && error.status, msg = (error && error.message) || '';
  let glyph = '↻', title = 'Не удалось открыть админку', text = msg || 'Попробуйте ещё раз.', retry = true;
  if (code === 403 && error.owner) { glyph = '🛡'; title = 'Доступ к админке закрыт'; retry = false; }
  else if (code === 403) {
    glyph = '🛡'; title = 'Только для персонала бота'; retry = false;
    text = msg + (/персонал/.test(msg) ? ' Если вы в команде, попросите создателя выдать вам роль, а потом напишите боту «бот админка».' : '');
  } else if (code === 401) {
    glyph = '🔒'; retry = false;
    if (/завершен/i.test(msg)) { title = 'Сессия завершена'; text = 'Откройте админку заново: напишите боту в личку «бот админка» и нажмите кнопку.'; }
    else { title = 'Откройте админку из Telegram'; text = 'Напишите боту в личку «бот админка» и нажмите кнопку «🛠 Открыть админку».'; }
  }
  return `<section class="state" role="alert"><div class="si" aria-hidden="true">${glyph}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>
    ${retry ? '<button type="button" class="btn primary load-retry">Повторить</button>' : `<a class="btn" href="${esc(BASE)}/">← В Предвестник</a>`}</section>`;
}
function showError(main, error, retry) {
  if (error && (error.status === 401 || error.status === 403) && !error.soft) {
    if (ME && ME.owner) error.owner = true;
    main.innerHTML = accessMarkup(error);
    const again = $('.load-retry', main); if (again) again.onclick = () => location.reload();
    return;
  }
  const timedOut = error && error.name === 'AbortError';
  main.replaceChildren(stateEl('↻', timedOut ? 'Сервер отвечает слишком долго' : 'Не загрузилось',
    timedOut ? 'Мы остановили ожидание, чтобы экран не завис.' : (error && error.message) || 'Попробуйте ещё раз.', ['Повторить', retry], 'bad'));
}

// ── Оболочка: шапка, док, «Ещё» ──────────────────────────────────────────────

function setTitle(title, sub = '') {
  $('#ttl').innerHTML = esc(title) + (sub ? `<small>${esc(sub)}</small>` : '');
  document.title = title + ' · Админка';
}
// Кнопка «назад»: своя в шапке (браузер) и системная Telegram. Обработчик Telegram ставится один раз.
// Одна кнопка «назад»: в Telegram — системная (наша в шапке скрыта), в браузере — в шапке, кроме корня раздела,
// чтобы случайный тап в углу главной не выкидывал из админки.
function backButton(atRoot = false) {
  const bb = TG && TG.platform && TG.platform !== 'unknown' && TG.BackButton;
  $('#hback').classList.toggle('dim', !!bb || (atRoot && NAV.depth === 0));
  if (!bb) return;
  try { bb.show(); } catch (_) {}
}
const DOCK_MAX = 5;
function dockItems() {
  if (ME.owner) return {main: ME.sections, rest: []};
  const pref = ['people', 'reports', 'journal'];
  const keys = ME.sections.map(s => s.key);
  const first = ['home', ...pref.filter(k => keys.includes(k)), ...keys.filter(k => !pref.includes(k))];
  const items = first.map(k => ({key: k, title: k === 'home' ? 'Главная' : sectionTitle(k)}));
  return items.length <= DOCK_MAX ? {main: items, rest: []} : {main: items.slice(0, DOCK_MAX - 1), rest: items.slice(DOCK_MAX - 1)};
}
let BADGES = {};
function dock(active) {
  const nav = $('#tabs');
  if (!ME) { nav.hidden = true; return; }
  const {main, rest} = dockItems();
  const inRest = rest.some(s => s.key === active);
  nav.hidden = main.length + rest.length < 2;   // один раздел (владелец чата) — доку нечего переключать
  nav.style.setProperty('--nav-n', main.length + (rest.length ? 1 : 0));
  nav.innerHTML = main.map(s => `<button type="button" class="nb ${s.key === active ? 'on' : ''}" data-tab="${s.key}" ${s.key === active ? 'aria-current="page"' : ''}>${icon(s.key, '')}<span>${esc(SHORT[s.key] || s.title)}</span>${BADGES[s.key] ? `<i class="badge">${BADGES[s.key] > 99 ? '99+' : BADGES[s.key]}</i>` : ''}</button>`).join('')
    + (rest.length ? `<button type="button" class="nb ${inRest ? 'on' : ''}" data-more="1">${icon('more', '')}<span>Ещё</span>${rest.some(s => BADGES[s.key]) ? '<i class="badge">•</i>' : ''}</button>` : '');
  NAV.section = active;
}
async function refreshBadges() {
  if (!ME || ME.owner) return;   // значки — для персонала
  try { BADGES = await api('/badges'); } catch (_) { return; }
  dock(NAV.section);
}
// Ссылки на экраны (#/…) идут через роутер: так «назад» знает глубину и не выходит из админки раньше времени.
document.addEventListener('click', e => {
  const a = e.target.closest('a[href^="#/"]');
  if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey) return;
  e.preventDefault();
  if (SHEETS.length) closeSheets();
  go(a.getAttribute('href').slice(2));
});
document.addEventListener('click', e => {
  const tab = e.target.closest('#tabs [data-tab]');
  if (tab) { haptic('select'); const k = tab.dataset.tab; if (NAV.section === k && parseHash().path === k) window.scrollTo({top: 0, behavior: 'smooth'}); else { const m = match(parseHash().path); go(k, {replace: !!(m && m.r.root)}); } return; }   // между разделами — без лишних шагов «назад»
  if (e.target.closest('#tabs [data-more]')) { haptic('select'); moreSheet(); }
});
// «Ещё»: все разделы плитками, оформление, клавиши и выход — одно место для редкого.
function moreSheet() {
  const {main, rest} = dockItems();
  const all = ME.owner ? main : [...main.filter(s => s.key !== 'home'), ...rest];
  const tiles = `<div class="tiles">${all.map(s => `<button type="button" class="tile" data-on="go" data-v="${s.key}" ${s.key === NAV.section ? 'aria-current="page"' : ''}>
      ${icon(s.key, '')}<span>${esc(SHORT[s.key] || s.title)}</span>${BADGES[s.key] ? `<i class="badge">${BADGES[s.key]}</i>` : ''}</button>`).join('')}</div>`;
  const panel = openSheet({title: 'Все разделы', sub: ME.rank_name, body: tiles + `<div class="list" style="margin-top:14px">
      ${row({lead: lead(icon('theme', 'ico')), title: 'Оформление', sub: THEMES.find(t => t[0] === themePref())[1], on: 'theme'})}
      ${!coarse() ? row({lead: lead(icon('keys', 'ico')), title: 'Горячие клавиши', sub: '/ — поиск, g затем буква — раздел', on: 'keys'}) : ''}
      ${row({lead: lead(icon('out', 'ico')), title: 'Вернуться в Предвестник', on: 'app'})}</div>`});
  on(panel.el, {go: el => go(el.dataset.v), theme: () => themeSheet(), keys: () => hotkeysSheet(), app: () => { location.href = (BASE || '') + '/'; }});
}

// ── Тема: тёмная (как Mini App), светлая или как в Telegram ─────────────────

const THEMES = [['auto', '📱 Как в Telegram', 'Сама меняется вслед за темой Telegram'], ['dark', '🌙 Тёмная', 'Как в Предвестнике'], ['light', '☀️ Светлая', 'Для яркого дня']];
const PAGE_COLOR = {dark: '#08090c', light: '#f2f3f7'};
const themePref = () => { const t = PREFS.get('theme', 'auto'); return THEMES.some(z => z[0] === t) ? t : 'auto'; };
function resolveTheme(pref = themePref()) {
  if (pref === 'light' || pref === 'dark') return pref;
  // Вне Telegram SDK всегда отвечает «light», поэтому его схему берём только когда мы действительно внутри Telegram
  const scheme = TG && TG.platform && TG.platform !== 'unknown' ? TG.colorScheme : '';
  if (scheme === 'light' || scheme === 'dark') return scheme;
  return window.matchMedia && matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}
function paintTmaShell(color) {   // шапка, фон и нижняя полоса Telegram того же цвета, что страница
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
  const draw = () => `<div class="list">${THEMES.map(([key, title, sub]) => `<button type="button" class="row" data-theme-pick="${key}" data-on="pick" data-v="${key}">
      <span class="row-t"><b>${title}</b><span>${sub}</span></span><span class="row-e">${key === themePref() ? '<b style="color:var(--accent)">✓</b>' : ''}</span></button>`).join('')}</div>
    <p class="sub">Хранится на этом устройстве.</p>`;
  const panel = openSheet({title: 'Оформление', body: draw()});
  on(panel.el, {pick: el => { PREFS.set('theme', el.dataset.v); applyTheme(); $('.sheet-b', panel.el).innerHTML = draw(); }});
}
applyTheme();
try { if (TG && TG.onEvent) TG.onEvent('themeChanged', () => { if (themePref() === 'auto') applyTheme(); }); } catch (_) {}
try { if (window.matchMedia) matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { if (themePref() === 'auto') applyTheme(); }); } catch (_) {}

// ── Шторки: стек. «‹» в шторке — к прошлому шагу, ✕ и тап по фону — закрыть всё ──
// Нижняя панель шторки липкая: главная кнопка видна всегда, даже над клавиатурой.

const SHEETS = [];
function sheetBox() { return $('#sheet'); }
function openSheet({title, sub = '', body = '', actions = [], wide = false, onClose = null} = {}) {
  const box = sheetBox();
  const el = Object.assign(document.createElement('div'), {className: 'sheet' + (wide ? ' wide' : '')});
  el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-label', title); el.tabIndex = -1;
  const backable = SHEETS.length > 0;
  el.innerHTML = `<div class="sheet-h">${backable ? `<button type="button" class="ib" data-sh="back" aria-label="Назад">${icon('back')}</button>` : ''}
      <h3>${esc(title)}${sub ? `<small>${esc(sub)}</small>` : ''}</h3><button type="button" class="ib" data-sh="close" aria-label="Закрыть">${icon('close')}</button></div>
    <div class="sheet-b">${body}</div>
    ${actions.length ? `<div class="sheet-f"><div class="err" role="alert" hidden></div><div class="btns">${actions.map((a, i) =>
      `<button type="button" class="btn ${a.kind || (i === 0 ? 'primary' : '')}" data-sa="${i}">${esc(a.label)}</button>`).join('')}</div></div>` : ''}`;
  SHEETS.forEach(s => s.el.classList.remove('is-top'));
  const api_ = {el, q: sel => el.querySelector(sel), qa: sel => $$(sel, el), close: () => closeSheets(), pop: () => popSheet(), onClose,
    error(text) { const e = el.querySelector('.sheet-f .err'); if (e) { e.textContent = text || ''; e.hidden = !text; } }};
  SHEETS.push(api_);
  box.append(el);
  el.classList.add('is-top');
  box.hidden = false;
  document.body.classList.add('locked');
  el.querySelector('[data-sh="close"]').onclick = () => closeSheets();
  if (backable) el.querySelector('[data-sh="back"]').onclick = () => popSheet();
  el.querySelectorAll('[data-sa]').forEach(btn => btn.onclick = async () => {
    const a = actions[+btn.dataset.sa];
    if (btn.disabled) return;   // двойной тап по «Подтвердить» не отправит второй запрос
    api_.error('');
    if (!a.run) { if (SHEETS.includes(api_)) { while (SHEETS[SHEETS.length - 1] !== api_) popSheet(); popSheet(); } return; }   // «Отмена» закрывает только это окно
    btn.disabled = true; btn.classList.add('busy');
    try {
      const res = await a.run(api_);
      if (res !== 'keep' && SHEETS.includes(api_)) closeSheets();
    } catch (e) { api_.error(e.message); haptic('error'); }
    finally { if (btn.isConnected) { btn.disabled = false; btn.classList.remove('busy'); } }
  });
  const first = el.querySelector('.sheet-b input:not([type=checkbox]):not([readonly]), .sheet-b textarea');
  setTimeout(() => { if (first && !coarse()) first.focus(); else el.focus(); }, 30);
  return api_;
}
function popSheet() {
  const top = SHEETS.pop();
  if (!top) return;
  top.el.remove();
  if (top.onClose) try { top.onClose(); } catch (_) {}
  if (SHEETS.length) SHEETS[SHEETS.length - 1].el.classList.add('is-top');
  else { sheetBox().hidden = true; document.body.classList.remove('locked'); }
}
function closeSheets() { while (SHEETS.length) popSheet(); }
// Короткая форма: заголовок, содержимое, одна главная кнопка (и «Отмена»). onSubmit может вернуть 'keep'.
function sheet(title, body, submitText, onSubmit, {info = false, cancelText = 'Отмена', kind = 'primary', sub = ''} = {}) {
  return openSheet({title, sub, body, actions: info ? [{label: submitText, kind: '', run: null}]
    : [{label: submitText, kind, run: p => onSubmit(p)}, {label: cancelText, kind: '', run: null}]});
}
// Подтверждение в стиле админки вместо системного confirm(): обещание true/false.
function ask(title, html, okText, {danger = true} = {}) {
  return new Promise(resolve => {
    let done = false;
    const p = openSheet({title, body: html, actions: [{label: okText, kind: danger ? 'btn danger fill' : 'primary', run: () => { done = true; resolve(true); }},
      {label: 'Отмена', kind: '', run: null}], onClose: () => { if (!done) resolve(false); }});
    return p;
  });
}
sheetBox().addEventListener('click', e => { if (e.target === sheetBox()) closeSheets(); });
// Tab не уходит из открытой шторки на страницу под ней.
document.addEventListener('keydown', e => {
  if (e.key !== 'Tab' || !SHEETS.length) return;
  const el = SHEETS[SHEETS.length - 1].el;
  const items = $$('button:not([disabled]), a[href], input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea', el).filter(x => x.offsetParent);
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (!el.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
  else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});
// Клавиатура телефона: шторка не прячется под неё (высота видимой части экрана).
if (window.visualViewport) {
  const fit = () => document.documentElement.style.setProperty('--vvh', visualViewport.height + 'px');
  visualViewport.addEventListener('resize', fit); fit();
}

// ── Действия над людьми и чатами: поля, итог, подтверждение ─────────────────

const DURATIONS = [[15, '15 мин'], [60, '1 час'], [1440, '1 день'], [10080, '7 дней'], [43200, '30 дней'], [0, 'навсегда']];
const REASONS = ['Спам', 'Флуд', 'Оскорбления', 'Реклама', 'Провокации', '18+', 'Обход наказания'];
function rememberReason(text) {
  const r = String(text || '').trim();
  if (!r || REASONS.includes(r)) return;
  PREFS.set('reasons', [r, ...PREFS.get('reasons', []).filter(x => x !== r)].slice(0, 4));
}
// Срок одним касанием; значение — в скрытом поле #fmin.
const durationField = (def = 60, label = 'Срок') => field(label, `<input type="hidden" id="fmin" value="${def}"/>${chipPick('fdur', DURATIONS, def)}`);
// Причина: поле + готовые и недавние причины одним касанием.
const reasonField = (required = false, value = '') => {
  const list = [...PREFS.get('reasons', []), ...REASONS].slice(0, 9);
  return field(`Причина${required ? '' : ' <span style="font-weight:400">(необязательно)</span>'}`,
    `<input id="freason" maxlength="200" value="${esc(value)}" ${required ? 'data-required="1"' : ''} autocomplete="off"/>${chipPick('freason', list.map(x => [x, x]), '')}`);
};
const hint = text => `<p class="sub" style="margin:0 0 14px">${text}</p>`;
// Поля шторки: чипы срока и причины пишут в свои поля.
function wireFormChips(root) {
  root.addEventListener('click', e => {
    const c = e.target.closest('.chip[data-on]');
    if (!c || !root.contains(c)) return;
    const key = c.dataset.on;
    if (key === 'fdur') { root.querySelector('#fmin').value = c.dataset.v; }
    else if (key === 'freason') { const f = root.querySelector('#freason'); f.value = c.dataset.v; }
    else if (key === 'fdays') { root.querySelector('#fdays').value = c.dataset.v; }
    else return;
    c.parentNode.querySelectorAll('.chip').forEach(x => x.setAttribute('aria-pressed', String(x === c)));
    haptic('select');
  });
}

// Форма под каждое действие: [разметка, collect(шторка) → что отправить].
function actionForm(key, ctx) {
  const v = (root, id) => ((root && root.querySelector('#' + id)) || {}).value;
  switch (key) {
    case 'warn': return [hint('Предупреждение действует выбранный срок. Когда их станет столько, сколько стоит в лимите чата, бот напишет об этом в чат.') + durationField(10080) + reasonField(false, ctx.reason),
      r => ({minutes: +v(r, 'fmin'), reason: v(r, 'freason')})];
    case 'mute': return [hint('Не сможет писать в этом чате до конца срока. Снять раньше — «Снять мут».') + durationField(60) + reasonField(false, ctx.reason),
      r => ({minutes: +v(r, 'fmin'), reason: v(r, 'freason')})];
    case 'ban': return [hint('Уберут из этого чата, вернуться сам не сможет. Снять — «Снять бан в чате».') + durationField(0) + reasonField(false, ctx.reason),
      r => ({minutes: +v(r, 'fmin'), reason: v(r, 'freason')})];
    case 'kick': case 'global_ban': return [hint(key === 'kick' ? 'Выйдет из чата, но сможет вернуться по ссылке.'
        : 'Бан сразу во всех чатах, где есть бот и у него есть права. Снять — «Снять бан во всех чатах». Понадобится ввести ID игрока.') + reasonField(false, ctx.reason),
      r => ({reason: v(r, 'freason')})];
    case 'block': return [hint('Бот перестанет отвечать игроку и считать его команды. В чатах он остаётся и может писать.')
        + field('На сколько', `<input type="hidden" id="fdays" value="0"/>${chipPick('fdays', [[1, '1 день'], [7, '7 дней'], [30, '30 дней'], [0, 'пока не снимут']], 0)}`) + reasonField(),
      r => ({days: +v(r, 'fdays'), reason: v(r, 'freason')})];
    case 'balance': {
      const rules = Object.entries(ctx.confirm_rules ? ctx.confirm_rules.balance : {}).map(([c, n]) => `${num(n)} ${({mora: 'мора', diamonds: 'алмазов', essence: 'эссенции', zarniki: 'зарников'})[c] || c}`).join(', ');
      return [hint('Минус спишет. Причина обязательна, она попадёт в журнал.' + (rules ? ` Крупные суммы (от ${rules}) попросят ввести ID игрока.` : ''))
        + `<div class="grid2">${field('Валюта', `<select id="fcur">${ctx.currencies.map(c => `<option value="${c.code}">${esc(c.title)} · ${num((ctx.balances || {})[c.code])}</option>`).join('')}</select>`)}
          ${field('Сумма', '<input id="famount" inputmode="decimal" placeholder="500 или -500" autocomplete="off"/>', 'Минус — списать')}</div>` + reasonField(true),
        r => ({currency: v(r, 'fcur'), amount: (v(r, 'famount') || '').replace(',', '.').replace(/\s/g, ''), reason: v(r, 'freason'), request_id: ctx._rid})];
    }
    case 'vip': return [field('Дней VIP (добавятся к текущему сроку)', `<input id="fdays" type="number" min="1" max="3650" value="7"/>${chipPick('fdays', [[7, '7 дн.'], [30, '30 дн.'], [90, '90 дн.'], [365, '365 дн.']], 7)}`) + reasonField(),
      r => ({days: +v(r, 'fdays'), reason: v(r, 'freason'), request_id: ctx._rid})];
    case 'local_rank': return [hint('Ранг действует только в выбранном чате. Владелец и глобальная роль этим не меняются.')
        + field('Ранг в чате', `<select id="flocalrank">${ctx.local_ranks.map(r => `<option value="${r.rank}" ${r.rank === ctx.local_rank ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select>`) + reasonField(true),
      r => ({rank: +v(r, 'flocalrank'), expected_rank: ctx.local_rank, reason: v(r, 'freason')})];
    case 'rank': return [hint('Роль открывает разделы админки и права в боте. Выдать можно только роль ниже своей. Понадобится ввести ID игрока.')
        + field('Новая роль', `<select id="frank">${ctx.ranks.map(r => `<option value="${r.rank}" ${r.rank === ctx.rank ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select>`) + reasonField(),
      r => ({rank: +v(r, 'frank'), reason: v(r, 'freason')})];
    case 'warn_limit': return [hint('Сколько предупреждений в этом чате считается пределом: на нём бот напишет в чат.')
        + field('Предупреждений до наказания', `<input id="fval" type="number" min="1" max="20" value="${ctx.warn_limit || 3}"/>`), r => ({value: +v(r, 'fval')})];
    case 'message': return [hint('Сообщение сразу уйдёт в чат от имени бота, его увидят все участники.') + field('Текст (без разметки)', '<textarea id="ftext" maxlength="3500"></textarea>'),
      r => ({text: v(r, 'ftext')})];
    default: return [hint('Подтвердите действие.'), () => ({})];
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
const CONFIRM_TITLE = {ban: '⛔ Забанить в чате', kick: '👢 Выгнать из чата', global_ban: '🚫 Забанить во всех чатах', block: '🙈 Бот перестанет отвечать',
  balance: '💰 Изменить баланс', rank: '🎖 Изменить роль', vip: '👑 Выдать VIP', leave: '🚪 Бот выйдет из чата',
  message: '📣 Написать от бота', close: '🔒 Чат закроется', revoke_sessions: '🔒 Сессии админки завершатся'};
// Итог перед подтверждением: строки [подпись, значение-разметка].
function confirmLines(key, payload, ctx, extra) {
  const minutes = m => !m ? 'навсегда' : (DURATIONS.find(([x]) => x === m) || [0, m + ' мин'])[1];
  const lines = [];
  if (ctx.username !== undefined) lines.push(['Кто', `<b>${esc(ctx.name || '')}${ctx.name ? ' · ' : ''}${who(ctx.id, ctx.username)}</b> · ID ${ctx.id}${ctx.rank_name ? ' · ' + esc(ctx.rank_name) : ''}`]);
  const chat = extra.chat_title || ctx.title;
  if (chat) lines.push(['Чат', `<b>${esc(chat)}</b>`]);
  if (key === 'ban') lines.push(['Что', `Бан на <b>${minutes(payload.minutes)}</b>. Удалят из чата, обратно сам не войдёт.`]);
  else if (key === 'kick') lines.push(['Что', 'Удалят из чата, вернуться по ссылке сможет.']);
  else if (key === 'global_ban') lines.push(['Что', 'Потеряет доступ <b>во всех чатах бота</b>. Снять — «Снять бан во всех чатах».']);
  else if (key === 'block') lines.push(['Что', `Бот перестанет отвечать: <b>${payload.days ? payload.days + ' дн.' : 'пока не снимут'}</b>.`]);
  else if (key === 'balance') {
    const cur = ctx.currencies.find(c => c.code === payload.currency) || {title: payload.currency};
    const now = (ctx.balances || {})[payload.currency], delta = parseFloat(payload.amount);
    lines.push(['Сумма', `${esc(cur.title)}: <b>${delta > 0 ? '+' : ''}${esc(payload.amount)}</b>${now !== undefined && !Number.isNaN(delta) ? ` · было ${num(now)}, станет <b>${num(Math.round((now + delta) * 100) / 100)}</b>` : ''}`]);
  } else if (key === 'rank') lines.push(['Роль', `${esc(ctx.rank_name || '')} → <b>${esc((ctx.ranks.find(r => r.rank === payload.rank) || {}).name || payload.rank)}</b>`]);
  else if (key === 'vip') lines.push(['VIP', `+<b>${payload.days} дн.</b>${ctx.vip ? ` (сейчас осталось ${ctx.vip.days_left})` : ''}`]);
  else if (key === 'leave') lines.push(['Что', 'Бот выйдет из чата, обратно его придётся добавлять заново.']);
  else if (key === 'message') lines.push(['Текст', `Увидят все участники чата:<blockquote>${esc(payload.text || '')}</blockquote>`]);
  else if (key === 'close') lines.push(['Что', 'Участники не смогут писать, пока чат не откроют.']);
  else if (key === 'revoke_sessions') lines.push(['Что', 'Сотрудник выйдет из админки на всех устройствах. Роль не меняется.']);
  if (payload.reason) lines.push(['Причина', esc(payload.reason)]);
  return lines;
}
const summary = (lines, danger = true) => `<div class="sum ${danger ? 'danger' : ''}">${lines.map(([k, v]) => `<div><span>${k}</span><span>${v}</span></div>`).join('')}</div>`;

// Действие: форма → (для опасного) итог и подтверждение. «‹» с итога возвращает к форме с теми же полями.
// Один request_id на открытое действие: повторное «Подтвердить» после потерянного ответа не начислит дважды.
function runAction(action, target, ctx, extra, after) {
  ctx = {...ctx, _rid: newRid()};
  let lastSig = '';
  const [body, collect] = actionForm(action.key, ctx);
  const danger = DANGEROUS.has(action.key);
  const perform = async payload => {
    const res = await post(target, payload);
    rememberReason(payload.reason);
    closeSheets();
    toast(res.message || 'Готово', {ok: true});
    if (after) await after(res);
  };
  const form = openSheet({title: action.title, sub: [extra.who || (ctx.username !== undefined ? nameOf(ctx) : ''), extra.chat_title ? 'чат: ' + extra.chat_title : ''].filter(Boolean).join(' · '), body,
    actions: [{label: danger ? 'Далее' : 'Выполнить', kind: danger ? 'danger' : 'primary', run: async panel => {
      const req = panel.q('[data-required]');
      if (req && !req.value.trim()) { req.focus(); throw new Error('Укажите причину: она попадёт в журнал.'); }
      const payload = {action: action.key, ...collect(panel.el), ...(extra.chat_id ? {chat_id: extra.chat_id} : {})};
      // Тот же ключ — только для того же самого действия: поменяли сумму или срок после «‹» — это уже новое действие.
      const sig = JSON.stringify({...payload, request_id: 0});
      if (lastSig && sig !== lastSig && 'request_id' in payload) { ctx._rid = newRid(); payload.request_id = ctx._rid; }
      lastSig = sig;
      if (!danger) { await perform(payload); return 'keep'; }
      const typed = needsTypedConfirm(action.key, payload, ctx);
      openSheet({title: CONFIRM_TITLE[action.key] || action.title, sub: 'Проверьте перед выполнением',
        body: summary(confirmLines(action.key, payload, ctx, extra)) + (typed ? field(`Для подтверждения введите ID игрока: <b>${ctx.id}</b>`,
          '<input id="fconfirm" inputmode="numeric" autocomplete="off"/>') : ''),
        actions: [{label: 'Подтвердить', kind: 'btn danger fill', run: async p2 => {
          if (!typed) { await perform(payload); return 'keep'; }
          const typedId = (p2.q('#fconfirm').value || '').trim();
          if (typedId !== String(ctx.id)) throw new Error('ID не совпал: введите ' + ctx.id);
          await perform({...payload, confirm: typedId});
          return 'keep';
        }}]});
      return 'keep';
    }}, {label: 'Отмена', kind: '', run: null}]});
  wireFormChips(form.el);
  return form;
}

// Массовые действия над выбранными игроками: одна шторка, один запрос на всех, список тех, у кого не вышло.
const BULK_TITLES = {watch: '👁 На контроль', unwatch: 'Снять с контроля', unwarn_all: '🧽 Снять все предупреждения', mark_grant: '🏅 Выдать регалию', mark_revoke: '✖️ Снять регалию'};
const BULK_MAX = 50;
async function bulkRun(action, ids, after) {
  const count = `<p class="sub">Игроков: <b>${ids.length}</b>.</p>`;
  const send = async extra => {
    const res = await post('/players/bulk', {action, ids, ...extra});
    closeSheets();
    toast(res.message, {ok: !res.failed.length});
    if (res.failed.length) {
      sheet('Не всем получилось', `<p class="sub">${esc(res.message)}</p><div class="list">${res.failed.map(f =>
        row({title: who(f.id, f.username), sub: esc(f.reason)})).join('')}</div>`, 'Понятно', null, {info: true});
    }
    after();
    return 'keep';
  };
  let p;
  if (action === 'watch') p = sheet(BULK_TITLES[action], count + hint('Они появятся в фильтре «На контроле».') + reasonField(), 'Поставить', s => send({reason: s.q('#freason').value}));
  else if (action === 'mark_grant' || action === 'mark_revoke') {
    const marks = await api('/marks');
    p = sheet(BULK_TITLES[action], count + field('Регалия', `<select id="fmark">${marks.items.map(m => `<option value="${esc(m.id)}">${esc(m.glyph)} ${esc(m.title)}</option>`).join('')}</select>`) + reasonField(true),
      action === 'mark_grant' ? 'Выдать' : 'Снять', s => {
        if (!s.q('#freason').value.trim()) throw new Error('Укажите причину.');
        return send({mark: s.q('#fmark').value, reason: s.q('#freason').value});
      });
  } else p = sheet(BULK_TITLES[action], count + hint(action === 'unwarn_all' ? 'Все действующие предупреждения во всех чатах будут сняты.' : 'Они уйдут из фильтра «На контроле».'), 'Выполнить', () => send({}));
  wireFormChips(p.el);
}

// ── Глобальный поиск: игроки, чаты, промокоды и разделы из одного поля ───────

function searchSheet(initial = '') {
  if (!ME || ME.owner) return;   // владельцу поиск по базе не положен (owner.py)
  const panel = openSheet({title: 'Поиск', body: `<div class="search">${icon('search')}<input id="gq" placeholder="${has('people') ? 'Игрок, @ник, ID, чат' : 'Раздел'}${has('promo') ? ', промокод' : ''}" autocomplete="off" enterkeyhint="search" value="${esc(initial)}"/></div><div id="gres"></div>`});
  const input = panel.q('#gq'), out = panel.q('#gres');
  let timer, ctrl, seq = 0;
  const sections = q => ME.sections.filter(s => !q || s.title.toLowerCase().includes(q.toLowerCase()) || (SHORT[s.key] || '').toLowerCase().includes(q.toLowerCase()));
  const recent = () => {
    const rec = PREFS.get('recent', []);
    out.innerHTML = (rec.length ? sh('Недавно открывали') + `<div class="faces">${rec.map(r => `<button type="button" class="face" data-go="player/${r.id}">${ava({id: r.id, name: r.n, username: r.u, avatar: r.a})}<span>${esc(r.n || (r.u ? '@' + r.u : 'id' + r.id))}</span></button>`).join('')}</div>` : '')
      + sh('Разделы') + `<div class="list">${sections('').map(s => row({lead: lead(icon(s.key, 'ico'), 'accent'), title: esc(s.title), sub: esc(SECTION_HINT[s.key] || ''), data: {go: s.key}, tag: 'button'})).join('')}</div>`;
  };
  const find = async q => {
    const mine = ++seq;
    if (ctrl) ctrl.abort();
    ctrl = new AbortController();
    const wantPeople = has('people') && (q.length >= 2 || /^-?\d+$/.test(q));
    const jobs = [wantPeople ? api(`/search?q=${encodeURIComponent(q)}`, {signal: ctrl.signal}) : Promise.resolve(null)];
    jobs.push(has('promo') && q.length >= 2 ? api(`/promo?q=${encodeURIComponent(q)}`, {signal: ctrl.signal}) : Promise.resolve(null));
    const [people, promo] = await Promise.allSettled(jobs).then(rs => rs.map(r => r.status === 'fulfilled' ? r.value : null));
    if (mine !== seq) return;
    const secs = sections(q);
    const players = (people && people.players) || [], chats = (people && people.chats) || [], codes = ((promo && promo.items) || []).slice(0, 5);
    out.innerHTML = (players.length ? sh('Игроки', {count: players.length}) + `<div class="list">${players.slice(0, 8).map(p => playerRow(p, {}, q)).join('')}</div>` : '')
      + (chats.length ? sh('Чаты', {count: chats.length}) + `<div class="list">${chats.slice(0, 5).map(c => chatRow(c, {}, q)).join('')}</div>` : '')
      + (codes.length ? sh('Промокоды') + `<div class="list">${codes.map(p => row({lead: lead('🎟'), title: `<span class="code">${hl(p.code, q)}</span>`, sub: esc(p.rewards_text.join(' · ')), data: {go: 'promo/' + encodeURIComponent(p.code)}, tag: 'button'})).join('')}</div>` : '')
      + (secs.length ? sh('Разделы') + `<div class="list">${secs.map(s => row({lead: lead(icon(s.key, 'ico'), 'accent'), title: esc(s.title), data: {go: s.key}, tag: 'button'})).join('')}</div>` : '')
      || emptyBox('Ничего не нашлось', 'Попробуйте ID, @ник или часть названия.');
  };
  input.oninput = () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { seq++; recent(); return; }
    timer = setTimeout(() => find(q).catch(() => {}), 280);   // не на каждую букву: лишние запросы и входы в журнал
  };
  input.addEventListener('keydown', e => {   // Enter — открыть первый результат
    if (e.key !== 'Enter') return;
    const first = out.querySelector('[data-go], a[href^="#/"]');
    if (first) { e.preventDefault(); first.click(); }
  });
  out.addEventListener('click', e => {
    const b = e.target.closest('[data-go], a[href^="#/"]');
    if (!b) return;
    e.preventDefault();
    closeSheets();
    go(b.dataset.go || b.getAttribute('href').slice(2));
  });
  if (initial) input.oninput(); else recent();
  setTimeout(() => input.focus(), 60);
}
// Строки людей и чатов — одни и те же везде (поиск, внимание, выбор).
// Строки людей и чатов — одни и те же везде (поиск, внимание, выбор): лицо с кольцом состояния,
// имя крупно, @ник и «когда был» мельче, справа — значки (бан, мут, VIP…). q — что искали, подсвечивается.
function playerRow(p, extra = {}, q = '') {
  const tags = [p.rank_name ? pill(p.rank_name, 'accent', true) : '', ...(p.tags || []).slice(0, 2).map(t => `<span class="pill plain">🏷 ${hl(t, q)}</span>`)].join('');
  const seen = p.last ? `<span class="${isFresh(p.last) ? 'fresh' : ''}">был ${ago(p.last)}</span>` : 'не писал';
  return row({lead: ava({...p, online: isFresh(p.last, 1)}), title: p.name ? hl(p.name, q) : p.username ? '@' + hl(p.username, q) : 'id' + hl(String(p.id), q),
    sub: [p.name && p.username ? '@' + hl(p.username, q) : '', seen, p.messages ? `<span title="${num(p.messages)}">${short(p.messages)} сообщ.</span>` : ''].filter(Boolean).join(' · '),
    pills: tags, end: flagIcons(p.flags), href: '#/player/' + p.id, ...extra});
}
function chatRow(c, extra = {}, q = '') {
  const seen = c.last ? `<span class="${isFresh(c.last) ? 'fresh' : ''}">${ago(c.last)}</span>` : 'сообщений не было';
  return row({lead: chatAva(c), title: hl(c.title, q), sub: `👥 ${short(c.members)} · ${seen}`, href: '#/chat/' + c.id, ...extra});
}
function rememberPerson(p) {
  PREFS.set('recent', [{id: p.id, u: p.username || '', n: p.name || '', a: p.avatar || ''}, ...PREFS.get('recent', []).filter(r => r.id !== p.id)].slice(0, 8));
}

// ── Горячие клавиши (компьютер) ───────────────────────────────────────────────

const GO_KEYS = {h: 'home', p: 'people', r: 'reports', m: 'metrics', j: 'journal', b: 'broadcast', c: 'promo', f: 'switches', s: 'settings', e: 'health'};
const HOTKEYS = [['/', 'Поиск: игроки, чаты, промокоды, разделы'], ['g, затем h', 'Главная'], ['g, затем p', 'Игроки'], ['g, затем r', 'Жалобы'], ['g, затем m', 'Метрики'],
  ['g, затем j', 'Журнал'], ['g, затем b', 'Рассылка'], ['g, затем c', 'Промокоды'], ['g, затем f', 'Функции'], ['g, затем s', 'Настройки'], ['g, затем e', 'Состояние'],
  ['Esc', 'Закрыть окно или вернуться назад'], ['Ctrl + Enter', 'Главная кнопка окна'], ['?', 'Эта подсказка']];
function hotkeysSheet() {
  const mine = key => !/^g, /.test(key) || GO_KEYS[key.slice(-1)] === 'home' || has(GO_KEYS[key.slice(-1)]);
  sheet('Горячие клавиши', `<div class="keys">${HOTKEYS.filter(([key]) => mine(key)).map(([key, text]) =>
    `<div><kbd>${esc(key)}</kbd><span>${esc(text)}</span></div>`).join('')}</div>`, 'Понятно', null, {info: true});
}
(function initHotkeys() {
  let goAt = 0;
  document.addEventListener('keydown', e => {
    if (!ME || e.metaKey || e.altKey) return;
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName || '') || e.target.isContentEditable;
    if (e.key === 'Enter' && e.ctrlKey && SHEETS.length) {
      const ok = $('.sheet.is-top .sheet-f [data-sa="0"]');
      if (ok && !ok.disabled) { e.preventDefault(); ok.click(); }
      return;
    }
    if (e.key === 'Escape') {
      if (SHEETS.length) { e.preventDefault(); popSheet(); }
      else if (typing) e.target.blur();
      else goBack();
      return;
    }
    if (typing || e.ctrlKey || SHEETS.length) return;
    if (goAt && Date.now() - goAt < 1500) {
      goAt = 0;
      const key = GO_KEYS[e.key.toLowerCase()];
      if (key && (key === 'home' || has(key))) { e.preventDefault(); go(key === 'home' ? homePath() : key); }
      return;
    }
    if (e.key === 'g') { goAt = Date.now(); return; }
    if (e.key === '/') { e.preventDefault(); searchSheet(); }
    else if (e.key === '?') { e.preventDefault(); hotkeysSheet(); }
  });
})();

// ── Оболочка Telegram ────────────────────────────────────────────────────────

// Нет сети — постоянная полоска сверху, а не загадочные ошибки; вернулась — тихо обновляем экран.
// Вернулись в админку после перерыва (свернули Telegram) — данные на экране обновляются сами.
(function initFreshness() {
  const bar = () => {
    let b = $('#offline');
    if (navigator.onLine) { if (b) { b.remove(); if (canAutoRefresh()) render('soft'); } return; }
    if (!b) { b = Object.assign(document.createElement('div'), {id: 'offline', className: 'offline', textContent: 'Нет сети: показаны последние данные'}); b.setAttribute('role', 'status'); document.body.append(b); }
  };
  window.addEventListener('offline', bar); window.addEventListener('online', bar);
  let hiddenAt = 0;
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { hiddenAt = Date.now(); return; }
    if (ME && hiddenAt && Date.now() - hiddenAt > 60000) { refreshBadges(); if (canAutoRefresh()) render('soft'); }
  });
})();

(function initShell() {
  // Открыта клавиатура телефона (фокус в поле) — липкая панель и док не закрывают поля.
  document.addEventListener('focusin', e => { if (coarse() && /^(INPUT|TEXTAREA)$/.test(e.target.tagName) && !e.target.closest('.sheet')) document.body.classList.add('kb'); });
  document.addEventListener('focusout', () => setTimeout(() => { const a = document.activeElement; if (!a || !/^(INPUT|TEXTAREA)$/.test(a.tagName)) document.body.classList.remove('kb'); }, 50));
  $('#hback').onclick = () => goBack();
  $('#hsearch').onclick = () => searchSheet();
  window.addEventListener('scroll', () => $('.top').classList.toggle('scrolled', window.scrollY > 4), {passive: true});
  if (!TG) return;
  try { if (TG.disableVerticalSwipes) TG.disableVerticalSwipes(); } catch (_) {}   // смахивание не закрывает админку посреди формы
  try { if (TG.BackButton) TG.BackButton.onClick(goBack); } catch (_) {}         // один обработчик на всё время: не копятся
  document.addEventListener('click', e => {
    const t = e.target.closest('.btn, .chip, .row[data-on], .tile, .seg button');
    if (!t || t.disabled) return;
    haptic(t.classList.contains('primary') ? 'medium' : t.classList.contains('btn') ? 'light' : 'select');
  }, true);
})();
