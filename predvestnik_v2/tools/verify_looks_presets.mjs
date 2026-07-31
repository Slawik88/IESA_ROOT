// «Образы» должны быть одной понятной лентой: сохранённый личный набор и
// последний элемент «сохранить текущий», а не серый чип рядом с чужой кнопкой.
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
  await page.waitForFunction(() => !!_looksData && !!document.querySelector('.looks-presets'));
  const state = await page.evaluate(() => {
    const root=document.querySelector('#looks-presets') || document.querySelector('.looks-presets');
    const saved=root?.querySelector('.looks-preset-card[data-preset]');
    const add=root?.querySelector('.looks-preset-card--add');
    const remove=root?.querySelector('.looks-preset-del');
    const rect=node=>node?{width:Math.round(node.getBoundingClientRect().width),height:Math.round(node.getBoundingClientRect().height)}:null;
    return {
      hasLabel: root?.getAttribute('aria-label') || '',
      countText: root?.querySelector('.looks-presets-head span:last-child')?.textContent.trim() || '',
      savedText: saved?.textContent.replace(/\s+/g, ' ').trim() || '',
      addText: add?.textContent.replace(/\s+/g, ' ').trim() || '',
      savedRect: rect(saved), addRect: rect(add), deleteRect: rect(remove),
      legacySave: !!root?.querySelector('.looks-preset-save'),
    };
  });

  check('presets use an explicit accessible image-strip container', state.hasLabel === 'Сохранённые образы');
  check('preset counter uses a natural Russian image noun', state.countText === '1 образ');
  check('saved preset identifies itself as a personal image', /Золотой образ/.test(state.savedText) && /Твой образ/.test(state.savedText));
  check('the last tile clearly saves the current image', /Сохранить текущий/.test(state.addText));
  check('saved and add tiles are comfortably tappable', state.savedRect?.width >= 120 && state.savedRect?.height >= 64 && state.addRect?.width >= 120 && state.addRect?.height >= 64);
  check('delete action has an independent touch target and old ghost save button is gone', state.deleteRect?.width >= 32 && state.deleteRect?.height >= 32 && !state.legacySave);
} finally {
  await browser.close();
}

if (failures.length) {
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
