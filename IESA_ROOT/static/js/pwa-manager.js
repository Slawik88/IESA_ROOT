/**
 * PWA Manager (disabled)
 * Simplified stub: does not register service workers or request permissions.
 */

class PWAManager {
  constructor() {
    this.isOnline = navigator.onLine;
    console.info('PWA features are disabled; site runs as regular web app.');
  }

  // Compatibility helpers (no-op)
  async clearCache() { return Promise.resolve(); }
  async cacheUrls() { return Promise.resolve(); }
  isAppOnline() { return this.isOnline; }
}

// Expose stub in case someone imports it
window.PWAManager = PWAManager;
