// Online Mafia · one room controller, explicit panels and per-channel conversation state.
const MO={gen:0,room:0,channel:'table',data:null,timer:null,clock:null,abort:null,busy:false,messages:new Map(),draft:'',nonce:'',reply:null,errors:0,tab:'chat',read:{},scroll:{},newCount:0};
const MO_ROLE={citizen:'Мирный житель',mafia:'Мафия',don:'Дон',doctor:'Доктор',detective:'Детектив'};
const MO_PHASE={lobby:'Город собирается',night:'Ночь',discussion:'Город говорит',voting:'Вердикт города',paused:'Пауза',finished:'Развязка',cancelled:'Стол закрыт'};
const MO_CHANNEL={table:'Общий',mafia:'Мафия',afterlife:'Выбывшие'};
function moStop(){clearTimeout(MO.eventTimer);if(el('mo-event'))el('mo-event').hidden=true;++MO.gen;MO.pollSeq=(MO.pollSeq||0)+1;clearTimeout(MO.timer);clearInterval(MO.clock);MO.timer=MO.clock=null;MO.abort?.abort();MO.abort=null;MO.busy=false;el('mo-root')?.removeAttribute('aria-busy');}
function moAuth(){const h=new Headers(hdrs());return JSON.stringify(['x-init-data','x-session-token','x-preprod-browser-ticket'].map(k=>h.get(k)||''));}
function moAlive(g){ const owner=moOwner();return g===MO.gen && (MO.auth===undefined||MO.auth===moAuth()) && (!MO.owner||!owner||MO.owner===owner) && el('mo-root')?.isConnected && el('modal').open; }
function moReady(){
  if(moAlive(MO.gen))return true;
  if(el('mo-root')?.isConnected&&el('modal')?.open){moStop();el('mo-root').innerHTML='<p class="mo-error" role="alert">Аккаунт изменился. Открой Мафию заново.</p><button class="v3-pill" onclick="openMafiaOnline()">Открыть Мафию</button>';}
  return false;
}

async function moRequest(path, body, signal){
  const controller=new AbortController(),abort=()=>controller.abort();let timeout=false;
  if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(()=>{timeout=true;abort();},12000);
  try{
    const r=await fetch(BASE+'/mafia-online'+path,{method:body===undefined?'GET':'POST',headers:moJSONHeaders(),body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});
    const data=await r.json().catch(()=>({}));
    if(!r.ok){const error=new Error(typeof data.detail==='string'?data.detail:r.status===422?'Проверьте данные и повторите.':'Город не ответил. Попробуйте снова.');error.status=r.status;throw error;}
    return data;
  }catch(e){if(timeout)throw new Error(body?.command?'Ответ на действие не пришёл. Нажмите «Проверить».':path.endsWith('/messages')?'Ответ не пришёл. Повторите отправку без дубля.':'Ответ не пришёл. Обновите состояние города.');if(e.name==='TypeError')throw new Error(body?.command?'Нет связи. Проверьте действие после подключения.':path.endsWith('/messages')?'Нет связи. Черновик сохранён.':'Нет связи. Попробуйте снова после подключения.');throw e;}
  finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}

function moJSONHeaders(){const headers=new Headers(hdrs());headers.set('Content-Type','application/json');return headers;}
function moError(e){return esc(String(e?.message||e||'Связь прервалась.'));}
function moShell(){MO.self=0;MO.owner=moOwner();MO.auth=moAuth();OM('Мафия','<div id="mo-root" class="mo-root"><p class="v3-empty" role="status">Зажигаем фонари…</p></div>');el('modal').classList.add('mo-mode');moViewport();}
async function openMafiaOnline(roomId=0,invite=''){moStore();moStop();MO.room=0;MO.data=null;moShell();return roomId?moJoin(Number(roomId),invite):moHub(true);}
async function moHub(followActive=false){
  if(MO.auth!==undefined&&MO.auth!==moAuth())return openMafiaOnline();
  moStore();moSheetClose();moStop();MO.room=0;MO.data=null;MO.pendingEvent=null;MO.channel='table';MO.hubQuery='';
  if(!el('mo-root'))moShell();const g=MO.gen;
  el('mo-root').innerHTML=`<div class="mo-hub">${v3Head('Мафия',{sub:'Игроки из разных чатов. Один город.',back:'CM()',end:''})}
    <section class="mo-city"><img src="${BASE}/static/mafia-art/city.webp" alt="" width="800" height="400"><div><span class="v3-eyebrow">Межчатовая</span><h2>Ночь зовёт</h2><p>Собери город. Найди свою сторону.</p></div></section>
    <button class="v3-pill v3-pill--full" id="mo-quick" disabled>Ищем город…</button><p id="mo-hub-state" class="mo-caption" role="status">Общий разговор · тайные роли · от 4 игроков</p>
    <div class="mo-hub-tools"><button class="v3-link" onclick="moCreate()">Создать стол</button><button class="v3-link" onclick="moHelp()">Правила</button></div>
    <p id="mo-error" class="mo-error" role="alert"></p><div class="v3-sec"><span class="v3-eyebrow">Открытые города</span><button class="v3-link" aria-label="Обновить список городов" onclick="moHubRefresh(MO.gen)">Обновить</button></div>
    <label class="mo-search-label" for="mo-hub-search">Найти стол</label><input class="mo-search" id="mo-hub-search" type="search" placeholder="Номер города или хозяин" autocomplete="off"><div class="mo-tables" id="mo-tables"></div>
    <div id="mo-history"></div><button class="v3-link mo-local" onclick="openMafiaStats()">Локальная мафия · моя история</button></div>`;
  el('mo-hub-search').oninput=e=>{MO.hubQuery=e.target.value;moHubRows();};
  el('mo-quick').onclick=()=>moBusy(async()=>{el('mo-quick').textContent='Занимаем место…';const d=MO.hub?.active?{room_id:MO.hub.active}:await moRequest('/quick',{});if(moAlive(g))return moEnter(d.room_id);});
  await moHubRefresh(g,followActive);
}
async function moHubRefresh(g,followActive=false){
  clearTimeout(MO.timer);if(!moAlive(g)||MO.room)return;
  try{const d=await moRequest('');if(!moAlive(g)||MO.room)return;MO.hub=d;el('mo-error').textContent='';MO.self=d.user_id;MO.owner=d.user_id;MO.launchBase=d.launch_url||'';
    if(followActive&&d.active)return moEnter(d.active);
    el('mo-quick').disabled=false;el('mo-quick').textContent=d.active?'Вернуться в партию':'Играть';
    el('mo-hub-state').textContent=d.active?'Твоё место за столом сохранено':'Общий разговор · тайные роли · от 4 игроков';moHubRows();
    const historyOpen=el('mo-history').querySelector('details')?.open;el('mo-history').innerHTML=d.history.length?`<details class="mo-history"><summary>Мои последние партии · ${d.history.length}</summary>${d.history.map(r=>`<button class="v3-row" onclick="moEnter(${r.id})"><span>Город №${r.id}<small>${moResultTitle(r)} · ${r.count} игроков</small></span><span class="v3-end">Итоги</span></button>`).join('')}</details>`:'';if(historyOpen&&el('mo-history').querySelector('details'))el('mo-history').querySelector('details').open=true;
  }catch(e){if(moAlive(g))el('mo-error').textContent=e.message;}
  finally{if(moAlive(g)&&!MO.room)MO.timer=setTimeout(()=>moHubRefresh(g),15000);}
}
function moHubRows(){const d=MO.hub;if(!d||!el('mo-tables'))return;const q=MO.hubQuery.trim().toLocaleLowerCase(),rows=d.rooms.filter(r=>r.id!==d.active).filter(r=>`${r.id} ${r.host}`.toLocaleLowerCase().includes(q));
  el('mo-tables').innerHTML=rows.map(r=>`<button class="v3-row" onclick="moJoin(${r.id})"><span><b>Город №${r.id}</b><small>${esc(r.host)} · ${{fast:'Быстрый',normal:'Обычный',slow:'Неспешный'}[r.tempo]} · ${r.vote_mode==='open'?'голоса открыты':'голоса скрыты'}</small></span><span class="v3-end">${r.count}/${r.seats}<small>Войти</small></span></button>`).join('')||`<p class="v3-empty">${q?'Такой город не найден. Измените поиск.':'Города пока пустуют. Нажми «Играть» — соберём первый.'}</p>`;
}
async function moBusy(fn){if(!moReady())return;if(MO.busy){moToast('Дожидаемся ответа города…');return;}MO.busy=true;const g=MO.gen;el('mo-root')?.setAttribute('aria-busy','true');moComposeState();
  try{await fn();}catch(e){if(moAlive(g))moShowError(e);}finally{if(g===MO.gen){MO.busy=false;el('mo-root')?.removeAttribute('aria-busy');moComposeState();if(!MO.room&&el('mo-quick'))el('mo-quick').textContent=MO.hub?.active?'Вернуться в партию':'Играть';}}
}
function moShowError(e){const box=el('mo-sheet')?.open?el('mo-sheet-error'):el('mo-error');if(box)box.textContent=String(e?.message||e);else if(el('mo-root'))el('mo-root').innerHTML=`<p id="mo-error" class="mo-error" role="alert">${moError(e)}</p><button class="v3-pill" onclick="moHub()">В хаб</button>`;}
async function moJoin(id,invite=''){if(!el('mo-root'))moShell();const g=MO.gen;return moBusy(async()=>{const d=await moRequest(`/rooms/${id}/join`,{invite});if(moAlive(g))return moEnter(d.room_id);});}
function moOwner(){return typeof _uid!=='undefined'&&_uid?_uid:typeof tg!=='undefined'&&tg?.initDataUnsafe?.user?.id?tg.initDataUnsafe.user.id:MO.self||0;}

function moDraftKey(){return `pv_mo_${moOwner()}_${MO.room}_${MO.channel}`;}
function moStore(){if(!MO.room||MO.draftOwner!==moOwner())return;try{sessionStorage.setItem(moDraftKey(),JSON.stringify({text:MO.draft,nonce:MO.nonce,reply:MO.reply}));}catch(_){}}
function moRestore(){MO.draftOwner=moOwner();try{const d=JSON.parse(sessionStorage.getItem(moDraftKey())||'{}');MO.draft=typeof d.text==='string'?d.text:'';MO.nonce=typeof d.nonce==='string'?d.nonce:'';MO.reply=d.reply&&typeof d.reply.body==='string'?d.reply:null;}catch(_){MO.draft='';MO.nonce='';MO.reply=null;}}
async function moEnter(id){
  moStore();moSheetClose();moStop();Object.assign(MO,{room:id,channel:'table',data:null,tab:'chat',statusKey:'',redactions:0,errors:0,hasOlder:false,settingsDraft:null,settingsVersion:null,phaseMarker:'',phaseMoment:null,presented:null,pendingEvent:null,checkSeen:0,playerQuery:'',newCount:0,sendState:'',sendError:false,read:{},scroll:{}});MO.messages.clear();moRestore();try{const read=JSON.parse(sessionStorage.getItem(`pv_mo_read_${moOwner()}_${id}`)||'{}');MO.read=read&&typeof read==='object'&&!Array.isArray(read)?read:{};}catch(_){MO.read={};}
  if(!el('mo-root'))moShell();el('mo-root').innerHTML=moRoomShell(id);
  const input=el('mo-text');input.value=MO.draft;input.oninput=()=>{MO.draft=input.value;MO.nonce='';MO.sendError=false;MO.sendState='';moStore();moComposeState();};
  moChatGestures();
  input.onkeydown=e=>{if(e.key==='Escape'&&MO.reply){e.preventDefault();e.stopPropagation();moCancelReply();return;}if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&(e.ctrlKey||e.metaKey||!matchMedia('(pointer:coarse)').matches)){e.preventDefault();moSend();}};
  el('mo-compose').onsubmit=e=>{e.preventDefault();moPendingMessage()?moPendingMessageDialog():moSend();};
  el('mo-chat').onscroll=()=>{const c=el('mo-chat'),near=c.scrollHeight-c.scrollTop-c.clientHeight<60;if(near){MO.newCount=0;moMarkRead();}moReading(!near);moNewBadge();};
  input.onfocus=()=>moReading(false);
  el('mo-tabs').onkeydown=e=>{const keys=['chat','players','table'],i=keys.indexOf(MO.tab);let next;if(e.key==='ArrowRight')next=(i+1)%3;else if(e.key==='ArrowLeft')next=(i+2)%3;else if(e.key==='Home')next=0;else if(e.key==='End')next=2;else return;e.preventDefault();moTab(keys[next],true);};
  moReplyMarkup();moPendingNotice();moComposeState();MO.clock=setInterval(moClock,1000);await moPoll(MO.gen);
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
    if(!MO.owner){MO.owner=d.me.id;MO.self=d.me.id;moRestore();if(el('mo-text'))el('mo-text').value=MO.draft;moReplyMarkup();}
    if(!MO.data||d.version>=MO.data.version){MO.data=d;MO.errors=0;moRenderRoom(d);}
    if(el('mo-connection'))el('mo-connection').textContent='';
  }catch(e){
    if(!moAlive(g)||seq!==MO.pollSeq||room!==MO.room||channel!==MO.channel||e.name==='AbortError')return;
    if(e.status===403&&MO.channel!=='table')return moChannel('table');
    if([401,403,404].includes(e.status)){el('mo-root').innerHTML=`<p id="mo-error" class="mo-error" role="alert">${moError(e)}</p><button class="v3-pill" onclick="moHub()">К столам</button>`;moStop();MO.room=0;MO.data=null;return;}
    MO.errors++;if(el('mo-connection'))el('mo-connection').textContent=MO.errors<3?'Связь прервалась · подключаемся…':'Нет связи · сообщения сохранены на устройстве';
    if(!MO.data&&el('mo-status'))el('mo-status').innerHTML=`<p class="mo-error" role="alert">${moError(e)}</p><button class="v3-link" onclick="moEnter(${room})">Повторить</button>`;
  }finally{if(moAlive(g)&&seq===MO.pollSeq)MO.timer=setTimeout(()=>moPoll(g),document.hidden?6000:Math.min(10000,2000*(MO.errors+1)));}
}
async function moRefresh(){clearTimeout(MO.timer);MO.abort?.abort();return moPoll(MO.gen);}

function moChannel(channel){if(!moReady())return;if(!MO.data?.channels.includes(channel)||MO.channel===channel)return;if(MO.messages.size){const chat=el('mo-chat');MO.scroll[MO.channel]=chat&&chat.scrollHeight-chat.scrollTop-chat.clientHeight<80?'bottom':chat?.scrollTop||0;}moStore();moStop();MO.channel=channel;MO.messages.clear();MO.newCount=0;MO.hasOlder=false;MO.statusKey='';moRestore();el('mo-text').value=MO.draft;el('mo-messages').replaceChildren();moReplyMarkup();moComposeState();moChannelMarkup();MO.clock=setInterval(moClock,1000);moPoll(MO.gen);}
function moClock(){if(!moAlive(MO.gen)){moReady();return;}const d=MO.data,c=el('mo-clock');if(!d||!c)return;const paused=d.phase==='paused',until=d.deadline||(d.phase==='finished'?d.chat_until:null),now=Date.now()/1000-(MO.offset||0),s=paused?Math.ceil(d.phase_remaining||0):until?Math.max(0,Math.ceil(until-now)):0;c.textContent=paused?`Ⅱ ${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`:until?(s?`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`:d.phase==='finished'?'Завершён':'Смена…'):'';c.classList.toggle('urgent',!paused&&!!s&&s<=15);el('mo-root')?.classList.toggle('mo-phase-urgent',!paused&&!!s&&s<=15&&!['finished','cancelled'].includes(d.phase));const progress=el('mo-phase-progress');if(progress){progress.style.transform=`scaleX(${d.phase_duration?Math.max(0,Math.min(1,s/d.phase_duration)):0})`;progress.parentElement.hidden=!d.phase_duration||['finished','cancelled'].includes(d.phase);}c.setAttribute('aria-label',paused?`Пауза. Осталось ${s} секунд`:d.phase==='finished'?`Общий разговор закроется через ${s} секунд`:`До смены этапа ${s} секунд`);const mini=el('mo-mini-clock');if(mini){mini.textContent=c.textContent;mini.setAttribute('aria-label',c.getAttribute('aria-label')||'Время этапа');}if(el('mo-postgame-time'))el('mo-postgame-time').textContent=s?`Разговор открыт ещё ${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`:'Общий разговор завершён';}
function moInvite(){const d=MO.data;if(!d||d.phase!=='lobby'||d.me.left)return;const url=(MO.launchBase||'').replace('{start}',`mfo_${d.id}_${d.invite}`);if(!url)return moToast('Приглашение временно недоступно. Открытый стол виден в хабе.');MO.inviteUrl=url;
  moSheet('Позвать в город',`<p>Друзья из любого чата попадут за этот стол.</p><label class="mo-search-label" for="mo-invite-link">Приглашение</label><input id="mo-invite-link" class="mo-search" value="${esc(url)}" readonly><div class="mo-sheet-actions"><button class="v3-pill" onclick="moShareInvite()">Отправить в Telegram</button><button class="v3-pill v3-pill--ghost" onclick="moCopyInvite()">Скопировать ссылку</button></div>`,'invite');}
function moShareInvite(){const url='https://t.me/share/url?'+new URLSearchParams({url:MO.inviteUrl,text:'Мафия · присоединяйся к нашему городу'});if(tg?.openTelegramLink)tg.openTelegramLink(url);else window.open(url,'_blank','noopener');}
async function moCopyInvite(){try{await navigator.clipboard.writeText(MO.inviteUrl);moToast('Приглашение скопировано');}catch(_){el('mo-invite-link')?.select();moShowError(new Error('Скопируйте выделенную ссылку.'));}}
function moViewport(){const v=window.visualViewport,m=el('modal');if(!m?.classList.contains('mo-mode'))return;m.style.setProperty('--mo-height',`${v?.height||innerHeight}px`);m.style.setProperty('--mo-top',`${v?.offsetTop||0}px`);const height=v?.height||innerHeight;m.classList.toggle('mo-short',height<=440);m.classList.toggle('mo-small',height<=420);m.classList.toggle('mo-tiny',height<=380);m.classList.toggle('mo-keyboard',(v?.height||innerHeight)<520&&document.activeElement===el('mo-text'));}
el('modal').addEventListener('keydown',e=>{if(e.key==='Escape'&&el('mo-sheet')?.open){e.preventDefault();e.stopPropagation();moSheetClose();}});
el('modal').addEventListener('cancel',e=>{if(el('mo-sheet')?.open){e.preventDefault();moSheetClose();}});
el('modal').addEventListener('close',()=>{if(el('modal').open)return;moStore();moStop();el('modal').classList.remove('mo-mode','mo-keyboard','mo-short','mo-small','mo-tiny');el('modal').style.removeProperty('--mo-height');el('modal').style.removeProperty('--mo-top');});
new MutationObserver(()=>{if(el('modal').classList.contains('mo-mode')&&!el('mo-root')){moStop();el('modal').classList.remove('mo-mode');}}).observe(el('mb'),{childList:true});
window.addEventListener('online',()=>{if(MO.room&&el('mo-root')&&el('modal').open)moRefresh();else if(el('mo-hub-search'))moHubRefresh(MO.gen);});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&MO.room&&el('mo-root')&&el('modal').open)moRefresh();});
window.visualViewport?.addEventListener('resize',moViewport);window.visualViewport?.addEventListener('scroll',moViewport);window.addEventListener('resize',moViewport);document.addEventListener('focusin',moViewport);document.addEventListener('focusout',moViewport);
