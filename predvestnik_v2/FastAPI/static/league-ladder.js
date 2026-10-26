// Лестница Лиги: «тропа» медальонов (пройденные со звёздами, текущий под акцентом, закрытые с замком, каждый 10-й — веха),
// превью уровня по нажатию, подиум топа сезона, справка свёрнута. Параметры уровня — те же формулы, что core/league_v1.py
// (mines_level, rhythm_level, rhythm_drafts); совпадение проверяет tools/test_league_preview_parity.py.
(() => {
  const L = () => window.League, A = () => window.LeagueArt, Fx = () => window.LeagueFx;
  const NAMES = {minesweeper: 'Сапёр', rhythm: 'Ритм'};
  const DEPTH = {1: 'простая: хватает одной цифры', 2: 'средняя: сравни две цифры', 3: 'сложная: думай по всей группе'};
  const sec = ms => `${(ms / 1000).toFixed(1).replace('.', ',')} с`;
  const BANDS = [[1, 3, 3], [4, 4, 4], [8, 5, 5], [13, 6, 6], [19, 7, 7], [26, 8, 8], [35, 9, 9], [46, 10, 10], [61, 11, 11], [81, 12, 12], [101, 12, 14], [121, 12, 16]];
  const pyRound = x => { const f = Math.floor(x), d = x - f; return d > .5 ? f + 1 : d < .5 ? f : (f % 2 ? f + 1 : f); };   // round() Питона: половина — к чётному

  function spec(game, level) {
    if (game === 'minesweeper') {
      const [, width, height] = BANDS.filter(b => level >= b[0]).pop();
      const density = Math.min(0.24, 0.10 + 0.0016 * level);
      return {width, height, mines: Math.max(2, pyRound(width * height * density)), tier: level <= 5 ? 1 : level <= 20 ? 2 : 3};
    }
    const signals = Math.min(60, 30 + 2 * Math.floor(level / 4));
    return {signals, window: Math.max(400, Math.trunc(2200 * 0.988 ** (level - 1))), drafts: Math.floor((signals - 1) / 20)};
  }

  function node(game, info, n) {
    const got = info.levels[String(n)]?.stars || 0, open = n <= info.unlocked, next = n === info.unlocked, mile = n % 10 === 0;
    const label = `Уровень ${n}${mile ? ', веха' : ''}${open ? (got ? `, звёзд ${got} из 3` : next ? ', следующий' : ', открыт') : ', закрыт'}`;
    return `<li class="lgl-step ${got ? 'is-done' : ''}"><button type="button" class="lgl-node ${next ? 'is-next' : ''} ${open ? '' : 'is-locked'} ${mile ? 'is-mile' : ''}"
      data-preview="${n}" aria-label="${label}">${next ? '<i class="lgl-halo" aria-hidden="true"></i>' : ''}${mile ? A().icon('medal', 'lgl-medal') : ''}
      <b>${open ? n : A().icon('lock', 'lgl-lock')}</b></button><span class="lgl-stars" aria-hidden="true">${open ? A().stars(got, 'lgl-star') : `<small>${n}</small>`}</span></li>`;
  }

  // Видно до 40 уровней назад и 10 вперёд от текущего (до 1000 уровней не рисуются все сразу)
  function trail(game, info) {
    const first = Math.max(1, Math.floor((info.unlocked - 40) / 10) * 10 + 1), last = Math.max(20, Math.ceil((info.unlocked + 9) / 10) * 10);
    const steps = [];
    for (let n = first; n <= last; n++) steps.push(node(game, info, n));
    return `<div class="lgl-trail"><ol aria-label="Уровни">${steps.join('')}</ol></div>`;
  }

  function playerAvatar(r) {
    return window.leaderboardAvatar ? window.leaderboardAvatar({profile_ref:r.profile_ref,is_vip:r.is_vip,display_name:r.name,avatar:r.avatar}) : '';
  }
  function podium(top) {
    if (!top.length) return '<p class="lg-muted">Пока никто не прошёл ни одного уровня — займи первое место.</p>';
    const medal = p => `<span class="lgl-medal-ico is-p${p}" aria-hidden="true">${p}</span>`;
    const head = [top[1], top[0], top[2]].filter(Boolean).map(r => `<li class="lgl-pod is-p${r.place} ${r.me ? 'is-me' : ''}">${medal(r.place)}
      ${playerAvatar(r)}<b>${L().esc(r.name)}</b><small>ур. ${r.level} · ${r.stars}★</small><i aria-hidden="true"></i></li>`).join('');
    const rest = top.slice(3).map(r => `<li class="${r.me ? 'is-me' : ''}"><span>${r.place}</span><span class="lgl-player">${playerAvatar(r)}${L().esc(r.name)}${r.me ? ' · это ты' : ''}</span><b>ур. ${r.level} · ${r.stars}★</b></li>`).join('');
    return `<ol class="lgl-podium" aria-label="Тройка лидеров">${head}</ol>${rest ? `<ol class="lg-top" start="4">${rest}</ol>` : ''}`;
  }

  function render(host, game) {
    const me = L().state.me, info = me.games[game];
    const passed = Object.values(info.levels).filter(l => l.stars > 0).length;
    host.innerHTML = `<div class="lg-state"><div><b data-count="${game}-next">${info.unlocked}</b><small>следующий уровень</small></div>
        <div><b><span data-count="${game}-stars">${info.stars}</span>${A().icon('star', 'lg-state-star is-on')}</b><small>звёзд</small></div><div><b data-count="${game}-done">${passed}</b><small>пройдено</small></div></div>
      ${trail(game, info)}
      <button type="button" class="lg-cta" data-play="${info.unlocked}">Играть уровень ${info.unlocked}</button>
      <h3 class="lg-eyebrow">Топ сезона${me.demo ? ' (демо)' : ''}</h3>${podium(info.top)}
      ${window.LeagueHelp.rules(game, me.xp_by_stars)}
      ${me.demo ? '<button type="button" class="lg-link" id="lg-reset">Сбросить мой прогресс демо</button>' : ''}`;
    Fx().count(host);
    window.hydrateLeaderboardAvatars?.(host);
    host.querySelector('[data-play]').onclick = () => L().play(game, info.unlocked);
    host.querySelectorAll('[data-preview]').forEach(b => { b.onclick = () => preview(game, info, Number(b.dataset.preview)); });
    if (L().$('lg-reset')) L().$('lg-reset').onclick = L().resetDemo;
    const track = host.querySelector('.lgl-trail'), current = host.querySelector('.lgl-node.is-next');
    if (track && current) track.scrollLeft += current.getBoundingClientRect().left - track.getBoundingClientRect().left - track.clientWidth / 2 + current.offsetWidth / 2;
  }

  function preview(game, info, n) {
    const s = spec(game, n), got = info.levels[String(n)]?.stars || 0, open = n <= info.unlocked;
    const facts = game === 'minesweeper'
      ? [['Поле', `${s.width}×${s.height}`], ['Мин', s.mines], ['Сложность', DEPTH[s.tier]]]
      : [['Нажатий', s.signals], ['Время на нажатие', sec(s.window)], ['Даров', s.drafts ? `${s.drafts} выбор${s.drafts > 1 ? 'а' : ''}` : 'нет']];
    const body = `<div class="lgl-pv">${A().icon(game === 'minesweeper' ? 'mine' : 'frame', 'lgl-pv-art')}<dl>${facts.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl></div>
      <p class="lgl-pv-best" aria-label="Лучший результат: звёзд ${got} из 3">${A().stars(got, 'lgl-pv-star')}<span>${got ? 'Лучший результат' : open ? 'Ещё не пройден' : `Откроется после уровня ${n - 1}`}</span></p>
      ${n % 10 === 0 ? '<p class="lg-muted">Веха: каждый десятый уровень — рубеж сезона.</p>' : ''}`;
    Fx().sheet(`${NAMES[game]} · уровень ${n}`, body, open ? [{l: got ? 'Сыграть ещё' : 'Играть', f: () => L().play(game, n)}, {l: 'Закрыть', ghost: true}] : [{l: 'Понятно'}]);
  }

  // Пропуск демо-сезона (до 25.10): награды для примера
  function demoPass(host) {
    const me = L().state.me, p = me.pass;
    const rows = p.track.map(r => `<li class="${r.reached ? 'is-got' : ''}"><span>${r.level}</span><span>${L().esc(r.free)}</span><b>${A().icon('crown', 'lg-inline')} ${L().esc(r.vip)}</b></li>`).join('');
    host.innerHTML = `<div class="lg-state"><div><b>${p.level}</b><small>уровень из ${p.levels}</small></div><div><b>${p.xp}</b><small>опыта</small></div><div><b>${p.xp_to_next}</b><small>до следующего</small></div></div>
      <p class="lg-demo-note">Награды показаны для примера и не выдаются. Скинов в Пропуске нет.</p>
      <h3 class="lg-eyebrow">Бесплатно · VIP</h3><ol class="lg-top lg-pass">${rows}</ol>
      ${window.LeagueHelp.xp({})}`;
  }

  window.LeagueLadder = {render, demoPass, spec};
})();
