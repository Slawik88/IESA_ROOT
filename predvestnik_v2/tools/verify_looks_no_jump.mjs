// Задача 6: переключатель режимов и ряд действий под превью не должны физически
// сдвигаться при переключении «По коллекциям»/«По слотам» и при примерке предмета.
import puppeteer from 'puppeteer';
const FAIL = [];
function check(name, cond) { if (!cond) FAIL.push(name); else console.log('OK:', name); }
const browser = await puppeteer.launch({ headless: 'new' });
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await page.goto('http://localhost:8402/', { waitUntil: 'load' });
await new Promise(r => setTimeout(r, 1500));
await page.mouse.click(195, 700);
await new Promise(r => setTimeout(r, 500));
await page.evaluate(() => openLooksModal());
await new Promise(r => setTimeout(r, 800));

// Сценарий 1: переключатель режимов не должен менять свой Y при клике по нему самому
const toggleYBefore = await page.evaluate(() => document.getElementById('looks-mode-toggle').getBoundingClientRect().y);
await page.click('[data-mode="slots"]');
await new Promise(r => setTimeout(r, 300));
const toggleYAfterSlots = await page.evaluate(() => document.getElementById('looks-mode-toggle').getBoundingClientRect().y);
await page.click('[data-mode="collections"]');
await new Promise(r => setTimeout(r, 300));
const toggleYAfterBack = await page.evaluate(() => document.getElementById('looks-mode-toggle').getBoundingClientRect().y);
check('переключатель режимов НЕ сдвигается при переходе в "По слотам"', toggleYBefore === toggleYAfterSlots);
check('переключатель режимов НЕ сдвигается при возврате в "По коллекциям"', toggleYBefore === toggleYAfterBack);

// Сценарий 2: умный ряд всегда в DOM (скрыт визуально, не удалён)
const barPresence = await page.evaluate(() => ({
  existsInCollections: !!document.getElementById('looks-filter-bar'),
  hiddenInCollections: document.getElementById('looks-filter-bar').classList.contains('sr-hidden'),
}));
check('умный ряд фильтра существует в DOM в режиме "По коллекциям" (просто скрыт)', barPresence.existsInCollections);
check('умный ряд фильтра скрыт классом sr-hidden в режиме "По коллекциям"', barPresence.hiddenInCollections);

// Сценарий 3: ряд действий под превью не сдвигает переключатель режимов при примерке предмета
// (переключаемся в slots, тапаем "Без" по слоту title — там уже надет cos_title_dawnchild,
// поэтому клик реально снимает предмет: _looksUnequip('title') меняет _looksSel.title на null
// и _looksFocus на null — ряд действий переходит .looks-ba-hint → .looks-ba-act (2 кнопки),
// без байбара (он вне скоупа задачи). Тап по уже надетой карточке был бы вакуумным —
// _looksSel не менялся бы и ряд действий не переключался бы вовсе.)
await page.click('[data-mode="slots"]');
await new Promise(r => setTimeout(r, 300));
const toggleYBeforeTap = await page.evaluate(() => document.getElementById('looks-mode-toggle').getBoundingClientRect().y);
await page.evaluate(() => {
  const noneCard = document.querySelector('#looks-grid-title [data-cos="__none__"]');
  if (noneCard) noneCard.click();
});
await new Promise(r => setTimeout(r, 300));
const toggleYAfterTap = await page.evaluate(() => document.getElementById('looks-mode-toggle').getBoundingClientRect().y);
check('переключатель режимов НЕ сдвигается при примерке предмета (ряд действий меняется)', toggleYBeforeTap === toggleYAfterTap);

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
