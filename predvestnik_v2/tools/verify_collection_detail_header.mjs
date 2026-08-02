// Детальный экран коллекции (Стадия 3): шапка, сегментный измеритель, кнопка
// «Купить всё недостающее» — 3 сценария на реальных данных мока preview_server.mjs:
// forest (1 предмет, уже владеет → «собрано»), threshold (2 предмета, 0 owned,
// сумма фактических цен 880 ≤ баланс 1250 → кнопка активна), artifact
// (1 предмет, 0 owned, цена 1500 > баланс 1250 → кнопка заблокирована).
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

async function openAndRead(lin) {
  await page.evaluate((l) => _looksOpenCollection(l), lin);
  await new Promise(r => setTimeout(r, 300));
  return page.evaluate(() => ({
    hasHead: !!document.querySelector('.coll-detail-head'),
    headTop: document.querySelector('.coll-detail-head')?.getBoundingClientRect().top ?? null,
    catalogChromeVisible: !!document.querySelector('.looks-surprises-entry, .looks-presets, #looks-quick-links, .looks-vipbar'),
    hasToggle: !!document.getElementById('looks-mode-toggle'),
    notches: document.querySelectorAll('.coll-meter-notch').length,
    onNotches: document.querySelectorAll('.coll-meter-notch.on').length,
    doneText: (document.querySelector('.coll-detail-done') || {}).textContent || null,
    btn: document.querySelector('.coll-detail-head button.btn-gold, .coll-detail-head button.btn-ghost'),
    btnText: (document.querySelector('.coll-detail-head button.btn-gold, .coll-detail-head button.btn-ghost') || {}).textContent || null,
    btnDisabled: (document.querySelector('.coll-detail-head button.btn-gold, .coll-detail-head button.btn-ghost') || {}).disabled,
    sectionsCount: document.querySelectorAll('#looks-sections .looks-section').length,
  }));
}

const forest = await openAndRead('forest');
check('шапка детального экрана отрендерена (forest)', forest.hasHead);
check('шапка коллекции попадает в первый мобильный экран', forest.headTop !== null && forest.headTop < 160);
check('каталожные промо и пресеты не отталкивают детали коллекции вниз', !forest.catalogChromeVisible);
check('переключатель режимов скрыт внутри детального экрана', !forest.hasToggle);
check('forest: 1 деление, 1 горит (мок владеет единственным предметом)', forest.notches === 1 && forest.onNotches === 1);
check('forest: показан статус "собрано", кнопки покупки нет', /собрана полностью/.test(forest.doneText || '') && !forest.btn);
check('пустые для линейки слоты не создают секции', forest.sectionsCount === 1);

// Ревью-финдинг: счётчик секции name_glow внутри детального экрана forest должен
// быть СКОПИРОВАН на линейку (1/1 — владеет только cos_name_glow_moon), а НЕ
// глобальным счётом по всем линейкам (1/3: moon(forest,owned)+frost+neon(artifact)).
const forestGlowNum = await page.evaluate(() => (document.querySelector('#looks-sec-name_glow .sec-num') || {}).textContent || null);
check('forest detail: секция name_glow показывает 1/1 (скоуп на линейку), не 1/3', forestGlowNum === '1/1');

const threshold = await openAndRead('threshold');
check('threshold: 2 деления, 0 горит', threshold.notches === 2 && threshold.onNotches === 0);
check('threshold: кнопка активна (880✨ ≤ баланс 1250✨)', threshold.btn && !threshold.btnDisabled);
check('threshold: текст кнопки содержит сумму фактических цен и количество', /880.*2\s*шт/.test((threshold.btnText||'').replace(/✨/g,'')));

const artifact = await openAndRead('artifact');
check('artifact: кнопка заблокирована (1500✨ > баланс 1250✨)', artifact.btn && artifact.btnDisabled);
check('artifact: текст кнопки — "Нужно"', /Нужно/.test(artifact.btnText || ''));

// Назад — детальный экран закрывается, переключатель режимов возвращается
await page.click('.coll-detail-back');
await new Promise(r => setTimeout(r, 300));
const back = await page.evaluate(() => ({
  detailGone: !document.querySelector('.coll-detail-head'),
  toggleBack: !!document.getElementById('looks-mode-toggle'),
  cardCount: document.querySelectorAll('.coll-card').length,
}));
check('кнопка "‹ Назад" закрывает детальный экран', back.detailGone);
check('переключатель режимов снова виден', back.toggleBack);
check('карточки коллекций снова на экране', back.cardCount === 7);

// Режим «По слотам» (полный каталог) должен по-прежнему показывать ГЛОБАЛЬНЫЙ счёт
// (не затронут фиксом finding 2 — только детальный экран коллекции скоупится).
await page.evaluate(() => _looksSetMode('slots'));
await new Promise(r => setTimeout(r, 300));
const slotsGlowNum = await page.evaluate(() => (document.querySelector('#looks-sec-name_glow .sec-num') || {}).textContent || null);
check('режим «По слотам»: секция name_glow показывает глобальные 1/3 (не изменилось)', slotsGlowNum === '1/3');

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
