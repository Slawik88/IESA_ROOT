const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {performance} = require('node:perf_hooks');
const events = {};
const context = vm.createContext({
  performance, setTimeout, clearTimeout,
  requestAnimationFrame: fn => setTimeout(() => fn(performance.now()), 5),
  document: {hidden:false, addEventListener:(name,fn)=>events[name]=fn},
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../FastAPI/static/app.load-scheduler.js'),'utf8'),context);
const evaluate = code => vm.runInContext(code,context);
const pause = ms => new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
  evaluate('_pvBusyUntil=0');
  let reads=0, complete;
  context.read = () => {reads++;return new Promise(resolve=>complete=resolve)};
  const a=evaluate("pvRead('auth-A:/me',read)"),b=evaluate("pvRead('auth-A:/me',read)");
  assert.equal(a,b); assert.equal(reads,1);
  evaluate('pvInvalidateReads()');
  const c=evaluate("pvRead('auth-A:/me',()=>Promise.resolve('fresh'))");
  assert.notEqual(a,c); complete('old'); assert.equal(await c,'fresh'); await a;
  let active=0,maxActive=0,done=0;
  context.job=async()=>{active++;maxActive=Math.max(active,maxActive);await pause(20);active--;done++};
  await Promise.all([evaluate("pvBackground('a',job)"),evaluate("pvBackground('b',job)"),evaluate("pvBackground('c',job)")]);
  assert.equal(maxActive,1);assert.equal(done,3);
  await evaluate("pvBackground('fails',()=>Promise.reject(Error('offline')))");
  await evaluate("pvBackground('recovers',job)");assert.equal(done,4);
  context.document.hidden=true;
  const hidden=evaluate("pvBackground('hidden',job)");
  await pause(25);assert.equal(done,4);
  context.document.hidden=false;events.visibilitychange();await hidden;assert.equal(done,5);
  const start=performance.now();evaluate('pvTransitionStarted(90)');
  await evaluate('pvAfterTransition()');assert(performance.now()-start>=75);
  const times=[];
  await Promise.all([evaluate('pvAfterTransition()').then(()=>times.push(performance.now())),
                    evaluate('pvAfterTransition()').then(()=>times.push(performance.now()))]);
  assert(times[1]-times[0]>=3);
  console.log('OK: GET dedup/invalidation, serial background reads, errors/hidden recovery, transition delay and separate response frames');
})().catch(error=>{console.error(error);process.exitCode=1});
