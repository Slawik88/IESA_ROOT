// Примерочная (Стадия 4): FAB + шторка + множественная примерка нескольких
// некупленных предметов из разных слотов и одна покупка всего набора.
import puppeteer from 'puppeteer';

const failures = [];
function check(name, condition) {
  if (!condition) failures.push(name);
  else console.log('OK:', name);
}

const browser = await puppeteer.launch({headless: 'new'});
const page = await browser.newPage();
await page.setViewport({width: 390, height: 844, deviceScaleFactor: 2});
await page.goto('http://localhost:8402/', {waitUntil: 'load'});
await new Promise(resolve => setTimeout(resolve, 1500));
await page.mouse.click(195, 700);
await new Promise(resolve => setTimeout(resolve, 500));
await page.evaluate(() => openLooksModal());
await new Promise(resolve => setTimeout(resolve, 800));

const initialFab = await page.evaluate(() => {
  const button = document.querySelector('.looks-fab');
  const nav = document.querySelector('nav');
  const label = button?.querySelector('.looks-fab-label');
  if (!button || !nav || !label) return {exists: !!button, hasBadge: false, dock: null};
  const b = button.getBoundingClientRect();
  const dock=document.getElementById('looks-dock');
  return {
    exists: true,
    hasBadge: !!button.querySelector('.looks-fab-badge'),
    dock: {
      label: label.textContent.trim(),
      portaledToBody: dock?.parentElement === document.body,
      fixed: !!dock && getComputedStyle(dock).position === 'fixed',
      staticButton: getComputedStyle(button).position === 'static',
      width: Math.round(b.width),
    },
  };
});
check('FAB отрендерен на странице', initialFab.exists);
check('у FAB нет бейджа до примерки', !initialFab.hasBadge);

check('dock panel has label', initialFab.dock?.label === 'Примерочная');
check('dock panel is portaled to the viewport outside the animated page', initialFab.dock?.portaledToBody === true && initialFab.dock?.fixed === true);
check('dock panel keeps a compact but clearly labelled tap target', initialFab.dock?.staticButton === true && initialFab.dock?.width >= 176 && initialFab.dock?.width <= 220);

await page.click('.looks-fab');
await new Promise(resolve => setTimeout(resolve, 300));
const initialSheet = await page.evaluate(() => {
  const card=document.querySelector('#looks-fit-top .hero');
  const rows=[...document.querySelectorAll('.fit-outfit-row')].map(row=>row.textContent.replace(/\s+/g,' ').trim());
  return {
    fullProfile: !!(card?.querySelector('.hero-head') && card.querySelector('.hero-xp') && card.querySelector('.cp-hero') && card.querySelector('.stats')),
    profileText: card?.textContent.replace(/\s+/g,' ').trim() || '',
    rows,
  };
});
check('fitting room shows the complete player profile card', initialSheet.fullProfile);
check('fitting room profile includes level, power and currencies', /Уровень 27/.test(initialSheet.profileText) && /ИНДЕКС СИЛЫ/.test(initialSheet.profileText) && /Зарники/.test(initialSheet.profileText));
check('outfit summary names the equipped name glow', initialSheet.rows.some(text=>/Ореол имени/.test(text) && /Лунный свет/.test(text) && /Надето/.test(text)));
check('outfit summary names the equipped title', initialSheet.rows.some(text=>/Титул/.test(text) && /Дитя Зари/.test(text) && /Надето/.test(text)));
check('outfit summary names an empty slot instead of a dash', initialSheet.rows.some(text=>/Рамка аватара/.test(text) && /Свободно/.test(text)));
const starfallEffect = await page.evaluate(() => {
  const hero = document.querySelector('#looks-fit-top .hero');
  if (!hero) return {hasVectorTrail: false, hasLegacyHardRay: true};
  const originalClassName = hero.className;
  hero.classList.remove(...[...hero.classList].filter(name => name.startsWith('pbg-')));
  hero.classList.add('pbg-starfall');
  const backgroundImage = getComputedStyle(hero).backgroundImage;
  hero.className = originalClassName;
  return {
    hasVectorTrail: backgroundImage.includes('image/svg+xml'),
    hasLegacyHardRay: backgroundImage.includes('linear-gradient(115deg'),
  };
});
check('starfall background renders soft vector trails instead of hard gradient bands',
  starfallEffect.hasVectorTrail && !starfallEffect.hasLegacyHardRay);

const delayedAvatar = await page.evaluate(() => {
  const initial=_vipAvatar;
  _vipAvatar='data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22/%3E';
  _applyVipAvatar();
  const src=document.querySelector('#fit-ava img')?.getAttribute('src') || '';
  _vipAvatar=initial;
  return src.startsWith('data:image/svg+xml,');
});
check('fitting room receives a VIP avatar loaded after it opens', delayedAvatar);
await page.evaluate(() => CM());
await new Promise(resolve => setTimeout(resolve, 150));

await page.click('[data-mode="slots"]');
await new Promise(resolve => setTimeout(resolve, 300));
await page.evaluate(() => {
  document.querySelector('#looks-grid-name_glow .looks-card.lc-buyable[data-cos]')?.click();
  document.querySelector('#looks-grid-avatar_frame .looks-card.lc-buyable[data-cos]')?.click();
});
await new Promise(resolve => setTimeout(resolve, 300));

const trialState = await page.evaluate(() => ({
  slots: Object.keys(_looksTrial),
  hasBadge: !!document.querySelector('.looks-fab-badge'),
  catalogTrialCards: [...document.querySelectorAll('.looks-card.lc-buyable.lc-trial')].map(card =>
    card.textContent.replace(/\s+/g, ' ').trim()),
}));
check('две примерки из разных слотов сохраняются одновременно',
  trialState.slots.includes('name_glow') && trialState.slots.includes('avatar_frame'));
check('FAB показывает бейдж при неоплаченной примерке', trialState.hasBadge);
check('catalog cards clearly state that the selected cosmetics are being tried on',
  trialState.catalogTrialCards.length === 2 && trialState.catalogTrialCards.every(text => text.includes('Примеряется')));

const replacementState = await page.evaluate(() => {
  const originalId=_looksTrial.name_glow;
  const replacement=[...document.querySelectorAll('#looks-grid-name_glow .looks-card.lc-buyable[data-cos]')]
    .find(card=>card.dataset.cos!==originalId);
  replacement?.click();
  return {originalId, replacementId:replacement?.dataset.cos, activeId:_looksTrial.name_glow,
    trialCardCount:document.querySelectorAll('#looks-grid-name_glow .looks-card.lc-trial').length};
});
check('a new trial replaces the previous item in the same slot',
  !!replacementState.replacementId && replacementState.activeId===replacementState.replacementId && replacementState.trialCardCount===1);
await page.evaluate(originalId =>
  [...document.querySelectorAll('#looks-grid-name_glow .looks-card.lc-buyable[data-cos]')]
    .find(card=>card.dataset.cos===originalId)?.click(), replacementState.originalId);
await new Promise(resolve => setTimeout(resolve, 150));

await page.click('[data-mode="collections"]');
await new Promise(resolve => setTimeout(resolve, 150));
const collectionTrialState = await page.evaluate(() =>
  [...document.querySelectorAll('.coll-card')]
    .find(card=>card.textContent.includes('Изморозь'))?.textContent.replace(/\s+/g,' ').trim() || '');
check('collection overview retains the active fitting status', collectionTrialState.includes('Примеряется'));

const collectionVisibility = await page.evaluate(() => {
  const textFor = lineup => document.querySelector(`.coll-card[data-lineup="${lineup}"]`)
    ?.textContent.replace(/\s+/g, ' ').trim() || '';
  return { frost: textFor('frost'), forest: textFor('forest') };
});
check('collection overview states the compact VIP visibility condition',
  collectionVisibility.frost.includes('С VIP'));
check('collection overview distinguishes a lineup that is visible to everyone',
  collectionVisibility.forest.includes('Всем'));

// На мобильном нижняя навигация перекрывает нижний край документа. Сначала явно
// доводим карточку до безопасной зоны, затем проверяем именно пользовательский тап.
await page.evaluate(() => document.querySelector('.coll-card[data-lineup="frost"]')?.scrollIntoView({block:'center'}));
await page.click('.coll-card[data-lineup="frost"]');
await new Promise(resolve => setTimeout(resolve, 150));
const collectionDetailVisibility = await page.evaluate(() =>
  document.querySelector('.coll-detail-head')?.textContent.replace(/\s+/g, ' ').trim() || '');
check('collection detail repeats the VIP display condition beside the collection price',
  collectionDetailVisibility.includes('На профиле — с VIP'));
check('collection detail makes clear that purchase remains available without VIP',
  collectionDetailVisibility.includes('Купить может каждый'));
const emptyCollectionSections = await page.evaluate(() =>
  [...document.querySelectorAll('#looks-sections .looks-section')]
    .filter(section => !!section.querySelector('.looks-empty')).length);
check('collection detail omits slots that have no cosmetics in that collection', emptyCollectionSections === 0);

await page.click('.looks-fab');
await new Promise(resolve => setTimeout(resolve, 400));
const sheetState = await page.evaluate(() => ({
  modalOpen: document.getElementById('modal').open,
  viewTransitionSupported: !!document.startViewTransition,
  sharedTransition: document.getElementById('modal').classList.contains('looks-fitting-shared'),
  transitionNameAfterFinish: getComputedStyle(document.querySelector('#looks-fit-top .fit-player-card')).viewTransitionName,
  hasHeroCard: !!document.querySelector('#looks-fit-top .hero'),
  trialChipCount: document.querySelectorAll('.fit-outfit-row.trial').length,
  trialRows: [...document.querySelectorAll('.fit-outfit-row.trial')].map(row=>row.textContent.replace(/\s+/g,' ').trim()),
  goldButtonCount: document.querySelectorAll('#mf .btn-gold').length,
  actionText: document.querySelector('#mf .btn-gold, #mf .btn-ghost:last-child')?.textContent || '',
}));
check('шторка открыта', sheetState.modalOpen);
check('visible selected cosmetic uses one short shared transition into the fitting card',
  !sheetState.viewTransitionSupported || sheetState.sharedTransition);
check('shared transition releases its temporary name after finishing', sheetState.transitionNameAfterFinish === 'none');
check('в шторке показана карточка профиля', sheetState.hasHeroCard);
check('шторка показывает обе примерки', sheetState.trialChipCount === 2);
check('в шторке только одна золотая кнопка', sheetState.goldButtonCount === 1);
check('золотая кнопка покупает и применяет всё', /Купить и применить/.test(sheetState.actionText));

check('trial name glow is shown with its full name and price', sheetState.trialRows.some(text=>/Ореол имени/.test(text) && /Ледяная вязь/.test(text) && /440/.test(text)));
check('trial avatar frame is shown with its full name and price', sheetState.trialRows.some(text=>/Рамка аватара/.test(text) && /Оправа Бездны/.test(text) && /440/.test(text)));

const noFxTransition = await page.evaluate(async () => {
  CM();
  document.body.classList.add('no-fx');
  _looksOpenFittingSheet();
  await new Promise(resolve=>setTimeout(resolve,40));
  const shared=document.getElementById('modal').classList.contains('looks-fitting-shared');
  CM();
  document.body.classList.remove('no-fx');
  return shared;
});
check('no-fx opens the same fitting state without the shared transition', !noFxTransition);

await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
const reducedMotionTransition = await page.evaluate(async () => {
  _looksOpenFittingSheet();
  await new Promise(resolve=>setTimeout(resolve,40));
  const shared=document.getElementById('modal').classList.contains('looks-fitting-shared');
  CM();
  return shared;
});
check('prefers-reduced-motion opens the same fitting state without the shared transition', !reducedMotionTransition);
await page.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'no-preference'}]);

await page.evaluate(() => switchPage('profile'));
await page.waitForFunction(() => _activePage === 'profile');
check('dock panel hides outside appearance screen', !await page.$('.looks-fab'));

await browser.close();
if (failures.length) {
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
