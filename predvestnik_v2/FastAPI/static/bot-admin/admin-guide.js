// ── Справка для администрации (S09): данные guide-admin.json, показ на примитивах админки ($, esc, pageHead, section, sheet, open) ──
// Темы того же вида, что в Путеводителе игрока (группы → темы → блоки, словарь, вопросы), плюс min_rank (с какой роли тема нужна),
// section (кнопка «Открыть» — open(section)) и owner (видит владелец чата). Роль видит только свои темы: ME.rank, ME.sections, ME.owner.
// Новая функция админки = тема в guide-admin.json в том же коммите (tools/test_admin_guide_contract.py сверит разделы, действия и пороги с кодом).
const AG = {data: null, pending: null, view: 'hub', topic: '', q: '', history: [], from: ''};
const AG_STOP = new Set(['как', 'где', 'что', 'это', 'для', 'мне', 'или', 'почему', 'если', 'можно', 'нужно', 'делать', 'игрока', 'игроку']);
const agNorm = s => String(s || '').toLowerCase().replace(/ё/g, 'е').replace(/[^a-zа-я0-9 ]+/g, ' ');
const agStem = w => w.length >= 7 ? w.slice(0, 5) : w.length >= 5 ? w.slice(0, -2) : w.length >= 4 ? w.slice(0, -1) : w;
const agWords = s => agNorm(s).split(/\s+/).filter(w => w.length > 2 && !AG_STOP.has(w));

function agVisible(t) {
  if (!ME) return false;
  if (ME.owner) return !!t.owner;   // владелец чата: только про свои чаты
  return ME.rank >= t.min_rank && (!t.section || t.section === 'mychats' || ME.sections.some(s => s.key === t.section));
}
const agTopics = () => (AG.data ? AG.data.topics.filter(agVisible) : []);
const agTopic = id => agTopics().find(t => t.id === id);

function agLoad() {
  if (AG.data) return Promise.resolve(AG.data);
  if (!AG.pending) AG.pending = fetch(BASE + '/bot-admin/guide-admin.json', {cache: 'no-cache'})
    .then(r => { if (!r.ok) throw new Error('Справка не загрузилась'); return r.json(); })
    .then(d => { if (!d || !Array.isArray(d.topics)) throw new Error('Справка повреждена'); AG.data = d; return d; })
    .finally(() => { AG.pending = null; });
  return AG.pending;
}

// Поиск: все слова запроса (по началу слова); не нашлось — одна опечатка в слове (замена, лишняя или пропущенная буква).
function agDist1(a, b) {
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0, j = 0, diff = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; continue; }
    if (++diff > 1) return false;
    if (a.length > b.length) i++; else if (b.length > a.length) j++; else { i++; j++; }
  }
  return diff + (a.length - i) + (b.length - j) <= 1;
}
function agFind(q) {
  const need = [...new Set(agWords(q).map(agStem))];
  if (!need.length) return [];
  const rows = agTopics().map(t => {
    const text = agWords([t.title, t.lead, (t.kw || []).join(' '), ...t.blocks.flatMap(b => [b.h, b.text, ...(b.items || []).flatMap(i => [i.h, i.p, i.w])])].filter(Boolean).join(' '));
    const hit = n => text.some(w => w.startsWith(n)) ? 2 : n.length >= 4 && text.some(w => agDist1(n, w.slice(0, n.length))) ? 1 : 0;
    const scores = need.map(hit);
    const title = agWords(t.title + ' ' + (t.kw || []).join(' '));
    return {t, ok: scores.every(Boolean), score: scores.reduce((a, b) => a + b, 0) + need.filter(n => title.some(w => w.startsWith(n))).length * 3};
  }).filter(r => r.ok);
  return rows.sort((a, b) => b.score - a.score).slice(0, 10).map(r => r.t);
}

const agRow = t => `<button type="button" class="ag-row" data-ag="${esc(t.id)}"><span class="ag-ic" aria-hidden="true">${esc(t.icon)}</span><span><b>${esc(t.title)}</b><small>${esc(t.lead)}</small></span><i aria-hidden="true">›</i></button>`;
const agSearchBox = () => `<input type="search" id="ag-q" class="ag-q" placeholder="Что ищешь? Например: мут" value="${esc(AG.q)}" autocomplete="off" enterkeyhint="search" aria-label="Поиск по справке">`;
const AG_BLOCK = {
  what: b => `<p class="ag-what">${esc(b.text)}</p>`,
  steps: b => `<h3 class="sec-title">${esc(b.h || '')}</h3><ol class="ag-steps">${b.items.map(i => `<li><b>${esc(i.h)}</b><span>${esc(i.p)}</span></li>`).join('')}</ol>`,
  gives: b => `<h3 class="sec-title">${esc(b.h || '')}</h3><ul class="ag-list">${b.items.map(i => `<li><span aria-hidden="true">${esc(i.i)}</span><b>${esc(i.h)}</b><small>${esc(i.p)}</small></li>`).join('')}</ul>`,
  words: b => `<h3 class="sec-title">${esc(b.h || '')}</h3><dl class="ag-words">${b.items.map(i => `<div><dt>${esc(i.w)}</dt><dd>${esc(i.p)}</dd></div>`).join('')}</dl>`,
  tip: b => `<aside class="ag-note"><b>Совет</b><p>${esc(b.text)}</p></aside>`,
  warn: b => `<aside class="ag-note ag-warn" role="note"><b>Осторожно</b><p>${esc(b.text)}</p></aside>`,
};
AG_BLOCK.list = AG_BLOCK.gives;

function agHub(main) {
  const groups = AG.data.groups.map((g, n) => {
    const rows = g.topics.map(agTopic).filter(Boolean);
    return rows.length ? `<details class="section ag-group" id="ag-group-${esc(g.id)}"${n === 0 || AG.openGroup === g.id ? ' open' : ''}><summary class="sec-h">${esc(g.icon)} ${esc(g.title)} <small class="cnt">· ${rows.length}</small></summary><div class="sec-body">${rows.map(agRow).join('')}</div></details>` : '';
  }).join('');
  const faq = AG.data.faq.filter(f => agTopic(f.t));
  const glossary = AG.data.glossary.filter(g => agTopic(g.t));
  main.innerHTML = `${pageHead('📘', 'Справка', ME.owner ? 'Как управлять своими чатами' : `Что умеет админка для роли «${ME.rank_name}» и как делать типовые задачи`)}
    ${agSearchBox()}<div id="ag-results" aria-live="polite"></div>
    <div id="ag-home">${groups}
      ${faq.length ? section('ag-faq', 'Частые вопросы', faq.map(f => `<details class="ag-faq"><summary>${esc(f.q)}</summary><p>${esc(f.a)}</p><button type="button" class="ag-link" data-ag="${esc(f.t)}">Читать тему ›</button></details>`).join(''), {fold: true, open: false, count: faq.length}) : ''}
      ${glossary.length ? section('ag-words', 'Словарь', `<dl class="ag-words">${glossary.map(g => `<div><dt>${esc(g.w)}</dt><dd>${esc(g.p)}</dd></div>`).join('')}</dl>`, {fold: true, open: false, count: glossary.length}) : ''}</div>`;
  const input = $('#ag-q', main);
  input.oninput = () => agSearch(main);
  if (AG.q) agSearch(main);
}
function agSearch(main) {
  const input = $('#ag-q', main); AG.q = input.value.trim();
  const out = $('#ag-results', main), home = $('#ag-home', main);
  if (!AG.q) { out.innerHTML = ''; home.hidden = false; return; }
  const found = agFind(AG.q);
  home.hidden = true;
  out.innerHTML = found.length ? `<div class="sub" style="margin:10px 0 4px">Подходящие темы · ${found.length}</div>${found.map(agRow).join('')}`
    : `<div class="empty">Ничего не нашлось. Попробуй коротко: «мут», «бан», «жалобы», «права».</div>`;
}
function agTopicView(main, t) {
  const group = AG.data.groups.find(g => g.topics.includes(t.id));
  const marks = t.blocks.map((b, i) => [b.h, i]).filter(([h]) => h);
  const toc = marks.length >= 3 ? `<details class="ag-toc"><summary>Содержание · ${marks.length}</summary><ol>${marks.map(([h, i]) => `<li><button type="button" class="ag-link" data-ag-block="${i}">${esc(h)}</button></li>`).join('')}</ol></details>` : '';
  const go = t.section && t.where.go && (t.section === 'mychats' ? ME.sections.some(s => s.key === 'mychats') : ME.sections.some(s => s.key === t.section))
    ? `<button type="button" class="btn primary" data-ag-open="${esc(t.section)}">${esc(t.where.label)}</button>` : '';
  const more = (t.next || []).map(agTopic).filter(Boolean);
  main.innerHTML = `<div class="bar"><button type="button" class="btn small" id="ag-back">← Назад</button></div>
    <nav class="ag-crumbs" aria-label="Где ты в справке"><button type="button" class="ag-link" data-ag-home="1">Справка</button>${group ? ` › <button type="button" class="ag-link" data-ag-group="${esc(group.id)}">${esc(group.title)}</button>` : ''}</nav>
    ${pageHead(t.icon, t.title, t.lead)}${agSearchBox()}${toc}
    ${t.blocks.map((b, i) => `<div class="ag-b" id="ag-b-${i}">${(AG_BLOCK[b.t] || (() => ''))(b)}</div>`).join('')}
    <section class="ag-where"><div><small>Где это</small><b>${esc(t.where.path)}</b></div>${go}</section>
    ${more.length ? section('ag-next', 'Читай дальше', more.map(agRow).join('')) : ''}`;
  $('#ag-back', main).onclick = () => agBack(main);
  $('#ag-q', main).oninput = e => { AG.history.push({view: 'topic', topic: t.id}); AG.view = 'hub'; AG.q = e.target.value; agPaint(main); const q = $('#ag-q', main); q.focus(); q.setSelectionRange(q.value.length, q.value.length); };
}
function agPaint(main) {
  main.removeAttribute('aria-busy');
  const t = AG.view === 'topic' && agTopic(AG.topic);
  if (t) agTopicView(main, t); else agHub(main);
  window.scrollTo(0, 0);
}
function agGo(main, id) {
  if (!agTopic(id)) return;
  AG.history.push({view: AG.view, topic: AG.topic}); if (AG.history.length > 40) AG.history.shift();
  AG.view = 'topic'; AG.topic = id; agPaint(main);
}
// «Назад»: по шагам внутри справки; первая тема, открытая из раздела, возвращает в этот раздел.
function agBack(main) {
  const prev = AG.history.pop();
  if (prev) { AG.view = prev.view; AG.topic = prev.topic; return agPaint(main); }
  if (AG.view === 'topic' && AG.from) return open(AG.from);
  AG.view = 'hub'; AG.topic = ''; agPaint(main);
}
// Справка открывается разделом «Справка» (в доке или «Ещё») и значком «?» в шапке — сразу на теме того раздела, где ты сейчас.
function openAdminGuide(topicId = '', from = '') {
  AG.history = []; AG.from = from; AG.q = '';
  AG.view = topicId ? 'topic' : 'hub'; AG.topic = topicId;
  open('guide');
}
function agContext() {
  const here = currentSection();
  if (here === 'guide') return openAdminGuide();
  agLoad().then(() => {
    const t = agTopics().find(x => x.section === here && !x.actions) || agTopics().find(x => x.section === here);
    openAdminGuide(t ? t.id : '', here);
  }).catch(() => openAdminGuide('', here));
}
// «Что это значит?» в окне опасного действия: тема этого действия, «Назад» вернёт в раздел.
function agWhy(action) {
  const box = $('#sheet'); if (box) { box.hidden = true; box.innerHTML = ''; }
  const here = currentSection();
  agLoad().then(() => openAdminGuide((agTopics().find(t => (t.actions || []).includes(action)) || {}).id || '', here)).catch(() => openAdminGuide('', here));
}

SECTIONS.guide = main => agLoad().then(() => agPaint(main)).catch(e => {
  main.removeAttribute('aria-busy');
  main.innerHTML = `${pageHead('📘', 'Справка')}${alertBox('bad', esc(e.message || 'Справка не загрузилась'))}<button type="button" class="btn" data-ag-open="guide">Повторить</button>`;
});
SECTION_META.guide = ['📘', 'Справка', 'Собираем темы для вашей роли'];
ICONS.guide = '<path d="M5 4.5h9.5a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h9.5M9 8.5h5"/>';
SHORT.guide = 'Справка';

document.addEventListener('click', e => {
  const main = $('#main');
  if (!main || currentSection() !== 'guide' && !e.target.closest('[data-ag-why]')) return;
  const why = e.target.closest('[data-ag-why]'); if (why) { agWhy(why.dataset.agWhy); return; }
  const row = e.target.closest('[data-ag]'); if (row) { agGo(main, row.dataset.ag); return; }
  const openKey = e.target.closest('[data-ag-open]'); if (openKey) { open(openKey.dataset.agOpen); return; }
  if (e.target.closest('[data-ag-home]')) { AG.history = []; AG.view = 'hub'; AG.topic = ''; agPaint(main); return; }
  const grp = e.target.closest('[data-ag-group]');
  if (grp) { AG.history.push({view: AG.view, topic: AG.topic}); AG.view = 'hub'; AG.topic = ''; AG.q = ''; AG.openGroup = grp.dataset.agGroup; agPaint(main); const g = $('#ag-group-' + grp.dataset.agGroup); if (g) { g.open = true; g.scrollIntoView({block: 'start'}); } return; }
  const blk = e.target.closest('[data-ag-block]'); if (blk) { const b = $('#ag-b-' + blk.dataset.agBlock); if (b) b.scrollIntoView({block: 'start'}); }
});
