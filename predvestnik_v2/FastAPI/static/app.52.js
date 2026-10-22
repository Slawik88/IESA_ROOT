// ── Казино «Зал Фортуны» (core/casino_v1.py): Руны удачи, Колесо, Кости — на жетоны ───────────────────────────
// Монолит (docs/MONOLITH_V3.md): крупный баланс на холсте, текстовые вкладки, одна главная пилюля «Крутить»,
// сцена игры — единственная поверхность экрана. Сервер тянет жребий и считает выплату; здесь только показ.
// Анимация лишь проигрывает уже известный исход; при «меньше движения» исход показывается сразу.
const _cs = { me: null, game: 'slots', stake: 100, chance: 50, busy: false, seq: 0 };
const _CS_GAMES = [['slots', 'Руны удачи'], ['wheel', 'Колесо'], ['dice', 'Кости']];
const _CS_SYM = { blank: '·', fehu: 'ᚠ', raido: 'ᚱ', thurs: 'ᚦ', comet: '☄', herald: '🌌' };
const _csCalm = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
const _csX = m => '×' + (m / 100).toLocaleString('ru', { maximumFractionDigits: 2 });
const _csId = () => (crypto.randomUUID ? crypto.randomUUID() : 'cs' + Date.now() + Math.random().toString(16).slice(2));

function openCasino() {
  switchPage('casino');
  const root = el('pg-casino'); if (!root || !_isPageEnabled('casino')) return;
  if (!_cs.me) root.innerHTML = `${v3Head('Казино', { back: 'navBack()' })}<div class="sk" style="height:96px;border-radius:18px;margin-top:8px"></div><div class="sk" style="height:220px;border-radius:18px;margin-top:22px"></div>`;
  return _csLoad();
}
function _csLoad() {
  const mine = ++_cs.seq;
  return api('/casino-v1/me').then(me => { if (mine !== _cs.seq) return; _cs.me = me; _csRender(); })
    .catch(error => {
      if (mine !== _cs.seq) return;
      const root = el('pg-casino'); if (!root || _activePage !== 'casino') return;
      root.innerHTML = `${v3Head('Казино', { back: 'navBack()' })}<div class="v3-empty" role="alert"><b>Казино не открылось</b><span>${esc(typeof error === 'string' ? error : 'Нет связи.')}</span> <button type="button" class="v3-link" onclick="openCasino()">Повторить</button></div>`;
    });
}

function _csRender() {
  const root = el('pg-casino'); if (!root || !_cs.me) return;
  const w = _cs.me.wallet, r = _cs.me.rules;
  const gift = w.gift_ready ? `<button type="button" class="v3-pill v3-pill--ghost v3-pill--sm" onclick="casinoGift(this)">🎁 +${fmt(r.daily_gift)}</button>` : '<span class="cs-gift-done">Подарок дня получен</span>';
  root.innerHTML = `${v3Head('Казино', { sub: 'Зал Фортуны · игра на жетоны', back: 'navBack()' })}
    <section class="cs-bank" aria-label="Жетоны"><span class="cs-bank-n"><b id="cs-chips">${fmt(w.chips)}</b><small>жетонов</small></span>${gift}</section>
    <div class="v3-tabs v3-tabs--wide cs-tabs" role="tablist">${_CS_GAMES.map(([id, name]) => `<button type="button" role="tab" class="v3-tab${_cs.game === id ? ' on' : ''}" aria-selected="${_cs.game === id}" onclick="casinoGame('${id}')">${name}</button>`).join('')}</div>
    <section class="cs-stage" id="cs-stage" aria-live="polite">${_csStage()}</section>
    ${_cs.game === 'dice' ? _csChances(r) : ''}
    <div class="cs-seg" role="group" aria-label="Ставка">${r.stakes.map(s => `<button type="button" class="cs-opt${_cs.stake === s ? ' on' : ''}" aria-pressed="${_cs.stake === s}" onclick="casinoStake(${s})">${fmt(s)}</button>`).join('')}</div>
    <button type="button" class="v3-pill v3-pill--full cs-go" id="cs-go" onclick="casinoPlay()"${w.chips < _cs.stake ? ' disabled' : ''}>${_csGoLabel()}</button>
    <p class="cs-note" id="cs-note">${w.chips < _cs.stake ? 'Не хватает жетонов: заберите подарок дня или купите ниже.' : ''}</p>
    ${_csBuy(w, r)}${_csLuck()}${_csHelp(r)}`;
  if (typeof v3EnterSync === 'function') v3EnterSync(root);
}
function _csGoLabel() { return (_cs.game === 'slots' ? 'Крутить барабаны' : _cs.game === 'wheel' ? 'Крутить колесо' : 'Бросить кости') + ' · ' + fmt(_cs.stake); }

function _csStage() {
  if (_cs.game === 'slots') return `<div class="cs-reels">${[0, 1, 2].map(i => `<span class="cs-reel" id="cs-reel-${i}">${_CS_SYM[['fehu', 'herald', 'raido'][i]]}</span>`).join('')}</div><p class="cs-out" id="cs-out">Три одинаковые руны — выигрыш, 🌌 Предвестник платит везде.</p>`;
  if (_cs.game === 'wheel') return `<div class="cs-wheel-box"><i class="cs-pin" aria-hidden="true"></i>${_csWheelSvg()}</div><p class="cs-out" id="cs-out">Сектор под стрелкой умножает ставку</p>`;
  return `<div class="cs-dice"><b id="cs-roll">—</b><small>от 1 до 100 · выигрыш при ${_cs.chance} и меньше</small></div><p class="cs-out" id="cs-out"></p>`;
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
  return `<div class="cs-seg cs-chances" role="group" aria-label="Шанс">${r.dice.chances.map(c => `<button type="button" class="cs-opt${_cs.chance === c.chance ? ' on' : ''}" aria-pressed="${_cs.chance === c.chance}" onclick="casinoChance(${c.chance})"><b>${c.chance}%</b><small>${_csX(c.mult)}</small></button>`).join('')}</div>`;
}
function _csBuy(w, r) {
  const rows = r.mora_packs.map(m => { const chips = m * r.chips_per_mora, over = chips > w.buy_left;
    return `<div class="v3-line cs-buy"><span>${fmt(chips)} жетонов</span><button type="button" class="v3-pill v3-pill--ghost v3-pill--sm" onclick="casinoBuy(this,${m})"${over ? ' disabled' : ''}>${fmt(m)} Моры</button></div>`; }).join('');
  return `<div class="v3-sec"><span class="v3-eyebrow">Жетоны за Мору</span><small class="cs-dim">сегодня ещё ${fmt(w.buy_left)}</small></div>${rows}`;
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
  return `<details class="cs-help"><summary>Как устроено и шансы</summary>
    <p>Жетоны — валюта только казино. Их дают бесплатно раз в день (${fmt(r.daily_gift)}) и продают за Мору: 1 Мора = ${r.chips_per_mora} жетонов, не больше ${fmt(r.daily_buy_cap)} в день. Обратно в Мору или Зарники жетоны не меняются.</p>
    <p><b>Руны удачи</b> · возврат ${s.rtp}% · выигрыш в ${s.hit_rate}% вращений<br>${['herald', 'comet', 'thurs', 'raido', 'fehu'].map(k => `${sym[k]}${sym[k]}${sym[k]} ${_csX(s.triple[k])}`).join(' · ')} · два ${sym.herald} ${_csX(s.two_heralds)} · один ${sym.herald} ${_csX(s.one_herald)} · пара на первых двух ${_csX(s.first_pair)}</p>
    <p><b>Колесо</b> · возврат ${r.wheel.rtp}% · ${r.wheel.sectors.length} равных секторов: ${r.wheel.sectors.filter(Boolean).sort((a, b) => b - a).map(_csX).join(', ')}, остальные пустые.</p>
    <p><b>Кости</b> · ${r.dice.chances.map(c => `${c.chance}% → ${_csX(c.mult)}`).join(' · ')} · возврат около 96%.</p>
    <p class="cs-dim">Исход тянет сервер случайным числом до нажатия анимации; анимация лишь показывает его. Играйте ради удовольствия.</p></details>`;
}

function casinoGame(id) { if (_cs.busy || !_CS_GAMES.some(g => g[0] === id)) return; _cs.game = id; _csRender(); }
function casinoStake(s) { if (_cs.busy) return; _cs.stake = s; _csRender(); }
function casinoChance(c) { if (_cs.busy) return; _cs.chance = c; _csRender(); }
function _csWallet(w) { if (!_cs.me || !w) return; _cs.me.wallet = w; const n = el('cs-chips'); if (n) n.textContent = fmt(w.chips); }
function _csPost(path, body) { return api('/casino-v1' + path, { method: 'POST', body: JSON.stringify(body || {}) }); }

function casinoGift(btn) {
  if (btn) btn.disabled = true;
  _csPost('/gift').then(r => { _csWallet(r.wallet); toast('🎁 +' + fmt(r.gift) + ' жетонов'); _csRender(); })
    .catch(e => { if (btn) btn.disabled = false; toast(typeof e === 'string' ? e : 'Не получилось', false); });
}
function casinoBuy(btn, mora) {
  if (btn) btn.disabled = true;
  _csPost('/buy', { mora, action_id: _csId() }).then(r => { _csWallet(r.wallet); toast('+' + fmt(r.chips) + ' жетонов'); _csRender(); })
    .catch(e => { if (btn) btn.disabled = false; toast(typeof e === 'string' ? e : 'Не получилось', false); });
}

function casinoPlay() {
  if (_cs.busy || !_cs.me) return;
  const go = el('cs-go'), note = el('cs-note'), game = _cs.game, stake = _cs.stake;
  _cs.busy = true; if (go) go.disabled = true; if (note) note.textContent = '';
  const body = { game, stake, action_id: _csId() }; if (game === 'dice') body.chance = _cs.chance;
  const wait = _csSpinStart(game);
  _csPost('/play', body).then(r => _csSpinEnd(game, r.round, wait).then(() => {
    _csWallet(r.wallet); _csShow(r.round);
  })).catch(e => { _csSpinStop(); if (note) note.textContent = typeof e === 'string' ? e : 'Нет связи. Ставка не списана — попробуйте ещё раз.'; })
    .finally(() => { _cs.busy = false; const b = el('cs-go'); if (b && _cs.me) b.disabled = _cs.me.wallet.chips < _cs.stake; });
}
function _csShow(round) {
  const out = el('cs-out'), win = round.payout > 0, net = round.payout - round.stake;
  if (out) { out.textContent = win ? `${_csX(round.mult)} · +${fmt(round.payout)} жетонов` + (net < 0 ? ' (часть ставки)' : '') : 'Мимо. Удача ещё повернётся.'; out.dataset.state = net > 0 ? 'win' : win ? 'back' : 'miss'; }
  if (net > 0 && typeof _haptic === 'function') _haptic(round.mult >= 500 ? 'success' : 'light');
  if (round.mult >= 500) { _cs.me.luck = null; api('/casino-v1/me').then(me => { _cs.me.luck = me.luck; }).catch(() => {}); }
}

// ── анимации: только показ исхода, длительность ~1 с, «меньше движения» — мгновенно ──
let _csTimer = null;
function _csSpinStop() { clearInterval(_csTimer); _csTimer = null; }
function _csSpinStart(game) {
  const t0 = performance.now(); if (_csCalm()) return t0;
  const keys = Object.keys(_CS_SYM);
  if (game === 'slots') { _csTimer = setInterval(() => [0, 1, 2].forEach(i => { const r = el('cs-reel-' + i); if (r && !r.dataset.stop) r.textContent = _CS_SYM[keys[Math.floor(Math.random() * keys.length)]]; }), 70); [0, 1, 2].forEach(i => { const r = el('cs-reel-' + i); if (r) { delete r.dataset.stop; r.classList.add('spin'); } }); }
  if (game === 'dice') _csTimer = setInterval(() => { const r = el('cs-roll'); if (r) r.textContent = 1 + Math.floor(Math.random() * 100); }, 60);
  return t0;
}
function _csSpinEnd(game, round, t0) {
  const calm = _csCalm(), d = round.detail || {};
  const after = ms => new Promise(res => setTimeout(res, calm ? 0 : Math.max(0, ms - (performance.now() - t0))));
  if (game === 'slots') return after(700).then(() => new Promise(res => {
    [0, 1, 2].forEach(i => setTimeout(() => { const r = el('cs-reel-' + i); if (r) { r.dataset.stop = '1'; r.classList.remove('spin'); r.textContent = _CS_SYM[d.reels[i]] || '·'; } if (i === 2) { _csSpinStop(); res(); } }, calm ? 0 : i * 260));
  }));
  if (game === 'dice') return after(800).then(() => { _csSpinStop(); const r = el('cs-roll'); if (r) { r.textContent = d.roll; r.dataset.state = round.payout ? 'win' : 'miss'; } });
  const wheel = el('cs-wheel'); if (!wheel) return Promise.resolve();
  const n = _cs.me.rules.wheel.sectors.length, turn = (Number(wheel.dataset.turn) || 0) + 4;
  const angle = turn * 360 - (d.sector + 0.5) * 360 / n;   // центр выпавшего сектора встаёт под стрелку сверху
  wheel.dataset.turn = turn; wheel.style.transition = calm ? 'none' : 'transform 2.4s cubic-bezier(.17,.67,.2,1)'; wheel.style.transform = `rotate(${angle}deg)`;
  return new Promise(res => setTimeout(res, calm ? 0 : 2450));
}
