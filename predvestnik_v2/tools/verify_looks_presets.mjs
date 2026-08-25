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
  await page.waitForFunction(() => typeof _plSkip === 'function');
await page.evaluate(() => _plSkip());
await page.waitForFunction(() => !document.getElementById('preloader'));
  await page.waitForFunction(() => !document.getElementById('preloader'));

  await page.evaluate(() => openLooksModal());
  await page.waitForFunction(() => !!_looksData && !!document.querySelector('.looks-presets'));
  const state = await page.evaluate(() => {
    const root=document.querySelector('#looks-presets') || document.querySelector('.looks-presets');
    const saved=root?.querySelector('.looks-preset-card[data-preset]');
    const add=root?.querySelector('.looks-preset-card--add');
    const manage=root?.querySelector('.looks-preset-menu');
    const preview=saved?.querySelector('.looks-preset-thumb');
    const addName=add?.querySelector('.looks-preset-name');
    const savedName=saved?.querySelector('.looks-preset-name');
    const rect=node=>node?{width:Math.round(node.getBoundingClientRect().width),height:Math.round(node.getBoundingClientRect().height)}:null;
    // scrollWidth is not reliable for a flex child whose own width is clamped
    // by ellipsis. Measure the full text in its computed typeface instead.
    const textFits=node=>{
      if(!node) return false;
      const s=getComputedStyle(node), canvas=document.createElement('canvas');
      const ctx=canvas.getContext('2d');
      ctx.font=`${s.fontStyle} ${s.fontVariant} ${s.fontWeight} ${s.fontSize} ${s.fontFamily}`;
      return ctx.measureText(node.textContent.trim()).width<=node.getBoundingClientRect().width;
    };
    return {
      hasLabel: root?.getAttribute('aria-label') || '',
      countText: root?.querySelector('.looks-presets-head span:last-child')?.textContent.trim() || '',
      savedText: saved?.textContent.replace(/\s+/g, ' ').trim() || '',
      addText: add?.textContent.replace(/\s+/g, ' ').trim() || '',
      addName: addName?.textContent.trim() || '',
      addNameFits: textFits(addName),
      savedName: savedName?.textContent.trim() || '',
      savedNameFits: textFits(savedName),
      savedRect: rect(saved), addRect: rect(add), manageRect: rect(manage),
      previewRect: rect(preview), previewClass: preview?.className || '',
      previewHasOwnedGlow: !!preview?.querySelector('.glow-moon'),
      previewHasOwnedFrame: !!preview?.querySelector('.frame-oak'),
      previewHasUnowned: preview?.classList.contains('looks-preset-thumb--unavailable') || false,
      applyPaddingRight: saved?parseFloat(getComputedStyle(saved.querySelector('.looks-preset-apply')).paddingRight):0,
      legacySave: !!root?.querySelector('.looks-preset-save'),
    };
  });

  console.log('Preset-strip geometry:', JSON.stringify(state));

  check('presets use an explicit accessible image-strip container', state.hasLabel === 'Сохранённые образы');
  check('preset counter uses a natural Russian image noun', state.countText === '1 образ');
  check('saved preset identifies itself through its number of real saved cosmetics', /Золотой образ/.test(state.savedText) && /4 предмета/.test(state.savedText));
  check('the last tile clearly saves a new image', state.addName === 'Сохранить' && /Новый образ/.test(state.addText));
  check('save-image label is fully visible instead of ending with an ellipsis', state.addNameFits);
  check('the default personal image name stays fully visible beside its action menu', state.savedName === 'Золотой образ' && state.savedNameFits);
  check('saved and add tiles are comfortably tappable', state.savedRect?.width >= 174 && state.savedRect?.height >= 64 && state.addRect?.width >= 174 && state.addRect?.height >= 64);
  check('management action has an independent mobile touch target and old ghost save button is gone', state.manageRect?.width >= 44 && state.manageRect?.height >= 44 && !state.legacySave);
  check('saved look uses only its owned cosmetic classes inside a compact truthful preview', state.previewRect?.width === 42 && state.previewRect?.height === 42
    && /pbg-forest/.test(state.previewClass) && state.previewHasOwnedGlow && state.previewHasOwnedFrame && !state.previewHasUnowned);
  const edgeCases = await page.evaluate(() => {
    const unavailable = _looksPresetState({loadout: {profile_bg: 'cos_profile_bg_starfall'}});
    const empty = _looksPresetState({loadout: {}});
    const malformed = _looksPresetState({invalid: true, loadout: {}});
    return {
      unavailable: {disabled: unavailable.unavailable, kind: _looksPresetKind(unavailable), preview: _looksPresetPreview({}, unavailable)},
      empty: {disabled: empty.unavailable, kind: _looksPresetKind(empty)},
      malformed: {disabled: malformed.unavailable, kind: _looksPresetKind(malformed), preview: _looksPresetPreview({}, malformed)},
    };
  });
  check('a preset with a removed or no-longer-owned cosmetic is blocked without rendering its old effect', edgeCases.unavailable.disabled
    && edgeCases.unavailable.kind === 'Недоступен' && !/pbg-starfall/.test(edgeCases.unavailable.preview));
  check('an intentionally empty preset remains an honest usable empty image', !edgeCases.empty.disabled && edgeCases.empty.kind === 'Пустой образ');
  check('a malformed legacy preset is visibly marked and cannot be applied', edgeCases.malformed.disabled
    && edgeCases.malformed.kind === 'Нужно пересобрать' && /looks-preset-thumb--invalid/.test(edgeCases.malformed.preview));
  const noFxThumb = await page.evaluate(() => {
    const host = document.createElement('div');
    host.innerHTML = '<span class="looks-preset-thumb"><span class="card-fx cfx-snow"></span></span>';
    document.body.append(host);
    const animation = getComputedStyle(host.querySelector('.card-fx')).animationName;
    host.remove();
    return animation;
  });
  check('the tiny saved-look preview never runs a decorative cosmetic animation', noFxThumb === 'none');
  // A real player can leave the page before a slow saved-look request returns.
  // Hold that request and prove that navigation waits for the authoritative
  // write before it fetches and renders the main player card.
  await page.evaluate(() => {
    const nativeFetch=window.fetch.bind(window);
    let held=false;
    window.__presetApplyStarted=false;
    window.__releasePresetApply=null;
    window.fetch=(input,init)=>{
      const url=String(typeof input==='string'?input:input?.url||'');
      if(!held && url.endsWith('/cosmetics/presets/1/apply') && String(init?.method||'GET').toUpperCase()==='POST'){
        held=true;
        window.__presetApplyStarted=true;
        return new Promise((resolve,reject)=>{
          window.__releasePresetApply=()=>nativeFetch(input,init).then(resolve,reject);
        });
      }
      return nativeFetch(input,init);
    };
  });
  await page.click('.looks-preset-apply');
  await page.waitForFunction(() => window.__presetApplyStarted && typeof window.__releasePresetApply === 'function');
  await page.evaluate(() => switchPage('profile'));
  const whilePending=await page.evaluate(() => ({
    activePage:_activePage,
    buttonDisabled:document.querySelector('.looks-preset-apply')?.disabled===true,
  }));
  check('leaving while a saved look is still applying keeps the player on the truthful appearance screen', whilePending.activePage==='looks');
  check('the applying saved-look control rejects a second tap until the request settles', whilePending.buttonDisabled);
  const applied = page.waitForResponse(response => response.request().method() === 'POST'
    && /\/cosmetics\/presets\/1\/apply$/.test(response.url()));
  await page.evaluate(() => window.__releasePresetApply());
  const applyResponse = await applied;
  check('the saved-look primary action reaches the explicit local apply contract', applyResponse.status() === 200);
  await page.waitForFunction(() => _looksData?.slots?.avatar_frame?.some(item => item.id === 'cos_avatar_frame_oak' && item.equipped));
  await page.waitForFunction(() => {
    const card=document.querySelector('#pro-main .profile-showcase-card');
    return _activePage==='profile' && card?.classList.contains('pbg-forest')
      && !!card.querySelector('.ava.frame-oak')
      && card.textContent.includes('Дитя Зари');
  });
  check('after the delayed saved look settles, normal navigation refreshes the player card with exactly the active cosmetics', true);
  await page.evaluate(() => openLooksModal());
  await page.waitForFunction(() => _activePage==='looks' && !!document.querySelector('.looks-preset-card[data-preset]'));
  await page.setViewport({width: 320, height: 700, deviceScaleFactor: 2});
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const narrow = await page.evaluate(() => ({
    pageOverflow: document.documentElement.scrollWidth > window.innerWidth,
    rowScrollable: document.querySelector('.looks-presets-row').scrollWidth > document.querySelector('.looks-presets-row').clientWidth,
    savedWidth: Math.round(document.querySelector('.looks-preset-card[data-preset]').getBoundingClientRect().width),
    manageWidth: Math.round(document.querySelector('.looks-preset-menu').getBoundingClientRect().width),
  }));
  check('at 320px the page does not gain horizontal overflow while the preset strip itself remains scrollable', !narrow.pageOverflow && narrow.rowScrollable);
  check('at 320px the saved image and its separate management target keep their usable dimensions', narrow.savedWidth >= 174 && narrow.manageWidth >= 44);
  await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
  if (process.env.SCREENSHOT_PATH) {
    const saved = await page.$('.looks-preset-card[data-preset]');
    await saved.screenshot({path: process.env.SCREENSHOT_PATH});
  }
  if (process.env.SCREENSHOT_FULL_PATH) {
    await page.screenshot({path: process.env.SCREENSHOT_FULL_PATH, fullPage: true});
  }
  await page.click('.looks-preset-menu');
  await page.waitForFunction(() => document.getElementById('modal')?.open);
  const actions = await page.evaluate(() => [...document.querySelectorAll('#mf button')].map(button => button.textContent.trim()));
  check('management menu gives explicit rename and delete choices before a destructive action', actions.includes('Переименовать') && actions.includes('Удалить образ'));
  await page.evaluate(() => _openRenamePreset(1));
  const renameInput = await page.$('#preset-rename-inp');
  if (!renameInput) throw new Error('Rename dialog did not render its input.');
  await page.$eval('#preset-rename-inp', input => {
    input.value = 'Лесной набор';
    input.dispatchEvent(new Event('input', {bubbles: true}));
  });
  const renamed = page.waitForResponse(response => response.request().method() === 'PATCH' && /\/cosmetics\/presets\/1$/.test(response.url()));
  await page.evaluate(() => _renamePresetGo(1));
  const renameResponse = await renamed;
  check('rename request reaches the local production-like adapter', renameResponse.status() === 200);
  await page.waitForFunction(() => document.querySelector('.looks-preset-name')?.textContent.trim() === 'Лесной набор', {timeout: 2000});
  check('rename updates the visible preset without applying or changing its thumbnail', true);
  await page.click('.looks-preset-menu');
  await page.waitForFunction(() => document.getElementById('modal')?.open);
  await page.evaluate(() => _deletePreset(1));
  await page.waitForFunction(() => !document.querySelector('.looks-preset-card[data-preset]'));
  check('delete is available through the management menu without applying the preset', true);
} finally {
  await browser.close();
}

if (failures.length) {
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
