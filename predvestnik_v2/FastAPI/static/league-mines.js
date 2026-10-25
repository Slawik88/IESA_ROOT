// Сапёр Лиги: поле живёт на сервере, каждое касание — один короткий запрос. Раскладка мин на телефон не приходит.
// Пока ждём ответ, клетка «вдавлена»; ответ проигрывается волной от точки нажатия (не дольше ответа сервера, ввод не держит).
(() => {
  const L = () => window.League, A = () => window.LeagueArt, Fx = () => window.LeagueFx;
  let run = null, mode = 'open', busy = false, ticker = null, startedAt = 0, press = null, pressed = false, prevStars = 0;
  const stop = () => { clearInterval(ticker); ticker = null; };
  const clock = ms => { const s = Math.max(0, Math.floor(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  const DEPTH = {1: 'очевидная логика', 2: 'пары чисел', 3: 'глубокая логика'};
  const WAVE_MAX = 40, STEP_MS = 15;   // не больше 40 клеток в движении, 15 мс на шаг волны

  async function start(level) {
    stop();
    run = await L().api('/runs', {method: 'POST', body: JSON.stringify({game: 'minesweeper', level})});
    prevStars = L().state.me?.games.minesweeper.levels[String(level)]?.stars || 0;
    mode = 'open';
    startedAt = performance.now() - (run.elapsed_ms || 0);
    ticker = setInterval(tick, 500);
    draw('', null, 1);
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
      data-cell="${cell}" aria-label="Клетка ${cell + 1}: ${label}" ${done || open ? 'disabled' : ''}>${mine ? A().icon('mine') : flag ? A().icon('flag') : open && n ? n : ''}</button>`;
  }

  function draw(error = '', fx = null, dir = 0) {
    const cells = [];
    for (let c = 0; c < run.width * run.height; c++) cells.push(cellHtml(c));
    const left = run.mine_count - run.flags.length, total = run.width * run.height - run.mine_count;
    L().show(`<div class="lgm-head"><h2>Уровень ${run.level}</h2><span class="lgm-tools"><span id="lgm-restart"></span><button type="button" class="lg-link" id="lgm-exit">К уровням</button></span></div>
      <p class="lg-sub">Поле ${run.width}×${run.height}, ${DEPTH[run.tier] || ''}. Без угадывания. Время на ★★★: ${clock(run.par_s * 1000)}.</p>
      <div class="lg-hud"><span>${A().icon('mine', 'lg-hud-ico')}<b>${left}</b><small>мин</small></span><span><b id="lgm-time">${clock(run.elapsed_ms)}</b><small>время</small></span>
        <span><b>${Object.keys(run.cells).length}</b><small>/${total} открыто</small></span></div>
      <div class="lg-seg" role="group" aria-label="Действие"><button type="button" data-mode="open" aria-pressed="${mode === 'open'}">Открывать</button><button type="button" data-mode="flag" aria-pressed="${mode === 'flag'}">${A().icon('flag', 'lg-inline')} Флаг</button></div>
      <div class="lg-board-wrap"><div class="lg-board" style="grid-template-columns:repeat(${run.width},minmax(0,1fr))" role="grid" aria-label="Поле">${cells.join('')}</div><i class="lgm-sweep" aria-hidden="true"></i></div>
      <p class="lg-error" role="alert">${error ? L().esc(error) : ''}</p>`, dir);
    bind();
    if (fx) animate(fx);
  }

  const pos = c => [c % run.width, Math.floor(c / run.width)];
  const dist = (a, b) => { const [ax, ay] = pos(a), [bx, by] = pos(b); return Math.hypot(ax - bx, ay - by); };
  const btn = c => document.querySelector(`.lg-cell[data-cell="${c}"]`);

  // Что изменилось после хода: новые открытые клетки — волной, новый флаг — «втык», мина — вспышка и цепочка, победа — волна света
  function animate({before, cell, kind}) {
    const opened = Object.keys(run.cells).map(Number).filter(c => !(String(c) in before.cells)).sort((a, b) => dist(a, cell) - dist(b, cell));
    opened.slice(0, WAVE_MAX).forEach(c => Fx().play(btn(c), [{transform: 'scale(.55)', opacity: 0}, {transform: 'scale(1.06)', opacity: 1, offset: .7}, {transform: 'none', opacity: 1}],
      {duration: 240, delay: Math.round(dist(c, cell)) * STEP_MS, fill: 'backwards'}));
    if (kind === 'flag' && run.flags.includes(cell) && !before.flags.includes(cell)) {
      Fx().play(btn(cell)?.firstElementChild, [{transform: 'translateY(-10px) scale(1.3)', opacity: 0}, {transform: 'rotate(-12deg)', opacity: 1, offset: .45}, {transform: 'rotate(8deg)', offset: .7}, {transform: 'none'}], {duration: 380});
    }
    if (run.status === 'lost') {
      const hit = btn(cell);
      hit?.classList.add('hit');
      Fx().play(hit, [{transform: 'scale(1)'}, {transform: 'scale(1.35)', offset: .35}, {transform: 'none'}], {duration: 360});
      Fx().ring(hit, 'is-bad');
      run.mines.filter(c => c !== cell).sort((a, b) => dist(a, cell) - dist(b, cell)).slice(0, WAVE_MAX)
        .forEach((c, i) => Fx().play(btn(c), [{transform: 'scale(.4)', opacity: 0}, {transform: 'none', opacity: 1}], {duration: 220, delay: 160 + i * 45, fill: 'backwards'}));
      Fx().shake(document.querySelector('.lg-board'));
    }
    if (run.status === 'won') {
      const sweep = document.querySelector('.lgm-sweep');
      Fx().play(sweep, [{transform: 'translateX(-110%) skewX(-18deg)', opacity: 0}, {transform: 'translateX(0) skewX(-18deg)', opacity: 1, offset: .5}, {transform: 'translateX(110%) skewX(-18deg)', opacity: 0}],
        {duration: 720, delay: 120, fill: 'both'});
      Object.keys(run.cells).map(Number).sort((a, b) => dist(a, cell) - dist(b, cell)).slice(0, WAVE_MAX)
        .forEach(c => Fx().play(btn(c), [{transform: 'none'}, {transform: 'scale(1.08)', offset: .5}, {transform: 'none'}], {duration: 300, delay: 100 + Math.round(dist(c, cell)) * 18}));
    }
  }

  function bind() {
    const $ = L().$;
    $('lgm-exit').onclick = () => { stop(); L().back(); };
    // «Заново»: после первого хода спрашиваем в листе (время на уровне идёт на сервере и не останавливается); до него — сразу
    $('lgm-restart').append(window.GameShell.restartPill({
      risky: () => run.status === 'active' && run.revision > 0, onRestart: () => start(run.level).catch(e => Fx().toast(L().esc(e.message), 'is-bad')),
      ask: {title: 'Начать уровень заново?', text: 'Это поле не сохранится: открытые клетки и время пропадут. Поле будет новым, звёзды, которые у тебя уже есть, останутся.', confirm: 'Да, начать заново'},
    }));
    document.querySelectorAll('.lg-seg button').forEach(b => { b.onclick = () => { mode = b.dataset.mode; draw(); }; });
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
    const before = run;
    btn(cell)?.classList.add('is-pressed');   // ждём ответа: клетка вдавлена, без спиннера
    try {
      const next = await L().api(`/runs/${encodeURIComponent(run.run_id)}/mines`, {method: 'POST', body: JSON.stringify({revision: run.revision, kind, cell})});
      run = next;
      if (run.status !== 'active') { stop(); L().haptic(run.status === 'won' ? 'medium' : 'heavy'); } else L().haptic('light');
      draw(next.stale ? 'Поле обновилось на другом экране — показано актуальное.' : '', next.stale ? null : {before, cell, kind});
      if (run.status !== 'active') { const id = run.run_id; setTimeout(() => finish(id), Fx().moves() ? (run.status === 'won' ? 950 : 1100) : 400); }
    } catch (error) {
      draw(error.message);
    } finally {
      busy = false;
    }
  }

  // Экран итога; поле остаётся в памяти — «Ещё раз» начинает новое той же сложности
  function finish(id) {
    // игрок мог уйти к уровням или начать новое поле, пока шла волна
    if (!run || run.run_id !== id || run.status === 'active' || !L().$('lgm-exit') || L().$('lg-play').classList.contains('lg-hidden')) return;
    const r = run.result || {}, won = run.status === 'won', level = run.level;
    const why = !won ? 'Мина. Пройди заново — будет новое поле той же сложности.'
      : r.stars === 3 ? 'Без ошибок и в срок.' : r.stars === 2 ? `Без ошибок. Для ★★★ уложись в ${clock(run.par_s * 1000)}.` : `Неверных флагов: ${run.wrong_flags}. Для ★★ — ни одного.`;
    window.LeagueResult.show({
      game: 'minesweeper', level, stars: r.stars || 0, xp: r.xp || 0, prevStars, why,
      title: won ? 'Поле пройдено!' : 'Не получилось',
      lines: `Время ${clock(run.elapsed_ms)} · открыто ${Object.keys(run.cells).length} из ${run.width * run.height - run.mine_count}`,
      onNext: () => start(level + 1).catch(e => Fx().toast(L().esc(e.message), 'is-bad')),
      onAgain: () => start(level).catch(e => Fx().toast(L().esc(e.message), 'is-bad')),
      onExit: () => L().back(),
    });
  }

  window.LeagueGames = {...(window.LeagueGames || {}), minesweeper: {start}};
})();
