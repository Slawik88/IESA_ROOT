/**
 * SECTION INTERACTIONS - Enhanced interactivity for all homepage sections
 * Features: Lazy loading, animations, hover effects, smooth scrolling
 */

function initProductCardEffects() {
    const productCards = document.querySelectorAll('.product-card');
    productCards.forEach(card => {
        card.addEventListener('mouseenter', function () {
            this.style.boxShadow = '0 20px 50px rgba(248, 113, 113, 0.25)';
        });
        card.addEventListener('mouseleave', function () {
            this.style.boxShadow = '';
        });
        card.addEventListener('click', function () {
            this.classList.add('clicked');
            setTimeout(() => this.classList.remove('clicked'), 300);
        });
    });
}

function initEventCardEffects() {
    const eventCards = document.querySelectorAll('.event-card');
    eventCards.forEach(card => {
        card.addEventListener('mouseenter', function () {
            const dateEl = this.querySelector('.event-date');
            if (dateEl) dateEl.style.transform = 'scale(1.05)';
        });
        card.addEventListener('mouseleave', function () {
            const dateEl = this.querySelector('.event-date');
            if (dateEl) dateEl.style.transform = 'scale(1)';
        });
    });
}

function initMemberCardEffects() {
    const memberCards = document.querySelectorAll('.member-card, .president-card');
    memberCards.forEach(card => {
        card.addEventListener('mouseenter', function () {
            const avatar = this.querySelector('.member-avatar');
            if (avatar) avatar.style.filter = 'brightness(1.1) contrast(1.1)';
        });
        card.addEventListener('mouseleave', function () {
            const avatar = this.querySelector('.member-avatar');
            if (avatar) avatar.style.filter = '';
        });
    });
}

function initLazyImageLoading() {
    const images = document.querySelectorAll('img[data-src]');
    if (!images.length) return;
    const imageObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.classList.add('loaded');
                imageObserver.unobserve(img);
            }
        });
    }, { rootMargin: '50px' });
    images.forEach(img => imageObserver.observe(img));
}

// Parallax убран — мешает layout и производительности на мобильных.
// CSS-parallax через background-attachment выполняется GPU без JS.

(function addAnimationStyles() {
    if (document.getElementById('sections-anim-css')) return;
    const style = document.createElement('style');
    style.id = 'sections-anim-css';
    style.textContent = `
        .product-card.clicked { animation: cardPulse 0.4s ease-out; }
        @keyframes cardPulse {
            0%   { transform: scale(1); }
            50%  { transform: scale(1.02); }
            100% { transform: scale(1); }
        }
        img.loaded { animation: imageLoad 0.5s ease-out; }
        @keyframes imageLoad { from { opacity: 0; } to { opacity: 1; } }
    `;
    document.head.appendChild(style);
})();

function _initCard(card, fn) {
    // B4-09: guard против повторной инициализации при HTMX swap
    if (card.dataset.siInit) return;
    card.dataset.siInit = '1';
    fn(card);
}

function run() {
    // Запускаем только для новых (не инициализированных) карточек
    document.querySelectorAll('.product-card').forEach(c => _initCard(c, function(card) {
        card.addEventListener('mouseenter', function () { this.style.boxShadow = '0 20px 50px rgba(248,113,113,0.25)'; });
        card.addEventListener('mouseleave', function () { this.style.boxShadow = ''; });
        card.addEventListener('click', function () { this.classList.add('clicked'); setTimeout(() => this.classList.remove('clicked'), 300); });
    }));
    document.querySelectorAll('.event-card').forEach(c => _initCard(c, function(card) {
        card.addEventListener('mouseenter', function () { const d = this.querySelector('.event-date'); if (d) d.style.transform = 'scale(1.05)'; });
        card.addEventListener('mouseleave', function () { const d = this.querySelector('.event-date'); if (d) d.style.transform = ''; });
    }));
    document.querySelectorAll('.member-card, .president-card').forEach(c => _initCard(c, function(card) {
        card.addEventListener('mouseenter', function () { const a = this.querySelector('.member-avatar'); if (a) a.style.filter = 'brightness(1.1) contrast(1.1)'; });
        card.addEventListener('mouseleave', function () { const a = this.querySelector('.member-avatar'); if (a) a.style.filter = ''; });
    }));
    initLazyImageLoading();
}

// Первичная инициализация
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
} else {
    run();
}

// Переинициализация после HTMX swap (новые карточки в DOM)
document.addEventListener('htmx:afterSettle', run);

window.HomepageSections = { run };
