/**
 * MOBILE OPTIMIZATION - non-destructive version
 * Keeps mobile UX helpers without applying inline style mutations.
 */

(function () {
  'use strict';

  function initMobileMenuToggle() {
    const navbarToggler = document.querySelector('.navbar-toggler');
    const navbarCollapse = document.getElementById('navbarNav');

    if (!navbarToggler || !navbarCollapse || typeof bootstrap === 'undefined') return;

    const bsCollapse = bootstrap.Collapse.getOrCreateInstance(navbarCollapse, { toggle: false });

    const navLinks = navbarCollapse.querySelectorAll('a[href*="#"]');
    navLinks.forEach((link) => {
      link.addEventListener('click', function () {
        const togglerVisible = window.getComputedStyle(navbarToggler).display !== 'none';
        if (togglerVisible && navbarCollapse.classList.contains('show')) {
          bsCollapse.hide();
        }
      });
    });
  }

  function initSearchDropdownAutoClose() {
    const toggle = document.getElementById('communitySearchToggle');
    const dropdown = document.querySelector('.navbar-search-dropdown');

    if (!toggle || !dropdown || typeof bootstrap === 'undefined') return;

    const dropdownInstance = bootstrap.Dropdown.getOrCreateInstance(toggle, { autoClose: true });

    const closeDropdown = () => {
      const isMobile = window.innerWidth < 992;
      if (isMobile && dropdown.classList.contains('show')) {
        dropdownInstance.hide();
      }
    };

    window.addEventListener('scroll', closeDropdown, { passive: true });
    window.addEventListener('orientationchange', closeDropdown);
  }

  function initTouchFlag() {
    const isTouch =
      ('ontouchstart' in window) ||
      (navigator.maxTouchPoints && navigator.maxTouchPoints > 0);

    if (isTouch) {
      document.body.classList.add('touch-enabled');
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    initTouchFlag();
    initMobileMenuToggle();
    initSearchDropdownAutoClose();
  });
})();
