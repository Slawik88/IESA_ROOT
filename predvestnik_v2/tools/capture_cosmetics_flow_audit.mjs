// Последовательные мобильные снимки всех ключевых точек косметического пути:
// профиль → магазин → каталог → коллекция → примерочная → чужой профиль.
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
import puppeteer from 'puppeteer';

const base = (process.env.PREVIEW_URL || 'http://127.0.0.1:8402').replace(/\/$/, '');
const outputDir = process.env.AUDIT_OUTPUT || '/tmp/predvestnik-cosmetics-flow-audit';
await mkdir(outputDir, {recursive: true});

const browser = await puppeteer.launch({headless: 'new'});
const page = await browser.newPage();
await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
await page.goto(`${base}/`, {waitUntil: 'load'});
await page.waitForFunction(() => typeof openLooksModal === 'function' && typeof openGlobalProfile === 'function');
await page.mouse.click(195, 700);
await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');

const evidence = [];
async function capture(step, name, ready) {
  if (ready) await page.waitForFunction(ready);
  await new Promise(resolve => setTimeout(resolve, 500));
  const filename = `${String(step).padStart(2, '0')}-${name}.png`;
  await page.screenshot({path: path.join(outputDir, filename)});
  evidence.push({
    step,
    name,
    screenshot: filename,
    state: await page.evaluate(() => ({
      activePage: document.querySelector('.page.active')?.id || '',
      modalOpen: !!document.getElementById('modal')?.open,
      scrollY,
      errors: window.__errs || [],
    })),
  });
}

await page.evaluate(() => { switchPage('profile'); scrollTo(0, 0); });
await capture(1, 'profile-entry', () => !!document.querySelector('#pro-main .pa3-row'));

await page.evaluate(() => switchPage('market'));
await capture(2, 'market-entry', () => !!document.querySelector('#pg-market > .tabs button[onclick*="openLooksModal"]'));

await page.evaluate(() => openLooksModal());
await capture(3, 'collection-catalog', () => document.querySelectorAll('.coll-card').length >= 7);

await page.evaluate(() => _looksOpenCollection('inferno'));
await capture(4, 'collection-detail', () => !!document.querySelector('.coll-detail-head'));

await page.evaluate(() => { _looksCloseCollection(); _looksOpenFittingSheet(); });
await capture(5, 'fitting-room', () => !!document.querySelector('#looks-fit-top .hero'));

await page.evaluate(() => { CM(); switchPage('profile'); openGlobalProfile(999); });
await capture(6, 'public-profile-outfit', () => !!document.querySelector('.gp-card'));

await page.evaluate(() => {
  const gift = [...document.querySelectorAll('#mb > button')]
    .find(button => button.textContent.includes('Подарить косметику'));
  gift?.click();
});
await capture(7, 'gift-catalog', () => document.getElementById('mt')?.textContent.includes('Подарить косметику'));

await browser.close();
await writeFile(path.join(outputDir, 'evidence.json'), JSON.stringify(evidence, null, 2), 'utf8');
console.log(JSON.stringify({outputDir, evidence}, null, 2));
