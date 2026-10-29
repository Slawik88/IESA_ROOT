(() => {
  if (window.MutationObserver) {
    const hydrate = () => window.hydrateLeaderboardAvatars?.(document.getElementById('leaderboard-list')?.parentElement);
    const observer = new MutationObserver(hydrate);
    for (const id of ['leaderboard-list','leaderboard-podium']) { const host = document.getElementById(id); if (host) observer.observe(host,{childList:true}); }
  }
  const tg = window.Telegram?.WebApp; tg?.ready(); tg?.expand();
  const base = document.body.dataset.appBase || location.pathname.replace(/\/rhythm-v2\/?$/, '');
  const init = tg?.initData || new URLSearchParams(location.hash.slice(1)).get('tgWebAppData') || '', session = (()=>{try{return localStorage.getItem('pv_sess')||''}catch(_){return ''}})(), headers = {'Content-Type':'application/json'};
  if (init) headers['x-init-data'] = init;
  if (session) headers['x-session-token'] = session;
  const $ = id => document.getElementById(id), storageKey = 'predvestnik-rhythm-v2-live';
  let tickEnd=0, state=null, timer=null, leaderboardMode='normal', boardPage=null, leaving=false;
  const store = new PVLocal.Store('rhythm', tg, session, init);
  let generation=0;let engine=null, journal=[], paused=false, resolving=false, remaining=null, expectedRune=null, loading=false;
  let drawSeq=0, preparing=false, prepareTimer=null, prepareDone=null;
  const show = id => {
    ['intro','countdown','choice','run','result'].forEach(x => $(x).classList.toggle('hidden', x !== id));
    document.body.classList?.toggle('lg-playing', id !== 'intro' && id !== 'result');   // во время забега случайное касание не переключает режим
  };
  const glyph = rune => ({left:'ᚠ',center:'ᚱ',right:'ᚦ'}[rune] || '—');
  const buttons = () => [...document.querySelectorAll('[data-rune]')];
  const err = text => { $('error').textContent = text || ''; };
  async function api(path, options={}) { const response=await PVLocal.request(base+'/rhythm-v2'+path,{...options,headers:{'Content-Type':'application/json',...(window.GameMode?.headers()||headers),...(options.headers||{})}}); const data=await response.json().catch(()=>({})); if(!response.ok){const error=new Error(data.detail||'Нет связи. Проверь интернет и попробуй ещё раз.');error.status=response.status;throw error;} return data; }
  if('serviceWorker' in navigator)navigator.serviceWorker.register(base+'/local-games-sw.js',{scope:base+'/'}).catch(()=>{});
  fetch(base+'/skins-v3/me',{headers:{'Content-Type':'application/json',...(window.GameMode?.headers()||headers)}}).then(response=>response.ok?response.json():null).then(skin=>window.applyGlobalSkinV3?.(skin)).catch(()=>{});
  function save(){if(engine){store.data.active={packet:engine.packet,state:engine.state,journal,remaining:remaining??Math.max(0,tickEnd-performance.now())};store.save();}}
  function setButtons(disabled, selected=null){buttons().forEach(b=>{b.disabled=disabled;b.classList.toggle('pending',b.dataset.rune===selected&&disabled)})}
  function connection(mark,text){const out=$('connection');if(!out)return;out.textContent=mark;out.setAttribute('aria-label',text);out.dataset.state=mark==='●'?'on':mark==='○'?'off':'wait'}
  // Вид забега — тот же, что у уровня рейтинга (league-rhythm-fx.js): сердца, кольцо времени, большая руна, чипы даров. Правила здесь не считаются.
  const ARC=2*Math.PI*54,Art=()=>window.LeagueArt,Fx=()=>window.LeagueFx;
  let shownHealth=null;
  const setArc=share=>{const arc=$('time-arc');if(arc)arc.style.strokeDashoffset=String((1-Math.max(0,Math.min(1,share)))*ARC);};
  const setTarget=(kind,text,label)=>{const t=$('instruction');t.textContent=text;t.dataset.kind=kind;t.setAttribute('aria-label',label||text);};
  function drawHearts(health){
    const box=$('health'),art=Art();box.setAttribute('aria-label','Сердец: '+health);
    if(!art){box.textContent='♥'.repeat(health)||'—';return}
    box.innerHTML=Array.from({length:Math.max(5,health)},(_,i)=>art.heart(i<health?'full':'empty')).join('');
    if(shownHealth!==null&&health<shownHealth)Fx()?.shake(box);
    shownHealth=health;
  }
  function drawPerks(view){
    const box=$('perks'),p=view.perks||{};box.replaceChildren();
    const chip=(text,kind)=>{const c=document.createElement('span');c.className='lgr-chip'+(kind?' is-'+kind:'');c.textContent=text;box.append(c)};
    (view.gifts||[]).forEach(g=>chip(g.name+(g.count>1?' ×'+g.count:''),engine?.catalog?.[g.id]?.kind));
    if(p.shield>0)chip('🛡 щит ×'+p.shield);
    if(p.revive>0)chip('🔥 Феникс готов');
    if(p.ebb>0)chip('🌊 отлив: ещё '+p.ebb+' нажатий с запасом времени');
    if(p.bloody>0)chip('🩸 очки втрое больше: ещё '+p.bloody+' нажатий');
    if(p.recovery>0)chip('Второе дыхание: ещё '+p.recovery+' нажатий с запасом времени');
  }
  // Отклик на нажатие: верно — кольцо и «+очки» (золотые за быстрый ответ), ошибка — встряска руны
  function tapFeel(ok,gained,perfect){
    const fx=Fx(),arena=$('arena');
    if(Number(tg?.version||0)>=6.1)tg.HapticFeedback?.impactOccurred(ok?'light':'heavy');
    if(!fx||!arena)return;
    if(ok){fx.ring(arena,perfect?'is-gold':'');fx.float(arena,'+'+gained,perfect?'is-gold':'');}else fx.shake($('instruction'));
  }
  function tick(duration,full){
    clearInterval(timer);remaining=null;tickEnd=performance.now()+duration;
    timer=setInterval(()=>{const left=Math.max(0,tickEnd-performance.now());setArc(left/full);if(left===0){clearInterval(timer);sendTap(null);}},16);
  }
  function stopPreparation(){clearTimeout(prepareTimer);prepareTimer=null;const done=prepareDone;prepareDone=null;preparing=false;done?.(false);$('run').classList.remove('preparing');}
  function pause(){
    if(!engine||engine.state.status!=='active')return;
    remaining=remaining??Math.max(0,tickEnd-performance.now());paused=true;++drawSeq;clearInterval(timer);stopPreparation();expectedRune=null;
    setTarget('text','Пауза');save();setButtons(true);$('resume-run').classList.remove('hidden');$('tap-feedback').textContent='Сердца сохранены. Продолжай, когда будешь готов';
    // A pending view (e.g. immediately after a gift) must not leave an obsolete
    // disabled choice screen behind when the page is hidden mid-transition.
    localDraw();
  }
  async function localDraw({prepare=false}={}){
    if(!engine)return;const current=engine,version=generation,draw=++drawSeq;
    if(prepare){stopPreparation();preparing=true;paused=true;remaining=current.window();expectedRune=null;setButtons(true);}
    const view=await current.view();if(engine!==current||version!==generation||draw!==drawSeq)return;state=view;
    connection(navigator.onLine?'●':'○','Игра работает на устройстве');err(store.durable?'':'Не удалось сохранить игру на устройстве. Не закрывай приложение.');
    drawHearts(view.health);$('score').textContent=view.score;$('combo').textContent=view.combo;
    drawPerks(view);weatherLine($('weather'),view.weather,'');
    if(view.status==='finished'){store.data.last={packet:engine.packet,state:engine.state,journal};store.queue(engine.packet,journal);finish({...view,integrity_status:'saved_local'});flushResults();return;}
    if(view.draft){stopPreparation();expectedRune=null;paused=true;clearInterval(timer);remaining=null;offers();return;}
    $('run-note').textContent='Нажатие '+view.next_signal_no+' · блок '+(view.chunk+1)+' · скорость '+view.speed_percent+'%';show('run');
    if(document.hidden)paused=true;
    if(prepare&&!document.hidden){
      setTarget('text','Приготовься');$('tap-feedback').textContent='Первая руна появится после отсчёта';$('tap-feedback').dataset.state='';
      $('resume-run').classList.add('hidden');setArc(1);setButtons(true);save();
      if(!await countdown(current,draw)||engine!==current||draw!==drawSeq||version!==generation||document.hidden)return;
      paused=false;
    }else if(paused){
      stopPreparation();expectedRune=null;setTarget('text','Пауза');$('tap-feedback').textContent='Продолжи, когда будешь готов';$('resume-run').classList.remove('hidden');setButtons(true);save();return;
    }
    expectedRune=view.rune;setTarget('glyph',glyph(view.rune),'Нажми руну '+glyph(view.rune));$('tap-feedback').textContent='Выбери такую же руну';$('tap-feedback').dataset.state='';
    $('resume-run').classList.add('hidden');setButtons(false);tick(remaining??view.window_ms,view.window_ms);
  }
  async function flushResults(){try{await store.flush(api,result=>{if(state?.run_id===result.run_id&&state.status==='finished'){if(result.rejected){$('result-status').textContent='Не удалось подтвердить результат';err(result.message);}else finish(result);}});}catch(error){if(state?.status==='finished')$('result-status').textContent=error.status===401?'Сохранено · открой игру заново в Telegram для отправки':'Сохранено на устройстве · отправим при подключении';}}
  setInterval(flushResults,5000);window.addEventListener('online',()=>{flushResults();store.refreshRules(api).catch(()=>{});});
  function finish(result) {
    state = result;
    try{localStorage.removeItem(storageKey);}catch(_){} clearInterval(timer);
    const clear = result.integrity_status === 'clear';
    const labels = { saved_local: 'Сохранено на устройстве', clear: 'Забег подтверждён', review_required: 'Результат ожидает проверки',
      quarantined: 'Результат не допущен в таблицу сезона', legacy_unverified: 'Старый результат без проверки' };
    connection(clear ? '●' : '◐', labels[result.integrity_status] || 'Результат сохранён, но не попал в таблицу');
    $('final-score').textContent = Number(result.score).toLocaleString('ru-RU');
    const n = Number(result.correct_taps) + Number(result.mistakes), acc = n ? (100 * result.correct_taps / n).toFixed(1) : '0';
    $('final-detail').textContent = result.correct_taps + ' из ' + n + ' нажатий верно';
    const passLine = $('pass-xp'); passLine.dataset.run = result.run_id || '';
    if (clear) window.GameMode?.passXp('rhythm', result.run_id, passLine); else passLine.hidden = true;
    const status = $('result-status');
    status.textContent = ({saved_local:'Сохранено · отправляем результат',clear:'В таблице',review_required:'На проверке',quarantined:'Вне таблицы',legacy_unverified:'Без проверки'})[result.integrity_status] || 'Без допуска';
    status.dataset.state = clear ? 'clear' : 'pending'; status.title = labels[result.integrity_status] || 'Не попал в таблицу сезона';
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
      record.textContent = a.previous_best === 0 ? 'Первый результат в таблице сезона' :
        delta > 0 ? 'Новый рекорд · +' + delta + ' очков' : 'Личный рекорд · ' + a.previous_best;
      box.append(record);
    }
    const tip = a.timeouts > a.wrong ? 'Чаще не хватало времени. Поможет дар, который добавляет время на нажатие.' :
      a.wrong > 0 ? 'Смотри на форму руны: это поможет реже путать символы.' :
      a.timing.late > a.timing.early ? 'Ты часто нажимал в самый последний момент. Старайся нажимать увереннее и раньше.' : '';
    if (tip) { const p = document.createElement('p'); p.className = 'r-result-hint'; p.textContent = tip; box.append(p); }
    const details = document.createElement('details'), title = document.createElement('summary'); details.className = 'lg-help'; title.textContent = 'Разбор забега'; details.append(title);
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
    if(!engine||engine.state.status!=='active'||paused||preparing||resolving||expectedRune===null||state?.draft)return;
    resolving=true;clearInterval(timer);const elapsed=rune===null?engine.window()+1:Math.min(60000,Math.max(0,Math.floor(engine.window()-(remaining??Math.max(0,tickEnd-performance.now())))));
    journal.push({kind:'tap',signal_no:engine.state.next_signal_no,rune,elapsed_ms:elapsed});
    const before=engine.state.score,quick=elapsed*3<=engine.window(),ok=engine.step(rune,elapsed,expectedRune);
    tapFeel(ok,engine.state.score-before,ok&&quick);remaining=engine.window();save();setButtons(true);
    try{await localDraw();}finally{resolving=false;}
  }
  async function start(mode){
    if(loading)return;loading=true;
    try{err('');leaving=false;stopPreparation();++drawSeq;clearInterval(timer);paused=true;remaining=null;expectedRune=null;
      const version=++generation;
      let packet=await store.fresh('rhythm');
      if(!packet){
        const started=await api('/runs',{method:'POST',body:JSON.stringify({mode})});
        packet=await api('/runs/'+started.run_id+'/local-packet',{method:'POST'});
      }
      if(version!==generation)return;
      store.data.template=packet;if(navigator.onLine)store.refreshRules(api).catch(()=>{});
      engine=new PVLocal.Rhythm(packet);journal=[];state={run_id:packet.run_id,status:'active'};remaining=engine.window();save();
      await localDraw({prepare:true});
    }catch(error){err(error.message);}finally{loading=false;}
  }
  const kindLabel={safe:'Надёжный',boost:'Усиление',risk:'Риск'};
  function countdown(current,draw){
    return new Promise(resolve=>{
      preparing=true;$('run').classList.add('preparing');
      let n=4;
      const finish=ok=>{clearTimeout(prepareTimer);prepareTimer=null;prepareDone=null;preparing=false;$('run').classList.remove('preparing');resolve(ok);};
      prepareDone=finish;
      const step=()=>{
        if(leaving||engine!==current||draw!==drawSeq||document.hidden||current.state.status!=='active'){finish(false);return;}
        if(n===0){finish(true);return;}
        const left=n--;setTarget('count',String(left),'Старт через '+left);prepareTimer=setTimeout(step,1000);
      };step();
    });
  }
  function offers() {
    clearInterval(timer); setButtons(true); show('choice');
    $('draft-title').textContent = 'Дар №' + state.draft.number;
    weatherLine($('draft-weather'), state.weather, 'Следующие 20 нажатий: ');
    const box = $('gifts'); box.replaceChildren();
    state.draft.offers.forEach(gift => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'lgr-card is-' + gift.kind; b.dataset.kind = gift.kind;
      for (const [tag, cls, text] of [['small', '', kindLabel[gift.kind] || ''], ['b', '', gift.name],
        ['span', 'g-plus', '＋ ' + gift.bonus], ['span', 'g-minus', '− ' + gift.cost]]) {
        const node = document.createElement(tag); node.className = cls; node.textContent = text; b.append(node);
      }
      const p = gift.preview;
      if (p) {
        const sec = ms => (ms / 1000).toFixed(2).replace('.', ',') + ' с', pct = v => v + '%';
        const changes = [['health', 'Сердца'], ['window_ms', 'Время на нажатие', sec], ['speed_percent', 'Скорость', pct],
          ['shield', 'Щиты'], ['ebb', 'Нажатий с запасом времени'], ['bloody', 'Нажатий с тройными очками'], ['revive', 'Феникс вернёт с сердцами'], ['sample_score', 'Очки за нажатие']]
          .filter(([key]) => p.before[key] !== p.after[key])
          .map(([key, label, fmt = v => v]) => label + ': ' + fmt(p.before[key]) + ' → ' + fmt(p.after[key]));
        const summary = document.createElement('span'); summary.className = 'g-fx'; summary.textContent = changes.join(' · ') || 'Следующее нажатие не меняется.'; b.append(summary);
      }
      b.onclick = () => pickGift(gift.id); box.append(b);
    });
    box_disable(false);
  }
  async function pickGift(id){
    if(!state?.draft||resolving||!state.draft.offers.some(g=>g.id===id))return;
    resolving=true;clearInterval(timer);journal.push({kind:'pick',perk_id:id});engine.pick(id);remaining=engine.window();save();box_disable(true);
    try{await localDraw({prepare:true});}finally{resolving=false;}
  }
  // Погода блока (core/rhythm_weather.py): одна строка, у всех одинаковая; без погоды строки нет.
  function weatherLine(node,w,lead){if(!node)return;node.hidden=!w;node.textContent=w?lead+w.icon+' '+w.name+' — '+w.effect:'';}
  function box_disable(flag){document.querySelectorAll('#gifts button').forEach(b=>{b.disabled=flag})}
  async function cancel(keepScreen=false){   // keepScreen: «Заново» сразу начинает новый забег, экран до игры не мелькает
    const id=state?.run_id;++generation;++drawSeq;leaving=true;clearInterval(timer);stopPreparation();expectedRune=null;engine=null;state=null;journal=[];store.data.active=null;store.save();
    if(keepScreen!==true)show('intro');if(id)api('/runs/'+id+'/cancel',{method:'POST'}).catch(()=>{});leaving=false;
  }
  function empty(text){$('leaderboard-podium').replaceChildren();const list=$('leaderboard-list');list.replaceChildren();const row=document.createElement('li');row.className='is-empty';row.textContent=text;list.append(row)}
  // Сезон: срок в подписи над результатом, призы и условия свёрнуты в «Награды сезона», прошлый сезон одной строкой под результатом
  const num=n=>Number(n||0).toLocaleString('ru-RU');
  const SEASON_PLAIN='Место в таблице для интереса: наград за него нет. Опыт Пропуска даёт сама игра, а больше всего его в режиме «Рейтинг».';
  function seasonTerms(s){const t=s.terms;return t?'Награду получают игроки, у которых от '+t.min_runs+' забегов в '+t.min_days+' разных днях и аккаунт старше '+t.min_account_days+' дней. Призовые места открываются, когда в таблице '+Object.values(t.podium_min_players).join(' / ')+' игроков.':''}
  function renderSeason(data){const s=data.season,l=data.last_season;if(!s)return;$('season-note').textContent=seasonTerms(s)||SEASON_PLAIN;$('season-rewards').closest('details').hidden=!(s.rewards||[]).length;const box=$('season-rewards');box.replaceChildren();(s.rewards||[]).forEach(r=>{const li=document.createElement('li'),place=document.createElement('b'),prize=document.createElement('span');place.textContent=r.label+' место';prize.textContent=num(r.mora)+' Моры + '+num(r.essence)+' Эссенции';li.append(place,prize);box.append(li)});const top=(s.rewards||[])[0];$('season-top').textContent=top?' · за 1 место '+num(top.mora)+' Моры':'';const last=$('season-last');last.hidden=!l;if(l)last.textContent='Прошлый сезон '+l.season+': место #'+l.place+(l.reward_mora?' · +'+num(l.reward_mora)+' Моры':'')+(l.reward_essence?' и '+num(l.reward_essence)+' Эссенции':'')}
  let knownTotal=0;   // «из N» приходит только со страницами полного топа: запоминаем, чтобы цифра в шапке не прыгала
  function personal(p){
    const note=$('leaderboard-personal');
    if(!p){$('r-place').textContent='—';$('r-best').textContent='—';$('r-place-note').textContent='место в сезоне';note.textContent='Тебя пока нет в таблице сезона. Заверши забег с очками, и он появится здесь.';return}
    if(p.total)knownTotal=p.total;
    $('r-place').textContent='#'+p.place;$('r-best').textContent=num(p.best_score);$('r-place-note').textContent=knownTotal?'место из '+knownTotal:'место в сезоне';note.textContent='';
  }
  // По умолчанию видна пятёрка лидеров; «Весь топ» листает всех игроков сезона страницами (boardPage = номер страницы)
  function list(data){
    if(data.season&&boardPage===null)renderSeason(data);
    const rows=boardPage===null?data.top.slice(0,5):data.items,target=$('leaderboard-list'),podium=$('leaderboard-podium');
    target.replaceChildren();podium.replaceChildren();
    if(!rows.length)empty('Пока нет завершённых забегов.');
    else{
      // тот же подиум и те же строки, что «Топ» в Mini App (top-board.js)
      gameTopBoardV3(podium,target,rows.map(gameTopRowV3),r=>num(r.raw.best_score),{podium:boardPage===null||boardPage===0});
    }
    personal(data.personal);more(data);
  }
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
  // «Заново» и «Выйти из забега»: если уже что-то сыграно, сначала вопрос в листе, забег на паузе (game-shell-v3.js). Нечего терять — сразу.
  const progress=()=>Boolean(engine&&engine.state.status==='active'&&engine.state.next_signal_no>1);
  const resumeRun=()=>{if(!preparing&&engine?.state.status==='active')localDraw({prepare:true});};
  const shell=window.GameShell,again=async()=>{await cancel(true);await start('normal');};
  const lose='Этот забег не сохранится: очки и сердца пропадут. Лучший результат сезона не изменится.';
  if(shell){
    $('restart-slot').append(shell.restartPill({risky:progress,pause,resume:resumeRun,onRestart:again,ask:{title:'Начать забег заново?',text:lose,confirm:'Да, начать заново'}}));
    $('exit-run').onclick=shell.guarded({risky:progress,pause,resume:resumeRun,run:()=>cancel(),ask:{title:'Выйти из забега?',text:lose,confirm:'Да, выйти'}});
  }else $('exit-run').onclick=cancel;
  $('exit-count').onclick=cancel;
  $('resume-run').onclick=resumeRun;
  window.addEventListener('pagehide',pause);document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
  buttons().forEach(b=>b.onclick=()=>sendTap(b.dataset.rune));
  $('again').onclick=()=>{engine=null;state=null;start('normal');};
  $('results-leaderboard').onclick=()=>{show('intro');refreshLeaderboard();};refreshLeaderboard();restore();shell?.mount({label:'обычный'});
})();
