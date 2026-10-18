const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../FastAPI/static/app.12.js'),'utf8');
const block=source.slice(source.indexOf('  let _chestsV1Data='),source.indexOf('  // ── Задания:'));
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function boot(stars){
  const posts=[],reads=[],root={innerHTML:'',querySelector:()=>({focus(){}})};
  let celebrations=0,switches=0;
  const result={open_id:'sealed-1',stars,revealed:true,reward:{kind:'mora',name:'Мора',icon:'coin',amount:100}};
  const ctx=vm.createContext({console,Number,Math,Map,Array,String,encodeURIComponent,
    _activePage:'chests',el:()=>root,esc:String,fmt:String,
    achievementWord:(n,one,two,many)=>n===1?one:n<5?two:many,
    requestAnimationFrame:f=>f(),v3Reward:()=>{celebrations++;},_haptic(){},toast(){},
    _chestsV1PendingActions:new Map(),v3EnterSync(){},
    switchPage:p=>{switches++;ctx._activePage=p;},
    api:(url,opts)=>{if(opts?.method==='POST'){posts.push(url);return Promise.resolve(result);}reads.push(url);return Promise.resolve({key_balance:0,pending_open:null,last_result:result});},
  });
  result.rewards=[result.reward,{kind:'food',name:'Жаркое',icon:'food',amount:1}];
  ctx.window=ctx;
  vm.runInContext(block,ctx);
  ctx.renderChestsV1=()=>{};
  const run=x=>vm.runInContext(x,ctx);
  run('_chestsV1Data={key_balance:1};_chestsV1Prepared={open_id:"sealed-1"}');
  return {ctx,run,posts,reads,result,celebrations:()=>celebrations,switches:()=>switches};
}
async function main(){
  for(const n of [1,3,10]){
    const b=boot(n);
    b.run('chestsV1Reveal();chestsV1Reveal()');await tick();
    assert.ok(b.run('chestRewardsText(_chestsV1RevealView.result)').includes('Жаркое'));
    assert.equal(b.posts.length,1,'rapid first taps share one server reveal');
    assert.equal(b.run('_chestsV1RevealView.step'),1);
    for(let step=1;step<n;step++){
      assert.ok(!b.run('chestRevealScene()').includes('100'),'reward hidden until final step');
      b.run('chestsV1Prepare()');assert.equal(b.posts.length,1,'new key blocked during reveal');
      b.run('chestsV1RevealStep()');
      assert.equal(b.run('_chestsV1RevealView.step'),step+1);
    }
    assert.ok(b.run('chestRevealScene()').includes('100'));
    assert.ok(b.run('chestRevealScene()').includes('chest-loot-card'));
    assert.ok(!b.run('chestLootCards({reward:{kind:"food",ref:"basic",name:"Паёк",amount:1}})').includes('undefined'));
    assert.equal((b.run('chestLootCards({rewards:[{kind:"food",ref:"basic",amount:1},{kind:"food",ref:"basic",amount:1}]})').match(/<li /g)||[]).length,1);
    assert.ok(b.run('chestLootCards({rewards:[{kind:"food",ref:"basic",amount:1},{kind:"food",ref:"basic",amount:1}]})').includes('+2'));
    assert.equal(b.posts.length,1);assert.equal(b.celebrations(),1);
    b.run('chestsV1RevealStep();chestsV1SkipReveal()');assert.equal(b.celebrations(),1);
    const step=b.run('_chestsV1RevealView.step');b.run('openChestsV1()');await tick();
    assert.equal(b.run('_chestsV1RevealView.step'),step,'read refresh preserves stage');
    b.run('chestsV1FinishReveal()');await tick();assert.equal(b.run('_chestsV1RevealView'),null);
  }
  const skip=boot(10);skip.run('chestsV1Reveal()');await tick();skip.run('chestsV1SkipReveal()');
  assert.equal(skip.run('_chestsV1RevealView.step'),10);assert.equal(skip.posts.length,1);
  const failed=boot(3);let attempts=0;
  failed.ctx.api=(url)=>{failed.posts.push(url);return ++attempts===1?Promise.reject(Error('lost response')):Promise.resolve(failed.result);};
  failed.run('chestsV1Reveal()');await tick();
  assert.equal(failed.run('_chestsV1Prepared.open_id'),'sealed-1');
  failed.run('chestsV1Reveal()');await tick();assert.equal(failed.posts[0],failed.posts[1]);
  const leaving=boot(10);let resolve;
  leaving.ctx.api=()=>new Promise(r=>{resolve=r;});leaving.run('chestsV1Reveal()');
  leaving.ctx._activePage='looks';resolve(leaving.result);await tick();
  assert.equal(leaving.ctx._activePage,'looks');assert.equal(leaving.switches(),0);
  console.log('chest reveal UI: 1/3/10 exact taps, one POST, skip, refresh, retry and navigation OK');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
