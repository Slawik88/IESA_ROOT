/* Живой график курса для биржи v2.
   Только отрисовка уже опубликованных сервером тиков; генератор не трогает.
   Чистые функции экспортируются для контрактного Node-теста. */
window.CM2Chart = (() => {
  const W = 320, H = 180;
  const PAD = { top: 18, right: 12, bottom: 26, left: 10 };
  const PLOT = { x0: PAD.left, x1: W - PAD.right, y0: PAD.top, y1: H - PAD.bottom };

  /* ── чистые помощники (тестируются без DOM) ─────────────────────────────── */

  function bounds(values) {
    let min = Infinity, max = -Infinity;
    for (const v of values) { if (v < min) min = v; if (v > max) max = v; }
    if (!Number.isFinite(min)) return { min: 0, max: 1 };
    if (max - min <= Math.abs(max) * 0.002) {
      const air = Math.max(Math.abs(max) * 0.012, 1e-9);
      return { min: min - air, max: max + air };
    }
    return { min, max };
  }

  function path(values, span) {
    const n = values.length;
    if (!n) return '';
    return values.map((v, i) => {
      const x = n === 1 ? (PLOT.x0 + PLOT.x1) / 2 : PLOT.x0 + (PLOT.x1 - PLOT.x0) * i / (n - 1);
      const y = PLOT.y1 - (PLOT.y1 - PLOT.y0) * (v - span.min) / (span.max - span.min);
      return `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ');
  }

  function downsample(points, cap = 300) {
    const n = points.length;
    if (n <= cap) return points;
    const step = (n - 1) / (cap - 1), out = [];
    for (let i = 0; i < cap; i++) out.push(points[Math.round(i * step)]);
    return out;
  }

  /* Подпись времени из серверного номера тика: детерминированно, UTC. */
  function label(tick, hours, tickSeconds, timeZone = 'UTC') {
    return new Date(tick * tickSeconds * 1000).toLocaleString('ru-RU', hours > 24
      ? { timeZone, day:'2-digit', month:'2-digit' }
      : { timeZone, hour:'2-digit', minute:'2-digit', hourCycle:'h23' });
  }

  /* ── отрисовка ──────────────────────────────────────────────────────────── */

  function fmt(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return n.toLocaleString('ru-RU', { maximumFractionDigits: 8 });
  }

  function markerPoints(ticks, values, span) {
    return ticks.map(m => {
      const i = values.findIndex(p => p.tick >= m.tick);
      const at = i < 0 ? values.length - 1 : i;
      const y = PLOT.y1 - (PLOT.y1 - PLOT.y0) * (m.value - span.min) / (span.max - span.min);
      const x = values.length === 1 ? (PLOT.x0 + PLOT.x1) / 2 : PLOT.x0 + (PLOT.x1 - PLOT.x0) * at / (values.length - 1);
      return { x, y, side: m.side, price: m.value, tick: m.tick };
    });
  }

  function tooltipFor(values, span) {
    const steps = values.length;
    return index => {
      const p = values[Math.max(0, Math.min(steps - 1, index))];
      const x = steps === 1 ? (PLOT.x0 + PLOT.x1) / 2 : PLOT.x0 + (PLOT.x1 - PLOT.x0) * index / (steps - 1);
      const y = PLOT.y1 - (PLOT.y1 - PLOT.y0) * (p.value - span.min) / (span.max - span.min);
      return { x, y, tick: p.tick, price: p.value };
    };
  }

  /* Точка тапа → ближайший тик. Возвращает -1, если промах. */
  function nearest(clientX, boxWidth, steps) {
    if (steps < 1 || !boxWidth) return -1;
    if (steps === 1) return 0;
    const x = clientX * W / boxWidth;
    if (x < PLOT.x0 - 14 || x > PLOT.x1 + 14) return -1;
    return Math.max(0, Math.min(steps - 1, Math.round((x - PLOT.x0) / (PLOT.x1 - PLOT.x0) * (steps - 1))));
  }

  function attach(host, values, span, hours, tickSeconds, timeZone) {
    const svg = host.querySelector('svg');
    if (!svg || !svg.addEventListener) return;
    const tip = svg.querySelector('.cm2-tip');
    const at = tooltipFor(values, span);
    const cursor = host.querySelector('.cm2-cursor'), output = host.querySelector('output');
    const select = index => {
      if (index < 0 || !tip) return;
      const point = at(index);
      host.dataset.selectedTick = String(point.tick);
      if (cursor) cursor.value = String(index);
      const caption = new Date(point.tick * tickSeconds * 1000).toLocaleString('ru-RU', {timeZone,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) + ' · ' + fmt(point.price) + ' Моры';
      if (output) output.textContent = caption;
      if (cursor) cursor.setAttribute('aria-valuetext',caption);
      tip.setAttribute('transform', `translate(${point.x},${point.y})`);
      tip.querySelector('line').setAttribute('y1', String(PLOT.y0 - point.y));
      tip.querySelector('text').textContent = '';
      const wide = point.x > W * 0.66;
      tip.querySelector('text').setAttribute('text-anchor', wide ? 'end' : 'start');
      tip.querySelector('text').setAttribute('x', wide ? -10 : 10);
      tip.removeAttribute('hidden');
    };
    const show = event => {
      const box = svg.getBoundingClientRect();
      if (box.width) select(nearest(event.clientX - box.left, box.width, values.length));
    };
    if (cursor) cursor.addEventListener('input',()=>select(Number(cursor.value)));
    const wanted = Number(host.dataset.selectedTick);
    const saved = Number.isFinite(wanted) ? values.reduce((best,p,i)=>Math.abs(p.tick-wanted)<Math.abs(values[best].tick-wanted)?i:best,0) : values.length-1;
    select(saved);
    svg.addEventListener('pointerdown', show);
    svg.addEventListener('pointermove', event => { if (event.pressure > 0 || event.pointerType === 'mouse') show(event); });
    svg.addEventListener('pointerup', show);
  }

  function body(points, options) {
    const values = points.map(p => ({ tick: p.tick, value: Number(p.price) }));
    const span = bounds(values.map(p => p.value));
    const line = path(values.map(p => p.value), span);
    const area = `${line} L${PLOT.x1.toFixed(2)},${PLOT.y1} L${PLOT.x0.toFixed(2)},${PLOT.y1} Z`;
    const last = values[values.length - 1];
    const lastX = values.length === 1 ? (PLOT.x0 + PLOT.x1) / 2 : PLOT.x1;
    const lastY = PLOT.y1 - (PLOT.y1 - PLOT.y0) * (last.value - span.min) / (span.max - span.min);
    const grid = [0, 0.5, 1].map(k => {
      const y = PLOT.y0 + (PLOT.y1 - PLOT.y0) * k;
      const val = span.max - (span.max - span.min) * k;
      return `<line class="cm2-grid" x1="${PLOT.x0}" y1="${y.toFixed(2)}" x2="${PLOT.x1}" y2="${y.toFixed(2)}"/>` +
        `<text class="cm2-grid-label" x="${PLOT.x1}" y="${(y - 4).toFixed(2)}" text-anchor="end">${fmt(val)}</text>`;
    }).join('');
    const cost = options.cost && Number.isFinite(Number(options.cost))
      ? (() => {
          const value = Number(options.cost);
          const y = PLOT.y1 - (PLOT.y1 - PLOT.y0) * (value - span.min) / (span.max - span.min);
          if (y < PLOT.y0 - 4 || y > PLOT.y1 + 4) return '';
          return `<line class="cm2-cost" x1="${PLOT.x0}" y1="${y.toFixed(2)}" x2="${PLOT.x1}" y2="${y.toFixed(2)}"/><text class="cm2-cost-label" x="${PLOT.x0 + 4}" y="${(y - 4).toFixed(2)}">ваша цена</text>`;
        })()
      : '';
    const marks = markerPoints((options.markers || []).map(m => ({ tick: m.tick, value: Number(m.price), side: m.side })), values, span)
      .map(m => `<circle class="cm2-mark cm2-mark-${m.side === 'buy' ? 'buy' : 'sell'}" cx="${m.x.toFixed(2)}" cy="${m.y.toFixed(2)}" r="3.4"><title>${m.side === 'buy' ? 'Покупка' : 'Продажа'} · ${fmt(m.price)}</title></circle>`)
      .join('');
    const ticks = [...new Set([0, Math.floor((values.length - 1) / 2), values.length - 1])];
    const times = ticks.map((i, k) => {
      const x = values.length === 1 ? (PLOT.x0 + PLOT.x1) / 2 : PLOT.x0 + (PLOT.x1 - PLOT.x0) * i / (values.length - 1);
      const anchor = k === 0 ? 'start' : k === ticks.length-1 ? 'end' : 'middle';
      return `<text class="cm2-time" x="${x.toFixed(2)}" y="${H - 6}" text-anchor="${anchor}">${label(values[i].tick, options.hours, options.tickSeconds, options.timeZone)}</text>`;
    }).join('');
    return { values, span, line, area, grid, cost, marks, times, last, lastX, lastY };
  }

  function render(host, points, options = {}) {
    if (!host) return;
    const hours = options.hours || 24, tickSeconds = options.tickSeconds || 300;
    const list = downsample(points || []);
    const signature = JSON.stringify([list,options.cost,options.markers,hours,tickSeconds]);
    if(host.dataset.renderSignature===signature)return;
    host.dataset.renderSignature=signature;
    if (list.length < 2) {
      host.innerHTML = '<p class="cm2-chart-empty">График появится после следующего обновления курса.</p>';
      return;
    }
    const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const focused = host.querySelector('.cm2-cursor') === host.ownerDocument?.activeElement;
    const b = body(list, { ...options, hours, tickSeconds, timeZone });
    host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Курс за период: от ${fmt(b.values[0].value)} до ${fmt(b.last.value)} Моры">` +
      `<defs><linearGradient id="cm2-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--v3-acc)" stop-opacity=".28"/><stop offset="1" stop-color="var(--v3-acc)" stop-opacity="0"/></linearGradient></defs>` +
      b.grid + b.cost +
      `<path class="cm2-area" d="${b.area}" fill="url(#cm2-fill)"/>` +
      `<path class="cm2-line" d="${b.line}"/>` +
      b.marks + b.times +
      `<g class="cm2-last"><circle class="cm2-dot" cx="${b.lastX}" cy="${b.lastY.toFixed(2)}" r="4.2"/></g>` +
      `<g class="cm2-tip" hidden><line y1="0" y2="0"/><circle r="3"/><text x="10" y="-8"/></g>` +
      `</svg><output class="cm2-chart-readout"></output><input class="cm2-cursor" type="range" min="0" max="${list.length-1}" step="1" aria-label="Выбрать время на графике">`;
    attach(host, b.values, b.span, hours, tickSeconds, timeZone);
    if (focused) host.querySelector('.cm2-cursor')?.focus({preventScroll:true});
  }

  return { render, path, bounds, downsample, label, nearest, markerPoints, tooltipFor, PLOT, W, H };
})();
