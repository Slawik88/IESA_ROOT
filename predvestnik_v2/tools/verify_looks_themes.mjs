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
    filterUsesSharedTabs: document.querySelector('.looks-theme-filter')?.classList.contains('tabs')
      && document.querySelector('.looks-theme-filter')?.classList.contains('tab-inner')
      && document.querySelector('.looks-theme-chip')?.classList.contains('tb'),
    filterVisibleHeight: Math.round(document.querySelector('.looks-theme-chip')?.getBoundingClientRect().height || 0),
    filterVisibleRadius: parseFloat(getComputedStyle(document.querySelector('.looks-theme-chip')).borderRadius) || 0,
    filterHitTop: parseFloat(getComputedStyle(document.querySelector('.looks-theme-chip'),'::before').top) || 0,
    filterHitContent: getComputedStyle(document.querySelector('.looks-theme-chip'),'::before').content,
    dock: (() => {
      const host=document.querySelector('body > #looks-dock'), node=host?.querySelector('.looks-fab'), nav=document.querySelector('.nav');
      const buttonRect=node?.getBoundingClientRect(), navRect=nav?.getBoundingClientRect();
      const centerX=buttonRect?buttonRect.left+buttonRect.width/2:0, centerY=buttonRect?buttonRect.top+buttonRect.height/2:0;
      return {
        portaled:!!host,
        position:host?getComputedStyle(host).position:'',
        width:Math.round(buttonRect?.width||0),
        clearOfNav:!!(buttonRect&&navRect&&buttonRect.bottom<=navRect.top),
        hitTarget:document.elementFromPoint(centerX,centerY)?.closest('.looks-fab')===node,
      };
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
  check('theme filters reuse the shared segmented-tab language across the app', state.filterUsesSharedTabs);
  check('theme filters keep an invisible expanded tap area around a compact visible segment', state.filterVisibleHeight <= 30
    && state.filterVisibleRadius <= 9 && state.filterHitContent==='""' && state.filterHitTop <= -9);
  check('fitting room stays compact, viewport-fixed, touchable and clear of bottom navigation',
    state.dock.portaled && state.dock.position === 'fixed' && state.dock.width >= 176 && state.dock.width <= 220 && state.dock.clearOfNav && state.dock.hitTarget);
  check('looks page keeps a compact bottom clearance instead of a viewport-sized blank tail', state.looksPageBottomPadding >= 64 && state.looksPageBottomPadding <= 88);
  if (process.env.SCREENSHOT_PATH) {
    const filter = await page.$('#looks-theme-filter');
    await filter.screenshot({path: process.env.SCREENSHOT_PATH});
  }
} finally {
  await browser.close();
}

if (failures.length) {
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
