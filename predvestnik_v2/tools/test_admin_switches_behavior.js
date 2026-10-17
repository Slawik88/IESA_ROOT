// Render and exercise the real switch handlers without changing any server flags.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../FastAPI/static/bot-admin/admin.js'),'utf8');
const fn=source.match(/^async function switchesView\([\s\S]*?^\}/m)[0];
const esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
let data,requests=[],confirmResult=true,failWrite=false,inputs=[];
const nodes={sglobal:{},schatq:{},schatfound:{innerHTML:''},sreason:{value:'Тест'}};
const main={
  html:'',
  set innerHTML(value){this.html=value;inputs=[...value.matchAll(/<input[^>]*data-sw="([^"]+)"[^>]*>/g)].map(m=>({
    dataset:{sw:m[1]},checked:/\schecked\b/.test(m[0]),disabled:/\sdisabled\b/.test(m[0]),
    html:m[0],addEventListener:()=>{},
  }));},
  get innerHTML(){return this.html;},
  querySelectorAll: selector=>selector==='[data-sw]'?inputs:[],
};
const ctx=vm.createContext({
  esc,loadSectionData:async()=>data,$:s=>nodes[s.slice(1)],setTimeout,clearTimeout,
  toast:()=>{},confirm:()=>confirmResult,
  api:async(p,opts)=>{requests.push([p,JSON.parse(opts.body)]);if(failWrite)throw new Error('offline');return {};},
});
vm.runInContext(fn,ctx);
const view=chat=>ctx.switchesView(main,chat);
function fixture(global={},chat={}){data={state:{global,chat},catalog:[{title:'Чат-бот',scope:'bot',items:[{key:'all',title:'Весь бот',hint:'Бот молчит на все команды'}]},{title:'Сайт',scope:'site',items:[{key:'site',title:'Весь сайт',hint:'Мини-приложение отвечает «временно закрыто»'}]}]};requests=[];}
async function run(){
  fixture();await view(null);
  assert.match(main.html,/Бот работает/);assert.match(main.html,/Сайт открыт/);
  assert.doesNotMatch(main.html,/Бот молчит/);
  assert(inputs.every(i=>i.checked&&/aria-label="[^\"]+везде"/.test(i.html)));
  assert.equal(requests.length,0,'rendering must never write');
  fixture({all:{reason:'Ремонт'}});await view({id:42,title:'Чат «A»'});
  assert.match(main.html,/Бот выключен/);assert.match(main.html,/выключено везде/);
  assert.match(inputs[0].html,/disabled/);assert(!inputs[0].checked);
  assert.match(inputs[0].html,/в чате/);assert.doesNotMatch(main.html,/Весь сайт/);
  fixture();await view(null);let input=inputs[0];
  confirmResult=false;input.checked=false;await input.onchange();
  assert(input.checked);assert.equal(requests.length,0,'cancelled global shutdown must not write');
  confirmResult=true;input.checked=false;await input.onchange();
  assert.deepEqual(requests[0],['/switches',{feature:'all',chat_id:0,enabled:false,reason:'Тест'}]);
  fixture();await view(null);input=inputs[0];failWrite=true;input.checked=false;await input.onchange();
  assert(input.checked,'failed write restores the visual state');
  console.log('OK: switch names, current state, inherited lock, cancellation, payload and failed-write rollback');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
