// ── Фирменные детали SSS · B (огонь, металл, ночь) ─────────────────────────────────────────────
// Продолжение _AP_DECOR и _ORN из app.22.js: разметка слоя фирменной детали (.ap-sig-<id>) и SVG-части образа (_ORN[<skin id>]); деталь видна с тира SSS (sig_from).
// Рамка рисуется в поле «-20 -20 140 140»: 1 единица это 1% рамки, центр кольца (50,50), край рамки r=50, поэтому деталь растёт и сжимается вместе с аватаром.
// Градиенты лежат один раз в своём скрытом SVG (#orn-defs-b). Всё внутри функции: имена не попадают в общую область и не спорят с другими файлами. Стили: skin-sig-b-v3.css.
(() => {
  const f = v => +v.toFixed(1), rad = d => d * Math.PI / 180;
  const pt = (r, d, c = 50) => [f(c + r * Math.cos(rad(d))), f(c + r * Math.sin(rad(d)))];
  const poly = a => `M${a.map(p => p.join(' ')).join('L')}z`;
  const hole = (x, y, r) => `M${x + r} ${y}a${r} ${r} 0 1 0 ${-2 * r} 0a${r} ${r} 0 1 0 ${2 * r} 0z`;
  const gear = (n, tip, root) => poly(Array.from({ length: n * 4 }, (_, i) => pt([root, tip, tip, root][i % 4], (Math.floor(i / 4) + [-.3, -.17, .17, .3][i % 4]) * 360 / n, 0)));
  const svg = (cls, vb, body) => `<svg class="${cls}" viewBox="${vb}" aria-hidden="true">${body}</svg>`;
  const W = '-20 -20 140 140';
  const st = a => a.map(([o, c]) => `<stop offset="${o}" stop-color="${c}"/>`).join('');
  const RA = k => pt(64, 30 * k + 15), RB = k => pt(57.4, 30 * k);   // грани рубина: 12 углов внешнего (A) и внутреннего (B) контура, 24 треугольника между ними
  const LIN = 'x1="0" y1="0" x2="1" y2="1"', UP = 'x1="0" y1="1" x2="0" y2="0"';   // по диагонали и снизу вверх
  const DEFS = '<svg id="orn-defs-b" width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>'
    + `<linearGradient id="ornInfernoLava" ${LIN}>${st([[0, '#ffe08a'], [.4, '#ff9a3c'], [.78, '#e3432b'], [1, '#8a1d10']])}</linearGradient>`
    + `<linearGradient id="ornInfernoCrust" ${LIN}>${st([[0, '#53200f'], [1, '#1b0805']])}</linearGradient>`
    + `<linearGradient id="ornInfernoVein" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="200">${st([[0, 'rgba(227,67,43,0)'], [.22, '#e3432b'], [.55, '#ffb35a'], [.85, '#e3432b'], [1, 'rgba(227,67,43,0)']])}</linearGradient>`
    + `<linearGradient id="ornCopperBody" ${LIN}>${st([[0, '#f6c299'], [.38, '#cd7d47'], [.75, '#8f4a27'], [1, '#5d2c17']])}</linearGradient>`
    + `<radialGradient id="ornPumpBody" cx=".5" cy=".56" r=".62">${st([[0, '#f08a1f'], [.55, '#b4500a'], [1, '#5a2105']])}</radialGradient>`
    + `<radialGradient id="ornPumpGlow" cx=".5" cy=".5" r=".6">${st([[0, '#fffbe0'], [.55, '#ffd36b'], [1, '#ffa63c']])}</radialGradient>`
    + `<radialGradient id="ornPumpHalo" cx=".5" cy=".5" r=".5">${st([[0, 'rgba(255,170,60,.6)'], [1, 'rgba(255,150,40,0)']])}</radialGradient>`
    + `<linearGradient id="ornPumpLeaf" ${LIN}>${st([[0, '#a3cc62'], [1, '#4b7a29']])}</linearGradient>`
    + `<linearGradient id="ornWitchMoon" ${LIN}>${st([[0, '#fff3c0'], [.5, '#ffd36b'], [1, '#d9992b']])}</linearGradient>`
    + `<linearGradient id="ornWitchFire" ${UP}>${st([[0, 'rgba(31,154,74,.2)'], [.5, '#3fe070'], [1, '#c8ffb0']])}</linearGradient>`
    + `<linearGradient id="ornRubySheen" x1="0" y1="0" x2="1" y2="0">${st([[0, 'rgba(255,255,255,0)'], [.5, 'rgba(255,246,242,.9)'], [1, 'rgba(255,255,255,0)']])}</linearGradient>`
    + `<linearGradient id="ornGateRise" ${UP}>${st([[0, 'rgba(190,160,255,.9)'], [1, 'rgba(190,160,255,0)']])}</linearGradient>`
    + `<clipPath id="ornRubyClip"><path clip-rule="evenodd" d="${poly(Array.from({ length: 12 }, (_, k) => RA(k)))}${hole(50, 50, 55)}"/></clipPath></defs></svg>`;
  const defs = () => { if (!document.getElementById('orn-defs-b')) document.body.insertAdjacentHTML('beforeend', DEFS); };
  const sig7 = draw => ti => (ti >= 7 ? (defs(), draw()) : '');   // часть сцены только с тира SSS
  const smooth = p => `M${p[0].join(' ')}${p.slice(1, -1).map((q, i) => `Q${q.join(' ')} ${f((q[0] + p[i + 2][0]) / 2)} ${f((q[1] + p[i + 2][1]) / 2)}`).join('')}L${p[p.length - 1].join(' ')}`;
  const star4 = (cls, a, s, extra = '') => `<path class="${cls}" ${extra} transform="translate(${a.join(' ')}) scale(${s})" d="M0-1L.22-.22 1 0 .22.22 0 1-.22.22-1 0-.22-.22z"/>`;

  // ── Инферно · blaze: обод из плит остывшей лавы, магма светится в швах и трещинах, угли; жилы-трещины по краям сцены с дрожащим жаром ──
  const jit = (k, i) => Math.sin(k * 7.3 + i * 3.1) * 1.3;
  const plates = Array.from({ length: 9 }, (_, k) => {
    const a = k * 40 - 98, at = i => a + 1.8 + i * 9.1;
    const out = [0, 1, 2, 3, 4].map(i => pt(61.8 + jit(k, i) * .85, at(i))), inn = [4, 3, 2, 1, 0].map(i => pt(56.8 + jit(k, i + 5) * .85, at(i)));
    return `<path d="${poly([...out, ...inn])}"/>${k % 2 ? '' : `<path class="sg-cr" d="M${pt(57.8, a + 12)}L${pt(59.8, a + 17)}L${pt(58.2, a + 22)}L${pt(61.2, a + 27)}"/>`}`;
  }).join('');
  const embers = [[-72, 1.5, 3.6, 0], [-8, 1.1, 4.4, -1.4], [205, 1.3, 4, -2.2], [250, 1, 3.2, -.8]].map(([a, r, d, dl], i) => `<circle class="sg-em" cx="${pt(59.5, a)[0]}" cy="${pt(59.5, a)[1]}" r="${r}" style="--d:${d}s;--dl:${dl}s;--dx:${i % 2 ? 7 : -7}px"/>`).join('');
  const vein = ph => {   // трещина вдоль края сцены: плавная жила с отростками внутрь и тающими концами; жар поднимается от неё
    const p = Array.from({ length: 11 }, (_, i) => [f(8 + Math.sin(i * 1.1 + ph) * 4.5 + Math.cos(i * .53 + ph * 2) * 2), i * 20]);
    const br = [3, 6, 8].map((i, k) => `M${p[i].join(' ')}q${5 + k * 2} 4 ${7 + k * 2} ${10 + k * 3}`).join('');
    return `<path class="o-vg" d="${smooth(p)}${br}"/><path class="o-vn" d="${smooth(p)}"/><path class="o-vb" d="${br}"/><path class="o-hz" style="--dl:${-ph}s" d="M17 188c-3-4 3-8 0-12s3-8 0-12"/>`;
  };

  // ── Медные Сумерки · cogs: медная шестерня-ободок (40 зубьев) и малая шестерня (10) в зацеплении, патина, искры кузни ──
  const ringGear = `<g transform="translate(50 50)"><path class="sg-gear" fill-rule="evenodd" d="${gear(40, 63.2, 58.6)}${hole(0, 0, 55.2)}"/>`
    + '<circle class="sg-pt" r="57" stroke-dasharray="7 37 3 49 12 66 5 80"/><circle class="sg-pt sg-pt--t" r="61.2" stroke-dasharray="4 66 9 58 3 90"/>'
    + Array.from({ length: 20 }, (_, i) => `<circle class="sg-rv" cx="${pt(56.9, i * 18, 0)[0]}" cy="${pt(56.9, i * 18, 0)[1]}" r=".85"/>`).join('')
    + `<path class="sg-hl" d="M${pt(56.9, 205, 0)}A56.9 56.9 0 0 1 ${pt(56.9, 292, 0)}"/></g>`;
  const smallGear = `<g transform="rotate(-9)"><path class="sg-gear" fill-rule="evenodd" d="${gear(10, 17.45, 12.85)}${hole(0, 0, 3)}${[36, 108, 180, 252, 324].map(a => hole(...pt(8.4, a, 0), 1.7)).join('')}"/><circle class="sg-pt" r="15.2" stroke-dasharray="7 24 3 36"/><circle class="sg-rv" r="1.3"/></g>`;
  const sparks = [[10, -12, 0], [17, -4, -.7], [5, -17, -1.4], [13, -9, -2.1]].map(([dx, dy, dl]) => `<path class="sg-spk" style="--dx:${dx}px;--dy:${dy}px;--dl:${dl}s" d="M0-2.4L.7-.7 2.4 0 .7.7 0 2.4-.7.7-2.4 0-.7-.7z"/>`).join('');

  // ── Тыквенный Фонарь · jacklight: подвесной фонарь с резным лицом (сцена), тыквенная лоза с листьями и огоньками на кольце (рамка) ──
  const lantern = '<g class="o-sw"><path class="o-ch" d="M30 0V17"/><circle class="o-gw" cx="30" cy="47" r="30"/>'
    + '<path class="o-st" d="M28.4 27c-.2-5 1.2-8.6 4.8-10.4l1.5 2.8c-2 1.3-2.9 3.5-2.9 7.6z"/>'
    + '<ellipse cx="17.5" cy="47" rx="12.5" ry="17.5"/><ellipse cx="42.5" cy="47" rx="12.5" ry="17.5"/><ellipse cx="30" cy="46" rx="15" ry="19.5"/>'
    + '<path class="o-rb" d="M23.5 28.5Q19.8 46 23.5 63.5M36.5 28.5Q40.2 46 36.5 63.5"/>'
    + '<g class="o-fc"><path d="M18.4 45.6l9.4-1-4.2-9.6zM41.6 45.6l-9.4-1 4.2-9.6zM30 48l-2.8 4.4h5.6z"/><path d="M17 53.4L21.6 55.4 24.4 52.4 28 56.4 31 53.2 34.2 56.6 37 52.4 40 55.4 43 53.4Q30 72 17 53.4z"/></g></g>';
  const vinePts = Array.from({ length: 21 }, (_, i) => pt(58.5 + 2.4 * Math.sin(i * 1.45), 192 + i * 7));
  const leaf = (a, s) => `<g transform="translate(${pt(58.6, a).join(' ')}) rotate(${a + s}) scale(${s > 0 ? 1 : .85})"><path class="o-lf" d="M0 0Q5.5-6.5 13 0Q5.5 6.5 0 0z"/><path class="o-lv" d="M1 0H11"/></g>`;
  const curl = (a, dir) => { const p = pt(58.5, a); return `<path class="o-vn" d="${smooth(Array.from({ length: 16 }, (_, i) => { const t = i * .55, r = 4.4 - i * .24; return [f(p[0] + dir * Math.cos(t + 1.6) * r), f(p[1] + Math.sin(t + 1.6) * r - 4.4)]; }))}"/>`; };
  const mini = (a, d) => `<g transform="translate(${pt(61, a).join(' ')}) rotate(${a + 90})"><g class="o-mp" style="--d:${d}s"><ellipse cx="-2.6" cy="0" rx="2.8" ry="3.4"/><ellipse cx="2.6" cy="0" rx="2.8" ry="3.4"/><ellipse cx="0" cy="0" rx="3" ry="3.8"/><path class="o-ms" d="M0-3.5q.4-2 2-2.6"/></g></g>`;

  // ── Паутина Полуночи · cobwebs: паутина в углах сцены и на кольце, росинки-звёзды, паучок на нити ──
  const web = (hx, hy, dir, span, nr, ds) => {
    const at = (d, a) => `${f(hx + d * Math.cos(rad(a)))} ${f(hy + d * Math.sin(rad(a)))}`, ang = Array.from({ length: nr }, (_, i) => dir - span / 2 + span * i / (nr - 1));
    const rays = ang.map(a => `M${hx} ${hy}L${at(ds[ds.length - 1], a)}`).join('');
    const arcs = ds.map(d => ang.slice(1).map((a, i) => `M${at(d, ang[i])}Q${at(d * .8, (ang[i] + a) / 2)} ${at(d, a)}`).join('')).join('');
    return { d: rays + arcs, dew: (j, i, s) => star4('o-dw', at(ds[j], ang[i]).split(' '), s, `style="--dl:${-(j + i) * .7}s"`) };
  };
  const cornerWeb = web(0, 0, 45, 90, 6, [16, 29, 43, 58, 74, 92]), ringWeb = web(...pt(51, -138), -138, 76, 5, [9, 17, 26, 36]);
  const legs = 'M10.4 47Q5 43 2.5 46M10 49Q4.5 47 1.8 51M10 51Q4.5 51.5 2.2 56M10.6 53Q6.5 56 5 61';
  const spider = `<line class="o-th" x1="12" y1="0" x2="12" y2="44"/><g class="o-sp"><path class="o-lg" d="${legs}"/><path class="o-lg" transform="matrix(-1 0 0 1 24 0)" d="${legs}"/><ellipse cx="12" cy="53.4" rx="3.5" ry="4.5"/><circle cx="12" cy="47.2" r="2.3"/><path class="o-mk" d="M12 51.2v4.2"/></g>`;

  // ── Час Ведьм · witchmoon: месяц и ведьма на метле (сцена), зелёный огонь под кольцом и пузырьки зелья (рамка) ──
  const witch = '<path class="o-wb" d="M6 21L41 12.5"/><path class="o-ws" d="M8 20.2L.5 16.5 -1 21 1 26.5 8 22z"/><path d="M20 18.5C14 18.5 10.5 21 7.5 25.5 13 23.4 18.5 23.2 24.5 19.6zM21 18.5C20.6 12.4 23 8.4 27.2 8.2L30.4 9.6C31.4 13 30.6 16 28.4 18.5z"/><circle cx="29.3" cy="7" r="2.6"/><path d="M24.3 5.4C25.8 1.2 24.8-1.6 21.4-4.2 27-3.6 31.6.3 33.6 5.4z"/><ellipse cx="29" cy="5.6" rx="6.9" ry="1.5"/><path class="o-wb" d="M28.4 11.6L35.4 14.4M24 18l2.4 6.4M26.8 8.4q-4 .8-6.2 4.6"/>';
  const FL = 'M-4 0C-6.4-5-3.4-8.6-1.6-12.4C-1-10.4 0-9.8.8-11C1.2-13.8.6-16.6 2-19 3.6-13 6.6-7 4 0z';
  const tongues = [[18, 14], [34, 19], [50, 21], [66, 15], [114, 15], [130, 21], [146, 19], [162, 14]].map(([a, h], i) => `<g transform="translate(${pt(54.2, a).join(' ')}) rotate(${a + 90}) scale(${i % 2 ? -.8 : .8} ${h / 19})"><g class="sg-fl" style="--d:${(1.5 + i % 3 * .4).toFixed(1)}s;--dl:${-i * .45}s"><path d="${FL}"/><path class="sg-fc" transform="scale(.55 .78)" d="${FL}"/></g></g>`).join('');
  const bubbles = [[132, 14, 4.6, 0], [48, 12, 5.4, -1.8], [150, 6, 6, -3.2], [30, 8, 4.2, -.9]].map(([a, dy, d, dl], i) => `<g transform="translate(${pt(66, a).join(' ')})"><g class="sg-bb" style="--d:${d}s;--dl:${dl}s;--dy:-${dy * 1.8}px;--dx:${i % 2 ? 6 : -6}px"><path d="M-1.2-.6a1.6 1.6 0 0 1 1-1"/><circle r="${2.5 + (i % 3) * .5}"/></g></g>`).join('');

  // ── Рубиновый Собор · facets: огранённая оправа из 24 граней, блики и полоса света по граням, стрельчатая арка с жемчужной нитью ──
  const facets = Array.from({ length: 24 }, (_, i) => {
    const k = i >> 1, tri = i % 2 ? [RA(k - 1), RA(k), RB(k)] : [RB(k), RA(k), RB(k + 1)], c = tri.reduce((s, p) => [s[0] + p[0] / 3, s[1] + p[1] / 3], [0, 0]);
    const s = Math.min(1, Math.max(0, .5 + .5 * Math.cos(Math.atan2(c[1] - 50, c[0] - 50) + rad(135)) + (i % 2 ? .12 : -.1) + Math.sin(i * 2.3) * .12));
    return `<path d="${poly(tri)}" style="fill:${s < .6 ? `color-mix(in srgb, var(--ap-a) ${f(s / .6 * 55)}%, var(--ap-b))` : `color-mix(in srgb, var(--ap-c) ${f((s - .6) / .4 * 70)}%, var(--ap-a))`}"/>`;
  }).join('');
  const glints = [[RA(7), 4.6, 0], [RA(2), 3.4, -1.1], [RA(5), 3, -2.2], [RB(3), 2.4, -.6]].map(([p, s, dl]) => star4('sg-gl', p, s, `style="--dl:${dl}s"`)).join('');
  const arch = R => `M${70 - R} 50A${R} ${R} 0 0 1 50 ${f(50 - Math.sqrt(R * R - 400))}A${R} ${R} 0 0 1 ${30 + R} 50`;   // две дуги радиуса R сходятся в вершине над кольцом (центры на линии пят, x=70 и x=30)
  const pearls = [192, 206, 220, 234, 247].map(a => { const p = [f(70 + 86.5 * Math.cos(rad(a))), f(50 + 86.5 * Math.sin(rad(a)))]; return `<circle cx="${p[0]}" cy="${p[1]}" r="1.3"/><circle cx="${f(100 - p[0])}" cy="${p[1]}" r="1.3"/>`; }).join('');

  // ── Порог · gateway: дверной проём из света вокруг кольца, порог и тени-шёпоты, что дрейфуют вверх вдоль косяков ──
  const wisp = (x, h, d, dl, mir) => `<g transform="translate(${x} 101) scale(${mir} 1)"><path class="sg-ws" style="--d:${d}s;--dl:${dl}s" d="M0 0C-7-${h * .22} 7-${h * .44} 0-${h * .66}S-5-${h * .9} 1-${h}a2.4 2.4 0 1 1 -3.6-1.4"/></g>`;
  Object.assign(_AP_DECOR, {
    blaze: () => (defs(), svg('sg-b', W, `<path class="sg-lava" d="${hole(50, 50, 59.3)}"/><g class="sg-crust">${plates}</g>${embers}`)),
    cogs: () => (defs(), svg('sg-b sg-gr', W, ringGear) + svg('sg-b sg-cg', '-20 -20 40 40', smallGear) + svg('sg-b sg-sp', W, `<g transform="translate(${pt(61, -63).join(' ')})">${sparks}</g>`)),
    jacklight: () => (defs(), svg('sg-b sg-vn', W, `<path class="o-vn" d="${smooth(vinePts)}"/>${curl(192, 1)}${curl(332, -1)}${[212, 252, 296].map((a, i) => leaf(a, i % 2 ? 30 : -34)).join('')}${mini(232, 3.1)}${mini(314, 2.6)}`)),
    cobwebs: () => (defs(), svg('sg-b sg-wb', W, `<path class="o-wl" d="${ringWeb.d}"/>${ringWeb.dew(1, 1, 1.2)}${ringWeb.dew(2, 3, 1)}${ringWeb.dew(3, 2, 1.3)}`)),
    witchmoon: () => (defs(), svg('sg-b sg-fr', W, tongues) + svg('sg-b sg-bu', W, bubbles)),
    facets: () => (defs(), svg('sg-b sg-gem', W, `<g class="sg-fct">${facets}</g><g clip-path="url(#ornRubyClip)"><g transform="rotate(24 50 50)"><rect class="sg-sw" x="-18" y="-30" width="15" height="170"/></g></g>${glints}`)
      + svg('sg-b sg-ar', '-30 -50 160 100', `<path class="sg-a1" d="${arch(90)}"/><path class="sg-a2" d="${arch(83)}"/><g class="sg-pe">${pearls}</g><path class="sg-ap" d="M50 -39.4l3.6 4.2L50 -28.6l-3.6-6.6z"/>`)),
    gateway: () => (defs(), svg('sg-b sg-lt', W, '<path class="sg-d0" d="M-8 103V50A58 58 0 0 1 108 50V103z"/>') + svg('sg-b sg-dr', W, `<path class="sg-d1" d="M-8 103V50A58 58 0 0 1 108 50V103"/><path class="sg-d2" d="M-1.5 96V50A51.5 51.5 0 0 1 101.5 50V96"/><rect class="sg-sl" x="-14" y="102.4" width="128" height="1.8"/>${star4('sg-ks', [50, -8], 4.2)}${wisp(-3, 48, 7, 0, 1)}${wisp(103, 42, 8.4, -3, -1)}${wisp(3, 34, 6.4, -4.5, -1)}${wisp(97, 36, 7.6, -1.5, 1)}`)),
  });
  Object.assign(_ORN, {
    inferno: sig7(() => svg('o-fv o-fvl', '0 0 24 200', vein(1)) + svg('o-fv o-fvr', '0 0 24 200', vein(2))),
    pumpkin_lantern: sig7(() => svg('o-lt', '0 0 60 78', lantern)),
    cobweb: sig7(() => svg('o-wc o-wcl', '0 0 100 100', `<g class="o-wq"><path class="o-wl" d="${cornerWeb.d}"/>${[[1, 2, 1.3], [2, 4, 1], [3, 1, 1.2], [4, 3, 1.5], [5, 5, 1.1]].map(a => cornerWeb.dew(...a)).join('')}</g>`)
      + svg('o-wc o-wcr', '0 0 100 100', `<g class="o-wq"><path class="o-wl" d="${cornerWeb.d}"/>${[[2, 1, 1.2], [3, 3, 1.4], [1, 4, 1], [4, 2, 1.1]].map(a => cornerWeb.dew(...a)).join('')}</g>`) + svg('o-spd', '0 0 24 64', spider)),
    witch_hour: sig7(() => svg('o-mn', '-26 -26 52 52', '<path d="M11.33-18.86A22 22 0 1 0 11.33 18.86A19 19 0 1 1 11.33-18.86z"/>') + svg('o-wt', '-3 -6 52 36', witch)),
  });
})();
