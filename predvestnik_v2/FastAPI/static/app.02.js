// ── Profile ───────────────────────────────────────────────────────────────────
// switchPro() defined later with marriage + wallet tabs
function _profileEsc(value){ return String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }

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
    :'<div class="profile-clean-state"><span>✓</span><div><b>Профиль без ограничений</b><small>Активных глобальных санкций нет</small></div></div>';
  const history=(sanctions.history||[]).map(item=>`<li><b>${_profileEsc(item.label||item.type||'Ограничение')}</b>${item.reason?` — ${_profileEsc(item.reason)}`:''}<small>${_profileDate(item.created_at)}${item.revoked_at?' · снято':''}${item.expires_at?` · до ${_profileDate(item.expires_at)}`:''}</small></li>`).join('')||'<li>История ограничений пуста.</li>';
  return `<section class="profile-detail-section profile-zone profile-zone--safety"><header><span>🛡</span><div><small>Безопасность аккаунта</small><h3>Санкции</h3></div></header>${activeHtml}<div class="profile-safety-stats"><span><small>Предупреждения</small><b>${fmt(sanctions.chat_warning_total||0)}</b></span><span><small>Активный мут</small><b>${sanctions.chat_mute_until?_profileDate(sanctions.chat_mute_until):'Нет'}</b></span></div><details class="profile-history"><summary>Показать историю</summary><ul>${history}</ul></details></section>`;
}
function renderProfileDetails(data,{owner=false}={}){
  const d=data||{}, games=d.game_results||{}, rhythm=games.rhythm||{}, mines=games.minesweeper||{}, mafia=games.mafia||{};
  const best=mines.best_ms||{};
  const unranked=owner&&Number(rhythm.personal_unranked_runs)>0
    ?`<small>${fmt(rhythm.personal_unranked_runs)} личных забегов не участвуют в рейтинге</small>`:'';
  const gameCards=`<div class="profile-game-grid">
    <article class="profile-game profile-game--rhythm"><span class="profile-game-icon">ᚱ</span><div><b>Ритм</b><strong>${rhythm.best_verified_score==null?'—':fmt(rhythm.best_verified_score)}</strong><small>лучший подтверждённый счёт</small><em>${fmt(rhythm.verified_runs||0)} забегов в рейтинге</em>${unranked}</div></article>
    <article class="profile-game profile-game--mines"><span class="profile-game-icon">▦</span><div><b>Сапёр</b><strong>${fmt(mines.wins||0)} <i>/ ${fmt(mines.played||0)}</i></strong><small>победы / партии</small><em>Лучшее: ${_profileDuration(best.easy)} · ${_profileDuration(best.normal)} · ${_profileDuration(best.hard)}</em></div></article>
    <article class="profile-game profile-game--mafia"><span class="profile-game-icon">◈</span><div><b>Мафия</b><strong>${fmt(mafia.wins||0)} <i>/ ${fmt(mafia.played||0)}</i></strong><small>победы / завершённые матчи</small><em>Засчитаны только завершённые партии</em></div></article>
  </div>`;
  const paths=d.achievement_paths?.families||[];
  const achievementRows=paths.map((path,index)=>{const level=Number(path.level)||0,max=Math.max(1,Number(path.max_level)||40),pct=Math.min(100,Math.round(level/max*100));return `<li style="--path:${pct}%"><span class="profile-path-icon">${['◉','◇','✦','⌁','△'][index%5]}</span><div><b>${_profileEsc(path.title||path.id)}</b><small>${fmt(path.completed_events||0)} событий · ${fmt(path.active_weeks||0)} недель</small><i><span></span></i></div><strong>${fmt(level)}<small> / ${fmt(max)}</small></strong></li>`;}).join('')||'<li class="profile-empty-row">Прогресс появится после первой активности.</li>';
  const pets=(d.pets||[]).map(pet=>`<article class="profile-social-pet${pet.active?' is-active':''}"><span>${pet.active?'●':'🐾'}</span><div><small>${pet.active?'Активный спутник':'Питомец'}</small><b>${_profileEsc(pet.name||'Питомец')}</b><em>${_profileEsc(pet.rarity||'Обычный')}${pet.level?` · уровень ${fmt(pet.level)}`:''}</em></div></article>`).join('')||'<div class="profile-social-empty"><span>🐾</span><p>Питомцев пока нет</p></div>';
  const clan=d.clan?`${_profileEsc(d.clan.emblem||'')} ${_profileEsc(d.clan.name||d.clan.tag||'Клан')}`.trim():'Нет';
  const publicVip=!owner&&d.vip?`<span><small>VIP</small><b>${_profileEsc(d.vip.label||d.vip.tier||'Активен')}</b><em>${fmt(d.vip.days_left||0)} дн.</em></span>`:'';
  return `<section class="profile-detail-section profile-zone profile-zone--games"><header><span>🎮</span><div><small>Личные рекорды</small><h3>Утверждённые игры</h3></div>${owner?'<button type="button" onclick="goTo(\'arena\',\'game\')">Играть →</button>':''}</header>${gameCards}</section>
    <section class="profile-detail-section profile-zone profile-zone--progress"><header><span>🏅</span><div><small>Путь игрока</small><h3>Прогресс и достижения</h3></div>${owner?'<button type="button" onclick="openAchievementsV1()">Все →</button>':''}</header><div class="profile-progress-summary"><span><b>${fmt(d.messages_all_time||0)}</b><small>сообщений</small></span><span><b>${fmt(d.achievement_paths?.total_levels||0)}</b><small>уровней</small></span><span><b>${_profileDate(d.joined_date)}</b><small>в проекте с</small></span></div><ul class="profile-paths">${achievementRows}</ul></section>
    <section class="profile-detail-section profile-zone profile-zone--social"><header><span>🌌</span><div><small>Люди и спутники</small><h3>Социальный профиль</h3></div>${owner?'<button type="button" onclick="openPetsV1()">Бестиарий →</button>':''}</header><div class="profile-social-identity"><span><small>Статус</small><b>${_profileEsc(d.rank||'Игрок')}</b></span>${publicVip}${owner?'':`<span><small>Клан</small><b>${clan}</b></span>`}<span><small>Партнёр</small><b>${_profileEsc(d.partner||'Нет')}</b></span></div><div class="profile-social-pets">${pets}</div></section>
    ${_profileSanctions(d)}`;
}
function _profileVipCard(vip){
  if(!vip)return '';   // покупка VIP недоступна: роутер /vip/* не подключён
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
  setTimeout(v3PaintCachedProfile, 0);   // после загрузки всех частей скрипта (loadProfile вызывается раньше app.15–19): кэш или скелет
  return api('/profile/me').then(d=>{
    if(!d || typeof d !== 'object') throw new Error('Неверный формат ответа сервера');
    _cid = _initChatId || d.chats?.[0]?.chat_tg_id || 0;
    if(d.user_id) _uid = d.user_id;
    _profileData = d;
    if(typeof v3NoteServerClock==='function') v3NoteServerClock(d.server_clock);
    if(typeof v3ApplyLook==='function') v3ApplyLook(d.look);
    // A profile response is authoritative. Optional decorations must never
    // turn it into the misleading “write the bot to create a profile” state.
    try { _applySysFlags(d.system_flags); } catch (_) {}
    const uid = d.user_id || _uid;
    el('pro-main').innerHTML=`
      ${renderProfileHome(d)}
      ${_profileCompensationCard(d.compensation,uid)}
      <details class="v3-more"><summary>Подробнее о профиле</summary>
        ${_profileVipCard(d.vip)}
        ${renderProfileDetails(d,{owner:true})}
        <div id="pro-marriage-card"><div class="sk" style="height:90px;border-radius:var(--r)"></div></div>
        <div id="pro-nick-card"></div>
        <div id="wallet-mini"></div>
      </details>`;
    if(typeof v3EnterSync==='function')v3EnterSync(el('pro-main'));   // перерисовка не перезапускает каскад секций
    try { checkWhatsNewBadge(); } catch (_) {}
    try { renderV3Bar(d); v3SaveProfileCache(d); _v3LastSync = Date.now(); delete el('pro-main').dataset.stale; v3CountUp(el('pro-main')); v3Delights(d); } catch (_) {}
    try { loadV3Today(); loadV3Path(); _v3TopCache = {}; v3LazyTop(); } catch (_) {}
    try { _tosGate(d); } catch (_) {}
    try { loadMarriageCard(); } catch (_) {}
    try { loadNickCard(); } catch (_) {}
    try { loadWalletMini(); } catch (_) {}
    try { if(!_ws && _uid) connectWS(); } catch (_) {}
    try { updateCurrBar(d); } catch (_) {}
  }).catch(e=>{el('pro-main').innerHTML=`<div style="color:var(--red);padding:20px;font-size:12px">${typeof e==='string'?e:'Напишите боту чтобы создать профиль.'}</div>`;});
}

// ── БЛОК22: Настройки + юридические документы ──────────────────────────────────
function _legalUrl(slug){ return BASE+'/legal/'+slug; }   // прямая публичная ссылка
function openLegalDoc(slug){
  const t={tos:'📖 Пользовательское соглашение',privacy:'🔒 Политика конфиденциальности'};
  OM(t[slug]||'Документ','<div class="loader">Загрузка…</div>',[{l:'Закрыть',c:'ghost',f:'CM()'}]);
  api('/legal/'+slug+'/text').then(d=>{
    el('mb').innerHTML=`<div class="legal-doc">${d.html}</div>
      <div class="legal-link">Прямая ссылка: <a href="${_legalUrl(slug)}" target="_blank" rel="noopener">${_legalUrl(slug)}</a></div>`;
  }).catch(e=>{ el('mb').innerHTML=`<div class="v3-err">${e}</div>`; });
}
// admin_audit C1b: авто-удаление за неактив + самоудаление с тройной защитой
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
    [{l:'📨 Получить код',c:'danger',f:'_accDeleteRequest()'},{l:'Отмена',c:'ghost',f:'CM()'}]);
}
function _accDeleteRequest(){
  api('/account/delete/request',{method:'POST'}).then(()=>{
    OM('🗑 Удаление — шаг 2 из 3',
      `<div style="font-size:12px;color:var(--muted);padding:4px 0">Код отправлен в ЛС бота.</div>
       <input id="acc-del-code" class="v3-field" inputmode="numeric" style="margin:6px 0" placeholder="Код из ЛС (6 цифр)"/>
       <input id="acc-del-phrase" class="v3-field" style="margin:0 0 4px" placeholder="Введите вручную: УДАЛИТЬ АККАУНТ"/>
       <div class="v3-dim">Шаг 3 — автоматический: 24 часа «остывания», в течение которых удаление можно отменить (в ЛС придёт напоминание как).</div>`,
      [{l:'Подтвердить удаление',c:'danger',f:'_accDeleteConfirm()'},{l:'Отмена',c:'ghost',f:'CM()'}]);
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
    .then(r=>{toast(r.message||'✅ Отменено');if(typeof _stLoad==='function')_stLoad('account');})
    .catch(e=>toast(e,false));
}
function _toggleNoFx(on){
  document.body.classList.toggle('no-fx',on);
  try{ localStorage.setItem('pv_no_fx',on?'1':'0'); }catch(e){}
  if(typeof applySkinTier==='function') applySkinTier(_v3Skin);   // движение образов и уровень эффектов пересчитываются сразу
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
      <button class="v3-pill v3-pill--ghost" onclick="openLegalDoc('tos')">📖 Правила (ToS)</button>
      <button class="v3-pill v3-pill--ghost" onclick="openLegalDoc('privacy')">🔒 Конфиденциальность</button>
    </div>
    <button class="v3-pill v3-pill--full" onclick="_tosAccept(this)">✅ Принять и играть</button>
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
    {l:'🎮 Открыть игры', c:'primary', f:"CM();goTo('arena','game')"},
    {l:'Позже', c:'ghost', f:'CM()'},
  ]), 500);
}

// ── Preloader: эффектный холодный старт (БЛОК 9.2) ──────────────────────────────
function _plSkip() {
  const pl = el('preloader');
  if(!pl || pl.classList.contains('pl-done')) return;
  pl.classList.add('pl-done');
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
  }, reduce ? 150 : 500);
  setTimeout(_plSkip, reduce ? 400 : 1300);
}
_runPreloader();

// Parity registry: bot redirects open the Mini App through
// ?startapp=<section>; lightweight chat surfaces remain in chat and do not
// need a web hop. The start parameter only selects the complex destination.
function _handleStartParam(){
  let p=''; try{ p=String((tg&&tg.initDataUnsafe&&tg.initDataUnsafe.start_param)||''); }catch(e){}
  // Обычная HTTPS-ссылка ?startapp=<раздел> не несёт нативный start_param: раздел лежит в query страницы.
  if(!p){ try{ p=new URLSearchParams(location.search).get('startapp')||''; }catch(e){} }
  if(!p) return;
  const base=p.split('_')[0];
  const run=fn=>setTimeout(()=>{ try{ fn(); }catch(e){} }, 380);
  const settings=()=>{ switchPage('profile'); setTimeout(()=>{ try{ openSettingsModal(); }catch(e){} },260); };
  // Диплинки живых разделов. Старые имена (рынок, аукцион, гача, кланы, БП и др.) ведут на «Игры»: их экранов больше нет.
  const LINKS={
    quests:openQuestsV1, achievements:openAchievementsV1, achievement:openAchievementsV1, pets:openPetsV1, zoo:openPetsV1,
    looks:openLooksModal, cosmetics:openLooksModal, themes:openLooksModal, shop:openLooksModal, goods:openLooksModal, inventory:openLooksModal, inv:openLooksModal,
    vip:()=>openStoreV3('vip'), zarniki:()=>openStoreV3('zarniki'), topup:()=>openStoreV3('zarniki'),
    exchange:openPlayerExchangeV1, exch:openPlayerExchangeV1, crypto:openPlayerExchangeV1, birzha:openPlayerExchangeV1,
    notifications:settings, notifprefs:settings, settings:openSettingsModal, top:openTopV3, news:openWhatsNew,
  };
  if(base==='public'){
    let ref=''; try{ ref=new URLSearchParams(location.search).get('profile')||''; }catch(e){}
    if(ref) run(()=>openPublicProfile(ref));
    return;
  }
  if(LINKS[base]) { run(LINKS[base]); return; }
  if(['arena','games','game','casino','barracks','gates','gacha','deal','craft','bp','auction','market','relics','clans','ach'].includes(base)) run(()=>goTo('arena','game'));
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
  // Identity belongs to the header, not to the optional compact currency bar.
  // The profile no longer renders that bar on its main page, so returning here
  // used to leave the header stuck at the loading placeholder "Игрок / …".
  if (data?.username !== undefined) {
    const nm=el('hdr-name'); if(nm) nm.textContent=(data.is_vip?'👑 ':'')+(data.username||'Игрок');
    const sub=el('hdr-sub'); if(sub) sub.textContent='Профиль Предвестника';
    const av=el('hdr-ava');
    if(av){
      if(data.is_vip){ av.textContent='👑'; _ensureVipAvatar(); }
      else if(!_vipAvatar) av.textContent='🔮';
    }
  }
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
        <div class="cm-desc">Основная валюта: награды за квесты и игры.</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">💎</div>
      <div class="cm-info">
        <div class="cm-name">Алмазы <span class="cm-val">${fmtF(dia)}</span></div>
        <div class="cm-desc">Редкая валюта: награды за достижения и сундуки.</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">💧</div>
      <div class="cm-info">
        <div class="cm-name">Эссенция <span class="cm-val">${fmtF(d.essence ?? 0)}</span></div>
        <div class="cm-desc">Растит образы по тирам. Её дают задания, ещё её можно взять за Зарники в разделе «Образы».</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">🌑</div>
      <div class="cm-info">
        <div class="cm-name">Тёмная Мора <span class="cm-val">${fmtF(dark)}</span></div>
        <div class="cm-desc">Старый остаток. Новых начислений нет.</div>
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
      <div style="display:flex;gap:6px"><input id="zar-exchange-amount" class="v3-field" type="number" inputmode="numeric" min="1" max="50" step="1" placeholder="1–50" style="flex:1;margin:0"><select id="zar-exchange-target" class="v3-field" style="width:126px;margin:0"><option value="mora">🪙 Мора</option><option value="diamonds">💎 Алмазы</option></select></div>
      <button id="zar-exchange-submit" class="v3-pill v3-pill--full" style="margin-top:7px" onclick="exchangeZarnikiV1()">Обменять</button>
    </div>
  </div>`, [{l:'Пополнить Зарники', c:'primary', f:'CM();openZarnikiTopup()'}, {l:'Закрыть', c:'ghost', f:'CM()'}]);
}

// Обмен Зарников: сначала лист подтверждения с тем, что отдаём и получаем (курс 1✨ = 10🪙 или 0,01💎), потом сам запрос
async function exchangeZarnikiV1(){
  const raw=(el('zar-exchange-amount')?.value||'').trim(),amount=Number(raw),target=el('zar-exchange-target')?.value;
  if(/^\d+$/.test(raw)&&Number.isSafeInteger(amount)&&amount>=1&&amount<=50&&(target==='mora'||target==='diamonds')){
    const got=target==='mora'?`${fmt(amount*10)} 🪙 Моры`:`${(amount/100).toLocaleString('ru')} 💎 Алмазов`;
    if(!(await v3Confirm({title:'Обмен Зарников',visual:'💱',name:`${fmt(amount)} ✨ → ${got}`,sub:'По курсу сервера',rows:[['Отдадите',`${fmt(amount)} ✨`],['Получите',got,true]],cta:'Обменять',note:'Обмен необратим. Лимит: 50 ✨ суммарно за сутки по UTC.'})))return;
  }
  return _exchangeZarnikiRun();
}
function _exchangeZarnikiRun(){
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

// Legacy achievement instructions were deliberately removed: several pointed
// players to retired gacha, gates, spending and message-spam loops.

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
// Everything from this entry downward describes the retired pre-relaunch
// product (Gates, gacha, auction and Battle Pass). Keep the source history in
// updates.json, but never mix it into the current player feed.
const _WN_ARCHIVE_BOUNDARY = '2026-08-23-reconstruction-first-release';
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
  return api('/updates.json').then(d => {
    const all=(d && Array.isArray(d.updates))?d.updates:[];
    const archiveAt=all.findIndex(u=>u.id===_WN_ARCHIVE_BOUNDARY);
    _wnData=archiveAt<0?all:all.slice(0,archiveAt);
    return _wnData;
  });
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
    document.querySelectorAll('[data-wn-dot]').forEach(dot => { dot.hidden = !unseen; });
    document.querySelectorAll('[data-wn-btn]').forEach(btn => btn.classList.toggle('has-new', unseen));
  }).catch(()=>{});
}
function _wnMarkSeen(list){
  const latest = _wnLatestId(list);
  if (latest) {
    if (_profileData) _profileData.whatsnew_seen_id = latest;   // сразу видно этой же сессии
    try { localStorage.setItem(_WN_SEEN_KEY, latest); } catch(_){}   // офлайн-подстраховка
    api('/profile/whatsnew-seen', {method:'POST', body: JSON.stringify({seen_id: latest})}).catch(()=>{});
  }
  document.querySelectorAll('[data-wn-dot]').forEach(dot => { dot.hidden = true; });
  document.querySelectorAll('[data-wn-btn]').forEach(btn => btn.classList.remove('has-new'));
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
      box.innerHTML = head + `<div class="v3-empty">📣<b>Пока тихо</b>Обновления появятся здесь</div>`;
      return;
    }
    const newCount = _wnNewCount(list);
    const cards = list.map((u,i) => _wnCard(u, i < newCount)).join('');
    box.innerHTML = head + `<div class="wn-list">${cards}</div>`;
    _wnMarkSeen(list);   // открыл ленту → всё прочитано, badge гаснет
  }).catch(e => { box.innerHTML = `<div class="v3-err" style="margin:12px">${e}</div>`; });
}
