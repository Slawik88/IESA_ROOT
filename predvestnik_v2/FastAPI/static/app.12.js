// Release wardrobe.  It intentionally replaces the retired /cosmetics/* UI:
// cosmetics are selected from durable ownership, while the shared shop comes later.
(function(){
  const SLOT_LABELS={name_glow:'Сияние имени',avatar_frame:'Рамка',title:'Титул',avatar_halo:'Ореол',profile_bg:'Фон профиля',card_fx:'Эффект карточки'};
  const LINEUP_LABELS={forest:'🌲 Лесной Странник',threshold:'🔮 Порог',frost:'❄️ Изморозь',inferno:'🔥 Инферно',hanami:'🌸 Ханами',celestial:'✨ Небесное Сияние',void:'🌌 Бездна',artifact:'⚡ Артефакт',moon_lotus:'🪷 Лунный Лотос',ryujin_tide:'🐉 Прилив Рюдзина'};
  const LINEUP_COLORS={forest:'#7dc47d',threshold:'#c084fc',frost:'#7ad4ff',inferno:'#ff7a3d',celestial:'#e8c45a',void:'#ff4d8d',artifact:'#3fe0e0',hanami:'#e8a3b6',moon_lotus:'#b9c9ff',ryujin_tide:'#69b8d6'};
  const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  let wardrobe=null, wardrobeBusy=false, wardrobePreviewMode='public', wardrobeOpenSlot='name_glow';

  function previewCosmetics(){
    const saved=wardrobe?.saved_look;
    if(saved?.cosmetics) return {...saved.cosmetics,composition:saved.composition||{}};
    return _profileData?.cosmetics||{};
  }
  function profilePreview(){
    const d=_profileData||{}, saved=previewCosmetics(), publicLook=d.cosmetics||{};
    const card=(look,caption)=>typeof renderProfileShowcase==='function'
      ?renderProfileShowcase(d,look,{caption,compact:true})
      :'<p class="empty">Предпросмотр временно недоступен.</p>';
    if(wardrobe?.vip_active) return card(publicLook,'Образ, видимый другим');
    const savedMode=wardrobePreviewMode==='saved';
    return `<div class="looks-preview-switch" role="group" aria-label="Режим предпросмотра">
      <button type="button" class="${savedMode?'':'is-active'}" aria-pressed="${savedMode?'false':'true'}" onclick="setWardrobePreview('public')">Видно другим</button>
      <button type="button" class="${savedMode?'is-active':''}" aria-pressed="${savedMode?'true':'false'}" onclick="setWardrobePreview('saved')">Сохранённый образ</button>
    </div>${card(savedMode?saved:publicLook,savedMode?'Сохранённый образ — вернётся с VIP':'Образ, видимый другим')}`;
  }
  function itemHtml(item){
    const chosen=item.equipped?' is-equipped':'';
    if(!item.owned) return '';
    const lineup=LINEUP_LABELS[item.lineup]||item.lineup||'Без коллекции';
    const color=LINEUP_COLORS[item.lineup]||'#9aa7b8';
    const css=typeof _profileCss==='function'?_profileCss(item.css):String(item.css||'');
    const face=_profileData?.is_vip?'👑':'🔮';
    const swatch={
      name_glow:`<div class="lc-sw"><span class="lc-nick ${css}">@Ник</span></div>`,
      title:`<div class="lc-sw"><span class="lc-title ${css}">${esc(item.text||item.name)}</span></div>`,
      avatar_frame:`<div class="lc-sw"><span class="lc-ava ${css}">${face}</span></div>`,
      avatar_halo:`<div class="lc-sw"><span class="lc-ava ${css}">${face}</span></div>`,
      profile_bg:`<div class="lc-sw lc-bg ${css}"><span class="looks-swatch-label">Профиль</span></div>`,
      card_fx:`<div class="lc-sw"><span class="looks-swatch-label">Профиль</span><span class="card-fx ${css}" aria-hidden="true"></span></div>`,
    }[item.slot]||'<div class="lc-sw"></div>';
    return `<button type="button" class="looks-card lc-lineup-accent${chosen}" style="--lc:${color};--lcg:${color}22" data-cos="${esc(item.id)}" data-cosmetic-id="${esc(item.id)}" data-cosmetic-name="${esc(String(item.name||'').toLowerCase())}" data-lineup="${esc(item.lineup||'')}" aria-label="${esc(item.name)}. ${esc(lineup)}. ${item.equipped?'Выбрано':'Выбрать'}" aria-pressed="${item.equipped?'true':'false'}" ${item.equipped||wardrobeBusy?'disabled':''}>
      ${swatch}<strong class="lc-name">${esc(item.name)}</strong><span class="lc-foot"><small class="lc-rar" style="color:${color}">${esc(lineup)}</small>${item.equipped?'<em class="lc-on">✓ Выбрано</em>':'<span class="looks-pick">Выбрать</span>'}</span>
    </button>`;
  }
  function slotHtml(slot,items){
    const list=items.filter(x=>x.owned);
    if(!list.length) return '';
    const equipped=list.find(x=>x.equipped);
    const open=slot===wardrobeOpenSlot?' open':'';
    return `<details class="looks-release-slot" data-wardrobe-slot="${esc(slot)}"${open}>
      <summary><span><b>${esc(SLOT_LABELS[slot]||slot)}</b><small>${equipped?`Выбрано: ${esc(equipped.name)}`:'Ничего не выбрано'}</small></span><em>${list.length}</em></summary>
      <div class="looks-slot-body"><div class="looks-grid looks-cards">${list.map(itemHtml).join('')}</div><button class="looks-remove" type="button" data-cosmetic-slot="${esc(slot)}" ${equipped&& !wardrobeBusy?'':'disabled'}>Снять ${esc((SLOT_LABELS[slot]||'предмет').toLowerCase())}</button></div>
    </details>`;
  }
  function applyWardrobeFilters(){
    const root=el('pg-looks'); if(!root) return;
    const query=String(root.querySelector('[data-wardrobe-search]')?.value||'').trim().toLowerCase();
    const lineup=root.querySelector('[data-wardrobe-lineup]')?.value||'';
    root.querySelectorAll('[data-wardrobe-slot]').forEach(section=>{
      let visible=0;
      section.querySelectorAll('[data-cosmetic-id]').forEach(button=>{
        const match=(!query||button.dataset.cosmeticName.includes(query))&&(!lineup||button.dataset.lineup===lineup);
        button.hidden=!match; if(match) visible+=1;
      });
      section.hidden=visible===0;
      if((query||lineup)&&visible) section.open=true;
    });
    const count=[...root.querySelectorAll('[data-cosmetic-id]')].filter(button=>!button.hidden).length;
    const countNode=root.querySelector('[data-wardrobe-count]');
    if(countNode) countNode.textContent=(query||lineup)?`Найдено: ${count}`:`${count} предмета · 6 разделов`;
    const empty=root.querySelector('[data-wardrobe-empty]'); if(empty) empty.hidden=count>0;
  }
  function setWardrobeBusyState(busy){
    const root=el('pg-looks'); if(!root) return;
    root.setAttribute('aria-busy',busy?'true':'false');
    root.querySelectorAll('[data-cosmetic-id],[data-cosmetic-slot]').forEach(button=>{button.disabled=busy||button.getAttribute('aria-pressed')==='true'||(button.hasAttribute('data-cosmetic-slot')&&!button.closest('details')?.querySelector('[aria-pressed="true"]'));});
    const status=root.querySelector('[data-wardrobe-status]'); if(status) status.textContent=busy?'Сохраняем образ…':'';
  }
  function render(){
    const root=el('pg-looks'); if(!root||!wardrobe) return;
    const owned=Object.values(wardrobe.slots||{}).flat().filter(x=>x.owned);
    root.innerHTML=`<div class="looks-head"><button class="looks-back" onclick="goTo('profile')" aria-label="Назад">‹</button><div class="looks-htitle">🎨 Примерочная</div></div>
      <section class="looks-release-preview"><div class="looks-eyebrow">Предпросмотр косметики</div>${profilePreview()}</section>
      <div class="looks-hint">${wardrobe.vip_active?'VIP активна — образ виден в профиле и карточках.':'VIP не активна — образ сохранён и виден только здесь. После продления он вернётся автоматически.'}</div>
      <section class="looks-release-section looks-wardrobe" aria-labelledby="wardrobe-title"><div class="looks-wardrobe-head"><div><h3 id="wardrobe-title">Мой гардероб</h3><p data-wardrobe-count>${owned.length} предмета · 6 разделов</p></div><span data-wardrobe-status role="status" aria-live="polite"></span></div>
      <div class="looks-tools"><label><span>Найти предмет</span><input type="search" placeholder="Название" autocomplete="off" data-wardrobe-search></label><label><span>Коллекция</span><select data-wardrobe-lineup><option value="">Все коллекции</option>${Object.entries(LINEUP_LABELS).map(([id,name])=>`<option value="${esc(id)}">${esc(name)}</option>`).join('')}</select></label></div>
      ${owned.length?'': '<p class="empty">Пока нет предметов в гардеробе.</p>'}<p class="empty" data-wardrobe-empty hidden>Ничего не найдено. Измени поиск или коллекцию.</p>
      <div class="looks-slots">${Object.entries(wardrobe.slots||{}).map(([slot,items])=>slotHtml(slot,items)).join('')}</div></section>`;
    root.querySelectorAll('[data-cosmetic-id]').forEach(button=>button.addEventListener('click',()=>appearanceEquip(button.dataset.cosmeticId)));
    root.querySelectorAll('[data-cosmetic-slot]').forEach(button=>button.addEventListener('click',()=>appearanceUnequip(button.dataset.cosmeticSlot)));
    root.querySelector('[data-wardrobe-search]')?.addEventListener('input',applyWardrobeFilters);
    root.querySelector('[data-wardrobe-lineup]')?.addEventListener('change',applyWardrobeFilters);
    root.querySelectorAll('[data-wardrobe-slot]').forEach(section=>section.addEventListener('toggle',()=>{if(!section.open)return;wardrobeOpenSlot=section.dataset.wardrobeSlot;root.querySelectorAll('[data-wardrobe-slot][open]').forEach(other=>{if(other!==section)other.open=false;});}));
    if(typeof _looksObserveSwatches==='function') _looksObserveSwatches(root);
    setWardrobeBusyState(wardrobeBusy);
  }
  async function refreshWardrobe(){
    const fresh=await api('/appearance/me');
    await loadProfile();
    wardrobe=fresh; render();
  }
  async function mutateWardrobe(request, success){
    if(wardrobeBusy){ toast('Предыдущая смена образа ещё сохраняется.',false); return; }
    wardrobeBusy=true; setWardrobeBusyState(true);
    try { await request(); await refreshWardrobe(); toast(success); }
    catch(error) { toast(error,false); }
    finally { wardrobeBusy=false; setWardrobeBusyState(false); }
  }
  window.appearanceEquip=function(id){
    return mutateWardrobe(()=>api('/appearance/equip',{method:'POST',body:JSON.stringify({cosmetic_id:id})}),'Образ сохранён');
  };
  window.setWardrobePreview=function(mode){ wardrobePreviewMode=mode==='saved'?'saved':'public'; render(); };
  window.appearanceUnequip=function(slot){
    return mutateWardrobe(()=>api('/appearance/unequip',{method:'POST',body:JSON.stringify({slot})}),'Предмет снят');
  };
  window.openLooksModal=async function(){
    switchPage('looks'); const root=el('pg-looks'); if(root)root.innerHTML='<div class="loader" style="margin-top:44px">Загрузка гардероба…</div>';
    try { await refreshWardrobe(); }
    catch(error) { if(root)root.innerHTML=`<div class="err" style="margin:16px">${esc(error)}</div>`; }
  };
  function dateLabel(value){
    if(!value) return '—';
    const parsed=new Date(value);
    return Number.isNaN(parsed.getTime())?esc(String(value).replace('T',' ').slice(0,16)):parsed.toLocaleDateString('ru-RU');
  }
  window.openPublicProfile=async function(profileRef){
    const ref=String(profileRef||'');
    if(!/^[A-Za-z0-9_-]{16,64}$/.test(ref)){ toast('Ссылка на профиль недействительна.',false); return; }
    switchPage('public-profile');
    const root=el('pg-public-profile'); if(!root) return;
    root.innerHTML='<div class="loader" style="margin-top:44px">Загрузка профиля игрока…</div>';
    try {
      const d=await api('/profile/public/'+encodeURIComponent(ref));
      root.innerHTML=`<div class="looks-head"><button class="looks-back" onclick="goTo('profile')" aria-label="Назад">‹</button><h1 class="looks-htitle">Публичный профиль</h1></div>${renderProfileShowcase(d,d.cosmetics,{caption:'Публичный профиль'})}${renderProfileDetails(d)}`;
    } catch(error) { root.innerHTML=`<div class="looks-head"><button class="looks-back" onclick="goTo('profile')" aria-label="Назад">‹</button><h1 class="looks-htitle">Профиль игрока</h1></div><div class="err" style="margin:16px">${esc(error)}</div>`; }
  };
  const chatTracker={query:'',sort:'recent',items:[],nextOffset:null,summary:{},filteredCount:0,busy:false,debounce:null,requestGeneration:0,error:'',pendingFocus:''};
  const CHAT_SORTS={recent:'Недавние',week:'За неделю',messages:'За всё время',rank:'По рангу'};
  function sanctionLabel(action){return ({warn:'Предупреждение',mute:'Мут',kick:'Исключение',ban:'Блокировка'})[action]||'Модерация';}
  function chatTrackerCard(chat){
    const history=(chat.sanction_history||[]).map(x=>`<li><span>${esc(sanctionLabel(x.action))}</span><time>${dateLabel(x.created_at)}</time></li>`).join('');
    const mute=chat.muted_until?`Мут до ${dateLabel(chat.muted_until)}`:(chat.warnings?`Предупреждений: ${fmt(chat.warnings)}`:'Санкций сейчас нет');
    return `<article class="chat-tracker-card">
      <header><div><h2>${esc(chat.chat_title||'Чат без названия')}</h2><small>Активность ${dateLabel(chat.last_message_at)}</small></div>${chat.activity_streak_days?`<span class="chat-tracker-streak" title="Дни активности подряд">🔥 ${fmt(chat.activity_streak_days)}</span>`:''}</header>
      <div class="chat-tracker-metrics"><span><b>${fmt(chat.user_messages_count_per_day||0)}</b><small>сегодня</small></span><span><b>${fmt(chat.user_messages_count_per_week||0)}</b><small>за неделю</small></span><span><b>${fmt(chat.user_messages_count_all_time||0)}</b><small>всего</small></span></div>
      <div class="chat-tracker-meta"><span>Уровень ${fmt(chat.user_level||1)}</span><span>${chat.local_rank?`Ранг ${fmt(chat.local_rank)}`:'Ранг ещё не получен'}</span><span class="${chat.warnings||chat.muted_until?'has-sanction':''}">${mute}</span></div>
      ${history?`<details class="chat-tracker-history"><summary>История модерации · ${history.match(/<li>/g)?.length||0}</summary><ul>${history}</ul></details>`:''}
    </article>`;
  }
  function renderChatTracker(){
    const root=el('pg-chat-tracker');if(!root)return;
    const active=document.activeElement,restoreSearch=active?.matches?.('.chat-tracker-tools input'),selection=restoreSearch?[active.selectionStart,active.selectionEnd]:null;
    const restoreSort=active?.dataset?.chatSort||'',restoreMore=active?.dataset?.chatMore==='true'||chatTracker.pendingFocus==='more';
    const summary=chatTracker.summary||{},hasQuery=Boolean(chatTracker.query),rows=chatTracker.items.map(chatTrackerCard).join('');
    const empty=hasQuery?'По этому запросу активных чатов не найдено.':'Ты пока не состоишь в активных чатах с собранной статистикой.';
    const emptyContent=chatTracker.error
      ?`<div class="chat-tracker-empty is-error"><b>Не удалось загрузить чаты</b><span>${esc(chatTracker.error)}</span><button type="button" onclick="loadChatTracker()">Повторить</button></div>`
      :`<div class="chat-tracker-empty"><b>${hasQuery?'Ничего не найдено':'Здесь пока тихо'}</b><span>${empty}</span></div>`;
    root.innerHTML=`<div class="chat-tracker-head"><button class="looks-back" onclick="goTo('profile')" aria-label="Назад">‹</button><div><h1>Трекер чатов</h1><p>Твоя активность, прогресс и санкции — отдельно по каждому чату.</p></div></div>
      <section class="chat-tracker-summary" aria-label="Сводка"><div><b>${fmt(summary.chat_count||0)}</b><span>активных чатов</span></div><div><b>${fmt(summary.messages_week||0)}</b><span>сообщений за неделю</span></div><div><b>${fmt(summary.messages_all_time||0)}</b><span>сообщений всего</span></div></section>
      <section class="chat-tracker-tools"><label><span class="sr-only">Найти чат</span><input type="search" value="${esc(chatTracker.query)}" maxlength="64" placeholder="Найти чат по названию" oninput="chatTrackerSearch(this.value)"></label><div class="chat-tracker-sorts" role="group" aria-label="Сортировка">${Object.entries(CHAT_SORTS).map(([key,label])=>`<button type="button" data-chat-sort="${key}" class="${chatTracker.sort===key?'is-active':''}" aria-pressed="${chatTracker.sort===key}" onclick="chatTrackerSort('${key}')">${label}</button>`).join('')}</div><p class="chat-tracker-status" tabindex="-1" role="status" aria-live="polite">${chatTracker.busy?'Обновляем…':(hasQuery?`Найдено: ${fmt(chatTracker.filteredCount)}`:`Показано: ${fmt(chatTracker.items.length)} из ${fmt(chatTracker.filteredCount)}`)}</p></section>
      <section class="chat-tracker-list">${rows||emptyContent}</section>
      ${chatTracker.error&&rows?`<div class="chat-tracker-page-error" role="alert"><span>Следующую страницу загрузить не удалось.</span><button type="button" onclick="chatTrackerLoadMore()">Повторить</button></div>`:''}
      ${chatTracker.nextOffset!==null?`<button type="button" data-chat-more="true" class="chat-tracker-more" onclick="chatTrackerLoadMore()" ${chatTracker.busy?'disabled':''}>${chatTracker.busy?'Загружаем…':'Показать ещё'}</button>`:''}`;
    if(restoreSearch){const input=root.querySelector('.chat-tracker-tools input');input?.focus({preventScroll:true});if(selection)input?.setSelectionRange(selection[0],selection[1]);}
    else if(restoreSort)root.querySelector(`[data-chat-sort="${restoreSort}"]`)?.focus({preventScroll:true});
    else if(restoreMore&&!chatTracker.busy){(root.querySelector('[data-chat-more="true"]')||root.querySelector('.chat-tracker-status'))?.focus({preventScroll:true});chatTracker.pendingFocus='';}
  }
  async function loadChatTracker({append=false}={}){
    const generation=++chatTracker.requestGeneration;chatTracker.busy=true;chatTracker.error='';if(append)renderChatTracker();
    const offset=append?chatTracker.nextOffset||0:0;
    try{
      const d=await api(`/profile/me/chat-tracker?limit=12&offset=${offset}&sort=${encodeURIComponent(chatTracker.sort)}&query=${encodeURIComponent(chatTracker.query)}`);
      if(generation!==chatTracker.requestGeneration)return;
      chatTracker.summary=d.summary||{};chatTracker.filteredCount=Number(d.filtered_count)||0;chatTracker.nextOffset=d.next_offset;
      chatTracker.items=append?chatTracker.items.concat(d.items||[]):(d.items||[]);
    }catch(error){if(generation!==chatTracker.requestGeneration)return;chatTracker.error=String(error||'Неизвестная ошибка');toast(error,false);if(!append){chatTracker.items=[];chatTracker.filteredCount=0;}}
    finally{if(generation===chatTracker.requestGeneration){chatTracker.busy=false;renderChatTracker();}}
  }
  window.chatTrackerSearch=function(value){chatTracker.query=String(value||'').slice(0,64);clearTimeout(chatTracker.debounce);chatTracker.debounce=setTimeout(()=>loadChatTracker(),260);};
  window.chatTrackerSort=function(value){if(!CHAT_SORTS[value]||value===chatTracker.sort)return;chatTracker.sort=value;loadChatTracker();};
  window.chatTrackerLoadMore=function(){if(!chatTracker.busy&&chatTracker.nextOffset!==null){chatTracker.pendingFocus='more';loadChatTracker({append:true});}};
  window.loadChatTracker=loadChatTracker;
  window.openChatTracker=function(){
    switchPage('chat-tracker');const root=el('pg-chat-tracker');if(!root)return;
    root.innerHTML='<div class="loader" style="margin-top:44px">Собираем статистику чатов…</div>';loadChatTracker();
  };
  window.openPetsV1=function(){
    switchPage('pets'); const root=el('pg-pets'); root.innerHTML='<div class="loader" style="margin-top:44px">Загрузка питомцев…</div>';
    api('/pets-v1/me').then(d=>{
      const foods=d.food||[];
      const cards=(d.pets||[]).map(p=>{
        const foodButtons=Number(p.endurance)<100&&foods.length?`<div class="pet-food-row" aria-label="Покормить ${esc(p.name)}">${foods.map(f=>`<button type="button" onclick="petsV1Feed(${p.id},'${esc(f.id)}')" title="+${f.restore} выносливости"><span>${esc(f.icon)}</span><b>+${f.restore}</b><small>${f.quantity} шт.</small></button>`).join('')}</div>`:'';
        return`<article class="pcard pet-release-card"><header><b>🐾 ${esc(p.name)}</b>${p.active?'<span>Активный</span>':''}</header><div class="pet-endurance"><div><i style="width:${Math.max(0,Math.min(100,Number(p.endurance)||0))}%"></i></div><b>${p.endurance}/100</b></div><p>Уровень ${p.level}/16 · ${esc(p.effects.visual_stage)} · маршрут +${p.effects.expedition_route_bonus_percent}%</p>${foodButtons}${p.active?'':`<button class="btn btn-ghost pet-activate" onclick="petsV1Activate(${p.id})">Сделать активным</button>`}</article>`;
      }).join('');
      const a=d.activity;
      const activePet=(d.pets||[]).find(p=>p.active),activityCosts=d.activity_costs||{};
      const decisionLabels={careful:'Осторожный маршрут',steady:'Ровный маршрут',bold:'Рискованный маршрут'};
      const timer=a?`<section class="looks-release-section pet-activity"><h3>${a.kind==='trek'?'Поход':'Экспедиция'}</h3><p>${a.status==='ready'?(a.kind==='expedition'&&!a.decision?`Таймер завершён. Выбери маршрут:`:'Награда уже получена.'):`Питомец занят до ${esc(String(a.ends_at).replace('T',' ').slice(0,16))}.`}</p>${a.status==='ready'&&a.kind==='expedition'&&!a.decision?`<div class="pet-route-grid">${['careful','steady','bold'].map(x=>`<button class="btn btn-ghost" onclick="petsV1Choose('${x}')">${decisionLabels[x]}</button>`).join('')}</div>`:''}</section>`:
        (d.active_pet_id?`<section class="looks-release-section pet-activity"><h3>Отправить питомца</h3><p>${esc(d.activity_reward_label||'За завершение — один ключ.')} Выносливость списывается при старте.</p><div class="pet-activity-grid">${['trek','expedition'].map(kind=>d.durations.map(hours=>{const cost=Number(activityCosts[hours])||0,locked=!activePet||Number(activePet.endurance)<cost,hoursWord=Number(hours)===3?'часа':'часов';return`<button class="btn btn-ghost" onclick="petsV1Start('${kind}',${hours})" ${locked?'disabled':''} aria-label="${kind==='trek'?'Поход':'Экспедиция'} на ${hours} ${hoursWord}, ${cost} выносливости, награда один ключ"><b>${kind==='trek'?'Поход':'Экспедиция'}</b><small>${hours} ч · ${cost} ⚡ · 1 🗝</small></button>`;}).join('')).join('')}</div></section>`:'');
      const earned=(d.activity_rewards||[]).length?`<div class="pet-key-earned" role="status"><b>🗝 Ключ получен</b><span>Завершённая активность уже зачислена в сундуки.</span><button type="button" onclick="openChestsV1()">К сундукам</button></div>`:'';
      const bestiary=(d.bestiary||[]).map(p=>`<article class="bestiary-card ${p.owned?'is-owned':'is-locked'}"><span aria-hidden="true">${p.owned?esc(p.icon):'?'}</span><div><b>${p.owned?esc(p.name):'Неизвестный питомец'}</b><small>${esc(p.rarity)} · ${p.owned?'открыт':'не найден'}</small></div>${p.owned?'<i aria-label="Открыт">✓</i>':''}</article>`).join('');
      root.innerHTML=`<div class="looks-head"><button class="looks-back" onclick="goTo('profile')" aria-label="Назад">‹</button><div class="looks-htitle">🐾 Питомцы</div></div>
        <section class="pet-hero"><div><small>Коллекция спутников</small><h2>${fmt(d.bestiary_owned||0)} из ${fmt(d.bestiary_total||0)}</h2><p>Открывай сундуки, находи карточки и собирай весь бестиарий.</p></div><strong>${Math.round(100*Number(d.bestiary_owned||0)/Math.max(1,Number(d.bestiary_total||0)))}%</strong></section>
        <div class="pet-tabs" role="tablist"><button type="button" role="tab" aria-selected="true" onclick="showPetPanel('owned',this)">Мои питомцы</button><button type="button" role="tab" aria-selected="false" onclick="showPetPanel('bestiary',this)">Бестиарий</button></div>
        <div data-pet-panel="owned"><div class="looks-hint">Выносливость уменьшается примерно на 10 в сутки. Еда из сундуков восстанавливает её сразу; смена активного питомца стоит 5.</div>${earned}${cards||'<div class="empty">Первую карточку питомца можно найти в сундуке.</div>'}${timer}</div>
        <div data-pet-panel="bestiary" hidden><div class="bestiary-grid">${bestiary}</div></div>`;
    }).catch(e=>root.innerHTML=`<div class="err" style="margin:16px">${esc(e)}</div>`);
  };
  window.showPetPanel=function(name,button){const root=el('pg-pets');root.querySelectorAll('[data-pet-panel]').forEach(x=>x.hidden=x.dataset.petPanel!==name);root.querySelectorAll('.pet-tabs button').forEach(x=>x.setAttribute('aria-selected',String(x===button)));};
  const _petsV1PendingActions=new Map();
  const _questsV1PendingActions=new Map();
  const _chestsV1PendingActions=new Map();
  function _pendingAction(store,key,prefix){
    const existing=store.get(key);
    if(existing)return existing;
    const value=prefix+(globalThis.crypto?.randomUUID?.()||Date.now().toString(36));
    store.set(key,value);return value;
  }
  window.petsV1Activate=function(id){
    const key=`activate:${id}`,action=_pendingAction(_petsV1PendingActions,key,'pet-activate-');
    api('/pets-v1/active',{method:'POST',body:JSON.stringify({pet_id:id,action_id:action})}).then(()=>{_petsV1PendingActions.delete(key);toast('Активный питомец выбран');openPetsV1();}).catch(e=>{toast(`${e} Проверяем актуальное состояние.`,false);openPetsV1();});
  };
  window.petsV1Start=function(kind,hours){
    const key=`activity:${kind}:${hours}`,action=_pendingAction(_petsV1PendingActions,key,'pet-activity-');
    api('/pets-v1/activity',{method:'POST',body:JSON.stringify({kind:kind,hours:hours,action_id:action})}).then(()=>{_petsV1PendingActions.delete(key);toast('Таймер запущен');openPetsV1();}).catch(e=>{toast(`${e} Проверяем запущенный таймер.`,false);openPetsV1();});
  };
  window.petsV1Feed=function(petId,foodId){
    const key=`feed:${petId}:${foodId}`,action=_pendingAction(_petsV1PendingActions,key,'pet-feed-');
    api('/pets-v1/feed',{method:'POST',body:JSON.stringify({pet_id:petId,food_id:foodId,action_id:action})}).then(d=>{_petsV1PendingActions.delete(key);toast(`Выносливость восстановлена до ${d.endurance}/100`);openPetsV1();}).catch(e=>toast(`${e} Повтори: запрос будет отправлен с тем же номером операции.`,false));
  };
  window.petsV1Choose=function(decision){
    const key=`decision:${decision}`,action=_pendingAction(_petsV1PendingActions,key,'pet-decision-');
    api('/pets-v1/expedition/decision',{method:'POST',body:JSON.stringify({decision:decision,action_id:action})}).then(d=>{_petsV1PendingActions.delete(key);toast(d.amount_keys?'Экспедиция завершена · +1 🗝':'Маршрут выбран');openPetsV1();}).catch(e=>{toast(`${e} Проверяем итог маршрута.`,false);openPetsV1();});
  };
  let _chestsV1Data=null,_chestsV1Busy=false,_chestsV1Prepared=null,_chestsV1LastResult=null;
  function chestRewardText(reward){
    if(!reward)return'Награда';
    const amount=fmt(reward.amount||0),name=esc(reward.name||reward.kind||'Награда'),icon=esc(reward.icon||'🎁');
    if(['mora','diamonds','zarniki'].includes(reward.kind))return`${amount} ${icon} ${name}`;
    if(reward.kind==='vip_days')return`${amount} дня ${icon} VIP`;
    return`${icon} ${name}${Number(reward.amount||0)>1?` · ${amount} шт.`:''}`;
  }
  function chestAmountText(outcome){
    const amount=outcome?.amount||{};
    if(amount.unit==='vip_days')return`${fmt(amount.fixed)} дня`;
    if(Number.isFinite(Number(amount.fixed)))return`${fmt(amount.fixed)} шт.`;
    if(Number.isFinite(Number(amount.min))&&Number.isFinite(Number(amount.max)))return amount.min===amount.max?fmt(amount.min):`${fmt(amount.min)}–${fmt(amount.max)}`;
    return'';
  }
  function chestOddsDetails(outcome){
    const parts=[];
    if(outcome?.rarity_odds)parts.push(`Редкости: ${Object.entries(outcome.rarity_odds).map(([rarity,percent])=>`${rarLabel(rarity)} ${percent}%`).join(' · ')}`);
    if(Array.isArray(outcome?.pool)&&outcome.pool.length){
      const names=outcome.pool.map(item=>typeof item==='object'?(item.name||item.id):item).filter(Boolean);
      parts.push(`Пул: ${names.join(', ')}`);
    }
    if(outcome?.fallback)parts.push(outcome.fallback);
    return parts.length?`<small>${esc(parts.join(' · '))}</small>`:'';
  }
  function renderChestsV1(){
    const d=_chestsV1Data,root=el('pg-chests');if(!d||!root)return;
    const odds=(d.star_odds||[]).map(row=>`<li><span>${row.stars}★</span><b>${String(row.percent).replace('.',',')}%</b></li>`).join('');
    const rewards=(d.rewards||[]).map(row=>`<details class="chest-tier"><summary><b>${row.stars}★</b><span>${String(row.star_percent).replace('.',',')}% сундуков</span></summary><ul>${(row.outcomes||[]).map(outcome=>`<li><span><b>${esc(outcome.label)}</b>${chestOddsDetails(outcome)}</span><em>${outcome.conditional_percent}%${chestAmountText(outcome)?` · ${chestAmountText(outcome)}`:''}</em></li>`).join('')}</ul></details>`).join('');
    const paid=d.funding||{},remaining=Math.max(0,Number(paid.remaining_today)||0),price=Number(paid.price_zarniki)||0;
    const inv=d.inventory||{},owned=Object.keys(inv.unlocked_pets||{}).length,cards=Object.values(inv.pet_cards||{}).reduce((a,b)=>a+Number(b||0),0),food=Object.values(inv.foods||{}).reduce((a,b)=>a+Number(b||0),0),jokers=Object.values(inv.jokers||{}).reduce((a,b)=>a+Number(b||0),0);
    const prepared=_chestsV1Prepared?`<section class="chest-reveal-zone"><button type="button" class="chest-orb" onclick="chestsV1Reveal()" ${_chestsV1Busy?'disabled':''} aria-label="Раскрыть подготовленный сундук"><span aria-hidden="true">✦</span><b>${_chestsV1Busy?'Раскрываю…':'Коснись, чтобы раскрыть'}</b><small>Награда уже сохранена сервером</small></button></section>`:'';
    const result=_chestsV1LastResult?`<section class="chest-result" role="status"><span>${'★'.repeat(Math.min(10,Number(_chestsV1LastResult.stars)||1))}</span><b>Получено: ${chestRewardText(_chestsV1LastResult.reward)}</b><small>Доставлено и записано · каталог ${esc(_chestsV1LastResult.catalog_version||'')}</small></section>`:'';
    root.innerHTML=`<header class="looks-head chest-head"><button class="looks-back" onclick="goTo('profile')" aria-label="Назад в профиль">‹</button><div><h1>🗝 Сундуки</h1><small>Одна попытка — одна честно зафиксированная награда</small></div></header><section class="chest-balance"><span>Твои ключи</span><b>${fmt(d.key_balance||0)} 🗝</b><small>Ещё по ключу дают полный день и неделя квестов</small></section><section class="chest-inventory" aria-label="Коллекция из сундуков"><span><b>${owned}/12</b> питомцев</span><span><b>${cards}</b> карт</span><span><b>${food}</b> еды</span><span><b>${jokers}</b> джокеров</span></section>${prepared}${!prepared?result:''}<div class="chest-actions"><button type="button" class="btn chest-open-btn" onclick="chestsV1Prepare()" ${_chestsV1Busy||_chestsV1Prepared||Number(d.key_balance||0)<1?'disabled':''}>${Number(d.key_balance||0)<1?'Сначала получи ключ':'Открыть за 1 ключ'}</button><button type="button" class="chest-buy-btn" onclick="chestsV1AskBuy(this)" ${_chestsV1Busy||_chestsV1Prepared||remaining<1?'disabled':''}><span>Купить ключ</span><b>${price} ✨</b><small>${remaining?`доступно сегодня: ${remaining} из ${paid.daily_limit}`:'лимит на сегодня исчерпан'}</small></button></div><p class="chest-policy">${esc(d.message||'')}</p><details class="chest-odds"><summary>Точные шансы и размеры наград</summary><div><section><h2>Шанс звёздности</h2><ul>${odds}</ul></section><section class="chest-reward-tiers"><h2>Награда внутри звёздности</h2>${rewards}</section></div><p>Сначала сервер выбирает звёздность, затем одну награду по процентам внутри неё. Бесплатные и купленные ключи равны; скорость тапов ничего не меняет.</p></details><div class="chest-canary-note"><b>Карты не пропадут</b><span>${esc(d.surplus_policy||'Лишние карты сохраняются в инвентаре.')}</span></div>`;
  }
  window.openChestsV1=function(){
    switchPage('chests');const root=el('pg-chests');root.innerHTML='<div class="loader" style="margin-top:44px">Загрузка сундуков…</div>';
    api('/chests-v1/me').then(d=>{_chestsV1Data=d;_chestsV1Prepared=d.pending_open||null;_chestsV1LastResult=d.last_result||null;renderChestsV1();}).catch(e=>root.innerHTML=`<div class="err quest-load-error" role="alert"><b>Сундуки не загрузились</b><span>${esc(e)}</span><button type="button" onclick="openChestsV1()">Повторить</button></div>`);
  };
  window.chestsV1Prepare=function(){
    if(_chestsV1Busy||_chestsV1Prepared||!_chestsV1Data)return;_chestsV1Busy=true;renderChestsV1();
    const key='prepare',action=_pendingAction(_chestsV1PendingActions,key,'chest-open-');
    api('/chests-v1/prepare',{method:'POST',body:JSON.stringify({action_id:action,catalog_version:_chestsV1Data.catalog_version,catalog_digest:_chestsV1Data.catalog_digest})}).then(d=>{_chestsV1PendingActions.delete(key);_chestsV1Prepared=d;_chestsV1Data.key_balance=d.key_balance;_chestsV1Busy=false;renderChestsV1();requestAnimationFrame(()=>el('pg-chests')?.querySelector('.chest-orb')?.focus());}).catch(e=>{_chestsV1Busy=false;toast(`${e} Повтори: ключ не спишется второй раз.`,false);openChestsV1();});
  };
  window.chestsV1Buy=function(){
    if(_chestsV1Busy||!_chestsV1Data||Number(_chestsV1Data.funding?.remaining_today||0)<1)return;_chestsV1Busy=true;renderChestsV1();
    const key='purchase',action=_pendingAction(_chestsV1PendingActions,key,'chest-buy-');
    api('/chests-v1/purchase',{method:'POST',body:JSON.stringify({action_id:action,catalog_version:_chestsV1Data.catalog_version,catalog_digest:_chestsV1Data.catalog_digest})}).then(d=>{_chestsV1PendingActions.delete(key);toast(`Ключ куплен за ${fmt(d.price_zarniki)} ✨`);_chestsV1Busy=false;openChestsV1();}).catch(e=>{_chestsV1Busy=false;toast(`${e} Повтори: покупка сохранит тот же номер операции.`,false);openChestsV1();});
  };
  window.chestsV1AskBuy=function(trigger){
    if(_chestsV1Busy||!_chestsV1Data)return;
    const funding=_chestsV1Data.funding||{},price=Number(funding.price_zarniki)||0,remaining=Number(funding.remaining_today)||0;
    if(trigger)trigger.dataset.modalTrigger='true';
    OM('Купить ключ',`<div class="chest-buy-confirm"><b>1 ключ за ${fmt(price)} ✨</b><p>Шансы полностью совпадают с бесплатным ключом. Сегодня после покупки останется ${Math.max(0,remaining-1)} из ${funding.daily_limit||0} покупок.</p><small>Неиспользованный купленный ключ можно вернуть через поддержку.</small></div>`,[{l:`Купить за ${fmt(price)} ✨`,c:'btn-gold',f:'chestsV1Buy();CM()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
  };
  window.chestsV1Reveal=function(){
    if(_chestsV1Busy||!_chestsV1Prepared)return;_chestsV1Busy=true;renderChestsV1();
    api(`/chests-v1/${encodeURIComponent(_chestsV1Prepared.open_id)}/reveal`,{method:'POST'}).then(d=>{_chestsV1Busy=false;_chestsV1Prepared=null;_chestsV1LastResult=d;toast(`${d.stars}★ · ${chestRewardText(d.reward)}`);openChestsV1();}).catch(e=>{_chestsV1Busy=false;toast(e,false);openChestsV1();});
  };
  let _questsV1Data=null,_questsV1Tab='daily',_questsV1Busy=false;
  function questMetricMeta(metric){
    if(metric==='game_completed')return{icon:'◆',label:'Выбрать игру',tone:'game',action:"goTo('arena','game')"};
    if(metric.startsWith('rhythm_'))return{icon:'ᚱ',label:'Открыть Ритм',tone:'rhythm',action:'openRhythmV2Game()'};
    if(metric.startsWith('minesweeper_'))return{icon:'▦',label:'Открыть Сапёр',tone:'mines',action:'openMinesweeperGame()'};
    if(metric.startsWith('mafia_'))return{icon:'◈',label:'Открыть игры',tone:'mafia',action:"goTo('arena','game')"};
    if(metric==='chest_revealed')return{icon:'✦',label:'К сундукам',tone:'chest',action:'openChestsV1()'};
    if(metric==='pet_fed'||metric==='pet_activity_completed')return{icon:'🐾',label:'К питомцам',tone:'pets',action:'openPetsV1()'};
    return{icon:'◆',label:'К играм',tone:'game',action:"goTo('arena','game')"};
  }
  function questCard(quest,period,rerolls){
    const progress=Math.max(0,Number(quest.progress)||0),target=Math.max(1,Number(quest.target)||1);
    const percent=Math.min(100,Math.round(progress/target*100)),meta=questMetricMeta(quest.metric);
    const status=quest.completed?'<span class="quest-status is-done">Готово</span>':`<span class="quest-status">${progress} / ${target}</span>`;
    const reroll=quest.completed?'':`<button class="quest-icon-action" type="button" onclick="questsV1AskReroll('${period}',${quest.slot},this)" aria-label="Заменить квест «${esc(quest.title)}»" ${rerolls.remaining>0&&!_questsV1Busy?'':'disabled'}><span>Сменить</span> ↻</button>`;
    const action=quest.completed?'<span class="quest-complete-note">✓ Задание выполнено</span>':`<button class="quest-route" type="button" onclick="${meta.action}">${meta.label}<span aria-hidden="true">›</span></button>${reroll}`;
    return `<article class="quest-card ${quest.completed?'is-done':''}"><div class="quest-card-icon quest-tone-${meta.tone}" aria-hidden="true">${meta.icon}</div><div class="quest-card-copy"><div class="quest-card-title"><strong>${esc(quest.title)}</strong>${status}</div><div class="quest-progress" role="progressbar" aria-label="${esc(quest.title)}: ${Math.min(progress,target)} из ${target}" aria-valuemin="0" aria-valuemax="${target}" aria-valuenow="${Math.min(progress,target)}"><i style="width:${percent}%"></i></div><div class="quest-card-meta"><span>${percent}%</span><span>${esc(quest.help)}</span></div><div class="quest-card-actions ${quest.completed?'is-complete':''}">${action}</div></div></article>`;
  }
  function questRewardCard(kind,reward,daily,weekly){
    const label={daily:'За день',weekly:'За неделю',combined:'За всё'}[kind]||kind;
    const target=kind==='daily'?daily:kind==='weekly'?weekly:null;
    const state=reward.claimed?'Получено':reward.claimable?'Готово к выдаче':kind==='combined'?`${daily.done}/${daily.total} за день · ${weekly.done}/${weekly.total} за неделю`:`${target.done}/${target.total} заданий`;
    const destination=kind==='weekly'?'weekly':kind==='combined'&&daily.done===daily.total?'weekly':'daily';
    const button=reward.claimable?`<button class="quest-reward-claim" type="button" onclick="questsV1Claim('${kind}')" ${_questsV1Busy?'disabled':''}>${_questsV1Busy?'Подожди…':'Забрать'}</button>`:(!reward.claimed?`<button class="quest-reward-go" type="button" onclick="questsV1SetTab('${destination}')">К заданиям</button>`:'');
    const keys=_sysFlags.content_chests_v1?Number(reward.amount_keys||0):0,value=`${reward.amount_mora} 🪙${keys?` + ${keys} 🗝`:''}`;
    return `<article class="quest-reward ${button?'has-action ':''}${reward.claimed?'is-claimed':reward.claimable?'is-ready':''}"><span class="quest-reward-mark" aria-hidden="true">${reward.claimed?'✓':keys?'🗝':'🪙'}</span><span><strong>${esc(label)}</strong><small>${esc(state)}</small></span><b>${value}</b>${button}</article>`;
  }
  function questPeriodSummary(period){
    const quests=_questsV1Data?.[period]?.quests||[],done=quests.filter(q=>q.completed).length;
    return {done,total:quests.length,percent:quests.length?Math.round(done/quests.length*100):0};
  }
  function renderQuestsV1(){
    const d=_questsV1Data,root=el('pg-questlog'); if(!d||!root)return;
    const rr=d.rerolls||{remaining:0,limit:0},daily=questPeriodSummary('daily'),weekly=questPeriodSummary('weekly');
    const active=_questsV1Tab==='weekly'?weekly:daily,period=_questsV1Tab==='weekly'?'weekly':'daily';
    const tasks=(d[period]?.quests||[]).map(q=>questCard(q,period,rr)).join('');
    const rewardKinds=['daily','weekly','combined'],rewardItems=d.rewards?.items||{};
    const rewardTotal=rewardKinds.reduce((sum,kind)=>sum+(Number(rewardItems[kind]?.amount_mora)||0),0);
    const rewards=rewardKinds.map(kind=>questRewardCard(kind,rewardItems[kind]||{amount_mora:0},daily,weekly)).join('');
    const periodReward=Number(rewardItems[period]?.amount_mora)||0,periodKeys=_sysFlags.content_chests_v1?(Number(rewardItems[period]?.amount_keys)||0):0;
    const keySummary=_sysFlags.content_chests_v1?' + 2 🗝 за день и неделю':'',keyBalance=_sysFlags.content_chests_v1?`<div class="quest-head-stats"><small>У тебя</small><b>${Number(d.rewards?.key_balance)||0} 🗝</b></div>`:'';
    const content=_questsV1Tab==='rewards'?`<section class="quest-panel" id="quest-panel" role="tabpanel" aria-labelledby="quest-tab-rewards"><div class="quest-section-head"><div><span>Три понятные цели</span><h2>${rewardTotal} 🪙${keySummary}</h2></div>${keyBalance}</div><div class="quest-reward-list">${rewards}</div><p class="quest-policy">${esc(d.rewards?.message||'')}</p></section>`:`<section class="quest-panel" id="quest-panel" role="tabpanel" aria-labelledby="quest-tab-${period}"><div class="quest-section-head"><div><span>${period==='daily'?'Сегодня':'Эта неделя'}</span><h2>${active.done}/${active.total} выполнено → ${periodReward} 🪙${periodKeys?` + ${periodKeys} 🗝`:''}</h2></div><div class="quest-head-stats"><b>${active.percent}%</b><small>↻ ${rr.remaining||0}/${rr.limit||0}</small></div></div><div class="quest-list">${tasks||'<div class="quest-empty"><b>Нет доступных заданий</b><span>Как только откроется доступная игра, задания появятся здесь.</span><button onclick="openQuestsV1()">Обновить</button></div>'}</div></section>`;
    const tab=(id,label)=>`<button id="quest-tab-${id}" role="tab" tabindex="${_questsV1Tab===id?'0':'-1'}" aria-selected="${_questsV1Tab===id}" class="${_questsV1Tab===id?'is-active':''}" onclick="questsV1SetTab('${id}')" onkeydown="questsV1TabKey(event)" aria-controls="quest-panel">${label}</button>`;
    root.innerHTML=`<header class="looks-head quest-head"><button class="looks-back" onclick="goTo('profile')" aria-label="Назад в профиль">‹</button><div><h1>🧭 Квесты</h1><small>Разные цели, честный прогресс, понятная награда</small></div></header><nav class="quest-tabs" role="tablist" aria-label="Разделы квестов">${tab('daily',`Сегодня <span>${daily.done}/${daily.total}</span>`)}${tab('weekly',`Неделя <span>${weekly.done}/${weekly.total}</span>`)}${tab('rewards','Награды')}</nav>${content}`;
  }
  window.questsV1SetTab=function(tab){if(!['daily','weekly','rewards'].includes(tab))return;_questsV1Tab=tab;renderQuestsV1();scrollTo(0,0);requestAnimationFrame(()=>el('pg-questlog')?.querySelector('.quest-tabs .is-active')?.focus());};
  window.questsV1TabKey=function(event){
    const tabs=['daily','weekly','rewards'],index=tabs.indexOf(_questsV1Tab);let next=null;
    if(event.key==='ArrowRight')next=tabs[(index+1)%tabs.length];
    if(event.key==='ArrowLeft')next=tabs[(index-1+tabs.length)%tabs.length];
    if(event.key==='Home')next=tabs[0]; if(event.key==='End')next=tabs[tabs.length-1];
    if(next){event.preventDefault();questsV1SetTab(next);}
  };
  window.openQuestsV1=function(tab){
    if(['daily','weekly','rewards'].includes(tab))_questsV1Tab=tab;
    switchPage('questlog'); const root=el('pg-questlog'); root.innerHTML='<div class="loader" style="margin-top:44px">Загрузка квестов…</div>';
    api('/quests-v1/me').then(d=>{_questsV1Data=d;renderQuestsV1();}).catch(e=>root.innerHTML=`<div class="err quest-load-error" role="alert"><b>Квесты не загрузились</b><span>${esc(e)}</span><button type="button" onclick="openQuestsV1('${_questsV1Tab}')">Повторить</button></div>`);
  };
  window.questsV1AskReroll=function(period,slot,trigger){
    if(_questsV1Busy){toast('Дождись завершения текущего действия.',false);return;}
    const quest=(_questsV1Data?.[period]?.quests||[]).find(q=>Number(q.slot)===Number(slot));
    if(!quest||quest.completed)return;
    const remaining=Number(_questsV1Data?.rerolls?.remaining)||0;
    if(remaining<=0){toast('Лимит замен на эту неделю исчерпан.',false);return;}
    if(trigger)trigger.dataset.modalTrigger='true';
    OM('↻ Заменить квест',`<div class="quest-reroll-confirm"><b>${esc(quest.title)}</b><p>Сервер подберёт другой тип задания из доступных игр. Вернуть этот вариант нельзя.</p><span>После замены останется: ${remaining-1}</span></div>`,[{l:'Заменить',c:'btn-gold',f:`questsV1Reroll('${period}',${slot});CM()`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
  };
  window.questsV1Reroll=function(period,slot){
    if(_questsV1Busy)return;
    _questsV1Busy=true;renderQuestsV1();
    const key=`reroll:${period}:${slot}`,action=_pendingAction(_questsV1PendingActions,key,'quest-reroll-');
    api('/quests-v1/reroll',{method:'POST',body:JSON.stringify({period,slot,action_id:action})}).then(d=>{_questsV1PendingActions.delete(key);_questsV1Data=d;toast('Квест заменён');}).catch(e=>toast(`${e} Повтори: лимит не спишется второй раз.`,false)).finally(()=>{_questsV1Busy=false;renderQuestsV1();});
  };
  window.questsV1Claim=function(kind){
    if(_questsV1Busy)return;
    _questsV1Busy=true;renderQuestsV1();
    api('/quests-v1/claim-reward',{method:'POST',body:JSON.stringify({kind})}).then(d=>{
      _questsV1Data=d;const keys=_sysFlags.content_chests_v1?(Number(d.reward_result?.amount_keys)||0):0;toast(d.reward_result?.already_claimed?'Награда уже получена':`Получено: ${d.reward_result?.amount_mora||0} 🪙${keys?` + ${keys} 🗝`:''}`);
    }).catch(e=>toast(e,false)).finally(()=>{_questsV1Busy=false;renderQuestsV1();});
  };
  let _achievementsV1Data=null,_achievementsV1Filter='all';
  const _achievementAction={rhythm:'openRhythmV2Game()',minesweeper:'openMinesweeperGame()',mafia:'openMafiaStats()',chests:'openChestsV1()',pets:'openPetsV1()'};
  function achievementPct(value,target){return target?Math.max(0,Math.min(100,Math.round(Number(value||0)*100/Number(target)))):100;}
  function achievementWord(value,one,few,many){const n=Math.abs(Number(value))%100,n1=n%10;return n>10&&n<20?many:n1===1?one:n1>=2&&n1<=4?few:many;}
  function achievementFamilyCard(f){
    const next=f.next,weeksMax=Number(_achievementsV1Data?.max_active_weeks)||156;
    const finalMilestone=(f.milestones||[]).find(m=>Number(m.level)===Number(f.max_level));
    const eventTarget=Number(next?.events_required)||Number(finalMilestone?.events_required)||1,weekTarget=Number(next?.weeks_required)||weeksMax;
    const eventPct=achievementPct(f.completed_events,eventTarget),weekPct=achievementPct(f.active_weeks,weekTarget);
    const remainingEvents=Math.max(0,eventTarget-Number(f.completed_events||0)),remainingWeeks=Math.max(0,weekTarget-Number(f.active_weeks||0));
    const remaining=[];
    if(remainingEvents)remaining.push(`${remainingEvents} ${achievementWord(remainingEvents,'завершение','завершения','завершений')}`);
    if(remainingWeeks)remaining.push(`${remainingWeeks} ${achievementWord(remainingWeeks,'активная неделя','активные недели','активных недель')}`);
    const nextCopy=next?`До уровня ${next.level}: ${remaining.length?'ещё '+remaining.join(' и '):'условия выполнены'}.`:'Все 40 уровней пути завершены.';
    const eventCopy=Number(f.completed_events)>=eventTarget?`${fmt(f.completed_events)} · цель ${fmt(eventTarget)} ✓`:`${fmt(f.completed_events)} / ${fmt(eventTarget)}`;
    const weekCopy=Number(f.active_weeks)>=weekTarget?`${fmt(f.active_weeks)} · цель ${fmt(weekTarget)} ✓`:`${fmt(f.active_weeks)} / ${fmt(weekTarget)}`;
    const milestones=(f.milestones||[]).map(m=>`<li class="achievement-milestone is-${esc(m.status)}"><span>${m.status==='claimed'?'✓':m.status==='reached'?'•':'○'}</span><b>${m.level} ур.</b><small>${fmt(m.events_required)} ${achievementWord(m.events_required,'завершение','завершения','завершений')} · ${m.weeks_required} нед.</small><em>+${fmt(m.reward_mora)} 🪙</em></li>`).join('');
    return `<article class="achievement-card" data-category="${esc(f.category)}">
      <header class="achievement-card-head"><span class="achievement-icon" aria-hidden="true">${esc(f.icon)}</span><div><small>${f.category==='games'?'Игры':'Приключения'}</small><h2>${esc(f.title)}</h2><p>${esc(f.help)}</p></div><strong>${f.level}<small>/ ${f.max_level}</small></strong></header>
      <div class="achievement-next"><b>${next?`Следующий уровень · +${fmt(next.reward_mora)} Моры`:'Путь завершён'}</b><span>${esc(nextCopy)}</span></div>
      <div class="achievement-meter"><label><span>Завершения</span><b>${eventCopy}</b></label><div role="progressbar" aria-label="${esc(f.title)}: завершения" aria-valuemin="0" aria-valuemax="${eventTarget}" aria-valuenow="${Math.min(Number(f.completed_events),eventTarget)}"><i style="width:${eventPct}%"></i></div></div>
      <div class="achievement-meter"><label><span>Активные недели</span><b>${weekCopy}</b></label><div role="progressbar" aria-label="${esc(f.title)}: активные недели" aria-valuemin="0" aria-valuemax="${weekTarget}" aria-valuenow="${Math.min(Number(f.active_weeks),weekTarget)}"><i style="width:${weekPct}%"></i></div></div>
      <div class="achievement-card-actions"><button type="button" onclick="${_achievementAction[f.id]||"goTo('activities')"}">${esc(f.action_label||'К активности')}</button><details><summary aria-label="Вехи: ${esc(f.title)}">Вехи</summary><p>Мора указана за достижение самого уровня.</p><ul>${milestones}</ul></details></div>
    </article>`;
  }
  function renderAchievementsV1(){
    const root=el('pg-achievements-v1'); if(!root||!_achievementsV1Data)return;
    const all=_achievementsV1Data.families||[],shown=_achievementsV1Filter==='all'?all:all.filter(f=>f.category===_achievementsV1Filter),summary=_achievementsV1Data.summary||{};
    root.innerHTML=`<div class="looks-head achievement-head"><button class="looks-back" onclick="goTo('profile')" aria-label="Назад">‹</button><h1 class="looks-htitle">🏅 Достижения</h1></div>
      <section class="achievement-hero"><div><span>Общий путь</span><strong>${fmt(summary.total_levels||0)} <small>/ ${fmt((summary.families||5)*40)} уровней</small></strong></div><div><span>Получено за уровни</span><strong>${fmt(summary.claimed_mora||0)} 🪙</strong></div><p>Засчитываются только подтверждённые завершения. Награда — Мора, без скрытой косметики.</p></section>
      <nav class="achievement-filters" aria-label="Категории достижений">${[['all','Все',all.length],['games','Игры',all.filter(f=>f.category==='games').length],['collection','Приключения',all.filter(f=>f.category==='collection').length]].map(([id,label,count])=>`<button type="button" data-achievement-filter="${id}" class="${_achievementsV1Filter===id?'is-active':''}" aria-pressed="${_achievementsV1Filter===id}" onclick="achievementsV1Filter('${id}')">${label}<span>${count}</span></button>`).join('')}</nav>
      <p class="sr-only" role="status" aria-live="polite">Показано путей: ${shown.length}</p><section class="achievement-list">${shown.map(achievementFamilyCard).join('')||'<p class="empty">В этой категории пока нет путей.</p>'}</section>`;
  }
  window.achievementsV1Filter=function(category){_achievementsV1Filter=['all','games','collection'].includes(category)?category:'all';renderAchievementsV1();requestAnimationFrame(()=>el('pg-achievements-v1')?.querySelector(`[data-achievement-filter="${_achievementsV1Filter}"]`)?.focus());};
  window.openAchievementsV1=function(){
    switchPage('achievements-v1'); const root=el('pg-achievements-v1'); root.innerHTML='<div class="loader" style="margin-top:44px">Загрузка достижений…</div>';
    api('/achievements-v1/me').then(d=>{_achievementsV1Data=d;_achievementsV1Filter='all';renderAchievementsV1();}).catch(e=>root.innerHTML=`<div class="err quest-load-error" role="alert"><b>Достижения не загрузились</b><span>${esc(e)}</span><button type="button" onclick="openAchievementsV1()">Повторить</button></div>`);
  };
})();
