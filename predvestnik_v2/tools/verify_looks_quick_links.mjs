// «Вход» и «Темы» — такие же части внешнего вида, как слоты косметики. Они не
// должны требовать пролистать весь каталог, особенно в режиме коллекций.
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
  await page.waitForFunction(() => typeof _plSkip === 'function');
await page.evaluate(() => _plSkip());
await page.waitForFunction(() => !document.getElementById('preloader'));
  await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');

  await page.evaluate(() => { openLooksModal(); document.body.classList.add('no-fx'); });
  await page.waitForFunction(() => !!_looksData && !!document.querySelector('#pg-looks'));
  const collections = await page.evaluate(() => ({
    links: [...document.querySelectorAll('#looks-quick-links [data-looks-jump]')].map(node => node.getAttribute('data-looks-jump')),
    heights: [...document.querySelectorAll('#looks-quick-links [data-looks-jump]')].map(node => Math.round(node.getBoundingClientRect().height)),
  }));

  await page.evaluate(() => _looksJump('themes'));
  const jump = await page.evaluate(() => ({
    scrollY: Math.round(window.scrollY),
    themesTop: Math.round(document.querySelector('#looks-sec-themes').getBoundingClientRect().top),
  }));

  await page.evaluate(() => _looksSetMode('slots'));
  const slots = await page.evaluate(() => ({
    links: [...document.querySelectorAll('#looks-quick-links [data-looks-jump]')].map(node => node.getAttribute('data-looks-jump')),
    unique: new Set([...document.querySelectorAll('#looks-quick-links [data-looks-jump]')].map(node => node.getAttribute('data-looks-jump'))).size,
    heights: [...document.querySelectorAll('#looks-quick-links [data-looks-jump]')].map(node => Math.round(node.getBoundingClientRect().height)),
  }));

  check('collections provide direct links to welcome and themes', collections.links.length === 2 && collections.links.includes('welcome') && collections.links.includes('themes'));
  check('quick links meet the mobile touch target', collections.heights.every(height => height >= 44));
  check('themes link reaches the themes section without a long manual scroll', jump.scrollY > 0 && jump.themesTop >= 0 && jump.themesTop < 260);
  check('slots keep every cosmetic slot plus welcome and themes in one unique quick-link strip', slots.links.length === 8 && slots.unique === 8 && slots.links.includes('welcome') && slots.links.includes('themes'));
  check('slots quick links remain touch-safe', slots.heights.every(height => height >= 44));
} finally {
  await browser.close();
}

if (failures.length) {
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
