// Вход в сундуки и крафт — часть косметического опыта, поэтому он должен быть
// объясняющей карточкой, а не одинокой ghost-кнопкой между несвязанными блоками.
import puppeteer from 'puppeteer';

const failures = [];
function check(name, condition) {
  if (!condition) failures.push(name);
  else console.log('OK:', name);
}

const browser = await puppeteer.launch({headless: 'new'});
try {
  const page = await browser.newPage();
  await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
  await page.goto('http://localhost:8402/', {waitUntil: 'load'});
  await page.waitForFunction(() => typeof openLooksModal === 'function');
  await page.mouse.click(195, 700);
  await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');

  await page.evaluate(() => openLooksModal());
  await page.waitForFunction(() => !!_looksData && !!document.querySelector('#pg-looks'));
  const state = await page.evaluate(() => {
    const entry=document.querySelector('.looks-surprises-entry');
    return {
      tag: entry?.tagName || '',
      text: entry?.textContent.replace(/\s+/g, ' ').trim() || '',
      width: Math.round(entry?.getBoundingClientRect().width || 0),
      height: Math.round(entry?.getBoundingClientRect().height || 0),
      legacy: !!document.querySelector('#pg-looks .btn-ghost.btn-full[onclick="_openSurprisesModal()"]'),
    };
  });

  check('surprises entry is a dedicated full-width button-card', state.tag === 'BUTTON' && state.width >= 300 && state.height >= 64);
  check('surprises entry explains both available activities', /Сюрпризы и крафт/.test(state.text) && /Сундуки, осколки и косметика/.test(state.text));
  check('legacy unlabelled ghost button is removed', !state.legacy);

  if (state.tag === 'BUTTON') {
    await page.click('.looks-surprises-entry');
    await page.waitForFunction(() => document.querySelector('#modal')?.open && /Сундуки-сюрпризы/.test(document.querySelector('#mb')?.textContent || ''));
    check('entry still opens the existing surprises and craft flow', true);
  } else {
    check('entry still opens the existing surprises and craft flow', false);
  }
} finally {
  await browser.close();
}

if (failures.length) {
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
