// Проверка умного ряда «По слотам»: один <input> поиска, одна пилюля выбора
// линейки (не 8 чипов), одна кнопка статуса (не отдельный ряд чипов).
// Запуск: node tools/verify_slots_smartrow.mjs (нужен запущенный preview_server.mjs на :8402)
import puppeteer from 'puppeteer';

const FAIL = [];
function check(name, cond) { if (!cond) FAIL.push(name); else console.log('OK:', name); }

const browser = await puppeteer.launch({ headless: 'new' });
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await page.goto('http://localhost:8402/', { waitUntil: 'load' });
await new Promise(r => setTimeout(r, 1500));
await page.mouse.click(195, 700); // skip welcome splash
await new Promise(r => setTimeout(r, 500));
await page.evaluate(() => openLooksModal());
await new Promise(r => setTimeout(r, 500));
// Переключиться на режим "По слотам" (т.к. по умолчанию режим "По коллекциям")
await page.click('[data-mode="slots"]');
await new Promise(r => setTimeout(r, 300));

const state = await page.evaluate(() => {
  const searchInput = document.querySelector('#looks-filter-bar input[type="text"]');
  const oldChipRows = document.querySelectorAll('.looks-filter .looks-chip').length;
  const lineupPill = document.getElementById('looks-lineup-pill');
  const statusBtn = document.getElementById('looks-status-btn');
  return {
    hasSearchInput: !!searchInput,
    oldChipCount: oldChipRows,
    hasLineupPill: !!lineupPill,
    hasStatusBtn: !!statusBtn,
  };
});
check('есть текстовое поле поиска', state.hasSearchInput);
check('старых чипов-линеек/статуса больше нет (было 8+3)', state.oldChipCount === 0);
check('есть пилюля выбора линейки', state.hasLineupPill);
check('есть кнопка-переключатель статуса', state.hasStatusBtn);

// Ввод в поиск фильтрует сетку
if (state.hasSearchInput) {
  await page.type('#looks-filter-bar input[type="text"]', 'Лунный');
  await new Promise(r => setTimeout(r, 300));
  const visibleCards = await page.evaluate(() =>
    document.querySelectorAll('#looks-grid-name_glow .looks-card[data-cos]:not([data-cos="__none__"])').length);
  check('поиск "Лунный" сужает сетку ореолов до 1 предмета', visibleCards === 1);
}

// Клик по кнопке статуса циклит all → owned → missing
if (state.hasStatusBtn) {
  const seq = [];
  for (let i = 0; i < 3; i++) {
    await page.click('#looks-status-btn');
    await new Promise(r => setTimeout(r, 150));
    seq.push(await page.evaluate(() => _looksStatus));
  }
  check('кнопка статуса циклит all→owned→missing→all', JSON.stringify(seq) === JSON.stringify(['owned','missing','all']));
}

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
