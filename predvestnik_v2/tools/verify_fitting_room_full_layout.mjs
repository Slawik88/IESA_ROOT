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
  const frostLook = {
    name_glow: 'cos_name_glow_frost',
    avatar_frame: 'cos_avatar_frame_crystal',
    avatar_halo: 'cos_avatar_halo_ice',
    title: 'cos_title_frostchild',
    profile_bg: 'cos_profile_bg_snowpeak',
    card_fx: 'cos_card_fx_snow',
  };
  Object.entries(frostLook).forEach(([slot, id]) => _looksTapUnowned(slot, id));
  _looksOpenFittingSheet();
});
await page.waitForFunction(() => document.querySelectorAll('#mb .fit-outfit-row.trial').length === 6);
await new Promise(resolve => setTimeout(resolve, 400));

const state = await page.evaluate(() => {
  const body = document.getElementById('mb');
  const list = body?.querySelector('.fit-outfit-list');
  const collection = body?.querySelector('.fit-collection-card');
  const rows = [...(body?.querySelectorAll('.fit-outfit-row') || [])];
  const profile = body?.querySelector('.fit-player-card');
  const profileMain=profile?.querySelector('.profile-showcase-main');
  const profileCanvas=profile?.querySelector('.character-showcase-area');
  const profileRail=profile?.querySelector('.player-data-rail--compact');
  const footerButtons = [...document.querySelectorAll('#mf .btn')];
  const frameHalo = profile?.querySelector('.ava.frame-crystal.halo-ice');
  const rowRects = rows.map(row => row.getBoundingClientRect());
  const footerRects = footerButtons.map(button => button.getBoundingClientRect());
  return {
    fittingContextClass: document.getElementById('modal')?.classList.contains('looks-fitting-modal') || false,
    unifiedCollectionSurface: body?.querySelectorAll('.fit-collection-card').length === 1,
    collectionName: collection?.querySelector('.fit-collection-name')?.textContent.trim() || '',
    collectionTotal: collection?.querySelector('.fit-collection-total')?.textContent.trim() || '',
    gridColumns: list ? getComputedStyle(list).gridTemplateColumns.split(' ').length : 0,
    allSixRows: rows.length === 6,
    minRowHeight: rowRects.length ? Math.min(...rowRects.map(rect => rect.height)) : 0,
    maxRowHeight: rowRects.length ? Math.max(...rowRects.map(rect => rect.height)) : 0,
    allNamesFullyVisible: rows.every(row => {
      const name = row.querySelector('.fit-outfit-main strong');
      return !!name && name.scrollHeight <= name.clientHeight + 1 && name.scrollWidth <= name.clientWidth + 1;
    }),
    bodyFitsWithoutScroll: !!body && body.scrollHeight <= body.clientHeight + 1,
    noHorizontalOverflow: !!body && body.scrollWidth <= body.clientWidth,
    profileUsesCurrentStructure: !!(profile?.classList.contains('profile-showcase-card--fitting')
      && profile.querySelector('.character-showcase-area')
      && profile.querySelector('.player-data-rail')
      && profile.querySelector('.profile-resource-rail')),
    profileStageSize: profile?.querySelector('.character-showcase-portrait')?.getBoundingClientRect().width || 0,
    profileFullyVisible: !!profile && profile.getBoundingClientRect().top >= body.getBoundingClientRect().top
      && profile.getBoundingClientRect().bottom <= body.getBoundingClientRect().bottom,
    compactRailRows: profileRail ? getComputedStyle(profileRail).gridTemplateRows.split(' ').filter(Boolean).length : 0,
    compactRailFits: !!profileMain && !!profileRail && [...profileRail.children].length===3
      && profileRail.getBoundingClientRect().bottom <= profileMain.getBoundingClientRect().bottom + 1,
    compactCanvasFits: !!profileMain && !!profileCanvas
      && profileCanvas.getBoundingClientRect().bottom <= profileMain.getBoundingClientRect().bottom + 1,
    compactCanvasPaddingBottom: profileCanvas ? parseFloat(getComputedStyle(profileCanvas).paddingBottom) : Infinity,
    compactGeometry: {
      main: profileMain ? {top:profileMain.getBoundingClientRect().top,bottom:profileMain.getBoundingClientRect().bottom,height:profileMain.getBoundingClientRect().height} : null,
      canvas: profileCanvas ? {top:profileCanvas.getBoundingClientRect().top,bottom:profileCanvas.getBoundingClientRect().bottom,height:profileCanvas.getBoundingClientRect().height} : null,
      rail: profileRail ? {top:profileRail.getBoundingClientRect().top,bottom:profileRail.getBoundingClientRect().bottom,height:profileRail.getBoundingClientRect().height} : null,
      railChildren: profileRail ? [...profileRail.children].map(item=>item.getBoundingClientRect().height) : [],
    },
    fittingCaptionHidden: profile
      ? getComputedStyle(profile.querySelector('.character-showcase-caption')).display === 'none'
      : false,
    resetIsSecondaryWidth: footerRects.length === 2 && footerRects[0].width < footerRects[1].width,
    minFooterTarget: footerRects.length ? Math.min(...footerRects.map(rect => rect.height)) : 0,
    actionText: footerButtons[1]?.textContent.replace(/\s+/g, ' ').trim() || '',
    actionIsSingleLine: footerButtons[1] ? footerButtons[1].scrollHeight <= footerButtons[1].clientHeight + 1 : false,
    disabledActionOpacity: footerButtons[1] ? parseFloat(getComputedStyle(footerButtons[1]).opacity) : 0,
    pairedHaloUsesSeparateLayer: !!frameHalo && getComputedStyle(frameHalo).filter === 'none'
      && getComputedStyle(frameHalo, '::after').content !== 'none'
      && getComputedStyle(frameHalo, '::after').borderTopWidth === '0px'
      && getComputedStyle(frameHalo, '::after').borderRadius === '50%',
    noRepeatedTrialLabels: rows.every(row => !/Примеряется/.test(row.textContent)),
    rowsDoNotLookLikeSeparateCards: rows.every(row => getComputedStyle(row).borderTopWidth === '0px'),
  };
});

console.log('Full fitting-room layout:', JSON.stringify(state));
check('full fitting room uses its own high-capacity bottom-sheet context', state.fittingContextClass);
check('the six items are presented as one collection instead of six unrelated cards', state.unifiedCollectionSurface && state.collectionName.includes('Изморозь'));
check('the unified collection keeps its transparent total price visible', /2680✨/.test(state.collectionTotal));
check('six cosmetic slots form a compact two-column collection grid', state.allSixRows && state.gridColumns === 2);
check('collection items remain comfortably touchable without becoming tall transaction rows', state.minRowHeight >= 52 && state.maxRowHeight <= 68);
check('collection state is expressed once instead of repeating “Примеряется” six times', state.noRepeatedTrialLabels);
check('items share one collection surface instead of six bordered mini-cards', state.rowsDoNotLookLikeSeparateCards);
check('all six cosmetic names remain fully readable', state.allNamesFullyVisible);
check('the complete 6/6 composition fits in the 390px sheet without hidden rows', state.bodyFitsWithoutScroll);
check('the 6/6 composition has no horizontal overflow', state.noHorizontalOverflow);
check('the current player-card scene remains visible and identifiable in the fitting sheet',
  state.profileUsesCurrentStructure && state.profileStageSize >= 60 && state.profileFullyVisible && state.fittingCaptionHidden);
check('the compact fitting card has exactly three data rows without overlapping its resource rail',
  state.compactRailRows === 3 && state.compactRailFits && state.compactCanvasFits && state.compactCanvasPaddingBottom < 20);
check('reset stays visually secondary to the purchase action', state.resetIsSecondaryWidth);
check('both fitting-room footer actions keep a 44px mobile touch target', state.minFooterTarget >= 44);
check('insufficient-balance action uses a concise single-line label', /Не хватает \d+✨/.test(state.actionText) && state.actionIsSingleLine);
check('disabled purchase feedback remains legible while clearly inactive', state.disabledActionOpacity >= .55 && state.disabledActionOpacity < .8);
check('paired Frost frame and halo use a borderless circular halo instead of a second rounded box', state.pairedHaloUsesSeparateLayer);

await page.setViewport({width: 320, height: 780, deviceScaleFactor: 2});
const narrow = await page.evaluate(() => {
  const body = document.getElementById('mb');
  const list = body?.querySelector('.fit-outfit-list');
  const rows = [...(body?.querySelectorAll('.fit-outfit-row') || [])];
  return {
    gridColumns: list ? getComputedStyle(list).gridTemplateColumns.split(' ').length : 0,
    noHorizontalOverflow: !!body && body.scrollWidth <= body.clientWidth,
    namesReadable: rows.every(row => {
      const name = row.querySelector('.fit-outfit-main strong');
      return !!name && name.scrollHeight <= name.clientHeight + 1 && name.scrollWidth <= name.clientWidth + 1;
    }),
    minRowHeight: rows.length ? Math.min(...rows.map(row => row.getBoundingClientRect().height)) : 0,
  };
});
console.log('Narrow full fitting-room layout:', JSON.stringify(narrow));
check('320px fitting room keeps the two-column wardrobe without horizontal overflow', narrow.gridColumns === 2 && narrow.noHorizontalOverflow);
check('320px collection keeps names readable and touch targets safe', narrow.namesReadable && narrow.minRowHeight >= 52);

await browser.close();
if (failures.length) {
  console.error(`\n${failures.length} full fitting-room layout check(s) failed.`);
  process.exit(1);
}
console.log('\nALL OK');
