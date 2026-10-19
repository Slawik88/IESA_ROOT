/* Биржа монет v2 — интерфейс.
   Все цены, комиссии и результаты считает аутентифицированный сервер.
   Клиент показывает опубликованные тики, опрашивает их и восстанавливает
   незавершённые операции по action_id. Генератор курса клиент не трогает. */
window.CM2 = (() => {
  let data=null, view='home', tab='market', selected=null, draft=null, busy=false,
      period=24, search='', group='all', limit=30, formRevision=0, marketRefreshing=false;
  let live={timer:null, clock:null, expiry:null, last:tickNow(), next:null};

  const root=()=>document.getElementById('pg-exchange-v1');
  function tickNow(){return Math.floor(Date.now()/1000);}
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=(s,price=false)=>{const n=Number(s);if(!Number.isFinite(n))return '—';if(n!==0&&Math.abs(n)<.01&&!price)return n<0?'− меньше 0,01':'меньше 0,01';return n.toLocaleString('ru-RU',{maximumFractionDigits:price?8:2});};
  // Confirmation amounts are canonical server decimals: preserve all six
  // ledger places without floating-point rounding, including tiny commissions.
  const exactMoney=s=>{const value=String(s??'0');if(!/^-?\d+(?:\.\d{1,6})?$/.test(value))return '—';const [whole,fraction='']=value.split('.'),tail=fraction.replace(/0+$/,'');return whole.replace(/\B(?=(\d{3})+(?!\d))/g,'\u00a0')+(tail?','+tail:'');};
  const signed=s=>(Number(s)>0?'+':'')+num(s);
  // Portfolio valuation only: never round server decimals through binary float.
  function sumMoney(values){
    let total=0n;
    for(const raw of values){const value=String(raw);if(!/^-?\d+(?:\.\d{1,6})?$/.test(value))return null;const negative=value.startsWith('-'),[whole,part='']=value.replace(/^-/,'').split('.');const amount=BigInt(whole)*1000000n+BigInt(part.padEnd(6,'0'));total+=negative?-amount:amount;}
    const sign=total<0n?'-':'';if(total<0n)total=-total;
    return sign+String(total/1000000n)+'.'+String(total%1000000n).padStart(6,'0');
  }
  function overviewMoney(value){
    const [whole,part='']=String(value).split('.');
    const cents=(BigInt(whole)*1000000n+BigInt(part.padEnd(6,'0'))+5000n)/10000n;
    return exactMoney(String(cents/100n)+'.'+String(cents%100n).padStart(2,'0'));
  }
  const haptic=kind=>{if(typeof _haptic==='function')try{_haptic(kind);}catch(_){}};

  const CHAR={calm:'Штиль',flow:'Течение',storm:'Шторм',tide:'Прилив'};
  const CHAR_HINT={calm:'Обычно небольшие колебания и более долгие движения.',
    flow:'Умеренные колебания с чередованием направлений.',
    storm:'Более резкие колебания и частые развороты.',
    tide:'Движения могут идти дольше; иногда случаются резкие скачки.'};
  const GROUP={'sky':'Небо','earth':'Земля','horizon':'Горизонт'};
  const groupLabel=c=>c.personal?'Личные':(GROUP[c.group]||'Рынок');
  const ICON={
    coin:'<svg aria-hidden="true" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="16" cy="16" r="12"/><circle cx="16" cy="16" r="6.5"/></svg>',
    star:'<svg aria-hidden="true" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M16 4l3.6 7.6 8 .9-6 5.7 1.6 8L16 22.2 8.8 26.2l1.6-8-6-5.7 8-.9z"/></svg>',
    wave:'<svg aria-hidden="true" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 19c3-6 6-6 9 0s6 6 9 0 6-6 6 0M4 12c3-6 6-6 9 0"/></svg>',
    leaf:'<svg aria-hidden="true" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M26 6C14 6 6 13 6 22c0 2 .5 3.5 1 4 5-11 12-14 19-20z"/><path d="M10 22c6-1 10-4 12-9"/></svg>'};
  // Six original emblems; personal coins retain the owner's chosen icon.
  const SYSTEM_ART = {
    orb:'<ellipse cx="16" cy="16" rx="12" ry="5.5" transform="rotate(-35 16 16)"/><circle cx="16" cy="16" r="4" fill="currentColor" stroke="none"/><circle cx="25.8" cy="9.2" r="2" fill="currentColor" stroke="none"/>',
    isk:'<path d="M18 3L7 18h8l-1 11 11-16h-8z" fill="currentColor" fill-opacity=".18"/><path d="M6 7l2 2M25 23l2 2M26 5l-2 3"/>',
    ine:'<path d="M16 3v26M4.7 9.5l22.6 13M4.7 22.5l22.6-13M12 6l4 4 4-4M12 26l4-4 4 4M5 14l5-1-1-5M23 24l-1-5 5-1M5 18l5 1-1 5M23 8l-1 5 5 1"/>',
    veg:'<path d="M16 3l3.4 9.6L29 16l-9.6 3.4L16 29l-3.4-9.6L3 16l9.6-3.4z" fill="currentColor" fill-opacity=".16"/><circle cx="16" cy="16" r="2.4" fill="currentColor" stroke="none"/>',
    may:'<path d="M11 26l2-14h6l2 14M10 26h12M12 8h8v4h-8zM14 5h4l2 3h-8zM16 16v3M4 7l5 2M28 7l-5 2M3 15l6-3M29 15l-6-3"/><path d="M12 22h8"/>',
    rif:'<path d="M16 28V12M16 21l-7-5v-6M9 16l-5-3V7M16 16l7-5V5M23 11l5-3M16 25l9-5v-4M9 11l4-4M6 28h20"/><circle cx="16" cy="9" r="2" fill="currentColor" stroke="none"/>'
  };
  const icon=c=>!c.personal && SYSTEM_ART[c.id]
    ? `<svg class="cm2-emblem cm2-emblem-${c.id}" aria-hidden="true" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${SYSTEM_ART[c.id]}</svg>`
    : ICON[c.icon] || ICON.coin;

  const pendingKey=()=>data?'cm2_pending_'+data.user_id:null;
  function pending(){try{return JSON.parse(localStorage.getItem(pendingKey())||'null');}catch(_){return null;}}
  function store(p){try{if(p)localStorage.setItem(pendingKey(),JSON.stringify(p));else localStorage.removeItem(pendingKey());return true;}catch(_){return false;}}

  function stopLive(){if(live.timer)clearInterval(live.timer);if(live.clock)clearInterval(live.clock);if(live.expiry)clearInterval(live.expiry);live.timer=live.clock=live.expiry=null;}

  async function request(path, body, method){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
    try{
      const headers=new Headers(typeof hdrs==='function'?hdrs():{});
      headers.set('Content-Type','application/json');
      const response=await fetch(BASE+'/coin-market/v2'+path,{method:method||(body?'POST':'GET'),headers,body:body?JSON.stringify(body):undefined,signal:controller.signal});
      const payload=await response.json();
      if(!response.ok){const d=payload.detail;const error=new Error(typeof d==='string'?d:d?.message||'Не удалось выполнить запрос.');error.status=response.status;error.code=d?.code;throw error;}
      return payload;
    }finally{clearTimeout(timer);}
  }
  function head(title, back='CM2.home()'){return typeof v3Head==='function'?v3Head(title,{back}):`<header class="cm2-head"><button class="cm2-plain" onclick="${back}">Назад</button><h1>${escape(title)}</h1></header>`;}
  function paint(html, focus=true){formRevision++;draft=null;const host=root();if(!host)return;host.innerHTML=`<section class="cm2">${html}<p id="cm2-message" class="cm2-status" role="status" aria-live="polite"></p></section>`;if(focus){const h=host.querySelector('h1');if(h){h.tabIndex=-1;h.focus({preventScroll:true});}}}
  function message(text, error=false){const host=document.getElementById('cm2-message');if(host){host.textContent=text;host.classList.toggle('cm2-error',error);}}

  function invalidate(){formRevision++;draft=null;const preview=document.getElementById('cm2-preview');if(preview)preview.innerHTML='';const button=document.getElementById('cm2-check');if(button){button.className='cm2-primary';button.disabled=false;button.textContent=view==='create'?'Показать итог':'Проверить условия';}}
  function quoteButton(loading, ready=false){const button=document.getElementById('cm2-check');if(!button)return;button.disabled=loading;button.className=ready?'cm2-plain cm2-recheck':'cm2-primary';button.textContent=loading?'Рассчитываем…':ready?'Пересчитать':view==='create'?'Показать итог':'Проверить условия';}

  async function preview(side, position){
    if(busy)return;busy=true;invalidate();quoteButton(true);
    const revision=formRevision,screen=view,coinId=selected?.id,previewHost=document.getElementById('cm2-preview');
    const current=()=>revision===formRevision&&screen===view&&coinId===selected?.id&&previewHost===document.getElementById('cm2-preview');
    try{const amount=document.getElementById('cm2-amount')?.value.replace(',','.')||'0',raw=document.getElementById('cm2-units')?.value.replace(',','.');if(raw&&!/^\d+(\.\d{1,3})?$/.test(raw))throw Error('Количество монет — до трёх знаков после запятой.');
      const body={coin_id:selected.id,side,amount,units:raw?Math.round(Number(raw)*1000):0,position_id:position||null};
      const q=await request('/quote',body);if(!current())return;draft={path:'/trade',body:{...body,action_id:crypto.randomUUID(),tick:q.tick,price:q.price}};
      document.getElementById('cm2-preview').innerHTML=`<div class="cm2-ticket"><span class="cm2-eyebrow">Итог до подтверждения</span><h2 class="cm2-focus">${q.spent?'Спишется '+exactMoney(q.spent):'Получите '+exactMoney(q.received)} Моры</h2><dl class="cm2-metrics"><dt>Комиссия</dt><dd>${exactMoney(q.commission)} Моры</dd>${q.received_units?`<dt>Монет</dt><dd>${num(Number(q.received_units)/1000,true)}</dd>`:''}${q.sold_units?`<dt>Продаёте</dt><dd>${num(Number(q.sold_units)/1000,true)} монет</dd>`:''}${q.liquidation_price?`<dt>Цена принудительного закрытия</dt><dd>${num(q.liquidation_price,true)} Моры</dd><dt>Максимальная потеря</dt><dd>${exactMoney(q.max_loss)} Моры</dd>`:''}${q.penalty&&Number(q.penalty)>0?`<dt>Штраф за закрытие</dt><dd>${exactMoney(q.penalty)} Моры</dd>`:''}</dl>${q.zero_payout?'<p class="cm2-dim">Получите 0 Моры — выбранный остаток закроется без выплаты. Мора из кошелька не списывается.</p>':''}<button class="cm2-primary ${side==='sell'?'cm2-danger':''}" onclick="CM2.confirm()">${q.zero_payout?'Продать за 0 Моры':'Подтвердить'}</button><p class="cm2-dim cm2-expiry" id="cm2-expiry"></p></div>`;
      startExpiry(q.expires_at);quoteButton(false,true);message('');
    }catch(e){if(current()){quoteButton(false);message(e.message,true);}}finally{busy=false;}
  }
  function startExpiry(expiresAt){
    const host=document.getElementById('cm2-expiry');if(!host)return;clearInterval(live.expiry);live.expiry=null;
    if(!expiresAt){host.textContent='Котировка может обновиться в любой момент.';return;}
    const render=()=>{const left=expiresAt-tickNow();host.textContent=left>0?'Котировка действует ещё '+String(Math.floor(left/60)).padStart(2,'0')+':'+String(left%60).padStart(2,'0'):'Котировка может обновиться в любой момент.';};
    render();live.expiry=setInterval(()=>{if(document.hidden||!document.getElementById('cm2-expiry')){clearInterval(live.expiry);live.expiry=null;return;}render();},1000);
  }

  function create(){
    if(pending()){showPending();return;}stopLive();view='create';draft=null;
    const z=[[1000,'1 000','Базовая'],[2500,'2 500','Цена +7,5%'],[5000,'5 000','Цена +20%']].map(([v,l,hint])=>`<button class="cm2-plain" aria-pressed="${v===1000}" data-z="${v}" onclick="CM2.zarniki(${v})"><strong>${l}</strong><small>${hint}</small></button>`).join('');
    const icons=Object.keys(ICON).map(k=>`<button class="cm2-icon-pick" aria-pressed="${k==='coin'}" data-icon="${k}" aria-label="${({coin:"Монета",star:"Звезда",wave:"Волна",leaf:"Лист"})[k]}" onclick="CM2.icon('${k}')">${ICON[k]}</button>`).join('');
    paint(head('Своя монета')+'<p class="cm2-lead">Ваша монета на общем рынке. Все расходы — до подтверждения.</p><h2 class="cm2-h2">Оформление</h2>'+
      `<div class="cm2-field"><label for="cm2-name">Название</label><input id="cm2-name" maxlength="24" placeholder="3–24 символа" autocomplete="off" oninput="CM2.invalidate()"></div>`+
      `<div class="cm2-field"><span class="cm2-label">Значок</span><div class="cm2-icons" role="group" aria-label="Значок монеты">${icons}</div><input type="hidden" id="cm2-icon" value="coin"></div>`+
      `<div class="cm2-field"><label for="cm2-desc">Описание <span class="cm2-dim">· необязательно</span></label><input id="cm2-desc" maxlength="160" placeholder="Одна короткая строка" autocomplete="off" oninput="CM2.invalidate()"></div>`+
      `<h2 class="cm2-h2">Создание и обеспечение</h2><div class="cm2-field"><span class="cm2-label">Зарников на создание</span><div class="cm2-presets cm2-segment" role="group" aria-label="Стоимость создания">${z}</div><input type="hidden" id="cm2-z" value="1000"><p class="cm2-dim">Зарники влияют на стартовую цену, а не на будущую доходность.</p></div>`+
      `<div class="cm2-field"><label for="cm2-deposit">Вклад в монету, Моры</label><input id="cm2-deposit" inputmode="decimal" value="1000" oninput="CM2.invalidate()"><p class="cm2-dim">От 1 000 до 100 000 Моры. Вклад становится обеспечением монеты.</p></div>`+
      `<label class="cm2-check"><input type="checkbox" id="cm2-gems" onchange="CM2.invalidate()"><span>Внести алмазами <span class="cm2-dim">· 1 алмаз = 1 000 Моры</span></span></label>`+
      '<button id="cm2-check" class="cm2-primary" onclick="CM2.createPreview()">Показать итог</button><div id="cm2-preview"></div>');
  }
  async function createPreview(){
    if(busy)return;busy=true;invalidate();quoteButton(true);
    const revision=formRevision,screen=view,coinId=selected?.id,previewHost=document.getElementById('cm2-preview');
    const current=()=>revision===formRevision&&screen===view&&coinId===selected?.id&&previewHost===document.getElementById('cm2-preview');
    try{const icon=document.getElementById('cm2-icon')?.value||'coin',description=document.getElementById('cm2-desc')?.value||'';
      const body={name:document.getElementById('cm2-name').value,zarniki:Number(document.getElementById('cm2-z')?.value||1000),deposit:document.getElementById('cm2-deposit').value.replace(',','.'),diamonds:document.getElementById('cm2-gems').checked,icon,description,action_id:crypto.randomUUID()};
      const q=await request('/create-quote',body);if(!current())return;draft={path:'/create',body};
      document.getElementById('cm2-preview').innerHTML=`<div class="cm2-ticket"><span class="cm2-eyebrow">Итог до подтверждения</span><h2 class="cm2-focus">${escape(q.name)}</h2><dl class="cm2-metrics"><dt>Создание</dt><dd>${num(q.zarniki)} Зарников</dd><dt>Вклад</dt><dd>${q.diamonds?num(Number(q.deposit)/1000,true)+' алм.':exactMoney(q.deposit)+' Моры'}</dd><dt>Стартовая цена</dt><dd>${num(q.price,true)} Моры</dd><dt>Ваша доля</dt><dd>${num(Number(q.creator_units)/1000)} монет · 20%</dd></dl><p class="cm2-dim">Забрать резерв напрямую нельзя. Свою долю можно продать по текущему курсу.</p><button class="cm2-primary" onclick="CM2.confirm()">Создать с этими условиями</button></div>`;quoteButton(false,true);}catch(e){if(current()){quoteButton(false);message(e.message,true);}}finally{busy=false;}
  }
  async function confirm(){
    if(busy||!draft)return;if(pending()){showPending();return;}
    if(!store(draft)){message('Не удалось сохранить запрос для восстановления. Разрешите локальное хранилище.',true);return;}
    await sendPending();
  }

  /* ── экраны ─────────────────────────────────────────────────────────────── */

  async function load(visit=true){
    stopLive();paint(head('Биржа','navBack()')+'<p class="cm2-loading" role="status">Загрузка рынка…</p>');
    try{data=await request('/me'+(visit?'?visit=true':''));view='home';renderHome();if(pending())showPending();}
    catch(e){paint(head('Биржа','navBack()')+`<div class="cm2-empty-block"><p>${escape(e.status===503?e.message:'Не удалось открыть рынок.')}</p><button class="cm2-primary" onclick="CM2.load()">Попробовать снова</button></div>`);message(e.message,e.status!==503);}
  }
  async function refreshMarket(){
    if(marketRefreshing||view!=='home')return;marketRefreshing=true;
    const revision=formRevision,button=document.getElementById('cm2-refresh');
    const current=()=>view==='home'&&revision===formRevision;
    if(button){button.disabled=true;button.textContent='Обновляем…';}
    try{const fresh=await request('/me');if(!current())return;
      const active=document.activeElement,activeId=active?.id,start=active?.selectionStart,end=active?.selectionEnd;
      data=fresh;renderHome(false);
      const restored=activeId?document.getElementById(activeId):null;
      if(restored){restored.focus({preventScroll:true});if(typeof start==='number'&&restored.setSelectionRange)restored.setSelectionRange(start,end);}
      message('Курсы и позиции обновлены.');}
    catch(e){if(current())message(e.message,true);}
    finally{marketRefreshing=false;if(current()&&button){button.disabled=false;button.textContent='Обновить';}}
  }
  function renderHome(focus=true){
    stopLive();view='home';draft=null;
    const mine=tab==='mine';
    const coins=data.coins.filter(c=>!mine||Number(c.units)>0||c.owned);
    const visible=coins.filter(c=>group==='all'||(group==='personal'?c.personal:c.group===group))
      .filter(c=>(c.name+' '+c.ticker).toLowerCase().includes(search.toLowerCase()));
    const chips=[['all','Все'],['sky','Небо'],['earth','Земля'],['horizon','Горизонт'],['personal','Личные']]
      .map(([key,label])=>`<button class="cm2-chip" aria-pressed="${group===key}" onclick="CM2.group('${key}')">${label}</button>`).join('');
    const shorts=mine?data.shorts.map(p=>{const c=data.coins.find(x=>x.id===p.coin_id);return `<div class="cm2-rowwrap"><button class="cm2-row" onclick="CM2.closeShort('${p.id}')"><span class="cm2-ava cm2-ico-drop"><svg aria-hidden="true" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M16 5v14m0 0l-5-5m5 5l5-5M8 26h16"/></svg></span><span class="cm2-name"><strong>${escape(c?.name||'Монета')}</strong><small>На падение · выделено ${num(p.collateral)} Моры</small></span><span class="cm2-end"><span class="cm2-change ${Number(p.result)>=0?'up':'down'}">${signed(p.result)} Моры</span></span></button></div>`;}).join(''):'';
    const body=visible.slice(0,limit).map(coinRow).join('');
    const empty=mine?'<div class="cm2-empty-block"><p>Здесь появятся купленные монеты и позиции на падение.</p><button class="cm2-plain" onclick="CM2.tab(\'market\')">Перейти на рынок</button></div>':'<div class="cm2-empty-block"><p>Монеты не найдены.</p></div>';
    paint(head('Биржа','navBack()')+
      walletSummary()+
      `<div class="cm2-tabs" role="tablist" aria-label="Раздел биржи"><button role="tab" aria-selected="${tab==='market'}" onclick="CM2.tab('market')">Рынок</button><button role="tab" aria-selected="${tab==='mine'}" onclick="CM2.tab('mine')">Мои позиции</button></div>`+
      (mine?portfolioSummary():marketSummary())+
      (mine?ordersPanel():'')+
      (data.news.length&&tab==='market'?`<h2 class="cm2-h2">Пока вас не было</h2><ul class="cm2-news">${data.news.map(n=>`<li>${n.coin_id?`<button onclick="CM2.coin('${n.coin_id}')"><span>${escape(n.text)}</span><span aria-hidden="true">›</span></button>`:`<p>${escape(n.text)}</p>`}</li>`).join('')}</ul>`:'')+
      (tab==='market'?`<div class="cm2-toolbar"><label class="sr-only" for="cm2-search">Найти монету</label><input id="cm2-search" type="search" value="${escape(search)}" placeholder="Найти монету" oninput="CM2.search(this.value)" autocomplete="off"></div><div class="cm2-chips" role="group" aria-label="Группы монет">${chips}</div>`:'')+
      (mine&&coins.some(c=>c.owned)?'<p class="cm2-note cm2-dim">Расходы на создание своей монеты в результате не учтены.</p>':'')+
      `<div id="cm2-list" class="cm2-list">${mine&&body?'<h2 class="cm2-h2">Монеты</h2>':''}${body}${shorts?'<h2 class="cm2-h2">На падение</h2>':''}${shorts}${body||shorts?'':empty}</div>`+
      (visible.length>limit?'<button class="cm2-plain cm2-more" onclick="CM2.more()">Показать ещё</button>':'')+
      (data.enabled?'<div class="cm2-actions cm2-create-line"><button class="cm2-plain" onclick="CM2.create()">Создать свою монету</button></div>':'<p class="cm2-dim">Новые сделки закрыты. Ваши позиции можно закрыть.</p>')+
      '<details class="cm2-help"><summary>Как работает биржа</summary><p>Курс меняет сервер по своему расписанию. Покупки игроков на него не влияют. Комиссия — 0,5% при покупке и продаже; чистый результат уже учитывает выход.</p><p>Позиция «на падение»: вы выделяете сумму, потерять можно только её. Если цены пойдут против позиции, сервер закроет её заранее. Остальной кошелёк не затрагивается.</p><button class="cm2-help-link" onclick="loadPlayerExchangeV1(true)">Проверить состояние прежней биржи</button></details>',focus);
  }
  function walletSummary(){
    const balance=data.balances,reserved=Number(balance.mora_reserved||0)>0;
    return `<div class="cm2-marketbar"><div class="cm2-wallet"><span class="cm2-eyebrow">В кошельке · Мора</span><strong class="cm2-wallet-sum">${num(balance.mora_total??balance.mora)}</strong></div><button id="cm2-refresh" class="cm2-plain" onclick="CM2.refreshMarket()">Обновить</button>${reserved?`<dl class="cm2-wallet-split"><div><dt>Для торговли</dt><dd>${num(balance.mora)}</dd></div><div><dt>В резерве</dt><dd>${num(balance.mora_reserved)}</dd></div></dl><p class="cm2-wallet-note">Зарезервированные средства недоступны для новых сделок.</p>`:''}</div>`;
  }
  function marketSummary(){
    const rising=data.coins.filter(c=>Number(c.change_24h)>0).length,falling=data.coins.filter(c=>Number(c.change_24h)<0).length;
    return `<div class="cm2-market-pulse" aria-label="Изменения монет за указанный у каждой монеты период"><span><i class="cm2-pulse-dot" aria-hidden="true"></i>${data.coins.length} монет на рынке</span><span class="cm2-up">↑ ${rising}</span><span class="cm2-down">↓ ${falling}</span></div>`;
  }
  function portfolioSummary(){
    const coins=data.coins.filter(c=>Number(c.units)>0),long=sumMoney(coins.map(c=>c.sell_value)),short=sumMoney(data.shorts.map(p=>p.received));
    if(!coins.length&&!data.shorts.length)return '';
    if(long===null||short===null)return '';
    const total=sumMoney([long,short]);
    return `<div class="cm2-portfolio"><span class="cm2-eyebrow">Оценка позиций · Мора</span><strong class="cm2-portfolio-value">≈ ${overviewMoney(total)}</strong><div class="cm2-portfolio-split"><div><span>Монеты · ${coins.length}</span><strong>${overviewMoney(long)}</strong></div><div><span>На падение · ${data.shorts.length}</span><strong>${overviewMoney(short)}</strong></div></div><p>После комиссии выхода. Шорты включают возвращаемое обеспечение.</p></div>`;
  }
  function coinRow(c){
    const up=Number(c.change_24h)>=0;
    const mine=tab==='mine';
    return `<div class="cm2-rowwrap"><button class="cm2-row" onclick="CM2.coin('${c.id}')"><span class="cm2-ava">${icon(c)}</span><span class="cm2-name"><strong>${escape(c.name)}</strong><small>${mine?num(Number(c.units)/1000,true)+' монет':escape(c.ticker)+' · '+groupLabel(c)}${c.owned?' · ваша':''}</small></span><span class="cm2-end"><strong>${mine?num(c.sell_value)+' Моры':num(c.price,true)}</strong><span class="cm2-change ${(mine?Number(c.result)>=0:up)?'up':'down'}">${mine?'Результат '+signed(c.result):`${up?'▲':'▼'} ${num(Math.abs(c.change_24h))}% · ${escape(c.change_period)}`}</span></span></button><button class="cm2-star" aria-pressed="${c.favorite}" aria-label="${c.favorite?'Убрать из избранного':'В избранное'}" onclick="CM2.star('${c.id}')">${ICON.star}</button></div>`;
  }

  async function coin(id){
    stopLive();selected=data.coins.find(c=>c.id===id);if(!selected)return CM2.home();
    view='coin';draft=null;
    paint(head(selected.name,`CM2.home()`)+coinBody(selected));
    message('');
    const requested=id,hours=period;
    try{const history=await request('/coins/'+id+'/history?hours='+period);if(view!=='coin'||selected?.id!==requested||period!==hours)return;draw(history);const last=history.points[history.points.length-1];if(selected)startLive(requested,last?last.tick:0);if(last&&last.tick!==selected.tick)refreshCoin(requested);}
    catch(e){if(view!=='coin'||selected?.id!==requested||period!==hours)return;const chart=document.getElementById('cm2-chart');if(chart)chart.innerHTML='<p class="cm2-chart-empty">График временно недоступен.</p>';message(e.message,true);}
  }
  function coinBody(c){
    const own=Number(c.units)>0;
    return `<p class="cm2-dim cm2-sub">${escape(c.ticker)} · ${c.personal?'Монета игрока':'Системная монета'} · ${CHAR[c.character]||''}</p>`+
      `<div class="cm2-quote"><strong class="cm2-price" id="cm2-price" tabindex="-1">${num(c.price,true)}</strong><small>Моры за монету</small><span class="cm2-change ${Number(c.change_24h)>=0?'up':'down'}" id="cm2-change">${Number(c.change_24h)>=0?'▲':'▼'} ${num(Math.abs(c.change_24h))}% · ${escape(c.change_period)}</span></div>`+
      `<div class="cm2-chart-card"><div class="cm2-chart-head"><div class="cm2-period" role="group" aria-label="Период графика">${[[1,'1 ч'],[24,'24 ч'],[168,'7 д']].map(([h,l])=>`<button class="cm2-plain" data-period="${h}" aria-pressed="${period===h}" onclick="CM2.period(${h})">${l}</button>`).join('')}</div><span class="cm2-live" id="cm2-live" role="status" aria-live="off"></span></div><div id="cm2-chart" class="cm2-chart" role="group" aria-label="График курса">Загрузка графика…</div><p class="cm2-dim cm2-stamp" id="cm2-stamp"></p></div>`+
      `<div id="cm2-position">${positionCard(c)}${shortCard(c)}</div>`+
      coinActions(c)+ordersPanel(c.id)+
      (c.description?`<p class="cm2-desc">${escape(c.description)}</p>`:'')+
      (c.owned?`<details class="cm2-help"><summary>Оформление моей монеты</summary><div class="cm2-field"><label for="cm2-edit-desc">Описание</label><input id="cm2-edit-desc" maxlength="160" value="${escape(c.description||'')}"></div><button class="cm2-plain" onclick="CM2.saveMetadata()">Сохранить</button></details>`:'')+
      `<details class="cm2-help"><summary>Характер монеты</summary><p>${CHAR_HINT[c.character]||'Серверный курс.'}</p><p>Курс может вырасти или упасть. Характер не является прогнозом. Новая покупка может быть ограничена запасом фонда; существующие остатки обеспечены для продажи.</p></details>`;
  }
  function coinActions(c){const own=Number(c.units)>0;
    return `<div id="cm2-coin-actions"><div class="cm2-actions cm2-trade-actions">${data.enabled?`<button class="cm2-primary" onclick="CM2.deal('buy')">Купить</button>`:''}${own?`<button class="cm2-plain cm2-danger" onclick="CM2.deal('sell')">Продать</button>`:''}</div><div class="cm2-actions cm2-secondary-actions">${data.shorts_enabled&&!data.shorts.some(p=>p.coin_id===c.id)?`<button class="cm2-plain" onclick="CM2.deal('short')">На падение</button>`:''}${data.vip_orders&&data.enabled?`<button class="cm2-plain" onclick="CM2.orderForm()">Автозаявка · VIP</button>`:''}<button class="cm2-plain cm2-favorite" aria-pressed="${c.favorite}" onclick="CM2.favorite()">${ICON.star}<span>Избранное</span></button></div></div>`;
  }

  const ORDER_STATUS={pending:'Ожидает',filled:'Исполнена',cancelled:'Отменена',failed:'Не выполнена',expired:'Срок истёк'};
  function ordersPanel(coinId){
    const list=(data.orders||[]).filter(o=>!coinId||o.coin_id===coinId);
    if(!list.length)return '';
    const row=o=>{
      const c=data.coins.find(c=>c.id===o.coin_id);
      return `<article class="cm2-order"><div><strong>${o.side==='buy'?'Купить':'Продать'} · ${escape(c?.ticker||'Монета')}</strong><span class="cm2-order-status">${ORDER_STATUS[o.status]||''}</span></div>
        <p>Цена ${o.direction==='below'?'≤':'≥'} ${exactMoney(o.threshold)} Моры · ${o.side==='buy'?exactMoney(o.amount)+' Моры':num(Number(o.units)/1000,true)+' монет'}</p>
        ${o.status==='pending'?`<small>До ${new Date(o.expires_at*1000).toLocaleDateString('ru-RU')}</small><button class="cm2-plain" onclick="CM2.cancelOrder('${o.id}')">Отменить</button>`:
          `<small>${escape(o.result?.message||(o.result?.price?'Цена исполнения: '+exactMoney(o.result.price)+' Моры':''))}</small>`}</article>`;
    };
    const active=list.filter(o=>o.status==='pending'),past=list.filter(o=>o.status!=='pending');
    return `<section class="cm2-orders"><h2 class="cm2-h2">Автозаявки${active.length?' · '+active.length:''}</h2>${!data.enabled?'<p class="cm2-dim">Автосделки на паузе, пока биржа закрыта для новых сделок. Срок заявок продолжает идти.</p>':''}
      ${active.map(row).join('')}${past.length?`<details class="cm2-help"><summary>Последние завершённые · ${Math.min(10,past.length)}</summary>${past.slice(0,10).map(row).join('')}</details>`:''}</section>`;
  }
  function orderForm(){
    if(pending()){showPending();return;}if(!data.vip_orders||!data.enabled)return;
    stopLive();view='order';const c=selected;
    paint(head('Автозаявка · VIP',`CM2.coin('${c.id}')`)+`<p class="cm2-lead">${escape(c.name)} · сейчас ${exactMoney(c.price)} Моры</p>
      <div class="cm2-field"><label for="cm2-order-side">Действие</label><select id="cm2-order-side" onchange="CM2.orderSide()"><option value="buy">Купить</option>${Number(c.units)>0?'<option value="sell">Продать</option>':''}</select></div>
      <div class="cm2-field"><label for="cm2-order-direction">Когда цена</label><select id="cm2-order-direction" onchange="CM2.invalidate()"><option value="below">Опустится до порога или ниже</option><option value="above">Поднимется до порога или выше</option></select></div>
      <div class="cm2-field"><label for="cm2-order-price">Порог, Моры за монету</label><input id="cm2-order-price" inputmode="decimal" placeholder="Укажите цену" oninput="CM2.invalidate()"></div>
      <div class="cm2-field"><label id="cm2-order-label" for="cm2-order-value">Бюджет покупки, Моры</label><input id="cm2-order-value" inputmode="decimal" oninput="CM2.invalidate()"></div>
      <p class="cm2-note">Работает на сервере при закрытом приложении. До 10 заявок, срок — 30 дней. Нужен действующий VIP при исполнении.</p>
      <p class="cm2-dim">Средства и монеты не резервируются. Если их не хватит, заявка завершится без сделки. Комиссия — обычные 0,5%. Цена исполнения может пройти дальше порога.</p>
      <button id="cm2-check" class="cm2-primary" onclick="CM2.orderPreview()">Проверить заявку</button><div id="cm2-preview"></div>`);
  }
  function orderSide(){
    const sell=document.getElementById('cm2-order-side').value==='sell';
    document.getElementById('cm2-order-label').textContent=sell?'Количество монет · доступно '+num(Number(selected.units)/1000,true):'Бюджет покупки, Моры';
    document.getElementById('cm2-order-value').value='';invalidate();
  }
  function orderPreview(){
    const side=document.getElementById('cm2-order-side').value,direction=document.getElementById('cm2-order-direction').value;
    const threshold=document.getElementById('cm2-order-price').value.trim().replace(',','.'),value=document.getElementById('cm2-order-value').value.trim().replace(',','.');
    if(!/^\d{1,12}(?:\.\d{1,6})?$/.test(threshold)||Number(threshold)<=0||!/^\d{1,12}(?:\.\d{1,6})?$/.test(value)||Number(value)<=0){message('Укажите положительный порог и сумму.',true);return;}
    if(side==='buy'&&Number(value)<10){message('Минимальный бюджет — 10 Моры.',true);return;}
    if(side==='sell'&&(!/^\d+(?:\.\d{1,3})?$/.test(value)||Math.round(Number(value)*1000)>Number(selected.units))){message('Количество — до трёх знаков после запятой, в пределах ваших монет.',true);return;}
    draft={path:'/orders',body:{coin_id:selected.id,side,direction,threshold,amount:side==='buy'?value:'0',units:side==='sell'?Math.round(Number(value)*1000):0,action_id:crypto.randomUUID()}};
    document.getElementById('cm2-preview').innerHTML=`<div class="cm2-ticket"><span class="cm2-eyebrow">Условие заявки</span><h2>${side==='buy'?'Купить':'Продать'} при цене ${direction==='below'?'≤':'≥'} ${exactMoney(threshold)}</h2><p>${side==='buy'?'Бюджет: '+exactMoney(value)+' Моры':'Количество: '+num(value,true)+' монет'}</p><p class="cm2-dim">Исполнение по серверному курсу, без гарантии точной цены порога. При нехватке средств сделка не состоится.</p><button class="cm2-primary" onclick="CM2.confirm()">Создать автозаявку</button></div>`;
  }
  async function cancelOrder(id){
    if(busy)return;if(pending()){showPending();return;}busy=true;const revision=formRevision;
    try{
      const r=await request('/orders/'+id+'/cancel',{});
      const order=(data.orders||[]).find(o=>o.id===id);if(order){order.status=r.status;order.result=r.result||{};}
      let fresh=true;try{data=await request('/me');}catch(_){fresh=false;}
      if(revision===formRevision){renderHome();message((r.status==='cancelled'?'Заявка отменена.':'Заявка уже завершена: '+(ORDER_STATUS[r.status]||''))+(!fresh?' Обновите рынок для свежих данных.':''));}
    }catch(e){if(revision===formRevision)message(e.message,true);}finally{busy=false;}
  }

  function positionCard(c){
    if(Number(c.units)<=0)return '';
    return `<div class="cm2-pos"><h2 class="cm2-h2">Мой остаток</h2><dl class="cm2-metrics"><dt>Монет</dt><dd>${num(Number(c.units)/1000,true)}</dd><dt>Покупки</dt><dd>${num(c.cost)} Моры</dd><dt>При продаже получите</dt><dd>${num(c.sell_value)} Моры</dd><dt>Результат позиции</dt><dd class="${Number(c.result)>=0?'cm2-up':'cm2-down'}">${signed(c.result)} Моры</dd></dl>${c.owned?'<p class="cm2-dim cm2-note">Расходы на создание монеты здесь не учтены.</p>':''}</div>`;
  }
  function shortCard(c){
    const p=data.shorts.find(x=>x.coin_id===c.id);if(!p)return '';
    return `<div class="cm2-short-card"><div class="cm2-position-title"><h2 class="cm2-h2">На падение</h2><strong class="${Number(p.result)>=0?'cm2-up':'cm2-down'}">${signed(p.result)} Моры</strong></div><dl class="cm2-metrics"><dt>Выделено</dt><dd>${num(p.collateral)} Моры</dd><dt>При закрытии</dt><dd>${num(p.received)} Моры</dd><dt>Цена принудительного закрытия</dt><dd>${num(p.liquidation_price,true)} Моры</dd></dl><button class="cm2-plain" onclick="CM2.closeShort('${p.id}')">Закрыть позицию</button></div>`;
  }
  function draw(history){
    const chart=document.getElementById('cm2-chart');
    const points=history.points||[];
    if(chart&&window.CM2Chart){window.CM2Chart.render(chart,points,{hours:period,tickSeconds:data.tick_seconds||300,cost:history.cost,markers:history.markers||[]});}
    const stamp=document.getElementById('cm2-stamp');
    const last=points[points.length-1];
    if(stamp)stamp.textContent=last?'Последнее значение: '+new Date(last.tick*(data.tick_seconds||300)*1000).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}):'';
  }

  function deal(side, position, initial){
    if(pending()){showPending();return;}stopLive();draft=null;
    const c=position?data.coins.find(x=>x.id===position.coin_id):selected;if(!c)return CM2.home();selected=c;view='deal';
    const title={buy:'Купить',sell:'Продать',short:'На падение',close_short:'Закрыть позицию'}[side];
    const amountValue=initial?.amount??'10',unitsValue=initial?.units!=null?String(initial.units/1000):String(Number(c.units)/1000);
    paint(head(title,`CM2.coin('${c.id}')`)+`<p class="cm2-dim cm2-sub">${escape(c.name)} · ${num(c.price,true)} Моры</p>`+
      (side==='buy'?`<div class="cm2-field"><label for="cm2-amount">Сколько потратить, Моры</label><input id="cm2-amount" type="text" inputmode="decimal" value="${escape(amountValue)}" oninput="CM2.invalidate()"><p class="cm2-dim">Минимум 10 Моры. Комиссия войдёт в сумму.</p></div><div class="cm2-presets">${[10,50,100].map(n=>`<button class="cm2-plain" onclick="CM2.amount('${n}')">${n}</button>`).join('')}</div>`:'')+
      (side==='sell'?`<div class="cm2-field"><label for="cm2-units">Продать монет</label><input id="cm2-units" inputmode="decimal" value="${escape(unitsValue)}" oninput="CM2.invalidate()"><p class="cm2-dim">Ваш остаток: ${num(Number(c.units)/1000,true)} монет.</p></div><div class="cm2-presets">${[25,50,100].map(n=>`<button class="cm2-plain" onclick="CM2.fraction(${n})">${n}%</button>`).join('')}</div>`:'')+
      (side==='short'?`<div class="cm2-field"><label for="cm2-amount">Выделить для позиции, Моры</label><input id="cm2-amount" type="text" inputmode="decimal" value="${escape(amountValue)}" oninput="CM2.invalidate()"><p class="cm2-dim">Потерять можно только выделенную сумму. При нехватке обеспечения позиция закроется сама.</p></div><div class="cm2-presets">${[10,50,100].map(n=>`<button class="cm2-plain" onclick="CM2.amount('${n}')">${n}</button>`).join('')}</div>`:'')+
      (position?`<dl class="cm2-metrics"><dt>Было выделено</dt><dd>${num(position.collateral)} Моры</dd><dt>Текущий результат</dt><dd>${signed(position.result)} Моры</dd></dl>`:'')+
      `<button id="cm2-check" class="cm2-primary" onclick="CM2.preview('${side}','${position?.id||''}')">Проверить условия</button><div id="cm2-preview"></div>`);
  }
  function startLive(id, lastTick){
    stopLive();live.last=lastTick||tickNow();live.next=data.next_tick_at||null;
    const chip=text=>{const host=document.getElementById('cm2-live');if(host)host.textContent=text;};
    const countdown=left=>left>0?('Новое значение через '+Math.floor(left/60)+':'+String(left%60).padStart(2,'0')):'Обновляем курс…';
    chip(live.next?countdown(live.next-tickNow()):'Курс обновляется сервером');
    live.clock=setInterval(()=>{
      if(document.hidden||!root()?.classList.contains('active')||view!=='coin'||selected?.id!==id)return;
      if(live.next){const left=live.next-tickNow();chip(countdown(left));
        if(left<=0){live.next+=data.tick_seconds||300;refreshCoin(id);}
      }
    },1000);
    live.timer=setInterval(()=>{if(!document.hidden&&root()?.classList.contains('active')&&view==='coin'&&selected?.id===id)refreshCoin(id);},20000);
  }
  async function refreshCoin(id){
    const revision=formRevision,hours=period;
    const current=()=>revision===formRevision&&view==='coin'&&selected?.id===id&&period===hours;
    try{
      const history=await request('/coins/'+id+'/history?hours='+hours);
      if(!current())return;
      const lastPoint=history.points[history.points.length-1];
      if(lastPoint&&(lastPoint.tick!==live.last||lastPoint.tick!==selected.tick)){
        const fresh=await request('/me');
        if(!current())return;data=fresh;live.last=lastPoint.tick;
        selected=data.coins.find(x=>x.id===id)||selected;
        const price=document.getElementById('cm2-price'),change=document.getElementById('cm2-change'),position=document.getElementById('cm2-position');
        if(price)price.textContent=num(selected.price,true);
        if(change){const up=Number(selected.change_24h)>=0;change.className='cm2-change '+(up?'up':'down');change.textContent=`${up?'▲':'▼'} ${num(Math.abs(selected.change_24h))}% · ${selected.change_period}`;}
        const focused=document.activeElement?.closest?.('#cm2-position button, #cm2-coin-actions button');
        const action=focused?.getAttribute('onclick');
        if(position)position.innerHTML=positionCard(selected)+shortCard(selected);
        const actions=document.getElementById('cm2-coin-actions');if(actions)actions.outerHTML=coinActions(selected);
        if(action){const target=[...document.querySelectorAll('#cm2-position button, #cm2-coin-actions button')].find(b=>b.getAttribute('onclick')===action);if(target)target.focus({preventScroll:true});else document.getElementById('cm2-price')?.focus({preventScroll:true});}
      }
      draw(history);
    }catch(_){/* живое обновление молча переживает сбой сети */}
  }

  async function complete(result){
    const saved=pending();
    if(result?.ok!==true||typeof result.coin_id!=='string'||
       (saved?.path==='/trade'&&(result.coin_id!==saved.body.coin_id||result.side!==saved.body.side))||
       (saved?.path==='/orders'&&(result.coin_id!==saved.body.coin_id||result.side!=='order'||typeof result.order_id!=='string'))){
      throw Error('Сервер не подтвердил операцию. Сохранённый запрос можно проверить повторно.');
    }
    store(null);draft=null;stopLive();
    let fresh=true;try{data=await request('/me');}catch(_){fresh=false;}
    if(typeof refreshCurrBar==='function')refreshCurrBar();
    renderHome();
    message(fresh?(result.side==='order'?'Автозаявка создана. Условие проверит сервер.':result.side==='buy'?'Монеты куплены.':result.side==='sell'?'Продажа выполнена.':result.side==='short'?'Позиция открыта.':result.coin_id&&result.name?'Монета создана.':'Операция выполнена.'):'Операция выполнена. Не удалось обновить рынок — откройте биржу заново.');
  }
  async function sendPending(){
    if(busy)return;const p=pending();if(!p)return;busy=true;showPending();message('Операция выполняется…');
    try{const r=await request(p.path,p.body);await complete(r);}
    catch(e){
      if([400,409,422].includes(e.status)){const body=p.body;store(null);draft=null;
        if(e.code==='requote'&&body?.side&&body.coin_id){await requote(body,e.message);return;}
        data=await request('/me');renderHome();message(e.message,true);
      }else{showPending();message('Не удалось подтвердить результат. Запрос сохранён; повтор не создаст вторую сделку.',true);}
    }finally{busy=false;}
  }
  async function requote(body,text){
    try{data=await request('/me');}catch(_){renderHome();message(text,true);return;}
    const coin=data.coins.find(c=>c.id===body.coin_id);
    if(!coin){renderHome();message(text,true);return;}
    selected=coin;
    const position=body.position_id?data.shorts.find(p=>p.id===body.position_id):null;
    deal(body.side,position,{amount:body.amount,units:body.units});
    message(text,true);
  }
  function showPending(){stopLive();paint(head('Проверка операции')+'<div class="cm2-empty-block"><p>Запрос сохранён. Проверим результат перед следующей сделкой.</p><button class="cm2-primary" onclick="CM2.check()">Проверить результат</button><button class="cm2-plain" onclick="CM2.retry()">Повторить этот же запрос</button></div>');}
  async function check(){if(busy)return;const p=pending();if(!p)return;busy=true;try{await complete(await request('/receipt/'+p.body.action_id));}catch(e){message(e.status===404?'Результат пока не найден. Можно повторить сохранённый запрос.':e.message,true);}finally{busy=false;}}
  async function favorite(){const c=selected,revision=formRevision;try{await request('/coins/'+c.id+'/favorite',{enabled:!c.favorite},'PUT');c.favorite=!c.favorite;if(revision===formRevision&&view==='coin'&&selected?.id===c.id)await coin(c.id);}catch(e){if(revision===formRevision)message(e.message,true);}}
  async function star(id){const c=data.coins.find(x=>x.id===id);if(!c)return;haptic('select');try{await request('/coins/'+id+'/favorite',{enabled:!c.favorite},'PUT');c.favorite=!c.favorite;renderHome();}catch(e){message(e.message,true);}}
  async function availability(){const r=await request('/availability');return r.visible;}
  async function saveMetadata(){const description=document.getElementById('cm2-edit-desc')?.value??'';busy=true;try{await request('/coins/'+selected.id+'/metadata',{icon:selected.icon,description},'PUT');selected.description=description.trim();message('Оформление сохранено.');}catch(e){message(e.message,true);}finally{busy=false;}}

  return {orderForm,orderSide,orderPreview,cancelOrder,load,refreshMarket,coin,deal,preview,confirm,create,createPreview,check,retry:sendPending,favorite,star,availability,invalidate,saveMetadata,
    home(){if(pending())showPending();else renderHome();},
    tab(t){tab=t;search='';group='all';limit=30;renderHome();},
    group(g){group=g;renderHome();},
    search(s){search=s;const list=document.getElementById('cm2-list');if(!list)return;const coins=data.coins.filter(c=>!tab||tab!=='mine'||Number(c.units)>0||c.owned).filter(c=>group==='all'||(group==='personal'?c.personal:c.group===group)).filter(c=>(c.name+' '+c.ticker).toLowerCase().includes(s.toLowerCase()));list.innerHTML=coins.slice(0,limit).map(coinRow).join('')||'<div class="cm2-empty-block"><p>Монеты не найдены.</p></div>';},
    more(){limit+=30;renderHome();},
    amount(n){const input=document.getElementById('cm2-amount');if(input){input.value=n;}invalidate();},
    fraction(n){const input=document.getElementById('cm2-units');if(input){input.value=Math.floor(Number(selected.units)*n/100)/1000;}invalidate();},
    period(h){if(period===h)return;period=h;coin(selected.id);},
    closeShort(id){const p=data.shorts.find(x=>x.id===id);if(p)deal('close_short',p);},
    zarniki(v){const input=document.getElementById('cm2-z');if(input){input.value=String(v);}document.querySelectorAll('[data-z]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.z)===v)));invalidate();},
    icon(k){const input=document.getElementById('cm2-icon');if(input){input.value=k;}document.querySelectorAll('[data-icon]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.icon===k)));invalidate();}
  };
})();
