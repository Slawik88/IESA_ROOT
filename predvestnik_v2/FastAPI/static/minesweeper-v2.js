(() => {
  const tg=window.Telegram?.WebApp;tg?.ready();tg?.expand();
  const base=document.body.dataset.appBase||location.pathname.replace(/\/minesweeper\/?$/,'');
  let session='';try{session=localStorage.getItem('pv_sess')||'';}catch(_){}
  const init=tg?.initData||new URLSearchParams(location.hash?.slice(1)||'').get('tgWebAppData')||'',headers={'Content-Type':'application/json'};if(init)headers['x-init-data']=init;if(session)headers['x-session-token']=session;
  const $=id=>document.getElementById(id),board=$('mine-board'),labels={easy:'Лёгкий',normal:'Обычный',hard:'Сложный'};
  let run=null,difficulty='normal',mode='open',known=new Map(),mines=new Set(),busy=false,ticker=null,clockAt=null,clockBase=0,longPress=null,skipClick=false,focusCell=0,restoreFocus=false,errorText='',pointerAt=null,leaderSeq=0,longPressDone=false,gestureCancelled=false;
  const store=new PVLocal.Store('minesweeper',tg,session,init);let engine=null,journal=[];
  const finished=status=>['won','lost','cancelled'].includes(status);
  function haptic(kind){if(Number(tg?.version||0)>=6.1)tg.HapticFeedback?.impactOccurred(kind);}
  async function api(path,options={}){const response=await PVLocal.request(base+'/minesweeper-v2'+path,{...options,headers:{...headers,...(options.headers||{})}});const data=await response.json().catch(()=>({}));if(!response.ok){const error=new Error(data.detail||'Не удалось связаться с сервером.');error.status=response.status;throw error;}return data;}
  if('serviceWorker' in navigator)navigator.serviceWorker.register(base+'/local-games-sw.js',{scope:base+'/'}).catch(()=>{});
  fetch(base+'/skins-v3/me',{headers}).then(response=>response.ok?response.json():null).then(skin=>window.applyGlobalSkinV3?.(skin)).catch(()=>{});
  function format(ms){const seconds=Math.max(0,Math.floor(ms/1000));return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;}
  function time(){return clockBase+(clockAt!==null?performance.now()-clockAt:0);}
  function updateClock(){if(run)$('timer').textContent=format(time());}
  function setError(text){errorText=text||'';$('mine-hint').textContent=errorText;}
  function sync(result){
    const bad=()=>{throw new Error('Сервер вернул неполное поле. Попробуй восстановить связь.');};
    if(!result||typeof result.run_id!=='string'||!result.run_id||![6,9].includes(result.size)||!['awaiting_first_open','active','won','lost','cancelled'].includes(result.status)||!Number.isInteger(result.revision)||result.revision<0)bad();
    const cellOk=cell=>Number.isInteger(cell)&&cell>=0&&cell<result.size*result.size;
    if(!['revealed','flags','mines','changed'].every(key=>Array.isArray(result[key]))||!['revealed','flags','mines'].every(key=>result[key].every(cellOk)))bad();
    const nextKnown=run?.run_id===result.run_id?new Map(known):new Map(),nextMines=new Set(result.mines);
    for(const item of result.changed){if(!item||!cellOk(item.cell)||!Number.isInteger(item.adjacent)||item.adjacent<0||item.adjacent>8)bad();nextKnown.set(item.cell,item.adjacent);}
    if(result.revealed.some(cell=>!nextMines.has(cell)&&!nextKnown.has(cell)))bad();
    run=result;known=nextKnown;mines=nextMines;
    clockBase=Number(result.elapsed_ms||0);clockAt=result.status==='active'?performance.now():null;
    if(result.status==='active'&&!ticker)ticker=setInterval(updateClock,500);if(finished(result.status)){clearInterval(ticker);ticker=null;clockAt=null;if(result.status!=='cancelled')refreshLeaderboard();}
  }
  function status(){return !run?'Подключаемся…':run.status==='awaiting_first_open'?'Открой первую клетку':run.status==='active'?'Ищи безопасный путь':run.status==='won'?'Поле очищено!':run.status==='cancelled'?'Партия закрыта':'Мина! Попробуй ещё раз';}
  function hint(){if(errorText)return errorText;if(!run)return 'Подключаем игровое поле…';if(run.status==='awaiting_first_open')return mode==='flag'?'Первый ход всегда открывает клетку.':'Первый ход безопасен — начинай с любого места.';if(run.status==='active')return busy?'Проверяем клетку…':mode==='open'?'Касание открывает. Удержание клетки ставит флаг.':'Режим флага: касание ставит или снимает флаг.';if(run.status==='cancelled')return 'Эта партия заменена новой. Начни новую партию.';if(store.data.outbox.some(r=>r.run_id===run.run_id))return 'Сохранено на устройстве. Результат отправится при подключении. Можно играть дальше.';return run.status==='won'?'Победа сохранена. Можно начать новую партию.':'Мины показаны. Можно начать новую партию.';}
  function render(){
    restoreFocus = restoreFocus || board.contains(document.activeElement);
    $('mine-status').textContent=!run&&errorText?'Поле недоступно':status();$('mine-hint').textContent=hint();$('new-game').disabled=busy;$('new-game').textContent=!run&&errorText?'Повторить подключение':'Новая партия';if(!run){board.replaceChildren();return;}
    $('mine-copy').textContent=`${run.label}: поле ${run.size}×${run.size}, Мин на поле: ${run.mine_count}. Первый ход и клетки вокруг него всегда безопасны.`;
    $('mines-left').textContent=Math.max(0,run.mine_count-(run.flags||[]).length);$('opened').textContent=`${(run.revealed||[]).filter(cell=>!mines.has(cell)).length} / ${run.size*run.size-run.mine_count}`;updateClock();board.style.setProperty('--mine-size',run.size);board.replaceChildren();
    const revealed=new Set(run.revealed||[]),flags=new Set(run.flags||[]);
    board.setAttribute('aria-rowcount',run.size);board.setAttribute('aria-colcount',run.size);
    let row;focusCell=Math.min(focusCell,run.size*run.size-1);
    for(let cell=0;cell<run.size*run.size;cell++){
      if(cell%run.size===0){row=document.createElement('div');row.className='mine-row';row.setAttribute('role','row');board.append(row);}
      const open=revealed.has(cell),flag=flags.has(cell),mine=mines.has(cell),wrongFlag=run.status==='lost'&&flag&&!mine,adjacent=known.get(cell);
      const button=document.createElement('button');button.type='button';button.dataset.cell=cell;
      button.className=`mine-cell ${open?'open':''} ${flag?'flag':''} ${mine?'mine':''} ${wrongFlag?'wrong-flag':''} ${open&&!mine&&adjacent?`n${adjacent}`:''}`;
      button.textContent=wrongFlag?'×':mine?'✹':flag?'⚑':open?(adjacent||''):'';
      button.setAttribute('role','gridcell');button.setAttribute('aria-rowindex',Math.floor(cell/run.size)+1);button.setAttribute('aria-colindex',cell%run.size+1);
      button.setAttribute('aria-label',`Строка ${Math.floor(cell/run.size)+1}, столбец ${cell%run.size+1}: `+(wrongFlag?'Ошибочный флаг, мины нет':mine?'Мина':flag?'Флаг':open?(adjacent?`рядом мин ${adjacent}`:'Открытая пустая клетка'):'Закрытая клетка'));
      button.tabIndex=cell===focusCell?0:-1;button.disabled=busy||finished(run.status);
      button.addEventListener('focus',()=>{focusCell=cell;board.querySelectorAll('.mine-cell').forEach(b=>b.tabIndex=b===button?0:-1);});
      button.addEventListener('keydown',event=>{
        if(event.key==='f'||event.key==='F'||event.key==='ContextMenu'||(event.key==='F10'&&event.shiftKey)){event.preventDefault();clearTimeout(longPress);if(run.status==='active')act(cell,'toggle_flag');return;}
        let next=cell;const col=cell%run.size;
        if(event.key==='ArrowLeft')next=cell-Math.min(1,col);
        else if(event.key==='ArrowRight')next=cell+Math.min(1,run.size-1-col);
        else if(event.key==='ArrowUp')next=Math.max(col,cell-run.size);
        else if(event.key==='ArrowDown')next=Math.min((run.size-1)*run.size+col,cell+run.size);
        else if(event.key==='Home')next=event.ctrlKey?0:cell-col;
        else if(event.key==='End')next=event.ctrlKey?run.size*run.size-1:cell-col+run.size-1;
        else return;
        event.preventDefault();board.querySelector(`[data-cell="${next}"]`)?.focus();
      });
      button.addEventListener('pointerdown',event=>{clearTimeout(longPress);longPressDone=false;gestureCancelled=false;skipClick=false;focusCell=cell;if(event.button!==undefined&&event.button!==0){pointerAt=null;return;}pointerAt={x:event.clientX,y:event.clientY};
        if(mode==='open'&&run.status==='active')longPress=setTimeout(()=>{longPressDone=true;skipClick=true;pointerAt=null;act(cell,'toggle_flag');},420);
      });
      button.addEventListener('pointermove',event=>{if(pointerAt&&Math.hypot(event.clientX-pointerAt.x,event.clientY-pointerAt.y)>8){clearTimeout(longPress);gestureCancelled=true;skipClick=true;}});
      ['pointerup','pointerleave','pointercancel'].forEach(event=>button.addEventListener(event,()=>{clearTimeout(longPress);if(event==='pointercancel'||(event==='pointerleave'&&pointerAt)){gestureCancelled=true;skipClick=true;}pointerAt=null;}));
      button.addEventListener('contextmenu',event=>{event.preventDefault();clearTimeout(longPress);pointerAt=null;skipClick=true;if(gestureCancelled||longPressDone)return;longPressDone=true;if(run.status==='active')act(cell,'toggle_flag');});
      button.onclick=event=>{if(event?.detail===0){skipClick=false;gestureCancelled=false;}if(skipClick||gestureCancelled){skipClick=false;return;}focusCell=cell;act(cell,mode==='flag'?'toggle_flag':'open');};row.append(button);
    }
    if(restoreFocus&&!busy){if(document.activeElement&&document.activeElement!==document.body&&!board.contains(document.activeElement)){restoreFocus=false;return;}board.querySelector(`[data-cell="${focusCell}"]`)?.focus({preventScroll:true});restoreFocus=false;}
  }
  function saveLocal(){if(engine){engine.state.elapsed_ms=Math.floor(time());store.data.active={packet:engine.packet,state:engine.state,first:engine.first,journal};store.save();}}
  async function flushResults(){try{await store.flush(api,result=>{if(result.rejected&&run?.run_id===result.run_id){setError('Сервер не подтвердил результат: '+result.message);render();}else{refreshLeaderboard();render();}});}catch(error){if(error.status===401&&run&&finished(run.status)){setError('Результат сохранён. Открой игру заново в Telegram для отправки.');render();}} }
  setInterval(flushResults,5000);window.addEventListener('online',()=>{flushResults();store.refreshRules(api).catch(()=>{});});
  async function start(resumeExisting=false){
    if(busy)return;errorText='';busy=true;render();
    try{
      let packet=resumeExisting?null:await store.fresh('minesweeper',difficulty);
      if(!packet){
        const started=await api('/runs',{method:'POST',body:JSON.stringify({difficulty,resume_existing:resumeExisting})});
        packet=await api('/runs/'+started.run_id+'/local-packet',{method:'POST'});
      }
      store.data.template=packet;if(navigator.onLine)store.refreshRules(api).catch(()=>{});
      engine=new PVLocal.Mines(packet);journal=[];focusCell=0;restoreFocus=false;known=new Map();mines=new Set();
      sync(engine.state);difficulty=engine.state.difficulty;saveLocal();
      document.querySelectorAll('[data-difficulty]').forEach(item=>item.setAttribute('aria-selected',String(item.dataset.difficulty===difficulty)));
    }catch(error){setError('Для загрузки новой партии нужна связь. Текущая игра сохранена. '+error.message);}
    finally{busy=false;render();refreshLeaderboard();}
  }
  async function act(cell,kind){
    if(!run||!engine||busy||finished(run.status))return;errorText='';
    if(run.status==='awaiting_first_open')kind='open';
    const elapsed=run.status==='awaiting_first_open'?0:Math.floor(time());
    journal.push({kind,cell,elapsed_ms:elapsed});const result=engine.step(cell,kind,elapsed);
    sync(result);saveLocal();render();haptic(result.status==='lost'?'heavy':result.status==='won'?'medium':'light');
    if(finished(result.status)){store.data.last={packet:engine.packet,state:engine.state,first:engine.first,journal};store.queue(engine.packet,journal);flushResults();}
    if(!store.durable)setError('Не удалось сохранить игру на устройстве. Не закрывай приложение.');
  }
  function pause(){if(!engine||finished(engine.state.status))return;clockBase=Math.floor(time());clockAt=null;saveLocal();}
  window.addEventListener('pagehide',pause);document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();else if(run?.status==='active')clockAt=performance.now();});
  function restore(){
    const active=store.data.active||(store.data.outbox.length?store.data.last:null);
    if(active?.packet?.protocol==='resilient-local-v1'){
      store.data.template=active.packet;engine=new PVLocal.Mines(active.packet,active.state,active.first);journal=active.journal||[];sync(engine.state);difficulty=run.difficulty;
      document.querySelectorAll('[data-difficulty]').forEach(item=>item.setAttribute('aria-selected',String(item.dataset.difficulty===difficulty)));render();
      if(finished(run.status)){store.data.last={packet:engine.packet,state:engine.state,first:engine.first,journal};store.queue(engine.packet,journal);flushResults();}
    }else start(!store.data.template);
    flushResults();if(navigator.onLine)store.refreshRules(api).catch(()=>{});
  }
  function seasonRewards(data){const box=$('season-rewards');if(!box)return;box.replaceChildren();((data.season||{}).rewards||[]).forEach(r=>{const li=document.createElement('li'),a=document.createElement('b'),b=document.createElement('span');a.textContent='Место '+r.label;b.textContent=r.mora+' Моры · '+r.essence+' Эссенции';li.append(a,b);box.append(li)})}
  function seasonNote(data){const s=data.season,l=data.last_season;if(!s)return '';const end=new Date(s.ends_at).toLocaleDateString('ru-RU'),left=s.days_left;let t='Сезон '+s.number+' · до '+end+' · осталось '+left+' дн.';const top=(s.rewards||[])[0];if(top)t+=' · Топ-1: '+top.mora+' Моры и '+top.essence+' Эссенции';if(s.paying===false)t+=' · Награды за места в Сапёре пока не выдаются';if(l)t+=' · Прошлый сезон '+l.season+': место #'+l.place+(l.reward_mora?' · +'+l.reward_mora+' Моры':'')+(l.reward_essence?' и '+l.reward_essence+' Эссенции':'');return t}
  function emptyLeaderboard(text){const list=$('leaderboard-list');list.replaceChildren();const row=document.createElement('li');row.textContent=text;list.append(row);}
  async function refreshLeaderboard(){
    const seq=++leaderSeq,selected=difficulty;
    $('leaderboard-difficulty').textContent=labels[selected];try{const data=await api('/leaderboard/'+selected);if(seq!==leaderSeq||selected!==difficulty)return;$('season-note').textContent=seasonNote(data);seasonRewards(data);const list=$('leaderboard-list');list.replaceChildren();if(!data.top.length)emptyLeaderboard('Пока нет побед.');else data.top.forEach(row=>{const item=document.createElement('li'),place=document.createElement('span'),name=document.createElement('a'),result=document.createElement('b'),player=row.player||{};place.textContent='#'+row.place;name.innerHTML=window.gameWhoV3?window.gameWhoV3(player):'';if(!name.innerHTML)name.textContent=player.display_name||'Игрок';name.href=base+'/?startapp=public&profile='+encodeURIComponent(player.profile_ref||'');name.setAttribute('aria-label','Открыть профиль '+(player.display_name||'Игрок'));result.textContent=format(row.best_elapsed_ms);if(row.is_me)item.className='is-me';item.append(place,name,result);list.append(item);});$('leaderboard-personal').textContent=data.personal?`Твоё место: #${data.personal.place} · ${format(data.personal.best_elapsed_ms)}`:'Победи, чтобы попасть в таблицу.';}catch(error){if(seq===leaderSeq&&selected===difficulty)emptyLeaderboard('Таблица временно недоступна.');}
  }
  $('mine-view-toggle').onclick=()=>{const large=document.body.dataset.mineZoom!=='large';document.body.dataset.mineZoom=large?'large':'fit';$('mine-view-toggle').setAttribute('aria-pressed',String(large));$('mine-view-toggle').textContent=large?'Показать всё поле':'Крупные клетки';$('mine-view-label').textContent=large?'Прокручивай поле вбок':'Поле целиком';};
  document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>{mode=button.dataset.mode;if(Number(tg?.version||0)>=6.1)tg.HapticFeedback?.selectionChanged();document.querySelectorAll('[data-mode]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));render();});
  document.querySelectorAll('[data-difficulty]').forEach(button=>button.onclick=()=>{if(busy||difficulty===button.dataset.difficulty)return;difficulty=button.dataset.difficulty;document.querySelectorAll('[data-difficulty]').forEach(item=>item.setAttribute('aria-selected',String(item===button)));start();});$('new-game').onclick=()=>start(!run);restore();
})();
