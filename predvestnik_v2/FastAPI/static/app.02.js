// ── Profile ───────────────────────────────────────────────────────────────────
// switchPro() defined later with marriage + wallet tabs
function loadProfile() {
  el('pro-main').innerHTML='<div class="sk" style="height:120px;border-radius:var(--r);margin-bottom:8px"></div><div class="sk" style="height:60px;border-radius:var(--r)"></div>';
  return api('/profile/me').then(d=>{
    if(!d || typeof d !== 'object') throw new Error('Неверный формат ответа сервера');
    _cid = _initChatId || d.chats?.[0]?.chat_tg_id || 0;
    if(d.user_id) _uid = d.user_id;
    _profileData = d;
    const cosmetics = typeof window._looksProfileCosmeticsPreview==='function'
      ? window._looksProfileCosmeticsPreview(d.cosmetics||{})
      : (d.cosmetics||{});
    const looksTrial = typeof window._looksProfileTrialSummary==='function'
      ? window._looksProfileTrialSummary()
      : null;
    const lineageStyle = typeof window._looksLineageStyle==='function'
      ? window._looksLineageStyle(cosmetics)
      : '';
    _applySysFlags(d.system_flags);
    checkWhatsNewBadge();   // «Что нового»: золотая точка на 📣, если есть непрочитанное
    _tosGate(d);   // БЛОК22: блок-экран принятия ToS/Privacy для не принявших
    const pets=d.pets.filter(p=>p.placement!=='storage').slice(0,6);
    const uid = d.user_id || _uid;
    // R0: уровень аккаунта (глобальный, экспоненциальная кривая) — с бэка,
    // per-chat user_level больше не игровой уровень (фолбэк для старого кэша ответа)
    const lvl = d.account_level || d.chats?.[0]?.user_level || 1;
    const xpPerLvl = d.xp_to_next || d.xp_per_level || 3000;
    const xpInLvl = (typeof d.xp_into==='number') ? d.xp_into : ((d.chats?.[0]?.user_xp||0) % xpPerLvl);
    const xpPct = Math.min(100, Math.round(xpInLvl/xpPerLvl*100));
    // БЛОК 3: торжественный левел-ап (детект между загрузками) + анимация заливки
    // XP-шкалы один раз за сессию (чтобы авто-релоад каждые 5 мин её не дёргал).
    _checkLevelUp(lvl);
    const animateXp = !_xpAnimated; _xpAnimated = true;
    if (animateXp) setTimeout(() => {
      const f = el('pro-main')?.querySelector('.xp-fill');
      if (f) f.style.width = (f.dataset.pct || 0) + '%';
    }, 40);
    const animateCp = !_cpAnimated; _cpAnimated = true;
    const hasCp = typeof d.combat_power === 'number';
    if (hasCp) setTimeout(() => {
      if (animateCp) _animateCpCount('cp-hero-val', d.combat_power);
      else { const n = el('cp-hero-val'); if (n) n.textContent = fmt(d.combat_power); }
    }, 40);
    const looksEntryLabel=looksTrial?'Продолжить примерку':'Внешний вид';
    const looksEntryMeta=looksTrial?`${looksTrial.count} ${looksTrial.noun} сохранено`:'Примерочная и образы';
    el('pro-main').innerHTML=`
      <div class="hero profile-showcase-card ${cosmetics.profile_bg?cosmetics.profile_bg.css:''}">
        ${cosmetics.card_fx?`<div class="card-fx ${cosmetics.card_fx.css}"></div>`:''}
        <div class="profile-showcase-head">
          <div class="hero-head${lineageStyle?' lineage-link':''}"${lineageStyle?` style="${lineageStyle}"`:''}>
            <div class="ava ${cosmetics.avatar_frame?cosmetics.avatar_frame.css:''} ${cosmetics.avatar_halo?cosmetics.avatar_halo.css:''}" id="pro-ava">${d.is_vip?'👑':'🔮'}</div>
            <div class="profile-copy">
              <div class="pname ${cosmetics.name_glow?cosmetics.name_glow.css:''}">@${vipName(d.username||'Игрок', d.is_vip)}</div>
              <div class="prank">${d.rank}</div>
              ${cosmetics.title?`<div class="ptitle${cosmetics.title_css?' '+cosmetics.title_css:''}">${esc(cosmetics.title)}</div>`:''}
            </div>
          </div>
          <button class="showcase-fitting-button" type="button" onclick="openLooksModal()" aria-label="${looksEntryLabel}">
            <span aria-hidden="true">🎨</span><span>Примерочная</span><span aria-hidden="true">›</span>
          </button>
        </div>

        <div class="profile-showcase-main">
          <button class="character-showcase-area" type="button" onclick="openLooksModal()" aria-label="Открыть текущий образ в примерочной">
            <span class="character-showcase-caption"><strong>${looksEntryLabel}</strong><small>${looksEntryMeta}</small></span>
          </button>
          <aside class="player-data-rail" aria-label="Основные показатели игрока">
            ${hasCp?`<button class="player-rail-item player-rail-item--power" type="button" onclick="showCpBreakdown()">
              <span class="player-rail-kicker">⚡ Сила</span><strong id="cp-hero-val">0</strong><small>Подробнее ›</small>
            </button>`:''}
            <div class="player-rail-item player-rail-item--level">
              <span class="player-rail-kicker">Уровень</span><strong>LV${lvl}</strong>
              <div class="hero-xp">
                <div class="xp-bar"><div class="xp-fill" data-pct="${xpPct}" style="width:${animateXp?0:xpPct}%"></div></div>
                <div class="xp-lbl"><span>${fmt(xpInLvl)}</span><span>${fmt(xpPerLvl)} XP</span></div>
              </div>
            </div>
            <button class="player-rail-item" type="button" onclick="goTo('quests','streak')">
              <span class="player-rail-kicker">🔥 Стрик</span><strong id="pro-stat-streak">${d.streak}</strong><small>дней подряд</small>
            </button>
            <button class="player-rail-item" type="button" onclick="goTo('ach')">
              <span class="player-rail-kicker">🏆 Ачивки</span><strong>${d.achievements}</strong><small>Открыть ›</small>
            </button>
          </aside>
        </div>

        <div class="stats profile-resource-rail" aria-label="Ресурсы игрока">
          <div class="stat clickable" onclick="openExchangeCurrencyModal('buy')"><div>🪙</div><div class="sv" id="pro-stat-mora">${fmt(d.mora)}</div><div class="sl">Мора</div></div>
          <div class="stat clickable" onclick="openExchangeCurrencyModal('sell')"><div>💎</div><div class="sv" id="pro-stat-dia">${fmtF(d.diamonds)}</div><div class="sl">Алмазы</div></div>
          <div class="stat clickable" onclick="${(d.zarniki||0)>0?'openExchangeZarnikiModal()':"goTo('market','vip')"}"><div>✨</div><div class="sv" id="pro-stat-zar">${Math.floor(d.zarniki||0)}</div><div class="sl">${(d.zarniki||0)>0?'Зарники':'Зарники +'}</div></div>
          <div class="stat clickable" onclick="goTo('ach')"><div>🏆</div><div class="sv" id="pro-stat-ach">${d.achievements}</div><div class="sl">Ачивки ›</div></div>
        </div>
        <div class="profile-showcase-meta">
          <span>🆔 <code>${uid}</code></span>
          <button class="profile-copy-id" type="button" onclick="copyUid(${uid})">Копировать</button>
        </div>
      </div>

      <div class="profile-card-actions" aria-label="Настройки профиля">
        <button type="button" onclick="openClansModal()"><span aria-hidden="true">🛡</span><span>Клан</span></button>
        <button type="button" onclick="openPromoModal()"><span aria-hidden="true">🎟</span><span>Промокод</span></button>
        <button type="button" onclick="openSettingsModal()"><span aria-hidden="true">⚙️</span><span>Настройки</span></button>
      </div>

      <!-- Быстрые действия: всё важное в 1 клик -->
      <div class="qa-row">
        <div class="qa qa-hot" onclick="goTo('quests','streak')"><span>🔥</span>Стрик <span>${d.streak}</span></div>
        <div class="qa" onclick="goTo('quests')"><span>📋</span>Квесты</div>
        <div class="qa" onclick="goTo('bp')"><span>🎫</span>Пропуск</div>
        <div class="qa" onclick="goTo('zoo')"><span>🍖</span>Питомцы</div>
      </div>

      <!-- Топ-3 игроков (loadTop3) — соревнование на видном месте (block 11) -->
      <div id="pro-top3"></div>

      <!-- Активные баффы (заполняется loadActiveBuffs) -->
      <div id="pro-buffs"></div>

      ${d.is_vip?'':`<div class="vip-banner" onclick="goTo('market','vip')">
        <span class="vb-crown">👑</span>
        <div><div class="vb-title">Стань VIP</div><div class="vb-sub">Еженедельные подарки, +слот питомника, безлимит ника</div></div>
        <span class="vb-cta">›</span>
      </div>`}

      <!-- Карточка брака (заполняется loadMarriageCard) -->
      <div id="pro-marriage-card"><div class="sk" style="height:90px;border-radius:var(--r)"></div></div>
      <!-- Карточка ника (заполняется loadNickCard) -->
      <div id="pro-nick-card"></div>
      ${pets.length?`<details class="profile-fold">
        <summary><span class="profile-fold-title">🐾 Питомники</span><span class="profile-fold-meta">${pets.length} активн.</span><span class="profile-fold-arrow" aria-hidden="true">›</span></summary>
        <div class="profile-fold-body">
        ${pets.map(p=>`
        <div class="pcard" onclick="goTo('zoo')" style="cursor:pointer"><div class="pcol">
          <div class="pn">${p.name||p.species_id} ${rc(p.rarity)}</div>
          <div class="ps">Lv${p.pet_level} · ${PL[p.placement]}</div>
          <div class="fat-bar"><div class="fat-fill" style="width:${p.fatigue}%;background:${fatC(p.fatigue)}"></div></div>
        </div></div>`).join('')}
        <div class="shortcut-row">
          <span class="shortcut-link" onclick="goTo('zoo')">Управлять питомцами →</span>
        </div>
        </div>
      </details>`:`<details class="profile-fold"><summary><span class="profile-fold-title">🐾 Питомники</span><span class="profile-fold-meta">Нет питомцев</span><span class="profile-fold-arrow" aria-hidden="true">›</span></summary><div class="profile-fold-body"><div class="empty-state"><div class="es-icon">🐾</div><div class="es-title">Питомцев пока нет</div><div class="es-sub">Крутни Гачу, чтобы завести первого</div><button class="btn btn-gold btn-sm" style="margin-top:10px" onclick="goTo('market','gacha')">🎲 Открыть Гачу</button></div></div></details>`}
      ${d.chats.length?`<details class="profile-fold">
        <summary><span class="profile-fold-title">💬 Активность</span><span class="profile-fold-meta">${d.chats.length} ${d.chats.length===1?'чат':'чата'}</span><span class="profile-fold-arrow" aria-hidden="true">›</span></summary>
        <div class="profile-fold-body">
        ${d.chats.map(c=>`<div class="irow"><span class="ik">${esc(c.chat_title||'Чат')}</span><span class="iv">Lv${c.user_level} · ${fmt(c.user_messages_count_all_time)}</span></div>`).join('')}
        <div class="shortcut-row">
          <span class="shortcut-link" onclick="goTo('hof')">Посмотреть топ →</span>
        </div>
        </div>
      </details>`:''}
      <div id="wallet-mini"></div>`;
    loadMarriageCard();
    loadNickCard();
    loadTop3();
    loadActiveBuffs();
    loadWalletMini();
    if(!_ws && _uid) connectWS();
    updateCurrBar(d);          // populate sticky currency bar from profile data
    if(!_adminChats) checkAdminAccess();
    checkGlobalAccess();
  }).catch(e=>{el('pro-main').innerHTML=`<div style="color:var(--red);padding:20px;font-size:12px">${typeof e==='string'?e:'Напишите боту чтобы создать профиль.'}</div>`;});
}
// ── Топ-3 игроков на профиле (block 11): соревнование на видном месте ──────────
// Глобальный подиум + СВОЁ место и дистанция до топ-3 — главный крючок вовлечения.
function loadTop3(){
  const box=el('pro-top3'); if(!box) return;
  api('/top/global').then(rows=>{
    if(!Array.isArray(rows) || rows.length<3){ box.innerHTML=''; return; }  // нужен полный подиум
    const top3=rows.slice(0,3);
    const meIdx=rows.findIndex(r=>String(r.user_id)===String(typeof _uid!=='undefined'?_uid:''));
    const meRank=meIdx>=0?meIdx+1:null;
    const rowsHtml=top3.map((r,i)=>`<div class="t3-row${meRank===i+1?' t3-row--me':''}">
        <span class="t3-medal">${MEDALS[i]||(i+1)}</span>
        <span class="t3-name">${_topName(r)}</span>
        <span class="t3-cnt">${fmt(r.count)} 💬</span>
      </div>`).join('');
    let you;
    if(meRank && meRank>3){
      const gap=Math.max(1,(top3[2].count||0)-(rows[meIdx].count||0)+1);
      you=`<span>Ты <b>#${meRank}</b></span><span>до топ-3: <b>+${fmt(gap)}</b> 💬</span>`;
    } else if(meRank){
      you=`<span>🔥 Ты в топ-3 — <b>#${meRank}</b></span><span>удержи место</span>`;
    } else {
      you=`<span>Ты пока вне топ-200</span><span>активнее в чатах →</span>`;
    }
    box.innerHTML=`<div class="card t3-card" onclick="openTop3Full()">
      <div class="t3-head"><span class="t3-title">🏆 Топ игроков</span><span class="t3-all">весь топ ›</span></div>
      ${rowsHtml}
      <div class="t3-you">${you}</div>
    </div>`;
  }).catch(()=>{box.innerHTML='';});
}
function openTop3Full(){
  goTo('hof');
  // виджет глобальный → открываем глобальную вкладку (2-я кнопка в свитчере топа)
  const btns=document.querySelectorAll('#pro-hof .tab-inner .tb');
  if(btns[1]) switchTop('global', btns[1]);
}
// ── БЛОК22: Настройки + юридические документы ──────────────────────────────────
function _legalUrl(slug){ return BASE+'/legal/'+slug; }   // прямая публичная ссылка
function openLegalDoc(slug){
  const t={tos:'📖 Пользовательское соглашение',privacy:'🔒 Политика конфиденциальности'};
  OM(t[slug]||'Документ','<div class="loader">Загрузка…</div>',[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
  api('/legal/'+slug+'/text').then(d=>{
    el('mb').innerHTML=`<div class="legal-doc">${d.html}</div>
      <div class="legal-link">Прямая ссылка: <a href="${_legalUrl(slug)}" target="_blank" rel="noopener">${_legalUrl(slug)}</a></div>`;
  }).catch(e=>{ el('mb').innerHTML=`<div class="err">${e}</div>`; });
}
function openSettingsModal(){
  const noFx=document.body.classList.contains('no-fx');
  const easyInp=_easyInput();
  OM('⚙️ Настройки',`
    <div class="set-sec-t">Внешний вид</div>
    <label style="display:flex;align-items:center;gap:8px;padding:8px 2px;cursor:pointer">
      <input type="checkbox" ${noFx?'checked':''} onchange="_toggleNoFx(this.checked)"/>
      <span style="font-size:12.5px">Отключить анимации косметики</span>
    </label>
    <div class="set-hint">Свечения, рамки и частицы станут статичными — полезно на слабых телефонах.</div>
    <label style="display:flex;align-items:center;gap:8px;padding:8px 2px;cursor:pointer">
      <input type="checkbox" ${easyInp?'checked':''} onchange="_toggleEasyInput(this.checked)"/>
      <span style="font-size:12.5px">Упрощённый ввод (бой и гача)</span>
    </label>
    <div class="set-hint">Тайминг крита/ульты в бою мягче, крутка гачи — обычным тапом без удержания. Для тех, кому неудобно ловить моменты.</div>
    <div class="set-sec-t" style="margin-top:14px">🔔 Уведомления от бота</div>
    <div id="set-notif-prefs"><div class="loader">Загрузка...</div></div>
    <div class="set-hint">Личные напоминания в ЛС. Групповые события чата приходят всем и здесь не отключаются.</div>
    <div class="set-sec-t" style="margin-top:14px">Юридические документы</div>
    <button class="btn btn-ghost btn-full" onclick="openLegalDoc('tos')">📖 Пользовательское соглашение</button>
    <button class="btn btn-ghost btn-full" style="margin-top:7px" onclick="openLegalDoc('privacy')">🔒 Политика конфиденциальности</button>
    <div class="set-hint">Документы также доступны по прямой ссылке и в боте.</div>
    ${!INIT_DATA?`<div class="set-sec-t" style="margin-top:14px">🔀 Вход</div>
    <div class="set-hint">Сейчас: Telegram @${esc((_profileData&&_profileData.username)||'—')}. Сайт открыт в браузере — если сменили активный аккаунт в приложении Telegram, страница сама этого не узнает.</div>
    <button class="btn btn-ghost btn-full" style="margin-top:6px" onclick="switchTgAccount()">🔀 Войти другим Telegram-аккаунтом</button>`:''}
    <div class="set-sec-t" style="margin-top:14px">👤 Аккаунт</div>
    <div id="set-account"><div class="loader">Загрузка...</div></div>`,
    [{l:'Готово',c:'btn-ghost',f:'CM()'}]);
  _loadNotifPrefs();
  _loadAccountSection();
}
// admin_audit C1b: авто-удаление за неактив + самоудаление с тройной защитой
function _loadAccountSection(){
  const box=el('set-account'); if(!box) return;
  api('/account/deletion-status').then(d=>{
    const days=d.delete_after_days||365;
    const proc=d.process_status;
    let procHtml='';
    if(proc==='confirming') procHtml=`<div class="set-hint" style="color:var(--gold2)">⏳ Ожидается код из ЛС бота.</div>
      <button class="btn btn-teal btn-full" onclick="_accCancel()">↩ Отменить процесс</button>`;
    if(proc==='cooling') procHtml=`<div class="set-hint" style="color:var(--red)">⏳ Удаление запланировано — период «остывания».</div>
      <button class="btn btn-teal btn-full" onclick="_accCancel()">↩ Отменить удаление</button>`;
    box.innerHTML=`
      <div style="font-size:12px;margin-bottom:4px">Удалять аккаунт после неактива:</div>
      <select class="num-input" style="margin:0 0 4px" onchange="_accSetInactivity(this.value)">
        <option value="180" ${days===180?'selected':''}>6 месяцев</option>
        <option value="365" ${days===365?'selected':''}>1 год (по умолчанию)</option>
        <option value="730" ${days===730?'selected':''}>2 года</option>
      </select>
      <div class="set-hint">За 14 дней до срока придёт предупреждение в ЛС; любое сообщение в чате отменяет отсчёт. После удаления — 14 дней на восстановление.</div>
      ${procHtml||`<button class="btn btn-ghost btn-full" style="margin-top:6px;color:var(--red)" onclick="_accDeleteStart()">🗑 Удалить аккаунт…</button>`}`;
  }).catch(e=>{box.innerHTML=`<div class="err">${e}</div>`;});
}
function _accSetInactivity(v){
  api('/account/set-inactivity',{method:'POST',body:JSON.stringify({days:parseInt(v,10)})})
    .then(r=>toast(r.message||'✅')).catch(e=>toast(e,false));
}
function _accDeleteStart(){
  OM('🗑 Удаление аккаунта — шаг 1 из 3',
    `<div style="font-size:12px;color:var(--muted);line-height:1.5;padding:6px 0">
      Будут удалены: питомцы, инвентарь, косметика, балансы, прогресс.<br>
      <b>14 дней</b> после удаления всё можно вернуть («бот восстановить аккаунт»).<br><br>
      Сейчас в <b>ЛС бота</b> придёт код подтверждения.</div>`,
    [{l:'📨 Получить код',c:'btn-red',f:'_accDeleteRequest()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _accDeleteRequest(){
  api('/account/delete/request',{method:'POST'}).then(()=>{
    OM('🗑 Удаление — шаг 2 из 3',
      `<div style="font-size:12px;color:var(--muted);padding:4px 0">Код отправлен в ЛС бота.</div>
       <input id="acc-del-code" class="num-input" inputmode="numeric" style="margin:6px 0" placeholder="Код из ЛС (6 цифр)"/>
       <input id="acc-del-phrase" class="num-input" style="margin:0 0 4px" placeholder="Введите вручную: УДАЛИТЬ АККАУНТ"/>
       <div class="set-hint">Шаг 3 — автоматический: 24 часа «остывания», в течение которых удаление можно отменить (в ЛС придёт напоминание как).</div>`,
      [{l:'Подтвердить удаление',c:'btn-red',f:'_accDeleteConfirm()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
  }).catch(e=>toast(e,false));
}
function _accDeleteConfirm(){
  const code=el('acc-del-code')?.value.trim(), phrase=el('acc-del-phrase')?.value.trim();
  api('/account/delete/confirm',{method:'POST',body:JSON.stringify({code,phrase})})
    .then(r=>{toast(r.message||'⏳ Запланировано');CM();})
    .catch(e=>toast(e,false));
}
function _accCancel(){
  api('/account/delete/cancel',{method:'POST'})
    .then(r=>{toast(r.message||'✅ Отменено');_loadAccountSection();})
    .catch(e=>toast(e,false));
}
// R6 «Умный Пульс»: тумблеры персональных DM-уведомлений (раньше их нельзя было
// отключить нигде — БЛОК 36.1)
function _loadNotifPrefs(){
  const box=el('set-notif-prefs'); if(!box) return;
  api('/profile/notification-prefs').then(d=>{
    box.innerHTML=(d.categories||[]).map(c=>`
      <label style="display:flex;align-items:center;gap:8px;padding:6px 2px;cursor:pointer">
        <input type="checkbox" ${c.enabled?'checked':''} onchange="_setNotifPref('${c.key}',this.checked)"/>
        <span style="font-size:12.5px">${esc(c.label)}</span>
      </label>`).join('')||'<div class="set-hint">Категорий пока нет.</div>';
  }).catch(()=>{box.innerHTML='<div class="set-hint" style="color:var(--red)">Не удалось загрузить настройки.</div>';});
}
function _setNotifPref(key,on){
  api('/profile/notification-prefs',{method:'POST',body:JSON.stringify({category:key,enabled:on})})
    .then(()=>toast(on?'🔔 Включено':'🔕 Выключено'))
    .catch(e=>{toast(e,false);_loadNotifPrefs();});
}
function _toggleNoFx(on){
  document.body.classList.toggle('no-fx',on);
  try{ localStorage.setItem('pv_no_fx',on?'1':'0'); }catch(e){}
}
// UX_AUDIT С23: облегчённый ввод для игроков с моторными/реакционными ограничениями.
// Потребители: гача (app.04 — спин тапом вместо удержания) и бой (app.11 — мягче QTE).
function _easyInput(){ try{ return localStorage.getItem('pv_easy_input')==='1'; }catch(e){ return false; } }
function _toggleEasyInput(on){
  try{ localStorage.setItem('pv_easy_input',on?'1':'0'); }catch(e){}
  toast(on?'🧿 Упрощённый ввод включён':'Упрощённый ввод выключен');
}
// Блок-экран принятия документов (неубираемый оверлей) — для не принявших.
function _tosGate(d){
  const ex=el('tos-gate');
  if(d&&d.tos_accepted){ if(ex) ex.remove(); return; }
  if(ex) return;
  const g=document.createElement('div');
  g.id='tos-gate'; g.className='tos-gate';
  g.innerHTML=`<div class="tos-gate-box">
    <div class="tos-gate-emoji">📋</div>
    <div class="tos-gate-title">Добро пожаловать в PREDVESTNIK</div>
    <div class="tos-gate-sub">Чтобы продолжить, ознакомьтесь и примите наши документы.</div>
    <div class="tos-gate-links">
      <button class="btn btn-ghost" onclick="openLegalDoc('tos')">📖 Правила (ToS)</button>
      <button class="btn btn-ghost" onclick="openLegalDoc('privacy')">🔒 Конфиденциальность</button>
    </div>
    <button class="btn btn-gold btn-full" onclick="_tosAccept(this)">✅ Принять и играть</button>
    <div class="tos-gate-hint">Нажимая «Принять», вы соглашаетесь с Пользовательским соглашением и Политикой конфиденциальности.</div>
  </div>`;
  document.body.appendChild(g);
}
function _tosAccept(btn){
  if(btn){ btn.disabled=true; btn.textContent='Сохраняем…'; }
  api('/legal/accept',{method:'POST'}).then(()=>{
    const g=el('tos-gate'); if(g) g.remove();
    toast('✅ Спасибо! Приятной игры.',true);
    if(_profileData) _profileData.tos_accepted=true;
    loadProfile();
    _showWelcome();
  }).catch(e=>{ toast(e,false); if(btn){ btn.disabled=false; btn.textContent='✅ Принять и играть'; } });
}
// UX-аудит: единственный «welcome»-экран был юридическим гейтом без единого
// слова о геймплее — новый игрок оставался один на один с пустым профилем.
// Показываем короткое приветствие ровно один раз, сразу после принятия ToS
// (= момент первого реального входа), с одним понятным следующим шагом.
function _showWelcome(){
  try{ if(localStorage.getItem('pv_welcomed')) return; localStorage.setItem('pv_welcomed','1'); }catch(e){}
  setTimeout(()=>OM('👋 Коротко о главном', `
    <div style="font-size:12px;line-height:1.6">
      <p>Общайся в чате — растёт опыт и открываются <b>Задания</b> с наградой в
      <b>🪙 Мору</b> (основная валюта). На Мору покупаешь еду, крутишь Гачу за
      питомцами, растишь питомник.</p>
      <p>💎 <b>Алмазы</b> — премиум-валюта (события/донат). ✨ <b>Зарники</b> — за реальные Stars,
      на косметику и VIP.</p>
      <p>Нажми на цифры валют в самом верху экрана в любой момент — там подробное
      объяснение, что для чего.</p>
      <p style="color:var(--gold2)">Первый шаг: открой 📋 Задания — там первая Мора на первую крутку Гачи.</p>
    </div>`, [
    {l:'📋 К заданиям', c:'btn-gold', f:'CM();goTo("quests")'},
    {l:'Понятно, сам разберусь', c:'btn-ghost', f:'CM()'},
  ]), 500);
}


// ── Кланы / Гильдии ─────────────────────────────────────────────────────────────
let _clansData=null, _clanEmblemSel='🛡';
function openClansModal(){
  OM('🛡 Кланы','<div class="loader">Загрузка...</div>',[{l:'Готово',c:'btn-ghost',f:'CM()'}]);
  api('/clans/').then(d=>{_clansData=d; _clanEmblemSel=(d.emblems&&d.emblems[0])||'🛡'; renderClans();})
    .catch(e=>{const b=el('mb'); if(b)b.innerHTML=`<div class="err">${e}</div>`;});
}
function renderClans(){
  const b=el('mb'); if(!b||!_clansData) return;
  b.innerHTML=(_clansData.my_clan?_clanMyHtml():_clanCreateHtml())+_clanTopHtml();
}
function _clanMyHtml(){
  const c=_clansData.my_clan;
  const lp=c.level_progress||{level:c.level||1,xp_into:0,xp_needed:0,is_max:false};
  const pct=lp.is_max?100:(lp.xp_needed?Math.min(100,Math.round(lp.xp_into/lp.xp_needed*100)):0);
  const emax=c.effective_max||_clansData.max_members;
  const members=(c.members||[]).map(m=>{
    const lead=m.role==='leader';
    const title=m.title?`<div class="top-title">${esc(m.title)}</div>`:'';
    return `<div class="clan-mrow"><span class="clan-mname">${lead?'👑 ':''}${unameLink(m.user_id, m.username, false, m.glow)}${title}</span>
      <span class="clan-mrole">🎖 ${fmtF(m.clan_coins||0)}</span></div>`;
  }).join('');
  return `<div class="clan-card">
      <div class="clan-emblem">${c.emblem||'🛡'}</div>
      <div class="clan-name">${esc(c.name)} <span class="clan-tag">[${esc(c.tag)}]</span></div>
      ${c.description?`<div class="clan-desc">${esc(c.description)}</div>`:''}
      <div class="clan-lvlrow"><span class="clan-lvlbadge">🏛 Уровень ${lp.level}</span>
        <span class="clan-lvlxp">${lp.is_max?'МАКС':fmtF(lp.xp_into)+' / '+fmtF(lp.xp_needed)+' XP'}</span></div>
      <div class="clan-lvlbar"><div class="clan-lvlfill" style="width:${pct}%"></div></div>
      <div class="clan-stats"><div><b>${(c.members||[]).length}</b>/${emax} участников</div>
        <div><b>${fmtF(c.total_xp||0)}</b> XP · 🎖 <b>${fmtF(c.clan_coins||0)}</b></div></div>
    </div>
    ${_clan2NavHtml()}
    ${_clanShopHtml()}
    ${_clanBuildingsHtml()}
    <div class="looks-slot-t" style="margin-top:12px">Состав <span class="clan-coin-note">· вклад 🎖</span></div>
    <div class="clan-members">${members}</div>
    <button class="btn btn-full btn-ghost" style="margin-top:12px" onclick="_clanLeave()">🚪 Покинуть клан</button>`;
}
function _clanBuildingsHtml(){
  const c=_clansData.my_clan;
  const bs=(c&&c.buildings)||[];
  if(!bs.length) return '';
  const lvl=(c.level)||1;
  const cards=bs.map(b=>`<div class="clan-bld">
    <div class="clan-bld-ico">${b.emoji||'🏛'}</div>
    <div class="clan-bld-body">
      <div class="clan-bld-name">${esc(b.name)}</div>
      <div class="clan-bld-eff">${esc(b.effect||'')}</div>
      ${b.next_effect?`<div class="clan-bld-next">↑ ур.${lvl+1}: ${esc(b.next_effect)}</div>`:`<div class="clan-bld-next clan-bld-max">★ максимум</div>`}
    </div></div>`).join('');
  return `<div class="looks-slot-t" style="margin-top:12px">🏛 Штаб клана · ур.${lvl}</div>
    <div class="clan-blds">${cards}</div>`;
}
function _clanCreateHtml(){
  const emblems=(_clansData.emblems||[]).map(e=>`<span class="clan-emb-opt ${e===_clanEmblemSel?'sel':''}" onclick="_clanPickEmblem('${e}')">${e}</span>`).join('');
  return `<div class="looks-hint">Создай свой клан или вступи в существующий ниже. Один клан на игрока.</div>
    <div class="clan-form">
      <div class="looks-slot-t">Эмблема</div>
      <div class="clan-emblems">${emblems}</div>
      <input id="clan-name" type="text" class="num-input" maxlength="${_clansData.name_max||24}" placeholder="Название клана"/>
      <input id="clan-tag" type="text" class="num-input" maxlength="${_clansData.tag_max||5}" placeholder="Тег (2–5, напр. WOLF)" style="text-transform:uppercase"/>
      <input id="clan-desc" type="text" class="num-input" maxlength="120" placeholder="Девиз (необязательно)"/>
      <button class="btn btn-full btn-gold" onclick="_clanCreate()">🛡 Основать за ${fmtF(_clansData.create_cost||0)} 🪙</button>
    </div>`;
}
function _clanTopHtml(){
  const top=_clansData.top||[]; if(!top.length) return '';
  const inClan=!!_clansData.my_clan;
  const rows=top.map((c,i)=>{
    const mine=_clansData.my_clan&&_clansData.my_clan.clan_id===c.clan_id;
    const join=(!inClan)?`<button class="btn btn-sm btn-gold" onclick="_clanJoin(${c.clan_id})">Вступить</button>`:(mine?'<span class="clan-you">ты тут</span>':'');
    return `<div class="clan-trow${mine?' clan-mine':''}"><span class="clan-trank">${i+1}</span>
      <span class="clan-temblem">${c.emblem||'🛡'}</span>
      <span class="clan-tname">${esc(c.name)} <span class="clan-tag">[${esc(c.tag)}]</span></span>
      <span class="clan-txp">ур.${c.level||1} · ${fmtF(c.total_xp||0)} XP · ${c.member_count}/${c.effective_max||_clansData.max_members}</span>
      ${join}</div>`;
  }).join('');
  return `<div class="looks-slot-t" style="margin-top:14px">🏆 Топ кланов</div><div class="clan-top">${rows}</div>`;
}
function _clanPickEmblem(e){ _clanEmblemSel=e; renderClans(); }
function _clanCreate(){
  const name=(el('clan-name')||{}).value||'', tag=(el('clan-tag')||{}).value||'', desc=(el('clan-desc')||{}).value||'';
  api('/clans/create',{method:'POST',body:JSON.stringify({name,tag,description:desc,emblem:_clanEmblemSel})})
    .then(r=>{toast(r.message); refreshCurrBar(); openClansModal();})
    .catch(e=>toast(e,false));
}
function _clanJoin(id){
  api('/clans/join',{method:'POST',body:JSON.stringify({clan_id:id})})
    .then(r=>{toast(r.message); openClansModal();}).catch(e=>toast(e,false));
}
function _clanLeave(){
  OM('🚪 Покинуть клан','<div style="padding:6px 2px;font-size:13px">Точно выйти? Если ты лидер — лидерство перейдёт старейшему участнику, а без участников клан распустится.</div>',
    [{l:'Отмена',c:'btn-ghost',f:'openClansModal()'},{l:'Выйти',c:'btn-gold',f:'_clanLeaveDo()'}]);
}
function _clanLeaveDo(){
  api('/clans/leave',{method:'POST',body:JSON.stringify({})})
    .then(r=>{toast(r.message); openClansModal();}).catch(e=>{toast(e,false); openClansModal();});
}
// ── Доска Запросов: создать / помочь / снять ────────────────────────────────────
function _clanReqCreateDo(){
  const item=(el('creq-item')||{}).value||'';
  const qty=parseInt((el('creq-qty')||{}).value||'1',10)||1;
  api('/clans/request/create',{method:'POST',body:JSON.stringify({item_id:item,qty:qty})})
    .then(r=>{toast(r.message); openClansModal();}).catch(e=>toast(e,false));
}
// ── Клан-лавка (сток clan_coins) ────────────────────────────────────────────────
function _clanShopHtml(){
  const c=_clansData.my_clan;
  const shop=(c&&c.shop)||[];
  if(!shop.length) return '';
  const coins=c.clan_coins||0;
  const rows=shop.map(s=>{
    const afford=coins+1e-9>=s.cost;
    const btn=afford
      ?`<button class="btn btn-sm btn-gold" onclick="_clanShopBuy('${s.id}')">${fmtF(s.cost)} 🎖</button>`
      :`<button class="btn btn-sm btn-ghost" disabled style="opacity:.5">${fmtF(s.cost)} 🎖</button>`;
    return `<div class="clan-req">
      <div class="clan-req-top"><span class="clan-req-name">${s.emoji||'🎖'} ${esc(s.name)}</span>
        <span class="clan-req-act">${btn}</span></div>
      <div class="clan-board-hint" style="margin:2px 0 0">${esc(s.desc||'')}</div>
    </div>`;
  }).join('');
  return `<div class="clan-board-head"><span class="looks-slot-t" style="margin:0">🎖 Клан-лавка</span>
      <span class="clan-coin-note">у тебя ${fmtF(coins)} 🎖</span></div>
    <div class="clan-board-hint">Трать клан-монеты, заработанные помощью по Доске.</div>
    <div class="clan-board">${rows}</div>`;
}
function _clanShopBuy(id){
  api('/clans/shop/buy',{method:'POST',body:JSON.stringify({shop_id:id})})
    .then(r=>{toast(r.message); refreshCurrBar(); openClansModal();}).catch(e=>toast(e,false));
}
// ── Preloader: эффектный холодный старт (БЛОК 9.2) ──────────────────────────────
function _plSkip() {
  const pl = el('preloader');
  if(!pl || pl.classList.contains('pl-done')) return;
  pl.classList.add('pl-done');
  // Вход → вкладка = одно целое: активная страница «всплывает» каскадом,
  // пока прелоадер растворяется.
  const pg = document.querySelector('.page.active');
  if(pg){ pg.classList.add('pg-enter'); setTimeout(()=>pg.classList.remove('pg-enter'), 1000); }
  setTimeout(()=>{ const p=el('preloader'); if(p) p.remove(); }, 600);
}
function _runPreloader() {
  const pl = el('preloader'); if(!pl) return;
  const reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const box = el('pl-lines');
  // UX_AUDIT С2: гостю без сессии нечего «синхронизировать» — честные нейтральные строки
  const _authed = !!(INIT_DATA || sess());
  const lines = _authed
    ? ['🔌 Синхронизация с сервером…','🔍 Проверка сигнатур…','📦 Загрузка данных…']
    : ['🌘 Открываем врата…','📦 Загрузка данных…'];
  let i = 0;
  const add = () => { if(!box || i>=lines.length) return; const d=document.createElement('div'); d.className='pl-line'; d.textContent=lines[i++]; box.appendChild(d); };
  add();
  const step = reduce ? 90 : 440;
  const tm = setInterval(()=>{ if(i>=lines.length){ clearInterval(tm); return; } add(); }, step);
  setTimeout(()=>{
    const ln = el('pl-lines'); if(ln) ln.classList.add('pl-fade');   // убираем строки — чистая сцена под приветствие
    const mode = (_profileData && _profileData.cosmetics && _profileData.cosmetics.welcome) || 'scanner';
    pl.classList.add('plm-' + mode);                                 // режим приветствия (VIP-выбор, дефолт — scanner)
    const w = el('pl-welcome'); if(!w) return;
    const nick = (_profileData && _profileData.username) ? _profileData.username : '';
    w.innerHTML = nick
      ? `<span class="plw-hi">Добро пожаловать,</span><span class="plw-nick">@${esc(nick)}</span>`
      : `<span class="plw-nick" style="font-size:23px">Добро пожаловать!</span>`;
    w.classList.add('show');
  }, reduce ? 220 : 1500);
  setTimeout(_plSkip, reduce ? 650 : 3200);
}
_runPreloader();

// БЛОК19 Web-First: бот-редиректы открывают мини-апп через ?startapp=<section> →
// доводим юзера до нужного раздела (раньше start_param игнорировался).
function _handleStartParam(){
  let p=''; try{ p=String((tg&&tg.initDataUnsafe&&tg.initDataUnsafe.start_param)||''); }catch(e){}
  // Фолбэк: обычная HTTPS-ссылка ?startapp=<section> (не t.me-диплинк) не несёт
  // нативный start_param — Telegram его просто не заполняет. Раздел в этом
  // случае лежит в query самой страницы.
  if(!p){ try{ p=new URLSearchParams(location.search).get('startapp')||''; }catch(e){} }
  if(!p) return;
  const base=p.split('_')[0];
  const run=fn=>setTimeout(()=>{ try{ fn(); }catch(e){} }, 380);
  if(base==='clans'){ run(()=>openClansModal()); return; }
  if(base==='cosmetics'||base==='looks'){ run(()=>openLooksModal()); return; }
  if(base==='exchange'||base==='exch'){ run(()=>{ switchPage('auction'); setTimeout(()=>{try{swAuction('exch')}catch(e){}},220); }); return; }
  if(base==='crypto'||base==='birzha'){ run(()=>{ switchPage('auction'); setTimeout(()=>{try{swAuction('crypto')}catch(e){}},220); }); return; }
  // БЛОК 36.1: «бот уведомления» раньше вёл на голую вкладку профиля — теперь
  // сразу открывает «⚙️ Настройки» с чекбоксами уведомлений.
  if(base==='notifications'||base==='notifprefs'){ run(()=>{ switchPage('profile'); setTimeout(()=>{try{openSettingsModal()}catch(e){}},260); }); return; }
  const M={ shop:['market','goods'],goods:['market','goods'],gacha:['market','gacha'],deal:['market','deal'],
    vip:['market','vip'],themes:['profile','themes'],craft:['craft'],inventory:['profile','inv'],inv:['profile','inv'],
    quests:['quests'],ach:['ach'],achievements:['ach'],zoo:['zoo'],pets:['zoo'],bp:['bp'],auction:['auction'],
    arena:['arena'],games:['arena','games'],casino:['arena','games'],relics:['market'],
    barracks:['arena','barracks'],gates:['arena','gates'] };
  const t=M[base]; if(t) run(()=>goTo(t[0],t[1]));
}
if(INIT_DATA||sess()){loadProfile();_loaded.add('profile');setTimeout(loadPendingNotifications,1000);_handleStartParam();}

// ── Sticky currency bar ───────────────────────────────────────────────────────
// Редизайн v5: хедер с валютами виден ВСЕГДА (см. showCurrBar ниже — параметр show
// уже не используется, флаг всегда true). Раньше стартовал false и включался только
// внутри switchPage() — а Профиль загружается из серверного HTML БЕЗ switchPage(),
// поэтому в свежей сессии, где игрок ни разу не тронул нижнюю навигацию, весь
// авто-refresh валют (и 90-сек таймер, и реактивный хук после мутаций) молча не
// работал до первого перехода по вкладкам. Стартуем сразу true.
let _currBarVisible = true;
let _currInited = false;

// UX-фикс: компакт больших чисел в шапке (12,3к / 1,2М) — иначе 4 чипа с
// длинными суммами не влезают в 390px и наезжают на аватар. Точные значения —
// в модалке валют (ⓘ) и в профиле, там по-прежнему полный fmtF.
function fmtBar(v){
  v = +v || 0;
  if (v >= 1e6) return (v/1e6).toFixed(1).replace('.',',').replace(',0','') + 'М';
  if (v >= 1e4) return (v/1e3).toFixed(1).replace('.',',').replace(',0','') + 'к';
  if (v >= 1e3) return fmt(Math.round(v));   // ≥1000 — без копеек, компактнее
  return fmtF(v);
}
function updateCurrBar(data) {
  const bar = el('curr-bar');
  if (!bar) return;
  const set = (id, val, fmt2) => {
    const v=el(id); if(!v) return;
    const next = fmt2(val);
    if (_currInited && v.textContent !== next) {
      v.classList.remove('cb-pulse'); void v.offsetWidth; v.classList.add('cb-pulse');
    }
    v.textContent = next;
  };
  set('cb-mora', data?.mora ?? 0, fmtBar);
  set('cb-dia',  data?.diamonds ?? 0, fmtBar);
  set('cb-dark', data?.dark_mora ?? 0, fmtBar);
  set('cb-zar',  data?.zarniki ?? 0, fmtBar);
  // Баг из UX-аудита: слот 🌑 был захардкожен display:none навсегда — значение
  // обновлялось, но игрок никогда не видел свой баланс Тёмной Моры в шапке.
  // Показываем, как только она у игрока появилась (не захламляем шапку 5-й
  // валютой тем, кто вообще не трогал эту механику).
  const darkItem = el('cb-dark-item');
  if (darkItem) darkItem.style.display = (data?.dark_mora > 0) ? '' : 'none';
  _currInited = true;
  // Хедер: имя + уровень/ранг игрока
  if (data?.username !== undefined) {
    const nm=el('hdr-name'); if(nm) nm.textContent=(data.is_vip?'👑 ':'')+(data.username||'Игрок');
    const sub=el('hdr-sub');
    if(sub) sub.textContent=`Lv${data.account_level||data.chats?.[0]?.user_level||1} · 🔥${data.streak||0}`;
    const av=el('hdr-ava'); if(av && data.is_vip){ av.textContent='👑'; _ensureVipAvatar(); }
  }
}

// ── VIP Telegram avatar (Block 3) ──────────────────────────────────────────────
// Грузим один раз за сессию, кэшируем, применяем к хедеру и карточке профиля.
let _vipAvatar = null, _vipAvatarTried = false;
function _applyVipAvatar() {
  if (!_vipAvatar) return;
  const img = `<img src="${_vipAvatar}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;display:block">`;
  const h = el('hdr-ava'); if (h) h.innerHTML = img;
  const p = el('pro-ava'); if (p) p.innerHTML = img;
  const f = el('fit-ava'); if (f) f.innerHTML = img;
}
function _ensureVipAvatar() {
  if (_vipAvatar) { _applyVipAvatar(); return; }
  if (_vipAvatarTried) return;
  _vipAvatarTried = true;
  api('/profile/avatar').then(r => {
    if (r && r.avatar) { _vipAvatar = r.avatar; _applyVipAvatar(); }
  }).catch(()=>{});
}

function showCurrModal() {
  const d = _profileData || {};
  const mora = d.mora ?? 0, dia = d.diamonds ?? 0, dark = d.dark_mora ?? 0, zar = d.zarniki ?? 0;
  OM('💰 Валюты', `<div class="curr-modal">
    <div class="cm-block">
      <div class="cm-icon">🪙</div>
      <div class="cm-info">
        <div class="cm-name">Мора <span class="cm-val">${fmtF(mora)}</span></div>
        <div class="cm-desc">Основная валюта. Зарабатывай в чатах, дуэлях, квестах и на аукционе.</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">💎</div>
      <div class="cm-info">
        <div class="cm-name">Алмазы <span class="cm-val">${fmtF(dia)}</span></div>
        <div class="cm-desc">Премиум валюта. Покупай в Магазине или получай за достижения и ивенты.</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">🌑</div>
      <div class="cm-info">
        <div class="cm-name">Тёмная Мора <span class="cm-val">${fmtF(dark)}</span></div>
        <div class="cm-desc">Редкая валюта тёмного рынка. Получай через Контрабанду (раз в 4 дня).</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">✨</div>
      <div class="cm-info">
        <div class="cm-name">Зарники <span class="cm-val">${fmtF(zar)}</span></div>
        <div class="cm-desc">Донат-валюта — нельзя заработать в игре. Открывает эксклюзивные темы и предметы.</div>
      </div>
    </div>
  </div>`, [{l:'Закрыть', c:'btn-ghost', f:'CM()'}]);
}

function showCurrBar(show) {
  // Редизайн v5: хедер с валютами и кнопкой пополнения виден ВСЕГДА (донат на виду).
  _currBarVisible = true;
}

el('curr-bar')?.addEventListener('click', showCurrModal);

// Refresh bar data from server (called on a slow timer + реактивно после мутаций, см. app.01.js api())
function refreshCurrBar() {
  if (!_uid || !_currBarVisible) return;
  api('/profile/me').then(d => {
    updateCurrBar(d);
      if(d.mora!==undefined) _profileData = {...(_profileData||{}),
        mora:d.mora, diamonds:d.diamonds, zarniki:d.zarniki, dark_mora:d.dark_mora};
    _profileSyncStats(d);
  }).catch(()=>{});
}
setInterval(refreshCurrBar, 90000); // every 90s
// Точечный патч цифр на карточке профиля (Мора/Алмазы/Зарники/Ачивки/Индекс Силы/Стрик) —
// БЕЗ полного loadProfile() (это дёрнуло бы скелетон-лоадер и пересборку всей карточки).
// Раньше эти карточки обновлялись только раз в 5 мин (setInterval в app.06.js) или
// вручную (F5) — метки честно предупреждали об этом значком 🔄, теперь он не нужен.
// Патчит и когда экран профиля не активен — тот же паттерн, что уже у updateCurrBar().
function _profileSyncStats(d){
  const set=(id,val)=>{ const n=el(id); if(n && val!=null) n.textContent=val; };
  set('pro-stat-mora', fmt(d.mora));
  set('pro-stat-dia', fmtF(d.diamonds));
  set('pro-stat-zar', Math.floor(d.zarniki||0));
  set('pro-stat-ach', d.achievements);
  set('pro-stat-streak', d.streak);
  if(typeof d.combat_power==='number') set('cp-hero-val', fmt(d.combat_power));
}

// Mirrors services/streak.py:calc_streak_reward
function calcStreakReward(streak) {
  if(streak<=0) streak=1;
  const BLOCK=7, BASE_M=70, BASE_D=0.15, BONUS=4.0;
  const cycle=Math.floor((streak-1)/BLOCK);
  const dayInBlock=((streak-1)%BLOCK)+1;
  const isEnd=(dayInBlock===BLOCK);
  const logMult=1.0+0.5*Math.log(1.0+cycle);
  const blockMult=isEnd?BONUS:1.0;
  return {
    mora:Math.round(BASE_M*logMult*blockMult*100)/100,
    dia:Math.round(BASE_D*logMult*blockMult*100)/100,
    dayInBlock, isEnd, cycle,
  };
}

function plDays(n){n=Math.abs(n)%100;const d=n%10;if(n>10&&n<20)return'дней';if(d===1)return'день';if(d>=2&&d<=4)return'дня';return'дней';}
function loadStreak() {
  el('pro-streak').innerHTML='<div class="loader">Загрузка...</div>';
  api('/streak/calendar').then(d=>{
    const today=new Date().toISOString().slice(0,10);
    const streak=d.streak||0;
    const cur=calcStreakReward(streak||1);
    const dayInBlock=cur.dayInBlock;            // позиция дня в текущем блоке (1..7)
    const cycleStart=cur.cycle*7;               // номер стрика дня 1 текущего блока
    const blockPct=Math.round(dayInBlock/7*100);
    const toBonus=7-dayInBlock;
    const nextRw=calcStreakReward(streak+1);

    // 7-дневный трек блока: завершён / текущий / бонус / будущий
    const track=Array.from({length:7},(_,i)=>{
      const pos=i+1, rw=calcStreakReward(cycleStart+pos);
      const done=streak>0 && pos<dayInBlock;
      const isCur=streak>0 && pos===dayInBlock;
      let cls='st-day'; if(done)cls+=' done'; if(isCur)cls+=' cur'; if(rw.isEnd)cls+=' bonus';
      return `<div class="${cls}">
        <div class="st-day-n">${pos}${rw.isEnd?' ★':''}</div>
        <div class="st-day-r">${fmt(Math.round(rw.mora))}🪙</div>
        ${rw.dia>0?`<div class="st-day-d">${fmtF(rw.dia)}💎</div>`:''}
        ${done?'<div class="st-day-chk">✓</div>':''}</div>`;
    }).join('');

    // Хитмап активности (интенсивность по числу сообщений)
    const cells=d.calendar.map(day=>{
      const c=day.count||0; let lvl=0;
      if(c>0)lvl=1; if(c>=5)lvl=2; if(c>=20)lvl=3; if(c>=50)lvl=4;
      return `<div class="st-cell l${lvl}${day.date===today?' today':''}" title="${day.date}: ${c} сообщ."></div>`;
    }).join('');

    el('pro-streak').innerHTML=`
    <div class="st-hero">
      <div class="st-flame">🔥</div>
      <div class="st-big">${streak}</div>
      <div class="st-sub">${plDays(streak)} подряд · единый на все чаты</div>
      <div class="st-blockbar"><div class="st-blockfill" style="width:${blockPct}%"></div></div>
      <div class="st-blocklabel">Блок #${cur.cycle+1} · день ${dayInBlock}/7 ${toBonus>0?'· до бонуса '+toBonus+' '+plDays(toBonus):'· 🎉 бонусный день!'}</div>
    </div>

    <div class="card" style="margin-top:10px">
      <div class="card-title">🎁 Завтра — день ${streak+1}</div>
      <div class="st-next">
        <span class="st-next-m">+${fmt(Math.round(nextRw.mora))} 🪙</span>
        ${nextRw.dia>0?`<span class="st-next-d">+${fmtF(nextRw.dia)} 💎</span>`:''}
        ${nextRw.isEnd?'<span class="st-next-b">★ БОНУС ×4</span>':''}
      </div>
      <div class="st-track">${track}</div>
      <div style="font-size:10px;color:var(--muted);margin-top:7px">Пиши хотя бы одно сообщение в день в любом чате — стрик растёт. Пропуск дня сбрасывает блок (можно восстановить: «бот стрик восстановить»).</div>
    </div>

    <div class="card" style="margin-top:10px">
      <div class="card-title">📅 Активность · 60 дней</div>
      <div class="st-heat">${cells}</div>
      <div class="st-legend"><span>меньше</span>
        <i class="st-cell l0"></i><i class="st-cell l1"></i><i class="st-cell l2"></i><i class="st-cell l3"></i><i class="st-cell l4"></i>
        <span>больше</span></div>
    </div>`;
  }).catch(e=>{el('pro-streak').innerHTML=`<div style="color:var(--red);padding:10px;font-size:12px">${typeof e==='string'?esc(e):'Ошибка загрузки'}</div>`;});
}

// What each achievement tracks and how to earn it
const ACH_HOW = {
  gacha_addict:{
    how:   'Крутите гачу',
    where: 'Арена → Гача → выберите тип крутки',
    note:  'Засчитывается каждый спин, включая жетоны',
  },
  collector:   {
    how:   'Получите новые виды питомцев',
    where: 'Крутите Гачу — каждый новый вид засчитывается',
    note:  'Важен именно НОВЫЙ вид, не дубликаты существующего',
  },
  trainer:     {
    how:   'Прокачайте питомца до максимального Lv10',
    where: 'Получайте дубликаты из Гачи — уровень растёт',
    note:  'Нужны дубликаты: Common ×10→Lv10, Epic ×4→Lv10 и т.д.',
  },
  wanderer:    {
    how:   'Отправляйте питомцев в экспедиции',
    where: 'Зоопарк → нажмите на питомца → «бот поход»',
    note:  'Засчитывается каждое завершение похода (не старт)',
  },
  persistent:  {
    how:   'Поддерживайте ежедневный стрик',
    where: 'Пишите хотя бы одно сообщение в боте каждый день',
    note:  'Счётчик — максимальный стрик за всё время, не текущий',
  },
  vow_keeper:  {
    how:   'Пробудьте в браке суммарно N дней',
    where: 'Оформите брак: «бот брак, @username» в чате',
    note:  'Счётчик идёт автоматически каждый день пока вы в браке. Суммируется по всем бракам.',
  },
  patron:      {
    how:   'Потратьте Мору в магазине бота',
    where: 'Рынок → Магазин → купите любые предметы',
    note:  'Засчитывается сумма всех покупок в магазине (бот магазин)',
  },
  magnate:     {
    how:   'Накопите максимальный баланс Моры',
    where: 'Зарабатывайте Мору всеми способами, не тратьте',
    note:  'Трекается МАКСИМАЛЬНЫЙ баланс когда-либо, не текущий',
  },
  treasury:    {
    how:   'Накопите максимальный баланс Алмазов',
    where: 'Получайте Алмазы из стрика, ачивок, гачи',
    note:  'Трекается МАКСИМАЛЬНЫЙ баланс когда-либо, не текущий',
  },
  dealer:      {
    how:   'Продайте лоты на аукционе',
    where: 'Рынок → Аукцион → «+ Выставить» → дождитесь покупки',
    note:  'Засчитывается только успешная продажа (кто-то купил)',
  },
  lucky_one:   {
    how:   'Побеждайте в мини-играх',
    where: '«бот кости», «бот монета», «бот число», «бот рулетка»',
    note:  'Засчитывается каждая победа в любой мини-игре',
  },
  duelist:     {
    how:   'Побеждайте в дуэлях',
    where: '«бот дуэль, @соперник, [ставка]» — вызов на дуэль',
    note:  'Засчитывается только победа, не ничья',
  },
  talker:      {
    how:   'Пишите сообщения в чатах с ботом',
    where: 'Любой чат где есть бот — просто общайтесь',
    note:  'Суммируются сообщения из ВСЕХ чатов (глобальный счётчик)',
  },
  star:        {
    how:   'Будьте топ-1 в чате по активности за неделю',
    where: 'Пишите больше всех в чате в течение недели',
    note:  'Засчитывается каждая неделя когда вы на 1-м месте',
  },
  star_gacha:  {
    how:   'Выбивайте легендарных и мифических питомцев из гачи',
    where: 'Арена → Гача — одиночные и мульти-крутки',
    note:  'Считаются legendary и mythic из любой крутки',
  },
  fashionista: {
    how:   'Покупайте предметы косметики',
    where: 'Профиль → Внешний вид — ореолы, рамки, гало, фоны, частицы, титулы',
    note:  'Косметика, что у вас уже есть, тоже засчитана',
  },
  gate_conqueror:{
    how:   'Побеждайте во Вратах',
    where: 'Арена → Врата — PvE-лестница по этажам',
    note:  'Прошлые победы во Вратах тоже засчитаны',
  },
};

function loadAch() {
  el('pro-ach').innerHTML='<div class="loader">Загрузка...</div>';
  api('/achievements/').then(achs=>{
    _achData=achs;
    renderAch();
  }).catch(e=>{el('pro-ach').innerHTML=`<div style="color:var(--red);padding:10px;font-size:12px">${e}</div>`;});
}
function setAchSort(s){_achSort=s;renderAch();}
function renderAch() {
  if(!_achData) return;
  let achs=[..._achData];
  if(_achSort==='progress') achs.sort((a,b)=>b.pct-a.pct);
  else if(_achSort==='todo') achs.sort((a,b)=>(a.completed?1:0)-(b.completed?1:0)||b.pct-a.pct);
  const done=achs.filter(a=>a.completed).length;
  el('pro-ach').innerHTML=`
    <div style="display:flex;gap:4px;margin-bottom:10px;align-items:center;flex-wrap:wrap">
      <span style="font-size:10px;color:var(--muted);margin-right:2px">Сорт:</span>
      <button class="btn btn-sm ${_achSort==='default'?'btn-gold':'btn-ghost'}" style="padding:4px 8px;font-size:10px" onclick="setAchSort('default')">По умолч.</button>
      <button class="btn btn-sm ${_achSort==='progress'?'btn-gold':'btn-ghost'}" style="padding:4px 8px;font-size:10px" onclick="setAchSort('progress')">% прогресса</button>
      <button class="btn btn-sm ${_achSort==='todo'?'btn-gold':'btn-ghost'}" style="padding:4px 8px;font-size:10px" onclick="setAchSort('todo')">Сначала активные</button>
    </div>
    <div class="card">
      <div class="card-title">Достижения <span style="font-size:9px;font-weight:400;color:${done===achs.length?'var(--green)':'var(--muted)'}">${done} / ${achs.length} ✅</span></div>
      ${achs.map(a=>{
        const hw=ACH_HOW[a.id]||{};
        const fc=a.completed?'high':a.pct>=60?'high':a.pct>=25?'':'low';
        // UX-аудит: награда следующего уровня была видна только после
        // открытия модалки — показываем сразу на карточке в списке.
        const rw=a.next_reward||{};
        const rwParts=[rw.mora&&`+${fmt(rw.mora)} 🪙`,rw.diamonds&&`+${rw.diamonds} 💎`].filter(Boolean).join(', ');
        return `<div class="ach-item" style="cursor:pointer" onclick="openAchModal(${JSON.stringify(a).replace(/"/g,"'")})">
          <div class="ach-head">
            <div class="ach-icon">${a.icon}</div>
            <div class="ach-name">${a.name}</div>
            <div class="ach-lvl" style="color:${a.completed?'var(--gold)':a.level>0?'var(--green)':'var(--muted)'}">
              ${a.completed?'★ MAX':a.level>0?`Lv${a.level}`:'—'}
            </div>
          </div>
          <div style="font-size:10px;color:var(--muted);margin-bottom:5px">${hw.how||''}${!a.completed&&rwParts?` · <span style="color:var(--gold)">Далее: ${rwParts}</span>`:''}</div>
          <div class="ach-bar"><div class="ach-fill ${fc}" style="width:${a.pct}%"></div></div>
          <div class="ach-prog">${fmt(a.progress)} / ${fmt(a.next_threshold||a.progress)}${a.completed?' ✅':''}</div>
        </div>`;
      }).join('')}
    </div>`;
}

function openAchModal(a) {
  const hw=ACH_HOW[a.id]||{};
  const rw=a.next_reward||{};
  const rwParts=[rw.mora&&`+${fmt(rw.mora)} 🪙`,rw.diamonds&&`+${rw.diamonds} 💎`].filter(Boolean).join(', ');
  OM(`${a.icon} ${a.name}`,`
    <div style="text-align:center;padding:8px 0 14px">
      <div style="font-size:28px;font-weight:800;color:${a.completed?'var(--gold)':'var(--text)'}">
        ${a.completed?'★ МАКСИМУМ':`Lv${a.level} / ${a.max_level}`}
      </div>
      <div class="ach-bar" style="height:8px;margin:10px 0 4px">
        <div class="ach-fill" style="width:${a.pct}%"></div>
      </div>
      <div style="font-size:12px;color:var(--muted)">${fmt(a.progress)} / ${fmt(a.next_threshold||a.progress)}</div>
    </div>
    <div class="divider"></div>
    <div class="irow"><span class="ik">Что нужно</span><span style="color:var(--text);text-align:right;max-width:65%;font-size:11px">${hw.how||a.desc||'—'}</span></div>
    <div class="irow"><span class="ik">Где</span><span style="color:var(--teal);text-align:right;max-width:65%;font-size:11px">${hw.where||'—'}</span></div>
    ${hw.note?`<div style="background:var(--dim);border-radius:var(--r);padding:8px 10px;margin-top:8px;font-size:11px;color:var(--muted);line-height:1.4">💡 ${hw.note}</div>`:''}
    ${!a.completed&&rwParts?`<div class="irow" style="margin-top:8px"><span class="ik">Награда Lv${a.level+1}</span><span style="color:var(--gold)">${rwParts}</span></div>`:''}
    ${a.completed?`<div style="text-align:center;padding:10px;color:var(--gold);font-size:13px;font-weight:600">🏆 Выполнено полностью!</div>`:''}
  `,[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}


// ── R1: модалка брейкдауна Индекса Силы (⚡ CP) ────────────────────────────────
function showCpBreakdown() {
  const b=_profileData&&_profileData.cp_breakdown;
  if(!b){toast('Данные CP ещё не загружены',false);return;}
  const row=(k,v)=>`<div class="irow"><span class="ik">${k}</span><span class="iv" style="color:var(--gold2)">+${fmt(v)}</span></div>`;
  OM('⚡ Индекс Силы',`
    <div style="text-align:center;padding:8px 0 12px">
      <div style="font-size:30px;font-weight:800;color:var(--gold2)">⚡ ${fmt(b.total)}</div>
      <div style="font-size:10px;color:var(--muted);margin-top:2px">публичный показатель силы аккаунта</div>
    </div>
    ${row('⭐ Уровень аккаунта × 100', b.level_part)}
    ${row('⚔️ Отряд юнитов (Казарма)', b.squad_units!==undefined?b.squad_units:b.active_pet)}
    ${row('🏰 Юниты в резерве (×0.25)', b.reserve_units!==undefined?b.reserve_units:0)}
    ${row('🐾 Коллекция питомцев (×0.1)', b.pet_collection!==undefined?b.pet_collection:b.passive_pets)}
    ${row('🎨 Полный сет косметики', b.cosmetics_set)}
    ${row('🏛 Реликвии', b.relics)}
    <div style="font-size:10px;color:var(--muted);margin-top:8px;line-height:1.4">Боёвка 3.0: силу дают боевые юниты из Казармы. Мирные питомцы — экономика, но коллекция даёт небольшой бонус. Сет косметики — все 6 слотов, бонус по минимальной редкости.</div>
  `,[{l:'🏰 В Казарму',c:'btn-gold',f:"goTo('arena','barracks')"},{l:'Понятно',c:'btn-ghost',f:'CM()'}]);
}

// ══ R3 Кланы 2.0: Бездна · Здания · Войны (внутри клан-модалки) ══════════════
// UX-аудит: названия вкладок ничего не объясняли новичку + переключение между
// ними требовало полного возврата в карточку клана. Теперь у каждой кнопки
// однословная подсказка, а сама панель встроена в шапку всех трёх экранов —
// прямой переход Бездна↔Здания↔Войны без промежуточного «↩ К клану».
function _clan2NavHtml(active){
  const item=(key,icon,label,sub,fn)=>
    `<button class="btn ${active===key?'btn-gold':'btn-ghost'}" onclick="${fn}">${icon} ${label}<span class="clan2-nav-sub">${sub}</span></button>`;
  return `<div class="clan2-nav">
    ${item('abyss','🌀','Бездна','копать клетки','c2Abyss()')}
    ${item('build','🏗','Здания','тратить 🔷','c2Buildings()')}
    ${item('war','⚔️','Войны','отбить узел','c2War()')}
  </div>`;
}
const C2_CELL_ICO={empty:'▫️',chest:'📦',monster:'👹',boss:'👑',exit:'🚪'};
let _c2Ab=null;
function c2Abyss(){
  const b=el('mb'); if(b)b.innerHTML='<div class="loader">Загрузка Бездны...</div>';
  api('/clans2/abyss').then(d=>{
    _c2Ab=d;
    if(d.active_battle){ _btBackFn=c2Abyss; _btRender(d.active_battle); return; }
    _c2RenderAbyss();
  }).catch(e=>{if(b)b.innerHTML=`<div class="err">${e}</div>`;});
}
function _c2RenderAbyss(){
  const b=el('mb'); if(!b||!_c2Ab) return;
  const d=_c2Ab;
  const cells=d.grid.map(c=>{
    if(c.state==='open') return `<div class="ab-cell open">${C2_CELL_ICO[c.type]||'▫️'}</div>`;
    if(c.state==='reachable') return `<button class="ab-cell reach" onclick="c2Open(${c.i},this)">${c.type?C2_CELL_ICO[c.type]:'❔'}</button>`;
    return `<div class="ab-cell fog"></div>`;
  }).join('');
  const gateOk=d.cp>=d.cp_gate;
  // Боёвка 3.0: клетки открываются отрядом юнитов (дневной лимит), питомцы не нужны
  const squad=(d.squad||[]).map(s=>`<span class="bk-chip">${s.emoji} ${esc(s.name)} · ур.${s.level}</span>`).join('');
  const squadHtml = squad
    ? `<div class="looks-slot-t">⚔️ Твой отряд (⚡${fmt(d.squad_cp||0)})</div><div class="bk-chips">${squad}</div>`
    : `<div class="cx-dim" style="font-size:11px;margin-top:6px">Отряда нет — монстров и босса бить некому.</div>
       <button class="btn btn-sm btn-gold" style="margin-top:6px" onclick="goTo('arena','barracks')">🏰 Собрать отряд в Казарме</button>`;
  b.innerHTML=`
    ${_clan2NavHtml('abyss')}
    <div class="looks-hint">🌀 Этаж <b>${d.floor}</b> · неделя ${d.week} · открытий сегодня: <b>${d.opens_left}/${d.opens_max}</b> (📡 Радар клана добавляет).
      Гейт этажа: ⚡${fmt(d.cp_gate)} ${gateOk?'✅':`❌ (у тебя ${fmt(d.cp)})`}
      ${d.key_found?' · 🗝 ключ найден':''}</div>
    <div class="ab-legend">🌫 туман · ❔ доступно (открой, узнаешь что там) ·
      📦 сундук: ${(d.loot?.chest||[2,6]).join('–')} 🔷 ·
      👹 монстры (бой отрядом): ${(d.loot?.monster||[3,8]).join('–')} 🔷 ·
      👑 босс: ${(d.loot?.boss||[15,25]).join('–')} 🔷 + 🗝 ключ + ${(d.loot?.boss_unit_shards||[3,5]).join('–')} ◈ осколков юнита ·
      🚪 выход этажа</div>
    <div class="ab-grid">${cells}</div>
    ${squadHtml}
    ${d.key_found?`<button class="btn btn-gold btn-full" style="margin-top:8px" onclick="c2NextFloor()">⬇️ Спуститься на этаж ${d.floor+1}</button>`:''}
    <button class="btn btn-ghost btn-full" style="margin-top:6px" onclick="openClansModal()">↩ К клану</button>`;
}
function c2Open(cell, btn){
  if(btn) btn.disabled=true;
  _btBackFn=c2Abyss;
  api('/clans2/abyss/open',{method:'POST',body:JSON.stringify({cell})})
    .then(r=>{
      if(r.battle){ _haptic('medium'); _btRender(r.battle); return; }
      if(r.type==='chest'){ _haptic('success'); toast(`📦 +${r.shards} 🔷 (${r.split.treasury} в казну)`); }
      else if(r.exit_found){ _haptic('success'); toast('🚪 Найден проход на следующий этаж!'); }
      else _haptic('light');
      // EPIC5: рассеивание тумана — сперва проигрываем fade на самой клетке,
      // и только потом тянем свежую карту (полный ре-рендер иначе обрежет анимацию).
      if(btn){ btn.classList.add('ab-cell-clearing'); setTimeout(c2Abyss, 480); }
      else c2Abyss();
    })
    .catch(e=>{toast(e,false); if(btn)btn.disabled=false;});
}
function c2NextFloor(){
  api('/clans2/abyss/next-floor',{method:'POST'})
    .then(r=>{toast(`⬇️ Этаж ${r.floor}!`); c2Abyss();})
    .catch(e=>toast(e,false));
}
function c2Buildings(){
  const b=el('mb'); if(b)b.innerHTML='<div class="loader">Загрузка...</div>';
  api('/clans2/overview').then(d=>{
    const cards=d.buildings.map(x=>`<div class="clan-bld">
      <div class="clan-bld-ico">${x.emoji}</div>
      <div class="clan-bld-body">
        <div class="clan-bld-name">${esc(x.name)} · ур.${x.level}/${x.max}</div>
        <div class="clan-bld-eff">${esc(x.desc)}</div>
      </div>
      ${x.next_cost?`<button class="btn btn-sm btn-gold" onclick="c2Build('${x.key}',this)">↑ ${x.next_cost} 🔷</button>`
                   :'<span class="cx-dim">★ макс</span>'}
    </div>`).join('');
    const log=(d.log||[]).map(l=>`<div class="lot-live-row">${esc(l.text)}</div>`).join('');
    el('mb').innerHTML=`
      ${_clan2NavHtml('build')}
      <div class="looks-hint">🏦 Казна: <b>${fmtF(d.treasury_shards)}</b>/${fmt(d.treasury_cap)} 🔷 · <b>${fmt(d.treasury_mora)}</b> 🪙 (доход узлов) · твоя роль: <b>${d.role}</b></div>
      <div class="clan-blds">${cards}</div>
      ${log?`<div class="looks-slot-t" style="margin-top:10px">📜 Лента клана</div><div class="bt-log">${log}</div>`:''}
      <button class="btn btn-ghost btn-full" style="margin-top:8px" onclick="openClansModal()">↩ К клану</button>`;
  }).catch(e=>{if(el('mb'))el('mb').innerHTML=`<div class="err">${e}</div>`;});
}
function c2Build(key, btn){
  if(btn)btn.disabled=true;
  api('/clans2/build',{method:'POST',body:JSON.stringify({key})})
    .then(r=>{_haptic('success'); toast(`🏗 ур.${r.level} (−${r.paid} 🔷)`); c2Buildings();})
    .catch(e=>{toast(e,false); if(btn)btn.disabled=false;});
}
function c2War(){
  const b=el('mb'); if(b)b.innerHTML='<div class="loader">Загрузка узлов...</div>';
  api('/clans2/war/nodes').then(d=>{
    const rows=d.nodes.map(n=>{
      const mine=n.owner&&n.owner.clan_id===d.my_clan_id;
      const owner=n.owner?`${esc(n.owner.name)} [${esc(n.owner.tag)}]`:'— ничей —';
      const shield=n.shield_left_sec>0?` · 🛡 ${Math.ceil(n.shield_left_sec/3600)}ч`:'';
      let act='';
      if(n.war){
        const pct=n.wall_hp_max?Math.min(100,Math.round(n.war.damage_total/n.wall_hp_max*100)):0;
        act=`<div class="bt-bar"><div class="bt-fill hp en" style="width:${pct}%"></div></div>
          <div class="bt-num">Штурм: ${fmt(n.war.damage_total)}/${fmt(n.wall_hp_max)} · ${Math.ceil(n.war.remaining_sec/3600)}ч</div>
          ${n.war.attacker_clan_id===d.my_clan_id?`<button class="btn btn-sm btn-red btn-full" onclick="c2WarAttack(${n.war.id})">⚔️ Атаковать стену</button>`:''}`;
      } else if(!mine && n.shield_left_sec<=0){
        // UX-аудит: кнопка объявления войны раньше молча пропадала для
        // Бойца/Казначея без единого слова объяснения — теперь виден и повод.
        act=['owner','warlord'].includes(d.my_role||'')
          ? `<button class="btn btn-sm btn-ghost btn-full" onclick="c2Declare(${n.id},this)">⚔️ Война (${fmt(d.declare_cost)} 🪙 казны)</button>`
          : `<div class="cx-dim" style="font-size:10px;margin-top:3px">🔒 Войну объявляет только Владыка или Воевода</div>`;
      }
      return `<div class="g2-floor"><div style="flex:1">
          <div class="g2-fn">${esc(n.name)}${mine?' 🏰':''}${shield}</div>
          <div class="bt-num">Владелец: ${owner} · стена ${fmt(n.wall_hp_max)} HP</div>${act}
        </div></div>`;
    }).join('');
    el('mb').innerHTML=`
      ${_clan2NavHtml('war')}
      <div class="looks-hint">🏰 Узлы дают 2 000 🪙/день в казну владельца. Война: 24ч на пробитие стены, ${d.attacks_per_day} атаки/день на бойца.</div>
      ${rows}
      <button class="btn btn-ghost btn-full" style="margin-top:8px" onclick="openClansModal()">↩ К клану</button>`;
  }).catch(e=>{if(el('mb'))el('mb').innerHTML=`<div class="err">${e}</div>`;});
}
function c2Declare(nodeId, btn){
  if(btn)btn.disabled=true;
  api('/clans2/war/declare',{method:'POST',body:JSON.stringify({node_id:nodeId})})
    .then(()=>{_haptic('heavy'); toast('⚔️ Война объявлена! 24 часа на штурм.'); c2War();})
    .catch(e=>{toast(e,false); if(btn)btn.disabled=false;});
}
function c2WarAttack(warId){
  _btBackFn=c2War;
  api('/clans2/war/attack',{method:'POST',body:JSON.stringify({war_id:warId})})
    .then(r=>{_haptic('medium'); _btRender(r.battle);})
    .catch(e=>toast(e,false));
}

// ── admin_audit B1: форма апелляции для забаненного (открывается по 403) ──────
let _banAppealOpen=false;
function openBanAppealModal() {
  if(_banAppealOpen) return;
  _banAppealOpen=true;
  api('/appeals/my').then(d=>{
    const s=d.sanction;
    const thread=(d.thread||[]).map(m=>
      `<div style="margin:5px 0;padding:6px 8px;border-radius:8px;background:${m.is_staff?'var(--dim)':'rgba(94,155,240,.12)'};font-size:12px">
        <div style="font-size:10px;color:var(--muted)">${m.is_staff?'👮 Модерация':'🙋 Вы'}</div>
        ${esc(m.text||'(фото)')}${(m.photos||[]).length?' 📎':''}
      </div>`).join('');
    const until=s&&s.expires_at?new Date(s.expires_at).toLocaleDateString():'бессрочно';
    OM('⛔ Доступ ограничен — подать апелляцию',
      `<div style="font-size:12px;color:var(--muted);margin-bottom:6px">
        ${s?`Санкция: <b>${s.type==='ban'?'глобальный бан':'ограничение'}</b> (${until}).<br>Причина: ${esc(s.reason||'не указана')}`:'Активная санкция не найдена.'}
       </div>
       ${thread?`<div style="max-height:30vh;overflow:auto;margin-bottom:6px">${thread}</div>`:''}
       <textarea id="ban-apl-text" class="num-input" style="min-height:80px;resize:vertical;margin:0 0 6px" placeholder="Почему санкцию стоит пересмотреть…" maxlength="9999"></textarea>
       <input id="ban-apl-file" type="file" accept="image/*" class="num-input" style="margin:0 0 4px;padding:6px"/>
       <div style="font-size:10px;color:var(--muted)">Можно и в ЛС бота: <code>бот апелляция, текст</code> (фото — с подписью). Диалог общий.</div>`,
      [{l:'📨 Отправить',c:'btn-gold',f:'_banAppealSend()'},{l:'Закрыть',c:'btn-ghost',f:'_banAppealClose()'}]);
  }).catch(()=>{_banAppealOpen=false;});
}
function _banAppealClose(){_banAppealOpen=false;CM();}
function _banAppealSend() {
  const text=el('ban-apl-text')?.value.trim()||'';
  const f=el('ban-apl-file')?.files&&el('ban-apl-file').files[0];
  const send=(photoIds)=>api('/appeals/message',{method:'POST',body:JSON.stringify({text,photo_ids:photoIds||[]})})
    .then(r=>{toast(r.message||'📨 Отправлено');_banAppealOpen=false;CM();})
    .catch(e=>toast(e,false));
  if(!text&&!f) return toast('Напишите текст или приложите фото',false);
  if(!f) return send([]);
  const reader=new FileReader();
  reader.onload=()=>{
    const b64=String(reader.result).split(',')[1]||'';
    api('/appeals/photo',{method:'POST',body:JSON.stringify({data_b64:b64,filename:f.name||'photo.jpg'})})
      .then(r=>send([r.file_id]))
      .catch(e=>toast(e,false));
  };
  reader.readAsDataURL(f);
}

// ═══ «Что нового» — страница обновлений + бейдж в шапке ═══════════════════════
// Данные: /updates.json (владелец правит FastAPI/static/updates.json как текст).
// «Прочитано» хранится на сервере (users.whatsnew_seen_id, через /profile/me +
// POST /profile/whatsnew-seen) — badge гаснет, когда игрок открыл ленту. Раньше
// хранилось только в localStorage: Telegram WebView не гарантирует его сохранность
// (чистка кэша/переустановка/долгий простой), из-за чего лента периодически
// «сбрасывалась» и всё показывалось заново «Новое», у многих игроков. localStorage
// остаётся только как разовый фолбэк миграции для игроков, у кого ещё нет
// server-side значения (см. _wnSeenId). Записи newest-first; новее прочитанной — «Новое».
let _wnData = null;                         // кэш ленты (массив записей)
const _WN_SEEN_KEY = 'wn_seen_id';
const _WN_MONTHS = ['января','февраля','марта','апреля','мая','июня','июля',
  'августа','сентября','октября','ноября','декабря'];
const _WN_TAG = {
  'Фича':    {cls:'wn-tag--feat',    ic:'✨'},
  'Фикс':    {cls:'wn-tag--fix',     ic:'🔧'},
  'Контент': {cls:'wn-tag--content', ic:'📦'},
  'Баланс':  {cls:'wn-tag--balance', ic:'⚖️'},
};

function _wnFetch(){
  if (_wnData) return Promise.resolve(_wnData);
  return api('/updates.json').then(d => { _wnData = (d && d.updates) || []; return _wnData; });
}
function _wnSeenId(){
  const server = _profileData && _profileData.whatsnew_seen_id;
  if (server) return server;
  // Разовая миграция: сервер ещё не знает (старый игрок/только что выкатили фикс) —
  // используем локальное значение один раз, дальше сервер уже источник правды.
  try { return localStorage.getItem(_WN_SEEN_KEY) || ''; } catch(_) { return ''; }
}
function _wnLatestId(list){ return (list && list.length) ? list[0].id : ''; }
function _wnNewCount(list){
  const seen = _wnSeenId();
  const idx = (list||[]).findIndex(u => u.id === seen);
  return idx === -1 ? (list||[]).length : idx;   // seen не найдена → всё новое
}
// Бейдж в шапке (вызывается из loadProfile). Тихо игнорит ошибки сети.
function checkWhatsNewBadge(){
  _wnFetch().then(list => {
    const unseen = _wnNewCount(list) > 0;
    const dot = el('whatsnew-dot'), btn = el('whatsnew-btn');
    if (dot) dot.hidden = !unseen;
    if (btn) btn.classList.toggle('has-new', unseen);
  }).catch(()=>{});
}
function _wnMarkSeen(list){
  const latest = _wnLatestId(list);
  if (latest) {
    if (_profileData) _profileData.whatsnew_seen_id = latest;   // сразу видно этой же сессии
    try { localStorage.setItem(_WN_SEEN_KEY, latest); } catch(_){}   // офлайн-подстраховка
    api('/profile/whatsnew-seen', {method:'POST', body: JSON.stringify({seen_id: latest})}).catch(()=>{});
  }
  const dot = el('whatsnew-dot'), btn = el('whatsnew-btn');
  if (dot) dot.hidden = true;
  if (btn) btn.classList.remove('has-new');
}
function _wnDate(iso){
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso||'');
  if(!m) return esc(iso||'');
  return `${+m[3]} ${_WN_MONTHS[+m[2]-1]||''}`;
}
function _wnReEsc(s){ return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'); }
// Подсветка терминов в тексте: один проход по esc-строке (не перескан вставленных
// span), длинные термины раньше — иначе короткий съест часть длинного.
function _wnLinkTerms(text, terms){
  let html = esc(text||'');
  if(!terms || !terms.length) return html;
  const map = {};
  terms.forEach(t => { if(t && t.term) map[esc(t.term)] = t.definition || ''; });
  const keys = Object.keys(map).sort((a,b) => b.length - a.length);
  if(!keys.length) return html;
  const re = new RegExp('(' + keys.map(_wnReEsc).join('|') + ')', 'g');
  return html.replace(re, m =>
    `<span class="wn-term" data-def="${esc(map[m]).replace(/"/g,'&quot;')}">${m}</span>`);
}
function _wnCard(u, isNew){
  const tg = _WN_TAG[u.tag] || {cls:'wn-tag--feat', ic:'•'};
  const terms = u.terms || [];
  const details = (u.details||[]).map(d => `<li>${_wnLinkTerms(d, terms)}</li>`).join('');
  return `<div class="wn-card${isNew?' wn-card--new':''}">
    <button class="wn-card-head" onclick="_wnToggle(this)">
      <div class="wn-card-meta">
        <span class="wn-tag ${tg.cls}">${tg.ic} ${esc(u.tag||'')}</span>
        <span class="wn-date">${_wnDate(u.date)}</span>
        ${isNew?'<span class="wn-new-badge">● Новое</span>':''}
      </div>
      <div class="wn-card-title">${esc(u.title||'')}</div>
      <div class="wn-card-sum">${_wnLinkTerms(u.summary||'', terms)}</div>
      ${details?'<span class="wn-chevron">▾</span>':''}
    </button>
    ${details?`<div class="wn-card-body"><ul class="wn-details">${details}</ul></div>`:''}
  </div>`;
}
function _wnToggle(btn){ const c = btn.closest('.wn-card'); if(c) c.classList.toggle('wn-card--open'); }

// Мини-поповер с объяснением термина (маленький, на месте — не модалка).
function _wnClosePop(){ const p = document.querySelector('.wn-pop'); if(p) p.remove(); }
function _wnTermTap(e){
  const t = e.target.closest('.wn-term');
  if(!t){ _wnClosePop(); return; }
  e.stopPropagation();
  _wnClosePop();
  const pop = document.createElement('div');
  pop.className = 'wn-pop';
  pop.innerHTML = `<div class="wn-pop-term">${esc(t.textContent)}</div>
    <div class="wn-pop-def">${esc(t.getAttribute('data-def')||'')}</div>`;
  document.body.appendChild(pop);
  const r = t.getBoundingClientRect();
  const pw = pop.offsetWidth;
  let left = r.left + window.scrollX;
  const maxLeft = window.innerWidth - pw - 10;
  if(left > maxLeft) left = maxLeft;
  if(left < 10) left = 10;
  pop.style.left = left + 'px';
  pop.style.top = (r.bottom + window.scrollY + 6) + 'px';
  setTimeout(() => document.addEventListener('click', _wnClosePop, { once: true }), 0);
}
document.addEventListener('click', _wnTermTap);

function openWhatsNew(){ switchPage('news'); }
function loadWhatsNew(){
  const box = el('pg-news'); if(!box) return;
  box.innerHTML = '<div class="loader">Загрузка…</div>';
  _wnFetch().then(list => {
    const head = `<div class="wn-head">
        <button class="wn-back" onclick="goTo('profile')" aria-label="Назад">‹</button>
        <div class="wn-htitle">📣 Что нового</div>
      </div>`;
    if(!list.length){
      box.innerHTML = head + `<div class="empty-state"><div class="es-icon">📣</div>
        <div class="es-title">Пока тихо</div><div class="es-sub">Обновления появятся здесь</div></div>`;
      return;
    }
    const newCount = _wnNewCount(list);
    const cards = list.map((u,i) => _wnCard(u, i < newCount)).join('');
    box.innerHTML = head + `<div class="wn-list">${cards}</div>`;
    _wnMarkSeen(list);   // открыл ленту → всё прочитано, badge гаснет
  }).catch(e => { box.innerHTML = `<div class="err" style="margin:12px">${e}</div>`; });
}
