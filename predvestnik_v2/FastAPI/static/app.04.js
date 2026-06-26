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
// ── Arena — только Дуэли + Ивенты. Гача/Крафт/Тёмная/Квесты перенесены в Рынок/Профиль.
function loadArena(){swArena(_arenaTab,document.querySelector('#pg-arena .tb'));}
function swArena(tab,btn) {
  _arenaTab=tab;
  document.querySelectorAll('#pg-arena .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  ['raids','events'].forEach(t=>{const e=el('ar-'+t); if(e)e.style.display=t===tab?'':'none';});
  ({raids:loadRaid,events:loadEvents}[tab]||loadRaid)();
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
    if(!qs.length && !weekly.length){
      el('qc').innerHTML='<div style="text-align:center;padding:24px;color:var(--muted)"><div style="font-size:28px;margin-bottom:6px">📋</div><div style="font-size:12px">Нет квестов — напиши <code>бот задания</code> в чате</div></div>';
      return;
    }
    const daily = _questSectionHtml('📅 Ежедневные', qs, r.bonus, 'Бонус за все дневные');
    const wk = weekly.length ? _questSectionHtml('🗓 Недельные', weekly, r.weekly_bonus, 'Бонус за все недельные') : '';
    el('qc').innerHTML = daily + (wk ? `<div style="height:8px"></div>${wk}` : '');
  }).catch(e=>{el('qc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
const SPIN_ICONS = {mora:'🪙',diamond:'💎'};
const SPIN_RARITY_ORDER = ['mythic','legendary','epic','rare','uncommon','common'];

function _topRarity(dups) {
  for(const r of SPIN_RARITY_ORDER) if(dups.some(d=>d.rarity===r)) return r;
  return '';
}

function loadGacha() {
  el('gc').innerHTML='<div class="loader">Загрузка...</div>';
  api('/gacha/').then(d=>{
    const disc = d.multi_discount_pct||10;
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
    <div class="card">
      <div class="card-title" style="margin-bottom:10px;display:flex;justify-content:space-between;align-items:center">
        <span>Выберите крутку</span>
        <button class="btn btn-sm btn-ghost" style="padding:2px 8px;font-size:10px" onclick="openGachaOdds()">ℹ️ Шансы</button>
      </div>
      ${d.spin_types.map(s=>{
        const icon = SPIN_ICONS[s.spin_type] || '🎲';
        const cost = s.cost_mora ? `${fmt(s.cost_mora)} 🪙` : `${s.cost_dia} 💎`;
        const multiCost = s.cost_mora ? `${fmt(s.multi_cost_mora)} 🪙` : `${s.multi_cost_dia} 💎`;
        const pityPct = s.pity_hard > 0 ? Math.round(s.pity/s.pity_hard*100) : 0;
        const rates = s.rates||{};
        const ratesBadges = Object.entries(rates).map(([r,v])=>
          `<span class="${RC[r]||'rc-common'}" style="font-size:9px;padding:1px 4px">${r[0].toUpperCase()+r.slice(1)} ${v}%</span>`
        ).join(' ');
        return `<div class="spin-block">
          <div class="spin-row" onclick="doSpin('${s.spin_type}',this)">
            <div class="sr-icon">${icon}</div>
            <div class="sr-info">
              <div class="sr-name">${s.label}</div>
              ${ratesBadges?`<div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:4px">${ratesBadges}</div>`:''}
            </div>
            ${s.token_qty?`<span style="font-size:11px;color:var(--green);margin-right:6px">🎟 ×${s.token_qty}</span>`:''}
            <div class="sr-cost">${cost}</div>
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
      }).join('')}
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

function doMultiSpin(st, btn) {
  btn.disabled=true;
  el('spin-res').innerHTML=`<div class="spin-anim-wrap"><div class="spin-anim-ball" style="animation-duration:2s">🎲</div><div style="font-size:12px;color:var(--gold2);margin-top:8px">×10 крутка...</div></div>`;
  api('/gacha/multi-spin',{method:'POST',body:JSON.stringify({spin_type:st,chat_id:_cid||0})}).then(r=>{
    const s=r.summary||{};
    const dups=s.dup_outcomes||[];
    const topRarity=_topRarity(dups);
    const glowCls=topRarity?'glow-'+topRarity:'';
    const cards=[];
    if(s.mora) cards.push({text:`🪙 ${fmt(s.mora)} Мора`,cls:''});
    if(s.diamonds) cards.push({text:`💎 ${s.diamonds} Алмазов`,cls:''});
    // Aggregate items by item_id to avoid duplicate entries
    const itemMap={};
    (s.items||[]).forEach(i=>{
      const k=i.id||i.item_id||i.name||'?';
      if(itemMap[k]) itemMap[k].qty+=i.qty||1;
      else itemMap[k]={name:i.name||k,qty:i.qty||1};
    });
    Object.values(itemMap).forEach(i=>cards.push({text:`📦 ${i.name} ×${i.qty}`,cls:''}));
    // Summarize pet dups by species
    const petMap={};
    dups.forEach(d=>{
      const k=d.species_id||d.species||'?';
      if(!petMap[k]) petMap[k]={name:d.species_name||k,rarity:d.rarity,count:0,newLevel:null};
      petMap[k].count++;
      if(d.new_level) petMap[k].newLevel=d.new_level;
    });
    Object.values(petMap).forEach(p=>cards.push({text:`🐾 ${p.name} ${rc(p.rarity)} ×${p.count}${p.newLevel?' → Lv'+p.newLevel:''}`,cls:p.rarity||''}));

    el('spin-res').innerHTML=`
      <div class="spin-anim-wrap ${glowCls}">
        <div style="font-size:40px;font-weight:800;color:var(--gold2)">×${s.count||10}</div>
        <div style="font-size:11px;color:var(--gold2);margin-top:4px;font-weight:700">
          ${topRarity?('⚡ '+topRarity.toUpperCase()):'Результат мультикрутки'}
        </div>
      </div>
      <div class="spin-results">
        ${cards.map((c,i)=>`<div class="spin-card ${c.cls}" style="animation-delay:${(i*0.06+0.5).toFixed(2)}s">${c.text}</div>`).join('')}
      </div>
      ${_petActionsHtml(dups)}
      <div style="display:flex;gap:8px;margin-top:10px">
        <button class="btn btn-gold" style="flex:2" onclick="loadGacha()">🔄 Крутить ещё</button>
        <button class="btn btn-ghost" style="flex:1" onclick="closeSpinResult()">↩ Назад</button>
      </div>`;
    _spinJuice(topRarity);
    refreshCurrBar();
    btn.disabled=false;
  }).catch(e=>{toast(e,false);btn.disabled=false;el('spin-res').innerHTML='';});
}
function loadCraft() {
  el('cc').innerHTML='<div class="loader">Загрузка...</div>';
  api('/craft/').then(recipes => {
    if (!recipes.length) { el('cc').innerHTML='<div class="empty-state"><div class="es-icon">⚗️</div><div class="es-title">Рецептов пока нет</div><div class="es-sub">Рецепты крафта появятся в следующих обновлениях</div></div>'; return; }
    el('cc').innerHTML = recipes.map(rc => `
      <div class="card card-gold">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <div style="font-size:15px;font-weight:700;color:var(--bright)">${rc.name}</div>
          ${rc.can_craft_times>1?`<span style="font-size:11px;color:var(--green);background:rgba(82,179,96,.15);padding:2px 8px;border-radius:99px">×${rc.can_craft_times} возможно</span>`:''}
        </div>
        ${rc.what_is?`<div style="font-size:12px;color:var(--text);line-height:1.5;margin-bottom:10px">${rc.what_is}</div>`:''}
        ${rc.how_use?`<div class="irow"><span class="ik">Как использовать</span><span style="color:var(--teal);font-size:11px">${rc.how_use}</span></div>`:''}
        ${rc.gacha_rates?`<div class="irow"><span class="ik">Шансы при открытии</span><span style="font-size:11px">${rc.gacha_rates}</span></div>`:''}
        ${rc.special_note?`<div style="background:rgba(224,82,82,.1);border:1px solid rgba(224,82,82,.25);border-radius:var(--r);padding:8px 10px;font-size:11px;color:var(--red);margin:8px 0">${rc.special_note}</div>`:''}
        <div class="divider"></div>
        <div class="card-title">Нужно для крафта</div>
        ${rc.ingredients_status.map(i=>`
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <span style="font-size:18px">${i.have>=i.needed?'✅':'❌'}</span>
            <div style="flex:1">
              <div style="font-size:12px;font-weight:600">${i.item_name}</div>
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

    // Challenge button
    html += `<button class="btn btn-red btn-full" style="margin-bottom:10px" onclick="openDuelChallenge()">⚔️ Вызвать игрока на дуэль</button>`;

    // Incoming challenges
    const incoming = active.filter(d => d.challenged_id == _uid);
    if(incoming.length) {
      html += `<div class="card"><div class="card-title">⏳ Входящие вызовы (${incoming.length})</div>
        ${incoming.map(d=>`<div class="duel-card">
          <div class="duel-vs">${vipName(d.challenger_name||'Игрок', d.challenger_is_vip)} вызывает вас</div>
          <div class="duel-stake">Ставка: ${fmt(d.stake)} 🪙</div>
          <div style="display:flex;gap:6px;margin-top:8px">
            <button class="btn btn-sm btn-teal" style="flex:1" onclick="acceptDuel(${d.id},this)">⚔️ Принять</button>
            <button class="btn btn-sm btn-red" style="flex:1" onclick="declineDuel(${d.id},this)">❌ Отклонить</button>
          </div>
        </div>`).join('')}
      </div>`;
    }

    // Outgoing pending
    const outgoing = active.filter(d => d.challenger_id == _uid);
    if(outgoing.length) {
      html += `<div class="card"><div class="card-title">📤 Мои вызовы</div>
        ${outgoing.map(d=>`<div class="duel-card">
          <div class="duel-vs">→ ${vipName(d.challenged_name||'Игрок', d.challenged_is_vip)}</div>
          <div class="duel-stake">Ставка: ${fmt(d.stake)} 🪙</div>
          <div style="font-size:10px;color:var(--muted)">Ожидание ответа...</div>
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
          return `<div class="duel-card">
            <div style="display:flex;align-items:center;justify-content:space-between">
              <div class="duel-vs">vs ${vipName(vs||'Игрок', vsIsVip)}</div>
              <div class="duel-result${isDone?(won?' win':' lose'):''}">
                ${isDone?(won?'✓ Победа':'✗ Поражение'):statusMap[d.status]||d.status}
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

function acceptDuel(id, btn) {
  btn.disabled = true;
  btn.textContent = '...';
  api('/duels/accept', {method:'POST', body:JSON.stringify({duel_id:id})})
    .then(r => {
      const won = r.winner_id == _uid;
      toast(won ? '🏆 Победа!' : (r.winner_id ? '😔 Поражение' : '🤝 Ничья'), won);
      loadDuels();
      refreshCurrBar();
    })
    .catch(e => { toast(e, false); btn.disabled = false; btn.textContent = '⚔️ Принять'; });
}

function declineDuel(id, btn) {
  btn.disabled = true;
  api('/duels/decline', {method:'POST', body:JSON.stringify({duel_id:id})})
    .then(() => { toast('✅ Вызов отклонён.'); loadDuels(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

function openDuelChallenge() {
  if(!_cid) { toast('Нужен Профиль с чатом для вызова.', false); return; }
  // Grab current balance from profile data if available
  const bal = _profileData?.mora || 0;
  const balStr = bal > 0 ? `<div style="background:var(--s);border-radius:var(--r);padding:6px 10px;margin-bottom:10px;font-size:11px;display:flex;justify-content:space-between"><span style="color:var(--muted)">Ваш баланс</span><span style="color:var(--gold);font-weight:600">${fmt(bal)} 🪙</span></div>` : '';
  OM('⚔️ Вызов на дуэль', `
    ${balStr}
    <div style="font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.5">
      Соперник получит уведомление в Telegram — он должен ответить <code>бот принять</code> в чате.
    </div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">@username соперника</div>
    <input id="duel-user" type="text" class="num-input" placeholder="username (без @)"/>
    <div style="font-size:11px;color:var(--muted);margin:8px 0 4px">Ставка 🪙 (200 – 15 000)</div>
    <input id="duel-stake" type="number" class="num-input" placeholder="500" min="200" max="15000"/>
    <div style="font-size:10px;color:var(--gold);margin-top:6px;background:var(--gold-dim);padding:6px 8px;border-radius:var(--r)">
      🔒 Ставка заморозится до конца дуэли. Победитель забирает обе ставки.
    </div>
  `, [
    {l:'⚔️ Вызвать', c:'btn-red', f:'submitDuelChallenge(this)'},
    {l:'Отмена', c:'btn-ghost', f:'CM()'},
  ]);
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
let _aucPage = 0, _aucTotal = 0, _aucPerPage = 48;

function loadAuction(page) {
  if(page !== undefined) _aucPage = page;
  api(`/auction/lots?page=${_aucPage}&per_page=${_aucPerPage}`).then(data=>{
    _allLots = data.lots || data;  // backward compat
    _aucTotal = data.total || _allLots.length;
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
    '<div style="font-size:12px;color:var(--muted);line-height:1.5">Лот закроется, активные ставки отменятся, а резерв вернётся участникам. Питомец (если лот на питомца) вернётся на склад.</div>',
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
      ⚠️ Внимательно проверь предмет перед выставлением — отменить лот нельзя!
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
  const maxQ = Math.min(maxQty, 10);
  el('mb').innerHTML = `
    <div style="background:var(--s);border-radius:var(--r);padding:10px;margin-bottom:12px">
      <div style="font-size:13px;font-weight:700;color:var(--bright);margin-bottom:4px">${itemName}</div>
      ${itemDesc?`<div style="font-size:11px;color:var(--muted);line-height:1.4">${itemDesc}</div>`:''}
      <div style="font-size:10px;color:var(--muted);margin-top:4px">В наличии: ×${maxQty}</div>
    </div>
    <div class="divider"></div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Количество (1–${maxQ})</div>
    <input id="lot-qty" type="number" class="num-input" min="1" max="${maxQ}" value="1"/>
    <div style="font-size:10px;color:var(--muted);margin-bottom:10px">Максимум 10 ед. за один лот</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Минимальная ставка 🪙</div>
    <input id="lot-bid" type="number" class="num-input" min="50" value="500" placeholder="Мин. ставка (от 50 🪙)"/>
    <div style="font-size:11px;color:var(--muted);margin:8px 0 4px">Цена выкупа 🪙 <span style="color:var(--dim)">(необязательно)</span></div>
    <input id="lot-buyout" type="number" class="num-input" placeholder="Оставь пустым если без выкупа"/>
    <div style="font-size:10px;color:var(--muted);margin-top:8px;padding:6px 8px;background:var(--s);border-radius:var(--r)">
      ⏳ Лот активен 24 часа. После создания отменить нельзя.
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
  if(!minBid||minBid<50){toast('Мин. ставка от 50 🪙',false);return;}
  const btn = document.querySelector('#mf .btn-gold');
  if(btn) btn.disabled=true;
  api('/auction/create',{method:'POST',body:JSON.stringify({item_id:itemId,quantity:qty,min_bid:minBid,buyout})})
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
    <input id="lot-bid" type="number" class="num-input" min="50" value="1000" placeholder="Мин. ставка (от 50 🪙)"/>
    <div style="font-size:11px;color:var(--muted);margin:8px 0 4px">Цена выкупа 🪙 <span style="color:var(--dim)">(необязательно)</span></div>
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
  if(!minBid||minBid<50){toast('Мин. ставка от 50 🪙',false);return;}
  const btn = document.querySelector('#mf .btn-gold');
  if(btn) btn.disabled=true;
  api('/auction/create-pet',{method:'POST',body:JSON.stringify({pet_id:petId,min_bid:minBid,buyout})})
    .then(r=>{toast(`✅ Питомец выставлен! Лот #${r.lot_id} (24ч)`);CM();loadAuction();})
    .catch(e=>{toast(e,false);if(btn)btn.disabled=false;});
}

// openBidModal(lotId, name, currentBid, minNextBid, hasBids, buyout)
// minNextBid comes from server (min_bid if no bids, ceil(cur*1.05) if bids exist)
function openBidModal(lotId, name, currentBid, minNextBid, hasBids, buyout) {
  const firstBid = !hasBids;
  const minLabel = firstBid
    ? `Первая ставка — не менее <b>${fmt(minNextBid)} 🪙</b>`
    : `Мин. для обгона — <b>${fmt(minNextBid)} 🪙</b> (текущая × 1.05)`;
  const buyoutBtn = buyout
    ? `<button class="btn btn-teal btn-full" style="margin-top:8px"
             onclick="doBid(${lotId},this,${buyout})">⚡ Выкупить за ${fmt(buyout)} 🪙</button>`
    : '';
  OM(`💰 Ставка: ${name}`, `
    <div class="irow"><span class="ik">Текущая ставка</span><span style="color:var(--gold);font-weight:700">${fmt(currentBid)} 🪙</span></div>
    <div style="font-size:11px;color:var(--muted);margin:8px 0">${minLabel}</div>
    <div class="divider"></div>
    <input id="bid-val" class="num-input" type="number"
           value="${minNextBid}" min="${minNextBid}" step="1"
           placeholder="Ваша ставка 🪙"/>
    <div style="font-size:10px;color:var(--muted);margin-top:6px">
      Мора будет зарезервирована до завершения аукциона.
    </div>
    ${buyoutBtn}
  `, [{l:'💰 Поставить ставку', c:'btn-gold', f:`doBid(${lotId},this,0)`}, {l:'Отмена', c:'btn-ghost', f:'CM()'}]);
}
function doBid(lotId, btn, fixedAmount) {
  const v = fixedAmount > 0 ? fixedAmount : parseFloat(el('bid-val')?.value || 0);
  if (!v || v <= 0) { toast('Введите сумму.', false); return; }
  btn.disabled = true;
  api('/auction/bid', {method:'POST', body:JSON.stringify({lot_id:lotId, amount:v})})
    .then(r => { toast(r.is_buyout ? '🎉 Выкуплено!' : '✅ Ставка принята!'); CM(); loadAuction(); refreshCurrBar(); })
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
      `<div class="card"><div class="card-title">${cats[cat]||cat}</div>${list.map(it=>`<div class="shop-row">
        <span style="font-size:22px;width:32px;text-align:center">${it.name.split(' ')[0]}</span>
        <div style="flex:1">
          <div style="font-size:13px;font-weight:600;color:var(--bright)">${it.name}</div>
          <div style="font-size:11px;color:var(--gold)">${it.price_mora?fmt(it.price_mora)+' 🪙':it.price_diamonds?it.price_diamonds+' 💎':fmt(it.price_zarniki)+' ✨'}${it.discount_active?' 🐢':''}</div>
          <div style="font-size:10px;color:var(--muted)">${it.description||''}</div>
          ${_invData.find(i=>i.item_id===it.item_id)
            ? `<div style="font-size:10px;color:var(--green);margin-top:2px">✓ В инвентаре: ×${_invData.find(i=>i.item_id===it.item_id).quantity}</div>`
            : ''}
        </div>
        <button class="btn btn-sm btn-gold" onclick="buyItem('${it.item_id}',this)">Купить</button>
      </div>`).join('')}</div>`).join('');
  }).catch(e=>{el('mkt-shop').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
// Block 9: warn before buying if already in inventory
function buyItem(id, btn) {
  const existing = _invData.find(i => i.item_id === id);
  if (existing) {
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
function doBuyConfirmed(id) { CM(); _shopBuy(id, 1, false, null); }
function _execBuy(id, btn) { _shopBuy(id, 1, false, btn); }
// Единый поток покупки + Smart Checkout (ШАГ6): при нехватке базовой валюты
// предлагаем добрать Зарниками (сценарий A) или купить Зарники (сценарий B).
function _shopBuy(id, qty, cover, btn) {
  if(btn) btn.disabled = true;
  api('/shop/buy', {method:'POST', body:JSON.stringify({item_id:id, quantity:qty, cover_with_zarniki:!!cover})})
    .then(r => { toast('✅ ' + (r.message || ('Куплено: ' + r.item_name))); loadShopCatalog(); refreshCurrBar(); if(btn) btn.disabled=false; })
    .catch(e => {
      if(btn) btn.disabled=false;
      if(cover) { toast(e, false); return; }   // уже добирали ✨ — не зацикливаемся
      _smartCheckout(id, qty, e);
    });
}
function _smartCheckout(id, qty, origErr) {
  api('/shop/checkout-quote', {method:'POST', body:JSON.stringify({item_id:id, quantity:qty})})
    .then(q => {
      if(q.affordable || !q.zarniki_needed) { toast(origErr, false); return; }  // ошибка не про деньги
      const lack = Object.values(q.deficits||{}).map(d=>`${fmtF(d.amount)} ${d.icon}`).join(' и ');
      if(q.coverable) {
        OM('✨ Не хватает чуть-чуть',
          `<div style="padding:6px 2px;font-size:13px;line-height:1.5">Тебе не хватает <b>${lack}</b> для покупки «${esc(q.item_name)}».<br><br>Покрыть недостаток Зарниками? Спишется <b>${q.zarniki_needed} ✨</b> <span style="color:var(--muted)">(у тебя ${fmtF(q.zarniki_have)} ✨)</span>.</div>`,
          [{l:`Купить +${q.zarniki_needed} ✨`, c:'btn-gold', f:`_smartConfirm('${id}',${qty})`},
           {l:'Отмена', c:'btn-ghost', f:'CM()'}]);
      } else {
        OM('✨ Нужны Зарники',
          `<div style="padding:6px 2px;font-size:13px;line-height:1.5">Тебе не хватает <b>${lack}</b> (или <b>${q.zarniki_needed} ✨</b>) для быстрой покупки «${esc(q.item_name)}».<br><br><span style="color:var(--muted)">У тебя ${fmtF(q.zarniki_have)} ✨ — недостаточно.</span></div>`,
          [{l:'Купить Зарники ✨', c:'btn-gold', f:"CM();goTo('market','vip')"},
           {l:'Отмена', c:'btn-ghost', f:'CM()'}]);
      }
    })
    .catch(() => toast(origErr, false));
}
function _smartConfirm(id, qty) { CM(); _shopBuy(id, qty, true, null); }
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
  const {item_id,name,quantity,category,description,spin_type,boost_hours,fatigue_restore}=it;
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
    body+=`<div class="irow"><span class="ik">Даёт дубликатов</span><span style="color:var(--gold)">+${item_id.includes('_l')?5:1}</span></div>`;
    if(quantity>0)btns.unshift({l:'✨ Применить',c:'btn-gold',f:`openDustModal('${item_id}')`});
  } else if(item_id==='study_notes'){
    body+=`<div class="irow"><span class="ik">Эффект</span><span style="color:var(--gold)">+50% XP · 4ч</span></div>`;
    if(quantity>0)btns.unshift({l:'📚 Активировать',c:'btn-gold',f:`useConsumable('${item_id}')`});
  }
  OM(name,body,btns);
}
function useConsumable(iid) {
  api('/inventory/use',{method:'POST',body:JSON.stringify({item_id:iid})})
    .then(r=>{toast(r.message||'✅ Применено!');CM();loadInventory();if(_loaded.has('profile'))loadActiveBuffs();})
    .catch(e=>toast(e,false));
}
