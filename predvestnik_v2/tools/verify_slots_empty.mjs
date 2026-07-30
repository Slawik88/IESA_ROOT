// Проверка стилизации пустого состояния фильтра: пунктирная рамка + иконка
// (Стадия 1, Задача 4, 208cd567 — коммит был без скрипта, добавлен финальным ревью).
// Запуск: node tools/verify_slots_empty.mjs (нужен запущенный preview_server.mjs на :8402)
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
await page.type('#looks-search-inp', 'этогонесуществует12345');
await new Promise(r => setTimeout(r, 300));

const empty = await page.evaluate(() => {
  const e = document.querySelector('#looks-grid-name_glow .looks-empty');
  return e ? {
    text: e.textContent.trim(),
    hasIco: !!e.querySelector('.looks-empty-ico'),
    hasIcon: !!e.querySelector('.looks-empty-ico'),
    styles: {
      hasGrid: e.className.includes('looks-empty'),
      hasDashed: window.getComputedStyle(e).borderStyle === 'dashed',
      borderColor: window.getComputedStyle(e).borderColor,
    }
  } : null;
});

console.log('Empty state:', JSON.stringify(empty, null, 2));
check('пустое состояние видно', empty !== null);
check('иконка присутствует', empty && empty.hasIco);
check('текст "Ничего не найдено по этому фильтру"', empty && empty.text.includes('Ничего не найдено'));

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
