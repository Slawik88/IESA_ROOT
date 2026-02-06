/**
 * Header Hide on Scroll
 * Скрывает header при прокрутке вниз, показывает при прокрутке вверх
 * Version 1.0
 */

(function() {
  'use strict';

  // Configuration
  const CONFIG = {
    header: document.querySelector('header'),
    devBanner: document.querySelector('[style*="background: linear-gradient"]'),
    hideThreshold: 100, // px - минимальная прокрутка для скрытия
    scrollTimeout: 150, // ms - задержка для оптимизации
  };

  if (!CONFIG.header) return; // Exit if no header

  let lastScrollTop = 0;
  let isHidden = false;
  let scrollTimeout = null;
  let totalScrollDistance = 0;

  /**
   * Скрыть header
   */
  function hideHeader() {
    if (isHidden) return;
    isHidden = true;
    
    CONFIG.header.style.transform = 'translateY(-100%)';
    CONFIG.header.style.transition = 'transform var(--header-hide-duration, 0.3s) var(--header-hide-easing, cubic-bezier(0.4, 0, 0.2, 1))';
    
    if (CONFIG.devBanner) {
      CONFIG.devBanner.style.transform = 'translateY(-100%)';
      CONFIG.devBanner.style.transition = 'transform var(--header-hide-duration, 0.3s) var(--header-hide-easing, cubic-bezier(0.4, 0, 0.2, 1))';
    }
  }

  /**
   * Показать header
   */
  function showHeader() {
    if (!isHidden) return;
    isHidden = false;
    
    CONFIG.header.style.transform = 'translateY(0)';
    CONFIG.header.style.transition = 'transform var(--header-hide-duration, 0.3s) var(--header-hide-easing, cubic-bezier(0.4, 0, 0.2, 1))';
    
    if (CONFIG.devBanner) {
      CONFIG.devBanner.style.transform = 'translateY(0)';
      CONFIG.devBanner.style.transition = 'transform var(--header-hide-duration, 0.3s) var(--header-hide-easing, cubic-bezier(0.4, 0, 0.2, 1))';
    }
  }

  /**
   * Обработчик скролла с оптимизацией
   */
  function onScroll() {
    // Очистить предыдущий timeout
    if (scrollTimeout) clearTimeout(scrollTimeout);

    scrollTimeout = setTimeout(function() {
      const currentScroll = window.pageYOffset || document.documentElement.scrollTop;
      const scrollDelta = currentScroll - lastScrollTop;

      const navbarCollapse = document.getElementById('navbarNav');
      const isMobile = window.innerWidth < 992;
      const isMenuOpen = navbarCollapse && navbarCollapse.classList.contains('show');

      if (isMobile || isMenuOpen) {
        showHeader();
        lastScrollTop = currentScroll;
        return;
      }

      // Не скрывать header если мы в верхней части страницы
      if (currentScroll < CONFIG.hideThreshold) {
        showHeader();
        lastScrollTop = currentScroll;
        return;
      }

      // Прокрутка вниз - скрыть header
      if (scrollDelta > 0) {
        hideHeader();
      }
      // Прокрутка вверх - показать header
      else if (scrollDelta < 0) {
        showHeader();
      }

      lastScrollTop = currentScroll;
    }, CONFIG.scrollTimeout);
  }

  /**
   * Инициализация
   */
  function init() {
    // Применяем начальное состояние
    CONFIG.header.style.transform = 'translateY(0)';
    CONFIG.header.style.willChange = 'transform';
    
    if (CONFIG.devBanner) {
      CONFIG.devBanner.style.transform = 'translateY(0)';
      CONFIG.devBanner.style.willChange = 'transform';
    }

    // Добавляем обработчик скролла
    window.addEventListener('scroll', onScroll, { passive: true });

    // Добавляем поддержку ResizeObserver для адаптивного дизайна
    if ('ResizeObserver' in window) {
      const resizeObserver = new ResizeObserver(() => {
        // Нужно пересчитать при изменении размера окна
        lastScrollTop = 0;
      });
      
      resizeObserver.observe(CONFIG.header);
    }
  }

  /**
   * Cleanup при unload
   */
  function cleanup() {
    if (scrollTimeout) clearTimeout(scrollTimeout);
    window.removeEventListener('scroll', onScroll);
  }

  // Инициализировать при готовности DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Cleanup при unload
  window.addEventListener('beforeunload', cleanup);

  // Экспортировать функции для отладки/контроля
  window.HeaderScroll = {
    hide: hideHeader,
    show: showHeader,
    reset: function() {
      isHidden = false;
      lastScrollTop = 0;
      showHeader();
    }
  };
})();
