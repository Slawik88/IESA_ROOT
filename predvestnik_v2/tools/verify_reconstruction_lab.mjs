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
    check(menuMetrics.tabs===5,`${width}px: expected five menu tabs`);
    check(menuMetrics.startHeight>=42&&menuMetrics.startHeight<=48,`${width}px: start action is not compact`);
    if(output&&width===390)await page.screenshot({path:`${output}/clicker-390-menu.png`,fullPage:true});
    await page.click('[data-menu-tab="companion"]');
    await page.waitForSelector('.role-card');
    const companionMetrics=await page.evaluate(()=>({
      pageWidth:document.documentElement.scrollWidth,
      viewport:innerWidth,
      menuHeight:document.querySelector('.menu-card').getBoundingClientRect().height,
      viewportHeight:innerHeight,
      roles:document.querySelectorAll('.role-card').length,
      careHeights:[...document.querySelectorAll('[data-care-action]')].map(node=>node.getBoundingClientRect().height),
      expeditionOptions:document.querySelectorAll('.expedition-grid > button').length,
    }));
    check(companionMetrics.pageWidth<=companionMetrics.viewport,`${width}px: companion page overflows`);
    check(companionMetrics.menuHeight<=companionMetrics.viewportHeight-16,`${width}px: companion menu exceeds viewport`);
    check(companionMetrics.roles===10,`${width}px: expected ten companion roles`);
    check(companionMetrics.careHeights.every(height=>height>=34&&height<=44),`${width}px: care controls are not compact`);
    check(companionMetrics.expeditionOptions===3,`${width}px: expected three expedition contracts`);
    if(output&&width===390)await page.screenshot({path:`${output}/clicker-390-companion.png`,fullPage:true});
    await page.click('[data-menu-tab="alliance"]');
    await page.waitForSelector('[data-menu-panel="alliance"]:not([hidden])');
    const allianceMetrics=await page.evaluate(()=>({
      overflow:document.documentElement.scrollWidth-innerWidth,
      stages:document.querySelectorAll('.alliance-stages > span').length,
      copy:document.getElementById('allianceContent')?.textContent,
    }));
    check(allianceMetrics.overflow<=0,`${width}px: Alliance panel overflows`);
    check(allianceMetrics.stages===3,`${width}px: Alliance stages are incomplete`);
    check(allianceMetrics.copy?.includes('0 НАГРАД'),`${width}px: Alliance test state is unclear`);
    if(output&&width===390)await page.screenshot({path:`${output}/clicker-390-alliance.png`,fullPage:true});
    await page.click('[data-menu-tab="play"]');
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
      companionDecoys:document.querySelectorAll('.strike-rune.companion-decoy').length,
      companionBuild:document.querySelectorAll('.companion-build').length,
      readableText:[
        '#bossHealthValue', '#windowIndicator span', '#coreHint',
        '.combat-readout span', '.squad-member small', '.build-strip small', '.event-strip',
      ].map(selector=>({selector,size:parseFloat(getComputedStyle(document.querySelector(selector)).fontSize)})),
    };});
    check(metrics.pageWidth<=metrics.viewport,`${width}px: page overflow ${metrics.pageWidth}px`);
    check(metrics.runes.length===3,`${width}px: expected three rune choices`);
    check(metrics.runes.every(item=>item.width>=44&&item.height>=44),`${width}px: rune target below 44px`);
    check(new Set(metrics.runes.map(item=>item.text)).size===3,`${width}px: runes are not distinct`);
    check(metrics.runes.some(item=>item.text===metrics.target),`${width}px: target rune has no match`);
    check(metrics.squad===3,`${width}px: expected three automatic squad members`);
    check(metrics.coreWidth>=150&&metrics.coreWidth<=190,`${width}px: core scale is not compact (${metrics.coreWidth})`);
    check(metrics.noFxAnimation==='none'&&metrics.noFxTransition==='0s',`${width}px: no-fx still animates`);
    check(metrics.companionDecoys===1,`${width}px: Lantern did not mark exactly one decoy`);
    check(metrics.companionBuild===1,`${width}px: companion role missing from active build`);
    check(metrics.readableText.every(item=>item.size>=9),`${width}px: unreadable combat text ${JSON.stringify(metrics.readableText)}`);
    check(!metrics.errorText,`${width}px: startup error ${metrics.errorText}`);
    check(errors.length===0,`${width}px: browser errors ${errors.join(', ')}`);
    if(output&&[390,1024].includes(width)){
      await page.screenshot({path:`${output}/clicker-${width}.png`,fullPage:true});
    }
    await page.close();
  }

  {
    const session=`feedback-ui-${Date.now()}`;
    const feedbackReset=await fetch(`${base}/__reconstruction/reset`,{
      method:'POST',
      headers:{'content-type':'application/json','x-reconstruction-session':session},
      body:JSON.stringify({encounter_id:'e01_two_bells'}),
    });
    check(feedbackReset.ok,'feedback UI: dev reset failed');
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width:390,height:844,deviceScaleFactor:1});
    await page.setExtraHTTPHeaders({'x-reconstruction-test-clock':'fixed-step-100'});
    await page.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),session);
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.click('#startRunButton');
    await page.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal')
      && [...document.querySelectorAll('.strike-rune')].some(node=>!node.disabled),{timeout:3000});
    const wrongClicked=await page.evaluate(()=>{
      const target=document.getElementById('bossGlyph').textContent.trim();
      const button=[...document.querySelectorAll('.strike-rune')]
        .find(node=>node.textContent.trim()!==target&&!node.disabled);
      if(!button)return false;
      button.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:button.getBoundingClientRect().x+20,clientY:button.getBoundingClientRect().y+20}));
      return true;
    });
    check(wrongClicked,'feedback UI: deliberate mistake was not clickable');
    await page.waitForSelector('.impact.miss',{timeout:2000});
    const missFeedback=await page.evaluate(()=>({
      text:document.querySelector('.impact.miss')?.textContent.trim(),
      accuracy:document.getElementById('accuracyValue').textContent.trim(),
      battleVisible:document.getElementById('menuLayer').hidden
        && document.getElementById('choiceLayer').hidden
        && document.getElementById('resultLayer').hidden,
    }));
    check(missFeedback.text==='ОШИБКА',`feedback UI: mistake confirmation missing ${JSON.stringify(missFeedback)}`);
    check(missFeedback.accuracy==='0%',`feedback UI: mistake accuracy is unclear ${missFeedback.accuracy}`);
    check(missFeedback.battleVisible,'feedback UI: mistake opened an unrelated modal');
    if(output)await page.screenshot({path:`${output}/clicker-390-error-feedback.png`,fullPage:true});
    await page.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal')
      && [...document.querySelectorAll('.strike-rune')].some(node=>!node.disabled),{timeout:3000});
    const correctClicked=await page.evaluate(()=>{
      const target=document.getElementById('bossGlyph').textContent.trim();
      const button=[...document.querySelectorAll('.strike-rune')]
        .find(node=>node.textContent.trim()===target&&!node.disabled);
      if(!button)return false;
      button.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:button.getBoundingClientRect().x+20,clientY:button.getBoundingClientRect().y+20}));
      return true;
    });
    check(correctClicked,'feedback UI: recovery signal was not clickable');
    await page.waitForSelector('.impact.hit',{timeout:2000});
    const hitFeedback=await page.$eval('.impact.hit',node=>node.textContent.trim());
    check(hitFeedback.startsWith('ТОЧНО'),`feedback UI: success confirmation missing ${hitFeedback}`);
    check(errors.length===0,`feedback UI browser errors ${errors.join(', ')}`);
    if(output)await page.screenshot({path:`${output}/clicker-390-success-feedback.png`,fullPage:true});
    await page.close();
  }

  {
    const session=`guardian-ui-${Date.now()}`;
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width:390,height:844,deviceScaleFactor:1});
    await page.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),session);
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.waitForSelector('#menuLayer:not([hidden])');
    await page.click('[data-menu-tab="companion"]');
    await page.waitForSelector('[data-companion-role="guardian"]');
    await page.click('[data-companion-role="guardian"]');
    await page.waitForFunction(()=>document.querySelector('[data-companion-role="guardian"]')?.classList.contains('selected'));
    await page.click('[data-menu-tab="play"]');
    await page.click('#startRunButton');
    await page.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:3000});
    await page.waitForSelector('[data-combat-command="companion_guardian_window"]');
    const guardianUsability=await page.evaluate(()=>{
      const button=document.querySelector('[data-combat-command="companion_guardian_window"]');
      const rune=document.querySelector('.strike-rune');
      const rect=button.getBoundingClientRect();
      return {
        height:rect.height,
        fontSize:parseFloat(getComputedStyle(button).fontSize),
        gapToRunes:rune.getBoundingClientRect().top-rect.bottom,
        inStage:Boolean(button.closest('.tap-stage')),
        visible:rect.top>=0&&rect.bottom<=innerHeight,
      };
    });
    check(guardianUsability.height>=44,`Guardian skill target is too short: ${guardianUsability.height}px`);
    check(guardianUsability.fontSize>=10,`Guardian skill text is too small: ${guardianUsability.fontSize}px`);
    check(guardianUsability.gapToRunes>=0&&guardianUsability.gapToRunes<=18,`Guardian skill is too far from runes: ${guardianUsability.gapToRunes}px`);
    check(guardianUsability.inStage&&guardianUsability.visible,'Guardian skill is outside the active play area');
    await page.$eval('[data-combat-command="companion_guardian_window"]',node=>{node.dataset.frameStable='yes';});
    await new Promise(resolve=>setTimeout(resolve,240));
    const guardianStable=await page.$eval('[data-combat-command="companion_guardian_window"]',node=>node.dataset.frameStable);
    check(guardianStable==='yes','Guardian skill was recreated during the active tap window');
    if(output)await page.screenshot({path:`${output}/clicker-390-guardian-ready.png`,fullPage:true});
    await page.evaluate(()=>document.querySelector('[data-combat-command="companion_guardian_window"]')?.click());
    await page.waitForFunction(()=>!document.querySelector('[data-combat-command="companion_guardian_window"]'));
    const roleState=await page.evaluate(()=>({
      role:document.querySelector('.companion-build b')?.textContent.trim(),
      overflow:document.documentElement.scrollWidth-innerWidth,
    }));
    check(roleState.role==='Страж',`Guardian active-build label missing: ${roleState.role}`);
    check(roleState.overflow<=0,`Guardian controls overflow by ${roleState.overflow}px`);
    check(errors.length===0,`Guardian UI browser errors ${errors.join(', ')}`);
    if(output)await page.screenshot({path:`${output}/clicker-390-guardian-armed.png`,fullPage:true});
    await page.close();
  }

  {
    const session=`rhythm-ui-${Date.now()}`;
    const rhythmReset=await fetch(`${base}/__reconstruction/reset`,{
      method:'POST',
      headers:{'content-type':'application/json','x-reconstruction-session':session},
      body:JSON.stringify({encounter_id:'e02_shattered_causeway'}),
    });
    check(rhythmReset.ok,'Rhythm Keeper UI: dev reset failed');
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width:390,height:844,deviceScaleFactor:1});
    await page.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),session);
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.waitForSelector('#menuLayer:not([hidden])');
    await page.click('[data-menu-tab="companion"]');
    await page.waitForSelector('[data-companion-role="rhythm_keeper"]');
    await page.click('[data-companion-role="rhythm_keeper"]');
    await page.waitForFunction(()=>document.querySelector('[data-companion-role="rhythm_keeper"]')?.classList.contains('selected'));
    await page.click('[data-menu-tab="play"]');
    await page.click('#startRunButton');
    await page.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:3000});
    await page.waitForSelector('[data-combat-command="companion_rhythm_guard"]');
    const rhythmUsability=await page.evaluate(()=>{
      const button=document.querySelector('[data-combat-command="companion_rhythm_guard"]');
      const rect=button.getBoundingClientRect();
      return {height:rect.height,fontSize:parseFloat(getComputedStyle(button).fontSize),copy:button.textContent.trim()};
    });
    check(rhythmUsability.height>=44,`Rhythm skill target is too short: ${rhythmUsability.height}px`);
    check(rhythmUsability.fontSize>=10&&rhythmUsability.copy.includes('пропуск'),`Rhythm skill lacks readable consequence: ${JSON.stringify(rhythmUsability)}`);
    if(output)await page.screenshot({path:`${output}/clicker-390-rhythm-ready.png`,fullPage:true});
    await page.evaluate(()=>document.querySelector('[data-combat-command="companion_rhythm_guard"]')?.click());
    await page.waitForFunction(()=>document.querySelector('#accuracyValue')?.textContent.trim()==='0%',{timeout:5000});
    const roleState=await page.evaluate(async()=>{
      const sessionKey=sessionStorage.getItem('reconstruction-preview-session');
      const response=await fetch('/__reconstruction/state',{headers:{'x-reconstruction-session':sessionKey}});
      const api=await response.json();
      return {
        role:document.querySelector('.companion-build b')?.textContent.trim(),
        missed:api.mastery.missed_signals,
        integrity:api.objective_state?.lantern_integrity,
        overflow:document.documentElement.scrollWidth-innerWidth,
      };
    });
    check(roleState.role==='Хранитель ритма',`Rhythm Keeper active-build label missing: ${roleState.role}`);
    check(roleState.missed===1,`Rhythm Keeper hid the miss from accuracy: ${roleState.missed}`);
    check(roleState.integrity===100,`Rhythm Keeper failed to protect objective integrity: ${roleState.integrity}`);
    check(roleState.overflow<=0,`Rhythm Keeper controls overflow by ${roleState.overflow}px`);
    check(errors.length===0,`Rhythm Keeper UI browser errors ${errors.join(', ')}`);
    if(output)await page.screenshot({path:`${output}/clicker-390-rhythm-guard.png`,fullPage:true});
    await page.close();
  }

  {
    const session=`echo-ui-${Date.now()}`;
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width:390,height:844,deviceScaleFactor:1});
    await page.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),session);
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.waitForSelector('#menuLayer:not([hidden])');
    await page.click('[data-menu-tab="companion"]');
    await page.waitForSelector('[data-companion-role="echo"]');
    await page.click('[data-companion-role="echo"]');
    await page.waitForFunction(()=>document.querySelector('[data-companion-role="echo"]')?.classList.contains('selected'));
    await page.click('[data-menu-tab="play"]');
    await page.click('#startRunButton');
    await page.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:3000});
    const strikeTarget=()=>page.evaluate(()=>{
      const target=document.querySelector('#bossGlyph')?.textContent.trim();
      const button=[...document.querySelectorAll('.strike-rune')]
        .find(node=>node.textContent.trim()===target&&!node.disabled);
      if(!button)return false;
      button.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));
      return true;
    });
    check(await strikeTarget(),'Echo UI: first known signal was not clickable');
    await page.waitForSelector('[data-combat-command="companion_echo_repeat"]',{timeout:3000});
    const echoUsability=await page.evaluate(()=>{
      const button=document.querySelector('[data-combat-command="companion_echo_repeat"]');
      const rect=button.getBoundingClientRect();
      return {height:rect.height,fontSize:parseFloat(getComputedStyle(button).fontSize),copy:button.textContent.trim()};
    });
    check(echoUsability.height>=44,`Echo skill target is too short: ${echoUsability.height}px`);
    check(echoUsability.fontSize>=10&&echoUsability.copy.includes('62%'),`Echo skill lacks readable timing: ${JSON.stringify(echoUsability)}`);
    if(output)await page.screenshot({path:`${output}/clicker-390-echo-ready.png`,fullPage:true});
    await page.evaluate(()=>document.querySelector('[data-combat-command="companion_echo_repeat"]')?.click());
    await page.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:3000});
    check(await strikeTarget(),'Echo UI: accelerated repeat was not clickable');
    await page.waitForFunction(async()=>{
      const sessionKey=sessionStorage.getItem('reconstruction-preview-session');
      const response=await fetch('/__reconstruction/state',{headers:{'x-reconstruction-session':sessionKey}});
      const api=await response.json();
      return Number(api.companion_state?.echo_insight)===1;
    },{polling:200,timeout:3000});
    const roleState=await page.evaluate(()=>({
      role:document.querySelector('.companion-build b')?.textContent.trim(),
      overflow:document.documentElement.scrollWidth-innerWidth,
    }));
    check(roleState.role==='Эхо',`Echo active-build label missing: ${roleState.role}`);
    check(roleState.overflow<=0,`Echo controls overflow by ${roleState.overflow}px`);
    check(errors.length===0,`Echo UI browser errors ${errors.join(', ')}`);
    if(output)await page.screenshot({path:`${output}/clicker-390-echo-repeat.png`,fullPage:true});
    await page.close();
  }

  {
    const session=`navigator-ui-${Date.now()}`;
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width:320,height:844,deviceScaleFactor:1});
    await page.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),session);
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.waitForSelector('#menuLayer:not([hidden])');
    await page.click('[data-menu-tab="companion"]');
    await page.waitForSelector('[data-companion-role="navigator"]');
    await page.click('[data-companion-role="navigator"]');
    await page.waitForFunction(()=>document.querySelector('[data-companion-role="navigator"]')?.classList.contains('selected'));
    await page.click('[data-menu-tab="play"]');
    await page.click('#startRunButton');
    await page.waitForSelector('.companion-build');
    const forecastState=await page.evaluate(async()=>{
      const sessionKey=sessionStorage.getItem('reconstruction-preview-session');
      const response=await fetch('/__reconstruction/state',{headers:{'x-reconstruction-session':sessionKey}});
      const api=await response.json();
      return {
        role:document.querySelector('.companion-build b')?.textContent.trim(),
        note:document.querySelector('.companion-build small')?.textContent.trim(),
        forecast:api.companion_state?.navigator_forecast,
        overflow:document.documentElement.scrollWidth-innerWidth,
      };
    });
    check(forecastState.role==='Навигатор',`Navigator active-build label missing: ${forecastState.role}`);
    check(forecastState.note?.includes(`${forecastState.forecast?.wave}-я волна`),`Navigator forecast is not visible: ${forecastState.note}`);
    check(forecastState.forecast?.reveals_answer===false,'Navigator leaked a correct answer');
    check(forecastState.overflow<=0,`Navigator forecast overflows by ${forecastState.overflow}px`);
    check(errors.length===0,`Navigator UI browser errors ${errors.join(', ')}`);
    if(output)await page.screenshot({path:`${output}/clicker-320-navigator.png`,fullPage:true});
    await page.close();
  }

  // DEV-only time compression makes the real expedition state transitions
  // testable without waiting two hours.  No wallet is attached to this bridge.
  {
    const session=`expedition-ui-state-machine-${Date.now()}`;
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width:390,height:844,deviceScaleFactor:1});
    await page.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),session);
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.waitForSelector('#menuLayer:not([hidden])');
    await page.click('[data-menu-tab="companion"]');
    await page.waitForSelector('[data-expedition-hours="2"]:not(:disabled)');
    await page.click('[data-expedition-hours="2"]');
    await page.waitForSelector('.expedition-contracts > span');
    const started=await page.evaluate(()=>({
      reserved:document.querySelector('.expedition-preview header > b')?.textContent.trim(),
      text:document.querySelector('.expedition-contracts')?.textContent,
    }));
    check(started.reserved?.includes('50'),`expedition UI did not reserve 50 Mora: ${started.reserved}`);
    check(started.text?.includes('2ч'),`expedition UI contract missing: ${started.text}`);
    await page.waitForSelector('[data-expedition-claim]',{timeout:12000});
    await page.click('[data-expedition-claim]');
    await page.waitForFunction(()=>document.querySelector('.status-toast')?.textContent.includes('В кошелёк не начислено'));
    const claimed=await page.evaluate(()=>({
      visibleContracts:document.querySelectorAll('.expedition-contracts > span').length,
      toast:document.querySelector('.status-toast').textContent,
      overflow:document.documentElement.scrollWidth-innerWidth,
    }));
    check(claimed.visibleContracts===0,'claimed expedition remains actionable');
    check(claimed.toast.includes('50 Моры'),'shadow claim total is missing');
    check(claimed.overflow<=0,`expedition state UI overflows by ${claimed.overflow}px`);
    check(errors.length===0,`expedition UI browser errors ${errors.join(', ')}`);
    if(output)await page.screenshot({path:`${output}/clicker-390-expedition-claimed.png`,fullPage:true});
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
    await page.setExtraHTTPHeaders({'x-reconstruction-test-clock':'fixed-step-100'});
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

  for(const spec of [
    {id:'e03_ink_path',label:'ЯСНОСТЬ',cue:'ОТРАЖЕНИЕ'},
    {id:'e03_ash_path',label:'ОГОНЬ',cue:null},
  ]){
    for(const width of [320,390,430]){
      const session=`visual-${spec.id}-${width}`;
      const response=await fetch(`${base}/__reconstruction/reset`,{
        method:'POST',
        headers:{'content-type':'application/json','x-reconstruction-session':session},
        body:JSON.stringify({encounter_id:spec.id}),
      });
      check(response.ok,`${spec.id} ${width}px: dev reset failed`);
      const page=await browser.newPage();
      const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.setViewport({width,height:844,deviceScaleFactor:1});
      await page.setExtraHTTPHeaders({'x-reconstruction-test-clock':'fixed-step-100'});
      await page.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),session);
      await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
      await page.click('#startRunButton');
      await page.waitForFunction(label=>document.getElementById('objectiveLabel')?.textContent.trim()===label,{},spec.label);
      if(spec.cue){
        await page.waitForFunction(cue=>document.getElementById('corePrompt')?.textContent.trim()===cue,{timeout:3000},spec.cue);
      }
      const metrics=await page.evaluate(()=>({
        overflow:document.documentElement.scrollWidth-innerWidth,
        objectiveHidden:document.getElementById('objectiveMeter').hidden,
        targetHeight:document.querySelector('.strike-rune').getBoundingClientRect().height,
      }));
      check(metrics.overflow<=0,`${spec.id} ${width}px: overflow ${metrics.overflow}px`);
      check(!metrics.objectiveHidden,`${spec.id} ${width}px: objective hidden`);
      check(metrics.targetHeight>=44,`${spec.id} ${width}px: target below 44px`);
      check(errors.length===0,`${spec.id} ${width}px: ${errors.join(', ')}`);
      await page.close();
    }
  }

  // Встреча памяти сначала показывает цепочку, затем намеренно убирает
  // центральную подсказку. На мобильном остаются только три удобные руны.
  for(const width of [320,390,430]){
    const session=`visual-e04-${width}`;
    const response=await fetch(`${base}/__reconstruction/reset`,{
      method:'POST',
      headers:{'content-type':'application/json','x-reconstruction-session':session},
      body:JSON.stringify({encounter_id:'e04_drowned_names'}),
    });
    check(response.ok,`${width}px: e04 dev reset failed`);
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width,height:844,deviceScaleFactor:1});
    await page.setExtraHTTPHeaders({'x-reconstruction-test-clock':'fixed-step-100'});
    await page.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),session);
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.click('#startRunButton');
    await page.waitForFunction(()=>
      document.getElementById('corePrompt')?.textContent.trim()==='ЗАПОМНИ'
      && ['◇','△','○'].includes(document.getElementById('bossGlyph')?.textContent.trim()),
      {timeout:3000},
    );
    const previewSymbol=await page.$eval('#bossGlyph',node=>node.textContent.trim());
    check(['◇','△','○'].includes(previewSymbol),`${width}px: e04 preview rune missing (${previewSymbol})`);
    await page.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:4000});
    const metrics=await page.evaluate(()=>({
      overflow:document.documentElement.scrollWidth-innerWidth,
      objective:document.getElementById('objectiveValue').textContent.trim(),
      prompt:document.getElementById('corePrompt').textContent.trim(),
      center:document.getElementById('bossGlyph').textContent.trim(),
      runes:[...document.querySelectorAll('.strike-rune')].map(node=>({
        text:node.textContent.trim(),height:node.getBoundingClientRect().height,
      })),
    }));
    check(metrics.overflow<=0,`${width}px: e04 overflow ${metrics.overflow}px`);
    check(metrics.objective==='0/3',`${width}px: e04 anchor counter ${metrics.objective}`);
    check(metrics.prompt==='ПОВТОРИ',`${width}px: e04 recall prompt ${metrics.prompt}`);
    check(!metrics.runes.some(item=>item.text===metrics.center),`${width}px: e04 leaked target in center`);
    check(metrics.runes.every(item=>item.height>=44),`${width}px: e04 target below 44px`);
    check(errors.length===0,`${width}px: e04 browser errors ${errors.join(', ')}`);
    if(output&&width===390)await page.screenshot({path:`${output}/clicker-390-e04.png`,fullPage:true});
    await page.close();
  }

  // Зеркальный двор визуально отмечает прошлую позицию, но правильная руна
  // всегда остаётся на другой доступной кнопке.
  for(const width of [320,390,430]){
    const session=`visual-e05-${width}`;
    const response=await fetch(`${base}/__reconstruction/reset`,{
      method:'POST',
      headers:{'content-type':'application/json','x-reconstruction-session':session},
      body:JSON.stringify({encounter_id:'e05_mirror_courtyard'}),
    });
    check(response.ok,`${width}px: e05 dev reset failed`);
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width,height:844,deviceScaleFactor:1});
    await page.setExtraHTTPHeaders({'x-reconstruction-test-clock':'fixed-step-100'});
    await page.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),session);
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.click('#startRunButton');
    await page.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:3000});
    const clicked=await page.evaluate(()=>{
      const target=document.getElementById('bossGlyph').textContent.trim();
      const button=[...document.querySelectorAll('.strike-rune')]
        .find(node=>node.textContent.trim()===target&&!node.disabled);
      if(!button)return false;
      button.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));
      return true;
    });
    check(clicked,`${width}px: e05 first target missing`);
    await page.waitForFunction(()=>
      document.querySelector('.tap-stage')?.classList.contains('signal')
      && [...document.querySelectorAll('.strike-rune')].some(node=>!node.disabled)
      && document.querySelector('.strike-rune.mirror-forbidden'),
      {timeout:3000},
    );
    const metrics=await page.evaluate(()=>{
      const target=document.getElementById('bossGlyph').textContent.trim();
      const forbidden=document.querySelector('.strike-rune.mirror-forbidden');
      const matching=[...document.querySelectorAll('.strike-rune')]
        .find(node=>node.textContent.trim()===target&&!node.disabled);
      return {
        overflow:document.documentElement.scrollWidth-innerWidth,
        objective:document.getElementById('objectiveValue').textContent.trim(),
        forbiddenIsTarget:forbidden===matching,
        forbiddenHeight:forbidden?.getBoundingClientRect().height||0,
      };
    });
    check(metrics.overflow<=0,`${width}px: e05 overflow ${metrics.overflow}px`);
    check(metrics.objective==='3/3',`${width}px: e05 ward counter ${metrics.objective}`);
    check(!metrics.forbiddenIsTarget,`${width}px: e05 target stayed in forbidden slot`);
    check(metrics.forbiddenHeight>=44,`${width}px: e05 forbidden target below 44px`);
    check(errors.length===0,`${width}px: e05 browser errors ${errors.join(', ')}`);
    if(output&&width===390)await page.screenshot({path:`${output}/clicker-390-e05.png`,fullPage:true});
    await page.close();
  }

  // Босс получает собственные подписи фаз, компактный счётчик и первую
  // серверную механику Записи без наследования чужих названий волн.
  for(const width of [320,390,430]){
    const session=`visual-e06-${width}`;
    const response=await fetch(`${base}/__reconstruction/reset`,{
      method:'POST',
      headers:{'content-type':'application/json','x-reconstruction-session':session},
      body:JSON.stringify({encounter_id:'e06_archivist'}),
    });
    check(response.ok,`${width}px: e06 dev reset failed`);
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setViewport({width,height:844,deviceScaleFactor:1});
    await page.setExtraHTTPHeaders({'x-reconstruction-test-clock':'fixed-step-100'});
    await page.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),session);
    await page.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
    await page.click('#startRunButton');
    await page.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:3000});
    const clicked=await page.evaluate(()=>{
      const target=document.getElementById('bossGlyph').textContent.trim();
      const button=[...document.querySelectorAll('.strike-rune')]
        .find(node=>node.textContent.trim()===target&&!node.disabled);
      if(!button)return false;
      button.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));
      return true;
    });
    check(clicked,`${width}px: e06 first target missing`);
    await page.waitForFunction(()=>
      document.querySelector('.tap-stage')?.classList.contains('signal')
      && [...document.querySelectorAll('.strike-rune')].some(node=>!node.disabled)
      && document.querySelector('.strike-rune.mirror-forbidden'),
      {timeout:3000},
    );
    const metrics=await page.evaluate(()=>({
      overflow:document.documentElement.scrollWidth-innerWidth,
      objective:document.getElementById('objectiveValue').textContent.trim(),
      rails:[...document.querySelectorAll('[data-wave-node] small')].map(node=>node.textContent.trim()),
      phase:document.getElementById('bossName').textContent.trim(),
      forbiddenHeight:document.querySelector('.strike-rune.mirror-forbidden')?.getBoundingClientRect().height||0,
    }));
    check(metrics.overflow<=0,`${width}px: e06 overflow ${metrics.overflow}px`);
    check(metrics.objective==='0/3',`${width}px: e06 phase counter ${metrics.objective}`);
    check(metrics.rails.join('|')==='Запись|Прилив|Имя',`${width}px: e06 rail ${metrics.rails.join('|')}`);
    check(metrics.phase==='Фаза I · Запись',`${width}px: e06 phase name ${metrics.phase}`);
    check(metrics.forbiddenHeight>=44,`${width}px: e06 forbidden target below 44px`);
    check(errors.length===0,`${width}px: e06 browser errors ${errors.join(', ')}`);
    if(output&&width===390)await page.screenshot({path:`${output}/clicker-390-e06.png`,fullPage:true});
    await page.close();
  }

  // Один глубокий проход босса проверяет, что в браузере реально появляются
  // вторая и третья грамматики, а не только их серверные поля.
  const bossSession='visual-e06-deep';
  const bossReset=await fetch(`${base}/__reconstruction/reset`,{
    method:'POST',
    headers:{'content-type':'application/json','x-reconstruction-session':bossSession},
    body:JSON.stringify({encounter_id:'e06_archivist'}),
  });
  check(bossReset.ok,'e06 deep: dev reset failed');
  const bossPage=await browser.newPage();
  const bossErrors=[];
  bossPage.on('pageerror',error=>bossErrors.push(error.message));
  await bossPage.setViewport({width:390,height:844,deviceScaleFactor:1});
  await bossPage.setExtraHTTPHeaders({'x-reconstruction-test-clock':'fixed-step-100'});
  await bossPage.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),bossSession);
  await bossPage.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
  await bossPage.click('#startRunButton');
  let tideCaptured=false;
  let lastNameCaptured=false;
  for(let guard=0;guard<160&&!lastNameCaptured;guard+=1){
    await bossPage.waitForFunction(()=>{
      const signal=document.querySelector('.tap-stage')?.classList.contains('signal')
        && [...document.querySelectorAll('.strike-rune')].some(node=>!node.disabled);
      const choice=!document.getElementById('choiceLayer')?.hidden;
      const preview=document.getElementById('corePrompt')?.textContent.trim()==='ЗАПОМНИ';
      return signal||choice||preview;
    },{timeout:3500});
    const phase=await bossPage.evaluate(()=>({
      choice:!document.getElementById('choiceLayer').hidden,
      signal:document.querySelector('.tap-stage').classList.contains('signal')
        && [...document.querySelectorAll('.strike-rune')].some(node=>!node.disabled),
      preview:document.getElementById('corePrompt').textContent.trim()==='ЗАПОМНИ',
      wave:document.getElementById('waveLabel').textContent.trim(),
      prompt:document.getElementById('corePrompt').textContent.trim(),
      target:document.getElementById('bossGlyph').textContent.trim(),
    }));
    if(phase.choice){
      await bossPage.click('.upgrade-card');
      await bossPage.waitForSelector('#choiceLayer[hidden]');
      continue;
    }
    if(phase.preview&&phase.wave.includes('3')){
      if(output)await bossPage.screenshot({path:`${output}/clicker-390-e06-last-name-preview.png`,fullPage:true});
      await bossPage.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:4000});
      const recall=await bossPage.evaluate(()=>({
        prompt:document.getElementById('corePrompt').textContent.trim(),
        center:document.getElementById('bossGlyph').textContent.trim(),
        runes:[...document.querySelectorAll('.strike-rune')].map(node=>node.textContent.trim()),
      }));
      check(recall.prompt==='ПОВТОРИ','e06 deep: last-name recall prompt missing');
      check(!recall.runes.includes(recall.center),'e06 deep: last-name target leaked in center');
      if(output)await bossPage.screenshot({path:`${output}/clicker-390-e06-last-name-recall.png`,fullPage:true});
      lastNameCaptured=true;
      break;
    }
    if(phase.signal){
      if(phase.wave.includes('2')&&!tideCaptured){
        check(['КОРОТКО','ДЛИННО'].includes(phase.prompt),`e06 deep: tide prompt ${phase.prompt}`);
        if(output)await bossPage.screenshot({path:`${output}/clicker-390-e06-tide.png`,fullPage:true});
        tideCaptured=true;
      }
      const clicked=await bossPage.evaluate(()=>{
        const target=document.getElementById('bossGlyph').textContent.trim();
        const button=[...document.querySelectorAll('.strike-rune')]
          .find(node=>node.textContent.trim()===target&&!node.disabled);
        if(!button)return false;
        button.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));
        return true;
      });
      check(clicked,`e06 deep: matching rune ${phase.target} missing`);
      await new Promise(resolve=>setTimeout(resolve,120));
    }
  }
  check(tideCaptured,'e06 deep: tide phase was not reached');
  check(lastNameCaptured,'e06 deep: last-name phase was not reached');
  check(bossErrors.length===0,`e06 deep browser errors ${bossErrors.join(', ')}`);
  await bossPage.close();

  // Ветвь с активным решением не добавляет старую панель способностей:
  // одна компактная кнопка меняет риск и сохраняет мобильную ширину.
  const branchSession='visual-branch-control';
  const branchReset=await fetch(`${base}/__reconstruction/reset`,{
    method:'POST',
    headers:{'content-type':'application/json','x-reconstruction-session':branchSession},
    body:JSON.stringify({
      encounter_id:'e01_two_bells',
      unit_branches:{
        r_red_seam:'seam_forbidden_repeat',
        r_tide_cartographer:'tide_hidden_swap',
      },
      companion_role_id:'guardian',
    }),
  });
  check(branchReset.ok,'branch UI: dev reset failed');
  const branchCompanion=await fetch(`${base}/__reconstruction/companions/role`,{
    method:'POST',
    headers:{'content-type':'application/json','x-reconstruction-session':branchSession},
    body:JSON.stringify({role_id:'guardian'}),
  });
  check(branchCompanion.ok,'branch UI: Guardian selection failed');
  const branchPage=await browser.newPage();
  await branchPage.setViewport({width:320,height:844,deviceScaleFactor:1});
  await branchPage.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),branchSession);
  await branchPage.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
  await branchPage.waitForSelector('#menuLayer:not([hidden])');
  await branchPage.click('#startRunButton');
  await branchPage.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'),{timeout:3000});
  await branchPage.waitForSelector('[data-combat-command="forbidden_toggle"]');
  await branchPage.waitForSelector('[data-combat-command="tide_swap"]');
  await branchPage.waitForSelector('[data-combat-command="companion_guardian_window"]');
  const branchControls=await branchPage.evaluate(()=>{
    const container=document.getElementById('branchControls');
    const runes=document.querySelector('.rune-orbit').getBoundingClientRect();
    const prompt=document.getElementById('coreHint').getBoundingClientRect();
    const buttons=[...container.querySelectorAll('button')].map(node=>{
      const rect=node.getBoundingClientRect();
      return {top:rect.top,height:rect.height,width:rect.width,right:rect.right,bottom:rect.bottom,fontSize:parseFloat(getComputedStyle(node).fontSize)};
    });
    const box=container.getBoundingClientRect();
    return {
      buttons, count:buttons.length, overflow:container.scrollWidth-container.clientWidth,
      gapToRunes:runes.top-box.bottom, gapFromPrompt:Math.min(...buttons.map(item=>item.top))-prompt.bottom,
      viewport:innerWidth,
    };
  });
  check(branchControls.count===3,`branch UI: expected three simultaneous controls, got ${branchControls.count}`);
  check(branchControls.buttons.every(item=>item.height>=44&&item.fontSize>=10),`branch UI: controls are not readable tap targets ${JSON.stringify(branchControls.buttons)}`);
  check(branchControls.overflow<=0,`branch UI: hidden horizontal controls ${branchControls.overflow}px`);
  check(Math.max(...branchControls.buttons.map(item=>item.top))-Math.min(...branchControls.buttons.map(item=>item.top))<=1,'branch UI: simultaneous controls wrapped into the target prompt');
  check(branchControls.gapFromPrompt>=4,`branch UI: controls cover the central instruction by ${branchControls.gapFromPrompt}px`);
  check(branchControls.gapToRunes>=0&&branchControls.gapToRunes<=18,`branch UI: controls are too far from runes ${branchControls.gapToRunes}px`);
  if(output)await branchPage.screenshot({path:`${output}/clicker-320-multi-skills-ready.png`,fullPage:true});
  await branchPage.evaluate(()=>document.querySelector('[data-combat-command="forbidden_toggle"]')?.click());
  await branchPage.waitForSelector('[data-combat-command="forbidden_toggle"].risk-on',{timeout:5000});
  const branchOverflow=await branchPage.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
  check(branchOverflow<=0,`branch UI: overflow ${branchOverflow}px`);
  await branchPage.close();

  const vowSession='visual-vow-decision';
  const vowReset=await fetch(`${base}/__reconstruction/reset`,{
    method:'POST',
    headers:{'content-type':'application/json','x-reconstruction-session':vowSession},
    body:JSON.stringify({
      encounter_id:'e01_two_bells',
      unit_branches:{r_oath_bell:'bell_broken_vow'},
    }),
  });
  check(vowReset.ok,'vow UI: dev reset failed');
  const vowPage=await browser.newPage();
  await vowPage.setViewport({width:390,height:844,deviceScaleFactor:1});
  await vowPage.evaluateOnNewDocument(key=>sessionStorage.setItem('reconstruction-preview-session',key),vowSession);
  await vowPage.goto(`${base}/static/reconstruction-lab.html`,{waitUntil:'domcontentloaded'});
  await vowPage.click('#startRunButton');
  await vowPage.waitForFunction(()=>document.querySelector('.tap-stage')?.classList.contains('signal'));
  await vowPage.evaluate(()=>{
    const target=document.getElementById('bossGlyph').textContent.trim();
    const wrong=[...document.querySelectorAll('.strike-rune')]
      .find(node=>node.textContent.trim()!==target&&!node.disabled);
    wrong.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));
  });
  await vowPage.waitForSelector('[data-combat-command="vow_keep"]');
  const vowModals=await vowPage.evaluate(()=>
    ['menuLayer','pauseLayer','choiceLayer','resultLayer']
      .filter(id=>!document.getElementById(id).hidden));
  check(vowModals.join(',')==='choiceLayer',`vow UI: wrong modal ${vowModals.join(',')}`);
  await vowPage.click('[data-combat-command="vow_keep"]');
  await vowPage.waitForSelector('#choiceLayer[hidden]');
  check(await vowPage.$eval('#menuLayer',node=>node.hidden),'vow UI: returned to menu instead of battle');
  await vowPage.close();

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
      const signal=document.querySelector('.tap-stage')?.classList.contains('signal')
        && [...document.querySelectorAll('.strike-rune')].some(node=>!node.disabled);
      const choice=!document.querySelector('#choiceLayer')?.hidden;
      const result=!document.querySelector('#resultLayer')?.hidden;
      return signal||choice||result;
    },{timeout:3500});
    const phase=await play.evaluate(()=>({
      result:!document.querySelector('#resultLayer').hidden,
      choice:!document.querySelector('#choiceLayer').hidden,
      signal:document.querySelector('.tap-stage').classList.contains('signal')
        && [...document.querySelectorAll('.strike-rune')].some(node=>!node.disabled),
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
