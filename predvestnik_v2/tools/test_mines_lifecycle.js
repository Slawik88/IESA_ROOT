// Execute the production client against controlled responses, including races.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const raw=fs.readFileSync(path.join(__dirname,'../FastAPI/static/minesweeper-v2.js'),'utf8');
const source=raw.replace(/\}\)\(\);\s*$/, 'globalThis.testMines={sync,render,refreshLeaderboard,updateClock};})();');
const tick=async()=>{for(let i=0;i<40;i++)await Promise.resolve();};
const state=(extra={})=>({run_id:'run-1',status:'active',revision:3,size:6,mine_count:5,label:'Лёгкий',flags_left:5,revealed:[],changed:[],flags:[],mines:[],...extra});
const response=data=>({ok:true,json:async()=>data});
function boot({blockedStorage=false,startState=state()}={}){
  let document;
  class El{
    constructor(){this.children=[];this.attrs={};this.dataset={};this.listeners={};this.style={setProperty(){}};this.textContent='';}
    setAttribute(k,v){this.attrs[k]=String(v);} append(...xs){this.children.push(...xs);} replaceChildren(){this.children=[];}
    addEventListener(k,f){this.listeners[k]=f;} contains(n){return n===this||this.children.some(c=>c.contains(n));}
    querySelectorAll(){return this.children.flatMap(c=>c.dataset.cell!==undefined?[c]:c.querySelectorAll());}
    querySelector(q){return this.querySelectorAll().find(c=>String(c.dataset.cell)===q.match(/data-cell="(\d+)"/)?.[1]);}
    focus(){document.activeElement=this;this.listeners.focus?.();}
  }
  const nodes=new Map(),get=id=>nodes.get(id)||(nodes.set(id,new El()),nodes.get(id));
  const modes=['open','flag'].map(mode=>Object.assign(new El(),{dataset:{mode}}));
  const difficulties=['easy','normal','hard'].map(difficulty=>Object.assign(new El(),{dataset:{difficulty}}));
  document={body:{dataset:{appBase:'/app'}},activeElement:null,getElementById:get,createElement:()=>new El(),querySelectorAll:q=>q.includes('data-mode')?modes:q.includes('data-difficulty')?difficulties:[]};
  const timers=new Map();let timerId=0;
  const requests=[],net={action:null,current:state(),start:startState,leader:null,mono:100,wall:1000};let stopped=0,ids=0;
  const ctx=vm.createContext({document,window:{Telegram:{WebApp:{initData:'telegram-proof',ready(){},expand(){}}}},location:{pathname:'/app/minesweeper'},
    localStorage:{getItem(){if(blockedStorage)throw Error('SecurityError');return 'session-proof';}},crypto:{randomUUID:()=>`action-${++ids}`},
    Date:class extends Date{static now(){return net.wall;}},performance:{now:()=>net.mono},Map,Set,Math,Number,String,Boolean,JSON,console,setInterval:()=>1,clearInterval(){stopped++;},setTimeout:f=>{timers.set(++timerId,f);return timerId;},clearTimeout:id=>timers.delete(id),
    fetch:async(url,opts={})=>{requests.push({url,opts});if(url.includes('/skins-'))return response(null);
      if(url.includes('/leaderboard/'))return response(net.leader?await net.leader(url):{top:[]});
      if(url.endsWith('/actions'))return response(net.action?await net.action(url,opts):state({revision:4}));
      if(url.endsWith('/runs'))return response(net.start);
      return response(typeof net.current==='function'?await net.current():net.current);
    }});
  vm.runInContext(source,ctx);
  return {ctx,m:ctx.testMines,get,modes,difficulties,requests,net,cells:()=>get('mine-board').querySelectorAll(),stopped:()=>stopped,runTimers:()=>{const pending=[...timers.values()];timers.clear();pending.forEach(f=>f());}};
}
const allText=e=>e.textContent+' '+e.children.map(allText).join(' ');
async function main(){
  const first=boot({blockedStorage:true});await tick();
  assert.equal(first.cells().length,36,'storage denial does not prevent the game from loading');
  assert.equal(first.requests.find(r=>r.url.endsWith('/runs')).opts.headers['x-init-data'],'telegram-proof');
  assert.equal(JSON.parse(first.requests.find(r=>r.url.endsWith('/runs')).opts.body).resume_existing,true);
  first.m.sync(state({status:'awaiting_first_open',revision:0}));first.m.render();first.modes[1].onclick();
  first.cells()[0].onclick();await tick();
  assert.equal(JSON.parse(first.requests.find(r=>r.url.endsWith('/actions')).opts.body).kind,'open','first flag-mode tap is a safe open');
  first.cells()[1].onclick();await tick();
  assert.equal(JSON.parse(first.requests.filter(r=>r.url.endsWith('/actions')).at(-1).opts.body).kind,'toggle_flag');

  let contextPrevented=false;
  first.cells()[2].listeners.contextmenu({preventDefault(){contextPrevented=true;}});await tick();
  assert.ok(contextPrevented);
  assert.equal(JSON.parse(first.requests.filter(r=>r.url.endsWith('/actions')).at(-1).opts.body).kind,'toggle_flag');

  first.get('mine-view-toggle').onclick();assert.equal(first.ctx.document.body.dataset.mineZoom,'large');
  first.get('mine-view-toggle').onclick();assert.equal(first.ctx.document.body.dataset.mineZoom,'fit');
  first.m.sync(state({status:'lost',revealed:[7],changed:[{cell:7,adjacent:1}],flags:[0,1,8],mines:[0]}));first.m.render();
  assert.equal(first.cells()[7].textContent,1);
  assert.equal(first.cells()[0].textContent,'✹','confirmed mine replaces the guess flag');
  assert.equal(first.cells()[1].textContent,'×');assert.equal(first.cells()[8].textContent,'×');
  assert.match(first.cells()[1].attrs['aria-label'],/мины нет/);
  assert.equal(first.get('mines-left').textContent,5,'total mines is independent of guessed flags');

  const keyboard=boot();await tick();
  for(const key of ['f','F10','ContextMenu']){
    let prevented=false;keyboard.cells()[0].listeners.keydown({key,shiftKey:true,preventDefault(){prevented=true;}});await tick();assert.ok(prevented);
  }
  assert.equal(keyboard.requests.filter(r=>r.url.endsWith('/actions')).length,3,'every keyboard flag gesture works independently');

  for(const touch of [false,true]){
    const gesture=boot();await tick();const cell=gesture.cells()[0];
    cell.listeners.pointerdown({button:touch?0:2,pointerType:touch?'touch':'mouse',clientX:1,clientY:1});
    if(touch){gesture.runTimers();await tick();}
    cell.listeners.contextmenu({preventDefault(){}});await tick();gesture.runTimers();await tick();
    assert.equal(gesture.requests.filter(r=>r.url.endsWith('/actions')).length,1,'right-click and touch contextmenu never duplicate the flag');
  }

  const malformed=boot();await tick();
  for(const bad of [{},state({revealed:[1],changed:[]}),state({changed:[{cell:1,adjacent:9}]}),state({revealed:[81]})]){
    assert.throws(()=>malformed.m.sync(bad),/неполное поле/);
    malformed.m.render();assert.equal(malformed.cells().length,36,'invalid data never replaces the current board');
  }
  malformed.m.sync(state({run_id:'new-run',revealed:[1],changed:[{cell:1,adjacent:2}]}));malformed.m.render();
  assert.equal(malformed.cells()[1].textContent,2);

  const pan=boot();await tick();const panCell=pan.cells()[0];
  panCell.listeners.pointerdown({button:0,clientX:10,clientY:10});
  panCell.listeners.pointermove({clientX:40,clientY:10});panCell.listeners.pointercancel();
  panCell.listeners.contextmenu({preventDefault(){}});pan.runTimers();panCell.onclick({detail:1});await tick();
  assert.equal(pan.requests.filter(r=>r.url.endsWith('/actions')).length,0,'cancelled pan cannot become a flag or click');
  panCell.onclick({detail:0});await tick();
  assert.equal(pan.requests.filter(r=>r.url.endsWith('/actions')).length,1,'keyboard click still works after a cancelled pan');

  const reconnect=boot({startState:{}});await tick();
  assert.equal(reconnect.get('new-game').textContent,'Повторить подключение');
  reconnect.net.start=state();reconnect.get('new-game').onclick();await tick();
  assert.ok(reconnect.requests.filter(r=>r.url.endsWith('/runs')).every(r=>JSON.parse(r.opts.body).resume_existing),'reconnection cannot silently cancel an existing run');

  const cancelled=boot();await tick();cancelled.net.action=()=>{throw Error('connection lost');};
  cancelled.net.current=state({status:'cancelled'});cancelled.cells()[0].onclick();await tick();
  assert.equal(cancelled.get('mine-status').textContent,'Партия закрыта');
  assert.match(cancelled.get('mine-hint').textContent,/партия заменена новой/i);
  assert.equal(cancelled.get('new-game').textContent,'Новая партия','cancelled even at the same revision clears uncertain action');
  assert.ok(cancelled.cells().every(c=>c.disabled));assert.ok(cancelled.stopped()>0);
  cancelled.get('new-game').onclick();await tick();assert.ok(cancelled.cells().every(c=>!c.disabled));

  const resumed=boot({startState:state({difficulty:'hard',label:'Сложный',elapsed_ms:2000})});await tick();
  assert.equal(resumed.difficulties[2].attrs['aria-selected'],'true');
  resumed.net.wall+=3600000;resumed.net.mono+=1000;resumed.m.updateClock();
  assert.equal(resumed.get('timer').textContent,'0:03','device wall-clock jump does not change elapsed time');
  resumed.get('new-game').onclick();await tick();
  assert.equal(JSON.parse(resumed.requests.filter(r=>r.url.endsWith('/runs')).at(-1).opts.body).resume_existing,false);

  const lost=boot();await tick();let failed=true;
  lost.net.action=()=>{if(failed)throw Error('lost');return state({revision:4});};
  lost.cells()[0].onclick();await tick();assert.equal(lost.get('new-game').textContent,'Восстановить ход');
  failed=false;lost.get('new-game').onclick();await tick();
  const attempts=lost.requests.filter(r=>r.url.endsWith('/actions')).map(r=>JSON.parse(r.opts.body));
  assert.equal(attempts.length,2);assert.deepEqual(attempts[0],attempts[1],'an uncertain request keeps its identity');

  for(const malformedReply of [false,true]){
    const recovery=boot();await tick();let online=false;
    recovery.net.action=()=>{if(!online){if(malformedReply)return {};throw Error('lost response');}return state({revision:4,idempotent_replay:true});};
    recovery.net.current=()=>{if(!online)throw Error('read failed');return state({revision:6,flags:[1],revealed:[2],changed:[{cell:2,adjacent:2}]});};
    recovery.cells()[0].onclick();await tick();
    assert.equal(recovery.get('new-game').textContent,'Восстановить ход','unvalidated response does not discard action identity');
    online=true;recovery.get('new-game').onclick();await tick();
    assert.equal(recovery.cells()[1].textContent,'⚑');assert.equal(recovery.cells()[2].textContent,2,'replay reads current authority instead of stale snapshot');
    const posts=recovery.requests.filter(r=>r.url.endsWith('/actions'));
    assert.deepEqual(JSON.parse(posts[0].opts.body),JSON.parse(posts[1].opts.body));
  }

  for(const rejectOld of [false,true]){
    const race=boot();await tick();let resolveOld,reject;
    race.net.leader=url=>url.endsWith('/normal')?new Promise((yes,no)=>{resolveOld=yes;reject=no;}):Promise.resolve({top:[{place:1,player:{display_name:'HARD'},best_elapsed_ms:1234}]});
    const pending=race.m.refreshLeaderboard();await tick();
    race.difficulties[2].onclick();await tick();
    assert.match(allText(race.get('leaderboard-list')),/HARD/);
    if(rejectOld)reject(Error('old failure'));else resolveOld({top:[{place:1,player:{display_name:'NORMAL'},best_elapsed_ms:9}]});
    await pending;await tick();
    assert.match(allText(race.get('leaderboard-list')),/HARD/);
    assert.equal(race.get('leaderboard-difficulty').textContent,'Сложный');
  }
  console.log('Mines lifecycle: cancelled recovery, flag-first move, storage denial, stable retry and leaderboard races OK');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
