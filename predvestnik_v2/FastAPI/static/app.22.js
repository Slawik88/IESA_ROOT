// ── Skins V3 · скин приложения и фирменные детали ───────────────────────────────
// v3ApplyLook: палитра надетого скина приходит с сервера токенами и ставится на body (без отдельного CSS на скин).
// Тир скина управляет уровнем эффектов (app.18.js). Без скина остаётся базовая палитра из shell-v3.css.
const _V3_TOKEN = /^--(?:v3-[a-z-]{2,16}|acc-rgb)$/;
let _v3Applied = [];
// Токены скина как строка style для .v3-scope (витрина, публичная карточка): те же проверки, что и для body
function v3TokenStyle(tokens) {
  if (!tokens || typeof tokens !== 'object') return '';
  return Object.entries(tokens).filter(([key, value]) => _V3_TOKEN.test(key) && _v3SafeValue(value)).map(([key, value]) => `${key}:${value}`).join(';');
}
function _v3SafeValue(value) { return typeof value === 'string' && value.length < 400 && !/[;{}<>\\]|url\(|@import|expression/i.test(value); }
function v3ApplyLook(look) {
  const style = document.body.style;
  _v3Applied.forEach(key => style.removeProperty(key));
  _v3Applied = [];
  [...document.body.classList].forEach(name => { if (/^skin-/.test(name)) document.body.classList.remove(name); });   // наследие прежних скинов
  const tokens = look && typeof look.tokens === 'object' ? look.tokens : null;
  if (tokens) {
    for (const [key, value] of Object.entries(tokens)) {
      if (_V3_TOKEN.test(key) && _v3SafeValue(value)) { style.setProperty(key, value); _v3Applied.push(key); }
    }
  }
  document.body.dataset.skin = look && /^[a-z_]{2,24}$/.test(look.id || '') ? look.id : '';
  document.dispatchEvent(new CustomEvent('skinchange', { detail: { css_class: '', tier: _AP_TIERS.includes(look?.tier) ? look.tier : 'D' } }));
}

// Фирменные детали: живут внутри рамки аватара и открываются, когда скин прокачан до своего потолка.
// Форма и движение описаны в skin-signatures-v3.css и skin-signatures-2-v3.css.
const _AP_DECOR = (() => {
  const many = (cls, count, vars) => Array.from({ length: count }, (_, i) => `<u class="${cls}" style="${vars(i)}"></u>`).join('');
  return {
    void: '<u class="sg-shadow"></u><u class="sg-disk"></u><u class="sg-arc"></u><u class="sg-arc sg-arc--low"></u>',
    aurora: '<u class="sg-veil"></u><u class="sg-veil"></u><u class="sg-veil"></u>',
    solar: many('sg-prom', 7, i => `--o:${i * 51.4}deg;--d:${(2.2 + (i % 3) * .5).toFixed(1)}s;--l:${(.7 + (i % 3) * .18).toFixed(2)}`),
    petalstorm: many('sg-pet', 9, i => `--o:${i * 40}deg;--r:${44 + (i % 3) * 8}px;--d:${(9 + (i % 4) * 2).toFixed(0)}s`),
    artifact: '<svg class="sg-hex" viewBox="0 0 100 100"><polygon points="50,2 93,26 93,74 50,98 7,74 7,26"/><polygon class="sg-hex-in" points="50,10 86,30 86,70 50,90 14,70 14,30"/></svg>' + many('sg-drone', 3, i => `--o:${i * 120}deg`) + '<u class="sg-tear"></u>',
    lotus: `<u class="sg-bloom">${[-58, -29, 0, 29, 58].map(a => `<u class="sg-leaf" style="--o:${a}deg"></u>`).join('')}${[-38, 0, 38].map(a => `<u class="sg-leaf sg-leaf--f" style="--o:${a}deg"></u>`).join('')}</u><u class="sg-moon"></u>`,
    tide: '<u class="sg-scales"></u><u class="sg-crack"></u>' + many('sg-wave', 3, i => `--i:${i}`),
    comet: '<u class="sg-orbit"><u class="sg-head"></u></u><u class="sg-orbit sg-orbit--far"><u class="sg-head"></u></u>',
    chrono: '<u class="sg-dial"></u><u class="sg-hand sg-hand--min"></u><u class="sg-hand sg-hand--hour"></u><u class="sg-cog"></u><u class="sg-cog sg-cog--r"></u>',
    heart: '<u class="sg-pulse"></u><u class="sg-pulse"></u><u class="sg-pulse"></u><u class="sg-core"></u>',
    // личные образы: глянцевые банты с орбитой звёзд и багровая луна с брызгами (skins-exclusive-v3.css); подтёки у «Багрового Мрака» с первого тира, их рисует apFrameOrn
    bowstar: () => _ornBow('sg-bow') + _ornBow('sg-bow sg-bow--s') + many('sg-star', 3, () => ''),
    bloodmoon: '<u class="sg-bmoon"></u><u class="sg-splat"></u>',
  };
})();
function apSigDecor(sig) { const draw = _AP_DECOR[sig]; return typeof draw === 'function' ? draw() : draw || ''; }

// ── Личные образы: свой слой SVG на сцене и на рамке ──────────────────────────────────────────────────────────
// «Алая Звезда» рисует глянцевые банты с цепочкой бусин, блёстки и звёзды в обводке; «Багровый Мрак» мокрые подтёки, брызги и отпечаток ладони.
// Это вектор: чёткий на любом экране, красится палитрой образа и двигается только под .ap-anim (skins-exclusive-v3.css). Богатство растёт с тиром:
// деталь с номером r появляется с тира r. Градиенты и фильтр лежат один раз в скрытом SVG страницы, поэтому их видит любая копия сцены (профиль, топ, предпросмотр).
const _ORN_DEFS = '<svg id="orn-defs" width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>'
  + '<linearGradient id="ornBow" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff7a90"/><stop offset=".45" stop-color="#e3183c"/><stop offset="1" stop-color="#8a0a20"/></linearGradient>'
  + '<linearGradient id="ornBlood" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#3a0508"/><stop offset=".42" stop-color="#8e111a"/><stop offset="1" stop-color="#4a070c"/></linearGradient>'
  + '<linearGradient id="ornBand" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7c0d15"/><stop offset="1" stop-color="#2e0407"/></linearGradient>'
  + '<radialGradient id="ornSplat" cx=".4" cy=".4" r=".7"><stop offset="0" stop-color="#781019"/><stop offset="1" stop-color="#2c0306"/></radialGradient>'
  + '<filter id="ornRough" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency=".05" numOctaves="2" seed="4" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="7"/><feGaussianBlur stdDeviation=".5"/></filter>'
  + '</defs></svg>';
function _ornDefs() { if (!document.getElementById('orn-defs')) document.body.insertAdjacentHTML('beforeend', _ORN_DEFS); }
// Бант как на образце: два широких округлых крыла, узел по центру и два хвоста с V-вырезом на концах. Хвосты рисуются первыми, крылья поверх них
const _ORN_BOW_TAILS = ['M29.5 27L12 54.5L22 51.5L25.5 57.5L33.5 29Z', 'M34.5 27L52 54.5L42 51.5L38.5 57.5L30.5 29Z'];
const _ORN_BOW_WINGS = ['M27 19C22 8 12 3 6 7C0 11 0 25 6 30C12 34 22 31 27 27Z', 'M37 19C42 8 52 3 58 7C64 11 64 25 58 30C52 34 42 31 37 27Z'];
const _ORN_STAR = 'M12 2.6l2.9 6.2 6.8.8-5 4.7 1.3 6.7L12 17.6 6 21l1.3-6.7-5-4.7 6.8-.8z';
function _ornBow(cls) { _ornDefs(); return `<svg class="o-bow ${cls}" viewBox="0 0 64 59" aria-hidden="true">${_ORN_BOW_TAILS.map(d => `<path class="o-w" d="${d}"/>`).join('')}${_ORN_BOW_WINGS.map(d => `<path class="o-w" d="${d}"/>`).join('')}<path class="o-fold" d="M26.5 22.5C23 20.5 19 20.5 15.5 22.5M37.5 22.5C41 20.5 45 20.5 48.5 22.5"/><path class="o-hl" d="M9 11C12 8 16 7 20 9M55 11C52 8 48 7 44 9"/><rect class="o-knot" x="27" y="17" width="10" height="13" rx="4"/><path class="o-hl" d="M29.5 20.5V25"/></svg>`; }
const _ORN = (() => {
  const bow = _ornBow;
  const spark = (cls, d) => `<svg class="o-sp ${cls}" style="--d:${d}s" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 1l2.6 8.4L23 12l-8.4 2.6L12 23l-2.6-8.4L1 12l8.4-2.6z"/></svg>`;
  const star = (cls, d) => `<svg class="o-st ${cls}" style="--d:${d}s" viewBox="0 0 24 24" aria-hidden="true"><path d="${_ORN_STAR}"/></svg>`;
  const chain = (cls, d) => { const pts = Array.from({ length: 12 }, (_, k) => [8 + 3.5 * Math.sin(k * .7), 5 + k * 9]);
    return `<svg class="o-chain ${cls}" style="--d:${d}s" viewBox="0 0 16 112" aria-hidden="true"><path d="M${pts.map(p => p.map(n => n.toFixed(1)).join(' ')).join('L')}"/>${pts.map((p, k) => `<circle cx="${p[0].toFixed(1)}" cy="${p[1]}" r="${k % 2 ? 1.7 : 2.5}"/>`).join('')}</svg>`; };
  const scarlet = [[1, bow('o-b1')], [1, bow('o-b2')], [1, chain('c1', 6)], [1, spark('sa', 3.1)], [1, spark('sb', 4.2)], [1, spark('sc', 3.6)], [1, star('sa', 6)], [1, star('sb', 7)], [1, star('sc', 5.5)],
    [2, spark('sd', 4.8)], [2, star('sd', 6.5)], [3, chain('c2', 7.5)], [5, spark('se', 3.9)], [5, spark('sf', 5.1)], [5, star('se', 7.5)], [6, spark('sg', 3.3)], [7, star('sg', 8)]];
  // подтёки: [x, длина, с какого тира]; по краю сцены 390 в ширину, обрезка по центру (slice), поэтому форма не тянется
  const DR = [[26, 34, 1], [101, 52, 1], [186, 40, 1], [268, 58, 1], [311, 30, 1], [352, 44, 1], [58, 22, 2], [143, 28, 2], [229, 24, 3], [380, 20, 4]];
  const FALL = [[101, 52, 3], [268, 58, 3], [186, 40, 5]];
  const drip = (x, l, i) => `<g class="dr" style="--d:${(6 + (i * 7) % 5).toFixed(0)}s;--i:${i}"><path class="o-wet" d="M${x - 4.2} 8V${l}a4.2 4.2 0 0 0 8.4 0V8z"/><rect class="o-gl" x="${x - 2.3}" y="13" width="1.5" height="${Math.max(4, l - 19)}" rx=".75"/><circle class="o-gl" cx="${x - 1.4}" cy="${l + 1.6}" r=".9"/></g>`;
  const fall = (x, l, i) => `<g transform="translate(${x} ${l + 11})"><path class="fl o-wet" style="--d:${(7 + i * 2)}s;--dl:${-i * 2.3}s" d="M0-5C2.6-1.8 3.6.4 3.6 1.8a3.6 3.6 0 0 1-7.2 0C-3.6.4-2.6-1.8 0-5z"/></g>`;
  const splat = (cls, d, sats) => `<svg class="o-splat ${cls}" viewBox="0 0 100 100" aria-hidden="true"><path d="${d}"/><g>${sats}</g></svg>`;
  const SPL = { a: ['M72.4 46.1Q66.1 49.5 65.3 51.5Q64.4 53.5 63.3 54.7Q62.2 55.9 61.6 57.5Q61.0 59.1 59.5 60.8Q58.0 62.6 56.3 62.5Q54.6 62.4 53.3 64.0Q52.0 65.6 50.0 65.1Q48.0 64.7 46.9 62.4Q45.8 60.0 43.5 62.1Q41.2 64.2 39.6 62.3Q37.9 60.5 37.6 58.7Q37.2 57.0 37.8 55.1Q38.4 53.2 39.0 51.7Q39.6 50.2 29.8 47.1Q20.1 43.9 28.7 43.7Q37.2 43.5 34.8 38.2Q32.3 32.9 31.9 28.7Q31.5 24.5 36.5 26.0Q41.5 27.5 45.1 33.2Q48.7 38.9 49.9 38.2Q51.0 37.6 52.2 38.8Q53.3 40.0 55.1 40.2Q57.0 40.3 62.9 37.5Q68.9 34.7 66.2 38.6Q63.6 42.6 71.1 42.7Q78.7 42.7 72.4 46.1Z', '<circle cx="63.8" cy="91.2" r="1.9"/><circle cx="37.2" cy="81.7" r="2.1"/><circle cx="81.7" cy="33.3" r="2.9"/><circle cx="90.4" cy="52.8" r="2.3"/><circle cx="34.8" cy="16.6" r="2.4"/><circle cx="94.6" cy="45.9" r="2.1"/><circle cx="20.6" cy="76.4" r="3.6"/><circle cx="96.1" cy="50.1" r="3.5"/><circle cx="9.9" cy="23.6" r="1.1"/><circle cx="68.4" cy="94.3" r="2.6"/><circle cx="19.4" cy="33.9" r="1.5"/><circle cx="18.1" cy="62.3" r="2.6"/>'], b: ['M65.8 48.2Q67.0 49.3 63.6 50.9Q60.3 52.4 69.8 58.1Q79.4 63.7 70.7 62.3Q61.9 60.9 60.2 61.0Q58.4 61.2 56.5 62.3Q54.5 63.5 52.8 62.7Q51.0 61.8 49.5 61.8Q48.0 61.8 46.1 62.9Q44.2 64.1 38.6 68.9Q33.0 73.7 36.5 66.3Q39.9 58.9 31.2 62.0Q22.5 65.2 27.8 59.4Q33.1 53.6 35.8 51.8Q38.6 50.0 38.2 48.6Q37.8 47.2 37.9 45.3Q37.9 43.3 38.0 41.0Q38.0 38.7 35.7 31.1Q33.3 23.6 39.0 29.0Q44.7 34.3 45.2 26.9Q45.6 19.5 48.9 27.7Q52.2 35.8 53.5 35.9Q54.8 35.9 59.9 31.9Q65.0 27.9 61.8 35.2Q58.7 42.5 61.7 42.6Q64.7 42.7 64.7 44.9Q64.7 47.1 65.8 48.2Z', '<circle cx="44.8" cy="6.9" r="2.8"/><circle cx="94.4" cy="54.3" r="2.1"/><circle cx="14.2" cy="71.4" r="2.2"/><circle cx="41.5" cy="83.0" r="3.3"/><circle cx="83.0" cy="60.3" r="2.7"/><circle cx="84.3" cy="82.4" r="2.4"/><circle cx="82.2" cy="62.4" r="3.0"/><circle cx="75.6" cy="85.8" r="2.0"/><circle cx="90.5" cy="67.8" r="1.7"/><circle cx="86.4" cy="55.1" r="3.0"/><circle cx="74.0" cy="14.2" r="2.0"/><circle cx="56.1" cy="86.3" r="3.3"/>'], c: ['M62.1 48.5Q63.7 49.4 64.1 51.8Q64.4 54.2 62.1 54.9Q59.7 55.6 59.4 56.8Q59.1 58.0 58.7 60.0Q58.2 62.0 56.5 61.5Q54.8 61.0 53.6 63.9Q52.4 66.8 50.4 64.1Q48.3 61.4 44.3 67.4Q40.4 73.3 41.9 66.3Q43.5 59.2 40.8 60.4Q38.1 61.6 32.7 62.2Q27.3 62.7 30.5 58.0Q33.7 53.2 33.2 51.8Q32.7 50.4 34.0 48.3Q35.2 46.3 34.9 44.4Q34.6 42.5 29.9 34.8Q25.2 27.2 34.3 33.3Q43.3 39.4 44.5 39.3Q45.7 39.2 46.0 32.5Q46.2 25.8 49.6 23.0Q53.0 20.2 53.9 27.8Q54.7 35.5 55.8 37.5Q57.0 39.5 64.5 35.6Q72.1 31.7 67.1 37.5Q62.1 43.3 61.3 45.5Q60.5 47.6 62.1 48.5Z', '<circle cx="83.9" cy="44.7" r="3.0"/><circle cx="69.2" cy="21.7" r="3.1"/><circle cx="21.9" cy="81.4" r="1.1"/><circle cx="85.0" cy="60.6" r="3.5"/><circle cx="64.7" cy="92.1" r="3.4"/><circle cx="86.3" cy="36.2" r="2.0"/><circle cx="5.7" cy="43.1" r="1.4"/><circle cx="49.5" cy="4.8" r="3.2"/><circle cx="96.0" cy="60.8" r="1.3"/><circle cx="27.0" cy="85.8" r="3.4"/><circle cx="24.9" cy="89.6" r="2.5"/><circle cx="35.3" cy="85.5" r="1.5"/>'] };
  const hand = '<svg class="o-hand" viewBox="0 0 100 130" aria-hidden="true"><g filter="url(#ornRough)"><rect x="25" y="22" width="11" height="46" rx="5.5" transform="rotate(-12 30 66)"/><rect x="39" y="10" width="12" height="56" rx="6" transform="rotate(-3 45 64)"/><rect x="54" y="14" width="11" height="52" rx="5.5" transform="rotate(5 60 64)"/><rect x="67" y="32" width="10" height="38" rx="5" transform="rotate(15 72 68)"/><rect x="5" y="66" width="11" height="38" rx="5.5" transform="rotate(-50 12 92)"/><path d="M26 66C22 92 30 120 50 124C72 120 80 92 76 66z"/></g></svg>';
  const crimson = ti => `<svg class="o-drips" viewBox="0 0 390 90" preserveAspectRatio="xMidYMin slice" aria-hidden="true"><path class="o-band" d="M0 0H390V9Q372 14 355 9T320 9T285 10T250 9T215 10T180 9T145 10T110 9T75 10T40 9T0 10z"/>`
    + `${DR.filter(d => d[2] <= ti).map((d, i) => drip(d[0], d[1], i)).join('')}${FALL.filter(d => d[2] <= ti).map((d, i) => fall(d[0], d[1], i)).join('')}</svg>`
    + splat('sa', ...SPL.a) + splat('sb', ...SPL.b) + (ti >= 3 ? splat('sc', ...SPL.c) : '') + hand;
  return { scarlet_star: ti => scarlet.filter(o => o[0] <= ti).map(o => o[1]).join(''), crimson_dark: crimson };
})();
// Подтёки под кольцом аватара: четыре, вид и движение те же, что у подтёков сцены
const _ORN_FRAME = { crimson_dark: ti => `<svg class="o-rd" viewBox="0 0 92 60" preserveAspectRatio="none" aria-hidden="true">${[[14, 28], [38, 48], [56, 22], [78, 36]].map(([x, l], i) => `<g class="dr" style="--d:${6 + i}s"><path class="o-wet" d="M${x - 4.4} 0V${l}a4.4 4.4 0 0 0 8.8 0V0z"/><rect class="o-gl" x="${x - 2.4}" y="4" width="1.5" height="${l - 8}" rx=".75"/></g>`).join('')}</svg>` };
function apOrn(ap) { const draw = _ORN[ap.id]; if (!draw) return ''; _ornDefs(); return `<div class="ap-orn ap-t${ap.ti}" data-sk="${ap.id}" aria-hidden="true">${draw(ap.ti)}</div>`; }
function apFrameOrn(ap) { const draw = _ORN_FRAME[ap.id]; if (!draw) return ''; _ornDefs(); return draw(ap.ti); }
