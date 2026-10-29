// ── Лента действий и очередь жалоб ──────────────────────────────────────────
// Отдельный файл: admin.js вырос с людьми и карточками. Загружается после
// admin.js (общие помощники) и до admin-boot.js (старт приложения).
// ── Журнал: все действия персонала ───────────────────────────────────────────

const JOURNAL = {kind: PREFS.get('journal.kind', ''), actor: 0, days: [1, 7, 30, 90].includes(PREFS.get('journal.days', 7)) ? PREFS.get('journal.days', 7) : 7,
  view: PREFS.get('journal.view', 'actions') === 'logins' ? 'logins' : 'actions'};
// Фильтр «один игрок или чат» ставится из их карточки и не запоминается: открыли раздел заново — снова весь журнал.
JOURNAL.scope = null;   // {user_id | chat_id, title}
function openJournalFor(scope) {
  if (!ME.sections.some(z => z.key === 'journal')) return toast('Журнал открыт со старшего хелпера (4).', true);
  JOURNAL.scope = scope; JOURNAL.view = 'actions'; JOURNAL.kind = ''; JOURNAL.actor = 0;
  tabs('journal'); journalView($('#main'));
}
const journalScopeQs = () => JOURNAL.scope ? (JOURNAL.scope.user_id ? `&user_id=${JOURNAL.scope.user_id}` : `&chat_id=${JOURNAL.scope.chat_id}`) : '';
const saveJournal = () => { PREFS.set('journal.kind', JOURNAL.kind); PREFS.set('journal.days', JOURNAL.days); PREFS.set('journal.view', JOURNAL.view); };
// Создатель видит ещё и входы в админку (адрес и устройство): остальным этой вкладки нет.
const journalTabs = () => !ME.creator ? '' : `<div class="scope" style="margin-bottom:8px">${[['actions', 'Действия'], ['logins', 'Входы']].map(([k, t]) =>
  `<button class="btn small ${k === JOURNAL.view ? 'primary' : ''}" data-jview="${k}">${t}</button>`).join('')}</div>`;
const bindJournalTabs = main => main.querySelectorAll('[data-jview]').forEach(b =>
  b.onclick = () => { JOURNAL.view = b.dataset.jview; saveJournal(); journalView(main); });
async function loginsView(main) {
  const data = await loadSectionData(main, `/logins?days=${JOURNAL.days}`, () => loginsView(main), 'journal');
  if (!data) return;
  const rows = data.items.map(x => `<div class="log"><div><b>${who(x.user.id, x.user.username)}</b> · ${esc(x.device)}</div>
      <div class="sub">${when(x.at)} · адрес ${esc(x.ip || 'неизвестен')}</div></div>`).join('');
  main.innerHTML = `${pageHead('☰', 'Журнал', 'Кто из команды и что сделал')}${journalTabs()}<div class="scope">${[[1, 'Сутки'], [7, '7 дней'], [30, '30 дней'], [90, '90 дней']].map(([d, t]) =>
      `<button class="btn small ${d === JOURNAL.days ? 'primary' : ''}" data-jdays="${d}">${t}</button>`).join('')}</div>
    <section class="section"><h3 class="sec-h">Входы в админку</h3>
      <div class="sub note">Кто и с какого устройства открывал админку. Повторные входы за полчаса с того же места не дублируются.</div>
      ${rows || '<div class="empty">За этот период входов нет.</div>'}</section>`;
  bindJournalTabs(main);
  main.querySelectorAll('[data-jdays]').forEach(b => b.onclick = () => { JOURNAL.days = +b.dataset.jdays; saveJournal(); loginsView(main); });
}
async function journalView(main, more = '') {
  if (ME.creator && JOURNAL.view === 'logins') return loginsView(main);
  const qs = `kind=${encodeURIComponent(JOURNAL.kind)}&actor=${JOURNAL.actor}&days=${JOURNAL.days}${journalScopeQs()}${more ? '&before=' + encodeURIComponent(more) : ''}`;
  const data = await loadSectionData(main, `/journal?${qs}`, () => journalView(main, more), 'journal');
  if (!data) return;
  if (JOURNAL.kind && !data.kinds.some(k => k.key === JOURNAL.kind)) { JOURNAL.kind = ''; saveJournal(); return journalView(main); }   // запомненный вид исчез
  const canPeople = ME.sections.some(z => z.key === 'people');
  const person = x => x && x.id
    ? (canPeople ? `<a href="#" data-player="${x.id}">${pinline(x)}</a>` : pinline(x)) + tagSfx(x.tag)
    : '';
  if (!more) JOURNAL.lastDay = '';   // разделитель дня не повторяется на подгруженной странице
  const dayHead = iso => {
    const d = iso ? new Date(iso).toLocaleDateString('ru-RU', {day: 'numeric', month: 'long', weekday: 'short'}) : '';
    if (!d || d === JOURNAL.lastDay) return '';
    JOURNAL.lastDay = d; return `<div class="day-h">${d}</div>`;
  };
  const rows = data.items.map(x => {
    const chatTitle = x.chat ? String(x.chat.title || x.chat.id) : '';
    const chat = chatTitle ? (canPeople ? `<a href="#" data-chat="${x.chat.id}">${esc(chatTitle)}</a>` : esc(chatTitle)) : '';
    // В описании переключателя чат уже назван словами — второй раз его не показываем.
    const where = chat && !String(x.text || '').includes(chatTitle) ? ` в чате «${chat}»` : '';
    const reason = x.reason ? ` · причина: ${esc(x.reason)}` : '';
    return `${dayHead(x.at)}<div class="log"><div><b>${esc(x.title)}</b>${x.text ? ' ' + esc(x.text) : ''}${where}</div>
      <div class="sub">${x.actor && x.actor.id ? person(x.actor) : 'бот'}${x.user ? ' → ' + person(x.user) : ''} · ${when(x.at)}${reason}</div></div>`;
  }).join('');
  const body = rows || (more ? '' : '<div class="empty">За этот период действий нет.</div>');
  if (more) {
    main.querySelector('#jmore')?.remove();
    main.querySelector('#jlist').insertAdjacentHTML('beforeend', body);
  } else {
    main.innerHTML = `${pageHead('☰', 'Журнал', 'Кто из команды и что сделал')}${journalTabs()}<div class="scope">${[[1, 'Сутки'], [7, '7 дней'], [30, '30 дней'], [90, '90 дней']].map(([d, t]) =>
        `<button class="btn small ${d === JOURNAL.days ? 'primary' : ''}" data-jdays="${d}">${t}</button>`).join('')}</div>
      <div class="grid2 jfilters">
        <div class="field"><label>Что</label><select id="jkind"><option value="">Всё</option>${data.kinds.map(k =>
          `<option value="${k.key}" ${k.key === JOURNAL.kind ? 'selected' : ''}>${esc(k.title)}</option>`).join('')}</select></div>
        <div class="field"><label>Кто</label><select id="jactor"><option value="0">Все</option>${data.actors.map(a =>
          `<option value="${a.id}" ${a.id === JOURNAL.actor ? 'selected' : ''}>${a.username ? '@' + esc(a.username) : 'id' + a.id}</option>`).join('')}</select></div></div>
      ${JOURNAL.scope ? `<div class="chips jscope"><span class="chip ok">${JOURNAL.scope.user_id ? '👤' : '💬'} ${esc(JOURNAL.scope.title)}</span><button type="button" class="btn small" id="jscopeoff">✕ Весь журнал</button></div>` : ''}
      <div class="actions jexport"><button type="button" class="btn small" id="jexport">⬇️ ${INIT ? 'Прислать таблицу в личку' : 'Скачать таблицу'} (CSV) за ${JOURNAL.days} дн.</button></div>
      <section class="section" id="jlist"><h3 class="sec-h">Действия персонала</h3>${body}</section>`;
    bindJournalTabs(main);
    main.querySelectorAll('[data-jdays]').forEach(b => b.onclick = () => { JOURNAL.days = +b.dataset.jdays; saveJournal(); journalView(main); });
    $('#jkind').onchange = e => { JOURNAL.kind = e.target.value; saveJournal(); journalView(main); };
    $('#jactor').onchange = e => { JOURNAL.actor = +e.target.value; journalView(main); };
    if ($('#jscopeoff')) $('#jscopeoff').onclick = () => { JOURNAL.scope = null; journalView(main); };
    $('#jexport').onclick = e => exportJournal(e.currentTarget);
    $('#jlist').onclick = e => {
      const p = e.target.closest('a[data-player]'), c = e.target.closest('a[data-chat]');
      if (p) { e.preventDefault(); tabs('people'); PEOPLE.stack = []; playerView(main, +p.dataset.player); }
      else if (c) { e.preventDefault(); tabs('people'); PEOPLE.stack = []; chatView(main, +c.dataset.chat); }
    };
  }
  if (data.more) {
    $('#jlist').insertAdjacentHTML('beforeend', `<button class="btn small more" id="jmore">Показать ещё</button>`);
    $('#jmore').onclick = () => journalView(main, data.next);
  }
}

SECTIONS.journal = main => { JOURNAL.scope = null; journalView(main); };

// Выгрузка того же среза (вид, кто, период, игрок или чат) файлом: сервер отдаёт до 5000 строк за период до 90 дней.
async function exportJournal(button) {
  if (button.disabled) return;
  button.disabled = true;
  try {
    const headers = {};
    if (INIT) headers['x-init-data'] = INIT;
    try { const s = localStorage.getItem('pv_sess'); if (s) headers['x-session-token'] = s; } catch (_) {}
    const qs = `kind=${encodeURIComponent(JOURNAL.kind)}&actor=${JOURNAL.actor}&days=${JOURNAL.days}${journalScopeQs()}`;
    if (INIT) {   // внутри Telegram страница файл не скачает: бот пришлёт его в личку
      toast((await api(`/journal/export?${qs}&deliver=dm`)).message);
      return;
    }
    const res = await fetch(`${BASE}/bot-admin/api/journal/export?${qs}`, {headers});
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Ошибка ${res.status}`);
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement('a'), {href: url, download: `journal-${JOURNAL.days}d.csv`});
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    toast('Таблица скачана');
  } catch (err) { toast(err.message, true); }
  finally { button.disabled = false; }
}

// ── Жалобы ──────────────────────────────────────────────────────────────────

const REPORT_PICK = new Set();   // выбранные для массовой чистки жалобы; живёт, пока открыта админка
async function reportsView(main, kind = 'open') {
  if (kind !== 'open' && kind !== 'closed') kind = 'open';
  PREFS.set('reports.kind', kind);
  const data = await loadSectionData(main, `/reports?kind=${kind}`, () => reportsView(main, kind), 'reports');
  if (!data) return;
  refreshBadges();
  const c = data.counts;
  const canPeople = ME.sections.some(z => z.key === 'people');
  const person = p => p ? (canPeople ? `<a href="#" data-player="${p.id}">${pinline(p)}</a>` : pinline(p)) + tagSfx(p.tag) : '—';
  const chipCls = {new: 'warn', in_work: '', resolved: 'ok', rejected: 'bad'};
  main.innerHTML = `
    ${pageHead('⚑', 'Жалобы', 'Что прислали игроки и что с этим решили')}
    <button type="button" class="btn small" onclick="mafiaOnlineReports(document.getElementById('main'))">Межчатовая Мафия ›</button>
    <div class="kpis rep-counts">${kpi('Новых', num(c.new), '', c.new ? 'sm warn' : 'sm')}${kpi('В работе', num(c.in_work), '', 'sm')}${kpi('Закрыто', num(c.resolved + c.rejected), '', 'sm')}</div>
    <div class="scope"><button class="btn small ${kind === 'open' ? 'primary' : ''}" data-kind="open">Очередь · ${c.new + c.in_work}</button>
      <button class="btn small ${kind === 'closed' ? 'primary' : ''}" data-kind="closed">Закрытые · ${c.resolved + c.rejected}</button></div>
    <div class="sub note">🔒 Жалобы анонимны. ${data.can_see_reporter ? 'Вам автор виден по настройкам жалоб.' : 'Автора жалобы видит только персонал с доступом.'}</div>
    ${data.repeat && data.repeat.length ? `<section class="section" data-sec="r-repeat"><h3 class="sec-h">🔁 Повторные нарушители <small class="cnt">· ${data.repeat.length}</small></h3>
      <div class="sub note">3 жалобы и больше за 30 дней, отклонённые не считаются.</div>
      ${data.repeat.map(x => `<div class="sw-row"><div class="t">${person(x)}
        <div class="sub">жалоб: ${x.reports} · от ${x.reporters} ${x.reporters === 1 ? 'игрока' : 'разных игроков'} · открытых: ${x.open} · подтверждено: ${x.confirmed}</div></div>
        ${canPeople ? `<button class="btn small" data-player="${x.id}">👤 Карточка</button>` : ''}</div>`).join('')}</section>` : ''}
    ${kind === 'open' && data.items.length > 1 ? '<div id="repbulk"></div>' : ''}
    ${data.items.length ? data.items.map(r => `<div class="card rep ${r.status}" data-card="${r.id}">
      <div>${kind === 'open' && data.items.length > 1 ? '<input type="checkbox" class="pick" data-pickrep="' + r.id + '" aria-label="Выбрать жалобу"/> ' : ''}<span class="chip ${chipCls[r.status] || ''}">${esc(r.status_title)}</span> <b>№${r.id}</b>
        <span class="sub">· ${when(r.created_at)} · ${esc(r.chat.title)}</span></div>
      <div style="margin-top:8px">На ${person(r.target)}${r.target_reports > 1 ? ` <span class="chip bad">жалоб всего: ${r.target_reports}</span>` : ''}
        <span class="sub">${r.reporter ? 'от ' + person(r.reporter) : '· автор скрыт'}</span></div>
      <div class="rep-why"><b>Причина:</b> ${esc(r.reason)}</div>
      ${r.message_text ? `<blockquote class="rep-msg">${esc(r.message_text)}</blockquote>` : ''}
      ${r.handled_by ? `<div class="sub" style="margin-top:6px">${pinline(r.handled_by)} · ${when(r.handled_at)}${r.note ? ' · ' + esc(r.note) : ''}</div>` : ''}
      ${kind === 'open' ? `<div class="actions" style="margin-top:10px">
        ${canPeople ? `<button class="btn small" data-player="${r.target.id}">👤 Карточка</button>` : ''}
        ${(data.punish || []).map(a => `<button class="btn small danger" data-punish="${a.key}" data-rid="${r.id}">${esc(a.title)}</button>`).join('')}
        ${r.status === 'new' ? `<button class="btn small" data-rep="${r.id}" data-act="take">🙋 Взять</button>` : ''}
        <button class="btn small primary" data-rep="${r.id}" data-act="resolve">✅ Нарушение</button>
        <button class="btn small" data-rep="${r.id}" data-act="reject">✖️ Отклонить</button></div>` : ''}
    </div>`).join('') : `<div class="empty">${kind === 'open' ? 'Очередь пуста.' : 'Закрытых жалоб пока нет.'}</div>`}`;
  main.querySelectorAll('[data-kind]').forEach(b => b.onclick = () => reportsView(main, b.dataset.kind));
  main.querySelectorAll('[data-player]').forEach(a => a.onclick = e => {
    e.preventDefault(); tabs('people'); PEOPLE.stack = []; playerView(main, +a.dataset.player);
  });
  // Быстрое наказание из жалобы: в том же чате, с закрытием жалобы как подтверждённой.
  main.querySelectorAll('[data-punish]').forEach(b => b.onclick = () => {
    const key = b.dataset.punish, r = data.items.find(x => x.id === +b.dataset.rid);
    const title = (data.punish.find(a => a.key === key) || {}).title || key;
    const [form, collect] = actionForm(key, {});
    sheet(title, `<div class="sub" style="margin-bottom:10px">На ${esc(r.target.name)} · чат «${esc(r.chat.title)}» · жалоба №${r.id}: ${esc(r.reason)}</div>${form}
      <div class="field switch"><input id="fclose" type="checkbox" checked/><label for="fclose" style="margin:0">Закрыть жалобу: нарушение подтверждено</label></div>`,
      key === 'ban' ? 'Далее' : 'Выполнить', async () => {
        const payload = {action: key, ...collect(), close: $('#fclose').checked};
        const send = async () => {
          const res = await api(`/reports/${r.id}/punish`, {method: 'POST', body: JSON.stringify(payload)});
          toast(res.message || 'Готово');
          reportsView(main, kind);
        };
        if (key !== 'ban') return send();
        // Бан — как в карточке игрока: сначала итог, потом подтверждение (по умолчанию он «навсегда»).
        const lines = [`Игрок: <b>${esc(r.target.name)}</b>`, ...confirmLines('ban', payload, {}, {chat_title: r.chat.title}),
          ...(payload.close ? ['Жалоба закроется как подтверждённая.'] : [])];
        sheet(CONFIRM_TITLE.ban, `<div class="sub" style="margin-bottom:8px">Проверьте перед выполнением:</div>
          <div class="confirm">${lines.map(l => `<div>${l}</div>`).join('')}</div>`, 'Подтвердить', send);
        return 'keep';
      });
  });
  // Массовая чистка очереди: отметить несколько жалоб и закрыть их одним действием (наказаний здесь нет).
  const queue = new Set(data.items.map(x => x.id));
  [...REPORT_PICK].forEach(id => { if (kind !== 'open' || !queue.has(id)) REPORT_PICK.delete(id); });
  const BULK_REPORT = {take: ['🙋 Взять', 'Взять в работу'], resolve: ['✅ Нарушение', 'Нарушение подтверждено'], reject: ['✖️ Отклонить', 'Отклонить']};
  const drawRepBulk = () => {
    const host = $('#repbulk'); if (!host) return;
    const n = REPORT_PICK.size;
    main.querySelectorAll('[data-card]').forEach(card => {
      const on = REPORT_PICK.has(+card.dataset.card);
      card.classList.toggle('picked', on);
      const box = card.querySelector('.pick'); if (box) box.checked = on;
    });
    host.innerHTML = `<div class="card bulkbar"><div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline">
        <b>Выбрано: ${n}</b><span class="sub"><a href="#" id="repall">${n === queue.size ? 'снять выбор' : 'выбрать все'}</a></span></div>
      ${n ? `<div class="actions" style="margin-top:8px">${Object.entries(BULK_REPORT).map(([key, [label]]) =>
        `<button class="btn small ${key === 'resolve' ? 'primary' : ''}" data-repbulk="${key}">${label}</button>`).join('')}</div>`
        : '<div class="sub" style="margin-top:4px">Отмечайте жалобы галочкой и закрывайте пачкой.</div>'}</div>`;
    $('#repall').onclick = e => { e.preventDefault(); n === queue.size ? REPORT_PICK.clear() : queue.forEach(id => REPORT_PICK.add(id)); drawRepBulk(); };
    host.querySelectorAll('[data-repbulk]').forEach(b => b.onclick = () => {
      const act = b.dataset.repbulk, ids = [...REPORT_PICK];
      const body = `<div class="sub" style="margin-bottom:8px">Жалоб: <b>${ids.length}</b>. ${act === 'take' ? 'Все они будут помечены как ваши.'
        : 'Авторам бот напишет в личку, чем всё закончилось. Нарушителей это не наказывает: выдать предупреждение, замутить или забанить можно из самой жалобы.'}</div>
        ${act === 'take' ? '' : '<div class="field"><label>Комментарий (необязательно)</label><input id="fnote" maxlength="300"/></div>'}`;
      sheet(BULK_REPORT[act][1], body, 'Готово', async () => {
        const res = await api('/reports/bulk', {method: 'POST', body: JSON.stringify({action: act, ids, note: ($('#fnote') || {}).value || ''})});
        toast(res.message || 'Готово');
        REPORT_PICK.clear();
        if (res.failed.length) {
          sheet('Не всё получилось', `<div class="sub">${esc(res.message)}</div>${res.failed.map(f =>
            `<div class="log"><b>№${f.id}</b><div class="sub">${esc(f.reason)}</div></div>`).join('')}`, 'Понятно', () => {}, {info: true});
        }
        reportsView(main, kind);
      });
    });
  };
  main.querySelectorAll('[data-pickrep]').forEach(box => box.onchange = () => {
    box.checked ? REPORT_PICK.add(+box.dataset.pickrep) : REPORT_PICK.delete(+box.dataset.pickrep);
    drawRepBulk();
  });
  drawRepBulk();
  const titles = {take: 'Взять жалобу в работу', resolve: 'Нарушение подтверждено', reject: 'Отклонить жалобу'};
  main.querySelectorAll('[data-rep]').forEach(b => b.onclick = () => {
    const act = b.dataset.act;
    const body = act === 'take' ? '<div class="sub">Жалоба будет помечена как ваша.</div>'
      : `<div class="sub" style="margin-bottom:8px">Автору жалобы бот напишет в личку, чем всё закончилось.
         Наказать нарушителя можно кнопкой «Наказать» (карточка игрока).</div>
         <div class="field"><label>Комментарий (необязательно)</label><input id="fnote" maxlength="300"/></div>`;
    sheet(titles[act], body, 'Готово', async () => {
      const res = await api(`/reports/${b.dataset.rep}`, {method: 'POST',
        body: JSON.stringify({action: act, note: ($('#fnote') || {}).value || ''})});
      toast(res.message || 'Готово');
      reportsView(main, kind);
    });
  });
}

SECTIONS.reports = main => reportsView(main, PREFS.get('reports.kind', 'open'));

async function mafiaOnlineReports(main, closed = false, before = 0) {
  const d = await loadSectionData(main, `/mafia-online-reports?resolved=${closed}&before=${before}`, () => mafiaOnlineReports(main, closed, before), 'reports');
  if (!d) return;
  main.innerHTML = `<button class="btn small" id="mfo-reports-back">‹ Жалобы</button>
    ${pageHead('⚑', 'Межчатовая Мафия', 'Сообщения, на которые пожаловались игроки')}
    <div class="scope"><button class="btn small ${closed?'':'primary'}" id="mfo-open">Открытые</button><button class="btn small ${closed?'primary':''}" id="mfo-closed">Решённые</button></div>
    ${d.items.map(m => `<div class="card"><div class="sub">Город #${m.room_id} · ${esc(({table:'Стол',mafia:'Мафия',afterlife:'Выбывшие'})[m.channel] || '')} · жалоб ${num(m.reports)}</div>
      <p><b>${esc(m.name)}</b></p><p style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(m.body)}</p>
      <p class="sub">${esc(m.reasons.join(' · '))}</p><div class="actions">
      ${m.hidden ? '<span class="chip">Скрыто</span>' : `<button class="btn small" data-mfo-action="hide" data-msg="${m.id}">Скрыть</button>`}
      <button class="btn small" data-mfo-action="mute" data-msg="${m.id}">Мут в этой партии</button>
      <button class="btn small" data-mfo-action="unmute" data-msg="${m.id}">Снять мут</button>
      ${closed?'':`<button class="btn small" data-mfo-action="resolve" data-msg="${m.id}">Закрыть жалобы</button>`}</div></div>`).join('') || `<p class="empty">${closed?'Решённых':'Открытых'} жалоб нет.</p>`}
    ${d.next_before?'<button class="btn small" id="mfo-earlier">Раньше</button>':''}`;
  $('#mfo-reports-back', main).onclick = () => reportsView(main);
  $('#mfo-open',main).onclick=()=>mafiaOnlineReports(main,false);
  $('#mfo-closed',main).onclick=()=>mafiaOnlineReports(main,true);
  if(d.next_before)$('#mfo-earlier',main).onclick=()=>mafiaOnlineReports(main,closed,d.next_before);
  main.querySelectorAll('[data-mfo-action]').forEach(button => button.onclick = () => {
    const kind = button.dataset.mfoAction, id = Number(button.dataset.msg);
    sheet('Решение по сообщению', hint(({hide:'Сообщение скроется у всех участников.', mute:'Игрок не сможет писать в этой партии. Голосование останется доступно.', unmute:'Игрок снова сможет писать, когда это разрешает этап.', resolve:'Жалобы на это сообщение будут закрыты.'})[kind]), 'Применить', async () => {
      await api(`/mafia-online-reports/${id}`, {method:'POST', body:JSON.stringify({kind})});
      toast('Решение сохранено.'); mafiaOnlineReports(main,closed,before);
    });
  });
}

