// При body.no-fx (и при системном prefers-reduced-motion) все новые
// keyframe-анимации иконок должны быть отключены
// (DESIGN_RULES.md §8 — открытый пункт, закрывается здесь).
import puppeteer from 'puppeteer';
const FAIL = [];
function check(name, cond) { if (!cond) FAIL.push(name); else console.log('OK:', name); }

async function checkAnims(page) {
  return page.evaluate(() => {
    const results = [];
    document.querySelectorAll('.coll-card, .coll-card *').forEach(el => {
      const cs = getComputedStyle(el);
      if (cs.animationName && cs.animationName !== 'none') results.push({ tag: el.tagName, cls: el.className, anim: cs.animationName });
    });
    return results;
  });
}

// Проход 1: ручной тумблер body.no-fx
{
  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await page.goto('http://localhost:8402/', { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 1500));
  await page.mouse.click(195, 700);
  await new Promise(r => setTimeout(r, 500));
  await page.evaluate(() => document.body.classList.add('no-fx'));
  await page.evaluate(() => openLooksModal());
  await new Promise(r => setTimeout(r, 800));

  const anims = await checkAnims(page);
  check('под body.no-fx ни один элемент иконок не анимируется', anims.length === 0);
  if (anims.length) console.log('still animating (no-fx):', JSON.stringify(anims));

  await browser.close();
}

// Проход 2: системная настройка prefers-reduced-motion, без ручного тумблера
{
  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();
  await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await page.goto('http://localhost:8402/', { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 1500));
  await page.mouse.click(195, 700);
  await new Promise(r => setTimeout(r, 500));
  await page.evaluate(() => openLooksModal());
  await new Promise(r => setTimeout(r, 800));

  const anims = await checkAnims(page);
  check('под prefers-reduced-motion ни один элемент иконок не анимируется', anims.length === 0);
  if (anims.length) console.log('still animating (prefers-reduced-motion):', JSON.stringify(anims));

  await browser.close();
}

if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
