// Снимки и DOM-геометрия основных мобильных экранов для автономного аудита
// компактности. Не является pass/fail-тестом: сохраняет доказательства для ревью.
import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
import puppeteer from 'puppeteer';

const base = (process.env.PREVIEW_URL || 'http://127.0.0.1:8402').replace(/\/$/, '');
const outputDir = process.env.AUDIT_OUTPUT || '/tmp/predvestnik-mobile-compactness-audit';
const screens = [
  {name: 'profile', open: () => switchPage('profile')},
  {name: 'pets', open: () => switchPage('zoo')},
  {name: 'arena', open: () => switchPage('arena')},
  {name: 'market', open: () => switchPage('market')},
  {name: 'more', open: () => switchPage('more')},
  {name: 'appearance', open: () => openLooksModal()},
];

await mkdir(outputDir, {recursive: true});
const browser = await puppeteer.launch({headless: 'new'});
const page = await browser.newPage();
await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
await page.goto(`${base}/`, {waitUntil: 'load'});
await page.waitForFunction(() => typeof switchPage === 'function' && typeof openLooksModal === 'function');
await page.mouse.click(195, 700);
await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');

const evidence = [];
for (const [index, screen] of screens.entries()) {
  await page.evaluate(() => {
    if (document.getElementById('modal')?.open && typeof CM === 'function') CM();
  });
  await page.evaluate(screen.open);
  await page.waitForFunction(name => document.getElementById(`pg-${name}`)?.classList.contains('active'), {},
    screen.name === 'pets' ? 'zoo' : screen.name === 'appearance' ? 'looks' : screen.name);
  await new Promise(resolve => setTimeout(resolve, 1000));

  const geometry = await page.evaluate(() => {
    const visible = node => {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > 0
        && rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < innerHeight;
    };
    const describe = node => {
      const rect = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      return {
        tag: node.tagName.toLowerCase(),
        id: node.id || '',
        className: typeof node.className === 'string' ? node.className : '',
        text: (node.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 90),
        position: style.position,
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        top: Math.round(rect.top),
        bottom: Math.round(rect.bottom),
        viewportAreaPct: Math.round(rect.width * rect.height / (innerWidth * innerHeight) * 1000) / 10,
      };
    };
    const persistent = [...document.querySelectorAll('body *')]
      .filter(visible)
      .filter(node => ['fixed', 'sticky'].includes(getComputedStyle(node).position))
      .map(describe)
      .filter(item => item.width >= 120 || item.height >= 44);
    const largeActions = [...document.querySelectorAll('button, a.btn, .btn, [role="button"]')]
      .filter(visible)
      .map(describe)
      .filter(item => item.width >= innerWidth * .82 || item.height >= 64)
      .sort((a, b) => b.viewportAreaPct - a.viewportAreaPct)
      .slice(0, 15);
    return {
      activePage: document.querySelector('.page.active')?.id || '',
      scrollHeight: document.documentElement.scrollHeight,
      persistent,
      largeActions,
      errors: window.__errs || [],
    };
  });

  const filename = `${String(index + 1).padStart(2, '0')}-${screen.name}.png`;
  await page.screenshot({path: path.join(outputDir, filename)});
  evidence.push({step: index + 1, screen: screen.name, screenshot: filename, ...geometry});
}

await browser.close();
await writeFile(path.join(outputDir, 'geometry.json'), JSON.stringify(evidence, null, 2), 'utf8');
console.log(JSON.stringify({outputDir, evidence}, null, 2));
