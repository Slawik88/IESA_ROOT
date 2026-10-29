// Реальный код «Чистки»: отказ виден вызывающему, закрытие страницы не задерживает второй запрос.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../FastAPI/static/bot-admin/admin-purge.js'), 'utf8');
const context = vm.createContext({clearTimeout, console});
vm.runInContext(source + `
globalThis.probe = async () => {
  purgeLoad = () => {};
  purgeApi = async () => { throw new Error('нет связи'); };
  let error;
  try { await purgePost(1, 'decision', {}); } catch (e) { error = e.message; }
  const calls = [], releases = [];
  purgeApi = (url, opts) => {
    calls.push({url, opts});
    return new Promise(resolve => releases.push(() => resolve({data: {ok: true}})));
  };
  const first = purgePost(10, 'decision', {user_id: 1}, true);
  const second = purgePost(20, 'decision', {user_id: 2}, true);
  const sentBeforeReply = calls.length;
  releases.forEach(release => release());
  await Promise.all([first, second]);
  calls.length = 0; releases.length = 0;
  const normalFirst = purgePost(30, 'decision', {user_id: 3});
  const normalSecond = purgePost(30, 'decision', {user_id: 4});
  await Promise.resolve(); await Promise.resolve();
  const normalBeforeReply = calls.length;
  releases[0](); await normalFirst;
  await Promise.resolve(); await Promise.resolve();
  releases[1](); await normalSecond;
  return {error, sentBeforeReply, normalBeforeReply, normalTotal: calls.length};
};`, context);
context.probe().then(result => {
  assert.equal(result.error, 'нет связи');
  assert.equal(result.sentBeforeReply, 2);
  assert.equal(result.normalBeforeReply, 1);
  assert.equal(result.normalTotal, 2);
  console.info('OK: отказ передан в полосу, при закрытии оба запроса начаты, обычная очередь сохранена');
}).catch(error => { console.error(error); process.exitCode = 1; });
