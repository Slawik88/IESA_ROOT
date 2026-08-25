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
await page.waitForFunction(() => typeof openLooksModal === 'function');
await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');
await page.waitForFunction(() => typeof _plSkip === 'function');
await page.evaluate(() => _plSkip());
await page.waitForFunction(() => !document.getElementById('preloader'));
await page.evaluate(() => openLooksModal());
await new Promise(resolve => setTimeout(resolve, 800));

await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));

const deepScroll = await page.evaluate(() => {
  const dock = document.getElementById('looks-dock');
  const button = dock?.querySelector('.looks-fab');
  const nav = document.querySelector('.nav');
  const finalContent = document.querySelector('#pg-looks .pay-terms');
  const rect = button?.getBoundingClientRect();
  const navRect = nav?.getBoundingClientRect();
  const finalContentRect = finalContent?.getBoundingClientRect();
  const hit = rect
    ? document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)?.closest('.looks-fab')
    : null;
  return {
    scrollY: window.scrollY,
    dockParentIsBody: dock?.parentElement === document.body,
    dockPosition: dock ? getComputedStyle(dock).position : null,
    buttonWidth: rect?.width || 0,
    buttonHeight: rect?.height || 0,
    buttonVisible: !!rect && rect.top >= 0 && rect.bottom <= window.innerHeight,
    clearOfNav: !!rect && !!navRect && rect.bottom <= navRect.top - 6,
    finalContentClear: !!rect && !!finalContentRect && finalContentRect.bottom <= rect.top - 12,
    hitTargetWorks: hit === button,
    hitTarget: hit?.className || null,
    buttonRect: rect ? {top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right} : null,
    navRect: navRect ? {top: navRect.top, bottom: navRect.bottom} : null,
  };
});

console.log('Deep-scroll fitting-room geometry:', JSON.stringify(deepScroll));

check('test reaches a deep part of the appearance page', deepScroll.scrollY > 500);
check('fitting-room dock is portaled outside the animated page', deepScroll.dockParentIsBody);
check('fitting-room dock is fixed to the viewport', deepScroll.dockPosition === 'fixed');
check('fitting-room action remains visible after a deep scroll', deepScroll.buttonVisible);
check('fitting-room action stays compact on the mobile viewport', deepScroll.buttonWidth >= 176 && deepScroll.buttonWidth <= 220);
check('fitting-room action keeps a 44px mobile touch target', deepScroll.buttonHeight >= 44);
check('fitting-room action stays above the bottom navigation', deepScroll.clearOfNav);
check('compact end spacing still keeps the final content above the fitting-room action', deepScroll.finalContentClear);
check('fitting-room action remains the real pointer target', deepScroll.hitTargetWorks);

if (process.env.SCREENSHOT_PATH) {
  await page.screenshot({path: process.env.SCREENSHOT_PATH});
}

await page.click('.looks-fab');
await new Promise(resolve => setTimeout(resolve, 200));
const sheetOpened = await page.evaluate(() => document.getElementById('modal')?.open
  && document.getElementById('mt')?.textContent.includes('Примерочная'));
check('deep-scroll fitting-room action opens the sheet', sheetOpened);

await page.evaluate(() => { CM(); switchPage('profile'); });
await page.waitForFunction(() => _activePage === 'profile');
const hiddenOutsideLooks = await page.evaluate(() => !document.querySelector('#looks-dock .looks-fab'));
check('fitting-room action disappears outside the appearance page', hiddenOutsideLooks);

// Имитируем поздний resolve загрузки каталога: renderLooks() в завершившемся
// промисе вызывает _looksRenderFab(), хотя игрок уже мог уйти со страницы.
await page.evaluate(() => _looksRenderFab());
const lateRenderHidden = await page.evaluate(() => !document.querySelector('#looks-dock .looks-fab'));
check('late appearance render cannot resurrect the fitting-room action on another page', lateRenderHidden);

await browser.close();
if (failures.length) {
  console.error(`\n${failures.length} fitting-room accessibility check(s) failed.`);
  process.exit(1);
}
console.log('\nALL OK');
