// Сквозная проверка именно пользовательского сценария в «Внешнем виде», а не
// только HTTP-мока: выбрать тему → купить → увидеть «Надеть» → активировать.
import puppeteer from 'puppeteer';

const base = 'http://localhost:8402';
const reset = () => fetch(base + '/__preview/reset', {method: 'POST'});
const failures = [];
function check(name, condition) {
  if (!condition) failures.push(name);
  else console.log('OK:', name);
}

await reset();
const browser = await puppeteer.launch({headless: 'new'});
try {
  const page = await browser.newPage();
  await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
  await page.goto(base + '/', {waitUntil: 'load'});
  await page.waitForFunction(() => typeof openLooksModal === 'function');
  await page.mouse.click(195, 700);
  await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');
  await page.evaluate(() => openLooksModal());
  await page.waitForFunction(() => !!_themeData && !!document.querySelector('.theme-card[data-theme="neon_terminal"]'));

  await page.click('.theme-card[data-theme="neon_terminal"]');
  await page.waitForFunction(() => /Купить\s*—\s*440\s*✨/.test(document.querySelector('#looks-theme-preview')?.textContent || ''));
  await page.$eval('#looks-theme-preview .btn-gold', button => button.scrollIntoView({block: 'center'}));
  await page.click('#looks-theme-preview .btn-gold');
  await page.waitForFunction(() => {
    const theme=_themeData?.find(item => item.theme_id === 'neon_terminal');
    return !!theme?.owned && /Надеть/.test(document.querySelector('#looks-theme-preview')?.textContent || '');
  });
  const bought = await page.evaluate(() => ({
    preview: document.querySelector('#looks-theme-preview')?.textContent.replace(/\s+/g, ' ').trim() || '',
    zarniki: _profileData?.zarniki,
  }));

  await page.$eval('#looks-theme-preview .btn-gold', button => button.scrollIntoView({block: 'center'}));
  await page.click('#looks-theme-preview .btn-gold');
  await page.waitForFunction(() => {
    const theme=_themeData?.find(item => item.theme_id === 'neon_terminal');
    return !!theme?.active && /Активная тема/.test(document.querySelector('#looks-theme-preview')?.textContent || '');
  });
  const equipped = await page.evaluate(() => ({
    active: _themeData.filter(item => item.active).map(item => item.theme_id),
    preview: document.querySelector('#looks-theme-preview')?.textContent.replace(/\s+/g, ' ').trim() || '',
  }));

  check('buy action becomes an equip action without leaving the appearance screen', /Надеть/.test(bought.preview));
  check('buy action refreshes the visible zarniki balance', bought.zarniki === 810);
  check('equip action leaves exactly the chosen theme active', equipped.active.length === 1 && equipped.active[0] === 'neon_terminal');
  check('equipped preview confirms the active state', /Активная тема/.test(equipped.preview));
} finally {
  await browser.close();
  await reset();
}

if (failures.length) {
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
