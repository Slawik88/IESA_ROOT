import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import puppeteer from 'puppeteer';

const outputDir=process.env.AUDIT_OUTPUT||'/tmp/predvestnik-cross-surface-audit';
await mkdir(outputDir,{recursive:true});

const browser=await puppeteer.launch({headless:'new'});
const page=await browser.newPage();
await page.setViewport({width:390,height:844,deviceScaleFactor:2});
await page.goto(process.env.PREVIEW_URL||'http://localhost:8402/',{waitUntil:'load'});
await new Promise(resolve=>setTimeout(resolve,1200));
await page.mouse.click(195,700);
await new Promise(resolve=>setTimeout(resolve,350));
await page.evaluate(()=>openLooksModal());
await page.waitForFunction(()=>document.querySelectorAll('.coll-card').length===10);

const evidence=[];
async function capture(name,selector){
  await new Promise(resolve=>setTimeout(resolve,180));
  const node=await page.$(selector);
  if(!node) throw new Error(`Missing audit target: ${selector}`);
  const file=`${String(evidence.length+1).padStart(2,'0')}-${name}.png`;
  await node.screenshot({path:path.join(outputDir,file)});
  evidence.push({name,file,selector});
}

await page.evaluate(()=>{
  _looksMode='slots';
  _looksFilter='moon_lotus';
  renderLooks();
  document.querySelector('[data-cos="cos_avatar_frame_lotus_petal_orbit"]')?.scrollIntoView({block:'center'});
});
await capture('catalog-item','[data-cos="cos_avatar_frame_lotus_petal_orbit"]');

await page.evaluate(()=>{_looksMode='collections';_looksOpenCollection('moon_lotus');});
await capture('collection-detail-item','[data-cos="cos_avatar_frame_lotus_petal_orbit"]');
await capture('curated-composition','[data-curated-look="lotus_eclipse_garden"]');

await page.click('[data-curated-look="lotus_eclipse_garden"]');
await page.waitForFunction(()=>document.querySelectorAll('.fit-outfit-row.trial').length===6);
await capture('fitting-profile','#looks-fit-top .fit-player-card');
await capture('purchase-state','#modal .sheet');

await page.evaluate(()=>{
  CM();
  const cosmetics={
    name_glow:{css:'glow-lotus-pearl',name:'Жемчужная дорожка',lineup:'moon_lotus'},
    avatar_frame:{css:'frame-lotus-petal-orbit',name:'Орбита лепестков',lineup:'moon_lotus'},
    avatar_halo:{css:'halo-lotus-moonwake',name:'След полной луны',lineup:'moon_lotus'},
    profile_bg:{css:'pbg-lotus-eclipse',name:'Сад во время затмения',lineup:'moon_lotus'},
    card_fx:{css:'cfx-lotus-fireflies',name:'Светлячки над водой',lineup:'moon_lotus'},
    title:'Хранитель Лунного Лотоса',title_css:'title-moon-lotus',
    lineage:{id:'moon_lotus',source_slot:'avatar_frame'},
  };
  const profile={..._profileData,cosmetics};
  const originalFetch=window.fetch.bind(window);
  window.fetch=(input,init)=>String(input).endsWith('/profile/me')
    ?Promise.resolve(new Response(JSON.stringify(profile),{status:200,headers:{'Content-Type':'application/json'}}))
    :originalFetch(input,init);
  switchPage('profile');
  loadProfile();
});
await page.waitForFunction(()=>document.querySelector('#pro-main .hero.pbg-lotus-eclipse'));
await capture('equipped-profile','#pro-main .hero');

const geometry=await page.evaluate(()=>{
  const hero=document.querySelector('#pro-main .hero');
  const copy=hero?.querySelector('.profile-copy');
  const avatar=hero?.querySelector('.ava');
  const card=hero?.getBoundingClientRect();
  const copyRect=copy?.getBoundingClientRect();
  const avatarRect=avatar?.getBoundingClientRect();
  return {
    profileContained:!!card&&card.left>=0&&card.right<=innerWidth,
    copyContained:!!copyRect&&!!card&&copyRect.right<=card.right,
    avatarGap:copyRect&&avatarRect?Math.round(copyRect.left-avatarRect.right):0,
    title:copy?.textContent.replace(/\s+/g,' ').trim()||'',
  };
});
await writeFile(path.join(outputDir,'evidence.json'),JSON.stringify({evidence,geometry},null,2),'utf8');
console.log(JSON.stringify({outputDir,evidence,geometry},null,2));
await browser.close();
