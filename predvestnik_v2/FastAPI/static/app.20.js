// ── Appearance V3 · рендер внешнего вида: ник, титул, аватар, сцена ───────────────
// Данные приходят в трёх формах (свой профиль, публичная карточка, строка топа); все приводятся к одному виду:
// {glow, title:{text}, frame, halo, bg, fx}, где у слота есть lineup (коллекция) и tier (D…SS).
function _apTierIndex(tier) { return { D: 1, C: 2, B: 3, A: 4, S: 5, SS: 6 }[tier] || 0; }
function _apCls(slot) {
  const lineup = String(slot?.lineup || ''), tier = _apTierIndex(slot?.tier);
  return /^[a-z_]{2,20}$/.test(lineup) && tier ? `ap-l-${lineup} ap-t${tier}` : '';
}
function apFromOwner(c) {
  if (!c) return {};
  const pick = key => (c[key] && typeof c[key] === 'object' ? c[key] : null);
  return { glow: pick('name_glow'), frame: pick('avatar_frame'), halo: pick('avatar_halo'), bg: pick('profile_bg'), fx: pick('card_fx'),
    title: c.title ? { text: c.title, lineup: c.title_lineup, tier: c.title_tier } : null };
}
function apFromPublic(items) {
  if (!items) return {};
  const title = items.title ? { text: items.title.text || items.title.name, lineup: items.title.lineup, tier: items.title.tier } : null;
  return { glow: items.name_glow || null, frame: items.avatar_frame || null, halo: items.avatar_halo || null, bg: items.profile_bg || null, fx: items.card_fx || null, title };
}
function apFromStyle(style) {
  return { glow: style?.glow || null, title: style?.title ? { text: style.title.text, lineup: style.title.lineup, tier: style.title.tier } : null };
}
function apName(ap, html) { const cls = _apCls(ap?.glow); return cls ? `<span class="ap-name ${cls}">${html}</span>` : html; }
function apTitle(ap) {
  const cls = _apCls(ap?.title);
  return cls && ap.title.text ? `<span class="ap-title ${cls}">${_profileEsc(ap.title.text)}</span>` : '';
}
function apHalo(ap) { const cls = _apCls(ap?.halo); return cls ? `<i class="ap-halo ${cls}" aria-hidden="true"></i>` : ''; }
function apFrame(ap) { const cls = _apCls(ap?.frame); return cls ? `<i class="ap-frame ${cls}" aria-hidden="true"></i>` : ''; }
// Частицы сцены: число растёт с тиром предмета; положение детерминировано, чтобы кадр не прыгал
function _apParticles(slot) {
  const tier = _apTierIndex(slot?.tier), count = [0, 6, 8, 10, 14, 18, 24][tier] || 0;
  return Array.from({ length: count }, (_, i) => {
    const r = n => { const x = Math.sin((i + 1) * 12.9898 + n * 78.233) * 43758.5453; return x - Math.floor(x); };
    return `<i style="--x:${(r(1) * 100).toFixed(1)}%;--y:${(r(2) * 90).toFixed(1)}%;--s:${(2 + r(3) * 3).toFixed(1)}px;--d:${(9 + r(4) * 8).toFixed(1)}s;--delay:-${(r(5) * 12).toFixed(1)}s;--dx:${((r(6) - .5) * 60).toFixed(0)}px"></i>`;
  }).join('');
}
function apHasStage(ap) { return !!(_apCls(ap?.bg) || _apCls(ap?.fx)); }
function apStage(ap, inner) {
  const bg = _apCls(ap?.bg), fx = _apCls(ap?.fx);
  if (!bg && !fx) return inner;
  return `<div class="ap-stage">${bg ? `<div class="ap-bg ${bg}" aria-hidden="true"></div>` : ''}${fx ? `<div class="ap-fx ${fx}" aria-hidden="true">${_apParticles(ap.fx)}</div>` : ''}${inner}</div>`;
}
// Имя и титул одной строки списка (топ): ник со стилем, титул-«таблетка», точка VIP
function apWho(row) {
  const ap = apFromStyle(row.style);
  return `<span class="v3-who"><span>${apName(ap, _profileEsc(row.name))}${row.is_vip ? ' <em class="v3-vipdot" aria-label="VIP"></em>' : ''}</span>${apTitle(ap)}</span>`;
}
