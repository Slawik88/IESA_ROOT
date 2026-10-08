// ── Skins V3 · рендер образа: ник, титул, рамка, ореол, сцена ─────────────────────
// Образ приходит с сервера одним объектом: {tier, ceiling, pal:[a,b,c], kinds:{frame,halo,pt,name,bg}, sig, title}.
// Палитра и форма берутся из скина, богатство — из тира (D…SSS = 1…7). Потолок у всех один, SSS; редкость (rarity) задаёт только цену и ряд коллекции.
// Фирменная деталь (sig) открывается с тира sig_from: у образов редкости S и выше со своей редкости, у остальных на SSS. Без VIP чужой образ приходит без pal/kinds, тогда ap = null и рисуется базовый вид.
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
    sig: look.sig && ti >= _apTi(look.sig_from || look.ceiling) && _AP_WORD.test(look.sig) ? look.sig : '',
    vars: `--ap-a:${pal[0]};--ap-b:${pal[1]};--ap-c:${pal[2]};--ap-i:${_AP_POWER[ti]}`,
  };
}
const _apSig = ap => (ap.sig ? ` ap-sig-${ap.sig}` : '');
const _apSk = ap => (/^[a-z_]{2,24}$/.test(ap.id || '') ? ` data-sk="${ap.id}"` : '');   // id образа на каждом слое: личные образы дорисовывают себя по нему (skins-exclusive-v3.css)
function apName(ap, html, plain) {
  if (!ap) return html;
  const text = plain ?? String(html).replace(/<[^>]*>/g, '');
  return `<span class="ap-name ap-t${ap.ti} ap-nm-${ap.k.name}${_apSig(ap)}"${_apSk(ap)} style="${ap.vars}" data-t="${text}">${html}</span>`;
}
function apCrest(ap) {   // знак собранного сета: сервер присылает его только владельцу или тем, кто вправе видеть образ
  const c = ap?.look?.crest;
  return c && typeof c.glyph === 'string' ? `<span class="ap-crest" style="${ap.vars}" title="${_profileEsc(c.name || '')}" role="img" aria-label="${_profileEsc(c.name || 'Сет')}">${_profileEsc(c.glyph)}</span>` : '';
}
function apTitle(ap) {
  const title = ap && ap.title ? `<span class="ap-title ap-t${ap.ti}${_apSig(ap)}"${_apSk(ap)} style="${ap.vars}">${_profileEsc(ap.title)}</span>` : '';
  return ap ? apCrest(ap) + title : '';
}
function apHalo(ap) { return ap ? `<i class="ap-halo ap-t${ap.ti} ap-ha-${ap.k.halo}${_apSig(ap)}"${_apSk(ap)} style="${ap.vars}" aria-hidden="true"><b></b><b></b><b></b></i>` : ''; }
function apFrame(ap) {
  return ap ? `<i class="ap-frame ap-t${ap.ti} ap-fr-${ap.k.frame}${_apSig(ap)}"${_apSk(ap)} style="${ap.vars}" aria-hidden="true">${typeof apFrameOrn === 'function' ? apFrameOrn(ap) : ''}${ap.sig && typeof apSigDecor === 'function' ? apSigDecor(ap.sig) : ''}</i>` : '';
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
  return `<div class="ap-stage ${cls}"${_apSk(ap)} style="${ap.vars}"><div class="ap-bg ${cls} ap-bg-${ap.k.bg}" aria-hidden="true"><b></b><b></b></div><div class="ap-fx ${cls} ap-pt-${ap.k.pt}" aria-hidden="true">${_apDust(ap)}</div>${typeof apOrn === 'function' ? apOrn(ap) : ''}${inner}</div>`;
}
// Имя и титул одной строки списка (топ): ник со стилем, титул-«таблетка», точка VIP
function apWho(row) {
  const ap = apFromLook(row.look);
  return `<span class="v3-who"><span>${ap ? apName(ap, _profileEsc(row.name)) : `<span class="ap-plain">${_profileEsc(row.name)}</span>`}${row.is_vip ? ' <em class="v3-vipdot" aria-label="VIP"></em>' : ''}${v3MarkDot(row.mark)}</span>${apTitle(ap)}</span>`;
}

// ── Аватар без фото: личное созвездие ──────────────────────────────────────────────
// У каждого игрока своё созвездие: рисунок задаёт id (одно и то же на любом устройстве), число звёзд растёт с уровнем аккаунта (4 → 9), а звёзды,
// уже появившиеся, не двигаются. Цвета берутся из токенов образа, поэтому созвездие всегда в тон. Главная звезда у VIP золотая.
function _cnRand(text) {
  let h = 1779033703 ^ text.length;
  for (let i = 0; i < text.length; i++) { h = Math.imul(h ^ text.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
  return () => { h = Math.imul(h ^ (h >>> 16), 2246822507); h = Math.imul(h ^ (h >>> 13), 3266489909); return ((h ^= h >>> 16) >>> 0) / 4294967296; };
}
const _cnCount = level => Math.min(9, 4 + Math.floor(((Number(level) || 1) - 1) / 6));
// Новый уровень добавил звезду: она вспыхивает на месте (вызов из v3Delights). Фото вместо созвездия: ничего не происходит
function v3GrowStar(from, to) {
  if (_cnCount(to) <= _cnCount(from)) return;
  document.querySelector('#pro-showcase-ava .cn-st circle:last-child')?.classList.add('cn-pop');
}
function _v3Constellation(seed, level, vip) {
  const rand = _cnRand(String(seed ?? 'player')), count = _cnCount(level);
  const pts = [], edges = [];
  for (let i = 0; i < count; i++) {       // лучший из нескольких кандидатов: звёзды расходятся по кругу, а не липнут друг к другу
    let best = null, gap = -1;
    for (let t = 0; t < 14; t++) {
      const a = rand() * 6.2832, r = 11 + Math.sqrt(rand()) * 27, p = [50 + Math.cos(a) * r, 50 + Math.sin(a) * r];
      const far = pts.length ? Math.min(...pts.map(q => Math.hypot(q[0] - p[0], q[1] - p[1]))) : 99;
      if (far > gap) { best = p; gap = far; }
    }
    const size = i ? 1.2 + rand() * 1.3 : 0, extra = rand() < .38;
    if (pts.length) {                      // линия к ближайшей из прежних звёзд, иногда ещё одна: получается фигура, а не веер
      const order = pts.map((q, j) => [Math.hypot(q[0] - best[0], q[1] - best[1]), j]).sort((x, y) => x[0] - y[0]);
      edges.push([order[0][1], i]); if (extra && order[1]) edges.push([order[1][1], i]);
    }
    pts.push(best); best.size = size;
  }
  const f = n => n.toFixed(1), main = pts[0], back = _cnRand(`${seed}-dust`);   // фоновая пыль считается отдельно: с ростом уровня она не сдвигается
  const dust = Array.from({ length: 7 }, () => { const a = back() * 6.2832, r = Math.sqrt(back()) * 43; return `<circle cx="${f(50 + Math.cos(a) * r)}" cy="${f(50 + Math.sin(a) * r)}" r="${f(.45 + back() * .4)}"/>`; }).join('');
  const path = edges.map(([a, b]) => `M${f(pts[a][0])} ${f(pts[a][1])}L${f(pts[b][0])} ${f(pts[b][1])}`).join('');
  const dots = pts.slice(1).map((p, i) => `<circle class="${i % 3 === 1 ? 'cn-tw' : ''}" cx="${f(p[0])}" cy="${f(p[1])}" r="${f(p.size)}"/>`).join('');
  const [x, y] = main.map(Number), k = 6.5;
  const spark = `M${f(x)} ${f(y - k)}Q${f(x)} ${f(y)} ${f(x + k)} ${f(y)}Q${f(x)} ${f(y)} ${f(x)} ${f(y + k)}Q${f(x)} ${f(y)} ${f(x - k)} ${f(y)}Q${f(x)} ${f(y)} ${f(x)} ${f(y - k)}Z`;
  return `<svg class="cn${vip ? ' cn-vip' : ''}" viewBox="0 0 100 100" aria-hidden="true" focusable="false"><circle class="cn-bg" cx="50" cy="50" r="50"/><g class="cn-dust">${dust}</g><path class="cn-ln" d="${path}"/><g class="cn-st">${dots}</g><circle class="cn-glow" cx="${f(x)}" cy="${f(y)}" r="11"/><path class="cn-main" d="${spark}"/></svg>`;
}
