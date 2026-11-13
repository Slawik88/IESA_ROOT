/* Real app.18 controller; virtual time models browser cadence without forcing its effect level. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../FastAPI/static/app.18.js'), 'utf8');

function harness({fps = 60, memory = 8, cores = 8, saveData = false, reduced = false, saved = {}, storageBlocked = false} = {}) {
  let now = 0, serial = 0;
  const timers = new Map(), events = new Map(), values = {...saved}, mediaListeners = [];
  const state = {fps, visible: true, sceneTier: 'D', sceneSkin: '', reduced};
  const names = new Set();
  const classList = {add: (...items) => items.forEach(n => names.add(n)), remove: (...items) => items.forEach(n => names.delete(n)),
    contains: name => names.has(name), toggle(name, on) {on ? names.add(name) : names.delete(name);}, [Symbol.iterator]: () => names.values()};
  const stage = {offsetHeight: 231, dataset: {}, classList: {contains: name => name === `ap-t${['D','C','B','A','S','SS','SSS'].indexOf(state.sceneTier) + 1}`}};
  const body = {dataset: {}, classList};
  const document = {body, hidden: false, querySelector: () => null,
    querySelectorAll: () => state.visible ? [stage] : [],
    addEventListener(name, fn) {if (!events.has(name)) events.set(name, []);events.get(name).push(fn);}};
  const schedule = (fn, delay) => {const id = ++serial;timers.set(id, {at: now + delay, fn});return id;};
  const context = vm.createContext({document, navigator: {deviceMemory: memory, hardwareConcurrency: cores, connection: {saveData}},
    window: {addEventListener() {}}, MutationObserver: class {observe() {}},
    matchMedia: () => ({matches: state.reduced, addEventListener: (name, fn) => mediaListeners.push(fn)}), performance: {now: () => now},
    localStorage: {getItem(key) {if (storageBlocked) throw new Error('storage unavailable');return values[key] ?? null;},
      setItem(key, value) {if (storageBlocked) throw new Error('storage unavailable');values[key] = value;},
      removeItem(key) {if (storageBlocked) throw new Error('storage unavailable');delete values[key];}},
    setTimeout: (fn, delay) => schedule(fn, delay), clearTimeout: id => timers.delete(id),
    requestAnimationFrame: fn => schedule(() => fn(now), 1000 / state.fps), cancelAnimationFrame: id => timers.delete(id)});
  context.window.matchMedia = context.matchMedia;
  vm.runInContext(source, context);
  // Canvas drawing is covered by browser checks; this harness exercises the unchanged controller entry points.
  vm.runInContext('_v3BuildFx=()=>{};_v3BindTilt=()=>{};_v3FxRun=()=>{};', context);
  const evaluate = code => vm.runInContext(code, context);
  return {state, values, document, names, evaluate, scene:stage,
    wear(skin = 'void', tier = 'SSS') {
      state.sceneSkin = stage.dataset.sk = body.dataset.skin = skin;state.sceneTier = tier;
      evaluate(`applySkinTier({tier:${JSON.stringify(tier)}})`);
    },
    run(ms) {
      const end = now + ms;let count = 0;
      while (timers.size) {
        const [id, task] = [...timers].sort((a,b) => a[1].at-b[1].at)[0];
        if (task.at > end) break;
        assert(++count < 20000, 'scheduler did not settle');timers.delete(id);now = task.at;task.fn();
      }
      now = end;
    },
    emit(name) {(events.get(name) || []).forEach(fn => fn({}));},
    calm(on) {classList.toggle('no-fx', on);evaluate('applySkinTier(_v3Skin)');},
    reduce(on) {state.reduced=on;mediaListeners.forEach(fn=>fn({matches:on}));},
    snapshot() {return {classes: [...names], fx: evaluate('v3FxLevelNow()'), lite: names.has('ap-lite'), low: names.has('ap-low')};},
  };
}

let checks = 0;
for (const fps of [60, 30]) {
  const h = harness({fps});h.wear();h.run(45000);
  assert(!h.snapshot().lite && !h.snapshot().low && h.snapshot().fx === 7, `${fps}fps lost motion: ${JSON.stringify(h.snapshot())}`);
  checks++;
}
for (const fps of [20, 10]) {
  const h = harness({fps});h.wear();h.run(45000);
  assert(h.snapshot().lite && h.snapshot().low && h.snapshot().fx < 7, `${fps}fps did not reduce effects`);
  assert(!h.values.v3_low && !h.values.v3_lite && !h.values.v3_fx_cap, 'automatic limits leaked into persistent storage');
  const reopened = harness({fps:60, saved:h.values});reopened.wear();reopened.run(12000);
  assert(!reopened.snapshot().low && reopened.snapshot().fx === 7, 'new document retained an old automatic limit');
  checks += 3;
}
{
  const h = harness({saved:{v3_perf_rev:'2026-10-12b',v3_lite:'1',v3_low:'1',v3_fx_cap:'2'}});
  h.wear();h.run(15000);
  assert(!h.snapshot().low && h.snapshot().fx === 7, 'legacy saved limit still wins over a healthy launch');checks++;
}
{
  const h = harness({fps:20, storageBlocked:true});h.wear();h.run(30000);
  assert(h.snapshot().low && h.snapshot().fx < 7, 'storage refusal disabled protection');checks++;
}
for (const options of [{memory:2}, {cores:2}]) {
  const h = harness(options);h.wear();h.run(12000);
  assert(h.snapshot().low && h.snapshot().fx <= 3, 'hardware restriction lost');checks++;
}
{
  const h = harness({saveData:true});h.wear();
  assert(!h.names.has('ap-anim') && h.snapshot().fx === 2, 'saveData restriction lost');checks++;
}
for (const kind of ['calm','reduced']) {
  const h = harness({reduced:kind==='reduced'});if (kind==='calm') h.calm(true);h.wear();h.run(10000);
  assert(!h.names.has('ap-anim') && h.snapshot().fx === 1, `${kind} preference ignored`);checks++;
}
{
  const h = harness({fps:20});h.wear();h.run(4000);h.wear('hanami','D');h.run(18000);
  assert(!h.snapshot().lite && !h.snapshot().low && h.snapshot().fx === 1, 'old SSS measurement poisoned new D');checks++;
  h.state.fps=60;h.wear('hanami','SSS');h.run(15000);
  assert(!h.snapshot().low && h.snapshot().fx === 7, 'cancelled measurement poisoned next look');checks++;
}
{
  const h = harness({fps:20});h.wear();h.run(4000);h.document.hidden=true;h.emit('visibilitychange');h.run(15000);
  assert(!h.snapshot().lite, 'hidden document completed a quality decision');
  h.state.fps=60;h.document.hidden=false;h.emit('visibilitychange');h.run(15000);
  assert(!h.snapshot().low && h.snapshot().fx === 7, 'return inherited cancelled slow frames');checks+=2;
}
{
  const h = harness({fps:20});h.wear();h.run(4000);h.state.visible=false;h.run(15000);
  assert(!h.snapshot().lite, 'hidden scene completed a quality decision');
  h.state.visible=true;h.state.fps=60;h.evaluate('_v3StartWatchdog(v3FxLevelNow())');h.run(15000);
  assert(!h.snapshot().low, 'visible scene could not be measured again');checks+=2;
}
{
  const h = harness({fps:20});h.wear();h.run(4000);h.calm(true);h.run(15000);
  assert(!h.snapshot().lite && h.snapshot().fx===1, 'calm mode continued a pending measurement');
  h.state.fps=60;h.calm(false);h.run(15000);
  assert(!h.snapshot().low && h.snapshot().fx===7, 'disabling calm restored stale frames');checks+=2;
}
{
  const h = harness({fps:20});h.wear('void','SSS');h.run(30000);h.wear('forest','C');
  assert(!h.snapshot().lite && !h.snapshot().low, 'SSS limit leaked into a lighter tier');checks++;
}
{
  const h=harness({fps:20});h.wear();h.run(4000);h.state.fps=60;h.wear('hanami','SSS');h.run(20000);
  assert(!h.snapshot().low&&h.snapshot().fx===7,'old look poisoned a new look at the same tier');checks++;
}
{
  const h=harness({fps:20});h.wear();h.scene.dataset.sk='hanami';h.run(30000);
  assert(!h.snapshot().lite,'a preview of another look reduced the equipped look');checks++;
}
{
  const h=harness({fps:20});h.wear();h.run(4000);h.reduce(true);h.run(12000);
  assert(!h.names.has('ap-anim')&&!h.snapshot().lite,'OS motion preference did not cancel measurement');
  h.state.fps=60;h.reduce(false);h.run(15000);
  assert(h.names.has('ap-anim')&&!h.snapshot().low,'OS motion preference did not restore ordinary effects');checks+=2;
}
process.stdout.write(`PASS ${checks} ordinary motion controller checks: cadence, storage, hardware, preferences, races and lifecycle\n`);
