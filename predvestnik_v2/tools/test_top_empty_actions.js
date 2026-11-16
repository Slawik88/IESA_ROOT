// Actual empty-top renderers and their handlers; no browser, network or database.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const dir = path.join(__dirname, '../FastAPI/static');
const nodes = new Map(['v3-top', 'pg-top'].map(id => [id, {innerHTML: ''}]));
const calls = [];
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
const ctx = vm.createContext({
  window: {}, document: {readyState: 'loading', addEventListener() {}},
  _sysFlags: {game_rhythm_v2: true, game_minesweeper_v2: true, game_mafia_v1: true},
  _profileData: {}, _backHooks: [], el: id => nodes.get(id), esc: escape, _profileEsc: escape,
  fmt: String, v3Head: title => `<h1>${title}</h1>`, v3GuideIcon: () => '', v3EnterSync() {},
  leaveForGame: route => calls.push(['game', route]), openGuide: topic => calls.push(['guide', topic]),
  v3Guide: topic => calls.push(['hint', topic]), _haptic() {},
});
for (const name of ['app.17.js', 'app.19.js', 'app.50.js']) {
  vm.runInContext(fs.readFileSync(path.join(dir, name), 'utf8'), ctx, {filename: name});
}
const run = code => vm.runInContext(code, ctx);
function click(html) {
  const button = html.match(/<button[^>]*class="v3-pill v3-pod-next"[^>]*onclick="([^"]+)"/);
  assert(button, 'empty state has no next action');
  run(button[1]);
}
for (const [scope, expected] of [
  ['rhythm', ['game', '/rhythm-v2']], ['minesweeper', ['game', '/minesweeper']],
  ['mafia', ['guide', 'mafia']], ['global', ['hint', 'top']],
  ['local', ['hint', 'top']], ['chats', ['hint', 'top']],
]) {
  run(`_v3Full.scope=${JSON.stringify(scope)}; _v3Full.data={items:[],chats:[]}; renderTopV3()`);
  const full = nodes.get('pg-top').innerHTML;
  click(full);
  assert.deepEqual(calls.pop(), expected);
  assert(!/onclick="(?:openMafia\(|openRhythmV2Game\(|openMinesweeperGame\()/.test(full));
  assert(!full.includes('/league?game='), 'ordinary board led to ranked mode');
}
for (const tab of ['week', 'all_time', 'rhythm', 'minesweeper', 'mafia']) {
  run(`_v3TopTab=${JSON.stringify(tab)}; _v3TopCache[_v3TopTab]={top:[],personal:null}; renderV3Top()`);
  click(nodes.get('v3-top').innerHTML);
  assert.equal(calls.length, 1, `compact ${tab} action failed`);
  calls.pop();
}
for (const [scope, flag] of [['rhythm', 'game_rhythm_v2'], ['minesweeper', 'game_minesweeper_v2'], ['mafia', 'game_mafia_v1']]) {
  ctx._sysFlags[flag] = false;
  const html = run(`v3TopEmpty(${JSON.stringify(scope)})`);
  click(html);
  assert.deepEqual(calls.pop(), ['hint', 'top'], 'disabled game still had a launch action');
  ctx._sysFlags[flag] = true;
}
run('_v3Full.scope="global"; _v3Full.data=null; renderTopV3()');
assert(!nodes.get('pg-top').innerHTML.includes('v3-pod-next'), 'loading claimed the board was empty');
run('_v3Full.failed="Unavailable"; renderTopV3()');
assert(!nodes.get('pg-top').innerHTML.includes('v3-pod-next'), 'a failed board offered an empty-board action');
assert(nodes.get('pg-top').innerHTML.includes('Повторить'));
assert(run('v3PodiumEmpty("<img src=x onerror=alert(1)>")').includes('&lt;img'));
assert(!run('v3PodiumEmpty("Empty")').includes('v3-pod-next'), 'legacy optional action changed');
vm.runInContext(fs.readFileSync(path.join(dir, 'app.47.js'), 'utf8'), ctx, {filename: 'app.47.js'});
const hint = run('_GUIDE_BOOK.top');
assert(hint.tiles.some(tile => tile.text.includes('пиши в группе с Предвестником')), 'participation hint did not explain where to write');
assert(hint.tiles.some(tile => tile.text.includes('обычном Ритме') && tile.text.includes('обычный Сапёр')), 'hint did not distinguish ordinary games');
const guide = JSON.parse(fs.readFileSync(path.join(dir, 'guide-v3.json'), 'utf8'));
const mafiaTopic = guide.topics.find(topic => topic.id === 'mafia');
assert(hint.tiles.some(tile => tile.text.includes(mafiaTopic.title)), 'Mafia hint named a missing guide topic');
console.log('OK: full/compact empty tops, ordinary modes, chat Mafia, disabled games, errors and escaping');
