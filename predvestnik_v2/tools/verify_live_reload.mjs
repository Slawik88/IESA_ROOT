// Все уже открытые вкладки локального стенда должны сами подхватывать правки
// клиентских файлов. Проверяем реальную цепочку fs.watch → SSE → location.reload.
import {writeFile, unlink} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import puppeteer from 'puppeteer';

const staticDir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'FastAPI', 'static');
const probePath = path.join(staticDir, `.preview-live-reload-${process.pid}`);
const browser = await puppeteer.launch({headless: 'new'});
let reloaded = false;

try {
  const page = await browser.newPage();
  await page.evaluateOnNewDocument(() => {
    const key = '__preview_reload_count';
    sessionStorage.setItem(key, String(Number(sessionStorage.getItem(key) || 0) + 1));
  });
  await page.goto('http://localhost:8402/', {waitUntil: 'load'});
  await page.waitForFunction(() => Number(sessionStorage.getItem('__preview_reload_count')) === 1);

  await writeFile(probePath, String(Date.now()), 'utf8');
  await page.waitForFunction(
    () => Number(sessionStorage.getItem('__preview_reload_count')) >= 2,
    {timeout: 5000},
  );
  reloaded = true;
} finally {
  await browser.close();
  await unlink(probePath).catch(error => {
    if (error.code !== 'ENOENT') throw error;
  });
}

if (!reloaded) {
  console.error('FAIL: an open preview tab did not reload after a static file changed');
  process.exit(1);
}

console.log('OK: an open preview tab reloads automatically after a static file changes');
