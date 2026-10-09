// ── Зарники и VIP: одна страница, два раздела ─────────────────────────────────────────
// «Зарники»: баланс, пакеты Telegram Stars строками (под выбранной целью заранее выбран тот, что хватит), на что хватит пакета, кнопка.
// «VIP»: статус, поручение дня, как вас видят, что даёт, срок, значок у ника с автосохранением. Любая трата идёт через лист подтверждения (v3Confirm, app.28.js).
// Вид монолитный: ни одного блока вокруг абзаца, строки с тонкой линией, одна выбранная строка (store-v3.css).
// Деньги считает сервер (/payments/zarniki/*, /vip/*, /skins-v3/me); здесь показ и повторяемые запросы. Стили: store-v3.css.
let _sv = { tab: 'zarniki', pk: null, vip: null, st: null, sel: null, term: 30, goal: null, busy: false, loading: false, paid: 0, failed: '', seq: 0, saved: false };
const _svBal = () => Number(_profileData?.zarniki ?? _sv.st?.zarniki ?? 0);
const _svItem = id => _sv.st?.items.find(i => i.id === id) || null;

function openStoreV3(tab, goal) {
  _sv = { ..._sv, tab: tab === 'vip' ? 'vip' : 'zarniki', goal: goal || null, paid: 0, failed: '', loading: true, sel: null, seq: _sv.seq + 1 };
  switchPage('store'); _svRender();
  const mine = _sv.seq;
  Promise.all([api('/payments/zarniki/packages'), api('/vip/status').catch(() => null), api('/skins-v3/me').catch(() => null)]).then(([pk, vip, st]) => {
    if (mine !== _sv.seq) return;
    Object.assign(_sv, { pk, vip, st, loading: false, term: _svTermFor(vip) }); _svPick(_svRecommended(), true);
  }).catch(e => { if (mine !== _sv.seq) return; Object.assign(_sv, { loading: false, failed: String(e || 'Не удалось загрузить') }); _svRender(); });
}
window.openZarnikiTopup = goal => openStoreV3('zarniki', typeof goal === 'string' ? goal : null);
window.openVipModal = () => openStoreV3('vip');

// Пакет, которого хватит на цель (или самый ходовой)
function _svRecommended() {
  const packs = _sv.pk?.packages || [], goal = _sv.goal && _svItem(_sv.goal);
  if (goal && !goal.owned) {
    const need = goal.price_zarniki - _svBal(), hit = packs.find(p => p.total >= need);
    return Number((hit || packs[packs.length - 1] || {}).stars) || null;
  }
  const pop = packs.find(p => p.popular) || packs[0]; return pop ? Number(pop.stars) : null;
}
// Срок VIP по умолчанию: тридцать дней, а если их нет в списке, второй по длине
function _svTermFor(vip) { const days = (vip?.tiers || []).map(t => Number(t.duration_days)); return days.includes(30) ? 30 : days[1] || days[0] || 30; }
function _svPick(stars, quiet) { _sv.sel = stars; if (!quiet) _haptic('select'); _svRender(); }
function svTab(tab) { if (_sv.tab !== tab) { _sv.tab = tab; _haptic('select'); _svRender(); window.scrollTo(0, 0); } }
function svSelect(stars) { _svPick(Number(stars)); }
function svTerm(days) { _sv.term = Number(days); _haptic('select'); _svRender(); }

function _svTop() {
  return `<div class="lk-top"><button type="button" class="v3-link pp-back" onclick="navBack()" aria-label="Назад">‹ Назад</button></div>
    <div class="sv-tabs" role="tablist" aria-label="Раздел">${[['zarniki', 'Зарники'], ['vip', 'VIP']].map(([id, t]) => `<button type="button" role="tab" aria-selected="${_sv.tab === id}" class="${_sv.tab === id ? 'is-on' : ''}" onclick="svTab('${id}')">${t}</button>`).join('')}</div>`;
}

// ── Знак образа в строке ──────────────────────────────────────────────────────────
// Маленький неподвижный знак из палитры образа: кольцо толще и со вторым ободком с тиром. Полный образ (ореолы, детали) в строке не рисуется: он выходит за свои границы
function _svAva(item) {
  const [a, b, c] = Array.isArray(item.pal) && item.pal.length >= 3 && item.pal.every(x => /^#[0-9a-f]{6}$/i.test(x)) ? item.pal : ['#d8cffd', '#8a7be0', '#fff'];
  const idx = Math.max(0, ['D', 'C', 'B', 'A', 'S', 'SS', 'SSS'].indexOf(item.rarity || item.ceiling));
  return `<span class="sv-ava" data-t="${idx}" style="--a:${a};--b:${b};--c:${c};--w:${(2 + idx * .35).toFixed(1)}px" aria-hidden="true"></span>`;
}
function svOpenSkin(id) { if (typeof _lk !== 'undefined') _lk.sel = id; openLooksModal(); }

// ── Зарники ──────────────────────────────────────────────────────────────────────
function _svReach(total) {
  const money = _svBal() + total;
  return (_sv.st?.items || []).filter(i => !i.owned && i.buyable !== false && i.price_zarniki <= money).sort((a, b) => b.price_zarniki - a.price_zarniki).slice(0, 3);
}
function _svPacks() {
  const packs = _sv.pk?.packages || [];
  return `<div class="sv-opts" role="radiogroup" aria-label="Пакет Зарников">${packs.map(p => {
    const on = Number(p.stars) === _sv.sel;
    return `<button type="button" role="radio" aria-checked="${on}" class="sv-opt${on ? ' is-on' : ''}" onclick="svSelect(${Number(p.stars)})">
      <span class="sv-opt-main"><b>${fmt(p.total)} <i>✨</i>${p.popular ? '<em class="sv-hit">Хит</em>' : ''}</b><small>${p.bonus ? `<span class="sv-plus">+${fmt(p.bonus)} бонус</span>` : 'без бонуса'}</small></span>
      <span class="sv-opt-end">${fmt(p.stars)} ⭐</span><i class="sv-radio" aria-hidden="true"></i></button>`;
  }).join('')}</div>`;
}
function _svReachHtml(pack) {
  const goal = _sv.goal && _svItem(_sv.goal), list = pack ? _svReach(Number(pack.total)) : [], money = _svBal() + (pack ? Number(pack.total) : 0);
  const head = goal && !goal.owned ? `<p class="sv-goal">Вы выбрали «${_profileEsc(goal.name)}»: ${fmt(goal.price_zarniki)} ✨${goal.price_zarniki > _svBal() ? `, не хватает ${fmt(goal.price_zarniki - _svBal())} ✨` : ''}</p>` : '';
  if (!list.length) return head;
  return `${head}<div class="sv-sec"><span class="v3-eyebrow">Хватит на</span><small>на счёте будет ${fmt(money)} ✨</small></div>
    <div class="sv-reach">${list.map(i => `<button type="button" class="v3-row sv-go" onclick="svOpenSkin('${i.id}')" aria-label="${_profileEsc(i.name)}, ${fmt(i.price_zarniki)} Зарников. Открыть образ">${_svAva(i)}
      <span><b>${_profileEsc(i.name)}</b><small>редкость <em class="sv-tier">${_profileEsc(i.rarity)}</em></small></span><span class="v3-end">${fmt(i.price_zarniki)} ✨ ${_v3Icon('chev')}</span></button>`).join('')}</div>`;
}
function _svZarniki() {
  const pk = _sv.pk, pack = (pk?.packages || []).find(p => Number(p.stars) === _sv.sel);
  if (!pk) return '';
  const off = pk.purchase_enabled === false;
  return `<p class="sv-lead">Образы, Эссенция и VIP за Зарники.</p>
    ${_sv.paid ? `<p class="sv-ok" role="status"><b>+${fmt(_sv.paid)} ✨</b> зачислено${_sv.goal && _svItem(_sv.goal) && !_svItem(_sv.goal).owned ? ` <button type="button" class="v3-link" onclick="navBack()">К образу ›</button>` : ''}</p>` : ''}
    <div class="sv-sec"><span class="v3-eyebrow">Пополнить</span></div>${_svPacks()}
    ${off ? `<p class="sv-fine">${pk.purchase_disabled_reason === 'preprod' ? 'На тестовом стенде платежи отключены. В продакшене пополнение работает.' : 'Пополнение сейчас недоступно.'}</p>`
      : `<button type="button" class="v3-pill sv-buy${_sv.busy ? ' is-busy' : ''}" ${_sv.busy || !pack ? 'disabled' : ''} onclick="svPay()">${_sv.busy ? 'Открываем оплату…' : pack ? `Купить ${fmt(pack.total)} ✨ · ${fmt(pack.stars)} ⭐` : 'Выберите пакет'}</button>
      <p class="sv-fine">Оплата в Telegram Stars. Зачисление после оплаты.</p>`}
    ${_svReachHtml(pack)}`;
}
async function svPay() {
  const stars = _sv.sel, pack = (_sv.pk?.packages || []).find(p => Number(p.stars) === stars);
  if (_sv.busy || !pack) return;
  const ok = await v3Confirm({ title: 'Пополнение Зарников', visual: '✨', name: `${fmt(pack.total)} ✨`, sub: pack.bonus ? `${fmt(pack.zarniki)} и ${fmt(pack.bonus)} в подарок` : 'Без бонуса',
    rows: [['Вы получите', `${fmt(pack.total)} ✨`], ['Оплата', `${fmt(pack.stars)} ⭐ Telegram Stars`], ['Будет на счёте', `${fmt(_svBal() + Number(pack.total))} ✨`, true]], cta: `Оплатить ${fmt(pack.stars)} ⭐`, note: 'Оплата откроется в Telegram. Зарники придут сразу после неё.' });
  if (!ok) return;
  const btn = document.querySelector('#pg-store .sv-buy')?.getBoundingClientRect(), origin = btn ? { x: btn.left + btn.width / 2, y: btn.top + btn.height / 2 } : null;   // откуда полетят искры
  _sv.busy = true; _svRender();
  try {
    const invoice = await api('/payments/zarniki/invoice', { method: 'POST', body: JSON.stringify({ stars }) });
    if (!invoice?.link) throw new Error('Счёт не создан.');
    if (typeof tg?.openInvoice === 'function') {
      tg.openInvoice(invoice.link, status => {
        if (status !== 'paid') return;
        _haptic('success'); _sv.paid = Number(pack.total); _v3RefreshBalance(); v3Fly(origin, 'zarniki', '✨', 6);
        api('/skins-v3/me').then(st => { _sv.st = st; _svRender(); }).catch(() => _svRender());
      });
    } else location.assign(invoice.link);
  } catch (e) { toast(e, false); }
  finally { _sv.busy = false; _svRender(); }
}

// ── VIP ──────────────────────────────────────────────────────────────────────────
// Кольцо статуса: дуга показывает остаток срока (до 30 дней полный круг), в центре корона
function _svRing(days) {
  const share = Math.min(1, Math.max(0, days) / 30);
  return `<svg class="sv-ring" viewBox="0 0 44 44" aria-hidden="true"><circle cx="22" cy="22" r="19" class="sv-ring-track"/><circle cx="22" cy="22" r="19" class="sv-ring-arc" stroke-dasharray="119.4" stroke-dashoffset="${(119.4 * (1 - share)).toFixed(1)}"/><path d="M13.5 28l2.2-9.6 4.4 4.8L22 16.6l1.9 6.6 4.4-4.8 2.2 9.6z" class="sv-ring-crown"/></svg>`;
}
function _svStatus(v) {
  return v.active
    ? `<section class="sv-status is-on" role="status">${_svRing(v.days_left || 0)}<div><b>VIP активен</b><span>ещё ${fmt(v.days_left || 0)} дн. · до ${_profileDate(v.expires_at)}</span></div></section>`
    : `<section class="sv-status" role="status">${_svRing(0)}<div><b>VIP не активен</b><span>С ним ваш образ видят все, а наград больше</span></div></section>`;
}
// Поручение дня: семь точек до бонуса, данные приходят с /vip/status
function _svMission(v) {
  const m = v.daily_mission; if (!v.active || !m) return '';
  const done = Number(m.cycle_progress) || 0;
  return `<div class="sv-sec"><span class="v3-eyebrow">Поручение дня</span><span class="sv-mission-end"><span class="sv-dots" role="img" aria-label="До бонуса: ${done} из 7">${Array.from({ length: 7 }, (_, i) => `<i${i < done ? ' class="is-on"' : ''}></i>`).join('')}</span><em class="${m.completed_today ? 'is-done' : ''}">${m.completed_today ? 'Сегодня ✓' : 'Не выполнено'}</em></span></div>
    <p class="sv-text"><b>${_profileEsc(m.title || 'Заверши одну игру')}</b> · +${fmt(m.daily_reward_mora || 20)} Моры; на седьмое ещё +${fmt(m.milestone_reward_mora || 100)} и ключ. Пропуски прогресс не сбрасывают</p>`;
}
// Как вас видят другие: две миниатюры профиля. Без VIP чужой видит обычный профиль, с VIP целиком ваш образ: фон, ореол, рамку на аватаре, ник и титул.
// Показывается надетый образ в его нынешнем тире, а если образа нет, образ недели с потолком (так видно, что покупает VIP)
function _svSee() {
  const worn = _sv.st?.items.find(i => i.equipped), shown = worn || _svItem(_sv.st?.featured?.skin_id) || _sv.st?.items[0];
  const name = String(_profileData?.display_name || 'Игрок'), avatar = _v3Avatar(_profileData || {});
  const ap = shown ? apFromLook({ ...shown, tier: worn ? (shown.shown_tier || shown.level || 'D') : shown.ceiling }) : null;
  const plain = `<div class="sv-prev"><i>Без VIP</i><div class="sv-prev-id"><div class="v3-ring"><svg viewBox="0 0 76 76" aria-hidden="true"><circle cx="38" cy="38" r="35" stroke="var(--v3-faint)"/></svg><div class="v3-ava">${avatar}</div></div>
    <div class="sv-prev-name"><span class="ap-plain">${_profileEsc(name)}</span></div><span class="sv-prev-dim">обычный профиль</span></div></div>`;
  const vip = ap ? `<div class="sv-prev is-vip" style="${v3TokenStyle(shown.tokens)}"><i>С VIP</i>${apStage(ap, `<div class="sv-prev-id"><div class="v3-ring">${apHalo(ap)}${_v3Ring(72)}<div class="v3-ava">${avatar}</div>${apFrame(ap)}</div>
      <div class="sv-prev-name">${apName(ap, _profileEsc(name))}</div>${apTitle(ap)}</div>`)}</div>`
    : `<div class="sv-prev is-vip"><i>С VIP</i><div class="sv-prev-id"><div class="v3-ring">${_v3Ring(72)}<div class="v3-ava">${avatar}</div></div><div class="sv-prev-name"><span class="ap-plain">${_profileEsc(name)} ✦</span></div></div></div>`;
  const note = !shown ? 'Образ, который вы наденете, увидят все.' : worn ? `Так другие видят «${_profileEsc(shown.name)}» в топе, в профиле и в чате. Выше тир образа, богаче вид.` : `Так выглядит образ «${_profileEsc(shown.name)}» с VIP. Сами вы видите свой образ всегда.`;
  return `<div class="sv-sec"><span class="v3-eyebrow">Как вас видят</span></div><section class="sv-see" aria-label="Как вас видят другие">${plain}${vip}</section><p class="sv-fine sv-fine--left">${note}</p>`;
}
// Что даёт: сервер присылает строки «эмодзи Название: пояснение»
function _svPerks(v) {
  return `<ul class="sv-perks">${(v.perks || []).map(t => {
    const text = String(t), icon = (text.match(/^\S+/) || [''])[0], rest = text.slice(icon.length).trim(), cut = rest.indexOf(':');
    const title = cut > 0 ? rest.slice(0, cut) : rest, cap = cut > 0 ? rest.slice(cut + 1).trim() : '';
    return `<li><span class="sv-pi" aria-hidden="true">${_profileEsc(icon)}</span><b>${_profileEsc(title)}</b>${cap ? `<small>${_profileEsc(cap)}</small>` : ''}</li>`;
  }).join('')}</ul>`;
}
function _svTerms(v) {
  const tiers = v.tiers || [], bal = _svBal(), cur = tiers.find(t => Number(t.duration_days) === _sv.term) || tiers[0]; if (!cur) return '';
  const days = Number(cur.duration_days), price = Number(cur.price_zarniki), enough = bal >= price;
  const perDay = tiers.map(t => Number(t.price_zarniki) / Number(t.duration_days)), flat = perDay.every(x => Math.abs(x - perDay[0]) < .01);
  return `<div class="sv-sec"><span class="v3-eyebrow">${v.active ? 'Продлить' : 'Оформить'}</span>${flat ? `<small>${fmt(Math.round(perDay[0]))} ✨ в день при любом сроке</small>` : ''}</div>
    <div class="sv-opts" role="radiogroup" aria-label="Срок VIP">${tiers.map(t => {
      const d = Number(t.duration_days), on = d === days;
      return `<button type="button" role="radio" aria-checked="${on}" class="sv-opt${on ? ' is-on' : ''}" onclick="svTerm(${d})"><span class="sv-opt-main"><b>${fmt(d)} ${_svDaysWord(d)}</b>${d === 365 ? '<small>целый год</small>' : ''}</span><span class="sv-opt-end">${fmt(t.price_zarniki)} ✨</span><i class="sv-radio" aria-hidden="true"></i></button>`;
    }).join('')}</div>
    ${enough ? `<button type="button" class="v3-pill sv-buy${_sv.busy ? ' is-busy' : ''}" ${_sv.busy ? 'disabled' : ''} onclick="svVipBuy(${days})">${v.active ? 'Продлить' : 'Оформить'} на ${fmt(days)} дн. · ${fmt(price)} ✨</button>`
      : `<button type="button" class="v3-pill sv-buy" onclick="_svNeed(${price})">Не хватает ${fmt(price - bal)} ✨ · пополнить</button>`}
    <p class="sv-fine">Срок добавляется к текущему, ничего не сгорает.</p>`;
}
const _svDaysWord = n => (n % 10 === 1 && n % 100 !== 11) ? 'день' : (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) ? 'дня' : 'дней';
function _svNeed(price) {   // не хватает на VIP: на вкладку пополнения, пакет подбирается под цену
  const need = price - _svBal(), packs = _sv.pk?.packages || [], hit = packs.find(p => p.total >= need);
  _sv.tab = 'zarniki'; _sv.goal = null; _sv.sel = Number((hit || packs[packs.length - 1] || {}).stars) || null; _haptic('select'); _svRender(); window.scrollTo(0, 0);
}
async function svVipBuy(days) {
  const v = _sv.vip, tier = (v?.tiers || []).find(t => Number(t.duration_days) === Number(days)); if (_sv.busy || !tier) return;
  const price = Number(tier.price_zarniki), from = v.active && v.expires_at ? new Date(v.expires_at) : new Date(), until = new Date(from.getTime() + Number(days) * 864e5);
  const ok = await v3Confirm({ title: v.active ? 'Продление VIP' : 'Оформление VIP', visual: '👑', name: `VIP на ${fmt(days)} дн.`, sub: `Будет действовать до ${_profileDate(until.toISOString())}`, price, icon: '✨', have: _svBal(), cta: `${v.active ? 'Продлить' : 'Оформить'} за ${fmt(price)} ✨`,
    note: v.active ? 'Дни добавятся к текущему сроку.' : 'Сразу после оплаты ваш образ увидят другие игроки.' });
  if (!ok) return;
  _sv.busy = true; _svRender();
  try {
    const key = (_sv.vipKeys ||= {})[days] ||= (globalThis.crypto?.randomUUID?.() || `vip-${Date.now()}`);
    const r = await api('/vip/purchase', { method: 'POST', body: JSON.stringify({ package_days: days, action_id: key }) });
    _sv.vipKeys = {}; toast(`VIP продлён на ${fmt(r.package_days)} дней`); _haptic('success');
    await Promise.all([loadProfile(), api('/vip/status').then(x => { _sv.vip = x; })]);
  } catch (e) { toast(e?.message || e || 'Покупка не выполнена', false); }
  finally { _sv.busy = false; _svRender(); }
}

// Значок у ника: двадцать значков сеткой, положение и напоминание переключателями. Всё сохраняется само, без кнопки «Сохранить»
const _SV_POS = [['left', 'Слева'], ['right', 'Справа'], ['both', 'С двух сторон'], ['hidden', 'Скрыть']];
function _svBadge(v) {
  if (!v.active) return '';
  const pr = v.preferences || {}, badge = (v.badges || []).find(b => b.id === pr.badge_id) || (v.badges || [])[0] || { id: 'spark', symbol: '✦' }, pos = pr.badge_position || 'left';
  const name = String(_profileData?.display_name || 'Игрок');
  return `<div class="sv-sec"><span class="v3-eyebrow">Значок у ника</span><small class="sv-saved${_sv.saved ? ' is-on' : ''}" role="status">${_sv.saved ? 'Сохранено ✓' : ''}</small></div>
    <p class="sv-preview" aria-label="Так выглядит ник"><span>${_profileEsc(vipName(name, true, badge.symbol, pos))}</span></p>
    <div class="sv-glyphs" role="radiogroup" aria-label="Значок">${(v.badges || []).map(b => `<button type="button" role="radio" aria-checked="${b.id === badge.id}" aria-label="${_profileEsc(b.id)}" class="sv-g${b.id === badge.id ? ' is-on' : ''}" onclick="svBadgeSet('badge_id','${_profileEsc(b.id)}')">${_profileEsc(b.symbol)}</button>`).join('')}</div>
    <div class="sv-pos" role="radiogroup" aria-label="Положение значка">${_SV_POS.map(([k, t]) => `<button type="button" role="radio" aria-checked="${pos === k}" class="${pos === k ? 'is-on' : ''}" onclick="svBadgeSet('badge_position','${k}')">${t}</button>`).join('')}</div>
    <button type="button" class="sv-switch" role="switch" aria-checked="${pr.reminder_enabled !== false}" onclick="svBadgeSet('reminder_enabled',${pr.reminder_enabled === false})"><span><b>Напоминать о поручении дня</b><small>Если оно не выполнено, вечером бот напишет в личные сообщения. Диалог с ботом нужно открыть один раз</small></span><i aria-hidden="true"></i></button>`;
}
let _svSaveTimer = 0;
function svBadgeSet(field, value) {
  const v = _sv.vip; if (!v?.active) return;
  v.preferences = { ...(v.preferences || {}), [field]: value }; _sv.saved = false; _haptic('select'); _svRender();
  clearTimeout(_svSaveTimer);
  _svSaveTimer = setTimeout(() => {      // несколько нажатий подряд уходят одним запросом
    const p = v.preferences;
    api('/vip/preferences', { method: 'PUT', body: JSON.stringify({ badge_id: p.badge_id || 'spark', badge_position: p.badge_position || 'left', reminder_enabled: p.reminder_enabled !== false }) })
      .then(() => { _sv.saved = true; _svRender(); loadProfile(); setTimeout(() => { _sv.saved = false; if (_sv.tab === 'vip') _svRender(); }, 1800); })
      .catch(e => { toast(e?.message || e || 'Не удалось сохранить', false); api('/vip/status').then(x => { _sv.vip = x; _svRender(); }).catch(() => {}); });
  }, 450);
}
function _svVip() {
  const v = _sv.vip; if (!v) return `<p class="sv-lead">VIP сейчас недоступен.</p>`;
  return `${_svStatus(v)}${_svTerms(v)}${_svMission(v)}<details class="sv-details"><summary>Что даёт VIP</summary>${_svPerks(v)}</details><details class="sv-details"><summary>Как вас видят другие</summary>${_svSee()}</details><details class="sv-details"><summary>Значок у ника</summary>${_svBadge(v)}</details>`;
}

function _svRender() {
  const root = el('pg-store'); if (!root) return;
  const body = _sv.loading ? '<div class="sv-skel" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>'
    : _sv.failed ? `<div class="v3-empty">${_profileEsc(_sv.failed)} <button type="button" class="v3-link" onclick="openStoreV3('${_sv.tab}')">Повторить</button></div>`
    : _sv.tab === 'vip' ? _svVip() : _svZarniki();
  root.innerHTML = `<div class="v3-scope lk-scope sv-scope v3-stagger">${_svTop()}${body}</div>`;
  v3EnterSync(root);
}
