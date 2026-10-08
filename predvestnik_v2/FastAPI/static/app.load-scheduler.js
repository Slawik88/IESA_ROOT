// Keep response processing and background reads out of navigation animations.
// Foreground requests never wait for the background queue's network slot.
let _pvBusyUntil = performance.now() + 320;
let _pvUiTimer = null, _pvUiFrame = null;
const _pvUiQueue = [], _pvBackgroundQueue = [], _pvBackgroundJobs = new Map();
let _pvBackgroundRunning = false;
const _pvReads = new Map();
let _pvReadEpoch = 0;

function pvTransitionStarted(duration = 420) {
  _pvBusyUntil = Math.max(_pvBusyUntil, performance.now() + duration);
}
function pvAfterTransition() {
  return new Promise(resolve => {
    _pvUiQueue.push({ resolve, since: performance.now() });
    _pvPumpUi();
  });
}
function _pvPumpUi() {
  if (!_pvUiQueue.length || _pvUiTimer !== null || _pvUiFrame !== null) return;
  const wait = Math.min(_pvBusyUntil - performance.now(),
                       1500 - (performance.now() - _pvUiQueue[0].since));
  if (wait > 0 && !document.hidden) {
    _pvUiTimer = setTimeout(() => { _pvUiTimer = null; _pvPumpUi(); }, wait);
    return;
  }
  const flush = () => {
    _pvUiFrame = null;
    // Navigation may have started after this frame was scheduled.
    if (!document.hidden && performance.now() < _pvBusyUntil &&
        performance.now() - _pvUiQueue[0].since < 1500) { _pvPumpUi(); return; }
    _pvUiQueue.shift()?.resolve();
    // Promise handlers render before the next response gets its own frame.
    _pvUiTimer = setTimeout(() => { _pvUiTimer = null; _pvPumpUi(); }, 0);
  };
  if (document.hidden) {
    _pvUiTimer = setTimeout(() => { _pvUiTimer = null; flush(); }, 0);
  } else {
    _pvUiFrame = requestAnimationFrame(flush);
  }
}
function pvInvalidateReads() { _pvReadEpoch++; _pvReads.clear(); }
function pvRead(key, load) {
  const scoped = _pvReadEpoch + ':' + key;
  if (_pvReads.has(scoped)) return _pvReads.get(scoped);
  const result = load();
  _pvReads.set(scoped, result);
  const clean = () => { if (_pvReads.get(scoped) === result) _pvReads.delete(scoped); };
  result.then(clean, clean);
  return result;
}
function pvBackground(key, load, valid = () => true) {
  if (_pvBackgroundJobs.has(key)) return _pvBackgroundJobs.get(key);
  const result = new Promise(resolve => _pvBackgroundQueue.push({ key, load, valid, resolve }));
  _pvBackgroundJobs.set(key, result);
  _pvDrainBackground();
  return result;
}
async function _pvDrainBackground() {
  if (_pvBackgroundRunning || document.hidden || !_pvBackgroundQueue.length) return;
  _pvBackgroundRunning = true;
  const job = _pvBackgroundQueue.shift();
  try {
    await pvAfterTransition();
    if (document.hidden) {
      _pvBackgroundQueue.unshift(job);
      return;
    }
    if (job.valid()) await job.load();
    job.resolve();
    _pvBackgroundJobs.delete(job.key);
  } catch (_) {
    job.resolve();
    _pvBackgroundJobs.delete(job.key);
  } finally {
    _pvBackgroundRunning = false;
    setTimeout(_pvDrainBackground, 80);
  }
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) _pvDrainBackground(); });
