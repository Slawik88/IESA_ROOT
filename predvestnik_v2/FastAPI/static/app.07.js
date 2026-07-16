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
          `<span class="badge" style="background:${v?'rgba(86,196,106,.14)':'var(--dim)'};border:1px solid ${v?'rgba(86,196,106,.3)':'var(--border2)'};color:${v?'var(--green)':'var(--muted)'};padding:3px 8px;border-radius:8px;font-size:11px;margin:2px">${n}</span>`
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
    <div class="card" style="padding:8px 14px">
      ${d.users.map(u=>{
        // UX: полный статус модерации участника (бан/глоб.ЧС/мут/кик/иммун/ушёл)
        const status=[
          u.is_banned?'<span style="color:var(--red)">🚫 забанен</span>':'',
          u.global_ban?'<span style="color:var(--red)">⛔ глоб.ЧС</span>':'',
          u.muted_until?`<span style="color:var(--gold)">🔇 до ${u.muted_until.slice(0,16)}</span>`:'',
          (!u.is_banned&&u.was_kicked)?'<span style="color:var(--muted)">👢 кикали</span>':'',
          u.is_immune?'🛡 Иммун':'',
          u.is_left?'👋 Ушёл':'',
        ].filter(Boolean).join(' · ');
        return `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border2)">
        <span style="flex:1;min-width:0">
          <span style="font-weight:600;font-size:12px;color:var(--bright)">@${vipName(u.user_tg_username||'ID'+u.user_tg_id, u.is_vip)}</span>
          <span style="font-size:10px;color:var(--muted)"> · ур.${u.user_level||1} · ${_RANK_NAMES[u.local_rank||0]||'?'}</span>
          ${(u.warnings||0)>0?`<span style="font-size:10px;color:var(--gold)"> · ⚠️${u.warnings}</span>`:''}
          ${status?`<span style="font-size:10px"> · ${status}</span>`:''}<br>
          <span style="font-size:10px;color:var(--muted)">ID ${u.user_tg_id} · ${u.user_messages_count_all_time||0} сообщ. · 📅 ${u.joined_at?fmtUTC(u.joined_at):'—'} · 🕓 ${u.last_message_at?fmtUTC(u.last_message_at):'—'}</span>
        </span>
        <span style="display:flex;gap:4px;flex:none">
          ${u.can_act?`<button class="btn btn-sm btn-ghost" style="padding:4px 8px" onclick='openAdminAction(${u.user_tg_id},${JSON.stringify(u.user_tg_username||'ID'+u.user_tg_id)},${JSON.stringify({w:u.can_warn,m:u.can_mute,k:u.can_kick,b:u.can_ban,s:u.can_shield,i:u.can_immune})})'>⚡</button>`:''}
          ${u.can_set_rank?`<button class="btn btn-sm btn-ghost" style="padding:4px 8px" title="Сменить ранг" onclick='openRankModal(${u.user_tg_id},${JSON.stringify(u.user_tg_username||'ID'+u.user_tg_id)},${u.local_rank||0})'>🎖</button>`:''}
        </span>
      </div>`;}).join('')}
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;font-size:11px;color:var(--muted)">
      <span>Всего: ${total}</span>
      <div style="display:flex;gap:6px">
        <button class="btn btn-sm btn-ghost" aria-label="Предыдущая страница" ${_adminPage<=1?'disabled':''} onclick="admPage(${_adminPage-1})">◀</button>
        <span>${_adminPage}/${pages||1}</span>
        <button class="btn btn-sm btn-ghost" aria-label="Следующая страница" ${_adminPage>=pages?'disabled':''} onclick="admPage(${_adminPage+1})">▶</button>
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
        <div class="card-title">🔔 Игровые уведомления в чат</div>
        <div style="font-size:10.5px;color:var(--muted);margin-bottom:6px">Глушится только сообщение в чат — механики и личные уведомления работают. Административные сообщения (модерация/чистка) шлются всегда, тумблера нет.</div>
        ${tog('notif_auction','🏛 Новые лоты аукциона',s.notif_auction)}
        ${tog('notif_gacha','🎰 Крутки гачи',s.notif_gacha)}
        ${tog('notif_expeditions','💫 Возврат из походов',s.notif_expeditions)}
        ${tog('notif_quests','📋 Выполненные квесты',s.notif_quests)}
      </div>
      <div class="card">
        <div class="card-title">⚖️ Минимальный ранг для действий</div>
        ${rank('rank_warn','⚠️ Выдавать варны',s.rank_warn)}
        ${rank('rank_mute','🔇 Ставить мут',s.rank_mute)}
        ${rank('rank_kick','👢 Кикнуть из чата',s.rank_kick)}
        ${rank('rank_ban','🔨 Забанить навсегда',s.rank_ban)}
        ${rank('rank_shield','🛡 Выдавать щит',s.rank_shield)}
        ${rank('rank_immune','🔰 Давать иммунитет',s.rank_immune)}
        ${rank('rank_marriage','💍 Предлагать брак',s.rank_marriage,true)}
        ${rank('rank_give','💸 Переводить мору/алмазы',s.rank_give,true)}
        ${rank('purge_min_rank','🧹 Освобождены от чистки (ранг ≥)',s.purge_min_rank)}
        ${rank('purge_action_rank','⚖️ Кнопки вердикта в сводке',s.purge_action_rank)}
        ${rank('purge_write_rank','✍️ Пишут во время чистки (0=все)',s.purge_write_rank,true)}
        ${rank('rank_chat_lock','🔒 Открывать/закрывать чат',s.rank_chat_lock)}
      </div>
      <div class="card">
        <div class="card-title">🧹 Чистка активности <button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px" onclick="loadPurgePanel()">🔄</button></div>
        <div style="font-size:11px;color:var(--muted);line-height:1.5;margin-bottom:8px">
          Досье уходят в чат <b>порциями</b> с кнопками вердикта (жмёт инициатор). Начатую здесь чистку
          можно вести и из чата — и наоборот. Чат не блокируется; если задан ранг письма при чистке —
          сообщения ниже ранга бот удаляет сам.
        </div>
        <div id="purge-panel"><div class="loader">Загрузка...</div></div>
      </div>
      <div id="adm-save-status" style="font-size:11px;color:var(--muted);text-align:center;margin-top:6px"></div>`;
    el('adm-settings')._settings=s;
    loadPurgePanel();
  }).catch(e=>{el('adm-settings').innerHTML=`<div class="err">${e}</div>`;});
}
// ── Чистка 2.0 (admin_audit B4): сессия видна и управляема с сайта ────────────
function loadPurgePanel() {
  const box=el('purge-panel'); if(!box||!_adminChatId) return;
  api(`/admin/${_adminChatId}/purge/status`).then(st=>{
    if(!st.active){
      box.innerHTML=`
        <div style="display:flex;gap:6px;margin:0 0 6px">
          <input id="purge-start" type="date" class="num-input" style="flex:1;margin:0" title="Начало периода"/>
          <input id="purge-end" type="date" class="num-input" style="flex:1;margin:0" title="Конец периода"/>
          <input id="purge-norm" type="number" class="num-input" style="width:80px;margin:0" placeholder="Норма" value="50" min="1"/>
        </div>
        <div style="font-size:10px;color:var(--muted);margin-bottom:6px">Пусто = последние 7 дней, норма 50.</div>
        <button class="btn btn-gold btn-full" onclick="doPurgeStart()">📋 Начать чистку</button>`;
      return;
    }
    const c=st.counts||{}, s=st.session||{};
    const vLabel={warn:'⚠️',kick:'👢',ban:'🔨',skip:'🕊'};
    const rows=(st.targets||[]).map(t=>{
      const name=esc(t.username||('ID '+t.user_id));
      const done=t.verdict?`<span style="font-size:14px">${vLabel[t.verdict]||t.verdict}</span>`:
        `<span style="display:flex;gap:6px">
          <button class="btn btn-sm btn-ghost" style="padding:6px 10px" title="Варн" aria-label="Варн" onclick="purgeVerdict(${t.user_id},'warn')">⚠️</button>
          <button class="btn btn-sm btn-ghost" style="padding:6px 10px" title="Кик" aria-label="Кик" onclick="purgeVerdict(${t.user_id},'kick')">👢</button>
          <button class="btn btn-sm btn-ghost" style="padding:6px 10px;color:var(--red)" title="Бан" aria-label="Бан" onclick="purgeVerdict(${t.user_id},'ban')">🔨</button>
          <button class="btn btn-sm btn-ghost" style="padding:6px 10px" title="Пропустить" aria-label="Пропустить" onclick="purgeVerdict(${t.user_id},'skip')">🕊</button>
        </span>`;
      return `<div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid var(--dim);font-size:11px">
        <span style="flex:1">${t.dossier_sent?'📨':'⏳'} ${name} <span style="color:var(--muted)">(${t.msg_count} msg · ${t.warns}⚠️)</span></span>${done}
      </div>`;
    }).join('');
    box.innerHTML=`
      <div style="font-size:12px;color:var(--gold2);margin-bottom:4px">Сессия #${s.id} · норма ${s.norm} · ${esc(s.date_from)} — ${esc(s.date_to)}</div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:6px">Досье: ${c.sent}/${c.total} · Вердиктов: ${c.decided}/${c.total} (⚠️${c.warned} 👢${c.kicked} 🔨${c.banned} 🕊${c.skipped})</div>
      <div style="max-height:260px;overflow:auto;margin-bottom:8px">${rows||'<i style="font-size:11px;color:var(--muted)">Нарушителей нет</i>'}</div>
      ${c.sent<c.total?`<button class="btn btn-teal btn-full" style="margin-bottom:6px" onclick="purgeDossiers()">📨 Выслать досье в чат (ещё ${c.total-c.sent})</button>`:''}
      <button class="btn btn-red btn-full" onclick="purgeFinish()">✅ Завершить чистку</button>`;
  }).catch(e=>{box.innerHTML=`<div class="err">${e}</div>`;});
}
function doPurgeStart() {
  const sd=el('purge-start')?.value||null, ed=el('purge-end')?.value||null;
  const norm=parseInt(el('purge-norm')?.value||'50')||50;
  OM('🧹 Начать чистку?',
    `<div style="text-align:center;padding:12px 0;color:var(--muted)">Бот соберёт активность, пришлёт сводку в чат и первую порцию досье с кнопками.<div style="font-size:11px;margin-top:6px">Период: ${sd||'−7 дней'} — ${ed||'сегодня'} · Норма: ${norm}</div></div>`,
    [{l:'Да, начать',c:'btn-gold',f:`_execPurgeStart(${JSON.stringify(sd)},${JSON.stringify(ed)},${norm})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execPurgeStart(sd, ed, norm) {
  api(`/admin/${_adminChatId}/purge/start`,{method:'POST',body:JSON.stringify({start_date:sd,end_date:ed,norm})})
    .then(r=>{toast(`📋 Чистка #${r.session_id}: ❌${r.failed} нарушителей, досье выслано ${r.sent}`);CM();loadPurgePanel();})
    .catch(e=>{toast(e,false);CM();});
}
function purgeDossiers() {
  api(`/admin/${_adminChatId}/purge/dossiers`,{method:'POST'})
    .then(r=>{toast(`📨 Выслано ${r.sent}, осталось ${r.remaining}`);loadPurgePanel();})
    .catch(e=>toast(e,false));
}
function purgeVerdict(uid, action, confirmed) {
  // UX_AUDIT С13: бан — самый тяжёлый вердикт, промах пальцем не должен его выносить
  if(action==='ban' && !confirmed){
    OM('🔨 Бан по итогам чистки?',
      '<div style="padding:8px 0;color:var(--muted);font-size:12px;line-height:1.5">Игрок будет забанен в чате. Это серьёзнее варна и кика — проверь, что палец не промахнулся.</div>',
      [{l:'🔨 Да, бан',c:'btn-red',f:`CM();purgeVerdict(${uid},'ban',1)`},
       {l:'Отмена',c:'btn-ghost',f:'CM()'}]);
    return;
  }
  api(`/admin/${_adminChatId}/purge/verdict`,{method:'POST',body:JSON.stringify({user_id:uid,action})})
    .then(()=>{toast('Вердикт записан');loadPurgePanel();})
    .catch(e=>toast(e,false));
}
function purgeFinish() {
  OM('✅ Завершить чистку?','<div style="padding:10px 0;color:var(--muted)">Сессия закроется, режим чистки снимется. Невынесенные вердикты останутся без действия.</div>',
    [{l:'Завершить',c:'btn-red',f:'_purgeFinishGo()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _purgeFinishGo() {
  CM();
  api(`/admin/${_adminChatId}/purge/finish`,{method:'POST'})
    .then(()=>{toast('✅ Чистка завершена');loadPurgePanel();})
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
              'rank_shield','rank_immune','rank_marriage','rank_give','purge_min_rank',
              'purge_action_rank','rank_chat_lock',
              'notif_auction','notif_gacha','notif_expeditions','notif_quests'];
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
      <div>
        ${d.logs.map(l=>`<div style="padding:7px 2px;border-bottom:1px solid var(--dim);font-size:11px">
          <div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline">
            <span style="font-weight:600">${l.action}</span>
            <span style="font-size:10px;color:var(--muted);white-space:nowrap">${fmtUTC(l.created_at)||'?'}</span>
          </div>
          <div style="margin-top:2px">@${vipName(l.target_name||'ID'+l.user_id, l.target_is_vip)}
            <span style="color:var(--muted)">· выдал @${vipName(l.admin_name||'ID'+l.admin_id, l.admin_is_vip)}</span></div>
          ${l.reason?`<div style="font-size:10px;color:var(--muted);margin-top:2px">${esc(l.reason)}</div>`:''}
        </div>`).join('')}
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
    admin:()=>{_adminChats=null;loadAdmin();}, global:loadGlobal, console:loadConsole
  };
  if(page && loaders[page]) { _loaded.delete(page); loaders[page](); toast('🔄 Обновлено!'); }
}

// ── Global Moderation (Block 7) ──────────────────────────────────────────────────
let _glbTab='chats', _glbChatsList=null, _glbChatId=0, _glbChatTitle='';
let _glbMembersPage=1, _glbMembersSearch='', _glbMembersSort='messages', _glbSearchTimer=null;
let _glbSanctionsType='', _glbLogPage=1, _glbAppealsStatus='pending', _glbSanctionTarget=null;
const _SANCTION_LABELS={warn:'⚠️ Варн', restrict:'🔇 Ограничение', ban:'🚫 Бан'};

function esc(s) { return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── БЛОК 21.2: эффективные права актёра (/admin/global/my-permissions) ─────────
// Вкладки и кнопки строятся по правам, а не по порогам ранга. Реестр прав —
// core/admin_permissions.py; настройка — вкладка «Штат» (только Разработчик).
let _gPerms=null, _gRank=0, _gCounts=null, _gPermsPromise=null;
function gp(k){ return !!(_gPerms && _gPerms.has(k)); }
function gpAny(list){ return !!(_gPerms && list.some(k=>_gPerms.has(k))); }
const _CONSOLE_PERMS=['console_overview','flags_manage','modules_manage','dossier_view',
  'user_search','economy_balance','economy_items','economy_vip','log_admin_view',
  'bp_manage','promo_manage','broadcast_send','sql_run','metrics_view','themes_manage'];
function loadMyPerms(force){
  if(_gPerms && !force) return Promise.resolve();
  if(_gPermsPromise) return _gPermsPromise;
  _gPermsPromise=api('/admin/global/my-permissions').then(d=>{
    _gPerms=new Set(d.perms||[]); _gRank=d.rank||0; _gCounts=d.counts||{}; _gPermsPromise=null;
    _updateMoreCard();   // W4.3: бейдж ⏳ на карточке «Управление»
  }).catch(()=>{ _gPerms=new Set(); _gRank=0; _gCounts={}; _gPermsPromise=null; });
  return _gPermsPromise;
}
function _applyGlobalTabPerms(){
  const show=(sel,ok)=>{ const b=document.querySelector(sel); if(b) b.style.display=ok?'':'none'; };
  show(`#pg-global .tb[onclick*="'chats'"]`, gp('members_view'));
  show(`#pg-global .tb[onclick*="'sanctions'"]`, gp('sanctions_view'));
  show(`#pg-global .tb[onclick*="'log'"]`, gp('log_view'));
  show(`#pg-global .tb[onclick*="'appeals'"]`, gp('appeals_view'));
  const tr=el('glb-tab-ranks'); if(tr) tr.style.display=gp('staff_manage')?'':'none';
  // W4.3: живые счётчики прямо в вкладках
  const ta=el('glb-tab-appeals');
  if(ta){ const n=(_gCounts||{}).appeals_pending||0; ta.textContent=n?`📨 Апелляции (${n})`:'📨 Апелляции'; }
  const ts=el('glb-tab-sanctions');
  if(ts){ const n=(_gCounts||{}).sanctions_active||0; ts.textContent=n?`🚫 Санкции (${n})`:'🚫 Санкции'; }
}
function _actorSanctionPerms(targetType) {
  const t=targetType||'user';
  return {warn:gp('sanction_warn_'+t), restrict:gp('sanction_restrict_'+t), ban:gp('sanction_ban_'+t)};
}

function loadGlobal() {
  loadMyPerms().then(()=>{
    _applyGlobalTabPerms();
    // Если текущая вкладка недоступна (хелпер с урезанными правами) — первая разрешённая;
    // без единого права модерации, но с консольными — сразу в Консоль (W4.1).
    const need={chats:'members_view',sanctions:'sanctions_view',log:'log_view',appeals:'appeals_view',ranks:'staff_manage'};
    if(need[_glbTab] && !gp(need[_glbTab])){
      if(gp('members_view')) _glbTab='chats';
      else if(gp('sanctions_view')) _glbTab='sanctions';
      else if(gp('appeals_view')) _glbTab='appeals';
      else if(gp('log_view')) _glbTab='log';
      else if(gpAny(_CONSOLE_PERMS)){ switchPage('console'); return; }
      else { el('glb-chats').innerHTML='<div class="card" style="text-align:center;padding:20px;color:var(--muted)">Нет прав глобальной модерации.</div>'; return; }
    }
    swGlobal(_glbTab, document.querySelector(`#pg-global .tb[onclick*="'${_glbTab}'"]`));
  });
}
function swGlobal(tab, btn) {
  if(!_gPerms){ loadMyPerms().then(()=>swGlobal(tab,btn)); return; }
  _glbTab=tab;
  document.querySelectorAll('#pg-global .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  ['chats','sanctions','log','appeals','ranks'].forEach(t=>{const d=el('glb-'+t); if(d) d.style.display=t===tab?'':'none';});
  if(tab==='chats') loadGlobalChats();
  else if(tab==='sanctions') loadGlobalSanctions();
  else if(tab==='log') { _glbLogPage=1; loadGlobalLog(); }
  else if(tab==='appeals') loadGlobalAppeals();
  else if(tab==='ranks') loadGlobalRanksTab();
}

// 1. Все чаты — БЛОК 21.2 W1.1: с правом chats_view_all видны ВСЕ чаты бота;
// поиск/сортировка на клиенте, бейджи: 👻 не состою · 🚫 санкция чата · ⚠️ варны.
let _glbChatQ='', _glbChatSort='title', _glbViewAll=false;
function loadGlobalChats() {
  el('glb-chats').innerHTML='<div class="loader">Загрузка...</div>';
  api('/admin/global/chats').then(d=>{
    _glbChatsList=d.chats||[];
    _glbViewAll=!!d.view_all;
    if(!_glbChatsList.length){
      el('glb-chats').innerHTML='<div class="empty-state"><div class="es-icon">💬</div><div class="es-title">Нет групп</div><div class="es-sub">Показываются только группы, в которых вы состоите</div></div>';
      return;
    }
    el('glb-chats').innerHTML=`
      <div style="display:flex;gap:6px;margin-bottom:8px">
        <input id="glb-chat-q" type="text" class="num-input" style="flex:1;margin:0" placeholder="🔎 Поиск чата" value="${esc(_glbChatQ)}" oninput="_glbChatQ=this.value;_renderGlobalChatsList()"/>
        <select class="num-input" style="width:118px;margin:0" onchange="_glbChatSort=this.value;_renderGlobalChatsList()">
          <option value="title" ${_glbChatSort==='title'?'selected':''}>По имени</option>
          <option value="members" ${_glbChatSort==='members'?'selected':''}>По людям</option>
          <option value="warns" ${_glbChatSort==='warns'?'selected':''}>По варнам</option>
        </select>
      </div>
      <div class="card">
        <div class="card-title" id="glb-chats-title"></div>
        <div id="glb-chats-list"></div>
      </div>`;
    _renderGlobalChatsList();
  }).catch(e=>{el('glb-chats').innerHTML=`<div class="err">${e}</div>`;});
}
function _renderGlobalChatsList() {
  const box=el('glb-chats-list'); if(!box) return;
  const q=(_glbChatQ||'').trim().toLowerCase();
  let rows=(_glbChatsList||[]).filter(c=>!q||(c.chat_title||'').toLowerCase().includes(q));
  if(_glbChatSort==='members') rows=rows.slice().sort((a,b)=>(b.member_count||0)-(a.member_count||0));
  else if(_glbChatSort==='warns') rows=rows.slice().sort((a,b)=>(b.warned_count||0)-(a.warned_count||0));
  const t=el('glb-chats-title');
  if(t) t.textContent=`${_glbViewAll?'🌐 Все чаты бота':'💬 Мои группы'} (${rows.length})`;
  const perms=_actorSanctionPerms('chat');
  const roleIcon = c => c.role==='admin' ? '🛡' : c.role==='main' ? '🏠' : '💬';
  box.innerHTML=rows.map(c=>`<div style="padding:8px 0;border-bottom:1px solid var(--border2)">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
        <span style="cursor:pointer;font-weight:600;color:var(--bright);font-size:12.5px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" onclick="openGlobalChatMembers(${c.chat_id})">${roleIcon(c)} ${esc(c.chat_title)}${c.chat_sanctioned?' <span style="color:var(--red)">🚫</span>':''}</span>
        <span style="display:flex;align-items:center;gap:6px;flex:none">
          ${(c.warned_count||0)>0?`<span style="font-size:10px;color:var(--gold)">⚠️${c.warned_count}</span>`:''}
          <span style="cursor:pointer;font-size:11px;color:var(--muted)" onclick="openGlobalChatMembers(${c.chat_id})">${c.member_count} 👤 ›</span>
          ${(perms.warn||perms.restrict||perms.ban)?`<button class="btn btn-sm btn-ghost" style="padding:2px 6px;font-size:10px" onclick="openGlobalChatSanction(${c.chat_id})">⚡</button>`:''}
        </span>
      </div>
      ${c.linked_title||c.is_member===false?`<div style="font-size:9.5px;color:var(--muted);margin-top:2px">
        ${c.is_member===false?'<span style="opacity:.8">👻 не состою</span>':''}
        ${c.linked_title?(c.role==='admin'?`🛡 админ-чат для «${esc(c.linked_title)}»`:`🛡 админ-чат: «${esc(c.linked_title)}»`):''}
      </div>`:''}
    </div>`).join('')||'<div style="font-size:11px;color:var(--muted);padding:8px 0">Ничего не найдено.</div>';
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
    <div class="card" style="padding:8px 14px">
      ${d.members.map(m=>`<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border2)">
        <span style="flex:1;min-width:0">
          <span style="font-weight:600;font-size:12px;color:var(--bright);${gp('dossier_view')?'cursor:pointer;text-decoration:underline':''}" ${gp('dossier_view')?`onclick="openPlayerCenter(${m.user_tg_id})"`:''}>@${vipName(m.user_tg_username||'ID'+m.user_tg_id, m.is_vip)}</span>
          <span style="font-size:10px;color:var(--muted)"> · ур.${m.user_level||1} · ${esc(m.global_rank_name||'')}</span><br>
          <span style="font-size:10px;color:var(--muted)">ID ${m.user_tg_id} · ${m.user_messages_count_all_time||0} сообщ. · 📅 ${m.joined_at?fmtUTC(m.joined_at):'—'} · 🕓 ${m.last_message_at?fmtUTC(m.last_message_at):'—'}</span>
        </span>
        ${(m.can_warn||m.can_restrict||m.can_ban)?`<button class="btn btn-sm btn-ghost" style="padding:4px 8px;flex:none" onclick='openGlobalSanctionForm("user",${m.user_tg_id},${JSON.stringify(m.user_tg_username||'ID'+m.user_tg_id)},${JSON.stringify({warn:m.can_warn,restrict:m.can_restrict,ban:m.can_ban})})'>⚡</button>`:''}
      </div>`).join('')}
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

// Форма выдачи санкции — W3.3: причина обязательна, фото-доказательства с сайта,
// «Выдать» неактивна до выбора типа, выбранный тип подсвечен заливкой.
let _gstPhotos=[];   // [{name, data(base64)}] — грузятся при отправке
function openGlobalSanctionForm(targetType, targetId, targetName, perms) {
  perms = perms || _actorSanctionPerms(targetType);
  if(!targetName) targetName = (targetType==='chat'?'Чат ID':'ID')+targetId;
  _glbSanctionTarget={type:targetType, id:targetId};
  _gstPhotos=[];
  const durations=[[0,'Бессрочно'],[1,'1 день'],[3,'3 дня'],[7,'7 дней'],[30,'30 дней']];
  OM(`⚡ ${targetName}`,`
    <div style="display:flex;gap:6px;margin-bottom:8px">
      <button class="btn btn-sm ${perms.warn?'btn-ghost':''}" ${perms.warn?'':'disabled'} onclick="selectGlobalSanctionType('warn')" id="gst-warn">⚠️ Варн</button>
      <button class="btn btn-sm ${perms.restrict?'btn-ghost':''}" ${perms.restrict?'':'disabled'} onclick="selectGlobalSanctionType('restrict')" id="gst-restrict">🔇 Огранич.</button>
      <button class="btn btn-sm ${perms.ban?'btn-ghost':''}" ${perms.ban?'':'disabled'} onclick="selectGlobalSanctionType('ban')" id="gst-ban">🚫 Бан</button>
    </div>
    <div id="gst-duration" style="display:none;margin-bottom:8px">
      <select id="gst-dur-sel" class="num-input" style="margin:0">
        ${durations.map(([dd,l])=>`<option value="${dd}">${l}</option>`).join('')}
      </select>
    </div>
    <textarea id="gst-reason" class="num-input" style="margin:0 0 6px;min-height:90px;resize:vertical;line-height:1.4" placeholder="Причина — ОБЯЗАТЕЛЬНА (до 9999 символов, можно со ссылками)" maxlength="9999"></textarea>
    <div style="font-size:10px;color:var(--muted);margin-bottom:4px">Кого уведомить о санкции:</div>
    <select id="gst-notify" class="num-input" style="margin:0 0 6px">
      <option value="all">📣 Все чаты игрока + ЛС</option>
      <option value="none">🔕 Только ЛС нарушителю (без чатов)</option>
    </select>
    <input type="file" id="gst-photo-input" accept="image/*" multiple style="display:none" onchange="_gstAddPhotos(this.files)"/>
    <button class="btn btn-ghost btn-sm btn-full" style="margin-bottom:6px" onclick="el('gst-photo-input').click()" id="gst-photo-btn">📎 Прикрепить фото-доказательства (0/4)</button>
    <button class="btn btn-gold btn-full" id="gst-submit" disabled style="margin-bottom:4px" onclick="doIssueGlobalSanction()">Выдать санкцию</button>
    <div style="font-size:10px;color:var(--muted)">Инструкция по апелляции уходит нарушителю в ЛС всегда. Копии фото останутся у вас в ЛС бота.</div>
  `,[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
  el('modal')._sanctionType=null;
}
function selectGlobalSanctionType(type) {
  el('modal')._sanctionType=type;
  // Выбранный тип — заливкой (btn-gold), остальные — ghost; «Выдать» оживает.
  ['warn','restrict','ban'].forEach(t=>{
    const b=el('gst-'+t); if(!b||b.disabled) return;
    b.classList.toggle('btn-gold', t===type);
    b.classList.toggle('btn-ghost', t!==type);
  });
  el('gst-duration').style.display=(type==='restrict'||type==='ban')?'':'none';
  const s=el('gst-submit'); if(s) s.disabled=false;
}
function _gstAddPhotos(files) {
  const room=4-_gstPhotos.length;
  Array.from(files||[]).slice(0,room).forEach(f=>{
    if(f.size>5*1024*1024) return toast(`«${f.name}» больше 5 МБ — пропущено`,false);
    const rd=new FileReader();
    rd.onload=()=>{ _gstPhotos.push({name:f.name, data:String(rd.result)}); _gstPhotoBtnUpd(); };
    rd.readAsDataURL(f);
  });
}
function _gstPhotoBtnUpd() {
  const b=el('gst-photo-btn');
  if(b) b.textContent=`📎 Прикрепить фото-доказательства (${_gstPhotos.length}/4)`;
}
async function _gstUploadPhotos() {
  const ids=[];
  for(const p of _gstPhotos){
    const r=await api('/admin/global/upload-photo',{method:'POST',body:JSON.stringify({data:p.data,filename:p.name})});
    if(r&&r.file_id) ids.push(r.file_id);
  }
  return ids;
}
async function doIssueGlobalSanction() {
  const type=el('modal')._sanctionType;
  if(!type) return toast('Выберите тип санкции',false);
  const reason=el('gst-reason')?.value.trim();
  if(!reason||reason.length<3) return toast('Причина обязательна (минимум 3 символа)',false);
  const durSel=el('gst-dur-sel');
  const days=durSel&&durSel.value!=='0'?parseInt(durSel.value):null;
  const notify=el('gst-notify')?.value||'all';
  const s=el('gst-submit'); if(s){ s.disabled=true; s.textContent=_gstPhotos.length?'📎 Загружаю фото…':'Выдаю…'; }
  let photo_ids=[];
  try { photo_ids=await _gstUploadPhotos(); }
  catch(e){ if(s){s.disabled=false;s.textContent='Выдать санкцию';} return toast('Фото не загрузилось: '+e,false); }
  api('/admin/global/sanctions',{method:'POST',body:JSON.stringify({
    target_type:_glbSanctionTarget.type, target_id:_glbSanctionTarget.id,
    sanction_type:type, reason, duration_days:days, notify, photo_ids,
  })}).then(r=>{
    const dm=r.dm_instruction_sent?'📨 инструкция в ЛС доставлена':'⚠️ ЛС закрыты';
    toast(`${r.message||'✅ Готово'}${r.chats_notified?` · уведомлено чатов: ${r.chats_notified}`:''} · ${dm}`); CM();
    if(_activePage==='console'&&_devUserId) devLookupUser();          // Центр игрока: обновить досье
    else if(_glbTab==='chats'&&_glbChatId) loadGlobalChatMembers();
    else if(_glbTab==='sanctions') loadGlobalSanctions();
    loadMyPerms(true).then(_applyGlobalTabPerms);                     // счётчики в вкладках/бейджах
  }).catch(e=>{
    const s2=el('gst-submit'); if(s2){ s2.disabled=false; s2.textContent='Выдать санкцию'; }
    toast(e,false);
  });
}

// ── БЛОК 21.2: «➕ Выдать санкцию» — поиск цели без захода в чат (боль D1) ──────
let _issTargetType='user', _issTimer=null;
function openIssueSanctionSearch() {
  OM('➕ Выдать санкцию', `
    <div class="tabs tab-inner" style="margin-bottom:8px">
      <button class="tb active" id="iss-t-user" onclick="_issSwitch('user')">👤 Игроку</button>
      <button class="tb" id="iss-t-chat" onclick="_issSwitch('chat')">💬 Чату</button>
    </div>
    <div id="iss-user-box">
      ${gp('user_search')
        ?`<input id="iss-q" type="text" class="num-input" style="margin:0 0 6px" placeholder="🔍 ник / ID (от 2 символов)" oninput="_issSearchDebounced(this.value)"/>`
        :`<input id="iss-q" type="number" class="num-input" style="margin:0 0 6px" placeholder="ID игрока" oninput="_issIdOnly(this.value)"/>`}
      <div id="iss-res" style="max-height:40vh;overflow-y:auto"></div>
    </div>
    <div id="iss-chat-box" style="display:none">
      <input id="iss-chat-q" type="text" class="num-input" style="margin:0 0 6px" placeholder="🔎 Поиск чата" oninput="_issFillChats(this.value)"/>
      <div id="iss-chat-list" style="max-height:40vh;overflow-y:auto"><div class="loader">Загрузка...</div></div>
    </div>
  `,[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
  _issTargetType='user';
  if(_glbChatsList) _issFillChats('');
  else api('/admin/global/chats').then(d=>{_glbChatsList=d.chats||[];_glbViewAll=!!d.view_all;_issFillChats('');}).catch(()=>{});
}
function _issSwitch(t){
  _issTargetType=t;
  el('iss-t-user')?.classList.toggle('active', t==='user');
  el('iss-t-chat')?.classList.toggle('active', t==='chat');
  const ub=el('iss-user-box'), cb=el('iss-chat-box');
  if(ub) ub.style.display=t==='user'?'':'none';
  if(cb) cb.style.display=t==='chat'?'':'none';
}
function _issSearchDebounced(v){ clearTimeout(_issTimer); _issTimer=setTimeout(()=>_issSearch(v),300); }
function _issSearch(v){
  const box=el('iss-res'); if(!box) return;
  v=(v||'').trim();
  if(v.length<2){ box.innerHTML=''; return; }
  box.innerHTML='<div class="loader">Поиск...</div>';
  api('/admin/dev/user-search?q='+encodeURIComponent(v)).then(d=>{
    const rows=d.results||[];
    box.innerHTML=rows.map(u=>`<div class="dev-cat-item" onclick='_issPick(${u.user_tg_id},${JSON.stringify('@'+(u.user_tg_username||('ID'+u.user_tg_id)))})'>
        <span>${u.has_sanction?'🚫 ':''}${u.is_vip?'👑 ':''}@${esc(u.user_tg_username||('ID'+u.user_tg_id))}${u.nickname?` <span style="color:var(--muted)">· ${esc(u.nickname)}</span>`:''}</span>
        <span style="color:var(--muted);font-size:9px;font-family:monospace">${u.user_tg_id}</span>
      </div>`).join('')||'<div style="font-size:11px;color:var(--muted);padding:8px">Никого не нашли — попробуйте ID.</div>';
  }).catch(e=>{box.innerHTML=`<div class="err">${e}</div>`;});
}
function _issIdOnly(v){
  const box=el('iss-res'); if(!box) return;
  const id=parseInt(v||'0');
  box.innerHTML=id?`<button class="btn btn-ghost btn-full" onclick="_issPick(${id},'ID${id}')">⚡ Выдать санкцию ID${id}</button>`:'';
}
function _issPick(id, name){
  CM();
  openGlobalSanctionForm('user', id, name, _actorSanctionPerms('user'));
}
function _issFillChats(q){
  const box=el('iss-chat-list'); if(!box) return;
  q=(q||'').trim().toLowerCase();
  const rows=(_glbChatsList||[]).filter(c=>!q||(c.chat_title||'').toLowerCase().includes(q));
  box.innerHTML=rows.map(c=>`<div class="dev-cat-item" onclick='_issPickChat(${c.chat_id},${JSON.stringify(c.chat_title||String(c.chat_id))})'>
      <span>${c.role==='admin'?'🛡':'💬'} ${esc(c.chat_title)}${c.chat_sanctioned?' <span style="color:var(--red)">🚫</span>':''}</span>
      <span style="color:var(--muted);font-size:9px">${c.member_count||0} 👤</span>
    </div>`).join('')||'<div style="font-size:11px;color:var(--muted);padding:8px">Чатов не найдено.</div>';
}
function _issPickChat(id, title){
  CM();
  openGlobalSanctionForm('chat', id, title, _actorSanctionPerms('chat'));
}

// 2. Активные санкции — W3.2: компактные строки, клиентский поиск и фильтры со
// счётчиками (данные грузятся один раз без type, фильтруем на клиенте).
const _ALL_SANCTION_PERMS=['sanction_warn_user','sanction_restrict_user','sanction_ban_user',
  'sanction_warn_chat','sanction_restrict_chat','sanction_ban_chat'];
let _glbSancAll=null, _glbSancQ='';
function loadGlobalSanctions() {
  el('glb-sanctions').innerHTML='<div class="loader">Загрузка...</div>';
  api('/admin/global/sanctions?active_only=true').then(d=>{
    _glbSancAll=d.sanctions||[];
    el('glb-sanctions').innerHTML=`
      ${gpAny(_ALL_SANCTION_PERMS)?`<button class="btn btn-gold btn-full" style="margin-bottom:8px" onclick="openIssueSanctionSearch()">➕ Выдать санкцию</button>`:''}
      <input type="text" class="num-input" style="margin:0 0 8px" placeholder="🔎 Поиск: ник / ID / причина" value="${esc(_glbSancQ)}" oninput="_glbSancQ=this.value;_renderGlobalSanctions()"/>
      <div class="tabs" id="glb-sanc-filters" style="margin-bottom:8px"></div>
      <div id="glb-sanc-list"></div>`;
    _renderGlobalSanctions();
  }).catch(e=>{el('glb-sanctions').innerHTML=`<div class="err">${e}</div>`;});
}
function _renderGlobalSanctions() {
  const all=_glbSancAll||[];
  const n=t=>all.filter(s=>s.sanction_type===t).length;
  const fl=el('glb-sanc-filters');
  if(fl) fl.innerHTML=`
    <button class="tb ${!_glbSanctionsType?'active':''}" onclick="filterGlobalSanctions('')">Все (${all.length})</button>
    <button class="tb ${_glbSanctionsType==='warn'?'active':''}" onclick="filterGlobalSanctions('warn')">⚠️ ${n('warn')}</button>
    <button class="tb ${_glbSanctionsType==='restrict'?'active':''}" onclick="filterGlobalSanctions('restrict')">🔇 ${n('restrict')}</button>
    <button class="tb ${_glbSanctionsType==='ban'?'active':''}" onclick="filterGlobalSanctions('ban')">🚫 ${n('ban')}</button>`;
  const q=(_glbSancQ||'').trim().toLowerCase();
  const rows=all.filter(s=>(!_glbSanctionsType||s.sanction_type===_glbSanctionsType)
    &&(!q||(s.target_name||'').toLowerCase().includes(q)||(s.reason||'').toLowerCase().includes(q)
       ||String(s.target_id).includes(q)));
  const icons={warn:'⚠️',restrict:'🔇',ban:'🚫'};
  el('glb-sanc-list').innerHTML=rows.length?`<div class="card" style="padding:8px 14px">${rows.map(s=>{
    const name=(s.target_type==='user'&&gp('dossier_view'))
      ?`<span style="cursor:pointer;text-decoration:underline;font-weight:600;color:var(--bright)" onclick="openPlayerCenter(${s.target_id})">${esc(s.target_name)}</span>`
      :`<span style="font-weight:600;color:var(--bright)">${s.target_type==='chat'?'💬 ':''}${esc(s.target_name)}</span>`;
    return `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border2)">
      <span style="flex:1;min-width:0;font-size:11.5px">${icons[s.sanction_type]||'❔'} ${name}
        <span style="color:var(--muted)">· ${esc((s.reason||'—').slice(0,48))}</span><br>
        <span style="font-size:10px;color:var(--muted)">${s.expires_at?('до '+fmtUTC(s.expires_at)):'бессрочно'} · выдал ${esc(s.issued_by_name||'—')}</span>
      </span>
      <span style="display:flex;gap:4px;flex:none">
        <button class="btn btn-sm btn-ghost" style="padding:3px 7px" title="Снять" onclick="doRevokeGlobalSanction(${s.id})">✅</button>
        ${s.target_type==='user'?`<button class="btn btn-sm btn-ghost" style="padding:3px 7px" title="История дел" onclick="openUserCase(${s.target_id})">📁</button>`:''}
        ${s.sanction_type!=='warn'?`<button class="btn btn-sm btn-ghost" style="padding:3px 7px" title="Изменить срок" onclick='openGlobalSanctionForm(${JSON.stringify(s.target_type)},${s.target_id},null,_actorSanctionPerms(${JSON.stringify(s.target_type)}))'>✏️</button>`:''}
      </span>
    </div>`;
  }).join('')}</div>`
  :'<div class="card" style="text-align:center;padding:20px;color:var(--muted)">'+(q||_glbSanctionsType?'Ничего не найдено по фильтру':'Нет активных санкций')+'</div>';
}
function filterGlobalSanctions(type) { _glbSanctionsType=type; _renderGlobalSanctions(); }
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
              <td style="font-size:11px">${(s.target_type==='user'&&gp('dossier_view'))?`<span style="cursor:pointer;text-decoration:underline" onclick="openPlayerCenter(${s.target_id})">👤 ${esc(s.target_name)}</span>`:`${s.target_type==='chat'?'💬':'👤'} ${esc(s.target_name)}`}</td>
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

// 4. Апелляции — W3.2 (D4): компактные строки, поиск, счётчики в фильтрах,
// порции по 30 («Показать ещё»). Полный текст и вложения — в диалоге (💬).
let _glbAppealsAll=null, _glbAppealsCounts={}, _glbAppealQ='', _glbAppealsShown=30;
function loadGlobalAppeals() {
  el('glb-appeals').innerHTML='<div class="loader">Загрузка...</div>';
  api(`/admin/global/appeals?status=${_glbAppealsStatus}`).then(d=>{
    _glbAppealsAll=d.appeals||[]; _glbAppealsCounts=d.counts||{}; _glbAppealsShown=30;
    el('glb-appeals').innerHTML=`
      <div class="tabs tabs-scroll" style="margin-bottom:8px">
        <button class="tb ${_glbAppealsStatus==='pending'?'active':''}" onclick="filterGlobalAppeals('pending')">⏳ Новые (${_glbAppealsCounts.pending||0})</button>
        <button class="tb ${_glbAppealsStatus==='accepted'?'active':''}" onclick="filterGlobalAppeals('accepted')">✅ Принятые (${_glbAppealsCounts.accepted||0})</button>
        <button class="tb ${_glbAppealsStatus==='rejected'?'active':''}" onclick="filterGlobalAppeals('rejected')">❌ Отклонённые (${_glbAppealsCounts.rejected||0})</button>
        <button class="tb ${_glbAppealsStatus==='closed'?'active':''}" onclick="filterGlobalAppeals('closed')">📪 Закрытые (${_glbAppealsCounts.closed||0})</button>
      </div>
      <input type="text" class="num-input" style="margin:0 0 8px" placeholder="🔎 Поиск: ник / ID / текст апелляции" value="${esc(_glbAppealQ)}" oninput="_glbAppealQ=this.value;_glbAppealsShown=30;_renderGlobalAppeals()"/>
      <div id="glb-appeals-list"></div>`;
    _renderGlobalAppeals();
  }).catch(e=>{el('glb-appeals').innerHTML=`<div class="err">${e}</div>`;});
}
function _renderGlobalAppeals() {
  const box=el('glb-appeals-list'); if(!box) return;
  const q=(_glbAppealQ||'').trim().toLowerCase();
  const rows=(_glbAppealsAll||[]).filter(a=>!q
    ||(a.user_name||'').toLowerCase().includes(q)
    ||(a.text||'').toLowerCase().includes(q)
    ||String(a.user_id).includes(q));
  const st={pending:'⏳',accepted:'✅',rejected:'❌',closed:'📪'};
  const shown=rows.slice(0,_glbAppealsShown);
  box.innerHTML=(shown.length?`<div class="card" style="padding:8px 14px">${shown.map(a=>{
    const name=gp('dossier_view')
      ?`<span style="cursor:pointer;text-decoration:underline;font-weight:600;color:var(--bright)" onclick="openPlayerCenter(${a.user_id})">${esc(a.user_name)}</span>`
      :`<span style="font-weight:600;color:var(--bright)">${esc(a.user_name)}</span>`;
    return `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border2)">
      <span style="flex:1;min-width:0;font-size:11.5px">${st[a.status]||'❔'} <b>#${a.id}</b> ${name}
        <span style="color:var(--muted)">· ${_SANCTION_LABELS[a.sanction_type]||'?'}${a.sanction_active===false?' (снята)':''} · ${esc((a.text||'').slice(0,44))}</span><br>
        <span style="font-size:10px;color:var(--muted)">${fmtUTC(a.created_at)}${a.status!=='pending'&&a.resolved_by_name?' · решение: '+esc(a.resolved_by_name):''}</span>
      </span>
      <span style="display:flex;gap:4px;flex:none">
        <button class="btn btn-sm btn-teal" style="padding:3px 7px" title="Диалог" onclick="openAppealThread(${a.id})">💬</button>
        ${a.status==='pending'?`<button class="btn btn-sm btn-ghost" style="padding:3px 7px" title="Снять санкцию" onclick="doResolveAppeal(${a.id},'accept')">✅</button>
        <button class="btn btn-sm btn-ghost" style="padding:3px 7px" title="Отклонить" onclick="doResolveAppeal(${a.id},'reject')">❌</button>`:''}
      </span>
    </div>`;}).join('')}</div>`
    :'<div class="card" style="text-align:center;padding:20px;color:var(--muted)">'+(q?'Ничего не найдено':'Нет апелляций')+'</div>')
    +(rows.length>_glbAppealsShown?`<button class="btn btn-ghost btn-full" style="margin-top:8px" onclick="_glbAppealsShown+=30;_renderGlobalAppeals()">⬇ Показать ещё (${rows.length-_glbAppealsShown})</button>`:'');
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
// БЛОК 21.2 (Штат 2.0): список штата с активностью + гибкая матрица прав рангов.
function loadGlobalRanksTab() {
  el('glb-ranks').innerHTML='<div class="loader">Загрузка...</div>';
  Promise.all([api('/admin/global/ranks'), api('/admin/global/permissions')]).then(([sd,sp])=>{
    const staff=sd.staff||[];
    const staffHtml=staff.map(s=>`<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border2)">
      <span style="flex:1;min-width:0;${gp('dossier_view')&&s.global_rank<3?'cursor:pointer':''}" ${gp('dossier_view')&&s.global_rank<3?`onclick="openPlayerCenter(${s.user_tg_id})"`:''}>
        <span style="font-size:12px;font-weight:600;color:var(--bright)">@${esc(s.user_tg_username||('ID'+s.user_tg_id))}</span><br>
        <span style="font-size:10px;color:var(--muted)">${esc(s.rank_name)} · за 30д: ⚡${s.sanctions_30d||0} санкц. · ⚖️${s.appeals_30d||0} апелл.</span>
      </span>
      ${s.global_rank<3?`<select class="num-input" style="width:auto;margin:0;font-size:11px" onchange="doSetGlobalRankFor(${s.user_tg_id},this.value)">
        <option value="1" ${s.global_rank===1?'selected':''}>🛡 Хелпер</option>
        <option value="2" ${s.global_rank===2?'selected':''}>⚔️ Ст. хелпер</option>
        <option value="0">❌ Снять</option>
      </select>`:`<span style="font-size:11px;color:var(--gold2)">🌌</span>`}
    </div>`).join('')||'<div style="font-size:11px;color:var(--muted)">Штат пуст — назначьте первого хелпера ниже.</div>';
    el('glb-ranks').innerHTML=`
      <div class="card"><div class="card-title">👮 Штат (${staff.length})</div>${staffHtml}</div>
      <div class="card">
        <div class="card-title">➕ Назначить ранг</div>
        <input id="glb-rank-uid" type="number" class="num-input" style="margin-bottom:6px" placeholder="ID пользователя (найти: Консоль → 🔍)"/>
        <select id="glb-rank-sel" class="num-input" style="margin-bottom:6px">
          <option value="1">🛡 Хелпер</option>
          <option value="2">⚔️ Старший хелпер</option>
          <option value="0">👤 Снять (Пользователь)</option>
        </select>
        <button class="btn btn-gold btn-full" onclick="doSetGlobalRank()">Сохранить</button>
      </div>
      <div class="card">
        <div class="card-title">🔐 Права рангов</div>
        <div style="font-size:10px;color:var(--muted);margin-bottom:6px">
          Тумблер = у ранга есть право. 🔒 — только Разработчик, не настраивается.
          ↩ у изменённых — вернуть дефолт. Права действуют и на сайте, и на бот-команды «глоб …».
        </div>
        <div style="display:flex;font-size:10px;color:var(--muted);gap:8px;justify-content:flex-end;padding-right:2px">
          <span style="width:52px;text-align:center">🛡 1</span><span style="width:52px;text-align:center">⚔️ 2</span>
        </div>
        <div id="glb-perm-matrix"></div>
      </div>`;
    _renderPermMatrix(sp);
  }).catch(e=>{el('glb-ranks').innerHTML=`<div class="err">${e}</div>`;});
}
function _renderPermMatrix(pd) {
  const box=el('glb-perm-matrix'); if(!box||!pd) return;
  const items=pd.items||[];
  box.innerHTML=(pd.groups||[]).map(g=>{
    const rows=items.filter(i=>i.group===g);
    if(!rows.length) return '';
    return `<div style="font-size:10px;font-weight:700;color:var(--gold2);margin:8px 0 2px;text-transform:uppercase">${esc(g)}</div>`
      + rows.map(i=>{
        const cell=(rank,on,ov)=>i.locked
          ? `<span style="width:52px;text-align:center;font-size:13px;opacity:.6">🔒</span>`
          : `<span style="width:52px;display:inline-flex;align-items:center;justify-content:center;gap:2px">
              <label class="dev-flag-toggle" style="margin:0" title="${esc(i.key)}">
                <input type="checkbox" ${on?'checked':''} onchange="devSetRankPerm(${rank},'${i.key}',this.checked)"/>
                <span class="dev-flag-slider"></span>
              </label>
              ${ov?`<span style="cursor:pointer;font-size:11px;color:var(--gold2)" title="Изменён дефолт — клик вернёт" onclick="devSetRankPerm(${rank},'${i.key}',null)">↩</span>`:''}
            </span>`;
        return `<div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--border2)">
          <span style="flex:1;min-width:0;font-size:11.5px">${esc(i.label)}</span>
          ${cell(1,i.rank1,i.rank1_override)}${cell(2,i.rank2,i.rank2_override)}
        </div>`;
      }).join('');
  }).join('');
}
function devSetRankPerm(rank, key, allowed) {
  api('/admin/global/permissions',{method:'POST',body:JSON.stringify({rank,key,allowed})})
    .then(d=>{toast(allowed===null?'↩ Дефолт восстановлен':'💾 Право обновлено');_renderPermMatrix(d);})
    .catch(e=>{toast(e,false);loadGlobalRanksTab();});
}
function doSetGlobalRankFor(uid, rank) {
  api('/admin/global/ranks',{method:'POST',body:JSON.stringify({user_id:uid,global_rank:parseInt(rank)})})
    .then(r=>{toast(`✅ ${r.rank_name}`);loadGlobalRanksTab();})
    .catch(e=>{toast(e,false);loadGlobalRanksTab();});
}
function doSetGlobalRank() {
  const uid=parseInt(el('glb-rank-uid')?.value||'0');
  const rank=parseInt(el('glb-rank-sel')?.value||'0');
  if(!uid) return toast('Укажите ID пользователя',false);
  api('/admin/global/ranks',{method:'POST',body:JSON.stringify({user_id:uid,global_rank:rank})})
    .then(r=>{toast(`✅ Назначено: ${r.rank_name}`);loadGlobalRanksTab();})
    .catch(e=>toast(e,false));
}


// ── admin_audit B1: диалог апелляции и история дел игрока ─────────────────────
function _appealMsgHtml(m) {
  const who=m.is_staff?'👮 Модерация':'🙋 Игрок';
  const photos=(m.photos||[]).map(fid=>
    `<img src="${BASE}/admin/global/tg-photo/${encodeURIComponent(fid)}" style="max-width:120px;max-height:120px;border-radius:6px;margin:4px 4px 0 0" loading="lazy"/>`).join('');
  return `<div style="margin:6px 0;padding:7px 9px;border-radius:8px;background:${m.is_staff?'var(--dim)':'rgba(80,140,220,.12)'}">
    <div style="font-size:10px;color:var(--muted)">${who} · ${fmtUTC(m.created_at)||''}</div>
    <div style="font-size:12px;white-space:pre-wrap;word-break:break-word">${esc(m.text||'(фото)')}</div>${photos}
  </div>`;
}
function openAppealThread(id) {
  api(`/admin/global/appeals/${id}/thread`).then(d=>{
    const a=d.appeal||{}, s=d.sanction||{};
    const msgs=(d.thread||[]).map(m=>_appealMsgHtml({...m,photos:JSON.parse(m.photos_json||'[]')})).join('')
      ||'<i style="font-size:11px;color:var(--muted)">Сообщений нет</i>';
    const open=a.status==='pending';
    OM(`💬 Апелляция #${id} ${open?'(открыта)':'— '+esc(a.status)}`,
      `<div style="font-size:11px;color:var(--muted)">Санкция #${a.sanction_id}: ${_SANCTION_LABELS[s.sanction_type]||''} · ${esc((s.reason||'').slice(0,120))}</div>
       <div style="max-height:38vh;overflow:auto;margin:6px 0">${msgs}</div>
       ${open?`<textarea id="apl-reply" class="num-input" style="min-height:70px;resize:vertical;margin:0 0 6px" placeholder="Ответ игроку (уйдёт ему в ЛС)…" maxlength="9999"></textarea>`:''}`,
      open?[{l:'💬 Ответить',c:'btn-gold',f:`_appealReplyGo(${id})`},
            {l:'📪 Закрыть дело',c:'btn-red',f:`_appealCloseAsk(${id})`},
            {l:'Выйти',c:'btn-ghost',f:'CM()'}]
          :[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
  }).catch(e=>toast(e,false));
}
function _appealReplyGo(id) {
  const text=el('apl-reply')?.value.trim();
  if(!text) return toast('Введите текст ответа',false);
  api(`/admin/global/appeals/${id}/reply`,{method:'POST',body:JSON.stringify({text})})
    .then(r=>{toast(r.message||'✅ Отправлено');openAppealThread(id);})
    .catch(e=>toast(e,false));
}
function _appealCloseAsk(id) {
  const resolution=el('apl-reply')?.value.trim()||'';
  OM('📪 Закрыть дело?',
    `<div style="padding:8px 0;color:var(--muted);font-size:12px">Диалог закроется, игрок получит финальное сообщение${resolution?' с вашим текстом из поля ответа':''}. Санкция при этом НЕ снимается (для снятия — «✅ Снять санкцию» в списке).</div>`,
    [{l:'Закрыть дело',c:'btn-red',f:`_appealCloseGo(${id},${JSON.stringify(resolution)})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _appealCloseGo(id, resolution) {
  api(`/admin/global/appeals/${id}/close`,{method:'POST',body:JSON.stringify({resolution:resolution||null,status:'closed'})})
    .then(r=>{toast(r.message||'📪 Закрыто');CM();loadGlobalAppeals();})
    .catch(e=>toast(e,false));
}
function openUserCase(uid) {
  api(`/admin/global/user-case/${uid}`).then(d=>{
    const sanc=(d.sanctions||[]).map(s=>{
      const photos=JSON.parse(s.photos_json||'[]').map(fid=>
        `<img src="${BASE}/admin/global/tg-photo/${encodeURIComponent(fid)}" style="max-width:90px;max-height:90px;border-radius:6px;margin:3px 3px 0 0" loading="lazy"/>`).join('');
      const active=!s.revoked_at&&(!s.expires_at||new Date(s.expires_at)>new Date());
      return `<div style="padding:6px 0;border-bottom:1px solid var(--dim)">
        <b>#${s.id}</b> ${_SANCTION_LABELS[s.sanction_type]||s.sanction_type} ${active?'<span style="color:var(--red)">● активна</span>':'<span style="color:var(--muted)">○</span>'}
        <div style="font-size:11px;color:var(--muted)">${esc((s.reason||'—').slice(0,200))}</div>${photos}
      </div>`;
    }).join('')||'<i style="font-size:11px;color:var(--muted)">Санкций не было</i>';
    const apls=(d.appeals||[]).map(a=>
      `<div style="padding:4px 0;font-size:11px">💬 Апелляция #${a.id} — ${esc(a.status)}
        <button class="btn btn-sm btn-ghost" style="padding:1px 8px;margin-left:6px" onclick="openAppealThread(${a.id})">открыть</button>
      </div>`).join('')||'<i style="font-size:11px;color:var(--muted)">Апелляций не было</i>';
    OM(`📁 История дел: ${esc(d.username||uid)}`,
      `<div style="max-height:50vh;overflow:auto">
         <div style="font-size:11px;color:var(--gold2);margin:4px 0">Санкции (${(d.sanctions||[]).length})</div>${sanc}
         <div style="font-size:11px;color:var(--gold2);margin:8px 0 4px">Апелляции (${(d.appeals||[]).length})</div>${apls}
       </div>`,
      [{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
  }).catch(e=>toast(e,false));
}
