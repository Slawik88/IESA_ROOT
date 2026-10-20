const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
global.window = global; global.crypto = require('crypto').webcrypto;
const memory = new Map();
global.localStorage = {getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
vm.runInThisContext(fs.readFileSync(require('path').join(__dirname,'../FastAPI/static/local-games-v1.js'),'utf8'));
(async()=>{
  const input=JSON.parse(fs.readFileSync(0,'utf8')), results=[];
  for(const test of input){
    if(test.game==='fresh'){const store=new PVLocal.Store('fresh',null,'');store.data.template=test.packet;results.push(await store.fresh(test.target,test.difficulty));continue;}
    if(test.game==='rhythm'){
      const engine=new PVLocal.Rhythm(test.packet), initial=await engine.view();
      for(const action of test.actions){if(action.kind==='pick')engine.pick(action.perk_id);else engine.step(action.rune,action.elapsed_ms,(await engine.view()).rune);}
      results.push({initial,state:engine.state,view:await engine.view()});
    }else{
      const engine=new PVLocal.Mines(test.packet);
      for(const action of test.actions)engine.step(action.cell,action.kind,action.elapsed_ms);
      results.push(engine.state);
    }
  }
  const legacy=new PVLocal.Store('rules',null,'');legacy.data.template={state:{ruleset_version:'old'},ruleset_version:'old',catalog:[],legacy:true};
  const active=legacy.data.template;await legacy.refreshRules(async()=>({ruleset_version:'rhythm-v2-rules-6',catalog:input[0].packet.catalog}));
  assert.equal(active.ruleset_version,'old');assert.equal(legacy.data.template.ruleset_version,'rhythm-v2-rules-6');
  const newPacket=await legacy.fresh('rhythm');assert.equal(newPacket.origin.ruleset_version,'rhythm-v2-rules-6');assert.equal(newPacket.legacy,false);
  const withoutSDK=new PVLocal.Store('rhythm',null,'',new URLSearchParams({user:JSON.stringify({id:1})}).toString());
  assert.equal(withoutSDK.key,'pv-local-v1:rhythm:1');
  const a=new PVLocal.Store('rhythm',{initDataUnsafe:{user:{id:1}}},''), b=new PVLocal.Store('rhythm',{initDataUnsafe:{user:{id:2}}},'');
  a.queue({run_id:'lost-reply'},[{kind:'tap'}]);
  assert.equal(b.data.outbox.length,0);
  let payload;
  await a.flush(async(p,o)=>{payload=o.body;throw Error('reply lost');}).catch(()=>{});
  assert.equal(new PVLocal.Store('rhythm',{initDataUnsafe:{user:{id:1}}},'').data.outbox.length,1);
  const restored=new PVLocal.Store('rhythm',{initDataUnsafe:{user:{id:1}}},'');
  await restored.flush(async(p,o)=>{assert.equal(o.body,payload);return {run_id:'lost-reply'};});
  assert.equal(restored.data.outbox.length,0);
  const queue=new PVLocal.Store('queue',null,'');queue.queue({run_id:'bad'},[{}]);queue.queue({run_id:'good'},[{}]);let seen=[];await queue.flush(async p=>{seen.push(p);if(p.includes('/bad/')){const e=Error('conflict');e.status=409;throw e;}return {run_id:'good'};});assert.equal(seen.length,2);assert.equal(queue.data.rejected.length,1);assert.equal(queue.data.outbox.length,0);
  process.stdout.write(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exit(1);});
