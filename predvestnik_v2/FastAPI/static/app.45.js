// ── Подарки по тирам и полка в профиле ────────────────────────────────────────────────
// Вкладка «Подарки» в магазине (через _shopExtra из app.44.js), полка в своём профиле (#pro-gifts) и витрина на чужой карточке (app.21.js).
// Всё за флагом gifts_v2: вкладка и полка появляются, только если GET /gifts-v2/me ответил; 404 «Подарки пока закрыты» прячет их.
// Первый релиз: дарим только супругу. Цены, лимиты (5 в сутки, 3 одному игроку) и нехватка приходят с сервера (core/gifts_v2.py).
// Записка до 60 символов приходит от другого игрока: везде выводится только через _profileEsc. Номер операции живёт до ответа «успех».
// Стили: app.css (.gift-*), тир читается по рамке: Знак — тонкая линия, Тёплый — золотистая подложка, Редкий — фиолетовое свечение, Легендарный — золото с мерцанием.
const _GIFT_ICONS = { mora: '🪙', diamonds: '💎', zarniki: '✨' };
const _GIFT_OFFLINE = 'Нет связи. Проверь интернет и попробуй ещё раз.';
const _giftPending = new Map();
let _giftsOn = null;   // null — ещё не спрашивали, true — флаг включён, false — подарки закрыты
const _gifts = { me: null, busy: null, errors: {}, loading: false, hist: { box: 'received', tier: 0 }, draft: null };

function _giftCost(cost) { return Object.entries(cost || {}).map(([k, v]) => `${fmtF(v)} ${_GIFT_ICONS[k] || k}`).join(' + '); }
function _giftMiss(gaps) { return `Не хватает: ${Object.entries(gaps || {}).map(([k, v]) => `${fmtF(v)} ${_GIFT_ICONS[k] || k}`).join(', ')}`; }
function _giftItem(id) { return (_gifts.me?.tiers || []).flatMap(t => t.gifts || []).find(g => g.id === id) || null; }
function _giftTier(n) { const t = Number(n); return t >= 1 && t <= 4 ? t : 1; }
function _giftLen(s) { return [...String(s || '')].length; }   // как на сервере: символы, а не половинки эмодзи
function _giftDate(v) { const d = new Date(v); return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' }); }

function _giftsLoad(after) {
  if (_gifts.loading) return;
  _gifts.loading = true;
  api('/gifts-v2/me').then(d => { _gifts.me = d; _giftsOn = true; })
    .catch(e => { if (e === 'Подарки пока закрыты') { _giftsOn = false; _gifts.me = null; } })
    .finally(() => { _gifts.loading = false; giftsShelfRender(); if (typeof _shopRender === 'function' && _activePage === 'shop') _shopRender(); if (after) after(); });
}

// ── Вкладка магазина ────────────────────────────────────────────────────────────────
if (typeof _shopExtra === 'object') {
  _shopExtra.gifts = { name: 'Подарки', on: () => _giftsOn === true && !!_gifts.me, load: () => _giftsLoad(), html: () => _giftsTab() };
}

function _giftLimits(d) {
  const l = d.limits || {}, day = l.daily || {}, one = l.recipient || {};
  const hours = Math.max(1, Math.ceil((Number(l.resets_in_seconds) || 0) / 3600));
  return `Сегодня осталось ${fmt(day.left || 0)} из ${fmt(day.max || 0)}${d.recipient ? ` · этому игроку ${fmt(one.left || 0)} из ${fmt(one.max || 0)}` : ''} · до сброса ${hours} ч`;
}

function _giftCard(g) {
  const gaps = g.missing || {}, short = Object.keys(gaps).length > 0, busy = _gifts.busy === g.id;
  const off = !g.available || short || !!_gifts.busy;
  const err = _gifts.errors[g.id] ? `<div class="shop-err" role="alert"><span>${_profileEsc(_gifts.errors[g.id])}</span><button type="button" onclick="giftRetry('${g.id}')">Повторить</button></div>` : '';
  const price = Object.entries(g.cost || {}).map(([k, v]) => `<span class="${gaps[k] ? 'is-miss' : ''}">${fmtF(v)} ${_GIFT_ICONS[k] || k}</span>`).join('');
  return `<article class="gift-card gt${_giftTier(g.tier)}${g.available ? '' : ' is-off'}" data-gift="${_profileEsc(g.id)}">
    <span class="gift-ico" aria-hidden="true">${_profileEsc(g.icon || '🎁')}</span><b>${_profileEsc(g.name)}</b>
    <div class="shop-price">${price}</div>
    ${short ? `<p class="shop-miss">${_profileEsc(_giftMiss(gaps))}</p>` : ''}${err}
    <button type="button" class="v3-pill shop-act" onclick="giftAsk('${g.id}',this)" ${off ? 'disabled' : ''} ${busy ? 'aria-busy="true"' : ''}>${busy ? 'Минутку…' : 'Подарить'}</button>
  </article>`;
}

function _giftsTab() {
  const d = _gifts.me; if (!d) return '<div class="loader">Загрузка…</div>';
  const who = d.recipient ? `Кому: <b>${_profileEsc(d.recipient.name)}</b>` : _profileEsc(d.unavailable_reason || 'Подарки пока можно дарить только супругу.');
  const tiers = (d.tiers || []).map(t => `<section class="gift-tier gt${_giftTier(t.tier)}" aria-label="${_profileEsc(t.name)}">
      <h3><span class="gift-gem" aria-hidden="true"></span>${_profileEsc(t.name)}</h3>
      <div class="gift-grid">${(t.gifts || []).map(_giftCard).join('')}</div></section>`).join('');
  return `<p class="shop-hint gift-to">${who}</p>
    <p class="shop-hint">${_profileEsc(_giftLimits(d))}. Подарок встанет на полку в профиле получателя.</p>
    ${d.recipient && d.unavailable_reason ? `<p class="shop-note">${_profileEsc(d.unavailable_reason)}</p>` : ''}${tiers}`;
}

// Шаг «записка»: необязательная, до 60 символов. Потом лист подтверждения с ценой и балансом до → после.
function giftAsk(id, trigger) {
  const g = _giftItem(id), d = _gifts.me; if (!g || !d || _gifts.busy || !d.recipient) return;
  if (trigger) trigger.dataset.modalTrigger = 'true';
  _gifts.draft = { id, note: _gifts.draft?.id === id ? _gifts.draft.note : '' };
  const max = Number(d.note_max) || 60;
  OM('Записка к подарку', `<div class="gift-note">
      <div class="cf-item"><span class="gift-ico gt${_giftTier(g.tier)}" aria-hidden="true">${_profileEsc(g.icon)}</span><div><b>${_profileEsc(g.name)}</b><small>Кому: ${_profileEsc(d.recipient.name)}</small></div></div>
      <label for="gift-note-in">Записка, по желанию</label>
      <input id="gift-note-in" class="v3-field" type="text" autocomplete="off" enterkeyhint="next" value="${_profileEsc(_gifts.draft.note)}" oninput="giftNoteInput(this.value)" placeholder="Пара слов от тебя">
      <small id="gift-note-count" aria-live="polite">${_giftLen(_gifts.draft.note)} / ${max}</small></div>`,
  [{ l: 'Дальше', c: 'primary', f: 'giftNoteNext()' }, { l: 'Отмена', c: 'ghost', f: 'CM()' }]);
}
function giftNoteInput(v) {
  if (!_gifts.draft) return;
  _gifts.draft.note = String(v || '');
  const max = Number(_gifts.me?.note_max) || 60, n = _giftLen(_gifts.draft.note.trim()), c = el('gift-note-count');
  if (c) { c.textContent = `${n} / ${max}`; c.classList.toggle('is-miss', n > max); }
}
async function giftNoteNext() {
  const draft = _gifts.draft, g = draft && _giftItem(draft.id), d = _gifts.me; if (!g || !d) return;
  const note = draft.note.trim(), max = Number(d.note_max) || 60;
  if (_giftLen(note) > max) { toast(`Записка — не больше ${max} символов.`, false); return; }
  CM();
  const b = d.balances || {};
  const spent = Object.entries(g.cost || {}).map(([k, v]) => [`Баланс ${_GIFT_ICONS[k] || k}`, `${fmtF(b[k] || 0)} → ${fmtF(Number(b[k] || 0) - Number(v))}`]);
  const ok = await v3Confirm({ title: 'Подарить', visual: g.icon || '🎁', name: g.name, sub: g.tier_name || '',
    rows: [['Кому', d.recipient?.name || ''], ['Отдаёшь', _giftCost(g.cost)], ...(note ? [['Записка', note]] : []), ...spent],
    cta: `Подарить за ${_giftCost(g.cost)}`, note: g.irreversible ? 'Это необратимо.' : '' });
  if (ok) _giftSend(g.id, note);
}
function giftRetry(id) { const draft = _gifts.draft; _giftSend(id, draft?.id === id ? draft.note.trim() : ''); }

function _giftSend(id, note) {
  const g = _giftItem(id), d = _gifts.me; if (!g || !d || _gifts.busy) return;
  const key = `${id}:${note}`;
  const action = _giftPending.get(key) || `gift-${globalThis.crypto?.randomUUID?.() || Date.now().toString(36)}`;
  _giftPending.set(key, action);
  _gifts.busy = id; delete _gifts.errors[id]; _shopRender();
  const body = { gift_id: id, action_id: action, catalog_version: d.catalog_version, catalog_digest: d.catalog_digest, note: note || null };
  api('/gifts-v2/send', { method: 'POST', body: JSON.stringify(body) }).then(res => {
    _giftPending.delete(key); _gifts.busy = null; _gifts.draft = null;
    if (res.balances && _gifts.me) Object.assign(_gifts.me.balances, res.balances);
    if (res.balances && _shop.me) Object.assign(_shop.me.balances, res.balances);
    toast(`${g.icon} ${g.name} уже на полке у ${d.recipient?.name || 'получателя'}`);
    try { v3Reward(document.querySelector(`[data-gift="${id}"] .gift-ico`)); } catch (_) {}
    try { refreshCurrBar(); } catch (_) {}
    _shopRender(); _giftsLoad();
  }).catch(e => {
    _gifts.busy = null;
    if (typeof e === 'string') { if (e.includes('уже использован')) _giftPending.delete(key); toast(e, false); _giftsLoad(); return; }
    _gifts.errors[id] = _GIFT_OFFLINE; _shopRender();   // обрыв связи: «Повторить» отправит тот же номер
  });
}

// ── Полка в своём профиле ───────────────────────────────────────────────────────────
function giftsShelfShell() {
  setTimeout(() => { giftsShelfRender(); _giftsLoad(); }, 0);   // сначала то, что уже знаем, потом свежий ответ
  return `<section class="gift-shelf-wrap" id="pro-gifts" aria-label="Подарки" ${_giftsOn === true ? '' : 'hidden'}></section>`;
}
function giftBadgeHtml(b) {
  if (!b || !b.icon) return '';
  return `<span class="gift-badge" role="img" aria-label="${_profileEsc(`${b.tier_name || 'Легендарный'} подарок: ${b.name || ''}`)}" title="${_profileEsc(b.name || '')}">${_profileEsc(b.icon)}</span>`;
}
function _giftPinned(list) {
  return (list || []).map(p => `<button type="button" class="gift-slot gt${_giftTier(p.tier)} is-on" onclick="giftSlot('${_profileEsc(p.gift_id)}')" aria-label="${_profileEsc(p.name)} на витрине"><span aria-hidden="true">${_profileEsc(p.icon)}</span><i aria-hidden="true">★</i></button>`).join('');
}
function giftsShelfRender() {
  const host = el('pro-gifts'); if (!host) return;
  const s = _gifts.me?.shelf;
  host.hidden = !(_giftsOn === true && s);
  if (host.hidden) return;
  const c = s.counts || {};
  const shelves = (s.tiers || []).map(t => `<div class="gift-shelf gt${_giftTier(t.tier)}"><span class="gift-shelf-name">${_profileEsc(t.name)}</span><div class="gift-slots">${(t.slots || []).map(x => x.count > 0
    ? `<button type="button" class="gift-slot gt${_giftTier(t.tier)} is-on" onclick="giftSlot('${_profileEsc(x.gift_id)}')" aria-label="${_profileEsc(x.name)}: ${fmt(x.count)}"><span aria-hidden="true">${_profileEsc(x.icon)}</span>${x.count > 1 ? `<b>×${fmt(x.count)}</b>` : ''}</button>`
    : `<span class="gift-slot is-empty" role="img" aria-label="${_profileEsc(x.name)}: ещё нет"><span aria-hidden="true">${_profileEsc(x.icon)}</span></span>`).join('')}</div></div>`).join('');
  host.innerHTML = `<div class="v3-sec"><span class="v3-eyebrow">Подарки</span><button type="button" class="v3-link" onclick="openGiftHistory()">История</button></div>
    <div class="gift-counts"><span>Получено <b>${fmt(c.received || 0)}</b></span><span>Отправлено <b>${fmt(c.sent || 0)}</b></span></div>
    ${(s.pinned || []).length ? `<div class="gift-showcase" aria-label="Витрина"><span class="gift-shelf-name">Витрина</span><div class="gift-slots">${_giftPinned(s.pinned)}</div></div>` : ''}
    ${c.received ? '' : '<p class="v3-empty gift-empty">Пока нет подарков</p>'}
    <div class="gift-shelves">${shelves}</div>`;
  const name = document.querySelector('#pro-main .v3-name');   // значок за легендарный подарок рядом с именем
  if (name) { name.querySelector('.gift-badge')?.remove(); name.insertAdjacentHTML('beforeend', giftBadgeHtml(s.top_badge)); }
}

function _giftRow(h, box) {
  const who = box === 'sent' ? h.to : h.from;
  const pin = box === 'received' ? `<button type="button" class="gift-pin" aria-pressed="${!!h.pinned}" aria-label="${h.pinned ? 'Снять с витрины' : 'На витрину'}" onclick="giftPin('${_profileEsc(h.id)}',${!h.pinned})">★</button>` : '';
  return `<li class="gift-row gt${_giftTier(h.tier)}"><span class="gift-ico" aria-hidden="true">${_profileEsc(h.icon)}</span>
    <div><b>${_profileEsc(h.name)} <small>${_profileEsc(h.tier_name)}</small></b>
    <small>${box === 'sent' ? 'Кому' : 'От'}: ${_profileEsc(who?.name || '—')} · ${_profileEsc(_giftDate(h.created_at))}</small>
    ${h.note ? `<q>${_profileEsc(h.note)}</q>` : ''}</div>${pin}</li>`;
}
// Тап по подарку на полке: кто, когда, записка, тир и звезда «на витрину» (не больше трёх).
function giftSlot(giftId) {
  OM('Подарок', '<div class="loader">Загрузка…</div>', [{ l: 'Закрыть', c: 'ghost', f: 'CM()' }]);
  _gifts.slot = giftId;
  api(`/gifts-v2/history?box=received&gift_id=${encodeURIComponent(giftId)}`).then(r => {
    const rows = r.items || [];
    el('mb').innerHTML = rows.length ? `<p class="v3-sub">Звезда ставит подарок на витрину: её видят другие игроки (до ${fmt(_gifts.me?.pin_max || 3)}).</p><ul class="gift-list">${rows.map(h => _giftRow(h, 'received')).join('')}</ul>` : '<p class="v3-empty">Пока нет подарков</p>';
  }).catch(e => { el('mb').innerHTML = `<p class="v3-empty">${_profileEsc(typeof e === 'string' ? e : _GIFT_OFFLINE)}</p>`; });
}
function giftPin(sendId, pinned) {
  api('/gifts-v2/pin', { method: 'POST', body: JSON.stringify({ send_id: sendId, pinned }) }).then(r => {
    if (_gifts.me && r.shelf) _gifts.me.shelf = r.shelf;
    giftsShelfRender(); _haptic('select');
    if (el('modal')?.open) { if (_gifts.histOpen) _giftHistLoad(); else if (_gifts.slot) giftSlot(_gifts.slot); }
  }).catch(e => toast(typeof e === 'string' ? e : _GIFT_OFFLINE, false));
}

// История: получено / отправлено, фильтр по тиру.
function openGiftHistory() {
  _gifts.histOpen = true; _gifts.slot = null;
  OM('История подарков', '<div id="gift-hist"><div class="loader">Загрузка…</div></div>', [{ l: 'Закрыть', c: 'ghost', f: 'CM();_gifts.histOpen=false' }]);
  _giftHistLoad();
}
function giftHist(box, tier) { if (box) _gifts.hist.box = box; if (tier != null) _gifts.hist.tier = tier; _giftHistLoad(); }
function _giftHistLoad() {
  const h = _gifts.hist, host = () => el('gift-hist');
  const names = (_gifts.me?.tiers || []).map(t => [t.tier, t.name]);
  const head = `<div class="shop-switch" role="group" aria-label="Список">${[['received', 'Получено'], ['sent', 'Отправлено']].map(([k, l]) => `<button type="button" aria-pressed="${h.box === k}" onclick="giftHist('${k}')">${l}</button>`).join('')}</div>
    <div class="gift-filter" role="group" aria-label="Тир">${[[0, 'Все'], ...names].map(([t, l]) => `<button type="button" class="v3-chip" aria-pressed="${h.tier === t}" onclick="giftHist(null,${t})">${_profileEsc(l)}</button>`).join('')}</div>`;
  if (host()) host().innerHTML = `${head}<div class="loader">Загрузка…</div>`;
  api(`/gifts-v2/history?box=${h.box}${h.tier ? `&tier=${h.tier}` : ''}`).then(r => {
    const rows = r.items || [];
    if (host()) host().innerHTML = `${head}${rows.length ? `<ul class="gift-list">${rows.map(x => _giftRow(x, h.box)).join('')}</ul>` : '<p class="v3-empty">Пока нет подарков</p>'}`;
  }).catch(e => { if (host()) host().innerHTML = `${head}<p class="v3-empty">${_profileEsc(typeof e === 'string' ? e : _GIFT_OFFLINE)}</p>`; });
}

// ── Чужая карточка: только витрина (до трёх) и общее число ────────────────────────────
function ppGiftsHtml(d) {
  const g = d && d.gifts; if (!g) return '';
  const pinned = (g.pinned || []).slice(0, 3).map(p => `<span class="gift-slot gt${_giftTier(p.tier)} is-on" role="img" aria-label="${_profileEsc(`${p.name}, ${p.tier_name}`)}"><span aria-hidden="true">${_profileEsc(p.icon)}</span></span>`).join('');
  const send = !d.is_self && g.can_send ? '<button type="button" class="v3-pill v3-pill--ghost" onclick="openShop(\'gifts\')">Подарить</button>' : '';
  return `<section><div class="v3-sec"><span class="v3-eyebrow">Подарки</span><span class="v3-sub">Всего: ${fmt(g.total || 0)}</span></div>
    ${pinned ? `<div class="gift-slots pp-gifts">${pinned}</div>` : `<p class="v3-empty">Пока нет подарков</p>`}${send}</section>`;
}
