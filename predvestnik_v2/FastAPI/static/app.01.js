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
const UK = 'pv_uid';
// Смена активного Telegram-аккаунта в приложении: если initData сейчас называет
// другого пользователя, чем закэширован pv_uid — старый браузерный токен (7 дней,
// x-session-token) мог остаться от прошлого аккаунта на этом же устройстве.
// initData всегда в приоритете на сервере (deps.py), но чистим клиентский кэш
// проактивно — иначе при последующем открытии сайта БЕЗ Telegram (чистый браузер)
// снова подхватится чужая сессия.
(() => {
  const tgUid = tg?.initDataUnsafe?.user?.id || 0;
  if (!tgUid) return;
  const cachedUid = parseInt(localStorage.getItem(UK) || '0', 10);
  if (cachedUid && cachedUid !== tgUid) {
    localStorage.removeItem(SK);
    localStorage.removeItem(UK);
  }
})();
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

// _arenaTab: дефолт 'barracks' (Боёвка 3.0) — вкладки «duels» в Арене больше нет (GAME_BIBLE
// находка №8: 'duels' скрывал обе панели при первом открытии Арены)
let _cid = 0, _uid = 0, _actTab='duels', _zooTab='nursery', _arenaTab='barracks';
let _zooData=null, _invData=[], _expTimer=null, _themeData=null, _mktTab='gacha';
let _proTab='main', _profileData=null;
let _achData=null, _achSort='default', _invSearch='', _themeFilter='all';
let _bpData=null;
let _analyticsSession=(Date.now().toString(36)+Math.random().toString(36).slice(2)).slice(0,16);

// ── Auth ──────────────────────────────────────────────────────────────────────
const sess = () => localStorage.getItem(SK)||'';
// Лёгкий отпечаток браузера (НЕ криптостойкий, только для дедупа на твинк-детекте
// дев-консоли — сервер всё равно солит HMAC-ом перед записью в БД, см. auth.hash_signal).
const CLIENT_FP = (() => {
  try {
    const raw = [navigator.userAgent, navigator.language, screen.width+'x'+screen.height,
      Intl.DateTimeFormat().resolvedOptions().timeZone, navigator.platform||''].join('|');
    let h = 0;
    for (let i = 0; i < raw.length; i++) { h = (Math.imul(31, h) + raw.charCodeAt(i)) | 0; }
    return 'fp_' + (h >>> 0).toString(36);
  } catch (e) { return ''; }
})();
const hdrs = () => {
  const h={'content-type':'application/json'};
  if (INIT_DATA) h['x-init-data']=INIT_DATA;
  if (sess()) h['x-session-token']=sess();
  if (CLIENT_FP) h['x-client-fp']=CLIENT_FP;
  return h;
};
// Авто-refresh (реактивный слой): после успешного мутирующего запроса раз в ~350мс
// (debounce, чтобы серия действий не долбила сервер) подтягиваем бар валют + счётчики,
// чтобы мора/алмазы/зарники/🌑 обновлялись сами, без ручной перезагрузки страницы.
// Подписчики (напр. экран гачи) регистрируют колбэк через onReactiveRefresh().
let _reactiveTimer=null;
const _reactiveSubs=new Set();
function onReactiveRefresh(fn){ if(typeof fn==='function') _reactiveSubs.add(fn); return fn; }
function offReactiveRefresh(fn){ _reactiveSubs.delete(fn); }
function _scheduleReactiveRefresh(){
  if(_reactiveTimer) clearTimeout(_reactiveTimer);
  _reactiveTimer=setTimeout(()=>{
    _reactiveTimer=null;
    try{ if(typeof refreshCurrBar==='function') refreshCurrBar(); }catch(_){}
    _reactiveSubs.forEach(fn=>{ try{ fn(); }catch(_){} });
  }, 350);
}
function api(path, opts={}) {
  return fetch(BASE+path,{...opts,headers:{...hdrs(),...(opts.headers||{})}})
    .then(r=>{
      if(r.status===401){localStorage.removeItem(SK);el('login-ov').classList.remove('hidden');return Promise.reject('Войдите снова.');}
      // авто-refresh только на успешных мутациях; GET/аналитику/сам /profile/me не триггерим (без петель)
      const _m=(opts.method||'GET').toUpperCase();
      if(r.ok && _m!=='GET' && path.indexOf('/analytics')!==0 && path.indexOf('/profile/me')!==0) _scheduleReactiveRefresh();
      return r.ok?r.json():r.text().then(t=>{
        try{
          const e=JSON.parse(t);
          const d=e.detail;
          const msg=typeof d==='string'?d:Array.isArray(d)?d.map(x=>x.msg||x).join('; '):(d?JSON.stringify(d):'Ошибка');
          // admin_audit B1: глобальный бан — вместо голого 403 открываем форму апелляции
          if(r.status===403&&typeof msg==='string'&&msg.indexOf('GLOBAL_BAN')===0&&path.indexOf('/appeals')!==0){
            try{ if(typeof openBanAppealModal==='function') openBanAppealModal(); }catch(e2){}
            return Promise.reject(msg.replace('GLOBAL_BAN: ',''));
          }
          return Promise.reject(_humanErr(msg, r.status));
        }catch{
          try{ console.warn('API raw error hidden:', t.slice(0,300)); }catch(_){ }
          return Promise.reject(r.status>=500?'Сервер прилёг отдохнуть. Попробуй через минуту.':'Ошибка сервера');
        }
      });
    });
}
// UX_AUDIT С9: сырые/англоязычные detail (Pydantic и пр.) не долетают до игрока.
// Русские сообщения сервера показываем как есть, техжаргон — прячем в консоль.
function _humanErr(msg, status){
  if(typeof msg!=='string'||!msg) return 'Что-то пошло не так. Попробуй ещё раз.';
  const latin=(msg.match(/[a-zA-Z]/g)||[]).length;
  const cyr=(msg.match(/[а-яА-ЯёЁ]/g)||[]).length;
  if(msg[0]==='{'||msg[0]==='['||(latin>8&&latin>cyr*2)){
    try{ console.warn('API detail hidden:', msg); }catch(_){ }
    return status>=500?'Сервер прилёг отдохнуть. Попробуй через минуту.'
                      :'Не получилось: проверь данные и попробуй ещё раз.';
  }
  return msg;
}
// L10 (аудит): пропущенный .catch у api() больше не «молчит» — показываем тост,
// чтобы действие без обработки ошибки не выглядело как «ничего не произошло».
window.addEventListener('unhandledrejection', e => {
  const r = e.reason;
  // Строки — наши осмысленные reject'ы из api(), их показываем как есть.
  if (typeof r === 'string') {
    if (!r) return;
    e.preventDefault();
    try { toast(r, false); } catch (_) {}
    return;
  }
  // UX_AUDIT С10: сырые JS-исключения (Error.message на английском с внутренностями
  // кода) игроку не показываем — только в консоль, игроку — человеческий текст.
  e.preventDefault();
  try { console.error('unhandled rejection:', r); } catch (_) {}
  try { toast('Что-то пошло не так. Если повторится — обнови страницу.', false); } catch (_) {}
});
window.onTelegramWidgetAuth = u => {
  const errBox=el('login-err');
  if(errBox) errBox.classList.add('hidden');
  api('/auth/telegram-login',{method:'POST',body:JSON.stringify(u)})
    .then(d=>{localStorage.setItem(SK,d.session_token);localStorage.setItem(UK,String(d.user_id||0));_uid=d.user_id||0;el('login-ov').classList.add('hidden');loadProfile();connectWS();})
    .catch(err=>{
      // UX_AUDIT С1: оформленное сообщение вместо нативного alert()
      if(errBox){ errBox.textContent='Не получилось войти: '+err+' Попробуйте ещё раз.'; errBox.classList.remove('hidden'); }
      else { try{ toast('Не получилось войти: '+err, false); }catch(_){} }
    });
};
if (!INIT_DATA && !sess()) el('login-ov').classList.remove('hidden');
// Явная смена Telegram-аккаунта в браузере (Настройки → Аккаунт). Внутри Telegram
// кнопка скрыта — там аккаунт и так всегда актуальный (initData подписывается заново
// при каждом запуске мини-аппа). В чистом браузере Telegram не даёт сайту узнать,
// какой аккаунт сейчас активен на устройстве — поэтому просим один тап в виджете.
function switchTgAccount(){
  localStorage.removeItem(SK);
  localStorage.removeItem(UK);
  location.reload();
}

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
  const earlyNote = e.early_finish
    ? `<div style="font-size:10px;color:var(--muted);text-align:center;margin-top:2px">⚡ Поход завершён досрочно (энергетик/кристалл) — награда −50%</div>` : '';
  OM(`🎉 ${esc(e.pet || 'Питомец')} вернулся!`,
    `<div style="margin-bottom:6px">${rows}
       <div style="display:flex;justify-content:space-between;gap:10px;padding:7px 0 0;font-size:13px;font-weight:700;color:var(--gold2)"><span>Итого</span><span>${tp.join(' · ')}</span></div>
     </div>
     <div style="font-size:10px;color:var(--green);text-align:center">✓ Награда уже зачислена</div>${earlyNote}`,
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
    const petLabel = (e.early_finish ? '⚡ ' : '🐾 ') + esc(e.pet || 'Питомец');
    return `<div style="${rs}"><span>${petLabel}</span><span style="color:var(--gold)">${parts.join(' · ')}</span></div>`;
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
// EPIC1: набегающий счётчик ⚡ Индекса Силы (rAF, ease-out) — тоже 1 раз за сессию,
// чтобы фоновый автообновление профиля (каждые 5 мин) не переигрывало анимацию.
let _cpAnimated = false;
function _animateCpCount(nodeId, target, dur) {
  const node = el(nodeId);
  if (!node) return;
  target = Number(target) || 0;
  dur = dur || 900;
  if (!target) { node.textContent = '0'; return; }
  const t0 = performance.now();
  function step(t) {
    const p = Math.min(1, (t - t0) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    node.textContent = fmt(Math.round(target * eased));
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}
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
  t.style.cssText=`background:${ok?'rgba(86,196,106,.92)':'rgba(239,99,99,.92)'};color:#fff;border:1px solid ${ok?'rgba(86,196,106,.5)':'rgba(239,99,99,.5)'}`;
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
  // Кавычки в onclick-строке (JSON.stringify-аргументы и т.п.) рвали HTML-атрибут —
  // кнопка молча умирала (напр. «Да, начать» чистку с выбранными датами).
  el('mf').innerHTML=btns.map(b=>`<button class="btn btn-sm ${b.c||'btn-ghost'}" onclick="${String(b.f||'').replace(/"/g,'&quot;')}" ${b.d?'disabled':''}>${b.l}</button>`).join('');
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

// EPIC6: базовый haptic на КАЖДОЙ кнопке .btn — один делегированный листенер
// вместо ручной расстановки _haptic() по сотням onclick по всему приложению.
// Сжатие scale(.95) уже глобально висит на .btn:active (чистый CSS, см. app.css).
// Фичи со своей семантикой (success/error/heavy) вызывают _haptic() сами в ответ
// на результат — этот тап лёгкий и мгновенный, не конфликтует с ними.
document.addEventListener('click', e => {
  const b = e.target.closest('.btn');
  if (b && !b.disabled && typeof _haptic === 'function') _haptic('light');
}, true);

// UX_AUDIT С12: маска «справа есть ещё» — на ЛЮБОМ ряду вкладок, который реально
// переполнился (а не только на размеченных вручную). Ряды рендерятся динамически,
// поэтому пересчёт — после кликов (когда контент дорисовался) и на resize.
function _updateTabMasks(){
  document.querySelectorAll('.tabs').forEach(t=>{
    t.classList.toggle('tabs-scroll', t.scrollWidth > t.clientWidth + 4);
  });
}
window.addEventListener('resize', _updateTabMasks);
window.addEventListener('load', _updateTabMasks);
document.addEventListener('click', ()=>{ setTimeout(_updateTabMasks, 350); }, true);

// ── Navigation ────────────────────────────────────────────────────────────────
const _loaded=new Set();
// Единая маршрутизация по ИМЕНИ страницы. Подсветка нижнего дока — по data-page;
// вторичные разделы (открытые через «Ещё») подсвечивают «Ещё».
let _activePage = 'profile';
const _PAGE_LOADERS = {
  zoo:loadZoo, arena:loadArena, market:loadMarket,
  bp:loadBattlePass, auction:loadAuctionPage,
  admin:loadAdmin, global:loadGlobal, console:loadConsole, help:()=>{},
  news:loadWhatsNew
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
  document.body.classList.toggle('pg-wide', name === 'global' || name === 'console');
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

// ── «Ещё» — Control Center: карточка «Управление» ведёт в Админку/Глобальную/Консоль ──
// БЛОК 21.2 W4.1: три полноценных входа; Консоль — по правам (gp из app.07),
// с фолбэком на ранг 3, пока my-permissions не подгрузились.
function _canConsole() {
  // _gPerms/gpAny объявлены в app.07 — в склейке это один скрипт, в рантайме доступны.
  if (_gPerms) return gpAny(_CONSOLE_PERMS);
  return (_profileData?.global_rank || 0) >= 3;
}
function openManageMenu() {
  const isAdmin = !!(_adminChats && _adminChats.length);
  const gRank = _profileData?.global_rank || 0;
  const cards = [];
  if (isAdmin) cards.push(`<div class="more-card" onclick="goTo('admin')"><span class="mc-ic">🛡</span><span class="mc-t">Админка чата</span><span class="mc-s">Модерация</span></div>`);
  if (gRank>=1) cards.push(`<div class="more-card" onclick="goTo('global')"><span class="mc-ic">🌍</span><span class="mc-t">Глобальная</span><span class="mc-s">Сеть чатов</span></div>`);
  if (_canConsole()) cards.push(`<div class="more-card" onclick="goTo('console')"><span class="mc-ic">🛠</span><span class="mc-t">Консоль</span><span class="mc-s">Разработка</span></div>`);
  if (cards.length > 1) OM('⚙️ Управление', `<div class="more-grid">${cards.join('')}</div>`, []);
  else if (isAdmin) goTo('admin');
  else if (gRank>=1) goTo('global');
}
function _updateMoreCard() {
  const staff = (_adminChats && _adminChats.length) || (_profileData?.global_rank||0) >= 1;
  const c = el('cc-manage');
  if(c) c.style.display = staff ? '' : 'none';
  const hs = el('help-staff');
  if(hs) hs.style.display = staff ? '' : 'none';
  // W4.3: бейдж ⏳ новых апелляций на карточке «Управление» (счётчик из my-permissions)
  const b = el('cc-manage-badge');
  if(b) {
    const n = (typeof _gCounts !== 'undefined' && _gCounts ? _gCounts.appeals_pending : 0) || 0;
    b.style.display = n > 0 ? '' : 'none';
    b.textContent = n > 99 ? '99+' : String(n);
  }
}

