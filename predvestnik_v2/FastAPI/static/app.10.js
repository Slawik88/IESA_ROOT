// ── Конструктор «Внешний вид» (косметика профиля) ──────────────────────────────
// Редизайн (блок 7, 2026-07-23): вкладки убраны — один непрерывный скролл по всем
// секциям + чипы-якоря (скроллят к секции, не переключают панель) + прилипающее
// превью сверху, видно всегда. Раньше приходилось листать вкладки И скроллить
// наверх, чтобы увидеть «как оно будет выглядеть» — теперь ни то, ни другое.
const _LOOKS_SLOTS=['name_glow','avatar_frame','avatar_halo','title','profile_bg','card_fx'];
const _LOOKS_SLOT_LABEL={name_glow:'✨ Ореол имени',avatar_frame:'🖼 Рамка аватара',avatar_halo:'🌟 Гало аватара',title:'🏷 Титул',profile_bg:'🖌 Фон профиля',card_fx:'❄️ Частицы карточки'};
const _LOOKS_ANCHOR_LABEL={name_glow:'✨ Ореол',avatar_frame:'🖼 Рамка',avatar_halo:'🌟 Гало',title:'🏷 Титул',profile_bg:'🖌 Фон',card_fx:'❄️ Частицы',welcome:'🎬 Вход',themes:'🎭 Темы'};
const _LOOKS_TRIAL_KEY='pv_looks_trial_v1';
function _looksLoadTrialState(){
  try{
    const raw=JSON.parse(sessionStorage.getItem(_LOOKS_TRIAL_KEY)||'null');
    const ids={}, items={};
    _LOOKS_SLOTS.forEach(slot=>{
      const id=raw&&raw.ids&&raw.ids[slot];
      if(typeof id!=='string'||!/^[a-z0-9_-]{1,100}$/i.test(id)) return;
      ids[slot]=id;
      const meta=raw.items&&raw.items[slot];
      if(!meta||meta.id!==id) return;
      const css=typeof meta.css==='string'&&/^[a-z0-9_-]{0,80}$/i.test(meta.css)?meta.css:'';
      const lineup=typeof meta.lineup==='string'&&/^[a-z0-9_-]{0,40}$/i.test(meta.lineup)?meta.lineup:'';
      items[slot]={id,name:String(meta.name||'Предмет').slice(0,80),text:String(meta.text||'').slice(0,80),css,lineup,
        price:Number.isFinite(Number(meta.price))?Math.max(0,Number(meta.price)):0};
    });
    return {ids,items};
  }catch(e){ return {ids:{},items:{}}; }
}
const _looksRestoredTrial=_looksLoadTrialState();
let _looksData=null, _looksSel={}, _looksSaved={}, _looksDirty=false;
let _looksTrial=_looksRestoredTrial.ids; // некупленная примерка: по одному предмету на каждый слот
let _looksTrialMeta=_looksRestoredTrial.items; // снимок эффекта нужен профилю даже после reload до загрузки каталога
let _looksPreviewDirty=false, _looksLeavePending=false, _looksLeavePass=false;
let _looksPresets=[];  // кэш пресетов текущей сессии
let _looksFilter='all';                // фильтр ЛИНЕЙКИ (id из _looksData.lineups) — общий для ВСЕХ секций разом
let _looksStatus='all';                // фильтр СТАТУСА: all|owned|missing — независимое второе измерение (см. аудит 2026-07-29)
let _looksMode='collections';          // режим отображения: collections|slots — по умолчанию коллекции (Стадия 2)
let _looksDetailLineup=null;   // id открытой коллекции в детальном экране (Стадия 3); null = список карточек
let _looksLastTouchedCosmetic=''; // источник короткого перехода «карточка → примерочная»
let _looksFittingViewTransitionActive=false;
// Редизайн 2026-07-29: редкость (common→artifact) заменена ЛИНЕЙКАМИ (тематические
// коллекции, core/cosmetics.py::LINEUPS) — фильтр/бейджи теперь по линейке, не по
// редкости. `rarity` на предмете остался ТЕХНИЧЕСКИМ полем (ценовой ярус, VIP-гейт,
// see core/cosmetics.py) — r-{rarity} CSS-классы карточек (цвет рамки) поэтому не
// трогал, они по-прежнему осмысленны (ярус линейки=та же цена). Только ВИДИМЫЙ текст
// бейджа сменился с названия редкости на название линейки. Фильтр-чипы теперь ВНУТРИ
// .looks-sticky вместе с превью (не отдельным блоком ниже anchors) — иначе при скролле
// вниз чипы уезжали ПОД прилипшее превью и физически переставали быть кликабельными.
const LINEUP_COLOR = {
  forest:'#7dc47d', threshold:'#c084fc', frost:'#7ad4ff', inferno:'#ff7a3d',
  celestial:'#e8c45a', void:'#ff4d8d', artifact:'#3fe0e0',
  hanami:'#e8a3b6', moon_lotus:'#b9c9ff', ryujin_tide:'#69b8d6',
};
function lineupMeta(id){ return (_looksData&&_looksData.lineups&&_looksData.lineups[id])||null; }
function lineupLabel(id){ const l=lineupMeta(id); return l?l.name:(id||'—'); }
function lineupColor(id){ return LINEUP_COLOR[id]||'#9aa7b8'; }
const _LOOKS_LINEAGE_PRIORITY=['avatar_frame','avatar_halo','card_fx','profile_bg'];
function _looksLineageId(cosmetics){
  const co=cosmetics||{};
  const declared=co.lineage&&typeof co.lineage.id==='string'?co.lineage.id:'';
  if(declared&&LINEUP_COLOR[declared]) return declared;
  for(const slot of _LOOKS_LINEAGE_PRIORITY){
    const id=co[slot]&&typeof co[slot].lineup==='string'?co[slot].lineup:'';
    if(id&&LINEUP_COLOR[id]) return id;
  }
  return '';
}
window._looksLineageStyle=function(cosmetics){
  const id=_looksLineageId(cosmetics); if(!id) return '';
  const color=LINEUP_COLOR[id];
  return `--avatar-lineage:${color};--avatar-lineage-wash:${color}30`;
};
function _looksTrialMetaFromItem(it){
  return {id:it.id,name:it.name||'Предмет',text:it.text||'',css:it.css||'',lineup:it.lineup||'',price:_looksItemPrice(it)};
}
function _looksPersistTrial(){
  try{
    if(Object.keys(_looksTrial).length) sessionStorage.setItem(_LOOKS_TRIAL_KEY,JSON.stringify({ids:_looksTrial,items:_looksTrialMeta}));
    else sessionStorage.removeItem(_LOOKS_TRIAL_KEY);
  }catch(e){}
}
function _looksSetTrial(slot,id){
  const it=_looksCos(id); if(!it) return;
  _looksTrial[slot]=id; _looksTrialMeta[slot]=_looksTrialMetaFromItem(it);
  _looksPreviewDirty=true; _looksPersistTrial();
}
function _looksDropTrial(slot){
  if(!_looksTrial[slot]&&!_looksTrialMeta[slot]) return;
  delete _looksTrial[slot]; delete _looksTrialMeta[slot];
  _looksPreviewDirty=true; _looksPersistTrial();
}
function _looksClearTrial(){
  const had=Object.keys(_looksTrial).length||Object.keys(_looksTrialMeta).length;
  _looksTrial={}; _looksTrialMeta={};
  if(had) _looksPreviewDirty=true;
  _looksPersistTrial();
}
function _looksSanitizeTrial(){
  if(!_looksData) return;
  let changed=false;
  _LOOKS_SLOTS.forEach(slot=>{
    const id=_looksTrial[slot]; if(!id) return;
    const it=(_looksData.slots[slot]||[]).find(item=>item.id===id);
    if(!it||it.owned){ delete _looksTrial[slot]; delete _looksTrialMeta[slot]; changed=true; return; }
    const nextMeta=_looksTrialMetaFromItem(it);
    if(JSON.stringify(_looksTrialMeta[slot]||null)!==JSON.stringify(nextMeta)) changed=true;
    _looksTrialMeta[slot]=nextMeta;
  });
  if(changed) _looksPreviewDirty=true;
  _looksPersistTrial();
}
window._looksProfileCosmeticsPreview=function(serverCosmetics){
  // Черновик примерки сохраняется между экранами, но не маскируется под уже
  // надетую косметику на основном профиле. Там показываем только серверное
  // состояние; возврат к черновику даёт отдельная компактная кнопка.
  return {...(serverCosmetics||{})};
};
window._looksProfileTrialSummary=function(){
  const count=Object.keys(_looksTrial).length; if(!count) return null;
  const noun=count===1?'предмет':count>=2&&count<=4?'предмета':'предметов';
  const total=Object.values(_looksTrialMeta).reduce((sum,it)=>sum+(Number(it.price)||0),0);
  return {count,noun,total};
};
window._looksGuardPageLeave=function(resume){
  if(_looksLeavePass){ _looksLeavePass=false; return false; }
  if(_looksLeavePending) return true;
  _looksLeavePending=true;
  const apply=_looksChanged()?_looksApply():Promise.resolve();
  apply.then(()=>((_looksDirty||_looksPreviewDirty)?loadProfile():null)).then(()=>{
    _looksDirty=false; _looksPreviewDirty=false; _looksLeavePending=false; _looksLeavePass=true; resume();
  }).catch(e=>{ _looksLeavePending=false; toast(e,false); });
  return true;
};
// Полноэкранный экран «Внешний вид» (был модалкой). Имя openLooksModal сохранено —
// его зовут старые точки входа (профиль/маркет), диплинки и «назад» из под-шитов.
function openLooksModal(){
  _looksFilter='all'; _looksStatus='all'; _looksSearch=''; _looksDetailLineup=null;
  if(!_looksData){   // режим восстанавливаем только на «холодном» открытии — не сбрасывать выбор пользователя, если он уже листает вкладку
    try{ const saved=localStorage.getItem('pv_looks_mode'); if(saved==='collections'||saved==='slots') _looksMode=saved; }catch(e){}
  }
  switchPage('looks');
  if(_looksData){ _looksSanitizeTrial(); renderLooks(); return; } // из кэша — БЕЗ пере-запроса (убирает лаги навигации)
  _looksDirty=false;
  const b=el('pg-looks'); if(b) b.innerHTML='<div class="loader" style="margin-top:44px">Загрузка…</div>';
  Promise.all([api('/cosmetics/'),api('/cosmetics/presets')])
    .then(([d,pr])=>{_looksData=d;_looksSaved=_looksEquipped(d);_looksSel={..._looksSaved};_looksPresets=pr.presets||[];_looksSanitizeTrial();renderLooks();})
    .catch(e=>{const bb=el('pg-looks'); if(bb)bb.innerHTML=`<div class="err" style="margin:16px">${e}</div>`;});
}
const _LOOKS_MODE_LABEL={collections:'🗂 По коллекциям',slots:'📚 По слотам'};
function _looksModeToggleHtml(){
  return `<div class="mode-toggle" id="looks-mode-toggle">
    ${Object.keys(_LOOKS_MODE_LABEL).map(m=>`<button class="mode-toggle-btn${m===_looksMode?' on':''}" data-mode="${m}" type="button" onclick="_looksSetMode('${m}')">${_LOOKS_MODE_LABEL[m]}</button>`).join('')}
  </div>`;
}
function _looksSetMode(mode){
  if(mode===_looksMode) return;
  _looksMode=mode;
  try{ localStorage.setItem('pv_looks_mode', mode); }catch(e){}
  renderLooks();
}
function _looksClose(){   // стрелка ‹: сохранить изменения и вернуться именно к странице-источнику
  // Общий guard в switchPage обрабатывает и эту стрелку, и нижнюю навигацию.
  // Так любой путь выхода одинаково применяет купленные предметы и сохраняет примерку.
  if(_navStack.length) navBack(); else goTo('profile');
}
function _looksEquipped(d){
  const sel={};
  _LOOKS_SLOTS.forEach(s=>{const eq=(d.slots[s]||[]).find(it=>it.equipped); sel[s]=eq?eq.id:null;});
  return sel;
}
function _looksCos(id){ if(!id||!_looksData)return null; for(const s of _LOOKS_SLOTS){const f=(_looksData.slots[s]||[]).find(it=>it.id===id); if(f)return f;} return null; }
function _rarLabel(r){return rarLabel(r);}
function _srcLabel(s){return {vip:'🎁 даётся с VIP',bp:'🎫 платный БП',reward:'🏅 за достижение',shop:''}[s]||'';}
function _looksPriceTxt(opt){ return Object.entries(opt).map(([cur,amt])=>`${amt}${(_looksData.currency_icons||{})[cur]||cur}`).join('+'); }
function renderLooks(){
  const b=el('pg-looks'); if(!b||!_looksData) return;
  const isDetail=!!_looksDetailLineup;
  const vipBar=_looksData.vip?'':`<div class="looks-vipbar">
    <span>👑 Купить можно любую косметику. Линейки дороже «Лесного Странника» <b>отображаются на профиле только с VIP</b>.</span>
    <button class="btn btn-sm btn-gold" onclick="goTo('market','vip')">Перейти к VIP</button></div>`;
  const modeBody=_looksMode==='collections'?_looksCollectionsViewHtml():_looksSlotsViewHtml();
  // Примерочная живёт в отдельном viewport-dock, который _looksRenderFab()
  // порталит прямо в body. Внутри .page его нельзя оставлять: animation:rise
  // создаёт transform-контейнер, из-за которого fixed/sticky в Telegram WebView
  // перестаёт быть надёжно привязан к экрану. Sticky здесь только для фильтра.
  const stickyFilterBar = _looksMode==='slots' ? `<div class="looks-sticky"><div id="looks-filter-bar">${_looksFilterHtml()}</div></div>` : '';
  b.innerHTML=`
    <div class="looks-head">
      ${isDetail?'':'<button class="looks-back" onclick="_looksClose()" aria-label="Назад">‹</button>'}
      <div class="looks-htitle">🎨 Внешний вид</div>
    </div>
    ${isDetail?'':_looksModeToggleHtml()}
    ${isDetail?'':stickyFilterBar}`
    +(isDetail?'':vipBar)
    +(isDetail?'':`<button class="looks-surprises-entry" type="button" onclick="_openSurprisesModal()">
        <span class="looks-surprises-medallion" aria-hidden="true">🎁</span>
        <span class="looks-surprises-copy"><span>Сюрпризы и крафт</span><small>Сундуки, осколки и косметика</small></span>
        <span class="looks-surprises-arrow" aria-hidden="true">›</span>
      </button>`)
    +(isDetail?'':_looksPresetsHtml())
    +(isDetail?'':_looksQuickLinksHtml())
    +`<div id="looks-mode-body">${modeBody}</div>`
    +(isDetail?'':`<div id="looks-common-sections">${_looksWelcomeSectionHtml()}${_looksThemesSectionHtml()}</div>`)
    +`<div class="pay-terms">Покупая косметику, вы соглашаетесь с <a href="${BASE}/legal/tos" target="_blank" rel="noopener">Соглашением</a>. Цифровые товары возврату не подлежат.</div>`;
  if(!isDetail){
    _playWelcomePreview(_looksData.welcome&&_looksData.welcome.current);
    _looksThemesEnsureLoaded();
  }
  _looksSyncStickyH();
  _looksObserveSwatches();
  _looksRenderFab();
}
// Быстрые переходы остаются доступными и в «По коллекциям»: «Вход» и «Темы» —
// полноценные части внешнего вида, а не нижний хвост каталога. В слотах рядом с
// ними доступны все шесть слотов; в коллекциях остаются только две общие секции.
function _looksQuickLinksHtml(){
  const ids=_looksMode==='slots'?[..._LOOKS_SLOTS,'welcome','themes']:['welcome','themes'];
  return `<div class="looks-anchors" id="looks-quick-links" aria-label="Быстрые переходы по внешнему виду">${ids.map(id=>
    `<button class="looks-anchor-chip" type="button" data-looks-jump="${id}" onclick="_looksJump('${id}')">${_LOOKS_ANCHOR_LABEL[id]}</button>`
  ).join('')}</div>`;
}
// Режим «По слотам» — умный ряд (фильтр) живёт в .looks-sticky (рендерится в
// renderLooks), здесь только секции слотов. «Вход»/«Темы» общие, рендерятся
// отдельно в renderLooks().
function _looksSlotsViewHtml(){
  return `<div id="looks-sections">${_LOOKS_SLOTS.map(s=>_looksSectionHtml(s)).join('')}</div>`;
}
// Статистика коллекции: считается на клиенте из уже загруженных _looksData.slots
// (никакого нового запроса к бэку не нужно — lineup/owned уже есть на каждом предмете).
function _looksLineupStats(lin){
  let owned=0, total=0, trial=0; const slotOwned={};
  _LOOKS_SLOTS.forEach(slot=>{
    const items=(_looksData.slots[slot]||[]).filter(it=>it.lineup===lin);
    total+=items.length;
    const hasOwned=items.some(it=>it.owned);
    if(hasOwned) owned+=items.filter(it=>it.owned).length;
    if(items.some(it=>!it.owned && _looksTrial[slot]===it.id)) trial++;
    slotOwned[slot]=hasOwned;
  });
  return {owned,total,trial,slotOwned};
}
function _looksCollectionStatusHtml(stats){
  if(stats.total===0) return `<div class="coll-status" style="color:var(--muted);background:rgba(255,255,255,.05)">не начато</div>`;
  if(stats.owned===stats.total) return `<div class="coll-status" style="color:#56c46a;background:rgba(86,196,106,.13)">✓ собрано</div>`;
  if(stats.trial) return `<div class="coll-status" style="color:#c7b5ff;background:rgba(139,108,240,.15)">🔮 Примеряется: ${stats.trial}</div>`;
  if(stats.owned===0) return `<div class="coll-status" style="color:var(--muted);background:rgba(255,255,255,.05)">не начато</div>`;
  return `<div class="coll-status" style="color:var(--gold2);background:rgba(232,181,77,.13)">${stats.total-stats.owned} не куплено</div>`;
}
function _looksLineupVisibility(meta, compact=false){
  if(compact) return meta&&meta.vip_required ? '👑 С VIP' : '👁 Всем';
  return meta&&meta.vip_required ? '👑 На профиле — с VIP' : '👁 Видна всем';
}
function _looksItemPrice(item){
  return Number(item&&item.price&&item.price[0]&&item.price[0].zarniki)||0;
}
function _looksLineupItems(lin){
  if(!_looksData) return [];
  return _LOOKS_SLOTS.flatMap(slot=>_looksData.slots[slot]||[]).filter(item=>item.lineup===lin);
}
function _looksLineupPriceRange(lin){
  const prices=_looksLineupItems(lin).map(_looksItemPrice).filter(Boolean);
  if(prices.length) return {min:Math.min(...prices),max:Math.max(...prices)};
  const meta=_looksData&&_looksData.lineups&&_looksData.lineups[lin];
  const value=Number(meta&&meta.price&&meta.price[0]&&meta.price[0].zarniki)||0;
  return {min:value,max:value};
}
function _looksLineupPriceText(lin){
  const {min,max}=_looksLineupPriceRange(lin);
  if(!min) return '—';
  return min===max?`${min}✨`:`${min}–${max}✨`;
}
const _LOOKS_SLOT_ICON={name_glow:'✨',avatar_frame:'🖼',avatar_halo:'🌟',title:'🏷',profile_bg:'🖌',card_fx:'❄️'};
function _looksCollectionCard(lin){
  const meta=lineupMeta(lin); if(!meta) return '';
  const stats=_looksLineupStats(lin);
  const pct=stats.total?Math.round(stats.owned/stats.total*100):0;
  const c=LINEUP_COLOR[lin]||'#9aa7b8';
  const price=_looksLineupPriceText(lin);
  const slotsHtml=_LOOKS_SLOTS.map(slot=>`<span class="coll-slot${stats.slotOwned[slot]?' on':''}">${_LOOKS_SLOT_ICON[slot]}</span>`).join('');
  return `<div class="coll-card" style="--c:${c};--cb:${c}4d;--cg:${c}1f" data-lineup="${lin}" onclick="_looksOpenCollection('${lin}')">
    <div class="coll-inner"><div class="coll-frame"></div>
      <div class="coll-top">
        <div class="coll-sig" style="--c:${c}">
          <div class="coll-ring" style="background:conic-gradient(${c} calc(${pct}%),rgba(255,255,255,.08) 0)"><div class="coll-ring-mask"></div></div>
          ${_looksCollectionIconSvg(lin)}
        </div>
        <div><div class="coll-name">${esc(meta.name)}</div>${_looksCollectionStatusHtml(stats)}<div class="coll-price">${price}</div><div class="coll-visibility${meta.vip_required?' coll-visibility--vip':''}">${_looksLineupVisibility(meta,true)}</div></div>
      </div>
      <div class="coll-slots">${slotsHtml}</div>
    </div>
  </div>`;
}
function _looksCollectionsViewHtml(){
  if(_looksDetailLineup) return _looksCollectionDetailHeaderHtml(_looksDetailLineup)+_looksCollectionDetailBodyHtml();
  const lineups=Object.keys(_looksData.lineups||{});
  return `<div class="coll-grid">${lineups.map(_looksCollectionCard).join('')}</div>`;
}
function _looksCuratedById(lookId){
  return ((_looksData&&_looksData.curated_looks)||[]).find(look=>look.id===lookId)||null;
}
function _looksCuratedCardHtml(look){
  const ids=look.items||{};
  const glow=_looksCos(ids.name_glow), frame=_looksCos(ids.avatar_frame), halo=_looksCos(ids.avatar_halo);
  const title=_looksCos(ids.title), bg=_looksCos(ids.profile_bg), fx=_looksCos(ids.card_fx);
  if(!glow||!frame||!halo||!title||!bg||!fx) return '';
  const color=lineupColor(look.lineup);
  const state=look.fully_owned?'✓ Всё принадлежит':`${look.owned_count||0}/${look.total_count||6} · докупить ${look.missing_price||0}✨`;
  return `<button class="looks-curated-card" type="button" data-curated-look="${esc(look.id)}" style="--curated:${color};--curated-wash:${color}24" onclick="_looksTryCurated('${look.id}')">
    <span class="looks-curated-preview looks-preview ${bg.css}">
      <span class="card-fx ${fx.css}"></span>
      <span class="looks-curated-identity">
        <span class="ava ${frame.css} ${halo.css}">${_looksData.vip?'👑':'🔮'}</span>
        <span class="looks-curated-profile-copy"><strong class="pname ${glow.css}">@Твой ник</strong><small class="ptitle ${title.css||''}">${esc(title.text||title.name)}</small></span>
      </span>
    </span>
    <span class="looks-curated-copy"><strong>${esc(look.name)}</strong><small>${esc(look.mood)}</small><span>${state}</span></span>
    <span class="looks-curated-action">Примерить образ <b aria-hidden="true">›</b></span>
  </button>`;
}
function _looksCuratedLooksHtml(lineup){
  const looks=((_looksData&&_looksData.curated_looks)||[]).filter(look=>look.lineup===lineup);
  if(!looks.length) return '';
  return `<section class="looks-curated" aria-label="Кураторские образы коллекции">
    <div class="looks-curated-head"><strong>Собранные образы</strong><span>${looks.length} сочетания</span></div>
    <div class="looks-curated-row">${looks.map(_looksCuratedCardHtml).join('')}</div>
  </section>`;
}
function _looksTryCurated(lookId){
  const look=_looksCuratedById(lookId); if(!look) return;
  _looksSel={..._looksSaved};
  _looksLastTouchedCosmetic='';
  _LOOKS_SLOTS.forEach(slot=>{
    const id=look.items&&look.items[slot], item=_looksCos(id);
    if(!item) return;
    if(item.owned){ _looksSel[slot]=id; _looksDropTrial(slot); }
    else _looksSetTrial(slot,id);
  });
  _looksRenderFab();
  _LOOKS_SLOTS.forEach(_looksMarkSel);
  _looksOpenFittingSheet();
}
// Детальный экран: переиспользует секции слотов из режима «По слотам», но не
// рисует пустые категории. В полном каталоге у каждой линейки есть все шесть
// слотов; эта защита нужна для частичной выдачи, чтобы вместо карточки товара
// игрок не видел ложное «Ничего не найдено». Якорь-чипы не нужны: набор
// секций одной линейки остаётся коротким.
function _looksCollectionDetailBodyHtml(){
  const slots=_LOOKS_SLOTS.filter(s=>
    (_looksData.slots[s]||[]).some(it=>it.lineup===_looksDetailLineup));
  return `${_looksCuratedLooksHtml(_looksDetailLineup)}<div id="looks-sections">${slots.map(s=>_looksSectionHtml(s,_looksDetailLineup)).join('')}</div>`;
}
// Медальон-иконка каждой линейки — авторский анимированный SVG-сигиль (не эмодзи,
// см. COSMETICS_COLLECTION_DESIGN_RULES.md §1). Код транскрибирован из брейншторма
// (.superpowers/brainstorm/1020-1785343726/content/icon-set-v3.html) без изменений.
function _looksCollectionIconSvg(lin){
  switch(lin){
    case 'forest': return `<svg class="coll-sig-svg" viewBox="0 0 24 24" style="animation:canopyBreathe 3.6s ease-in-out infinite;transform-origin:12px 20px">
        <defs><linearGradient id="pineGrad-${lin}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#a8e0a8"/><stop offset="100%" stop-color="#3f7d3f"/></linearGradient></defs>
        <polygon points="12,2 4,10 20,10" fill="url(#pineGrad-${lin})" stroke="#3f7d3f" stroke-width=".6"/>
        <polygon points="12,6 3,15 21,15" fill="url(#pineGrad-${lin})" stroke="#3f7d3f" stroke-width=".6" opacity=".95"/>
        <polygon points="12,10 2,20 22,20" fill="url(#pineGrad-${lin})" stroke="#3f7d3f" stroke-width=".6" opacity=".9"/>
        <rect x="10.5" y="20" width="3" height="2.5" fill="#5c4326"/>
        <circle cx="6" cy="9" r="1" fill="#e8ffb0" style="animation:fireflyDrift 3.4s ease-in-out infinite"/>
        <circle cx="18" cy="13" r="1" fill="#e8ffb0" style="animation:fireflyDrift 4.1s ease-in-out infinite 1.1s"/>
        <circle cx="9" cy="17" r=".7" fill="#e8ffb0" style="animation:fireflyDrift 3.8s ease-in-out infinite 2s"/>
      </svg>`;
    case 'threshold': return `<svg class="coll-sig-svg" viewBox="0 0 24 24" fill="none">
        <defs>
          <clipPath id="gateClip-${lin}"><path d="M6.5 22V10a5.5 5.5 0 0 1 11 0v12z"/></clipPath>
          <linearGradient id="gateGlow-${lin}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#c084fc" stop-opacity="0"/><stop offset="50%" stop-color="#e6c9ff" stop-opacity=".9"/><stop offset="100%" stop-color="#c084fc" stop-opacity="0"/></linearGradient>
        </defs>
        <path d="M5 22V10a7 7 0 0 1 14 0v12" stroke="currentColor" stroke-width="1.3" style="color:#c084fc"/>
        <path d="M6.5 22V10a5.5 5.5 0 0 1 11 0v12" stroke="currentColor" stroke-width=".6" opacity=".5" style="color:#c084fc"/>
        <g clip-path="url(#gateClip-${lin})">
          <rect x="4" y="0" width="16" height="6" fill="url(#gateGlow-${lin})" style="animation:portalTravel 3.2s ease-in-out infinite"/>
          <g style="animation:portalSwirl 6s linear infinite;transform-origin:12px 15px">
            <circle cx="12" cy="11" r=".6" fill="#e6c9ff"/><circle cx="12" cy="19" r=".5" fill="#e6c9ff"/>
          </g>
        </g>
      </svg>`;
    case 'frost': return `<svg class="coll-sig-svg" viewBox="0 0 24 24" fill="none" stroke="#7ad4ff" stroke-width="1.1" style="transform-origin:center;animation:frostSway 4.5s ease-in-out infinite">
        <line x1="12" y1="2" x2="12" y2="22"/><line x1="12" y1="2" x2="12" y2="22" transform="rotate(60 12 12)"/><line x1="12" y1="2" x2="12" y2="22" transform="rotate(120 12 12)"/>
        <path d="M12 6 9 8M12 6 15 8M12 18 9 16M12 18 15 16M12 4 10.5 5M12 4 13.5 5" style="animation:frostTwinkle 2s ease-in-out infinite"/>
        <circle cx="12" cy="12" r="1.4" fill="#7ad4ff" stroke="none" style="animation:frostTwinkle 2s ease-in-out infinite .3s"/>
      </svg>
      <svg class="coll-sig-svg" viewBox="0 0 24 24" style="position:absolute;inset:0;margin:auto">
        <text class="ico-snowflake" x="4" y="2" font-size="3" fill="#cdeeff" style="--sx:3px;animation:snowFall 3s linear infinite">❋</text>
        <text class="ico-snowflake" x="17" y="0" font-size="2.4" fill="#cdeeff" style="--sx:-2px;animation:snowFall 3.6s linear infinite 1.2s">❋</text>
        <text class="ico-snowflake" x="10" y="-2" font-size="2" fill="#cdeeff" style="--sx:2px;animation:snowFall 2.6s linear infinite 2s">❋</text>
      </svg>`;
    case 'inferno': return `<div class="ico-heatglow" style="position:absolute;width:40px;height:40px;border-radius:50%;background:radial-gradient(circle,#ff7a3d,transparent 70%);animation:heatGlow 2.4s ease-in-out infinite"></div>
      <svg class="coll-sig-svg" viewBox="0 0 24 24">
        <defs><linearGradient id="flameGrad-${lin}" x1="0" y1="1" x2="0" y2="0"><stop offset="0%" stop-color="#ff7a3d"/><stop offset="60%" stop-color="#ffb15e"/><stop offset="100%" stop-color="#fff1c2"/></linearGradient></defs>
        <path d="M12 2C9 6 6 9 6 13a6 6 0 0 0 12 0c0-2-1-3.5-2-5 .3 2-.5 3-1.5 3.5.5-3-1-6-2.5-9.5z" fill="url(#flameGrad-${lin})" style="transform-origin:12px 22px;animation:collFlameFlicker 1.6s ease-in-out infinite"/>
        <circle cx="9" cy="18" r="1" fill="#ffb15e" style="--ex:-4px;animation:emberRise 2.2s ease-in infinite"/>
        <circle cx="15" cy="19" r="1" fill="#ffb15e" style="--ex:5px;animation:emberRise 2.6s ease-in infinite .8s"/>
        <circle cx="12" cy="20" r=".8" fill="#ffb15e" style="--ex:1px;animation:emberRise 2s ease-in infinite 1.5s"/>
      </svg>`;
    case 'celestial': return `<svg class="coll-sig-svg" viewBox="0 0 24 24" style="position:absolute;transform-origin:center">
        <g class="ico-rays" stroke="#e8c45a" stroke-width=".6">
          <line x1="12" y1="0" x2="12" y2="4" style="animation:rayPulse 2s ease-in-out infinite"/>
          <line x1="12" y1="20" x2="12" y2="24" style="animation:rayPulse 2s ease-in-out infinite .5s"/>
          <line x1="0" y1="12" x2="4" y2="12" style="animation:rayPulse 2s ease-in-out infinite 1s"/>
          <line x1="20" y1="12" x2="24" y2="12" style="animation:rayPulse 2s ease-in-out infinite 1.5s"/>
        </g>
      </svg>
      <svg class="coll-sig-svg" viewBox="0 0 24 24" style="transform-origin:center;animation:starSpin 9s linear infinite">
        <defs><radialGradient id="starGrad-${lin}"><stop offset="0%" stop-color="#fff6d8"/><stop offset="100%" stop-color="#e8c45a"/></radialGradient></defs>
        <path d="M12 2 L14 10 L22 12 L14 14 L12 22 L10 14 L2 12 L10 10 Z" fill="url(#starGrad-${lin})"/>
        <circle cx="12" cy="12" r="2.2" fill="#fff6d8" style="animation:starPulse 2.4s ease-in-out infinite"/>
      </svg>`;
    case 'void': return `<svg class="coll-sig-svg" viewBox="0 0 24 24" fill="none" style="position:absolute;animation:voidSwirl 12s linear infinite;transform-origin:12px 12px">
        <circle class="ico-voidspark" cx="12" cy="2.3" r=".6" fill="#ffd0e2" style="animation:voidSpark 2.4s ease-in-out infinite"/>
        <circle class="ico-voidspark" cx="21.7" cy="12" r=".5" fill="#ffd0e2" style="animation:voidSpark 3s ease-in-out infinite .8s"/>
        <circle class="ico-voidspark" cx="12" cy="21.7" r=".5" fill="#ffd0e2" style="animation:voidSpark 2.7s ease-in-out infinite 1.6s"/>
      </svg>
      <svg class="coll-sig-svg" viewBox="0 0 24 24" fill="none">
        <defs><radialGradient id="voidGrad-${lin}" cx="50%" cy="50%" r="50%"><stop offset="55%" stop-color="#0e1019"/><stop offset="100%" stop-color="#ff4d8d" stop-opacity=".6"/></radialGradient></defs>
        <circle cx="12" cy="12" r="8.4" fill="url(#voidGrad-${lin})" stroke="#ff4d8d" stroke-width="1"/>
        <circle cx="12" cy="12" r="8.4" fill="#0e1019" style="animation:voidOrbit 6s ease-in-out infinite"/>
      </svg>`;
    case 'artifact': return `<svg class="coll-sig-svg" viewBox="0 0 24 24" style="overflow:visible">
        <defs>
          <clipPath id="gemclip-${lin}"><path d="M12 2 L20 9 L16 21 L8 21 L4 9 Z"/></clipPath>
          <linearGradient id="gemGrad-${lin}" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#c8fbfb"/><stop offset="100%" stop-color="#1f9d9d"/></linearGradient>
        </defs>
        <path d="M12 2 L20 9 L16 21 L8 21 L4 9 Z" fill="url(#gemGrad-${lin})" opacity=".85" stroke="#3fe0e0" stroke-width=".8"/>
        <path d="M4 9 L20 9M8 21 L12 9 L16 21M12 2 L12 9" stroke="#0b3d3d" stroke-width=".6" opacity=".6" fill="none"/>
        <g clip-path="url(#gemclip-${lin})">
          <rect x="-4" y="-4" width="10" height="32" fill="#fff" opacity=".5" style="animation:gemShimmer 3.6s ease-in-out infinite alternate"/>
        </g>
        <circle cx="9" cy="12" r=".7" fill="#fff" style="animation:gemSparkle 2.6s ease-in-out infinite"/>
        <circle cx="15" cy="15" r=".6" fill="#fff" style="animation:gemSparkle 3.1s ease-in-out infinite 1.3s"/>
      </svg>`;
    case 'hanami': return `<svg class="coll-sig-svg" viewBox="0 0 24 24" fill="none" style="overflow:visible">
        <defs><linearGradient id="hanamiBranch-${lin}" x1="2" y1="22" x2="20" y2="3"><stop stop-color="#6b3f45"/><stop offset="1" stop-color="#d8a07f"/></linearGradient></defs>
        <path d="M3 21C7.5 16.8 8.2 11.2 14 7.5c2.2-1.4 4.2-2.5 7-3.4M9 14.4c-1.2-2.2-2.8-3.4-5-4.1M13.2 8.1c-.1-2.3.8-4.1 2.8-5.6" stroke="url(#hanamiBranch-${lin})" stroke-width="1.25" stroke-linecap="round"/>
        <g fill="#f3b6c6" stroke="#fff0f4" stroke-width=".25" style="transform-origin:16px 7px;animation:hanamiBloom 4.8s ease-in-out infinite">
          <path d="M17 4.3c.8-1.6 2.5-1.3 2.4.3 1.6-.3 2.2 1.3.8 2.1 1.1 1.1.1 2.5-1.3 1.7-.5 1.5-2.2 1.4-2.4-.2-1.5.5-2.2-1.1-.9-2.1-1.2-1.1-.1-2.5 1.4-1.8z"/>
          <circle cx="17.8" cy="6.4" r=".65" fill="#d889a2" stroke="none"/>
        </g>
        <g fill="#ed9fb7" opacity=".92" style="transform-origin:7px 12px;animation:hanamiBloom 5.4s ease-in-out infinite 1.1s">
          <circle cx="7" cy="11.3" r="1.5"/><circle cx="8.5" cy="12" r="1.4"/><circle cx="7.7" cy="13.5" r="1.35"/><circle cx="6" cy="13.1" r="1.35"/><circle cx="5.7" cy="11.6" r="1.3"/><circle cx="7.1" cy="12.4" r=".55" fill="#ffe6ad"/>
        </g>
        <path d="M20.5 10c1.1.8.9 2.2-.3 2.8-1.1-.8-1-2.1.3-2.8z" fill="#f3b6c6" style="animation:hanamiPetalFall 4.6s ease-in-out infinite"/>
      </svg>`;
    case 'moon_lotus': return `<svg class="coll-sig-svg" viewBox="0 0 24 24" fill="none" style="overflow:visible">
        <defs>
          <radialGradient id="lotusMoon-${lin}"><stop stop-color="#fffef2"/><stop offset=".72" stop-color="#dce4ff"/><stop offset="1" stop-color="#8da4e5"/></radialGradient>
          <linearGradient id="lotusPearl-${lin}" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fff"/><stop offset=".45" stop-color="#efc9e4"/><stop offset="1" stop-color="#9eb8ff"/></linearGradient>
        </defs>
        <circle cx="12" cy="7" r="4.6" fill="url(#lotusMoon-${lin})" opacity=".9" style="animation:moonLotusGlow 4.8s ease-in-out infinite"/>
        <g fill="url(#lotusPearl-${lin})" stroke="#f8f2ff" stroke-width=".3" style="transform-origin:12px 18px;animation:moonLotusFloat 5.6s ease-in-out infinite">
          <path d="M12 19.5C8.8 16.7 8.8 13.5 12 11c3.2 2.5 3.2 5.7 0 8.5z"/>
          <path d="M11.3 20c-4.2-.6-6.2-3.2-5.5-6.9 3.7.5 5.7 2.8 5.5 6.9z" opacity=".9"/>
          <path d="M12.7 20c4.2-.6 6.2-3.2 5.5-6.9-3.7.5-5.7 2.8-5.5 6.9z" opacity=".9"/>
          <path d="M10.4 20.1c-3.6 1-6.4-.2-7.8-3.4 3.2-.9 5.8.1 7.8 3.4z" opacity=".72"/>
          <path d="M13.6 20.1c3.6 1 6.4-.2 7.8-3.4-3.2-.9-5.8.1-7.8 3.4z" opacity=".72"/>
        </g>
        <path d="M4 22c4-1 12-1 16 0" stroke="#9eb8ff" stroke-width=".65" stroke-linecap="round" opacity=".75" style="animation:moonRipple 5s ease-in-out infinite"/>
      </svg>`;
    case 'ryujin_tide': return `<svg class="coll-sig-svg" viewBox="0 0 24 24" fill="none" style="overflow:visible">
        <defs><linearGradient id="ryujinWave-${lin}" x1="2" y1="20" x2="22" y2="5"><stop stop-color="#23516c"/><stop offset=".55" stop-color="#7bd4e8"/><stop offset="1" stop-color="#e6c879"/></linearGradient></defs>
        <g stroke="url(#ryujinWave-${lin})" stroke-linecap="round" stroke-linejoin="round" style="transform-origin:12px 12px;animation:ryujinSigFlow 6.5s ease-in-out infinite">
          <path d="M2.5 17.8c3.5-5.7 7.2-7.7 11.1-5.8 2.3 1.1 3.4-.5 2.2-2.4-1.1-1.8.3-3.9 2.4-3.1 1.6.6 2.8 2.2 3.3 4" stroke-width="1.45"/>
          <path d="M3.2 20.2c4.9-3.7 9.2-4 12.8-.8 1.6 1.4 3.5 1.3 5.5-.1" stroke-width="1" opacity=".8"/>
          <path d="M15.9 7.7 13.6 5l3.5.7M19 6.8l1-3 1.1 3.2" stroke-width=".75"/>
          <circle cx="18.6" cy="8.3" r=".55" fill="#f7df9a" stroke="none"/>
        </g>
        <path d="m5 15.7 2.2-2.5-1.1 3.1 2.7-.8" stroke="#f2d17b" stroke-width=".55" style="animation:ryujinGoldFlash 4.2s ease-in-out infinite"/>
      </svg>`;
    default: return `<svg class="coll-sig-svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.2"/></svg>`;
  }
}
// Высота .looks-sticky «плавает» (lineup-info то есть, то нет, разной длины) —
// scroll-margin-top секций держим в CSS-переменной, иначе якорь-прыжок иногда
// подсовывал заголовок секции ПОД прилипшую шапку (замерено puppeteer при фиксе
// бага "фильтр-чипы уезжают под sticky-превью", 2026-07-29).
function _looksSyncStickyH(){
  const s=document.querySelector('.looks-sticky'); if(!s) return;
  const top=parseFloat(getComputedStyle(s).top)||0;   // «прилипает» с отступом top — его тоже надо перекрыть
  document.documentElement.style.setProperty('--looks-sticky-h', (top+s.offsetHeight+14)+'px');
}
// Якорь-чип: скроллит к секции (не переключает панель — все секции уже на странице).
function _looksJump(id){
  const sec=el('looks-sec-'+id); if(!sec) return;
  const reduce=document.body.classList.contains('no-fx')||(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches);
  sec.scrollIntoView({behavior: reduce?'auto':'smooth', block:'start'});
}
let _looksSearch='';   // поиск по названию — общий для всех секций разом, как и остальные фильтры
function _looksFilterHtml(){
  const lin=lineupMeta(_looksFilter);
  const lineupTxt=_looksFilter==='all'?'Все линейки':esc(lin?lin.name:'—');
  const dotHtml=_looksFilter==='all'
    ?`<span class="sr-dot-all"><span style="background:#ff7a3d"></span><span style="background:#7ad4ff"></span><span style="background:#c084fc"></span></span>`
    :`<span class="sr-dot" style="color:${lineupColor(_looksFilter)}"></span>`;
  const statusIcon=_LOOKS_STATUS_ICON[_looksStatus];
  const statusLabel=_LOOKS_STATUS_LABEL[_looksStatus];
  const lineupTxtAttr=lineupTxt.replace(/"/g,'&quot;');   // esc() не экранирует кавычки — своя защита для атрибута title
  return `<div class="smartrow">
    <div class="sr-tap sr-tap--flex"><div class="sr-box sr-search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
      <input type="text" id="looks-search-inp" placeholder="Поиск…" value="${esc(_looksSearch).replace(/"/g,'&quot;')}" oninput="_looksSetSearch(this.value)">
    </div></div>
    <div class="sr-tap"><button class="sr-box sr-lineup" id="looks-lineup-pill" type="button" onclick="_looksOpenLineupPicker()" title="Линейка: ${lineupTxtAttr}">${dotHtml}${lineupTxt}</button></div>
    <div class="sr-tap"><button class="sr-box sr-status sr-status--${_looksStatus}" id="looks-status-btn" onclick="_looksCycleStatus()" type="button" title="${statusLabel}" aria-label="Статус владения: ${statusLabel}">${statusIcon}</button></div>
  </div><div id="looks-lineup-info">${_looksLineupInfoHtml()}</div>`;
}
function _looksSetSearch(v){
  _looksSearch=v;
  _LOOKS_SLOTS.forEach(_looksRenderSectionGrid);
  _looksSyncStickyH();
}
function _looksOpenLineupPicker(){
  const lineups=Object.keys(_looksData.lineups||{});
  const rows=[{id:'all',label:'Все линейки'}, ...lineups.map(id=>({id,label:lineupLabel(id)}))]
    .map(o=>`<div class="picker-opt${o.id===_looksFilter?' on':''}" onclick="_looksPickLineup('${o.id}')">${esc(o.label)}</div>`).join('');
  OM('Линейка', `<div class="picker">${rows}</div>`, [{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}
function _looksPickLineup(lin){
  CM();
  _looksFilter=lin;
  // Полная перерисовка умного ряда (пилюля/точка меняются) — дешёвая операция, не вся страница
  const host=el('looks-filter-bar');
  if(host) host.outerHTML=`<div id="looks-filter-bar">${_looksFilterHtml()}</div>`;
  _LOOKS_SLOTS.forEach(_looksRenderSectionGrid);
  _looksSyncStickyH();
}
// Тап по карточке коллекции: открывает детальный экран (Стадия 3) — алтарная
// шапка (медальон крупнее/блёрб/сегментный измеритель/атмосфера линейки) +
// кнопка «Купить всё недостающее» + все 6 секций слотов (переиспользованы БЕЗ
// изменений из Стадии 1 — они уже фильтруются по _looksFilter=lin).
function _looksOpenCollection(lin){
  _looksSearch=''; _looksStatus='all'; _looksFilter=lin; _looksDetailLineup=lin;
  renderLooks();
  // Финальный ревью: если тап пришёлся на карточку в скролле (не только у 3 из
  // карточек линеек внизу сетки), шапка детального экрана рендерится за текущим
  // scrollTop и остаётся за прилипшим превью — игрок не видит медальон/блёрб/
  // измеритель вообще, только хвост кнопки покупки.
  window.scrollTo(0,0);
}
function _looksCloseCollection(){
  _looksDetailLineup=null; _looksFilter='all';
  renderLooks();
  window.scrollTo(0,0);
}
// Алтарная шапка открытой коллекции (Стадия 3) — см. COSMETICS_COLLECTION_DESIGN_RULES.md §6:
// медальон крупнее (74px+), сегментный измеритель (N делений = N предметов
// линейки, не гладкий %), явная кнопка «Купить всё недостающее» — реальная
// транзакция, НЕ побочный эффект тапа по карточке/плитке.
function _looksCollectionDetailHeaderHtml(lin){
  const meta=lineupMeta(lin); if(!meta) return '';
  const stats=_looksLineupStats(lin);
  const c=LINEUP_COLOR[lin]||'#9aa7b8';
  const missingItems=_looksLineupItems(lin).filter(item=>!item.owned);
  const missing=missingItems.length;
  const total=missingItems.reduce((sum,item)=>sum+_looksItemPrice(item),0);
  const priceRange=_looksLineupPriceText(lin);
  const visibility=_looksLineupVisibility(meta);
  const bal=(_looksData.balances||{}).zarniki||0;
  const can=missing>0&&bal>=total;
  const notches=Array.from({length:stats.total},(_,i)=>`<div class="coll-meter-notch${i<stats.owned?' on':''}"></div>`).join('');
  const action = missing===0
    ? `<div class="coll-detail-done">✓ Коллекция собрана полностью</div>`
    : `<button class="btn btn-sm ${can?'btn-gold':'btn-ghost'} btn-full" ${can?'':'disabled'} onclick="_looksBuyLineup('${lin}',this)">${can?`✨ Купить всё недостающее — ${total}✨ (${missing} шт.)`:`🚫 Нужно ${total}✨ (есть ${Math.floor(bal)}✨)`}</button>`;
  return `<div class="coll-detail-head" style="--c:${c};--cb:${c}4d;--cg:${c}1f">
    <button class="coll-detail-back" onclick="_looksCloseCollection()" aria-label="Назад к коллекциям">‹</button>
    <div class="coll-detail-atmo">${_looksCollectionAtmosphereHtml(lin)}</div>
    <div class="coll-detail-sig" style="--c:${c}">${_looksCollectionIconSvg(lin)}</div>
    <div class="coll-detail-name">${esc(meta.name)}</div>
    <div class="coll-detail-blurb">${esc(meta.blurb||'')}</div>
    <div class="coll-detail-rule"><span class="coll-visibility${meta.vip_required?' coll-visibility--vip':''}">${visibility}</span><span>🛍 Купить может каждый</span></div>
    <div class="coll-meter">${notches}</div>
    <div class="coll-meter-caption"><span>${stats.owned} из ${stats.total} собрано</span><span>${missing>0?`${missing} не куплено · ${priceRange}`:''}</span></div>
    ${action}
  </div>`;
}
// Финальный ревью Стадии 3: без блокировки кнопки двойной тап отправлял 2
// одинаковых POST — бэкенд теперь тоже защищён (владение читается после
// блокировки баланса), но кнопку всё равно блокируем на время запроса —
// не полагаться на бэк как на единственную линию защиты. Также обновляет
// После массовой покупки обновляем каталог и только FAB: примерочная больше не
// живёт в основном потоке страницы.
function _looksBuyLineup(lin,btn){
  if(btn) btn.disabled=true;
  const requestKey=btn?.dataset.requestKey||economyRequestKey(`cosmetic-lineup-${lin}`);
  if(btn)btn.dataset.requestKey=requestKey;
  api('/cosmetics/buy-lineup',{method:'POST',headers:{'Idempotency-Key':requestKey},body:JSON.stringify({lineup:lin})})
    .then(r=>{if(btn)delete btn.dataset.requestKey; toast(r.message); refreshCurrBar(); return api('/cosmetics/');})
    .then(d=>{_looksData=d; _looksSaved=_looksEquipped(d); _looksSel={..._looksSaved};
      _looksDirty=true;
      _looksSanitizeTrial();
      const body=el('looks-mode-body'); if(body) body.innerHTML=_looksCollectionsViewHtml();
      _looksRenderFab(); _looksSyncStickyH();})
    .catch(e=>{toast(e,false); if(btn) btn.disabled=false;});
}
// Фоновая атмосфера шапки детального экрана (Стадия 3) — 2-3 крупные МЕДЛЕННЫЕ
// малозаметные частицы в духе линейки, см. COSMETICS_COLLECTION_DESIGN_RULES.md
// §6: «тот же тип, что у иконки (_looksCollectionIconSvg), но крупнее и
// медленнее — это фон всего экрана, не деталь 56px иконки». Переиспользует
// СУЩЕСТВУЮЩИЕ keyframes иконок (app.css) с более долгой длительностью —
// не изобретает новые анимации.
function _looksCollectionAtmosphereHtml(lin){
  switch(lin){
    case 'forest': return `
      <div style="position:absolute;width:5px;height:5px;border-radius:50%;background:#e8ffb0;left:20%;top:65%;animation:fireflyDrift 7s ease-in-out infinite"></div>
      <div style="position:absolute;width:4px;height:4px;border-radius:50%;background:#e8ffb0;left:75%;top:30%;animation:fireflyDrift 8.5s ease-in-out infinite 2s"></div>`;
    case 'threshold': return `
      <div style="position:absolute;left:30%;top:0;width:40%;height:60%;background:linear-gradient(180deg, rgba(224,201,255,.35), transparent);animation:portalTravel 6.5s ease-in-out infinite"></div>`;
    case 'frost': return `
      <div style="position:absolute;font-size:20px;color:#cdeeff;left:15%;top:8%;animation:snowFall 7s linear infinite">❋</div>
      <div style="position:absolute;font-size:14px;color:#cdeeff;left:70%;top:14%;animation:snowFall 9s linear infinite 2.5s">❋</div>`;
    case 'inferno': return `
      <div style="position:absolute;width:90px;height:90px;border-radius:50%;left:50%;top:60%;transform:translate(-50%,0);background:radial-gradient(circle,#ff7a3d,transparent 70%);animation:heatGlow 4.5s ease-in-out infinite"></div>
      <div style="position:absolute;width:4px;height:4px;border-radius:50%;background:#ffb15e;left:35%;top:70%;animation:emberRise 4s ease-in infinite"></div>
      <div style="position:absolute;width:3px;height:3px;border-radius:50%;background:#ffb15e;left:60%;top:75%;animation:emberRise 4.6s ease-in infinite 1.5s"></div>`;
    case 'celestial': return `
      <div style="position:absolute;width:100%;height:100%;background:conic-gradient(from 0deg, transparent, rgba(232,196,90,.12), transparent 30%);animation:starSpin 20s linear infinite"></div>`;
    case 'void': return `
      <div style="position:absolute;width:3px;height:3px;border-radius:50%;background:#ffd0e2;left:25%;top:40%;animation:voidSpark 4.4s ease-in-out infinite"></div>
      <div style="position:absolute;width:2px;height:2px;border-radius:50%;background:#ffd0e2;left:70%;top:55%;animation:voidSpark 5.2s ease-in-out infinite 1.6s"></div>`;
    case 'artifact': return `
      <div style="position:absolute;width:80%;height:90%;left:10%;top:5%;background:linear-gradient(100deg, transparent, rgba(255,255,255,.10), transparent);animation:gemShimmer 6s ease-in-out infinite alternate"></div>`;
    case 'hanami': return `
      <div style="position:absolute;width:8px;height:5px;border-radius:90% 15% 90% 15%;background:#e8a3b6;left:18%;top:12%;animation:hanamiAtmoFall 8s ease-in-out infinite;opacity:.55"></div>
      <div style="position:absolute;width:6px;height:4px;border-radius:90% 15% 90% 15%;background:#f2c2cf;left:76%;top:4%;animation:hanamiAtmoFall 10s ease-in-out infinite 2.4s;opacity:.48"></div>`;
    case 'moon_lotus': return `
      <div style="position:absolute;width:120px;height:120px;border-radius:50%;left:50%;top:-68px;transform:translateX(-50%);background:radial-gradient(circle,rgba(245,247,255,.18),rgba(185,201,255,.04) 54%,transparent 70%);animation:moonLotusGlow 7s ease-in-out infinite"></div>
      <div style="position:absolute;width:64%;height:18px;left:18%;top:64%;border:1px solid rgba(185,201,255,.18);border-left-color:transparent;border-right-color:transparent;border-radius:50%;animation:moonRipple 8s ease-in-out infinite"></div>
      <div style="position:absolute;width:9px;height:5px;border-radius:90% 18% 90% 18%;background:#e9d6eb;left:22%;top:5%;opacity:.56;animation:lotusPetalAtmo 9s ease-in-out infinite"></div>
      <div style="position:absolute;width:7px;height:4px;border-radius:90% 18% 90% 18%;background:#cbd8ff;left:72%;top:16%;opacity:.46;animation:lotusPetalAtmo 11s ease-in-out infinite 2.8s"></div>`;
    case 'ryujin_tide': return `
      <div style="position:absolute;width:130%;height:85%;left:-15%;top:38%;border-radius:50%;border-top:2px solid rgba(105,184,214,.14);transform:rotate(-7deg);animation:ryujinAtmoCurrent 9s ease-in-out infinite"></div>
      <div style="position:absolute;width:2px;height:46%;left:69%;top:6%;background:linear-gradient(transparent,rgba(230,200,121,.38),transparent);transform:rotate(34deg);animation:ryujinGoldFlash 6.5s ease-in-out infinite"></div>
      <div style="position:absolute;width:5px;height:3px;left:24%;top:72%;background:#e4c36e;clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%);opacity:.45;animation:ryujinScaleDrift 8s ease-in-out infinite"></div>
      <div style="position:absolute;width:4px;height:2px;left:79%;top:67%;background:#8ccfdf;clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%);opacity:.4;animation:ryujinScaleDrift 10s ease-in-out infinite 2.2s"></div>`;
    default: return '';
  }
}
const _LOOKS_STATUS_CYCLE=['all','owned','missing'];
const _LOOKS_STATUS_ICON={all:'∅',owned:'✓',missing:'🔒'};
const _LOOKS_STATUS_LABEL={all:'Все',owned:'Куплено',missing:'Не куплено'};
function _looksCycleStatus(){
  const i=_LOOKS_STATUS_CYCLE.indexOf(_looksStatus);
  _looksStatus=_LOOKS_STATUS_CYCLE[(i+1)%_LOOKS_STATUS_CYCLE.length];
  const btn=el('looks-status-btn');
  if(btn){
    btn.textContent=_LOOKS_STATUS_ICON[_looksStatus];
    btn.className=`sr-box sr-status sr-status--${_looksStatus}`;
    btn.title=_LOOKS_STATUS_LABEL[_looksStatus];
    btn.setAttribute('aria-label', `Статус владения: ${_LOOKS_STATUS_LABEL[_looksStatus]}`);
  }
  _LOOKS_SLOTS.forEach(_looksRenderSectionGrid);
  _looksSyncStickyH();
}
// Карточка-плашка с полной коммерческой инфой линейки (цена/VIP/описание) —
// владелец явно просил "чтобы точно видел то, что будет на продакшене", не
// прятать это в описаниях отдельных предметов. Пусто при фильтре "Все".
function _looksLineupInfoHtml(){
  if(_looksFilter==='all') return '';
  const l=lineupMeta(_looksFilter); if(!l) return '';
  const price=`${_looksLineupPriceText(_looksFilter)} за предмет`;
  const visibility=_looksLineupVisibility(l);
  return `<div class="looks-lineup-info">
    <div class="looks-lineup-blurb">${esc(l.blurb||'')}</div>
    <div class="looks-lineup-meta"><span>💰 ${price}</span><span>${visibility}</span><span>🛍 Купить может каждый</span></div>
  </div>`;
}
// Секция одного слота: заголовок-якорь + фильтруемая сетка (id стабилен для _looksJump).
function _looksSectionHtml(slot, lineupFilter){
  const all=_looksData.slots[slot]||[];
  const items=lineupFilter?all.filter(it=>it.lineup===lineupFilter):all;
  const owned=items.filter(it=>it.owned).length, total=items.length;
  // Порядок делений НЕ важен — деления обезличены (просто N одинаковых чёрточек,
  // не привязаны к конкретному предмету), горят ПЕРВЫЕ owned штук слева направо.
  // Это осознанно проще per-item подсветки (которая бы выглядела рандомно
  // раскиданной, т.к. массив не гарантированно owned-first).
  const notches=items.map((_,i)=>`<div class="mini-notch${i<owned?' on':''}"></div>`).join('');
  return `<section class="looks-section" id="looks-sec-${slot}">
    <div class="sec-head">
      <div class="looks-sec-t">${_LOOKS_SLOT_LABEL[slot]}</div>
      <div class="mini-meter">${notches}</div>
      <div class="sec-num">${owned}/${total}</div>
    </div>
    <div class="looks-sec-grid" id="looks-grid-${slot}">${_looksGridHtml(slot)}</div>
  </section>`;
}
// Живой свотч только у карточек, реально видимых на экране прямо сейчас. Когда
// карточка уходит за экран, класс снимается и её эффект снова становится статичным.
let _lcSwObserver=null;
function _looksObserveSwatches(container){
  if(!('IntersectionObserver' in window)) return;
  if(!_lcSwObserver){
    _lcSwObserver=new IntersectionObserver(entries=>{
      entries.forEach(entry=>entry.target.classList.toggle('lc-sw-live', entry.isIntersecting));
    }, {root:null, rootMargin:'50px', threshold:0.1});
  }
  (container||document).querySelectorAll('.looks-card[data-cos]').forEach(card=>_lcSwObserver.observe(card));
}
function _looksRenderSectionGrid(slot){
  const g=el('looks-grid-'+slot); if(g){ g.innerHTML=_looksGridHtml(slot); _looksObserveSwatches(g); }
}
// В примерочной показываем тот же полный профиль, что и на главной странице.
// Разница только в источнике косметики: здесь он может содержать примеряемые предметы.
function _looksRenderCard(sel){
  const d=_profileData||{};
  const glow=_looksCos(sel.name_glow), frame=_looksCos(sel.avatar_frame), title=_looksCos(sel.title);
  const halo=_looksCos(sel.avatar_halo), bg=_looksCos(sel.profile_bg), fx=_looksCos(sel.card_fx);
  const lvl=d.account_level||d.chats?.[0]?.user_level||1;
  const xpPerLvl=d.xp_to_next||d.xp_per_level||3000;
  const xpInLvl=typeof d.xp_into==='number'?d.xp_into:((d.chats?.[0]?.user_xp||0)%xpPerLvl);
  const xpPct=Math.min(100,Math.round(xpInLvl/xpPerLvl*100));
  const avatar=(typeof _vipAvatar!=='undefined'&&_vipAvatar)
    ?`<img src="${esc(_vipAvatar)}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;display:block">`
    :(d.is_vip?'👑':'🔮');
  const uid=d.user_id||_uid||0;
  const lineageStyle=_looksLineageStyle({avatar_frame:frame,avatar_halo:halo,card_fx:fx,profile_bg:bg});
  const transitionStyle=_looksFittingViewTransitionActive?'view-transition-name:looks-fitting-card':'';
  return `<div class="hero fit-player-card ${bg?bg.css:''}"${transitionStyle?` style="${transitionStyle}"`:''}>
    ${fx?`<div class="card-fx ${fx.css}"></div>`:''}
    <div class="hero-head${lineageStyle?' lineage-link':''}"${lineageStyle?` style="${lineageStyle}"`:''}>
      <div class="ava ${frame?frame.css:''} ${halo?halo.css:''}" id="fit-ava">${avatar}</div>
      <div class="profile-copy">
        <div class="pname ${glow?glow.css:''}">@${esc(vipName(d.username||'Игрок',d.is_vip))}</div>
        <div class="prank">${esc(d.rank||'Игрок')}</div>
        ${title?`<div class="ptitle${title.css?' '+title.css:''}">${esc(title.text||title.name)}</div>`:''}
      </div>
    </div>
    <div class="hero-xp">
      <div class="xp-bar"><div class="xp-fill" style="width:${xpPct}%"></div></div>
      <div class="xp-lbl"><span>Уровень ${lvl}</span><span>${fmt(xpInLvl)} / ${fmt(xpPerLvl)} XP</span></div>
    </div>
    ${typeof d.combat_power==='number'?`<div class="cp-hero fit-cp-hero"><div class="cp-hero-lbl">⚡ ИНДЕКС СИЛЫ</div><div class="cp-hero-val">${fmt(d.combat_power)}</div></div>`:''}
    <div class="stats">
      <div class="stat"><div>🪙</div><div class="sv">${fmt(d.mora||0)}</div><div class="sl">Мора</div></div>
      <div class="stat"><div>💎</div><div class="sv">${fmtF(d.diamonds||0)}</div><div class="sl">Алмазы</div></div>
      <div class="stat"><div>✨</div><div class="sv">${Math.floor(d.zarniki||0)}</div><div class="sl">Зарники</div></div>
      <div class="stat"><div>🏆</div><div class="sv">${fmt(d.achievements||0)}</div><div class="sl">Ачивки</div></div>
    </div>
    ${uid?`<div class="fit-player-id"><span>🆔 <code>${uid}</code></span><button class="btn btn-ghost btn-sm" onclick="copyUid(${Number(uid)})">📋 Копировать</button></div>`:''}
  </div>`;
}
function _looksChanged(){ return _LOOKS_SLOTS.some(s=>(_looksSel[s]||null)!==(_looksSaved[s]||null)); }

function _looksFabHtml(){
  if(!_looksData) return '';
  const sel=_looksHeroSel();
  const frame=_looksCos(sel.avatar_frame), halo=_looksCos(sel.avatar_halo);
  const trialCount=Object.keys(_looksTrial).length, hasTrial=trialCount>0;
  const trialNoun=trialCount===1?'предмет':trialCount>=2&&trialCount<=4?'предмета':'предметов';
  const sub=hasTrial?`${trialCount} ${trialNoun} · ${_looksTrialTotal()}✨`:'Открыть свой образ';
  return `<button class="looks-fab" onclick="_looksOpenFittingSheet()" aria-label="Примерочная — ${sub}">
    <span class="looks-fab-avatar"><span class="ava looks-fab-ava ${frame?frame.css:''} ${halo?halo.css:''}">${_looksData.vip?'👑':'🔮'}</span></span>
    <span class="looks-fab-copy"><span class="looks-fab-label">Примерочная</span><span class="looks-fab-sub">${sub}</span></span>
    ${hasTrial?`<span class="looks-fab-badge">${trialCount}</span>`:''}
    <span class="looks-fab-arrow" aria-hidden="true">›</span>
  </button>`;
}
function _looksRenderFab(){
  let dock=el('looks-dock');
  if(_activePage!=='looks'){
    if(dock) dock.innerHTML='';
    return;
  }
  if(!dock){
    dock=document.createElement('div');
    dock.id='looks-dock';
    document.body.appendChild(dock);
  }
  dock.innerHTML=_looksFabHtml();
}

function _looksOpenFittingSheetNow(sharedTransition=false){
  OM('🎨 Примерочная', _looksFittingSheetBodyHtml(), _looksFittingSheetButtons());
  el('modal').classList.add('looks-fitting-modal');
  if(sharedTransition) el('modal').classList.add('looks-fitting-shared');
}
function _looksOpenFittingSheet(){
  const source=_looksLastTouchedCosmetic
    ?document.querySelector(`.looks-card[data-cos="${_looksLastTouchedCosmetic}"]`)
    :null;
  const rect=source&&source.getBoundingClientRect();
  const sourceVisible=!!rect&&rect.width>0&&rect.height>0&&rect.bottom>0&&rect.top<innerHeight;
  const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(!document.startViewTransition||document.body.classList.contains('no-fx')||reduceMotion||!sourceVisible){
    _looksOpenFittingSheetNow(false);
    return;
  }
  // Связываем только последнюю реально видимую карточку с итоговой карточкой
  // игрока. Состояние примерки меняется ДО этого, поэтому анимация ничего не
  // маскирует и остаётся чисто навигационной подсказкой.
  source.style.viewTransitionName='looks-fitting-card';
  _looksFittingViewTransitionActive=true;
  let transition;
  try{
    transition=document.startViewTransition(()=>{
      source.style.removeProperty('view-transition-name');
      _looksOpenFittingSheetNow(true);
    });
  }catch(e){
    source.style.removeProperty('view-transition-name');
    _looksFittingViewTransitionActive=false;
    _looksOpenFittingSheetNow(false);
    return;
  }
  transition.finished.finally(()=>{
    _looksFittingViewTransitionActive=false;
    const target=document.querySelector('#looks-fit-top .fit-player-card');
    if(target) target.style.removeProperty('view-transition-name');
  });
}
function _looksTrialTotal(){
  return Object.entries(_looksTrial).reduce((sum,[slot,id])=>{
    const it=_looksCos(id), meta=_looksTrialMeta[slot];
    return sum+((it&&it.price&&it.price[0]&&it.price[0].zarniki)||(meta&&meta.price)||0);
  },0);
}
function _looksFittingSlotChipsHtml(){
  const hero=_looksHeroSel();
  const used=_LOOKS_SLOTS.filter(slot=>hero[slot]).length;
  const trialCount=Object.keys(_looksTrial).length;
  const trialTotal=_looksTrialTotal();
  const selectedItems=_LOOKS_SLOTS.map(slot=>{
    const id=hero[slot];
    return id?(_looksCos(id)||_looksTrialMeta[slot]||null):null;
  }).filter(Boolean);
  const selectedLineups=[...new Set(selectedItems.map(it=>it.lineup).filter(Boolean))];
  const fullLineup=used===_LOOKS_SLOTS.length&&selectedLineups.length===1?selectedLineups[0]:'';
  const setColor=lineupColor(fullLineup);
  const setName=fullLineup?String(lineupLabel(fullLineup)).replace(/^\S+\s*/,''):'Собранный образ';
  const setKicker=fullLineup?'Полная коллекция':`${used} из ${_LOOKS_SLOTS.length} предметов`;
  const setState=trialCount===used&&used>0?'Вся коллекция в примерочной':trialCount?`${trialCount} в примерочной`:'Ваш текущий образ';
  return `<section class="fit-outfit" aria-label="Состав образа">
    <div class="fit-collection-card" style="--fit-set:${setColor};--fit-set-wash:${setColor}18;--fit-set-edge:${setColor}66">
      <div class="fit-collection-head${fullLineup?'':' fit-collection-head--mixed'}">
        ${fullLineup?`<div class="fit-collection-sig" style="--c:${setColor}">${_looksCollectionIconSvg(fullLineup)}</div>`:''}
        <div class="fit-collection-copy"><span class="fit-collection-kicker">${esc(setKicker)}</span><strong class="fit-collection-name">${esc(setName)}</strong><span class="fit-collection-state">${esc(setState)}</span></div>
        ${trialTotal?`<strong class="fit-collection-total">${trialTotal}✨</strong>`:`<span class="fit-collection-count">${used}/${_LOOKS_SLOTS.length}</span>`}
      </div>
      <div class="fit-outfit-list">${_LOOKS_SLOTS.map(slot=>{
    const rawLabel=_LOOKS_SLOT_LABEL[slot]||slot;
    const icon=rawLabel.split(' ')[0], slotLabel=rawLabel.replace(/^\S+\s*/, '');
    const trialId=_looksTrial[slot];
    if(trialId){
      const it=_looksCos(trialId)||_looksTrialMeta[slot];
      const price=(it&&it.price&&it.price[0]&&it.price[0].zarniki)||(it&&it.price)||0;
      const c=lineupColor(it&&it.lineup);
      return `<button class="fit-outfit-row trial" style="--fit-c:${c};--fit-bg:${c}18" aria-label="${esc(it?it.name:'Предмет')} — ${price} зарников" onclick="_looksBuyFromPreview('${trialId}',0,'${slot}')"><span class="fit-outfit-icon">${icon}</span><span class="fit-outfit-main"><span class="fit-outfit-slot">${esc(slotLabel)}</span><strong>${esc(it?it.name:'Предмет')}</strong></span><span class="fit-outfit-state"><b>${price}✨</b></span></button>`;
    }
    const ownedId=_looksSel[slot];
    if(ownedId){
      const it=_looksCos(ownedId), state=_looksSaved[slot]===ownedId?'Надето':'Выбрано';
      const c=lineupColor(it&&it.lineup);
      return `<div class="fit-outfit-row owned" style="--fit-c:${c};--fit-bg:${c}14"><span class="fit-outfit-icon">${icon}</span><span class="fit-outfit-main"><span class="fit-outfit-slot">${esc(slotLabel)}</span><strong>${esc(it?it.name:'Предмет')}</strong></span><span class="fit-outfit-state">${state}</span></div>`;
    }
    return `<div class="fit-outfit-row empty"><span class="fit-outfit-icon">${icon}</span><span class="fit-outfit-main"><span class="fit-outfit-slot">${esc(slotLabel)}</span><strong>Слот свободен</strong></span><span class="fit-outfit-state">Свободно</span></div>`;
  }).join('')}</div>
    </div>
    ${used<_LOOKS_SLOTS.length?'<div class="fit-outfit-hint">Выберите предмет в каталоге — он сразу появится на карточке и в составе образа.</div>':''}
  </section>`;
}
function _looksFittingSheetButtons(){
  const hasTrial=Object.keys(_looksTrial).length>0;
  const hasFree=_looksChanged();
  if(!hasFree&&!hasTrial) return [{l:'Закрыть',c:'btn-ghost',f:'CM()'}];
  {
    const total=_looksTrialTotal(), bal=(_looksData.balances||{}).zarniki||0;
    const can=!hasTrial||bal>=total;
    const label=hasTrial?(can?`Купить и применить · ${total}✨`:`Не хватает ${Math.max(0,total-Math.floor(bal))}✨`):'✓ Применить';
    return [{l:'↺ Сбросить',c:'btn-ghost',f:'_looksResetTrialAndRerenderSheet()'},{l:label,c:can?'btn-gold':'btn-ghost',d:!can,f:'_looksBuyAndApplyAll(this)'}];
  }
}
function _looksFittingSheetBodyHtml(){
  return `<div id="looks-fit-top">${_looksRenderCard(_looksHeroSel())}</div>${_looksFittingSlotChipsHtml()}`;
}
function _looksRerenderFittingSheetIfOpen(){
  const dlg=el('modal'); if(dlg&&dlg.open){
    const body=el('mb'), foot=el('mf');
    if(body) body.innerHTML=_looksFittingSheetBodyHtml();
    if(foot) foot.innerHTML=_looksFittingSheetButtons().map(b=>`<button class="btn btn-sm ${b.c||'btn-ghost'}" onclick="${String(b.f||'').replace(/"/g,'&quot;')}" ${b.d?'disabled':''}>${b.l}</button>`).join('');
  }
}
function _looksResetTrialAndRerenderSheet(){ _looksReset(); _looksRerenderFittingSheetIfOpen(); }
function _looksBuyAndApplyAll(btn){
  if(btn) btn.disabled=true;
  const trialIds=Object.values(_looksTrial);
  const requestKey=btn?.dataset.requestKey||economyRequestKey('cosmetic-fitting');
  if(btn)btn.dataset.requestKey=requestKey;
  const buy=trialIds.length?api('/cosmetics/buy-many',{method:'POST',headers:{'Idempotency-Key':requestKey},body:JSON.stringify({cosmetic_ids:trialIds})}):Promise.resolve(null);
  buy.then(r=>{
      if(btn)delete btn.dataset.requestKey;
      if(r){toast(r.message); refreshCurrBar();}
      Object.entries(_looksTrial).forEach(([slot,id])=>{_looksSel[slot]=id;});
      _looksClearTrial();
      return _looksApply();
    })
    .then(()=>_looksReloadCatalog())
    .then(()=>CM())
    .catch(e=>{toast(e,false); if(btn) btn.disabled=false;});
}
function _looksGridHtml(slot){
  const q=_looksSearch.trim().toLowerCase();
  const items=(_looksData.slots[slot]||[]).filter(it=>
    (_looksFilter==='all'||it.lineup===_looksFilter) &&
    (_looksStatus==='all'||(_looksStatus==='owned'?it.owned:!it.owned)) &&
    (!q||it.name.toLowerCase().includes(q)));
  const none=`<div class="looks-card ${_looksShownId(slot)==null?'sel':''}" data-cos="__none__" onclick="_looksUnequip('${slot}')">
    <div class="lc-sw lc-sw--none">✖</div><div class="lc-name">Без</div></div>`;
  const empty=items.length?'':`<div class="looks-empty"><div class="looks-empty-ico">🔍</div>Ничего не найдено по этому фильтру</div>`;
  return `<div class="looks-cards">${none}${items.map(it=>_looksCard(slot,it)).join('')}${empty}</div>`;
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
function _looksCard(slot,it){
  const sel=_looksShownId(slot)===it.id;
  const trial=!it.owned && _looksTrial[slot]===it.id;
  const sw=_looksSwatch(slot,it);
  const rar=`<span class="lc-rar" style="color:${lineupColor(it.lineup)}">${esc(lineupLabel(it.lineup))}</span>`;
  // Статичный акцент цвета линейки (не анимация — .lc-sw уже намеренно без
  // анимации из-за перф, см. app.css:1925). r-{rarity} класс НЕ убираю —
  // им пользуется модалка сундуков/крафта (осталась на старой системе).
  const accentStyle=`style="--lc:${lineupColor(it.lineup)};--lcg:${lineupColor(it.lineup)}22"`;
  if(it.owned){
    const offBadge=it.vip_locked_inactive?'<span class="lc-vip-off">⏸ нужна VIP</span>':'';
    return `<div class="looks-card lc-lineup-accent r-${it.rarity} ${sel?'sel':''} ${it.vip_locked_inactive?'lc-dim':''}" ${accentStyle} data-cos="${it.id}" onclick="_looksEquip('${slot}','${it.id}')">
      ${sw}<div class="lc-name">${esc(it.name)}</div>
      <div class="lc-foot">${rar}${offBadge}${(!it.vip_locked_inactive&&_looksSaved[slot]===it.id)?'<span class="lc-on">✓ надето</span>':''}</div></div>`;
  }
  const vip=it.vip_required?'<span class="lc-vip">VIP</span>':'';
  const priceTxt=it.price&&it.price.length?`<span class="lc-price-hint">${_looksPriceTxt(it.price[0])}</span>`:'';   // _looksPriceTxt уже с иконкой ✨
  return `<div class="looks-card lc-lineup-accent r-${it.rarity} locked lc-buyable ${sel?'sel':''}${trial?' lc-trial':''}" ${accentStyle} data-cos="${it.id}" onclick="_looksTapUnowned('${slot}','${it.id}')">
    ${sw}<div class="lc-name">${trial?'🔮':'🔒'} ${esc(it.name)} ${vip}</div>
    <div class="lc-foot">${rar}${priceTxt}${trial?'<span class="lc-trial-state">Примеряется</span>':'<span class="lc-prev-hint">👁</span>'}</div></div>`;
}
// Финальный ревью Стадии 3: перезагружает каталог после покупки/применения БЕЗ
// сброса навигационного состояния (открытая коллекция/фильтр/поиск) — в
// отличие от openLooksModal(), которая рассчитана на «холодный» вход в вкладку
// и раньше использовалась здесь как попало «перезагрузить кэш» — из-за чего
// покупка предмета ИЗНУТРИ детального экрана коллекции выкидывала игрока
// обратно на сетку карточек (тот же баг класса, что и с переключателем
// режимов — новое состояние встретилось со старым «reload», который его
// не знал и сбрасывал).
function _looksReloadCatalog(){
  // Ревью финального ревью: openLooksModal() тянет и /cosmetics/presets тоже
  // (Promise.all), но только на «холодном» входе (if(!_looksData)) — этот
  // хелпер вызывается, когда _looksData УЖЕ не пуст, так что тот путь никогда
  // не сработал бы. Без явного рефетча тут пресеты один раз ушли бы в 0 и
  // оставались 0 до полной перезагрузки страницы (originSessionId бага —
  // .superpowers/sdd/progress.md, финальное ревью Стадии 3).
  // .catch на пресетах отдельно от каталога: иначе сбой ЧТЕНИЯ пресетов (сеть,
  // 500) топит ВЕСЬ reload — включая случай, когда его вызвали ПОСЛЕ успешной
  // платной покупки (см. _looksBuyFromPreview) — игрок теряет деньги/предмет
  // на сервере, но видит ошибку и не видит купленное на экране.
  return Promise.all([api('/cosmetics/'),api('/cosmetics/presets').catch(()=>({presets:_looksPresets}))]).then(([d,pr])=>{
    _looksData=d; _looksSaved=_looksEquipped(d); _looksSel={..._looksSaved};
    _looksPresets=pr.presets||[];
    _looksSanitizeTrial();
    renderLooks();
  });
}
// Покупка одного предмета: удаляет только его примерку. Остальные слоты в
// примерочной сохраняются и после обновления каталога остаются в шторке.
const _looksPurchaseKeys=new Map();
function _looksBuyFromPreview(id,opt,slot){
  const keySlot=`${id}:${opt}`;
  const requestKey=_looksPurchaseKeys.get(keySlot)||economyRequestKey(`cosmetic-${id}`);
  _looksPurchaseKeys.set(keySlot,requestKey);
  api('/cosmetics/buy',{method:'POST',headers:{'Idempotency-Key':requestKey},body:JSON.stringify({cosmetic_id:id,option_index:opt})})
    .then(r=>{_looksPurchaseKeys.delete(keySlot); toast(r.message); refreshCurrBar(); _looksDirty=true;
      return api('/cosmetics/equip',{method:'POST',body:JSON.stringify({cosmetic_id:id})});})
    .then(()=>{toast('✅ Надето!'); _looksDropTrial(slot); return _looksReloadCatalog();})
    .then(()=>_looksRerenderFittingSheetIfOpen())
    .catch(e=>toast(e,false));
}

// Примерка перекрывает выбранное только в том же слоте: можно держать несколько
// неоплаченных предметов одновременно, по одному на слот.
function _looksShownId(slot){ return _looksTrial[slot]||_looksSel[slot]||null; }
function _looksHeroSel(){ const sel={..._looksSel}; Object.keys(_looksTrial).forEach(slot=>{sel[slot]=_looksTrial[slot];}); return sel; }
function _looksHeroDiffers(){ const hs=_looksHeroSel(); return _LOOKS_SLOTS.some(s=>(hs[s]||null)!==(_looksSaved[s]||null)); }
function _looksEquip(slot,id){ _looksLastTouchedCosmetic=id; _looksSel[slot]=id; _looksDropTrial(slot); _looksRenderFab(); _looksMarkSel(slot); }
function _looksUnequip(slot){ _looksLastTouchedCosmetic=''; _looksSel[slot]=null; _looksDropTrial(slot); _looksRenderFab(); _looksMarkSel(slot); }
function _looksReset(){ _looksSel={..._looksSaved}; _looksClearTrial(); _looksRenderFab(); _LOOKS_SLOTS.forEach(_looksMarkSel); }
function _looksTapUnowned(slot,id){ _looksLastTouchedCosmetic=id; _looksSetTrial(slot,id); _looksRenderFab(); _looksMarkSel(slot); }
// Перф: точечно переставить .sel в сетке ЭТОГО слота (без пересборки innerHTML —
// это и был источник «подлагивания»: раньше каждый тап перерисовывал весь грид).
function _looksMarkSel(slot){
  // Выбор примерки меняет не только обводку, но и смысл карточки: замок
  // превращается в «Примеряется». Поэтому обновляем лишь сетку этого слота —
  // без пересборки всей страницы и без скачка её прокрутки.
  _looksRenderSectionGrid(slot);
}

// ── Пресеты образов ────────────────────────────────────────────────────────────
function _looksPresetCountLabel(count){
  const tail=count%100, last=count%10;
  const noun=tail>=11&&tail<=14?'образов':last===1?'образ':last>=2&&last<=4?'образа':'образов';
  return `${count} ${noun}`;
}
function _looksPresetsHtml(){
  const cards=_looksPresets.map(p=>`<article class="looks-preset-card" data-preset="${p.id}">
    <button class="btn-plain looks-preset-apply" onclick="_applyPreset(${p.id})" title="Применить образ «${esc(p.name)}»">
      <span class="looks-preset-orb" aria-hidden="true">💾</span>
      <span class="looks-preset-copy"><span class="looks-preset-name">${esc(p.name)}</span><span class="looks-preset-kind">Твой образ</span></span>
    </button>
    <button class="btn-plain looks-preset-del" onclick="_deletePreset(${p.id})" title="Удалить образ «${esc(p.name)}»" aria-label="Удалить образ «${esc(p.name)}»"><span class="looks-preset-del-icon" aria-hidden="true"></span></button>
  </article>`).join('');
  const save=`<button class="looks-preset-card looks-preset-card--add" type="button" onclick="_savePreset()">
    <span class="looks-preset-orb looks-preset-orb--add" aria-hidden="true">＋</span>
    <span class="looks-preset-copy"><span class="looks-preset-name">Сохранить</span><span class="looks-preset-kind">Новый образ</span></span>
  </button>`;
  const empty=!_looksPresets.length?'<div class="looks-presets-empty">Сохраните удачную комбинацию, чтобы вернуть её одним тапом.</div>':'';
  return `<section class="looks-presets" id="looks-presets" aria-label="Сохранённые образы">
    <div class="looks-presets-head"><span>💾 Образы</span>${_looksPresets.length?`<span>${_looksPresetCountLabel(_looksPresets.length)}</span>`:''}</div>
    ${empty}<div class="looks-presets-row">${cards}${save}</div>
  </section>`;
}
// UX_AUDIT С16: bottom-sheet с полем вместо нативного prompt()
function _savePreset(){
  OM('💾 Сохранить образ',
    `<div class="set-hint">Текущая косметика сохранится как образ — потом применишь одним тапом.</div>
     <input id="preset-name-inp" class="num-input" type="text" maxlength="30"
       placeholder="Название образа (до 30 символов)" autocomplete="off" style="margin-top:10px">`,
    [{l:'💾 Сохранить',c:'btn-gold',f:'_savePresetGo()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
  setTimeout(()=>{const i=el('preset-name-inp'); if(i) i.focus();},60);
}
function _savePresetGo(){
  const name=((el('preset-name-inp')||{}).value||'').trim().slice(0,30)||'Образ';
  api('/cosmetics/presets',{method:'POST',body:JSON.stringify({name})})
    .then(r=>{toast(r.message); if(r.preset){_looksPresets.push(r.preset);} CM(); renderLooks();})
    .catch(e=>toast(e,false));
}
function _applyPreset(id){
  api(`/cosmetics/presets/${id}/apply`,{method:'POST'})
    .then(r=>{toast(r.message); _looksDirty=true; return _looksReloadCatalog();})
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
function _looksWelcomeSectionHtml(){
  const w=_looksData.welcome; if(!w) return '';
  const cards=(w.options||[]).map(o=>{
    const cls=['looks-card','welcome-card','r-'+o.rarity]; if(o.current)cls.push('sel'); if(o.locked)cls.push('locked');
    const vip=o.vip_required?' <span class="lc-vip">VIP</span>':'';
    const state=o.current?'✓ Сейчас используется':(o.locked?'🔒 Доступно с VIP':o.desc);
    return `<div class="${cls.join(' ')}" data-welcome="${o.id}" onclick="_welcomePick('${o.id}')">
      <div class="lc-name">${o.locked?'🔒 ':''}${esc(o.name)}${vip}</div>
      <div class="lc-tag${o.current?' welcome-state-current':''}${o.locked?' welcome-state-locked':''}">${esc(state)}</div></div>`;
  }).join('');
  const hint=_looksData.vip?'':'<div class="looks-hint">👆 Нажмите на режим — увидите его в превью. «Вспышка» доступна с VIP.</div>';
  return `<section class="looks-section" id="looks-sec-welcome">
    <div class="looks-sec-t">${_LOOKS_ANCHOR_LABEL.welcome}</div>
    <div id="wpreview" class="wpreview"></div>${hint}
    <div class="looks-welcome-cards">${cards}</div>
  </section>`;
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
// Точечно перерисовать секцию приветствия (список карточек «выбрано»/локи) —
// не всю страницу. wpreview восстанавливаем следом, т.к. новая разметка его очищает.
function _looksRenderWelcomeSection(){
  const sec=el('looks-sec-welcome'); if(!sec) return;
  sec.outerHTML=_looksWelcomeSectionHtml();
  _wpMode=null; _playWelcomePreview(_looksData.welcome&&_looksData.welcome.current);
}
function _setWelcome(id){
  if(!_looksData||!_looksData.welcome) return;
  const w=_looksData.welcome, prev=w.current;
  if(id===prev) return;
  w.current=id; (w.options||[]).forEach(o=>o.current=(o.id===id));
  _looksRenderWelcomeSection(); _looksDirty=true;
  api('/cosmetics/welcome',{method:'POST',body:JSON.stringify({animation_id:id})})
    .then(r=>toast(r.message))
    .catch(e=>{toast(e,false); w.current=prev;
      (w.options||[]).forEach(o=>o.current=(o.id===prev)); _looksRenderWelcomeSection();});
}

// ── Темы профиля — секция экрана «Внешний вид» ──────────────────────────────────
// Миграция блока 7: раньше отдельная вкладка Профиль→Темы (модалка-на-тему через
// openThemeModal). Здесь — тот же паттерн, что у косметики: тап примеряет тему
// инлайн (raw-string превью с бэка, как и было — /themes/preview/{id}), без ухода
// в модалку. _themeData/themeStatusBadge переиспользуются из app.05.js.
let _looksThemeSel=null, _looksThemeFilter='all';
function _looksThemesEnsureLoaded(){
  if(_themeData){ _looksRenderThemesGrid(); _looksThemeShowInitialPreview(); return; }
  api('/themes/').then(themes=>{ _themeData=themes; _looksRenderThemesGrid(); _looksThemeShowInitialPreview(); })
    .catch(e=>{ const g=el('looks-grid-themes'); if(g) g.innerHTML=`<div class="err">${e}</div>`; });
}
// У темы всегда есть контекст: после возврата на экран восстанавливаем последний
// просмотр, а при первом входе — активную тему. Пустая декоративная плашка не
// объясняла игроку, что именно он видит и зачем нужны карточки ниже.
function _looksThemeShowInitialPreview(){
  if(!_themeData) return;
  const selected=_themeData.find(t=>t.theme_id===_looksThemeSel)
    ||_themeData.find(t=>t.active)||_themeData[0];
  if(selected) _looksThemeTap(selected.theme_id);
}
function _looksThemesSectionHtml(){
  return `<section class="looks-section" id="looks-sec-themes">
    <div class="looks-sec-t">${_LOOKS_ANCHOR_LABEL.themes}</div>
    <div id="looks-theme-preview" class="looks-theme-preview"></div>
    <div class="tabs tab-inner looks-theme-filter" id="looks-theme-filter">
      <button class="tb looks-theme-chip active" data-f="all" onclick="_looksThemeSetFilter('all')">Все</button>
      <button class="tb looks-theme-chip" data-f="owned" onclick="_looksThemeSetFilter('owned')">Мои</button>
      <button class="tb looks-theme-chip" data-f="premium" onclick="_looksThemeSetFilter('premium')">✨ Премиум</button>
    </div>
    <div class="looks-sec-grid" id="looks-grid-themes"><div class="loader">Загрузка…</div></div>
  </section>`;
}
function _looksThemeSetFilter(f){
  _looksThemeFilter=f;
  const bar=el('looks-theme-filter');
  if(bar) bar.querySelectorAll('.looks-theme-chip').forEach(c=>c.classList.toggle('active', c.getAttribute('data-f')===f));
  _looksRenderThemesGrid();
}
function _looksRenderThemesGrid(){
  const g=el('looks-grid-themes'); if(!g||!_themeData) return;
  const filtered=_looksThemeFilter==='owned'?_themeData.filter(t=>t.owned||t.active)
    :_looksThemeFilter==='premium'?_themeData.filter(t=>t.premium)
    :_themeData;
  if(!filtered.length){ g.innerHTML='<div class="looks-empty">Нет тем в этой категории</div>'; return; }
  g.innerHTML=`<div class="looks-cards looks-theme-cards">${filtered.map(_looksThemeCard).join('')}</div>`;
}
function _looksThemeAvailabilityText(t){
  if(t.active) return 'Надета сейчас';
  if(t.owned) return 'В коллекции';
  if(t.source&&t.source.startsWith('gacha')) return 'Выпадает в Гаче';
  if(t.source==='event') return 'Награда ивента';
  if(t.price_mora) return `Купить · ${fmt(t.price_mora)} 🪙`;
  if(t.price_diamonds) return `Купить · ${t.price_diamonds} 💎`;
  if(t.price_zarniki) return `Купить · ${fmt(t.price_zarniki)} ✨`;
  if(t.price_dark) return `Купить · ${t.price_dark} 🌑`;
  return 'Способ получения неизвестен';
}
function _looksThemeCard(t){
  // БАГ 2026-07-23: раньше сюда впихивали ПОЛНУЮ декоративную «шапку» темы (top/bot_line) —
  // некоторые темы используют длинные безпробельные строки (fullwidth-текст, эмодзи-паттерны
  // без пробелов), браузер не может их перенести — карточка требовала ширину больше своей
  // колонки, и вся сетка/страница уезжала вбок (растягивала сайт по ширине). Правильное
  // место для полной «шапки» — inline-превью сверху секции (уже есть, тап по карточке),
  // а в самой карточке — компактная иконка+имя, как у остальной косметики (.lc-sw).
  const sel=_looksThemeSel===t.theme_id;
  const accent=t.accent||(t.top||'').trim().charAt(0)||'🎭';
  const pattern=(t.top||t.bot_line||accent).replace(/\s+/g,' ').trim();
  return `<div class="looks-card theme-card r-${esc(t.rarity||'common')}${t.active?' sel':''}${sel&&!t.active?' theme-previewing':''}" data-theme="${t.theme_id}" onclick="_looksThemeTap('${t.theme_id}')">
    <div class="theme-card-swatch"><span class="theme-card-pattern">${esc(pattern)}</span><span class="theme-card-accent">${esc(accent)}</span></div>
    <div class="theme-card-copy"><div class="lc-name">${esc(t.name)}</div><div class="theme-card-meta">${esc(_looksThemeAvailabilityText(t))}</div></div>
  </div>`;
}
function _looksThemeTap(tid){
  if(!_themeData) return;
  const t=_themeData.find(x=>x.theme_id===tid); if(!t) return;
  _looksThemeSel=tid;
  document.querySelectorAll('#looks-grid-themes .looks-card').forEach(c=>{
    const cardTheme=_themeData.find(x=>x.theme_id===c.getAttribute('data-theme'));
    const active=!!(cardTheme&&cardTheme.active);
    c.classList.toggle('sel', active);
    c.classList.toggle('theme-previewing', c.getAttribute('data-theme')===tid&&!active);
  });
  const box=el('looks-theme-preview'); if(!box) return;
  box.innerHTML='<div class="loader">Загрузка превью…</div>';
  api(`/themes/preview/${tid}`).then(r=>{
    const price=t.price_mora?`${fmt(t.price_mora)} 🪙`:t.price_diamonds?`${t.price_diamonds} 💎`
      :t.price_zarniki?`${fmt(t.price_zarniki)} ✨`:t.price_dark?`${t.price_dark} 🌑`:null;
    const buyable=price&&(t.source==='shop_mora'||t.source==='shop_diamond'||t.source==='zarniki'||t.source==='dark');
    let actionHtml='';
    if(t.active) actionHtml='<div class="looks-theme-active">✓ Активная тема</div>';
    else if(t.owned) actionHtml=`<button class="btn btn-sm btn-gold btn-full" onclick="_looksThemeEquip('${tid}')">✓ Надеть</button>`;
    else if(buyable) actionHtml=`<button class="btn btn-sm btn-gold btn-full" onclick="_looksThemeBuy('${tid}')">Купить — ${price}</button>`;
    const stateLabel=t.active?'Сейчас на профиле':'Предпросмотр темы';
    box.innerHTML=`<div class="looks-theme-kicker">${stateLabel}</div><div class="profile-preview" style="min-height:40px">${r.text||''}</div>
      <div class="looks-theme-name">${esc(t.name)} · ${_rarLabel(t.rarity)}</div>
      ${t.desc?`<div class="looks-theme-desc">${esc(t.desc)}</div>`:''}
      ${actionHtml}`;
  }).catch(()=>{ box.innerHTML='<span style="color:var(--muted);font-size:11px">Нет данных профиля</span>'; });
}
function _looksThemeBuy(tid){
  api('/themes/buy',{method:'POST',body:JSON.stringify({theme_id:tid})})
    .then(r=>{ toast(`✅ ${r.theme_name} куплена!`); _themeData=null; refreshCurrBar();
      _looksThemesEnsureLoaded(); _looksThemeTap(tid); })
    .catch(e=>toast(e,false));
}
function _looksThemeEquip(tid){
  api('/themes/equip',{method:'POST',body:JSON.stringify({theme_id:tid})})
    .then(()=>{ toast('✅ Тема активирована!'); _themeData=null; loadProfile();
      _looksThemesEnsureLoaded(); _looksThemeTap(tid); })
    .catch(e=>toast(e,false));
}
// ── БЛОК21 #3: сундуки-сюрпризы + крафт косметики из осколков ────────────────────
function _openSurprisesModal(){
  // Модалка доступна и НЕ из вкладки «Внешний вид» (напр. категория «сундуки»
  // инвентаря, app.04.js::openItemModal) — «← К внешнему виду» ОБЯЗАН сам
  // переключить страницу (switchPage), _looksReloadCatalog() этого не делает
  // (он только для «уже на вкладке, просто обновить кэш»).
  OM('🎁 Сюрпризы и Крафт','<div class="loader">Загрузка...</div>',[{l:'← К внешнему виду',c:'btn-ghost',f:"CM();switchPage('looks');_looksReloadCatalog()"}]);
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
    .then(r=>{ _looksDirty=true; _looksData=null; _chestReveal(r.drop||{}); })   // владение могло измениться → кэш инвалидировать (иначе счётчики измерителя устареют)
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
    .then(r=>{ toast(r.message); _looksDirty=true; _looksData=null; _openSurprisesModal(); })   // владение изменилось → кэш инвалидировать
    .catch(e=>{toast(e,false); if(btn) btn.disabled=false;});
}
