import fs from 'fs';
import puppeteer from 'puppeteer';

const base=process.env.PREVIEW_URL||'http://localhost:8402';
const output=process.env.RECON_SCREENSHOT_DIR||'';
if(output) fs.mkdirSync(output,{recursive:true});
const browser=await puppeteer.launch({
  headless:'new',
  executablePath:process.env.PUPPETEER_EXECUTABLE_PATH||undefined,
  args:['--no-sandbox'],
});
const failures=[];
const check=(condition,message)=>{if(!condition) failures.push(message);};

async function reset(){
  await fetch(`${base}/__reconstruction/reset`,{
    method:'POST',headers:{'content-type':'application/json'},body:'{}',
  });
}

try{
  for(const width of [320,390,430,1024]){
    await reset();
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width,height:width<600?844:900,deviceScaleFactor:1});
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.waitForSelector('.squad-member');
    await page.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:3000});
    const metrics=await page.evaluate(()=>{
      document.body.classList.add('no-fx');
      return {
      pageWidth:document.documentElement.scrollWidth,
      viewport:innerWidth,
      runes:[...document.querySelectorAll('.strike-rune')].map(node=>({
        width:node.getBoundingClientRect().width,
        height:node.getBoundingClientRect().height,
        text:node.textContent.trim(),
      })),
      squad:document.querySelectorAll('.squad-member').length,
      target:document.querySelector('#bossGlyph')?.textContent.trim(),
      coreWidth:document.querySelector('.echo-core')?.getBoundingClientRect().width,
      bodyHeight:document.documentElement.scrollHeight,
      errorText:document.querySelector('.status-toast.error')?.textContent||'',
      noFxAnimation:getComputedStyle(document.querySelector('.echo-core')).animationName,
      noFxTransition:getComputedStyle(document.querySelector('.strike-rune')).transitionDuration,
    };});
    check(metrics.pageWidth<=metrics.viewport,`${width}px: page overflow ${metrics.pageWidth}px`);
    check(metrics.runes.length===3,`${width}px: expected three rune choices`);
    check(metrics.runes.every(item=>item.width>=44&&item.height>=44),`${width}px: rune target below 44px`);
    check(new Set(metrics.runes.map(item=>item.text)).size===3,`${width}px: runes are not distinct`);
    check(metrics.runes.some(item=>item.text===metrics.target),`${width}px: target rune has no match`);
    check(metrics.squad===3,`${width}px: expected three automatic squad members`);
    check(metrics.coreWidth>=150&&metrics.coreWidth<=190,`${width}px: core scale is not compact (${metrics.coreWidth})`);
    check(metrics.noFxAnimation==='none'&&metrics.noFxTransition==='0s',`${width}px: no-fx still animates`);
    check(!metrics.errorText,`${width}px: startup error ${metrics.errorText}`);
    check(errors.length===0,`${width}px: browser errors ${errors.join(', ')}`);
    if(output&&[390,1024].includes(width)){
      await page.screenshot({path:`${output}/clicker-${width}.png`,fullPage:true});
    }
    await page.close();
  }

  // Полный забег через реальный UI: читаем знак в центре и нажимаем совпавшую
  // кнопку. Это проверяет три волны, два выбора усиления и финальный экран.
  await reset();
  const play=await browser.newPage();
  const errors=[];
  play.on('pageerror',error=>errors.push(error.message));
  await play.setViewport({width:390,height:844,deviceScaleFactor:1});
  await play.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
  await play.waitForSelector('.squad-member');

  let finished=false;
  for(let guard=0;guard<100&&!finished;guard+=1){
    await play.waitForFunction(()=>{
      const signal=document.querySelector('.tap-stage')?.classList.contains('signal');
      const choice=!document.querySelector('#choiceLayer')?.hidden;
      const result=!document.querySelector('#resultLayer')?.hidden;
      return signal||choice||result;
    },{timeout:3500});
    const phase=await play.evaluate(()=>({
      result:!document.querySelector('#resultLayer').hidden,
      choice:!document.querySelector('#choiceLayer').hidden,
      signal:document.querySelector('.tap-stage').classList.contains('signal'),
      target:document.querySelector('#bossGlyph').textContent.trim(),
    }));
    if(phase.result){finished=true;break;}
    if(phase.choice){
      await play.click('.upgrade-card');
      await play.waitForFunction(()=>document.querySelector('#choiceLayer').hidden);
      continue;
    }
    if(phase.signal){
      const clicked=await play.evaluate(target=>{
        const button=[...document.querySelectorAll('.strike-rune')]
          .find(node=>node.textContent.trim()===target&&!node.disabled);
        if(!button) return false;
        button.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:button.getBoundingClientRect().x+20,clientY:button.getBoundingClientRect().y+20}));
        return true;
      },phase.target);
      check(clicked,`playthrough: matching rune ${phase.target} was not clickable`);
      await new Promise(resolve=>setTimeout(resolve,140));
    }
  }
  const result=await play.evaluate(()=>({
    visible:!document.querySelector('#resultLayer').hidden,
    title:document.querySelector('#resultTitle')?.textContent,
    stats:document.querySelector('#resultStats')?.textContent,
  }));
  check(result.visible,'playthrough: result screen did not open');
  check(result.title==='Колокол отвечает тебе',`playthrough: unexpected result ${result.title}`);
  check(/100%/.test(result.stats),`playthrough: expected 100% accuracy (${result.stats})`);
  check(errors.length===0,`playthrough: browser errors ${errors.join(', ')}`);
  if(output) await play.screenshot({path:`${output}/clicker-390-won.png`,fullPage:true});
  await play.close();
}finally{
  await browser.close();
}

if(failures.length){
  console.error(failures.map(failure=>`FAIL ${failure}`).join('\n'));
  process.exit(1);
}
console.log('OK precise clicker: 320/390/430/1024 responsive + 100% UI playthrough');
