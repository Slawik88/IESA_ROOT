// Тап по карточке коллекции открывает детальный экран (Стадия 3) с шапкой и
// сегментным измерителем; кнопка "‹ Назад" возвращает к списку карточек.
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

await page.click('.coll-card[data-lineup="inferno"]');
await new Promise(r => setTimeout(r, 400));

const state = await page.evaluate(() => ({
  mode: _looksMode,
  detailLineup: _looksDetailLineup,
  hasDetailHead: !!document.querySelector('.coll-detail-head'),
  hasFilterBar: !!document.getElementById('looks-filter-bar'),
}));
check('тап по карточке "Инферно" открывает детальный экран (mode остаётся collections)', state.mode === 'collections');
check('_looksDetailLineup выставлен на inferno', state.detailLineup === 'inferno');
check('шапка детального экрана отрендерена', state.hasDetailHead);
check('умный ряд "По слотам" НЕ показывается внутри детального экрана', !state.hasFilterBar);

// Кнопка "‹ Назад" в шапке детального экрана возвращает к списку карточек коллекций
await page.click('.coll-detail-back');
await new Promise(r => setTimeout(r, 300));
const back = await page.evaluate(() => ({
  mode: _looksMode,
  detailLineup: _looksDetailLineup,
  cardCount: document.querySelectorAll('.coll-card').length,
}));
check('кнопка "‹ Назад" возвращает detailLineup в null', back.detailLineup === null);
check('режим остаётся collections', back.mode === 'collections');
check('карточки коллекций снова на экране', back.cardCount === 7);

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
