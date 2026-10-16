'use strict';
// Replay real engine rounds; no network, rewards or production state.
const assert = require('node:assert/strict');
const fixtures = require('./pet_practice_paths.json');
const {load} = require('./pet_practice_harness.cjs');
async function main() {
 const {game} = load(); let count = 0;
 for (const row of fixtures) {
  for (const approach of row.contract === 'beacon' ? ['any', row.lensSource] : ['any']) {
   game.fresh(row.seed, row.contract, row.layout);
   const first = game.get(); first.approach = approach === 'guard' ? 'guard' : approach === 'ruins' ? 'ruins' : 'any'; game.put(first);
   for (const action of row.actions) {
    const before = game.get(); assert.equal(before.status, 'playing');
    if (['move', 'dash'].includes(action.type)) assert.ok(game.legalMoves().some(a => a.type === action.type && a.to === action.to));
    else if (action.type === 'attack') assert.ok(before.enemies.some(e => e.id === action.id && e.hp > 0 && game.dist(before.pos, e.pos) === 1));
    else if (!['wait','sniff'].includes(action.type)) {
     const at = action.type === 'tunnel' ? action.to === 17 ? 12 : 17 : action.at;
     assert.equal(game.actionFor(at)?.[0], action.type);
    }
    const {state} = await game.act(action); assert.equal(state.turn, before.turn + 1);
    const restored = game.restoreSnapshot({privateContent: state}).state;
    assert.equal(restored.turn, state.turn); assert.equal(restored.hp, state.hp);
    assert.equal(restored.approach, first.approach);
   }
   const final = game.get(); assert.equal(final.status, 'won'); assert.equal(final.turn, row.turn); assert.equal(final.hp, row.hp); count++;
  }
 }
 // A mandatory route cannot be bypassed through the alternative lens source.
 game.fresh(1, 'beacon', 0); let s = game.get(); s.approach = 'guard'; s.pos = 6; game.put(s);
 assert.notEqual(game.actionFor(0)?.[0], 'chest');
 await game.act({type:'chest', correct:true}); assert.equal(game.get().lens, false);
 s = game.get(); s.approach = 'ruins'; s.pos = 14; s.enemies[0].hp = 2; game.put(s);
 await game.act({type:'attack',id:'guard'}); assert.equal(game.get().lens, false);
 // Same seed, different goals and paths have separate records.
 game.fresh(1,'beacon',0); s = game.get(); s.lensSource = 'ruins'; game.put(s); const key = game.recordKey();
 s.approach = 'ruins'; game.put(s); assert.notEqual(game.recordKey(), key);
 // Broken local saves recover to preparation, never an unplayable round.
 assert.equal(game.restoreSnapshot({privateContent:{v:4, hp:-1}}).state.status,'prep');
 console.log(`Pet practice: ${count} valid winning policies + route constraints, restore and record isolation OK`);
}
main().catch(error => {console.error(error); process.exitCode = 1;});
