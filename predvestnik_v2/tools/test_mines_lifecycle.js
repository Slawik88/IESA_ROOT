const assert=require('node:assert/strict'),boot=require('./mines_client_harness.cjs');
const text=e=>e.textContent+' '+e.children.map(text).join(' ');
const board=h=>text(h.get('leaderboard-podium'))+' '+text(h.get('leaderboard-list'));   // тройка лидеров — подиум, остальные — строки
(async()=>{
  const first=boot({blockedStorage:true,status:'awaiting_first_open',size:6});await first.tick();assert.equal(first.cells().length,36);
  assert.equal(first.requests.find(r=>r.url.endsWith('/runs')).opts.headers['x-init-data'],'telegram-proof');
  first.modes[1].onclick({detail:0});first.cells()[0].onclick({detail:0});await first.tick();assert.equal(first.m.journal()[0].kind,'open');
  first.cells()[3].onclick({detail:0});await first.tick();assert.equal(first.m.journal()[1].kind,'toggle_flag');
  first.get('mine-view-toggle').onclick({detail:0});assert.equal(first.ctx.document.body.dataset.mineZoom,'large');
  first.get('mine-view-toggle').onclick({detail:0});assert.equal(first.ctx.document.body.dataset.mineZoom,'fit');
  for(const touch of [false,true]){
    const h=boot();await h.tick();const cell=h.cells()[0];
    cell.listeners.pointerdown({button:touch?0:2,clientX:1,clientY:1});if(touch){h.runTimers();await h.tick();}
    cell.listeners.contextmenu({preventDefault(){}});await h.tick();h.runTimers();await h.tick();
    assert.equal(h.m.journal().length,1,'contextmenu after hold cannot toggle flag twice');
  }
  const keyboard=boot();await keyboard.tick();
  for(const key of ['f','F10','ContextMenu']){let prevented=false;keyboard.cells()[0].listeners.keydown({key,shiftKey:true,preventDefault(){prevented=true;}});await keyboard.tick();assert(prevented);}
  assert.equal(keyboard.m.journal().length,3);
  const malformed=boot();await malformed.tick();
  for(const bad of [{},{...malformed.m.engine().state,revealed:[1],changed:[]},{...malformed.m.engine().state,revealed:[81]}])assert.throws(()=>malformed.m.sync(bad),/загрузилось не полностью/);
  for(const rejectOld of [false,true]){
    const h=boot();await h.tick();let resolveOld,reject;
    h.net.leader=url=>url.endsWith('/easy')?new Promise((yes,no)=>{resolveOld=yes;reject=no;}):Promise.resolve({top:[{place:1,player:{display_name:'HARD'},best_elapsed_ms:1234}]});
    const pending=h.m.refreshLeaderboard();await h.tick();h.difficulties[2].onclick({detail:0});await h.tick();
    await new Promise(resolve=>setTimeout(resolve,50));await h.tick();
    assert.match(board(h),/HARD/);
    if(rejectOld)reject(Error('old failure'));else resolveOld({top:[{place:1,player:{display_name:'OLD'},best_elapsed_ms:9}]});
    await pending;await h.tick();assert.match(board(h),/HARD/);
  }
  const ranking=boot();await ranking.tick();
  ranking.net.leader=async()=>({top:[{place:1,player:{display_name:'FAST'},best_elapsed_ms:250}],personal:{place:1,best_elapsed_ms:250}});
  await ranking.m.refreshLeaderboard();
  assert.match(board(ranking),/0:00\.250/);
  assert.match(text(ranking.get('leaderboard-personal')),/0:00\.250/);
  const auto={...ranking.m.engine().state,status:'won',opened_actions:1,elapsed_ms:0};
  ranking.m.sync(auto);ranking.m.render();
  assert.match(text(ranking.get('mine-hint')),/Поле открылось первым ходом/);
  assert.match(text(ranking.get('mine-hint')),/В таблицу лидеров/);
  console.log('OK: Mines lifecycle, leaderboard race, subsecond records and automatic-win explanation');
})().catch(e=>{console.error(e);process.exitCode=1;});
