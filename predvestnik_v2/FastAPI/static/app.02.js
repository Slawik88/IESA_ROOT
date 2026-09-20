// ── Profile ───────────────────────────────────────────────────────────────────
// switchPro() defined later with marriage + wallet tabs
function _profileEsc(value){ return String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
function _profileCss(value){ return String(value||'').split(/\s+/).filter(token=>/^[A-Za-z0-9_-]{1,80}$/.test(token)).join(' '); }
function renderProfileShowcase(data, cosmetics, options={}) {
  const d=data||{}, c=cosmetics||{};
  const item=slot=>(c[slot]&&typeof c[slot]==='object'?c[slot]:null);
  const title=typeof c.title==='object'?c.title:(c.title?{text:c.title,css:c.title_css}:null);
  const frame=item('avatar_frame'), halo=item('avatar_halo'), bg=item('profile_bg'), fx=item('card_fx'), glow=item('name_glow');
  const level=Math.max(1,Number(d.account_level)||1), xp=Math.max(0,Number(d.xp_into)||0), xpNeed=Math.max(1,Number(d.xp_to_next)||Number(d.xp_per_level)||1);
  const xpPercent=Math.min(100,Math.round(xp/xpNeed*100));
  const wallet=(d.balances&&typeof d.balances==='object')?d.balances:d;
  const avatar=d.is_vip?'👑':'🔮', titleText=title?(title.text||title.name):'';
  const avatarImage=typeof d.avatar==='string'&&/^data:image\/(?:png|jpe?g|webp);base64,/i.test(d.avatar)
    ?`<img src="${_profileEsc(d.avatar)}" alt="" decoding="async">`:avatar;
  const publicName=String(d.display_name||'').trim();
  const profileName=String(d.username||'Игрок').trim()||'Игрок';
  const shownName=publicName||(profileName.startsWith('@')?profileName:`@${profileName.replace(/^@+/, '')}`);
  const lineage=_profileCss(c.composition?.dominant_lineup||c.lineage?.id||bg?.lineup||frame?.lineup||halo?.lineup||fx?.lineup||'');
  // The lead item names the identity accent, while both independently owned
  // classes remain on the avatar.  The paired CSS assigns frame and halo to
  // separate orbits; dropping the ambient class would make a saved item vanish.
  const accent=(c.composition?.identity?.lead_slot==='avatar_halo'?halo:frame)||halo;
  const identityCss=[frame?.css,halo?.css].map(_profileCss).filter(Boolean).join(' ');
  const accentName=accent?.name||bg?.name||titleText||'Базовый образ';
  const cardClass=`hero profile-showcase-card ${options.compact?'profile-showcase-card--fitting':''} ${_profileCss(bg?.css)} ${lineage?`profile-tone-${lineage}`:''}`;
  const caption=options.caption||'Личный профиль';
  const stageTag=options.openLooks?'button':'div';
  const stageAttrs=options.openLooks
    ?`type="button" onclick="openLooksModal()" aria-label="Открыть примерочную"`
    :`aria-label="${_profileEsc(caption)}"`;
  return `<div class="${cardClass}">
    <div class="profile-showcase-head">
      <div class="profile-copy"><div class="pname ${_profileCss(glow?.css)}">${_profileEsc(shownName)}</div>
      <div class="prank">${_profileEsc(d.rank||caption)}</div>${titleText?`<div class="ptitle ${_profileCss(title?.css)}">${_profileEsc(titleText)}</div>`:''}</div>
      ${options.openLooks?'<button type="button" class="profile-looks-link" onclick="openLooksModal()">Примерочная</button>':''}
    </div>
    <div class="profile-showcase-main">
      <${stageTag} class="character-showcase-area hero ${_profileCss(bg?.css)}" ${stageAttrs}>
        ${fx?`<span class="card-fx ${_profileCss(fx.css)}" aria-hidden="true"></span>`:''}
        <span class="character-showcase-portrait ava ${identityCss?'profile-identity-accent':''} ${identityCss}" aria-hidden="true">${avatarImage}</span>
        <span class="character-showcase-caption" aria-hidden="true"><strong>${_profileEsc(caption)}</strong><small>${_profileEsc(accentName)}</small></span>
      </${stageTag}>
      <aside class="player-data-rail player-data-rail--compact" aria-label="Основные показатели игрока">
        <div class="player-rail-item player-rail-item--level"><span class="player-rail-kicker">Уровень</span><strong>LV${level}</strong><div class="hero-xp"><div class="xp-bar"><div class="xp-fill" style="width:${xpPercent}%"></div></div><div class="xp-lbl"><span>${fmt(xp)} XP</span><span>до следующего</span></div></div></div>
        <div class="player-rail-item"><span class="player-rail-kicker">🔥 Серия</span><strong>${fmt(d.streak||0)}</strong><small>лучший результат</small></div>
        <div class="player-rail-item"><span class="player-rail-kicker">🏅 Достижения</span><strong>${fmt(d.achievements||0)}</strong><small>открыто</small></div>
      </aside>
    </div>
    <div class="stats profile-resource-rail" aria-label="Ресурсы игрока">
      <div class="stat"><div>🪙</div><div class="sv">${fmt(wallet.mora||0)}</div><div class="sl">Мора</div></div>
      <div class="stat"><div>💎</div><div class="sv">${fmtF(wallet.diamonds||0)}</div><div class="sl">Алмазы</div></div>
      ${options.openLooks?`<button type="button" class="stat profile-zarniki-topup" onclick="openZarnikiTopup()" aria-label="Пополнить Зарники. Баланс ${fmt(wallet.zarniki||0)}"><div>✨</div><div class="sv">${fmt(wallet.zarniki||0)}</div><div class="sl">+ Пополнить</div></button>`:`<div class="stat"><div>✨</div><div class="sv">${fmt(wallet.zarniki||0)}</div><div class="sl">Зарники</div></div>`}
      <div class="stat"><div>🌑</div><div class="sv">${fmt(wallet.dark_mora||0)}</div><div class="sl">Тёмная мора</div></div>
      <div class="stat"><div>◈</div><div class="sv">${fmt(wallet.echo_shards||0)}</div><div class="sl">Осколки Эха</div></div>
    </div>
  </div>`;
}
function _profileDate(value){
  if(!value) return '—';
  const parsed=new Date(value);
  return Number.isNaN(parsed.getTime())?_profileEsc(String(value).replace('T',' ').slice(0,16)):parsed.toLocaleDateString('ru-RU');
}
function _profileDuration(ms){
  if(ms===null||ms===undefined) return '—';
  const seconds=Math.max(0,Math.round(Number(ms)/1000));
  return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;
}
function _profileSanctions(data){
  const sanctions=data?.sanctions||{}, active=sanctions.active_global;
  const activeHtml=active
    ?`<div class="profile-detail-alert"><b>${_profileEsc(active.label||active.type||'Ограничение')}</b>${active.reason?`<span>${_profileEsc(active.reason)}</span>`:''}${active.expires_at?`<small>до ${_profileDate(active.expires_at)}</small>`:''}</div>`
    :'<p class="profile-detail-muted">Активных глобальных ограничений нет.</p>';
  const history=(sanctions.history||[]).map(item=>`<li><b>${_profileEsc(item.label||item.type||'Ограничение')}</b>${item.reason?` — ${_profileEsc(item.reason)}`:''}<small>${_profileDate(item.created_at)}${item.revoked_at?' · снято':''}${item.expires_at?` · до ${_profileDate(item.expires_at)}`:''}</small></li>`).join('')||'<li>История ограничений пуста.</li>';
  return `<section class="profile-detail-section"><h3>Санкции</h3>${activeHtml}<div class="profile-detail-pairs"><span>Предупреждения в чатах</span><b>${fmt(sanctions.chat_warning_total||0)}</b><span>Активный мут</span><b>${sanctions.chat_mute_until?_profileDate(sanctions.chat_mute_until):'Нет'}</b></div><details class="profile-history"><summary>История санкций</summary><ul>${history}</ul></details></section>`;
}
function renderProfileDetails(data,{owner=false}={}){
  const d=data||{}, games=d.game_results||{}, rhythm=games.rhythm||{}, mines=games.minesweeper||{}, mafia=games.mafia||{};
  const best=mines.best_ms||{};
  const unranked=owner&&Number(rhythm.personal_unranked_runs)>0
    ?`<small>${fmt(rhythm.personal_unranked_runs)} личных забегов не участвуют в рейтинге</small>`:'';
  const gameCards=`<div class="profile-game-grid">
    <article><b>ᚱ Ритм</b><strong>${rhythm.best_verified_score==null?'—':fmt(rhythm.best_verified_score)}</strong><span>лучший подтверждённый счёт</span><small>${fmt(rhythm.verified_runs||0)} подтверждённых забегов</small>${unranked}</article>
    <article><b>▦ Сапёр</b><strong>${fmt(mines.wins||0)} / ${fmt(mines.played||0)}</strong><span>победы / партии</span><small>Лучшее: ${_profileDuration(best.easy)} · ${_profileDuration(best.normal)} · ${_profileDuration(best.hard)}</small></article>
    <article><b>◈ Мафия</b><strong>${fmt(mafia.wins||0)} / ${fmt(mafia.played||0)}</strong><span>победы / завершённые матчи</span><small>Только завершённые партии</small></article>
  </div>`;
  const paths=d.achievement_paths?.families||[];
  const achievementRows=paths.map(path=>`<li><b>${_profileEsc(path.title||path.id)}</b><span>ур. ${fmt(path.level||0)} / ${fmt(path.max_level||40)} · событий ${fmt(path.completed_events||0)} · недель ${fmt(path.active_weeks||0)}</span></li>`).join('')||'<li>Прогресс достижений пока не начат.</li>';
  const pets=(d.pets||[]).map(pet=>`<li><b>${pet.active?'● ':''}${_profileEsc(pet.name||'Питомец')}</b><span>${_profileEsc(pet.rarity||'')}${pet.level?` · ур. ${fmt(pet.level)}`:''}${pet.active?' · активный':''}</span></li>`).join('')||'<li>Питомцев пока нет.</li>';
  const clan=d.clan?`${_profileEsc(d.clan.emblem||'')} ${_profileEsc(d.clan.name||d.clan.tag||'Клан')}`.trim():'Нет';
  const publicVip=!owner&&d.vip?`<span>VIP</span><b>${_profileEsc(d.vip.label||d.vip.tier||'Активен')} · ${fmt(d.vip.days_left||0)} дн.</b>`:'';
  return `<section class="profile-detail-section"><h3>Утверждённые игры</h3>${gameCards}</section>
    <section class="profile-detail-section"><h3>Прогресс и достижения</h3><div class="profile-detail-pairs"><span>Сообщения во всех чатах</span><b>${fmt(d.messages_all_time||0)}</b><span>Уровни текущих достижений</span><b>${fmt(d.achievement_paths?.total_levels||0)}</b><span>В проекте с</span><b>${_profileDate(d.joined_date)}</b></div><ul class="profile-collection">${achievementRows}</ul></section>
    <section class="profile-detail-section"><h3>Социальный профиль</h3><div class="profile-detail-pairs">${publicVip}<span>Статус</span><b>${_profileEsc(d.rank||'Игрок')}</b>${owner?'':`<span>Клан</span><b>${clan}</b>`}<span>Партнёр</span><b>${_profileEsc(d.partner||'Нет')}</b></div><ul class="profile-collection">${pets}</ul></section>
    ${_profileSanctions(d)}`;
}
function _profileVipCard(vip){
  if(!vip)return `<section class="profile-vip-card profile-vip-card--inactive"><span aria-hidden="true">◇</span><div><small>Статус аккаунта</small><b>Обычный профиль</b><p>VIP сейчас не активен</p></div></section>`;
  const expires=vip.expires_at?_profileDate(vip.expires_at):'';
  return `<section class="profile-vip-card" aria-label="VIP активен, осталось ${fmt(vip.days_left||0)} дней"><span class="profile-vip-gem" aria-hidden="true">✦</span><div><small>VIP активен</small><b>${_profileEsc(vip.label||vip.tier||'VIP')}</b><p>${fmt(vip.days_left||0)} дн. осталось${expires?` · до ${expires}`:''}</p></div><strong>${fmt(vip.days_left||0)}<small>дней</small></strong></section>`;
}
function _profileCompensationCard(c,userId){
  if(!c)return'';
  const total=Number(c.zarniki_added)||0,summary=c.source_summary||{},old=summary.old_balances||{},counts=summary.retired_counts||{};
  const sources=[['🎨','Косметика',c.cosmetics_zarniki],['🌌','Темы',c.themes_zarniki],['🎁','Донат-предметы',c.donate_inventory_zarniki],['↺','Обмен Зарников',c.retired_exchange_zarniki]].filter(x=>Number(x[2])>0);
  const retired=[['Предметы',counts.inventory],['Питомцы',counts.pets],['Боевые единицы',counts.units],['Реликвии',counts.relics]].filter(x=>Number(x[1])>0);
  const key=`predvestnik-compensation-seen:${userId}:${c.snapshot_id}`;
  let first=false;try{first=!localStorage.getItem(key);if(first)localStorage.setItem(key,'1');}catch(_){ }
  return `<section class="migration-card${first?' is-animating':''}" data-compensation-card>
    <header><span aria-hidden="true">✦</span><div><small>Переход завершён</small><h3>Ваши ресурсы сохранены</h3></div><button type="button" onclick="replayCompensationAnimation(this)" aria-label="Повторить анимацию переноса">↻</button></header>
    <p>Старые системы закрыты, но их ценность не пропала. Вот ваша личная квитанция переноса.</p>
    <div class="migration-result"><span>✨</span><div><small>Компенсация в Зарниках</small><b>+${fmt(total)}</b><p>${fmt(c.zarniki_carry||0)} прежних Зарников сохранены отдельно</p></div></div>
    ${sources.length?`<div class="migration-sources">${sources.map(x=>`<div class="migration-source"><span>${x[0]}</span><b>${_profileEsc(x[1])}</b><small>→ ${fmt(x[2])} ✨</small></div>`).join('')}</div>`:''}
    <div class="migration-balance-flow"><div><span>🪙 Мора</span><b>${fmt(old.mora||0)} <i>→</i> ${fmt(c.mora_compensation||0)}</b><small>по снимку переноса</small></div><div><span>💎 Алмазы</span><b>${fmt(old.diamonds||0)} <i>→</i> ${fmt(c.diamonds_compensation||0)}</b><small>по снимку переноса</small></div></div>
    ${retired.length?`<div class="migration-retired"><small>Старый прогресс учтён</small>${retired.map(x=>`<span><b>${fmt(x[1])}</b> ${_profileEsc(x[0])}</span>`).join('')}</div>`:''}
    <div class="migration-awards"><div><span>👑</span><b>${fmt(c.vip_preserved_days||0)}</b><small>дн. VIP сохранено</small></div><div><span>✦</span><b>+${fmt(c.vip_bonus_days||0)}</b><small>дн. VIP за прогресс</small></div><div><span>◈</span><b>${fmt(c.legacy_score||0)}</b><small>баллов учтено</small></div></div>
    <details><summary>Как рассчитано</summary><p>Обычные предметы, питомцы, боевые единицы, реликвии и старые валюты переведены в общий балл прогресса. По зафиксированному снимку из него рассчитаны ограниченные значения Моры и Алмазов, а оставшаяся ценность — бонусный VIP с уменьшающимся курсом. Действия после снимка сохраняются отдельно, поэтому текущий кошелёк может отличаться. Тёмная Мора (${fmt(old.dark_mora||0)}) и старые кристаллы (${fmt(old.crystals||0)}) больше не являются активными валютами.</p></details>
  </section>`;
}
window.replayCompensationAnimation=function(button){const card=button?.closest('[data-compensation-card]');if(!card)return;card.classList.remove('is-animating');void card.offsetWidth;card.classList.add('is-animating');};
function loadProfile() {
  el('pro-main').innerHTML='<div class="sk" style="height:120px;border-radius:var(--r);margin-bottom:8px"></div><div class="sk" style="height:60px;border-radius:var(--r)"></div>';
  return api('/profile/me').then(d=>{
    if(!d || typeof d !== 'object') throw new Error('Неверный формат ответа сервера');
    _cid = _initChatId || d.chats?.[0]?.chat_tg_id || 0;
    if(d.user_id) _uid = d.user_id;
    _profileData = d;
    _applyGlobalSkin(d.global_skin);
    // A profile response is authoritative. Optional decorations must never
    // turn it into the misleading “write the bot to create a profile” state.
    try { _applySysFlags(d.system_flags); } catch (_) {}
    const uid = d.user_id || _uid;
    el('pro-main').innerHTML=`
      ${renderProfileShowcase(d,d.cosmetics,{caption:'Личный профиль',openLooks:true})}

      ${_profileVipCard(d.vip)}
      ${_profileCompensationCard(d.compensation,uid)}

      <div class="profile-card-actions" aria-label="Настройки профиля">
        <button type="button" onclick="openSettingsModal()"><span aria-hidden="true">⚙️</span><span>Настройки</span></button>
        <button type="button" onclick="openPetsV1()"><span aria-hidden="true">🐾</span><span>Питомцы</span></button>
        <button type="button" onclick="openQuestsV1()"><span aria-hidden="true">🧭</span><span>Квесты</span></button>
        ${_sysFlags.content_chests_v1?'<button type="button" onclick="openChestsV1()"><span aria-hidden="true">🗝</span><span>Сундуки</span></button>':''}
        <button type="button" onclick="openAchievementsV1()"><span aria-hidden="true">🏅</span><span>Достижения</span></button>
        <button type="button" onclick="openChatTracker()"><span aria-hidden="true">💬</span><span>Мои чаты</span></button>
      </div>

      ${renderProfileDetails(d,{owner:true})}

      <!-- Главный вход: сейчас здесь только реально доступные форматы. -->
      <div class="qa-row profile-activity-row">
        <button class="qa qa-hot qa-hub" type="button" onclick="goTo('arena','game')" aria-label="Открыть Центр Предвестника и выбрать игру">
          <span class="qa-hub-icon" aria-hidden="true">🎮</span>
          <span class="qa-hub-copy"><strong>Центр Предвестника</strong><small>Ритм · Сапёр · Мафия</small></span>
          <span class="qa-hub-arrow" aria-hidden="true">›</span>
        </button>
      </div>

      <!-- Карточка брака (заполняется loadMarriageCard) -->
      <div id="pro-marriage-card"><div class="sk" style="height:90px;border-radius:var(--r)"></div></div>
      <!-- Карточка ника (заполняется loadNickCard) -->
      <div id="pro-nick-card"></div>
      <div id="wallet-mini"></div>`;
    try { checkWhatsNewBadge(); } catch (_) {}
    try { _tosGate(d); } catch (_) {}
    try { loadMarriageCard(); } catch (_) {}
    try { loadNickCard(); } catch (_) {}
    try { loadWalletMini(); } catch (_) {}
    try { if(!_ws && _uid) connectWS(); } catch (_) {}
    try { updateCurrBar(d); } catch (_) {}
    try { if(!_adminChats) checkAdminAccess(); } catch (_) {}
    try { checkGlobalAccess(); } catch (_) {}
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
  OM('⚙️ Настройки',`
    <div class="set-sec-t">Внешний вид</div>
    ${_globalSkinSettingsHtml()}
    <label style="display:flex;align-items:center;gap:8px;padding:8px 2px;cursor:pointer">
      <input type="checkbox" ${noFx?'checked':''} onchange="_toggleNoFx(this.checked)"/>
      <span style="font-size:12.5px">Отключить анимации косметики</span>
    </label>
    <div class="set-hint">Свечения, рамки и частицы станут статичными — полезно на слабых телефонах.</div>
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
let _globalSkinBusy=false;
function _applyGlobalSkin(state){
  if(typeof window.applyGlobalSkinV1==='function') window.applyGlobalSkinV1(state);
}
function _globalSkinSettingsHtml(){
  const state=_profileData&&_profileData.global_skin;
  if(!state||!Array.isArray(state.items)) return '<div class="set-hint">Скины приложения временно недоступны.</div>';
  const rows=state.items.filter(item=>item.owned||item.price_zarniki).map(item=>{
    const action=item.owned?`_selectGlobalSkin('${item.id}')`:`CM();openLooksModal()`;
    const status=item.active?'Активен':item.selected?'Сохранён':item.owned?'Выбрать':`${item.price_zarniki}✨`;
    return `<button class="skin-choice${item.selected?' selected':''}" type="button" onclick="${action}" ${_globalSkinBusy?'disabled':''}><span><b>${_profileEsc(item.name)}</b><small>${_profileEsc(item.description)}</small></span><em>${status}</em></button>`;
  }).join('');
  const selected=state.items.find(item=>item.id===state.selected_skin_id);
  const gate=!state.vip_active&&selected?.vip_required
    ?'<div class="set-hint">Выбор сохранён. На всём приложении он включится вместе с активным VIP.</div>'
    :'<div class="set-hint">Скин меняет только палитру и фон. Доступ, цены, расположение элементов и правила игр не меняются.</div>';
  return `<div class="skin-settings">${rows}</div>${gate}`;
}
function _selectGlobalSkin(skinId){
  if(_globalSkinBusy) return;
  _globalSkinBusy=true;
  api('/global-skins-v1/select',{method:'POST',body:JSON.stringify({skin_id:skinId})})
    .then(state=>{_globalSkinBusy=false;if(_profileData)_profileData.global_skin=state;_applyGlobalSkin(state);toast(state.active_skin_id===skinId?'Скин приложения включён':'Выбор сохранён до активации VIP');CM();openSettingsModal();})
    .catch(error=>{_globalSkinBusy=false;toast(error,false);});
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
      <p><b>Предвестник</b> собирает разные форматы игры в одном месте: Ритм для реакции, Сапёр для логики и Мафию для живого чата.</p>
      <p>Питомцы, кланы, экономика и косметика будут добавляться по мере утверждения правил. Никаких скрытых преимуществ или обязательных таймеров.</p>
      <p style="color:var(--gold2)">Первый шаг: открой «Игра» и выбери формат под настроение.</p>
    </div>`, [
    {l:'🎮 Открыть игры', c:'btn-gold', f:"CM();goTo('arena','game')"},
    {l:'Позже', c:'btn-ghost', f:'CM()'},
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
    const lead=m.role==='owner';
    const title=m.title?`<div class="top-title">${esc(m.title)}</div>`:'';
    return `<div class="clan-mrow"><span class="clan-mname">${lead?'👑 ':''}${unameLink(m.user_id, m.username, false, m.glow)}${title}</span>
      <span class="clan-mrole">🎖 ${fmtF(m.clan_coins||0)}</span></div>`;
  }).join('');
  return `<div class="clan-card">
      <div class="clan-emblem">${c.emblem||'🛡'}</div>
      <div class="clan-name">${esc(c.name)} <span class="clan-tag">[${esc(c.tag)}]</span></div>
      ${c.description?`<div class="clan-desc">${esc(c.description)}</div>`:''}
      <div class="clan-lvlrow"><span class="clan-lvlbadge">🏛 Основание клана</span>
        <span class="clan-lvlxp">${fmtF(c.foundation_score||c.total_xp||0)} истории</span></div>
      <div class="clan-stats"><div><b>${(c.members||[]).length}</b>/${emax} участников</div>
        <div>роли и состав сохранены</div></div>
    </div>
    ${_clan2NavHtml()}
    <div class="looks-hint">Старая сила и здания не дают преимущества. Совместные цели идут через Союз, а клан сохраняет имя, состав и историю.</div>
    <div class="looks-slot-t" style="margin-top:12px">Состав</div>
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
      <button class="btn btn-full btn-gold" onclick="_clanCreate()">🛡 Основать клан</button>
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
      <span class="clan-txp">${c.member_count}/${c.effective_max||_clansData.max_members} участников · ${fmtF(c.total_xp||0)} истории</span>
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

// Parity registry: bot redirects open the Mini App through
// ?startapp=<section>; lightweight chat surfaces remain in chat and do not
// need a web hop. The start parameter only selects the complex destination.
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
  if(base==='quests'){ run(()=>openQuestsV1()); return; }
  if(base==='achievements'||base==='achievement'){ run(()=>openAchievementsV1()); return; }
  if(base==='pets'){ run(()=>openPetsV1()); return; }
  if(base==='cosmetics'||base==='looks'){ run(()=>openLooksModal()); return; }
  if(base==='public'){
    let ref=''; try{ ref=new URLSearchParams(location.search).get('profile')||''; }catch(e){}
    if(ref) run(()=>openPublicProfile(ref));
    return;
  }
  if(base==='exchange'||base==='exch'){ run(()=>{ switchPage('auction'); setTimeout(()=>{try{swAuction('exch')}catch(e){}},220); }); return; }
  if(base==='crypto'||base==='birzha'){ run(()=>{ switchPage('auction'); setTimeout(()=>{try{swAuction('crypto')}catch(e){}},220); }); return; }
  // БЛОК 36.1: «бот уведомления» раньше вёл на голую вкладку профиля — теперь
  // сразу открывает «⚙️ Настройки» с чекбоксами уведомлений.
  if(base==='notifications'||base==='notifprefs'){ run(()=>{ switchPage('profile'); setTimeout(()=>{try{openSettingsModal()}catch(e){}},260); }); return; }
  if(base==='relics'){ run(()=>{ try{ _goodsTab='dark'; goTo('market','goods'); }catch(e){} }); return; }
  const M={ shop:['market','goods'],goods:['market','goods'],gacha:['market','gacha'],deal:['market','deal'],
    vip:['market','vip'],themes:['profile','themes'],craft:['craft'],inventory:['profile','inv'],inv:['profile','inv'],
    ach:['ach'],achievements:['ach'],zoo:['profile'],bp:['bp'],auction:['auction'],
    arena:['arena'],games:['arena','game'],casino:['arena','game'],
    barracks:['arena','game'],gates:['arena','game'],game:['arena','game'] };
  const t=M[base]; if(t) run(()=>goTo(t[0],t[1]));
}
if(INIT_DATA||sess()||LOCAL_PREPROD_TEST){loadProfile();_loaded.add('profile');setTimeout(loadPendingNotifications,1000);_handleStartParam();}

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
    if(sub) sub.textContent='Профиль Предвестника';
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
  const s = el('pro-showcase-ava'); if (s) s.innerHTML = img;
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
        <div class="cm-desc">Основная валюта для расходников, комиссий и разрешённых торгов.</div>
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
        <div class="cm-desc">Донат-валюта. Можно обменять в пределах общего суточного лимита — без прямой покупки Моры или Алмазов за Stars.</div>
      </div>
    </div>
    <div class="cm-block" style="display:block">
      <div class="cm-name" style="margin-bottom:6px">💱 Обмен Зарников</div>
      <div class="cm-desc" style="margin-bottom:8px">1✨ = 10🪙 или 0,01💎. Лимит: суммарно 50✨ за UTC-день. После успешного обмена услуга оказана и операция необратима.</div>
      <div style="display:flex;gap:6px"><input id="zar-exchange-amount" class="num-input" type="number" inputmode="numeric" min="1" max="50" step="1" placeholder="1–50" style="flex:1;margin:0"><select id="zar-exchange-target" class="num-input" style="width:126px;margin:0"><option value="mora">🪙 Мора</option><option value="diamonds">💎 Алмазы</option></select></div>
      <button id="zar-exchange-submit" class="btn btn-gold btn-full" style="margin-top:7px" onclick="exchangeZarnikiV1()">Обменять</button>
    </div>
  </div>`, [{l:'Закрыть', c:'btn-ghost', f:'CM()'}]);
}

function exchangeZarnikiV1(){
  const input=el('zar-exchange-amount'),button=el('zar-exchange-submit');
  const raw=(input?.value||'').trim(), amount=Number(raw), target=el('zar-exchange-target')?.value;
  if(!/^\d+$/.test(raw)||!Number.isSafeInteger(amount)||amount<1||amount>50)return toast('Введите целое число от 1 до 50.',false);
  if(target!=='mora'&&target!=='diamonds')return toast('Выбери Мору или Алмазы.',false);
  if(button?.dataset.busy==='1')return;
  const key=button?.dataset.requestKey||(globalThis.crypto?.randomUUID?.()||`zar-exchange-${Date.now()}`);
  if(button){button.dataset.busy='1';button.dataset.requestKey=key;button.disabled=true;}
  api('/wallet/exchange-zarniki',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({amount,to:target})}).then(r=>{
    const icon=target==='mora'?'🪙':'💎';toast(`Обменено ${r.zarniki_spent}✨ → ${fmtF(r.amount_received)}${icon}`);refreshCurrBar();
    if(input)input.value='';if(button)delete button.dataset.requestKey;
  }).catch(e=>toast(e,false)).finally(()=>{if(button){delete button.dataset.busy;button.disabled=false;}});
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
// Точечный патч цифр на карточке профиля (Мора/Алмазы/Зарники/Ачивки/Стрик) —
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
}

function plDays(n){n=Math.abs(n)%100;const d=n%10;if(n>10&&n<20)return'дней';if(d===1)return'день';if(d>=2&&d<=4)return'дня';return'дней';}
function loadStreak() {
  el('pro-streak').innerHTML='<div class="loader">Загрузка...</div>';
  api('/streak/calendar').then(d=>{
    const today=new Date().toISOString().slice(0,10);
    const streak=d.streak||0;
    // История присутствия, без награды за объём сообщений.
    const cells=d.calendar.map(day=>{
      const active=Boolean(day.active);
      return `<div class="st-cell l${active?2:0}${day.date===today?' today':''}" title="${day.date}: ${active?'был активен':'нет активности'}"></div>`;
    }).join('');

    el('pro-streak').innerHTML=`
    <div class="st-hero">
      <div class="st-flame">🔥</div>
      <div class="st-big">${streak}</div>
      <div class="st-sub">${plDays(streak)} · сохранённый рекорд старой системы</div>
    </div>

    <div class="card" style="margin-top:10px">
      <div class="card-title">Что изменилось</div>
      <div style="font-size:11px;color:var(--muted);line-height:1.5">Рекорд не стирается и не уменьшается. Сообщения больше не дают Мору, Алмазы или жетоны, а платного восстановления нет.</div>
    </div>

    <div class="card" style="margin-top:10px">
      <div class="card-title">📅 Присутствие в чатах · 60 дней</div>
      <div class="st-heat">${cells}</div>
      <div style="font-size:10px;color:var(--muted);margin-top:7px">Показан только факт активности за день; число сообщений не усиливает награду.</div>
    </div>`;
  }).catch(e=>{el('pro-streak').innerHTML=`<div style="color:var(--red);padding:10px;font-size:12px">${typeof e==='string'?esc(e):'Ошибка загрузки'}</div>`;});
}

// Legacy achievement instructions were deliberately removed: several pointed
// players to retired gacha, gates, spending and message-spam loops.

function loadAch() {
  el('pro-ach').innerHTML='<div class="loader">Загрузка...</div>';
  api('/achievements/').then(payload=>{
    _achRetired=Boolean(payload&&payload.retired);
    _achMessage=payload&&payload.message||'';
    _featData=payload&&payload.chronicle||null;
    _achData=Array.isArray(payload)?payload:(payload.achievements||[]);
    renderAch();
  }).catch(e=>{el('pro-ach').innerHTML=`<div style="color:var(--red);padding:10px;font-size:12px">${e}</div>`;});
}
function setAchSort(s){_achSort=s;renderAch();}
function renderAch() {
  if(!_achData||!_featData) return;
  const feats=[...(_featData.feats||[])].sort((a,b)=>(a.completed?1:0)-(b.completed?1:0)||b.pct-a.pct||a.order-b.order);
  let achs=[..._achData];
  if(_achSort==='progress') achs.sort((a,b)=>b.pct-a.pct);
  else if(_achSort==='todo') achs.sort((a,b)=>(a.completed?1:0)-(b.completed?1:0)||b.pct-a.pct);
  const legacyDone=achs.filter(a=>a.level>0).length;
  el('pro-ach').innerHTML=`
    <div class="card" style="margin-bottom:8px">
      <div class="card-title">▤ Хроника подвигов <span style="font-size:9px;font-weight:400;color:var(--muted)">${_featData.completed} / ${_featData.total}</span></div>
      <div style="font-size:11px;color:var(--muted);line-height:1.5">${esc(_featData.message)}</div>
      <div style="font-size:10px;color:var(--teal);margin-top:6px">Личные отметки · не рейтинг · не продаются · не дают силу</div>
    </div>
    <div class="card" style="margin-bottom:10px">
      ${feats.map(a=>`<div class="ach-item" style="cursor:pointer" data-feat-id="${esc(a.id)}">
        <div class="ach-head"><div class="ach-icon">${esc(a.icon)}</div><div class="ach-name">${esc(a.name)}</div><div class="ach-lvl" style="color:${a.completed?'var(--gold)':'var(--muted)'}">${a.completed?'★ ГОТОВО':`${a.progress}/${a.target}`}</div></div>
        <div style="font-size:10px;color:var(--muted);margin-bottom:5px">${esc(a.description)}</div>
        <div class="ach-bar"><div class="ach-fill ${a.completed?'high':a.pct>=50?'':'low'}" style="width:${a.pct}%"></div></div>
      </div>`).join('')}
    </div>
    <details class="card">
      <summary class="card-title" style="cursor:pointer">🏆 Архив старых достижений · ${legacyDone}/${achs.length}</summary>
      <div style="font-size:11px;color:var(--muted);line-height:1.5;margin:6px 0 10px">${esc(_achMessage)}</div>
    <div style="display:flex;gap:4px;margin-bottom:10px;align-items:center;flex-wrap:wrap">
      <span style="font-size:10px;color:var(--muted);margin-right:2px">Сорт:</span>
      <button class="btn btn-sm ${_achSort==='default'?'btn-gold':'btn-ghost'}" style="padding:4px 8px;font-size:10px" onclick="setAchSort('default')">По умолч.</button>
      <button class="btn btn-sm ${_achSort==='progress'?'btn-gold':'btn-ghost'}" style="padding:4px 8px;font-size:10px" onclick="setAchSort('progress')">% прогресса</button>
      <button class="btn btn-sm ${_achSort==='todo'?'btn-gold':'btn-ghost'}" style="padding:4px 8px;font-size:10px" onclick="setAchSort('todo')">Сначала активные</button>
    </div>
      ${achs.map(a=>{
        const fc=a.completed?'high':a.pct>=60?'high':a.pct>=25?'':'low';
        return `<div class="ach-item" style="cursor:pointer" data-legacy-ach-id="${esc(a.id)}">
          <div class="ach-head">
            <div class="ach-icon">${a.icon}</div>
            <div class="ach-name">${a.name}</div>
            <div class="ach-lvl" style="color:${a.completed?'var(--gold)':a.level>0?'var(--green)':'var(--muted)'}">
              ${a.completed?'★ MAX':a.level>0?`Lv${a.level}`:'—'}
            </div>
          </div>
          <div style="font-size:10px;color:var(--muted);margin-bottom:5px">Сохранённый прогресс · система закрыта</div>
          <div class="ach-bar"><div class="ach-fill ${fc}" style="width:${a.pct}%"></div></div>
          <div class="ach-prog">${fmt(a.progress)} / ${fmt(a.next_threshold||a.progress)}${a.completed?' ✅':''}</div>
        </div>`;
      }).join('')}
    </details>`;
}

function openFeatModal(id) {
  const a=(_featData?.feats||[]).find(item=>item.id===id);
  if(!a) return;
  OM(`${a.icon} ${esc(a.name)}`,`
    <div style="font-size:13px;line-height:1.5">${esc(a.description)}</div>
    <div class="ach-bar" style="height:8px;margin:12px 0 4px"><div class="ach-fill ${a.completed?'high':''}" style="width:${a.pct}%"></div></div>
    <div style="font-size:12px;color:var(--muted);text-align:center">${a.progress} / ${a.target}${a.completed?' · выполнено':''}</div>
    <div style="background:var(--dim);border-radius:var(--r);padding:8px 10px;margin-top:10px;font-size:11px;color:var(--muted);line-height:1.4">Подвиг вычисляется из подтверждённого состояния игры. Его нельзя купить, забрать повторно или обменять на силу.</div>
  `,[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}

function openAchModal(id) {
  const a=(_achData||[]).find(item=>item.id===id);
  if(!a) return;
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
    <div style="background:var(--dim);border-radius:var(--r);padding:8px 10px;margin-top:8px;font-size:11px;color:var(--muted);line-height:1.4">Уровень и счётчик сохранены как история. Новые действия не меняют этот результат и не выдают наград.</div>
  `,[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}

document.addEventListener('click',event=>{
  const feat=event.target.closest('[data-feat-id]');
  if(feat) return openFeatModal(feat.dataset.featId);
  const legacy=event.target.closest('[data-legacy-ach-id]');
  if(legacy) openAchModal(legacy.dataset.legacyAchId);
});


// ══ Кланы: переход к общей системе Союза ══════════════════════════════════════
// Базовый клан, состав и владение остаются в /clans. Старые Бездна, здания за
// осколки и клеточные войны закрыты: они нарушали новую экономику и возвращали
// удалённую боёвку. До аудиторных порогов кланы играют вместе через Союз.
function _clan2NavHtml(active){
  const item=(key,icon,label,sub)=>
    `<button class="btn ${active===key?'btn-gold':'btn-ghost'}" onclick="showClanTransition('${key}')">${icon} ${label}<span class="clan2-nav-sub">${sub}</span></button>`;
  return `<div class="clan2-nav">
    ${item('alliance','◈','Союз','общая цель')}
    ${item('projects','▦','Проекты','после 3 кланов')}
    ${item('competition','◇','Состязание','после 8 кланов')}
  </div>`;
}
function showClanTransition(section){
  const copy={
    alliance:['Союз Предвестников','Совместная цель появится после утверждения клановых правил и экономики.'],
    projects:['Клановые проекты','Откроются, когда в игре будет не меньше трёх активных кланов. Так проекты станут совместной игрой, а не пустой шкалой.'],
    competition:['Клановое состязание','Откроется при восьми активных кланах. До этого не будет фиктивной войны с пустыми соперниками.'],
  }[section]||['Кланы','Раздел готовится к новой экономике.'];
  OM(`◈ ${copy[0]}`,`<div class="looks-hint">${copy[1]}</div>`,[
    {l:'Открыть игры',c:'btn-gold',f:"CM();goTo('arena','game')"},
    {l:'Закрыть',c:'btn-ghost',f:'CM()'},
  ]);
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
