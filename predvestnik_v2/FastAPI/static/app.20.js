// ── Skins V3 · рендер образа: ник, титул, рамка, ореол, сцена ─────────────────────
// Образ приходит с сервера одним объектом: {tier, ceiling, pal:[a,b,c], kinds:{frame,halo,pt,name,bg}, sig, title}.
// Палитра и форма берутся из скина, богатство — из тира (D…SSS = 1…7). Фирменная деталь (sig) открывается,
// когда скин прокачан до своего потолка. Без VIP чужой образ приходит без pal/kinds, тогда ap = null и рисуется базовый вид.
const _AP_TIERS = ['D', 'C', 'B', 'A', 'S', 'SS', 'SSS'];
const _AP_WORD = /^[a-z_]{2,16}$/, _AP_HEX = /^#[0-9a-f]{6}$/i;
const _AP_POWER = [0, .4, .5, .6, .72, .85, .95, 1];
const _AP_DUST = [0, 5, 7, 9, 12, 16, 20, 26];
function _apTi(tier) { return _AP_TIERS.indexOf(tier) + 1; }
function apFromLook(look) {
  const ti = _apTi(look?.tier), kinds = look?.kinds, pal = look?.pal;
  if (!ti || !kinds || !Array.isArray(pal) || pal.length < 3 || !pal.every(c => _AP_HEX.test(c))) return null;
  const word = value => (_AP_WORD.test(value || '') ? value : '');
  return {
    look, ti, tier: look.tier, id: String(look.id || ''), title: String(look.title || ''),
    k: { frame: word(kinds.frame), halo: word(kinds.halo), pt: word(kinds.pt), name: word(kinds.name), bg: word(kinds.bg) },
    sig: look.sig && look.tier === look.ceiling && _AP_WORD.test(look.sig) ? look.sig : '',
    vars: `--ap-a:${pal[0]};--ap-b:${pal[1]};--ap-c:${pal[2]};--ap-i:${_AP_POWER[ti]}`,
  };
}
const _apSig = ap => (ap.sig ? ` ap-sig-${ap.sig}` : '');
function apName(ap, html, plain) {
  if (!ap) return html;
  const text = plain ?? String(html).replace(/<[^>]*>/g, '');
  return `<span class="ap-name ap-t${ap.ti} ap-nm-${ap.k.name}${_apSig(ap)}" style="${ap.vars}" data-t="${text}">${html}</span>`;
}
function apTitle(ap) {
  return ap && ap.title ? `<span class="ap-title ap-t${ap.ti}${_apSig(ap)}" style="${ap.vars}">${_profileEsc(ap.title)}</span>` : '';
}
function apHalo(ap) { return ap ? `<i class="ap-halo ap-t${ap.ti} ap-ha-${ap.k.halo}${_apSig(ap)}" style="${ap.vars}" aria-hidden="true"><b></b><b></b><b></b></i>` : ''; }
function apFrame(ap) {
  return ap ? `<i class="ap-frame ap-t${ap.ti} ap-fr-${ap.k.frame}${_apSig(ap)}" style="${ap.vars}" aria-hidden="true">${ap.sig && typeof apSigDecor === 'function' ? apSigDecor(ap.sig) : ''}</i>` : '';
}
// Частицы сцены: число растёт с тиром; положение детерминировано, чтобы кадр не прыгал при перерисовке
function _apDust(ap) {
  return Array.from({ length: _AP_DUST[ap.ti] || 0 }, (_, i) => {
    const r = n => { const x = Math.sin((i + 1) * 12.9898 + n * 78.233) * 43758.5453; return x - Math.floor(x); };
    return `<i style="--x:${(r(1) * 100).toFixed(1)}%;--y:${(r(2) * 80).toFixed(1)}%;--s:${(3 + r(3) * 4).toFixed(1)}px;--d:${(10 + r(4) * 9).toFixed(1)}s;--delay:-${(r(5) * 14).toFixed(1)}s;--dx:${((r(6) - .5) * 70).toFixed(0)}px;--r:${(r(7) * 360).toFixed(0)}deg"></i>`;
  }).join('');
}
// Сцена: фон и частицы за блоком личности. inner — сам блок. Без образа возвращается как есть.
function apStage(ap, inner) {
  if (!ap) return inner;
  const cls = `ap-t${ap.ti}${_apSig(ap)}`;
  return `<div class="ap-stage ${cls}" style="${ap.vars}"><div class="ap-bg ${cls} ap-bg-${ap.k.bg}" aria-hidden="true"><b></b><b></b></div><div class="ap-fx ${cls} ap-pt-${ap.k.pt}" aria-hidden="true">${_apDust(ap)}</div>${inner}</div>`;
}
// Имя и титул одной строки списка (топ): ник со стилем, титул-«таблетка», точка VIP
function apWho(row) {
  const ap = apFromLook(row.look);
  return `<span class="v3-who"><span>${apName(ap, _profileEsc(row.name))}${row.is_vip ? ' <em class="v3-vipdot" aria-label="VIP"></em>' : ''}</span>${apTitle(ap)}</span>`;
}
