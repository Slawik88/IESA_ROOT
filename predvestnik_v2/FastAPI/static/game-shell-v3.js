// Общая оболочка игр: шапка (сезон, дни до конца), полоска Пропуска и кнопка «Заново» одинаковы на страницах Ритма, Сапёра и Лиги.
// Обычный режим (/rhythm-v2, /minesweeper) и рейтинг (/league) собирают шапку из одного куска разметки (game-shell-v3.html), поэтому при
// переключении «Обычный | Рейтинг» меняется только содержимое под ней. Данные Пропуска запоминаются в localStorage: шапка и полоска стоят на месте
// с первого кадра, а свежий ответ сервера лишь подправляет цифры. Нужны league-art.js и league-fx.js (значки, лист, движение).
(() => {
  const CACHE = 'pv_shell_pass';
  const base = document.body.dataset.appBase || '';
  const $ = id => document.getElementById(id);
  const A = () => window.LeagueArt, Fx = () => window.LeagueFx;
  const read = key => { try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch (_) { return null; } };
  const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* приватный режим: оболочка живёт без памяти */ } };
  const plural = (n, one, few, many) => n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? few : many;

  // Возвращаемся только в доказанно соседнюю запись нашего приложения. Прямой
  // вход, другая вкладка и старый WebView сохраняют обычную ссылку «К играм».
  const backLink = $('lg-back-link');
  let returnTo = 'games';
  let trip = history.state?.pvGameTrip || null;
  try {
    const saved = readReturn();
    const pending = sessionStorage.getItem('pv_game_pending');
    sessionStorage.removeItem('pv_game_pending');
    if (!trip && saved && saved.nonce === pending && new URL(saved.url).origin === location.origin) trip = saved;
    if (trip) {
      history.replaceState({...history.state, pvGameTrip: trip}, '');
      if (trip.returnTo === 'pets' || /^guide_[a-z]+(-[a-z]+)*$/.test(trip.returnTo)) returnTo = trip.returnTo;
    }
  } catch (_) { /* Повреждённая память: ссылка ведёт в Игры. */ }
  function readReturn() { return JSON.parse(sessionStorage.getItem('pv_game_return') || 'null'); }
  function returnToApp(event) {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey
        || !backLink || !event.target.closest('#lg-back-link')) return;
    try {
      const entry = window.navigation?.currentEntry;
      const previous = window.navigation?.entries().find(item => item.index === entry?.index - 1);
      if (!trip || !previous || new URL(previous.url).origin + new URL(previous.url).pathname !== trip.url
          || previous.getState()?.pvGameOrigin !== trip.nonce) return;
      event.preventDefault();
      history.back();
    } catch (_) { /* Ссылка работает без Navigation API и sessionStorage. */ }
  }
  if (backLink) {
    backLink.href = `${base}/?startapp=${returnTo}`;
    if (returnTo !== 'games') backLink.setAttribute('aria-label', returnTo === 'pets' ? 'Назад к питомцам' : 'Назад в Путеводитель');
    document.addEventListener('click', returnToApp);
  }
  function carryReturn() {
    try { if (trip) sessionStorage.setItem('pv_game_pending', trip.nonce); } catch (_) { /* Запасная ссылка остаётся. */ }
  }

  // Ответ /pass → то, что рисуют шапка и полоска: текущий сезон, уровень, опыт до следующего, сколько наград ждёт, когда сезон кончится
  function summary(pass, demoPass = null) {
    const s = demoPass || (pass?.active && pass.seasons.find(x => x.current));
    if (!s) return null;
    const waiting = !demoPass && pass.account?.eligible
      ? pass.seasons.reduce((n, x) => n + x.track.filter(r => r.free.state === 'ready').length + x.track.filter(r => r.vip.state === 'ready').length + Number(!!(x.current && x.repeat?.ready)), 0) : 0;
    return {season: s.season ?? null, level: s.level, levels: s.levels, per: s.xp_per_level, toNext: s.xp_to_next, ready: waiting, endsAt: s.ends_at || null};
  }

  // Целых дней до конца — как «ещё N дн.» на страницах игр (core/seasons.py); null — срок неизвестен
  const daysLeft = sum => sum?.endsAt ? Math.max(0, Math.floor((Date.parse(sum.endsAt) - Date.now()) / 864e5)) : null;

  function paintDays(sum) {
    const el = $('lg-days'), days = daysLeft(sum);
    if (!el) return;
    el.hidden = days === null;
    if (days) { el.innerHTML = `<b data-count="days">${days}</b><small>${plural(days, 'день', 'дня', 'дней')} до конца</small>`; Fx()?.count(el); }
    else if (days === 0) el.innerHTML = '<small>последний<br>день сезона</small>';
  }

  // Полоска под переключателем: уровень Пропуска, опыт до следующего, сколько наград ждёт. Нажатие — onOpen.
  function paintStrip(sum, onOpen, hidden = false) {
    const el = $('lg-strip');
    if (!el) return;
    el.hidden = hidden || !sum;
    if (el.hidden) return;
    const max = sum.level >= sum.levels, into = max ? sum.per : sum.per - sum.toNext;
    const note = sum.ready ? `К получению: ${sum.ready}` : max ? 'Все уровни открыты' : `${sum.toNext} опыта до уровня ${sum.level + 1}`;
    el.innerHTML = `<span class="lgs-ico" aria-hidden="true">${A().icon('chest')}</span>
      <span class="lgs-t"><b>Пропуск · уровень ${sum.level}<small> из ${sum.levels}</small></b><small class="${sum.ready ? 'is-ready' : ''}">${sum.ready ? '<i class="lgs-dot" aria-hidden="true"></i>' : ''}${note}</small></span>
      <span class="lgs-bar" aria-hidden="true"><i style="transform:scaleX(${(into / sum.per).toFixed(3)})"></i></span><span class="lgs-go" aria-hidden="true">›</span>`;
    el.setAttribute('aria-label', `Пропуск сезона, уровень ${sum.level} из ${sum.levels}. ${note}`);
    el.onclick = onOpen;
  }

  const remember = sum => { if (sum) write(CACHE, sum); };

  // Страницы обычного режима: нарисовать из памяти сразу, потом спросить сервер
  function mount({label, onOpen = () => { carryReturn(); location.replace(`${base}/league#pass`); }}) {
    const paint = sum => {
      const season = $('lg-eyebrow');
      if (season) season.textContent = sum?.season ? `Сезон ${sum.season} · ${label}` : label;
      paintDays(sum);
      paintStrip(sum, onOpen);
    };
    paint(read(CACHE));
    return fetch(`${base}/league-demo/api/pass`, {headers: window.GameMode?.headers() || {}})
      .then(r => r.ok ? r.json() : null)
      .then(pass => { const sum = summary(pass); if (sum) { remember(sum); paint(sum); } })
      .catch(() => { /* нет сети: остаётся то, что запомнено */ });
  }

  // Опасное действие (начать заново, бросить партию). Если в партии есть что терять, сначала вопрос в листе: игра на паузе, «Продолжить» выбрано
  // по умолчанию, опасная кнопка включается через 0,45 с и не оказывается под пальцем. Нечего терять — действие сразу.
  function guarded({risky, pause = () => {}, resume = () => {}, run, ask}) {
    let asking = false;
    return () => {
      if (asking) return;
      if (!risky()) { run(); return; }
      asking = true;
      pause();
      Fx().sheet(ask.title, `<p class="lg-rules">${ask.text}</p>`, [
        {l: 'Продолжить', f: () => { asking = false; resume(); }},
        {l: ask.confirm, ghost: true, arm: 450, f: () => { asking = false; run(); }},
      ], () => { asking = false; resume(); });
    };
  }

  // Кнопка «Заново». Стоит в верхнем углу экрана игры, подальше от рун и клеток.
  function restartPill({risky, pause, resume, onRestart, ask}) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'lg-restart'; b.setAttribute('aria-label', 'Начать заново');
    b.innerHTML = `${A().icon('restart', 'lg-restart-ico')}<span>Заново</span>`;
    b.onclick = guarded({risky, pause, resume, run: onRestart, ask});
    return b;
  }

  window.GameShell = {summary, daysLeft, paintDays, paintStrip, remember, mount, guarded, restartPill, plural, carryReturn, cached: () => read(CACHE)};
})();
