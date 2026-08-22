import fs from 'fs';
import puppeteer from 'puppeteer';

const base=process.env.PREVIEW_URL||'http://localhost:8402';
const output=process.env.SHOP_V3_SCREENSHOT_DIR||'';
if(output)fs.mkdirSync(output,{recursive:true});
const browser=await puppeteer.launch({
  headless:'new',
  executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||undefined,
  args:['--no-sandbox'],
});
const failures=[];
const check=(condition,message)=>{if(!condition)failures.push(message);};

try{
  for(const width of [320,390,430]){
    const page=await browser.newPage();
    const errors=[];
    const shopRequests=[];
    page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{
      if(request.url().endsWith('/shop/buy')) shopRequests.push({
        headers:request.headers(),
        body:request.postData()||'',
      });
      if(request.url().includes('/shop/checkout-quote')) shopRequests.push({forbiddenQuote:true});
    });
    await page.setViewport({width,height:844,deviceScaleFactor:1});
    await page.goto(`${base}/`,{waitUntil:'load'});
    await page.waitForFunction(()=>typeof goTo==='function'&&typeof _shopBuy==='function');
    await page.evaluate(()=>_plSkip());
    await page.waitForFunction(()=>!document.getElementById('preloader'));
    await page.evaluate(()=>goTo('market','goods'));
    await page.waitForFunction(()=>document.querySelectorAll('#mkt-shop .shop-row').length>=4);

    const state=await page.evaluate(()=>{
      const root=document.querySelector('#mkt-shop');
      const buttons=[...root.querySelectorAll('.shop-row button')];
      return {
        overflow:document.documentElement.scrollWidth-innerWidth,
        copy:root.textContent||'',
        minFont:Math.min(...[...root.querySelectorAll('*')]
          .filter(node=>node.textContent.trim())
          .map(node=>parseFloat(getComputedStyle(node).fontSize)||99)),
        maxButtonWidth:Math.max(...buttons.map(button=>button.getBoundingClientRect().width)),
        maxButtonHeight:Math.max(...buttons.map(button=>button.getBoundingClientRect().height)),
      };
    });
    check(state.overflow<=0,`${width}px: shop page overflows`);
    check(state.minFont>=10,`${width}px: shop text is below 10px`);
    check(state.maxButtonWidth<width*.5,`${width}px: purchase action is oversized`);
    check(state.maxButtonHeight<=52,`${width}px: purchase action is too tall`);
    check(!/доплат|покрыть недостаток|быстрой покупки/i.test(state.copy),`${width}px: forbidden premium shortfall copy remains`);
    if(output&&width===390)await page.screenshot({path:`${output}/shop-v3-390.png`,fullPage:true});

    await page.evaluate(()=>_shopBuy('food_apple',1,null));
    await page.waitForFunction(()=>document.querySelector('.toast')?.textContent.includes('Покупка завершена')||document.querySelector('.toast')?.textContent.includes('Куплено'),{timeout:3000}).catch(()=>{});
    check(shopRequests.length===1,`${width}px: one purchase created ${shopRequests.length} requests`);
    const request=shopRequests[0]||{};
    check(Boolean(request.headers?.['idempotency-key']),`${width}px: purchase has no Idempotency-Key`);
    check(!request.body?.includes('cover_with_zarniki'),`${width}px: legacy premium-cover flag remains in request`);
    check(!shopRequests.some(item=>item.forbiddenQuote),`${width}px: obsolete checkout quote was requested`);
    check(errors.length===0,`${width}px: page errors: ${errors.join('; ')}`);
    await page.close();
  }
}finally{
  await browser.close();
}

if(failures.length){
  console.error(failures.map(item=>`FAIL ${item}`).join('\n'));
  process.exit(1);
}
console.log('OK shop v3: 320/390/430px + compact actions + idempotent purchase request');
