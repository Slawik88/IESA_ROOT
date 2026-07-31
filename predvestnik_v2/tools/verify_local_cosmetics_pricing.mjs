// Локальное предложение цен: Frost должен показывать разные цены слотов и
// честную сумму набора, рассчитанную из самих предметов, а не из цены линейки.
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
  await page.waitForFunction(() => !!_looksData && !!document.querySelector('.coll-card[data-lineup="frost"]'));
  const overview = await page.$eval('.coll-card[data-lineup="frost"]', card =>
    card.textContent.replace(/\s+/g, ' ').trim());
  // Frost находится в нижней части сетки: перед pointer tap помещаем карточку выше
  // фиксированной навигации, как это делает пользователь обычной прокруткой.
  await page.evaluate(() => document.querySelector('.coll-card[data-lineup="frost"]')?.scrollIntoView({block:'center'}));
  await page.click('.coll-card[data-lineup="frost"]');
  await page.waitForFunction(() => !!document.querySelector('.coll-detail-head'));

  const state = await page.evaluate(() => {
    const frost = Object.entries(_looksData.slots).flatMap(([slot, items]) =>
      items.filter(item => item.lineup === 'frost').map(item => ({...item, slot})));
    const prices = Object.fromEntries(frost.map(item => [item.id, item.price?.[0]?.zarniki]));
    return {
      frostSlotCount: new Set(frost.map(item => item.slot)).size,
      prices,
      detail: document.querySelector('.coll-detail-head')?.textContent.replace(/\s+/g, ' ').trim() || '',
    };
  });

  check('Frost review catalog contains one purchasable cosmetic for every slot', state.frostSlotCount === 6);
  check('Frost title is cheaper than its profile background',
    state.prices.cos_title_frostchild === 310 && state.prices.cos_profile_bg_snowpeak === 550);
  check('Frost prices rise with the visual weight of the cosmetic slot',
    state.prices.cos_title_frostchild < state.prices.cos_avatar_halo_ice &&
    state.prices.cos_avatar_halo_ice < state.prices.cos_avatar_frame_crystal &&
    state.prices.cos_avatar_frame_crystal < state.prices.cos_name_glow_frost &&
    state.prices.cos_name_glow_frost < state.prices.cos_profile_bg_snowpeak &&
    state.prices.cos_profile_bg_snowpeak < state.prices.cos_card_fx_snow);
  check('collection overview shows the actual Frost price range', /310\s*[–-]\s*590✨/.test(overview));
  check('buy-all quote sums the six actual Frost prices', /2\s*680✨/.test(state.detail));
} finally {
  await browser.close();
}

if (failures.length) {
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
