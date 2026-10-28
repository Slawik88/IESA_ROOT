// Run with node tools/test_guide_navigation.js. Real guide code and data, no browser or live database.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const staticDir = path.join(__dirname, '../FastAPI/static');
const source = fs.readFileSync(path.join(staticDir, 'app.57.js'), 'utf8');
const data = JSON.parse(fs.readFileSync(path.join(staticDir, 'guide-v3.json'), 'utf8'));

function fixture() {
  const storage = new Map(), timers = new Map(), nodes = new Map();
  let timerId = 0;
  const ctx = vm.createContext({
    guideData: data, BASE: '/predvestnik', AbortController, _backHooks: [], _haptic() {},
    window: { scrollY: 0 }, document: { querySelectorAll: () => [] }, el: id => nodes.get(id),
    localStorage: { getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v) },
    setTimeout: fn => { timers.set(++timerId, fn); return timerId; }, clearTimeout: id => timers.delete(id),
    fetch: async () => ({ ok: true, json: async () => data }),
    esc: s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;'),
    v3Head: title => `<h1>${title}</h1>`, location: { href: '' }, addEventListener() {},
  });
  vm.runInContext(source, ctx);
  const run = code => vm.runInContext(code, ctx);
  return { ctx, run, storage, timers, nodes };
}

async function main() {
  const f = fixture();
  f.run('_GV.data = guideData');
  const queries = [
    ['БП', 'pass'], ['bp', 'pass'], ['xp', 'xp'], ['как получить мору', 'mora'],
    ['как набрать опыт БП', 'xp'], ['где взять еду', 'pets'], ['как кормить питомца', 'pets'],
    ['почему не дают опыт', 'xp'], ['почему не видно скин', 'looks'], ['вип', 'vip'],
    ['как открыть сундук', 'keys'], ['звёздная пыль', 'dust'], ['звездная пыль', 'dust'],
    ['как сменить ник', 'profile'], ['почему питомец не растёт', 'pet-growth'],
    ['закончились силы', 'pet-growth'], ['нет энергии', 'pet-growth'], ['как повысить уровень питомца', 'pet-growth'],
    ['зачем нужны карточки', 'pets'], ['хочу питомца', 'pets'], ['как поставить флаг', 'mines'], ['как убрать флаг', 'mines'],
    ['почему не могу забрать вип награды', 'pass'], ['есть ли награды в обычном режиме', 'modes'],
    ['что делать если пропал интернет', 'modes'], ['что значит 3 звезды', 'keys'], ['вылазка', 'pet-play'], ['подготовка', 'pet-prep'],
  ];
  for (const [query, topic] of queries) {
    const results = f.run(`gvFind(${JSON.stringify(query)})`);
    assert(results.some(r => r.kind === 'topic' && r.id === topic), `${query} must find ${topic}`);
  }
  for (const query of ['   ', '???', 'совсемнесуществующаявещь', 'мора совсемнесуществующаявещь']) {
    assert.equal(f.run(`gvFind(${JSON.stringify(query)}).length`), 0, `Unrelated results for ${query}`);
  }
  assert(!f.run('_gvResults("<img src=x onerror=alert(1)>")').includes('<img'), 'Search must not insert user HTML');
  f.nodes.set('gv-results', {}); f.nodes.set('gv-home', {});
  f.ctx.window.scrollTo = position => { f.ctx.window.scrollY = position.top; };
  f.run('window.scrollY=2000; gvSearch({value:"БП"})');
  assert.equal(f.ctx.window.scrollY, 0, 'Searching from a category near the bottom must show the first results');
  assert(f.nodes.get('gv-home').hidden && !f.nodes.get('gv-results').hidden);

  // A reader returns to the source view with the search/filter, disclosure and scroll position intact.
  f.run('gvPaint = position => { window.restored = position; }');
  f.run('_GV.q="мора"; window.scrollY=460; gvOpen("mora"); gvOpen("wallet"); gvBack()');
  assert.equal(f.run('_GV.topic'), 'mora');
  f.run('gvBack()');
  assert.equal(f.run('_GV.view'), 'hub');
  assert.equal(f.run('_GV.q'), 'мора');
  assert.equal(f.run('window.restored.scroll'), 460);
  f.run('gvView("terms")');
  f.nodes.set('gv-filter', { value: 'еда' });
  f.ctx.document.querySelectorAll = () => [{ id: 'gv-gift-list' }];
  f.run('window.scrollY=900; gvOpen("pets"); gvBack()');
  assert.equal(f.run('_GV.view'), 'terms');
  assert.equal(f.run('window.restored.filter'), 'еда');
  assert.equal(f.run('window.restored.open[0]'), 'gv-gift-list');
  assert.equal(f.run('window.restored.scroll'), 900);
  f.run('_GV.q="мора"; gvHome()');
  assert.equal(f.run('_GV.q'), 'мора', '«Путеводитель» in the breadcrumbs keeps the search');
  assert.equal(f.run('_GV.history.length'), 0);
  f.run('_GV.q=""');
  assert.equal(f.storage.get('pv_guide_last'), 'pets');
  for (const [go, destination] of [['rhythm', '/rhythm-v2'], ['mines', '/minesweeper'], ['rating', '/league?game=rhythm']]) {
    f.run(`gvGo('${go}')`);
    assert.equal(f.ctx.location.href, '/predvestnik' + destination);
  }

  // S07: a topic opened from another screen goes back there in one press; inside the guide «Назад» still steps back.
  const nav = fixture();
  nav.run('_GV.data = guideData; gvPaint = () => {}; var _activePage = "chests", pages = []; switchPage = p => { pages.push(p); _activePage = p; }; gvShow = () => Promise.resolve()');
  await nav.run('openGuide("keys")');
  assert.equal(nav.run('_GV.ext'), true);
  nav.run('var profileRefreshes = 0; renderV3Next = () => profileRefreshes++; _gvRemember("first-day")');
  assert.equal(nav.storage.get('pv_guide_first'), '1');
  assert.equal(nav.run('profileRefreshes'), 1, 'reading first-day refreshes the cached profile card immediately');
  assert.equal(nav.run('gvBack()'), false, 'the first topic from a screen hands «Назад» to the page stack (back to that screen)');
  nav.run('_activePage = "chests"');   // navBack took the player back to the chests
  await nav.run('openGuide("keys")');
  nav.run('gvOpen("wallet")');
  assert.equal(nav.run('gvBack()'), true); assert.equal(nav.run('_GV.topic'), 'keys');
  assert.equal(nav.run('gvBack()'), false, 'and from the first topic — out to the screen');
  nav.run('_activePage = "help"; gvHome(); gvOpen("mora")');
  assert.equal(nav.run('gvBack()'), true); assert.equal(nav.run('_GV.view'), 'hub', 'a topic opened inside the guide returns to its hub');
  assert.equal(nav.run('gvBack()'), false);
  await nav.run('openGuide("pass", "5")');
  assert.equal(nav.run('_GV.block'), 5, 'guide_<topic>_<block> remembers the block to scroll to');
  // A guide opened from a modal restores both its page and the modal, without a duplicate page in the stack.
  const modal = fixture();
  modal.run('_GV.data = guideData; gvPaint = () => {}; var _activePage = "profile", _navStack = [], restoredModal = 0; switchPage = (p, btn, back) => { if (!back && p !== _activePage) _navStack.push(_activePage); _activePage = p; }; gvShow = () => Promise.resolve()');
  await modal.run('openGuide("wallet", 0, () => restoredModal++)');
  assert.equal(modal.run('gvBack()'), true);
  assert.equal(modal.run('_activePage'), 'profile');
  assert.equal(modal.run('_navStack.length'), 0);
  assert.equal(modal.run('restoredModal'), 1);
  assert.equal(modal.run('_GV.origin'), null, 'restoration is consumed once');
  modal.run('_activePage = "help"');
  await modal.run('openGuide("wallet", 0, () => restoredModal++)');
  assert.equal(modal.run('gvBack()'), true, 'a modal opened over the guide stays on that page');
  assert.equal(modal.run('_activePage'), 'help');
  assert.equal(modal.run('restoredModal'), 2);
  await modal.run('openGuide("keys")');
  assert.equal(modal.run('_GV.origin'), null, 'a new unrelated guide entry forgets the old modal');

  // Search from a topic page: results on the hub, «Назад» returns to the topic.
  nav.run('_GV.view = "topic"; _GV.topic = "keys"; _GV.history = []; gvSearchFrom({ value: "мора" })');
  assert.equal(nav.run('_GV.view'), 'hub'); assert.equal(nav.run('_GV.q'), 'мора');
  nav.run('gvBack()'); assert.equal(nav.run('_GV.topic'), 'keys');

  // Breadcrumbs: the guide, the group, the topic (both links work).
  const crumbs = nav.run('_gvCrumbs(guideData.topics.find(t => t.id === "keys"))');
  assert(crumbs.includes('gvHome()') && crumbs.includes("gvGroup('money')") && crumbs.includes('Деньги и ключи'), crumbs);
  // A long topic has a table of contents whose numbers match the block ids and the deep link.
  const pass = nav.run('_gvTopic(guideData, guideData.topics.find(t => t.id === "pass"))');
  assert(pass.includes('class="gv-toc"') && pass.includes('gvBlock(2)') && pass.includes('id="gv-b-2"'), 'pass has a table of contents');
  assert(!nav.run('_gvTopic(guideData, guideData.topics.find(t => t.id === "promo"))').includes('gv-toc'), 'a short topic has none');
  // Quick answers: one per section, not the first six of the list.
  const quick = nav.run('_gvQuick(guideData)');
  assert.equal(new Set(quick.map(i => data.groups.find(g => g.topics.includes(data.faq[i].t)).id)).size, quick.length);
  assert(quick.length >= 6);
  // FAQ grouped by section.
  assert.equal((nav.run('_gvFaq(guideData)').match(/class="gv-qcat"/g) || []).length, new Set(data.faq.map(f => data.groups.find(g => g.topics.includes(f.t)).id)).size);

  // Typos, the English keyboard layout and chat words find their topic; nonsense stays empty and shows three nearby topics.
  for (const [query, topic] of [['питмоец', 'pets'], ['сундкуи', 'keys'], ['vjhf', 'mora'], ['ghjvjrjl', 'promo'], ['промик', 'promo'], ['кейс', 'keys'], ['ачивки', 'ach'], ['донат', 'zarniki'], ['петы', 'pets']]) {
    const exact = f.run(`gvFind(${JSON.stringify(query)})`), fixed = exact.length ? '' : f.run(`gvSuggest(${JSON.stringify(query)})`);
    const rows = exact.length ? exact : f.run(`gvFind(${JSON.stringify(fixed)})`);
    assert(rows.some(r => r.kind === 'topic' && r.id === topic), `${query} → ${fixed || 'as is'} must find ${topic}`);
  }
  assert.equal(f.run('gvSuggest("совсемнесуществующаявещь")'), '');
  assert.equal(f.run('gvSuggest("мора")'), '', 'a correct query is not «corrected»');
  assert.equal(f.run('gvNear("совсемнесуществующаявещь").length'), 3);
  const sent = [];
  f.ctx.window.PVDiagnostics = { telemetry: (type, data) => sent.push([type, data.message]) };
  f.run('_gvResults("совсемнесуществующаявещь")');
  [...f.timers.values()].forEach(fn => fn()); f.timers.clear();
  assert.deepEqual(sent, [['guide_miss', 'совсемнесуществующаявещь']], 'an unanswered query goes to the owner\'s health panel once');
  f.run('_gvResults("совсемнесуществующаявещь")'); [...f.timers.values()].forEach(fn => fn()); f.timers.clear();
  assert.equal(sent.length, 1);
  assert(f.run('_gvResults("питмоец")').includes('Похоже на опечатку'), 'the player sees which word was searched instead');

  const fresh = fixture();
  let requests = 0;
  fresh.ctx.fetch = async () => { requests++; return { ok: true, json: async () => data }; };
  const first = fresh.run('gvLoad()'), second = fresh.run('gvLoad()');
  assert.equal(first, second, 'Repeated opens share the pending request');
  await first;
  assert.equal(requests, 1);
  assert.equal(fresh.timers.size, 0, 'Successful reads clear timeout');
  assert.equal(fresh.run('_GV.offline'), false);

  const cached = fixture();
  cached.storage.set('pv_guide_v1', JSON.stringify(data));
  cached.ctx.fetch = async () => { throw new Error('offline'); };
  await cached.run('gvLoad()');
  assert.equal(cached.run('_GV.offline'), true, 'Cached rules must be visibly marked as potentially stale');
  cached.ctx.fetch = async () => ({ ok: true, json: async () => data });
  cached.run('_GV.data=null');
  await cached.run('gvLoad()');
  assert.equal(cached.run('_GV.offline'), false, 'Recovery removes offline notice');

  const stuck = fixture();
  stuck.ctx.fetch = (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('timeout'))));
  const waiting = stuck.run('gvLoad()');
  [...stuck.timers.values()][0]();
  await assert.rejects(waiting, /guide/);
  assert.equal(stuck.run('_GV.pending'), null, 'Timeout leaves retry possible');

  const corrupt = fixture();
  corrupt.storage.set('pv_guide_v1', '{broken');
  corrupt.ctx.fetch = async () => ({ ok: true, json: async () => ({ version: 999, topics: [] }) });
  await assert.rejects(corrupt.run('gvLoad()'), /guide/);
  assert.equal(corrupt.storage.get('pv_guide_v1'), '{broken', 'Invalid network payload must not replace the saved copy');
  assert.equal(corrupt.timers.size, 0);
  const broken = fixture();
  broken.ctx.fetch = async () => ({ ok: true, json: async () => ({ version: 1, topics: [{}], groups: [], glossary: [], faq: [] }) });
  await assert.rejects(broken.run('gvLoad()'), /guide/);
  assert.equal(broken.storage.has('pv_guide_v1'), false, 'Incomplete topics must not poison the saved copy');
  console.log(`OK: ${queries.length} player queries; typos, layout and chat words; back to the source screen, breadcrumbs, contents, search from a topic; navigation, explicit game modes, request deduplication, offline recovery, timeout and corrupt data`);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
