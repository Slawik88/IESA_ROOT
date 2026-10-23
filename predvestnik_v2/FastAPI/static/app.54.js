// Earned star dust: one confirmed, durable exchange across uncertain responses.
const _sd = {me:null, pending:null, busy:false, seq:0, notice:'', noticeError:false, refreshing:false, choice:null, draft:'', formError:'', readySeq:0, writeVersion:0};
function _sdKey() { return 'pv_dust_pending:'+_sd.me.user_id; }
function _sdVisible() { return document.getElementById('sd-content'); }
async function _sdRead() {
  // A read begun before a confirmed write must never overwrite its receipt.
  let version,me;
  do {version=_sd.writeVersion;me=await api('/star-dust/me');} while(version!==_sd.writeVersion);
  return me;
}
async function openStarDust() {
  const seq=++_sd.seq;_sd.refreshing=false;
  _trSheet(_trSheetHtml('Звёздная пыль','<div id="sd-content" role="status">Собираем звёзды…</div>',''));
  try {
    const me=await _sdRead();
    if(seq!==_sd.seq || !_sdVisible()) return;
    if(_sd.me?.user_id!==me.user_id) _sd.draft='';
    _sd.readySeq=seq;_sd.me=me; _sd.choice=null; _sd.formError=''; _sd.notice=''; _sd.noticeError=false; _sd.pending=null;
    try { _sd.pending=JSON.parse(sessionStorage.getItem(_sdKey())||'null'); } catch(_) {}
    _sdRender();
  } catch(e) {
    if(seq===_sd.seq && _sdVisible()) _sdVisible().innerHTML=`<p class="tr-note" role="alert">${_trE(e.message||'Не удалось открыть звёздную пыль.')}</p><button class="v3-pill" onclick="openStarDust()">Повторить</button>`;
  }
}
function _sdDate(value) {
  const date=new Date(value);
  return Number.isFinite(date.getTime()) ? date.toLocaleString('ru',{day:'numeric',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '';
}
function _sdProgress(m) {
  const fraction=Math.max(0,Math.min(.999999,Number(m.pet_fraction)||0));
  const part=Math.floor(fraction*100)/100;
  const saved=fraction>0 ? `<p class="tr-note">${part>0?'В звёздном следе сохранено '+part.toLocaleString('ru')+' пыли.':'В звёздном следе сохранена частица пыли.'} Остаток добавится к следующей находке.</p>` : '';
  if(m.vip.max_days) return saved;
  const total=Number(m.balance)+fraction,missing=Math.max(.01,Number((m.vip.day_cost-total).toFixed(2)));
  return `${saved}<p class="tr-note">${m.vip.active?'До ещё одного':'До первого'} дня VIP ещё ${missing.toLocaleString('ru')} пыли.</p><progress class="sd-progress" max="${m.vip.day_cost}" value="${total}" aria-label="Пыль для одного дня VIP"></progress>`;
}
function _sdRender(days) {
  if(!_sdVisible() || !_sd.me || _sd.readySeq!==_sd.seq) return;
  if(days!==undefined) _sd.choice=days;
  const m=_sd.me,v=m.vip,p=_sd.pending,disabled=_sd.busy||_sd.refreshing;
  const chosen=_sd.choice;
  const expiry=_sdDate(v.expires_at);
  const status=expiry && v.active ? `VIP активен до ${expiry}` : 'VIP пока не активен';
  const controls=p ? `<p class="tr-note">Подтверждение на ${p.days} дн. сохранено. Повтор вернёт результат этого же обмена.</p><button type="button" class="v3-pill v3-pill--full" data-f="dust-retry" onclick="starDustBuy()" ${disabled?'disabled':''}>${_sd.busy?'Проверяем обмен…':'Проверить обмен'}</button>`
    : chosen ? `<section class="tr-grp"><h3>VIP на ${chosen} дн.</h3><p>Стоимость: <b>${fmt(chosen*v.day_cost)} пыли</b>. ${v.active?'Добавим к действующему VIP.':'VIP начнётся после подтверждения.'}</p><button type="button" class="v3-pill v3-pill--full" data-f="dust-confirm" onclick="starDustBuy(${chosen})" ${disabled?'disabled':''}>Подтвердить обмен</button><button type="button" class="v3-link" data-f="dust-back" onclick="starDustBack()" ${disabled?'disabled':''}>‹ Выбрать другой срок</button></section>`
    : `<div class="sd-options">${[1,2,3,7].filter(d=>d<=v.max_days).map(d=>`<button type="button" class="v3-pill v3-pill--ghost" data-f="dust-${d}" onclick="starDustChoose(${d})" ${disabled?'disabled':''}>${d} дн. · ${fmt(d*v.day_cost)} 🌠</button>`).join('')}</div>${v.max_days>3?`<form class="sd-custom" novalidate onsubmit="_sdChoose(event)"><label class="tr-note" for="sd-days">По вашему запасу: до ${fmt(v.max_days)} дн.</label><input id="sd-days" data-f="dust-days" type="text" inputmode="numeric" autocomplete="off" aria-describedby="sd-days-help sd-days-error" aria-invalid="${!!_sd.formError}" value="${_trE(_sd.draft||'')}" placeholder="Дней" oninput="starDustDraft(this)" ${disabled?'disabled':''}><button type="submit" class="v3-pill v3-pill--ghost" data-f="dust-choose" ${disabled?'disabled':''}>Выбрать</button><span id="sd-days-help" class="tr-note">Укажите целое число дней, например 5.</span><span id="sd-days-error" class="tr-note sd-error" role="alert">${_trE(_sd.formError||'')}</span></form>`:''}${v.max_days?'':'<p class="tr-note">Пыль приносят путешествия питомцев и «бот звездопад» в чате.</p>'}`;
  const chat=m.chat_ready ? 'Сегодня можно поймать звёзды в чате.' : `Следующий звездопад — ${_sdDate(m.next_chat_at)}.`;
  _trRepaint(_trSheetHtml('Звёздная пыль',`<div id="sd-content" aria-busy="${!!disabled}"><div class="sd-heading"><p class="v3-eyebrow">Ваш звёздный запас</p><button type="button" class="v3-link" data-f="dust-refresh" onclick="starDustRefresh()" ${disabled?'disabled':''}>${_sd.refreshing?'Обновляем…':'Обновить'}</button></div><p class="tr-lv sd-balance"><span>🌠 Пыль</span><b>${fmt(m.balance)}</b></p><p class="tr-note">Из путешествий сегодня: ${m.pet_today}</p>${_sdProgress(m)}<p class="tr-note sd-vip-status" role="status">${_trE(status)}</p>${_sd.notice?`<p class="tr-note" role="${_sd.noticeError?'alert':'status'}">${_trE(_sd.notice)}</p>`:''}<section class="tr-grp"><h3>Дни VIP за игру</h3><p>${v.day_cost} пыли за день · любой срок по вашему запасу</p>${controls}</section><details class="tr-grp" data-detail="dust-rules"><summary>Где найти пыль и как работает обмен</summary><p class="tr-note">${_trE(chat)} Напишите «бот звездопад»: раз в день можно поймать до 24 пыли, а иногда звёзды не появляются.</p><p class="tr-note">Звёздный след общий для отряда: походы и экспедиции собирают 2 пыли в час, дозоры — 1 пыль за 5 часов. Перекрытия не умножают пыль, дробная часть сохраняется. Обычные находки у каждого питомца свои. Пыль личная, её нельзя передать или обменять на Мору.</p><p class="tr-note">Копите пыль и выбирайте любой доступный срок VIP. Ограничений на запас и календарных лимитов обмена нет; оплаченный VIP продлевается.</p></details></div>`,''));
}
function starDustDraft(input) {
  _sd.draft=input.value;_sd.formError='';
  input.setAttribute('aria-invalid','false');
  const error=document.getElementById('sd-days-error');if(error) error.textContent='';
}
function starDustChoose(days) {
  if(_sd.busy||_sd.refreshing) return;
  _sdRender(days);document.querySelector('[data-f="dust-confirm"]')?.focus({preventScroll:true});
}
function starDustBack() {
  _sd.choice=null;_sdRender();
  (document.getElementById('sd-days')||document.querySelector('[data-f="dust-1"]'))?.focus({preventScroll:true});
}
async function starDustRefresh() {
  if(!_sd.me || _sd.busy || _sd.refreshing) return;
  const owner=_sd.me.user_id,seq=++_sd.seq;_sd.readySeq=seq;
  _sd.refreshing=true;_sdRender();
  try {
    const fresh=await _sdRead();
    if(seq!==_sd.seq || _sd.me?.user_id!==owner) return;
    if(fresh.user_id!==owner) {await openStarDust();return;}
    _sd.me=fresh;
    if(_sd.noticeError) _sd.notice='Запас обновлён.';
    if(_sd.choice>fresh.vip.max_days) {_sd.choice=null;_sd.notice='Запас изменился. Выберите доступный срок.';}
    _sd.noticeError=false;
  } catch(e) {
    if(seq===_sd.seq && _sd.me?.user_id===owner) {_sd.notice='Не удалось обновить запас. Последние данные сохранены; попробуйте ещё раз.';_sd.noticeError=true;}
  } finally {if(seq===_sd.seq && _sd.me?.user_id===owner) {_sd.refreshing=false;_sdRender();}}
}
async function starDustBuy(days) {
  if(_sd.busy || !_sd.me) return;
  if(!_sd.pending) {
    if(!Number.isInteger(days) || days<1 || days>_sd.me.vip.max_days) return;
    _sd.pending={days,expected_cost:days*_sd.me.vip.day_cost,expected_user_id:_sd.me.user_id,action_id:'dust-'+(globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+Math.random().toString(36).slice(2))};
    try { sessionStorage.setItem(_sdKey(),JSON.stringify(_sd.pending)); }
    catch(_) { _sd.pending=null;_sd.notice='Не удалось сохранить подтверждение. Откройте приложение заново.';_sdRender();return; }
  }
  const owner=_sd.me.user_id,seq=_sd.seq,body={..._sd.pending},key=_sdKey();
  _sd.busy=true;_sdRender();
  const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),15000);
  try {
    const response=await fetch(BASE+'/star-dust/vip',{method:'POST',headers:hdrs(),body:JSON.stringify(body),signal:controller.signal});
    const r=await response.json().catch(()=>({}));
    if(!response.ok) {const e=new Error(typeof r.detail==='string'?r.detail:'Не удалось проверить обмен. Повторите ту же кнопку.');e.definitive=[409,422].includes(response.status);throw e;}
    ++_sd.writeVersion;
    sessionStorage.removeItem(key);
    if(_sd.me?.user_id!==owner) return;
    _sd.pending=null;_sd.choice=null;_sd.draft='';_sd.noticeError=false;_sd.notice=`VIP продлён на ${r.days} дн. Списано ${r.cost} пыли.`;
    _sd.me.balance=r.balance;_sd.me.vip.max_days=Math.floor(r.balance/_sd.me.vip.day_cost);_sd.me.vip.expires_at=r.expires_at;_sd.me.vip.active=true;
    try { const fresh=await _sdRead(); if(_sd.me?.user_id===owner && _sd.seq===seq && fresh.user_id===owner) _sd.me=fresh; } catch(_) { /* receipt is already confirmed; show it even if fresh read fails */ }
    if(_sd.me?.user_id!==owner) return;
    if(typeof _scheduleReactiveRefresh==='function') _scheduleReactiveRefresh();
    if(_tr.me?.user_id===owner && _tr.me.star_dust) _tr.me.star_dust.balance=r.balance;
  } catch(e) {
    if(_sd.me?.user_id!==owner) return;
    if(e.definitive) {sessionStorage.removeItem(key);_sd.pending=null;}
    _sd.noticeError=true;_sd.choice=null;
    _sd.notice=e.message||'Ответ не дошёл. Повторите проверку: обмен не спишется дважды.';
  } finally {clearTimeout(timer);_sd.busy=false;_sdRender();}
}

function _sdChoose(event) {
  event?.preventDefault();
  if(_sd.busy||_sd.refreshing) return;
  const raw=document.getElementById('sd-days')?.value.trim()||'';
  _sd.draft=raw;
  const days=Number(raw);
  if(!/^[0-9]+$/.test(raw) || !Number.isSafeInteger(days) || days<1) _sd.formError='Укажите целое число дней от 1.';
  else if(days>_sd.me.vip.max_days) _sd.formError=`Для ${days} дн. нужно ${fmt(days*_sd.me.vip.day_cost)} пыли. В запасе ${fmt(_sd.me.balance)}.`;
  else { _sd.formError='';starDustChoose(days);return; }
  _sd.choice=null;_sdRender();document.getElementById('sd-days')?.focus({preventScroll:true});
}
