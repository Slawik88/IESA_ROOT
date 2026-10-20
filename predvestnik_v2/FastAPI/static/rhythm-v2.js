(() => {
  const tg = window.Telegram?.WebApp; tg?.ready(); tg?.expand();
  const base = document.body.dataset.appBase || location.pathname.replace(/\/rhythm-v2\/?$/, '');
  const init = tg?.initData || new URLSearchParams(location.hash.slice(1)).get('tgWebAppData') || '', session = (()=>{try{return localStorage.getItem('pv_sess')||''}catch(_){return ''}})(), headers = {'Content-Type':'application/json'};
  if (init) headers['x-init-data'] = init;
  if (session) headers['x-session-token'] = session;
  const $ = id => document.getElementById(id), storageKey = 'predvestnik-rhythm-v2-live';
  let tickEnd=0, state=null, timer=null, leaderboardMode='normal', boardPage=null, leaving=false;
  const store = new PVLocal.Store('rhythm', tg, session, init);
  let generation=0;let engine=null, journal=[], paused=false, resolving=false, remaining=null, expectedRune=null, loading=false;
  const show = id => ['intro','countdown','choice','run','result'].forEach(x => $(x).classList.toggle('hidden', x !== id));
  const glyph = rune => ({left:'ᚠ',center:'ᚱ',right:'ᚦ'}[rune] || '—');
  const buttons = () => [...document.querySelectorAll('[data-rune]')];
  const err = text => { $('error').textContent = text || ''; };
  async function api(path, options={}) { const response=await PVLocal.request(base+'/rhythm-v2'+path,{...options,headers:{...headers,...(options.headers||{})}}); const data=await response.json().catch(()=>({})); if(!response.ok){const error=new Error(data.detail||'Не удалось связаться с сервером.');error.status=response.status;throw error;} return data; }
  if('serviceWorker' in navigator)navigator.serviceWorker.register(base+'/local-games-sw.js',{scope:base+'/'}).catch(()=>{});
  fetch(base+'/skins-v3/me',{headers}).then(response=>response.ok?response.json():null).then(skin=>window.applyGlobalSkinV3?.(skin)).catch(()=>{});
  function save(){if(engine){store.data.active={packet:engine.packet,state:engine.state,journal,remaining:remaining??Math.max(0,tickEnd-performance.now())};store.save();}}
  function setButtons(disabled, selected=null){buttons().forEach(b=>{b.disabled=disabled;b.classList.toggle('pending',b.dataset.rune===selected&&disabled)})}
  function connection(mark,text){$('connection').textContent=mark;$('connection').setAttribute('aria-label',text)}
  function tick(duration,full){
    clearInterval(timer);remaining=null;tickEnd=performance.now()+duration;
    timer=setInterval(()=>{const left=Math.max(0,tickEnd-performance.now());$('timebar').style.transform='scaleX('+left/full+')';if(left===0){clearInterval(timer);sendTap(null);}},16);
  }
  function pause(){if(!engine||engine.state.status!=='active')return;remaining=remaining??Math.max(0,tickEnd-performance.now());paused=true;clearInterval(timer);save();setButtons(true);$('resume-run').classList.remove('hidden');$('tap-feedback').textContent='На паузе — сердца сохранены';}
  async function localDraw(){
    if(!engine)return;const current=engine,version=generation;const view=await current.view();if(engine!==current||version!==generation)return;state=view;expectedRune=view.rune;
    connection(navigator.onLine?'●':'○','Игра работает на устройстве');err(store.durable?'':'Не удалось сохранить игру на устройстве. Не закрывай приложение.');
    $('health').textContent='♥'.repeat(view.health)||'—';$('score').textContent=view.score;$('combo').textContent=view.combo;
    $('speed').textContent=view.speed_percent+'%';$('perks').textContent=perksLine(view);
    if(view.status==='finished'){store.data.last={packet:engine.packet,state:engine.state,journal};store.queue(engine.packet,journal);finish({...view,integrity_status:'saved_local'});flushResults();return;}
    if(view.draft){clearInterval(timer);remaining=null;offers();return;}
    $('instruction').textContent='Нажми руну '+glyph(view.rune);$('run-note').textContent='Такт '+view.next_signal_no+' · чанк '+view.chunk+' · окно '+view.window_ms+' мс';
    $('tap-feedback').textContent='Выбери руну';$('tap-feedback').dataset.state='';show('run');
    if(document.hidden)paused=true;
    $('resume-run').classList.toggle('hidden',!paused);setButtons(paused);
    if(!paused)tick(remaining??view.window_ms,view.window_ms);else save();
  }
  async function flushResults(){try{await store.flush(api,result=>{if(state?.run_id===result.run_id&&state.status==='finished'){if(result.rejected){$('result-status').textContent='Не удалось подтвердить результат';err(result.message);}else finish(result);}});}catch(error){if(state?.status==='finished')$('result-status').textContent=error.status===401?'Сохранено · открой игру заново в Telegram для отправки':'Сохранено на устройстве · отправим при подключении';}}
  setInterval(flushResults,5000);window.addEventListener('online',()=>{flushResults();store.refreshRules(api).catch(()=>{});});
  function finish(result) {
    state = result;
    try{localStorage.removeItem(storageKey);}catch(_){} clearInterval(timer);
    const clear = result.integrity_status === 'clear';
    const labels = { saved_local: 'Сохранено на устройстве', clear: 'Забег подтверждён', review_required: 'Результат ожидает проверки',
      quarantined: 'Результат не допущен в рейтинг', legacy_unverified: 'Старый результат без проверки' };
    connection(clear ? '●' : '◐', labels[result.integrity_status] || 'Результат сохранён без рейтингового допуска');
    $('final-score').textContent = Number(result.score).toLocaleString('ru-RU');
    const n = Number(result.correct_taps) + Number(result.mistakes), acc = n ? (100 * result.correct_taps / n).toFixed(1) : '0';
    $('final-detail').textContent = result.correct_taps + ' из ' + n + ' тактов верно';
    const status = $('result-status');
    status.textContent = ({saved_local:'Сохранено · отправляем результат',clear:'В рейтинге',review_required:'На проверке',quarantined:'Вне рейтинга',legacy_unverified:'Без проверки'})[result.integrity_status] || 'Без допуска';
    status.dataset.state = clear ? 'clear' : 'pending'; status.title = labels[result.integrity_status] || 'Нет рейтингового допуска';
    $('final-accuracy').textContent = acc.replace('.', ',') + '%';
    $('result-accuracy').style.setProperty('--accuracy', acc + '%');
    $('result-accuracy').setAttribute('aria-label', 'Точность ' + acc.replace('.', ',') + ' процента');
    drawAnalysis(result); leaderboardMode = result.mode; boardPage = null; show('result'); refreshLeaderboard();
  }
  function drawAnalysis(result) {
    const box = $('run-analysis'); box.replaceChildren();
    const a = result.analysis;
    if (!a?.complete) { const p = document.createElement('p'); p.className = 'r-result-hint'; p.textContent = 'Подробности этого забега не сохранены.'; box.append(p); return; }
    const dl = document.createElement('dl'); dl.className = 'r-analysis-metrics';
    const metric = (name, value) => { const row = document.createElement('div'), dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = name; dd.textContent = value; row.append(dt, dd); dl.append(row); };
    metric('Лучшая серия', a.best_streak); metric('Неверные руны', a.wrong); metric('Пропуски', a.timeouts); box.append(dl);
    if (result.integrity_status === 'clear' && a.previous_best != null) {
      const delta = result.score - a.previous_best;
      const record = document.createElement('p'); record.className = 'r-result-record';
      record.textContent = a.previous_best === 0 ? 'Первый результат в рейтинге' :
        delta > 0 ? 'Новый рекорд · +' + delta + ' очков' : 'Личный рекорд · ' + a.previous_best;
      box.append(record);
    }
    const tip = a.timeouts > a.wrong ? 'Чаще не хватало времени. Дар с широким окном может помочь.' :
      a.wrong > 0 ? 'Смотри на форму руны: это поможет реже путать символы.' :
      a.timing.late > a.timing.early ? 'Ответы ближе к краю окна. Попробуй более спокойный темп.' : '';
    if (tip) { const p = document.createElement('p'); p.className = 'r-result-hint'; p.textContent = tip; box.append(p); }
    const details = document.createElement('details'), title = document.createElement('summary'); title.textContent = 'Разбор забега'; details.append(title);
    const extra = document.createElement('dl'); extra.className = 'r-analysis-extra';
    for (const [name,value] of [['Потеряно сердец',a.hearts_lost],['Средний ответ',a.response_ms == null ? '—' : a.response_ms+' мс']]) {
      const row=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=name;dd.textContent=value;row.append(dt,dd);extra.append(row);
    }
    details.append(extra);
    const caveat=document.createElement('p');caveat.className='r-analysis-caveat';caveat.textContent='Время ответа измерено на устройстве. Паузы и ожидание сети не отнимают сердца.';details.append(caveat);
    const list = document.createElement('ol');
    (a.chunks || []).forEach(row => { const li = document.createElement('li'); li.textContent = 'Блок ' + row.chunk + (row.merged ? ' и далее' : '') + ': верных ' + row.correct + ', неверных ' + row.wrong + ', пропусков ' + row.timeouts + ', потеряно сердец ' + row.hearts_lost + '.'; list.append(li); });
    details.append(list);
    if (result.gifts?.length) { const p=document.createElement('p');p.textContent='Сборка: '+result.gifts.map(g=>g.name+(g.count>1?' ×'+g.count:'')).join(' · ');details.append(p); }
    box.append(details);
  }
  async function sendTap(rune){
    if(!engine||engine.state.status!=='active'||paused||resolving||state?.draft)return;
    resolving=true;clearInterval(timer);const elapsed=rune===null?engine.window()+1:Math.min(60000,Math.max(0,Math.floor(engine.window()-(remaining??Math.max(0,tickEnd-performance.now())))));
    journal.push({kind:'tap',signal_no:engine.state.next_signal_no,rune,elapsed_ms:elapsed});
    engine.step(rune,elapsed,expectedRune);remaining=engine.window();save();setButtons(true);
    try{await localDraw();}finally{resolving=false;}
  }
  async function start(mode){
    if(loading)return;loading=true;
    try{err('');leaving=false;paused=false;remaining=null;
      const version=++generation;
      let packet=await store.fresh('rhythm');
      if(!packet){
        const started=await api('/runs',{method:'POST',body:JSON.stringify({mode})});
        packet=await api('/runs/'+started.run_id+'/local-packet',{method:'POST'});
      }
      if(version!==generation)return;
      store.data.template=packet;if(navigator.onLine)store.refreshRules(api).catch(()=>{});
      engine=new PVLocal.Rhythm(packet);journal=[];state={run_id:packet.run_id,status:'active'};remaining=engine.window();save();
      if(await countdown())await localDraw();
    }catch(error){err(error.message);}finally{loading=false;}
  }
  const kindLabel={safe:'Надёжный',boost:'Усиление',risk:'Риск'};
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  async function countdown(){show('countdown');const id=state.run_id;for(let n=5;n>0;n--){$('count-num').textContent=n;await sleep(1000);if(leaving||!state||state.run_id!==id)return false}return true}
  function offers() {
    clearInterval(timer); setButtons(true); show('choice');
    $('draft-title').textContent = 'Рун-дар №' + state.draft.number;
    const box = $('gifts'); box.replaceChildren();
    state.draft.offers.forEach(gift => {
      const b = document.createElement('button'); b.className = 'gift'; b.dataset.kind = gift.kind;
      for (const [tag, cls, text] of [['small', '', kindLabel[gift.kind] || ''], ['b', '', gift.name],
        ['span', 'gift-plus', '＋ ' + gift.bonus], ['span', 'gift-minus', '− ' + gift.cost]]) {
        const node = document.createElement(tag); node.className = cls; node.textContent = text; b.append(node);
      }
      const p = gift.preview;
      if (p) {
        const changes = [['health', 'Сердца', ''], ['window_ms', 'Окно', ' мс'], ['speed_percent', 'Темп', '%'],
          ['shield', 'Щиты', ''], ['ebb', 'Такты отлива', ''], ['bloody', 'Тройные очки, тактов', ''], ['sample_score', 'Очки за примерный ответ', '']]
          .filter(([key]) => p.before[key] !== p.after[key])
          .map(([key, label, unit]) => label + ': ' + p.before[key] + unit + ' → ' + p.after[key] + unit);
        const summary = document.createElement('span'); summary.className = 'gift-effective'; summary.textContent = changes.join(' · ') || 'Параметры следующего такта не меняются.'; b.append(summary);
      }
      b.onclick = () => pickGift(gift.id); box.append(b);
    });
    box_disable(false);
  }
  async function pickGift(id){
    if(!state?.draft||resolving||!state.draft.offers.some(g=>g.id===id))return;
    resolving=true;clearInterval(timer);journal.push({kind:'pick',perk_id:id});engine.pick(id);remaining=engine.window();save();box_disable(true);
    try{await localDraw();}finally{resolving=false;}
  }
  function box_disable(flag){document.querySelectorAll('#gifts button').forEach(b=>{b.disabled=flag})}
  function perksLine(s){const parts=(s?.gifts||[]).map(g=>g.name+(g.count>1?' ×'+g.count:''));const p=s?.perks||{};if(p.shield>0)parts.push('🛡 щит ×'+p.shield);if(p.ebb>0)parts.push('🌊 отлив ещё '+p.ebb);if(p.bloody>0)parts.push('🩸 тройные очки ещё '+p.bloody);if(p.recovery>0)parts.push('Второе дыхание: ещё '+p.recovery+' такта');return parts.join(' · ')}
  async function cancel(){
    const id=state?.run_id;++generation;leaving=true;clearInterval(timer);engine=null;state=null;journal=[];store.data.active=null;store.save();
    show('intro');if(id)api('/runs/'+id+'/cancel',{method:'POST'}).catch(()=>{});leaving=false;
  }
  function empty(text){const list=$('leaderboard-list');list.replaceChildren();const row=document.createElement('li');row.className='leaderboard-empty';row.textContent=text;list.append(row)}
  // Сезон: срок в подписи над результатом, призы и условия свёрнуты в «Награды сезона», прошлый сезон одной строкой под результатом
  const num=n=>Number(n||0).toLocaleString('ru-RU');
  function seasonTerms(s){const t=s.terms;return t?'Награду получают игроки, у которых от '+t.min_runs+' забегов в '+t.min_days+' разных днях и аккаунт старше '+t.min_account_days+' дней. Призовые места открываются, когда в таблице '+Object.values(t.podium_min_players).join(' / ')+' игроков.':''}
  function renderSeason(data){const s=data.season,l=data.last_season;if(!s)return;$('season-no').textContent=s.number;$('season-left').textContent=' · ещё '+s.days_left+' дн., до '+new Date(s.ends_at).toLocaleDateString('ru-RU');$('season-note').textContent=seasonTerms(s);$('season-note').hidden=!s.terms;$('season-rewards').closest('details').hidden=!(s.rewards||[]).length;const box=$('season-rewards');box.replaceChildren();(s.rewards||[]).forEach(r=>{const li=document.createElement('li'),place=document.createElement('b'),prize=document.createElement('span');place.textContent=r.label+' место';prize.textContent=num(r.mora)+' Моры + '+num(r.essence)+' Эссенции';li.append(place,prize);box.append(li)});const top=(s.rewards||[])[0];$('season-top').textContent=top?' · за 1 место '+num(top.mora)+' Моры':'';const last=$('season-last');last.hidden=!l;if(l)last.textContent='Прошлый сезон '+l.season+': место #'+l.place+(l.reward_mora?' · +'+num(l.reward_mora)+' Моры':'')+(l.reward_essence?' и '+num(l.reward_essence)+' Эссенции':'')}
  let knownTotal=0;   // «из N» приходит только со страницами полного топа: запоминаем, чтобы цифра в шапке не прыгала
  function personal(p){const box=$('leaderboard-personal');box.replaceChildren();if(!p){box.textContent='Тебя пока нет в таблице сезона. Заверши забег с очками, и он появится здесь.';box.classList.remove('has-place');return}if(p.total)knownTotal=p.total;const place=document.createElement('b'),rest=document.createElement('span');place.textContent='#'+p.place+(knownTotal?' из '+knownTotal:'');rest.textContent='лучший счёт '+num(p.best_score);box.append(place,rest);box.classList.add('has-place')}
  // По умолчанию видна пятёрка лидеров; «Весь топ» листает всех игроков сезона страницами (boardPage = номер страницы)
  function list(data){if(data.season&&boardPage===null)renderSeason(data);const rows=boardPage===null?data.top.slice(0,5):data.items,target=$('leaderboard-list');target.replaceChildren();if(!rows.length)empty('Пока нет завершённых забегов.');else rows.forEach(row=>{const item=document.createElement('li'),p=document.createElement('span'),name=document.createElement('a'),score=document.createElement('b'),player=row.player||{};p.textContent='#'+row.place;name.innerHTML=window.gameWhoV3?window.gameWhoV3(player):'';if(!name.innerHTML)name.textContent=player.display_name||'Игрок';name.href=base+'/?startapp=public&profile='+encodeURIComponent(player.profile_ref||'');name.setAttribute('aria-label','Открыть профиль '+(player.display_name||'Игрок'));score.textContent=row.best_score;if(row.is_me)item.className='is-me';item.append(p,name,score);target.append(item)});personal(data.personal);more(data);document.querySelectorAll('[data-leaderboard-mode]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.leaderboardMode===leaderboardMode)))}
  function boardButton(text,label,go,disabled){const b=document.createElement('button');b.type='button';b.className='secondary';b.textContent=text;if(label)b.setAttribute('aria-label',label);b.disabled=!!disabled;b.onclick=go;return b}
  function more(data){const box=$('leaderboard-more');box.replaceChildren();if(boardPage===null){if(data.top.length>5)box.append(boardButton('Весь топ ›','',()=>openBoard(0)));return}if(data.pages>1){const at=document.createElement('span');at.textContent=(data.page+1)+' / '+data.pages;box.append(boardButton('‹','Предыдущая страница',()=>openBoard(data.page-1),data.page<=0),at,boardButton('›','Следующая страница',()=>openBoard(data.page+1),data.page+1>=data.pages))}box.append(boardButton('Свернуть','',()=>openBoard(null)))}
  function openBoard(page){boardPage=page;refreshLeaderboard()}
  async function refreshLeaderboard(){try{list(await api(boardPage===null?'/leaderboard/'+leaderboardMode:'/leaderboard/'+leaderboardMode+'/full?page='+boardPage))}catch(error){$('leaderboard-more').replaceChildren();if(boardPage===null)$('leaderboard-personal').textContent='';empty(init?'Таблица временно недоступна.':'Войдите через Telegram, чтобы увидеть результаты.')}}
  async function restore(){
    const version=generation;const active=store.data.active||(store.data.outbox.length?store.data.last:null);
    if(active?.packet?.protocol==='resilient-local-v1'){
      store.data.template=active.packet;engine=new PVLocal.Rhythm(active.packet,active.state);journal=active.journal||[];remaining=active.remaining??engine.window();paused=true;await localDraw();
    }else{
      // Take over a run left by the previous WS client without charging the
      // disconnected interval. Only remove the old checkpoint after success.
      try{const saved=JSON.parse(localStorage.getItem(storageKey)||'null');if(saved?.state?.run_id&&saved.state.status==='active'){
        const packet=await api('/runs/'+saved.state.run_id+'/local-packet',{method:'POST'});if(version!==generation)return;engine=new PVLocal.Rhythm(packet);journal=[];remaining=engine.window();paused=true;save();await localDraw();localStorage.removeItem(storageKey);
      }}catch(_){}
    }
    flushResults();if(navigator.onLine)store.refreshRules(api).catch(()=>{});
  }
  document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>start(b.dataset.mode));
  $('exit-run').onclick=cancel;$('exit-count').onclick=cancel;
  $('resume-run').onclick=()=>{paused=false;$('resume-run').classList.add('hidden');localDraw();};
  window.addEventListener('pagehide',pause);document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
  buttons().forEach(b=>b.onclick=()=>sendTap(b.dataset.rune));
  $('again').onclick=()=>{engine=null;state=null;show('intro');refreshLeaderboard();};
  $('results-leaderboard').onclick=()=>{show('intro');refreshLeaderboard();};refreshLeaderboard();restore();
})();
