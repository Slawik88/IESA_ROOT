/**
 * PWA Manager - Initialize and manage Progressive Web App features
 * Handles service worker registration, offline detection, install prompts
 */

class PWAManager {
  constructor(options = {}) {
    this.options = {
      swPath: '/static/js/service-worker.js',
      showInstallPrompt: true,
      enableOfflineIndicator: true,
      enableNotifications: true,
      updateCheckInterval: 60000, // 1 minute
      ...options
    };

    this.serviceWorkerReg = null;
    this.isOnline = navigator.onLine;
    this.deferredPrompt = null;
    this.installPromptShown = false;

    this.init();
  }

  async init() {
    // Check browser support
    if (!('serviceWorker' in navigator)) {
      console.warn('⚠️ Service Workers not supported');
      return;
    }

    // Register service worker
    await this.registerServiceWorker();

    // Setup online/offline detection
    this.setupOfflineDetection();

    // Setup install prompt
    if (this.options.showInstallPrompt) {
      this.setupInstallPrompt();
    }

    // Setup update checking
    this.startUpdateCheck();

    // Setup notification permission
    if (this.options.enableNotifications) {
      this.requestNotificationPermission();
    }

    console.log('✅ PWA Manager initialized');
  }

  async registerServiceWorker() {
    try {
      const registration = await navigator.serviceWorker.register(
        this.options.swPath,
        { scope: '/' }
      );

      this.serviceWorkerReg = registration;
      console.log('✅ Service Worker registered');

      // Listen for updates
      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing;
        newWorker.addEventListener('statechange', () => {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            this.showUpdateNotification();
          }
        });
      });

      return registration;
    } catch (error) {
      console.error('❌ Service Worker registration failed:', error);
    }
  }

  setupOfflineDetection() {
    window.addEventListener('online', () => {
      this.isOnline = true;
      this.showOfflineIndicator(false);
      this.syncPendingData();
      console.log('✅ Back online');
    });

    window.addEventListener('offline', () => {
      this.isOnline = false;
      this.showOfflineIndicator(true);
      console.log('⚠️ Offline mode');
    });
  }

  setupInstallPrompt() {
    window.addEventListener('beforeinstallprompt', (e) => {
      // Prevent the mini-infobar from appearing
      e.preventDefault();
      // Stash the event for later use
      this.deferredPrompt = e;
      // Show install button
      this.showInstallButton();
    });

    // Detect when app is installed
    window.addEventListener('appinstalled', () => {
      console.log('📲 PWA installed');
      this.hideInstallButton();
      this.deferredPrompt = null;
    });
  }

  setupNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().then((permission) => {
        if (permission === 'granted') {
          console.log('✅ Notification permission granted');
        }
      });
    }
  }

  requestNotificationPermission() {
    if (!('Notification' in window)) {
      console.warn('⚠️ Notifications not supported');
      return;
    }

    if (Notification.permission === 'granted') {
      return;
    }

    if (Notification.permission !== 'denied') {
      Notification.requestPermission().then((permission) => {
        if (permission === 'granted') {
          console.log('✅ Notification permission granted');
          this.subscribeToPushNotifications();
        }
      });
    }
  }

  async subscribeToPushNotifications() {
    if (!this.serviceWorkerReg) return;

    try {
      const subscription = await this.serviceWorkerReg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: this.getPublicKey()
      });

      // Send subscription to server
      await fetch('/api/notifications/subscribe/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this.getCsrfToken()
        },
        body: JSON.stringify(subscription)
      });

      console.log('✅ Push notifications enabled');
    } catch (error) {
      console.error('❌ Failed to subscribe to push notifications:', error);
    }
  }

  showInstallButton() {
    const installButton = document.getElementById('pwa-install-button');
    if (installButton) {
      installButton.style.display = 'flex';
    }
  }

  hideInstallButton() {
    const installButton = document.getElementById('pwa-install-button');
    if (installButton) {
      installButton.style.display = 'none';
    }
  }

  async promptInstall() {
    if (!this.deferredPrompt) return;

    this.deferredPrompt.prompt();
    const { outcome } = await this.deferredPrompt.userChoice;

    if (outcome === 'accepted') {
      console.log('✅ User accepted install prompt');
    } else {
      console.log('❌ User dismissed install prompt');
    }

    this.deferredPrompt = null;
    this.hideInstallButton();
  }

  showOfflineIndicator(isOffline) {
    if (!this.options.enableOfflineIndicator) return;

    let indicator = document.getElementById('offline-indicator');
    if (!indicator) {
      indicator = document.createElement('div');
      indicator.id = 'offline-indicator';
      indicator.className = 'offline-indicator';
      document.body.appendChild(indicator);
    }

    if (isOffline) {
      indicator.textContent = '📡 Без интернета - работа в режиме оффлайн';
      indicator.classList.add('show');
    } else {
      indicator.classList.remove('show');
    }
  }

  showUpdateNotification() {
    const notification = document.createElement('div');
    notification.className = 'update-notification';
    notification.innerHTML = `
      <div class="update-content">
        <span>🔄 Доступно обновление приложения</span>
        <button class="btn btn-sm btn-primary" id="update-accept">Обновить</button>
        <button class="btn btn-sm btn-secondary" id="update-dismiss">Позже</button>
      </div>
    `;
    document.body.appendChild(notification);

    document.getElementById('update-accept').addEventListener('click', () => {
      this.updateServiceWorker();
      notification.remove();
    });

    document.getElementById('update-dismiss').addEventListener('click', () => {
      notification.remove();
    });
  }

  updateServiceWorker() {
    if (!this.serviceWorkerReg?.waiting) return;

    // Tell the waiting service worker to skip waiting
    this.serviceWorkerReg.waiting.postMessage({ action: 'SKIP_WAITING' });

    // Reload once new service worker is active
    let refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!refreshing) {
        refreshing = true;
        window.location.reload();
      }
    });
  }

  startUpdateCheck() {
    // Check for updates periodically
    setInterval(() => {
      if (this.serviceWorkerReg) {
        this.serviceWorkerReg.update();
      }
    }, this.options.updateCheckInterval);
  }

  async syncPendingData() {
    // Sync any pending requests when back online
    if (this.serviceWorkerReg) {
      try {
        await this.serviceWorkerReg.sync.register('sync-posts');
        console.log('🔄 Background sync scheduled');
      } catch (error) {
        console.error('Failed to schedule background sync:', error);
      }
    }
  }

  getPublicKey() {
    // This should come from your Django backend
    const key = document.querySelector('meta[name="push-public-key"]')?.content;
    if (key) {
      return this.urlBase64ToUint8Array(key);
    }
    return null;
  }

  urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding)
      .replace(/\-/g, '+')
      .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  getCsrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
           document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1];
  }

  // Public API methods
  isAppOnline() {
    return this.isOnline;
  }

  async clearCache() {
    return new Promise((resolve) => {
      if (this.serviceWorkerReg?.active) {
        this.serviceWorkerReg.active.postMessage({ action: 'CLEAR_CACHE' });
      }
      resolve();
    });
  }

  async cacheUrls(urls) {
    if (this.serviceWorkerReg?.active) {
      this.serviceWorkerReg.active.postMessage({
        action: 'CACHE_URLS',
        urls: urls
      });
    }
  }
}

// Auto-initialize on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    if (!window.__pwaInitialized) {
      window.PWAManager = new PWAManager();
      window.__pwaInitialized = true;
    }
  });
} else {
  if (!window.__pwaInitialized) {
    window.PWAManager = new PWAManager();
    window.__pwaInitialized = true;
  }
}

export { PWAManager };
