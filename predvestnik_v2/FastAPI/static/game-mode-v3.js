// Переключатель «Обычный | Рейтинг» внутри игры: одна игра — два режима, без лишних вкладок и экранов.
// Обычный — страница игры (/rhythm-v2, /minesweeper), рейтинг — лестница Лиги этой же игры (/league?game=…).
// Последний выбор запоминается: из меню «Играть» игра откроется в нём (app.04.js). Страницы подключают его так:
// <div data-game-mode="rhythm" data-gmode="casual" hidden></div> (монтируется сам) или GameMode.mount(host, {game, mode}).
// Переключатель появляется, только когда Лига открыта игроку (до сезона 2 — ранний доступ).
// Переход плавный: ползунок уезжает, содержимое под шапкой уходит в сторону нового режима (а шапка, переключатель и полоска Пропуска
// остаются на месте — у обеих страниц они одинаковые), новая страница приходит с той же стороны. Следующая страница подгружается заранее.
(() => {
  const base = document.body.dataset.appBase || '';
  const PAGES = {casual: {rhythm: '/rhythm-v2', minesweeper: '/minesweeper'}, ranked: {rhythm: '/league?game=rhythm', minesweeper: '/league?game=minesweeper'}};
  const ACCESS = 'pv_league_access', SEEN = 'pv_league_seen', MODE = 'pv_game_mode:', LEAVE_MS = 170;
  const read = key => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const write = (key, value) => { try { localStorage.setItem(key, value); } catch (_) { /* private mode */ } };

  function headers() {
    const app = window.Telegram?.WebApp, init = app?.initData || new URLSearchParams(location.hash.slice(1)).get('tgWebAppData') || '';
    const h = {};
    if (init) h['x-init-data'] = init;
    const session = read('pv_sess');
    if (session) h['x-session-token'] = session;
    return h;
  }

  // Открыта ли Лига этому игроку: ответ запоминается, чтобы переключатель стоял на месте сразу, в том числе без сети
  async function access() {
    try {
      const r = await fetch(base + '/league-demo/api/access', {headers: headers()});
      if (!r.ok) return read(ACCESS) === '1';
      const allowed = Boolean((await r.json()).allowed);
      write(ACCESS, allowed ? '1' : '0');
      return allowed;
    } catch (_) {
      return read(ACCESS) === '1';
    }
  }

  // Движение разрешено так же, как в Лиге (слабый телефон, «Спокойный режим», prefers-reduced-motion — без него)
  const moves = () => window.LeagueFx ? window.LeagueFx.moves() : !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  function go(game, mode) {
    write(MODE + game, mode);
    window.GameShell?.carryReturn();
    try { window.Telegram?.WebApp?.HapticFeedback?.selectionChanged(); } catch (_) { /* old client */ }
    try { sessionStorage.setItem('pv_mode_dir', mode === 'ranked' ? '1' : '-1'); } catch (_) { /* без памяти: страница просто появится */ }
    document.body.classList.add('gm-leaving', mode === 'ranked' ? 'gm-to-ranked' : 'gm-to-casual');
    // замена, а не переход: «назад» ведёт в меню игр, а не по кругу режимов; ползунок и уход содержимого успевают доехать
    setTimeout(() => location.replace(base + PAGES[mode][game]), moves() ? LEAVE_MS : 0);
  }

  // Другой режим подгружается заранее, пока игрок смотрит на этот: при переключении страница уже рядом
  function prefetch(url) {
    if (document.querySelector(`link[rel="prefetch"][href="${url}"]`)) return;
    const link = document.createElement('link');
    link.rel = 'prefetch'; link.href = url;
    document.head.appendChild(link);
  }
  window.addEventListener('pageshow', event => { if (event.persisted) document.body.classList.remove('gm-leaving'); });

  // data-gmode, а не data-mode: страницы игр вешают обработчики на все [data-mode] (открыть/флаг, старт забега)
  function draw(host, game, mode) {
    const fresh = mode === 'casual' && read(SEEN) !== '1';
    host.innerHTML = `<nav class="gmode" aria-label="Режим игры"><i class="gmode-thumb ${mode === 'ranked' ? 'is-right' : ''}" aria-hidden="true"></i>
      <button type="button" data-gmode="casual" aria-pressed="${mode === 'casual'}">Обычный</button>
      <button type="button" data-gmode="ranked" aria-pressed="${mode === 'ranked'}">Рейтинг${fresh ? '<i class="gmode-new">новое</i>' : ''}</button></nav>`;
    host.hidden = false;
    host.querySelectorAll('button').forEach(b => {
      b.onclick = () => {
        if (b.dataset.gmode === mode || host.dataset.leaving) return;
        host.dataset.leaving = '1';
        host.querySelector('.gmode-thumb').classList.toggle('is-right', b.dataset.gmode === 'ranked');
        host.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        go(game, b.dataset.gmode);
      };
    });
    (window.requestIdleCallback || (job => setTimeout(job, 600)))(() => prefetch(base + PAGES[mode === 'ranked' ? 'casual' : 'ranked'][game]));
  }

  async function mount(host, {game, mode, known = false}) {
    if (!host || !PAGES[mode]?.[game]) return;
    write(MODE + game, mode);
    if (mode === 'ranked') write(SEEN, '1');
    if (known || read(ACCESS) === '1') draw(host, game, mode); else host.hidden = true;
    if (known) { write(ACCESS, '1'); return; }
    if (await access()) { if (host.hidden) draw(host, game, mode); } else host.hidden = true;
  }

  // «+N опыта Пропуска» на экране итога обычной игры: сервер уже записал опыт вместе с результатом, здесь только читаем.
  // Без доступа к Лиге, без сети или когда игра опыта не дала — строки нет.
  async function passXp(game, runId, el) {
    if (!el) return;
    el.hidden = true;
    if (!runId || read(ACCESS) !== '1') return;
    try {
      const r = await fetch(`${base}/league-demo/api/pass/casual/${game}/${encodeURIComponent(runId)}`, {headers: headers()});
      const d = r.ok ? await r.json() : null;
      if (!d?.active || !d.counted || el.dataset.run !== String(runId)) return;
      el.textContent = d.xp ? `+${d.xp} опыта Пропуска${d.today >= d.cap ? ' · дневной предел из обычных игр набран' : ''}`
        : `Опыт Пропуска из обычных игр на сегодня набран (${d.cap}). Уровни «Рейтинга» дают опыт без предела.`;
      el.hidden = false;
    } catch (_) { /* нет сети: строка не нужна */ }
  }

  document.querySelectorAll('[data-game-mode]').forEach(host => mount(host, {game: host.dataset.gameMode, mode: host.dataset.gmode}));
  window.GameMode = {mount, passXp, headers, PAGES, last: game => read(MODE + game), allowed: () => read(ACCESS) === '1'};
})();
