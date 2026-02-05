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
            // Add tilt effect on mouse move
            addTiltEffect(card);
            
            // Add ripple effect on click
            addRippleEffect(card);
            
            // Lazy load partner logos
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
            ripple.classList.add('ripple-effect');
            
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
     * Add hover sound effect (optional, subtle)
     */
    function addAudioFeedback() {
        // Create audio context for subtle hover sounds
        let audioContext;
        
        document.querySelectorAll('.partner-card-compact').forEach(card => {
            card.addEventListener('mouseenter', () => {
                // Subtle click sound on hover (very quiet)
                if (!audioContext) {
                    audioContext = new (window.AudioContext || window.webkitAudioContext)();
                }
                
                const oscillator = audioContext.createOscillator();
                const gainNode = audioContext.createGain();
                
                oscillator.connect(gainNode);
                gainNode.connect(audioContext.destination);
                
                oscillator.frequency.value = 800;
                gainNode.gain.value = 0.01; // Very quiet
                
                oscillator.start();
                oscillator.stop(audioContext.currentTime + 0.05);
            });
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
        const partnersSection = document.getElementById('partners-section');
        if (!partnersSection) return;
        
        window.addEventListener('scroll', () => {
            const scrolled = window.pageYOffset;
            const rect = partnersSection.getBoundingClientRect();
            
            if (rect.top < window.innerHeight && rect.bottom > 0) {
                const offset = (scrolled - partnersSection.offsetTop) * 0.3;
                partnersSection.style.backgroundPosition = `center ${offset}px`;
            }
        });
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initPartnerCards();
            initStaggerAnimation();
            animatePartnerBadges();
            // addAudioFeedback(); // Optional - can be enabled for extra feedback
        });
    } else {
        initPartnerCards();
        initStaggerAnimation();
        animatePartnerBadges();
    }

    // Public API
    window.PartnerCardEffects = {
        init: initPartnerCards,
        reinit: function() {
            initPartnerCards();
            initStaggerAnimation();
        }
    };

})();

// CSS animations for ripple and fade-in
const style = document.createElement('style');
style.textContent = `
    .ripple-effect {
        position: absolute;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(248, 113, 113, 0.3) 0%, transparent 70%);
        transform: scale(0);
        animation: ripple 0.6s ease-out;
        pointer-events: none;
        z-index: 10;
    }
    
    @keyframes ripple {
        to {
            transform: scale(2);
            opacity: 0;
        }
    }
    
    .partner-card-compact {
        position: relative;
        overflow: hidden;
        transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    @keyframes badgeFadeIn {
        from {
            opacity: 0;
            transform: translateY(-10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
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
    
    .fade-in-up-animated {
        animation: fadeInUp 0.6s ease-out forwards;
    }
    
    .partner-logo-compact img {
        opacity: 0;
        transition: opacity 0.4s ease;
    }
    
    .partner-logo-compact img.loaded {
        opacity: 1;
    }
`;
document.head.appendChild(style);
