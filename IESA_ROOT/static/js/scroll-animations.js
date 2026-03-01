/**
 * Unified Scroll Animations System
 * Uses IntersectionObserver for efficient scroll-triggered animations
 * Replaces inline animation scripts across templates
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px',
        animateOnLoad: true
    };

    // Animation class mappings for different element types
    const ANIMATION_CLASSES = {
        hero: 'hero-animate',
        card: 'card-animate',
        about: 'about-animate',
        partner: 'partner-animate',
        default: 'fade-in-up'
    };

    /**
     * Initialize scroll animations on DOM load
     */
    function initScrollAnimations() {
        // Animate hero section immediately on page load
        if (CONFIG.animateOnLoad) {
            animateHeroSection();
        }

        // Set up IntersectionObserver for scroll-triggered animations
        const observer = createObserver();
        observeElements(observer);
    }

    /**
     * Animate hero section immediately (no scroll needed)
     */
    function animateHeroSection() {
        const heroSection = document.querySelector('.hero-section');
        if (heroSection) {
            heroSection.classList.add('animate-on-scroll', ANIMATION_CLASSES.hero, 'animated');
        }
    }

    /**
     * Create IntersectionObserver instance
     */
    function createObserver() {
        return new IntersectionObserver(handleIntersection, {
            threshold: CONFIG.threshold,
            rootMargin: CONFIG.rootMargin
        });
    }

    /**
     * Handle element intersection
     */
    function handleIntersection(entries, observer) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animated');
                // Stop observing once animated (performance optimization)
                observer.unobserve(entry.target);
            }
        });
    }

    /**
     * Observe all animatable elements
     */
    function observeElements(observer) {
        // Define element selectors and their animation types
        const elementsToObserve = [
            { selector: '#events-section .grid > *', animationClass: ANIMATION_CLASSES.card },
            { selector: '#core-products-section .grid > *', animationClass: ANIMATION_CLASSES.card },
            { selector: '#benefits-section .row > *', animationClass: ANIMATION_CLASSES.card },
            { selector: '#about-section', animationClass: ANIMATION_CLASSES.about },
            { selector: '#partners-section .grid > *', animationClass: ANIMATION_CLASSES.partner },
            { selector: '.member-card', animationClass: ANIMATION_CLASSES.card },
            { selector: '.product-card', animationClass: ANIMATION_CLASSES.card },
            { selector: '.event-card', animationClass: ANIMATION_CLASSES.card },
            { selector: '.benefit-card', animationClass: ANIMATION_CLASSES.card },
            { selector: '.partner-card-compact', animationClass: ANIMATION_CLASSES.partner }
        ];

        elementsToObserve.forEach(({ selector, animationClass }) => {
            const elements = document.querySelectorAll(selector);
            elements.forEach(element => {
                element.classList.add('animate-on-scroll', animationClass);
                observer.observe(element);
            });
        });
    }

    /**
     * Public API for manual animation triggering (if needed)
     */
    window.ScrollAnimations = {
        init: initScrollAnimations,
        animateElement: function(element, animationType = 'default') {
            if (element) {
                const animationClass = ANIMATION_CLASSES[animationType] || ANIMATION_CLASSES.default;
                element.classList.add('animate-on-scroll', animationClass, 'animated');
            }
        }
    };

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initScrollAnimations);
    } else {
        initScrollAnimations();
    }
})();
