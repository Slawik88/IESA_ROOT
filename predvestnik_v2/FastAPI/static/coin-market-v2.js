/* V2 UI. All executable prices/results come from the authenticated server. */
window.CM2 = (() => {
  let data=null,view='home',tab='market',selected=null,draft=null,busy=false,period=24,search='',limit=30,formRevision=0;
  const root=()=>document.getElementById('pg-exchange-v1');
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=(s,price=false)=>{const n=Number(s);if(!Number.isFinite(n))return '—';if(n!==0&&Math.abs(n)<.01&&!price)return n<0?'− меньше 0,01':'меньше 0,01';return n.toLocaleString('ru-RU',{maximumFractionDigits:price?8:2});};
  const signed=s=>(Number(s)>0?'+':'')+num(s);
  const icon='<svg class="cm2-icon" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="16" cy="16" r="13"/><path d="M9 21l5-9 4 6 5-7M10 25h12"/></svg>';
  const pendingKey=()=>data?'cm2_pending_'+data.user_id:null;
  function pending(){try{return JSON.parse(localStorage.getItem(pendingKey())||'null');}catch(_){return null;}}
  function store(p){try{if(p)localStorage.setItem(pendingKey(),JSON.stringify(p));else localStorage.removeItem(pendingKey());return true;}catch(_){return false;}}
  async function request(path,body,method){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
    try{
      const headers=new Headers(typeof hdrs==='function'?hdrs():{});
      headers.set('Content-Type','application/json');
      const response=await fetch(BASE+'/coin-market/v2'+path,{method:method||(body?'POST':'GET'),headers,body:body?JSON.stringify(body):undefined,signal:controller.signal});
      const payload=await response.json().catch(()=>({}));
      if(!response.ok){const d=payload.detail;const error=new Error(typeof d==='string'?d:d?.message||'Не удалось выполнить запрос.');error.status=response.status;error.code=d?.code;throw error;}
      return payload;
    }finally{clearTimeout(timer);}
  }
  function head(title,back='CM2.home()'){return typeof v3Head==='function'?v3Head(title,{back}):`<header><button class="cm2-plain" onclick="${back}">Назад</button><h1>${escape(title)}</h1></header>`;}
  function paint(html,focus=true){formRevision++;draft=null;const host=root();if(!host)return;host.innerHTML=`<section class="cm2">${html}<p id="cm2-message" class="cm2-status" role="status" aria-live="polite"></p></section>`;if(focus){const h=host.querySelector('h1');if(h){h.tabIndex=-1;h.focus({preventScroll:true});}}}
  function message(text,error=false){const host=document.getElementById('cm2-message');if(host){host.textContent=text;host.classList.toggle('cm2-error',error);}}
  function row(c){return `<button class="cm2-row" onclick="CM2.coin('${c.id}')">${icon}<span class="cm2-name"><strong>${escape(c.name)}</strong><small>${escape(c.ticker)} · ${c.personal?'личная':'системная'}</small></span><span class="cm2-end"><strong>${num(c.price,true)}</strong><small>${signed(c.change_24h)}% · ${escape(c.change_period)}</small></span></button>`;}
  async function load(visit=true){
    paint(head('Биржа','navBack()')+'<p class="cm2-loading" role="status">Загрузка рынка…</p>');
    try{data=await request('/me'+(visit?'?visit=true':''));view='home';renderHome();if(pending())showPending();}catch(e){paint(head('Биржа','navBack()')+'<p>Не удалось открыть рынок.</p><button class="cm2-primary" onclick="CM2.load()">Попробовать снова</button>');message(e.message,true);}
  }
  function renderHome(){
    view='home';draft=null;
    const coins=data.coins.filter(c=>tab!=='mine'||Number(c.units)>0||c.owned);
    const visible=coins.filter(c=>(c.name+' '+c.ticker).toLowerCase().includes(search.toLowerCase()));
    const shorts=tab==='mine'?data.shorts.map(p=>{const c=data.coins.find(x=>x.id===p.coin_id);return `<button class="cm2-row" onclick="CM2.closeShort('${p.id}')"><span class="cm2-name"><strong>${escape(c?.ticker||'Монета')} · на падение</strong><small>Выделено ${num(p.collateral)} Моры</small></span><span class="cm2-end">${signed(p.result)}</span></button>`;}).join(''):'';
    paint(head('Биржа','navBack()')+`<p class="cm2-balance">Доступно ${num(data.balances.mora)} Моры</p><div class="cm2-tabs" role="tablist" aria-label="Раздел биржи"><button role="tab" aria-selected="${tab==='market'}" onclick="CM2.tab('market')">Рынок</button><button role="tab" aria-selected="${tab==='mine'}" onclick="CM2.tab('mine')">Мои монеты</button></div>`+
      (data.news.length&&tab==='market'?`<ul class="cm2-news" aria-label="Пока вас не было">${data.news.map(n=>`<li>${n.coin_id?`<button onclick="CM2.coin('${n.coin_id}')">${escape(n.text)}</button>`:`<p>${escape(n.text)}</p>`}</li>`).join('')}</ul>`:'')+
      (tab==='market'?`<label for="cm2-search">Найти монету</label><input id="cm2-search" type="search" value="${escape(search)}" oninput="CM2.search(this.value)" autocomplete="off">`:'')+
      `<div id="cm2-list">${visible.slice(0,limit).map(row).join('')||'<p class="v3-empty">'+(tab==='mine'?'Монет пока нет. Выберите монету на рынке.':'Монеты не найдены.')+'</p>'}${shorts}</div>`+
      (visible.length>limit?'<button class="cm2-plain" onclick="CM2.more()">Показать ещё</button>':'')+
      (data.enabled?'<div class="cm2-actions"><button class="cm2-plain" onclick="CM2.create()">Создать свою монету</button></div>':'<p>Новые сделки закрыты. Ваши позиции можно закрыть.</p>')+
      '<details><summary>Как работает биржа</summary><p>Курс меняет сервер. Покупки игроков на него не влияют. Комиссия — 0,5% при покупке и продаже. Чистый результат уже учитывает выход.</p><p>На падение: выделите сумму и закройте позицию, когда захотите. При исчерпании обеспечения сервер закроет её сам. Остальной кошелёк не затрагивается.</p><button class="cm2-help-link" onclick="loadPlayerExchangeV1(true)">Проверить состояние прежней биржи</button></details>');
  }
  async function coin(id){
    selected=data.coins.find(c=>c.id===id);if(!selected)return;view='coin';draft=null;
    const c=selected,own=Number(c.units)>0;
    paint(head(c.name)+`<p class="cm2-dim">${escape(c.ticker)} · ${c.personal?'Монета игрока':'Системная монета'}</p><div class="cm2-price">${num(c.price,true)} <small>Моры</small></div><p>${signed(c.change_24h)}% · ${escape(c.change_period)}</p>`+
      `<div class="cm2-actions">${data.enabled?'<button class="cm2-primary" onclick="CM2.deal(\'buy\')">Купить</button>':''}${own?'<button class="cm2-plain cm2-danger" onclick="CM2.deal(\'sell\')">Продать</button>':''}</div>`+
      '<div class="cm2-actions cm2-period" aria-label="Период графика">'+[1,24,168].map(h=>`<button class="cm2-plain" aria-pressed="${period===h}" onclick="CM2.period(${h})">${h===1?'1 час':h===24?'24 часа':'7 дней'}</button>`).join('')+'</div><div id="cm2-chart" class="cm2-chart" role="status">Загрузка графика…</div><div id="cm2-scale" class="cm2-chart-caption"></div>'+
      (own?`<dl class="cm2-metrics"><dt>Монет</dt><dd>${num(Number(c.units)/1000,true)}</dd><dt>Вложено</dt><dd>${num(c.cost)} Моры</dd><dt>При продаже получите</dt><dd>${num(c.sell_value)} Моры</dd><dt>Результат после комиссии</dt><dd>${signed(c.result)} Моры</dd></dl>`:'')+
      `<div class="cm2-actions">${data.shorts_enabled?'<button class="cm2-plain" onclick="CM2.deal(\'short\')">На падение</button>':''}<button class="cm2-plain" aria-pressed="${c.favorite}" onclick="CM2.favorite()">${c.favorite?'В избранном':'В избранное'}</button></div><details><summary>Характер монеты</summary><p>${escape(({calm:'Обычно небольшие колебания и более долгие движения.',flow:'Умеренные колебания с чередованием направлений.',storm:'Более резкие колебания и частые развороты.',tide:'Движения могут идти дольше; иногда случаются резкие скачки.'})[c.character]||'Серверный курс.')}</p><p>Курс может вырасти или упасть. Характер не является прогнозом. Новая покупка может быть ограничена запасом фонда; существующие остатки обеспечены для продажи.</p></details>`);
    const requested=id,hours=period;
    try{const history=await request('/coins/'+id+'/history?hours='+period);if(view!=='coin'||selected?.id!==requested||period!==hours)return;draw(history.points);}catch(e){const chart=document.getElementById('cm2-chart');if(chart)chart.textContent='График временно недоступен.';message(e.message,true);}
  }
  function draw(points){
    const chart=document.getElementById('cm2-chart'),scale=document.getElementById('cm2-scale');if(!chart)return;
    if(points.length<2){chart.textContent='Монета только запущена. График появится после следующего обновления.';return;}
    const values=points.map(p=>Number(p.price)),min=Math.min(...values),max=Math.max(...values),range=max-min||max*.01||1;
    const path=values.map((v,i)=>`${i?'L':'M'}${(i/(values.length-1)*300).toFixed(2)},${(140-(v-min)/range*120).toFixed(2)}`).join(' ');
    chart.innerHTML=`<svg viewBox="0 0 300 160" role="img" aria-label="Курс за ${period===1?'час':period===24?'24 часа':'7 дней'}: от ${num(values[0],true)} до ${num(values.at(-1),true)} Моры"><path d="${path}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
    scale.innerHTML=`<span>Мин. ${num(min,true)}</span><span>Макс. ${num(max,true)} Моры</span>`;
  }
  function deal(side,position){
    if(pending()){showPending();return;}draft=null;view='deal';const c=position?data.coins.find(x=>x.id===position.coin_id):selected;selected=c;
    const title=({buy:'Купить',sell:'Продать',short:'На падение',close_short:'Закрыть позицию'})[side];
    paint(head(title,`CM2.coin('${c.id}')`)+`<p>${escape(c.name)} · ${num(c.price,true)} Моры</p>`+
      (side==='buy'||side==='short'?`<label for="cm2-amount">${side==='short'?'Выделить для позиции':'Потратить, включая комиссию'}<input id="cm2-amount" type="text" inputmode="decimal" value="10" oninput="CM2.invalidate()"></label><div class="cm2-presets">${[10,50,100].map(n=>`<button class="cm2-plain" onclick="CM2.amount('${n}')">${n}</button>`).join('')}</div>`:'')+
      (side==='sell'?`<label for="cm2-units">Продать монет<input id="cm2-units" inputmode="decimal" value="${Number(c.units)/1000}" oninput="CM2.invalidate()"></label><div class="cm2-presets">${[25,50,100].map(n=>`<button class="cm2-plain" onclick="CM2.fraction(${n})">${n}%</button>`).join('')}</div>`:'')+
      (side==='short'?'<p class="cm2-dim">Потерять можно только выделенную сумму. При нехватке обеспечения позиция закроется автоматически.</p>':'')+
      (position?`<dl class="cm2-metrics"><dt>Было выделено</dt><dd>${num(position.collateral)} Моры</dd><dt>Текущий результат</dt><dd>${signed(position.result)} Моры</dd></dl>`:'')+
      `<button class="cm2-primary" onclick="CM2.preview('${side}','${position?.id||''}')">Проверить условия</button><div id="cm2-preview"></div>`);
  }
  function invalidate(){formRevision++;draft=null;const preview=document.getElementById('cm2-preview');if(preview)preview.innerHTML='';}
  async function preview(side,position){
    if(busy)return;busy=true;invalidate();
    const revision=formRevision,screen=view,coinId=selected?.id,previewHost=document.getElementById('cm2-preview');
    const current=()=>revision===formRevision&&screen===view&&coinId===selected?.id&&previewHost===document.getElementById('cm2-preview');
    try{const amount=document.getElementById('cm2-amount')?.value.replace(',','.')||'0',raw=document.getElementById('cm2-units')?.value.replace(',','.');if(raw&&!/^\d+(\.\d{1,3})?$/.test(raw))throw Error('Количество монет — до трёх знаков после запятой.');
      const body={coin_id:selected.id,side,amount,units:raw?Math.round(Number(raw)*1000):0,position_id:position||null};
      const q=await request('/quote',body);if(!current())return;draft={path:'/trade',body:{...body,action_id:crypto.randomUUID(),tick:q.tick,price:q.price}};
      document.getElementById('cm2-preview').innerHTML=`<h2 class="cm2-focus">${q.spent?'Спишется '+num(q.spent):'Получите '+num(q.received)} Моры</h2><dl class="cm2-metrics"><dt>Комиссия</dt><dd>${num(q.commission)} Моры</dd>${q.received_units?`<dt>Монет</dt><dd>${num(Number(q.received_units)/1000,true)}</dd>`:''}${q.liquidation_price?`<dt>Цена принудительного закрытия</dt><dd>${num(q.liquidation_price,true)} Моры</dd><dt>Максимальная потеря</dt><dd>${num(q.max_loss)} Моры</dd>`:''}</dl>${q.zero_payout?'<p class="cm2-dim">Получите 0 Моры — выбранный остаток будет продан без выплаты. Мора из кошелька не списывается.</p>':''}<button class="cm2-primary ${side==='sell'?'cm2-danger':''}" onclick="CM2.confirm()">${q.zero_payout?'Продать за 0 Моры':'Подтвердить'}</button>`;message('Условия действуют до следующего обновления курса.');
    }catch(e){if(current())message(e.message,true);}finally{busy=false;}
  }
  function create(){
    if(pending()){showPending();return;}view='create';draft=null;
    paint(head('Своя монета')+'<p>Назовите монету и выберите вклад.</p><label for="cm2-name">Название<input id="cm2-name" maxlength="24" autocomplete="off" oninput="CM2.invalidate()"></label><label for="cm2-z">Зарников на создание<select id="cm2-z" onchange="CM2.invalidate()"><option value="1000">1 000 Зарников</option><option value="2500">2 500 Зарников</option><option value="5000">5 000 Зарников</option></select></label><label for="cm2-deposit">Вклад, эквивалент Моры<input id="cm2-deposit" inputmode="decimal" value="1000" oninput="CM2.invalidate()"></label><label class="cm2-inline-check"><input type="checkbox" id="cm2-gems" onchange="CM2.invalidate()">Внести алмазами (1 = 1 000 Моры)</label><p class="cm2-dim">Зарники оплачивают создание. Вклад становится обеспечением монеты; создателю достаются 20% монет. Больше Зарников повышает стартовую цену до 20%, но не процент доходности.</p><button class="cm2-primary" onclick="CM2.createPreview()">Показать итог</button><div id="cm2-preview"></div>');
  }
  async function createPreview(){
    if(busy)return;busy=true;invalidate();
    const revision=formRevision,screen=view,coinId=selected?.id,previewHost=document.getElementById('cm2-preview');
    const current=()=>revision===formRevision&&screen===view&&coinId===selected?.id&&previewHost===document.getElementById('cm2-preview');
    try{const body={name:document.getElementById('cm2-name').value,zarniki:Number(document.getElementById('cm2-z').value),deposit:document.getElementById('cm2-deposit').value.replace(',','.'),diamonds:document.getElementById('cm2-gems').checked,action_id:crypto.randomUUID()};const q=await request('/create-quote',body);if(!current())return;draft={path:'/create',body};document.getElementById('cm2-preview').innerHTML=`<h2 class="cm2-focus">${escape(q.name)}</h2><dl class="cm2-metrics"><dt>Создание</dt><dd>${num(q.zarniki)} Зарников</dd><dt>Вклад</dt><dd>${q.diamonds?num(Number(q.deposit)/1000)+' алмазов':num(q.deposit)+' Моры'}</dd><dt>Стартовая цена</dt><dd>${num(q.price,true)} Моры</dd><dt>Ваша доля</dt><dd>${num(Number(q.creator_units)/1000)} монет · 20%</dd></dl><p class="cm2-dim">Забрать резерв напрямую нельзя. Свою долю можно продать по текущему курсу.</p><button class="cm2-primary" onclick="CM2.confirm()">Создать с этими условиями</button>`;}catch(e){if(current())message(e.message,true);}finally{busy=false;}
  }
  async function confirm(){
    if(busy||!draft)return;if(pending()){showPending();return;}
    if(!store(draft)){message('Не удалось сохранить запрос для восстановления. Разрешите локальное хранилище.',true);return;}
    await sendPending();
  }
  function showPending(){paint(head('Проверка операции')+'<p>Запрос сохранён. Проверим результат перед следующей сделкой.</p><button class="cm2-primary" onclick="CM2.check()">Проверить результат</button><div class="cm2-actions"><button class="cm2-plain" onclick="CM2.retry()">Повторить этот же запрос</button></div>');}
  async function complete(result){store(null);draft=null;let fresh=true;try{data=await request('/me');}catch(_){fresh=false;}if(typeof refreshCurrBar==='function')refreshCurrBar();renderHome();message(fresh?(result.side==='buy'?'Монеты куплены.':result.coin_id&&result.name?'Монета создана.':'Операция выполнена.'):'Операция выполнена. Не удалось обновить рынок — откройте биржу заново.');}
  async function sendPending(){if(busy)return;const p=pending();if(!p)return;busy=true;showPending();message('Операция выполняется…');try{const r=await request(p.path,p.body);await complete(r);}catch(e){if([400,409,422].includes(e.status)){store(null);draft=null;data=await request('/me');renderHome();message(e.message,true);}else{showPending();message('Не удалось подтвердить результат. Запрос сохранён; повтор не создаст вторую сделку.',true);}}finally{busy=false;}}
  async function check(){if(busy)return;const p=pending();if(!p)return;busy=true;try{await complete(await request('/receipt/'+p.body.action_id));}catch(e){message(e.status===404?'Результат пока не найден. Можно повторить сохранённый запрос.':e.message,true);}finally{busy=false;}}
  async function favorite(){try{await request('/coins/'+selected.id+'/favorite',{enabled:!selected.favorite},'PUT');selected.favorite=!selected.favorite;await coin(selected.id);}catch(e){message(e.message,true);}}
  async function availability(){const r=await request('/availability');return r.visible;}
  return {load,coin,deal,preview,confirm,create,createPreview,check,retry:sendPending,favorite,availability,invalidate,
    home(){if(pending())showPending();else renderHome();},tab(t){tab=t;search='';limit=30;renderHome();},
    search(s){search=s;const rows=data.coins.filter(c=>(c.name+' '+c.ticker).toLowerCase().includes(s.toLowerCase()));document.getElementById('cm2-list').innerHTML=rows.slice(0,30).map(row).join('')||'<p>Монеты не найдены.</p>';},
    more(){limit+=30;renderHome();},amount(n){document.getElementById('cm2-amount').value=n;invalidate();},fraction(n){document.getElementById('cm2-units').value=Math.floor(Number(selected.units)*n/100)/1000;invalidate();},
    period(h){period=h;coin(selected.id);},closeShort(id){const p=data.shorts.find(x=>x.id===id);if(p)deal('close_short',p);}
  };
})();
