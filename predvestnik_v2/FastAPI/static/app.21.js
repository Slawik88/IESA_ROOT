// ── Публичный профиль (карточка игрока) ──────────────────────────────────────────
// Открывается из топа и из любого места, где виден чужой ник. Образ и палитра владельца показываются,
// только если у него активен VIP; без VIP видно название образа и тир, но не как он выглядит (core/appearance_v3.py).
// Композиция: сцена с героем, три главных числа, «Путь», игры, питомец, образ с кнопкой «Примерить».
let _ppSeq = 0;
function _ppMs(ms) { const total = Math.round(Number(ms) / 1000); return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`; }
function v3PpBack() { const prev = _navStack.pop() || 'profile'; switchPage(prev, null, true); }
const _PP_BACK = '<button type="button" class="v3-link pp-back" onclick="v3PpBack()">‹ Назад</button>';

function openPublicCardV3(ref) {
  const id = String(ref || '');
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(id)) { toast('Ссылка на профиль недействительна.', false); return; }
  const root = el('pg-public-profile'); if (!root) return;
  switchPage('public-profile');
  const mine = ++_ppSeq;
  root.innerHTML = `<div class="v3-scope pp-neutral">${_PP_BACK}<div class="sk" style="height:96px;width:96px;border-radius:50%;margin:34px auto 0"></div><div class="sk" style="height:24px;width:46%;border-radius:12px;margin:22px auto 0"></div><div class="sk" style="height:120px;border-radius:14px;margin-top:34px"></div></div>`;
  api(`/public-profile-v3/${encodeURIComponent(id)}`)
    .then(d => { if (mine === _ppSeq) root.innerHTML = renderPublicCardV3(d); })
    .catch(e => { if (mine === _ppSeq) root.innerHTML = `<div class="v3-scope pp-neutral">${_PP_BACK}<div class="v3-empty">${_profileEsc(e)} <button type="button" class="v3-link" onclick="openPublicCardV3('${id}')">Повторить</button></div></div>`; });
}
window.openPublicProfile = openPublicCardV3;   // старые ссылки (startapp, чаты) ведут на новую карточку

function _ppPresence(p, d) {
  if (d?.is_self && d.presence_level === 'nobody') return '<div class="pp-presence"><i aria-hidden="true"></i>Другие не видят, когда вы в сети <button type="button" class="v3-link pp-change" onclick="openSettingsModal()">Изменить</button></div>';
  if (!p || !p.label || p.state === 'hidden') return '';
  return `<div class="pp-presence${p.state === 'online' ? ' is-online' : ''}"><i aria-hidden="true"></i>${_profileEsc(p.label)}</div>`;
}
function _ppGames(g) {
  const rh = g.rhythm || {}, ms = g.minesweeper || {}, mf = g.mafia || {}, best = ms.best_ms || {};
  const pct = (wins, played) => (played > 0 ? Math.round(wins / played * 100) : null);
  const ring = (value, label, caption) => `<div class="pp-game"><span class="v3-aspect-ring">${_v3Ring(value ?? 0)}<b>${value == null ? '—' : `${value}%`}</b></span><span class="pp-gl">${label}</span><small>${caption}</small></div>`;
  const time = [['лёгк.', best.easy], ['обыч.', best.normal], ['слож.', best.hard]].filter(([, v]) => v != null).map(([k, v]) => `${k} ${_ppMs(v)}`)[0];
  return `<section><div class="v3-sec"><span class="v3-eyebrow">Игры</span></div><div class="pp-games">
    <div class="pp-game"><b class="pp-big">${rh.best_verified_score != null ? fmt(rh.best_verified_score) : '—'}</b><span class="pp-gl">Ритм</span><small>${fmt(rh.verified_runs || 0)} забегов</small></div>
    ${ring(pct(ms.wins || 0, ms.played || 0), 'Сапёр', `${fmt(ms.wins || 0)} из ${fmt(ms.played || 0)}${time ? ` · ${time}` : ''}`)}
    ${ring(pct(mf.wins || 0, mf.played || 0), 'Мафия', `${fmt(mf.wins || 0)} из ${fmt(mf.played || 0)}`)}</div></section>`;
}
function ppTry(id) { _lk.sel = id; openLooksModal(); }
function _ppLook(d, ap) {
  const a = d.appearance || {}, look = a.look || {};
  if (!a.worn) return '';
  const head = '<div class="v3-sec"><span class="v3-eyebrow">Образ</span></div>';
  if (a.visible && ap) {
    return `<section>${head}<div class="pp-look"><span class="lk-mini">${_lkMini({ ...look, ceiling: look.tier })}</span>
      <span><b>${_profileEsc(look.name)}</b><small><i class="v3-tier">${_profileEsc(look.tier)}</i>${look.tier === look.ceiling ? 'раскрыт полностью' : `растёт до ${_profileEsc(look.ceiling)}`}</small></span>
      <button type="button" class="v3-pill v3-pill--ghost" onclick="ppTry('${_profileEsc(look.id)}')">Примерить</button></div></section>`;
  }
  const lock = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="11" width="12" height="9" rx="2"/><path d="M9 11V8a3 3 0 0 1 6 0v3"/></svg>';
  const why = d.is_self ? 'Другие игроки видят ваш образ только пока у вас активен VIP. Вы сами видите его как обычно.' : 'Образ скрыт: другие игроки видят его только у владельцев VIP.';
  return `<section>${head}<div class="pp-look pp-look--hidden"><span><b>${_profileEsc(look.name || 'Образ')}</b><small><i class="v3-tier">${_profileEsc(look.tier || '')}</i></small></span></div><div class="v3-lock">${lock}<span>${why}</span></div></section>`;
}
function _ppCollection(d) {   // только числа и названия: что именно собрано, остальные не видят
  const c = d.appearance?.collection; if (!c || !c.owned) return '';
  const sets = (c.sets_done || []).map(x => `${_profileEsc(x.glyph)} ${_profileEsc(x.name)}`).join(' · '), extra = [c.maxed ? `на максимуме: ${c.maxed}` : '', sets].filter(Boolean).join(' · ');
  return `<section><div class="v3-sec"><span class="v3-eyebrow">Коллекция</span></div><div class="pp-coll"><span class="lk-pring" style="--p:${Math.round(100 * c.owned / c.total)}">${c.owned}/${c.total}</span>
    <span><b>${_profileEsc(c.rank)}</b><small>${_profileEsc(extra || `Образов: ${c.owned} из ${c.total}`)}</small></span></div></section>`;
}
function renderPublicCardV3(d) {
  const a = d.appearance || {}, ap = a.visible ? apFromLook(a.look) : null;
  const tokens = ap ? v3TokenStyle(a.look.tokens) : '';
  const lv = d.level || {}, capped = !(lv.xp_to_next > 0), level = lv.level || 1;
  const rank = String(d.rank || '').replace(/^[\p{Extended_Pictographic}\s]+/u, '');
  const joined = d.stats?.joined_date ? ` · с нами с ${_profileDate(d.stats.joined_date)}` : '';
  const avatar = _v3Avatar({ avatar: d.avatar, display_name: d.name, is_vip: !!d.vip, vip: d.vip });
  const name = vipName(d.name, !!d.vip, d.vip?.badge || '✦', d.vip?.badge_position || 'left');
  const hero = `<section class="pp-hero v3-id${d.vip ? ' is-vip' : ''}${ap ? ' has-look' : ''}" aria-label="Игрок">
      <div class="v3-ring pp-ring">${apHalo(ap)}${_v3Ring(capped ? 100 : lv.xp_into / lv.xp_to_next * 100)}<div class="v3-ava">${avatar}</div>${apFrame(ap)}<span class="v3-lv" aria-label="Уровень ${level}">${level}</span></div>
      <div class="v3-name pp-name">${apName(ap, _profileEsc(name))}</div>
      ${apTitle(ap) ? `<div class="pp-title-row">${apTitle(ap)}</div>` : ''}
      <div class="v3-sub">${_profileEsc(rank || 'Игрок')}${_profileEsc(joined)}</div>
      ${v3MarksHtml(d.marks)}
      ${_ppPresence(d.presence, d)}${_v3VipSeal(d.vip)}
      <div class="v3-sub pp-xp">${capped ? 'Максимальный уровень' : `${fmt(Math.max(0, lv.xp_to_next - lv.xp_into))} XP до ${level + 1} уровня`}</div></section>`;
  const s = d.stats || {}, families = d.paths?.families || [];
  const pet = s.active_pet ? `<section><div class="v3-sec"><span class="v3-eyebrow">Питомец</span></div><div class="pp-pet"><b>${_profileEsc(s.active_pet.name)}</b><small>${s.active_pet.level || 1} ур. · всего питомцев: ${fmt(s.pets_total || 0)}</small></div></section>` : '';
  const path = families.length ? `<section><div class="v3-sec"><span class="v3-eyebrow">Путь</span></div><div class="v3-path-row">${families.map(f => {
    const max = Math.max(1, f.max_level || 40), got = Math.min(max, f.level || 0);
    return `<div class="v3-aspect" role="img" aria-label="${_profileEsc(f.title)}: уровень ${got} из ${max}"><span class="v3-aspect-ring">${_v3Ring(got / max * 100)}<b>${got}</b></span><span>${_profileEsc(f.title)}</span></div>`;
  }).join('')}</div></section>` : '';
  return `<div class="v3-scope pp-scope${ap ? '' : ' pp-neutral'}" style="${tokens}">${_PP_BACK}${d.is_self ? '<p class="v3-sub pp-self">Так вас видят другие игроки.</p>' : ''}
    ${apStage(ap, hero)}
    <section class="v3-stats" aria-label="Показатели"><div><b>${fmt(s.streak || 0)}</b><span>дней подряд</span></div><div><b>${fmt(s.achievements || 0)}</b><span>достижений</span></div><div><b>${_v3Short(s.messages || 0)}</b><span>сообщений</span></div></section>
    ${path}${_ppGames(d.games || {})}${pet}${_ppLook(d, ap)}${_ppCollection(d)}</div>`;
}
