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
let _pgWeb = { cid: 0, page: 0, mode: 'pending', seq: 0, state: null, busy: false };
async function loadPurgeEntry() {
  const root = el('pg-more'); if (!root || el('more-purge-entry')) return;
  try {
    const d = await api('/purge-v1/chats');
    if (!d.items?.length || el('more-purge-entry')) return;
    const b = document.createElement('button'); b.type = 'button'; b.id = 'more-purge-entry'; b.className = 'v3-row';
    b.textContent = 'Чистка чатов · решения и досье'; b.onclick = () => openPurgeHub(); root.append(b);
  } catch (_) { /* ordinary players have no moderation entry */ }
}
async function openPurgeHub(cid = 0) {
  OM('Чистка чатов', '<div id="web-purge-host" role="status">Загружаем ваши чаты…</div>', [{l:'Закрыть',f:'CM()'}]);
  const host = el('web-purge-host'), seq = ++_pgWeb.seq;
  try {
    const d = await api('/purge-v1/chats'); if (!host?.isConnected || seq !== _pgWeb.seq) return;
    _pgWeb.chats = d.items || []; _pgWeb.cid = _pgWeb.chats.some(c => c.id === Number(cid)) ? Number(cid) : (_pgWeb.chats[0]?.id || 0);
    _pgWeb.page = 0; _pgWeb.mode = 'pending';
    if (!_pgWeb.cid) { host.innerHTML = '<p class="v3-empty">Нет чатов с правом проводить чистку. Права определяются вашим текущим рангом в каждом чате.</p>'; return; }
    await purgeWebLoad();
  } catch (e) { if (host?.isConnected) host.innerHTML = `<p class="v3-err" role="alert">${esc(String(e))}</p><button class="v3-link" onclick="openPurgeHub()">Повторить</button>`; }
}
function purgeWebPick(cid) { if (_pgWeb.busy) return; _pgWeb.cid = Number(cid); _pgWeb.page = 0; purgeWebLoad(); }
function purgeWebFilter(mode) { if (_pgWeb.busy) return; _pgWeb.mode = mode; _pgWeb.page = 0; purgeWebLoad(); }
async function purgeWebLoad(page = _pgWeb.page) {
  const host = el('web-purge-host'), cid = _pgWeb.cid, mode = _pgWeb.mode, seq = ++_pgWeb.seq;
  if (!host) return;
  try {
    const d = await api(`/purge-v1/chats/${cid}?page=${page}&mode=${mode}`);
    if (seq !== _pgWeb.seq || !host.isConnected) return;
    if (d.active && !d.items.length && page > 0) return purgeWebLoad(page - 1);
    _pgWeb.state = d; _pgWeb.page = page;
    const labels = {forgive:'Оставлен',skip:'Пропущен',warn:'Варн',mute:'Мут на час',kick:'Кик',ban:'Бан'};
    const choose = `<label for="pg-web-chat" class="tr-note">Чат</label><select id="pg-web-chat" class="v3-field" onchange="purgeWebPick(this.value)">${(_pgWeb.chats || []).map(c => `<option value="${c.id}"${c.id === cid ? ' selected' : ''}>${esc(c.title)}</option>`).join('')}</select>`;
    if (!d.active) {
      const local = new Date(), day = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
      const end = new Date(local); end.setDate(end.getDate()-1); const start = new Date(end); start.setDate(start.getDate()-6);
      host.innerHTML = `${choose}<p class="tr-note">Чистка не идёт. При запуске чат перейдёт в режим чистки, текущая Мафия встанет на паузу. Решения принимаются отдельно по каждому человеку. Даты учитываются по часовому поясу бота.</p><label for="pg-web-norm">Норма сообщений</label><input id="pg-web-norm" class="v3-field" type="number" inputmode="numeric" min="1" max="100000" value="100"><label for="pg-web-from">Начало периода</label><input id="pg-web-from" class="v3-field" type="date" value="${day(start)}"><label for="pg-web-to">Конец периода включительно</label><input id="pg-web-to" class="v3-field" type="date" value="${day(end)}"><button class="v3-pill v3-pill--full" onclick="purgeWebStart(this)">Начать чистку</button>`;
      return;
    }
    const s = d.session, c = d.counts;
    const rows = d.items.map(t => {
      const waiting = ['sending','unknown'].includes(t.decision_state), name = t.member_tag || (t.username ? '@'+t.username : 'Участник '+t.user_id);
      return `<li class="tr-grp"><h3>${esc(name)}</h3><p>Сообщений за период: <b>${t.msg_count}</b> · индивидуальная норма: <b>${t.required_norm ?? s.norm}</b></p><p class="tr-note">Дней в чате: ${t.days_in_chat} · варнов на начало чистки: ${t.warns}. Норма учитывает дату входа и время в муте.</p>${t.verdict ? `<p class="tr-ok">Решение: ${labels[t.verdict] || esc(t.verdict)}</p>` : waiting ? `<p class="tr-err" role="status">${esc(t.decision_error || 'Операция отправлена. Не повторяйте санкцию до проверки результата.')}</p><button class="v3-link" onclick="purgeWebReconcile(${t.user_id})">Сверить результат вручную</button>` : `<div class="tr-chips">${['forgive','warn','mute','kick','ban'].map(a => `<button class="v3-pill v3-pill--sm${a==='ban'||a==='kick'?' v3-pill--ghost':''}" onclick="purgeWebDecide(${t.user_id},'${a}',this)">${a==='forgive'?'Оставить':labels[a]}</button>`).join('')}</div>${t.decision_error ? `<p class="tr-note">${esc(t.decision_error)}</p>` : ''}`}</li>`;
    }).join('');
    host.innerHTML = `${choose}<p class="v3-stat-line">${esc(s.date_from)} — ${esc(s.date_to)} · норма ${s.norm}</p><p role="status">Решено ${c.decided} из ${c.total}. Без решения: ${c.total-c.decided}.</p><div class="tr-chips" role="group" aria-label="Фильтр досье">${[['pending','Ждут решения'],['decided','Решённые'],['all','Все']].map(([key,title]) => `<button class="tr-chip" aria-pressed="${mode===key}" onclick="purgeWebFilter('${key}')">${title}</button>`).join('')}</div><button class="v3-link" onclick="purgeWebLoad()">Обновить с учётом решений в Telegram</button><ul class="tr-list">${rows || '<li class="v3-empty">В этом разделе досье нет.</li>'}</ul><div class="tr-chips">${page ? `<button class="v3-link" onclick="purgeWebLoad(${page-1})">Предыдущие</button>` : ''}${d.has_more ? `<button class="v3-link" onclick="purgeWebLoad(${page+1})">Следующие</button>` : ''}</div><button class="v3-pill v3-pill--full v3-pill--ghost" onclick="purgeWebFinish()">Завершить чистку</button><p class="tr-note">Участники без решения останутся без санкций. Отдельно закрытый чат после чистки останется закрытым.</p>`;
  } catch (e) { if (host.isConnected && seq === _pgWeb.seq) host.innerHTML = `<p class="v3-err" role="alert">${esc(String(e))}</p><button class="v3-link" onclick="purgeWebLoad()">Повторить загрузку</button>`; }
}
async function purgeWebPost(path, body, button) {
  if (_pgWeb.busy) return;
  const cid = _pgWeb.cid; _pgWeb.busy = true; if (button) button.disabled = true;
  try { return await api(`/purge-v1/chats/${cid}/${path}`, {method:'POST',body:JSON.stringify(body)}); }
  catch (e) { toast(String(e), false); }
  finally { _pgWeb.busy = false; if (el('web-purge-host') && _pgWeb.cid === cid) await purgeWebLoad(); }
}
async function purgeWebStart(button) {
  const body = {norm:Number(el('pg-web-norm').value),date_from:el('pg-web-from').value,date_to:el('pg-web-to').value}, cid = _pgWeb.cid;
  if (!Number.isInteger(body.norm) || body.norm<1 || body.norm>100000 || !body.date_from || !body.date_to || body.date_from>body.date_to) { toast('Проверьте норму и период.',false); return; }
  const title = _pgWeb.chats.find(c=>c.id===cid)?.title || 'Чат';
  if (!await v3Confirm({title:'Начать чистку?',name:title,sub:'Чат перейдёт в режим чистки. Санкции выбираются отдельно.',rows:[['Период',body.date_from+' — '+body.date_to],['Норма',String(body.norm)]],cta:'Начать чистку'}) || cid!==_pgWeb.cid || !el('web-purge-host')) return;
  const key = `pv-purge-start:${cid}:${body.norm}:${body.date_from}:${body.date_to}`;
  let id; try { id = localStorage.getItem(key); } catch (_) {}
  id ||= crypto.randomUUID(); try { localStorage.setItem(key,id); } catch (_) {}
  const result = await purgeWebPost('start',{...body,action_id:id},button);
  if (result?.ok) { try { localStorage.removeItem(key); } catch (_) {} toast(result.message); }
}
async function purgeWebDecide(uid, action, button) {
  const s = _pgWeb.state?.session, target = _pgWeb.state?.items.find(t=>t.user_id===uid), cid = _pgWeb.cid;
  if (!s || !target || _pgWeb.busy) return;
  const labels={forgive:'Оставить участника',warn:'Выдать бессрочный варн',mute:'Выдать мут на час',kick:'Исключить из чата',ban:'Забанить бессрочно'};
  if (!await v3Confirm({title:labels[action],name:target.member_tag||target.username||'Участник '+uid,sub:_pgWeb.chats.find(c=>c.id===cid)?.title,rows:[['Сообщений',String(target.msg_count)],['Норма',String(target.required_norm??s.norm)]],cta:labels[action]})) return;
  if (cid!==_pgWeb.cid || _pgWeb.state?.session?.id!==s.id || !el('web-purge-host')) return;
  const key = `pv-purge:${cid}:${s.id}:${uid}:${action}`; let id;
  try { id=localStorage.getItem(key); } catch (_) {}
  id ||= crypto.randomUUID(); try { localStorage.setItem(key,id); } catch (_) {}
  const result = await purgeWebPost('decision',{session_id:s.id,user_id:uid,action,action_id:id},button);
  if (result?.ok) { try { localStorage.removeItem(key); } catch (_) {} }
}
async function purgeWebFinish() {
  const s = _pgWeb.state?.session, cid = _pgWeb.cid; if (!s) return;
  if (await v3Confirm({title:'Завершить чистку?',name:_pgWeb.chats.find(c=>c.id===cid)?.title,sub:'Нерешённые досье останутся без санкций. Отдельная блокировка чата сохраняется.',cta:'Завершить'}) && cid===_pgWeb.cid && el('web-purge-host')) await purgeWebPost('finish',{session_id:s.id});
}
function purgeWebReconcile(uid) {
  const s = _pgWeb.state?.session, cid = _pgWeb.cid; if (!s) return;
  OM('Сверка исполнения', `<p>Сначала проверьте статус участника и журнал Telegram. Эта операция ничего не отправляет повторно.</p><label for="pg-reconcile-applied">Проверенный результат</label><select id="pg-reconcile-applied" class="v3-field"><option value="">Выберите результат проверки</option><option value="yes">Санкция применена</option><option value="no">Санкция точно не применена</option></select><label for="pg-reconcile-reason">Что вы проверили (12–300 символов)</label><textarea id="pg-reconcile-reason" class="v3-field" minlength="12" maxlength="300"></textarea><p id="pg-reconcile-error" role="alert"></p>`, [{l:'Назад',f:`openPurgeHub(${cid})`},{l:'Записать сверку',f:`purgeWebReconcileGo(${cid},${s.id},${uid})`}]);
}
async function purgeWebReconcileGo(cid,sid,uid) {
  const value=el('pg-reconcile-applied')?.value, reason=el('pg-reconcile-reason')?.value.trim();
  if (!value || !reason || reason.length<12) { el('pg-reconcile-error').textContent='Выберите проверенный результат и опишите проверку.'; return; }
  try { await api(`/purge-v1/chats/${cid}/reconcile`,{method:'POST',body:JSON.stringify({session_id:sid,user_id:uid,applied:value==='yes',reason})}); await openPurgeHub(cid); }
  catch(e) { if(el('pg-reconcile-error')) el('pg-reconcile-error').textContent=String(e); }
}
