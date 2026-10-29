// Execute the actual recovery code with controlled transport/timers and DOM.
// Photos arrive as a server address with avatar_state (roadmap S02): only "loading" is asked again,
// "absent" and "vip_only" are final answers and cause no further requests.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../FastAPI/static/app.02.js'), 'utf8');
const block = source.slice(source.indexOf('let _vipAvatar ='), source.indexOf('let _walletPolicy'));
const esc = String(source.match(/function _profileEsc[^\n]+/)[0]);
const shared = fs.readFileSync(path.join(__dirname, '../FastAPI/static/app.20.js'), 'utf8');   // _validAvatar, _avatarSrc: общие с топами игр (S13)
const helpers = shared.slice(shared.indexOf('function _validAvatar('), shared.indexOf('function _v3Avatar('));
const photo = '/profile/avatar/abcdefghijklmnopqrstuvwx?v=0123456789abcdef';
const legacy = 'data:image/jpeg;base64,AAAA';
async function main() {
  let calls = 0, saved, active = true;
  const nodes = Object.fromEntries(['hdr-ava','pro-showcase-ava','fit-ava'].map(k => [k, {}]));
  const context = vm.createContext({
    Date, Promise, BASE: '/predvestnik', setTimeout: fn => { fn(); },
    el: id => nodes[id], _profileData: {is_vip:true},
    v3SaveProfileCache: data => { saved = {...data}; },
    api: async () => { calls++; if (calls === 1) throw Error('offline'); if (calls === 2) return {vip:true, avatar:null, avatar_state:'loading'}; return {vip:true, avatar:photo, avatar_state:'ready'}; },
  });
  vm.runInContext(esc + helpers + block, context);
  await vm.runInContext('_ensureVipAvatar(); _ensureVipAvatar(); _vipAvatarLoading', context);
  assert.equal(calls, 3, 'concurrent callers share one recovery; an error and "loading" are retried');
  assert.equal(saved.avatar, photo, 're-render source and persistent cache carry recovered photo');
  assert.match(nodes['pro-showcase-ava'].innerHTML, /src="\/predvestnik\/profile\/avatar\//, 'address gets the app base');
  nodes['pro-showcase-ava'] = {};
  vm.runInContext('_ensureVipAvatar()', context);
  assert.match(nodes['pro-showcase-ava'].innerHTML, /\/profile\/avatar\//, 'replacement DOM gets cached photo');
  assert.equal(calls, 3);
  for (const bad of ['data:image/svg+xml;base64,AAAA', '/profile/avatar/short?v=0123456789abcdef', 'https://evil.test/profile/avatar/abcdefghijklmnopqrstuvwx?v=0123456789abcdef', '/profile/avatar/abcdefghijklmnopqrstuvwx?v=x"onerror="1'])
    assert.equal(vm.runInContext(`_validAvatar(${JSON.stringify(bad)})`, context), false, bad);
  assert.equal(vm.runInContext(`_validAvatar(${JSON.stringify(legacy)})`, context), true, 'older data URI answers still show');
  context.isCurrent = () => active;
  context.api = async () => { active = false; return {vip:true, avatar:photo}; };
  assert.equal(await vm.runInContext("_requestVipAvatar('other-profile-ref', isCurrent)", context), null,
    'late public response discarded after switching player');

  // No photo and "not a VIP" are answers: exactly one request, no retries.
  for (const state of ['absent', 'vip_only']) {
    let asked = 0;
    const quiet = vm.createContext({Date, Promise, BASE: '', setTimeout: fn => { fn(); }, el: () => null, _profileData: {is_vip:true},
      v3SaveProfileCache() {}, api: async () => { asked++; return {vip: state !== 'vip_only', avatar: null, avatar_state: state}; }});
    vm.runInContext(esc + helpers + block, quiet);
    assert.equal(await vm.runInContext('_requestVipAvatar(null)', quiet), null);
    assert.equal(asked, 1, `${state}: one answer, no retries`);
    vm.runInContext(`_ensureVipAvatar(${JSON.stringify(state)})`, quiet);
    assert.equal(vm.runInContext('_vipAvatarLoading', quiet), null, `${state} from the profile: no request at all`);
    assert.equal(asked, 1);
  }

  // The current shell has no legacy hdr-ava. Its real profile loader must still hydrate.
  const modernNodes={'pro-main':{},'pro-showcase-ava':{}};
  const modern=vm.createContext({Date,Promise,BASE:'',setTimeout:fn=>fn(),el:id=>modernNodes[id],
    _profileData:null,_initChatId:0,_cid:0,_uid:0,_ws:{},v3PaintCachedProfile(){},
    renderProfileHome:()=>'<profile>',updateCurrBar(){},v3SaveProfileCache(){},
    api:async route=>route==='/profile/me'?{is_vip:true,user_id:101,username:'QA',avatar:null,avatar_state:'loading'}:{vip:true,avatar:photo,avatar_state:'ready'}});
  vm.runInContext(esc + helpers + block,modern);
  vm.runInContext(source.slice(source.indexOf('function loadProfile()'),source.indexOf('function openBotAdmin()')),modern);
  await vm.runInContext('loadProfile()',modern);
  await vm.runInContext('_vipAvatarLoading',modern);
  assert.match(modernNodes['pro-showcase-ava'].innerHTML,/\/profile\/avatar\//,'modern profile recovers without hdr-ava');
  console.log('avatar UI: retry only while loading, single-flight, rerender, safe addresses, final states and stale-card guard OK');
}
main().catch(e => { console.error(e); process.exitCode = 1; });
