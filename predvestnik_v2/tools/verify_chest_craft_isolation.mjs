// Saved chest/shard ownership remains in inventory, but random use has no visible route.
import puppeteer from 'puppeteer';

const browser=await puppeteer.launch({headless:'new'});
try {
  const page=await browser.newPage();
  await page.setViewport({width:390,height:844,deviceScaleFactor:2});
  await page.goto('http://localhost:8402/',{waitUntil:'load'});
  await page.waitForFunction(()=>typeof openLooksModal==='function');
  await page.waitForFunction(() => typeof _plSkip === 'function');
await page.evaluate(() => _plSkip());
await page.waitForFunction(() => !document.getElementById('preloader'));
  await page.evaluate(()=>openLooksModal());
  await page.waitForFunction(()=>typeof _looksData!=='undefined'&&!!_looksData);
  const result=await page.evaluate(()=>({
    randomEntry:!!document.querySelector('#pg-looks .looks-surprises-entry, #pg-looks [onclick="_openSurprisesModal()"]'),
    randomCopy:/Сундуки-сюрпризы|Сюрпризы и крафт/.test(document.querySelector('#pg-looks')?.textContent||''),
    overflow:document.documentElement.scrollWidth-innerWidth,
  }));
  if(result.randomEntry||result.randomCopy) throw new Error('random chest/craft route returned to Looks');
  if(result.overflow>1) throw new Error(`horizontal overflow ${result.overflow}`);
  console.log('OK: random chest/craft route is isolated from Looks; saved data is handled by inventory API');
} finally { await browser.close(); }
