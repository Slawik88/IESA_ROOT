// Execute the production client against controlled responses, including races.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const raw=fs.readFileSync(path.join(__dirname,'../FastAPI/static/minesweeper-v2.js'),'utf8');
const source=raw.replace(/\}\)\(\);\s*$/, 'globalThis.testMines={sync,render,refreshLeaderboard};})();');
const tick=async()=>{for(let i=0;i<40;i++)await Promise.resolve();};
const state=(extra={})=>({run_id:'run-1',status:'active',revision:3,size:6,mine_count:5,label:'Лёгкий',flags_left:5,revealed:[],changed:[],flags:[],mines:[],...extra});
const response=data=>({ok:true,json:async()=>data});
function boot({blockedStorage=false}={}){
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
  const requests=[],net={action:null,current:state(),start:state(),leader:null};let stopped=0,ids=0;
  const ctx=vm.createContext({document,window:{Telegram:{WebApp:{initData:'telegram-proof',ready(){},expand(){}}}},location:{pathname:'/app/minesweeper'},
    localStorage:{getItem(){if(blockedStorage)throw Error('SecurityError');return 'session-proof';}},crypto:{randomUUID:()=>`action-${++ids}`},
    Date,Map,Set,Math,Number,String,Boolean,JSON,console,setInterval:()=>1,clearInterval(){stopped++;},setTimeout:()=>1,clearTimeout(){},
    fetch:async(url,opts={})=>{requests.push({url,opts});if(url.includes('/skins-'))return response(null);
      if(url.includes('/leaderboard/'))return response(net.leader?await net.leader(url):{top:[]});
      if(url.endsWith('/actions'))return response(net.action?await net.action(url,opts):state({revision:4}));
      if(url.endsWith('/runs'))return response(net.start);
      return response(net.current);
    }});
  vm.runInContext(source,ctx);
  return {ctx,m:ctx.testMines,get,modes,difficulties,requests,net,cells:()=>get('mine-board').querySelectorAll(),stopped:()=>stopped};
}
const allText=e=>e.textContent+' '+e.children.map(allText).join(' ');
async function main(){
  const first=boot({blockedStorage:true});await tick();
  assert.equal(first.cells().length,36,'storage denial does not prevent the game from loading');
  assert.equal(first.requests.find(r=>r.url.endsWith('/runs')).opts.headers['x-init-data'],'telegram-proof');
  first.m.sync(state({status:'awaiting_first_open',revision:0}));first.m.render();first.modes[1].onclick();
  first.cells()[0].onclick();await tick();
  assert.equal(JSON.parse(first.requests.find(r=>r.url.endsWith('/actions')).opts.body).kind,'open','first flag-mode tap is a safe open');
  first.cells()[1].onclick();await tick();
  assert.equal(JSON.parse(first.requests.filter(r=>r.url.endsWith('/actions')).at(-1).opts.body).kind,'toggle_flag');

  const cancelled=boot();await tick();cancelled.net.action=()=>{throw Error('connection lost');};
  cancelled.net.current=state({status:'cancelled'});cancelled.cells()[0].onclick();await tick();
  assert.equal(cancelled.get('mine-status').textContent,'Партия закрыта');
  assert.match(cancelled.get('mine-hint').textContent,/партия заменена новой/i);
  assert.equal(cancelled.get('new-game').textContent,'Новая партия','cancelled even at the same revision clears uncertain action');
  assert.ok(cancelled.cells().every(c=>c.disabled));assert.ok(cancelled.stopped()>0);
  cancelled.get('new-game').onclick();await tick();assert.ok(cancelled.cells().every(c=>!c.disabled));

  const lost=boot();await tick();let failed=true;
  lost.net.action=()=>{if(failed)throw Error('lost');return state({revision:4});};
  lost.cells()[0].onclick();await tick();assert.equal(lost.get('new-game').textContent,'Восстановить ход');
  failed=false;lost.get('new-game').onclick();await tick();
  const attempts=lost.requests.filter(r=>r.url.endsWith('/actions')).map(r=>JSON.parse(r.opts.body));
  assert.equal(attempts.length,2);assert.deepEqual(attempts[0],attempts[1],'an uncertain request keeps its identity');

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
