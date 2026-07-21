// ═══ app.11.js — Боёвка 4.0 «Клеточная тактика»: Казарма + Врата + арена ═══
// Сервер-авторитарно: клиент шлёт действия (move/attack/skill/defend/end_turn) и
// сырой tap_offset_ms; всю математику (AP/дальность/LoS/криты/ярость/стихии/ИИ
// врага) считает бэкенд (battle3.py).
let _bkData=null, _bkPickSlot=null;
// Боёвка 4.0: клеточная арена. _b3Sel — индекс выбранного своего юнита (null=нет),
// _b3SkillMode — режим выбора цели навыка.
let _b3St=null, _b3Sel=null, _b3SkillMode=false, _b3QteStart=0, _b3Lock=false, _b3LastReward=null;
let _b3OutcomeShown=false, _b3Round=0;
// Онбординг боя: пошаговый проигрыватель «ленты хода врага». Пока идёт — доска на
// экране остаётся до-фазовой, мы анимируем DOM-токены; по завершении — один _btRender
// в финальное состояние. Тайминги зеркалят core/constants.py::B4_BEAT_*.
let _b3Playing=false, _b3PlayTimer=null, _b3PendingFinal=null, _b3SkipReq=false;
const B4_BEAT_MOVE_MS=300, B4_BEAT_HIT_MS=220, B4_BEAT_GAP_MS=180;
// Онбординг боя: коуч-слой скриптованного «Первого боя». Индекс текущего шага и
// стартовый суммарный HP врагов (веха «нанёс первый урон»). Мягкое ведение — шаги
// продвигаются по наблюдаемому состоянию, игрок волен действовать иначе.
let _b3CoachIdx=0, _b3CoachEnemyHp0=null;

const B3_EL_ICO={fire:'🔥',ice:'❄️',storm:'⚡',earth:'🗿',dark:'🌑'};
// BATTLE_VFX_CONCEPT.md (блок 2): цвет вспышек/чисел урона по стихии атакующего.
const B3_ELEMENT_COLORS={fire:'#ff7a3d',ice:'#5fc6ff',storm:'#f7e04a',earth:'#a97c50',dark:'#7a3bd6'};
const B3_ROLE_ICO={dd:'⚔️',tank:'🛡',support:'💚'};
const B3_SLOT_NAMES=['Фронт','Фланг','Тыл'];
const B3_FX_ICO={burn:'🔥',frozen:'🧊',stunned:'💫',reflect:'↩️',regen:'🌿',weaken:'⛓',
  invuln:'🛡',intercept_all:'🧲',web:'🕸',armor_break:'🪨',dmg_bonus:'📈',
  counter:'🥊',def_up:'🛡',chill_aura:'❄️'};
// Боёвка 4.0: рельеф клеток (grid: 0 пусто, 1 препятствие, 2 укрытие, 3 опасная)
// и иконки намерений врага (intents.kind).
const B4_TERR={1:['b4-obstacle','🌲'],2:['b4-cover','🪨'],3:['b4-danger','🔥']};
const B4_THREAT_ICO={atk:'⚔️',defend:'🛡',aoe:'💥',ult:'🔥💥'};

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
  else if(els.length===3 && new Set(els).size===3) syn='🌈 «Триада»: бесплатный AoE-удар по всем врагам раз в бой';
  const owned=d.units.filter(u=>u.owned);
  const locked=d.units.filter(u=>!u.owned);
  host.innerHTML=`
    <div class="looks-hint"><button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px;margin-left:6px" onclick="_b3IntroOpen('barracks')" aria-label="Обучение">❓</button>
      🏰 <b>Казарма</b> — боевые юниты. Собери отряд из 3: в бою они ходят по клеткам
      (⚡ AP на шаг/атаку/навык/защиту), позиция и укрытия решают. Призыв — за 🔷
      Осколки Бездны (Врата, Бездна кланов).</div>
    <div class="looks-slot-t">⚔️ Отряд · сила ⚡${fmt(d.squad_cp)} ${syn?`· <span style="color:var(--gold2)">${syn}</span>`:''}</div>
    <div class="bk-squad">${slots}</div>
    <button class="btn btn-gold btn-full" style="margin:8px 0" onclick="_bkSummon(this)">
      🔮 Призыв юнита — ${d.summon_cost} 🔷 <span class="cx-dim">(у тебя ${fmt(d.shards)})</span></button>
    <div class="looks-slot-t">📖 Мои юниты (${d.owned_count}/16)</div>
    <div class="bk-grid">${owned.map(u=>_bkCard(u)).join('')||'<div class="cx-dim" style="padding:6px;font-size:11px">Пока никого — призови первого!</div>'}</div>
    ${locked.length?`<div class="looks-slot-t">🔒 Ещё не открыты</div>
    <div class="bk-grid">${locked.map(u=>_bkCard(u)).join('')}</div>`:''}
    <div class="cx-dim" style="font-size:10px;margin-top:8px;line-height:1.5">Дубль в призыве → осколки юнита.
      Осколки качают уровень (+12% статов) и открывают юнита напрямую. Таргет-осколки падают с боссов Бездны и этажей Врат 5–6,
      а нужного юнита можно качать направленно: 🔷 Гравировка в карточке юнита (${d.engrave_cost} 🔷 → +${d.engrave_shards} ◈).</div>`;
  _b3ShowIntro('barracks');
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
    призовёшь за 🔷 Осколки Бездны):</div>
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
    <div class="looks-slot-t" style="margin-top:8px">✨ ${esc(u.skill.name)} (навык · 3 AP)</div>
    <div class="cx-dim" style="font-size:11px">${esc(u.skill.desc)}</div>
    <div class="looks-slot-t" style="margin-top:6px">💥 ${esc(u.ult.name)} (ульта, ярость 100)</div>
    <div class="cx-dim" style="font-size:11px">${esc(u.ult.desc)}</div>
    ${u.owned&&u.next_level_shards?`<div class="cx-dim" style="font-size:10px;margin-top:8px">След. уровень: ${u.next_level_shards} осколков (есть ${u.shards}) + ${fmt(u.next_level_mora)} 🪙</div>`:''}
    <div class="cx-dim" style="font-size:10px;margin-top:4px">🔷 Гравировка: ${_bkData?.engrave_cost||25} 🔷 → +${_bkData?.engrave_shards||4} ◈ осколка именно этого юнита (у тебя ${fmt(_bkData?.shards||0)} 🔷).</div>
  `,[
    ...(u.owned?[{l:inSq?'❌ Убрать из отряда':'⚔️ В отряд',c:inSq?'btn-ghost':'btn-gold',
      f:inSq?`_bkSquadRemove('${u.unit_id}')`:`_bkPickSlotFor('${u.unit_id}')`}]:[]),
    {l:`🔷 Гравировка ×${_bkData?.engrave_shards||4}◈`,c:'btn-ghost',f:`_bkEngrave('${u.unit_id}')`},
    {l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}
function _bkEngrave(uid){
  api('/barracks/engrave',{method:'POST',body:JSON.stringify({unit_id:uid})})
    .then(r=>{_haptic('success');toast(r.message);CM();loadBarracks();refreshCurrBar&&refreshCurrBar();})
    .catch(e=>toast(e,false));
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
      <div class="looks-hint"><button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px;margin-left:6px" onclick="_b3IntroOpen('gates')" aria-label="Обучение">❓</button>
        🌑 <b>Врата</b> — бой отрядом на клеточном поле: позиция и AP решают.
        Победа: Тёмная Мора + ${lo.shard_chance_pct||20}% шанс ${(lo.shard_range||[1,3]).join('–')} 🔷,
        на этажах 5–6 — ещё и осколки юнитов (см. ниже).
        Входов сегодня: <b>${d.entries_left}</b> · Твоя Сила: ⚡${fmt(d.cp)}.</div>
      ${d.tutorial_done===false
        ? `<button class="btn btn-gold btn-full" style="margin:8px 0" onclick="_gtTutorialStart(this)">▶ Пройти обучение «Первый бой»</button>`
        : `<button class="btn btn-sm btn-ghost" style="margin:6px 0" onclick="_gtTutorialStart(this)">🎓 Пройти обучение заново</button>`}
      ${squad?`<div class="looks-slot-t">⚔️ Отряд (⚡${fmt(d.squad_cp)})</div><div class="bk-chips">${squad}</div>`
        :`<div class="cx-dim" style="font-size:11px">Отряда нет.</div>
          <button class="btn btn-sm btn-gold" style="margin-top:4px" onclick="goTo('arena','barracks')">🏰 Собрать отряд</button>`}
      <div class="looks-slot-t" style="margin-top:8px">🗼 Этажи</div>${floors}`;
    _b3ShowIntro('gates');
  }).catch(e=>{if(el('gtc'))el('gtc').innerHTML=`<div class="err">${e}</div>`;});
}

// ── UX_AUDIT С3: обучение Боёвки 3.0 — один раз при первом входе + кнопка «❓» ──
function _b3ShowIntro(kind){
  try{
    if(localStorage.getItem('pv_b3_intro_'+kind)) return;
    localStorage.setItem('pv_b3_intro_'+kind,'1');
  }catch(e){ return; }
  _b3IntroOpen(kind);
}
function _b3IntroOpen(kind){
  const steps = kind==='barracks'
    ? ['1️⃣ <b>Призови юнитов</b> за 🔷 и собери отряд из трёх — они выходят на поле боя.',
       '2️⃣ <b>Каждый юнит ходит по клеткам</b>: очки действий (AP) тратятся на шаг, атаку, навык и защиту. Позиция решает.',
       '3️⃣ <b>Качай юнитов осколками</b> — дубли призыва, боссы, 🔷 Гравировка. Растёт сила ⚡ отряда.']
    : ['1️⃣ <b>Тапни своего юнита</b> — подсветятся клетки хода и цели. Тап по клетке — шаг, тап по врагу — удар (в дальности).',
       '2️⃣ <b>Тактика решает</b>: прячься в укрытие (−30% урона), защищайся (−40%), бей врага без защиты (+25%). Кончились AP — «Конец хода».',
       '3️⃣ <b>Круг сжимается — жми в момент сжатия!</b> Так проходят криты и ульты (ярость 100). Промахнулся — будет обычный удар, не страшно.'];
  OM(kind==='barracks'?'🏰 Как устроена Казарма':'🌑 Как драться во Вратах',
    `<div style="display:flex;flex-direction:column;gap:8px;padding:4px 0">${steps.map(s=>`<div class="looks-hint" style="margin:0">${s}</div>`).join('')}</div>
     <div class="cx-dim" style="font-size:10px;margin-top:10px;text-align:center">Вернуться к этой подсказке: кнопка «❓» вверху раздела.</div>`,
    [{l:'Понятно, в бой!',c:'btn-gold',f:'CM()'}]);
}
function _gtEnter(floor,btn){
  if(btn)btn.disabled=true;
  _btBackFn=loadGates;
  api('/combat2/gates/enter',{method:'POST',body:JSON.stringify({floor})})
    .then(st=>{_haptic('medium');_btRender(st);})
    .catch(e=>{toast(e,false);if(btn)btn.disabled=false;});
}
// Онбординг боя: запуск/перезапуск скриптованного «Первого боя» (коуч-слой сам
// ведёт по вехам). Сбрасываем прогресс коуча перед стартом.
function _gtTutorialStart(btn){
  if(btn)btn.disabled=true;
  _btBackFn=loadGates;
  _b3CoachReset();
  api('/combat2/tutorial/start',{method:'POST'})
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
// Онбординг боя: постоянная легенда поля — доступна кнопкой «❓» в любой момент боя.
function _b3Legend(){
  OM('❓ Как читать поле', `<div class="b4-lg">
    <div class="b4-lg-sec">Клетки при выбранном бойце</div>
    <div class="b4-lg-row"><span class="b4-lg-ic b4-lg-reach"></span> Точка — куда можно шагнуть (⚡ AP на клетку)</div>
    <div class="b4-lg-row"><span class="b4-lg-ic b4-lg-atk"></span> Кольцо-прицел — враг в дальности удара</div>
    <div class="b4-lg-sec">Рельеф</div>
    <div class="b4-lg-row"><span class="b4-lg-terr">🪨</span> Укрытие — входящий урон −30%</div>
    <div class="b4-lg-row"><span class="b4-lg-terr">🔥</span> Опасная — теряешь HP в начале своего хода</div>
    <div class="b4-lg-row"><span class="b4-lg-terr">🌲</span> Препятствие — не пройти и не простреливается</div>
    <div class="b4-lg-sec">Намерение врага (над ним)</div>
    <div class="b4-lg-row">⚔️→ ударит по цели · 🛡 защита · 💥 удар по всем · 🔥💥 ульта</div>
    <div class="b4-lg-sec">Статусы на бойце</div>
    <div class="b4-lg-row">🔥 горение · 🧊 заморозка · 💫 оглушение · 🛡 щит · 🌿 реген · ⛓ ослабление · 🕸 паутина</div>
    <div class="b4-lg-sec">Шкалы</div>
    <div class="b4-lg-row">⚡ AP — очки действий: шаг / атака / навык / защита. Ярость 100 → 💥 ульта.</div>
  </div>`, [{l:'Понятно',c:'btn-gold',f:'CM()'}]);
}
// ── Онбординг боя: коуч-слой «Первого боя» (data-driven, мягкое ведение) ────────
function _b3EnemyHpSum(st){
  return ((st.enemy||{}).units||[]).reduce(function(s,u){ return s+(u.alive?u.hp:0); }, 0);
}
function _b3CoachReset(){ _b3CoachIdx=0; _b3CoachEnemyHp0=null; }
function _b3CoachSkip(){ _b3CoachIdx=9999; if(_b3St) _btRender(_b3St); }
// Возвращает текущий шаг обучения {text, hlSel, idx, total} или null. Шаги — по
// наблюдаемым вехам состояния (выбор → первый урон → конец хода → фаза врага → ярость).
function _b3CoachStep(st){
  if(!st || !st.tutorial || st.status==='lost') return null;
  if(_b3CoachEnemyHp0==null) _b3CoachEnemyHp0=_b3EnemyHpSum(st);
  const aUnits=(st.ally||{}).units||[];
  let firstAlly=-1;
  for(let i=0;i<aUnits.length;i++){ if(aUnits[i].alive){ firstAlly=i; break; } }
  const rage=(st.ally||{}).rage||0;
  const steps=[
    { text:'👆 <b>Тапни своего бойца</b> — подсветятся клетки хода и цели.',
      hl: firstAlly>=0?'#b4-tok-ally-'+firstAlly:null,
      done: _b3Sel!=null },
    { text:'🔵 Точки — куда <b>шагнуть</b>. 🎯 Кольцо-прицел — <b>враг в дальности</b>: тапни по нему, чтобы ударить.',
      hl: null,
      done: _b3EnemyHpSum(st) < _b3CoachEnemyHp0 },
    { text:'💡 Прячься в 🪨 укрытие (−30%), 🛡 <b>Защита</b> (−40%), бей открытого (+25%). Кончились ⚡AP — жми <b>«Конец хода»</b>.',
      hl: '.b4-endturn',
      done: (st.round||1) > 1 },
    { text:'👀 Вот как ходит <b>враг</b>: сначала намерение, потом шаг, потом удар. Продолжай — добивай врагов!',
      hl: null,
      done: rage>=100 || st.status==='won' },
    { text:'💥 <b>Ярость полна!</b> Выбери бойца и жми 💥 ульту — по кольцу тапни в момент сжатия.',
      hl: null,
      done: st.status==='won' },
  ];
  while(_b3CoachIdx<steps.length && steps[_b3CoachIdx].done) _b3CoachIdx++;
  if(_b3CoachIdx>=steps.length) return null;
  const s=steps[_b3CoachIdx];
  return { text:s.text, hlSel:s.hl, idx:_b3CoachIdx, total:steps.length };
}
function _btRender(st, turn, reward){
  // Боёвка 4.0: клеточная арена (Врата/Бездна/Войны — app.02/app.11).
  // Локальные ре-рендеры (выбор юнита/навыка) приходят с тем же объектом st →
  // выбор сохраняется. НОВОЕ состояние с сервера (st!==_b3St) = новый ход →
  // сбрасываем выбор и режим навыка.
  // Выбор юнита живёт в пределах СВОЕГО хода (AP-модель = несколько действий одним
  // юнитом: ход→атака). Сброс — на новом раунде (после фазы врага) или если юнит пал.
  // Режим навыка — транзиентный, сбрасывается на любом новом состоянии с сервера.
  if(st!==_b3St){
    _b3SkillMode=false;
    const selAlive=_b3Sel!=null && ((st.ally.units[_b3Sel]||{}).alive);
    if(st.round!==_b3Round || !selAlive) _b3Sel=null;
  }
  _b3Round=st.round;
  _b3St=st; _b3Lock=false;
  if(reward!==undefined) _b3LastReward=reward;
  if(st.reward!==undefined&&st.reward!==null) _b3LastReward=st.reward;
  const ov=_b3Ov();
  const finished=st.status==='won'||st.status==='lost';
  const grid=st.grid||[];
  const aUnits=st.ally.units||[], eUnits=st.enemy.units||[];

  // Кто на какой клетке (для рендера токенов и тап-логики)
  const occ={};
  aUnits.forEach((u,i)=>{ const p=u.pos||{}; occ[p.x+','+p.y]={side:'ally',i,u}; });
  eUnits.forEach((u,i)=>{ const p=u.pos||{}; occ[p.x+','+p.y]={side:'enemy',i,u}; });

  // Намерения врага → иконки угрозы + подсветка союзников-целей (упрощённо)
  const intentByEnemy={}, threatCells=new Set();
  (st.enemy.intents||[]).forEach(it=>{
    intentByEnemy[it.i]=it;
    if(it.kind==='atk'&&it.target!=null){
      const tp=(aUnits[it.target]||{}).pos; if(tp) threatCells.add(tp.x+','+tp.y);
    }
  });

  // Выбранный юнит → достижимые клетки (BFS) и атакуемые враги (chebyshev≤range)
  let reachSet=new Set(); const atkCells=new Set();
  const sel=(_b3Sel!=null)?aUnits[_b3Sel]:null;
  if(sel&&sel.alive&&!finished&&!st.pending){
    const occSet=new Set();
    aUnits.concat(eUnits).forEach(u=>{ if(u.alive&&u!==sel){ const p=u.pos||{}; occSet.add(p.x+','+p.y); } });
    reachSet=_b4Reach(grid, sel.pos.x, sel.pos.y, sel.ap||0, occSet);
    // Дальность цели: обычная атака — по роли (sel.range); целевой навык сервер
    // разрешает на chebyshev≤2 независимо от роли (см. _skill_target_ok), так что
    // в режиме навыка подсвечиваем врагов в радиусе 2.
    const _trng=_b3SkillMode?2:(sel.range||1);
    eUnits.forEach(u=>{ if(u.alive){ const p=u.pos||{};
      if(Math.max(Math.abs(p.x-sel.pos.x),Math.abs(p.y-sel.pos.y))<=_trng) atkCells.add(p.x+','+p.y); } });
  }

  // Сетка 7×5
  let cells='';
  for(let y=0;y<grid.length;y++){
    for(let x=0;x<(grid[y]||[]).length;x++){
      const terr=B4_TERR[grid[y][x]];
      const key=x+','+y, o=occ[key];
      let cls='b4-cell';
      if(terr) cls+=' '+terr[0];
      if((!o||!o.u.alive)&&reachSet.has(key)) cls+=' b4-reach';
      if(o&&o.side==='enemy'&&o.u.alive&&atkCells.has(key)) cls+=' b4-atk';
      if(o&&o.side==='ally'&&threatCells.has(key)) cls+=' b4-threat';
      let inner=terr?`<span class="b4-terr">${terr[1]}</span>`:'';
      if(o){
        const u=o.u, side=o.side, pct=Math.max(0,Math.min(100,u.hp/u.hp_max*100)).toFixed(0);
        const isSel=side==='ally'&&o.i===_b3Sel;
        const fx=((u.shield?['🛡'+fmt(u.shield)]:[]).concat((u.fx||[]).map(f=>B3_FX_ICO[f]||''))).join(' ');
        let threat='';
        if(side==='enemy'&&u.alive&&intentByEnemy[o.i]){
          const it=intentByEnemy[o.i];
          const tgtE=(it.kind==='atk'&&it.target!=null)?'→'+((aUnits[it.target]||{}).emoji||''):'';
          threat=`<span class="b4-threat-l">${B4_THREAT_ICO[it.kind]||'❔'}${tgtE}</span>`;
        }
        inner+=`<span class="b4-tok b4-${side} ${u.alive?'':'b4-dead'} ${u.boss?'b4-boss':''} ${isSel?'b4-sel':''} ${u.defending?'b4-def':''}" id="b4-tok-${side}-${o.i}">
          ${threat}${u.element_emoji?`<span class="b4-el">${u.element_emoji}</span>`:''}
          <span class="b4-emoji">${u.emoji}</span>
          ${fx?`<span class="b4-fx">${fx}</span>`:''}
          <span class="b4-hpbar"><span class="b4-hpfill ${side==='enemy'?'en':''}" style="width:${pct}%"></span></span>
        </span>`;
      }
      cells+=`<div class="${cls}" data-cell="${x}-${y}" onclick="_b3TapCell(${x},${y})">${inner}</div>`;
    }
  }

  const rageA=Math.min(100,st.ally.rage||0), rageE=Math.min(100,st.enemy.rage||0);
  const grade=turn&&turn.grade;

  // Итог боя + награда
  let headHtml='';
  if(finished){
    const rw=_b3LastReward; let rwTxt='';
    if(st.status==='won'&&rw){
      if(rw.dark_mora!==undefined) rwTxt=`+${rw.dark_mora} 🌑${rw.shards?` · +${rw.shards} 🔷`:''}${rw.reward_mult&&rw.reward_mult>1?` · ⚡×${rw.reward_mult} за мастерство`:''}`;
      else if(rw.split) rwTxt=`+${rw.shards} 🔷 (${rw.split.treasury} в казну${rw.boss_key?' · 🗝 ключ этажа':''})`;
      else if(rw.damage!==undefined) rwTxt=`урон стене: ${fmt(rw.damage)}${rw.breached?' · 🏰 УЗЕЛ ЗАХВАЧЕН!':` (${fmt(rw.wall_total)}/${fmt(rw.wall_hp_max)})`}`;
      if(rw.unit_shards) rwTxt+=` · ${rw.unit_shards.emoji} +${rw.unit_shards.n}◈ ${esc(rw.unit_shards.name)}`;
    }
    headHtml=st.status==='won'
      ?`<div class="skg-head skg-won">🏆 ПОБЕДА! ${rwTxt}</div>`
      :`<div class="skg-head skg-lost">☠️ Отряд пал. Юниты восстановятся к следующему бою.</div>`;
  }

  const qte=st.qte&&st.pending;
  const apc=st.ap_costs||{};

  // Панель действий (AP) выбранного юнита + общий ряд (Триада/Конец хода)
  let actHtml='';
  if(!finished&&!qte){
    if(sel&&sel.alive){
      const rageReady=(st.ally.rage||0)>=100;
      const skillDis=(sel.ap||0)<(apc.skill||3)||(sel.skill_cd||0)>0;
      actHtml+=`<div class="b4-actions">
        <div class="b4-ap">${sel.emoji} ${esc(sel.name)} · ⚡ ${sel.ap||0}/${sel.ap_max||0} AP</div>
        <div class="b4-btns">
          <button class="btn btn-sm ${_b3SkillMode?'btn-teal':'btn-ghost'}" ${skillDis?'disabled':''}
            onclick="_b3SkillBtn()" title="${esc(sel.skill_desc||'')}">🎯 ${esc(sel.skill_name||'Навык')}${(sel.skill_cd||0)>0?` (${sel.skill_cd})`:''} · ${apc.skill||3}AP</button>
          <button class="btn btn-sm btn-ghost" ${(sel.ap||0)<(apc.defend||1)?'disabled':''} onclick="_b3Defend()">🛡 Защита · ${apc.defend||1}AP</button>
          ${rageReady?`<button class="btn btn-sm btn-gold" onclick="_b3Ult(${_b3Sel})" title="${esc(sel.ult_desc||'')}">💥 ${esc(sel.ult_name||'Ульта')}</button>`:''}
        </div>
        ${_b3SkillMode?`<div class="b4-hint">🎯 Выбери цель навыка (враг в дальности) — или тапни этого юнита для навыка на себя.</div>`:''}
      </div>`;
    } else {
      actHtml+=`<div class="b4-hint b4-hint-idle">👆 Тапни своего юнита — подсветятся ходы и цели.</div>`;
    }
    actHtml+=`<div class="b4-bar">
      ${st.ally.triad_available?`<button class="btn btn-sm btn-teal" onclick="_b3TriadAct()">🌈 Триада</button>`:''}
      <button class="btn btn-gold b4-endturn" onclick="_b3EndTurn()">↪ Конец хода</button>
    </div>`;
  }

  // Онбординг боя: коуч-пузырь скриптованного «Первого боя» (в потоке, над панелью
  // действий — не перекрывает кнопки). Подсветку цели вешаем после рендера.
  const coach = st.tutorial ? _b3CoachStep(st) : null;
  const coachHtml = coach ? `<div class="b4-coach">
      <button class="b4-coach-skip" onclick="_b3CoachSkip()">Пропустить обучение ✕</button>
      <div class="b4-coach-t"><span class="b4-coach-ic">🎓</span><span>${coach.text}</span></div>
      <div class="b4-coach-step">Шаг ${coach.idx+1} из ${coach.total}</div>
    </div>` : '';

  ov.innerHTML=`
    <div class="b3-top">
      <span class="b3-round">Раунд ${st.round}${st.escalation?` · 🔥+${Math.round(st.escalation*100)}%`:''}</span>
      <div style="display:flex;gap:6px">
        <button class="b3-flee" onclick="_b3Legend()" aria-label="Легенда боя">❓</button>
        ${finished?'':`<button class="b3-flee" onclick="_b3Cancel()">🚪 Выйти</button>
        <button class="b3-flee" onclick="_b3Flee()">🏳 Сдаться</button>`}
      </div>
    </div>
    <div class="b3-rage b3-rage-en"><div class="b3-rage-f" style="width:${rageE}%"></div><span>ярость врага ${rageE}</span></div>
    <div class="b4-grid">${cells}</div>
    ${grade?`<div class="bt-flash bt-flash-${grade}"></div>`:''}
    <div class="b3-rage"><div class="b3-rage-f b3-rage-my" style="width:${rageA}%"></div><span>твоя ярость ${rageA}${rageA>=100?' — УЛЬТА ГОТОВА!':''}</span></div>
    <div class="b4-mid">
      ${coachHtml}
      ${headHtml}
      ${qte?`<div class="bt-qte b3-qte" onclick="_b3QteTap()">
          <div class="bt-ring" id="b3-ring"></div>
          <div class="bt-ring-core">${st.pending.type==='ult'?'💥':'🎯'}</div>
          <div class="b3-qte-hint">${st.pending.type==='ult'?'УЛЬТА: жми в момент сжатия!':'КРИТ: жми в момент сжатия!'}</div>
        </div>`:actHtml}
    </div>
    <div class="bt-log b3-log">${(st.log||[]).slice(-6).map(l=>`<div>${esc(l)}</div>`).join('')}</div>
    ${finished?`<button class="btn btn-gold btn-full" style="margin-top:6px" onclick="_btBack()">↩ Назад</button>`:''}
  `;
  if(qte) _b3StartQte(st.qte);
  // Онбординг боя: подсвечиваем цель текущего шага обучения (токен/кнопка) — glow.
  if(coach && coach.hlSel){ const _hl=ov.querySelector(coach.hlSel); if(_hl) _hl.classList.add('b4-coach-hl'); }
  // BATTLE_VFX_CONCEPT.md (блок 2): бьём по СВЕЖЕ отрендеренным токенам.
  if(!finished) _b3OutcomeShown=false;
  if(turn&&turn.hits&&turn.hits.length) _b3PlayHitFx(turn.hits, grade&&grade!=='miss');
  if(finished&&!_b3OutcomeShown){
    _b3OutcomeShown=true;
    ov.classList.remove('b3-outcome-won','b3-outcome-lost');
    void ov.offsetWidth;
    ov.classList.add(st.status==='won'?'b3-outcome-won':'b3-outcome-lost');
  }
}
function _b3CardEl(side,i){ return el('b4-tok-'+(side==='enemy'?'enemy':'ally')+'-'+i); }
function _b3OneHitFx(h,isCrit,noSrcPulse){
  const color=B3_ELEMENT_COLORS[h.elem]||'#e8b54d';
  const tgt=_b3CardEl(h.side,h.i);
  if(tgt){
    tgt.style.setProperty('--el-color',color);
    tgt.classList.remove('b3-hit-shake','b3-hit-flash'); void tgt.offsetWidth;
    tgt.classList.add('b3-hit-shake','b3-hit-flash');
    const num=document.createElement('div');
    num.className='b3-dmg-num'+(isCrit?' b3-dmg-crit':'');
    num.textContent='-'+fmt(h.dmg);
    tgt.appendChild(num);
    setTimeout(()=>{ try{num.remove();}catch(e){} },650);
  }
  // noSrcPulse — в проигрывателе ленты источник (враг) уже сдвинут инлайн-transform;
  // b3-act-pulse (scale) перебил бы слайд, поэтому подсветку источника даём через b4-acting.
  if(!noSrcPulse&&h.src_side!=null&&h.src_i!=null){
    const atk=_b3CardEl(h.src_side,h.src_i);
    if(atk){
      atk.style.setProperty('--el-color',color);
      atk.classList.remove('b3-act-pulse'); void atk.offsetWidth;
      atk.classList.add('b3-act-pulse');
    }
  }
}
// ── Онбординг боя: проигрыватель «ленты хода врага» (пошагово вместо телепорта) ──
function _b3NoMotion(){
  try{ return document.body.classList.contains('no-fx')
    || (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); }
  catch(e){ return false; }
}
function _b3PlayTimeline(timeline, finalRes){
  const st=_b3St;
  if(!st){ _btRender(finalRes, null, finalRes.reward); return; }
  const noMotion=_b3NoMotion();
  // «живой» HP по сторонам (сеем из до-фазового состояния): полоски убывают по мере ударов
  const live={};
  ['ally','enemy'].forEach(function(side){
    ((st[side]||{}).units||[]).forEach(function(u,i){
      live[side+i]={hp:u.hp, max:u.hp_max||1, alive:u.alive}; });
  });
  _b3Playing=true; _b3PendingFinal=finalRes; _b3SkipReq=false;
  let idx=0;
  function finish(){
    if(_b3PlayTimer){ clearTimeout(_b3PlayTimer); _b3PlayTimer=null; }
    _b3Playing=false; _b3SkipReq=false; _b3PendingFinal=null;
    _btRender(finalRes, null, finalRes.reward);   // null turn → без повторного проигрыша hits
  }
  function step(){
    if(_b3SkipReq || idx>=timeline.length){ finish(); return; }
    const beat=timeline[idx++];
    const ei=beat.actor && beat.actor.i;
    const tok=_b3CardEl('enemy', ei);
    if(tok && !noMotion){ tok.classList.remove('b4-acting'); void tok.offsetWidth; tok.classList.add('b4-acting'); }
    let dur=B4_BEAT_GAP_MS;
    if(beat.kind==='move' && beat.to){
      dur=_b3SlideToken(tok, beat.to, noMotion)+B4_BEAT_GAP_MS;
    } else if(beat.hits && beat.hits.length){
      beat.hits.forEach(function(h){ _b3OneHitFx(h, false, true); _b3LiveHit(live, h); });
      dur=B4_BEAT_HIT_MS+B4_BEAT_GAP_MS;
    } else {
      dur=B4_BEAT_GAP_MS+100;   // defend/skip — короткая пауза, чтобы бит читался
    }
    if(noMotion) dur=0;
    _b3PlayTimer=setTimeout(step, dur);
  }
  step();
}
function _b3SlideToken(tok, to, noMotion){
  if(!tok || noMotion) return 0;
  const ov=el('b3-ov'); if(!ov) return 0;
  const cellFrom=tok.closest('.b4-cell');
  const cellTo=ov.querySelector('[data-cell="'+to.x+'-'+to.y+'"]');
  if(!cellFrom || !cellTo) return 0;
  const rf=cellFrom.getBoundingClientRect(), rt=cellTo.getBoundingClientRect();
  const dx=Math.round(rt.left-rf.left), dy=Math.round(rt.top-rf.top);
  tok.style.zIndex='6';
  tok.style.transition='transform '+B4_BEAT_MOVE_MS+'ms cubic-bezier(.4,.1,.3,1)';
  tok.style.transform='translate('+dx+'px,'+dy+'px)';
  return B4_BEAT_MOVE_MS;
}
function _b3LiveHit(live, h){
  const rec=live[h.side+h.i]; if(!rec) return;
  rec.hp=Math.max(0, rec.hp-(h.dmg||0));
  const tok=_b3CardEl(h.side, h.i); if(!tok) return;
  const fill=tok.querySelector('.b4-hpfill');
  if(fill) fill.style.width=Math.max(0,Math.min(100, rec.hp/rec.max*100)).toFixed(0)+'%';
  if(rec.hp<=0 && rec.alive){ rec.alive=false; tok.classList.add('b4-dead'); }
}
function _b3PlayHitFx(hits,isCrit){
  const arr=hits||[];
  // Ход врага приходит одним ответом сервера (все его удары разом) — разносим FX
  // во времени, чтобы фаза врага читалась как серия ударов, а не мгновенная вспышка.
  // Без движения (no-fx/reduced-motion) — без задержек, всё сразу.
  let noMotion=false;
  try{ noMotion=document.body.classList.contains('no-fx')
    || (window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches); }catch(e){}
  const gap=(noMotion||arr.length<=1)?0:240;
  arr.forEach((h,idx)=>{
    if(gap) setTimeout(()=>_b3OneHitFx(h,isCrit), idx*gap);
    else _b3OneHitFx(h,isCrit);
  });
}
// Клиентский BFS достижимости (4-соседства, стоимость 1/клетка, не сквозь
// препятствия grid==1 и занятые клетки). occupied — Set "x,y" всех живых юнитов
// кроме выбранного. Возвращает Set "x,y" с cost≤ap (сервер валидирует повторно).
function _b4Reach(grid, sx, sy, ap, occupied){
  const H=grid.length, W=(grid[0]||[]).length, res=new Set();
  if(!(ap>0)||!H||!W) return res;
  const seen=new Set([sx+','+sy]), q=[[sx,sy,0]], DIRS=[[1,0],[-1,0],[0,1],[0,-1]];
  while(q.length){
    const cur=q.shift(), x=cur[0], y=cur[1], c=cur[2];
    if(c>0) res.add(x+','+y);
    if(c>=ap) continue;
    for(let d=0;d<DIRS.length;d++){
      const nx=x+DIRS[d][0], ny=y+DIRS[d][1], k=nx+','+ny;
      if(nx<0||ny<0||nx>=W||ny>=H||seen.has(k)) continue;
      if(grid[ny][nx]===1||occupied.has(k)) continue;
      seen.add(k); q.push([nx,ny,c+1]);
    }
  }
  return res;
}
function _b3TapCell(x,y){
  // Онбординг боя: тап по доске во время проигрывания ленты — доиграть мгновенно.
  if(_b3Playing){ _b3SkipReq=true; return; }
  if(!_b3St||_b3Lock) return;
  const st=_b3St, aUnits=st.ally.units||[], eUnits=st.enemy.units||[];
  if(st.status==='won'||st.status==='lost'||st.pending) return;
  let hit=null;
  aUnits.forEach((u,i)=>{ if(u.pos&&u.pos.x===x&&u.pos.y===y) hit={side:'ally',i,u}; });
  eUnits.forEach((u,i)=>{ if(u.pos&&u.pos.x===x&&u.pos.y===y) hit={side:'enemy',i,u}; });
  // тап по своему живому юниту → выбор (в режиме навыка тап по себе = навык на себя)
  if(hit&&hit.side==='ally'&&hit.u.alive){
    if(_b3SkillMode&&hit.i===_b3Sel){ _b3AttackOrSkill(null); return; }
    _b3SelectUnit(hit.i); return;
  }
  if(_b3Sel==null) return;
  const sel=aUnits[_b3Sel]; if(!sel||!sel.alive||!sel.pos) return;
  // тап по врагу → атака или навык (дальность навыка = 2, обычной атаки = роль)
  if(hit&&hit.side==='enemy'&&hit.u.alive){
    const rng=_b3SkillMode?2:(sel.range||1);
    if(Math.max(Math.abs(x-sel.pos.x),Math.abs(y-sel.pos.y))<=rng) _b3AttackOrSkill(hit.i);
    else toast('Цель вне дальности',false);
    return;
  }
  // тап по пустой/трупной клетке: в режиме навыка → выход из режима (без траты AP);
  // иначе → ход, если клетка достижима (труп не занимает клетку для сервера)
  if(!hit||!hit.u.alive){
    if(_b3SkillMode){ _b3SkillMode=false; _btRender(st); return; }
    const occSet=new Set();
    aUnits.concat(eUnits).forEach(u=>{ if(u.alive&&u!==sel&&u.pos) occSet.add(u.pos.x+','+u.pos.y); });
    if(_b4Reach(st.grid, sel.pos.x, sel.pos.y, sel.ap||0, occSet).has(x+','+y)) _b3Move(x,y);
  }
}
function _b3SelectUnit(i){
  if(!_b3St||_b3Playing) return;
  if(_b3Sel===i){ _b3Sel=null; _b3SkillMode=false; }
  else { _b3Sel=i; _b3SkillMode=false; }
  _haptic('light'); _btRender(_b3St);
}
function _b3SkillBtn(){
  if(_b3Sel==null||_b3Playing) return;
  _b3SkillMode=!_b3SkillMode; _haptic('light'); _btRender(_b3St);
}
function _b3Act(body){ if(!_b3St) return; _b3Api('/combat2/battle/action', Object.assign({battle_id:_b3St.battle_id}, body)); }
function _b3Move(x,y){ if(_b3Sel==null) return; _b3Act({type:'move', unit_i:_b3Sel, cell:{x,y}}); }
function _b3AttackOrSkill(targetI){
  if(_b3Sel==null) return;
  _b3Act(_b3SkillMode?{type:'skill', unit_i:_b3Sel, target_i:targetI}
                     :{type:'attack', unit_i:_b3Sel, target_i:targetI});
}
function _b3Defend(){ if(_b3Sel==null) return; _b3Act({type:'defend', unit_i:_b3Sel}); }
function _b3EndTurn(){ _b3Act({type:'end_turn'}); }
function _b3TriadAct(){ _b3Act({type:'triad'}); }
function _b3Api(path, body, after){
  if(_b3Lock||_b3Playing) return;
  _b3Lock=true;
  api(path,{method:'POST',body:JSON.stringify(body)})
    .then(r=>{
      _b3Lock=false;
      if(r.status==='won'){_haptic('success');refreshCurrBar&&refreshCurrBar();}
      else if(r.status==='lost')_haptic('error');
      // Онбординг боя: если пришла лента хода врага — проигрываем её пошагово (кроме
      // кастомного after у QTE и режима без анимаций). Иначе — обычный рендер.
      const tl=r.turn&&r.turn.timeline;
      if(!after && tl && tl.length && _b3St && !_b3NoMotion()){ _b3PlayTimeline(tl, r); }
      else (after||_btRender)(r, r.turn, r.reward);
    })
    .catch(e=>{_b3Lock=false;toast(e,false);});
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
  let off=Math.abs(elapsed-(_b3St._ringMs||1400));
  // UX_AUDIT С23: упрощённый ввод — окно тайминга мягче (offset считается клиентом,
  // сервер только грейдит его; это осознанная доступность, не чит-путь)
  if(typeof _easyInput==='function' && _easyInput()) off=Math.round(off*0.45);
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
