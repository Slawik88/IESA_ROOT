// Execute the shipped widget scripts with a small Telegram bridge and DOM double.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '../core/widgets/html');
const boot = fs.readFileSync(path.join(root, '_boot.js'), 'utf8');

function widget(key, {telegram = true, storage = null, state = {b: '---------', r: 1}} = {}) {
  const nodes = new Map(), events = {}, calls = [], pending = [], timers = [];
  const element = () => ({textContent: '', dataset: {}, style: {}, children: [], appendChild(child) { this.children.push(child); }});
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, element());
    return nodes.get(id);
  };
  const bridge = {
    chatData: JSON.stringify(state), colorScheme: 'dark', viewer: {first_name: 'Creator'},
    onEvent(type, fn) { const previous = events[type]; events[type] = () => { if (previous) previous(); fn(); }; }, ready() {},
    request(data) { calls.push(data); return new Promise((resolve, reject) => pending.push({resolve, reject})); },
    HapticFeedback: {selectionChanged() {}, notificationOccurred() {}, impactOccurred() {}}, copyText() {},
  };
  const context = vm.createContext({window: {TelegramWidget: telegram ? bridge : undefined},
    document: {getElementById: get, createElement: element},
    localStorage: {getItem() { return storage; }, setItem() {}}, Promise, Date,
    setTimeout(fn) {timers.push(fn);}});
  const source = fs.readFileSync(path.join(root, `${key}.html`), 'utf8');
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1];
  vm.runInContext(`${script};${boot}`, context);
  return {context, nodes, events, calls, pending, bridge, timers};
}

async function run() {
  for (const key of ['ping', 'ttt', 'card']) {
    widget(key, {telegram: false});
    widget(key, {storage: '{broken'});
  }
  const state = {k: 'abcdefghijklmnop', t: 'Задания', l: ['Прогресс 3 / 10', '<script>не разметка</script>'], p: 0, n: 2, r: 7};
  const card = widget('card', {state});
  assert.deepEqual(card.calls, ['card:p:abcdefghijklmnop:0:7'], 'drawing acknowledges the exact revision');
  assert.equal(card.nodes.get('lines').children[1].textContent, '<script>не разметка</script>');
  card.pending.shift().resolve({result: JSON.stringify(state)});
  await new Promise(resolve => setImmediate(resolve));
  card.nodes.get('next').onclick();
  card.nodes.get('next').onclick();
  assert.equal(card.calls.length, 2, 'page taps cannot race');
  assert.equal(card.calls[1], 'card:p:abcdefghijklmnop:1:7');
  card.pending.shift().resolve({result: JSON.stringify({...state, p: 1, l: ['Страница 2']})});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(card.context.S.p, 1);
  card.bridge.chatData = JSON.stringify({...state, r: 8});
  card.events.chatDataChanged();
  assert.equal(card.calls.at(-1), 'card:p:abcdefghijklmnop:0:8', 'a changed menu must be acknowledged again');
  card.bridge.chatData = JSON.stringify({...state, r: 9});
  card.events.chatDataChanged();
  const before = card.calls.length;
  card.pending.shift().resolve({result: JSON.stringify({...state, r: 8})});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(card.calls.length, before + 1, 'new revision during pending request is not lost');
  assert.equal(card.calls.at(-1), 'card:p:abcdefghijklmnop:0:9');
  const failedAck = widget('card', {state});
  failedAck.pending.shift().reject({code: 'FAILED'});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(failedAck.timers.length, 1, 'initial acknowledgement retries a transient failure');
  failedAck.timers.shift()();
  assert.equal(failedAck.calls.length, 2);
  const ping = widget('ping');
  assert.deepEqual(ping.calls, ['ping:s']);
  ping.pending.shift().reject({code: 'TIMEOUT'});
  await new Promise(resolve => setImmediate(resolve));
  assert.match(ping.nodes.get('m').textContent, /Бот не ответил/);
  ping.nodes.get('go').onclick();
  assert.equal(ping.calls.length, 2, 'retry after failed background request works');
  ping.pending.shift().resolve({result: JSON.stringify({t: Date.now(), r: 2})});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ping.nodes.get('nn').textContent, 1);

  const ttt = widget('ttt');
  const first = ttt.nodes.get('g').children[0];
  first.onclick({currentTarget: first});
  first.onclick({currentTarget: first});
  assert.deepEqual(ttt.calls, ['ttt:m:0:---------'], 'a double click sends only one move');
  ttt.pending.shift().resolve({result: JSON.stringify({b: 'x---o----', r: 3})});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ttt.context.S.b, 'x---o----');
  ttt.bridge.chatData = JSON.stringify({b: '---------', r: 2});
  ttt.events.chatDataChanged();
  assert.equal(ttt.context.S.b, 'x---o----', 'late state cannot erase a newer move');
  ttt.bridge.chatData = JSON.stringify({b: 'x---o---x', r: 4});
  ttt.events.chatDataChanged();
  assert.equal(ttt.context.S.b, 'x---o---x');
  process.stdout.write('OK: widget scripts, offline render, broken storage, retry, double click and state revisions\n');
}

run().catch(error => { process.stderr.write(`${error.stack}\n`); process.exitCode = 1; });
