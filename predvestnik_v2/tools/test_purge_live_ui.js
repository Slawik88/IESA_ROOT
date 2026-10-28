// Execute the production purge page (app.07.js, S05) with live events, ETag, response loss and background start.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../FastAPI/static/app.07.js'),'utf8');
let nextTimer=0,renders=0,fail=0,postFail=0,postStatus=200;
const timers=new Map(),nodes={},requests=[],toasts=[];
const page={isConnected:true,get innerHTML(){return this.html||''},set innerHTML(value){this.html=value;renders++;
  for(const id of ['pg-norm','pg-from','pg-to']){const match=value.match(new RegExp(`id="${id}"[^>]*value="([^"]*)"`));if(match)nodes[id]={value:match[1]};else delete nodes[id]}}};
nodes['pg-purge']=page;nodes.modal={open:false};
const views={};
const active=(sent,decided=0)=>({active:true,page:0,has_more:false,mode:'pending',dossiers_running:sent<2,preparing:null,
  session:{id:10,norm:10,date_from:'2026-10-01',date_to:'2026-10-07'},counts:{total:2,sent,decided,blocked:0},
  items:[{user_id:2,username:'qa',member_tag:'<b>Тег</b>',msg_count:1,required_norm:10,days_in_chat:20,warns:0,decision_state:'idle'},
         {user_id:3,username:'quiet',msg_count:0,required_norm:10,days_in_chat:9,warns:1,decision_state:'idle',verdict:decided?'warn':null}]});
const idle={active:false,items:[],page:0,has_more:false,completed:null,preparing:null,defaults:{date_from:'2026-10-01',date_to:'2026-10-07',today:'2026-10-09'}};
views[-1]=active(1);views[-2]=idle;
let etag='"v1"',unchanged=false;
const ctx=vm.createContext({console,AbortController,BASE:'',hdrs:()=>({}),_activePage:'more',_navStack:[],
  document:{hidden:false,scrollingElement:{scrollTop:0},addEventListener(){}},el:id=>nodes[id],
  toast:(m)=>toasts.push(m),fmt:n=>String(n),esc:s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'),
  v3Head:(t,o)=>`<header><button onclick="${o.back}">‹</button><h1>${t}</h1></header>`,_v3Icon:()=>'›',
  OM:()=>{},CM:()=>{},v3Confirm:async()=>true,handleAuthRefusal(){},
  localStorage:{s:{},getItem(k){return this.s[k]??null},setItem(k,v){this.s[k]=v},removeItem(k){delete this.s[k]}},
  crypto:{randomUUID:()=>'qa-id'},
  setTimeout:(fn,ms)=>{const id=++nextTimer;timers.set(id,{fn,ms});return id},clearTimeout:id=>timers.delete(id),
  fetch:async(url,options={})=>{requests.push([options.method||'GET',url,options.headers||{}]);
    if(options.method==='POST'){if(postFail)return {ok:false,status:postFail,json:async()=>({detail:'Нет связи.'}),headers:{get:()=>''}};
      const cid=Number(url.split('/')[3]);
      if(url.includes('/start?background=1')){views[cid]={...idle,preparing:{state:'preparing',norm:50,date_from:'2026-10-02',date_to:'2026-10-08'}};
        return {ok:true,status:202,json:async()=>({ok:true,accepted:true,job:{state:'preparing'}}),headers:{get:()=>''}}}
      return {ok:true,status:200,json:async()=>({ok:true}),headers:{get:()=>''}}}
    if(url.startsWith('/purge-v1/chats?')||url==='/purge-v1/chats')return {ok:true,status:200,json:async()=>({items:[{id:-1,title:'Первый'},{id:-2,title:'Второй'}],next_offset:null}),headers:{get:()=>''}};
    if(fail)return {ok:false,status:fail,json:async()=>({detail:fail===403?'Нет права проводить чистку.':'Нет связи.'}),headers:{get:()=>''}};
    if(unchanged&&options.headers?.['If-None-Match']===etag)return {ok:false,status:304,json:async()=>({}),headers:{get:()=>etag}};
    const cid=Number(url.split('/')[3].split('?')[0]);
    return {ok:true,status:200,json:async()=>JSON.parse(JSON.stringify(views[cid])),headers:{get:k=>k==='etag'?etag:''}}},
});
ctx.switchPage=name=>{ctx._activePage=name};ctx.navBack=()=>{ctx._activePage=ctx._navStack.pop()};
vm.runInContext(source,ctx);
const run=code=>vm.runInContext(code,ctx);
const fallback=()=>[...timers.values()].filter(t=>t.ms===15000);
(async()=>{
 await run('openPurgeHub(-1)');
 assert.equal(ctx._activePage,'purge');assert.match(page.innerHTML,/Отправляю досье: 1 из 2/);assert.match(page.innerHTML,/&lt;b&gt;Тег/,'tags are text, not markup');
 assert(requests.some(r=>r[1].startsWith('/purge-v1/chats/-1?live=1')),'the page subscribes to live events');
 assert.equal(fallback().length,1,'exactly one fallback refresh, every 15 s');
 // A live event for this chat refreshes; an unchanged answer (304) keeps the DOM.
 unchanged=true;let before=renders,count=requests.length;await run('purgeLive({chat_id:-1})');
 assert.equal(requests.length,count+1);assert.equal(requests.at(-1)[2]['If-None-Match'],etag);assert.equal(renders,before,'304 keeps DOM, focus and scroll');
 count=requests.length;await run('purgeLive({chat_id:-99})');assert.equal(requests.length,count,'events of another chat are ignored');
 unchanged=false;views[-1]=active(2,1);etag='"v2"';await run('purgeLive({chat_id:-1})');
 assert.match(page.innerHTML,/Решено 1 из 2/);assert.doesNotMatch(page.innerHTML,/Отправляю/);
 // Offline: the last dossiers stay, with a note.
 fail=503;await run('purgeLoad(true)');assert.match(page.innerHTML,/Решено 1 из 2/);assert.match(page.innerHTML,/Нет связи\. Показано последнее/);
 // Revoked rights clear private dossiers and stop refreshing.
 fail=403;await run('purgeLoad(true)');assert.doesNotMatch(page.innerHTML,/qa|quiet|Решено/);assert.match(page.innerHTML,/Нет доступа/);assert.equal(fallback().length,0,'revoked access stops refreshing');
 fail=0;
 // Start form: a failed start keeps the typed draft, a background start shows «Готовлю список».
 await run('purgePick(-2)');assert.match(page.innerHTML,/Начать чистку/);
 nodes['pg-norm'].value='50';nodes['pg-from'].value='2026-10-02';nodes['pg-to'].value='2026-10-08';
 postFail=503;await run('purgeStart(null)');assert.equal(nodes['pg-norm'].value,'50','failed start keeps the norm');assert.equal(nodes['pg-from'].value,'2026-10-02');assert(toasts.includes('Нет связи.'));
 const key='pv-purge-start:-2:50:2026-10-02:2026-10-08';assert.equal(ctx.localStorage.getItem(key),'qa-id','the retry reuses the same start id');
 postFail=0;await run('purgeStart(null)');
 assert(requests.some(r=>r[0]==='POST'&&r[1]==='/purge-v1/chats/-2/start?background=1'),'the new page starts in the background');
 assert.match(page.innerHTML,/Готовлю список/);assert.equal(ctx.localStorage.getItem(key),null,'an accepted start forgets its id');
 // Back leaves the page and stops refreshing.
 await run('purgeBack()');assert.equal(ctx._activePage,'more');assert.equal(fallback().length,0,'leaving the page cancels refresh');
 count=requests.length;await run('purgeLive({chat_id:-2})');assert.equal(requests.length,count,'a hidden page does not refresh');
 console.log('PASS: live subscription, 304 keeps DOM, other chats ignored, offline retention, revoked rights, draft kept on failed start, background start, back');
})().catch(e=>{console.error(e);process.exitCode=1});
