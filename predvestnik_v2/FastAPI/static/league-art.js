// Картинки Лиги: один SVG-спрайт в странице (символы <symbol>, градиенты в <defs>), без файлов и внешних библиотек.
// LeagueArt.icon('coin') → <svg><use href="#lga-coin"></svg>. Смысл всегда дублирует текст или aria-label: картинка не единственный носитель.
(() => {
  const SPRITE = `<svg xmlns="http://www.w3.org/2000/svg" class="lga-sprite" aria-hidden="true" focusable="false"><defs>
<linearGradient id="lga-g-gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe7a3"/><stop offset=".55" stop-color="#f2c45a"/><stop offset="1" stop-color="#c58a22"/></linearGradient>
<linearGradient id="lga-g-coin" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff0b8"/><stop offset=".5" stop-color="#f0bf4c"/><stop offset="1" stop-color="#b9781b"/></linearGradient>
<linearGradient id="lga-g-gem" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e9fbff"/><stop offset=".45" stop-color="#8fd8ff"/><stop offset="1" stop-color="#7a6bff"/></linearGradient>
<linearGradient id="lga-g-spark" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff6d6"/><stop offset=".5" stop-color="#ffc35c"/><stop offset="1" stop-color="#d36bff"/></linearGradient>
<linearGradient id="lga-g-heart" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff9cad"/><stop offset="1" stop-color="#e2445e"/></linearGradient>
<linearGradient id="lga-g-chest" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8a67ff"/><stop offset="1" stop-color="#3b2a7a"/></linearGradient>
</defs>
<symbol id="lga-star" viewBox="0 0 24 24"><path d="M12 2.2l2.9 6.1 6.7.8-4.9 4.6 1.3 6.6L12 17l-6 3.3 1.3-6.6-4.9-4.6 6.7-.8z"/></symbol>
<symbol id="lga-heart-l" viewBox="0 0 24 24"><path d="M12 6.2C10.6 3.9 8.4 3 6.6 3 3.9 3 2 5.2 2 8c0 5 6 9.2 10 12.6l-1.3-4.1 1.9-2.6-1.6-3 1.6-2.4z" fill="url(#lga-g-heart)"/></symbol>
<symbol id="lga-heart-r" viewBox="0 0 24 24"><path d="M12 6.2c1.4-2.3 3.6-3.2 5.4-3.2C20.1 3 22 5.2 22 8c0 5-6 9.2-10 12.6l-1.3-4.1 1.9-2.6-1.6-3 1.6-2.4z" fill="url(#lga-g-heart)"/><path d="M15.6 5.4c1.6-.2 3 .7 3.4 2.2" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.4" stroke-linecap="round"/></symbol>
<symbol id="lga-heart-o" viewBox="0 0 24 24"><path d="M12 6.2C10.6 3.9 8.4 3 6.6 3 3.9 3 2 5.2 2 8c0 5 6 9.2 10 12.6C16 17.2 22 13 22 8c0-2.8-1.9-5-4.6-5-1.8 0-4 .9-5.4 3.2z" fill="none" stroke="currentColor" stroke-width="1.6"/></symbol>
<symbol id="lga-coin" viewBox="0 0 32 32"><circle cx="16" cy="16" r="13" fill="url(#lga-g-coin)"/><circle cx="16" cy="16" r="9.6" fill="none" stroke="#8a5a12" stroke-opacity=".55" stroke-width="1.4"/><path d="M11 21V11l5 6 5-6v10" fill="none" stroke="#7a4c0c" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/><path d="M8.5 11.5a9 9 0 0 1 5-4.6" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width="1.6" stroke-linecap="round"/></symbol>
<symbol id="lga-gem" viewBox="0 0 32 32"><path d="M9 5h14l6 8-13 15L3 13z" fill="url(#lga-g-gem)"/><path d="M3 13h26M9 5l4 8 3 15M23 5l-4 8-3 15M13 13l3-8 3 8" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1"/><path d="M9 5h14l6 8-13 15L3 13z" fill="none" stroke="#3f2f9e" stroke-opacity=".5" stroke-width="1"/></symbol>
<symbol id="lga-spark" viewBox="0 0 32 32"><path d="M16 2l3.4 9.2L29 14l-8.2 4.6L22 29l-6-6.8L10 29l1.2-10.4L3 14l9.6-2.8z" fill="url(#lga-g-spark)"/><path d="M16 9l1.6 4.6 4.4 1.2-3.8 2.2.6 4.8L16 18.6l-2.8 3.2.6-4.8-3.8-2.2 4.4-1.2z" fill="#fff" fill-opacity=".6"/></symbol>
<symbol id="lga-key" viewBox="0 0 32 32"><circle cx="11" cy="11" r="7.2" fill="none" stroke="currentColor" stroke-width="3.4"/><path d="M16 16l11 11M21.5 21.5l3-3M24.5 24.5l2.6-2.6" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round"/><path d="M6.8 8.4a5 5 0 0 1 3-2.6" fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="1.5" stroke-linecap="round"/><path d="M18 18l7 7" stroke="#fff" stroke-opacity=".35" stroke-width="1" stroke-linecap="round"/></symbol>
<symbol id="lga-crown" viewBox="0 0 24 24"><path d="M3 8l4.5 4L12 4l4.5 8L21 8l-2 11H5z" fill="url(#lga-g-gold)"/><path d="M5 19h14" stroke="#8a5a12" stroke-opacity=".6" stroke-width="1.4"/><circle cx="12" cy="4" r="1.6" fill="#fff4cc"/></symbol>
<symbol id="lga-chest" viewBox="0 0 32 32"><path d="M4 13c0-5 5-8 12-8s12 3 12 8v3H4z" fill="url(#lga-g-chest)"/><rect x="4" y="15" width="24" height="12" rx="2" fill="url(#lga-g-chest)"/><path d="M4 16h24M10 6.5V27M22 6.5V27" stroke="#f2c45a" stroke-width="1.8"/><rect x="13.5" y="13" width="5" height="6" rx="1.2" fill="url(#lga-g-gold)"/></symbol>
<symbol id="lga-lock" viewBox="0 0 24 24"><rect x="5" y="10.5" width="14" height="10" rx="2.4" fill="currentColor"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="15.4" r="1.5" fill="#000" fill-opacity=".45"/></symbol>
<symbol id="lga-check" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="lga-mine" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6" fill="currentColor"/><path d="M12 2.5v4M12 17.5v4M2.5 12h4M17.5 12h4M5.3 5.3l2.8 2.8M15.9 15.9l2.8 2.8M5.3 18.7l2.8-2.8M15.9 8.1l2.8-2.8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="10" cy="10" r="1.6" fill="#fff" fill-opacity=".7"/></symbol>
<symbol id="lga-flag" viewBox="0 0 24 24"><path d="M6 21V3.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M7 4h11l-3 4 3 4H7z" fill="currentColor"/></symbol>
<symbol id="lga-restart" viewBox="0 0 24 24"><path d="M19.5 12a7.5 7.5 0 1 1-2.6-5.7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M19.8 3.8v4.7h-4.7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></symbol>
<symbol id="lga-medal" viewBox="0 0 48 48"><path d="M24 3l17 9.5v19L24 45 7 31.5v-19z" fill="currentColor" fill-opacity=".14" stroke="currentColor" stroke-width="2"/><path d="M24 9l12 6.8v13.6L24 39l-12-9.6V15.8z" fill="none" stroke="currentColor" stroke-opacity=".45" stroke-width="1.2"/></symbol>
<symbol id="lga-frame" viewBox="0 0 48 48"><path d="M24 2l22 22-22 22L2 24z" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M24 7l17 17-17 17L7 24z" fill="currentColor" fill-opacity=".06" stroke="currentColor" stroke-opacity=".4" stroke-width="1"/></symbol>
</svg>`;

  // Ключи четырёх уровней: тир сундука → металл (Обычный, Бронзовый, Серебряный, Платиновый)
  const METAL = {1: 'iron', 3: 'bronze', 4: 'silver', 6: 'platinum'};
  const KEY_NAMES = {1: 'Обычный', 3: 'Бронзовый', 4: 'Серебряный', 6: 'Платиновый'};
  const icon = (name, cls = '') => `<svg class="lga lga-${name} ${cls}" aria-hidden="true" focusable="false"><use href="#lga-${name}"/></svg>`;
  const heart = (state = 'full') => state === 'empty' ? `<span class="lga-heart is-empty">${icon('heart-o')}</span>`
    : `<span class="lga-heart"><svg class="lga lga-hl" aria-hidden="true"><use href="#lga-heart-l"/></svg><svg class="lga lga-hr" aria-hidden="true"><use href="#lga-heart-r"/></svg></span>`;
  const stars = (got, cls = '') => [1, 2, 3].map(n => icon('star', `${cls} ${n <= got ? 'is-on' : 'is-off'}`)).join('');
  const key = tier => icon('key', `lga-key--${METAL[tier] || 'iron'}`);

  // Награда Пропуска из текста сервера («🪙 100 Моры», «🗝 Бронзовый ключ · 3★+»): какой значок и что подписать коротко
  function reward(text) {
    const t = String(text || ''), num = (t.match(/\d[\d\s]*/) || [''])[0].replace(/\s/g, '');
    if (t.startsWith('🗝')) {
      const tier = Number((t.match(/(\d)★/) || [])[1]) || 1;
      return {kind: 'key', tier, amount: 1, art: key(tier), short: `${tier}★+`};
    }
    if (t.startsWith('🪙')) return {kind: 'mora', amount: Number(num), art: icon('coin'), short: num};
    if (t.startsWith('💎')) return {kind: 'diamonds', amount: Number(num), art: icon('gem'), short: num};
    if (t.startsWith('✨')) return {kind: 'zarniki', amount: Number(num), art: icon('spark'), short: num};
    return {kind: 'other', amount: 0, art: icon('chest'), short: t};
  }

  function mount() {
    if (document.querySelector('.lga-sprite')) return;
    document.body.insertAdjacentHTML('afterbegin', SPRITE);
  }
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);
  window.LeagueArt = {icon, heart, stars, key, reward, METAL, KEY_NAMES};
})();
