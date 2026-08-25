import fs from 'fs';
import puppeteer from 'puppeteer';

const base=process.env.PREVIEW_URL||'http://localhost:8402';
const output=process.env.ECONOMY_V3_SCREENSHOT_DIR||'';
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
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width,height:844,deviceScaleFactor:1});
    await page.goto(`${base}/`,{waitUntil:'load'});
    await page.waitForFunction(()=>typeof swAuction==='function'&&typeof openExchangeZarnikiModal==='function');
    await page.evaluate(()=>_plSkip());
    await page.waitForFunction(()=>!document.getElementById('preloader'));
    await page.evaluate(()=>{switchPage('auction');swAuction('exch');scrollTo(0,0);});
    await page.waitForFunction(()=>document.querySelector('#mkt-exch')?.textContent.includes('У валют разные задачи'));
    const state=await page.evaluate(()=>({
      overflow:document.documentElement.scrollWidth-innerWidth,
      copy:document.querySelector('#mkt-exch')?.textContent||'',
      actionCount:document.querySelectorAll('#mkt-exch button').length,
      actionWidth:document.querySelector('#mkt-exch button')?.getBoundingClientRect().width||0,
      minFont:Math.min(...[...document.querySelectorAll('#mkt-exch *')]
        .filter(node=>node.textContent.trim())
        .map(node=>parseFloat(getComputedStyle(node).fontSize)||99)),
    }));
    check(state.overflow<=0,`${width}px: wallet policy page overflows`);
    check(state.copy.includes('Покупка и продажа Алмазов за Мору отключены'),`${width}px: blocked route is unclear`);
    check(state.copy.includes('испытания и сезонные рубежи'),`${width}px: Diamond source is missing`);
    check(!state.copy.includes('Доступен всегда')&&!state.copy.includes('спред'),`${width}px: stale exchange copy remains`);
    check(state.actionCount===0,`${width}px: obsolete exchange action remains`);
    check(state.minFont>=10,`${width}px: wallet policy text is below 10px`);
    if(output&&width===390)await page.screenshot({path:`${output}/wallet-roles-390.png`,fullPage:true});

    await page.evaluate(()=>openExchangeCurrencyModal('buy'));
    await page.waitForFunction(()=>document.querySelector('#mb')?.textContent.includes('Алмазы выдаются'));
    const modal=await page.evaluate(()=>({
      copy:document.querySelector('#mb')?.textContent||'',
      inputs:document.querySelectorAll('#mb input').length,
      overflow:document.querySelector('.modal')?.scrollWidth-document.querySelector('.modal')?.clientWidth,
    }));
    check(modal.inputs===0,`${width}px: retired Mora/Diamond input remains`);
    check(modal.copy.includes('Покупка и продажа Алмазов за Мору отключены'),`${width}px: modal hides the new rule`);
    check((modal.overflow||0)<=0,`${width}px: wallet role modal overflows`);
    await page.evaluate(()=>CM());

    await page.evaluate(()=>openExchangeZarnikiModal());
    await page.waitForFunction(()=>document.querySelector('#mb')?.textContent.includes('1 ✨ = 150 🪙'));
    const zarniki=await page.evaluate(()=>({
      buttons:document.querySelectorAll('#mb button[onclick*="doExchangeZarniki"]').length,
      copy:document.querySelector('#mb')?.textContent||'',
    }));
    check(zarniki.buttons===1,`${width}px: Zarniki modal exposes a forbidden route`);
    check(zarniki.copy.includes('Обмен назад невозможен'),`${width}px: irreversible exchange is unclear`);
    check(zarniki.copy.includes('Алмазы выдаются'),`${width}px: Zarniki modal does not explain Diamonds`);
    if(output&&width===390)await page.screenshot({path:`${output}/zarniki-to-mora-390.png`,fullPage:true});
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
console.log('OK economy v3 wallet: 320/390/430px, roles + allowed route verified');
