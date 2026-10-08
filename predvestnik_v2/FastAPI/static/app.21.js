// ── Публичный профиль (карточка игрока) ──────────────────────────────────────────
// Открывается из топа и из любого места, где виден чужой ник. Внешний вид и скин показываются, только если
// у владельца есть VIP; без VIP видно, что надето, но не как это выглядит (core/appearance_v3.py).
let _ppSeq = 0;
const _PP_SLOTS = { name_glow: 'Стиль ника', title: 'Титул', avatar_frame: 'Рамка аватара', avatar_halo: 'Ореол', profile_bg: 'Фон профиля', card_fx: 'Эффект карточки' };
function _ppMs(ms) { const total = Math.round(Number(ms) / 1000); return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`; }
function _ppFact(label, value, hint) { return `<div class="v3-fact"><span>${label}${hint ? `<small>${hint}</small>` : ''}</span><b>${value}</b></div>`; }
function v3PpBack() { const prev = _navStack.pop() || 'profile'; switchPage(prev, null, true); }

function openPublicCardV3(ref) {
  const id = String(ref || '');
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(id)) { toast('Ссылка на профиль недействительна.', false); return; }
  const root = el('pg-public-profile'); if (!root) return;
  switchPage('public-profile');
  const mine = ++_ppSeq, back = '<button type="button" class="v3-link pp-back" onclick="v3PpBack()">‹ Назад</button>';
  root.innerHTML = `<div class="v3-scope skin-default">${back}<div class="sk" style="height:76px;border-radius:38px;margin-top:14px"></div><div class="sk" style="height:120px;border-radius:14px;margin-top:22px"></div></div>`;
  api(`/public-profile-v3/${encodeURIComponent(id)}`)
    .then(d => { if (mine === _ppSeq) root.innerHTML = renderPublicCardV3(d); })
    .catch(e => { if (mine === _ppSeq) root.innerHTML = `<div class="v3-scope skin-default">${back}<div class="v3-empty">${_profileEsc(e)} <button type="button" class="v3-link" onclick="openPublicCardV3('${id}')">Повторить</button></div></div>`; });
}
window.openPublicProfile = openPublicCardV3;   // старые ссылки (startapp, чаты) ведут на новую карточку

function _ppAppearanceBlock(d) {
  const look = d.appearance || {}, items = look.equipped || [];
  const rows = items.map(i => `<div class="v3-fact"><span><i class="v3-tier">${_profileEsc(i.tier || '')}</i>${_profileEsc(i.name)}</span><b>${_PP_SLOTS[i.slot] || ''}</b></div>`).join('');
  const skin = look.skin || {};
  const skinRow = skin.worn ? _ppFact('Скин приложения', `<i class="v3-tier">${_profileEsc(skin.tier || '')}</i>${_profileEsc(skin.name)}`) : '';
  const lock = !look.visible && (items.length || skin.worn)
    ? `<div class="v3-lock"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="11" width="12" height="9" rx="2"/><path d="M9 11V8a3 3 0 0 1 6 0v3"/></svg><span>${d.is_self ? 'Другие игроки не видят ваш образ и скин: для этого нужен VIP. Вы сами видите его как обычно.' : 'Образ и скин скрыты: другие игроки видят их только у владельцев VIP.'}</span></div>` : '';
  const body = rows || skinRow ? `${rows}${skinRow}${lock}` : '<div class="v3-empty">Базовый образ, ничего не надето.</div>';
  return `<section><div class="v3-sec"><span class="v3-eyebrow">Внешний вид</span></div>${body}</section>`;
}
function _ppGames(g) {
  const rh = g.rhythm || {}, ms = g.minesweeper || {}, mf = g.mafia || {}, best = ms.best_ms || {};
  const times = [['лёгк.', best.easy], ['обыч.', best.normal], ['слож.', best.hard]].filter(([, v]) => v != null).map(([k, v]) => `${k} ${_ppMs(v)}`).join(' · ');
  return `<section><div class="v3-sec"><span class="v3-eyebrow">Игры</span></div>
    ${_ppFact('Ритм', rh.best_verified_score != null ? fmt(rh.best_verified_score) : '—', `${fmt(rh.verified_runs || 0)} подтверждённых забегов`)}
    ${_ppFact('Сапёр', `${fmt(ms.wins || 0)} побед`, `${fmt(ms.played || 0)} партий${times ? ` · лучшее: ${times}` : ''}`)}
    ${_ppFact('Мафия', `${fmt(mf.wins || 0)} побед`, `${fmt(mf.played || 0)} партий`)}</section>`;
}
function renderPublicCardV3(d) {
  const look = d.appearance || {}, visible = !!look.visible, ap = visible ? apFromPublic(look.items) : {};
  const wanted = visible ? look.skin?.css_class : '';
  const skinClass = /^skin-[a-z0-9-]{1,80}$/.test(wanted || '') ? wanted : 'skin-default';
  const lv = d.level || {}, capped = !(lv.xp_to_next > 0), level = lv.level || 1;
  const rank = String(d.rank || '').replace(/^[\p{Extended_Pictographic}\s]+/u, '');
  const joined = d.stats?.joined_date ? ` · с нами с ${_profileDate(d.stats.joined_date)}` : '';
  const avatar = _v3Avatar({ avatar: d.avatar, display_name: d.name, is_vip: !!d.vip, vip: d.vip });
  const name = vipName(d.name, !!d.vip, d.vip?.badge || '✦', d.vip?.badge_position || 'left');
  const identity = `<section class="v3-id${d.vip ? ' is-vip' : ''}${ap.glow ? ' has-glow' : ''}" aria-label="Игрок">
      <div class="v3-ring">${apHalo(ap)}${_v3Ring(capped ? 100 : lv.xp_into / lv.xp_to_next * 100)}<div class="v3-ava">${avatar}</div>${apFrame(ap)}<span class="v3-lv" aria-label="Уровень ${level}">${level}</span></div>
      <div style="min-width:0"><div class="v3-name">${apName(ap, _profileEsc(name))}</div>
      <div class="pp-title-row">${apTitle(ap)}</div>
      <div class="v3-sub">${_profileEsc(rank || 'Игрок')}${_profileEsc(joined)}</div>
      ${_v3VipSeal(d.vip)}
      <div class="v3-sub" style="margin-top:2px">${capped ? 'Максимальный уровень' : `${fmt(Math.max(0, lv.xp_to_next - lv.xp_into))} XP до ${level + 1} уровня`}</div></div></section>`;
  const s = d.stats || {}, families = d.paths?.families || [];
  const pet = s.active_pet ? _ppFact('Питомец', _profileEsc(s.active_pet.name), `${s.active_pet.level || 1} ур. · всего питомцев: ${fmt(s.pets_total || 0)}`) : '';
  const path = families.length ? `<section><div class="v3-sec"><span class="v3-eyebrow">Путь</span></div><div class="v3-path-row">${families.map(f => {
    const max = Math.max(1, f.max_level || 40), got = Math.min(max, f.level || 0);
    return `<div class="v3-aspect" role="img" aria-label="${_profileEsc(f.title)}: уровень ${got} из ${max}"><span class="v3-aspect-ring">${_v3Ring(got / max * 100)}<b>${got}</b></span><span>${_profileEsc(f.title)}</span></div>`;
  }).join('')}</div></section>` : '';
  const selfNote = d.is_self ? '<p class="v3-sub" style="margin-top:6px">Так вас видят другие игроки.</p>' : '';
  return `<div class="v3-scope ${skinClass}"><button type="button" class="v3-link pp-back" onclick="v3PpBack()">‹ Назад</button>${selfNote}
    <div style="margin-top:14px">${apStage(ap, identity)}</div>
    <section class="v3-stats" aria-label="Показатели"><div><b>${fmt(s.streak || 0)}</b><span>дней подряд</span></div><div><b>${fmt(s.achievements || 0)}</b><span>достижений</span></div><div><b>${_v3Short(s.messages || 0)}</b><span>сообщений</span></div></section>
    ${path}${_ppGames(d.games || {})}${pet ? `<section><div class="v3-sec"><span class="v3-eyebrow">Питомцы</span></div>${pet}</section>` : ''}${_ppAppearanceBlock(d)}</div>`;
}
