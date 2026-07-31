// Личные данные остаются главным слоем карточки: эффекты не перекрывают их,
// а на активных фонах у имени есть тёмная подложка с предсказуемым контрастом.
import fs from 'node:fs';
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
  await page.waitForFunction(()=>!!document.querySelector('#pg-looks .looks-fab'));
  await page.click('.looks-fab');
  await page.waitForFunction(()=>!!document.querySelector('#looks-fit-top .hero'));

  const state=await page.evaluate(()=>{
    const inspect=hero=>{
      hero.classList.add('pbg-starfall');
      let effect=hero.querySelector(':scope > .card-fx');
      if(!effect){
        effect=document.createElement('div');
        effect.className='card-fx cfx-stars';
        hero.prepend(effect);
      }
      const copy=hero.querySelector('.profile-copy');
      return {
        hasCopy:!!copy,
        copyZ:copy?getComputedStyle(copy).zIndex:'',
        underlay:copy?getComputedStyle(copy,'::before').backgroundImage:'',
        underlayContent:copy?getComputedStyle(copy,'::before').content:'',
        effectZ:getComputedStyle(effect).zIndex,
        headZ:getComputedStyle(hero.querySelector('.hero-head')).zIndex,
      };
    };
    return {
      profile:inspect(document.querySelector('#pro-main .hero')),
      fitting:inspect(document.querySelector('#looks-fit-top .hero')),
    };
  });

  for(const [name, card] of Object.entries(state)){
    check(`${name} card gives profile data a semantic copy layer`, card.hasCopy && card.copyZ==='3');
    check(`${name} card gives bright backgrounds a readable name underlay`, card.underlayContent==='""' && card.underlay.includes('linear-gradient'));
    check(`${name} card keeps the content above cosmetic particles`, Number(card.headZ)>Number(card.effectZ));
  }
  const publicSource=fs.readFileSync('FastAPI/static/app.06.js','utf8');
  check('public profile uses the same semantic copy layer', publicSource.includes('class="profile-copy"'));
} finally {
  await browser.close();
}

if(failures.length){
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
