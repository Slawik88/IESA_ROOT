// Random cosmetic chests and duplicate crafting must not return as a visible entry.
import puppeteer from 'puppeteer';

const browser = await puppeteer.launch({headless: 'new'});
try {
  const page = await browser.newPage();
  await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
  await page.goto('http://localhost:8402/', {waitUntil: 'load'});
  await page.waitForFunction(() => typeof openLooksModal === 'function');
  await page.waitForFunction(() => typeof _plSkip === 'function');
await page.evaluate(() => _plSkip());
await page.waitForFunction(() => !document.getElementById('preloader'));
  await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');
  await page.evaluate(() => openLooksModal());
  await page.waitForFunction(() => typeof _looksData !== 'undefined' && !!_looksData && !!document.querySelector('#pg-looks'));
  const state = await page.evaluate(() => ({
    visibleEntry: !!document.querySelector('.looks-surprises-entry'),
    ghostEntry: !!document.querySelector('#pg-looks [onclick="_openSurprisesModal()"]'),
    copy: document.querySelector('#pg-looks')?.textContent || '',
    overflow: document.documentElement.scrollWidth - innerWidth,
  }));
  if (state.visibleEntry || state.ghostEntry) throw new Error('retired random cosmetics entry is visible');
  if (/Сундуки-сюрпризы|Сюрпризы и крафт/.test(state.copy)) throw new Error('retired random cosmetics copy is visible');
  if (state.overflow > 1) throw new Error(`looks page overflow: ${state.overflow}px`);
  console.log('OK: random cosmetic chests/craft have no visible entry; looks page stays mobile-safe');
} finally {
  await browser.close();
}
