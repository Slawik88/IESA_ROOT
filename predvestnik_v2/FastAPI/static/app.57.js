// ── «Путеводитель» (вкладка «Ещё» › «Путеводитель», #pg-help): темы, словарь и быстрые ответы из guide-v3.json ─────────────
// Все тексты — в данных (FastAPI/static/guide-v3.json), здесь только показ: главная с поиском и группами, тема из блоков
// (что это · шаги · что даёт · слова · совет · где найти), «Читать по порядку», словарь и частые вопросы. Правила текстов — docs/PLAYER_COPY.md.
// Ссылка на тему: ?startapp=guide_<id> или guide_<id>_<номер блока> (app.02.js), из подсказок и игр — openGuide('<id>'). Стили: guide-v3.css (префикс gv-).
// Тема, открытая с другого экрана (💡, профиль, ссылка), помнит это: «Назад» сразу возвращает туда, а не на главную Путеводителя (_GV.ext).
const _GV = { data: null, pending: null, view: 'hub', topic: '', faq: -1, q: '', index: null, vocab: null, history: [], offline: false, ext: false, origin: null, block: 0, missTimer: 0, missSent: new Set() };
const _GV_STORE = 'pv_guide_v1';
const _GV_LAST = 'pv_guide_last';
const _GV_STOP = new Set(['как', 'где', 'что', 'это', 'для', 'мне', 'меня', 'мой', 'мои', 'моя', 'мою', 'его', 'или', 'такое', 'такой', 'почему', 'взять', 'найти', 'получить', 'дают', 'даются', 'видно', 'хочу', 'могу', 'ли', 'если', 'делать']);
// Как игроки называют вещи в чате → слово из тем. Добавляй сюда, когда «Здоровье» показывает частый запрос без ответа (guide_miss).
const _GV_ALIAS = { бп: 'пропуск', bp: 'пропуск', батлпас: 'пропуск', баттлпас: 'пропуск', пасс: 'пропуск', xp: 'опыт', хп: 'сердца', exp: 'опыт', экспа: 'опыт', лвл: 'уровень', lvl: 'уровень',
  вип: 'vip', еду: 'еда', еды: 'еда', едой: 'еда', пет: 'питомец', пета: 'питомец', петы: 'питомцы', петов: 'питомцы', кейс: 'сундук', кейсы: 'сундуки', лутбокс: 'сундук',
  донат: 'зарники', задонатить: 'зарники', гемы: 'алмазы', кристаллы: 'алмазы', деньги: 'мора', бабки: 'мора', ачивка: 'достижения', ачивки: 'достижения',
  промик: 'промокод', промо: 'промокод', рулетка: 'казино', мафа: 'мафия', скины: 'образы', квест: 'задание', квесты: 'задания', дейлики: 'задания', крипта: 'биржа', рейт: 'рейтинг' };
// Набранное в английской раскладке: «vjhf» → «мора»
const _GV_KEYS = { q: 'й', w: 'ц', e: 'у', r: 'к', t: 'е', y: 'н', u: 'г', i: 'ш', o: 'щ', p: 'з', '[': 'х', ']': 'ъ', a: 'ф', s: 'ы', d: 'в', f: 'а', g: 'п', h: 'р', j: 'о', k: 'л', l: 'д', ';': 'ж', "'": 'э',
  z: 'я', x: 'ч', c: 'с', v: 'м', b: 'и', n: 'т', m: 'ь', ',': 'б', '.': 'ю', '`': 'ё' };
const _GV_GO = {
  games: () => switchPage('arena'), rhythm: () => _gvLeave('/rhythm-v2', 'Ритм'), mines: () => _gvLeave('/minesweeper', 'Сапёр'), rating: () => _gvRating(),
  pass: () => _gvLeave('/league#pass', 'Пропуск сезона'), profile: () => switchPage('profile'), pets: () => openPetsV1(), quests: () => openQuestsV1(),
  looks: () => openLooksModal(), chests: () => openChestsV1(), inventory: () => openInventory(), top: () => openTopV3(), wallet: () => showCurrModal(),
  more: () => switchPage('more'), vip: () => openStoreV3('vip'), zarniki: () => openStoreV3('zarniki'), promo: () => openPromoSheet(),
  achievements: () => openAchievementsV1(), market: () => openPlayerExchangeV1(), casino: () => openCasino(),
};
// Игры живут на своих страницах: показываем «Открываем…», а «‹» в игре вернёт в эту же тему (pv_back читает game-shell-v3.html).
function _gvLeave(path, what) {
  try { if (_GV.view === 'topic' && _GV.topic) sessionStorage.setItem('pv_back', 'guide_' + _GV.topic); } catch (_) {}
  const root = el('pg-help');
  if (root) root.innerHTML = `<div class="gv-scope">${v3Head(what, { sub: 'Открываем…' })}<div class="sk" style="height:220px;border-radius:18px"></div><p class="gv-sub">Кнопка «‹» в игре вернёт тебя в эту тему Путеводителя.</p></div>`;
  location.href = BASE + path;
}
const _gvRating = () => _gvLeave('/league?game=rhythm', 'Рейтинг');
const _gvNorm = s => String(s || '').toLowerCase().replace(/ё/g, 'е').replace(/[^a-zа-я0-9 ]+/g, ' ');
const _gvStem = w => w.length >= 7 ? w.slice(0, 5) : w.length >= 5 ? w.slice(0, w.length - 2) : w.length >= 4 ? w.slice(0, w.length - 1) : w;
const _gvWords = s => _gvNorm(s).split(/\s+/).flatMap(w => (_GV_ALIAS[w] || (/^скин/.test(w) ? 'образ' : /^корм/.test(w) ? 'еда' : w)).split(' ')).filter(w => w.length > 2 && !_GV_STOP.has(w));
const _gvText = b => [b.h, b.text, ...(b.items || []).flatMap(i => [i.h, i.p, i.w, i.plus, i.minus]), ...(b.a ? [b.a.h, ...b.a.items] : []), ...(b.b ? [b.b.h, ...b.b.items] : [])].filter(Boolean).join(' ');
function _gvValid(d) {
  if (!d || d.version !== 1 || !['topics', 'groups', 'glossary', 'faq'].every(k => Array.isArray(d[k])) || !d.topics.length) return false;
  const strings = (row, keys) => row && keys.every(k => typeof row[k] === 'string');
  const ids = new Set(d.topics.map(t => t?.id));
  const block = b => {
    if (!b) return false;
    if (['what', 'tip', 'warn'].includes(b.t)) return strings(b, ['text']);
    if (b.t === 'pair') return [b.a, b.b].every(s => strings(s, ['h']) && Array.isArray(s.items) && s.items.every(i => typeof i === 'string'));
    const fields = { steps: ['h', 'p'], gives: ['i', 'h', 'p'], list: ['i', 'h', 'p'], words: ['w', 'p'], gifts: ['w', 'k', 'plus', 'minus'] }[b.t];
    return !!fields && Array.isArray(b.items) && b.items.every(i => strings(i, fields));
  };
  return ids.size === d.topics.length && d.topics.every(t => strings(t, ['id', 'title', 'lead', 'icon']) && /^[a-z]+(-[a-z]+)*$/.test(t.id)
    && Array.isArray(t.blocks) && t.blocks.every(block) && strings(t.where, ['path', 'label'])
    && (!t.kw || Array.isArray(t.kw) && t.kw.every(w => typeof w === 'string'))
    && (!t.where.go || Object.hasOwn(_GV_GO, t.where.go)) && (!t.next || Array.isArray(t.next) && t.next.every(id => ids.has(id))))
    && d.groups.every(g => strings(g, ['id', 'title', 'icon', 'sub']) && /^[a-z]+$/.test(g.id) && Array.isArray(g.topics) && g.topics.every(id => ids.has(id)))
    && d.glossary.every(g => strings(g, ['w', 'p', 't']) && ids.has(g.t)) && d.faq.every(f => strings(f, ['q', 'a', 't']) && ids.has(f.t));
}
const _gvPosition = () => ({ view: _GV.view, topic: _GV.topic, faq: _GV.faq, q: _GV.q, scroll: window.scrollY,
  filter: el('gv-filter')?.value || '', focus: document.activeElement?.getAttribute('data-gv-key') || '',
  open: [...document.querySelectorAll('.gv-scope details[open]')].map(row => row.id).filter(Boolean) });
const _gvGroupOf = id => _GV.data?.groups.find(g => g.topics.includes(id));
// Где ты: «Путеводитель › Группа» над темой (сама тема — заголовок экрана); каждое звено ведёт туда. Поиск по всем темам есть на каждой странице Путеводителя.
function _gvCrumbs(t) {
  const group = t && _gvGroupOf(t.id);
  const link = (label, act, key) => `<button type="button" class="gv-crumb" data-gv-key="${key}" onclick="${act}">${esc(label)}</button>`;
  const tail = group ? `<i aria-hidden="true">›</i>${link(group.title, `gvGroup('${esc(group.id)}')`, 'crumb-group')}` : '';
  return `<nav class="gv-crumbs" aria-label="Где ты в Путеводителе">${link('Путеводитель', 'gvHome()', 'crumb-home')}${tail}</nav>`;
}
const _gvSearchBox = (handler, value = '') => `<div class="gv-search"><input id="gv-q" class="v3-field" type="search" placeholder="Что ищешь? Например: мора" value="${esc(value)}" oninput="${handler}(this)" autocomplete="off" enterkeyhint="search" aria-label="Поиск по Путеводителю"></div>`;
const _gvHubButton = t => `${_gvCrumbs(t)}${_gvSearchBox('gvSearchFrom')}${_GV.view === 'topic' ? '<nav class="gv-tools"><button type="button" class="v3-link gv-all" data-gv-key="dictionary" onclick="gvView(\'terms\')">Словарь</button></nav>' : ''}`;

function gvLoad() {
  if (_GV.data) return Promise.resolve(_GV.data);
  if (_GV.pending) return _GV.pending;
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 8000);
  _GV.pending = fetch(BASE + '/guide-v3.json', { cache: 'no-cache', signal: controller.signal }).then(r => { if (!r.ok) throw new Error('guide'); return r.json(); })
    .then(d => { if (!_gvValid(d)) throw new Error('guide'); _GV.offline = false; try { localStorage.setItem(_GV_STORE, JSON.stringify(d)); } catch (_) {} return d; })
    .catch(() => { try { const d = JSON.parse(localStorage.getItem(_GV_STORE)); if (_gvValid(d)) { _GV.offline = true; return d; } } catch (_) {} throw new Error('guide'); })
    .then(d => { _GV.data = d; _GV.index = null; _GV.vocab = null; return d; })
    .finally(() => { clearTimeout(timer); _GV.pending = null; });
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
  const need = [...new Set(_gvWords(q).map(_gvStem))]; if (!need.length) return [];
  const hits = new Map();
  for (const p of _gvIndex()) {
    const key = p.kind + ':' + p.id, row = hits.get(key) || { kind: p.kind, id: p.id, score: 0, got: new Set() };
    need.forEach(n => { if (p.words.some(w => w.startsWith(n))) { row.score += p.w; row.got.add(n); } });
    hits.set(key, row);
  }
  const rows = [...hits.values()].filter(r => r.got.size === need.length);
  return rows.sort((a, b) => b.score - a.score).slice(0, 12);
}
// Расстояние «одна опечатка»: замена, лишняя, пропущенная или переставленная буква (Дамерау — Левенштейн, с отсечкой).
function _gvDist(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev2 = [], prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const row = [i]; let best = i;
    for (let j = 1; j <= b.length; j++) {
      row[j] = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) row[j] = Math.min(row[j], prev2[j - 2] + 1);
      best = Math.min(best, row[j]);
    }
    if (best > max) return max + 1;
    prev2 = prev; prev = row;
  }
  return prev[b.length];
}
function _gvVocab() {
  if (!_GV.vocab) { const count = new Map(); _gvIndex().forEach(p => p.words.forEach(w => count.set(w, (count.get(w) || 0) + p.w))); _GV.vocab = count; }
  return _GV.vocab;
}
// Запрос с исправленными опечатками или раскладкой: «питмоец» → «питомец», «vjhf» → «мора». Пусто — исправлять нечего.
function gvSuggest(q) {
  const raw = _gvNorm(String(q || '').toLowerCase().replace(/[a-z\[\];',.`]/g, c => _GV_KEYS[c] || c));
  const vocab = _gvVocab(), known = w => [...vocab.keys()].some(v => v.startsWith(_gvStem(w)));
  const fix = (/[a-z]/.test(_gvNorm(q)) && raw !== _gvNorm(q) ? raw : _gvNorm(q)).split(/\s+/).filter(Boolean).map(w => {
    if (w.length < 4 || _GV_STOP.has(w) || _GV_ALIAS[w] || known(w)) return w;
    const max = w.length >= 7 ? 2 : 1;
    let best = '', bestD = max + 1, bestW = 0;
    for (const [v, weight] of vocab) {
      if (v.length < 4) continue;
      const d = Math.min(_gvDist(w, v, max), v.length > w.length ? _gvDist(w, v.slice(0, w.length), max) : max + 1);
      if (d <= max && (d < bestD || d === bestD && weight > bestW)) { best = v; bestD = d; bestW = weight; }
    }
    return best || w;
  }).join(' ');
  return fix !== _gvNorm(q).trim() && gvFind(fix).length ? fix : '';
}
// Три ближайшие темы, когда ничего не нашлось: совпало хоть одно слово, иначе — с чего начать.
function gvNear(q) {
  const need = [...new Set(_gvWords(q).map(_gvStem))], score = new Map();
  for (const p of _gvIndex()) if (p.kind === 'topic') need.forEach(n => { if (p.words.some(w => w.startsWith(n))) score.set(p.id, (score.get(p.id) || 0) + p.w); });
  const ids = [...score.entries()].sort((a, b) => b[1] - a[1]).map(([id]) => id);
  for (const id of ['first-day', 'map', 'welcome']) if (!ids.includes(id)) ids.push(id);
  return ids.slice(0, 3);
}
// Запрос без ответа — анонимно в «Здоровье» админки (S01, тип guide_miss): так видно, каких тем не хватает. Один раз на запрос, после паузы в наборе.
function _gvMiss(q) {
  clearTimeout(_GV.missTimer);
  const text = _gvNorm(q).replace(/\s+/g, ' ').trim().slice(0, 60);
  if (text.length < 3 || _GV.missSent.has(text) || _GV.missSent.size >= 3) return;   // не больше трёх на открытие: общий лимит телеметрии нужен ошибкам
  _GV.missTimer = setTimeout(() => {
    if (_GV.q && _gvNorm(_GV.q).replace(/\s+/g, ' ').trim().slice(0, 60) !== text) return;
    _GV.missSent.add(text);
    try { window.PVDiagnostics?.telemetry?.('guide_miss', { message: text }); } catch (_) {}
  }, 1500);
}

function _gvRow(t) {
  return `<button type="button" class="gv-row" data-gv-key="topic-${esc(t.id)}" onclick="gvOpen('${esc(t.id)}')"><span class="gv-ic" aria-hidden="true">${esc(t.icon)}</span><span class="gv-tx"><b>${esc(t.title)}</b><small>${esc(t.lead)}</small></span><i class="gv-chev" aria-hidden="true"></i></button>`;
}
function _gvAnswer(f, i) {
  return `<article class="gv-card"><b>${esc(f.q)}</b><p>${esc(f.a)}</p><button type="button" class="v3-link" data-gv-key="answer-${i}" onclick="gvOpen('${esc(f.t)}')">Читать тему ›</button></article>`;
}
function _gvResults(q) {
  const d = _GV.data, exact = gvFind(q), fixed = exact.length ? '' : gvSuggest(q), rows = exact.length ? exact : fixed ? gvFind(fixed) : [];
  if (!rows.length) {
    _gvMiss(q);
    const near = gvNear(q).map(id => d.topics.find(t => t.id === id)).filter(Boolean).map(_gvRow).join('');
    return `<div class="v3-empty"><b>Точного ответа нет</b><span>Попробуй коротко: «опыт», «ключи», «питомец» или «VIP». Или загляни в близкие темы:</span></div><div class="gv-near">${near}</div><nav class="gv-tools"><button type="button" class="v3-link" onclick="gvClear()">Показать все темы</button><button type="button" class="v3-link" onclick="gvView('terms')">Открыть словарь</button></nav>`;
  }
  const head = fixed ? `<p class="gv-sub gv-fixed" role="status">Похоже на опечатку — показываю «${esc(fixed)}»</p>` : '';
  return head + `<p class="gv-sub">Подходящие темы и ответы · ${rows.length}</p>` + rows.map(r => r.kind === 'topic' ? _gvRow(d.topics.find(t => t.id === r.id))
    : r.kind === 'faq' ? _gvAnswer(d.faq[r.id], r.id)
    : `<article class="gv-card"><b>${esc(d.glossary[r.id].w)}</b><p>${esc(d.glossary[r.id].p)}</p><button type="button" class="v3-link" data-gv-key="result-term-${r.id}" onclick="gvOpen('${esc(d.glossary[r.id].t)}')">Читать тему ›</button></article>`).join('');
}
function gvSearch(input) {
  if (!input) return;
  _GV.q = input.value.trim();
  const out = el('gv-results'), home = el('gv-home'); if (!out || !home) return;
  out.hidden = !_GV.q; home.hidden = !!_GV.q;
  out.innerHTML = _GV.q ? _gvResults(_GV.q) : '';
  // Поиск доступен и внизу списка: первые результаты должны оказаться перед глазами.
  if (window.scrollY > 0) window.scrollTo({ top: 0, behavior: 'instant' });
}

// Быстрые ответы по смыслу: первый вопрос из каждого раздела, а не первые шесть подряд.
function _gvQuick(d) {
  return d.groups.map(g => d.faq.findIndex(f => g.topics.includes(f.t))).filter(i => i >= 0);
}
function _gvHub(d) {
  let last; try { last = d.topics.find(t => t.id === localStorage.getItem(_GV_LAST)); } catch (_) {}
  const resume = last ? `<button type="button" class="gv-resume" onclick="gvOpen('${esc(last.id)}')"><small>Продолжить чтение · тема ${d.topics.indexOf(last) + 1} из ${d.topics.length}</small><b>${esc(last.title)} ›</b></button>` : '';
  const quick = _gvQuick(d).map(i => `<button type="button" class="gv-chip" onclick="gvOpenFaq(${i})">${esc(d.faq[i].q)}</button>`).join('');
  const sections = `<nav class="gv-sections" aria-label="Разделы Путеводителя">${d.groups.map(g => `<button type="button" class="gv-chip" onclick="gvGroup('${esc(g.id)}')">${esc(g.title)}</button>`).join('')}</nav>`;
  // Группы свёрнуты, кроме «Начни отсюда» и той, где последняя прочитанная тема: 32 темы не растягиваются на три экрана.
  const lastGroup = last && _gvGroupOf(last.id);
  const groups = d.groups.map((g, i) => `<details class="v3-group gv-group" id="gv-group-${esc(g.id)}"${i === 0 || g === lastGroup ? ' open' : ''}><summary><h2 class="v3-eyebrow">${esc(g.icon)} ${esc(g.title)}</h2><p class="gv-sub">${esc(g.sub)} · ${g.topics.length}</p></summary>${g.topics.map(id => _gvRow(d.topics.find(t => t.id === id))).join('')}</details>`).join('');
  return `${v3Head('Путеводитель', { sub: 'Всё об игре: найди нужное или читай по порядку', back: 'navBack()' })}
    ${_gvSearchBox('gvSearch', _GV.q)}
    <div id="gv-results" hidden aria-live="polite"></div>
    <div id="gv-home">${resume}<div class="gv-cta"><button type="button" class="v3-pill" onclick="gvOpen('${esc(d.topics[0].id)}')">Читать по порядку ›</button><button type="button" class="v3-pill v3-pill--ghost" onclick="gvView('terms')">Словарь</button><button type="button" class="v3-pill v3-pill--ghost" onclick="gvView('faq')">Все вопросы</button></div>
      <h2 class="v3-eyebrow gv-eb">Выбери раздел</h2>${sections}<h2 class="v3-eyebrow gv-eb">Быстрые ответы</h2><div class="gv-chips">${quick}</div>${groups}</div>`;
}
function _gvTerms(d) {
  const rows = d.glossary.map((g, i) => `<div class="gv-term"><dt>${esc(g.w)}</dt><dd>${esc(g.p)} <button type="button" class="v3-link" data-gv-key="term-${i}" onclick="gvOpen('${esc(g.t)}')">Тема ›</button></dd></div>`).join('');
  return `${v3Head('Словарь', { sub: `${d.glossary.length} слов из игры — по алфавиту`, back: 'navBack()' })}${_gvHubButton()}<label class="gv-filter">Найти слово<input id="gv-filter" class="v3-field" type="search" oninput="gvFilter(this, 'term')" placeholder="Например: Следы"></label><dl class="gv-terms">${rows}</dl><p id="gv-filter-empty" hidden>Такого слова нет. Попробуй поиск по всем темам.</p>`;
}
function _gvFaq(d) {
  const row = i => { const f = d.faq[i]; return `<details class="gv-q" id="gv-q-${i}"${i === _GV.faq ? ' open' : ''}><summary>${esc(f.q)}</summary><p>${esc(f.a)}</p><button type="button" class="v3-link" data-gv-key="faq-${i}" onclick="gvOpen('${esc(f.t)}')">Читать тему ›</button></details>`; };
  // По разделам Путеводителя: вопрос про ключи рядом с вопросами про деньги, а не в общем списке из 42.
  const rows = d.groups.map(g => { const own = d.faq.map((f, i) => g.topics.includes(f.t) ? i : -1).filter(i => i >= 0);
    return own.length ? `<section class="gv-qcat"><h2 class="v3-eyebrow gv-eb">${esc(g.icon)} ${esc(g.title)}</h2>${own.map(row).join('')}</section>` : ''; }).join('');
  return `${v3Head('Частые вопросы', { sub: 'Нажми на вопрос — ответ раскроется', back: 'navBack()' })}${_gvHubButton()}<label class="gv-filter">Найти вопрос<input id="gv-filter" class="v3-field" type="search" oninput="gvFilter(this, 'q')" placeholder="Например: награда"></label><div class="gv-qs">${rows}</div><p id="gv-filter-empty" hidden>Такого вопроса нет. Попробуй поиск по всем темам.</p>`;
}
function gvFilter(input, kind) {
  const words = _gvWords(input.value).map(_gvStem), rows = el('pg-help').querySelectorAll('.gv-' + kind);
  let visible = 0;
  rows.forEach(row => { const text = _gvWords(row.textContent); row.hidden = !words.every(w => text.some(t => t.startsWith(w))); if (!row.hidden) visible++; });
  el('pg-help').querySelectorAll('.gv-qcat').forEach(cat => { cat.hidden = !cat.querySelector('.gv-q:not([hidden])'); });
  el('gv-filter-empty').hidden = visible > 0;
}
function gvJump(id) { const target = el(id); if (target) { if (target.tagName === 'DETAILS') target.open = true; target.scrollIntoView({ block: 'start' }); target.tabIndex = -1; target.focus({ preventScroll: true }); } }
// Звено «Группа» в крошках и кнопки разделов: главная Путеводителя, нужная группа раскрыта и перед глазами
function gvGroup(id) {
  if (_GV.view !== 'hub') { _GV.history.push(_gvPosition()); _GV.view = 'hub'; _GV.topic = ''; _GV.faq = -1; _GV.q = ''; gvPaint(); }
  else if (_GV.q) gvClear();
  gvJump('gv-group-' + id);
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
  gifts: b => `<details class="gv-gift-list" id="gv-gift-list"><summary>${esc(b.h)} · ${b.items.length} — раскрыть</summary><ul class="gv-gifts">${b.items.map(i => `<li class="is-${esc(i.k)}"><small>${esc(_gvKind[i.k] || '')}${i.twice ? ' · можно взять дважды' : ''}${i.rare ? ' · редко' : ''}</small><b>${esc(i.w)}</b><span class="gv-plus">＋ ${esc(i.plus)}</span><span class="gv-minus">− ${esc(i.minus)}</span></li>`).join('')}</ul></details>`,
};
function _gvWhere(w) {
  if (!w) return '';
  const go = w.go && _GV_GO[w.go] ? `<button type="button" class="v3-pill v3-pill--sm" onclick="gvGo('${esc(w.go)}')">${esc(w.label)}</button>` : '';
  return `<section class="gv-where"><div><small>Где найти</small><b>${esc(w.path)}</b></div>${go}</section>`;
}
// Оглавление длинной темы: блоки с заголовком (от трёх). Номер блока — тот же, что в ссылке guide_<тема>_<номер>.
function _gvToc(t) {
  const marks = t.blocks.map((b, i) => [b.h, i + 1]).filter(([h]) => h);
  if (marks.length < 3) return '';
  return `<details class="gv-toc"><summary>Содержание · ${marks.length}</summary><ol>${marks.map(([h, n]) => `<li><button type="button" class="v3-link" data-gv-key="toc-${n}" onclick="gvBlock(${n})">${esc(h)}</button></li>`).join('')}</ol></details>`;
}
function gvBlock(n) {
  const target = el('gv-b-' + n); if (!target) return;
  const inner = target.querySelector('details'); if (inner) inner.open = true;
  target.scrollIntoView({ block: 'start' }); target.tabIndex = -1; target.focus({ preventScroll: true });
}
function _gvTopic(d, t) {
  const at = d.topics.indexOf(t), prev = d.topics[at - 1], next = d.topics[at + 1];
  const more = (t.next || []).map(id => d.topics.find(x => x.id === id)).filter(Boolean).map(_gvRow).join('');
  const pager = `<nav class="gv-pager" aria-label="Соседние темы">${prev ? `<button type="button" class="v3-pill v3-pill--ghost" onclick="gvOpen('${esc(prev.id)}')">‹ ${esc(prev.title)}</button>` : '<span></span>'}${next ? `<button type="button" class="v3-pill" onclick="gvOpen('${esc(next.id)}')">${esc(next.title)} ›</button>` : ''}</nav>`;
  const blocks = t.blocks.map((b, i) => `<div class="gv-b" id="gv-b-${i + 1}">${(_GV_BLOCK[b.t] || (() => ''))(b)}</div>`).join('');
  return `${v3Head(t.title, { sub: `Тема ${at + 1} из ${d.topics.length}`, back: 'navBack()' })}${_gvHubButton(t)}
    <p class="gv-lead"><span class="gv-bigic" aria-hidden="true">${esc(t.icon)}</span>${esc(t.lead)}</p>${_gvToc(t)}${blocks}${_gvWhere(t.where)}
    ${more ? `<span class="v3-eyebrow gv-eb">Читай дальше</span>${more}` : ''}${pager}`;
}

function gvPaint(position) {
  const root = el('pg-help'), d = _GV.data; if (!root || !d) return;
  const t = _GV.view === 'topic' && d.topics.find(x => x.id === _GV.topic);
  const missing = _GV.view === 'topic' && !t ? `${v3Head('Тема не найдена', { back: 'navBack()' })}<p class="gv-lead">Эта ссылка устарела. Найди ответ среди всех тем.</p>${_gvCrumbs({ id: '', title: 'Тема не найдена' })}${_gvSearchBox('gvSearchFrom')}` : '';
  root.innerHTML = `<div class="gv-scope">${missing || (t ? _gvTopic(d, t) : _GV.view === 'terms' ? _gvTerms(d) : _GV.view === 'faq' ? _gvFaq(d) : _gvHub(d))}</div>`;
  if (_GV.offline) root.firstElementChild.insertAdjacentHTML('afterbegin', '<p class="gv-offline" role="status">Нет связи. Показана сохранённая версия: правила могли измениться. <button type="button" class="v3-link" onclick="gvReload()">Обновить</button></p>');
  if (_GV.view === 'hub' && _GV.q) gvSearch(el('gv-q'));
  if (position && el('gv-filter')) { el('gv-filter').value = position.filter || ''; gvFilter(el('gv-filter'), _GV.view === 'terms' ? 'term' : 'q'); }
  if (position) (position.open || []).forEach(id => { const row = el(id); if (row) row.open = true; });
  v3EnterSync(root.firstElementChild);
  const open = _GV.view === 'faq' && _GV.faq >= 0 ? el('gv-q-' + _GV.faq) : null;
  const heading = root.querySelector('h1'), origin = position?.focus && [...root.querySelectorAll('[data-gv-key]')].find(node => node.getAttribute('data-gv-key') === position.focus);
  if (origin) origin.focus({ preventScroll: true }); else if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
  if (position) window.scrollTo(0, position.scroll || 0); else if (open) open.scrollIntoView({ block: 'center' }); else window.scrollTo(0, 0);
  if (_GV.block && t) { gvBlock(_GV.block); } _GV.block = 0;
}
function gvView(view, topic = '', faq = -1) {
  if (view === _GV.view && topic === _GV.topic && faq === _GV.faq) return;
  _GV.history.push(_gvPosition()); if (_GV.history.length > 60) _GV.history.shift();
  _haptic('select'); _GV.view = view; _GV.topic = topic; _GV.faq = faq; gvPaint();
}
function _gvRemember(id) {
  if (!_GV.data?.topics.some(t => t.id === id)) return;
  try { localStorage.setItem(_GV_LAST, id); if (id === 'first-day') localStorage.setItem('pv_guide_first', '1'); } catch (_) { return; }
  // Профиль остаётся в памяти: обновляем «Дальше» сразу, до возвращения из прочитанной темы.
  if (id === 'first-day' && typeof renderV3Next === 'function') renderV3Next();
}
function gvOpen(id) { gvView('topic', id); _gvRemember(id); }
function gvOpenFaq(i) { gvView('faq', '', i); }
// «Путеводитель» в крошках: главная с тем же запросом в поиске (его стирает крестик в поле или «Показать все темы»).
function gvHome() { _GV.history = []; _GV.ext = false; _GV.view = 'hub'; _GV.topic = ''; _GV.faq = -1; gvPaint(); el('gv-q')?.focus(); }
function gvClear() { _GV.q = ''; const input = el('gv-q'); if (input) { input.value = ''; gvSearch(input); input.focus(); } }
// Поиск со страницы темы, словаря или вопросов: уводит на главную с результатами, «Назад» вернёт на эту страницу.
function gvSearchFrom(input) {
  const value = input.value;
  _GV.history.push({ ..._gvPosition(), q: _GV.q }); if (_GV.history.length > 60) _GV.history.shift();
  Object.assign(_GV, { view: 'hub', topic: '', faq: -1, q: value.trim() });
  gvPaint();
  const box = el('gv-q'); if (box) { box.value = value; box.focus({ preventScroll: true }); try { box.setSelectionRange(value.length, value.length); } catch (_) {} }
}
// «Назад»: по шагам внутри Путеводителя; первая тема, открытая с другого экрана, возвращает на тот экран (navBack снимет его со стека страниц).
function gvBack() {
  const prev = _GV.history.pop();
  if (prev) { Object.assign(_GV, { view: prev.view, topic: prev.topic, faq: prev.faq, q: prev.q }); gvPaint(prev); return true; }
  if (_GV.origin) {
    const origin = _GV.origin; _GV.origin = null;
    if (_activePage !== origin.page) {
      if (_navStack[_navStack.length - 1] === origin.page) _navStack.pop();
      switchPage(origin.page, null, true);
    }
    origin.restore();
    return true;
  }
  if (_GV.view === 'hub' || _GV.ext) return false;
  gvHome(); return true;
}
function gvReload() { _GV.data = null; return gvShow(); }
function gvGo(key) { _haptic('select'); if (_GV_GO[key]) _GV_GO[key](); }
function gvShow() {
  const root = el('pg-help'); if (!root) return Promise.resolve();
  if (!_GV.data) root.innerHTML = `<div class="gv-scope">${v3Head('Путеводитель', { sub: 'Загружаем…' })}<div class="sk" style="height:48px;border-radius:12px"></div><div class="sk" style="height:220px;border-radius:18px;margin-top:18px"></div></div>`;
  return gvLoad().then(() => gvPaint()).catch(() => { root.innerHTML = `<div class="gv-scope">${v3Head('Путеводитель')}<div class="v3-empty" role="alert"><b>Путеводитель не открылся</b><span>Проверь связь.</span> <button type="button" class="v3-link" onclick="gvShow()">Повторить</button></div></div>`; });
}
// Открыть тему из любого места приложения: подсказки, «Что нового», ссылка из бота (?startapp=guide_<id>[_<номер блока>])
function openGuide(id, block, returnTo) {
  _GV.history = [];
  _GV.faq = -1;
  _GV.ext = !!id && _activePage !== 'help';
  _GV.origin = typeof returnTo === 'function' ? { page: _activePage, restore: returnTo } : null;
  _GV.block = Number(block) || 0;
  if (_activePage !== 'help') switchPage('help');
  if (id) { _GV.view = 'topic'; _GV.topic = id; } else { _GV.view = 'hub'; _GV.topic = ''; }
  return gvShow().then(() => { if (id) _gvRemember(id); });
}
_backHooks.push(() => _activePage === 'help' && gvBack());
// Возврат из игры системным «Назад» достаёт страницу из памяти браузера с экраном «Открываем…» (_gvLeave): рисуем тему заново.
addEventListener('pageshow', e => { if (e.persisted && _activePage === 'help' && _GV.data) gvPaint(); });
