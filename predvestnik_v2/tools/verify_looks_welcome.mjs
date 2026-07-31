// Выбор приветствия — отдельная настройка с двумя вариантами, а не сломанная
// 2/3-строчная карточка внутри общего каталога предметов.
import puppeteer from 'puppeteer';

const failures = [];
function check(name, condition) {
  if (!condition) failures.push(name);
  else console.log('OK:', name);
}

const browser = await puppeteer.launch({headless: 'new'});
try {
  const page = await browser.newPage();
  await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
  await page.goto('http://localhost:8402/', {waitUntil: 'load'});
  await page.waitForFunction(() => typeof openLooksModal === 'function');
  await page.mouse.click(195, 700);
  await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');

  await page.evaluate(() => openLooksModal());
  await page.waitForFunction(() => !!_looksData && !!document.querySelector('#looks-sec-welcome'));
  const state = await page.evaluate(() => {
    const grid=document.querySelector('#looks-sec-welcome .looks-welcome-cards');
    const cards=[...document.querySelectorAll('#looks-sec-welcome .welcome-card')];
    return {
      columns: grid ? getComputedStyle(grid).gridTemplateColumns.split(' ').length : 0,
      cardCount: cards.length,
      wideCount: cards.filter(card => card.classList.contains('lc-wide')).length,
      current: cards.find(card => card.dataset.welcome === 'scanner')?.textContent.replace(/\s+/g, ' ').trim() || '',
      locked: cards.find(card => card.dataset.welcome === 'nova')?.textContent.replace(/\s+/g, ' ').trim() || '',
      cardHeights: cards.map(card => Math.round(card.getBoundingClientRect().height)),
    };
  });

  check('welcome choices use a dedicated two-column grid', state.columns === 2 && state.cardCount === 2 && state.wideCount === 0);
  check('current welcome state is explicit', /Сейчас используется/.test(state.current));
  check('VIP-only welcome state explains the requirement', /Доступно с VIP/.test(state.locked));
  check('welcome choices stay comfortably tappable', state.cardHeights.every(height => height >= 72));
} finally {
  await browser.close();
}

if (failures.length) {
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
