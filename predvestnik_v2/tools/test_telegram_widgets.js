// Execute the shipped widget scripts with a small Telegram bridge and DOM double.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '../core/widgets/html');
const boot = fs.readFileSync(path.join(root, '_boot.js'), 'utf8');
const KEYS = ['ping', 'ttt', 'hub', 'mines'];

function element(tag = 'div') {
  const props = {};
  let text = '';
  return {
    tag, className: '', hidden: false, dataset: {}, children: [], props,
    get textContent() { return text; },
    set textContent(value) { text = value; this.children = []; },   // как в DOM: текст заменяет детей
    style: {setProperty(name, value) { props[name] = value; }},
    appendChild(child) { this.children.push(child); return child; },
    all() { return this.children.flatMap(child => [child, ...(child.all ? child.all() : [])]); },
    querySelector(selector) {
      const [owner, child] = selector.replace(/^\./, '').split('>');
      const found = this.all().find(node => (node.className || '').split(' ').includes(owner));
      return found && child ? found.children.find(node => node.tag === child) : found;
    },
    querySelectorAll(selector) { return selector === '[data-w]' ? this.all().filter(node => node.dataset && node.dataset.w) : []; },
    text() { return [this.textContent, ...this.children.map(child => child.text ? child.text() : child.textContent)].join(' '); },
  };
}

function widget(key, {telegram = true, storage = null, chatData = null, scheme = 'dark', look = PLAIN} = {}) {
  const nodes = new Map(), events = {}, calls = [], pending = [], links = [], haptics = [];
  const get = id => {
    if (!nodes.has(id)) nodes.set(id, element());
    return nodes.get(id);
  };
  const documentElement = element('html');
  const bridge = {
    chatData: chatData || JSON.stringify({b: '---------', r: 1}), colorScheme: scheme, viewer: {first_name: 'Creator'},
    themeParams: {bg_color: scheme === 'dark' ? '#181818' : '#ffffff'},
    onEvent(type, fn) { events[type] = fn; }, ready() {},
    request(data) { calls.push(data); return new Promise((resolve, reject) => pending.push({resolve, reject})); },
    openTelegramLink(url) { links.push(url); },
    HapticFeedback: {selectionChanged() { haptics.push('select'); }, notificationOccurred(type) { haptics.push(type); }, impactOccurred() {}},
    copyText() {},
  };
  const context = vm.createContext({window: {TelegramWidget: telegram ? bridge : undefined},
    document: {getElementById: get, createElement: element, createTextNode: text => ({textContent: text}), documentElement,
      querySelectorAll: selector => [...nodes.values()].flatMap(node => node.querySelectorAll(selector))},
    localStorage: {getItem() { return storage; }, setItem(name, value) { storage = value; }}, Promise, Date, Math, JSON, parseInt,
    setInterval() { return 0; }, setTimeout(fn) { setImmediate(fn); return 0; }});
  const source = fs.readFileSync(path.join(root, `${key}.html`), 'utf8');
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1];
  vm.runInContext(`var L=${JSON.stringify(look)};${script};${boot}`, context);   // как core.widgets.html(): образ перед шаблоном
  return {context, nodes, events, calls, pending, bridge, links, haptics, documentElement, storage: () => storage};
}

const settle = () => new Promise(resolve => setImmediate(resolve));
const buttons = node => node.all().filter(child => child.tag === 'button');
// то, что core/widgets/skin.py вшивает в скрипт: без образа и «Бездна» на SSS
const PLAIN = {s: '', t: '', ti: '', g: '🔮', b: ['', ''], i: ['💬', '🔥', '💰'], d: '', f: '', ph: '', pt: '', q: ''};
const VOID = {s: 'void:SSS', t: 'SSS', ti: '🌌 Предвестник', g: '🌌', b: ['꧁𒆜', '𒆜꧂'], i: ['🌌', '✨', '🌙'],
              d: '┄┄ ⋆ ┄┄', f: '┄┄┄┄ ⋆ ┄┄┄┄', ph: 'Край воронки мерцает. Значит, кто-то смотрит.', pt: '⋆', q: '🌌'};

async function hubChecks() {
  const day = {v: 'day', k: 'void:SSS', b: {q: 1, pass: 1}, r: 5, l: [
    {i: '@p', t: 'Серия: 3 дня', s: 'Напиши в группе с ботом до полуночи', w: [Date.now() - 1000, Date.now() + 3_600_000]},
    {i: '📜', t: 'Задания дня: 4 из 4', s: '20 Моры', p: [4, 4], a: 'q:d'},
    {i: '🎫', t: 'Пропуск: 3 из 40', p: [10, 300], a: [['Подробнее', 'v:pass']]},
    {i: '👛', t: 'Кошелёк', g: [['🪙', '1 200'], ['🗝', '3']]},
    {i: '🔥', t: 'Серия', m: '0123401234012340123401234012340123401234012340123401234012340123'.slice(0, 63)},
    {i: '🎨', t: 'Образ', a: [['Образы', 'https://t.me/bot/app?startapp=looks']]},
    {i: '🐾', t: 'Рыжик · Экспедиция 6 ч', a: [['Осторожно', 'r:abc:c'], ['Ровно', 'r:abc:s'], ['Смело', 'r:abc:b']]},
  ]};
  const hub = widget('hub', {chatData: JSON.stringify(day), look: VOID});
  assert.deepEqual(hub.calls, ['hub:s:day'], 'the pult refreshes the current tab when it appears');
  assert.equal(hub.nodes.get('hn').textContent, '꧁𒆜 Creator 𒆜꧂', 'the name wears the skin brackets, as in chat');
  assert.equal(hub.nodes.get('hs').textContent, '🌌 Предвестник', 'the skin title item');
  assert.equal(hub.nodes.get('ht').textContent, '🌌 SSS');
  assert.match(hub.nodes.get('cd').className, / sh$/, 'SSS adds the shine (the markup gives the card its own class)');
  assert.equal(hub.nodes.get('cd').children.at(-1).textContent, '⋆ '.repeat(5), 'SS+ sparks of the skin');
  assert.equal(hub.nodes.get('dv').textContent, '┄┄ ⋆ ┄┄');
  assert.equal(hub.nodes.get('ph').textContent, VOID.ph);
  const rows = hub.nodes.get('rows').children;
  assert.equal(rows.length, 7);
  assert.equal(rows[0].children[0].children[0].textContent, '✨', '@p is the skin progress icon');
  assert.equal(buttons(rows[1])[0].className, 'btn', 'a claim is the filled primary button');
  assert.equal(buttons(rows[2])[0].className, 'btn sec', 'a tab jump is a calm secondary button');
  assert.equal(rows[0].dataset.w.split(',').length, 2, 'timer rows tick');
  assert.match(rows[0].text(), /ещё (59 мин|1 ч)/);
  const tabs = buttons(hub.nodes.get('tabs'));
  assert.equal(tabs.length, 5);
  assert.match(tabs[1].className, /on/, '«День» is active');
  assert.match(tabs[2].className, /dot/, 'a ready quest reward puts a dot on «Задания»');

  hub.pending.shift().resolve({result: JSON.stringify({...day, r: 6})});
  await settle();
  const claim = buttons(rows[1])[0];
  assert.equal(claim.textContent, 'Забрать');
  claim.onclick();
  claim.onclick();
  assert.deepEqual(hub.calls.slice(1), ['hub:q:d:day'], 'a double tap claims once');
  hub.pending.shift().resolve({result: JSON.stringify({...day, r: 7, o: '✅ Забрано: Мора +20.'})});
  await settle();
  assert.equal(hub.nodes.get('m').textContent, '✅ Забрано: Мора +20.');
  assert.ok(hub.haptics.includes('success'));

  buttons(hub.nodes.get('rows').children[5])[0].onclick();
  assert.deepEqual(hub.links, ['https://t.me/bot/app?startapp=looks'], 'app sections open as Telegram links');
  assert.equal(hub.calls.length, 2, 'a link is not a bot request');

  buttons(hub.nodes.get('tabs'))[3].onclick();
  assert.equal(hub.calls.at(-1), 'hub:v:pass');
  assert.match(buttons(hub.nodes.get('tabs'))[3].className, /on/, 'the tapped tab lights up at once');
  hub.pending.shift().reject({code: 'TIMEOUT'});
  await settle();
  assert.equal(hub.context.TAB, 'day', 'a failed tab switch returns to the shown tab');
  assert.match(buttons(hub.nodes.get('tabs'))[1].className, /on/);

  const choice = buttons(hub.nodes.get('rows').children[6]);
  assert.equal(choice.length, 3, 'an expedition fork shows three paths');
  choice[2].onclick();
  assert.equal(hub.calls.at(-1), 'hub:r:abc:b:day');

  const plain = widget('hub', {chatData: JSON.stringify({v: 'q', r: 1, l: []})});
  assert.equal(plain.nodes.get('hs').textContent, 'Образ не выбран');
  assert.equal(plain.nodes.get('ht').hidden, true, 'no tier badge without a skin');
  assert.equal(plain.nodes.get('dv').hidden, true);
  assert.deepEqual(plain.calls, ['hub:s:q']);
  widget('hub', {chatData: JSON.stringify({v: 'qw', r: 1, l: []})});
}

async function minesChecks() {
  const board = {z: 6, b: '#'.repeat(36), c: 6, st: 'a', v: 3, t: 5000, x: 'run1', n: 'Лёгкий · 6×6', r: 2, k: 'void:SSS'};
  const mines = widget('mines', {chatData: JSON.stringify(board), look: VOID});
  assert.deepEqual(mines.calls, ['mines:s']);
  const early = mines.nodes.get('g').children;
  early[3].onclick({currentTarget: early[3]});
  assert.equal(mines.calls.length, 1, 'a tap during the background refresh waits');
  mines.pending.shift().resolve({result: JSON.stringify({...board, r: 3})});
  await settle();
  await settle();
  assert.deepEqual(mines.calls.slice(1), ['mines:o:run1:3:3'], '…and is played after it, into the shown run');
  mines.pending.shift().resolve({result: JSON.stringify({...board, r: 3.5})});
  await settle();
  await settle();
  mines.calls.splice(1);
  const cells = mines.nodes.get('g').children;
  assert.equal(cells.length, 36);
  cells[7].onclick({currentTarget: cells[7]});
  cells[8].onclick({currentTarget: cells[8]});
  assert.deepEqual(mines.calls.slice(1), ['mines:o:run1:7:3'], 'one move at a time');
  const opened = '0'.repeat(7) + '1' + '#'.repeat(28);
  mines.pending.shift().resolve({result: JSON.stringify({...board, b: opened, v: 4, r: 4})});
  await settle();
  await settle();
  assert.deepEqual(mines.calls.slice(2), ['mines:o:run1:8:4'], 'a tap made while waiting is played after the answer');
  mines.pending.shift().resolve({result: JSON.stringify({...board, b: opened, v: 5, r: 5})});
  await settle();

  const clock = mines.nodes.get('tm').textContent;
  mines.nodes.get('fl').onclick();
  assert.equal(mines.nodes.get('tm').textContent, clock, 'redrawing for a flag does not rewind the clock');
  const fresh = mines.nodes.get('g').children;
  fresh[20].onclick({currentTarget: fresh[20]});
  assert.equal(mines.calls.length, 3, 'a flag is local and costs no request');
  assert.equal(mines.nodes.get('g').children[20].textContent, '🚩');
  assert.match(mines.storage(), /"f":\[20\]/, 'flags survive on the device for this run');
  assert.equal(mines.nodes.get('fc').textContent, 'мин: 5');

  const lost = {...board, b: '*' + '1'.repeat(35), st: 'l', v: 6, r: 6, p: [['easy', 'Лёгкий · 6×6, мин: 6']],
                o: '💥 Мина!'};
  mines.bridge.chatData = JSON.stringify(lost);
  mines.events.chatDataChanged();
  assert.equal(mines.nodes.get('cl').hidden, true, 'no flag switch after the end');
  const picker = buttons(mines.nodes.get('pk'));
  assert.equal(picker.length, 1);
  picker[0].onclick();
  assert.equal(mines.calls.at(-1), 'mines:n:easy');
  const none = widget('mines', {chatData: JSON.stringify({st: 'n', p: [['easy', 'Лёгкий']], r: 1})});
  assert.equal(none.nodes.get('g').children.length, 0, 'no board before the first game');
  assert.equal(buttons(none.nodes.get('pk')).length, 1);
}

async function run() {
  for (const key of KEYS) {
    widget(key, {telegram: false});
    widget(key, {storage: '{broken'});
  }
  const ping = widget('ping');
  assert.deepEqual(ping.calls, ['ping:s']);
  ping.pending.shift().reject({code: 'TIMEOUT'});
  await settle();
  assert.match(ping.nodes.get('m').textContent, /Бот не ответил/);
  ping.nodes.get('go').onclick();
  assert.equal(ping.calls.length, 2, 'retry after failed background request works');
  ping.pending.shift().resolve({result: JSON.stringify({t: Date.now(), r: 2})});
  await settle();
  assert.equal(ping.nodes.get('nn').textContent, 1);

  const ttt = widget('ttt');
  const first = ttt.nodes.get('g').children[0];
  first.onclick({currentTarget: first});
  first.onclick({currentTarget: first});
  assert.deepEqual(ttt.calls, ['ttt:m:0:---------'], 'a double click sends only one move');
  ttt.pending.shift().resolve({result: JSON.stringify({b: 'x---o----', r: 3})});
  await settle();
  assert.equal(ttt.context.S.b, 'x---o----');
  ttt.bridge.chatData = JSON.stringify({b: '---------', r: 2});
  ttt.events.chatDataChanged();
  assert.equal(ttt.context.S.b, 'x---o----', 'late state cannot erase a newer move');
  ttt.bridge.chatData = JSON.stringify({b: 'x---o---x', r: 4});
  ttt.events.chatDataChanged();
  assert.equal(ttt.context.S.b, 'x---o---x');

  await hubChecks();
  await minesChecks();
  process.stdout.write('OK: widget scripts, offline render, broken storage, retry, double click, state revisions, ' +
                       'board tabs/claims/links/skin dress, mines moves/queue/flags/picker\n');
}

run().catch(error => { process.stderr.write(`${error.stack}\n`); process.exitCode = 1; });
