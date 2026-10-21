const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function boot({restore=false,remaining=900,deferred=false}={}){
  let now=0,next=0;const timers=new Map(),events={},nodes=new Map(),intervals=new Set();
  class El{constructor(){this.textContent='';this.children=[];this.dataset={};this.style={setProperty(){}};this.disabled=false;this.classes=new Set(['hidden']);this.classList={add:x=>this.classes.add(x),remove:x=>this.classes.delete(x),toggle:(x,on)=>{if(on??!this.classes.has(x))this.classes.add(x);else this.classes.delete(x);}};}setAttribute(){}append(...x){this.children.push(...x)}replaceChildren(){this.children=[]}closest(){return this}querySelectorAll(){return []}}
  const get=id=>nodes.get(id)||(nodes.set(id,new El()),nodes.get(id));
  const runes=['left','center','right'].map(rune=>Object.assign(new El(),{dataset:{rune}}));
  const modes=[Object.assign(new El(),{dataset:{mode:'normal'}})];
  const document={body:{dataset:{appBase:'/app'}},hidden:false,getElementById:get,createElement:()=>new El(),addEventListener:(e,f)=>events[e]=f,querySelectorAll:q=>q==='[data-rune]'?runes:q==='[data-mode]'?modes:q==='#gifts button'?get('gifts').children:[]};
  const packet={run_id:'run',protocol:'resilient-local-v1',state:{status:'active',next_signal_no:1,health:5,score:0,combo:0,selected:[]}};
  const store={data:{active:restore?{packet,state:packet.state,journal:[],remaining}:null,outbox:[]},durable:true,save(){},fresh:async()=>packet,refreshRules:async()=>{},flush:async()=>{},queue(){}};
  const pending=[];
  class Engine{
    constructor(p,s=p.state){this.packet=p;this.state={...s};this.gift=false;this.hold=deferred;}
    window(){return 900}
    async view(){if(this.hold)await new Promise(r=>pending.push(r));return {...this.state,run_id:'run',rune:'left',gifts:[],perks:{},speed_percent:100,window_ms:900,chunk:1,draft:this.gift?{number:1,offers:[{id:'gift',name:'Дар',bonus:'Плюс',cost:'Минус'}]}:null}}
    step(rune){this.state.next_signal_no++;if(rune===null)this.state.health--}
    pick(){this.gift=false;this.state.selected.push('gift')}
  }
  const memory=new Map(),context=vm.createContext({document,window:{Telegram:{WebApp:{ready(){},expand(){}}},addEventListener:(e,f)=>events[e]=f},navigator:{onLine:true},location:{pathname:'/app/rhythm-v2',hash:''},URLSearchParams,performance:{now:()=>now},localStorage:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},PVLocal:{Store:function(){return store},Rhythm:Engine,request:async()=>({ok:true,json:async()=>({top:[]})})},fetch:async()=>({ok:true,json:async()=>null}),setTimeout:(f,d)=>{timers.set(++next,{f,due:now+d});return next},clearTimeout:id=>timers.delete(id),setInterval:(f,d)=>{timers.set(++next,{f,due:now+d,period:d});intervals.add(next);return next},clearInterval:id=>{timers.delete(id);intervals.delete(id)},console,Date,Number,Math});
  const file=path.join(__dirname,'../FastAPI/static/rhythm-v2.js');
  vm.runInContext(fs.readFileSync(file,'utf8').replace(/\}\)\(\);\s*$/,'globalThis.rhythmTest={engine:()=>engine,journal:()=>journal,pause,localDraw,pickGift,start,cancel};})();'),context);
  const settle=async()=>{for(let i=0;i<50;i++)await Promise.resolve()};
  async function advance(ms){await settle();const end=now+ms;for(;;){const due=[...timers].filter(([,t])=>t.due<=end).sort((a,b)=>a[1].due-b[1].due)[0];if(!due)break;const [id,t]=due;now=t.due;timers.delete(id);if(t.period)timers.set(id,{...t,due:now+t.period});t.f();await settle();}now=end;await settle()}
  return {get,runes,modes,document,events,m:context.rhythmTest,store,advance,settle,pending,intervals};
}
const noTarget=h=>{assert(!h.get('instruction').textContent.includes('ᚠ'));assert(h.runes.every(b=>b.disabled));assert.equal(h.m.journal().filter(a=>a.kind==='tap').length,0)};
(async()=>{
  const h=boot();await h.settle();h.modes[0].onclick();await h.settle();
  assert(!h.get('run').classes.has('hidden'));noTarget(h);assert.match(h.get('instruction').textContent,/4/);
  await h.advance(3999);noTarget(h);assert.equal(h.m.engine().state.health,5);
  await h.advance(1);assert.match(h.get('instruction').textContent,/ᚠ/);assert(h.runes.every(b=>!b.disabled));
  h.m.engine().gift=true;await h.m.localDraw();h.get('gifts').children[0].onclick();await h.settle();
  await h.advance(3999);noTarget(h);await h.advance(1);assert.match(h.get('instruction').textContent,/ᚠ/);
  const restored=boot({restore:true,remaining:50});await restored.settle();noTarget(restored);
  restored.get('resume-run').onclick();restored.get('resume-run').onclick();await restored.advance(3900);noTarget(restored);
  restored.document.hidden=true;restored.events.visibilitychange();await restored.settle();await restored.advance(5000);noTarget(restored);
  restored.document.hidden=false;restored.events.visibilitychange();restored.get('resume-run').onclick();await restored.advance(3999);noTarget(restored);
  await restored.advance(1);assert.match(restored.get('instruction').textContent,/ᚠ/);await restored.advance(800);assert.equal(restored.m.engine().state.health,5,'resume starts a full reaction window');
  const cancelled=boot();cancelled.modes[0].onclick();await cancelled.advance(1000);await cancelled.m.cancel();await cancelled.advance(10000);assert(!cancelled.get('intro').classes.has('hidden'));assert(cancelled.get('run').classes.has('hidden'));
  const race=boot({restore:true,deferred:true});await race.settle();race.document.hidden=true;race.events.visibilitychange();await race.m.cancel();race.pending.forEach(r=>r());await race.settle();assert(race.get('run').classes.has('hidden'));
  console.log('OK: Rhythm start/gift/resume wait4s without target, frozen hearts, duplicate resume, hidden restart, cancel/stale view');
})().catch(e=>{console.error(e);process.exitCode=1});
