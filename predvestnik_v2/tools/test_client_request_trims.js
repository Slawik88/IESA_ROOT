// S04: the real client code with fake timers. A burst of chat messages refreshes the tops once per pause,
// tab time goes to the server once a minute and when the app is hidden, the «Ещё» purge entry asks a short question
// and remembers "no" for a while.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const path = require('node:path');
const app01 = fs.readFileSync(path.join(__dirname, '../FastAPI/static/app.01.js'), 'utf8');
const app07 = fs.readFileSync(path.join(__dirname, '../FastAPI/static/app.07.js'), 'utf8');
const between = (source, start, end) => source.slice(source.indexOf(start), source.indexOf(end));

function clock() {
  let now = 1_000_000, seq = 0;
  const timers = new Map();
  return {
    Date: { now: () => now },
    setTimeout: (fn, ms) => { timers.set(++seq, { at: now + ms, fn }); return seq; },
    clearTimeout: id => timers.delete(id),
    setInterval: (fn, ms) => { const id = ++seq; const tick = () => { timers.set(id, { at: now + ms, fn: () => { fn(); tick(); } }); }; tick(); return id; },
    advance(ms) {
      const until = now + ms;
      for (;;) {
        const next = [...timers.entries()].filter(([, t]) => t.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        timers.delete(next[0]); now = next[1].at; next[1].fn();
      }
      now = until;
    },
  };
}

// 1. Tops: the first activity refreshes at once, a burst of 20 more within 10 s gives exactly one more refresh.
{
  const time = clock();
  let topLoads = 0;
  const context = vm.createContext({
    Date: time.Date, setTimeout: time.setTimeout, clearTimeout: time.clearTimeout,
    _activePage: 'profile', _v3TopCache: { week: 1 }, v3LazyTop: () => { topLoads++; },
    _reactiveSubs: new Set(), refreshCurrBar() {},
  });
  vm.runInContext(`let _dynamicEventTimer=0; const _dynamicScopes=new Set();\n${between(app01, 'function queueDynamicRefresh', 'function queueLiveBalance')}`, context);
  vm.runInContext("queueDynamicRefresh('activity')", context);
  time.advance(600);
  assert.equal(topLoads, 1, 'the first message refreshes the top');
  for (let i = 0; i < 20; i++) { vm.runInContext("queueDynamicRefresh('activity')", context); time.advance(400); }
  assert.equal(topLoads, 1, 'messages inside the pause wait');
  time.advance(10_000);
  assert.equal(topLoads, 2, 'the burst ends with one refresh');
  time.advance(60_000);
  assert.equal(topLoads, 2, 'no refresh without new messages');
}

// 2. Tab time: ticks every 15 s, one request per minute; switching tabs keeps seconds apart; hiding sends at once.
{
  const time = clock();
  const sent = [], listeners = {};
  const document = { visibilityState: 'visible', addEventListener: (type, fn) => { listeners[type] = fn; } };
  const context = vm.createContext({
    Date: time.Date, setInterval: time.setInterval, JSON, Map, document, _activePage: 'profile', _analyticsSession: 'sid',
    window: { addEventListener: (type, fn) => { listeners[type] = fn; } },
    api: (url, opts) => { sent.push({ url, opts, body: JSON.parse(opts.body) }); return Promise.resolve({}); },
  });
  vm.runInContext(between(app01, 'const _TAB_TICK_SEC', '// Единая программная навигация'), context);
  time.advance(45_000);
  assert.equal(sent.length, 0, 'nothing before a minute of viewing');
  time.advance(15_000);
  assert.deepEqual(sent.map(s => [s.body.tab, s.body.delta_sec]), [['profile', 60]]);
  assert.equal(sent[0].opts.keepalive, true, 'the request survives closing the app');
  context._activePage = 'top';
  time.advance(30_000);
  document.visibilityState = 'hidden'; listeners.visibilitychange();
  assert.deepEqual(sent.slice(1).map(s => [s.body.tab, s.body.delta_sec]), [['top', 30]], 'hiding sends what was counted');
  time.advance(120_000);
  assert.equal(sent.length, 2, 'a hidden app counts and sends nothing');
}

// 3. «Ещё»: one short access question; "no" is remembered for 10 minutes, "yes" adds the entry once.
(async () => {
  const time = clock();
  const asked = [];
  let available = false;
  const root = { querySelector: () => null, append() { root.appended = true; } };
  const context = vm.createContext({
    Date: time.Date, document: { createElement: () => ({ dataset: {} }) },
    el: id => (id === 'pg-more' ? root : (id === 'more-purge-entry' && root.appended ? {} : null)),
    _v3Icon: () => '', orderNavigation() {},
    purgeWebApi: async url => { asked.push(url); return { available }; },
  });
  vm.runInContext(between(app07, '// «Ещё» открывают часто', 'async function openPurgeHub'), context);
  await vm.runInContext('loadPurgeEntry()', context);
  assert.deepEqual(asked, ['/purge-v1/access'], 'a short access question, not the chat listing');
  await vm.runInContext('loadPurgeEntry()', context);
  assert.equal(asked.length, 1, '"no" is remembered');
  time.advance(10 * 60 * 1000);
  available = true;
  await vm.runInContext('loadPurgeEntry()', context);
  assert.equal(asked.length, 2, 'asked again after 10 minutes');
  assert.equal(root.appended, true, 'the entry appears');
  await vm.runInContext('loadPurgeEntry()', context);
  assert.equal(asked.length, 2, 'an existing entry is not asked for again');
  console.log('PASS: tops refreshed once per burst, tab time once a minute and on hide, purge entry by a short cached question');
})().catch(error => { console.error(error); process.exit(1); });
