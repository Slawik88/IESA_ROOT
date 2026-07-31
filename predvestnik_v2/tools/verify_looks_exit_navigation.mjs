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
  await page.waitForFunction(() => typeof switchPage === 'function' && typeof openLooksModal === 'function');
  // Чистый запуск перекрыт заставкой до первого касания: в реальном UI игрок
  // закрывает её тапом, иначе последующий клик не попадёт в стрелку раздела.
  await page.mouse.click(195, 700);
  await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');

  await page.evaluate(() => switchPage('market'));
  await page.waitForFunction(() => _activePage === 'market');
  await page.evaluate(() => openLooksModal());
  await page.waitForFunction(() =>
    _activePage === 'looks' &&
    !!document.querySelector('.looks-back') &&
    !!_looksData &&
    document.querySelectorAll('.looks-card').length > 0
  );

  const opened = await page.evaluate(() => {
    const fallback = document.getElementById('nav-back');
    return {
      activePage: _activePage,
      hasHeaderExit: !!document.querySelector('.looks-back'),
      fallbackIsVisible: !!fallback && !fallback.classList.contains('hidden'),
    };
  });
  check('appearance opens with its own header exit', opened.activePage === 'looks' && opened.hasHeaderExit);
  check('appearance hides the duplicate floating back control', !opened.fallbackIsVisible);

  await page.click('.looks-back');
  await page.waitForFunction(() => _activePage === 'market' && !document.querySelector('.looks-fab'));
  const closed = await page.evaluate(() => ({
    activePage: _activePage,
    fittingRoomExists: !!document.querySelector('.looks-fab'),
  }));
  check('appearance header exit returns the player to the page they came from', closed.activePage === 'market');
  check('fitting room dock leaves with the appearance page', !closed.fittingRoomExists);
} finally {
  await browser.close();
}

if (failures.length) {
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
