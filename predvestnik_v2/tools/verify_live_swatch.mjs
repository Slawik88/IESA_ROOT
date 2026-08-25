// Живой свотч: анимация включается только для карточек в видимой области.
import puppeteer from 'puppeteer';

const FAIL = [];
function check(name, cond) {
  if (!cond) FAIL.push(name);
  else console.log('OK:', name);
}

const browser = await puppeteer.launch({ headless: 'new' });
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await page.goto('http://localhost:8402/', { waitUntil: 'load' });
await new Promise(resolve => setTimeout(resolve, 1500));
await page.waitForFunction(() => typeof _plSkip === 'function');
await page.evaluate(() => _plSkip());
await page.waitForFunction(() => !document.getElementById('preloader'));
await new Promise(resolve => setTimeout(resolve, 500));
await page.evaluate(() => openLooksModal());
await new Promise(resolve => setTimeout(resolve, 400));
await page.click('[data-mode="slots"]');
await new Promise(resolve => setTimeout(resolve, 500));
await page.$eval('#looks-sec-name_glow .looks-card[data-cos="cos_name_glow_neon"]', card =>
  card.scrollIntoView({block: 'center'}));
await new Promise(resolve => setTimeout(resolve, 300));

const state = await page.evaluate(() => {
  const visible = document.querySelector('#looks-sec-name_glow .looks-card[data-cos="cos_name_glow_neon"]');
  const swatch = visible?.querySelector('.lc-sw .lc-nick') || null;
  document.body.classList.add('no-fx');
  const noFxAnimationName = swatch ? getComputedStyle(swatch).animationName : null;
  document.body.classList.remove('no-fx');
  return {
    hasVisibleLive: !!visible?.classList.contains('lc-sw-live'),
    animationName: swatch ? getComputedStyle(swatch).animationName : null,
    noFxAnimationName,
  };
});

check('хотя бы одна видимая карточка помечена .lc-sw-live', state.hasVisibleLive);
check('у видимой карточки анимация эффекта не отключена', state.animationName && state.animationName !== 'none');

check('no-fx disables a live swatch animation', state.noFxAnimationName === 'none');
await page.emulateMediaFeatures([{name: 'prefers-reduced-motion', value: 'reduce'}]);
const reducedAnimationName = await page.$eval(
  '#looks-sec-name_glow .looks-card[data-cos="cos_name_glow_neon"] .lc-sw .lc-nick',
  swatch => getComputedStyle(swatch).animationName,
);
await page.emulateMediaFeatures([]);
check('prefers-reduced-motion disables a live swatch animation', reducedAnimationName === 'none');

await browser.close();
if (FAIL.length) {
  console.error('FAIL:', FAIL);
  process.exit(1);
}
console.log('ALL OK');
