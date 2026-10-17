// app.15.js — «🧩 Функции чата», журнал настроек и обслуживание в панели модератора.
// Сервер отдаёт module_catalog/module_globals/settings_audit/timezone, клиент
// только рендерит. Список ключей для сохранения собирается из каталога — новый
// модуль в реестре сам появится в UI и в POST /admin/{chat}/settings.

let _admSettingKeys=[]; // module_* ключи текущего экрана (для saveAdmSettings)

function _globOff(key, s) {
  const g=(s.module_globals||{})[key];
  return g && g.enabled===false ? g : null;
}
function _globOffNote(key, s) {
  const g=_globOff(key, s);
  if(!g) return '';
  const why=g.disabled_reason?`: ${esc(g.disabled_reason)}`:'';
  return `<div class="module-global-off">🌐 Выключено разработчиком — не заработает, пока не включат глобально${why}</div>`;
}

function _moduleRowHtml(m, s, master) {
  const on=!!s[m.key];
  const desc=m.description?`<div class="module-desc">${esc(m.description)}</div>`:'';
  const ico=esc(m.icon||(master?'🚫':'🧩'));
  return `<div class="irow module-row${master?' module-master':''}" style="cursor:pointer" onclick="toggleAdmSetting('${m.key}')">
    <span class="ik"><span class="module-ico">${ico}</span> <b>${esc(m.name||m.key)}</b>${desc}${_globOffNote(m.key,s)}</span>
    <span id="aset-${m.key}" style="color:${on?'var(--green)':'var(--red)'}">${on?'ВКЛ':'ВЫКЛ'}</span>
  </div>`;
}

function chatModulesCardHtml(s) {
  const cat=s.module_catalog||[];
  _admSettingKeys=cat.map(m=>m.key);
  const master=cat.find(m=>m.key==='module_bot');
  const groups=[];
  const byGroup=new Map();
  for(const m of cat) {
    if(m.key==='module_bot') continue;   // мастер-стоп всегда отдельной строкой
    const g=m.group||'other';
    if(!byGroup.has(g)) { byGroup.set(g, []); groups.push(g); }
    byGroup.get(g).push(m);
  }
  // Счётчик группы — «эффективно включено»: локальное ВКЛ не помогает, если
  // модуль выключен разработчиком глобально.
  const groupCards=groups.map(g=>{
    const list=byGroup.get(g);
    const icon=list[0].group_icon||'🧩', name=list[0].group_name||g;
    const on=list.filter(m=>s[m.key]&&!_globOff(m.key,s)).length;
    // Полностью включённая группа свёрнута — экран не превращается в простыню.
    const open=on<list.length?' open':'';
    return `<details class="module-group"${open}>
      <summary><span>${esc(icon)} ${esc(name)}</span>
        <span class="module-group-count${on<list.length?' off':''}">${on}/${list.length}</span></summary>
      ${list.map(m=>_moduleRowHtml(m, s)).join('')}
    </details>`;
  }).join('');
  const auditRows=(s.module_audit||[]);
  const audit=auditRows.length
    ? `<details class="module-audit"><summary>Последние изменения · ${auditRows.length}</summary>${auditRows.map(r=>`<div><span>${r.after_enabled?'↗':'↘'}</span><p><b>${esc(r.module?.name||r.module_key)}</b><small>@${esc(r.actor_name||String(r.actor_id))} · ${fmtUTC(r.created_at)}</small></p><strong>${r.after_enabled?'включён':'выключен'}</strong></div>`).join('')}</details>`
    : '<div class="module-audit-empty">Изменений модулей ещё не было.</div>';
  return `<div class="card module-control-card">
    <div class="card-title">🧩 Функции чата</div>
    <div class="module-control-help">Каждый переключатель — одна механика: выключайте точечно. Изменения сохраняются в журнале.</div>
    ${master?_moduleRowHtml(master, s, true):''}
    ${groupCards}
    ${audit}
  </div>`;
}

// ── Журнал скалярных настроек: ранги, тумблеры, часовой пояс, админ-чат ──────
function _auditVal(v) {
  return (v===null||v===undefined||v==='')?'—':esc(String(v));
}

function chatSettingsAuditCardHtml(s) {
  const rows=s.settings_audit||[];
  return `<div class="card">
    <div class="card-title">📜 История настроек</div>
    ${rows.length
      ? `<details class="module-audit"><summary>Последние изменения · ${rows.length}</summary>${rows.map(r=>`<div><span>✎</span><p><b>${esc(r.label||r.setting_key)}</b><small>@${esc(r.actor_name||String(r.actor_id))} · ${fmtUTC(r.created_at)}</small></p><strong>${_auditVal(r.before_value)} → ${_auditVal(r.after_value)}</strong></div>`).join('')}</details>`
      : '<div class="module-audit-empty">Изменений настроек ещё не было. Сюда попадут ранги, тумблеры, часовой пояс и привязка админ-чата.</div>'}
  </div>`;
}

// ── Часовой пояс (только показ) + сброс к стандарту ──────────────────────────
function chatToolsCardHtml(s) {
  const tz=(typeof s.timezone==='number')?s.timezone:0;
  const label='UTC'+(tz>=0?'+':'')+tz;
  return `<div class="card">
    <div class="card-title">🕓 Часовой пояс и обслуживание</div>
    <div class="irow"><span class="ik">Часовой пояс чата<div class="module-desc">Локальные топы, стрик и квесты сбрасываются по полуночи этого пояса. Меняется в боте: «Настройки чата → 🏆 Активность и время».</div></span><span>${label}</span></div>
    <button class="btn btn-ghost btn-full" style="margin-top:8px" onclick="doAdmReset()">♻️ Вернуть стандартные настройки</button>
  </div>`;
}

function doAdmReset() {
  OM('♻️ Вернуть стандартные настройки?',
    '<div style="text-align:center;padding:12px 0;color:var(--muted)">Модули, пороги рангов и тумблеры вернутся к заводским значениям. Каждое изменение попадёт в журнал.<div style="font-size:11px;margin-top:6px">Действие не отменить.</div></div>',
    [{l:'Да, вернуть',c:'btn-gold',f:'_execAdmReset()'},{l:'Отмена',c:'btn-ghost',f:'CM()'}]);
}
function _execAdmReset() {
  api(`/admin/${_adminChatId}/settings/reset`,{method:'POST'})
    .then(r=>{CM();toast(`♻️ Стандарт: модулей ${r.modules_changed||0}, настроек ${r.settings_changed||0}`);loadAdminSettings();})
    .catch(e=>toast(e,false));
}
