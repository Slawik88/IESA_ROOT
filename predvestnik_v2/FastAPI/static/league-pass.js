// Пропуск сезона (с сезона 2): опыт за уровни Лиги и, меньше, за обычные игры; бесплатная и VIP-дорожки, «Забрать».
// Числа и награды присылает сервер (GET /league-demo/api/pass), выдачу делает только он (POST .../pass/claim).
// Вид: лента по уровням (scroll-snap), текущий уровень по центру; «Забрать» — награды по очереди летят в сундук, итог в листе.
(() => {
  const L = () => window.League, A = () => window.LeagueArt, Fx = () => window.LeagueFx;
  let busy = false;
  const FLY_MAX = 12;
  const date = iso => new Date(iso).toLocaleDateString('ru-RU', {day: 'numeric', month: 'long', timeZone: 'UTC'});
  const STATE = {claimed: 'получено', ready: 'можно забрать', locked: 'ещё не открыто', vip: 'нужен VIP'};

  function cell(level, track, item) {
    const r = A().reward(item.text), st = item.state;
    const badge = st === 'claimed' ? A().icon('check', 'lgp-badge is-done') : st === 'vip' ? A().icon('lock', 'lgp-badge is-lock') : '';
    return `<div class="lgp-cell is-t-${track} is-${st}" data-cell="${level}-${track}" role="listitem" aria-label="Уровень ${level}, ${track === 'vip' ? 'VIP' : 'бесплатно'}: ${L().esc(item.text.replace(/^\S+\s/, ''))}, ${STATE[st]}">
      <span class="lgp-art">${r.art}</span><b>${L().esc(r.short)}</b>${badge}</div>`;
  }

  function season(s, me) {
    const ready = s.track.reduce((n, r) => n + (r.free.state === 'ready') + (r.vip.state === 'ready'), 0), can = ready && me.account.eligible;
    const max = s.level >= s.levels, into = max ? s.xp_per_level : s.xp_per_level - s.xp_to_next;
    const cols = s.track.map(r => `<li class="lgp-col ${r.level <= s.level ? 'is-reached' : ''} ${r.level === Math.min(s.levels, s.level + 1) ? 'is-current' : ''} ${r.level % 10 === 0 ? 'is-mile' : ''}">
      <span class="lgp-num">${r.level}</span>${cell(r.level, 'free', r.free)}${cell(r.level, 'vip', r.vip)}</li>`).join('');
    const why = !me.account.eligible ? `Награды выдаются аккаунтам, которые в боте не меньше ${me.account.min_days} дней. Опыт копится.`
      : ready ? '' : s.current ? 'Новых наград пока нет — проходи уровни Лиги.' : '';
    return `<section class="lgp" data-season="${s.season}" aria-label="Пропуск сезона ${s.season}">
      <div class="lgp-head"><div><small class="lg-eyebrow">Пропуск сезона ${s.season}${s.current ? '' : ' · закончился'}</small>
        <p class="lgp-lvl">Уровень <b data-count="pass-${s.season}">${s.level}</b><small> из ${s.levels}</small></p></div>
        <p class="lgp-vip ${me.vip ? 'is-on' : ''}">${A().icon('crown', 'lgp-crown')}<span>${me.vip ? 'VIP-дорожка открыта' : 'VIP — с активным VIP'}</span></p></div>
      <div class="lgp-xp"><div class="lgp-bar ${can ? 'is-ready' : ''}" role="progressbar" aria-valuemin="0" aria-valuemax="${s.xp_per_level}" aria-valuenow="${into}" aria-label="Опыт до следующего уровня">
        <i style="transform:scaleX(${(into / s.xp_per_level).toFixed(3)})"></i></div>
        <small>${max ? `Все уровни открыты · ${s.xp} опыта` : `${into}/${s.xp_per_level} до уровня ${s.level + 1} · ${s.current ? `до ${date(s.ends_at)}` : `забрать до ${date(s.claim_until)}`}`}</small></div>
      ${can ? `<button type="button" class="lg-cta lgp-claim" data-claim="${s.season}"><span class="lgp-chest">${A().icon('chest')}</span>Забрать награды · ${ready}</button>` : ''}
      ${why ? `<p class="lg-rules">${why}</p>` : ''}<p class="lg-error" role="alert" id="lp-err-${s.season}"></p>
      <div class="lgp-ribbon" tabindex="0" aria-label="Награды по уровням, листай вбок"><div class="lgp-rows" aria-hidden="true"><span>Бесплатно</span><span>${A().icon('crown', 'lg-inline')}VIP</span></div>
        <ol role="list">${cols}</ol></div></section>`;
  }

  function rules(me) {
    return `<details class="lg-help"><summary>Как копить опыт</summary><p class="lg-rules">Главное — уровни Лиги: ★ 60, ★★ 80, ★★★ 100 опыта, один раз за уровень в сезоне (улучшил звёзды — получаешь разницу).
      Обычные игры дают меньше: Ритм — 1 опыт за 300 очков (до 60 за забег), победа в Сапёре — 12 / 20 / 40 по сложности.
      Из обычных игр за день засчитывается до ${me.casual.cap} опыта (сегодня ${me.casual.today}).</p>
      <p class="lg-rules">${A().icon('key', 'lg-inline lga-key--bronze')} Ключ открывает сундук: «3★+» значит, что звёзд у сундука будет не меньше трёх. Металл ключа — его уровень: обычный, бронзовый, серебряный, платиновый.
      В сундуках — еда, карточки питомцев, джокеры, Мора, алмазы. Скинов в Пропуске нет.</p></details>`;
  }

  async function render(host, fresh = null) {
    if (!fresh) host.innerHTML = '<div class="lg-skel" aria-hidden="true"><i class="w60"></i><i class="h48"></i><i class="h96"></i></div><p class="lg-sr">Загружаем Пропуск…</p>';
    let me = fresh;
    try { me = me || await L().api('/pass'); } catch (error) {
      host.innerHTML = `<div class="lg-empty"><p class="lg-error" role="alert">${L().esc(error.message)}</p><button type="button" id="lp-retry">Повторить</button></div>`;
      L().$('lp-retry').onclick = () => render(host);
      return;
    }
    L().state.pass = me;
    if (!me.active) { host.innerHTML = `<div class="lg-empty"><h2>Пропуск сезона</h2><p class="lg-rules">Новый Пропуск откроется ${date(me.starts_at)}.</p></div>`; return; }
    host.innerHTML = me.seasons.map(s => season(s, me)).join('') + rules(me);
    Fx().count(host);
    host.querySelectorAll('[data-claim]').forEach(b => { b.onclick = () => claim(host, Number(b.dataset.claim), b); });
    host.querySelectorAll('.lgp-ribbon').forEach(rb => {
      const cur = rb.querySelector('.lgp-col.is-current');
      if (cur) rb.scrollLeft = cur.offsetLeft - rb.clientWidth / 2 + cur.offsetWidth / 2;
    });
  }

  // Сводка полученного: Мора, алмазы, Зарники суммой, ключи по металлам
  function summary(granted) {
    const sum = {mora: 0, diamonds: 0, zarniki: 0}, keys = {}, NAME = {mora: 'Мора', diamonds: 'Алмазы', zarniki: 'Зарники'}, ART = {mora: 'coin', diamonds: 'gem', zarniki: 'spark'};
    granted.forEach(g => { const r = A().reward(g.text); if (r.kind === 'key') keys[r.tier] = (keys[r.tier] || 0) + 1; else if (r.kind in sum) sum[r.kind] += r.amount; });
    const rows = Object.entries(sum).filter(([, n]) => n).map(([k, n]) => `<li>${A().icon(ART[k], 'lgp-sum-art')}<span>${NAME[k]}</span><b>+<span data-count="sum-${k}">${n}</span></b></li>`)
      .concat(Object.entries(keys).map(([t, n]) => `<li>${A().icon('key', `lgp-sum-art lgp-swing lga-key--${A().METAL[t] || 'iron'}`)}<span>${A().KEY_NAMES[t] || ''} ключ · ${t}★+</span><b>×${n}</b></li>`));
    const vip = granted.filter(g => g.track === 'vip').length;
    return `<ul class="lgp-sum" aria-live="polite">${rows.join('')}</ul>${vip ? `<p class="lg-muted">${A().icon('crown', 'lg-inline')} Из них с VIP-дорожки: ${vip}.</p>` : ''}
      <p class="lg-muted">Ключи уже лежат в «Сундуках», валюта — на балансе.</p>`;
  }

  async function claim(host, number, button) {
    if (busy) return;
    busy = true; button.disabled = true; button.classList.add('is-busy');
    let problem = '', result = null;
    try {
      result = await L().api('/pass/claim', {method: 'POST', body: JSON.stringify({season: number})});
      L().haptic('medium');
    } catch (error) {
      problem = error.message;   // при обрыве связи награды могли уже выдаться: экран перечитывается и это покажет
    }
    if (result) await flights(host, number, result.granted, button);
    busy = false;
    let fresh = null;
    try { fresh = await L().api('/pass'); } catch (_) { fresh = null; }
    await render(host, fresh);
    if (result) Fx().count(Fx().sheet(`${A().icon('chest', 'lgp-sheet-chest')} Получено: ${result.granted.length}`, summary(result.granted), [{l: 'Отлично'}]).host);
    const el = L().$('lp-err-' + number);
    if (el && problem) el.textContent = problem;
  }

  // Награды по очереди вылетают из ленты в сундук на кнопке; ячейка сразу получает галочку
  async function flights(host, number, granted, button) {
    const sec = host.querySelector(`.lgp[data-season="${number}"]`), ribbon = sec?.querySelector('.lgp-ribbon');
    if (!sec || !Fx().moves()) return;
    const first = sec.querySelector(`[data-cell="${granted[0]?.level}-${granted[0]?.track}"]`);
    if (ribbon && first) ribbon.scrollLeft = first.parentElement.offsetLeft - 56;
    const chest = button.querySelector('.lgp-chest') || button, box = ribbon.getBoundingClientRect();
    const jobs = granted.slice(0, FLY_MAX).map((g, i) => {
      const c = sec.querySelector(`[data-cell="${g.level}-${g.track}"]`), r = c?.getBoundingClientRect();
      const from = r && r.left >= box.left - 4 && r.right <= box.right + 4 ? c : ribbon;
      setTimeout(() => { c?.classList.add('is-claimed'); c?.classList.remove('is-ready'); }, i * 90);
      return Fx().fly(from, chest, A().reward(g.text).art, i * 90);
    });
    await Promise.all(jobs);
    await Fx().bump(chest, 1.3);
  }

  window.LeaguePass = {render};
})();
