// ── Profile ───────────────────────────────────────────────────────────────────
// switchPro() defined later with marriage + wallet tabs
function _profileEsc(value){ return String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }

function _profileDate(value){
  if(!value) return '—';
  const parsed=new Date(value);
  return Number.isNaN(parsed.getTime())?_profileEsc(String(value).replace('T',' ').slice(0,16)):parsed.toLocaleDateString('ru-RU');
}
function loadProfile() {
  setTimeout(v3PaintCachedProfile, 0);   // после загрузки всех частей скрипта (loadProfile вызывается раньше app.15–19): кэш или скелет
  return api('/profile/me').then(d=>{
    if(!d || typeof d !== 'object') throw new Error('Неверный формат ответа сервера');
    _cid = _initChatId || d.chats?.[0]?.chat_tg_id || 0;
    if(d.user_id) _uid = d.user_id;
    _profileData = d;
    if (d.is_vip && !d.avatar && _vipAvatar) d.avatar = _vipAvatar;
    if (!d.is_vip) _vipAvatar = null;
    const adminEntry=el('v3-admin-entry');
    if(adminEntry) adminEntry.hidden=!(d.is_developer||d.is_staff);
    if(typeof v3NoteServerClock==='function') v3NoteServerClock(d.server_clock);
    if(typeof v3ApplyLook==='function') v3ApplyLook(d.look);
    // A profile response is authoritative. Optional decorations must never
    // turn it into the misleading “write the bot to create a profile” state.
    try { _applySysFlags(d.system_flags); } catch (_) {}
    el('pro-main').innerHTML=renderProfileHome(d);
    if(typeof v3EnterSync==='function')v3EnterSync(el('pro-main'));   // перерисовка не перезапускает каскад секций
    try { checkWhatsNewBadge(); } catch (_) {}
    try { passCheck(); } catch (_) {}   // точка на вкладке «Игры», пока есть что забрать из пропуска сезона (app.43.js)
    try { renderV3Bar(d); v3SaveProfileCache(d); _v3LastSync = Date.now(); delete el('pro-main').dataset.stale; v3CountUp(el('pro-main')); v3Delights(d); } catch (_) {}
    try { loadV3Today(); loadV3Path(); _v3TopCache = {}; v3LazyTop(); } catch (_) {}
    try { _tosGate(d); } catch (_) {}
    try { if(!_ws && _uid) connectWS(); } catch (_) {}
    try { updateCurrBar(d); } catch (_) {}
  }).catch(e=>{el('pro-main').innerHTML=`<div style="color:var(--red);padding:20px;font-size:12px">${typeof e==='string'?e:'Напишите боту чтобы создать профиль.'}</div>`;});
}

function openBotAdmin(){
  location.href=`${BASE}/bot-admin`;
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
  // ?startapp=<раздел> в адресе страницы главнее нативного start_param: это переход внутри приложения (например «‹» из игры),
  // а нативный параметр остаётся от первого запуска и перебил бы его.
  let p=''; try{ p=new URLSearchParams(location.search).get('startapp')||''; }catch(e){}
  if(!p){ try{ p=String((tg&&tg.initDataUnsafe&&tg.initDataUnsafe.start_param)||''); }catch(e){} }
  if(!p) return;
  const base=p.split('_')[0];
  if(base==='admin'){ openBotAdmin(); return; }   // ссылка «🛠 Открыть админку» из чата: сразу в админку, без показа приложения
  const run=fn=>setTimeout(()=>{ try{ fn(); }catch(e){} }, 380);
  const settings=()=>{ switchPage('profile'); setTimeout(()=>{ try{ openSettingsModal(); }catch(e){} },260); };
  // Диплинки живых разделов. Старые имена (рынок, аукцион, гача, кланы, БП и др.) ведут на «Игры»: их экранов больше нет.
  // Лениво: часть экранов (window.openQuestsV1 и др.) объявляется в более поздних частях скрипта, прямое обращение здесь роняло весь скрипт ReferenceError'ом.
  const LINKS={
    mfo:()=>openMafiaOnline(Number(p.split('_')[1])||0,p.split('_')[2]||''),
    purge:()=>openPurgeHub(Number(p.split('_')[1])||0), family:()=>openFamilyTree(), mafia:()=>openMafiaReview(Number(p.split('_')[1])||0),
    quests:()=>openQuestsV1(), achievements:()=>openAchievementsV1(), achievement:()=>openAchievementsV1(), pets:()=>openPetsV1(), zoo:()=>openPetsV1(),
    looks:()=>openLooksModal(), cosmetics:()=>openLooksModal(), themes:()=>openLooksModal(), shop:()=>openLooksModal(), goods:()=>openLooksModal(), inventory:()=>openInventory(), inv:()=>openInventory(),
    vip:()=>openStoreV3('vip'), zarniki:()=>openStoreV3('zarniki'), topup:()=>openStoreV3('zarniki'),
    casino:()=>openCasino(), exchange:()=>openPlayerExchangeV1(), exch:()=>openPlayerExchangeV1(), crypto:()=>openPlayerExchangeV1(), birzha:()=>openPlayerExchangeV1(),
    guide:()=>openGuide(p.split('_')[1]||''), help:()=>openGuide(p.split('_')[1]||''),
    notifications:settings, notifprefs:settings, settings:()=>openSettingsModal(), top:()=>openTopV3(), news:()=>openWhatsNew(), pass:()=>openSeasonPass(), season:()=>openSeasonPass(), bp:()=>openSeasonPass(), battlepass:()=>openSeasonPass(),
  };
  if(base==='public'){
    let ref=''; try{ ref=new URLSearchParams(location.search).get('profile')||''; }catch(e){}
    if(ref) run(()=>openPublicProfile(ref));
    return;
  }
  if(LINKS[base]) { run(LINKS[base]); return; }
  if(['arena','games','game','barracks','gates','gacha','deal','craft','auction','market','relics','clans','ach'].includes(base)) run(()=>goTo('arena','game'));
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
  if (typeof renderV3Bar === 'function') renderV3Bar(data);
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
  set('cb-zar',  data?.zarniki ?? 0, fmtBar);
  _currInited = true;
}

// ── VIP Telegram avatar (Block 3) ──────────────────────────────────────────────
// Грузим один раз за сессию, кэшируем, применяем к хедеру и карточке профиля.
let _vipAvatar = null, _vipAvatarLoading = null, _vipAvatarRetryAt = 0;
function _validAvatar(value) {
  return typeof value === 'string' && /^data:image\/(?:png|jpe?g|webp);base64,[A-Za-z0-9+/=]+$/.test(value);
}
async function _requestVipAvatar(ref, current = () => true) {
  // Bounded recovery covers a cold background download and the short negative
  // cache. Leaving a card stops its retries; the next visit can try again.
  for (const delay of [0, 2000, 6000, 12000]) {
    if (delay) await new Promise(resolve => setTimeout(resolve, delay));
    if (!current()) return null;
    try {
      const r = await api('/profile/avatar' + (ref ? `?profile_ref=${encodeURIComponent(ref)}` : ''));
      if (!current()) return null;
      if (r?.vip === false) return null;
      if (_validAvatar(r?.avatar)) return r.avatar;
    } catch (_) { /* a transient network error is retried within this budget */ }
  }
  return null;
}
function _applyVipAvatar() {
  if (!_vipAvatar) return;
  if (_profileData?.is_vip) {
    _profileData.avatar = _vipAvatar;
    if (typeof v3SaveProfileCache === 'function') v3SaveProfileCache(_profileData);
  }
  const img = `<img src="${_vipAvatar}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;display:block">`;
  const h = el('hdr-ava'); if (h) h.innerHTML = img;
  const p = el('pro-ava'); if (p) p.innerHTML = img;
  const s = el('pro-showcase-ava'); if (s) s.innerHTML = img;
  const f = el('fit-ava'); if (f) f.innerHTML = img;
}
function _ensureVipAvatar() {
  if (_vipAvatar) { _applyVipAvatar(); return; }
  if (_vipAvatarLoading || Date.now() < _vipAvatarRetryAt) return;
  _vipAvatarLoading = _requestVipAvatar(null, () => !!_profileData?.is_vip).then(avatar => {
    if (avatar && _profileData?.is_vip) { _vipAvatar = avatar; _applyVipAvatar(); }
  }).finally(() => { _vipAvatarLoading = null; _vipAvatarRetryAt = Date.now() + 30000; });
}

let _walletPolicy = null, _walletTarget = 'mora', _walletSeq = 0, _walletBusy = false;
const _walletRequests = new Map();
function _walletIcon(code) {
  if (typeof v3Cur === 'function' && v3Cur(code)) return v3Cur(code, 'wallet-cur');   // рисованные валюты (app.50.js), как в Пропуске и сундуках
  const paths = {mora:'<circle cx="12" cy="12" r="8"/><path d="M8 8h8M8 16h8M10 8v8M14 8v8"/>',diamonds:'<path d="m4 9 4-5h8l4 5-8 11zM4 9h16M8 4l4 16 4-16"/>',essence:'<path d="M12 3c3 4 6 7 6 11a6 6 0 0 1-12 0c0-4 3-7 6-11z"/>',zarniki:'<path d="m12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3z"/>'};
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[code] || paths.zarniki}</svg>`;
}
function showCurrModal() {
  const d = _v3Wallet(_profileData || {}), mine = ++_walletSeq;
  _walletPolicy = null;
  OM('Кошелёк', `<div class="wallet-v4">
    <div class="wallet-summary"><span>${_walletIcon('zarniki')} Зарники</span><strong id="cm-bal-zarniki">${fmtF(d.zarniki || 0)}</strong></div>
    <div class="wallet-assets">${[['mora','Мора','Игры и задания'],['diamonds','Алмазы','Редкие награды'],['essence','Эссенция','Развитие образов']].map(([id,name,sub])=>`<div class="wallet-asset">${_walletIcon(id)}<span><b>${name}</b><small>${sub}</small></span><strong id="cm-bal-${id}">${fmtF(d[id] || 0)}</strong></div>`).join('')}</div>
    <section class="wallet-exchange" id="wallet-exchange" aria-live="polite"><p class="v3-sub">Загружаем актуальные курсы…</p></section>
    <details class="wallet-help"><summary>Как устроен обмен</summary><p>Зарники можно обменять на Мору, Алмазы или Эссенцию. Курс один для кошелька, магазина и «Образов».</p><p>Мору и Алмазы можно менять в любом количестве и в любой день. Эссенция продаётся готовыми наборами — такими же, как в «Образах».</p><p>Обмен нельзя отменить: обратно в Зарники ничего не превратится.</p></details>
  </div>`, [{l:'Пополнить Зарники',c:'ghost',f:'CM();openZarnikiTopup()'},{l:'Закрыть',c:'ghost',f:'CM()'}]);
  api('/wallet/exchange-policy').then(p => {
    if (mine !== _walletSeq || !el('modal')?.open || !el('wallet-exchange')) return;
    if (!Array.isArray(p?.routes) || !p.routes.length) throw new Error('Курсы временно недоступны');
    _walletPolicy = p; _walletRenderExchange();
  }).catch(() => {
    if (mine === _walletSeq && el('modal')?.open && el('wallet-exchange')) el('wallet-exchange').innerHTML = '<p class="v3-sub">Не удалось загрузить курсы.</p><button type="button" class="v3-link" onclick="showCurrModal()">Повторить</button>';
  });
}
function _walletRoute() { return _walletPolicy?.routes.find(r => r.id === _walletTarget); }
function _walletRenderExchange() {
  const root = el('wallet-exchange'); if (!root || !_walletPolicy) return;
  const route = _walletRoute() || _walletPolicy.routes[0]; _walletTarget = route.id;
  const amount = route.packs ? route.packs[0].zarniki : 10;
  root.innerHTML = `<h3>Обменять Зарники</h3><div class="wallet-fields"><label>Получить<select id="zar-exchange-target" class="v3-field" onchange="walletPickTarget(this.value)">${_walletPolicy.routes.map(r=>`<option value="${_profileEsc(r.id)}" ${r.id===route.id?'selected':''}>${_profileEsc(r.name)}</option>`).join('')}</select></label>
    <label>Отдать, Зарники${route.packs ? `<select id="zar-exchange-amount" class="v3-field" onchange="walletQuote()">${route.packs.map(p=>`<option value="${p.zarniki}">${fmt(p.zarniki)}</option>`).join('')}</select>` : `<input id="zar-exchange-amount" class="v3-field" type="number" inputmode="numeric" min="1" step="1" value="${amount || ''}" placeholder="Сумма" oninput="walletQuote()">`}</label></div>
    <div class="wallet-quote"><span>Получите</span><strong id="wallet-receive">—</strong></div>
    <p class="wallet-rate">1 Зарник = ${fmtF(Number(route.rate))} ${_profileEsc(route.unit || route.name)}. ${route.shared_daily_limit ? `Осталось ${fmt(_walletPolicy.remaining_today)} из ${fmt(_walletPolicy.daily_cap)} на сегодня · UTC.` : (route.packs ? 'Без суточного лимита · наборы как в «Образах».' : 'Без суточного лимита.')}</p>
    <button type="button" class="v3-pill v3-pill--full" id="zar-exchange-submit" onclick="exchangeZarnikiV1()">Обменять</button><p class="wallet-message" id="wallet-message" role="status"></p>`;
  walletQuote();
}
function walletPickTarget(value) { if (_walletBusy) return; _walletTarget = value; _walletRenderExchange(); }
function _walletDraft() {
  const raw = String(el('zar-exchange-amount')?.value || '').trim(), amount = Number(raw), route = _walletRoute();
  if (!route || !/^\d+$/.test(raw) || !Number.isSafeInteger(amount) || amount < 1) return null;
  const pack = route.packs?.find(p => Number(p.zarniki) === amount);
  if (route.packs ? !pack : route.shared_daily_limit && amount > _walletPolicy.remaining_today) return null;
  return { amount, target: route.id, name: route.unit || route.name, received: pack ? Number(pack.amount) : Math.round(amount * Number(route.rate) * 1e6) / 1e6 };
}
function walletQuote() {
  const draft = _walletDraft(), b = el('zar-exchange-submit'), receive = el('wallet-receive'), message = el('wallet-message');
  const enough = draft && draft.amount <= Number(_v3Wallet(_profileData || {}).zarniki || 0);
  if (receive) receive.textContent = draft ? `${fmtF(draft.received)} ${draft.name}` : '—';
  if (message) message.textContent = !draft ? 'Выберите доступную сумму обмена.' : !enough ? 'Не хватает Зарников.' : '';
  if (b) { b.disabled = _walletBusy || !draft || !enough; b.textContent = _walletBusy ? 'Обмениваем…' : 'Обменять'; }
  for (const id of ['zar-exchange-target','zar-exchange-amount']) { const field = el(id); if (field) field.disabled = _walletBusy; }
}
async function exchangeZarnikiV1() {
  const draft = _walletDraft(); if (!draft || _walletBusy) return;
  const mine = _walletSeq;
  _walletBusy = true; walletQuote();
  try {
    if (!(await v3Confirm({title:'Обмен Зарников',visual:_walletIcon(draft.target),name:`${fmt(draft.amount)} Зарников → ${fmtF(draft.received)} ${draft.name}`,rows:[['Отдадите',`${fmt(draft.amount)} Зарников`],['Получите',`${fmtF(draft.received)} ${draft.name}`,true]],cta:'Подтвердить обмен',note:'После получения валюты обмен необратим.'}))) return;
    const signature = `${draft.target}:${draft.amount}`, key = _walletRequests.get(signature) || economyRequestKey('wallet-exchange');
    _walletRequests.set(signature, key);
    const essence = draft.target === 'essence';
    const result = await api(essence ? '/skins-v3/essence' : '/wallet/exchange-zarniki', {method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify(essence ? {zarniki:draft.amount} : {amount:draft.amount,to:draft.target})});
    _walletRequests.delete(signature);
    toast(essence ? result.message : `Получено ${fmtF(result.amount_received)} ${draft.name}`);
    if (essence && result.state) {
      _profileData = {...(_profileData || {}), essence:result.state.essence.balance,zarniki:result.state.zarniki};
      updateCurrBar(_profileData);
    }
    const reconciled = await refreshCurrBar();
    // The refresh is a reconciliation read; do not replay a completed spend if
    // loading the new quota fails afterwards.
    if (mine === _walletSeq && el('modal')?.open && el('wallet-exchange')) {
      if (reconciled) showCurrModal();
      else {
        for (const code of ['mora','diamonds','zarniki','essence']) { const node = el('cm-bal-' + code); if (node) node.textContent = '—'; }
        el('wallet-exchange').innerHTML = '<p class="v3-sub">Обмен выполнен. Не удалось обновить балансы.</p><button type="button" class="v3-pill v3-pill--full" onclick="walletRefreshBalances()">Обновить балансы</button>';
      }
    }
  } catch (e) { toast(e, false); }
  finally { _walletBusy = false; walletQuote(); }
}
async function walletRefreshBalances() {
  const mine = _walletSeq, data = await refreshCurrBar();
  if (mine === _walletSeq && el('modal')?.open && data) showCurrModal();
  else if (!data) toast('Не удалось обновить балансы. Повторите позже.', false);
}

function showCurrBar(show) {
  // Редизайн v5: хедер с валютами и кнопкой пополнения виден ВСЕГДА (донат на виду).
  _currBarVisible = true;
}

el('curr-bar')?.addEventListener('click', showCurrModal);

// Reconciliation read: initial load and a real WebSocket reconnect only.
// Normal changes arrive as exact transactional `balance_changed` events.
function refreshCurrBar() {
  if (!_uid || !_currBarVisible) return;
  return api('/profile/me').then(d => {
    updateCurrBar(d);
    _profileData = {...(_profileData||{}), ...d};
    _profileSyncStats(d);
    return d;
  }).catch(()=>{});
}
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
  const metric=(key,val,short=false)=>{
    const n=document.querySelector(`#pro-main [data-key="${key}"]`);if(!n||val==null)return;
    n.dataset.n=String(Number(val)||0);n.textContent=short?_v3Short(val):fmt(val);
  };
  metric('mora',d.mora);metric('streak',d.streak);metric('ach',d.achievements);
  metric('msgs',d.messages_all_time,true);
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
// Запись с полем flag (ключ модуля, например "pets_v2") лежит в ленте сразу, а игрок видит её, когда модуль включён:
// о том, чего ещё нет на его экране, не рассказываем. Пока флаги не пришли, такая запись скрыта.
const _wnShown = list => list.filter(u => !u.flag || _sysFlags[u.flag] === true);
function _wnFetch(){
  if (_wnData) return Promise.resolve(_wnShown(_wnData));
  return api('/updates.json').then(d => {
    const all=(d && Array.isArray(d.updates))?d.updates:[];
    const archiveAt=all.findIndex(u=>u.id===_WN_ARCHIVE_BOUNDARY);
    _wnData=archiveAt<0?all:all.slice(0,archiveAt);
    return _wnShown(_wnData);
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
    if (typeof _wnTabDots === 'function') _wnTabDots(list);   // точки на вкладках дока (app.42.js)
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
// Страница ленты (openWhatsNew, loadWhatsNew), записи, фильтр, «Открыть» и точки на вкладках дока: app.42.js.
