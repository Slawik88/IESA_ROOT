// Админка Предвестника. Разделы приходят с сервера (/me) — по роли пользователя.
'use strict';

const BASE = window.ADMIN_BASE || '';
const TG = window.Telegram && window.Telegram.WebApp;
const INIT = (TG && TG.initData) || '';
const $ = (sel, root = document) => root.querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const num = n => Number(n).toLocaleString('ru-RU');

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
};
let _viewAbort = null, _viewRequest = 0, _loadStageTimers = [];

function currentSection() { return $('#tabs .on')?.dataset.tab || 'start'; }
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
function showLoadError(main, key, error, retry) {
  clearLoadStages(); main.setAttribute('aria-busy', 'false');
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

async function api(path, opts = {}) {
  const headers = {'content-type': 'application/json'};
  if (INIT) headers['x-init-data'] = INIT;
  try { const s = localStorage.getItem('pv_sess'); if (s) headers['x-session-token'] = s; } catch (_) {}
  const res = await fetch(`${BASE}/bot-admin/api${path}`, {...opts, headers});
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error((data && data.detail) || `Ошибка ${res.status}`);
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

function tabs(active) {
  $('#tabs').innerHTML = ME.sections.map(s =>
    `<button class="${s.key === active ? 'on' : ''}" data-tab="${s.key}">${esc(s.title)}</button>`).join('');
  const on = $('#tabs .on'); if (on && on.scrollIntoView) on.scrollIntoView({inline: 'center', block: 'nearest'});
}

function open(key) {
  if (TG && TG.BackButton) TG.BackButton.hide();
  if (_viewAbort) { _viewRequest++; _viewAbort.abort(); _viewAbort = null; }
  tabs(key);
  try { localStorage.setItem('pv_admin_tab', key); } catch (_) {}
  const render = SECTIONS[key];
  showSectionLoading($('#main'), key);
  if (render) render($('#main'));
}

document.addEventListener('click', e => {
  const tab = e.target.closest('[data-tab]');
  if (tab) open(tab.dataset.tab);
});

// ── Игроки и чаты: поиск, карточки, действия ─────────────────────────────────

const who = (id, username) => username ? '@' + esc(username) : 'id' + id;
const PEOPLE = {query: '', stack: []};   // stack — откуда пришли (для «Назад»)

function sheet(title, body, submitText, onSubmit) {
  const box = $('#sheet');
  box.innerHTML = `<div class="sheet"><h3>${esc(title)}</h3>${body}
    <div class="actions" style="margin-top:12px"><button class="btn primary" id="sok">${esc(submitText)}</button>
      <button class="btn" id="scancel">Отмена</button></div></div>`;
  box.hidden = false;
  const close = () => { box.hidden = true; box.innerHTML = ''; };
  $('#scancel').onclick = close;
  box.onclick = e => { if (e.target === box) close(); };
  $('#sok').onclick = async () => {
    $('#sok').disabled = true;
    try { if (await onSubmit(box) !== 'keep') close(); } catch (e) { toast(e.message, true); $('#sok').disabled = false; }
  };
}

const DURATIONS = [[15, '15 минут'], [60, '1 час'], [1440, '1 день'], [10080, '7 дней'], [43200, '30 дней'], [0, 'навсегда']];
const durationField = (def = 60) => `<div class="field"><label>Срок</label><select id="fmin">
  ${DURATIONS.map(([m, t]) => `<option value="${m}" ${m === def ? 'selected' : ''}>${t}</option>`).join('')}</select></div>`;
const reasonField = (required = false) => `<div class="field"><label>Причина${required ? '' : ' (необязательно)'}</label>
  <input id="freason" maxlength="200"/></div>`;

// Форма под каждое действие: поля + что отправить.
function actionForm(key, ctx) {
  const v = id => ($('#' + id) || {}).value;
  switch (key) {
    case 'warn': return [durationField(10080) + reasonField(), () => ({minutes: +v('fmin'), reason: v('freason')})];
    case 'mute': return [durationField(60) + reasonField(), () => ({minutes: +v('fmin'), reason: v('freason')})];
    case 'ban': return [durationField(0) + reasonField(), () => ({minutes: +v('fmin'), reason: v('freason')})];
    case 'kick': case 'global_ban': return [reasonField(), () => ({reason: v('freason')})];
    case 'block': return [`<div class="field"><label>На сколько</label><select id="fdays">
        <option value="1">1 день</option><option value="7">7 дней</option><option value="30">30 дней</option>
        <option value="0" selected>пока не снимут</option></select></div>` + reasonField(),
      () => ({days: +v('fdays'), reason: v('freason')})];
    case 'balance': return [`<div class="grid2"><div class="field"><label>Валюта</label><select id="fcur">
        ${ctx.currencies.map(c => `<option value="${c.code}">${esc(c.title)}</option>`).join('')}</select></div>
        <div class="field"><label>Сумма (минус — списать)</label><input id="famount" inputmode="decimal" placeholder="500 или -500"/></div></div>
        ${reasonField(true)}`,
      () => ({currency: v('fcur'), amount: (v('famount') || '').replace(',', '.').replace(/\s/g, ''), reason: v('freason'),
              request_id: ctx._rid})];
    case 'vip': return [`<div class="field"><label>Дней VIP (добавятся к текущему сроку)</label>
        <input id="fdays" type="number" min="1" max="3650" value="7"/>
        <div class="chips">${[7, 30, 90, 365].map(d => `<span class="chip" onclick="document.getElementById('fdays').value=${d}">${d} дн.</span>`).join('')}</div></div>` + reasonField(),
      () => ({days: +v('fdays'), reason: v('freason'), request_id: ctx._rid})];
    case 'rank': return [`<div class="field"><label>Новая роль</label><select id="frank">
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
    case 'warn_limit': return [`<div class="field"><label>Варнов до наказания</label>
        <input id="fval" type="number" min="1" max="20" value="${ctx.warn_limit || 3}"/></div>`, () => ({value: +v('fval')})];
    case 'message': return [`<div class="field"><label>Текст (без разметки)</label><textarea id="ftext" maxlength="3500"></textarea></div>`,
      () => ({text: v('ftext')})];
    default: return ['<div class="sub">Подтвердите действие.</div>', () => ({})];
  }
}

// Опасные действия просят подтверждение с итогом: кому, что именно и что изменится.
const DANGEROUS = new Set(['ban', 'kick', 'global_ban', 'block', 'balance', 'rank', 'vip', 'leave', 'message', 'close']);
const CONFIRM_TITLE = {ban: '⛔ Бан в чате', kick: '👢 Кик из чата', global_ban: '🚫 Бан во всех чатах', block: '🙈 Бот перестанет отвечать',
  balance: '💰 Изменение баланса', rank: '🎖 Новая глобальная роль', vip: '👑 Выдача VIP', leave: '🚪 Бот уйдёт из чата',
  message: '📣 Сообщение от бота в чат', close: '🔒 Чат закроется'};
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
    sheet(CONFIRM_TITLE[action.key] || action.title, `<div class="sub" style="margin-bottom:8px">Проверьте перед выполнением:</div>
      <div class="confirm">${confirmLines(action.key, payload, ctx, extra).map(l => `<div>${l}</div>`).join('')}</div>`,
      'Подтвердить', () => perform(payload));
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
        ${x.chat ? ' · ' + esc(x.chat.title || x.chat.id) : ''}${x.user ? ' · ' + who(x.user.id, x.user.username) : ''}</div></div>`).join('')}</div>`;
}

async function peopleSearch(main, query = '') {
  PEOPLE.query = query;
  if (TG && TG.BackButton) TG.BackButton.hide();
  main.innerHTML = `
    <div class="bar"><input id="pplq" placeholder="ID, @ник, имя или название чата" value="${esc(query)}" autocomplete="off"/></div>
    <div id="pplres"><div class="empty">Загрузка…</div></div>`;
  let timer;
  if (!(window.matchMedia && matchMedia('(pointer: coarse)').matches)) $('#pplq').focus();   // с клавиатуры сразу печатать; на телефоне клавиатуру без нужды не поднимаем
  $('#pplq').oninput = e => { clearTimeout(timer); timer = setTimeout(() => load(e.target.value), 250); };
  async function load(q) {
    PEOPLE.query = q;
    const host = $('#pplres'); if (!host) return;
    const data = await loadSectionData(host, `/search?q=${encodeURIComponent(q.trim())}`, () => load(q), 'people');
    if (!data) return;
    const {players, chats} = data;
    const head = q.trim() ? '' : '<div class="sub" style="margin-bottom:8px">Недавно активные</div>';
    $('#pplres').innerHTML = head + `
      <h3 class="sec">Игроки · ${players.length}</h3>
      <div class="list">${players.map(p => `<div class="row" data-player="${p.id}">
        <div class="head"><b>${who(p.id, p.username)}</b>${p.rank_name ? `<span class="chip">${esc(p.rank_name)}</span>` : ''}</div>
        <div class="sub">${p.name ? esc(p.name) + ' · ' : ''}ID ${p.id} · сообщений ${num(p.messages)}${p.last ? ' · был ' + when(p.last) : ''}</div></div>`).join('')
        || '<div class="sub">Никого</div>'}</div>
      <h3 class="sec">Чаты · ${chats.length}</h3>
      <div class="list">${chats.map(c => `<div class="row" data-chat="${c.id}">
        <div class="head"><b>${esc(c.title)}</b><span class="sub">${num(c.members)} уч.</span></div>
        <div class="sub">ID ${c.id} · сообщений ${num(c.messages)}${c.last ? ' · активность ' + when(c.last) : ''}</div></div>`).join('')
        || '<div class="sub">Ничего</div>'}</div>`;
  }
  $('#pplres').onclick = e => {
    const p = e.target.closest('[data-player]'), c = e.target.closest('[data-chat]');
    PEOPLE.stack = [];
    if (p) playerView(main, +p.dataset.player);
    else if (c) chatView(main, +c.dataset.chat);
  };
  load(query);
}

async function playerView(main, id, push = true, from = null) {
  const p = await loadSectionData(main, `/player/${id}`, () => playerView(main, id, push, from), 'people');
  if (!p) return;
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
  ].join(' ');
  // Глобальные действия — без взаимоисключающих пар.
  const hide = new Set([p.blocked ? 'block' : 'unblock', p.global_ban ? 'global_ban' : 'global_unban']);
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
      ${globalActs.length ? `<div class="actions" style="margin-top:12px">${globalActs.map(a =>
        `<button class="btn small ${/ban|block/.test(a.key) && !a.key.startsWith('un') && a.key !== 'global_unban' ? 'danger' : ''}" data-act="${a.key}">${esc(a.title)}</button>`).join('')}</div>` : ''}
    </div>
    ${marksCard}
    ${reportsCard}
    ${notesCard}
    <div class="card"><h3>Чаты · ${p.chats.length}</h3>
      ${p.chats.map(c => `<div class="member">
        <div class="head"><a href="#" data-chat="${c.id}"><b>${esc(c.title)}</b></a><span class="sub">${esc(c.rank_name)}</span></div>
        <div class="sub">сообщений ${num(c.messages)}${c.last ? ' · ' + when(c.last) : ''}</div>
        <div class="chips">${c.left ? '<span class="chip off">не в чате</span>' : ''}
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
  $('#noteadd').onclick = async () => {
    const text = $('#notetext').value.trim();
    if (!text) return toast('Напишите текст заметки', true);
    try { drawNotes(await api(`/player/${id}/notes`, {method: 'POST', body: JSON.stringify({text})})); $('#notetext').value = ''; toast('Заметка добавлена'); }
    catch (e) { toast(e.message, true); }
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

async function chatView(main, id, push = true, from = null) {
  const c = await loadSectionData(main, `/chat/${id}`, () => chatView(main, id, push, from), 'people');
  if (!c) return;
  if (push && from) PEOPLE.stack.push(from);
  const reopen = () => chatView(main, id, false);
  const m = c.messages;
  const acts = c.actions.chat.filter(a => !(a.key === 'close' && c.closed) && !(a.key === 'open' && !c.closed));
  const can = key => c.actions.member.find(a => a.key === key);
  const person = x => `<a href="#" data-player="${x.user}">${who(x.user, x.username)}</a>`;
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
        <span class="chip">⚠️ лимит варнов ${c.warn_limit}</span>
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
    <div class="card"><h3>Самые активные</h3>${c.top.map((x, i) => `<div class="sw-row"><div class="t">${i + 1}. ${person({user: x.id, username: x.username})}</div>
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

const tile = (label, value) => `<div><span>${label}</span><b>${value}</b></div>`;

async function metricsView(main, days = 1) {
  showSectionLoading(main, 'metrics');
  const m = await loadSectionData(main, `/metrics?days=${days}`, () => metricsView(main, days), 'metrics');
  if (!m) return;
  const s = m.site, b = m.bot, c = m.chats;
  const period = {1: 'Сегодня', 7: '7 дней', 30: '30 дней'};
  main.innerHTML = `
    <div class="scope">${Object.entries(period).map(([d, t]) =>
      `<button class="btn small ${+d === m.days ? 'primary' : ''}" data-days="${d}">${t}</button>`).join('')}
      <span class="sub">${m.days === 1 ? m.until.split('-').reverse().join('.') : m.since.split('-').reverse().join('.') + ' — ' + m.until.split('-').reverse().join('.')}</span></div>
    <div class="card"><h3>Всего</h3><div class="stats">
      ${tile('👤 Уникальных людей', num(m.everyone))}${tile('🗂 Игроков в базе', num(m.players_total))}
      ${tile('💬 Чатов с ботом', num(m.chats_total))}</div>
      <div class="sub" style="margin-top:8px">Уникальные — кто открыл приложение, вызвал команду или писал в чате с ботом.</div></div>
    <div class="card"><h3>📱 Мини-приложение</h3><div class="stats">
      ${tile('Посетителей', num(s.visitors))}${tile('Сессий', num(s.sessions))}${tile('Открытий вкладок', num(s.visits))}
      ${tile('Время всего', dur(s.seconds))}${tile('В среднем на человека', dur(s.avg_seconds_per_visitor))}</div>
      ${bars(m.day_list, s.daily, 'users', 'Посетители по дням')}
      ${s.pages.length ? `<table style="margin-top:12px"><tr><th>Вкладка</th><th>Открытий</th><th>Людей</th><th>Время</th><th>Среднее</th></tr>
        ${s.pages.map(p => `<tr><td>${esc(p.title)}</td><td>${num(p.visits)}</td><td>${num(p.users)}</td><td>${dur(p.seconds)}</td><td>${dur(p.avg_seconds)}</td></tr>`).join('')}</table>`
        : '<div class="sub" style="margin-top:8px">За период никто не открывал.</div>'}
      ${s.subpages.length ? `<details style="margin-top:10px"><summary class="sub">Разделы внутри вкладок · ${s.subpages.length}</summary>
        <table>${s.subpages.map(p => `<tr><td>${esc(p.tab)}</td><td>${num(p.visits)}</td><td>${num(p.users)} чел.</td></tr>`).join('')}</table></details>` : ''}
    </div>
    <div class="card"><h3>🤖 Команды бота</h3><div class="stats">
      ${tile('Команд', num(b.commands))}${tile('В чатах', num(b.commands_group))}${tile('В личке', num(b.commands_private))}
      ${tile('Людей', num(b.users))}${tile('Людей в чатах', num(b.users_group))}${tile('Людей в личке', num(b.users_private))}</div>
      ${bars(m.day_list, b.daily, 'users', 'Люди, вызывавшие команды, по дням')}
      ${b.top.length ? `<table style="margin-top:12px"><tr><th>Команда</th><th>В чатах</th><th>В личке</th><th>Всего</th></tr>
        ${b.top.map(x => `<tr><td>бот ${esc(x.command)}</td><td>${num(x.group)}</td><td>${num(x.private)}</td><td>${num(x.total)}</td></tr>`).join('')}</table>`
        : '<div class="sub" style="margin-top:8px">Команд за период не было.</div>'}
    </div>
    <div class="card"><h3>💬 Чаты</h3><div class="stats">
      ${tile('Сообщений', num(c.messages))}${tile('Писали', num(c.users) + ' чел.')}${tile('Активных чатов', num(c.chats))}</div>
      ${bars(m.day_list, c.daily, 'messages', 'Сообщения по дням')}
      ${c.top.length ? `<table style="margin-top:12px"><tr><th>Чат</th><th>Сообщений</th><th>Писали</th></tr>
        ${c.top.map(x => `<tr><td>${ME.sections.some(z => z.key === 'people') ? `<a href="#" data-chat="${x.id}">${esc(x.title)}</a>` : esc(x.title)}</td>
          <td>${num(x.messages)}</td><td>${num(x.users)}</td></tr>`).join('')}</table>` : ''}
    </div>`;
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

SECTIONS.metrics = main => metricsView(main);

// ── Журнал: все действия персонала ───────────────────────────────────────────

const JOURNAL = {kind: '', actor: 0, days: 7};
async function journalView(main, more = '') {
  const qs = `kind=${encodeURIComponent(JOURNAL.kind)}&actor=${JOURNAL.actor}&days=${JOURNAL.days}${more ? '&before=' + encodeURIComponent(more) : ''}`;
  const data = await loadSectionData(main, `/journal?${qs}`, () => journalView(main, more), 'journal');
  if (!data) return;
  const canPeople = ME.sections.some(z => z.key === 'people');
  const person = x => x && x.id ? (canPeople ? `<a href="#" data-player="${x.id}">${who(x.id, x.username)}</a>` : who(x.id, x.username)) : '';
  const rows = data.items.map(x => `<div class="log"><div><b>${esc(x.title)}</b> ${esc(x.text)}</div>
      ${x.reason ? `<div class="sub">Причина: ${esc(x.reason)}</div>` : ''}
      <div class="sub">${when(x.at)} · ${x.actor && x.actor.id ? person(x.actor) : 'бот'}${x.user ? ' → ' + person(x.user) : ''}${x.chat ? ' · ' + (canPeople ? `<a href="#" data-chat="${x.chat.id}">${esc(x.chat.title || x.chat.id)}</a>` : esc(x.chat.title || x.chat.id)) : ''}</div></div>`).join('');
  const body = rows || (more ? '' : '<div class="empty">За этот период действий нет.</div>');
  if (more) {
    main.querySelector('#jmore')?.remove();
    main.querySelector('#jlist').insertAdjacentHTML('beforeend', body);
  } else {
    main.innerHTML = `<div class="scope">${[[1, 'Сутки'], [7, '7 дней'], [30, '30 дней'], [90, '90 дней']].map(([d, t]) =>
        `<button class="btn small ${d === JOURNAL.days ? 'primary' : ''}" data-jdays="${d}">${t}</button>`).join('')}</div>
      <div class="grid2" style="margin:10px 0">
        <div class="field"><label>Что</label><select id="jkind"><option value="">Всё</option>${data.kinds.map(k =>
          `<option value="${k.key}" ${k.key === JOURNAL.kind ? 'selected' : ''}>${esc(k.title)}</option>`).join('')}</select></div>
        <div class="field"><label>Кто</label><select id="jactor"><option value="0">Все</option>${data.actors.map(a =>
          `<option value="${a.id}" ${a.id === JOURNAL.actor ? 'selected' : ''}>${a.username ? '@' + esc(a.username) : 'id' + a.id}</option>`).join('')}</select></div></div>
      <div class="card" id="jlist"><h3>Действия персонала</h3>${body}</div>`;
    main.querySelectorAll('[data-jdays]').forEach(b => b.onclick = () => { JOURNAL.days = +b.dataset.jdays; journalView(main); });
    $('#jkind').onchange = e => { JOURNAL.kind = e.target.value; journalView(main); };
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

async function reportsView(main, kind = 'open') {
  const data = await loadSectionData(main, `/reports?kind=${kind}`, () => reportsView(main, kind), 'reports');
  if (!data) return;
  const c = data.counts;
  const canPeople = ME.sections.some(z => z.key === 'people');
  const person = p => p ? (canPeople ? `<a href="#" data-player="${p.id}">${esc(p.name)}</a>` : esc(p.name)) : '—';
  const chipCls = {new: 'warn', in_work: '', resolved: 'ok', rejected: 'bad'};
  main.innerHTML = `
    <div class="scope"><button class="btn small ${kind === 'open' ? 'primary' : ''}" data-kind="open">Очередь · ${c.new + c.in_work}</button>
      <button class="btn small ${kind === 'closed' ? 'primary' : ''}" data-kind="closed">Закрытые · ${c.resolved + c.rejected}</button></div>
    <div class="sub" style="margin-bottom:8px">🔒 Жалобы анонимны. ${data.can_see_reporter ? 'Вам автор виден по настройкам жалоб.' : 'Автора жалобы видит только персонал с доступом.'}</div>
    ${data.items.length ? data.items.map(r => `<div class="card">
      <div><span class="chip ${chipCls[r.status] || ''}">${esc(r.status_title)}</span> <b>№${r.id}</b>
        <span class="sub">· ${when(r.created_at)} · ${esc(r.chat.title)}</span></div>
      <div style="margin-top:8px">На ${person(r.target)}${r.target_reports > 1 ? ` <span class="chip bad">жалоб всего: ${r.target_reports}</span>` : ''}
        <span class="sub">${r.reporter ? 'от ' + person(r.reporter) : '· автор скрыт'}</span></div>
      <div style="margin-top:6px"><b>Причина:</b> ${esc(r.reason)}</div>
      ${r.message_text ? `<div class="sub" style="margin-top:6px;white-space:pre-wrap">«${esc(r.message_text)}»</div>` : ''}
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
      'Выполнить', async () => {
        const res = await api(`/reports/${r.id}/punish`, {method: 'POST', body: JSON.stringify({action: key, ...collect(), close: $('#fclose').checked})});
        toast(res.message || 'Готово');
        reportsView(main, kind);
      });
  });
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

SECTIONS.reports = main => reportsView(main);

// ── Рассылка ─────────────────────────────────────────────────────────────────

// Предпросмотр HTML Telegram: всё экранируется, обратно включаются только теги, которые понимает Telegram.
function tgHtml(text) {
  return esc(text)
    .replace(/&lt;(\/?)(b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote|tg-spoiler)&gt;/g, '<$1$2>')
    .replace(/&lt;a href=&quot;(https?:\/\/[^&"]*)&quot;&gt;/g, '<a href="$1" target="_blank" rel="noopener">')
    .replace(/&lt;\/a&gt;/g, '</a>');
}

async function broadcastView(main) {
  const data = await loadSectionData(main, '/broadcasts', () => broadcastView(main), 'broadcast');
  if (!data) return;
  const running = data.items.some(b => b.status === 'running');
  main.innerHTML = `
    <div class="card"><h3>📣 Новая рассылка</h3>
      <div class="field"><label>Кому</label><select id="baud">${data.audiences.map(a =>
        `<option value="${a.key}">${esc(a.title)} · ${num(data.sizes[a.key] || 0)}</option>`).join('')}</select></div>
      <div class="field"><label>Текст (до 3500 символов)</label><textarea id="btext" maxlength="3500" rows="6"></textarea></div>
      <label class="sub" style="display:flex;gap:8px;align-items:center;margin-bottom:6px"><input type="checkbox" id="bhtml" checked/> HTML-разметка Telegram</label>
      <div class="sub" id="bhelp">Можно: &lt;b&gt;жирный&lt;/b&gt;, &lt;i&gt;курсив&lt;/i&gt;, &lt;u&gt;, &lt;s&gt;, &lt;code&gt;, &lt;blockquote&gt;, &lt;tg-spoiler&gt;, &lt;a href="https://…"&gt;ссылка&lt;/a&gt;.</div>
      <div class="sub" style="margin-top:6px">Предпросмотр</div><div class="card" id="bprev" style="white-space:pre-wrap;min-height:44px"></div>
      <div class="sub">В личку дойдёт только тем, кто хоть раз открывал диалог с ботом. Заблокированным и забаненным везде не отправляется.</div>
      <div class="actions" style="margin-top:10px"><button class="btn" id="btest">✉️ Отправить себе в личку</button>
        <button class="btn primary" id="bgo" ${running ? 'disabled' : ''}>Проверить и отправить</button></div>
      ${running ? '<div class="sub" style="margin-top:6px">Сейчас идёт другая рассылка.</div>' : ''}
    </div>
    <div class="card"><h3>История</h3>${data.items.length ? data.items.map(b => `
      <div class="log"><div><b>${esc(b.audience_title)}</b> · ${esc(b.status_title)} · ${num(b.sent)}/${num(b.total)}${b.failed ? ` · не дошло ${num(b.failed)}` : ''}
        ${b.status === 'running' ? `<button class="btn small" data-stop="${b.id}">⏹ Остановить</button>` : ''}</div>
        <div class="sub" style="white-space:pre-wrap">${(b.html ? tgHtml : esc)(b.text.length > 200 ? b.text.slice(0, 200) + '…' : b.text)}</div>
        <div class="sub">${when(b.created_at)} · ${esc(b.actor)}</div></div>`).join('') : '<div class="sub">Рассылок ещё не было.</div>'}</div>`;
  const html = () => $('#bhtml').checked;
  const draw = () => { const t = $('#btext').value; $('#bprev').innerHTML = html() ? tgHtml(t) : esc(t); $('#bhelp').hidden = !html(); };
  $('#btext').oninput = draw; $('#bhtml').onchange = draw; draw();
  $('#btest').onclick = async () => {
    const text = $('#btext').value.trim();
    if (!text) { toast('Напишите текст.', true); return; }
    $('#btest').disabled = true;
    try { toast((await api('/broadcasts/test', {method: 'POST', body: JSON.stringify({text, html: html()})})).message); }
    catch (e) { toast(e.message, true); }
    $('#btest').disabled = false;
  };
  $('#bgo').onclick = () => {
    const audience = $('#baud').value, text = $('#btext').value.trim(), isHtml = html();
    if (!text) { toast('Напишите текст.', true); return; }
    const a = data.audiences.find(x => x.key === audience);
    const rid = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()) + Math.random();
    sheet('Отправить рассылку?', `<div class="sub" style="margin-bottom:8px">${esc(a.title)} · ${num(data.sizes[audience] || 0)} получателей. Отменить уже отправленное нельзя.</div>
      <div class="card" style="white-space:pre-wrap">${isHtml ? tgHtml(text) : esc(text)}</div>`, 'Отправить', async () => {
      const res = await api('/broadcasts', {method: 'POST', body: JSON.stringify({audience, text, html: isHtml, request_id: rid})});
      toast(res.message || 'Запущено');
      broadcastView(main);
    });
  };
  main.querySelectorAll('[data-stop]').forEach(b => b.onclick = async () => {
    try { toast((await api(`/broadcasts/${b.dataset.stop}/stop`, {method: 'POST'})).message); } catch (e) { toast(e.message, true); }
    broadcastView(main);
  });
  if (running) setTimeout(() => { if ($('#bgo') && document.body.contains(main) && $('#tabs .on')?.dataset.tab === 'broadcast') broadcastView(main); }, 4000);
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
      <button class="btn primary" id="pnew">+ Новый</button></div>
    <div class="list" id="plist"><div class="empty">Загрузка…</div></div>`;
  $('#pnew').onclick = () => promoEdit(main, null);
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

async function promoView(main, code) {
  const p = await loadSectionData(main, `/promo/${encodeURIComponent(code)}`, () => promoView(main, code), 'promo');
  if (!p) return;
  main.innerHTML = `
    <div class="bar"><button class="btn" id="pback">← Все промокоды</button></div>
    <div class="card">
      <div class="head" style="display:flex;justify-content:space-between;gap:8px">
        <span class="code" style="font-size:20px">${esc(p.code)}</span>${promoStatus(p)}</div>
      ${p.note ? `<div class="sub" style="margin-top:6px">${esc(p.note)}</div>` : ''}
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
    <div class="card"><h3>Кто активировал · ${p.redemptions.length}</h3>
      ${p.redemptions.length ? `<table><tr><th>Игрок</th><th>Где</th><th>Когда</th><th>Получил</th></tr>
        ${p.redemptions.map(r => `<tr><td>${r.username ? '@' + esc(r.username) : r.user_id}<div class="sub">${r.user_id}</div></td>
          <td>${r.chat_id ? esc(r.chat_title || r.chat_id) : 'личка'}</td><td>${when(r.at)}</td>
          <td>${esc((r.granted || []).join(', '))}</td></tr>`).join('')}</table>` : '<div class="sub">Пока никто.</div>'}
    </div>`;
  $('#pback').onclick = () => promoList(main);
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
function skinPicker(currentId, onPick) {
  const box = $('#sheet'), all = OPTIONS.skins, priv = OPTIONS.private_skins || [], pool = [...all, ...priv];
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

async function promoEdit(main, p) {
  OPTIONS = OPTIONS || await api('/promo-options');
  const isNew = !p;
  const state = {
    rewards: p && p.rewards.length ? p.rewards.map(r => ({...r})) : [{type: 'mora', amount: ''}],
    chats: p ? p.chats.map(c => ({...c})) : [],
  };
  main.innerHTML = `
    <div class="bar"><button class="btn" id="pback">← Назад</button></div>
    <div class="card">
      <h3>${isNew ? 'Новый промокод' : 'Промокод ' + esc(p.code)}</h3>
      ${isNew ? `<div class="field"><label>Код (латиница, цифры, - и _)</label>
        <div class="bar" style="margin:0"><input id="fcode" maxlength="32" style="text-transform:uppercase"/>
        <button class="btn" id="fgen">Случайный</button></div></div>` : ''}
      <div class="field"><label>Награды</label><div id="frewards"></div>
        <button class="btn small" id="fadd">+ Награда</button></div>
      <div class="grid2">
        <div class="field"><label>Лимит активаций (0 — без лимита)</label><input id="fmax" type="number" min="0" value="${p ? p.max_activations : 0}"/></div>
        <div class="field switch"><input id="factive" type="checkbox" ${!p || p.is_active ? 'checked' : ''}/><label for="factive" style="margin:0">Включён</label></div>
        <div class="field"><label>Начало (необязательно)</label><input id="ffrom" type="datetime-local" value="${localInput(p && p.valid_from)}"/></div>
        <div class="field"><label>Конец (необязательно)</label><input id="funtil" type="datetime-local" value="${localInput(p && p.valid_until)}"/></div>
      </div>
      <div class="field"><label>Где активировать: пусто — везде, иначе только в выбранных чатах</label>
        <input id="fchatq" placeholder="Найти чат по названию или ID"/><div class="found" id="fchatfound"></div>
        <div class="chips" id="fchats"></div></div>
      <div class="field"><label>Только для игроков: пусто — для всех</label>
        <input id="fuserq" placeholder="Найти игрока по @нику или ID"/><div class="found" id="fuserfound"></div>
        <div class="chips" id="fusers"></div></div>
      <div class="field"><label>Заметка для себя</label><textarea id="fnote" maxlength="300">${esc(p ? p.note : '')}</textarea></div>
      <div class="actions"><button class="btn primary" id="fsave">${isNew ? 'Создать' : 'Сохранить'}</button></div>
    </div>`;
  $('#pback').onclick = () => (p ? promoView(main, p.code) : promoList(main));
  if (isNew) $('#fgen').onclick = () => {
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
      if ((OPTIONS.private_skins || []).some(k => k.id === id) && !+$('#fmax').value && !users.length) {
        $('#fmax').value = 1; toast('Личный образ: лимит активаций поставлен в 1');
      }
    });
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

  $('#fsave').onclick = async () => {
    const toIso = v => (v ? new Date(v).toISOString() : null);
    const body = {
      code: isNew ? $('#fcode').value.trim().toUpperCase() : p.code,
      rewards: state.rewards, max_activations: +$('#fmax').value || 0, is_active: $('#factive').checked,
      valid_from: toIso($('#ffrom').value), valid_until: toIso($('#funtil').value),
      allowed_chats: state.chats.map(c => c.id), allowed_users: users.map(u => u.id), note: $('#fnote').value,
    };
    try {
      const saved = isNew
        ? await api('/promo', {method: 'POST', body: JSON.stringify(body)})
        : await api(`/promo/${encodeURIComponent(p.code)}`, {method: 'PUT', body: JSON.stringify(body)});
      toast(isNew ? 'Промокод создан' : 'Сохранено');
      promoView(main, saved.code);
    } catch (e) { toast(e.message, true); }
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
    ${reportSettingsCard(data)}`;
  bindReportSettings(main, data);
  main.querySelectorAll('[data-cur]').forEach(input => {
    input.onchange = async () => {
      const currencies = [...main.querySelectorAll('[data-cur]')].filter(x => x.checked && !x.disabled).map(x => x.dataset.cur);
      try { await api('/settings/transfer', {method: 'POST', body: JSON.stringify({currencies})}); toast('Сохранено'); settingsView(main); }
      catch (e) { toast(e.message, true); input.checked = !input.checked; }
    };
  });
}

SECTIONS.settings = main => settingsView(main);

// ── Старт ────────────────────────────────────────────────────────────────────

(async () => {
  if (TG) { try { TG.ready(); TG.expand(); } catch (_) {} }
  showSectionLoading($('#main'), 'start');
  try {
    ME = await api('/me');
  } catch (e) {
    $('#main').innerHTML = `<div class="empty">${esc(e.message)}<br><br>Откройте админку из Telegram: напишите боту в личку <b>бот админка</b>.</div>`;
    return;
  }
  $('#who').textContent = ME.rank_name;
  if (!ME.sections.length) { $('#main').innerHTML = '<div class="empty">Для вашей роли разделов пока нет.</div>'; return; }
  let saved = '';
  try { saved = localStorage.getItem('pv_admin_tab') || ''; } catch (_) {}
  open(ME.sections.some(s => s.key === saved) ? saved : ME.sections[0].key);
})();
