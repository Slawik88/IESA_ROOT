// Лига: рейтинговый режим одной игры (/league?game=rhythm|minesweeper) и Пропуск сезона (/league#pass).
// Вкладок нет: «Обычный | Рейтинг» сверху (game-mode-v3.js) — тот же переключатель, что на страницах игр, а Пропуск — полоска с опытом.
// До сезона 2 — демо раннего доступа, с ним — для всех.
// Лестница и топ — league-ladder.js, игры — league-mines.js и league-rhythm.js, Пропуск — league-pass.js, итог уровня — league-result.js.
// Сервер — единственный источник правил и звёзд; здесь только показ.
(() => {
  const webApp = () => window.Telegram?.WebApp || null;   // скрипт Telegram грузится асинхронно
  const base = document.body.dataset.appBase || '';
  const Fx = () => window.LeagueFx;
  let session = '';
  try { session = localStorage.getItem('pv_sess') || ''; } catch (_) { session = ''; }
  const headers = () => {
    const app = webApp();
    const init = (app && app.initData) || new URLSearchParams(location.hash.slice(1)).get('tgWebAppData') || '';
    const h = {'Content-Type': 'application/json'};
    if (init) h['x-init-data'] = init;
    if (session) h['x-session-token'] = session;
    return h;
  };
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const stars = n => '★'.repeat(n) + '☆'.repeat(3 - n);
  const GAMES = ['minesweeper', 'rhythm'], NAMES = {minesweeper: 'Сапёр', rhythm: 'Ритм'};
  const asked = new URLSearchParams(location.search).get('game');
  // view — что на экране; game — игра, из которой пришли (к ней ведёт «‹» из Пропуска)
  const state = {view: 'minesweeper', game: GAMES.includes(asked) ? asked : null, me: null, pass: null};
  const SKELETON = '<div class="lg-skel" aria-hidden="true"><i class="w40"></i><i class="h96"></i><i class="h48 w60"></i><i></i><i class="w80"></i></div><p class="lg-sr">Загружаем…</p>';

  async function api(path, options = {}) {
    let response;
    try {
      response = await fetch(base + '/league-demo/api' + path, {...options, headers: headers()});
    } catch (_) {
      throw new Error('Нет связи. Проверь интернет и попробуй ещё раз.');
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) { const error = new Error(data.detail || 'Ответа нет. Попробуй ещё раз.'); error.status = response.status; throw error; }
    return data;
  }

  // Тема: как у Telegram (светлая/тёмная); надетый образ задаёт свою палитру и важнее темы (skin-runtime-v3.js)
  // Тёмная, как меню и страницы игр: переключатель «Обычный | Рейтинг» не должен мигать светлым экраном.
  // Светлая палитра в CSS остаётся на случай, если всё приложение получит светлую тему.
  function theme() {
    document.documentElement.dataset.theme = 'dark';
  }

  // Шапка, дни до конца и полоска Пропуска — общие с обычным режимом (game-shell-v3.js)
  const Shell = () => window.GameShell;
  const summary = () => Shell().summary(state.pass, state.me?.demo ? state.me.pass : null);

  // Шапка: игра или «Пропуск сезона», номер сезона, сколько дней осталось; «‹» из Пропуска возвращает к игре, из игры — в меню игр
  function hero() {
    const demo = state.me?.demo, pass = state.view === 'pass';
    const season = !state.me ? 'Сезон' : demo ? 'Ранний доступ · демо' : `Сезон ${String(state.me.season).replace(/^s/, '')}`;
    $('lg-eyebrow').textContent = pass || !state.me ? season : `${season} · рейтинг`;
    $('lg-title').textContent = pass ? 'Пропуск сезона' : NAMES[state.view];
    document.title = `${pass ? 'Пропуск сезона' : NAMES[state.view] + ' · рейтинг'} — Предвестник`;
    $('lg-note').classList.toggle('lg-hidden', !demo);
    Shell().paintDays(Shell().summary(state.pass));
    const link = $('lg-back-link'), inPage = pass && state.game;
    link.setAttribute('aria-label', inPage ? `Назад: ${NAMES[state.game]}` : 'Назад к играм');
    link.onclick = inPage ? event => { event.preventDefault(); go(state.game, -1); } : null;
  }

  // Полоска Пропуска под переключателем: уровень, опыт до следующего, сколько наград ждёт. Нажатие — экран Пропуска.
  function strip() {
    const sum = summary();
    if (sum && !state.me?.demo) Shell().remember(sum);   // обычный режим нарисует то же с первого кадра
    Shell().paintStrip(sum, () => go('pass', 1), state.view === 'pass');
  }

  function go(view, dir) {
    if (view === state.view) return;
    state.view = view;
    if (view !== 'pass') state.game = view;
    try { history.replaceState(null, '', view === 'pass' ? (state.game ? `?game=${state.game}#pass` : '#pass') : `?game=${view}`); } catch (_) { /* file:// */ }
    render(dir);
    window.scrollTo({top: 0});
  }

  function render(dir = 0) {
    hero();
    const mode = $('lg-mode');
    if (!state.me) {   // до ответа сервера: переключатель и полоска из памяти, чтобы шапка стояла на месте с первого кадра (без доступа их не видно)
      if (state.view !== 'pass' && mode.dataset.game !== state.view) { mode.dataset.game = state.view; window.GameMode.mount(mode, {game: state.view, mode: 'ranked'}); }
      Shell().paintStrip(Shell().cached(), () => go('pass', 1), state.view === 'pass');
      Shell().paintDays(Shell().cached());
      return;
    }
    if (state.view === 'pass') mode.hidden = true;
    else if (mode.dataset.game !== state.view || mode.hidden) { mode.dataset.game = state.view; window.GameMode.mount(mode, {game: state.view, mode: 'ranked', known: true}); }
    strip();
    const view = $('lg-view');
    if (state.view !== 'pass') window.LeagueLadder.render(view, state.view);
    else if (state.me.demo) window.LeagueLadder.demoPass(view);
    else window.LeaguePass?.render(view);
    if (dir) Fx().enter(view, dir);
  }

  async function refresh() {
    try {
      const [me, pass] = await Promise.all([api('/me'), api('/pass').catch(() => null)]);
      state.me = me; state.pass = pass;
      render();
    } catch (error) {
      const closed = error.status === 403 || error.status === 401;
      $('lg-view').innerHTML = `<div class="lg-empty"><h2>${closed ? 'Ранний доступ закрыт' : 'Не загрузилось'}</h2><p class="lg-error" role="alert">${esc(error.message)}</p>
        ${closed ? '' : '<button type="button" id="lg-retry">Повторить</button>'}</div>`;
      if (!closed) $('lg-retry').onclick = () => { $('lg-view').innerHTML = SKELETON; refresh(); };
    }
  }

  // Сброс демо: подтверждение в листе, а не confirm()
  function resetDemo() {
    Fx().sheet('Сбросить прогресс демо?', '<p class="lg-rules">Уровни и звёзды демо рейтинга начнутся заново. Настоящий сезон это не трогает.</p>', [
      {l: 'Сбросить', f: async () => {
        try { await api('/reset', {method: 'POST', body: '{}'}); await refresh(); } catch (error) { Fx().toast(esc(error.message), 'is-bad'); }
      }},
      {l: 'Отмена', ghost: true},
    ]);
  }

  // Экран уровня приходит справа, возврат к лестнице — слева
  function show(html, dir = 0) {
    const play = $('lg-play'), entering = play.classList.contains('lg-hidden');
    $('lg-view').classList.add('lg-hidden'); play.classList.remove('lg-hidden'); play.innerHTML = html;
    document.body.classList.add('lg-playing');   // во время уровня вкладки скрыты: случайное касание не обрывает забег
    if (entering || dir) Fx().enter(play, dir || 1);
    return play;
  }
  function back() {
    $('lg-play').classList.add('lg-hidden'); $('lg-view').classList.remove('lg-hidden');
    document.body.classList.remove('lg-playing');
    Fx().enter($('lg-view'), -1);
    refresh();
  }
  function haptic(kind) { const app = webApp(); try { if (app && Number(app.version || 0) >= 6.1) app.HapticFeedback.impactOccurred(kind); } catch (_) { /* no haptics */ } }

  function play(game, level) {
    const runner = window.LeagueGames?.[game];
    if (!runner) return;
    runner.start(level).catch(error => { show(`<div class="lg-empty"><h2>Уровень не открылся</h2><p class="lg-error" role="alert">${esc(error.message)}</p><button type="button" id="lg-back">К уровням</button></div>`); $('lg-back').onclick = back; });
  }

  window.League = {api, show, back, esc, stars, haptic, $, state, play, refresh, resetDemo, plural: window.GameShell.plural};
  // Старая ссылка /league без игры открывает ту, в которую играли последней
  if (location.hash === '#pass') state.view = 'pass';
  else state.view = state.game || GAMES.find(g => window.GameMode.last(g) === 'ranked') || 'minesweeper';
  if (state.view !== 'pass') state.game = state.view;
  theme();
  render();
  $('lg-view').innerHTML = SKELETON;
  window.addEventListener('load', () => {
    const app = webApp();
    if (app) { try { app.ready(); app.expand(); app.onEvent?.('themeChanged', theme); } catch (_) { /* old client */ } }
    theme();
    fetch(base + '/skins-v3/me', {headers: headers()}).then(r => r.ok ? r.json() : null).then(skin => window.applyGlobalSkinV3?.(skin)).catch(() => {});
    refresh();
  });
})();
