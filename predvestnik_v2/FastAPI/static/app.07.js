// ── Admin Panel ───────────────────────────────────────────────────────────────
let _adminChats=null, _adminChatId=0, _adminTab='dash';
let _adminPage=1, _adminSearch='', _adminSort='messages', _adminSearchTimer=null;
const _RANK_NAMES={0:'👤',1:'👁 Мод.',2:'👮 Мл.Адм',3:'👮 Адм',4:'🕵️ Ст.Адм',5:'👑 Совл.',6:'👑 Влад.'};

function loadAdmin() {
  if(_adminChats) { renderAdminChatSel(); return; }
  el('adm-dash').innerHTML='<div class="loader">Загрузка...</div>';
  api('/admin/my-chats').then(d=>{
    _adminChats=d.chats||[];
    if(!_adminChats.length){
      el('adm-dash').innerHTML='<div class="card" style="text-align:center;padding:24px;color:var(--muted)">У вас нет прав модератора ни в одном чате.<br>Обратитесь к администратору чата.</div>';
      return;
    }
    _updateMoreCard();
    _adminChatId=_adminChats[0].chat_tg_id;
    renderAdminChatSel();
    loadAdminDash();
  }).catch(e=>{el('adm-dash').innerHTML=`<div class="err">${e}</div>`;});
}
function renderAdminChatSel() {
  if(!_adminChats?.length) return;
  const roleIcon = c => c.role==='admin' ? '🛡' : c.role==='main' ? '🏠' : '💬';
  const cur = _adminChats.find(c=>c.chat_tg_id==_adminChatId) || _adminChats[0];
  el('adm-chat-sel').innerHTML=`
    <select id="adm-sel" class="num-input" style="width:100%;margin:0 0 6px" onchange="onAdminChatChange(this.value)">
      ${_adminChats.map(c=>`<option value="${c.chat_tg_id}" ${c.chat_tg_id==_adminChatId?'selected':''}>${roleIcon(c)} ${esc(c.chat_title)} · ${_RANK_NAMES[c.local_rank]||c.local_rank}</option>`).join('')}
    </select>
    ${cur && cur.linked_title ? `<div style="font-size:10.5px;color:var(--muted);padding:0 2px 4px">${cur.role==='admin'?`🛡 Это админ-чат группы «${cur.linked_title}»`:`🏠 Основная группа · 🛡 админ-чат: «${cur.linked_title}»`}</div>` : ''}`;
}
function onAdminChatChange(cid) {
  _adminChatId=parseInt(cid);
  _loaded.delete('admin');
  swAdmin(_adminTab, document.querySelector('#pg-admin .tb.active'));
}
function swAdmin(tab, btn) {
  _adminTab=tab;
  document.querySelectorAll('#pg-admin .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  ['dash','users','bl','mod','settings','logs'].forEach(t=>el('adm-'+t).style.display=t===tab?'':'none');
  if(!_adminChatId) return;
  if(tab==='dash') loadAdminDash();
  else if(tab==='users') { _adminPage=1; loadAdminUsers(); }
  else if(tab==='bl') loadAdminBlacklist();
  else if(tab==='mod') loadAdminMod();
  else if(tab==='settings') loadAdminSettings();
  else if(tab==='logs') { _adminPage=1; _admLogFilter=''; loadAdminLogs(); }
}
function swAdminByName(tab) {
  swAdmin(tab, document.querySelector(`#pg-admin .tb[onclick*="'${tab}'"]`));
}
function loadAdminDash() {
  if(!_adminChatId) return;
  el('adm-dash').innerHTML='<div class="loader">Загрузка...</div>';
  api(`/admin/${_adminChatId}/dashboard`).then(d=>{
    el('adm-dash').innerHTML=`
      <div class="card">
        <div class="card-title">📊 Сводка</div>
        <div class="irow"><span class="ik">Ваш ранг</span><span style="color:var(--gold)">${d.my_rank_name}</span></div>
        <div class="irow"><span class="ik">Участников</span><span>${d.member_count}</span></div>
        <div class="irow"><span class="ik">Активны сегодня</span><span>${d.active_today}</span></div>
        <div class="irow"><span class="ik">С предупреждениями</span><span style="color:${d.warned_count>0?'var(--gold)':'var(--muted)'}">${d.warned_count}</span></div>
        <div class="irow"><span class="ik">Заблокированных</span><span style="color:${d.ban_count>0?'var(--red)':'var(--muted)'}">${d.ban_count}</span></div>
      </div>
      <div class="card">
        <div class="card-title">⚙️ Ваши права</div>
        ${[['Варн',d.can_warn],['Мут',d.can_mute],['Кик',d.can_kick],['Бан',d.can_ban]].map(([n,v])=>
          `<span class="badge" style="background:${v?'var(--green)':'var(--dim)'};color:${v?'#fff':'var(--muted)'};padding:3px 8px;border-radius:4px;font-size:11px;margin:2px">${n}</span>`
        ).join('')}
      </div>
      <div class="card">
        <div class="card-title">🔒 Управление чатом</div>
        <div style="font-size:11px;color:var(--muted);margin-bottom:8px">Закрыть чат — писать смогут только админы. То же, что «бот -чат» / «бот +чат».</div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-red" style="flex:1" onclick="doChatLock(false)">🔒 Закрыть</button>
          <button class="btn btn-gold" style="flex:1" onclick="doChatLock(true)">🔓 Открыть</button>
        </div>
      </div>`;
  }).catch(e=>{el('adm-dash').innerHTML=`<div class="err">${e}</div>`;});
}
function doChatLock(open) {
  api(`/admin/${_adminChatId}/chat-lock`,{method:'POST',body:JSON.stringify({open})})
    .then(()=>toast(open?'🔓 Чат открыт':'🔒 Чат закрыт'))
    .catch(e=>toast(e,false));
}
function loadAdminUsers() {
  if(!_adminChatId) return;
  el('adm-users').innerHTML='<div class="loader">Загрузка...</div>';
  api(`/admin/${_adminChatId}/users?page=${_adminPage}&search=${encodeURIComponent(_adminSearch)}&sort=${_adminSort}`)
    .then(d=>renderAdminUserTable(d))
    .catch(e=>{el('adm-users').innerHTML=`<div class="err">${e}</div>`;});
}
function renderAdminUserTable(d) {
  const total=d.total||0, pages=Math.ceil(total/(d.page_size||20));
  _admMaxRank=d.max_assignable_rank??0;
  el('adm-users').innerHTML=`
    <div style="display:flex;gap:6px;margin-bottom:8px">
      <input id="adm-search" type="text" class="num-input" style="flex:1;margin:0" placeholder="Поиск по нику/ID" value="${_adminSearch}" oninput="onAdminSearch(this.value)"/>
      <select class="num-input" style="width:120px;margin:0" onchange="onAdminSort(this.value)">
        <option value="messages" ${_adminSort==='messages'?'selected':''}>По сообщ.</option>
        <option value="level" ${_adminSort==='level'?'selected':''}>По уровню</option>
        <option value="rank" ${_adminSort==='rank'?'selected':''}>По рангу</option>
        <option value="warns" ${_adminSort==='warns'?'selected':''}>По варнам</option>
      </select>
    </div>
    <div style="overflow-x:auto">
      <table class="adm-table">
        <thead><tr><th>Пользователь</th><th>Ур.</th><th>Ранг</th><th>Варны</th><th>Статус</th><th>Действия</th></tr></thead>
        <tbody>
          ${d.users.map(u=>`<tr>
            <td>
              <div style="font-weight:600;font-size:12px">@${vipName(u.user_tg_username||'ID'+u.user_tg_id, u.is_vip)}</div>
              <div style="font-size:10px;color:var(--muted)">ID: ${u.user_tg_id} · ${u.user_messages_count_all_time||0} сообщ.</div>
              <div style="font-size:9.5px;color:var(--dim)">📅 ${u.joined_at?fmtUTC(u.joined_at):'—'} · 🕓 ${u.last_message_at?fmtUTC(u.last_message_at):'—'}</div>
            </td>
            <td style="text-align:center">${u.user_level||1}</td>
            <td style="font-size:10px">${_RANK_NAMES[u.local_rank||0]||'?'}</td>
            <td style="text-align:center;color:${u.warnings>0?'var(--gold)':'var(--muted)'}">${u.warnings||0}</td>
            <td style="font-size:10px">
              ${u.muted_until?`<span style="color:var(--gold)">🔇 до ${u.muted_until.slice(0,16)}</span>`:
                u.is_immune?'🛡 Иммун':u.is_left?'👋 Ушёл':'✅'}
            </td>
            <td style="white-space:nowrap">
              ${u.can_act?`<button class="btn btn-sm btn-ghost" style="font-size:10px;padding:3px 6px" onclick='openAdminAction(${u.user_tg_id},${JSON.stringify(u.user_tg_username||'ID'+u.user_tg_id)},${JSON.stringify({w:u.can_warn,m:u.can_mute,k:u.can_kick,b:u.can_ban,s:u.can_shield,i:u.can_immune})})'>⚡</button>`:`<span style="font-size:10px;color:var(--dim)">—</span>`}
              ${u.can_set_rank?`<button class="btn btn-sm btn-ghost" style="font-size:10px;padding:3px 6px" title="Сменить ранг" onclick='openRankModal(${u.user_tg_id},${JSON.stringify(u.user_tg_username||'ID'+u.user_tg_id)},${u.local_rank||0})'>🎖</button>`:''}
            </td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;font-size:11px;color:var(--muted)">
      <span>Всего: ${total}</span>
      <div style="display:flex;gap:6px">
        <button class="btn btn-sm btn-ghost" ${_adminPage<=1?'disabled':''} onclick="admPage(${_adminPage-1})">◀</button>
        <span>${_adminPage}/${pages||1}</span>
        <button class="btn btn-sm btn-ghost" ${_adminPage>=pages?'disabled':''} onclick="admPage(${_adminPage+1})">▶</button>
      </div>
    </div>`;
}
function admPage(p) { _adminPage=p; loadAdminUsers(); }
function onAdminSearch(v) {
  clearTimeout(_adminSearchTimer);
  _adminSearchTimer=setTimeout(()=>{ _adminSearch=v; _adminPage=1; loadAdminUsers(); },400);
}
function onAdminSort(v) { _adminSort=v; _adminPage=1; loadAdminUsers(); }

function openAdminAction(userId, userName, perms) {
  // Map each action to its permission flag (unwarn shares warn perm, unmute shares mute perm,
  // shield/unshield share rank_shield, set_immune/unset_immune share rank_immune)
  const _perm = {warn:perms.w, unwarn:perms.w, mute:perms.m, unmute:perms.m, kick:perms.k, ban:perms.b,
                 shield:perms.s, unshield:perms.s, set_immune:perms.i, unset_immune:perms.i};
  const _btn=(action,label,cls)=>{
    const ok=_perm[action]===true;
    return `<button class="btn btn-sm ${cls}" style="flex:1;position:relative" onclick="${ok?`doAdminAction(${userId},'${action}')`:''}" ${ok?'':'disabled'} title="${ok?'':'Недостаточно прав'}">${label}${!ok?'<span class="perm-tip">Нет прав</span>':''}</button>`;
  };
  OM(`⚡ ${userName||'ID'+userId}`,`
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:8px 0">
      ${_btn('warn','⚠️ Варн','btn-ghost')}
      ${_btn('unwarn','✅ Снять варн','btn-ghost')}
      ${_btn('mute','🔇 Мут','btn-ghost')}
      ${_btn('unmute','🔊 Снять мут','btn-ghost')}
      ${_btn('kick','🥾 Кик','btn-ghost')}
      ${_btn('ban','🚫 Бан','btn-red')}
      ${_btn('shield','🛡 Щит (24ч)','btn-ghost')}
      ${_btn('unshield','🛡❌ Снять щит','btn-ghost')}
      ${_btn('set_immune','🔰 Иммунитет','btn-ghost')}
      ${_btn('unset_immune','🔰❌ Снять имм.','btn-ghost')}
    </div>
    <div style="margin-top:8px">
      <input id="adm-reason" type="text" class="num-input" style="margin:0" placeholder="Причина (необязательно)" maxlength="200"/>
    </div>
  `,[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
  el('modal')._adminTarget=userId;
}
let _admPendingAction=null, _admPendingUser=0, _admPendingReason='';
function doAdminAction(userId, action) {
  if(action==='mute') { openMuteDuration(userId); return; }
  const reason=el('adm-reason')?.value||'';
  // Опасные действия (Бан/Кик) — подтверждение через модалку (заповедь 3).
  if(action==='ban'||action==='kick'){
    _admPendingAction=action; _admPendingUser=userId; _admPendingReason=reason;
    const labels={ban:'🚫 Бан',kick:'🥾 Кик'};
    OM(`${labels[action]} — подтверждение`,
      `<div style="text-align:center;padding:12px 0;color:var(--muted)">Подтвердите <b style="color:var(--red)">${labels[action]}</b> для этого пользователя.${reason?`<div style="font-size:11px;margin-top:6px">Причина: ${reason.replace(/</g,'&lt;')}</div>`:''}</div>`,
      [{l:'Да, выполнить',c:'btn-red',f:'_execAdminConfirmed()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
    return;
  }
  _execAdminAction(userId, action, reason);
}
function _execAdminConfirmed(){ _execAdminAction(_admPendingUser,_admPendingAction,_admPendingReason); }
function _execAdminAction(userId, action, reason) {
  api(`/admin/${_adminChatId}/action`,{method:'POST',body:JSON.stringify({user_id:userId,action,reason:reason||null})})
    .then(r=>{toast(`✅ ${action} выполнено`+(r.new_warnings!=null?` (варнов: ${r.new_warnings})`:''));CM();loadAdminUsers();})
    .catch(e=>toast(e,false));
}
let _admMuteUserId=0, _admMuteReason='';
function openMuteDuration(userId) {
  _admMuteUserId=userId;
  _admMuteReason=el('adm-reason')?.value||'';
  const opts=[[5,'5 мин'],[30,'30 мин'],[60,'1 ч'],[360,'6 ч'],[1440,'1 д'],[10080,'7 д']];
  OM('🔇 Длительность мута',
    `<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;padding:8px 0">
      ${opts.map(([m,l])=>`<button class="btn btn-sm btn-ghost" onclick="doMute(${m})">${l}</button>`).join('')}
    </div>`,[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function doMute(minutes) {
  const userId=_admMuteUserId, reason=_admMuteReason;
  api(`/admin/${_adminChatId}/action`,{method:'POST',body:JSON.stringify({user_id:userId,action:'mute',duration_minutes:minutes,reason:reason||null})})
    .then(r=>{toast(`🔇 Мут ${minutes} мин.`+(r.telegram_ok?'':' (Telegram недоступен)'));CM();loadAdminUsers();})
    .catch(e=>toast(e,false));
}

function loadAdminSettings() {
  if(!_adminChatId) return;
  el('adm-settings').innerHTML='<div class="loader">Загрузка...</div>';
  api(`/admin/${_adminChatId}/settings`).then(s=>{
    const tog=(key,label,val)=>`<div class="irow" style="cursor:pointer" onclick="toggleAdmSetting('${key}')">
      <span class="ik">${label}</span>
      <span id="aset-${key}" style="color:${val?'var(--green)':'var(--red)'}">${val?'ВКЛ':'ВЫКЛ'}</span>
    </div>`;
    const rank=(key,label,val,fromZero)=>`<div class="irow">
      <span class="ik">${label}</span>
      <select id="aset-${key}" class="num-input" style="width:auto;margin:0;font-size:11px" onchange="queueAdmSave()">
        ${(fromZero?[0,1,2,3,4,5,6]:[1,2,3,4,5,6]).map(r=>`<option value="${r}" ${val===r?'selected':''}>${_RANK_NAMES[r]}</option>`).join('')}
      </select>
    </div>`;
    el('adm-settings').innerHTML=`
      <div class="card">
        <div class="card-title">🔧 Модули</div>
        ${tog('module_shop','🛒 Магазин',s.module_shop)}
        ${tog('module_gacha','🎲 Гача',s.module_gacha)}
        ${tog('module_zoo','🐾 Зоопарк',s.module_zoo)}
        ${tog('module_expeditions','🗺 Экспедиции',s.module_expeditions)}
        ${tog('module_auction','🏛 Аукцион',s.module_auction)}
        ${tog('module_games','🎮 Игры',s.module_games)}
        ${tog('module_exchange','💱 Обмен',s.module_exchange)}
        ${tog('module_quests','📋 Квесты',s.module_quests)}
        ${tog('module_daily_deal','🏷 Акция дня',s.module_daily_deal)}
        ${tog('events_enabled','🎪 Ивенты',s.events_enabled)}
        ${tog('nsfw_warps_allowed','🔞 NSFW варпы',s.nsfw_warps_allowed)}
      </div>
      <div class="card">
        <div class="card-title">⚖️ Минимальный ранг для действий</div>
        ${rank('rank_warn','⚠️ Выдавать варны',s.rank_warn)}
        ${rank('rank_mute','🔇 Ставить мут',s.rank_mute)}
        ${rank('rank_kick','👢 Кикнуть из чата',s.rank_kick)}
        ${rank('rank_ban','🔨 Забанить навсегда',s.rank_ban)}
        ${rank('rank_shield','🛡 Выдавать щит',s.rank_shield)}
        ${rank('rank_immune','🔰 Давать иммунитет',s.rank_immune)}
        ${rank('rank_duel','⚔️ Начинать дуэли',s.rank_duel,true)}
        ${rank('rank_marriage','💍 Предлагать брак',s.rank_marriage,true)}
        ${rank('rank_give','💸 Переводить мору/алмазы',s.rank_give,true)}
        ${rank('purge_min_rank','🧹 Не проверяется чисткой',s.purge_min_rank)}
        ${rank('purge_action_rank','⚖️ Кнопки вердикта в сводке',s.purge_action_rank)}
        ${rank('rank_chat_lock','🔒 Открывать/закрывать чат',s.rank_chat_lock)}
      </div>
      <div class="card">
        <div class="card-title">🧹 Чистка активности — сводка</div>
        <div style="font-size:11px;color:var(--muted);line-height:1.5;margin-bottom:8px">
          Бот соберёт сводку активности и пришлёт <b>досье с кнопками</b> (Варн/Кик/Бан) в <b>админ-чат</b> (если привязан), иначе в основной чат.
          Чат <b>не блокируется</b>, никакие действия над людьми не выполняются автоматически — решение по каждому принимаешь ты.
        </div>
        <div style="display:flex;gap:6px;margin:0 0 6px">
          <input id="purge-start" type="date" class="num-input" style="flex:1;margin:0" title="Начало периода"/>
          <input id="purge-end" type="date" class="num-input" style="flex:1;margin:0" title="Конец периода"/>
          <input id="purge-norm" type="number" class="num-input" style="width:80px;margin:0" placeholder="Норма" value="50" min="1"/>
        </div>
        <div style="font-size:10px;color:var(--muted);margin-bottom:6px">Пусто = последние 7 дней, норма 50.</div>
        <button class="btn btn-gold btn-full" onclick="doPurgeStart()">📋 Сформировать сводку</button>
      </div>
      <div id="adm-save-status" style="font-size:11px;color:var(--muted);text-align:center;margin-top:6px"></div>`;
    el('adm-settings')._settings=s;
  }).catch(e=>{el('adm-settings').innerHTML=`<div class="err">${e}</div>`;});
}
function doPurgeStart() {
  const sd=el('purge-start')?.value||null, ed=el('purge-end')?.value||null;
  const norm=parseInt(el('purge-norm')?.value||'50')||50;
  OM('🧹 Сформировать сводку чистки?',
    `<div style="text-align:center;padding:12px 0;color:var(--muted)">Бот соберёт активность и пришлёт сводку + досье с кнопками. Чат <b>не блокируется</b>.<div style="font-size:11px;margin-top:6px">Период: ${sd||'−7 дней'} — ${ed||'сегодня'} · Норма: ${norm}</div></div>`,
    [{l:'Да, собрать',c:'btn-gold',f:`_execPurgeStart(${JSON.stringify(sd)},${JSON.stringify(ed)},${norm})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execPurgeStart(sd, ed, norm) {
  api(`/admin/${_adminChatId}/purge/start`,{method:'POST',body:JSON.stringify({start_date:sd,end_date:ed,norm})})
    .then(r=>{toast(`📋 Сводка готова: ✅${r.passed} ❌${r.failed} 🛡${r.protected}${r.routed_to_admin_chat?' · в админ-чат':''}`);CM();})
    .catch(e=>toast(e,false));
}
let _admSaveTimer=null;
function toggleAdmSetting(key) {
  const el2=el('aset-'+key); if(!el2) return;
  const cur=el2.textContent==='ВКЛ';
  el2.textContent=cur?'ВЫКЛ':'ВКЛ';
  el2.style.color=cur?'var(--red)':'var(--green)';
  queueAdmSave();
}
function queueAdmSave() {
  clearTimeout(_admSaveTimer);
  if(el('adm-save-status')) el('adm-save-status').textContent='...';
  _admSaveTimer=setTimeout(saveAdmSettings, 1000);
}
function saveAdmSettings() {
  const keys=['module_shop','module_gacha','module_zoo','module_expeditions','module_auction',
              'module_games','module_exchange','module_quests','module_daily_deal',
              'events_enabled','nsfw_warps_allowed','rank_warn','rank_mute','rank_kick','rank_ban',
              'rank_shield','rank_immune','rank_duel','rank_marriage','rank_give','purge_min_rank',
              'purge_action_rank','rank_chat_lock'];
  const body={};
  for(const k of keys) {
    const e2=el('aset-'+k); if(!e2) continue;
    if(e2.tagName==='SELECT') body[k]=parseInt(e2.value);
    else body[k]=e2.textContent==='ВКЛ'?1:0;
  }
  api(`/admin/${_adminChatId}/settings`,{method:'POST',body:JSON.stringify(body)})
    .then(()=>{ if(el('adm-save-status')) { el('adm-save-status').textContent='✅ Сохранено'; setTimeout(()=>{const s=el('adm-save-status');if(s)s.textContent='';},2000); } })
    .catch(e=>{ if(el('adm-save-status')) el('adm-save-status').textContent='❌ '+e; });
}
function loadAdminLogs() {
  if(!_adminChatId) return;
  el('adm-logs').innerHTML='<div class="loader">Загрузка...</div>';
  const filterBar=`<div class="tabs" style="margin-bottom:8px">
    <button class="tb ${!_admLogFilter?'active':''}" onclick="admLogFilter('')">Все</button>
    <button class="tb ${_admLogFilter==='ban'?'active':''}" onclick="admLogFilter('ban')">🚫 Баны</button>
    <button class="tb ${_admLogFilter==='kick'?'active':''}" onclick="admLogFilter('kick')">🥾 Кики</button>
    <button class="tb ${_admLogFilter==='left'?'active':''}" onclick="admLogFilter('left')">👋 Вышедшие</button>
  </div>`;
  if(_admLogFilter==='left'){
    api(`/admin/${_adminChatId}/left`).then(d=>{
      const rows=d.left||[];
      el('adm-logs').innerHTML=filterBar+(rows.length?`<div class="card">
        <div class="card-title">👋 Вышедшие из чата (${rows.length})</div>
        ${rows.map(u=>`<div class="irow"><span class="ik">@${u.user_tg_username||'ID'+u.user_tg_id}</span><span class="iv" style="font-size:10px;color:var(--muted)">ID: ${u.user_tg_id}</span></div>`).join('')}
      </div>`:'<div class="card" style="text-align:center;padding:20px;color:var(--muted)">Никто не выходил</div>');
    }).catch(e=>{el('adm-logs').innerHTML=filterBar+`<div class="err">${e}</div>`;});
    return;
  }
  api(`/admin/${_adminChatId}/logs?page=${_adminPage}${_admLogFilter?'&action='+_admLogFilter:''}`).then(d=>{
    const total=d.total||0, pages=Math.ceil(total/(d.page_size||25));
    el('adm-logs').innerHTML=filterBar+`
      <div style="overflow-x:auto">
        <table class="adm-table">
          <thead><tr><th>Время</th><th>Действие</th><th>Цель</th><th>Модератор</th><th>Причина</th></tr></thead>
          <tbody>
            ${d.logs.map(l=>`<tr>
              <td style="font-size:10px;white-space:nowrap">${fmtUTC(l.created_at)||'?'}</td>
              <td><span style="font-size:11px;font-weight:600">${l.action}</span></td>
              <td style="font-size:11px">@${vipName(l.target_name||'ID'+l.user_id, l.target_is_vip)}</td>
              <td style="font-size:11px">@${vipName(l.admin_name||'ID'+l.admin_id, l.admin_is_vip)}</td>
              <td style="font-size:10px;color:var(--muted)">${l.reason||'—'}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;font-size:11px;color:var(--muted)">
        <span>Всего: ${total}</span>
        <div style="display:flex;gap:6px">
          <button class="btn btn-sm btn-ghost" ${_adminPage<=1?'disabled':''} onclick="admLogPage(${_adminPage-1})">◀</button>
          <span>${_adminPage}/${pages||1}</span>
          <button class="btn btn-sm btn-ghost" ${_adminPage>=pages?'disabled':''} onclick="admLogPage(${_adminPage+1})">▶</button>
        </div>
      </div>`;
  }).catch(e=>{el('adm-logs').innerHTML=filterBar+`<div class="err">${e}</div>`;});
}
function admLogPage(p) { _adminPage=p; loadAdminLogs(); }
function admLogFilter(f) { _admLogFilter=f; _adminPage=1; loadAdminLogs(); }

// ── Admin Moderation tab — активные муты, предупреждения, свежие действия ────────
function loadAdminMod() {
  if(!_adminChatId) return;
  el('adm-mod').innerHTML='<div class="loader">Загрузка...</div>';
  Promise.all([
    api(`/admin/${_adminChatId}/users?sort=warns&page=1`),
    api(`/admin/${_adminChatId}/logs?page=1`),
  ]).then(([ud, ld])=>{
    const now = Date.now();
    const users = ud.users||[];
    const muted = users.filter(u=>{
      if(!u.muted_until) return false;
      const ts = new Date(u.muted_until.replace(' ','T')+'Z').getTime();
      return ts > now;
    });
    const warned = users.filter(u=>(u.warnings||0)>0);
    const logs = (ld.logs||[]).slice(0,8);
    const ACTION_COL = {ban:'var(--red)',kick:'var(--red)',mute:'var(--gold)',
      unmute:'var(--green)',warn:'var(--gold)',unwarn:'var(--green)',unban:'var(--green)',immune:'var(--blue)'};
    const userRow = (u,badge) => `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border2)">
      <span style="font-size:12px;color:var(--bright)">@${vipName(u.user_tg_username||'ID'+u.user_tg_id, u.is_vip)}</span>
      <span style="font-size:11px">${badge}</span>
    </div>`;
    el('adm-mod').innerHTML=`
      ${muted.length?`<div class="card">
        <div class="card-title" style="color:var(--red)">🔇 Активные муты (${muted.length})</div>
        ${muted.map(u=>userRow(u,`<span style="color:var(--muted);font-size:10px">до ${u.muted_until?.slice(0,16)||'?'}</span>
          <button class="btn btn-sm btn-ghost" style="margin-left:6px" onclick="openAdminAction(${u.user_tg_id},'@${u.user_tg_username||u.user_tg_id}',{w:${!!u.can_warn},m:${!!u.can_mute},k:${!!u.can_kick},b:${!!u.can_ban},s:${!!u.can_shield},i:${!!u.can_immune}})">⚡</button>`)).join('')}
      </div>`:''}
      ${warned.length?`<div class="card">
        <div class="card-title" style="color:var(--gold)">⚠️ Предупреждения</div>
        ${warned.slice(0,10).map(u=>userRow(u,`<span style="color:var(--red);font-weight:700">${u.warnings}× ⚠️</span>
          <button class="btn btn-sm btn-ghost" style="margin-left:6px" onclick="openAdminAction(${u.user_tg_id},'@${u.user_tg_username||u.user_tg_id}',{w:${!!u.can_warn},m:${!!u.can_mute},k:${!!u.can_kick},b:${!!u.can_ban},s:${!!u.can_shield},i:${!!u.can_immune}})">⚡</button>`)).join('')}
      </div>`:''}
      ${!muted.length&&!warned.length?`<div class="card" style="text-align:center;padding:20px">
        <div style="font-size:28px;margin-bottom:8px">✅</div>
        <div style="font-size:13px;font-weight:700;color:var(--green)">Всё спокойно</div>
        <div style="font-size:11px;color:var(--muted);margin-top:4px">Нет активных мутов и предупреждений</div>
      </div>`:''}
      <div class="card">
        <div class="card-title">📋 Последние действия</div>
        ${logs.length?logs.map(l=>{
          const base = (l.action||'').split('_')[0];
          const col = ACTION_COL[base]||'var(--muted)';
          return `<div style="display:flex;justify-content:space-between;align-items:flex-start;padding:5px 0;border-bottom:1px solid var(--border2)">
            <div>
              <span style="font-size:11px;font-weight:700;color:${col}">${l.action}</span>
              <span style="font-size:11px;color:var(--text)"> @${vipName(l.target_name||l.user_id, l.target_is_vip)}</span>
              ${l.reason?`<span style="font-size:10px;color:var(--muted)"> — ${l.reason}</span>`:''}
            </div>
            <span style="font-size:10px;color:var(--muted);white-space:nowrap;margin-left:8px">${fmtUTC(l.created_at)}</span>
          </div>`;
        }).join(''):'<div style="font-size:12px;color:var(--muted)">Нет записей</div>'}
        <button class="btn btn-ghost btn-sm btn-full" style="margin-top:8px" onclick="swAdminByName('logs')">Полный журнал →</button>
      </div>`;
  }).catch(e=>{el('adm-mod').innerHTML=`<div class="err">${e}</div>`;});
}

// ── 8.1: Чёрный список чата ──────────────────────────────────────────────────────
let _admLogFilter='', _admMaxRank=0;
function loadAdminBlacklist() {
  if(!_adminChatId) return;
  el('adm-bl').innerHTML='<div class="loader">Загрузка...</div>';
  api(`/admin/${_adminChatId}/blacklist`).then(d=>{
    const rows=d.blacklist||[];
    el('adm-bl').innerHTML=`
      <div class="card">
        <div class="card-title">➕ Добавить в ЧС</div>
        <div style="display:flex;gap:6px">
          <input id="bl-uid" type="number" class="num-input" style="flex:1;margin:0" placeholder="ID пользователя"/>
          <input id="bl-reason" type="text" class="num-input" style="flex:1.4;margin:0" placeholder="Причина" maxlength="200"/>
        </div>
        <button class="btn btn-red btn-full" style="margin-top:8px" onclick="doBlacklistAdd()">🚫 В чёрный список</button>
        <div style="font-size:10px;color:var(--muted);margin-top:4px">Игрок из ЧС не сможет вернуться в чат — бот забанит его при входе.</div>
      </div>
      ${rows.length?`<div class="card">
        <div class="card-title">🚫 Чёрный список (${rows.length})</div>
        ${rows.map(b=>`<div style="padding:6px 0;border-bottom:1px solid var(--border2)">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:12px;font-weight:600">@${b.username||'ID'+b.user_id}</span>
            <button class="btn btn-sm btn-ghost" onclick="doBlacklistRemove(${b.user_id})">✅ Убрать</button>
          </div>
          <div style="font-size:10px;color:var(--muted)">ID: ${b.user_id} · ${b.reason?esc(b.reason)+' · ':''}добавил @${b.added_by_name||'ID'+b.added_by}${b.added_at?' · '+fmtUTC(b.added_at):''}</div>
        </div>`).join('')}
      </div>`:'<div class="card" style="text-align:center;padding:20px;color:var(--muted)">Чёрный список пуст</div>'}`;
  }).catch(e=>{el('adm-bl').innerHTML=`<div class="err">${e}</div>`;});
}
function doBlacklistAdd() {
  const uid=parseInt(el('bl-uid')?.value||'0');
  const reason=el('bl-reason')?.value.trim()||null;
  if(!uid) return toast('Укажите ID пользователя',false);
  api(`/admin/${_adminChatId}/blacklist`,{method:'POST',body:JSON.stringify({user_id:uid,reason})})
    .then(()=>{toast('🚫 Добавлен в ЧС');loadAdminBlacklist();})
    .catch(e=>toast(e,false));
}
function doBlacklistRemove(uid) {
  api(`/admin/${_adminChatId}/blacklist/${uid}`,{method:'DELETE'})
    .then(()=>{toast('✅ Убран из ЧС');loadAdminBlacklist();})
    .catch(e=>toast(e,false));
}

// ── 8.2: Смена локального ранга ──────────────────────────────────────────────────
function openRankModal(userId, userName, currentRank) {
  const maxR=Math.max(0,_admMaxRank);
  const opts=[];
  for(let r=0;r<=maxR;r++) opts.push(`<option value="${r}" ${r===currentRank?'selected':''}>${_RANK_NAMES[r]||r}</option>`);
  OM(`🎖 Ранг — ${userName||'ID'+userId}`,`
    <div style="font-size:11px;color:var(--muted);margin-bottom:6px">Текущий: ${_RANK_NAMES[currentRank]||currentRank}. Можно выдать до ранга ниже вашего.</div>
    <select id="rank-sel" class="num-input" style="margin:0">${opts.join('')}</select>
  `,[{l:'Сохранить',c:'btn-gold',f:`doSetLocalRank(${userId})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function doSetLocalRank(userId) {
  const newRank=parseInt(el('rank-sel')?.value||'0');
  api(`/admin/${_adminChatId}/users/${userId}/rank`,{method:'POST',body:JSON.stringify({new_rank:newRank})})
    .then(r=>{toast(`🎖 Назначено: ${r.rank_name}`);CM();loadAdminUsers();})
    .catch(e=>toast(e,false));
}

// ── Init admin check after login ──────────────────────────────────────────────
function checkAdminAccess() {
  if(!_uid) return;
  api('/admin/my-chats').then(d=>{
    _adminChats=d.chats||[];
    _updateMoreCard();
  }).catch(()=>{});
}
// Refresh current page data
function refreshPage() {
  const page = _activePage;
  const rb = document.querySelector('.hdr-refresh');
  if (rb) { rb.classList.remove('spinning'); void rb.offsetWidth; rb.classList.add('spinning'); }
  const loaders = {
    profile:loadProfile, zoo:()=>{_zooData=null;loadZoo();}, arena:loadArena, market:loadMarket,
    bp:loadBattlePass, auction:loadAuctionPage,
    admin:()=>{_adminChats=null;loadAdmin();}, global:loadGlobal
  };
  if(page && loaders[page]) { _loaded.delete(page); loaders[page](); toast('🔄 Обновлено!'); }
}

// ── Global Moderation (Block 7) ──────────────────────────────────────────────────
let _glbTab='chats', _glbChatsList=null, _glbChatId=0, _glbChatTitle='';
let _glbMembersPage=1, _glbMembersSearch='', _glbMembersSort='messages', _glbSearchTimer=null;
let _glbSanctionsType='', _glbLogPage=1, _glbAppealsStatus='pending', _glbSanctionTarget=null;
const _SANCTION_LABELS={warn:'⚠️ Варн', restrict:'🔇 Ограничение', ban:'🚫 Бан'};

function esc(s) { return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function _actorSanctionPerms() {
  const r=_profileData?.global_rank||0;
  return {warn:r>=1, restrict:r>=2, ban:r>=3};
}

function loadGlobal() {
  swGlobal(_glbTab, document.querySelector(`#pg-global .tb[onclick*="'${_glbTab}'"]`));
}
function swGlobal(tab, btn) {
  _glbTab=tab;
  document.querySelectorAll('#pg-global .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  ['chats','sanctions','log','appeals','ranks','dev'].forEach(t=>el('glb-'+t).style.display=t===tab?'':'none');
  if(tab==='chats') loadGlobalChats();
  else if(tab==='sanctions') loadGlobalSanctions();
  else if(tab==='log') { _glbLogPage=1; loadGlobalLog(); }
  else if(tab==='appeals') loadGlobalAppeals();
  else if(tab==='ranks') loadGlobalRanksTab();
  else if(tab==='dev') loadGlobalDev();
}

// 1. Все чаты ─────────────────────────────────────────────────────────────────────
function loadGlobalChats() {
  el('glb-chats').innerHTML='<div class="loader">Загрузка...</div>';
  api('/admin/global/chats').then(d=>{
    _glbChatsList=d.chats||[];
    const perms=_actorSanctionPerms();
    if(!_glbChatsList.length){
      el('glb-chats').innerHTML='<div class="empty-state"><div class="es-icon">💬</div><div class="es-title">Нет групп</div><div class="es-sub">Показываются только группы, в которых вы состоите</div></div>';
      return;
    }
    const roleIcon = c => c.role==='admin' ? '🛡' : c.role==='main' ? '🏠' : '💬';
    el('glb-chats').innerHTML=`
      <div class="card">
        <div class="card-title">💬 Мои группы (${_glbChatsList.length})</div>
        ${_glbChatsList.map(c=>`<div style="padding:8px 0;border-bottom:1px solid var(--border2)">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
            <span style="cursor:pointer;font-weight:600;color:var(--bright);font-size:12.5px" onclick="openGlobalChatMembers(${c.chat_id})">${roleIcon(c)} ${esc(c.chat_title)}</span>
            <span style="display:flex;align-items:center;gap:6px;flex:none">
              <span style="cursor:pointer;font-size:11px;color:var(--muted)" onclick="openGlobalChatMembers(${c.chat_id})">${c.member_count} 👤 ›</span>
              ${(perms.restrict||perms.ban)?`<button class="btn btn-sm btn-ghost" style="padding:2px 6px;font-size:10px" onclick="openGlobalChatSanction(${c.chat_id})">⚡</button>`:''}
            </span>
          </div>
          ${c.linked_title?`<div style="font-size:9.5px;color:var(--dim);margin-top:2px">${c.role==='admin'?`🛡 админ-чат для «${esc(c.linked_title)}»`:`🛡 админ-чат: «${esc(c.linked_title)}»`}</div>`:''}
        </div>`).join('')}
      </div>`;
  }).catch(e=>{el('glb-chats').innerHTML=`<div class="err">${e}</div>`;});
}
function openGlobalChatSanction(chatId) {
  const chat=(_glbChatsList||[]).find(c=>c.chat_id===chatId);
  openGlobalSanctionForm('chat', chatId, chat?.chat_title, _actorSanctionPerms());
}
function openGlobalChatMembers(chatId) {
  const chat=(_glbChatsList||[]).find(c=>c.chat_id===chatId);
  _glbChatId=chatId; _glbChatTitle=chat?.chat_title||('Chat '+chatId);
  _glbMembersPage=1; _glbMembersSearch=''; _glbMembersSort='messages';
  loadGlobalChatMembers();
}
function loadGlobalChatMembers() {
  el('glb-chats').innerHTML='<div class="loader">Загрузка...</div>';
  api(`/admin/global/chats/${_glbChatId}/members?page=${_glbMembersPage}&search=${encodeURIComponent(_glbMembersSearch)}&sort=${_glbMembersSort}`)
    .then(renderGlobalMembers)
    .catch(e=>{el('glb-chats').innerHTML=`<div class="err">${e}</div>`;});
}
function renderGlobalMembers(d) {
  const total=d.total||0, pages=Math.ceil(total/(d.page_size||20));
  el('glb-chats').innerHTML=`
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      <button class="btn btn-sm btn-ghost" onclick="loadGlobalChats()">← Назад</button>
      <span style="font-size:13px;font-weight:700">${esc(_glbChatTitle)}</span>
    </div>
    <div style="display:flex;gap:6px;margin-bottom:8px">
      <input id="glb-search" type="text" class="num-input" style="flex:1;margin:0" placeholder="Поиск по нику/ID" value="${esc(_glbMembersSearch)}" oninput="onGlobalMemberSearch(this.value)"/>
      <select class="num-input" style="width:120px;margin:0" onchange="onGlobalMemberSort(this.value)">
        <option value="messages" ${_glbMembersSort==='messages'?'selected':''}>По сообщ.</option>
        <option value="level" ${_glbMembersSort==='level'?'selected':''}>По уровню</option>
        <option value="rank" ${_glbMembersSort==='rank'?'selected':''}>По рангу</option>
        <option value="warns" ${_glbMembersSort==='warns'?'selected':''}>По варнам</option>
      </select>
    </div>
    <div style="overflow-x:auto">
      <table class="adm-table">
        <thead><tr><th>Пользователь</th><th>Ур.</th><th>Глоб.ранг</th><th>Действия</th></tr></thead>
        <tbody>
          ${d.members.map(m=>`<tr>
            <td>
              <div style="font-weight:600;font-size:12px">@${vipName(m.user_tg_username||'ID'+m.user_tg_id, m.is_vip)}</div>
              <div style="font-size:10px;color:var(--muted)">ID: ${m.user_tg_id} · ${m.user_messages_count_all_time||0} сообщ.</div>
              <div style="font-size:9.5px;color:var(--dim)">📅 ${m.joined_at?fmtUTC(m.joined_at):'—'} · 🕓 ${m.last_message_at?fmtUTC(m.last_message_at):'—'}</div>
            </td>
            <td style="text-align:center">${m.user_level||1}</td>
            <td style="font-size:10px">${m.global_rank_name}</td>
            <td>
              ${(m.can_warn||m.can_restrict||m.can_ban)?`<button class="btn btn-sm btn-ghost" style="font-size:10px;padding:3px 6px" onclick='openGlobalSanctionForm("user",${m.user_tg_id},${JSON.stringify(m.user_tg_username||'ID'+m.user_tg_id)},${JSON.stringify({warn:m.can_warn,restrict:m.can_restrict,ban:m.can_ban})})'>⚡</button>`:`<span style="font-size:10px;color:var(--dim)">—</span>`}
            </td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;font-size:11px;color:var(--muted)">
      <span>Всего: ${total}</span>
      <div style="display:flex;gap:6px">
        <button class="btn btn-sm btn-ghost" ${_glbMembersPage<=1?'disabled':''} onclick="glbMemberPage(${_glbMembersPage-1})">◀</button>
        <span>${_glbMembersPage}/${pages||1}</span>
        <button class="btn btn-sm btn-ghost" ${_glbMembersPage>=pages?'disabled':''} onclick="glbMemberPage(${_glbMembersPage+1})">▶</button>
      </div>
    </div>`;
}
function glbMemberPage(p) { _glbMembersPage=p; loadGlobalChatMembers(); }
function onGlobalMemberSearch(v) {
  clearTimeout(_glbSearchTimer);
  _glbSearchTimer=setTimeout(()=>{ _glbMembersSearch=v; _glbMembersPage=1; loadGlobalChatMembers(); },400);
}
function onGlobalMemberSort(v) { _glbMembersSort=v; _glbMembersPage=1; loadGlobalChatMembers(); }

// Форма выдачи санкции — используется из «Все чаты» и для «изменить срок» ─────────
function openGlobalSanctionForm(targetType, targetId, targetName, perms) {
  perms = perms || _actorSanctionPerms();
  if(!targetName) targetName = (targetType==='chat'?'Чат ID':'ID')+targetId;
  _glbSanctionTarget={type:targetType, id:targetId};
  const durations=[[0,'Бессрочно'],[1,'1 день'],[3,'3 дня'],[7,'7 дней'],[30,'30 дней']];
  OM(`⚡ ${targetName}`,`
    <div style="display:flex;gap:6px;margin-bottom:8px">
      <button class="btn btn-sm ${perms.warn?'btn-ghost':''}" ${perms.warn?'':'disabled'} onclick="selectGlobalSanctionType('warn')" id="gst-warn">⚠️ Варн</button>
      <button class="btn btn-sm ${perms.restrict?'btn-ghost':''}" ${perms.restrict?'':'disabled'} onclick="selectGlobalSanctionType('restrict')" id="gst-restrict">🔇 Огранич.</button>
      <button class="btn btn-sm ${perms.ban?'btn-red':''}" ${perms.ban?'':'disabled'} onclick="selectGlobalSanctionType('ban')" id="gst-ban">🚫 Бан</button>
    </div>
    <div id="gst-duration" style="display:none;margin-bottom:8px">
      <select id="gst-dur-sel" class="num-input" style="margin:0">
        ${durations.map(([dd,l])=>`<option value="${dd}">${l}</option>`).join('')}
      </select>
    </div>
    <input id="gst-reason" type="text" class="num-input" style="margin:0" placeholder="Причина" maxlength="200"/>
  `,[{l:'Выдать',c:'btn-gold',f:'doIssueGlobalSanction()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
  el('modal')._sanctionType=null;
}
function selectGlobalSanctionType(type) {
  el('modal')._sanctionType=type;
  ['warn','restrict','ban'].forEach(t=>{const b=el('gst-'+t); if(b) b.style.outline=t===type?'2px solid var(--gold)':'';});
  el('gst-duration').style.display=(type==='restrict'||type==='ban')?'':'none';
}
function doIssueGlobalSanction() {
  const type=el('modal')._sanctionType;
  if(!type) return toast('Выберите тип санкции',false);
  const reason=el('gst-reason')?.value.trim()||null;
  const durSel=el('gst-dur-sel');
  const days=durSel&&durSel.value!=='0'?parseInt(durSel.value):null;
  api('/admin/global/sanctions',{method:'POST',body:JSON.stringify({
    target_type:_glbSanctionTarget.type, target_id:_glbSanctionTarget.id,
    sanction_type:type, reason, duration_days:days,
  })}).then(r=>{
    toast(r.message||'✅ Готово'); CM();
    if(_glbTab==='chats'&&_glbChatId) loadGlobalChatMembers();
    else if(_glbTab==='sanctions') loadGlobalSanctions();
  }).catch(e=>toast(e,false));
}

// 2. Активные ограничения ─────────────────────────────────────────────────────────
function loadGlobalSanctions() {
  el('glb-sanctions').innerHTML='<div class="loader">Загрузка...</div>';
  api(`/admin/global/sanctions?active_only=true${_glbSanctionsType?'&type='+_glbSanctionsType:''}`).then(d=>{
    el('glb-sanctions').innerHTML=`
      <div class="tabs" style="margin-bottom:8px">
        <button class="tb ${!_glbSanctionsType?'active':''}" onclick="filterGlobalSanctions('')">Все</button>
        <button class="tb ${_glbSanctionsType==='warn'?'active':''}" onclick="filterGlobalSanctions('warn')">⚠️ Варны</button>
        <button class="tb ${_glbSanctionsType==='restrict'?'active':''}" onclick="filterGlobalSanctions('restrict')">🔇 Огранич.</button>
        <button class="tb ${_glbSanctionsType==='ban'?'active':''}" onclick="filterGlobalSanctions('ban')">🚫 Баны</button>
      </div>
      ${d.sanctions.length?d.sanctions.map(s=>`<div class="card">
        <div class="irow"><span class="ik">${_SANCTION_LABELS[s.sanction_type]||s.sanction_type}</span><span class="iv">${s.target_type==='chat'?'💬 ':'👤 '}${esc(s.target_name)}</span></div>
        <div class="irow"><span class="ik">Причина</span><span style="font-size:11px">${esc(s.reason||'—')}</span></div>
        <div class="irow"><span class="ik">Выдал</span><span style="font-size:11px">${s.issued_by_name}</span></div>
        <div class="irow"><span class="ik">До</span><span style="font-size:11px">${s.expires_at?fmtUTC(s.expires_at):'Бессрочно'}</span></div>
        <div style="display:flex;gap:6px;margin-top:6px">
          <button class="btn btn-sm btn-ghost" style="flex:1" onclick="doRevokeGlobalSanction(${s.id})">✅ Снять</button>
          ${s.sanction_type!=='warn'?`<button class="btn btn-sm btn-ghost" style="flex:1" onclick='openGlobalSanctionForm(${JSON.stringify(s.target_type)},${s.target_id},null,${JSON.stringify(_actorSanctionPerms())})'>✏️ Изменить срок</button>`:''}
        </div>
      </div>`).join(''):'<div class="card" style="text-align:center;padding:20px;color:var(--muted)">Нет активных ограничений</div>'}`;
  }).catch(e=>{el('glb-sanctions').innerHTML=`<div class="err">${e}</div>`;});
}
function filterGlobalSanctions(type) { _glbSanctionsType=type; loadGlobalSanctions(); }
function doRevokeGlobalSanction(id) {
  OM('✅ Снять ограничение?','<div style="text-align:center;padding:12px 0;color:var(--muted)">Санкция будет немедленно снята.</div>',
    [{l:'Да, снять',c:'btn-gold',f:`_execRevokeGlobalSanction(${id})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execRevokeGlobalSanction(id) {
  api(`/admin/global/sanctions/${id}/revoke`,{method:'POST'})
    .then(r=>{toast(r.message||'✅ Снято');CM();loadGlobalSanctions();})
    .catch(e=>toast(e,false));
}

// 3. Журнал ───────────────────────────────────────────────────────────────────────
function loadGlobalLog() {
  el('glb-log').innerHTML='<div class="loader">Загрузка...</div>';
  api(`/admin/global/log?page=${_glbLogPage}`).then(d=>{
    const total=d.total||0, pages=Math.ceil(total/(d.page_size||25));
    el('glb-log').innerHTML=`
      <div style="overflow-x:auto">
        <table class="adm-table">
          <thead><tr><th>Время</th><th>Тип</th><th>Цель</th><th>Модератор</th><th>Причина</th><th>Статус</th></tr></thead>
          <tbody>
            ${d.logs.map(s=>`<tr>
              <td style="font-size:10px;white-space:nowrap">${fmtUTC(s.created_at)||'?'}</td>
              <td style="font-size:11px;font-weight:600">${_SANCTION_LABELS[s.sanction_type]||s.sanction_type}</td>
              <td style="font-size:11px">${s.target_type==='chat'?'💬':'👤'} ${esc(s.target_name)}</td>
              <td style="font-size:11px">${s.issued_by_name}</td>
              <td style="font-size:10px;color:var(--muted)">${esc(s.reason||'—')}</td>
              <td style="font-size:10px">${s.is_active?'<span style="color:var(--green)">Активна</span>':s.revoked_by_name?`<span style="color:var(--muted)">Снята: ${s.revoked_by_name}</span>`:'<span style="color:var(--muted)">Истекла</span>'}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;font-size:11px;color:var(--muted)">
        <span>Всего: ${total}</span>
        <div style="display:flex;gap:6px">
          <button class="btn btn-sm btn-ghost" ${_glbLogPage<=1?'disabled':''} onclick="glbLogPage(${_glbLogPage-1})">◀</button>
          <span>${_glbLogPage}/${pages||1}</span>
          <button class="btn btn-sm btn-ghost" ${_glbLogPage>=pages?'disabled':''} onclick="glbLogPage(${_glbLogPage+1})">▶</button>
        </div>
      </div>`;
  }).catch(e=>{el('glb-log').innerHTML=`<div class="err">${e}</div>`;});
}
function glbLogPage(p) { _glbLogPage=p; loadGlobalLog(); }

// 4. Апелляции ──────────────────────────────────────────────────────────────────────
function loadGlobalAppeals() {
  el('glb-appeals').innerHTML='<div class="loader">Загрузка...</div>';
  api(`/admin/global/appeals?status=${_glbAppealsStatus}`).then(d=>{
    el('glb-appeals').innerHTML=`
      <div class="tabs" style="margin-bottom:8px">
        <button class="tb ${_glbAppealsStatus==='pending'?'active':''}" onclick="filterGlobalAppeals('pending')">⏳ Новые</button>
        <button class="tb ${_glbAppealsStatus==='accepted'?'active':''}" onclick="filterGlobalAppeals('accepted')">✅ Принятые</button>
        <button class="tb ${_glbAppealsStatus==='rejected'?'active':''}" onclick="filterGlobalAppeals('rejected')">❌ Отклонённые</button>
      </div>
      ${d.appeals.length?d.appeals.map(a=>`<div class="card">
        <div class="irow"><span class="ik">От</span><span class="iv">${a.user_name}</span></div>
        <div class="irow"><span class="ik">Санкция</span><span style="font-size:11px">${_SANCTION_LABELS[a.sanction_type]||'?'}${a.sanction_active===false?' (уже снята)':''}</span></div>
        <div class="irow"><span class="ik">Причина санкции</span><span style="font-size:11px">${esc(a.sanction_reason||'—')}</span></div>
        <div style="margin:6px 0;padding:8px;background:var(--dim);border-radius:6px;font-size:12px">${esc(a.text)}</div>
        <div class="irow"><span class="ik">Когда</span><span style="font-size:11px">${fmtUTC(a.created_at)}</span></div>
        ${a.status==='pending'?`<div style="display:flex;gap:6px;margin-top:6px">
          <button class="btn btn-sm btn-gold" style="flex:1" onclick="doResolveAppeal(${a.id},'accept')">✅ Снять санкцию</button>
          <button class="btn btn-sm btn-ghost" style="flex:1" onclick="doResolveAppeal(${a.id},'reject')">❌ Отклонить</button>
        </div>`:`<div class="irow"><span class="ik">Решение</span><span style="font-size:11px">${a.status==='accepted'?'✅ Принята':'❌ Отклонена'}${a.resolved_by_name?' · '+a.resolved_by_name:''}</span></div>`}
      </div>`).join(''):'<div class="card" style="text-align:center;padding:20px;color:var(--muted)">Нет апелляций</div>'}`;
  }).catch(e=>{el('glb-appeals').innerHTML=`<div class="err">${e}</div>`;});
}
function filterGlobalAppeals(status) { _glbAppealsStatus=status; loadGlobalAppeals(); }
function doResolveAppeal(id, action) {
  if(action==='reject'){
    OM('❌ Отклонить апелляцию?','<div style="text-align:center;padding:12px 0;color:var(--muted)">Апелляция будет отклонена, санкция останется в силе.</div>',
      [{l:'Да, отклонить',c:'btn-red',f:`_execResolveAppeal(${id},'reject')`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
    return;
  }
  OM('✅ Снять санкцию?','<div style="text-align:center;padding:12px 0;color:var(--muted)">Санкция будет снята, апелляция помечена как принятая.</div>',
    [{l:'Да, снять',c:'btn-gold',f:`_execResolveAppeal(${id},'accept')`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execResolveAppeal(id, action) {
  api(`/admin/global/appeals/${id}/resolve`,{method:'POST',body:JSON.stringify({action})})
    .then(r=>{toast(r.message||'✅ Готово');CM();loadGlobalAppeals();})
    .catch(e=>toast(e,false));
}

// 5. Управление штатом ────────────────────────────────────────────────────────────────
function loadGlobalRanksTab() {
  el('glb-ranks').innerHTML=`
    <div class="card">
      <div class="card-title">👮 Назначить ранг</div>
      <input id="glb-rank-uid" type="number" class="num-input" style="margin-bottom:6px" placeholder="ID пользователя"/>
      <select id="glb-rank-sel" class="num-input" style="margin-bottom:6px">
        <option value="0">👤 Снять (Пользователь)</option>
        <option value="1">🛡 Хелпер</option>
        <option value="2">⚔️ Старший хелпер</option>
      </select>
      <button class="btn btn-gold btn-full" onclick="doSetGlobalRank()">Сохранить</button>
    </div>`;
}
function doSetGlobalRank() {
  const uid=parseInt(el('glb-rank-uid')?.value||'0');
  const rank=parseInt(el('glb-rank-sel')?.value||'0');
  if(!uid) return toast('Укажите ID пользователя',false);
  api('/admin/global/ranks',{method:'POST',body:JSON.stringify({user_id:uid,global_rank:rank})})
    .then(r=>toast(`✅ Назначено: ${r.rank_name}`))
    .catch(e=>toast(e,false));
}

