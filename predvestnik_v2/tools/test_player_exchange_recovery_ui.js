// Regression: a failed financial read must never become an empty portfolio.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '..', 'FastAPI', 'static', 'app.14.js'), 'utf8');
const entry = {hidden: true, title: ''};
let replies = {};
const context = vm.createContext({
  BASE: '', hdrs: () => ({}),
  fetch: async url => {
    const answer = replies[url];
    if (!answer) throw new Error('network failed');
    return {status: answer.status, ok: answer.status >= 200 && answer.status < 300,
      json: async () => answer.body};
  },
  api: async () => { throw new Error('login required'); },
  el: id => id === 'cc-exchange-v1' ? entry : null,
  _isFeatureEnabled: () => false,
});
vm.runInContext(source, context);
const read = path => vm.runInContext(`_pxRecoveryRequest(${JSON.stringify(path)})`, context);
const tick = () => new Promise(resolve => setTimeout(resolve, 0));

(async () => {
  const spot = '/player-exchange/v1/me?limit=1';
  const shorts = '/player-exchange/v1/shorts/me?limit=1';
  replies = {
    [spot]: {status: 404, body: {detail: 'Биржа монет пока закрыта для игроков.'}},
    [shorts]: {status: 404, body: {detail: 'Шорты пока закрыты для игроков.'}},
  };
  assert.equal(await read(spot), null);
  assert.equal(await read(shorts), null);
  vm.runInContext('syncPlayerExchangeEntry()', context);
  await tick();
  assert.equal(entry.hidden, true);

  replies[spot] = {status: 200, body: {holdings: {items: [{coin_id: 'owned'}]}}};
  replies[shorts] = {status: 500, body: {detail: 'temporary failure'}};
  await assert.rejects(read(shorts), /temporary failure/);
  await assert.rejects(Promise.all([read(spot), read(shorts)]), /temporary failure/);
  vm.runInContext('syncPlayerExchangeEntry()', context);
  await tick();
  assert.equal(entry.hidden, false);

  replies[spot] = {status: 404, body: {detail: 'Биржа временно недоступна: хранилище не готово.'}};
  await assert.rejects(read(spot), /хранилище не готово/);
  console.log('PLAYER_EXCHANGE_RECOVERY_UI_OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
