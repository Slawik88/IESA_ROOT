const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const {performance}=require('node:perf_hooks');
const pending=[];
const context=vm.createContext({performance,setTimeout,clearTimeout,DOMException,
  requestAnimationFrame:fn=>setTimeout(fn,2),
  document:{hidden:false,addEventListener(){}},
  BASE:'https://fixture.invalid',hdrs:()=>({'x-session-token':context.session}),
  session:'A',fetch:(url,opts)=>new Promise(resolve=>pending.push({url,opts,resolve})),
  _scheduleReactiveRefresh(){},_humanErr:x=>x,
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../FastAPI/static/app.load-scheduler.js'),'utf8'),context);
const source=fs.readFileSync(path.join(__dirname,'../FastAPI/static/app.01.js'),'utf8');
vm.runInContext(source.slice(source.indexOf('function api('),source.indexOf('// UX_AUDIT С9')),context);
const run=code=>vm.runInContext(code,context);
const reply=(job,value)=>job.resolve({ok:true,status:200,json:async()=>value});
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
(async()=>{
  run('_pvBusyUntil=0');
  const old=run("api('/profile/balances')");
  assert.equal(old,run("api('/profile/balances')"));
  const mutation=run("api('/skins-v3/buy',{method:'POST',body:'{}'})");
  reply(pending[1],{purchased:true});await mutation;
  const fresh=run("api('/profile/balances')");
  reply(pending[0],{zarniki:100});
  await tick();
  // A late old response shares the authoritative fresh request.
  assert.equal(pending.length,3);
  reply(pending[2],{zarniki:20});
  assert.equal((await fresh).zarniki,20);
  assert.equal((await old).zarniki,20);
  const previous=run("api('/profile/me')");
  context.session='B';
  pending[3].resolve({status:401,ok:false});
  await assert.rejects(previous,{name:'AbortError'});
  const current=run("api('/profile/me')");reply(pending[4],{user_id:202});
  assert.equal((await current).user_id,202);
  let finishBody, bodyStarted;
  const started=new Promise(resolve=>bodyStarted=resolve);
  const body=run("api('/profile/me')");
  pending[5].resolve({ok:true,status:200,json:()=>new Promise(resolve=>{finishBody=resolve;bodyStarted()})});
  await started;context.session='C';finishBody({user_id:202});
  await assert.rejects(body,{name:'AbortError'});
  console.log('PASS: mutation ordering, shared fresh reads, previous-session 401');
})().catch(error=>{console.error(error);process.exitCode=1});
