// Lost HTTP responses must never turn a retry into a second money transfer.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const nodes=new Map(),memory=new Map(),calls=[],modal=[];
const el=id=>nodes.get(id)||(nodes.set(id,{value:'',disabled:false,textContent:'',innerHTML:'',isConnected:true}),nodes.get(id));
let outcome='lost';
const ctx=vm.createContext({_uid:101,UK:'uid',BASE:'/app',crypto:require('node:crypto').webcrypto,AbortSignal,AbortController,setTimeout,clearTimeout,console,
  localStorage:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)},
  el,hdrs:()=>({'Content-Type':'application/json'}),toast(){},refreshCurrBar(){},esc:String,fmt:String,
  vipName:x=>x,apName:(x,y)=>y,apFromLook:()=>({}),CM(){},OM:(title,body)=>modal.push({title,body}),
  api:async p=>p==='/marriage/'?{married:true,partner_name:'Партнёр',days:2,family_balance:50,family_balance_essence:7}:
      p==='/marriage/proposals'?{proposals:[]}:{root:0,nodes:[],edges:[]},
  fetch:async(url,opts)=>{calls.push(opts);if(outcome==='lost')throw Error('response lost');
    if(outcome==='500')return {ok:false,status:500,json:async()=>({detail:'server error'})};
    if(outcome==='400')return {ok:false,status:400,json:async()=>({detail:'Недостаточно средств'})};
    return {ok:true,status:200,json:async()=>({message:'Готово'})};}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../FastAPI/static/app.06.js'),'utf8'),ctx);
const tick=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
(async()=>{
  ctx.openFamilyTree();await tick();
  assert.match(modal[0].body,/id="pro-marriage-card"/,'family navigation must actually create the wallet host');
  assert.match(el('pro-marriage-card').innerHTML,/value="essence"/);assert.match(el('pro-marriage-card').innerHTML,/Эссенция/);
  el('bank-amt').value='25';el('bank-cur').value='essence';await ctx.familyBank('deposit');
  const first=calls[0];assert(memory.has('pv-family-bank:101'));
  // Even editing the requested action after a lost response retries the
  // original immutable body, rather than guessing whether money was moved.
  outcome='500';await ctx.familyBank('withdraw');assert.equal(calls[1].body,first.body);assert.equal(calls[1].headers['Idempotency-Key'],first.headers['Idempotency-Key']);
  outcome='success';await ctx.familyBank('withdraw');assert.equal(calls[2].body,first.body);assert(!memory.has('pv-family-bank:101'));
  el('bank-amt').value='1';outcome='400';await ctx.familyBank('deposit');assert(!memory.has('pv-family-bank:101'));
  outcome='success';await ctx.familyBank('withdraw');assert.notEqual(calls[4].headers['Idempotency-Key'],first.headers['Idempotency-Key']);
  const count=calls.length;el('bank-amt').value='NaN';await ctx.familyBank('deposit');el('bank-amt').value='1.5';await ctx.familyBank('deposit');assert.equal(calls.length,count);
  console.log('OK: reachable family wallet, essence, lost-response/5xx immutable retry, explicit rejection recovery, invalid amount and account-scoped key');
})().catch(e=>{console.error(e);process.exitCode=1;});
