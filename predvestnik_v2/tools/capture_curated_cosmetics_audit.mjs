import {mkdirSync} from 'fs';
import {resolve} from 'path';
import puppeteer from 'puppeteer';

const outputDir=resolve(process.env.OUTPUT_DIR||'/tmp/predvestnik-curated-cosmetics-audit');
mkdirSync(outputDir,{recursive:true});

const browser=await puppeteer.launch({headless:'new'});
const page=await browser.newPage();
await page.setViewport({width:390,height:844,deviceScaleFactor:2});
await page.goto('http://localhost:8402/',{waitUntil:'load'});
await new Promise(resolveWait=>setTimeout(resolveWait,1200));
await page.mouse.click(195,700);
await new Promise(resolveWait=>setTimeout(resolveWait,300));
await page.evaluate(()=>openLooksModal());
await page.waitForFunction(()=>document.querySelectorAll('.coll-card').length===10);
await page.evaluate(()=>document.body.classList.add('no-fx'));

const results=[];
for(const lineup of ['hanami','moon_lotus','ryujin_tide']){
  await page.evaluate(id=>_looksOpenCollection(id),lineup);
  await page.waitForFunction(()=>document.querySelectorAll('.looks-curated-card').length===2);
  await new Promise(resolveWait=>setTimeout(resolveWait,80));
  const section=await page.$('.looks-curated');
  const file=resolve(outputDir,`${lineup}-curated.png`);
  await section.screenshot({path:file});
  results.push(file);
  await page.evaluate(()=>_looksCloseCollection());
}

console.log(JSON.stringify(results,null,2));
await browser.close();
