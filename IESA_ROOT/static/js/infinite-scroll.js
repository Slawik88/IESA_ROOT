/**
 * Infinite Scroll System
 * Automatically loads and appends more content as user scrolls down
 * Compatible with Django pagination and HTMX
 */

(function() {
    'use strict';

    const InfiniteScroll = {
        isLoading: false,
        hasMore: true,
        container: null,
        nextUrl: null,
        scrollThreshold: 500, // pixels from bottom to trigger load
        loadingIndicator: null,

        /**
         * Initialize infinite scroll
         */
        init() {
            // Find infinite scroll container
            this.container = document.querySelector('[data-infinite-scroll]');
            
            if (!this.container) return;

            // Get next page URL
            this.nextUrl = this.container.dataset.nextUrl;
            this.hasMore = this.container.dataset.hasMore !== 'false';

            // Listen for scroll
            window.addEventListener('scroll', this.handleScroll.bind(this), { passive: true });

            // Create loading indicator
            this.createLoadingIndicator();

            // Listen for HTMX events
            document.addEventListener('htmx:afterSwap', this.handleAfterSwap.bind(this));
        },

        /**
         * Handle scroll event
         */
        handleScroll() {
            if (this.isLoading || !this.hasMore || !this.nextUrl) return;

            const distanceToBottom = document.documentElement.scrollHeight - 
                                   (window.scrollY + window.innerHeight);

            if (distanceToBottom < this.scrollThreshold) {
                this.loadMore();
            }
        },

        /**
         * Load more items
         */
        loadMore() {
            if (this.isLoading || !this.nextUrl) return;

            this.isLoading = true;
            this.showLoadingIndicator();

            // Use HTMX to load more content
            htmx.ajax('GET', this.nextUrl, {
                target: this.container,
                swap: 'beforeend',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
        },

        /**
         * Handle HTMX after swap
         */
        handleAfterSwap(event) {
            if (event.detail.target !== this.container) return;

            this.isLoading = false;
            this.hideLoadingIndicator();

            // Check for next page URL in loaded content
            const nextLink = event.detail.target.querySelector('[data-next-url]');
            if (nextLink) {
                this.nextUrl = nextLink.dataset.nextUrl;
                this.hasMore = nextLink.dataset.hasMore !== 'false';
            } else {
                // No more pages
                this.hasMore = false;
                this.showEndMessage();
            }

            // Update dynamic values from container
            const containerNextUrl = this.container.dataset.nextUrl;
            if (containerNextUrl) {
                this.nextUrl = containerNextUrl;
            }
        },

        /**
         * Create loading indicator
         */
        createLoadingIndicator() {
            this.loadingIndicator = document.createElement('div');
            this.loadingIndicator.className = 'infinite-scroll-loader';
            this.loadingIndicator.innerHTML = `
                <div class="loader-content">
                    <div class="skeleton skeleton-post mb-4">
                        <div class="skeleton-item skeleton-avatar skeleton-pulse"></div>
                        <div class="skeleton-content">
                            <div class="skeleton-item skeleton-title skeleton-pulse"></div>
                            <div class="skeleton-item skeleton-text skeleton-pulse"></div>
                        </div>
                    </div>
                </div>
            `;
            this.loadingIndicator.style.display = 'none';
            this.container.appendChild(this.loadingIndicator);
        },

        /**
         * Show loading indicator
         */
        showLoadingIndicator() {
            if (this.loadingIndicator) {
                this.loadingIndicator.style.display = 'block';
            }
        },

        /**
         * Hide loading indicator
         */
        hideLoadingIndicator() {
            if (this.loadingIndicator) {
                this.loadingIndicator.style.display = 'none';
            }
        },

        /**
         * Show end of list message
         */
        showEndMessage() {
            const endMessage = document.createElement('div');
            endMessage.className = 'infinite-scroll-end';
            endMessage.innerHTML = `
                <div class="text-center py-5 text-muted">
                    <i class="fas fa-check-circle mb-3 d-block" style="font-size: 2rem; opacity: 0.5;"></i>
                    <p>No more content to load</p>
                </div>
            `;
            this.container.appendChild(endMessage);
        },

        /**
         * Reset scroll (clear content and reload)
         */
        reset() {
            this.isLoading = false;
            this.hasMore = true;
            this.nextUrl = this.container.dataset.nextUrl;
        },

        /**
         * Manually load more
         */
        loadMoreManual() {
            if (this.hasMore && this.nextUrl) {
                this.loadMore();
            }
        }
    };

    /**
     * Virtual Scroll for Large Lists
     * Improves performance by only rendering visible items
     */
    const VirtualScroll = {
        itemHeight: 0,
        container: null,
        items: [],
        visibleStart: 0,
        visibleEnd: 0,

        init() {
            const container = document.querySelector('[data-virtual-scroll]');
            if (!container) return;

            this.container = container;
            this.items = Array.from(container.querySelectorAll('[data-virtual-item]'));
            
            if (this.items.length === 0) return;

            // Calculate item height from first item
            this.itemHeight = this.items[0].offsetHeight;

            // Initial layout
            this.updateVisibleItems();

            // Listen for scroll and resize
            window.addEventListener('scroll', this.updateVisibleItems.bind(this), { passive: true });
            window.addEventListener('resize', this.updateVisibleItems.bind(this), { passive: true });
        },

        /**
         * Update visible items based on scroll position
         */
        updateVisibleItems() {
            if (!this.container || this.itemHeight === 0) return;

            const containerRect = this.container.getBoundingClientRect();
            const containerTop = containerRect.top + window.scrollY;
            const containerHeight = containerRect.height;

            this.visibleStart = Math.max(0, Math.floor((window.scrollY - containerTop) / this.itemHeight));
            this.visibleEnd = Math.min(
                this.items.length,
                Math.ceil((window.scrollY - containerTop + window.innerHeight) / this.itemHeight)
            );

            this.renderVisibleItems();
        },

        /**
         * Render only visible items
         */
        renderVisibleItems() {
            this.items.forEach((item, index) => {
                if (index >= this.visibleStart - 1 && index <= this.visibleEnd) {
                    item.style.display = '';
                } else {
                    item.style.display = 'none';
                }
            });
        }
    };

    /**
     * Pagination Helper
     * Converts pagination links to infinite scroll
     */
    const PaginationHelper = {
        init() {
            const paginationLinks = document.querySelectorAll('.pagination a');
            
            paginationLinks.forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const url = link.getAttribute('href');
                    InfiniteScroll.nextUrl = url;
                    InfiniteScroll.loadMore();
                });
            });

            // Hide pagination when infinite scroll is enabled
            const pagination = document.querySelector('.pagination');
            if (pagination && document.querySelector('[data-infinite-scroll]')) {
                pagination.style.display = 'none';
            }
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            InfiniteScroll.init();
            VirtualScroll.init();
            PaginationHelper.init();
        });
    } else {
        InfiniteScroll.init();
        VirtualScroll.init();
        PaginationHelper.init();
    }

    // Export for use in other scripts
    window.InfiniteScroll = InfiniteScroll;
    window.VirtualScroll = VirtualScroll;
})();
