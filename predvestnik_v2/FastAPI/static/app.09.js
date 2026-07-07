// ── БП: редактор наград (Block 6) ──────────────────────────────────────────────
function _parseBpItems(s) {
  // "food_basic:2, spin_token:1" → [["food_basic",2],["spin_token",1]]
  return (s||'').split(',').map(p=>p.trim()).filter(Boolean).map(p=>{
    const [id,q]=p.split(':').map(x=>x.trim());
    return [id, parseInt(q||'1')||1];
  });
}
function _parseBpOption(s) {
  // "мора;алмазы;предметы;тема" → {mora,diamonds,items,theme}
  const [m,d,it,th]=(s||'').split(';');
  return {mora:parseInt(m||'0')||0, diamonds:parseInt(d||'0')||0,
          items:_parseBpItems(it), theme:(th||'').trim()||null};
}
function devBpRewardSet() {
  const season=_bpSeason; if(!season) return toast('Выбери сезон над таблицей',false);
  const level=parseInt(el('dev-br-level')?.value||'0');
  const track=el('dev-br-track')?.value;
  if(!level) return toast('Укажите уровень',false);
  const body={season_id:season, level, track,
    mora:parseInt(el('dev-br-mora')?.value||'0')||0,
    diamonds:parseInt(el('dev-br-dia')?.value||'0')||0,
    items:_parseBpItems(el('dev-br-items')?.value),
    theme_id:(el('dev-br-theme')?.value||'').trim()||null};
  if(el('dev-br-choice')?.checked){
    const opt1={mora:body.mora,diamonds:body.diamonds,items:body.items,theme:body.theme_id};
    const opt2=_parseBpOption(el('dev-br-opt2')?.value);
    body.reward_options=[opt1,opt2];
  }
  api('/admin/dev/bp/rewards',{method:'POST',body:JSON.stringify(body)})
    .then(()=>{toast(`💾 Ур.${level} (${track}) сохранён`);loadBpTable();})
    .catch(e=>toast(e,false));
}
function devBpRewardReset() {
  const season=_bpSeason; if(!season) return toast('Выбери сезон над таблицей',false);
  const level=parseInt(el('dev-br-level')?.value||'0');
  const track=el('dev-br-track')?.value;
  if(!level) return toast('Укажите уровень',false);
  api(`/admin/dev/bp/rewards/${season}/${level}/${track}`,{method:'DELETE'})
    .then(()=>{toast('↩ Сброшено к registry');loadBpTable();})
    .catch(e=>toast(e,false));
}
function devBpBulk() {
  if(!_bpSeason) return toast('Выбери сезон над таблицей',false);
  const body={season_id:_bpSeason,
    track:el('dev-bk-track')?.value,
    level_from:parseInt(el('dev-bk-from')?.value||'0'),
    level_to:parseInt(el('dev-bk-to')?.value||'0'),
    mora_base:parseInt(el('dev-bk-mora')?.value||'0')||0,
    mora_step:parseInt(el('dev-bk-mstep')?.value||'0')||0,
    diamonds_base:parseInt(el('dev-bk-dia')?.value||'0')||0, diamonds_step:0};
  if(!body.level_from||!body.level_to) return toast('Укажите диапазон',false);
  api('/admin/dev/bp/rewards/bulk',{method:'POST',body:JSON.stringify(body)})
    .then(r=>{toast(`⚙️ Заполнено уровней: ${r.updated}`);loadBpTable();})
    .catch(e=>toast(e,false));
}
function devBpDistribute() {
  if(!_bpSeason) return toast('Выбери сезон над таблицей',false);
  const body={season_id:_bpSeason,
    track:el('dev-ds-track')?.value||'free',
    level_from:parseInt(el('dev-ds-from')?.value||'0'),
    level_to:parseInt(el('dev-ds-to')?.value||'0'),
    total_mora:parseInt(el('dev-ds-mora')?.value||'0')||0,
    total_diamonds:parseInt(el('dev-ds-dia')?.value||'0')||0,
    curve:el('dev-ds-curve')?.value||'linear'};
  if(!body.level_from||!body.level_to) return toast('Укажите диапазон',false);
  if(!body.total_mora&&!body.total_diamonds) return toast('Укажите пул моры и/или алмазов',false);
  api('/admin/dev/bp/rewards/distribute',{method:'POST',body:JSON.stringify(body)})
    .then(r=>{toast(`🎲 Раскидано на ${r.updated} ур. (🪙${fmt(body.total_mora)} · 💎${fmtF(body.total_diamonds)})`);loadBpTable();})
    .catch(e=>toast(e,false));
}
// XP-конструктор БП (B+A): вес/дневной потолок/вкл-выкл за каждое действие.
let _bpXpLabels={};
function loadBpXpActions() {
  const box=el('dev-bpxp-list'); if(!box) return;
  box.innerHTML='<div class="loader">Загрузка...</div>';
  api('/admin/dev/bp/xp-actions').then(d=>{
    const acts=d.actions||[]; const per=d.xp_per_level||100;
    _bpXpLabels={}; acts.forEach(a=>{ _bpXpLabels[a.metric]=a.label; });
    const wbi=el('dev-bpxp-weekend'); if(wbi) wbi.value=d.weekend_boost_pct||0;
    const perLvlEl=el('dev-bpxp-perlevel'); if(perLvlEl) perLvlEl.textContent=`${per} XP = 1 уровень.`;
    if(!acts.length){ box.innerHTML='<div style="font-size:11px;color:var(--muted)">Нет действий.</div>'; return; }
    box.innerHTML=acts.map(a=>{
      const cap=a.daily_cap||0;
      const note=cap>0?`потолок ${cap} XP/день (≈${(cap/per).toFixed(1)} ур./д)`:'без дневного лимита';
      return `<div class="bpxp-row" style="${a.enabled?'':'opacity:.5'}">
        <div class="bpxp-head"><b>${esc(a.label)}</b> ${a.is_override?'🔧':''}<span class="bpxp-metric">${esc(a.metric)}</span></div>
        <div class="bpxp-ctrls">
          <label>XP<input type="number" id="bpxp-w-${a.metric}" class="num-input bpxp-in" value="${a.weight}"/></label>
          <label>лимит/д<input type="number" id="bpxp-c-${a.metric}" class="num-input bpxp-in" value="${cap}" title="0 = без лимита"/></label>
          <label class="bpxp-tog"><input type="checkbox" id="bpxp-e-${a.metric}" ${a.enabled?'checked':''}/>вкл</label>
          <button class="btn btn-sm btn-gold" onclick="devBpXpRowSave('${a.metric}')">💾</button>
          ${a.is_override?`<button class="btn btn-sm btn-red" onclick="devBpXpReset('${a.metric}')">↩</button>`:''}
        </div>
        <div class="bpxp-note">${note}</div>
      </div>`;
    }).join('');
  }).catch(e=>{ box.innerHTML=`<div class="err">${e}</div>`; });
}
function devBpXpRowSave(metric) {
  const weight=parseInt(el('bpxp-w-'+metric)?.value||'0')||0;
  const cap=parseInt(el('bpxp-c-'+metric)?.value||'0')||0;
  const enabled=!!el('bpxp-e-'+metric)?.checked;
  const label=_bpXpLabels[metric]||null;
  api('/admin/dev/bp/xp-weight',{method:'POST',body:JSON.stringify({metric,weight,enabled,daily_cap:cap,label})})
    .then(()=>{toast(`💾 ${metric}: ${weight} XP${cap?(' · ≤'+cap+'/д'):''}${enabled?'':' · ВЫКЛ'}`);loadBpXpActions();})
    .catch(e=>toast(e,false));
}
function devBpXpReset(metric) {
  api('/admin/dev/bp/xp-weight/reset',{method:'POST',body:JSON.stringify({metric})})
    .then(()=>{toast('↩ '+metric+' → дефолт');loadBpXpActions();})
    .catch(e=>toast(e,false));
}
function devBpXpSet() {
  const metric=(el('dev-bpxp-metric')?.value||'').trim().toLowerCase();
  if(!/^[a-z0-9_]{1,40}$/.test(metric)) return toast('metric: a-z, 0-9, _ (до 40)',false);
  const weight=parseInt(el('dev-bpxp-weight')?.value||'0')||0;
  const cap=parseInt(el('dev-bpxp-cap')?.value||'0')||0;
  const label=(el('dev-bpxp-label')?.value||'').trim()||null;
  api('/admin/dev/bp/xp-weight',{method:'POST',body:JSON.stringify({metric,weight,enabled:true,daily_cap:cap,label})})
    .then(()=>{toast('💾 Действие сохранено: '+metric);
      ['dev-bpxp-metric','dev-bpxp-label','dev-bpxp-weight','dev-bpxp-cap'].forEach(id=>{const e2=el(id);if(e2)e2.value='';});
      loadBpXpActions();})
    .catch(e=>toast(e,false));
}
function devBpWeekendSet(){
  const pct=parseInt(el('dev-bpxp-weekend')?.value||'0')||0;
  api('/admin/dev/bp/weekend-boost',{method:'POST',body:JSON.stringify({pct})})
    .then(()=>{toast(pct>0?`⚡ Weekend boost: +${pct}% XP по выходным`:'⚡ Weekend boost выключен');loadBpXpActions();})
    .catch(e=>toast(e,false));
}
function devBpShowExample() {
  const example = {
    season_id: _bpSeason || 's1',
    rewards: [
      {level:1, track:"free", mora:500},
      {level:1, track:"paid", diamonds:5, items:[["spin_token",2]]},
      {level:2, track:"free", items:[["food_basic",3]]},
      {level:2, track:"paid", mora:0, diamonds:0, theme_id:"theme_id_необяз"},
      {level:3, track:"paid", reward_options:[{mora:1000},{diamonds:5,items:[["spin_token",1]]}]}
    ]
  };
  const ta=el('dev-bp-json');
  if(ta && !ta.value.trim()) ta.value=JSON.stringify(example, null, 2);
  el('dev-bp-import-out').innerHTML='<div style="color:var(--muted)">Поля каждого элемента: <code>level</code>, <code>track</code> (free/paid), и любые из: <code>mora</code>, <code>diamonds</code>, <code>items</code>:[[id,кол-во]], <code>theme_id</code>, <code>reward_options</code>:[{...},{...}] (выбор из вариантов). <b>Сезон берётся из селектора над таблицей</b> (season_id в JSON игнорируется).</div>';
}
function devBpImport() {
  const raw=(el('dev-bp-json')?.value||'').trim();
  if(!raw) return toast('Вставьте JSON', false);
  let data;
  try { data=JSON.parse(raw); }
  catch(e){ el('dev-bp-import-out').innerHTML='<div class="err">Невалидный JSON: '+esc(''+e)+'</div>'; return; }
  if(!_bpSeason){ el('dev-bp-import-out').innerHTML='<div class="err">Сначала выбери сезон над таблицей.</div>'; return; }
  // Импорт ВСЕГДА в выбранный сезон (season_id из JSON игнорируем) — чтобы таблица
  // сразу показала результат, а не «ничего не произошло».
  const rewards = Array.isArray(data) ? data : (data.rewards || []);
  if(!Array.isArray(rewards) || !rewards.length) return toast('rewards пуст или не массив', false);
  const body = {season_id: _bpSeason, rewards};
  el('dev-bp-import-out').innerHTML='<div style="color:var(--muted)">Импортирую…</div>';
  api('/admin/dev/bp/rewards/import',{method:'POST',body:JSON.stringify(body)})
    .then(r=>{
      const errs=(r.errors||[]);
      el('dev-bp-import-out').innerHTML=
        `<div style="color:var(--green)">✅ В сезон «${esc(_bpSeason)}» импортировано: ${r.imported}${errs.length?' · ⚠ пропущено: '+errs.length:''}</div>`+
        (errs.length?`<div style="color:var(--red);font-size:9px;margin-top:2px">${errs.map(esc).join('<br>')}</div>`:'');
      loadBpTable();
    })
    .catch(e=>{el('dev-bp-import-out').innerHTML=`<div class="err">${e}</div>`;});
}
function devBpSummary() {
  api('/admin/dev/bp/season-summary').then(d=>{
    const f=d.summary.free, p=d.summary.paid;
    el('dev-bp-out').innerHTML=
      `📊 Сезон <b>${d.season_id||'—'}</b><br>`+
      `🆓 ${fmt(f.mora)}🪙 · ${f.diamonds}💎 · ${f.items} предм.<br>`+
      `👑 ${fmt(p.mora)}🪙 · ${p.diamonds}💎 · ${p.items} предм.<br>`+
      (d.empty_levels.length?`⚠️ Пустые уровни: ${d.empty_levels.join(', ')}`:'✅ Все уровни заполнены');
  }).catch(e=>toast(e,false));
}
function devBpCopy() {
  const from=el('dev-cp-from')?.value.trim(), to=el('dev-cp-to')?.value.trim();
  if(!from||!to) return toast('Укажите оба сезона',false);
  api('/admin/dev/bp/rewards/copy',{method:'POST',body:JSON.stringify({from_season:from,to_season:to})})
    .then(r=>{
      toast(`📋 Скопировано наград: ${r.copied} → «${to}»`);
      _bpSeason=to;
      const sel=el('dev-bp-season-sel'); if(sel) sel.value=to;
      const sf=el('dev-br-season'); if(sf) sf.value=to;
      loadBpTable();
    })
    .catch(e=>toast(e,false));
}
function devLoadSeasons() {
  api('/admin/dev/bp/seasons').then(d=>{
    const rows=d.seasons||[];
    const frozen=!!d.frozen;
    const freezeBar=`<div class="dev-freeze-bar${frozen?' on':''}">
      <span>${frozen?'❄️ <b>БП ЗАМОРОЖЕН</b> — XP и награды приостановлены у всех':'🟢 БП активен'}</span>
      <button class="btn btn-sm ${frozen?'btn-gold':'btn-ghost'}" onclick="devToggleBpFreeze(${frozen?'false':'true'})">${frozen?'Разморозить':'❄️ Заморозить'}</button>
    </div>`;
    el('dev-seasons').innerHTML=freezeBar+(rows.length?rows.map(s=>`
      <div class="irow">
        <span class="ik">${s.active?'🟢 ':''}${esc(s.label)} <span style="color:var(--dim)">(${s.id}, ${s.source})</span></span>
        <span class="iv" style="font-size:10px;display:flex;align-items:center;gap:6px">${s.starts_at} → ${s.ends_at}
          <button class="btn btn-sm btn-ghost" style="padding:2px 6px" onclick='devEditSeason(${JSON.stringify(s.id)},${JSON.stringify(s.label)},${JSON.stringify(s.starts_at)},${JSON.stringify(s.ends_at)})'>✏️</button>
          ${s.source==='db'?`<button class="btn btn-sm btn-ghost" style="padding:2px 6px" onclick='devDeleteSeason(${JSON.stringify(s.id)})'>🗑</button>`:''}
        </span>
      </div>`).join(''):'<div style="font-size:11px;color:var(--muted)">Сезонов нет</div>');
  }).catch(e=>{el('dev-seasons').innerHTML=`<div class="err">${e}</div>`;});
}
function devToggleBpFreeze(frozen) {
  api('/admin/dev/bp/freeze',{method:'POST',body:JSON.stringify({frozen})})
    .then(r=>{toast(r.frozen?'❄️ БП заморожен':'🟢 БП разморожен');devLoadSeasons();})
    .catch(e=>toast(e,false));
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
  OM('🗑 Удалить сезон?',`<div style="text-align:center;padding:12px 0;color:var(--muted)">Сезон <b>${esc(id)}</b> будет удалён из БД <b>вместе с</b> его переопределениями наград и прогрессом игроков этого сезона (каскад — без сирот).</div>`,
    [{l:'Удалить',c:'btn-red',f:`_execDevDeleteSeason('${id}')`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execDevDeleteSeason(id) {
  api(`/admin/dev/bp/seasons/${encodeURIComponent(id)}`,{method:'DELETE'})
    .then(r=>{
      toast(r.reverted_to_registry
        ? `⚠️ Оверрайд удалён — «${id}» зашит в коде (registry), сезон откатился к дефолтным датам из кода, а не исчез`
        : '🗑 Удалён');
      CM();devLoadSeasons();
    })
    .catch(e=>toast(e,false));
}
let _bcCounts=null;
const _BC_AUD_LABEL={main:'🏠 основные',admin:'🛡 админки',main_admin:'🏠+🛡 основные и админки',
  dm_admin:'✉️+🛡 ЛС и админки',dm:'✉️ ЛС',all:'🌐 все чаты'};
function _bcLoadCounts() {
  api('/admin/dev/broadcast/audience-counts').then(d=>{ _bcCounts=d; _bcPreview(); }).catch(()=>{});
}
function _bcPreview() {
  const aud=el('dev-bc-audience')?.value||'main';
  const cEl=el('dev-bc-count');
  if(cEl){
    const n=_bcCounts?_bcCounts[aud]:null;
    cEl.innerHTML=n==null?'Получателей: …':`📨 Получат: <b>${n}</b> чат(ов) · ${_BC_AUD_LABEL[aud]||aud}`;
  }
  const pv=el('dev-bc-preview');
  if(pv){
    const t=(el('dev-bc-text')?.value||'').trim();
    pv.innerHTML=t?t:'<span style="color:var(--muted)">—</span>';
  }
}
function devBroadcastTest() {
  // admin_audit C2: проверка форматирования на себе до массовой отправки
  const text=el('dev-bc-text')?.value.trim();
  if(!text) return toast('Введите текст',false);
  api('/admin/dev/broadcast/test',{method:'POST',body:JSON.stringify({text,audience:'dm'})})
    .then(()=>toast('🧪 Отправлено вам в ЛС — проверьте разметку'))
    .catch(e=>toast(e,false));
}
function devBroadcast() {
  const text=el('dev-bc-text')?.value.trim();
  if(!text) return toast('Введите текст',false);
  const aud=el('dev-bc-audience')?.value||'main';
  const n=_bcCounts?_bcCounts[aud]:'?';
  OM('📢 Отправить рассылку?',
    `<div style="padding:10px 0;color:var(--muted)">Аудитория: <b>${esc(_BC_AUD_LABEL[aud]||aud)}</b><br>Получателей: <b style="color:var(--gold2)">${n}</b> чат(ов).<br><span style="color:var(--red)">Отменить нельзя.</span></div>
     <div class="bc-preview" style="margin-top:4px">${text}</div>`,
    [{l:'Отправить',c:'btn-red',f:'_execDevBroadcast()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execDevBroadcast() {
  const text=el('dev-bc-text')?.value.trim();
  const audience=el('dev-bc-audience')?.value||'main';
  CM(); toast('📢 Отправляю...');
  api('/admin/dev/broadcast',{method:'POST',body:JSON.stringify({text,audience})})
    .then(r=>toast(`📢 Отправлено: ${r.sent}/${r.total}${r.failed?' (ошибок: '+r.failed+')':''}`))
    .catch(e=>toast(e,false));
}
function devRunSql() {
  const q=el('dev-sql')?.value.trim();
  if(!q) return toast('Введите запрос',false);
  OM('🖥 Выполнить SQL?',`<div style="font-family:monospace;font-size:11px;padding:8px;background:var(--dim);border-radius:6px;word-break:break-all">${esc(q.slice(0,300))}</div>`,
    [{l:'Выполнить',c:'btn-red',f:'_execDevSql()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execDevSql(confirmed) {
  const q=el('dev-sql')?.value.trim();
  CM();
  api('/admin/dev/sql',{method:'POST',body:JSON.stringify({query:q,confirm:!!confirmed})}).then(r=>{
    // admin_audit A1: мутация требует второго подтверждения + журналируется
    if(r.needs_confirm){
      OM('⚠️ Запрос ИЗМЕНЯЕТ данные',
        `<div style="padding:8px 0;color:var(--muted);font-size:12px">${esc(r.notice||'')}</div>
         <div style="font-family:monospace;font-size:11px;padding:8px;background:var(--dim);border-radius:6px;word-break:break-all">${esc(q.slice(0,300))}</div>`,
        [{l:'Выполнить и записать в журнал',c:'btn-red',f:'_execDevSql(true)'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
      return;
    }
    if(!r.rows||!r.rows.length){
      el('dev-sql-result').innerHTML=`<div style="font-size:11px;color:var(--green)">✅ OK${r.count?` (строк: ${r.count})`:''}${r.logged?' · записано в журнал':''}</div>`;
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
let _devTLVars=[];
let _devTLVarHelp=[];
function _devTLOptionsHTML(templates) {
  const groups={premium:[],basic:[]};
  templates.forEach(t=>(groups[t.kind||'basic']||groups.basic).push(t));
  const opt=t=>`<option value="${t.template_id}">${esc(t.name)}${t.has_override?' ✏️':''}</option>`;
  let html='';
  if(groups.premium.length) html+=`<optgroup label="✨ Премиум">${groups.premium.map(opt).join('')}</optgroup>`;
  if(groups.basic.length) html+=`<optgroup label="🎨 Обычные">${groups.basic.map(opt).join('')}</optgroup>`;
  return html;
}
function devTLInit() {
  api('/admin/dev/theme-templates').then(d=>{
    _devThemeTemplates=d.templates||[];
    const sel=el('dev-tl-template');
    if(!sel) return;
    sel.innerHTML=_devTLOptionsHTML(_devThemeTemplates);
    if(_devThemeTemplates.length) devTLLoad();
  }).catch(e=>{el('dev-tl-status').innerHTML=`<div class="err">${e}</div>`;});
  el('dev-tl-vars')?.addEventListener('click', e=>{
    const chip=e.target.closest('.tl-chip');
    if(chip) _devTLInsertVar(chip.dataset.v);
  });
}
function _devTLRefreshBadges() {
  const sel=el('dev-tl-template'); const cur=sel?.value;
  api('/admin/dev/theme-templates').then(d=>{
    _devThemeTemplates=d.templates||[];
    if(!sel) return;
    sel.innerHTML=_devTLOptionsHTML(_devThemeTemplates);
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
    _devTLVars=d.variables||[];
    _devTLVarHelp=d.var_help||[];
    el('dev-tl-vars').innerHTML=_devTLVars.length
      ?'<span class="tl-chips-label">Теги (клик — вставить):</span> '+_devTLVars.map(v=>`<span class="tl-chip" data-v="${esc(v)}">{${esc(v)}}</span>`).join('')
        +' <span class="tl-chip-help" onclick="devTLVarHelp()">ℹ️ что выводит каждый</span>'
      :'<span style="color:var(--muted);font-size:11px">Нет переменных</span>';
    el('dev-tl-status').innerHTML=d.has_override
      ?'<span style="color:var(--gold)">✏️ Сохранён кастомный вариант</span>'
      :'<span style="color:var(--muted)">Дефолтный шаблон (из кода)</span>';
    _devTLUpdateLinenos();
    _devTLStats();
  }).catch(e=>{el('dev-tl-status').innerHTML=`<div class="err">${e}</div>`;});
}
function devTLVarHelp() {
  const rows=(_devTLVarHelp.length?_devTLVarHelp:_devTLVars.map(v=>({name:v,desc:''})));
  const body=`<div style="max-height:55vh;overflow-y:auto">
    <div style="font-size:11px;color:var(--muted);margin-bottom:8px">Клик по тегу в списке выше вставляет его в шаблон. Ниже — что выводит каждый.</div>
    ${rows.map(r=>`<div class="tl-help-row" onclick="_devTLInsertVar(${JSON.stringify(r.name)});CM()">
      <code class="tl-help-tag">{${esc(r.name)}}</code>
      <span class="tl-help-desc">${esc(r.desc||'—')}</span></div>`).join('')}
  </div>`;
  OM('🏷 Справка по тегам',body,[{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}
function _devTLInsertVar(name) {
  const ta=el('dev-tl-text'); if(!ta) return;
  const token=`{${name}}`;
  const start=ta.selectionStart??ta.value.length;
  const end=ta.selectionEnd??start;
  ta.value=ta.value.slice(0,start)+token+ta.value.slice(end);
  const pos=start+token.length;
  ta.focus(); ta.setSelectionRange(pos,pos);
  _devTLStats();
}
function _devTLUpdateLinenos() {
  const ta=el('dev-tl-text');
  const ln=el('dev-tl-linenos');
  if(!ta||!ln) return;
  const count=(ta.value.match(/\n/g)||[]).length+1;
  // Build line numbers — overLines will be filled by _devTLStats
  if(!_devTLOverLines) {
    ln.textContent=Array.from({length:count},(_,i)=>i+1).join('\n');
  } else {
    ln.innerHTML=Array.from({length:count},(_,i)=>{
      const n=i+1;
      return _devTLOverLines.has(n)?`<span class="tl-ln-over">${n}</span>`:n;
    }).join('\n');
  }
  _devTLSyncScroll();
}
function _devTLSyncScroll() {
  const ta=el('dev-tl-text');
  const ln=el('dev-tl-linenos');
  if(ta&&ln) ln.scrollTop=ta.scrollTop;
}
let _devTLOverLines=null;
function _devTLStats() {
  const text=el('dev-tl-text')?.value??'';
  const lines=text.split('\n');
  const deviceW=parseInt(el('dev-tl-device')?.value||'390',10);
  const fontPx=parseFloat(el('dev-tl-fontsize')?.value||'16');
  const innerW=deviceW-48;
  const maxChars=Math.max(8,Math.floor(innerW/(fontPx*0.6)));
  let longest=0, longestLine=0;
  const overNums=[];
  lines.forEach((line,i)=>{
    const len=[...line].length;
    if(len>longest){longest=len;longestLine=i+1;}
    if(len>maxChars) overNums.push(i+1);
  });
  _devTLOverLines=overNums.length?new Set(overNums):null;
  _devTLUpdateLinenos();
  const overHtml=overNums.length
    ?`<span style="color:var(--red)">⚠ стр. ${overNums.join(', ')} длиннее ≈${maxChars} симв. — могут не влезть</span>`
    :`<span style="color:var(--green)">✓ влезает (≈${maxChars} симв./стр.)</span>`;
  const used=new Set();
  text.replace(/\{([^{}\n]+)\}/g,(_,name)=>{used.add(name);return '';});
  const unknown=[...used].filter(v=>!_devTLVars.includes(v));
  const typoHtml=unknown.length
    ?`<br><span style="color:var(--red)">❓ неизвестные плейсхолдеры: ${unknown.map(v=>`{${esc(v)}}`).join(', ')}</span>`
    :'';
  el('dev-tl-stats').innerHTML=`Макс. длина: ${longest} симв. (стр. ${longestLine}). ${overHtml}${typoHtml}`;
}
function _devTLCopy() {
  const text=el('dev-tl-text')?.value??'';
  navigator.clipboard?.writeText(text)
    .then(()=>toast('📋 Скопировано!'))
    .catch(()=>toast('Буфер обмена недоступен',false));
}
function _devTLApplyFrame() {
  const w=el('dev-tl-device')?.value||'390';
  const fontPx=parseFloat(el('dev-tl-fontsize')?.value||'16');
  const frame=el('dev-tl-frame');
  if(frame){ frame.style.width=w+'px'; frame.style.setProperty('--tl-fs',fontPx+'px'); }
  const lbl=el('dev-tl-fontsize-val'); if(lbl) lbl.textContent=fontPx+'px';
  _devTLStats();
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
function devTLSendTest() {
  const tid=el('dev-tl-template')?.value;
  const text=el('dev-tl-text')?.value??'';
  if(!tid||!text.trim()) return toast('Пустой шаблон',false);
  toast('📤 Отправляю...');
  api(`/admin/dev/theme-templates/${tid}/send-test`,{method:'POST',body:JSON.stringify({raw_text:text})})
    .then(()=>toast('✅ Отправлено себе в Telegram — проверь чат с ботом'))
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

// ── Theme Lab: Редактор метаданных темы ──────────────────────────────────────
function devTLMetaLoad() {
  const tid=el('dev-tl-template')?.value; if(!tid){toast('Выберите тему',false);return;}
  api(`/admin/dev/theme-meta/${tid}`).then(d=>{
    el('dev-tl-meta-tid').value=tid;
    el('dev-tl-meta-name').value=d.name||'';
    el('dev-tl-meta-rarity').value=d.rarity||'common';
    el('dev-tl-meta-source').value=d.source||'';
    el('dev-tl-meta-pmora').value=d.price_mora||'';
    el('dev-tl-meta-pdia').value=d.price_diamonds||'';
    el('dev-tl-meta-pzar').value=d.price_zarniki||'';
    el('dev-tl-meta-pdark').value=d.price_dark||'';
    el('dev-tl-meta-bp').checked=!!d.obtainable_bp;
    el('dev-tl-meta-desc').value=d.desc||'';
    el('dev-tl-meta-form').style.display='';
    el('dev-tl-meta-status').textContent=d.has_override?'📝 Оверрайд в БД активен':'💡 Значения из кода (themes.py)';
  }).catch(e=>toast(e,false));
}
function devTLMetaSave() {
  const tid=el('dev-tl-meta-tid')?.value; if(!tid) return;
  const body={
    name:el('dev-tl-meta-name').value||null,
    rarity:el('dev-tl-meta-rarity').value||null,
    source:el('dev-tl-meta-source').value||null,
    price_mora:parseInt(el('dev-tl-meta-pmora').value)||null,
    price_diamonds:parseFloat(el('dev-tl-meta-pdia').value)||null,
    price_zarniki:parseInt(el('dev-tl-meta-pzar').value)||null,
    price_dark:parseInt(el('dev-tl-meta-pdark').value)||null,
    obtainable_bp:el('dev-tl-meta-bp').checked,
    desc:el('dev-tl-meta-desc').value||null,
  };
  api(`/admin/dev/theme-meta/${tid}`,{method:'POST',body:JSON.stringify(body)})
    .then(()=>{toast('💾 Метаданные сохранены');el('dev-tl-meta-status').textContent='✅ Сохранено в БД';})
    .catch(e=>toast(e,false));
}
function devTLMetaDelete() {
  const tid=el('dev-tl-meta-tid')?.value; if(!tid) return;
  api(`/admin/dev/theme-meta/${tid}`,{method:'DELETE'})
    .then(()=>{toast('🗑 Метаданные сброшены');el('dev-tl-meta-status').textContent='💡 Сброшено к themes.py';})
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

// ── 🎟 Промокоды в дев-консоли (admin_audit B6) ──────────────────────────────
function devPromoLoad() {
  const box=el('dev-promo-list'); if(!box) return;
  api('/admin/dev/promocodes').then(d=>{
    const rows=d.promocodes||[];
    if(!rows.length){ box.innerHTML='<div style="font-size:11px;color:var(--muted)">Промокодов пока нет — создайте первый ниже.</div>'; return; }
    box.innerHTML=rows.map(p=>{
      const lim=p.max_activations>0?`${p.activations_count}/${p.max_activations}`:`${p.activations_count}/∞`;
      const on=p.is_active?'🟢':'🔴';
      const until=p.valid_until?` · до ${esc(p.valid_until)}`:'';
      return `<div style="display:flex;align-items:center;gap:6px;padding:5px 0;border-bottom:1px solid var(--dim);font-size:11px">
        <span style="cursor:pointer" onclick="devPromoInfo('${esc(p.code)}')">${on} <b>${esc(p.code)}</b></span>
        <span style="color:var(--muted);flex:1">${lim}${until}</span>
        <button class="btn btn-sm btn-ghost" style="padding:2px 8px" onclick="devPromoToggle('${esc(p.code)}')">${p.is_active?'⏸':'▶'}</button>
        <button class="btn btn-sm btn-ghost" style="padding:2px 8px;color:var(--red)" onclick="devPromoDelete('${esc(p.code)}')">🗑</button>
      </div>`;
    }).join('');
  }).catch(e=>{box.innerHTML=`<div class="err">${e}</div>`;});
}
function devPromoInfo(code) {
  api('/admin/dev/promocodes/'+encodeURIComponent(code)).then(d=>{
    const p=d.promocode||{};
    const rw=[p.reward_mora>0?`${p.reward_mora} 🪙`:'',p.reward_diamonds>0?`${p.reward_diamonds} 💎`:'',
      p.reward_dark_mora>0?`${p.reward_dark_mora} 🌑`:'',p.reward_zarniki>0?`${p.reward_zarniki} ✨`:'',
      p.reward_items_json&&p.reward_items_json!=='{}'?esc(p.reward_items_json):''].filter(Boolean).join(' · ')||'—';
    const acts=(d.activators||[]).map(a=>`<div style="font-size:10px;color:var(--muted)">${esc(a.username||a.user_id)} — ${esc(a.redeemed_at||'')}</div>`).join('')||'<div style="font-size:10px;color:var(--muted)">Активаций нет</div>';
    OM('🎟 '+esc(code),
      `<div style="font-size:12px;padding:6px 0">${esc(p.description||'без описания')}</div>
       <div style="font-size:11px">Награда: ${rw}</div>
       <div style="font-size:11px;color:var(--muted);margin:4px 0">Активации: ${p.activations_count}${p.max_activations>0?'/'+p.max_activations:'/∞'} · ${p.is_active?'🟢 активен':'🔴 выключен'}</div>
       <div style="border-top:1px solid var(--dim);margin-top:6px;padding-top:6px;max-height:150px;overflow:auto">${acts}</div>`,
      [{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
  }).catch(e=>toast(e,false));
}
function devPromoToggle(code) {
  api('/admin/dev/promocodes/'+encodeURIComponent(code)+'/toggle',{method:'POST'})
    .then(r=>{toast(r.is_active?'▶ Промокод включён':'⏸ Промокод выключен');devPromoLoad();})
    .catch(e=>toast(e,false));
}
function devPromoDelete(code) {
  OM('🗑 Удалить промокод?',`<div style="padding:8px 0;color:var(--muted)">Код <b>${esc(code)}</b> будет удалён навсегда (история активаций останется в журнале).</div>`,
    [{l:'Удалить',c:'btn-red',f:`_devPromoDeleteGo('${esc(code)}')`},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _devPromoDeleteGo(code) {
  CM();
  api('/admin/dev/promocodes/'+encodeURIComponent(code),{method:'DELETE'})
    .then(()=>{toast('🗑 Удалён');devPromoLoad();}).catch(e=>toast(e,false));
}
function devPromoCreate() {
  const code=el('dev-promo-code')?.value.trim();
  if(!code) return toast('Введите код',false);
  const items={};
  (el('dev-promo-items')?.value||'').split(',').forEach(pair=>{
    const m=pair.trim().split(':');
    if(m.length===2&&m[0].trim()&&parseInt(m[1],10)>0) items[m[0].trim()]=parseInt(m[1],10);
  });
  const body={
    code, description:el('dev-promo-desc')?.value.trim()||'',
    mora:parseFloat(el('dev-promo-mora')?.value)||0,
    diamonds:parseFloat(el('dev-promo-dia')?.value)||0,
    dark_mora:parseFloat(el('dev-promo-dark')?.value)||0,
    zarniki:parseFloat(el('dev-promo-zar')?.value)||0,
    items, max_activations:parseInt(el('dev-promo-max')?.value,10)||0,
    valid_until:el('dev-promo-until')?.value.trim()||null,
  };
  api('/admin/dev/promocodes',{method:'POST',body:JSON.stringify(body)})
    .then(r=>{toast('🎟 Создан: '+r.code);['code','desc','mora','dia','dark','zar','items','max','until'].forEach(s=>{const i=el('dev-promo-'+s);if(i)i.value='';});devPromoLoad();})
    .catch(e=>toast(e,false));
}
