import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer';

const base = process.env.PREVIEW_URL || 'http://localhost:8402';
const chromium = process.env.PUPPETEER_EXECUTABLE_PATH;
const evidenceDir = process.env.BOTTOM_NAV_EVIDENCE_DIR
  ? path.resolve(process.env.BOTTOM_NAV_EVIDENCE_DIR)
  : '/tmp';
fs.mkdirSync(evidenceDir, { recursive: true });
const evidencePath = name => path.join(evidenceDir, name);
const browser = await puppeteer.launch(
  chromium ? { headless: 'new', executablePath: chromium } : { headless: 'new' },
);
const failures = [];
const evidence = [];
const check = (condition, message) => {
  if (!condition) failures.push(message);
};

try {
  for (const width of [320, 390, 611, 1024]) {
    const page = await browser.newPage();
    const runtimeErrors = [];
    page.on('pageerror', error => runtimeErrors.push(error.message));
    await page.setViewport({ width, height: 755, deviceScaleFactor: 1 });
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof switchPage === 'function');
    await page.evaluate(() => {
      if (typeof _plSkip === 'function') _plSkip();
      const preloader = document.getElementById('preloader');
      if (preloader) preloader.style.display = 'none';
      switchPage('profile');
      scrollTo(0, 0);
    });
    await new Promise(resolve => setTimeout(resolve, 350));

    const metrics = await page.evaluate(() => {
      const dock = document.querySelector('.nav');
      const dockRect = dock.getBoundingClientRect();
      const items = [...dock.querySelectorAll('.nb')].map(item => {
        const rect = item.getBoundingClientRect();
        return { width: rect.width, height: rect.height };
      });
      return {
        viewportWidth: innerWidth,
        pageWidth: document.documentElement.scrollWidth,
        left: dockRect.left,
        right: dockRect.right,
        dockWidth: dockRect.width,
        bottomGap: innerHeight - dockRect.bottom,
        centerDelta: Math.abs((dockRect.left + dockRect.right) / 2 - innerWidth / 2),
        items,
      };
    });

    const expectedWidth = Math.min(width - 18, 482);
    check(metrics.pageWidth === width, `${width}px: page has horizontal overflow (${metrics.pageWidth}px)`);
    check(metrics.left >= 0 && metrics.right <= width, `${width}px: dock is clipped (${metrics.left}..${metrics.right})`);
    check(Math.abs(metrics.dockWidth - expectedWidth) <= 1, `${width}px: dock width is ${metrics.dockWidth}, expected ${expectedWidth}`);
    check(metrics.centerDelta <= 1, `${width}px: dock is not centered (${metrics.centerDelta}px)`);
    check(metrics.bottomGap >= 8, `${width}px: dock bottom gap is too small (${metrics.bottomGap}px)`);
    check(metrics.items.length === 5, `${width}px: expected five dock items`);
    check(metrics.items.every(item => item.width >= 55 && item.height >= 50), `${width}px: dock target is too small`);

    for (const pageName of ['profile', 'zoo', 'arena', 'market', 'more']) {
      await page.evaluate(() => {
        const modal = document.getElementById('modal');
        if (modal?.open && typeof CM === 'function') CM();
        switchPage('profile');
      });
      await new Promise(resolve => setTimeout(resolve, 100));
      await page.click(`.nb[data-page="${pageName}"]`, { delay: 35 });
      await new Promise(resolve => setTimeout(resolve, 300));
      const state = await page.evaluate(name => ({
        activeDock: document.querySelector('.nb.active')?.dataset.page || '',
        activePage: document.querySelector('.page.active')?.id || '',
        dockVisible: document.querySelector('.nav')?.getBoundingClientRect().bottom <= innerHeight,
      }), pageName);
      check(state.activeDock === pageName, `${width}px: ${pageName} does not activate its dock item`);
      check(state.activePage === `pg-${pageName}`, `${width}px: ${pageName} does not open its page`);
      check(state.dockVisible, `${width}px: dock leaves the viewport after opening ${pageName}`);
    }

    check(runtimeErrors.length === 0, `${width}px: runtime errors: ${runtimeErrors.join('; ')}`);
    if (width === 611) {
      await page.evaluate(() => {
        const modal = document.getElementById('modal');
        if (modal?.open && typeof CM === 'function') CM();
        switchPage('profile');
      });
      await new Promise(resolve => setTimeout(resolve, 220));
      await page.screenshot({ path: evidencePath('bottom-nav-after-611.png') });
      await page.screenshot({
        path: evidencePath('bottom-nav-after-focused-611.png'),
        clip: { x: 0, y: 645, width: 611, height: 110 },
      });
      await page.addStyleTag({ content: `
        @media (min-width: 520px) {
          .nav { left: 9px !important; right: 9px !important; width: 482px !important; transform: translateX(-50%) !important; }
        }
      ` });
      await page.screenshot({ path: evidencePath('bottom-nav-source-reproduction-611.png') });
      await page.screenshot({
        path: evidencePath('bottom-nav-source-focused-611.png'),
        clip: { x: 0, y: 645, width: 611, height: 110 },
      });
    }
    evidence.push({ width, ...metrics, runtimeErrors });
    await page.close();
  }
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(failures.map(failure => `FAIL ${failure}`).join('\n'));
  process.exit(1);
}

console.log(JSON.stringify(evidence, null, 2));
console.log('OK: bottom dock geometry and all five destinations verified at 320/390/611/1024px');
