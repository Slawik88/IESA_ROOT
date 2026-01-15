/**
 * Parallax Effects
 * Creates beautiful parallax scrolling effects for hero sections and backgrounds
 */

(function() {
    'use strict';

    const Parallax = {
        elements: [],
        isReducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        lastScrollY: 0,

        /**
         * Initialize parallax effects
         */
        init() {
            // Disable parallax if user prefers reduced motion
            if (this.isReducedMotion) return;

            // Find all parallax elements
            this.elements = Array.from(document.querySelectorAll('[data-parallax]'));
            
            if (this.elements.length === 0) return;

            // Listen for scroll
            window.addEventListener('scroll', this.handleScroll.bind(this), { passive: true });

            // Initial calculation
            this.updateParallax();

            // Listen for resize
            window.addEventListener('resize', this.updateParallax.bind(this), { passive: true });

            // Watch for dynamically added parallax elements
            this.observeDOM();
        },

        /**
         * Handle scroll events
         */
        handleScroll() {
            this.lastScrollY = window.scrollY;
            requestAnimationFrame(() => this.updateParallax());
        },

        /**
         * Update parallax positions
         */
        updateParallax() {
            this.elements.forEach(element => {
                const speed = parseFloat(element.dataset.parallax) || 0.5;
                const offset = element.dataset.parallaxOffset || 0;
                const rect = element.getBoundingClientRect();
                
                // Only update if element is in viewport or near it
                if (rect.bottom > -500 && rect.top < window.innerHeight + 500) {
                    const scrolled = window.scrollY + rect.top;
                    const yPos = (scrolled * speed) + parseFloat(offset);
                    element.style.transform = `translateY(${yPos}px)`;
                }
            });
        },

        /**
         * Observe DOM for dynamically added parallax elements
         */
        observeDOM() {
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === 1) { // Element node
                            const parallaxEl = node.querySelector('[data-parallax]');
                            if (parallaxEl) {
                                this.elements.push(parallaxEl);
                            }
                        }
                    });
                });
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }
    };

    /**
     * Hero Parallax Effect
     * Special handling for hero sections
     */
    const HeroParallax = {
        hero: null,
        background: null,

        init() {
            this.hero = document.querySelector('.hero, [data-hero]');
            if (!this.hero) return;

            // Create background layer if not exists
            this.background = this.hero.querySelector('.parallax-background');
            if (!this.background) {
                this.background = document.createElement('div');
                this.background.className = 'parallax-background';
                this.hero.style.position = 'relative';
                this.hero.style.overflow = 'hidden';
                this.hero.insertBefore(this.background, this.hero.firstChild);
            }

            window.addEventListener('scroll', this.handleHeroScroll.bind(this), { passive: true });
            window.addEventListener('resize', this.updateHeroHeight.bind(this), { passive: true });
            
            this.updateHeroHeight();
        },

        handleHeroScroll() {
            requestAnimationFrame(() => {
                const scrolled = window.scrollY;
                const heroTop = this.hero.getBoundingClientRect().top + scrolled;
                
                // Only apply parallax while hero is visible
                if (scrolled < heroTop + this.hero.offsetHeight) {
                    const parallaxOffset = (scrolled - heroTop) * 0.5;
                    this.background.style.transform = `translateY(${parallaxOffset}px)`;
                }
            });
        },

        updateHeroHeight() {
            if (this.background) {
                this.background.style.height = (this.hero.offsetHeight * 1.3) + 'px';
                this.background.style.top = -(this.hero.offsetHeight * 0.15) + 'px';
            }
        }
    };

    /**
     * Tilt Effect on Cards
     * Subtle 3D tilt effect on hover
     */
    const TiltEffect = {
        elements: [],

        init() {
            this.elements = Array.from(document.querySelectorAll('[data-tilt]'));
            
            this.elements.forEach(element => {
                element.addEventListener('mousemove', this.handleMouseMove.bind(this));
                element.addEventListener('mouseleave', this.handleMouseLeave.bind(this));
            });
        },

        handleMouseMove(event) {
            const element = event.currentTarget;
            const rect = element.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;

            const centerX = rect.width / 2;
            const centerY = rect.height / 2;

            const angleX = (y - centerY) / 10;
            const angleY = (centerX - x) / 10;

            element.style.transform = `
                perspective(1000px)
                rotateX(${angleX}deg)
                rotateY(${angleY}deg)
                scale(1.05)
            `;
        },

        handleMouseLeave(event) {
            const element = event.currentTarget;
            element.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale(1)';
        }
    };

    /**
     * Fade In on Scroll
     * Elements fade in as they enter viewport
     */
    const FadeInOnScroll = {
        elements: [],
        observer: null,

        init() {
            this.elements = Array.from(document.querySelectorAll('[data-fade-in]'));
            
            if (!this.elements.length) return;

            // Use Intersection Observer for performance
            this.observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('fade-in-visible');
                        this.observer.unobserve(entry.target);
                    }
                });
            }, {
                threshold: 0.1,
                rootMargin: '0px 0px -50px 0px'
            });

            this.elements.forEach(element => this.observer.observe(element));
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            Parallax.init();
            HeroParallax.init();
            TiltEffect.init();
            FadeInOnScroll.init();
        });
    } else {
        Parallax.init();
        HeroParallax.init();
        TiltEffect.init();
        FadeInOnScroll.init();
    }

    // Export for use in other scripts
    window.Parallax = Parallax;
    window.HeroParallax = HeroParallax;
    window.TiltEffect = TiltEffect;
    window.FadeInOnScroll = FadeInOnScroll;
})();
