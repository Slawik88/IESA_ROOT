// Узкий телефон не должен превращать сетку коллекций в горизонтальную прокрутку страницы.
import puppeteer from 'puppeteer';

const failures=[];
function check(name, condition){
  if(condition) console.log('OK:', name);
  else failures.push(name);
}

const browser=await puppeteer.launch({headless:'new'});
try {
  const page=await browser.newPage();
  await page.setViewport({width:320,height:740,deviceScaleFactor:1});
  await page.goto('http://localhost:8402/',{waitUntil:'load'});
  await page.waitForFunction(()=>typeof openLooksModal==='function');
  await page.mouse.click(160,650);
  await page.waitForFunction(()=>document.elementFromPoint(160,120)?.id!=='preloader');
  await page.evaluate(()=>openLooksModal());
  await page.waitForFunction(()=>!!document.querySelector('.coll-grid'));

  const state=await page.evaluate(()=>{
    const cards=[...document.querySelectorAll('.coll-card')];
    return {
      pageFits:document.documentElement.scrollWidth<=innerWidth,
      widths:cards.slice(0,2).map(card=>Math.round(card.getBoundingClientRect().width)),
      cardContentFits:cards.every(card=>{
        const rect=card.getBoundingClientRect();
        return rect.left>=-1 && rect.right<=innerWidth+1;
      }),
      vipVisibility:document.querySelector('.coll-card[data-lineup="frost"] .coll-visibility')?.textContent.trim() || '',
      typeScale:['.coll-name','.coll-status','.coll-price','.coll-visibility'].map(selector=>
        getComputedStyle(document.querySelector(selector)).fontSize),
      dockWidth:Math.round(document.querySelector('.looks-fab')?.getBoundingClientRect().width||0),
    };
  });
  check('320px appearance screen has no horizontal page overflow', state.pageFits);
  check('both collection cards stay inside the narrow screen', state.cardContentFits && state.widths.length===2 && state.widths.every(width=>width>=130));
  check('narrow collection card uses a compact but unambiguous VIP visibility label', state.vipVisibility==='👑 С VIP');
  check('collection metadata stays readable instead of using sub-caption text', state.typeScale.join('|')==='12px|9.5px|9px|8.5px');
  check('fitting-room dock remains a wide touch target on narrow screens', state.dockWidth>=280);
} finally {
  await browser.close();
}

if(failures.length){
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
