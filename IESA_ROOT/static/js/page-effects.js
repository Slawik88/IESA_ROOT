/**
 * IESA Page Effects v3.0
 * Global JS interactions for all pages. Everything here only touches
 * transform / opacity (compositor) and never forces layout inside input handlers.
 * - Scroll-reveal (IntersectionObserver; CSS lives in animations.css, gated by html.js)
 * - Staggered card entrances (below-the-fold only → no flash on first paint)
 * - Tilt 3D on cards, magnetic buttons (rAF-batched, rect cached on enter)
 * - Animated counters (run once per element)
 * - Particle canvas on CTA sections (paused when off-screen / tab hidden)
 * - Click ripple, lazy-image fade-in
 */
(function () {
  'use strict';

  const EASE_OUT_CUBIC = 'cubic-bezier(.22,1,.36,1)';
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(hover:hover) and (pointer:fine)').matches;

  function injectCss(id, css) {
    if (document.getElementById(id)) return;
    const style = document.createElement('style');
    style.id = id;
    style.textContent = css;
    document.head.appendChild(style);
  }

  /* ──────────────────────────────────────────────
     1. SCROLL REVEAL  ([data-reveal])
     ────────────────────────────────────────────── */
  function initScrollReveal() {
    const els = document.querySelectorAll('[data-reveal]:not(.revealed)');
    if (!els.length) return;

    if (prefersReducedMotion) {
      els.forEach(el => el.classList.add('revealed'));
      return;
    }

    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (!e.isIntersecting) return;
        e.target.classList.add('revealed');
        io.unobserve(e.target);
      });
    }, { threshold: 0.12 });

    els.forEach(el => io.observe(el));
  }

  /* ──────────────────────────────────────────────
     2. STAGGERED CARD ENTRANCE
     Only cards that start below the fold are animated; visible ones would
     otherwise flash (visible → hidden → fade in).
     ────────────────────────────────────────────── */
  function initCardStagger() {
    if (prefersReducedMotion) return;
    // Only inside <main>: footer / navbar columns must not animate in
    const cards = document.querySelectorAll([
      '.post-card', '.ev-card', '.ben-card',
      '.gallery-thumb', '.product-card',
      '.gallery-grid .col', '.row.g-4 > .col-md-6',
      '.row.g-4 > .col-lg-4', '.row.g-3 > .col-12'
    ].map(s => 'main ' + s).join(','));
    if (!cards.length) return;

    injectCss('iesa-stagger-css', `
      .iesa-stagger {
        opacity: 0;
        transform: translateY(40px) scale(.97);
        transition: opacity .6s ${EASE_OUT_CUBIC}, transform .6s ${EASE_OUT_CUBIC};
      }
      .iesa-stagger.iesa-visible { opacity: 1; transform: none; }
    `);

    const vh = window.innerHeight;
    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (!e.isIntersecting) return;
        e.target.classList.add('iesa-visible');
        io.unobserve(e.target);
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

    let i = 0;
    cards.forEach(card => {
      if (card.dataset.staggerInit) return;
      card.dataset.staggerInit = '1';
      // Parent already reveals itself
      if (card.closest('[data-reveal]') && !card.hasAttribute('data-reveal')) return;
      if (card.getBoundingClientRect().top < vh) return;
      card.classList.add('iesa-stagger');
      card.style.transitionDelay = `${Math.min(i++ * 0.07, 0.6)}s`;
      io.observe(card);
    });
  }

  /* ──────────────────────────────────────────────
     3. POINTER-DRIVEN TRANSFORMS (tilt + magnetic)
     rect is measured once on pointerenter, writes are batched in rAF,
     will-change is only set while the pointer is over the element.
     ────────────────────────────────────────────── */
  function pointerEffect(el, compute, restTransition) {
    let rect = null;
    let raf = 0;
    let px = 0;
    let py = 0;

    function paint() {
      raf = 0;
      el.style.transform = compute(px - rect.left, py - rect.top, rect);
    }

    el.addEventListener('pointerenter', e => {
      if (e.pointerType && e.pointerType !== 'mouse') return;
      rect = el.getBoundingClientRect();
      el.style.willChange = 'transform';
      el.style.transition = 'none'; // follow the cursor 1:1
    });
    el.addEventListener('pointermove', e => {
      if (!rect) return;
      px = e.clientX;
      py = e.clientY;
      if (!raf) raf = requestAnimationFrame(paint);
    });
    el.addEventListener('pointerleave', () => {
      rect = null;
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      el.style.transition = restTransition; // ease back to rest
      el.style.transform = '';
      el.style.willChange = '';
    });
  }

  function initTilt() {
    if (prefersReducedMotion || !finePointer) return;
    document.querySelectorAll('[data-tilt]:not([data-fx]), .tilt3d:not([data-fx])').forEach(card => {
      card.dataset.fx = '1';
      card.style.transformStyle = 'preserve-3d';
      pointerEffect(card, (x, y, r) => {
        const mx = (x / r.width - 0.5) * 2;
        const my = (y / r.height - 0.5) * 2;
        return `perspective(700px) rotateY(${mx * 5}deg) rotateX(${-my * 5}deg) scale3d(1.02,1.02,1.02)`;
      }, 'transform .35s ' + EASE_OUT_CUBIC);
    });
  }

  function initMagneticButtons() {
    if (prefersReducedMotion || !finePointer) return;
    document.querySelectorAll('.hero-btn-p, .hero-btn-g, .btn-magnetic, .mag-btn').forEach(btn => {
      if (btn.dataset.fx) return;
      btn.dataset.fx = '1';
      pointerEffect(btn, (x, y, r) =>
        `translate3d(${(x - r.width / 2) * 0.22}px, ${(y - r.height / 2) * 0.22}px, 0)`,
        'transform .35s ' + EASE_OUT_CUBIC);
    });
  }

  /* ──────────────────────────────────────────────
     4. ANIMATED COUNTERS  ([data-count], runs once)
     ────────────────────────────────────────────── */
  function initCounters() {
    const counters = document.querySelectorAll('[data-count]:not([data-counted])');
    if (!counters.length) return;

    function animateCount(el, target, duration) {
      const start = performance.now();
      (function step(now) {
        const p = Math.min((now - start) / duration, 1);
        el.textContent = Math.round((1 - Math.pow(1 - p, 3)) * target);
        if (p < 1) requestAnimationFrame(step);
        else el.textContent = target;
      })(start);
    }

    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        const target = parseInt(e.target.dataset.count, 10);
        if (isNaN(target)) return;
        if (prefersReducedMotion) { e.target.textContent = target; return; }
        animateCount(e.target, target, 1600);
      });
    }, { threshold: 0.4 });

    counters.forEach(el => {
      el.dataset.counted = '1';
      io.observe(el);
    });
  }

  /* ──────────────────────────────────────────────
     5. PARTICLE CANVAS on CTA sections
     Runs only while visible and while the tab is shown.
     ────────────────────────────────────────────── */
  function initParticles() {
    const ctas = document.querySelectorAll('.ben-cta, .prod-empty, .gal-empty');
    if (!ctas.length || prefersReducedMotion) return;

    ctas.forEach(container => {
      if (container.dataset.particles) return;
      container.dataset.particles = '1';

      const canvas = document.createElement('canvas');
      canvas.setAttribute('aria-hidden', 'true');
      canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0;opacity:.6;';
      if (getComputedStyle(container).position === 'static') container.style.position = 'relative';
      container.insertBefore(canvas, container.firstChild);

      const ctx = canvas.getContext('2d');
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      let W = 0;
      let H = 0;
      const particles = [];

      function resize() {
        W = container.offsetWidth;
        H = container.offsetHeight;
        canvas.width = W * dpr;
        canvas.height = H * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
      resize();
      let resizeTimer;
      window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(resize, 150);
      }, { passive: true });

      const count = Math.min(Math.floor(W * H / 15000), 30);
      for (let i = 0; i < count; i++) {
        particles.push({
          x: Math.random() * W,
          y: Math.random() * H,
          r: Math.random() * 2.5 + 0.8,
          vx: (Math.random() - 0.5) * 0.5,
          vy: (Math.random() - 0.5) * 0.3,
          alpha: Math.random() * 0.5 + 0.2,
        });
      }

      let animId = 0;
      function draw() {
        ctx.clearRect(0, 0, W, H);
        for (const p of particles) {
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < 0) p.x = W;
          if (p.x > W) p.x = 0;
          if (p.y < 0) p.y = H;
          if (p.y > H) p.y = 0;
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(220,38,38,${p.alpha})`;
          ctx.fill();
        }
        for (let i = 0; i < particles.length; i++) {
          for (let j = i + 1; j < particles.length; j++) {
            const dx = particles[i].x - particles[j].x;
            const dy = particles[i].y - particles[j].y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 100) {
              ctx.beginPath();
              ctx.moveTo(particles[i].x, particles[i].y);
              ctx.lineTo(particles[j].x, particles[j].y);
              ctx.strokeStyle = `rgba(220,38,38,${0.12 * (1 - dist / 100)})`;
              ctx.lineWidth = 0.5;
              ctx.stroke();
            }
          }
        }
        animId = requestAnimationFrame(draw);
      }

      let inView = false;
      function sync() {
        const shouldRun = inView && !document.hidden;
        if (shouldRun && !animId) animId = requestAnimationFrame(draw);
        else if (!shouldRun && animId) { cancelAnimationFrame(animId); animId = 0; }
      }
      new IntersectionObserver(entries => {
        inView = entries[0].isIntersecting;
        sync();
      }, { threshold: 0 }).observe(canvas);
      document.addEventListener('visibilitychange', sync);
    });
  }

  /* ──────────────────────────────────────────────
     6. RIPPLE ON CLICK (buttons)
     ────────────────────────────────────────────── */
  function initRipple() {
    if (prefersReducedMotion) return;

    injectCss('iesa-ripple-css', `
      .iesa-ripple {
        position: absolute;
        border-radius: 50%;
        background: rgba(255,255,255,.35);
        transform: scale(0);
        animation: iesa-ripple-expand .6s ease-out forwards;
        pointer-events: none;
      }
      @keyframes iesa-ripple-expand {
        to { transform: scale(4); opacity: 0; }
      }
    `);

    document.addEventListener('click', e => {
      const btn = e.target.closest('.hero-btn-p, .hero-btn-g, .ev-btn-primary, .post-card__btn');
      if (!btn) return;
      if (getComputedStyle(btn).position === 'static') btn.style.position = 'relative';
      btn.style.overflow = 'hidden';
      const rect = btn.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height);
      const ripple = document.createElement('span');
      ripple.className = 'iesa-ripple';
      ripple.style.width = ripple.style.height = size + 'px';
      ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
      ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
      btn.appendChild(ripple);
      ripple.addEventListener('animationend', () => ripple.remove(), { once: true });
    });
  }

  /* ──────────────────────────────────────────────
     7. LAZY IMAGE FADE-IN (CSS in animations.css, gated by html.js)
     A failed image is also revealed so its alt text stays visible.
     ────────────────────────────────────────────── */
  function initLazyReveal() {
    document.querySelectorAll('img[loading="lazy"]:not(.iesa-loaded)').forEach(img => {
      if (img.complete) {
        img.classList.add('iesa-loaded');
      } else {
        const done = () => img.classList.add('iesa-loaded');
        img.addEventListener('load', done, { once: true });
        img.addEventListener('error', done, { once: true });
      }
    });
  }

  function init() {
    initScrollReveal();
    initCardStagger();
    initTilt();
    initCounters();
    initParticles();
    initMagneticButtons();
    initRipple();
    initLazyReveal();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Re-init on HTMX swap (dynamic content); every initializer is idempotent
  document.body.addEventListener('htmx:afterSettle', () => {
    initScrollReveal();
    initCardStagger();
    initLazyReveal();
    initCounters();
    initTilt();
  });

  window.IESAEffects = { init, initScrollReveal, initCardStagger };
})();
