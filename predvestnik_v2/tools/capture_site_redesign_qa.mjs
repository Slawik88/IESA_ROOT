import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer';

const phase = process.argv[2] || 'after';
if (!/^(before|after)$/.test(phase)) throw new Error('phase must be before or after');

const out = path.resolve(`docs/audits/2026-08-11-site-redesign/${phase}`);
fs.mkdirSync(out, { recursive: true });

const chromium = process.env.PUPPETEER_EXECUTABLE_PATH;
const launch = chromium ? { headless: 'new', executablePath: chromium } : { headless: 'new' };
const screens = [
  { page: 'profile', label: 'profile' },
  { page: 'zoo', label: 'zoo' },
  { page: 'arena', label: 'arena' },
  { page: 'market', label: 'market' },
  { page: 'more', label: 'more' },
];
const widths = [320, 390, 430];
const evidence = [];
const browser = await puppeteer.launch(launch);

try {
  for (const width of widths) {
    for (const screen of screens) {
      const page = await browser.newPage();
      const consoleErrors = [];
      page.on('console', message => {
        if (message.type() === 'error') consoleErrors.push(message.text());
      });
      await page.setViewport({ width, height: 844, deviceScaleFactor: 1 });
      await page.goto('http://localhost:8402/', { waitUntil: 'load' });
      await page.waitForFunction(() => typeof switchPage === 'function');
      await page.evaluate(pageName => {
        const preloader = document.getElementById('preloader');
        if (preloader) preloader.style.display = 'none';
        switchPage(pageName);
        window.scrollTo(0, 0);
      }, screen.page);
      await new Promise(resolve => setTimeout(resolve, 900));

      const metrics = await page.evaluate(() => {
        const active = document.querySelector('.page.active');
        const visibleTargets = [...document.querySelectorAll('.page.active button, .page.active [onclick], .page.active summary')]
          .filter(node => {
            const rect = node.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && node.offsetParent !== null;
          })
          .map(node => {
            const rect = node.getBoundingClientRect();
            return {
              label: (node.textContent || node.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 60),
              width: Math.round(rect.width),
              height: Math.round(rect.height),
            };
          });
        return {
          activePage: active?.id || null,
          viewportWidth: innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          scrollHeight: document.documentElement.scrollHeight,
          smallTargets: visibleTargets.filter(target => target.width < 44 || target.height < 44),
          cards: active?.querySelectorAll('.card, .hero, .profile-showcase-card, .pcard, .bk-card, .shop-row, .cc-card').length || 0,
        };
      });

      const file = `${screen.label}-${width}.png`;
      await page.screenshot({ path: path.join(out, file), fullPage: true });
      evidence.push({ ...screen, width, file, metrics, consoleErrors });
      await page.close();
    }
  }
} finally {
  await browser.close();
}

fs.writeFileSync(path.join(out, 'evidence.json'), JSON.stringify(evidence, null, 2));
console.log(JSON.stringify(evidence, null, 2));
