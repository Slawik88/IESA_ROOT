(() => {
  const tg=window.Telegram?.WebApp;tg?.ready();tg?.expand();
  const base=document.body.dataset.appBase||location.pathname.replace(/\/minesweeper\/?$/,'');
  let session='';try{session=localStorage.getItem('pv_sess')||'';}catch(_){}
  const init=tg?.initData||'',headers={'Content-Type':'application/json'};if(init)headers['x-init-data']=init;if(session)headers['x-session-token']=session;
  const $=id=>document.getElementById(id),board=$('mine-board'),labels={easy:'Лёгкий',normal:'Обычный',hard:'Сложный'};
  let run=null,difficulty='normal',mode='open',known=new Map(),mines=new Set(),busy=false,pending=null,uncertain=null,ticker=null,clockAt=null,clockBase=0,longPress=null,skipClick=false,focusCell=0,restoreFocus=false,errorText='',pointerAt=null,leaderSeq=0,longPressDone=false,gestureCancelled=false;
  const finished=status=>['won','lost','cancelled'].includes(status);
  function haptic(kind){if(Number(tg?.version||0)>=6.1)tg.HapticFeedback?.impactOccurred(kind);}
  async function api(path,options={}){const response=await fetch(base+'/minesweeper-v2'+path,{...options,headers:{...headers,...(options.headers||{})}});const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.detail||'Не удалось связаться с сервером.');return data;}
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
  function hint(){if(errorText)return errorText;if(!run)return 'Подключаем игровое поле…';if(uncertain)return busy?'Восстанавливаем этот же ход…':'Ответ потерян. Нажми «Восстановить ход»: повтор уйдёт с тем же номером операции.';if(run.status==='awaiting_first_open')return mode==='flag'?'Первый ход всегда открывает клетку.':'Первый ход безопасен — начинай с любого места.';if(run.status==='active')return busy?'Проверяем клетку…':mode==='open'?'Касание открывает. Удержание клетки ставит флаг.':'Режим флага: касание ставит или снимает флаг.';if(run.status==='cancelled')return 'Эта партия заменена новой. Начни новую партию.';return run.status==='won'?'Время подтверждено сервером. Новая партия уже готова.':'Мины показаны. Новая партия уже готова.';}
  function render(){
    restoreFocus = restoreFocus || board.contains(document.activeElement);
    $('mine-status').textContent=!run&&errorText?'Поле недоступно':status();$('mine-hint').textContent=hint();$('new-game').disabled=busy;$('new-game').textContent=uncertain?'Восстановить ход':!run&&errorText?'Повторить подключение':'Новая партия';if(!run){board.replaceChildren();return;}
    $('mine-copy').textContent=`${run.label}: поле ${run.size}×${run.size}, Мин на поле: ${run.mine_count}. Первый ход и клетки вокруг него всегда безопасны.`;
    $('mines-left').textContent=run.mine_count;$('opened').textContent=`${(run.revealed||[]).filter(cell=>!mines.has(cell)).length} / ${run.size*run.size-run.mine_count}`;updateClock();board.style.setProperty('--mine-size',run.size);board.replaceChildren();
    const revealed=new Set(run.revealed||[]),flags=new Set(run.flags||[]);
    board.setAttribute('aria-rowcount',run.size);board.setAttribute('aria-colcount',run.size);
    let row;focusCell=Math.min(focusCell,run.size*run.size-1);
    for(let cell=0;cell<run.size*run.size;cell++){
      if(cell%run.size===0){row=document.createElement('div');row.className='mine-row';row.setAttribute('role','row');board.append(row);}
      const open=revealed.has(cell),flag=flags.has(cell),mine=mines.has(cell),wrongFlag=run.status==='lost'&&flag&&!mine,adjacent=known.get(cell);
      const button=document.createElement('button');button.type='button';button.dataset.cell=cell;
      button.className=`mine-cell ${open?'open':''} ${flag?'flag':''} ${mine?'mine':''} ${wrongFlag?'wrong-flag':''} ${open&&!mine&&adjacent?`n${adjacent}`:''} ${pending===cell?'pending':''}`;
      button.textContent=wrongFlag?'×':mine?'✹':flag?'⚑':open?(adjacent||''):'';
      button.setAttribute('role','gridcell');button.setAttribute('aria-rowindex',Math.floor(cell/run.size)+1);button.setAttribute('aria-colindex',cell%run.size+1);
      button.setAttribute('aria-label',`Строка ${Math.floor(cell/run.size)+1}, столбец ${cell%run.size+1}: `+(wrongFlag?'Ошибочный флаг, мины нет':mine?'Мина':flag?'Флаг':open?(adjacent?`рядом мин ${adjacent}`:'Открытая пустая клетка'):'Закрытая клетка'));
      button.tabIndex=cell===focusCell?0:-1;button.disabled=busy||Boolean(uncertain)||finished(run.status);
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
    if(restoreFocus&&!busy&&!uncertain){if(document.activeElement&&document.activeElement!==document.body&&!board.contains(document.activeElement)){restoreFocus=false;return;}board.querySelector(`[data-cell="${focusCell}"]`)?.focus({preventScroll:true});restoreFocus=false;}
  }
  async function start(resumeExisting=false){
    if(busy)return;
    errorText='';focusCell=0;restoreFocus=false;clearTimeout(longPress);longPressDone=false;gestureCancelled=false;pointerAt=null;clearInterval(ticker);ticker=null;busy=true;pending=null;uncertain=null;known=new Map();mines=new Set();run=null;render();
    try{const result=await api('/runs',{method:'POST',body:JSON.stringify({difficulty,resume_existing:resumeExisting})});sync(result);difficulty=result.difficulty||difficulty;document.querySelectorAll('[data-difficulty]').forEach(item=>item.setAttribute('aria-selected',String(item.dataset.difficulty===difficulty)));}catch(error){setError(error.message);}finally{busy=false;render();refreshLeaderboard();}
  }
  async function submitUncertain(){
    if(!uncertain||busy)return;const request=uncertain;errorText='';busy=true;pending=request.cell;render();
    try{const delivered=await api(`/runs/${encodeURIComponent(request.runId)}/actions`,{method:'POST',body:JSON.stringify({action_id:request.actionId,expected_revision:request.expectedRevision,kind:request.kind,cell:request.cell})});const result=delivered.idempotent_replay?await api(`/runs/${encodeURIComponent(request.runId)}`):delivered;sync(result);if(uncertain===request)uncertain=null;haptic(result.status==='lost'?'heavy':result.status==='won'?'medium':'light');}
    catch(error){
      try{const current=await api(`/runs/${encodeURIComponent(request.runId)}`);sync(current);if(Number(current.revision)!==Number(request.expectedRevision)||finished(current.status)){if(uncertain===request)uncertain=null;setError(current.status==='cancelled'?'Эта партия заменена новой. Начни новую партию.':'Поле восстановлено с сервера. Проверь состояние клеток.');}else setError('Ход не подтверждён. Повтори восстановление — номер операции сохранён.');}
      catch(_){setError('Связь не восстановлена. Нажми «Восстановить ход»: повтор не создаст вторую операцию.');}
    }finally{pending=null;busy=false;render();}
  }
  async function act(cell,kind){
    if(!run||busy||uncertain||finished(run.status))return;errorText='';if(run.status==='awaiting_first_open')kind='open';
    uncertain={runId:run.run_id,actionId:crypto.randomUUID(),expectedRevision:run.revision,kind,cell};await submitUncertain();
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
  document.querySelectorAll('[data-difficulty]').forEach(button=>button.onclick=()=>{if(busy||uncertain||difficulty===button.dataset.difficulty)return;difficulty=button.dataset.difficulty;document.querySelectorAll('[data-difficulty]').forEach(item=>item.setAttribute('aria-selected',String(item===button)));start();});$('new-game').onclick=()=>uncertain?submitUncertain():start(!run);start(true);
})();
