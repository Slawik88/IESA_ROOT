import puppeteer from 'puppeteer';

const failures = [];
function check(label, condition) {
  if (condition) console.log(`OK: ${label}`);
  else {
    console.error(`FAIL: ${label}`);
    failures.push(label);
  }
}

const browser = await puppeteer.launch({headless: 'new'});
const page = await browser.newPage();
await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
await page.goto('http://localhost:8402/', {waitUntil: 'load'});
await page.waitForFunction(() => typeof openLooksModal === 'function');
await page.waitForFunction(() => typeof _plSkip === 'function');
await page.evaluate(() => _plSkip());
await page.waitForFunction(() => !document.getElementById('preloader'));
await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');
await page.evaluate(() => openLooksModal());
await page.waitForFunction(() => _activePage === 'looks' && !!_looksData);

await page.evaluate(() => {
  _looksTapUnowned('profile_bg', 'cos_profile_bg_starfall');
  _looksTapUnowned('avatar_frame', 'cos_avatar_frame_inferno');
  // Именно нижняя навигация раньше обходила _looksClose() и теряла выбранный образ.
  switchPage('profile');
});
await page.waitForFunction(() => _activePage === 'profile' && !!document.querySelector('#pro-main .hero'));

const profileState = await page.evaluate(() => {
  const hero = document.querySelector('#pro-main .hero');
  const entry = document.querySelector('#pro-main [data-open-looks="profile-showcase"]');
  const caption = document.querySelector('#pro-main .character-showcase-caption');
  const entryRect = entry?.getBoundingClientRect();
  const heroRect = hero?.getBoundingClientRect();
  let stored = null;
  try { stored = JSON.parse(sessionStorage.getItem('pv_looks_trial_v1') || 'null'); } catch (_) {}
  return {
    activePage: _activePage,
    hasTrialBackground: hero?.classList.contains('pbg-starfall') || false,
    hasTrialFrame: hero?.querySelector('.ava')?.classList.contains('frame-inferno') || false,
    entryInsideProfileCard: !!entry && !!hero?.contains(entry),
    entryText: entry?.textContent.replace(/\s+/g, ' ').trim() || '',
    captionText: caption?.textContent.replace(/\s+/g, ' ').trim() || '',
    entryHasNoNestedControls: !entry?.querySelector('button, a, input, select, textarea'),
    entryHeight: entryRect?.height || 0,
    entryFillsStage: !!entryRect && !!heroRect && entryRect.width >= heroRect.width * .5,
    noHorizontalOverflow: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    storedSlots: stored?.ids ? Object.keys(stored.ids).sort() : [],
  };
});

console.log('Profile trial state:', JSON.stringify(profileState));
check('bottom navigation returns to the profile after finalising appearance state', profileState.activePage === 'profile');
check('unpaid trial background does not impersonate an equipped main-profile item', !profileState.hasTrialBackground);
check('unpaid trial frame does not impersonate an equipped main-profile item', !profileState.hasTrialFrame);
check('draft fitting entry stays integrated into the player card', profileState.entryInsideProfileCard);
check('main profile offers a clear return to the saved draft', /Продолжить примерку/.test(profileState.entryText)
  && /Черновик:\s*2 предмета сохранено/.test(profileState.captionText) && profileState.entryHasNoNestedControls);
check('fitting-session return action keeps the complete visual-stage touch target', profileState.entryHeight >= 268);
check('draft return uses the single visual stage instead of a second header control', profileState.entryFillsStage);
check('trial profile remains inside the 390px viewport', profileState.noHorizontalOverflow);
check('trial selections persist for the current browser tab', profileState.storedSlots.join(',') === 'avatar_frame,profile_bg');

await page.setViewport({width: 320, height: 780, deviceScaleFactor: 2});
check('active fitting-session entry remains contained on a narrow phone', await page.evaluate(() => {
  const entry = document.querySelector('#pro-main [data-open-looks="profile-showcase"]');
  const entryRect = entry?.getBoundingClientRect();
  return !!entryRect && entryRect.left >= 0
    && entryRect.right <= document.documentElement.clientWidth && entryRect.height >= 268;
}));
await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});

if (process.env.SCREENSHOT_PATH) {
  await new Promise(resolve => setTimeout(resolve, 700));
  await page.screenshot({path: process.env.SCREENSHOT_PATH});
}

const entryExists = await page.$('#pro-main [data-open-looks="profile-showcase"]');
if (entryExists) await page.click('#pro-main [data-open-looks="profile-showcase"]');
else await page.evaluate(() => openLooksModal());
await page.waitForFunction(() => _activePage === 'looks' && !!_looksData);
check('reopening appearance keeps both active trial selections', await page.evaluate(() =>
  _looksTrial.profile_bg === 'cos_profile_bg_starfall'
  && _looksTrial.avatar_frame === 'cos_avatar_frame_inferno'));

await page.reload({waitUntil: 'load'});
await page.waitForFunction(() => typeof openLooksModal === 'function');
await page.waitForFunction(() => typeof _plSkip === 'function');
await page.evaluate(() => _plSkip());
await page.waitForFunction(() => !document.getElementById('preloader'));
await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');
await page.waitForFunction(() => !!document.querySelector('#pro-main .hero'));
check('trial look survives an in-tab reload', await page.evaluate(() => {
  const hero = document.querySelector('#pro-main .hero');
  let stored = null;
  try { stored = JSON.parse(sessionStorage.getItem('pv_looks_trial_v1') || 'null'); } catch (_) {}
  return !hero?.classList.contains('pbg-starfall')
    && !hero?.querySelector('.ava')?.classList.contains('frame-inferno')
    && /\u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c \u043f\u0440\u0438\u043c\u0435\u0440\u043a\u0443/.test(document.querySelector('#pro-main [data-open-looks="profile-showcase"]')?.textContent || '')
    && /\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a/.test(document.querySelector('#pro-main .character-showcase-caption')?.textContent || '')
    && stored?.ids?.profile_bg === 'cos_profile_bg_starfall'
    && stored?.ids?.avatar_frame === 'cos_avatar_frame_inferno';
}));

await page.evaluate(() => openLooksModal());
await page.waitForFunction(() => _activePage === 'looks' && !!_looksData);
await page.evaluate(() => {
  _looksReset();
  switchPage('profile');
});
await page.waitForFunction(() => _activePage === 'profile' && !!document.querySelector('#pro-main .hero'));
check('resetting the fitting session restores the equipped profile and removes the status chip', await page.evaluate(() => {
  const hero = document.querySelector('#pro-main .hero');
  return !hero?.classList.contains('pbg-starfall')
    && !hero?.querySelector('.ava')?.classList.contains('frame-inferno')
    && !/\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a/.test(document.querySelector('#pro-main .character-showcase-caption')?.textContent || '')
    && !sessionStorage.getItem('pv_looks_trial_v1');
}));

await page.evaluate(() => openLooksModal());
await page.waitForFunction(() => _activePage === 'looks' && !!_looksData);
await page.evaluate(() => {
  window.__looksMutationPaths = [];
  const realApi = window.api;
  window.api = (path, options) => {
    if (path === '/cosmetics/equip' || path === '/cosmetics/unequip') {
      window.__looksMutationPaths.push(path);
    }
    return realApi(path, options);
  };
  _looksUnequip('title');
  switchPage('profile');
});
await page.waitForFunction(() => _activePage === 'profile');
check('bottom navigation also applies changes to already-owned cosmetics', await page.evaluate(() =>
  window.__looksMutationPaths.includes('/cosmetics/unequip')));

await browser.close();
if (failures.length) {
  console.error(`\n${failures.length} fitting-room persistence check(s) failed.`);
  process.exit(1);
}
console.log('\nALL OK');
