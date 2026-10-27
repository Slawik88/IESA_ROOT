// Скриншоты «образ × тир» без базы. Запуск (после dump_skins.py и build.js):
//   node shot.js forest,hanami,void D,B,S,SSS метка
// Результат: out/<метка>-<образ>-<тир>.png (390 px, масштаб 1.5, режим fx-7).
const fs = require('fs'), path = require('path');
const { chromium } = require(process.env.PW_NODE || '/opt/node-tools/node_modules/playwright');
(async () => {
  const exe = fs.readdirSync('/opt/pw-browsers').filter(d => /^chromium-/.test(d)).map(d => `/opt/pw-browsers/${d}/chrome-linux/chrome`).find(p => fs.existsSync(p));
  const browser = await chromium.launch({ executablePath: exe, args: ['--no-sandbox'] });
  const skins = (process.argv[2] || 'hanami').split(','), tiers = (process.argv[3] || 'D,B,S,SSS').split(','), tag = process.argv[4] || 'out';
  const outDir = path.join(__dirname, 'out'); fs.mkdirSync(outDir, { recursive: true });
  const ctx = await browser.newContext({ viewport: { width: 390, height: 520 }, deviceScaleFactor: 1.5, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(String(e).slice(0, 200))); page.on('console', m => { if (m.type() === 'error') errs.push('console:' + m.text().slice(0, 150)); });
  await page.goto('file://' + path.join(__dirname, 'build', 'page.html'));
  await page.waitForFunction(() => typeof window.render === 'function');
  await page.evaluate(() => { document.body.classList.add('fx-7'); });
  for (const s of skins) for (const t of tiers) {
    await page.evaluate(() => { document.getElementById('root').innerHTML = ''; });
    await page.evaluate(([s, t]) => window.render(s, t), [s, t]);
    await page.waitForTimeout(1200);
    await (await page.$('.cell')).screenshot({ path: path.join(outDir, `${tag}-${s}-${t}.png`) });
  }
  console.log('errors:', [...new Set(errs)].slice(0, 8));
  await browser.close();
})();
