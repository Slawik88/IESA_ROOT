/**
 * IESA Sport Service Worker — 6e: offline caching strategy
 * Cache-first: статика (CSS/JS/шрифты)
 * Network-first: HTML-страницы, API
 * Stale-while-revalidate: профили, уведомления
 * Offline fallback: /offline/
 */

const CACHE_VERSION = 'iesa-v3';
const STATIC_CACHE  = `${CACHE_VERSION}-static`;
const DYNAMIC_CACHE = `${CACHE_VERSION}-dynamic`;

/* Только реально существующие файлы */
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

/* Страницы для stale-while-revalidate */
const SWR_PATTERNS = [
  /^\/auth\/profile\//,
  /^\/notifications\//,
  /^\/blog\/$/,
  /^\/$/,
];

/* Пути которые никогда не кэшируем */
const NO_CACHE_PATTERNS = [
  /^\/auth\/partner\//,          // партнёрский портал (всегда свежий)
  /^\/admin\//,
  /^\/auth\/login\//,
  /^\/auth\/logout\//,
  /\/api\//,
  /\.json$/,
];

// ── Install ──────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => Promise.resolve());
    }).then(() => self.skipWaiting())
  );
});

// ── Activate ─────────────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => {
        if (k !== STATIC_CACHE && k !== DYNAMIC_CACHE) return caches.delete(k);
      }))
    ).then(() => self.clients.claim())
  );
});

// ── Fetch ─────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  /* Только GET, только наш origin */
  if (req.method !== 'GET' || url.origin !== location.origin) return;

  /* Не кэшируем admin/api/auth-pages */
  if (NO_CACHE_PATTERNS.some((p) => p.test(url.pathname))) return;

  /* Статические файлы → cache-first */
  if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/media/')) {
    event.respondWith(cacheFirst(req));
    return;
  }

  /* Stale-while-revalidate для профилей и уведомлений */
  if (SWR_PATTERNS.some((p) => p.test(url.pathname))) {
    event.respondWith(staleWhileRevalidate(req));
    return;
  }

  /* Остальные HTML-страницы → network-first с offline fallback */
  event.respondWith(networkFirst(req));
});

// ── Стратегии ─────────────────────────────────────────────────────

async function cacheFirst(req) {
  const cached = await caches.match(req);
  if (cached) return cached;
  try {
    const resp = await fetch(req);
    if (resp.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(req, resp.clone());
    }
    return resp;
  } catch {
    return cached || new Response('', { status: 503 });
  }
}

async function networkFirst(req) {
  try {
    const resp = await fetch(req);
    if (resp.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(req, resp.clone());
    }
    return resp;
  } catch {
    const cached = await caches.match(req);
    if (cached) return cached;
    /* Offline fallback для навигационных запросов */
    if (req.mode === 'navigate') {
      const offline = await caches.match('/offline/');
      if (offline) return offline;
    }
    return new Response('Offline', { status: 503 });
  }
}

async function staleWhileRevalidate(req) {
  const cache  = await caches.open(DYNAMIC_CACHE);
  const cached = await cache.match(req);
  const fetchPromise = fetch(req).then((resp) => {
    if (resp.ok) cache.put(req, resp.clone());
    return resp;
  }).catch(() => null);
  return cached || fetchPromise;
}

// ── Messages ──────────────────────────────────────────────────────
self.addEventListener('message', (event) => {
  if (event.data?.action === 'SKIP_WAITING') self.skipWaiting();
  if (event.data?.action === 'CLEAR_CACHE') {
    caches.keys().then((k) => Promise.all(k.map((n) => caches.delete(n))));
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
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if (c.url === url && 'focus' in c) return c.focus();
      }
      return clients.openWindow(url);
    })
  );
});
