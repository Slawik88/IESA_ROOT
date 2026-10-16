'use strict';
// Local synthetic parent with the production bridge and real opaque game frame.
// Run: NODE_PATH=<directory containing playwright> node tools/test_pet_practice_browser.cjs
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const staticDir = path.join(__dirname, '../FastAPI/static');
const read = name => fs.readFileSync(path.join(staticDir, name), 'utf8');
const render = read('app.40.js').match(/function _trRender\(\) \{[\s\S]*?\n\}/)[0];
const setup = `
 const _sysFlags={pets_v2:true}, SK='session', UK='user';
 let _uid=101,_activePage='pets',credential='fake-A',delay=0;
 const _tr={view:'hub',me:{pets:[{id:7,name:'Лиса',icon:'🦊',energy:0,run_id:'busy'}]}},_TR_VIEWS={hub:()=>'<p>Питомцы</p>'};
 const calls=[],el=id=>document.getElementById(id),hdrs=()=>({authorization:credential}),_trE=x=>String(x).replace(/[<>&"']/g,'');
 const v3Head=t=>'<h2>'+t+'</h2>',v3EnterSync=()=>{};
 async function api(url){calls.push(url);const owner=_uid,pets=structuredClone(_tr.me?.pets||[{id:7,name:'Лиса',icon:'🦊'}]);if(delay)await new Promise(r=>setTimeout(r,delay));return url==='/profile/me'?{user_id:owner}:{pets};}
 function trailGo(view){_tr.view=view;_trRender();}
 function trailBack(){_tr.view='hub';_trRender();}
 function openTrail(){_tr.view='hub';_trRender();}
 ${render}
`;
const parentHtml = `<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><div id="login-ov" class="hidden"></div><main id="pg-pets"></main><script>${setup}</script><script src="/bridge.js"></script><script>window.qa={start:()=>trailPractice(7),refresh:()=>_trRender(),exit:()=>trailBack(),inspect:()=>({key:_ppContext?.key,gen:_ppGeneration,snapshot:_ppContext?.snapshot,calls:[...calls],valid:!!_ppContext,token:_ppContext?.token,height:_ppContext?.frame?.style.height}),identity:()=>{credential='fake-B';_uid=202;},login:()=>el('login-ov').classList.remove('hidden'),delay:x=>delay=x};const BASE=location.origin;trailPractice(7);</script></html>`;
async function main() {
 const csp = fs.readFileSync(path.join(__dirname,'../FastAPI/main.py'),'utf8').match(/"Content-Security-Policy": "([^"]+)"/)[1];
 const server = http.createServer((req,res) => {
  const url = new URL(req.url,'http://localhost');
  if(url.pathname==='/') {res.setHeader('Content-Type','text/html; charset=utf-8');res.end(parentHtml);return;}
  if(url.pathname==='/bridge.js'){res.setHeader('Content-Type','application/javascript');res.end(read('app.48.js'));return;}
  if(url.pathname==='/pet-practice'){res.setHeader('Content-Type','text/html; charset=utf-8');res.setHeader('Content-Security-Policy',csp);res.end(read('pet-practice.html').replaceAll('{{BASE}}','').replaceAll('{{ASSET_VER}}','test'));return;}
  if(url.pathname==='/favicon.ico'){res.statusCode=204;res.end();return;}
  const name=url.pathname.replace('/static/','');
  if(['pet-practice.css','pet-practice-host.js','pet-practice-game.js'].includes(name)){res.setHeader('Content-Type',name.endsWith('.css')?'text/css':'application/javascript');res.end(read(name));return;}
  res.statusCode=404;res.end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser = await chromium.launch({channel:process.env.PRACTICE_BROWSER || 'msedge',headless:true});
 const page = await browser.newPage({viewport:{width:390,height:844}}), errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 page.on('console',message=>{if(message.type()==='error'&&!message.text().includes('favicon')) errors.push(message.text());});
 const url=`http://127.0.0.1:${server.address().port}/`;
 const ready = async()=>{await page.frameLocator('iframe').locator('#practice-content').waitFor({state:'visible'});return page.frames().find(f=>f.url().includes('/pet-practice'));};
 const check = async()=>page.evaluate(()=>qa.inspect());
 try {
  await page.goto(url);let frame=await ready();
  assert.equal(await frame.evaluate(()=>{try{return localStorage.length}catch(_){return 'blocked'}}),'blocked');
  assert.equal(await frame.evaluate(()=>window.PetPractice.widgetState),null);
  await frame.locator('[data-approach]').selectOption('ruins');
  await frame.locator('[data-depart]').click();
  await page.waitForFunction(()=>qa.inspect().snapshot?.privateContent?.status==='playing');
  const first=await check();assert.equal(first.key,'pv:pet-practice:v1:101:7');
  assert.equal(first.snapshot.privateContent.approach,'ruins');
  const frameIdentity=await page.locator('iframe').evaluate(e=>{e.dataset.probe='preserved';return e.dataset.probe});
  await page.evaluate(()=>qa.refresh());assert.equal(await page.locator('iframe').getAttribute('data-probe'),frameIdentity);
  // A player action has not been saved while enemies are still playing back.
  await frame.locator('#lh-wait').click();
  assert.equal((await check()).snapshot.privateContent.turn,0);
  await page.evaluate(()=>qa.exit()); await page.waitForTimeout(400);
  await page.evaluate(()=>qa.start());frame=await ready();
  assert.equal(await frame.locator('#lh-turn').textContent(),'0');
  await frame.locator('#lh-wait').click();await page.waitForFunction(()=>qa.inspect().snapshot?.privateContent?.turn===1);
  await page.reload();frame=page.frames().find(f=>f.url().includes('/pet-practice'));await page.waitForFunction(()=>qa.inspect().snapshot?.privateContent?.turn===1);
  frame=page.frames().find(f=>f.url().includes('/pet-practice'));await frame.locator('#lh-wait').waitFor();assert.equal(await frame.locator('#lh-turn').textContent(),'1');
  await page.waitForFunction(()=>qa.inspect().height);const height=(await check()).height;await page.waitForTimeout(300);assert.equal((await check()).height,height,'frame height must settle');
  if(process.env.PRACTICE_SCREENSHOT)await page.screenshot({path:process.env.PRACTICE_SCREENSHOT,fullPage:true});
  const stale=await check(); await page.evaluate(()=>qa.identity());
  await frame.evaluate(({token,snapshot})=>parent.postMessage({channel:'pv-practice-v1',type:'save',token,sequence:999,snapshot},'*'),{token:stale.token,snapshot:stale.snapshot});
  await page.waitForFunction(()=>!qa.inspect().valid);
  assert.equal(await page.evaluate(()=>localStorage.getItem('pv:pet-practice:v1:202:7')),null);
  // A delayed response cannot revive a game after account/view change.
  await page.reload();await page.locator('iframe').waitFor();await page.evaluate(()=>{qa.exit();});await page.waitForTimeout(350);
  await page.evaluate(()=>{qa.delay(150);qa.start();qa.identity();});await page.waitForTimeout(250);assert.equal((await check()).valid,false);
  // No persistent storage: play continues with a visible limitation and memory fallback.
  await page.evaluate(()=>localStorage.clear());
  await page.addInitScript(()=>{Storage.prototype.setItem=function(){throw new DOMException('blocked','SecurityError')};});
  await page.goto(url);frame=await ready();await frame.locator('[data-depart]').click();await frame.locator('#practice-notice').waitFor({state:'visible'});
  assert.match(await frame.locator('#practice-notice').textContent(),/Сохранение/);
  await page.evaluate(()=>qa.login());await page.waitForFunction(()=>!qa.inspect().valid);
  assert.ok((await check()).calls.every(x=>['/profile/me','/pets-v2/me'].includes(x)));
  // Synthetic Telegram Web chain: real production CSP, all requests fulfilled locally.
  const nested=await browser.newPage();
  await nested.route('https://practice.invalid/**',async route=>{
   const target=new URL(route.request().url());const response=await route.fetch({url:url.slice(0,-1)+target.pathname+target.search});await route.fulfill({response});
  });
  await nested.route('https://web.telegram.org/**',route=>route.fulfill({contentType:'text/html',body:'<iframe src="https://practice.invalid/" style="width:430px;height:1000px"></iframe>'}));
  await nested.goto('https://web.telegram.org/');
  await nested.frameLocator('iframe').frameLocator('iframe').locator('[data-depart]').waitFor();
  await nested.close();
  assert.deepEqual(errors,[]);
  console.log('Pet practice browser: opaque sandbox/CSP, busy pet, checkpoint boundaries, refresh/reload, identity races, 401 and blocked storage OK');
 } finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(error=>{console.error(error);process.exitCode=1});
