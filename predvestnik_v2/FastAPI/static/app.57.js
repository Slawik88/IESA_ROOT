// ── «Путеводитель» (вкладка «Ещё» › «Путеводитель», #pg-help): темы, словарь и быстрые ответы из guide-v3.json ─────────────
// Все тексты — в данных (FastAPI/static/guide-v3.json), здесь только показ: главная с поиском и группами, тема из блоков
// (что это · шаги · что даёт · слова · совет · где найти), «Читать по порядку», словарь и частые вопросы. Правила текстов — docs/PLAYER_COPY.md.
// Ссылка на тему: ?startapp=guide_<id> (app.02.js), из подсказок и игр — openGuide('<id>'). Стили: guide-v3.css (префикс gv-).
const _GV = { data: null, pending: null, view: 'hub', topic: '', faq: -1, q: '', index: null };
const _GV_STORE = 'pv_guide_v1';
const _GV_GO = {
  games: () => switchPage('arena'), rhythm: () => openRhythmV2Game(), mines: () => openMinesweeperGame(), rating: () => _gvRating(),
  pass: () => { location.href = BASE + '/league#pass'; }, profile: () => switchPage('profile'), pets: () => openPetsV1(), quests: () => openQuestsV1(),
  looks: () => openLooksModal(), chests: () => openChestsV1(), inventory: () => openInventory(), top: () => openTopV3(), wallet: () => showCurrModal(),
  more: () => switchPage('more'), vip: () => openStoreV3('vip'), zarniki: () => openStoreV3('zarniki'), promo: () => openPromoSheet(),
  achievements: () => openAchievementsV1(), market: () => openPlayerExchangeV1(), casino: () => openCasino(),
};
const _gvRating = () => { if (typeof _league !== 'undefined' && _league && _league.allowed) location.href = BASE + '/league?game=rhythm'; else openRhythmV2Game(); };
const _gvNorm = s => String(s || '').toLowerCase().replace(/ё/g, 'е').replace(/[^a-zа-я0-9 ]+/g, ' ');
const _gvStem = w => w.length >= 7 ? w.slice(0, 5) : w.length >= 5 ? w.slice(0, w.length - 2) : w.length >= 4 ? w.slice(0, w.length - 1) : w;
const _gvWords = s => _gvNorm(s).split(/\s+/).filter(w => w.length > 2);
const _gvText = b => [b.h, b.text, ...(b.items || []).flatMap(i => [i.h, i.p, i.w, i.plus, i.minus]), ...(b.a ? [b.a.h, ...b.a.items] : []), ...(b.b ? [b.b.h, ...b.b.items] : [])].filter(Boolean).join(' ');

function gvLoad() {
  if (_GV.data) return Promise.resolve(_GV.data);
  if (_GV.pending) return _GV.pending;
  _GV.pending = fetch(BASE + '/guide-v3.json', { cache: 'no-cache' }).then(r => { if (!r.ok) throw new Error('guide'); return r.json(); })
    .then(d => { try { localStorage.setItem(_GV_STORE, JSON.stringify(d)); } catch (_) {} return d; })
    .catch(() => { try { const d = JSON.parse(localStorage.getItem(_GV_STORE)); if (d && d.topics) return d; } catch (_) {} throw new Error('guide'); })
    .then(d => { _GV.data = d; _GV.index = null; return d; })
    .finally(() => { _GV.pending = null; });
  return _GV.pending;
}
function _gvIndex() {
  if (_GV.index) return _GV.index;
  const d = _GV.data, parts = [];
  d.topics.forEach(t => parts.push({ kind: 'topic', id: t.id, w: 5, text: t.title }, { kind: 'topic', id: t.id, w: 4, text: (t.kw || []).join(' ') }, { kind: 'topic', id: t.id, w: 3, text: t.lead },
    { kind: 'topic', id: t.id, w: 1, text: t.blocks.map(_gvText).join(' ') }));
  d.glossary.forEach((g, i) => parts.push({ kind: 'term', id: i, w: 6, text: g.w }, { kind: 'term', id: i, w: 2, text: g.p }));
  d.faq.forEach((f, i) => parts.push({ kind: 'faq', id: i, w: 5, text: f.q }, { kind: 'faq', id: i, w: 2, text: f.a }));
  return (_GV.index = parts.map(p => ({ ...p, words: _gvWords(p.text) })));
}
function gvFind(q) {
  const need = _gvWords(q).map(_gvStem); if (!need.length) return [];
  const hits = new Map();
  for (const p of _gvIndex()) {
    const key = p.kind + ':' + p.id, row = hits.get(key) || { kind: p.kind, id: p.id, score: 0, got: new Set() };
    need.forEach(n => { if (p.words.some(w => w.startsWith(n))) { row.score += p.w; row.got.add(n); } });
    hits.set(key, row);
  }
  const all = [...hits.values()].filter(r => r.got.size === need.length);
  const rows = all.length ? all : [...hits.values()].filter(r => r.got.size > 0 && r.got.size * 2 >= need.length);
  return rows.sort((a, b) => b.score - a.score).slice(0, 12);
}

function _gvRow(t) {
  return `<button type="button" class="gv-row" onclick="gvOpen('${esc(t.id)}')"><span class="gv-ic" aria-hidden="true">${esc(t.icon)}</span><span class="gv-tx"><b>${esc(t.title)}</b><small>${esc(t.lead)}</small></span><i class="gv-chev" aria-hidden="true"></i></button>`;
}
function _gvAnswer(f, i) {
  return `<article class="gv-card"><b>${esc(f.q)}</b><p>${esc(f.a)}</p><button type="button" class="v3-link" onclick="gvOpen('${esc(f.t)}')">Читать тему ›</button></article>`;
}
function _gvResults(q) {
  const d = _GV.data, rows = gvFind(q);
  if (!rows.length) return `<div class="v3-empty"><b>Ничего не нашлось</b><span>Попробуй другое слово или открой <button type="button" class="v3-link" onclick="gvView('terms')">Словарь</button>.</span></div>`;
  return rows.map(r => r.kind === 'topic' ? _gvRow(d.topics.find(t => t.id === r.id))
    : r.kind === 'faq' ? _gvAnswer(d.faq[r.id], r.id)
    : `<article class="gv-card"><b>${esc(d.glossary[r.id].w)}</b><p>${esc(d.glossary[r.id].p)}</p><button type="button" class="v3-link" onclick="gvOpen('${esc(d.glossary[r.id].t)}')">Читать тему ›</button></article>`).join('');
}
function gvSearch(input) {
  _GV.q = input.value.trim();
  const out = el('gv-results'), home = el('gv-home'); if (!out || !home) return;
  out.hidden = !_GV.q; home.hidden = !!_GV.q;
  out.innerHTML = _GV.q ? _gvResults(_GV.q) : '';
}

function _gvHub(d) {
  const quick = d.faq.slice(0, 6).map((f, i) => `<button type="button" class="gv-chip" onclick="gvOpenFaq(${i})">${esc(f.q)}</button>`).join('');
  const groups = d.groups.map(g => `<section class="v3-group gv-group"><span class="v3-eyebrow">${esc(g.icon)} ${esc(g.title)}</span><p class="gv-sub">${esc(g.sub)}</p>${g.topics.map(id => _gvRow(d.topics.find(t => t.id === id))).join('')}</section>`).join('');
  return `${v3Head('Путеводитель', { sub: 'Всё об игре: найди нужное или читай по порядку' })}
    <div class="gv-search"><input id="gv-q" class="v3-field" type="search" placeholder="Что ищешь? Например: мора" value="${esc(_GV.q)}" oninput="gvSearch(this)" autocomplete="off" enterkeyhint="search" aria-label="Поиск по Путеводителю"></div>
    <div id="gv-results" hidden aria-live="polite"></div>
    <div id="gv-home"><div class="gv-cta"><button type="button" class="v3-pill" onclick="gvOpen('${esc(d.topics[0].id)}')">Читать по порядку ›</button><button type="button" class="v3-pill v3-pill--ghost" onclick="gvView('terms')">Словарь</button><button type="button" class="v3-pill v3-pill--ghost" onclick="gvView('faq')">Все вопросы</button></div>
      <span class="v3-eyebrow gv-eb">Быстрые ответы</span><div class="gv-chips">${quick}</div>${groups}</div>`;
}
function _gvTerms(d) {
  const rows = d.glossary.map(g => `<div class="gv-term"><dt>${esc(g.w)}</dt><dd>${esc(g.p)} <button type="button" class="v3-link" onclick="gvOpen('${esc(g.t)}')">Тема ›</button></dd></div>`).join('');
  return `${v3Head('Словарь', { sub: `${d.glossary.length} слов из игры — по алфавиту`, back: 'gvBack()' })}<dl class="gv-terms">${rows}</dl>`;
}
function _gvFaq(d) {
  const rows = d.faq.map((f, i) => `<details class="gv-q" id="gv-q-${i}"${i === _GV.faq ? ' open' : ''}><summary>${esc(f.q)}</summary><p>${esc(f.a)}</p><button type="button" class="v3-link" onclick="gvOpen('${esc(f.t)}')">Читать тему ›</button></details>`).join('');
  return `${v3Head('Частые вопросы', { sub: 'Нажми на вопрос — ответ раскроется', back: 'gvBack()' })}<div class="gv-qs">${rows}</div>`;
}

const _gvHead = b => b.h ? `<h2 class="gv-h">${esc(b.h)}</h2>` : '';
const _gvItems = (b, cls) => `<ul class="gv-gives${cls}">${b.items.map(i => `<li><span class="gv-gi" aria-hidden="true">${esc(i.i)}</span><b>${esc(i.h)}</b><span>${esc(i.p)}</span></li>`).join('')}</ul>`;
const _gvKind = { safe: 'Надёжный', boost: 'Усиление', risk: 'Риск' };
const _GV_BLOCK = {
  what: b => `<p class="gv-what">${esc(b.text)}</p>`,
  steps: b => `<section class="gv-sec">${_gvHead(b)}<ol class="gv-steps">${b.items.map(i => `<li><b>${esc(i.h)}</b><span>${esc(i.p)}</span></li>`).join('')}</ol></section>`,
  gives: b => `<section class="gv-sec">${_gvHead(b)}${_gvItems(b, '')}</section>`,
  list: b => `<section class="gv-sec">${_gvHead(b)}${_gvItems(b, ' is-compact')}</section>`,
  words: b => `<section class="gv-sec">${_gvHead(b)}<dl class="gv-words">${b.items.map(i => `<div><dt>${esc(i.w)}</dt><dd>${esc(i.p)}</dd></div>`).join('')}</dl></section>`,
  tip: b => `<aside class="gv-note gv-tip"><b>Совет</b><p>${esc(b.text)}</p></aside>`,
  warn: b => `<aside class="gv-note gv-warn" role="note"><b>Осторожно</b><p>${esc(b.text)}</p></aside>`,
  pair: b => `<div class="gv-pair">${[b.a, b.b].map(s => `<section class="gv-card"><b>${esc(s.h)}</b><ul>${s.items.map(x => `<li>${esc(x)}</li>`).join('')}</ul></section>`).join('')}</div>`,
  gifts: b => `<section class="gv-sec">${_gvHead(b)}<ul class="gv-gifts">${b.items.map(i => `<li class="is-${esc(i.k)}"><small>${esc(_gvKind[i.k] || '')}${i.twice ? ' · можно взять дважды' : ''}${i.rare ? ' · редко' : ''}</small><b>${esc(i.w)}</b><span class="gv-plus">＋ ${esc(i.plus)}</span><span class="gv-minus">− ${esc(i.minus)}</span></li>`).join('')}</ul></section>`,
};
function _gvWhere(w) {
  if (!w) return '';
  const go = w.go && _GV_GO[w.go] ? `<button type="button" class="v3-pill v3-pill--sm" onclick="gvGo('${esc(w.go)}')">${esc(w.label)}</button>` : '';
  return `<section class="gv-where"><div><small>Где найти</small><b>${esc(w.path)}</b></div>${go}</section>`;
}
function _gvTopic(d, t) {
  const at = d.topics.indexOf(t), prev = d.topics[at - 1], next = d.topics[at + 1], group = d.groups.find(g => g.topics.includes(t.id));
  const more = (t.next || []).map(id => d.topics.find(x => x.id === id)).filter(Boolean).map(_gvRow).join('');
  const pager = `<nav class="gv-pager" aria-label="Соседние темы">${prev ? `<button type="button" class="v3-pill v3-pill--ghost" onclick="gvOpen('${esc(prev.id)}')">‹ ${esc(prev.title)}</button>` : '<span></span>'}${next ? `<button type="button" class="v3-pill" onclick="gvOpen('${esc(next.id)}')">${esc(next.title)} ›</button>` : ''}</nav>`;
  return `${v3Head(t.title, { sub: `Тема ${at + 1} из ${d.topics.length} · ${group ? group.title : ''}`, back: 'gvBack()' })}
    <p class="gv-lead"><span class="gv-bigic" aria-hidden="true">${esc(t.icon)}</span>${esc(t.lead)}</p>${t.blocks.map(b => (_GV_BLOCK[b.t] || (() => ''))(b)).join('')}${_gvWhere(t.where)}
    ${more ? `<span class="v3-eyebrow gv-eb">Читай дальше</span>${more}` : ''}${pager}`;
}

function gvPaint() {
  const root = el('pg-help'), d = _GV.data; if (!root || !d) return;
  const t = _GV.view === 'topic' && d.topics.find(x => x.id === _GV.topic);
  root.innerHTML = `<div class="gv-scope">${t ? _gvTopic(d, t) : _GV.view === 'terms' ? _gvTerms(d) : _GV.view === 'faq' ? _gvFaq(d) : _gvHub(d)}</div>`;
  if (_GV.view === 'hub' && _GV.q) gvSearch(el('gv-q'));
  v3EnterSync(root.firstElementChild);
  const open = _GV.view === 'faq' && _GV.faq >= 0 ? el('gv-q-' + _GV.faq) : null;
  if (open) open.scrollIntoView({ block: 'center' }); else window.scrollTo(0, 0);
}
function gvView(view, topic = '') { _haptic('select'); _GV.view = view; _GV.topic = topic; if (view !== 'faq') _GV.faq = -1; gvPaint(); }
function gvOpen(id) { gvView('topic', id); }
function gvOpenFaq(i) { _GV.faq = i; _haptic('select'); _GV.view = 'faq'; gvPaint(); }
function gvBack() { if (_GV.view === 'hub') return false; gvView('hub'); return true; }
function gvGo(key) { _haptic('select'); if (_GV_GO[key]) _GV_GO[key](); }
function gvShow() {
  const root = el('pg-help'); if (!root) return Promise.resolve();
  if (!_GV.data) root.innerHTML = `<div class="gv-scope">${v3Head('Путеводитель', { sub: 'Загружаем…' })}<div class="sk" style="height:48px;border-radius:12px"></div><div class="sk" style="height:220px;border-radius:18px;margin-top:18px"></div></div>`;
  return gvLoad().then(gvPaint).catch(() => { root.innerHTML = `<div class="gv-scope">${v3Head('Путеводитель')}<div class="v3-empty" role="alert"><b>Путеводитель не открылся</b><span>Проверь связь.</span> <button type="button" class="v3-link" onclick="gvShow()">Повторить</button></div></div>`; });
}
// Открыть тему из любого места приложения: подсказки, «Что нового», ссылка из бота (?startapp=guide_<id>)
function openGuide(id) {
  if (_activePage !== 'help') switchPage('help');
  if (id) { _GV.view = 'topic'; _GV.topic = id; } else { _GV.view = 'hub'; _GV.topic = ''; }
  return gvShow();
}
_backHooks.push(() => _activePage === 'help' && gvBack());
