// ── Фирменные детали SSS · A (природа и вода) ─────────────────────────────────────────────
// Продолжение _AP_DECOR из app.22.js: разметка слоя фирменной детали (.ap-sig-<id>), SVG, привязанный к рамке аватара. Стили: skin-sig-a-v3.css. Деталь видна с тира SSS (sig_from).
// Рисунок в единицах рамки: 0..100 это сама рамка (центр 50,50; внешнее кольцо ≈ 57), холст -30..130, поэтому он масштабируется вместе с аватаром
// (76 px в профиле, ~100 в карточке и витрине). Под ником остаётся меньше 8 единиц: низ рисунка держится у кольца.
// Градиенты строятся в каждой копии со своими id и красятся палитрой образа (var(--ap-a/b/c)); цвет и движение задаёт CSS, здесь только форма. Ничего не берётся из данных игрока.
(() => {
  const R = n => Math.round(n * 10) / 10;
  const pt = (r, deg, c = 50) => [R(c + r * Math.cos(deg * Math.PI / 180)), R(c + r * Math.sin(deg * Math.PI / 180))];
  const col = k => (k.length === 1 ? `var(--ap-${k})` : k);
  const H = 'x1="0" y1="0" x2="1" y2="0"', RAD = 'cx=".5" cy=".5" r=".5"', DIAG = 'x1="0" y1="0" x2="1" y2="1"';
  const SPARK = 'M0-1L.27-.27L1 0L.27.27L0 1L-.27.27L-1 0L-.27-.27Z';
  const spark = (x, y, s, cls, d) => `<g transform="translate(${x} ${y}) scale(${s})"><path class="${cls}" style="--d:${d}s" d="${SPARK}"/></g>`;
  let seq = 0;
  const art = (name, fn) => () => {
    const defs = [];
    const g = (stops, attrs = 'x1="0" y1="0" x2="0" y2="1"', tag = attrs.startsWith('cx') ? 'radialGradient' : 'linearGradient') => {
      const id = `sa${++seq}`;
      defs.push(`<${tag} id="${id}" ${attrs}>${stops.map(([o, c, a = 1]) => `<stop offset="${o}" style="stop-color:${col(c)};stop-opacity:${a}"/>`).join('')}</${tag}>`);
      return `url(#${id})`;
    };
    const body = fn(g, d => defs.push(d)), svg = (cls, inner) => `<svg class="sa sa-${name}${cls}" viewBox="-30 -30 160 160" aria-hidden="true">${inner}</svg>`;
    return Array.isArray(body) ? svg(' sa-b', `<defs>${defs.join('')}</defs>${body[0]}`) + svg('', body[1]) : svg('', `<defs>${defs.join('')}</defs>${body}`);   // [за кольцом, поверх кольца]
  };
  const arc = (r, a0, a1, big = 0) => `M${pt(r, a0)}A${r} ${r} 0 ${big} 1 ${pt(r, a1)}`;

  // ── Лесной Странник: свод листвы над кольцом, роса на листьях, светлячки ───────────────────────────────
  const LEAF = 'M0 0C.15-.55.7-.62 1 0C.7.55.15.5 0 0Z';
  const canopy = art('canopy', g => {
    const deep = g([[0, 'b', .95], [1, 'b', .7]], H), mid = g([[0, 'b'], [.55, 'a', .92], [1, 'a', .7]], H), lite = g([[0, 'b'], [.4, 'a'], [1, 'c']], H), glow = g([[0, '#f8ffd2', 1], [.3, 'a', .8], [1, 'a', 0]], RAD);
    const leaf = (r, ang, L, tilt, fill, rich) => {
      const [x, y] = pt(r, ang), k = Math.abs(Math.sin((ang - 140) * Math.PI / 260)) ** .6;   // у концов свода листья лежат вдоль кольца: сбоку от аватара места мало
      return `<g transform="translate(${x} ${y}) rotate(${R(ang + (ang < 270 ? 90 - tilt * k : tilt * k - 90))}) scale(${R(L)})"><path d="${LEAF}" fill="${fill}"/>${rich ? '<path class="s-hl" d="M0 0C.15-.55.7-.62 1 0L.1 0Z"/><path class="s-rib" d="M0 0L.9 0"/>' : ''}</g>`;
    };
    const row = (n, off, r, tilt, base, amp, fill, rich) => Array.from({ length: n }, (_, i) => {
      const t = (i + off) / (off ? n : n - 1);
      return leaf(r, 156 + 228 * t, base + amp * Math.sin(Math.PI * t) ** 1.1, tilt, fill, rich);
    }).join('');
    const drop = ([x, y]) => `<g class="sa-dew" transform="translate(${x} ${y})"><ellipse rx="1.5" ry="1.5"/><ellipse class="s-sp" cx="-.5" cy="-.5" rx=".5" ry=".5"/></g>`;
    const fly = (x, y, d, dl) => `<g transform="translate(${x} ${y})"><g class="sa-ff" style="--d:${d}s;--dl:${dl}s"><ellipse rx="8.5" ry="8.5" fill="${glow}"/><ellipse class="s-core" rx="1.5" ry="1.5"/></g></g>`;
    return `<g class="sa-back"><path class="s-twig" d="${arc(57, 156, 384, 1)}"/>${row(11, 0, 59, 62, 10, 24, deep, false)}</g>`
      + `<g class="sa-front">${row(11, .5, 58, 38, 8, 18, mid, true)}${row(9, .5, 57, 14, 6, 11, lite, true)}${[pt(68, 222), pt(72, 292), pt(64, 346), pt(62, 176)].map(drop).join('')}</g>`
      + fly(-8, 26, 6, 0) + fly(108, 8, 7.5, -2.5) + fly(110, 100, 5.5, -4);
  });

  // ── Песчаная Тропа: гряды дюн за кольцом, низкое солнце за гребнем, ленты ветра и марево над кольцом ──────
  const dunes = art('dunes', (g, put) => {
    const far = g([[0, 'a', .95], [.28, 'b', .5], [.5, 'b', 0]]), near = g([[0, 'b', .95], [.2, 'b', .5], [.42, 'b', 0]]), crest = g([[0, 'c', .95], [.7, 'c', .8], [1, 'c', 0]]);
    const sun = g([[0, '#fff'], [.45, 'c'], [1, 'a']], RAD), halo = g([[0, 'a', .6], [1, 'a', 0]], RAD), wind = g([[0, 'c', 0], [.2, 'c', .95], [.75, 'a', .9], [1, 'a', 0]], H);
    const mk = `sam${++seq}`, cp = `sac${++seq}`;
    put(`<mask id="${mk}" maskUnits="userSpaceOnUse" x="-30" y="-30" width="160" height="160"><rect x="-30" y="-30" width="160" height="160" fill="${g([[.05, '#000'], [.28, '#fff'], [.72, '#fff'], [.95, '#000']], H)}"/></mask>`);
    put(`<clipPath id="${cp}"><path clip-rule="evenodd" d="M-30-30H130V130H-30ZM50 3A47 47 0 1 0 50.01 3Z"/></clipPath>`);   // внутри внутреннего кольца рисунка нет: аватар без фото прозрачен
    const rays = Array.from({ length: 7 }, (_, i) => { const a = -172 + i * 27, [x1, y1] = pt(13, a, 0), [x2, y2] = pt(i % 2 ? 18 : 22, a, 0); return `M${x1} ${y1}L${x2} ${y2}`; }).join('');
    const FAR = 'M-30 92C-18 82-6 82 8 88C20 94 30 100 46 102C60 103 74 98 90 90C102 84 118 82 130 90', NEAR = 'M-30 104C-10 98 8 100 26 106C40 110 54 111 66 108C84 104 100 96 114 98C122 99 126 101 130 103';
    const ripple = 'M-14 98C-6 95 4 96 12 100M96 94C104 91 114 91 124 96M32 109C40 111 52 111 62 109';
    const ribbon = (d, cls) => `<path class="s-wind sa-rb ${cls}" fill="${wind}" d="${d}"/>`;
    return [`<g clip-path="url(#${cp})"><ellipse cx="106" cy="86" rx="24" ry="24" fill="${halo}"/><g class="sa-sun" transform="translate(106 86)"><path class="s-rays" d="${rays}"/><circle r="10" fill="${sun}"/></g><g mask="url(#${mk})">`
      + `<path d="${FAR}V132H-30Z" fill="${far}"/><path class="s-crest" stroke="${crest}" d="${FAR}"/><path d="${NEAR}V132H-30Z" fill="${near}"/><path class="s-crest s-crest2" stroke="${crest}" d="${NEAR}"/><path class="s-ripl" d="${ripple}"/></g></g>`,
      ribbon('M-26 44C-12 14 26-14 62-12C92-10 112 6 122 28C112 10 92-6 62-9C28-11-8 16-26 44Z', 'sa-rb1') + ribbon('M-10 22C6 2 34-8 56-6C40-6 14 6-10 22Z', 'sa-rb2')
      + `<g class="sa-heat"><path class="s-heat" d="M102 70q2.5-2 5 0t5 0t5 0"/><path class="s-heat" d="M104 63q2.5-2 5 0t5 0"/></g>`
      + [[10, 14, 1.1, 3.4], [44, -14, .8, 4.6], [90, -6, 1, 3.9], [112, 40, .9, 5.2]].map(([x, y, r, d]) => `<circle class="s-grain" style="--d:${d}s" cx="${x}" cy="${y}" r="${r}"/>`).join('')];
  });

  // ── Тихая Гавань: маяк с вращающимся лучом, причальный канат вокруг рамки, круги на воде ────────────────
  const lighthouse = art('lighthouse', g => {
    const wall = g([[0, 'c'], [.55, 'a'], [1, 'b']], H), beam = g([[0, 'c', .8], [1, 'c', 0]], 'x1="1" y1="0" x2="0" y2="0"'), lamp = g([[0, '#fff', .95], [.35, 'c', .6], [1, 'c', 0]], RAD);
    const rope = pt(60.5, 128);
    return `<g transform="translate(106 1)"><g class="sa-beam"><path class="s-beam" fill="${beam}" d="M0 0L-132-30V30Z"/><path class="s-beam" fill="${beam}" d="M0 0L-132-9V9Z"/></g><circle class="sa-lamp" r="9" fill="${lamp}"/></g>`
      + `<circle class="s-rope" cx="50" cy="50" r="60.5"/><circle class="s-twist" cx="50" cy="50" r="60.5"/><circle class="s-rl" cx="50" cy="50" r="59.6"/><circle class="s-rd" cx="50" cy="50" r="61.5"/>`
      + `<g transform="translate(${rope})"><g class="sa-sway"><path class="s-rope s-tail" d="M-.5 1C-3 7-1.5 12-3.5 17"/><path class="s-rope s-tail" d="M1.5 1C4 6 3 10 5 13"/></g><path class="s-loop" d="M0 0C-6-6-9 2-4 3.2C-1.5 3.8 0 1.5 0 0ZM0 0C6-6 9 2 4 3.2C1.5 3.8 0 1.5 0 0Z"/><circle class="s-knot" r="2.1"/></g>`
      + `<g transform="translate(106 30)"><path class="s-rock" d="M-10 5Q-6-3-3-2Q3-5 9 5Z"/><path d="M-5 0L-3.2-24H3.2L5 0Z" fill="${wall}"/><path class="s-band" d="M-4.4-7L-4-11H4L4.4-7ZM-3.8-16L-3.5-20H3.5L3.8-16Z"/>`
      + `<rect class="s-rail" x="-4.8" y="-26.2" width="9.6" height="2" rx=".6"/><rect class="s-room" x="-2.8" y="-32.2" width="5.6" height="6" rx="1"/><path class="s-roof" d="M-4-32.2L0-37.4L4-32.2Z"/></g>`
      + `<ellipse class="s-ripple" cx="50" cy="110.5" rx="30" ry="2.6"/><ellipse class="sa-rip s-ripple" cx="50" cy="110.5" rx="30" ry="2.6"/><ellipse class="sa-rip sa-rip2 s-ripple" cx="50" cy="110.5" rx="30" ry="2.6"/>`;
  });

  // ── Пруд Лотосов: кувшинки с росой на воде у кольца, один бутон на стебле ──────────────────────────────
  const lilypads = art('lilypads', g => {
    const padG = g([[0, 'a'], [.65, 'b'], [1, 'b', .92]], 'cx=".38" cy=".34" r=".75"', 'radialGradient');
    const bud = g([[0, '#fff', .92], [.4, 'c'], [1, 'c', .8]]), side = g([[0, 'c', .55], [1, 'c']]);
    const veins = Array.from({ length: 9 }, (_, i) => { const a = (-30 + i * 40) * Math.PI / 180; return `M0 0L${R(.92 * Math.cos(a) * 100) / 100} ${R(.92 * Math.sin(a) * 100) / 100}`; }).join('');
    const pad = (x, y, rx, rot, cls) => `<g transform="translate(${x} ${y})"><g class="sa-pad ${cls}"><g transform="scale(1 .4) rotate(${rot}) scale(${rx})"><path class="s-pad" fill="${padG}" d="M0 0L.707-.707A1 1 0 1 1 .259-.966Z"/><path class="s-vein" d="${veins}"/></g></g></g>`;
    const drop = (x, y) => `<g class="sa-dew" transform="translate(${x} ${y})"><ellipse rx="1.5" ry="1.5"/><ellipse class="s-sp" cx="-.5" cy="-.5" rx=".5" ry=".5"/></g>`;
    return `<ellipse class="sa-rip s-ripple" cx="-3" cy="93" rx="17" ry="6.8"/><ellipse class="sa-rip sa-rip2 s-ripple" cx="95" cy="97" rx="16" ry="6.4"/>`
      + pad(-3, 93, 17, 20, 'sa-pa') + pad(95, 97, 16, 200, 'sa-pb') + pad(-11, 38, 8, 100, 'sa-pc') + pad(109, 108, 6, 250, 'sa-pc') + drop(-1, 92) + drop(-9, 94) + drop(98, 97) + drop(-12, 38)
      + `<path class="s-stem" d="M95 95C99 88 108 84 106 70"/><g transform="translate(106 70) scale(1.12)"><g class="sa-bud"><path class="s-sepal" d="M0 1C-5 0-7-5-6-8C-3-5-1-3 0 1ZM0 1C5 0 7-5 6-8C3-5 1-3 0 1Z"/>`
      + `<path d="M0 0C-8-2-9-13-3.5-18C-3-10-1.5-4 0 0ZM0 0C8-2 9-13 3.5-18C3-10 1.5-4 0 0Z" fill="${side}"/><path d="M0 0C-4.5-5-4.5-15 0-22C4.5-15 4.5-5 0 0Z" fill="${bud}"/><path class="s-gloss" d="M-1.6-4C-2.3-9-1.5-14 0-18"/></g></g>`;
  });

  // ── Изморозь: ледяные друзы и звёздочки инея растут по рамке, большая снежинка, блики ───────────────────
  const rime = art('rime', g => {
    const shard = g([[0, '#fff', .95], [1, 'a', .65]]), edge = g([[0, 'c', .8], [.65, 'c', .35], [1, 'c', 0]]);
    const spike = (L, w) => `<path fill="${shard}" d="M${-w} 0L${R(-w * .75)} ${R(-L * .72)}L0 ${-L}L${R(w * .75)} ${R(-L * .72)}L${w} 0Z"/><path class="s-facet" d="M0 0V${-L}"/>`;
    const druse = (ang, L) => { const [x, y] = pt(57.5, ang); return `<g transform="translate(${x} ${y}) rotate(${ang + 90})"><g transform="rotate(-24)">${spike(L * .62, 1.5)}</g><g transform="rotate(22)">${spike(L * .7, 1.6)}</g>${spike(L, 2.2)}</g>`; };
    const arm = len => `<path d="M0 0V-${len}M0-${R(len * .45)}L-3.2-${R(len * .45 + 3)}M0-${R(len * .45)}L3.2-${R(len * .45 + 3)}M0-${R(len * .72)}L-2.2-${R(len * .72 + 2.2)}M0-${R(len * .72)}L2.2-${R(len * .72 + 2.2)}"/>`;
    const star = (len, k = 1) => [0, 60, 120, 180, 240, 300].map(a => `<g transform="rotate(${a}) scale(${k})">${arm(len)}</g>`).join('');
    const mini = (ang, r) => { const [x, y] = pt(r, ang), arms = star(5, .8); return `<g transform="translate(${x} ${y}) rotate(${ang})"><g class="s-gl">${arms}</g><g class="s-ice">${arms}</g></g>`; };
    const ring = Array.from({ length: 12 }, (_, i) => pt(60, i * 30)).map(p => p.join(' ')).join('L');
    return `<path class="s-poly" stroke="${edge}" d="M${ring}Z"/>` + [[168, 10], [192, 13], [214, 11], [238, 17], [262, 12], [284, 10], [346, 12], [6, 14], [24, 10]].map(([a, L]) => druse(a, L)).join('')
      + [[180, 67], [226, 69], [250, 70], [272, 68], [356, 66], [15, 68]].map(([a, r]) => mini(a, r)).join('')
      + `<g transform="translate(103 -5)"><g class="sa-flake"><g class="s-gl">${star(12)}</g><g class="s-ice">${star(12)}</g><circle class="s-core" r="1.7"/></g></g>`
      + spark(-8, 16, 4, 's-glint', 3.4) + spark(114, 40, 3, 's-glint sg2', 4.6) + spark(30, -19, 3.6, 's-glint sg3', 3.9) + spark(76, -22, 2.4, 's-glint sg4', 5.2);
  });

  // ── Снежный Шар: стеклянный купол с бликом, городок на снегу, снег кружит у стекла ──────────────────────
  const snowdome = art('snowdome', g => {
    const glass = g([[0, '#fff', .16], [.62, '#fff', .02], [1, 'a', .14]], 'cx=".4" cy=".34" r=".7"', 'radialGradient'), rim = g([[0, '#fff', .98], [.5, 'a', .55], [1, 'b', .75]], DIAG);
    const snow = g([[0, '#fff', .96], [.55, 'a', .6], [1, 'a', .1]]);
    const Y = 103, half = Math.sqrt(62 * 62 - (Y - 50) ** 2);
    const house = (x, w, h, lit) => `<path class="s-town" d="M${x} ${Y}V${R(Y - h)}L${R(x + w / 2)} ${R(Y - h - w * .62)}L${R(x + w)} ${R(Y - h)}V${Y}Z"/><path class="s-cap" d="M${R(x - .6)} ${R(Y - h + .5)}L${R(x + w / 2)} ${R(Y - h - w * .62 - .5)}L${R(x + w + .6)} ${R(Y - h + .5)}Q${R(x + w / 2)} ${R(Y - h - .8)} ${R(x - .6)} ${R(Y - h + .5)}Z"/>${lit ? `<rect class="s-win" x="${R(x + w / 2 - .9)}" y="${R(Y - h * .72)}" width="1.8" height="2.1"/>` : ''}`;
    const flake = ([a, r, s]) => { const [x, y] = pt(r, a); return `<ellipse cx="${x}" cy="${y}" rx="${s}" ry="${s}"/>`; };
    return `<circle cx="50" cy="50" r="62" fill="${glass}"/><circle class="s-rim" cx="50" cy="50" r="62" stroke="${rim}"/>`
      + `<path fill="${snow}" d="M${R(50 - half)} ${Y}H${R(50 + half)}A62 62 0 0 1 ${R(50 - half)} ${Y}Z"/>`
      + `<g class="sa-town">${house(16, 7, 6.2, 1)}${house(23.6, 7.4, 8.6, 1)}${house(31.6, 5.6, 4.8, 0)}${house(64, 6.4, 5.4, 0)}${house(70.8, 6, 9, 1)}<path class="s-town" d="M78.4 ${Y}V${Y - 11}L80.4 ${Y - 18.6}L82.4 ${Y - 11}V${Y}Z"/><path class="s-cap" d="M77.9 ${Y - 10.4}L80.4 ${Y - 19.4}L82.9 ${Y - 10.4}Q80.4 ${Y - 11.8} 77.9 ${Y - 10.4}Z"/><rect class="s-win" x="79.6" y="${Y - 7}" width="1.6" height="2"/></g>`
      + `<path class="s-glare" d="M${pt(59.5, 194)}A59.5 59.5 0 0 1 ${pt(59.5, 266)}A47 47 0 0 0 ${pt(59.5, 194)}Z"/><path class="s-glare s-glare2" d="${arc(59.5, 280, 298)}"/><path class="s-glare s-glare3" d="${arc(59.5, 18, 48)}"/>`
      + `<path class="s-collar" d="${arc(62, 66, 114)}"/>`
      + `<g class="sa-fl1 s-flake">${[[200, 59.5, 1.4], [262, 60, 1.1], [318, 59, 1.5], [24, 60, 1], [150, 59.5, 1.1]].map(flake).join('')}</g><g class="sa-fl2 s-flake">${[[232, 59.5, 1.1], [350, 60, 1.3], [100, 60.5, 1]].map(flake).join('')}</g>`;
  });

  // ── Нефритовый Двор: резной нефритовый би с решётчатыми окнами, золотые кромки, лаковый блик и золотая пыль ──
  const jadecourt = art('jadecourt', g => {
    const body = g([[0, 'a'], [.5, 'b'], [1, 'b', .5]], DIAG);
    const circle = r => `M${50 + r} 50A${r} ${r} 0 1 0 ${50 - r} 50A${r} ${r} 0 1 0 ${50 + r} 50Z`, RO = 66, RI = 57.5, RM = (RO + RI) / 2;
    const holes = Array.from({ length: 16 }, (_, i) => { const a = i * 22.5 + 11.25; return `M${pt(RI + 1.4, a)}L${pt(RM, a + 3)}L${pt(RO - 1.4, a)}L${pt(RM, a - 3)}Z`; }).join('');
    const studs = Array.from({ length: 16 }, (_, i) => { const [x, y] = pt(RM, i * 22.5); return `<ellipse cx="${x}" cy="${y}" rx=".85" ry=".85"/>`; }).join('');
    return `<path fill="${body}" fill-rule="evenodd" d="${circle(RO)}${circle(RI)}${holes}"/><circle class="s-edge" cx="50" cy="50" r="${RO}"/><circle class="s-edge" cx="50" cy="50" r="${RI}"/><g class="s-stud">${studs}</g>`
      + `<path class="s-lacq" d="${arc(RM, 192, 246)}"/><path class="s-lacq s-lacq2" d="${arc(RM, 256, 268)}"/><g class="sa-glint"><path class="s-lacq s-sweep" d="${arc(RM, -12, 20)}"/></g>`
      + spark(-12, 14, 2.8, 's-gold', 3.2) + spark(114, 22, 2.2, 's-gold sg2', 4.1) + spark(110, 90, 2.6, 's-gold sg3', 3.6) + spark(-10, 84, 1.8, 's-gold sg4', 4.8) + spark(66, -18, 2, 's-gold sg5', 3.9)
      + [[-6, 4], [116, 62], [22, -14], [112, 2], [-14, 56], [92, -10], [8, 100], [96, 112]].map(([x, y]) => `<circle class="s-dust" cx="${x}" cy="${y}" r=".7"/>`).join('');
  });

  Object.assign(_AP_DECOR, { canopy: canopy, dunes: dunes, lighthouse: lighthouse, lilypads: lilypads, rime: rime, snowdome: snowdome, jadecourt: jadecourt });
})();
