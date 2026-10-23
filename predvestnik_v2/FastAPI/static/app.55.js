// Межчатовая Мафия · один контроллер комнаты, отмена опроса и восстановление соединения.
const MO = {gen:0, room:0, channel:'table', data:null, timer:null, clock:null, abort:null, busy:false,
  messages:new Map(), draft:'', nonce:'', reply:null, statusKey:'', errors:0};
const MO_ROLE = {citizen:'Мирный житель',mafia:'Мафия',don:'Дон',doctor:'Доктор',detective:'Детектив'};
const MO_PHASE = {lobby:'Сбор игроков',night:'Ночь',discussion:'Обсуждение',voting:'Голосование',paused:'Пауза',finished:'Итоги',cancelled:'Стол закрыт'};
function moStop(){ ++MO.gen; MO.pollSeq=(MO.pollSeq||0)+1; clearTimeout(MO.timer); clearInterval(MO.clock); MO.timer=null;MO.clock=null; MO.abort?.abort(); MO.abort=null; MO.busy=false;el('mo-root')?.removeAttribute('aria-busy'); }
function moAuth(){const h=new Headers(hdrs());return JSON.stringify(['x-init-data','x-session-token','x-preprod-browser-ticket'].map(k=>h.get(k)||''));}
function moAlive(g){ const owner=moOwner();return g===MO.gen && (MO.auth===undefined||MO.auth===moAuth()) && (!MO.owner||!owner||MO.owner===owner) && el('mo-root')?.isConnected && el('modal').open; }
function moReady(){
  if(moAlive(MO.gen))return true;
  if(el('mo-root')?.isConnected&&el('modal')?.open){moStop();el('mo-root').innerHTML='<p class="mo-error" role="alert">Аккаунт изменился. Откройте Мафию заново.</p><button class="v3-pill" onclick="openMafiaOnline()">Открыть Мафию</button>';}
  return false;
}
async function moRequest(path, body, signal){
  const controller=new AbortController(),abort=()=>controller.abort();let timeout=false;
  if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(()=>{timeout=true;abort();},12000);
  try{
    // hdrs() already supplies lowercase content-type. A second casing is merged
    // by fetch into an invalid "application/json, application/json" value.
    const headers=new Headers(hdrs());headers.set('Content-Type','application/json');
    const r=await fetch(BASE+'/mafia-online'+path,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});
    const data=await r.json().catch(()=>({}));
    if(!r.ok){const error=new Error(typeof data.detail==='string'?data.detail:r.status===429?'Слишком много действий. Подождите немного и повторите.':r.status===401?'Вход устарел. Откройте приложение заново.':'Не удалось загрузить стол. Попробуйте снова.');error.status=r.status;throw error;}
    return data;
  }catch(e){if(timeout)throw new Error(body?.command?'Ответ на действие не пришёл. Его можно проверить.':'Ответ не пришёл. Попробуйте снова — сообщение не продублируется.');if(e.name==='TypeError')throw new Error(body?.command?'Нет связи. Проверьте действие после подключения.':'Нет связи. Текст сохранён — отправьте снова.');throw e;}
  finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
function moError(error){ return esc(String(error?.message||error||'Связь прервалась.')); }
function moShell(){
  MO.self=0;MO.owner=moOwner();MO.auth=moAuth();
  OM('Мафия','<div id="mo-root" class="mo-root"><p class="v3-empty" role="status">Собираем город…</p></div>');
  el('modal').classList.add('mo-mode');
  moViewport();
}
function moViewport(){
  const modal=el('modal');if(!modal?.classList.contains('mo-mode'))return;
  const v=window.visualViewport,height=v?.height||window.innerHeight;
  modal.style.setProperty('--mo-viewport-height',height+'px');
  modal.style.setProperty('--mo-viewport-bottom',Math.max(0,window.innerHeight-height-(v?.offsetTop||0))+'px');
  modal.classList.toggle('mo-keyboard',height<window.innerHeight*.76||(height<500&&!!document.activeElement?.closest('.mo-compose')));
}
async function openMafiaOnline(roomId=0,invite=''){
  moStop(); moShell();
  if(roomId){return moJoin(Number(roomId),invite);}
  return moHub(true);
}
async function moHub(followActive=false){
  if(MO.auth!==undefined&&MO.auth!==moAuth())return openMafiaOnline();
  moStore();moStop(); MO.room=0; MO.data=null; MO.channel='table';MO.draft='';MO.nonce='';MO.reply=null;MO.draftOwner=undefined;
  if(!el('mo-root'))moShell();
  const g=MO.gen, root=el('mo-root');
  root.innerHTML='<p class="v3-empty" role="status">Собираем город…</p>';
  try{
    const d=await moRequest(''); if(!moAlive(g))return;
    MO.launchBase=d.launch_url||'';
    MO.self=d.user_id;MO.owner=d.user_id;
    if(followActive&&d.active)return moEnter(d.active);
    root.innerHTML=`<div class="mo-hub">${v3Head('Мафия',{sub:'Один город. Игроки из разных чатов.',back:'CM()'})}
      <section class="mo-city" aria-label="Межчатовая Мафия"><img src="${BASE}/static/mafia-art/city.webp" alt="" width="800" height="400"><div><span class="v3-eyebrow">Межчатовая</span><b>Город ждёт тебя</b></div></section>
      <button type="button" class="v3-pill v3-pill--full" id="mo-quick">${d.active?'Вернуться за стол':'Играть'}</button>
      <p class="mo-caption">От 4 игроков · роль и разговор здесь</p><p id="mo-error" class="mo-error" role="alert"></p>
      <div class="v3-sec"><span class="v3-eyebrow">Открытые столы</span><button type="button" class="v3-link" onclick="moHub()">Обновить</button></div>
      <div class="mo-tables">${d.rooms.filter(r=>r.id!==d.active).map(r=>`<button type="button" class="v3-row" onclick="moJoin(${r.id})"><span>Город #${r.id}<small>${esc(r.host)} · ${{fast:'Быстро',normal:'Обычно',slow:'Неспешно'}[r.tempo]}</small></span><span class="v3-end">${r.count}/${r.seats} ›</span></button>`).join('')||`<p class="v3-empty">${d.active?'Других открытых столов пока нет.':'Первый стол будет вашим.'}</p>`}</div>
      <details class="mo-create"><summary>Свой стол</summary><form id="mo-create-form">${moSettingsMarkup()}<button class="v3-pill v3-pill--ghost" type="submit">Создать стол</button></form></details>
      ${d.history.length?`<details class="mo-history"><summary>Мои партии · ${d.history.length}</summary>${d.history.map(r=>`<button class="v3-row" onclick="moEnter(${r.id})"><span>Город #${r.id}<small>${r.winner==='town'?'Победили мирные':r.winner==='mafia'?'Победила мафия':r.winner==='draw'?'Ничья':'Стол закрыт'}</small></span><span class="v3-end">Итоги ›</span></button>`).join('')}</details>`:''}
      ${moHowto()}<button class="v3-link mo-local" onclick="openMafiaStats()">Локальная мафия · история ›</button></div>`;
    el('mo-quick').onclick=()=>moBusy(async()=>{if(d.active)return moEnter(d.active); const r=await moRequest('/quick',{}); if(moAlive(g))return moEnter(r.room_id);});
    el('mo-create-form').onsubmit=e=>{e.preventDefault();moBusy(async()=>{const r=await moRequest('/rooms',moSettingsRead(e.target));if(moAlive(g))return moEnter(r.room_id);});};
    const check=()=>{if(!moAlive(g))return;if(MO.busy||document.activeElement?.closest('.mo-create')||el('mo-root')?.querySelector('details[open]'))MO.timer=setTimeout(check,15000);else moHub();};
    MO.timer=setTimeout(check,15000);
  }catch(e){if(moAlive(g))root.innerHTML=`<p class="mo-error" role="alert">${moError(e)}</p><button class="v3-pill" onclick="moHub()">Повторить</button>`;}
}
async function moBusy(fn){
  if(!moReady())return;
  if(MO.busy)return;MO.busy=true;const g=MO.gen;
  el('mo-root')?.setAttribute('aria-busy','true');
  try{await fn();}catch(e){if(moAlive(g)){const host=el('mo-error');if(host)host.innerHTML=moError(e);else el('mo-root').innerHTML=`<p class="mo-error" role="alert">${moError(e)}</p><button class="v3-pill" onclick="moHub()">К столам</button>`;}}
  finally{if(g===MO.gen){MO.busy=false;el('mo-root')?.removeAttribute('aria-busy');}}
}
async function moJoin(id,invite=''){
  if(!el('mo-root'))moShell();
  const g=MO.gen;
  return moBusy(async()=>{const d=await moRequest('/rooms/'+id+'/join',{invite});if(moAlive(g))return moEnter(d.room_id);});
}
function moOwner(){return typeof _uid!=='undefined'&&_uid?_uid:typeof tg!=='undefined'&&tg?.initDataUnsafe?.user?.id?tg.initDataUnsafe.user.id:MO.self||0;}
function moDraftKey(){return `pv_mo_${moOwner()}_${MO.room}_${MO.channel}`;}
function moStore(){if(MO.draftOwner!==moOwner())return;try{sessionStorage.setItem(moDraftKey(),JSON.stringify({text:MO.draft,nonce:MO.nonce,reply:MO.reply}));}catch(_){}}
function moRestore(){MO.draftOwner=moOwner();try{const d=JSON.parse(sessionStorage.getItem(moDraftKey())||'{}');MO.draft=typeof d.text==='string'?d.text:'';MO.nonce=typeof d.nonce==='string'?d.nonce:'';MO.reply=d.reply&&typeof d.reply.body==='string'?d.reply:null;}catch(_){MO.draft='';MO.nonce='';MO.reply=null;}}
async function moEnter(id){
  moStop();if(!el('mo-root'))moShell();MO.room=id;MO.channel='table';MO.data=null;MO.messages.clear();MO.statusKey='';MO.redactions=0;MO.errors=0;MO.hasOlder=false;MO.settingsDraft=null;MO.settingsVersion=null;moRestore();
  el('mo-root').innerHTML=`<div class="mo-room"><div class="mo-room-head"><button class="v3-link" onclick="moHub()" aria-label="К столам">‹ Столы</button><b>Город #${Number(id)}</b><button class="v3-link" onclick="moInvite()">Позвать</button></div>
    <section id="mo-status" aria-live="polite"><p class="v3-empty">Подключаемся к столу…</p></section><p id="mo-connection" class="mo-connection" role="status"></p><button type="button" class="v3-link mo-info-toggle" id="mo-info-toggle" aria-expanded="false" aria-controls="mo-info" onclick="moToggleInfo()">Участники и управление ›</button><section id="mo-info" class="mo-info" aria-label="Участники и управление" hidden></section>
    <nav class="mo-channels" id="mo-channels" aria-label="Разговоры"></nav><div class="mo-chat" id="mo-chat" aria-label="Сообщения"><button class="v3-link" id="mo-older" onclick="moOlder()">Раньше</button><div id="mo-messages" role="log" aria-live="polite" aria-relevant="additions"></div></div>
    <button class="v3-link mo-new" id="mo-new" type="button" onclick="moLatest()" hidden>Новые сообщения ↓</button><p class="mo-error" id="mo-error" role="alert"></p><div id="mo-control-pending" class="mo-control-pending"></div><div id="mo-message-pending" class="mo-control-pending" role="status"></div><form class="mo-compose" id="mo-compose"><div id="mo-reply"></div><div class="mo-input-row"><textarea id="mo-text" rows="1" maxlength="600" aria-label="Сообщение" placeholder="Ваше сообщение…"></textarea><button class="v3-pill v3-pill--ghost" type="submit" id="mo-send" aria-label="Отправить сообщение">↑</button></div><small id="mo-write-hint"></small></form></div>`;
  el('mo-text').value=MO.draft;moReplyMarkup();
  el('mo-text').disabled=true;el('mo-send').disabled=true;
  el('mo-text').oninput=e=>{MO.draft=e.target.value;MO.nonce='';moStore();};
  el('mo-compose').onsubmit=e=>{e.preventDefault();moSend();};
  el('mo-text').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();moSend();}};
  el('mo-text').onfocus=moViewport;el('mo-text').onblur=moViewport;
  el('mo-chat').onscroll=()=>{const c=el('mo-chat');if(c.scrollHeight-c.scrollTop-c.clientHeight<60)el('mo-new').hidden=true;};
  moPendingNotice();moMessagePendingNotice();
  MO.clock=setInterval(moClock,1000);await moPoll(MO.gen);
}
async function moPoll(g){
  if(!moAlive(g)||!MO.room)return;
  const room=MO.room,channel=MO.channel,seq=MO.pollSeq=(MO.pollSeq||0)+1,controller=new AbortController();MO.abort=controller;
  try{
    const after=MO.messages.size?Math.max(...MO.messages.keys()):0;
    let d=await moRequest(`/rooms/${room}?channel=${channel}&after=${after}`,undefined,controller.signal);
    if(!moAlive(g)||seq!==MO.pollSeq||room!==MO.room||channel!==MO.channel)return;
    if(after&&d.redactions!==MO.redactions)d=await moRequest(`/rooms/${room}?channel=${channel}`,undefined,controller.signal);
    if(!moAlive(g)||seq!==MO.pollSeq||room!==MO.room||channel!==MO.channel)return;
    if(!d?.me||!Array.isArray(d.players)||!Array.isArray(d.messages)||!Array.isArray(d.channels)||!Number.isFinite(d.version))throw new Error('Стол ответил не полностью. Подключаемся заново.');
    if(!MO.owner){MO.owner=d.me.id;MO.self=d.me.id;moRestore();if(el('mo-text'))el('mo-text').value=MO.draft;moReplyMarkup();moMessagePendingNotice();}
    if(!MO.data||d.version>=MO.data.version){MO.data=d;MO.errors=0;moRenderRoom(d);}
    if(el('mo-connection'))el('mo-connection').textContent='';
  }catch(e){
    if(!moAlive(g)||seq!==MO.pollSeq||room!==MO.room||channel!==MO.channel||e.name==='AbortError')return;
    if(e.status===403&&MO.channel!=='table')return moChannel('table');
    if([401,403,404].includes(e.status)){el('mo-root').innerHTML=`<p id="mo-error" class="mo-error" role="alert">${moError(e)}</p><div id="mo-control-pending" class="mo-control-pending"></div><button class="v3-pill" onclick="moHub()">К столам</button>`;moStop();moPendingNotice();return;}
    MO.errors++;if(el('mo-connection'))el('mo-connection').textContent=MO.errors<3?'Связь прервалась · подключаемся…':'Нет связи · сообщения сохранены на устройстве';
    if(!MO.data&&el('mo-status'))el('mo-status').innerHTML=`<p class="mo-error" role="alert">${moError(e)}</p><button class="v3-link" onclick="moEnter(${room})">Повторить</button>`;
  }finally{if(moAlive(g)&&seq===MO.pollSeq)MO.timer=setTimeout(()=>moPoll(g),document.hidden?6000:Math.min(10000,2000*(MO.errors+1)));}
}
async function moRefresh(){clearTimeout(MO.timer);MO.abort?.abort();return moPoll(MO.gen);}
function moChannel(channel){
  if(!MO.data?.channels.includes(channel)||MO.channel===channel)return;
  moStore();moStop();MO.channel=channel;MO.messages.clear();MO.statusKey='';moRestore();
  el('mo-text').value=MO.draft;el('mo-messages').innerHTML='';if(el('mo-new'))el('mo-new').hidden=true;moReplyMarkup();moMessagePendingNotice();MO.clock=setInterval(moClock,1000);moPoll(MO.gen);
}
function moToggleInfo(){
  const panel=el('mo-info'),button=el('mo-info-toggle');if(!panel||!button)return;
  const open=panel.hidden;panel.hidden=!open;panel.closest('.mo-room').classList.toggle('info-open',open);
  button.setAttribute('aria-expanded',String(open));button.textContent=open?'‹ Вернуться к разговору':'Участники и управление ›';
}
function moClock(){const d=MO.data,clock=el('mo-clock');if(clock&&d?.deadline){const s=Math.max(0,Math.ceil(d.deadline-(Date.now()/1000-(MO.offset||0))));clock.textContent=Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}}
function moInvite(){
  const d=MO.data;if(!d)return;
  const payload=`mfo_${d.id}_${d.invite}`;
  const launch=d.launch_url||MO.launchBase||'';
  if(!launch){const host=el('mo-error');if(host)host.textContent='Приглашение пока недоступно. Стол виден в хабе, если он открытый.';return;}
  const url=launch.replace('{start}',payload);
  const share='https://t.me/share/url?'+new URLSearchParams({url,text:'Мафия · Город #'+d.id});
  if(tg?.openTelegramLink)tg.openTelegramLink(share);else window.open(share,'_blank','noopener');
}
el('modal').addEventListener('close',()=>{if(el('modal').open)return;moStore();moStop();el('modal').classList.remove('mo-mode');});
new MutationObserver(()=>{if(el('modal').classList.contains('mo-mode')&&!el('mo-root')){moStop();el('modal').classList.remove('mo-mode');}}).observe(el('mb'),{childList:true});
window.addEventListener('online',()=>{if(MO.room&&el('mo-root')&&el('modal').open)moRefresh();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&MO.room&&el('mo-root')&&el('modal').open)moRefresh();});
window.visualViewport?.addEventListener('resize',moViewport);
window.visualViewport?.addEventListener('scroll',moViewport);
window.addEventListener('resize',moViewport);
