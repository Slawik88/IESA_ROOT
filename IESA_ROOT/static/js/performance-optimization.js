/**
 * Lazy loading for <img data-src> / <iframe data-src> (used by the gallery grid).
 *
 * Everything else that used to live here (preload stubs, DOM/API caches, resize re-dispatch to every
 * .card, deviceMemory classes) had no consumers; it only polluted the global scope with
 * `const debounce/throttle/...` bindings and ran work on every page. Wrapped in an IIFE now.
 */
(function () {
    'use strict';

    if (!('IntersectionObserver' in window)) {
        // Old browsers: just load everything
        document.querySelectorAll('img[data-src], iframe[data-src]').forEach(function (el) {
            el.src = el.dataset.src;
        });
        return;
    }

    var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            var el = entry.target;
            if (el.dataset.src) {
                el.src = el.dataset.src;
                el.removeAttribute('data-src');
            }
            if (el.dataset.srcset) {
                el.srcset = el.dataset.srcset;
                el.removeAttribute('data-srcset');
            }
            el.classList.add('lazy-loaded');
            observer.unobserve(el);
        });
    }, { threshold: 0.1, rootMargin: '200px' });

    function observeAll(root) {
        (root || document).querySelectorAll('img[data-src], iframe[data-src]').forEach(function (el) {
            observer.observe(el);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { observeAll(); });
    } else {
        observeAll();
    }

    // Content swapped in by HTMX may contain new lazy elements
    document.addEventListener('htmx:afterSwap', function (e) { observeAll(e.target); });
})();
