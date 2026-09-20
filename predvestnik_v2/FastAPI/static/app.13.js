// Mobile-first cosmetic storefront. The former release wardrobe remains the
// private owner projection; this layer adds the server-authoritative shop,
// collection bundles and whole-app backgrounds without trusting client prices.
(function(){
  'use strict';
  const SLOT_LABELS={name_glow:'Сияние имени',avatar_frame:'Рамка',avatar_halo:'Ореол',title:'Титул',profile_bg:'Фон профиля',card_fx:'Эффект карточки',site_bg:'Фон приложения'};
  const SLOT_ICONS={name_glow:'✨',avatar_frame:'▣',avatar_halo:'◉',title:'◆',profile_bg:'▤',card_fx:'✦',site_bg:'▥'};
  const LINEUP_COLORS={forest:'#7dc47d',threshold:'#b793e9',frost:'#7ad4ff',inferno:'#e98b58',hanami:'#e8a3b6',celestial:'#e8c45a',void:'#9aa8e6',artifact:'#55cfd0',moon_lotus:'#b9c9ff',ryujin_tide:'#69b8d6'};
  const PREVIEW_PICKS={void:{name_glow:'cos_name_glow_void',avatar_frame:'cos_avatar_frame_void',avatar_halo:'cos_avatar_halo_void',title:'cos_title_harbinger',profile_bg:'cos_profile_bg_starfall',card_fx:'cos_card_fx_void_storm'}};
  const e=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  let catalog=null, skins=null, mode='collections', detail='', slotFilter='all', search='', selected=null, busy=false, searchTimer=null, collectionScroll=0;
  let topup=null, topupBusy=false, returnOffer='', focusPreview=false, focusTopup=false;
  const baseNavBack=globalThis.navBack;

  function allCosmetics(){ return catalog?Object.values(catalog.slots||{}).flat():[]; }
  function shopSkins(){ return (skins?.items||[]).filter(item=>item.price_zarniki); }
  function catalogSkins(){ return (skins?.items||[]).filter(item=>item.price_zarniki||((item.owned||item.selected)&&item.id!=='default')); }
  function allOffers(){
    return [
      ...allCosmetics().map(item=>({...item,kind:'cosmetic',price_zarniki:Number(item.price?.[0]?.zarniki)||0})),
      ...shopSkins().map(item=>({...item,kind:'skin',slot:'site_bg'})),
    ];
  }
  function catalogOffers(){
    return [
      ...allCosmetics().map(item=>({...item,kind:'cosmetic',price_zarniki:Number(item.price?.[0]?.zarniki)||0})),
      ...catalogSkins().map(item=>({...item,kind:'skin',slot:'site_bg'})),
    ];
  }
  function color(id){ return LINEUP_COLORS[id]||'#9aa7b8'; }
  function lineupMeta(id){ return catalog?.lineups?.[id]||{}; }
  function lineupName(id){ return lineupMeta(id).name||id||'Без коллекции'; }
  function requestKey(scope){
    const value=globalThis.crypto?.randomUUID?.()||`${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    return `${scope}-${value}`;
  }
  function owned(item){ return item.kind==='skin'?Boolean(item.owned):Boolean(item.owned); }
  function equipped(item){ return item.kind==='skin'?Boolean(item.selected):Boolean(item.equipped); }
  function offersFor(lineup){ return allOffers().filter(item=>item.lineup===lineup); }
  function missingFor(lineup){ return offersFor(lineup).filter(item=>!owned(item)&&item.price_zarniki>0); }
  function collectionTotals(lineup){
    const offers=offersFor(lineup), mine=offers.filter(owned).length, missing=offers.filter(item=>!owned(item));
    return {offers,mine,total:offers.length,missing,price:missing.reduce((sum,item)=>sum+item.price_zarniki,0)};
  }
  function currentBalance(){ return Math.floor(Number(catalog?.balances?.zarniki)||0); }
  function skinAsset(item){ return item?.asset?`${BASE}/${String(item.asset).replace(/^\//,'')}`:''; }
  function itemWord(value){
    const n=Math.abs(Number(value)||0)%100, tail=n%10;
    if(n>10&&n<20)return 'предметов';
    if(tail===1)return 'предмет';
    if(tail>=2&&tail<=4)return 'предмета';
    return 'предметов';
  }

  function projectedItem(item){
    if(!item)return null;
    return item.slot==='title'
      ?{id:item.id,text:item.text||item.name,css:item.css,name:item.name,lineup:item.lineup}
      :{id:item.id,css:item.css,name:item.name,lineup:item.lineup};
  }
  function cosmeticLook(lineup){
    const look={};
    for(const slot of ['name_glow','avatar_frame','avatar_halo','title','profile_bg','card_fx']){
      const items=(catalog?.slots?.[slot]||[]).filter(x=>x.lineup===lineup);
      const item=items.find(x=>x.id===PREVIEW_PICKS[lineup]?.[slot])||items[0];
      if(!item) continue;
      look[slot]=projectedItem(item);
    }
    look.composition={dominant_lineup:lineup,layer_count:Object.keys(look).length};
    look.lineage={id:lineup,source_slot:'avatar_frame'};
    return look;
  }
  function selectedLook(){
    if(!selected)return null;
    // Preview one offer over the player's authoritative current look.  The old
    // implementation filled every slot from the offer's collection, so trying
    // one background also showed a fictional title, frame, halo and card FX
    // that the one-slot Equip operation never saved.
    const current=_profileData?.cosmetics||{};
    const look={...current};
    if(selected.kind==='cosmetic'){
      look[selected.slot]=projectedItem(selected);
      look.composition={...(current.composition||{}),dominant_lineup:selected.lineup};
      look.lineage={id:selected.lineup,source_slot:selected.slot};
    }
    return look;
  }
  function previewHtml(lineup,caption){
    if(typeof renderProfileShowcase!=='function') return '';
    return renderProfileShowcase(_profileData||{},cosmeticLook(lineup),{caption:caption||'Предпросмотр коллекции',compact:true});
  }
  function swatch(item){
    if(item.kind==='skin'){
      const asset=skinAsset(item);
      return `<span class="store-swatch store-swatch--site" style="background-image:linear-gradient(rgba(5,8,18,.18),rgba(5,8,18,.60)),url('${e(asset)}')"><b>Всё приложение</b></span>`;
    }
    const css=typeof _profileCss==='function'?_profileCss(item.css):String(item.css||'');
    const face=_profileData?.is_vip?'👑':'🔮';
    return ({
      name_glow:`<span class="store-swatch"><b class="pname ${css}">@Ник</b></span>`,
      title:`<span class="store-swatch"><b class="ptitle ${css}">${e(item.text||item.name)}</b></span>`,
      avatar_frame:`<span class="store-swatch"><i class="ava ${css}">${face}</i></span>`,
      avatar_halo:`<span class="store-swatch"><i class="ava ${css}">${face}</i></span>`,
      profile_bg:`<span class="store-swatch ${css}"><b>Профиль</b></span>`,
      card_fx:`<span class="store-swatch"><b>Карточка</b><i class="card-fx ${css}" aria-hidden="true"></i></span>`,
    })[item.slot]||'<span class="store-swatch"></span>';
  }
  function offerCard(item){
    const isOwned=owned(item), isEquipped=equipped(item), c=color(item.lineup);
    const action=isEquipped?'Выбрано':isOwned?'Надеть':`${item.price_zarniki}✨`;
    return `<button class="store-item${selected?.id===item.id?' is-selected':''}${isEquipped?' is-equipped':''}" type="button" data-offer="${e(item.kind)}:${e(item.id)}" style="--store-accent:${c}" aria-label="${e(item.name)}. ${isOwned?action:`Купить за ${item.price_zarniki} зарников`}">
      ${swatch(item)}<span class="store-item-copy"><b>${e(item.name)}</b><small>${e(SLOT_LABELS[item.slot]||item.slot)}</small></span><span class="store-item-action">${isEquipped?'✓ ':''}${e(action)}</span>
    </button>`;
  }
  function collectionCard(id){
    const meta=lineupMeta(id), totals=collectionTotals(id), c=color(id), pct=totals.total?Math.round(totals.mine/totals.total*100):0;
    const skin=totals.offers.find(item=>item.kind==='skin'), asset=skinAsset(skin);
    return `<button class="store-collection" type="button" data-collection="${e(id)}" style="--store-accent:${c};${asset?`--store-art:url('${e(asset)}')`:''}">
      <span class="store-collection-art">${asset?'':`<b>${e(String(meta.name||id).slice(0,2))}</b>`}</span>
      <span class="store-collection-copy"><strong>${e(meta.name||id)}</strong><small>${totals.mine}/${totals.total} · ${pct}% собрано</small><span>${totals.price?`от ${Math.min(...totals.missing.map(x=>x.price_zarniki))}✨`:'Коллекция собрана'}</span></span>
    </button>`;
  }
  function balanceHtml(){ return `<span class="store-balance" aria-label="Баланс зарников"><i>✨</i><b>${currentBalance()}</b></span>`; }
  function tabsHtml(){
    return `<div class="store-tabs" role="tablist" aria-label="Навигация по косметике">
      ${[['collections','Коллекции'],['catalog','Каталог'],['mine','Мои']].map(([id,label])=>`<button type="button" role="tab" aria-selected="${mode===id}" aria-controls="store-panel" tabindex="${mode===id?'0':'-1'}" data-store-mode="${id}">${label}</button>`).join('')}
    </div>`;
  }
  function collectionsHtml(){
    const ids=Object.keys(catalog?.lineups||{}), featured=collectionTotals('void'), skin=featured.offers.find(x=>x.kind==='skin'), asset=skinAsset(skin);
    const partial=ids.filter(id=>{const t=collectionTotals(id);return t.mine>0&&t.mine<t.total;});
    return `<section class="store-feature" style="--store-art:url('${e(asset)}')">
      <span class="store-feature-kicker">Новинка · коллекция «Бездна»</span><h2>Атлас Бездны</h2><p>Космическая карта меняет фон всего приложения и мягко продолжает линии карточки игрока.</p>
      <button type="button" class="store-primary" data-collection="void">Смотреть коллекцию <span>›</span></button>
    </section>
    ${partial.length?`<section class="store-continue"><div class="store-section-title"><b>Продолжить коллекцию</b><small>Ближе всего к завершению</small></div><div class="store-continue-row">${partial.sort((a,b)=>collectionTotals(a).missing.length-collectionTotals(b).missing.length||collectionTotals(a).price-collectionTotals(b).price).slice(0,3).map(collectionCard).join('')}</div></section>`:''}
    <section><div class="store-section-title"><b>Все коллекции</b><small>${ids.length} миров · ${allOffers().length} предметов</small></div><div class="store-collection-grid">${ids.map(collectionCard).join('')}</div></section>`;
  }
  function detailHtml(){
    const totals=collectionTotals(detail), meta=lineupMeta(detail), c=color(detail), skin=totals.offers.find(x=>x.kind==='skin'), asset=skinAsset(skin), canBuy=totals.price>0&&currentBalance()>=totals.price;
    const slotOrder=['site_bg','avatar_frame','avatar_halo','name_glow','title','profile_bg','card_fx'];
    const groups=slotOrder.map(slot=>{
      const items=totals.offers.filter(x=>x.slot===slot); if(!items.length)return '';
      return `<section class="store-offer-group"><div class="store-section-title"><b>${e(SLOT_ICONS[slot]||'')}&nbsp; ${e(SLOT_LABELS[slot]||slot)}</b><small>${items.filter(owned).length}/${items.length}</small></div><div class="store-item-grid">${items.map(offerCard).join('')}</div></section>`;
    }).join('');
    return `<button class="store-inline-back" type="button" data-store-back>‹ Все коллекции</button>
      <section class="store-detail-hero store-detail-hero--${e(detail)}" style="--store-accent:${c};${asset?`--store-art:url('${e(asset)}')`:''}">
        <div class="store-detail-copy"><span>Коллекция</span><h2>${e(meta.name||detail)}</h2><p>${e(meta.blurb||'')}</p><div><b>${totals.mine}/${totals.total}</b><small>уже принадлежит</small></div></div>
        <div class="store-detail-preview">${previewHtml(detail,'Коллекция целиком')}</div>
        ${totals.price?`<button class="store-bundle" type="button" data-buy-lineup="${e(detail)}" ${busy||!canBuy?'disabled':''}><span><b>Купить всё недостающее</b><small>${totals.missing.length} ${itemWord(totals.missing.length)} одной покупкой</small></span><strong>${totals.price}✨</strong></button>${!canBuy?`<div class="store-balance-note">Не хватает ${Math.max(0,totals.price-currentBalance())}✨ <button type="button" data-store-topup>Пополнить Зарники</button></div>`:''}`:'<div class="store-complete">✓ Коллекция полностью собрана</div>'}
      </section>${groups}`;
  }
  function catalogHtml(onlyMine=false){
    let items=catalogOffers().filter(item=>(!onlyMine||owned(item))&&(slotFilter==='all'||item.slot===slotFilter));
    if(search) items=items.filter(item=>String(item.name||'').toLowerCase().includes(search));
    const slots=['all','site_bg','avatar_frame','avatar_halo','name_glow','title','profile_bg','card_fx'];
    return `<section class="store-tools"><label><span class="sr-only">Поиск косметики</span><input type="search" data-store-search value="${e(search)}" placeholder="Найти предмет">${search?'<button type="button" data-store-search-clear aria-label="Очистить поиск">×</button>':''}</label><div class="store-chip-row" role="group" aria-label="Тип предмета">${slots.map(slot=>`<button type="button" data-slot="${slot}" class="${slot===slotFilter?'is-active':''}">${slot==='all'?'Все':`${SLOT_ICONS[slot]} ${SLOT_LABELS[slot]}`}</button>`).join('')}</div></section>
      <div class="store-results"><span>${items.length} ${itemWord(items.length)}</span><small>${onlyMine?'Только купленные':'Можно примерить перед покупкой'}</small></div>
      <div class="store-item-grid store-item-grid--catalog">${items.map(offerCard).join('')||'<p class="empty">По этому фильтру ничего нет.</p>'}</div>`;
  }
  function actionDockHtml(){
    if(!selected) return '';
    const isOwned=owned(selected), isEquipped=equipped(selected), enough=currentBalance()>=selected.price_zarniki;
    const label=isEquipped?'Уже выбрано':isOwned?'Надеть':enough?`Купить · ${selected.price_zarniki}✨`:`Не хватает ${selected.price_zarniki-currentBalance()}✨`;
    const preview=typeof renderProfileShowcase==='function'
      ?renderProfileShowcase(_profileData||{},selectedLook(),{caption:`Примерка: ${selected.name}`,compact:true})
      :'';
    return `<div class="store-preview-backdrop" data-store-preview-backdrop><aside class="store-preview-sheet" role="dialog" aria-modal="true" aria-labelledby="store-preview-title">
      <header><span><small>${e(SLOT_LABELS[selected.slot]||'Предмет')}</small><b id="store-preview-title">${e(selected.name)}</b></span><button type="button" data-store-preview-close aria-label="Закрыть примерку">×</button></header>
      <div class="store-preview-card">${preview}</div>
      <footer><small>${selected.kind==='skin'?'Фон временно включён на всём экране. Закрытие вернёт ваш текущий фон.':'Показан именно этот предмет поверх вашего текущего образа.'}</small>${!isOwned&&!enough?'<button type="button" data-store-topup>Пополнить</button>':`<button type="button" data-store-primary-action ${busy||isEquipped?'disabled':''}>${e(label)}</button>`}</footer>
    </aside></div>`;
  }
  function topupHtml(){
    if(!topup)return '';
    const packages=Array.isArray(topup.packages)?topup.packages:[];
    const content=topup.loading?'<div class="loader">Загружаем безопасные пакеты…</div>':topup.error?`<p class="err">${e(topup.error)}</p>`:topup.purchase_enabled===false?'<p class="store-topup-unavailable">Пополнение временно закрыто до завершения безопасного учёта платежей.</p>':`<div class="store-topup-packages">${packages.map(p=>`<button type="button" data-zarniki-stars="${Number(p.stars)}" ${topupBusy?'disabled':''}><span><b>${Number(p.total)}✨</b>${p.popular?'<small>Популярный</small>':''}</span><strong>${Number(p.stars)}⭐</strong></button>`).join('')}</div><p>Оплата откроется в защищённом окне Telegram. Покупку подтверждаете только вы.</p>`;
    return `<div class="store-topup-backdrop"><section class="store-topup" role="dialog" aria-modal="true" aria-labelledby="store-topup-title"><header><div><small>Баланс ${currentBalance()}✨</small><h2 id="store-topup-title">Пополнить Зарники</h2></div><button type="button" data-store-topup-close aria-label="Закрыть пополнение">×</button></header>${content}</section></div>`;
  }
  function syncSkinPreview(){
    if(typeof window.applyGlobalSkinV1!=='function')return;
    const preview=selected?.kind==='skin'&&/^skin-[a-z0-9-]{1,80}$/.test(selected.css_class||'')
      ?{items:[{active:true,css_class:selected.css_class}]}
      :skins;
    window.applyGlobalSkinV1(preview);
  }
  function closeSelection(){ const target=returnOffer; selected=null; render(); requestAnimationFrame(()=>target&&el('pg-looks')?.querySelector(`[data-offer="${target}"]`)?.focus()); }
  function closeTopup(){ topup=null; render(); requestAnimationFrame(()=>el('pg-looks')?.querySelector(selected?'.store-preview-sheet [data-store-topup]':'[data-store-topup]')?.focus()); }
  function closeDetail(){
    detail=''; selected=null; render();
    requestAnimationFrame(()=>scrollTo({top:collectionScroll,behavior:'auto'}));
  }
  function headBack(){
    if(topup)return closeTopup();
    if(selected)return closeSelection();
    if(detail)return closeDetail();
    if(_navStack.length&&typeof baseNavBack==='function')return baseNavBack();
    goTo('profile');
  }
  function render(){
    const root=el('pg-looks'); if(!root||!catalog||!skins)return;
    const body=detail?detailHtml():mode==='collections'?collectionsHtml():catalogHtml(mode==='mine');
    root.innerHTML=`<header class="store-head"><button type="button" class="looks-back" data-store-head-back aria-label="${detail?'Назад к коллекциям':'Назад'}">‹</button><div><span>Магазин косметики</span><h1>Образы</h1></div>${balanceHtml()}</header>${detail?'':tabsHtml()}<main class="looks-store" id="store-panel">${body}</main>${topup?'':actionDockHtml()}${topupHtml()}`;
    bind(); syncSkinPreview();
    if(focusTopup){focusTopup=false;requestAnimationFrame(()=>root.querySelector('[data-store-topup-close]')?.focus());}
    else if(focusPreview){focusPreview=false;requestAnimationFrame(()=>root.querySelector('[data-store-preview-close]')?.focus());}
  }
  function bind(){
    const root=el('pg-looks'); if(!root)return;
    root.querySelectorAll('[data-store-mode]').forEach(btn=>{
      btn.addEventListener('click',()=>{mode=btn.dataset.storeMode;detail='';selected=null;render();});
      btn.addEventListener('keydown',event=>{
        const ids=['collections','catalog','mine'],current=ids.indexOf(btn.dataset.storeMode);
        const next=event.key==='ArrowRight'?current+1:event.key==='ArrowLeft'?current-1:event.key==='Home'?0:event.key==='End'?ids.length-1:null;
        if(next===null)return;
        event.preventDefault(); mode=ids[(next+ids.length)%ids.length]; detail=''; selected=null; render();
        root.querySelector('[data-store-mode][aria-selected="true"]')?.focus();
      });
    });
    root.querySelector('[data-store-head-back]')?.addEventListener('click',headBack);
    root.querySelectorAll('[data-collection]').forEach(btn=>btn.addEventListener('click',()=>{collectionScroll=scrollY;detail=btn.dataset.collection;selected=null;render();scrollTo({top:0,behavior:'smooth'});}));
    root.querySelector('[data-store-back]')?.addEventListener('click',closeDetail);
    root.querySelectorAll('[data-offer]').forEach(btn=>btn.addEventListener('click',()=>{const [kind,id]=btn.dataset.offer.split(':');returnOffer=btn.dataset.offer;selected=catalogOffers().find(x=>x.kind===kind&&x.id===id)||null;focusPreview=Boolean(selected);render();}));
    root.querySelectorAll('[data-slot]').forEach(btn=>btn.addEventListener('click',()=>{slotFilter=btn.dataset.slot;render();}));
    root.querySelector('[data-store-search]')?.addEventListener('input',event=>{
      search=String(event.target.value||'').trim().toLowerCase();
      clearTimeout(searchTimer);
      searchTimer=setTimeout(()=>{
        render();
        const next=root.querySelector('[data-store-search]');
        next?.focus();
        next?.setSelectionRange(search.length,search.length);
      },140);
    });
    root.querySelector('[data-store-search-clear]')?.addEventListener('click',()=>{
      clearTimeout(searchTimer); search=''; render(); root.querySelector('[data-store-search]')?.focus();
    });
    root.querySelector('[data-store-preview-close]')?.addEventListener('click',closeSelection);
    root.querySelector('[data-store-preview-backdrop]')?.addEventListener('click',event=>{if(event.target===event.currentTarget)closeSelection();});
    root.querySelectorAll('[data-store-topup]').forEach(btn=>btn.addEventListener('click',openTopup));
    root.querySelector('[data-store-topup-close]')?.addEventListener('click',closeTopup);
    root.querySelectorAll('[data-zarniki-stars]').forEach(btn=>btn.addEventListener('click',()=>purchaseZarniki(Number(btn.dataset.zarnikiStars))));
    root.onkeydown=event=>{
      if(event.key==='Escape'){
        if(topup){event.preventDefault();closeTopup();}
        else if(selected){event.preventDefault();closeSelection();}
        return;
      }
      if(event.key!=='Tab'||(!topup&&!selected))return;
      const dialog=root.querySelector('[role="dialog"]');
      const focusable=[...(dialog?.querySelectorAll('button:not([disabled]),input:not([disabled]),[href],[tabindex]:not([tabindex="-1"])')||[])];
      if(!focusable.length)return;
      const first=focusable[0],last=focusable[focusable.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    };
    root.querySelector('[data-store-primary-action]')?.addEventListener('click',primaryAction);
    root.querySelector('[data-buy-lineup]')?.addEventListener('click',event=>buyLineup(event.currentTarget.dataset.buyLineup));
  }
  async function openTopup(){
    topup={loading:true};focusTopup=true;render();
    try{topup=await api('/payments/zarniki/packages');focusTopup=true;render();}
    catch(error){topup={error:String(error)};focusTopup=true;render();}
  }
  async function purchaseZarniki(stars){
    if(topupBusy||!Number.isInteger(stars)||stars<1)return;
    topupBusy=true;render();
    try{
      const invoice=await api('/payments/zarniki/invoice',{method:'POST',body:JSON.stringify({stars})});
      if(!invoice?.link)throw new Error('Счёт не создан.');
      if(typeof tg?.openInvoice==='function')tg.openInvoice(invoice.link,async status=>{if(status==='paid'){await reload();topup=null;selected=null;render();}});
      else location.assign(invoice.link);
    }catch(error){toast(error,false);}
    finally{topupBusy=false;render();}
  }
  async function reload(){
    const [nextCatalog,nextSkins]=await Promise.all([api('/cosmetics/'),api('/global-skins-v1/me'),loadProfile()]);
    catalog=nextCatalog; skins=nextSkins;
    if(_profileData)_profileData.global_skin=nextSkins;
    _applyGlobalSkin?.(nextSkins);
  }
  async function mutate(work){
    if(busy)return; busy=true;render();
    try{const result=await work();toast(result?.message||'Готово');await reload();selected=null;render();refreshCurrBar?.();}
    catch(error){toast(error,false);}
    finally{busy=false;render();}
  }
  function primaryAction(){
    if(!selected)return;
    if(owned(selected)){
      return mutate(()=>selected.kind==='skin'
        ?api('/global-skins-v1/select',{method:'POST',body:JSON.stringify({skin_id:selected.id})})
        :api('/appearance/equip',{method:'POST',body:JSON.stringify({cosmetic_id:selected.id})}));
    }
    const key=requestKey(selected.kind==='skin'?'skin':'cosmetic');
    return mutate(()=>selected.kind==='skin'
      ?api('/global-skins-v1/buy',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({skin_id:selected.id})})
      :api('/cosmetics/buy',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({cosmetic_id:selected.id,option_index:0})}));
  }
  function buyLineup(lineup){
    const key=requestKey('collection');
    return mutate(()=>api('/cosmetics/buy-lineup',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({lineup})}));
  }
  window.openLooksModal=async function(){
    switchPage('looks');
    detail=''; selected=null; syncSkinPreview();
    const root=el('pg-looks');if(root)root.innerHTML='<div class="loader" style="margin-top:44px">Открываем витрину…</div>';
    try{await reload();render();}
    catch(error){if(root)root.innerHTML=`<div class="err" style="margin:16px">${e(error)}</div>`;}
  };
  globalThis.navBack=function(){
    if(_activePage==='looks'&&topup){closeTopup();return;}
    if(_activePage==='looks'&&selected){closeSelection();return;}
    if(_activePage==='looks'&&detail){closeDetail();return;}
    if(typeof baseNavBack==='function')return baseNavBack();
  };
  window._looksGuardPageLeave=function(){ selected=null;topup=null;syncSkinPreview(); return false; };
})();
