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
async function settledFrame(page) {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
async function stableY(page, selector) {
  let last=null, identicalFrames=0;
  for(let attempt=0; attempt<12; attempt++){
    await new Promise(resolve => setTimeout(resolve, 100));
    await settledFrame(page);
    const current=await page.evaluate(sel => document.querySelector(sel)?.getBoundingClientRect().y, selector);
    identicalFrames=current===last ? identicalFrames+1 : 0;
    if(identicalFrames>=2) return current;
    last=current;
  }
  throw new Error(`Layout did not settle for ${selector}`);
}
const browser = await puppeteer.launch({ headless: 'new' });
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await page.goto('http://localhost:8402/', { waitUntil: 'load' });
await new Promise(r => setTimeout(r, 1500));
await page.waitForFunction(() => typeof _plSkip === 'function');
await page.evaluate(() => _plSkip());
await page.waitForFunction(() => !document.getElementById('preloader'));
await new Promise(r => setTimeout(r, 500));
await page.evaluate(() => openLooksModal());
await new Promise(r => setTimeout(r, 800));

// Сценарий 1: переключатель режимов не должен менять свой Y при клике по нему самому
const toggleYBefore = await stableY(page, '#looks-mode-toggle');
await page.click('[data-mode="slots"]');
const toggleYAfterSlots = await stableY(page, '#looks-mode-toggle');
await page.click('[data-mode="collections"]');
const toggleYAfterBack = await stableY(page, '#looks-mode-toggle');
check('переключатель режимов НЕ сдвигается при переходе в "По слотам"', Math.abs(toggleYBefore - toggleYAfterSlots) < .5);
check('переключатель режимов НЕ сдвигается при возврате в "По коллекциям"', Math.abs(toggleYBefore - toggleYAfterBack) < .5);

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
// Карточка второй строки естественно находится ниже первого экрана после добавления
// примерочной, образов и полезных ссылок. Сначала скроллим её в безопасную зону над nav,
// затем проверяем именно реальный pointer tap, а не программный вызов обработчика.
await page.evaluate(() => document.querySelector('.coll-card[data-lineup="inferno"]')?.scrollIntoView({block:'center'}));
await page.click('.coll-card[data-lineup="inferno"]');
await new Promise(r => setTimeout(r, 400));
const infernoOpened = await page.evaluate(() => _looksDetailLineup === 'inferno');
check('реальный клик по карточке "Инферно" (2-й ряд сетки) открывает детальный экран', infernoOpened);
await page.click('.coll-detail-back');
await new Promise(r => setTimeout(r, 300));

// Сценарий 3: ряд действий под превью НЕ сдвигает контент ниже .looks-sticky при
// примерке предмета (переключаемся в slots, тапаем "Без" по слоту title — там уже
// надет cos_title_dawnchild, поэтому клик реально снимает предмет: _looksUnequip
// ('title') меняет _looksSel.title на null и _looksFocus на null — ряд действий
// переходит .looks-ba-hint → .looks-ba-act (2 кнопки), без байбара (вне скоупа
// задачи). Тап по уже надетой карточке был бы вакуумным.
//
// ВАЖНО: проверяем Y координату #looks-mode-body, НЕ #looks-mode-toggle — после
// финального ревью переключатель рендерится ДО .looks-sticky (Сценарий 1), поэтому
// его Y НИКОГДА не меняется от того, что внутри .looks-sticky, независимо от того,
// работает ли фикс min-height ряда действий или нет — проверка по toggle здесь была
// бы вакуумной (доказано: временный откат min-height не ронял её). #looks-mode-body
// идёт ПОСЛЕ .looks-sticky в потоке — его Y корректно отражает, действительно ли
// высота .looks-sticky осталась постоянной между состояниями ряда действий.
await page.click('[data-mode="slots"]');
await new Promise(r => setTimeout(r, 300));
const bodyYBeforeTap = await page.evaluate(() => document.getElementById('looks-mode-body').getBoundingClientRect().y);
await page.evaluate(() => {
  const noneCard = document.querySelector('#looks-grid-title [data-cos="__none__"]');
  if (noneCard) noneCard.click();
});
await new Promise(r => setTimeout(r, 300));
const bodyYAfterTap = await page.evaluate(() => document.getElementById('looks-mode-body').getBoundingClientRect().y);
check('контент под превью НЕ сдвигается при примерке предмета (ряд действий меняется, min-height одинаковый)', bodyYBeforeTap === bodyYAfterTap);

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
