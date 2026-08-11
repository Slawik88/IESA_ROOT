import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer';

const out = path.resolve('docs/audits/2026-08-11-site-redesign/secondary');
fs.mkdirSync(out, { recursive: true });

const chromium = process.env.PUPPETEER_EXECUTABLE_PATH;
const states = [
  { label: 'profile-inventory', action: `switchPage('profile'); document.querySelector("#pg-profile > .tabs .tb[onclick*='inv']")?.click()` },
  { label: 'profile-themes', action: `switchPage('profile'); document.querySelector("#pg-profile > .tabs .tb[onclick*='themes']")?.click()` },
  { label: 'profile-quests', action: `goTo('quests')` },
  { label: 'profile-achievements', action: `goTo('ach')` },
  { label: 'profile-top', action: `goTo('hof')` },
  { label: 'looks', action: `openLooksModal()` },
  { label: 'zoo-bestiary', action: `goTo('bestiary')` },
  { label: 'arena-gates', action: `goTo('arena','gates')` },
  { label: 'arena-raids', action: `goTo('arena','raids')` },
  { label: 'arena-games', action: `goTo('arena','games')` },
  { label: 'arena-events', action: `goTo('arena','events')` },
  { label: 'market-vip', action: `goTo('market','vip')` },
  { label: 'market-goods', action: `goTo('market','goods')` },
  { label: 'market-deal', action: `goTo('market','deal')` },
  { label: 'auction', action: `switchPage('auction')` },
  { label: 'battle-pass', action: `switchPage('bp')` },
  { label: 'help', action: `switchPage('help')` },
  { label: 'admin', action: `switchPage('admin')` },
  { label: 'global', action: `switchPage('global')` },
  { label: 'console', action: `switchPage('console')` },
];

const browser = await puppeteer.launch(chromium ? { headless: 'new', executablePath: chromium } : { headless: 'new' });
const evidence = [];
try {
  for (const state of states) {
    const page = await browser.newPage();
    const errors = [];
    page.on('console', message => {
      if (message.type() === 'error') errors.push(message.text());
    });
    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await page.goto('http://localhost:8402/', { waitUntil: 'load' });
    await page.waitForFunction(() => typeof switchPage === 'function');
    await page.evaluate(action => {
      const preloader = document.getElementById('preloader');
      if (preloader) preloader.style.display = 'none';
      // Controlled local QA actions declared in this script.
      window.eval(action);
    }, state.action);
    await new Promise(resolve => setTimeout(resolve, 1400));
    const metrics = await page.evaluate(() => ({
      activePage: document.querySelector('.page.active')?.id || null,
      width: innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      scrollHeight: document.documentElement.scrollHeight,
      visibleDialogs: [...document.querySelectorAll('dialog')].filter(dialog => dialog.open).length,
      imagesBroken: [...document.images].filter(image => image.complete && !image.naturalWidth).length,
    }));
    const file = `${state.label}.png`;
    await page.screenshot({ path: path.join(out, file), fullPage: true });
    evidence.push({ label: state.label, file, metrics, errors });
    await page.close();
  }
} finally {
  await browser.close();
}

fs.writeFileSync(path.join(out, 'evidence.json'), JSON.stringify(evidence, null, 2));
console.log(JSON.stringify(evidence, null, 2));
