// Темы должны сразу объяснять текущий вид профиля и честно предлагать доступную
// локальному стенду покупку. Золото остаётся только маркером активной темы,
// фиолетовый — временным просмотром другой темы.
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
  await page.waitForFunction(() => !!_themeData && document.querySelectorAll('#looks-grid-themes .looks-card').length > 0);
  const initial = await page.$eval('#looks-theme-preview', node => node.textContent.replace(/\s+/g, ' ').trim());

  await page.click('#looks-grid-themes .looks-card[data-theme="neon_terminal"]');
  await page.waitForFunction(() => document.querySelector('#looks-theme-preview')?.textContent.includes('Неоновый Терминал'));
  await page.evaluate(() => {
    document.querySelector('#looks-sec-themes')?.scrollIntoView({block: 'center'});
    window.dispatchEvent(new Event('scroll'));
  });
  await new Promise(resolve => setTimeout(resolve, 80));
  const state = await page.evaluate(() => ({
    preview: document.querySelector('#looks-theme-preview')?.textContent.replace(/\s+/g, ' ').trim() || '',
    activeClasses: document.querySelector('#looks-grid-themes .looks-card[data-theme="classic"]')?.className || '',
    viewedClasses: document.querySelector('#looks-grid-themes .looks-card[data-theme="neon_terminal"]')?.className || '',
    gridColumns: getComputedStyle(document.querySelector('#looks-grid-themes .looks-cards')).gridTemplateColumns.split(' ').length,
    pattern: document.querySelector('#looks-grid-themes .looks-card[data-theme="neon_terminal"] .theme-card-pattern')?.textContent || '',
    filterHeight: Math.round(document.querySelector('.looks-theme-chip')?.getBoundingClientRect().height || 0),
    dock: (() => {
      const host=document.querySelector('#pg-looks #looks-dock'), node=document.querySelector('.looks-fab'), card=document.querySelector('.theme-card');
      const rect=item=>item?.getBoundingClientRect(); const buttonRect=rect(node), cardRect=rect(card);
      const overlaps=!!(buttonRect&&cardRect&&buttonRect.left<cardRect.right&&buttonRect.right>cardRect.left&&buttonRect.top<cardRect.bottom&&buttonRect.bottom>cardRect.top);
      return {inside:!!host, position:host?getComputedStyle(host).position:'', buttonPosition:node?getComputedStyle(node).position:'', width:Math.round(buttonRect?.width||0), overlaps};
    })(),
    looksPageBottomPadding: Math.round(parseFloat(getComputedStyle(document.querySelector('#pg-looks')).paddingBottom)),
  }));

  check('themes initialise the preview with the active theme', /Классика/.test(initial) && /Активная тема/.test(initial));
  check('viewed theme explains its visual idea', /IT-стиль: зелёный курсор, поток кода\./.test(state.preview));
  check('directly sold local theme presents its zarniki buy action', /Купить\s*—\s*440\s*✨/.test(state.preview));
  check('theme preview names the interaction state', /Предпросмотр темы/.test(state.preview));
  check('active and viewed themes use distinct visual states',
    /\bsel\b/.test(state.activeClasses) && !/theme-previewing/.test(state.activeClasses) &&
    /theme-previewing/.test(state.viewedClasses) && !/\bsel\b/.test(state.viewedClasses));
  check('theme catalog uses roomy two-column cards with a clipped visual pattern',
    state.gridColumns === 2 && /▚▞/.test(state.pattern));
  check('theme filters have a mobile-safe touch target', state.filterHeight >= 44);
  check('fitting room stays in the appearance flow instead of covering catalog cards',
    state.dock.inside && state.dock.position === 'sticky' && state.dock.buttonPosition === 'static' && state.dock.width >= 300 && !state.dock.overlaps);
  check('looks page keeps a purposeful bottom clearance instead of a viewport-sized blank tail', state.looksPageBottomPadding <= 160);
} finally {
  await browser.close();
}

if (failures.length) {
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
