// ── Skins V3 · скин приложения и фирменные детали ───────────────────────────────
// v3ApplyLook: палитра надетого скина приходит с сервера токенами и ставится на body (без отдельного CSS на скин).
// Тир скина управляет уровнем эффектов (app.18.js). Без скина остаётся базовая палитра из shell-v3.css.
const _V3_TOKEN = /^--(?:v3-[a-z-]{2,16}|acc-rgb)$/;
let _v3Applied = [];
// Токены скина как строка style для .v3-scope (витрина, публичная карточка): те же проверки, что и для body
function v3TokenStyle(tokens) {
  if (!tokens || typeof tokens !== 'object') return '';
  return Object.entries(tokens).filter(([key, value]) => _V3_TOKEN.test(key) && _v3SafeValue(value)).map(([key, value]) => `${key}:${value}`).join(';');
}
function _v3SafeValue(value) { return typeof value === 'string' && value.length < 400 && !/[;{}<>\\]|url\(|@import|expression/i.test(value); }
function v3ApplyLook(look) {
  const style = document.body.style;
  _v3Applied.forEach(key => style.removeProperty(key));
  _v3Applied = [];
  [...document.body.classList].forEach(name => { if (/^skin-/.test(name)) document.body.classList.remove(name); });   // наследие прежних скинов
  const tokens = look && typeof look.tokens === 'object' ? look.tokens : null;
  if (tokens) {
    for (const [key, value] of Object.entries(tokens)) {
      if (_V3_TOKEN.test(key) && _v3SafeValue(value)) { style.setProperty(key, value); _v3Applied.push(key); }
    }
  }
  document.body.dataset.skin = look && /^[a-z_]{2,24}$/.test(look.id || '') ? look.id : '';
  document.dispatchEvent(new CustomEvent('skinchange', { detail: { css_class: '', tier: _AP_TIERS.includes(look?.tier) ? look.tier : 'D' } }));
}

// Фирменные детали: живут внутри рамки аватара и открываются, когда скин прокачан до своего потолка.
// Форма и движение описаны в skin-signatures-v3.css и skin-signatures-2-v3.css.
const _AP_DECOR = (() => {
  const many = (cls, count, vars) => Array.from({ length: count }, (_, i) => `<u class="${cls}" style="${vars(i)}"></u>`).join('');
  return {
    void: '<u class="sg-disk"></u><u class="sg-arc"></u>',
    aurora: '<u class="sg-veil"></u><u class="sg-veil"></u><u class="sg-veil"></u>',
    solar: many('sg-prom', 7, i => `--o:${i * 51.4}deg;--d:${(2.2 + (i % 3) * .5).toFixed(1)}s;--l:${(.7 + (i % 3) * .18).toFixed(2)}`),
    petalstorm: many('sg-pet', 9, i => `--o:${i * 40}deg;--r:${44 + (i % 3) * 8}px;--d:${(9 + (i % 4) * 2).toFixed(0)}s`),
    artifact: '<svg class="sg-hex" viewBox="0 0 100 100"><polygon points="50,2 93,26 93,74 50,98 7,74 7,26"/><polygon class="sg-hex-in" points="50,10 86,30 86,70 50,90 14,70 14,30"/></svg>' + many('sg-drone', 3, i => `--o:${i * 120}deg`) + '<u class="sg-tear"></u>',
    lotus: `<u class="sg-bloom">${[-58, -29, 0, 29, 58].map(a => `<u class="sg-leaf" style="--o:${a}deg"></u>`).join('')}${[-38, 0, 38].map(a => `<u class="sg-leaf sg-leaf--f" style="--o:${a}deg"></u>`).join('')}</u><u class="sg-moon"></u>`,
    tide: '<u class="sg-scales"></u><u class="sg-crack"></u>' + many('sg-wave', 3, i => `--i:${i}`),
    comet: '<u class="sg-orbit"><u class="sg-head"></u></u><u class="sg-orbit sg-orbit--far"><u class="sg-head"></u></u>',
    chrono: '<u class="sg-dial"></u><u class="sg-hand sg-hand--min"></u><u class="sg-hand sg-hand--hour"></u><u class="sg-cog"></u><u class="sg-cog sg-cog--r"></u>',
    heart: '<u class="sg-pulse"></u><u class="sg-pulse"></u><u class="sg-pulse"></u><u class="sg-core"></u>',
  };
})();
function apSigDecor(sig) { return _AP_DECOR[sig] || ''; }
