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
    await page.setExtraHTTPHeaders({'x-reconstruction-test-clock':'fixed-step-100'});
    await page.evaluateOnNewDocument(()=>localStorage.removeItem('reconstruction-mvp-career-v1'));
    await page.setViewport({width,height:width<600?844:900,deviceScaleFactor:1});
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.waitForSelector('.squad-member');
    await page.waitForSelector('#menuLayer:not([hidden])');
    const frozenBefore=await page.$eval('#roundClock strong',node=>node.textContent);
    await new Promise(resolve=>setTimeout(resolve,320));
    const frozenAfter=await page.$eval('#roundClock strong',node=>node.textContent);
    check(frozenBefore===frozenAfter,`${width}px: timer advances behind main menu`);
    const menuMetrics=await page.evaluate(()=>({
      width:document.querySelector('.menu-card').getBoundingClientRect().width,
      height:document.querySelector('.menu-card').getBoundingClientRect().height,
      viewportHeight:innerHeight,
      tabs:document.querySelectorAll('[data-menu-tab]').length,
      startHeight:document.querySelector('#startRunButton').getBoundingClientRect().height,
    }));
    check(menuMetrics.width<=width-16,`${width}px: menu exceeds viewport`);
    check(menuMetrics.height<=menuMetrics.viewportHeight-16,`${width}px: menu exceeds viewport height`);
    check(menuMetrics.tabs===3,`${width}px: expected three menu tabs`);
    check(menuMetrics.startHeight>=42&&menuMetrics.startHeight<=48,`${width}px: start action is not compact`);
    if(output&&width===390)await page.screenshot({path:`${output}/clicker-390-menu.png`,fullPage:true});
    await page.click('#startRunButton');
    await page.waitForSelector('#menuLayer[hidden]');
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

  // Вторая встреча использует другую цель: отдельный индикатор Фонаря обязан
  // оставаться читаемым и не расширять мобильный viewport.
  for(const width of [320,390,430]){
    const session=`visual-e02-${width}`;
    const resetResponse=await fetch(`${base}/__reconstruction/reset`,{
      method:'POST',
      headers:{'content-type':'application/json','x-reconstruction-session':session},
      body:JSON.stringify({encounter_id:'e02_shattered_causeway'}),
    });
    check(resetResponse.ok,`${width}px: e02 dev reset failed`);
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width,height:844,deviceScaleFactor:1});
    await page.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),session);
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.waitForSelector('#menuLayer:not([hidden])');
    await page.click('#startRunButton');
    await page.waitForSelector('#menuLayer[hidden]');
    const metrics=await page.evaluate(()=>({
      overflow:document.documentElement.scrollWidth-innerWidth,
      objectiveHidden:document.getElementById('objectiveMeter').hidden,
      objective:document.getElementById('objectiveValue').textContent.trim(),
      targetHeight:document.querySelector('.strike-rune').getBoundingClientRect().height,
    }));
    check(metrics.overflow<=0,`${width}px: e02 overflows by ${metrics.overflow}px`);
    check(!metrics.objectiveHidden&&metrics.objective==='100%',`${width}px: lantern meter missing`);
    check(metrics.targetHeight>=44,`${width}px: e02 rune target below 44px`);
    check(errors.length===0,`${width}px: e02 browser errors ${errors.join(', ')}`);
    if(output&&width===390)await page.screenshot({path:`${output}/clicker-390-e02.png`,fullPage:true});
    await page.close();
  }

  // Сквозная формула точности: UI обязан повторять server state, а нулевое
  // количество сигналов не должно выглядеть как заработанные 100%.
  const accuracyPage=await browser.newPage();
  await accuracyPage.evaluateOnNewDocument(()=>localStorage.removeItem('reconstruction-mvp-career-v1'));
  await accuracyPage.setViewport({width:390,height:844,deviceScaleFactor:1});
  await accuracyPage.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
  await accuracyPage.waitForSelector('.squad-member');
  check(await accuracyPage.$eval('#accuracyValue',node=>node.textContent.trim())==='—','accuracy: empty run must show dash');
  await accuracyPage.click('#startRunButton');
  await accuracyPage.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:3000});
  await accuracyPage.click('#menuButton');
  await accuracyPage.waitForSelector('#pauseLayer:not([hidden])');
  const liveContract=await accuracyPage.evaluate(async()=>{
    const session=sessionStorage.getItem('reconstruction-preview-session');
    const response=await fetch('/__reconstruction/state',{headers:{'x-reconstruction-session':session}});
    const api=await response.json();
    const number=value=>Math.max(0,Math.round(Number(value)||0)).toLocaleString('ru-RU');
    return {
      actual:{
        wave:document.querySelector('#waveLabel').textContent.trim(),
        name:document.querySelector('#bossName').textContent.trim(),
        subtitle:document.querySelector('#bossSubtitle').textContent.trim(),
        clock:document.querySelector('#roundClock strong').textContent.trim(),
        health:document.querySelector('#bossHealthValue').textContent.trim(),
        combo:document.querySelector('#comboValue').textContent.trim(),
        accuracy:document.querySelector('#accuracyValue').textContent.trim(),
        tapPower:document.querySelector('#tapPowerValue').textContent.trim(),
        charge:document.querySelector('#chargeValue').textContent.trim(),
      },
      expected:{
        wave:`ВОЛНА ${api.round} ИЗ ${api.waves_total}`,
        name:api.wave.name,
        subtitle:api.wave.subtitle,
        clock:Math.max(0,api.wave.time_left_ms/1000).toFixed(1).replace('.',','),
        health:`${number(api.wave.hp)} / ${number(api.wave.hp_max)}`,
        combo:`×${api.combo.count}`,
        accuracy:api.accuracy===null?'—':`${number(api.accuracy)}%`,
        tapPower:number(api.team.tap_power),
        charge:`${Math.floor(api.team.charge/api.team.charge_max*100)}%`,
      },
    };
  });
  check(JSON.stringify(liveContract.actual)===JSON.stringify(liveContract.expected),`live readout mismatch ${JSON.stringify(liveContract)}`);
  await accuracyPage.click('#continueButton');
  await accuracyPage.waitForSelector('#pauseLayer[hidden]');
  for(const correct of [true,false]){
    await accuracyPage.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:3000});
    const clicked=await accuracyPage.evaluate(shouldBeCorrect=>{
      const target=document.querySelector('#bossGlyph').textContent.trim();
      const button=[...document.querySelectorAll('.strike-rune')].find(node=>{
        const match=node.textContent.trim()===target;
        return !node.disabled&&(shouldBeCorrect?match:!match);
      });
      if(!button)return false;
      button.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:button.getBoundingClientRect().x+20,clientY:button.getBoundingClientRect().y+20}));
      return true;
    },correct);
    check(clicked,`accuracy: ${correct?'correct':'wrong'} rune was not clickable`);
    await new Promise(resolve=>setTimeout(resolve,180));
  }
  await accuracyPage.waitForFunction(()=>document.querySelector('#accuracyValue')?.textContent.trim()==='50%',{timeout:2000});
  const accuracyContract=await accuracyPage.evaluate(async()=>{
    const session=sessionStorage.getItem('reconstruction-preview-session');
    const response=await fetch('/__reconstruction/state',{headers:{'x-reconstruction-session':session}});
    const api=await response.json();
    return {
      ui:document.querySelector('#accuracyValue').textContent.trim(),
      api:api.accuracy,
      tapAccuracy:api.tap_accuracy,
      resolved:api.signals_resolved,
      correct:api.mastery.correct_taps,
      wrong:api.mastery.mistakes,
      missed:api.mastery.missed_signals,
      totalTaps:api.mastery.total_taps,
    };
  });
  check(accuracyContract.ui==='50%'&&accuracyContract.api===50&&accuracyContract.tapAccuracy===50,'accuracy: UI/API mismatch after 1 correct + 1 wrong');
  check(accuracyContract.resolved===2&&accuracyContract.correct===1&&accuracyContract.wrong===1&&accuracyContract.missed===0&&accuracyContract.totalTaps===2,`accuracy: counters mismatch ${JSON.stringify(accuracyContract)}`);
  await accuracyPage.close();

  // Полный забег через реальный UI: читаем знак в центре и нажимаем совпавшую
  // кнопку. Это проверяет три волны, два выбора усиления и финальный экран.
  await reset();
  const play=await browser.newPage();
  const errors=[];
  play.on('pageerror',error=>errors.push(error.message));
  await play.evaluateOnNewDocument(()=>{
    if(!sessionStorage.getItem('reconstruction-verify-started')){
      localStorage.removeItem('reconstruction-mvp-career-v1');
      sessionStorage.setItem('reconstruction-verify-started','1');
    }
    window.__reconstructionLayoutShifts=[];
    new PerformanceObserver(list=>{
      for(const entry of list.getEntries())if(!entry.hadRecentInput)window.__reconstructionLayoutShifts.push({
        value:entry.value,
        sources:(entry.sources||[]).map(source=>{
          const node=source.node;
          return node?.id?`#${node.id}`:node?.className?`.${String(node.className).trim().replace(/\s+/g,'.')}`:node?.tagName||'unknown';
        }),
      });
    }).observe({type:'layout-shift',buffered:true});
  });
  await play.setViewport({width:390,height:844,deviceScaleFactor:1});
  await play.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
  await play.waitForSelector('.squad-member');
  await play.click('#startRunButton');
  await play.waitForSelector('#menuLayer[hidden]');

  // Пауза не должна расходовать время и должна возвращать в тот же run.
  await new Promise(resolve=>setTimeout(resolve,220));
  await play.click('#menuButton');
  await play.waitForSelector('#pauseLayer:not([hidden])');
  const pauseBefore=await play.$eval('#roundClock strong',node=>node.textContent);
  await new Promise(resolve=>setTimeout(resolve,320));
  const pauseAfter=await play.$eval('#roundClock strong',node=>node.textContent);
  check(pauseBefore===pauseAfter,'pause: timer keeps advancing');

  // Measure the underlying battle layout while the run is paused.  Advancing
  // nearly a second here would intentionally ignore an open signal and make a
  // 100%-accuracy playthrough depend on test timing.
  const geometry=await play.evaluate(async()=>{
    const selectors=['#battleCard','.echo-core','.rune-orbit','.combat-readout','.squad-strip'];
    const samples=[];
    for(let index=0;index<18;index+=1){
      samples.push(selectors.map(selector=>{
        const rect=document.querySelector(selector).getBoundingClientRect();
        return [rect.x,rect.y,rect.width,rect.height].map(value=>Math.round(value*10)/10);
      }));
      await new Promise(resolve=>setTimeout(resolve,55));
    }
    return samples;
  });
  for(let element=0;element<geometry[0].length;element+=1){
    for(let metric=0;metric<4;metric+=1){
      const values=geometry.map(sample=>sample[element][metric]);
      check(Math.max(...values)-Math.min(...values)<=1,`stability: element ${element} metric ${metric} shifted (${Math.min(...values)}..${Math.max(...values)})`);
    }
  }
  await play.click('#continueButton');
  await play.waitForSelector('#pauseLayer[hidden]');

  let finished=false;
  let capturedChoice=false;
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
      if(output&&!capturedChoice){
        await play.screenshot({path:`${output}/clicker-390-choice.png`,fullPage:true});
        capturedChoice=true;
      }
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
  const resultContract=await play.evaluate(async()=>{
    const session=sessionStorage.getItem('reconstruction-preview-session');
    const response=await fetch('/__reconstruction/state',{headers:{'x-reconstruction-session':session}});
    const api=await response.json();
    const number=value=>Math.max(0,Math.round(Number(value)||0)).toLocaleString('ru-RU');
    return {
      actual:[...document.querySelectorAll('#resultStats span')].map(node=>({
        value:node.querySelector('strong')?.textContent.trim(),
        label:[...node.childNodes]
          .filter(child=>child.nodeType===Node.TEXT_NODE)
          .map(child=>child.textContent.trim())
          .join(' '),
      })),
      expected:[
        {value:String(api.mastery.correct_taps),label:'точных'},
        {value:`${number(api.accuracy)}%`,label:'точность'},
        {value:String(api.combo.max),label:'макс. серия'},
        {value:String(api.mastery.mistakes),label:'ошибок'},
        {value:String(api.mastery.missed_signals),label:'пропущено'},
        {value:`${Math.round(api.mastery.elapsed_ms/1000)}с`,label:'время'},
      ],
    };
  });
  check(JSON.stringify(resultContract.actual)===JSON.stringify(resultContract.expected),`result readout mismatch ${JSON.stringify(resultContract)}`);
  const modalState=()=>play.evaluate(()=>{
    const ids=['menuLayer','pauseLayer','choiceLayer','resultLayer'];
    return ids.filter(id=>!document.getElementById(id).hidden);
  });
  check(JSON.stringify(await modalState())===JSON.stringify(['resultLayer']),'modal: result is not the only visible layer');
  await new Promise(resolve=>setTimeout(resolve,650));
  check(JSON.stringify(await modalState())===JSON.stringify(['resultLayer']),'modal: result changed without user action');
  if(output) await play.screenshot({path:`${output}/clicker-390-won.png`,fullPage:true});
  const shiftsBeforeReload=await play.evaluate(()=>window.__reconstructionLayoutShifts);
  await play.reload({waitUntil:'domcontentloaded'});
  await play.waitForSelector('#resultLayer:not([hidden])');
  check(JSON.stringify(await modalState())===JSON.stringify(['resultLayer']),'modal: live reload did not restore result layer');
  check(await play.$eval('#resultTitle',node=>node.textContent.trim())==='Колокол отвечает тебе','modal: result content changed after reload');
  await play.click('#resultMenu');
  await play.waitForSelector('#menuLayer:not([hidden])');
  await new Promise(resolve=>setTimeout(resolve,450));
  check(JSON.stringify(await modalState())===JSON.stringify(['menuLayer']),'modal: stats menu changed without user action');
  const career=await play.evaluate(()=>({
    stats:document.querySelector('#careerStats')?.textContent,
    activeTab:document.querySelector('[data-menu-tab].active')?.dataset.menuTab,
  }));
  check(career.activeTab==='stats','result: stats menu did not open');
  check(/1побед/.test((career.stats||'').replace(/\s/g,'')),`result: local victory was not recorded (${career.stats})`);
  check(errors.length===0,`playthrough: browser errors ${errors.join(', ')}`);
  const shiftsAfterReload=await play.evaluate(()=>window.__reconstructionLayoutShifts);
  const allShifts=[...shiftsBeforeReload,...shiftsAfterReload];
  const cls=allShifts.reduce((sum,item)=>sum+item.value,0);
  check(cls<0.05,`playthrough: unexpected layout shift score ${cls} ${JSON.stringify(allShifts)}`);
  if(output) await play.screenshot({path:`${output}/clicker-390-stats.png`,fullPage:true});
  await play.close();
}finally{
  await browser.close();
}

if(failures.length){
  console.error(failures.map(failure=>`FAIL ${failure}`).join('\n'));
  process.exit(1);
}
console.log('OK precise clicker: 320/390/430/1024 responsive + 100% UI playthrough');
