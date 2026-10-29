// ── «Чистка» внутри админки (S10) ───────────────────────────────────────────
// Тот же сервер, что у Mini App и команд бота (/purge-v1, S05): решения общие, потерянный ответ не повторяет санкцию.
// Экран не уводит из админки: «Назад» возвращает в карточку чата. Ход обновляется живым событием
// (admin-live.js, data_changed{scope:'purge'}) и раз в PURGE_FALLBACK_MS на случай обрыва; неизменившийся ход — 304.
// Загружается после admin.js и до admin-boot.js.

const PURGE_FALLBACK_MS = 15000;
const PURGE_VERDICTS = {forgive: 'Оставлен', skip: 'Пропущен (бот)', warn: 'Варн', mute: 'Мут на час', kick: 'Исключён', ban: 'Бан'};
const PURGE_DECISIONS = [['forgive', 'Оставить', 'Ничего не будет: участник остаётся в чате.'],
  ['warn', 'Варн', 'Предупреждение без срока. Сколько варнов ведут к наказанию, решает настройка чата.'],
  ['mute', 'Мут на час', 'Участник час не сможет писать.'],
  ['kick', 'Исключить', 'Участник выйдет из чата, но сможет вернуться по ссылке.'],
  ['ban', 'Бан', 'Участник выйдет из чата и не сможет вернуться. Снимается кнопкой «Снять бан в чате».']];
const PURGE = {cid: 0, title: '', mode: 'pending', page: 0, view: null, etag: '', busy: false, timer: 0, back: null, main: null};

// Ключ действия переживает потерянный ответ: повтор того же решения сервер узнаёт и не повторяет санкцию.
function purgeKey(name) {
  let id = '';
  try { id = localStorage.getItem(name) || ''; } catch (_) {}
  id ||= (crypto.randomUUID && crypto.randomUUID()) || `purge-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  try { localStorage.setItem(name, id); } catch (_) {}
  return id;
}
function purgeForget(name) { try { localStorage.removeItem(name); } catch (_) {} }

async function purgeApi(path, opts = {}) {
  const headers = {'content-type': 'application/json', ...(opts.headers || {})};
  if (INIT) headers['x-init-data'] = INIT;
  try { const s = localStorage.getItem('pv_sess'); if (s) headers['x-session-token'] = s; } catch (_) {}
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 25000);
  try {
    const res = await fetch(`${BASE}/purge-v1${path}`, {...opts, headers, signal: controller.signal});
    if (res.status === 304) return {status: 304};
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(typeof data.detail === 'string' ? data.detail : `Ошибка ${res.status}`), {status: res.status});
    return {status: res.status, data, etag: res.headers.get('etag') || ''};
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('Ответ не получен. Посмотрите ход ещё раз перед повтором.');
    throw e;
  } finally { clearTimeout(timer); }
}

const purgeVisible = () => !!(PURGE.main && PURGE.main.isConnected && PURGE.main.querySelector('#purgeview'));
const purgeDay = iso => { const d = iso ? new Date(`${String(iso).slice(0, 10)}T12:00:00`) : null; return d && !isNaN(d) ? d.toLocaleDateString('ru-RU', {day: 'numeric', month: 'short'}) : esc(iso || ''); };
const purgeName = t => t.member_tag || (t.username ? '@' + t.username : 'Участник ' + t.user_id);

async function purgeView(main, cid, title, from = null, back = null) {
  if (from) PEOPLE.stack.push(from);
  Object.assign(PURGE, {cid: +cid, title, mode: 'pending', page: 0, view: null, etag: '', main,
    back: back || (() => window.back(main))});   // из карточки чата: «Назад» ведёт в неё (она в PEOPLE.stack)
  main.innerHTML = `<div class="bar"><button class="btn" id="pgback">← Назад</button></div>
    <div id="purgeview"><div class="card"><h3>🧹 Чистка · ${esc(title || cid)}</h3><div class="sub">Загружаю ход…</div></div></div>`;
  $('#pgback').onclick = () => { clearTimeout(PURGE.timer); PURGE.main = null; PURGE.back(); };
  window.scrollTo(0, 0);
  await purgeLoad();
}

function purgeSchedule() {
  clearTimeout(PURGE.timer);
  if (!purgeVisible()) return;
  PURGE.timer = setTimeout(() => {
    if (!purgeVisible()) return;
    if (document.hidden || PURGE.busy || !$('#sheet').hidden) { purgeSchedule(); return; }
    purgeLoad(true);
  }, PURGE_FALLBACK_MS);
}
// Живое событие: ход этого чата изменился (admin-live.js)
function purgeLive(event) {
  if (purgeVisible() && Number(event.chat_id) === PURGE.cid && !PURGE.busy) purgeLoad(true);
}

async function purgeLoad(quiet = false) {
  if (!purgeVisible()) return;
  const cid = PURGE.cid;
  try {
    const answer = await purgeApi(`/chats/${cid}?live=1&page=${PURGE.page}&mode=${PURGE.mode}`, {headers: PURGE.etag ? {'If-None-Match': PURGE.etag} : {}});
    if (cid !== PURGE.cid || !purgeVisible()) return;
    if (answer.status !== 304 || !PURGE.view) { PURGE.view = answer.data; PURGE.etag = answer.etag; PURGE.page = answer.data.page || 0; }
    purgeRender(quiet);
  } catch (e) {
    if (!purgeVisible()) return;
    if (e.status === 403 || e.status === 401) PURGE.view = null;
    $('#purgeview').innerHTML = `<div class="card"><h3>🧹 Чистка · ${esc(PURGE.title || cid)}</h3>
      <div class="sub" role="alert">${e.status === 403 ? 'Нет доступа: ' : 'Не загрузилось: '}${esc(e.message)}</div>
      ${PURGE.view ? '' : '<div class="actions"><button class="btn small" id="pgretry">Повторить</button></div>'}</div>`;
    if ($('#pgretry')) $('#pgretry').onclick = () => purgeLoad();
  } finally { purgeSchedule(); }
}

function purgeRender(quiet) {
  const keep = quiet ? window.scrollY : 0, v = PURGE.view;
  $('#purgeview').innerHTML = `<div class="card"><h3>🧹 Чистка · ${esc(PURGE.title || PURGE.cid)}</h3>
    <div class="sub">Кто за период написал меньше нормы. Решения общие с Telegram: досье в админ-чате и этот экран — одно и то же.</div></div>
    ${v.active ? purgeActive(v) : purgeIdle(v)}`;
  purgeWire();
  if (quiet) window.scrollTo(0, keep);
}

function purgeIdle(v) {
  const job = v.preparing;
  if (job && job.state === 'preparing') {
    return `<div class="card" role="status"><b>Готовлю список…</b><div class="sub">Считаю сообщения с ${purgeDay(job.date_from)} по ${purgeDay(job.date_to)}, норма ${num(job.norm)}. Обычно это несколько секунд.</div></div>`;
  }
  const failed = job && job.state === 'failed' ? `<div class="card" role="alert"><b>Чистка не началась</b><div class="sub">${esc(job.error || '')}</div></div>` : '';
  const done = v.completed && v.completed.counts;
  const d = v.defaults || {};
  return `${failed}<div class="card"><h3>Начать чистку</h3>
    <div class="field"><label for="pgnorm">Норма сообщений за период</label><input id="pgnorm" type="number" inputmode="numeric" min="1" max="100000" value="100"/></div>
    <div class="grid2"><div class="field"><label for="pgfrom">С</label><input id="pgfrom" type="date" value="${esc(d.date_from || '')}" max="${esc(d.today || '')}"/></div>
      <div class="field"><label for="pgto">По</label><input id="pgto" type="date" value="${esc(d.date_to || '')}" max="${esc(d.today || '')}"/></div></div>
    <div class="sub hint">Оба дня входят в период. Чат закроется до конца чистки, Мафия в нём встанет на паузу.</div>
    <div class="actions"><button class="btn primary" id="pgstart">Начать чистку</button></div>
    ${done ? `<div class="sub" style="margin-top:8px">Прошлая чистка (${purgeDay(v.completed.date_from)} — ${purgeDay(v.completed.date_to)}): решено ${num(done.decided)} из ${num(done.total)}, исключено ${num(done.kicked)}, забанено ${num(done.banned)}.</div>` : ''}</div>`;
}

function purgeActive(v) {
  const s = v.session, c = v.counts, waiting = c.total - c.decided;
  const sending = v.dossiers_running && c.sent < c.total;
  const shown = sending ? c.sent : c.decided;
  const state = sending ? `<b>Отправляю досье: ${num(c.sent)} из ${num(c.total)}</b><div class="sub">Досье уходят в админ-чат по одному, решать можно уже сейчас</div>`
    : `<b>Решено ${num(c.decided)} из ${num(c.total)}</b><div class="sub">${purgeDay(s.date_from)} — ${purgeDay(s.date_to)} · норма ${num(s.norm)}</div>`;
  const rows = v.items.map(t => {
    const stuck = ['sending', 'unknown'].includes(t.decision_state);
    const end = t.verdict ? `<span class="chip ${t.verdict === 'forgive' ? 'ok' : 'warn'}">${esc(PURGE_VERDICTS[t.verdict] || t.verdict)}</span>` : stuck ? '<span class="chip bad">проверить</span>' : '<span class="arr">›</span>';
    return `<button type="button" class="arow" data-pgu="${t.user_id}"><span class="atxt"><b>${esc(purgeName(t))}</b>
      <small>${num(t.msg_count)} из ${num(t.required_norm ?? s.norm)} сообщений${t.member_tag && t.username ? ' · @' + esc(t.username) : ''}</small></span>${end}</button>`;
  }).join('');
  const empty = {pending: 'Все решения приняты. Можно завершать.', decided: 'Решений пока нет.', all: 'В этой чистке никого нет.'}[PURGE.mode];
  return `<div class="card" role="status">${state}<div class="meter" aria-hidden="true"><i style="width:${Math.round(100 * shown / Math.max(1, c.total))}%"></i></div></div>
    <div class="chips filters">${[['pending', `Ждут · ${num(waiting)}`], ['decided', 'Решённые'], ['all', 'Все']].map(([k, t]) =>
      `<span class="chip ${PURGE.mode === k ? 'ok' : ''}" data-pgmode="${k}">${t}</span>`).join('')}</div>
    <div class="card">${rows || `<div class="sub">${empty}</div>`}
      ${v.page || v.has_more ? `<div class="actions">${v.page ? '<button class="btn small" data-pgpage="-1">‹ Предыдущие</button>' : ''}${v.has_more ? '<button class="btn small" data-pgpage="1">Следующие ›</button>' : ''}</div>` : ''}</div>
    <div class="actions"><button class="btn" id="pgfinish" ${c.blocked ? 'disabled' : ''}>Завершить чистку</button></div>
    <div class="sub">${c.blocked ? 'Завершить можно, когда Telegram ответит на все решения.' : 'Кто останется без решения, останется без наказания. Чат откроется.'}</div>`;
}

function purgeWire() {
  const v = PURGE.view;
  if ($('#pgstart')) $('#pgstart').onclick = () => purgeStart();
  if ($('#pgfinish')) $('#pgfinish').onclick = () => {
    const waiting = v.counts.total - v.counts.decided;
    sheet('🧹 Завершить чистку?', `<div class="confirm"><div>Чат: <b>${esc(PURGE.title)}</b></div><div>Без решения: <b>${num(waiting)}</b> — они останутся без наказания.</div><div>Чат откроется.</div></div>`,
      'Завершить', () => purgePost('finish', {session_id: v.session.id}));
  };
  document.querySelectorAll('[data-pgmode]').forEach(b => b.onclick = () => { if (PURGE.busy) return; PURGE.mode = b.dataset.pgmode; PURGE.page = 0; PURGE.etag = ''; purgeLoad(); });
  document.querySelectorAll('[data-pgpage]').forEach(b => b.onclick = () => { if (PURGE.busy) return; PURGE.page = Math.max(0, PURGE.page + +b.dataset.pgpage); PURGE.etag = ''; purgeLoad(); });
  document.querySelectorAll('[data-pgu]').forEach(b => b.onclick = () => purgeOpen(+b.dataset.pgu));
}

async function purgePost(path, body) {
  if (PURGE.busy) return null;
  PURGE.busy = true; clearTimeout(PURGE.timer);
  try { const res = await purgeApi(`/chats/${PURGE.cid}/${path}`, {method: 'POST', body: JSON.stringify(body)}); return res.data; }
  catch (e) { toast(e.message, true); return null; }
  finally { PURGE.busy = false; PURGE.etag = ''; purgeLoad(true); }
}

function purgeStart() {
  const body = {norm: +$('#pgnorm').value, date_from: $('#pgfrom').value, date_to: $('#pgto').value};
  if (!Number.isInteger(body.norm) || body.norm < 1 || body.norm > 100000 || !body.date_from || !body.date_to || body.date_from > body.date_to) {
    toast('Проверьте норму и даты: «С» не позже «По».', true); return;
  }
  sheet('🧹 Начать чистку?', `<div class="confirm"><div>Чат: <b>${esc(PURGE.title)}</b></div><div>Период: <b>${purgeDay(body.date_from)} — ${purgeDay(body.date_to)}</b></div>
    <div>Норма: <b>${num(body.norm)}</b></div><div>Чат закроется до конца чистки. Наказание выбираете сами, по каждому.</div></div>`, 'Начать чистку', async () => {
    const name = `pv-purge-start:${PURGE.cid}:${body.norm}:${body.date_from}:${body.date_to}`;
    const res = await purgePost('start?background=1', {...body, action_id: purgeKey(name)});
    if (res && res.ok) purgeForget(name);
  });
}

function purgeOpen(uid) {
  const v = PURGE.view, t = v && v.items.find(x => x.user_id === uid);
  if (!t || !v.active) return;
  const facts = `<div class="confirm"><div><b>${num(t.msg_count)}</b> из ${num(t.required_norm ?? v.session.norm)} сообщений за период</div>
    <div>В чате ${num(t.days_in_chat)} дн. · варнов на начало чистки: ${num(t.warns)}. Норма уже учитывает дату входа и время в муте.</div></div>
    <div class="actions"><button class="btn small" data-pgcard="${uid}">Карточка игрока ›</button></div>`;
  if (t.verdict) {
    sheet(purgeName(t), `${facts}<div class="sub">Решение: <b>${esc(PURGE_VERDICTS[t.verdict] || t.verdict)}</b>${t.verdict_by ? ' · ' + esc(t.verdict_by_name || t.verdict_by_username || 'админ') : ''}</div>`, 'Закрыть', () => {}, {info: true});
  } else if (['sending', 'unknown'].includes(t.decision_state)) {
    sheet(purgeName(t), `${facts}<div class="sub" role="status">${esc(t.decision_error || 'Решение отправлено в Telegram. Не повторяйте его, пока не проверите участника.')}</div>
      ${t.reconcile_ready ? '<div class="actions"><button class="btn small" id="pgcheck">Проверить вручную</button></div>' : '<div class="sub">Если Telegram не ответит, проверить вручную можно через две минуты.</div>'}`, 'Закрыть', () => {}, {info: true});
    if ($('#pgcheck')) $('#pgcheck').onclick = () => purgeReconcile(uid);
  } else {
    sheet(purgeName(t), `${facts}${t.decision_error ? `<div class="sub">${esc(t.decision_error)}</div>` : ''}<div class="sec-title">Решение</div>
      ${PURGE_DECISIONS.map(([key, label, what]) => `<button type="button" class="arow${key === 'ban' || key === 'kick' ? ' danger' : ''}" data-pgdo="${key}"><span class="atxt"><b>${label}</b><small>${what}</small></span><span class="arr">›</span></button>`).join('')}`,
      'Закрыть', () => {}, {info: true});
    $('#sheet').querySelectorAll('[data-pgdo]').forEach(b => b.onclick = () => {
      const action = b.dataset.pgdo, name = `pv-purge:${PURGE.cid}:${v.session.id}:${uid}:${action}`;
      const box = $('#sheet'); box.hidden = true; box.innerHTML = '';
      const send = async () => {
        const res = await purgePost('decision', {session_id: v.session.id, user_id: uid, action, action_id: purgeKey(name)});
        if (res && res.ok) { purgeForget(name); if (res.replayed) toast('Другой админ уже решил. Показано его решение.'); }
      };
      if (action === 'forgive') send(); else undoLater(`${b.querySelector('b').textContent} · ${purgeName(t)}`, send);   // санкция — с 10 секундами на отмену
    });
  }
  const card = $('#sheet').querySelector('[data-pgcard]');
  if (card) card.onclick = () => { const box = $('#sheet'); box.hidden = true; box.innerHTML = ''; clearTimeout(PURGE.timer); playerView(PURGE.main, uid, true, {type: 'chat', id: PURGE.cid}); };
}

function purgeReconcile(uid) {
  const v = PURGE.view;
  sheet('Проверка решения', `<div class="sub">Сначала посмотрите в Telegram, что с участником: в чате ли он, есть ли бан или ограничение. Эта проверка ничего не отправляет повторно.</div>
    <div class="field"><label for="pgapplied">Что вы увидели</label><select id="pgapplied"><option value="">Выберите</option><option value="yes">Наказание применилось</option><option value="no">Наказания точно нет</option></select></div>
    <div class="field"><label for="pgreason">Что именно проверили (12–300 знаков)</label><textarea id="pgreason" minlength="12" maxlength="300"></textarea></div>`,
  'Записать', async () => {
    const applied = $('#pgapplied').value, reason = $('#pgreason').value.trim();
    if (!applied || reason.length < 12) throw new Error('Выберите, что увидели, и опишите проверку (от 12 знаков).');
    await purgePost('reconcile', {session_id: v.session.id, user_id: uid, applied: applied === 'yes', reason});
  });
}
