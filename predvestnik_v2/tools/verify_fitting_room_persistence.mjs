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
await page.mouse.click(195, 700);
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
  const chip = document.querySelector('#pro-main .profile-trial-chip');
  const chipRect = chip?.getBoundingClientRect();
  const heroRect = hero?.getBoundingClientRect();
  let stored = null;
  try { stored = JSON.parse(sessionStorage.getItem('pv_looks_trial_v1') || 'null'); } catch (_) {}
  return {
    activePage: _activePage,
    hasTrialBackground: hero?.classList.contains('pbg-starfall') || false,
    hasTrialFrame: hero?.querySelector('.ava')?.classList.contains('frame-inferno') || false,
    chipOutsideProfileCard: !!chip && !hero?.contains(chip),
    chipText: chip?.textContent.replace(/\s+/g, ' ').trim() || '',
    chipSubText: chip?.querySelector('.profile-trial-sub')?.textContent.replace(/\s+/g, ' ').trim() || '',
    chipHasStructuredCopy: !!chip?.querySelector('.profile-trial-avatar')
      && !!chip?.querySelector('.profile-trial-copy')
      && !!chip?.querySelector('.profile-trial-arrow'),
    chipHeight: chipRect?.height || 0,
    chipRadius: chip ? parseFloat(getComputedStyle(chip).borderRadius) : 0,
    chipIsCompact: !!chipRect && !!heroRect && chipRect.width < heroRect.width * .8,
    noHorizontalOverflow: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    storedSlots: stored?.ids ? Object.keys(stored.ids).sort() : [],
  };
});

console.log('Profile trial state:', JSON.stringify(profileState));
check('bottom navigation returns to the profile after finalising appearance state', profileState.activePage === 'profile');
check('unpaid trial background does not impersonate an equipped main-profile item', !profileState.hasTrialBackground);
check('unpaid trial frame does not impersonate an equipped main-profile item', !profileState.hasTrialFrame);
check('draft fitting entry stays outside the authentic profile card', profileState.chipOutsideProfileCard);
check('main profile offers a concise two-line return to the saved draft', /Продолжить примерку/.test(profileState.chipText)
  && /Сохранено:\s*2 предмета/.test(profileState.chipSubText) && profileState.chipHasStructuredCopy);
check('fitting-session return action keeps a 44px mobile touch target', profileState.chipHeight >= 44);
check('draft return uses a compact mini-dock shape instead of a raw pill', profileState.chipHeight <= 52 && profileState.chipRadius <= 18);
check('fitting-session return action stays compact instead of spanning the card', profileState.chipIsCompact);
check('trial profile remains inside the 390px viewport', profileState.noHorizontalOverflow);
check('trial selections persist for the current browser tab', profileState.storedSlots.join(',') === 'avatar_frame,profile_bg');

await page.setViewport({width: 320, height: 780, deviceScaleFactor: 2});
check('active fitting-session chip remains contained on a narrow phone', await page.evaluate(() => {
  const chip = document.querySelector('#pro-main .profile-trial-chip');
  const chipRect = chip?.getBoundingClientRect();
  return !!chipRect && chipRect.left >= 0
    && chipRect.right <= document.documentElement.clientWidth && chipRect.height >= 44;
}));
await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});

if (process.env.SCREENSHOT_PATH) {
  await new Promise(resolve => setTimeout(resolve, 700));
  await page.screenshot({path: process.env.SCREENSHOT_PATH});
}

const chipExists = await page.$('#pro-main .profile-trial-chip');
if (chipExists) await page.click('#pro-main .profile-trial-chip');
else await page.evaluate(() => openLooksModal());
await page.waitForFunction(() => _activePage === 'looks' && !!_looksData);
check('reopening appearance keeps both active trial selections', await page.evaluate(() =>
  _looksTrial.profile_bg === 'cos_profile_bg_starfall'
  && _looksTrial.avatar_frame === 'cos_avatar_frame_inferno'));

await page.reload({waitUntil: 'load'});
await page.waitForFunction(() => typeof openLooksModal === 'function');
await page.mouse.click(195, 700);
await page.waitForFunction(() => document.elementFromPoint(195, 120)?.id !== 'preloader');
await page.waitForFunction(() => !!document.querySelector('#pro-main .hero'));
check('trial look survives an in-tab reload', await page.evaluate(() => {
  const hero = document.querySelector('#pro-main .hero');
  let stored = null;
  try { stored = JSON.parse(sessionStorage.getItem('pv_looks_trial_v1') || 'null'); } catch (_) {}
  return !hero?.classList.contains('pbg-starfall')
    && !hero?.querySelector('.ava')?.classList.contains('frame-inferno')
    && !!document.querySelector('#pro-main .profile-trial-chip')
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
    && !document.querySelector('#pro-main .profile-trial-chip')
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
