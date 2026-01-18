/**
 * Service Worker for Progressive Web App (PWA)
 * Handles offline support, caching, background sync
 */

const CACHE_VERSION = 'iesa-v1';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DYNAMIC_CACHE = `${CACHE_VERSION}-dynamic`;
const API_CACHE = `${CACHE_VERSION}-api`;

// Assets to cache on install
const STATIC_ASSETS = [
  '/',
  '/static/css/variables.css',
  '/static/css/base.css',
  '/static/css/layout.css',
  '/static/css/components.css',
  '/static/css/pages.css',
  '/static/css/utilities.css',
  '/static/css/responsive.css',
  '/static/css/toast-notifications.css',
  '/static/css/page-transitions.css',
  '/static/css/skeleton-loading.css',
  '/static/css/smooth-scroll.css',
  '/static/css/parallax.css',
  '/static/css/card-animations.css',
  '/static/css/infinite-scroll.css',
  '/static/css/advanced-filters.css',
  '/static/css/lazy-loading.css',
  '/static/css/touch-gestures.css',
  '/static/css/form-validation.css',
  '/static/css/form-enhancements.css',
  '/static/js/mobile-interactions.js',
  '/static/js/htmx.min.js',
  '/static/js/page-transitions.js',
  '/static/js/skeleton-loading.js',
  '/static/js/smooth-scroll.js',
  '/static/js/parallax.js',
  '/static/js/card-animations.js',
  '/static/js/infinite-scroll.js',
  '/static/js/advanced-filters.js',
  '/static/js/lazy-loading.js',
  '/static/js/touch-gestures.js',
  '/static/js/pull-to-refresh.js',
  '/static/js/form-validation.js',
  '/static/js/form-enhancements.js'
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      console.log('📦 Caching static assets...');
      return cache.addAll(STATIC_ASSETS).catch((error) => {
        console.warn('⚠️ Failed to cache some assets:', error);
        // Continue even if some assets fail
        return Promise.resolve();
      });
    }).then(() => {
      self.skipWaiting();
    })
  );
});

// Activate event - clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== STATIC_CACHE && 
              cacheName !== DYNAMIC_CACHE && 
              cacheName !== API_CACHE) {
            console.log('🗑️ Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      self.clients.claim();
    })
  );
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip cross-origin requests
  if (url.origin !== location.origin) {
    return;
  }

  // API requests - network first, cache fallback
  if (url.pathname.startsWith('/api/') || 
      url.pathname.includes('.json')) {
    event.respondWith(networkFirstStrategy(request, API_CACHE));
    return;
  }

  // HTML pages - network first with fallback
  if (request.method === 'GET' && 
      (request.headers.get('accept')?.includes('text/html') ||
       url.pathname === '/' ||
       !url.pathname.includes('.'))) {
    event.respondWith(networkFirstStrategy(request, DYNAMIC_CACHE));
    return;
  }

  // Static assets - cache first, network fallback
  if (request.method === 'GET') {
    event.respondWith(cacheFirstStrategy(request, DYNAMIC_CACHE));
    return;
  }
});

// Cache first strategy (for static assets)
async function cacheFirstStrategy(request, cacheName) {
  try {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }

    const response = await fetch(request);
    if (!response || response.status !== 200 || response.type === 'error') {
      return response;
    }

    const cache = await caches.open(cacheName);
    cache.put(request, response.clone());
    return response;
  } catch (error) {
    console.error('❌ Cache first strategy failed:', error);
    return caches.match(request) || 
           new Response('Offline - Resource not available', { 
             status: 503,
             statusText: 'Service Unavailable'
           });
  }
}

// Network first strategy (for pages and API)
async function networkFirstStrategy(request, cacheName) {
  try {
    const response = await fetch(request);
    
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
      return response;
    }
    
    return caches.match(request) || response;
  } catch (error) {
    console.error('❌ Network first strategy failed:', error);
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }

    // Return offline page if available
    if (request.mode === 'navigate') {
      return caches.match('/offline/');
    }

    return new Response('Offline', { 
      status: 503,
      statusText: 'Service Unavailable'
    });
  }
}

// Handle messages from client
self.addEventListener('message', (event) => {
  if (event.data?.action === 'SKIP_WAITING') {
    self.skipWaiting();
  }

  if (event.data?.action === 'CLEAR_CACHE') {
    caches.keys().then((cacheNames) => {
      Promise.all(
        cacheNames.map((cacheName) => caches.delete(cacheName))
      ).then(() => {
        console.log('✅ All caches cleared');
      });
    });
  }

  if (event.data?.action === 'CACHE_URLS') {
    const { urls } = event.data;
    caches.open(DYNAMIC_CACHE).then((cache) => {
      cache.addAll(urls);
    });
  }
});

// Background sync
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-posts') {
    event.waitUntil(syncPosts());
  }
});

async function syncPosts() {
  try {
    const cache = await caches.open(DYNAMIC_CACHE);
    const requests = await cache.keys();
    
    for (const request of requests) {
      if (request.url.includes('/posts/')) {
        try {
          const response = await fetch(request);
          cache.put(request, response);
        } catch (error) {
          console.error('Failed to sync:', request.url);
        }
      }
    }
  } catch (error) {
    console.error('Background sync failed:', error);
  }
}

// Periodic background sync (notifications)
self.addEventListener('periodicsync', (event) => {
  if (event.tag === 'check-notifications') {
    event.waitUntil(checkNotifications());
  }
});

async function checkNotifications() {
  try {
    const response = await fetch('/api/notifications/unread/');
    if (!response.ok) return;

    const data = await response.json();
    if (data.count > 0) {
      self.registration.showNotification('IESA', {
        body: `У вас ${data.count} новые уведомления`,
        icon: '/static/img/icon-192x192.png',
        badge: '/static/img/badge-72x72.png',
        tag: 'notifications',
        requireInteraction: false
      });
    }
  } catch (error) {
    console.error('Failed to check notifications:', error);
  }
}

// Push notifications
self.addEventListener('push', (event) => {
  const data = event.data?.json() || {
    title: 'IESA',
    body: 'Новое уведомление'
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'IESA', {
      body: data.body || 'Новое уведомление',
      icon: data.icon || '/static/img/icon-192x192.png',
      badge: '/static/img/badge-72x72.png',
      tag: data.tag || 'notification',
      data: data.data || {}
    })
  );
});

// Notification click
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const urlToOpen = event.notification.data.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Check if page is already open
        for (let i = 0; i < clientList.length; i++) {
          const client = clientList[i];
          if (client.url === urlToOpen && 'focus' in client) {
            return client.focus();
          }
        }
        // Open new window if not found
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen);
        }
      })
  );
});
