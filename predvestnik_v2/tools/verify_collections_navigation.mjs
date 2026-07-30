// Тап по карточке коллекции переключает в режим «По слотам», отфильтрованный
// на эту линейку, и режим сохраняется (можно вернуться назад к «По коллекциям»).
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
  filter: _looksFilter,
  hasFilterBar: !!document.getElementById('looks-filter-bar'),
  lineupPillText: (document.getElementById('looks-lineup-pill') || {}).textContent || null,
}));
check('тап по карточке "Инферно" переключает режим на slots', state.mode === 'slots');
check('фильтр линейки установлен на inferno', state.filter === 'inferno');
check('умный ряд "По слотам" виден', state.hasFilterBar);
check('пилюля линейки показывает название Инферно', /Инферно/i.test(state.lineupPillText || ''));

// Кнопка "По коллекциям" в переключателе возвращает назад (не теряя фильтр слотов)
await page.click('[data-mode="collections"]');
await new Promise(r => setTimeout(r, 300));
const back = await page.evaluate(() => ({ mode: _looksMode, cardCount: document.querySelectorAll('.coll-card').length }));
check('кнопка "По коллекциям" возвращает в режим collections', back.mode === 'collections');
check('карточки коллекций снова на экране', back.cardCount === 7);

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
