/**
 * IESA Community UI — interactive effects for Posts & Events pages
 * Features: live countdown timers · capacity bars · scroll-reveal · reading time
 */
(function () {
  'use strict';

  /* ─── 1. Live Countdown Timers ─────────────────────────────────────────── */
  function initCountdowns() {
    document.querySelectorAll('[data-countdown]').forEach(function (el) {
      var targetMs = Number(el.dataset.countdown) * 1000;
      var wrap = el.closest('.tl-countdown');
      var timerId = null;

      function tick() {
        // Прекращаем, если элемент уже вне DOM (HTMX swap)
        if (!document.contains(el)) { clearTimeout(timerId); return; }

        var diff = targetMs - Date.now();
        if (diff <= 0) {
          if (wrap) wrap.innerHTML = '<i class="fas fa-play me-1"></i><span>In progress</span>';
          else el.textContent = '—';
          return;
        }
        var d = Math.floor(diff / 86400000);
        var h = Math.floor((diff % 86400000) / 3600000);
        var m = Math.floor((diff % 3600000) / 60000);
        var s = Math.floor((diff % 60000) / 1000);
        el.textContent = d > 0
          ? (d + 'd ' + h + 'h ' + pad(m) + 'm')
          : (pad(h) + ':' + pad(m) + ':' + pad(s));
        timerId = setTimeout(tick, 1000);
      }
      tick();
    });
  }

  function pad(n) { return String(n).padStart(2, '0'); }

  /* ─── 2. Capacity Progress Bars ─────────────────────────────────────────── */
  function initCapacityBars() {
    document.querySelectorAll('.tl-capacity-fill[data-filled]').forEach(function (bar) {
      var filled = parseInt(bar.dataset.filled, 10) || 0;
      var max    = parseInt(bar.dataset.max,    10) || 0;
      if (!max) return;
      var pct = Math.min(100, Math.round(filled / max * 100));
      if (pct >= 100) bar.classList.add('tl-capacity-fill--full');
      else if (pct >= 75) bar.classList.add('tl-capacity-fill--warn');
      // Animate after a small delay so the transition is visible
      setTimeout(function () { bar.style.width = pct + '%'; }, 350);
    });
  }

  /* ─── 3. Timeline Stagger Reveal ─────────────────────────────────────────── */
  function initTimelineReveal() {
    if (!window.IntersectionObserver) {
      document.querySelectorAll('.tl-item').forEach(function (el) {
        el.classList.add('tl-visible');
      });
      return;
    }
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('tl-visible');
          obs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

    document.querySelectorAll('.tl-item').forEach(function (el, i) {
      el.style.transitionDelay = (i * 75) + 'ms';
      obs.observe(el);
    });
  }

  /* ─── 4. Magazine Article Reveal ────────────────────────────────────────── */
  function initArticleReveal() {
    if (!window.IntersectionObserver) {
      document.querySelectorAll('.iesa-article').forEach(function (el) {
        el.classList.add('article-visible');
      });
      return;
    }
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('article-visible');
          obs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.07, rootMargin: '0px 0px -30px 0px' });

    document.querySelectorAll('.iesa-article').forEach(function (el, i) {
      if (!el.classList.contains('article-visible')) {
        el.style.transitionDelay = (i * 55) + 'ms';
        obs.observe(el);
      }
    });
  }

  /* ─── 5. Reading Time from Excerpt Text ─────────────────────────────────── */
  function initReadingTime() {
    document.querySelectorAll('.art-excerpt').forEach(function (excerpt) {
      var card  = excerpt.closest('.iesa-article');
      if (!card) return;
      var badge = card.querySelector('.art-read-time-val');
      if (!badge) return;
      var text  = excerpt.textContent.trim();
      var words = text.split(/\s+/).filter(Boolean).length;
      // Multiply 3x: excerpt is ~1/3 of full article
      var mins  = Math.max(1, Math.round((words * 3) / 200));
      badge.textContent = mins + ' min';
    });
  }

  /* ─── 6. Article Progress Bar (decorative popularity indicator) ──────────── */
  function initProgressBars() {
    if (!window.IntersectionObserver) return;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var bar = entry.target.querySelector('.art-progress-bar');
          if (bar) {
            var views = parseInt(bar.dataset.views, 10) || 0;
            // Scale: 500 views = 100%, minimum 15%
            var pct = Math.min(97, Math.max(15, Math.round(views / 500 * 100)));
            setTimeout(function () { bar.style.width = pct + '%'; }, 300);
          }
          obs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.2 });

    document.querySelectorAll('.iesa-article').forEach(function (el) {
      obs.observe(el);
    });
  }

  /* ─── 7. Index Number Badges ─────────────────────────────────────────────── */
  function initIndexBadges() {
    document.querySelectorAll('.art-index').forEach(function (el, i) {
      el.textContent = String(i + 1).padStart(2, '0');
    });
  }

  /* ─── Runner ─────────────────────────────────────────────────────────────── */
  function run() {
    initCountdowns();
    initCapacityBars();
    initTimelineReveal();
    initArticleReveal();
    initReadingTime();
    initProgressBars();
    initIndexBadges();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }

  // Re-run after HTMX swaps new content in
  document.addEventListener('htmx:afterSettle', run);

})();
