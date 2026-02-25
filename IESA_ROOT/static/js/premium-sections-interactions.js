/**
 * PREMIUM SECTIONS INTERACTIONS - Events, About, Partnerships
 * Advanced interactions, animations, and dynamic effects
 */

document.addEventListener('DOMContentLoaded', function () {
    initEventCardAnimations();
    initAboutSectionAnimations();
    initPartnerCardAnimations();
});

/**
 * Event cards - Advanced 3D animations and interactions
 */
function initEventCardAnimations() {
    const eventCards = document.querySelectorAll('.event-card');
    
    if (eventCards.length === 0) return;
    
    eventCards.forEach((card, index) => {
        // Stagger entrance animations
        card.style.animation = `cardEnter 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) ${index * 0.1}s both`;
        
        // 3D hover effect with perspective
        card.addEventListener('mouseenter', function () {
            this.style.perspective = '1000px';
            
            this.addEventListener('mousemove', (e) => {
                const rect = this.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                
                const rotateY = ((x - rect.width / 2) / rect.width) * 8;
                const rotateX = -((y - rect.height / 2) / rect.height) * 8;
                
                this.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(20px)`;
            });
        });
        
        card.addEventListener('mouseleave', function () {
            this.style.transform = '';
        });
        
        // Image zoom on hover
        const image = card.querySelector('.card-img-top');
        if (image) {
            card.addEventListener('mouseenter', () => {
                image.style.filter = 'brightness(1.3) contrast(1.2) blur(0px)';
            });
            
            card.addEventListener('mouseleave', () => {
                image.style.filter = 'brightness(1) contrast(1) blur(0px)';
            });
        }
        
        // Button animation on hover
        const buttons = card.querySelectorAll('.btn');
        buttons.forEach(btn => {
            btn.addEventListener('mouseenter', function () {
                this.style.transform = 'scale(1.08) translateY(-3px)';
                this.style.boxShadow = '0 8px 20px rgba(248, 113, 113, 0.3)';
            });
            
            btn.addEventListener('mouseleave', function () {
                this.style.transform = '';
                this.style.boxShadow = '';
            });
        });
    });
}

/**
 * About section - Leadership card interactions
 */
function initAboutSectionAnimations() {
    const presidentCard = document.querySelector('.president-card');
    const memberCards = document.querySelectorAll('.member-card');
    
    // President card special effects
    if (presidentCard) {
        presidentCard.style.animation = 'cardEnter 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)';
        
        presidentCard.addEventListener('mouseenter', function () {
            const avatar = this.querySelector('.president-avatar');
            if (avatar) {
                avatar.style.filter = 'brightness(1.2) saturate(1.3) drop-shadow(0 10px 30px rgba(248, 113, 113, 0.3))';
                avatar.style.transform = 'scale(1.15) rotate(5deg) translateY(-5px)';
            }
        });
        
        presidentCard.addEventListener('mouseleave', function () {
            const avatar = this.querySelector('.president-avatar');
            if (avatar) {
                avatar.style.filter = '';
                avatar.style.transform = '';
            }
        });
    }
    
    // Member cards animations
    memberCards.forEach((card, index) => {
        card.style.animation = `cardEnter 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) ${0.3 + index * 0.08}s both`;
        
        // Counter animation on card hover
        card.addEventListener('mouseenter', function () {
            const avatar = this.querySelector('.member-avatar');
            if (avatar) {
                avatar.style.filter = 'brightness(1.15) saturate(1.2)';
                avatar.style.boxShadow = '0 15px 40px rgba(248, 113, 113, 0.25)';
            }
        });
        
        card.addEventListener('mouseleave', function () {
            const avatar = this.querySelector('.member-avatar');
            if (avatar) {
                avatar.style.filter = '';
                avatar.style.boxShadow = '';
            }
        });
    });
}

/**
 * Partner cards - Premium interactions
 */
function initPartnerCardAnimations() {
    const partnerCards = document.querySelectorAll('.partner-card-compact');
    
    if (partnerCards.length === 0) return;
    
    partnerCards.forEach((card, index) => {
        // Stagger entrance
        card.style.animation = `cardEnter 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) ${index * 0.06}s both`;
        
        // Logo animation on card hover
        const logo = card.querySelector('.partner-logo-compact');
        const img = card.querySelector('.partner-logo-compact img');
        
        if (logo) {
            logo.addEventListener('mouseenter', function () {
                if (img) {
                    img.style.filter = 'brightness(1.3) saturate(1.4) contrast(1.1)';
                }
                this.style.transform = 'scale(1.15) rotate(8deg)';
                this.style.boxShadow = '0 12px 36px rgba(248, 113, 113, 0.25)';
            });
            
            logo.addEventListener('mouseleave', function () {
                if (img) {
                    img.style.filter = '';
                }
                this.style.transform = '';
                this.style.boxShadow = '';
            });
        }
        
        // Button group animation
        const buttonGroup = card.querySelector('.d-flex.gap-2');
        if (buttonGroup) {
            const buttons = buttonGroup.querySelectorAll('.btn');
            
            card.addEventListener('mouseenter', function () {
                buttons.forEach((btn, idx) => {
                    btn.style.animation = `buttonSlideIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) ${idx * 0.05}s both`;
                });
            });
        }
        
        // Ripple effect on click
        card.addEventListener('click', function (e) {
            if (e.target.closest('a, button')) return;
            
            const ripple = document.createElement('span');
            const rect = this.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;
            
            ripple.style.cssText = `
                position: absolute;
                width: ${size}px;
                height: ${size}px;
                background: radial-gradient(circle, rgba(248, 113, 113, 0.4) 0%, transparent 70%);
                border-radius: 50%;
                left: ${x}px;
                top: ${y}px;
                pointer-events: none;
                animation: partnerRipple 0.6s ease-out forwards;
            `;
            
            this.style.position = 'relative';
            this.appendChild(ripple);
            
            setTimeout(() => ripple.remove(), 600);
        });
    });
}

/**
 * Add animation keyframes
 */
(function addAnimationKeyframes() {
    const style = document.createElement('style');
    style.textContent = `
        @keyframes cardEnter {
            from {
                opacity: 0;
                transform: translateY(40px) scale(0.9);
                filter: blur(5px);
            }
            to {
                opacity: 1;
                transform: translateY(0) scale(1);
                filter: blur(0);
            }
        }
        
        @keyframes buttonSlideIn {
            from {
                opacity: 0;
                transform: translateX(-10px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }
        
        @keyframes partnerRipple {
            to {
                transform: scale(4);
                opacity: 0;
            }
        }
        
        @keyframes shimmer {
            0% {
                left: -100%;
            }
            100% {
                left: 100%;
            }
        }
        
        @keyframes rotateSlow {
            from {
                transform: rotate(0deg);
            }
            to {
                transform: rotate(360deg);
            }
        }
        
        @keyframes floatParallax {
            0%, 100% {
                transform: translateY(0px);
            }
            50% {
                transform: translateY(-30px);
            }
        }
    `;
    document.head.appendChild(style);
})();

/**
 * Pagination buttons - Enhanced interaction
 */
(function initPaginationButtons() {
    const paginationBtns = document.querySelectorAll('.pagination-btn');
    
    paginationBtns.forEach(btn => {
        btn.addEventListener('mouseenter', function () {
            this.style.transform = 'scale(1.15) rotate(15deg)';
            this.style.boxShadow = '0 15px 40px rgba(248, 113, 113, 0.4)';
        });
        
        btn.addEventListener('mouseleave', function () {
            this.style.transform = '';
            this.style.boxShadow = '';
        });
        
        btn.addEventListener('click', function () {
            this.style.animation = 'buttonClick 0.3s ease-out';
        });
    });
})();

/**
 * Lazy load observer for cards
 */
(function initLazyCardLoading() {
    const cards = document.querySelectorAll('.event-card, .member-card, .partner-card-compact');
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('in-view');
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '50px'
    });
    
    cards.forEach(card => observer.observe(card));
})();

// Expose functions
window.PremiumSections = {
    initEventCardAnimations,
    initAboutSectionAnimations,
    initPartnerCardAnimations
};
