/**
 * Header Hide on Scroll
 * Desktop only: hides header on scroll down, shows on scroll up.
 * Mobile (< 992px): header NEVER hides.
 *
 * ВАЖНО: не используем inline transform на шапке пока она видима —
 * transform создаёт containing block для position:absolute потомков
 * (Bootstrap dropdowns), что ломает Popper.js позиционирование.
 * Вместо этого используем CSS-класс .hhs-hidden только когда шапка скрыта.
 */
(function () {
    'use strict';

    var header = document.querySelector('header');
    if (!header) return;

    var HIDE_THRESHOLD = 80;
    var MOBILE_BP     = 992;
    var lastY         = 0;
    var hidden        = false;
    var ticking       = false;

    function isMobile() { return window.innerWidth < MOBILE_BP; }

    function hide() {
        if (hidden) return;
        hidden = true;
        header.classList.add('hhs-hidden');
    }

    function show() {
        if (!hidden) return;
        hidden = false;
        header.classList.remove('hhs-hidden');
    }

    function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(function () {
            ticking = false;
            if (isMobile()) { show(); return; }

            var y = window.pageYOffset || document.documentElement.scrollTop;
            if (y < HIDE_THRESHOLD) {
                show();
            } else if (y > lastY + 4) {
                hide();
            } else if (y < lastY - 4) {
                show();
            }
            lastY = y;
        });
    }

    /* Body scroll lock for mobile menu */
    function lockScroll() {
        document.body.style.overflow = 'hidden';
        document.body.style.touchAction = 'none';
        document.body.classList.add('mobile-menu-open');
    }
    function unlockScroll() {
        document.body.style.overflow = '';
        document.body.style.touchAction = '';
        document.body.classList.remove('mobile-menu-open');
    }

    function init() {
        /* НЕ применяем transform/willChange здесь —
           это сломает Bootstrap dropdown позиционирование */
        window.addEventListener('scroll', onScroll, { passive: true });
        window.addEventListener('resize', function () {
            if (isMobile() && hidden) show();
        });

        /* Collapse events для мобильного меню Bootstrap */
        var nav = document.getElementById('iesa-nav-collapse');
        if (nav) {
            nav.addEventListener('show.bs.collapse',   lockScroll);
            nav.addEventListener('hidden.bs.collapse', unlockScroll);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.HeaderScroll = { hide: hide, show: show };
})();
