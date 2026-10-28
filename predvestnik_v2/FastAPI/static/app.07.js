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

// Shared web/Telegram purge. Decisions are server-owned; response loss always refetches the session.
let _pgWeb = { cid: 0, page: 0, mode: 'pending', seq: 0, state: null, busy: false, timer: null, signature: '', loading: false, denied:false, drafts:{}, completed:{} };
function purgeWebVisible(host = el('web-purge-host')) { return !!(host?.isConnected && el('modal')?.open); }
function purgeWebRememberDraft() {
  if (!_pgWeb.renderedCid || !el('pg-web-norm')) return;
  _pgWeb.drafts[_pgWeb.renderedCid] = {norm:el('pg-web-norm').value,from:el('pg-web-from').value,to:el('pg-web-to').value};
}
el('modal')?.addEventListener('close', () => {
  purgeWebRememberDraft(); clearTimeout(_pgWeb.timer); ++_pgWeb.seq; _pgWeb.loading = false;
});
function purgeWebSchedule() {
  clearTimeout(_pgWeb.timer);
  if (!purgeWebVisible() || _pgWeb.denied) return;
  _pgWeb.timer = setTimeout(() => {
    if (!purgeWebVisible()) return;
    if (document.hidden || _pgWeb.busy || el('cf-sheet')) { purgeWebSchedule(); return; }
    return purgeWebLoad(_pgWeb.page, true);
  }, 2000);
}
document.addEventListener('visibilitychange', () => { if (!document.hidden && purgeWebVisible() && !_pgWeb.busy) purgeWebLoad(_pgWeb.page, true); });
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
async function openPurgeHub(cid = 0, restore = null) {
  purgeWebRememberDraft();
  clearTimeout(_pgWeb.timer); _pgWeb.signature = ''; _pgWeb.state = null; _pgWeb.denied = false;
  OM('Чистка чатов', '<div id="web-purge-host" class="purge-web"><p role="status">Загружаем ваши чаты…</p></div>', [{l:'Закрыть',f:'CM()'}]);
  const host = el('web-purge-host'), seq = ++_pgWeb.seq;
  try {
    const d = await purgeWebApi('/purge-v1/chats');
    while (d.next_offset !== null && d.next_offset !== undefined) { const next = await purgeWebApi(`/purge-v1/chats?offset=${d.next_offset}`); d.items.push(...next.items); d.next_offset = next.next_offset; }
    if (!purgeWebVisible(host) || seq !== _pgWeb.seq) return;
    _pgWeb.chats = d.items || []; _pgWeb.cid = _pgWeb.chats.some(c => c.id === Number(cid)) ? Number(cid) : (_pgWeb.chats[0]?.id || 0);
    _pgWeb.page = restore?.page || 0; _pgWeb.mode = restore?.mode || 'pending';
    if (!_pgWeb.cid) { host.innerHTML = '<p class="v3-empty">Нет чатов с правом проводить чистку. Права определяются вашим текущим рангом в каждом чате.</p>'; return; }
    await purgeWebLoad();
    if (restore && el('mb')) el('mb').scrollTop = restore.scroll || 0;
  } catch (e) { if (host?.isConnected) host.innerHTML = `<p class="v3-err" role="alert">${esc(String(e))}</p><button class="v3-link" onclick="openPurgeHub()">Повторить</button>`; }
}
function purgeWebPick(cid) { if (_pgWeb.busy) return; purgeWebRememberDraft(); _pgWeb.cid = Number(cid); _pgWeb.page = 0; _pgWeb.signature = ''; purgeWebLoad(); }
function purgeWebFilter(mode) { if (_pgWeb.busy) return; _pgWeb.mode = mode; _pgWeb.page = 0; _pgWeb.signature = ''; purgeWebLoad(); }
async function purgeWebLoad(page = _pgWeb.page, quiet = false) {
  if (_pgWeb.busy || (quiet && _pgWeb.loading)) { purgeWebSchedule(); return; }
  if (!purgeWebVisible()) return;
  purgeWebRememberDraft(); _pgWeb.loading = true; _pgWeb.denied = false;
  const host = el('web-purge-host'), cid = _pgWeb.cid, mode = _pgWeb.mode, seq = ++_pgWeb.seq;
  if (!host) return;
  try {
    const d = await purgeWebApi(`/purge-v1/chats/${cid}?page=${page}&mode=${mode}`);
    if (seq !== _pgWeb.seq || !purgeWebVisible(host)) return;
    page = d.page;
    _pgWeb.state = d; _pgWeb.page = page;
    const signature = JSON.stringify([cid, mode, d]);
    const sync = el('pg-web-sync');
    if (sync) { sync.textContent = 'Решения обновляются автоматически'; sync.className = 'tr-note'; }
    if (quiet && (signature === _pgWeb.signature || el('cf-sheet'))) return;
    _pgWeb.signature = signature;
    const focused = host.contains(document.activeElement) ? document.activeElement : null;
    const focusId = focused?.id, focusAction = focused?.getAttribute('onclick');
    const scroll = el('mb')?.scrollTop || 0;
    const anchor = quiet ? [...host.querySelectorAll('[data-purge-user]')].find(row => row.getBoundingClientRect().bottom > el('mb').getBoundingClientRect().top) : null;
    const anchorId = anchor?.dataset.purgeUser, anchorTop = anchor?.getBoundingClientRect().top;
    const labels = {forgive:'Оставлен',skip:'Пропущен',warn:'Варн',mute:'Мут на час',kick:'Кик',ban:'Бан'};
    const choose = `<p id="pg-web-sync" class="tr-note" role="status">Решения обновляются автоматически</p><label for="pg-web-chat" class="tr-note">Чат</label><select id="pg-web-chat" class="v3-field" onchange="purgeWebPick(this.value)">${(_pgWeb.chats || []).map(c => `<option value="${c.id}"${c.id === cid ? ' selected' : ''}>${esc(c.title)}</option>`).join('')}</select>`;
    if (!d.active) {
      const local = new Date(), day = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
      const end = new Date(local); end.setDate(end.getDate()-1); const start = new Date(end); start.setDate(start.getDate()-6);
      host.innerHTML = `${choose}<p class="tr-note">Чистка не идёт. При запуске чат перейдёт в режим чистки, текущая Мафия встанет на паузу. Решения принимаются отдельно по каждому человеку. Даты учитываются по часовому поясу бота.</p><label for="pg-web-norm">Норма сообщений</label><input id="pg-web-norm" class="v3-field" type="number" inputmode="numeric" min="1" max="100000" value="100"><label for="pg-web-from">Начало периода</label><input id="pg-web-from" class="v3-field" type="date" value="${d.defaults?.date_from || day(start)}" max="${d.defaults?.today || day(local)}"><label for="pg-web-to">Конец периода включительно</label><input id="pg-web-to" class="v3-field" type="date" value="${d.defaults?.date_to || day(end)}" max="${d.defaults?.today || day(local)}"><button class="v3-pill v3-pill--full" onclick="purgeWebStart(this)">Начать чистку</button>`;
      _pgWeb.renderedCid = cid;
      const draft = _pgWeb.drafts[cid];
      if (draft) { el('pg-web-norm').value = draft.norm; el('pg-web-from').value = draft.from; el('pg-web-to').value = draft.to; }
      const result = d.completed?.counts || _pgWeb.completed[cid];
      if (result) host.insertAdjacentHTML('afterbegin', `<section class="tr-grp"><h3>Чистка завершена</h3><p>Решено ${result.decided} из ${result.total}. Оставлено: ${result.skipped}. Варнов: ${result.warned}. Мутов: ${result.muted}. Киков: ${result.kicked}. Банов: ${result.banned}.</p><p class="tr-note">Без решения: ${result.total-result.decided}. Санкции им не назначены.</p></section>`);
      if (el('mb')) el('mb').scrollTop = quiet ? scroll : 0;
      return;
    }
    const s = d.session, c = d.counts;
    const rows = d.items.map(t => {
      const waiting = ['sending','unknown'].includes(t.decision_state), name = t.member_tag || (t.username ? '@'+t.username : 'Участник '+t.user_id);
      return `<li class="tr-grp" data-purge-user="${t.user_id}"><h3><a href="tg://user?id=${t.user_id}">${esc(name)}</a></h3><p>Сообщений за период: <b>${t.msg_count}</b> · индивидуальная норма: <b>${t.required_norm ?? s.norm}</b></p><p class="tr-note">Дней в чате: ${t.days_in_chat} · варнов на начало чистки: ${t.warns}. Норма учитывает дату входа и время в муте.</p>${t.verdict ? `<p class="tr-ok">Решение: ${labels[t.verdict] || esc(t.verdict)}${t.verdict_by ? ' · ' + esc(t.verdict_by_name || t.verdict_by_username || 'администратор ' + t.verdict_by) : ''}</p>` : waiting ? `<p class="tr-err" role="status">${esc(t.decision_error || 'Операция отправлена. Не повторяйте санкцию до проверки результата.')}</p>${t.reconcile_ready ? `<button class="v3-link" onclick="purgeWebReconcile(${t.user_id})">Сверить результат вручную</button>` : '<p class="tr-note">Решение ещё выполняется. Если ответа не будет, сверка станет доступна через две минуты.</p>'}` : `<div class="tr-chips">${['forgive','warn','mute','kick','ban'].map(a => `<button class="v3-pill v3-pill--sm${a==='ban'||a==='kick'?' v3-pill--ghost':''}" onclick="purgeWebDecide(${t.user_id},'${a}',this)">${a==='forgive'?'Оставить':labels[a]}</button>`).join('')}</div>${t.decision_error ? `<p class="tr-note">${esc(t.decision_error)}</p>` : ''}`}</li>`;
    }).join('');
    host.innerHTML = `${choose}<p class="v3-stat-line">${esc(s.date_from)} — ${esc(s.date_to)} · норма ${s.norm}</p><p role="status">Решено ${c.decided} из ${c.total}. Без решения: ${c.total-c.decided}.</p><div class="tr-chips" role="group" aria-label="Фильтр досье">${[['pending','Ждут решения'],['decided','Решённые'],['all','Все']].map(([key,title]) => `<button class="tr-chip" aria-pressed="${mode===key}" onclick="purgeWebFilter('${key}')">${title}</button>`).join('')}</div><button class="v3-link" onclick="purgeWebLoad()">Обновить сейчас</button><ul class="tr-list">${rows || '<li class="v3-empty">В этом разделе досье нет.</li>'}</ul><div class="tr-chips">${page ? `<button class="v3-link" onclick="purgeWebLoad(${page-1})">Предыдущие</button>` : ''}${d.has_more ? `<button class="v3-link" onclick="purgeWebLoad(${page+1})">Следующие</button>` : ''}</div><button class="v3-pill v3-pill--full v3-pill--ghost" ${c.blocked ? 'disabled' : ''} onclick="purgeWebFinish()">Завершить чистку</button><p class="tr-note">Участники без решения останутся без санкций. Отдельно закрытый чат после чистки останется закрытым.</p>`;
    if (quiet) {
      if (el('mb')) {
        el('mb').scrollTop = scroll;
        const row = anchorId ? host.querySelector(`[data-purge-user="${anchorId}"]`) : null;
        if (row) el('mb').scrollTop += row.getBoundingClientRect().top - anchorTop;
      }
      if (focusId) el(focusId)?.focus({preventScroll:true});
      else if (focusAction) [...host.querySelectorAll('button')].find(b => b.getAttribute('onclick') === focusAction)?.focus({preventScroll:true});
    }
  } catch (e) {
    if (host.isConnected && seq === _pgWeb.seq) {
      const sync = el('pg-web-sync');
      if (e?.status===403 || e?.status===401) { _pgWeb.denied = true; _pgWeb.state = null; host.innerHTML = `<p class="v3-err" role="alert">${esc(e.message)}</p><button class="v3-link" onclick="openPurgeHub()">Проверить доступ снова</button>`; }
      else if (sync) { sync.textContent = `${e.message || 'Нет связи.'} Показаны последние данные; попробуем ещё раз.`; sync.className = 'tr-err'; }
      else host.innerHTML = `<p class="v3-err" role="alert">${esc(String(e))}</p><button class="v3-link" onclick="purgeWebLoad()">Повторить загрузку</button>`;
    }
  } finally {
    if (seq === _pgWeb.seq) { _pgWeb.loading = false; if (purgeWebVisible(host)) purgeWebSchedule(); }
  }
}
async function purgeWebPost(path, body, button) {
  if (_pgWeb.busy) return;
  const cid = _pgWeb.cid, host = el('web-purge-host'); _pgWeb.busy = true; ++_pgWeb.seq; clearTimeout(_pgWeb.timer); if (button) button.disabled = true;
  host?.querySelectorAll('button,select').forEach(b => b.disabled = true);
  const sync = el('pg-web-sync'); if (sync) sync.textContent = 'Сохраняем решение…';
  try {
    const result = await purgeWebApi(`/purge-v1/chats/${cid}/${path}`, {method:'POST',body:JSON.stringify(body)});
    if (result.ok && path==='finish') _pgWeb.completed[cid] = result.counts;
    if (result.ok && path==='start') delete _pgWeb.completed[cid];
    return result;
  }
  catch (e) { toast(e.message || String(e), false); }
  finally { _pgWeb.busy = false; _pgWeb.loading = false; _pgWeb.signature = ''; if (el('web-purge-host') === host && _pgWeb.cid === cid) await purgeWebLoad(_pgWeb.page,true); }
}
async function purgeWebStart(button) {
  if (_pgWeb.busy || !el('pg-web-norm') || !el('pg-web-from') || !el('pg-web-to')) return;
  const body = {norm:Number(el('pg-web-norm').value),date_from:el('pg-web-from').value,date_to:el('pg-web-to').value}, cid = _pgWeb.cid;
  if (!Number.isInteger(body.norm) || body.norm<1 || body.norm>100000 || !body.date_from || !body.date_to || body.date_from>body.date_to) { toast('Проверьте норму и период.',false); return; }
  const title = _pgWeb.chats.find(c=>c.id===cid)?.title || 'Чат';
  if (!await v3Confirm({title:'Начать чистку?',name:title,sub:'Чат перейдёт в режим чистки. Санкции выбираются отдельно.',rows:[['Период',body.date_from+' — '+body.date_to],['Норма',String(body.norm)]],cta:'Начать чистку'}) || cid!==_pgWeb.cid || !purgeWebVisible()) return;
  const key = `pv-purge-start:${cid}:${body.norm}:${body.date_from}:${body.date_to}`;
  let id; try { id = localStorage.getItem(key); } catch (_) {}
  id ||= typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `purge-${Date.now()}-${Math.random().toString(36).slice(2)}`; try { localStorage.setItem(key,id); } catch (_) {}
  const result = await purgeWebPost('start',{...body,action_id:id},button);
  if (result?.ok) { try { localStorage.removeItem(key); } catch (_) {} toast(result.message); }
}
async function purgeWebDecide(uid, action, button) {
  const s = _pgWeb.state?.session, target = _pgWeb.state?.items.find(t=>t.user_id===uid), cid = _pgWeb.cid;
  if (!s || !target || _pgWeb.busy) return;
  const labels={forgive:'Оставить участника',warn:'Выдать бессрочный варн',mute:'Выдать мут на час',kick:'Исключить из чата',ban:'Забанить бессрочно'};
  if (!await v3Confirm({title:labels[action],name:target.member_tag||target.username||'Участник '+uid,sub:_pgWeb.chats.find(c=>c.id===cid)?.title,rows:[['Сообщений',String(target.msg_count)],['Норма',String(target.required_norm??s.norm)]],cta:labels[action]})) return;
  if (cid!==_pgWeb.cid || _pgWeb.state?.session?.id!==s.id || !purgeWebVisible()) return;
  const key = `pv-purge:${cid}:${s.id}:${uid}:${action}`; let id;
  try { id=localStorage.getItem(key); } catch (_) {}
  id ||= typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `purge-${Date.now()}-${Math.random().toString(36).slice(2)}`; try { localStorage.setItem(key,id); } catch (_) {}
  const result = await purgeWebPost('decision',{session_id:s.id,user_id:uid,action,action_id:id},button);
  if (result?.ok) { try { localStorage.removeItem(key); } catch (_) {} if (result.replayed) toast('Другой администратор уже принял решение. Показан сохранённый результат.'); }
}
async function purgeWebFinish() {
  const s = _pgWeb.state?.session, cid = _pgWeb.cid; if (!s || _pgWeb.busy) return;
  if (await v3Confirm({title:'Завершить чистку?',name:_pgWeb.chats.find(c=>c.id===cid)?.title,sub:'Нерешённые досье останутся без санкций. Отдельная блокировка чата сохраняется.',cta:'Завершить'}) && cid===_pgWeb.cid && purgeWebVisible() && _pgWeb.state?.session?.id===s.id) await purgeWebPost('finish',{session_id:s.id});
}
function purgeWebReconcile(uid) {
  const s = _pgWeb.state?.session, cid = _pgWeb.cid; if (!s || _pgWeb.busy) return;
  _pgWeb.returnTo = {page:_pgWeb.page,mode:_pgWeb.mode,scroll:el('mb')?.scrollTop || 0}; clearTimeout(_pgWeb.timer); ++_pgWeb.seq;
  OM('Сверка исполнения', `<p>Сначала проверьте статус участника и журнал Telegram. Эта операция ничего не отправляет повторно.</p><label for="pg-reconcile-applied">Проверенный результат</label><select id="pg-reconcile-applied" class="v3-field"><option value="">Выберите результат проверки</option><option value="yes">Санкция применена</option><option value="no">Санкция точно не применена</option></select><label for="pg-reconcile-reason">Что вы проверили (12–300 символов)</label><textarea id="pg-reconcile-reason" class="v3-field" minlength="12" maxlength="300"></textarea><p id="pg-reconcile-error" role="alert"></p>`, [{l:'Назад',f:`purgeWebBack(${cid})`},{l:'Записать сверку',f:`purgeWebReconcileGo(${cid},${s.id},${uid})`}]);
}
async function purgeWebReconcileGo(cid,sid,uid) {
  if (_pgWeb.busy) return;
  const value=el('pg-reconcile-applied')?.value, reason=el('pg-reconcile-reason')?.value.trim();
  if (!value || !reason || reason.length<12) { el('pg-reconcile-error').textContent='Выберите проверенный результат и опишите проверку.'; return; }
  const error = el('pg-reconcile-error'); _pgWeb.busy = true;
  el('mf')?.querySelectorAll('button').forEach(b => b.disabled = true); error.textContent = 'Проверяем и сохраняем результат…';
  try {
    await purgeWebApi(`/purge-v1/chats/${cid}/reconcile`,{method:'POST',body:JSON.stringify({session_id:sid,user_id:uid,applied:value==='yes',reason})});
    _pgWeb.busy = false;
    if (el('pg-reconcile-error')===error && el('modal')?.open) await purgeWebBack(cid);
  }
  catch(e) { if(el('pg-reconcile-error')===error) error.textContent=e.message || String(e); }
  finally { _pgWeb.busy = false; if(el('pg-reconcile-error')===error) el('mf')?.querySelectorAll('button').forEach(b => b.disabled = false); }
}
function purgeWebBack(cid) { return openPurgeHub(cid,_pgWeb.returnTo); }
