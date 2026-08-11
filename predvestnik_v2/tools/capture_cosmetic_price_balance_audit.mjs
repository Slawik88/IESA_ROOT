import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer';

const out=path.resolve('docs/audits/2026-08-11-cosmetics-pricing');
fs.mkdirSync(out,{recursive:true});

const browser=await puppeteer.launch({headless:'new'});
try{
  const page=await browser.newPage();
  await page.setViewport({width:390,height:844,deviceScaleFactor:2});
  await page.goto('http://localhost:8402/',{waitUntil:'load'});
  await page.waitForFunction(()=>typeof openLooksModal==='function');
  await page.mouse.click(195,700);
  await page.waitForFunction(()=>document.elementFromPoint(195,120)?.id!=='preloader');
  await page.evaluate(()=>openLooksModal());
  await page.waitForFunction(()=>document.querySelectorAll('.coll-card').length===10);
  await page.screenshot({path:path.join(out,'01-collections-price-ranges-390.png'),fullPage:true});

  await page.evaluate(()=>_looksOpenCollection('moon_lotus'));
  await page.waitForFunction(()=>!!document.querySelector('.coll-detail-head'));
  await page.screenshot({path:path.join(out,'02-moon-lotus-detail-390.png'),fullPage:true});

  await page.click('.looks-curated-card[data-curated-look="lotus_eclipse_garden"]');
  await page.waitForFunction(()=>document.querySelectorAll('.fit-outfit-row.trial').length===6);
  await page.screenshot({path:path.join(out,'03-moon-lotus-fitting-390.png')});

  await page.setViewport({width:320,height:780,deviceScaleFactor:2});
  await page.screenshot({path:path.join(out,'04-moon-lotus-fitting-320.png')});
}finally{
  await browser.close();
}

console.log(out);
