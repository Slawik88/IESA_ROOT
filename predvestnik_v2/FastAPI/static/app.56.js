// Межчатовая Мафия · компактные состояния, роли и действия. Локальная история не меняется.
function moHowto(){return `<details class="mo-howto"><summary>Как играть</summary><ol><li>Займите место. От четырёх игроков хозяин может начать.</li><li>Ночью действуйте своей ролью. Днём обсуждайте и голосуйте.</li><li>Мирные ищут мафию. Мафия остаётся в большинстве.</li></ol><p>Выбывшие читают стол и общаются отдельно. Внешние договорённости портят игру.</p></details>`;}
function moSettingsMarkup(d={}){
  return `<div class="mo-settings"><label>Мест<select name="seats">${[4,6,8,10,12,16,20].map(n=>`<option value="${n}" ${n===(d.seats||8)?'selected':''}>${n}</option>`).join('')}</select></label>
    <label>Темп<select name="tempo">${[['fast','Быстро'],['normal','Обычно'],['slow','Неспешно']].map(([k,v])=>`<option value="${k}" ${k===(d.tempo||'normal')?'selected':''}>${v}</option>`).join('')}</select></label>
    <label>Доступ<select name="visibility"><option value="public">Открытый стол</option><option value="invite" ${d.visibility==='invite'?'selected':''}>По приглашению</option></select></label>
    <label>Голоса<select name="vote_mode"><option value="secret">Скрытые</option><option value="open" ${d.vote_mode==='open'?'selected':''}>Открытые</option></select></label></div>
    <label class="mo-check"><input name="roles_auto" type="checkbox" ${d.roles_auto!==false?'checked':''}>Подбирать роли автоматически</label>
    <details><summary>Выбрать роли</summary><div class="mo-role-options">${[['doctor','Доктор'],['detective','Детектив'],['don','Дон · от 8 мест']].map(([k,v])=>`<label class="mo-check"><input name="roles" value="${k}" type="checkbox" ${(d.roles||[]).includes(k)?'checked':''}>${v}</label>`).join('')}</div></details>`;
}
function moSettingsRead(form){const d=new FormData(form);return{seats:Number(d.get('seats')),tempo:d.get('tempo'),visibility:d.get('visibility'),vote_mode:d.get('vote_mode'),roles_auto:d.has('roles_auto'),roles:d.getAll('roles')};}
function moLabel(p){return p.seat?`${p.name} · #${p.seat}`:p.name;}
function moRole(d){
  const p=d.me;if(!p.role)return '';
  const copy={citizen:'Слушайте город. Днём найдите мафию.',mafia:'Ночью выберите цель вместе с командой.',don:'При равных ночных голосах решает ваш выбор.',doctor:'Ночью защитите одного игрока. Можно себя.',detective:'Ночью проверьте одного игрока.'};
  return `<details class="mo-role"><summary><img src="${BASE}/static/mafia-art/${p.role}.webp" alt="" width="44" height="44"><span><small>${p.alive?'Ваша роль':'Вы выбыли'}</small><b>${MO_ROLE[p.role]}</b></span><span aria-hidden="true">⌄</span></summary>
    <p>${copy[p.role]}</p>${p.team.length?`<p>Команда: ${p.team.map(x=>esc(moLabel(x))+(x.alive?'':' · выбыл')).join(', ')}.</p>`:''}
    ${p.checks.map(x=>`<p>Ночь ${x.round} · ${esc(moLabel(x))} — <b>${x.mafia?'мафия':'мирный'}</b></p>`).join('')}</details>`;
}
function moTargets(d){
  const mine=d.me,kind=d.phase==='voting'?'vote':{mafia:'mafia_target',don:'mafia_target',doctor:'doctor_save',detective:'detective_check'}[mine.role];
  if(!mine.alive||mine.left||!['night','voting'].includes(d.phase)||!kind)return '';
  const team=new Set(mine.team.map(p=>p.id));
  const choices=d.players.filter(p=>p.alive && !(kind==='mafia_target'&&team.has(p.id)) && !(kind!=='doctor_save'&&p.id===mine.id));
  const one=(id,name)=>`<button type="button" class="mo-target ${mine.action&&mine.action.target===id?'selected':''}" data-mo-target="${id===null?'none':id}" onclick="moAction('${kind}',${id===null?'null':id},${d.phase_number})">${mine.action&&mine.action.target===id?'✓ ':''}${esc(name)}</button>`;
  return `<div class="mo-actions"><span class="v3-eyebrow">${{vote:'Ваш голос',mafia_target:'Ночная цель',doctor_save:'Кого защитить',detective_check:'Кого проверить'}[kind]}</span><div class="mo-targets">${choices.map(p=>one(p.id,moLabel(p))).join('')}${kind==='vote'?one(null,'Никого'):''}</div><small>${mine.action?'Выбор принят · можно изменить до конца этапа':mine.choice_reset?'Цель вышла · выберите заново':'Нажмите на имя'}</small></div>`;
}
function moOpenVotes(d){
  if(d.phase!=='voting'||d.vote_mode!=='open')return '';
  const names=new Map(d.players.map(p=>[String(p.id),moLabel(p)]));
  return `<details class="mo-open-votes"><summary>Открытые голоса · ${Object.keys(d.votes).length}</summary>${Object.entries(d.votes).map(([uid,target])=>`<p>${esc(names.get(uid)||'Игрок')} → ${target===null?'Никого':esc(names.get(String(target))||'Выбыл')}</p>`).join('')||'<p class="mo-caption">Пока никто не выбрал.</p>'}</details>`;
}
function moPeople(d){return `<details class="mo-people"><summary>За столом · ${d.players.filter(p=>p.alive).length}/${d.players.length}</summary><div>${d.players.map(p=>`<div class="mo-person ${p.alive?'':'out'}"><span>${esc(moLabel(p))}${p.host?' · хозяин':''}${p.id===d.me.id?' · вы':''}<small>${p.left?'Покинул стол':p.role?MO_ROLE[p.role]:p.alive?'В игре':'Выбыл'}${p.muted?' · без сообщений':''}</small></span>${d.host_id===d.me.id&&p.id!==d.me.id&&!p.staff_muted?`<button class="v3-link" onclick="moModerate('${p.muted?'unmute':'mute'}',${p.id})">${p.muted?'Снять мут':'Мут'}</button>`:''}</div>`).join('')}</div></details>`;}
function moTeamChoices(d){
  if(!d.me.team_choices)return '';
  const names=new Map(d.players.map(p=>[p.id,moLabel(p)]));
  return `<details class="mo-team-choices"><summary>Выбор команды · ${d.me.team_choices.filter(p=>p.target).length}/${d.me.team_choices.length}</summary>${d.me.team_choices.map(p=>`<p>${esc(names.get(p.id)||p.name)} → ${p.target?esc(names.get(p.target)||'Игрок'):'ещё выбирает'}</p>`).join('')}</details>`;
}
function moRenderRoom(d){
  const ended=['finished','cancelled'].includes(d.phase);
  MO.self=d.me.id;
  moPendingNotice();
  if(MO.redactions!==d.redactions){MO.messages.clear();MO.redactions=d.redactions;}
  MO.offset=Date.now()/1000-d.server_time;MO.launchBase=d.launch_url||MO.launchBase;
  const phaseKey=JSON.stringify([d.version,d.me.can_write,d.channels,d.can_claim]);
  const editing=d.phase==='lobby'&&d.host_id===d.me.id&&el('mo-settings-form')?.contains(document.activeElement);
  if(MO.statusKey!==phaseKey){
    const wasRole=el('mo-status')?.querySelector('.mo-role')?.open, wasPeople=el('mo-status')?.querySelector('.mo-people')?.open;
    const wasControls=el('mo-status')?.querySelector('.mo-controls')?.open;
    const wasVotes=el('mo-status')?.querySelector('.mo-open-votes')?.open,wasTeam=el('mo-status')?.querySelector('.mo-team-choices')?.open;
    const host=d.host_id===d.me.id;
    const lobby=d.phase==='lobby';
    const markup=`<div class="mo-phase"><span><small>${lobby?'Город собирается':ended?'Город #'+d.id:'Круг '+d.round}</small><b>${MO_PHASE[d.phase]}</b></span><time id="mo-clock" aria-label="Осталось времени"></time></div>
      ${lobby?`<div class="mo-lobby"><span class="mo-seats">${d.players.length}<small> / ${d.seats}</small></span><p>${d.players.length<4?'Ещё '+(4-d.players.length)+' до начала':host?'Город готов. Можно начинать.':'Ждём старта от хозяина.'}</p>${host?`<button class="v3-pill" onclick="moControl('start')" ${d.players.length<4?'disabled':''}>Начать партию</button>`:''}</div>`:moRole(d)}
      ${ended?`<p class="mo-result">${d.winner==='town'?'Мирные победили':d.winner==='mafia'?'Мафия победила':d.winner==='draw'?'Ничья':'Стол закрыт'}</p><button class="v3-pill" onclick="moAgain()">Ещё партию</button>`:moTargets(d)}
      ${d.me.role==='citizen'&&d.phase==='night'&&d.me.alive?'<p class="mo-caption">Город спит. Утром начнётся обсуждение.</p>':''}
      ${!d.me.alive&&!ended?'<p class="mo-caption">Вы выбыли. Для общения есть «Выбывшие».</p>':''}
      ${d.phase==='night'&&d.channels.includes('mafia')?`<p class="mo-caption">Команда: ${d.me.team.map(p=>esc(moLabel(p))).join(', ')} · разговор во вкладке «Мафия».</p>`:''}
      ${moTeamChoices(d)}${moOpenVotes(d)}${moPeople(d)}
      ${!ended?`<details class="mo-controls"><summary>Управление столом</summary><div class="mo-control-row">${host?`${d.phase==='paused'?'<button class="v3-link" onclick="moControl(\'resume\')">Продолжить</button>':['night','discussion','voting'].includes(d.phase)?'<button class="v3-link" onclick="moControl(\'pause\')">Пауза</button>':''}${d.phase==='discussion'?`<button class="v3-link" onclick="moControl('skip',${d.phase_number})">К голосованию</button>`:''}<button class="v3-link" onclick="moConfirmControl('cancel')">Закрыть партию</button>`:''}${d.can_claim?'<button class="v3-link" onclick="moControl(\'claim\')">Взять стол</button>':''}<button class="v3-link" onclick="moConfirmControl('leave')">Выйти из партии</button></div>
      ${host&&lobby?`<form id="mo-settings-form">${moSettingsMarkup(MO.settingsDraft||d)}<button class="v3-pill v3-pill--ghost">Сохранить</button></form>`:''}</details>`:''}`;
    const status=el('mo-status'),preserved=editing?status.querySelector('.mo-controls'):null;
    if(preserved){
      const template=document.createElement('template');template.innerHTML=markup;
      for(const child of [...status.children])if(child!==preserved)child.remove();
      for(const child of [...template.content.children])if(!child.classList.contains('mo-controls'))status.insertBefore(child,preserved);
    }else status.innerHTML=markup;
    if(wasRole&&el('mo-status').querySelector('.mo-role'))el('mo-status').querySelector('.mo-role').open=true;
    if(wasPeople&&el('mo-status').querySelector('.mo-people'))el('mo-status').querySelector('.mo-people').open=true;
    if(wasControls&&el('mo-status').querySelector('.mo-controls'))el('mo-status').querySelector('.mo-controls').open=true;
    if(wasVotes&&el('mo-status').querySelector('.mo-open-votes'))el('mo-status').querySelector('.mo-open-votes').open=true;
    if(wasTeam&&el('mo-status').querySelector('.mo-team-choices'))el('mo-status').querySelector('.mo-team-choices').open=true;
    const form=el('mo-settings-form');if(form){
      if(!preserved)form.dataset.version=MO.settingsDraft?(MO.settingsVersion??d.version):d.version;
      form.onchange=()=>{if(!MO.settingsDraft)MO.settingsVersion=Number(form.dataset.version);MO.settingsDraft=moSettingsRead(form);};
      form.onfocusout=()=>setTimeout(()=>{if(MO.data&&el('mo-settings-form')&&!el('mo-settings-form').contains(document.activeElement)){MO.statusKey='';moRenderRoom(MO.data);}},0);
      form.onsubmit=e=>{e.preventDefault();moControl('settings',null,moSettingsRead(form),MO.settingsVersion??Number(form.dataset.version));};
    }
    MO.statusKey=phaseKey;
  }
  const names={table:'Стол',mafia:'Мафия',afterlife:'Выбывшие'};
  const tabHtml=d.channels.map(k=>`<button class="${k===MO.channel?'on':''}" type="button" aria-pressed="${k===MO.channel}" onclick="moChannel('${k}')">${names[k]}</button>`).join('');
  if(el('mo-channels').innerHTML!==tabHtml)el('mo-channels').innerHTML=tabHtml;
  if(!d.channels.includes(MO.channel)){moChannel('table');return;}
  moMessages(d.messages);moClock();
  el('mo-text').disabled=!d.me.can_write;el('mo-send').disabled=!d.me.can_write;
  el('mo-write-hint').textContent=d.me.can_write?'До 600 знаков · Enter — отправить':d.me.muted?'Сообщения ограничены модератором':d.phase==='night'?'Город спит':d.phase==='paused'?'Игра на паузе':ended?'Партия окончена':'Читайте стол или откройте «Выбывшие»';
}
function moMessageMarkup(m){
  const mine=m.user_id===MO.data?.me.id,system=m.user_id===null;
  return `<article class="mo-msg ${mine?'mine':''} ${system?'system':''}" data-msg="${m.id}">${!system?`<header><b>${esc(moLabel(m))}</b><time>${new Date(m.time*1000).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}</time><button class="v3-link" aria-label="Действия с сообщением" onclick="moMessageMenu(${m.id})">⋯</button></header>`:''}${m.reply_to?`<blockquote><b>${esc(moLabel({name:m.reply_name||'Сообщение',seat:m.reply_seat}))}</b><span>${esc(m.reply_body||'')}</span></blockquote>`:''}<p>${esc(m.body)}</p></article>`;
}
function moMessages(rows,older=false){
  const chat=el('mo-chat'),box=el('mo-messages');if(!chat||!box)return;
  const atBottom=chat.scrollHeight-chat.scrollTop-chat.clientHeight<80,oldHeight=chat.scrollHeight;
  const empty=MO.messages.size===0;
  if(empty){box.replaceChildren();MO.hasOlder=rows.length===80;}
  else if(older)MO.hasOlder=rows.length===80;
  let additions=false;
  const nodes=new Map([...box.children].map(n=>[Number(n.dataset.msg),n]));
  rows.forEach(m=>MO.messages.set(m.id,m));
  const sorted=[...MO.messages.values()].sort((a,b)=>a.id-b.id);
  for(const m of sorted){
    const html=moMessageMarkup(m),node=nodes.get(m.id);
    if(node?.outerHTML===html)continue;
    const template=document.createElement('template');template.innerHTML=html;const next=template.content.firstElementChild;
    if(node)node.replaceWith(next);
    else{const following=[...box.children].find(n=>Number(n.dataset.msg)>m.id);box.insertBefore(next,following||null);additions=true;}
  }
  if(atBottom&&!older&&sorted.length>240){for(const m of sorted.slice(0,-240)){MO.messages.delete(m.id);box.querySelector(`[data-msg="${m.id}"]`)?.remove();}MO.hasOlder=true;}
  if(older)chat.scrollTop+=chat.scrollHeight-oldHeight;
  else if(atBottom||empty)chat.scrollTop=chat.scrollHeight;
  else if(additions)el('mo-new').hidden=false;
  el('mo-older').hidden=!MO.hasOlder;
}
function moLatest(){const chat=el('mo-chat');if(chat)chat.scrollTop=chat.scrollHeight;if(el('mo-new'))el('mo-new').hidden=true;}
async function moOlder(){
  const ids=[...MO.messages.keys()];if(!ids.length)return;const g=MO.gen,room=MO.room,channel=MO.channel;
  return moBusy(async()=>{
    const d=await moRequest(`/rooms/${room}?channel=${channel}&before=${Math.min(...ids)}`);
    if(!moAlive(g)||room!==MO.room||channel!==MO.channel)return;
    if(d.version<MO.data.version||d.redactions!==MO.redactions)return moRefresh();
    moMessages(d.messages,true);
  });
}
async function moAction(kind,target,phase){const g=MO.gen,room=MO.room;return moBusy(async()=>{await moRequest(`/rooms/${room}/action`,{kind,target,phase_number:phase});if(moAlive(g))await moRefresh();});}
function moCommandKey(room=MO.room){return `pv_mo_command_${typeof _uid!=='undefined'&&_uid?_uid:MO.self||0}_${room}`;}
function moPendingCommand(){try{return JSON.parse(sessionStorage.getItem(moCommandKey())||'null');}catch(_){return null;}}
function moPendingNotice(){
  const box=el('mo-control-pending');if(!box)return;
  box.innerHTML=moPendingCommand()?'<span>Ответ на действие не пришёл</span><button class="v3-link" onclick="moRetryControl()">Проверить</button>':'';
}
async function moRunControl(payload){
  const g=MO.gen,room=MO.room,key=moCommandKey(room);
  return moBusy(async()=>{
    try{
      await moRequest(`/rooms/${room}/control`,payload);
      if(JSON.parse(sessionStorage.getItem(key)||'null')?.nonce===payload.nonce)sessionStorage.removeItem(key);
      if(!moAlive(g))return;
      if(payload.command==='settings'){MO.settingsDraft=null;MO.settingsVersion=null;MO.statusKey='';}
      moPendingNotice();el('mo-error').textContent='';
      if(payload.command==='leave')return moHub();
      await moRefresh();
    }catch(e){
      if(e.status&&e.status<500){
        sessionStorage.removeItem(key);
        if(moAlive(g)){
          if(payload.command==='settings'&&e.status===409){MO.settingsDraft=null;MO.settingsVersion=null;MO.statusKey='';document.activeElement?.blur();}
          await moRefresh();
        }
      }
      if(moAlive(g))moPendingNotice();throw e;
    }
  });
}
function moRetryControl(){const payload=moPendingCommand();if(payload)return moRunControl(payload);}
async function moControl(command,phase=null,settings=null,expectedVersion=null){
  if(MO.busy)return;
  if(moPendingCommand()){moPendingNotice();el('mo-error').textContent='Сначала проверьте предыдущее действие.';return;}
  const payload={command,phase_number:phase??MO.data?.phase_number,settings,expected_version:expectedVersion??MO.data?.version,nonce:crypto.randomUUID()};
  try{sessionStorage.setItem(moCommandKey(),JSON.stringify(payload));}catch(_){el('mo-error').textContent='Не удалось сохранить действие на устройстве. Попробуйте снова.';return;}
  return moRunControl(payload);
}
function moConfirmControl(command){
  const root=el('mo-error');if(!root)return;
  root.innerHTML=`<span>${command==='leave'?'Покинуть партию? В активной игре вы выбываете.':'Закрыть партию для всех?'}</span><button class="v3-link" onclick="moControl('${command}',${MO.data.phase_number})">${command==='leave'?'Выйти':'Закрыть партию'}</button><button class="v3-link" onclick="el('mo-error').textContent=''">Отмена</button>`;
}
async function moAgain(){return moBusy(async()=>{const g=MO.gen,d=await moRequest('/quick',{});if(moAlive(g))moEnter(d.room_id);});}
async function moSend(){
  const input=el('mo-text');if(!input||!MO.data?.me.can_write||MO.busy)return;
  const text=input.value.trim();if(!text)return;
  if(!MO.nonce)MO.nonce=crypto.randomUUID();MO.draft=input.value;moStore();
  const nonce=MO.nonce,g=MO.gen,room=MO.room,channel=MO.channel,reply=MO.reply;
  return moBusy(async()=>{
    await moRequest(`/rooms/${room}/messages`,{channel,text,nonce,reply_to:reply?.id||null});
    if(!moAlive(g))return;
    if(MO.nonce===nonce){MO.draft='';MO.nonce='';MO.reply=null;input.value='';moStore();moReplyMarkup();}
    el('mo-error').textContent='';await moRefresh();
  });
}
function moReplyMarkup(){const box=el('mo-reply');if(box)box.innerHTML=MO.reply?`<span>Ответ ${esc(MO.reply.name)}: ${esc(MO.reply.body.slice(0,80))}</span><button type="button" class="v3-link" aria-label="Отменить ответ" onclick="MO.reply=null;MO.nonce='';moStore();moReplyMarkup()">×</button>`:'';}
function moMessageMenu(id){
  const m=MO.messages.get(id),root=el('mo-error');if(!m||!root)return;
  root.innerHTML=`<span>${esc(m.name)}</span>${MO.data?.me.can_write&&!m.hidden?`<button class="v3-link" onclick="moReply(${id})">Ответить</button>`:''}${m.user_id?`<button class="v3-link" onclick="moModerate('report',null,${id})">Пожаловаться</button>`:''}${m.user_id&&MO.data.host_id===MO.data.me.id?`<button class="v3-link" onclick="moModerate('hide',null,${id})">Скрыть</button>`:''}<button class="v3-link" onclick="el('mo-error').textContent=''">Закрыть</button>`;
}
function moReply(id){const m=MO.messages.get(id);if(m){MO.nonce='';MO.reply={id:m.id,name:moLabel(m),body:m.body};moStore();moReplyMarkup();el('mo-error').textContent='';el('mo-text').focus();}}
async function moModerate(kind,target=null,message_id=null){const g=MO.gen,room=MO.room;return moBusy(async()=>{await moRequest(`/rooms/${room}/moderation`,{kind,target,message_id});if(!moAlive(g))return;el('mo-error').textContent=kind==='report'?'Жалоба отправлена.':'Готово.';await moRefresh();});}
