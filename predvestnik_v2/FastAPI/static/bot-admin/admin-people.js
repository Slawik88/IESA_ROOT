// ── Игроки и чаты: поиск, карточка человека, карточка чата, действия ─────────
// Адреса: #/people?q=&f=  ·  #/player/123?tab=chats  ·  #/chat/-100123?tab=sanctions

const PEOPLE_FILTERS = [['', 'Все'], ['vip', '👑 VIP'], ['banned', '⛔ С баном'], ['warned', '⚠️ С предупреждениями'],
  ['new', '🌱 Новые за 7 дней'], ['watch', '👁 На контроле'], ['staff', '🎖 Персонал'], ['needs_staff_mark', '🏅 Персонал без регалии']];
const PICK = {on: false, ids: new Map()};   // выбор игроков для массовых действий: id -> имя; живёт, пока открыта админка
let MARKS = null;
const marksCatalog = async () => (MARKS = MARKS || await api('/marks'));

async function peopleView(ctx) {
  const v = ctx.view;
  let q = ctx.query.get('q') || '';
  let flt = ctx.query.has('f') ? ctx.query.get('f') : PREFS.get('people.filter', '');
  const valid = f => PEOPLE_FILTERS.some(([k]) => k === f) || /^(?:marked|missing):[a-z_]+$/.test(f) || ['manual_marks', 'no_manual_marks'].includes(f);
  if (!valid(flt)) flt = '';
  const markTitle = f => {
    if (f === 'manual_marks') return 'Есть ручные регалии';
    if (f === 'no_manual_marks') return 'Нет ручных регалий';
    const m = /^(marked|missing):(.+)$/.exec(f), mk = m && MARKS && MARKS.items.find(x => x.id === m[2]);
    return m ? `${m[1] === 'marked' ? 'Есть' : 'Нет'}: ${mk ? mk.glyph + ' ' + mk.title : m[2]}` : '';
  };
  const isMark = f => !!f && !PEOPLE_FILTERS.some(([k]) => k === f);
  v.innerHTML = `<div class="search sticky">${icon('search')}<input id="pplq" type="search" placeholder="ID, @ник, имя, тег или чат" value="${esc(q)}" autocomplete="off" enterkeyhint="search"/></div>
    <div class="chipset scroll" id="pplf">${PEOPLE_FILTERS.map(([k, t]) => `<button type="button" class="chip" data-on="flt" data-v="${k}" aria-pressed="${k === flt}">${esc(t)}</button>`).join('')}
      <button type="button" class="chip" data-on="marks" aria-pressed="${isMark(flt)}">🏅 ${isMark(flt) ? esc(markTitle(flt) || 'Регалии') : 'Регалии…'}</button></div>
    <div id="pplres">${skeleton(6).replace('sk sk-title', 'sk sk-title" style="display:none')}</div>`;
  ctx.mount();
  if (!coarse() && !q) setTimeout(() => { const f = v.querySelector('#pplq'); if (f && ctx.alive()) f.focus(); }, 50);   // с клавиатуры сразу печатать; на телефоне без нужды не поднимаем
  if (isMark(flt)) marksCatalog().then(() => { const c = v.querySelector('[data-on="marks"]'); if (c) c.textContent = '🏅 ' + markTitle(flt); }).catch(() => {});
  let timer, rows = [], total = 0, seq = 0;
  const host = () => v.querySelector('#pplres');

  const drawBar = () => {
    if (!PICK.on) { ctx.bar(''); return; }
    const n = PICK.ids.size, can = key => !key.startsWith('mark_') || ME.rank >= 5;
    ctx.bar(`<div><b>Выбрано: ${n}</b>${n ? `<button type="button" class="linkbtn" style="min-height:0;padding:0" data-on="clear">сбросить</button>` : 'Нажимайте на игроков'}</div>
      <div class="btns">${n ? Object.entries(BULK_TITLES).filter(([k]) => can(k)).map(([k, t]) => `<button type="button" class="btn sm" data-on="bulk" data-v="${k}">${esc(t)}</button>`).join('') : ''}
      <button type="button" class="btn sm ghost" data-on="done">Готово</button></div>`, {
      clear: () => { PICK.ids.clear(); paintPicked(); drawBar(); },
      done: () => { PICK.on = false; PICK.ids.clear(); draw(); drawBar(); },
      bulk: el => bulkRun(el.dataset.v, [...PICK.ids.keys()], () => { PICK.ids.clear(); loadPage(0); drawBar(); }).catch(e => toast(e.message, true)),
    }, 'wide');
  };
  const paintPicked = () => $$('[data-pid]', v).forEach(r => r.classList.toggle('picked', PICK.ids.has(+r.dataset.pid)));
  const playerLine = p => PICK.on
    ? row({lead: `<span class="tick" aria-hidden="true">✓</span>` + ava(p), title: esc(nameOf(p)), sub: `${p.name && p.username ? '@' + esc(p.username) + ' · ' : ''}ID ${p.id}`,
        on: 'pick', data: {pid: p.id, n: nameOf(p)}, chev: false, cls: PICK.ids.has(p.id) ? 'picked' : ''})
    : playerRow(p, {data: {pid: p.id}}, q);
  const draw = (data = null) => {
    if (data) { ({total = 0} = data); }
    const players = rows, chats = data ? data.chats || [] : (draw.chats || []);
    draw.chats = chats;
    const label = !q.trim() ? (flt ? (PEOPLE_FILTERS.find(f => f[0] === flt) || [])[1] || markTitle(flt) : 'Недавно активные') : '';
    const recent = !q.trim() && !flt && !PICK.on ? PREFS.get('recent', []) : [];
    host().innerHTML = (recent.length ? sh('Вы открывали') + `<div class="faces">${recent.map(r => `<a class="face" href="#/player/${r.id}">${ava({id: r.id, name: r.n, username: r.u, avatar: r.a})}<span>${esc(r.n || (r.u ? '@' + r.u : 'id' + r.id))}</span></a>`).join('')}</div>` : '')
      + (players.length || !chats.length ? sh(label ? esc(label) : 'Игроки', {count: total > players.length ? `${players.length} из ${num(total)}` : players.length}).replace('</div>',
        players.length ? `<button type="button" class="lnk" data-on="select">${PICK.on ? 'Готово' : 'Выбрать'}</button></div>` : '</div>') : '')
      + (players.length ? `<div class="list">${players.map(playerLine).join('')}</div>` : (q || flt ? emptyBox('Никого не нашли', q ? 'Проверьте написание или поищите по ID.' : 'В этом фильтре пока пусто.') : ''))
      + (draw.more ? `<button type="button" class="btn more" data-on="more">Показать ещё</button>` : '')
      + (!flt && chats.length ? sh('Чаты', {count: chats.length}) + `<div class="list">${chats.map(c => chatRow(c, {}, q)).join('')}</div>` : '');
  };
  // Поиск и фильтр не перерисовывают экран целиком: поле ввода не теряет фокус, старые ответы не перетирают новые.
  async function loadPage(off) {
    const mine = ++seq;
    const path = `/search?q=${encodeURIComponent(q.trim())}${flt ? '&filter=' + encodeURIComponent(flt) : ''}&offset=${off}`;
    const data = await ctx.load(path, {cache: off === 0});
    if (!ctx.alive() || mine !== seq) return;
    rows = off ? [...rows, ...data.players] : data.players;
    draw.more = data.next_offset != null && data.offset !== undefined;
    draw.next = data.next_offset;
    draw(data);
  }
  on(v, {
    flt: el => { if (el.dataset.v !== flt) setFilter(el.dataset.v); },
    marks: () => marksSheet(flt, setFilter),
    select: () => { PICK.on = !PICK.on; if (!PICK.on) PICK.ids.clear(); draw(); drawBar(); },
    pick: el => {
      const id = +el.dataset.pid;
      if (PICK.ids.has(id)) PICK.ids.delete(id);
      else if (PICK.ids.size < BULK_MAX) PICK.ids.set(id, el.dataset.n);
      else { toast(`За один раз можно выбрать до ${BULK_MAX} игроков.`, true); return; }
      paintPicked(); drawBar(); haptic('select');
    },
    more: el => busy(el, () => loadPage(draw.next)),
  });
  const setFilter = f => {
    flt = f; PREFS.set('people.filter', f); setQuery({f}); PICK.ids.clear(); drawBar();
    $$('#pplf [data-on="flt"]', v).forEach(c => c.setAttribute('aria-pressed', String(c.dataset.v === f)));
    const mc = v.querySelector('[data-on="marks"]');
    mc.setAttribute('aria-pressed', String(isMark(f)));
    mc.textContent = '🏅 ' + (isMark(f) ? markTitle(f) || 'Регалии' : 'Регалии…');
    loadPage(0).catch(e => toast(e.message, true));
  };
  v.querySelector('#pplq').addEventListener('input', e => {
    clearTimeout(timer);
    timer = setTimeout(() => { if (!ctx.alive()) return; q = e.target.value.trim(); setQuery({q}); loadPage(0).catch(err => toast(err.message, true)); }, 300);
  });
  await loadPage(0);
  drawBar();
}
// Регалии — длинный список: в отдельной шторке, а не выпадающим списком над результатами.
async function marksSheet(current, pick) {
  const cat = await marksCatalog().catch(e => { toast(e.message, true); return null; });
  if (!cat) return;
  const opt = (v, t) => row({title: esc(t), on: 'm', data: {v}, end: v === current ? '<b style="color:var(--accent)">✓</b>' : '', chev: false});
  const p = openSheet({title: 'Фильтр по регалиям', body: `<div class="list">${opt('', 'Все регалии')}${opt('manual_marks', 'Есть ручные регалии')}${opt('no_manual_marks', 'Нет ручных регалий')}</div>
    ${cat.items.map(m => sh(`${esc(m.glyph)} ${esc(m.title)}`) + `<div class="list">${opt('marked:' + m.id, 'Есть')}${opt('missing:' + m.id, 'Нет')}</div>`).join('')}`});
  on(p.el, {m: el => { closeSheets(); pick(el.dataset.v); }});
}
route('people', {section: 'people', root: true, title: () => 'Игроки и чаты', render: peopleView});

// ── Все действия над человеком — в одной шторке ───────────────────────────────
// Группы и подсказки: что произойдёт, если нажать. Опасные — красные; подтверждение и ввод ID — в runAction.
const ACTION_GROUPS = [
  ['chat', 'В этом чате', ['local_rank', 'warn', 'mute', 'unmute', 'kick', 'ban', 'unban', 'unwarn_all']],
  ['everywhere', 'Везде', ['global_ban', 'global_unban', 'block', 'unblock']],
  ['profile', 'Профиль', ['balance', 'vip', 'rank']],
  ['service', 'Служебное', ['revoke_sessions']],
];
const ACTION_HINTS = {
  local_rank: 'Права только в этом чате, глобальная роль не меняется', warn: 'Предупреждение; много — наказание по лимиту чата',
  mute: 'Не сможет писать в этом чате до конца срока', unmute: 'Снова сможет писать в этом чате', kick: 'Выйдет из чата, вернуться по ссылке сможет',
  ban: 'Не сможет вернуться в этот чат сам', unban: 'Снова сможет зайти в этот чат', unwarn_all: 'Снять все действующие предупреждения',
  global_ban: 'Потеряет доступ во всех чатах, где есть бот', global_unban: 'Снять бан во всех чатах бота', block: 'В чатах останется, команды не будут работать',
  unblock: 'Бот снова начнёт отвечать', balance: 'Мора, алмазы, эссенция; крупные суммы — с подтверждением', vip: 'Дни добавятся к текущему сроку',
  rank: 'Откроет или закроет разделы админки; только роль ниже своей', revoke_sessions: 'Выйдет из админки на всех устройствах',
};
// Какие действия в чате сейчас бессмысленны (мут уже стоит, бана нет и т. п.).
function memberFits(key, c) {
  return !(key === 'local_rank' && (c.left || c.local_rank >= 9))
    && !(key === 'mute' && c.muted) && !(key === 'unmute' && !c.muted)
    && !(key === 'unban' && !c.ban) && !(key === 'ban' && c.ban)
    && !(key === 'kick' && (c.left || c.ban)) && !(key === 'unwarn_all' && !c.warns);
}
// Какие действия «везде» показать: из взаимоисключающих пар — только возможное; сессии админки — только у сотрудников.
function playerActionKeys(p) {
  const hidden = new Set([p.blocked ? 'block' : 'unblock', p.global_ban ? 'global_ban' : 'global_unban']);
  if (!p.rank) hidden.add('revoke_sessions');
  return p.actions.player.map(a => a.key).filter(k => !hidden.has(k));
}
function actionRow(a, data) {
  const parts = a.title.split(' ');   // подпись с сервера начинается с эмодзи: «🔇 Замутить в чате» → значок + текст
  const glyph = parts.length > 1 ? parts[0] : '•', label = parts.length > 1 ? parts.slice(1).join(' ') : a.title;
  const danger = DANGEROUS.has(a.key);
  return row({lead: lead(esc(glyph), danger ? 'bad' : ''), title: esc(label), sub: esc(ACTION_HINTS[a.key] || ''), on: 'act', data, cls: danger ? 'danger' : ''});
}
function actionsSheet(p, chatId, reopen) {
  const chats = p.chats || [];
  const cur = chats.find(c => c.id === chatId) || chats[0] || null;
  const playerKeys = new Set(playerActionKeys(p)), member = new Set(p.actions.member.map(a => a.key));
  const parts = [];
  for (const [key, title, keys] of ACTION_GROUPS) {
    let list;
    if (key === 'chat') {
      if (!cur) continue;
      list = keys.filter(k => member.has(k) && memberFits(k, cur)).map(k => p.actions.member.find(a => a.key === k));
      parts.push(sh(title) + (chats.length > 1 ? `<div class="field" style="margin:0 0 4px"><select id="aschats" aria-label="Чат">${chats.map(c =>
        `<option value="${c.id}"${c.id === cur.id ? ' selected' : ''}>${esc(c.title)}</option>`).join('')}</select></div>` : `<p class="sub" style="margin:0">Чат: ${esc(cur.title)}</p>`));
      parts.push(list.length ? `<div class="list">${list.map(a => actionRow(a, {k: a.key, scope: 'member', cid: cur.id, ctitle: cur.title})).join('')}</div>` : '<p class="sub">В этом чате действий нет.</p>');
      continue;
    }
    list = keys.filter(k => playerKeys.has(k)).map(k => p.actions.player.find(a => a.key === k));
    if (list.length) parts.push(sh(esc(title)) + `<div class="list">${list.map(a => actionRow(a, {k: a.key, scope: 'player'})).join('')}</div>`);
  }
  const panel = openSheet({title: 'Действия', sub: `${nameOf(p)} · ID ${p.id}`, body: parts.join('')});
  const pick = panel.q('#aschats');
  if (pick) pick.onchange = () => { closeSheets(); actionsSheet(p, +pick.value, reopen); };
  const ctx = cur ? {...p, local_rank: cur.local_rank} : p;
  on(panel.el, {act: el => {
    if (el.dataset.scope === 'player') runAction(p.actions.player.find(a => a.key === el.dataset.k), `/player/${p.id}/action`, p, {}, reopen);
    else runAction(p.actions.member.find(a => a.key === el.dataset.k), `/player/${p.id}/action`, ctx, {chat_id: +el.dataset.cid, chat_title: el.dataset.ctitle}, reopen);
  }});
}

// ── Карточка игрока ──────────────────────────────────────────────────────────

const CUR_ICON = {mora: '🪙', diamonds: '💎', essence: '🔮', zarniki: '✨'};
const CUR_NAME = {mora: 'Мора', diamonds: 'Алмазы', essence: 'Эссенция', zarniki: 'Зарники'};
const PLAYER_TABS = [['chats', 'Чаты'], ['reports', 'Жалобы'], ['notes', 'Заметки'], ['history', 'История'], ['marks', 'Регалии'], ['more', 'Связи']];

async function playerView(ctx) {
  const id = +ctx.params.id;
  const p = await ctx.load(`/player/${id}`);
  if (!ctx.alive()) return;
  rememberPerson(p);
  const v = ctx.view, rp = p.reports || {total: 0, open: 0, confirmed: 0, last: []}, mk = p.marks || {given: [], earned: [], grantable: []};
  const tab = PLAYER_TABS.some(t => t[0] === ctx.query.get('tab')) ? ctx.query.get('tab') : PREFS.get('player.tab', 'chats');
  const lastSeen = p.chats.reduce((last, c) => (c.last && c.last > last ? c.last : last), '');
  const warns = p.chats.reduce((n, c) => n + (c.warns || 0), 0);
  const sanctioned = p.chats.filter(c => c.ban || c.muted).length;
  ctx.title(nameOf(p), p.rank_name || 'Игрок');
  // Вердикт одной строкой: можно не читать всю карточку, чтобы понять, «чистый» ли человек.
  const bansIn = p.chats.filter(c => c.ban).length, mutedIn = p.chats.filter(c => c.muted).length;
  const verdict = p.global_ban || p.blocked || bansIn
    ? ['bad', '!', 'Под наказанием', [p.global_ban ? 'бан во всех чатах' : '', p.blocked ? 'бот не отвечает' : '', bansIn ? `бан в ${bansIn} ${plural(bansIn, 'чате', 'чатах', 'чатах')}` : '', mutedIn ? `мут в ${mutedIn} ${plural(mutedIn, 'чате', 'чатах', 'чатах')}` : ''].filter(Boolean).join(' · ')]
    : mutedIn || warns || rp.open || p.watch
      ? ['warn', '•', 'Есть замечания', [mutedIn ? `мут в ${mutedIn} ${plural(mutedIn, 'чате', 'чатах', 'чатах')}` : '', warns ? `${warns} ${plural(warns, 'предупреждение', 'предупреждения', 'предупреждений')}` : '', rp.open ? `${rp.open} ${plural(rp.open, 'открытая жалоба', 'открытые жалобы', 'открытых жалоб')}` : '', p.watch ? 'на контроле' : ''].filter(Boolean).join(' · ')]
      : ['ok', '✓', 'Нарушений нет', rp.confirmed ? `раньше подтверждено жалоб: ${rp.confirmed}` : 'ни банов, ни мутов, ни предупреждений'];
  p.ring = verdict[0] === 'ok' ? '' : verdict[0];
  const pills = [
    p.rank ? pill(p.rank_name, 'accent') : '',
    p.vip ? pill(`👑 VIP · ${p.vip.days_left} дн.`, 'ok') : '', p.sponsor ? pill('спонсор', 'ok') : '',
    p.deleted_at ? pill('аккаунт удаляется', 'warn') : '',   // бан везде, «бот молчит» и контроль — ниже плашками с «Снять», не повторяем
  ].join('');
  // «Что сейчас»: состояние, которое важнее всего, и как его снять — рядом.
  const undo = key => playerActionKeys(p).includes(key) ? `<button type="button" class="btn sm" data-on="quick" data-k="${key}">Снять</button>` : '';
  const now = [
    p.global_ban ? callout('bad', '🚫', `<b>Бан во всех чатах</b>${p.global_ban.reason ? `<small>${esc(p.global_ban.reason)}</small>` : ''}`, undo('global_unban')) : '',
    p.blocked ? callout('bad', '🙈', `<b>Бот не отвечает</b><small>${p.blocked.until ? untilText(p.blocked.until) : 'пока не снимут'}${p.blocked.reason ? ' · ' + esc(p.blocked.reason) : ''}</small>`, undo('unblock')) : '',
    p.watch ? callout('warn', '👁', `<b>На контроле</b><small>${p.watch.reason ? esc(p.watch.reason) + ' · ' : ''}${who(p.watch.by.id, p.watch.by.username)}, ${ago(p.watch.at)}</small>`, '<button type="button" class="btn sm" data-on="watch">Снять</button>') : '',
  ].join('');
  const fam = p.family;
  const tabs = PLAYER_TABS.map(([k, t]) => {
    const n = k === 'chats' ? p.chats.length : k === 'reports' ? rp.total : k === 'notes' ? p.notes.total : k === 'marks' ? mk.given.length + mk.earned.length : null;
    const bad = k === 'chats' && sanctioned || k === 'reports' && rp.open;
    return `<button type="button" role="tab" data-on="tab" data-v="${k}" aria-selected="${k === tab}">${t}${n ? `<span class="n ${bad ? 'bad' : ''}">${n}</span>` : ''}</button>`;
  }).join('');
  v.innerHTML = `<div class="hero">${ava(p, 'lg')}<div><h2>${esc(nameOf(p))}</h2>
      <div class="ids">${p.username ? `<button type="button" data-on="copy" data-v="@${esc(p.username)}">@${esc(p.username)}</button>` : ''}<button type="button" data-on="copy" data-v="${p.id}">ID ${p.id}</button></div>
      ${pills ? `<div class="pills">${pills}</div>` : ''}</div></div>
    <div class="verdict ${verdict[0]}" role="status"><span class="vi" aria-hidden="true">${verdict[1]}</span><div><b>${verdict[2]}</b><small>${esc(verdict[3])}</small></div></div>
    ${now}
    <div class="facts">
      <div><span>Был</span><b>${lastSeen ? esc(ago(lastSeen)).replace(/ (\d\d:\d\d)$/, '<small>$1</small>') : 'не писал'}</b></div>
      <div><span>Сообщ. за 7 дн.</span><b>${num(p.messages.week)}</b></div>
      <button type="button" data-on="tab" data-v="chats"><span>Чатов</span><b>${p.chats.length}</b></button>
      <button type="button" data-on="tab" data-v="chats"><span>Предупреждений</span><b class="${warns ? 'warn' : ''}">${warns}</b></button>
      <button type="button" data-on="tab" data-v="reports"><span>Жалоб</span><b class="${rp.open ? 'bad' : ''}">${rp.total}${rp.open ? `<small>${rp.open} открыто</small>` : ''}</b></button>
      <button type="button" data-on="tab" data-v="notes"><span>Заметок</span><b>${p.notes.total}</b></button></div>
    <div class="money">${Object.keys(CUR_ICON).map(k => `<div title="${CUR_NAME[k]}: ${num(p.balances[k])}"><span aria-hidden="true">${CUR_ICON[k]}</span><b>${short(p.balances[k])}</b><small>${CUR_NAME[k]}</small></div>`).join('')}</div>
    <p class="line-i">💬 сегодня <b>${num(p.messages.today)}</b> · всего <b>${num(p.messages.total)}</b> · 🔥 стрик <b>${p.streak.current}</b> (лучший ${p.streak.best}) · 🏆 <b>${p.achievements.count}</b> достижений
      ${fam ? `<br>💞 ${fam.partner ? `В браке с <a href="#/player/${fam.partner}">${who(fam.partner, fam.partner_username)}</a>${fam.since ? ' с ' + new Date(fam.since).toLocaleDateString('ru-RU') : ''}` : 'Ребёнок в семье'}${fam.children ? ` · детей: ${fam.children}` : ''}` : ''}</p>
    <div class="btns grow mt">${p.watch ? '' : '<button type="button" class="btn" data-on="watch">👁 На контроль</button>'}
      ${p.username ? `<button type="button" class="btn" data-on="tgopen" data-v="${esc(p.username)}">✉️ Написать</button>` : ''}</div>
    <div class="tabs" role="tablist">${tabs}</div>
    <div id="ptab"></div>`;
  const drawTab = k => {
    PREFS.set('player.tab', k); setQuery({tab: k});
    $$('.tabs [data-on="tab"]', v).forEach(b => b.setAttribute('aria-selected', String(b.dataset.v === k)));
    v.querySelector('#ptab').innerHTML = PLAYER_TAB_DRAW[k](p, rp, mk);
  };
  drawTab(tab);
  const reopen = () => { CACHE.delete(`/player/${id}`); ctx.refresh(); };
  // Главная кнопка всегда под большим пальцем: лицо, имя и «Действия» в липкой панели, сколько ни листай карточку.
  ctx.bar(`${ava({...p, ring: p.ring}, 'sm')}<div><b>${esc(nameOf(p))}</b>${esc(verdict[2])}</div><div class="btns"><button type="button" class="btn sm primary" data-on="acts">Действия</button></div>`,
    {acts: () => actionsSheet(p, p.chats[0] ? p.chats[0].id : 0, reopen)});
  const memberAction = (key, cid) => {
    const c = p.chats.find(x => x.id === cid), a = p.actions.member.find(x => x.key === key);
    if (a && c) runAction(a, `/player/${id}/action`, {...p, local_rank: c.local_rank}, {chat_id: cid, chat_title: c.title, who: nameOf(p)}, reopen);
  };
  on(v, {
    tgopen: el => {   // профиль по @нику: в Telegram — родным переходом, в браузере — ссылкой t.me
      const url = 'https://t.me/' + el.dataset.v;
      try { if (TG && TG.openTelegramLink) { TG.openTelegramLink(url); return; } } catch (_) {}
      window.open(url, '_blank', 'noopener');
    },
    showall: el => { $$('[data-more-row]', v).forEach(r => { r.hidden = false; }); el.remove(); },
    tab: el => { drawTab(el.dataset.v); const t = v.querySelector('.tabs'); if (t.getBoundingClientRect().top < 0 || window.scrollY > t.offsetTop) window.scrollTo({top: t.offsetTop - 56, behavior: 'smooth'}); },
    copy: el => copyText(el.dataset.v, el.dataset.v.startsWith('@') ? 'Ник скопирован' : 'ID скопирован'),
    acts: () => actionsSheet(p, p.chats[0] ? p.chats[0].id : 0, reopen),
    chatacts: el => actionsSheet(p, +el.dataset.cid, reopen),
    mact: el => memberAction(el.dataset.k, +el.dataset.cid),
    quick: el => { const a = p.actions.player.find(x => x.key === el.dataset.k); if (a) runAction(a, `/player/${id}/action`, p, {}, reopen); },
    watch: () => {
      const done = async (onn, reason) => { await post(`/player/${id}/watch`, {on: onn, reason}); toast(onn ? 'Игрок на контроле' : 'Снят с контроля', {ok: true}); reopen(); };
      if (p.watch) done(false, '').catch(e => toast(e.message, true));
      else { const s = sheet('👁 На контроль', hint(`${esc(nameOf(p))} об этом не узнает, ограничений нет: это список для персонала, фильтр «На контроле».`) + reasonField(),
        'Поставить', s2 => done(true, s2.q('#freason').value)); wireFormChips(s.el); }
    },
    grant: el => markSheet('mark_grant', mk.grantable.find(m => m.id === el.dataset.v)),
    unmark: el => markSheet('mark_revoke', mk.given.find(m => m.id === el.dataset.v)),
    noteadd: el => busy(el, async () => {
      const t = v.querySelector('#notetext'), text = t.value.trim();
      if (!text) { toast('Напишите текст заметки', true); t.focus(); return; }
      const data = await post(`/player/${id}/notes`, {text});
      p.notes = data; t.value = ''; toast('Заметка добавлена', {ok: true}); CACHE.delete(`/player/${id}`); drawTab('notes');
    }),
    notedel: el => busy(el, async () => { p.notes = await api(`/player/${id}/notes/${el.dataset.v}`, {method: 'DELETE'}); toast('Заметка убрана', {ok: true}); CACHE.delete(`/player/${id}`); drawTab('notes'); }),
    notemore: el => busy(el, async () => {
      const more = await api(`/player/${id}/notes?offset=${p.notes.next}`);
      p.notes = {...more, items: [...p.notes.items, ...more.items]}; drawTab('notes');
    }),
  });
  const markSheet = (action, m) => {
    if (!m) return;
    const s = sheet(`${action === 'mark_grant' ? 'Выдать' : 'Снять'} регалию`, `<div class="mark held" style="margin-bottom:12px"><span class="g">${esc(m.glyph)}</span><b>${esc(m.title)}</b><small>${esc(m.desc || '')}</small></div>
      ${hint('Игрок: ' + esc(nameOf(p)))}${reasonField(true)}`, action === 'mark_grant' ? 'Выдать' : 'Снять', async s2 => {
      const reason = s2.q('#freason').value.trim();
      if (!reason) throw new Error('Укажите причину: она попадёт в журнал.');
      const res = await post(`/player/${id}/action`, {action, mark: m.id, reason});
      toast(res.message || 'Готово', {ok: true}); reopen();
    }, {kind: action === 'mark_grant' ? 'primary' : 'btn danger'});
    wireFormChips(s.el);
  };
}
// Вкладки карточки игрока: каждая — одна функция, рисует только свой кусок.
const PLAYER_TAB_DRAW = {
  chats(p) {
    if (!p.chats.length) return emptyBox('Не писал ни в одном чате с ботом');
    const member = new Set(p.actions.member.map(a => a.key));
    // Чаты с баном, мутом или предупреждениями — наверху: ради них карточку обычно и открывают.
    const weight = c => (c.ban ? 4 : 0) + (c.muted ? 2 : 0) + (c.warns ? 1 : 0);
    const list = [...p.chats].sort((a, b) => weight(b) - weight(a));
    const SHOW = 6;
    return `<div class="list" id="pchats">${list.map((c, i) => {
      const st = [c.ban ? pill(`⛔ бан ${c.ban.until ? untilText(c.ban.until) : 'навсегда'}`, 'bad') : '', c.muted ? pill(`🔇 мут ${c.muted_until ? untilText(c.muted_until) : 'навсегда'}`, 'warn') : '',
        c.warns ? pill(`⚠️ ${c.warns} ${plural(c.warns, 'предупреждение', 'предупреждения', 'предупреждений')}`, 'warn') : '', c.left ? pill('не в чате', '') : '', c.tag ? pill('🏷 ' + c.tag, '', true) : ''].join('');
      const quick = [c.ban && member.has('unban') ? ['unban', 'Снять бан'] : null, c.muted && member.has('unmute') ? ['unmute', 'Снять мут'] : null,
        c.warns && member.has('unwarn_all') ? ['unwarn_all', 'Снять предупр.'] : null].filter(Boolean);
      const acts = p.actions.member.some(a => memberFits(a.key, c));
      return `<div class="row" style="flex-wrap:wrap"${i >= SHOW ? ' hidden data-more-row' : ''}>${chatAva({...c, ring: c.ban ? 'bad' : c.muted || c.warns ? 'warn' : ''}, 'sm')}<span class="row-t"><b><a href="#/chat/${c.id}" style="color:inherit">${esc(c.title)}</a></b>
          <span>${esc(c.rank_name)} · ${num(c.messages)} сообщ.${c.last ? ' · ' + ago(c.last) : ''}</span>${st ? `<span class="pills">${st}</span>` : ''}</span>
        ${quick.length || acts ? `<div class="btns" style="flex-basis:100%;padding-left:44px">${quick.map(([k, t]) => `<button type="button" class="btn sm" data-on="mact" data-k="${k}" data-cid="${c.id}">${t}</button>`).join('')}
          ${acts ? `<button type="button" class="btn sm ghost" data-on="chatacts" data-cid="${c.id}">Действия в чате</button>` : ''}</div>` : ''}</div>`;
    }).join('')}</div>${list.length > SHOW ? `<button type="button" class="btn more" data-on="showall">Показать все чаты · ${list.length}</button>` : ''}`;
  },
  reports(p, rp) {
    if (!rp.total) return emptyBox('Жалоб не было');
    return `<div class="stats three" style="margin-top:8px">${stat('Всего', rp.total)}${stat('Открытых', rp.open, {tone: rp.open ? 'warn' : ''})}${stat('Подтверждено', rp.confirmed, {tone: rp.confirmed ? 'bad' : ''})}</div>
      <div class="list">${rp.last.map(r => row({lead: lead('⚑', r.status === 'resolved' ? 'bad' : r.status === 'rejected' ? '' : 'warn'), title: esc(r.reason), sub: `№${r.id} · ${ago(r.created_at)} · ${esc(r.chat)}`,
        end: pill(r.status_title, r.status === 'resolved' ? 'bad' : r.status === 'rejected' ? '' : 'warn')})).join('')}</div>
      ${has('reports') ? `<p class="sub">Авторов жалоб здесь не видно: жалобы анонимны. <a href="#/reports">Все жалобы ›</a></p>` : ''}`;
  },
  notes(p) {
    const n = p.notes;
    return `<div class="field" style="margin-top:10px"><textarea id="notetext" maxlength="1000" placeholder="Что важно знать другим модераторам"></textarea>
        <div class="hint">Видят только сотрудники, игрок — нет.</div></div>
      <button type="button" class="btn primary block" data-on="noteadd">Добавить заметку</button>
      <div class="list" style="margin-top:8px">${n.items.map(x => `<div class="ev"><div><div class="ev-t" style="white-space:pre-wrap">${esc(x.text)}</div>
          <div class="ev-m">${person(x.author)}<span>${ago(x.at)}</span></div></div>${x.can_remove ? `<button type="button" class="ib" data-on="notedel" data-v="${x.id}" aria-label="Убрать заметку">${icon('trash')}</button>` : ''}</div>`).join('')
        || emptyBox('Пока нет заметок')}</div>
      ${n.next ? '<button type="button" class="btn more" data-on="notemore">Показать ещё</button>' : ''}`;
  },
  history(p) { return journalList(p.history, {user: false}); },
  marks(p, rp, mk) {
    const canGrant = p.actions.player.some(a => a.key === 'mark_grant'), canRevoke = p.actions.player.some(a => a.key === 'mark_revoke');
    const held = new Set(mk.given.map(m => m.id)), free = mk.grantable.filter(m => !held.has(m.id));
    const tile = (m, act) => `<${act ? 'button type="button"' : 'div'} class="mark ${act === 'unmark' || !act ? 'held' : ''}" ${act ? `data-on="${act}" data-v="${esc(m.id)}"` : ''}>
      <span class="g">${esc(m.glyph)}</span><b>${esc(m.title)}</b><small>${act === 'unmark' ? 'Нажмите, чтобы снять' : esc(m.desc || '')}</small></${act ? 'button' : 'div'}>`;
    return `${sh('Выданы', {count: mk.given.length})}${mk.given.length ? `<div class="marks">${mk.given.map(m => tile(m, canRevoke ? 'unmark' : '')).join('')}</div>` : '<p class="sub">Пока ни одной.</p>'}
      ${mk.earned.length ? sh('Заработаны в игре', {count: mk.earned.length}) + `<div class="marks">${mk.earned.map(m => tile(m, '')).join('')}</div><p class="sub">Их выдаёт игра, вручную не снимаются.</p>` : ''}
      ${canGrant ? sh('Выдать') + (free.length ? `<div class="marks">${free.map(m => tile(m, 'grant')).join('')}</div>` : '<p class="sub">Все регалии уже выданы.</p>')
        : '<p class="sub">Выдавать регалии может роль «Разработчик» и выше.</p>'}`;
  },
  more(p) {
    const lk = p.linked, NAME_KINDS = {username: '@ник', name: 'имя'};
    const link = (u, extra = '') => row({lead: ava(u, 'sm'), title: who(u.id, u.username), sub: extra, href: '#/player/' + u.id});
    const parts = [];
    if (lk) {
      const any = lk.invited_by || lk.invited.total || lk.same_username.length || lk.same_name.length;
      parts.push(sh('🔗 Возможные связи') + (any ? `<div class="list">${lk.invited_by ? link(lk.invited_by, 'пригласил его') : ''}
        ${lk.invited.items.map(u => link(u, 'пришёл по его приглашению')).join('')}
        ${lk.same_username.map(u => link(u, 'тот же ник: @' + esc(u.value))).join('')}${lk.same_name.map(u => link(u, 'такое же имя: ' + esc(u.name))).join('')}</div>
        ${lk.invited.total > lk.invited.items.length ? `<p class="sub">Пригласил ещё ${lk.invited.total - lk.invited.items.length}</p>` : ''}` : '<p class="sub">Связей не найдено.</p>')
        + help('Как это считается', '<p>Совпадение ника или имени — повод присмотреться, а не доказательство. Устройства и адреса бот не собирает.</p>'));
    }
    if (p.names.length) parts.push(sh('🕘 Как назывался в Telegram') + `<div class="list">${p.names.map(n => row({title: esc(n.kind === 'username' ? '@' + n.value : n.value), sub: `${NAME_KINDS[n.kind] || n.kind} · с ${when(n.at)}`})).join('')}</div>`);
    if (p.nicknames.length) parts.push(sh('Ники в чатах') + `<div class="list">${p.nicknames.map(n => row({title: esc(n.nickname), sub: esc(n.chat.title), href: '#/chat/' + n.chat.id})).join('')}</div>`);
    if (p.tag_history && p.tag_history.length) parts.push(sh('🏷 Теги в чатах') + `<div class="list">${p.tag_history.map(t => row({title: t.tag ? esc(t.tag) : '— тег убрали —', sub: `${esc(t.chat_title || t.chat_id)} · ${ago(t.at)}`, href: '#/chat/' + t.chat_id})).join('')}</div>`);
    return parts.join('') || emptyBox('Ничего не записано');
  },
};
route('player/:id', {section: 'people', up: () => 'people', title: () => 'Игрок', stats: true, render: playerView});

// ── Карточка чата ────────────────────────────────────────────────────────────

const CHAT_TABS = [['sanctions', 'Нарушители'], ['top', 'Активные'], ['history', 'История'], ['settings', 'Настройки']];
async function chatView(ctx) {
  const id = +ctx.params.id;
  const c = await ctx.load(`/chat/${id}`);
  if (!ctx.alive()) return;
  const v = ctx.view, m = c.messages, s = c.sanctions;
  const nSanc = s.bans.total + s.mutes.total + s.warns.total;
  const tab = CHAT_TABS.some(t => t[0] === ctx.query.get('tab')) ? ctx.query.get('tab') : (nSanc ? 'sanctions' : 'top');
  ctx.title(c.title, 'Чат');
  const acts = c.actions.chat.filter(a => !(a.key === 'close' && c.closed) && !(a.key === 'open' && !c.closed));
  const pills = [c.closed ? pill('🔒 закрыт', 'warn') : pill('открыт', 'ok'),
    c.bot && c.bot.left_at ? pill('бота удалили ' + ago(c.bot.left_at), 'bad') : c.bot && c.bot.can_moderate === false ? pill('у бота нет прав', 'warn') : '',
    pill(`⚠️ лимит ${c.warn_limit}`, '', true), c.tagged ? pill(`🏷 с тегом: ${c.tagged}`, '', true) : '',
    c.switched_off.length ? pill(`выключено функций: ${c.switched_off.length}`, 'warn') : ''].join('');
  v.innerHTML = `<div class="hero">${chatAva(c, 'lg')}<div><h2>${esc(c.title)}</h2>
      <div class="ids"><button type="button" data-on="copy" data-v="${c.id}">ID ${c.id}</button></div><div class="pills">${pills}</div></div></div>
    ${c.bot && c.bot.can_moderate === false && !c.bot.left_at ? callout('warn', '⚠️', '<b>У бота нет прав модерации</b><small>Мут, бан и чистка не сработают, пока боту не выдадут права администратора.</small>') : ''}
    ${c.switched_off.length ? callout('warn', '⏻', `<b>Выключено: ${c.switched_off.map(x => esc(x.title)).join(', ')}</b>${c.switched_off.some(x => x.reason) ? `<small>${c.switched_off.filter(x => x.reason).map(x => esc(x.reason)).join('; ')}</small>` : ''}`,
      has('switches') ? `<a class="btn sm" href="#/switches/${c.id}">Функции</a>` : '') : ''}
    <div class="stats three">${stat('Участников', num(c.members))}${stat('Сегодня', num(m.today.messages), {small: `${m.today.active} чел.`})}${stat('7 дней', num(m.week.messages), {small: `${m.week.active} чел.`})}</div>
    <p class="line-i">Владелец: ${c.owner ? `<a href="#/player/${c.owner.id}">${who(c.owner.id, c.owner.username)}</a>` : 'неизвестен'}${c.admin_chat ? ` · админ-чат: <a href="#/chat/${c.admin_chat.id}">${esc(c.admin_chat.title)}</a>` : ''}
      · 30 дней <b>${num(m.month.messages)}</b> (${m.month.active} чел.) · всего <b>${num(m.total)}</b></p>
    <div class="btns mt">${acts.map(a => `<button type="button" class="btn sm ${a.key === 'leave' ? 'danger' : ''}" data-on="act" data-k="${a.key}">${esc(a.title)}</button>`).join('')}
      ${has('switches') ? `<a class="btn sm" href="#/switches/${c.id}">⏻ Функции чата</a>` : ''}<a class="btn sm" href="${BASE}/?startapp=purge_${c.id}">Чистка ›</a></div>
    <div class="tabs" role="tablist">${CHAT_TABS.map(([k, t]) => `<button type="button" role="tab" data-on="tab" data-v="${k}" aria-selected="${k === tab}">${t}${k === 'sanctions' && nSanc ? `<span class="n bad">${nSanc}</span>` : ''}</button>`).join('')}</div>
    <div id="ctab"></div>`;
  const can = key => c.actions.member.find(a => a.key === key);
  const SANCTIONS = {
    bans: ['⛔ Баны', x => (x.until ? untilText(x.until) : 'навсегда') + (x.reason ? ' · ' + esc(x.reason) : ''), 'unban', 'bad'],
    mutes: ['🔇 Муты', x => x.until ? untilText(x.until) : 'навсегда', 'unmute', 'warn'],
    warns: ['⚠️ Предупреждения', x => `действующих: ${x.count}`, 'unwarn_all', 'warn'],
  };
  const sanctionRow = (kind, x) => {
    const [, line, undo] = SANCTIONS[kind];
    return `<div class="row">${ava({id: x.user, username: x.username, avatar: x.avatar, name: x.name})}<span class="row-t"><b><a href="#/player/${x.user}" style="color:inherit">${who(x.user, x.username)}</a>${x.tag ? ` <span class="sub">[${esc(x.tag)}]</span>` : ''}</b><span>${line(x)}</span></span>
      ${can(undo) ? `<button type="button" class="btn sm" data-on="undo" data-k="${undo}" data-uid="${x.user}" data-who="${esc(x.username ? '@' + x.username : 'id' + x.user)}">Снять</button>` : ''}</div>`;
  };
  const TAB = {
    sanctions: () => nSanc ? Object.keys(SANCTIONS).filter(k => s[k].total).map(k => `<div data-kind="${k}">${sh(SANCTIONS[k][0], {count: s[k].total})}<div class="list srows">${s[k].items.map(x => sanctionRow(k, x)).join('')}</div>
      ${s[k].next ? `<button type="button" class="btn more" data-on="smore" data-v="${k}" data-next="${s[k].next}">Показать ещё</button>` : ''}</div>`).join('') : emptyBox('Нарушителей нет', 'Банов, мутов и предупреждений сейчас нет.'),
    top: () => {
      if (!c.top.length) return emptyBox('Пока никого');
      const max = Math.max(1, ...c.top.map(x => x.messages));
      return `<div class="list">${c.top.map((x, i) => `<a class="row" href="#/player/${x.id}">${ava(x)}<span class="row-t"><b>${i < 3 ? `<span class="medal" aria-label="место ${i + 1}">${['🥇', '🥈', '🥉'][i]}</span> ` : ''}${who(x.id, x.username)}</b>
        <span>${x.tag ? `[${esc(x.tag)}] · ` : ''}${num(x.messages)} сообщ.</span>${meter(x.messages / max * 100, i === 0 ? 'accent' : '')}</span><span class="chev" aria-hidden="true">›</span></a>`).join('')}</div>`;
    },
    history: () => journalList(c.history, {chat: false}),
    settings: () => chatRightsCard(c) + chatSettingsCard(c.settings) || emptyBox('Настроек нет'),
  };
  const drawTab = k => { setQuery({tab: k}); $$('.tabs [data-on="tab"]', v).forEach(b => b.setAttribute('aria-selected', String(b.dataset.v === k))); v.querySelector('#ctab').innerHTML = TAB[k](); };
  drawTab(tab);
  const reopen = () => { CACHE.delete(`/chat/${id}`); ctx.refresh(); };
  on(v, {
    tab: el => drawTab(el.dataset.v),
    copy: el => copyText(el.dataset.v, 'ID скопирован'),
    act: el => runAction(c.actions.chat.find(a => a.key === el.dataset.k), `/chat/${id}/action`, c, {}, reopen),
    undo: el => runAction(can(el.dataset.k), `/player/${el.dataset.uid}/action`, c, {chat_id: id, chat_title: c.title, who: el.dataset.who}, reopen),
    smore: el => busy(el, async () => {
      const kind = el.dataset.v, page = await api(`/chat/${id}/sanctions?kind=${kind}&offset=${el.dataset.next}`);
      s[kind].items.push(...page.items); s[kind].next = page.next;
      el.closest('[data-kind]').querySelector('.srows').insertAdjacentHTML('beforeend', page.items.map(x => sanctionRow(kind, x)).join(''));
      if (page.next) el.dataset.next = page.next; else el.remove();
    }),
    crdefaults: () => c.rank_rights.actions.forEach(a => { v.querySelector(`#cr-${a.key}`).value = a.default; }),
    crsave: el => busy(el, async () => {
      const changes = {}, expected = {};
      $$('[data-right]', v).forEach(x => { const k = x.dataset.right, val = +x.value; if (val !== c.rank_rights.values[k]) { changes[k] = val; expected[k] = c.rank_rights.values[k]; } });
      if (!Object.keys(changes).length) { toast('Нет изменений'); return; }
      const reason = v.querySelector('#crreason').value.trim();
      if (reason.length < 3) { toast('Укажите причину изменения', true); v.querySelector('#crreason').focus(); return; }
      const result = await post(`/chat/${id}/rights`, {changes, expected, reason});
      toast(result.message, {ok: true}); reopen();
    }),
  });
}
// Права рангов чата: минимальный ранг для каждого действия, с причиной и проверкой конфликта на сервере.
function chatRightsCard(c) {
  const r = c.rank_rights;
  if (!r || !c.can_edit_rights) return '';
  return `${sh('Права рангов')}<p class="sub" style="margin-top:0">Минимальный ранг для каждого действия; старшие ранги тоже получают право.</p>
    <details class="fold"><summary>Настроить <span class="cnt">${r.actions.length} прав</span></summary>
    ${r.actions.map(a => field(esc(a.title), `<select id="cr-${a.key}" data-right="${a.key}">${r.ranks.map(x => `<option value="${x.rank}" ${x.rank === r.values[a.key] ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}</select>`, '', 'cr-' + a.key)).join('')}
    <button type="button" class="btn sm" data-on="crdefaults">Стандартные права</button>
    ${field('Причина изменения', '<input id="crreason" minlength="3" maxlength="200" placeholder="Что и зачем меняем"/>', '', 'crreason')}
    <button type="button" class="btn primary block" data-on="crsave">Сохранить права чата</button></details>`;
}
// Настройки чата одним взглядом. Меняются командами в самом чате и в «Функциях».
function chatSettingsCard(st) {
  if (!st || !st.ranks) return '';
  const flag = (title, onn) => pill(title, onn ? 'ok' : '');
  return `${sh('Кто что может')}<div class="list">${st.ranks.map(r => row({title: esc(r.title), end: esc(r.name)})).join('')}</div>
    ${sh('Чистка')}<p class="sub" style="margin:0">${st.purge.on ? 'Включена' : 'Выключена'} · запускает ${esc(st.purge.min_rank)} · действия с ${esc(st.purge.action_rank)}${st.shield_days ? ` · защита ${st.shield_days} дн.` : ''}</p>
    ${sh('Модули')}<div class="pills">${st.modules.map(m => flag(m.icon + ' ' + m.name, m.on)).join('')}</div>
    ${sh('Прочее')}<div class="pills">${st.flags.map(f => flag(f.title, f.on)).join('')}</div>`;
}
route('chat/:id', {section: 'people', up: () => 'people', title: () => 'Чат', stats: true, render: chatView});
