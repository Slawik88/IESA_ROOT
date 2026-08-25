import puppeteer from 'puppeteer';

const sizes=[
  {width:320,height:780},
  {width:390,height:844},
  {width:430,height:932},
];
const failures=[];
const browser=await puppeteer.launch({headless:'new'});

const check=(ok,message)=>{if(!ok) failures.push(message);};

try{
  for(const size of sizes){
    const page=await browser.newPage();
    await page.setViewport({...size,deviceScaleFactor:1});
    await page.goto('http://localhost:8402/',{waitUntil:'load'});
    await page.waitForFunction(()=>typeof loadProfile==='function');
    await page.mouse.click(size.width/2,Math.min(size.height-70,700));
    await page.waitForFunction(()=>document.elementFromPoint(innerWidth/2,120)?.id!=='preloader');
    await page.evaluate(()=>{switchPage('profile');loadProfile();scrollTo(0,0);});
    await page.waitForFunction(()=>!!document.querySelector('#pro-main .profile-showcase-card')&&document.querySelectorAll('.profile-fold').length>=3);
    await new Promise(resolve=>setTimeout(resolve,350));

    const state=await page.evaluate(()=>{
      const rect=s=>{const n=document.querySelector(s);const r=n?.getBoundingClientRect();return r?{top:r.top,left:r.left,right:r.right,bottom:r.bottom,width:r.width,height:r.height}:null;};
      const bar=document.querySelector('#curr-bar')?.getBoundingClientRect();
      const currencies=[...document.querySelectorAll('#curr-bar .cb-item')]
        .filter(n=>getComputedStyle(n).display!=='none')
        .map(n=>{const r=n.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width};});
      const folds=[...document.querySelectorAll('.profile-fold')];
      return {
        pageWidth:document.documentElement.scrollWidth,
        pageHeight:document.documentElement.scrollHeight,
        entry:rect('[data-open-looks="profile-showcase"]'), hero:rect('#pro-main .profile-showcase-card'), quick:rect('.qa-row'), promo:rect('.profile-card-actions button[onclick="openPromoModal()"]'),
        entryTools:[...document.querySelectorAll('[data-open-looks="profile-showcase"]')].map(n=>{const r=n.getBoundingClientRect();return {w:r.width,h:r.height};}),
        quickItems:[...document.querySelectorAll('.qa')].map(n=>{const r=n.getBoundingClientRect();return {w:r.width,h:r.height};}),
        folds:folds.map(n=>({open:n.open,summaryH:n.querySelector('summary')?.getBoundingClientRect().height||0})),
        bar:bar?{left:bar.left,right:bar.right}:null,currencies,
        hasDuplicateAppearance:document.querySelectorAll('[onclick="openLooksModal()"]').length,
      };
    });

    const tag=`${size.width}px`;
    check(state.pageWidth===size.width,`${tag}: horizontal page overflow (${state.pageWidth})`);
    check(state.pageHeight<=1540,`${tag}: overview remains too long (${state.pageHeight}px)`);
    check(state.entry&&state.entry.top<size.height-160&&state.entry.bottom<=size.height-120,`${tag}: appearance entry is not safely reachable in the first screen`);
    check(state.entryTools.length===1&&state.entryTools.every(x=>x.h>=268),`${tag}: visual appearance stage lost its large tap target`);
    check(state.quickItems.every(x=>x.h>=56),`${tag}: quick action target below 56px`);
    check(state.promo&&state.promo.width<size.width*.55,`${tag}: promo action is still oversized`);
    check(state.folds.length>=5&&state.folds.every(x=>!x.open&&x.summaryH>=48),`${tag}: secondary sections are not compact or tappable`);
    check(state.hasDuplicateAppearance===1,`${tag}: appearance entry is duplicated (${state.hasDuplicateAppearance})`);
    check(state.currencies.every(x=>x.left>=state.bar.left-1&&x.right<=state.bar.right+1),`${tag}: a currency chip escapes the header`);

    await page.click('#pro-marriage-card summary');
    const marriage=await page.$eval('#pro-marriage-card .profile-fold',n=>({open:n.open,height:n.getBoundingClientRect().height,summary:n.querySelector('summary').getBoundingClientRect().height}));
    check(marriage.open&&marriage.height>marriage.summary+100,`${tag}: marriage disclosure does not reveal its controls`);
    await page.close();
  }
}finally{
  await browser.close();
}

if(failures.length){
  console.error(failures.map(x=>`FAIL ${x}`).join('\n'));
  process.exit(1);
}
console.log(`OK homepage layout: ${sizes.map(x=>x.width).join('/')}px, compact overview and disclosures verified`);
