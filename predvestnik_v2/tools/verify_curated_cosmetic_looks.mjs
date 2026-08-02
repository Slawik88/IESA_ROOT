import puppeteer from 'puppeteer';

const failures=[];
function check(name, condition){
  if(condition) console.log('OK:', name);
  else failures.push(name);
}

const browser=await puppeteer.launch({headless:'new'});
const page=await browser.newPage();
await page.setViewport({width:390,height:844,deviceScaleFactor:2});
await page.goto('http://localhost:8402/',{waitUntil:'load'});
await new Promise(resolve=>setTimeout(resolve,1200));
await page.mouse.click(195,700);
await new Promise(resolve=>setTimeout(resolve,350));
await page.evaluate(()=>openLooksModal());
await page.waitForFunction(()=>document.querySelectorAll('.coll-card').length===10);
await page.evaluate(()=>document.querySelector('.coll-card[data-lineup="hanami"]')?.scrollIntoView({block:'center'}));
await page.click('.coll-card[data-lineup="hanami"]');
await new Promise(resolve=>setTimeout(resolve,200));

const detail=await page.evaluate(()=>{
  const cards=[...document.querySelectorAll('.looks-curated-card')];
  const first=cards[0], preview=first?.querySelector('.looks-curated-preview');
  const row=document.querySelector('.looks-curated-row');
  return {
    cardCount:cards.length,
    ids:cards.map(card=>card.dataset.curatedLook),
    firstText:first?.textContent.replace(/\s+/g,' ').trim()||'',
    firstWidth:first?.getBoundingClientRect().width||0,
    firstMinHeight:first?.getBoundingClientRect().height||0,
    previewHasRealLayers:!!(preview?.className.includes('pbg-')
      && preview.querySelector('.card-fx[class*="cfx-"]')
      && preview.querySelector('.ava[class*="frame-"][class*="halo-"]')
      && preview.querySelector('.pname[class*="glow-"]')
      && preview.querySelector('.ptitle[class*="title-"]')),
    rowScrollable:!!row&&row.scrollWidth>row.clientWidth,
    noPageOverflow:document.documentElement.scrollWidth<=document.documentElement.clientWidth,
  };
});
check('Hanami detail exposes exactly two server-backed curated looks',
  detail.cardCount===2&&detail.ids.includes('hanami_washi_dawn')&&detail.ids.includes('hanami_lantern_rain'));
check('curated card previews one real cosmetic from every visual layer', detail.previewHasRealLayers);
check('curated card names the mood and transparent missing-set price',
  detail.firstText.includes('Рассвет на васи')&&detail.firstText.includes('Тихий сад')&&detail.firstText.includes('0/6')&&detail.firstText.includes('3780✨'));
check('curated looks are readable cards rather than tiny pills', detail.firstWidth>=208&&detail.firstMinHeight>=200);
check('two curated looks use contained horizontal discovery without page overflow', detail.rowScrollable&&detail.noPageOverflow);

await page.click('.looks-curated-card[data-curated-look="hanami_washi_dawn"]');
await new Promise(resolve=>setTimeout(resolve,450));
const fitting=await page.evaluate(()=>({
  modalOpen:document.getElementById('modal').open,
  trialSlots:Object.keys(_looksTrial).sort(),
  trialRows:document.querySelectorAll('.fit-outfit-row.trial').length,
  collectionText:document.querySelector('.fit-collection-card')?.textContent.replace(/\s+/g,' ').trim()||'',
  actionText:document.querySelector('#mf .btn:last-child')?.textContent.trim()||'',
}));
check('curated look opens as a complete six-slot fitting state',
  fitting.modalOpen&&fitting.trialRows===6&&fitting.trialSlots.length===6);
check('fitting room keeps the real collection name and total visible',
  fitting.collectionText.includes('Ханами')&&fitting.collectionText.includes('3780✨'));
check('purchase action keeps the exact affordability gap visible',
  fitting.actionText.includes('Не хватает 2530✨'));

await page.evaluate(()=>{CM();document.body.classList.add('no-fx');});
const noFx=await page.evaluate(()=>{
  const preview=document.querySelector('.looks-curated-preview');
  const nodes=preview?[preview,...preview.querySelectorAll('*')]:[];
  return nodes.every(node=>getComputedStyle(node).animationName==='none');
});
check('no-fx freezes every curated-preview element', noFx);
await page.evaluate(()=>document.body.classList.remove('no-fx'));

await page.setViewport({width:320,height:720,deviceScaleFactor:2});
await new Promise(resolve=>setTimeout(resolve,120));
const narrow=await page.evaluate(()=>({
  noPageOverflow:document.documentElement.scrollWidth<=document.documentElement.clientWidth,
  cardContained:[...document.querySelectorAll('.looks-curated-card')].every(card=>card.getBoundingClientRect().width<=document.querySelector('.looks-curated-row').scrollWidth),
}));
check('320px detail keeps curated cards inside the page scroller', narrow.noPageOverflow&&narrow.cardContained);

await browser.close();
if(failures.length){console.error('FAIL:',failures);process.exit(1);}
console.log('ALL OK');
