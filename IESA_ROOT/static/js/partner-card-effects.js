/**
 * Partner Cards Interactive Effects
 * Adds modern hover interactions, particle effects, and smooth animations
 */

(function() {
    'use strict';

    /**
     * Initialize partner card interactions
     */
    function initPartnerCards() {
        const partnerCards = document.querySelectorAll('.partner-card-compact');

        partnerCards.forEach(card => {
            // B4-01: пропускаем уже инициализированные — без guard listeners
            // дублируются экспоненциально при каждом HTMX swap
            if (card.dataset.pcInit) return;
            card.dataset.pcInit = '1';

            addTiltEffect(card);
            addRippleEffect(card);
            lazyLoadLogos(card);
        });
    }

    /**
     * Add subtle tilt effect on hover
     * @param {HTMLElement} card
     */
    function addTiltEffect(card) {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            
            const tiltX = ((y - centerY) / centerY) * 3; // max 3 degrees
            const tiltY = ((x - centerX) / centerX) * -3;
            
            card.style.transform = `perspective(1000px) rotateX(${tiltX}deg) rotateY(${tiltY}deg) translateY(-4px)`;
        });
        
        card.addEventListener('mouseleave', () => {
            card.style.transform = '';
        });
    }

    /**
     * Add ripple effect on card click
     * @param {HTMLElement} card
     */
    function addRippleEffect(card) {
        card.addEventListener('click', function(e) {
            // Don't ripple on button clicks
            if (e.target.closest('button') || e.target.closest('a')) {
                return;
            }
            
            const ripple = document.createElement('span');
            const rect = card.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;
            
            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';
            ripple.classList.add('ripple');
            
            card.appendChild(ripple);
            
            setTimeout(() => ripple.remove(), 600);
        });
    }

    /**
     * Lazy load partner logos for performance
     * @param {HTMLElement} card
     */
    function lazyLoadLogos(card) {
        const logo = card.querySelector('.partner-logo-compact img');
        if (!logo || logo.complete) return;
        
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src || img.src;
                    img.classList.add('loaded');
                    observer.unobserve(img);
                }
            });
        }, { rootMargin: '50px' });
        
        observer.observe(logo);
    }

    /**
     * Add stagger animation to partner cards on scroll
     */
    function initStaggerAnimation() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry, index) => {
                if (entry.isIntersecting) {
                    setTimeout(() => {
                        entry.target.classList.add('fade-in-up-animated');
                    }, index * 50); // 50ms delay between each card
                    
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1 });
        
        document.querySelectorAll('.partner-card-compact').forEach(card => {
            observer.observe(card);
        });
    }

    /**
     * Initialize partner category color animation
     */
    function animatePartnerBadges() {
        const badges = document.querySelectorAll('[class*="badge-partner-"]');
        
        badges.forEach((badge, index) => {
            // Delay each badge animation
            setTimeout(() => {
                badge.style.animation = 'badgeFadeIn 0.5s ease-out forwards';
            }, index * 100);
        });
    }

    /**
     * Add parallax effect to partner section background
     */
    function initParallaxEffect() {
        // Parallax через JS убран — реализован CSS background-attachment в responsive.css.
    }

    function runAll() {
        initPartnerCards();
        initStaggerAnimation();
        animatePartnerBadges();
    }

    // Первичная инициализация
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runAll);
    } else {
        runAll();
    }

    // Переинициализация после HTMX swap (новые партнёры в DOM)
    document.addEventListener('htmx:afterSettle', runAll);

    // Public API
    window.PartnerCardEffects = { init: initPartnerCards, reinit: runAll };

})();

// NOTE: CSS for .ripple, .partner-card-compact, @keyframes badgeFadeIn/fadeInUp,
// .fade-in-up-animated, .partner-logo-compact img — moved to components.css (P6.6)
