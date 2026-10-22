// Пропуск сезона (с сезона 2): опыт за уровни Лиги и, меньше, за обычные игры; бесплатная и VIP-дорожки, «Забрать».
// Числа и награды присылает сервер (GET /league-demo/api/pass), выдачу делает только он (POST .../pass/claim).
(() => {
  const L = () => window.League;
  let busy = false;
  const MARK = {claimed: '✓', ready: '●', locked: '', vip: '👑'};
  const date = iso => new Date(iso).toLocaleDateString('ru-RU', {day: 'numeric', month: 'long', timeZone: 'UTC'});

  function season(s, me) {
    const ready = s.track.reduce((n, r) => n + (r.free.state === 'ready') + (r.vip.state === 'ready'), 0);
    const rows = s.track.map(r => `<li class="${r.level <= s.level ? 'me' : ''}"><span>${r.level}</span>
      <span>${MARK[r.free.state]} ${L().esc(r.free.text)}</span><b>${MARK[r.vip.state] || '👑'} ${L().esc(r.vip.text)}</b></li>`).join('');
    const why = !me.account.eligible ? `Награды выдаются аккаунтам, которые в боте не меньше ${me.account.min_days} дней. Опыт копится.`
      : ready ? '' : 'Новых наград пока нет — копи опыт.';
    return `<h2>Пропуск сезона ${s.season}${s.current ? '' : ' (закончился)'}</h2>
      <p class="lg-sub">${s.current ? `До ${date(s.ends_at)}` : `Забрать можно до ${date(s.claim_until)}`}${me.vip ? ' · 👑 VIP-дорожка открыта' : ' · VIP-дорожка — с активным VIP'}</p>
      <div class="lg-stats"><div><b>${s.level}</b><small>уровень из ${s.levels}</small></div><div><b>${s.xp}</b><small>опыта</small></div><div><b>${s.xp_to_next}</b><small>до следующего</small></div></div>
      <div class="lg-row">${ready && me.account.eligible ? `<button type="button" data-claim="${s.season}">Забрать награды (${ready})</button>` : ''}</div>
      ${why ? `<p class="lg-rules">${why}</p>` : ''}<p class="lg-error" role="alert" id="lp-err-${s.season}"></p>
      <h3>Бесплатно · 👑 VIP</h3><ol class="lg-top lg-pass">${rows}</ol>`;
  }

  function rules(me) {
    return `<h3>Как копить опыт</h3><p class="lg-rules">Главное — уровни Лиги: ★ 60, ★★ 80, ★★★ 100 опыта, один раз за уровень в сезоне (улучшил звёзды — получаешь разницу).
      Обычные игры дают меньше: Ритм — 1 опыт за 300 очков (до 60 за забег), победа в Сапёре — 12 / 20 / 40 по сложности.
      Из обычных игр за день засчитывается до ${me.casual.cap} опыта (сегодня ${me.casual.today}).</p>
      <p class="lg-rules">🗝 Ключ открывает сундук: «3★+» значит, что звёзд у сундука будет не меньше трёх. В сундуках — еда, карточки питомцев, джокеры, Мора, алмазы. Скинов в Пропуске нет.</p>`;
  }

  async function render(host) {
    host.innerHTML = '<p class="lg-muted">Загружаем Пропуск…</p>';
    let me;
    try { me = await L().api('/pass'); } catch (error) {
      host.innerHTML = `<p class="lg-error" role="alert">${L().esc(error.message)}</p><div class="lg-row"><button type="button" id="lp-retry">Повторить</button></div>`;
      L().$('lp-retry').onclick = () => render(host);
      return;
    }
    if (!me.active) { host.innerHTML = `<h2>Пропуск сезона</h2><p class="lg-rules">Новый Пропуск откроется ${date(me.starts_at)}.</p>`; return; }
    host.innerHTML = me.seasons.map(s => season(s, me)).join('') + rules(me);
    host.querySelectorAll('[data-claim]').forEach(b => { b.onclick = () => claim(host, Number(b.dataset.claim), b); });
  }

  async function claim(host, number, button) {
    if (busy) return;
    busy = true; button.disabled = true;
    let problem = '';
    try {
      const r = await L().api('/pass/claim', {method: 'POST', body: JSON.stringify({season: number})});
      L().haptic('medium');
      alert('Получено:\n' + r.granted.map(g => `• ${g.text}${g.track === 'vip' ? ' (VIP)' : ''}`).join('\n'));
    } catch (error) {
      problem = error.message;   // при обрыве связи награды могли уже выдаться: экран перечитывается и это покажет
    } finally {
      busy = false;
    }
    await render(host);
    const el = L().$('lp-err-' + number);
    if (el && problem) el.textContent = problem;
  }

  window.LeaguePass = {render};
})();
