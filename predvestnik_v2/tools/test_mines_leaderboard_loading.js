const assert=require('node:assert/strict'),boot=require('./mines_client_harness.cjs');
const text=e=>e.textContent+' '+e.children.map(text).join(' ');
const board=h=>text(h.get('leaderboard-podium'))+' '+text(h.get('leaderboard-list'));   // тройка лидеров — подиум, остальные — строки
(async()=>{
  const restored=boot({restored:true,size:6});await restored.tick();
  assert(restored.requests.some(r=>r.url.endsWith('/leaderboard/easy')),'active saved board must start a leaderboard request');
  assert(!restored.requests.some(r=>r.url.endsWith('/runs')),'restore cannot create a fresh game');
  const cold=boot({slowGame:true});await cold.tick();
  assert(cold.requests.some(r=>r.url.includes('/leaderboard/')),'ranking cannot wait for blocked game creation');
  const h=boot();await h.tick();let calls=0,resolve;
  h.net.leader=()=>{calls++;return new Promise(r=>resolve=r);};
  const a=h.m.refreshLeaderboard(),b=h.m.refreshLeaderboard();await h.tick();
  assert.equal(calls,1,'duplicate refreshes share one pending request');
  const win=h.m.refreshLeaderboard(true);resolve({top:[{place:1,player:{display_name:'BEFORE WIN'},best_elapsed_ms:5000}]});await h.tick();
  assert.equal(calls,2,'committed win forces a trailing request');
  assert(!board(h).includes('BEFORE WIN'),'known stale response cannot flash as current');
  resolve({top:[{place:1,player:{display_name:'AFTER WIN'},best_elapsed_ms:1000}]});await Promise.all([a,b,win]);
  assert.match(board(h),/AFTER WIN/);
  // Failure releases the pending entry so a later retry really reaches the server.
  h.net.leader=()=>{calls++;throw Error('offline');};await h.m.refreshLeaderboard();
  h.net.leader=async()=>{calls++;return {top:[]};};await h.m.refreshLeaderboard();assert.equal(calls,4);
  console.log('PASS: restored/cold bootstrap starts ranking, pending GETs coalesce, committed wins refresh, failed GET can retry');
})().catch(e=>{console.error(e);process.exitCode=1;});
