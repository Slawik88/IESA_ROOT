/* Cache game shells and assets only. Never cache authenticated API responses. */
const CACHE='pv-games-{{VERSION}}', ASSETS={{PRECACHE}};
const paths=new Set(ASSETS.map(url=>new URL(url,self.location.origin).pathname));
self.addEventListener('install',event=>event.waitUntil((async()=>{
  const cache=await caches.open(CACHE);
  await Promise.all(ASSETS.map(async url=>{
    const response=await fetch(url,{cache:'reload'});
    if(!response.ok)throw new Error('Game cache incomplete');
    await cache.put(url,response);
  }));
  await self.skipWaiting();
})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{
  for(const key of await caches.keys())if(key.startsWith('pv-games-')&&key!==CACHE)await caches.delete(key);
  await self.clients.claim();
})()));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(event.request.method!=='GET'||url.origin!==self.location.origin||!paths.has(url.pathname))return;
  event.respondWith((async()=>{
    const cache=await caches.open(CACHE);
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),2500);
    try{const response=await fetch(event.request,{signal:controller.signal});if(response.ok)await cache.put(event.request,response.clone());else if(response.status>=500){const saved=await cache.match(event.request,{ignoreSearch:true});if(saved)return saved;}return response;}
    catch(error){const saved=await cache.match(event.request,{ignoreSearch:true});if(saved)return saved;throw error;}
    finally{clearTimeout(timeout);}
  })());
});
