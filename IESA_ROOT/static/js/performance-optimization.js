/** Load lazy media, including HTMX content. */
(function () {
'use strict';
const observedMedia = new WeakSet();
let mediaObserver;

function loadMedia(element) {
    // Set responsive candidates first to avoid downloading the fallback twice.
    if (element.dataset.srcset) {
        element.srcset = element.dataset.srcset;
        element.removeAttribute('data-srcset');
    }
    if (element.dataset.src) {
        element.src = element.dataset.src;
        element.removeAttribute('data-src');
    }
    element.classList.add('lazy-loaded');
}

function initLazyLoading(root = document) {
    const selector = 'img[data-src], img[data-srcset], iframe[data-src]';
    const elements = Array.from(root.querySelectorAll(selector));
    if (root.matches?.(selector)) elements.unshift(root);
    const pending = elements.filter(element => !observedMedia.has(element));
    if (!pending.length) return;
    if (!window.IntersectionObserver) {
        pending.forEach(loadMedia);
        return;
    }
    if (!mediaObserver) {
        mediaObserver = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    loadMedia(entry.target);
                    mediaObserver.unobserve(entry.target);
                }
            });
        }, { rootMargin: '50px', threshold: 0.1 });
    }
    pending.forEach(element => {
        observedMedia.add(element);
        mediaObserver.observe(element);
    });
}

// Release removed nodes, including swaps performed outside the main page.
document.addEventListener('htmx:beforeCleanupElement', event => {
    const root = event.detail.elt;
    if (!mediaObserver || !root || typeof root.querySelectorAll !== 'function') return;
    [root, ...root.querySelectorAll('img, iframe')].forEach(element => {
        mediaObserver.unobserve(element);
        observedMedia.delete(element);
    });
});
document.addEventListener('htmx:afterSwap', event => {
    initLazyLoading(event.detail.elt || document);
});


if (document.readyState === 'loading') {
 document.addEventListener('DOMContentLoaded', () => initLazyLoading());
} else { initLazyLoading(); }
})();
