const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }  // setHeaderColor removed — deprecated in TG WebApp v6.0

const BASE = (location.origin + location.pathname).replace(/[/]$/, '');

// el() defined here — BEFORE any usage to avoid TDZ ReferenceError
const el = id => document.getElementById(id);
const INIT_DATA = tg?.initData || '';
const SK = 'pv_sess';
const MEDALS = ['🥇','🥈','🥉'];
const PL = {active:'Активный',passive:'Пассивный',storage:'Склад'};
const RC = {common:'rc-common',uncommon:'rc-uncommon',rare:'rc-rare',
            epic:'rc-epic',legendary:'rc-legendary',shadow:'rc-shadow',mythic:'rc-mythic'};

// Chat where the mini app was opened from: bot encodes ?chat_id= for group
// launches (Telegram WebApp context alone isn't reliable for group buttons).
const _tgChat = tg?.initDataUnsafe?.chat || null;
const _urlChatId = parseInt(new URLSearchParams(location.search).get('chat_id') || '0', 10) || 0;
const _initChatId = _urlChatId || _tgChat?.id || 0;   // primary chat_id for local data
const _initChatTitle = _tgChat?.title || '';

let _cid = 0, _uid = 0, _actTab='duels', _zooTab='nursery', _arenaTab='duels';
let _zooData=null, _invData=[], _expTimer=null, _themeData=null, _mktTab='vip';
let _proTab='main', _profileData=null;
let _achData=null, _achSort='default', _invSearch='', _themeFilter='all';
let _bpData=null;

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
  const div = document.createElement('div');
  div.className = 'ws-notif';
  div.innerHTML = `<div class="wn-title">${titles[event.type]||'🔮 Уведомление'}</div>
                   <div class="wn-body">${(bodies[event.type]||(() => ''))(event)}</div>`;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 5000);
  if (_loaded.has('zoo') && event.type === 'expedition_done') { _zooData=null; loadZoo(); }
}

// ── Utils ─────────────────────────────────────────────────────────────────────
const fmt = n => Number(n).toLocaleString('ru');
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
  t.classList.add('show');
  clearTimeout(t._tid);t._tid=setTimeout(()=>t.classList.remove('show'),2500);
}

function copyUid(uid) {
  navigator.clipboard?.writeText(String(uid))
    .then(()=>toast('🆔 ID скопирован!'))
    .catch(()=>toast('Буфер обмена недоступен',false));
}

function countdown(endsAt) {
  const ends=new Date((endsAt+'').includes('T')?endsAt:endsAt+'Z');
  const diff=Math.max(0,Math.floor((ends-Date.now())/1000));
  if(diff<=0)return'<span style="color:var(--green)">Готово ✓</span>';
  const h=Math.floor(diff/3600),m=Math.floor((diff%3600)/60),s=diff%60;
  const str=h?`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${m}:${String(s).padStart(2,'0')}`;
  return `<span class="exp-timer${diff<300?' urgent':''}">${str}</span>`;
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
  quests:loadQuestsPage, bp:loadBattlePass, ach:loadAch, bestiary:renderZooGuide,
  craft:loadCraft, auction:loadAuctionPage, hof:loadTop,
  admin:loadAdmin, global:loadGlobal, help:()=>{}
};
function switchPage(name, _btn) {
  if(!el('pg-'+name)) return;
  _activePage = name;
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nb').forEach(b=>b.classList.remove('active'));
  el('pg-'+name).classList.add('active');
  const prim = document.querySelector(`.nb[data-page="${name}"]`);
  (prim || el('nb-more'))?.classList.add('active');
  showCurrBar(name !== 'profile');
  try { window.scrollTo(0, 0); } catch(e) {}
  if(!_loaded.has(name)){
    _loaded.add(name);
    (_PAGE_LOADERS[name] || (() => {}))();
  }
}

// Единая программная навигация — шорткаты в карточках/модалках.
// goTo('zoo') · goTo('quests','streak') · goTo('market','gacha')
// Закрывает открытую модалку/меню (CM) — нужно для шорткатов внутри окон.
function goTo(page, tab) {
  CM();
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

// ── Profile ───────────────────────────────────────────────────────────────────
// switchPro() defined later with marriage + wallet tabs
function loadProfile() {
  el('pro-main').innerHTML='<div class="sk" style="height:120px;border-radius:var(--r);margin-bottom:8px"></div><div class="sk" style="height:60px;border-radius:var(--r)"></div>';
  api('/profile/me').then(d=>{
    if(!d || typeof d !== 'object') throw new Error('Неверный формат ответа сервера');
    _cid = _initChatId || d.chats?.[0]?.chat_tg_id || 0;
    if(d.user_id) _uid = d.user_id;
    _profileData = d;
    const pets=d.pets.filter(p=>p.placement!=='storage').slice(0,6);
    const uid = d.user_id || _uid;
    const lvl = d.chats?.[0]?.user_level || 1;
    const xp = d.chats?.[0]?.user_xp || 0;
    const xpInLvl = xp % 3000, xpPct = Math.min(100, Math.round(xpInLvl/3000*100));
    el('pro-main').innerHTML=`
      <div class="hero">
        <div class="hero-head">
          <div class="ava">${d.is_vip?'👑':'🔮'}</div>
          <div style="min-width:0">
            <div class="pname">@${vipName(d.username||'Игрок', d.is_vip)}</div>
            <div class="prank">${d.rank}</div>
          </div>
        </div>
        <div class="hero-xp">
          <div class="xp-bar"><div class="xp-fill" style="width:${xpPct}%"></div></div>
          <div class="xp-lbl"><span>Уровень ${lvl}</span><span>${fmt(xpInLvl)} / 3 000 XP</span></div>
        </div>
        <div class="stats">
          <div class="stat"><div>🪙</div><div class="sv">${fmt(d.mora)}</div><div class="sl">Мора</div></div>
          <div class="stat"><div>💎</div><div class="sv">${d.diamonds.toFixed(1)}</div><div class="sl">Алмазы</div></div>
          <div class="stat clickable" onclick="${(d.zarniki||0)>0?'openExchangeZarnikiModal()':"goTo('market','vip')"}"><div>✨</div><div class="sv">${Math.floor(d.zarniki||0)}</div><div class="sl">${(d.zarniki||0)>0?'Зарники 🔄':'Зарники +'}</div></div>
          <div class="stat clickable" onclick="goTo('ach')"><div>🏆</div><div class="sv">${d.achievements}</div><div class="sl">Ачивки ›</div></div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;padding:9px 0 0;margin-top:11px;border-top:1px solid var(--border2)">
          <span style="font-size:10.5px;color:var(--muted)">🆔 <code>${uid}</code></span>
          <button class="btn btn-ghost btn-sm" style="padding:3px 9px;font-size:10px" onclick="copyUid(${uid})">📋 Копировать</button>
        </div>
      </div>

      <!-- Быстрые действия: всё важное в 1 клик -->
      <div class="qa-row">
        <div class="qa qa-hot" onclick="goTo('quests','streak')"><span>🔥</span>Стрик ${d.streak}</div>
        <div class="qa" onclick="goTo('quests')"><span>📋</span>Квесты</div>
        <div class="qa" onclick="goTo('bp')"><span>🎫</span>Пропуск</div>
        <div class="qa" onclick="goTo('zoo')"><span>🍖</span>Питомцы</div>
      </div>

      ${d.is_vip?'':`<div class="vip-banner" onclick="goTo('market','vip')">
        <span class="vb-crown">👑</span>
        <div><div class="vb-title">Стань VIP</div><div class="vb-sub">Еженедельные подарки, +слот питомника, безлимит ника</div></div>
        <span class="vb-cta">›</span>
      </div>`}

      <!-- Карточка брака (заполняется loadMarriageCard) -->
      <div id="pro-marriage-card"><div class="sk" style="height:90px;border-radius:var(--r)"></div></div>
      <!-- Карточка ника (заполняется loadNickCard) -->
      <div id="pro-nick-card"></div>
      ${pets.length?`<div class="card">
        <div class="card-title">🐾 Питомники</div>
        ${pets.map(p=>`
        <div class="pcard" onclick="goTo('zoo')" style="cursor:pointer"><div class="pcol">
          <div class="pn">${p.name||p.species_id} ${rc(p.rarity)}</div>
          <div class="ps">Lv${p.pet_level} · ${PL[p.placement]}</div>
          <div class="fat-bar"><div class="fat-fill" style="width:${p.fatigue}%;background:${fatC(p.fatigue)}"></div></div>
        </div></div>`).join('')}
        <div class="shortcut-row">
          <span class="shortcut-link" onclick="goTo('zoo')">Управлять питомцами →</span>
        </div>
      </div>`:`<div class="card"><div class="empty-state"><div class="es-icon">🐾</div><div class="es-title">Питомцев пока нет</div><div class="es-sub">Открой яйцо в Гаче, чтобы завести первого</div><button class="btn btn-gold btn-sm" style="margin-top:10px" onclick="goTo('market','gacha')">🎲 Открыть Гачу</button></div></div>`}
      ${d.chats.length?`<div class="card">
        <div class="card-title">💬 Активность</div>
        ${d.chats.map(c=>`<div class="irow"><span class="ik">${c.chat_title||'Чат'}</span><span class="iv">Lv${c.user_level} · ${fmt(c.user_messages_count_all_time)}</span></div>`).join('')}
        <div class="shortcut-row">
          <span class="shortcut-link" onclick="goTo('hof')">Посмотреть топ →</span>
        </div>
      </div>`:''}
      <div id="wallet-mini"></div>`;
    loadMarriageCard();
    loadNickCard();
    loadWalletMini();
    if(!_ws && _uid) connectWS();
    updateCurrBar(d);          // populate sticky currency bar from profile data
    if(!_adminChats) checkAdminAccess();
    checkGlobalAccess();
  }).catch(e=>{el('pro-main').innerHTML=`<div style="color:var(--red);padding:20px;font-size:12px">${typeof e==='string'?e:'Напишите боту чтобы создать профиль.'}</div>`;});
}
if(INIT_DATA||sess()){loadProfile();_loaded.add('profile');}

// ── Sticky currency bar ───────────────────────────────────────────────────────
// Shows 🪙💎🌑✨ at top of screen (hidden on Profile tab)
let _currBarVisible = false;

function updateCurrBar(data) {
  const bar = el('curr-bar');
  if (!bar) return;
  const set = (id, val, fmt2) => { const v=el(id); if(v) v.textContent=fmt2(val); };
  set('cb-mora', Math.floor(data?.mora ?? 0), fmt);
  set('cb-dia',  data?.diamonds ?? 0, n => parseFloat(n).toFixed(1));
  set('cb-dark', Math.floor(data?.dark_mora ?? 0), fmt);
  set('cb-zar',  data?.zarniki ?? 0, n => Math.floor(n).toString());
  // Хедер: имя + уровень/ранг игрока
  if (data?.username !== undefined) {
    const nm=el('hdr-name'); if(nm) nm.textContent=(data.is_vip?'👑 ':'')+(data.username||'Игрок');
    const sub=el('hdr-sub');
    if(sub) sub.textContent=`Lv${data.chats?.[0]?.user_level||1} · 🔥${data.streak||0}`;
    const av=el('hdr-ava'); if(av && data.is_vip) av.textContent='👑';
  }
}

function showCurrModal() {
  const d = _profileData || {};
  const mora = d.mora ?? 0, dia = d.diamonds ?? 0, dark = d.dark_mora ?? 0, zar = d.zarniki ?? 0;
  OM('💰 Валюты', `<div class="curr-modal">
    <div class="cm-block">
      <div class="cm-icon">🪙</div>
      <div class="cm-info">
        <div class="cm-name">Мора <span class="cm-val">${fmt(Math.floor(mora))}</span></div>
        <div class="cm-desc">Основная валюта. Зарабатывай в чатах, дуэлях, квестах и на аукционе.</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">💎</div>
      <div class="cm-info">
        <div class="cm-name">Алмазы <span class="cm-val">${parseFloat(dia).toFixed(1)}</span></div>
        <div class="cm-desc">Премиум валюта. Покупай в Магазине или получай за достижения и ивенты.</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">🌑</div>
      <div class="cm-info">
        <div class="cm-name">Тёмная Мора <span class="cm-val">${fmt(Math.floor(dark))}</span></div>
        <div class="cm-desc">Редкая валюта тёмного рынка. Получай через Контрабанду (раз в 4 дня).</div>
      </div>
    </div>
    <div class="cm-block">
      <div class="cm-icon">✨</div>
      <div class="cm-info">
        <div class="cm-name">Зарники <span class="cm-val">${Math.floor(zar)}</span></div>
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

// Refresh bar data from server (called on a slow timer)
function refreshCurrBar() {
  if (!_uid || !_currBarVisible) return;
  api('/profile/me').then(d => {
    updateCurrBar(d);
    if(d.mora!==undefined) _profileData = {...(_profileData||{}), mora:d.mora, diamonds:d.diamonds};
  }).catch(()=>{});
}
setInterval(refreshCurrBar, 90000); // every 90s

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

function loadStreak() {
  el('pro-streak').innerHTML='<div class="loader">Загрузка...</div>';
  api('/streak/calendar').then(d=>{
    const today=new Date().toISOString().slice(0,10);
    const streak=d.streak||0;

    // Current cycle position
    const cur=calcStreakReward(streak||1);
    const doneInBlock=cur.dayInBlock;   // days completed in current block (1-based = current day)
    const cycleStart=cur.cycle*7;       // streak number of day 1 of current block

    // Build 7-day cycle display
    const cycleHtml=Array.from({length:7},(_,i)=>{
      const dayNum=cycleStart+i+1;      // streak day number (1-indexed)
      const rw=calcStreakReward(dayNum);
      const isDone=(i+1)<doneInBlock;
      const isCurrent=(i+1)===doneInBlock;
      const isBonus=rw.isEnd;
      let cls='sday';
      if(isDone) cls+=' done';
      if(isCurrent) cls+=' current';
      if(isBonus&&!isDone) cls+=' bonus';
      return `<div class="${cls}">
        <div class="sd-num">День ${i+1}</div>
        <div class="sd-mora">${fmt(Math.round(rw.mora))} 🪙</div>
        ${rw.dia>0?`<div class="sd-dia">${rw.dia.toFixed(2)} 💎</div>`:''}
        ${isBonus?'<div class="sd-bonus">★ БОНУС ×4</div>':''}
        ${isDone?'<span class="sd-done">✓</span>':''}
      </div>`;
    }).join('');

    // Next reward (tomorrow's streak)
    const nextRw=calcStreakReward(streak+1);
    const nextIsBonus=nextRw.isEnd;

    el('pro-streak').innerHTML=`
    <div class="card card-gold">
      <div style="text-align:center">
        <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px">Текущий стрик</div>
        <div class="streak-num">${streak} 🔥</div>
        <div style="font-size:11px;color:var(--muted)">дней подряд</div>
      </div>

      <div class="divider"></div>
      <div class="card-title">Награды — цикл ${cur.cycle+1} (дни ${cycleStart+1}–${cycleStart+7})</div>
      <div class="streak-cycle">${cycleHtml}</div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">
        Завтра за день ${streak+1}: <b style="color:var(--gold)">${fmt(Math.round(nextRw.mora))} 🪙${nextRw.dia>0?' + '+nextRw.dia.toFixed(2)+' 💎':''}${nextIsBonus?' ⭐ БОНУС ×4':''}</b>
      </div>
    </div>

    <div class="card" style="margin-top:8px">
      <div class="card-title">Активность — последние 60 дней</div>
      <div class="cal">${d.calendar.map(day=>`<div class="cal-day${day.active?' on':''}${day.date===today?' today':''}" title="${day.active?'✓ '+day.count+' сообщ.':'Нет активности'} (${day.date})"></div>`).join('')}</div>
      <div style="display:flex;gap:12px;margin-top:6px;font-size:10px;color:var(--muted)">
        <span>⬜ Нет</span><span style="color:var(--green)">■ Активен</span><span style="border:1px solid var(--gold);display:inline-block;width:10px;height:10px;vertical-align:middle"></span> Сегодня
      </div>
    </div>`;
  }).catch(e=>{el('pro-streak').innerHTML=`<div style="color:var(--red);padding:10px;font-size:12px">${e}</div>`;});
}

// What each achievement tracks and how to earn it
const ACH_HOW = {
  egg_opener:  {
    how:   'Открывайте яйца питомцев',
    where: 'Инвентарь → нажмите на яйцо → «Открыть»',
    note:  'Засчитывается каждое открытое яйцо любого типа',
  },
  gacha_addict:{
    how:   'Крутите гачу',
    where: 'Арена → Гача → выберите тип крутки',
    note:  'Засчитывается каждый спин, включая жетоны',
  },
  collector:   {
    how:   'Получите новые виды питомцев',
    where: 'Открывайте яйца — каждый новый вид засчитывается',
    note:  'Важен именно НОВЫЙ вид, не дубликаты существующего',
  },
  trainer:     {
    how:   'Прокачайте питомца до максимального Lv10',
    where: 'Открывайте дубликаты одного вида — уровень растёт',
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
      <button class="btn btn-sm ${_achSort==='default'?'btn-gold':'btn-ghost'}" style="padding:3px 7px;font-size:9px" onclick="setAchSort('default')">По умолч.</button>
      <button class="btn btn-sm ${_achSort==='progress'?'btn-gold':'btn-ghost'}" style="padding:3px 7px;font-size:9px" onclick="setAchSort('progress')">% прогресса</button>
      <button class="btn btn-sm ${_achSort==='todo'?'btn-gold':'btn-ghost'}" style="padding:3px 7px;font-size:9px" onclick="setAchSort('todo')">Сначала активные</button>
    </div>
    <div class="card">
      <div class="card-title">Достижения <span style="font-size:9px;font-weight:400;color:${done===achs.length?'var(--green)':'var(--muted)'}">${done} / ${achs.length} ✅</span></div>
      ${achs.map(a=>{
        const hw=ACH_HOW[a.id]||{};
        const fc=a.completed?'high':a.pct>=60?'high':a.pct>=25?'':'low';
        return `<div class="ach-item" style="cursor:pointer" onclick="openAchModal(${JSON.stringify(a).replace(/"/g,"'")})">
          <div class="ach-head">
            <div class="ach-icon">${a.icon}</div>
            <div class="ach-name">${a.name}</div>
            <div class="ach-lvl" style="color:${a.completed?'var(--gold)':a.level>0?'var(--green)':'var(--muted)'}">
              ${a.completed?'★ MAX':a.level>0?`Lv${a.level}`:'—'}
            </div>
          </div>
          <div style="font-size:10px;color:var(--muted);margin-bottom:5px">${hw.how||''}</div>
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
    <div class="irow"><span class="ik">Что нужно</span><span style="color:var(--text);text-align:right;max-width:65%;font-size:11px">${hw.how||'—'}</span></div>
    <div class="irow"><span class="ik">Где</span><span style="color:var(--teal);text-align:right;max-width:65%;font-size:11px">${hw.where||'—'}</span></div>
    ${hw.note?`<div style="background:var(--dim);border-radius:var(--r);padding:8px 10px;margin-top:8px;font-size:11px;color:var(--muted);line-height:1.4">💡 ${hw.note}</div>`:''}
    ${!a.completed&&rwParts?`<div class="irow" style="margin-top:8px"><span class="ik">Награда Lv${a.level+1}</span><span style="color:var(--gold)">${rwParts}</span></div>`:''}
    ${a.completed?`<div style="text-align:center;padding:10px;color:var(--gold);font-size:13px;font-weight:600">🏆 Выполнено полностью!</div>`:''}
  `,[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}

// ── Battle Pass (B5) ─────────────────────────────────────────────────────────
const BP_CELL_STYLE = {
  claimed:      {opacity:'.55', border:'var(--green)'},
  available:    {opacity:'1',   border:'var(--gold)'},
  locked_vip:   {opacity:'.45', border:'var(--border2)'},
  locked_level: {opacity:'.45', border:'var(--border2)'},
};
function loadBattlePass() {
  el('pro-bp').innerHTML='<div class="loader">Загрузка...</div>';
  api('/battle_pass/status').then(d=>{
    _bpData=d;
    renderBattlePass();
  }).catch(e=>{el('pro-bp').innerHTML=`<div style="color:var(--red);padding:10px;font-size:12px">${e}</div>`;});
}
function renderBattlePass() {
  const d=_bpData;
  if(!d) return;
  if(!d.active) {
    el('pro-bp').innerHTML=`<div class="card" style="text-align:center;padding:24px;color:var(--muted);font-size:12px">🎫 Сезон Боевого пропуска скоро начнётся, следи за анонсами!</div>`;
    return;
  }
  const pct=Math.round(d.xp_in_level/d.xp_per_level*100);
  el('pro-bp').innerHTML=`
    <div class="card card-gold" style="margin-bottom:8px">
      <div class="card-title">🎫 ${d.season_label} — Уровень ${d.level}/${d.max_level}</div>
      <div class="ach-bar" style="height:8px"><div class="ach-fill" style="width:${pct}%"></div></div>
      <div class="ach-prog">${d.level>=d.max_level?'★ MAX уровень':`${fmt(d.xp_in_level)} / ${fmt(d.xp_per_level)} XP`}</div>
      ${!d.paid_track_open?'<div style="margin-top:8px;font-size:11px;color:var(--gold2)">👑 VIP-трек закрыт — оформи VIP («бот vip»), чтобы забирать платные награды.</div>':''}
    </div>
    <div class="card">
      <div class="card-title">Награды по уровням</div>
      <div style="display:grid;grid-template-columns:28px 1fr 1fr;gap:6px;font-size:9px;color:var(--muted);margin-bottom:4px">
        <div></div><div>🆓 Бесплатный</div><div>👑 VIP</div>
      </div>
      ${d.rewards.map(_bpLevelRow).join('')}
    </div>`;
}
function _bpLevelRow(r) {
  const cur=r.level===_bpData.level;
  return `<div style="display:grid;grid-template-columns:28px 1fr 1fr;gap:6px;align-items:stretch;padding:4px 0;${cur?'background:var(--gold-dim);border-radius:6px':'border-bottom:1px solid var(--border2)'}">
    <div style="display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:${cur?'var(--gold)':'var(--muted)'}">${r.level}</div>
    ${_bpRewardCell(r.level,'free',r.free)}
    ${_bpRewardCell(r.level,'paid',r.paid)}
  </div>`;
}
function _bpRewardCell(level,track,reward) {
  const parts=[];
  if(reward.mora) parts.push(`+${fmt(reward.mora)} 🪙`);
  if(reward.diamonds) parts.push(`+${reward.diamonds} 💎`);
  (reward.items||[]).forEach(it=>parts.push(`+${it.qty} ${it.name}`));
  if(reward.theme) parts.push(`🎨 Тема «${reward.theme}»`);
  const text=parts.join(', ')||'—';
  const st=reward.status;
  const sty=BP_CELL_STYLE[st]||BP_CELL_STYLE.locked_level;
  const mark=st==='claimed'?'✅ ':st==='locked_vip'?'🔒 ':'';
  const btn=st==='available'
    ?`<button class="btn btn-sm btn-gold" style="margin-top:3px;width:100%;padding:2px 0;font-size:9px" onclick="doBpClaim(${level},'${track}',this)">Забрать</button>`
    :'';
  return `<div style="font-size:10px;padding:4px 6px;border:1px solid ${sty.border};border-radius:6px;opacity:${sty.opacity}">${mark}${text}${btn}</div>`;
}
function doBpClaim(level,track,btn) {
  btn.disabled=true;
  api('/battle_pass/claim',{method:'POST',body:JSON.stringify({level,track})})
    .then(r=>{toast(r.message);loadBattlePass();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

// ── Zoo ───────────────────────────────────────────────────────────────────────
function loadZoo() {
  el('zoo-c').innerHTML='<div class="loader">Загрузка...</div>';
  Promise.all([api('/zoo/'),api('/zoo/expeditions')]).then(([data,expData])=>{
    _zooData=data;
    renderExps(expData);
    renderZoo(_zooTab);
  }).catch(e=>{el('zoo-c').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function renderExps(d) {
  if(_expTimer)clearInterval(_expTimer);
  const w=el('zoo-exp-wrap');
  if(!d.expeditions.length){w.innerHTML='';return;}
  const boo=d.boosters;
  w.innerHTML=d.expeditions.map(e=>`<div class="exp-card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <div style="font-size:13px;font-weight:600;color:var(--bright)">${e.name} <span style="font-size:11px;color:var(--muted)">· ${e.duration_hours}ч</span></div>
      <div id="tm-${e.pet_id}">${countdown(e.ends_at)}</div>
    </div>
    ${Object.keys(boo).length?`<div style="padding-top:8px;border-top:1px solid var(--border2)">
      ${Object.entries(boo).map(([bid,b])=>`<div class="fopt" onclick="boostExp(${e.pet_id},'${bid}',this)">
        <span style="font-size:16px">⏩</span>
        <span class="fn">${b.name}</span><span class="fq">×${b.qty}</span>
        <span class="fr" style="color:var(--teal)">−${b.boost_hours}ч</span>
      </div>`).join('')}
    </div>`:''}
  </div>`).join('');
  _expTimer=setInterval(()=>d.expeditions.forEach(e=>{const t=el('tm-'+e.pet_id);if(t)t.innerHTML=countdown(e.ends_at);}),1000);
}
// ── Zoo helpers ───────────────────────────────────────────────────────────────
function bonusLines(sid, b) {
  const p = v => `${(v*100).toFixed(0)}%`, ln = [];
  ({
    hamster: b => { ln.push(`🪙 ${b.mora_per_hour}/ч · Кап ${b.cap}`);
      if(b.ignore_exhaustion) ln.push('✅ Копит при 100% усталости');
      if(b.double_chance>0) ln.push(`🎲 Шанс ×2: ${p(b.double_chance)}`);
      if(b.daily_diamond>0) ln.push(`💎 +${b.daily_diamond}/день`); },
    owl: b => { ln.push(`📚 +${b.bonus_xp} XP каждые ${b.trigger_every_n_msg} сообщ.`);
      if(b.expedition_xp_bonus>0) ln.push(`🗺 +${p(b.expedition_xp_bonus)} XP похода`);
      if(b.weekend_double) ln.push('✅ ×2 XP в выходные');
      if(b.daily_free_spin_token) ln.push('🎟 Жетон/день'); },
    dog: b => { ln.push(`⏱ −${p(b.speed_reduction)} время похода`);
      if(b.self_fatigue_reduction>0) ln.push(`💪 Пёс: −${p(b.self_fatigue_reduction)} усталости`);
      if(b.zero_fatigue_chance>0) ln.push(`🍀 0 усталости: ${p(b.zero_fatigue_chance)}`);
      if(b.expedition_cost_reduction>0) ln.push(`💰 −${p(b.expedition_cost_reduction)} стоимость`); },
    turtle: b => { if(b.shop_discount>0) ln.push(`🛒 −${p(b.shop_discount)} магазин`);
      if(b.expedition_discount>0) ln.push(`🗺 −${p(b.expedition_discount)} поход`);
      if(b.gacha_daily_discount>0) ln.push(`🏷 −${p(b.gacha_daily_discount)} акция дня`);
      if(b.double_egg_chance>0) ln.push(`🥚 ×2 яйцо: ${p(b.double_egg_chance)}`); },
    falcon: b => { ln.push(`💰 +${p(b.mora_bonus)} Мора похода`);
      if(b.xp_bonus>0) ln.push(`📚 +${p(b.xp_bonus)} XP`);
      if(b.double_loot_chance>0) ln.push(`🎁 Двойной лут: ${p(b.double_loot_chance)}`);
      if(b.capstone_8h_treasure_map) ln.push('🗺 Карта сокровищ (8ч, гарант.)'); },
    wolf: b => { if(b.passive_reduction>0) ln.push(`😴 Пасс. −${p(b.passive_reduction)}/день`);
      if(b.active_reduction>0) ln.push(`⚔️ Актив. −${p(b.active_reduction)}/день`);
      if(b.food_extra>0) ln.push(`🍖 Корм +${b.food_extra} ед.`);
      if(b.daily_restore_uses>0) ln.push(`♻️ ${b.daily_restore_uses}×/день +${b.daily_restore_amount} ед.`);
      if(b.movement_immunity) ln.push('✅ Бесплатное перемещение'); },
    fox: b => { if(b.diamond_chance_per_2h>0) ln.push(`💎 Алмаз каждые 2ч: ${p(b.diamond_chance_per_2h)}`);
      if(b.common_dup_bonus>0) ln.push(`🐾 +${p(b.common_dup_bonus)} Common дубли`);
      if(b.weekly_guaranteed_diamond) ln.push('✅ Гарант. 💎/неделю');
      if(b.crystal_egg_chance>0) ln.push(`🔷 Кристальное яйцо: ${p(b.crystal_egg_chance)}`); },
    dragon: b => { ln.push(`🏦 Кап банка: +${fmt(b.bank_bonus)} 🪙`);
      if(b.free_food_chance>0) ln.push(`🍖 Бесплатный корм: ${p(b.free_food_chance)}`);
      if(b.hamster_collect_bonus>0) ln.push(`🐹 Хомяк +${b.hamster_collect_bonus}`);
      if(b.weekly_bank_grant>0) ln.push(`💰 +${b.weekly_bank_grant} в банк/нед.`); },
    unicorn: b => { ln.push(`😴 −${p(b.daily_fatigue_reduction)}/день всем`);
      if(b.immunity_uses>0) ln.push(`🛡 ${b.immunity_uses}×/день иммун. ${b.immunity_hours}ч`);
      if(b.active_recovery_per_hour>0) ln.push(`♻️ +${b.active_recovery_per_hour} ед./ч`);
      if(b.auto_recover) ln.push('✅ Авто-восст. при 100%'); },
  }[sid]||(() => {}))(b);
  return ln;
}

function petCard(p) {
  const fatPct = p.fatigue || 0;
  const fatWarn = fatPct >= 100 ? '⛔ ' : fatPct >= 80 ? '⚠️ ' : '';
  const placeBadge = p.placement === 'active'
    ? '<span style="color:var(--teal);font-size:10px;font-weight:600">⚔️ Активный</span>'
    : p.placement === 'passive'
    ? '<span style="color:var(--blue);font-size:10px;font-weight:600">🛡 Пассивный</span>'
    : '<span style="color:var(--dim);font-size:10px">📦 Склад</span>';
  const lvl = p.pet_level || 1;
  const dups = p.duplicates_collected || 0;
  return `<div class="pcard" style="cursor:pointer;${fatPct>=80?'border-color:'+fatC(fatPct)+';':''}" onclick="openPetModal(${p.id})">
    <div class="pcol">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:2px">
        <div class="pn">${p.name||p.species_id} ${rc(p.rarity)}</div>
        ${placeBadge}
      </div>
      <div class="ps">Lv${lvl}/10 · 📦 ${dups} дубл.</div>
      <div class="fat-bar"><div class="fat-fill${fatPct>=80?' critical':''}" style="width:${fatPct}%;background:${fatC(fatPct)}"></div></div>
      <div style="font-size:10px;color:${fatC(fatPct)}">${fatWarn}${fatPct}% усталости</div>
    </div>
  </div>`;
}

function swZoo(tab,btn) {
  _zooTab=tab;
  document.querySelectorAll('#pg-zoo .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  if(!_zooData){loadZoo();return;}
  renderZoo(tab);
}

function renderZoo(tab) {
  if(!_zooData)return;
  let pets;
  if(tab==='nursery') pets=_zooData.pets.filter(p=>p.placement!=='storage');
  else pets=_zooData.pets.filter(p=>p.placement==='storage');

  if(!pets.length){
    el('zoo-c').innerHTML=tab==='nursery'
      ?`<div style="text-align:center;padding:32px 16px;color:var(--muted)">
          <div style="font-size:32px;margin-bottom:8px">🐾</div>
          <div style="font-size:13px;font-weight:600;margin-bottom:4px">Питомник пуст</div>
          <div style="font-size:11px">Переведи питомца со склада в питомник через кнопку «Переместить»</div>
        </div>`
      :`<div style="text-align:center;padding:32px 16px;color:var(--muted)">
          <div style="font-size:32px;margin-bottom:8px">📦</div>
          <div style="font-size:13px;font-weight:600;margin-bottom:4px">Склад пуст</div>
          <div style="font-size:11px">Открой яйцо в Арене → Гача, чтобы получить питомца</div>
        </div>`;
    return;
  }

  if(tab==='nursery'){
    const active=pets.filter(p=>p.placement==='active');
    const passive=pets.filter(p=>p.placement==='passive');
    const maxSlots=_zooData.max_slots||3;
    const expandQty=_zooData.slot_expander_qty||0;
    const occupied=active.length+passive.length;
    const pendingMora=_zooData.pending_hamster_mora||0;
    const hasHamsters=pets.some(p=>p.species_id==='hamster');
    let html=`<div style="background:var(--s);border-radius:var(--r);border:1px solid var(--border2);padding:8px 12px;margin-bottom:10px">
      <div style="display:flex;align-items:center;justify-content:space-between">
        <span style="font-size:12px;color:var(--muted)">🐾 Слоты питомника</span>
        <span style="font-size:14px;font-weight:700;color:${occupied>=maxSlots?'var(--red)':'var(--green)'}">${occupied}/${maxSlots}</span>
      </div>
      ${occupied>=maxSlots&&expandQty===0&&maxSlots<6?`
        <div style="margin-top:6px;font-size:10px;color:var(--muted)">🔒 Слоты заполнены. <span style="color:var(--gold);cursor:pointer" onclick="goTo('market','goods')">Купи 🏡 Расширитель в Магазине</span></div>`:''}
      ${expandQty>0&&maxSlots<6?`
        <div style="margin-top:8px;border-top:1px solid var(--border2);padding-top:8px">
          <div style="font-size:10px;color:var(--muted);margin-bottom:5px">В инвентаре: 🏡 Расширитель слота ×${expandQty}</div>
          <button class="btn btn-full btn-sm" onclick="doExpandSlot()" style="font-size:11px">🏡 Применить расширитель (+1 слот)</button>
        </div>`:''}
    </div>
    ${hasHamsters?`<div style="background:var(--gold-dim);border:1px solid var(--border);border-radius:var(--r);padding:10px 12px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between">
      <div>
        <div style="font-size:11px;color:var(--muted);margin-bottom:2px">🐹 Хомяк-банкир накопил</div>
        <div style="font-size:16px;font-weight:700;color:var(--gold)">${pendingMora>0?fmt(pendingMora)+' 🪙':'Копит...'}</div>
      </div>
      <button class="btn btn-gold btn-sm" onclick="collectHamster(this)" ${pendingMora<1?'disabled':''}>Собрать</button>
    </div>`:''}
    ${(()=>{
      const wr=_zooData.wolf_restore;
      if(!wr||wr.uses_left<=0) return '';
      return `<div style="background:var(--s);border:1px solid var(--border2);border-radius:var(--r);padding:10px 12px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between">
        <div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:2px">🐺 Волк — восстановление усталости</div>
          <div style="font-size:13px;font-weight:600">Осталось: ${wr.uses_left}/${wr.max_uses} · −${wr.restore_amount}% усталости</div>
        </div>
        <button class="btn btn-sm" style="background:var(--purple,#7c3aed);color:#fff" onclick="doWolfRestorePick()">Использовать</button>
      </div>`;
    })()}
    ${(()=>{
      const ua=_zooData.unicorn_ability;
      if(!ua) return '';
      if(ua.active) return `<div style="background:var(--s);border:1px solid var(--border2);border-radius:var(--r);padding:10px 12px;margin-bottom:10px">
        <div style="font-size:11px;color:var(--muted)">🦄 Иммунитет усталости: <b style="color:var(--green)">АКТИВЕН</b></div>
        <div style="font-size:10px;color:var(--muted);margin-top:2px">Истекает: ${ua.expires_at?ua.expires_at.slice(0,16).replace('T',' '):''}</div>
      </div>`;
      if(!ua.available) return '';
      return `<div style="background:var(--s);border:1px solid var(--border2);border-radius:var(--r);padding:10px 12px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between">
        <div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:2px">🦄 Единорог — иммунитет усталости</div>
          <div style="font-size:13px;font-weight:600">Защита на ${ua.immunity_hours} ч. для всех питомцев</div>
        </div>
        <button class="btn btn-sm" style="background:linear-gradient(135deg,#a855f7,#ec4899);color:#fff" onclick="doUnicornImmunity(this)">Активировать</button>
      </div>`;
    })()}`;
    if(active.length) html+=`<div class="card-title" style="margin:8px 0 4px">⚔️ Активные (${active.length})</div>${active.map(petCard).join('')}`;
    if(passive.length) html+=`<div class="card-title" style="margin:12px 0 4px">🛡 Пассивные (${passive.length})</div>${passive.map(petCard).join('')}`;
    el('zoo-c').innerHTML=html;
  } else {
    el('zoo-c').innerHTML=pets.map(petCard).join('');
  }
}

// Full pet modal — redesigned with all-level progression and active/passive split
function openPetModal(petId) {
  OM('🐾 Питомец', '<div class="loader">Загрузка...</div>', []);
  // Background-fetch inventory if not loaded so "Apply items" block populates
  if(!_invData||!_invData.length) api('/inventory/').then(d=>{_invData=d;}).catch(()=>{});
  api(`/zoo/pet/${petId}`).then(p=>{
    const fatPct = p.fatigue||0;
    const lvl = p.pet_level||1;
    const dups = p.duplicates_collected||0;
    const toNext = p.dups_for_next_level||0;

    // ── ALL 10 LEVELS with diff-highlighting ───────────────────────────────
    const allLevels = p.levels ? p.levels.map((tier, i)=>{
      const isUnlocked = tier.level <= lvl;
      const isCurrent  = tier.level === lvl;
      const lines      = bonusLines(p.species_id, tier.bonus||{});

      // Find bonuses that are NEW compared to previous level
      const prevLines = i > 0
        ? new Set(bonusLines(p.species_id, p.levels[i-1].bonus||{}))
        : new Set();
      const newLines = lines.filter(l=>!prevLines.has(l));
      const hasNew   = newLines.length > 0;

      const bg     = isCurrent ? 'rgba(201,168,76,.08)' : hasNew && !isCurrent && isUnlocked ? 'rgba(82,179,96,.05)' : 'transparent';
      const border = isCurrent ? '1px solid var(--gold)' : hasNew ? '1px solid rgba(82,179,96,.4)' : '1px solid var(--border2)';

      const milestoneBadge = tier.milestone
        ? ` <span style="color:var(--bright);font-size:10px">🎁 ${tier.milestone.mora?'+'+fmt(tier.milestone.mora)+' 🪙':''} ${tier.milestone.diamonds?'+'+tier.milestone.diamonds+' 💎':''}</span>`
        : '';

      return `<div style="display:flex;gap:8px;padding:6px 8px;border-radius:6px;background:${bg};border:${border};margin-bottom:3px">
        <div style="font-weight:700;font-size:11px;min-width:26px;color:${isCurrent?'var(--gold)':isUnlocked?'var(--green)':'var(--dim)'}">
          ${isCurrent?'▶':isUnlocked?'✓':'○'}${tier.level}
        </div>
        <div style="flex:1">
          ${lines.map(l=>{
            const isNew = newLines.includes(l) && tier.level > 1;
            return `<div style="font-size:10px;${isNew?'color:var(--gold);font-weight:700;':'color:'+(isUnlocked?'var(--text)':'var(--dim)')+''}">
              ${isNew?'✦ ':''}${l}
            </div>`;
          }).join('')}
          ${!lines.length?`<div style="font-size:10px;color:var(--dim)">—</div>`:''}
        </div>
        ${milestoneBadge}
      </div>`;
    }).join('') : '<div style="font-size:11px;color:var(--muted)">Нет данных</div>';

    // ── PLACEMENT BONUS explanation ─────────────────────────────────────────
    const isActive  = p.placement === 'active';
    const isPassive = p.placement === 'passive';
    const placePill = isActive
      ? `<span style="background:rgba(82,199,180,.15);color:var(--teal);padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600">⚔️ Активный слот</span>`
      : isPassive
      ? `<span style="background:rgba(100,160,230,.15);color:var(--blue);padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600">🛡 Пассивный слот</span>`
      : `<span style="background:var(--s);color:var(--muted);padding:2px 8px;border-radius:12px;font-size:11px">📦 Склад</span>`;

    const curBonus = bonusLines(p.species_id, p.current_bonus||{});
    const bonusHtml = curBonus.length
      ? curBonus.map(l=>`<div style="font-size:11px;padding:3px 0;color:var(--text)">• ${l}</div>`).join('')
      : `<div style="font-size:11px;color:var(--muted)">Переведи питомца в активный или пассивный слот</div>`;

    // ── FOOD ───────────────────────────────────────────────────────────────
    const foodHtml = Object.entries(p.available_food||{}).length
      ? Object.entries(p.available_food).map(([fid,f])=>`
          <div class="fopt" onclick="doFeed(${petId},'${fid}',this)">
            <span class="fn">${f.name}</span>
            <span class="fq">×${f.qty}</span>
            <span class="fr" style="color:var(--green)">−${f.restore} уст.</span>
          </div>`).join('')
      : '<div style="font-size:11px;color:var(--muted);padding:5px">Корма нет — купите в Магазине.</div>';

    const body = `
      <!-- Header -->
      <div style="text-align:center;padding:10px 0 10px">
        <div style="font-size:28px;margin-bottom:6px">${p.name}</div>
        <div style="margin-bottom:6px">${rc(p.rarity)}</div>
        <div style="margin-bottom:8px">${placePill}</div>
        <div style="font-size:11px;color:var(--muted);line-height:1.5;max-width:280px;margin:0 auto">${p.species_desc||''}</div>
      </div>
      <div class="divider"></div>

      <!-- Stats row -->
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:12px">
        <div style="background:var(--s);border-radius:var(--r);padding:8px;text-align:center">
          <div style="font-size:18px;font-weight:700;color:var(--gold)">${lvl}<span style="font-size:10px">/10</span></div>
          <div style="font-size:9px;color:var(--muted);margin-top:2px">УРОВЕНЬ</div>
        </div>
        <div style="background:var(--s);border-radius:var(--r);padding:8px;text-align:center">
          <div style="font-size:18px;font-weight:700;color:var(--text)">${dups}${lvl<10?`<span style="font-size:10px;color:var(--muted)">/${dups+toNext}</span>`:''}</div>
          <div style="font-size:9px;color:var(--muted);margin-top:2px">ДУБЛИКАТЫ</div>
        </div>
        <div style="background:var(--s);border-radius:var(--r);padding:8px;text-align:center">
          <div style="font-size:18px;font-weight:700;color:${fatC(fatPct)}">${fatPct}<span style="font-size:10px">%</span></div>
          <div style="font-size:9px;color:var(--muted);margin-top:2px">УСТАЛОСТЬ</div>
        </div>
      </div>

      <!-- Fatigue bar -->
      <div style="margin-bottom:14px">
        <div class="fat-bar" style="height:6px"><div class="fat-fill${fatPct>=80?' critical':''}" style="width:${fatPct}%;background:${fatC(fatPct)}"></div></div>
        <div style="font-size:10px;color:var(--muted);margin-top:4px">
          ${lvl<10?`До Lv${lvl+1}: нужно ${toNext} дублик.`:'<span style="color:var(--gold)">★ Максимальный уровень!</span>'}
        </div>
      </div>

      <!-- Current bonuses -->
      <div style="background:var(--s);border-radius:var(--r);padding:10px;margin-bottom:12px">
        <div style="font-size:10px;font-weight:700;color:var(--muted);margin-bottom:6px">📊 ТЕКУЩИЕ БОНУСЫ</div>
        ${bonusHtml}
      </div>

      <!-- Level progression -->
      <div style="margin-bottom:4px;display:flex;justify-content:space-between;align-items:center">
        <div class="card-title" style="margin:0">📈 Все уровни</div>
        <div style="font-size:9px;color:var(--muted)">✦ = новый баф · ▶ = текущий</div>
      </div>
      <div style="margin-bottom:12px">${allLevels}</div>

      <!-- Feed -->
      <div class="card-title">🍖 Покормить (снизить усталость)</div>
      <div style="margin-bottom:8px">${foodHtml}</div>

      ${renderPetItems(petId, p)}

      <div class="card-title">↔ Переместить</div>
      <div style="display:flex;flex-direction:column;gap:6px">
        ${['active','passive','storage'].filter(pl=>pl!==p.placement).map(pl=>{
          const isActive = pl==='active';
          const toNursery = pl !== 'storage';
          const fatigueNote = toNursery
            ? `<span style="font-size:10px;color:var(--muted);display:block;margin-top:2px">+20% усталости за перемещение</span>`
            : '';
          return `<div>
            <button class="btn btn-full ${pl==='storage'?'btn-ghost':isActive?'btn-teal':'btn-green'}" onclick="doMove(${petId},'${pl}',this)">
              ${isActive?'⚔️ В активные':pl==='passive'?'🛡 В пассивные':'📦 На склад'}
            </button>${fatigueNote}
          </div>`;
        }).join('')}
      </div>`;

    el('mt').textContent=p.name||p.species_name||p.species_id;
    el('mb').innerHTML=body;
    el('mf').innerHTML=`<button class="btn btn-ghost btn-sm" onclick="CM()">Закрыть</button>`;
  }).catch(e=>{el('mb').innerHTML=`<div style="color:var(--red);font-size:12px">${e}</div>`;});
}

function doFeed(pid,fid,row) {
  row.style.opacity='.4';
  api('/zoo/feed',{method:'POST',body:JSON.stringify({pet_id:pid,food_id:fid})})
    .then(r=>{toast(`✅ Усталость: ${r.fatigue_before}% → ${r.fatigue_after}%`);CM();_zooData=null;loadZoo();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}

function doMove(pid,pl,btn) {
  btn.disabled=true;
  api('/zoo/move',{method:'POST',body:JSON.stringify({pet_id:pid,placement:pl})})
    .then(()=>{toast('✅ Перемещено!');CM();_zooData=null;loadZoo();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

function doExpandSlot() {
  api('/zoo/expand-slot',{method:'POST'})
    .then(r=>{toast(`✅ Слот добавлен! Теперь ${r.max_slots} слотов.`);_zooData=null;loadZoo();})
    .catch(e=>toast(e,false));
}

function collectHamster(btn) {
  btn.disabled=true;
  api('/zoo/collect',{method:'POST'})
    .then(r=>{
      let msg=`🐹 Собрано ${fmt(r.mora)} 🪙`;
      if(r.double_bonus>0) msg+=` (×2 +${fmt(r.double_bonus)})`;
      if(r.dragon_bonus>0) msg+=` 🐉 +${fmt(r.dragon_bonus)}`;
      if(r.diamonds>0) msg+=` 💎 +${r.diamonds}`;
      toast(msg);
      refreshCurrBar();
      _zooData=null;loadZoo();
    })
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

function doWolfRestorePick() {
  if(!_zooData) return;
  const targets=_zooData.pets.filter(p=>p.placement!=='storage'&&p.species_id!=='wolf');
  if(!targets.length){toast('Нет питомцев для восстановления.',false);return;}
  const wr=_zooData.wolf_restore;
  const rows=targets.map(p=>`
    <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border2)">
      <div>
        <span style="font-weight:600">${p.name||p.species_id}</span>
        <span style="font-size:11px;color:var(--muted);margin-left:6px">Усталость: ${Math.round(p.fatigue||0)}%</span>
      </div>
      <button class="btn btn-sm" onclick="doWolfRestore(${p.id},this)" ${(p.fatigue||0)<=0?'disabled':''}>−${wr.restore_amount}%</button>
    </div>`).join('');
  OM('🐺 Восстановить усталость',`<div>${rows}</div>`,[]);
}

function doWolfRestore(petId,btn) {
  btn.disabled=true;
  api('/zoo/wolf-restore',{method:'POST',body:JSON.stringify({pet_id:petId})})
    .then(r=>{toast(`✅ Усталость: ${r.fatigue_before}% → ${r.fatigue_after}%`);CM();_zooData=null;loadZoo();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

function doUnicornImmunity(btn) {
  btn.disabled=true;
  api('/zoo/unicorn-immunity',{method:'POST'})
    .then(r=>{toast(`🦄 Иммунитет активирован на ${r.immunity_hours} ч.!`);_zooData=null;loadZoo();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

function boostExp(pid,bid,row) {
  row.style.opacity='.4';
  api('/zoo/boost',{method:'POST',body:JSON.stringify({pet_id:pid,booster_id:bid})})
    .then(r=>{toast(`⏩ −${r.boosted_hours}ч!`);_loaded.delete('zoo');loadZoo();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}

// ── Бестиарий (бывш. Справка + Витрина) ───────────────────────────────────────
// Все виды по редкостям. Клик по виду → showSpeciesDetail (бонусы по уровням).
let _bestiaryFilter='all';
function renderZooGuide() {
  if(_showcaseData){_renderBestiary();return;}
  el('best-c').innerHTML='<div class="loader">Загрузка...</div>';
  api('/zoo/species').then(list=>{_showcaseData=list;_renderBestiary();})
    .catch(e=>{el('best-c').innerHTML=`<div class="err">${e}</div>`;});
}
function setBestiaryFilter(r){_bestiaryFilter=r;_renderBestiary();}
function _renderBestiary() {
  const ORDER = {common:0,uncommon:1,rare:2,epic:3,legendary:4,mythic:5};
  const RARITY_LABEL = {common:'⬜ Обычные',uncommon:'🟢 Необычные',rare:'🟦 Редкие',epic:'🟣 Эпические',legendary:'🟡 Легендарные',mythic:'🔴 Мифические'};
  const all=[...(_showcaseData||[])].sort((a,b)=>(ORDER[a.rarity]||0)-(ORDER[b.rarity]||0));
  const filters=['all',...Object.keys(ORDER).filter(r=>all.some(p=>p.rarity===r))];
  const list=_bestiaryFilter==='all'?all:all.filter(p=>p.rarity===_bestiaryFilter);
  const g={};list.forEach(s=>(g[s.rarity]=g[s.rarity]||[]).push(s));
  const filterRow=`<div class="tabs" style="margin-bottom:10px">
    ${filters.map(r=>`<button class="tb ${_bestiaryFilter===r?'active':''}" onclick="setBestiaryFilter('${r}')">${r==='all'?'Все':(RARITY_LABEL[r]||r).replace(/^.. /,'')}</button>`).join('')}
  </div>`;
  const body=Object.entries(g).map(([r,pets])=>`<div class="card">
      <div class="card-title">${RARITY_LABEL[r]||r} (${pets.length})</div>
      ${pets.map(p=>{
        const t1=bonusLines(p.species_id,(p.bonus_tiers||{})['1']||{});
        const t4=bonusLines(p.species_id,(p.bonus_tiers||{})['4']||{});
        const t10=bonusLines(p.species_id,(p.bonus_tiers||{})['10']||{});
        return `<div class="pcard" style="cursor:pointer;display:block" onclick="showSpeciesDetail('${p.species_id}')">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <div style="font-size:13px;font-weight:700;color:var(--bright);flex:1">${p.name}</div>
            <div style="font-size:10px;color:${p.role==='active'?'var(--teal)':'var(--blue)'}">${p.role==='active'?'⚔️ Активный':'🛡 Пассивный'}</div>
          </div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:7px;line-height:1.4">${p.desc}</div>
          <div style="font-size:10px">
            <span style="color:var(--muted)">Lv1: </span>${t1[0]||'—'}
            ${t4.length?`<span style="color:var(--muted)"> · Lv4: </span>${t4[0]||'—'}`:''}
            ${t10.length?`<span style="color:var(--muted)"> · Lv10: </span>${t10[t10.length-1]||'—'}`:''}
          </div>
        </div>`;
      }).join('')}
    </div>`).join('');
  el('best-c').innerHTML=filterRow+(body||`<div class="empty-state"><div class="es-icon">🔍</div><div class="es-title">Пусто</div><div class="es-sub">Нет видов этой редкости</div></div>`);
}
setInterval(()=>{if(_loaded.has('zoo'))api('/zoo/expeditions').then(d=>renderExps(d)).catch(()=>{});},30000);

// ── Arena ─────────────────────────────────────────────────────────────────────
// ── Arena — только Дуэли + Ивенты. Гача/Крафт/Тёмная/Квесты перенесены в Рынок/Профиль.
function loadArena(){swArena(_arenaTab,document.querySelector('#pg-arena .tb'));}
function swArena(tab,btn) {
  _arenaTab=tab;
  document.querySelectorAll('#pg-arena .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  ['duels','events'].forEach(t=>el('ar-'+t).style.display=t===tab?'':'none');
  ({duels:loadDuels,events:loadEvents}[tab]||loadDuels)();
}
const QUEST_NAMES = {
  msg_15:     {n:'💬 Болтун',         d:'Напиши 15 сообщений в чате'},
  msg_30:     {n:'💬 Оратор',         d:'Напиши 30 сообщений в чате'},
  feed_pet:   {n:'🍖 Забота о питомце',d:'Покорми питомца 1 раз'},
  gacha_3:    {n:'🎲 Удача в крутке', d:'Покрути гачу 3 раза'},
  exped_2:    {n:'🗺 Путешественник',  d:'Отправь питомца в 2 экспедиции'},
  exped_4:    {n:'🗺 Искатель приключений',d:'Отправь питомца в 4 экспедиции'},
  open_egg:   {n:'🥚 Яйцелов',        d:'Открой 1 яйцо в инвентаре'},
  warp_3:     {n:'🌀 Варп-мастер',    d:'Отправь 3 варпа разным игрокам'},
  auction_bid:{n:'🏛 Аукционист',     d:'Поставь 1 ставку на аукционе'},
  gacha_10:   {n:'🎰 Одержимый гачей',d:'Покрути гачу 10 раз'},
  hug_5:      {n:'🤗 Душа компании',  d:'Обними 5 разных игроков'},
  rare_dup:   {n:'🌟 Редкий дубликат',d:'Получи дубликат редкого+ питомца'},
  level_pet:  {n:'⬆️ Тренер',         d:'Повысь питомца до нового уровня'},
};
function loadQuests() {
  el('qc').innerHTML='<div class="loader">Загрузка...</div>';
  if(!_cid){el('qc').innerHTML='<div style="color:var(--muted);font-size:12px;padding:10px">Нужен Профиль с чатом.</div>';return;}
  api(`/quests/${_cid}`).then(qs=>{
    el('qc').innerHTML=qs.length?'<div class="card">'+qs.map(q=>{
      const pct=Math.min(100,Math.round((q.progress||0)/(q.target||1)*100));
      const qi=QUEST_NAMES[q.id]||{n:q.id,d:''};
      const _QI={'star_dust_s':'🌟 Звёздная пыль','star_dust_l':'✨ Небесная пыль',
                 'soul_shard':'💠 Осколок','spin_token_novice':'🎟 Жетон',
                 'spin_token_standard':'🎟 Ст. жетон','spin_token_premium':'🎟 Пр. жетон'};
      const rw=[
        q.reward?.mora?`+${fmt(q.reward.mora)} 🪙`:'',
        q.reward?.diamonds?`+${q.reward.diamonds} 💎`:'',
        ...(q.reward?.items||[]).map(([id,n])=>`+${n>1?n+'× ':''}${_QI[id]||id}`),
      ].filter(Boolean).join(' · ');
      return `<div class="qitem">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:2px">
          <div style="font-size:13px;font-weight:600;color:var(--bright)">${q.completed?'✅':'🔲'} ${qi.n}</div>
          ${rw?`<div style="font-size:11px;color:var(--gold);white-space:nowrap;margin-left:8px">${rw}</div>`:''}
        </div>
        ${qi.d?`<div style="font-size:10px;color:var(--muted);margin-bottom:4px">${qi.d}</div>`:''}
        <div class="qbar"><div class="qfill" style="width:${pct}%"></div></div>
        <div style="font-size:10px;color:var(--muted);margin-top:2px">${Math.round(q.progress||0)} / ${q.target}</div>
      </div>`;
    }).join('')+'</div>':'<div style="text-align:center;padding:24px;color:var(--muted)"><div style="font-size:28px;margin-bottom:6px">📋</div><div style="font-size:12px">Нет квестов — напиши <code>бот задания</code> в чате</div></div>';
  }).catch(e=>{el('qc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
const SPIN_ICONS = {novice:'🎟',standard:'🎲',premium:'💎',diamond:'💠'};
const SPIN_RARITY_ORDER = ['mythic','legendary','epic','rare','uncommon','common'];

function _topRarity(dups) {
  for(const r of SPIN_RARITY_ORDER) if(dups.some(d=>d.rarity===r)) return r;
  return '';
}

function loadGacha() {
  el('gc').innerHTML='<div class="loader">Загрузка...</div>';
  api('/gacha/').then(d=>{
    const disc = d.multi_discount_pct||10;
    el('gc').innerHTML=`
    <div class="gacha-header">
      <div class="gh-title">✨ ГАЧА</div>
      <div class="gh-sub">Крути яйца, получай питомцев и ресурсы</div>
    </div>
    <div class="gacha-balance">
      <span class="gb-item" id="gacha-bal-mora">🪙 ${fmt(d.mora)}</span>
      <span style="color:var(--border2)">│</span>
      <span class="gb-item" id="gacha-bal-dia">💎 ${(d.diamonds||0).toFixed(1)}</span>
    </div>
    <div class="card">
      <div class="card-title" style="margin-bottom:10px">Выберите крутку</div>
      ${d.spin_types.map(s=>{
        const icon = SPIN_ICONS[s.spin_type] || '🎲';
        const cost = s.cost_mora ? `${fmt(s.cost_mora)} 🪙` : `${s.cost_dia} 💎`;
        const multiCost = s.cost_mora ? `${fmt(s.multi_cost_mora)} 🪙` : `${s.multi_cost_dia} 💎`;
        const pityPct = s.pity_hard > 0 ? Math.round(s.pity/s.pity_hard*100) : 0;
        const rates = s.rates||{};
        const ratesBadges = Object.entries(rates).map(([r,v])=>
          `<span class="${RC[r]||'rc-common'}" style="font-size:9px;padding:1px 4px">${r[0].toUpperCase()+r.slice(1)} ${v}%</span>`
        ).join(' ');
        return `<div class="spin-block">
          <div class="spin-row" onclick="doSpin('${s.spin_type}',this)">
            <div class="sr-icon">${icon}</div>
            <div class="sr-info">
              <div class="sr-name">${s.label}</div>
              ${ratesBadges?`<div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:4px">${ratesBadges}</div>`:''}
            </div>
            ${s.token_qty?`<span style="font-size:11px;color:var(--green);margin-right:6px">🎟 ×${s.token_qty}</span>`:''}
            <div class="sr-cost">${cost}</div>
          </div>
          <div style="display:flex;gap:6px;padding:0 4px 10px">
            <div style="flex:1;font-size:10px;color:var(--muted)">
              ${s.pity>0?`Пити: <span style="color:var(--gold)">${s.pity}/${s.pity_hard}</span>
              <div class="pity-bar"><div class="pity-fill" style="width:${pityPct}%"></div></div>`:'Гарант не накоплен'}
            </div>
            <button class="btn btn-sm btn-ghost" style="font-size:10px;white-space:nowrap" onclick="doMultiSpin('${s.spin_type}',this)">
              ×${d.multi_count||10} <span style="color:var(--green)">−${disc}%</span><br>
              <span style="color:var(--gold)">${multiCost}</span>
            </button>
          </div>
        </div>`;
      }).join('')}
    </div>
    <div id="spin-res"></div>`;
  }).catch(e=>{el('gc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}

// doSpin — preserves result; no loadGacha() call
let _lastSpinType = null;
function spinAgain() {
  if (!_lastSpinType) { loadGacha(); return; }
  // Find the matching spin-row in the current gacha page and trigger it
  const rows = document.querySelectorAll('.spin-row');
  for (const r of rows) {
    const oc = r.getAttribute('onclick') || '';
    if (oc.includes(_lastSpinType)) { doSpin(_lastSpinType, r); return; }
  }
  loadGacha(); // fallback: row not found, reload
}

function doSpin(st, row) {
  _lastSpinType = st;
  row.style.opacity='.4'; row.style.pointerEvents='none';
  el('spin-res').innerHTML='';
  api('/gacha/spin',{method:'POST',body:JSON.stringify({spin_type:st,chat_id:_cid||0})}).then(r=>{
    const dups = r.dup_outcomes||[];
    const topRarity = _topRarity(dups);
    const glowCls = topRarity ? 'glow-'+topRarity : '';

    // Determine display emoji for animation ball
    const ballEmoji = dups.length ? (PET_SPECIES_EMOJI[dups[0].species_id]||'🐾') : (r.mora ? '🪙' : '💎');

    // Build result cards
    const cards=[];
    if(r.mora) cards.push({text:`🪙 ${fmt(r.mora)} Мора`, cls:'', icon:'🪙'});
    if(r.diamonds) cards.push({text:`💎 ${r.diamonds} Алмазов`, cls:'', icon:'💎'});
    (r.items||[]).forEach(i=>cards.push({text:`${i.name}${i.qty>1?' ×'+i.qty:''}`, cls:'', icon:'📦'}));
    dups.forEach(d=>cards.push({
      text:`🐾 ${d.species_name||d.species_id||''} ${rc(d.rarity||'common')} ${d.outcome==='first_copy_created'?'🆕 Новый!':d.new_level?'→ Lv'+d.new_level:''}`,
      cls:d.rarity||'', icon:'🐾'
    }));

    el('spin-res').innerHTML=`
      <div class="spin-anim-wrap ${glowCls}">
        <div class="spin-anim-ball">${ballEmoji}</div>
        <div style="font-size:11px;color:var(--gold2);margin-top:8px;font-weight:700">
          ${topRarity?('⚡ '+topRarity.toUpperCase()):'Результат'}
        </div>
      </div>
      <div class="spin-results">
        ${cards.map((c,i)=>`<div class="spin-card ${c.cls}" style="animation-delay:${(i*0.08+3.1).toFixed(2)}s">${c.text}</div>`).join('')}
      </div>
      <div style="display:flex;gap:8px;margin-top:10px">
        <button class="btn btn-gold" style="flex:2" onclick="spinAgain()">🔄 Крутить ещё</button>
        <button class="btn btn-ghost" style="flex:1" onclick="closeSpinResult()">↩ Выбрать</button>
      </div>`;

    // Update balance displays
    refreshCurrBar();
    const balEl=el('gacha-bal-mora');
    if(balEl) api('/profile/me').then(d=>{ if(d.mora!==undefined) balEl.textContent='🪙 '+fmt(d.mora); }).catch(()=>{});
    row.style.opacity='1'; row.style.pointerEvents='';
  }).catch(e=>{toast(e,false); row.style.opacity='1'; row.style.pointerEvents='';});
}
// Minimal species→emoji map (expand as needed)
const PET_SPECIES_EMOJI={hamster:'🐹',owl:'🦉',dog:'🐕',turtle:'🐢',falcon:'🦅',wolf:'🐺',fox:'🦊',dragon:'🐉',unicorn:'🦄'};
function closeSpinResult(){const s=el('spin-res');if(s)s.innerHTML='';loadGacha();}

function doMultiSpin(st, btn) {
  btn.disabled=true;
  el('spin-res').innerHTML=`<div class="spin-anim-wrap"><div class="spin-anim-ball" style="animation-duration:2s">🎲</div><div style="font-size:12px;color:var(--gold2);margin-top:8px">×10 крутка...</div></div>`;
  api('/gacha/multi-spin',{method:'POST',body:JSON.stringify({spin_type:st,chat_id:_cid||0})}).then(r=>{
    const s=r.summary||{};
    const dups=s.dup_outcomes||[];
    const topRarity=_topRarity(dups);
    const glowCls=topRarity?'glow-'+topRarity:'';
    const cards=[];
    if(s.mora) cards.push({text:`🪙 ${fmt(s.mora)} Мора`,cls:''});
    if(s.diamonds) cards.push({text:`💎 ${s.diamonds} Алмазов`,cls:''});
    // Aggregate items by item_id to avoid duplicate entries
    const itemMap={};
    (s.items||[]).forEach(i=>{
      const k=i.id||i.item_id||i.name||'?';
      if(itemMap[k]) itemMap[k].qty+=i.qty||1;
      else itemMap[k]={name:i.name||k,qty:i.qty||1};
    });
    Object.values(itemMap).forEach(i=>cards.push({text:`📦 ${i.name} ×${i.qty}`,cls:''}));
    // Summarize pet dups by species
    const petMap={};
    dups.forEach(d=>{
      const k=d.species_id||d.species||'?';
      if(!petMap[k]) petMap[k]={name:d.species_name||k,rarity:d.rarity,count:0,newLevel:null};
      petMap[k].count++;
      if(d.new_level) petMap[k].newLevel=d.new_level;
    });
    Object.values(petMap).forEach(p=>cards.push({text:`🐾 ${p.name} ${rc(p.rarity)} ×${p.count}${p.newLevel?' → Lv'+p.newLevel:''}`,cls:p.rarity||''}));

    el('spin-res').innerHTML=`
      <div class="spin-anim-wrap ${glowCls}">
        <div style="font-size:40px;font-weight:800;color:var(--gold2)">×${s.count||10}</div>
        <div style="font-size:11px;color:var(--gold2);margin-top:4px;font-weight:700">
          ${topRarity?('⚡ '+topRarity.toUpperCase()):'Результат мультикрутки'}
        </div>
      </div>
      <div class="spin-results">
        ${cards.map((c,i)=>`<div class="spin-card ${c.cls}" style="animation-delay:${(i*0.06+0.5).toFixed(2)}s">${c.text}</div>`).join('')}
      </div>
      <div style="display:flex;gap:8px;margin-top:10px">
        <button class="btn btn-gold" style="flex:2" onclick="loadGacha()">🔄 Крутить ещё</button>
        <button class="btn btn-ghost" style="flex:1" onclick="closeSpinResult()">↩ Назад</button>
      </div>`;
    refreshCurrBar();
    btn.disabled=false;
  }).catch(e=>{toast(e,false);btn.disabled=false;el('spin-res').innerHTML='';});
}
function loadCraft() {
  el('cc').innerHTML='<div class="loader">Загрузка...</div>';
  api('/craft/').then(recipes => {
    if (!recipes.length) { el('cc').innerHTML='<div class="empty-state"><div class="es-icon">⚗️</div><div class="es-title">Рецептов пока нет</div><div class="es-sub">Рецепты крафта появятся в следующих обновлениях</div></div>'; return; }
    el('cc').innerHTML = recipes.map(rc => `
      <div class="card card-gold">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <div style="font-size:15px;font-weight:700;color:var(--bright)">${rc.name}</div>
          ${rc.can_craft_times>1?`<span style="font-size:11px;color:var(--green);background:rgba(82,179,96,.15);padding:2px 8px;border-radius:99px">×${rc.can_craft_times} возможно</span>`:''}
        </div>
        ${rc.what_is?`<div style="font-size:12px;color:var(--text);line-height:1.5;margin-bottom:10px">${rc.what_is}</div>`:''}
        ${rc.how_use?`<div class="irow"><span class="ik">Как использовать</span><span style="color:var(--teal);font-size:11px">${rc.how_use}</span></div>`:''}
        ${rc.gacha_rates?`<div class="irow"><span class="ik">Шансы при открытии</span><span style="font-size:11px">${rc.gacha_rates}</span></div>`:''}
        ${rc.special_note?`<div style="background:rgba(224,82,82,.1);border:1px solid rgba(224,82,82,.25);border-radius:var(--r);padding:8px 10px;font-size:11px;color:var(--red);margin:8px 0">${rc.special_note}</div>`:''}
        <div class="divider"></div>
        <div class="card-title">Нужно для крафта</div>
        ${rc.ingredients_status.map(i=>`
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <span style="font-size:18px">${i.have>=i.needed?'✅':'❌'}</span>
            <div style="flex:1">
              <div style="font-size:12px;font-weight:600">${i.item_name}</div>
              <div style="font-size:10px;color:var(--muted)">${i.have} из ${i.needed} в инвентаре</div>
            </div>
            <div style="font-size:14px;font-weight:700;color:${i.have>=i.needed?'var(--green)':'var(--red)'}">${i.have}/${i.needed}</div>
          </div>`).join('')}
        ${rc.ingredient_tip?`<div style="font-size:11px;color:var(--muted);margin-top:6px;padding:8px;background:var(--s);border-radius:var(--r)">💡 ${rc.ingredient_tip}</div>`:''}
        <button class="btn btn-full ${rc.can_craft?'btn-gold':'btn-ghost'}" style="margin-top:12px"
                ${rc.can_craft?'':'disabled'} onclick="doCraft('${rc.recipe_id}',this)">
          ${rc.can_craft?`⚗️ Скрафтить ${rc.name}`:'🔒 Недостаточно ингредиентов'}
        </button>
      </div>`).join('');
  }).catch(e => { el('cc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`; });
}
function doCraft(recipeId, btn) {
  btn.disabled = true;
  api(`/craft/${recipeId}`, {method:'POST'})
    .then(r => { toast(`✅ Скрафтено: ${r.name}!`); loadCraft(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}
function loadDuels() {
  el('dc').innerHTML='<div class="loader">Загрузка...</div>';
  Promise.all([api('/duels/active'), api('/duels/history')]).then(([active, hist]) => {
    let html = '';

    // Challenge button
    html += `<button class="btn btn-red btn-full" style="margin-bottom:10px" onclick="openDuelChallenge()">⚔️ Вызвать игрока на дуэль</button>`;

    // Incoming challenges
    const incoming = active.filter(d => d.challenged_id == _uid);
    if(incoming.length) {
      html += `<div class="card"><div class="card-title">⏳ Входящие вызовы (${incoming.length})</div>
        ${incoming.map(d=>`<div class="duel-card">
          <div class="duel-vs">${vipName(d.challenger_name||'Игрок', d.challenger_is_vip)} вызывает вас</div>
          <div class="duel-stake">Ставка: ${fmt(d.stake)} 🪙</div>
          <div style="display:flex;gap:6px;margin-top:8px">
            <button class="btn btn-sm btn-teal" style="flex:1" onclick="acceptDuel(${d.id},this)">⚔️ Принять</button>
            <button class="btn btn-sm btn-red" style="flex:1" onclick="declineDuel(${d.id},this)">❌ Отклонить</button>
          </div>
        </div>`).join('')}
      </div>`;
    }

    // Outgoing pending
    const outgoing = active.filter(d => d.challenger_id == _uid);
    if(outgoing.length) {
      html += `<div class="card"><div class="card-title">📤 Мои вызовы</div>
        ${outgoing.map(d=>`<div class="duel-card">
          <div class="duel-vs">→ ${vipName(d.challenged_name||'Игрок', d.challenged_is_vip)}</div>
          <div class="duel-stake">Ставка: ${fmt(d.stake)} 🪙</div>
          <div style="font-size:10px;color:var(--muted)">Ожидание ответа...</div>
        </div>`).join('')}
      </div>`;
    }

    // History
    if(hist.length) {
      html += `<div class="card"><div class="card-title">📜 История (последние 20)</div>
        ${hist.map(d => {
          const won = d.winner_id == _uid;
          const isDone = d.status === 'finished';
          const vs = d.challenger_id == _uid ? d.challenged_name : d.challenger_name;
          const vsIsVip = d.challenger_id == _uid ? d.challenged_is_vip : d.challenger_is_vip;
          const statusMap = {pending:'⏳ Ожидание', timeout:'⏰ Истёк', declined:'❌ Отклонён', finished:''};
          return `<div class="duel-card">
            <div style="display:flex;align-items:center;justify-content:space-between">
              <div class="duel-vs">vs ${vipName(vs||'Игрок', vsIsVip)}</div>
              <div class="duel-result${isDone?(won?' win':' lose'):''}">
                ${isDone?(won?'✓ Победа':'✗ Поражение'):statusMap[d.status]||d.status}
              </div>
            </div>
            <div class="duel-stake">${fmt(d.stake)} 🪙</div>
          </div>`;
        }).join('')}
      </div>`;
    }

    if(!html) html = `<div style="text-align:center;padding:32px 16px;color:var(--muted)">
      <div style="font-size:32px;margin-bottom:8px">⚔️</div>
      <div style="font-size:13px;font-weight:600;margin-bottom:4px">Дуэлей пока нет</div>
      <div style="font-size:11px">Нажми «Вызвать игрока» и бросить кому-нибудь вызов!</div>
    </div>`;
    el('dc').innerHTML = html;
  }).catch(e => { el('dc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`; });
}

function acceptDuel(id, btn) {
  btn.disabled = true;
  btn.textContent = '...';
  api('/duels/accept', {method:'POST', body:JSON.stringify({duel_id:id})})
    .then(r => {
      const won = r.winner_id == _uid;
      toast(won ? '🏆 Победа!' : (r.winner_id ? '😔 Поражение' : '🤝 Ничья'), won);
      loadDuels();
      refreshCurrBar();
    })
    .catch(e => { toast(e, false); btn.disabled = false; btn.textContent = '⚔️ Принять'; });
}

function declineDuel(id, btn) {
  btn.disabled = true;
  api('/duels/decline', {method:'POST', body:JSON.stringify({duel_id:id})})
    .then(() => { toast('✅ Вызов отклонён.'); loadDuels(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

function openDuelChallenge() {
  if(!_cid) { toast('Нужен Профиль с чатом для вызова.', false); return; }
  // Grab current balance from profile data if available
  const bal = _profileData?.mora || 0;
  const balStr = bal > 0 ? `<div style="background:var(--s);border-radius:var(--r);padding:6px 10px;margin-bottom:10px;font-size:11px;display:flex;justify-content:space-between"><span style="color:var(--muted)">Ваш баланс</span><span style="color:var(--gold);font-weight:600">${fmt(bal)} 🪙</span></div>` : '';
  OM('⚔️ Вызов на дуэль', `
    ${balStr}
    <div style="font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.5">
      Соперник получит уведомление в Telegram — он должен ответить <code>бот принять</code> в чате.
    </div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">@username соперника</div>
    <input id="duel-user" type="text" class="num-input" placeholder="username (без @)"/>
    <div style="font-size:11px;color:var(--muted);margin:8px 0 4px">Ставка 🪙 (200 – 15 000)</div>
    <input id="duel-stake" type="number" class="num-input" placeholder="500" min="200" max="15000"/>
    <div style="font-size:10px;color:var(--gold);margin-top:6px;background:var(--gold-dim);padding:6px 8px;border-radius:var(--r)">
      🔒 Ставка заморозится до конца дуэли. Победитель забирает обе ставки.
    </div>
  `, [
    {l:'⚔️ Вызвать', c:'btn-red', f:'submitDuelChallenge(this)'},
    {l:'Отмена', c:'btn-ghost', f:'CM()'},
  ]);
}

function submitDuelChallenge(btn) {
  const username = el('duel-user')?.value?.trim().replace('@','');
  const stake = parseFloat(el('duel-stake')?.value||0);
  if(!username) { toast('Введите @username.', false); return; }
  if(!stake || stake < 200) { toast('Мин. ставка 200 🪙.', false); return; }
  const myBal = _profileData?.mora || 0;
  if(myBal > 0 && stake > myBal) { toast(`Недостаточно Моры. У тебя ${fmt(myBal)} 🪙.`, false); return; }
  btn.disabled = true;
  api('/duels/challenge', {method:'POST', body:JSON.stringify({username, stake, chat_id:_cid})})
    .then(() => {
      el('mb').innerHTML=`<div style="text-align:center;padding:20px">
        <div style="font-size:36px;margin-bottom:8px">⚔️</div>
        <div style="font-size:14px;font-weight:700;margin-bottom:6px">Вызов отправлен!</div>
        <div style="font-size:11px;color:var(--muted)">@${username} получит уведомление в Telegram.<br>Ставка <b>${fmt(stake)} 🪙</b> заморожена до конца дуэли.</div>
      </div>`;
      el('mf').innerHTML=`<button class="btn btn-ghost btn-sm" onclick="CM();loadDuels()">Закрыть</button>`;
    })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

// ── Market ────────────────────────────────────────────────────────────────────
function loadMarket(){swMkt(_mktTab,document.querySelector('#pg-market .tb'));}
// swMkt() defined later with deal + promo tabs
let _aucPage = 0, _aucTotal = 0, _aucPerPage = 20;

function loadAuction(page) {
  if(page !== undefined) _aucPage = page;
  api(`/auction/lots?page=${_aucPage}&per_page=${_aucPerPage}`).then(data=>{
    _allLots = data.lots || data;  // backward compat
    _aucTotal = data.total || _allLots.length;
    const totalPages = Math.ceil(_aucTotal / _aucPerPage);

    el('mkt-auc').innerHTML=`
      <div style="display:flex;gap:7px;margin-bottom:8px">
        <input type="text" class="num-input" style="margin:0;flex:1;font-size:12px"
               placeholder="🔍 Поиск..." oninput="filterAuction(this.value)"/>
        <button class="btn btn-gold btn-sm" onclick="openCreateLotModal()">+ Выставить</button>
      </div>
      <!-- Reserved mora -->
      <div id="auc-reserve" style="margin-bottom:8px"></div>
      <div id="lot-list"></div>
      <!-- Pagination -->
      ${totalPages > 1 ? `<div style="display:flex;gap:6px;justify-content:center;margin-top:10px">
        ${_aucPage > 0 ? `<button class="btn btn-ghost btn-sm" onclick="loadAuction(${_aucPage-1})">← Пред.</button>` : ''}
        <span style="font-size:11px;color:var(--muted);padding:6px">${_aucPage+1} / ${totalPages} (${_aucTotal} лотов)</span>
        ${data.has_more ? `<button class="btn btn-ghost btn-sm" onclick="loadAuction(${_aucPage+1})">След. →</button>` : ''}
      </div>` : `<div style="font-size:10px;color:var(--muted);text-align:center;margin-top:6px">${_aucTotal} лотов</div>`}`;

    renderLots(_allLots);
    loadAucReserve();
  }).catch(e=>{el('mkt-auc').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;_allLots=[];});
}

function loadAucReserve() {
  if(!_uid && !sess()) return;
  api('/auction/reserved').then(r=>{
    const div = el('auc-reserve'); if(!div) return;
    if(!r.reserved_total || !r.bids?.length) { div.innerHTML=''; return; }
    const bidsHtml = r.bids.map(b=>{
      const ends = new Date((b.ends_at+'').includes('T')?b.ends_at:b.ends_at+'Z');
      const diff = Math.max(0,Math.floor((ends-Date.now())/1000));
      const tl = diff>3600?Math.floor(diff/3600)+'ч':Math.floor(diff/60)+'м';
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid var(--border2)">
        <div>
          <span style="font-size:11px;color:var(--bright)">${b.item_name||'Лот #'+b.lot_id}</span>
          <span style="font-size:10px;color:var(--muted)"> · ⏳${tl}</span>
        </div>
        <span style="font-size:11px;color:var(--gold);font-weight:600">${fmt(b.amount)} 🪙</span>
      </div>`;
    }).join('');
    div.innerHTML=`<div style="background:var(--gold-dim);border:1px solid var(--border);border-radius:var(--r);padding:8px 10px;font-size:11px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-weight:600;color:var(--gold2)">🔒 Зарезервировано: ${fmt(r.reserved_total)} 🪙</span>
        <span style="font-size:10px;color:var(--muted)">${r.bids.length} ставок</span>
      </div>
      ${bidsHtml}
    </div>`;
  }).catch(()=>{});
}
// ── Create lot modal ─────────────────────────────────────────────────────────
let _invForAuction = [];
function openCreateLotModal() {
  // Always reload fresh inventory
  OM('🏛 Выставить лот', '<div class="loader">Загрузка инвентаря...</div>', []);
  // Load inventory AND pets for listing
  Promise.all([api('/inventory/'), api('/zoo/')]).then(([items, zooData])=>{
    _invData = items;
    // ALL items with quantity > 0 (server validates tradability)
    const tradable = items.filter(it => it.quantity > 0);
    const pets = (zooData.pets||[]).filter(p=>p.placement !== 'storage');

    if(!tradable.length && !pets.length) {
      el('mb').innerHTML = `<div style="text-align:center;padding:20px">
        <div style="font-size:32px;margin-bottom:8px">📦</div>
        <div style="font-size:13px;font-weight:600;margin-bottom:6px">Нечего выставить</div>
        <div style="font-size:11px;color:var(--muted)">Купите предметы в Магазине или получите питомцев в Гача.</div>
      </div>`;
      el('mf').innerHTML = `
        <button class="btn btn-ghost btn-sm" onclick="CM()">Закрыть</button>
        <button class="btn btn-gold btn-sm" onclick="goTo('market','goods')">🛒 В Магазин</button>`;
      return;
    }
    _invForAuction = tradable;
    el('mt').textContent = '🏛 Что выставить?';
    let html = `<div style="background:rgba(224,82,82,.08);border:1px solid rgba(224,82,82,.3);border-radius:var(--r);padding:8px 10px;margin-bottom:10px;font-size:10px;color:var(--red)">
      ⚠️ Внимательно проверь предмет перед выставлением — отменить лот нельзя!
    </div>`;

    if(tradable.length) {
      html += `<div class="card-title" style="margin-bottom:6px">📦 Предметы из инвентаря</div>`;
      html += tradable.map(it=>`
        <div class="fopt" onclick="selectLotItem('${it.item_id}','${(it.name||it.item_id).replace(/'/g,"\\'")}',${it.quantity},'','${(it.description||'').replace(/'/g,"\\'")}')">
          <div style="flex:1">
            <div class="fn">${it.name||it.item_id}</div>
            ${it.description?`<div style="font-size:10px;color:var(--muted);margin-top:1px">${it.description}</div>`:''}
          </div>
          <span class="fq" style="margin-left:8px">×${it.quantity}</span>
        </div>`).join('');
    }

    if(pets.length) {
      html += `<div class="card-title" style="margin-top:12px;margin-bottom:6px">🐾 Питомцы</div>`;
      html += `<div style="background:var(--gold-dim);border:1px solid var(--border);border-radius:var(--r);padding:8px;margin-bottom:6px;font-size:10px;color:var(--gold)">
        💡 Питомцев можно выставить через бота: <code>бот аукцион</code>
      </div>`;
      html += pets.map(pt=>`
        <div class="fopt" style="opacity:.6;cursor:default">
          <div style="flex:1">
            <div class="fn">${pt.name} ${rc(pt.rarity)}</div>
            <div style="font-size:10px;color:var(--muted)">Lv${pt.pet_level||1} · ${pt.placement==='active'?'⚔️ Активный':'🛡 Пассивный'}</div>
          </div>
          <span style="font-size:10px;color:var(--muted)">через бота</span>
        </div>`).join('');
    }
    el('mb').innerHTML = html;
    el('mf').innerHTML = `<button class="btn btn-ghost btn-sm" onclick="CM()">Отмена</button>`;
  }).catch(e=>{el('mb').innerHTML=`<div class="err">${e}</div>`;});
}
function selectLotItem(itemId, itemName, maxQty, _unused, itemDesc) {
  el('mt').textContent = `🏛 Выставить лот`;
  const maxQ = Math.min(maxQty, 10);
  el('mb').innerHTML = `
    <div style="background:var(--s);border-radius:var(--r);padding:10px;margin-bottom:12px">
      <div style="font-size:13px;font-weight:700;color:var(--bright);margin-bottom:4px">${itemName}</div>
      ${itemDesc?`<div style="font-size:11px;color:var(--muted);line-height:1.4">${itemDesc}</div>`:''}
      <div style="font-size:10px;color:var(--muted);margin-top:4px">В наличии: ×${maxQty}</div>
    </div>
    <div class="divider"></div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Количество (1–${maxQ})</div>
    <input id="lot-qty" type="number" class="num-input" min="1" max="${maxQ}" value="1"/>
    <div style="font-size:10px;color:var(--muted);margin-bottom:10px">Максимум 10 ед. за один лот</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Минимальная ставка 🪙</div>
    <input id="lot-bid" type="number" class="num-input" min="50" value="500" placeholder="Мин. ставка (от 50 🪙)"/>
    <div style="font-size:11px;color:var(--muted);margin:8px 0 4px">Цена выкупа 🪙 <span style="color:var(--dim)">(необязательно)</span></div>
    <input id="lot-buyout" type="number" class="num-input" placeholder="Оставь пустым если без выкупа"/>
    <div style="font-size:10px;color:var(--muted);margin-top:8px;padding:6px 8px;background:var(--s);border-radius:var(--r)">
      ⏳ Лот активен 24 часа. После создания отменить нельзя.
    </div>
  `;
  el('mf').innerHTML = `
    <button class="btn btn-ghost btn-sm" onclick="openCreateLotModal()">← Назад</button>
    <button class="btn btn-gold btn-sm" onclick="submitLot('${itemId}')">✅ Выставить</button>
  `;
}
function submitLot(itemId) {
  const qty = parseInt(el('lot-qty')?.value||1);
  const minBid = parseFloat(el('lot-bid')?.value||0);
  const buyout = parseFloat(el('lot-buyout')?.value||0)||null;
  if(!minBid||minBid<50){toast('Мин. ставка от 50 🪙',false);return;}
  const btn = document.querySelector('#mf .btn-gold');
  if(btn) btn.disabled=true;
  api('/auction/create',{method:'POST',body:JSON.stringify({item_id:itemId,quantity:qty,min_bid:minBid,buyout})})
    .then(r=>{toast(`✅ Лот #${r.lot_id} создан! (24ч)`);CM();loadAuction();refreshCurrBar();})
    .catch(e=>{toast(e,false);if(btn)btn.disabled=false;});
}

// openBidModal(lotId, name, currentBid, minNextBid, hasBids, buyout)
// minNextBid comes from server (min_bid if no bids, ceil(cur*1.05) if bids exist)
function openBidModal(lotId, name, currentBid, minNextBid, hasBids, buyout) {
  const firstBid = !hasBids;
  const minLabel = firstBid
    ? `Первая ставка — не менее <b>${fmt(minNextBid)} 🪙</b>`
    : `Мин. для обгона — <b>${fmt(minNextBid)} 🪙</b> (текущая × 1.05)`;
  const buyoutBtn = buyout
    ? `<button class="btn btn-teal btn-full" style="margin-top:8px"
             onclick="doBid(${lotId},this,${buyout})">⚡ Выкупить за ${fmt(buyout)} 🪙</button>`
    : '';
  OM(`💰 Ставка: ${name}`, `
    <div class="irow"><span class="ik">Текущая ставка</span><span style="color:var(--gold);font-weight:700">${fmt(currentBid)} 🪙</span></div>
    <div style="font-size:11px;color:var(--muted);margin:8px 0">${minLabel}</div>
    <div class="divider"></div>
    <input id="bid-val" class="num-input" type="number"
           value="${minNextBid}" min="${minNextBid}" step="1"
           placeholder="Ваша ставка 🪙"/>
    <div style="font-size:10px;color:var(--muted);margin-top:6px">
      Мора будет зарезервирована до завершения аукциона.
    </div>
    ${buyoutBtn}
  `, [{l:'💰 Поставить ставку', c:'btn-gold', f:`doBid(${lotId},this,0)`}, {l:'Отмена', c:'btn-ghost', f:'CM()'}]);
}
function doBid(lotId, btn, fixedAmount) {
  const v = fixedAmount > 0 ? fixedAmount : parseFloat(el('bid-val')?.value || 0);
  if (!v || v <= 0) { toast('Введите сумму.', false); return; }
  btn.disabled = true;
  api('/auction/bid', {method:'POST', body:JSON.stringify({lot_id:lotId, amount:v})})
    .then(r => { toast(r.is_buyout ? '🎉 Выкуплено!' : '✅ Ставка принята!'); CM(); loadAuction(); refreshCurrBar(); })
    .catch(e => { toast(e, false); btn.disabled = false; });
}

function loadShopCatalog() {
  // Always fetch inventory fresh so "в инвентаре" badges reflect purchases/promos
  Promise.all([
    api('/inventory/').then(items=>{_invData=items;}).catch(()=>{}),
    api('/shop/'),
  ]).then(([,d])=>{
    el('balrow').style.display='flex';
    el('balrow').innerHTML=`<div class="bal"><div class="bv">🪙 ${fmt(d.mora)}</div><div class="bl">Мора</div></div>
      <div class="bal"><div class="bv">💎 ${d.diamonds.toFixed(1)}</div><div class="bl">Алмазы</div></div>`;
    const cats={food:'🥩 Еда',egg:'🥚 Яйца',utility:'🛠 Утилиты',booster:'⚗️ Зелья',donate:'✨ Донат'};
    const grps={};d.items.forEach(it=>(grps[it.category]=grps[it.category]||[]).push(it));
    const promoBtn=`<button class="btn btn-ghost btn-full" style="margin-bottom:10px" onclick="openPromoModal()">🎫 У меня есть промокод</button>`;
    el('mkt-shop').innerHTML=promoBtn+Object.entries(grps).map(([cat,list])=>
      `<div class="card"><div class="card-title">${cats[cat]||cat}</div>${list.map(it=>`<div class="shop-row">
        <span style="font-size:22px;width:32px;text-align:center">${it.name.split(' ')[0]}</span>
        <div style="flex:1">
          <div style="font-size:13px;font-weight:600;color:var(--bright)">${it.name}</div>
          <div style="font-size:11px;color:var(--gold)">${it.price_mora?fmt(it.price_mora)+' 🪙':it.price_diamonds?it.price_diamonds+' 💎':fmt(it.price_zarniki)+' ✨'}${it.discount_active?' 🐢':''}</div>
          <div style="font-size:10px;color:var(--muted)">${it.description||''}</div>
          ${_invData.find(i=>i.item_id===it.item_id)
            ? `<div style="font-size:10px;color:var(--green);margin-top:2px">✓ В инвентаре: ×${_invData.find(i=>i.item_id===it.item_id).quantity}</div>`
            : ''}
        </div>
        <button class="btn btn-sm btn-gold" onclick="buyItem('${it.item_id}',this)">Купить</button>
      </div>`).join('')}</div>`).join('');
  }).catch(e=>{el('mkt-shop').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
// Block 9: warn before buying if already in inventory
function buyItem(id, btn) {
  const existing = _invData.find(i => i.item_id === id);
  if (existing) {
    OM('⚠️ Уже в инвентаре', `
      <div style="text-align:center;padding:10px 0 14px">
        <div style="font-size:24px;margin-bottom:8px">⚠️</div>
        <div style="font-size:13px;font-weight:600;color:var(--bright);margin-bottom:6px">У вас уже есть этот предмет</div>
        <div style="font-size:12px;color:var(--muted)">В инвентаре: <b style="color:var(--gold)">×${existing.quantity}</b></div>
        <div style="font-size:11px;color:var(--muted);margin-top:8px">Купить ещё?</div>
      </div>
    `, [
      {l:'✅ Да, купить ещё', c:'btn-gold', f:`doBuyConfirmed('${id}')`},
      {l:'Отмена', c:'btn-ghost', f:'CM()'},
    ]);
    return;
  }
  _execBuy(id, btn);
}
function doBuyConfirmed(id) {
  CM();
  api('/shop/buy', {method:'POST', body:JSON.stringify({item_id:id, quantity:1})})
    .then(r => { toast('✅ Куплено: ' + r.item_name); loadShopCatalog(); refreshCurrBar(); })
    .catch(e => toast(e, false));
}
function _execBuy(id, btn) {
  if(btn) btn.disabled = true;
  api('/shop/buy', {method:'POST', body:JSON.stringify({item_id:id, quantity:1})})
    .then(r => { toast('✅ Куплено: ' + r.item_name); loadShopCatalog(); refreshCurrBar(); })
    .catch(e => { toast(e, false); if(btn) btn.disabled = false; });
}
function loadInventory() {
  el('mkt-inv').innerHTML='<div class="loader">Загрузка...</div>';
  api('/inventory/').then(items=>{
    _invData=items;
    _invSearch='';
    _renderInventory();
  }).catch(e=>{el('mkt-inv').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function filterInv(q){_invSearch=q;_renderInventory();}
function _renderInventory() {
  const items=_invSearch?_invData.filter(i=>(i.name||'').toLowerCase().includes(_invSearch.toLowerCase())):_invData;
  const grid=items.length
    ?'<div class="inv-grid">'+items.map(it=>`<div class="icard" onclick="openItemModal('${it.item_id}')">
        <div class="icat">${it.category}</div>
        <div class="iname">${it.name}</div>
        <div class="iqty">×${it.quantity}</div>
        <div class="idesc">${it.description||''}</div>
      </div>`).join('')+'</div>'
    :_invData.length
      ?`<div class="empty-state"><div class="es-icon">🔍</div><div class="es-title">Ничего не найдено</div><div class="es-sub">По запросу «${_invSearch}»</div></div>`
      :`<div class="empty-state"><div class="es-icon">🎒</div><div class="es-title">Инвентарь пуст</div><div class="es-sub">Купите предметы в Магазине или получите через Гачу</div></div>`;
  el('mkt-inv').innerHTML=`<div style="position:relative;margin-bottom:8px">
    <span style="position:absolute;left:10px;top:50%;transform:translateY(-50%);font-size:13px;pointer-events:none;z-index:1">🔍</span>
    <input type="text" class="num-input" style="margin:0;padding-left:32px" placeholder="Поиск в инвентаре..." value="${_invSearch.replace(/"/g,'&quot;')}" oninput="filterInv(this.value)"/>
  </div>${grid}`;
}
function openItemModal(iid) {
  const it=_invData.find(i=>i.item_id===iid);if(!it)return;
  const {item_id,name,quantity,category,description,spin_type,boost_hours,fatigue_restore,gacha_rates}=it;
  let body=`<div class="irow"><span class="ik">В инвентаре</span><span>×${quantity}</span></div>`;
  if(description)body+=`<div style="font-size:11px;color:var(--muted);margin-top:7px;line-height:1.4">${description}</div>`;
  body+='<div class="divider"></div>';
  const btns=[{l:'Закрыть',c:'btn-ghost',f:'CM()'}];
  if(category==='egg'&&gacha_rates){
    body+=Object.entries(gacha_rates).filter(([,v])=>v>0).map(([r,v])=>`<div class="irow"><span class="${RC[r]||'rc-common'}" style="font-size:11px">${r}</span><span>${v}%</span></div>`).join('');
    if(quantity>0)btns.unshift({l:'🥚 Открыть',c:'btn-gold',f:`doOpenEgg('${item_id}',1)`});
  } else if(category==='food'&&fatigue_restore){
    body+=`<div class="irow"><span class="ik">Восстанавливает</span><span style="color:var(--green)">−${fatigue_restore} уст.</span></div>`;
    if(quantity>0)btns.unshift({l:'🍖 Покормить питомца',c:'btn-gold',f:`openFeedSelModal('${item_id}')`});
  } else if(boost_hours){
    body+=`<div class="irow"><span class="ik">Ускорение</span><span style="color:var(--teal)">−${boost_hours}ч</span></div>`;
    if(quantity>0)btns.unshift({l:'⏩ К экспедиции',c:'btn-teal',f:`openBoostSelModal('${item_id}')`});
  } else if(category==='spin_token'){
    if(quantity>0)btns.unshift({l:'🎲 В Гачу',c:'btn-gold',f:`goTo('market','gacha')`});
  } else if(item_id.startsWith('star_dust')){
    body+=`<div class="irow"><span class="ik">Даёт дубликатов</span><span style="color:var(--gold)">+${item_id.includes('_l')?5:1}</span></div>`;
    if(quantity>0)btns.unshift({l:'✨ Применить',c:'btn-gold',f:`openDustModal('${item_id}')`});
  }
  OM(name,body,btns);
}
function doOpenEgg(eid,cnt) {
  CM();
  api('/inventory/open-egg',{method:'POST',body:JSON.stringify({egg_id:eid,count:cnt})}).then(r=>{
    const results=r.results||[];
    const ocMap={first_copy_created:'🆕 Новый питомец!',leveled_up:'⬆️ Уровень вырос',added:'📦 Дубликат',overflow:'💫 Переполнение'};
    OM('🎉 Яйцо открыто!',
      `<div style="text-align:center;padding:4px 0 12px"><div style="font-size:32px;margin-bottom:4px">🐾</div><div style="font-size:13px;font-weight:700">Получено:</div></div>`+
      results.map(res=>{
        const oc=ocMap[res.outcome]||res.outcome;
        return `<div style="background:var(--s);border-radius:var(--r);padding:8px 10px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:12px;font-weight:600">${res.species_name||res.species||''}</span>
          <span style="font-size:11px;color:var(--gold)">${oc}${res.new_level?' Lv'+res.new_level:''}</span>
        </div>`;
      }).join('')||'<div style="color:var(--green);font-size:12px;text-align:center">Готово!</div>',
      [{l:'🐾 В Зоопарк',c:'btn-teal',f:"CM();document.querySelector('.nb[onclick*=zoo]')?.click();loadZoo();"},{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
    loadInventory();
  }).catch(e=>toast(e,false));
}
function openFeedSelModal(fid) {
  if(!_zooData){toast('Зайдите в Зоопарк.',false);return;}
  const pets=_zooData.pets.filter(p=>p.placement!=='storage');
  if(!pets.length){toast('Нет питомцев.',false);return;}
  OM('🍖 Выберите питомца',pets.map(p=>`<div class="fopt" onclick="doFeedFromInv(${p.id},'${fid}',this)"><span class="fn">${p.name||p.species_id}</span><span class="fq">${p.fatigue}% уст.</span></div>`).join(''),[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function doFeedFromInv(pid,fid,row) {
  row.style.opacity='.4';
  api('/zoo/feed',{method:'POST',body:JSON.stringify({pet_id:pid,food_id:fid})})
    .then(r=>{toast(`✅ ${r.fatigue_before}%→${r.fatigue_after}%`);CM();_zooData=null;loadInventory();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}
function openBoostSelModal(bid) {
  api('/zoo/expeditions').then(d=>{
    if(!d.expeditions.length){toast('Нет активных экспедиций.',false);return;}
    OM('⏩ Выберите экспедицию',d.expeditions.map(e=>`<div class="fopt" onclick="doBoostFromInv(${e.pet_id},'${bid}',this)">
      <span class="fn">${e.name}</span><span style="font-size:11px;color:var(--teal)">${countdown(e.ends_at)}</span></div>`).join(''),[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
  }).catch(e=>toast(e,false));
}
function doBoostFromInv(pid,bid,row) {
  row.style.opacity='.4';
  api('/zoo/boost',{method:'POST',body:JSON.stringify({pet_id:pid,booster_id:bid})})
    .then(r=>{toast(`⏩ −${r.boosted_hours}ч!`);CM();_loaded.delete('zoo');loadZoo();loadInventory();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}
function openDustModal(did) { _showDustModal_or_load(did); }
function _showDustModal_or_load(did) {
  if(!_zooData) {
    api('/zoo/').then(d=>{_zooData=d;_showDustModal(did);}).catch(e=>toast(e,false));
  } else { _showDustModal(did); }
}
function doApplyDust(did,pid,row) {
  row.style.opacity='.4';
  api('/inventory/apply-dust',{method:'POST',body:JSON.stringify({dust_id:did,pet_id:pid})})
    .then(r=>{toast(`✅ +${r.duplicates_added} дубл.`);CM();_zooData=null;loadInventory();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}

// ── Source info for themes ────────────────────────────────────────────────────
const SRC = {
  start:          {label:'Стартовая',     desc:'Есть у всех игроков с самого начала. Бесплатно!', action:null},
  shop_mora:      {label:'Магазин 🪙',    desc:'Купите напрямую в Магазине за Мору.', action:null},
  shop_diamond:   {label:'Магазин 💎',    desc:'Купите в Магазине за Алмазы.', action:null},
  dark:           {label:'Чёрный Рынок 🌑', desc:'Покупается за Тёмную Мору на Чёрном Рынке. Зарабатывайте Тёмную Мору через Контрабанду и Ритуал Культа Бездны.', action:{l:'🌑 Открыть Тёмную Мору', f:"goToDarkMora()"}},
  zarniki:        {label:'Зарники ✨',     desc:'Приобретается за донат-валюту Зарники (Telegram Stars). 1 Звезда = 10 Зарников.',
                   action:{l:'✨ Пополнить Зарники', f:"goTo('market','vip')"}},
  gacha_novice:   {label:'Гача 🎲',       desc:'Может выпасть из Ученической крутки гачи. Шанс — случайный.', action:{l:'🎲 Открыть Гачу', f:"goTo('market','gacha')"}},
  gacha_standard: {label:'Гача 🎲',       desc:'Может выпасть из Стандартной крутки гачи (1000 🪙 / спин).', action:{l:'🎲 Открыть Гачу', f:"goTo('market','gacha')"}},
  gacha_premium:  {label:'Гача 🎲',       desc:'Может выпасть из Премиум крутки гачи (2800 🪙 / спин).', action:{l:'🎲 Открыть Гачу', f:"goTo('market','gacha')"}},
  gacha_diamond:  {label:'Гача 💎',       desc:'Выпадает из Алмазной крутки гачи (5 💎 / спин). Самые редкие темы.', action:{l:'🎲 Открыть Гачу', f:"goTo('market','gacha')"}},
  event:          {label:'Ивент 🎪',      desc:'Выдаётся за участие в особых мировых событиях. Следите за объявлениями в чате.', action:null},
  auction:        {label:'Аукцион 🏛',    desc:'Можно купить у других игроков на Аукционе.', action:{l:'🏛 Открыть Аукцион', f:"goTo('auction')"}},
};

// goTo() — единая реализация определена выше (с CM + switchPage).

// ── Collection ────────────────────────────────────────────────────────────────
// _profileData declared in globals above
// Темы → pg-profile (#col-themes), Топы → pg-hof (#top-c, loadTop)

function themeStatusBadge(t) {
  if(t.active)   return '<span class="theme-status ts-active">✓ Активна</span>';
  if(t.owned)    return '<span class="theme-status ts-owned">В коллекции</span>';
  if(t.premium)       return `<div class="theme-price">🔒 ${fmt(t.price_zarniki)} ✨</div>`;
  if(t.source && t.source.startsWith('gacha')) return '<span class="theme-status ts-gacha">Гача 🎲</span>';
  if(t.source === 'event')   return '<span class="theme-status ts-event">Ивент 🎪</span>';
  if(t.source === 'dark')    return '<span class="theme-status ts-dark">🔒 ' + (t.price_dark||'') + ' 🌑</span>';
  if(t.price_mora)    return `<div class="theme-price">${fmt(t.price_mora)} 🪙</div>`;
  if(t.price_diamonds)return `<div class="theme-price">${t.price_diamonds} 💎</div>`;
  return '';
}

function loadThemes() {
  api('/themes/').then(themes => {
    _themeData = themes;
    _themeFilter='all';
    _renderThemes();
  }).catch(e => { el('col-themes').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`; });
}
function setThemeFilter(f){_themeFilter=f;_renderThemes();}

// Карточка темы: для непринадлежащих премиум-тем — эффект витрины (🔒 + блюр)
function _themeCardHTML(t) {
  const locked = t.premium && !t.owned;          // донат-тема, ещё не куплена → upsell
  const cls = `theme-card${t.owned?' owned':''}${t.active?' active-theme':''}${locked?' premium-locked':''}`;
  return `<div class="${cls}" onclick="openThemeModal('${t.theme_id}')">
    ${locked?'<div class="lock-ic" style="position:absolute;top:7px;right:8px;font-size:13px;z-index:2">🔒</div>':''}
    <div class="theme-deco">${t.top||'━━━━━━━━'}</div>
    <div class="theme-name">${t.name}</div>
    <div class="theme-deco" style="margin-top:3px">${t.bot_line||'━━━━━━━━'}</div>
    <div style="margin-top:6px">${themeStatusBadge(t)}</div>
  </div>`;
}

function _renderThemes() {
  if(!_themeData) return;
  const ownedCount=_themeData.filter(t=>t.owned||t.active).length;
  const premiumCount=_themeData.filter(t=>t.premium&&!t.owned).length;
  const filtered=_themeFilter==='owned'?_themeData.filter(t=>t.owned||t.active)
    :_themeFilter==='premium'?_themeData.filter(t=>t.premium)
    :_themeData;
  const groups={};
  filtered.forEach(t=>(groups[t.rarity]=groups[t.rarity]||[]).push(t));
  const ORDER=['common','uncommon','rare','epic','legendary','mythic','shadow','zarniki','seasonal'];

  const filterBar=`<div style="display:flex;gap:5px;margin-bottom:12px;flex-wrap:wrap">
      <button class="btn btn-sm ${_themeFilter==='all'?'btn-gold':'btn-ghost'}" onclick="setThemeFilter('all')">Все</button>
      <button class="btn btn-sm ${_themeFilter==='owned'?'btn-gold':'btn-ghost'}" onclick="setThemeFilter('owned')">Мои (${ownedCount})</button>
      <button class="btn btn-sm ${_themeFilter==='premium'?'btn-gold':'btn-ghost'}" onclick="setThemeFilter('premium')">✨ Премиум (${premiumCount})</button>
    </div>`;

  if(!Object.keys(groups).length){
    el('col-themes').innerHTML=filterBar+`<div class="empty-state"><div class="es-icon">🎨</div><div class="es-title">Ничего не найдено</div><div class="es-sub">В этой категории нет тем</div></div>`;
    return;
  }

  el('col-themes').innerHTML=filterBar+ORDER.filter(r=>groups[r]).map(r=>{
    const items=groups[r];
    const label=`${items[0]?.badge||''} ${items[0]?.rarity_label||r}`;
    // Зарниковая → подкатегории: 💻 IT-стиль и ✨ Премиум
    if(r==='zarniki'){
      const it=items.filter(t=>t.it), rest=items.filter(t=>!t.it);
      const sub=(ttl,arr)=>arr.length?`<div style="font-size:11px;font-weight:700;color:var(--gold2);margin:6px 2px 8px">${ttl}</div><div class="theme-grid" style="margin-bottom:10px">${arr.map(_themeCardHTML).join('')}</div>`:'';
      return `<div class="card">
        <div class="card-title">✨ Зарниковая <span style="font-size:9px;color:var(--muted);font-weight:600">— премиум за донат</span></div>
        ${sub('💻 IT-стиль', it)}
        ${sub('🌌 Премиум', rest)}
      </div>`;
    }
    return `<div class="card">
      <div class="card-title">${label}</div>
      <div class="theme-grid">${items.map(_themeCardHTML).join('')}</div>
    </div>`;
  }).join('');
}

function _premBar(pct, len=7) {
  const f=Math.round(pct/100*len);
  return '▰'.repeat(f)+'▱'.repeat(len-f);
}

// ── Profile preview — Render Raw String approach ─────────────────────────────
// Backend generates the EXACT same HTML string as sent to Telegram.
// Frontend just sets innerHTML + white-space:pre-wrap. No parsing.

function buildProfilePreview(t) {
  // Empty container — filled immediately via fetch (no visible flash)
  return `<div class="profile-preview" style="min-height:40px"></div>`;

  const p    = _profileData;
  const name = p ? (p.username || 'Игрок') : 'Игрок';
  const lvl  = p?.chats?.[0]?.user_level || 1;
  const xp   = p?.chats?.[0]?.user_xp || 0;
  const xpMax = 3000; // approximate per level
  const xpInLvl = xp % xpMax;
  const pct  = p ? Math.min(99, Math.round(xpInLvl / xpMax * 100)) : 79;
  const bar  = '█'.repeat(Math.round(pct/100*8)) + '░'.repeat(8 - Math.round(pct/100*8));
  const mora = p ? fmt(Math.round(p.mora||0)) : '12 500';
  const dia  = p ? (p.diamonds||0).toFixed(1) : '45.0';
  const ach  = p?.achievements || 14;
  const st   = p?.streak || 7;
  const dMsgs = p?.chats?.[0]?.user_messages_count_per_day || 54;
  const wMsgs = p?.chats?.[0]?.user_messages_count_per_week || 389;
  const aMsgs = p?.chats?.[0]?.user_messages_count_all_time || 490;
  const acc  = t.accent || '🔮';
  const side = t.side || '';
  const pfx  = t.prefix || '';
  const isZarniki = !!pfx;

  const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  // Zarniki: left sidebar in accent color, regular: no prefix
  const sideChar = pfx ? `<span style="color:#5a6480;user-select:none">${pfx}</span>` : '';
  const L   = (html) => `<span class="pp-line">${sideChar}${html}</span><br>`;
  const SEP = () => {
    const sepText = esc(t.sep||'');
    return isZarniki
      ? `<span class="pp-sep-line">${sideChar}${sepText}</span><br>`
      : `<span class="pp-sep-line">${sepText}</span><br>`;
  };

  // Top block: zarniki = only frame line; others = header + sep
  const topParts = (t.top||'').split('\n');
  const topHTML = topParts.map((l,i) =>
    `<span class="${i===0?'pp-header-line':'pp-sep-line'}">${esc(l)}</span><br>`
  ).join('');

  // Name line — mirroring identity.py logic exactly
  const nameLine = side
    ? `<b>${esc(side)} ${esc(acc)} ${esc(name)} ${esc(acc)}</b>`
    : `<b>${esc(acc)} ${esc(name)}</b>`;

  // Bot phrase
  const botHTML = (t.bot||'').replace('{id}','894721653').split('\n')
    .map(l=>`<span class="pp-bot-line">${esc(l)}</span><br>`).join('');

  // XP compact
  const xpStr = `(${xpInLvl<1000?xpInLvl:Math.round(xpInLvl/100)/10+'k'}/${xpMax<1000?xpMax:xpMax/1000+'k'})`;

  return `<div class="profile-preview">${topHTML}
${L(nameLine)}
${L('🌍 Мастер Теней  |  🏘 Ветеран')}
${L('📅 В чате с: 01.01.2026')}
<br>
${SEP()}
<br>
${L(`🌟 Ур.<b>${lvl}</b>  [${bar}] ${pct}% ${xpStr}`)}
${L('⚖️ Реп: +0  |  ⚠️ Варны: 0')}
${L(`💰 ${mora} 🪙  |  💎 ${dia}  |  🏆 ${ach} ачив.`)}
${L(`🔥 Стрик: <b>${st}</b> дн.`)}
<br>
${SEP()}
<br>
${L(`💬 ${dMsgs} д  |  ${wMsgs} н  |  ${aMsgs} всего`)}
${L('💍 Не в браке')}
${L(`🎨 Тема: ${esc(t.name||'?')}`)}
<br>
${SEP()}
<br>
${L('🐾 <b>Питомцы:</b>')}
${L('├ ⚔️ Актив: Буря · Lv8 · 🟢 · 📦×8')}
${L('└ 💤 Пассив: Золото · Lv5 · 🟡 · 📦×3')}
${SEP()}
${L('🆔 <code>894721653</code>')}
${botHTML}</div>`;
}

function _buildPremiumPreview(t, tpl) {
  const p = _profileData;
  const name  = p ? (p.username || 'Игрок') : 'Игрок';
  const lvl   = p?.chats?.[0]?.user_level || 1;
  const pct   = 79;
  const bar   = _premBar(pct);
  const mora  = p ? fmt(Math.round(p.mora||0)) : '47.3k';
  const dia   = p ? (p.diamonds||0).toFixed(1) : '215';
  const ach   = p?.achievements || 42;
  const streak= p?.streak || 30;
  const nameU = name.toUpperCase();
  // simplified global rank
  const grank = p?.rank || 'Мастер Теней';
  const lrank = p?.chats?.[0]?.chat_local_rank_name || 'Ветеран';

  const lines = [];
  if(tpl === 'system_override') {
    lines.push('▼ 💻 ＳＹＳＴＥＭ_ＯＶＥＲＲＩＤＥ 💻 ▼','',
      `>_ 👤 USER_ID: ${name} 📟`,
      `>_ 🛡️ AUTH: ${grank}`,
      `>_ 🔋 SYNC: Ур.${lvl} [${bar}] ${pct}% ⚡`,'',
      '► [ 💾 ROOT / ASSETS ] ──────────────',
      `/// 🪙 CRDT: ${mora} 🔌 /// 💎 CRYPT: ${dia} 🌐`,'',
      '► [ 📡 ROOT / DATA ] ────────────────',
      `/// ⚖️ REP: +0 ⚙️  /// 🏆 ACHV: ${ach} 🔓`,'',
      '► [ 🔌 ROOT / ENTITIES ] ────────────',
      '[+] 🔗 LINK: Аня (212d) 💟',
      '[*] 🤖 PORT_01: Буря (Феникс) [v8.0] 🔥','',
      '▲ 🕹️ ID: 894721653 ▲',
      '*>_ Проснись, Нео. Ты всё ещё в чате… ▮* 🟢');
  } else if(tpl === 'wind_free') {
    lines.push('【 🎐 ‧̍̊˙· ВЕТЕР СВОБОДЫ ·˙‧̍̊ 🎐 】','',
      `👤 ${nameU} ✦ 🌍 ${grank} 🪽`,
      `[ 🗺️ Ранг: 🏘 ${lrank} ]`,
      `╰┈➤ 🌬️ Ур. ${lvl} [${bar}] ${pct}% ✨`,'',
      '▽ 【 🎒 ИНВЕНТАРЬ И ЗАСЛУГИ 】',
      `[ 🪙 ${mora} Монет ] ✧ [ 💎 ${dia} Кристаллов ]`,
      `[ ⚖️ Кармы: +0 🪷 ] ✧ [ 🏆 Ачивок: ${ach} 📜 ]`,'',
      '▽ 【 🕊️ АКТИВНОСТЬ В МИРЕ 】',
      '💬 Связь: 42/дн 🍃 | 892/нед ✉️ | 23k/вс 🌐','',
      '▽ 【 ⚔️ СПУТНИКИ И ОТРЯД 】',
      '💍 Узы: Аня (212 дн.) 💞',
      '🐾 Слот I: Буря (Феникс) ⟡ Ранг 8 🔥','',
      '【 🎐 ID: 894721653 】',
      '«Разве не прекрасно…» 🍃');
  } else if(tpl === 'empire') {
    lines.push('🥂 ✧ ━━ ⚜️ ИМПЕРИЯ ⚜️ ━━ ✧ 🥂','',
      `👑 ВЛАДЕЛЕЦ: ${name} ✦ 🌍 ${grank}`,
      `╰┈➤ 💠 Ур. ${lvl} [${bar}] ${pct}% ✨`,'',
      '▼ 【 🏦 ФИНАНСОВЫЙ КАПИТАЛ 】',
      `💳 Наличные: ${mora} 🪙 | 💎 Брюллики: ${dia} 💠`,
      `⚖️ Влияние: +0 🍷 | 🏆 Награды: ${ach} 🏵️`,'',
      '▼ 【 🪩 СВЕТСКАЯ АКТИВНОСТЬ 】',
      '💌 Чат: 42/дн 🍾 | 892/нед 🥂 | 23k/вс 🎭','',
      '▼ 【 ⚜️ ПРИВИЛЕГИИ И СВИТА 】',
      '💍 Узы крови: Аня (212 дн.) 🌹',
      '🐾 Телохранитель: Буря (Феникс) ✦ Ранг 8 🦅','',
      '🥂 ✧ ━━ 💳 ID: 894721653 ━━ ✧ 🥂',
      '«У роскоши нет предела…» 💸');
  }
  return `<div class="profile-preview">
    ${lines.map(l=>l===''?'<div style="height:6px"></div>':`<div class="pp-line">${l}</div>`).join('')}
  </div>`;
}

function openThemeModal(tid) {
  if(!_themeData) return;
  const t = _themeData.find(x => x.theme_id === tid);
  if(!t) return;

  const price = t.price_mora ? `${fmt(t.price_mora)} 🪙` : t.price_diamonds ? `${t.price_diamonds} 💎`
    : t.price_zarniki ? `${fmt(t.price_zarniki)} ✨` : t.price_dark ? `${t.price_dark} 🌑` : null;
  const src = SRC[t.source] || SRC[t.source?.split('_')[0]+'_'+t.source?.split('_').slice(1).join('_')] || {label:t.source, desc:'', action:null};
  // Покупаемо в вебе: магазинные (🪙/💎) и донатные (✨). Тёмные (🌑) — через бота.
  const buyable = price && (t.source === 'shop_mora' || t.source === 'shop_diamond' || t.source === 'zarniki');

  const body = `
    <div style="margin-bottom:12px">
      <div style="font-size:10px;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:1px">Предпросмотр профиля</div>
      ${buildProfilePreview(t)}
    </div>
    <div class="divider"></div>
    <div class="irow"><span class="ik">Редкость</span><span>${t.badge} ${t.rarity_label}</span></div>
    ${t.desc ? `<div style="font-size:11px;color:var(--muted);margin:8px 0;line-height:1.4">${t.desc}</div>` : ''}
    <div class="divider"></div>
    <div style="font-size:10px;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:1px">Как получить</div>
    <div style="background:var(--card);border-radius:var(--r);padding:10px">
      <div style="font-size:12px;font-weight:600;color:var(--bright);margin-bottom:4px">${src.label}</div>
      <div style="font-size:11px;color:var(--muted);line-height:1.4">${src.desc}</div>
      ${src.action ? `<button class="btn btn-ghost btn-sm btn-full" style="margin-top:8px" onclick="${src.action.f}">${src.action.l}</button>` : ''}
    </div>
    ${price ? `<div class="irow" style="margin-top:10px"><span class="ik">Цена</span><span style="color:var(--gold);font-weight:700">${price}</span></div>` : ''}
    ${t.active ? `<div style="text-align:center;padding:10px;color:var(--gold);font-size:12px;font-weight:600">✓ Это ваша активная тема</div>` : ''}
  `;

  const btns = [{l:'Закрыть', c:'btn-ghost', f:'CM()'}];
  if(!t.active && t.owned) btns.unshift({l:'✓ Надеть', c:'btn-gold', f:`doEquipTheme('${tid}')`});
  else if(buyable && !t.owned) btns.unshift({l:`Купить — ${price}`, c:'btn-gold', f:`doBuyTheme('${tid}')`});

  OM(t.name, body, btns);

  // Fetch raw profile string from backend (Render Raw String approach)
  // The backend returns the exact string the bot would send to Telegram.
  api(`/themes/preview/${tid}`)
    .then(r => {
      const container = el('mb')?.querySelector('.profile-preview');
      if(container && r.text) {
        container.innerHTML = r.text;  // raw HTML — <b>,<i>,<code> render natively
      }
    })
    .catch(() => {
      const container = el('mb')?.querySelector('.profile-preview');
      if(container) container.innerHTML = `<span style="color:var(--muted);font-size:11px">Нет данных профиля</span>`;
    });
}

function doBuyTheme(tid) {
  api('/themes/buy', {method:'POST', body:JSON.stringify({theme_id:tid})})
    .then(r => { toast(`✅ ${r.theme_name} куплена!`); CM(); loadThemes(); loadProfile(); })
    .catch(e => toast(e, false));
}
function doEquipTheme(tid) {
  api('/themes/equip', {method:'POST', body:JSON.stringify({theme_id:tid})})
    .then(() => { toast('✅ Тема активирована!'); CM(); loadThemes(); })
    .catch(e => toast(e, false));
}

// ── Top ───────────────────────────────────────────────────────────────────────
// Priority: chat where mini app was opened (_initChatId) → profile chat (_cid)
function loadTop(){switchTop('local',document.querySelector('#pg-hof .tb'));}
function switchTop(mode, btn) {
  document.querySelectorAll('#pg-hof .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');

  const localChatId = _initChatId || _cid;
  const localChatName = _initChatTitle || '(из профиля)';

  if (mode === 'local' && !localChatId) {
    el('top-c').innerHTML='<div style="color:var(--muted);font-size:12px;padding:10px">Откройте мини-апп через кнопку в чате, чтобы видеть его топ.</div>';
    return;
  }
  el('top-c').innerHTML='<div class="loader">Загрузка...</div>';
  api(mode==='global' ? '/top/global' : `/top/local/${localChatId}`)
    .then(rows => {
      const header = mode === 'local'
        ? `<div style="font-size:11px;color:var(--muted);padding:0 2px 10px">📍 Чат: ${localChatName}</div>`
        : `<div style="font-size:11px;color:var(--muted);padding:0 2px 10px">🌍 Все чаты · за всё время</div>`;
      if(!rows.length){
        el('top-c').innerHTML='<div class="empty-state"><div class="es-icon">🏆</div><div class="es-title">Пока нет данных</div><div class="es-sub">Топ появится после первых сообщений</div></div>';
        return;
      }
      // Подиум для топ-3 + список остальных
      const top3=rows.slice(0,3), rest=rows.slice(3,30);
      const podium = top3.length>=2 ? '<div class="podium">'+top3.map((r,i)=>`
        <div class="pd pd-${i+1}">
          <div class="pd-medal">${MEDALS[i]}</div>
          <div class="pd-name">${vipName(r.username, r.is_vip)}</div>
          <div class="pd-cnt">${fmt(r.count)} 💬</div>
        </div>`).join('')+'</div>' : '';
      const restHtml = rest.length ? '<div class="card">'+rest.map((r,i)=>`<div class="trow">
          <div class="tpos">${i+4}</div>
          <div class="tname">${vipName(r.username, r.is_vip)}</div>
          <div class="tcnt">${fmt(r.count)} 💬</div>
        </div>`).join('')+'</div>' : '';
      // если меньше 2 игроков — просто список
      const single = (top3.length<2) ? '<div class="card">'+top3.map((r,i)=>`<div class="trow">
          <div class="tpos">${MEDALS[i]||(i+1)}</div><div class="tname">${vipName(r.username, r.is_vip)}</div>
          <div class="tcnt">${fmt(r.count)} 💬</div></div>`).join('')+'</div>' : '';
      el('top-c').innerHTML = header + podium + single + restHtml;
    })
    .catch(e => { el('top-c').innerHTML=`<div class="err">${e}</div>`; });
}

// ── Exchange ──────────────────────────────────────────────────────────────────
function loadExchange() {
  el('mkt-exch').innerHTML='<div class="loader">Загрузка...</div>';
  api('/exchange/').then(d=>{
    if(!d.active){
      const when=d.scheduled?`<div class="irow" style="margin-top:10px"><span class="ik">Следующий ивент</span><span style="color:var(--teal)">${d.scheduled.starts_at||'—'}</span></div>`:'';
      el('mkt-exch').innerHTML=`<div class="card card-gold">
        <div style="text-align:center;padding:16px 0 12px">
          <div style="font-size:36px;margin-bottom:8px">💱</div>
          <div style="font-size:15px;font-weight:700;color:var(--bright);margin-bottom:6px">Ивент обмена Мора → Алмазы</div>
          <div style="font-size:11px;color:var(--muted)">Сейчас неактивен</div>
        </div>
        <div class="divider"></div>
        <div style="font-size:13px;font-weight:600;color:var(--bright);margin-bottom:8px">Что такое ивент обмена?</div>
        <div style="font-size:12px;color:var(--muted);line-height:1.6">
          Один раз в неделю (случайный день) открывается возможность
          обменять Мору на Алмазы по фиксированному курсу.<br><br>
          💡 <b>Курс обмена:</b> 3 000 🪙 = 1 💎<br>
          📊 <b>Дневной лимит:</b> 300 💎<br>
          ⏱ <b>Длительность:</b> 24 часа<br><br>
          Когда ивент начнётся — бот объявит в чатах!
        </div>
        ${when}
      </div>`;
      return;
    }
    const maxCanBuy = Math.floor(Math.min(d.remaining, d.mora / d.rate));
    const rateHtml = `<div class="exch-rate">
      <div class="er">1 💎 = ${fmt(d.rate)} 🪙</div>
      <div class="el">Квота: ${d.remaining.toFixed(1)} / ${d.daily_cap} 💎 осталось</div>
    </div>`;
    if(maxCanBuy < 1) {
      const reason = d.remaining <= 0 ? 'Дневной лимит исчерпан — возвращайтесь завтра.' : `Нужно минимум ${fmt(d.rate)} 🪙 для обмена (у вас ${fmt(d.mora)} 🪙).`;
      el('mkt-exch').innerHTML=`${rateHtml}<div class="card" style="text-align:center;padding:20px">
        <div style="font-size:28px;margin-bottom:8px">${d.remaining<=0?'✅':'💸'}</div>
        <div style="font-size:13px;color:var(--muted)">${reason}</div>
      </div>`;
      return;
    }
    el('mkt-exch').innerHTML=`${rateHtml}
      <div class="card">
        <div class="card-title">Сколько Алмазов получить?</div>
        <div class="irow"><span class="ik">У вас</span><span>${fmt(d.mora)} 🪙</span></div>
        <div class="irow"><span class="ik">Стоимость</span><span id="exch-cost" style="color:var(--gold)">—</span></div>
        <div class="range-wrap">
          <input type="range" id="exch-dia" min="1" max="${maxCanBuy}" value="1" step="1"
                 oninput="updExch(${d.rate},${d.mora})"/>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <input type="number" id="exch-num" class="num-input" style="max-width:120px"
                 min="1" max="${maxCanBuy}" value="1"
                 oninput="syncExchRange(${d.rate},${d.mora})"/>
          <span style="font-size:14px">💎</span>
        </div>
        <button class="btn btn-gold btn-full" style="margin-top:10px" onclick="doExchange(this)">💱 Обменять</button>
      </div>`;
    updExch(d.rate, d.mora);
  }).catch(e=>{el('mkt-exch').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
function updExch(rate, mora) {
  const v=parseInt(el('exch-dia')?.value||1);
  if(el('exch-num'))el('exch-num').value=v;
  const cost=v*rate;
  const c=el('exch-cost');
  if(c)c.textContent=`${fmt(cost)} 🪙${cost>mora?' ❌ недостаточно':''}`;
}
function syncExchRange(rate, mora) {
  const v=parseInt(el('exch-num')?.value||1);
  if(el('exch-dia'))el('exch-dia').value=v;
  updExch(rate, mora);
}
function doExchange(btn) {
  const v=parseInt(el('exch-num')?.value||0);
  if(!v){toast('Введите количество.',false);return;}
  btn.disabled=true;
  api('/exchange/convert',{method:'POST',body:JSON.stringify({diamonds:v})})
    .then(r=>{toast(`✅ +${r.diamonds_gained} 💎  −${fmt(r.mora_spent)} 🪙`);loadExchange();refreshCurrBar();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

// ── Dark Mora ─────────────────────────────────────────────────────────────────
function loadDarkMora() {
  // Load merchant status in parallel
  api('/dark-mora/merchant-status').then(m=>{
    const div = document.createElement('div');
    div.className = 'card';
    div.style.marginBottom = '10px';
    let merchantHtml = '';
    if(m.active) {
      merchantHtml = `<div style="background:rgba(201,168,76,.12);border:1px solid var(--border);border-radius:var(--r);padding:10px;margin-bottom:10px">
        <div style="font-size:13px;font-weight:700;color:var(--gold2);margin-bottom:4px">🕵️ Теневой Торговец ЗДЕСЬ!</div>
        <div style="font-size:11px;color:var(--muted)">Найди ключевое слово в пророчестве в чате → <code>бот слово, [слово]</code></div>
      </div>`;
    } else if(m.next_expected) {
      const next = new Date(m.next_expected);
      const diff = Math.max(0, Math.floor((next - Date.now()) / 1000));
      const days = Math.floor(diff/86400), hours = Math.floor((diff%86400)/3600);
      merchantHtml = `<div style="background:var(--dim);border-radius:var(--r);padding:10px;margin-bottom:10px">
        <div style="font-size:12px;font-weight:600;color:var(--bright);margin-bottom:3px">🕵️ Теневой Торговец</div>
        <div style="font-size:11px;color:var(--muted)">Следующий примерно через ${days ? days+'д '+hours+'ч' : hours+'ч'}</div>
        <div style="font-size:10px;color:var(--muted);margin-top:3px">${m.how_it_works}</div>
      </div>`;
    } else {
      merchantHtml = `<div style="background:var(--dim);border-radius:var(--r);padding:10px;margin-bottom:10px">
        <div style="font-size:12px;font-weight:600;color:var(--bright);margin-bottom:3px">🕵️ Теневой Торговец</div>
        <div style="font-size:11px;color:var(--muted)">${m.how_it_works}</div>
        <div style="font-size:10px;color:var(--muted);margin-top:3px">Появляется каждые ${m.cooldown_days} дня · Награда: ${m.reward_min}–${m.reward_max} 🌑</div>
      </div>`;
    }
    const wrap = el('dkc-merchant');
    if(wrap) wrap.innerHTML = merchantHtml;
  }).catch(()=>{});

  el('dkc').innerHTML=`
    <div id="dkc-merchant"></div>
    <div class="card card-gold">
    <div class="card-title">🌑 Тёмная Мора</div>
    <div style="font-size:12px;color:var(--muted);line-height:1.5;margin-bottom:12px">
      Нелегальная валюта. Нельзя купить — только заработать нечестным путём.<br>
      Тратится на Реликвии и Теневые темы.
    </div>
    <div class="divider"></div>
    <div style="font-size:12px;font-weight:600;color:var(--bright);margin:10px 0 6px">🎲 Контрабанда</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:8px">
      Ставь Мору на рискованную сделку. 40% — успех, 35% — провал, 25% — поймали.<br>
      Кулдаун: 7 дней. При поимке — штраф 14 дней.
    </div>
    <input id="contra-stake" type="number" class="num-input" placeholder="Ставка (100–5000 🪙)" min="100" max="5000" step="50"/>
    <button class="btn btn-gold btn-full" onclick="doContrabanda(this)">🎲 Рискнуть</button>
    <div class="divider"></div>
    <div style="font-size:12px;font-weight:600;color:var(--bright);margin:10px 0 6px">🌑 Культ Бездны</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:8px">
      Ритуал доступен с 23:00 до 01:00 UTC при стрике 7+, уровне 6+, 3+ питомцах.<br>
      Награда: 10–20 🌑 раз в 30 дней.
    </div>
    <button class="btn btn-ghost btn-full" onclick="doRitual(this)">🌑 Провести ритуал</button>
  </div>`;
}
function doContrabanda(btn) {
  const v=parseInt(el('contra-stake')?.value||0);
  if(!v||v<100||v>5000){toast('Ставка: 100–5000 🪙.',false);return;}
  OM('🎲 Подтверждение',`<div class="irow"><span class="ik">Ставка</span><span style="color:var(--gold)">${fmt(v)} 🪙</span></div>
    <div style="font-size:11px;color:var(--muted);margin-top:8px">40% успех · 35% провал · 25% поймают (штраф 14д)</div>`,
    [{l:'🎲 Рискнуть',c:'btn-red',f:`runContrabanda(${v})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function runContrabanda(stake) {
  CM();
  api('/dark-mora/contrabanda',{method:'POST',body:JSON.stringify({stake})})
    .then(r=>toast(r.result_text||'Готово!',r.success))
    .catch(e=>toast(e,false));
}
function doRitual(btn) {
  btn.disabled=true;
  api('/dark-mora/ritual',{method:'POST'}).then(r=>toast(r.message||'✅',true)).catch(e=>{toast(e,false);btn.disabled=false;});
}

// ── VIP-подписка (Implementation Block 2.5) ─────────────────────────────────────
// ── ✨ Премиум-хаб: донат-магазин Зарников (Stars) + VIP ──────────────────────
let _zarPkgs=null;
// Еженедельная VIP-крутка выдаётся в понедельник (scheduler). Считаем до ближайшего
// понедельника 00:00 МСК (UTC+3) — единый тайм-зон проекта.
function _vipCrateText() {
  const nowMs = Date.now();
  const mskMs = nowMs + 3*3600000;                 // wall-clock МСК как если бы это был UTC
  const d = new Date(mskMs);
  let daysToMon = (8 - d.getUTCDay()) % 7;         // пн=1 → 0; иначе дни до пн
  if(daysToMon===0) daysToMon = 7;                 // сегодня пн → ждём следующий
  const target = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()+daysToMon, 0,0,0);
  let mins = Math.max(0, Math.round((target - mskMs)/60000));
  const dd = Math.floor(mins/1440); mins -= dd*1440;
  const hh = Math.floor(mins/60);   mins -= hh*60;
  return dd>0 ? `${dd}д ${hh}ч` : hh>0 ? `${hh}ч ${mins}м` : `${mins}м`;
}
function loadVip() {
  el('mkt-vip').innerHTML = '<div class="loader">Загрузка...</div>';
  Promise.all([
    api('/payments/zarniki/packages').catch(()=>null),
    api('/vip/status'),
  ]).then(([pk, d])=>_renderPremiumHub(pk, d))
    .catch(e=>{el('mkt-vip').innerHTML = `<div class="err">${e}</div>`;});
}

function _renderPremiumHub(pk, d) {
  _zarPkgs = pk;
  const bal = Math.floor(_profileData?.zarniki || 0);
  const perStar = pk?.per_star || 10;

  // 1. Донат-витрина Зарников за Telegram Stars
  const pkgCards = (pk?.packages || []).map((p,i)=>{
    const best = i===(pk.packages.length-1);
    return `<div class="zar-pack${best?' zar-best':''}" onclick="buyZarniki(${p.stars})">
      ${best?'<span class="zar-best-tag">ВЫГОДНО</span>':''}
      <div class="zar-amt">${fmt(p.zarniki)} ✨</div>
      <div class="zar-stars">${p.stars} ⭐</div>
    </div>`;
  }).join('');

  const donateCard = `
    <div class="prem-card" style="text-align:center">
      <div style="font-size:34px;animation:floaty 3.5s infinite">✨</div>
      <div class="prem-title">Зарники</div>
      <div style="font-size:11px;color:var(--muted);margin:4px 0 2px">Донат-валюта: премиум-темы, VIP, обмен на 🪙/💎</div>
      <div style="font-size:13px;color:var(--gold2);font-weight:800;margin-bottom:10px">Баланс: ${fmt(bal)} ✨</div>
      <div class="zar-grid">${pkgCards}</div>
      <div style="display:flex;gap:6px;margin-top:10px">
        <input id="zar-custom" type="number" min="1" class="num-input" style="flex:1;margin:0" placeholder="Своя сумма ⭐"/>
        <button class="btn btn-gold" onclick="buyZarnikiCustom()">Купить</button>
      </div>
      <div style="font-size:9.5px;color:var(--muted);margin-top:6px">1 ⭐ = ${perStar} ✨ · оплата звёздами Telegram</div>
    </div>`;

  // 2. VIP
  const seniorityLine = d.seniority_days>0
    ? `<div style="font-size:11px;color:var(--gold2);margin-top:4px">🏅 Стаж VIP: ${d.seniority_months} мес. (${d.seniority_days} дн.)</div>` : '';
  const vipStatus = d.active
    ? `<div class="prem-card">
        <div class="prem-tag">VIP</div>
        <div class="prem-title">👑 ${d.tier_label}</div>
        <div style="font-size:11.5px;color:var(--muted);margin-top:3px">Истекает ${new Date(d.expires_at).toLocaleDateString('ru-RU')} · осталось ${d.days_left} дн.</div>
        ${seniorityLine}
        <div style="display:flex;align-items:center;gap:6px;margin-top:8px;padding:7px 10px;background:rgba(232,181,77,.1);border:1px solid var(--border);border-radius:12px">
          <span style="font-size:16px">🎁</span>
          <span style="font-size:11px;color:var(--text)">Бесплатная крутка через <b style="color:var(--gold2)">${_vipCrateText()}</b></span>
        </div>
        <div style="font-size:11px;color:var(--muted);margin-top:6px">Можно продлить — срок сложится, тариф сменится сразу.</div>
      </div>`
    : `<div class="card card-gold">
        <div class="card-title">👑 VIP-подписка</div>
        <div style="font-size:12px;color:var(--muted);line-height:1.5">Косметика, удобство и еженедельные подарки — без преимущества в силе.</div>
        ${seniorityLine}
      </div>`;

  const tiers = d.tiers.map(t=>{
    const gift=[];
    if(t.gift_mora>0) gift.push(`${fmt(t.gift_mora)} 🪙`);
    if(t.gift_diamonds>0) gift.push(`${fmt(t.gift_diamonds)} 💎`);
    t.gift_items.forEach(i=>gift.push(`${i.qty}× ${i.name}`));
    const weekly = t.weekly.map(i=>`${i.qty}× ${i.name}`);
    const afford = bal >= t.price_zarniki;
    return `<div class="prem-card">
      <div class="prem-title">${t.label}</div>
      <div class="prem-price">${fmt(t.price_zarniki)} ✨ <span style="font-size:10px;color:var(--muted);font-weight:600">/ ${t.duration_days} дн.</span></div>
      <div class="prem-list">🎁 ${gift.join(', ')}<br>📅 Еженедельно: ${weekly.join(', ')}${t.extra_slot?'<br>🐾 +1 слот питомника':''}</div>
      <button class="btn ${afford?'btn-gold':'btn-ghost'} btn-full" style="margin-top:4px" onclick="${afford?`doBuyVip('${t.tier}','${t.label}',${t.price_zarniki})`:`goToZarTop()`}">${afford?`Оформить за ${fmt(t.price_zarniki)} ✨`:`Нужно ${fmt(t.price_zarniki)} ✨ — пополнить`}</button>
    </div>`;
  }).join('');

  el('mkt-vip').innerHTML = donateCard
    + `<div class="card-title" style="margin:14px 2px 8px;font-size:14px">👑 VIP-подписка</div>`
    + vipStatus + tiers;
}

function goToZarTop() {
  el('mkt-vip')?.scrollIntoView({behavior:'smooth', block:'start'});
  toast('Пополни Зарники сверху ☝️');
}

function buyZarniki(stars) {
  api('/payments/zarniki/invoice',{method:'POST',body:JSON.stringify({stars})})
    .then(r=>{
      const link = r.link;
      const onStatus = status=>{
        if(status==='paid'){
          toast('✨ Зарники зачислены! Спасибо за поддержку 💜');
          CM();
          setTimeout(()=>{ loadProfile(); if(_mktTab==='vip') loadVip(); }, 1600);
        } else if(status==='failed'){ toast('Платёж не прошёл',false); }
      };
      // openInvoice есть в telegram-web-app.js, но клиент может НЕ поддерживать метод
      // (старая версия / запуск по обычной ссылке из группы) → WebAppMethodUnsupported.
      // Гейтим по версии + try/catch, иначе открываем счёт ссылкой в Telegram.
      const verOk = tg && (!tg.isVersionAtLeast || tg.isVersionAtLeast('6.1'));
      if(tg && typeof tg.openInvoice === 'function' && verOk){
        try { tg.openInvoice(link, onStatus); return; } catch(e) { /* fallback ниже */ }
      }
      if(tg && typeof tg.openTelegramLink === 'function' && verOk){
        try { tg.openTelegramLink(link); toast('Счёт открыт в Telegram — оплати звёздами там'); return; } catch(e) {}
      }
      window.open(link, '_blank');
      toast('Счёт открыт — оплати звёздами в Telegram');
    })
    .catch(e=>toast(e,false));
}
function buyZarnikiCustom() {
  const v=parseInt(el('zar-custom')?.value||'0');
  if(!v || v<1) return toast('Введите количество звёзд (от 1)',false);
  buyZarniki(v);
}

function doBuyVip(tier, label, price) {
  OM(`👑 ${label}`,
    `<div style="font-size:12px;color:var(--muted);line-height:1.5">Списать <b style="color:var(--gold)">${fmt(price)} ✨</b> и оформить <b>${label}</b>?</div>`,
    [{l:'✅ Купить', c:'btn-gold', f:`confirmBuyVip('${tier}')`}, {l:'Отмена', c:'btn-ghost', f:'CM()'}]);
}
function confirmBuyVip(tier) {
  api('/vip/purchase', {method:'POST', body:JSON.stringify({tier})})
    .then(r=>{
      el('mb').innerHTML = `<div style="font-size:13px;line-height:1.7">${r.message.replace(/\n/g,'<br>')}</div>`;
      el('mf').innerHTML = `<button class="btn btn-gold btn-sm" onclick="CM();loadVip();loadProfile();">Отлично!</button>`;
    })
    .catch(e=>toast(e,false));
}

// swArena and swMkt are defined above with correct dark/exch handling

// ── Auction search ────────────────────────────────────────────────────────────
let _allLots=[];
function filterAuction(q) {
  const f = q.toLowerCase();
  const lots = f ? _allLots.filter(l => {
    const name = (l.item_name_display || l.item_name || '').split('||')[0].toLowerCase();
    return name.includes(f);
  }) : _allLots;
  renderLots(lots, f);
}
// Category → icon emoji for auction lot cards
const LOT_CAT_ICON={egg:'🥚',food:'🍖',spin_token:'🎟',booster:'⚡',material:'💠',utility:'🏡',theme:'🎨',pet:'🐾'};

function renderLots(lots, searchQuery) {
  if (!el('lot-list')) return;
  if(!lots.length) {
    el('lot-list').innerHTML = searchQuery
      ? `<div style="text-align:center;padding:24px;color:var(--muted)"><div style="font-size:24px;margin-bottom:6px">🔍</div><div style="font-size:12px">Ничего не найдено по «${searchQuery}»</div></div>`
      : `<div style="text-align:center;padding:32px 16px;color:var(--muted)"><div style="font-size:32px;margin-bottom:8px">🏛️</div><div style="font-size:13px;font-weight:600;margin-bottom:4px">Аукцион пуст</div><div style="font-size:11px">Выставь свой лот — нажми «+ Выставить»!</div></div>`;
    return;
  }
  el('lot-list').innerHTML = lots.map(l => {
    const ends = new Date((l.ends_at+'').includes('T') ? l.ends_at : l.ends_at+'Z');
    const totalSec = 24*3600;
    const diffSec  = Math.max(0, Math.floor((ends - Date.now())/1000));
    const pctLeft  = Math.min(100, Math.round(diffSec/totalSec*100));
    const tl = diffSec > 3600
      ? Math.floor(diffSec/3600)+'ч '+Math.floor((diffSec%3600)/60)+'м'
      : Math.floor(diffSec/60)+'м';
    const isUrgent = diffSec < 3600;

    const hasBids = !!l.has_bids;
    const curBid  = l.current_bid || l.min_bid;
    const minNext = l.min_next_bid || (hasBids ? Math.ceil(curBid*1.05)+1 : Math.ceil(l.min_bid));
    const buyout  = l.buyout || 0;

    const displayName = l.item_name_display || (l.item_name||'?').split('||')[0] || '?';
    const desc   = l.item_description || '';
    const cat    = l.item_category || '';
    const icon   = LOT_CAT_ICON[cat] || (displayName.match(/^\p{Emoji}/u)?.[0] || '📦');
    const qty    = l.quantity > 1 ? ` ×${l.quantity}` : '';
    const bidArgs = `${l.id},'${displayName.replace(/'/g,"\\'")}',${curBid},${minNext},${hasBids},${buyout}`;

    const hotCls     = hasBids ? ' hot' : '';
    const buyoutCls  = buyout ? ' buyout-avail' : '';

    return `<div class="lot-card${hotCls}${buyoutCls}">
      <!-- Timer bar -->
      <div class="lot-timer-bar">
        <div class="lot-timer-fill" style="width:${pctLeft}%;${isUrgent?'background:var(--red)':''}"></div>
      </div>
      <!-- Top row: icon + info -->
      <div class="lot-card-top">
        <div class="lot-icon">${icon}</div>
        <div class="lot-info">
          <div class="lot-name">${displayName}${qty}</div>
          ${desc?`<div class="lot-desc">${desc}</div>`:''}
          <div class="lot-badges">
            <span class="lot-badge seller">👤 ${vipName(l.seller_name||'Игрок', l.seller_is_vip)}</span>
            <span class="lot-badge timer${isUrgent?' hot':''}">⏳ ${tl}</span>
            ${hasBids
              ? '<span class="lot-badge hot">🔥 Есть ставки</span>'
              : '<span class="lot-badge first">Первая ставка</span>'}
          </div>
        </div>
      </div>
      <!-- Footer: bid + button -->
      <div class="lot-footer">
        <div class="lot-price-wrap">
          <div class="lot-bid-label">${hasBids?'Текущая ставка':'Старт'}</div>
          <div class="lot-bid">${fmt(curBid)} 🪙</div>
          ${buyout?`<div class="lot-buyout">⚡ Выкуп: ${fmt(buyout)} 🪙</div>`:''}
        </div>
        <button class="btn btn-sm btn-gold" onclick="openBidModal(${bidArgs})" style="padding:8px 14px">
          💰 Ставка
        </button>
      </div>
    </div>`;
  }).join('');
}

// openDuelChallenge / submitDuelChallenge — defined above in the loadDuels section

// doSpin and closeSpinResult defined above (no loadGacha to avoid overwriting result)

// ── Browser Notifications ─────────────────────────────────────────────────────
function requestBrowserNotif() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission().then(p => { if(p==='granted') toast('✅ Уведомления включены!'); });
  }
}
function browserNotif(title, body) {
  if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
    new Notification(title, {body, icon: './favicon.ico'});
  }
}
// Request permission when user first connects WS
// Override connectWS with browser notification support
function connectWS() {
  if (!_uid) return;
  requestBrowserNotif();
  const wsUrl = BASE.replace('https://','wss://').replace('http://','ws://') + '/ws/'+_uid;
  _ws = new WebSocket(wsUrl);
  _ws.onmessage = e => {
    const ev = JSON.parse(e.data);
    if(ev.type!=='pong') showWsNotif(ev);
  };
  _ws.onclose = () => { setTimeout(connectWS, 4000); };
  _ws.onerror = () => {};
}

// ── WS ping/pong — prevents Cloudflare 100s idle timeout ─────────────────────
setInterval(() => { if (_ws?.readyState === WebSocket.OPEN) _ws.send('ping'); }, 25000);

// ── Refresh button helper ─────────────────────────────────────────────────────
function addRefreshBtn(containerId, reloadFn) {
  const c = el(containerId);
  if(!c) return;
  const ts = new Date().toLocaleTimeString('ru', {hour:'2-digit',minute:'2-digit'});
  const btn = `<div style="text-align:right;padding:0 0 8px">
    <button class="btn btn-ghost" style="font-size:10px;padding:3px 8px"
            onclick="${reloadFn}">🔄 Обновить · ${ts}</button>
  </div>`;
  if(!c.querySelector('[onclick*="Обновить"]')) c.insertAdjacentHTML('afterbegin', btn);
}

// ── Marriage card (в дашборде Обзор) ──────────────────────────────────────────
// Рендерит в #pro-marriage-card. Развод/банк/предложения — прямо внутри карточки
// (Закон близости: действие рядом с объектом).
function loadMarriageCard() {
  const host = el('pro-marriage-card');
  if(!host) return;
  Promise.all([api('/marriage/'), api('/marriage/proposals')]).then(([m, pr])=>{
    const proposals = pr.proposals || [];
    let propHtml = '';
    if(proposals.length) {
      propHtml = `<div class="card" style="border-color:var(--gold)">
        <div class="card-title">💌 Предложения руки и сердца (${proposals.length})</div>
        ${proposals.map(p=>`<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border2)">
          <div>
            <span style="font-weight:600">@${vipName(p.proposer_name||'ID'+p.proposer_id, p.proposer_is_vip)}</span>
            <span style="font-size:10px;color:var(--muted);margin-left:6px">${new Date(p.proposed_at).toLocaleDateString('ru')}</span>
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn btn-sm btn-gold" onclick="acceptProposal(${p.id},this)">✅ Принять</button>
            <button class="btn btn-sm btn-ghost" onclick="declineProposal(${p.id},this)">❌</button>
          </div>
        </div>`).join('')}
      </div>`;
    }
    if(!m.married){
      // Empty state с CTA (заповедь 5)
      host.innerHTML=propHtml+`<div class="card">
        <div class="empty-state">
          <div class="es-icon">💔</div>
          <div class="es-title">Вы не в браке</div>
          <div class="es-sub">Свяжите судьбу с другим игроком — напишите в чате<br><code>бот брак, @username</code></div>
        </div>
      </div>`;
      return;
    }
    const pets=m.family_pets||[];
    host.innerHTML=propHtml+`
      <div class="card card-gold">
        <div class="card-title">💍 Брак</div>
        <div style="text-align:center;padding:4px 0 12px">
          <div style="font-size:28px;margin-bottom:6px">💍</div>
          <div style="font-size:15px;font-weight:700;color:var(--bright)">${vipName(m.partner_name||'Партнёр', m.partner_is_vip)}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:3px">Вместе ${m.days} дней</div>
        </div>
        <div class="irow"><span class="ik">Семейный банк</span><span style="color:var(--gold);font-weight:700">${fmt(m.family_balance)} 🪙</span></div>
        <div style="display:flex;gap:7px;margin-top:10px">
          <input id="bank-amt" type="number" class="num-input" style="margin:0;flex:1" placeholder="Сумма 🪙" min="1"/>
          <button class="btn btn-sm btn-gold" onclick="familyBank('deposit')">📥 Вложить</button>
          <button class="btn btn-sm btn-ghost" onclick="familyBank('withdraw')">📤 Забрать</button>
        </div>
        ${pets.length?`<div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border2)">
          <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">🐾 Питомцы семьи (${pets.length})</div>
          ${pets.map(p=>`<div class="irow"><span class="ik">${p.name||p.species_id} ${rc(p.rarity)}</span><span class="iv">Lv${p.pet_level} · ${PL[p.placement]||p.placement}</span></div>`).join('')}
        </div>`:''}
        <div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border2)">
          <button class="btn btn-red btn-full" style="margin:0" onclick="confirmDivorce()">💔 Развестись</button>
        </div>
      </div>`;
    host._mid=m.marriage_id;
  }).catch(e=>{host.innerHTML=`<div class="card"><div class="err">${e}</div></div>`;});
}
function familyBank(action) {
  const v=parseFloat(el('bank-amt')?.value||0);
  if(!v||v<=0){toast('Введите сумму.',false);return;}
  const mid=el('pro-marriage-card')?._mid;
  if(!mid){toast('Нет данных о браке.',false);return;}
  api('/marriage/bank',{method:'POST',body:JSON.stringify({marriage_id:mid,amount:v,action})})
    .then(r=>{toast(`✅ ${r.message}`);refreshCurrBar();loadMarriageCard();})
    .catch(e=>toast(e,false));
}
function confirmDivorce() {
  OM('💔 Развод','<div style="text-align:center;padding:12px 0;color:var(--muted)">Вы уверены? Брак будет расторгнут <b style="color:var(--red)">безвозвратно</b>. Семейный банк будет разделён.</div>',[
    {l:'Да, развестись',c:'btn-red',f:'doDivorce()'},
    {l:'Отмена',c:'btn-ghost',f:'CM()'},
  ]);
}
function doDivorce() {
  api('/marriage/divorce',{method:'POST'})
    .then(()=>{toast('💔 Развод оформлен.');CM();loadMarriageCard();})
    .catch(e=>toast(e,false));
}
function acceptProposal(id,btn) {
  btn.disabled=true;
  api('/marriage/proposals/accept',{method:'POST',body:JSON.stringify({proposal_id:id})})
    .then(()=>{toast('💍 Брак заключён!');loadMarriageCard();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}
function declineProposal(id,btn) {
  btn.disabled=true;
  api('/marriage/proposals/decline',{method:'POST',body:JSON.stringify({proposal_id:id})})
    .then(()=>{toast('Предложение отклонено.');loadMarriageCard();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

// ── Wallet mini — свёрнутая история транзакций внизу дашборда Профиля ────────────
let _walletMiniExpanded = false;
let _walletMiniTxs = [];
function loadWalletMini() {
  const host = el('wallet-mini');
  if(!host) return;
  host.innerHTML='<div class="sk" style="height:44px;border-radius:var(--r)"></div>';
  api('/wallet/history').then(txs=>{
    _walletMiniTxs = txs;
    _walletMiniExpanded = false;
    _renderWalletMini();
  }).catch(()=>{ if(el('wallet-mini')) el('wallet-mini').innerHTML=''; });
}
function toggleWalletMini() { _walletMiniExpanded=!_walletMiniExpanded; _renderWalletMini(); }
function _renderWalletMini() {
  const host = el('wallet-mini');
  if(!host) return;
  if(!_walletMiniTxs.length){ host.innerHTML=''; return; }
  const show = _walletMiniExpanded ? _walletMiniTxs : _walletMiniTxs.slice(0,4);
  const fmtTx = t => {
    const mora = t.delta_mora?`<span style="color:${t.delta_mora>0?'var(--green)':'var(--red)'};font-weight:600">${t.delta_mora>0?'+':''}${fmt(t.delta_mora)} 🪙</span>`:'';
    const dia  = t.delta_diamonds?`<span style="color:${t.delta_diamonds>0?'var(--blue)':'var(--red)'};font-weight:600">${t.delta_diamonds>0?'+':''}${t.delta_diamonds} 💎</span>`:'';
    return `<div style="display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid var(--border2)">
      <div style="flex:1;min-width:0">
        <div style="font-size:12px;font-weight:600;color:var(--bright);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${t.label}</div>
        ${t.note?`<div style="font-size:10px;color:var(--muted)">${t.note}</div>`:''}
        <div style="font-size:10px;color:var(--muted)">${fmtUTC(t.created_at)}</div>
      </div>
      <div style="text-align:right;white-space:nowrap;flex-shrink:0">${[mora,dia].filter(Boolean).join(' ')}</div>
    </div>`;
  };
  host.innerHTML=`<div class="card">
    <div class="card-title">💳 История операций</div>
    ${show.map(fmtTx).join('')}
    ${_walletMiniTxs.length>4?`<button class="btn btn-ghost btn-sm btn-full" style="margin-top:6px" onclick="toggleWalletMini()">${_walletMiniExpanded?'▲ Свернуть':'▼ Показать все ('+_walletMiniTxs.length+')'}</button>`:''}
  </div>`;
}

// ── Daily Deal ────────────────────────────────────────────────────────────────
let _dealRefreshAt = null, _dealTimerInterval = null;
function loadDeal() {
  el('mkt-deal').innerHTML='<div class="loader">Загрузка...</div>';
  api('/daily-deal/').then(d=>{
    _dealRefreshAt = d.refreshes_at;
    const deals = d.deals||[];
    el('mkt-deal').innerHTML=`
      <div style="background:var(--gold-dim);border:1px solid var(--border);border-radius:var(--r);padding:10px;margin-bottom:12px;text-align:center">
        <div style="font-size:11px;color:var(--gold);text-transform:uppercase;letter-spacing:1px">Акция обновится через</div>
        <div id="deal-timer" style="font-size:20px;font-weight:700;color:var(--gold2);font-family:monospace">--:--:--</div>
      </div>
      <div class="balrow">
        <div class="bal"><div class="bv">🪙 ${fmt(d.mora)}</div><div class="bl">Мора</div></div>
        <div class="bal"><div class="bv">💎 ${d.diamonds.toFixed(1)}</div><div class="bl">Алмазы</div></div>
      </div>
      ${deals.length?'<div class="card"><div class="card-title">🏷 Предложения сегодня</div>'+
        deals.map(deal=>{
          const price=deal.price_mora?`${fmt(deal.price_mora)} 🪙`:deal.price_diamonds?`${deal.price_diamonds} 💎`:'—';
          const purchased=deal.purchased===true;
          return `<div class="shop-row">
            <div class="shop-icon">${(deal.item_name||'?').split(' ')[0]}</div>
            <div class="shop-info">
              <div class="shop-name">${deal.item_name||'?'} ${deal.quantity>1?'×'+deal.quantity:''}</div>
              <div class="shop-price">${price}</div>
              <div class="shop-desc">${deal.item_description||''}</div>
            </div>
            <button class="btn btn-sm ${purchased?'btn-ghost':'btn-gold'}" ${purchased?'disabled':''} onclick="buyDeal(${deal.slot},this)">
              ${purchased?'✓ Куплено':'Купить'}
            </button>
          </div>`;
        }).join('')+'</div>'
      :'<div class="loader">Акций нет.</div>'}`;
    startDealTimer();
  }).catch(e=>{el('mkt-deal').innerHTML=`<div class="err">${e}</div>`;});
}
function startDealTimer() {
  if(_dealTimerInterval) clearInterval(_dealTimerInterval);
  if(!_dealRefreshAt) return;
  const tick=()=>{
    const t=el('deal-timer');if(!t){clearInterval(_dealTimerInterval);return;}
    const diff=Math.max(0,Math.floor((new Date(_dealRefreshAt)-Date.now())/1000));
    if(diff<=0){t.textContent='Скоро обновится...';clearInterval(_dealTimerInterval);return;}
    const h=Math.floor(diff/3600),m=Math.floor((diff%3600)/60),s=diff%60;
    t.textContent=`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  };
  tick();
  _dealTimerInterval=setInterval(tick,1000);
}
function buyDeal(dealId,btn) {
  btn.disabled=true;
  btn.textContent='...';
  api('/daily-deal/buy',{method:'POST',body:JSON.stringify({deal_id:dealId})})
    .then(r=>{
      btn.textContent='✓ Куплено';
      btn.className='btn btn-ghost btn-sm';
      toast(`✅ Куплено +${r.qty}× предмет!`);
      refreshCurrBar();
    })
    .catch(e=>{toast(e,false);btn.disabled=false;btn.textContent='Купить';});
}

// ── Promo code (модалка из шапки Магазина) ────────────────────────────────────
function openPromoModal() {
  OM('🎫 Промокод', `
    <div style="font-size:12px;color:var(--muted);margin-bottom:10px;line-height:1.5">
      Введите промокод. Каждый код — одноразовый.<br>
      <span style="color:var(--gold);font-size:11px">💡 Коды публикуются в официальных чатах и анонсах бота.</span>
    </div>
    <input id="promo-input" type="text" class="num-input"
           placeholder="ПРОМОКОД" style="text-transform:uppercase;margin:0"
           oninput="this.value=this.value.toUpperCase()"/>
    <div id="promo-result" style="margin-top:8px"></div>
  `, [
    {l:'🎫 Активировать', c:'btn-gold', f:'redeemPromo(this)'},
    {l:'Закрыть', c:'btn-ghost', f:'CM()'},
  ]);
}
function redeemPromo(btn) {
  const code=el('promo-input')?.value?.trim();
  if(!code){toast('Введите промокод.',false);return;}
  btn.disabled=true;
  api('/promo/redeem',{method:'POST',body:JSON.stringify({code})})
    .then(r=>{
      el('promo-input').value='';
      const rw=r.reward||{};
      const rewards=[];
      if(rw.mora>0)    rewards.push(`<span style="color:var(--gold);font-size:22px;font-weight:800">+${fmt(rw.mora)} 🪙</span>`);
      if(rw.diamonds>0)rewards.push(`<span style="color:var(--blue);font-size:22px;font-weight:800">+${rw.diamonds} 💎</span>`);
      if(rw.dark_mora>0)rewards.push(`<span style="color:var(--muted);font-size:22px;font-weight:800">+${fmt(rw.dark_mora)} 🌑</span>`);
      if(rw.zarniki>0) rewards.push(`<span style="color:var(--bright);font-size:22px;font-weight:800">+${rw.zarniki} ✨</span>`);
      if(rw.items&&Object.keys(rw.items).length){
        for(const[id,q] of Object.entries(rw.items)) rewards.push(`<span style="font-size:16px">+${q}× ${id}</span>`);
      }
      const desc=rw.description?`<div style="font-size:11px;color:var(--muted);margin-top:6px">${rw.description}</div>`:'';
      el('promo-result').innerHTML=`
        <div style="background:var(--s);border:1px solid var(--border);border-radius:var(--r);padding:16px;text-align:center;animation:fadeIn .4s ease">
          <div style="font-size:24px;margin-bottom:6px">🎉</div>
          <div style="font-size:13px;font-weight:700;color:var(--green);margin-bottom:10px">Промокод активирован!</div>
          <div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-bottom:8px">${rewards.join('')}</div>
          ${desc}
          <div style="font-size:10px;color:var(--dim);margin-top:8px">Код: <code>${rw.code||code}</code></div>
        </div>`;
      refreshCurrBar();
    })
    .catch(e=>{
      el('promo-result').innerHTML=`<div class="err">${e}</div>`;
    })
    .finally(()=>{btn.disabled=false;});
}

// ── Exchange Zarniki → Mora/Diamonds (Implementation Block 1.3) ───────────────
function openExchangeZarnikiModal() {
  const zar = Math.floor(_profileData?.zarniki || 0);
  OM('🔄 Обмен Зарников', `
    <div style="font-size:12px;color:var(--muted);margin-bottom:10px;line-height:1.5">
      Баланс: <b style="color:var(--bright)">${zar} ✨</b><br>
      Курс: 1✨ = 3 🪙  ·  1✨ = 0.05 💎 (20✨ = 1💎)<br>
      <span style="color:var(--gold);font-size:11px">⚠️ Обмен необратим.</span>
    </div>
    <input id="exch-zar-amount" type="number" class="num-input" min="1" max="${zar}" step="1"
           placeholder="Сколько ✨ обменять" style="margin:0"/>
    <div style="display:flex;gap:8px;margin-top:8px">
      <button class="btn btn-sm btn-gold" style="flex:1" onclick="doExchangeZarniki('mora')">→ 🪙 Мора</button>
      <button class="btn btn-sm btn-gold" style="flex:1" onclick="doExchangeZarniki('diamonds')">→ 💎 Алмазы</button>
    </div>
    <div id="exch-zar-result" style="margin-top:8px"></div>
  `, [
    {l:'Закрыть', c:'btn-ghost', f:'CM()'},
  ]);
}
function doExchangeZarniki(to) {
  const amount = parseFloat(el('exch-zar-amount')?.value);
  if(!amount || amount<=0){ toast('Укажи количество ✨', false); return; }
  api('/wallet/exchange-zarniki', {method:'POST', body:JSON.stringify({amount, to})})
    .then(r=>{
      el('exch-zar-result').innerHTML = `<div style="color:var(--green);font-size:12px">${r.message}</div>`;
      loadProfile();
    })
    .catch(e=>{
      el('exch-zar-result').innerHTML = `<div class="err">${e}</div>`;
    });
}

// ── switchPro — Профиль: Обзор(дашборд+кошелёк) / Инвентарь / Темы ──────────────
// Брак и Ник — карточки в Обзоре. История кошелька — свёрнутая секция внизу Обзора.
function switchPro(tab, btn) {
  _proTab = tab;
  document.querySelectorAll('#pg-profile .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  ['main','inv','themes'].forEach(t=>el('pro-'+t).style.display=t===tab?'':'none');
  if(tab==='main') loadProfile();
  else if(tab==='inv') loadInventory();
  else if(tab==='themes') loadThemes();
}

// ── swMkt — Магазин: Премиум / Гача / Расходники / Акции дня ────────────────────
// Промокод — модалка (кнопка в шапке Магазина). Аукцион/Обмен → pg-auction, Крафт → pg-craft.
function swMkt(tab, _btn) {
  const btn = _btn || document.querySelector(`#pg-market .tb[onclick*="'${tab}'"]`) || document.querySelector('#pg-market .tb');
  _mktTab = tab;
  document.querySelectorAll('#pg-market .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const bd = el('balrow'); bd.style.display = tab === 'goods' ? 'flex' : 'none';
  ['vip','gacha','goods','deal'].forEach(t=>el(t==='goods'?'mkt-goods':'mkt-'+t).style.display=t===tab?'':'none');
  ({vip:loadVip, gacha:loadGacha, goods:loadMarketGoods, deal:loadDeal}[tab]||loadVip)();
}

// ── swGoods — Расходники: 🛒 Обычный (Магазин) / 🌑 Тёмный (Чёрный Рынок) ────────
let _goodsTab='shop';
function swGoods(sub, btn) {
  _goodsTab = sub;
  document.querySelectorAll('#mkt-goods .tabs .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  el('mkt-shop').style.display = sub==='shop' ? '' : 'none';
  el('mkt-dark').style.display = sub==='dark' ? '' : 'none';
  el('balrow').style.display='flex';
  if(sub==='shop') loadShopCatalog(); else loadDarkMora();
}
function loadMarketGoods() {
  swGoods(_goodsTab, document.querySelector(`#mkt-goods .tabs .tb[onclick*="'${_goodsTab}'"]`));
}
// Шорткат "Чёрный Рынок" из карточек предметов — открыть Расходники сразу на Тёмном
function goToDarkMora() { _goodsTab='dark'; goTo('market','goods'); }

// ── swAuction — Аукцион & Обменник ──────────────────────────────────────────────
let _aucTab='auc';
function swAuction(tab, btn) {
  _aucTab = tab;
  document.querySelectorAll('#pg-auction .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  el('mkt-auc').style.display = tab==='auc' ? '' : 'none';
  el('mkt-exch').style.display = tab==='exch' ? '' : 'none';
  if(tab==='auc') loadAuction(1); else loadExchange();
}
function loadAuctionPage() { swAuction(_aucTab, document.querySelector(`#pg-auction .tb[onclick*="'${_aucTab}'"]`)); }

// ── swQuests — Квесты & Стрик ───────────────────────────────────────────────────
let _questsTab='quests';
function swQuests(tab, btn) {
  _questsTab = tab;
  document.querySelectorAll('#pg-quests .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  el('pro-quests').style.display = tab==='quests' ? '' : 'none';
  el('pro-streak').style.display = tab==='streak' ? '' : 'none';
  if(tab==='quests') loadQuests(); else loadStreak();
}
function loadQuestsPage() { swQuests(_questsTab, document.querySelector(`#pg-quests .tb[onclick*="'${_questsTab}'"]`)); }

// ── Auto-refresh ──────────────────────────────────────────────────────────────
setInterval(()=>{if(_loaded.has('profile'))loadProfile();},300000);
setInterval(()=>{if(_loaded.has('zoo'))api('/zoo/expeditions').then(d=>renderExps(d)).catch(()=>{});},30000);

// ── Dust modal ────────────────────────────────────────────────────────────────
function _showDustModal(did) {
  if(!_zooData?.pets?.length){toast('У вас нет питомцев.',false);return;}
  const dusts={'star_dust_s':'+1 дубл.','star_dust_l':'+5 дубл.'};
  OM('✨ Применить '+dusts[did],
    _zooData.pets.map(p=>`<div class="fopt" onclick="doApplyDust('${did}',${p.id},this)">
      <span class="fn">${p.name||p.species_id}</span>
      <span style="font-size:11px;color:var(--muted)">${rc(p.rarity)} Lv${p.pet_level||1} · ${p.placement==='storage'?'📦':p.placement==='active'?'⚔️':'🛡'}</span>
    </div>`).join(''),
    [{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}

// ── Pet modal: applicable items section ───────────────────────────────────────
function renderPetItems(petId, petData) {
  const dustItems = (_invData||[]).filter(i=>i.item_id.startsWith('star_dust') && i.quantity>0);
  if(!dustItems.length) return '';
  return `<div class="card-title" style="margin-top:14px">📦 Применить предмет</div>
    ${dustItems.map(i=>`<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border2)">
      <div>
        <span style="font-size:13px;font-weight:600">${i.name}</span>
        <span style="font-size:10px;color:var(--muted);margin-left:6px">×${i.quantity}</span>
      </div>
      <button class="btn btn-sm btn-gold" onclick="doApplyDustFromPetModal('${i.item_id}',${petId},this)">Применить</button>
    </div>`).join('')}`;
}
function doApplyDustFromPetModal(did,pid,btn) {
  btn.disabled=true;
  api('/inventory/apply-dust',{method:'POST',body:JSON.stringify({dust_id:did,pet_id:pid})})
    .then(r=>{toast(`✅ +${r.duplicates_added} дубл. добавлено!`);CM();_zooData=null;loadInventory();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}

// ── Profile Settings ──────────────────────────────────────────────────────────
// ── Nickname card (в дашборде Обзор) ──────────────────────────────────────────
// Рендерит в #pro-nick-card. Без активного чата карточка просто не показывается.
function loadNickCard() {
  const c=el('pro-nick-card');
  if(!c) return;
  // Prefer the chat mini-app was opened from (_initChatId); fall back to first chat from API
  const chatId=_initChatId||_cid||0;
  if(!chatId){ c.innerHTML=''; return; }
  api(`/profile/nickname?chat_id=${chatId}`).then(r=>{
    const nick=(r.nickname||'').replace(/"/g,'&quot;');
    c.innerHTML=`<div class="card">
      <div class="card-title">🏷 Ник в чате</div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:8px">Отображается вместо @username в статистике чата</div>
      <div style="display:flex;gap:8px;align-items:center">
        <input id="nick-inp" type="text" class="num-input" style="flex:1;margin:0"
               value="${nick}" placeholder="Ваш ник" maxlength="32"/>
        <button class="btn btn-sm btn-gold" onclick="saveNick()">Сохранить</button>
      </div>
      <div id="nick-status" style="font-size:11px;margin-top:6px;color:var(--muted)">1–32 символа, буквы/цифры/пробел/- .</div>
    </div>`;
  }).catch(()=>{c.innerHTML='';});
}
function saveNick() {
  const v=(el('nick-inp')?.value||'').trim();
  if(!v){toast('Введите ник.',false);return;}
  if(v.length>32){toast('Ник слишком длинный.',false);return;}
  el('nick-status').textContent='Сохраняем...';
  api('/profile/set-nickname',{method:'POST',body:JSON.stringify({chat_id:_initChatId||_cid,nickname:v})})
    .then(r=>{
      el('nick-status').textContent=`✅ Ник установлен: ${r.nickname}`;
      el('nick-status').style.color='var(--green)';
    })
    .catch(e=>{
      el('nick-status').textContent='❌ '+e;
      el('nick-status').style.color='var(--red)';
    });
}

// ── Events ────────────────────────────────────────────────────────────────────
function loadEvents() {
  el('evc').innerHTML='<div class="loader">Загрузка...</div>';
  api('/events/').then(ev=>{
    let html='';

    // Exchange event
    if(ev.exchange_active) {
      const ea=ev.exchange_active;
      const ends=ea.ends_at?new Date(ea.ends_at):null;
      const msLeft=ends?Math.max(0,ends-Date.now()):0;
      html+=`<div class="card card-gold">
        <div class="card-title">💱 Обмен Мора → Алмазы <span style="color:var(--green);text-transform:none">АКТИВЕН</span></div>
        <div class="irow"><span class="ik">Курс</span><span>${fmt(ev.exchange_rate)} 🪙 = 1 💎</span></div>
        <div class="irow"><span class="ik">Лимит</span><span>${fmt(ev.exchange_cap)} 💎/день</span></div>
        ${msLeft>0?`<div class="irow"><span class="ik">До конца</span><span style="color:var(--gold)">${fmtTime(msLeft)}</span></div>`:''}
        <button class="btn btn-sm btn-gold" style="margin-top:8px;width:100%" onclick="goTo('auction','exch')">Перейти к обмену</button>
      </div>`;
    } else if(ev.exchange_next) {
      const en=ev.exchange_next;
      const starts=en.starts_at?new Date(en.starts_at):null;
      const startsStr=starts?starts.toLocaleString('ru-RU'):'-';
      html+=`<div class="card">
        <div class="card-title">💱 Следующий обмен</div>
        <div class="irow"><span class="ik">Начало</span><span>${startsStr}</span></div>
        <div class="irow"><span class="ik">Курс</span><span>${fmt(ev.exchange_rate)} 🪙 = 1 💎</span></div>
      </div>`;
    } else {
      html+=`<div class="card"><div class="card-title">💱 Обмен</div>
        <div style="color:var(--muted);font-size:12px">Ивент скоро будет запланирован. Заходите позже!</div>
      </div>`;
    }

    // Daily deals
    if(ev.daily_deals?.length) {
      html+=`<div class="card">
        <div class="card-title">🏷 Акция дня</div>
        ${ev.daily_deals.map(d=>`<div class="irow">
          <span class="ik">${d.name}${d.qty>1?` ×${d.qty}`:''}</span>
          <span>
            <span style="color:var(--gold);font-weight:700">${fmt(d.price)} 🪙</span>
            ${d.original&&d.original>d.price?`<s style="color:var(--muted);font-size:10px;margin-left:4px">${fmt(d.original)}</s>`:''}
          </span>
        </div>`).join('')}
        <button class="btn btn-sm btn-teal" style="margin-top:8px;width:100%" onclick="goTo('market','deal')">К акции дня</button>
      </div>`;
    }

    // Gacha overview — show egg types with rates
    if(ev.gacha_types?.length) {
      const withRates=ev.gacha_types.filter(g=>g.rates&&Object.keys(g.rates).length>0);
      if(withRates.length) {
        html+=`<div class="card">
          <div class="card-title">🥚 Яйца — шансы редкостей</div>
          ${withRates.slice(0,5).map(g=>`<div style="margin-bottom:8px">
            <div style="font-size:11px;font-weight:600;margin-bottom:3px;color:var(--muted)">${g.label}</div>
            <div style="display:flex;flex-wrap:wrap;gap:3px">
              ${Object.entries(g.rates).map(([r,v])=>`<span class="${RC[r]||'rc-common'}" style="font-size:10px;padding:1px 5px">${r} ${v}%</span>`).join('')}
            </div>
          </div>`).join('')}
          <button class="btn btn-sm btn-gold" style="margin-top:4px;width:100%" onclick="goTo('market','gacha')">К крутке</button>
        </div>`;
      }
    }

    el('evc').innerHTML=html||'<div class="card" style="text-align:center;padding:20px;color:var(--muted)">Нет активных ивентов.</div>';
  }).catch(e=>{el('evc').innerHTML=`<div class="err">${e}</div>`;});
}
// Nav helpers for events page (avoids complex inline onclick in template literals)
// nav-хелперы заменены на единый goTo()
function fmtTime(ms) {
  const s=Math.floor(ms/1000),h=Math.floor(s/3600),m=Math.floor((s%3600)/60);
  if(h>24) return `${Math.floor(h/24)}д ${h%24}ч`;
  return `${h}ч ${m}м`;
}

// ── Species data (общий кэш для Бестиария) ────────────────────────────────────
// Витрина переехала в Зоопарк → Бестиарий (_renderBestiary). Здесь только кэш
// видов и модалка деталей вида, которую вызывает Бестиарий.
let _showcaseData=null;
function showSpeciesDetail(sid) {
  const p=(_showcaseData||[]).find(x=>x.species_id===sid);
  if(!p) return;
  const tiers=p.bonus_tiers||{};
  let bonusHtml='';
  for(const [lv,b] of Object.entries(tiers)){
    const lines=bonusLines(sid,b);
    if(lines.length) bonusHtml+=`<div style="margin-bottom:8px"><div style="font-size:10px;color:var(--gold);font-weight:600;margin-bottom:3px">Уровень ${lv}</div>${lines.map(l=>`<div style="font-size:11px;color:var(--text)">• ${l}</div>`).join('')}</div>`;
  }
  OM(p.name,`<div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:10px">${p.desc||''}</div>
    <div class="irow"><span class="ik">Редкость</span><span class="${RC[p.rarity]}">${p.rarity}</span></div>
    <div class="irow"><span class="ik">Роль</span><span>${p.role==='active'?'⚔️ Активный':'🛡 Пассивный'}</span></div>
    <div style="margin-top:10px">${bonusHtml||'<div style="color:var(--muted);font-size:11px">Нет данных о бонусах</div>'}</div>
  </div>`,[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}

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
      ${_adminChats.map(c=>`<option value="${c.chat_tg_id}" ${c.chat_tg_id==_adminChatId?'selected':''}>${roleIcon(c)} ${c.chat_title} · ${_RANK_NAMES[c.local_rank]||c.local_rank}</option>`).join('')}
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
  const loaders = {
    profile:loadProfile, zoo:()=>{_zooData=null;loadZoo();}, arena:loadArena, market:loadMarket,
    quests:loadQuestsPage, bp:loadBattlePass, ach:loadAch, bestiary:renderZooGuide,
    craft:loadCraft, auction:loadAuctionPage, hof:loadTop,
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

// ── 🛠 Консоль разработчика (только DEVELOPER_ID, global_rank=3) ──────────────────
let _devItems=null;
function loadGlobalDev() {
  el('glb-dev').innerHTML=`
    <div id="dev-overview"><div class="loader">Загрузка...</div></div>
    <div class="card">
      <div class="card-title">🔎 Досье на игрока</div>
      <div style="display:flex;gap:6px">
        <input id="dev-q" type="text" class="num-input" style="flex:1;margin:0" placeholder="ID или @username"/>
        <button class="btn btn-gold" onclick="devLookupUser()">Найти</button>
      </div>
      <div id="dev-user-result"></div>
    </div>
    <div class="card">
      <div class="card-title">💰 Баланс (+/−)</div>
      <input id="dev-bal-uid" type="number" class="num-input" style="margin-bottom:6px" placeholder="ID пользователя"/>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <select id="dev-bal-cur" class="num-input" style="flex:1;margin:0">
          <option value="mora">🪙 Мора</option>
          <option value="diamonds">💎 Алмазы</option>
          <option value="dark_mora">🌑 Тёмная мора</option>
          <option value="zarniki">✨ Зарники</option>
        </select>
        <input id="dev-bal-amt" type="number" step="any" class="num-input" style="flex:1;margin:0" placeholder="Сумма (− забрать)"/>
      </div>
      <button class="btn btn-gold btn-full" onclick="devAdjustBalance()">Применить</button>
    </div>
    <div class="card">
      <div class="card-title">🎁 Выдать предмет (− забрать)</div>
      <input id="dev-item-uid" type="number" class="num-input" style="margin-bottom:6px" placeholder="ID пользователя"/>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-item-id" list="dev-items-dl" class="num-input" style="flex:1.6;margin:0" placeholder="item_id"/>
        <datalist id="dev-items-dl"></datalist>
        <input id="dev-item-qty" type="number" class="num-input" style="flex:1;margin:0" placeholder="Кол-во" value="1"/>
      </div>
      <button class="btn btn-gold btn-full" onclick="devGiveItem()">Применить</button>
    </div>
    <div class="card">
      <div class="card-title">👑 Выдать VIP (бесплатно)</div>
      <input id="dev-vip-uid" type="number" class="num-input" style="margin-bottom:6px" placeholder="ID пользователя"/>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <select id="dev-vip-tier" class="num-input" style="flex:1;margin:0">
          <option value="1m">VIP-1М</option><option value="3m">VIP-3М</option>
          <option value="8m">VIP-8М</option><option value="12m">VIP-12М</option>
        </select>
        <input id="dev-vip-days" type="number" class="num-input" style="flex:1;margin:0" placeholder="Дней" value="30"/>
      </div>
      <button class="btn btn-gold btn-full" onclick="devGiveVip()">Выдать</button>
    </div>
    <div class="card">
      <div class="card-title">🎫 Боевой пропуск — сезоны</div>
      <div id="dev-seasons"><div class="loader">Загрузка...</div></div>
      <div style="display:flex;gap:6px;margin:8px 0 6px">
        <input id="dev-s-id" type="text" class="num-input" style="flex:1;margin:0" placeholder="id (s2)"/>
        <input id="dev-s-label" type="text" class="num-input" style="flex:1.4;margin:0" placeholder="Название"/>
      </div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <input id="dev-s-start" type="date" class="num-input" style="flex:1;margin:0"/>
        <input id="dev-s-end" type="date" class="num-input" style="flex:1;margin:0"/>
      </div>
      <button class="btn btn-gold btn-full" onclick="devSaveSeason()">💾 Создать/обновить сезон</button>
      <div style="font-size:10px;color:var(--muted);margin-top:4px">id из registry (s1) можно перекрыть, создав БД-сезон с тем же id. Награды уровней общие для всех сезонов.</div>
      <div class="divider"></div>
      <div class="card-title" style="margin-top:4px">⚡ Начислить BP XP</div>
      <div style="display:flex;gap:6px">
        <input id="dev-bp-uid" type="number" class="num-input" style="flex:1.4;margin:0" placeholder="ID пользователя"/>
        <input id="dev-bp-xp" type="number" class="num-input" style="flex:1;margin:0" placeholder="XP (− снять)"/>
        <button class="btn btn-gold" onclick="devBpXp()">OK</button>
      </div>
    </div>
    <div class="card">
      <div class="card-title">📢 Рассылка по всем чатам</div>
      <textarea id="dev-bc-text" class="num-input" style="margin:0 0 6px;min-height:70px;resize:vertical" placeholder="Текст (HTML разрешён)"></textarea>
      <button class="btn btn-red btn-full" onclick="devBroadcast()">📢 Отправить во ВСЕ чаты</button>
    </div>
    <div class="card">
      <div class="card-title">🎨 Theme Lab — редактор премиум-тем</div>
      <select id="dev-tl-template" class="num-input" style="margin-bottom:6px" onchange="devTLLoad()"></select>
      <div id="dev-tl-vars" style="font-size:10px;color:var(--muted);margin-bottom:6px"></div>
      <textarea id="dev-tl-text" class="num-input" style="margin:0 0 6px;min-height:180px;resize:vertical;font-family:monospace;font-size:11px;white-space:pre"></textarea>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <button class="btn btn-ghost" style="flex:1" onclick="devTLPreview()">👁 Превью</button>
        <button class="btn btn-gold" style="flex:1" onclick="devTLSave()">💾 Сохранить</button>
        <button class="btn btn-red" style="flex:1" onclick="devTLReset()">↩️ Сброс</button>
      </div>
      <div id="dev-tl-status" style="font-size:10px;margin-bottom:6px"></div>
      <div id="dev-tl-preview"></div>
    </div>
    <div class="card">
      <div class="card-title">🖥 SQL-консоль</div>
      <textarea id="dev-sql" class="num-input" style="margin:0 0 6px;min-height:70px;resize:vertical;font-family:monospace;font-size:11px" placeholder="SELECT * FROM users LIMIT 5"></textarea>
      <button class="btn btn-red btn-full" onclick="devRunSql()">▶ Выполнить</button>
      <div id="dev-sql-result" style="overflow-x:auto;margin-top:6px"></div>
    </div>`;
  devLoadOverview();
  devLoadSeasons();
  devTLInit();
  if(!_devItems) api('/admin/dev/items').then(d=>{
    _devItems=d.items||[];
    const dl=el('dev-items-dl');
    if(dl) dl.innerHTML=_devItems.map(i=>`<option value="${i.item_id}">${esc(i.name)}</option>`).join('');
  }).catch(()=>{});
  else { const dl=el('dev-items-dl'); if(dl) dl.innerHTML=_devItems.map(i=>`<option value="${i.item_id}">${esc(i.name)}</option>`).join(''); }
}
function devLoadOverview() {
  api('/admin/dev/overview').then(d=>{
    el('dev-overview').innerHTML=`<div class="card">
      <div class="card-title">📊 Система <button class="btn btn-sm btn-ghost" style="float:right;padding:2px 8px" onclick="devLoadOverview()">🔄</button></div>
      <div class="irow"><span class="ik">Игроков / Чатов</span><span class="iv">${d.users_total} / ${d.chats_total}</span></div>
      <div class="irow"><span class="ik">Сообщений сегодня</span><span class="iv">${d.messages_today}</span></div>
      <div class="irow"><span class="ik">Активных VIP</span><span class="iv">👑 ${d.vips_active}</span></div>
      <div class="irow"><span class="ik">Санкции / Апелляции</span><span class="iv">${d.sanctions_active} / ⏳${d.appeals_pending}</span></div>
      <div class="irow"><span class="ik">Всего 🪙/💎/✨ в экономике</span><span class="iv" style="font-size:10px">${fmt(Math.round(d.mora_total))} / ${fmt(Math.round(d.diamonds_total))} / ${fmt(Math.round(d.zarniki_total))}</span></div>
      <div class="irow"><span class="ik">Сезон БП</span><span class="iv">${d.bp_season?esc(d.bp_season.label)+' (до '+d.bp_season.ends_at+')':'— нет активного'}</span></div>
    </div>`;
  }).catch(e=>{el('dev-overview').innerHTML=`<div class="err">${e}</div>`;});
}
function devLookupUser() {
  const q=el('dev-q')?.value.trim();
  if(!q) return toast('Введите ID или @username',false);
  el('dev-user-result').innerHTML='<div class="loader">Поиск...</div>';
  api(`/admin/dev/user?q=${encodeURIComponent(q)}`).then(d=>{
    el('dev-user-result').innerHTML=`
      <div class="divider"></div>
      <div class="irow"><span class="ik">@${esc(d.user_tg_username||'—')}</span><span class="iv">ID: ${d.user_tg_id}</span></div>
      <div class="irow"><span class="ik">Глоб. ранг</span><span class="iv">${d.global_rank_name}</span></div>
      <div class="irow"><span class="ik">Балансы</span><span class="iv" style="font-size:10px">🪙${fmt(Math.round(d.mora))} 💎${d.diamonds.toFixed(1)} 🌑${Math.round(d.dark_mora)} ✨${Math.round(d.zarniki)}</span></div>
      <div class="irow"><span class="ik">VIP</span><span class="iv" style="font-size:10px">${d.vip?(d.vip.active?'👑 ':'(истёк) ')+d.vip.tier+' до '+d.vip.expires_at.slice(0,10)+' · стаж '+d.vip.total_days+' дн.':'—'}</span></div>
      <div class="irow"><span class="ik">Боевой пропуск</span><span class="iv">${d.battle_pass?`Ур.${d.battle_pass.level} (${d.battle_pass.xp} XP)`:'—'}</span></div>
      ${d.sanctions.length?`<div class="irow"><span class="ik" style="color:var(--red)">Санкции</span><span class="iv" style="font-size:10px">${d.sanctions.map(s=>s.sanction_type+(s.expires_at?' до '+s.expires_at.slice(0,10):'')).join(', ')}</span></div>`:''}
      <div style="font-size:11px;font-weight:700;margin:6px 0 2px">Чаты (${d.chats.length}):</div>
      ${d.chats.slice(0,10).map(c=>`<div class="irow"><span class="ik" style="font-size:10px">${esc(c.chat_title)}</span><span class="iv" style="font-size:10px">${c.rank_name} · ур.${c.user_level||1} · ${c.user_messages_count_all_time||0} сообщ.${c.is_left?' · 👋':''}</span></div>`).join('')}
      <div style="display:flex;gap:6px;margin-top:8px">
        <button class="btn btn-sm btn-ghost" style="flex:1" onclick="devPrefill(${d.user_tg_id})">⚙️ Подставить ID в формы</button>
      </div>`;
  }).catch(e=>{el('dev-user-result').innerHTML=`<div class="err">${e}</div>`;});
}
function devPrefill(uid) {
  ['dev-bal-uid','dev-item-uid','dev-vip-uid','dev-bp-uid'].forEach(id=>{const e2=el(id);if(e2)e2.value=uid;});
  toast('ID подставлен в формы');
}
function devAdjustBalance() {
  const uid=parseInt(el('dev-bal-uid')?.value||'0');
  const cur=el('dev-bal-cur')?.value;
  const amt=parseFloat(el('dev-bal-amt')?.value||'0');
  if(!uid||!amt) return toast('Заполните ID и сумму',false);
  const body={user_id:uid,mora:0,diamonds:0,dark_mora:0,zarniki:0};
  body[cur]=amt;
  api('/admin/dev/balance',{method:'POST',body:JSON.stringify(body)})
    .then(()=>toast(`✅ ${amt>0?'+':''}${amt} ${cur} → ID${uid}`))
    .catch(e=>toast(e,false));
}
function devGiveItem() {
  const uid=parseInt(el('dev-item-uid')?.value||'0');
  const item=el('dev-item-id')?.value.trim();
  const qty=parseInt(el('dev-item-qty')?.value||'0');
  if(!uid||!item||!qty) return toast('Заполните все поля',false);
  api('/admin/dev/give-item',{method:'POST',body:JSON.stringify({user_id:uid,item_id:item,qty})})
    .then(r=>toast(`✅ ${qty>0?'+':''}${qty}× ${r.item_name}`))
    .catch(e=>toast(e,false));
}
function devGiveVip() {
  const uid=parseInt(el('dev-vip-uid')?.value||'0');
  const tier=el('dev-vip-tier')?.value;
  const days=parseInt(el('dev-vip-days')?.value||'0');
  if(!uid||!days) return toast('Заполните ID и дни',false);
  api('/admin/dev/give-vip',{method:'POST',body:JSON.stringify({user_id:uid,tier,days})})
    .then(r=>toast(`👑 ${r.label} на ${days} дн. → ID${uid}`))
    .catch(e=>toast(e,false));
}
function devBpXp() {
  const uid=parseInt(el('dev-bp-uid')?.value||'0');
  const xp=parseInt(el('dev-bp-xp')?.value||'0');
  if(!uid||!xp) return toast('Заполните ID и XP',false);
  api('/admin/dev/bp/xp',{method:'POST',body:JSON.stringify({user_id:uid,xp})})
    .then(r=>toast(`🎫 Теперь: Ур.${r.level} (${r.xp} XP)`))
    .catch(e=>toast(e,false));
}
function devLoadSeasons() {
  api('/admin/dev/bp/seasons').then(d=>{
    const rows=d.seasons||[];
    el('dev-seasons').innerHTML=rows.length?rows.map(s=>`
      <div class="irow">
        <span class="ik">${s.active?'🟢 ':''}${esc(s.label)} <span style="color:var(--dim)">(${s.id}, ${s.source})</span></span>
        <span class="iv" style="font-size:10px;display:flex;align-items:center;gap:6px">${s.starts_at} → ${s.ends_at}
          <button class="btn btn-sm btn-ghost" style="padding:2px 6px" onclick='devEditSeason(${JSON.stringify(s.id)},${JSON.stringify(s.label)},${JSON.stringify(s.starts_at)},${JSON.stringify(s.ends_at)})'>✏️</button>
          ${s.source==='db'?`<button class="btn btn-sm btn-ghost" style="padding:2px 6px" onclick='devDeleteSeason(${JSON.stringify(s.id)})'>🗑</button>`:''}
        </span>
      </div>`).join(''):'<div style="font-size:11px;color:var(--muted)">Сезонов нет</div>';
  }).catch(e=>{el('dev-seasons').innerHTML=`<div class="err">${e}</div>`;});
}
function devEditSeason(id,label,starts,ends) {
  el('dev-s-id').value=id; el('dev-s-label').value=label;
  el('dev-s-start').value=starts; el('dev-s-end').value=ends;
  toast('Сезон подставлен в форму — правьте и сохраняйте');
}
function devSaveSeason() {
  const id=el('dev-s-id')?.value.trim(), label=el('dev-s-label')?.value.trim();
  const starts=el('dev-s-start')?.value, ends=el('dev-s-end')?.value;
  if(!id||!label||!starts||!ends) return toast('Заполните все поля сезона',false);
  api('/admin/dev/bp/seasons',{method:'POST',body:JSON.stringify({id,label,starts_at:starts,ends_at:ends})})
    .then(()=>{toast('💾 Сезон сохранён');devLoadSeasons();})
    .catch(e=>toast(e,false));
}
function devDeleteSeason(id) {
  OM('🗑 Удалить сезон?',`<div style="text-align:center;padding:12px 0;color:var(--muted)">Сезон <b>${id}</b> будет удалён из БД. Прогресс игроков сохранится в battle_pass_progress.</div>`,
    [{l:'Удалить',c:'btn-red',f:`_execDevDeleteSeason(${JSON.stringify(id)})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execDevDeleteSeason(id) {
  api(`/admin/dev/bp/seasons/${encodeURIComponent(id)}`,{method:'DELETE'})
    .then(()=>{toast('🗑 Удалён');CM();devLoadSeasons();})
    .catch(e=>toast(e,false));
}
function devBroadcast() {
  const text=el('dev-bc-text')?.value.trim();
  if(!text) return toast('Введите текст',false);
  OM('📢 Рассылка во ВСЕ чаты?','<div style="text-align:center;padding:12px 0;color:var(--muted)">Сообщение уйдёт в каждый чат, где есть бот. Отменить нельзя.</div>',
    [{l:'Да, отправить',c:'btn-red',f:'_execDevBroadcast()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execDevBroadcast() {
  const text=el('dev-bc-text')?.value.trim();
  CM(); toast('📢 Отправляю...');
  api('/admin/dev/broadcast',{method:'POST',body:JSON.stringify({text})})
    .then(r=>toast(`📢 Отправлено: ${r.sent}/${r.total}${r.failed?' (ошибок: '+r.failed+')':''}`))
    .catch(e=>toast(e,false));
}
function devRunSql() {
  const q=el('dev-sql')?.value.trim();
  if(!q) return toast('Введите запрос',false);
  OM('🖥 Выполнить SQL?',`<div style="font-family:monospace;font-size:11px;padding:8px;background:var(--dim);border-radius:6px;word-break:break-all">${esc(q.slice(0,300))}</div>`,
    [{l:'Выполнить',c:'btn-red',f:'_execDevSql()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execDevSql() {
  const q=el('dev-sql')?.value.trim();
  CM();
  api('/admin/dev/sql',{method:'POST',body:JSON.stringify({query:q})}).then(r=>{
    if(!r.rows||!r.rows.length){
      el('dev-sql-result').innerHTML=`<div style="font-size:11px;color:var(--green)">✅ OK${r.count?` (строк: ${r.count})`:''}</div>`;
      return;
    }
    const cols=Object.keys(r.rows[0]);
    el('dev-sql-result').innerHTML=`
      <div style="font-size:10px;color:var(--muted);margin-bottom:4px">Строк: ${r.count}${r.truncated?' (показаны первые 200)':''}</div>
      <table class="adm-table"><thead><tr>${cols.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead>
      <tbody>${r.rows.map(row=>`<tr>${cols.map(c=>`<td style="font-size:10px">${esc(row[c]??'∅')}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  }).catch(e=>{el('dev-sql-result').innerHTML=`<div class="err">${e}</div>`;});
}

// ── 🎨 Theme Lab — кастомные raw-шаблоны премиум-тем (правки без деплоя) ──────────
let _devThemeTemplates=null;
function devTLInit() {
  api('/admin/dev/theme-templates').then(d=>{
    _devThemeTemplates=d.templates||[];
    const sel=el('dev-tl-template');
    if(!sel) return;
    sel.innerHTML=_devThemeTemplates.map(t=>`<option value="${t.template_id}">${esc(t.name)}${t.has_override?' ✏️':''}</option>`).join('');
    if(_devThemeTemplates.length) devTLLoad();
  }).catch(e=>{el('dev-tl-status').innerHTML=`<div class="err">${e}</div>`;});
}
function _devTLRefreshBadges() {
  const sel=el('dev-tl-template'); const cur=sel?.value;
  api('/admin/dev/theme-templates').then(d=>{
    _devThemeTemplates=d.templates||[];
    if(!sel) return;
    sel.innerHTML=_devThemeTemplates.map(t=>`<option value="${t.template_id}">${esc(t.name)}${t.has_override?' ✏️':''}</option>`).join('');
    sel.value=cur;
  }).catch(()=>{});
}
function devTLLoad() {
  const tid=el('dev-tl-template')?.value;
  if(!tid) return;
  el('dev-tl-status').textContent='Загрузка...';
  el('dev-tl-preview').innerHTML='';
  api(`/admin/dev/theme-templates/${tid}`).then(d=>{
    el('dev-tl-text').value=d.raw_text;
    el('dev-tl-vars').innerHTML='Переменные: '+d.variables.map(v=>`<code>{${v}}</code>`).join(' ');
    el('dev-tl-status').innerHTML=d.has_override
      ?'<span style="color:var(--gold)">✏️ Сохранён кастомный вариант</span>'
      :'<span style="color:var(--muted)">Дефолтный шаблон (из кода)</span>';
  }).catch(e=>{el('dev-tl-status').innerHTML=`<div class="err">${e}</div>`;});
}
function devTLPreview() {
  const tid=el('dev-tl-template')?.value;
  const text=el('dev-tl-text')?.value??'';
  if(!tid) return;
  el('dev-tl-preview').innerHTML='<div class="loader">Рендерю...</div>';
  api(`/admin/dev/theme-templates/${tid}/preview`,{method:'POST',body:JSON.stringify({raw_text:text})})
    .then(r=>{ el('dev-tl-preview').innerHTML=`<div class="profile-preview">${r.text}</div>`; })
    .catch(e=>{ el('dev-tl-preview').innerHTML=`<div class="err">${e}</div>`; });
}
function devTLSave() {
  const tid=el('dev-tl-template')?.value;
  const text=el('dev-tl-text')?.value??'';
  if(!tid||!text.trim()) return toast('Пустой шаблон',false);
  api(`/admin/dev/theme-templates/${tid}`,{method:'POST',body:JSON.stringify({raw_text:text})})
    .then(()=>{
      toast('💾 Сохранено — применяется сразу, без деплоя');
      el('dev-tl-status').innerHTML='<span style="color:var(--gold)">✏️ Сохранён кастомный вариант</span>';
      _devTLRefreshBadges();
      devTLPreview();
    })
    .catch(e=>toast(e,false));
}
function devTLReset() {
  const tid=el('dev-tl-template')?.value;
  if(!tid) return;
  OM('↩️ Сбросить шаблон?','<div style="text-align:center;padding:12px 0;color:var(--muted)">Кастомный вариант будет удалён, тема вернётся к версии из кода.</div>',
    [{l:'Сбросить',c:'btn-red',f:`_execDevTLReset(${JSON.stringify(tid)})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execDevTLReset(tid) {
  CM();
  api(`/admin/dev/theme-templates/${tid}`,{method:'DELETE'})
    .then(()=>{toast('↩️ Сброшено');devTLLoad();_devTLRefreshBadges();})
    .catch(e=>toast(e,false));
}

// ── Init global moderation check after login ──────────────────────────────────────
function checkGlobalAccess() {
  const rank=_profileData?.global_rank||0;
  if(rank>=1) {
    const tr=el('glb-tab-ranks'); if(tr) tr.style.display=rank>=3?'':'none';
    const td=el('glb-tab-dev'); if(td) td.style.display=rank>=3?'':'none';
  }
  _updateMoreCard();
}
