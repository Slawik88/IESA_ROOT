import puppeteer from 'puppeteer';

const chromium = process.env.PUPPETEER_EXECUTABLE_PATH;
const browser = await puppeteer.launch(chromium ? { headless: 'new', executablePath: chromium } : { headless: 'new' });
const failures = [];
const check = (condition, message) => {
  if (!condition) failures.push(message);
};

try {
  for (const width of [320, 390, 430]) {
    const page = await browser.newPage();
    await page.setViewport({ width, height: 844, deviceScaleFactor: 1 });
    await page.goto('http://localhost:8402/', { waitUntil: 'load' });
    // Other UI regressions may equip a saved look. This test asserts the
    // canonical 3/6 fixture, so it must not inherit process-global preview
    // cosmetics from its predecessor.
    await page.evaluate(() => fetch('/__preview/reset', {method: 'POST'}));
    await page.waitForFunction(() => typeof switchPage === 'function');
    await page.evaluate(() => {
      const preloader = document.getElementById('preloader');
      if (preloader) preloader.style.display = 'none';
      switchPage('profile');
      loadProfile();
      scrollTo(0, 0);
    });
    await page.waitForSelector('.profile-showcase-card');
    await new Promise(resolve => setTimeout(resolve, 450));

    const state = await page.evaluate(() => {
      const card = document.querySelector('.profile-showcase-card');
      const canvas = document.querySelector('.character-showcase-area');
      const main = document.querySelector('.profile-showcase-main');
      const looksControl = document.querySelector('[data-open-looks="profile-showcase"]');
      const portrait = document.querySelector('#pro-showcase-ava');
      const caption = document.querySelector('.character-showcase-caption');
      const style = node => node ? getComputedStyle(node) : null;
      return {
        pageWidth: document.documentElement.scrollWidth,
        viewportWidth: innerWidth,
        cardWidth: card?.getBoundingClientRect().width || 0,
        canvasHeight: canvas?.getBoundingClientRect().height || 0,
      mainColumns: style(main)?.gridTemplateColumns || '',
      railRows: style(document.querySelector('.player-data-rail--compact'))?.gridTemplateRows || '',
      railFitsMain: (() => {
        const rail=document.querySelector('.player-data-rail--compact');
        const railRect=rail?.getBoundingClientRect();
        const items=[...(rail?.children||[])];
        return !!railRect && items.length===3 && items.every(item=>item.getBoundingClientRect().bottom<=railRect.bottom+1);
      })(),
        railItems: document.querySelectorAll('.player-data-rail .player-rail-item').length,
        resources: document.querySelectorAll('.profile-resource-rail .stat').length,
        looksControlCount: document.querySelectorAll('[data-open-looks="profile-showcase"]').length,
        looksText: looksControl?.textContent.replace(/\s+/g, ' ').trim() || '',
        looksHeight: looksControl?.getBoundingClientRect().height || 0,
        looksLabel: looksControl?.getAttribute('aria-label') || '',
        portraitWidth: portrait?.getBoundingClientRect().width || 0,
        portraitBottom: portrait?.getBoundingClientRect().bottom || 0,
        captionTop: caption?.getBoundingClientRect().top || 0,
        captionMeta: caption?.querySelector('small')?.textContent.replace(/\s+/g, ' ').trim() || '',
        captionCss: caption ? {
          position: style(caption)?.position,
          display: style(caption)?.display,
          bottom: style(caption)?.bottom,
          paddingTop: style(caption)?.paddingTop,
          background: style(caption)?.backgroundColor,
        } : null,
        hasShowcaseFrame: !!document.querySelector('#pro-showcase-ava.frame-oak'),
        actionHeights: [...document.querySelectorAll('.profile-card-actions button')].map(button => button.getBoundingClientRect().height),
        hasFrame: !!document.querySelector('.profile-showcase-card #pro-ava.frame-oak'),
        hasGlow: !!document.querySelector('.profile-showcase-card .pname.glow-moon'),
        cardShadow: style(card)?.boxShadow || '',
      };
    });

    const tag = `${width}px`;
    check(state.pageWidth === state.viewportWidth, `${tag}: page has horizontal overflow`);
    check(state.cardWidth > width - 32, `${tag}: player card does not use the available width`);
    check(state.canvasHeight >= 268, `${tag}: customization canvas is not spacious enough`);
    check(state.mainColumns.split(' ').filter(Boolean).length >= 2, `${tag}: canvas and data rail are not laid out side-by-side`);
    check(state.railItems === 3, `${tag}: data rail must show level, streak, and achievements without retired power`);
    check(state.railRows.split(' ').filter(Boolean).length === 3 && state.railFitsMain,
      `${tag}: the three-metric rail has an empty or overflowing grid row`);
    check(state.resources === 4, `${tag}: resource rail must preserve four balances/achievement tiles`);
    check(state.looksControlCount === 1, `${tag}: player card must expose exactly one Looks entry`);
    check(/образы|примерку/i.test(state.looksText) && /открыть образы|продолжить примерку/i.test(state.looksLabel), `${tag}: Looks canvas is not clearly named`);
    check(/\b3 из 6\b/.test(state.looksText), `${tag}: normal profile shows the wrong equipped-look count`);
    check(state.captionMeta === 'На сцене: рамка', `${tag}: stage copy claims cosmetics that are only in the header or not equipped`);
    check(state.looksHeight >= 268, `${tag}: Looks canvas no longer fills the player-card stage`);
    check(state.portraitWidth >= 88 && state.portraitWidth <= 112, `${tag}: central portrait is not safely sized`);
    check(state.captionCss?.position === 'absolute' && state.captionCss?.display === 'grid'
      && state.captionCss?.bottom === '10px' && state.captionCss?.paddingTop === '8px'
      && state.captionCss?.background !== 'rgba(0, 0, 0, 0)', `${tag}: canvas caption lost its visual anchor`);
    check(state.captionTop > state.portraitBottom + 16, `${tag}: canvas caption overlaps the portrait instead of forming a clear vertical hierarchy`);
    check(state.actionHeights.length === 3 && state.actionHeights.every(height => height >= 44), `${tag}: profile utility actions are not mobile-safe`);
    check(state.hasFrame && state.hasShowcaseFrame && state.hasGlow, `${tag}: equipped cosmetic layers were lost in the new card`);
    check(state.cardShadow === 'none', `${tag}: neutral player card gained a heavy base shadow`);

    await page.focus('[data-open-looks="profile-showcase"]');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#pg-looks')?.classList.contains('active'));
    const looksWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    check(looksWidth === width, `${tag}: fitting-room page overflows after opening from the canvas`);
    await page.close();
  }

  // The canvas must stay useful for a completely plain profile as well as a
  // fully assembled look. The normal preview fixture above already covers 3/6.
  const showcaseFixtures = [
    ['empty', {}, 0],
    ['full', {
      name_glow: { css: 'glow-moon' },
      avatar_frame: { css: 'frame-oak' },
      avatar_halo: { css: 'halo-ice' },
      title: 'Хранитель',
      title_css: 'title-frostchild',
      profile_bg: { css: 'pbg-forest' },
      card_fx: { css: 'cfx-sparks' },
    }, 6],
  ];
  for (const [fixtureName, cosmetics, expectedCount] of showcaseFixtures) {
    for (const width of [320, 390, 430]) {
      const page = await browser.newPage();
      await page.setViewport({ width, height: 844, deviceScaleFactor: 1 });
      await page.goto('http://localhost:8402/', { waitUntil: 'load' });
      await page.waitForFunction(() => typeof switchPage === 'function');
      await page.evaluate(async cosmeticFixture => {
        const originalApi = window.api;
        const profile = await originalApi('/profile/me');
        window.api = (path, ...args) => path === '/profile/me'
          ? Promise.resolve({ ...profile, cosmetics: cosmeticFixture })
          : originalApi(path, ...args);
        document.getElementById('preloader')?.style.setProperty('display', 'none');
        switchPage('profile');
        loadProfile();
        scrollTo(0, 0);
      }, cosmetics);
      await page.waitForSelector('[data-open-looks="profile-showcase"]');
      await new Promise(resolve => setTimeout(resolve, 300));
      const state = await page.evaluate(() => {
        const control = document.querySelector('[data-open-looks="profile-showcase"]');
        const portrait = document.querySelector('#pro-showcase-ava');
        const card = document.querySelector('.profile-showcase-card');
        const effect = control?.querySelector('.card-fx');
        const portraitImage = portrait?.querySelector('img');
        const headerImage = document.querySelector('#pro-ava img');
        return {
          pageWidth: document.documentElement.scrollWidth,
          text: control?.textContent.replace(/\s+/g, ' ').trim() || '',
          captionMeta: control?.querySelector('.character-showcase-caption small')?.textContent.replace(/\s+/g, ' ').trim() || '',
          portraitWidth: portrait?.getBoundingClientRect().width || 0,
          hasFrame: portrait?.classList.contains('frame-oak') || false,
          cardFxPointerEvents: effect ? getComputedStyle(effect).pointerEvents : '',
          stageHasBackground: !!control?.classList.contains('pbg-forest'),
          outerBackgroundIsNeutral: getComputedStyle(card).backgroundImage === 'none',
          portraitImageSource: portraitImage?.src || '',
          headerImageSource: headerImage?.src || '',
        };
      });
      const tag = `${fixtureName}/${width}px`;
      check(state.pageWidth === width, `${tag}: player canvas overflows`);
      check(new RegExp(`\\b${expectedCount} из 6\\b`).test(state.text), `${tag}: wrong equipped-look count`);
      check(state.captionMeta === (expectedCount === 6 ? 'Полный образ на сцене' : 'Собери свой первый образ'), `${tag}: stage copy does not match the visible cosmetic layers`);
      check(state.portraitWidth >= 88 && state.portraitWidth <= 112, `${tag}: portrait is not visible at a safe size`);
      check(state.hasFrame === (expectedCount === 6), `${tag}: frame layer does not match the fixture`);
      if (expectedCount === 6) check(state.cardFxPointerEvents === 'none'
        && state.stageHasBackground && state.outerBackgroundIsNeutral,
        `${tag}: cosmetic background/effect must stay inside the stage, not obscure profile data`);

      // Telegram photo is applied to both the compact identity and the large
      // stage rather than leaving the latter as a stale fallback glyph.
      const sources = await page.evaluate(() => {
        _vipAvatar = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==';
        _applyVipAvatar();
        return [document.querySelector('#pro-ava img')?.src || '', document.querySelector('#pro-showcase-ava img')?.src || ''];
      });
      check(sources[0] && sources[0] === sources[1], `${tag}: VIP photo is not mirrored into the stage`);
      await page.close();
    }
  }

  const page = await browser.newPage();
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.goto('http://localhost:8402/', { waitUntil: 'load' });
  await page.waitForFunction(() => typeof switchPage === 'function');
  await page.evaluate(() => {
    const preloader = document.getElementById('preloader');
    if (preloader) preloader.style.display = 'none';
  });
  for (const name of ['profile', 'zoo', 'arena', 'market', 'more', 'auction', 'bp', 'help']) {
    await page.evaluate(pageName => { switchPage(pageName); scrollTo(0, 0); }, name);
    await new Promise(resolve => setTimeout(resolve, 500));
    const screen = await page.evaluate(pageName => ({
      active: document.querySelector('.page.active')?.id,
      width: document.documentElement.scrollWidth,
      expected: `pg-${pageName}`,
    }), name);
    check(screen.active === screen.expected, `${name}: navigation did not activate the expected page`);
    check(screen.width === 390, `${name}: shared redesign causes horizontal overflow`);
  }
  await page.close();
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(failures.map(failure => `FAIL ${failure}`).join('\n'));
  process.exit(1);
}

console.log('OK: hybrid player showcase and shared site redesign verified at 320/390/430px');
