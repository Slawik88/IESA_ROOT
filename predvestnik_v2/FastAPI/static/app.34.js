// ── Фирменные детали SSS · C (цветение, небо, огни) ─────────────────────────────────────────────
// Продолжение _AP_DECOR и _ORN из app.22.js: разметка слоя фирменной детали (.ap-sig-<id>) и SVG-части образа (_ORN[<skin id>], рисуется на сцене).
// Стили: skin-sig-c-v3.css. Деталь видна с тира SSS (sig_from). Рисунок это вектор: цвета берутся из палитры образа в CSS, а градиент один и тот же белый блик (ornCSheen) в скрытом SVG страницы.
(() => {
  const DEFS = '<svg id="orn-defs-c" width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>'
    + '<linearGradient id="ornCSheen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset=".55" stop-color="#fff" stop-opacity="0"/></linearGradient>'
    + '<mask id="ornCHole" maskUnits="userSpaceOnUse" x="-60" y="-50" width="220" height="220"><rect x="-60" y="-50" width="220" height="220" fill="#fff"/><circle cx="50" cy="50" r="36" fill="#303030"/></mask>'   // дырка под аватар: лепестки не лезут на фото и на созвездие
    + '<radialGradient id="ornCGlow"><stop offset="0" stop-color="#ffb3d1" stop-opacity=".6"/><stop offset="1" stop-color="#ffb3d1" stop-opacity="0"/></radialGradient>'   // мягкое свечение цветка и фонаря без размытия: filter на SVG не везде работает
    + '<clipPath id="ornCDisc"><circle r="10"/></clipPath>'
    + '<g id="ornCBlossom"><path d="M0 0C-3.2-1-4-5-1.9-7L0-6 1.9-7C4-5 3.2-1 0 0z"/><path transform="rotate(72)" d="M0 0C-3.2-1-4-5-1.9-7L0-6 1.9-7C4-5 3.2-1 0 0z"/><path transform="rotate(144)" d="M0 0C-3.2-1-4-5-1.9-7L0-6 1.9-7C4-5 3.2-1 0 0z"/><path transform="rotate(216)" d="M0 0C-3.2-1-4-5-1.9-7L0-6 1.9-7C4-5 3.2-1 0 0z"/><path transform="rotate(288)" d="M0 0C-3.2-1-4-5-1.9-7L0-6 1.9-7C4-5 3.2-1 0 0z"/><circle r="1.5" style="fill:var(--ap-b)"/></g>'
    + '</defs></svg>';
  // витражное крыло (левое; правое это то же, отражённое): перья из трёх вложенных лепестков, синий кончик, золото, светлая сердцевина, свинцовый контур
  const leafD = (L, W) => `M0 0C${-W} ${-L * .3} ${-W * .85} ${-L * .8} 0 ${-L}C${W * .85} ${-L * .8} ${W} ${-L * .3} 0 0z`;
  const wingFeather = (a, L, W) => `<g transform="rotate(${a})">${[1, .72, .44].map((k, i) => `<path class="sr-f${i}" d="${leafD(L * k, W * k)}"/>`).join('')}<path class="sr-sh" d="${leafD(L, W)}"/></g>`;
  const WING = '<g id="ornCWing"><g transform="translate(36 58)">' + [[-76, 46, 9], [-62, 60, 11], [-48, 68, 12.5], [-35, 66, 12], [-22, 56, 11], [-9, 44, 10]].map(f => wingFeather(...f)).join('')
    + [[-70, 28, 7.5], [-54, 36, 8.5], [-38, 36, 8], [-22, 30, 7.5]].map(f => wingFeather(...f)).join('') + '</g></g>';
  const DEFS_ALL = DEFS.replace('</defs>', WING + '</defs>');
  const defs = () => { if (!document.getElementById('orn-defs-c')) document.body.insertAdjacentHTML('beforeend', DEFS_ALL); };
  const SSS = 7;
  const draw = parts => ti => (ti >= SSS ? (defs(), parts) : '');   // деталь одна и видна только на потолке
  const svg = (cls, box, body) => `<svg class="${cls}" viewBox="${box}" aria-hidden="true">${body}</svg>`;

  // ── Бутон Сакуры: голая ветка из угла, тугие бутоны и один раскрывающийся ──
  const bark = (d, w) => `<path class="bd-bk" style="stroke-width:${w}" d="${d}"/><path class="bd-bh" style="stroke-width:${(w * .24).toFixed(1)}" transform="translate(${(-w * .2).toFixed(1)} ${(-w * .22).toFixed(1)})" d="${d}"/>`;
  const bud = (x, y, a, s) => `<g transform="translate(${x} ${y}) rotate(${a}) scale(${s})"><path class="bd-a" d="M0 0C-3.4-1.4-4.2-7 0-12.5 4.2-7 3.4-1.4 0 0z"/><path class="bd-b" d="M0-12.5C4.2-7 3.4-1.4 0 0 1.7-4 1.9-8.4 0-12.5z"/><path class="bd-c" d="M-1.6-4.4C-2-6.8-1-8.8-.3-10.2"/><path class="bd-k" d="M-3.2 1C-2 4.2 2 4.2 3.2 1 2.2-1.9-2.2-1.9-3.2 1z"/></g>`;
  const PET = 'M0 0C-5.2-1.8-6.6-8-3.4-12.6L-1-11 0-11.8 1-11 3.4-12.6C6.6-8 5.2-1.8 0 0z';   // лепесток сакуры с выемкой на конце
  const bloom = `<g transform="translate(140 58) rotate(204) scale(1.6)"><circle class="bd-gl" r="13" cy="-7"/>`
    + `<path class="bd-pl bd-a" style="--r:-34deg" d="${PET}"/><path class="bd-pl bd-a" style="--r:34deg" d="${PET}"/><path class="bd-pl bd-b" style="--r:-12deg" d="${PET}"/><path class="bd-pl bd-b" style="--r:12deg" d="${PET}"/>`
    + `<g class="bd-st"><path d="M-1.6-4V-8.6M0-4V-10M1.6-4V-8.6"/><circle cx="-1.6" cy="-8.8" r=".8"/><circle cx="0" cy="-10.2" r=".8"/><circle cx="1.6" cy="-8.8" r=".8"/></g>`
    + `<path class="bd-a" d="M0 0C-4-1.4-4.6-8.4-2.2-11.4L-.8-10.2 0-10.8.8-10.2 2.2-11.4C4.6-8.4 4-1.4 0 0z"/><path class="bd-c" d="M-2.2-4.6C-2.6-6.8-2.2-8.4-1.6-9.4"/>`
    + `<path class="bd-k" d="M-3.4 1.2C-2 4.6 2 4.6 3.4 1.2 2.4-2-2.4-2-3.4 1.2z"/></g>`;
  const branch = [
    bark('M178-6C158 6 142 16 120 22', 5.4), bark('M120 22C104 28 88 36 74 48', 3.6), bark('M74 48C66 55 60 62 56 72', 2.3),
    bark('M146 14C150 28 148 44 140 58', 2.1), bark('M120 22C116 12 108 6 98 4', 1.9), bark('M96 34C98 46 94 58 88 66', 1.8), bark('M74 48C68 42 62 40 54 41', 1.6),
    bud(98, 4, -66, .95), bud(88, 66, 196, .9), bud(54, 41, -100, .8), bud(56, 72, 202, .85), bloom,
    '<g transform="translate(138 62)"><path class="bd-fall" d="M0 0C3-1 5 2 4 5 2 4-1 2 0 0z"/></g>',
  ].join('');
  Object.assign(_ORN, { sakura_bud: draw(svg('bd-branch', '0 0 170 90', branch)) });
  Object.assign(_AP_DECOR, { budbloom: '' });

  // ── Ханами: облако цветущей кроны над сценой, бумажный фонарь и лепестки, медленно падающие вниз (тушь и васи: приглушённые тона) ──
  const rnd = k => { const x = Math.sin(k * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  const cloud = (cx, cy, rx, ry, n, k0, m = 1) => Array.from({ length: n }, (_, i) => {
    const a = rnd(k0 + i) * 6.283, r = Math.sqrt(rnd(k0 + i + 40)), x = Math.min(384, Math.max(6, cx + Math.cos(a) * r * rx)), y = Math.max(2, cy + Math.sin(a) * r * ry);
    return `<use class="hn-${i % 3 + 1}" href="#ornCBlossom" transform="translate(${x.toFixed(0)} ${y.toFixed(0)}) rotate(${(rnd(k0 + i + 80) * 72).toFixed(0)}) scale(${((.8 + rnd(k0 + i + 120) * .8) * m).toFixed(2)})"/>`;
  }).join('');
  const hnInk = (d, w) => `<path class="hn-ink" style="stroke-width:${w}" d="${d}"/>`;
  const lantern = '<g transform="translate(344 22)"><path class="hn-ink" style="stroke-width:.8" d="M0 0V9"/><g class="hn-sw"><circle class="hn-gl" cx="0" cy="25" r="24"/><rect class="hn-cap" x="-5" y="8" width="10" height="3" rx="1.2"/><rect class="hn-lb" x="-10" y="10" width="20" height="26" rx="9"/><path class="hn-rib" d="M-9.2 17H9.2M-10 23H10M-9.2 29H9.2"/><rect class="hn-cap" x="-5" y="35" width="10" height="3" rx="1.2"/><path class="hn-ink" style="stroke-width:.8" d="M0 38V46"/><circle class="hn-lb" cx="0" cy="47" r="1.8"/></g></g>';
  const petal = (x, y, dx, d, dl) => `<g transform="translate(${x} ${y})"><path class="hn-pt" style="--dx:${dx}px;--d:${d}s;--dl:${dl}s" d="M0 0C3-1.4 6 1.6 5 5 2.6 4.4-1 2.2 0 0z"/></g>`;
  const canopy = '<g class="hn-wash"><circle cx="50" cy="12" r="56"/><circle cx="338" cy="14" r="62"/></g>'
    + hnInk('M-8 16C40 6 92 28 150 10', 2.6) + hnInk('M398 8C350 22 300 10 236 22', 2.8) + hnInk('M60 20C66 34 62 46 54 54', 1.2) + hnInk('M300 18C298 32 302 44 310 50', 1.2) + hnInk('M120 24C128 36 124 44 116 50', 1)
    + cloud(36, 20, 60, 34, 15, 1) + cloud(346, 24, 66, 38, 16, 60) + cloud(190, 1, 92, 3, 6, 130, .6) + cloud(100, 50, 12, 8, 2, 200) + cloud(262, 46, 14, 8, 2, 220)
    + lantern + petal(118, 56, -22, 17, -2) + petal(250, 40, 26, 19, -8) + petal(60, 60, 18, 15, -11) + petal(318, 58, -30, 21, -5) + petal(190, 20, 14, 23, -14);
  Object.assign(_ORN, { hanami: draw(svg('hn-canopy', '0 0 390 130', canopy)) });
  Object.assign(_AP_DECOR, { hanamitree: '' });

  // ── Золотой Лотос: лотос из золотых лепестков под кольцом, блики и круги храмового пруда (рисуется в координатах рамки: 0..100 это кольцо) ──
  const gx = n => +n.toFixed(1);
  const lotusPetal = (a, L, W, cls, fine) => {
    const d = (k = 1) => `M0 0C${gx(-W * .55 * k)} ${gx(-L * .28 * k)} ${gx(-W * .6 * k)} ${gx(-L * .66 * k)} 0 ${gx(-L * k)}C${gx(W * .6 * k)} ${gx(-L * .66 * k)} ${gx(W * .55 * k)} ${gx(-L * .28 * k)} 0 0z`;
    return `<g transform="rotate(${a})"><path class="${cls}" d="${d()}"/>${fine ? `<path class="gl-vn" d="M0-${gx(L * .1)}V-${gx(L * .74)}"/><path class="gl-in" d="${d(.72)}"/>` : ''}<path class="gl-sh" d="${d()}"/></g>`;
  };
  const glint = (x, y, s, d) => `<g transform="translate(${x} ${y})"><path class="gl-sp" style="--s:${s};--d:${d}s" d="M0-5L1.2-1.2 5 0 1.2 1.2 0 5-1.2 1.2-5 0-1.2-1.2z"/></g>`;
  const lotusBack = '<ellipse class="gl-glow" cx="50" cy="96" rx="62" ry="28"/>'
    + [0, 1, 2].map(i => `<ellipse class="gl-rp" style="--i:${i}" cx="50" cy="106" rx="${50 + i * 19}" ry="${10 + i * 4}"/>`).join('')
    + `<g transform="translate(50 108)">${[-72, -50, -28, 28, 50, 72, 0].map(a => lotusPetal(a, 70, 26, 'gl-b', false)).join('')}${[-62, -40, -18, 18, 40, 62].map(a => lotusPetal(a, 62, 24, 'gl-a', true)).join('')}</g>`;
  const lotusFront = `<g transform="translate(50 114)">${[-38, 38, 0].map(a => lotusPetal(a, 34, 17, 'gl-c', true)).join('')}</g>` + glint(-8, 80, 1.5, 3.4) + glint(108, 78, 1.2, 4.6) + glint(50, 108, 1, 5.4) + glint(86, 100, .8, 4);
  Object.assign(_AP_DECOR, {
    goldlotus: () => (defs(), svg('gl-back', '-30 -10 160 130', `<g mask="url(#ornCHole)">${lotusBack}</g>`) + svg('gl-front', '-30 -10 160 130', `<g mask="url(#ornCHole)">${lotusFront}</g>`)),
  });

  // ── Лазурная Обсерватория: латунный телескоп смотрит на планету с кольцом и орбитами; спутник идёт по орбите ──
  const tube = '<g transform="translate(32 80) rotate(-36)"><path class="tl-yk" d="M0 0L-5 15M0 0L5 15"/>'
    + '<rect class="tl-d" x="-14" y="-2.6" width="10" height="5.2" rx="1.4"/><rect class="tl-d" x="-17.5" y="-3.6" width="4.4" height="7.2" rx="1.6"/>'
    + '<rect class="tl-br" x="-4" y="-6" width="40" height="12" rx="2.5"/><rect class="tl-hl" x="-3" y="-5" width="38" height="2.2" rx="1.1"/><rect class="tl-sd" x="-3" y="3.4" width="38" height="2.4" rx="1.2"/>'
    + '<path class="tl-ln" d="M6-6V6M22-6V6"/><rect class="tl-d" x="34" y="-7.6" width="4" height="15.2" rx="1.4"/><rect class="tl-br" x="36" y="-8.4" width="14" height="16.8" rx="2.6"/><rect class="tl-hl" x="37" y="-7.4" width="12" height="2.2" rx="1.1"/>'
    + '<ellipse class="tl-ln2" cx="50.6" cy="0" rx="2.6" ry="7.2"/><rect class="tl-d" x="4" y="-12.8" width="19" height="4.2" rx="1.9"/><rect class="tl-d" x="7" y="-9.2" width="2.2" height="3.4"/><rect class="tl-d" x="17.6" y="-9.2" width="2.2" height="3.4"/>'
    + '<circle class="tl-d" r="3.6"/><circle class="tl-hl2" r="1.2"/></g>';
  const planet = '<g transform="translate(104 28) rotate(-20)"><path class="tl-rg" d="M-20 0A20 5.4 0 0 1 20 0"/><g transform="rotate(20)"><circle class="tl-pl" r="10"/><circle class="tl-pd" cx="5" cy="4" r="11" clip-path="url(#ornCDisc)"/><path class="tl-pb" d="M-8.2-5.6A10 10 0 0 1 2-9.8"/></g><path class="tl-rg tl-rf" d="M-20 0A20 5.4 0 0 0 20 0"/>'
    + '<ellipse class="tl-or" rx="36" ry="11"/><ellipse class="tl-or tl-o2" rx="52" ry="16"/><g transform="scale(1 .305)"><g class="tl-mn"><g transform="translate(36 0) scale(1 3.28)"><circle class="tl-mo" r="2.5"/></g></g></g></g>';
  const star = (x, y, r, d) => `<circle class="tl-s" style="--d:${d}s" cx="${x}" cy="${y}" r="${r}"/>`;
  const scope = '<path class="tl-ray" d="M76 49L92 38"/>' + planet + tube + '<path class="tl-ln" d="M32 80V95"/><path class="tl-ft" d="M22 97H42"/>'
    + star(132, 62, 1, 3.1) + star(142, 44, 1.3, 4.3) + star(80, 12, 1.1, 3.7) + star(58, 30, .9, 5.1) + star(140, 84, 1, 4.7) + star(112, 76, .9, 3.3);
  Object.assign(_ORN, { observatory: draw(svg('tl-scope', '0 0 150 100', scope)) });
  Object.assign(_AP_DECOR, { telescope: '' });

  // ── Огни Гирлянды: провисший провод с цветными лампочками по верху сцены и короткая нитка вокруг кольца; огни бегут по цепочке (только opacity) ──
  const bulb = (x, y, r, i, k, z = 1) => `<g transform="translate(${x} ${y}) rotate(${r}) scale(${z})"><g class="fl-b fl-${k}" style="--i:${i}"><circle class="fl-g" cy="5.4" r="6.6"/><rect class="fl-sk" x="-1.7" y="0" width="3.4" height="2.8" rx=".8"/><path class="fl-bl" d="M-2.5 2.6C-3.7 5-3.3 8.4 0 9.4 3.3 8.4 3.7 5 2.5 2.6z"/><ellipse class="fl-hi" cx="-.9" cy="5.2" rx=".7" ry="1.6"/></g></g>`;
  const swag = (x0, x1, sag, k0, n, count) => {   // провод провисает по параболе, лампочки висят вниз; по краям провис глубже, над ником мелкий
    const mid = (x0 + x1) / 2, pts = Array.from({ length: count }, (_, j) => { const t = (j + 1) / (count + 1), u = 1 - t; return [u * u * x0 + 2 * u * t * mid + t * t * x1, u * u * 3 + 2 * u * t * (3 + sag * 2) + t * t * 3]; });
    return `<path class="fl-w" d="M${x0} 3Q${mid} ${3 + sag * 2} ${x1} 3"/>` + pts.map((q, j) => bulb(q[0].toFixed(1), q[1].toFixed(1), 0, n + j, (k0 + j) % 3 + 1, 1.2)).join('');
  };
  const swags = swag(-4, 104, 22, 0, 0, 3) + swag(104, 288, 6, 0, 3, 4) + swag(288, 394, 22, 1, 7, 3);
  const ringLights = () => {
    const ang = [-160, -138, -116, -94, -72, -50, -28], at = a => [50 + 57 * Math.cos(a * Math.PI / 180), 50 + 57 * Math.sin(a * Math.PI / 180)].map(n => n.toFixed(1));
    const [x0, y0] = at(-172), [x1, y1] = at(-16);
    return `<path class="fl-w" d="M${x0} ${y0}A57 57 0 0 1 ${x1} ${y1}"/>` + ang.map((a, j) => { const [x, y] = at(a); return bulb(x, y, a - 90, j, j % 3 + 1); }).join('');
  };
  Object.assign(_ORN, { garland: draw(svg('fl-swags', '0 0 390 48', swags)) });
  Object.assign(_AP_DECOR, { fairylights: () => (defs(), svg('fl-ring', '-12 -12 124 124', ringLights())) });

  // ── Бой Курантов: циферблат на полночь, качающийся колокол на кронштейне и золотые салюты по краям (колокол качается, салют вспыхивает: transform и opacity) ──
  const ticks = Array.from({ length: 12 }, (_, k) => { const a = k * Math.PI / 6, r0 = k % 3 ? 17.4 : 15.4; return `M${(Math.sin(a) * r0).toFixed(1)} ${(-Math.cos(a) * r0).toFixed(1)}L${(Math.sin(a) * 19.4).toFixed(1)} ${(-Math.cos(a) * 19.4).toFixed(1)}`; }).join('');
  const clock = `<g transform="translate(76 28)"><circle class="bc-fc" r="24"/><circle class="bc-bz" r="24"/><circle class="bc-bz2" r="20.6"/><path class="bc-tk" d="${ticks}"/><path class="bc-dm" d="M0-14.4l1.9 2.3L0-9.8l-1.9-2.3z"/><path class="bc-hm" d="M0 2.5V-15.6"/><path class="bc-hh" d="M0 2.5L-1.7-10"/><circle class="bc-hub" r="2.2"/></g>`;
  const bell = '<g transform="translate(18 13)"><g class="bc-bell"><path class="bc-bd" d="M-4.5 2C-4.5-.6 4.5-.6 4.5 2 8 6 9 15 12 21 13.2 23.4 15 24.4 16 26H-16C-15 24.4-13.2 23.4-12 21-9 15-8 6-4.5 2z"/><path class="bc-bs" d="M4.5 2C8 6 9 15 12 21 13.2 23.4 15 24.4 16 26H5C6.4 20 6.4 8 4.5 2z"/><path class="bc-bh" d="M-6.4 6.4C-7.8 11.4-8.8 15.6-10.8 20"/><rect class="bc-lp" x="-17" y="25.2" width="34" height="3.6" rx="1.8"/><circle class="bc-lo" cy="-2.2" r="2.2"/><g class="bc-cl"><path class="bc-cn" d="M0 8V29"/><circle class="bc-cb" cy="30.6" r="2.8"/></g></g></g>';
  const burst = (cx, cy, r, k, dl) => `<g transform="translate(${cx} ${cy})"><g class="bc-fw" style="--dl:${dl}s"><circle class="bc-d1" r="2.2"/>${Array.from({ length: 12 }, (_, j) => {
    const a = (j * 30 + k * 11) * Math.PI / 180, c = Math.cos(a), n = Math.sin(a), f = v => (v).toFixed(1);
    return `<path class="bc-r${j % 3}" d="M${f(c * r * .4)} ${f(n * r * .4)}L${f(c * r * .8)} ${f(n * r * .8)}"/><circle class="bc-d${j % 3}" cx="${f(c * r)}" cy="${f(n * r)}" r="${j % 2 ? 1 : 1.6}"/>`;
  }).join('')}</g></g>`;
  const arm = '<rect class="bc-ar" x="4" y="10.4" width="52" height="3.2" rx="1.6"/><path class="bc-br" d="M44 13.6L56 25"/>';
  const waves = '<g class="bc-wv"><path d="M38 18Q41 27 38 36"/><path d="M43 15Q48 27 43 39"/></g>';
  Object.assign(_ORN, {
    midnight_chimes: draw(svg('bc-clock', '0 0 104 66', arm + clock + waves + bell) + svg('bc-fw1', '0 0 110 80', burst(34, 34, 28, 0, 0) + burst(86, 16, 13, 1, -3.4)) + svg('bc-fw2', '0 0 60 60', burst(30, 30, 16, 2, -5.2))),
  });
  Object.assign(_AP_DECOR, { bellchimes: '' });

  // ── Небесное Сияние: витражные крылья за кольцом, тонкий золотой нимб над ним, перо падает вниз ──
  const feather = (x, y, d, dl, dx) => `<g transform="translate(${x} ${y})"><g class="sr-fd" style="--d:${d}s;--dl:${dl}s;--dx:${dx}px"><path class="sr-fe" d="M0 0C2.6-3 3-9 0-15-3-9-2.6-3 0 0z"/><path class="sr-q" d="M0 1V-12"/></g></g>`;
  const seraphBack = '<g mask="url(#ornCHole)"><use class="sr-w" href="#ornCWing"/><g transform="translate(100 0) scale(-1 1)"><use class="sr-w" href="#ornCWing"/></g></g>'
    + feather(-8, 44, 16, -3, 10) + feather(108, 56, 19, -9, -12) + feather(14, 82, 22, -13, 8);
  const seraphHalo = '<g transform="translate(50 -15) rotate(-6)"><ellipse class="sr-h0" rx="24" ry="6.4"/><ellipse class="sr-h1" rx="20.5" ry="5.2"/><g transform="translate(24 0)"><path class="sr-sp" d="M0-6L1.4-1.4 6 0 1.4 1.4 0 6-1.4 1.4-6 0-1.4-1.4z"/></g></g>';
  Object.assign(_AP_DECOR, { seraph: () => (defs(), svg('sr-back', '-30 -10 160 130', seraphBack) + svg('sr-halo', '-30 -40 160 100', seraphHalo)) });
})();
