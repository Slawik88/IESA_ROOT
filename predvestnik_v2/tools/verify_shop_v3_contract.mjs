import puppeteer from 'puppeteer';

const base=process.env.PREVIEW_URL||'http://localhost:8402';
const browser=await puppeteer.launch({headless:'new',executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||undefined,args:['--no-sandbox']});
const failures=[];
try {
  for(const width of [320,390,430]){
    const page=await browser.newPage();
    const mutations=[];
    page.on('request',request=>{
      if(request.method()!=='GET' && /\/shop\/buy|\/daily-deal\/buy/.test(request.url())) mutations.push(request.url());
    });
    await page.setViewport({width,height:844,deviceScaleFactor:1});
    await page.goto(`${base}/`,{waitUntil:'load'});
    await page.waitForFunction(()=>typeof goTo==='function');
    await page.evaluate(()=>_plSkip());
    await page.evaluate(()=>goTo('market','goods'));
    await page.waitForFunction(()=>/Мастерская обновляется/.test(document.querySelector('#mkt-shop')?.textContent||''));
    const state=await page.evaluate(()=>({
      copy:document.querySelector('#mkt-shop')?.textContent||'',
      buyButtons:document.querySelectorAll('#mkt-shop .shop-row button').length,
      overflow:document.documentElement.scrollWidth-innerWidth,
    }));
    if(!/старые расходники больше не продаются/i.test(state.copy)) failures.push(`${width}px: retirement reason is missing`);
    if(state.buyButtons!==0) failures.push(`${width}px: purchase buttons remain`);
    if(state.overflow>1) failures.push(`${width}px: horizontal overflow ${state.overflow}`);
    if(mutations.length) failures.push(`${width}px: retired shop sent ${mutations.length} mutation(s)`);
    await page.close();
  }
} finally { await browser.close(); }
if(failures.length){console.error(failures.map(x=>`FAIL ${x}`).join('\n'));process.exit(1);}
console.log('OK shop v3: retired catalog is truthful, compact and sends no purchase mutations');
