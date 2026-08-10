/**
 * IESA MOBILE OPTIMIZATION v3.0
 * 
 * Modules:
 *  1. Touch flag (body class)
 *  2. Viewport height fix (iOS dynamic toolbar)
 *  3. Navbar collapse — auto-close on anchor link click
 *  4. Search dropdown auto-close on scroll
 *  5. Bottom nav — active state + shadow on scroll
 *  6. Swipe-to-close navbar collapse
 *  7. Prevent double-tap zoom on buttons/links (iOS)
 *  8. Scroll restoration for HTMX navigations
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
    const navbarToggler = document.querySelector('.navbar-toggler');
    const navbarCollapse = document.getElementById('navbarNav');

    if (!navbarToggler || !navbarCollapse || typeof bootstrap === 'undefined') return;

    const bsCollapse = bootstrap.Collapse.getOrCreateInstance(navbarCollapse, { toggle: false });

    // Закрываем при клике на якорные ссылки
    const navLinks = navbarCollapse.querySelectorAll('a[href*="#"]');
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
      if (!navbarCollapse.contains(e.target) && !navbarToggler.contains(e.target)) {
        if (navbarCollapse.classList.contains('show')) {
          bsCollapse.hide();
        }
      }
    }, { passive: true });
  }

  /* ─────────────────────────────────────────
     4. SEARCH DROPDOWN AUTO-CLOSE ON SCROLL
     ───────────────────────────────────────── */
  function initSearchDropdownAutoClose() {
    const toggle = document.getElementById('communitySearchToggle');
    const dropdown = document.querySelector('.navbar-search-dropdown');

    if (!toggle || !dropdown || typeof bootstrap === 'undefined') return;

    const dropdownInstance = bootstrap.Dropdown.getOrCreateInstance(toggle, { autoClose: true });
    const closeDropdown = function () {
      const isMobile = window.innerWidth < 992;
      if (isMobile && dropdown.classList.contains('show')) {
        dropdownInstance.hide();
      }
    };

    window.addEventListener('scroll', closeDropdown, { passive: true });
    window.addEventListener('orientationchange', closeDropdown);
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
     6. SWIPE-TO-CLOSE NAVBAR COLLAPSE
     Смахивание влево/вправо закрывает меню
     ───────────────────────────────────────── */
  function initSwipeToClose() {
    const navbarCollapse = document.getElementById('navbarNav');
    if (!navbarCollapse || typeof bootstrap === 'undefined') return;

    let touchStartX = 0;
    let touchStartY = 0;
    const THRESHOLD = 60; // px

    navbarCollapse.addEventListener('touchstart', function (e) {
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
    }, { passive: true });

    navbarCollapse.addEventListener('touchend', function (e) {
      const dx = e.changedTouches[0].clientX - touchStartX;
      const dy = e.changedTouches[0].clientY - touchStartY;

      // Swipe up = close (вертикальный свайп вверx)
      if (Math.abs(dy) > Math.abs(dx) && dy < -THRESHOLD) {
        const bsCollapse = bootstrap.Collapse.getInstance(navbarCollapse);
        if (bsCollapse && navbarCollapse.classList.contains('show')) {
          bsCollapse.hide();
        }
      }
    }, { passive: true });
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

  /* ─────────────────────────────────────────
     8. HTMX SCROLL RESTORATION
     Сохраняем позицию скролла при HTMX свопах
     ───────────────────────────────────────── */
  function initHtmxScrollRestore() {
    if (typeof htmx === 'undefined') return;

    let savedScrollY = 0;

    document.addEventListener('htmx:beforeSwap', function () {
      savedScrollY = window.scrollY;
    });

    document.addEventListener('htmx:afterSettle', function () {
      /* HTMX may replace content above the viewport. Keep the user's exact
         position; never animate or pull them to a background-updated target. */
      if (Math.abs(window.scrollY - savedScrollY) > 1) {
        window.scrollTo({ top: savedScrollY, behavior: 'auto' });
      }
    });
  }

  /* ─────────────────────────────────────────
     9. LAZY LOADING IMAGES
     Добавляем loading="lazy" к изображениям
     у которых нет атрибута
     ───────────────────────────────────────── */
  function initLazyImages() {
    const imgs = document.querySelectorAll('img:not([loading]):not([src^="data:"])');
    imgs.forEach(function (img) {
      img.loading = 'lazy';
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
    initSearchDropdownAutoClose();
    initBottomNav();
    initSwipeToClose();
    initTouchManipulation();
    initHtmxScrollRestore();
    initLazyImages();
  });

  // Повторяем lazy init после HTMX swap
  document.addEventListener('htmx:afterSwap', function () {
    initLazyImages();
  });

})();
