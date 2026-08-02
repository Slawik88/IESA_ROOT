// Чужой красивый образ должен вдохновлять открыть свою примерочную, но кнопка
// не должна обещать точное копирование, которого этот переход не выполняет.
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
await page.waitForFunction(() => typeof openGlobalProfile === 'function');
await page.mouse.click(195, 700);
await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');
await page.evaluate(() => openGlobalProfile(999));
await page.waitForFunction(() => document.querySelector('#mb .gp-card'));

const state = await page.evaluate(() => {
  const buttons = [...document.querySelectorAll('#mb > button')];
  const outfitButton = buttons.find(button => button.getAttribute('onclick')?.includes('openLooksModal'));
  const avatar = document.querySelector('#mb .gp-card .ava');
  const avatarImage = avatar?.querySelector('img');
  return {
    outfitCount: document.querySelectorAll('#mb .gp-card .gp-chips .gp-chip').length,
    label: outfitButton?.textContent.replace(/\s+/g, ' ').trim() || '',
    hasGiftAction: buttons.some(button => button.textContent.includes('Подарить косметику')),
    avatarImageWidth: avatarImage?.naturalWidth || 0,
    avatarFallback: avatar?.textContent.trim() || '',
  };
});

console.log('Public-profile outfit action:', JSON.stringify(state));
check('public profile visibly presents the equipped look', state.outfitCount > 0);
check('preview profile uses a legible avatar or intentional fallback', state.avatarImageWidth >= 32 || !!state.avatarFallback);
check('outfit action invites self-expression without promising an exact copy', state.label === '🎨 Собрать свой образ');
check('transparent gift action remains available', state.hasGiftAction);

await page.evaluate(() => {
  const gift = [...document.querySelectorAll('#mb > button')]
    .find(button => button.textContent.includes('Подарить косметику'));
  gift?.click();
});
await page.waitForFunction(() => document.getElementById('mt')?.textContent.includes('Подарить косметику'));
await page.waitForFunction(() => !document.querySelector('#mb .loader'));
const giftState = await page.evaluate(() => {
  const cards = [...document.querySelectorAll('#mb .looks-card')];
  const purchaseButtons = [...document.querySelectorAll('#mb .looks-card button:not([disabled])')];
  const body = document.getElementById('mb');
  const grid = document.querySelector('#mb .gift-cards');
  return {
    cardCount: cards.length,
    hasTransparentChargeCopy: /Списываются твои.*Зарники/.test(document.getElementById('mb')?.textContent || ''),
    allItemsNamed: cards.length > 0 && cards.every(card => !!card.querySelector('.lc-name')?.textContent.trim()),
    allItemsPricedOrOwned: cards.length > 0 && cards.every(card => {
      const text = card.textContent || '';
      return /\d+\s*✨/.test(text) || /есть/.test(text);
    }),
    minPurchaseHeight: purchaseButtons.length
      ? Math.round(Math.min(...purchaseButtons.map(button => button.getBoundingClientRect().height)))
      : 0,
    purchaseNamesAreDescriptive: purchaseButtons.length > 0 && purchaseButtons.every(button => {
      const itemName = button.closest('.looks-card')?.querySelector('.lc-name')?.textContent.trim() || '';
      const label = button.getAttribute('aria-label') || '';
      return !!itemName && label.includes(itemName) && /\d+/.test(label) && /Зарник/.test(label);
    }),
    gridColumns: grid ? getComputedStyle(grid).gridTemplateColumns.split(' ').length : 0,
    minCardWidth: cards.length ? Math.round(Math.min(...cards.map(card => card.getBoundingClientRect().width))) : 0,
    minSwatchHeight: cards.length ? Math.round(Math.min(...cards.map(card => card.querySelector('.lc-sw')?.getBoundingClientRect().height || 0))) : 0,
    pricesUsePills: purchaseButtons.length > 0 && purchaseButtons.every(button =>
      parseFloat(getComputedStyle(button).borderRadius) >= 20),
    visualPriceMaxHeight: purchaseButtons.length
      ? Math.round(Math.max(...purchaseButtons.map(button => button.querySelector('.gift-buy-pill')?.getBoundingClientRect().height || 0)))
      : 0,
    noHorizontalOverflow: !!body && body.scrollWidth <= body.clientWidth,
  };
});
console.log('Gift catalog:', JSON.stringify(giftState));
check('gift catalog contains realistic cosmetic choices', giftState.cardCount >= 4);
check('gift flow explains whose currency is charged', giftState.hasTransparentChargeCopy);
check('every gift is named and has an explicit price or owned state', giftState.allItemsNamed && giftState.allItemsPricedOrOwned);
check('gift purchase buttons keep a 44px mobile touch target', giftState.minPurchaseHeight >= 44);
check('gift purchase buttons name the cosmetic and price for assistive tech', giftState.purchaseNamesAreDescriptive);
check('gift catalog uses a readable two-column mobile composition', giftState.gridColumns === 2 && giftState.minCardWidth >= 130);
check('gift cosmetics get a stronger visual preview', giftState.minSwatchHeight >= 64);
check('gift prices use compact premium pills instead of heavy square buttons', giftState.pricesUsePills);
check('gift price fill stays visually compact inside the larger touch target', giftState.visualPriceMaxHeight >= 32 && giftState.visualPriceMaxHeight <= 36);
check('gift catalog stays inside the mobile sheet', giftState.noHorizontalOverflow);

const noFxPriceSheen = await page.evaluate(() => {
  document.body.classList.add('no-fx');
  const pill = document.querySelector('#mb .gift-buy-pill');
  const stopped = pill ? getComputedStyle(pill, '::after').animationName === 'none' : false;
  document.body.classList.remove('no-fx');
  return stopped;
});
check('gift price sheen respects the in-game reduced-effects setting', noFxPriceSheen);

await page.emulateMediaFeatures([{name: 'prefers-reduced-motion', value: 'reduce'}]);
check('gift price sheen respects the system reduced-motion setting', await page.evaluate(() => {
  const pill = document.querySelector('#mb .gift-buy-pill');
  return pill ? getComputedStyle(pill, '::after').animationName === 'none' : false;
}));
await page.emulateMediaFeatures([{name: 'prefers-reduced-motion', value: 'no-preference'}]);

await page.click('#mb .gift-cards .looks-card button:not([disabled])');
await page.waitForFunction(() => !document.getElementById('modal')?.open);
check('local gift purchase completes and confirms the action', await page.evaluate(() =>
  (document.getElementById('toast')?.textContent || '').includes('Подарок отправлен')));

await page.evaluate(() => openGlobalProfile(999));
await page.waitForFunction(() => document.querySelector('#mb .gp-card'));
await page.click('#mb > button[onclick*="openLooksModal"]');
await page.waitForFunction(() => document.getElementById('pg-looks')?.classList.contains('active'));
check('outfit action opens the appearance flow', await page.evaluate(() => _activePage === 'looks'));

await browser.close();
if (failures.length) {
  console.error(`\n${failures.length} public-profile outfit action check(s) failed.`);
  process.exit(1);
}
console.log('\nALL OK');
