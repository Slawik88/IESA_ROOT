/**
 * PERFORMANCE OPTIMIZATION - Load time improvements and caching
 * Features: Code splitting, lazy loading, debouncing, caching
 */

// Debounce utility
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Throttle utility
function throttle(func, limit) {
    let inThrottle;
    return function (...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * Lazy load images and iframes
 */
const observedMedia = new WeakSet();
let mediaObserver;

function loadMedia(element) {
    // Set responsive candidates first to avoid downloading the fallback twice.
    if (element.dataset.srcset) {
        element.srcset = element.dataset.srcset;
        element.removeAttribute('data-srcset');
    }
    if (element.dataset.src) {
        element.src = element.dataset.src;
        element.removeAttribute('data-src');
    }
    element.classList.add('lazy-loaded');
}

function initLazyLoading(root = document) {
    const selector = 'img[data-src], img[data-srcset], iframe[data-src]';
    const elements = Array.from(root.querySelectorAll(selector));
    if (root.matches?.(selector)) elements.unshift(root);
    const pending = elements.filter(element => !observedMedia.has(element));
    if (!pending.length) return;
    if (!window.IntersectionObserver) {
        pending.forEach(loadMedia);
        return;
    }
    if (!mediaObserver) {
        mediaObserver = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    loadMedia(entry.target);
                    mediaObserver.unobserve(entry.target);
                }
            });
        }, { rootMargin: '50px', threshold: 0.1 });
    }
    pending.forEach(element => {
        observedMedia.add(element);
        mediaObserver.observe(element);
    });
}

// Release removed nodes, including swaps performed outside the main page.
document.addEventListener('htmx:beforeCleanupElement', event => {
    const root = event.detail.elt;
    if (!mediaObserver || !root || typeof root.querySelectorAll !== 'function') return;
    [root, ...root.querySelectorAll('img, iframe')].forEach(element => {
        mediaObserver.unobserve(element);
        observedMedia.delete(element);
    });
});
document.addEventListener('htmx:afterSwap', event => {
    initLazyLoading(event.detail.elt || document);
});

/**
 * Cache DOM elements for repeated access
 */
const DOMCache = {
    elements: {},

    get: function(selector) {
        if (!this.elements[selector]) {
            this.elements[selector] = document.querySelectorAll(selector);
        }
        return this.elements[selector];
    },

    clear: function() {
        this.elements = {};
    }
};

// B4-03: при HTMX swap DOM меняется — кэш устаревших NodeList ссылок
// должен сбрасываться чтобы следующий get() получил актуальные элементы.
document.addEventListener('htmx:afterSwap', function() { DOMCache.clear(); });

/**
 * Debounce window resize events
 */
function initOptimizedResize() {
    const handleResize = debounce(() => {
        // Trigger resize event on specific elements
        const cards = DOMCache.get('.card');
        cards.forEach(card => {
            card.dispatchEvent(new Event('customResize'));
        });
    }, 250);

    window.addEventListener('resize', handleResize);
}

/**
 * Cache API responses
 */
const APICache = {
    cache: {},
    ttl: 5 * 60 * 1000, // 5 minutes
    
    set: function(key, value) {
        this.cache[key] = {
            value: value,
            timestamp: Date.now()
        };
    },
    
    get: function(key) {
        const item = this.cache[key];
        if (!item) return null;
        
        if (Date.now() - item.timestamp > this.ttl) {
            delete this.cache[key];
            return null;
        }
        
        return item.value;
    },
    
    clear: function() {
        this.cache = {};
    }
};

/**
 * Monitor performance metrics
 */
function monitorPerformance() {
    if (window.performance && window.performance.timing) {
        window.addEventListener('load', function () {
            const perfData = window.performance.timing;
            const pageLoadTime = perfData.loadEventEnd - perfData.navigationStart;
            
            // Send to analytics if needed
            if (window.gtag) {
                gtag('event', 'page_load_time', {
                    'value': pageLoadTime,
                    'event_category': 'performance'
                });
            }
        });
    }
    
}

/**
 * Optimize animations for low-end devices
 */
function optimizeForDevice() {
    // Check for prefers-reduced-motion
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    
    if (prefersReducedMotion) {
        document.body.classList.add('reduce-motion');
    }
    
    // Check device memory if available
    if (navigator.deviceMemory && navigator.deviceMemory < 4) {
        document.body.classList.add('low-end-device');
    }
}

/**
 * Initialize all performance optimizations
 */
function initPerformanceOptimizations() {
    initLazyLoading();
    initOptimizedResize();
    optimizeForDevice();
    
    // Monitor in development mode
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        monitorPerformance();
    }
}

// Start optimizations when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPerformanceOptimizations);
} else {
    initPerformanceOptimizations();
}

// Expose utilities for external use
window.PerformanceUtils = {
    debounce,
    throttle,
    DOMCache,
    APICache,
    initLazyLoading,
    monitorPerformance
};
