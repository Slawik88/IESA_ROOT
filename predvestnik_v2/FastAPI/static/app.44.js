// ── Магазин ──────────────────────────────────────────────────────────────────────────
// Страница «Магазин» (#pg-shop): ключи по звёздам, Шлифовка (Эссенция), обменник Зарников и плитки на готовые экраны (пропуск, VIP, образы).
// Всё за флагом shop_v1: вход (строка в профиле и кнопка в окне валют) показывается, только если GET /shop-v1/me ответил; 404 «Магазин пока закрыт» прячет его.
// Цены, лимиты, шансы и нехватка приходят с сервера (core/shop_v1.py), клиент их не считает. Перед каждым списанием лист подтверждения: отдаёшь, получаешь, баланс до и после.
// Номер операции живёт до ответа «успех»: «Повторить» после обрыва связи шлёт тот же номер, второго списания не будет. Подарки появятся в PR-C. Стили: app.css (.shop-*).
const _SHOP_ICONS = { mora: '🪙', diamonds: '💎', zarniki: '✨', essence: '🔮' };
const _SHOP_VERB = { buy: 'Купить', craft: 'Скрафтить', exchange: 'Обменять' };
const _SHOP_TABS = { keys: 'Ключи', essence: 'Эссенция', exchange: 'Обменник' };
const _SHOP_SWITCH = { key_t4: { key_t4_craft: 'Крафт', key_t4_zar: 'За ✨' } };   // Серебро: одна плитка, способ переключается
const _SHOP_LINKS = { pass: () => openSeasonPass(), vip: () => openVipModal(), skins: () => openLooksModal() };
const _SHOP_LINK_FN = { pass: 'openSeasonPass', vip: 'openVipModal', skins: 'openLooksModal' };
const _SHOP_OFFLINE = 'Нет связи. Проверь интернет и попробуй ещё раз.';
const _shopPending = new Map();
let _shopOn = null;   // null — ещё не спрашивали, true — флаг включён, false — магазин закрыт
const _shop = { me: null, tab: 'keys', pick: { key_t4: 'key_t4_craft' }, amounts: {}, busy: null, errors: {}, failed: null, loading: false };

function _shopNum(n) { return fmtF(n); }
function _shopCost(cost) { return Object.entries(cost || {}).map(([k, v]) => `${_shopNum(v)} ${_SHOP_ICONS[k] || k}`).join(' + '); }
function _shopMissText(gaps) { return `Не хватает: ${Object.entries(gaps || {}).map(([k, v]) => `${_shopNum(v)} ${_SHOP_ICONS[k] || k}`).join(', ')}`; }
function _shopItems() { return (_shop.me?.sections || []).flatMap(s => s.items || []); }
function _shopItem(id) { return _shopItems().find(i => i.id === id) || null; }
function _shopHours(sec) { return Math.max(1, Math.ceil((Number(sec) || 0) / 3600)); }

// Вход в магазин: строка в профиле и кнопка в окне валют. Узнаём флаг одним GET /shop-v1/me на сессию (страница перечитывает сама).
function shopProbe() {
  if (_shopOn !== null || _shop.loading) return;
  _shop.loading = true;
  api('/shop-v1/me').then(d => { _shop.me = d; _shopOn = true; }).catch(e => { if (typeof e === 'string') _shopOn = false; })
    .finally(() => { _shop.loading = false; _shopSyncEntries(); });
}
function _shopSyncEntries() {
  document.querySelectorAll('[data-shop-entry]').forEach(node => { node.hidden = _shopOn !== true; });
}
function shopEntryRow() {
  if (_shopOn === null) setTimeout(shopProbe, 0);
  return _v3Row('shop', 'Магазин', 'openShop()', 'Ключи, Шлифовка, обменник').replace('<button ', `<button data-shop-entry ${_shopOn === true ? '' : 'hidden '}`);
}

window.openShop = function (tab) {
  if (tab && _SHOP_TABS[tab]) _shop.tab = tab;
  try { CM(); } catch (_) {}
  switchPage('shop');
  _shopLoad();
};
function shopBack() { if (_navStack.length) navBack(); else switchPage('profile'); }

function _shopLoad() {
  const root = el('pg-shop'); if (!root) return;
  if (!_shop.me) root.innerHTML = '<div class="loader" style="margin-top:44px">Загрузка магазина…</div>';
  api('/shop-v1/me').then(d => {
    _shop.me = d; _shop.failed = null; _shopOn = true; _shopSyncEntries(); _shopRender();
  }).catch(e => {
    if (e === 'Магазин пока закрыт') { _shopOn = false; _shopSyncEntries(); _shop.me = null; }
    _shop.failed = typeof e === 'string' ? e : _SHOP_OFFLINE;
    if (!_shop.me) root.innerHTML = `<div class="v3-err quest-load-error" role="alert"><b>${_shopOn === false ? 'Магазин пока закрыт' : 'Магазин не загрузился'}</b><span>${esc(_shop.failed)}</span>${_shopOn === false ? '' : '<button type="button" onclick="openShop()">Повторить</button>'}</div>`;
    else { toast(_shop.failed, false); _shopRender(); }
  });
}

function _shopBalances(b) {
  const keys = b.keys || {}, tiers = Object.keys(keys).filter(t => Number(keys[t]) > 0 || t === '1');
  return `<section class="shop-bal" aria-label="Баланс">${['mora', 'diamonds', 'zarniki', 'essence'].map(k => `<span>${_SHOP_ICONS[k]} <b>${_shopNum(b[k] || 0)}</b></span>`).join('')}<span class="shop-keys">🗝 ${tiers.map(t => `${t}★ <b>${fmt(keys[t] || 0)}</b>`).join(' · ')}</span></section>`;
}

function _shopLimit(item) {
  const l = item.limit || {}, left = Number(l.left) || 0, max = Number(l.max) || 0;
  if (l.period === 'week') return left > 0 ? `Осталось ${left} из ${max} на этой неделе` : 'Лимит на этой неделе исчерпан';
  const reset = `до сброса ${_shopHours(l.resets_in_seconds)} ч`;
  return left > 0 ? `Осталось ${left} из ${max} · ${reset}` : `Лимит на сегодня исчерпан · ${reset}`;
}

function _shopAmount(item) {
  const v = Number(_shop.amounts[item.id] ?? 1);
  return Number.isSafeInteger(v) && v >= 1 ? v : 0;
}
function _shopExchangeGets(item, amount) {
  const got = amount * Number(item.rate || 0);
  return item.target === 'diamonds' || item.id === 'exchange_dia' ? `${_shopNum(got)} 💎` : `${_shopNum(got)} 🪙`;
}
// Сколько не хватает именно на выбранную сумму обмена: сервер присылает нехватку на 1✨.
function _shopGaps(item) {
  if (item.mode !== 'exchange') return item.missing || {};
  const have = Number(_shop.me?.balances?.zarniki) || 0, amount = _shopAmount(item);
  return amount > have ? { zarniki: Math.ceil(amount - have) } : {};
}

function _shopCard(item, group) {
  const gaps = _shopGaps(item), short = Object.keys(gaps).length > 0, busy = _shop.busy === item.id;
  const amount = item.mode === 'exchange' ? _shopAmount(item) : 1;
  const tooMuch = item.mode === 'exchange' && (amount < 1 || amount > Number(item.limit?.left || 0));
  const off = !item.available || short || tooMuch || !!_shop.busy;
  const price = Object.entries(item.cost || {}).map(([k, v]) => `<span class="${gaps[k] ? 'is-miss' : ''}">${_shopNum(item.mode === 'exchange' ? v * Math.max(1, amount) : v)} ${_SHOP_ICONS[k] || k}</span>`).join('<span aria-hidden="true">+</span>');
  const sw = group ? `<div class="shop-switch" role="group" aria-label="Способ">${Object.entries(_SHOP_SWITCH[group]).map(([id, label]) => `<button type="button" aria-pressed="${id === item.id}" onclick="shopPick('${group}','${id}')">${label}</button>`).join('')}</div>` : '';
  const amt = item.mode === 'exchange' ? `<label class="shop-amount"><input class="v3-field" type="number" inputmode="numeric" min="1" max="${Number(item.limit?.left || 0)}" step="1" value="${amount || ''}" aria-label="Сколько Зарников обменять" oninput="shopAmount('${item.id}',this.value)"><small>→ ${_shopExchangeGets(item, amount)}</small></label>` : '';
  const err = _shop.errors[item.id] ? `<div class="shop-err" role="alert"><span>${esc(_shop.errors[item.id])}</span><button type="button" onclick="shopRetry('${item.id}')">Повторить</button></div>` : '';
  return `<article class="shop-card${item.available ? '' : ' is-off'}" data-item="${esc(item.id)}">
    <div class="shop-card-top"><span class="shop-ico${item.tier ? ` t${item.tier}` : ''}" aria-hidden="true">${esc(item.icon || '🛒')}</span><div><b>${esc(item.name)}</b><small>${esc(item.gives?.text || '')}</small></div>${item.tier ? `<span class="shop-tier">${item.tier}★</span>` : ''}</div>
    ${sw}${amt}<div class="shop-price">${price}</div>
    <p class="shop-limit">${esc(_shopLimit(item))}</p>
    ${short ? `<p class="shop-miss">${esc(_shopMissText(gaps))}</p>` : ''}${item.unavailable_reason ? `<p class="shop-note">${esc(item.unavailable_reason)}</p>` : ''}${err}
    <button type="button" class="v3-pill shop-act" onclick="shopAsk('${item.id}',this)" ${off ? 'disabled' : ''} ${busy ? 'aria-busy="true"' : ''}>${busy ? 'Минутку…' : _SHOP_VERB[item.mode] || 'Купить'}</button>
  </article>`;
}

function _shopSection(section) {
  const cards = [], seen = new Set();
  for (const item of section.items || []) {
    const group = _SHOP_SWITCH[item.group] ? item.group : null;
    if (group) {
      if (seen.has(group)) continue; seen.add(group);
      const chosen = _shopItem(_shop.pick[group]) || item;
      cards.push(_shopCard(chosen, group));
    } else cards.push(_shopCard(item, null));
  }
  let hint = '';
  if (section.id === 'keys') hint = (_shop.me.key_odds || []).map(o => `Ключ ${o.stars}★: ${o.stars === 6 ? 'около' : 'примерно'} ${String(o.percent).replace('.', ',')}% выпадет ${o.stars}★${o.stars === 6 ? '' : ', остальное выше'}.`).join(' ');
  if (section.id === 'essence') hint = 'Эссенция растит образы по тирам.';
  if (section.id === 'exchange') { const x = _shop.me.exchange || {}; hint = `Лимит ${fmt(x.daily_cap || 0)}✨ в сутки, осталось ${fmt(x.left || 0)}. Обмен необратим.`; }
  return `${hint ? `<p class="shop-hint">${esc(hint)}</p>` : ''}<div class="shop-list">${cards.join('')}</div>`;
}

function _shopRender() {
  const root = el('pg-shop'), d = _shop.me; if (!root || !d) return;
  const sections = d.sections || [];
  if (!sections.some(s => s.id === _shop.tab)) _shop.tab = sections[0]?.id || 'keys';
  const section = sections.find(s => s.id === _shop.tab) || { items: [] };
  const tabs = sections.map(s => `<button type="button" role="tab" aria-selected="${s.id === _shop.tab}" onclick="shopTab('${s.id}')">${esc(s.name || _SHOP_TABS[s.id] || s.id)}</button>`).join('');
  const links = (d.links || []).filter(l => typeof window[_SHOP_LINK_FN[l.target]] === 'function')   // нет экрана — нет плитки
    .map(l => `<button type="button" onclick="shopLink('${l.target}')"><span aria-hidden="true">${esc(l.icon)}</span>${esc(l.name)}</button>`).join('');
  const focused = document.activeElement?.closest?.('.shop-amount') ? document.activeElement.closest('[data-item]')?.dataset.item : null;
  root.innerHTML = `<header class="looks-head shop-head"><button class="looks-back" onclick="shopBack()" aria-label="Назад">‹</button><div><h1>🛒 Магазин</h1><small>Цены и лимиты — с сервера, сутки и неделя по UTC</small></div></header>
    ${_shopBalances(d.balances || {})}
    <div class="shop-tabs" role="tablist" aria-label="Разделы магазина">${tabs}</div>
    <section class="shop-sec" role="tabpanel">${_shopSection(section)}</section>
    ${links ? `<nav class="shop-links" aria-label="Другие экраны">${links}</nav>` : ''}`;
  if (focused) { const input = root.querySelector(`[data-item="${focused}"] .shop-amount input`); if (input) { input.focus({ preventScroll: true }); const v = input.value; input.value = ''; input.value = v; } }
}

function shopTab(id) { if (_shop.busy) return; _shop.tab = id; _haptic('select'); _shopRender(); }
function shopPick(group, id) { if (_shop.busy) return; _shop.pick[group] = id; _haptic('select'); _shopRender(); }
function shopAmount(id, raw) { _shop.amounts[id] = /^\d+$/.test(String(raw).trim()) ? Number(raw) : 0; _shopRender(); }
function shopLink(target) { const run = _SHOP_LINKS[target]; if (run) run(); }

// Лист подтверждения: что отдаёшь, что получаешь и баланс до → после по каждой задетой валюте.
async function shopAsk(id, trigger) {
  const item = _shopItem(id), d = _shop.me; if (!item || !d || _shop.busy) return;
  const b = d.balances || {}, amount = item.mode === 'exchange' ? _shopAmount(item) : 1;
  const cost = Object.fromEntries(Object.entries(item.cost || {}).map(([k, v]) => [k, v * amount]));
  let gets, after = [];
  if (item.section === 'keys') {
    const keys = b.keys || {};
    gets = `1 🗝 ключ ${item.tier}★`;
    after.push([`Ключи ${item.tier}★`, `${fmt(keys[String(item.tier)] || 0)} → ${fmt(Number(keys[String(item.tier)] || 0) + 1)}`]);
  } else if (item.mode === 'exchange') {
    gets = _shopExchangeGets(item, amount);
    const k = item.id === 'exchange_dia' ? 'diamonds' : 'mora';
    after.push([`Баланс ${_SHOP_ICONS[k]}`, `${_shopNum(b[k] || 0)} → ${_shopNum(Number(b[k] || 0) + amount * Number(item.rate || 0))}`]);
  } else {
    gets = `${fmt(item.gives?.essence || 0)} 🔮 Эссенции`;
    after.push(['Баланс 🔮', `${_shopNum(b.essence || 0)} → ${_shopNum(Number(b.essence || 0) + Number(item.gives?.essence || 0))}`]);
  }
  const spent = Object.entries(cost).map(([k, v]) => [`Баланс ${_SHOP_ICONS[k] || k}`, `${_shopNum(b[k] || 0)} → ${_shopNum(Number(b[k] || 0) - v)}`]);
  const hard = 'zarniki' in cost || 'diamonds' in cost;
  const note = item.section === 'keys' ? (hard ? 'Это необратимо. Покупка необратима: ключ не возвращается.' : 'Покупка необратима: ключ не возвращается.') : hard ? 'Это необратимо.' : '';
  if (trigger) trigger.dataset.modalTrigger = 'true';
  const ok = await v3Confirm({ title: _SHOP_VERB[item.mode] || 'Купить', visual: item.icon || '🛒', name: item.name, sub: item.gives?.text || '',
    rows: [['Отдаёшь', _shopCost(cost)], ['Получаешь', gets, true], ...spent, ...after], cta: `${_SHOP_VERB[item.mode] || 'Купить'} за ${_shopCost(cost)}`, note });
  if (ok) _shopBuy(id, amount);
}
function shopRetry(id) { const item = _shopItem(id); if (item) _shopBuy(id, item.mode === 'exchange' ? _shopAmount(item) : 1); }

function _shopDone(item, d) {
  const r = d.receipt || {};
  if (item.section === 'keys') return `Ключ ${item.tier}★ получен`;
  if (item.mode === 'exchange') return `Обменено ${fmt(r.zarniki_spent || 0)}✨ → ${_shopNum(r.amount_received || 0)} ${item.id === 'exchange_dia' ? '💎' : '🪙'}`;
  return `Шлифовка готова · +${fmt(r.gives?.essence || item.gives?.essence || 0)} 🔮`;
}
function _shopBuy(id, amount) {
  const item = _shopItem(id), d = _shop.me; if (!item || !d || _shop.busy) return;
  const key = item.mode === 'exchange' ? `${id}:${amount}` : id;
  const action = _shopPending.get(key) || `shop-${globalThis.crypto?.randomUUID?.() || Date.now().toString(36)}`;
  _shopPending.set(key, action);
  _shop.busy = id; delete _shop.errors[id]; _shopRender();
  const body = { item_id: id, action_id: action, catalog_version: d.catalog_version, catalog_digest: d.catalog_digest };
  if (item.mode === 'exchange') body.amount = amount;
  api('/shop-v1/buy', { method: 'POST', body: JSON.stringify(body) }).then(res => {
    _shopPending.delete(key); _shop.busy = null;
    if (res.balances && _shop.me) Object.assign(_shop.me.balances, res.balances);   // баланс меняется на месте сразу, полный ответ догоняет
    toast(_shopDone(item, res)); _haptic('success');
    try { refreshCurrBar(); } catch (_) {}
    _shopRender(); _shopLoad();
  }).catch(e => {
    _shop.busy = null;
    if (typeof e === 'string') { if (e.includes('уже использован')) _shopPending.delete(key); toast(e, false); _shopLoad(); return; }   // ответ сервера: обновляем цены и лимиты, номер операции остаётся до успеха
    _shop.errors[id] = _SHOP_OFFLINE; _shopRender();                       // обрыв связи: «Повторить» отправит тот же номер
  });
}
