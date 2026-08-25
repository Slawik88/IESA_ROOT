// Вход в косметику должен быть виден сразу в первом мобильном viewport Магазина,
// а не прятаться за горизонтальным скроллом вкладок.
import puppeteer from 'puppeteer';

const failures = [];
function check(label, condition) {
  if (condition) console.log(`OK: ${label}`);
  else {
    console.error(`FAIL: ${label}`);
    failures.push(label);
  }
}

const browser = await puppeteer.launch({headless: 'new'});
const page = await browser.newPage();
await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
await page.goto('http://localhost:8402/', {waitUntil: 'load'});
await page.waitForFunction(() => typeof switchPage === 'function');
await page.waitForFunction(() => typeof _plSkip === 'function');
await page.evaluate(() => _plSkip());
await page.waitForFunction(() => !document.getElementById('preloader'));
await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');
await page.evaluate(() => switchPage('market'));
await page.waitForFunction(() => document.getElementById('pg-market')?.classList.contains('active'));

const selector = '#pg-market > .tabs button[onclick*="openLooksModal"]';
const entry = await page.evaluate(selector => {
  const button = document.querySelector(selector);
  const row = button?.closest('.tabs');
  if (!button || !row) return null;
  const buttonRect = button.getBoundingClientRect();
  const rowRect = row.getBoundingClientRect();
  return {
    label: button.textContent.replace(/\s+/g, ' ').trim(),
    visibleWithoutScroll: row.scrollLeft === 0
      && buttonRect.left >= rowRect.left
      && buttonRect.right <= Math.min(rowRect.right, innerWidth),
    buttonRect: {left: buttonRect.left, right: buttonRect.right},
    rowRect: {left: rowRect.left, right: rowRect.right},
    rowScrollWidth: row.scrollWidth,
    rowClientWidth: row.clientWidth,
  };
}, selector);

console.log('Market appearance entry geometry:', JSON.stringify(entry));
check('market exposes an appearance entry', !!entry);
check('appearance entry is visible before horizontal tab scrolling', entry?.visibleWithoutScroll === true);
check('appearance entry is framed around player identity rather than a direct sale', entry?.label === '🎨 Образы');

await page.click(selector);
await page.waitForFunction(() => document.getElementById('pg-looks')?.classList.contains('active'));
check('appearance entry opens the existing appearance flow', await page.evaluate(() => _activePage === 'looks'));

await browser.close();
if (failures.length) {
  console.error(`\n${failures.length} market appearance entry check(s) failed.`);
  process.exit(1);
}
console.log('\nALL OK');
