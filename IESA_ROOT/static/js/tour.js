/**
 * IESA Interactive Tour — onboarding tooltips with spotlight.
 * Created: 2026-05-27.
 *
 * Usage in template:
 *   {{ tour_data|json_script:"tour-data" }}
 *   <script src="{% static 'js/tour.js' %}" defer></script>
 *
 * tour_data structure:
 *   {
 *     "name": "user" | "partner" | "president",
 *     "complete_url": "/auth/tour/user/complete/",
 *     "csrf_token": "...",
 *     "labels": {"next": "Got it", "skip": "Skip", "finish": "Done", "of": "of"},
 *     "steps": [
 *       {"selector": "#some-element", "title": "...", "text": "...", "pos": "bottom"},
 *       ...
 *     ]
 *   }
 */
(function () {
    'use strict';

    var dataEl = document.getElementById('tour-data');
    if (!dataEl) return;

    var data;
    try {
        data = JSON.parse(dataEl.textContent);
    } catch (e) {
        return;
    }
    if (!data || !data.steps || !data.steps.length) return;

    var current = 0;
    var overlay, spotlight, tip;

    function createElements() {
        overlay = document.createElement('div');
        overlay.className = 'iesa-tour-overlay';
        overlay.addEventListener('click', function (e) {
            // Click on overlay = skip (close)
            if (e.target === overlay) finishTour(true);
        });

        spotlight = document.createElement('div');
        spotlight.className = 'iesa-tour-spotlight';

        tip = document.createElement('div');
        tip.className = 'iesa-tour-tip';
        tip.setAttribute('role', 'dialog');
        tip.setAttribute('aria-live', 'polite');

        document.body.appendChild(overlay);
        document.body.appendChild(spotlight);
        document.body.appendChild(tip);

        // Esc to close
        document.addEventListener('keydown', onKey);
    }

    function onKey(e) {
        if (e.key === 'Escape') finishTour(true);
        if (e.key === 'Enter' || e.key === ' ') {
            if (document.activeElement && document.activeElement.closest('.iesa-tour-tip')) {
                e.preventDefault();
                nextStep();
            }
        }
    }

    function destroyElements() {
        document.removeEventListener('keydown', onKey);
        [overlay, spotlight, tip].forEach(function (el) {
            if (el && el.parentNode) el.parentNode.removeChild(el);
        });
    }

    function renderStep(idx) {
        var step = data.steps[idx];
        if (!step) return finishTour(true);

        // ── CENTERED step (нет selector или selector='center') ───────
        // Используется для welcome/finish шагов — tooltip по центру экрана,
        // подсветки нет, оверлей затемнён.
        if (!step.selector || step.selector === 'center') {
            spotlight.classList.remove('visible');
            spotlight.style.width = '0';
            spotlight.style.height = '0';
            overlay.classList.add('visible');
            renderTipContent(idx, step);
            positionTipCentered();
            return;
        }

        var el = document.querySelector(step.selector);
        if (!el) {
            // Селектор не найден — пропускаем шаг
            return nextStep();
        }

        // Прокрутить элемент в viewport, если он не виден
        var rect = el.getBoundingClientRect();
        var vh = window.innerHeight;
        if (rect.top < 80 || rect.bottom > vh - 80) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            // Подождать прокрутку и пере-вычислить позицию
            setTimeout(function () {
                renderTipContent(idx, step);
                positionUI(el, step);
            }, 400);
            return;
        }
        renderTipContent(idx, step);
        positionUI(el, step);
    }

    function renderTipContent(idx, step) {

        // Build tooltip content
        var stepLabel = (idx + 1) + ' ' + (data.labels.of || 'of') + ' ' + data.steps.length;
        var isLast = idx === data.steps.length - 1;

        // Dots progress
        var dotsHtml = '';
        for (var i = 0; i < data.steps.length; i++) {
            var cls = i === idx ? 'active' : (i < idx ? 'done' : '');
            dotsHtml += '<span class="iesa-tour-dot ' + cls + '"></span>';
        }

        tip.innerHTML =
            '<div class="iesa-tour-head">' +
                '<span class="iesa-tour-counter">' + escapeHtml(stepLabel) + '</span>' +
                '<button type="button" class="iesa-tour-close" aria-label="' +
                    escapeHtml(data.labels.skip || 'Skip') + '">' +
                    '<i class="fas fa-times" aria-hidden="true"></i>' +
                '</button>' +
            '</div>' +
            '<h3 class="iesa-tour-title">' + escapeHtml(step.title || '') + '</h3>' +
            '<p class="iesa-tour-text">' + escapeHtml(step.text || '') + '</p>' +
            '<div class="iesa-tour-foot">' +
                '<div class="iesa-tour-progress">' + dotsHtml + '</div>' +
                '<div class="iesa-tour-actions">' +
                    '<button type="button" class="iesa-tour-btn">' +
                        escapeHtml(isLast ? (data.labels.finish || 'Done') :
                                            (data.labels.next || 'Got it')) +
                    '</button>' +
                '</div>' +
            '</div>';

        // Wire events
        tip.querySelector('.iesa-tour-close').addEventListener('click', function () {
            finishTour(true);
        });
        tip.querySelector('.iesa-tour-btn').addEventListener('click', nextStep);
    }

    function positionTipCentered() {
        // Tooltip по центру экрана — используется для welcome/finish шагов.
        // Mobile: CSS-правила (.iesa-tour-tip) переопределяют left/right.
        var tipW = Math.min(380, window.innerWidth - 32);
        var tipH = tip.offsetHeight || 220;
        var top  = Math.max(16, (window.innerHeight - tipH) / 2);
        var left = Math.max(16, (window.innerWidth - tipW) / 2);
        tip.style.top  = top + 'px';
        tip.style.left = left + 'px';
        tip.setAttribute('data-pos', 'center');
        tip.classList.add('visible');
    }

    function positionUI(el, step) {
        var rect = el.getBoundingClientRect();
        var pad = 8;

        // Spotlight
        spotlight.style.top    = (rect.top - pad) + 'px';
        spotlight.style.left   = (rect.left - pad) + 'px';
        spotlight.style.width  = (rect.width + pad * 2) + 'px';
        spotlight.style.height = (rect.height + pad * 2) + 'px';
        spotlight.classList.add('visible');
        overlay.classList.add('visible');

        // Tooltip position: вычисляется после рендера контента
        // (см. renderStep), тут только базовые координаты
        var tipW = Math.min(360, window.innerWidth - 32);
        var tipH = 200; // приблизительная высота
        var pos = step.pos || 'bottom';

        var top, left;
        switch (pos) {
            case 'top':
                top = rect.top - tipH - 16;
                left = rect.left;
                break;
            case 'left':
                top = rect.top;
                left = rect.left - tipW - 16;
                break;
            case 'right':
                top = rect.top;
                left = rect.right + 16;
                break;
            default: // bottom
                top = rect.bottom + 16;
                left = rect.left;
        }
        // Boundary check (mobile uses CSS to override)
        var maxLeft = window.innerWidth - tipW - 16;
        var maxTop = window.innerHeight - tipH - 16;
        if (left > maxLeft) left = maxLeft;
        if (left < 16)      left = 16;
        if (top > maxTop)   top = maxTop;
        if (top < 16)       top = 16;

        tip.style.top  = top + 'px';
        tip.style.left = left + 'px';
        tip.setAttribute('data-pos', pos);
        tip.classList.add('visible');
    }

    function nextStep() {
        if (current >= data.steps.length - 1) {
            finishTour(false);
            return;
        }
        current++;
        renderStep(current);
    }

    function finishTour(skipped) {
        if (overlay) overlay.classList.remove('visible');
        if (spotlight) spotlight.classList.remove('visible');
        if (tip) tip.classList.remove('visible');
        setTimeout(destroyElements, 300);

        // Mark tour as done on server (only if logged in & URL provided)
        if (data.complete_url && data.csrf_token) {
            try {
                fetch(data.complete_url, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': data.csrf_token, 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: '{}',
                }).catch(function () { /* silent */ });
            } catch (e) { /* silent */ }
        }
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // Boot
    function start() {
        createElements();
        renderStep(0);
        // Re-position on resize/scroll
        var rePosition = function () {
            var step = data.steps[current];
            if (!step) return;
            // Centered step (welcome/finish) — без selector или с 'center'
            if (!step.selector || step.selector === 'center') {
                positionTipCentered();
                return;
            }
            var el = document.querySelector(step.selector);
            if (el) positionUI(el, step);
        };
        window.addEventListener('resize', rePosition);
        window.addEventListener('scroll', rePosition, { passive: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        // FIX 2026-05-28: запускаемся сразу, без задержки. Welcome-модалка
        // больше не показывается, ждать её появления/закрытия не нужно.
        start();
    }
})();
