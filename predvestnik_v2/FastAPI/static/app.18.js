// ── Shell V3 · тиры скинов D…SSS: контроллер эффектов ────────────────────────────
// Тир скина (с сервера) задаёт потолок эффектов. Фактический уровень = min(тир, возможности устройства).
// CSS: fx-tiers-v3.css, документация: docs/SKINS_V3.md.
const _V3_TIER_LIST = ['D', 'C', 'B', 'A', 'S', 'SS', 'SSS'];
const _V3_FX_CAP_KEY = 'v3_fx_cap', _V3_LITE_KEY = 'v3_lite', _V3_LOW_KEY = 'v3_low';
// Пометка слабого телефона (лёгкий режим, экономный режим, сниженный потолок) хранится в localStorage и без этого держалась бы вечно, даже когда вид уже ускорили. После каждого ускорения
// номер ревизии растёт, пометки сбрасываются, и телефон проверяется заново: если он всё ещё не тянет, замер кадров вернёт пометку через несколько секунд.
const _V3_PERF_REV = '2026-10-12a';
try {
  if (localStorage.getItem('v3_perf_rev') !== _V3_PERF_REV) {
    [_V3_FX_CAP_KEY, _V3_LITE_KEY, _V3_LOW_KEY].forEach(key => localStorage.removeItem(key));
    localStorage.setItem('v3_perf_rev', _V3_PERF_REV);
  }
} catch (_) { /* без хранилища пометок и не было */ }
let _v3Skin = { css_class: '', tier: 'D' }, _v3FxLevel = 1, _v3Forced = false, _v3Watchdog = false, _v3PointerOn = false;

function v3FxLevelNow() { return _v3FxLevel; }
function _v3DeviceCap() {
  let cap = 7;
  try {
    const nav = navigator, mem = nav.deviceMemory, cores = nav.hardwareConcurrency;
    // Safari и WebView на iPhone не отдают deviceMemory, а число ядер там занижено (6 у быстрых моделей): без памяти судим только по самым слабым.
    if ((mem && mem <= 2) || (cores && cores <= 3)) cap = 3;            // слабый телефон
    else if ((mem && mem <= 4) || (!mem && cores && cores <= 4)) cap = 6;   // средний: без лент света SSS; движение образов остаётся, зависимость от кадров решает замер ниже
    if (nav.connection?.saveData) cap = Math.min(cap, 2);
    const stored = Number(localStorage.getItem(_V3_FX_CAP_KEY));
    if (stored >= 1 && stored < 7) cap = Math.min(cap, stored);
  } catch (_) { /* хранилище недоступно: остаётся оценка по железу */ }
  return cap;
}
// Класс устройства: low (слабый), mid (средний), high. Решает, сколько движения включать (app.31.js) и какой режим образов нужен.
// Режимов образов три: полный (high), лёгкий .ap-lite (mid: частиц вдвое меньше, без «акцентного» слоя сцены) и экономный .ap-low (low или замер кадров не выдержал:
// фирменные детали и фон стоят на месте). Полный вид никогда не отключается «на всякий случай»: вниз ведёт только железо или замер кадров.
function _v3Class() { const cap = _v3DeviceCap(); return cap <= 3 ? 'low' : cap <= 6 ? 'mid' : 'high'; }
function _v3Lite() {
  try { if (localStorage.getItem(_V3_LITE_KEY) === '1' || localStorage.getItem(_V3_LOW_KEY) === '1') return true; } catch (_) { /* без памяти: только оценка по железу */ }
  return _v3Class() !== 'high';
}
function _v3Low() {
  try { if (localStorage.getItem(_V3_LOW_KEY) === '1') return true; } catch (_) { /* см. выше */ }
  return _v3Class() === 'low';
}
function _v3Calm() {
  return document.body.classList.contains('no-fx') || !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
}
function _v3Rand(seed) { const x = Math.sin(seed * 9301 + 49297) * 233280; return x - Math.floor(x); }
// Фон страницы (B и выше) рисует JS на ОДНОМ холсте размером с экран, а не слоями CSS. Сначала слоёв было пять (дыхание, зерно, наклон, две ленты), потом три (акварель body::before, пятна света, зерно): каждый слой на весь
// экран это экран текстуры в памяти и экран заливки на каждом кадре. На телефоне с плотностью 3 набиралось больше 60 МБ графики, и на SSS экран мигал, элементы пропадали и появлялись, кадры падали до 10.
// Теперь холст один (1 пиксель = 1 пиксель CSS): акварель, пятна света и зерно рисуются в нём в том же порядке, в каком лежали слоями. Акварель и зерно не меняются: они собраны один раз на запасных холстах и просто
// копируются. Пятна считаются на крошечном холсте (1 пиксель = 4 пикселя экрана; мягкие градиенты, браузер растягивает их сам). Движение медленное, поэтому пятна пересчитываются раз в 200 мс.
// Формулы те же, что были в CSS: размеры, прозрачность, сроки и ease-in-out (v3breath 9 с, v3ribbon 26 и 34 с, сдвиг по наклону 10 px).
const _V3_FX = { glow: null, low: null, wash: null, grain: null, washList: null, washKey: null, timer: 0, size: 0, w: 0, h: 0, rgb: ['216,207,253', '216,207,253', '216,207,253'], loop: 1, colorsAt: 0, tilt: [0, 0], frozen: false };   // frozen: только для проверок (tools/ui_skin_lab.py)
const _V3_FX_STEP = 200, _V3_FX_SCALE = 4;
function _v3Ease(x) {   // cubic-bezier(.42, 0, .58, 1): ease-in-out из CSS
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  let t = x;
  for (let i = 0; i < 6; i++) {
    const u = 1 - t, cx = 3 * u * u * t * .42 + 3 * u * t * t * .58 + t * t * t, dx = 1.26 * u * u + .96 * u * t + 1.26 * t * t;
    if (Math.abs(cx - x) < 1e-5 || dx < 1e-6) break;
    t -= (cx - x) / dx;
  }
  const u = 1 - t; return 3 * u * t * t + t * t * t;
}
// Акварель страницы это токен --v3-wash: два эллипса света radial-gradient(RX% RY% at X% Y%, rgba(...), transparent S%). Читается в список; запись не по этой форме возвращает null,
// и тогда акварель остаётся слоем CSS (body::before), холст её не трогает.
function _v3FxParseWash(text) {
  if (!text || text === 'none') return [];
  const re = /radial-gradient\(\s*(-?[\d.]+)%\s+(-?[\d.]+)%\s+at\s+(-?[\d.]+)%\s+(-?[\d.]+)%\s*,\s*rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)\s*,\s*transparent\s+(-?[\d.]+)%\s*\)/g;
  const list = []; let rest = text, m;
  while ((m = re.exec(text))) {
    list.push({ rx: +m[1] / 100, ry: +m[2] / 100, x: +m[3] / 100, y: +m[4] / 100, rgb: `${m[5]},${m[6]},${m[7]}`, a: m[8] === undefined ? 1 : +m[8], end: Math.max(0, Math.min(1, +m[9] / 100)) });
    rest = rest.replace(m[0], '');
  }
  return rest.replace(/[\s,]+/g, '') === '' && list.length ? list : null;
}
function _v3FxPaintWash() {   // запасной холст с акварелью: нижний градиент рисуется первым, как нижний слой background
  const list = _V3_FX.washList, cv = _V3_FX.glow, wash = _V3_FX.wash;
  if (!cv || !wash || !list) return;
  const W = wash.width = cv.width, H = wash.height = cv.height, ctx = wash.getContext('2d');
  for (let i = list.length - 1; i >= 0; i--) {
    const g = list[i]; ctx.save(); ctx.translate(g.x * W, g.y * H); ctx.scale(g.rx * W, g.ry * H);
    const fill = ctx.createRadialGradient(0, 0, 0, 0, 0, 1); fill.addColorStop(0, `rgba(${g.rgb},${g.a})`); fill.addColorStop(g.end, `rgba(${g.rgb},0)`);
    ctx.fillStyle = fill; ctx.fillRect(-g.x / g.rx, -g.y / g.ry, 1 / g.rx, 1 / g.ry); ctx.restore();
  }
}
function _v3FxColors() {   // цвета берутся из токенов образа; читаются не чаще раза в полторы секунды
  const now = performance.now(); if (now - _V3_FX.colorsAt < 1500) return; _V3_FX.colorsAt = now;
  const body = document.body, cs = getComputedStyle(body), probe = document.createElement('i');
  probe.style.cssText = 'position:absolute;visibility:hidden;pointer-events:none'; body.appendChild(probe);
  const color = name => {
    probe.style.color = `var(${name})`;
    const text = getComputedStyle(probe).color, n = (text.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    return n.length === 3 ? n.map(v => Math.round(/^color\(/.test(text) ? v * 255 : v)).join(',') : '216,207,253';
  };
  _V3_FX.rgb = [(cs.getPropertyValue('--acc-rgb').trim().replace(/\s+/g, '') || '216,207,253'), color('--v3-fx-a'), color('--v3-fx-b')];
  _V3_FX.loop = parseFloat(cs.getPropertyValue('--v3-loop')) || 1;
  probe.remove();
  const wash = cs.getPropertyValue('--v3-wash').trim();
  if (wash !== _V3_FX.washKey) {   // смена образа или режима OLED: акварель собирается заново, слой CSS уходит, пока холст её держит
    _V3_FX.washKey = wash; _V3_FX.washList = _v3FxParseWash(wash); _v3FxPaintWash();
    body.classList.toggle('v3-fx-wash', !!_V3_FX.washList && !!_V3_FX.glow?.getContext('2d'));
  }
}
// Один кадр света. ms: время в миллисекундах (для проверок кадр можно нарисовать на любом моменте).
function _v3FxFrame(ms) {
  const cv = _V3_FX.glow, ctx = cv && cv.getContext('2d'), low = _V3_FX.low, lc = low && low.getContext('2d'); if (!ctx || !lc) return;
  _v3FxColors();
  const W = _V3_FX.w || innerWidth, H = _V3_FX.h || innerHeight, level = _v3FxLevel, [acc, fa, fb] = _V3_FX.rgb, loop = _V3_FX.loop, k = low.width / W;   // размер экрана кэшируется: чтение innerWidth заставляет браузер пересчитать стили всех анимаций
  lc.setTransform(1, 0, 0, 1, 0, 0); lc.clearRect(0, 0, low.width, low.height); lc.setTransform(k, 0, 0, k, 0, 0);
  const blob = (cx, cy, rx, ry, rgb, alpha, end = 1) => {   // эллипс с мягким краем: radial-gradient(closest-side, цвет, transparent)
    lc.save(); lc.translate(cx, cy); lc.scale(rx, ry); lc.globalAlpha = alpha;
    const g = lc.createRadialGradient(0, 0, 0, 0, 0, 1); g.addColorStop(0, `rgba(${rgb},1)`); g.addColorStop(end, `rgba(${rgb},0)`);
    lc.fillStyle = g; lc.fillRect(-1, -1, 2, 2); lc.restore();
  };
  const swing = (seconds, back) => { const p = (ms / (seconds * 1000 * loop)) % 2, q = p < 1 ? p : 2 - p; return _v3Ease(back ? 1 - q : q); };   // alternate / alternate-reverse
  { const e = swing(9), s = 1 + .08 * e; blob(.5 * W, .5 * H - .6 * H * s, .72 * W * s, .48 * H * s, acc, .2 * (.35 + .65 * e), .7); }   // дыхание: свет сверху, 9 с
  if (level >= 6) {   // два пятна, которые сдвигаются от наклона телефона
    const bw = 1.12 * W, bh = 1.12 * H, ox = -.06 * W + _V3_FX.tilt[0] * 10, oy = -.06 * H + _V3_FX.tilt[1] * 10;
    blob(ox + .4 * bw, oy + .29 * bh, .4 * bw, .25 * bh, fa, .22); blob(ox + .7 * bw, oy + .67 * bh, .4 * bw, .25 * bh, fb, .14);
  }
  if (level >= 7) {   // две ленты света, 26 и 34 с
    const e1 = swing(26), e2 = swing(34, true);
    blob(.5 * W + (-.08 + .16 * e1) * 1.5 * W, .2 * H + .06 * e1 * .7 * H, .75 * W * (.9 + .2 * e1), .35 * H * (.9 + .2 * e1), fa, .16);
    blob(.5 * W + (-.08 + .16 * e2) * 1.5 * W, .9 * H + .06 * e2 * .7 * H, .75 * W * (.9 + .2 * e2), .35 * H * (.9 + .2 * e2), fb, .12);
  }
  // порядок слоёв как был: акварель, пятна света, зерно
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  if (_V3_FX.washList) { ctx.globalCompositeOperation = 'copy'; ctx.drawImage(_V3_FX.wash, 0, 0); ctx.globalCompositeOperation = 'source-over'; } else ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.drawImage(low, 0, 0, cv.width, cv.height);
  if (_V3_FX.grain) ctx.drawImage(_V3_FX.grain, 0, 0);
}
function _v3FxRun() {
  clearTimeout(_V3_FX.timer);
  if (!_V3_FX.glow || document.hidden || _V3_FX.frozen) return;
  _v3FxFrame(performance.now());
  _V3_FX.timer = setTimeout(_v3FxRun, _V3_FX_STEP);
}
// Зерно: плитка шума 160 px на запасном холсте размером с экран, 1 пиксель = 1 пиксель CSS. Прозрачность .07 (она раньше стояла в CSS) вшита в плитку; шум не меняется, поэтому зерно собирается один раз.
function _v3FxPaintGrain() {
  const cv = _V3_FX.glow, grain = _V3_FX.grain; if (!cv || !grain) return;
  grain.width = cv.width; grain.height = cv.height;
  const ctx = grain.getContext('2d'), tile = document.createElement('canvas'); tile.width = tile.height = 160;
  const tc = tile.getContext('2d'), img = tc.createImageData(160, 160), d = img.data;
  for (let i = 0; i < d.length; i += 4) { d[i] = d[i + 1] = d[i + 2] = 255; d[i + 3] = Math.round(230 * .07 * (Math.random() + Math.random() + Math.random()) / 3); }
  tc.putImageData(img, 0, 0); ctx.fillStyle = ctx.createPattern(tile, 'repeat'); ctx.fillRect(0, 0, grain.width, grain.height);
}
function _v3FxResize() {
  _V3_FX.w = innerWidth; _V3_FX.h = innerHeight;
  const cv = _V3_FX.glow, low = _V3_FX.low; if (!cv || !low) return;
  const w = Math.max(1, Math.ceil(innerWidth)), h = Math.max(1, Math.ceil(innerHeight));
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
  low.width = Math.max(1, Math.ceil(w / _V3_FX_SCALE)); low.height = Math.max(1, Math.ceil(h / _V3_FX_SCALE));
  _V3_FX.colorsAt = 0; _V3_FX.washKey = null; _v3FxColors();   // акварель читается заново и рисуется под новый размер
  if (_V3_FX.grain) _v3FxPaintGrain();
  _v3FxRun();
}
function _v3BuildFx(level) {
  document.querySelector('.v3-fx')?.remove(); clearTimeout(_V3_FX.timer);
  _V3_FX.glow = _V3_FX.low = _V3_FX.wash = _V3_FX.grain = null; _V3_FX.washList = null; document.body.classList.remove('v3-fx-wash');
  if (level < 3) return;
  const layer = document.createElement('div'); layer.className = 'v3-fx'; layer.setAttribute('aria-hidden', 'true');
  _V3_FX.glow = Object.assign(document.createElement('canvas'), { className: 'v3-fx-glow' }); layer.appendChild(_V3_FX.glow);
  _V3_FX.low = document.createElement('canvas'); _V3_FX.wash = document.createElement('canvas');
  if (level >= 4) _V3_FX.grain = document.createElement('canvas');
  document.body.appendChild(layer); _v3FxResize();
}
window.addEventListener('resize', () => { clearTimeout(_V3_FX.size); _V3_FX.size = setTimeout(_v3FxResize, 200); }, { passive: true });
let _v3FxOled = document.body.classList.contains('pv-oled');   // режим OLED меняет --v3-wash: холст узнаёт об этом сразу, а не через полторы секунды
new MutationObserver(() => {
  const oled = document.body.classList.contains('pv-oled'); if (oled === _v3FxOled) return;
  _v3FxOled = oled; _V3_FX.colorsAt = 0; _v3FxRun();
}).observe(document.body, { attributes: true, attributeFilter: ['class'] });
// Наклон телефона и указатель двигают слой SS+. В руке телефон никогда не лежит неподвижно: сырой наклон дрожит, а запись переменной в body пересчитывает стиль всей страницы.
// Поэтому: ноль берётся из первого замера, дрожь меньше мёртвой зоны гасится, движение сглаживается и пишется только в слой эффектов и док (не в body), редко и пока есть что менять.
function _v3BindTilt() {
  if (_v3PointerOn) return; _v3PointerOn = true;
  let frame = 0, goalX = 0, goalY = 0, curX = 0, curY = 0, base = null, lastPush = 0;
  const targets = () => [document.querySelector('.nav')].filter(Boolean);   // свет страницы читает наклон из _V3_FX.tilt, переменные нужны только доку
  const push = now => {
    frame = 0;
    curX += (goalX - curX) * 0.1; curY += (goalY - curY) * 0.1;
    if (now - lastPush >= 66 && (Math.abs(goalX - curX) > 0.004 || Math.abs(goalY - curY) > 0.004)) {   // не чаще 15 раз в секунду
      lastPush = now; _V3_FX.tilt = [curX, curY]; targets().forEach(n => { n.style.setProperty('--tilt-x', curX.toFixed(3)); n.style.setProperty('--tilt-y', curY.toFixed(3)); });
      _v3FxRun();   // свет сдвигается вслед за наклоном сразу, а не на следующем шаге таймера
    }
    if (Math.abs(goalX - curX) > 0.004 || Math.abs(goalY - curY) > 0.004) frame = requestAnimationFrame(push);
  };
  const aim = (x, y) => { if (Math.abs(x - goalX) < 0.06 && Math.abs(y - goalY) < 0.06) return; goalX = x; goalY = y; if (!frame) frame = requestAnimationFrame(push); };
  window.addEventListener('deviceorientation', e => {
    if (_v3FxLevel < 6 || e.gamma == null || document.hidden) return;
    if (!base) base = [e.gamma, e.beta];
    aim(Math.max(-1, Math.min(1, (e.gamma - base[0]) / 40)), Math.max(-1, Math.min(1, (e.beta - base[1]) / 40)));
  }, { passive: true });
  window.addEventListener('pointermove', e => { if (_v3FxLevel < 6 || e.pointerType === 'touch') return; aim(e.clientX / innerWidth * 2 - 1, e.clientY / innerHeight * 2 - 1); }, { passive: true });
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
  body.classList.toggle('ap-lite', _v3Lite()); body.classList.toggle('ap-low', _v3Low()); body.dataset.dev = _v3Class();   // лёгкий режим: частиц вдвое меньше; экономный: образ стоит на месте (fx-tiers-v3.css)
  _v3BuildFx(level); if (level >= 6) _v3BindTilt();
  _v3StartWatchdog(level);
}
// Если устройство не тянет: после показа замеряем кадры. Сначала включается лёгкий режим образов, затем экономный, и только если и после него кадры медленные,
// потолок эффектов снижается на две ступени (запоминается)
function _v3StartWatchdog(level) {
  if (_v3Watchdog || _v3Forced || level < 3) return; _v3Watchdog = true;
  const measure = (done, waited = 0) => setTimeout(() => {
    if (document.hidden) { _v3Watchdog = false; return; }   // вкладка в фоне: замер повторится при следующем показе
    if (document.querySelector('#toast.show, #gift-toast') && waited < 4) { measure(done, waited + 1); return; }   // пока на экране тост: он сам тянет кадры, замер подождёт (до десяти секунд)
    const times = []; let last = performance.now(), count = 0;
    const tick = now => {
      times.push(now - last); last = now;
      if (++count < 90) { requestAnimationFrame(tick); return; }
      const sorted = times.slice(5).sort((a, b) => a - b); done(sorted[Math.floor(sorted.length / 2)]);
    };
    requestAnimationFrame(tick);
  }, 2500);
  const lower = median => {
    if (median <= 30 || _v3FxLevel <= 2) return;
    try { localStorage.setItem(_V3_FX_CAP_KEY, String(Math.max(2, _v3FxLevel - 2))); } catch (_) { /* не сохранится: сработает снова в следующем сеансе */ }
    applySkinTier(_v3Skin);
  };
  // Ступени вниз: полный вид -> лёгкий (.ap-lite) -> экономный (.ap-low) -> ниже потолок эффектов. Каждая ступень включается только если кадры правда медленные.
  const mark = key => { try { localStorage.setItem(key, '1'); } catch (_) { /* не сохранится: сработает снова в следующем сеансе */ } };
  const step = median => {
    if (median <= 26) return;
    if (!_v3Lite()) { mark(_V3_LITE_KEY); applySkinTier(_v3Skin); measure(step); return; }
    if (!_v3Low()) { mark(_V3_LOW_KEY); applySkinTier(_v3Skin); measure(step); return; }
    lower(median);
  };
  measure(step);
}
document.addEventListener('skinchange', e => applySkinTier(e.detail));
document.addEventListener('visibilitychange', () => { document.body.classList.toggle('v3-paused', document.hidden); _v3FxRun(); });
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
// Эффекты вне экрана не рисуются и не считаются: пока образ (сцена, рамка, ореол, частицы, фирменная деталь) или блик ника не виден, на нём класс .ap-off, а в CSS он стоит на паузе
// (fx-tiers-v3.css). Запас 120 px, чтобы движение уже шло, когда блок въезжает в экран. Строки списков не наблюдаются: их блики и так выключены.
const _AP_WATCH = '.ap-stage, .ap-name, .ap-title';
const _apIO = typeof IntersectionObserver === 'function'
  ? new IntersectionObserver(list => list.forEach(e => e.target.classList.toggle('ap-off', !e.isIntersecting)), { rootMargin: '120px 0px' }) : null;
function _apWatch(node) {
  if (!_apIO || node.nodeType !== 1) return;
  if (node.matches(_AP_WATCH)) _apIO.observe(node);
  node.querySelectorAll(_AP_WATCH).forEach(n => { if (!n.closest('.v3-who')) _apIO.observe(n); });
}
if (_apIO) {
  _apWatch(document.body);
  new MutationObserver(list => list.forEach(m => m.addedNodes.forEach(_apWatch))).observe(document.body, { childList: true, subtree: true });
}
applySkinTier({ css_class: '', tier: 'D' });
