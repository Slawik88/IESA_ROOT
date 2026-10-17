const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const dir=path.join(__dirname,'../FastAPI/static');
const nodes=new Map();const el=id=>nodes.get(id)||(nodes.set(id,{textContent:'',classList:{contains:()=>false,remove(){},add(){},toggle(){}},dataset:{},scrollWidth:0,clientWidth:100}),nodes.get(id));
const ctx=vm.createContext({document:{fonts:null,addEventListener(){},querySelector:()=>null},window:{addEventListener(){}},el,fmt:x=>String(x),fmtF:x=>String(x),_v3Ring:()=>'',console,Date,Number});
vm.runInContext(fs.readFileSync(path.join(dir,'app.16.js'),'utf8'),ctx);
const run=x=>vm.runInContext(x,ctx);
run('renderV3Bar({balances:{mora:400,diamonds:5,zarniki:9},mora:0,zarniki:7,essence:3})');
assert.equal(el('vb-mora').textContent,'0');assert.equal(el('cm-bal-mora').textContent,'0');assert.equal(el('cm-bal-diamonds').textContent,'5');assert.equal(el('cm-bal-zarniki').textContent,'7');assert.equal(el('cm-bal-essence').textContent,'3');
el('zar-exchange-amount').value='23';run('renderV3Bar({mora:100,diamonds:0,zarniki:0,essence:0})');
assert.equal(el('cm-bal-mora').textContent,'100');assert.equal(el('cm-bal-zarniki').textContent,'0');assert.equal(el('zar-exchange-amount').value,'23');
// Actual WebSocket handler merges a partial balance and updates both DTO shapes.
const app1=fs.readFileSync(path.join(dir,'app.01.js'),'utf8');const start=app1.indexOf('function queueLiveBalance('),end=app1.indexOf('\nfunction showWsNotif',start);
Object.assign(ctx,{_pendingBalanceEvent:null,_balanceEventTimer:0,_profileData:{mora:50,diamonds:2,zarniki:8,balances:{mora:50,diamonds:2,zarniki:8}},updateCurrBar:ctx.renderV3Bar,_profileSyncStats(){},setTimeout:f=>{ctx.fire=f;return 1;}});
vm.runInContext(app1.slice(start,end),ctx);run('queueLiveBalance({mora:0})');ctx.fire();
assert.equal(ctx._profileData.mora,0);assert.equal(ctx._profileData.balances.mora,0);assert.equal(ctx._profileData.balances.zarniki,8);assert.equal(el('cm-bal-mora').textContent,'0');
console.log('OK: wallet flat/nested reconciliation, zero balances, live partial updates, open modal and preserved form input');
