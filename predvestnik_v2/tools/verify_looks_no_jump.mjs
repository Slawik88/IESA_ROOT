// Задача 6: переключатель режимов и ряд действий под превью не должны физически
// сдвигаться при переключении «По коллекциям»/«По слотам» и при примерке предмета.
// Фикс (после отката 1-й версии, которая ломала тап по карточкам коллекций —
// см. app.10.js): переключатель рендерится ДО .looks-sticky, а не после — его
// позиция вообще не зависит от того, что внутри прилипающего превью. Умный ряд
// фильтра остаётся строго условным (не в DOM в «По коллекциям»), место под него
// НЕ резервируется.
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

// Сценарий 2: умный ряд фильтра строго условный (НЕТ в DOM вне "По слотам") —
// место под него НЕ резервируется (резервирование ломало клики по карточкам
// коллекций на 390×844, см. комментарий в app.10.js::renderLooks). Прыжок
// переключателя чинится по-другому (Сценарий 1) — позицией ДО .looks-sticky.
await page.click('[data-mode="collections"]');
await new Promise(r => setTimeout(r, 300));
const barAbsence = await page.evaluate(() => !document.getElementById('looks-filter-bar'));
check('умный ряд фильтра НЕ в DOM в режиме "По коллекциям" (место не резервируется)', barAbsence);

// Сценарий 2b (регресс-тест реальной поломки, найденной этой же задачей): реальный
// клик мышью (не JS .click(), а настоящее hit-testing) по карточке коллекции ВО
// ВТОРОМ РЯДУ сетки (inferno) должен открывать детальный экран. Первая версия
// фикса резервировала место под умный ряд даже в "По коллекциям" — .looks-sticky
// становился выше, вторая строка карточек уезжала под нижнюю навигацию (.nb),
// и реальный клик попадал в таб навигации, а не в карточку (JS .click() этого
// не ловит — он не делает hit-testing, поэтому нужен именно page.click()).
await page.click('.coll-card[data-lineup="inferno"]');
await new Promise(r => setTimeout(r, 400));
const infernoOpened = await page.evaluate(() => _looksDetailLineup === 'inferno');
check('реальный клик по карточке "Инферно" (2-й ряд сетки) открывает детальный экран', infernoOpened);
await page.click('.coll-detail-back');
await new Promise(r => setTimeout(r, 300));

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
