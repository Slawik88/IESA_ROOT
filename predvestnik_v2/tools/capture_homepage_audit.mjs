import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer';

const phase=process.argv[2]||'before';
if(!/^(before|after)$/.test(phase)) throw new Error('phase must be before or after');
const out=path.resolve(`docs/audits/2026-08-11-homepage/${phase}`);
fs.mkdirSync(out,{recursive:true});

const sizes=[
  {width:320,height:780},
  {width:390,height:844},
  {width:430,height:932},
];
const evidence=[];
const browser=await puppeteer.launch({headless:'new'});
try{
  for(const size of sizes){
    const page=await browser.newPage();
    const consoleErrors=[];
    page.on('console',message=>{ if(message.type()==='error') consoleErrors.push(message.text()); });
    await page.setViewport({...size,deviceScaleFactor:2});
    await page.goto('http://localhost:8402/',{waitUntil:'load'});
    await page.waitForFunction(()=>typeof loadProfile==='function');
    await page.mouse.click(size.width/2,Math.min(size.height-70,700));
    await page.waitForFunction(()=>document.elementFromPoint(innerWidth/2,120)?.id!=='preloader');
    await page.evaluate(()=>{ switchPage('profile'); loadProfile(); window.scrollTo(0,0); });
    await page.waitForFunction(()=>!!document.querySelector('#pro-main .hero'));
    await new Promise(resolve=>setTimeout(resolve,400));
    const metrics=await page.evaluate(()=>{
      const box=selector=>{
        const node=document.querySelector(selector); if(!node)return null;
        const r=node.getBoundingClientRect(); return {top:r.top,left:r.left,width:r.width,height:r.height,bottom:r.bottom,right:r.right};
      };
      const touchTargets=[...document.querySelectorAll('#pg-profile button, #pg-profile [onclick], #pg-profile summary')]
        .filter(node=>{const r=node.getBoundingClientRect();return r.width>0&&r.height>0&&node.offsetParent!==null;})
        .map(node=>{const r=node.getBoundingClientRect();return {label:(node.textContent||node.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim().slice(0,80),width:r.width,height:r.height};});
      return {
        viewport:{width:innerWidth,height:innerHeight},
        page:{scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,scrollHeight:document.documentElement.scrollHeight},
        header:box('#app-header'),tabs:box('#pg-profile > .tabs'),entry:box('.profile-entry-bar'),hero:box('#pro-main .hero'),
        quickActions:box('.qa-row'),promo:box('.profile-promo-link'),leaderboard:box('.t3-card'),nav:box('.nav'),
        tabsOverflow:(()=>{const n=document.querySelector('#pg-profile > .tabs');return n?{scrollWidth:n.scrollWidth,clientWidth:n.clientWidth}:null})(),
        smallTargets:touchTargets.filter(target=>target.width<44||target.height<44),
      };
    });
    const file=`${phase}-${size.width}.png`;
    await page.screenshot({path:path.join(out,file),fullPage:true});
    evidence.push({...size,file,metrics,consoleErrors});
    await page.close();
  }
}finally{
  await browser.close();
}
fs.writeFileSync(path.join(out,'evidence.json'),JSON.stringify(evidence,null,2));
console.log(JSON.stringify(evidence,null,2));
