// Behaviour proof: independent reads, recovery, stale responses and no writes from stale VIP.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../FastAPI/static/app.30.js'), 'utf8');
const root = { innerHTML: '' };
let calls = [], responses = {}, notices = [];
const ctx = vm.createContext({
  console, Date, Promise, setTimeout, clearTimeout, window: {scrollTo: () => {}},
  _profileData: { vip: { days_left: 5, expires_at: '2030-01-01T00:00:00Z' } },
  el: () => root, switchPage: () => {}, v3EnterSync: () => {}, _haptic: () => {},
  _profileEsc: x => String(x).replaceAll('<', '&lt;'), _profileDate: x => x,
  fmt: x => String(x), toast: x => notices.push(String(x)), v3Confirm: async () => true, loadProfile: async () => {throw new Error("profile offline");},
  api: p => { calls.push(p); return responses[p](); },
});
vm.runInContext(source, ctx);
assert.match(vm.runInContext('_svMission({active:true,daily_mission:{cycle_progress:0,milestone_reward_keys:2}})', ctx), /ключи: 2/);
vm.runInContext('_svSee=()=>""; _svTerms=()=>""; _svMission=()=>""; _svPerks=()=>""; _svBadge=()=>"";', ctx);
const run = x => vm.runInContext(x, ctx);
const ok = x => () => Promise.resolve(x);
const fail = () => Promise.reject(new Error('offline'));
const packs = {packages: [{stars: 20,total:215}]};
function setup(vip, pk=ok(packs)) {
  calls = [];
  responses = {'/payments/zarniki/packages': pk, '/vip-v2/status': vip, '/skins-v3/me': ok(null)};
}
async function main() {
  setup(fail);
  await run("openStoreV3('vip')");
  assert.match(root.innerHTML, /Не удалось обновить VIP/);
  assert.match(root.innerHTML, /2030-01-01/);
  assert.match(root.innerHTML, /Последние данные профиля/);
  assert.match(root.innerHTML, /Повторить/);
  assert.match(root.innerHTML, /Помощь в сообществе/);
  assert.doesNotMatch(root.innerHTML, /VIP не активен|onclick="svVipBuy|onclick="svBadgeSet/);
  await run('svVipBuy(30)'); run("svBadgeSet('badge_id','spark')");
  assert.equal(calls.length, 3, 'stale/profile information must not enable a write');

  setup(ok({active:false,tiers:[]}), fail);
  await run("openStoreV3('vip')");
  assert.match(root.innerHTML, /VIP не активен/);
  assert.doesNotMatch(root.innerHTML, /Не удалось обновить VIP|Не удалось загрузить пакеты/);
  run("svTab('zarniki')");
  assert.match(root.innerHTML, /Не удалось загрузить пакеты Зарников/);

  setup(ok({active:true,days_left:3,expires_at:'2031-01-01',tiers:[]}));
  await run("openStoreV3('vip')");
  assert.match(root.innerHTML, /VIP активен/);
  setup(fail);
  await run("openStoreV3('vip')");
  assert.match(root.innerHTML, /2031-01-01/);
  assert.match(root.innerHTML, /Обновлено/);
  assert.doesNotMatch(root.innerHTML, /onclick="svVipBuy/);

  setup(ok({}));
  await run("openStoreV3('vip')");
  assert.match(root.innerHTML, /Не удалось обновить VIP/, 'invalid payload is not an inactive subscription');

  let release;
  setup(() => new Promise(resolve => { release=resolve; }));
  const old = run("openStoreV3('vip')");
  setup(ok({active:false,tiers:[]}));
  await run("openStoreV3('vip')");
  release({active:true,days_left:999,expires_at:'2040-01-01',tiers:[]});
  await old;
  assert.match(root.innerHTML, /VIP не активен/);
  assert.doesNotMatch(root.innerHTML, /2040/);
  // A confirmed write remains successful when a subsequent read fails.
  setup(fail); notices=[];
  responses['/vip-v2/purchase']=ok({package_days:30});
  run("_svRender=()=>{}; _profileData.zarniki=1000; _sv.loading=false; _sv.vipFailed=false; _sv.vip={active:false,tiers:[{duration_days:30,price_zarniki:100}]};");
  await run('svVipBuy(30)');
  assert.equal(calls.filter(x=>x==='/vip-v2/purchase').length,1);
  assert(notices.some(x=>/продлён/.test(x)));
  assert(notices.some(x=>/Покупка подтверждена/.test(x)));
  assert(!notices.some(x=>/Покупка не выполнена|offline/.test(x)));
  assert.equal(run('_sv.vipFailed'),true);
  await run('svVipBuy(30)');
  assert.equal(calls.filter(x=>x==='/vip-v2/purchase').length,1,'stale status cannot buy again');
  console.log('OK: VIP recovery, independent reads, invalid payload, retry, stale-response rejection and write guards');
}
main().catch(e => { console.error(e);process.exitCode=1; });
