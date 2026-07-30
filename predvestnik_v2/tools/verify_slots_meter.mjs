// Проверка мини-измерителя на заголовке секции: есть N делений = N предметов слота,
// заполненные (owned) делений столько же, сколько owned=true в данных.
import puppeteer from 'puppeteer';
const FAIL=[];
function check(name,cond){ if(!cond) FAIL.push(name); else console.log('OK:',name); }
const browser=await puppeteer.launch({headless:'new'});
const page=await browser.newPage();
await page.setViewport({width:390,height:844,deviceScaleFactor:2});
await page.goto('http://localhost:8402/',{waitUntil:'load'});
await new Promise(r=>setTimeout(r,1500));
await page.mouse.click(195,700);
await new Promise(r=>setTimeout(r,500));
await page.evaluate(()=>openLooksModal());
await new Promise(r=>setTimeout(r,500));
await page.click('[data-mode="slots"]');
await new Promise(r=>setTimeout(r,300));
const info=await page.evaluate(()=>{
  const total=(_looksData.slots.name_glow||[]).length;
  const owned=(_looksData.slots.name_glow||[]).filter(it=>it.owned).length;
  const sec=document.getElementById('looks-sec-name_glow');
  const notches=sec?sec.querySelectorAll('.mini-notch').length:0;
  const onNotches=sec?sec.querySelectorAll('.mini-notch.on').length:0;
  const numTxt=sec?(sec.querySelector('.sec-num')||{}).textContent:null;
  return {total,owned,notches,onNotches,numTxt};
});
check('число делений совпадает с числом предметов слота', info.notches===info.total);
check('число горящих делений совпадает с owned', info.onNotches===info.owned);
check('текстовая подпись показывает X/Y', info.numTxt===`${info.owned}/${info.total}`);
await browser.close();
if(FAIL.length){console.error('FAIL:',FAIL);process.exit(1);}
console.log('ALL OK');
