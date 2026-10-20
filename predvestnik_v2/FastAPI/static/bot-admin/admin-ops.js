// ── Разделы работы с ботом: метрики, рассылка, промокоды, функции, настройки, состояние, права, владелец чата ──

// ── Метрики ──────────────────────────────────────────────────────────────────

const CURRENCIES = {mora: '🪙 Мора', diamonds: '💎 Алмазы', dark_mora: '🌑 Тёмная мора', zarniki: '✨ Зарники'};
const signed = x => (x > 0 ? '+' : x < 0 ? '−' : '') + num(Math.abs(x));
// Рейтинг строками с полоской доли: на телефоне читается лучше таблицы.
const rankRows = (items, value, title, sub = () => '', href = () => '') => {
  const max = Math.max(1, ...items.map(value));
  return `<div class="list">${items.map(x => `<${href(x) ? `a href="${href(x)}"` : 'div'} class="row" style="display:block;min-height:0">
    <div style="display:flex;gap:10px;align-items:baseline"><span class="row-t"><b style="font-size:14px">${title(x)}</b>${sub(x) ? `<span>${sub(x)}</span>` : ''}</span><b class="num">${num(value(x))}</b></div>
    ${meter(value(x) / max * 100)}</${href(x) ? 'a' : 'div'}>`).join('')}</div>`;
};

async function exportMetrics(days) {   // в браузере файлом, в Telegram (там файлы не скачать) — в буфер
  const headers = {};
  if (INIT) headers['x-init-data'] = INIT;
  try { const s = localStorage.getItem('pv_sess'); if (s) headers['x-session-token'] = s; } catch (_) {}
  const res = await fetch(`${BASE}/bot-admin/api/metrics/export?days=${days}`, {headers});
  if (!res.ok) throw new Error(`Ошибка ${res.status}`);
  const text = await res.text();
  if (INIT) { await copyText(text.replace(/^﻿/, ''), 'Таблица скопирована: вставьте её в Excel или Google Таблицы.'); return; }
  const url = URL.createObjectURL(new Blob([text], {type: 'text/csv;charset=utf-8'}));
  const a = Object.assign(document.createElement('a'), {href: url, download: `metrics-${days}d.csv`});
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

async function metricsView(ctx) {
  let days = +ctx.query.get('days') || PREFS.get('metrics.days', 1);
  if (![1, 7, 30].includes(days)) days = 1;
  PREFS.set('metrics.days', days);
  const m = await ctx.load(`/metrics?days=${days}`);
  if (!ctx.alive()) return;
  const v = ctx.view, s = m.site, b = m.bot, c = m.chats, cmp = m.compare || {};
  const tr = (cur, prev) => m.days === 1 ? '' : trend(cur, prev);
  const series = (daily, f) => m.day_list.map(d => (daily[d] || {})[f] || 0);
  const dmy = d => d.split('-').reverse().join('.');
  const fold = (key, title, count, body, openDef = false) => {
    const open = PREFS.get('fold.' + key, openDef);
    return `<details class="fold" data-fold="${key}" ${open ? 'open' : ''}><summary>${title}${count != null ? ` <span class="cnt">${count}</span>` : ''}</summary>${body}</details>`;
  };
  const eco = Object.entries(m.economy || {}).filter(([k, x]) => CURRENCIES[k] && (x.issued || x.spent));
  const r = m.retention, f = m.funnel;
  v.innerHTML = seg('mdays', [[1, 'Сегодня'], [7, '7 дней'], [30, '30 дней']], m.days, {cls: 'sticky'})
    + `<p class="sub" style="margin:-4px 0 10px">${m.days === 1 ? dmy(m.until) + ' · день ещё идёт (UTC)' : dmy(m.since) + ' — ' + dmy(m.until) + ' · стрелки — к прошлым ' + m.days + ' дн.'}</p>
    <div class="stats four">
      ${stat('👤 Людей', num(m.everyone), {extra: tr(m.everyone, cmp.everyone)})}
      ${stat('📱 В приложении', num(s.visitors), {extra: tr(s.visitors, cmp.visitors), sparkline: m.days > 1 ? series(s.daily, 'users') : null})}
      ${stat('🤖 Команд бота', num(b.commands), {extra: tr(b.commands, cmp.commands), sparkline: m.days > 1 ? series(b.daily, 'users') : null})}
      ${stat('💬 Сообщений', num(c.messages), {extra: tr(c.messages, cmp.messages), sparkline: m.days > 1 ? series(c.daily, 'messages') : null})}</div>
    ${fold('m-app', '📱 Мини-приложение', null, `<div class="stats three">${stat('Посетителей', num(s.visitors))}${stat('Сессий', num(s.sessions))}${stat('На человека', dur(s.avg_seconds_per_visitor))}</div>
      ${bars(m.day_list, s.daily, 'users')}
      ${s.pages.length ? sh('Вкладки') + rankRows(s.pages, x => x.visits, x => esc(x.title), x => `${num(x.users)} чел. · ${dur(x.avg_seconds)} в среднем`) : emptyBox('За период никто не открывал')}
      ${s.subpages.length ? fold('m-sub', 'Разделы внутри вкладок', s.subpages.length, rankRows(s.subpages, x => x.visits, x => esc(x.tab), x => `${num(x.users)} чел.`)) : ''}`, true)}
    ${fold('m-bot', '🤖 Команды бота', null, `<div class="stats three">${stat('В чатах', num(b.commands_group))}${stat('В личке', num(b.commands_private))}${stat('Людей', num(b.users), {extra: tr(b.users, cmp.bot_users)})}</div>
      ${bars(m.day_list, b.daily, 'users')}
      ${b.top.length ? sh('Популярные команды') + rankRows(b.top.slice(0, 12), x => x.total, x => 'бот ' + esc(x.command), x => `в чатах ${num(x.group)} · в личке ${num(x.private)}`) : emptyBox('Команд за период не было')}
      ${b.top_includes_staff ? '<p class="sub">Рейтинг команд включает и аккаунты команды; плитки выше — нет.</p>' : ''}`)}
    ${fold('m-chats', '💬 Чаты', null, `<div class="stats three">${stat('Писали', num(c.users), {extra: tr(c.users, cmp.chat_users)})}${stat('Активных чатов', num(c.chats))}${stat('Сообщений', num(c.messages))}</div>
      ${bars(m.day_list, c.daily, 'messages')}
      ${c.top.length ? sh('Самые активные') + rankRows(c.top, x => x.messages, x => esc(x.title), x => `писали ${num(x.users)}`, x => has('people') ? '#/chat/' + x.id : '') : ''}`)}
    ${fold('m-eco', '💰 Экономика', eco.length || null, eco.length ? eco.map(([k, x]) => `${sh(CURRENCIES[k])}<div class="stats three">${stat('Выдано', num(x.issued))}${stat('Потрачено', num(x.spent))}${stat('Итого', signed(x.net), {tone: x.net > 0 ? 'warn' : ''})}</div>
      ${x.sources.length ? fold('m-eco-in-' + k, 'Откуда пришло', x.sources.length, rankRows(x.sources, y => y.amount, y => esc(y.title))) : ''}
      ${x.sinks.length ? fold('m-eco-out-' + k, 'На что ушло', x.sinks.length, rankRows(x.sinks, y => y.amount, y => esc(y.title))) : ''}`).join('')
      + help('Как считается', '<p>Переводы между игроками не считаются: деньги только переходят от человека к человеку. Аккаунты команды в счёт не входят.</p>') : emptyBox('Движений валюты не было'))}
    ${fold('m-ret', '🔁 Удержание', null, r ? `<div class="stats three">${[['d1', 'Через день'], ['d7', 'За 7 дней'], ['d30', 'За 30 дней']].map(([k, t]) => r[k] && r[k].cohort
      ? stat(t, r[k].percent + '%', {small: `${num(r[k].returned)} из ${num(r[k].cohort)}`}) : stat(t, '—', {small: 'данных нет'})).join('')}</div>
      ${help('Как считается', '<p>Доля новых людей, которые вернулись. «Новый» — впервые замечен в сообщениях чатов или командах бота; у каждого срока своя группа.</p>')}` : emptyBox('Данных нет'))}
    ${fold('m-fun', '🪜 Воронка приложения', null, f && f.steps && f.steps[0].users ? `<div class="list">${f.steps.map(x => x.users == null ? row({title: esc(x.title), sub: 'данных пока нет'})
      : `<div class="row" style="display:block;min-height:0"><div style="display:flex;gap:10px;align-items:baseline"><span class="row-t"><b style="font-size:14px">${esc(x.title)}</b>
        ${x.of_prev != null && x.key !== 'opened' ? `<span>${x.of_prev}% от прошлого шага</span>` : ''}</span><b class="num">${num(x.users)}</b></div>${meter(x.of_first || 0, 'accent')}</div>`).join('')}</div>
      ${f.with_bot_percent == null ? '' : `<p class="sub">Из открывших приложение ещё и пользуются командами бота: ${num(f.with_bot)} (${f.with_bot_percent}%)</p>`}` : emptyBox('За период приложение никто не открывал'))}
    <button type="button" class="btn block mt" data-on="export">⬇ Таблица CSV</button>
    ${help('Что входит в цифры', `<p>В базе ${num(m.players_total)} игроков и ${num(m.chats_total)} чатов с ботом. Уникальные люди — кто открыл приложение, вызвал команду или писал в чате с ботом.</p>
      ${m.excluded ? `<p>Без аккаунтов команды (разработчик, создатель, тестеры): ${num(m.excluded)}.</p>` : ''}`)}`;
  v.addEventListener('toggle', e => { const d = e.target; if (d.dataset && d.dataset.fold) PREFS.set('fold.' + d.dataset.fold, d.open); }, true);
  on(v, {
    mdays: el => { setQuery({days: el.dataset.v}); ctx.refresh(); },
    export: el => busy(el, () => exportMetrics(m.days)),
  });
}
route('metrics', {section: 'metrics', root: true, title: () => 'Метрики', stats: true, render: metricsView});

// ── Рассылка ─────────────────────────────────────────────────────────────────

// Предпросмотр HTML Telegram: всё экранируется, обратно включаются только теги, которые понимает Telegram.
function tgHtml(text) {
  const html = esc(text)
    .replace(/&lt;(\/?)(b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote|tg-spoiler)&gt;/g, '<$1$2>')
    .replace(/&lt;a href=&quot;(https?:\/\/[^&"]*)&quot;&gt;/g, '<a href="$1" target="_blank" rel="noopener">')
    .replace(/&lt;\/a&gt;/g, '</a>');
  // Теги закрываем сами: обрезанный на полуслове текст («<b>жирный…») не должен делать жирными соседние строки.
  const open = [];
  const balanced = html.replace(/<(\/?)([a-z-]+)[^>]*>/g, (m, close, tag) => {
    if (!close) { open.push(tag); return m; }
    const at = open.lastIndexOf(tag);
    if (at < 0) return '';
    return open.splice(at).reverse().map(t => `</${t}>`).join('');
  });
  return balanced + open.reverse().map(t => `</${t}>`).join('');
}

// Выбор людей или чатов поиском: чипы + подсказки. items — массив {id, label}, меняется на месте.
function pickerField(host, {hint: hintText, placeholder, search, items, onChange}) {
  host.innerHTML = `<input placeholder="${esc(placeholder)}" autocomplete="off"/><div class="found list"></div><div class="picks"></div>`;
  const input = $('input', host), found = $('.found', host), chips = $('.picks', host);
  const draw = () => {
    chips.innerHTML = items.length ? items.map((x, i) => `<button type="button" class="chip x" data-un="${i}" aria-label="Убрать ${esc(x.label)}">${x.avatar !== undefined ? ava(x, 'xs') : ''}${esc(x.label)}</button>`).join('')
      : `<span class="sub">${esc(hintText)}</span>`;
  };
  draw();
  chips.onclick = e => { const c = e.target.closest('[data-un]'); if (c) { items.splice(+c.dataset.un, 1); draw(); onChange(); } };
  let timer, seq = 0;
  input.oninput = () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { found.innerHTML = ''; return; }
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const list = (await search(q)).filter(x => !items.some(y => y.id === x.id));
        if (mine !== seq) return;
        found.innerHTML = list.map((x, i) => row({lead: x.avatar !== undefined ? ava(x, 'sm') : x.chat ? chatAva({id: x.id, title: x.label}, 'sm') : '', title: esc(x.label), sub: String(x.id), on: 'add', data: {i}, chev: false})).join('')
          || '<p class="sub">Не найдено</p>';
        found._list = list;
      } catch (e) { found.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
    }, 280);
  };
  found.onclick = e => {
    const b = e.target.closest('[data-i]');
    if (!b || !found._list) return;
    items.push(found._list[+b.dataset.i]);
    found.innerHTML = ''; input.value = '';
    draw(); onChange();
  };
}
const searchChats = async q => (await api(`/chats?q=${encodeURIComponent(q)}`)).items.map(c => ({id: c.id, label: (c.admin ? '🛡 ' : '') + c.title, chat: true}));
const searchPlayers = async q => (await api(`/search?q=${encodeURIComponent(q)}`)).players
  .map(u => ({id: u.id, label: u.username ? '@' + u.username : u.name || 'id' + u.id, username: u.username, name: u.name, avatar: u.avatar}));

// Черновик живёт, пока открыта админка: обновление списка или ошибка не стирают набранное.
const BC = {kind: 'players', chats: [], players: [], active: '', chatKind: '', vip: '', newDays: '', minMsg: '', text: '', html: true,
  btnText: '', btnUrl: '', later: false, at: '', count: null, title: ''};
function bcSegment() {
  const s = {kind: BC.kind};
  if (BC.chats.length) s.chats = BC.chats.map(x => x.id);
  if (BC.kind === 'chats' && (BC.chatKind === 'main' || BC.chatKind === 'admin')) s.chat_kind = BC.chatKind;
  if (+BC.active) s.active_days = +BC.active;
  if (BC.kind === 'players') {
    if (BC.vip !== '') s.vip = BC.vip === '1';
    if (+BC.newDays) s.new_days = +BC.newDays;
    if (+BC.minMsg) s.min_messages = +BC.minMsg;
    if (BC.players.length) s.players = BC.players.map(x => x.id);
  }
  return s;
}
const bcButton = () => (BC.btnText.trim() || BC.btnUrl.trim()) ? {text: BC.btnText.trim(), url: BC.btnUrl.trim()} : null;
const BC_TONE = {running: 'info', scheduled: 'accent', done: 'ok', sent: 'ok', stopped: '', interrupted: 'warn', failed: 'bad'};
const bubble = (text, html, btn) => `<div class="chatbg"><div class="bubble ${text ? '' : 'empty-b'}">${text ? (html ? tgHtml : esc)(text) : 'Здесь будет сообщение'}</div>${btn ? `<div class="bubble-btn">${esc(btn.text || '…')}</div>` : ''}</div>`;

function bcHistoryRow(b) {
  const resumable = b.status === 'interrupted' || (b.status === 'stopped' && b.total > b.sent + b.failed);
  const share = b.total ? (b.sent + b.failed) / b.total * 100 : 0;
  return `<div class="row" style="display:block">
    <div style="display:flex;gap:8px;align-items:center">${pill(b.status_title, BC_TONE[b.status] || '')}<span class="sub" style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(b.audience_title)}</span>
      <span class="sub">${b.status === 'scheduled' ? 'в ' + when(b.scheduled_at) : ago(b.created_at)}</span></div>
    <div class="clamp" style="margin-top:6px;font-size:14px;white-space:pre-wrap">${(b.html ? tgHtml : esc)(b.text.length > 220 ? b.text.slice(0, 220) + '…' : b.text)}</div>
    ${b.status !== 'scheduled' ? `<div class="sub" style="margin-top:4px">Дошло ${num(b.sent)} из ${num(b.total)}${b.failed ? ` · не дошло <b style="color:var(--bad)">${num(b.failed)}</b>` : ''} · ${esc(b.actor)}</div>${b.status === 'running' ? meter(share, 'accent') : ''}` : `<div class="sub">${esc(b.actor)}</div>`}
    <div class="btns" style="margin-top:8px">
      ${b.status === 'running' ? `<button type="button" class="btn sm danger" data-on="bstop" data-v="${b.id}">⏹ Остановить</button>` : ''}
      ${b.status === 'scheduled' ? `<button type="button" class="btn sm danger" data-on="bstop" data-v="${b.id}">✖ Отменить</button>` : ''}
      ${resumable ? `<button type="button" class="btn sm" data-on="bresume" data-v="${b.id}">▶ Продолжить</button>` : ''}
      ${b.status !== 'scheduled' ? `<button type="button" class="btn sm" data-on="breport" data-v="${b.id}">Отчёт</button>` : ''}
      <button type="button" class="btn sm ghost" data-on="breuse" data-v="${b.id}" title="Взять этот текст в новую рассылку">↻ Текст в черновик</button></div></div>`;
}
async function bcReport(id, refresh) {
  const rep = await api(`/broadcasts/${id}`), b = rep.broadcast;
  sheet(`Рассылка №${b.id}`, `<p class="sub" style="margin-top:0">${esc(b.audience_title)} · ${esc(b.status_title)}</p>
    <div class="stats">${stat('Дошло', num(rep.sent), {tone: 'ok'})}${stat('Не дошло', num(rep.failed), {tone: rep.failed ? 'bad' : ''})}</div>
    ${rep.pending ? `<p class="sub">Ещё не отправлено: ${num(rep.pending)}</p>` : ''}
    ${rep.reasons.length ? sh('Почему не дошло') + `<div class="list">${rep.reasons.map(r => row({title: esc(r.title), end: `<b>${num(r.count)}</b>`})).join('')}</div>` : ''}
    ${rep.failed_sample.length ? sh('Кому не дошло', {count: rep.failed > rep.failed_sample.length ? `первые ${rep.failed_sample.length}` : null}) + `<div class="list">${rep.failed_sample.map(x => row({lead: ava(x, 'sm'), title: esc(nameOf(x)), sub: esc(x.reason)})).join('')}</div>` : ''}
    ${sh('Текст')}${bubble(b.text, b.html, b.button)}`,
    rep.failed ? 'Повторить недоставленным' : 'Закрыть', async () => {
      if (!rep.failed) return;
      const res = await post(`/broadcasts/${id}/retry`);
      toast(res.message, {ok: true}); refresh();
    }, {cancelText: 'Закрыть'});
}

async function broadcastView(ctx) {
  const data = await ctx.load('/broadcasts', {cache: false});
  if (!ctx.alive()) return;
  const v = ctx.view;
  let items = data.items, templates = data.templates || [];
  const numberField = (id, label, key) => field(label, `<input id="${id}" type="number" min="0" inputmode="numeric" value="${esc(BC[key])}" placeholder="Любые" data-input="seg" data-k="${key}"/>`);
  v.innerHTML = `${ME.creator ? `<div class="box">${row({lead: lead('📰', 'accent'), title: 'Важное обновление проекта', sub: 'Одна новость со скриншотом в официальную тему', on: 'official', cls: 'first'})}</div>` : ''}
    <div class="step"><i>1</i><h3>Кому</h3></div>
    ${seg('bkind', data.audiences.map(a => [a.key, a.title, num(data.sizes[a.key] || 0)]), BC.kind)}
    <details class="fold" id="bfold" ${BC.chats.length || BC.players.length || BC.active || BC.vip || BC.newDays || BC.minMsg || BC.chatKind ? 'open' : ''}><summary>Уточнить получателей</summary><div id="bseg"></div></details>
    <div class="step"><i>2</i><h3>Текст</h3></div>
    ${templates.length ? field('', `<div class="chipset scroll" id="btpls">${templates.map(t => `<button type="button" class="chip" data-on="tpl" data-v="${t.id}">📄 ${esc(t.title)}</button>`).join('')}</div>`) : ''}
    <div class="field"><label for="btext">Сообщение <span class="counter" id="bcnt">0 / 3500</span></label><textarea id="btext" maxlength="3500" rows="6" data-input="draw" placeholder="Что хотите сказать игрокам"></textarea></div>
    <label class="row" style="min-height:52px;border-top:0"><span class="row-t"><b>HTML-разметка Telegram</b><span>&lt;b&gt;, &lt;i&gt;, &lt;u&gt;, &lt;s&gt;, &lt;code&gt;, &lt;blockquote&gt;, &lt;tg-spoiler&gt;, &lt;a href="…"&gt;</span></span>${toggle('id="bhtml" data-change="draw"', BC.html, 'HTML-разметка')}</label>
    <details class="fold" ${BC.btnText || BC.btnUrl ? 'open' : ''}><summary>Кнопка под сообщением</summary><div class="grid2">
      ${field('Подпись', '<input id="bbtext" maxlength="64" placeholder="Например: Играть" data-input="draw"/>')}${field('Ссылка', '<input id="bburl" maxlength="512" placeholder="https://t.me/…" data-input="draw" inputmode="url"/>')}</div></details>
    <div class="btns" style="margin:10px 0"><button type="button" class="btn sm ghost" data-on="tplsave">💾 Сохранить как шаблон</button>
      <button type="button" class="btn sm ghost" id="btpldel" data-on="tpldel" hidden>Удалить шаблон</button></div>
    ${sh('Так увидят')}<div id="bprev"></div>
    <div class="step"><i>3</i><h3>Когда</h3></div>
    ${seg('blater', [['0', 'Сейчас'], ['1', 'Позже']], BC.later ? '1' : '0')}
    <div class="field" id="batwrap" ${BC.later ? '' : 'hidden'}><label for="bat">Когда (по вашему времени)</label><input type="datetime-local" id="bat" data-input="draw" value="${esc(BC.at)}"/></div>
    ${help('Кому дойдёт', '<p>В личку дойдёт только тем, кто хоть раз открывал диалог с ботом. Заблокированным и забаненным везде не отправляется. Получателей отложенной рассылки бот считает в момент отправки.</p>')}
    ${sh('История', {count: items.length})}<div id="bhist" class="list"></div>`;
  ctx.mount();
  const $v = sel => v.querySelector(sel);
  $v('#btext').value = BC.text; $v('#bbtext').value = BC.btnText; $v('#bburl').value = BC.btnUrl;
  let tplOn = null;

  // ── Получатели: счётчик пересчитывается с задержкой; ответ на старый запрос не перетирает новый ──
  let countTimer, countSeq = 0, running = false;
  const paintBar = () => ctx.bar(`<div><b id="bcount">${BC.count == null ? 'Считаем…' : `👥 ${num(BC.count)}`}</b>
      ${running ? '<span id="bbusy">Идёт другая рассылка</span>' : BC.count == null ? '' : `${plural(BC.count, 'получатель', 'получателя', 'получателей')} · ${esc(BC.title || '')}`}</div>
    <div class="btns"><button type="button" class="btn sm ghost" id="btest" data-on="test">Себе</button>
      <button type="button" class="btn sm primary" id="bgo" data-on="go" ${running ? 'disabled' : ''}>${BC.later ? 'Запланировать ›' : 'Проверить ›'}</button></div>`, barHandlers);
  const refreshCount = () => {
    clearTimeout(countTimer);
    countTimer = setTimeout(async () => {
      const mine = ++countSeq;
      try {
        const res = await post('/broadcasts/preview', {segment: bcSegment()});
        if (mine === countSeq && ctx.alive()) { BC.count = res.count; BC.title = res.title; paintBar(); }
      } catch (e) { if (mine === countSeq && ctx.alive()) { BC.count = null; BC.title = e.message; paintBar(); } }
    }, 300);
  };
  const drawSegment = () => {
    const players = BC.kind === 'players';
    $v('#bseg').innerHTML = `<div class="field"><label>${players ? 'Только участники этих чатов' : 'Только эти чаты'}</label><div id="bpchats"></div></div>
      ${players ? '' : field('Какие чаты', `<select id="bckind" data-change="seg" data-k="chatKind">${[['', 'Все — основные и админ-чаты'], ['main', '🏠 Только основные'], ['admin', '🛡 Только админ-чаты']].map(([x, t]) => `<option value="${x}" ${BC.chatKind === x ? 'selected' : ''}>${t}</option>`).join('')}</select>`, 'Админ-чаты определяются по связке с основным чатом.')}
      ${players ? `<div class="field"><label>Только эти игроки</label><div id="bpplayers"></div></div>` : ''}
      <div class="grid2">${numberField('bactive', players ? 'Писали хоть где-то за N дней' : 'Писали в чате за N дней', 'active')}
        ${players ? field('VIP', `<select id="bvip" data-change="seg" data-k="vip">${[['', 'Не важно'], ['1', 'Только с VIP'], ['0', 'Только без VIP']].map(([x, t]) => `<option value="${x}" ${BC.vip === x ? 'selected' : ''}>${t}</option>`).join('')}</select>`)
          + numberField('bnew', 'Новички за N дней', 'newDays') + numberField('bmin', 'Сообщений всего — от', 'minMsg') : ''}</div>`;
    pickerField($v('#bpchats'), {hint: players ? 'Любые чаты' : 'Все чаты бота · 🛡 — админ-чат', placeholder: 'Найти чат по названию или ID', search: searchChats, items: BC.chats, onChange: refreshCount});
    if (players) pickerField($v('#bpplayers'), {hint: 'Любые игроки', placeholder: 'Найти игрока по @нику или ID', search: searchPlayers, items: BC.players, onChange: refreshCount});
    refreshCount();
  };
  const draw = () => {
    BC.text = $v('#btext').value; BC.html = $v('#bhtml').checked; BC.btnText = $v('#bbtext').value; BC.btnUrl = $v('#bburl').value; BC.at = $v('#bat').value;
    $v('#bprev').innerHTML = bubble(BC.text, BC.html, bcButton());
    $v('#bcnt').textContent = `${BC.text.length} / 3500`;
    $v('#batwrap').hidden = !BC.later;
    $v('#btpldel').hidden = !tplOn;
  };
  // ── История: перерисовывается отдельно, пока идёт рассылка; опрос живёт, только пока открыт этот экран ──
  let poll;
  const drawHistory = () => {
    clearTimeout(poll);
    running = items.some(b => b.status === 'running');
    $v('#bhist').innerHTML = items.length ? items.map(bcHistoryRow).join('') : emptyBox('Рассылок ещё не было');
    paintBar();
    if (running || items.some(b => b.status === 'scheduled')) poll = setTimeout(async () => {
      if (!ctx.alive()) return;
      try { items = (await api('/broadcasts')).items; } catch (_) {}
      if (ctx.alive()) drawHistory();
    }, running ? 4000 : 30000);
  };
  const reload = async () => { items = (await api('/broadcasts')).items; drawHistory(); };
  const barHandlers = {
    test: el => busy(el, async () => {
      if (!BC.text.trim()) { toast('Напишите текст.', true); $v('#btext').focus(); return; }
      toast((await post('/broadcasts/test', {text: BC.text.trim(), html: BC.html, button: bcButton()})).message, {ok: true});
    }),
    go: () => {
      const text = BC.text.trim();
      if (!text) { toast('Напишите текст.', true); $v('#btext').focus(); return; }
      if (BC.later && !BC.at) { toast('Выберите время отправки.', true); $v('#bat').focus(); return; }
      const rid = newRid();   // один ключ на окно подтверждения: повтор после потерянного ответа не разошлёт дважды
      openSheet({title: BC.later ? 'Запланировать рассылку?' : 'Отправить рассылку?', sub: BC.count == null ? 'Получатели не посчитаны' : `${num(BC.count)} получателей`,
        body: summary([['Кому', esc(BC.title || '')], ['Когда', BC.later ? when(BC.at) : 'сейчас, отменить отправленное нельзя']], false) + `<div style="margin-top:12px">${bubble(text, BC.html, bcButton())}</div>`,
        actions: [{label: BC.later ? 'Запланировать' : 'Отправить', run: async () => {
          const res = await post('/broadcasts', {audience: BC.kind, segment: bcSegment(), text, html: BC.html, button: bcButton(), request_id: rid,
            scheduled_at: BC.later ? new Date(BC.at).toISOString() : null});
          toast(res.message || 'Готово', {ok: true});
          Object.assign(BC, {text: '', btnText: '', btnUrl: '', later: false, at: ''});
          closeSheets(); ctx.refresh(); return 'keep';
        }}, {label: 'Отмена', kind: '', run: null}]});
    },
  };
  on(v, {
    bkind: el => { BC.kind = el.dataset.v; $$('[data-on="bkind"]', v).forEach(b => b.setAttribute('aria-selected', String(b === el))); drawSegment(); },
    seg: el => { BC[el.dataset.k] = el.value; refreshCount(); },
    draw: () => draw(),
    blater: el => { BC.later = el.dataset.v === '1'; $$('[data-on="blater"]', v).forEach(b => b.setAttribute('aria-selected', String(b === el))); draw(); paintBar(); },
    tpl: el => {
      const t = templates.find(x => String(x.id) === el.dataset.v); if (!t) return;
      tplOn = t; $$('#btpls .chip', v).forEach(c => c.setAttribute('aria-pressed', String(c === el)));
      $v('#btext').value = t.text; $v('#bhtml').checked = t.html; $v('#bbtext').value = t.button ? t.button.text : ''; $v('#bburl').value = t.button ? t.button.url : '';
      draw();
    },
    tplsave: () => {
      if (!$v('#btext').value.trim()) { toast('Сначала напишите текст.', true); return; }
      sheet('Сохранить как шаблон', field('Название', '<input id="btitle" maxlength="60" placeholder="Например: Новости недели"/>', 'Сохранятся текст, разметка и кнопка. Получатели и время — нет.'), 'Сохранить', async p => {
        const res = await post('/broadcasts/templates', {title: p.q('#btitle').value, text: $v('#btext').value.trim(), html: $v('#bhtml').checked, button: bcButton()});
        templates = res.items; toast(res.message, {ok: true}); ctx.refresh();
      });
    },
    tpldel: async () => {
      const t = tplOn;
      if (!t || !await ask('Удалить шаблон?', hint(`«${esc(t.title)}» пропадёт у всей команды.`), 'Удалить')) return;
      try { templates = (await api(`/broadcasts/templates/${t.id}`, {method: 'DELETE'})).items; toast('Шаблон удалён.', {ok: true}); ctx.refresh(); }
      catch (e) { toast(e.message, true); }
    },
    official: () => officialUpdatesOpen().catch(e => toast(e.message, true)),
    bstop: async el => { if (!await ask('Остановить рассылку?', hint('Уже отправленное не отменить. Остаток можно будет продолжить.'), 'Остановить')) return; busy(el, async () => { toast((await post(`/broadcasts/${el.dataset.v}/stop`)).message, {ok: true}); await reload(); }); },
    bresume: el => busy(el, async () => { toast((await post(`/broadcasts/${el.dataset.v}/resume`)).message, {ok: true}); await reload(); }),
    breport: el => busy(el, () => bcReport(el.dataset.v, reload)),
    breuse: el => {
      const b = items.find(x => String(x.id) === el.dataset.v); if (!b) return;
      $v('#btext').value = b.text; $v('#bhtml').checked = !!b.html; $v('#bbtext').value = b.button ? b.button.text : ''; $v('#bburl').value = b.button ? b.button.url : '';
      draw(); $v('#btext').scrollIntoView({block: 'center', behavior: 'smooth'}); toast('Текст в черновике: проверьте получателей');
    },
  });
  drawSegment(); draw(); drawHistory();
}
route('broadcast', {section: 'broadcast', root: true, title: () => 'Рассылка', render: broadcastView});

// Важные обновления проекта (только создатель): черновик → предпросмотр → публикация → сверка.
let OFFICIAL_POSTS = [];
const OFFICIAL_KINDS = {pets: 'Питомцы', rhythm: 'Ритм', mafia: 'Мафия', family: 'Родословная', purge: 'Чистка'};
const OFFICIAL_STATES = {draft: 'Черновик', sending: 'Отправляется', sent: 'Доставлено', unknown: 'Нужна сверка', failed: 'Не отправлено'};
const OFFICIAL_IMAGES = {'pets-forecast.png': 'Прогноз питомца · с пометкой', 'rhythm-analysis.png': 'Разбор Ритма · с пометкой', 'family-tree.png': 'Родословная · с пометкой', 'mafia-review.png': 'Разбор Мафии', 'purge-web.png': 'Чистка на сайте'};
async function officialUpdatesOpen() {
  const d = await api('/official-updates');
  OFFICIAL_POSTS = d.items;
  const requestKey = `update-${Date.now()}-${newRid().slice(0, 8)}`;
  const p = openSheet({title: 'Важное обновление', sub: 'Не чаще одного поста в сутки', body: `<p class="sub" style="margin-top:0">Куда: <a href="${esc(d.target)}" target="_blank" rel="noopener">тема обновлений официальной группы</a>. Мелкие изменения объединяйте.</p>
    ${d.topic_verified ? '' : callout('warn', '⚠️', '<b>Тема не подтверждена</b><small>Рабочий бот ещё не зафиксировал сообщение в теме. До подтверждения публикация заблокирована.</small>')}
    ${field('Раздел', `<select id="ou-kind">${d.kinds.map(k => `<option value="${k}">${esc(OFFICIAL_KINDS[k] || k)}</option>`).join('')}</select>`)}
    ${field('Короткая новость', '<textarea id="ou-caption" rows="5" minlength="30" maxlength="900" placeholder="Что стало удобнее, где попробовать, один следующий шаг"></textarea>')}
    ${field('Проверенный скриншот', `<select id="ou-image"><option value="">Выберите изображение</option>${d.images.map(n => `<option value="${esc(n)}">${esc(OFFICIAL_IMAGES[n] || n)}</option>`).join('')}</select>`, 'Реальный интерфейс без личных данных, одна-две пометки.')}
    ${d.items.length ? sh('Последние публикации') + `<div class="list">${d.items.map((x, i) => row({title: esc(OFFICIAL_KINDS[x.kind] || x.kind), sub: esc(x.caption.slice(0, 90)) + (x.error ? ' · ' + esc(x.error) : ''),
      end: pill(OFFICIAL_STATES[x.status] || x.status, x.status === 'sent' ? 'ok' : x.status === 'failed' ? 'bad' : x.status === 'unknown' ? 'warn' : ''), on: 'post', data: {i}})).join('')}</div>` : ''}`,
    actions: [{label: 'Сохранить и посмотреть', run: async s => {
      const created = await post('/official-updates/draft', {release_key: requestKey, kind: s.q('#ou-kind').value, caption: s.q('#ou-caption').value.trim(), image_name: s.q('#ou-image').value});
      OFFICIAL_POSTS.unshift(created); officialUpdatesPreview(0); return 'keep';
    }}]});
  on(p.el, {post: el => { const x = OFFICIAL_POSTS[+el.dataset.i]; if (['sending', 'unknown'].includes(x.status)) officialUpdatesReconcile(+el.dataset.i); else officialUpdatesPreview(+el.dataset.i); }});
}
function officialUpdatesPreview(index) {
  const x = OFFICIAL_POSTS[index]; if (!x) return;
  openSheet({title: 'Предпросмотр публикации', sub: OFFICIAL_STATES[x.status] || x.status, body: `<div class="official"><img src="${BASE}/static/announcements/${encodeURIComponent(x.image_name)}" alt="Скриншот к обновлению"/></div>
    <div class="bubble" style="max-width:100%">${esc(x.caption)}</div><div class="bubble-btn">${esc(x.button)}</div>
    <p class="sub">Бот отправит изображение, подпись и одну кнопку в официальную тему.</p>`,
    actions: [x.status === 'sent' ? {label: 'Уже опубликовано', kind: '', run: null} : {label: 'Опубликовать в теме', run: async () => {
      const result = await post(`/official-updates/${encodeURIComponent(x.release_key)}/publish`, {expected_digest: x.content_digest});
      toast(result.replayed ? 'Этот пост уже был опубликован.' : 'Публикация доставлена.', {ok: true});
    }}]});
}
function officialUpdatesReconcile(index) {
  const x = OFFICIAL_POSTS[index]; if (!x) return;
  openSheet({title: 'Сверить публикацию', body: `<p class="sub" style="margin-top:0">Откройте <a href="https://t.me/predvestnik_official/4" target="_blank" rel="noopener">тему обновлений</a>. При потерянном ответе пост мог быть доставлен. Ничего повторно не отправляется.</p>
    ${field('Проверенный результат', '<select id="ou-resolution"><option value="">Выберите</option><option value="sent">Пост найден</option><option value="absent">Поста точно нет</option></select>')}
    ${field('Номер найденного сообщения', '<input id="ou-message" type="number" min="1" placeholder="Последнее число в ссылке сообщения"/>')}
    ${field('Как проверено', '<textarea id="ou-reason" minlength="12" maxlength="300"></textarea>')}`,
    actions: [{label: 'Записать сверку', run: async s => {
      const resolution = s.q('#ou-resolution').value;
      if (!resolution) throw new Error('Выберите результат проверки.');
      await post(`/official-updates/${encodeURIComponent(x.release_key)}/reconcile`, {expected_digest: x.content_digest, message_id: resolution === 'sent' ? Number(s.q('#ou-message').value) : null,
        confirmed_absent: resolution === 'absent', reason: s.q('#ou-reason').value.trim()});
      toast('Сверка записана.', {ok: true});
    }}]});
}

// ── Промокоды ────────────────────────────────────────────────────────────────

let OPTIONS = null;
function promoState(p) {
  if (p.legacy) return ['старый формат', 'warn'];
  const now = Date.now();
  if (!p.is_active) return ['выключен', ''];
  if (p.valid_until && Date.parse(p.valid_until) < now) return ['истёк', ''];
  if (p.valid_from && Date.parse(p.valid_from) > now) return ['ещё не начался', 'warn'];
  if (p.max_activations && p.activations >= p.max_activations) return ['исчерпан', ''];
  return ['работает', 'ok'];
}
const promoStatus = p => pill(...promoState(p));

async function promoList(ctx) {
  const q = ctx.query.get('q') || '';
  const v = ctx.view;
  v.innerHTML = `<div class="search sticky">${icon('search')}<input id="pq" type="search" placeholder="Поиск по коду" value="${esc(q)}" autocomplete="off"/></div><div id="plist"></div>`;
  ctx.bar(`<div><b>Промокоды</b>Награды игрокам по коду</div><div class="btns"><a class="btn sm" href="#/promo/bulk">Пачка</a><a class="btn sm primary" href="#/promo/new">+ Новый</a></div>`);
  let seq = 0;
  const loadList = async query => {
    const mine = ++seq;
    const {items} = await ctx.load(`/promo?q=${encodeURIComponent(query)}`);
    if (!ctx.alive() || mine !== seq) return;
    v.querySelector('#plist').innerHTML = items.length ? `<div class="list">${items.map(p => {
      const [t, tone] = promoState(p);
      return `<div class="row"><a href="#/promo/${encodeURIComponent(p.code)}" class="row-t" style="color:inherit"><b><span class="code">${esc(p.code)}</span> ${pill(t, tone)}</b>
        <span>${p.rewards_text.length ? esc(p.rewards_text.join(' · ')) : 'наград нового формата нет'}</span>
        <span>${num(p.activations)}${p.max_activations ? ' из ' + num(p.max_activations) : ''} активаций${p.allowed_chats.length ? ' · чатов: ' + p.allowed_chats.length : ''}${p.valid_until ? ' · до ' + when(p.valid_until) : ''}</span>
        ${p.max_activations ? meter(p.activations / p.max_activations * 100) : ''}</a>
        <button type="button" class="ib" data-on="copy" data-v="${esc(p.code)}" aria-label="Копировать код ${esc(p.code)}">${icon('copy')}</button></div>`;
    }).join('')}</div>` : emptyBox(query ? 'Ничего не нашлось' : 'Промокодов нет', query ? '' : 'Создайте первый кнопкой «+ Новый».');
  };
  on(v, {copy: el => copyText(el.dataset.v, 'Код скопирован')});
  let timer;
  v.querySelector('#pq').addEventListener('input', e => { clearTimeout(timer); timer = setTimeout(() => { setQuery({q: e.target.value.trim()}); loadList(e.target.value.trim()).catch(err => toast(err.message, true)); }, 280); });
  await loadList(q);
}
route('promo', {section: 'promo', root: true, title: () => 'Промокоды', render: promoList});

const SPENT_TITLES = [['mora', 'мора'], ['diamonds', 'алмазов'], ['essence', 'эссенции'], ['zarniki', 'зарников'], ['vip_days', 'дн. VIP']];
async function promoView(ctx) {
  const code = ctx.params.code;
  const p = await ctx.load(`/promo/${encodeURIComponent(code)}`, {cache: false});
  if (!ctx.alive()) return;
  ctx.title(p.code, 'Промокод');
  const s = p.stats, [st, tone] = promoState(p);
  const spent = s ? SPENT_TITLES.filter(([k]) => s.spent && s.spent[k] != null && +s.spent[k] > 0).map(([k, t]) => `${num(s.spent[k])} ${t}`) : [];
  ctx.view.innerHTML = `<div class="hero">${lead('🎟', tone || '')}<div><h2 class="code">${esc(p.code)}</h2><div class="pills">${pill(st, tone)}</div>
      ${p.note ? `<p class="sub" style="margin:6px 0 0">${esc(p.note)}</p>` : ''}</div></div>
    ${(p.warnings || []).map(w => callout('warn', '⚠️', esc(w))).join('')}
    <div class="btns grow"><button type="button" class="btn" data-on="copy" data-v="${esc(p.code)}">${icon('copy')} Код</button>
      <button type="button" class="btn" data-on="copy" data-v="бот промокод ${esc(p.code)}" title="Что игроку написать в чате">${icon('copy')} Команда</button></div>
    ${sh('Награда')}<div class="pills">${p.rewards_text.map(r => pill(r, 'accent', true)).join('') || '<span class="sub">Нет наград нового формата — пересохраните код.</span>'}</div>
    ${s ? `${sh('Как идёт')}<div class="stats">${stat('Активаций', num(s.activations), {small: s.limit ? 'из ' + num(s.limit) : 'без лимита'})}${s.left != null ? stat('Осталось', num(s.left), {tone: s.left === 0 ? 'warn' : ''}) : stat('В чатах / в личке', `${num(s.chats)} / ${num(s.private)}`)}</div>
      ${s.limit ? meter(s.activations / s.limit * 100, 'accent') : ''}
      <p class="sub">${s.first_at ? `Первая ${ago(s.first_at)} · последняя ${ago(s.last_at)}` : 'Пока никто не активировал'}${spent.length ? ' · уже выдано: ' + spent.map(esc).join(', ') : ''}</p>
      ${s.activations ? bars(s.per_day.map(d => d.day), Object.fromEntries(s.per_day.map(d => [d.day, {n: d.n}])), 'n') : ''}` : ''}
    ${sh('Условия')}<div class="list">
      ${row({lead: lead('🔢'), title: p.max_activations ? `${num(p.max_activations)} активаций` : 'Без лимита'})}
      ${row({lead: lead('🗓'), title: p.valid_from || p.valid_until ? `${p.valid_from ? 'с ' + when(p.valid_from) + ' ' : ''}${p.valid_until ? 'до ' + when(p.valid_until) : ''}` : 'Без срока'})}
      ${row({lead: lead('💬'), title: p.chats.length ? 'Только в чатах' : 'Во всех чатах и в личке', sub: p.chats.map(c => esc(c.title)).join(', ')})}
      ${p.allowed_users.length ? row({lead: lead('👤'), title: 'Только для игроков', sub: p.allowed_users.join(', ')}) : ''}
      ${row({lead: lead('📱'), title: p.show_in_app && !p.chats.length ? 'Виден в Mini App' : p.allowed_users.length && !p.chats.length ? 'В Mini App — только этим игрокам' : 'В Mini App не показывается'})}</div>
    ${sh('Кто активировал', {count: p.redemptions.length})}
    ${p.redemptions.length ? `<div class="list">${p.redemptions.map(r => row({lead: ava({id: r.user_id, username: r.username, avatar: r.avatar}, 'sm'), title: r.username ? '@' + esc(r.username) : 'id' + r.user_id,
      sub: `${r.chat_id ? esc(r.chat_title || r.chat_id) : 'личка'} · ${ago(r.at)}${(r.granted || []).length ? ' · ' + esc(r.granted.join(', ')) : ''}`, href: has('people') ? '#/player/' + r.user_id : ''})).join('')}</div>` : emptyBox('Пока никто')}`;
  ctx.bar(`<div><b>${esc(p.code)}</b>${esc(st)}</div><div class="btns"><button type="button" class="btn sm ${p.is_active ? 'danger' : ''}" data-on="toggle">${p.is_active ? 'Выключить' : 'Включить'}</button>
    <a class="btn sm primary" href="#/promo/${encodeURIComponent(p.code)}/edit">Изменить</a></div>`, {
    toggle: async el => {
      if (p.is_active && !await ask('Выключить промокод?', hint('Игроки не смогут его активировать, пока не включите снова.'), 'Выключить')) return;
      busy(el, async () => { await post(`/promo/${encodeURIComponent(p.code)}/active`, {active: !p.is_active}); toast(p.is_active ? 'Выключен' : 'Включён', {ok: true}); CACHE.delete('/promo?q='); ctx.refresh(); });
    }});
  on(ctx.view, {copy: el => copyText(el.dataset.v, el.dataset.v.startsWith('бот') ? 'Команда скопирована' : 'Код скопирован')});
}
route('promo/:code', {section: 'promo', up: () => 'promo', title: p => p.code, render: promoView});

function localInput(iso) {
  if (!iso) return '';
  const d = new Date(iso), pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
// Выбор образа для награды: сетка мини-профилей в цветах образа, фильтр по тиру и поиск.
const SKIN_SLOTS = [['title', 'Титул'], ['name_glow', 'Ник'], ['avatar_frame', 'Рамка'], ['avatar_halo', 'Ореол'], ['profile_bg', 'Фон'], ['card_fx', 'Частицы']];
const FRAME_LINE = {ring: 'solid', dash: 'dashed', double: 'double', seg: 'dotted', drip: 'solid'};
const TIER_TITLES = {D: 'D · обычные', C: 'C · необычные', B: 'B · редкие', A: 'A · очень редкие', S: 'S · эпические', SS: 'SS · легендарные', SSS: 'SSS · высшие'};
function skinArt(k) {
  const t = k.tokens || {}, acc = t['--v3-acc'] || (k.pal || [])[0] || '#8b7cf6', bg = t['--v3-bg'] || k.bg || '#0e0f14';
  const ink = t['--v3-ink'] || '#f4f5f8', line = FRAME_LINE[k.frame] || 'solid';
  return `<span class="skin-art" style="background:${t['--v3-wash'] ? esc(t['--v3-wash']) + ',' : ''}${esc(bg)};--sa:${esc(acc)};--sb:${esc(bg)};--si:${esc(ink)};--sl:${line}">
    <i class="skin-av"></i><span class="skin-nick">${esc((k.items && k.items.title) || k.name)}</span><b class="skin-t">${esc(k.tier)}</b></span>`;
}
function skinTags(k) {
  const h = (k.holders || [])[0];
  return [k.exclusive ? (h ? pill('🌟 личный · у ' + h.name, 'warn') : pill('🌟 личный · свободен', 'ok')) : '', k.set_name ? pill('🧩 ' + k.set_name, '', true) : '',
    k.season ? pill('🎃 сезонный' + (k.season_name ? ' · ' + k.season_name : ''), 'warn') : ''].join('');
}
const skinCard = (k, onn, dim = false, tag = 'button') => `<${tag} ${tag === 'button' ? 'type="button"' : ''} class="skin ${onn ? 'on' : ''} ${dim ? 'dim' : ''}" data-skin="${esc(k.id)}" aria-pressed="${onn}" ${dim ? 'disabled' : ''}>
  ${skinArt(k)}<span class="skin-n">${esc(k.name)}</span><span class="skin-b">${esc(k.blurb || '')}</span><span class="pills">${skinTags(k)}</span></${tag}>`;
function skinDetail(k) {
  if (!k) return '<p class="sub">Нажмите на образ, чтобы посмотреть, из чего он состоит.</p>';
  return `<div class="skin-detail">${skinArt(k)}<div><b>${esc(k.name)}</b> <span class="sub">· ${esc(TIER_TITLES[k.tier] || k.tier)}</span>
    <div class="sub" style="margin:4px 0 6px">${esc(k.blurb || '')}</div><div class="pills">${skinTags(k)}</div>
    ${k.exclusive ? '<p class="sub">Достаётся одному игроку: промокод на 1 активацию или для одного игрока. Занятый образ сначала отзывают у владельца.</p>' : ''}
    <div class="skin-items">${SKIN_SLOTS.filter(([key]) => k.items && k.items[key]).map(([key, label]) => `<span><small>${label}</small>${esc(k.items[key])}</span>`).join('')}</div></div></div>`;
}
function skinPicker(currentId, onPick, {noPrivate = false} = {}) {
  const all = OPTIONS.skins, priv = noPrivate ? [] : OPTIONS.private_skins || [], pool = [...all, ...priv];
  const filters = [['all', `Все · ${all.length}`], ...[...new Set(all.map(k => k.tier))].map(t => [t, t]), ['season', 'Сезонные'], ['set', 'Наборы'], ...(priv.length ? [['private', `Личные · ${priv.length}`]] : [])];
  let filter = 'all', q = '', chosen = pool.find(k => k.id === currentId) || null;
  const p = openSheet({title: 'Выберите образ', wide: true, body: `<div id="skd"></div><div class="search">${icon('search')}<input id="skq" placeholder="Название, набор, описание, титул" autocomplete="off"/></div>
    <div id="skt"></div><div id="skg"></div>`, actions: [{label: 'Выбрать', run: () => { if (chosen) onPick(chosen.id); }}]});
  const match = k => {
    if (filter === 'season' && !k.season) return false;
    if (filter === 'set' && !k.set) return false;
    if (filter === 'private' && !k.exclusive) return false;
    if (!['all', 'season', 'set', 'private'].includes(filter) && k.tier !== filter) return false;
    return !q || [k.name, k.blurb, k.set_name, k.season_name, ...Object.values(k.items || {})].join(' ').toLowerCase().includes(q);
  };
  const draw = () => {
    p.q('#skt').innerHTML = chipPick('skf', filters, filter, {scroll: true});
    const list = filter === 'private' ? [] : all.filter(match), tiers = [...new Set(list.map(k => k.tier))];
    const privList = ['all', 'private'].includes(filter) || q ? priv.filter(match) : [];
    p.q('#skg').innerHTML = (tiers.map(t => sh(esc(TIER_TITLES[t] || t), {count: list.filter(k => k.tier === t).length}) + `<div class="skin-grid">${list.filter(k => k.tier === t).map(k => skinCard(k, chosen && k.id === chosen.id)).join('')}</div>`).join('')
      || (privList.length ? '' : emptyBox('Ничего не нашлось')))
      + (privList.length ? sh('Личные образы', {count: privList.length}) + `<div class="skin-grid">${privList.map(k => skinCard(k, chosen && k.id === chosen.id, (k.holders || []).length > 0)).join('')}</div>` : '');
    p.q('#skd').innerHTML = skinDetail(chosen);
    const ok = p.q('[data-sa="0"]'); if (ok) ok.disabled = !chosen;
  };
  draw();
  p.q('#skq').oninput = e => { q = e.target.value.trim().toLowerCase(); draw(); };
  p.el.addEventListener('click', e => {
    const f = e.target.closest('[data-on="skf"]'); if (f) { filter = f.dataset.v; draw(); return; }
    const b = e.target.closest('[data-skin]');
    if (b && !b.disabled) { chosen = pool.find(k => k.id === b.dataset.skin) || chosen; draw(); p.q('.sheet-b').scrollTo({top: 0, behavior: 'smooth'}); }
  });
}
const promoWarnings = list => list.map(w => callout('warn', '⚠️', esc(w))).join('');
function promoPreviewHtml(pv) {
  return `<p class="sub" style="margin-top:0">Так бот ответит игроку:</p><div class="chatbg"><div class="bubble">🎟 Промокод <b>${esc(pv.code)}</b> активирован!
    <blockquote>${pv.player_text.map(esc).join('<br>')}</blockquote></div></div><p class="sub">Кто может: ${esc(pv.who_can)}.</p>${promoWarnings(pv.warnings)}`;
}

async function promoEdit(ctx) {
  OPTIONS = OPTIONS || await ctx.load('/promo-options');
  const code = ctx.params.code, bulk = ctx.route === 'bulk';
  const p = code ? await ctx.load(`/promo/${encodeURIComponent(code)}`, {cache: false}) : null;
  if (!ctx.alive()) return;
  const isNew = !p;
  ctx.title(bulk ? 'Пачка кодов' : isNew ? 'Новый промокод' : 'Изменить ' + p.code);
  const state = {rewards: p && p.rewards.length ? p.rewards.map(r => ({...r})) : [{type: 'mora', amount: ''}], chats: p ? p.chats.map(c => ({...c})) : [],
    users: ((p && p.allowed_users) || []).map(id => ({id: +id, label: 'id' + id}))};
  const v = ctx.view;
  v.innerHTML = `${bulk ? hint('Много разных кодов с одной наградой. Каждый сработает один раз: удобно для конкурсов и подарков.') + `<div class="grid2">
      ${field('Начало кода (необязательно)', '<input id="fprefix" maxlength="16" placeholder="например, EVENT" style="text-transform:uppercase" autocomplete="off"/>')}
      ${field('Сколько кодов (1–200)', '<input id="fcount" type="number" min="1" max="200" value="10"/>')}</div>`
    : isNew ? field('Код', `<div style="display:flex;gap:8px"><input id="fcode" maxlength="32" style="text-transform:uppercase" autocomplete="off"/><button type="button" class="btn" data-on="gen">🎲 Случайный</button></div>`, 'Латиница, цифры, - и _') : ''}
    ${sh('Награды')}<div id="frewards"></div><button type="button" class="btn sm ghost" data-on="add">${icon('plus')} Ещё награда</button>
    ${sh('Условия')}
    ${bulk ? '' : `<div class="grid2">${field('Лимит активаций', `<input id="fmax" type="number" min="0" value="${p ? p.max_activations : 0}"/>`, '0 — без лимита')}</div>
      <label class="row" style="border-top:0"><span class="row-t"><b>Включён</b><span>Выключенный код не активируется</span></span>${toggle('id="factive"', !p || p.is_active, 'Включён')}</label>
      <label class="row"><span class="row-t"><b>Показывать в Mini App</b><span>Игроки заберут в одно касание; коды для чатов там не показываются</span></span>${toggle('id="fshow"', p && p.show_in_app, 'Показывать в Mini App')}</label>`}
    <div class="grid2">${field('Начало', `<input id="ffrom" type="datetime-local" value="${localInput(p && p.valid_from)}"/>`, 'Необязательно')}${field('Конец', `<input id="funtil" type="datetime-local" value="${localInput(p && p.valid_until)}"/>`, 'Необязательно')}</div>
    <div class="field"><label>Где активировать</label><div id="fchats"></div></div>
    ${bulk ? '' : '<div class="field"><label>Только для игроков</label><div id="fusers"></div></div>'}
    ${field('Заметка для себя', `<textarea id="fnote" maxlength="300">${esc(p ? p.note : '')}</textarea>`)}`;
  ctx.mount();
  const $v = sel => v.querySelector(sel);
  const allSkins = () => [...OPTIONS.skins, ...(OPTIONS.private_skins || [])];
  const drawRewards = () => {
    $v('#frewards').innerHTML = state.rewards.map((r, i) => {
      const opt = OPTIONS.rewards.find(o => o.type === r.type) || OPTIONS.rewards[0];
      const k = allSkins().find(x => x.id === r.id);
      const value = opt.field === 'id'
        ? `<button type="button" class="skin-pick" data-on="pick" data-i="${i}">${k ? skinCard(k, false, false, 'div') : '<span class="sub">Образ не выбран</span>'}<span class="btn sm">Сменить</span></button>`
        : `<input data-input="rv" data-i="${i}" data-k="${opt.field}" type="number" min="0" step="${r.type === 'diamonds' ? '0.01' : '1'}" value="${esc(r[opt.field] ?? '')}" placeholder="Сколько" aria-label="Сколько"/>`;
      return `<div class="reward"><select data-change="rt" data-i="${i}" aria-label="Награда">${OPTIONS.rewards.map(o => `<option value="${o.type}" ${o.type === r.type ? 'selected' : ''}>${esc(o.title)}</option>`).join('')}</select>
        ${value}<button type="button" class="ib" data-on="del" data-i="${i}" aria-label="Убрать награду">${icon('close')}</button></div>`;
    }).join('') || '<p class="sub">Добавьте хотя бы одну награду.</p>';
  };
  drawRewards();
  pickerField($v('#fchats'), {hint: 'Во всех чатах и в личке с ботом', placeholder: 'Найти чат по названию или ID', search: searchChats, items: state.chats = state.chats.map(c => ({id: c.id, label: c.title || c.label, chat: true})), onChange: () => {}});
  if (!bulk) pickerField($v('#fusers'), {hint: 'Для всех игроков', placeholder: 'Найти игрока по @нику или ID', search: searchPlayers, items: state.users, onChange: () => {}});
  on(v, {
    gen: () => { const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; $v('#fcode').value = Array.from({length: 8}, () => abc[Math.floor(Math.random() * abc.length)]).join(''); },
    add: () => { state.rewards.push({type: 'mora', amount: ''}); drawRewards(); },
    del: el => { state.rewards.splice(+el.dataset.i, 1); drawRewards(); },
    rt: el => { const i = +el.dataset.i; state.rewards[i] = {type: el.value}; if (el.value === 'skin') state.rewards[i].id = (OPTIONS.skins[0] || {}).id; drawRewards(); },
    rv: el => { state.rewards[+el.dataset.i][el.dataset.k] = el.value; },
    pick: el => skinPicker(state.rewards[+el.dataset.i].id, id => {
      state.rewards[+el.dataset.i].id = id; drawRewards();
      // Личный образ у одного владельца: сами ставим лимит 1, если не выбран игрок.
      if (!bulk && (OPTIONS.private_skins || []).some(k => k.id === id) && !+$v('#fmax').value && !state.users.length) { $v('#fmax').value = 1; toast('Личный образ: лимит активаций поставлен в 1'); }
    }, {noPrivate: bulk}),
  });
  const toIso = x => (x ? new Date(x).toISOString() : null);
  const collect = () => {
    const common = {rewards: state.rewards, valid_from: toIso($v('#ffrom').value), valid_until: toIso($v('#funtil').value), allowed_chats: state.chats.map(c => c.id), note: $v('#fnote').value};
    return bulk ? {...common, prefix: $v('#fprefix').value.trim().toUpperCase(), count: +$v('#fcount').value || 0}
      : {...common, code: isNew ? $v('#fcode').value.trim().toUpperCase() : p.code, max_activations: +$v('#fmax').value || 0,
         is_active: $v('#factive').checked, show_in_app: $v('#fshow').checked, allowed_users: state.users.map(u => u.id)};
  };
  // Предпросмотр у сервера: он же знает, что считается «слишком много». Сохранять он не мешает.
  const preview = body => post('/promo/preview', bulk ? {...body, max_activations: 1} : body);
  const save = async body => {
    if (bulk) { const made = await post('/promo/bulk', body); toast(`Создано кодов: ${made.codes.length}`, {ok: true}); promoBulkDone(made, body.prefix); return; }
    const saved = isNew ? await post('/promo', body) : await api(`/promo/${encodeURIComponent(p.code)}`, {method: 'PUT', body: JSON.stringify(body)});
    toast(isNew ? 'Промокод создан' : 'Сохранено', {ok: true});
    CACHE.forEach((_, k) => { if (k.startsWith('/promo')) CACHE.delete(k); });
    go('promo/' + encodeURIComponent(saved.code), {replace: true});
  };
  ctx.bar(`<div><b>${bulk ? 'Пачка' : isNew ? 'Новый код' : esc(p.code)}</b>Проверьте, как увидит игрок</div><div class="btns"><button type="button" class="btn sm" data-on="pv">Как увидит</button>
    <button type="button" class="btn sm primary" data-on="save">${bulk ? 'Создать' : isNew ? 'Создать' : 'Сохранить'}</button></div>`, {
    pv: el => busy(el, async () => { const pv = await preview(collect()); sheet('Как увидит игрок', promoPreviewHtml(pv) + (bulk ? '<p class="sub">Каждый код сработает один раз.</p>' : ''), 'Понятно', null, {info: true}); }),
    save: el => busy(el, async () => {   // повторный тап во время запроса не создаст код второй раз
      const body = collect();
      const warnings = (await preview(body)).warnings;
      if (!warnings.length) return save(body);
      sheet('Проверьте перед сохранением', hint('Код сработает, но вот что стоит перепроверить:') + promoWarnings(warnings), bulk ? 'Всё верно, создать' : 'Всё верно, сохранить', () => save(body), {cancelText: 'Вернуться'});
    }),
  });
  // Готовая пачка: все коды, чтобы сразу скопировать или скачать и раздать.
  function promoBulkDone(made, prefix) {
    const text = made.codes.join('\n');
    ctx.bar('');
    v.innerHTML = `${callout('ok', '✓', `<b>Пачка готова · ${made.codes.length}</b><small>${made.rewards_text.map(esc).join(' · ')}</small>`)}
      <p class="sub">Каждый код сработает один раз. Игрок пишет боту: «бот промокод КОД».</p>
      ${field('Коды (по одному в строке)', `<textarea readonly rows="${Math.min(12, made.codes.length + 1)}" class="mono">${esc(text)}</textarea>`)}
      <div class="btns grow"><button type="button" class="btn primary" data-on="cp">Копировать все</button>${INIT ? '' : '<button type="button" class="btn" data-on="dl">Скачать .txt</button>'}
        <a class="btn" href="#/promo?q=${encodeURIComponent(prefix || '')}">В списке</a></div>`;
    on(v, {cp: () => copyText(text, 'Коды скопированы'), dl: () => {
      const url = URL.createObjectURL(new Blob([text + '\n'], {type: 'text/plain;charset=utf-8'}));
      const a = Object.assign(document.createElement('a'), {href: url, download: `promo-${prefix || 'codes'}-${made.codes.length}.txt`});
      document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 4000);
    }});
  }
}
route('promo/new', {section: 'promo', up: () => 'promo', title: () => 'Новый промокод', render: ctx => promoEdit(ctx)});
route('promo/bulk', {section: 'promo', up: () => 'promo', title: () => 'Пачка кодов', render: ctx => { ctx.route = 'bulk'; return promoEdit(ctx); }});
route('promo/:code/edit', {section: 'promo', up: p => 'promo/' + encodeURIComponent(p.code), title: () => 'Изменить', render: promoEdit});

// ── Функции: выключатели бота и сайта ────────────────────────────────────────

const OFF_REASONS = ['Чиним, вернём скоро', 'Плановые работы', 'Временно закрыто', 'Тестируем'];
async function switchesView(ctx) {
  const chatId = +ctx.params.chat || 0;
  const data = await ctx.load(`/switches?chat_id=${chatId}`, {cache: false});
  if (!ctx.alive()) return;
  const chat = chatId ? {id: chatId, title: data.chat_title || ctx.query.get('t') || (CACHE.get(`/chat/${chatId}`) || {data: {}}).data.title || 'чат ' + chatId} : null;
  const off = data.state, v = ctx.view;
  const opened = new Set(PREFS.get('sw.open', []));
  const state = item => {
    const globalOff = off.global[item.key], localOff = chat ? off.chat[item.key] : globalOff;
    return {enabled: !localOff && !(chat && globalOff), locked: !!(chat && globalOff), why: (localOff || globalOff || {}).reason};
  };
  const swRow = item => {
    if (!item.key) return '';
    const {enabled, locked, why} = state(item);
    const status = item.key === 'all' ? (enabled ? 'Бот работает' : 'Бот выключен') : item.key === 'site' ? (enabled ? 'Сайт открыт' : 'Сайт закрыт') : (enabled ? 'Включено' : 'Выключено');
    const big = ['all', 'site', 'notice:achievements'].includes(item.key);
    const sub = [locked ? 'выключено везде — включается только во «Везде»' : '', !enabled && why ? '«' + esc(why) + '»' : '',
      item.hint && item.hint !== 'Весь раздел' && (!big || !enabled) ? (big ? 'При выключении: ' : '') + esc(item.hint) : ''].filter(Boolean).join(' · ');
    return `<div class="row ${enabled ? '' : 'off'}">${lead(enabled ? '●' : '○', enabled ? 'ok' : locked ? 'warn' : 'bad')}<span class="row-t"><b>${esc(item.title)}</b><span>${status}${sub ? ' · ' + sub : ''}</span></span>
      ${toggle(`data-change="sw" data-k="${esc(item.key)}" data-t="${esc(item.title)}"`, enabled, `${item.title}: ${status.toLowerCase()}, ${chat ? `в чате «${chat.title}»` : 'везде'}`, locked)}</div>`;
  };
  const group = item => item.items && item.items.length
    ? `<details class="fold" data-grp="${esc(item.title)}" ${opened.has(item.title) ? 'open' : ''}><summary>${esc(item.title)} <span class="cnt">${item.items.filter(x => !state(x).enabled).length ? item.items.filter(x => !state(x).enabled).length + ' выкл.' : ''}</span></summary>
        ${item.key ? swRow(item) : ''}<div class="list">${item.items.map(swRow).join('')}</div></details>`
    : `<div class="list">${swRow(item)}</div>`;
  const offCount = Object.keys(chat ? off.chat : off.global).length;
  v.innerHTML = seg('scope', [['0', 'Везде'], [chat ? String(chat.id) : 'pick', chat ? '💬 ' + chat.title : '💬 Выбрать чат…']], chat ? String(chat.id) : '0')
    + (offCount ? callout('warn', '⏻', `<b>Выключено ${chat ? 'в этом чате' : 'везде'}: ${offCount}</b>`) : callout('ok', '✓', `<b>Всё включено ${chat ? 'в этом чате' : 'везде'}</b>`))
    + data.catalog.filter(g => !(chat && g.scope === 'site')).map(g => sh(esc(g.title)) + g.items.map(group).join('')).join('')
    + (chat ? '<p class="sub">Сайт выключается только целиком для всех — переключитесь на «Везде».</p>' : '');
  v.addEventListener('toggle', e => {
    const d = e.target; if (!d.dataset || !d.dataset.grp) return;
    d.open ? opened.add(d.dataset.grp) : opened.delete(d.dataset.grp); PREFS.set('sw.open', [...opened]);   // раскрытые группы помним между перерисовками
  }, true);
  const send = async (input, enabled, reason) => {
    try {
      await post('/switches', {feature: input.dataset.k, chat_id: chat ? chat.id : 0, enabled, reason});
      toast(enabled ? 'Включено' : 'Выключено', {ok: true});
      ctx.refresh();
    } catch (err) { toast(err.message, true); input.checked = !enabled; }
  };
  on(v, {
    scope: el => {
      if (el.dataset.v === '0') { if (chat) go('switches', {replace: true}); return; }
      if (el.dataset.v === 'pick' || chat) chatPick();
    },
    // Выключение спрашивает причину (её увидят игроки) прямо здесь; весь бот и сайт — с красным подтверждением. Включение — сразу.
    sw: input => {
      const enabled = input.checked;
      if (enabled) return send(input, true, '');
      input.checked = true;   // пока не подтвердили, на экране прежнее состояние
      const big = input.dataset.k === 'all' || input.dataset.k === 'site';
      const s = openSheet({title: big ? (input.dataset.k === 'all' ? `Выключить весь бот ${chat ? 'в этом чате' : 'во всех чатах'}?` : 'Закрыть весь сайт для игроков?') : `Выключить «${input.dataset.t}»?`,
        sub: chat ? 'Чат: ' + chat.title : 'Везде',
        body: (big ? callout('bad', '⚠️', '<b>Это заметят все игроки сразу</b>') : '') + field('Причина для игроков (необязательно)', `<input id="sreason" maxlength="200" autocomplete="off"/>${chipPick('sr', OFF_REASONS.map(x => [x, x]), '')}`),
        actions: [{label: 'Выключить', kind: big ? 'btn danger fill' : 'danger', run: async p => { input.checked = false; await send(input, false, p.q('#sreason').value); }}, {label: 'Отмена', kind: '', run: null}]});
      s.el.addEventListener('click', e => { const c = e.target.closest('[data-on="sr"]'); if (c) { s.q('#sreason').value = c.dataset.v; } });
    },
  });
  function chatPick() {
    const p = openSheet({title: 'Функции в чате', body: `<div class="search">${icon('search')}<input id="scq" placeholder="Название чата или ID" autocomplete="off"/></div><div id="scf" class="list"></div>`});
    let t;
    p.q('#scq').oninput = e => {
      clearTimeout(t);
      const q = e.target.value.trim();
      if (!q) { p.q('#scf').innerHTML = ''; return; }
      t = setTimeout(async () => {
        try { const {items} = await api(`/chats?q=${encodeURIComponent(q)}`); p.q('#scf').innerHTML = items.map(c => row({lead: chatAva(c, 'sm'), title: esc(c.title), sub: String(c.id), on: 'c', data: {v: c.id, t: c.title}})).join('') || emptyBox('Не найдено'); }
        catch (err) { p.q('#scf').innerHTML = `<p class="err">${esc(err.message)}</p>`; }
      }, 280);
    };
    on(p.el, {c: el => { closeSheets(); go(`switches/${el.dataset.v}?t=${encodeURIComponent(el.dataset.t)}`, {replace: !!chat}); }});
  }
}
route('switches', {section: 'switches', root: true, title: () => 'Функции', render: switchesView});
route('switches/:chat', {section: 'switches', up: () => 'switches', title: () => 'Функции чата', render: switchesView});

// ── Настройки бота ───────────────────────────────────────────────────────────

async function settingsView(ctx) {
  const data = await ctx.load('/settings', {cache: false});
  if (!ctx.alive()) return;
  const v = ctx.view, r = data.reports, o = data.report_options;
  const select = (id, value, list, offTitle) => `<select id="${id}">${offTitle ? `<option value="0" ${!value ? 'selected' : ''}>${offTitle}</option>` : ''}
    ${list.map(x => `<option value="${x.value}" ${x.value === value ? 'selected' : ''}>${esc(x.title)}</option>`).join('')}</select>`;
  v.innerHTML = `${sh('💸 Переводы между игроками')}<p class="sub" style="margin-top:0">Какие валюты можно отправить командой «бот перевод».</p>
    <div class="list">${data.transfer.map(c => `<div class="row ${c.enabled ? '' : 'off'}"><span class="row-t"><b>${esc(c.title)}</b><span>${c.locked ? 'Переводить нельзя никогда' : c.enabled ? 'Можно переводить' : 'Переводы закрыты'}</span></span>
      ${toggle(`data-change="cur" data-cur="${c.code}"`, c.enabled, c.title, c.locked)}</div>`).join('')}</div>
    <div id="repset">${sh('⚑ Жалобы')}<p class="sub" style="margin-top:0">Жалоба анонимна: игроки и нарушитель не видят, кто пожаловался. Бот убирает команду из чата и отвечает автору в личку.</p>
    <label class="row" style="border-top:0"><span class="row-t"><b>Отчёт в админ-чат</b><span>Если к чату привязан админ-чат, жалоба приходит туда без имени автора</span></span>${toggle('id="rs-admin"', r.to_admin_chat, 'Отчёт в админ-чат')}</label>
    ${field('Отчёт в личку модераторам чата — с ранга', select('rs-chat', r.dm_chat_rank, o.chat_ranks, 'Не писать в личку'))}
    ${field('Отчёт в личку персоналу бота — с роли', select('rs-staff', r.dm_staff_rank, o.staff_ranks, 'Не писать в личку'))}
    ${field('Автора жалобы в админке видят — с роли', select('rs-see', r.reporter_min_rank, o.staff_ranks, ''), 'Остальные видят «автор скрыт». В личку пишем только тем, кто открывал диалог с ботом.')}
    <button type="button" class="btn primary block" data-on="rsave">Сохранить настройки жалоб</button></div>
    <div id="secset">${sh('🔐 Безопасность')}<p class="sub" style="margin-top:0">Потеряли телефон или вошли с чужого устройства — завершите сессии: админку придётся открыть заново через Telegram.</p>
    <div class="list">${row({lead: lead(icon('out', 'ico')), title: 'Выйти на всех моих устройствах', sub: 'Включая этот экран. Роль не меняется.', on: 'revself', data: {id: 'revself'}})}
      ${ME.creator ? row({lead: lead(icon('out', 'ico'), 'bad'), title: 'Завершить сессии всех сотрудников', sub: 'Все, включая вас, откроют админку заново', on: 'revall', cls: 'danger', data: {id: 'revall'}}) : ''}</div></div>
    ${sh('🎨 Оформление')}<div class="list">${row({lead: lead(icon('theme', 'ico')), title: 'Тема', sub: THEMES.find(t => t[0] === themePref())[1], on: 'theme'})}</div>`;
  const revoke = async (title, text, all) => {
    if (!await ask(title, hint(text), 'Завершить')) return;
    try { const res = await post('/sessions/revoke', {all}); v.innerHTML = ''; ctx.view.replaceChildren(stateEl('✅', 'Сессии завершены', res.message)); }
    catch (e) { toast(e.message, true); }
  };
  on(v, {
    cur: input => {
      const currencies = $$('[data-cur]', v).filter(x => x.checked && !x.disabled).map(x => x.dataset.cur);
      post('/settings/transfer', {currencies}).then(() => { toast('Сохранено', {ok: true}); ctx.refresh(); }).catch(e => { toast(e.message, true); input.checked = !input.checked; });
    },
    rsave: el => busy(el, async () => {
      await post('/settings/reports', {to_admin_chat: v.querySelector('#rs-admin').checked, dm_chat_rank: +v.querySelector('#rs-chat').value,
        dm_staff_rank: +v.querySelector('#rs-staff').value, reporter_min_rank: +v.querySelector('#rs-see').value});
      toast('Сохранено', {ok: true});
    }),
    revself: () => revoke('Выйти на всех устройствах', 'Админка закроется везде, где она открыта, включая этот экран. Роль не меняется.', false),
    revall: () => revoke('Сессии всех сотрудников', 'Все сотрудники, включая вас, выйдут из админки и откроют её заново. Роли не меняются.', true),
    theme: () => themeSheet(),
  });
}
route('settings', {section: 'settings', root: true, title: () => 'Настройки', render: settingsView});

// ── Состояние ────────────────────────────────────────────────────────────────

const uptime = sec => { const d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600), m = Math.floor(sec % 3600 / 60); return d ? `${d} д ${h} ч` : h ? `${h} ч ${m} мин` : `${m} мин`; };
async function healthView(ctx) {
  const h = await ctx.load('/health', {cache: false});
  if (!ctx.alive()) return;
  const v = ctx.view, tg = h.telegram, dg = h.digest, bad = tg && !tg.ok;
  const warn = h.errors.count_24h || h.chats.no_rights;
  v.innerHTML = (bad ? callout('bad', '⛔', `<b>Telegram не отвечает</b><small>Бот не получает и не отправляет сообщения: ${esc(tg.error || 'причина не указана')}</small>`)
      : warn ? callout('warn', '•', `<b>Работает, есть замечания</b><small>${[h.errors.count_24h ? `ошибок за сутки: ${num(h.errors.count_24h)}` : '', h.chats.no_rights ? `чатов без прав: ${num(h.chats.no_rights)}` : ''].filter(Boolean).join(' · ')}</small>`)
      : callout('ok', '✓', '<b>Всё работает</b><small>Telegram, база и очереди в порядке</small>'))
    + `<div class="stats four">${stat('🤖 Telegram', tg ? (tg.ok ? tg.ms + ' мс' : 'нет') : '—', {tone: tg ? (tg.ok ? 'ok' : 'bad') : ''})}${stat('🗄 База', h.database.ms + ' мс', {tone: h.database.ms > 500 ? 'warn' : ''})}
      ${stat('⏱ Работает', uptime(h.process.uptime_seconds))}${stat('⚠️ Ошибок', num(h.errors.count_24h), {tone: h.errors.count_24h ? 'warn' : '', small: 'за сутки'})}</div>
    <p class="sub">${tg && tg.ok ? '@' + esc(tg.username) + ' · ' : ''}с ${when(h.process.started_at)} · Python ${esc(h.process.python)}${h.process.commit ? ` · версия ${esc(h.process.commit)}` : ''}
      ${h.database.pool && h.database.pool.size != null ? ` · соединений ${h.database.pool.size - h.database.pool.idle}/${h.database.pool.size} (макс. ${h.database.pool.max})` : ''}</p>
    ${sh('⚠️ Ошибки', {count: num(h.errors.count_24h)})}${h.errors.recent.length ? `<div class="list">${h.errors.recent.map(e => row({lead: lead('!', 'bad'), title: `<span class="mono" style="font-size:13px;font-weight:500">${esc(e.text)}</span>`, sub: ago(e.at)})).join('')}</div>
      ${h.errors.count_24h > h.errors.recent.length ? `<p class="sub">Показаны последние ${h.errors.recent.length}.</p>` : ''}` : emptyBox('Ошибок нет', 'Считаются с последнего перезапуска.')}
    ${sh('💬 Чаты и игроки')}<div class="list">
      ${row({lead: lead('💬'), title: 'Чатов с ботом', end: `<b>${num(h.chats.active)}</b>`})}
      ${row({lead: lead('🚪', h.chats.left ? 'bad' : ''), title: 'Бота удалили', sub: h.chats.left ? 'В рассылки они не попадают' : '', end: `<b>${num(h.chats.left)}</b>`, on: h.chats.left ? 'attn' : '', data: {k: 'left', t: 'Бота удалили из чатов'}})}
      ${row({lead: lead('🛡', h.chats.no_rights ? 'warn' : ''), title: 'Без прав модерации', sub: h.chats.no_rights ? 'Мут, бан и чистка там не сработают' : '', end: `<b>${num(h.chats.no_rights)}</b>`, on: h.chats.no_rights ? 'attn' : '', data: {k: 'no_rights', t: 'Без прав модерации'}})}
      ${row({lead: lead('💤'), title: 'Тихих чатов', sub: '30 дней без сообщений', end: `<b>${num(h.chats.quiet)}</b>`, on: h.chats.quiet ? 'attn' : '', data: {k: 'quiet', t: 'Тихие чаты'}})}
      ${row({lead: lead('👤'), title: 'Игроков', end: `<b>${num(h.players.total)}</b>`})}
      ${row({lead: lead('🙈', h.players.blocked_bot ? 'warn' : ''), title: 'Заблокировали бота', sub: h.players.blocked_bot ? 'В личку им рассылка не уходит' : '', end: `<b>${num(h.players.blocked_bot)}</b>`})}</div>
    ${sh('📬 Очереди')}<div class="list">
      ${row({lead: lead('📣', h.queues.broadcasts_running ? 'info' : ''), title: 'Рассылок идёт', end: `<b>${num(h.queues.broadcasts_running)}</b>`, href: has('broadcast') && h.queues.broadcasts_running ? '#/broadcast' : ''})}
      ${row({lead: lead('🗓'), title: 'Рассылок запланировано', end: `<b>${num(h.queues.broadcasts_scheduled)}</b>`, href: has('broadcast') && h.queues.broadcasts_scheduled ? '#/broadcast' : ''})}
      ${row({lead: lead('⚑', h.queues.reports_open ? 'warn' : ''), title: 'Открытых жалоб', end: `<b>${num(h.queues.reports_open)}</b>`, href: has('reports') && h.queues.reports_open ? '#/reports' : ''})}</div>
    ${sh('🌅 Итоги дня владельцу')}<p class="sub" style="margin-top:0">Раз в сутки бот пишет владельцу в личку: новые игроки, сообщения, команды, жалобы, ошибки, чаты без прав.</p>
    <label class="row" style="border-top:0"><span class="row-t"><b>Присылать итоги дня</b>${dg.can_edit ? '' : '<span>Настраивает только владелец</span>'}</span>${toggle('id="dgon" data-change="dg"', dg.enabled, 'Присылать итоги дня', !dg.can_edit)}</label>
    ${field('Во сколько (по времени бота)', `<select id="dghour" data-change="dg" ${dg.can_edit ? '' : 'disabled'}>${Array.from({length: 24}, (_, i) => `<option value="${i}" ${i === dg.hour ? 'selected' : ''}>${String(i).padStart(2, '0')}:00</option>`).join('')}</select>`)}
    <button type="button" class="btn block" data-on="dgtest">✉️ Прислать мне за вчера</button>
    ${help('Почему «0» после выката ничего не доказывает', '<p>Ошибки и время работы считаются с последнего перезапуска: каждый выкат новой версии обнуляет их.</p>')}`;
  on(v, {
    attn: el => attentionSheet(el.dataset.k, el.dataset.t).catch(e => toast(e.message, true)),
    dg: () => post('/health/digest', {enabled: v.querySelector('#dgon').checked, hour: +v.querySelector('#dghour').value}).then(() => toast('Сохранено', {ok: true})).catch(e => toast(e.message, true)),
    dgtest: el => busy(el, async () => toast((await post('/health/digest/test')).message, {ok: true})),
  });
}
route('health', {section: 'health', root: true, title: () => 'Состояние', stats: true, render: healthView});

// ── Права (только создатель): кто из ролей что может, и вход владельцев чатов ───────────────────

const roleWord = name => name.replace(/^\S+\s/, '').toLowerCase();   // «💬 Хелпер» -> «хелпер»: этим словом подтверждается изменение
async function accessView(ctx) {
  const d = await ctx.load('/access/matrix', {cache: false});
  if (!ctx.alive()) return;
  const v = ctx.view, word = r => roleWord(d.roles.find(x => x.rank === r).name);
  const item = i => `<div class="row" style="flex-wrap:wrap"><span class="row-t"><b>${esc(i.title)}</b><span>${i.changed ? '✎ изменено · ' : ''}по умолчанию: ${esc((d.roles.find(x => x.rank === i.default) || {}).name || i.default)}</span></span>
    <div style="display:flex;gap:8px;flex-basis:100%"><select data-change="akey" data-k="${esc(i.key)}" data-t="${esc(i.title)}" aria-label="${esc(i.title)}: с какой роли">${d.roles.map(r => `<option value="${r.rank}" ${r.rank === i.current ? 'selected' : ''}>${esc(r.name)}</option>`).join('')}</select>
    ${i.changed ? `<button type="button" class="btn sm" data-on="areset" data-k="${esc(i.key)}">Сбросить</button>` : ''}</div></div>`;
  let owners = null;
  if (ME.creator) { try { owners = await api('/access/owners'); } catch (_) {} }
  if (!ctx.alive()) return;
  v.innerHTML = callout('info', 'ⓘ', 'Роль выше или равная выбранной получает право. Деньги, роли, рассылки, промокоды, переключатели и настройки закреплены за разработчиком и создателем.')
    + sh('🗂 Разделы') + `<div class="list">${d.items.filter(i => i.group === 'section').map(item).join('')}</div>`
    + sh('🛡 Модерация') + `<div class="list">${d.items.filter(i => i.group === 'moderation').map(item).join('')}</div>`
    + (owners ? `<div id="ownacc">${sh('🧑‍💼 Владельцы чатов')}
      <label class="row" style="border-top:0"><span class="row-t"><b>Вход владельцев чатов</b><span>${owners.enabled ? 'Открыт' : 'Закрыт'} · до ${owners.max_chats} чатов на человека, владение проверяется при каждом входе</span></span>${toggle('id="own-on" data-change="own"', owners.enabled, 'Вход владельцев чатов')}</label>
      ${sh('Доступ отозван', {count: owners.blocked.length})}${owners.blocked.length ? `<div class="list">${owners.blocked.map(b => `<div class="row">${ava(b, 'sm')}<span class="row-t"><b>${who(b.id, b.username)}</b><span>${esc(b.reason || 'без причины')} · ${ago(b.at)}</span></span>
        <button type="button" class="btn sm" data-on="ounblock" data-v="${b.id}">Вернуть</button></div>`).join('')}</div>` : '<p class="sub">Никто не отозван.</p>'}
      <button type="button" class="btn danger block mt" data-on="oblock">Отозвать доступ владельца…</button></div>` : '');
  const ask_ = (title, key, rank, expect) => sheet(title, hint('Изменение вступает в силу сразу для всех сотрудников. Для подтверждения введите «' + esc(expect) + '».') + field('Подтверждение', '<input id="a-confirm" autocomplete="off"/>'),
    'Изменить', async p => { await post('/access/matrix', {key, min_rank: rank, confirm: p.q('#a-confirm').value}); toast('Сохранено', {ok: true}); ctx.refresh(); });
  on(v, {
    akey: sel => { const rank = +sel.value, was = d.items.find(i => i.key === sel.dataset.k).current; sel.value = was; ask_(`Изменить право «${sel.dataset.t}»`, sel.dataset.k, rank, word(rank)); },
    areset: el => ask_('Вернуть значение по умолчанию', el.dataset.k, null, 'сброс'),
    own: async input => {
      const onn = input.checked;
      input.checked = !onn;
      if (onn && !await ask('Пустить владельцев чатов в админку?', hint('Любой, кто создал группу с ботом, сможет входить и модерировать свой чат.'), 'Пустить')) return;
      try { await post('/access/owners', {enabled: onn}); toast(onn ? 'Вход владельцев открыт' : 'Вход владельцев закрыт', {ok: true}); ctx.refresh(); } catch (e) { toast(e.message, true); }
    },
    ounblock: el => busy(el, async () => { await post('/access/owners/block', {user_id: +el.dataset.v, blocked: false}); toast('Доступ возвращён', {ok: true}); ctx.refresh(); }),
    oblock: () => {
      const s = sheet('Отозвать доступ владельца', field('Кто', '<div id="obpick"></div>') + reasonField(), 'Отозвать', async p => {
        const target = picked[0];
        if (!target) throw new Error('Выберите человека.');
        await post('/access/owners/block', {user_id: target.id, blocked: true, reason: p.q('#freason').value.trim()});
        toast('Доступ отозван', {ok: true}); ctx.refresh();
      }, {kind: 'btn danger fill'});
      const picked = [];
      pickerField(s.q('#obpick'), {hint: 'Найдите по @нику или ID', placeholder: '@ник или ID', search: searchPlayers, items: picked, onChange: () => { if (picked.length > 1) picked.splice(0, 1); }});
      wireFormChips(s.el);
    },
  });
}
route('access', {section: 'access', root: true, title: () => 'Права', render: accessView});

// ── Владелец чата: только свои чаты и только то, что можно командами «бот …» ──────────────
// Участник выбирается поиском по @нику или имени — числовой ID знать не нужно.

const OWNER = {chats: [], chat: 0};
async function ownerBoot() {
  try {
    const o = await api('/owner/me');
    OWNER.chats = o.chats; OWNER.chat = o.chats[0].id;
    return {rank_name: 'Владелец чата', sections: [{key: 'mychats', title: 'Мои чаты'}], creator: false, owner: true};
  } catch (e) { e.owner = true; throw e; }
}
const OWNER_ACTS = [['warn', '⚠️', 'Выдать предупреждение', 'Много предупреждений — наказание по лимиту чата', ''], ['mute', '🔇', 'Замутить в чате', 'Не сможет писать до конца срока', 'warn'],
  ['kick', '👢', 'Выгнать из чата', 'Вернуться по ссылке сможет', 'bad'], ['ban', '⛔', 'Забанить в чате', 'Сам вернуться не сможет', 'bad']];
async function ownerView(ctx) {
  if (!ME.owner) { go(homePath(), {replace: true}); return; }
  const cid = +ctx.params.id || OWNER.chat;
  if (!OWNER.chats.some(x => x.id === cid)) { go('mychats', {replace: true}); return; }
  OWNER.chat = cid;
  const c = await ctx.load(`/owner/chat/${cid}`, {cache: false});
  if (!ctx.alive()) return;
  ctx.title(c.title, 'Ваш чат');
  const v = ctx.view, s = c.sanctions;
  const lift = (kind, id, label) => `<button type="button" class="btn sm" data-on="lift" data-k="${kind}" data-v="${id}">${label}</button>`;
  const personRow = (x, sub, btn) => `<div class="row">${ava(x)}<span class="row-t"><b>${who(x.id, x.username)}</b><span>${sub}</span></span>${btn}</div>`;
  const n = s.bans.length + s.mutes.length + s.warns.length;
  v.innerHTML = (OWNER.chats.length > 1 ? chipPick('ochat', OWNER.chats.map(x => [x.id, x.title]), cid, {scroll: true}) : '')
    + `<div class="hero">${chatAva(c, 'lg')}<div><h2>${esc(c.title)}</h2><div class="pills">${c.closed ? pill('🔒 закрыт', 'warn') : pill('открыт', 'ok')}${c.bot.can_moderate ? pill('бот с правами', 'ok') : pill('у бота нет прав', 'bad')}</div></div></div>
    ${c.bot.can_moderate ? '' : callout('bad', '⚠️', '<b>Выдайте боту права администратора</b><small>Удаление сообщений и ограничение участников — иначе мут, бан и кик не сработают.</small>')}
    <div class="stats three">${stat('Участников', num(c.members))}${stat('Нарушителей', num(n), {tone: n ? 'warn' : ''})}${stat('Лимит предупр.', c.max_warnings)}</div>
    <div class="btns mt"><button type="button" class="btn primary" style="flex:2 1 auto" data-on="punish">Наказать участника</button><a class="btn" style="flex:1 1 auto" href="${BASE}/?startapp=purge_${c.id}">Чистка ›</a></div>
    ${sh('⛔ Баны', {count: s.bans.length})}${s.bans.length ? `<div class="list">${s.bans.map(b => personRow(b, untilText(b.until) + (b.reason ? ' · ' + esc(b.reason) : ''), lift('unban', b.id, 'Снять бан'))).join('')}</div>` : '<p class="sub">Нет.</p>'}
    ${sh('🔇 Муты', {count: s.mutes.length})}${s.mutes.length ? `<div class="list">${s.mutes.map(m => personRow(m, untilText(m.until), lift('unmute', m.id, 'Снять мут'))).join('')}</div>` : '<p class="sub">Нет.</p>'}
    ${sh('⚠️ Предупреждения', {count: s.warns.length})}${s.warns.length ? `<div class="list">${s.warns.map(w => personRow(w, `${w.count} ${plural(w.count, 'предупреждение', 'предупреждения', 'предупреждений')}`, lift('unwarn_all', w.id, 'Снять все'))).join('')}</div>` : '<p class="sub">Нет.</p>'}
    ${sh('⚙️ Чат')}<div class="list">
      <label class="row"><span class="row-t"><b>Чат открыт</b><span>${c.closed ? 'Пишут только ранги с правом' : 'Писать могут все участники'}</span></span>${toggle('data-change="otoggle"', !c.closed, 'Чат открыт')}</label>
      <div class="row"><span class="row-t"><b>Лимит предупреждений</b><span>На нём бот наказывает по правилам чата</span></span>
        <div class="stepper"><button type="button" data-on="lim" data-v="-1" aria-label="Меньше">−</button><b id="olim">${c.max_warnings}</b><button type="button" data-on="lim" data-v="1" aria-label="Больше">+</button></div></div></div>
    ${help('Что здесь можно', '<p>Только ваш чат и только то, что можно командами «бот …» в самом чате. Персонал бота и сам бот защищены.</p>')}`;
  const post_ = (path, body) => post(path, body);
  const done = msg => { toast(msg, {ok: true}); ctx.refresh(); };
  let limTimer;
  on(v, {
    ochat: el => go('mychats/' + el.dataset.v, {replace: true}),
    lift: el => busy(el, async () => done((await post_(`/owner/chat/${c.id}/member/${el.dataset.v}/action`, {action: el.dataset.k})).message)),
    otoggle: async input => {
      const open = input.checked; input.checked = !open;
      if (!await ask(open ? 'Открыть чат?' : 'Закрыть чат?', hint(open ? 'Участники снова смогут писать.' : 'Писать смогут только ранги с правом.'), open ? 'Открыть' : 'Закрыть', {danger: !open})) return;
      try { done((await post_(`/owner/chat/${c.id}/action`, {action: open ? 'open' : 'close'})).message); } catch (e) { toast(e.message, true); }
    },
    lim: el => {
      const b = v.querySelector('#olim'), val = Math.max(1, Math.min(20, +b.textContent + +el.dataset.v));
      b.textContent = val; clearTimeout(limTimer);
      limTimer = setTimeout(() => post_(`/owner/chat/${c.id}/action`, {action: 'warn_limit', value: val}).then(r => toast(r.message, {ok: true})).catch(e => toast(e.message, true)), 700);   // несколько нажатий — один запрос
    },
    punish: () => ownerPunish(c, () => ctx.refresh()),
  });
}
// Наказать участника своего чата: найти по @нику/имени → выбрать действие → срок и причина → (кик и бан) подтверждение.
function ownerPunish(c, after) {
  const p = openSheet({title: 'Кого наказать', sub: c.title, body: `<div class="search">${icon('search')}<input id="omq" placeholder="@ник, имя или ID участника" autocomplete="off"/></div><div id="omf" class="list"></div>
    <p class="sub">Ищем только среди участников этого чата.</p>`});
  let t, seq = 0;
  p.q('#omq').oninput = e => {
    clearTimeout(t);
    const q = e.target.value.trim();
    if (q.replace(/^@/, '').length < 2 && !/^\d+$/.test(q)) { p.q('#omf').innerHTML = ''; return; }
    t = setTimeout(async () => {   // проверка владения на сервере ходит в Telegram: не на каждую букву
      const mine = ++seq;
      try {
        const {items} = await api(`/owner/chat/${c.id}/members?q=${encodeURIComponent(q)}`);
        if (mine !== seq) return;
        p.q('#omf').innerHTML = items.map(x => row({lead: ava(x), title: esc(nameOf(x)), sub: `${x.name && x.username ? '@' + esc(x.username) + ' · ' : ''}${num(x.messages)} сообщ.${x.last ? ' · ' + ago(x.last) : ''}`,
          on: 'm', data: {v: x.id, n: nameOf(x)}})).join('') || emptyBox('Никого не нашли', 'Проверьте написание. Персонал бота здесь не показывается.');
      } catch (err) { p.q('#omf').innerHTML = `<p class="err">${esc(err.message)}</p>`; }
    }, 400);
  };
  on(p.el, {m: el => ownerActionPick(c, {id: +el.dataset.v, name: el.dataset.n}, after)});
}
function ownerActionPick(c, target, after) {
  const p = openSheet({title: 'Что сделать', sub: target.name, body: `<div class="list">${OWNER_ACTS.map(([k, g, t, h, tone]) => row({lead: lead(g, tone), title: t, sub: h, on: 'a', data: {k}, cls: tone === 'bad' ? 'danger' : ''})).join('')}</div>`});
  on(p.el, {a: el => {
    const key = el.dataset.k, [, , title] = OWNER_ACTS.find(a => a[0] === key);
    const send = async payload => { const res = await post(`/owner/chat/${c.id}/member/${target.id}/action`, payload); closeSheets(); toast(res.message, {ok: true}); after(); return 'keep'; };
    const f = openSheet({title, sub: target.name, body: (key === 'kick' ? '' : durationField(key === 'warn' ? 10080 : key === 'ban' ? 0 : 60)) + reasonField(),
      actions: [{label: key === 'kick' || key === 'ban' ? 'Далее' : 'Выполнить', kind: key === 'kick' || key === 'ban' ? 'danger' : 'primary', run: async s => {
        const payload = {action: key, reason: s.q('#freason').value.trim(), minutes: +((s.q('#fmin') || {}).value || 0)};
        if (key !== 'kick' && key !== 'ban') return send(payload);
        openSheet({title: CONFIRM_TITLE[key], sub: 'Проверьте перед выполнением', body: summary([['Кто', `<b>${esc(target.name)}</b> · ID ${target.id}`], ['Чат', esc(c.title)],
          ['Что', key === 'ban' ? `Бан ${payload.minutes ? 'на ' + (DURATIONS.find(d => d[0] === payload.minutes) || [0, payload.minutes + ' мин'])[1] : 'навсегда'}` : 'Удалят из чата, вернуться по ссылке сможет'],
          ...(payload.reason ? [['Причина', esc(payload.reason)]] : [])]), actions: [{label: 'Подтвердить', kind: 'btn danger fill', run: () => send(payload)}]});
        return 'keep';
      }}, {label: 'Отмена', kind: '', run: null}]});
    wireFormChips(f.el);
  }});
}
route('mychats', {section: 'mychats', root: true, title: () => 'Мои чаты', render: ownerView});
route('mychats/:id', {section: 'mychats', root: true, title: () => 'Мои чаты', render: ownerView});
