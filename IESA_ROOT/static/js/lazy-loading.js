/**
 * Lazy Loading Images & Media
 * Efficient image loading with blur-up technique and fade-in animations
 */

(function() {
    'use strict';

    const LazyLoading = {
        images: [],
        observer: null,

        /**
         * Initialize lazy loading
         */
        init() {
            // Get all lazy loadable images
            this.images = Array.from(document.querySelectorAll('img[data-src], img[loading="lazy"]'));
            
            if (this.images.length === 0) return;

            // Use Intersection Observer for efficient loading
            this.setupIntersectionObserver();

            // Listen for dynamically added images
            this.observeDOM();
        },

        /**
         * Setup Intersection Observer for lazy loading
         */
        setupIntersectionObserver() {
            this.observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        this.loadImage(entry.target);
                        this.observer.unobserve(entry.target);
                    }
                });
            }, {
                rootMargin: '50px 0px',
                threshold: 0.01
            });

            this.images.forEach(img => this.observer.observe(img));
        },

        /**
         * Load single image
         */
        loadImage(img) {
            // Skip if already loaded
            if (img.classList.contains('lazy-loaded')) return;

            const srcset = img.dataset.srcset;
            const src = img.dataset.src || img.src;
            const alt = img.dataset.alt || img.alt || '';

            // Preload image
            const tempImg = new Image();
            
            tempImg.onload = () => {
                img.src = src;
                if (srcset) {
                    img.srcset = srcset;
                }
                if (alt) {
                    img.alt = alt;
                }
                
                // Add loaded class for CSS animations
                img.classList.add('lazy-loaded');
                img.classList.remove('lazy-loading');

                // Trigger custom event
                const event = new CustomEvent('imageLoaded', { detail: { img } });
                img.dispatchEvent(event);

                // Notify parent container
                const parent = img.closest('[data-lazy-container]');
                if (parent) {
                    parent.classList.add('image-loaded');
                }
            };

            tempImg.onerror = () => {
                img.classList.add('lazy-error');
                console.warn(`Failed to load image: ${src}`);
            };

            // Add loading class
            img.classList.add('lazy-loading');

            // Start loading
            tempImg.src = src;
            if (srcset) {
                tempImg.srcset = srcset;
            }
        },

        /**
         * Observe DOM for dynamically added images
         */
        observeDOM() {
            const mutationObserver = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === 1) {
                            const images = node.querySelectorAll('img[data-src], img[loading="lazy"]');
                            images.forEach(img => {
                                if (!this.images.includes(img)) {
                                    this.images.push(img);
                                    this.observer.observe(img);
                                }
                            });
                        }
                    });
                });
            });

            mutationObserver.observe(document.body, {
                childList: true,
                subtree: true
            });
        },

        /**
         * Load all images immediately
         */
        loadAll() {
            this.images.forEach(img => {
                if (!img.classList.contains('lazy-loaded')) {
                    this.loadImage(img);
                }
            });
        },

        /**
         * Load images in container
         */
        loadInContainer(container) {
            const images = container.querySelectorAll('img[data-src], img[loading="lazy"]');
            images.forEach(img => this.loadImage(img));
        }
    };

    /**
     * Responsive Image Helper
     * Automatically serve correct image size based on device
     */
    const ResponsiveImages = {
        init() {
            // Add picture element support detection
            if ('picture' in document) {
                this.setupPictureElements();
            }

            // Optimize image sizes for viewport
            this.optimizeImageSizes();
            window.addEventListener('resize', this.optimizeImageSizes.bind(this), { passive: true });
        },

        /**
         * Setup picture elements for responsive images
         */
        setupPictureElements() {
            const pictures = document.querySelectorAll('picture');
            
            pictures.forEach(picture => {
                const sources = picture.querySelectorAll('source');
                const img = picture.querySelector('img');

                if (img && sources.length > 0) {
                    // Preload source based on media queries
                    sources.forEach(source => {
                        const media = source.getAttribute('media');
                        if (media && window.matchMedia(media).matches) {
                            const srcset = source.getAttribute('srcset');
                            if (srcset) {
                                img.dataset.srcset = srcset;
                            }
                        }
                    });
                }
            });
        },

        /**
         * Optimize image sizes for viewport
         */
        optimizeImageSizes() {
            const images = document.querySelectorAll('img[data-sizes]');
            const width = window.innerWidth;

            images.forEach(img => {
                const sizes = img.dataset.sizes;
                if (!sizes) return;

                try {
                    const sizeMap = JSON.parse(sizes);
                    Object.entries(sizeMap).forEach(([breakpoint, size]) => {
                        if (parseInt(breakpoint) <= width) {
                            img.sizes = size;
                        }
                    });
                } catch (e) {
                    console.warn('Invalid sizes data:', sizes);
                }
            });
        }
    };

    /**
     * Blur-up Image Loading
     * Low-quality image placeholder that fades to high-quality
     */
    const BlurUpImages = {
        init() {
            const placeholders = document.querySelectorAll('[data-blur-up]');
            
            placeholders.forEach(container => {
                const lowQuality = container.querySelector('img[data-blur-low]');
                const highQuality = container.querySelector('img[data-blur-high]');

                if (lowQuality && highQuality) {
                    // Start loading high-quality image
                    const tempImg = new Image();
                    tempImg.onload = () => {
                        highQuality.src = highQuality.dataset.src;
                        container.classList.add('blur-up-loaded');
                    };
                    tempImg.src = highQuality.dataset.src;
                }
            });
        }
    };

    /**
     * Image Preloading
     * Preload critical images for faster perceived performance
     */
    const ImagePreloading = {
        init() {
            // Preload images marked as critical
            const criticalImages = document.querySelectorAll('img[data-preload]');
            
            criticalImages.forEach(img => {
                const preloadImg = new Image();
                preloadImg.src = img.dataset.src || img.src;
            });
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            LazyLoading.init();
            ResponsiveImages.init();
            BlurUpImages.init();
            ImagePreloading.init();
        });
    } else {
        LazyLoading.init();
        ResponsiveImages.init();
        BlurUpImages.init();
        ImagePreloading.init();
    }

    // Export for use in other scripts
    window.LazyLoading = LazyLoading;
    window.ResponsiveImages = ResponsiveImages;
})();
