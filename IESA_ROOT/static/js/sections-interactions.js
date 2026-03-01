/**
 * SECTION INTERACTIONS - Enhanced interactivity for all homepage sections
 * Features: Lazy loading, animations, hover effects, smooth scrolling
 */

document.addEventListener('DOMContentLoaded', function () {
    // 1. Add interactivity to product cards
    initProductCardEffects();
    
    // 2. Add interactivity to event cards
    initEventCardEffects();
    
    // 3. Add interactivity to member cards
    initMemberCardEffects();
});

/**
 * Add hover effects to product cards
 */
function initProductCardEffects() {
    const productCards = document.querySelectorAll('.product-card');
    
    productCards.forEach(card => {
        card.addEventListener('mouseenter', function () {
            // Add glow effect
            this.style.boxShadow = '0 20px 50px rgba(248, 113, 113, 0.2)';
        });
        
        card.addEventListener('mouseleave', function () {
            // Remove glow effect
            this.style.boxShadow = '0 8px 24px rgba(0, 0, 0, 0.04)';
        });
        
        // Click effect - trigger animation
        card.addEventListener('click', function () {
            this.classList.add('clicked');
            setTimeout(() => this.classList.remove('clicked'), 300);
        });
    });
}

/**
 * Add hover effects to event cards
 */
function initEventCardEffects() {
    const eventCards = document.querySelectorAll('.event-card');
    
    eventCards.forEach(card => {
        // Hover effect
        card.addEventListener('mouseenter', function () {
            const dateEl = this.querySelector('.event-date');
            if (dateEl) {
                dateEl.style.transform = 'scale(1.05)';
            }
        });
        
        card.addEventListener('mouseleave', function () {
            const dateEl = this.querySelector('.event-date');
            if (dateEl) {
                dateEl.style.transform = 'scale(1)';
            }
        });
    });
}

/**
 * Add hover effects to member cards
 */
function initMemberCardEffects() {
    const memberCards = document.querySelectorAll('.member-card, .president-card');
    
    memberCards.forEach(card => {
        card.addEventListener('mouseenter', function () {
            const avatar = this.querySelector('.member-avatar');
            if (avatar) {
                avatar.style.filter = 'brightness(1.1) contrast(1.1)';
            }
        });
        
        card.addEventListener('mouseleave', function () {
            const avatar = this.querySelector('.member-avatar');
            if (avatar) {
                avatar.style.filter = 'brightness(1) contrast(1)';
            }
        });
    });
}

/**
 * Initialize smooth scroll navigation to sections
 * NOTE: Removed — CSS scroll-behavior: smooth + scroll-margin-top handles this.
 */

/**
 * Parallax scrolling effect for hero section
 */
function initParallaxEffect() {
    const heroSection = document.querySelector('.hero-section');
    
    if (heroSection) {
        window.addEventListener('scroll', function () {
            const scrollPosition = window.pageYOffset;
            const heroTop = heroSection.offsetTop;
            const parallaxValue = (scrollPosition - heroTop) * 0.5;
            
            if (scrollPosition < heroTop + heroSection.offsetHeight) {
                heroSection.style.transform = `translateY(${parallaxValue}px)`;
            }
        });
    }
}

/**
 * Lazy load images with fade-in effect
 */
function initLazyImageLoading() {
    const images = document.querySelectorAll('img[data-src]');
    
    const imageObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.classList.add('loaded');
                imageObserver.unobserve(img);
            }
        });
    }, {
        rootMargin: '50px'
    });
    
    images.forEach(img => imageObserver.observe(img));
}

/**
 * Add CSS for animations
 */
(function addAnimationStyles() {
    const style = document.createElement('style');
    style.textContent = `
        .fade-in-up-animated {
            animation: fadeInUp 0.6s cubic-bezier(0.4, 0, 0.2, 1) forwards !important;
        }
        
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .product-card.clicked {
            animation: cardPulse 0.4s ease-out;
        }
        
        @keyframes cardPulse {
            0% {
                transform: scale(1);
            }
            50% {
                transform: scale(1.02);
            }
            100% {
                transform: scale(1);
            }
        }
        
        img.loaded {
            animation: imageLoad 0.5s ease-out;
        }
        
        @keyframes imageLoad {
            from {
                opacity: 0;
            }
            to {
                opacity: 1;
            }
        }
    `;
    document.head.appendChild(style);
})();

// Initialize parallax and lazy loading on page load
window.addEventListener('load', function () {
    initParallaxEffect();
    initLazyImageLoading();
});

// Expose functions for external use
window.HomepageSections = {
    initProductCardEffects,
    initEventCardEffects,
    initMemberCardEffects,
    initParallaxEffect,
    initLazyImageLoading
};
