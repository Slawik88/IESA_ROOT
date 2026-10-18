// Grid behaviour against the actual Mines script, without network or a real account.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
class El {
 constructor(){this.children=[];this.attrs={};this.dataset={};this.listeners={};this.style={setProperty(){}};this.textContent='';}
 setAttribute(k,v){this.attrs[k]=String(v);} append(...xs){this.children.push(...xs);} replaceChildren(){this.children=[];}
 addEventListener(k,f){this.listeners[k]=f;} contains(n){return n===this||this.children.some(c=>c.contains(n));}
 querySelectorAll(){return this.children.flatMap(c=>c.dataset.cell!==undefined?[c]:c.querySelectorAll());}
 querySelector(q){const m=q.match(/data-cell="(\d+)"/);return this.querySelectorAll().find(x=>String(x.dataset.cell)===m?.[1]);}
 focus(){document.activeElement=this;this.listeners.focus?.();}
}
const nodes=new Map(),get=id=>nodes.get(id)||(nodes.set(id,new El()),nodes.get(id));
const document={body:{dataset:{appBase:'/predvestnik'}},activeElement:null,getElementById:get,createElement:()=>new El(),querySelectorAll:()=>[]};
let failStart=false,actions=0,revision=0,delayed;
const state=()=>({run_id:'test',status:'active',revision:revision++,size:9,mine_count:10,label:'Обычный',flags_left:10,revealed:[],changed:[],flags:[],mines:[]});
const ctx=vm.createContext({document,window:{},location:{pathname:'/predvestnik/minesweeper'},localStorage:{getItem:()=>''},crypto:{randomUUID:()=> 'same-id'},Date,performance:{now:()=>100},Map,Set,Math,Number,String,Boolean,JSON,
 setInterval:()=>1,clearInterval(){},setTimeout:f=>{delayed=f;return 1;},clearTimeout:()=>{delayed=null;},
 fetch:async url=>{if(url.endsWith('/runs')&&failStart)throw new Error('offline');if(url.endsWith('/actions'))actions++;const data=url.includes('/leaderboard/')?{top:[]}:state();return {ok:true,json:async()=>data};},console});
const tick=async()=>{for(let i=0;i<15;i++)await Promise.resolve();};
async function main(){
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../FastAPI/static/minesweeper-v2.js'),'utf8'),ctx);await tick();
 const board=get('mine-board'),cells=()=>board.querySelectorAll();
 assert.equal(cells().length,81);assert.equal(cells().filter(x=>x.tabIndex===0).length,1);
 assert.match(cells()[0].attrs['aria-label'],/Строка 1, столбец 1/);
 cells()[0].focus();let prevented=false;cells()[0].listeners.keydown({key:'ArrowDown',preventDefault(){prevented=true;}});
 assert(prevented);assert.equal(document.activeElement.dataset.cell,9);assert.equal(actions,0);
 document.activeElement.listeners.keydown({key:'End',preventDefault(){}});assert.equal(document.activeElement.dataset.cell,17);
 document.activeElement.onclick();await tick();assert.equal(actions,1);assert.equal(document.activeElement.dataset.cell,17);
 assert.equal(cells().filter(x=>x.tabIndex===0).length,1);
 const button=cells()[18];button.listeners.pointerdown({clientX:1,clientY:1});button.listeners.pointermove({clientX:30,clientY:1});assert.equal(delayed,null);button.onclick();await tick();assert.equal(actions,1,'scroll gesture must not open a cell');
 failStart=true;get('new-game').onclick();await tick();assert.match(get('mine-hint').textContent,/offline/);assert.equal(get('mine-status').textContent,'Поле недоступно');
 console.log('OK: Mines roving focus, coordinates, arrow navigation, focus restoration, scroll cancellation and retry error');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
