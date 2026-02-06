/**
 * MOBILE OPTIMIZATION - Enhanced experience for mobile devices
 * Features: Touch gestures, responsive adjustments, mobile-first interactions
 */

document.addEventListener('DOMContentLoaded', function () {
    initMobileMenuToggle();
    initTouchOptimizations();
    initMobileNavigationMenu();
    adjustLayoutForMobile();
});

/**
 * Mobile menu toggle with smooth animation
 */
function initMobileMenuToggle() {
    const navbarToggler = document.querySelector('.navbar-toggler');
    const navbarCollapse = document.getElementById('navbarNav');
    
    if (!navbarToggler || !navbarCollapse || typeof bootstrap === 'undefined') return;
    
    const bsCollapse = bootstrap.Collapse.getOrCreateInstance(navbarCollapse, { toggle: false });
    
    // Close menu when link is clicked
    const navLinks = navbarCollapse.querySelectorAll('a[href*="#"]');
    navLinks.forEach(link => {
        link.addEventListener('click', function () {
            if (navbarToggler.offsetParent !== null && navbarCollapse.classList.contains('show')) {
                bsCollapse.hide();
            }
        });
    });
}

/**
 * Touch optimizations
 */
function initTouchOptimizations() {
    const isTouchDevice = () => {
        return (
            (typeof window !== 'undefined' &&
                ('ontouchstart' in window ||
                    (window.DocumentTouch &&
                        typeof document !== 'undefined' &&
                        document instanceof window.DocumentTouch))) ||
            (typeof navigator !== 'undefined' &&
                (navigator.maxTouchPoints > 0 ||
                    navigator.msMaxTouchPoints > 0))
        );
    };
    
    if (isTouchDevice()) {
        document.body.classList.add('touch-enabled');
        
        // Add touch feedback to interactive elements
        const touchTargets = document.querySelectorAll('a, button, [role="button"], .card');
        
        touchTargets.forEach(target => {
            target.addEventListener('touchstart', function () {
                this.style.opacity = '0.8';
                this.style.transform = 'scale(0.98)';
            });
            
            target.addEventListener('touchend', function () {
                this.style.opacity = '1';
                this.style.transform = 'scale(1)';
            });
        });
    }
}

/**
 * Mobile navigation menu enhancements
 */
function initMobileNavigationMenu() {
    const windowWidth = window.innerWidth;
    
    if (windowWidth < 768) {
        // Add touch-friendly padding to nav items
        const navItems = document.querySelectorAll('.nav-link');
        navItems.forEach(item => {
            item.style.padding = '12px 15px';
            item.style.minHeight = '44px'; // Apple's recommended touch target size
            item.style.display = 'flex';
            item.style.alignItems = 'center';
        });
    }
    
    // Handle viewport changes without reload
    window.addEventListener('resize', debounce(() => {
        adjustLayoutForMobile();
    }, 200));
}

/**
 * Adjust layout for mobile
 */
function adjustLayoutForMobile() {
    const viewport = window.innerWidth;
    
    if (viewport < 768) {
        // Adjust card padding on mobile
        const cards = document.querySelectorAll('.card');
        cards.forEach(card => {
            const body = card.querySelector('.card-body');
            if (body) {
                body.style.padding = '1.25rem';
            }
        });
        
        // Adjust font sizes for better readability
        const headers = document.querySelectorAll('h1, h2, h3');
        headers.forEach(header => {
            const fontSize = parseInt(window.getComputedStyle(header).fontSize);
            if (fontSize > 32) {
                header.style.fontSize = (fontSize * 0.85) + 'px';
            }
        });
        
        // Optimize section padding
        const sections = document.querySelectorAll('section');
        sections.forEach(section => {
            section.style.paddingLeft = '1rem';
            section.style.paddingRight = '1rem';
        });
    }
}

/**
 * Debounce utility
 */
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

/**
 * Safe area adjustments for devices with notches
 */
function applySafeAreaAdjustments() {
    if (window.CSS && window.CSS.supports && window.CSS.supports('padding-left', 'max(0px, env(safe-area-inset-left))')) {
        const header = document.querySelector('header');
        const footer = document.querySelector('footer');
        
        if (header) {
            header.style.paddingLeft = 'max(1rem, env(safe-area-inset-left))';
            header.style.paddingRight = 'max(1rem, env(safe-area-inset-right))';
        }
        
        if (footer) {
            footer.style.paddingLeft = 'max(1rem, env(safe-area-inset-left))';
            footer.style.paddingRight = 'max(1rem, env(safe-area-inset-right))';
        }
    }
}

/**
 * Orientation change detection
 */
function handleOrientationChange() {
    window.addEventListener('orientationchange', function () {
        // Reload layout after orientation change
        setTimeout(() => {
            location.reload();
        }, 100);
    });
}

/**
 * Optimize images for mobile
 */
function optimizeMobileImages() {
    const images = document.querySelectorAll('img');
    
    images.forEach(img => {
        // Use lower resolution on mobile
        if (window.innerWidth < 768 && img.dataset.mobileSrc) {
            img.src = img.dataset.mobileSrc;
        }
        
        // Add responsive images
        if (!img.srcset && window.innerWidth < 768) {
            img.style.maxWidth = '100%';
            img.style.height = 'auto';
        }
    });
}

/**
 * Mobile-friendly form optimization
 */
function optimizeForms() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        const inputs = form.querySelectorAll('input, textarea, select');
        
        inputs.forEach(input => {
            // Increase touch target size
            const wrapper = input.parentElement;
            if (wrapper) {
                wrapper.style.minHeight = '44px';
            }
            
            // Disable zoom on input focus
            input.addEventListener('focus', function () {
                document.querySelector('meta[name="viewport"]').setAttribute(
                    'content',
                    'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no'
                );
            });
            
            input.addEventListener('blur', function () {
                document.querySelector('meta[name="viewport"]').setAttribute(
                    'content',
                    'width=device-width, initial-scale=1'
                );
            });
        });
    });
}

/**
 * Mobile-friendly scrolling optimization
 */
function optimizeScrolling() {
    // Use passive event listeners for better scroll performance
    const scrollableElements = document.querySelectorAll('[data-scrollable]');
    
    scrollableElements.forEach(el => {
        el.addEventListener('scroll', () => {
            // Perform scroll calculations
        }, { passive: true });
    });
    
    // Apply will-change to frequently animated elements
    document.querySelectorAll('.hero-section, [class*="card"]').forEach(el => {
        el.style.willChange = 'transform';
    });
}

// Initialize all mobile optimizations
if (window.innerWidth < 768) {
    applySafeAreaAdjustments();
    optimizeScrolling();
    optimizeMobileImages();
    optimizeForms();
}

handleOrientationChange();

// Expose functions for external use
window.MobileOptimization = {
    initMobileMenuToggle,
    initTouchOptimizations,
    adjustLayoutForMobile,
    applySafeAreaAdjustments,
    optimizeMobileImages,
    optimizeForms
};

console.log('📱 Mobile optimizations loaded');
