// Cold photos appear in existing rows, are shared by reference, and obey VIP display rights.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const src=fs.readFileSync(path.join(__dirname,'../FastAPI/static/game-board-v3.js'),'utf8'),photo='data:image/jpeg;base64,AAAA',ref='abcdefghijklmnop';
let calls=0;
const ctx=vm.createContext({window:{},console,setTimeout:f=>{f();return 1},document:{createElement:()=>({})},api:async()=>{calls++;return {vip:true,avatar:photo}}});
vm.runInContext(src,ctx);
const rendered=ctx.window.gameWhoV3({display_name:'<admin>',profile_ref:ref,is_vip:true});
assert.match(rendered,/&lt;admin&gt;/);assert.match(rendered,/data-lb-avatar/);
assert.doesNotMatch(ctx.window.gameWhoV3({display_name:'Plain',profile_ref:ref,is_vip:false,avatar:photo}),/data:image/);
const node=()=>({isConnected:true,dataset:{lbAvatar:ref},images:[],querySelector(){return this.images[0]},append(img){this.images.push(img)}});
const a=node(),b=node(),host={isConnected:true,querySelectorAll:()=>[a,b]};
(async()=>{
 ctx.window.hydrateLeaderboardAvatars(host);ctx.window.hydrateLeaderboardAvatars(host);
 await new Promise(setImmediate);await new Promise(setImmediate);
 assert.equal(calls,1,'same player shares the request');assert.equal(a.images.length,1);assert.equal(b.images.length,1);assert.equal(a.images[0].src,photo);
 const late=node();late.dataset.lbAvatar='qrstuvwxyzabcdef';let done;ctx.api=()=>new Promise(resolve=>{done=resolve});
 const old={isConnected:true,querySelectorAll:()=>[late]};ctx.window.hydrateLeaderboardAvatars(old);old.isConnected=false;done({vip:true,avatar:photo});
 await new Promise(setImmediate);assert.equal(late.images.length,0,'late response cannot change a detached board');
 assert.doesNotMatch(ctx.window.gameWhoV3({display_name:'Unsafe',is_vip:true,avatar:'data:image/svg+xml;base64,AAAA'}),/<img/);
 // Standalone pages use fetch rather than the shell's api(). HTTP failures must retry.
 for(const status of [401,429,500]){
   let tries=0;
   const offline=vm.createContext({window:{GameMode:{headers:()=>({'x-init-data':'current'})}},Date,Promise,AbortController,clearTimeout(){},setTimeout:fn=>{fn();return 1},
     document:{body:{dataset:{}},createElement:()=>({})},fetch:async(url,options)=>{
       assert.equal(options.headers['x-init-data'],'current');tries++;
       return tries===1?{ok:false,status}:{ok:true,json:async()=>({vip:true,avatar:photo})};
     }});
   vm.runInContext(src,offline);
   const row=node(),table={isConnected:true,querySelectorAll:()=>[row]};
   offline.window.hydrateLeaderboardAvatars(table);
   await new Promise(setImmediate);await new Promise(setImmediate);
   assert.equal(tries,2,`HTTP ${status} is retried`);assert.equal(row.images[0].src,photo);
 }
 console.log('PASS: shared cold avatar hydration, escaped names, VIP display gate, safe image types and detached-board guard');
})().catch(e=>{console.error(e);process.exitCode=1});
