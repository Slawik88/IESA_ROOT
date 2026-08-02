import puppeteer from 'puppeteer';

const failures=[];
function check(name,condition){if(condition)console.log('OK:',name);else failures.push(name);}

const browser=await puppeteer.launch({headless:'new'});
const page=await browser.newPage();
await page.setViewport({width:390,height:844,deviceScaleFactor:2});
await page.goto('http://localhost:8402/',{waitUntil:'load'});
await new Promise(resolve=>setTimeout(resolve,1200));
await page.mouse.click(195,700);
await new Promise(resolve=>setTimeout(resolve,350));
await page.evaluate(()=>openLooksModal());
await page.waitForFunction(()=>document.querySelectorAll('.coll-card').length===10);

await page.evaluate(()=>{_looksMode='slots';_looksFilter='moon_lotus';renderLooks();});
const catalog=await page.evaluate(()=>{
  const card=document.querySelector('[data-cos="cos_avatar_frame_lotus_petal_orbit"]');
  const avatar=card?.querySelector('.lc-ava');
  return {text:card?.textContent.replace(/\s+/g,' ').trim()||'',css:avatar?.className||'',avatarPosition:avatar?getComputedStyle(avatar).position:''};
});
check('catalog names and prices the audited item transparently',catalog.text.includes('Орбита лепестков')&&catalog.text.includes('1500✨'));
check('catalog swatch applies the real frame class to a local positioned avatar',catalog.css.includes('frame-lotus-petal-orbit')&&catalog.avatarPosition==='relative');

await page.evaluate(()=>{_looksMode='collections';_looksOpenCollection('moon_lotus');});
const detail=await page.evaluate(()=>{
  const card=document.querySelector('[data-cos="cos_avatar_frame_lotus_petal_orbit"]');
  const curated=document.querySelector('[data-curated-look="lotus_eclipse_garden"]');
  return {
    text:card?.textContent.replace(/\s+/g,' ').trim()||'',
    css:card?.querySelector('.lc-ava')?.className||'',
    curatedText:curated?.textContent.replace(/\s+/g,' ').trim()||'',
    curatedBgSize:curated?getComputedStyle(curated.querySelector('.looks-curated-preview')).backgroundSize:'',
    noOverflow:document.documentElement.scrollWidth<=document.documentElement.clientWidth,
  };
});
check('collection detail preserves the same item identity and price',detail.text===catalog.text&&detail.css===catalog.css);
check('curated state shows the full look and exact missing price',detail.curatedText.includes('Сад затмения')&&detail.curatedText.includes('9000✨'));
check('compact eclipse preview uses its protected moon scale without page overflow',detail.curatedBgSize.startsWith('36px 36px')&&detail.noOverflow);

await page.click('[data-curated-look="lotus_eclipse_garden"]');
await page.waitForFunction(()=>document.querySelectorAll('.fit-outfit-row.trial').length===6);
const fitting=await page.evaluate(()=>({
  avatarCss:document.querySelector('#fit-ava')?.className||'',
  frameRow:[...document.querySelectorAll('.fit-outfit-row.trial')].find(row=>row.textContent.includes('Орбита лепестков'))?.textContent.replace(/\s+/g,' ').trim()||'',
  action:document.querySelector('#mf .btn:last-child')?.textContent.trim()||'',
  profileContained:document.querySelector('#looks-fit-top .hero')?.getBoundingClientRect().right<=innerWidth,
}));
check('fitting profile applies the same frame class',fitting.avatarCss.includes('frame-lotus-petal-orbit'));
check('purchase state keeps the same item name, exact item price, and exact total gap',fitting.frameRow.includes('1500✨')&&fitting.action.includes('7750✨'));
check('complete premium look remains contained in the mobile fitting room',fitting.profileContained);

await page.evaluate(()=>{
  CM();
  const cosmetics={
    name_glow:{css:'glow-lotus-pearl',name:'Жемчужная дорожка',lineup:'moon_lotus'},
    avatar_frame:{css:'frame-lotus-petal-orbit',name:'Орбита лепестков',lineup:'moon_lotus'},
    avatar_halo:{css:'halo-lotus-moonwake',name:'След полной луны',lineup:'moon_lotus'},
    profile_bg:{css:'pbg-lotus-eclipse',name:'Сад во время затмения',lineup:'moon_lotus'},
    card_fx:{css:'cfx-lotus-fireflies',name:'Светлячки над водой',lineup:'moon_lotus'},
    title:'Хранитель Лунного Лотоса',title_css:'title-moon-lotus',lineage:{id:'moon_lotus',source_slot:'avatar_frame'},
  };
  const profile={..._profileData,cosmetics};
  const originalFetch=window.fetch.bind(window);
  window.fetch=(input,init)=>String(input).endsWith('/profile/me')
    ?Promise.resolve(new Response(JSON.stringify(profile),{status:200,headers:{'Content-Type':'application/json'}}))
    :originalFetch(input,init);
  switchPage('profile');loadProfile();
});
await page.waitForFunction(()=>document.querySelector('#pro-main .hero.pbg-lotus-eclipse'));
const profile=await page.evaluate(()=>{
  const hero=document.querySelector('#pro-main .hero'),avatar=hero.querySelector('.ava'),copy=hero.querySelector('.profile-copy');
  const a=avatar.getBoundingClientRect(),c=copy.getBoundingClientRect(),h=hero.getBoundingClientRect();
  return {avatarCss:avatar.className,text:copy.textContent.replace(/\s+/g,' ').trim(),gap:Math.round(c.left-a.right),contained:c.right<=h.right};
});
check('equipped profile preserves the same frame and full title',profile.avatarCss.includes('frame-lotus-petal-orbit')&&profile.text.includes('Хранитель Лунного Лотоса'));
check('equipped profile keeps avatar effects clear of readable copy',profile.gap>=20&&profile.contained);

await browser.close();
if(failures.length){console.error('FAIL:',failures);process.exit(1);}
console.log('ALL OK');
