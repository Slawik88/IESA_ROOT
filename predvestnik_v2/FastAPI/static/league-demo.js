// Лига: оболочка (герой сезона, вкладки, переходы), до сезона 2 — демо раннего доступа, с ним — для всех.
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
  const TABS = ['minesweeper', 'rhythm', 'pass'];
  const state = {tab: 'minesweeper', me: null, pass: null};
  const SKELETON = '<div class="lg-skel" aria-hidden="true"><i class="w40"></i><i class="h96"></i><i class="h48 w60"></i><i></i><i class="w80"></i></div><p class="lg-sr">Загружаем Лигу…</p>';

  async function api(path, options = {}) {
    let response;
    try {
      response = await fetch(base + '/league-demo/api' + path, {...options, headers: headers()});
    } catch (_) {
      throw new Error('Нет связи. Проверь интернет и попробуй ещё раз.');
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) { const error = new Error(data.detail || 'Сервер не ответил.'); error.status = response.status; throw error; }
    return data;
  }

  // Тема: как у Telegram (светлая/тёмная); надетый образ задаёт свою палитру и важнее темы (skin-runtime-v3.js)
  function theme() {
    const scheme = webApp()?.colorScheme || (window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    document.documentElement.dataset.theme = scheme === 'light' ? 'light' : 'dark';
  }

  function tabs(dir) {
    const index = TABS.indexOf(state.tab);
    document.querySelectorAll('.lg-tabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === state.tab)));
    const thumb = document.querySelector('.lg-tabs-thumb');
    if (thumb) thumb.style.transform = `translateX(${index * 100}%)`;
    return dir;
  }

  // Шапка: номер сезона, сколько дней осталось, точка на «Пропуске», если есть что забрать
  function hero() {
    const demo = state.me?.demo;
    $('lg-eyebrow').textContent = !state.me ? 'Лига' : demo ? 'Ранний доступ · демо' : `Сезон ${String(state.me.season).replace(/^s/, '')}`;
    $('lg-note').classList.toggle('lg-hidden', !demo);
    const current = state.pass?.active && state.pass.seasons.find(s => s.current);
    const days = current ? Math.max(0, Math.ceil((Date.parse(current.ends_at) - Date.now()) / 864e5)) : null;
    $('lg-days').hidden = days === null;
    if (days !== null) { $('lg-days').innerHTML = `<b data-count="days">${days}</b><small>${plural(days, 'день', 'дня', 'дней')} до конца</small>`; Fx().count($('lg-days')); }
    const ready = state.pass?.active && state.pass.account?.eligible ? state.pass.seasons.reduce((n, s) => n + s.track.filter(r => r.free.state === 'ready').length
      + s.track.filter(r => r.vip.state === 'ready').length, 0) : 0;
    document.querySelector('[data-tab="pass"]').classList.toggle('has-dot', ready > 0);
  }
  const plural = (n, one, few, many) => n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? few : many;

  function render(dir = 0) {
    tabs(dir);
    if (!state.me) return;
    hero();
    const view = $('lg-view');
    if (state.tab !== 'pass') window.LeagueLadder.render(view, state.tab);
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
      $('lg-view').innerHTML = `<div class="lg-empty"><h2>${closed ? 'Ранний доступ закрыт' : 'Лига не загрузилась'}</h2><p class="lg-error" role="alert">${esc(error.message)}</p>
        ${closed ? '' : '<button type="button" id="lg-retry">Повторить</button>'}</div>`;
      if (!closed) $('lg-retry').onclick = () => { $('lg-view').innerHTML = SKELETON; refresh(); };
    }
  }

  // Сброс демо: подтверждение в листе, а не confirm()
  function resetDemo() {
    Fx().sheet('Сбросить прогресс демо?', '<p class="lg-rules">Уровни и звёзды демо Лиги начнутся заново. Настоящий сезон это не трогает.</p>', [
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

  window.League = {api, show, back, esc, stars, haptic, $, state, play, refresh, resetDemo, plural};
  if (location.hash === '#pass') state.tab = 'pass';
  theme();
  tabs(0);
  $('lg-view').innerHTML = SKELETON;
  document.querySelectorAll('.lg-tabs button').forEach(b => {
    b.onclick = () => {
      if (b.dataset.tab === state.tab) return;
      const dir = Math.sign(TABS.indexOf(b.dataset.tab) - TABS.indexOf(state.tab));
      state.tab = b.dataset.tab;
      render(dir);
    };
  });
  window.addEventListener('load', () => {
    const app = webApp();
    if (app) { try { app.ready(); app.expand(); app.onEvent?.('themeChanged', theme); } catch (_) { /* old client */ } }
    theme();
    fetch(base + '/skins-v3/me', {headers: headers()}).then(r => r.ok ? r.json() : null).then(skin => window.applyGlobalSkinV3?.(skin)).catch(() => {});
    refresh();
  });
})();
