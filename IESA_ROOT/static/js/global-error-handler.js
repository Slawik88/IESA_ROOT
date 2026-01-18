/**
 * Global Error Handler for HTMX and AJAX requests
 * Handles authentication errors and prevents infinite retry loops
 */

(function() {
    'use strict';

    const ErrorHandler = {
        failureCounts: new Map(),
        MAX_FAILURES: 3,

        init() {
            // Handle HTMX errors globally
            document.addEventListener('htmx:responseError', this.handleHTMXError.bind(this));
            
            // Handle HTMX before requests
            document.addEventListener('htmx:beforeRequest', this.beforeHTMXRequest.bind(this));
        },

        beforeHTMXRequest(event) {
            const url = event.detail.pathInfo.requestPath;
            const failures = this.failureCounts.get(url) || 0;
            
            if (failures >= this.MAX_FAILURES) {
                console.warn(`Blocked request to ${url} (too many failures)`);
                event.preventDefault();
            }
        },

        handleHTMXError(event) {
            const xhr = event.detail.xhr;
            const status = xhr?.status;
            const url = event.detail.pathInfo?.requestPath;

            // Track failures
            if (url) {
                const failures = this.failureCounts.get(url) || 0;
                this.failureCounts.set(url, failures + 1);
            }

            // Handle authentication/authorization errors
            if (status === 401) {
                console.error('Unauthorized (401). Redirecting to login...');
                // Redirect to login after brief delay
                setTimeout(() => {
                    window.location.href = '/users/login/?next=' + encodeURIComponent(window.location.pathname);
                }, 1000);
            } else if (status === 403) {
                const failures = this.failureCounts.get(url) || 0;
                
                if (failures >= this.MAX_FAILURES) {
                    console.error(`Access forbidden (403) to ${url}. Stopping retries.`);
                    
                    // Remove polling elements with this URL
                    this.stopPolling(url);
                    
                    // Show user message
                    this.showAccessDeniedMessage();
                }
            } else if (status >= 500) {
                console.error(`Server error (${status}) from ${url}`);
                
                const failures = this.failureCounts.get(url) || 0;
                if (failures >= this.MAX_FAILURES) {
                    this.stopPolling(url);
                }
            }
        },

        stopPolling(url) {
            // Find and remove HTMX polling elements with this URL
            document.querySelectorAll('[hx-get]').forEach(el => {
                const hxUrl = el.getAttribute('hx-get');
                if (hxUrl && hxUrl.includes(url?.split('?')[0])) {
                    console.log('Stopping polling for:', hxUrl);
                    if (typeof htmx !== 'undefined') {
                        htmx.remove(el);
                    }
                    el.remove();
                }
            });
        },

        showAccessDeniedMessage() {
            // Only show once
            if (document.querySelector('.access-denied-alert')) return;

            const alert = document.createElement('div');
            alert.className = 'alert alert-warning alert-dismissible fade show access-denied-alert';
            alert.style.cssText = 'position: fixed; top: 70px; right: 20px; z-index: 9999; max-width: 400px;';
            alert.innerHTML = `
                <strong>Доступ ограничен</strong>
                <p class="mb-0">У вас нет доступа к этому ресурсу. Пожалуйста, обновите страницу или вернитесь назад.</p>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                <div class="mt-2">
                    <button class="btn btn-sm btn-primary" onclick="window.location.reload()">Обновить страницу</button>
                    <button class="btn btn-sm btn-secondary" onclick="window.history.back()">Назад</button>
                </div>
            `;
            document.body.appendChild(alert);

            // Auto-remove after 10 seconds
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.remove();
                }
            }, 10000);
        },

        resetFailures(url) {
            this.failureCounts.delete(url);
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => ErrorHandler.init());
    } else {
        ErrorHandler.init();
    }

    // Expose globally for manual control if needed
    window.ErrorHandler = ErrorHandler;

    console.log('✓ Global Error Handler initialized');
})();
