import puppeteer from 'puppeteer';

const chromium = process.env.PUPPETEER_EXECUTABLE_PATH;
const browser = await puppeteer.launch(chromium ? { headless: 'new', executablePath: chromium } : { headless: 'new' });
const failures = [];
const check = (condition, message) => {
  if (!condition) failures.push(message);
};

try {
  for (const width of [320, 390, 430]) {
    const page = await browser.newPage();
    await page.setViewport({ width, height: 844, deviceScaleFactor: 1 });
    await page.goto('http://localhost:8402/', { waitUntil: 'load' });
    await page.waitForFunction(() => typeof switchPage === 'function');
    await page.evaluate(() => {
      const preloader = document.getElementById('preloader');
      if (preloader) preloader.style.display = 'none';
      switchPage('profile');
      loadProfile();
      scrollTo(0, 0);
    });
    await page.waitForSelector('.profile-showcase-card');
    await new Promise(resolve => setTimeout(resolve, 450));

    const state = await page.evaluate(() => {
      const card = document.querySelector('.profile-showcase-card');
      const canvas = document.querySelector('.character-showcase-area');
      const main = document.querySelector('.profile-showcase-main');
      const fitting = document.querySelector('.showcase-fitting-button');
      const style = node => node ? getComputedStyle(node) : null;
      return {
        pageWidth: document.documentElement.scrollWidth,
        viewportWidth: innerWidth,
        cardWidth: card?.getBoundingClientRect().width || 0,
        canvasHeight: canvas?.getBoundingClientRect().height || 0,
        mainColumns: style(main)?.gridTemplateColumns || '',
        railItems: document.querySelectorAll('.player-data-rail .player-rail-item').length,
        resources: document.querySelectorAll('.profile-resource-rail .stat').length,
        fittingText: fitting?.textContent.replace(/\s+/g, ' ').trim() || '',
        fittingHeight: fitting?.getBoundingClientRect().height || 0,
        actionHeights: [...document.querySelectorAll('.profile-card-actions button')].map(button => button.getBoundingClientRect().height),
        hasFrame: !!document.querySelector('.profile-showcase-card #pro-ava.frame-oak'),
        hasGlow: !!document.querySelector('.profile-showcase-card .pname.glow-moon'),
        cardShadow: style(card)?.boxShadow || '',
      };
    });

    const tag = `${width}px`;
    check(state.pageWidth === state.viewportWidth, `${tag}: page has horizontal overflow`);
    check(state.cardWidth > width - 32, `${tag}: player card does not use the available width`);
    check(state.canvasHeight >= 268, `${tag}: customization canvas is not spacious enough`);
    check(state.mainColumns.split(' ').filter(Boolean).length >= 2, `${tag}: canvas and data rail are not laid out side-by-side`);
    check(state.railItems === 4, `${tag}: data rail must show power, level, streak, and achievements`);
    check(state.resources === 4, `${tag}: resource rail must preserve four balances/achievement tiles`);
    check(state.fittingText.includes('Примерочная'), `${tag}: fitting room is not clearly named in the player card`);
    check(state.fittingHeight >= 44, `${tag}: fitting-room action is below the 44px mobile target`);
    check(state.actionHeights.length === 3 && state.actionHeights.every(height => height >= 44), `${tag}: profile utility actions are not mobile-safe`);
    check(state.hasFrame && state.hasGlow, `${tag}: equipped cosmetic layers were lost in the new card`);
    check(state.cardShadow === 'none', `${tag}: neutral player card gained a heavy base shadow`);

    await page.click('.character-showcase-area');
    await page.waitForFunction(() => document.querySelector('#pg-looks')?.classList.contains('active'));
    const looksWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    check(looksWidth === width, `${tag}: fitting-room page overflows after opening from the canvas`);
    await page.close();
  }

  const page = await browser.newPage();
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.goto('http://localhost:8402/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof switchPage === 'function');
  await page.evaluate(() => {
    const preloader = document.getElementById('preloader');
    if (preloader) preloader.style.display = 'none';
  });
  for (const name of ['profile', 'zoo', 'arena', 'market', 'more', 'auction', 'bp', 'help']) {
    await page.evaluate(pageName => { switchPage(pageName); scrollTo(0, 0); }, name);
    await new Promise(resolve => setTimeout(resolve, 500));
    const screen = await page.evaluate(pageName => ({
      active: document.querySelector('.page.active')?.id,
      width: document.documentElement.scrollWidth,
      expected: `pg-${pageName}`,
    }), name);
    check(screen.active === screen.expected, `${name}: navigation did not activate the expected page`);
    check(screen.width === 390, `${name}: shared redesign causes horizontal overflow`);
  }
  await page.close();
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(failures.map(failure => `FAIL ${failure}`).join('\n'));
  process.exit(1);
}

console.log('OK: hybrid player showcase and shared site redesign verified at 320/390/430px');
