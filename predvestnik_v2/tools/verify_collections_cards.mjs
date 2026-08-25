// Проверка карточек коллекций: одна на каждую запись каталога, у каждой медальон+SVG, кольцо-прогресс
// соответствует реальному owned/total, полоска слотов совпадает с фактическим
// владением, статус-текст честный (собрано/не куплено/не начато).
import puppeteer from 'puppeteer';

const FAIL = [];
function check(name, cond) { if (!cond) FAIL.push(name); else console.log('OK:', name); }

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

const info = await page.evaluate(() => {
  const cards = document.querySelectorAll('.coll-card');
  const lineupIds = Object.keys(_looksData.lineups || {});
  const results = [];
  cards.forEach(card => {
    const lin = card.getAttribute('data-lineup');
    const svg = card.querySelector('.coll-sig-svg');
    const ring = card.querySelector('.coll-ring');
    const slots = card.querySelectorAll('.coll-slot');
    const statusEl = card.querySelector('.coll-status');
    results.push({
      lin, hasSvg: !!svg, hasRing: !!ring,
      slotCount: slots.length,
      statusText: statusEl ? statusEl.textContent.trim() : null,
    });
  });
  return { cardCount: cards.length, lineupCount: lineupIds.length, results, lineupIds };
});

check('ровно 10 карточек коллекций (по числу линеек)', info.cardCount === info.lineupCount && info.cardCount === 10);
check('каждая карточка имеет data-lineup из реального набора линеек', info.results.every(r => info.lineupIds.includes(r.lin)));
check('у каждой карточки есть SVG-медальон', info.results.every(r => r.hasSvg));
check('у каждой карточки есть кольцо-прогресс', info.results.every(r => r.hasRing));
check('у каждой карточки ровно 6 слот-иконок (по числу слотов игры)', info.results.every(r => r.slotCount === 6));
check('у каждой карточки есть текст статуса', info.results.every(r => !!r.statusText));

// Честность статус-текста и полоски слотов: сверяем с реальными данными по каждой линейке
const statsCheck = await page.evaluate(() => {
  const mismatches = [];
  const slotMismatches = [];
  Object.keys(_looksData.lineups).forEach(lin => {
    let owned = 0, total = 0;
    const slotOwned = {};
    _LOOKS_SLOTS.forEach(slot => {
      const items = (_looksData.slots[slot] || []).filter(it => it.lineup === lin);
      total += items.length;
      const hasOwned = items.some(it => it.owned);
      if (hasOwned) owned += items.filter(it => it.owned).length;
      slotOwned[slot] = hasOwned;
    });
    const card = document.querySelector(`.coll-card[data-lineup="${lin}"] .coll-status`);
    const text = card ? card.textContent.trim() : null;
    let expected;
    if (total === 0) expected = 'не начато';
    else if (owned === total) expected = '✓ собрано';
    else if (owned === 0) expected = 'не начато';
    else expected = `${total - owned} не куплено`;
    if (text !== expected) mismatches.push({ lin, owned, total, text, expected });

    const slotEls = document.querySelectorAll(`.coll-card[data-lineup="${lin}"] .coll-slot`);
    _LOOKS_SLOTS.forEach((slot, i) => {
      const domOn = slotEls[i] ? slotEls[i].classList.contains('on') : null;
      const expectedOn = slotOwned[slot];
      if (domOn !== expectedOn) slotMismatches.push({ lin, slot, domOn, expectedOn });
    });
  });
  return { mismatches, slotMismatches };
});
check('статус-текст на каждой карточке точно совпадает с реальным owned/total', statsCheck.mismatches.length === 0);
if (statsCheck.mismatches.length) console.log('mismatches:', JSON.stringify(statsCheck.mismatches));
check('полоска слот-иконок (яркая/тусклая) точно совпадает с реальным владением по слотам', statsCheck.slotMismatches.length === 0);
if (statsCheck.slotMismatches.length) console.log('slot mismatches:', JSON.stringify(statsCheck.slotMismatches));

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
