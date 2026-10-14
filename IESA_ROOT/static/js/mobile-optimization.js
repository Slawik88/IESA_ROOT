/**
 * IESA MOBILE OPTIMIZATION v3.0
 * 
 * Modules:
 *  1. Touch flag (body class)
 *  2. Viewport height fix (iOS dynamic toolbar)
 *  3. Navbar collapse — auto-close on anchor link click
 *  5. Bottom nav — active state + shadow on scroll
 *  7. Prevent double-tap zoom on buttons/links (iOS)
 */

(function () {
  'use strict';

  /* ─────────────────────────────────────────
     1. TOUCH FLAG
     ───────────────────────────────────────── */
  function initTouchFlag() {
    const isTouch =
      ('ontouchstart' in window) ||
      (navigator.maxTouchPoints && navigator.maxTouchPoints > 0);
    if (isTouch) {
      document.body.classList.add('touch-enabled');
    }
  }

  /* ─────────────────────────────────────────
     2. VIEWPORT HEIGHT FIX
     Решает проблему 100vh в iOS Safari когда
     адресная строка скрывается / появляется.
     ───────────────────────────────────────── */
  function initViewportHeightFix() {
    function setVH() {
      const vh = window.innerHeight * 0.01;
      document.documentElement.style.setProperty('--vh', vh + 'px');
    }
    setVH();
    window.addEventListener('resize', setVH, { passive: true });
    window.addEventListener('orientationchange', function () {
      setTimeout(setVH, 120);
    });
  }

  /* ─────────────────────────────────────────
     3. NAVBAR COLLAPSE — auto-close on anchor
     ───────────────────────────────────────── */
  function initMobileMenuToggle() {
    const navbarToggler = document.querySelector('.iesa-toggler');
    const navbarCollapse = document.getElementById('iesa-nav-collapse');

    if (!navbarToggler || !navbarCollapse || typeof bootstrap === 'undefined') return;

    const bsCollapse = bootstrap.Collapse.getOrCreateInstance(navbarCollapse, { toggle: false });

    // Закрываем при клике на якорные ссылки
    const navLinks = navbarCollapse.querySelectorAll('a[href]:not([data-bs-toggle])');
    navLinks.forEach(function (link) {
      link.addEventListener('click', function () {
        const togglerVisible = window.getComputedStyle(navbarToggler).display !== 'none';
        if (togglerVisible && navbarCollapse.classList.contains('show')) {
          bsCollapse.hide();
        }
      });
    });

    // Закрываем при клике вне навбара
    document.addEventListener('click', function (e) {
      if (window.innerWidth >= 992) return;
      if (!navbarCollapse.contains(e.target) && !navbarToggler.contains(e.target)) {
        if (navbarCollapse.classList.contains('show')) {
          bsCollapse.hide();
        }
      }
    }, { passive: true });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape' || window.innerWidth >= 992 ||
          !navbarCollapse.classList.contains('show')) return;
      e.preventDefault();
      bsCollapse.hide();
      navbarToggler.focus();
    });
  }

  /* ─────────────────────────────────────────
     5. BOTTOM NAV — active state + shadow
     ───────────────────────────────────────── */
  function initBottomNav() {
    const bottomNav = document.getElementById('mobileBottomNav');
    if (!bottomNav) return;

    // B4-07: единый RAF-throttled scroll listener вместо двух отдельных
    var _scrollTicking = false;
    window.addEventListener('scroll', function () {
      if (!_scrollTicking) {
        _scrollTicking = true;
        requestAnimationFrame(function () {
          bottomNav.style.boxShadow = window.scrollY > 10
            ? '0 -6px 24px rgba(0,0,0,0.12)'
            : '0 -4px 20px rgba(0,0,0,0.08)';
          _scrollTicking = false;
        });
      }
    }, { passive: true });

    // Подсвечиваем активный элемент при клике (визуальный фидбек)
    const items = bottomNav.querySelectorAll('.mbn-item');
    items.forEach(function (item) {
      item.addEventListener('click', function () {
        items.forEach(function (el) { el.classList.remove('active'); });
        item.classList.add('active');
      });
    });
  }

  /* ─────────────────────────────────────────
     7. PREVENT DOUBLE-TAP ZOOM (iOS)
     Устанавливаем touch-action: manipulation
     на все интерактивные элементы
     ───────────────────────────────────────── */
  function initTouchManipulation() {
    const style = document.createElement('style');
    style.textContent = [
      'a, button, [role="button"], .btn, .nav-link, .dropdown-item,',
      '.mbn-item, label, .card[onclick], [data-bs-toggle] {',
      '  touch-action: manipulation;',
      '  -webkit-tap-highlight-color: transparent;',
      '}'
    ].join('\n');
    document.head.appendChild(style);
  }

  // Leave scroll anchoring to the browser. A global afterSettle restoration
  // overwrites scrolling performed by the user while an HTMX swap settles.

  /* ─────────────────────────────────────────
     9. LAZY LOADING IMAGES
     Добавляем loading="lazy" к изображениям
     у которых нет атрибута
     ───────────────────────────────────────── */
  function initLazyImages(root = document) {
    const selector = 'img:not([loading]):not([src^="data:"])';
    const imgs = Array.from(root.querySelectorAll(selector));
    if (root.matches?.(selector)) imgs.unshift(root);
    imgs.forEach(function (img) {
      // Keep visible images eager; delaying them can worsen LCP.
      const rect = img.getBoundingClientRect();
      img.loading = rect.top < window.innerHeight && rect.bottom > 0 ? 'eager' : 'lazy';
      img.decoding = 'async';
    });
  }

  /* ─────────────────────────────────────────
     INIT
     ───────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    initTouchFlag();
    initViewportHeightFix();
    initMobileMenuToggle();
    initBottomNav();
    initTouchManipulation();
    initLazyImages();
  });

  // Повторяем lazy init после HTMX swap
  document.addEventListener('htmx:afterSwap', function (event) {
    initLazyImages(event.detail.elt || document);
  });

})();
