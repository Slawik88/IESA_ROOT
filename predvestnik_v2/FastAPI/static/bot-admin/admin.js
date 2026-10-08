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
}

function open(key) {
  tabs(key);
  try { localStorage.setItem('pv_admin_tab', key); } catch (_) {}
  const render = SECTIONS[key];
  $('#main').innerHTML = '<div class="empty">Загрузка…</div>';
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
    try { await onSubmit(box); close(); } catch (e) { toast(e.message, true); $('#sok').disabled = false; }
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
              request_id: (crypto.randomUUID && crypto.randomUUID()) || String(Date.now())})];
    case 'vip': return [`<div class="field"><label>Дней VIP (добавятся к текущему сроку)</label>
        <input id="fdays" type="number" min="1" max="3650" value="7"/></div>` + reasonField(),
      () => ({days: +v('fdays'), reason: v('freason')})];
    case 'rank': return [`<div class="field"><label>Новая роль</label><select id="frank">
        ${ctx.ranks.map(r => `<option value="${r.rank}" ${r.rank === ctx.rank ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select></div>`
        + reasonField(), () => ({rank: +v('frank'), reason: v('freason')})];
    case 'warn_limit': return [`<div class="field"><label>Варнов до наказания</label>
        <input id="fval" type="number" min="1" max="20" value="${ctx.warn_limit || 3}"/></div>`, () => ({value: +v('fval')})];
    case 'message': return [`<div class="field"><label>Текст (без разметки)</label><textarea id="ftext" maxlength="3500"></textarea></div>`,
      () => ({text: v('ftext')})];
    default: return ['<div class="sub">Подтвердите действие.</div>', () => ({})];
  }
}

function runAction(action, target, ctx, extra, after) {
  const [body, collect] = actionForm(action.key, ctx);
  const place = extra.chat_title ? `<div class="sub" style="margin-bottom:10px">Чат: ${esc(extra.chat_title)}</div>` : '';
  sheet(action.title, place + body, 'Выполнить', async () => {
    const payload = {action: action.key, ...collect(), ...(extra.chat_id ? {chat_id: extra.chat_id} : {})};
    const res = await api(target, {method: 'POST', body: JSON.stringify(payload)});
    toast(res.message || 'Готово');
    after();
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

function wireBack(main) {
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
  main.innerHTML = `
    <div class="bar"><input id="pplq" placeholder="ID, @ник или название чата" value="${esc(query)}" autocomplete="off"/></div>
    <div id="pplres"><div class="empty">Загрузка…</div></div>`;
  let timer;
  $('#pplq').oninput = e => { clearTimeout(timer); timer = setTimeout(() => load(e.target.value), 250); };
  async function load(q) {
    PEOPLE.query = q;
    const {players, chats} = await api(`/search?q=${encodeURIComponent(q.trim())}`);
    const head = q.trim() ? '' : '<div class="sub" style="margin-bottom:8px">Недавно активные</div>';
    $('#pplres').innerHTML = head + `
      <h3 class="sec">Игроки · ${players.length}</h3>
      <div class="list">${players.map(p => `<div class="row" data-player="${p.id}">
        <div class="head"><b>${who(p.id, p.username)}</b>${p.rank_name ? `<span class="chip">${esc(p.rank_name)}</span>` : ''}</div>
        <div class="sub">ID ${p.id} · сообщений ${num(p.messages)}${p.last ? ' · был ' + when(p.last) : ''}</div></div>`).join('')
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
  load(query).catch(e => toast(e.message, true));
}

async function playerView(main, id, push = true, from = null) {
  const p = await api(`/player/${id}`).catch(e => { toast(e.message, true); return null; });
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
  const globalActs = p.actions.player.filter(a => !hide.has(a.key));
  const memberActs = c => p.actions.member.filter(a =>
    !(a.key === 'mute' && c.muted) && !(a.key === 'unmute' && !c.muted) && !(a.key === 'unban' && !c.ban)
    && !(a.key === 'ban' && c.ban) && !(a.key === 'kick' && (c.left || c.ban)) && !(a.key === 'unwarn_all' && !c.warns));
  main.innerHTML = `${backBar()}
    <div class="card">
      <div class="head" style="display:flex;justify-content:space-between;gap:8px;align-items:baseline">
        <span style="font-size:20px;font-weight:700">${who(p.id, p.username)}</span><span class="sub">ID ${p.id}</span></div>
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
  main.querySelectorAll('[data-mact]').forEach(btn => btn.onclick = () =>
    runAction(p.actions.member.find(a => a.key === btn.dataset.mact), `/player/${id}/action`, p,
      {chat_id: +btn.dataset.cid, chat_title: btn.dataset.ctitle}, reopen));
  main.querySelectorAll('a[data-chat]').forEach(a => a.onclick = e => { e.preventDefault(); chatView(main, +a.dataset.chat, true, here); });
  main.querySelectorAll('a[data-player]').forEach(a => a.onclick = e => { e.preventDefault(); playerView(main, +a.dataset.player, true, here); });
}

async function chatView(main, id, push = true, from = null) {
  const c = await api(`/chat/${id}`).catch(e => { toast(e.message, true); return null; });
  if (!c) return;
  if (push && from) PEOPLE.stack.push(from);
  const reopen = () => chatView(main, id, false);
  const m = c.messages;
  const acts = c.actions.chat.filter(a => !(a.key === 'close' && c.closed) && !(a.key === 'open' && !c.closed));
  const can = key => c.actions.member.find(a => a.key === key);
  const person = x => `<a href="#" data-player="${x.user}">${who(x.user, x.username)}</a>`;
  const sanction = (title, rows, line, undo) => rows.length ? `<h3 class="sec">${title} · ${rows.length}</h3>${rows.map(x => `
      <div class="sw-row"><div class="t">${person(x)}<div class="sub">${line(x)}</div></div>
      ${can(undo) ? `<button class="btn small" data-undo="${undo}" data-uid="${x.user}">${esc(can(undo).title)}</button>` : ''}</div>`).join('')}` : '';
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
    ${s.bans.length || s.mutes.length || s.warns.length ? `<div class="card">
      ${sanction('⛔ Баны', s.bans, x => (x.until ? 'до ' + when(x.until) : 'навсегда') + (x.reason ? ' · ' + esc(x.reason) : ''), 'unban')}
      ${sanction('🔇 Муты', s.mutes, x => x.until ? 'до ' + when(x.until) : 'навсегда', 'unmute')}
      ${sanction('⚠️ Варны', s.warns, x => 'действующих: ' + x.count, 'unwarn_all')}</div>` : ''}
    ${historyCard(c.history)}`;
  wireBack(main);
  const here = {type: 'chat', id};
  main.querySelectorAll('[data-act]').forEach(btn => btn.onclick = () =>
    runAction(c.actions.chat.find(a => a.key === btn.dataset.act), `/chat/${id}/action`, c, {}, reopen));
  main.querySelectorAll('[data-undo]').forEach(btn => btn.onclick = () =>
    runAction(can(btn.dataset.undo), `/player/${btn.dataset.uid}/action`, c, {chat_id: id, chat_title: c.title}, reopen));
  main.querySelectorAll('a[data-player]').forEach(a => a.onclick = e => { e.preventDefault(); playerView(main, +a.dataset.player, true, here); });
  main.querySelectorAll('a[data-chat]').forEach(a => a.onclick = e => { e.preventDefault(); chatView(main, +a.dataset.chat, true, here); });
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
  main.innerHTML = '<div class="empty">Считаю…</div>';
  const m = await api(`/metrics?days=${days}`).catch(e => { toast(e.message, true); return null; });
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
  main.querySelectorAll('[data-days]').forEach(btn => btn.onclick = () => metricsView(main, +btn.dataset.days));
  main.querySelectorAll('a[data-chat]').forEach(a => a.onclick = e => {
    e.preventDefault(); tabs('people'); PEOPLE.stack = []; chatView(main, +a.dataset.chat);
  });
}

SECTIONS.metrics = main => metricsView(main);

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
    const {items} = await api(`/promo?q=${encodeURIComponent(q)}`);
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
  load(query).catch(e => toast(e.message, true));
}

async function promoView(main, code) {
  const p = await api(`/promo/${encodeURIComponent(code)}`).catch(e => { toast(e.message, true); return null; });
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
      <div class="field"><label>Только для игроков (ID через запятую, пусто — для всех)</label>
        <input id="fusers" value="${p ? p.allowed_users.join(', ') : ''}"/></div>
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
        ? `<select data-i="${i}" data-k="id">${OPTIONS.skins.map(s => `<option value="${esc(s.id)}" ${s.id === r.id ? 'selected' : ''}>${esc(s.name)} · ${esc(s.tier)}</option>`).join('')}</select>`
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

  $('#fsave').onclick = async () => {
    const toIso = v => (v ? new Date(v).toISOString() : null);
    const users = $('#fusers').value.split(/[\s,;]+/).filter(Boolean);
    if (users.some(x => !/^\d+$/.test(x))) return toast('ID игроков — только цифры через запятую', true);
    const body = {
      code: isNew ? $('#fcode').value.trim().toUpperCase() : p.code,
      rewards: state.rewards, max_activations: +$('#fmax').value || 0, is_active: $('#factive').checked,
      valid_from: toIso($('#ffrom').value), valid_until: toIso($('#funtil').value),
      allowed_chats: state.chats.map(c => c.id), allowed_users: users.map(Number), note: $('#fnote').value,
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
  const data = await api(`/switches?chat_id=${chat ? chat.id : 0}`).catch(e => { toast(e.message, true); return null; });
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
      <div class="t"><b>${esc(item.title)}</b>${item.hint ? `<div class="sub">${esc(item.hint)}</div>` : ''}
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

async function settingsView(main) {
  const data = await api('/settings').catch(e => { toast(e.message, true); return null; });
  if (!data) return;
  main.innerHTML = `
    <div class="card"><h3>Переводы между игроками</h3>
      <div class="sub" style="margin-bottom:6px">Какие валюты можно отправить командой «бот перевод».</div>
      ${data.transfer.map(c => `<div class="sw-row ${c.enabled ? '' : 'off'}">
        <div class="t"><b>${esc(c.title)}</b>${c.locked ? '<div class="sub">Переводить нельзя никогда</div>' : ''}</div>
        <label class="toggle"><input type="checkbox" data-cur="${c.code}" ${c.enabled ? 'checked' : ''} ${c.locked ? 'disabled' : ''}/><span></span></label>
      </div>`).join('')}
    </div>`;
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
