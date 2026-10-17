const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../FastAPI/static/coin-market-v2.js'),'utf8');
const nodes={'cm2-amount':{value:'0'},'cm2-units':{value:'0.001'},'cm2-preview':{innerHTML:''}};
nodes['cm2-check']={className:'cm2-primary',disabled:false,textContent:''};
let calls=[],quote={received:'0',commission:'0.000001',sold_units:'1',zero_payout:true,tick:7,price:'0.001'};
nodes['cm2-name']={value:'My coin'};nodes['cm2-z']={value:'1000'};nodes['cm2-deposit']={value:'1000'};nodes['cm2-gems']={checked:false};
const moneyCtx=vm.createContext({});
vm.runInContext(source.slice(source.indexOf('const exactMoney='),source.indexOf('\n  const signed='))+';this.format=exactMoney;',moneyCtx);
assert.equal(moneyCtx.format('10.000001'),'10,000001');
assert.equal(moneyCtx.format('999999999999.123456'),'999\u00a0999\u00a0999\u00a0999,123456');
assert.equal(moneyCtx.format('0.000001'),'0,000001');
assert.equal(moneyCtx.format('0'),'0');
vm.runInContext(source.slice(source.indexOf('function sumMoney('),source.indexOf('\n  const haptic='))+';this.sum=sumMoney;this.overview=overviewMoney;',moneyCtx);
assert.equal(moneyCtx.sum(['999999999999.123456','0.000001']),'999999999999.123457','portfolio keeps micro precision beyond float-safe integers');
assert.equal(moneyCtx.sum(['100','-1.000001']),'98.999999');
assert.equal(moneyCtx.sum([]),'0.000000');assert.equal(moneyCtx.sum(['invalid']),null,'invalid money never becomes a fake zero valuation');
assert.equal(moneyCtx.overview('395.914383'),'395,91');assert.equal(moneyCtx.overview('0.005000'),'0,01');assert.equal(moneyCtx.overview('999999999999.999999'),'1\u00a0000\u00a0000\u00a0000\u00a0000','overview rounding must carry without float loss');
const host={innerHTML:'',querySelector:()=>null};
let respond=null;
const ctx=vm.createContext({document:{getElementById:id=>nodes[id]},busy:false,formRevision:0,view:'deal',selected:{id:'dust',units:'1'},draft:null,root:()=>host,crypto:{randomUUID:()=> 'dust-explicit-confirmation'},num:String,exactMoney:moneyCtx.format,escape:String,message(){},request:async(p,b)=>{calls.push({p,b});return respond?respond():quote;}});
vm.runInContext(source.slice(source.indexOf('function paint('),source.indexOf('\n  function message(')),ctx);
vm.runInContext(source.slice(source.indexOf('function invalidate('),source.indexOf('\n  async function preview(')),ctx);
vm.runInContext(source.slice(source.indexOf('async function preview('),source.indexOf('\n  function create(){')),ctx);
vm.runInContext(source.slice(source.indexOf('async function createPreview('),source.indexOf('\n  async function confirm(')),ctx);
async function main(){
 const walletCtx=vm.createContext({data:{balances:{mora:'894',mora_total:'1094',mora_reserved:'200'}},num:String});
 vm.runInContext(source.slice(source.indexOf('function walletSummary('),source.indexOf('\n  function marketSummary(')),walletCtx);
 const split=walletCtx.walletSummary();
 assert.match(split,/В кошельке · Мора/);assert.match(split,/>1094<\/strong>/);
 assert.match(split,/Для торговли<\/dt><dd>894/);assert.match(split,/В резерве<\/dt><dd>200/);
 walletCtx.data.balances={mora:'1094',mora_total:'1094',mora_reserved:'0'};
 assert.doesNotMatch(walletCtx.walletSummary(),/В резерве/,'empty reserve must not clutter the wallet');
 const refreshButton={disabled:false,textContent:'Обновить'};let finishRefresh,homeRenders=0;
 const marketCtx=vm.createContext({marketRefreshing:false,view:'home',formRevision:1,data:{old:true},document:{getElementById:()=>refreshButton},request:()=>new Promise(r=>finishRefresh=r),renderHome(){homeRenders++;},message(){}});
 vm.runInContext(source.slice(source.indexOf('async function refreshMarket('),source.indexOf('\n  function renderHome(')),marketCtx);
 const oldRefresh=marketCtx.refreshMarket();assert.equal(refreshButton.disabled,true);
 marketCtx.view='coin';marketCtx.formRevision++;finishRefresh({new:true});await oldRefresh;
 assert.equal(homeRenders,0,'a delayed refresh cannot return the player from coin to market');
 assert.equal(marketCtx.data.old,true,'a stale response cannot replace another screen snapshot');
 marketCtx.view='home';const freshRefresh=marketCtx.refreshMarket();
 let caret=null,focusRestored=false;
 marketCtx.document.activeElement={id:'cm2-search',selectionStart:2,selectionEnd:3};
 marketCtx.document.getElementById=id=>id==='cm2-search'?{focus(){focusRestored=true;},setSelectionRange(a,b){caret=[a,b];}}:refreshButton;
 finishRefresh({new:true});await freshRefresh;assert.equal(homeRenders,1);assert.equal(marketCtx.data.new,true);
 assert(focusRestored,'typing during refresh retains search focus');assert.deepEqual(caret,[2,3],'refresh retains selection/caret');
 const refreshCalls=[];
 const refreshCtx=vm.createContext({formRevision:0,view:'coin',period:24,selected:{id:'orb',tick:1},live:{last:2},data:null,
  document:{getElementById:()=>null},draw(){},request:async p=>{refreshCalls.push(p);return p==='/me'?{coins:[{id:'orb',tick:2}]}:{points:[{tick:2,price:'1'}]};}});
 vm.runInContext(source.slice(source.indexOf('async function refreshCoin('),source.indexOf('\n  async function complete(')),refreshCtx);
 await refreshCtx.refreshCoin('orb');
 assert(refreshCalls.includes('/me'),'opening an older snapshot must update the hero even when history is current');
 assert.equal(refreshCtx.selected.tick,2);
 const requestCtx=vm.createContext({Headers,AbortController,setTimeout,clearTimeout,BASE:'/test',hdrs:()=>({'content-type':'application/json','x-session-token':'test-only'}),fetch:async(url,options)=>{
  assert.equal(options.headers.get('content-type'),'application/json','exactly one Content-Type');
  assert.equal(options.headers.get('x-session-token'),'test-only','auth preserved');
  return {ok:true,json:async()=>({ok:true})};
 }});
 vm.runInContext(source.slice(source.indexOf('async function request('),source.indexOf('\n  function head(')),requestCtx);
 await requestCtx.request('/quote',{units:1});

 await ctx.preview('sell',null);
 assert.equal(calls.length,1);assert.equal(calls[0].p,'/quote');assert.equal(calls[0].b.units,1);
 assert.match(nodes['cm2-preview'].innerHTML,/Получите 0 Моры/);
 assert.match(nodes['cm2-preview'].innerHTML,/Продать за 0 Моры/);
 assert.match(nodes['cm2-preview'].innerHTML,/Мора из кошелька не списывается/);
 assert.equal(ctx.draft.path,'/trade');assert.equal(ctx.draft.body.units,1);
 assert.equal(nodes['cm2-check'].className,'cm2-plain cm2-recheck','only final confirmation stays primary');
 ctx.invalidate();assert.equal(nodes['cm2-check'].className,'cm2-primary','editing restores the first action');
 assert.equal(ctx.draft,null,'editing cannot retain old confirmation');
 quote={...quote,received:'0.000001',zero_payout:false};calls=[];await ctx.preview('sell',null);
 assert.doesNotMatch(nodes['cm2-preview'].innerHTML,/Продать за 0 Моры|будет продан без выплаты/);
 assert.equal(calls.length,1,'preview must never submit a trade automatically');
 for(const kind of ['trade','create']){
  for(const change of ['input','navigate','same-screen-repaint','coin','replaced-host']){
   ctx.view=kind==='trade'?'deal':'create';ctx.selected={id:'dust'};ctx.draft=null;
   nodes['cm2-preview']={innerHTML:''};let resolve;
   respond=()=>new Promise(r=>{resolve=r;});
   const running=kind==='trade'?ctx.preview('sell',null):ctx.createPreview();
   if(change==='input')ctx.invalidate();
   if(change==='navigate'){ctx.view='home';ctx.paint('home');}
   if(change==='same-screen-repaint')ctx.paint('new form');
   if(change==='coin')ctx.selected={id:'other'};
   if(change==='replaced-host')nodes['cm2-preview']={innerHTML:''};
   resolve(quote);await running;
   assert.equal(ctx.draft,null,`${kind}/${change}: stale quote cannot enable a trade`);
   assert.equal(nodes['cm2-preview'].innerHTML,'',`${kind}/${change}: no stale confirmation`);
   assert.equal(ctx.busy,false);
  }
 }
 respond=null;ctx.view='create';await ctx.createPreview();
 assert.equal(ctx.draft.path,'/create','fresh creation preview still works');
 assert.match(nodes['cm2-preview'].innerHTML,/Создать с этими условиями/);
 assert.equal(nodes['cm2-check'].className,'cm2-plain cm2-recheck');
 const cards=vm.createContext({data:{enabled:false,shorts_enabled:false,shorts:[{id:'s1',coin_id:'orb',collateral:'100',received:'98',result:'-2',liquidation_price:'1.2'}]},num:String,signed:String});
 vm.runInContext(source.slice(source.indexOf('function coinActions('),source.indexOf('\n  function draw(')),cards);
 assert.match(cards.shortCard({id:'orb'}),/CM2.closeShort\('s1'\)/,'existing short can close even with entry flags off');
 assert.match(cards.shortCard({id:'orb'}),/При закрытии/,'returned collateral is not labelled profit');
 cards.data.shorts=[];assert.equal(cards.shortCard({id:'orb'}),'','liquidated positions disappear');
 console.log('PASS: explicit zero payout, manual confirmation, and stale trade/create quotes rejected after edits or navigation');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
