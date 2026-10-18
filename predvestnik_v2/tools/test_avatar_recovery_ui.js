// Execute the actual recovery code with controlled transport/timers and DOM.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../FastAPI/static/app.02.js'), 'utf8');
const block = source.slice(source.indexOf('let _vipAvatar ='), source.indexOf('function showCurrModal'));
const photo = 'data:image/jpeg;base64,AAAA';
async function main() {
  let calls = 0, saved, active = true;
  const nodes = Object.fromEntries(['hdr-ava','pro-showcase-ava','fit-ava'].map(k => [k, {}]));
  const context = vm.createContext({
    Date, Promise, setTimeout: fn => { fn(); },
    el: id => nodes[id], _profileData: {is_vip:true},
    v3SaveProfileCache: data => { saved = {...data}; },
    api: async () => { calls++; if (calls === 1) throw Error('offline'); return {vip:true, avatar:photo}; },
  });
  vm.runInContext(block, context);
  await vm.runInContext('_ensureVipAvatar(); _ensureVipAvatar(); _vipAvatarLoading', context);
  assert.equal(calls, 2, 'concurrent callers share one recovery, first error retried');
  assert.equal(saved.avatar, photo, 're-render source and persistent cache carry recovered photo');
  assert.match(nodes['pro-showcase-ava'].innerHTML, /data:image/);
  nodes['pro-showcase-ava'] = {};
  vm.runInContext('_ensureVipAvatar()', context);
  assert.match(nodes['pro-showcase-ava'].innerHTML, /data:image/, 'replacement DOM gets cached photo');
  assert.equal(calls, 2);
  assert.equal(vm.runInContext('_validAvatar(\'data:image/svg+xml;base64,AAAA\')', context), false);
  context.isCurrent = () => active;
  context.api = async () => { active = false; return {vip:true, avatar:photo}; };
  assert.equal(await vm.runInContext("_requestVipAvatar('other-profile-ref', isCurrent)", context), null,
    'late public response discarded after switching player');
  console.log('avatar UI: retry, single-flight, rerender, safe URI and stale-card guard OK');
}
main().catch(e => { console.error(e); process.exitCode = 1; });
