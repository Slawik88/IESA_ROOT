/**
 * Mobile Interactions & Enhanced UX
 * JavaScript для улучшения пользовательского опыта на мобильных устройствах
 */

(function() {
    'use strict';

    // ========================================
    // 1. MOBILE MENU TOGGLE
    // ========================================
    function initMobileMenu() {
        const menuToggle = document.querySelector('.navbar-toggler');
        const menuContent = document.querySelector('.navbar-collapse');
        const body = document.body;

        if (!menuToggle || !menuContent) return;

        menuToggle.addEventListener('click', function() {
            const isExpanded = menuToggle.getAttribute('aria-expanded') === 'true';
            
            // Toggle menu
            if (isExpanded) {
                menuContent.classList.remove('show');
                body.classList.remove('mobile-menu-open');
                menuToggle.setAttribute('aria-expanded', 'false');
            } else {
                menuContent.classList.add('show');
                body.classList.add('mobile-menu-open');
                menuToggle.setAttribute('aria-expanded', 'true');
            }
        });

        // Close menu when clicking outside
        document.addEventListener('click', function(e) {
            if (!menuToggle.contains(e.target) && !menuContent.contains(e.target)) {
                menuContent.classList.remove('show');
                body.classList.remove('mobile-menu-open');
                menuToggle.setAttribute('aria-expanded', 'false');
            }
        });

        // Close menu on menu item click (mobile)
        if (window.innerWidth <= 768) {
            menuContent.querySelectorAll('.nav-link').forEach(link => {
                link.addEventListener('click', function() {
                    menuContent.classList.remove('show');
                    body.classList.remove('mobile-menu-open');
                    menuToggle.setAttribute('aria-expanded', 'false');
                });
            });
        }
    }

    // ========================================
    // 2. NAVBAR SCROLL SHADOW
    // ========================================
    function initNavbarScrollEffect() {
        const navbar = document.querySelector('.navbar');
        if (!navbar) return;

        let lastScroll = 0;
        
        window.addEventListener('scroll', function() {
            const currentScroll = window.pageYOffset;
            
            // Add shadow on scroll
            if (currentScroll > 10) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }

            // Optional: Hide navbar on scroll down (uncomment if needed)
            // if (currentScroll > lastScroll && currentScroll > 100) {
            //     navbar.style.transform = 'translateY(-100%)';
            // } else {
            //     navbar.style.transform = 'translateY(0)';
            // }

            lastScroll = currentScroll;
        });
    }

    // ========================================
    // 3. MODAL ENHANCEMENTS
    // ========================================
    function initModalEnhancements() {
        // Add backdrop click to close
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', function(e) {
                if (e.target === modal) {
                    closeModal(modal);
                }
            });

            // ESC key to close
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape' && modal.classList.contains('active')) {
                    closeModal(modal);
                }
            });
        });

        // Modal open/close functions
        window.openModal = function(modalId) {
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.classList.add('active');
                document.body.classList.add('modal-open');
                modal.setAttribute('aria-hidden', 'false');
            }
        };

        window.closeModal = function(modal) {
            if (typeof modal === 'string') {
                modal = document.getElementById(modal);
            }
            if (modal) {
                modal.classList.remove('active');
                document.body.classList.remove('modal-open');
                modal.setAttribute('aria-hidden', 'true');
            }
        };
    }

    // ========================================
    // 4. TOUCH RIPPLE EFFECT
    // ========================================
    function initTouchRipple() {
        document.querySelectorAll('.btn, .card').forEach(element => {
            element.addEventListener('touchstart', function(e) {
                const ripple = document.createElement('span');
                ripple.classList.add('ripple');
                
                const rect = element.getBoundingClientRect();
                const size = Math.max(rect.width, rect.height);
                const x = e.touches[0].clientX - rect.left - size / 2;
                const y = e.touches[0].clientY - rect.top - size / 2;
                
                ripple.style.width = ripple.style.height = size + 'px';
                ripple.style.left = x + 'px';
                ripple.style.top = y + 'px';
                
                element.appendChild(ripple);
                
                setTimeout(() => ripple.remove(), 600);
            });
        });
    }

    // ========================================
    // 5. BOTTOM SHEET
    // ========================================
    function initBottomSheet() {
        window.openBottomSheet = function(sheetId) {
            const sheet = document.getElementById(sheetId);
            if (sheet) {
                sheet.classList.add('active');
                document.body.classList.add('bottom-sheet-open');
            }
        };

        window.closeBottomSheet = function(sheetId) {
            const sheet = document.getElementById(sheetId);
            if (sheet) {
                sheet.classList.remove('active');
                document.body.classList.remove('bottom-sheet-open');
            }
        };

        // Swipe to close bottom sheets
        document.querySelectorAll('.bottom-sheet').forEach(sheet => {
            let startY = 0;
            let currentY = 0;

            sheet.addEventListener('touchstart', function(e) {
                startY = e.touches[0].clientY;
            });

            sheet.addEventListener('touchmove', function(e) {
                currentY = e.touches[0].clientY;
                const diff = currentY - startY;
                
                if (diff > 0) {
                    sheet.style.transform = `translateY(${diff}px)`;
                }
            });

            sheet.addEventListener('touchend', function() {
                const diff = currentY - startY;
                
                if (diff > 100) {
                    closeBottomSheet(sheet.id);
                }
                
                sheet.style.transform = '';
                startY = 0;
                currentY = 0;
            });
        });
    }

    // ========================================
    // 6. FORM ENHANCEMENTS
    // ========================================
    function initFormEnhancements() {
        // Prevent iOS zoom on input focus
        if (/iPhone|iPad|iPod/i.test(navigator.userAgent)) {
            const inputs = document.querySelectorAll('input, select, textarea');
            inputs.forEach(input => {
                if (!input.style.fontSize || parseFloat(input.style.fontSize) < 16) {
                    input.style.fontSize = '16px';
                }
            });
        }

        // Add floating labels effect
        document.querySelectorAll('.form-control').forEach(input => {
            input.addEventListener('focus', function() {
                this.parentElement.classList.add('focused');
            });

            input.addEventListener('blur', function() {
                if (!this.value) {
                    this.parentElement.classList.remove('focused');
                }
            });
        });

        // Show password toggle
        document.querySelectorAll('input[type="password"]').forEach(input => {
            const toggleBtn = document.createElement('button');
            toggleBtn.type = 'button';
            toggleBtn.className = 'btn-password-toggle';
            toggleBtn.innerHTML = '<i class="fas fa-eye"></i>';
            toggleBtn.setAttribute('aria-label', 'Show password');
            
            input.parentElement.style.position = 'relative';
            input.parentElement.appendChild(toggleBtn);
            
            toggleBtn.addEventListener('click', function() {
                if (input.type === 'password') {
                    input.type = 'text';
                    toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i>';
                    toggleBtn.setAttribute('aria-label', 'Hide password');
                } else {
                    input.type = 'password';
                    toggleBtn.innerHTML = '<i class="fas fa-eye"></i>';
                    toggleBtn.setAttribute('aria-label', 'Show password');
                }
            });
        });
    }

    // ========================================
    // 7. LAZY LOADING IMAGES
    // ========================================
    function initLazyLoading() {
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src;
                        img.classList.remove('lazy');
                        observer.unobserve(img);
                    }
                });
            });

            document.querySelectorAll('img.lazy').forEach(img => {
                imageObserver.observe(img);
            });
        } else {
            // Fallback for browsers without IntersectionObserver
            document.querySelectorAll('img.lazy').forEach(img => {
                img.src = img.dataset.src;
                img.classList.remove('lazy');
            });
        }
    }

    // ========================================
    // 8. PULL TO REFRESH (Optional)
    // ========================================
    function initPullToRefresh() {
        let startY = 0;
        let pulling = false;
        const pullIndicator = document.querySelector('.pull-to-refresh');

        if (!pullIndicator) return;

        document.addEventListener('touchstart', function(e) {
            if (window.pageYOffset === 0) {
                startY = e.touches[0].clientY;
            }
        });

        document.addEventListener('touchmove', function(e) {
            const currentY = e.touches[0].clientY;
            const diff = currentY - startY;

            if (diff > 0 && window.pageYOffset === 0) {
                pulling = true;
                pullIndicator.style.opacity = Math.min(diff / 100, 1);
            }
        });

        document.addEventListener('touchend', function() {
            if (pulling && pullIndicator.style.opacity >= 0.8) {
                window.location.reload();
            }
            
            pulling = false;
            pullIndicator.style.opacity = 0;
        });
    }

    // ========================================
    // 9. SMOOTH SCROLL FOR ANCHOR LINKS
    // ========================================
    function initSmoothScroll() {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function(e) {
                const targetId = this.getAttribute('href');
                if (targetId === '#') return;

                const targetElement = document.querySelector(targetId);
                if (targetElement) {
                    e.preventDefault();
                    targetElement.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });
    }

    // ========================================
    // 10. BACK TO TOP BUTTON
    // ========================================
    function initBackToTop() {
        const backToTopBtn = document.getElementById('back-to-top');
        if (!backToTopBtn) return;

        window.addEventListener('scroll', function() {
            if (window.pageYOffset > 300) {
                backToTopBtn.classList.add('visible');
            } else {
                backToTopBtn.classList.remove('visible');
            }
        });

        backToTopBtn.addEventListener('click', function() {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }

    // ========================================
    // 11. TOAST NOTIFICATIONS
    // ========================================
    window.showToast = function(message, type = 'info', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => toast.classList.add('show'), 100);
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    };

    // ========================================
    // 12. ACCESSIBILITY ENHANCEMENTS
    // ========================================
    function initAccessibility() {
        // Skip to main content
        const skipLink = document.querySelector('.skip-to-main');
        if (skipLink) {
            skipLink.addEventListener('click', function(e) {
                e.preventDefault();
                const mainContent = document.getElementById('main-content');
                if (mainContent) {
                    mainContent.setAttribute('tabindex', '-1');
                    mainContent.focus();
                }
            });
        }

        // Trap focus in modals
        document.querySelectorAll('.modal').forEach(modal => {
            const focusableElements = modal.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );
            const firstFocusable = focusableElements[0];
            const lastFocusable = focusableElements[focusableElements.length - 1];

            modal.addEventListener('keydown', function(e) {
                if (e.key === 'Tab') {
                    if (e.shiftKey) {
                        if (document.activeElement === firstFocusable) {
                            lastFocusable.focus();
                            e.preventDefault();
                        }
                    } else {
                        if (document.activeElement === lastFocusable) {
                            firstFocusable.focus();
                            e.preventDefault();
                        }
                    }
                }
            });
        });
    }

    // ========================================
    // INITIALIZE ALL ON DOM READY
    // ========================================
    function init() {
        initMobileMenu();
        initNavbarScrollEffect();
        initModalEnhancements();
        initTouchRipple();
        initBottomSheet();
        initFormEnhancements();
        initLazyLoading();
        initPullToRefresh();
        initSmoothScroll();
        initBackToTop();
        initAccessibility();

        console.log('✨ Mobile interactions initialized');
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
