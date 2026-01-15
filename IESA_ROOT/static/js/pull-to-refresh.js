/**
 * Pull-to-Refresh System
 * Native-like pull-to-refresh functionality for web
 * Perfect for mobile apps and social feeds
 */

(function() {
    'use strict';

    const PullToRefresh = {
        container: null,
        startY: 0,
        currentY: 0,
        isPulling: false,
        threshold: 100, // pixels to pull to trigger refresh
        isRefreshing: false,
        refreshURL: null,

        /**
         * Initialize pull-to-refresh
         */
        init() {
            this.container = document.querySelector('[data-pull-to-refresh]');
            
            if (!this.container) return;

            this.refreshURL = this.container.dataset.refreshUrl;

            // Create refresh indicator
            this.createRefreshIndicator();

            // Touch event listeners
            this.container.addEventListener('touchstart', this.handleTouchStart.bind(this), { passive: true });
            document.addEventListener('touchmove', this.handleTouchMove.bind(this), { passive: false });
            document.addEventListener('touchend', this.handleTouchEnd.bind(this), { passive: true });

            // Allow overscrolling on iOS
            this.enableOverscroll();
        },

        /**
         * Create refresh indicator element
         */
        createRefreshIndicator() {
            const indicator = document.createElement('div');
            indicator.className = 'pull-to-refresh-indicator';
            indicator.innerHTML = `
                <div class="refresh-spinner">
                    <svg viewBox="0 0 50 50" class="spinner-icon">
                        <circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="2" />
                    </svg>
                </div>
                <div class="refresh-text">Pull to refresh</div>
            `;
            
            this.container.insertBefore(indicator, this.container.firstChild);
            this.indicator = indicator;
        },

        /**
         * Handle touch start
         */
        handleTouchStart(event) {
            const scrollTop = this.container.scrollTop;
            
            // Only start pull-to-refresh if at top of container
            if (scrollTop === 0) {
                this.startY = event.touches[0].clientY;
                this.isPulling = true;
            }
        },

        /**
         * Handle touch move
         */
        handleTouchMove(event) {
            if (!this.isPulling || this.isRefreshing) return;

            const scrollTop = this.container.scrollTop;
            const currentY = event.touches[0].clientY;
            const pull = currentY - this.startY;

            // Only apply pull effect if at top
            if (scrollTop === 0 && pull > 0) {
                event.preventDefault();
                this.currentY = pull;
                this.updateIndicator(pull);
            } else {
                this.isPulling = false;
            }
        },

        /**
         * Handle touch end
         */
        handleTouchEnd(event) {
            if (!this.isPulling) return;

            this.isPulling = false;

            if (this.currentY >= this.threshold) {
                this.triggerRefresh();
            } else {
                this.resetIndicator();
            }

            this.currentY = 0;
        },

        /**
         * Update indicator position and state
         */
        updateIndicator(pull) {
            const progress = Math.min(pull / this.threshold, 1);
            const maxTranslate = Math.min(pull, this.threshold * 1.5);

            this.indicator.style.transform = `translateY(${maxTranslate}px)`;
            this.indicator.style.opacity = Math.min(progress * 1.5, 1);

            const text = this.indicator.querySelector('.refresh-text');
            const spinner = this.indicator.querySelector('.spinner-icon');

            // Update spinner rotation
            spinner.style.transform = `rotate(${progress * 180}deg)`;

            // Update text
            if (progress < 1) {
                text.textContent = 'Pull to refresh';
            } else {
                text.textContent = 'Release to refresh';
            }
        },

        /**
         * Trigger refresh
         */
        triggerRefresh() {
            this.isRefreshing = true;

            const text = this.indicator.querySelector('.refresh-text');
            text.textContent = 'Refreshing...';

            const spinner = this.indicator.querySelector('.spinner-icon');
            spinner.style.animation = 'spin 1s linear infinite';

            // Fetch new content
            if (this.refreshURL) {
                this.loadNewContent();
            } else {
                // Trigger custom event
                const event = new CustomEvent('refreshRequested');
                this.container.dispatchEvent(event);
            }

            // Simulate refresh (adjust timeout based on your needs)
            setTimeout(() => {
                this.resetIndicator();
                this.isRefreshing = false;

                // Show success message
                this.showRefreshSuccess();
            }, 1500);
        },

        /**
         * Load new content via HTMX
         */
        loadNewContent() {
            if (!this.refreshURL) return;

            htmx.ajax('GET', this.refreshURL, {
                target: this.container,
                swap: 'innerHTML',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
        },

        /**
         * Reset indicator to initial state
         */
        resetIndicator() {
            this.indicator.style.transform = 'translateY(0)';
            this.indicator.style.opacity = '0';

            const text = this.indicator.querySelector('.refresh-text');
            text.textContent = 'Pull to refresh';

            const spinner = this.indicator.querySelector('.spinner-icon');
            spinner.style.animation = 'none';
            spinner.style.transform = 'rotate(0)';
        },

        /**
         * Show success message
         */
        showRefreshSuccess() {
            const text = this.indicator.querySelector('.refresh-text');
            const spinner = this.indicator.querySelector('.spinner-icon');
            const originalText = text.textContent;

            text.textContent = 'Refreshed!';
            spinner.style.opacity = '0';

            setTimeout(() => {
                text.textContent = originalText;
                spinner.style.opacity = '1';
            }, 1000);
        },

        /**
         * Enable overscroll effect on iOS
         */
        enableOverscroll() {
            // This allows natural overscroll on iOS
            this.container.style.overscrollBehavior = 'contain';
        }
    };

    /**
     * Refresh Button Handler
     * Alternative manual refresh trigger
     */
    const ManualRefresh = {
        init() {
            const refreshBtns = document.querySelectorAll('[data-refresh]');
            
            refreshBtns.forEach(btn => {
                btn.addEventListener('click', this.handleRefresh.bind(this));
            });
        },

        handleRefresh(event) {
            const btn = event.currentTarget;
            const target = btn.dataset.refresh;
            const url = btn.dataset.refreshUrl || window.location.href;

            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Refreshing...';

            const targetEl = document.querySelector(target) || document.body;

            htmx.ajax('GET', url, {
                target: targetEl,
                swap: 'innerHTML',
                onAfterSwap: () => {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-redo me-2"></i>Refresh';

                    // Show toast notification
                    if (window.Toast) {
                        Toast.success('Refreshed successfully!', 2000);
                    }
                },
                onError: () => {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-redo me-2"></i>Refresh';

                    if (window.Toast) {
                        Toast.error('Failed to refresh');
                    }
                }
            });
        }
    };

    /**
     * Last Updated Timestamp
     * Show when content was last refreshed
     */
    const LastUpdated = {
        init() {
            const timestamps = document.querySelectorAll('[data-last-updated]');
            
            timestamps.forEach(el => {
                this.updateTimestamp(el);
            });

            // Update timestamps every minute
            setInterval(() => {
                timestamps.forEach(el => this.updateTimestamp(el));
            }, 60000);
        },

        updateTimestamp(el) {
            const time = el.dataset.lastUpdated;
            const date = new Date(time);
            const now = new Date();
            const diff = now - date;

            let text = '';
            if (diff < 60000) {
                text = 'Just now';
            } else if (diff < 3600000) {
                const minutes = Math.floor(diff / 60000);
                text = `${minutes}m ago`;
            } else if (diff < 86400000) {
                const hours = Math.floor(diff / 3600000);
                text = `${hours}h ago`;
            } else {
                text = date.toLocaleDateString();
            }

            el.textContent = text;
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            PullToRefresh.init();
            ManualRefresh.init();
            LastUpdated.init();
        });
    } else {
        PullToRefresh.init();
        ManualRefresh.init();
        LastUpdated.init();
    }

    // Export for use in other scripts
    window.PullToRefresh = PullToRefresh;
})();
