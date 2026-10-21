// Веб-админка владельца чата на демо-данных (как tools/admin_stand.py --owner): node admin_shots.cjs <папка>
const fs=require('fs'),path=require('path');const {chromium}=require(path.join(require('child_process').execSync('npm root -g').toString().trim(),'playwright'));
const STATIC=path.join(__dirname,'..','..','..','FastAPI','static','bot-admin')+path.sep;
const read=n=>fs.readFileSync(STATIC+n,'utf8');
const ban=(id,u,r,until)=>({id,username:u,reason:r,until});
const CHAT={id:-1004,title:'ФЛУД 18:00 ☕',closed:false,max_warnings:3,bot:{is_admin:true,can_moderate:true},members:2431,
 sanctions:{bans:[ban(901,'krypta_tut','спам ссылками',null),ban(902,'flood_bot77','реклама','2026-10-28T10:00:00+00:00')],
   mutes:[{id:903,username:'tema_frog',until:'2026-10-21T22:00:00+00:00'},{id:904,username:'caps_lock_king',until:'2026-10-22T12:00:00+00:00'}],
   warns:[{id:905,username:'egor_zz',count:2},{id:906,username:'sleepy_bear',count:1}]}};
const ROUTES={'/me':[403,{detail:'Админка доступна только персоналу бота.'}],'/owner/me':{user_id:5001,kind:'owner',max_chats:10,chat_actions:[],member_actions:[],
  chats:[{id:-1004,title:CHAT.title},{id:-1001,title:'Флудилка 🌚'}]},'/owner/chat/-1004':CHAT,'/badges':{}};
(async()=>{
  const out=process.argv[2];
  const b=await chromium.launch();
  const ctx=await b.newContext({viewport:{width:390,height:844},deviceScaleFactor:1080/390,isMobile:true,hasTouch:true});
  await ctx.addInitScript(`localStorage.setItem('pv_admin_prefs', JSON.stringify({theme:'dark'}))`);
  await ctx.route('**/*',r=>{const u=new URL(r.request().url());
    if(u.host!=='stand.local') return r.abort();
    if(u.pathname.startsWith('/bot-admin/api/')){const k=u.pathname.slice('/bot-admin/api'.length);const v=ROUTES[k];
      if(!v) return r.fulfill({status:404,contentType:'application/json',body:'{"detail":"нет"}'});
      const [st,body]=Array.isArray(v)?v:[200,v];return r.fulfill({status:st,contentType:'application/json',body:JSON.stringify(body)});}
    const name=u.pathname.split('/').pop();
    if(name.startsWith('admin')&&name.endsWith('.js')) return r.fulfill({status:200,contentType:'text/javascript',body:read(name)});
    if(name.startsWith('admin')&&name.endsWith('.css')) return r.fulfill({status:200,contentType:'text/css',body:read(name)});
    return r.fulfill({status:200,contentType:'text/html',body:read('index.html').replaceAll('{{BASE}}','http://stand.local').replaceAll('{{VER}}','stand')});});
  const p=await ctx.newPage(); p.on('pageerror',e=>console.log('ERR',e.message));
  await p.goto('http://stand.local/bot-admin/'); await p.waitForTimeout(2500);
  await p.evaluate(()=>{for(const e of document.querySelectorAll('*')){if(getComputedStyle(e).position==='fixed')e.style.visibility='hidden';}});
  await p.screenshot({path:out+'/admin_owner.png',fullPage:true});
  console.log('ok');
  await b.close();})();
