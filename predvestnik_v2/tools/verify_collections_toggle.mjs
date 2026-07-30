// Проверка переключателя режимов: виден, две кнопки, клик переключает контент
// и сохраняется в localStorage. Запуск: node tools/verify_collections_toggle.mjs
// (нужен запущенный preview_server.mjs на :8402)
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

const initial = await page.evaluate(() => ({
  hasToggle: !!document.getElementById('looks-mode-toggle'),
  hasCollectionsBtn: !!document.querySelector('[data-mode="collections"]'),
  hasSlotsBtn: !!document.querySelector('[data-mode="slots"]'),
  mode: typeof _looksMode !== 'undefined' ? _looksMode : null,
  hasFilterBar: !!document.getElementById('looks-filter-bar'),
}));
check('переключатель существует', initial.hasToggle);
check('есть кнопка "По коллекциям"', initial.hasCollectionsBtn);
check('есть кнопка "По слотам"', initial.hasSlotsBtn);
check('режим по умолчанию — collections', initial.mode === 'collections');
check('в режиме collections НЕТ умного ряда "По слотам" на экране', !initial.hasFilterBar);

// Клик на "По слотам" переключает контент
await page.click('[data-mode="slots"]');
await new Promise(r => setTimeout(r, 300));
const afterSlotsClick = await page.evaluate(() => ({
  mode: _looksMode,
  hasFilterBar: !!document.getElementById('looks-filter-bar'),
  savedMode: (() => { try { return localStorage.getItem('pv_looks_mode'); } catch(e){ return 'ERR'; } })(),
}));
check('клик "По слотам" переключает _looksMode', afterSlotsClick.mode === 'slots');
check('в режиме slots умный ряд появляется', afterSlotsClick.hasFilterBar);
check('режим сохранён в localStorage', afterSlotsClick.savedMode === 'slots');

// Закрыть и снова открыть — режим должен восстановиться из localStorage
await page.evaluate(() => { _looksData = null; });
await page.evaluate(() => openLooksModal());
await new Promise(r => setTimeout(r, 500));
const afterReopen = await page.evaluate(() => _looksMode);
check('режим восстановлен из localStorage при повторном открытии', afterReopen === 'slots');

// "Вход"/"Темы" — общие для обоих режимов, должны рендериться РОВНО один раз,
// не дублироваться и не пропадать при переключении режима.
await page.evaluate(() => { _looksSetMode('collections'); });
await new Promise(r => setTimeout(r, 300));
const commonSectionsCollections = await page.evaluate(() => ({
  welcomeCount: document.querySelectorAll('#looks-sec-welcome').length,
  themesCount: document.querySelectorAll('#looks-sec-themes').length,
}));
check('в режиме collections секция "Вход" ровно одна', commonSectionsCollections.welcomeCount === 1);
check('в режиме collections секция "Темы" ровно одна', commonSectionsCollections.themesCount === 1);

await page.evaluate(() => { _looksSetMode('slots'); });
await new Promise(r => setTimeout(r, 300));
const commonSectionsSlots = await page.evaluate(() => ({
  welcomeCount: document.querySelectorAll('#looks-sec-welcome').length,
  themesCount: document.querySelectorAll('#looks-sec-themes').length,
}));
check('в режиме slots секция "Вход" ровно одна (не задублирована)', commonSectionsSlots.welcomeCount === 1);
check('в режиме slots секция "Темы" ровно одна (не задублирована)', commonSectionsSlots.themesCount === 1);

// Проверка что фильтр-бар находится ВНУТРИ .looks-sticky в режиме slots
// (не уезжает при скролле)
const stickyCheck = await page.evaluate(() => ({
  slotsFilterBarInSticky: !!document.querySelector('.looks-sticky #looks-filter-bar'),
}));
check('в режиме slots #looks-filter-bar находится ВНУТРИ .looks-sticky (не уезжает при скролле)', stickyCheck.slotsFilterBarInSticky);

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
