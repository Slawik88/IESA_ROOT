/**
 * Smooth Scroll & Anchor Navigation
 * Provides smooth scrolling to anchor links with customizable offsets
 */

(function() {
    'use strict';

    const SmoothScroll = {
        offsetTop: 80, // Offset from header height
        duration: 500, // Duration in ms
        easing: 'cubic-bezier(0.4, 0, 0.2, 1)',

        /**
         * Initialize smooth scroll
         */
        init() {
            // Handle anchor clicks
            document.addEventListener('click', this.handleAnchorClick.bind(this));
            
            // Smooth scroll on page load if hash present
            if (window.location.hash) {
                setTimeout(() => this.scrollToElement(window.location.hash), 100);
            }

            // Listen for hash changes
            window.addEventListener('hashchange', this.handleHashChange.bind(this));

            // Update active nav items based on scroll position
            window.addEventListener('scroll', this.updateActiveNavItem.bind(this), { passive: true });
        },

        /**
         * Handle anchor link clicks
         */
        handleAnchorClick(event) {
            const link = event.target.closest('a');
            
            if (!link) return;
            
            const href = link.getAttribute('href');
            
            // Check if it's an anchor link
            if (href && href.startsWith('#') && href.length > 1) {
                event.preventDefault();
                this.scrollToElement(href);
                
                // Update history
                window.history.pushState(null, '', href);
            }
        },

        /**
         * Handle hash changes from history
         */
        handleHashChange(event) {
            const hash = window.location.hash;
            if (hash) {
                setTimeout(() => this.scrollToElement(hash), 100);
            }
        },

        /**
         * Scroll to element with smooth animation
         */
        scrollToElement(selector) {
            const element = document.querySelector(selector);
            if (!element) return;

            const elementPosition = element.getBoundingClientRect().top + window.scrollY;
            const offsetPosition = elementPosition - this.offsetTop;

            // Use native smooth scroll if supported
            if ('scrollBehavior' in document.documentElement.style) {
                window.scrollTo({
                    top: offsetPosition,
                    behavior: 'smooth'
                });
            } else {
                // Fallback for older browsers
                this.animateScroll(offsetPosition);
            }

            // Focus element for accessibility
            element.focus({ preventScroll: true });
        },

        /**
         * Animate scroll for browsers without native support
         */
        animateScroll(targetPosition) {
            const startPosition = window.scrollY;
            const distance = targetPosition - startPosition;
            const duration = this.duration;
            let start = null;

            const animation = (currentTime) => {
                if (start === null) start = currentTime;
                const elapsed = currentTime - start;
                const progress = Math.min(elapsed / duration, 1);

                // Easing function
                const ease = this.easeInOutCubic(progress);
                window.scrollTo(0, startPosition + distance * ease);

                if (elapsed < duration) {
                    requestAnimationFrame(animation);
                }
            };

            requestAnimationFrame(animation);
        },

        /**
         * Easing function for smooth animation
         */
        easeInOutCubic(t) {
            return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        },

        /**
         * Update active navigation items based on scroll position
         */
        updateActiveNavItem() {
            const sections = document.querySelectorAll('[id]');
            if (!sections.length) return;

            let currentSection = null;
            const scrollPosition = window.scrollY + this.offsetTop + 50;

            sections.forEach(section => {
                if (section.offsetTop <= scrollPosition) {
                    currentSection = section;
                }
            });

            if (!currentSection) return;

            // Update nav items
            document.querySelectorAll('a[href^="#"]').forEach(link => {
                link.classList.remove('active');
                
                if (link.getAttribute('href') === `#${currentSection.id}`) {
                    link.classList.add('active');
                    
                    // Also activate parent nav if in dropdown
                    const parent = link.closest('.nav-item');
                    if (parent) {
                        parent.classList.add('active');
                    }
                }
            });
        },

        /**
         * Scroll to top of page
         */
        scrollToTop() {
            this.animateScroll(0);
        },

        /**
         * Check if element is in viewport
         */
        isInViewport(element) {
            const rect = element.getBoundingClientRect();
            return (
                rect.top >= 0 &&
                rect.left >= 0 &&
                rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                rect.right <= (window.innerWidth || document.documentElement.clientWidth)
            );
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => SmoothScroll.init());
    } else {
        SmoothScroll.init();
    }

    // Initialize back to top button
    const backToTopBtn = document.getElementById('back-to-top');
    if (backToTopBtn) {
        // Show button when scrolled down
        window.addEventListener('scroll', () => {
            if (window.scrollY > 300) {
                backToTopBtn.style.display = 'block';
                backToTopBtn.style.opacity = '1';
            } else {
                backToTopBtn.style.opacity = '0';
                setTimeout(() => {
                    if (window.scrollY <= 300) {
                        backToTopBtn.style.display = 'none';
                    }
                }, 300);
            }
        }, { passive: true });

        // Click to scroll to top
        backToTopBtn.addEventListener('click', () => SmoothScroll.scrollToTop());
    }

    // Export for use in other scripts
    window.SmoothScroll = SmoothScroll;
})();
