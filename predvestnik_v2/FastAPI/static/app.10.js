// ── Конструктор «Внешний вид» (косметика профиля) ──────────────────────────────
// Редизайн (блок 7, 2026-07-23): вкладки убраны — один непрерывный скролл по всем
// секциям + чипы-якоря (скроллят к секции, не переключают панель) + прилипающее
// превью сверху, видно всегда. Раньше приходилось листать вкладки И скроллить
// наверх, чтобы увидеть «как оно будет выглядеть» — теперь ни то, ни другое.
const _LOOKS_SLOTS=['name_glow','avatar_frame','avatar_halo','title','profile_bg','card_fx'];
const _LOOKS_SLOT_LABEL={name_glow:'✨ Ореол имени',avatar_frame:'🖼 Рамка аватара',avatar_halo:'🌟 Гало аватара',title:'🏷 Титул',profile_bg:'🖌 Фон профиля',card_fx:'❄️ Частицы карточки'};
const _LOOKS_ANCHOR_LABEL={name_glow:'✨ Ореол',avatar_frame:'🖼 Рамка',avatar_halo:'🌟 Гало',title:'🏷 Титул',profile_bg:'🖌 Фон',card_fx:'❄️ Частицы',welcome:'🎬 Вход',themes:'🎭 Темы'};
let _looksData=null, _looksSel={}, _looksSaved={}, _looksDirty=false, _looksFocus=null;
let _looksPresets=[];  // кэш пресетов текущей сессии
let _looksFilter='all';                // фильтр ЛИНЕЙКИ (id из _looksData.lineups) — общий для ВСЕХ секций разом
let _looksStatus='all';                // фильтр СТАТУСА: all|owned|missing — независимое второе измерение (см. аудит 2026-07-29)
let _looksMode='collections';          // режим отображения: collections|slots — по умолчанию коллекции (Стадия 2)
let _looksDetailLineup=null;   // id открытой коллекции в детальном экране (Стадия 3); null = список карточек
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
};
function lineupMeta(id){ return (_looksData&&_looksData.lineups&&_looksData.lineups[id])||null; }
function lineupLabel(id){ const l=lineupMeta(id); return l?l.name:(id||'—'); }
function lineupColor(id){ return LINEUP_COLOR[id]||'#9aa7b8'; }
// Полноэкранный экран «Внешний вид» (был модалкой). Имя openLooksModal сохранено —
// его зовут старые точки входа (профиль/маркет), диплинки и «назад» из под-шитов.
function openLooksModal(){
  _looksFilter='all'; _looksStatus='all'; _looksSearch=''; _looksFocus=null; _looksDetailLineup=null;
  if(!_looksData){   // режим восстанавливаем только на «холодном» открытии — не сбрасывать выбор пользователя, если он уже листает вкладку
    try{ const saved=localStorage.getItem('pv_looks_mode'); if(saved==='collections'||saved==='slots') _looksMode=saved; }catch(e){}
  }
  switchPage('looks');
  if(_looksData){ renderLooks(); return; }        // из кэша — БЕЗ пере-запроса (убирает лаги навигации)
  _looksDirty=false;
  const b=el('pg-looks'); if(b) b.innerHTML='<div class="loader" style="margin-top:44px">Загрузка…</div>';
  Promise.all([api('/cosmetics/'),api('/cosmetics/presets')])
    .then(([d,pr])=>{_looksData=d;_looksSaved=_looksEquipped(d);_looksSel={..._looksSaved};_looksPresets=pr.presets||[];renderLooks();})
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
function _looksClose(){   // стрелка ‹ Назад: применить незакоммиченное и вернуться в профиль
  if(_looksChanged()){ _looksApply().then(()=>{ loadProfile(); goTo('profile'); }); }
  else { if(_looksDirty) loadProfile(); goTo('profile'); }
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
  const b=el('pg-looks'); if(!b||!_looksData) return;
  const vipBar=_looksData.vip?'':`<div class="looks-vipbar">
    <span>👑 Купить можно любую косметику. Линейки дороже «Лесного Странника» <b>отображаются на профиле только с VIP</b>.</span>
    <button class="btn btn-sm btn-gold" onclick="goTo('market','vip')">Перейти к VIP</button></div>`;
  const modeBody=_looksMode==='collections'?_looksCollectionsViewHtml():_looksSlotsViewHtml();
  // «Вход»/«Темы» — ОБЩИЕ для обоих режимов (по спеку), рендерятся здесь ОДИН раз,
  // а не внутри modeBody — иначе в режиме «По коллекциям» пропал бы доступ к смене
  // приветствия/темы. Умный ряд фильтров («По слотам» режим) тоже ОБЩИЙ, но
  // находится ВНУТРИ .looks-sticky (2026-07-29: чтобы при скролле не уезжал под
  // прилипшее превью).
  const stickyFilterBar = _looksMode==='slots' ? `<div id="looks-filter-bar">${_looksFilterHtml()}</div>` : '';
  b.innerHTML=`
    <div class="looks-head">
      <button class="looks-back" onclick="_looksClose()" aria-label="Назад">‹</button>
      <div class="looks-htitle">🎨 Внешний вид</div>
    </div>
    <div class="looks-sticky"><div id="looks-top">${_looksPreviewHtml()}</div>${stickyFilterBar}</div>
    ${_looksDetailLineup?'':_looksModeToggleHtml()}`
    +vipBar
    +'<button class="btn btn-ghost btn-full" style="margin:2px 0 10px" onclick="_openSurprisesModal()">🎁 Сюрпризы и 🔹 Крафт косметики</button>'
    +_looksPresetsHtml()
    +`<div id="looks-mode-body">${modeBody}</div>`
    +`<div id="looks-common-sections">${_looksWelcomeSectionHtml()}${_looksThemesSectionHtml()}</div>`
    +`<div class="pay-terms">Покупая косметику, вы соглашаетесь с <a href="${BASE}/legal/tos" target="_blank" rel="noopener">Соглашением</a>. Цифровые товары возврату не подлежат.</div>`;
  _playWelcomePreview(_looksData.welcome&&_looksData.welcome.current);
  _looksThemesEnsureLoaded();
  _looksSyncStickyH();
}
// Режим «По слотам» — умный ряд (фильтр) живёт в .looks-sticky (рендерится в
// renderLooks), здесь только якоря и секции слотов. «Вход»/«Темы» общие, рендерятся
// отдельно в renderLooks().
function _looksSlotsViewHtml(){
  return `<div class="looks-anchors">${_LOOKS_SLOTS.map(s=>`<button class="looks-anchor-chip" onclick="_looksJump('${s}')">${_LOOKS_ANCHOR_LABEL[s]}</button>`).join('')}</div>`
    +`<div id="looks-sections">${_LOOKS_SLOTS.map(s=>_looksSectionHtml(s)).join('')}</div>`;
}
// Статистика коллекции: считается на клиенте из уже загруженных _looksData.slots
// (никакого нового запроса к бэку не нужно — lineup/owned уже есть на каждом предмете).
function _looksLineupStats(lin){
  let owned=0, total=0; const slotOwned={};
  _LOOKS_SLOTS.forEach(slot=>{
    const items=(_looksData.slots[slot]||[]).filter(it=>it.lineup===lin);
    total+=items.length;
    const hasOwned=items.some(it=>it.owned);
    if(hasOwned) owned+=items.filter(it=>it.owned).length;
    slotOwned[slot]=hasOwned;
  });
  return {owned,total,slotOwned};
}
function _looksCollectionStatusHtml(stats){
  if(stats.total===0) return `<div class="coll-status" style="color:var(--muted);background:rgba(255,255,255,.05)">не начато</div>`;
  if(stats.owned===stats.total) return `<div class="coll-status" style="color:#56c46a;background:rgba(86,196,106,.13)">✓ собрано</div>`;
  if(stats.owned===0) return `<div class="coll-status" style="color:var(--muted);background:rgba(255,255,255,.05)">не начато</div>`;
  return `<div class="coll-status" style="color:var(--gold2);background:rgba(232,181,77,.13)">${stats.total-stats.owned} не куплено</div>`;
}
const _LOOKS_SLOT_ICON={name_glow:'✨',avatar_frame:'🖼',avatar_halo:'🌟',title:'🏷',profile_bg:'🖌',card_fx:'❄️'};
function _looksCollectionCard(lin){
  const meta=lineupMeta(lin); if(!meta) return '';
  const stats=_looksLineupStats(lin);
  const pct=stats.total?Math.round(stats.owned/stats.total*100):0;
  const c=LINEUP_COLOR[lin]||'#9aa7b8';
  const price=(meta.price&&meta.price[0]&&meta.price[0].zarniki)?`${meta.price[0].zarniki}✨/предмет`:'—';
  const slotsHtml=_LOOKS_SLOTS.map(slot=>`<span class="coll-slot${stats.slotOwned[slot]?' on':''}">${_LOOKS_SLOT_ICON[slot]}</span>`).join('');
  return `<div class="coll-card" style="--c:${c};--cb:${c}4d;--cg:${c}1f" data-lineup="${lin}" onclick="_looksOpenCollection('${lin}')">
    <div class="coll-inner"><div class="coll-frame"></div>
      <div class="coll-top">
        <div class="coll-sig" style="--c:${c}">
          <div class="coll-ring" style="background:conic-gradient(${c} calc(${pct}%),rgba(255,255,255,.08) 0)"><div class="coll-ring-mask"></div></div>
          ${_looksCollectionIconSvg(lin)}
        </div>
        <div><div class="coll-name">${esc(meta.name)}</div>${_looksCollectionStatusHtml(stats)}<div class="coll-price">${price}</div></div>
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
// Детальный экран: все 6 секций слотов, переиспользованы БЕЗ ИЗМЕНЕНИЙ из режима
// «По слотам» (Стадия 1) — уже читают _looksFilter (=lin, выставлен в
// _looksOpenCollection) и рендерят реальные карточки предметов с тем же
// инлайн-примеркой+покупкой, что и everywhere else в конструкторе. Якорь-чипы
// (.looks-anchors) намеренно не рендерим — 6 секций одной линейки короткие,
// прыгать некуда.
function _looksCollectionDetailBodyHtml(){
  return `<div id="looks-sections">${_LOOKS_SLOTS.map(s=>_looksSectionHtml(s,_looksDetailLineup)).join('')}</div>`;
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
}
function _looksCloseCollection(){
  _looksDetailLineup=null; _looksFilter='all';
  renderLooks();
}
// Алтарная шапка открытой коллекции (Стадия 3) — см. COSMETICS_COLLECTION_DESIGN_RULES.md §6:
// медальон крупнее (74px+), сегментный измеритель (N делений = N предметов
// линейки, не гладкий %), явная кнопка «Купить всё недостающее» — реальная
// транзакция, НЕ побочный эффект тапа по карточке/плитке.
function _looksCollectionDetailHeaderHtml(lin){
  const meta=lineupMeta(lin); if(!meta) return '';
  const stats=_looksLineupStats(lin);
  const c=LINEUP_COLOR[lin]||'#9aa7b8';
  const missing=stats.total-stats.owned;
  const unit=(meta.price&&meta.price[0]&&meta.price[0].zarniki)||0;
  const total=missing*unit;
  const bal=(_looksData.balances||{}).zarniki||0;
  const can=missing>0&&bal>=total;
  const notches=Array.from({length:stats.total},(_,i)=>`<div class="coll-meter-notch${i<stats.owned?' on':''}"></div>`).join('');
  const action = missing===0
    ? `<div class="coll-detail-done">✓ Коллекция собрана полностью</div>`
    : `<button class="btn btn-sm ${can?'btn-gold':'btn-ghost'} btn-full" ${can?'':'disabled'} onclick="_looksBuyLineup('${lin}')">${can?`✨ Купить всё недостающее — ${total}✨ (${missing}×${unit}✨)`:`🚫 Нужно ${total}✨ (есть ${Math.floor(bal)}✨)`}</button>`;
  return `<div class="coll-detail-head" style="--c:${c};--cb:${c}4d;--cg:${c}1f">
    <button class="coll-detail-back" onclick="_looksCloseCollection()" aria-label="Назад к коллекциям">‹</button>
    <div class="coll-detail-atmo">${_looksCollectionAtmosphereHtml(lin)}</div>
    <div class="coll-detail-sig" style="--c:${c}">${_looksCollectionIconSvg(lin)}</div>
    <div class="coll-detail-name">${esc(meta.name)}</div>
    <div class="coll-detail-blurb">${esc(meta.blurb||'')}</div>
    <div class="coll-meter">${notches}</div>
    <div class="coll-meter-caption"><span>${stats.owned} из ${stats.total} собрано</span><span>${missing>0?`${missing} не куплено · ${unit}✨/предмет`:''}</span></div>
    ${action}
  </div>`;
}
function _looksBuyLineup(lin){
  api('/cosmetics/buy-lineup',{method:'POST',body:JSON.stringify({lineup:lin})})
    .then(r=>{toast(r.message); refreshCurrBar(); return api('/cosmetics/');})
    .then(d=>{_looksData=d; _looksSaved=_looksEquipped(d); _looksSel={..._looksSaved};
      const body=el('looks-mode-body'); if(body) body.innerHTML=_looksCollectionsViewHtml();})
    .catch(e=>toast(e,false));
}
function _looksCollectionAtmosphereHtml(lin){ return ''; }   // Task 4 заменит на реальную атмосферу
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
  const price=(l.price&&l.price[0]&&l.price[0].zarniki)?`${l.price[0].zarniki}✨ за предмет`:'—';
  const vipTxt=l.vip_required?'👑 показ на профиле только с VIP':'👁 видна всем, VIP не влияет';
  return `<div class="looks-lineup-info">
    <div class="looks-lineup-blurb">${esc(l.blurb||'')}</div>
    <div class="looks-lineup-meta"><span>💰 ${price}</span><span>${vipTxt}</span></div>
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
function _looksRenderSectionGrid(slot){
  const g=el('looks-grid-'+slot); if(g) g.innerHTML=_looksGridHtml(slot);
}
// Горячий путь: перерисовывает только блок «сейчас→станет» (не всю модалку).
function _looksRenderTop(){
  const t=el('looks-top'); if(!t) return;
  t.innerHTML=_looksPreviewHtml();
}
// Мини-карточка профиля из набора слотов sel для сравнения «Сейчас → Станет».
function _looksRenderCard(sel){
  const d=_looksData;
  const glow=_looksCos(sel.name_glow), frame=_looksCos(sel.avatar_frame), title=_looksCos(sel.title);
  const halo=_looksCos(sel.avatar_halo), bg=_looksCos(sel.profile_bg), fx=_looksCos(sel.card_fx);
  const sizeCls=' looks-preview--mini';
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
  const applyable=_looksChanged(), diff=_looksHeroDiffers();
  const actions=applyable
    ?`<div class="looks-ba-act">
        <button class="btn btn-sm btn-gold" onclick="_looksApply()">✓ Применить</button>
        <button class="btn btn-sm btn-ghost" onclick="_looksReset()">Сбросить</button></div>`
    :diff
    ?`<div class="looks-ba-act"><button class="btn btn-sm btn-ghost btn-full" onclick="_looksReset()">↩ Сбросить примерку</button></div>`
    :`<div class="looks-ba-hint">👇 Жми предмет — примерка сразу здесь. Понравилось — «Применить».</div>`;
  return `<div class="looks-ba">
      <div class="looks-ba-col"><div class="looks-ba-lbl">Сейчас</div>${_looksRenderCard(_looksSaved)}</div>
      <div class="looks-ba-arrow">${diff?'➜':'='}</div>
      <div class="looks-ba-col"><div class="looks-ba-lbl ${diff?'looks-ba-lbl--new':''}">Станет</div>${_looksRenderCard(_looksHeroSel())}</div>
    </div>${_looksBuyBarHtml()}${actions}`;
}
// Инлайн-плашка покупки под превью — когда последний выбранный предмет ещё не куплен.
// Заменяет 2-ю модалку «Примерка»: примерка теперь прямо в hero, покупка — тут же.
function _looksBuyBarHtml(){
  const f=_looksFocus; if(!f) return '';
  const it=(_looksData.slots[f.slot]||[]).find(x=>x.id===f.id);
  if(!it || it.owned || !(it.price&&it.price.length)) return '';
  const opt=it.price[0], bal=_looksData.balances||{};
  const can=Object.entries(opt).every(([c,a])=>(bal[c]||0)>=a);
  const price=_looksPriceTxt(opt);   // уже с иконкой ✨ из currency_icons
  const vipWarn=(!_looksData.vip && it.rarity && it.rarity!=='common')
    ? `<div class="looks-buy-vip">⚠️ Без VIP предмет ляжет в инвентарь, но не покажется на профиле.</div>` : '';
  return `<div class="looks-buybar">
    <div class="looks-buy-t">🔒 <b>${esc(it.name)}</b> · ${esc(lineupLabel(it.lineup))}${it.desc?`<div class="looks-buy-d">${esc(it.desc)}</div>`:''}</div>
    <button class="btn btn-sm ${can?'btn-gold':'btn-ghost'} btn-full" ${can?'':'disabled'} onclick="_looksBuyFocus()">${can?'✨ Купить за '+price:'🚫 Нужно '+price}</button>
    ${vipWarn}</div>`;
}
function _looksBuyFocus(){
  const f=_looksFocus; if(!f) return;
  _looksBuyFromPreview(f.id, 0, f.slot);   // купить + надеть + перезагрузить (reuse)
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
  return `<div class="looks-card lc-lineup-accent r-${it.rarity} locked lc-buyable ${sel?'sel':''}" ${accentStyle} data-cos="${it.id}" onclick="_looksTapUnowned('${slot}','${it.id}')">
    ${sw}<div class="lc-name">🔒 ${esc(it.name)} ${vip}</div>
    <div class="lc-foot">${rar}${priceTxt}<span class="lc-prev-hint">👁</span></div></div>`;
}
function _looksBuyFromPreview(id,opt,slot){
  api('/cosmetics/buy',{method:'POST',body:JSON.stringify({cosmetic_id:id,option_index:opt})})
    .then(r=>{toast(r.message); refreshCurrBar(); _looksDirty=true;
      return api('/cosmetics/equip',{method:'POST',body:JSON.stringify({cosmetic_id:id})});})
    .then(()=>{toast('✅ Надето!'); _looksData=null; openLooksModal();})   // владение изменилось → перезагрузить кэш
    .catch(e=>toast(e,false));
}

// Что показано в слоте прямо сейчас: примеряемый (focus) перекрывает выбранное.
function _looksShownId(slot){ return (_looksFocus&&_looksFocus.slot===slot)?_looksFocus.id:(_looksSel[slot]||null); }
// Набор для hero: применимый выбор + наложенная примерка focus (в т.ч. непокупленного).
function _looksHeroSel(){ if(!_looksFocus) return _looksSel; const s={..._looksSel}; s[_looksFocus.slot]=_looksFocus.id; return s; }
// Отличается ли hero от применённого визуально (для стрелки/подписи «Станет»).
function _looksHeroDiffers(){ const hs=_looksHeroSel(); return _LOOKS_SLOTS.some(s=>(hs[s]||null)!==(_looksSaved[s]||null)); }
function _looksEquip(slot,id){ _looksSel[slot]=id; _looksFocus={slot,id}; _looksRenderTop(); _looksMarkSel(slot); }
function _looksUnequip(slot){ _looksSel[slot]=null; _looksFocus=null; _looksRenderTop(); _looksMarkSel(slot); }
function _looksReset(){ _looksSel={..._looksSaved}; _looksFocus=null; _looksRenderTop(); _LOOKS_SLOTS.forEach(_looksMarkSel); }
// Непокупленный: только примерка (focus), в _looksSel НЕ кладём → «Применить» его не тронет
// (нельзя надеть то, чем не владеешь); для покупки — инлайн-плашка под hero.
function _looksTapUnowned(slot,id){ _looksFocus={slot,id}; _looksRenderTop(); _looksMarkSel(slot); }
// Перф: точечно переставить .sel в сетке ЭТОГО слота (без пересборки innerHTML —
// это и был источник «подлагивания»: раньше каждый тап перерисовывал весь грид).
function _looksMarkSel(slot){
  const grid=el('looks-grid-'+slot); if(!grid){ _looksRenderSectionGrid(slot); return; }
  const cards=grid.querySelectorAll('.looks-card[data-cos]');
  if(!cards.length){ _looksRenderSectionGrid(slot); return; }
  const shown=_looksShownId(slot);
  cards.forEach(c=>{
    const cid=c.getAttribute('data-cos');
    c.classList.toggle('sel', cid===String(shown) || (cid==='__none__' && shown==null));
  });
}

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
    .then(r=>{toast(r.message); _looksDirty=true; _looksData=null; openLooksModal();})
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
    const cls=['looks-card','lc-wide','r-'+o.rarity]; if(o.current)cls.push('sel'); if(o.locked)cls.push('locked');
    const vip=o.vip_required?' <span class="lc-vip">VIP</span>':'';
    return `<div class="${cls.join(' ')}" onclick="_welcomePick('${o.id}')">
      <div class="lc-name">${o.locked?'🔒 ':''}${esc(o.name)}${vip}</div>
      <div class="lc-tag">${o.current?'✓ выбрано':esc(o.desc)}</div></div>`;
  }).join('');
  const hint=_looksData.vip?'':'<div class="looks-hint">👆 Жми на любой режим — увидишь превью. Выбрать приветствие можно с VIP.</div>';
  return `<section class="looks-section" id="looks-sec-welcome">
    <div class="looks-sec-t">${_LOOKS_ANCHOR_LABEL.welcome}</div>
    <div id="wpreview" class="wpreview"></div>${hint}
    <div class="looks-cards">${cards}</div>
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
  if(_themeData){ _looksRenderThemesGrid(); return; }
  api('/themes/').then(themes=>{ _themeData=themes; _looksRenderThemesGrid(); })
    .catch(e=>{ const g=el('looks-grid-themes'); if(g) g.innerHTML=`<div class="err">${e}</div>`; });
}
function _looksThemesSectionHtml(){
  return `<section class="looks-section" id="looks-sec-themes">
    <div class="looks-sec-t">${_LOOKS_ANCHOR_LABEL.themes}</div>
    <div id="looks-theme-preview" class="looks-theme-preview"></div>
    <div class="looks-theme-filter" id="looks-theme-filter">
      <button class="looks-theme-chip active" data-f="all" onclick="_looksThemeSetFilter('all')">Все</button>
      <button class="looks-theme-chip" data-f="owned" onclick="_looksThemeSetFilter('owned')">Мои</button>
      <button class="looks-theme-chip" data-f="premium" onclick="_looksThemeSetFilter('premium')">✨ Премиум</button>
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
  g.innerHTML=`<div class="looks-cards">${filtered.map(_looksThemeCard).join('')}</div>`;
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
  return `<div class="looks-card${t.active?' sel':''}${sel&&!t.active?' sel':''}" data-theme="${t.theme_id}" onclick="_looksThemeTap('${t.theme_id}')">
    <div class="lc-sw"><span class="lc-ava">${esc(accent)}</span></div>
    <div class="lc-name">${esc(t.name)}</div>
    <div class="lc-foot">${themeStatusBadge(t)}</div>
  </div>`;
}
function _looksThemeTap(tid){
  if(!_themeData) return;
  const t=_themeData.find(x=>x.theme_id===tid); if(!t) return;
  _looksThemeSel=tid;
  document.querySelectorAll('#looks-grid-themes .looks-card').forEach(c=>
    c.classList.toggle('sel', c.getAttribute('data-theme')===tid));
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
    box.innerHTML=`<div class="profile-preview" style="min-height:40px">${r.text||''}</div>
      <div class="looks-theme-name">${esc(t.name)} · ${_rarLabel(t.rarity)}</div>
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
  OM('🎁 Сюрпризы и Крафт','<div class="loader">Загрузка...</div>',[{l:'← К внешнему виду',c:'btn-ghost',f:'CM();_looksData=null;openLooksModal()'}]);
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
