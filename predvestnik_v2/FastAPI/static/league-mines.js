// Сапёр Лиги: поле живёт на сервере, каждое касание — один короткий запрос. Раскладка мин на телефон не приходит.
(() => {
  const L = () => window.League;
  let run = null, mode = 'open', busy = false, ticker = null, startedAt = 0, press = null, pressed = false;
  const stop = () => { clearInterval(ticker); ticker = null; };
  const clock = ms => { const s = Math.max(0, Math.floor(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  const DEPTH = {1: 'очевидная логика', 2: 'пары чисел', 3: 'глубокая логика'};

  async function start(level) {
    stop();
    run = await L().api('/runs', {method: 'POST', body: JSON.stringify({game: 'minesweeper', level})});
    mode = 'open';
    startedAt = performance.now() - (run.elapsed_ms || 0);
    ticker = setInterval(tick, 500);
    draw();
  }

  function tick() {
    const el = L().$('lgm-time');
    if (el && run && run.status === 'active') el.textContent = clock(performance.now() - startedAt);
  }

  function cellHtml(cell) {
    const key = String(cell), open = key in run.cells, flag = run.flags.includes(cell), mine = run.mines.includes(cell);
    const n = open ? run.cells[key] : 0;
    const label = mine ? 'Мина' : flag ? 'Флаг' : open ? (n ? `рядом мин ${n}` : 'пусто') : 'закрыта';
    const done = run.status !== 'active';
    return `<button type="button" class="lg-cell ${open ? 'open' : ''} ${flag ? 'flag' : ''} ${mine ? 'mine' : ''} ${open && n ? 'n' + n : ''}"
      data-cell="${cell}" aria-label="Клетка ${cell + 1}: ${label}" ${done || open ? 'disabled' : ''}>${mine ? '✹' : flag ? '⚑' : open && n ? n : ''}</button>`;
  }

  function draw(error = '') {
    const cells = [];
    for (let c = 0; c < run.width * run.height; c++) cells.push(cellHtml(c));
    const left = run.mine_count - run.flags.length;
    L().show(`<h2>Сапёр · уровень ${run.level}</h2>
      <p class="lg-sub">Поле ${run.width}×${run.height}, мин: ${run.mine_count}, ${DEPTH[run.tier] || ''}. Без угадывания. Время на ★★★: ${clock(run.par_s * 1000)}.</p>
      <div class="lg-stats"><div><b>${left}</b><small>мин осталось</small></div><div><b id="lgm-time">${clock(run.elapsed_ms)}</b><small>время</small></div><div><b>${Object.keys(run.cells).length}/${run.width * run.height - run.mine_count}</b><small>открыто</small></div></div>
      <div class="lg-mode" role="group" aria-label="Действие"><button type="button" data-mode="open" aria-pressed="${mode === 'open'}">Открывать</button><button type="button" data-mode="flag" aria-pressed="${mode === 'flag'}">Флаг</button></div>
      <div class="lg-board" style="grid-template-columns:repeat(${run.width},minmax(0,1fr))" role="grid" aria-label="Поле">${cells.join('')}</div>
      ${error ? `<p class="lg-error" role="alert">${L().esc(error)}</p>` : ''}
      ${run.status === 'active' ? '' : finishHtml()}
      <div class="lg-row"><button type="button" class="secondary" id="lgm-exit">К уровням</button></div>`);
    bind();
  }

  function finishHtml() {
    const r = run.result || {}, won = run.status === 'won';
    const why = !won ? 'Мина. Поле можно пройти заново — будет новое поле той же сложности.'
      : r.stars === 3 ? 'Без ошибок и в срок.' : r.stars === 2 ? `Без ошибок. Для ★★★ уложись в ${clock(run.par_s * 1000)}.` : `Неверных флагов: ${run.wrong_flags}. Для ★★ — ни одного.`;
    return `<div class="lg-stars" aria-label="Звёзд: ${r.stars || 0} из 3">${L().stars(r.stars || 0)}</div>
      <p class="lg-rules">${won ? 'Поле пройдено!' : 'Не получилось.'} ${why}${r.xp ? ` +${r.xp} опыта Пропуска (демо).` : ''}</p>
      <div class="lg-row">${won ? `<button type="button" id="lgm-next">Уровень ${run.level + 1}</button>` : ''}<button type="button" class="${won ? 'secondary' : ''}" id="lgm-again">Ещё раз</button></div>`;
  }

  function bind() {
    const $ = L().$;
    $('lgm-exit').onclick = () => { stop(); L().back(); };
    $('lgm-again') && ($('lgm-again').onclick = () => start(run.level).catch(e => draw(e.message)));
    $('lgm-next') && ($('lgm-next').onclick = () => start(run.level + 1).catch(e => draw(e.message)));
    document.querySelectorAll('.lg-mode button').forEach(b => { b.onclick = () => { mode = b.dataset.mode; draw(); }; });
    document.querySelectorAll('.lg-cell[data-cell]').forEach(b => {
      const cell = Number(b.dataset.cell);
      b.addEventListener('pointerdown', () => { pressed = false; clearTimeout(press); press = setTimeout(() => { pressed = true; act(cell, 'flag'); }, 450); });
      b.addEventListener('pointerup', () => clearTimeout(press));
      b.addEventListener('pointerleave', () => clearTimeout(press));
      b.addEventListener('contextmenu', e => { e.preventDefault(); clearTimeout(press); if (!pressed) act(cell, 'flag'); pressed = true; });
      b.addEventListener('click', () => { if (pressed) { pressed = false; return; } act(cell, mode === 'flag' ? 'flag' : 'open'); });
    });
  }

  async function act(cell, kind) {
    if (busy || !run || run.status !== 'active') return;
    busy = true;
    try {
      const next = await L().api(`/runs/${encodeURIComponent(run.run_id)}/mines`, {method: 'POST', body: JSON.stringify({revision: run.revision, kind, cell})});
      run = next;
      if (run.status !== 'active') { stop(); L().haptic(run.status === 'won' ? 'medium' : 'heavy'); } else L().haptic('light');
      draw(next.stale ? 'Поле обновилось на другом экране — показано актуальное.' : '');
    } catch (error) {
      draw(error.message);
    } finally {
      busy = false;
    }
  }

  window.LeagueGames = {...(window.LeagueGames || {}), minesweeper: {start}};
})();
