const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../FastAPI/static/local-games-sw.js'),'utf8').replace('{{VERSION}}','test').replace('{{PRECACHE}}',JSON.stringify(['/rhythm-v2','/static/local-games-v1.js']));
function boot(failInstall=false){
  const handlers={},entries=new Map([['/rhythm-v2',{ok:true,status:200,body:'saved-shell'}]]);let activated=false;
  const ctx={self:{location:{origin:'https://example.test'},clients:{claim:async()=>{}},skipWaiting:async()=>{activated=true;},addEventListener:(name,fn)=>handlers[name]=fn},URL,AbortController,setTimeout,clearTimeout,
    caches:{open:async()=>({put:async(k,v)=>entries.set(typeof k==='string'?k:k.url,v),match:async()=>entries.get('/rhythm-v2')}),keys:async()=>['pv-games-old'],delete:async()=>{throw Error('old cache must survive failed install');}},
    fetch:async url=>({ok:!failInstall,status:failInstall?503:200,clone(){return this;}})};
  vm.runInNewContext(source,ctx);return {ctx,handlers,activated:()=>activated};
}
(async()=>{
  const bad=boot(true);let installation;bad.handlers.install({waitUntil:p=>installation=p});await assert.rejects(installation,/incomplete/);assert(!bad.activated());
  const h=boot();let response;h.ctx.fetch=async()=>({ok:false,status:503});h.handlers.fetch({request:{method:'GET',url:'https://example.test/rhythm-v2'},respondWith:p=>response=p});assert.equal((await response).body,'saved-shell');
  response=null;h.handlers.fetch({request:{method:'GET',url:'https://example.test/rhythm-v2/runs/private'},respondWith:p=>response=p});assert.equal(response,null,'authenticated API must never be cached');
  response=null;h.handlers.fetch({request:{method:'POST',url:'https://example.test/rhythm-v2'},respondWith:p=>response=p});assert.equal(response,null);
  console.log('OK: worker install atomicity, old-cache survival, gateway-error fallback and authenticated API exclusion');
})().catch(e=>{console.error(e);process.exitCode=1;});
