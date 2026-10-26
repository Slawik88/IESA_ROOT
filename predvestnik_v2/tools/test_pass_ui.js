const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const dir = path.join(__dirname, '../FastAPI/static');
async function main() {
  const handlers = {};
  const transitionWindow = {};
  vm.runInNewContext(fs.readFileSync(path.join(dir,'page-transitions.js'),'utf8'),{window:transitionWindow,addEventListener:(name,fn)=>{handlers[name]=fn;}});
  for (const name of ['pageswap','pagereveal']) handlers[name]({viewTransition:{ready:Promise.reject(Error('opt-in disabled')),finished:Promise.resolve(),updateCallbackDone:Promise.resolve()}});
  await new Promise(setImmediate);
  let rejection, toasts=0, prevented=0;
  const appSource=fs.readFileSync(path.join(dir,'app.01.js'),'utf8');
  vm.runInNewContext(appSource.slice(appSource.indexOf("window.addEventListener('unhandledrejection'"),appSource.indexOf('window.onTelegramWidgetAuth')),{
    window:{...transitionWindow,addEventListener:(_name,fn)=>{rejection=fn;}},toast:()=>toasts++,console:{error(){}},
  });
  rejection({reason:{name:'InvalidStateError',message:'Transition was aborted because of invalid state. ViewTransition opt-in disabled'},preventDefault(){prevented++;}});
  assert.equal(prevented,1); assert.equal(toasts,0,'Skipped browser animation must not report a failed game');
  rejection({reason:{name:'InvalidStateError',message:'A different operation failed'},preventDefault(){}});
  rejection({reason:new TypeError('actual app failure'),preventDefault(){}});
  assert.equal(toasts,2,'Real application errors must remain visible');
  for (const page of ['index.html','game-shell-v3.html']) assert(fs.readFileSync(path.join(dir,page),'utf8').includes('/static/page-transitions.js'));
  let resolveClaim, sheets=0;
  const button={dataset:{claim:'2'},isConnected:true,classList:{add(){}},querySelector:()=>null};
  const host={innerHTML:'',isConnected:true,querySelectorAll:s=>s==='[data-claim]'?[button]:[]};
  const L={state:{view:'pass'},esc:String,haptic(){},$:()=>null,api:()=>new Promise(r=>{resolveClaim=r;})};
  const Fx={count(){},moves:()=>false,sheet(){sheets++;return{host:{}};}};
  const passCtx=vm.createContext({window:{League:L,LeagueArt:{icon:()=>'',METAL:{},reward:text=>({art:'',short:text})},LeagueFx:Fx,LeagueHelp:{xp:()=>''}},Date,clearTimeout,setTimeout});
  vm.runInContext(fs.readFileSync(path.join(dir,'league-pass.js'),'utf8'),passCtx);
  const season={season:2,current:true,level:40,levels:40,xp:12300,xp_per_level:300,track:[],repeat:{ready:true,level:41,xp_per_claim:300,banked_xp:300,wait_hours:12,key_tier:1}};
  await passCtx.window.LeaguePass.render(host,{active:true,vip:false,vip_min_days:30,account:{eligible:true},seasons:[season]});
  assert(host.innerHTML.includes('VIP от 1 месяца')&&host.innerHTML.includes('Возобновляемый')&&host.innerHTML.includes('12 ч'));
  assert(host.innerHTML.includes('data-cell="41-free"')&&!host.innerHTML.includes('data-cell="41-vip"'));
  assert(!host.innerHTML.includes('<aside')&&!host.innerHTML.includes('VIP-дорожка: активная подписка'));
  assert(host.innerHTML.indexOf('data-cell="41-free"')>host.innerHTML.indexOf('<ol role="list">'),'Repeat belongs inside the reward ribbon');
  const pending=button.onclick();
  L.state.view='rhythm';button.isConnected=false;
  resolveClaim({granted:[{level:41,track:'free',text:'ключ'}]});
  await pending;
  assert.equal(sheets,0,'Leaving BP while claim is pending must not open a reward sheet over the game');
  L.state.view='pass';
  const account={eligible:true,min_days:14};
  const me={active:true,vip:false,account,seasons:[season]};
  await passCtx.window.LeaguePass.render(host,{...me,seasons:[{...season,level:1}]});
  assert(host.innerHTML.includes('После уровня 40')&&!host.innerHTML.includes('Можно забрать'));
  await passCtx.window.LeaguePass.render(host,{...me,account:{eligible:false,min_days:14}});
  assert(host.innerHTML.includes('Аккаунту нужно 14 дней')&&!host.innerHTML.includes('Можно забрать'));
  await passCtx.window.LeaguePass.render(host,{...me,seasons:[{...season,current:false}]});
  assert(!host.innerHTML.includes('data-cell="41-free"'),'No repeat reward in past seasons');
  const nodes = new Map(['lgr-progress','lgr-progress-fill','lgr-remaining','lgr-sig'].map(id=>[id,{style:{},setAttribute(k,v){this[k]=v;}}]));
  const rhythmCtx = vm.createContext({window:{League:{}},document:{getElementById:id=>nodes.get(id)}});
  vm.runInContext(fs.readFileSync(path.join(dir,'league-rhythm-fx.js'),'utf8'),rhythmCtx);
  for (const [signal,done] of [[1,0],[2,1],[31,30]]) {
    rhythmCtx.window.LeagueRhythmView.hud({s:{health:3,score:0,signal},pace:()=>100},{hearts:3,signals:30});
    assert.equal(nodes.get('lgr-progress')['aria-valuenow'],done);
    assert.equal(nodes.get('lgr-sig').textContent,`${done}/30`);
  }
  let choices, paused=0, restarted=0, resumed=0;
  const shellCtx = vm.createContext({window:{LeagueFx:{sheet:(_h,_b,actions)=>{choices=actions;}}},document:{body:{dataset:{}}}});
  vm.runInContext(fs.readFileSync(path.join(dir,'game-shell-v3.js'),'utf8'),shellCtx);
  const restart = shellCtx.window.GameShell.guarded({risky:()=>true,pause:()=>paused++,resume:()=>resumed++,run:()=>restarted++,ask:{}});
  restart(); restart();
  assert.equal(paused,1); assert.equal(restarted,0); assert.equal(choices[1].arm,450);
  choices[0].f(); assert.equal(resumed,1); assert.equal(restarted,0);
  restart(); choices[1].f(); assert.equal(restarted,1);
  console.log('OK: WebView transition refusals, single page update, repeat panel, VIP label, leaving a pending BP claim');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
