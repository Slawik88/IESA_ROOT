// ── Shell V3 · экран «Топ»: то же, что «бот топ» в чате, но на сайте ─────────────
const _V3_TOP_SCOPES = [{ id: 'global', label: 'Все игроки' }, { id: 'chats', label: 'Чаты' }, { id: 'local', label: 'Мой чат' }];
const _V3_TOP_PERIODS = [{ id: 'day', label: 'Сегодня' }, { id: 'week', label: 'Неделя' }, { id: 'month', label: 'Месяц' }, { id: 'all_time', label: 'Всё время' }];
let _v3Full = { scope: 'global', period: 'week', chat: null, page: 0, data: null, failed: false, loading: false }, _v3FullSeq = 0;

function openTopV3(scope, period) {
  if (scope) _v3Full.scope = scope;
  if (period) _v3Full.period = period;
  _v3Full.page = 0; _v3Full.data = null; _v3Full.failed = false;
  switchPage('top'); renderTopV3(); loadTopV3();
}
function loadTopV3() {
  const mine = ++_v3FullSeq, f = _v3Full;
  if (f.scope === 'local' && f.chat == null) { const first = _profileData?.chats?.[0]?.chat_tg_id; if (first) f.chat = Number(first); }
  const query = new URLSearchParams({ scope: f.scope, period: f.period, page: String(f.page) });
  if (f.scope === 'local' && f.chat != null) query.set('chat_id', String(f.chat));
  f.failed = false; f.loading = true; renderTopV3();   // прежний список остаётся на экране, пока идёт запрос: серого блока на долю секунды больше нет
  return api(`/leaderboards/messages/full?${query}`).then(d => {
    if (mine !== _v3FullSeq) return;
    f.data = d; f.failed = false; f.loading = false; if (f.scope === 'local' && f.chat == null && d.chats?.length) f.chat = d.chats[0].chat_id;
    renderTopV3();
  }).catch(e => { if (mine !== _v3FullSeq) return; f.failed = String(e || 'Ошибка'); f.loading = false; renderTopV3(); });
}
function v3FullSet(key, value) {
  const f = _v3Full; if (f[key] === value) return;
  f[key] = key === 'chat' ? Number(value) : value; if (key !== 'page') f.page = 0;
  _haptic('select'); loadTopV3();
}
function _v3FullRow(r, scope) {
  if (scope === 'chats') return `<li><div class="v3-rowbtn"><i>${r.place}</i><span>${_profileEsc(r.name)}<small>${fmt(r.users)} уч.</small></span><b>${fmt(r.count)}</b></div></li>`;
  return `<li class="${r.is_me ? 'is-me' : ''}">${_v3RowButton(r, r.count)}</li>`;
}
function renderTopV3() {
  const host = el('pg-top'); if (!host) return;
  const f = _v3Full, d = f.data, hasChat = !!(d?.chats?.length || _profileData?.chats?.length);
  const scopes = _V3_TOP_SCOPES.filter(s => s.id !== 'local' || hasChat);
  const seg = (items, current, key) => items.map(i => `<button type="button" role="tab" class="v3-tab${i.id === current ? ' on' : ''}" aria-selected="${i.id === current}" onclick="v3FullSet('${key}','${i.id}')">${i.label}</button>`).join('');
  const chatPick = f.scope === 'local' && d?.chats?.length > 1
    ? `<label class="sr-only" for="v3-top-chat">Чат</label><select id="v3-top-chat" class="v3-select" onchange="v3FullSet('chat',this.value)">${d.chats.map(c => `<option value="${c.chat_id}"${c.chat_id === f.chat ? ' selected' : ''}>${_profileEsc(c.title)}</option>`).join('')}</select>` : '';
  let body;
  if (f.failed) body = `<div class="v3-empty">${_profileEsc(f.failed)} <button type="button" class="v3-link" onclick="loadTopV3()">Повторить</button></div>`;
  else if (!d) body = '<div class="sk" style="height:340px;border-radius:14px"></div>';
  else if (!d.items.length) body = '<div class="v3-empty">Пока тихо. Напишите в чате, и вы первым окажетесь в списке.</div>';
  else {
    const me = d.personal ? `<div class="v3-top-me">Вы: #${fmt(d.personal.place)} из ${fmt(d.personal.total)} · ${fmt(d.personal.count)} сообщ.${d.personal.delta != null ? ` · <span class="${d.personal.delta >= 0 ? 'v3-up' : ''}">${d.personal.delta >= 0 ? '+' : ''}${fmt(d.personal.delta)} к прошлому периоду</span>` : ''}</div>`
      : (f.scope === 'chats' ? '' : '<div class="v3-top-me">У вас пока нет сообщений за выбранный период.</div>');
    const pager = d.pages > 1 ? `<div class="v3-pager"><button type="button" class="v3-link" ${d.page <= 0 ? 'disabled' : ''} onclick="v3FullSet('page',${d.page - 1})" aria-label="Предыдущая страница">‹</button><span>${d.page + 1} / ${d.pages}</span><button type="button" class="v3-link" ${d.page + 1 >= d.pages ? 'disabled' : ''} onclick="v3FullSet('page',${d.page + 1})" aria-label="Следующая страница">›</button></div>` : '';
    body = `${me}<div class="v3-ranking-labels"><span>Место · ${f.scope === 'chats' ? 'чат' : 'игрок'}</span><span>Сообщения</span></div><ol class="v3-top-list v3-top-list--full">${d.items.map(r => _v3FullRow(r, f.scope)).join('')}</ol>${pager}`;
  }
  host.innerHTML = `<div class="eyebrow-row"><button type="button" class="v3-link" onclick="switchPage('profile')" aria-label="Назад в профиль">‹ Профиль</button></div>
    <header class="v3-screen-head"><span class="v3-eyebrow">Рейтинг сообщества</span><h1 class="v3-title">Топ</h1><p class="v3-sub">Кто задаёт темп ${f.period === 'all_time' ? 'за всё время' : f.period === 'day' ? 'сегодня' : f.period === 'month' ? 'в этом месяце' : 'на этой неделе'}.</p></header>
    <div class="v3-tabs v3-tabs--wide" role="tablist" aria-label="Область рейтинга">${seg(scopes, f.scope, 'scope')}</div>
    <div class="v3-tabs v3-tabs--wide" role="tablist" aria-label="Период">${seg(_V3_TOP_PERIODS, f.period, 'period')}</div>
    ${chatPick}<div class="v3-top-body${f.loading && d ? ' is-loading' : ''}" aria-live="polite" aria-busy="${!!f.loading}">${body}</div>`;
  v3EnterSync(host);
}
