#!/usr/bin/env node
import puppeteer from 'puppeteer';

const base = process.env.PREVIEW_BASE || 'http://127.0.0.1:8402';
const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH;
const browser = await puppeteer.launch({
  headless: true,
  executablePath,
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
});

try {
  for (const width of [320, 390, 430]) {
    const page = await browser.newPage();
    const pageErrors = [];
    page.on('pageerror', (error) => pageErrors.push(error.message));
    await page.setViewport({ width, height: 844, deviceScaleFactor: 1 });
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.nb[data-page="arena"]');
    const preloaderVisible = await page.evaluate(() => {
      const node = document.getElementById('preloader');
      return Boolean(node && getComputedStyle(node).display !== 'none');
    });
    if (preloaderVisible) {
      await page.evaluate(() => document.getElementById('preloader')?.click());
      await page.waitForFunction(() => {
        const node = document.getElementById('preloader');
        return !node || node.classList.contains('pl-done');
      });
    }
    await page.click('.nb[data-page="arena"]');
    try {
      await page.waitForSelector('#ar-game .recon-entry-card', { timeout: 5000 });
    } catch (error) {
      const state = await page.evaluate(() => ({
        activePage: document.querySelector('.page.active')?.id || null,
        hubHtml: document.getElementById('game-hub')?.innerHTML || null,
        loginVisible: !document.getElementById('login-ov')?.classList.contains('hidden'),
      }));
      throw new Error(`${width}px: game hub did not render; ${JSON.stringify({ state, pageErrors })}`);
    }

    const audit = await page.evaluate(() => {
      const pageNode = document.getElementById('pg-arena');
      const action = document.querySelector('.recon-entry-action');
      const labels = [...document.querySelectorAll('#pg-arena .tabs .tb')]
        .map((node) => node.textContent.trim());
      return {
        labels,
        pageVisible: pageNode.classList.contains('active'),
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        actionWidth: action.getBoundingClientRect().width,
        viewportWidth: document.documentElement.clientWidth,
      };
    });

    if (!audit.pageVisible) throw new Error(`${width}px: game page is not active`);
    if (audit.labels.join('|') !== '🔔 Разлом|🎮 Игры|🎪 Ивенты') {
      throw new Error(`${width}px: legacy combat tabs remain: ${audit.labels.join(', ')}`);
    }
    if (audit.overflow > 1) throw new Error(`${width}px: horizontal overflow ${audit.overflow}px`);
    if (audit.actionWidth > Math.min(220, audit.viewportWidth - 36)) {
      throw new Error(`${width}px: primary action is oversized (${audit.actionWidth}px)`);
    }

    await Promise.all([
      page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
      page.click('.recon-entry-action'),
    ]);
    await page.waitForSelector('#menuLayer');
    const gamePath = new URL(page.url()).pathname;
    if (gamePath !== '/game') throw new Error(`${width}px: expected /game, got ${gamePath}`);
    await page.close();
  }
  console.log('OK: new game entry replaces legacy tabs at 320/390/430px and opens /game');
} finally {
  await browser.close();
}
