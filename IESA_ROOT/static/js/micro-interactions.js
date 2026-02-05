/**
 * MICRO-INTERACTIONS & PERFORMANCE - Polished UX touches
 * Features: Loading states, tooltips, transitions, accessibility
 */

document.addEventListener('DOMContentLoaded', function () {
    // Initialize all micro-interactions
    initButtonFeedback();
    initTooltips();
    initLoadingStates();
    initFormAnimations();
});

/**
 * Button feedback and ripple effect
 */
function initButtonFeedback() {
    const buttons = document.querySelectorAll('.btn, button:not([class*="close"])');
    
    buttons.forEach(button => {
        button.addEventListener('click', function (e) {
            // Create ripple effect
            const ripple = document.createElement('span');
            const rect = this.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;
            
            ripple.style.cssText = `
                position: absolute;
                width: ${size}px;
                height: ${size}px;
                background: rgba(255, 255, 255, 0.5);
                border-radius: 50%;
                left: ${x}px;
                top: ${y}px;
                pointer-events: none;
                animation: rippleAnimation 0.6s ease-out;
            `;
            
            if (this.style.position !== 'absolute' && this.style.position !== 'relative' && this.style.position !== 'fixed') {
                this.style.position = 'relative';
            }
            
            this.appendChild(ripple);
            
            setTimeout(() => ripple.remove(), 600);
        });
        
        // Visual feedback on focus
        button.addEventListener('focus', function () {
            this.style.boxShadow = `0 0 0 3px rgba(248, 113, 113, 0.3)`;
        });
        
        button.addEventListener('blur', function () {
            this.style.boxShadow = '';
        });
    });
    
    // Add ripple animation keyframes
    addAnimationKeyframes(`
        @keyframes rippleAnimation {
            to {
                transform: scale(4);
                opacity: 0;
            }
        }
    `);
}

/**
 * Simple tooltips with hover
 */
function initTooltips() {
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    
    tooltipElements.forEach(el => {
        el.addEventListener('mouseenter', function () {
            const tooltip = document.createElement('div');
            const text = this.getAttribute('data-tooltip');
            
            tooltip.className = 'micro-tooltip';
            tooltip.textContent = text;
            tooltip.style.cssText = `
                position: absolute;
                background: rgba(0, 0, 0, 0.9);
                color: white;
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 0.75rem;
                white-space: nowrap;
                z-index: 10000;
                pointer-events: none;
                animation: tooltipFadeIn 0.3s ease-out;
            `;
            
            document.body.appendChild(tooltip);
            
            const rect = this.getBoundingClientRect();
            tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + window.scrollX + 'px';
            tooltip.style.top = (rect.top - tooltip.offsetHeight - 10) + window.scrollY + 'px';
            
            this._tooltip = tooltip;
        });
        
        el.addEventListener('mouseleave', function () {
            if (this._tooltip) {
                this._tooltip.remove();
                this._tooltip = null;
            }
        });
    });
    
    addAnimationKeyframes(`
        @keyframes tooltipFadeIn {
            from {
                opacity: 0;
                transform: translateY(4px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
    `);
}

/**
 * Loading state indicators
 */
function initLoadingStates() {
    const links = document.querySelectorAll('a[href*="#"]');
    
    links.forEach(link => {
        link.addEventListener('click', function () {
            // Add loading visual feedback if it's a navigation link
            if (this.dataset.loading !== 'false') {
                this.style.opacity = '0.7';
                this.style.pointerEvents = 'none';
                
                setTimeout(() => {
                    this.style.opacity = '1';
                    this.style.pointerEvents = 'auto';
                }, 500);
            }
        });
    });
}

/**
 * Form animation enhancements
 */
function initFormAnimations() {
    const inputs = document.querySelectorAll('input[type="text"], input[type="email"], textarea, select');
    
    inputs.forEach(input => {
        // Focus effect
        input.addEventListener('focus', function () {
            this.parentElement.style.transition = 'all 0.3s ease';
            this.parentElement.style.transform = 'scale(1.02)';
        });
        
        // Blur effect
        input.addEventListener('blur', function () {
            this.parentElement.style.transform = 'scale(1)';
        });
        
        // Input animation
        input.addEventListener('input', function () {
            if (this.value) {
                this.style.borderColor = '#f87171';
                this.style.boxShadow = '0 0 0 3px rgba(248, 113, 113, 0.1)';
            }
        });
    });
}

/**
 * Utility function to add keyframe animations
 */
function addAnimationKeyframes(keyframes) {
    if (!window._animationStyleSheet) {
        const style = document.createElement('style');
        document.head.appendChild(style);
        window._animationStyleSheet = style;
    }
    
    window._animationStyleSheet.appendChild(document.createTextNode(keyframes));
}

/**
 * Scroll to top button
 */
(function initScrollToTop() {
    const scrollButton = document.createElement('button');
    scrollButton.id = 'scroll-to-top';
    scrollButton.innerHTML = '↑';
    scrollButton.style.cssText = `
        position: fixed;
        bottom: 2rem;
        right: 2rem;
        width: 50px;
        height: 50px;
        border-radius: 50%;
        background: linear-gradient(135deg, #f87171 0%, #fb7185 100%);
        color: white;
        border: none;
        cursor: pointer;
        opacity: 0;
        pointer-events: none;
        transition: all 0.3s ease;
        z-index: 999;
        font-size: 1.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 4px 16px rgba(248, 113, 113, 0.3);
    `;
    
    document.body.appendChild(scrollButton);
    
    window.addEventListener('scroll', function () {
        if (window.pageYOffset > 300) {
            scrollButton.style.opacity = '1';
            scrollButton.style.pointerEvents = 'auto';
        } else {
            scrollButton.style.opacity = '0';
            scrollButton.style.pointerEvents = 'none';
        }
    });
    
    scrollButton.addEventListener('click', function () {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
    
    scrollButton.addEventListener('mouseenter', function () {
        this.style.transform = 'scale(1.1)';
    });
    
    scrollButton.addEventListener('mouseleave', function () {
        this.style.transform = 'scale(1)';
    });
})();

/**
 * Page visibility detection (pause animations when tab is not active)
 */
document.addEventListener('visibilitychange', function () {
    const allElements = document.querySelectorAll('[style*="animation"]');
    
    if (document.hidden) {
        allElements.forEach(el => {
            el.style.animationPlayState = 'paused';
        });
    } else {
        allElements.forEach(el => {
            el.style.animationPlayState = 'running';
        });
    }
});

/**
 * Keyboard navigation enhancement
 */
document.addEventListener('keydown', function (e) {
    // Escape key to close modals or clear focus
    if (e.key === 'Escape') {
        const activeElement = document.activeElement;
        if (activeElement) {
            activeElement.blur();
        }
    }
    
    // Tab navigation visual feedback (already in CSS, but ensure it works)
    if (e.key === 'Tab') {
        document.body.classList.add('keyboard-nav');
    }
});

/**
 * Expose functions for external use
 */
window.MicroInteractions = {
    initButtonFeedback,
    initTooltips,
    initLoadingStates,
    initFormAnimations,
    addAnimationKeyframes
};

console.log('✨ Micro-interactions initialized');
