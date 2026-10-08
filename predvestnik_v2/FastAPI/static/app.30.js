// ── Зарники и VIP: одна страница, которая продаёт сама себя ────────────────────────────
// Вкладка «Зарники»: что можно купить сейчас, пакеты Telegram Stars (под выбранной целью заранее выбран тот, что хватит) и список образов, на которые
// хватит после пополнения. Вкладка «VIP»: как вас видят другие с VIP и без него, что он даёт, сроки за Зарники, значок у ника.
// Деньги считает сервер (/payments/zarniki/*, /vip/*, /skins-v3/me); здесь показ и повторяемые запросы. Стили: store-v3.css.
let _sv = { tab: 'zarniki', pk: null, vip: null, st: null, sel: null, goal: null, busy: false, loading: false, paid: 0, failed: '', seq: 0 };
const _svBal = () => Number(_profileData?.zarniki ?? _sv.st?.zarniki ?? 0);
const _svItem = id => _sv.st?.items.find(i => i.id === id) || null;

function openStoreV3(tab, goal) {
  _sv = { ..._sv, tab: tab === 'vip' ? 'vip' : 'zarniki', goal: goal || null, paid: 0, failed: '', loading: true, sel: null, seq: _sv.seq + 1 };
  switchPage('store'); _svRender();
  const mine = _sv.seq;
  Promise.all([api('/payments/zarniki/packages'), api('/vip/status').catch(() => null), api('/skins-v3/me').catch(() => null)]).then(([pk, vip, st]) => {
    if (mine !== _sv.seq) return;
    Object.assign(_sv, { pk, vip, st, loading: false }); _svPick(_svRecommended(), true);
  }).catch(e => { if (mine !== _sv.seq) return; Object.assign(_sv, { loading: false, failed: String(e || 'Не удалось загрузить') }); _svRender(); });
}
window.openZarnikiTopup = goal => openStoreV3('zarniki', typeof goal === 'string' ? goal : null);
window.openVipModal = () => openStoreV3('vip');

// Пакет, которого хватит на цель (или самый ходовой), по возрасту «не хватает»
function _svRecommended() {
  const packs = _sv.pk?.packages || [], goal = _sv.goal && _svItem(_sv.goal);
  if (goal && !goal.owned) {
    const need = goal.price_zarniki - _svBal(), hit = packs.find(p => p.total >= need);
    return Number((hit || packs[packs.length - 1] || {}).stars) || null;
  }
  const pop = packs.find(p => p.popular) || packs[0]; return pop ? Number(pop.stars) : null;
}
function _svPick(stars, quiet) { _sv.sel = stars; if (!quiet) _haptic('select'); _svRender(); }
function svTab(tab) { if (_sv.tab !== tab) { _sv.tab = tab; _haptic('select'); _svRender(); window.scrollTo(0, 0); } }
function svSelect(stars) { _svPick(Number(stars)); }

function _svTop() {
  return `<div class="lk-top"><button type="button" class="v3-link pp-back" onclick="navBack()" aria-label="Назад">‹ Назад</button>
    <div class="lk-wallet" role="group" aria-label="Баланс"><button type="button" onclick="svTab('zarniki')" aria-label="Зарники ${fmt(_svBal())}">✨ <b>${fmt(_svBal())}</b></button></div></div>
    <div class="lk-seg" role="tablist" aria-label="Раздел">${[['zarniki', 'Зарники'], ['vip', 'VIP']].map(([id, t]) => `<button type="button" role="tab" aria-selected="${_sv.tab === id}" class="${_sv.tab === id ? 'is-on' : ''}" onclick="svTab('${id}')">${t}</button>`).join('')}</div>`;
}

// ── Зарники ──────────────────────────────────────────────────────────────────────
function _svReach(total) {
  const money = _svBal() + total;
  return (_sv.st?.items || []).filter(i => !i.owned && i.buyable !== false && i.price_zarniki <= money).sort((a, b) => b.price_zarniki - a.price_zarniki).slice(0, 3);
}
function _svPacks() {
  const packs = _sv.pk?.packages || [];
  return `<div class="sv-packs" role="radiogroup" aria-label="Пакет Зарников">${packs.map(p => {
    const on = Number(p.stars) === _sv.sel, tag = p.popular ? 'Популярный' : '', bonus = p.bonus ? `${fmt(p.zarniki)} + ${fmt(p.bonus)} в подарок` : `${fmt(p.zarniki)} ✨`;
    return `<button type="button" role="radio" aria-checked="${on}" class="sv-pack${on ? ' is-on' : ''}" onclick="svSelect(${Number(p.stars)})"><span><b>${fmt(p.total)} ✨</b><small>${bonus}</small></span><span class="sv-pack-end"><b>${fmt(p.stars)} ⭐</b>${tag ? `<small>${tag}</small>` : ''}</span></button>`;
  }).join('')}</div>`;
}
function _svReachHtml(pack) {
  const goal = _sv.goal && _svItem(_sv.goal), list = pack ? _svReach(Number(pack.total)) : [];
  const head = goal && !goal.owned ? `<p class="sv-goal">Вы выбрали «${_profileEsc(goal.name)}»: ${fmt(goal.price_zarniki)} ✨${goal.price_zarniki > _svBal() ? `, не хватает ${fmt(goal.price_zarniki - _svBal())} ✨` : ''}</p>` : '';
  if (!list.length) return head;
  return `${head}<div class="v3-sec"><span class="v3-eyebrow">С этим пакетом хватит на</span></div><ul class="sv-reach">${list.map(i => `<li>${_lkMini(i)}<span><b>${_profileEsc(i.name)}</b><small>${i.ceiling} · ${fmt(i.price_zarniki)} ✨${i.season ? ' · сезон' : ''}</small></span></li>`).join('')}</ul>`;
}
function _svZarniki() {
  const pk = _sv.pk, pack = (pk?.packages || []).find(p => Number(p.stars) === _sv.sel);
  if (!pk) return '';
  const off = pk.purchase_enabled === false;
  return `<h1 class="v3-title">Зарники</h1><p class="v3-sub">Валюта для образов, сетов и VIP. Цена видна заранее, случайных наград нет.</p>
    ${_sv.paid ? `<div class="sv-ok" role="status"><b>+${fmt(_sv.paid)} ✨</b> зачислено. ${_sv.goal && _svItem(_sv.goal) && !_svItem(_sv.goal).owned ? `<button type="button" class="v3-link" onclick="navBack()">Вернуться к образу ›</button>` : ''}</div>` : ''}
    ${_svReachHtml(pack)}
    <div class="v3-sec"><span class="v3-eyebrow">Пакеты</span></div>${_svPacks()}
    ${off ? `<p class="lk-fine">${pk.purchase_disabled_reason === 'preprod' ? 'На тестовом стенде платежи отключены. В продакшене пополнение работает.' : 'Пополнение сейчас недоступно.'}</p>`
      : `<button type="button" class="v3-pill sv-buy${_sv.busy ? ' is-busy' : ''}" ${_sv.busy || !pack ? 'disabled' : ''} onclick="svPay()">${_sv.busy ? 'Открываем оплату…' : pack ? `Купить ${fmt(pack.total)} ✨ за ${fmt(pack.stars)} ⭐` : 'Выберите пакет'}</button>
      <p class="lk-fine">Оплата откроется внутри Telegram, баланс обновится сам.</p>`}`;
}
async function svPay() {
  const stars = _sv.sel, pack = (_sv.pk?.packages || []).find(p => Number(p.stars) === stars);
  if (_sv.busy || !pack) return;
  _sv.busy = true; _svRender();
  try {
    const invoice = await api('/payments/zarniki/invoice', { method: 'POST', body: JSON.stringify({ stars }) });
    if (!invoice?.link) throw new Error('Счёт не создан.');
    if (typeof tg?.openInvoice === 'function') {
      tg.openInvoice(invoice.link, status => {
        if (status !== 'paid') return;
        _haptic('success'); _sv.paid = Number(pack.total); _v3RefreshBalance();
        api('/skins-v3/me').then(st => { _sv.st = st; _svRender(); }).catch(() => _svRender());
      });
    } else location.assign(invoice.link);
  } catch (e) { toast(e, false); }
  finally { _sv.busy = false; _svRender(); }
}

// ── VIP ──────────────────────────────────────────────────────────────────────────
function _svSee() {
  const worn = _sv.st?.items.find(i => i.equipped) || _svItem(_sv.st?.featured?.skin_id), name = String(_profileData?.display_name || 'Игрок');
  const row = (label, inner) => `<li><i>${label}</i><span class="v3-who-wrap">${inner}</span></li>`;
  const look = worn ? { ...worn, tier: worn.ceiling } : null;
  return `<div class="v3-sec"><span class="v3-eyebrow">Как вас видят другие</span></div><ul class="sv-see">
    ${row('Без VIP', `<span class="ap-plain">${_profileEsc(name)}</span>`)}${row('С VIP', look ? apWho({ look, name, is_vip: true }) : `<span class="ap-plain">${_profileEsc(name)} ✦</span>`)}</ul>
    <p class="lk-fine">${worn ? `Так выглядит образ «${_profileEsc(worn.name)}» в топе и профиле.` : 'Образ, который вы наденете, увидят все.'} Сами вы видите свой образ всегда.</p>`;
}
function _svVipPackages() {
  const v = _sv.vip, bal = _svBal();
  return `<div class="sv-vip-list">${(v?.tiers || []).map(p => {
    const days = Number(p.duration_days), price = Number(p.price_zarniki), enough = bal >= price, miss = price - bal;
    return `<button type="button" class="sv-vip${enough ? '' : ' is-short'}" ${_sv.busy ? 'disabled' : ''} onclick="${enough ? `svVipBuy(${days})` : `_svNeed(${price})`}"><span><b>${fmt(days)} ${days === 365 ? 'дней, год' : 'дней'}</b><small>${enough ? 'Срок добавится к текущему' : `Не хватает ${fmt(miss)} ✨, нажмите, чтобы пополнить`}</small></span><span class="sv-vip-end"><b>${fmt(price)} ✨</b></span></button>`;
  }).join('')}</div>`;
}
function _svNeed(price) {   // не хватает на VIP: на вкладку пополнения, пакет подбирается под цену
  const need = price - _svBal(), packs = _sv.pk?.packages || [], hit = packs.find(p => p.total >= need);
  _sv.tab = 'zarniki'; _sv.goal = null; _sv.sel = Number((hit || packs[packs.length - 1] || {}).stars) || null; _haptic('select'); _svRender(); window.scrollTo(0, 0);
}
async function svVipBuy(days) {
  if (_sv.busy) return;
  _sv.busy = true; _svRender();
  try {
    const key = (_sv.vipKeys ||= {})[days] ||= (globalThis.crypto?.randomUUID?.() || `vip-${Date.now()}`);
    const r = await api('/vip/purchase', { method: 'POST', body: JSON.stringify({ package_days: days, action_id: key }) });
    _sv.vipKeys = {}; toast(`VIP продлён на ${fmt(r.package_days)} дней`); _haptic('success');
    await Promise.all([loadProfile(), api('/vip/status').then(v => { _sv.vip = v; })]);
  } catch (e) { toast(e?.message || e || 'Покупка не выполнена', false); }
  finally { _sv.busy = false; _svRender(); }
}
function _svBadge() {
  const v = _sv.vip; if (!v?.active) return '';
  const pos = v.preferences?.badge_position || 'left', opts = (v.badges || []).map(b => `<option value="${_profileEsc(b.id)}"${v.preferences?.badge_id === b.id ? ' selected' : ''}>${_profileEsc(b.symbol)} ${_profileEsc(b.id)}</option>`).join('');
  return `<div class="v3-sec"><span class="v3-eyebrow">Значок у ника</span></div><div class="sv-badge"><select id="vip-badge" class="num-input" aria-label="Значок">${opts}</select>
    <select id="vip-badge-pos" class="num-input" aria-label="Положение">${[['left', 'Слева'], ['right', 'Справа'], ['both', 'С двух сторон'], ['hidden', 'Скрыть']].map(([k, t]) => `<option value="${k}"${pos === k ? ' selected' : ''}>${t}</option>`).join('')}</select>
    <label class="st-row"><span><b>Напоминать о конце срока</b></span><input id="vip-reminders" type="checkbox" class="st-switch" role="switch"${v.preferences?.reminder_enabled !== false ? ' checked' : ''}></label>
    <button type="button" class="v3-pill v3-pill--ghost" onclick="svSaveBadge(this)">Сохранить</button></div>`;
}
function _svVip() {
  const v = _sv.vip; if (!v) return `<h1 class="v3-title">VIP</h1><p class="v3-sub">Сейчас недоступно.</p>`;
  const state = v.active ? `<div class="sv-state is-on" role="status"><b>VIP активен</b><span>ещё ${fmt(v.days_left || 0)} дн. · до ${_profileDate(v.expires_at)}</span></div>` : '<div class="sv-state"><b>VIP не активен</b><span>Пока другие видят вас без образа</span></div>';
  return `<h1 class="v3-title">VIP</h1><p class="v3-sub">Ваш образ видят все, а у вас больше возможностей. В играх силы он не даёт.</p>${state}
    ${_svSee()}
    <div class="v3-sec"><span class="v3-eyebrow">Что даёт</span></div><ul class="sv-perks">${(v.perks || []).map(t => `<li>${_profileEsc(t)}</li>`).join('')}</ul>
    <div class="v3-sec"><span class="v3-eyebrow">${v.active ? 'Продлить' : 'Оформить'}</span></div>${_svVipPackages()}
    <p class="lk-fine">Платите Зарниками, цена одна на день: 20 ✨. Срок складывается, ничего не сгорает.</p>${_svBadge()}`;
}

function _svRender() {
  const root = el('pg-store'); if (!root) return;
  const body = _sv.loading ? '<div class="sk" style="height:280px;border-radius:18px;margin-top:18px"></div>'
    : _sv.failed ? `<div class="v3-empty">${_profileEsc(_sv.failed)} <button type="button" class="v3-link" onclick="openStoreV3('${_sv.tab}')">Повторить</button></div>`
    : _sv.tab === 'vip' ? _svVip() : _svZarniki();
  root.innerHTML = `<div class="v3-scope lk-scope sv-scope">${_svTop()}${body}</div>`;
}

function svSaveBadge(button) {
  if (!button || button.disabled) return;
  button.disabled = true;
  api('/vip/preferences', { method: 'PUT', body: JSON.stringify({ badge_id: el('vip-badge')?.value || 'spark', badge_position: el('vip-badge-pos')?.value || 'left', reminder_enabled: !!el('vip-reminders')?.checked }) })
    .then(() => { toast('Настройки VIP сохранены'); loadProfile(); return api('/vip/status'); }).then(v => { _sv.vip = v; _svRender(); })
    .catch(e => { toast(e?.message || e || 'Не удалось сохранить', false); button.disabled = false; });
}
