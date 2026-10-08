/**
 * Swipe rows ([data-snap]): adds a row of dots under each row and keeps the active dot in sync.
 * The rows themselves are plain CSS scroll-snap (see home-mobile.css); this only paints the indicator.
 * Dots are decorative (aria-hidden) — the row is scrollable and its links stay keyboard reachable.
 */
(function () {
    'use strict';

    function build(row) {
        var items = row.children;
        if (items.length < 2 || row.dataset.snapReady) return;
        row.dataset.snapReady = '1';

        var dots = document.createElement('div');
        dots.className = 'm-dots';
        dots.setAttribute('aria-hidden', 'true');
        for (var i = 0; i < items.length; i++) dots.appendChild(document.createElement('i'));
        row.insertAdjacentElement('afterend', dots);

        var marks = dots.children, ticking = false, current = -1;

        function paint() {
            ticking = false;
            var left = row.scrollLeft, best = 0, bestDist = Infinity;
            for (var i = 0; i < items.length; i++) {
                var d = Math.abs(items[i].offsetLeft - items[0].offsetLeft - left);
                if (d < bestDist) { bestDist = d; best = i; }
            }
            // at the very end the last card may never reach the start edge
            if (row.scrollLeft + row.clientWidth >= row.scrollWidth - 4) best = items.length - 1;
            if (best === current) return;
            if (current > -1) marks[current].classList.remove('on');
            marks[best].classList.add('on');
            current = best;
        }

        row.addEventListener('scroll', function () {
            if (ticking) return;
            ticking = true;
            requestAnimationFrame(paint);
        }, { passive: true });
        paint();
    }

    function init() { document.querySelectorAll('[data-snap]').forEach(build); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
