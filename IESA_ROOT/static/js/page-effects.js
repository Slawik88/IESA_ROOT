/**
 * IESA Page Effects v2.0
 * Global JS animations & interactions for all subpages
 * - Scroll-reveal (IntersectionObserver)
 * - Staggered card entrances
 * - Parallax heroes
 * - Typed text effect
 * - Tilt 3D on cards
 * - Animated counters
 * - Particle canvas on CTA sections
 * - Smooth lightbox transitions
 * - Magnetic buttons
 * - Floating background orbs
 */
(function () {
  'use strict';

  /* ──────────────────────────────────────────────
     0. CONSTANTS
     ────────────────────────────────────────────── */
  const EASE_OUT_CUBIC = 'cubic-bezier(.22,1,.36,1)';
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ──────────────────────────────────────────────
     1. GLOBAL SCROLL REVEAL  (data-reveal)
     Works on ALL pages, not just homepage
     ────────────────────────────────────────────── */
  function initScrollReveal() {
    const els = document.querySelectorAll('[data-reveal]');
    if (!els.length) return;

    // Inject CSS if not already present (subpages don't have it)
    if (!document.getElementById('iesa-reveal-css')) {
      const style = document.createElement('style');
      style.id = 'iesa-reveal-css';
      style.textContent = `
        [data-reveal] {
          opacity: 0;
          transform: translateY(32px);
          transition: opacity .65s ${EASE_OUT_CUBIC}, transform .65s ${EASE_OUT_CUBIC};
        }
        [data-reveal].revealed {
          opacity: 1;
          transform: none;
        }
        [data-reveal][data-delay="1"] { transition-delay: .08s; }
        [data-reveal][data-delay="2"] { transition-delay: .16s; }
        [data-reveal][data-delay="3"] { transition-delay: .24s; }
        [data-reveal][data-delay="4"] { transition-delay: .32s; }
        [data-reveal][data-delay="5"] { transition-delay: .40s; }
        [data-reveal][data-delay="6"] { transition-delay: .48s; }
        [data-reveal][data-delay="7"] { transition-delay: .56s; }
        [data-reveal][data-delay="8"] { transition-delay: .64s; }
        [data-reveal][data-delay="9"] { transition-delay: .72s; }
      `;
      document.head.appendChild(style);
    }

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
     Auto-applies to common card containers
     ────────────────────────────────────────────── */
  function initCardStagger() {
    const selectors = [
      '.post-card', '.ev-card', '.ben-card',
      '.gallery-thumb', '.product-card',
      '.gallery-grid .col', '.row.g-4 > .col-md-6',
      '.row.g-4 > .col-lg-4', '.row.g-3 > .col-12'
    ];
    const cards = document.querySelectorAll(selectors.join(','));
    if (!cards.length || prefersReducedMotion) return;

    // Inject stagger CSS
    if (!document.getElementById('iesa-stagger-css')) {
      const style = document.createElement('style');
      style.id = 'iesa-stagger-css';
      style.textContent = `
        .iesa-stagger {
          opacity: 0;
          transform: translateY(40px) scale(.97);
          transition: opacity .6s ${EASE_OUT_CUBIC}, transform .6s ${EASE_OUT_CUBIC};
        }
        .iesa-stagger.iesa-visible {
          opacity: 1;
          transform: none;
        }
      `;
      document.head.appendChild(style);
    }

    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (!e.isIntersecting) return;
        e.target.classList.add('iesa-visible');
        io.unobserve(e.target);
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

    cards.forEach((card, i) => {
      // Don't double-apply if parent already has data-reveal
      if (card.closest('[data-reveal]') && !card.hasAttribute('data-reveal')) return;
      card.classList.add('iesa-stagger');
      card.style.transitionDelay = `${Math.min(i * 0.07, 0.6)}s`;
      io.observe(card);
    });
  }

  /* ──────────────────────────────────────────────
     3. PARALLAX HERO SECTIONS
     Subtle vertical scroll parallax on hero backgrounds
     ────────────────────────────────────────────── */
  function initParallax() {
    const heroes = document.querySelectorAll(
      '.gal-hero, .ben-hero, .pl-hero, .ev-page-hero, .prod-hero'
    );
    if (!heroes.length || prefersReducedMotion) return;

    // Add ::after pseudo overlay for floating orbs
    heroes.forEach(hero => {
      hero.style.willChange = 'transform';
    });

    let ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const scrollY = window.scrollY;
        heroes.forEach(hero => {
          const rect = hero.getBoundingClientRect();
          if (rect.bottom < 0 || rect.top > window.innerHeight) return;
          const offset = scrollY * 0.35;
          hero.style.backgroundPositionY = `${offset}px`;
          // Subtle opacity fade
          const fadeStart = hero.offsetHeight * 0.5;
          if (scrollY > fadeStart) {
            hero.style.opacity = Math.max(1 - (scrollY - fadeStart) / hero.offsetHeight, 0.3);
          } else {
            hero.style.opacity = 1;
          }
        });
        ticking = false;
      });
    }
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  /* ──────────────────────────────────────────────
     4. TYPED TEXT EFFECT
     Add data-typed to any heading for typewriter effect
     ────────────────────────────────────────────── */
  function initTypedText() {
    /* V18 (дизайн-аудит): эффект печатной машинки отключён — заголовки статичны.
       Курсор мигал на каждой странице, заголовок застывал на полуслове при паузе
       рендера, а SEO/reader-mode видели пустой h1. Разметка data-typed безвредна. */
    return;
    const els = document.querySelectorAll('[data-typed]');
    if (!els.length || prefersReducedMotion) return;

    if (!document.getElementById('iesa-typed-css')) {
      const style = document.createElement('style');
      style.id = 'iesa-typed-css';
      style.textContent = `
        .iesa-typed-cursor {
          display: inline-block;
          width: 3px;
          height: 1em;
          background: var(--primary, #dc2626);
          margin-left: 4px;
          vertical-align: text-bottom;
          animation: iesa-blink .7s step-end infinite;
        }
        @keyframes iesa-blink { 0%,100%{opacity:1} 50%{opacity:0} }
      `;
      document.head.appendChild(style);
    }

    els.forEach(el => {
      const fullText = el.textContent.trim();
      const speed = parseInt(el.dataset.typed) || 45;
      el.textContent = '';
      el.style.visibility = 'visible';

      const cursor = document.createElement('span');
      cursor.className = 'iesa-typed-cursor';
      el.appendChild(cursor);

      const io = new IntersectionObserver(entries => {
        if (!entries[0].isIntersecting) return;
        io.disconnect();
        let i = 0;
        function type() {
          if (i < fullText.length) {
            el.insertBefore(document.createTextNode(fullText[i]), cursor);
            i++;
            setTimeout(type, speed + Math.random() * 30);
          } else {
            setTimeout(() => cursor.remove(), 2000);
          }
        }
        setTimeout(type, 400);
      }, { threshold: 0.5 });
      io.observe(el);
    });
  }

  /* ──────────────────────────────────────────────
     5. TILT 3D EFFECT ON CARDS
     Add data-tilt or .tilt3d class
     ────────────────────────────────────────────── */
  function initTilt() {
    const cards = document.querySelectorAll('[data-tilt], .tilt3d');
    if (!cards.length || prefersReducedMotion ||
        !window.matchMedia('(hover:hover) and (pointer:fine)').matches) return;

    cards.forEach(card => {
      card.style.transition = 'transform .2s ease';
      card.style.transformStyle = 'preserve-3d';

      card.addEventListener('mousemove', e => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const mx = (x / rect.width - 0.5) * 2;
        const my = (y / rect.height - 0.5) * 2;
        card.style.transform = `perspective(700px) rotateY(${mx * 5}deg) rotateX(${-my * 5}deg) scale3d(1.02,1.02,1.02)`;
      });

      card.addEventListener('mouseleave', () => {
        card.style.transform = '';
      });
    });
  }

  /* ──────────────────────────────────────────────
     6. ANIMATED COUNTERS
     Add data-count="123" to any element
     ────────────────────────────────────────────── */
  function initCounters() {
    const counters = document.querySelectorAll('[data-count]');
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
        const target = parseInt(e.target.dataset.count);
        animateCount(e.target, target, 1600);
        io.unobserve(e.target);
      });
    }, { threshold: 0.4 });

    counters.forEach(el => io.observe(el));
  }

  /* ──────────────────────────────────────────────
     7. PARTICLE/GLOW CANVAS on CTA sections
     Creates ambient floating particles
     ────────────────────────────────────────────── */
  function initParticles() {
    const ctas = document.querySelectorAll('.ben-cta, .prod-empty, .gal-empty');
    if (!ctas.length || prefersReducedMotion) return;

    ctas.forEach(container => {
      const canvas = document.createElement('canvas');
      canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0;opacity:.6;';
      container.style.position = 'relative';
      container.insertBefore(canvas, container.firstChild);

      const ctx = canvas.getContext('2d');
      let W, H, particles = [];

      function resize() {
        W = canvas.width = container.offsetWidth;
        H = canvas.height = container.offsetHeight;
      }
      resize();
      window.addEventListener('resize', resize);

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

      let animId;
      function draw() {
        ctx.clearRect(0, 0, W, H);
        particles.forEach(p => {
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
        });
        // Draw connection lines between nearby particles
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

      // Only animate when visible
      const io = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting) {
          draw();
        } else {
          cancelAnimationFrame(animId);
        }
      }, { threshold: 0 });
      io.observe(canvas);
    });
  }

  /* ──────────────────────────────────────────────
     8. MAGNETIC BUTTONS
     Buttons subtly follow cursor on hover
     ────────────────────────────────────────────── */
  function initMagneticButtons() {
    const btns = document.querySelectorAll('.hero-btn-p, .hero-btn-g, .btn-magnetic');
    if (!btns.length || prefersReducedMotion ||
        !window.matchMedia('(hover:hover)').matches) return;

    btns.forEach(btn => {
      btn.style.transition = 'transform .25s ease';
      btn.addEventListener('mousemove', e => {
        const rect = btn.getBoundingClientRect();
        const x = e.clientX - rect.left - rect.width / 2;
        const y = e.clientY - rect.top - rect.height / 2;
        btn.style.transform = `translate(${x * 0.2}px, ${y * 0.2}px)`;
      });
      btn.addEventListener('mouseleave', () => {
        btn.style.transform = '';
      });
    });
  }

  /* ──────────────────────────────────────────────
     9. FLOATING BACKGROUND ORBS
     Ambient glowing orbs behind hero sections
     ────────────────────────────────────────────── */
  function initFloatingOrbs() {
    const heroes = document.querySelectorAll(
      '.gal-hero, .ben-hero, .pl-hero, .ev-page-hero, .prod-hero'
    );
    if (!heroes.length || prefersReducedMotion) return;

    if (!document.getElementById('iesa-orbs-css')) {
      const style = document.createElement('style');
      style.id = 'iesa-orbs-css';
      style.textContent = `
        .iesa-orb {
          position: absolute;
          border-radius: 50%;
          filter: blur(60px);
          pointer-events: none;
          animation: iesa-orb-float 8s ease-in-out infinite alternate;
          z-index: 0;
        }
        .iesa-orb:nth-child(2) { animation-delay: -3s; animation-duration: 10s; }
        .iesa-orb:nth-child(3) { animation-delay: -6s; animation-duration: 12s; }
        @keyframes iesa-orb-float {
          0%   { transform: translate(0, 0) scale(1); }
          33%  { transform: translate(30px, -20px) scale(1.1); }
          66%  { transform: translate(-20px, 15px) scale(0.9); }
          100% { transform: translate(10px, -10px) scale(1.05); }
        }
      `;
      document.head.appendChild(style);
    }

    heroes.forEach(hero => {
      if (hero.querySelector('.iesa-orb')) return;
      const orbConfigs = [
        { w: 200, h: 200, bg: 'rgba(220,38,38,.12)', top: '10%', left: '15%' },
        { w: 150, h: 150, bg: 'rgba(139,92,246,.08)', top: '30%', right: '10%' },
        { w: 120, h: 120, bg: 'rgba(59,130,246,.06)', bottom: '20%', left: '50%' },
      ];
      orbConfigs.forEach(cfg => {
        const orb = document.createElement('div');
        orb.className = 'iesa-orb';
        orb.style.width = cfg.w + 'px';
        orb.style.height = cfg.h + 'px';
        orb.style.background = cfg.bg;
        if (cfg.top) orb.style.top = cfg.top;
        if (cfg.bottom) orb.style.bottom = cfg.bottom;
        if (cfg.left) orb.style.left = cfg.left;
        if (cfg.right) orb.style.right = cfg.right;
        hero.appendChild(orb);
      });
    });
  }

  /* ──────────────────────────────────────────────
     10. SMOOTH GALLERY LIGHTBOX TRANSITIONS
     Enhances the existing Bootstrap modal
     ────────────────────────────────────────────── */
  function initGalleryEnhance() {
    const modal = document.getElementById('galleryModal');
    const img = document.getElementById('galleryModalImage');
    if (!modal || !img) return;

    // Add smooth image transition
    if (!document.getElementById('iesa-gallery-css')) {
      const style = document.createElement('style');
      style.id = 'iesa-gallery-css';
      style.textContent = `
        #galleryModalImage {
          transition: opacity .35s ease, transform .35s ease;
        }
        #galleryModalImage.iesa-fading {
          opacity: 0;
          transform: scale(.95);
        }
        .gallery-thumb {
          cursor: pointer;
        }
        .gallery-thumb::after {
          content: '';
          position: absolute;
          inset: 0;
          border-radius: 16px;
          box-shadow: inset 0 0 0 0 rgba(220,38,38,0);
          transition: box-shadow .3s ease;
          pointer-events: none;
        }
        .gallery-thumb:hover::after {
          box-shadow: inset 0 0 0 2px rgba(220,38,38,.5);
        }
        /* Zoom cursor */
        .gallery-grid__item { cursor: zoom-in; }
      `;
      document.head.appendChild(style);
    }

    // Navigation, keyboard and swipe are owned by the gallery component itself.
    // A single controller prevents duplicate swipe events and desynchronised counters.
  }

  /* ──────────────────────────────────────────────
     11. PROGRESS BAR ANIMATION (shared utility)
     ────────────────────────────────────────────── */
  function initProgressBars() {
    const bars = document.querySelectorAll('[data-progress]');
    if (!bars.length) return;

    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (!e.isIntersecting) return;
        const val = e.target.dataset.progress;
        e.target.style.width = val + '%';
        io.unobserve(e.target);
      });
    }, { threshold: 0.3 });

    bars.forEach(bar => {
      bar.style.width = '0%';
      bar.style.transition = 'width 1.2s ' + EASE_OUT_CUBIC;
      io.observe(bar);
    });
  }

  /* ──────────────────────────────────────────────
     12. HERO TEXT ENTRANCE ANIMATION
     Animate hero text with split lines
     ────────────────────────────────────────────── */
  function initHeroEntrance() {
    const heroes = document.querySelectorAll(
      '.gal-hero .container, .ben-hero .container, .pl-hero .container, .ev-page-hero .container, .prod-hero .container'
    );
    if (!heroes.length || prefersReducedMotion) return;

    if (!document.getElementById('iesa-hero-entrance-css')) {
      const style = document.createElement('style');
      style.id = 'iesa-hero-entrance-css';
      style.textContent = `
        .iesa-hero-anim > * {
          opacity: 0;
          transform: translateY(24px);
          transition: opacity .7s ${EASE_OUT_CUBIC}, transform .7s ${EASE_OUT_CUBIC};
        }
        .iesa-hero-anim.iesa-hero-visible > *:nth-child(1) { opacity: 1; transform: none; transition-delay: .1s; }
        .iesa-hero-anim.iesa-hero-visible > *:nth-child(2) { opacity: 1; transform: none; transition-delay: .25s; }
        .iesa-hero-anim.iesa-hero-visible > *:nth-child(3) { opacity: 1; transform: none; transition-delay: .4s; }
        .iesa-hero-anim.iesa-hero-visible > *:nth-child(4) { opacity: 1; transform: none; transition-delay: .55s; }
      `;
      document.head.appendChild(style);
    }

    heroes.forEach(container => {
      container.classList.add('iesa-hero-anim');
      // Small delay so CSS is applied before adding visible class
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          container.classList.add('iesa-hero-visible');
        });
      });
    });
  }

  /* ──────────────────────────────────────────────
     13. RIPPLE EFFECT ON CLICK (buttons)
     ────────────────────────────────────────────── */
  function initRipple() {
    if (prefersReducedMotion) return;

    if (!document.getElementById('iesa-ripple-css')) {
      const style = document.createElement('style');
      style.id = 'iesa-ripple-css';
      style.textContent = `
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
      `;
      document.head.appendChild(style);
    }

    document.addEventListener('click', e => {
      const btn = e.target.closest('.hero-btn-p, .hero-btn-g, .ev-btn-primary, .post-card__btn');
      if (!btn) return;
      btn.style.position = 'relative';
      btn.style.overflow = 'hidden';
      const rect = btn.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height);
      const ripple = document.createElement('span');
      ripple.className = 'iesa-ripple';
      ripple.style.width = ripple.style.height = size + 'px';
      ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
      ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
      btn.appendChild(ripple);
      setTimeout(() => ripple.remove(), 700);
    });
  }

  /* ──────────────────────────────────────────────
     14. SMOOTH NUMBER TRANSITION on filter counts
     ────────────────────────────────────────────── */
  function initFilterAnimations() {
    // Animate filter pills on click
    document.querySelectorAll('.nav-pills .nav-link, .ev-filters-bar .nav-link, .pl-filters-bar .nav-link').forEach(link => {
      link.addEventListener('click', function () {
        this.style.transform = 'scale(.95)';
        setTimeout(() => { this.style.transform = ''; }, 150);
      });
    });
  }

  /* ──────────────────────────────────────────────
     15. IMAGE LAZY LOAD REVEAL
     Add fade-in when lazy-loaded images appear
     ────────────────────────────────────────────── */
  function initLazyReveal() {
    if (prefersReducedMotion) return;

    if (!document.getElementById('iesa-lazy-css')) {
      const style = document.createElement('style');
      style.id = 'iesa-lazy-css';
      style.textContent = `
        img[loading="lazy"] {
          opacity: 0;
          transition: opacity .5s ease;
        }
        img[loading="lazy"].iesa-loaded {
          opacity: 1;
        }
      `;
      document.head.appendChild(style);
    }

    document.querySelectorAll('img[loading="lazy"]').forEach(img => {
      if (img.complete) {
        img.classList.add('iesa-loaded');
      } else {
        img.addEventListener('load', () => img.classList.add('iesa-loaded'), { once: true });
      }
    });
  }

  /* ──────────────────────────────────────────────
     INIT ALL
     ────────────────────────────────────────────── */
  function init() {
    initScrollReveal();
    initCardStagger();
    initParallax();
    initTypedText();
    initTilt();
    initCounters();
    initParticles();
    initMagneticButtons();
    initFloatingOrbs();
    initGalleryEnhance();
    initProgressBars();
    initHeroEntrance();
    initRipple();
    initFilterAnimations();
    initLazyReveal();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Re-init on HTMX swap (for dynamic content)
  document.body.addEventListener('htmx:afterSettle', () => {
    initScrollReveal();
    initCardStagger();
    initLazyReveal();
    initCounters();
  });

  // Expose API
  window.IESAEffects = { init, initScrollReveal, initCardStagger };
})();
