// ── Образы · витрина скинов ──────────────────────────────────────────────────────
// Экран продаёт сам себя: сверху ВЫ в выбранном скине (живая примерка на вашем аватаре, вся страница
// окрашивается его палитрой), ниже лента скинов, шаги прокачки тира и одно главное действие.
// Скин покупается на тире D и растёт до своего потолка за Эссенцию; превью выше D помечено как превью.
// Сервер считает всё сам (/skins-v3/*), здесь только показ и повторяемые запросы с Idempotency-Key.
const _LK_TIERS = ['D', 'C', 'B', 'A', 'S', 'SS', 'SSS'];
let _lk = { st: null, sel: null, tier: 'D', busy: false, failed: '', seq: 0, keys: {}, view: 'shop' };
let _lkFetchedAt = 0, _lkCacheEpoch = -1;
const _lkUuid = () => globalThis.crypto?.randomUUID?.() || `lk-${Date.now()}-${Math.random().toString(16).slice(2)}`;
const _lkItem = id => _lk.st?.items.find(i => i.id === id) || null;
const _lkPrice = z => `${fmt(z)} ✨`;
const _lkWeekId = st => st.featured?.skin_id || st.items[0].id;   // «образ недели»: один для всех, считает сервер (app.27.js)

function openLooksModal() {
  switchPage('looks');
  const root = el('pg-looks'); if (!root) return Promise.resolve();
  if(_lk.st && _lkCacheEpoch===_pvReadEpoch && Date.now()-_lkFetchedAt<20000){
    lkMainButton(); lkTourOnce(_lk.st); return Promise.resolve(_lk.st);
  }
  if (!_lk.st) root.innerHTML = '<div class="v3-scope lk-scope"><div class="sk" style="height:330px;border-radius:18px"></div><div class="sk" style="height:60px;border-radius:30px;margin-top:22px"></div></div>';
  const mine = ++_lk.seq;
  return api('/skins-v3/me').then(st => {
    if (mine !== _lk.seq) return;
    _lk.st = st; _lk.failed = '';
    _lkFetchedAt=Date.now(); _lkCacheEpoch=_pvReadEpoch;
    _lkPick(_lk.sel && _lkItem(_lk.sel) ? _lk.sel : (st.equipped || _lkWeekId(st)));
    lkTourOnce(st);
  }).catch(e => { if (mine !== _lk.seq) return; _lk.failed = String(e || 'Ошибка'); _lkRender(); });
}
function warmLooksV3(){
  if(_activePage==='looks' || _lk.busy || _lk.st) return;
  const mine=++_lk.seq, epoch=_pvReadEpoch;
  return api('/skins-v3/me').then(st=>{
    if(mine!==_lk.seq || epoch!==_pvReadEpoch || _activePage==='looks') return;
    _lk.st=st; _lkFetchedAt=Date.now(); _lkCacheEpoch=epoch;
    const item=st.items.find(i=>i.id===st.equipped)||st.items.find(i=>i.id===_lkWeekId(st));
    if(!item)return;
    _lk.sel=item.id; _lk.tier=item.owned?item.level:item.ceiling;
    _lkRender('',true);
  });
}
function _lkPick(id, fromUser) {
  const item = _lkItem(id); if (!item) return;
  _lk.sel = id; _lk.tier = item.owned ? item.level : item.ceiling;   // чужой скин показываем в полную силу, свой там, где он сейчас
  if (fromUser) _haptic('select');
  _lkRender(fromUser ? 'swap' : '');
}
function lkTier(tier) { if (_LK_TIERS.includes(tier)) { _lk.tier = tier; _haptic('select'); _lkRender('swap'); } }

// ── Что делает главная кнопка ────────────────────────────────────────────────────
function _lkAction(item, st) {
  const z = st.zarniki, e = st.essence.balance;
  if (!item.owned) {
    if (item.buyable === false) return { t: 'Сезон закрыт', a: '', sub: `«${item.season?.name || 'Сезонный образ'}» откроется сам ${_lkDate(item.season?.starts_at)}, через ${_lkLeft(item.season?.starts_at)}. Купленное остаётся навсегда` };
    return z >= item.price_zarniki ? { t: `Купить за ${_lkPrice(item.price_zarniki)}`, a: 'buy', sub: 'Начнёт с тира D, дальше растёт за Эссенцию' }
      : { t: `Не хватает ${_lkPrice(item.price_zarniki - z)}`, a: 'topup', sub: `Цена ${_lkPrice(item.price_zarniki)}, нажмите, чтобы пополнить` };
  }
  if (!item.equipped) return { t: 'Надеть', a: 'equip', sub: item.maxed ? 'Максимальный тир' : `Сейчас тир ${item.level}` };
  if (item.maxed) return { t: 'Максимальный тир', a: '', sub: 'Образ раскрыт полностью' };
  if (item.next.needs_vip) return { t: 'Открыть SSS с VIP', a: 'vip', sub: 'Последний тир SSS доступен только с активным VIP' };
  return e >= item.next.essence
    ? { t: `Улучшить до ${item.next.tier}`, a: 'upgrade', sub: `${fmt(item.next.essence)} Эссенции, останется ${fmt(e - item.next.essence)}`, cost: item.next.essence }
    : { t: `Не хватает ${fmt(item.next.essence - e)} Эссенции`, a: 'essence', sub: `Тир ${item.next.tier} стоит ${fmt(item.next.essence)}, нажмите, чтобы пополнить` };
}

// ── Разметка ─────────────────────────────────────────────────────────────────────
function _lkMini(item) {
  const ap = apFromLook({ ...item, tier: item.rarity || item.ceiling });   // плитка показывает образ в его начальной редкости: так он узнаваем и недорог в отрисовке
  return `<span class="lk-mini"><span class="v3-ring">${apHalo(ap)}<svg viewBox="0 0 76 76" aria-hidden="true"><circle cx="38" cy="38" r="35" stroke="var(--v3-faint)"/></svg><span class="v3-ava"></span>${apFrame(ap)}</span></span>`;
}
function _lkStrip(st) {
  let last = '';
  const week = _lkWeekId(st);
  return `<nav class="lk-strip" aria-label="Скины">${st.items.map(i => {
    const grp = i.exclusive ? 'личный' : i.season ? 'сезон' : i.rarity, label = last !== grp ? `<span class="lk-grp" aria-hidden="true">${grp}</span>` : ''; last = grp;
    const mark = i.equipped ? '<i class="lk-dot is-on" title="Надет"></i>' : i.owned ? '<i class="lk-dot" title="Куплен"></i>' : '';
    return `${label}<button type="button" class="lk-pick${i.id === _lk.sel ? ' is-sel' : ''}" data-id="${i.id}" aria-pressed="${i.id === _lk.sel}" onclick="_lkPick('${i.id}',true)">${_lkMini(i)}<b>${_profileEsc(i.name)}</b><small>${mark}${i.owned ? `тир ${i.level}` : i.buyable === false ? 'сезон закрыт' : _lkPrice(i.price_zarniki)}${i.id === week ? ' · образ недели' : ''}</small></button>`;
  }).join('')}</nav>`;
}
function _lkSteps(item) {
  const upto = _LK_TIERS.indexOf(item.ceiling), have = item.owned ? _LK_TIERS.indexOf(item.level) : -1, costs = _lk.st.essence.costs;
  return `<div class="lk-steps" role="radiogroup" aria-label="Тир скина">${_LK_TIERS.slice(0, upto + 1).map((t, n) => {
    const cls = ['lk-step', n <= have ? 'is-owned' : '', n === have + 1 ? 'is-next' : '', t === _lk.tier ? 'is-on' : ''].join(' ');
    return `<button type="button" role="radio" aria-checked="${t === _lk.tier}" class="${cls}" onclick="lkTier('${t}')"><span>${t}</span><small>${n === 0 ? 'старт' : n <= have ? '✓' : fmt(costs[t])}</small></button>`;
  }).join('<i class="lk-link"></i>')}</div>`;
}
function _lkTop(st) {
  return `<div class="lk-top"><button type="button" class="v3-link pp-back" onclick="navBack()" aria-label="Назад">‹ Профиль</button>
      <div class="lk-wallet" role="group" aria-label="Баланс"><button type="button" onclick="openZarnikiTopup()" aria-label="Зарники ${fmt(st.zarniki)}. Пополнить">✨ <b>${fmt(st.zarniki)}</b></button><button type="button" onclick="lkEssence()" aria-label="Эссенция ${fmt(st.essence.balance)}. Пополнить">${_v3Icon('essence')} <b>${fmt(st.essence.balance)}</b></button></div></div>${lkViewSwitch()}`;
}
function lkTop() { window.scrollTo({ top: 0, behavior: 'smooth' }); }

function _lkRender(anim, prepare=false) {
  const root = el('pg-looks'); if (!root) return;
  const st = _lk.st;
  if (!st) { root.innerHTML = `<div class="v3-scope lk-scope"><div class="v3-empty">${_profileEsc(_lk.failed || 'Загрузка…')} <button type="button" class="v3-link" onclick="openLooksModal()">Повторить</button></div></div>`; return; }
  const item = _lkItem(_lk.sel), look = { ...item, tier: _lk.tier }, ap = apFromLook(look), act = _lkAction(item, st);
  const tokens = v3TokenStyle(item.tokens);
  if (_lk.view === 'album') { root.innerHTML = `<div class="v3-scope lk-scope" style="${tokens}">${_lkTop(st)}${lkAlbumHtml(st)}</div>`; lkMainButton(); return; }
  const avatar = _v3Avatar(_profileData || {});
  const name = _profileEsc(String(_profileData?.display_name || 'Игрок'));
  const stripScroll = root.querySelector('.lk-strip')?.scrollLeft || 0;
  const identity = `<div class="lk-id"><div class="v3-ring lk-ring">${apHalo(ap)}${_v3Ring(72)}<div class="v3-ava">${avatar}</div>${apFrame(ap)}</div>
    <div class="v3-name lk-name">${apName(ap, name)}</div><div class="pp-title-row">${apTitle(ap)}</div></div>`;
  const setTag = item.set ? `<span class="lk-tag">${_profileEsc(st.sets.find(s => s.id === item.set)?.name || '')}</span>` : '';
  const seasonTag = item.season ? `<span class="lk-tag lk-tag--day">${item.season.open ? `Сезон · ещё ${_lkLeft(item.season.ends_at)}` : `Откроется через ${_lkLeft(item.season.starts_at)}`}</span>` : '';
  const dayTag = item.exclusive ? '<span class="lk-tag lk-tag--day">Личный образ</span>' : item.id === _lkWeekId(st) ? '<span class="lk-tag lk-tag--day">Образ недели</span>' : '';
  const note = !item.owned ? (_lk.tier === 'D' ? 'Так образ выглядит на старте.' : `Превью тира ${_lk.tier}. Куплен он начнёт с D и дорастёт до этого вида.`)
    : _lk.tier === item.level ? '' : _lk.tier === 'SSS' && !st.vip ? 'Превью тира SSS. Последний тир открывается только с активным VIP.' : `Превью тира ${_lk.tier}, сейчас у вас ${item.level}.`;
  const total = Math.ceil(item.total_upgrade_essence / st.essence.per_zarnik);
  const owner = st.vip ? '' : '<p class="lk-fine">Другие игроки видят ваш образ только пока у вас активен VIP. Вы сами видите его всегда. <button type="button" class="v3-link" onclick="openStoreV3(\'vip\')">Что даёт VIP ›</button></p>';
  const selectionHtml = `
    <div class="lk-hero${anim ? ' is-swap' : ''}">${apStage(ap, identity)}</div>
    <h1 class="lk-title">${_profileEsc(item.name)}</h1>
    <p class="lk-blurb">${_profileEsc(item.blurb)}</p>
    <div class="lk-tags"><span class="lk-tag lk-tag--tier">Тир ${_lk.tier}</span><span class="lk-tag">редкость ${item.rarity}</span>${setTag}${dayTag}${seasonTag}</div>
    ${_lkSteps(item)}
    <p class="lk-note" aria-live="polite">${_profileEsc(note)}</p>
    <div class="lk-cta">${act.a ? `<button type="button" class="v3-pill${_lk.busy ? ' is-busy' : ''}" ${_lk.busy ? 'disabled aria-busy="true"' : ''} onclick="lkAct('${act.a}')">${_profileEsc(act.t)}</button>` : `<div class="lk-done">${_profileEsc(act.t)}</div>`}<small>${_profileEsc(act.sub || '')}</small>
      ${item.equipped ? '<button type="button" class="v3-link" onclick="lkAct(\'unequip\')">Снять образ</button>' : ''}</div>
    <p class="lk-fine">Полная прокачка до ${item.ceiling}: ${fmt(item.total_upgrade_essence)} Эссенции, это около ${fmt(total)} ✨. Вместе со скином ${fmt(item.full_price_zarniki)} ✨. Эссенция тратится только на тиры образов.</p>${owner}`;
  const selection=root.querySelector('.lk-selection');
  if(anim && selection && root._lkRenderedState===st){
    root.querySelector('.lk-scope').style.cssText=tokens;
    selection.innerHTML=selectionHtml;
    root.querySelector('.lk-fit-note').innerHTML=lkFitNote(st,item);
    const fit=lkFitPack(st,item);
    root.querySelectorAll('.lk-packs button').forEach((button,index)=>button.classList.toggle('is-fit',st.essence.packs[index].zarniki===fit));
    root.querySelectorAll('.lk-pick').forEach(button=>{
      const selected=button.dataset.id===_lk.sel;
      button.classList.toggle('is-sel',selected); button.setAttribute('aria-pressed',String(selected));
    });
    lkMainButton();
    const strip=root.querySelector('.lk-strip');
    requestAnimationFrame(()=>{
      if(!strip?.isConnected || _activePage!=='looks')return;
      const on=strip.querySelector('.is-sel');
      if(on)strip.scrollTo({left:on.offsetLeft-strip.clientWidth/2+on.clientWidth/2,behavior:'smooth'});
    });
    return;
  }
  root.innerHTML = `<div class="v3-scope lk-scope" style="${tokens}">
    ${_lkTop(st)}<div class="lk-selection">${selectionHtml}</div>
    ${lkGoalHtml(st)}${lkWeekHtml(st)}${lkSoonHtml(st)}
    <div class="v3-sec"><span class="v3-eyebrow">Все образы</span></div>${_lkStrip(st)}
    <div class="v3-sec"><span class="v3-eyebrow">Сеты</span></div>${_lkSets(st)}
    <div class="v3-sec"><span class="v3-eyebrow">Эссенция</span><button type="button" class="v3-link" onclick="lkTour()">Как это работает</button></div>
    <p class="lk-fine">Валюта прокачки. Её дают задания (+${st.essence.quest_reward.daily} за день, +${st.essence.quest_reward.weekly} за неделю, +${st.essence.quest_reward.combined} за всё) или обмен: 1 ✨ = ${st.essence.per_zarnik} Эссенции.</p>
    <div class="lk-fit-note">${lkFitNote(st, item)}</div><div class="lk-packs">${st.essence.packs.map(p => `<button type="button" class="v3-pill v3-pill--ghost${p.zarniki === lkFitPack(st, item) ? ' is-fit' : ''}" onclick="lkAct('pack',${p.zarniki})" ${_lk.busy ? 'disabled' : ''}>${p.zarniki} ✨ → ${fmt(p.essence)}</button>`).join('')}</div></div>`;
  const strip = root.querySelector('.lk-strip');
  root._lkRenderedState=st;
  if(!prepare)lkMainButton();
  if(strip && !prepare)requestAnimationFrame(()=>{
    if(!strip.isConnected || _activePage!=='looks')return;
    strip.scrollLeft=stripScroll;
    if(!stripScroll||anim){const on=strip.querySelector('.is-sel');if(on)strip.scrollTo({left:on.offsetLeft-strip.clientWidth/2+on.clientWidth/2,behavior:stripScroll?'smooth':'auto'});}
  });
}

// ── Действия ─────────────────────────────────────────────────────────────────────
function _lkSync() {                           // новый скин сразу виден везде: палитра, профиль, кошелёк
  const st = _lk.st, worn = st.items.find(i => i.equipped), look = worn ? { ...worn, tier: worn.shown_tier } : null;
  if (_profileData) { _profileData.look = look; _profileData.zarniki = st.zarniki; _profileData.essence = st.essence.balance; v3SaveProfileCache(_profileData); renderV3Bar(_profileData); }
  if (typeof v3Morph === 'function' && document.body.dataset.skin !== (look?.id || '')) v3Morph(() => v3ApplyLook(look)); else v3ApplyLook(look);   // смена образа: палитра перетекает (app.31.js)
}
// Что показать в подтверждении: образ за Зарники, тир за Эссенцию, набор Эссенции за Зарники
function _lkConfirmSpec(kind, item, arg) {
  const st = _lk.st; if (!st) return null;
  if (kind === 'buy') return { title: 'Покупка образа', visual: _svAva(item), name: item.name, sub: `Начнёт с тира D и вырастет до ${item.ceiling} за Эссенцию`, price: item.price_zarniki, icon: '✨', have: st.zarniki, cta: `Купить за ${fmt(item.price_zarniki)} ✨`, note: 'Образ остаётся у вас навсегда.' };
  if (kind === 'upgrade') return { title: 'Улучшение тира', visual: _svAva(item), name: `${item.name}: тир ${item.next.tier}`, sub: `Сейчас тир ${item.level}`, price: item.next.essence, icon: '💧', have: st.essence.balance, cta: `Улучшить за ${fmt(item.next.essence)} 💧` };
  const per = Number(st.essence.per_zarnik) || 1;
  return { title: 'Набор Эссенции', visual: '💧', name: `${fmt(arg * per)} 💧 Эссенции`, sub: 'Растит образы по тирам', price: arg, icon: '✨', have: st.zarniki, cta: `Взять за ${fmt(arg)} ✨`, note: 'Курс один для всех наборов: больше берёте, но цена за единицу не меняется.' };
}
async function lkAct(kind, arg) {
  if (_lk.busy) return;
  const item = _lkItem(_lk.sel);
  if (kind === 'topup') return openStoreV3('zarniki', item?.id);
  if (kind === 'vip') return openStoreV3('vip');
  if (kind === 'essence') return lkEssence();
  const calls = {
    buy: () => api('/skins-v3/buy', { method: 'POST', headers: { 'Idempotency-Key': _lk.keys.buy ||= _lkUuid() }, body: JSON.stringify({ skin_id: item.id }) }),
    upgrade: () => api('/skins-v3/upgrade', { method: 'POST', headers: { 'Idempotency-Key': _lk.keys.upgrade ||= _lkUuid() }, body: JSON.stringify({ skin_id: item.id }) }),
    pack: () => api('/skins-v3/essence', { method: 'POST', headers: { 'Idempotency-Key': _lk.keys[`pack${arg}`] ||= _lkUuid() }, body: JSON.stringify({ zarniki: arg }) }),
    equip: () => api('/skins-v3/equip', { method: 'POST', body: JSON.stringify({ skin_id: item.id }) }).then(state => ({ state })),
    unequip: () => api('/skins-v3/equip', { method: 'POST', body: JSON.stringify({ skin_id: null }) }).then(state => ({ state })),
  };
  if (!calls[kind]) return;
  if (kind === 'buy' || kind === 'upgrade' || kind === 'pack') { const spec = _lkConfirmSpec(kind, item, arg); if (spec && !(await v3Confirm(spec))) return; }   // трата идёт только после второго нажатия
  _lk.busy = true; _lkRender();
  try {
    const reply = await calls[kind]();
    _lk.keys = {}; _lk.st = reply.state;
    const now = _lkItem(_lk.sel);
    if (kind === 'buy' || kind === 'upgrade' || kind === 'equip') _lk.tier = now.level;
    _lkSync();
    if (reply.message && kind !== 'buy' && kind !== 'upgrade') toast(reply.message);   // покупку и тир рассказывает раскрытие
    if (kind === 'buy' || kind === 'upgrade') lkReveal([...(kind === 'buy' ? [{ kind: 'owned', name: now.name, rarity: now.rarity, ceiling: now.ceiling }] : []), ...(reply.state.events || [])]);
    else if (kind === 'pack') v3Reward(el('pg-looks')?.querySelector('.lk-packs .v3-pill'));
    else _haptic('success');
  } catch (e) {
    if (/запрос уже использован|Idempotency/i.test(String(e))) _lk.keys = {};
    toast(e, false);
  } finally { _lk.busy = false; _lkRender(); }
}
function lkEssence() {                         // «пополнить Эссенцию»: показать наборы и подсветить их
  const packs = el('pg-looks')?.querySelector('.lk-packs'); if (!packs) return;
  packs.scrollIntoView({ behavior: 'smooth', block: 'center' });
  packs.classList.remove('is-hint'); void packs.offsetWidth; packs.classList.add('is-hint');
}
