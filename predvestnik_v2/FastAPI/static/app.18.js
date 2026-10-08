// ── Shell V3 · тиры скинов D…SSS: контроллер эффектов ────────────────────────────
// Тир скина (с сервера) задаёт потолок эффектов. Фактический уровень = min(тир, возможности устройства).
// CSS: fx-tiers-v3.css, документация: docs/SKINS_V3.md.
const _V3_TIER_LIST = ['D', 'C', 'B', 'A', 'S', 'SS', 'SSS'];
const _V3_FX_CAP_KEY = 'v3_fx_cap';
let _v3Skin = { css_class: '', tier: 'D' }, _v3FxLevel = 1, _v3Forced = false, _v3Watchdog = false, _v3PointerOn = false;

function v3FxLevelNow() { return _v3FxLevel; }
function _v3DeviceCap() {
  let cap = 7;
  try {
    const nav = navigator, lowMem = nav.deviceMemory && nav.deviceMemory <= 2, lowCpu = nav.hardwareConcurrency && nav.hardwareConcurrency <= 3;
    if (lowMem || lowCpu) cap = 3;
    if (nav.connection?.saveData) cap = Math.min(cap, 2);
    const stored = Number(localStorage.getItem(_V3_FX_CAP_KEY));
    if (stored >= 1 && stored < 7) cap = Math.min(cap, stored);
  } catch (_) { /* хранилище недоступно: остаётся оценка по железу */ }
  return cap;
}
function _v3Calm() {
  return document.body.classList.contains('no-fx') || !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
}
function _v3Rand(seed) { const x = Math.sin(seed * 9301 + 49297) * 233280; return x - Math.floor(x); }
function _v3BuildFx(level) {
  document.querySelector('.v3-fx')?.remove();
  if (level < 3) return;
  const layer = document.createElement('div'); layer.className = 'v3-fx'; layer.setAttribute('aria-hidden', 'true');
  const add = (cls, html = '') => { const n = document.createElement('div'); n.className = cls; n.innerHTML = html; layer.appendChild(n); };
  add('v3-fx-breath');
  if (level >= 4) add('v3-fx-grain');
  if (level >= 5) {
    const dots = Array.from({ length: 16 }, (_, i) => `<i style="--x:${(_v3Rand(i + 1) * 100).toFixed(1)}%;--s:${(2 + _v3Rand(i + 40) * 3).toFixed(1)}px;--d:${(14 + _v3Rand(i + 80) * 14).toFixed(1)}s;--delay:-${(_v3Rand(i + 120) * 20).toFixed(1)}s;--dx:${((_v3Rand(i + 160) - .5) * 80).toFixed(0)}px"></i>`).join('');
    add('v3-fx-dots', dots); layer.lastChild.style.cssText = 'inset:0';
  }
  if (level >= 6) add('v3-fx-tilt');
  if (level >= 7) { add('v3-fx-ribbon'); add('v3-fx-ribbon'); }
  document.body.appendChild(layer);
}
// Наклон телефона и указатель двигают слой SS+: обновление не чаще кадра
function _v3BindTilt() {
  if (_v3PointerOn) return; _v3PointerOn = true;
  let frame = 0, tx = 0, ty = 0;
  const push = () => { frame = 0; document.body.style.setProperty('--tilt-x', tx.toFixed(3)); document.body.style.setProperty('--tilt-y', ty.toFixed(3)); };
  const queue = () => { if (!frame) frame = requestAnimationFrame(push); };
  window.addEventListener('deviceorientation', e => { if (_v3FxLevel < 6 || e.gamma == null) return; tx = Math.max(-1, Math.min(1, e.gamma / 30)); ty = Math.max(-1, Math.min(1, (e.beta - 45) / 30)); queue(); }, { passive: true });
  window.addEventListener('pointermove', e => { if (_v3FxLevel < 6 || e.pointerType === 'touch') return; tx = e.clientX / innerWidth * 2 - 1; ty = e.clientY / innerHeight * 2 - 1; queue(); }, { passive: true });
}
function applySkinTier(skin, options = {}) {
  _v3Skin = { css_class: skin?.css_class || '', tier: _V3_TIER_LIST.includes(skin?.tier) ? skin.tier : 'D' };
  _v3Forced = !!options.force;
  const nominal = _V3_TIER_LIST.indexOf(_v3Skin.tier) + 1;
  const level = _v3Calm() ? 1 : _v3Forced ? nominal : Math.min(nominal, _v3DeviceCap());
  _v3FxLevel = level;
  const body = document.body;
  [...body.classList].forEach(name => { if (/^fx-\d$/.test(name) || /^tier-[a-z]+$/.test(name)) body.classList.remove(name); });
  for (let i = 1; i <= level; i++) body.classList.add(`fx-${i}`);
  body.classList.add(`tier-${_v3Skin.tier.toLowerCase()}`); body.dataset.tier = _v3Skin.tier;
  body.classList.toggle('ap-anim', !_v3Calm() && _v3DeviceCap() >= 3);   // движение образов (рамки, ореолы, частицы) не зависит от тира своего скина
  _v3BuildFx(level); if (level >= 6) _v3BindTilt();
  _v3StartWatchdog(level);
}
// Если устройство не тянет: после показа замеряем кадры и один раз снижаем потолок на две ступени
function _v3StartWatchdog(level) {
  if (_v3Watchdog || _v3Forced || level < 3) return; _v3Watchdog = true;
  setTimeout(() => {
    if (document.hidden) { _v3Watchdog = false; return; }
    const times = []; let last = performance.now(), count = 0;
    const tick = now => {
      times.push(now - last); last = now;
      if (++count < 90) { requestAnimationFrame(tick); return; }
      const sorted = times.slice(5).sort((a, b) => a - b), median = sorted[Math.floor(sorted.length / 2)];
      if (median > 30 && _v3FxLevel > 2) {
        try { localStorage.setItem(_V3_FX_CAP_KEY, String(Math.max(2, _v3FxLevel - 2))); } catch (_) { /* не сохранится: сработает снова в следующем сеансе */ }
        applySkinTier(_v3Skin);
      }
    };
    requestAnimationFrame(tick);
  }, 2500);
}
document.addEventListener('skinchange', e => applySkinTier(e.detail));
document.addEventListener('visibilitychange', () => document.body.classList.toggle('v3-paused', document.hidden));
// Круг от касания: только на SSS
document.addEventListener('pointerdown', e => {
  if (_v3FxLevel < 7) return;
  const ring = document.createElement('i'); ring.className = 'v3-ripple'; document.body.appendChild(ring);
  const run = ring.animate([{ transform: `translate(${e.clientX}px,${e.clientY}px) scale(.2)`, opacity: .9 }, { transform: `translate(${e.clientX}px,${e.clientY}px) scale(2.2)`, opacity: 0 }], { duration: 650, easing: 'cubic-bezier(.22,1,.36,1)' });
  run.onfinish = () => ring.remove();
}, { passive: true });
// Предпросмотр палитры и тира без покупки (консоль разработчика): v3SkinPreview('skin-neon-lime', 'SSS')
window.v3SkinPreview = (cssClass, tier) => {
  [...document.body.classList].forEach(name => { if (/^skin-/.test(name)) document.body.classList.remove(name); });
  if (/^skin-[a-z0-9-]{1,80}$/.test(cssClass || '')) document.body.classList.add(cssClass);
  applySkinTier({ css_class: cssClass, tier }, { force: true });
};
applySkinTier({ css_class: '', tier: 'D' });
