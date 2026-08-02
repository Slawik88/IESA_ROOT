// Атмосфера шапки детального экрана (Стадия 3): каждая линейка каталога рендерит
// хотя бы 1 анимированный узел внутри .coll-detail-atmo, и все они гасятся
// под body.no-fx (тот же парный паттерн, что и .coll-card, Стадия 2).
import puppeteer from 'puppeteer';
const FAIL = [];
function check(name, cond) { if (!cond) FAIL.push(name); else console.log('OK:', name); }
const browser = await puppeteer.launch({ headless: 'new' });
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await page.goto('http://localhost:8402/', { waitUntil: 'load' });
await new Promise(r => setTimeout(r, 1500));
await page.mouse.click(195, 700);
await new Promise(r => setTimeout(r, 500));
await page.evaluate(() => openLooksModal());
await new Promise(r => setTimeout(r, 800));

const lineups = await page.evaluate(() => Object.keys(_looksData.lineups || {}));
for (const lin of lineups) {
  await page.evaluate((l) => _looksOpenCollection(l), lin);
  await new Promise(r => setTimeout(r, 200));
  const n = await page.evaluate(() => document.querySelectorAll('.coll-detail-atmo *').length);
  check(`${lin}: атмосфера рендерит ≥1 декоративный узел`, n >= 1);
}

// no-fx гасит анимацию атмосферы (проверяем на inferno — 3 узла, ico-heatglow-стиль)
await page.evaluate(() => _looksOpenCollection('inferno'));
await new Promise(r => setTimeout(r, 200));
await page.evaluate(() => document.body.classList.add('no-fx'));
await new Promise(r => setTimeout(r, 200));
const styles = await page.evaluate(() =>
  Array.from(document.querySelectorAll('.coll-detail-atmo *')).map(e => getComputedStyle(e).animationName));
check('body.no-fx гасит все анимации атмосферы (animationName === "none")', styles.every(s => s === 'none'));

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
