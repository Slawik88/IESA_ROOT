// Actual client functions under lost HTTP responses and a later /me recovery.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const dir=path.join(__dirname,'../FastAPI/static');
const hub=fs.readFileSync(path.join(dir,'app.40.js'),'utf8'),gear=fs.readFileSync(path.join(dir,'app.49.js'),'utf8');
const state={keys:{},seq:0,busy:false,needsRefresh:false,pet:1,me:{now:'2026-10-22T01:00:00Z',pets:[{id:1,equipment:{revision:0,items:{},equipped:{}}}],equipment:{attempts_left:3,parts:0,open:null}}};
const calls=[];let fail=true;
const box={_tr:state,_trPet:id=>state.me.pets.find(p=>p.id===id),_trRender(){},_trRefresh:()=>Promise.resolve(true),toast(){},document:{getElementById:()=>null},crypto:{randomUUID:()=>String(Math.random())},_trFail(){},
 api:async(p,o)=>{const body=JSON.parse(o.body);calls.push({p,body});if(fail)throw Error('lost');return p.endsWith('/equipment')?{equipment:{revision:body.expected_tier+1,items:{compass:2},equipped:{}},parts:5,energy:50,spent:12}:{outing:{id:'new',pet_id:1,status:'active'},energy:50};}};
vm.createContext(box);
for(const [source,names] of [[hub,['_trKey','_trPost','_trRun']],[gear,['trailGear','trailOutingStart','trailOutingChoose']]])for(const name of names){
 const m=source.match(new RegExp(`^(?:async )?function ${name}\\([\\s\\S]*?^\\}`,'m'));assert(m,name);vm.runInContext(m[0],box);
}
(async()=>{
 await box.trailOutingStart(null,1);const first=calls.at(-1).body.action_id;
 await box.trailOutingStart(null,1);assert.equal(calls.at(-1).body.action_id,first,'retry keeps identity before recovery');
 // Lost response was committed. /me discovers it; the player resumes and finishes.
 state.me.equipment.attempts_left=2;state.me.equipment.open=null;
 fail=false;await box.trailOutingStart(null,1);
 assert.notEqual(calls.at(-1).body.action_id,first,'new outing after resumed one must not replay old start');
 assert.equal(state.me.equipment.attempts_left,1);
 state.me.equipment.open=null;state.me.equipment.attempts_left=3;state.me.now='2026-10-23T00:00:00Z';
 await box.trailOutingStart(null,1);assert.notEqual(calls.at(-1).body.action_id,first,'daily reset cannot reuse uncertain nonce');
 fail=true;await box.trailGear(null,'equip','compass');const oldGear=calls.at(-1).body.action_id;
 await box.trailGear(null,'equip','compass');assert.equal(calls.at(-1).body.action_id,oldGear);
 state.me.pets[0].equipment.revision=2;await box.trailGear(null,'equip','compass');
 assert.notEqual(calls.at(-1).body.action_id,oldGear,'recovered revision retires a lost equip response');
 let release;box.api=()=>new Promise(r=>release=r);let jobs=0;
 const a=box._trRun(null,async()=>{jobs++;await box.api();});await box._trRun(null,()=>jobs++);
 assert.equal(jobs,1,'double click cannot start a second writer');release();await a;
 console.log('PASS: lost start/gear responses retain retry identity, recovered outing/revision gets fresh identity, double clicks serialized');
})().catch(e=>{console.error(e);process.exitCode=1;});
