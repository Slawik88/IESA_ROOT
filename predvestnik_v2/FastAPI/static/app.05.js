// ── ✨ Активные баффы игрока (player_buffs) — «что действует сейчас» в профиле ──
function loadActiveBuffs() {
  const host=el('pro-buffs');
  if(!host) return;
  api('/inventory/buffs').then(r=>{
    const buffs=r.buffs||[];
    if(!buffs.length){host.innerHTML='';return;}
    const rows=buffs.map(b=>{
      let right;
      if(b.mode==='time'&&b.expires_at){
        const t=new Date(b.expires_at.replace(' ','T').split('.')[0]+'Z').getTime();
        const mins=isNaN(t)?null:Math.max(0,Math.round((t-Date.now())/60000));
        right=(mins==null)?`<span style="color:var(--teal)">активно</span>`
          :`<span style="color:var(--teal)">${Math.floor(mins/60)?Math.floor(mins/60)+'ч ':''}${mins%60}м</span>`;
      } else {
        right=`<span style="color:var(--teal)">×${b.uses_left||1}</span>`;
      }
      const val=b.value?` <span style="color:var(--gold);font-size:10px">+${Math.round(b.value*100)}%</span>`:'';
      return `<div class="irow"><span class="ik">${b.icon} ${esc(b.label)}${val}</span>${right}</div>`;
    }).join('');
    host.innerHTML=`<div class="card"><div class="card-title">✨ Активные баффы</div>${rows}</div>`;
  }).catch(()=>{host.innerHTML='';});
}
// doOpenEgg УДАЛЁН (БЛОК19 Ч.2): открытие яиц вырезано, питомцы — только через Гачу.
function openFeedSelModal(fid) {
  if(!_zooData){toast('Зайдите в Зоопарк.',false);return;}
  const pets=_zooData.pets.filter(p=>p.placement!=='storage');
  if(!pets.length){toast('Нет питомцев.',false);return;}
  OM('🍖 Выберите питомца',pets.map(p=>`<div class="fopt" onclick="doFeedFromInv(${p.id},'${fid}',this)"><span class="fn">${p.name||p.species_id}</span><span class="fq">${p.fatigue}% уст.</span></div>`).join(''),[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function doFeedFromInv(pid,fid,row) {
  row.style.opacity='.4';
  api('/zoo/feed',{method:'POST',body:JSON.stringify({pet_id:pid,food_id:fid})})
    .then(r=>{
      toast(`✅ ${r.fatigue_before}%→${r.fatigue_after}%`);CM();_zooData=null;loadInventory();
      // БАГ 2026-07-23: food_energy мгновенно завершает поход (services/zoo.py::
      // end_expedition_now), но экран «Отправить в поход» на Зоопарке строится из
      // кэша _expOpts (см. app.03.js::loadZoo/expLauncherHtml) — этот путь его не
      // трогал (только loadInventory), так что открытый ранее Зоопарк ещё долго
      // показывал старое «поход идёт». Тот же паттерн, что и у WS expedition_done.
      if(fid==='food_energy' && _loaded.has('zoo')) loadZoo();
    })
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}
function openBoostSelModal(bid) {
  api('/zoo/expeditions').then(d=>{
    if(!d.expeditions.length){toast('Нет активных экспедиций.',false);return;}
    OM('⏩ Выберите экспедицию',d.expeditions.map(e=>`<div class="fopt" onclick="doBoostFromInv(${e.pet_id},'${bid}',this)">
      <span class="fn">${e.name}</span><span style="font-size:11px;color:var(--teal)">${countdownMs(expDeadlineMs(e))}</span></div>`).join(''),[{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
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
  api('/inventory/apply-dust',{method:'POST',body:JSON.stringify({dust_id:did,pet_id:pid,chat_id:_cid})})
    .then(r=>{toast(`✅ +${r.duplicates_added} дубл.`);CM();_zooData=null;loadInventory();})
    .catch(e=>{toast(e,false);row.style.opacity='1';});
}

// ── Source info for themes ────────────────────────────────────────────────────
const SRC = {
  start:          {label:'Стартовая',     desc:'Есть у всех игроков с самого начала. Бесплатно!', action:null},
  shop_mora:      {label:'Магазин 🪙',    desc:'Купите напрямую в Магазине за Мору.', action:null},
  shop_diamond:   {label:'Магазин 💎',    desc:'Купите в Магазине за Алмазы.', action:null},
  dark:           {label:'Архив Ночи 🌑', desc:'Архивный предмет за ранее накопленную Тёмную Мору. Новых начислений нет.', action:{l:'🌑 Открыть Архив', f:"goToDarkMora()"}},
  zarniki:        {label:'Зарники ✨',     desc:'Приобретается за донат-валюту Зарники (Telegram Stars). 1 Звезда = 10 Зарников.',
                   action:{l:'✨ Пополнить Зарники', f:"goTo('market','vip')"}},
  gacha_novice:   {label:'Архив находок', desc:'Источник закрыт; уже полученная тема остаётся у владельца.', action:null},
  gacha_standard: {label:'Архив находок', desc:'Источник закрыт; уже полученная тема остаётся у владельца.', action:null},
  gacha_premium:  {label:'Архив находок', desc:'Источник закрыт; уже полученная тема остаётся у владельца.', action:null},
  gacha_mora:     {label:'Архив находок', desc:'Источник закрыт; уже полученная тема остаётся у владельца.', action:null},
  gacha_diamond:  {label:'Архив находок', desc:'Источник закрыт; уже полученная тема остаётся у владельца.', action:null},
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
  if(t.source && t.source.startsWith('gacha')) return '<span class="theme-status ts-gacha">Архив</span>';
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

// ── Profile preview — Render Raw String approach ─────────────────────────────
// Backend generates the EXACT same HTML string as sent to Telegram.
// Frontend just sets innerHTML + white-space:pre-wrap. No parsing.

function buildProfilePreview(t) {
  // Пустой контейнер — бэкенд заполняет его строкой через fetch /themes/preview
  // (Render Raw String: тот же HTML, что бот шлёт в Telegram). См. openThemeModal().
  return `<div class="profile-preview" style="min-height:40px"></div>`;
}

function openThemeModal(tid) {
  if(!_themeData) return;
  const t = _themeData.find(x => x.theme_id === tid);
  if(!t) return;

  const price = t.price_mora ? `${fmt(t.price_mora)} 🪙` : t.price_diamonds ? `${t.price_diamonds} 💎`
    : t.price_zarniki ? `${fmt(t.price_zarniki)} ✨` : t.price_dark ? `${t.price_dark} 🌑` : null;
  const src = SRC[t.source] || SRC[t.source?.split('_')[0]+'_'+t.source?.split('_').slice(1).join('_')] || {label:t.source, desc:'', action:null};
  // UX_AUDIT С5 («Сайт == бот»): покупаемо всё, что умеет бэкенд /themes/buy —
  // магазинные (🪙/💎), донатные (✨) и тёмные (🌑).
  const buyable = price && (t.source === 'shop_mora' || t.source === 'shop_diamond' || t.source === 'zarniki' || t.source === 'dark');

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
function loadTop(){switchTop('local',document.querySelector('#pro-hof .tab-inner .tb'));}
// БЛОК21 «видимый статус»: имя в топе с флексом — ник-глоу (косметика) + титул под ником.
function _topName(r){
  const g = r.glow ? ' '+r.glow : '';
  const t = r.title ? `<div class="top-title${r.title_css?' '+r.title_css:''}">${esc(r.title)}</div>` : '';
  return `<span class="uname-link${g}" onclick="openGlobalProfile(${r.user_id})">${vipName(r.username, r.is_vip)}</span>${t}`;
}
function switchTop(mode, btn) {
  document.querySelectorAll('#pro-hof .tab-inner .tb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  _trackSubtab('profile/hof/'+mode);
  const localChatId = _initChatId || _cid;
  const localChatName = _initChatTitle || 'самый активный из ваших';

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
      const top3=rows.slice(0,3), rest=rows.slice(3,200);
      const podium = top3.length>=2 ? '<div class="podium">'+top3.map((r,i)=>`
        <div class="pd pd-${i+1}">
          <div class="pd-medal">${MEDALS[i]}</div>
          <div class="pd-name">${_topName(r)}</div>
          <div class="pd-cnt">${fmt(r.count)} 💬</div>
        </div>`).join('')+'</div>' : '';
      const restHtml = rest.length ? '<div class="card">'+rest.map((r,i)=>`<div class="trow${r.is_vip?' trow-vip':''}">
          <div class="tpos">${i+4}</div>
          <div class="tname">${_topName(r)}</div>
          <div class="tcnt">${fmt(r.count)} 💬</div>
        </div>`).join('')+'</div>' : '';
      // если меньше 2 игроков — просто список
      const single = (top3.length<2) ? '<div class="card">'+top3.map((r,i)=>`<div class="trow">
          <div class="tpos">${MEDALS[i]||(i+1)}</div><div class="tname">${_topName(r)}</div>
          <div class="tcnt">${fmt(r.count)} 💬</div></div>`).join('')+'</div>' : '';
      el('top-c').innerHTML = header + podium + single + restHtml;
    })
    .catch(e => { el('top-c').innerHTML=`<div class="err">${e}</div>`; });
}

// ── Роли Моры и Алмазов (owner-v3: прямого обмена больше нет) ────────────────
let _exchData = null;
// Старый вход сохранён как понятная памятка, чтобы не оставлять мёртвую вкладку.
function loadExchange() {
  el('mkt-exch').innerHTML='<div class="loader">Загрузка...</div>';
  api('/exchange/').then(d=>{
    _exchData = d;
    el('mkt-exch').innerHTML=`<div class="card">
      <div style="padding:4px 0 8px">
        <div style="font-size:15px;font-weight:700;color:var(--bright)">${d.title}</div>
      <div style="font-size:11px;color:var(--muted);margin-top:3px">${d.blocked_rule}</div>
      </div>
      <div class="divider"></div>
      <div class="irow"><span class="ik">Ваш баланс</span><span>${fmt(d.mora)} 🪙 · ${d.diamonds.toFixed(1)} 💎</span></div>
      <div class="irow"><span class="ik">🪙 Мора</span><span>${d.mora_rule}</span></div>
      <div class="irow"><span class="ik">💎 Алмазы</span><span>${d.diamonds_rule}</span></div>
    </div>`;
  }).catch(e=>{el('mkt-exch').innerHTML=`<div style="color:var(--red);font-size:12px;padding:10px">${e}</div>`;});
}
// Клик по Море/Алмазам объясняет их назначение вместо несуществующего обмена.
function openExchangeCurrencyModal(dir) {
  OM('💱 Обмен валют', '<div class="loader">Загрузка...</div>', [{l:'Закрыть', c:'btn-ghost', f:'CM()'}]);
  api('/exchange/').then(d=>{
    _exchData = d;
    el('mb').innerHTML = `
      <div style="font-size:12px;color:var(--muted);line-height:1.6">
        Баланс: <b style="color:var(--gold2)">${fmt(d.mora)} 🪙</b> · <b style="color:var(--bright)">${d.diamonds.toFixed(1)} 💎</b>
      </div>
      <div style="display:grid;gap:8px;margin-top:10px">
        <div class="irow"><span class="ik">🪙 Мора</span><span>${d.mora_rule}</span></div>
        <div class="irow"><span class="ik">💎 Алмазы</span><span>${d.diamonds_rule}</span></div>
      </div>
      <div style="font-size:11px;color:var(--gold2);margin-top:10px">${d.blocked_rule}</div>`;
  }).catch(e=>{ el('mb').innerHTML = `<div class="err">${e}</div>`; });
}

// ── Dark Mora ─────────────────────────────────────────────────────────────────
function loadDarkMora() {
  el('dkc').innerHTML=`
    <button class="btn gates-cta" style="margin-bottom:10px" onclick="openShadowGates()">🔔 Открыть новую игру <b>›</b></button>
    <div class="card card-gold">
    <div class="card-title">🌑 Архив Ночи</div>
    <div style="font-size:12px;color:var(--muted);line-height:1.5;margin-bottom:12px">
      Здесь сохранена ранее полученная Тёмная Мора. Новых начислений нет.<br>
      Остаток можно потратить на архивные реликвии и уже выпущенные теневые темы.
    </div>
  </div>
  <div id="relics-card" style="margin-top:10px"></div>`;
  loadRelics();
}

// ── 🏛 Реликвии (Block 13 на вебе — паритет с ботом «бот реликвии») ───────────
function loadRelics() {
  const host = el('relics-card');
  if(!host) return;
  api('/relics/').then(d=>{
    const PCI = {mora:'🪙', diamonds:'💎', dark_mora:'🌑'};
    const priceStr = p => Object.entries(p||{}).map(([k,v])=>`${fmtF(v)} ${PCI[k]||k}`).join(' + ');
    const rows = (d.relics||[]).map(r=>{
      const right = r.owned
        ? `<span style="color:var(--green);font-weight:700;flex:none;font-size:11px">✅ В коллекции</span>`
        : `<button class="btn btn-sm btn-gold" style="flex:none" onclick="buyRelic('${r.id}',this)">Купить за ${priceStr(r.price)}</button>`;
      return `<div style="padding:9px 0;border-bottom:1px solid var(--border2)">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
          <div style="min-width:0">
            <div style="font-weight:600">${r.owned?'':esc(r.badge)+' '}${esc(r.name)}</div>
            <div style="font-size:10px;color:var(--muted);margin-top:2px">${esc(r.desc)}</div>
          </div>
          ${right}
        </div>
      </div>`;
    }).join('');
    host.innerHTML = `<div class="card card-gold">
      <div class="card-title">🏛 Реликвии</div>
      <div class="irow"><span class="ik">Коллекция</span><span style="color:var(--gold);font-weight:700">${d.owned_count}/${d.total}</span></div>
      <div style="font-size:11px;color:var(--muted);margin:8px 0">Архивные предметы за ранее накопленную 🌑 Тёмную Мору. Они сохраняют историю, но не дают игровую силу.</div>
      ${rows}
    </div>`;
  }).catch(e=>{host.innerHTML=`<div class="card"><div class="err">${e}</div></div>`;});
}
function buyRelic(id,btn) {
  if(btn) btn.disabled=true;
  const requestKey=btn?.dataset.requestKey||economyRequestKey('archive-relic-'+id);
  if(btn) btn.dataset.requestKey=requestKey;
  api('/relics/buy',{method:'POST',headers:{'Idempotency-Key':requestKey},body:JSON.stringify({relic_id:id})})
    .then(r=>{toast(r.message||'🏛 Реликвия получена!');refreshCurrBar();loadRelics();})
    .catch(e=>{toast(e,false);if(btn) btn.disabled=false;});
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
      <div style="font-size:11px;color:var(--muted);margin:4px 0 2px">Косметика, сервисные возможности и необратимый обмен в Мору</div>
      <div style="font-size:13px;color:var(--gold2);font-weight:800;margin-bottom:10px">Баланс: ${fmt(bal)} ✨</div>
      <div class="zar-grid">${pkgCards}</div>
      <div style="display:flex;gap:6px;margin-top:10px">
        <input id="zar-custom" type="number" min="1" class="num-input" style="flex:1;margin:0" placeholder="Своя сумма ⭐"/>
        <button class="btn btn-gold" onclick="buyZarnikiCustom()">Купить</button>
      </div>
      <div style="font-size:9.5px;color:var(--muted);margin-top:6px">1 ⭐ = ${perStar} ✨ · оплата звёздами Telegram</div>
      <div class="pay-terms">Покупая, вы соглашаетесь с <a href="${BASE}/legal/tos" target="_blank" rel="noopener">Соглашением</a>. Цифровые товары возврату не подлежат.</div>
    </div>`;

  // 2. VIP
  const seniorityLine = d.seniority_days>0
    ? `<div style="font-size:11px;color:var(--gold2);margin-top:4px">🏅 Стаж VIP: ${d.seniority_months} мес. (${d.seniority_days} дн.)</div>` : '';
  // Перки VIP — продающий список (из бэкенда, единый с ботом)
  const perksBlock = (d.perks && d.perks.length)
    ? `<div class="card card-gold" style="margin-bottom:4px">
        <div class="card-title">✨ Что даёт VIP</div>
        <div style="font-size:11.5px;color:var(--text);line-height:1.85">${d.perks.map(p=>esc(p)).join('<br>')}</div>
        <div style="font-size:10px;color:var(--muted);margin-top:6px">Всё это — косметика, удобство и бонусы. Без преимущества в силе.</div>
      </div>` : '';

  const vipStatus = d.active
    ? `<div class="prem-card">
        <div class="prem-tag">VIP</div>
        <div class="prem-title">👑 ${d.tier_label}</div>
        <div style="font-size:11.5px;color:var(--muted);margin-top:3px">Истекает ${new Date(d.expires_at).toLocaleDateString('ru-RU')} · осталось ${d.days_left} дн.</div>
        ${seniorityLine}
        <div style="font-size:11px;color:var(--text);margin-top:8px;padding:7px 10px;background:rgba(232,181,77,.08);border:1px solid var(--border);border-radius:12px">🎨 Сервис и оформление активны. Игровые шансы и награды не меняются.</div>
        <div style="font-size:11px;color:var(--muted);margin-top:6px">Можно продлить — срок сложится, тариф сменится сразу.</div>
      </div>`
    : '';

  const tiers = d.tiers.map(t=>{
    const afford = bal >= t.price_zarniki;
    const savings = t.savings_zarniki>0
      ? `<span style="font-size:10px;color:var(--muted);text-decoration:line-through;margin-left:4px">${fmt(t.base_price_zarniki)}✨</span> <span style="font-size:10px;color:var(--green);font-weight:700">−${fmt(t.savings_zarniki)}✨</span>` : '';
    return `<div class="prem-card">
      <div class="prem-title">${t.label}</div>
      ${t.tagline?`<div style="font-size:10.5px;color:var(--gold2);margin:2px 0 4px">${esc(t.tagline)}</div>`:''}
      <div class="prem-price">${fmt(t.price_zarniki)} ✨ <span style="font-size:10px;color:var(--muted);font-weight:600">/ ${t.duration_days} дн.</span>${savings}</div>
      <div class="prem-list">🎨 Образы и сцены профиля<br>📊 Расширенная история забегов<br>🤖 Дополнительный лимит ИИ для мира и справки</div>
      <button class="btn ${afford?'btn-gold':'btn-ghost'} btn-full" style="margin-top:4px" onclick="${afford?`doBuyVip('${t.tier}','${t.label}',${t.price_zarniki})`:`goToZarTop()`}">${afford?`Оформить за ${fmt(t.price_zarniki)} ✨`:`Нужно ${fmt(t.price_zarniki)} ✨ — пополнить`}</button>
    </div>`;
  }).join('');

  el('mkt-vip').innerHTML = donateCard
    + `<div class="card-title" style="margin:14px 2px 8px;font-size:14px">👑 VIP-подписка</div>`
    + (vipStatus ? vipStatus : perksBlock)
    + (d.active ? perksBlock : '')
    + tiers
    + `<div class="pay-terms">Оформляя покупку, вы соглашаетесь с <a href="${BASE}/legal/tos" target="_blank" rel="noopener">Соглашением</a>. Цифровые товары возврату не подлежат.</div>`;
}

function goToZarTop() {
  el('mkt-vip')?.scrollIntoView({behavior:'smooth', block:'start'});
  toast('Пополни Зарники сверху ☝️');
}

// Открыть Stars-invoice с фолбэками (openInvoice → openTelegramLink → window.open).
// openInvoice есть в telegram-web-app.js, но старый клиент / запуск по ссылке из группы
// может НЕ поддерживать метод (WebAppMethodUnsupported) → гейтим по версии + try/catch.
function _openInvoiceLink(link, onPaid){
  const verOk = tg && (!tg.isVersionAtLeast || tg.isVersionAtLeast('6.1'));
  const onStatus = status=>{ if(status==='paid'){ if(onPaid) onPaid(); } else if(status==='failed'){ toast('Платёж не прошёл',false); } };
  if(tg && typeof tg.openInvoice === 'function' && verOk){ try { tg.openInvoice(link, onStatus); return; } catch(e) {} }
  if(tg && typeof tg.openTelegramLink === 'function' && verOk){ try { tg.openTelegramLink(link); toast('Счёт открыт в Telegram — оплати звёздами'); return; } catch(e) {} }
  window.open(link, '_blank'); toast('Счёт открыт — оплати звёздами в Telegram');
}
function buyZarniki(stars) {
  api('/payments/zarniki/invoice',{method:'POST',body:JSON.stringify({stars})})
    .then(r=>_openInvoiceLink(r.link, ()=>{
      toast('✨ Зарники зачислены! Спасибо за поддержку 💜'); CM();
      setTimeout(()=>{ loadProfile(); if(_mktTab==='vip') loadVip(); }, 1600);
    }))
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
    [{l:'✅ Купить', c:'btn-gold', f:`_vipPay('${tier}',${price})`}, {l:'Отмена', c:'btn-ghost', f:'CM()'}]);
}
function _vipPay(tier, price) {
  CM();  // Block 5.2-rollout: для женатых — выбор личный/семейный кошелёк (✨)
  withPaymentSource('zarniki', price, () => confirmBuyVip(tier));
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
