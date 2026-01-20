/**
 * HTMX Animation Disabler
 * Prevents page load animations from firing during HTMX partial requests
 * Only regular page navigation should trigger animations
 */

(function() {
    'use strict';
    
    if (typeof htmx === 'undefined') {
        console.warn('⚠️ HTMX not loaded, animation disabler skipped');
        return;
    }
    
    // Add class to html element when HTMX request starts
    document.addEventListener('htmx:beforeSend', function(evt) {
        // Mark as HTMX request to disable View Transitions
        document.documentElement.classList.add('htmx-request');
    });
    
    // Remove class when HTMX request completes
    document.addEventListener('htmx:afterSwap', function(evt) {
        // Remove marker so next regular navigation still triggers animations
        document.documentElement.classList.remove('htmx-request');
    });
    
    document.addEventListener('htmx:afterSettle', function(evt) {
        // Extra safety: ensure class is removed
        document.documentElement.classList.remove('htmx-request');
    });
    
    // Also handle errors
    document.addEventListener('htmx:responseError', function(evt) {
        document.documentElement.classList.remove('htmx-request');
    });
    
    console.log('✅ HTMX Animation Disabler: Loaded');
})();
