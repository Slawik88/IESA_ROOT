// Рамка остаётся близко к аватару, а гало получает отдельный внешний контур.
// Это не даёт двум предметам визуально сливаться в одну случайную подсветку.
import puppeteer from 'puppeteer';

const failures=[];
function check(name, condition){
  if(condition) console.log('OK:', name);
  else failures.push(name);
}

const browser=await puppeteer.launch({headless:'new'});
try {
  const page=await browser.newPage();
  await page.setViewport({width:390,height:844,deviceScaleFactor:2});
  await page.goto('http://localhost:8402/',{waitUntil:'load'});
  await page.waitForFunction(()=>typeof openLooksModal==='function');
  await page.mouse.click(195,700);
  await page.waitForFunction(()=>document.elementFromPoint(195,120)?.id!=='preloader');
  await page.evaluate(()=>openLooksModal());
  await page.waitForFunction(()=>!!document.querySelector('.looks-fab'));
  await page.click('.looks-fab');
  await page.waitForFunction(()=>!!document.querySelector('#looks-fit-top .ava'));

  const state=await page.evaluate(()=>{
    const inspect=classes=>{
      const avatar=document.querySelector('#looks-fit-top .ava');
      avatar.className=`ava ${classes}`;
      const style=getComputedStyle(avatar), halo=getComputedStyle(avatar,'::after');
      return {
        position:style.position,
        overflow:style.overflow,
        filter:style.filter,
        frameShadow:style.boxShadow,
        haloContent:halo.content,
        haloTop:halo.top,
        haloBorder:halo.borderTopWidth,
        haloAnimation:halo.animationName,
      };
    };
    const frost=inspect('frame-icespikes halo-snowcrown');
    document.body.classList.add('no-fx');
    const frostReduced={animation:getComputedStyle(document.querySelector('#looks-fit-top .ava'),'::after').animationName};
    document.body.classList.remove('no-fx');
    return {frost, frostReduced, artifact:inspect('frame-artifact-data halo-artifact-grid')};
  });

  check('avatar establishes a local layer stage for cosmetic pseudo-elements', state.frost.position==='relative');
  check('paired halo may extend beyond the avatar without being clipped', state.frost.overflow==='visible');
  check('paired halo does not use the same drop-shadow layer as the frame', state.frost.filter==='none');
  check('paired halo has a separate outer ring after the close frame', state.frost.frameShadow!=='none' && state.frost.haloContent==='""' && parseFloat(state.frost.haloTop)<=-8 && state.frost.haloBorder!=='0px');
  check('outer halo animation also respects the no-effects preference', state.frostReduced.animation==='none');
  check('artifact frame and halo share the same local stage without clipping', state.artifact.position==='relative' && state.artifact.overflow==='visible' && state.artifact.haloContent==='""' && parseFloat(state.artifact.haloTop)<=-8);
} finally {
  await browser.close();
}

if(failures.length){
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
