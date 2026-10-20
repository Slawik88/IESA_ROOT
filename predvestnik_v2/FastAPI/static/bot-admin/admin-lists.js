// ── Журнал и жалобы ─────────────────────────────────────────────────────────
// Адреса: #/journal?days=7&kind=&actor=&view=logins  ·  #/reports?kind=open|closed

// Значок и цвет события: глаз узнаёт бан/мут/снятие раньше, чем прочтёт текст.
const EVENT_LOOK = {
  ban: ['⛔', 'bad'], global_ban: ['🚫', 'bad'], kick: ['👢', 'bad'], block: ['🙈', 'bad'], leave: ['🚪', 'bad'],
  mute: ['🔇', 'warn'], warn: ['⚠️', 'warn'], close: ['🔒', 'warn'], close_chat: ['🔒', 'warn'], watch_add: ['👁', 'warn'],
  unban: ['✓', 'ok'], global_unban: ['✓', 'ok'], unmute: ['✓', 'ok'], unwarn: ['✓', 'ok'], unwarn_all: ['✓', 'ok'], unblock: ['✓', 'ok'],
  open: ['🔓', 'ok'], open_chat: ['🔓', 'ok'], watch_remove: ['👁', ''],
  balance: ['💰', 'info'], vip: ['👑', 'info'], rank: ['🎖', 'accent'], chat_rank: ['🎖', 'accent'], chat_rights: ['🛡', 'accent'], grant: ['🛡', 'accent'],
  mark_grant: ['🏅', 'accent'], mark_revoke: ['🏅', ''], note_add: ['📝', ''], note_remove: ['📝', ''], message: ['📣', 'info'],
  promo_create: ['🎟', 'info'], promo_update: ['🎟', ''], promo_active: ['🎟', ''], promo_bulk: ['🎟', 'info'], switch: ['⏻', 'warn'],
  broadcast: ['📣', 'info'], broadcast_stop: ['⏹', ''], broadcast_resume: ['▶', ''], broadcast_template: ['💾', ''],
  report_in_work: ['🙋', 'info'], report_resolved: ['⚑', 'bad'], report_rejected: ['✖', ''], sessions_revoke: ['🔒', 'warn'],
};
// Лента событий с разделителями по дням. opts.user / opts.chat = false — не повторять то, что и так ясно из карточки.
function journalList(items, {user = true, chat = true, lastDay = {v: ''}} = {}) {
  if (!items || !items.length) return emptyBox('Пока пусто');
  return items.map(x => {
    const d = x.at ? new Date(x.at).toLocaleDateString('ru-RU', {day: 'numeric', month: 'long', weekday: 'short'}) : '';
    const head = d && d !== lastDay.v ? `<div class="day">${d}</div>` : '';
    if (d) lastDay.v = d;
    const [glyph, tone] = EVENT_LOOK[x.action] || ['•', ''];
    const time = x.at ? new Date(x.at).toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'}) : '';
    return `${head}<div class="ev">${lead(glyph, tone)}<div><div class="ev-t"><b>${esc(x.title)}</b> ${esc(x.text || '')}</div>
      <div class="ev-m">${x.actor && x.actor.id ? person(x.actor) : '<span>бот</span>'}${user && x.user ? `<span class="arrow">→</span>${person(x.user)}` : ''}
        ${chat && x.chat ? `<span>· ${chatLink(x.chat)}</span>` : ''}</div>
      ${x.reason ? `<div class="ev-r">«${esc(x.reason)}»</div>` : ''}</div><time>${time}</time></div>`;
  }).join('');
}

// ── Журнал: все действия персонала ───────────────────────────────────────────

async function journalView(ctx) {
  const v = ctx.view, q = ctx.query;
  const days = [1, 7, 30, 90].includes(+q.get('days')) ? +q.get('days') : ([1, 7, 30, 90].includes(PREFS.get('journal.days', 7)) ? PREFS.get('journal.days', 7) : 7);
  const kind = q.has('kind') ? q.get('kind') : PREFS.get('journal.kind', '');
  const actor = +q.get('actor') || 0;
  const view = ME.creator && (q.get('view') || PREFS.get('journal.view', 'actions')) === 'logins' ? 'logins' : 'actions';
  const set = patch => { Object.entries(patch).forEach(([k, val]) => { if (k !== 'actor') PREFS.set('journal.' + k, val); }); setQuery(patch); ctx.refresh(); };
  const head = (ME.creator ? seg('jview', [['actions', 'Действия'], ['logins', 'Входы в админку']], view) : '')
    + seg('jdays', [[1, 'Сутки'], [7, '7 дней'], [30, '30 дней'], [90, '90 дней']], days);
  on(v, {jview: el => set({view: el.dataset.v}), jdays: el => set({days: +el.dataset.v}), jkind: el => set({kind: el.dataset.v}),
    jactor: () => actorSheet(), jclear: () => set({actor: ''})});
  if (view === 'logins') {
    const data = await ctx.load(`/logins?days=${days}`);
    if (!ctx.alive()) return;
    v.innerHTML = head + `<div class="list">${data.items.map(x => row({lead: ava(x.user), title: `${who(x.user.id, x.user.username)} · ${esc(x.device)}`,
      sub: `${ago(x.at)} · адрес ${esc(x.ip || 'неизвестен')}`, href: has('people') ? '#/player/' + x.user.id : ''})).join('') || emptyBox('За этот период входов нет')}</div>
      ${help('Что здесь', '<p>Кто и с какого устройства открывал админку. Повторные входы за полчаса с того же места не дублируются.</p>')}`;
    return;
  }
  const qs = before => `kind=${encodeURIComponent(kind)}&actor=${actor}&days=${days}${before ? '&before=' + encodeURIComponent(before) : ''}`;
  const data = await ctx.load(`/journal?${qs('')}`);
  if (!ctx.alive()) return;
  if (kind && !data.kinds.some(k => k.key === kind)) { PREFS.set('journal.kind', ''); setQuery({kind: ''}); ctx.refresh(); return; }   // запомненный вид исчез
  const who_ = data.actors.find(a => a.id === actor);
  const lastDay = {v: ''};
  v.innerHTML = head + `<div class="chipset scroll">${[['', 'Всё'], ...data.kinds.map(k => [k.key, k.title])].map(([k, t]) =>
      `<button type="button" class="chip" data-on="jkind" data-v="${esc(k)}" aria-pressed="${k === kind}">${esc(t)}</button>`).join('')}</div>
    <div class="btns" style="margin:10px 0 4px">${who_ ? `<button type="button" class="chip x" data-on="jclear" aria-pressed="true">${who(who_.id, who_.username)}</button>`
      : `<button type="button" class="chip" data-on="jactor">👤 Кто: все ▾</button>`}</div>
    <div id="jlist">${journalList(data.items, {lastDay}) }</div>
    ${data.more ? '<button type="button" class="btn more" id="jmore">Показать ещё</button>' : ''}`;
  let next = data.next;
  const more = v.querySelector('#jmore');
  if (more) more.onclick = () => busy(more, async () => {
    const page = await api(`/journal?${qs(next)}`);
    v.querySelector('#jlist').insertAdjacentHTML('beforeend', journalList(page.items, {lastDay}));   // разделитель дня не повторяется на подгруженной странице
    next = page.next;
    if (!page.more) more.remove();
  });
  function actorSheet() {
    const p = openSheet({title: 'Кто сделал', body: `<div class="list">${data.actors.map(a => row({lead: ava(a, 'sm'), title: who(a.id, a.username), on: 'a', data: {v: a.id}, chev: false})).join('') || emptyBox('Никого')}</div>`});
    on(p.el, {a: el => { closeSheets(); set({actor: +el.dataset.v}); }});
  }
}
route('journal', {section: 'journal', root: true, title: () => 'Журнал', render: journalView});

// ── Жалобы ──────────────────────────────────────────────────────────────────

// Наказания из жалобы (сервер отдаёт только разрешённые роли ключи): значок, глагол, цвет.
const PUNISH_LOOK = {warn: ['⚠️', 'Выдать предупреждение', 'warn'], mute: ['🔇', 'Замутить в чате', 'warn'], ban: ['⛔', 'Забанить в чате', 'bad']};
const REPORT_PICK = new Set();   // выбранные для массового закрытия жалобы; живёт, пока открыта админка
const REPORT_TONE = {new: 'warn', in_work: 'info', resolved: 'bad', rejected: ''};
let REPORT_SELECT = false;
async function reportsView(ctx) {
  const v = ctx.view;
  const kind = ['open', 'closed'].includes(ctx.query.get('kind')) ? ctx.query.get('kind') : PREFS.get('reports.kind', 'open') === 'closed' ? 'closed' : 'open';
  PREFS.set('reports.kind', kind);
  const data = await ctx.load(`/reports?kind=${kind}`);
  if (!ctx.alive()) return;
  refreshBadges();
  const c = data.counts, open = kind === 'open';
  const queue = new Set(data.items.map(x => x.id));
  [...REPORT_PICK].forEach(id => { if (!open || !queue.has(id)) REPORT_PICK.delete(id); });   // ушедшие из очереди не остаются выбранными
  const selecting = open && REPORT_SELECT && data.items.length > 1;
  const card = r => `<article class="rep ${r.status}${REPORT_PICK.has(r.id) ? ' picked' : ''}" data-card="${r.id}">
      <div class="rep-top">${selecting ? `<input type="checkbox" class="pick" data-change="pick" data-v="${r.id}" ${REPORT_PICK.has(r.id) ? 'checked' : ''} aria-label="Выбрать жалобу №${r.id}" style="width:22px;height:22px"/>` : ''}
        ${pill(r.status_title, REPORT_TONE[r.status])}<span>№${r.id} · ${ago(r.created_at)} · ${esc(r.chat.title)}</span></div>
      <${has('people') ? `a href="#/player/${r.target.id}"` : 'div'} class="rep-who">${ava(r.target)}<div><b>${esc(r.target.name)}</b>
        <span>${r.target.tag ? `[${esc(r.target.tag)}] · ` : ''}${r.target_reports > 1 ? `<span style="color:var(--bad);font-weight:600">${r.target_reports} ${plural(r.target_reports, 'жалоба', 'жалобы', 'жалоб')} всего</span> · ` : ''}${r.reporter ? 'от ' + esc(r.reporter.name) : 'автор скрыт'}</span></div>
        ${has('people') ? '<span class="chev" aria-hidden="true">›</span>' : ''}</${has('people') ? 'a' : 'div'}>
      <div class="rep-why">${esc(r.reason)}</div>
      ${r.message_text ? `<div class="quote clamp" data-on="expand">${esc(r.message_text)}</div>` : ''}
      ${r.handled_by ? `<div class="rep-done">${person(r.handled_by)}<span>· ${ago(r.handled_at)}${r.note ? ' · «' + esc(r.note) + '»' : ''}</span></div>` : ''}
      ${open && !selecting ? `<div class="btns grow">${r.status === 'new' ? `<button type="button" class="btn sm" data-on="take" data-v="${r.id}">🙋 Взять</button>` : ''}
        <button type="button" class="btn sm primary" data-on="decide" data-v="${r.id}">Решить ›</button></div>` : ''}</article>`;
  v.innerHTML = seg('rkind', [['open', 'Очередь', c.new + c.in_work, c.new ? 'bad' : ''], ['closed', 'Закрытые', c.resolved + c.rejected]], kind, {cls: 'sticky'})
    + (open && c.new + c.in_work ? `<p class="sub" style="margin:-4px 0 0">${pill(c.new + ' ' + plural(c.new, 'новая', 'новые', 'новых'), c.new ? 'warn' : '')} ${pill(c.in_work + ' в работе', 'info')}</p>` : '')
    + (data.repeat && data.repeat.length ? sh('🔁 Повторные нарушители', {count: data.repeat.length}) + `<div class="faces">${data.repeat.map(x =>
        `<${has('people') ? `a href="#/player/${x.id}"` : 'div'} class="face" title="жалоб: ${x.reports} · от ${x.reporters} · открытых ${x.open} · подтверждено ${x.confirmed}">${ava({...x, dot: true})}<span>${esc(x.name)}</span><span style="color:var(--bad);font-weight:700">${x.reports} жалоб</span></${has('people') ? 'a' : 'div'}>`).join('')}</div>` : '')
    + (data.items.length ? sh(open ? 'Очередь' : 'Закрытые', {count: data.items.length}).replace('</div>', open && data.items.length > 1 ? `<button type="button" class="lnk" data-on="select">${selecting ? 'Готово' : 'Выбрать'}</button></div>` : '</div>')
        + data.items.map(card).join('') : emptyBox(open ? 'Очередь пуста' : 'Закрытых жалоб пока нет', open ? 'Новые жалобы появятся здесь и значком на вкладке.' : ''))
    + help('Как устроены жалобы', `<p>🔒 Жалобы анонимны. ${data.can_see_reporter ? 'Вам автор виден по настройкам жалоб.' : 'Автора видит только персонал с доступом.'}</p>
      <p>«Повторные нарушители» — 3 жалобы и больше за 30 дней, отклонённые не считаются. Решение жалобы бот сообщает её автору в личку.</p>`);
  const reload = () => { CACHE.delete(`/reports?kind=${kind}`); ctx.refresh(); };
  const drawBar = () => {
    if (!selecting) { ctx.bar(''); return; }
    const n = REPORT_PICK.size;
    ctx.bar(`<div><b>Выбрано: ${n}</b><button type="button" class="linkbtn" style="min-height:0;padding:0" data-on="all">${n === queue.size ? 'снять выбор' : 'выбрать все'}</button></div>
      <div class="btns">${n ? '<button type="button" class="btn sm" data-on="bulk" data-v="take">🙋 Взять</button><button type="button" class="btn sm primary" data-on="bulk" data-v="resolve">✅ Нарушение</button><button type="button" class="btn sm" data-on="bulk" data-v="reject">✖️ Отклонить</button>' : ''}</div>`, {
      all: () => { n === queue.size ? REPORT_PICK.clear() : queue.forEach(id => REPORT_PICK.add(id)); paint(); drawBar(); },
      bulk: el => bulkReports(el.dataset.v),
    }, 'wide');
  };
  const paint = () => $$('[data-card]', v).forEach(cardEl => {
    const onn = REPORT_PICK.has(+cardEl.dataset.card);
    cardEl.classList.toggle('picked', onn);
    const box = cardEl.querySelector('.pick'); if (box) box.checked = onn;
  });
  const bulkReports = act => {
    const ids = [...REPORT_PICK];
    const titles = {take: 'Взять в работу', resolve: 'Нарушение подтверждено', reject: 'Отклонить'};
    const s = sheet(titles[act], hint(`Жалоб: <b>${ids.length}</b>. ${act === 'take' ? 'Все они будут помечены как ваши.'
        : 'Авторам бот напишет в личку, чем всё закончилось. Нарушителей это не наказывает: наказать можно из самой жалобы.'}`)
      + (act === 'take' ? '' : field('Комментарий (необязательно)', '<input id="fnote" maxlength="300"/>')), 'Готово', async p => {
      const res = await post('/reports/bulk', {action: act, ids, note: (p.q('#fnote') || {}).value || ''});
      closeSheets();
      toast(res.message || 'Готово', {ok: !res.failed.length});
      REPORT_PICK.clear();
      if (res.failed.length) sheet('Не всё получилось', `<p class="sub">${esc(res.message)}</p><div class="list">${res.failed.map(f => row({title: '№' + f.id, sub: esc(f.reason)})).join('')}</div>`, 'Понятно', null, {info: true});
      reload();
      return 'keep';
    });
    return s;
  };
  const byId = id => data.items.find(x => x.id === +id);
  // Закрыть жалобу без наказания: нарушение подтверждено или отклонить; автору бот пишет итог.
  const close = (r, act) => sheet(act === 'resolve' ? '✅ Нарушение подтверждено' : act === 'reject' ? '✖️ Отклонить жалобу' : '🙋 Взять в работу',
    act === 'take' ? hint('Жалоба будет помечена как ваша.') : hint('Автору жалобы бот напишет в личку, чем всё закончилось.') + field('Комментарий (необязательно)', '<input id="fnote" maxlength="300"/>'),
    'Готово', async p => {
      const res = await post(`/reports/${r.id}`, {action: act, note: (p.q('#fnote') || {}).value || ''});
      closeSheets(); toast(res.message || 'Готово', {ok: true}); reload(); return 'keep';
    });
  // Наказание из жалобы: в том же чате, с закрытием жалобы как подтверждённой (галочка по умолчанию). Бан — с итогом.
  const punish = (r, key) => {
    const title = (PUNISH_LOOK[key] || [])[1] || (data.punish.find(a => a.key === key) || {}).title || key;
    const [form, collect] = actionForm(key, {reason: r.reason});
    const p = openSheet({title, sub: `${r.target.name} · ${r.chat.title}`, body: `<div class="sum" style="margin-bottom:14px"><div><span>Жалоба</span><span>№${r.id}: ${esc(r.reason)}</span></div></div>${form}
        <label class="row" style="min-height:52px"><span class="row-t"><b>Закрыть жалобу</b><span>Нарушение подтверждено, автору придёт итог</span></span>${toggle('id="fclose"', true, 'Закрыть жалобу')}</label>`,
      actions: [{label: key === 'ban' ? 'Далее' : 'Выполнить', kind: key === 'ban' ? 'danger' : 'primary', run: async panel => {
        const payload = {action: key, ...collect(panel.el), close: panel.q('#fclose').checked};
        const send = async () => {
          const res = await post(`/reports/${r.id}/punish`, payload);
          rememberReason(payload.reason); closeSheets(); toast(res.message || 'Готово', {ok: true}); reload(); return 'keep';
        };
        if (key !== 'ban') return send();
        openSheet({title: CONFIRM_TITLE.ban, sub: 'Проверьте перед выполнением', body: summary([['Кто', `<b>${esc(r.target.name)}</b>`], ...confirmLines('ban', payload, {}, {chat_title: r.chat.title}),
          ...(payload.close ? [['Жалоба', 'Закроется как подтверждённая.']] : [])]), actions: [{label: 'Подтвердить', kind: 'btn danger fill', run: send}]});
        return 'keep';
      }}, {label: 'Отмена', kind: '', run: null}]});
    wireFormChips(p.el);
  };
  const decide = r => {
    const p = openSheet({title: 'Решить жалобу', sub: `№${r.id} · ${r.target.name}`, body: `<div class="sum" style="margin-bottom:6px"><div><span>Причина</span><span><b>${esc(r.reason)}</b></span></div>
        ${r.message_text ? `<div><span>Сообщение</span><span class="wrap">${esc(r.message_text.slice(0, 300))}</span></div>` : ''}</div>
      ${sh('Наказать в этом чате')}<div class="list">${(data.punish || []).map(a => {
        const [glyph, title, tone] = PUNISH_LOOK[a.key] || ['•', a.title, ''];
        return row({lead: lead(glyph, tone), title, sub: esc(ACTION_HINTS[a.key] || ''), on: 'pun', data: {k: a.key}, cls: tone === 'bad' ? 'danger' : ''});
      }).join('')}</div>
      ${sh('Закрыть без наказания')}<div class="list">${row({lead: lead('✅', 'ok'), title: 'Нарушение подтверждено', sub: 'Наказание уже выдано или не нужно', on: 'cl', data: {k: 'resolve'}})}
        ${row({lead: lead('✖️'), title: 'Отклонить', sub: 'Нарушения нет', on: 'cl', data: {k: 'reject'}})}</div>
      ${has('people') ? `<div class="list" style="margin-top:8px">${row({lead: ava(r.target), title: 'Карточка игрока', sub: 'История, другие чаты, заметки', href: '#/player/' + r.target.id})}</div>` : ''}`});
    on(p.el, {pun: el => punish(r, el.dataset.k), cl: el => close(r, el.dataset.k)});
  };
  on(v, {
    rkind: el => { setQuery({kind: el.dataset.v}); ctx.refresh(); },
    select: () => { REPORT_SELECT = !REPORT_SELECT; if (!REPORT_SELECT) REPORT_PICK.clear(); ctx.refresh(); },
    pick: el => { el.checked ? REPORT_PICK.add(+el.dataset.v) : REPORT_PICK.delete(+el.dataset.v); paint(); drawBar(); },
    take: el => close(byId(el.dataset.v), 'take'),
    decide: el => decide(byId(el.dataset.v)),
    expand: el => el.classList.toggle('open'),
  });
  ctx.mount();
  drawBar();
}
route('reports', {section: 'reports', root: true, title: () => 'Жалобы', render: reportsView});
