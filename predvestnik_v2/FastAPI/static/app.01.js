const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }  // setHeaderColor removed — deprecated in TG WebApp v6.0

const BASE = (location.origin + location.pathname).replace(/[/]$/, '');

// el() defined here — BEFORE any usage to avoid TDZ ReferenceError
const el = id => document.getElementById(id);
// Тумблер «Отключить анимации косметики» (Настройки) — до первой отрисовки, чтобы
// не было вспышки анимации перед заморозкой. Сам класс гасит анимацию через
// правило .no-fx в app.css (тот же вход, что и системный prefers-reduced-motion).
try{ if(localStorage.getItem('pv_no_fx')==='1') document.body.classList.add('no-fx'); }catch(e){}
const INIT_DATA = tg?.initData || '';
const SK = 'pv_sess';
const MEDALS = ['🥇','🥈','🥉'];
const PL = {active:'Активный',passive:'Пассивный',storage:'Склад',auction:'🏛 На аукционе'};
const RC = {common:'rc-common',uncommon:'rc-uncommon',rare:'rc-rare',
            epic:'rc-epic',legendary:'rc-legendary',shadow:'rc-shadow',mythic:'rc-mythic'};
// Единый источник: русское название + акцентный цвет редкости (для бейджей/подписей).
// Множественные формы для фильтров ("Редкие", с эмодзи) — отдельно в app.04.js, другой контекст.
const RARITY_META = {
  common:    {label:'Обычный',    color:'#9aa7b8'},
  rare:      {label:'Редкий',     color:'#5b9bd5'},
  epic:      {label:'Эпический',  color:'#b07ad6'},
  legendary: {label:'Легендарный',color:'#e8c45a'},
  mythic:    {label:'Мифический', color:'#e0556b'},
};
function rarLabel(r){ return (RARITY_META[r]||{}).label || r; }
function rarColor(r){ return (RARITY_META[r]||{}).color || '#9aa7b8'; }

// Chat where the mini app was opened from: bot encodes ?chat_id= for group
// launches (Telegram WebApp context alone isn't reliable for group buttons).
const _tgChat = tg?.initDataUnsafe?.chat || null;
const _urlChatId = parseInt(new URLSearchParams(location.search).get('chat_id') || '0', 10) || 0;
const _initChatId = _urlChatId || _tgChat?.id || 0;   // primary chat_id for local data
const _initChatTitle = _tgChat?.title || '';

// _arenaTab: дефолт 'raids' — вкладки «duels» в Арене больше нет (GAME_BIBLE
// находка №8: 'duels' скрывал обе панели при первом открытии Арены)
let _cid = 0, _uid = 0, _actTab='duels', _zooTab='nursery', _arenaTab='raids';
let _zooData=null, _invData=[], _expTimer=null, _themeData=null, _mktTab='gacha';
let _proTab='main', _profileData=null;
let _achData=null, _achSort='default', _invSearch='', _themeFilter='all';
let _bpData=null;
let _analyticsSession=(Date.now().toString(36)+Math.random().toString(36).slice(2)).slice(0,16);

// ── Auth ──────────────────────────────────────────────────────────────────────
const sess = () => localStorage.getItem(SK)||'';
const hdrs = () => {
  const h={'content-type':'application/json'};
  if (INIT_DATA) h['x-init-data']=INIT_DATA;
  if (sess()) h['x-session-token']=sess();
  return h;
};
function api(path, opts={}) {
  return fetch(BASE+path,{...opts,headers:{...hdrs(),...(opts.headers||{})}})
    .then(r=>{
      if(r.status===401){localStorage.removeItem(SK);el('login-ov').classList.remove('hidden');return Promise.reject('Войдите снова.');}
      return r.ok?r.json():r.text().then(t=>{
        try{
          const e=JSON.parse(t);
          const d=e.detail;
          const msg=typeof d==='string'?d:Array.isArray(d)?d.map(x=>x.msg||x).join('; '):(d?JSON.stringify(d):'Ошибка');
          return Promise.reject(msg);
        }catch{
          return Promise.reject(t.slice(0,120)||'Ошибка сервера');
        }
      });
    });
}
// L10 (аудит): пропущенный .catch у api() больше не «молчит» — показываем тост,
// чтобы действие без обработки ошибки не выглядело как «ничего не произошло».
window.addEventListener('unhandledrejection', e => {
  const r = e.reason;
  const msg = typeof r === 'string' ? r : (r && r.message) || '';
  if (!msg) return;
  e.preventDefault();
  try { toast(msg, false); } catch (_) {}
});
window.onTelegramWidgetAuth = u => {
  api('/auth/telegram-login',{method:'POST',body:JSON.stringify(u)})
    .then(d=>{localStorage.setItem(SK,d.session_token);_uid=d.user_id||0;el('login-ov').classList.add('hidden');loadProfile();connectWS();})
    .catch(e=>alert('Ошибка: '+e));
};
if (!INIT_DATA && !sess()) el('login-ov').classList.remove('hidden');

// ── WebSocket ─────────────────────────────────────────────────────────────────
let _ws=null;
// connectWS() defined later with browser-notification + ping/pong support
function showWsNotif(event) {
  const titles = {
    expedition_done: '⚔️ Поход завершён!',
    quest_done: '✅ Квест выполнен!',
    duel_challenge: '⚔️ Вызов на дуэль!',
  };
  const bodies = {
    expedition_done: e => `${e.pet} вернулся: +${fmt(e.mora)} 🪙 +${e.xp} XP`,
    quest_done: e => `«${e.quest}» — получено!`,
    duel_challenge: e => `@${e.from} ставка ${fmt(e.stake)} 🪙 · Ответьте в чате: бот принять`,
  };
  // Play sound for duel challenge
  if(event.type === 'duel_challenge') {
    if('vibrate' in navigator) navigator.vibrate([200, 100, 200]);
    browserNotif('⚔️ Вызов на дуэль!', bodies.duel_challenge(event));
    // Auto-reload duels if on arena page
    if(_loaded.has('arena') && _arenaTab === 'duels') loadDuels();
  }
  // Подарок от администрации → коробка-сюрприз (БЛОК 3.4)
  if (event.type === 'admin_gift') { showGiftBox([event]); return; }
  // Подарок от супруга (Block 5.4) → романтическая коробка
  if (event.type === 'partner_gift') {
    showPartnerGift([event]);
    if (_loaded.has('profile')) loadMarriageCard();
    return;
  }
  // Возврат питомца из похода → «чек награды» (БЛОК 3) вместо углового уведомления
  if (event.type === 'expedition_done') {
    showExpeditionReceipt(event);
    if (_loaded.has('zoo')) { _zooData = null; loadZoo(); }
    return;
  }
  const div = document.createElement('div');
  div.className = 'ws-notif';
  div.innerHTML = `<div class="wn-title">${titles[event.type]||'🔮 Уведомление'}</div>
                   <div class="wn-body">${(bodies[event.type]||(() => ''))(event)}</div>`;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 5000);
}

// Чек награды экспедиции: база + бонусы (питомцы/реликвии) + итого. Данные —
// из WS-payload expedition_done (services/scheduler.py → expedition.calculate_reward).
function showExpeditionReceipt(e) {
  const bd = e.breakdown || [];
  const baseM = (e.base_mora != null) ? e.base_mora : e.mora;
  const baseX = (e.base_xp != null) ? e.base_xp : e.xp;
  const rs = 'display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid var(--border2);font-size:12px';
  let rows = `<div style="${rs}"><span style="color:var(--muted)">🎒 Базовая добыча</span><span>+${fmt(baseM)} 🪙 · +${fmt(baseX)} XP</span></div>`;
  bd.forEach(b => {
    const parts = [];
    if (b.mora)     parts.push(`+${fmt(b.mora)} 🪙`);
    if (b.xp)       parts.push(`+${fmt(b.xp)} XP`);
    if (b.diamonds) parts.push(`+${b.diamonds} 💎`);
    if (b.extra)    parts.push(b.extra);
    rows += `<div style="${rs};color:var(--gold)"><span>${esc(b.label || 'Бонус')}</span><span>${parts.join(' · ') || '—'}</span></div>`;
  });
  const tp = [`+${fmt(e.mora)} 🪙`, `+${fmt(e.xp)} XP`];
  if (e.diamonds) tp.push(`+${e.diamonds} 💎`);
  OM(`🎉 ${esc(e.pet || 'Питомец')} вернулся!`,
    `<div style="margin-bottom:6px">${rows}
       <div style="display:flex;justify-content:space-between;gap:10px;padding:7px 0 0;font-size:13px;font-weight:700;color:var(--gold2)"><span>Итого</span><span>${tp.join(' · ')}</span></div>
     </div>
     <div style="font-size:10px;color:var(--green);text-align:center">✓ Награда уже зачислена</div>`,
    [{l:'🎁 Забрать', c:'btn-gold', f:'CM();_nextModal()'}]);
}

// Очередь модалок: если при входе ждут и подарки, и чеки походов — показываем
// по очереди (кнопка каждой модалки зовёт _nextModal), а не клобберим друг друга.
let _modalQueue = [];
function _runModalQueue(queue) { _modalQueue = queue || []; _nextModal(); }
function _nextModal() { const fn = _modalQueue.shift(); if (fn) fn(); }

// Welcome Back (БЛОК 3.3) + админ-подарки (БЛОК 3.4): то, что накопилось офлайн.
// Бэкенд копит в web_notifications (если WS не доставил онлайн).
function loadPendingNotifications() {
  api('/notifications/pending').then(r => {
    const list = r.notifications || [];
    if (!list.length) return;
    const ids = list.map(n => n.id);
    api('/notifications/seen', {method:'POST', body: JSON.stringify({ids})}).catch(() => {});
    const payloads = list.map(n => n.payload || {});
    const gifts = payloads.filter(p => p.type === 'admin_gift');
    const pgifts = payloads.filter(p => p.type === 'partner_gift');
    const exped = payloads.filter(p => p.type === 'expedition_done');
    const queue = [];
    if (gifts.length) queue.push(() => showGiftBox(gifts));        // подарки — приоритет
    pgifts.forEach(p => queue.push(() => showPartnerGift([p])));    // подарки от супруга
    if (exped.length) queue.push(() => showWelcomeBack(exped));
    _runModalQueue(queue);
  }).catch(() => {});
}
// Коробка-подарок от Администрации (БЛОК 3.4). payloads: [{reason, gifts:[{label,amount}]}]
function showGiftBox(payloads) {
  const rs = 'display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px solid var(--border2);font-size:13px';
  let body = '';
  (payloads || []).forEach(p => {
    const items = (p.gifts || []).map(g =>
      `<div style="${rs}"><span>${esc(g.label || 'Награда')}</span><span style="color:var(--gold2);font-weight:700">+${fmt(g.amount)}</span></div>`
    ).join('');
    const reason = (p.reason || '').trim();
    body += `<div style="margin-bottom:10px">${items}
      ${reason ? `<div style="font-size:11px;color:var(--muted);margin-top:6px">📝 Причина: <span style="color:var(--bright)">${esc(reason)}</span></div>` : ''}</div>`;
  });
  OM('🎁 Награда от Администрации!',
    `<div style="text-align:center;font-size:46px;margin:2px 0 10px;animation:floaty 1.6s ease-in-out infinite">🎁</div>
     ${body}
     <div style="font-size:10px;color:var(--green);text-align:center;margin-top:2px">✓ Уже у тебя в профиле</div>`,
    [{l:'🎉 Забрать!', c:'btn-gold', f:'CM();_nextModal()'}]);
}
function showWelcomeBack(items) {
  if (items.length === 1) { showExpeditionReceipt(items[0]); return; }
  let totM = 0, totX = 0, totD = 0;
  const rs = 'display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid var(--border2);font-size:12px';
  const rows = items.map(e => {
    totM += e.mora || 0; totX += e.xp || 0; totD += e.diamonds || 0;
    const parts = [`+${fmt(e.mora || 0)} 🪙`, `+${fmt(e.xp || 0)} XP`];
    if (e.diamonds) parts.push(`+${e.diamonds} 💎`);
    return `<div style="${rs}"><span>🐾 ${esc(e.pet || 'Питомец')}</span><span style="color:var(--gold)">${parts.join(' · ')}</span></div>`;
  }).join('');
  const tp = [`+${fmt(totM)} 🪙`, `+${fmt(totX)} XP`];
  if (totD) tp.push(`+${totD} 💎`);
  OM('🎉 С возвращением!',
    `<div style="font-size:12px;color:var(--muted);margin-bottom:8px">Пока тебя не было, питомцев вернулось: <b style="color:var(--bright)">${items.length}</b></div>
     <div style="margin-bottom:6px">${rows}
       <div style="display:flex;justify-content:space-between;gap:10px;padding:7px 0 0;font-size:13px;font-weight:700;color:var(--gold2)"><span>Итого</span><span>${tp.join(' · ')}</span></div>
     </div>
     <div style="font-size:10px;color:var(--green);text-align:center">✓ Всё уже зачислено</div>`,
    [{l:'🎁 Отлично!', c:'btn-gold', f:'CM();_nextModal()'}]);
}

// Левел-ап игрока (БЛОК 3): детект между загрузками профиля + торжественная модалка.
// Триггера в реальном времени нет (уровень растёт от чата на стороне бота), поэтому
// сравниваем уровень с прошлой загрузкой (localStorage). _xpAnimated — флаг анимации
// заливки XP-шкалы (один раз за сессию), объявлен здесь до первого вызова loadProfile.
let _xpAnimated = false;
function _checkLevelUp(lvl) {
  try {
    const prev = parseInt(localStorage.getItem('pv_last_level') || '0');
    localStorage.setItem('pv_last_level', String(lvl));
    if (prev && lvl > prev) showLevelUp(lvl);
  } catch (e) {}
}
function showLevelUp(lvl) {
  if ('vibrate' in navigator) navigator.vibrate([100, 50, 100]);
  OM('🎉 Новый уровень!',
    `<div style="text-align:center;padding:6px 0">
       <div style="font-size:54px;animation:floaty 1.6s ease-in-out infinite">⭐</div>
       <div style="font-size:30px;font-weight:800;color:var(--gold2);margin:6px 0">Уровень ${lvl}</div>
       <div style="font-size:12px;color:var(--muted)">Так держать! Общайся в чате, чтобы расти дальше.</div>
     </div>`,
    [{l:'🔥 Дальше!', c:'btn-gold', f:'CM()'}]);
}

// ── Utils ─────────────────────────────────────────────────────────────────────
const fmt = n => Number(n).toLocaleString('ru');
// Float-формат валют/цен: разделители тысяч + до 2 знаков после запятой (без хвостовых нулей).
const fmtF = n => (Number(n)||0).toLocaleString('ru',{maximumFractionDigits:2});
function vipName(name, isVip) { return isVip ? `👑 ${name}` : name; }
function fmtUTC(s) {
  if (!s) return '';
  const d = new Date(s.includes('T') ? s : s.replace(' ', 'T') + 'Z');
  return isNaN(d) ? s.slice(0,16) : d.toLocaleString('ru-RU', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
}
const fatC = f => f<40?'var(--green)':f<70?'var(--gold)':'var(--red)';
function rc(r) { return `<span class="rc ${RC[r]||'rc-common'}">${r}</span>`; }

function toast(msg,ok=true) {
  const t=el('toast');
  // showModal() puts dialog in the browser top-layer above all z-indexes.
  // Moving the toast node inside the open dialog keeps it visible above the overlay.
  const dlg=el('modal');
  if(dlg&&dlg.open){if(t.parentElement!==dlg)dlg.appendChild(t);}
  else{if(t.parentElement!==document.body)document.body.appendChild(t);}
  t.textContent=msg;
  t.style.cssText=`background:${ok?'rgba(82,179,96,.9)':'rgba(224,82,82,.9)'};color:#fff;border:1px solid ${ok?'rgba(82,179,96,.5)':'rgba(224,82,82,.5)'}`;
  t.classList.remove('show'); void t.offsetWidth; t.classList.add('show');
  clearTimeout(t._tid);t._tid=setTimeout(()=>t.classList.remove('show'),2500);
}

function copyUid(uid) {
  navigator.clipboard?.writeText(String(uid))
    .then(()=>toast('🆔 ID скопирован!'))
    .catch(()=>toast('Буфер обмена недоступен',false));
}

// Дедлайн экспедиции: строится ОДИН раз из серверного remaining_sec (разность
// внутри БД — не зависит ни от таймзоны naive-строки ends_at, ни от часов
// устройства игрока; фикс бага «Готово ✓» при ещё идущем походе). Парсинг
// абсолютной строки — только фолбэк для старых/кэшированных ответов без поля.
function expDeadlineMs(e){
  if(e._dl===undefined){
    e._dl=(typeof e.remaining_sec==='number')
      ? Date.now()+e.remaining_sec*1000
      : new Date((e.ends_at+'').includes('T')?e.ends_at:e.ends_at+'Z').getTime();
  }
  return e._dl;
}
function countdownMs(deadlineMs) {
  const diff=Math.max(0,Math.floor((deadlineMs-Date.now())/1000));
  if(diff<=0)return'<span style="color:var(--green)">Готово ✓</span>';
  const h=Math.floor(diff/3600),m=Math.floor((diff%3600)/60),s=diff%60;
  const str=h?`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${m}:${String(s).padStart(2,'0')}`;
  return `<span class="exp-timer${diff<300?' urgent':''}">${str}</span>`;
}
// Короткая длительность для подписей: «2ч 15м» / «45м»
function fmtDurShort(sec){
  sec=Math.max(0,Math.floor(sec||0));
  const h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60);
  return h?`${h}ч ${String(m).padStart(2,'0')}м`:`${m}м`;
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function OM(title,body,btns=[]) {
  el('mt').textContent=title;
  el('mb').innerHTML=body;
  el('mf').innerHTML=btns.map(b=>`<button class="btn btn-sm ${b.c||'btn-ghost'}" onclick="${b.f}" ${b.d?'disabled':''}>${b.l}</button>`).join('');
  el('modal').showModal();
  document.body.classList.add('modal-open');
}
const CM=()=>{
  el('modal').close();document.body.classList.remove('modal-open');
  // R5: закрытие модалки = выход из live-комнаты лота (объявлена в app.06 —
  // к моменту клика склейка загружена целиком, hoisting function declaration)
  try{ if(typeof lotLiveLeave==='function') lotLiveLeave(); }catch(e){}
  // Move toast back to body in case it was reparented inside the dialog for z-order
  const t=el('toast');if(t&&t.parentElement!==document.body)document.body.appendChild(t);
};
el('modal').addEventListener('click',e=>{if(e.target===el('modal'))CM();});
el('modal').addEventListener('cancel',()=>{document.body.classList.remove('modal-open');const t=el('toast');if(t&&t.parentElement!==document.body)document.body.appendChild(t);});

// ── Navigation ────────────────────────────────────────────────────────────────
const _loaded=new Set();
// Единая маршрутизация по ИМЕНИ страницы. Подсветка нижнего дока — по data-page;
// вторичные разделы (открытые через «Ещё») подсвечивают «Ещё».
let _activePage = 'profile';
const _PAGE_LOADERS = {
  zoo:loadZoo, arena:loadArena, market:loadMarket,
  bp:loadBattlePass, auction:loadAuctionPage,
  admin:loadAdmin, global:loadGlobal, help:()=>{}
};

// Карта page→flag_key: только те страницы, которые управляются ползунком в dev-консоли.
const _PAGE_FLAG = {zoo:'tab_zoo', market:'tab_market', bp:'tab_bp', auction:'tab_auction'};
let _sysFlags = {};  // заполняется из /profile/me (system_flags) при loadProfile()
function _applySysFlags(flagsList) {
  _sysFlags = Object.fromEntries((flagsList||[]).map(f=>[f.key,!!f.enabled]));
}
function _isPageEnabled(name) {
  const key = _PAGE_FLAG[name];
  if(!key) return true;
  return _sysFlags[key] !== false;  // undefined = ещё не загружено → разрешаем
}
function _showMaintenance(pg) {
  const box = el('pg-'+pg); if(!box) return;
  box.innerHTML=`<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:40vh;gap:12px;padding:32px 16px">
    <div style="font-size:40px">🚧</div>
    <div style="font-size:17px;font-weight:700;color:var(--bright)">Временно недоступно</div>
    <div style="font-size:12px;color:var(--muted);text-align:center">Этот раздел отключён разработчиком.<br>Попробуйте позже.</div>
  </div>`;
}

function switchPage(name, _btn) {
  if(!el('pg-'+name)) return;
  _activePage = name;
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nb').forEach(b=>b.classList.remove('active'));
  el('pg-'+name).classList.add('active');
  const prim = document.querySelector(`.nb[data-page="${name}"]`);
  (prim || el('nb-more'))?.classList.add('active');
  showCurrBar(name !== 'profile');
  document.body.classList.toggle('pg-wide', name === 'global');
  try { window.scrollTo(0, 0); } catch(e) {}
  api('/analytics/tab',{method:'POST',body:JSON.stringify({tab:name,session_id:_analyticsSession})}).catch(()=>{});
  if(!_loaded.has(name)){
    _loaded.add(name);
    if(!_isPageEnabled(name)){ _showMaintenance(name); return; }
    (_PAGE_LOADERS[name] || (() => {}))();
  }
}
function _trackSubtab(path){api('/analytics/tab',{method:'POST',body:JSON.stringify({tab:path,session_id:_analyticsSession})}).catch(()=>{});}

// Хартбит времени удержания — раз в 15с, ТОЛЬКО пока вкладка реально видима на экране
// (не в фоне/свёрнут Telegram) — копится на бэке в ту же строку визита, что завёл switchPage.
setInterval(()=>{
  if(document.visibilityState!=='visible' || !_activePage) return;
  api('/analytics/tab-duration',{method:'POST',body:JSON.stringify({tab:_activePage,session_id:_analyticsSession,delta_sec:15})}).catch(()=>{});
},15000);

// Единая программная навигация — шорткаты в карточках/модалках.
// goTo('zoo') · goTo('quests','streak') · goTo('market','gacha')
// Закрывает открытую модалку/меню (CM) — нужно для шорткатов внутри окон.
function goTo(page, tab) {
  CM();
  // Редиректы: страницы, которые переехали в подвкладки других разделов
  if (page==='quests'||page==='ach'||page==='hof') {
    const proTab = page==='hof'?'hof':page==='ach'?'ach':'quests';
    switchPage('profile');
    setTimeout(()=>{
      const btn = document.querySelector(`#pg-profile > .tabs > .tb[onclick*="'${proTab}'"]`);
      if(btn) btn.click();
      if(tab) setTimeout(()=>{
        const sub = document.querySelector(`#pro-${proTab} .tab-inner .tb[onclick*="'${tab}'"]`);
        if(sub) sub.click();
      },80);
    },80);
    return;
  }
  if (page==='bestiary') {
    switchPage('zoo');
    setTimeout(()=>{ const b=document.querySelector('#pg-zoo > .tabs > .tb[onclick*="bestiary"]'); if(b) b.click(); },80);
    return;
  }
  if (page==='craft') {
    switchPage('profile');
    setTimeout(()=>{
      const b=document.querySelector("#pg-profile > .tabs > .tb[onclick*=\"'inv'\"]"); if(b) b.click();
      setTimeout(()=>{ const c=document.querySelector("#pro-inv .tab-inner .tb[onclick*=\"'craft'\"]"); if(c) c.click(); },80);
    },80);
    return;
  }
  switchPage(page);
  if (tab) setTimeout(() => {
    const tabBtn = document.querySelector(`#pg-${page} .tb[onclick*="'${tab}'"]`);
    if (tabBtn) tabBtn.click();
  }, 80);
}

// ── «Ещё» — Control Center: карточка «Управление» ведёт в Админку/Модерацию ────
function openManageMenu() {
  const isAdmin = !!(_adminChats && _adminChats.length);
  const gRank = _profileData?.global_rank || 0;
  if (isAdmin && gRank>=1) {
    OM('⚙️ Управление', `<div class="more-grid">
      <div class="more-card" onclick="goTo('admin')"><span class="mc-ic">🛡</span><span class="mc-t">Админка чата</span><span class="mc-s">Модерация</span></div>
      <div class="more-card" onclick="goTo('global')"><span class="mc-ic">🌍</span><span class="mc-t">Глобальная</span><span class="mc-s">Сеть чатов</span></div>
    </div>`, []);
  } else if (isAdmin) goTo('admin');
  else if (gRank>=1) goTo('global');
}
function _updateMoreCard() {
  const staff = (_adminChats && _adminChats.length) || (_profileData?.global_rank||0) >= 1;
  const c = el('cc-manage');
  if(c) c.style.display = staff ? '' : 'none';
  const hs = el('help-staff');
  if(hs) hs.style.display = staff ? '' : 'none';
}

