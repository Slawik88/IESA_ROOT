// Демо Лиги (ранний доступ): вкладки, лестница уровней со звёздами, топ, демо-Пропуск. Игры — league-mines.js и league-rhythm.js.
// Сервер — единственный источник правил и звёзд; опыт и награды здесь ненастоящие.
(() => {
  const webApp = () => window.Telegram?.WebApp || null;   // скрипт Telegram грузится асинхронно
  const base = document.body.dataset.appBase || '';
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
  const state = {tab: 'minesweeper', me: null};
  const NAMES = {minesweeper: 'Сапёр', rhythm: 'Ритм'};

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

  function levelGrid(game, info) {
    const first = Math.max(1, info.unlocked - 9), cells = [];
    for (let n = first; n < first + 15; n++) {
      const got = info.levels[String(n)]?.stars || 0, open = n <= info.unlocked;
      cells.push(`<button type="button" class="lg-level ${n === info.unlocked ? 'next' : ''} ${open ? '' : 'locked'}" ${open ? `data-play="${n}"` : 'disabled'}
        aria-label="Уровень ${n}${open ? (got ? `, звёзд ${got} из 3` : ', открыт') : ', закрыт'}">${n}<small>${open ? stars(got) : '🔒'}</small></button>`);
    }
    return `<div class="lg-levels">${cells.join('')}</div>`;
  }

  const RULES = {
    minesweeper: `<p class="lg-rules">Уровни идут лестницей: поле растёт с 3×3 до 12×16, мин больше, а логика глубже. <b>Каждое поле решается без угадывания</b> — сервер проверяет это до того, как ты его увидишь, и сам открывает старт.</p>
      <p class="lg-rules">★ — поле пройдено, открыт следующий уровень. ★★ — без единого неверного флага. ★★★ — ещё и за щедрое время (таймер не главное: его хватает с запасом).</p>`,
    rhythm: `<p class="lg-rules">Уровень — короткий забег на 30–60 тактов: дойди до конца, сохранив хотя бы одно сердце. С каждым уровнем окно нажатия уже. <b>Дары уровня одинаковые у всех</b>, любой дар можно пропустить.</p>
      <p class="lg-rules">★ — дошёл до конца. ★★ — 70% эталонного счёта. ★★★ — 90%. Игра идёт на телефоне без задержек, сервер проверяет уровень в паузе после него.</p>`,
  };

  function renderGame(game) {
    const info = state.me.games[game];
    const top = info.top.length ? info.top.map(r => `<li class="${r.me ? 'me' : ''}"><span>${r.place}</span><span>${esc(r.name)}</span><b>ур. ${r.level} · ${r.stars}★</b></li>`).join('')
      : '<li><span></span><span>Пока никто не прошёл ни одного уровня</span><b></b></li>';
    $('lg-view').innerHTML = `<h2>${NAMES[game]} · рейтинг</h2>
      <div class="lg-stats"><div><b>${info.unlocked}</b><small>следующий уровень</small></div><div><b>${info.stars}</b><small>звёзд</small></div><div><b>${Math.max(0, info.unlocked - 1)}</b><small>пройдено</small></div></div>
      <h3>Уровни</h3>${levelGrid(game, info)}
      <div class="lg-row"><button type="button" data-play="${info.unlocked}">Играть уровень ${info.unlocked}</button></div>
      <h3>Как устроено</h3>${RULES[game]}
      <h3>Топ сезона (демо)</h3><ol class="lg-top">${top}</ol>
      <div class="lg-row"><button type="button" class="secondary" id="lg-reset">Сбросить мой прогресс демо</button></div>`;
    $('lg-view').querySelectorAll('[data-play]').forEach(b => { b.onclick = () => play(game, Number(b.dataset.play)); });
    $('lg-reset').onclick = resetDemo;
  }

  function renderPass() {
    const p = state.me.pass;
    const rows = p.track.map(r => `<li class="${r.reached ? 'me' : ''}"><span>${r.level}</span><span>${esc(r.free)}</span><b>👑 ${esc(r.vip)}</b></li>`).join('');
    $('lg-view').innerHTML = `<h2>Пропуск сезона (демо)</h2>
      <p class="lg-rules">Опыт дают только пройденные рейтинговые уровни: ★ — ${state.me.xp_by_stars[1]}, ★★ — ${state.me.xp_by_stars[2]}, ★★★ — ${state.me.xp_by_stars[3]} опыта, один раз за уровень в сезоне (улучшил звёзды — получаешь разницу).</p>
      <div class="lg-stats"><div><b>${p.level}</b><small>уровень из ${p.levels}</small></div><div><b>${p.xp}</b><small>опыта</small></div><div><b>${p.xp_to_next}</b><small>до следующего</small></div></div>
      <h3>Бесплатно · 👑 VIP</h3><ol class="lg-top">${rows}</ol>
      <p class="lg-demo-note">Награды показаны для примера и не выдаются. Скинов в Пропуске нет.</p>`;
  }

  function render() {
    document.querySelectorAll('.lg-tabs button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === state.tab)));
    if (!state.me) return;
    if (state.tab === 'pass') renderPass(); else renderGame(state.tab);
  }

  async function refresh() {
    try {
      state.me = await api('/me');
      render();
    } catch (error) {
      const closed = error.status === 403 || error.status === 401;
      $('lg-view').innerHTML = `<h2>${closed ? 'Ранний доступ закрыт' : 'Лига не загрузилась'}</h2><p class="lg-error" role="alert">${esc(error.message)}</p>
        ${closed ? '' : '<div class="lg-row"><button type="button" id="lg-retry">Повторить</button></div>'}`;
      if (!closed) $('lg-retry').onclick = refresh;
    }
  }

  async function resetDemo() {
    if (!confirm('Сбросить твой прогресс в демо Лиги?')) return;
    try { await api('/reset', {method: 'POST', body: '{}'}); await refresh(); } catch (error) { alert(error.message); }
  }

  function show(html) { $('lg-view').classList.add('lg-hidden'); $('lg-play').classList.remove('lg-hidden'); $('lg-play').innerHTML = html; }
  function back() { $('lg-play').classList.add('lg-hidden'); $('lg-view').classList.remove('lg-hidden'); refresh(); }
  function haptic(kind) { const app = webApp(); try { if (app && Number(app.version || 0) >= 6.1) app.HapticFeedback.impactOccurred(kind); } catch (_) { /* no haptics */ } }

  function play(game, level) {
    const runner = window.LeagueGames?.[game];
    if (!runner) return;
    runner.start(level).catch(error => { show(`<h2>Уровень не открылся</h2><p class="lg-error" role="alert">${esc(error.message)}</p><div class="lg-row"><button type="button" id="lg-back">К уровням</button></div>`); $('lg-back').onclick = back; });
  }

  window.League = {api, show, back, esc, stars, haptic, $};
  document.querySelectorAll('.lg-tabs button').forEach(b => { b.onclick = () => { state.tab = b.dataset.tab; render(); }; });
  window.addEventListener('load', () => {
    const app = webApp();
    if (app) { try { app.ready(); app.expand(); } catch (_) { /* old client */ } }
    refresh();
  });
})();
