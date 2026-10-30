// Real room poller and invalidation handler: virtual time, controlled races, no network.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../FastAPI/static/app.55.js'), 'utf8');
const start = source.indexOf('async function moPoll('), end = source.indexOf('function moChannel(', start);
let now = 0, nextTimer = 0, calls = 0, delayed = null;
const timers = new Map(), rendered = [], nodes = new Map();
const MO = {gen: 1, room: 7, channel: 'table', messages: new Map(), pollSeq: 0, errors: 0};
const data = version => ({version, me: {id: 1}, players: [], messages: [], channels: ['table']});
const context = {
  MO, AbortController, document: {hidden: false},
  setTimeout(fn, delay) {const id = ++nextTimer; timers.set(id, {at: now + delay, fn}); return id;},
  clearTimeout(id) {timers.delete(id);},
  moAlive: g => g === MO.gen,
  moRequest() {calls++; return delayed ? new Promise(resolve => {delayed.resolve = resolve;}) : Promise.resolve(data(1));},
  moRenderRoom(d) {rendered.push({at: now, version: d.version});},
  el(id) {if (!nodes.has(id)) nodes.set(id, {textContent: '', innerHTML: ''}); return nodes.get(id);},
  moChannel() {throw Error('unexpected channel');}, moError: String, moStop() {MO.gen++;},
};
vm.createContext(context); vm.runInContext(source.slice(start, end), context);
async function advance(ms) {
  const until = now + ms;
  while (true) {
    const next = [...timers].sort((a, b) => a[1].at - b[1].at)[0];
    if (!next || next[1].at > until) break;
    now = next[1].at; timers.delete(next[0]); await next[1].fn(); await Promise.resolve();
  }
  now = until;
}
const event = {type: 'mafia_room_changed', room_id: 7, version: 1};
(async () => {
  await context.moPoll(1); const initial = calls;
  await advance(59999);
  assert.equal(calls - initial, 2, 'quiet room performs only two periodic reads before one minute');
  const quiet = calls;
  context.moLive({...event, room_id: 8}); await advance(200);
  assert.equal(calls, quiet, 'another table must not refresh this one');
  for (let i = 0; i < 40; i++) context.moLive(event);
  const sentAt = now; await advance(100);
  assert.equal(calls, quiet + 1, 'a burst at the same version is one read, including chat changes');
  assert(rendered.at(-1).at - sentAt <= 1000);
  delayed = {}; const pending = context.moRefresh();
  context.moLive(event); context.moLive(event);
  delayed.resolve(data(2)); delayed = null; await pending;
  const raced = calls; await advance(100);
  assert.equal(calls, raced + 1, 'an event during GET requires a second snapshot');
  context.moLive({type: 'balance_stream_ready'}); await advance(100);
  assert.equal(calls, raced + 2, 'reconnection immediately repairs the missed-event gap');
  context.moLive(event); MO.gen++; await advance(100);
  assert.equal(calls, raced + 2, 'late notifications cannot revive a closed controller');
  for (const file of ['app.55.js', 'app.56.js']) {
    const lines = fs.readFileSync(path.join(__dirname, '../FastAPI/static', file), 'utf8').split('\n');
    assert(Math.max(...lines.map(line => line.length)) <= 400, file + ': readable source line budget');
  }
  console.log('PASS quiet room: 3 reads/minute including entry; 100ms burst delivery, same-version chat, GET race, reconnect and stale room; source lines <=400');
})().catch(error => {console.error(error); process.exitCode = 1;});
