// ── Образы · жажда сбора: образ недели, цель, сеты, альбом, раскрытие наград ────────────
// Всё считает сервер (/skins-v3/me: featured, sets, collection, events). Здесь только показ: награды видны заранее,
// случайности нет, а каждая награда приходит один раз (ключи на сервере). Стили: collect-v3.css.
const _RV_KINDS = new Set(['owned', 'tier', 'set', 'rank', 'row', 'badge', 'featured', 'tour']);
let _rv = null;

function _lkLeft(iso) {
  const ms = Date.parse(iso) - Date.now();
  if (!(ms > 0)) return 'скоро сменится';
  const d = Math.floor(ms / 864e5), h = Math.floor(ms % 864e5 / 36e5);
  return d ? `${d} д ${h} ч` : `${h || 1} ч`;
}
function _lkDate(iso) { const d = new Date(iso); return Number.isNaN(+d) ? '' : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', timeZone: 'UTC' }); }
// Сезон, до которого осталось меньше двух недель: заранее видно, что он откроется сам
function lkSoonHtml(st) {
  const next = st.sets.filter(x => x.season && !x.season.open && !x.complete && Date.parse(x.season.starts_at) - Date.now() < 14 * 864e5)
    .sort((a, b) => Date.parse(a.season.starts_at) - Date.parse(b.season.starts_at))[0];
  if (!next) return '';
  return `<button type="button" class="lk-week" onclick="_lkPick('${next.members[0]}',true);lkTop()"><span class="lk-pring" style="--p:100" aria-hidden="true">${next.glyph}</span><span><small>Скоро сезон · ${_lkDate(next.season.starts_at)}</small><b>${_profileEsc(next.name)}</b>
    <em>Откроется сам через ${_lkLeft(next.season.starts_at)}: ${next.members.length} образа, знак сета и +${fmt(next.bonus_essence)} Эссенции</em></span><i>›</i></button>`;
}
function lkViewSwitch() {
  const tab = (v, t) => `<button type="button" role="tab" aria-selected="${_lk.view === v}" class="${_lk.view === v ? 'is-on' : ''}" onclick="lkView('${v}')">${t}</button>`;
  return `<div class="lk-seg" role="tablist" aria-label="Раздел">${tab('shop', 'Образы')}${tab('album', 'Коллекция')}</div>`;
}
function lkView(v) { if (_lk.view !== v && (v === 'shop' || v === 'album')) { _lk.view = v; _haptic('select'); _lkRender(); lkTop(); } }

// ── Образ недели и ближайшая цель ────────────────────────────────────────────────
function lkWeekHtml(st) {
  const w = st.featured, item = w && _lkItem(w.skin_id);
  if (!item || w.owned) return '';
  return `<button type="button" class="lk-week" onclick="_lkPick('${item.id}',true);lkTop()">${_lkMini(item)}<span><small>Образ недели · ещё ${_lkLeft(w.ends_at)}</small><b>${_profileEsc(item.name)}</b>
    <em>За покупку на этой неделе +${fmt(w.bonus_essence)} Эссенции в подарок</em></span><i>${item.ceiling}</i></button>`;
}
function _lkGoal(st) {
  const c = st.collection, hot = st.sets.find(x => x.season?.open && !x.complete);
  if (hot) {
    const miss = _lkItem(hot.missing[0]);
    return { p: Math.round(100 * hot.have / hot.members.length), n: `${hot.have}/${hot.members.length}`, t: `Сезон «${hot.name}»: ещё ${_lkLeft(hot.season.ends_at)}`,
      s: hot.have ? `Осталось «${miss.name}» за ${_lkPrice(miss.price_zarniki)}. Награда: знак сета ${hot.glyph} и +${fmt(hot.bonus_essence)} Эссенции` : `${hot.members.length} образа, которые можно купить только в сезон. Знак сета ${hot.glyph} и +${fmt(hot.bonus_essence)} Эссенции за сбор`, pick: miss.id };
  }
  const set = st.sets.filter(s => !s.complete && s.have > 0).sort((a, b) => b.have / b.members.length - a.have / a.members.length)[0];
  if (set) {
    const miss = _lkItem(set.missing[0]);
    return { p: Math.round(100 * set.have / set.members.length), n: `${set.have}/${set.members.length}`, t: `${set.name}: ${set.have} из ${set.members.length}`,
      s: `Осталось «${miss.name}» за ${_lkPrice(miss.price_zarniki)}. Награда: знак сета ${set.glyph} и +${fmt(set.bonus_essence)} Эссенции`, pick: miss.id };
  }
  const row = c.rows.find(r => !r.done && r.have > 0 && r.total - r.have === 1), left = row && st.items.find(i => i.ceiling === row.rarity && !i.season && !i.owned);
  if (left) return { p: Math.round(100 * row.have / row.total), n: `${row.have}/${row.total}`, t: `Редкость ${row.rarity}: не хватает одного`, s: `«${left.name}» за ${_lkPrice(left.price_zarniki)}, награда +${fmt(row.bonus_essence)} Эссенции`, pick: left.id };
  const next = c.next_milestone;
  if (next && c.owned > 0 && next.at - c.owned <= 3) return { p: Math.round(100 * c.owned / next.at), n: `${c.owned}/${next.at}`, t: `До ранга «${next.rank}» ещё ${next.at - c.owned}`, s: `Награда +${fmt(next.essence)} Эссенции`, pick: '' };
  return null;
}
function lkGoalHtml(st) {
  const g = _lkGoal(st); if (!g) return '';
  return `<button type="button" class="lk-goal" onclick="${g.pick ? `_lkPick('${g.pick}',true);lkTop()` : "lkView('album')"}"><span class="lk-pring" style="--p:${g.p}">${g.n}</span>
    <span><b>${_profileEsc(g.t)}</b><small>${_profileEsc(g.s)}</small></span><i>›</i></button>`;
}

// ── Сеты: прогресс и награда видны заранее ──────────────────────────────────────
function _lkSets(st) {
  return st.sets.map(s => `<div class="lk-set"><div><b>${s.glyph} ${_profileEsc(s.name)}</b><small>${_profileEsc(s.blurb)}</small>
      <div class="lk-set-meter" aria-hidden="true">${s.members.map(id => `<i class="${s.missing.includes(id) ? '' : 'is-on'}"></i>`).join('')}</div></div>
    <div class="lk-set-end"><span>${s.have} из ${s.members.length}</span><small class="lk-set-prize">${s.complete ? 'Сет собран' : s.season && !s.season.open ? `Откроется через ${_lkLeft(s.season.starts_at)}` : `Знак сета и +${fmt(s.bonus_essence)} Эссенции`}</small>${s.season?.open && !s.complete ? `<small>Сезон, ещё ${_lkLeft(s.season.ends_at)}</small>` : ''}</div>
    <div class="lk-set-row">${s.members.map(id => { const i = _lkItem(id); return `<button type="button" class="lk-pick${id === _lk.sel ? ' is-sel' : ''}${i.owned ? '' : ' is-lock'}" onclick="_lkPick('${id}',true);lkTop()">${_lkMini(i)}<b>${_profileEsc(i.name)}</b><small>${i.owned ? `✓ тир ${i.level}` : i.buyable === false ? 'не продаётся' : `${i.ceiling} · ${_lkPrice(i.price_zarniki)}`}</small></button>`; }).join('')}</div></div>`).join('');
}

// ── Набор Эссенции под ближайший тир ─────────────────────────────────────────────
function lkFitPack(st, item) {
  if (!item || !item.owned || item.maxed || !item.next) return 0;
  const need = item.next.essence - st.essence.balance; if (need <= 0) return 0;
  return (st.essence.packs.find(p => p.essence >= need) || st.essence.packs[st.essence.packs.length - 1]).zarniki;
}
function lkFitNote(st, item) {
  const pack = lkFitPack(st, item); if (!pack) return '';
  const p = st.essence.packs.find(x => x.zarniki === pack), need = item.next.essence - st.essence.balance;
  return `<p class="lk-fit">${p.essence >= need ? `Для тира ${item.next.tier} хватит набора ${pack} ✨ (${fmt(p.essence)} Эссенции)` : `Для тира ${item.next.tier} нужно ещё ${fmt(need)} Эссенции, это больше одного набора`}</p>`;
}

// ── Альбом коллекции ─────────────────────────────────────────────────────────────
function lkAlbumHtml(st) {
  const c = st.collection, pct = Math.round(100 * c.owned / c.total), next = c.next_milestone;
  const hint = next ? `До «${next.rank}» ещё ${next.at - c.owned}. Награда +${fmt(next.essence)} Эссенции.` : 'Вы собрали всю коллекцию.';
  const ladder = c.milestones.map(m => `<li class="${m.done ? 'is-done' : ''}"><i>${m.done ? '✓' : ''}</i><b>${m.at === c.total ? 'Все образы' : `${m.at} образов`}</b><span>${_profileEsc(m.rank)}</span><em>+${fmt(m.essence)}</em></li>`).join('');
  const rows = c.rows.map(r => `<div class="lk-rar"><div class="lk-rar-head"><b>${r.rarity}</b><span>${r.have} из ${r.total}</span><small class="${r.done ? 'is-done' : ''}">${r.done ? 'Собрано ✓' : `+${fmt(r.bonus_essence)} Эссенции за все`}</small></div>
    <div class="lk-set-row">${st.items.filter(i => i.ceiling === r.rarity && !i.season).map(i => `<button type="button" class="lk-pick${i.owned ? '' : ' is-lock'}" onclick="_lkPick('${i.id}',true);lkView('shop')">${_lkMini(i)}<b>${_profileEsc(i.name)}</b><small>${i.owned ? `✓ тир ${i.level}` : _lkPrice(i.price_zarniki)}</small></button>`).join('')}</div></div>`).join('');
  const badges = c.maxed_badges.map(b => `<span class="lk-badge${b.done ? ' is-done' : ''}">${b.done ? '✦ ' : ''}${_profileEsc(b.title)} · ${b.at}</span>`).join('');
  return `<div class="lk-rank"><div class="lk-rank-ring" style="--p:${pct}"><span><b>${c.owned}</b><small>из ${c.total}</small></span></div><h2>${_profileEsc(c.rank)}</h2><p>${_profileEsc(hint)}</p></div>
    <div class="v3-sec"><span class="v3-eyebrow">Ранги</span></div><ul class="lk-ladder">${ladder}</ul>
    <div class="v3-sec"><span class="v3-eyebrow">По редкости</span></div>${rows}
    <div class="v3-sec"><span class="v3-eyebrow">Сеты</span></div>${_lkSets(st)}
    <div class="v3-sec"><span class="v3-eyebrow">Образы на максимуме: ${c.maxed}</span></div><div class="lk-badges">${badges}</div>
    ${st.share_url ? '<button type="button" class="v3-pill v3-pill--ghost lk-share" onclick="lkShare()">Поделиться рангом</button>' : ''}`;
}
function lkShare() {
  const c = _lk.st?.collection, url = _lk.st?.share_url; if (!c || !url) return;
  const text = `Мой ранг в Предвестнике: «${c.rank}». Образов в коллекции: ${c.owned} из ${c.total}. Заходи!`;
  const link = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
  _haptic('select');
  if (typeof tg?.openTelegramLink === 'function') tg.openTelegramLink(link); else window.open(link, '_blank', 'noopener');
}

// ── Раскрытие наград: покупка, тир, сет, ранг ────────────────────────────────────
function _rvCard(e) {
  const gift = n => `Награда: +${fmt(n)} Эссенции.`;
  switch (e.kind) {
    case 'owned': return { mark: e.ceiling, eyebrow: 'Новый образ', title: e.name, text: e.ceiling === 'D' ? 'Он ваш и уже надет. Потолок этого образа D.' : `Он ваш и уже надет. Начинает с тира D, потолок ${e.ceiling}: впереди ступени за Эссенцию.` };
    case 'tier': return { mark: e.tier, eyebrow: e.maxed ? 'Максимальный тир' : 'Новый тир', title: e.name, text: e.maxed ? (e.sig ? 'Фирменная деталь образа раскрыта.' : 'Образ раскрыт полностью.') : `Образ стал богаче: тир ${e.tier}.` };
    case 'set': return { mark: e.glyph, glyph: true, eyebrow: 'Сет собран', title: e.name, text: `Знак сета теперь стоит рядом с титулом. ${gift(e.essence)}` };
    case 'rank': return { mark: '★', eyebrow: 'Новый ранг', title: e.rank, text: `${e.at} образов в коллекции. ${gift(e.essence)}` };
    case 'row': return { mark: e.rarity, eyebrow: 'Редкость собрана', title: `Все образы ${e.rarity}`, text: gift(e.essence) };
    case 'badge': return { mark: '✦', glyph: true, eyebrow: 'Новый значок', title: e.title, text: `Образов на максимуме: ${e.maxed}.` };
    case 'tour': return { mark: e.mark, glyph: !!e.glyph, eyebrow: e.eyebrow, title: e.title, text: e.text };
    default: return { mark: '✨', glyph: true, eyebrow: 'Образ недели', title: 'Подарок за покупку', text: `+${fmt(e.essence)} Эссенции уже на счёте.` };
  }
}
function lkReveal(events) {
  const list = (events || []).filter(e => _RV_KINDS.has(e?.kind)); if (!list.length) return;
  _rv = { list, i: 0, tokens: v3TokenStyle(_lkItem(_lk.sel)?.tokens) }; _rvRender();
}
function _rvRender() {
  let host = document.getElementById('lk-reveal');
  if (!_rv) { host?.remove(); document.removeEventListener('keydown', _rvKeys, true); lkMainButton(); return; }
  if (!host) { host = document.createElement('div'); host.id = 'lk-reveal'; host.className = 'lk-reveal'; document.body.appendChild(host); document.addEventListener('keydown', _rvKeys, true); }
  const card = _rvCard(_rv.list[_rv.i]), last = _rv.i === _rv.list.length - 1;
  host.setAttribute('style', _rv.tokens || ''); host.setAttribute('role', 'dialog'); host.setAttribute('aria-modal', 'true'); host.setAttribute('aria-labelledby', 'lk-rv-title');
  host.innerHTML = `<div class="lk-rv" key="${_rv.i}"><div class="lk-rv-badge"><span${card.glyph ? ' class="is-glyph"' : ''}>${_profileEsc(card.mark)}</span></div><small>${_profileEsc(card.eyebrow)}</small>
    <h2 id="lk-rv-title">${_profileEsc(card.title)}</h2><p>${_profileEsc(card.text)}</p>
    <button type="button" class="v3-pill" onclick="lkRevealNext()">${last ? 'Отлично' : 'Дальше'}</button></div>`;
  host.querySelector('button')?.focus({ preventScroll: true });
  v3Reward(host.querySelector('.lk-rv-badge'));
  lkMainButton();
}
function lkRevealNext() { if (!_rv) return; if (_rv.i + 1 < _rv.list.length) { _rv.i += 1; _rvRender(); } else { _rv = null; _rvRender(); } }
function _rvKeys(e) { if (e.key === 'Escape') { e.preventDefault(); _rv = null; _rvRender(); } else if (e.key === 'Tab') { e.preventDefault(); document.querySelector('#lk-reveal button')?.focus(); } }

// ── Нативная кнопка Telegram (MainButton): главное действие витрины внизу экрана ────
// Только внутри Telegram (непустой initData). Страничная кнопка при этом прячется, в браузере остаётся она. Цвет берётся из палитры образа.
let _lkMb = { bound: false, act: '' };
function lkMainButton() {
  const mb = tg && tg.initData && tg.MainButton; if (!mb) return;
  const item = _lk.st && _lkItem(_lk.sel), here = !!item && _activePage === 'looks' && _lk.view === 'shop' && !_rv;
  const act = here ? _lkAction(item, _lk.st) : null, show = !!(act && act.a);
  if (!_lkMb.bound) { mb.onClick(() => { if (_lkMb.act && !_lk.busy) lkAct(_lkMb.act); }); _lkMb.bound = true; }
  _lkMb.act = show ? act.a : '';
  try {
    if (!show) { mb.hideProgress?.(); mb.hide(); }
    else {
      const tk = item.tokens || {}, hex = v => (/^#[0-9a-f]{6}$/i.test(v || '') ? v : null);
      const params = { text: act.t, is_active: !_lk.busy, is_visible: true };
      if (hex(tk['--v3-acc'])) params.color = tk['--v3-acc'];
      if (hex(tk['--v3-on-acc'])) params.text_color = tk['--v3-on-acc'];
      mb.setParams(params);
      if (_lk.busy) mb.showProgress?.(false); else mb.hideProgress?.();
    }
  } catch (_) { /* старый клиент без setParams: остаётся страничная кнопка */ }
  document.querySelector('#pg-looks .lk-cta')?.classList.toggle('is-native', show && !!mb.isVisible);
}
{ const pg = el('pg-looks'); if (pg) new MutationObserver(() => lkMainButton()).observe(pg, { attributes: true, attributeFilter: ['class'] }); }   // ушли с витрины: кнопка прячется

// ── Первый вход на витрину: три карточки о том, как всё устроено (один раз на устройстве, повтор по ссылке внизу) ────
function lkTour() {
  const e = 'Как это работает';
  lkReveal([
    { kind: 'tour', mark: '✦', glyph: true, eyebrow: e, title: 'Один образ — весь вид', text: 'Цвета приложения, ник, титул, рамка аватара и фон профиля. Другие игроки видят ваш образ, пока у вас активен VIP; сами вы видите его всегда.' },
    { kind: 'tour', mark: '↑', glyph: true, eyebrow: e, title: 'Образ растёт', text: 'Он покупается на тире D и растёт за Эссенцию до своей редкости. Эссенцию дают задания или набор за Зарники: 1 ✨ = 4 Эссенции, цена всегда видна заранее.' },
    { kind: 'tour', mark: '🪷', glyph: true, eyebrow: e, title: 'Собирайте сеты', text: 'Знак сета рядом с титулом, ранги и награды за коллекцию. Сезонные сеты открываются сами в праздники, а купленное остаётся навсегда.' },
  ]);
}
function lkTourOnce(st) {   // только тем, у кого ещё нет образов; признак «видел» хранится на устройстве
  if (_lsGet('pv_looks_tour') === '1' || st.items.some(i => i.owned)) return;
  _lsSet('pv_looks_tour', '1'); setTimeout(lkTour, 600);
}
