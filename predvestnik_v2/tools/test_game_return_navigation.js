// Real game shell and socket lifecycle: safe history, stale storage, old WebViews.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const read = name => fs.readFileSync(path.join(__dirname, '../FastAPI/static', name), 'utf8');
const trip = {nonce: 'qa-origin', url: 'https://qa.test/predvestnik/', returnTo: 'guide_rhythm'};
{
  const memory = new Map();
  const source = read('app.04.js');
  const box = {window: {}, BASE: '/predvestnik', history: {state: {pvGameOrigin: trip.nonce}},
    location: {origin: 'https://qa.test', pathname: '/predvestnik/'},
    sessionStorage: {getItem: k => memory.get(k), removeItem: k => memory.delete(k)}};
  vm.createContext(box);
  vm.runInContext(source.slice(source.indexOf('function leaveForGame('), source.indexOf('function openRhythmV2Game(')), box);
  const target = data => { memory.set('pv_game_return', JSON.stringify(data)); return vm.runInContext('gameReturnTarget()', box); };
  assert.equal(target(trip), 'guide_rhythm');
  assert.equal(target({...trip, returnTo: 'pets'}), 'pets');
  assert.equal(target({...trip, returnTo: 'admin'}), '');
  assert.equal(target({...trip, nonce: 'stale'}), '');
  box.history.state = null;
  assert.equal(target({url: trip.url}), '');
  memory.set('pv_game_return', '{broken');
  assert.equal(vm.runInContext('gameReturnTarget()', box), '');
}
function game({pending = true, stored = trip, state = null, previous = true, navigation = true} = {}) {
  const memory = new Map([['pv_game_return', JSON.stringify(stored)]]);
  if (pending) memory.set('pv_game_pending', trip.nonce);
  const listeners = {}, back = {href: '', setAttribute() {}};
  let backs = 0;
  const history = {state, replaceState(value) { this.state = value; }, back() { backs++; }};
  const previousEntry = {index: 0, url: trip.url, getState: () => ({pvGameOrigin: previous ? trip.nonce : 'another-entry'})};
  const box = {window: {}, document: {body: {dataset: {appBase: '/predvestnik'}}, getElementById: () => back,
    addEventListener(name, fn) { listeners[name] = fn; }}, history, URL,
    location: {origin: 'https://qa.test'}, sessionStorage: {getItem: k => memory.get(k) || null,
      setItem: (k, v) => memory.set(k, v), removeItem: k => memory.delete(k)}};
  if (navigation) box.window.navigation = {currentEntry: {index: 1}, entries: () => [previousEntry]};
  vm.createContext(box); vm.runInContext(read('game-shell-v3.js'), box);
  function click(extra = {}) {
    let prevented = false;
    listeners.click({target: {closest: () => back}, button: 0, defaultPrevented: false,
      preventDefault() { prevented = true; }, ...extra});
    return prevented;
  }
  return {box, memory, back, click, backs: () => backs};
}
let fixture = game();
assert.equal(fixture.back.href, '/predvestnik/?startapp=guide_rhythm');
assert(fixture.click()); assert.equal(fixture.backs(), 1);
assert(!fixture.click({ctrlKey: true}));
assert(!fixture.click({defaultPrevented: true})); // League's internal pass → game Back wins.
fixture.box.window.GameShell.carryReturn();
assert.equal(fixture.memory.get('pv_game_pending'), trip.nonce);
assert(!game({navigation: false}).click());
assert(!game({previous: false}).click());
fixture = game({pending: false});
assert.equal(fixture.back.href, '/predvestnik/?startapp=games'); // stale previous visit
assert(!fixture.click());
assert(game({pending: false, state: {pvGameTrip: trip}}).click()); // refresh preserves entry state
assert(!game({pending: false, state: {pvGameTrip: {url: trip.url}}}).click());
fixture = game({stored: {nonce: trip.nonce, url: 'https://elsewhere.test/', returnTo: 'guide_rhythm'}});
assert.equal(fixture.back.href, '/predvestnik/?startapp=games');
assert(!fixture.click());

// A socket which closes after pageshow must not clear or replace the new one.
const listeners = {}, sockets = [], timers = new Map();
let refreshes = 0, timer = 0;
class Socket {
  constructor() { sockets.push(this); }
  close() { this.closed = true; }
}
const box = {window: {addEventListener: (n, f) => { listeners[n] = f; }},
  document: {visibilityState: 'visible', addEventListener() {}}, WebSocket: Socket,
  BASE: 'https://qa.test', _uid: 1, INIT_DATA: '', sess: () => 'synthetic',
  _activePage: 'arena', loadActivitiesHub() { refreshes++; },
  setTimeout: f => { timers.set(++timer, f); return timer; }, clearTimeout: k => timers.delete(k), setInterval() {},
  refreshInitData() {}, refreshCurrBar() { refreshes++; }, loadPendingNotifications() {}, queueDynamicRefresh() {}, _syncBackButton() {}};
vm.createContext(box);
const source = read('app.01.js');
vm.runInContext(source.slice(source.indexOf('let _ws=null'), source.indexOf('function showAppUpdate(')), box);
vm.runInContext('connectWS()', box); assert.equal(sockets.length, 1);
listeners.pagehide(); assert(sockets[0].closed);
vm.runInContext('connectWS()', box); assert.equal(sockets.length, 1);
listeners.pageshow({persisted: true}); assert.equal(sockets.length, 2); assert.equal(refreshes, 2);
sockets[0].onclose({code: 1000}); assert.equal(timers.size, 0);
vm.runInContext('connectWS()', box); assert.equal(sockets.length, 2);
sockets[1].onclose({code: 1008}); assert.equal(timers.size, 0);
console.log('OK: game return identity, stale/corrupt origins, modifiers, refresh, mode carry, old WebView fallback; socket suspend/resume and stale close');
