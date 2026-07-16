// ── Конструктор «Внешний вид» (косметика профиля) ──────────────────────────────
const _LOOKS_SLOTS=['name_glow','avatar_frame','avatar_halo','title','profile_bg','card_fx'];
const _LOOKS_SLOT_LABEL={name_glow:'✨ Ореол имени',avatar_frame:'🖼 Рамка аватара',avatar_halo:'🌟 Гало аватара',title:'🏷 Титул',profile_bg:'🖌 Фон профиля',card_fx:'❄️ Частицы карточки',welcome:'🎬 Приветствие'};
const _LOOKS_TABS=[..._LOOKS_SLOTS,'welcome'];
let _looksData=null, _looksSel={}, _looksSaved={}, _looksDirty=false;
let _looksPresets=[];  // кэш пресетов текущей сессии
let _looksActiveTab=_LOOKS_SLOTS[0];   // какая вкладка сейчас открыта в модалке
let _looksFilter='all';                // фильтр редкости — общий для всех вкладок, не сбрасывается при переключении
function openLooksModal(){
  _looksDirty=false;
  _looksActiveTab=_LOOKS_SLOTS[0]; _looksFilter='all';
  OM('🎨 Внешний вид','<div class="loader">Загрузка...</div>',[{l:'Готово',c:'btn-ghost',f:'_looksClose()'}]);
  Promise.all([api('/cosmetics/'),api('/cosmetics/presets')])
    .then(([d,pr])=>{_looksData=d;_looksSaved=_looksEquipped(d);_looksSel={..._looksSaved};_looksPresets=pr.presets||[];renderLooks();})
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
function _rarLabel(r){return rarLabel(r);}
function _srcLabel(s){return {vip:'🎁 даётся с VIP',bp:'🎫 платный БП',reward:'🏅 за достижение',shop:''}[s]||'';}
function _looksPriceTxt(opt){ return Object.entries(opt).map(([cur,amt])=>`${amt}${(_looksData.currency_icons||{})[cur]||cur}`).join('+'); }
function renderLooks(){
  const b=el('mb'); if(!b||!_looksData) return;
  const vipBar=_looksData.vip?'':`<div class="looks-vipbar">
    <span>👑 Купить можно любую косметику. Редкая и выше (🟣+) <b>отображается на профиле только с VIP</b>.</span>
    <button class="btn btn-sm btn-gold" onclick="CM();goTo('market','vip')">Перейти к VIP</button></div>`;
  b.innerHTML=`<div id="looks-top">${_looksPreviewHtml()}</div>`+vipBar
    +'<button class="btn btn-ghost btn-full" style="margin:2px 0 10px" onclick="_openSurprisesModal()">🎁 Сюрпризы и 🔹 Крафт косметики</button>'
    +_looksPresetsHtml()+_looksTabsHtml()+'<div id="looks-tabpanel"></div>'
    +`<div class="pay-terms">Покупая косметику, вы соглашаетесь с <a href="${BASE}/legal/tos" target="_blank" rel="noopener">Соглашением</a>. Цифровые товары возврату не подлежат.</div>`;
  _looksRenderActiveTab();
}
// Панель вкладок слотов — переиспользует .tabs/.tb (тот же паттерн, что и в Маркете).
function _looksTabsHtml(){
  return `<div class="tabs" id="looks-tabs">${_LOOKS_TABS.map(t=>
    `<button class="tb${t===_looksActiveTab?' active':''}" onclick="_looksSwitchTab('${t}',this)">${_LOOKS_SLOT_LABEL[t]}</button>`
  ).join('')}</div>`;
}
function _looksSwitchTab(tab,btn){
  _looksActiveTab=tab;
  document.querySelectorAll('#looks-tabs .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  _looksRenderActiveTab();
}
function _looksFilterHtml(){
  const rarities=['all',...Object.keys(RARITY_META)];
  return `<div class="looks-filter">${rarities.map(r=>
    `<button class="looks-chip${r===_looksFilter?' active':''}" onclick="_looksSetFilter('${r}')">${r==='all'?'Все':rarLabel(r)}</button>`
  ).join('')}</div>`;
}
function _looksSetFilter(r){ _looksFilter=r; _looksRenderActiveTab(); }
// Горячий путь: перерисовывает ТОЛЬКО панель активной вкладки (не всю модалку).
function _looksRenderActiveTab(){
  const p=el('looks-tabpanel'); if(!p) return;
  if(_looksActiveTab==='welcome'){
    p.innerHTML=_looksWelcomeHtml();
    _playWelcomePreview(_looksData.welcome&&_looksData.welcome.current);
    return;
  }
  p.innerHTML=_looksFilterHtml()+_looksGridHtml(_looksActiveTab);
}
// Горячий путь: перерисовывает только блок «сейчас→станет» (не всю модалку).
function _looksRenderTop(){
  const t=el('looks-top'); if(!t) return;
  t.innerHTML=_looksPreviewHtml();
}
// Мини-карточка профиля из набора слотов sel — общий рендерер для всех размеров:
// size='mini' (сравнение «Сейчас→Станет»), size='hero' (витрина примерки, крупный
// план), без size — обычный (карточка «Сейчас» в витрине примерки).
// Раньше было 2 независимые копии этой функции (расходились только CSS-модификатором
// размера) — снесены в одну, чтобы не плодить точки будущего расхождения разметки.
function _looksRenderCard(sel,size){
  const d=_looksData;
  const glow=_looksCos(sel.name_glow), frame=_looksCos(sel.avatar_frame), title=_looksCos(sel.title);
  const halo=_looksCos(sel.avatar_halo), bg=_looksCos(sel.profile_bg), fx=_looksCos(sel.card_fx);
  const sizeCls=size==='mini'?' looks-preview--mini':size==='hero'?' looks-preview--hero':'';
  return `<div class="looks-preview${sizeCls} ${bg?bg.css:''}">
    ${fx?`<div class="card-fx ${fx.css}"></div>`:''}
    <div class="ava ${frame?frame.css:''} ${halo?halo.css:''}">${d.vip?'👑':'🔮'}</div>
    <div class="pname ${glow?glow.css:''}">@${esc((_profileData&&_profileData.username)||'Игрок')}</div>
    ${title?`<div class="ptitle${title.css?' '+title.css:''}">${esc(title.text||title.name)}</div>`:''}
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
      <div class="looks-ba-col"><div class="looks-ba-lbl">Сейчас</div>${_looksRenderCard(_looksSaved,'mini')}</div>
      <div class="looks-ba-arrow">${changed?'➜':'='}</div>
      <div class="looks-ba-col"><div class="looks-ba-lbl ${changed?'looks-ba-lbl--new':''}">Станет</div>${_looksRenderCard(_looksSel,'mini')}</div>
    </div>${actions}`;
}
// Топ-редкость слота среди ещё НЕ купленного — витрина-спотлайт (только при фильтре «Все»).
function _looksSpotlight(slot){
  if(_looksFilter!=='all') return null;
  const cand=(_looksData.slots[slot]||[]).filter(it=>!it.owned);
  if(!cand.length) return null;
  const order=Object.keys(RARITY_META);
  cand.sort((a,b)=>order.indexOf(b.rarity)-order.indexOf(a.rarity));
  return cand[0];
}
function _looksGridHtml(slot){
  const spot=_looksSpotlight(slot);
  const items=(_looksData.slots[slot]||[]).filter(it=>
    (_looksFilter==='all'||it.rarity===_looksFilter) && (!spot||it.id!==spot.id));
  const spotHtml=spot?`<div class="looks-spotlight">${_looksCard(slot,spot,true)}</div>`:'';
  const none=`<div class="looks-card ${_looksSel[slot]?'':'sel'}" onclick="_looksUnequip('${slot}')">
    <div class="lc-sw lc-sw--none">✖</div><div class="lc-name">Без</div></div>`;
  const empty=items.length?'':'<div class="looks-empty">Нет предметов этой редкости</div>';
  return `${spotHtml}<div class="looks-cards">${none}${items.map(it=>_looksCard(slot,it)).join('')}${empty}</div>`;
}
// Мини-превью реального эффекта в карточке (а не просто текст).
function _looksSwatch(slot,it){
  const c=it.css||'';
  const face=(_looksData&&_looksData.vip)?'👑':'🔮';
  switch(slot){
    case 'name_glow':    return `<div class="lc-sw"><span class="lc-nick ${c}">@Ник</span></div>`;
    case 'title':        return `<div class="lc-sw"><span class="lc-title${it.css?' '+it.css:''}">${esc(it.text||it.name)}</span></div>`;
    case 'avatar_frame':
    case 'avatar_halo':  return `<div class="lc-sw"><span class="lc-ava ${c}">${face}</span></div>`;
    case 'profile_bg':   return `<div class="lc-sw lc-bg ${c}"></div>`;
    case 'card_fx':      return `<div class="lc-sw"><div class="card-fx ${c}"></div></div>`;
    default:             return `<div class="lc-sw"></div>`;
  }
}
function _looksCard(slot,it,spotlight){
  const sel=_looksSel[slot]===it.id;
  const sw=_looksSwatch(slot,it);
  const rar=`<span class="lc-rar">${_rarLabel(it.rarity)}</span>`;
  const spotBadge=spotlight?'<div class="lc-spot-badge">★ Топ слота</div>':'';
  if(it.owned){
    const offBadge=it.vip_locked_inactive?'<span class="lc-vip-off">⏸ нужна VIP</span>':'';
    return `<div class="looks-card r-${it.rarity} ${sel?'sel':''} ${it.vip_locked_inactive?'lc-dim':''}" onclick="_looksEquip('${slot}','${it.id}')">
      ${spotBadge}${sw}<div class="lc-name">${esc(it.name)}</div>
      <div class="lc-foot">${rar}${offBadge}${(!it.vip_locked_inactive&&_looksSaved[slot]===it.id)?'<span class="lc-on">✓ надето</span>':''}</div></div>`;
  }
  // Непокупленный предмет — кнопка «Примерить» открывает превью-модалку
  const vip=it.vip_required?'<span class="lc-vip">VIP</span>':'';
  const priceTxt=it.price&&it.price.length?`<span class="lc-price-hint">${_looksPriceTxt(it.price[0])} ✨</span>`:'';
  return `<div class="looks-card r-${it.rarity} locked lc-buyable" onclick="_showCosmeticPreview('${slot}','${it.id}')">
    ${spotBadge}${sw}<div class="lc-name">🔒 ${esc(it.name)} ${vip}</div>
    <div class="lc-foot">${rar}${priceTxt}<span class="lc-prev-hint">👁</span></div></div>`;
}
// Превью-модалка (витрина примерки): полноэкранный показ косметики до покупки,
// с пролистыванием ‹/› по остальным предметам того же слота+фильтра (без выхода
// в сетку и обратно — чисто по уже закэшированным _looksData, без новых запросов).
let _cosPrevSlot=null, _cosPrevList=[], _cosPrevIdx=0;
function _showCosmeticPreview(slot,id){
  if(!_looksData) return;
  const all=_looksData.slots[slot]||[];
  _cosPrevSlot=slot;
  _cosPrevList=_looksFilter==='all'?all:all.filter(it=>it.rarity===_looksFilter);
  const idx=_cosPrevList.findIndex(it=>it.id===id);
  _cosPrevIdx=idx>=0?idx:0;
  _renderCosmeticPreview();
}
function _cosPrevNav(dir){
  if(!_cosPrevList.length) return;
  _cosPrevIdx=(_cosPrevIdx+dir+_cosPrevList.length)%_cosPrevList.length;
  _renderCosmeticPreview();
}
function _renderCosmeticPreview(){
  const it=_cosPrevList[_cosPrevIdx]; if(!it) return;
  const slot=_cosPrevSlot;

  // «После» — показываем только выбранный слот поверх текущего набора, крупным планом
  const afterSel=Object.assign({},_looksSaved); afterSel[slot]=it.id;
  const beforeCard=_looksRenderCard(_looksSaved);
  const afterCard=_looksRenderCard(afterSel,'hero');

  const rc_=rarColor(it.rarity), rl_=rarLabel(it.rarity);
  const bal=_looksData.balances||{};

  let priceHtml='';
  if(it.owned){
    priceHtml=`<div class="cos-prev-lock">${_looksSaved[slot]===it.id?'✓ уже надето':'✓ уже в коллекции'}</div>`;
  } else if(it.price&&it.price.length){
    const opt=it.price[0];
    const can=Object.entries(opt).every(([cur,amt])=>(bal[cur]||0)>=amt);
    const lbl=_looksPriceTxt(opt)+' ✨';
    const zarBtn=`<button class="btn btn-gold cos-prev-buy${can?'':' lc-buy--no'}" onclick="_looksBuyFromPreview('${it.id}',0,'${slot}')">${can?'✨ Купить за':'🚫 Нужно'} ${lbl}</button>`;
    const nomoney=!can?`<div class="cos-prev-nomoney">Нет зарников? Пополни через раздел VIP/Зарники ✨</div>`:'';
    const vipWarn=(!_looksData.vip&&it.rarity&&it.rarity!=='common')
      ?`<div class="cos-prev-vipwarn">⚠️ Без VIP-подписки косметика сохранится в инвентаре, но не будет отображаться на профиле.
        <button class="btn btn-xs btn-gold" onclick="CM();goTo('market','vip')">Получить VIP ›</button></div>` : '';
    priceHtml=`<div class="cos-prev-price">${zarBtn}${nomoney}${vipWarn}</div>`;
  } else {
    priceHtml=`<div class="cos-prev-lock">${_srcLabel(it.source)||'Не продаётся'}</div>`;
  }

  const body=`<div class="cos-prev-modal">
    <div class="cos-prev-header">
      <span class="cos-prev-rar" style="color:${rc_}">${rl_}</span>
      <span class="cos-prev-name">${esc(it.name)}</span>
    </div>
    <div class="cos-prev-desc">${esc(it.desc||'')}</div>
    <div class="cos-prev-cards">
      <div class="cos-prev-col"><div class="cos-prev-lbl">Сейчас</div>${beforeCard}</div>
      <div class="cos-prev-arrow">✨</div>
      <div class="cos-prev-col cos-prev-col--hero"><div class="cos-prev-lbl cos-prev-lbl--new">Станет</div>${afterCard}</div>
    </div>
    ${priceHtml}
  </div>`;

  const nav=_cosPrevList.length>1;
  OM('👁 Примерка',body,[
    ...(nav?[{l:'‹',c:'btn-ghost',f:'_cosPrevNav(-1)'}]:[]),
    {l:'← Назад',c:'btn-ghost',f:'openLooksModal()'},
    ...(nav?[{l:'›',c:'btn-ghost',f:'_cosPrevNav(1)'}]:[]),
  ]);
}
function _looksBuyFromPreview(id,opt,slot){
  api('/cosmetics/buy',{method:'POST',body:JSON.stringify({cosmetic_id:id,option_index:opt})})
    .then(r=>{toast(r.message); refreshCurrBar(); _looksDirty=true;
      return api('/cosmetics/equip',{method:'POST',body:JSON.stringify({cosmetic_id:id})});})
    .then(()=>{toast('✅ Надето!'); openLooksModal();})
    .catch(e=>toast(e,false));
}

function _looksEquip(slot,id){ _looksSel[slot]=id; _looksRenderTop(); _looksRenderActiveTab(); }
function _looksUnequip(slot){ _looksSel[slot]=null; _looksRenderTop(); _looksRenderActiveTab(); }
function _looksReset(){ _looksSel={..._looksSaved}; _looksRenderTop(); _looksRenderActiveTab(); }

// ── Пресеты образов ────────────────────────────────────────────────────────────
function _looksPresetsHtml(){
  const chips=_looksPresets.map(p=>`<span class="looks-preset-chip">
    <button class="btn-plain looks-preset-name" onclick="_applyPreset(${p.id})" title="Применить образ">${esc(p.name)}</button>
    <button class="btn-plain looks-preset-del" onclick="_deletePreset(${p.id})" title="Удалить">✕</button>
  </span>`).join('');
  const saveBtn=`<button class="btn btn-sm btn-ghost looks-preset-save" onclick="_savePreset()">💾 Сохранить образ</button>`;
  if(!_looksPresets.length) return `<div class="looks-presets"><div class="looks-presets-hint">Нет сохранённых образов</div>${saveBtn}</div>`;
  return `<div class="looks-presets">${chips}${saveBtn}</div>`;
}
// UX_AUDIT С16: bottom-sheet с полем вместо нативного prompt()
function _savePreset(){
  OM('💾 Сохранить образ',
    `<div class="set-hint">Текущая косметика сохранится как образ — потом применишь одним тапом.</div>
     <input id="preset-name-inp" class="num-input" type="text" maxlength="30"
       placeholder="Название образа (до 30 символов)" autocomplete="off" style="margin-top:10px">`,
    [{l:'💾 Сохранить',c:'btn-gold',f:'_savePresetGo()'},{l:'Отмена',c:'btn-ghost',f:'openLooksModal()'}]);
  setTimeout(()=>{const i=el('preset-name-inp'); if(i) i.focus();},60);
}
function _savePresetGo(){
  const name=((el('preset-name-inp')||{}).value||'').trim().slice(0,30)||'Образ';
  api('/cosmetics/presets',{method:'POST',body:JSON.stringify({name})})
    .then(r=>{toast(r.message); if(r.preset){_looksPresets.push(r.preset);} openLooksModal();})
    .catch(e=>toast(e,false));
}
function _applyPreset(id){
  api(`/cosmetics/presets/${id}/apply`,{method:'POST'})
    .then(r=>{toast(r.message); _looksDirty=true; openLooksModal();})
    .catch(e=>toast(e,false));
}
function _deletePreset(id){
  api(`/cosmetics/presets/${id}`,{method:'DELETE'})
    .then(r=>{toast(r.message); _looksPresets=_looksPresets.filter(p=>p.id!==id); renderLooks();})
    .catch(e=>toast(e,false));
}
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
  return `<div id="wpreview" class="wpreview"></div>${hint}
    <div class="looks-cards">${cards}</div>`;
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
  _looksRenderActiveTab(); _looksDirty=true;
  api('/cosmetics/welcome',{method:'POST',body:JSON.stringify({animation_id:id})})
    .then(r=>toast(r.message))
    .catch(e=>{toast(e,false); w.current=prev;
      (w.options||[]).forEach(o=>o.current=(o.id===prev)); _looksRenderActiveTab();});
}
// ── БЛОК21 #3: сундуки-сюрпризы + крафт косметики из осколков ────────────────────
function _openSurprisesModal(){
  OM('🎁 Сюрпризы и Крафт','<div class="loader">Загрузка...</div>',[{l:'← К внешнему виду',c:'btn-ghost',f:'openLooksModal()'}]);
  Promise.all([api('/cosmetics/chests'),api('/cosmetics/craft')]).then(([ch,cr])=>{
    const b=el('mb'); if(!b) return;
    const chests=(ch.chests||[]).map(c=>{
      const odds=(c.odds||[]).map(o=>`<span class="chest-odd ${o.rarity?(RC[o.rarity]||''):''}">${esc(o.label)} · ${o.pct}%</span>`).join('');
      return `<div class="gift-card">
        <div class="gift-name" style="min-height:auto;margin-bottom:6px">${esc(c.name)}</div>
        <div class="chest-odds">${odds}</div>
        <div class="gift-foot" style="margin-top:8px">
          ${c.owned>0?`<button class="btn btn-sm btn-gold" onclick="_openChest('${c.id}',this)">Открыть (${c.owned})</button>`:''}
          <button class="btn btn-sm btn-ghost" onclick="_buyChest('${c.id}')">Купить за ${c.zarniki} ✨</button>
        </div></div>`;
    }).join('');
    const craftItems=(cr.items||[]).map(it=>{
      const foot=it.owned?'<span class="lc-on">✓ есть</span>'
        :`<button class="btn btn-sm ${it.can?'btn-gold':'btn-ghost'}" ${it.can?'':'disabled'} onclick="_craftCosmetic('${it.id}',this)">${it.can?`Скрафтить за ${it.cost} 🔹`:`Нужно ${it.cost} 🔹`}</button>`;
      return `<div class="looks-card r-${it.rarity}${it.owned?' lc-dim':''}">
        ${_looksSwatch(it.slot, it)}<div class="lc-name">${esc(it.name)}</div>
        <div class="lc-foot"><span class="lc-rar">${_rarLabel(it.rarity)}</span>${foot}</div></div>`;
    }).join('');
    b.innerHTML=`<div class="looks-hint">🎁 Сундуки за ✨ дают случайную косметику/расходники; дубль косметики → 🔹 осколки. Из осколков собирай конкретную косметику в Крафте.</div>
      <div class="looks-slot-t">🎁 Сундуки-сюрпризы</div>
      <div class="gift-grid">${chests}</div>
      <div class="looks-slot-t" style="margin-top:14px">🔹 Крафт <span class="clan-coin-note">· осколков: ${cr.shards}</span></div>
      <div class="looks-cards">${craftItems}</div>`;
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
    .then(r=>{ _looksDirty=true; _chestReveal(r.drop||{}); })
    .catch(e=>{toast(e,false); if(btn) btn.disabled=false;});
}
function _chestReveal(d){
  let inner;
  if(d.kind==='cosmetic'){
    const sw = d.slot ? _looksSwatch(d.slot, d) : '';
    inner = `<div class="chest-reveal r-${d.rarity}">
      <div class="chest-reveal-sw">${sw}</div>
      <div class="lc-name" style="font-size:14px;margin-top:10px">${esc(d.name)}</div>
      <span class="lc-rar" style="margin-top:6px">${_rarLabel(d.rarity)}</span></div>`;
  } else {
    inner = `<div class="chest-reveal"><div style="font-size:40px">${d.kind==='shards'?'🔹':'🎁'}</div>
      <div class="lc-name" style="font-size:14px;margin-top:8px">${esc(d.name||'Награда')}</div></div>`;
  }
  OM('🎉 Из сундука выпало!', inner, [{l:'Класс! 🎉',c:'btn-gold',f:'_openSurprisesModal()'}]);
}
function _craftCosmetic(id,btn){
  if(btn) btn.disabled=true;
  api('/cosmetics/craft',{method:'POST',body:JSON.stringify({cosmetic_id:id})})
    .then(r=>{ toast(r.message); _looksDirty=true; _openSurprisesModal(); })
    .catch(e=>{toast(e,false); if(btn) btn.disabled=false;});
}
