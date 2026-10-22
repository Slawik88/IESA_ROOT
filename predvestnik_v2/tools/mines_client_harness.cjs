const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
module.exports=function boot({blockedStorage=false,status='active',size=9,restored=false,slowGame=false}={}){
  let document;const events={};
  class El{
    constructor(){this.children=[];this.attrs={};this.dataset={};this.listeners={};this.style={setProperty(){}};this.textContent='';}
    setAttribute(k,v){this.attrs[k]=String(v);}append(...xs){this.children.push(...xs);}replaceChildren(){this.children=[];}
    addEventListener(k,f){this.listeners[k]=f;}contains(n){return n===this||this.children.some(c=>c.contains(n));}
    querySelectorAll(){return this.children.flatMap(c=>c.dataset.cell!==undefined?[c]:c.querySelectorAll());}
    querySelector(q){return this.querySelectorAll().find(c=>String(c.dataset.cell)===q.match(/data-cell="(\d+)"/)?.[1]);}
    focus(){document.activeElement=this;this.listeners.focus?.();}
  }
  const nodes=new Map(),get=id=>nodes.get(id)||(nodes.set(id,new El()),nodes.get(id));
  const modes=['open','flag'].map(mode=>Object.assign(new El(),{dataset:{mode}}));
  const difficulties=['easy','normal','hard'].map(difficulty=>Object.assign(new El(),{dataset:{difficulty}}));
  document={body:{dataset:{appBase:'/app'}},activeElement:null,getElementById:get,createElement:()=>new El(),addEventListener:(k,f)=>events[k]=f,querySelectorAll:q=>q.includes('data-mode')?modes:q.includes('data-difficulty')?difficulties:[]};
  const timers=new Map(),memory=new Map();let nextTimer=0;
  const state={run_id:'fixture',status,revision:0,size,mine_count:6,label:'Лёгкий',difficulty:'easy',ruleset_version:'minesweeper-v1',opened_actions:0,revealed:[],changed:[],flags:[],mines:[],elapsed_ms:0};
  const packet={protocol:'resilient-local-v1',state,first_cell:status==='active'?0:null,layouts:Object.fromEntries(Array.from({length:size*size},(_,c)=>[c,[2,3,4,5,6,7]])),run_id:'fixture',seed:'00'.repeat(32)};
  const requests=[],net={offline:false,leader:null,mono:100};
  const response=data=>({ok:true,json:async()=>data});
  const context=vm.createContext({document,window:{Telegram:{WebApp:{initData:'telegram-proof',ready(){},expand(){}}},addEventListener(){}},navigator:{onLine:true},location:{pathname:'/app/minesweeper'},
    localStorage:{getItem(k){if(blockedStorage)throw Error('SecurityError');return memory.get(k)||(restored&&k.startsWith('pv-local-v1:')?JSON.stringify({active:{packet,state,first:packet.first_cell,journal:[]},outbox:[]}):null);},setItem(k,v){if(blockedStorage)throw Error('SecurityError');memory.set(k,v);},removeItem:k=>memory.delete(k)},
    crypto:require('node:crypto').webcrypto,TextEncoder,Uint8Array,DataView,BigInt,AbortSignal,AbortController,Date,performance:{now:()=>net.mono},console,
    setInterval:()=>1,clearInterval(){},setTimeout:f=>{timers.set(++nextTimer,f);return nextTimer;},clearTimeout:id=>timers.delete(id),
    fetch:async(url,opts={})=>{requests.push({url,opts});if(net.offline)throw Error('offline');if(url.includes('/skins-'))return response(null);if(url.includes('/leaderboard/'))return response(net.leader?await net.leader(url):{top:[]});if(slowGame&&url.endsWith('/runs'))return new Promise(()=>{});if(url.endsWith('/local-packet'))return response(packet);return response(state);}});
  const staticDir=path.join(__dirname,'../FastAPI/static');
  vm.runInContext(fs.readFileSync(path.join(staticDir,'local-games-v1.js'),'utf8'),context);context.PVLocal=context.window.PVLocal;
  const source=fs.readFileSync(path.join(staticDir,'minesweeper-v2.js'),'utf8').replace(/\}\)\(\);\s*$/,'globalThis.testMines={sync,render,refreshLeaderboard,updateClock,journal:()=>journal,engine:()=>engine,store:()=>store};})();');
  vm.runInContext(source,context);
  return {ctx:context,m:context.testMines,events,get,modes,difficulties,requests,net,cells:()=>get('mine-board').querySelectorAll(),runTimers:()=>{const pending=[...timers.values()];timers.clear();pending.forEach(f=>f());},tick:async()=>{for(let i=0;i<100;i++)await Promise.resolve();}};
};
