/**
 * IESA Community UI — interactive effects for Posts & Events pages
 * Features: live countdown timers · capacity bars · scroll-reveal · reading time
 */
(function () {
  'use strict';

  const countdownTimers = new WeakMap();
  const initializedCapacity = new WeakSet();
  const reveals = new Map();
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function revealNew(selector, onVisible, options, delay) {
    let state = reveals.get(selector);
    if (!state) {
      state = { seen: new WeakSet(), observer: null };
      reveals.set(selector, state);
    }
    const pending = Array.from(document.querySelectorAll(selector))
      .filter(element => !state.seen.has(element));
    if (!pending.length) return;
    const show = element => onVisible(element);
    if (!window.IntersectionObserver || reducedMotion) {
      pending.forEach(element => { state.seen.add(element); show(element); });
      return;
    }
    if (!state.observer) {
      state.observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            show(entry.target);
            state.observer.unobserve(entry.target);
          }
        });
      }, options);
    }
    pending.forEach((element, index) => {
      state.seen.add(element);
      if (delay) element.style.transitionDelay = Math.min(index, 6) * delay + 'ms';
      state.observer.observe(element);
    });
  }

  document.addEventListener('htmx:beforeCleanupElement', event => {
    const root = event.detail.elt;
    if (!root || typeof root.querySelectorAll !== 'function') return;
    [root, ...root.querySelectorAll('*')].forEach(element => {
      clearTimeout(countdownTimers.get(element));
      countdownTimers.delete(element);
      initializedCapacity.delete(element);
      reveals.forEach(state => {
        state.observer?.unobserve(element);
        state.seen.delete(element);
      });
    });
  });

  /* ─── 1. Live Countdown Timers ─────────────────────────────────────────── */
  function initCountdowns() {
    document.querySelectorAll('[data-countdown]').forEach(function (el) {
      if (countdownTimers.has(el)) return;
      var targetMs = Number(el.dataset.countdown) * 1000;
      if (!Number.isFinite(targetMs)) return;
      countdownTimers.set(el, null);
      var wrap = el.closest('.tl-countdown');
      var timerId = null;

      function tick() {
        // Прекращаем, если элемент уже вне DOM (HTMX swap)
        if (!document.contains(el)) { clearTimeout(timerId); return; }

        var diff = targetMs - Date.now();
        if (diff <= 0) {
          if (wrap) {
            // B4-17: DOM manipulation вместо innerHTML для безопасности
            wrap.textContent = '';
            var icon = document.createElement('i');
            icon.className = 'fas fa-play me-1';
            var sp = document.createElement('span');
            sp.textContent = 'In progress';
            wrap.appendChild(icon);
            wrap.appendChild(sp);
          } else {
            el.textContent = '—';
          }
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
        countdownTimers.set(el, timerId);
      }
      tick();
    });
  }

  function pad(n) { return String(n).padStart(2, '0'); }

  /* ─── 2. Capacity Progress Bars ─────────────────────────────────────────── */
  function initCapacityBars() {
    document.querySelectorAll('.tl-cap-fill[data-filled]').forEach(function (bar) {
      if (initializedCapacity.has(bar)) return;
      initializedCapacity.add(bar);
      var filled = parseInt(bar.dataset.filled, 10) || 0;
      var max    = parseInt(bar.dataset.max,    10) || 0;
      if (!max) return;
      var pct = Math.min(100, Math.round(filled / max * 100));
      if (pct >= 100) bar.classList.add('tl-cap-fill--full');
      else if (pct >= 75) bar.classList.add('tl-cap-fill--warn');
    });
  }

  /* ─── 3. Timeline Stagger Reveal ─────────────────────────────────────────── */
  function initTimelineReveal() {
    revealNew('.tl-item', el => el.classList.add('tl-visible'),
      { threshold: 0.08, rootMargin: '0px 0px -40px 0px' }, 75);
  }

  function initArticleReveal() {
    revealNew('.iesa-article', el => el.classList.add('article-visible'),
      { threshold: 0.07, rootMargin: '0px 0px -30px 0px' }, 55);
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
    revealNew('.iesa-article:has(.art-progress-bar)', el => {
      const bar = el.querySelector('.art-progress-bar');
      const views = parseInt(bar.dataset.views, 10) || 0;
      bar.style.setProperty('--p', Math.min(97, Math.max(15, Math.round(views / 500 * 100))));
    }, { threshold: 0.2 });
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
