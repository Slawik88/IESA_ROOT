// Снимки экранов мини-приложения со стенда (tools/ui_stand.py): MOCK=mocks/x.json node app_shots.cjs <ссылка входа> <папка> имя=js ...
// name с суффиксом «+full» — снимок всей страницы (для прокрутки в ролике)
const fs=require('fs'),path=require('path');const {chromium}=require(path.join(require('child_process').execSync('npm root -g').toString().trim(),'playwright'));
const CLEAN=`for (const n of document.querySelectorAll('span,div,a,b')) { if (n.children.length<=2 && /^(🛠\\s*)?(Разработчик|Тестер)$/.test(n.textContent.trim())) n.style.display='none'; }
  for (const b of document.querySelectorAll('button,a,div')) { if (b.children.length<=3 && b.textContent.trim()==='Биржа' && b.closest('nav,[class*=dock],[class*=tab]')) b.style.display='none'; }`;
(async()=>{
  const [url,out,...jobs]=process.argv.slice(2);
  const b=await chromium.launch();
  const ctx=await b.newContext({viewport:{width:390,height:844},deviceScaleFactor:1080/390,isMobile:true,hasTouch:true});
  const mocks=process.env.MOCK?JSON.parse(fs.readFileSync(process.env.MOCK,'utf8')):{};
  await ctx.route('**/*',r=>{const u=r.request().url();const k=Object.keys(mocks).filter(k=>u.includes(k)).sort((a,b)=>b.length-a.length)[0];
    return k?r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(mocks[k])}):r.continue();});
  const p=await ctx.newPage(); p.on('pageerror',e=>console.log('ERR',e.message));
  await p.goto(url); await p.waitForTimeout(4000); const home=p.url();
  for(const j of jobs){const i=j.indexOf('=');let name=j.slice(0,i);const js=j.slice(i+1);const full=name.endsWith('+full');name=name.replace('+full','');
    try{ await p.goto(home); await p.waitForTimeout(2500); if(js) await p.evaluate(js); await p.waitForTimeout(2600); await p.evaluate(CLEAN); if(full) await p.evaluate(()=>{for(const e of document.querySelectorAll('*')){if(getComputedStyle(e).position==='fixed')e.style.visibility='hidden';}});
      await p.screenshot({path:`${out}/${name}.png`,fullPage:full}); console.log('ok',name);}catch(e){console.log('fail',name,e.message.slice(0,200));}}
  await b.close();})();
