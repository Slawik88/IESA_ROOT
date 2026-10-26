// Execute the production purge UI with controlled response loss and concurrent updates.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../FastAPI/static/app.07.js'),'utf8');
let nextTimer=0,calls=0,fail=0,renders=0,postFail=0;
const timers=new Map(),nodes={};
const host={isConnected:true,contains:()=>false,querySelectorAll:()=>[],querySelector:()=>null,insertAdjacentHTML(_,value){this.html=value+this.html},get innerHTML(){return this.html||''},set innerHTML(value){this.html=value;renders++;for(const id of ['pg-web-norm','pg-web-from','pg-web-to']){const match=value.match(new RegExp(`id="${id}"[^>]*value="([^"]*)"`));if(match)nodes[id]={value:match[1]};else delete nodes[id]}if(value.includes('pg-web-sync'))nodes['pg-web-sync']={textContent:'',className:''};else delete nodes['pg-web-sync']}};
const modal={open:true,scrollTop:0,events:{},addEventListener(name,fn){this.events[name]=fn}};nodes['web-purge-host']=host;nodes.modal=modal;nodes.mb={scrollTop:0};
let state={active:true,page:0,has_more:false,mode:'pending',session:{id:10,norm:10,date_from:'2026-10-01',date_to:'2026-10-07'},counts:{total:1,decided:0,blocked:0},items:[{user_id:2,username:'qa',msg_count:1,required_norm:10,days_in_chat:20,warns:0,decision_state:'idle'}]};
const context=vm.createContext({console,AbortController,BASE:'',hdrs:()=>({}),document:{hidden:false,activeElement:null,addEventListener(){}},el:id=>nodes[id],toast(){},crypto:{randomUUID:()=> 'qa'},setTimeout:(fn,ms)=>{const id=++nextTimer;timers.set(id,{fn,ms});return id},clearTimeout:id=>timers.delete(id),fetch:async(_,options={})=>{calls++;const status=options.method==='POST'?postFail:fail;if(status) return {ok:false,status,json:async()=>({detail:status===403?'Нет права проводить чистку.':'Нет связи.'})};return {ok:true,status:200,json:async()=>JSON.parse(JSON.stringify(state))}} });
vm.runInContext(source,context);
const load=quiet=>vm.runInContext(`purgeWebLoad(0,${quiet})`,context);
async function tick(){const t=[...timers.entries()].find(([,t])=>t.ms===2000);assert(t,'exactly one live refresh is scheduled');timers.delete(t[0]);await t[1].fn();}
(async()=>{
 vm.runInContext("_pgWeb.cid=-1;_pgWeb.chats=[{id:-1,title:'𝓒𝓾𝓼𝓽𝓸𝓶'}]",context);
 await load(false);const first=renders;assert.match(host.innerHTML,/qa/);
 await tick();assert.equal(renders,first,'unchanged live response preserves DOM, selection and scroll');
 state.items[0].verdict='warn';state.items[0].verdict_by=3;state.items[0].verdict_by_name='<admin>';state.counts.decided=1;
 await tick();assert.match(host.innerHTML,/Решение: Варн/);assert.match(host.innerHTML,/&lt;admin&gt;/);
 nodes['cf-sheet']={};const before=calls;await tick();assert.equal(calls,before,'confirmation pauses background replacement');delete nodes['cf-sheet'];
 nodes['pg-web-sync']={textContent:'',className:''};const saved=host.innerHTML;fail=503;await tick();assert.equal(host.innerHTML,saved,'offline keeps last dossiers');assert.match(nodes['pg-web-sync'].textContent,/Нет связи/);
 fail=403;await tick();assert.doesNotMatch(host.innerHTML,/qa|Решение/,'revoked access clears private dossiers');assert.equal(vm.runInContext('_pgWeb.state',context),null);assert(![...timers.values()].some(t=>t.ms===2000),'revoked access stops polling');
 fail=0;state={active:false,items:[],page:0,has_more:false};await load(false);const form=renders;await tick();assert.equal(renders,form,'polling never clears an edited start form');
 nodes['pg-web-norm'].value='321';nodes['pg-web-from'].value='2026-10-02';nodes['pg-web-to'].value='2026-10-09';
 postFail=503;await vm.runInContext("purgeWebPost('start',{})",context);assert.equal(nodes['pg-web-norm'].value,'321','failed start retains the chosen norm');assert.equal(nodes['pg-web-from'].value,'2026-10-02');assert.equal(nodes['pg-web-to'].value,'2026-10-09');postFail=0;
 const retained=host.innerHTML;fail=503;await tick();assert.equal(host.innerHTML,retained,'temporary permission outage retains data and keeps retrying');fail=0;
 // Native dialog.close retains its DOM. This is the real CM() lifecycle.
 modal.open=false;modal.events.close();assert(nodes['web-purge-host']===host && host.isConnected);assert(![...timers.values()].some(t=>t.ms===2000),'closing a retained dialog cancels refresh');
 const closedCalls=calls;await load(true);assert.equal(calls,closedCalls,'closed retained host cannot trigger a request');
 modal.open=true;await load(false);assert.equal(nodes['pg-web-norm'].value,'321','reopening retains the draft');
 console.log('PASS: live dossiers, stable DOM, confirmation pause, offline/temporary outage retention, revoked rights, failed-start draft, real dialog close and reopen');
})().catch(e=>{console.error(e);process.exitCode=1});
