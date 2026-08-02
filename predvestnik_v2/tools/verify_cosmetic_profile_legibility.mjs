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
  await page.waitForFunction(()=>document.body.querySelector(':scope > #looks-dock .looks-fab'));
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
      const avatar=hero.querySelector('.ava');
      avatar.classList.add('frame-inferno','halo-ice');
      const head=hero.querySelector('.hero-head');
      const copyRect=copy?.getBoundingClientRect();
      const avatarRect=avatar?.getBoundingClientRect();
      const measuredGap=copyRect&&avatarRect?copyRect.left-avatarRect.right:0;
      return {
        hasCopy:!!copy,
        copyZ:copy?getComputedStyle(copy).zIndex:'',
        underlay:copy?getComputedStyle(copy,'::before').backgroundImage:'',
        underlayContent:copy?getComputedStyle(copy,'::before').content:'',
        underlayFilter:copy?getComputedStyle(copy,'::before').filter:'',
        cardBorder:getComputedStyle(hero).borderTopColor,
        effectZ:getComputedStyle(effect).zIndex,
        headZ:getComputedStyle(head).zIndex,
        copyUnderlayLeft:copy?getComputedStyle(copy,'::before').left:'',
        avatarToCopyGap:measuredGap||parseFloat(getComputedStyle(head).columnGap)||0,
        hasLineage:head?.classList.contains('lineage-link')||false,
        lineageWash:head?getComputedStyle(head,'::before').backgroundImage:'',
      };
    };
    return {
      profile:inspect(document.querySelector('#pro-main .hero')),
      fitting:inspect(document.querySelector('#looks-fit-top .hero')),
    };
  });

  console.log('Profile-layer geometry:', JSON.stringify(state));

  for(const [name, card] of Object.entries(state)){
    check(`${name} card gives profile data a semantic copy layer`, card.hasCopy && card.copyZ==='3');
    check(`${name} card gives bright backgrounds a readable name underlay`, card.underlayContent==='""' && card.underlay.includes('linear-gradient'));
    check(`${name} text underlay feathers into the card instead of forming a hard box`, card.underlayFilter.includes('blur'));
    check(`${name} cosmetic card uses a restrained neutral edge`, card.cardBorder==='rgba(255, 255, 255, 0.12)');
    check(`${name} card keeps the content above cosmetic particles`, Number(card.headZ)>Number(card.effectZ));
    check(`${name} card keeps avatar glow out of the text underlay`, parseFloat(card.copyUnderlayLeft)>=0 && card.avatarToCopyGap>=20);
  }
  check('main profile links the avatar to the server-declared cosmetic lineage', state.profile.hasLineage
    && state.profile.lineageWash.includes('radial-gradient'));
  const publicSource=fs.readFileSync('FastAPI/static/app.06.js','utf8');
  check('public profile uses the same semantic copy layer', publicSource.includes('class="profile-copy"'));
  check('public profile uses the shared glow-safe profile row', publicSource.includes('class="profile-copy-row${lineageStyle')
    && !publicSource.includes('flex:none;overflow:hidden'));
  check('public profile consumes the same lineage metadata without a cosmetic-id map', publicSource.includes('_looksLineageStyle(co)')
    && publicSource.includes("lineage-link"));

  await page.setViewport({width:320,height:780,deviceScaleFactor:2});
  const narrow=await page.evaluate(()=>{
    const head=document.querySelector('#looks-fit-top .hero-head');
    const avatar=head?.querySelector('.ava'), copy=head?.querySelector('.profile-copy');
    if(!avatar||!copy) return {gap:0,overflow:true};
    const a=avatar.getBoundingClientRect(), c=copy.getBoundingClientRect();
    return {gap:c.left-a.right,overflow:head.scrollWidth>head.clientWidth};
  });
  check('narrow fitting card preserves a clean avatar/text gap without overflow', narrow.gap>=20 && !narrow.overflow);
} finally {
  await browser.close();
}

if(failures.length){
  console.error('FAIL:', failures);
  process.exit(1);
}
console.log('ALL OK');
