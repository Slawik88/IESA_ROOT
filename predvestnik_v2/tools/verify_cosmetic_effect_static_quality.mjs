// Декоративные эффекты должны останавливаться в спокойной, читаемой фазе.
// Отключение animation само по себе возвращает базовые CSS-значения и может
// случайно заморозить вспышку на максимальной яркости.
import puppeteer from 'puppeteer';

const failures=[];
function check(label, condition) {
  if (condition) console.log('OK:', label);
  else { console.error('FAIL:', label); failures.push(label); }
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
  await page.waitForFunction(()=>!document.getElementById('preloader'));

  const state=await page.evaluate(()=>{
    document.body.classList.add('no-fx');
    const inspect=(heroClass,fxClass)=>{
      const hero=document.createElement('article');
      hero.className=`hero ${heroClass}`;
      hero.style.cssText='position:fixed;left:-9999px;width:360px;height:340px';
      const fx=document.createElement('div');
      fx.className=`card-fx ${fxClass}`;
      hero.appendChild(fx);
      document.body.appendChild(hero);
      const style=getComputedStyle(fx), heroAfter=getComputedStyle(hero,'::after');
      const result={
        opacity:Number(style.opacity),transform:style.transform,animation:style.animationName,
        backgroundImage:style.backgroundImage,
        mask:style.maskImage||style.webkitMaskImage,
        heroAfterOpacity:Number(heroAfter.opacity),
        heroAfterMask:heroAfter.maskImage||heroAfter.webkitMaskImage,
      };
      hero.remove();
      return result;
    };
    return {
      nova:inspect('pbg-sunrise','cfx-nova'),
      artifact:inspect('pbg-artifact-matrix','cfx-artifact'),
      frostbite:inspect('pbg-snowpeak','cfx-frostbite'),
    };
  });

  console.log('Static cosmetic effects:',JSON.stringify(state));
  check('no-fx stops the Nova animation',state.nova.animation==='none');
  check('no-fx freezes Nova below content-washing brightness',state.nova.opacity>=.1&&state.nova.opacity<=.24);
  check('no-fx keeps a visible expanded glow instead of a solid central flash',state.nova.transform!=='none');
  check('no-fx keeps Artifact foil below content-washing brightness',state.artifact.opacity>=.12&&state.artifact.opacity<=.25);
  check('Artifact foil fades away from the identity header',state.artifact.mask&&state.artifact.mask!=='none');
  check('Artifact matrix scan is restrained and masked away from the identity header',state.artifact.heroAfterOpacity<=.35
    && state.artifact.heroAfterMask&&state.artifact.heroAfterMask!=='none');
  check('no-fx freezes Frostbite at a restrained edge-frost intensity',state.frostbite.opacity>=.3&&state.frostbite.opacity<=.55);
  check('Frostbite glow grows from the card corners instead of floating as clipped ovals',/at 0% 0%/.test(state.frostbite.backgroundImage)
    && /at 100% 100%/.test(state.frostbite.backgroundImage));

  const motion=await page.evaluate(()=>{
    document.body.classList.remove('no-fx');
    const peak=(fxClass,progress)=>{
      const hero=document.createElement('article');
      hero.className='hero';
      hero.style.cssText='position:fixed;left:-9999px;width:360px;height:340px';
      const fx=document.createElement('div');
      fx.className=`card-fx ${fxClass}`;
      hero.appendChild(fx);
      document.body.appendChild(hero);
      const animation=fx.getAnimations()[0];
      if(animation){ animation.pause(); animation.currentTime=Number(animation.effect.getTiming().duration)*progress; }
      const opacity=Number(getComputedStyle(fx).opacity);
      hero.remove();
      return opacity;
    };
    return {nova:peak('cfx-nova',.08),artifact:peak('cfx-artifact',.5),frostbite:peak('cfx-frostbite',.5)};
  });
  console.log('Animated effect peaks:',JSON.stringify(motion));
  check('Nova animation peak stays below a content-washing flash',motion.nova<=.5);
  check('Artifact foil animation peak stays subordinate to profile content',motion.artifact<=.5);
  check('Frostbite pulse stays a corner texture rather than a white overlay',motion.frostbite<=.68);
} finally {
  await browser.close();
}

if(failures.length){
  console.error('FAIL:',failures);
  process.exit(1);
}
console.log('ALL OK');
