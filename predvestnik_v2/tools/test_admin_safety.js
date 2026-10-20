// Безопасность действий админки 3.0 — проверяются настоящие функции из файлов админки (вырезаются и исполняются в vm),
// а не их копии. Заменяет прежние хэш-пины: важно не то, что текст функции не менялся, а что она делает.
//   node tools/test_admin_safety.js
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict'), path = require('node:path');
const dir = path.join(__dirname, '../FastAPI/static/bot-admin');
const core = fs.readFileSync(path.join(dir, 'admin.js'), 'utf8'), people = fs.readFileSync(path.join(dir, 'admin-people.js'), 'utf8');
const fn = (src, name) => { const m = src.match(new RegExp(`^function ${name}\\([\\s\\S]*?^\\}`, 'm')); assert(m, `нет функции ${name}`); return m[0]; };
const decl = (src, name) => { const m = src.match(new RegExp(`^const ${name} = [\\s\\S]*?;$`, 'm')); assert(m, `нет ${name}`); return m[0]; };
const ctx = vm.createContext({esc: s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])),
  num: n => String(n), who: (id, u) => u ? '@' + u : 'id' + id});
vm.runInContext([decl(core, 'DURATIONS'), decl(core, 'DANGEROUS'), fn(core, 'needsTypedConfirm'), fn(core, 'confirmLines'), fn(people, 'memberFits'), fn(people, 'playerActionKeys'),
  'this.out = {DANGEROUS, needsTypedConfirm, confirmLines, memberFits, playerActionKeys};'].join('\n'), ctx);
const {DANGEROUS, needsTypedConfirm, confirmLines, memberFits, playerActionKeys} = ctx.out;

// 1. Опасное идёт через «Далее» и итог: набор не сужается.
for (const k of ['ban', 'kick', 'global_ban', 'block', 'balance', 'rank', 'vip', 'leave', 'message', 'close', 'revoke_sessions']) assert(DANGEROUS.has(k), k);
for (const k of ['warn', 'mute', 'unmute', 'unban']) assert(!DANGEROUS.has(k), k);

// 2. Ввод ID: только когда сервер его потребует (правила, известный игрок), порог — по каждой валюте.
const rules = {actions: ['global_ban', 'rank'], balance: {mora: 100000, diamonds: 50}};
const player = {id: 7, username: 'x', confirm_rules: rules};
assert.equal(needsTypedConfirm('global_ban', {}, player), true);
assert.equal(needsTypedConfirm('ban', {}, player), false);
assert.equal(needsTypedConfirm('balance', {currency: 'mora', amount: '-100000'}, player), true, 'минус тоже крупная сумма');
assert.equal(needsTypedConfirm('balance', {currency: 'mora', amount: '99999'}, player), false);
assert.equal(needsTypedConfirm('balance', {currency: 'diamonds', amount: '50'}, player), true, 'порог своей валюты');
assert.equal(needsTypedConfirm('balance', {currency: 'essence', amount: '1e9'}, player), false, 'без порога — без ввода');
assert.equal(needsTypedConfirm('global_ban', {}, {...player, confirm_rules: undefined}), false);
assert.equal(needsTypedConfirm('global_ban', {}, {id: 7, confirm_rules: rules}), false, 'ник неизвестен (контекст чата) — ввод не спрашиваем');
assert.equal(needsTypedConfirm('rank', {}, {username: 'x', confirm_rules: rules}), false);

// 3. Итог показывает, кому, где и что изменится; текст экранирован.
const lines = o => confirmLines(...o).map(([k, v]) => k + ': ' + v).join('\n');
let t = lines(['ban', {minutes: 0, reason: '<script>'}, {...player, name: 'Вася', rank_name: 'Игрок'}, {chat_title: 'Чат <b>'}]);
assert.match(t, /Кто: <b>Вася · @x<\/b> · ID 7/); assert.match(t, /Чат: <b>Чат &lt;b&gt;<\/b>/); assert.match(t, /навсегда/); assert.match(t, /&lt;script&gt;/); assert.doesNotMatch(t, /<script>/);
t = lines(['balance', {currency: 'mora', amount: '-500'}, {...player, currencies: [{code: 'mora', title: 'Мора'}], balances: {mora: 1200}}, {}]);
assert.match(t, /-500/); assert.match(t, /было 1200, станет <b>700<\/b>/);
t = lines(['ban', {minutes: 60}, {}, {chat_title: 'Чат'}]);
assert.doesNotMatch(t, /Кто:/, 'жалоба передаёт пустой контекст: строки «Кто» из контекста нет');
assert.match(lines(['ban', {minutes: 60}, {}, {}]), /1 час/);

// 4. В чате показываются только возможные действия.
const c = (o = {}) => ({left: false, local_rank: 1, muted: false, ban: null, warns: 0, ...o});
assert(!memberFits('unmute', c()) && memberFits('mute', c()));
assert(memberFits('unmute', c({muted: true})) && !memberFits('mute', c({muted: true})));
assert(!memberFits('ban', c({ban: {}})) && memberFits('unban', c({ban: {}})) && !memberFits('kick', c({ban: {}})));
assert(!memberFits('kick', c({left: true})) && !memberFits('local_rank', c({left: true})) && !memberFits('local_rank', c({local_rank: 9})));
assert(!memberFits('unwarn_all', c()) && memberFits('unwarn_all', c({warns: 2})));

// 5. «Везде»: из пар — только возможное; сессии админки — только у сотрудников.
const acts = ['global_ban', 'global_unban', 'block', 'unblock', 'balance', 'revoke_sessions'].map(key => ({key}));
assert.deepEqual([...playerActionKeys({actions: {player: acts}, rank: 0})], ['global_ban', 'block', 'balance']);
assert.deepEqual([...playerActionKeys({actions: {player: acts}, rank: 3, blocked: {}, global_ban: {}})], ['global_unban', 'unblock', 'balance', 'revoke_sessions']);
console.log('OK: опасные действия, ввод ID, итог, фильтр действий');
