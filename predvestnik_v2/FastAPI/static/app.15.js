// app.15.js — «🧩 Функции чата» в панели модератора: карточка по реестру модулей.
// Сервер отдаёт module_catalog (группы + описание), клиент только рендерит.
// Список ключей для сохранения собирается из каталога — новый модуль в реестре
// сам появится в UI и в POST /admin/{chat}/settings.

let _admSettingKeys=[]; // module_* ключи текущего экрана (для saveAdmSettings)

function _moduleRowHtml(m, s) {
  const on=!!s[m.key];
  const desc=m.description?`<div class="module-desc">${esc(m.description)}</div>`:'';
  return `<div class="irow module-row" style="cursor:pointer" onclick="toggleAdmSetting('${m.key}')">
    <span class="ik"><span class="module-ico">${esc(m.icon||'🧩')}</span> <b>${esc(m.name||m.key)}</b>${desc}</span>
    <span id="aset-${m.key}" style="color:${on?'var(--green)':'var(--red)'}">${on?'ВКЛ':'ВЫКЛ'}</span>
  </div>`;
}

function _moduleMasterRowHtml(m, s) {
  const on=!!s[m.key];
  const desc=m.description?`<div class="module-desc">${esc(m.description)}</div>`:'';
  return `<div class="irow module-row module-master" style="cursor:pointer" onclick="toggleAdmSetting('${m.key}')">
    <span class="ik"><span class="module-ico">${esc(m.icon||'🚫')}</span> <b>${esc(m.name||m.key)}</b>${desc}</span>
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
  const groupCards=groups.map(g=>{
    const list=byGroup.get(g);
    const icon=list[0].group_icon||'🧩', name=list[0].group_name||g;
    const on=list.filter(m=>s[m.key]).length;
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
    ${master?_moduleMasterRowHtml(master, s):''}
    ${groupCards}
    ${audit}
  </div>`;
}
