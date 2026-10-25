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
    v3Head: title => `<h1>${title}</h1>`, location: { href: '' },
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
  f.run('gvHome()');
  assert.equal(f.run('_GV.q'), '');
  assert.equal(f.run('_GV.history.length'), 0);
  assert.equal(f.storage.get('pv_guide_last'), 'pets');
  for (const [go, destination] of [['rhythm', '/rhythm-v2'], ['mines', '/minesweeper'], ['rating', '/league?game=rhythm']]) {
    f.run(`gvGo('${go}')`);
    assert.equal(f.ctx.location.href, '/predvestnik' + destination);
  }

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
  console.log(`OK: ${queries.length} player queries; navigation, explicit game modes, request deduplication, offline recovery, timeout and corrupt data`);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
