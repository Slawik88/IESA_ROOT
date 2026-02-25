/**
 * Header Hide on Scroll
 * Desktop only: hides header on scroll down, shows on scroll up.
 * Mobile (< 992px): header NEVER hides.
 * When mobile menu is open: body scroll is LOCKED.
 */
(function() {
  'use strict';

  var header = document.querySelector('header');
  if (!header) return;

  var HIDE_THRESHOLD = 100;
  var SCROLL_DELAY = 150;
  var MOBILE_BP = 992;

  var lastY = 0;
  var hidden = false;
  var timer = null;

  function isMobile() { return window.innerWidth < MOBILE_BP; }

  function hide() {
    if (hidden) return;
    hidden = true;
    header.style.transform = 'translateY(-100%)';
    header.style.transition = 'transform .3s cubic-bezier(.4,0,.2,1)';
  }

  function show() {
    if (!hidden) return;
    hidden = false;
    header.style.transform = 'translateY(0)';
    header.style.transition = 'transform .3s cubic-bezier(.4,0,.2,1)';
  }

  function onScroll() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(function() {
      // Mobile: NEVER hide header
      if (isMobile()) { if (hidden) show(); return; }

      var y = window.pageYOffset || document.documentElement.scrollTop;
      if (y < HIDE_THRESHOLD) { show(); }
      else if (y > lastY) { hide(); }
      else if (y < lastY) { show(); }
      lastY = y;
    }, SCROLL_DELAY);
  }

  // Body scroll lock for mobile menu
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
    header.style.transform = 'translateY(0)';
    header.style.willChange = 'transform';
    window.addEventListener('scroll', onScroll, { passive: true });

    var nav = document.getElementById('navbarNav');
    if (nav) {
      nav.addEventListener('show.bs.collapse', lockScroll);
      nav.addEventListener('hidden.bs.collapse', unlockScroll);
    }

    window.addEventListener('resize', function() {
      if (isMobile() && hidden) show();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.HeaderScroll = { hide: hide, show: show };
})();
