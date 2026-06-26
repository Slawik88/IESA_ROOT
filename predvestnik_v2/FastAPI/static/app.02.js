// ── Profile ───────────────────────────────────────────────────────────────────
// switchPro() defined later with marriage + wallet tabs
function loadProfile() {
  el('pro-main').innerHTML='<div class="sk" style="height:120px;border-radius:var(--r);margin-bottom:8px"></div><div class="sk" style="height:60px;border-radius:var(--r)"></div>';
  api('/profile/me').then(d=>{
    if(!d || typeof d !== 'object') throw new Error('Неверный формат ответа сервера');
    _cid = _initChatId || d.chats?.[0]?.chat_tg_id || 0;
    if(d.user_id) _uid = d.user_id;
    _profileData = d;
    const pets=d.pets.filter(p=>p.placement!=='storage').slice(0,6);
    const uid = d.user_id || _uid;
    const lvl = d.chats?.[0]?.user_level || 1;
    const xp = d.chats?.[0]?.user_xp || 0;
    const xpInLvl = xp % 3000, xpPct = Math.min(100, Math.round(xpInLvl/3000*100));
    // БЛОК 3: торжественный левел-ап (детект между загрузками) + анимация заливки
    // XP-шкалы один раз за сессию (чтобы авто-релоад каждые 5 мин её не дёргал).
    _checkLevelUp(lvl);
    const animateXp = !_xpAnimated; _xpAnimated = true;
    if (animateXp) setTimeout(() => {
      const f = el('pro-main')?.querySelector('.xp-fill');
      if (f) f.style.width = (f.dataset.pct || 0) + '%';
    }, 40);
    el('pro-main').innerHTML=`
      <div class="hero ${d.cosmetics&&d.cosmetics.profile_bg?d.cosmetics.profile_bg.css:''}">
        ${d.cosmetics&&d.cosmetics.card_fx?`<div class="card-fx ${d.cosmetics.card_fx.css}"></div>`:''}
        <div class="hero-head">
          <div class="ava ${d.cosmetics&&d.cosmetics.avatar_frame?d.cosmetics.avatar_frame.css:''} ${d.cosmetics&&d.cosmetics.avatar_halo?d.cosmetics.avatar_halo.css:''}" id="pro-ava">${d.is_vip?'👑':'🔮'}</div>
          <div style="min-width:0">
            <div class="pname ${d.cosmetics&&d.cosmetics.name_glow?d.cosmetics.name_glow.css:''}">@${vipName(d.username||'Игрок', d.is_vip)}</div>
            <div class="prank">${d.rank}</div>
            ${d.cosmetics&&d.cosmetics.title?`<div class="ptitle">${esc(d.cosmetics.title)}</div>`:''}
          </div>
        </div>
        <div class="hero-xp">
          <div class="xp-bar"><div class="xp-fill" data-pct="${xpPct}" style="width:${animateXp?0:xpPct}%"></div></div>
          <div class="xp-lbl"><span>Уровень ${lvl}</span><span>${fmt(xpInLvl)} / 3 000 XP</span></div>
        </div>
        <div class="stats">
          <div class="stat clickable" onclick="openExchangeCurrencyModal('buy')"><div>🪙</div><div class="sv">${fmt(d.mora)}</div><div class="sl">Мора 🔄</div></div>
          <div class="stat clickable" onclick="openExchangeCurrencyModal('sell')"><div>💎</div><div class="sv">${fmtF(d.diamonds)}</div><div class="sl">Алмазы 🔄</div></div>
          <div class="stat clickable" onclick="${(d.zarniki||0)>0?'openExchangeZarnikiModal()':"goTo('market','vip')"}"><div>✨</div><div class="sv">${Math.floor(d.zarniki||0)}</div><div class="sl">${(d.zarniki||0)>0?'Зарники 🔄':'Зарники +'}</div></div>
          <div class="stat clickable" onclick="goTo('ach')"><div>🏆</div><div class="sv">${d.achievements}</div><div class="sl">Ачивки ›</div></div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;padding:9px 0 0;margin-top:11px;border-top:1px solid var(--border2)">
          <span style="font-size:10.5px;color:var(--muted)">🆔 <code>${uid}</code></span>
          <button class="btn btn-ghost btn-sm" style="padding:3px 9px;font-size:10px" onclick="copyUid(${uid})">📋 Копировать</button>
        </div>
      </div>

      <!-- Быстрые действия: всё важное в 1 клик -->
      <div class="qa-row">
        <div class="qa qa-hot" onclick="goTo('quests','streak')"><span>🔥</span>Стрик ${d.streak}</div>
        <div class="qa" onclick="goTo('quests')"><span>📋</span>Квесты</div>
        <div class="qa" onclick="goTo('bp')"><span>🎫</span>Пропуск</div>
        <div class="qa" onclick="goTo('zoo')"><span>🍖</span>Питомцы</div>
      </div>

      <button class="btn btn-full promo-cta" style="margin-top:10px" onclick="openPromoModal()">🎟 У меня есть промокод</button>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-ghost" style="flex:1" onclick="openLooksModal()">🎨 Внешний вид</button>
        <button class="btn btn-ghost" style="flex:1" onclick="openClansModal()">🛡 Клан</button>
      </div>

      <!-- Активные баффы (заполняется loadActiveBuffs) -->
      <div id="pro-buffs"></div>

      ${d.is_vip?'':`<div class="vip-banner" onclick="goTo('market','vip')">
        <span class="vb-crown">👑</span>
        <div><div class="vb-title">Стань VIP</div><div class="vb-sub">Еженедельные подарки, +слот питомника, безлимит ника</div></div>
        <span class="vb-cta">›</span>
      </div>`}

      <!-- Карточка брака (заполняется loadMarriageCard) -->
      <div id="pro-marriage-card"><div class="sk" style="height:90px;border-radius:var(--r)"></div></div>
      <!-- Карточка ника (заполняется loadNickCard) -->
      <div id="pro-nick-card"></div>
      ${pets.length?`<div class="card">
        <div class="card-title">🐾 Питомники</div>
        ${pets.map(p=>`
        <div class="pcard" onclick="goTo('zoo')" style="cursor:pointer"><div class="pcol">
          <div class="pn">${p.name||p.species_id} ${rc(p.rarity)}</div>
          <div class="ps">Lv${p.pet_level} · ${PL[p.placement]}</div>
          <div class="fat-bar"><div class="fat-fill" style="width:${p.fatigue}%;background:${fatC(p.fatigue)}"></div></div>
        </div></div>`).join('')}
        <div class="shortcut-row">
          <span class="shortcut-link" onclick="goTo('zoo')">Управлять питомцами →</span>
        </div>
      </div>`:`<div class="card"><div class="empty-state"><div class="es-icon">🐾</div><div class="es-title">Питомцев пока нет</div><div class="es-sub">Крутни Гачу, чтобы завести первого</div><button class="btn btn-gold btn-sm" style="margin-top:10px" onclick="goTo('market','gacha')">🎲 Открыть Гачу</button></div></div>`}
      ${d.chats.length?`<div class="card">
        <div class="card-title">💬 Активность</div>
        ${d.chats.map(c=>`<div class="irow"><span class="ik">${esc(c.chat_title||'Чат')}</span><span class="iv">Lv${c.user_level} · ${fmt(c.user_messages_count_all_time)}</span></div>`).join('')}
        <div class="shortcut-row">
          <span class="shortcut-link" onclick="goTo('hof')">Посмотреть топ →</span>
        </div>
      </div>`:''}
      <div id="wallet-mini"></div>`;
    loadMarriageCard();
    loadNickCard();
    loadActiveBuffs();
    loadWalletMini();
    if(!_ws && _uid) connectWS();
    updateCurrBar(d);          // populate sticky currency bar from profile data
    if(!_adminChats) checkAdminAccess();
    checkGlobalAccess();
  }).catch(e=>{el('pro-main').innerHTML=`<div style="color:var(--red);padding:20px;font-size:12px">${typeof e==='string'?e:'Напишите боту чтобы создать профиль.'}</div>`;});
}
// ── Конструктор «Внешний вид» (косметика профиля) ──────────────────────────────
const _LOOKS_SLOTS=['name_glow','avatar_frame','avatar_halo','title','profile_bg','card_fx'];
const _LOOKS_SLOT_LABEL={name_glow:'✨ Ореол имени',avatar_frame:'🖼 Рамка аватара',avatar_halo:'🌟 Гало аватара',title:'🏷 Титул',profile_bg:'🖌 Фон профиля',card_fx:'❄️ Частицы карточки'};
let _looksData=null, _looksSel={}, _looksSaved={}, _looksDirty=false;
function openLooksModal(){
  _looksDirty=false;
  OM('🎨 Внешний вид','<div class="loader">Загрузка...</div>',[{l:'Готово',c:'btn-gold',f:'_looksClose()'}]);
  api('/cosmetics/').then(d=>{_looksData=d;_looksSaved=_looksEquipped(d);_looksSel={..._looksSaved};renderLooks();})
    .catch(e=>{const b=el('mb'); if(b)b.innerHTML=`<div class="err">${e}</div>`;});
}
function _looksClose(){
  if(_looksChanged()){ _looksApply().then(()=>{ CM(); loadProfile(); }); }   // «Готово» = применить незакоммиченное
  else { CM(); if(_looksDirty) loadProfile(); }
}
function _looksEquipped(d){
  const sel={};
  _LOOKS_SLOTS.forEach(s=>{const eq=(d.slots[s]||[]).find(it=>it.equipped); sel[s]=eq?eq.id:null;});
  return sel;
}
function _looksCos(id){ if(!id)return null; for(const s of _LOOKS_SLOTS){const f=(_looksData.slots[s]||[]).find(it=>it.id===id); if(f)return f;} return null; }
function _rarLabel(r){return {common:'Обычный',rare:'Редкий',epic:'Эпический',legendary:'Легендарный',mythic:'Мифический'}[r]||r;}
function _srcLabel(s){return {vip:'🎁 даётся с VIP',bp:'🎫 платный БП',reward:'🏅 за достижение',shop:''}[s]||'';}
function _looksPriceTxt(opt){ return Object.entries(opt).map(([cur,amt])=>`${amt}${(_looksData.currency_icons||{})[cur]||cur}`).join('+'); }
function renderLooks(){
  const b=el('mb'); if(!b||!_looksData) return;
  const vipBar=_looksData.vip?'':`<div class="looks-vipbar">
    <span>👑 Смотреть и листать превью можно всё. Покупать косметику и выбирать приветствие — с VIP.</span>
    <button class="btn btn-sm btn-gold" onclick="CM();goTo('market','vip')">Перейти к VIP</button></div>`;
  b.innerHTML=_looksPreviewHtml()+vipBar+'<button class="btn btn-ghost btn-full" style="margin:2px 0 10px" onclick="_openSurprisesModal()">🎁 Сюрпризы и 🔹 Крафт косметики</button>'+_LOOKS_SLOTS.map(_looksSlotHtml).join('')+_looksWelcomeHtml();
  _playWelcomePreview(_looksData.welcome&&_looksData.welcome.current);
}
// Мини-карточка профиля из набора слотов sel — для сравнения «Сейчас → Станет».
function _looksRenderCard(sel){
  const d=_looksData;
  const glow=_looksCos(sel.name_glow), frame=_looksCos(sel.avatar_frame), title=_looksCos(sel.title);
  const halo=_looksCos(sel.avatar_halo), bg=_looksCos(sel.profile_bg), fx=_looksCos(sel.card_fx);
  return `<div class="looks-preview looks-preview--mini ${bg?bg.css:''}">
    ${fx?`<div class="card-fx ${fx.css}"></div>`:''}
    <div class="ava ${frame?frame.css:''} ${halo?halo.css:''}">${d.vip?'👑':'🔮'}</div>
    <div class="pname ${glow?glow.css:''}">@${esc((_profileData&&_profileData.username)||'Игрок')}</div>
    ${title?`<div class="ptitle">${esc(title.text||title.name)}</div>`:''}
  </div>`;
}
function _looksChanged(){ return _LOOKS_SLOTS.some(s=>(_looksSel[s]||null)!==(_looksSaved[s]||null)); }
// Превью «Сейчас → Станет»: левая карточка = применённое, правая = выбранное (ещё не сохранено).
function _looksPreviewHtml(){
  const changed=_looksChanged();
  const actions=changed
    ?`<div class="looks-ba-act">
        <button class="btn btn-sm btn-gold" onclick="_looksApply()">✓ Применить</button>
        <button class="btn btn-sm btn-ghost" onclick="_looksReset()">Сбросить</button></div>`
    :`<div class="looks-ba-hint">👇 Жми предмет — увидишь, как изменится профиль, затем «Применить».</div>`;
  return `<div class="looks-ba">
      <div class="looks-ba-col"><div class="looks-ba-lbl">Сейчас</div>${_looksRenderCard(_looksSaved)}</div>
      <div class="looks-ba-arrow">${changed?'➜':'='}</div>
      <div class="looks-ba-col"><div class="looks-ba-lbl ${changed?'looks-ba-lbl--new':''}">Станет</div>${_looksRenderCard(_looksSel)}</div>
    </div>${actions}`;
}
function _looksSlotHtml(slot){
  const items=_looksData.slots[slot]||[];
  const none=`<div class="looks-card ${_looksSel[slot]?'':'sel'}" onclick="_looksUnequip('${slot}')">
    <div class="lc-sw lc-sw--none">✖</div><div class="lc-name">Без</div></div>`;
  return `<div class="looks-slot"><div class="looks-slot-t">${_LOOKS_SLOT_LABEL[slot]}</div>
    <div class="looks-cards">${none}${items.map(it=>_looksCard(slot,it)).join('')}</div></div>`;
}
// Мини-превью реального эффекта в карточке (а не просто текст).
function _looksSwatch(slot,it){
  const c=it.css||'';
  const face=(_looksData&&_looksData.vip)?'👑':'🔮';
  switch(slot){
    case 'name_glow':    return `<div class="lc-sw"><span class="lc-nick ${c}">@Ник</span></div>`;
    case 'title':        return `<div class="lc-sw"><span class="lc-title">${esc(it.text||it.name)}</span></div>`;
    case 'avatar_frame':
    case 'avatar_halo':  return `<div class="lc-sw"><span class="lc-ava ${c}">${face}</span></div>`;
    case 'profile_bg':   return `<div class="lc-sw lc-bg ${c}"></div>`;
    case 'card_fx':      return `<div class="lc-sw"><div class="card-fx ${c}"></div></div>`;
    default:             return `<div class="lc-sw"></div>`;
  }
}
function _looksCard(slot,it){
  const sel=_looksSel[slot]===it.id;
  const sw=_looksSwatch(slot,it);
  const rar=`<span class="lc-rar">${_rarLabel(it.rarity)}</span>`;
  if(it.owned){
    return `<div class="looks-card r-${it.rarity} ${sel?'sel':''}" onclick="_looksEquip('${slot}','${it.id}')">
      ${sw}<div class="lc-name">${esc(it.name)}</div>
      <div class="lc-foot">${rar}${_looksSaved[slot]===it.id?'<span class="lc-on">✓ надето</span>':''}</div></div>`;
  }
  const vip=it.vip_required?'<span class="lc-vip">VIP</span>':'';
  const bal=_looksData.balances||{};
  let foot;
  if(it.vip_required && !_looksData.vip){
    foot=`<div class="lc-tag">🔒 Только для VIP</div>`;
  } else if(it.price&&it.price.length){
    foot=`<div class="lc-buys">${it.price.map((opt,i)=>{
      const can=Object.entries(opt).every(([cur,amt])=>(bal[cur]||0)>=amt);
      return `<button class="btn btn-sm btn-gold lc-buy${can?'':' lc-buy--no'}" onclick="_looksBuy('${it.id}',${i})">${_looksPriceTxt(opt)}</button>`;
    }).join('')}</div>`;
  } else {
    foot=`<div class="lc-tag">${_srcLabel(it.source)}</div>`;
  }
  return `<div class="looks-card r-${it.rarity} locked">
    ${sw}<div class="lc-name">🔒 ${esc(it.name)} ${vip}</div>
    <div class="lc-foot">${rar}</div>${foot}</div>`;
}
function _looksEquip(slot,id){ _looksSel[slot]=id; renderLooks(); }   // pending — применяется по «Применить»
function _looksUnequip(slot){ _looksSel[slot]=null; renderLooks(); }
function _looksReset(){ _looksSel={..._looksSaved}; renderLooks(); }
function _looksApply(){
  const ops=[];
  _LOOKS_SLOTS.forEach(s=>{
    const sel=_looksSel[s]||null, sav=_looksSaved[s]||null;
    if(sel===sav) return;
    ops.push(sel
      ? api('/cosmetics/equip',{method:'POST',body:JSON.stringify({cosmetic_id:sel})})
      : api('/cosmetics/unequip',{method:'POST',body:JSON.stringify({slot:s})}));
  });
  if(!ops.length) return Promise.resolve();
  return Promise.all(ops).then(()=>{
    _looksSaved={..._looksSel};
    _LOOKS_SLOTS.forEach(s=>(_looksData.slots[s]||[]).forEach(it=>it.equipped=(_looksSaved[s]===it.id)));
    _looksDirty=true; toast('✅ Внешний вид применён!'); renderLooks();
  }).catch(e=>toast(e,false));
}
function _looksBuy(id,opt){
  api('/cosmetics/buy',{method:'POST',body:JSON.stringify({cosmetic_id:id,option_index:opt})})
    .then(r=>{toast(r.message); refreshCurrBar(); _looksDirty=true;
      return api('/cosmetics/equip',{method:'POST',body:JSON.stringify({cosmetic_id:id})});})
    .then(()=>openLooksModal())
    .catch(e=>toast(e,false));
}
// ── Приветственная анимация (выбор режима прелоадера; премиум — за VIP) ─────────
let _wpMode=null;
function _looksWelcomeHtml(){
  const w=_looksData.welcome; if(!w) return '';
  const cards=(w.options||[]).map(o=>{
    const cls=['looks-card','lc-wide','r-'+o.rarity]; if(o.current)cls.push('sel'); if(o.locked)cls.push('locked');
    const vip=o.vip_required?' <span class="lc-vip">VIP</span>':'';
    return `<div class="${cls.join(' ')}" onclick="_welcomePick('${o.id}')">
      <div class="lc-name">${o.locked?'🔒 ':''}${esc(o.name)}${vip}</div>
      <div class="lc-tag">${o.current?'✓ выбрано':esc(o.desc)}</div></div>`;
  }).join('');
  const hint=_looksData.vip?'':'<div class="looks-hint">👆 Жми на любой режим — увидишь превью. Выбрать приветствие можно с VIP.</div>';
  return `<div class="looks-slot"><div class="looks-slot-t">🎬 Приветствие при входе</div>
    <div id="wpreview" class="wpreview"></div>${hint}
    <div class="looks-cards">${cards}</div></div>`;
}
function _playWelcomePreview(mode){
  const box=el('wpreview'); if(!box) return;
  mode=mode||'scanner';
  if(_wpMode===mode && box.childNodes.length) return;   // не перезапускаем при правках др. слотов
  _wpMode=mode;
  const nick=(_profileData&&_profileData.username)||'Игрок';
  box.className='wpreview plm-'+mode;
  box.innerHTML=`<div class="wp-orb">🔮</div><div class="plw-nick wp-name">@${esc(nick)}</div>`;
}
// Клик по режиму приветствия: превью видят ВСЕ; применяет только тот, кому доступно.
function _welcomePick(id){
  if(!_looksData||!_looksData.welcome) return;
  const o=(_looksData.welcome.options||[]).find(x=>x.id===id); if(!o) return;
  _playWelcomePreview(id);                       // превью — доступно всем
  if(o.locked){ toast('🔒 Это приветствие доступно с VIP',false); return; }
  _setWelcome(id);                               // применить — только разрешённое
}
function _setWelcome(id){
  if(!_looksData||!_looksData.welcome) return;
  const w=_looksData.welcome, prev=w.current;
  if(id===prev) return;
  w.current=id; (w.options||[]).forEach(o=>o.current=(o.id===id));
  renderLooks(); _looksDirty=true;
  api('/cosmetics/welcome',{method:'POST',body:JSON.stringify({animation_id:id})})
    .then(r=>toast(r.message))
    .catch(e=>{toast(e,false); w.current=prev;
      (w.options||[]).forEach(o=>o.current=(o.id===prev)); renderLooks();});
}
// ── БЛОК21 #3: сундуки-сюрпризы + крафт косметики из осколков ────────────────────
function _openSurprisesModal(){
  OM('🎁 Сюрпризы и Крафт','<div class="loader">Загрузка...</div>',[{l:'← К внешнему виду',c:'btn-ghost',f:'openLooksModal()'}]);
  Promise.all([api('/cosmetics/chests'),api('/cosmetics/craft')]).then(([ch,cr])=>{
    const b=el('mb'); if(!b) return;
    const chests=(ch.chests||[]).map(c=>`<div class="gift-card">
      <div class="gift-name" style="min-height:auto;margin-bottom:8px">${esc(c.name)}</div>
      <div class="gift-foot">
        ${c.owned>0?`<button class="btn btn-sm btn-gold" onclick="_openChest('${c.id}',this)">Открыть (${c.owned})</button>`:''}
        <button class="btn btn-sm btn-ghost" onclick="_buyChest('${c.id}')">${c.zarniki} ✨</button>
      </div></div>`).join('');
    const craftItems=(cr.items||[]).map(it=>{
      const sw=it.text?`<span class="lc-title">${esc(it.text)}</span>`:`<span class="lc-nick ${it.css||''}">@Ник</span>`;
      const btn=it.owned?`<span class="gp-owned">✓ есть</span>`
        :`<button class="btn btn-sm ${it.can?'btn-gold':'btn-ghost'}" ${it.can?'':'disabled'} onclick="_craftCosmetic('${it.id}',this)">${it.cost} 🔹</button>`;
      return `<div class="gift-card${it.owned?' gift-owned':''}"><div class="gift-sw">${sw}</div>
        <div class="gift-name">${esc(it.name)}</div>
        <div class="gift-foot"><span class="lc-rar">${_rarLabel(it.rarity)}</span>${btn}</div></div>`;
    }).join('');
    b.innerHTML=`<div class="looks-hint">🎁 Сундуки за ⭐ дают случайную косметику/расходники; дубль косметики → 🔹 осколки. Из осколков собирай конкретную косметику в Крафте.</div>
      <div class="looks-slot-t">🎁 Сундуки-сюрпризы</div>
      <div class="gift-grid">${chests}</div>
      <div class="looks-slot-t" style="margin-top:14px">🔹 Крафт <span class="clan-coin-note">· осколков: ${cr.shards}</span></div>
      <div class="gift-grid">${craftItems}</div>`;
  }).catch(e=>{const b=el('mb');if(b)b.innerHTML=`<div class="err">${e}</div>`;});
}
function _buyChest(id){
  api('/cosmetics/chest/buy',{method:'POST',body:JSON.stringify({chest_id:id})})
    .then(r=>{ toast(r.message||'🎁 Куплено!'); refreshCurrBar(); _openSurprisesModal(); })
    .catch(e=>toast(e,false));
}
function _openChest(id,btn){
  if(btn) btn.disabled=true;
  api('/cosmetics/chest/open',{method:'POST',body:JSON.stringify({chest_id:id})})
    .then(r=>{ const d=r.drop||{}; toast('🎉 '+(d.name||'Открыто!'), true); _looksDirty=true; _openSurprisesModal(); })
    .catch(e=>{toast(e,false); if(btn) btn.disabled=false;});
}
function _craftCosmetic(id,btn){
  if(btn) btn.disabled=true;
  api('/cosmetics/craft',{method:'POST',body:JSON.stringify({cosmetic_id:id})})
    .then(r=>{ toast(r.message); _looksDirty=true; _openSurprisesModal(); })
    .catch(e=>{toast(e,false); if(btn) btn.disabled=false;});
}
// ── Кланы / Гильдии ─────────────────────────────────────────────────────────────
let _clansData=null, _clanEmblemSel='🛡';
function openClansModal(){
  OM('🛡 Кланы','<div class="loader">Загрузка...</div>',[{l:'Готово',c:'btn-gold',f:'CM()'}]);
  api('/clans/').then(d=>{_clansData=d; _clanEmblemSel=(d.emblems&&d.emblems[0])||'🛡'; renderClans();})
    .catch(e=>{const b=el('mb'); if(b)b.innerHTML=`<div class="err">${e}</div>`;});
}
function renderClans(){
  const b=el('mb'); if(!b||!_clansData) return;
  b.innerHTML=(_clansData.my_clan?_clanMyHtml():_clanCreateHtml())+_clanTopHtml();
}
function _clanMyHtml(){
  const c=_clansData.my_clan;
  const lp=c.level_progress||{level:c.level||1,xp_into:0,xp_needed:0,is_max:false};
  const pct=lp.is_max?100:(lp.xp_needed?Math.min(100,Math.round(lp.xp_into/lp.xp_needed*100)):0);
  const emax=c.effective_max||_clansData.max_members;
  const members=(c.members||[]).map(m=>{
    const lead=m.role==='leader';
    const title=m.title?`<div class="top-title">${esc(m.title)}</div>`:'';
    return `<div class="clan-mrow"><span class="clan-mname">${lead?'👑 ':''}${unameLink(m.user_id, m.username, false, m.glow)}${title}</span>
      <span class="clan-mrole">🎖 ${fmtF(m.clan_coins||0)}</span></div>`;
  }).join('');
  return `<div class="clan-card">
      <div class="clan-emblem">${c.emblem||'🛡'}</div>
      <div class="clan-name">${esc(c.name)} <span class="clan-tag">[${esc(c.tag)}]</span></div>
      ${c.description?`<div class="clan-desc">${esc(c.description)}</div>`:''}
      <div class="clan-lvlrow"><span class="clan-lvlbadge">🏛 Уровень ${lp.level}</span>
        <span class="clan-lvlxp">${lp.is_max?'МАКС':fmtF(lp.xp_into)+' / '+fmtF(lp.xp_needed)+' XP'}</span></div>
      <div class="clan-lvlbar"><div class="clan-lvlfill" style="width:${pct}%"></div></div>
      <div class="clan-stats"><div><b>${(c.members||[]).length}</b>/${emax} участников</div>
        <div><b>${fmtF(c.total_xp||0)}</b> XP · 🎖 <b>${fmtF(c.clan_coins||0)}</b></div></div>
    </div>
    ${_clanBoardHtml()}
    ${_clanShopHtml()}
    ${_clanBuildingsHtml()}
    <div class="looks-slot-t" style="margin-top:12px">Состав <span class="clan-coin-note">· вклад 🎖</span></div>
    <div class="clan-members">${members}</div>
    <button class="btn btn-full btn-ghost" style="margin-top:12px" onclick="_clanLeave()">🚪 Покинуть клан</button>`;
}
function _clanBuildingsHtml(){
  const c=_clansData.my_clan;
  const bs=(c&&c.buildings)||[];
  if(!bs.length) return '';
  const lvl=(c.level)||1;
  const cards=bs.map(b=>`<div class="clan-bld">
    <div class="clan-bld-ico">${b.emoji||'🏛'}</div>
    <div class="clan-bld-body">
      <div class="clan-bld-name">${esc(b.name)}</div>
      <div class="clan-bld-eff">${esc(b.effect||'')}</div>
      ${b.next_effect?`<div class="clan-bld-next">↑ ур.${lvl+1}: ${esc(b.next_effect)}</div>`:`<div class="clan-bld-next clan-bld-max">★ максимум</div>`}
    </div></div>`).join('');
  return `<div class="looks-slot-t" style="margin-top:12px">🏛 Штаб клана · ур.${lvl}</div>
    <div class="clan-blds">${cards}</div>`;
}
function _clanBoardHtml(){
  const c=_clansData.my_clan;
  const reqs=(c.requests||[]);
  const rows=reqs.length?reqs.map(r=>{
    const pct=r.qty_need?Math.min(100,Math.round(r.qty_filled/r.qty_need*100)):0;
    const help=(!r.mine)?`<button class="btn btn-sm btn-gold" onclick="_clanReqFill(${r.request_id},${r.remaining})">🤝 Помочь</button>`:'';
    const cancel=(r.can_cancel)?`<button class="btn btn-sm btn-ghost" onclick="_clanReqCancel(${r.request_id})">✕</button>`:'';
    return `<div class="clan-req">
      <div class="clan-req-top"><span class="clan-req-name">${esc(r.item_name||r.item_id)}</span>
        <span class="clan-req-qty">${r.qty_filled}/${r.qty_need}</span></div>
      <div class="clan-req-bar"><div class="clan-req-fill" style="width:${pct}%"></div></div>
      <div class="clan-req-bot"><span class="clan-req-author">для ${unameLink(r.author_id, r.author_name, false)}${r.mine?' <span class="clan-you">ты</span>':''}</span>
        <span class="clan-req-act">${help}${cancel}</span></div>
    </div>`;
  }).join(''):'<div class="clan-empty">Пока пусто. Жми «➕ Запрос» — попроси у клана нужный ресурс.</div>';
  return `<div class="clan-board-head"><span class="looks-slot-t" style="margin:0">📋 Доска Запросов</span>
      <button class="btn btn-sm btn-gold" onclick="_clanReqCreate()">➕ Запрос</button></div>
    <div class="clan-board-hint">Проси корм и материалы — согильдиец передаёт их тебе лично, получая 🎖 и XP клану.</div>
    <div class="clan-board">${rows}</div>`;
}
function _clanCreateHtml(){
  const emblems=(_clansData.emblems||[]).map(e=>`<span class="clan-emb-opt ${e===_clanEmblemSel?'sel':''}" onclick="_clanPickEmblem('${e}')">${e}</span>`).join('');
  return `<div class="looks-hint">Создай свой клан или вступи в существующий ниже. Один клан на игрока.</div>
    <div class="clan-form">
      <div class="looks-slot-t">Эмблема</div>
      <div class="clan-emblems">${emblems}</div>
      <input id="clan-name" type="text" class="num-input" maxlength="${_clansData.name_max||24}" placeholder="Название клана"/>
      <input id="clan-tag" type="text" class="num-input" maxlength="${_clansData.tag_max||5}" placeholder="Тег (2–5, напр. WOLF)" style="text-transform:uppercase"/>
      <input id="clan-desc" type="text" class="num-input" maxlength="120" placeholder="Девиз (необязательно)"/>
      <button class="btn btn-full btn-gold" onclick="_clanCreate()">🛡 Основать за ${fmtF(_clansData.create_cost||0)} 🪙</button>
    </div>`;
}
function _clanTopHtml(){
  const top=_clansData.top||[]; if(!top.length) return '';
  const inClan=!!_clansData.my_clan;
  const rows=top.map((c,i)=>{
    const mine=_clansData.my_clan&&_clansData.my_clan.clan_id===c.clan_id;
    const join=(!inClan)?`<button class="btn btn-sm btn-gold" onclick="_clanJoin(${c.clan_id})">Вступить</button>`:(mine?'<span class="clan-you">ты тут</span>':'');
    return `<div class="clan-trow${mine?' clan-mine':''}"><span class="clan-trank">${i+1}</span>
      <span class="clan-temblem">${c.emblem||'🛡'}</span>
      <span class="clan-tname">${esc(c.name)} <span class="clan-tag">[${esc(c.tag)}]</span></span>
      <span class="clan-txp">ур.${c.level||1} · ${fmtF(c.total_xp||0)} XP · ${c.member_count}/${c.effective_max||_clansData.max_members}</span>
      ${join}</div>`;
  }).join('');
  return `<div class="looks-slot-t" style="margin-top:14px">🏆 Топ кланов</div><div class="clan-top">${rows}</div>`;
}
function _clanPickEmblem(e){ _clanEmblemSel=e; renderClans(); }
function _clanCreate(){
  const name=(el('clan-name')||{}).value||'', tag=(el('clan-tag')||{}).value||'', desc=(el('clan-desc')||{}).value||'';
  api('/clans/create',{method:'POST',body:JSON.stringify({name,tag,description:desc,emblem:_clanEmblemSel})})
    .then(r=>{toast(r.message); refreshCurrBar(); openClansModal();})
    .catch(e=>toast(e,false));
}
function _clanJoin(id){
  api('/clans/join',{method:'POST',body:JSON.stringify({clan_id:id})})
    .then(r=>{toast(r.message); openClansModal();}).catch(e=>toast(e,false));
}
function _clanLeave(){
  OM('🚪 Покинуть клан','<div style="padding:6px 2px;font-size:13px">Точно выйти? Если ты лидер — лидерство перейдёт старейшему участнику, а без участников клан распустится.</div>',
    [{l:'Отмена',c:'btn-ghost',f:'openClansModal()'},{l:'Выйти',c:'btn-gold',f:'_clanLeaveDo()'}]);
}
function _clanLeaveDo(){
  api('/clans/leave',{method:'POST',body:JSON.stringify({})})
    .then(r=>{toast(r.message); openClansModal();}).catch(e=>{toast(e,false); openClansModal();});
}
// ── Доска Запросов: создать / помочь / снять ────────────────────────────────────
function _clanReqCreate(){
  const items=(_clansData&&_clansData.request_items)||[];
  if(!items.length){ toast('Нет предметов, доступных для запроса.',false); return; }
  const cap=(_clansData.my_clan&&_clansData.my_clan.request_qty_cap)||5;
  const opts=items.map(it=>`<option value="${esc(it.item_id)}">${esc(it.name)}</option>`).join('');
  OM('➕ Запрос на Доску',
    `<div class="clan-reqform">
       <div class="looks-slot-t">Что нужно</div>
       <select id="creq-item" class="num-input">${opts}</select>
       <div class="looks-slot-t" style="margin-top:8px">Количество (макс ${cap})</div>
       <input id="creq-qty" type="number" class="num-input" min="1" max="${cap}" value="1"/>
       <div class="looks-hint" style="margin-top:6px">Можно просить только корм и материалы. Согильдийцы скидывают предмет тебе лично.</div>
     </div>`,
    [{l:'Отмена',c:'btn-ghost',f:'openClansModal()'},{l:'Опубликовать',c:'btn-gold',f:'_clanReqCreateDo()'}]);
}
function _clanReqCreateDo(){
  const item=(el('creq-item')||{}).value||'';
  const qty=parseInt((el('creq-qty')||{}).value||'1',10)||1;
  api('/clans/request/create',{method:'POST',body:JSON.stringify({item_id:item,qty:qty})})
    .then(r=>{toast(r.message); openClansModal();}).catch(e=>toast(e,false));
}
function _clanReqFill(rid,remaining){
  const def=remaining>0?remaining:1;
  OM('🤝 Помочь по запросу',
    `<div class="clan-reqform">
       <div style="font-size:13px;margin-bottom:6px">Сколько передать? (нужно ещё ${remaining})</div>
       <input id="cfill-qty" type="number" class="num-input" min="1" value="${def}"/>
       <div class="looks-hint" style="margin-top:6px">Отдашь не больше, чем нужно и чем есть у тебя. Награда — 🎖 клан-монеты и XP клану.</div>
     </div>`,
    [{l:'Отмена',c:'btn-ghost',f:'openClansModal()'},{l:'Передать',c:'btn-gold',f:'_clanReqFillDo('+rid+')'}]);
}
function _clanReqFillDo(rid){
  const qty=parseInt((el('cfill-qty')||{}).value||'1',10)||1;
  api('/clans/request/fill',{method:'POST',body:JSON.stringify({request_id:rid,qty:qty})})
    .then(r=>{toast(r.message); refreshCurrBar(); openClansModal();}).catch(e=>toast(e,false));
}
function _clanReqCancel(rid){
  api('/clans/request/cancel',{method:'POST',body:JSON.stringify({request_id:rid})})
    .then(r=>{toast(r.message); openClansModal();}).catch(e=>toast(e,false));
}
// ── Клан-лавка (сток clan_coins) ────────────────────────────────────────────────
function _clanShopHtml(){
  const c=_clansData.my_clan;
  const shop=(c&&c.shop)||[];
  if(!shop.length) return '';
  const coins=c.clan_coins||0;
  const rows=shop.map(s=>{
    const afford=coins+1e-9>=s.cost;
    const btn=afford
      ?`<button class="btn btn-sm btn-gold" onclick="_clanShopBuy('${s.id}')">${fmtF(s.cost)} 🎖</button>`
      :`<button class="btn btn-sm btn-ghost" disabled style="opacity:.5">${fmtF(s.cost)} 🎖</button>`;
    return `<div class="clan-req">
      <div class="clan-req-top"><span class="clan-req-name">${s.emoji||'🎖'} ${esc(s.name)}</span>
        <span class="clan-req-act">${btn}</span></div>
      <div class="clan-board-hint" style="margin:2px 0 0">${esc(s.desc||'')}</div>
    </div>`;
  }).join('');
  return `<div class="clan-board-head"><span class="looks-slot-t" style="margin:0">🎖 Клан-лавка</span>
      <span class="clan-coin-note">у тебя ${fmtF(coins)} 🎖</span></div>
    <div class="clan-board-hint">Трать клан-монеты, заработанные помощью по Доске.</div>
    <div class="clan-board">${rows}</div>`;
}
function _clanShopBuy(id){
  api('/clans/shop/buy',{method:'POST',body:JSON.stringify({shop_id:id})})
    .then(r=>{toast(r.message); refreshCurrBar(); openClansModal();}).catch(e=>toast(e,false));
}
// ── Preloader: эффектный холодный старт (БЛОК 9.2) ──────────────────────────────
function _plSkip() {
  const pl = el('preloader');
  if(!pl || pl.classList.contains('pl-done')) return;
  pl.classList.add('pl-done');
  // Вход → вкладка = одно целое: активная страница «всплывает» каскадом,
  // пока прелоадер растворяется.
  const pg = document.querySelector('.page.active');
  if(pg){ pg.classList.add('pg-enter'); setTimeout(()=>pg.classList.remove('pg-enter'), 1000); }
  setTimeout(()=>{ const p=el('preloader'); if(p) p.remove(); }, 600);
}
function _runPreloader() {
  const pl = el('preloader'); if(!pl) return;
  const reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const box = el('pl-lines');
  const lines = ['🔌 Синхронизация с сервером…','🔍 Проверка сигнатур…','📦 Загрузка данных…'];
  let i = 0;
  const add = () => { if(!box || i>=lines.length) return; const d=document.createElement('div'); d.className='pl-line'; d.textContent=lines[i++]; box.appendChild(d); };
  add();
  const step = reduce ? 90 : 440;
  const tm = setInterval(()=>{ if(i>=lines.length){ clearInterval(tm); return; } add(); }, step);
  setTimeout(()=>{
    const ln = el('pl-lines'); if(ln) ln.classList.add('pl-fade');   // убираем строки — чистая сцена под приветствие
    const mode = (_profileData && _profileData.cosmetics && _profileData.cosmetics.welcome) || 'scanner';
    pl.classList.add('plm-' + mode);                                 // режим приветствия (VIP-выбор, дефолт — scanner)
    const w = el('pl-welcome'); if(!w) return;
    const nick = (_profileData && _profileData.username) ? _profileData.username : '';
    w.innerHTML = nick
      ? `<span class="plw-hi">Добро пожаловать,</span><span class="plw-nick">@${esc(nick)}</span>`
      : `<span class="plw-nick" style="font-size:23px">Добро пожаловать!</span>`;
    w.classList.add('show');
  }, reduce ? 220 : 1500);
  setTimeout(_plSkip, reduce ? 650 : 3200);
}
_runPreloader();

// БЛОК19 Web-First: бот-редиректы открывают мини-апп через ?startapp=<section> →
// доводим юзера до нужного раздела (раньше start_param игнорировался).
function _handleStartParam(){
  let p=''; try{ p=String((tg&&tg.initDataUnsafe&&tg.initDataUnsafe.start_param)||''); }catch(e){}
  if(!p) return;
  const base=p.split('_')[0];
  const run=fn=>setTimeout(()=>{ try{ fn(); }catch(e){} }, 380);
  if(base==='clans'){ run(()=>openClansModal()); return; }
  if(base==='exchange'||base==='exch'){ run(()=>{ switchPage('auction'); setTimeout(()=>{try{swAuction('exch')}catch(e){}},220); }); return; }
  if(base==='crypto'||base==='birzha'){ run(()=>{ switchPage('auction'); setTimeout(()=>{try{swAuction('crypto')}catch(e){}},220); }); return; }
  const M={ shop:['market','goods'],goods:['market','goods'],gacha:['market','gacha'],deal:['market','deal'],
    vip:['market','vip'],themes:['profile','themes'],craft:['craft'],inventory:['profile','inv'],inv:['profile','inv'],
    quests:['quests'],ach:['ach'],achievements:['ach'],zoo:['zoo'],pets:['zoo'],bp:['bp'],auction:['auction'],
    arena:['arena'],relics:['market'],notifications:['profile'] };
  const t=M[base]; if(t) run(()=>goTo(t[0],t[1]));
}
if(INIT_DATA||sess()){loadProfile();_loaded.add('profile');setTimeout(loadPendingNotifications,1000);_handleStartParam();}

// ── Sticky currency bar ───────────────────────────────────────────────────────
// Shows 🪙💎🌑✨ at top of screen (hidden on Profile tab)
let _currBarVisible = false;
let _currInited = false;

function updateCurrBar(data) {
  const bar = el('curr-bar');
  if (!bar) return;
  const set = (id, val, fmt2) => {
    const v=el(id); if(!v) return;
    const next = fmt2(val);
    if (_currInited && v.textContent !== next) {
      v.classList.remove('cb-pulse'); void v.offsetWidth; v.classList.add('cb-pulse');
    }
    v.textContent = next;
  };
  set('cb-mora', data?.mora ?? 0, fmtF);
  set('cb-dia',  data?.diamonds ?? 0, fmtF);
  set('cb-dark', data?.dark_mora ?? 0, fmtF);
  set('cb-zar',  data?.zarniki ?? 0, fmtF);
  _currInited = true;
  // Хедер: имя + уровень/ранг игрока
  if (data?.username !== undefined) {
    const nm=el('hdr-name'); if(nm) nm.textContent=(data.is_vip?'👑 ':'')+(data.username||'Игрок');
    const sub=el('hdr-sub');
    if(sub) sub.textContent=`Lv${data.chats?.[0]?.user_level||1} · 🔥${data.streak||0}`;
    const av=el('hdr-ava'); if(av && data.is_vip){ av.textContent='👑'; _ensureVipAvatar(); }
  }
}

// ── VIP Telegram avatar (Block 3) ──────────────────────────────────────────────
// Грузим один раз за сессию, кэшируем, применяем к хедеру и карточке профиля.
let _vipAvatar = null, _vipAvatarTried = false;
function _applyVipAvatar() {
  if (!_vipAvatar) return;
  const img = `<img src="${_vipAvatar}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;display:block">`;
  const h = el('hdr-ava'); if (h) h.innerHTML = img;
  const p = el('pro-ava'); if (p) p.innerHTML = img;
}
function _ensureVipAvatar() {
  if (_vipAvatar) { _applyVipAvatar(); return; }
  if (_vipAvatarTried) return;
  _vipAvatarTried = true;
  api('/profile/avatar').then(r => {
    if (r && r.avatar) { _vipAvatar = r.avatar; _applyVipAvatar(); }
  }).catch(()=>{});
}

function showCurrModal() {
  const d = _profileData || {};
  const mora = d.mora ?? 0, dia = d.diamonds ?? 0, dark = d.dark_mora ?? 0, zar = d.zarniki ?? 0;
  OM('💰 Валюты', `<div class="curr-modal">
    <div class="cm-block">
      <div class="cm-icon">🪙</div>
      <div class="cm-info">
        <div class="cm-name">Мора <span class="cm-val">${fmtF(mora)}</span></div>
        <div class="cm-desc">Основная валюта. Зарабатывай в чатах, дуэлях, квестах и на аукционе.</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">💎</div>
      <div class="cm-info">
        <div class="cm-name">Алмазы <span class="cm-val">${fmtF(dia)}</span></div>
        <div class="cm-desc">Премиум валюта. Покупай в Магазине или получай за достижения и ивенты.</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">🌑</div>
      <div class="cm-info">
        <div class="cm-name">Тёмная Мора <span class="cm-val">${fmtF(dark)}</span></div>
        <div class="cm-desc">Редкая валюта тёмного рынка. Получай через Контрабанду (раз в 4 дня).</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">✨</div>
      <div class="cm-info">
        <div class="cm-name">Зарники <span class="cm-val">${fmtF(zar)}</span></div>
        <div class="cm-desc">Донат-валюта — нельзя заработать в игре. Открывает эксклюзивные темы и предметы.</div>
      </div>
    </div>
  </div>`, [{l:'Закрыть', c:'btn-ghost', f:'CM()'}]);
}

function showCurrBar(show) {
  // Редизайн v5: хедер с валютами и кнопкой пополнения виден ВСЕГДА (донат на виду).
  _currBarVisible = true;
}

el('curr-bar')?.addEventListener('click', showCurrModal);

// Refresh bar data from server (called on a slow timer)
function refreshCurrBar() {
  if (!_uid || !_currBarVisible) return;
  api('/profile/me').then(d => {
    updateCurrBar(d);
    if(d.mora!==undefined) _profileData = {...(_profileData||{}), mora:d.mora, diamonds:d.diamonds};
  }).catch(()=>{});
}
setInterval(refreshCurrBar, 90000); // every 90s

// Mirrors services/streak.py:calc_streak_reward
function calcStreakReward(streak) {
  if(streak<=0) streak=1;
  const BLOCK=7, BASE_M=70, BASE_D=0.15, BONUS=4.0;
  const cycle=Math.floor((streak-1)/BLOCK);
  const dayInBlock=((streak-1)%BLOCK)+1;
  const isEnd=(dayInBlock===BLOCK);
  const logMult=1.0+0.5*Math.log(1.0+cycle);
  const blockMult=isEnd?BONUS:1.0;
  return {
    mora:Math.round(BASE_M*logMult*blockMult*100)/100,
    dia:Math.round(BASE_D*logMult*blockMult*100)/100,
    dayInBlock, isEnd, cycle,
  };
}

function plDays(n){n=Math.abs(n)%100;const d=n%10;if(n>10&&n<20)return'дней';if(d===1)return'день';if(d>=2&&d<=4)return'дня';return'дней';}
function loadStreak() {
  el('pro-streak').innerHTML='<div class="loader">Загрузка...</div>';
  api('/streak/calendar').then(d=>{
    const today=new Date().toISOString().slice(0,10);
    const streak=d.streak||0;
    const cur=calcStreakReward(streak||1);
    const dayInBlock=cur.dayInBlock;            // позиция дня в текущем блоке (1..7)
    const cycleStart=cur.cycle*7;               // номер стрика дня 1 текущего блока
    const blockPct=Math.round(dayInBlock/7*100);
    const toBonus=7-dayInBlock;
    const nextRw=calcStreakReward(streak+1);

    // 7-дневный трек блока: завершён / текущий / бонус / будущий
    const track=Array.from({length:7},(_,i)=>{
      const pos=i+1, rw=calcStreakReward(cycleStart+pos);
      const done=streak>0 && pos<dayInBlock;
      const isCur=streak>0 && pos===dayInBlock;
      let cls='st-day'; if(done)cls+=' done'; if(isCur)cls+=' cur'; if(rw.isEnd)cls+=' bonus';
      return `<div class="${cls}">
        <div class="st-day-n">${pos}${rw.isEnd?' ★':''}</div>
        <div class="st-day-r">${fmt(Math.round(rw.mora))}🪙</div>
        ${rw.dia>0?`<div class="st-day-d">${fmtF(rw.dia)}💎</div>`:''}
        ${done?'<div class="st-day-chk">✓</div>':''}</div>`;
    }).join('');

    // Хитмап активности (интенсивность по числу сообщений)
    const cells=d.calendar.map(day=>{
      const c=day.count||0; let lvl=0;
      if(c>0)lvl=1; if(c>=5)lvl=2; if(c>=20)lvl=3; if(c>=50)lvl=4;
      return `<div class="st-cell l${lvl}${day.date===today?' today':''}" title="${day.date}: ${c} сообщ."></div>`;
    }).join('');

    el('pro-streak').innerHTML=`
    <div class="st-hero">
      <div class="st-flame">🔥</div>
      <div class="st-big">${streak}</div>
      <div class="st-sub">${plDays(streak)} подряд · единый на все чаты</div>
      <div class="st-blockbar"><div class="st-blockfill" style="width:${blockPct}%"></div></div>
      <div class="st-blocklabel">Блок #${cur.cycle+1} · день ${dayInBlock}/7 ${toBonus>0?'· до бонуса '+toBonus+' '+plDays(toBonus):'· 🎉 бонусный день!'}</div>
    </div>

    <div class="card" style="margin-top:10px">
      <div class="card-title">🎁 Завтра — день ${streak+1}</div>
      <div class="st-next">
        <span class="st-next-m">+${fmt(Math.round(nextRw.mora))} 🪙</span>
        ${nextRw.dia>0?`<span class="st-next-d">+${fmtF(nextRw.dia)} 💎</span>`:''}
        ${nextRw.isEnd?'<span class="st-next-b">★ БОНУС ×4</span>':''}
      </div>
      <div class="st-track">${track}</div>
      <div style="font-size:10px;color:var(--muted);margin-top:7px">Пиши хотя бы одно сообщение в день в любом чате — стрик растёт. Пропуск дня сбрасывает блок (можно восстановить: «бот стрик восстановить»).</div>
    </div>

    <div class="card" style="margin-top:10px">
      <div class="card-title">📅 Активность · 60 дней</div>
      <div class="st-heat">${cells}</div>
      <div class="st-legend"><span>меньше</span>
        <i class="st-cell l0"></i><i class="st-cell l1"></i><i class="st-cell l2"></i><i class="st-cell l3"></i><i class="st-cell l4"></i>
        <span>больше</span></div>
    </div>`;
  }).catch(e=>{el('pro-streak').innerHTML=`<div style="color:var(--red);padding:10px;font-size:12px">${typeof e==='string'?esc(e):'Ошибка загрузки'}</div>`;});
}

// What each achievement tracks and how to earn it
const ACH_HOW = {
  gacha_addict:{
    how:   'Крутите гачу',
    where: 'Арена → Гача → выберите тип крутки',
    note:  'Засчитывается каждый спин, включая жетоны',
  },
  collector:   {
    how:   'Получите новые виды питомцев',
    where: 'Крутите Гачу — каждый новый вид засчитывается',
    note:  'Важен именно НОВЫЙ вид, не дубликаты существующего',
  },
  trainer:     {
    how:   'Прокачайте питомца до максимального Lv10',
    where: 'Получайте дубликаты из Гачи — уровень растёт',
    note:  'Нужны дубликаты: Common ×10→Lv10, Epic ×4→Lv10 и т.д.',
  },
  wanderer:    {
    how:   'Отправляйте питомцев в экспедиции',
    where: 'Зоопарк → нажмите на питомца → «бот поход»',
    note:  'Засчитывается каждое завершение похода (не старт)',
  },
  persistent:  {
    how:   'Поддерживайте ежедневный стрик',
    where: 'Пишите хотя бы одно сообщение в боте каждый день',
    note:  'Счётчик — максимальный стрик за всё время, не текущий',
  },
  vow_keeper:  {
    how:   'Пробудьте в браке суммарно N дней',
    where: 'Оформите брак: «бот брак, @username» в чате',
    note:  'Счётчик идёт автоматически каждый день пока вы в браке. Суммируется по всем бракам.',
  },
  patron:      {
    how:   'Потратьте Мору в магазине бота',
    where: 'Рынок → Магазин → купите любые предметы',
    note:  'Засчитывается сумма всех покупок в магазине (бот магазин)',
  },
  magnate:     {
    how:   'Накопите максимальный баланс Моры',
    where: 'Зарабатывайте Мору всеми способами, не тратьте',
    note:  'Трекается МАКСИМАЛЬНЫЙ баланс когда-либо, не текущий',
  },
  treasury:    {
    how:   'Накопите максимальный баланс Алмазов',
    where: 'Получайте Алмазы из стрика, ачивок, гачи',
    note:  'Трекается МАКСИМАЛЬНЫЙ баланс когда-либо, не текущий',
  },
  dealer:      {
    how:   'Продайте лоты на аукционе',
    where: 'Рынок → Аукцион → «+ Выставить» → дождитесь покупки',
    note:  'Засчитывается только успешная продажа (кто-то купил)',
  },
  lucky_one:   {
    how:   'Побеждайте в мини-играх',
    where: '«бот кости», «бот монета», «бот число», «бот рулетка»',
    note:  'Засчитывается каждая победа в любой мини-игре',
  },
  duelist:     {
    how:   'Побеждайте в дуэлях',
    where: '«бот дуэль, @соперник, [ставка]» — вызов на дуэль',
    note:  'Засчитывается только победа, не ничья',
  },
  talker:      {
    how:   'Пишите сообщения в чатах с ботом',
    where: 'Любой чат где есть бот — просто общайтесь',
    note:  'Суммируются сообщения из ВСЕХ чатов (глобальный счётчик)',
  },
  star:        {
    how:   'Будьте топ-1 в чате по активности за неделю',
    where: 'Пишите больше всех в чате в течение недели',
    note:  'Засчитывается каждая неделя когда вы на 1-м месте',
  },
};

function loadAch() {
  el('pro-ach').innerHTML='<div class="loader">Загрузка...</div>';
  api('/achievements/').then(achs=>{
    _achData=achs;
    renderAch();
  }).catch(e=>{el('pro-ach').innerHTML=`<div style="color:var(--red);padding:10px;font-size:12px">${e}</div>`;});
}
function setAchSort(s){_achSort=s;renderAch();}
function renderAch() {
  if(!_achData) return;
  let achs=[..._achData];
  if(_achSort==='progress') achs.sort((a,b)=>b.pct-a.pct);
  else if(_achSort==='todo') achs.sort((a,b)=>(a.completed?1:0)-(b.completed?1:0)||b.pct-a.pct);
  const done=achs.filter(a=>a.completed).length;
  el('pro-ach').innerHTML=`
    <div style="display:flex;gap:4px;margin-bottom:10px;align-items:center;flex-wrap:wrap">
      <span style="font-size:10px;color:var(--muted);margin-right:2px">Сорт:</span>
      <button class="btn btn-sm ${_achSort==='default'?'btn-gold':'btn-ghost'}" style="padding:3px 7px;font-size:9px" onclick="setAchSort('default')">По умолч.</button>
      <button class="btn btn-sm ${_achSort==='progress'?'btn-gold':'btn-ghost'}" style="padding:3px 7px;font-size:9px" onclick="setAchSort('progress')">% прогресса</button>
      <button class="btn btn-sm ${_achSort==='todo'?'btn-gold':'btn-ghost'}" style="padding:3px 7px;font-size:9px" onclick="setAchSort('todo')">Сначала активные</button>
    </div>
    <div class="card">
      <div class="card-title">Достижения <span style="font-size:9px;font-weight:400;color:${done===achs.length?'var(--green)':'var(--muted)'}">${done} / ${achs.length} ✅</span></div>
      ${achs.map(a=>{
        const hw=ACH_HOW[a.id]||{};
        const fc=a.completed?'high':a.pct>=60?'high':a.pct>=25?'':'low';
        return `<div class="ach-item" style="cursor:pointer" onclick="openAchModal(${JSON.stringify(a).replace(/"/g,"'")})">
          <div class="ach-head">
            <div class="ach-icon">${a.icon}</div>
            <div class="ach-name">${a.name}</div>
            <div class="ach-lvl" style="color:${a.completed?'var(--gold)':a.level>0?'var(--green)':'var(--muted)'}">
              ${a.completed?'★ MAX':a.level>0?`Lv${a.level}`:'—'}
            </div>
          </div>
          <div style="font-size:10px;color:var(--muted);margin-bottom:5px">${hw.how||''}</div>
          <div class="ach-bar"><div class="ach-fill ${fc}" style="width:${a.pct}%"></div></div>
          <div class="ach-prog">${fmt(a.progress)} / ${fmt(a.next_threshold||a.progress)}${a.completed?' ✅':''}</div>
        </div>`;
      }).join('')}
    </div>`;
}

function openAchModal(a) {
  const hw=ACH_HOW[a.id]||{};
  const rw=a.next_reward||{};
  const rwParts=[rw.mora&&`+${fmt(rw.mora)} 🪙`,rw.diamonds&&`+${rw.diamonds} 💎`].filter(Boolean).join(', ');
  OM(`${a.icon} ${a.name}`,`
    <div style="text-align:center;padding:8px 0 14px">
      <div style="font-size:28px;font-weight:800;color:${a.completed?'var(--gold)':'var(--text)'}">
        ${a.completed?'★ МАКСИМУМ':`Lv${a.level} / ${a.max_level}`}
      </div>
      <div class="ach-bar" style="height:8px;margin:10px 0 4px">
        <div class="ach-fill" style="width:${a.pct}%"></div>
      </div>
      <div style="font-size:12px;color:var(--muted)">${fmt(a.progress)} / ${fmt(a.next_threshold||a.progress)}</div>
    </div>
    <div class="divider"></div>
    <div class="irow"><span class="ik">Что нужно</span><span style="color:var(--text);text-align:right;max-width:65%;font-size:11px">${hw.how||'—'}</span></div>
    <div class="irow"><span class="ik">Где</span><span style="color:var(--teal);text-align:right;max-width:65%;font-size:11px">${hw.where||'—'}</span></div>
    ${hw.note?`<div style="background:var(--dim);border-radius:var(--r);padding:8px 10px;margin-top:8px;font-size:11px;color:var(--muted);line-height:1.4">💡 ${hw.note}</div>`:''}
    ${!a.completed&&rwParts?`<div class="irow" style="margin-top:8px"><span class="ik">Награда Lv${a.level+1}</span><span style="color:var(--gold)">${rwParts}</span></div>`:''}
    ${a.completed?`<div style="text-align:center;padding:10px;color:var(--gold);font-size:13px;font-weight:600">🏆 Выполнено полностью!</div>`:''}
  `,[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}

