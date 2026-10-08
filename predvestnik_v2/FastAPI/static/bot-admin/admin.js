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
