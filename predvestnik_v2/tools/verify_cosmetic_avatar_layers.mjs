// Рамка остаётся близко к аватару, а гало получает отдельную круглую световую
// орбиту. Оно не дублирует скруглённую квадратную геометрию рамки.
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
  await page.waitForFunction(() => typeof _plSkip === 'function');
await page.evaluate(() => _plSkip());
await page.waitForFunction(() => !document.getElementById('preloader'));
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
        haloRadius:halo.borderRadius,
        haloBackground:halo.backgroundImage,
        haloShadow:halo.boxShadow,
        haloAnimation:halo.animationName,
      };
    };
    const frost=inspect('frame-icespikes halo-snowcrown');
    const mixed=inspect('frame-inferno halo-ice');
    document.body.classList.add('no-fx');
    const frostReduced={animation:getComputedStyle(document.querySelector('#looks-fit-top .ava'),'::after').animationName};
    document.body.classList.remove('no-fx');
    return {frost, mixed, frostReduced, artifact:inspect('frame-artifact-data halo-artifact-grid')};
  });

  check('avatar establishes a local layer stage for cosmetic pseudo-elements', state.frost.position==='relative');
  check('paired halo may extend beyond the avatar without being clipped', state.frost.overflow==='visible');
  check('paired halo does not use the same drop-shadow layer as the frame', state.frost.filter==='none');
  check('paired halo is a borderless circular light orbit after the close frame', state.frost.frameShadow!=='none'
    && state.frost.haloContent==='""' && parseFloat(state.frost.haloTop)<=-8
    && state.frost.haloBorder==='0px' && state.frost.haloRadius==='50%'
    && state.frost.haloBackground!=='none' && state.frost.haloShadow!=='none');
  check('mixed Inferno frame uses a restrained paired treatment instead of a heavy hard border', state.mixed.haloBorder==='0px'
    && state.mixed.haloRadius==='50%' && !state.mixed.frameShadow.includes('0px 0px 0px 2px'));
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
