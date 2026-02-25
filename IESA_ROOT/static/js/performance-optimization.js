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
function initLazyLoading() {
    // Check if IntersectionObserver is supported
    if ('IntersectionObserver' in window) {
        const options = {
            threshold: 0.1,
            rootMargin: '50px'
        };

        const imageObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                    }
                    
                    if (img.dataset.srcset) {
                        img.srcset = img.dataset.srcset;
                        img.removeAttribute('data-srcset');
                    }
                    
                    img.classList.add('lazy-loaded');
                    imageObserver.unobserve(img);
                }
            });
        }, options);

        document.querySelectorAll('img[data-src]').forEach(img => {
            imageObserver.observe(img);
        });

        // Lazy load iframes
        const iframeObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const iframe = entry.target;
                    if (iframe.dataset.src) {
                        iframe.src = iframe.dataset.src;
                        iframe.removeAttribute('data-src');
                    }
                    iframeObserver.unobserve(iframe);
                }
            });
        }, options);

        document.querySelectorAll('iframe[data-src]').forEach(iframe => {
            iframeObserver.observe(iframe);
        });
    }
}

/**
 * Optimize scroll listeners with throttling
 */
function initOptimizedScrollListeners() {
    const header = document.querySelector('header');
    let lastScrollY = 0;

    const handleScroll = throttle(() => {
        const scrollY = window.scrollY;
        
        // Optimize header hide/show logic
        if (header) {
            if (scrollY > lastScrollY && scrollY > 100) {
                // Scrolling down - hide header
                header.style.transform = 'translateY(-100%)';
            } else {
                // Scrolling up - show header
                header.style.transform = 'translateY(0)';
            }
        }
        
        lastScrollY = scrollY;
    }, 50);

    window.addEventListener('scroll', handleScroll, { passive: true });
}

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
 * Preload critical resources
 */
function preloadCriticalResources() {
    const criticalCSS = [
        'css/homepage-v2.css',
        'css/sections-enhancements.css'
    ];
    
    const criticalJS = [
        'js/partner-card-effects.js',
        'js/sections-interactions.js'
    ];
    
    // Preload critical CSS
    criticalCSS.forEach(href => {
        const link = document.createElement('link');
        link.rel = 'preload';
        link.as = 'style';
        link.href = `/static/${href}`;
        document.head.appendChild(link);
    });
    
    // Prefetch critical JS
    criticalJS.forEach(src => {
        const script = document.createElement('link');
        script.rel = 'prefetch';
        script.href = `/static/${src}`;
        document.head.appendChild(script);
    });
}

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
    
    // Use Performance Observer API if available
    if ('PerformanceObserver' in window) {
        try {
            const observer = new PerformanceObserver((list) => {
                // Performance entries observed
            });
            
            observer.observe({ entryTypes: ['measure', 'navigation'] });
        } catch (e) {
            // PerformanceObserver not supported
        }
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
    preloadCriticalResources();
    initLazyLoading();
    initOptimizedScrollListeners();
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
    initOptimizedScrollListeners,
    monitorPerformance
};
