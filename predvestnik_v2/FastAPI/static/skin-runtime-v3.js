// ── Скин в играх (Ритм, Сапёр): палитра надетого образа из /skins-v3/me ─────────────
// Игры живут на отдельных страницах, поэтому токены ставятся на body так же, как в app.22.js.
(function () {
  'use strict';
  const KEY = /^--(?:v3-[a-z-]{2,16}|acc-rgb)$/;
  const safe = value => typeof value === 'string' && value.length < 400 && !/[;{}<>\\]|url\(|@import|expression/i.test(value);
  let applied = [];
  window.applyGlobalSkinV3 = function (state) {
    const body = document.body;
    applied.forEach(key => body.style.removeProperty(key)); applied = [];
    const worn = state && Array.isArray(state.items) ? state.items.find(item => item && item.equipped === true) : null;
    body.classList.toggle('skin-v3', !!(worn && worn.tokens));
    if (!worn || !worn.tokens) return;
    Object.entries(worn.tokens).forEach(([key, value]) => { if (KEY.test(key) && safe(value)) { body.style.setProperty(key, value); applied.push(key); } });
  };
})();
