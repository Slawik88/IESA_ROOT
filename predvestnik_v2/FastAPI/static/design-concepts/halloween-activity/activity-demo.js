/* Демо-обвязка: синтетические данные в форме daily_user_stats и контролы.
   В проекте на этом месте — fetch('/profile/me/activity?days=N'). */
(function () {
  'use strict';
  const plot = document.getElementById('hw-plot');
  const rail = document.getElementById('hw-rail');
  const legend = document.getElementById('hw-legend');
  const sub = document.getElementById('hw-sub');
  const streakChip = document.getElementById('hw-streak');
  const todayChip = document.getElementById('hw-today');

  /* seeded LCG — данные демо стабильны между перезагрузками */
  let seed = 20261031;
  const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;

  function buildSeries(days) {
    const out = [];
    const today = new Date(); today.setHours(0, 0, 0, 0);
    for (let k = days - 1; k >= 0; k--) {
      const d = new Date(today.getTime() - k * 86400000);
      const dow = d.getDay();
      const wave = 1 + Math.sin((days - k) / 26) * 0.35;
      let n = Math.round((6 + rnd() * 26) * wave * (dow === 0 || dow === 6 ? 1.55 : 1));
      if (rnd() < 0.09) n = 0;                                   // пропуски
      if (rnd() < 0.03) n += 30 + Math.round(rnd() * 40);        // всплески
      const sinceStart = days - 1 - k;
      if (sinceStart > 40 && sinceStart < 56) n = Math.round(n * 0.08); // «отпуск»
      if (k < 14) n = Math.round(n * 1.15 + 4);                  // свежий азарт
      out.push({ d: d.toISOString().slice(0, 10), n });
    }
    return out;
  }
  const SERIES = buildSeries(400);

  function slice(period) {
    return SERIES.slice(-Math.min(period, SERIES.length)).map(p => Object.assign({}, p));
  }
  function streakOf() {
    let s = 0, i = SERIES.length - 1;
    if (SERIES[i].n === 0) i--;
    for (; i >= 0 && SERIES[i].n > 0; i--) s++;
    return s;
  }
  function chip(id, text, title) {
    const node = document.getElementById(id);
    if (node) { node.textContent = text; if (title) node.title = title; }
  }

  function renderRail(points) {
    const total = points.reduce((s, p) => s + p.n, 0);
    const peak = points.reduce((a, b) => (b.n > a.n ? b : a), points[0]);
    const perDay = (total / points.length).toFixed(1).replace('.0', '');
    rail.innerHTML =
      '<div><dt>Всего за период</dt><dd>' + total + '</dd></div>' +
      '<div><dt>В среднем в день</dt><dd>' + perDay + '</dd></div>' +
      '<div><dt>Лучший день</dt><dd>' + peak.n + ' <small>' + peak.d.slice(8) + '.' + peak.d.slice(5, 7) + '</small></dd></div>';
  }
  function renderLegend(mode) {
    if (mode !== 'heat') {
      legend.innerHTML = '<span class="hw-legend"><i style="background:linear-gradient(180deg,var(--bar-1),var(--bar-2))"></i>сообщения</span>' +
        '<span class="hw-legend" style="margin-left:auto"><i style="background:var(--sick)"></i>сегодня · 7-дневное среднее</span>';
      return;
    }
    const steps = ['rgba(255,255,255,.055)', '#7a4415', '#b3601c', '#ec8b22', '#ffc46b'];
    legend.innerHTML = '<span>Меньше</span><span class="hw-legend">' +
      steps.map(c => '<i style="background:' + c + '"></i>').join('') + '</span><span>Больше</span>' +
      '<span style="margin-left:auto">свайп влево-вправо →</span>';
  }

  let period = 30;
  let view = 'auto';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const plot0 = () => plot.getBoundingClientRect().width || 320;

  function paint(keepScroll) {
    const points = slice(period);
    const mode = view !== 'auto' ? view : (period === 365 ? 'heat' : 'bars');
    document.querySelectorAll('#hw-periods button').forEach(b =>
      b.classList.toggle('on', Number(b.dataset.period) === period));
    document.querySelectorAll('#hw-views button').forEach(b =>
      b.classList.toggle('on', b.dataset.view === (view === 'auto' ? mode : view)));
    sub.textContent = 'сообщения за ' + (period === 365 ? 'год' : period + ' дн') + ' · ' + (mode === 'heat' ? 'календарь' : 'полосы');
    const scroll = keepScroll ? plot.scrollLeft : null;
    window.HwActivity.render(plot, points, { mode: mode, showAvg: mode === 'bars', reduceMotion: reduceMotion });
    if (scroll !== null) plot.scrollLeft = scroll;
    renderRail(points);
    renderLegend(mode);
    const today = points[points.length - 1];
    chip('hw-today', '🏠 ' + today.n);
    chip('hw-streak', '🔥 ' + streakOf() + ' дн', 'Дней подряд с сообщениями');
    window.__hwStats = { total: points.reduce((s, p) => s + p.n, 0), days: points.length, mode: mode };
  }

  document.getElementById('hw-periods').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    period = Number(b.dataset.period);
    e.currentTarget.querySelectorAll('button').forEach(x => x.setAttribute('aria-selected',
      String(x === b)));
    paint();
  });
  document.getElementById('hw-views').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    view = b.dataset.view;
    e.currentTarget.querySelectorAll('button').forEach(x => x.setAttribute('aria-selected',
      String(x === b)));
    paint();
  });
  document.querySelector('.demo-seg').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    document.querySelectorAll('.demo-seg button').forEach(x => x.classList.toggle('on', x === b));
    const w = Number(b.dataset.w);
    document.getElementById('phone').style.setProperty('--pw', w ? w + 'px' : '100%');
    setTimeout(() => paint(), 30);
  });
  document.getElementById('demo-hw').addEventListener('change', e => {
    document.body.classList.toggle('hw-skin', e.target.checked);
    setTimeout(() => paint(true), 30);
  });

  let rt;
  new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(() => paint(true), 120); }).observe(plot);
  paint();
})();
