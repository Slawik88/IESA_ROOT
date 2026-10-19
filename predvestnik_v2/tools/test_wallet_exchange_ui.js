const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path'), assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../FastAPI/static/app.02.js'), 'utf8');
const block = source.slice(source.indexOf('let _walletPolicy ='), source.indexOf('\nfunction showCurrBar('));
const tick = () => new Promise(resolve => setImmediate(resolve));
async function main() {
  const nodes = {};
  for (const id of ['zar-exchange-amount','zar-exchange-target','zar-exchange-submit','wallet-receive','wallet-message','wallet-exchange','modal',...['mora','diamonds','zarniki','essence'].map(c => 'cm-bal-'+c)]) nodes[id] = {value:'',textContent:'',innerHTML:'',open:true};
  nodes['zar-exchange-amount'].value = '10';
  let writes = [], opens = 0, confirms = 0, serial = 0, read = {zarniki:990};
  const ctx = vm.createContext({console,Number,String,Math,Map,JSON,
    el:id=>nodes[id], _profileData:{zarniki:1000}, _v3Wallet:d=>d,
    fmt:String, fmtF:String, _profileEsc:String, toast(){}, updateCurrBar(){},
    economyRequestKey:()=>`key-${++serial}`,
    refreshCurrBar:async()=>read,
    api:async(url, opts)=>{writes.push({url,...opts});return {amount_received:100,zarniki_spent:10};},
    v3Confirm:async()=>{confirms++;return true;},
    policy:{daily_cap:null,remaining_today:null,routes:[{id:'mora',name:'Мора',rate:'10'},{id:'diamonds',name:'Алмазы',rate:'.01'},{id:'essence',name:'Эссенция',rate:'2.5',packs:[{zarniki:20,amount:50}]}]},
  });
  const run = code => vm.runInContext(code,ctx);
  vm.runInContext(block,ctx);
  ctx.showCurrModal = () => { opens++; };
  run('_walletPolicy=policy');
  nodes['zar-exchange-amount'].value='1000';
  assert.equal(run('_walletDraft().amount'),1000,'wallet accepts amount above former daily quota');
  run('walletQuote()');
  assert.equal(nodes['zar-exchange-submit'].disabled,false);
  nodes['zar-exchange-amount'].value='1001';run('walletQuote()');
  assert.equal(nodes['zar-exchange-submit'].disabled,true,'balance still bounds conversion');
  nodes['zar-exchange-amount'].value='10';
  let finishPrompt;
  ctx.v3Confirm = () => { confirms++; return new Promise(resolve => {finishPrompt=resolve;}); };
  const cancelled = run('exchangeZarnikiV1()');
  await run('exchangeZarnikiV1()');
  assert.equal(confirms,1,'double tap opens one confirmation');
  finishPrompt(false); await cancelled;
  assert.equal(writes.length,0,'cancel does not spend');

  const captured = run('exchangeZarnikiV1()');
  nodes['zar-exchange-amount'].value='49';
  finishPrompt(true); await captured;
  assert.equal(JSON.parse(writes[0].body).amount,10,'confirmation spends captured amount');
  assert.equal(writes.length,1);
  assert.equal(opens,1);

  ctx.v3Confirm=async()=>true;
  nodes['zar-exchange-amount'].value='10';
  ctx.api=async(url,opts)=>{writes.push({url,...opts});throw Error('reply lost after server commit');};
  await run('exchangeZarnikiV1()');
  const retryKey=writes.at(-1).headers['Idempotency-Key'];
  ctx.api=async(url,opts)=>{writes.push({url,...opts});return {amount_received:100,zarniki_spent:10};};
  await run('exchangeZarnikiV1()');
  assert.equal(writes.at(-1).headers['Idempotency-Key'],retryKey,'lost reply retry keeps key');
  await run('exchangeZarnikiV1()');
  assert.notEqual(writes.at(-1).headers['Idempotency-Key'],retryKey,'new completed intent gets a new key');

  let finishWrite;
  ctx.api=(url,opts)=>{writes.push({url,...opts});return new Promise(resolve=>{finishWrite=resolve;});};
  const closing=run('exchangeZarnikiV1()'); await tick();
  const previousOpens=opens;nodes.modal.open=false;
  finishWrite({amount_received:100,zarniki_spent:10});await closing;
  assert.equal(opens,previousOpens,'completion never reopens a closed wallet');

  nodes.modal.open=true;read=null;
  ctx.api=async(url,opts)=>{writes.push({url,...opts});return {amount_received:100,zarniki_spent:10};};
  await run('exchangeZarnikiV1()');
  assert.match(nodes['wallet-exchange'].innerHTML,/Обмен выполнен/);
  assert.equal(nodes['cm-bal-zarniki'].textContent,'—','stale balance is not presented as current');
  const before=writes.length;read={zarniki:900};await run('walletRefreshBalances()');
  assert.equal(writes.length,before,'balance recovery performs no spend');

  run('_walletTarget="essence"'); nodes['zar-exchange-amount'].value='20';
  ctx.api=async(url,opts)=>{writes.push({url,...opts});return {message:'Получено 50 Эссенции',state:{essence:{balance:50},zarniki:880}};};
  await run('exchangeZarnikiV1()');
  assert.equal(writes.at(-1).url,'/skins-v3/essence');
  assert.equal(JSON.parse(writes.at(-1).body).zarniki,20);
  assert.equal(ctx._profileData.essence,50);
  console.log('wallet UI: cancel, double tap, captured draft, replay key, closed dialog, read failure and essence writer OK');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
