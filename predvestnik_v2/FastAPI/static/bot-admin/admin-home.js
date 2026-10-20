// ── Главная: что требует внимания сейчас ────────────────────────────────────
// Правило трёх секунд: открыл — видно, всё ли в порядке и что делать первым. Каждый блок грузится
// сам по себе и только если у роли есть его раздел; упал один — остальные на месте.

// Человек, которому нужно внимание: лицо, кто это и почему его стоит открыть.
function attentionPersonRow(x) {
  const shown = x.name || who(x.id, x.username);
  const uname = x.username && shown !== '@' + x.username ? '@' + esc(x.username) : '';
  const at = x.at ? `${esc(x.at_label || '')} ${ago(x.at)}`.trim() : '';
  return row({lead: ava({...x, dot: x.flag_kind === 'bad'}), title: esc(shown), sub: [uname, x.note ? esc(x.note) : '', at].filter(Boolean).join(' · '),
    end: pill(x.flag, x.flag_kind || ''), href: '#/player/' + x.id, chev: false});
}
// Чат, где что-то не так: бот без прав, тихо 30 дней, бота удалили.
const CHAT_PROBLEM = {no_rights: 'warn', quiet: '', left: 'bad'};
function attentionChatRow(x) {
  return row({lead: chatAva(x), title: esc(x.title), sub: `${num(x.members)} уч. · ${x.last ? 'писали ' + ago(x.last) : 'сообщений не было'}`,
    pills: x.problems.map(p => pill(p.title, CHAT_PROBLEM[p.key] || '')).join(''), href: '#/chat/' + x.id});
}
async function attentionSheet(kind, title) {
  const data = await api(`/chats/attention?kind=${kind}`);
  sheet(title, data.items.length ? `<div class="list">${data.items.map(attentionChatRow).join('')}</div>${data.total > data.items.length
    ? `<p class="sub">Показаны ${data.items.length} из ${data.total}: самые людные.</p>` : ''}` : emptyBox('Таких чатов нет'), 'Закрыть', null, {info: true});
}
// Воронка подключения: шаги мастера и чаты, где бота так и не сделали админом.
async function onboardingSheet(days) {
  const f = await api(`/chats/onboarding?days=${days}`);
  const stuck = f.stuck.map(x => row({lead: chatAva(x), title: esc(x.title), sub: `добавили ${ago(x.added_at)}${x.inviter ? ' · ' + who(x.inviter.id, x.inviter.username) : ''}`,
    end: x.reminders ? `${x.reminders} напом.` : '', href: '#/chat/' + x.id})).join('');
  sheet(`🚪 Подключение чатов · ${f.days} дн.`, `<div class="list">${f.events.map(e => row({title: esc(e.title), sub: `чатов ${num(e.chats)}`, end: `<b>${num(e.count)}</b>`})).join('')
      || emptyBox('Пока никто не подключал бота')}</div>${stuck ? sh('Ждут прав', {count: f.waiting}) + `<div class="list">${stuck}</div>` : ''}`, 'Закрыть', null, {info: true});
}

function homeTiles() {
  return `<div class="tiles">${ME.sections.map(s => `<a class="tile" href="#/${s.key}">${icon(s.key, '')}<span>${esc(SHORT[s.key] || s.title)}</span>${BADGES[s.key] ? `<i class="badge">${BADGES[s.key]}</i>` : ''}</a>`).join('')}</div>`;
}

async function homeView(ctx) {
  const v = ctx.view, hour = new Date().getHours();
  const hi = hour < 5 ? 'Доброй ночи' : hour < 12 ? 'Доброе утро' : hour < 18 ? 'Добрый день' : 'Добрый вечер';
  v.innerHTML = `<div class="hello"><h2>${hi}</h2><p id="hsum">${esc(ME.rank_name)} · собираем сводку…</p></div>
    ${has('people') ? '<div id="h-attn">' + skeleton(2).replace('sk sk-title', 'sk sk-title" style="width:40%') + '</div>' : ''}
    ${has('reports') ? '<div id="h-rep"></div>' : ''}
    ${has('health') ? '<div id="h-health"></div>' : ''}
    ${has('metrics') ? '<div id="h-metrics"></div>' : ''}
    ${sh('Разделы')}${homeTiles()}`;
  ctx.mount();
  const todo = [];   // что ждёт человека: для строки под приветствием
  const put = (id, html) => { const el = v.querySelector('#' + id); if (el && ctx.alive()) el.innerHTML = html; };
  const jobs = [];

  if (has('people')) jobs.push(Promise.allSettled([api('/people/attention'), api('/chats/attention'), api('/chats/onboarding')]).then(([pr, ar, or]) => {
    const ppl = pr.status === 'fulfilled' ? pr.value.items || [] : [];
    const att = ar.status === 'fulfilled' ? ar.value : null;
    const onb = or.status === 'fulfilled' ? or.value : null;
    const chats = att ? att.items.slice(0, 3) : [];
    if (ppl.length) todo.push(`${ppl.length} ${plural(ppl.length, 'человек', 'человека', 'человек')} на виду`);
    if (att && att.total) todo.push(`${att.total} ${plural(att.total, 'чат', 'чата', 'чатов')} с проблемами`);
    const onbHtml = onb && onb.added ? `<div class="box" style="margin-top:10px">${row({lead: lead('🚪', 'info'), title: `Подключение чатов · ${onb.days} дн.`,
      sub: `добавили ${onb.added} · выдали права ${onb.ready}${onb.waiting ? ` · ждут прав ${onb.waiting}` : ''}${onb.gave_up ? ` · ушли без прав ${onb.gave_up}` : ''}`,
      end: onb.waiting ? pill('ждут ' + onb.waiting, 'warn') : '', on: 'onb', data: {days: onb.days}, cls: 'first'})}</div>` : '';
    if (!ppl.length && !chats.length) { put('h-attn', (onbHtml ? sh('Чаты') + onbHtml : '')); return; }
    put('h-attn', sh('Требуют внимания', {count: ppl.length + (att ? att.total : 0)}) + `<div class="box">${ppl.map(attentionPersonRow).join('')}${chats.map(attentionChatRow).join('')}
      ${att && att.total > 3 ? `<button type="button" class="linkbtn" data-on="allchats">Все проблемы чатов · ${att.total} ›</button>` : ''}</div>${onbHtml}`);
  }));

  if (has('reports')) jobs.push(api('/reports?kind=open').then(d => {
    const c = d.counts, open = c.new + c.in_work;
    if (c.new) todo.push(`${c.new} ${plural(c.new, 'новая жалоба', 'новые жалобы', 'новых жалоб')}`);
    put('h-rep', sh('Жалобы', {count: open || '', link: '#/reports'}) + (open ? `<div class="stats three">
        ${stat('Новых', num(c.new), {tone: c.new ? 'warn' : '', on: 'rep'})}${stat('В работе', num(c.in_work), {on: 'rep'})}${stat('Закрыто', num(c.resolved + c.rejected), {on: 'rep'})}</div>
      <div class="box" style="margin-top:8px">${d.items.slice(0, 3).map(r => row({lead: ava(r.target), title: esc(r.target.name), sub: `${esc(r.reason)} · ${esc(r.chat.title)}`,
        end: pill(r.status_title, r.status === 'new' ? 'warn' : 'info'), href: '#/reports?kind=open&r=' + r.id, cls: 'c2'})).join('')}</div>`
      : `<div class="box">${row({lead: lead('✓', 'ok'), title: 'Очередь пуста', sub: 'Новых жалоб нет', cls: 'first', href: '#/reports'})}</div>`));
  }).catch(e => put('h-rep', sh('Жалобы') + `<p class="err">${esc(e.message)}</p>`)));

  if (has('health')) jobs.push(api('/health').then(h => {
    const tg = h.telegram, bad = tg && !tg.ok, errs = h.errors.count_24h;
    if (bad) todo.unshift('Telegram не отвечает');
    const tone = bad ? 'bad' : errs || h.chats.no_rights ? 'warn' : 'ok';
    put('h-health', sh('Состояние', {link: '#/health'}) + `<div class="box tone-${tone === 'ok' ? '' : tone}">${row({lead: lead(bad ? '!' : tone === 'ok' ? '✓' : '•', tone),
      title: bad ? 'Telegram не отвечает' : tone === 'ok' ? 'Всё работает' : 'Работает, есть замечания',
      sub: [tg && tg.ok ? `Telegram ${tg.ms} мс` : '', `база ${h.database.ms} мс`, `ошибок за сутки ${num(errs)}`, h.queues.broadcasts_running ? 'идёт рассылка' : ''].filter(Boolean).join(' · '),
      href: '#/health', cls: 'first'})}</div>`);
  }).catch(() => {}));

  if (has('metrics')) jobs.push(api('/metrics?days=1').then(m => {
    put('h-metrics', sh('Сегодня', {link: '#/metrics'}) + `<div class="stats four">${stat('Людей', num(m.everyone), {on: 'met'})}${stat('В приложении', num(m.site.visitors), {on: 'met'})}
      ${stat('Команд бота', num(m.bot.commands), {on: 'met'})}${stat('Сообщений', num(m.chats.messages), {on: 'met'})}</div>`);
  }).catch(() => {}));

  on(v, {
    allchats: () => attentionSheet('', '⚠️ Чаты требуют внимания').catch(e => toast(e.message, true)),
    onb: el => onboardingSheet(+el.dataset.days).catch(e => toast(e.message, true)),
    rep: () => go('reports'), met: () => go('metrics'),
  });
  Promise.allSettled(jobs).then(() => {
    const s = v.querySelector('#hsum');
    if (s && ctx.alive()) s.textContent = todo.length ? todo.slice(0, 3).join(' · ') : 'Всё спокойно: срочного нет';
  });
}
route('home', {section: 'home', root: true, title: () => 'Главная', render: homeView});
