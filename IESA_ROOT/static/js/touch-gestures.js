/**
 * Mobile Swipe & Gesture Recognition
 * Advanced touch gesture support for enhanced mobile UX
 * Features: swipe, long press, pinch, double tap
 */

(function() {
    'use strict';

    const GestureHandler = {
        touches: [],
        startX: 0,
        startY: 0,
        startTime: 0,
        gestures: {
            swipe: [],
            longPress: [],
            doubleTap: [],
            pinch: []
        },

        /**
         * Initialize gesture recognition
         */
        init() {
            // Register swipe handlers
            this.registerSwipeHandlers();
            
            // Register long press handlers
            this.registerLongPressHandlers();
            
            // Register double tap handlers
            this.registerDoubleTapHandlers();
            
            // Register pinch handlers
            this.registerPinchHandlers();

            // Touch event listeners
            document.addEventListener('touchstart', this.handleTouchStart.bind(this), { passive: true });
            document.addEventListener('touchmove', this.handleTouchMove.bind(this), { passive: true });
            document.addEventListener('touchend', this.handleTouchEnd.bind(this), { passive: true });
        },

        /**
         * Register swipe gesture handlers
         */
        registerSwipeHandlers() {
            const swipeElements = document.querySelectorAll('[data-swipe]');
            
            swipeElements.forEach(element => {
                const direction = element.dataset.swipe;
                const action = element.dataset.swipeAction;
                
                if (action) {
                    element.addEventListener('swipe', (e) => {
                        if (e.detail.direction === direction) {
                            this.triggerAction(element, action);
                        }
                    });
                }
            });
        },

        /**
         * Register long press handlers
         */
        registerLongPressHandlers() {
            const longPressElements = document.querySelectorAll('[data-long-press]');
            
            longPressElements.forEach(element => {
                element.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                });
            });
        },

        /**
         * Register double tap handlers
         */
        registerDoubleTapHandlers() {
            const doubleTapElements = document.querySelectorAll('[data-double-tap]');
            
            doubleTapElements.forEach(element => {
                element.addEventListener('doubletap', () => {
                    const action = element.dataset.doubleTap;
                    this.triggerAction(element, action);
                });
            });
        },

        /**
         * Register pinch handlers
         */
        registerPinchHandlers() {
            const pinchElements = document.querySelectorAll('[data-pinch]');
            
            pinchElements.forEach(element => {
                element.addEventListener('pinch', (e) => {
                    console.log(`Pinch detected with scale: ${e.detail.scale}`);
                });
            });
        },

        /**
         * Handle touch start
         */
        handleTouchStart(event) {
            const touch = event.touches[0];
            this.startX = touch.clientX;
            this.startY = touch.clientY;
            this.startTime = Date.now();
            this.touches = Array.from(event.touches);
        },

        /**
         * Handle touch move
         */
        handleTouchMove(event) {
            if (event.touches.length === 2) {
                // Pinch gesture
                this.handlePinch(event);
            }
        },

        /**
         * Handle touch end
         */
        handleTouchEnd(event) {
            const touch = event.changedTouches[0];
            const endX = touch.clientX;
            const endY = touch.clientY;
            const endTime = Date.now();
            const duration = endTime - this.startTime;

            // Detect swipe
            this.detectSwipe(this.startX, this.startY, endX, endY, duration, event.target);

            // Detect long press
            if (duration > 500 && this.getDistance(this.startX, this.startY, endX, endY) < 50) {
                this.detectLongPress(event.target);
            }

            // Detect double tap
            this.detectDoubleTap(event.target, endTime);
        },

        /**
         * Detect swipe gesture
         */
        detectSwipe(startX, startY, endX, endY, duration, target) {
            const minDistance = 50;
            const maxDuration = 500;
            const distance = this.getDistance(startX, startY, endX, endY);
            const deltaX = endX - startX;
            const deltaY = endY - startY;

            if (distance < minDistance || duration > maxDuration) {
                return;
            }

            let direction = '';
            if (Math.abs(deltaX) > Math.abs(deltaY)) {
                direction = deltaX > 0 ? 'right' : 'left';
            } else {
                direction = deltaY > 0 ? 'down' : 'up';
            }

            // Find closest swipe-enabled element
            let element = target;
            while (element && !element.hasAttribute('data-swipe')) {
                element = element.parentElement;
            }

            if (element) {
                const event = new CustomEvent('swipe', {
                    detail: { direction, deltaX, deltaY, target: element }
                });
                element.dispatchEvent(event);
            }
        },

        /**
         * Detect long press
         */
        detectLongPress(target) {
            let element = target;
            while (element && !element.hasAttribute('data-long-press')) {
                element = element.parentElement;
            }

            if (element) {
                const event = new CustomEvent('longpress', { detail: { target: element } });
                element.dispatchEvent(event);
            }
        },

        /**
         * Detect double tap
         */
        detectDoubleTap(target, currentTime) {
            if (!this.lastTapTime) {
                this.lastTapTime = currentTime;
                this.lastTapTarget = target;
                return;
            }

            if (currentTime - this.lastTapTime < 300 && this.lastTapTarget === target) {
                let element = target;
                while (element && !element.hasAttribute('data-double-tap')) {
                    element = element.parentElement;
                }

                if (element) {
                    const event = new CustomEvent('doubletap', { detail: { target: element } });
                    element.dispatchEvent(event);
                }
            }

            this.lastTapTime = currentTime;
            this.lastTapTarget = target;
        },

        /**
         * Handle pinch gesture
         */
        handlePinch(event) {
            const touch1 = event.touches[0];
            const touch2 = event.touches[1];
            const distance = this.getDistance(touch1.clientX, touch1.clientY, touch2.clientX, touch2.clientY);

            if (!this.lastPinchDistance) {
                this.lastPinchDistance = distance;
                return;
            }

            const scale = distance / this.lastPinchDistance;
            const element = event.target.closest('[data-pinch]');

            if (element) {
                const pinchEvent = new CustomEvent('pinch', {
                    detail: { scale, distance }
                });
                element.dispatchEvent(pinchEvent);
            }

            this.lastPinchDistance = distance;
        },

        /**
         * Calculate distance between two points
         */
        getDistance(x1, y1, x2, y2) {
            return Math.sqrt(Math.pow(x2 - x1, 2) + Math.pow(y2 - y1, 2));
        },

        /**
         * Trigger action based on gesture
         */
        triggerAction(element, action) {
            switch (action) {
                case 'navigate':
                    const href = element.dataset.href || element.getAttribute('href');
                    if (href) window.location.href = href;
                    break;
                case 'toggle':
                    element.classList.toggle(element.dataset.toggleClass || 'active');
                    break;
                case 'submit':
                    const form = element.closest('form');
                    if (form) form.submit();
                    break;
                default:
                    // Trigger custom event
                    element.dispatchEvent(new CustomEvent(action));
            }
        }
    };

    /**
     * Carousel/Slider with Swipe Support
     */
    const SwipeCarousel = {
        init() {
            const carousels = document.querySelectorAll('[data-swipe-carousel]');
            
            carousels.forEach(carousel => {
                carousel.addEventListener('swipe', (e) => {
                    this.handleCarouselSwipe(carousel, e.detail.direction);
                });
            });
        },

        handleCarouselSwipe(carousel, direction) {
            const prevBtn = carousel.querySelector('[data-carousel-prev]');
            const nextBtn = carousel.querySelector('[data-carousel-next]');

            if (direction === 'right' && prevBtn) {
                prevBtn.click();
            } else if (direction === 'left' && nextBtn) {
                nextBtn.click();
            }
        }
    };

    /**
     * Swipe to Dismiss/Delete
     */
    const SwipeToDismiss = {
        init() {
            const dismissElements = document.querySelectorAll('[data-swipe-dismiss]');
            
            dismissElements.forEach(element => {
                element.addEventListener('swipe', (e) => {
                    this.handleDismiss(element, e.detail.direction);
                });
            });
        },

        handleDismiss(element, direction) {
            const dismissDirection = element.dataset.swipeDismiss;
            
            if (dismissDirection === 'both' || dismissDirection === direction) {
                element.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                element.style.opacity = '0';
                element.style.transform = `translateX(${direction === 'left' ? '-100%' : '100%'})`;
                
                setTimeout(() => {
                    element.remove();
                }, 300);
            }
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            GestureHandler.init();
            SwipeCarousel.init();
            SwipeToDismiss.init();
        });
    } else {
        GestureHandler.init();
        SwipeCarousel.init();
        SwipeToDismiss.init();
    }

    // Export for use in other scripts
    window.GestureHandler = GestureHandler;
})();
