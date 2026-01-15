/**
 * Page Transitions with HTMX
 * Provides smooth fade in/out transitions when navigating between pages
 * Works seamlessly with HTMX AJAX requests
 */

(function() {
    'use strict';

    const PageTransitions = {
        duration: 300, // Duration of fade animation in ms
        easing: 'cubic-bezier(0.4, 0, 0.2, 1)',

        /**
         * Initialize page transitions
         * Sets up event listeners for HTMX and regular navigation
         */
        init() {
            // Handle HTMX before swap (fade out)
            document.addEventListener('htmx:beforeSwap', this.handleBeforeSwap.bind(this));
            
            // Handle HTMX after swap (fade in)
            document.addEventListener('htmx:afterSwap', this.handleAfterSwap.bind(this));
            
            // Handle regular link clicks for smooth transitions
            document.addEventListener('click', this.handleLinkClick.bind(this));
            
            // Initial page fade in
            this.fadeInContent();
        },

        /**
         * Fade out content before HTMX swap
         */
        handleBeforeSwap(event) {
            const main = document.querySelector('main');
            if (!main) return;

            // Add fade-out class
            main.style.transition = `opacity ${this.duration}ms ${this.easing}`;
            main.style.opacity = '0';
        },

        /**
         * Fade in content after HTMX swap
         */
        handleAfterSwap(event) {
            const main = document.querySelector('main');
            if (!main) return;

            // Reset and fade in
            main.style.opacity = '0';
            main.style.transition = `opacity ${this.duration}ms ${this.easing}`;
            
            // Trigger reflow to ensure animation plays
            void main.offsetHeight;
            main.style.opacity = '1';

            // Scroll to top smoothly
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });

            // Trigger any necessary post-swap initialization
            this.reinitializeComponents();
        },

        /**
         * Handle regular link clicks with HTMX
         */
        handleLinkClick(event) {
            const link = event.target.closest('a');
            
            if (!link) return;
            
            // Skip special links
            const href = link.getAttribute('href');
            if (!href || 
                href.startsWith('http') ||
                href.startsWith('#') ||
                link.target === '_blank' ||
                link.hasAttribute('hx-boost') === false
            ) {
                return;
            }

            // Only handle internal links
            if (href.startsWith('/')) {
                link.setAttribute('hx-boost', 'true');
            }
        },

        /**
         * Fade in initial page content
         */
        fadeInContent() {
            const main = document.querySelector('main');
            if (!main) return;

            main.style.transition = `opacity ${this.duration}ms ${this.easing}`;
            main.style.opacity = '1';
        },

        /**
         * Reinitialize components after page change
         * Re-initialize Bootstrap components, tooltips, etc.
         */
        reinitializeComponents() {
            // Re-initialize Bootstrap tooltips
            const tooltipTriggerList = [].slice.call(
                document.querySelectorAll('[data-bs-toggle="tooltip"]')
            );
            tooltipTriggerList.forEach(tooltipTriggerEl => {
                new bootstrap.Tooltip(tooltipTriggerEl);
            });

            // Re-initialize popovers
            const popoverTriggerList = [].slice.call(
                document.querySelectorAll('[data-bs-toggle="popover"]')
            );
            popoverTriggerList.forEach(popoverTriggerEl => {
                new bootstrap.Popover(popoverTriggerEl);
            });

            // Dispatch custom event for other components to listen to
            const event = new CustomEvent('pageTransitioned', { 
                detail: { timestamp: Date.now() } 
            });
            document.dispatchEvent(event);
        },

        /**
         * Scroll to specific element smoothly
         */
        scrollToElement(selector, offset = 80) {
            const element = document.querySelector(selector);
            if (!element) return;

            const elementPosition = element.getBoundingClientRect().top + window.scrollY;
            const offsetPosition = elementPosition - offset;

            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            });
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => PageTransitions.init());
    } else {
        PageTransitions.init();
    }

    // Export for use in other scripts
    window.PageTransitions = PageTransitions;
})();
