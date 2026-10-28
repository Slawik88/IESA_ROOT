// ── Общие хелперы страницы ──────────────────────
// Админка чата, глобальная модерация и консоль разработчика удалены (код);
// новая админка пишется с нуля.
function esc(s) { return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// Refresh current page data
function refreshPage() {
  const page = _activePage;
  const rb = document.querySelector('.hdr-refresh');
  if (rb) { rb.classList.remove('spinning'); void rb.offsetWidth; rb.classList.add('spinning'); }
  const loaders = {
    profile:loadProfile, more:loadProfile, arena:loadArena
  };
  if(page && loaders[page]) { _loaded.delete(page); loaders[page](); toast('Данные обновлены'); }
}

// Запросы «Чистки»: отказ показывается текстом сервера, потерянный ответ не повторяет действие.
async function purgeWebApi(path, options = {}) {
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 25000);
  try {
    const response = await fetch(BASE+path,{...options,headers:{...hdrs(),...(options.headers || {})},signal:controller.signal});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) handleAuthRefusal(response.headers.get('x-auth-reason') || '');
      const error = new Error(typeof data.detail==='string' ? data.detail : 'Не удалось выполнить действие. Проверь данные и попробуй снова.');
      error.status = response.status; throw error;
    }
    if ((options.method || 'GET')!=='GET' && typeof _scheduleReactiveRefresh==='function') _scheduleReactiveRefresh();
    return data;
  } catch (e) {
    if (e?.name === 'AbortError') throw new Error('Ответ не получен. Проверь сохранённое состояние перед повтором.');
    throw e;
  } finally { clearTimeout(timeout); }
}
// «Ещё» открывают часто, а чистка доступна немногим: короткая проверка доступа, «нет» помним 10 минут (S04).
const PURGE_ENTRY_RECHECK_MS = 10 * 60 * 1000;
let _purgeEntryDeniedAt = 0;
async function loadPurgeEntry() {
  const root = el('pg-more'); if (!root || el('more-purge-entry')) return;
  if (_purgeEntryDeniedAt && Date.now() - _purgeEntryDeniedAt < PURGE_ENTRY_RECHECK_MS) return;
  try {
    const d = await purgeWebApi('/purge-v1/access');
    if (!d.available) { _purgeEntryDeniedAt = Date.now(); return; }
    if (el('more-purge-entry')) return;
    const b = document.createElement('button'); b.type = 'button'; b.id = 'more-purge-entry'; b.className = 'v3-row';
    b.dataset.navKey = 'purge'; b.innerHTML = `${_v3Icon('manage')}<span>Чистка чатов<small>Досье и решения, общие с Telegram</small></span><span class="v3-end">${_v3Icon('chev')}</span>`; b.onclick = () => openPurgeHub();
    const group = root.querySelector('[data-nav-group="community"]'); if (group) group.append(b); else root.append(b);
    orderNavigation();
  } catch (_) { /* ordinary players have no moderation entry */ }
}

// ── «Чистка» (S05) ─────────────────────────────────────────────────────────
// Страница хода чистки. Решения принимает сервер, тот же, что в Telegram: потерянный ответ не повторяет санкцию,
// экран просто перечитывает ход. Экран подписан на живые события (data_changed{scope:'purge'}, live=1) и раз в
// PURGE_FALLBACK_MS перечитывает ход на случай обрыва связи; неизменившийся ход сервер отдаёт как 304.
const PURGE_FALLBACK_MS = 15000;
const PURGE_LABELS = {forgive:'Оставлен', skip:'Пропущен (бот)', warn:'Варн', mute:'Мут на час', kick:'Исключён', ban:'Бан'};
const PURGE_ACTIONS = [
  ['forgive', 'Оставить', 'Оставить участника', 'Ничего не будет: участник остаётся в чате.'],
  ['warn', 'Варн', 'Выдать варн', 'Предупреждение без срока. Сколько варнов ведут к наказанию, решает настройка чата.'],
  ['mute', 'Мут на час', 'Мут на час', 'Участник час не сможет писать.'],
  ['kick', 'Исключить', 'Исключить из чата', 'Участник выйдет из чата, но сможет вернуться по ссылке.'],
  ['ban', 'Бан', 'Забанить навсегда', 'Участник выйдет из чата и не сможет вернуться. Снять бан можно командой «бот снять бан».'],
];
let _purge = {chats: null, cid: 0, mode: 'pending', page: 0, view: null, etag: '', seq: 0, busy: false, loading: false,
              timer: 0, error: '', denied: false, drafts: {}, lastStart: null, returnTo: null};

function _purgeVisible() { return _activePage === 'purge' && !!el('pg-purge'); }
function _purgeId(key) {
  let id; try { id = localStorage.getItem(key); } catch (_) {}
  id ||= typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `purge-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  try { localStorage.setItem(key, id); } catch (_) {}
  return id;
}
function _purgeForget(key) { try { localStorage.removeItem(key); } catch (_) {} }
// GET хода с ETag: 304 — ничего не изменилось. Отдельно от purgeWebApi, потому что нужен заголовок ответа.
async function _purgeFetch(path) {
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 25000);
  try {
    const headers = {...hdrs(), ...(_purge.etag ? {'If-None-Match': _purge.etag} : {})};
    const response = await fetch(BASE + path, {headers, signal: controller.signal});
    if (response.status === 304) return {status: 304};
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) handleAuthRefusal(response.headers.get('x-auth-reason') || '');
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'Не удалось загрузить чистку.');
      error.status = response.status; throw error;
    }
    return {status: response.status, data, etag: response.headers.get('etag') || ''};
  } catch (e) {
    if (e?.name === 'AbortError') throw new Error('Нет ответа. Проверь связь.');
    throw e;
  } finally { clearTimeout(timeout); }
}

async function openPurgeHub(cid = 0) {
  switchPage('purge');
  _purgeRememberDraft();
  if (cid) _purge.cid = Number(cid);
  _purge.error = ''; _purge.denied = false; _purge.etag = '';
  const seq = ++_purge.seq;
  _purgeRender();
  try {
    const d = await purgeWebApi('/purge-v1/chats');
    while (d.next_offset !== null && d.next_offset !== undefined) { const next = await purgeWebApi(`/purge-v1/chats?offset=${d.next_offset}`); d.items.push(...next.items); d.next_offset = next.next_offset; }
    if (seq !== _purge.seq) return;
    _purge.chats = d.items || [];
    if (!_purge.chats.some(c => c.id === _purge.cid)) { _purge.cid = _purge.chats[0]?.id || 0; _purge.view = null; _purge.page = 0; }
  } catch (e) {
    if (seq === _purge.seq) { _purge.error = e.message || 'Нет связи.'; _purgeRender(); }
    return;
  }
  if (!_purge.cid) { _purgeRender(); return; }
  await purgeLoad();
}
function purgeBack() {
  clearTimeout(_purge.timer); _purgeRememberDraft(); ++_purge.seq;
  if (_navStack.length) navBack(); else switchPage('more', null, true);
}
function purgePick(cid) {
  if (_purge.busy) return null;
  _purgeRememberDraft(); _purge.cid = Number(cid); _purge.view = null; _purge.page = 0; _purge.mode = 'pending'; _purge.etag = '';
  _purge.denied = false;
  return purgeLoad();
}
function purgeFilter(mode) { if (_purge.busy) return null; _purge.mode = mode; _purge.page = 0; _purge.etag = ''; return purgeLoad(); }
function purgePage(page) { if (_purge.busy) return null; _purge.page = Math.max(0, page); _purge.etag = ''; return purgeLoad(); }

function _purgeSchedule() {
  clearTimeout(_purge.timer);
  if (!_purgeVisible() || _purge.denied || !_purge.cid) return;
  _purge.timer = setTimeout(() => {
    if (!_purgeVisible()) return;
    if (document.hidden || _purge.busy || el('cf-sheet') || el('modal')?.open) { _purgeSchedule(); return; }
    purgeLoad(true);
  }, PURGE_FALLBACK_MS);
}
// Живое событие с сервера (app.01.js): ход этого чата изменился
function purgeLive(event) {
  if (!_purgeVisible() || Number(event?.chat_id) !== _purge.cid || _purge.busy || _purge.loading) return null;
  return purgeLoad(true);
}
document.addEventListener('visibilitychange', () => { if (!document.hidden && _purgeVisible() && !_purge.busy) purgeLoad(true); });

async function purgeLoad(quiet = false) {
  if (!_purgeVisible() || !_purge.cid || (quiet && _purge.loading)) return;
  const cid = _purge.cid, seq = ++_purge.seq;
  _purge.loading = true;
  if (!quiet) { _purge.error = ''; _purgeRender(); }
  try {
    const answer = await _purgeFetch(`/purge-v1/chats/${cid}?live=1&page=${_purge.page}&mode=${_purge.mode}`);
    if (seq !== _purge.seq || !_purgeVisible()) return;
    _purge.denied = false; _purge.error = '';
    if (answer.status === 304 && _purge.view) return;
    _purge.view = answer.data; _purge.etag = answer.etag || ''; _purge.page = answer.data.page || 0;
    _purgeRender(quiet);
  } catch (e) {
    if (seq !== _purge.seq) return;
    if (e?.status === 403 || e?.status === 401) { _purge.denied = true; _purge.view = null; _purge.etag = ''; }
    _purge.error = e.message || 'Нет связи.';
    _purgeRender(quiet);
  } finally {
    if (seq === _purge.seq) { _purge.loading = false; _purgeSchedule(); }
  }
}

function _purgeRememberDraft() {
  if (!_purge.cid || !el('pg-norm')) return;
  _purge.drafts[_purge.cid] = {norm: el('pg-norm').value, from: el('pg-from').value, to: el('pg-to').value};
}
const _purgeDay = iso => { const d = iso ? new Date(`${String(iso).slice(0, 10)}T12:00:00`) : null; return d && !isNaN(d) ? d.toLocaleDateString('ru-RU', {day: 'numeric', month: 'short'}) : esc(iso || ''); };
const _purgeName = t => t.member_tag || (t.username ? '@' + t.username : 'Участник ' + t.user_id);
const _purgeHelp = () => `<details class="pg-help"><summary>Как устроена чистка</summary><p>Бот находит тех, кто за период написал меньше нормы. Новичкам и тем, кто был в муте, норма уменьшается.</p><p>Чат закрыт, пока идёт чистка: писать могут только участники с рангом для чистки.</p><p>Решение по каждому принимаешь ты или другой админ — здесь или кнопками под досье в Telegram.</p><button type="button" class="v3-link" onclick="v3Guide('purge')">Подробнее в Путеводителе</button></details>`;

function _purgeRender(quiet = false) {
  const root = el('pg-purge'); if (!root) return;
  const scroll = quiet ? (document.scrollingElement?.scrollTop || 0) : null;
  _purgeRememberDraft();
  const head = v3Head('Чистка', {sub: 'Кто не набрал норму сообщений', back: 'purgeBack()'});
  root.innerHTML = `${head}<div class="pg-body">${_purgeBody()}</div>`;
  const draft = _purge.drafts[_purge.cid];
  if (draft && el('pg-norm')) { el('pg-norm').value = draft.norm; el('pg-from').value = draft.from; el('pg-to').value = draft.to; }
  if (scroll !== null) try { document.scrollingElement.scrollTop = scroll; } catch (_) {}
}
function _purgeBody() {
  if (_purge.chats === null) {
    return _purge.error
      ? `<div class="v3-empty" role="alert"><b>Чаты не загрузились</b> ${esc(_purge.error)} <button type="button" class="v3-link" onclick="openPurgeHub()">Повторить</button></div>`
      : '<p class="v3-empty" role="status">Загружаю твои чаты…</p>';
  }
  if (!_purge.chats.length) return '<p class="v3-empty">Нет чатов, где твой ранг разрешает чистку.</p>';
  const pick = _purge.chats.length > 1
    ? `<label class="v3-eyebrow pg-label" for="pg-chat">Чат</label><select id="pg-chat" class="v3-field" onchange="purgePick(this.value)" ${_purge.busy ? 'disabled' : ''}>${_purge.chats.map(c => `<option value="${c.id}"${c.id === _purge.cid ? ' selected' : ''}>${esc(c.title)}</option>`).join('')}</select>`
    : `<p class="v3-stat-line"><b>${esc(_purge.chats[0].title)}</b></p>`;
  const v = _purge.view;
  if (_purge.denied) return `${pick}<div class="v3-empty" role="alert"><b>Нет доступа</b> ${esc(_purge.error)} <button type="button" class="v3-link" onclick="openPurgeHub()">Проверить снова</button></div>`;
  if (!v) {
    return pick + (_purge.error
      ? `<div class="v3-empty" role="alert"><b>Чистка не загрузилась</b> ${esc(_purge.error)} <button type="button" class="v3-link" onclick="purgeLoad()">Повторить</button></div>`
      : '<p class="v3-empty" role="status">Загружаю…</p>');
  }
  const offline = _purge.error ? `<p class="tr-err" role="status">${esc(_purge.error)} Показано последнее, что загрузилось.</p>` : '';
  return pick + offline + (v.active ? _purgeActive(v) : _purgeIdle(v));
}
function _purgeIdle(v) {
  const job = v.preparing;
  if (job?.state === 'preparing') {
    return `<section class="pg-state" role="status"><b>Готовлю список…</b><p class="tr-note">Считаю сообщения участников с ${_purgeDay(job.date_from)} по ${_purgeDay(job.date_to)}, норма ${fmt(job.norm)}. Обычно это несколько секунд.</p></section>${_purgeHelp()}`;
  }
  const failed = job?.state === 'failed'
    ? `<div class="v3-empty" role="alert"><b>Чистка не началась</b> ${esc(job.error || '')} <button type="button" class="v3-link" onclick="purgeRetryStart()" ${_purge.busy ? 'disabled' : ''}>Повторить</button></div>` : '';
  const done = v.completed?.counts;
  const result = done ? `<p class="tr-note">Прошлая чистка (${_purgeDay(v.completed.date_from)} — ${_purgeDay(v.completed.date_to)}): решено ${fmt(done.decided)} из ${fmt(done.total)}, исключено ${fmt(done.kicked)}, забанено ${fmt(done.banned)}.</p>` : '';
  const d = v.defaults || {};
  return `${failed}<section class="pg-form"><label class="v3-eyebrow pg-label" for="pg-norm">Норма сообщений за период</label><input id="pg-norm" class="v3-field" type="number" inputmode="numeric" min="1" max="100000" value="100">
    <div class="pg-dates"><span><label class="v3-eyebrow pg-label" for="pg-from">С</label><input id="pg-from" class="v3-field" type="date" value="${esc(d.date_from || '')}" max="${esc(d.today || '')}"></span><span><label class="v3-eyebrow pg-label" for="pg-to">По</label><input id="pg-to" class="v3-field" type="date" value="${esc(d.date_to || '')}" max="${esc(d.today || '')}"></span></div>
    <button type="button" class="v3-pill v3-pill--full" onclick="purgeStart(this)" ${_purge.busy ? 'disabled' : ''}>Начать чистку</button>
    <p class="tr-note">Оба дня входят в период. Чат закроется до конца чистки, Мафия в нём встанет на паузу.</p></section>${result}${_purgeHelp()}`;
}
function _purgeActive(v) {
  const s = v.session, c = v.counts, waiting = c.total - c.decided;
  const sending = v.dossiers_running && c.sent < c.total;
  const shown = sending ? c.sent : c.decided, of = Math.max(1, c.total);
  const state = sending
    ? `<b>Отправляю досье: ${fmt(c.sent)} из ${fmt(c.total)}</b><small>Досье уходят в админ-чат по одному, решать можно уже сейчас</small>`
    : `<b>Решено ${fmt(c.decided)} из ${fmt(c.total)}</b><small>${_purgeDay(s.date_from)} — ${_purgeDay(s.date_to)} · норма ${fmt(s.norm)}</small>`;
  const tabs = [['pending', `Ждут · ${fmt(waiting)}`], ['decided', 'Решённые'], ['all', 'Все']]
    .map(([key, title]) => `<button type="button" role="tab" class="v3-tab${_purge.mode === key ? ' on' : ''}" aria-selected="${_purge.mode === key}" onclick="purgeFilter('${key}')">${title}</button>`).join('');
  const rows = v.items.map(t => {
    const stuck = ['sending', 'unknown'].includes(t.decision_state);
    const end = t.verdict ? esc(PURGE_LABELS[t.verdict] || t.verdict) : stuck ? 'Проверить' : _v3Icon('chev');
    return `<button type="button" class="v3-row pg-row" data-purge-user="${t.user_id}" onclick="purgeOpen(${t.user_id})"><span>${esc(_purgeName(t))}<small>${fmt(t.msg_count)} из ${fmt(t.required_norm ?? s.norm)} сообщений${t.member_tag && t.username ? ' · @' + esc(t.username) : ''}</small></span><span class="v3-end">${end}</span></button>`;
  }).join('');
  const empty = {pending: 'Все решения приняты. Можно завершать.', decided: 'Решений пока нет.', all: 'В этой чистке никого нет.'}[_purge.mode];
  const pages = (v.page ? `<button type="button" class="v3-link" onclick="purgePage(${v.page - 1})">‹ Предыдущие</button>` : '')
    + (v.has_more ? `<button type="button" class="v3-link" onclick="purgePage(${v.page + 1})">Следующие ›</button>` : '');
  return `<section class="pg-state" role="status">${state}<span class="pg-meter" aria-hidden="true"><i style="width:${Math.round(100 * shown / of)}%"></i></span></section>
    <nav class="v3-tabs" role="tablist" aria-label="Досье">${tabs}</nav>
    <div class="pg-list">${rows || `<p class="v3-empty">${empty}</p>`}</div>${pages ? `<div class="pg-pages">${pages}</div>` : ''}
    <button type="button" class="v3-pill v3-pill--full v3-pill--ghost pg-finish" onclick="purgeFinish()" ${c.blocked || _purge.busy ? 'disabled' : ''}>Завершить чистку</button>
    <p class="tr-note">${c.blocked ? 'Завершить можно, когда Telegram ответит на все решения.' : 'Кто останется без решения, останется без наказания. Чат откроется.'}</p>${_purgeHelp()}`;
}

// Подробности участника и решения — лист поверх страницы
function purgeOpen(uid) {
  const v = _purge.view, t = v?.items.find(x => x.user_id === uid); if (!t || !v.active) return;
  const facts = `<p class="v3-stat-line"><b>${fmt(t.msg_count)}</b> из ${fmt(t.required_norm ?? v.session.norm)} сообщений за период</p><p class="tr-note">В чате ${fmt(t.days_in_chat)} дн · варнов на начало чистки: ${fmt(t.warns)}. Норма уже учитывает дату входа и время в муте.</p><p><a class="v3-link" href="tg://user?id=${t.user_id}">Открыть профиль в Telegram</a></p>`;
  if (t.verdict) {
    const who = t.verdict_by ? ` · ${esc(t.verdict_by_name || t.verdict_by_username || 'админ')}` : '';
    OM(_purgeName(t), `${facts}<p class="tr-ok">Решение: ${esc(PURGE_LABELS[t.verdict] || t.verdict)}${who}</p>`, [{l: 'Назад', f: 'CM()'}]);
    return;
  }
  if (['sending', 'unknown'].includes(t.decision_state)) {
    const note = t.reconcile_ready ? '' : '<p class="tr-note">Telegram ещё отвечает. Если ответа не будет, проверить вручную можно через две минуты.</p>';
    OM(_purgeName(t), `${facts}<p class="tr-err" role="status">${esc(t.decision_error || 'Решение отправлено в Telegram. Не повторяй его, пока не проверишь участника.')}</p>${note}`,
      [{l: 'Назад', f: 'CM()'}, ...(t.reconcile_ready ? [{l: 'Проверить вручную', f: `purgeReconcile(${uid})`}] : [])]);
    return;
  }
  const buttons = PURGE_ACTIONS.map(([key, label]) => `<button type="button" class="v3-pill v3-pill--ghost" onclick="purgeDecide(${uid},'${key}',this)">${label}</button>`).join('');
  OM(_purgeName(t), `${facts}${t.decision_error ? `<p class="tr-note">${esc(t.decision_error)}</p>` : ''}<div class="pg-acts" role="group" aria-label="Решение">${buttons}</div>`, [{l: 'Назад', f: 'CM()'}]);
}

async function _purgePost(path, body, button) {
  if (_purge.busy) return null;
  const cid = _purge.cid; _purge.busy = true; ++_purge.seq; clearTimeout(_purge.timer);
  if (button) button.disabled = true;
  try { return await purgeWebApi(`/purge-v1/chats/${cid}/${path}`, {method: 'POST', body: JSON.stringify(body)}); }
  catch (e) { toast(e.message || String(e), false); return null; }
  finally { _purge.busy = false; _purge.loading = false; _purge.etag = ''; if (button?.isConnected) button.disabled = false; if (_purge.cid === cid) await purgeLoad(true); }
}
async function purgeStart(button) {
  if (_purge.busy || !el('pg-norm')) return;
  const body = {norm: Number(el('pg-norm').value), date_from: el('pg-from').value, date_to: el('pg-to').value}, cid = _purge.cid;
  if (!Number.isInteger(body.norm) || body.norm < 1 || body.norm > 100000 || !body.date_from || !body.date_to || body.date_from > body.date_to) { toast('Проверь норму и даты: «С» не позже «По».', false); return; }
  const title = _purge.chats.find(c => c.id === cid)?.title || 'Чат';
  if (!await v3Confirm({title: 'Начать чистку?', visual: '🧹', name: title, sub: 'Чат закроется до конца чистки. Наказания выбираешь сам, по каждому.', rows: [['Период', `${_purgeDay(body.date_from)} — ${_purgeDay(body.date_to)}`], ['Норма', String(body.norm)]], cta: 'Начать чистку'}) || cid !== _purge.cid || !_purgeVisible()) return;
  _purge.lastStart = {cid, body};
  await _purgeSendStart(cid, body, button);
}
function purgeRetryStart() { const last = _purge.lastStart; if (last && last.cid === _purge.cid) _purgeSendStart(last.cid, last.body, null); else purgeLoad(); }
async function _purgeSendStart(cid, body, button) {
  const key = `pv-purge-start:${cid}:${body.norm}:${body.date_from}:${body.date_to}`;
  const result = await _purgePost('start?background=1', {...body, action_id: _purgeId(key)}, button);
  if (result?.ok) { _purgeForget(key); delete _purge.drafts[cid]; }
}
async function purgeDecide(uid, action, button) {
  const v = _purge.view, t = v?.items.find(x => x.user_id === uid), cid = _purge.cid; if (!t || _purge.busy) return;
  const [, , title, what] = PURGE_ACTIONS.find(a => a[0] === action);
  if (!await v3Confirm({title, visual: '🧹', name: _purgeName(t), sub: what, rows: [['Сообщений', `${fmt(t.msg_count)} из ${fmt(t.required_norm ?? v.session.norm)}`]], cta: title})) return;
  if (cid !== _purge.cid || _purge.view?.session?.id !== v.session.id) return;
  const key = `pv-purge:${cid}:${v.session.id}:${uid}:${action}`;
  CM();
  const result = await _purgePost('decision', {session_id: v.session.id, user_id: uid, action, action_id: _purgeId(key)}, button);
  if (result?.ok) { _purgeForget(key); if (result.replayed) toast('Другой админ уже решил. Показано его решение.'); }
}
async function purgeFinish() {
  const v = _purge.view, cid = _purge.cid; if (!v?.active || _purge.busy) return;
  const waiting = v.counts.total - v.counts.decided;
  if (!await v3Confirm({title: 'Завершить чистку?', visual: '🧹', name: _purge.chats.find(c => c.id === cid)?.title || 'Чат', sub: 'Чат откроется. Кто остался без решения, останется без наказания.', rows: [['Без решения', String(waiting)]], cta: 'Завершить'})) return;
  if (cid === _purge.cid && _purge.view?.session?.id === v.session.id) await _purgePost('finish', {session_id: v.session.id});
}
function purgeReconcile(uid) {
  const v = _purge.view; if (!v?.active || _purge.busy) return;
  OM('Проверка решения', `<p>Сначала посмотри, что с участником в Telegram: в чате ли он, есть ли бан или ограничение. Эта проверка ничего не отправляет повторно.</p><label class="v3-eyebrow pg-label" for="pg-reconcile-applied">Что ты увидел</label><select id="pg-reconcile-applied" class="v3-field"><option value="">Выбери</option><option value="yes">Наказание применилось</option><option value="no">Наказания точно нет</option></select><label class="v3-eyebrow pg-label" for="pg-reconcile-reason">Что именно проверил (12–300 знаков)</label><textarea id="pg-reconcile-reason" class="v3-field" minlength="12" maxlength="300"></textarea><p id="pg-reconcile-error" class="tr-err" role="alert"></p>`,
    [{l: 'Назад', f: `purgeOpen(${uid})`}, {l: 'Записать', f: `purgeReconcileGo(${v.session.id},${uid})`, c: 'primary'}]);
}
async function purgeReconcileGo(sid, uid) {
  if (_purge.busy) return;
  const value = el('pg-reconcile-applied')?.value, reason = el('pg-reconcile-reason')?.value.trim() || '', error = el('pg-reconcile-error');
  if (!value || reason.length < 12) { if (error) error.textContent = 'Выбери, что увидел, и опиши проверку (от 12 знаков).'; return; }
  el('mf')?.querySelectorAll('button').forEach(b => b.disabled = true);
  const result = await _purgePost('reconcile', {session_id: sid, user_id: uid, applied: value === 'yes', reason});
  if (result?.ok) CM(); else el('mf')?.querySelectorAll('button').forEach(b => b.disabled = false);
}
