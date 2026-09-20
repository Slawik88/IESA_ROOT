(() => {
  const tg = window.Telegram?.WebApp; tg?.ready(); tg?.expand();
  const base = document.body.dataset.appBase || location.pathname.replace(/\/rhythm-v2\/?$/, '');
  const init = tg?.initData || '', session = localStorage.getItem('pv_sess') || '', headers = {'Content-Type':'application/json'};
  if (init) headers['x-init-data'] = init;
  if (session) headers['x-session-token'] = session;
  const $ = id => document.getElementById(id), storageKey = 'predvestnik-rhythm-v2-live';
  let state = null, socket = null, pendingTap = null, selection = {positive:new Set(), negative:new Set()}, timer = null, reconnectTimer = null, reconnectAttempt = 0, leaderboardMode = 'normal', leaving = false;
  const show = id => ['intro','choice','run','result'].forEach(x => $(x).classList.toggle('hidden', x !== id));
  const glyph = rune => ({left:'ᚠ',center:'ᚱ',right:'ᚦ'}[rune] || '—');
  const buttons = () => [...document.querySelectorAll('[data-rune]')];
  const err = text => { $('error').textContent = text || ''; };
  async function api(path, options={}) { const response=await fetch(base+'/rhythm-v2'+path,{...options,headers:{...headers,...(options.headers||{})}}); const data=await response.json().catch(()=>({})); if(!response.ok) throw new Error(data.detail||'Не удалось связаться с сервером.'); return data; }
  fetch(base+'/global-skins-v1/me',{headers}).then(response=>response.ok?response.json():null).then(skin=>window.applyGlobalSkinV1?.(skin)).catch(()=>{});
  function save(){ if(state?.run_id&&['choosing','active'].includes(state.status))localStorage.setItem(storageKey,JSON.stringify({state}));else localStorage.removeItem(storageKey); }
  function setButtons(disabled, selected=null){buttons().forEach(b=>{b.disabled=disabled;b.classList.toggle('pending',b.dataset.rune===selected&&disabled)})}
  function connection(mark,text){$('connection').textContent=mark;$('connection').setAttribute('aria-label',text)}
  function tick(remaining,windowMs){clearInterval(timer);const started=performance.now(),duration=Math.max(0,Number(remaining)||0),full=Math.max(1,Number(windowMs)||1);const go=()=>{const left=Math.max(0,(duration-(performance.now()-started))/full);$('timebar').style.transform='scaleX('+left+')';if(left===0){clearInterval(timer);setButtons(true);$('tap-feedback').textContent='Время вышло · жду следующий такт';$('tap-feedback').dataset.state='pending'}};go();timer=setInterval(go,33)}
  function finish(result){
    state=result;pendingTap=null;localStorage.removeItem(storageKey);clearInterval(timer);clearTimeout(reconnectTimer);if(socket){socket.onclose=null;socket.close();socket=null}const pendingReview=result.integrity_status==='review_required';connection(pendingReview?'◐':'●',pendingReview?'Забег ожидает проверки':'Забег подтверждён проверкой');$('final-score').textContent=result.score+' очков';$('final-detail').textContent='Точность: '+result.correct_taps+' · ошибок: '+result.mistakes+(pendingReview?' · результат сохранён и появится в рейтинге только после проверки.':' · результат подтверждён проверкой.');leaderboardMode=result.mode;show('result');refreshLeaderboard();
  }
  function drawLive(next){
    const previousSignal=Number(state?.next_signal_no||0);state={...(state||{}),...next};save();connection('●','Связь с игровым сервером установлена');err('');
    if(state.status==='finished')return finish(state);if(state.status!=='active')return;
    if(pendingTap&&Number(state.next_signal_no)!==Number(pendingTap.signal_no))pendingTap=null;
    $('health').textContent='♥'.repeat(state.health)||'—';$('score').textContent=state.score;$('combo').textContent=state.combo;$('speed').textContent=state.speed_percent+'%';$('instruction').textContent='Нажми руну '+glyph(state.rune);$('run-note').textContent='Такт '+state.next_signal_no+' · чанк '+state.chunk+' · окно '+state.window_ms+' мс';
    if(!pendingTap||previousSignal!==Number(state.next_signal_no)){$('tap-feedback').textContent='Выбери руну';$('tap-feedback').dataset.state=''}
    setButtons(Boolean(pendingTap)||socket?.readyState!==WebSocket.OPEN,pendingTap?.rune||null);show('run');tick(state.remaining_ms,state.window_ms);
    if(pendingTap&&Number(state.next_signal_no)===Number(pendingTap.signal_no)&&socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'tap',signal_no:pendingTap.signal_no,rune:pendingTap.rune,action_id:pendingTap.actionId}));
  }
  function scheduleReconnect(message){
    if(leaving||!state?.run_id||state.status!=='active')return;clearTimeout(reconnectTimer);connection('○','Переподключение к игровому серверу');err(message||'Связь прервалась. Восстанавливаю этот же забег…');const wait=Math.min(4000,350*(2**reconnectAttempt++));reconnectTimer=setTimeout(()=>connectTransport(),wait);
  }
  async function connectTransport(){
    if(leaving||!state?.run_id)return;try{const issued=await api('/runs/'+state.run_id+'/transport-ticket',{method:'POST'});const target=new URL(base+'/rhythm-v2/runs/'+encodeURIComponent(state.run_id)+'/live',location.origin);target.protocol=location.protocol==='https:'?'wss:':'ws:';const ws=new WebSocket(target);socket=ws;connection('○','Подключение к игровому серверу');ws.onopen=()=>ws.send(JSON.stringify({type:'authenticate',ticket:issued.ticket}));ws.onmessage=event=>{let message;try{message=JSON.parse(event.data)}catch(_){return}if(message?.type==='state'){reconnectAttempt=0;drawLive(message.state)}};ws.onerror=()=>{};ws.onclose=()=>{if(socket===ws)socket=null;scheduleReconnect('Связь прервалась. Восстанавливаю этот же забег…')};}catch(error){scheduleReconnect(error.message)}
  }
  function sendTap(rune){
    if(!state||state.status!=='active'||pendingTap||socket?.readyState!==WebSocket.OPEN)return;pendingTap={signal_no:Number(state.next_signal_no),rune,actionId:crypto.randomUUID()};clearInterval(timer);setButtons(true,rune);$('tap-feedback').textContent='Сервер проверяет такт…';$('tap-feedback').dataset.state='pending';socket.send(JSON.stringify({type:'tap',signal_no:pendingTap.signal_no,rune:pendingTap.rune,action_id:pendingTap.actionId}));
  }
  async function start(mode){try{err('');leaving=false;selection={positive:new Set(),negative:new Set()};state=await api('/runs',{method:'POST',body:JSON.stringify({mode})});save();if(state.status==='choosing')return offers();await connectTransport()}catch(error){err(error.message)}}
  function offers(){show('choice');for(const [polarity,title] of [['positive','ДАРЫ · выбери 2'],['negative','ИСПЫТАНИЯ · выбери 2']]){const box=$(polarity);box.innerHTML='<h3>'+title+'</h3>';state.offers[polarity].forEach(id=>{const b=document.createElement('button');b.className='augment';b.dataset.polarity=polarity;b.textContent=id.replaceAll('_',' ');b.onclick=()=>{const set=selection[polarity];set.has(id)?set.delete(id):(set.size<2&&set.add(id));box.querySelectorAll('button').forEach(x=>x.classList.toggle('chosen',set.has(state.offers[polarity][[...box.querySelectorAll('button')].indexOf(x)])));$('confirm').disabled=selection.positive.size!==2||selection.negative.size!==2};box.append(b)})}}
  async function confirm(){try{state=await api('/runs/'+state.run_id+'/augmentations',{method:'POST',body:JSON.stringify({positive:[...selection.positive],negative:[...selection.negative]})});save();await connectTransport()}catch(error){err(error.message)}}
  async function cancel(){if(!state?.run_id)return;try{leaving=true;clearTimeout(reconnectTimer);if(socket){socket.onclose=null;socket.close();socket=null}await api('/runs/'+state.run_id+'/cancel',{method:'POST'});clearInterval(timer);pendingTap=null;state=null;localStorage.removeItem(storageKey);show('intro');err('Забег отменён.')}catch(error){err(error.message)}finally{leaving=false}}
  function cancelOnPageExit(){
    if(!state?.run_id||leaving)return;
    leaving=true;
    localStorage.removeItem(storageKey);clearTimeout(reconnectTimer);if(socket){socket.onclose=null;socket.close();socket=null}
    fetch(base+'/rhythm-v2/runs/'+encodeURIComponent(state.run_id)+'/cancel',{method:'POST',headers,keepalive:true}).catch(()=>{});
  }
  function empty(text){const list=$('leaderboard-list');list.replaceChildren();const row=document.createElement('li');row.className='leaderboard-empty';row.textContent=text;list.append(row)}
  function list(data){const target=$('leaderboard-list');target.replaceChildren();if(!data.top.length)empty('Пока нет завершённых забегов.');else data.top.forEach(row=>{const item=document.createElement('li'),p=document.createElement('span'),name=document.createElement('a'),score=document.createElement('b'),player=row.player||{};p.textContent='#'+row.place;name.textContent=player.display_name||'Игрок';name.href=base+'/?startapp=public&profile='+encodeURIComponent(player.profile_ref||'');name.setAttribute('aria-label','Открыть профиль '+name.textContent);score.textContent=row.best_score;item.append(p,name,score);target.append(item)});$('leaderboard-personal').textContent=data.personal?'Ваше место: #'+data.personal.place+' · '+data.personal.best_score+' очков':'Ваш результат появится после первого завершённого забега.';document.querySelectorAll('[data-leaderboard-mode]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.leaderboardMode===leaderboardMode)))}
  async function refreshLeaderboard(){try{list(await api('/leaderboard/'+leaderboardMode))}catch(error){empty(init?'Таблица временно недоступна.':'Войдите через Telegram, чтобы увидеть результаты.')}}
  function restore(){try{const saved=JSON.parse(localStorage.getItem(storageKey)||'null');if(saved?.state?.run_id){state=saved.state;if(state.status==='choosing')offers();else if(state.status==='active')connectTransport()}}catch(_){localStorage.removeItem(storageKey)}}
  localStorage.removeItem('predvestnik-rhythm-v2-local');document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>start(b.dataset.mode));$('confirm').onclick=confirm;$('exit-run').onclick=cancel;window.addEventListener('pagehide',cancelOnPageExit);buttons().forEach(b=>b.onclick=()=>sendTap(b.dataset.rune));$('again').onclick=()=>{state=null;pendingTap=null;selection={positive:new Set(),negative:new Set()};show('intro');refreshLeaderboard()};$('results-leaderboard').onclick=()=>{show('intro');refreshLeaderboard()};document.querySelectorAll('[data-leaderboard-mode]').forEach(b=>b.onclick=()=>{leaderboardMode=b.dataset.leaderboardMode;refreshLeaderboard()});refreshLeaderboard();restore();
})();
