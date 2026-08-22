// ── Бестиарий (бывш. Справка + Витрина) ───────────────────────────────────────
// Все виды по редкостям. Клик по виду → showSpeciesDetail (бонусы по уровням).
let _bestiaryFilter='all';
function renderZooGuide() {
  if(_showcaseData){_renderBestiary();return;}
  el('best-c').innerHTML='<div class="loader">Загрузка...</div>';
  api('/zoo/species').then(list=>{_showcaseData=list;_renderBestiary();})
    .catch(e=>{el('best-c').innerHTML=`<div class="err">${e}</div>`;});
}
function setBestiaryFilter(r){_bestiaryFilter=r;_renderBestiary();}
function _renderBestiary() {
  const ORDER = {common:0,uncommon:1,rare:2,epic:3,legendary:4,mythic:5};
  const RARITY_LABEL = {common:'⬜ Обычные',uncommon:'🟢 Необычные',rare:'🟦 Редкие',epic:'🟣 Эпические',legendary:'🟡 Легендарные',mythic:'🔴 Мифические'};
  const all=[...(_showcaseData||[])].sort((a,b)=>(ORDER[a.rarity]||0)-(ORDER[b.rarity]||0));
  const filters=['all',...Object.keys(ORDER).filter(r=>all.some(p=>p.rarity===r))];
  const list=_bestiaryFilter==='all'?all:all.filter(p=>p.rarity===_bestiaryFilter);
  const g={};list.forEach(s=>(g[s.rarity]=g[s.rarity]||[]).push(s));
  const filterRow=`<div class="tabs" style="margin-bottom:10px">
    ${filters.map(r=>`<button class="tb ${_bestiaryFilter===r?'active':''}" onclick="setBestiaryFilter('${r}')">${r==='all'?'Все':(RARITY_LABEL[r]||r).replace(/^.. /,'')}</button>`).join('')}
  </div>`;
  const body=Object.entries(g).map(([r,pets])=>`<div class="card">
      <div class="card-title">${RARITY_LABEL[r]||r} (${pets.length})</div>
      ${pets.map(p=>{
        const t1=bonusLines(p.species_id,(p.bonus_tiers||{})['1']||{});
        const t4=bonusLines(p.species_id,(p.bonus_tiers||{})['4']||{});
        const t10=bonusLines(p.species_id,(p.bonus_tiers||{})['10']||{});
        return `<div class="pcard" style="cursor:pointer;display:block" onclick="showSpeciesDetail('${p.species_id}')">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <div style="font-size:13px;font-weight:700;color:var(--bright);flex:1">${p.name}</div>
            <div style="font-size:10px;color:${p.role==='active'?'var(--teal)':'var(--blue)'}">${p.role==='active'?'⚔️ Активный':'🛡 Пассивный'}</div>
          </div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:7px;line-height:1.4">${p.desc}</div>
          <div style="font-size:10px">
            <span style="color:var(--muted)">Lv1: </span>${t1[0]||'—'}
            ${t4.length?`<span style="color:var(--muted)"> · Lv4: </span>${t4[0]||'—'}`:''}
            ${t10.length?`<span style="color:var(--muted)"> · Lv10: </span>${t10[t10.length-1]||'—'}`:''}
          </div>
        </div>`;
      }).join('')}
    </div>`).join('');
  el('best-c').innerHTML=filterRow+(body||`<div class="empty-state"><div class="es-icon">🔍</div><div class="es-title">Пусто</div><div class="es-sub">Нет видов этой редкости</div></div>`);
}
setInterval(()=>{if(_loaded.has('zoo'))api('/zoo/expeditions').then(d=>renderExps(d)).catch(()=>{});},30000);

// ── Arena ─────────────────────────────────────────────────────────────────────
// Боёвка 3.0: Казарма (юниты) + Врата (бои отрядом) + Рейды/Игры/Ивенты.
const _ARENA_TABS=['game','games','events'];
function openReconstructionGame(){ location.href=BASE+'/game'; }
function loadReconstructionHub(){
  const host=el('game-hub'); if(!host)return;
  host.innerHTML=`<section class="recon-entry-card">
    <div class="recon-entry-mark">◉</div>
    <div class="recon-entry-copy">
      <span class="recon-entry-kicker">НОВАЯ БОЕВАЯ СИСТЕМА</span>
      <h2>Разлом колокола</h2>
      <p>Три короткие волны. Найди правильную руну, удержи серию и собери усиления между волнами.</p>
      <div class="recon-entry-facts"><span>≈ 75 сек</span><span>3 волны</span><span>без спама</span></div>
    </div>
    <button class="btn btn-gold recon-entry-action" onclick="openReconstructionGame()">Начать забег <b>›</b></button>
  </section>`;
}
function loadArena(){
  const i=Math.max(0,_ARENA_TABS.indexOf(_arenaTab));
  swArena(_ARENA_TABS[i],document.querySelectorAll('#pg-arena .tb')[i]);
}
function swArena(tab,btn) {
  _arenaTab=tab;
  document.querySelectorAll('#pg-arena .tb').forEach(b=>b.classList.remove('active'));
  if(btn)btn.classList.add('active');
  _ARENA_TABS.forEach(t=>{const e=el('ar-'+t); if(e)e.style.display=t===tab?'':'none';});
  _trackSubtab('arena/'+tab);
  ({game:loadReconstructionHub,games:loadSkillGames,events:loadEvents}[tab]||loadReconstructionHub)();
}
const QUEST_NAMES = {
  msg_15:     {n:'💬 Болтун',         d:'Напиши 15 сообщений в чате'},
  msg_30:     {n:'💬 Оратор',         d:'Напиши 30 сообщений в чате'},
  feed_pet:   {n:'🍖 Забота о питомце',d:'Покорми питомца 1 раз'},
  gacha_3:    {n:'🎲 Удача в крутке', d:'Покрути гачу 3 раза'},
  exped_2:    {n:'🗺 Путешественник',  d:'Отправь питомца в 2 экспедиции'},
  exped_4:    {n:'🗺 Искатель приключений',d:'Отправь питомца в 4 экспедиции'},
  warp_3:     {n:'🌀 Варп-мастер',    d:'Отправь 3 варпа разным игрокам'},
  auction_bid:{n:'🏛 Аукционист',     d:'Поставь 1 ставку на аукционе'},
  gacha_10:   {n:'🎰 Одержимый гачей',d:'Покрути гачу 10 раз'},
  hug_5:      {n:'🤗 Душа компании',  d:'Обними 5 разных игроков'},
  rare_dup:   {n:'🌟 Редкий дубликат',d:'Получи дубликат редкого+ питомца'},
  level_pet:  {n:'⬆️ Тренер',         d:'Повысь питомца до нового уровня'},
  // Недельные (БЛОК 5)
  w_gourmet:    {n:'🥗 Гурман',                d:'Покорми питомцев 20 раз за неделю'},
  w_patron:     {n:'🤑 Безумный меценат',      d:'Покрути гачу 40 раз за неделю'},
  w_rescuer:    {n:'🚑 Спасатель пустошей',    d:'Заверши 15 экспедиций за неделю'},
  w_geneticist: {n:'🧬 Генетический эксперимент',d:'Открой 12 яиц за неделю'},
  w_cardinal:   {n:'⚖️ Серый Кардинал',        d:'Сделай 6 ставок на аукционе за неделю'},
};
const _QI_REWARD={'star_dust_s':'🌟 Звёздная пыль','star_dust_l':'✨ Небесная пыль',
                  'soul_shard':'💠 Осколок','spin_token':'🎟 Жетон Гачи'};
function _fmtQuestReward(rw){
  return [
    rw?.mora?`+${fmt(rw.mora)} 🪙`:'',
    rw?.diamonds?`+${rw.diamonds} 💎`:'',
    ...(rw?.items||[]).map(([id,n])=>`+${n>1?n+'× ':''}${_QI_REWARD[id]||id}`),
  ].filter(Boolean).join(' · ');
}
function _questSectionHtml(title, qs, bonus, bonusLabel) {
  if(!qs || !qs.length) return '';
  const doneCount = qs.filter(q=>q.completed).length;
  let bonusHtml = '';
  if(bonus){
    const rw = _fmtQuestReward(bonus.reward);
    const bpct = Math.round(doneCount/qs.length*100);
    const status = bonus.claimed ? '✅ Получено!' : `Закрой все: ${doneCount} / ${qs.length}`;
    bonusHtml = `<div class="card" style="border:1px solid ${bonus.claimed?'var(--green)':'var(--border)'};background:var(--gold-dim);margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
        <div style="font-size:13px;font-weight:700;color:var(--gold2)">🏆 ${bonusLabel||'Бонус за все задания'}</div>
        <div style="font-size:11px;color:var(--gold);white-space:nowrap">${rw}</div>
      </div>
      <div class="qbar" style="margin-top:6px"><div class="qfill" style="width:${bpct}%"></div></div>
      <div style="font-size:10px;color:var(--muted);margin-top:3px">${status}</div>
    </div>`;
  }
  const items = '<div class="card">'+qs.map(q=>{
    const pct=Math.min(100,Math.round((q.progress||0)/(q.target||1)*100));
    const qi=QUEST_NAMES[q.id]||{n:q.id,d:''};
    const rw=_fmtQuestReward(q.reward);
    return `<div class="qitem">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2px">
        <div style="font-size:13px;font-weight:600;color:var(--bright)">${q.completed?'✅':'🔲'} ${qi.n}</div>
        ${rw?`<div style="font-size:11px;color:var(--gold);white-space:nowrap;margin-left:8px">${rw}</div>`:''}
      </div>
      ${qi.d?`<div style="font-size:10px;color:var(--muted);margin-bottom:4px">${qi.d}</div>`:''}
      <div class="qbar"><div class="qfill" style="width:${pct}%"></div></div>
      <div style="font-size:10px;color:var(--muted);margin-top:2px">${Math.round(q.progress||0)} / ${q.target}</div>
    </div>`;
  }).join('')+'</div>';
  const header = title ? `<div class="card-title" style="margin:4px 2px 8px;font-size:14px">${title}</div>` : '';
  return header + bonusHtml + items;
}
function loadQuests() {
  el('qc').innerHTML='<div class="loader">Загрузка...</div>';
  if(!_cid){el('qc').innerHTML='<div style="color:var(--muted);font-size:12px;padding:10px">Нужен Профиль с чатом.</div>';return;}
  api(`/quests/${_cid}`).then(r=>{
    const qs = r.quests || r;     // backward-compat если вернётся массив
    const weekly = r.weekly || [];
    const retired = r.retired
      ? `<div class="card" style="margin-bottom:8px"><div class="card-title">📋 Архив заданий</div><div style="font-size:11px;color:var(--muted);line-height:1.5">${esc(r.message||'Старые задания закрыты.')}</div></div>`
      : '';
    if(!qs.length && !weekly.length){
      el('qc').innerHTML=retired||'<div class="empty-state"><div class="es-icon">📋</div><div class="es-title">Заданий нет</div></div>';
      return;
    }
    const shownQs = r.retired ? qs.map(q=>({...q,reward:{}})) : qs;
    const shownWeekly = r.retired ? weekly.map(q=>({...q,reward:{}})) : weekly;
    const daily = _questSectionHtml('📅 Ежедневные', shownQs, r.retired?null:r.bonus, 'Бонус за все дневные');
    const wk = shownWeekly.length ? _questSectionHtml('🗓 Недельные', shownWeekly, r.retired?null:r.weekly_bonus, 'Бонус за все недельные') : '';
    el('qc').innerHTML = retired + daily + (wk ? `<div style="height:8px"></div>${wk}` : '');
  }).catch(e=>{el('qc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
const SPIN_ICONS = {mora:'🪙',diamond:'💎'};
const SPIN_RARITY_ORDER = ['mythic','legendary','epic','rare','uncommon','common'];

function _topRarity(dups) {
  for(const r of SPIN_RARITY_ORDER) if(dups.some(d=>d.rarity===r)) return r;
  return '';
}

let _gachaBal = {mora:0, dia:0};
let _spinCosts = {};
// Ряды круток — вынесены, чтобы обновлять счётчик жетонов/цены/пити ПОСЛЕ крутки,
// не трогая экран результата (#spin-res). Раньше 🎟 ×N висел устаревшим до перезагрузки.
function _gachaBlocks(d){
  const disc = d.multi_discount_pct||10;
  return d.spin_types.map(s=>{
    const icon = SPIN_ICONS[s.spin_type] || '🎲';
    const cost = s.cost_mora ? `${fmt(s.cost_mora)} 🪙` : `${s.cost_dia} 💎`;
    const mc = d.multi_count||10;
    const tokensForMulti = Math.min(s.token_qty||0, mc);
    const paidSpins = mc - tokensForMulti;
    const multiCost = paidSpins<=0 ? '🎟 бесплатно'
      : (tokensForMulti>0 ? `🎟×${tokensForMulti} + ` : '')
        + (s.cost_mora ? `${fmt(Math.round(s.multi_cost_mora*paidSpins/mc))} 🪙` : `${(s.multi_cost_dia*paidSpins/mc).toFixed(1)} 💎`);
    const pityPct = s.pity_hard > 0 ? Math.round(s.pity/s.pity_hard*100) : 0;
    const rates = s.rates||{};
    const ratesBadges = Object.entries(rates).map(([r,v])=>
      `<span class="${RC[r]||'rc-common'}" style="font-size:9px;padding:1px 4px">${r[0].toUpperCase()+r.slice(1)} ${v}%</span>`
    ).join(' ');
    return `<div class="spin-block">
      <div class="spin-row" onclick="spinRowClick(event,'${s.spin_type}',this)"
           onpointerdown="spinPressStart(event,'${s.spin_type}',this)"
           onpointerup="spinPressEnd(event,this)"
           onpointercancel="spinPressEnd(event,this)"
           onpointerleave="spinPressEnd(event,this)">
        <div class="sr-charge"></div>
        <div class="sr-icon">${icon}</div>
        <div class="sr-info">
          <div class="sr-name">${s.label}</div>
          ${ratesBadges?`<div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:4px">${ratesBadges}</div>`:''}
        </div>
        ${s.token_qty?`<span style="font-size:11px;color:var(--green);margin-right:6px">🎟 ×${s.token_qty}</span>`:''}
        <div style="text-align:right"><div class="sr-cost">${cost}</div><div class="sr-hold-hint">⏱ удерживай</div></div>
      </div>
      <div style="display:flex;gap:6px;padding:0 4px 10px">
        <div style="flex:1;font-size:10px;color:var(--muted)">
          ${s.pity>0?`Пити: <span style="color:var(--gold)">${s.pity}/${s.pity_hard}</span>
          <div class="pity-bar"><div class="pity-fill" style="width:${pityPct}%"></div></div>`:'Гарант не накоплен'}
        </div>
        <button class="btn btn-sm btn-ghost" style="font-size:10px;white-space:nowrap" onclick="doMultiSpin('${s.spin_type}',this)">
          ×${d.multi_count||10} <span style="color:var(--green)">−${disc}%</span><br>
          <span style="color:var(--gold)">${multiCost}</span>
        </button>
      </div>
    </div>`;
  }).join('');
}
// Реактивно (после любой крутки/мутации, пока открыта гача): подтянуть свежие жетоны/
// цены/пити и баланс, НЕ затирая экран результата. Guard el('gacha-rows') — если гача
// не открыта, ничего не делаем и не ходим в сеть.
function _gachaSyncRows(){
  const box=el('gacha-rows'); if(!box) return;
  api('/gacha/').then(d=>{
    _gachaBal={mora:d.mora||0,dia:d.diamonds||0};
    _spinCosts={};
    d.spin_types.forEach(s=>{ _spinCosts[s.spin_type]={mora:s.cost_mora||0,dia:s.cost_dia||0,token:s.token_qty||0}; });
    const bm=el('gacha-bal-mora'); if(bm) bm.textContent='🪙 '+fmt(d.mora);
    const bd=el('gacha-bal-dia'); if(bd) bd.textContent='💎 '+(d.diamonds||0).toFixed(1);
    const b=el('gacha-rows'); if(b) b.innerHTML=_gachaBlocks(d);
  }).catch(()=>{});
}
onReactiveRefresh(_gachaSyncRows);   // регистрируем один раз (Set дедупит по ссылке)
function loadGacha() {
  el('gc').innerHTML='<div class="loader">Загрузка...</div>';
  api('/gacha/').then(d=>{
    const disc = d.multi_discount_pct||10;
    _gachaBal = {mora: d.mora||0, dia: d.diamonds||0};
    _spinCosts = {};
    d.spin_types.forEach(s=>{ _spinCosts[s.spin_type] = {mora: s.cost_mora||0, dia: s.cost_dia||0, token: s.token_qty||0}; });
    el('gc').innerHTML=`
    <div class="gacha-header">
      <div class="gh-title">✨ ГАЧА</div>
      <div class="gh-sub">Крути Гачу, получай питомцев и ресурсы</div>
    </div>
    <div class="gacha-balance">
      <span class="gb-item" id="gacha-bal-mora">🪙 ${fmt(d.mora)}</span>
      <span style="color:var(--border2)">│</span>
      <span class="gb-item" id="gacha-bal-dia">💎 ${(d.diamonds||0).toFixed(1)}</span>
    </div>
    ${d.spin_types.every(s=>!s.token_qty&&((s.cost_mora&&d.mora<s.cost_mora)||(s.cost_dia&&(d.diamonds||0)<s.cost_dia)))
      ? `<div class="cx-dim" style="font-size:11px;padding:8px 10px;background:var(--dim);border-radius:var(--r);margin-bottom:10px">
          На крутку пока не хватает — общайся в чате и выполняй <span class="shortcut-link" onclick="goTo('quests')">📋 Задания</span>, там первая Мора.
        </div>` : ''}
    <div class="card">
      <div class="card-title" style="margin-bottom:10px;display:flex;justify-content:space-between;align-items:center">
        <span>Выберите крутку</span>
        <button class="btn btn-sm btn-ghost" style="padding:2px 8px;font-size:10px" onclick="openGachaOdds()">ℹ️ Шансы</button>
      </div>
      <div id="gacha-rows">${_gachaBlocks(d)}</div>
    </div>
    <div id="spin-res"></div>`;
  }).catch(e=>{el('gc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}

// ── ℹ️ Честные шансы гачи (полная таблица дропа с процентами) ─────────────────
function openGachaOdds() {
  OM('🎲 Шансы выпадения','<div style="text-align:center;padding:16px;color:var(--muted)">Загрузка…</div>',
     [{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
  api('/gacha/odds').then(r=>{
    const tables=r.tables||{};
    let html='';
    Object.keys(tables).forEach(st=>{
      const t=tables[st];
      html+=`<div class="card-title" style="margin:8px 0 4px;font-size:13px">${SPIN_ICONS[st]||'🎲'} ${esc(t.label)}</div>`;
      html+=(t.entries||[]).map(e=>`<div class="irow">
        <span class="ik" style="${e.valuable?'color:var(--gold2);font-weight:600':''}">${esc(e.label)}</span>
        <span class="iv" style="font-variant-numeric:tabular-nums">${e.pct}%</span>
      </div>`).join('');
    });
    el('mb').innerHTML=`<div style="font-size:10px;color:var(--muted);margin-bottom:8px">Честные шансы за одну крутку. Дубликаты повышают уровень питомца; гарант (пити) усиливает шанс редкого с каждой пустой круткой.</div>${html}`;
  }).catch(e=>{el('mb').innerHTML=`<div class="err">${e}</div>`;});
}

// ── R4.1 Ритуал Крутки: long-press с нарастающей вибрацией ────────────────────
// Удержание ~0.9с заряжает крутку (слой .sr-charge, хаптик light→medium→heavy),
// на 100% спин запускается сам. Ранний отпуск/скролл (pointercancel) — сброс.
// Фолбэк: в вебвью без PointerEvent работает обычный клик (spinRowClick).
function _haptic(kind){
  try{
    const h = tg && tg.HapticFeedback;
    if(!h) return;
    if(kind==='success'||kind==='error'||kind==='warning') h.notificationOccurred(kind);
    else h.impactOccurred(kind);
  }catch(e){}
}
const SPIN_HOLD_MS = 900;
let _press = null;   // {row, st, t0, timer, fired}
function spinPressStart(ev, st, row){
  if(!window.PointerEvent) return;              // фолбэк-клик отработает сам
  if(_press) spinPressEnd(ev, _press.row);      // защитный сброс зависшего состояния
  if(row.style.pointerEvents==='none') return;  // спин уже в полёте
  // UX-аудит: не начинать ритуал заряда, если крутка заведомо не по карману —
  // раньше игрок проходил всю анимацию и узнавал о нехватке денег в конце.
  // БАГФИКС 2026-07-14: жетон (бесплатный спин) списывается ПЕРВЫМ и ПРИОРИТЕТНО
  // (services/gacha.py::roll_single) — эта проверка баланса игнорировала token_qty
  // и блокировала жест ещё до вызова API, даже когда жетон реально есть и валюта
  // не нужна вовсе. Игрок с жетоном, но без денег, не мог покрутить.
  const c = _spinCosts[st];
  if(c && !c.token && ((c.mora>0 && _gachaBal.mora<c.mora) || (c.dia>0 && _gachaBal.dia<c.dia))){
    _haptic('error');
    toast(c.mora>0?`Не хватает Моры (нужно ${fmt(c.mora)} 🪙)`:`Не хватает Алмазов (нужно ${c.dia} 💎)`, false);
    return;
  }
  // UX_AUDIT С23: упрощённый ввод — крутка обычным тапом, без ритуала удержания
  if(typeof _easyInput==='function' && _easyInput()){
    _haptic('medium');
    doSpin(st, row);
    return;
  }
  _press = {row, st, t0: Date.now(), fired: false, h1: false, h2: false};
  row.classList.add('charging');
  _haptic('light');
  _press.timer = setInterval(()=>{
    if(!_press) return;
    const p = Math.min(1, (Date.now() - _press.t0) / SPIN_HOLD_MS);
    _press.row.style.setProperty('--chg', p.toFixed(3));
    if(p >= 0.4 && !_press.h1){ _press.h1 = true; _haptic('medium'); }
    if(p >= 0.75 && !_press.h2){ _press.h2 = true; _haptic('heavy'); }
    if(p >= 1 && !_press.fired){
      _press.fired = true;
      const {row: r, st: s} = _press;
      _pressReset();
      r.classList.add('charged');
      setTimeout(()=>r.classList.remove('charged'), 700);
      _haptic('success');
      doSpin(s, r);
    }
  }, 50);
}
function _pressReset(){
  if(!_press) return;
  clearInterval(_press.timer);
  _press.row.classList.remove('charging');
  _press.row.style.setProperty('--chg', 0);
  _press = null;
}
function spinPressEnd(ev, row){
  // Отпустил раньше 100% (или палец ушёл в скролл) — просто сброс зарядки
  if(_press && !_press.fired) _pressReset();
}
function spinRowClick(ev, st, row){
  if(window.PointerEvent) return;  // long-press уже обработал (или сбросил) жест
  doSpin(st, row);
}

// doSpin — preserves result; no loadGacha() call
let _lastSpinType = null;
function spinAgain() {
  if (!_lastSpinType) { loadGacha(); return; }
  // Find the matching spin-row in the current gacha page and trigger it
  const rows = document.querySelectorAll('.spin-row');
  for (const r of rows) {
    const oc = r.getAttribute('onclick') || '';
    if (oc.includes(_lastSpinType)) { doSpin(_lastSpinType, r); return; }
  }
  loadGacha(); // fallback: row not found, reload
}

function doSpin(st, row) {
  _lastSpinType = st;
  row.style.opacity='.4'; row.style.pointerEvents='none';
  el('spin-res').innerHTML='';
  api('/gacha/spin',{method:'POST',body:JSON.stringify({spin_type:st,chat_id:_cid||0})}).then(r=>{
    const dups = r.dup_outcomes||[];
    const topRarity = _topRarity(dups);
    const glowCls = topRarity ? 'glow-'+topRarity : '';

    // Determine display emoji for animation ball
    const ballEmoji = dups.length ? (PET_SPECIES_EMOJI[dups[0].species_id]||'🐾') : (r.mora ? '🪙' : '💎');

    // Build result cards
    const cards=[];
    if(r.mora) cards.push({text:`🪙 ${fmt(r.mora)} Мора`, cls:'', icon:'🪙'});
    if(r.diamonds) cards.push({text:`💎 ${r.diamonds} Алмазов`, cls:'', icon:'💎'});
    (r.items||[]).forEach(i=>cards.push({text:`${i.name}${i.qty>1?' ×'+i.qty:''}`, cls:'', icon:'📦'}));
    dups.forEach(d=>cards.push({
      text:`🐾 ${d.species_name||d.species_id||''} ${rc(d.rarity||'common')} ${d.outcome==='first_copy_created'?'🆕 Новый!':d.new_level?'→ Lv'+d.new_level:''}`,
      cls:d.rarity||'', icon:'🐾'
    }));

    el('spin-res').innerHTML=`
      <div class="spin-anim-wrap ${glowCls}">
        <div class="spin-anim-ball">${ballEmoji}</div>
        <div style="font-size:11px;color:var(--gold2);margin-top:8px;font-weight:700">
          ${topRarity?('⚡ '+topRarity.toUpperCase()):'Результат'}
        </div>
      </div>
      <div class="spin-results">
        ${cards.map((c,i)=>`<div class="spin-card ${c.cls}" style="animation-delay:${(i*0.08+3.1).toFixed(2)}s">${c.text}</div>`).join('')}
      </div>
      ${_petActionsHtml(dups)}
      <div style="display:flex;gap:8px;margin-top:10px">
        <button class="btn btn-gold" style="flex:2" onclick="spinAgain()">🔄 Крутить ещё</button>
        <button class="btn btn-ghost" style="flex:1" onclick="closeSpinResult()">↩ Выбрать</button>
      </div>`;

    _spinJuice(topRarity);
    // Update balance displays
    refreshCurrBar();
    const balEl=el('gacha-bal-mora');
    if(balEl) api('/profile/me').then(d=>{ if(d.mora!==undefined) balEl.textContent='🪙 '+fmt(d.mora); }).catch(()=>{});
    row.style.opacity='1'; row.style.pointerEvents='';
  }).catch(e=>{toast(e,false); row.style.opacity='1'; row.style.pointerEvents='';});
}
// Minimal species→emoji map (expand as needed)
const PET_SPECIES_EMOJI={hamster:'🐹',owl:'🦉',dog:'🐕',turtle:'🐢',falcon:'🦅',wolf:'🐺',fox:'🦊',dragon:'🐉',unicorn:'🦄'};
function closeSpinResult(){const s=el('spin-res');if(s)s.innerHTML='';loadGacha();}

// Screen-shake на топ-дропах (epic и выше) — «восторг» от редкой крутки (БЛОК 3).
function _spinJuice(topRarity) {
  if(!['epic','legendary','mythic','shadow'].includes(topRarity)) return;
  const box = el('spin-res');
  if(!box) return;
  box.classList.remove('shake-fx');
  void box.offsetWidth;        // форсим reflow → анимация перезапускается каждый раз
  box.classList.add('shake-fx');
}

// Retention CTA после крутки (БЛОК 3): выпал питомец — окно не тупик, а действие.
// 1 питомец → прямая экипировка; несколько → переход в питомник.
function _petActionsHtml(dups) {
  const pets = (dups||[]).filter(d=>d.pet_id && d.outcome!=='overflow');
  if(!pets.length) return '';
  if(pets.length===1){
    const p = pets[0];
    return `<div id="spin-pet-cta" style="display:flex;gap:6px;margin-top:10px">
      <button class="btn btn-teal btn-sm" style="flex:1" onclick="equipFromSpin(${p.pet_id},'active',this)">⚔️ В активные</button>
      <button class="btn btn-green btn-sm" style="flex:1" onclick="equipFromSpin(${p.pet_id},'passive',this)">🛡 В пассивные</button>
    </div>`;
  }
  return `<button class="btn btn-ghost btn-sm btn-full" style="margin-top:10px" onclick="goTo('zoo')">🐾 Пристроить питомцев в питомнике</button>`;
}
function equipFromSpin(petId, placement, btn) {
  btn.disabled = true;
  api('/zoo/move',{method:'POST',body:JSON.stringify({pet_id:petId,placement})})
    .then(()=>{
      toast(placement==='active'?'⚔️ Питомец в активном слоте!':'🛡 Питомец в пассивном слоте!');
      const row = el('spin-pet-cta');
      if(row) row.innerHTML = `<div style="flex:1;text-align:center;font-size:11px;color:var(--green);padding:6px">✅ Пристроен · <span style="cursor:pointer;text-decoration:underline;color:var(--gold2)" onclick="goTo('zoo')">в питомник ›</span></div>`;
    })
    .catch(e=>{ toast(e,false); btn.disabled=false; });  // напр. слоты заняты — игрок видит причину
}

// ── R4.1: мультикрутка ×10 → скретч-карты (стирание пальцем) ──────────────────
// Каждая из 10 круток — закрытая «серебряная» карта; редкие отсортированы в
// конец (эскалация напряжения). Итог и CTA-кнопки питомцев — после полного
// раскрытия (или по кнопке «Открыть все»).
const _RAR_RANK = {common:0, uncommon:1, rare:2, epic:3, legendary:4, mythic:5, shadow:5};
let _scr = null;   // {opened, total, dups, topRarity, tailHtml}
function doMultiSpin(st, btn) {
  btn.disabled=true;
  el('spin-res').innerHTML=`<div class="spin-anim-wrap"><div class="spin-anim-ball" style="animation-duration:2s">🎲</div><div style="font-size:12px;color:var(--gold2);margin-top:8px">×10 крутка...</div></div>`;
  api('/gacha/multi-spin',{method:'POST',body:JSON.stringify({spin_type:st,chat_id:_cid||0})}).then(r=>{
    const s=r.summary||{};
    const results=r.results||[];
    const dups=s.dup_outcomes||[];
    const topRarity=_topRarity(dups);
    if(!results.length){ // страховка на неожиданный формат — старый плоский вывод
      el('spin-res').innerHTML=`<div class="spin-results"><div class="spin-card">🪙 ${fmt(s.mora||0)} · 💎 ${s.diamonds||0}</div></div>`;
      btn.disabled=false; return;
    }
    // Одна крутка → одна карта: текст + топ-редкость этой крутки
    const cards = results.map(res=>{
      const lines=[];
      if(res.mora) lines.push(`🪙 ${fmt(res.mora)}`);
      if(res.diamonds) lines.push(`💎 ${res.diamonds}`);
      (res.items||[]).forEach(i=>lines.push(`📦 ${i.name}${(i.qty||1)>1?' ×'+i.qty:''}`));
      (res.dup_outcomes||[]).forEach(d=>lines.push(
        `🐾 ${d.species_name||d.species_id||''} ${rc(d.rarity||'common')}${d.outcome==='first_copy_created'?' 🆕':d.new_level?' → Lv'+d.new_level:''}`));
      const rar=_topRarity(res.dup_outcomes||[])||'';
      return {html: lines.join('<br>')||'—', rarity: rar};
    });
    cards.sort((a,b)=>(_RAR_RANK[a.rarity]||0)-(_RAR_RANK[b.rarity]||0));  // редкие в конец

    // Хвост (итог + CTA) — прячется до полного раскрытия
    const themeCard = s.theme_drop?`<div class="spin-card epic" style="margin-top:8px">🎨 Новая тема: <b>${esc(s.theme_drop.name||'')}</b></div>`:'';
    const tailHtml = `
      <div class="spin-results" style="margin-top:10px">
        <div class="spin-card ${topRarity||''}">Итого: 🪙 ${fmt(s.mora||0)}${s.diamonds?` · 💎 ${s.diamonds}`:''} · 🐾 ×${dups.length}${s.tokens_used?` · 🎟 бесплатно: ${s.tokens_used}/${results.length}`:''}</div>
        ${themeCard}
      </div>
      ${_petActionsHtml(dups)}`;

    _scr = {opened:0, total:cards.length, topRarity, tailHtml};
    el('spin-res').innerHTML=`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px">
        <div style="font-size:12px;font-weight:700;color:var(--gold2)">🃏 ×${cards.length} — сотри карты пальцем</div>
        <button class="btn btn-sm btn-ghost" style="font-size:10px" onclick="scrRevealAll()">⚡ Открыть все</button>
      </div>
      <div class="scr-grid" id="scr-grid">
        ${cards.map((c,i)=>`<div class="scr-card ${c.rarity?'r-'+c.rarity:''}" data-rar="${c.rarity}">
          <div class="scr-body">${c.html}</div>
          <canvas class="scr-canvas"></canvas>
        </div>`).join('')}
      </div>
      <div id="scr-tail"></div>
      <div style="display:flex;gap:8px;margin-top:10px">
        <button class="btn btn-gold" style="flex:2" onclick="loadGacha()">🔄 Крутить ещё</button>
        <button class="btn btn-ghost" style="flex:1" onclick="closeSpinResult()">↩ Назад</button>
      </div>`;
    document.querySelectorAll('#scr-grid .scr-canvas').forEach(cv=>_scrInitCanvas(cv));
    refreshCurrBar();
    btn.disabled=false;
  }).catch(e=>{toast(e,false);btn.disabled=false;el('spin-res').innerHTML='';});
}
// Серебряное покрытие + стирание. Стёртость меряем сеткой 8×5 «затронутых» клеток
// (getImageData на каждый move слишком дорог для слабых телефонов).
function _scrInitCanvas(cv){
  const card=cv.parentElement, r=card.getBoundingClientRect();
  cv.width=Math.max(2, Math.round(r.width)); cv.height=Math.max(2, Math.round(r.height));
  const ctx=cv.getContext('2d');
  const g=ctx.createLinearGradient(0,0,cv.width,cv.height);
  g.addColorStop(0,'#3a4150'); g.addColorStop(.5,'#535d70'); g.addColorStop(1,'#3a4150');
  ctx.fillStyle=g; ctx.fillRect(0,0,cv.width,cv.height);
  ctx.fillStyle='rgba(232,181,77,.75)'; ctx.font='11px sans-serif'; ctx.textAlign='center';
  ctx.fillText('✦ сотри ✦', cv.width/2, cv.height/2+4);
  const GX=8, GY=5, hit=new Set();
  let down=false;
  const erase=(ev)=>{
    const b=cv.getBoundingClientRect();
    const x=ev.clientX-b.left, y=ev.clientY-b.top;
    ctx.globalCompositeOperation='destination-out';
    ctx.beginPath(); ctx.arc(x,y,18,0,Math.PI*2); ctx.fill();
    hit.add(Math.min(GX-1,Math.max(0,Math.floor(x/b.width*GX)))+'_'+Math.min(GY-1,Math.max(0,Math.floor(y/b.height*GY))));
    if(hit.size >= GX*GY*0.55) _scrReveal(card);
  };
  cv.onpointerdown=(ev)=>{down=true; try{cv.setPointerCapture(ev.pointerId);}catch(e){} erase(ev);};
  cv.onpointermove=(ev)=>{if(down) erase(ev);};
  cv.onpointerup=cv.onpointercancel=()=>{down=false;};
  // Фолбэк для вебвью без PointerEvent: тап раскрывает карту сразу
  if(!window.PointerEvent) cv.onclick=()=>_scrReveal(card);
}
function _scrReveal(card){
  if(!card || card.classList.contains('scr-open')) return;
  card.classList.add('scr-open');
  const rar=card.getAttribute('data-rar')||'';
  _haptic(['epic','legendary','mythic','shadow'].includes(rar)?'success':(rar==='rare'?'medium':'light'));
  if(_scr){
    _scr.opened++;
    if(_scr.opened>=_scr.total){
      const tail=el('scr-tail');
      if(tail && _scr.tailHtml){ tail.innerHTML=_scr.tailHtml; }
      _spinJuice(_scr.topRarity);
      _scr.tailHtml=null;
    }
  }
}
function scrRevealAll(){
  document.querySelectorAll('#scr-grid .scr-card:not(.scr-open)').forEach(c=>_scrReveal(c));
}
function loadCraft() {
  el('cc').innerHTML='<div class="loader">Загрузка...</div>';
  api('/craft/').then(recipes => {
    if (!recipes.length) { el('cc').innerHTML='<div class="empty-state"><div class="es-icon">⚗️</div><div class="es-title">Рецептов пока нет</div><div class="es-sub">Рецепты крафта появятся в следующих обновлениях</div></div>'; return; }
    el('cc').innerHTML = recipes.map(rc => `
      <div class="card card-gold">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <div style="font-size:15px;font-weight:700;color:var(--bright)">${rc.name}</div>
          ${rc.can_craft_times>1?`<span style="font-size:11px;color:var(--green);background:rgba(86,196,106,.14);border:1px solid rgba(86,196,106,.3);padding:2px 8px;border-radius:999px">×${rc.can_craft_times} возможно</span>`:''}
        </div>
        ${rc.what_is?`<div style="font-size:12px;color:var(--text);line-height:1.5;margin-bottom:10px">${rc.what_is}</div>`:''}
        ${rc.how_use?`<div class="irow"><span class="ik">Как использовать</span><span style="color:var(--teal);font-size:11px">${rc.how_use}</span></div>`:''}
        ${rc.gacha_rates?`<div class="irow"><span class="ik">Шансы при открытии</span><span style="font-size:11px">${rc.gacha_rates}</span></div>`:''}
        ${rc.special_note?`<div style="background:rgba(239,99,99,.1);border:1px solid rgba(239,99,99,.25);border-radius:var(--r);padding:8px 10px;font-size:11px;color:var(--red);margin:8px 0">${rc.special_note}</div>`:''}
        <div class="divider"></div>
        <div class="card-title">Нужно для крафта</div>
        ${rc.ingredients_status.map(i=>`
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <span style="font-size:18px">${i.have>=i.needed?'✅':'❌'}</span>
            <div style="flex:1">
              <div style="font-size:12px;font-weight:600">${itemLink(i.item_id, i.item_name)}</div>
              <div style="font-size:10px;color:var(--muted)">${i.have} из ${i.needed} в инвентаре</div>
            </div>
            <div style="font-size:14px;font-weight:700;color:${i.have>=i.needed?'var(--green)':'var(--red)'}">${i.have}/${i.needed}</div>
          </div>`).join('')}
        ${rc.ingredient_tip?`<div style="font-size:11px;color:var(--muted);margin-top:6px;padding:8px;background:var(--s);border-radius:var(--r)">💡 ${rc.ingredient_tip}</div>`:''}
        <button class="btn btn-full ${rc.can_craft?'btn-gold':'btn-ghost'}" style="margin-top:12px"
                ${rc.can_craft?'':'disabled'} onclick="doCraft('${rc.recipe_id}',this)">
          ${rc.can_craft?`⚗️ Скрафтить ${rc.name}`:'🔒 Недостаточно ингредиентов'}
        </button>
      </div>`).join('');
  }).catch(e => { el('cc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`; });
}
function doCraft(recipeId, btn) {
  btn.disabled = true;
  api(`/craft/${recipeId}`, {method:'POST'})
    .then(r => { toast(`✅ Скрафтено: ${r.name}!`); loadCraft(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}
function loadDuels() {
  el('dc').innerHTML='<div class="loader">Загрузка...</div>';
  Promise.all([api('/duels/active'), api('/duels/history')]).then(([active, hist]) => {
    let html = '';

    html += `<div class="card" style="margin-bottom:10px">
      <div class="card-title">⚔️ Старые дуэли закрыты</div>
      <div style="font-size:11px;color:var(--muted);line-height:1.5">Новые бои проходят во вкладке «Игра». Здесь можно освободить Мору из незавершённого старого вызова и посмотреть историю.</div>
    </div>`;

    // Incoming challenges
    const incoming = active.filter(d => d.challenged_id == _uid);
    if(incoming.length) {
      html += `<div class="card"><div class="card-title">⏳ Входящие вызовы (${incoming.length})</div>
        ${incoming.map(d=>`<div class="duel-card">
          <div class="duel-vs">${vipName(d.challenger_name||'Игрок', d.challenger_is_vip)} · старый вызов</div>
          <div class="duel-stake">Зарезервировано: ${fmt(d.stake)} 🪙</div>
          <button class="btn btn-sm btn-ghost" style="margin-top:8px" onclick="declineDuel(${d.id},this)">Освободить ставку</button>
        </div>`).join('')}
      </div>`;
    }

    // Outgoing pending
    const outgoing = active.filter(d => d.challenger_id == _uid);
    if(outgoing.length) {
      html += `<div class="card"><div class="card-title">📤 Мои вызовы</div>
        ${outgoing.map(d=>`<div class="duel-card">
          <div class="duel-vs">→ ${vipName(d.challenged_name||'Игрок', d.challenged_is_vip)}</div>
          <div class="duel-stake">Зарезервировано: ${fmt(d.stake)} 🪙</div>
          <button class="btn btn-sm btn-ghost" style="margin-top:8px" onclick="declineDuel(${d.id},this)">Освободить ставку</button>
        </div>`).join('')}
      </div>`;
    }

    // History
    if(hist.length) {
      html += `<div class="card"><div class="card-title">📜 История (последние 20)</div>
        ${hist.map(d => {
          const won = d.winner_id == _uid;
          const isDone = d.status === 'finished';
          const vs = d.challenger_id == _uid ? d.challenged_name : d.challenger_name;
          const vsIsVip = d.challenger_id == _uid ? d.challenged_is_vip : d.challenger_is_vip;
          const statusMap = {pending:'⏳ Ожидание', timeout:'⏰ Истёк', declined:'❌ Отклонён', finished:''};
          const amountStr = isDone
            ? (won ? ` (+${fmt(Math.round(d.winner_gain||0))} 🪙)` : ` (−${fmt(d.stake)} 🪙)`)
            : '';
          return `<div class="duel-card">
            <div style="display:flex;align-items:center;justify-content:space-between">
              <div class="duel-vs">vs ${vipName(vs||'Игрок', vsIsVip)}</div>
              <div class="duel-result${isDone?(won?' win':' lose'):''}">
                ${isDone?(won?'✓ Победа':'✗ Поражение'):statusMap[d.status]||d.status}${amountStr}
              </div>
            </div>
            <div class="duel-stake">${fmt(d.stake)} 🪙</div>
          </div>`;
        }).join('')}
      </div>`;
    }

    if(!html) html = `<div style="text-align:center;padding:32px 16px;color:var(--muted)">
      <div style="font-size:32px;margin-bottom:8px">⚔️</div>
      <div style="font-size:13px;font-weight:600;margin-bottom:4px">Дуэлей пока нет</div>
      <div style="font-size:11px">Нажми «Вызвать игрока» и бросить кому-нибудь вызов!</div>
    </div>`;
    el('dc').innerHTML = html;
  }).catch(e => { el('dc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`; });
}

function acceptDuel(id, opponentName, btn) {
  btn.disabled = true;
  btn.textContent = '...';
  api('/duels/accept', {method:'POST', body:JSON.stringify({duel_id:id})})
    .then(r => {
      const res = r.result || {};
      const won = r.winner_id == _uid;
      _haptic(won ? 'success' : 'error');
      const myPower = (res.challenged_id == _uid) ? res.challenged_power : res.challenger_power;
      const oppPower = (res.challenged_id == _uid) ? res.challenger_power : res.challenged_power;
      const powerLine = (typeof myPower==='number' && typeof oppPower==='number')
        ? `<div style="font-size:11px;color:var(--muted);margin-top:6px">Твоя сила: <b>${myPower.toFixed(1)}</b> · ${esc(opponentName)}: <b>${oppPower.toFixed(1)}</b></div>` : '';
      const moneyLine = won
        ? `<div style="font-size:14px;color:var(--green);font-weight:700;margin-top:4px">+${fmt(Math.round(res.winner_gain||0))} 🪙 (комиссия ${fmt(Math.round(res.commission||0))} 🪙)</div>`
        : (r.winner_id ? `<div style="font-size:14px;color:var(--red);font-weight:700;margin-top:4px">−${fmt(res.stake||0)} 🪙</div>` : '');
      OM(won?'🏆 Победа!':(r.winner_id?'😔 Поражение':'🤝 Ничья'), `
        <div style="text-align:center;padding:6px 0">
          <div style="font-size:36px">${won?'🏆':(r.winner_id?'💥':'🤝')}</div>
          ${moneyLine}
          ${powerLine}
          <div style="font-size:10px;color:var(--muted);margin-top:6px">Оба питомца получили +15 усталости</div>
        </div>`, [{l:'Закрыть', c:'btn-gold', f:'CM();loadDuels()'}]);
      refreshCurrBar();
    })
    .catch(e => { toast(e, false); btn.disabled = false; btn.textContent = '⚔️ Принять'; });
}

function declineDuel(id, btn) {
  btn.disabled = true;
  api('/duels/decline', {method:'POST', body:JSON.stringify({duel_id:id})})
    .then(r => { toast(r.message||'Старая ставка освобождена.'); loadDuels(); refreshCurrBar(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

function openDuelChallenge() {
  if(!_cid) { toast('Нужен Профиль с чатом для вызова.', false); return; }
  // Grab current balance from profile data if available
  const bal = _profileData?.mora || 0;
  const balStr = bal > 0 ? `<div style="background:var(--s);border-radius:var(--r);padding:6px 10px;margin-bottom:10px;font-size:11px;display:flex;justify-content:space-between"><span style="color:var(--muted)">Ваш баланс</span><span style="color:var(--gold);font-weight:600">${fmt(bal)} 🪙</span></div>` : '';
  // UX-аудит: механика решалки была «чёрным ящиком» — игрок не видел даже
  // своего питомца перед ставкой. Показываем, кто идёт в бой, и честно
  // объясняем правило (редкость×уровень±15% случайности), без опоры на
  // питомца соперника — тот неизвестен, пока он не примет вызов.
  const myPet = (_profileData?.pets||[]).find(p=>p.placement==='active');
  const petStr = myPet
    ? `<div style="font-size:11px;color:var(--muted);margin-bottom:8px">🐾 В бой пойдёт: <b style="color:var(--bright)">${esc(myPet.name||myPet.species_id)}</b> · ${rarLabel(myPet.rarity)} · Ур.${myPet.pet_level}</div>`
    : `<div style="font-size:11px;color:var(--red);margin-bottom:8px">⚠️ Нет активного питомца — назначьте его в Зоопарке перед вызовом.</div>`;
  OM('⚔️ Вызов на дуэль', `
    ${balStr}
    ${petStr}
    <div style="font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.5">
      Соперник получит уведомление в Telegram — он должен ответить <code>бот принять</code> в чате.
      Побеждает более сильный питомец (редкость × уровень), но исход не гарантирован — есть ±15% случайности.
    </div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">@username соперника</div>
    <input id="duel-user" type="text" class="num-input" placeholder="username (без @)"/>
    <div style="font-size:11px;color:var(--muted);margin:8px 0 4px">Ставка 🪙 (200 – 15 000)</div>
    <input id="duel-stake" type="number" class="num-input" placeholder="500" min="200" max="15000" oninput="_duelUpdateEstimate()"/>
    <div style="font-size:10px;color:var(--gold);margin-top:6px;background:var(--gold-dim);padding:6px 8px;border-radius:var(--r)">
      🔒 Ставка заморозится до конца дуэли. Победитель получает обе ставки минус 5% комиссии:
      <span id="duel-est">победитель получит ≈475 🪙 чистыми при ставке 500 🪙 с каждого</span>.
      Оба питомца получат +15 усталости, независимо от исхода.
    </div>
  `, [
    {l:'⚔️ Вызвать', c:'btn-red', f:'submitDuelChallenge(this)'},
    {l:'Отмена', c:'btn-ghost', f:'CM()'},
  ]);
}
function _duelUpdateEstimate(){
  const stake = parseFloat(el('duel-stake')?.value || 0) || 500;
  const net = Math.round(stake*2*0.95 - stake);
  const est = el('duel-est');
  if(est) est.textContent = `победитель получит ≈${fmt(net)} 🪙 чистыми при ставке ${fmt(stake)} 🪙 с каждого`;
}

function submitDuelChallenge(btn) {
  const username = el('duel-user')?.value?.trim().replace('@','');
  const stake = parseFloat(el('duel-stake')?.value||0);
  if(!username) { toast('Введите @username.', false); return; }
  if(!stake || stake < 200) { toast('Мин. ставка 200 🪙.', false); return; }
  const myBal = _profileData?.mora || 0;
  if(myBal > 0 && stake > myBal) { toast(`Недостаточно Моры. У тебя ${fmt(myBal)} 🪙.`, false); return; }
  btn.disabled = true;
  api('/duels/challenge', {method:'POST', body:JSON.stringify({username, stake, chat_id:_cid})})
    .then(() => {
      el('mb').innerHTML=`<div style="text-align:center;padding:20px">
        <div style="font-size:36px;margin-bottom:8px">⚔️</div>
        <div style="font-size:14px;font-weight:700;margin-bottom:6px">Вызов отправлен!</div>
        <div style="font-size:11px;color:var(--muted)">@${username} получит уведомление в Telegram.<br>Ставка <b>${fmt(stake)} 🪙</b> заморожена до конца дуэли.</div>
      </div>`;
      el('mf').innerHTML=`<button class="btn btn-ghost btn-sm" onclick="CM();loadDuels()">Закрыть</button>`;
    })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

// ── Market ────────────────────────────────────────────────────────────────────
function loadMarket(){swMkt(_mktTab,document.querySelector(`#pg-market > .tabs > .tb[onclick*="'${_mktTab}'"]`)||document.querySelector('#pg-market > .tabs > .tb'));}
// swMkt() defined later with deal + promo tabs
let _aucPage = 0, _aucTotal = 0, _aucPerPage = 48, _aucMinBidFloor = 1;

function loadAuction(page) {
  if(page !== undefined) _aucPage = page;
  api(`/auction/lots?page=${_aucPage}&per_page=${_aucPerPage}`).then(data=>{
    _allLots = data.lots || data;  // backward compat
    _aucTotal = data.total || _allLots.length;
    _aucMinBidFloor = data.min_bid_floor || 1;
    const totalPages = Math.ceil(_aucTotal / _aucPerPage);

    el('mkt-auc').innerHTML=`
      <div class="auc-bar">
        <input type="text" class="num-input auc-search" placeholder="🔍 Поиск по названию..." value="${_aucSearch?esc(_aucSearch):''}" oninput="filterAuction(this.value)"/>
        <button class="btn btn-gold btn-sm" onclick="openCreateLotModal()">+ Выставить</button>
      </div>
      <div class="auc-bar auc-bar2">
        <select class="num-input auc-sel" onchange="setAucFilter('sort',this.value)">
          ${_aucOpt('sort',[['ending','⏱ Скоро конец'],['new','🆕 Новые'],['cheap','⬇️ Дешевле'],['expensive','⬆️ Дороже']])}
        </select>
        <select class="num-input auc-sel" onchange="setAucFilter('rarity',this.value)">
          ${_aucOpt('rarity',[['','✦ Все редкости'],['common','Обычные'],['rare','Редкие'],['epic','Эпические'],['legendary','Легендарные'],['mythic','Мифические']])}
        </select>
        <select class="num-input auc-sel" onchange="setAucFilter('cat',this.value)">
          ${_aucOpt('cat',[['','📦 Все типы'],['food','🍖 Еда'],['booster','⚡ Бустеры'],['material','💠 Материалы'],['utility','🏡 Утилиты'],['theme','🎨 Темы'],['pet','🐾 Питомцы'],['other','📦 Прочее']])}
        </select>
      </div>
      <!-- Reserved mora -->
      <div id="auc-reserve" style="margin-bottom:8px"></div>
      <!-- My active lots (with cancel) -->
      <div id="auc-mylots" style="margin-bottom:8px"></div>
      <div id="lot-list"></div>
      <!-- Pagination -->
      ${totalPages > 1 ? `<div style="display:flex;gap:6px;justify-content:center;margin-top:10px">
        ${_aucPage > 0 ? `<button class="btn btn-ghost btn-sm" onclick="loadAuction(${_aucPage-1})">← Пред.</button>` : ''}
        <span style="font-size:11px;color:var(--muted);padding:6px">${_aucPage+1} / ${totalPages} (${_aucTotal} лотов)</span>
        ${data.has_more ? `<button class="btn btn-ghost btn-sm" onclick="loadAuction(${_aucPage+1})">След. →</button>` : ''}
      </div>` : `<div style="font-size:10px;color:var(--muted);text-align:center;margin-top:6px">${_aucTotal} лотов</div>`}`;

    _applyAucFilters();
    loadAucReserve();
    loadMyLots();
  }).catch(e=>{el('mkt-auc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;_allLots=[];});
}

// Мои активные лоты + снятие с торгов (web-паритет с ботом).
function loadMyLots() {
  if(!_uid && !sess()) return;
  api('/auction/my-lots').then(lots=>{
    const div = el('auc-mylots'); if(!div) return;
    const active = (lots||[]).filter(l=>l.status==='active');
    if(!active.length){ div.innerHTML=''; return; }
    const rows = active.map(l=>{
      const name = (l.item_name||'Лот').split('||')[0].trim();
      const ends = new Date((l.ends_at+'').includes('T')?l.ends_at:l.ends_at+'Z');
      const diff = Math.max(0,Math.floor((ends-Date.now())/1000));
      const tl = diff>3600?Math.floor(diff/3600)+'ч':Math.floor(diff/60)+'м';
      const bidTxt = (l.current_bid>0)?`${fmt(l.current_bid)} 🪙`:'нет ставок';
      return `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border2)">
        <div style="flex:1;min-width:0">
          <span style="font-size:11px;color:var(--bright)">${esc(name)}</span>
          <span style="font-size:10px;color:var(--muted)"> · ⏳${tl} · ${bidTxt}</span>
        </div>
        <button class="btn btn-red btn-sm" style="padding:2px 9px;font-size:10px;white-space:nowrap" onclick="cancelMyLot(${l.id})">Снять</button>
      </div>`;
    }).join('');
    div.innerHTML=`<div style="background:var(--s);border:1px solid var(--border2);border-radius:var(--r);padding:8px 10px">
      <div style="font-size:11px;font-weight:600;color:var(--gold2);margin-bottom:4px">📋 Мои лоты (${active.length})</div>
      ${rows}
    </div>`;
  }).catch(()=>{});
}
function cancelMyLot(lotId) {
  OM('Снять лот с торгов?',
    '<div style="font-size:12px;color:var(--muted);line-height:1.5">Лот закроется, предмет вернётся тебе, а Мора из активной ставки снова станет доступна участнику.</div>',
    [{l:'Отмена', c:'btn-ghost', f:'CM()'},
     {l:'🗑 Снять', c:'btn-red', f:`_doCancelLot(${lotId})`}]);
}
function _doCancelLot(lotId) {
  CM();
  api('/auction/cancel',{method:'POST',body:JSON.stringify({lot_id:lotId})})
    .then(()=>{toast('✅ Лот снят с торгов');loadAuction();})
    .catch(e=>toast(e,false));
}

function loadAucReserve() {
  if(!_uid && !sess()) return;
  api('/auction/reserved').then(r=>{
    const div = el('auc-reserve'); if(!div) return;
    if(!r.reserved_total || !r.bids?.length) { div.innerHTML=''; return; }
    const bidsHtml = r.bids.map(b=>{
      const ends = new Date((b.ends_at+'').includes('T')?b.ends_at:b.ends_at+'Z');
      const diff = Math.max(0,Math.floor((ends-Date.now())/1000));
      const tl = diff>3600?Math.floor(diff/3600)+'ч':Math.floor(diff/60)+'м';
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid var(--border2)">
        <div>
          <span style="font-size:11px;color:var(--bright)">${b.item_name||'Лот #'+b.lot_id}</span>
          <span style="font-size:10px;color:var(--muted)"> · ⏳${tl}</span>
        </div>
        <span style="font-size:11px;color:var(--gold);font-weight:600">${fmt(b.amount)} 🪙</span>
      </div>`;
    }).join('');
    div.innerHTML=`<div style="background:var(--gold-dim);border:1px solid var(--border);border-radius:var(--r);padding:8px 10px;font-size:11px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-weight:600;color:var(--gold2)">🔒 Зарезервировано: ${fmt(r.reserved_total)} 🪙</span>
        <span style="font-size:10px;color:var(--muted)">${r.bids.length} ставок</span>
      </div>
      ${bidsHtml}
    </div>`;
  }).catch(()=>{});
}
// ── Create lot modal ─────────────────────────────────────────────────────────
let _invForAuction = [];
function openCreateLotModal() {
  // Always reload fresh inventory
  OM('🏛 Выставить лот', '<div class="loader">Загрузка инвентаря...</div>', []);
  // Load inventory AND pets for listing
  Promise.all([api('/inventory/'), api('/zoo/')]).then(([items, zooData])=>{
    _invData = items;
    // ALL items with quantity > 0 (server validates tradability)
    const tradable = items.filter(it => it.quantity > 0);
    const pets = (zooData.pets||[]).filter(p=>p.placement === 'storage');

    if(!tradable.length && !pets.length) {
      el('mb').innerHTML = `<div style="text-align:center;padding:20px">
        <div style="font-size:32px;margin-bottom:8px">📦</div>
        <div style="font-size:13px;font-weight:600;margin-bottom:6px">Нечего выставить</div>
        <div style="font-size:11px;color:var(--muted)">Купите предметы в Магазине или получите питомцев в Гача.</div>
      </div>`;
      el('mf').innerHTML = `
        <button class="btn btn-ghost btn-sm" onclick="CM()">Закрыть</button>
        <button class="btn btn-gold btn-sm" onclick="goTo('market','goods')">🛒 В Магазин</button>`;
      return;
    }
    _invForAuction = tradable;
    el('mt').textContent = '🏛 Что выставить?';
    let html = `<div style="background:rgba(224,82,82,.08);border:1px solid rgba(224,82,82,.3);border-radius:var(--r);padding:8px 10px;margin-bottom:10px;font-size:10px;color:var(--red)">
      ⚠️ Проверь предмет перед выставлением. Передумаешь — лот можно снять в «📋 Мои лоты», ставки вернутся участникам.
    </div>`;

    if(tradable.length) {
      html += `<div class="card-title" style="margin-bottom:6px">📦 Предметы из инвентаря</div>`;
      html += tradable.map(it=>`
        <div class="fopt" onclick="selectLotItem('${it.item_id}','${(it.name||it.item_id).replace(/'/g,"\\'")}',${it.quantity},'','${(it.description||'').replace(/'/g,"\\'")}')">
          <div style="flex:1">
            <div class="fn">${it.name||it.item_id}</div>
            ${it.description?`<div style="font-size:10px;color:var(--muted);margin-top:1px">${it.description}</div>`:''}
          </div>
          <span class="fq" style="margin-left:8px">×${it.quantity}</span>
        </div>`).join('');
    }

    if(pets.length) {
      html += `<div class="card-title" style="margin-top:12px;margin-bottom:6px">🐾 Питомцы со склада</div>`;
      html += pets.map(pt=>`
        <div class="fopt" onclick="selectLotPet(${pt.id},'${(pt.name||pt.species_id||'Питомец').replace(/'/g,"\\'")}','${pt.rarity||'common'}',${pt.pet_level||1})">
          <div style="flex:1">
            <div class="fn">${pt.name||pt.species_id} ${rc(pt.rarity)}</div>
            <div style="font-size:10px;color:var(--muted)">Lv${pt.pet_level||1} · 🏬 Склад</div>
          </div>
          <span style="font-size:10px;color:var(--gold)">Выставить ›</span>
        </div>`).join('');
    } else {
      html += `<div style="font-size:10px;color:var(--muted);margin-top:10px">
        🐾 Чтобы выставить питомца — перенеси его в склад питомника (из активных слотов).
      </div>`;
    }
    el('mb').innerHTML = html;
    el('mf').innerHTML = `<button class="btn btn-ghost btn-sm" onclick="CM()">Отмена</button>`;
  }).catch(e=>{el('mb').innerHTML=`<div class="err">${e}</div>`;});
}
function selectLotItem(itemId, itemName, maxQty, _unused, itemDesc) {
  el('mt').textContent = `🏛 Выставить лот`;
  const floor = _aucMinBidFloor;
  el('mb').innerHTML = `
    <div style="background:var(--s);border-radius:var(--r);padding:10px;margin-bottom:12px">
      <div style="font-size:13px;font-weight:700;color:var(--bright);margin-bottom:4px">${itemName}</div>
      ${itemDesc?`<div style="font-size:11px;color:var(--muted);line-height:1.4">${itemDesc}</div>`:''}
      <div style="font-size:10px;color:var(--muted);margin-top:4px">В наличии: ×${maxQty}</div>
    </div>
    <div class="divider"></div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Количество (1–${maxQty})</div>
    <input id="lot-qty" type="number" class="num-input" min="1" max="${maxQty}" value="1"/>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Минимальная ставка 🪙</div>
    <input id="lot-bid" type="number" class="num-input" min="${floor}" value="500" placeholder="Мин. ставка (от ${floor} 🪙)"/>
    <div style="font-size:11px;color:var(--muted);margin:8px 0 4px">Цена выкупа 🪙 <span style="color:var(--muted)">(необязательно)</span></div>
    <input id="lot-buyout" type="number" class="num-input" placeholder="Оставь пустым если без выкупа"/>
    <div style="font-size:10px;color:var(--muted);margin-top:8px;padding:6px 8px;background:var(--s);border-radius:var(--r)">
      ⏳ Лот активен 24 часа. Передумал — сними его в «📋 Мои лоты» (ставки вернутся участникам).
    </div>
  `;
  el('mf').innerHTML = `
    <button class="btn btn-ghost btn-sm" onclick="openCreateLotModal()">← Назад</button>
    <button class="btn btn-gold btn-sm" onclick="submitLot('${itemId}')">✅ Выставить</button>
  `;
}
function submitLot(itemId) {
  const qty = parseInt(el('lot-qty')?.value||1);
  const minBid = parseFloat(el('lot-bid')?.value||0);
  const buyout = parseFloat(el('lot-buyout')?.value||0)||null;
  if(!minBid||minBid<_aucMinBidFloor){toast(`Мин. ставка от ${_aucMinBidFloor} 🪙`,false);return;}
  const btn = document.querySelector('#mf .btn-gold');
  if(btn) btn.disabled=true;
  const sig=`${itemId}:${qty}:${minBid}:${buyout??''}`;
  if(btn && btn.dataset.requestSig!==sig){btn.dataset.requestSig=sig;btn.dataset.requestKey=economyRequestKey('auction-listing');}
  const requestKey=btn?.dataset.requestKey||economyRequestKey('auction-listing');
  api('/auction/create',{method:'POST',headers:{'Idempotency-Key':requestKey},body:JSON.stringify({item_id:itemId,quantity:qty,min_bid:minBid,buyout})})
    .then(r=>{toast(`✅ Лот #${r.lot_id} создан! (24ч)`);CM();loadAuction();refreshCurrBar();})
    .catch(e=>{toast(e,false);if(btn)btn.disabled=false;});
}
// Питомец → лот (web-паритет с ботом). Эскроу на бэкенде: питомец уходит из
// склада в placement='auction' и вернётся, если лот не продастся/отменён.
function selectLotPet(petId, petName, rarity, level) {
  el('mt').textContent = '🏛 Выставить питомца';
  el('mb').innerHTML = `
    <div style="background:var(--s);border-radius:var(--r);padding:10px;margin-bottom:12px">
      <div style="font-size:13px;font-weight:700;color:var(--bright);margin-bottom:4px">🐾 ${petName} ${rc(rarity)}</div>
      <div style="font-size:11px;color:var(--muted)">Уровень ${level} · со склада питомника</div>
    </div>
    <div style="background:rgba(224,82,82,.08);border:1px solid rgba(224,82,82,.3);border-radius:var(--r);padding:8px 10px;margin-bottom:10px;font-size:10px;color:var(--red)">
      ⚠️ На время аукциона питомец уйдёт в эскроу — пользоваться им нельзя. Вернётся, если лот не продастся или ты его отменишь.
    </div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Минимальная ставка 🪙</div>
    <input id="lot-bid" type="number" class="num-input" min="${_aucMinBidFloor}" value="1000" placeholder="Мин. ставка (от ${_aucMinBidFloor} 🪙)"/>
    <div style="font-size:11px;color:var(--muted);margin:8px 0 4px">Цена выкупа 🪙 <span style="color:var(--muted)">(необязательно)</span></div>
    <input id="lot-buyout" type="number" class="num-input" placeholder="Оставь пустым если без выкупа"/>
    <div style="font-size:10px;color:var(--muted);margin-top:8px;padding:6px 8px;background:var(--s);border-radius:var(--r)">
      ⏳ Лот активен 24 часа.
    </div>`;
  el('mf').innerHTML = `
    <button class="btn btn-ghost btn-sm" onclick="openCreateLotModal()">← Назад</button>
    <button class="btn btn-gold btn-sm" onclick="submitPetLot(${petId})">✅ Выставить</button>`;
}
function submitPetLot(petId) {
  const minBid = parseFloat(el('lot-bid')?.value||0);
  const buyout = parseFloat(el('lot-buyout')?.value||0)||null;
  if(!minBid||minBid<_aucMinBidFloor){toast(`Мин. ставка от ${_aucMinBidFloor} 🪙`,false);return;}
  const btn = document.querySelector('#mf .btn-gold');
  if(btn) btn.disabled=true;
  const sig=`${petId}:${minBid}:${buyout??''}`;
  if(btn && btn.dataset.requestSig!==sig){btn.dataset.requestSig=sig;btn.dataset.requestKey=economyRequestKey('auction-pet-listing');}
  const requestKey=btn?.dataset.requestKey||economyRequestKey('auction-pet-listing');
  api('/auction/create-pet',{method:'POST',headers:{'Idempotency-Key':requestKey},body:JSON.stringify({pet_id:petId,min_bid:minBid,buyout})})
    .then(r=>{toast(`✅ Питомец выставлен! Лот #${r.lot_id} (24ч)`);CM();loadAuction();})
    .catch(e=>{toast(e,false);if(btn)btn.disabled=false;});
}

// openBidModal(lotId, name, currentBid, minNextBid, hasBids, buyout, remSec)
// minNextBid comes from server (min_bid if no bids, ceil(cur*1.05) if bids exist)
// R5: при remSec ≤ 600 модалка входит в live-режим «🔥 Финал» — WS-комната лота
// (тикающий таймер с анти-снайп-продлениями, лента ставок, зрители, жаба 🐸).
function openBidModal(lotId, name, currentBid, minNextBid, hasBids, buyout, remSec) {
  const firstBid = !hasBids;
  const minLabel = firstBid
    ? `Первая ставка — не менее <b>${fmt(minNextBid)} 🪙</b>`
    : `Мин. для обгона — <b>${fmt(minNextBid)} 🪙</b> (текущая × 1.05)`;
  const buyoutBtn = buyout
    ? `<button class="btn btn-teal btn-full" style="margin-top:8px"
             onclick="doBid(${lotId},this,${buyout})">⚡ Выкупить за ${fmt(buyout)} 🪙</button>`
    : '';
  const isFinal = typeof remSec==='number' && remSec>0 && remSec<=600;
  const liveHtml = isFinal ? `
    <div class="lot-live" id="lot-live">
      <div class="lot-live-fly" id="lot-live-fly"></div>
      <div class="lot-live-head">
        <span>🔥 ФИНАЛ · <span id="lot-live-timer">--:--</span></span>
        <span style="display:flex;align-items:center;gap:8px">
          <span id="lot-live-viewers">👁 1</span>
          <button class="btn btn-sm btn-ghost" style="padding:2px 10px;font-size:14px" onclick="lotLiveReact()">🐸</button>
        </span>
      </div>
      <div id="lot-live-feed" class="lot-live-feed"><div class="set-hint">Ставка в последние 60с продлевает лот на +60с. Кто сдастся первым?</div></div>
    </div>` : '';
  OM(`💰 Ставка: ${name}`, `
    <div class="irow"><span class="ik">Текущая ставка</span><span id="lot-live-cur" style="color:var(--gold);font-weight:700">${fmt(currentBid)} 🪙</span></div>
    <div style="font-size:11px;color:var(--muted);margin:8px 0">${minLabel}</div>
    ${liveHtml}
    <div class="divider"></div>
    <input id="bid-val" class="num-input" type="number"
           value="${minNextBid}" min="${minNextBid}" step="1"
           placeholder="Ваша ставка 🪙"/>
    <div style="font-size:10px;color:var(--muted);margin-top:6px">
      Мора будет зарезервирована до завершения аукциона.
    </div>
    ${buyoutBtn}
  `, [{l:'💰 Поставить ставку', c:'btn-gold', f:`doBid(${lotId},this,0)`}, {l:'Отмена', c:'btn-ghost', f:'CM()'}]);
  if(isFinal) lotLiveJoin(lotId, remSec);
}
function doBid(lotId, btn, fixedAmount) {
  const v = fixedAmount > 0 ? fixedAmount : parseFloat(el('bid-val')?.value || 0);
  if (!v || v <= 0) { toast('Введите сумму.', false); return; }
  btn.disabled = true;
  const sig=`${lotId}:${v}`;
  if(btn.dataset.requestSig!==sig){btn.dataset.requestSig=sig;btn.dataset.requestKey=economyRequestKey('auction-bid');}
  const requestKey=btn.dataset.requestKey;
  api('/auction/bid', {method:'POST', headers:{'Idempotency-Key':requestKey}, body:JSON.stringify({lot_id:lotId, amount:v})})
    .then(r => { toast(r.is_buyout ? `🎉 Выкуплено за ${fmt(r.amount)} 🪙!` : `✅ Ставка ${fmt(r.amount)} 🪙 принята!`); CM(); loadAuction(); refreshCurrBar(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

function loadShopCatalog() {
  // Always fetch inventory fresh so "в инвентаре" badges reflect purchases/promos
  Promise.all([
    api('/inventory/').then(items=>{_invData=items;}).catch(()=>{}),
    api('/shop/'),
  ]).then(([,d])=>{
    el('balrow').style.display='flex';
    el('balrow').innerHTML=`<div class="bal"><div class="bv">🪙 ${fmt(d.mora)}</div><div class="bl">Мора</div></div>
      <div class="bal"><div class="bv">💎 ${d.diamonds.toFixed(1)}</div><div class="bl">Алмазы</div></div>`;
    const cats={food:'🥩 Еда',utility:'🛠 Утилиты',booster:'⚗️ Зелья',donate:'✨ Донат'};
    const grps={};d.items.forEach(it=>(grps[it.category]=grps[it.category]||[]).push(it));
    const promoBtn=`<button class="btn btn-ghost btn-full" style="margin-bottom:10px" onclick="openPromoModal()">🎫 У меня есть промокод</button>`;
    el('mkt-shop').innerHTML=promoBtn+Object.entries(grps).map(([cat,list])=>
      `<div class="card"><div class="card-title">${cats[cat]||cat}</div>${list.map(it=>{
        const priceIcon = it.price_mora?'🪙':it.price_diamonds?'💎':'✨';
        const priceVal = it.price_mora?it.price_mora:it.price_diamonds?it.price_diamonds:it.price_zarniki;
        const haveVal = it.price_mora?d.mora:it.price_diamonds?d.diamonds:(d.zarniki||0);
        const afford = haveVal >= priceVal;
        return `<div class="shop-row">
        <span style="font-size:22px;width:32px;text-align:center">${it.name.split(' ')[0]}</span>
        <div style="flex:1">
          <div style="font-size:13px;font-weight:600;color:var(--bright)">${it.name}</div>
          <div style="font-size:11px;color:var(--gold)">${fmt(priceVal)} ${priceIcon}${it.discount_active?' 🐢':''}</div>
          <div style="font-size:10px;color:var(--muted)">${it.description||''}</div>
          ${_invData.find(i=>i.item_id===it.item_id)
            ? `<div style="font-size:10px;color:var(--green);margin-top:2px">✓ В инвентаре: ×${_invData.find(i=>i.item_id===it.item_id).quantity}</div>`
            : ''}
        </div>
        <button class="btn btn-sm ${afford?'btn-gold':'btn-ghost'}" onclick="buyItem('${it.item_id}',this,'${cat}')">${afford?`Купить за ${fmt(priceVal)} ${priceIcon}`:`Нужно ${fmt(priceVal)} ${priceIcon}`}</button>
      </div>`;}).join('')}</div>`).join('');
  }).catch(e=>{el('mkt-shop').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
// Block 9: warn before buying if already in inventory.
// UX_AUDIT С19: еда и зелья — расходники, докупаются часто; для них повторный
// confirm «уже в инвентаре» только мешает. Предупреждаем лишь про остальное.
function buyItem(id, btn, cat) {
  const existing = _invData.find(i => i.item_id === id);
  if (existing && cat !== 'food' && cat !== 'booster') {
    OM('⚠️ Уже в инвентаре', `
      <div style="text-align:center;padding:10px 0 14px">
        <div style="font-size:24px;margin-bottom:8px">⚠️</div>
        <div style="font-size:13px;font-weight:600;color:var(--bright);margin-bottom:6px">У вас уже есть этот предмет</div>
        <div style="font-size:12px;color:var(--muted)">В инвентаре: <b style="color:var(--gold)">×${existing.quantity}</b></div>
        <div style="font-size:11px;color:var(--muted);margin-top:8px">Купить ещё?</div>
      </div>
    `, [
      {l:'✅ Да, купить ещё', c:'btn-gold', f:`doBuyConfirmed('${id}')`},
      {l:'Отмена', c:'btn-ghost', f:'CM()'},
    ]);
    return;
  }
  _execBuy(id, btn);
}
function doBuyConfirmed(id) { CM(); _shopBuy(id, 1, null); }
function _execBuy(id, btn) { _shopBuy(id, 1, btn); }
const _shopRequestKeys=new Map();
function _shopBuy(id, qty, btn) {
  if(btn) btn.disabled = true;
  const slot=`${id}:${qty}`;
  const requestKey=_shopRequestKeys.get(slot)||economyRequestKey(`shop-${id}`);
  _shopRequestKeys.set(slot,requestKey);
  api('/shop/buy', {method:'POST', headers:{'Idempotency-Key':requestKey}, body:JSON.stringify({item_id:id, quantity:qty})})
    .then(r => { _shopRequestKeys.delete(slot); toast('✅ ' + (r.message || ('Куплено: ' + r.item_name))); loadShopCatalog(); refreshCurrBar(); if(btn) btn.disabled=false; })
    .catch(e => {
      if(btn) btn.disabled=false;
      toast(e, false);
    });
}
// Русские названия категорий для бейджа инвентаря (магазин локализует свои отдельно).
const CAT_RU={food:'Корм',material:'Материал',booster:'Зелье',utility:'Утилита',spin_token:'Жетон',chest:'Сундук',donate:'Донат'};
function loadInventory() {
  el('mkt-inv').innerHTML='<div class="loader">Загрузка...</div>';
  api('/inventory/').then(items=>{
    _invData=items;
    _invSearch='';
    _renderInventory();
  }).catch(e=>{el('mkt-inv').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function filterInv(q){_invSearch=q;_renderInventory();}
function _renderInventory() {
  const items=_invSearch?_invData.filter(i=>(i.name||'').toLowerCase().includes(_invSearch.toLowerCase())):_invData;
  const grid=items.length
    ?'<div class="inv-grid">'+items.map(it=>`<div class="icard" onclick="openItemModal('${it.item_id}')">
        <div class="icat">${CAT_RU[it.category]||it.category}</div>
        <div class="iname">${it.name}</div>
        <div class="iqty">×${it.quantity}</div>
        <div class="idesc">${it.description||''}</div>
      </div>`).join('')+'</div>'
    :_invData.length
      ?`<div class="empty-state"><div class="es-icon">🔍</div><div class="es-title">Ничего не найдено</div><div class="es-sub">По запросу «${_invSearch}»</div></div>`
      :`<div class="empty-state"><div class="es-icon">🎒</div><div class="es-title">Инвентарь пуст</div><div class="es-sub">Купите предметы в Магазине или получите через Гачу</div></div>`;
  el('mkt-inv').innerHTML=`<div style="position:relative;margin-bottom:8px">
    <span style="position:absolute;left:10px;top:50%;transform:translateY(-50%);font-size:13px;pointer-events:none;z-index:1">🔍</span>
    <input type="text" class="num-input" style="margin:0;padding-left:32px" placeholder="Поиск в инвентаре..." value="${_invSearch.replace(/"/g,'&quot;')}" oninput="filterInv(this.value)"/>
  </div>${grid}`;
}
function openItemModal(iid) {
  const it=_invData.find(i=>i.item_id===iid);if(!it)return;
  const {item_id,name,quantity,category,description,spin_type,boost_hours,fatigue_restore,dup_count}=it;
  let body=`<div class="irow"><span class="ik">В инвентаре</span><span>×${quantity}</span></div>`;
  if(description)body+=`<div style="font-size:11px;color:var(--muted);margin-top:7px;line-height:1.4">${description}</div>`;
  body+='<div class="divider"></div>';
  const btns=[{l:'Закрыть',c:'btn-ghost',f:'CM()'}];
  if(category==='food'&&fatigue_restore){
    body+=`<div class="irow"><span class="ik">Восстанавливает</span><span style="color:var(--green)">−${fatigue_restore} уст.</span></div>`;
    if(quantity>0)btns.unshift({l:'🍖 Покормить питомца',c:'btn-gold',f:`openFeedSelModal('${item_id}')`});
  } else if(boost_hours){
    body+=`<div class="irow"><span class="ik">Ускорение</span><span style="color:var(--teal)">−${boost_hours}ч</span></div>`;
    if(quantity>0)btns.unshift({l:'⏩ К экспедиции',c:'btn-teal',f:`openBoostSelModal('${item_id}')`});
  } else if(category==='spin_token'){
    if(quantity>0)btns.unshift({l:'🎲 В Гачу',c:'btn-gold',f:`goTo('market','gacha')`});
  } else if(category==='chest'){
    if(quantity>0)btns.unshift({l:'🎁 Открыть',c:'btn-gold',f:`CM();_openSurprisesModal()`});
  } else if(item_id.startsWith('star_dust')){
    body+=`<div class="irow"><span class="ik">Даёт дубликатов</span><span style="color:var(--gold)">+${dup_count||1}</span></div>`;
    if(quantity>0)btns.unshift({l:'✨ Применить',c:'btn-gold',f:`openDustModal('${item_id}')`});
  } else if(item_id==='study_notes'){
    body+=`<div class="irow"><span class="ik">Статус</span><span>Архивный · не расходуется</span></div>`;
  }
  OM(name,body,btns);
}
function useConsumable(iid) {
  api('/inventory/use',{method:'POST',body:JSON.stringify({item_id:iid})})
    .then(r=>{toast(r.message||'✅ Применено!');CM();loadInventory();if(_loaded.has('profile'))loadActiveBuffs();})
    .catch(e=>toast(e,false));
}

// ══ R7: Интеллектуальные мини-игры — «Теневой Сапёр» и «Взлом сейфа» ══════════
// Server-authoritative: раскладка мин/секрет сейфа живут только на бэке
// (/games2/*), клиент рисует и шлёт действия. Хаптика — через _haptic (app.04).
let _skg=null;          // кэш /games2/state
let _safeInput=[];      // текущий ввод кода сейфа
function loadSkillGames(){
  el('skg').innerHTML='<div class="loader">Загрузка...</div>';
  api('/games2/state').then(d=>{
    _skg=d;
    if(d.sapper){ _skgRenderSapper(d.sapper); return; }
    if(d.safe){ _safeInput=[]; _skgRenderSafe(d.safe); return; }
    if(d.alchemy){ _alchResume(d.alchemy); return; }
    _skgRenderLobby();
  }).catch(e=>{el('skg').innerHTML=`<div class="err">${e}</div>`;});
}
function _skgRenderLobby(){
  const d=_skg, cd=d.cooldown_left_sec||0;
  const cdHtml=cd>0?`<div class="skg-cd">⏳ Кулдаун: ${Math.floor(cd/60)}м ${String(cd%60).padStart(2,'0')}с до следующей игры</div>`:'';
  const lim=d.limits||{sapper:[100,2000],safe:[100,2000],alchemy:[100,2000]};
  el('skg').innerHTML=`
    ${cdHtml}
    <div class="card">
      <div class="card-title">💣 Теневой Сапёр</div>
      <div class="skg-desc">Поле 5×5, три мины. Каждая безопасная клетка растит множитель —
      забрать выигрыш можно в любой момент. Наступил на мину — ставка сгорела.</div>
      <div class="skg-ladder">${(d.ladder||[]).slice(0,8).map((m,i)=>`<span class="skg-step">${i+1}: ×${m}</span>`).join('')}<span class="skg-step">…</span></div>
      ${_skgStakeHtml('sapper', lim.sapper)}
      <button class="btn btn-gold btn-full" ${cd>0?'disabled':''} onclick="skgStart('sapper')">▶ Играть</button>
    </div>
    <div class="card">
      <div class="card-title">🔐 Взлом сейфа</div>
      <div class="skg-desc">Код — 4 цифры (0–9, могут повторяться). ${d.safe_attempts||6} попыток.
      После каждой: 🎯 «на месте» и 🔄 «есть, но не там». Взломал — ×${d.safe_win_mult||1.6}.</div>
      ${_skgStakeHtml('safe', lim.safe)}
      <button class="btn btn-gold btn-full" ${cd>0?'disabled':''} onclick="skgStart('safe')">▶ Играть</button>
    </div>
    <div class="card">
      <div class="card-title">⚗️ Алхимия</div>
      <div class="skg-desc">Merge-2048 на поле 4×4, 60 секунд. Свайпай плитки, объединяй одинаковые —
      выплата = ставка × (счёт / 1000), максимум ×3.</div>
      ${_skgStakeHtml('alch', lim.alchemy)}
      <button class="btn btn-gold btn-full" ${cd>0?'disabled':''} onclick="alchStart()">▶ Играть</button>
    </div>
    <div class="set-hint">Дневной лимит выигрыша общий для всех трёх игр. Сервер решает всё — шансы честные и фиксированные.</div>`;
}
function _skgStakeHtml(game, lim){
  const chips=[100,250,500,1000,2000].filter(v=>v>=lim[0]&&v<=lim[1]);
  return `<div class="skg-stakes" id="skg-st-${game}">
    ${chips.map((v,i)=>`<button class="btn btn-sm ${i===0?'btn-gold':'btn-ghost'}" data-v="${v}"
      onclick="_skgPickStake('${game}',this)">${fmt(v)}</button>`).join('')}
  </div>`;
}
function _skgPickStake(game, btn){
  document.querySelectorAll(`#skg-st-${game} .btn`).forEach(b=>b.className='btn btn-sm btn-ghost');
  btn.className='btn btn-sm btn-gold';
}
function _skgStake(game){
  const b=document.querySelector(`#skg-st-${game} .btn-gold`);
  return b?parseFloat(b.getAttribute('data-v')):100;
}
function skgStart(game){
  const stake=_skgStake(game);
  api(`/games2/${game}/start`,{method:'POST',body:JSON.stringify({stake})}).then(r=>{
    _haptic('light'); refreshCurrBar();
    if(_skg) _skg[game]=r;   // кэш активной сессии (ставка/прогресс между ходами)
    if(game==='sapper') _skgRenderSapper(r); else { _safeInput=[]; _skgRenderSafe(r); }
  }).catch(e=>toast(e,false));
}
// ── Сапёр: поле ───────────────────────────────────────────────────────────────
function _skgRenderSapper(s, final){
  const opened=new Set(s.opened||[]);
  const minesSet=new Set(final&&final.mines||[]);
  const cells=[];
  for(let i=0;i<(s.grid||25);i++){
    const isOpen=opened.has(i), isMine=minesSet.has(i);
    const boomCell = final&&final.boom&&final.cell===i;
    cells.push(`<button class="skg-cell${isOpen?' open':''}${isMine?' mine':''}${boomCell?' boom':''}"
      ${(isOpen||final)?'disabled':''} onclick="skgOpen(${i},this)">${boomCell?'💥':isMine?'💣':isOpen?'✅':''}</button>`);
  }
  const k=s.k||0;
  let head, foot;
  if(final&&final.boom){
    head=`<div class="skg-head skg-lost">💥 Мина! Ставка ${fmt(final.stake)} 🪙 сгорела</div>`;
    foot=`<button class="btn btn-gold btn-full" onclick="loadSkillGames()">↩ В лобби</button>`;
  } else if(final&&final.cashed){
    head=`<div class="skg-head skg-won">💰 Забрал ×${final.multiplier} — +${fmt(final.payout)} 🪙${final.capped?' (срезано дневным капом)':''}</div>`;
    foot=`<button class="btn btn-gold btn-full" onclick="loadSkillGames()">↩ В лобби</button>`;
  } else {
    head=`<div class="skg-head">Открыто: <b>${k}</b> · множитель <b style="color:var(--gold2)">×${s.multiplier||0}</b> · следующая: ×${s.next_multiplier||''}</div>`;
    foot=k>0
      ?`<button class="btn btn-gold btn-full" onclick="skgCashout(this)">💰 Забрать ${fmt(s.cashout_value)} 🪙 (×${s.multiplier})</button>`
      :`<div class="set-hint" style="text-align:center">Открой первую клетку — и решай: жадность или расчёт</div>`;
  }
  el('skg').innerHTML=`
    <div class="card">
      <div class="card-title">💣 Теневой Сапёр ${final?'':`<span style="float:right;font-size:11px;color:var(--muted)">ставка ${fmt(s.stake)} 🪙</span>`}</div>
      ${head}
      <div class="skg-grid">${cells.join('')}</div>
      ${foot}
    </div>`;
}
function skgOpen(cell, btn){
  if(btn){btn.disabled=true;}
  api('/games2/sapper/open',{method:'POST',body:JSON.stringify({cell})}).then(r=>{
    if(r.boom){ _haptic('error'); _skgRenderSapper({stake:r.stake, opened:[], grid:25, k:0}, r); refreshCurrBar(); return; }
    if(r.cashed){ _haptic('success'); _skgRenderSapper({stake:0, opened:[], grid:25, k:r.k}, r); refreshCurrBar(); return; }
    _haptic('light');
    // локально дорисовываем без полного refetch
    const cur=(_skg&&_skg.sapper)?_skg.sapper:{stake:0,opened:[],grid:25};
    cur.opened=(cur.opened||[]).concat([cell]);
    cur.k=r.k; cur.multiplier=r.multiplier; cur.next_multiplier=r.next_multiplier; cur.cashout_value=r.cashout_value;
    if(_skg) _skg.sapper=cur;
    _skgRenderSapper(cur);
  }).catch(e=>{toast(e,false); if(btn)btn.disabled=false;});
}
function skgCashout(btn){
  if(btn)btn.disabled=true;
  api('/games2/sapper/cashout',{method:'POST'}).then(r=>{
    _haptic('success'); refreshCurrBar();
    if(_skg) _skg.sapper=null;
    _skgRenderSapper({stake:0, opened:[], grid:25, k:r.k}, r);
  }).catch(e=>{toast(e,false); if(btn)btn.disabled=false;});
}
// ── Сейф: наборник ────────────────────────────────────────────────────────────
function _skgRenderSafe(s, final){
  const guesses=(final&&final.guesses)||s.guesses||[];
  const rows=guesses.map(g=>`<div class="safe-row">
    <span class="safe-code">${g.digits.join(' ')}</span>
    <span class="safe-bc">🎯 ${g.bulls} · 🔄 ${g.cows}</span>
  </div>`).join('')||'<div class="set-hint">Первая попытка — разведка. 🎯 цифра на месте, 🔄 есть в коде, но не там.</div>';
  let head, pad='';
  if(final&&final.cracked){
    head=`<div class="skg-head skg-won">🔓 ВЗЛОМАН! Код ${final.secret.join(' ')} — +${fmt(final.payout)} 🪙${final.capped?' (срезано капом)':''}</div>`;
    pad=`<button class="btn btn-gold btn-full" onclick="loadSkillGames()">↩ В лобби</button>`;
  } else if(final&&final.failed){
    head=`<div class="skg-head skg-lost">🔒 Не взломан. Код был: <b>${final.secret.join(' ')}</b>. Ставка сгорела.</div>`;
    pad=`<button class="btn btn-gold btn-full" onclick="loadSkillGames()">↩ В лобби</button>`;
  } else {
    const left=(final&&final.attempts_left!==undefined)?final.attempts_left:s.attempts_left;
    const wm=s.win_mult||(_skg&&_skg.safe_win_mult)||1.6;
    head=`<div class="skg-head">Попыток осталось: <b>${left}</b> · взлом = ×${wm}</div>`;
    pad=`
      <div class="safe-input" id="safe-inp">${[0,1,2,3].map(i=>`<span class="safe-digit">${_safeInput[i]!==undefined?_safeInput[i]:'·'}</span>`).join('')}</div>
      <div class="safe-pad">
        ${[1,2,3,4,5,6,7,8,9,0].map(n=>`<button class="btn btn-ghost" onclick="safeKey(${n})">${n}</button>`).join('')}
        <button class="btn btn-ghost" onclick="safeKey(-1)">⌫</button>
        <button class="btn btn-gold" onclick="safeSubmit(this)">✓</button>
      </div>`;
  }
  el('skg').innerHTML=`
    <div class="card">
      <div class="card-title">🔐 Взлом сейфа ${(final&&(final.cracked||final.failed))?'':`<span style="float:right;font-size:11px;color:var(--muted)">ставка ${fmt(s.stake)} 🪙</span>`}</div>
      ${head}
      <div class="safe-history">${rows}</div>
      ${pad}
    </div>`;
}
function safeKey(n){
  if(n===-1){ _safeInput.pop(); }
  else if(_safeInput.length<4){ _safeInput.push(n); _haptic('light'); }
  const inp=el('safe-inp');
  if(inp) inp.innerHTML=[0,1,2,3].map(i=>`<span class="safe-digit">${_safeInput[i]!==undefined?_safeInput[i]:'·'}</span>`).join('');
}
function safeSubmit(btn){
  if(_safeInput.length!==4){ toast('Введи 4 цифры', false); return; }
  if(btn)btn.disabled=true;
  const digits=_safeInput.slice();
  api('/games2/safe/guess',{method:'POST',body:JSON.stringify({digits})}).then(r=>{
    _safeInput=[];
    if(r.cracked){ _haptic('success'); refreshCurrBar(); _skgRenderSafe({stake:0}, r); return; }
    if(r.failed){ _haptic('error'); _skgRenderSafe({stake:0}, r); return; }
    _haptic(r.bulls>0?'medium':'light');
    _skgRenderSafe({stake:(_skg&&_skg.safe?_skg.safe.stake:0), guesses:r.guesses, attempts_left:r.attempts_left, win_mult:(_skg&&_skg.safe_win_mult)||1.6});
  }).catch(e=>{toast(e,false); if(btn)btn.disabled=false;});
}

// ══ R7.2 «Алхимия»: merge-2048 4×4 на 60 сек ══════════════════════════════════
// Детерминированная симуляция (двойник services/alchemy.py — xorshift32, тот же
// порядок операций, кросс-тест node↔python). Сервер выдаёт seed, клиент играет
// локально и шлёт ЛОГ ХОДОВ; счёт для выплаты считает ТОЛЬКО сервер (реплей).
function _alchRng(s){ s^=(s<<13); s>>>=0; s^=(s>>>17); s^=(s<<5); s>>>=0; return s; }
function _alchSim(seed){
  const S={rng:(seed>>>0)||1, board:new Array(16).fill(0), score:0};
  S.next=()=>{S.rng=_alchRng(S.rng); return S.rng;};
  S.spawn=()=>{
    const empty=[]; S.board.forEach((v,i)=>{if(!v)empty.push(i);});
    if(!empty.length) return;
    const pos=empty[S.next()%empty.length];
    S.board[pos]=(S.next()%10)<9?2:4;
  };
  S.move=(d)=>{
    let changed=false;
    for(let k=0;k<4;k++){
      const idx=[];
      for(let j=0;j<4;j++) idx.push(d==='L'||d==='R' ? k*4+j : j*4+k);
      let line=idx.map(i=>S.board[i]);
      if(d==='R'||d==='D') line.reverse();
      const vals=line.filter(v=>v), out=[];
      let gained=0;
      for(let i=0;i<vals.length;i++){
        if(i+1<vals.length && vals[i]===vals[i+1]){ out.push(vals[i]*2); gained+=vals[i]*2; i++; }
        else out.push(vals[i]);
      }
      while(out.length<4) out.push(0);
      const ch=out.some((v,i)=>v!==line[i]);
      if(ch){
        changed=true; S.score+=gained;
        const w=out.slice(); if(d==='R'||d==='D') w.reverse();
        idx.forEach((bi,i)=>{S.board[bi]=w[i];});
      }
    }
    if(changed) S.spawn();
    return changed;
  };
  S.spawn(); S.spawn();
  return S;
}
let _alch=null;   // {sim, moves, deadline, timer, sessionId, stake}
function _alchResume(a){
  _alch={sim:_alchSim(a.seed), moves:[], sessionId:a.session_id, stake:a.stake,
         deadline:Date.now()+(a.remaining_sec||0)*1000, done:false};
  _alchRender();
  _alch.timer=setInterval(()=>{
    const s=Math.max(0,Math.ceil((_alch.deadline-Date.now())/1000));
    const t=el('alch-timer'); if(t){t.textContent=s+'с'; t.style.color=s<=10?'var(--red)':'';}
    if(s<=0) alchSubmit();
  },250);
}
function alchStart(){
  const stake=_skgStake('alch');
  api('/games2/alchemy/start',{method:'POST',body:JSON.stringify({stake})}).then(r=>{
    _haptic('medium'); refreshCurrBar();
    _alch={sim:_alchSim(r.seed), moves:[], sessionId:r.session_id, stake:r.stake,
           deadline:Date.now()+(r.time_limit_sec||60)*1000, done:false};
    _alchRender();
    _alch.timer=setInterval(()=>{
      const s=Math.max(0,Math.ceil((_alch.deadline-Date.now())/1000));
      const t=el('alch-timer'); if(t){t.textContent=s+'с'; t.style.color=s<=10?'var(--red)':'';}
      if(s<=0) alchSubmit();
    },250);
  }).catch(e=>toast(e,false));
}
function _alchRender(){
  const host=el('skg'); if(!host||!_alch) return;
  const tiles=_alch.sim.board.map(v=>`<div class="alch-tile v${v}">${v||''}</div>`).join('');
  host.innerHTML=`
    <div class="card">
      <div class="card-title">⚗️ Алхимия
        <span style="float:right;font-size:12px">⏱ <span id="alch-timer">60с</span></span></div>
      <div class="skg-head">Счёт: <b id="alch-score" style="color:var(--gold2)">${_alch.sim.score}</b>
        · выплата = ставка × min(3, счёт/1000)</div>
      <div class="alch-grid" id="alch-grid"
           ontouchstart="_alchTouch(event,1)" ontouchend="_alchTouch(event,0)">${tiles}</div>
      <div class="bt-stances" style="grid-template-columns:repeat(4,1fr)">
        <button class="btn btn-ghost" onclick="alchMove('L')">←</button>
        <button class="btn btn-ghost" onclick="alchMove('U')">↑</button>
        <button class="btn btn-ghost" onclick="alchMove('D')">↓</button>
        <button class="btn btn-ghost" onclick="alchMove('R')">→</button>
      </div>
      <button class="btn btn-gold btn-full" style="margin-top:8px" onclick="alchSubmit()">✅ Завершить и получить</button>
    </div>`;
}
let _alchT0=null;
function _alchTouch(ev,down){
  if(down){ const t=ev.touches[0]; _alchT0={x:t.clientX,y:t.clientY}; return; }
  if(!_alchT0) return;
  const t=ev.changedTouches[0], dx=t.clientX-_alchT0.x, dy=t.clientY-_alchT0.y;
  _alchT0=null;
  if(Math.max(Math.abs(dx),Math.abs(dy))<24) return;   // не свайп
  alchMove(Math.abs(dx)>Math.abs(dy) ? (dx>0?'R':'L') : (dy>0?'D':'U'));
}
function alchMove(d){
  if(!_alch||_alch.done) return;
  if(Date.now()>_alch.deadline) { alchSubmit(); return; }
  if(_alch.moves.length>=250){ alchSubmit(); return; }
  if(_alch.sim.move(d)){
    _alch.moves.push(d);
    _haptic('light');
    const g=el('alch-grid');
    if(g) g.innerHTML=_alch.sim.board.map(v=>`<div class="alch-tile v${v}">${v||''}</div>`).join('');
    const sc=el('alch-score'); if(sc) sc.textContent=_alch.sim.score;
  }
}
function alchSubmit(){
  if(!_alch||_alch.done) return;
  _alch.done=true; clearInterval(_alch.timer);
  api('/games2/alchemy/submit',{method:'POST',body:JSON.stringify({session_id:_alch.sessionId, moves:_alch.moves})})
    .then(r=>{
      _haptic(r.payout>_alch.stake?'success':'light'); refreshCurrBar();
      el('skg').innerHTML=`<div class="card">
        <div class="skg-head ${r.payout>0?'skg-won':'skg-lost'}">
          ⚗️ Счёт ${fmt(r.score)} → ×${r.mult} — ${r.payout>0?`+${fmt(r.payout)} 🪙`:'ставка сгорела'}${r.capped?' (кап)':''}
        </div>
        <button class="btn btn-gold btn-full" onclick="loadSkillGames()">↩ В лобби</button></div>`;
      _alch=null;
    })
    .catch(e=>{toast(e,false); el('skg').innerHTML=''; loadSkillGames(); _alch=null;});
}
