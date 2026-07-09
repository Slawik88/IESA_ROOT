// ═══ app.11.js — Боёвка 3.0 «Руны отряда»: Казарма + Врата + арена ═══
// Сервер-авторитарно: клиент шлёт порядок рун/цели/сырой tap_offset_ms,
// всю математику (криты/ярость/перехваты/стихии) считает бэкенд (battle3.py).
let _bkData=null, _bkPickSlot=null;
let _b3St=null, _b3Order=[], _b3Target=0, _b3QteStart=0, _b3Lock=false, _b3LastReward=null;

const B3_EL_ICO={fire:'🔥',ice:'❄️',storm:'⚡',earth:'🗿',dark:'🌑'};
const B3_ROLE_ICO={dd:'⚔️',tank:'🛡',support:'💚'};
const B3_SLOT_NAMES=['Фронт','Фланг','Тыл'];
const B3_INTENT_ICO={atk:'⚔️',def:'🛡',heal:'💚',ult:'💥',aoe:'💥',frozen:'❄️'};
const B3_FX_ICO={burn:'🔥',frozen:'🧊',stunned:'💫',reflect:'↩️',regen:'🌿',weaken:'⛓',
  invuln:'🛡',intercept_all:'🧲',web:'🕸',armor_break:'🪨',dmg_bonus:'📈'};

// ── Казарма ───────────────────────────────────────────────────────────────────
function loadBarracks(){
  const host=el('bkc'); if(host)host.innerHTML='<div class="loader">Загрузка Казармы...</div>';
  api('/barracks').then(d=>{_bkData=d;renderBarracks();})
    .catch(e=>{if(el('bkc'))el('bkc').innerHTML=`<div class="err">${e}</div>`;});
}
function renderBarracks(){
  const host=el('bkc'); if(!host||!_bkData) return;
  const d=_bkData;
  if(d.starter_available){ host.innerHTML=_bkStarterHtml(d); return; }
  const byId={}; d.units.forEach(u=>byId[u.unit_id]=u);
  // Отряд: 3 слота-позиции
  const slots=[0,1,2].map(s=>{
    const uid=d.squad[String(s)];
    const u=uid?byId[uid]:null;
    return `<button class="bk-slot ${u?'r-'+u.rarity:''}" onclick="_bkPickForSlot(${s})">
      <div class="bk-slot-t">${B3_SLOT_NAMES[s]}</div>
      ${u?`<div class="bk-slot-e">${u.emoji}</div>
           <div class="bk-slot-n">${esc(u.name)}</div>
           <div class="bk-slot-s">${u.element_emoji}${B3_ROLE_ICO[u.role]} ур.${u.level}</div>`
         :`<div class="bk-slot-e bk-slot-empty">➕</div><div class="bk-slot-n cx-dim">пусто</div>`}
    </button>`;
  }).join('');
  // Синергия-подсказка
  const squadUnits=[0,1,2].map(s=>byId[d.squad[String(s)]]).filter(Boolean);
  const els=squadUnits.map(u=>u.element).filter(Boolean);
  let syn='';
  if(new Set(els).size<els.length) syn='✨ Синергия стихии активна';
  else if(els.length===3 && new Set(els).size===3) syn='🌈 «Триада»: бесплатная комбо-руна раз в бой';
  const owned=d.units.filter(u=>u.owned);
  const locked=d.units.filter(u=>!u.owned);
  host.innerHTML=`
    <div class="looks-hint">🏰 <b>Казарма</b> — боевые юниты. Каждый приносит в бой 3 руны:
      ⚔️ удар · 🛡 защита · ✨ навык. Собери отряд из 3 (позиция важна: фронт перехватывает
      удары по тылу). Призыв — за 💠 Осколки Бездны (Врата, Бездна кланов).</div>
    <div class="looks-slot-t">⚔️ Отряд · сила ⚡${fmt(d.squad_cp)} ${syn?`· <span style="color:var(--gold2)">${syn}</span>`:''}</div>
    <div class="bk-squad">${slots}</div>
    <button class="btn btn-gold btn-full" style="margin:8px 0" onclick="_bkSummon(this)">
      🔮 Призыв юнита — ${d.summon_cost} 💠 <span class="cx-dim">(у тебя ${fmt(d.shards)})</span></button>
    <div class="looks-slot-t">📖 Мои юниты (${d.owned_count}/16)</div>
    <div class="bk-grid">${owned.map(u=>_bkCard(u)).join('')||'<div class="cx-dim" style="padding:6px;font-size:11px">Пока никого — призови первого!</div>'}</div>
    ${locked.length?`<div class="looks-slot-t">🔒 Ещё не открыты</div>
    <div class="bk-grid">${locked.map(u=>_bkCard(u)).join('')}</div>`:''}
    <div class="cx-dim" style="font-size:10px;margin-top:8px;line-height:1.5">Дубль в призыве → осколки юнита.
      Осколки качают уровень (+12% статов) и открывают юнита напрямую. Таргет-осколки падают с боссов Бездны и этажей Врат 5–6.</div>`;
}
function _bkStarterHtml(d){
  const byId={}; d.units.forEach(u=>byId[u.unit_id]=u);
  const cards=(d.starter_choices||[]).map(id=>{
    const u=byId[id]; if(!u) return '';
    return `<div class="bk-starter r-${u.rarity}">
      <div class="bk-slot-e">${u.emoji}</div>
      <div class="bk-slot-n">${esc(u.name)}</div>
      <div class="bk-slot-s">${u.element_emoji} ${esc(u.element_name)} · ${B3_ROLE_ICO[u.role]} ${esc(u.role_name)}</div>
      <div class="bk-starter-sk">✨ ${esc(u.skill.name)}: ${esc(u.skill.desc)}</div>
      <button class="btn btn-gold btn-full btn-sm" onclick="_bkStarterPick('${u.unit_id}',this)">Выбрать</button>
    </div>`;
  }).join('');
  return `<div class="looks-hint">🏰 <b>Добро пожаловать в Казарму!</b> Мирные питомцы теперь заняты
    экономикой — сражаются <b>боевые юниты</b>. Выбери первого бойца (остальных
    призовёшь за 💠 Осколки Бездны):</div>
    <div class="bk-starter-row">${cards}</div>`;
}
function _bkStarterPick(uid,btn){
  if(btn)btn.disabled=true;
  api('/barracks/starter',{method:'POST',body:JSON.stringify({unit_id:uid})})
    .then(r=>{_haptic('success');toast(r.message);loadBarracks();})
    .catch(e=>{toast(e,false);if(btn)btn.disabled=false;});
}
function _bkCard(u){
  const lvl=u.owned?`ур.${u.level}`:'—';
  let foot='';
  if(u.owned){
    const inSq=u.squad_slot!==null&&u.squad_slot!==undefined;
    foot=`${u.next_level_shards!==null&&u.next_level_shards!==undefined
      ?`<button class="btn btn-sm ${u.shards>=u.next_level_shards?'btn-gold':'btn-ghost'}" onclick="event.stopPropagation();_bkLevelUp('${u.unit_id}',this)">⬆ ${u.shards}/${u.next_level_shards}◈</button>`
      :'<span class="cx-dim" style="font-size:10px">★ макс</span>'}
      ${inSq?`<span class="bk-insq">${B3_SLOT_NAMES[u.squad_slot]}</span>`:''}`;
  } else {
    foot=u.shards>=(u.unlock_shards||99)
      ?`<button class="btn btn-sm btn-gold" onclick="event.stopPropagation();_bkUnlock('${u.unit_id}',this)">🔓 Открыть</button>`
      :`<span class="cx-dim" style="font-size:10px">◈ ${u.shards}/${u.unlock_shards}</span>`;
  }
  return `<div class="bk-card r-${u.rarity}${u.owned?'':' bk-locked'}" onclick="_bkInfo('${u.unit_id}')">
    <div class="bk-card-e">${u.emoji}</div>
    <div class="bk-card-n">${esc(u.name)}</div>
    <div class="bk-card-s">${u.element_emoji}${B3_ROLE_ICO[u.role]} ${lvl}</div>
    <div class="bk-card-f">${foot}</div>
  </div>`;
}
function _bkInfo(uid){
  const u=(_bkData?.units||[]).find(x=>x.unit_id===uid); if(!u) return;
  const inSq=u.squad_slot!==null&&u.squad_slot!==undefined;
  OM(`${u.emoji} ${esc(u.name)}`,`
    <div class="bk-info-head r-${u.rarity}">
      <span>${u.element_emoji} ${esc(u.element_name)}</span>
      <span>${B3_ROLE_ICO[u.role]} ${esc(u.role_name)}</span>
      <span>${_rarLabel?_rarLabel(u.rarity):u.rarity}</span>
      ${u.owned?`<span>ур.${u.level}</span>`:'<span>🔒 не открыт</span>'}
    </div>
    <div class="irow"><span class="ik">⚔️ Атака</span><span class="iv">${u.atk}</span></div>
    <div class="irow"><span class="ik">🛡 Защита</span><span class="iv">${u.def}</span></div>
    <div class="irow"><span class="ik">❤️ Здоровье</span><span class="iv">${u.hp}</span></div>
    ${u.owned?`<div class="irow"><span class="ik">⚡ Сила (CP)</span><span class="iv" style="color:var(--gold2)">${fmt(u.cp)}</span></div>`:''}
    <div class="looks-slot-t" style="margin-top:8px">✨ ${esc(u.skill.name)} (руна навыка)</div>
    <div class="cx-dim" style="font-size:11px">${esc(u.skill.desc)}</div>
    <div class="looks-slot-t" style="margin-top:6px">💥 ${esc(u.ult.name)} (ульта, ярость 100)</div>
    <div class="cx-dim" style="font-size:11px">${esc(u.ult.desc)}</div>
    ${u.owned&&u.next_level_shards?`<div class="cx-dim" style="font-size:10px;margin-top:8px">След. уровень: ${u.next_level_shards} осколков (есть ${u.shards}) + ${fmt(u.next_level_mora)} 🪙</div>`:''}
  `,[
    ...(u.owned?[{l:inSq?'❌ Убрать из отряда':'⚔️ В отряд',c:inSq?'btn-ghost':'btn-gold',
      f:inSq?`_bkSquadRemove('${u.unit_id}')`:`_bkPickSlotFor('${u.unit_id}')`}]:[]),
    {l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}
function _bkSummon(btn){
  if(btn)btn.disabled=true;
  api('/barracks/summon',{method:'POST'})
    .then(r=>{
      _haptic(r.duplicate?'medium':'success');
      OM('🔮 Призыв',`<div class="bk-summon-res r-${r.rarity}">
        <div class="bk-summon-e">${r.emoji}</div>
        <div class="bk-slot-n" style="font-size:15px">${esc(r.name)}</div>
        <div class="bk-slot-s">${r.element_emoji} · ${esc(r.role_name)} · ${_rarLabel?_rarLabel(r.rarity):r.rarity}</div>
        <div style="margin-top:6px;font-size:12px">${r.duplicate?`Дубль → <b>+${r.shards} ◈ осколков</b> юнита`:'<b>НОВЫЙ ЮНИТ!</b> 🎉'}</div>
      </div>`,[{l:'🔮 Ещё раз',c:'btn-gold',f:'CM();_bkSummon()'},{l:'Готово',c:'btn-ghost',f:'CM();loadBarracks()'}]);
      loadBarracks(); refreshCurrBar&&refreshCurrBar();
    })
    .catch(e=>{toast(e,false);if(btn)btn.disabled=false;});
}
function _bkLevelUp(uid,btn){
  if(btn)btn.disabled=true;
  api('/barracks/levelup',{method:'POST',body:JSON.stringify({unit_id:uid})})
    .then(r=>{_haptic('success');toast(r.message);loadBarracks();})
    .catch(e=>{toast(e,false);if(btn)btn.disabled=false;});
}
function _bkUnlock(uid,btn){
  if(btn)btn.disabled=true;
  api('/barracks/unlock',{method:'POST',body:JSON.stringify({unit_id:uid})})
    .then(r=>{_haptic('success');toast(r.message);loadBarracks();})
    .catch(e=>{toast(e,false);if(btn)btn.disabled=false;});
}
function _bkPickForSlot(slot){
  _bkPickSlot=slot;
  const d=_bkData; if(!d) return;
  const owned=d.units.filter(u=>u.owned);
  const cur=d.squad[String(slot)];
  const items=owned.map(u=>`<div class="fopt" onclick="_bkSetSlot('${u.unit_id}')">
      ${u.emoji} ${esc(u.name)} · ${u.element_emoji}${B3_ROLE_ICO[u.role]} ур.${u.level}
      ${u.squad_slot!==null&&u.squad_slot!==undefined?`<span class="cx-dim">(${B3_SLOT_NAMES[u.squad_slot]})</span>`:''}
    </div>`).join('')||'<div class="cx-dim" style="padding:8px">Нет юнитов — призови в Казарме.</div>';
  OM(`${B3_SLOT_NAMES[slot]} — кто встанет?`,`${items}
    ${cur?`<div class="fopt" style="color:var(--red,#e05252)" onclick="_bkSetSlot(null)">❌ Освободить слот</div>`:''}`,
    [{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _bkPickSlotFor(uid){
  CM();
  const d=_bkData; if(!d) return;
  // юнит в первый свободный слот, иначе — в фронт
  let slot=0;
  for(let s=0;s<3;s++){ if(!d.squad[String(s)]){slot=s;break;} }
  _bkPickSlot=slot;
  _bkSetSlot(uid);
}
function _bkSetSlot(uid){
  CM();
  const d=_bkData; if(!d||_bkPickSlot===null) return;
  const slots={...d.squad};
  // если юнит стоял в другом слоте — бэкенд сам уберёт дубль, но пошлём чисто
  Object.keys(slots).forEach(k=>{ if(uid&&slots[k]===uid) slots[k]=null; });
  slots[String(_bkPickSlot)]=uid;
  api('/barracks/squad',{method:'POST',body:JSON.stringify({slots})})
    .then(()=>{_haptic('light');loadBarracks();})
    .catch(e=>toast(e,false));
}
function _bkSquadRemove(uid){
  CM();
  const d=_bkData; if(!d) return;
  const slots={...d.squad};
  Object.keys(slots).forEach(k=>{ if(slots[k]===uid) slots[k]=null; });
  api('/barracks/squad',{method:'POST',body:JSON.stringify({slots})})
    .then(()=>{_haptic('light');loadBarracks();})
    .catch(e=>toast(e,false));
}

// ── Врата (лобби) ─────────────────────────────────────────────────────────────
function loadGates(){
  const host=el('gtc'); if(host)host.innerHTML='<div class="loader">Загрузка Врат...</div>';
  api('/combat2/gates').then(d=>{
    if(d.active_battle){ _btBackFn=loadGates; _btRender(d.active_battle); return; }
    const host2=el('gtc'); if(!host2) return;
    const squad=(d.squad||[]).map(s=>`<span class="bk-chip">${s.emoji} ${esc(s.name)} · ур.${s.level}</span>`).join('');
    const lo=d.loot||{};
    const floors=(d.floors||[]).map(f=>`<div class="g2-floor${f.open?'':' locked'}">
        <span class="g2-fn">Этаж ${f.floor} <span class="cx-dim">· врагов: ${f.enemies}${f.unit_shards?` · ◈ ${lo.unit_shard_chance_pct||35}% шанс ${(lo.unit_shard_range||[1,2]).join('–')} осколков юнита`:''}</span></span>
        <span class="g2-fr">+${f.reward_dark} 🌑</span>
        ${f.open
          ? `<button class="btn btn-sm btn-gold" ${d.entries_left<=0||!(d.squad||[]).length?'disabled':''} onclick="_gtEnter(${f.floor},this)">⚔️ Войти</button>`
          : `<span class="g2-lock">🔒 ⚡${fmt(f.cp_gate)}</span>`}
      </div>`).join('');
    host2.innerHTML=`
      <div class="looks-hint">🌑 <b>Врата</b> — бой отрядом: раздача рун, порядок решает.
        Победа: Тёмная Мора + ${lo.shard_chance_pct||20}% шанс ${(lo.shard_range||[1,3]).join('–')} 💠,
        на этажах 5–6 — ещё и осколки юнитов (см. ниже).
        Входов сегодня: <b>${d.entries_left}</b> · Твоя Сила: ⚡${fmt(d.cp)}.</div>
      ${squad?`<div class="looks-slot-t">⚔️ Отряд (⚡${fmt(d.squad_cp)})</div><div class="bk-chips">${squad}</div>`
        :`<div class="cx-dim" style="font-size:11px">Отряда нет.</div>
          <button class="btn btn-sm btn-gold" style="margin-top:4px" onclick="goTo('arena','barracks')">🏰 Собрать отряд</button>`}
      <div class="looks-slot-t" style="margin-top:8px">🗼 Этажи</div>${floors}`;
  }).catch(e=>{if(el('gtc'))el('gtc').innerHTML=`<div class="err">${e}</div>`;});
}
function _gtEnter(floor,btn){
  if(btn)btn.disabled=true;
  _btBackFn=loadGates;
  api('/combat2/gates/enter',{method:'POST',body:JSON.stringify({floor})})
    .then(st=>{_haptic('medium');_btRender(st);})
    .catch(e=>{toast(e,false);if(btn)btn.disabled=false;});
}

// ── АРЕНА: полноэкранный бой ──────────────────────────────────────────────────
function _b3Ov(){
  let ov=el('b3-ov');
  if(!ov){
    ov=document.createElement('div');
    ov.id='b3-ov'; ov.className='b3-ov';
    document.body.appendChild(ov);
  }
  ov.style.display='flex';
  return ov;
}
function _b3Close(){ const ov=el('b3-ov'); if(ov)ov.style.display='none'; _b3St=null; }
function _btRender(st, turn, reward){
  // Совместимое имя: сюда приходят Врата/Бездна/Войны (app.02/app.11).
  // Порядок рун сбрасывается только на НОВОМ состоянии с сервера —
  // локальные ре-рендеры (выбор цели/порядка) его сохраняют.
  if(st!==_b3St) _b3Order=[];
  _b3St=st; _b3Lock=false;
  if(reward!==undefined) _b3LastReward=reward;
  if(st.reward!==undefined&&st.reward!==null) _b3LastReward=st.reward;
  const ov=_b3Ov();
  const finished=st.status==='won'||st.status==='lost';
  const alive=(st.enemy.units||[]).map((u,i)=>({u,i})).filter(x=>x.u.alive);
  if(!alive.find(x=>x.i===_b3Target)) _b3Target=alive.length?alive[0].i:0;
  // Телеграф по юнитам
  const intentOf={};
  (st.enemy.intents||[]).forEach(it=>{intentOf[it.i]=it;});
  const eCards=(st.enemy.units||[]).map((u,i)=>{
    const it=intentOf[i];
    const fx=(u.fx||[]).map(f=>B3_FX_ICO[f]||'').join('');
    return `<button class="b3-card b3-en ${u.alive?'':'b3-dead'} ${i===_b3Target&&u.alive?'b3-tgt':''} ${u.boss?'b3-boss':''}"
      onclick="_b3SetTarget(${i})">
      ${it&&u.alive?`<div class="b3-intent" title="намерение">${B3_INTENT_ICO[it.kind]||'❔'}${it.kind==='atk'&&it.t!==undefined&&it.t!==null?'→'+((st.ally.units[it.t]||{}).emoji||''):''}</div>`:''}
      <div class="b3-card-e">${u.emoji}</div>
      <div class="b3-card-n">${u.element_emoji||''}${esc(u.name)}</div>
      <div class="bt-bar"><div class="bt-fill hp en" style="width:${(u.hp/u.hp_max*100).toFixed(0)}%"></div></div>
      <div class="b3-hp">${fmt(u.hp)}/${fmt(u.hp_max)}${u.shield?` 🛡${fmt(u.shield)}`:''} ${fx}</div>
    </button>`;
  }).join('');
  const aCards=(st.ally.units||[]).map((u,i)=>{
    const fx=(u.fx||[]).map(f=>B3_FX_ICO[f]||'').join('');
    const ultReady=st.ally.rage>=100&&u.alive&&!finished&&!st.pending;
    return `<div class="b3-card b3-al ${u.alive?'':'b3-dead'}">
      <div class="b3-card-e">${u.emoji}</div>
      <div class="b3-card-n">${u.element_emoji||''}${esc(u.name)}</div>
      <div class="bt-bar"><div class="bt-fill hp" style="width:${(u.hp/u.hp_max*100).toFixed(0)}%"></div></div>
      <div class="b3-hp">${fmt(u.hp)}/${fmt(u.hp_max)}${u.shield?` 🛡${fmt(u.shield)}`:''} ${fx}</div>
      ${ultReady?`<button class="b3-ult-btn" onclick="_b3Ult(${i})" title="${esc(u.ult_desc||'')}">💥 ${esc(u.ult_name||'УЛЬТА')}</button>`:''}
    </div>`;
  }).join('');
  const rageA=Math.min(100,st.ally.rage||0), rageE=Math.min(100,st.enemy.rage||0);
  // Рука рун
  const hand=(st.hand||[]).map((r,i)=>{
    const ord=_b3Order.indexOf(i);
    return `<div class="b3-rune ${r.forced_crit?'b3-fcrit':''} ${ord>=0?'b3-ord':''}" onclick="_b3TapRune(${i})">
      ${ord>=0?`<div class="b3-ord-n">${ord+1}</div>`:''}
      <div class="b3-rune-e">${r.emoji}<span class="b3-rune-ue">${r.unit_emoji}</span></div>
      <div class="b3-rune-l">${esc(r.label)}</div>
      ${r.k==='skill'?`<div class="b3-rune-d">${esc((r.desc||'').slice(0,42))}</div>`:''}
      ${!finished&&!st.pending?`<div class="b3-rune-acts">
        <button class="b3-ract" onclick="event.stopPropagation();_b3Reroll(${i})" title="переброс (1🧿)">🔄1</button>
        ${r.k==='atk'&&!r.forced_crit?`<button class="b3-ract" onclick="event.stopPropagation();_b3FCrit(${i})" title="гарант-крит (2🧿)">🎯2</button>`:''}
      </div>`:''}
    </div>`;
  }).join('');
  const grade=turn&&turn.grade;
  let headHtml='';
  if(finished){
    const rw=_b3LastReward;
    let rwTxt='';
    if(st.status==='won'&&rw){
      if(rw.dark_mora!==undefined) rwTxt=`+${rw.dark_mora} 🌑${rw.shards?` · +${rw.shards} 💠`:''}`;
      else if(rw.split) rwTxt=`+${rw.shards} 💠 (${rw.split.treasury} в казну${rw.boss_key?' · 🗝 ключ этажа':''})`;
      else if(rw.damage!==undefined) rwTxt=`урон стене: ${fmt(rw.damage)}${rw.breached?' · 🏰 УЗЕЛ ЗАХВАЧЕН!':` (${fmt(rw.wall_total)}/${fmt(rw.wall_hp_max)})`}`;
      if(rw.unit_shards) rwTxt+=` · ${rw.unit_shards.emoji} +${rw.unit_shards.n}◈ ${esc(rw.unit_shards.name)}`;
    }
    headHtml=st.status==='won'
      ?`<div class="skg-head skg-won">🏆 ПОБЕДА! ${rwTxt}</div>`
      :`<div class="skg-head skg-lost">☠️ Отряд пал. Юниты восстановятся к следующему бою.</div>`;
  }
  const qte=st.qte&&st.pending;
  ov.innerHTML=`
    <div class="b3-top">
      <span class="b3-round">Раунд ${st.round}${st.escalation?` · 🔥+${Math.round(st.escalation*100)}%`:''} · колода: ${st.deck_left}</span>
      ${finished?'':`<div style="display:flex;gap:6px">
        <button class="b3-flee" onclick="_b3Cancel()">🚪 Выйти</button>
        <button class="b3-flee" onclick="_b3Flee()">🏳 Сдаться</button>
      </div>`}
    </div>
    <div class="b3-rage b3-rage-en"><div class="b3-rage-f" style="width:${rageE}%"></div><span>ярость врага ${rageE}</span></div>
    <div class="b3-row">${eCards}</div>
    ${grade?`<div class="bt-flash bt-flash-${grade}"></div>`:''}
    <div class="b3-mid">
      ${headHtml}
      ${qte?`<div class="bt-qte b3-qte" onclick="_b3QteTap()">
          <div class="bt-ring" id="b3-ring"></div>
          <div class="bt-ring-core">${st.pending.type==='ult'?'💥':'🎯'}</div>
          <div class="b3-qte-hint">${st.pending.type==='ult'?'УЛЬТА: жми в момент сжатия!':'КРИТ: жми в момент сжатия!'}</div>
        </div>`
      :finished?''
      :`<div class="b3-hand">${hand||'<div class="cx-dim" style="font-size:11px;padding:6px">Рука пуста</div>'}</div>
        <div class="b3-ctl">
          <span class="b3-focus" title="Фокус: 🔄 переброс руны (1) · 🎯 гарант-крит (2)">🧿 ${st.ally.focus}</span>
          ${st.ally.triad_available?`<button class="btn btn-sm btn-teal" onclick="_b3Triad(this)">🌈 Триада</button>`:''}
          <button class="btn btn-gold b3-go" ${_b3Order.length===(st.hand||[]).length&&(st.hand||[]).length>=0?'':'disabled'} onclick="_b3Play(this)">▶️ Ход (${_b3Order.length}/${(st.hand||[]).length})</button>
        </div>
        <div class="cx-dim" style="font-size:10px;text-align:center">Тапай руны в нужном порядке · цель — тап по врагу</div>`}
    </div>
    <div class="b3-rage"><div class="b3-rage-f b3-rage-my" style="width:${rageA}%"></div><span>твоя ярость ${rageA}${rageA>=100?' — УЛЬТА ГОТОВА!':''}</span></div>
    <div class="b3-row">${aCards}</div>
    <div class="bt-log b3-log">${(st.log||[]).slice(-6).map(l=>`<div>${esc(l)}</div>`).join('')}</div>
    ${finished?`<button class="btn btn-gold btn-full" style="margin-top:6px" onclick="_btBack()">↩ Назад</button>`:''}
  `;
  if(qte) _b3StartQte(st.qte);
}
function _b3SetTarget(i){
  if(!_b3St||!(_b3St.enemy.units[i]||{}).alive) return;
  _b3Target=i; _haptic('light');
  _btRender(_b3St);
}
function _b3TapRune(i){
  if(!_b3St||_b3St.pending) return;
  const p=_b3Order.indexOf(i);
  if(p>=0) _b3Order.splice(p,1); else _b3Order.push(i);
  _haptic('light');
  _btRender(_b3St);
}
function _b3Api(path, body, after){
  if(_b3Lock) return;
  _b3Lock=true;
  api(path,{method:'POST',body:JSON.stringify(body)})
    .then(r=>{
      _b3Lock=false;
      if(r.status==='won'){_haptic('success');refreshCurrBar&&refreshCurrBar();}
      else if(r.status==='lost')_haptic('error');
      (after||_btRender)(r, r.turn, r.reward);
    })
    .catch(e=>{_b3Lock=false;toast(e,false);});
}
function _b3Play(btn){
  if(!_b3St) return;
  if(_b3Order.length!==(_b3St.hand||[]).length){toast('Выбери порядок всех рун',false);return;}
  if(btn)btn.disabled=true;
  const targets={};
  _b3Order.forEach(hi=>{targets[String(hi)]=_b3Target;});
  _b3Api('/combat2/battle/round',{battle_id:_b3St.battle_id,order:_b3Order,targets});
  _b3Order=[];
}
function _b3StartQte(q){
  const ring=el('b3-ring'); if(!ring||!q) return;
  ring.style.animation='none'; void ring.offsetWidth;
  ring.style.animation=`btRing ${q.ring_ms}ms linear forwards`;
  _b3QteStart=Date.now();
  _b3St._ringMs=q.ring_ms;
}
function _b3QteTap(){
  if(!_b3St||!_b3St.pending) return;
  const elapsed=Date.now()-_b3QteStart;
  const off=Math.abs(elapsed-(_b3St._ringMs||1400));
  _b3Api('/combat2/battle/qte',{battle_id:_b3St.battle_id,tap_offset_ms:off},(r,turn)=>{
    const g=turn&&turn.grade;
    _haptic(g==='perfect'?'success':(g==='good'?'medium':'error'));
    _btRender(r,turn,r.reward);
  });
}
function _b3Ult(unitI){
  if(!_b3St) return;
  _b3Api('/combat2/battle/ult',{battle_id:_b3St.battle_id,unit_i:unitI});
}
function _b3Reroll(i){
  if(!_b3St) return;
  _b3Order=[];
  _b3Api('/combat2/battle/reroll',{battle_id:_b3St.battle_id,hand_i:i});
}
function _b3FCrit(i){
  if(!_b3St) return;
  _b3Api('/combat2/battle/focus-crit',{battle_id:_b3St.battle_id,hand_i:i});
}
function _b3Triad(btn){
  if(!_b3St) return;
  if(btn)btn.disabled=true;
  _b3Order=[];
  _b3Api('/combat2/battle/triad',{battle_id:_b3St.battle_id});
}
function _b3Flee(){
  if(!_b3St) return;
  OM('🏳 Сдаться?','<div style="font-size:12px;color:var(--muted)">Бой закончится поражением, вход будет потрачен.</div>',
    [{l:'🏳 Да, сдаться',c:'btn-red',f:'CM();_b3FleeGo()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _b3FleeGo(){
  if(!_b3St) return;
  _b3Api('/combat2/battle/flee',{battle_id:_b3St.battle_id});
}
function _b3Cancel(){
  if(!_b3St) return;
  OM('🚪 Выйти из боя?','<div style="font-size:12px;color:var(--muted)">Бой отменится будто его не было — без награды, но и без поражения. Вход дня всё равно будет потрачен.</div>',
    [{l:'🚪 Да, выйти',c:'btn-red',f:'CM();_b3CancelGo()'},{l:'Остаться',c:'btn-ghost',f:'CM()'}]);
}
function _b3CancelGo(){
  if(!_b3St||_b3Lock) return;
  _b3Lock=true;
  api('/combat2/battle/cancel',{method:'POST',body:JSON.stringify({battle_id:_b3St.battle_id})})
    .then(()=>{ _b3Lock=false; toast('🚪 Вышел из боя'); _btBack(); })
    .catch(e=>{ _b3Lock=false; toast(e,false); });
}
