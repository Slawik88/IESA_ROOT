/**
 * Cache public static assets only. HTML/HTMX/media may contain account data,
 * so they always use the network; navigations get a generic offline page.
 */
const CACHE_VERSION = 'iesa-v7';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const OFFLINE_URL = '/offline/';

const STATIC_ASSETS = [
  '/static/css/variables.css',
  '/static/css/base.css',
  '/static/css/layout.css',
  '/static/css/components.css',
  '/static/css/pages.css',
  '/static/css/utilities.css',
  '/static/css/responsive.css',
  '/static/css/animations.css',
  '/static/css/profile-page.css',
  '/static/css/dashboard.css',
  '/static/css/bootstrap.min.css',
  '/static/js/htmx.min.js',
  '/static/js/bootstrap.bundle.min.js',
  '/static/js/touch-gestures.js',
  '/static/js/scroll-animations.js',
];

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    // A missing optional asset must not discard every successful download.
    await Promise.allSettled([...STATIC_ASSETS, OFFLINE_URL].map(url => cache.add(url)));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key.startsWith('iesa-') && key !== STATIC_CACHE)
      .map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheStatic(req, event));
  } else if (req.mode === 'navigate') {
    event.respondWith(navigate(req));
  }
  // HTMX, APIs and protected media use normal browser network handling.
});

async function cacheStatic(req, event) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(req);
  // Manifest filenames contain a content hash and are immutable. Plain names
  // must refresh in the background so deployments do not leave old JS/CSS.
  if (cached) {
    if (!/\.[a-f0-9]{12}\./i.test(new URL(req.url).pathname)) {
      event.waitUntil(refreshStatic(cache, req).catch(() => {}));
    }
    return cached;
  }
  try {
    return await refreshStatic(cache, req);
  } catch {
    return new Response('', { status: 503 });
  }
}

async function refreshStatic(cache, req) {
  const response = await fetch(req, { cache: 'no-cache' });
  if (response.ok && !response.redirected && !/no-store|private/i.test(response.headers.get('Cache-Control') || '')) {
    try { await cache.put(req, response.clone()); } catch { /* Storage may be full. */ }
  }
  return response;
}

async function navigate(req) {
  try {
    return await fetch(req);
  } catch {
    const cache = await caches.open(STATIC_CACHE);
    return await cache.match(OFFLINE_URL) || new Response('Offline', {
      status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    });
  }
}

self.addEventListener('message', event => {
  if (event.data?.action === 'SKIP_WAITING') self.skipWaiting();
  if (event.data?.action === 'CLEAR_CACHE') {
    event.waitUntil(caches.keys().then(keys => Promise.all(
      keys.filter(key => key.startsWith('iesa-')).map(key => caches.delete(key))
    )));
  }
});

// ── Push уведомления (PWA) ────────────────────────────────────────
self.addEventListener('push', (event) => {
  const data = event.data?.json() || { title: 'IESA Sport', body: 'New notification' };
  event.waitUntil(
    self.registration.showNotification(data.title || 'IESA Sport', {
      body: data.body || '',
      icon: data.icon || '/static/img/icon-192x192.png',
      badge: '/static/img/badge-72x72.png',
      tag: data.tag || 'iesa-notification',
      data: data.data || {},
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  let target;
  try { target = new URL(event.notification.data?.url || '/', self.location.origin); }
  catch { target = new URL('/', self.location.origin); }
  const url = target.origin === self.location.origin ? target.href : self.location.origin + '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if (c.url === url && 'focus' in c) return c.focus();
      }
      return clients.openWindow(url);
    })
  );
});
