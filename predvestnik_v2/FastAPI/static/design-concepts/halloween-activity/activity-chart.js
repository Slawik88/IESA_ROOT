/* HwActivity — рендер «Активности по сообщениям» без библиотек.
   Тот же файл кладётся в проект как отдельная часть бандла (app.NN.js).
   Вход: точки [{d:'YYYY-MM-DD', n:int}] по возрастанию даты.
   Выход: SVG внутри контейнера + тултип при наведении/тапе. */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
  const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

  function el(name, attrs) {
    const node = document.createElementNS(NS, name);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    return node;
  }
  function fmt(d) {
    const p = String(d).split('-');
    return p[2] + '.' + p[1];
  }
  function dayInfo(d) {
    const dt = new Date(String(d) + 'T00:00:00');
    return WEEKDAYS[dt.getDay()] + ', ' + Number(String(d).split('-')[2]) + ' ' + MONTHS[dt.getMonth()];
  }
  function niceMax(v) {
    if (v <= 5) return Math.max(5, v);
    const pow = Math.pow(10, Math.floor(Math.log10(v)));
    const steps = [1, 2, 2.5, 5, 10];
    for (const s of steps) if (v <= s * pow) return Math.ceil(s * pow);
    return Math.ceil(v / pow) * pow;
  }
  function gradient(defs, id, from, to) {
    const g = el('linearGradient', { id: id, x1: '0', y1: '1', x2: '0', y2: '0' });
    g.append(el('stop', { offset: '0', 'stop-color': from }), el('stop', { offset: '1', 'stop-color': to }));
    defs.append(g);
    return 'url(#' + id + ')';
  }
  function movingAvg(points, window) {
    return points.map((_, i) => {
      const slice = points.slice(Math.max(0, i - window + 1), i + 1);
      return slice.reduce((s, p) => s + p.n, 0) / slice.length;
    });
  }

  /* ── полосы ─────────────────────────────────────────────────────────── */
  function drawBars(svg, plot, tip, points, ctx) {
    const W = Math.max(280, plot.clientWidth || 360), H = 186;
    const padL = 24, padR = 8, padT = 18, padB = 20;
    const iw = W - padL - padR, ih = H - padT - padB;
    const n = points.length;
    const max = niceMax(Math.max(1, ...points.map(p => p.n)));
    const slot = iw / n, gap = Math.min(2.6, slot * 0.26);
    const barW = Math.max(1.6, slot - gap);
    const y = v => padT + ih - (v / max) * ih;
    const defs = el('defs');
    const barFill = gradient(defs, 'hwg' + ctx.uid, 'var(--bar-2)', 'var(--bar-1)');
    const todayFill = gradient(defs, 'hwt' + ctx.uid, '#4d7c1b', '#b6ff4d');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('height', H + 'px');
    svg.append(defs);

    const peak = points.reduce((a, b) => (b.n > a.n ? b : a), points[0]);
    [0, max / 2, max].forEach(v => {
      const gy = y(v);
      svg.append(el('line', { x1: padL, y1: gy, x2: W - padR, y2: gy, stroke: 'rgba(255,255,255,.07)',
        'stroke-width': 1, 'stroke-dasharray': v === 0 ? '' : '3 5' }));
      const t = el('text', { x: padL - 6, y: gy + 3, 'text-anchor': 'end', fill: 'var(--muted)', 'font-size': 9 });
      t.textContent = Math.round(v);
      svg.append(t);
    });

    const labelEvery = n <= 14 ? 1 : n <= 31 ? 5 : n <= 100 ? 15 : 30;
    const todayKey = points[n - 1].d;
    points.forEach((p, i) => {
      const isToday = p.d === todayKey;
      const isPeak = p === peak && p.n > 0 && !isToday;
      const cx = padL + slot * i + gap / 2;
      const top = y(p.n);
      const r = el('rect', {
        x: cx.toFixed(2), y: top.toFixed(2), width: barW.toFixed(2), height: Math.max(1, (padT + ih - top)).toFixed(2),
        rx: Math.min(barW / 2, 2.6), fill: isToday ? todayFill : barFill,
        class: 'hw-bar' + (isToday ? ' is-today' : ''), 'data-i': i, 'data-top': top.toFixed(1),
      });
      if (isToday) r.setAttribute('filter', 'url(#' + ctx.glow + ')');
      const hit = el('rect', { x: (padL + slot * i).toFixed(2), y: padT, width: slot.toFixed(2), height: ih,
        fill: 'transparent', 'data-i': i, 'data-top': top.toFixed(1), tabindex: '-1' });
      svg.append(hit, r);
      if (isPeak) svg.append(el('circle', { cx: cx + barW / 2, cy: top - 6, r: 2.6,
        fill: 'var(--pumpkin)', filter: 'url(#' + ctx.glow + ')' }));
      if (n <= 14) {
        const v = el('text', { x: cx + barW / 2, y: Math.max(10, top - 5), 'text-anchor': 'middle',
          fill: isToday ? 'var(--sick)' : 'var(--bone)', 'font-size': 9.5, 'font-weight': 600 });
        v.textContent = p.n;
        svg.append(v);
      }
      if (i % labelEvery === 0 || isToday) {
        const l = el('text', { x: cx + barW / 2, y: H - 7, 'text-anchor': 'middle',
          fill: isToday ? 'var(--sick)' : 'var(--muted)', 'font-size': 9 });
        l.textContent = isToday ? 'сегодня' : fmt(p.d);
        svg.append(l);
      }
      if (!ctx.reduceMotion && n <= 40) {
        r.style.transformBox = 'fill-box'; r.style.transformOrigin = 'bottom';
        r.animate([{ transform: 'scaleY(0)' }, { transform: 'scaleY(1)' }],
          { duration: 420, delay: i * 9, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'backwards' });
      }
    });
    if (ctx.showAvg && n >= 21) {
      const ma = movingAvg(points, 7);
      const d = ma.map((v, i) => (i ? 'L' : 'M') + (padL + slot * i + slot / 2).toFixed(1) + ' ' + y(v).toFixed(1)).join(' ');
      const path = el('path', { d: d, fill: 'none', stroke: 'var(--sick)', 'stroke-width': 1.6,
        'stroke-linejoin': 'round', 'stroke-linecap': 'round', opacity: '.9', filter: 'url(#' + ctx.glow + ')' });
      svg.append(path);
    }
    return { tipFor: hit => { const p = points[+hit.getAttribute('data-i')]; return '<b>' + p.n + '</b> сообщ' + (p.n % 10 === 1 && p.n !== 11 ? 'ение' : 'ений') + '<small>' + dayInfo(p.d) + '</small>'; }, peak: peak.d };
  }

  /* ── календарь (год) ───────────────────────────────────────────────── */
  function drawHeat(svg, plot, tip, points, ctx) {
    const cell = 11, gap = 3.4, padL = 20, padT = 16, padB = 18;
    const start = new Date(points[0].d + 'T00:00:00');
    const startOffset = (start.getDay() + 6) % 7;          // неделя начинается с понедельника
    const byWeek = [];
    points.forEach((p, i) => {
      const dt = new Date(p.d + 'T00:00:00');
      const dayNo = Math.round((dt - start) / 86400000);
      const w = Math.floor((dayNo + startOffset) / 7);
      const row = (dt.getDay() + 6) % 7;
      (byWeek[w] = byWeek[w] || []).push({ p: p, row: row, i: i });
    });
    const W = padL + byWeek.length * (cell + gap) + 4, H = padT + 7 * (cell + gap) + padB;
    const lvl = v => (v === 0 ? 0 : v <= 1 ? 1 : v <= 5 ? 2 : v <= 15 ? 3 : 4);
    const fills = ['rgba(255,255,255,.055)', '#7a4415', '#b3601c', '#ec8b22', '#ffc46b'];
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.setAttribute('height', H + 'px');
    let lastMonth = -1;
    byWeek.forEach((week, w) => {
      week.forEach(d => {
        const x = padL + w * (cell + gap), y = padT + d.row * (cell + gap);
        const isToday = d.p.d === points[points.length - 1].d;
        const rect = el('rect', { x: x, y: y, width: cell, height: cell, rx: 3,
          fill: fills[lvl(d.p.n)], 'data-i': d.i, class: 'hw-cell' });
        if (isToday) { rect.setAttribute('stroke', 'var(--sick)'); rect.setAttribute('stroke-width', '1.6'); }
        else if (lvl(d.p.n) === 4) rect.setAttribute('filter', 'url(#' + ctx.glow + ')');
        svg.append(rect);
      });
      const dt = new Date(week[0].p.d + 'T00:00:00');
      if (dt.getMonth() !== lastMonth) {
        lastMonth = dt.getMonth();
        const t = el('text', { x: padL + w * (cell + gap), y: 10, fill: 'var(--muted)', 'font-size': 9 });
        t.textContent = MONTHS[dt.getMonth()];
        svg.append(t);
      }
    });
    ['пн', 'ср', 'сб'].forEach((name, k) => {
      const t = el('text', { x: padL - 5, y: padT + [0, 2, 5][k] * (cell + gap) + 9, 'text-anchor': 'end',
        fill: 'var(--muted)', 'font-size': 8.5 });
      t.textContent = name;
      svg.append(t);
    });
    const peak = points.reduce((a, b) => (b.n > a.n ? b : a), points[0]);
    if (ctx.autoScroll) requestAnimationFrame(() => { plot.scrollLeft = plot.scrollWidth; });
    return { tipFor: rect => { const p = points[+rect.getAttribute('data-i')]; return '<b>' + p.n + '</b> сообщ' +
      (p.n % 10 === 1 && p.n !== 11 ? 'ение' : 'ений') + '<small>' + dayInfo(p.d) + '</small>'; }, peak: peak.d };
  }

  function bindTips(svg, plot, tip, meta) {
    const show = target => {
      const html = meta.tipFor(target);
      tip.innerHTML = html;
      tip.hidden = false;
      const pr = plot.getBoundingClientRect(), tr = target.getBoundingClientRect();
      const x = tr.left - pr.left + plot.scrollLeft + tr.width / 2;
      const y = target.dataset.top != null ? parseFloat(target.dataset.top) : (tr.top - pr.top);
      tip.style.left = Math.min(Math.max(x, 44), plot.clientWidth - 44) + 'px';
      tip.style.top = Math.max(14, y - 2) + 'px';
    };
    const hide = () => { tip.hidden = true; };
    svg.addEventListener('pointerover', e => { if (e.target.dataset.i) show(e.target); });
    svg.addEventListener('pointerdown', e => { if (e.target.dataset.i) { show(e.target); e.preventDefault(); } });
    svg.addEventListener('pointermove', e => { if (e.target.dataset.i) show(e.target); });
    svg.addEventListener('pointerleave', hide);
    plot.addEventListener('touchstart', hide, { passive: true });
    svg.setAttribute('tabindex', '0');
  }

  window.HwActivity = {
    render(plot, points, opts) {
      const o = Object.assign({ mode: 'bars', showAvg: true, reduceMotion: false }, opts || {});
      const tip = document.getElementById('hw-tip');
      const old = plot.querySelector('svg');
      if (old) old.remove();
      const svg = el('svg', { id: 'hw-svg', role: 'img' });
      const defs = el('defs');
      const glow = el('filter', { id: 'hw-glow', x: '-60%', y: '-60%', width: '220%', height: '220%' });
      glow.append(el('feGaussianBlur', { stdDeviation: '1.6', result: 'blur' }));
      const merge = el('feMerge');
      merge.append(el('feMergeNode', { in: 'blur' }), el('feMergeNode', { in: 'SourceGraphic' }));
      glow.append(merge);
      defs.append(glow);
      svg.append(defs);
      plot.classList.toggle('is-heat', o.mode === 'heat');
      plot.insertBefore(svg, plot.firstChild);
      const ctx = { uid: String(Math.random()).slice(2, 7), glow: 'hw-glow', showAvg: o.showAvg,
        reduceMotion: o.reduceMotion, autoScroll: o.mode === 'heat' };
      const meta = o.mode === 'heat'
        ? drawHeat(svg, plot, tip, points, ctx)
        : drawBars(svg, plot, tip, points, ctx);
      bindTips(svg, plot, tip, meta);
      const total = points.reduce((s, p) => s + p.n, 0);
      const peak = points.reduce((a, b) => (b.n > a.n ? b : a), points[0]);
      svg.setAttribute('aria-label', 'Активность по сообщениям: ' + points.length + ' дней, всего ' + total +
        ', максимум ' + peak.n + ' — ' + dayInfo(peak.d));
      return { total, peak, activeDays: points.filter(p => p.n > 0).length };
    },
  };
})();
