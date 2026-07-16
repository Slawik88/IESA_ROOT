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
  _bpCheckLevelUp(d.level);
  const pct=Math.round(d.xp_in_level/d.xp_per_level*100);
  const isMax=d.level>=d.max_level;
  const tinfo=_bpSeasonTimer(d);
  el('pro-bp').innerHTML=`
    <div class="card card-gold" style="margin-bottom:8px">
      <div class="card-title">🎫 ${d.season_label} — Уровень ${d.level}/${d.max_level}<button class="xpg-btn" onclick="bpXpGuide()">⚡ За что XP?</button></div>
      ${d.frozen?`<div class="bp-frozen-banner">❄️ <b>Сезон временно заморожен.</b> Начисление XP и выдача наград приостановлены.</div>`:''}
      ${!d.frozen&&d.weekend_boost&&d.weekend_boost.active?`<div style="margin:4px 0 8px;padding:5px 8px;border-radius:8px;background:linear-gradient(90deg,rgba(232,181,77,.18),rgba(232,181,77,.04));font-size:11px;color:var(--gold)">⚡ Выходные: <b>+${d.weekend_boost.pct}% XP</b> ко всему Боевому пропуску!</div>`:''}
      <div class="ach-bar bp-xpbar ${d.frozen?'bp-bar-frozen':''}" style="height:10px"><div class="ach-fill" style="width:${isMax?100:pct}%"></div></div>
      <div class="ach-prog">${isMax?'★ MAX уровень достигнут':`${fmt(d.xp_in_level)} / ${fmt(d.xp_per_level)} XP · осталось ${fmt(d.xp_to_next)} XP до ур. ${d.level+1}`}</div>
      ${tinfo.html}
      ${d.buy_next&&!d.frozen?`<button class="btn btn-sm btn-teal" style="margin-top:8px;width:100%" onclick="bpBuyLevel(this)">💎 Открыть уровень ${d.buy_next.level} за ${d.buy_next.price}💎</button>`:''}
      ${!d.paid_track_open?'<div style="margin-top:8px;font-size:11px;color:var(--gold2)">👑 VIP-трек закрыт — оформи VIP («бот vip»), чтобы забирать платные награды.</div>':''}
    </div>
    ${_bpNextRewardCard(d)}
    <div class="card">
      <div class="card-title">Награды по уровням${_bpHasClaimable(d)?' <button class="btn btn-sm btn-gold" style="float:right;padding:2px 10px" onclick="bpClaimAll(this)">🎁 Забрать всё</button>':''}</div>
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
// Косметика в наградах БП раньше показывалась голым item_id (cos_name_glow_silver) —
// теперь бэк резолвит имя+css+rarity+slot (_resolve_items), а тут превращаем это
// в кликабельный чип: тап открывает живой превью того же вида, что в «Внешний вид».
let _bpCosMap={};
function _bpItemChip(it){
  if(it.is_cosmetic){
    _bpCosMap[it.item_id]=it;
    return `<span class="bp-cos-chip" onclick="event.stopPropagation();_bpCosPreview('${it.item_id}')">🎨 ${esc(it.name)}</span>`;
  }
  return `+${it.qty} ${esc(it.name)}`;
}
function _bpCosPreview(id){
  const it=_bpCosMap[id]; if(!it) return;
  const sw=_looksSwatch(it.slot,it);
  OM(`🎨 ${esc(it.name)}`,
    `<div style="text-align:center;padding:6px 0">${sw}
       <div style="margin-top:10px;font-size:12px;color:${rarColor(it.rarity)}">${esc(rarLabel(it.rarity))}</div>
     </div>`,
    [{l:'Понятно',c:'btn-gold',f:'CM()'}]);
}
function _bpRewardCell(level,track,reward) {
  const hasChoice = reward.options && reward.options.length>=2;
  let text;
  if(hasChoice){
    text = `🎁 Выбор: ${reward.options.map(o=>o.text).join(' / ')}`;
  } else {
    const parts=[];
    if(reward.mora) parts.push(`+${fmt(reward.mora)} 🪙`);
    if(reward.diamonds) parts.push(`+${reward.diamonds} 💎`);
    (reward.items||[]).forEach(it=>parts.push(_bpItemChip(it)));
    if(reward.theme) parts.push(`🎨 Тема «${reward.theme}» <span class="bp-exc-tag">🗓 эксклюзив</span>`);
    text=parts.join(', ')||'—';
  }
  const st=reward.status;
  const sty=BP_CELL_STYLE[st]||BP_CELL_STYLE.locked_level;
  const mark=st==='claimed'?'✅ ':st==='locked_vip'?'🔒 ':'';
  const btn=st==='available'
    ?(hasChoice
      ?`<button class="btn btn-sm btn-gold" style="margin-top:3px;width:100%;padding:3px 0;font-size:10px" onclick="bpChoose(${level},'${track}')">Выбрать</button>`
      :`<button class="btn btn-sm btn-gold" style="margin-top:3px;width:100%;padding:3px 0;font-size:10px" onclick="doBpClaim(${level},'${track}',this)">Забрать</button>`)
    :'';
  return `<div style="font-size:10px;padding:4px 6px;border:1px solid ${sty.border};border-radius:6px;opacity:${sty.opacity}">${mark}${text}${btn}</div>`;
}
// C4: таймер сезона + % прошедшего времени + прогноз домакса по текущему темпу.
function _bpSeasonTimer(d){
  if(!d.season_ends) return {html:''};
  const msDay=86400000;
  const today=new Date(); today.setHours(0,0,0,0);
  const end=new Date(d.season_ends+'T23:59:59');
  const start=d.season_starts?new Date(d.season_starts+'T00:00:00'):null;
  const daysLeft=Math.max(0,Math.ceil((end-today)/msDay));
  let elapsedPct=0, projHtml='';
  if(start){
    const total=Math.max(1,(end-start)/msDay);
    const passed=Math.min(total,Math.max(0,(today-start)/msDay));
    elapsedPct=Math.round(passed/total*100);
    if(d.level<d.max_level && passed>=1){
      const rate=d.xp/passed;                                  // XP/день текущий темп
      const need=(d.max_level-1)*d.xp_per_level - d.xp;        // XP до MAX
      const daysNeed=rate>0?need/rate:Infinity;
      projHtml = daysNeed<=daysLeft
        ? `<span style="color:var(--green)">✓ при текущем темпе домакаешься за ~${Math.ceil(daysNeed)} дн.</span>`
        : `<span style="color:var(--gold2)">⚠ при текущем темпе MAX не успеть — нужно активнее</span>`;
    }
  }
  const urgent = daysLeft>0 && daysLeft<=7;
  const daysHtml = daysLeft>0
    ? `${urgent?'🔥':'⏳'} До конца сезона: <b style="${urgent?'color:var(--red)':''}">${daysLeft}</b> дн.${urgent?' — успей!':''}`
    : '🔥 Сезон завершается СЕГОДНЯ!';
  const endStr = (d.season_ends||'').split('-').reverse().slice(0,2).join('.');
  return {html:`<div style="margin-top:8px;font-size:11px;color:var(--muted)">
      ${daysHtml}
      <div class="ach-bar" style="height:5px;margin-top:4px;opacity:.7"><div class="ach-fill" style="width:${elapsedPct}%;background:var(--teal)"></div></div>
      ${projHtml?`<div style="margin-top:4px">${projHtml}</div>`:''}
      <div class="bp-exclusive">🔒 Косметика и темы сезона — <b>эксклюзив</b>. После ${endStr} их не получить никогда — кто прошёл, флексит навсегда.</div>
    </div>`};
}
// C1: справка «за что сколько XP» (данные из status.xp_guide → весов конструктора).
function bpXpGuide(){
  const g=((_bpData&&_bpData.xp_guide)||[]).slice().sort((a,b)=>(b.xp||0)-(a.xp||0));
  const wb=_bpData&&_bpData.weekend_boost;
  const boost=wb&&wb.active?`<div class="xpg-boost">⚡ Сейчас выходные — весь XP <b>+${wb.pct}%</b>!</div>`:'';
  const maxXp=Math.max(1,...g.map(a=>a.xp||0));
  const rows=g.length
    ? g.map(a=>{
        const pct=Math.round((a.xp||0)/maxXp*100);
        return `<div class="xpg-row">
          <div class="xpg-row-top">
            <span class="xpg-label">${esc(a.label)}</span>
            <span class="xpg-xp">+${a.xp}<span class="xpg-xp-u">XP</span></span>
          </div>
          <div class="xpg-bar"><span style="width:${pct}%"></span></div>
          <div class="xpg-cap">${a.daily_cap?`лимит ${a.daily_cap}/день`:'без лимита'}</div>
        </div>`;
      }).join('')
    : '<div style="color:var(--muted);font-size:12px;padding:8px 0">Список действий пока пуст.</div>';
  const body=`<div class="xpg-head">💯 <b>100 XP = 1 уровень.</b> Опыт капает за действия в чатах:</div>${boost}<div class="xpg-list">${rows}</div>`;
  OM('⚡ За что даётся опыт', body, [{l:'Понятно', c:'btn-gold', f:'CM()'}]);
}
// C2: лёгкий «сочный» левел-ап — вспышка карточки + тост при росте уровня с прошлого визита.
function _bpCheckLevelUp(level){
  let prev=null;
  try{ prev=parseInt(localStorage.getItem('bp_seen_level')||''); }catch(e){}
  if(prev && level>prev){ toast(`🎉 Боевой пропуск: уровень ${level}!`); _bpFlash(); }
  try{ localStorage.setItem('bp_seen_level', String(level)); }catch(e){}
}
function _bpFlash(){
  const c=el('pro-bp'); if(!c) return;
  c.classList.remove('bp-levelup'); void c.offsetWidth; c.classList.add('bp-levelup');
}
// C3: превью следующей награды (уровень L+1).
function _bpNextRewardCard(d){
  if(d.level>=d.max_level) return '';
  const r=(d.rewards||[]).find(x=>x.level===d.level+1);
  if(!r) return '';
  const cell=(rw,label)=>{
    let txt;
    if(rw.options&&rw.options.length>=2) txt='🎁 Выбор: '+rw.options.map(o=>o.text).join(' / ');
    else{ const p=[];
      if(rw.mora)p.push(`+${fmt(rw.mora)} 🪙`);
      if(rw.diamonds)p.push(`+${rw.diamonds} 💎`);
      (rw.items||[]).forEach(it=>p.push(_bpItemChip(it)));
      if(rw.theme)p.push(`🎨 Тема «${rw.theme}»`);
      txt=p.join(', ')||'—';
    }
    return `<div style="flex:1;min-width:0"><div style="font-size:9px;color:var(--muted);margin-bottom:2px">${label}</div><div style="font-size:11px">${txt}</div></div>`;
  };
  return `<div class="card" style="margin-bottom:8px">
    <div class="card-title" style="font-size:12px">🎯 Следующая награда — уровень ${d.level+1}</div>
    <div style="display:flex;gap:12px">${cell(r.free,'🆓 Бесплатный')}${cell(r.paid,d.paid_track_open?'👑 VIP':'🔒 VIP')}</div>
    <div style="font-size:10px;color:var(--muted);margin-top:6px">⚡ Ещё ${fmt(d.xp_to_next)} XP до открытия</div>
  </div>`;
}
function _bpHasClaimable(d){
  const ok=rw=>rw.status==='available' && !(rw.options&&rw.options.length>=2);
  return (d.rewards||[]).some(r=>ok(r.free)||ok(r.paid));
}
// C5: открыть следующий уровень за 💎 (подтверждение → покупка).
function bpBuyLevel(){
  const bn=_bpData&&_bpData.buy_next; if(!bn) return;
  OM('💎 Открыть уровень',
    `<div style="font-size:12px;color:var(--muted);padding:6px 0">Мгновенно открыть <b>уровень ${bn.level}</b> Боевого пропуска за <b>${bn.price}💎</b>?<br>Награду уровня нужно будет забрать.</div>`,
    [{l:`💎 Открыть за ${bn.price}`, c:'btn-gold', f:'_bpDoBuyLevel()'},
     {l:'Отмена', c:'btn-ghost', f:'CM()'}]);
}
function _bpDoBuyLevel(){
  CM();
  api('/battle_pass/buy-level',{method:'POST'})
    .then(r=>{toast(r.message); refreshCurrBar(); loadBattlePass();})
    .catch(e=>toast(e,false));
}
// C6: забрать все доступные награды одним тапом.
function bpClaimAll(btn){
  if(btn) btn.disabled=true;
  api('/battle_pass/claim-all',{method:'POST'})
    .then(r=>{
      toast(r.claimed?`🎁 Забрано наград: ${r.claimed}`:'Нет наград для сбора');
      if(r.pending_choices) setTimeout(()=>toast('🔀 Награды с выбором забери вручную'),500);
      loadBattlePass();
    })
    .catch(e=>{toast(e,false); if(btn)btn.disabled=false;});
}
function doBpClaim(level,track,btn) {
  btn.disabled=true;
  api('/battle_pass/claim',{method:'POST',body:JSON.stringify({level,track})})
    .then(r=>{toast(r.message);loadBattlePass();})
    .catch(e=>{toast(e,false);btn.disabled=false;});
}
function bpChoose(level,track) {
  const lvl=(_bpData.rewards||[]).find(r=>r.level===level);
  const opts=(lvl&&lvl[track]&&lvl[track].options)||[];
  if(opts.length<2) return;
  OM(`🎫 Уровень ${level} — выбор награды`,
    `<div style="font-size:12px;color:var(--muted);padding:6px 0">Можно забрать только ОДИН вариант:</div>`,
    opts.map((o,i)=>({l:`🎁 ${o.text}`, c:'btn-gold', f:`doBpClaimChoice(${level},'${track}',${i})`})));
}
function doBpClaimChoice(level,track,idx) {
  CM();
  api('/battle_pass/claim',{method:'POST',body:JSON.stringify({level,track,choice_index:idx})})
    .then(r=>{toast(r.message);loadBattlePass();})
    .catch(e=>toast(e,false));
}

// ── Zoo ───────────────────────────────────────────────────────────────────────
let _expOpts=null;   // данные лаунчера похода (GET /zoo/expedition-options)
function loadZoo() {
  el('zoo-c').innerHTML='<div class="loader">Загрузка...</div>';
  Promise.all([api('/zoo/'),api('/zoo/expeditions'),api('/zoo/expedition-options').catch(()=>null)]).then(([data,expData,expOpts])=>{
    _zooData=data;
    _expOpts=expOpts;
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
      <div id="tm-${e.pet_id}">${countdownMs(expDeadlineMs(e))}</div>
    </div>
    ${Object.keys(boo).length?`<div style="padding-top:8px;border-top:1px solid var(--border2)">
      ${Object.entries(boo).map(([bid,b])=>`<div class="fopt" onclick="boostExp(${e.pet_id},'${bid}',this)">
        <span style="font-size:16px">⏩</span>
        <span class="fn">${b.name}</span><span class="fq">×${b.qty}</span>
        <span class="fr" style="color:var(--teal)">−${b.boost_hours}ч</span>
      </div>`).join('')}
    </div>`:''}
  </div>`).join('');
  _expTimer=setInterval(()=>d.expeditions.forEach(e=>{const t=el('tm-'+e.pet_id);if(t)t.innerHTML=countdownMs(expDeadlineMs(e));}),1000);
}
// ── 🗺 Лаунчер похода (отправка активного питомца прямо с сайта) ───────────────
function expLauncherHtml() {
  const o=_expOpts;
  if(!o) return '';
  if(o.busy) {
    const _left=(typeof o.busy_remaining_sec==='number')
      ?`вернётся через ${fmtDurShort(o.busy_remaining_sec)}`
      :`до ${esc(o.busy_until||'')}`;
    return `<div class="card" style="margin-bottom:10px">
      <div class="card-title">🗺 Поход идёт</div>
      <div class="irow"><span class="ik">${esc(o.busy_pet||'Питомец')} в походе</span><span style="color:var(--teal)">${_left}</span></div>
      <div style="font-size:10px;color:var(--muted);margin-top:4px">За раз можно отправить одного питомца. Ускорить возвращение — бустером (см. блок похода выше).</div>
    </div>`;
  }
  if(!o.active_pet) {
    return `<div class="card" style="margin-bottom:10px">
      <div class="card-title">🗺 Отправить в поход</div>
      <div style="font-size:11px;color:var(--muted);line-height:1.5">Нет активного питомца. Нажми на питомца ниже → «⚔️ Сделать активным», и сможешь отправить его в поход за Морой и опытом.</div>
    </div>`;
  }
  const p=o.active_pet, fat=p.fatigue||0;
  const rows=o.options.map(op=>{
    const free=op.cost<=0;
    const enoughMora=free||o.mora>=op.cost;
    const tooTired=(fat+op.fatigue)>100;
    const ret=new Date(Date.now()+op.hours*3600000);
    const rt=String(ret.getHours()).padStart(2,'0')+':'+String(ret.getMinutes()).padStart(2,'0');
    const warn=[];
    if(!enoughMora) warn.push('💰 может не хватить Моры');
    if(tooTired) warn.push('😴 сильно устанет');
    const xp=op.max_xp!==op.min_xp?`${op.min_xp}–${op.max_xp}`:`${op.min_xp}`;
    return `<div class="exp-opt${tooTired?' exp-opt-warn':''}" onclick="confirmExpedition(${op.hours})">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-weight:700">${op.hours}ч <span style="font-size:10px;color:var(--muted);font-weight:400">→ ~${rt}</span></span>
        <span style="font-size:11px;font-weight:600;color:${free?'var(--green)':'var(--gold)'}">${free?'бесплатно':fmt(op.cost)+' 🪙'}</span>
      </div>
      <div style="font-size:11px;color:var(--gold2);margin-top:3px">🪙 ${fmt(op.min_m)}–${fmt(op.max_m)} · 📚 ${xp} XP · 😴 +${op.fatigue}%</div>
      ${warn.length?`<div style="font-size:10px;color:var(--red);margin-top:3px">${warn.join(' · ')}</div>`:''}
    </div>`;
  }).join('');
  return `<div class="card card-gold" style="margin-bottom:10px">
    <div class="card-title">🗺 Отправить в поход</div>
    <div class="irow"><span class="ik">Питомец</span><span style="font-weight:700">${esc(p.name||p.species_id)} ${rc(p.rarity)} · Lv${p.pet_level}</span></div>
    <div class="fat-bar" style="margin:5px 0 3px"><div class="fat-fill${fat>=80?' critical':''}" style="width:${fat}%;background:${fatC(fat)}"></div></div>
    <div style="font-size:10px;color:${fatC(fat)};margin-bottom:8px">${fat}% усталости · в кошельке ${fmt(o.mora)} 🪙</div>
    ${rows}
    <div style="font-size:10px;color:var(--muted);margin-top:6px">Награда и усталость зависят от вида и уровня питомца — точный итог при возвращении. Отправится активный питомец.</div>
  </div>`;
}
function confirmExpedition(hours) {
  const o=_expOpts; if(!o) return;
  const op=(o.options||[]).find(x=>x.hours===hours); if(!op) return;
  const free=op.cost<=0;
  const xp=op.max_xp!==op.min_xp?`${op.min_xp}–${op.max_xp}`:`${op.min_xp}`;
  OM('🗺 Отправить в поход?',
    `<div class="irow"><span class="ik">Длительность</span><span>${hours}ч (вернётся ~${String(new Date(Date.now()+hours*3600000).getHours()).padStart(2,'0')}:${String(new Date(Date.now()+hours*3600000).getMinutes()).padStart(2,'0')})</span></div>
     <div class="irow"><span class="ik">Стоимость</span><span style="color:${free?'var(--green)':'var(--gold)'}">${free?'бесплатно':fmt(op.cost)+' 🪙'}</span></div>
     <div class="irow"><span class="ik">Награда</span><span style="color:var(--gold2)">🪙 ${fmt(op.min_m)}–${fmt(op.max_m)} · 📚 ${xp} XP</span></div>
     <div class="irow"><span class="ik">Усталость</span><span>+${op.fatigue}%</span></div>
     <div style="font-size:10px;color:var(--muted);margin-top:6px">Отправится твой активный питомец. Точная награда — при возвращении.</div>`,
    [{l:'🗺 Отправить',c:'btn-gold',f:`doStartExpedition(${hours})`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function doStartExpedition(hours) {
  api('/zoo/start-expedition',{method:'POST',body:JSON.stringify({hours,chat_id:_cid})})
    .then(r=>{toast(`🗺 ${r.pet_name} отправлен в поход на ${r.hours}ч!`);refreshCurrBar();CM();loadZoo();})
    .catch(e=>toast(e,false));
}

// ── Zoo helpers ───────────────────────────────────────────────────────────────
function bonusLines(sid, b) {
  const p = v => `${(v*100).toFixed(0)}%`, ln = [];
  ({
    squirrel: b => { ln.push(`📋 +${p(b.quest_mora_bonus)} Моры за квесты`); },
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
      if(b.gacha_daily_discount>0) ln.push(`🏷 −${p(b.gacha_daily_discount)} акция дня`); },
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
      if(b.crystal_egg_chance>0) ln.push(`🎟 Алмазный Жетон: ${p(b.crystal_egg_chance)}`); },
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

// ── Питомцы 2.0: слоты (Казарма-стиль) ─────────────────────────────────────────
function _zcEmoji(speciesId) {
  // PET_SPECIES_EMOJI определён в app.04.js (позже в склейке) — но это function
  // declaration вызывается только по клику, после того как весь скрипт уже
  // выполнился, так что const уже проинициализирован. Defensive-check — тот же
  // паттерн, что уже используется в app.06.js/app.11.js для этого же глобала.
  const map = (typeof PET_SPECIES_EMOJI !== 'undefined') ? PET_SPECIES_EMOJI : {};
  return map[speciesId] || '🐾';
}
function _zcSlotInner(p) {
  if (!p) return `<div class="bk-slot-e bk-slot-empty">➕</div><div class="bk-slot-n cx-dim">пусто</div>`;
  const fatPct = p.fatigue || 0;
  return `<div class="bk-slot-e">${_zcEmoji(p.species_id)}</div>
    <div class="bk-slot-n">${esc(p.name || p.species_id)}</div>
    <div class="bk-slot-s">Ур.${p.pet_level || 1}/10</div>
    <div class="zc-card-fat"><div class="zc-card-fat-fill" style="width:${fatPct}%;background:${fatC(fatPct)}"></div></div>`;
}
function _zcRenderSlots(active, passive, totalSlots) {
  const heroPet = active[0] || null;
  const hero = `<div class="bk-slot zc-slot-hero" onclick="${heroPet ? `openPetModal(${heroPet.id})` : `_zcOpenSlotPicker('active')`}">
    <div class="bk-slot-t">⚔️ Активный</div>${_zcSlotInner(heroPet)}
  </div>`;
  const passiveSlotsCount = Math.max(0, totalSlots - 1);
  const passiveCells = [];
  for (let i = 0; i < passiveSlotsCount; i++) {
    const p = passive[i] || null;
    passiveCells.push(`<div class="bk-slot" onclick="${p ? `openPetModal(${p.id})` : `_zcOpenSlotPicker('passive')`}">
      <div class="bk-slot-t">🛡 Пассивный</div>${_zcSlotInner(p)}
    </div>`);
  }
  return `<div class="zc-slots-row">${hero}</div>
    <div class="zc-slots-passive">${passiveCells.join('')}</div>`;
}
function _zcOpenSlotPicker(targetPlacement) {
  if (!_zooData) return;
  const storagePets = (_zooData.pets || []).filter(p => p.placement === 'storage');
  if (!storagePets.length) {
    toast('На складе нет питомцев — крутни Гачу.', false);
    return;
  }
  const label = targetPlacement === 'active' ? 'В активный слот' : 'В пассивный слот';
  const rows = storagePets.map(p => `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border2)">
      <div>
        <span style="font-weight:600">${esc(p.name || p.species_id)}</span> ${rc(p.rarity)}
        <span style="font-size:11px;color:var(--muted);margin-left:6px">Ур.${p.pet_level || 1}</span>
      </div>
      <button class="btn btn-sm btn-gold" onclick="_zcAssignPick(${p.id},'${targetPlacement}',this)">Выбрать</button>
    </div>`).join('');
  OM(label, `<div>${rows}</div>`, [{ l: 'Отмена', c: 'btn-ghost', f: 'CM()' }]);
}
function _zcAssignPick(petId, targetPlacement, btn) {
  if (btn) btn.disabled = true;
  api('/zoo/move', { method: 'POST', body: JSON.stringify({ pet_id: petId, placement: targetPlacement }) })
    .then(() => { CM(); toast('✅ Перемещено!'); _zooData = null; loadZoo(); })
    .catch(e => { toast(e, false); if (btn) btn.disabled = false; });
}

// Питомцы 2.0: компактная карточка грида (Казарма-стиль) — заменяет старую
// list-style petCard.
function _zcCard(p) {
  const fatPct = p.fatigue || 0;
  const lvl = p.pet_level || 1;
  const emoji = _zcEmoji(p.species_id);
  const badge = p.placement === 'active' ? '⚔️ Активный'
    : p.placement === 'passive' ? '🛡 Пассивный' : '';
  return `<div class="bk-card zc-card zc-card-in r-${p.rarity}" onclick="openPetModal(${p.id})">
    <div class="bk-card-e">${emoji}</div>
    <div class="bk-card-n">${esc(p.name || p.species_id)}</div>
    <div class="bk-card-s">${rc(p.rarity)} · Ур.${lvl}/10</div>
    <div class="zc-card-fat"><div class="zc-card-fat-fill" style="width:${fatPct}%;background:${fatC(fatPct)}"></div></div>
    ${badge ? `<div class="bk-card-f"><span class="bk-insq">${badge}</span></div>` : ''}
  </div>`;
}

// Питомцы 2.0: 2 вкладки (nursery = единый экран, bestiary — без изменений).
function swZoo(tab,btn) {
  _zooTab=tab;
  document.querySelectorAll('#pg-zoo > .tabs > .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const zooC = el('zoo-c'), zooBest = el('zoo-bestiary');
  if(zooC) zooC.style.display = tab==='bestiary' ? 'none' : '';
  if(zooBest) zooBest.style.display = tab==='bestiary' ? '' : 'none';
  _trackSubtab('zoo/'+tab);
  if(tab==='bestiary') { renderZooGuide(); return; }
  if(!_zooData){loadZoo();return;}
  renderZoo();
}

function renderZoo() {
  if(!_zooData)return;
  const allPets = _zooData.pets || [];
  if(!allPets.length){
    el('zoo-c').innerHTML=`<div style="text-align:center;padding:32px 16px;color:var(--muted)">
        <div style="font-size:32px;margin-bottom:8px">🐾</div>
        <div style="font-size:13px;font-weight:600;margin-bottom:4px">Питомцев пока нет</div>
        <div style="font-size:11px">Крутни Гачу, чтобы получить первого питомца</div>
        <button class="btn btn-gold btn-sm" style="margin-top:10px" onclick="goTo('market','gacha')">🎲 Открыть Гачу</button>
      </div>`;
    return;
  }

  const active=allPets.filter(p=>p.placement==='active');
  const passive=allPets.filter(p=>p.placement==='passive');
  const maxSlots=_zooData.max_slots||3;
  const baseSlots=_zooData.base_slots||3;
  const boughtSlots=_zooData.bought_slots||0;
  const vipExtra=_zooData.vip_extra_slot||0;
  const atCap=!!_zooData.at_slot_cap;
  const nextPrice=_zooData.slot_next_price;
  const totalSlots=maxSlots+vipExtra;
  const pendingMora=_zooData.pending_hamster_mora||0;
  const hasHamsters=allPets.some(p=>p.species_id==='hamster');

  let html = _zcRenderSlots(active, passive, totalSlots);
  html += `<div class="zc-buy-hint">
      📦 Базовых: <b style="color:var(--bright)">${baseSlots}</b>
      ${boughtSlots>0?` · 💎 Докуплено: <b style="color:var(--bright)">+${boughtSlots}</b>`:''}
      ${vipExtra>0?` · 👑 VIP: <b style="color:var(--gold)">+${vipExtra}</b>`:''}
    </div>`;
  html += atCap
    ? `<button class="btn btn-full btn-sm" disabled style="opacity:.45;cursor:not-allowed;margin-bottom:10px">🔒 Слоты за алмазы куплены (${boughtSlots}/${_zooData.max_purchasable||4})</button>`
    : `<button class="btn btn-full btn-sm btn-gold" style="margin-bottom:10px" onclick="doBuySlot()">🛒 Купить слот за ${nextPrice} 💎</button>`;

  if(hasHamsters){
    html += `<div style="background:var(--gold-dim);border:1px solid var(--border);border-radius:var(--r);padding:10px 12px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between">
      <div>
        <div style="font-size:11px;color:var(--muted);margin-bottom:2px">🐹 Хомяк-банкир накопил</div>
        <div style="font-size:16px;font-weight:700;color:var(--gold)">${pendingMora>0?fmt(pendingMora)+' 🪙':'Копит...'}</div>
      </div>
      <button class="btn btn-gold btn-sm" onclick="collectHamster(this)" ${pendingMora<1?'disabled':''}>Собрать</button>
    </div>`;
  }
  const wr=_zooData.wolf_restore;
  if(wr && wr.uses_left>0){
    html += `<div style="background:var(--s);border:1px solid var(--border2);border-radius:var(--r);padding:10px 12px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between">
      <div>
        <div style="font-size:11px;color:var(--muted);margin-bottom:2px">🐺 Волк — восстановление усталости</div>
        <div style="font-size:13px;font-weight:600">Осталось: ${wr.uses_left}/${wr.max_uses} · −${wr.restore_amount}% усталости</div>
      </div>
      <button class="btn btn-sm" style="background:var(--purple,#7c3aed);color:#fff" onclick="doWolfRestorePick()">Использовать</button>
    </div>`;
  }
  const ua=_zooData.unicorn_ability;
  if(ua){
    if(ua.active){
      html += `<div style="background:var(--s);border:1px solid var(--border2);border-radius:var(--r);padding:10px 12px;margin-bottom:10px">
        <div style="font-size:11px;color:var(--muted)">🦄 Иммунитет усталости: <b style="color:var(--green)">АКТИВЕН</b></div>
        <div style="font-size:10px;color:var(--muted);margin-top:2px">Истекает: ${ua.expires_at?ua.expires_at.slice(0,16).replace('T',' '):''}</div>
      </div>`;
    } else if(ua.available){
      html += `<div style="background:var(--s);border:1px solid var(--border2);border-radius:var(--r);padding:10px 12px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between">
        <div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:2px">🦄 Единорог — иммунитет усталости</div>
          <div style="font-size:13px;font-weight:600">Защита на ${ua.immunity_hours} ч. для всех питомцев</div>
        </div>
        <button class="btn btn-sm" style="background:linear-gradient(135deg,#a855f7,#ec4899);color:#fff" onclick="doUnicornImmunity(this)">Активировать</button>
      </div>`;
    }
  }
  html += expLauncherHtml();

  // Ростер: ВСЕ питомцы (вкл. занятых слотом — с бейджем), сортировка:
  // сначала занятые слотом (активный → пассивные), потом склад; внутри —
  // по убыванию редкости и уровня.
  const rarityRank = {mythic:5, legendary:4, epic:3, rare:2, uncommon:1, common:0};
  const placeRank = p => p.placement==='active' ? 2 : p.placement==='passive' ? 1 : 0;
  const roster = [...allPets].sort((a,b) =>
    (placeRank(b)-placeRank(a)) ||
    ((rarityRank[b.rarity]||0)-(rarityRank[a.rarity]||0)) ||
    ((b.pet_level||1)-(a.pet_level||1)));

  html += `<div class="looks-slot-t" style="margin-top:14px">📖 Все питомцы (${roster.length})</div>
    <div class="bk-grid">${roster.map(_zcCard).join('')}</div>`;

  el('zoo-c').innerHTML = html;
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

      const bg     = isCurrent ? 'rgba(232,181,77,.08)' : hasNew && !isCurrent && isUnlocked ? 'rgba(86,196,106,.05)' : 'transparent';
      const border = isCurrent ? '1px solid var(--gold)' : hasNew ? '1px solid rgba(86,196,106,.4)' : '1px solid var(--border2)';

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
          ${!lines.length?`<div style="font-size:10px;color:var(--muted)">—</div>`:''}
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
      : `<div style="font-size:11px;color:var(--muted);padding:5px">Корма нет.
           <button class="btn btn-sm btn-ghost" style="margin-left:6px" onclick="CM();goTo('market','goods')">🛒 Купить корм</button>
         </div>`;

    const body = `
      <!-- Header: чип-стиль Казармы (bk-info-head), рамка модалки по редкости -->
      <div class="r-${p.rarity}" style="text-align:center;padding:10px 0 10px;border-radius:var(--r)">
        <div style="font-size:28px;margin-bottom:6px">${p.name}</div>
        <div class="bk-info-head">
          <span>${rc(p.rarity)}</span>
          <span>${placePill}</span>
        </div>
        <div style="font-size:11px;color:var(--muted);line-height:1.5;max-width:280px;margin:8px auto 0">${p.species_desc||''}</div>
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

function doBuySlot() {
  const price = _zooData && _zooData.slot_next_price;
  if (!price) return _execBuySlot();
  withPaymentSource('diamonds', price, _execBuySlot);
}
function _execBuySlot() {
  api('/zoo/buy-slot',{method:'POST'})
    .then(r=>{toast(r.message||`✅ Слот куплен за ${r.price_paid} 💎!`);_zooData=null;loadZoo();refreshCurrBar();})
    .catch(e=>toast(e,false));
}

// ── Block 5.2: выбор источника оплаты (личный / семейный кошелёк) ───────────────
// Авто-перевод: если выбран семейный — нужная сумма переносится family→личный,
// затем обычная покупка. Не женат → сразу личный, без модалки.
let _pendingPay = null;  // {currency, amount, proceed}
function withPaymentSource(currency, amount, proceed) {
  if (!_profileData || !_profileData.partner) { proceed(); return; }
  _pendingPay = { currency, amount, proceed };
  const icon = {mora:'🪙',diamonds:'💎',dark_mora:'🌑',zarniki:'✨'}[currency] || '';
  OM('💳 Чем оплатить?',
    `<div style="text-align:center;padding:8px 0;color:var(--muted);font-size:12px">К оплате: <b style="color:var(--gold2)">${fmt(amount)} ${icon}</b></div>`,
    [{l:'👤 Личный счёт', c:'btn-gold', f:'paySrc(0)'},
     {l:'💑 Семейный кошелёк', c:'btn-ghost', f:'paySrc(1)'}]);
}
function paySrc(useFamily) {
  const p = _pendingPay; _pendingPay = null; CM();
  if (!p) return;
  if (!useFamily) { p.proceed(); return; }
  api('/marriage/fund', {method:'POST', body:JSON.stringify({currency:p.currency, amount:p.amount})})
    .then(()=>{ toast('💑 Переведено из семейного кошелька'); p.proceed(); })
    .catch(e=>toast(e, false));
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

