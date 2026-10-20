const assert=require('node:assert/strict'),boot=require('./mines_client_harness.cjs');
(async()=>{
  const h=boot();await h.tick();const cells=h.cells;
  assert.equal(cells().length,81);assert.equal(cells().filter(x=>x.tabIndex===0).length,1);
  assert.match(cells()[0].attrs['aria-label'],/Строка 1, столбец 1/);
  cells()[0].focus();let prevented=false;cells()[0].listeners.keydown({key:'ArrowDown',preventDefault(){prevented=true;}});
  assert(prevented);assert.equal(h.ctx.document.activeElement.dataset.cell,9);assert.equal(h.m.journal().length,0);
  h.ctx.document.activeElement.listeners.keydown({key:'End',preventDefault(){}});assert.equal(h.ctx.document.activeElement.dataset.cell,17);
  h.net.offline=true;h.ctx.document.activeElement.onclick();await h.tick();assert.equal(h.m.journal().length,1);assert.equal(h.ctx.document.activeElement.dataset.cell,17);
  assert.equal(cells().filter(x=>x.tabIndex===0).length,1);
  const button=cells()[18];button.listeners.pointerdown({clientX:1,clientY:1});button.listeners.pointermove({clientX:30,clientY:1});button.onclick({detail:1});await h.tick();assert.equal(h.m.journal().length,1,'scroll gesture cannot open a cell');
  assert.equal(h.requests.filter(r=>r.url.endsWith('/actions')).length,0,'offline gestures never need server actions');
  console.log('OK: Mines local actions, coordinates, roving focus, arrows, restored focus and scroll cancellation');
})().catch(e=>{console.error(e);process.exitCode=1;});
