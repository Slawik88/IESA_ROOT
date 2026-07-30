// Проверка изоляции модалки «Сюрпризы и Крафт» (сундуки/крафт) от редизайна
// линеек (Стадия 1, 2026-07-29, финальное ревью — находка 4): раньше preview_server.mjs
// не мокал /cosmetics/chests и /cosmetics/craft → модалка рендерила 0 карточек, и
// проверка «нет lc-lineup-accent» проходила ВАКУУМНО (не с чем было бы сломаться).
// Теперь есть моки → сначала проверяем count>0 (тест не может пройти пусто), ПОТОМ —
// что ни одна карточка крафта не получила класс lc-lineup-accent (эта модалка
// намеренно осталась на старой системе r-{rarity}, без акцента линейки).
// Запуск: node tools/verify_chest_craft_isolation.mjs (нужен запущенный preview_server.mjs на :8402)
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
await page.evaluate(() => _openSurprisesModal());
await new Promise(r => setTimeout(r, 800));

const info = await page.evaluate(() => {
  const chestCards = document.querySelectorAll('#mb .gift-card');
  const craftCards = document.querySelectorAll('#mb .looks-cards .looks-card');
  const accented = document.querySelectorAll('#mb .looks-cards .looks-card.lc-lineup-accent');
  return {
    chestCount: chestCards.length,
    craftCount: craftCards.length,
    accentCount: accented.length,
  };
});
console.log('Chest/craft modal card counts:', JSON.stringify(info));

check('сундуков отрендерилось больше нуля (мок работает)', info.chestCount > 0);
check('карточек крафта отрендерилось больше нуля (проверка не может пройти вакуумно)', info.craftCount > 0);
check('ни одна карточка крафта НЕ получила lc-lineup-accent (изоляция от редизайна линеек цела)', info.accentCount === 0);

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
