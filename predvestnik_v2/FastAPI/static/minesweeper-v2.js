(() => {
  const tg=window.Telegram?.WebApp;tg?.ready();tg?.expand();
  const base=document.body.dataset.appBase||location.pathname.replace(/\/minesweeper\/?$/,'');
  const init=tg?.initData||'',session=localStorage.getItem('pv_sess')||'',headers={'Content-Type':'application/json'};if(init)headers['x-init-data']=init;if(session)headers['x-session-token']=session;
  const $=id=>document.getElementById(id),board=$('mine-board'),labels={easy:'Лёгкий',normal:'Обычный',hard:'Сложный'};
  let run=null,difficulty='normal',mode='open',known=new Map(),mines=new Set(),busy=false,pending=null,uncertain=null,ticker=null,clockAt=0,clockBase=0,longPress=null,skipClick=false;
  function haptic(kind){if(Number(tg?.version||0)>=6.1)tg.HapticFeedback?.impactOccurred(kind);}
  async function api(path,options={}){const response=await fetch(base+'/minesweeper-v2'+path,{...options,headers:{...headers,...(options.headers||{})}});const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.detail||'Не удалось связаться с сервером.');return data;}
  fetch(base+'/global-skins-v1/me',{headers}).then(response=>response.ok?response.json():null).then(skin=>window.applyGlobalSkinV1?.(skin)).catch(()=>{});
  function format(ms){const seconds=Math.max(0,Math.floor(ms/1000));return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;}
  function time(){return clockBase+(clockAt?Date.now()-clockAt:0);}
  function updateClock(){if(run)$('timer').textContent=format(time());}
  function setError(text){$('mine-hint').textContent=text||'';}
  function sync(result){
    run=result;new Set(result.revealed||[]).forEach(cell=>{if(!known.has(cell)){const item=(result.changed||[]).find(change=>change.cell===cell);if(item)known.set(cell,item.adjacent);}});
    (result.changed||[]).forEach(item=>known.set(item.cell,item.adjacent));mines=new Set(result.mines||[]);
    clockBase=Number(result.elapsed_ms||0);clockAt=result.status==='active'?Date.now():0;
    if(result.status==='active'&&!ticker)ticker=setInterval(updateClock,500);if(result.status==='won'||result.status==='lost'){clearInterval(ticker);ticker=null;clockAt=0;refreshLeaderboard();}
  }
  function status(){return !run?'Подключаемся…':run.status==='awaiting_first_open'?'Открой первую клетку':run.status==='active'?'Ищи безопасный путь':run.status==='won'?'Поле очищено!':'Мина! Попробуй ещё раз';}
  function hint(){if(!run)return 'Подключаем игровое поле…';if(uncertain)return busy?'Восстанавливаем этот же ход…':'Ответ потерян. Нажми «Восстановить ход»: повтор уйдёт с тем же номером операции.';if(run.status==='awaiting_first_open')return mode==='flag'?'Первый ход всегда открывает клетку.':'Первый ход безопасен — начинай с любого места.';if(run.status==='active')return busy?'Проверяем клетку…':mode==='open'?'Касание открывает. Удержание клетки ставит флаг.':'Режим флага: касание ставит или снимает флаг.';return run.status==='won'?'Время подтверждено сервером. Новая партия уже готова.':'Мины показаны. Новая партия уже готова.';}
  function render(){
    $('mine-status').textContent=status();setError(hint());$('new-game').textContent=uncertain?'Восстановить ход':'Новая партия';if(!run){board.replaceChildren();return;}
    $('mine-copy').textContent=`${run.label}: поле ${run.size}×${run.size}, ${run.mine_count} мин. Первый ход и клетки вокруг него всегда безопасны.`;
    $('mines-left').textContent=run.flags_left;$('opened').textContent=`${(run.revealed||[]).filter(cell=>!mines.has(cell)).length} / ${run.size*run.size-run.mine_count}`;updateClock();board.style.setProperty('--mine-size',run.size);board.replaceChildren();
    const revealed=new Set(run.revealed||[]),flags=new Set(run.flags||[]);
    for(let cell=0;cell<run.size*run.size;cell++){
      const open=revealed.has(cell),flag=flags.has(cell),mine=mines.has(cell),adjacent=known.get(cell);const button=document.createElement('button');button.type='button';button.className=`mine-cell ${open?'open':''} ${flag?'flag':''} ${mine?'mine':''} ${open&&adjacent?`n${adjacent}`:''} ${pending===cell?'pending':''}`;button.textContent=flag?'⚑':mine?'✹':open?(adjacent||''):'';button.setAttribute('role','gridcell');button.setAttribute('aria-label',flag?'Флаг':mine?'Мина':open?(adjacent?`Открытая клетка: рядом мин ${adjacent}`:'Открытая пустая клетка'):'Закрытая клетка');button.disabled=busy||Boolean(uncertain)||run.status==='won'||run.status==='lost';button.addEventListener('pointerdown',()=>{if(mode==='open'&&run.status==='active')longPress=setTimeout(()=>{skipClick=true;act(cell,'toggle_flag');},420)});['pointerup','pointerleave','pointercancel'].forEach(event=>button.addEventListener(event,()=>clearTimeout(longPress)));button.onclick=()=>{if(skipClick){skipClick=false;return;}act(cell,mode==='flag'?'toggle_flag':'open');};board.append(button);
    }
  }
  async function start(){
    clearInterval(ticker);ticker=null;busy=true;pending=null;uncertain=null;known=new Map();mines=new Set();run=null;render();
    try{sync(await api('/runs',{method:'POST',body:JSON.stringify({difficulty})}));}catch(error){setError(error.message);}finally{busy=false;render();refreshLeaderboard();}
  }
  async function submitUncertain(){
    if(!uncertain||busy)return;const request=uncertain;busy=true;pending=request.cell;render();
    try{const result=await api(`/runs/${encodeURIComponent(request.runId)}/actions`,{method:'POST',body:JSON.stringify({action_id:request.actionId,expected_revision:request.expectedRevision,kind:request.kind,cell:request.cell})});if(uncertain===request)uncertain=null;sync(result);haptic(result.status==='lost'?'heavy':result.status==='won'?'medium':'light');}
    catch(error){
      try{const current=await api(`/runs/${encodeURIComponent(request.runId)}`);sync(current);if(Number(current.revision)!==Number(request.expectedRevision)||['won','lost'].includes(current.status)){if(uncertain===request)uncertain=null;setError('Поле восстановлено с сервера: ход уже был учтён.');}else setError('Ход не подтверждён. Повтори восстановление — номер операции сохранён.');}
      catch(_){setError('Связь не восстановлена. Нажми «Восстановить ход»: повтор не создаст вторую операцию.');}
    }finally{pending=null;busy=false;render();}
  }
  async function act(cell,kind){
    if(!run||busy||uncertain)return;if(run.status==='awaiting_first_open'&&kind!=='open'){setError('Первый ход должен открыть клетку.');return;}
    uncertain={runId:run.run_id,actionId:crypto.randomUUID(),expectedRevision:run.revision,kind,cell};await submitUncertain();
  }
  function emptyLeaderboard(text){const list=$('leaderboard-list');list.replaceChildren();const row=document.createElement('li');row.textContent=text;list.append(row);}
  async function refreshLeaderboard(){
    $('leaderboard-difficulty').textContent=labels[difficulty];try{const data=await api('/leaderboard/'+difficulty);const list=$('leaderboard-list');list.replaceChildren();if(!data.top.length)emptyLeaderboard('Пока нет побед.');else data.top.forEach(row=>{const item=document.createElement('li'),place=document.createElement('span'),name=document.createElement('a'),result=document.createElement('b'),player=row.player||{};place.textContent='#'+row.place;name.textContent=player.display_name||'Игрок';name.href=base+'/?startapp=public&profile='+encodeURIComponent(player.profile_ref||'');name.setAttribute('aria-label','Открыть профиль '+name.textContent);result.textContent=format(row.best_elapsed_ms);item.append(place,name,result);list.append(item);});$('leaderboard-personal').textContent=data.personal?`Твоё место: #${data.personal.place} · ${format(data.personal.best_elapsed_ms)}`:'Победи, чтобы попасть в таблицу.';}catch(error){emptyLeaderboard('Таблица временно недоступна.');}
  }
  document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>{mode=button.dataset.mode;if(Number(tg?.version||0)>=6.1)tg.HapticFeedback?.selectionChanged();document.querySelectorAll('[data-mode]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));render();});
  document.querySelectorAll('[data-difficulty]').forEach(button=>button.onclick=()=>{if(busy||uncertain||difficulty===button.dataset.difficulty)return;difficulty=button.dataset.difficulty;document.querySelectorAll('[data-difficulty]').forEach(item=>item.setAttribute('aria-selected',String(item===button)));start();});$('new-game').onclick=()=>uncertain?submitUncertain():start();start();
})();
