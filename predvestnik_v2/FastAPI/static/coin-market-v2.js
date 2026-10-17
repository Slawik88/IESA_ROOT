/* Биржа монет v2 — интерфейс.
   Все цены, комиссии и результаты считает аутентифицированный сервер.
   Клиент показывает опубликованные тики, опрашивает их и восстанавливает
   незавершённые операции по action_id. Генератор курса клиент не трогает. */
window.CM2 = (() => {
  let data=null, view='home', tab='market', selected=null, draft=null, busy=false,
      period=24, search='', group='all', limit=30, formRevision=0;
  let live={timer:null, clock:null, expiry:null, last:tickNow(), next:null};

  const root=()=>document.getElementById('pg-exchange-v1');
  function tickNow(){return Math.floor(Date.now()/1000);}
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=(s,price=false)=>{const n=Number(s);if(!Number.isFinite(n))return '—';if(n!==0&&Math.abs(n)<.01&&!price)return n<0?'− меньше 0,01':'меньше 0,01';return n.toLocaleString('ru-RU',{maximumFractionDigits:price?8:2});};
  const signed=s=>(Number(s)>0?'+':'')+num(s);
  const haptic=kind=>{if(typeof _haptic==='function')try{_haptic(kind);}catch(_){}};

  const CHAR={calm:'Штиль',flow:'Течение',storm:'Шторм',tide:'Прилив'};
  const CHAR_HINT={calm:'Обычно небольшие колебания и более долгие движения.',
    flow:'Умеренные колебания с чередованием направлений.',
    storm:'Более резкие колебания и частые развороты.',
    tide:'Движения могут идти дольше; иногда случаются резкие скачки.'};
  const GROUP={'sky':'Небо','earth':'Земля','horizon':'Горизонт'};
  const groupLabel=c=>c.personal?'Личные':(GROUP[c.group]||'Рынок');
  const ICON={
    coin:'<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="16" cy="16" r="12"/><circle cx="16" cy="16" r="6.5"/></svg>',
    star:'<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M16 4l3.6 7.6 8 .9-6 5.7 1.6 8L16 22.2 8.8 26.2l1.6-8-6-5.7 8-.9z"/></svg>',
    wave:'<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 19c3-6 6-6 9 0s6 6 9 0 6-6 6 0M4 12c3-6 6-6 9 0"/></svg>',
    leaf:'<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M26 6C14 6 6 13 6 22c0 2 .5 3.5 1 4 5-11 12-14 19-20z"/><path d="M10 22c6-1 10-4 12-9"/></svg>'};
  const icon=c=>ICON[c.icon]||ICON.coin;

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

  function invalidate(){formRevision++;draft=null;const preview=document.getElementById('cm2-preview');if(preview)preview.innerHTML='';}

  async function preview(side, position){
    if(busy)return;busy=true;invalidate();
    const revision=formRevision,screen=view,coinId=selected?.id,previewHost=document.getElementById('cm2-preview');
    const current=()=>revision===formRevision&&screen===view&&coinId===selected?.id&&previewHost===document.getElementById('cm2-preview');
    try{const amount=document.getElementById('cm2-amount')?.value.replace(',','.')||'0',raw=document.getElementById('cm2-units')?.value.replace(',','.');if(raw&&!/^\d+(\.\d{1,3})?$/.test(raw))throw Error('Количество монет — до трёх знаков после запятой.');
      const body={coin_id:selected.id,side,amount,units:raw?Math.round(Number(raw)*1000):0,position_id:position||null};
      const q=await request('/quote',body);if(!current())return;draft={path:'/trade',body:{...body,action_id:crypto.randomUUID(),tick:q.tick,price:q.price}};
      document.getElementById('cm2-preview').innerHTML=`<div class="cm2-ticket"><h2 class="cm2-focus">${q.spent?'Спишется '+num(q.spent):'Получите '+num(q.received)} Моры</h2><dl class="cm2-metrics"><dt>Комиссия</dt><dd>${num(q.commission)} Моры</dd>${q.received_units?`<dt>Монет</dt><dd>${num(Number(q.received_units)/1000,true)}</dd>`:''}${q.sold_units?`<dt>Продаёте</dt><dd>${num(Number(q.sold_units)/1000,true)} монет</dd>`:''}${q.liquidation_price?`<dt>Цена принудительного закрытия</dt><dd>${num(q.liquidation_price,true)} Моры</dd><dt>Максимальная потеря</dt><dd>${num(q.max_loss)} Моры</dd>`:''}${q.penalty&&Number(q.penalty)>0?`<dt>Штраф за закрытие</dt><dd>${num(q.penalty)} Моры</dd>`:''}</dl>${q.zero_payout?'<p class="cm2-dim">Получите 0 Моры — выбранный остаток закроется без выплаты. Мора из кошелька не списывается.</p>':''}<button class="cm2-primary ${side==='sell'?'cm2-danger':''}" onclick="CM2.confirm()">${q.zero_payout?'Продать за 0 Моры':'Подтвердить'}</button><p class="cm2-dim cm2-expiry" id="cm2-expiry"></p></div>`;
      startExpiry(q.expires_at);message('Условия действуют до следующего обновления курса.');
    }catch(e){if(current())message(e.message,true);}finally{busy=false;}
  }
  function startExpiry(expiresAt){
    const host=document.getElementById('cm2-expiry');if(!host)return;clearInterval(live.expiry);live.expiry=null;
    if(!expiresAt){host.textContent='Котировка может обновиться в любой момент.';return;}
    const render=()=>{const left=expiresAt-tickNow();host.textContent=left>0?'Котировка действует ещё '+String(Math.floor(left/60)).padStart(2,'0')+':'+String(left%60).padStart(2,'0'):'Котировка может обновиться в любой момент.';};
    render();live.expiry=setInterval(()=>{if(document.hidden||!document.getElementById('cm2-expiry')){clearInterval(live.expiry);live.expiry=null;return;}render();},1000);
  }

  function create(){
    if(pending()){showPending();return;}stopLive();view='create';draft=null;
    const z=[[1000,'1 000'],[2500,'2 500'],[5000,'5 000']].map(([v,l])=>`<button class="cm2-plain" aria-pressed="${v===1000}" data-z="${v}" onclick="CM2.zarniki(${v})">${l}</button>`).join('');
    const icons=Object.keys(ICON).map(k=>`<button class="cm2-icon-pick" aria-pressed="${k==='coin'}" data-icon="${k}" aria-label="${({coin:"Монета",star:"Звезда",wave:"Волна",leaf:"Лист"})[k]}" onclick="CM2.icon('${k}')">${ICON[k]}</button>`).join('');
    paint(head('Своя монета')+'<p class="cm2-lead">Название и значок — затем вклад. Итог покажем до подтверждения.</p>'+
      `<div class="cm2-field"><label for="cm2-name">Название</label><input id="cm2-name" maxlength="24" placeholder="3–24 символа" autocomplete="off" oninput="CM2.invalidate()"></div>`+
      `<div class="cm2-field"><span class="cm2-label">Значок</span><div class="cm2-icons" role="group" aria-label="Значок монеты">${icons}</div><input type="hidden" id="cm2-icon" value="coin"></div>`+
      `<div class="cm2-field"><label for="cm2-desc">Описание <span class="cm2-dim">· необязательно</span></label><input id="cm2-desc" maxlength="160" placeholder="Одна короткая строка" autocomplete="off" oninput="CM2.invalidate()"></div>`+
      `<div class="cm2-field"><span class="cm2-label">Зарников на создание</span><div class="cm2-presets cm2-segment" role="group" aria-label="Стоимость создания">${z}</div><input type="hidden" id="cm2-z" value="1000"></div>`+
      `<div class="cm2-field"><label for="cm2-deposit">Вклад в монету, Моры</label><input id="cm2-deposit" inputmode="decimal" value="1000" oninput="CM2.invalidate()"><p class="cm2-dim">От 1 000 до 100 000 Моры. Вклад становится обеспечением монеты.</p></div>`+
      `<label class="cm2-check"><input type="checkbox" id="cm2-gems" onchange="CM2.invalidate()"><span>Внести алмазами <span class="cm2-dim">· 1 алмаз = 1 000 Моры</span></span></label>`+
      '<button class="cm2-primary" onclick="CM2.createPreview()">Показать итог</button><div id="cm2-preview"></div>');
  }
  async function createPreview(){
    if(busy)return;busy=true;invalidate();
    const revision=formRevision,screen=view,coinId=selected?.id,previewHost=document.getElementById('cm2-preview');
    const current=()=>revision===formRevision&&screen===view&&coinId===selected?.id&&previewHost===document.getElementById('cm2-preview');
    try{const icon=document.getElementById('cm2-icon')?.value||'coin',description=document.getElementById('cm2-desc')?.value||'';
      const body={name:document.getElementById('cm2-name').value,zarniki:Number(document.getElementById('cm2-z')?.value||1000),deposit:document.getElementById('cm2-deposit').value.replace(',','.'),diamonds:document.getElementById('cm2-gems').checked,icon,description,action_id:crypto.randomUUID()};
      const q=await request('/create-quote',body);if(!current())return;draft={path:'/create',body};
      document.getElementById('cm2-preview').innerHTML=`<div class="cm2-ticket"><h2 class="cm2-focus">${escape(q.name)}</h2><dl class="cm2-metrics"><dt>Создание</dt><dd>${num(q.zarniki)} Зарников</dd><dt>Вклад</dt><dd>${q.diamonds?num(Number(q.deposit)/1000)+' алмазов':num(q.deposit)+' Моры'}</dd><dt>Стартовая цена</dt><dd>${num(q.price,true)} Моры</dd><dt>Ваша доля</dt><dd>${num(Number(q.creator_units)/1000)} монет · 20%</dd></dl><p class="cm2-dim">Забрать резерв напрямую нельзя. Свою долю можно продать по текущему курсу.</p><button class="cm2-primary" onclick="CM2.confirm()">Создать с этими условиями</button></div>`;}catch(e){if(current())message(e.message,true);}finally{busy=false;}
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
  function renderHome(){
    stopLive();view='home';draft=null;
    const mine=tab==='mine';
    const coins=data.coins.filter(c=>!mine||Number(c.units)>0||c.owned);
    const visible=coins.filter(c=>group==='all'||(group==='personal'?c.personal:c.group===group))
      .filter(c=>(c.name+' '+c.ticker).toLowerCase().includes(search.toLowerCase()));
    const chips=[['all','Все'],['sky','Небо'],['earth','Земля'],['horizon','Горизонт'],['personal','Личные']]
      .map(([key,label])=>`<button class="cm2-chip" aria-pressed="${group===key}" onclick="CM2.group('${key}')">${label}</button>`).join('');
    const shorts=mine?data.shorts.map(p=>{const c=data.coins.find(x=>x.id===p.coin_id);return `<div class="cm2-rowwrap"><button class="cm2-row" onclick="CM2.closeShort('${p.id}')"><span class="cm2-ava cm2-ico-drop"><svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M16 5v14m0 0l-5-5m5 5l5-5M8 26h16"/></svg></span><span class="cm2-name"><strong>${escape(c?.name||'Монета')}</strong><small>На падение · выделено ${num(p.collateral)} Моры</small></span><span class="cm2-end"><span class="cm2-change ${Number(p.result)>=0?'up':'down'}">${signed(p.result)} Моры</span></span></button></div>`;}).join(''):'';
    const body=visible.slice(0,limit).map(coinRow).join('');
    const empty=mine?'<div class="cm2-empty-block"><p>Здесь появятся купленные монеты и позиции на падение.</p><button class="cm2-plain" onclick="CM2.tab(\'market\')">Перейти на рынок</button></div>':'<div class="cm2-empty-block"><p>Монеты не найдены.</p></div>';
    paint(head('Биржа','navBack()')+
      `<div class="cm2-wallet"><span class="cm2-eyebrow">Доступно Моры</span><strong class="cm2-wallet-sum">${num(data.balances.mora)}</strong></div>`+
      `<div class="cm2-tabs" role="tablist" aria-label="Раздел биржи"><button role="tab" aria-selected="${tab==='market'}" onclick="CM2.tab('market')">Рынок</button><button role="tab" aria-selected="${tab==='mine'}" onclick="CM2.tab('mine')">Мои монеты</button></div>`+
      (data.news.length&&tab==='market'?`<h2 class="cm2-h2">Пока вас не было</h2><ul class="cm2-news">${data.news.map(n=>`<li>${n.coin_id?`<button onclick="CM2.coin('${n.coin_id}')"><span>${escape(n.text)}</span><span aria-hidden="true">›</span></button>`:`<p>${escape(n.text)}</p>`}</li>`).join('')}</ul>`:'')+
      (tab==='market'?`<div class="cm2-toolbar"><label class="sr-only" for="cm2-search">Найти монету</label><input id="cm2-search" type="search" value="${escape(search)}" placeholder="Найти монету" oninput="CM2.search(this.value)" autocomplete="off"></div><div class="cm2-chips" role="group" aria-label="Группы монет">${chips}</div>`:'')+
      `<div id="cm2-list" class="cm2-list">${body}${shorts}${body||shorts?'':empty}</div>`+
      (visible.length>limit?'<button class="cm2-plain cm2-more" onclick="CM2.more()">Показать ещё</button>':'')+
      (data.enabled?'<div class="cm2-actions cm2-create-line"><button class="cm2-plain" onclick="CM2.create()">Создать свою монету</button></div>':'<p class="cm2-dim">Новые сделки закрыты. Ваши позиции можно закрыть.</p>')+
      '<details class="cm2-help"><summary>Как работает биржа</summary><p>Курс меняет сервер по своему расписанию. Покупки игроков на него не влияют. Комиссия — 0,5% при покупке и продаже; чистый результат уже учитывает выход.</p><p>Позиция «на падение»: вы выделяете сумму, потерять можно только её. Если цены пойдут против позиции, сервер закроет её заранее. Остальной кошелёк не затрагивается.</p><button class="cm2-help-link" onclick="loadPlayerExchangeV1(true)">Проверить состояние прежней биржи</button></details>');
  }
  function coinRow(c){
    const up=Number(c.change_24h)>=0;
    return `<div class="cm2-rowwrap"><button class="cm2-row" onclick="CM2.coin('${c.id}')"><span class="cm2-ava">${icon(c)}</span><span class="cm2-name"><strong>${escape(c.name)}</strong><small>${escape(c.ticker)} · ${groupLabel(c)}${c.owned?' · ваша':''}</small></span><span class="cm2-end"><strong>${num(c.price,true)}</strong><span class="cm2-change ${up?'up':'down'}">${up?'▲':'▼'} ${num(Math.abs(c.change_24h))}% · ${escape(c.change_period)}</span></span></button><button class="cm2-star" aria-pressed="${c.favorite}" aria-label="${c.favorite?'Убрать из избранного':'В избранное'}" onclick="CM2.star('${c.id}')">★</button></div>`;
  }

  async function coin(id){
    stopLive();selected=data.coins.find(c=>c.id===id);if(!selected)return CM2.home();
    view='coin';draft=null;
    paint(head(selected.name,`CM2.home()`)+coinBody(selected));
    message('');
    const requested=id,hours=period;
    try{const history=await request('/coins/'+id+'/history?hours='+period);if(view!=='coin'||selected?.id!==requested||period!==hours)return;draw(history);const last=history.points[history.points.length-1];if(selected)startLive(requested,last?last.tick:0);}
    catch(e){const chart=document.getElementById('cm2-chart');if(chart)chart.innerHTML='<p class="cm2-chart-empty">График временно недоступен.</p>';message(e.message,true);}
  }
  function coinBody(c){
    const own=Number(c.units)>0;
    return `<p class="cm2-dim cm2-sub">${escape(c.ticker)} · ${c.personal?'Монета игрока':'Системная монета'} · ${CHAR[c.character]||''}</p>`+
      `<div class="cm2-quote"><strong class="cm2-price" id="cm2-price">${num(c.price,true)}</strong><small>Моры за монету</small><span class="cm2-change ${Number(c.change_24h)>=0?'up':'down'}" id="cm2-change">${Number(c.change_24h)>=0?'▲':'▼'} ${num(Math.abs(c.change_24h))}% · ${escape(c.change_period)}</span></div>`+
      `<div class="cm2-chart-card"><div class="cm2-chart-head"><div class="cm2-period" role="group" aria-label="Период графика">${[[1,'1 ч'],[24,'24 ч'],[168,'7 д']].map(([h,l])=>`<button class="cm2-plain" data-period="${h}" aria-pressed="${period===h}" onclick="CM2.period(${h})">${l}</button>`).join('')}</div><span class="cm2-live" id="cm2-live" role="status" aria-live="off"></span></div><div id="cm2-chart" class="cm2-chart" role="img" aria-label="График курса">Загрузка графика…</div><p class="cm2-dim cm2-stamp" id="cm2-stamp"></p></div>`+
      `<div id="cm2-position">${positionCard(c)}</div>`+
      `<div class="cm2-actions">${data.enabled?`<button class="cm2-primary" onclick="CM2.deal('buy')">Купить</button>`:''}${own?`<button class="cm2-plain cm2-danger" onclick="CM2.deal('sell')">Продать</button>`:''}${data.shorts_enabled&&!data.shorts.some(p=>p.coin_id===c.id)?`<button class="cm2-plain" onclick="CM2.deal('short')">На падение</button>`:''}</div>`+
      `<div class="cm2-actions"><button class="cm2-plain" aria-pressed="${c.favorite}" onclick="CM2.favorite()">${c.favorite?'★ В избранном':'☆ В избранное'}</button></div>`+
      (c.description?`<p class="cm2-desc">${escape(c.description)}</p>`:'')+
      (c.owned?`<details class="cm2-help"><summary>Оформление моей монеты</summary><div class="cm2-field"><label for="cm2-edit-desc">Описание</label><input id="cm2-edit-desc" maxlength="160" value="${escape(c.description||'')}"></div><button class="cm2-plain" onclick="CM2.saveMetadata()">Сохранить</button></details>`:'')+
      `<details class="cm2-help"><summary>Характер монеты</summary><p>${CHAR_HINT[c.character]||'Серверный курс.'}</p><p>Курс может вырасти или упасть. Характер не является прогнозом. Новая покупка может быть ограничена запасом фонда; существующие остатки обеспечены для продажи.</p></details>`;
  }
  function positionCard(c){
    if(Number(c.units)<=0)return '';
    return `<div class="cm2-pos"><h2 class="cm2-h2">Мой остаток</h2><dl class="cm2-metrics"><dt>Монет</dt><dd>${num(Number(c.units)/1000,true)}</dd><dt>Вложено</dt><dd>${num(c.cost)} Моры</dd><dt>При продаже получите</dt><dd>${num(c.sell_value)} Моры</dd><dt>Результат после комиссии</dt><dd class="${Number(c.result)>=0?'cm2-up':'cm2-down'}">${signed(c.result)} Моры</dd></dl><button class="cm2-plain cm2-danger" onclick="CM2.deal('sell')">Продать</button></div>`;
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
      `<button class="cm2-primary" onclick="CM2.preview('${side}','${position?.id||''}')">Проверить условия</button><div id="cm2-preview"></div>`);
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
      if(lastPoint&&lastPoint.tick!==live.last){live.last=lastPoint.tick;
        const fresh=await request('/me');
        if(!current())return;data=fresh;
        selected=data.coins.find(x=>x.id===id)||selected;
        const price=document.getElementById('cm2-price'),change=document.getElementById('cm2-change'),position=document.getElementById('cm2-position');
        if(price)price.textContent=num(selected.price,true);
        if(change){const up=Number(selected.change_24h)>=0;change.className='cm2-change '+(up?'up':'down');change.textContent=`${up?'▲':'▼'} ${num(Math.abs(selected.change_24h))}% · ${selected.change_period}`;}
        if(position)position.innerHTML=positionCard(selected);
      }
      draw(history);
    }catch(_){/* живое обновление молча переживает сбой сети */}
  }

  async function complete(result){
    const saved=pending();
    if(result?.ok!==true||typeof result.coin_id!=='string'||
       (saved?.path==='/trade'&&(result.coin_id!==saved.body.coin_id||result.side!==saved.body.side))){
      throw Error('Сервер не подтвердил операцию. Сохранённый запрос можно проверить повторно.');
    }
    store(null);draft=null;stopLive();
    let fresh=true;try{data=await request('/me');}catch(_){fresh=false;}
    if(typeof refreshCurrBar==='function')refreshCurrBar();
    renderHome();
    message(fresh?(result.side==='buy'?'Монеты куплены.':result.side==='sell'?'Продажа выполнена.':result.side==='short'?'Позиция открыта.':result.coin_id&&result.name?'Монета создана.':'Операция выполнена.'):'Операция выполнена. Не удалось обновить рынок — откройте биржу заново.');
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

  return {load,coin,deal,preview,confirm,create,createPreview,check,retry:sendPending,favorite,star,availability,invalidate,saveMetadata,
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
