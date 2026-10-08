// ── Shell V3 · компактные лидерборды: сообщения (неделя, всё время) и Ритм ──────
const _V3_TOPS = [
  { id: 'week', label: 'Неделя', url: '/leaderboards/messages?period=week', unit: 'сообщ.' },
  { id: 'all_time', label: 'Всё время', url: '/leaderboards/messages?period=all_time', unit: 'сообщ.' },
  { id: 'rhythm', label: 'Ритм', url: '/rhythm-v2/leaderboard/normal', unit: 'очк.', flag: 'game_rhythm_v2' }
];
let _v3TopTab = 'week', _v3TopCache = {}, _v3TopSeq = 0;
function _v3TopShell() {
  return `<section class="v3-top" id="v3-top" aria-label="Лидерборды"><div class="v3-sec"><span class="v3-eyebrow">Топ-5</span></div><div class="v3-top-body"><div class="sk" style="height:170px;border-radius:14px"></div></div></section>`;
}
// Ответы двух API приводятся к одному виду: {top:[{place,name,value,is_vip,is_me}], personal:{place,value}|null}
function _v3TopNormalize(id, d) {
  if (id === 'rhythm') {
    return { top: (d.top || []).slice(0, 5).map(r => ({ place: r.place, name: r.player?.display_name || 'Игрок', ref: r.player?.profile_ref, value: r.best_score, is_vip: false, is_me: false, look: null })),
      personal: d.personal ? { place: d.personal.place, value: d.personal.best_score } : null };
  }
  return { top: (d.top || []).map(r => ({ place: r.place, name: r.name, ref: r.ref, value: r.count, is_vip: r.is_vip, is_me: r.is_me, look: r.look, mark: r.mark })),
    personal: d.personal ? { place: d.personal.place, value: d.personal.count } : null };
}
function _v3TopTabs() {
  const tabs = _V3_TOPS.filter(t => !t.flag || _sysFlags[t.flag] === true);
  if (!tabs.some(t => t.id === _v3TopTab)) _v3TopTab = tabs[0].id;
  return tabs;
}
function renderV3Top(state) {
  const host = el('v3-top'); if (!host) return;
  const tabs = _v3TopTabs(), tab = tabs.find(t => t.id === _v3TopTab);
  const head = `<div class="v3-sec"><span class="v3-eyebrow">Топ-5</span><div class="v3-tabs" role="tablist">${tabs.map(t =>
    `<button type="button" role="tab" class="v3-tab${t.id === _v3TopTab ? ' on' : ''}" aria-selected="${t.id === _v3TopTab}" onclick="v3TopSelect('${t.id}')">${t.label}</button>`).join('')}</div></div>`;
  const data = _v3TopCache[_v3TopTab];
  let body;
  if (state === 'error') body = `<div class="v3-empty">Топ не загрузился. <button type="button" class="v3-link" onclick="loadV3Top()">Повторить</button></div>`;
  else if (!data) body = '<div class="sk" style="height:170px;border-radius:14px"></div>';
  else if (!data.top.length) body = '<div class="v3-empty">Пока никого в рейтинге. Станьте первым.</div>';
  else {
    const inTop = data.top.some(r => r.is_me);
    body = `<ol class="v3-top-list">${data.top.map(r => `<li class="${r.is_me ? 'is-me' : ''}">${_v3RowButton(r, r.value)}</li>`).join('')}</ol>
      <div class="v3-top-foot"><span class="v3-top-me">${data.personal && !inTop ? `Вы: #${fmt(data.personal.place)} · ${fmt(data.personal.value)} ${tab.unit}` : ''}</span>${tab.id !== 'rhythm' ? `<button type="button" class="v3-link" onclick="openTopV3('global','${tab.id}')">Весь топ ›</button>` : ''}</div>`;
  }
  host.innerHTML = `${head}<div class="v3-top-body">${body}</div>`;
}
function loadV3Top() {
  const tabs = _v3TopTabs(), tab = tabs.find(t => t.id === _v3TopTab), mine = ++_v3TopSeq;
  renderV3Top();
  return api(tab.url).then(d => { _v3TopCache[tab.id] = _v3TopNormalize(tab.id, d); })
    .then(() => { if (mine === _v3TopSeq) renderV3Top(); })
    .catch(() => { if (mine === _v3TopSeq) renderV3Top('error'); });
}
function v3TopSelect(id) {
  if (id === _v3TopTab) return;
  _v3TopTab = id;
  if (_v3TopCache[id]) { renderV3Top(); return; }
  loadV3Top();
}

// Топ ниже первого экрана: запрос уходит, только когда блок почти попал в зону видимости
let _v3TopObserver = null;
function v3LazyTop() {
  const host = el('v3-top'); if (!host) return;
  _v3TopObserver?.disconnect();
  if (!('IntersectionObserver' in window)) { loadV3Top(); return; }
  _v3TopObserver = new IntersectionObserver((entries, observer) => {
    if (entries.some(entry => entry.isIntersecting)) { observer.disconnect(); loadV3Top(); }
  }, { rootMargin: '240px 0px' });
  _v3TopObserver.observe(host);
}

// Строка рейтинга: нажатие открывает публичную карточку игрока (ник со стилем виден только у VIP)
function _v3RowButton(row, value) {
  const open = row.ref && /^[A-Za-z0-9_-]{16,64}$/.test(row.ref) ? ` onclick="openPublicProfile('${row.ref}')"` : ' disabled';
  return `<button type="button" class="v3-rowbtn"${open} aria-label="Профиль игрока ${_profileEsc(row.name)}"><i>${row.place}</i><span>${apWho(row)}</span><b>${fmt(value)}</b></button>`;
}
