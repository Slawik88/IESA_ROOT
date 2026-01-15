/**
 * Advanced Card Interactions
 * Handles interactive card effects and animations
 */

(function() {
    'use strict';

    const CardAnimations = {
        /**
         * Initialize card animations
         */
        init() {
            // Get all animated cards
            const animatedCards = document.querySelectorAll('[data-card-animation]');
            
            animatedCards.forEach(card => {
                // Add hover listeners for enhanced effects
                card.addEventListener('mouseenter', this.handleCardEnter.bind(this));
                card.addEventListener('mouseleave', this.handleCardLeave.bind(this));
                card.addEventListener('click', this.handleCardClick.bind(this));
            });

            // Intersection observer for fade-in animation on scroll
            this.observeCardsInViewport();
        },

        /**
         * Handle card enter (hover)
         */
        handleCardEnter(event) {
            const card = event.currentTarget;
            const animationType = card.dataset.cardAnimation;

            // Add entering class for additional CSS hooks
            card.classList.add('card-entering');

            // Trigger custom event
            const enterEvent = new CustomEvent('cardEnter', { detail: { card, animationType } });
            card.dispatchEvent(enterEvent);
        },

        /**
         * Handle card leave (hover out)
         */
        handleCardLeave(event) {
            const card = event.currentTarget;
            card.classList.remove('card-entering');

            const leaveEvent = new CustomEvent('cardLeave', { detail: { card } });
            card.dispatchEvent(leaveEvent);
        },

        /**
         * Handle card click
         */
        handleCardClick(event) {
            const card = event.currentTarget;
            const link = card.querySelector('a[href]:not(.btn)');
            
            // If card has a primary link, navigate to it
            if (link && !event.target.closest('a, button')) {
                event.preventDefault();
                const url = link.getAttribute('href');
                if (url) {
                    // Add click animation
                    card.classList.add('card-clicked');
                    setTimeout(() => {
                        window.location.href = url;
                    }, 100);
                }
            }
        },

        /**
         * Observe cards in viewport for fade-in animation
         */
        observeCardsInViewport() {
            const cards = document.querySelectorAll('[data-card-animation]');
            
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('card-visible');
                        observer.unobserve(entry.target);
                    }
                });
            }, {
                threshold: 0.1,
                rootMargin: '0px 0px -50px 0px'
            });

            cards.forEach(card => observer.observe(card));
        },

        /**
         * Add ripple effect to card
         */
        addRipple(card, event) {
            const ripple = document.createElement('span');
            const rect = card.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = event.clientX - rect.left - size / 2;
            const y = event.clientY - rect.top - size / 2;

            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';
            ripple.classList.add('card-ripple');

            card.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        },

        /**
         * Update card animation type dynamically
         */
        setCardAnimation(card, animationType) {
            card.dataset.cardAnimation = animationType;
        },

        /**
         * Get all cards with specific animation type
         */
        getCardsByAnimation(animationType) {
            return document.querySelectorAll(`[data-card-animation="${animationType}"]`);
        }
    };

    /**
     * Advanced Card Hover Effects
     */
    const CardHoverEffects = {
        init() {
            this.setupMouseTracking();
            this.setupImageHoverEffects();
        },

        /**
         * Setup mouse tracking for advanced hover effects
         */
        setupMouseTracking() {
            const cards = document.querySelectorAll('[data-mouse-track]');
            
            cards.forEach(card => {
                card.addEventListener('mousemove', this.handleMouseTrack.bind(this));
                card.addEventListener('mouseleave', this.resetMouseTrack.bind(this));
            });
        },

        /**
         * Handle mouse tracking
         */
        handleMouseTrack(event) {
            const card = event.currentTarget;
            const rect = card.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;

            const centerX = rect.width / 2;
            const centerY = rect.height / 2;

            const angleX = (y - centerY) / 20;
            const angleY = (centerX - x) / 20;

            card.style.transform = `
                perspective(1000px)
                rotateX(${angleX}deg)
                rotateY(${angleY}deg)
            `;
        },

        /**
         * Reset mouse tracking
         */
        resetMouseTrack(event) {
            const card = event.currentTarget;
            card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0)';
        },

        /**
         * Setup image hover effects
         */
        setupImageHoverEffects() {
            const cardImages = document.querySelectorAll('[data-card-animation] img');
            
            cardImages.forEach(img => {
                img.addEventListener('mouseenter', () => {
                    img.style.filter = 'brightness(1.1) contrast(1.05)';
                });
                img.addEventListener('mouseleave', () => {
                    img.style.filter = 'brightness(1) contrast(1)';
                });
            });
        }
    };

    /**
     * Card Interaction Analytics
     * Track card interactions for analytics
     */
    const CardAnalytics = {
        init() {
            const cards = document.querySelectorAll('[data-card-animation]');
            
            cards.forEach(card => {
                card.addEventListener('cardEnter', this.logCardInteraction);
                card.addEventListener('click', this.logCardClick);
            });
        },

        logCardInteraction(event) {
            const { card, animationType } = event.detail;
            // Send to analytics service if available
            if (window.analytics) {
                window.analytics.logEvent('card_hover', {
                    animationType,
                    cardId: card.id || 'unknown'
                });
            }
        },

        logCardClick(event) {
            const card = event.currentTarget;
            if (window.analytics) {
                window.analytics.logEvent('card_click', {
                    cardId: card.id || 'unknown'
                });
            }
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            CardAnimations.init();
            CardHoverEffects.init();
            CardAnalytics.init();
        });
    } else {
        CardAnimations.init();
        CardHoverEffects.init();
        CardAnalytics.init();
    }

    // Export for use in other scripts
    window.CardAnimations = CardAnimations;
    window.CardHoverEffects = CardHoverEffects;
})();
