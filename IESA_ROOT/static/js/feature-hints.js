/**
 * FEATURE HINTS & TOOLTIPS
 * Версия: 1.0
 * 
 * Интуитивные подсказки для новых функций:
 * - First-time hints (показываются один раз)
 * - Interactive tooltips
 * - Feature discovery
 */

(function() {
    'use strict';

    const HINTS_SHOWN_KEY = 'iesa_hints_shown';
    let hintsShown = JSON.parse(localStorage.getItem(HINTS_SHOWN_KEY) || '{}');

    // ====================================================
    // 1. FEATURE HINTS
    // ====================================================

    const HINTS = {
        reactions: {
            id: 'reactions',
            target: '.reaction-add-btn',
            message: '👋 Click to react with emoji!',
            position: 'top',
            delay: 2000
        },
        messaging: {
            id: 'messaging',
            target: '.messaging-btn',
            message: '✉️ Send private messages here',
            position: 'bottom',
            delay: 3000
        },
        advancedSearch: {
            id: 'advancedSearch',
            target: '#communitySearchToggle',
            message: '🔍 Try advanced search with filters!',
            position: 'bottom',
            delay: 4000
        },
        comments: {
            id: 'comments',
            target: '.comment-reply-btn',
            message: '💬 Reply to comments directly',
            position: 'top',
            delay: 5000
        }
    };

    function init() {
        // Wait for page to load
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', showHints);
        } else {
            setTimeout(showHints, 1000);
        }

        // Add tooltips to all interactive elements
        initTooltips();

        console.log('✓ Feature Hints initialized');
    }

    function showHints() {
        Object.values(HINTS).forEach(hint => {
            if (!hintsShown[hint.id]) {
                setTimeout(() => showHint(hint), hint.delay);
            }
        });
    }

    function showHint(hint) {
        const target = document.querySelector(hint.target);
        if (!target) return;

        // Create hint element
        const hintEl = document.createElement('div');
        hintEl.className = `feature-hint feature-hint-${hint.position}`;
        hintEl.innerHTML = `
            <div class="feature-hint-content">
                ${hint.message}
                <button class="feature-hint-close" aria-label="Close hint">&times;</button>
            </div>
            <div class="feature-hint-arrow"></div>
        `;

        // Position hint
        document.body.appendChild(hintEl);
        positionHint(hintEl, target, hint.position);

        // Animate in
        setTimeout(() => hintEl.classList.add('show'), 50);

        // Close handlers
        const closeBtn = hintEl.querySelector('.feature-hint-close');
        closeBtn.addEventListener('click', () => {
            closeHint(hintEl, hint.id);
        });

        // Auto-close after 8 seconds
        setTimeout(() => {
            if (hintEl.parentNode) {
                closeHint(hintEl, hint.id);
            }
        }, 8000);

        // Close when clicking target
        target.addEventListener('click', () => {
            closeHint(hintEl, hint.id);
        }, { once: true });
    }

    function positionHint(hintEl, target, position) {
        const rect = target.getBoundingClientRect();
        const hintRect = hintEl.getBoundingClientRect();

        let top, left;

        if (position === 'top') {
            top = rect.top - hintRect.height - 10;
            left = rect.left + (rect.width / 2) - (hintRect.width / 2);
        } else if (position === 'bottom') {
            top = rect.bottom + 10;
            left = rect.left + (rect.width / 2) - (hintRect.width / 2);
        } else if (position === 'left') {
            top = rect.top + (rect.height / 2) - (hintRect.height / 2);
            left = rect.left - hintRect.width - 10;
        } else if (position === 'right') {
            top = rect.top + (rect.height / 2) - (hintRect.height / 2);
            left = rect.right + 10;
        }

        hintEl.style.top = `${top + window.scrollY}px`;
        hintEl.style.left = `${left}px`;
    }

    function closeHint(hintEl, hintId) {
        hintEl.classList.remove('show');
        setTimeout(() => {
            hintEl.remove();
        }, 300);

        // Mark as shown
        hintsShown[hintId] = true;
        localStorage.setItem(HINTS_SHOWN_KEY, JSON.stringify(hintsShown));
    }

    // ====================================================
    // 2. INTERACTIVE TOOLTIPS
    // ====================================================

    function initTooltips() {
        // Enhanced tooltips for reaction buttons
        document.addEventListener('mouseenter', (e) => {
            if (!e.target || !e.target.classList) return; // Guard against non-element targets
            if (e.target.classList.contains('reaction-add-btn')) {
                e.target.setAttribute('data-tooltip', 'Click to add reaction');
            }
            if (e.target.classList.contains('reaction-picker-item')) {
                const reactionName = e.target.dataset.reactionName;
                e.target.setAttribute('data-tooltip', `React with ${reactionName}`);
            }
            if (e.target.classList.contains('messaging-btn')) {
                e.target.setAttribute('data-tooltip', 'Send direct message');
            }
            if (e.target.id === 'communitySearchToggle') {
                e.target.setAttribute('data-tooltip', 'Search posts, users & events');
            }
        }, true);

        // Add visual pulse to important buttons (once)
        if (!hintsShown.pulsed) {
            setTimeout(() => {
                const reactionBtn = document.querySelector('.reaction-add-btn');
                if (reactionBtn) {
                    reactionBtn.classList.add('pulse-hint');
                    setTimeout(() => reactionBtn.classList.remove('pulse-hint'), 3000);
                }
            }, 2000);

            hintsShown.pulsed = true;
            localStorage.setItem(HINTS_SHOWN_KEY, JSON.stringify(hintsShown));
        }
    }

    // ====================================================
    // 3. RESET HINTS (for testing)
    // ====================================================

    window.FeatureHints = {
        init,
        reset: () => {
            localStorage.removeItem(HINTS_SHOWN_KEY);
            hintsShown = {};
            console.log('Feature hints reset');
        }
    };

    // Auto-initialize
    init();

})();
