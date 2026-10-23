// Итог уровня (Сапёр и Ритм): звёзды появляются по одной, опыт перетекает в полосу Пропуска, веха/рекорд — отдельным бейджем.
// Итог уже посчитан сервером и виден текстом сразу; анимация его только проигрывает и ничего не задерживает.
(() => {
  const L = () => window.League, A = () => window.LeagueArt, Fx = () => window.LeagueFx;

  // opts: {game, level, stars, xp, title, lines, why, prevStars, onNext, onAgain, onExit}
  function show(opts) {
    const won = opts.stars > 0, demo = L().state.me?.demo;
    const badges = [];
    if (won && opts.level % 10 === 0) badges.push(`${A().icon('medal', 'lgr-badge-ico')}Веха ${opts.level} пройдена`);
    if (won && opts.prevStars > 0 && opts.stars > opts.prevStars) badges.push(`${A().icon('star', 'lgr-badge-ico is-on')}Новый рекорд звёзд`);
    const host = L().show(`<section class="lgr ${won ? 'is-won' : 'is-lost'}" aria-labelledby="lgr-title">
      <p class="lg-eyebrow">${opts.game === 'minesweeper' ? 'Сапёр' : 'Ритм'} · уровень ${opts.level}</p>
      <h2 id="lgr-title">${opts.title}</h2>
      <div class="lgr-stars" role="img" aria-label="Звёзд: ${opts.stars} из 3">${[1, 2, 3].map(n => `<span class="lgr-star ${n <= opts.stars ? 'is-on' : ''}">${A().icon('star', 'lgr-star-ico')}</span>`).join('')}</div>
      ${badges.length ? `<div class="lgr-badges">${badges.map(b => `<span class="lgr-badge">${b}</span>`).join('')}</div>` : ''}
      <p class="lgr-lines" aria-live="polite">${opts.lines}</p>
      ${opts.why ? `<p class="lg-rules">${opts.why}</p>` : ''}
      <div class="lgr-xp" id="lgr-xp" ${opts.xp ? '' : 'hidden'}><div class="lgr-xp-top"><span>+<b>${opts.xp}</b> опыта Пропуска${demo ? ' (демо)' : ''}</span><small id="lgr-xp-lvl"></small></div>
        <div class="lgr-bar" aria-hidden="true"><i id="lgr-bar-was"></i><i id="lgr-bar-add"></i></div></div>
      <div class="lgr-btns">${won ? `<button type="button" class="lg-cta" id="lgr-next">Дальше: уровень ${opts.level + 1}</button>` : ''}
        <button type="button" class="${won ? 'secondary' : 'lg-cta'}" id="lgr-again">Ещё раз</button>
        <button type="button" class="lg-link" id="lgr-exit">К уровням</button></div></section>`, 1);
    L().$('lgr-again').onclick = opts.onAgain;
    L().$('lgr-exit').onclick = opts.onExit;
    if (L().$('lgr-next')) L().$('lgr-next').onclick = opts.onNext;
    reveal(host, opts.stars);
    if (opts.xp && !demo) passFlow(opts.xp); else noBar();
  }

  // Звезда за звездой (0,25 с), каждая с ударом и лёгкой вибрацией; третья — с золотой искрой
  function reveal(host, got) {
    const nodes = [...host.querySelectorAll('.lgr-star')];
    if (!Fx().moves()) return;
    nodes.forEach((star, i) => {
      const on = i < got, delay = 180 + i * 250;
      Fx().play(star, [{transform: 'scale(.3) rotate(-25deg)', opacity: 0}, {transform: 'scale(1.25) rotate(6deg)', opacity: 1, offset: .6}, {transform: 'none', opacity: 1}],
        {duration: on ? 420 : 260, delay, fill: 'backwards'});
      if (on) setTimeout(() => { L().haptic('light'); if (i === 2) Fx().ring(star, 'is-gold'); }, delay + 250);
    });
  }

  // Полоса уровня Пропуска: было → стало; перешёл уровень — вспышка и тост «Уровень N Пропуска»
  async function passFlow(gained) {
    let pass;
    try { pass = await L().api('/pass'); } catch (_) { return noBar(); }
    const s = pass.active && pass.seasons.find(x => x.current);
    if (!s) return noBar();
    L().state.pass = pass;
    const per = s.xp_per_level, was = Math.max(0, s.xp - gained), lvlWas = Math.min(s.levels, Math.floor(was / per));
    const label = L().$('lgr-xp-lvl');
    if (!label) return;
    if (s.level >= s.levels) { label.textContent = `Уровень ${s.level} — последний`; return bar(1, 0, 0); }
    label.textContent = `Уровень ${s.level + 1} Пропуска: ${per - s.xp_to_next}/${per}`;
    const up = s.level > lvlWas;
    bar(up ? 0 : (was % per) / per, (s.xp % per) / per, 380);
    if (up) {
      Fx().bump(L().$('lgr-xp'), 1.04);
      Fx().toast(`${A().icon('crown', 'lg-inline')} Уровень ${s.level} Пропуска${s.track[s.level - 1]?.free.state === 'ready' ? ' — награда ждёт' : ''}`, 'is-up');
      L().haptic('medium');
    }
  }

  const noBar = () => L().$('lgr-xp')?.querySelector('.lgr-bar')?.remove();   // демо или Пропуск недоступен: только «+N опыта»

  // Две полосы: прошлый опыт и прибавка; прибавка «втекает» через scaleX
  function bar(was, now, delay) {
    const a = L().$('lgr-bar-was'), b = L().$('lgr-bar-add');
    if (!a || !b) return;
    a.style.transform = `scaleX(${was})`; b.style.transform = `scaleX(${now})`;
    Fx().play(b, [{transform: `scaleX(${was})`}, {transform: `scaleX(${now})`}], {duration: 700, delay, fill: 'backwards'});
  }

  window.LeagueResult = {show};
})();
