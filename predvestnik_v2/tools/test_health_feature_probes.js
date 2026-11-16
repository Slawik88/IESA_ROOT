// Execute the real feature probes: disabled features, refreshes and delayed responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = name => fs.readFileSync(path.join(__dirname, '../FastAPI/static', name), 'utf8');
const requests = [], entry = {hidden: true};
const context = vm.createContext({
  window: {}, document: {querySelectorAll: () => [entry]},
  el: () => null, _activePage: 'profile',
  api: route => new Promise((resolve, reject) => requests.push({route, resolve, reject})),
});
const shell = source('app.01.js');
vm.runInContext(shell.slice(shell.indexOf('let _sysFlags ='), shell.indexOf('function _isPageEnabled')), context);
vm.runInContext(source('app.44.js') + '\n' + source('app.45.js'), context);
const run = code => vm.runInContext(code, context);
const settle = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
const flags = (shop, gifts) => run(`_applySysFlags([{key:'shop_v1',enabled:${shop}},{key:'gifts_v2',enabled:${gifts}}])`);

(async () => {
  flags(false, false);
  run('shopProbe(); _giftsLoad();');
  assert.equal(requests.length, 0, 'disabled features must not be probed');

  flags(true, true);
  run('shopProbe(); _giftsLoad(); shopProbe(); _giftsLoad();');
  assert.deepEqual(requests.map(r => r.route), ['/shop-v1/me', '/gifts-v2/me']);
  flags(false, false);
  requests.splice(0).forEach(r => r.resolve({shelf: {}}));
  await settle();
  assert.equal(entry.hidden, true, 'late success cannot re-open a disabled entry');
  assert.equal(run('_shop.me'), null);
  assert.equal(run('_gifts.me'), null);

  flags(false, true);
  run('shopProbe(); _giftsLoad();');
  assert.equal(requests.length, 1, 'the gift shelf works while the shop is disabled');
  requests.shift().resolve({shelf: {}});
  await settle();
  assert.equal(run('_giftsOn'), true);

  flags(true, true);
  run('shopProbe()');
  requests.shift().resolve({balances: {}});
  await settle();
  assert.equal(entry.hidden, false, 'refresh can re-enable the entry');

  // Older profile payloads do not carry feature flags: retain the existing server probe.
  run('_applySysFlags(undefined); shopProbe(); _giftsLoad();');
  assert.equal(requests.length, 2);
  requests.splice(0).forEach(r => r.reject('closed'));
  await settle();
  console.log('OK: feature probes skip closed sections, survive flag changes and ignore stale responses');
})().catch(error => { console.error(error); process.exitCode = 1; });
