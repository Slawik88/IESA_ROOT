const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../FastAPI/static/app.23.js'),'utf8');
let requests=0,fail=false,applied=[],toasts=[],nativeCalls=0;
const items=[{id:'forest',owned:true,level:'D',shown_tier:'D',tokens:{'--v3-acc':'#aaffaa'}},{id:'dune',owned:true,level:'D',shown_tier:'D',tokens:{'--v3-acc':'#ffccaa'}}];
const state=id=>({items:items.map(x=>({...x,equipped:x.id===id})),zarniki:100,essence:{balance:10}});
const context=vm.createContext({document:{startViewTransition(){nativeCalls++;throw Error('WebView transition unavailable')}},globalThis:{},_profileData:{},v3SaveProfileCache(){},renderV3Bar(){},v3ApplyLook:look=>applied.push(look?.id||null),_haptic(){},toast:e=>toasts.push(String(e)),api:async(_,options)=>{requests++;if(fail)throw 'Не удалось сохранить образ';return state(JSON.parse(options.body).skin_id)}});
vm.runInContext(source,context);vm.runInContext('_lkRender=()=>{}',context);
context.initial=state(null);vm.runInContext('_lk.st=initial;_lk.sel="forest"',context);
(async()=>{
 await vm.runInContext("lkAct('equip')",context);assert.equal(applied.at(-1),'forest');assert.equal(vm.runInContext('_profileData.look.id',context),'forest');
 await vm.runInContext("lkAct('unequip')",context);assert.equal(applied.at(-1),null);
 vm.runInContext('_lk.sel="dune"',context);await vm.runInContext("lkAct('equip')",context);assert.equal(applied.at(-1),'dune');assert.equal(vm.runInContext('_profileData.look.id',context),'dune');
 assert.deepEqual(applied,['forest',null,'dune'],'each successful request applies its confirmed palette exactly once');assert.equal(nativeCalls,0,'equipping cannot start a conflicting page transition');
 fail=true;await vm.runInContext("lkAct('equip')",context);assert.equal(toasts.at(-1),'Не удалось сохранить образ');assert.equal(applied.length,3,'failed requests preserve the equipped look');assert.equal(vm.runInContext('_lk.busy',context),false);
 assert.equal(requests,4);console.log('PASS: equip, remove and swap apply once without native transitions; genuine request failure remains visible');
})().catch(e=>{console.error(e);process.exitCode=1});
