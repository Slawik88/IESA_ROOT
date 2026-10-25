// Пропуск сезона (с сезона 2): опыт за уровни Лиги и, меньше, за обычные игры; бесплатная и VIP-дорожки, «Забрать».
// Числа и награды присылает сервер (GET /league-demo/api/pass), выдачу делает только он (POST .../pass/claim).
// Вид: лента по уровням (scroll-snap), текущий уровень по центру; «Забрать» — награды по очереди летят в сундук, итог в листе.
(() => {
  const L = () => window.League, A = () => window.LeagueArt, Fx = () => window.LeagueFx;
  let busy = false, refreshTimer = null, renderId = 0;
  const FLY_MAX = 12;
  const date = iso => new Date(iso).toLocaleDateString('ru-RU', {day: 'numeric', month: 'long', timeZone: 'UTC'});
  const STATE = {claimed: 'получено', ready: 'можно забрать', locked: 'ещё не открыто', vip: 'нужен VIP от 1 месяца'};

  function repeat(s, me) {
    const r = s.repeat;
    if (!s.current || !r) return '';
    const locked = s.level < s.levels;
    const until = r.next_claim_at && new Date(r.next_claim_at);
    const wait = !r.ready && until && until.getTime() > Date.now();
    const time = wait ? until.toLocaleString('ru-RU', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'}) : '';
    let status = 'Обнови экран Пропуска';
    if (locked) status = `После уровня ${s.levels}`;
    else if (!me.account.eligible) status = `Аккаунту нужно ${me.account.min_days} дней`;
    else if (r.ready) status = 'Можно забрать';
    else if (wait) status = `Снова ${time}`;
    else if (r.banked_xp < r.xp_per_claim) status = `Ещё ${r.xp_per_claim - r.banked_xp} опыта`;
    return `<li class="lgp-col lgp-repeat-col ${locked ? '' : 'is-current is-reached'}">
      <span class="lgp-num">${r.level}</span>
      <div class="lgp-cell lgp-repeat-cell ${locked ? 'is-locked' : r.ready && me.account.eligible ? 'is-ready' : ''}" data-cell="${r.level}-free" role="listitem" aria-label="Уровень ${r.level}, возобновляемый, для всех. Обычный ключ от ${r.key_tier} звезды за ${r.xp_per_claim} опыта, раз в ${r.wait_hours} часов. ${L().esc(status)}">
        <span class="lgp-repeat-badge">↻ Возобновляемый</span>
        <span class="lgp-art">${A().icon('key', `lga-key--${A().METAL[r.key_tier] || 'iron'}`)}</span>
        <b>Обычный ключ · ${r.key_tier}★+</b>
        <small>${r.xp_per_claim} опыта · раз в ${r.wait_hours} ч</small>
        <strong>${locked ? 'Откроется после финала' : `${r.banked_xp} опыта в запасе`}</strong>
        <small class="lgp-repeat-state">${L().esc(status)}${wait && !locked && me.account.eligible ? '<span>твоё время</span>' : ''}</small>
        <span class="lgp-repeat-note">Одна награда для всех</span>
      </div></li>`;
  }

  function cell(level, track, item) {
    const r = A().reward(item.text), st = item.state;
    const badge = st === 'claimed' ? A().icon('check', 'lgp-badge is-done') : st === 'vip' ? A().icon('lock', 'lgp-badge is-lock') : '';
    return `<div class="lgp-cell is-t-${track} is-${st}" data-cell="${level}-${track}" role="listitem" aria-label="Уровень ${level}, ${track === 'vip' ? 'VIP' : 'бесплатно'}: ${L().esc(item.text.replace(/^\S+\s/, ''))}, ${STATE[st]}">
      <span class="lgp-art">${r.art}</span><b>${L().esc(r.short)}</b>${badge}</div>`;
  }

  function season(s, me) {
    const ready = s.track.reduce((n, r) => n + (r.free.state === 'ready') + (r.vip.state === 'ready'), 0) + Number(!!(s.current && s.repeat?.ready)), can = ready && me.account.eligible;
    const max = s.level >= s.levels, into = max ? s.xp_per_level : s.xp_per_level - s.xp_to_next;
    const cols = s.track.map(r => `<li class="lgp-col ${r.level <= s.level ? 'is-reached' : ''} ${r.level === s.level + 1 ? 'is-current' : ''} ${r.level % 10 === 0 ? 'is-mile' : ''}">
      <span class="lgp-num">${r.level}</span>${cell(r.level, 'free', r.free)}${cell(r.level, 'vip', r.vip)}</li>`).join('');
    const why = !me.account.eligible ? `Забрать награды можно, когда аккаунту исполнится ${me.account.min_days} дней. Опыт копится уже сейчас.`
      : '';
    return `<section class="lgp" data-season="${s.season}" aria-label="Пропуск сезона ${s.season}">
      <div class="lgp-head"><div>${s.current ? '' : `<small class="lg-eyebrow">Пропуск сезона ${s.season} · закончился</small>`}
        <p class="lgp-lvl">Уровень <b data-count="pass-${s.season}">${s.level}</b><small> из ${s.levels}</small></p></div>
        <p class="lgp-vip ${me.vip ? 'is-on' : ''}">${A().icon('crown', 'lgp-crown')}<span>${me.vip ? 'VIP-дорожка открыта' : 'VIP от 1 месяца'}</span></p></div>
      <div class="lgp-xp"><div class="lgp-bar ${can ? 'is-ready' : ''}" role="progressbar" aria-valuemin="0" aria-valuemax="${s.xp_per_level}" aria-valuenow="${into}" aria-label="Опыт до следующего уровня">
        <i style="transform:scaleX(${(into / s.xp_per_level).toFixed(3)})"></i></div>
        <small>${max ? `Все уровни открыты · ${s.xp} опыта` : `${into}/${s.xp_per_level} до уровня ${s.level + 1} · ${s.current ? `до ${date(s.ends_at)}` : `забрать до ${date(s.claim_until)}`}`}</small></div>
      ${can ? `<button type="button" class="lg-cta lgp-claim" data-claim="${s.season}"><span class="lgp-chest">${A().icon('chest')}</span>Забрать награды · ${ready}</button>` : ''}
      ${why ? `<p class="lg-rules">${why}</p>` : ''}<p class="lg-error" role="alert" id="lp-err-${s.season}"></p>
      <div class="lgp-ribbon" tabindex="0" aria-label="Награды по уровням, листай вбок"><div class="lgp-rows" aria-hidden="true"><span>Бесплатно</span><span>VIP от 1 месяца</span></div>
        <ol role="list">${cols}${repeat(s, me)}</ol></div></section>`;
  }

  async function render(host, fresh = null) {
    const id = ++renderId;
    clearTimeout(refreshTimer);
    if (!fresh) host.innerHTML = '<div class="lg-skel" aria-hidden="true"><i class="w60"></i><i class="h48"></i><i class="h96"></i></div><p class="lg-sr">Загружаем Пропуск…</p>';
    let me = fresh;
    try { me = me || await L().api('/pass'); } catch (error) {
      if (id !== renderId || L().state.view !== 'pass') return;
      host.innerHTML = `<div class="lg-empty"><p class="lg-error" role="alert">${L().esc(error.message)}</p><button type="button" id="lp-retry">Повторить</button></div>`;
      L().$('lp-retry').onclick = () => render(host);
      return;
    }
    if (id !== renderId || L().state.view !== 'pass') return;
    L().state.pass = me;
    if (!me.active) { host.innerHTML = `<div class="lg-empty"><h2>Пропуск сезона</h2><p class="lg-rules">Новый Пропуск откроется ${date(me.starts_at)}.</p></div>`; return; }
    host.innerHTML = me.seasons.map(s => season(s, me)).join('') + window.LeagueHelp.xp(me);
    Fx().count(host);
    host.querySelectorAll('[data-claim]').forEach(b => { b.onclick = () => claim(host, Number(b.dataset.claim), b); });
    host.querySelectorAll('.lgp-ribbon').forEach(rb => {
      const cur = rb.querySelector('.lgp-col.is-current');
      if (cur) rb.scrollLeft = cur.offsetLeft - rb.clientWidth / 2 + cur.offsetWidth / 2;
    });
    const next = me.seasons.find(s => s.current)?.repeat;
    if (next?.next_claim_at && next.banked_xp >= next.xp_per_claim) {
      const delay = new Date(next.next_claim_at).getTime() - Date.now();
      if (delay > 0) refreshTimer = setTimeout(() => {
        if (host.isConnected && L().state.view === 'pass' && !busy) render(host);
      }, delay + 1000);
    }
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
    const id = renderId, current = () => id === renderId && L().state.view === 'pass' && button.isConnected;
    let problem = '', result = null;
    try {
      result = await L().api('/pass/claim', {method: 'POST', body: JSON.stringify({season: number})});
      L().haptic('medium');
      if (current()) await flights(host, number, result.granted, button);
    } catch (error) {
      problem = error.message;   // при обрыве связи награды могли уже выдаться: экран перечитывается и это покажет
    } finally {
      busy = false;
    }
    if (!current()) return;
    let fresh = null;
    try { fresh = await L().api('/pass'); } catch (_) { fresh = null; }
    if (!current()) return;
    await render(host, fresh);
    if (L().state.view !== 'pass') return;
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
      setTimeout(() => { if (!c?.classList.contains('lgp-repeat-cell')) c?.classList.add('is-claimed'); c?.classList.remove('is-ready'); }, i * 90);
      return Fx().fly(from, chest, A().reward(g.text).art, i * 90);
    });
    await Promise.all(jobs);
    await Fx().bump(chest, 1.3);
  }

  window.LeaguePass = {render};
})();
