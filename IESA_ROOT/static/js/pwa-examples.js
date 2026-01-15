/**
 * TIER 6: PWA & Offline Support Usage Examples
 * Service Worker, offline mode, install prompts, background sync
 */

/* ============================================================
   1. HTML STRUCTURE FOR PWA FEATURES
   ============================================================ */

HTML_PWA_STRUCTURE = `
<!DOCTYPE html>
<html>
<head>
  <!-- ... other meta tags ... -->
  
  <!-- PWA Manifest (already in base.html) -->
  <link rel="manifest" href="{% static 'manifest.json' %}">
  
  <!-- PWA Theme Color -->
  <meta name="theme-color" content="#3b82f6">
  
  <!-- Apple Touch Icon -->
  <link rel="apple-touch-icon" href="{% static 'img/icon-192x192.png' %}">
  
  <!-- PWA CSS (already in base.html) -->
  <link rel="stylesheet" href="{% static 'css/pwa.css' %}">
</head>
<body>
  <!-- PWA Install Button (optional - auto-shown when installable) -->
  <button id="pwa-install-button" aria-label="Установить приложение">
    <i class="fas fa-download"></i>
    <span>Установить приложение</span>
  </button>

  <!-- Offline Indicator (auto-shown when offline) -->
  <div id="offline-indicator">
    📡 Без интернета - работа в режиме оффлайн
  </div>

  <!-- PWA Manager Script (already in base.html) -->
  <script src="{% static 'js/pwa-manager.js' %}"></script>
  
  <script>
    // Access PWA Manager
    const pwaManager = window.PWAManager;
    
    // Check if online
    if (pwaManager.isAppOnline()) {
      console.log('✅ Online');
    } else {
      console.log('⚠️ Offline');
    }
    
    // Listen for install button
    document.getElementById('pwa-install-button')?.addEventListener('click', () => {
      pwaManager.promptInstall();
    });
    
    // Manually trigger update check
    // pwaManager.serviceWorkerReg?.update();
    
    // Clear cache if needed
    // pwaManager.clearCache();
    
    // Cache specific URLs
    // pwaManager.cacheUrls(['/api/data', '/images/important.jpg']);
  </script>
</body>
</html>
`;

/* ============================================================
   2. SERVICE WORKER FEATURES
   ============================================================ */

SERVICE_WORKER_FEATURES = `
// Service Worker Features:

1. **Static Asset Caching**
   - Кэширует CSS, JS, шрифты при установке
   - Использует cache-first стратегию для быстрого доступа

2. **Network First Strategy**
   - HTML страницы: сначала сеть, потом кэш
   - Гарантирует свежий контент при интернете

3. **API Caching**
   - Кэширует API ответы
   - Позволяет работать с данными в офлайне

4. **Offline Fallback**
   - Возвращает кэшированный контент в офлайне
   - Показывает 503 для недоступного контента

5. **Background Sync**
   - Синхронизирует данные при возвращении онлайн
   - Автоматически отправляет отложенные запросы

6. **Push Notifications**
   - Получает push-уведомления
   - Работает даже если приложение закрыто

7. **Periodic Background Sync**
   - Периодически проверяет уведомления
   - Отправляет локальные уведомления

8. **Update Checking**
   - Проверяет обновления сервис-воркера
   - Показывает пользователю уведомление об обновлении
`;

/* ============================================================
   3. OFFLINE PAGE EXAMPLE
   ============================================================ */

HTML_OFFLINE_PAGE = `
<!-- /offline/ or templates/offline.html -->

<div class="offline-page">
  <div class="offline-page-icon">📡</div>
  
  <h1 class="offline-page-title">Нет соединения с интернетом</h1>
  
  <p class="offline-page-description">
    Похоже, вы потеряли соединение с интернетом.
    Но не волнуйтесь, вы можете использовать приложение в режиме оффлайн.
  </p>
  
  <div class="offline-page-suggestions">
    <h3>Вы можете:</h3>
    <ul>
      <li>Читать сохраненные посты</li>
      <li>Просматривать профили</li>
      <li>Просматривать галерею</li>
      <li>Работать с сохраненными данными</li>
    </ul>
  </div>
  
  <button class="offline-page-button" onclick="location.reload()">
    Попробовать снова
  </button>
</div>
`;

/* ============================================================
   4. PWA JAVASCRIPT API REFERENCE
   ============================================================ */

PWA_API = `
// ===== PWAManager API =====

// Инициализация (автоматическая)
const pwaManager = window.PWAManager;

// Проверить статус интернета
const isOnline = pwaManager.isAppOnline();

// Установить приложение (для кнопки "Установить")
pwaManager.promptInstall();

// Очистить весь кэш
pwaManager.clearCache();

// Кэшировать определенные URL
pwaManager.cacheUrls([
  '/api/posts/',
  '/api/users/me/',
  '/images/logo.png'
]);

// Обновить сервис-воркер
pwaManager.updateServiceWorker();

// Свойства
pwaManager.isOnline           // Boolean - статус интернета
pwaManager.serviceWorkerReg   // ServiceWorkerRegistration
pwaManager.deferredPrompt     // BeforeInstallPrompt event
`;

/* ============================================================
   5. DJANGO BACKEND SETUP
   ============================================================ */

DJANGO_SETUP = `
# urls.py
from django.views.generic import TemplateView

urlpatterns = [
    # ... other urls ...
    
    # PWA offline page
    path('offline/', TemplateView.as_view(template_name='offline.html'), name='offline'),
    
    # API for push notifications
    path('api/notifications/subscribe/', 
         views.subscribe_to_notifications, name='subscribe_notifications'),
    path('api/notifications/unread/', 
         views.get_unread_notifications, name='unread_notifications'),
]

# settings.py
INSTALLED_APPS = [
    # ... other apps ...
    'django_push_notifications',  # For push notifications
]

# Middleware for offline support
MIDDLEWARE = [
    # ... other middleware ...
    'middleware.OfflineMiddleware',  # Custom middleware
]
`;

/* ============================================================
   6. SERVICE WORKER MESSAGE HANDLING
   ============================================================ */

SERVICE_WORKER_MESSAGES = `
// Send messages to service worker

// Clear all caches
navigator.serviceWorker.controller?.postMessage({
  action: 'CLEAR_CACHE'
});

// Cache specific URLs
navigator.serviceWorker.controller?.postMessage({
  action: 'CACHE_URLS',
  urls: ['/api/posts/', '/api/users/']
});

// Listen for messages from service worker
navigator.serviceWorker.addEventListener('message', (event) => {
  if (event.data.type === 'SYNC_COMPLETE') {
    console.log('✅ Background sync completed');
  }
});
`;

/* ============================================================
   7. PUSH NOTIFICATIONS SETUP
   ============================================================ */

PUSH_NOTIFICATIONS = `
// Subscribe to push notifications

async function subscribeToPush() {
  const registration = await navigator.serviceWorker.ready;
  
  try {
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: getPublicKey() // From Django
    });
    
    // Send subscription to server
    await fetch('/api/notifications/subscribe/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify(subscription)
    });
    
    console.log('✅ Subscribed to push notifications');
  } catch (error) {
    console.error('❌ Failed to subscribe:', error);
  }
}

// Request notification permission first
if (Notification.permission === 'granted') {
  subscribeToPush();
} else if (Notification.permission !== 'denied') {
  Notification.requestPermission().then((permission) => {
    if (permission === 'granted') {
      subscribeToPush();
    }
  });
}
`;

/* ============================================================
   8. BACKGROUND SYNC SETUP
   ============================================================ */

BACKGROUND_SYNC = `
// Trigger background sync

async function syncData() {
  const registration = await navigator.serviceWorker.ready;
  
  try {
    await registration.sync.register('sync-posts');
    console.log('✅ Background sync scheduled');
  } catch (error) {
    console.error('❌ Failed to register sync:', error);
    // Fallback: sync immediately
    await fetch('/api/sync/', { method: 'POST' });
  }
}

// Called automatically when app comes online
window.addEventListener('online', () => {
  syncData();
});

// Periodic background sync (every 12 hours)
async function setupPeriodicSync() {
  const registration = await navigator.serviceWorker.ready;
  
  try {
    await registration.periodicSync.register('check-notifications', {
      minInterval: 12 * 60 * 60 * 1000 // 12 hours
    });
    console.log('✅ Periodic sync scheduled');
  } catch (error) {
    console.error('Failed to register periodic sync:', error);
  }
}

setupPeriodicSync();
`;

/* ============================================================
   9. MANIFEST.JSON CONFIGURATION
   ============================================================ */

MANIFEST_CONFIG = `
// manifest.json contains:

- name: Полное название приложения
- short_name: Короткое имя (для рабочего стола)
- description: Описание
- start_url: URL, с которого запускается приложение
- display: "standalone" - как отдельное приложение
- theme_color: Цвет темы UI
- background_color: Цвет фона загрузки
- icons: Иконки для разных размеров (72x72 до 512x512)
- screenshots: Скриншоты для мобильных
- shortcuts: Быстрые ссылки (меню приложения)
- share_target: Поддержка нативного Share API
- categories: Категории приложения в app store
`;

/* ============================================================
   10. BROWSER SUPPORT & DETECTION
   ============================================================ */

BROWSER_SUPPORT = `
// Check PWA support

function checkPWASupport() {
  return {
    serviceWorker: 'serviceWorker' in navigator,
    cacheAPI: 'caches' in window,
    fetchAPI: 'fetch' in window,
    notifications: 'Notification' in window,
    pushManager: 'PushManager' in window,
    periodicSync: 'PeriodicSyncManager' in window,
    backgroundSync: 'sync' in (navigator.serviceWorker?.controller || {})
  };
}

const support = checkPWASupport();
console.log('PWA Support:', support);

// Progressive enhancement: only show features if supported
if (support.notifications) {
  // Show notification settings
}

if (support.pushManager) {
  // Show push notification opt-in
}
`;

export { 
  HTML_PWA_STRUCTURE, 
  SERVICE_WORKER_FEATURES,
  HTML_OFFLINE_PAGE,
  PWA_API,
  DJANGO_SETUP,
  SERVICE_WORKER_MESSAGES,
  PUSH_NOTIFICATIONS,
  BACKGROUND_SYNC,
  MANIFEST_CONFIG,
  BROWSER_SUPPORT
};
