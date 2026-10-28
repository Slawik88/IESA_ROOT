// ── Казино «Зал Фортуны» (core/casino_v1.py): Руны удачи, Колесо, Кости — на жетоны ───────────────────────────
// Монолит (docs/MONOLITH_V3.md): крупный баланс на холсте, текстовые вкладки, одна главная пилюля «Крутить»,
// сцена игры — единственная поверхность экрана. Сервер тянет жребий и считает выплату; здесь только показ.
// Анимация лишь проигрывает уже известный исход; при «меньше движения» исход показывается сразу.
const _cs = { me: null, owner: null, game: 'slots', funds: 'bonus', stake: 100, chance: 50, busy: false, seq: 0, pending: {}, last: null, notice: '', ui: {open:{},draft:'',errors:{},actionFocus:null} };
const _CS_GAMES = [['slots', 'Руны удачи'], ['wheel', 'Колесо'], ['dice', 'Кости']];
const _CS_SYM = { blank: '·', fehu: 'ᚠ', raido: 'ᚱ', thurs: 'ᚦ', comet: '☄', herald: '✺' };
const _csCalm = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
const _csX = m => '×' + (m / 100).toLocaleString('ru', { maximumFractionDigits: 2 });
const _csBalance = n => Number(n) >= 100000 ? Number(n).toLocaleString('ru', { notation: 'compact', maximumFractionDigits: 1 }) : fmt(n);
const _csId = () => (crypto.randomUUID ? crypto.randomUUID() : 'cs' + Date.now() + Math.random().toString(16).slice(2));

function openCasino() {
  switchPage('casino');
  const root = el('pg-casino'); if (!root || !_isPageEnabled('casino')) return;
  if (!_cs.me) root.innerHTML = `${v3Head('Казино', { back: 'navBack()' })}<div class="sk" style="height:96px;border-radius:18px;margin-top:8px"></div><div class="sk" style="height:220px;border-radius:18px;margin-top:22px"></div>`;
  return _csLoad();
}
function _csLoad() {
  if (_cs.busy) return Promise.resolve();
  const mine = ++_cs.seq;
  return api('/casino-v1/me').then(me => { if (mine !== _cs.seq || _cs.busy) return; _cs.me = me; _csRestore(); _csRender(); })
    .catch(error => {
      if (mine !== _cs.seq) return;
      const root = el('pg-casino'); if (!root || _activePage !== 'casino') return;
      root.innerHTML = `${v3Head('Казино', { back: 'navBack()' })}<div class="v3-empty" role="alert"><b>Казино не открылось</b><span>${esc(typeof error === 'string' ? error : 'Нет связи.')}</span> <button type="button" class="v3-link" onclick="openCasino()">Повторить</button></div>`;
    });
}

function _csFocus() {
  const root=el('pg-casino'),node=document.activeElement;
  if(_activePage!=='casino' || !root?.contains(node)) return null;
  return {id:node.id,key:node.dataset.csFocus,click:node.getAttribute('onclick')};
}
function _csCaptureUI() {
  const root=el('pg-casino');
  if(root?.dataset.csOwner!==String(_cs.me?.user_id)) return;
  root.querySelectorAll('details[data-cs-detail]').forEach(d=>{_cs.ui.open[d.dataset.csDetail]=d.open;});
}
function _csReturnFocus(focus) {
  const root=el('pg-casino'),active=document.activeElement;
  if(!focus || _activePage!=='casino' || (active!==document.body && !root?.contains(active))) return;
  let node=focus.id?el(focus.id):null;
  if(!node && focus.key) node=[...root.querySelectorAll('[data-cs-focus]')].find(n=>n.dataset.csFocus===focus.key);
  if(!node && focus.click) node=[...root.querySelectorAll('button')].find(n=>n.getAttribute('onclick')===focus.click);
  if(node && !node.disabled && node.getClientRects().length) node.focus({preventScroll:true});
}
function casinoWithdrawDraft(input) {
  _cs.ui.draft=input.value;_cs.ui.errors.withdraw='';_cs.ui.withdrawSuccess='';
  input.setAttribute('aria-invalid','false');
  const message=el('cs-withdraw-message');if(message) message.textContent='';
}
function casinoWithdrawAll() {
  const input=el('cs-withdraw-amount');if(!input || input.disabled) return;
  input.value=_cs.me.wallet.redeemable;casinoWithdrawDraft(input);input.focus({preventScroll:true});
}
function _csRender() {
  const root = el('pg-casino'); if (!root || !_cs.me) return;
  const focus=_csFocus()||_cs.ui.actionFocus;_csCaptureUI();
  if(_cs.ui.forceOpen) _cs.ui.open[_cs.ui.forceOpen]=true;
  const w = _cs.me.wallet, r = _cs.me.rules;
  const available = _csAvailable();
  const gift = w.gift_ready ? `<button type="button" class="v3-pill v3-pill--ghost v3-pill--sm" onclick="casinoGift(this)"${_cs.busy ? ' disabled' : ''}>Подарок +${fmt(r.daily_gift)}</button>` : '<span class="cs-gift-done">Подарок дня получен</span>';
  root.innerHTML = `${v3Head('Казино', { sub: 'Зал Фортуны · игра на жетоны', back: 'navBack()' })}
    <section class="cs-bank" aria-label="Жетоны"><div class="cs-funds" role="group" aria-label="Баланс для игры">${[['bonus','Подарочные'],['redeemable','С выводом']].map(([key,label]) => `<button type="button" class="cs-fund${_cs.funds === key ? ' on' : ''}" aria-label="${label}: ${fmt(w[key] || 0)} жетонов" aria-pressed="${_cs.funds === key}" onclick="casinoFunds('${key}')"${_csLocked() ? ' disabled' : ''}><b id="cs-${key}" title="${fmt(w[key] || 0)}">${_csBalance(w[key] || 0)}</b><small>${label}</small></button>`).join('')}</div>${gift}</section>
    <div class="v3-tabs v3-tabs--wide cs-tabs" role="group" aria-label="Игра">${_CS_GAMES.map(([id, name]) => `<button type="button" class="v3-tab${_cs.game === id ? ' on' : ''}" aria-pressed="${_cs.game === id}" onclick="casinoGame('${id}')"${_csLocked() ? ' disabled' : ''}>${name}</button>`).join('')}</div>
    <section class="cs-stage" id="cs-stage" aria-label="Игровая сцена" aria-busy="${_cs.busy}">${_csStage()}</section>
    ${_cs.game === 'dice' ? _csChances(r) : ''}
    <div class="cs-seg" role="group" aria-label="Ставка в жетонах">${r.stakes.map(s => `<button type="button" class="cs-opt${_cs.stake === s ? ' on' : ''}" aria-pressed="${_cs.stake === s}" onclick="casinoStake(${s})"${_csLocked() ? ' disabled' : ''}>${fmt(s)}</button>`).join('')}</div>
    <button type="button" class="v3-pill v3-pill--full cs-go" id="cs-go" onclick="casinoPlay()"${_cs.busy || _cs.pending.buy || _cs.pending.withdraw || (!_cs.pending.play && available < _cs.stake) ? ' disabled' : ''}>${_csGoLabel()}</button>
    <p class="cs-note" id="cs-note" role="status">${esc(_cs.notice || (_cs.pending.play ? 'Ответ не получен. Проверьте тот же раунд без повторной ставки.' : available < _cs.stake ? 'На выбранном балансе мало жетонов. Смените баланс или ставку.' : _cs.funds === 'bonus' ? 'Подарочная игра · выигрыши без вывода' : 'Игра на жетоны с выводом 1:1'))}</p>
    <div class="cs-odds">${_csOdds(r)}</div>
    ${_csExchange(w)}${_csBuy(w, r)}
    <div id="cs-history">${_csHistory()}</div><div id="cs-badges">${_csBadges()}</div>
    ${_csLuck()}${_csHelp(r)}`;
  if (_cs.last?.game === _cs.game && (_cs.last.detail.funds || 'bonus') === _cs.funds && !_cs.busy) { _csFinal(_cs.last); _csShow(_cs.last); }
  root.dataset.csOwner=String(_cs.me.user_id);
  root.querySelectorAll('details[data-cs-detail]').forEach(d=>{if(_cs.ui.open[d.dataset.csDetail]) d.open=true;});
  _csReturnFocus(focus);_cs.ui.actionFocus=null;_cs.ui.forceOpen=null;
  if (typeof v3EnterSync === 'function') v3EnterSync(root);
}
function _csGoLabel() { return _cs.busy ? 'Играем…' : _cs.pending.play ? 'Проверить результат' : (_cs.game === 'slots' ? 'Крутить барабаны' : _cs.game === 'wheel' ? 'Крутить колесо' : 'Бросить кости') + ' · ' + fmt(_cs.stake) + ' жет.'; }

function _csStage() {
  if (_cs.game === 'slots') return `<div class="cs-stage-meta"><span>Линия удачи</span><span>до ×300</span></div><div class="cs-reels" aria-hidden="true">${[0, 1, 2].map(i => `<div class="cs-reel" id="cs-reel-${i}"><div class="cs-strip">${_csStrip(['blank', ['fehu', 'herald', 'raido'][i], 'comet'])}</div></div>`).join('')}</div><p class="cs-out" id="cs-out" role="status">Три одинаковых символа · ✺ платит везде</p>`;
  if (_cs.game === 'wheel') return `<div class="cs-wheel-box"><i class="cs-pin" aria-hidden="true"></i>${_csWheelSvg()}</div><p class="cs-out" id="cs-out" role="status">Сектор умножает ставку · пустой без выплаты</p>`;
  return `<div class="cs-dice"><b id="cs-roll" aria-hidden="true">—</b><small>от 1 до 100 · выплата при ${_cs.chance} и меньше</small></div><p class="cs-out" id="cs-out" role="status">Выберите шанс и бросьте кости</p>`;
}
function _csStrip(keys) { return keys.map(k => `<span class="cs-symbol" data-symbol="${k}">${_CS_SYM[k] || '·'}</span>`).join(''); }
function _csOdds(r) {
  if (_cs.game === 'slots') return `Выплата в ${r.slots.hit_rate}% игр · больше ставки в ${r.slots.win_rate}%`;
  if (_cs.game === 'wheel') return `Выплата в ${r.wheel.hit_rate}% игр · больше ставки в ${r.wheel.win_rate}%`;
  const mult = r.dice.chances.find(c => c.chance === _cs.chance)?.mult || 0;
  return `Шанс выплаты ${_cs.chance}% · ${fmt(Math.floor(_cs.stake * mult / 100))} за ставку ${fmt(_cs.stake)}`;
}
function _csWheelSvg() {
  const sectors = _cs.me.rules.wheel.sectors, n = sectors.length, R = 100;
  const parts = sectors.map((m, i) => {
    const a0 = (i / n) * 2 * Math.PI - Math.PI / 2, a1 = ((i + 1) / n) * 2 * Math.PI - Math.PI / 2, mid = (a0 + a1) / 2;
    const p = a => `${(R + R * Math.cos(a)).toFixed(2)},${(R + R * Math.sin(a)).toFixed(2)}`;
    const tx = R + R * .74 * Math.cos(mid), ty = R + R * .74 * Math.sin(mid), deg = mid * 180 / Math.PI + 90;
    return `<path class="cs-sec cs-sec-${m >= 300 ? 'hi' : m >= 100 ? 'mid' : 'lo'}" d="M${R},${R} L${p(a0)} A${R},${R} 0 0 1 ${p(a1)} Z"/>` +
      (m ? `<text x="${tx.toFixed(1)}" y="${ty.toFixed(1)}" transform="rotate(${deg.toFixed(1)} ${tx.toFixed(1)} ${ty.toFixed(1)})">${_csX(m)}</text>` : '');
  }).join('');
  return `<svg class="cs-wheel" id="cs-wheel" viewBox="0 0 200 200" role="img" aria-label="Колесо из ${n} секторов">${parts}<circle cx="100" cy="100" r="14" class="cs-hub"/></svg>`;
}
function _csChances(r) {
  return `<div class="cs-seg cs-chances" role="group" aria-label="Шанс">${r.dice.chances.map(c => `<button type="button" class="cs-opt${_cs.chance === c.chance ? ' on' : ''}" aria-pressed="${_cs.chance === c.chance}" onclick="casinoChance(${c.chance})"${_csLocked() ? ' disabled' : ''}><b>${c.chance}%</b><small>${_csX(c.mult)}</small></button>`).join('')}</div>`;
}
function _csBuy(w, r) {
  const rows = r.mora_packs.map(m => { const chips = m * r.chips_per_mora, over = chips > w.buy_left;
    return `<div class="v3-line cs-buy"><span>${fmt(chips)} с выводом</span><button type="button" class="v3-pill v3-pill--ghost v3-pill--sm" onclick="casinoBuy(this,${m})"${_cs.busy || _cs.pending.play || _cs.pending.withdraw || (_cs.pending.buy ? _cs.pending.buy.mora !== m : over) ? ' disabled' : ''}>${_cs.pending.buy?.mora === m ? 'Проверить покупку' : fmt(m) + ' Моры'}</button></div>`; }).join('');
  return `<details data-cs-detail="buy" class="cs-help cs-shop"${_cs.pending.buy ? ' open' : ''}><summary data-cs-focus="buy-summary">Жетоны за Мору <span>сегодня ещё ${fmt(w.buy_left)}</span></summary><p id="cs-buy-message" class="cs-form-note" role="alert">${esc(_cs.ui.errors.buy||'')}</p>${rows}</details>`;
}
function _csExchange(w) {
  const pending = _cs.pending.withdraw, blocked = _cs.busy || _cs.pending.buy || _cs.pending.play;
  return `<details data-cs-detail="withdraw" class="cs-help cs-shop cs-exchange"${pending ? ' open' : ''}><summary data-cs-focus="withdraw-summary">Вывести в Мору <span>${fmt(w.redeemable)} доступно · 1:1</span></summary><p>Подарочные жетоны и их выигрыши не выводятся. Купленные и выигрыши с них — 1 жетон за 1 Мору.</p><form novalidate onsubmit="casinoWithdraw(event);return false"><label for="cs-withdraw-amount">Сколько жетонов вывести</label><div class="cs-exchange-field"><input id="cs-withdraw-amount" class="v3-field" oninput="casinoWithdrawDraft(this)" aria-describedby="cs-withdraw-message" aria-invalid="${!!_cs.ui.errors.withdraw}" inputmode="numeric" type="number" min="1" max="${pending ? pending.chips : w.redeemable}" step="1" value="${pending ? pending.chips : esc(_cs.ui.draft)}"${blocked || pending ? ' disabled' : ''} placeholder="От 1 жетона"><button type="button" class="v3-link" onclick="casinoWithdrawAll()"${blocked || pending || !w.redeemable ? ' disabled' : ''}>Все</button></div><p id="cs-withdraw-message" class="cs-form-note" role="${_cs.ui.errors.withdraw?'alert':'status'}">${esc(_cs.ui.errors.withdraw||_cs.ui.withdrawSuccess||'')}</p><button type="submit" data-cs-focus="withdraw-submit" class="v3-pill v3-pill--ghost v3-pill--full"${blocked || (!pending && !w.redeemable) ? ' disabled' : ''}>${pending ? 'Проверить вывод' : 'Вывести 1:1'}</button></form></details>`;
}
function _csHistory() {
  const rows = (_cs.me.recent || []).slice(0, 5);
  if (!rows.length) return '';
  return `<div class="v3-sec"><span class="v3-eyebrow">Последние игры</span></div>${rows.map(r => {
    const net = r.payout - r.stake, name = _CS_GAMES.find(g => g[0] === r.game)?.[1] || 'Игра';
    return `<div class="v3-line cs-history"><span>${name}<small>${r.detail?.funds === 'redeemable' ? 'С выводом' : 'Подарочные'} · ставка ${fmt(r.stake)} · ${_csX(r.mult)}</small></span><b>${net > 0 ? '+' : net < 0 ? '−' : ''}${fmt(Math.abs(net))}</b></div>`;
  }).join('')}`;
}
function _csBadges() {
  const badges = _cs.me.achievements || [];
  return `<details class="cs-help cs-badges" data-cs-detail="badges"><summary data-cs-focus="badges-summary">Достижения <span>${badges.filter(b => b.unlocked).length} / ${badges.length}</span></summary>${badges.map(b => `<div class="v3-line cs-badge${b.unlocked ? ' is-done' : ''}"><i aria-hidden="true">${esc(b.icon)}</i><span><b>${esc(b.title)}</b><small>${esc(b.help)}</small></span><em>${b.unlocked ? '<span class="sr-only">Открыто</span>✓' : b.target === 3 ? b.progress + '/3' : '◇'}</em></div>`).join('')}<p class="cs-dim">Прошлые партии тоже учитываются. Значки без валютных наград.</p><button type="button" class="v3-link" onclick="openAchievementsV1();achievementsV1Filter('casino')">Все достижения ›</button></details>`;
}
function _csLuck() {
  const rows = (_cs.me.luck || []).slice(0, 5);
  const who = p => { const ap = p && p.look && typeof apFromLook === 'function' ? apFromLook(p.look) : null, name = esc(p?.display_name || 'Игрок'); return ap ? apName(ap, name, p.display_name) : name; };
  const list = rows.length ? rows.map(r => `<div class="v3-line cs-luck${r.is_me ? ' is-me' : ''}"><span><i>#${r.place}</i> ${who(r.player)}</span><span class="cs-luck-v">${_csX(r.mult)} · +${fmt(r.payout)}</span></div>`).join('')
    : '<p class="cs-dim cs-luck-empty">Крупных выигрышей на этой неделе ещё нет — от ×5 попадают сюда.</p>';
  return `<div class="v3-sec"><span class="v3-eyebrow">Удача недели</span></div>${list}`;
}
function _csHelp(r) {
  const s = r.slots, sym = s.symbols;
  return `<details class="cs-help" data-cs-detail="rules"><summary data-cs-focus="rules-summary">Как устроено и шансы</summary>
    <p><b>Два вида жетонов.</b> Подарочные: подарок дня (${fmt(r.daily_gift)}) и всё, что выиграно с них. Вывести их в Мору нельзя.</p>
    <p><b>Жетоны с выводом</b> покупаются за Мору и выводятся обратно по курсу 1 к 1. Покупать можно не больше ${fmt(r.daily_buy_cap)} жетонов в день. При ставке два вида не смешиваются: ты выбираешь, какими играть.</p>
    <p>Жетоны, купленные до обновления, считались по старому курсу: вывести можно не больше, чем на них потрачено Моры. Остальное осталось подарочным.</p>
    <p><b>Руны удачи</b> · в среднем возвращается ${s.rtp}% ставок · выплата бывает в ${s.hit_rate}% вращений, выигрыш больше ставки — в ${s.win_rate}%<br>${['herald', 'comet', 'thurs', 'raido', 'fehu'].map(k => `${sym[k]}${sym[k]}${sym[k]} ${_csX(s.triple[k])}`).join(' · ')} · два ${sym.herald} ${_csX(s.two_heralds)} · один ${sym.herald} ${_csX(s.one_herald)} · пара на первых двух ${_csX(s.first_pair)}</p>
    <p><b>Колесо</b> · в среднем возвращается ${r.wheel.rtp}% ставок · ${r.wheel.sectors.length} равных секторов: ${r.wheel.sectors.filter(Boolean).sort((a, b) => b - a).map(_csX).join(', ')}. В остальных секторах выплаты нет.</p>
    <p><b>Кости</b> · ${r.dice.chances.map(c => `${c.chance}% → ${_csX(c.mult)}`).join(' · ')} · в среднем возвращается около 98% ставок.</p>
    <p><b>Как читать числа.</b> Выплата уже включает ставку: ×1 возвращает её, ×0,5 — половину, ×3 — втрое больше. Жетоны округляются вниз до целого, поэтому на малых ставках возвращается чуть меньше. Проценты — среднее за много игр, а не обещание выигрыша.</p>
    <p class="cs-dim">Исход определяется в момент нажатия, барабаны лишь показывают его. Играй ради удовольствия и только на то, что не жалко.</p></details>`;
}

function _csLocked() { return _cs.busy || !!_cs.pending.play || !!_cs.pending.buy || !!_cs.pending.withdraw; }
function _csAvailable() { return Number(_cs.me?.wallet?.[_cs.funds] || 0); }
function casinoFunds(funds) { if (_csLocked() || !['bonus','redeemable'].includes(funds)) return; _cs.funds = funds; _cs.notice = ''; _csRender(); }
function casinoGame(id) { if (_csLocked() || !_CS_GAMES.some(g => g[0] === id)) return; _cs.game = id; _cs.notice = ''; _csRender(); }
function casinoStake(s) { if (_csLocked() || !_cs.me.rules.stakes.includes(s)) return; _cs.stake = s; _cs.notice = ''; _csRender(); }
function casinoChance(c) { if (_csLocked() || !_cs.me.rules.dice.chances.some(x => x.chance === c)) return; _cs.chance = c; _csRender(); }
function _csWallet(w) { if (!_cs.me || !w) return; _cs.me.wallet = w; ['bonus','redeemable'].forEach(key => { const n = el('cs-' + key); if (n) { n.textContent = _csBalance(w[key]); n.title = fmt(w[key]); n.parentElement.setAttribute('aria-label', `${key === 'bonus' ? 'Подарочные' : 'С выводом'}: ${fmt(w[key])} жетонов`); } }); }
function _csSave() {
  try { if (_cs.me?.user_id) sessionStorage.setItem('pv_cs_pending:' + _cs.me.user_id, JSON.stringify(_cs.pending)); } catch (_) {}
}
function _csRestore() {
  if (_cs.owner !== _cs.me.user_id) { _cs.pending = {}; _cs.last = null; _cs.notice = ''; _cs.owner = _cs.me.user_id; _cs.ui={open:{},draft:'',errors:{},actionFocus:null}; }
  try { const saved = sessionStorage.getItem('pv_cs_pending:' + _cs.me.user_id); if (saved) _cs.pending = JSON.parse(saved) || {}; } catch (_) {}
  const p = _cs.pending.play;
  if (p) { _cs.game = p.game; _cs.stake = p.stake; _cs.funds = p.funds || 'bonus'; if (p.chance) _cs.chance = p.chance; }
}
async function _csPost(path, body) {
  // Only business/validation rejections prove this body was refused. Auth/gate/rate errors may hide a prior commit.
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(BASE + '/casino-v1' + path, { method: 'POST', headers: hdrs(), body: JSON.stringify(body || {}), signal: controller.signal });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const error = new Error(_humanErr(typeof payload.detail === 'string' ? payload.detail : 'Не получилось выполнить действие.', response.status));
      error.status = response.status;
      error.definitive = response.status === 409 || response.status === 422;
      if (response.status === 401) handleAuthRefusal(response.headers.get('x-auth-reason') || '');
      throw error;
    }
    const result = await response.json(); _scheduleReactiveRefresh(); return result;
  } finally { clearTimeout(timeout); }
}
function _csBusy(value) {
  if(value) {_csCaptureUI();_cs.ui.actionFocus=_csFocus();}
  _cs.busy = value;
  el('cs-stage')?.setAttribute('aria-busy', String(value));
  if (value) el('pg-casino')?.querySelectorAll('.cs-bank button,.cs-tabs button,.cs-opt,.cs-buy button,.cs-exchange button,.cs-exchange input,.cs-go').forEach(b => { b.disabled = true; });
  const go = el('cs-go'); if (go) go.textContent = _csGoLabel();
}

async function casinoGift() {
  if (_cs.busy) return;
  ++_cs.seq; _csBusy(true);
  try { const r = await _csPost('/gift'); _csWallet(r.wallet); _cs.notice = ''; toast('+' + fmt(r.gift) + ' жетонов'); }
  catch (e) { _cs.notice = e.message || 'Нет связи. Проверьте баланс перед повтором.'; }
  finally { _csBusy(false); _csRender(); }
}
async function casinoBuy(btn, mora) {
  if (_cs.busy || _cs.pending.play || _cs.pending.withdraw || (_cs.pending.buy && _cs.pending.buy.mora !== mora)) return;
  _cs.ui.errors.buy='';
  ++_cs.seq; _csBusy(true);
  const body = _cs.pending.buy || { mora, action_id: _csId() }; _cs.pending.buy = body; _csSave();
  try { const r = await _csPost('/buy', body); _csWallet(r.wallet); delete _cs.pending.buy;_cs.ui.errors.buy=''; _cs.notice = ''; toast('Покупка подтверждена: ' + fmt(r.chips) + ' жетонов'); }
  catch (e) { if (e.definitive) delete _cs.pending.buy; _cs.ui.forceOpen='buy';_cs.notice=''; _cs.ui.errors.buy = e.definitive ? e.message : 'Ответ о покупке не получен. Нажмите «Проверить покупку» — повторной оплаты не будет.'; }
  finally { _csSave(); _csBusy(false); _csRender(); }
}
async function casinoWithdraw(event) {
  event?.preventDefault();
  if (_cs.busy || _cs.pending.play || _cs.pending.buy) return;
  const chips = _cs.pending.withdraw?.chips ?? Number(el('cs-withdraw-amount')?.value);
  if (!Number.isSafeInteger(chips) || chips < 1 || (!_cs.pending.withdraw && chips>_cs.me.wallet.redeemable)) {
    _cs.ui.errors.withdraw=Number.isSafeInteger(chips)&&chips>_cs.me.wallet.redeemable ? 'Доступно к выводу '+fmt(_cs.me.wallet.redeemable)+' жетонов.' : 'Укажите целое положительное число жетонов.';
    _cs.ui.forceOpen='withdraw';_csRender();el('cs-withdraw-amount')?.focus({preventScroll:true});return;
  }
  const body = _cs.pending.withdraw || { chips, action_id: _csId() };
  _cs.ui.errors.withdraw='';_cs.ui.withdrawSuccess='';
  ++_cs.seq; _cs.pending.withdraw = body; _csSave(); _csBusy(true);
  try { const r = await _csPost('/withdraw', body); _csWallet(r.wallet); delete _cs.pending.withdraw; _cs.ui.draft='';_cs.ui.errors.withdraw='';_cs.ui.withdrawSuccess='На баланс зачислено '+fmt(r.mora)+' Моры.'; _cs.notice = ''; toast('На баланс +' + fmt(r.mora) + ' Моры'); }
  catch (e) { if (e.definitive) delete _cs.pending.withdraw; _cs.ui.forceOpen='withdraw'; _cs.notice=''; _cs.ui.errors.withdraw = e.definitive ? e.message : 'Ответ о выводе не получен. Нажмите «Проверить вывод» — сумму не выведет повторно.'; }
  finally { _csSave(); _csBusy(false); _csRender(); }
}

async function casinoPlay() {
  if (_cs.busy || !_cs.me || _cs.pending.buy || _cs.pending.withdraw) return;
  const body = _cs.pending.play || { game: _cs.game, funds: _cs.funds, stake: _cs.stake, action_id: _csId(), ...(_cs.game === 'dice' ? { chance: _cs.chance } : {}) };
  ++_cs.seq; _cs.pending.play = body; _csSave(); _cs.notice = ''; _csBusy(true);
  const stage = el('cs-stage'), t0 = _csSpinStart(body.game), out = el('cs-out');
  let settled = false;
  if (out) out.textContent = 'Разыгрываем ставку…';
  try {
    const r = await _csPost('/play', body);
    _csWallet(r.wallet); _cs.last = r.round; delete _cs.pending.play; _csSave();
    settled = true;
    _cs.me.recent = [r.round, ...(_cs.me.recent || []).filter(x => x.id !== r.round.id)].slice(0, 8);
    await _csSpinEnd(body.game, r.round, t0, stage);
    if (_activePage === 'casino' && r.round.payout > r.round.stake && typeof _haptic === 'function') _haptic(r.round.mult >= 500 ? 'success' : 'light');
  } catch (e) {
    if (e.definitive) delete _cs.pending.play;
    _cs.notice = settled ? '' : e.definitive ? e.message : 'Ответ не получен. Проверьте результат — этот раунд не спишет ставку повторно.';
  } finally { _csSave(); _csSpinStop(); _csBusy(false); _csRender(); if (settled) _csRefreshBadges(); }
}
async function _csRefreshBadges() {
  const seq = _cs.seq, user = _cs.me.user_id;
  try {
    const before = new Set((_cs.me.achievements || []).filter(b => b.unlocked).map(b => b.id));
    const result = await api('/achievements-v1/casino');
    if (seq !== _cs.seq || user !== _cs.me.user_id) return;
    _cs.me.achievements = result.badges;
    const node = el('cs-badges'); if (node) { const open = node.querySelector('details')?.open; node.innerHTML = _csBadges(); if (open) node.querySelector('details').open = true; }
    const fresh = result.badges.filter(b => b.unlocked && !before.has(b.id));
    if (fresh.length && _activePage === 'casino') toast('Достижение: ' + fresh.map(b => b.title).join(' · '));
  } catch (_) { /* badges are read-only and recover on the next overview */ }
}
function _csShow(round) {
  const out = el('cs-out'), net = round.payout - round.stake;
  const symbols = round.game === 'slots' ? round.detail.reels.map(k => _CS_SYM[k]).join(' ') + ' · ' : round.game === 'dice' ? 'Выпало ' + round.detail.roll + ' · ' : '';
  if (out) { out.innerHTML = `<b>${symbols}${net > 0 ? 'Выигрыш +' + fmt(net) : net === 0 ? 'Ставка вернулась' : 'Итог −' + fmt(-net)}</b><small>${round.detail.funds === 'redeemable' ? 'С выводом' : 'Подарочные'} · выплата ${fmt(round.payout)} · ставка ${fmt(round.stake)} · ${_csX(round.mult)}</small>`; out.dataset.state = net > 0 ? 'win' : net === 0 ? 'back' : 'miss'; }
}

// ── Continuous reel strips; only the server's outcome determines the final cell. ──
let _csTimer = null;
let _csAnimations = [];
function _csSpinStop() {
  clearInterval(_csTimer); _csTimer = null;
  _csAnimations.forEach(a => a.cancel()); _csAnimations = [];
  document.querySelectorAll('.cs-reel.spin').forEach(r => r.classList.remove('spin'));
}
function _csSpinStart(game) {
  _csSpinStop();
  const t0 = performance.now(); if (_csCalm()) return t0;
  const keys = Object.keys(_CS_SYM);
  if (game === 'slots') [0, 1, 2].forEach(i => {
    const reel = el('cs-reel-' + i), strip = reel?.querySelector('.cs-strip'); if (!strip) return;
    strip.innerHTML = _csStrip([...keys, ...keys, ...keys, ...keys]);
    const h = strip.firstElementChild.getBoundingClientRect().height;
    reel.classList.add('spin');
    const animation = strip.animate([{ transform: `translateY(${-h}px)` }, { transform: `translateY(${-(keys.length + 1) * h}px)` }], { duration: 400 + i * 55, iterations: Infinity, easing: 'linear' });
    _csAnimations.push(animation);
  });
  if (game === 'dice') _csTimer = setInterval(() => { const r = el('cs-roll'); if (r && _activePage === 'casino') r.textContent = 1 + Math.floor(Math.random() * 100); }, 60);
  return t0;
}
function _csFinal(round) {
  const d = round.detail || {};
  if (round.game === 'slots') [0, 1, 2].forEach(i => {
    const strip = el('cs-reel-' + i)?.querySelector('.cs-strip');
    if (strip) { strip.innerHTML = _csStrip(['blank', d.reels[i], 'blank']); strip.style.transform = 'translateY(calc(-1 * var(--cs-step)))'; }
  });
  if (round.game === 'dice') { const roll = el('cs-roll'); if (roll) { roll.textContent = d.roll; roll.dataset.state = round.payout > round.stake ? 'win' : 'miss'; } }
  if (round.game === 'wheel') { const wheel = el('cs-wheel'); if (wheel) { wheel.style.transition = 'none'; wheel.style.transform = `rotate(${-(d.sector + .5) * 360 / _cs.me.rules.wheel.sectors.length}deg)`; } }
}
function _csSpinEnd(game, round, t0, stage) {
  const calm = _csCalm() || _activePage !== 'casino' || stage !== el('cs-stage'), d = round.detail || {};
  if (calm) { _csSpinStop(); return Promise.resolve(); }
  const after = ms => new Promise(res => setTimeout(res, calm ? 0 : Math.max(0, ms - (performance.now() - t0))));
  if (game === 'slots') return after(300).then(() => Promise.all([0, 1, 2].map(i => {
    const reel = el('cs-reel-' + i), strip = reel?.querySelector('.cs-strip');
    if (!strip || !stage.isConnected || _activePage !== 'casino') return;
    const from = getComputedStyle(strip).transform, h = strip.firstElementChild.getBoundingClientRect().height, index = Object.keys(_CS_SYM).length * 2 + 1;
    _csAnimations[i]?.cancel(); strip.children[index].textContent = _CS_SYM[d.reels[i]]; strip.children[index].dataset.symbol = d.reels[i];
    const end = `translateY(${-index * h}px)`;
    const animation = strip.animate([{ transform: from }, { transform: end }], { duration: 650 + i * 220, easing: 'cubic-bezier(.12,.7,.18,1)', fill: 'forwards' });
    _csAnimations[i] = animation;
    return animation.finished.then(() => { strip.style.transform = end; reel.classList.remove('spin'); }).catch(() => {});
  })));
  if (game === 'dice') return after(800).then(() => { _csSpinStop(); const r = el('cs-roll'); if (r) { r.textContent = d.roll; r.dataset.state = round.payout ? 'win' : 'miss'; } });
  const wheel = el('cs-wheel'); if (!wheel) return Promise.resolve();
  const n = _cs.me.rules.wheel.sectors.length, turn = 4;
  const angle = turn * 360 - (d.sector + 0.5) * 360 / n;   // центр выпавшего сектора встаёт под стрелку сверху
  wheel.dataset.turn = turn; wheel.style.transition = calm ? 'none' : 'transform 2.4s cubic-bezier(.17,.67,.2,1)'; wheel.style.transform = `rotate(${angle}deg)`;
  return new Promise(res => setTimeout(res, calm ? 0 : 2450));
}

// Stop decorative work when this scene is hidden; the in-flight request still settles once.
new MutationObserver(() => { if (_activePage !== 'casino') _csSpinStop(); }).observe(el('pg-casino'), { attributes: true, attributeFilter: ['class'] });
