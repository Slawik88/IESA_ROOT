// S11: общая палитра Mini App, безопасная тема и листы на телефоне.
const ADMIN_LOOK_TOKEN = /^--(?:v3-[a-z-]{2,16}|acc-rgb)$/;
let adminAppliedTokens = [], adminThemeFallback = false;
const adminOwnTheme = () => PREFS.get('admin.look', 'own') !== 'strict';
function adminNicknameStyle(player) {
  const ap = player.vip && apFromLook(player.look);
  if (!ap) return '';
  const bg = getComputedStyle(document.body).getPropertyValue('--v3-bg').trim();
  const color = ap.look.pal.find(value => adminContrast(value, bg) >= 3.8);
  return color ? `color:${color}` : '';
}
function adminContrast(a, b) {
  const canvas = document.createElement('canvas'), ctx = canvas.getContext('2d');
  const light = color => {
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--v3-bg').trim(); ctx.fillRect(0, 0, 1, 1);
    ctx.fillStyle = color; ctx.fillRect(0, 0, 1, 1);
    const values = [...ctx.getImageData(0, 0, 1, 1).data];
    if (values[3] < 255) return NaN;
    const rgb = values.slice(0, 3).map(x => { x /= 255; return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4; });
    return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
  };
  const x = light(a), y = light(b);
  return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
}
function applyTheme() {
  const style = document.body.style;
  adminAppliedTokens.forEach(key => style.removeProperty(key)); adminAppliedTokens = [];
  adminThemeFallback = false;
  const tokens = adminOwnTheme() && ME && ME.look && ME.look.tokens;
  if (tokens && typeof tokens === 'object') {
    for (const [key, value] of Object.entries(tokens)) {
      if (ADMIN_LOOK_TOKEN.test(key) && typeof value === 'string' && value.length < 400 && !/[;{}<>\\]|url\(|@import|expression/i.test(value)) {
        style.setProperty(key, value); adminAppliedTokens.push(key);
      }
    }
    const css = getComputedStyle(document.body), color = key => css.getPropertyValue(key).trim();
    const pairs = [['--v3-ink', '--v3-bg', 4.5], ['--v3-dim', '--v3-bg', 5.2],
      ['--v3-ink', '--v3-sheet', 4.5], ['--v3-dim', '--v3-sheet', 5.2],
      ['--v3-ink', '--v3-dock', 4.5], ['--v3-on-acc', '--v3-acc', 4.5]];
    if (pairs.some(([a, b, floor]) => !(adminContrast(color(a), color(b)) >= floor))) {
      adminAppliedTokens.forEach(key => style.removeProperty(key)); adminAppliedTokens = []; adminThemeFallback = true;
    }
  }
  document.body.dataset.adminLook = adminOwnTheme() && !adminThemeFallback && tokens ? 'own' : 'strict';
  const bg = getComputedStyle(document.body).getPropertyValue('--v3-bg').trim();
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', bg); paintTmaShell(bg);
}
function themeSheet() {
  const own = adminOwnTheme();
  sheet('Тема админки', `<div class="go-list">
    <button type="button" data-look="own" aria-pressed="${own}">Как у меня<small class="sub">Цвета надетого образа</small></button>
    <button type="button" data-look="strict" aria-pressed="${!own}">Строгая<small class="sub">Базовый Обсидиан</small></button></div>
    <p class="sub">Выбор хранится на этом устройстве. Кнопки наказаний всегда одного цвета.</p>
    <p class="sub" id="look-fallback" ${adminThemeFallback ? '' : 'hidden'}>Для читаемости сейчас включена строгая тема.</p>`, 'Готово', () => {}, {info: true});
  $('#sheet').querySelectorAll('[data-look]').forEach(button => button.onclick = () => {
    PREFS.set('admin.look', button.dataset.look); applyTheme();
    $('#sheet').querySelectorAll('[data-look]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    $('#look-fallback').hidden = !adminThemeFallback;
  });
}
function adminCloseSheet() {
  const box = $('#sheet');
  if (!box || box.hidden) return false;
  box.hidden = true; box.innerHTML = ''; return true;
}
applyTheme();
document.addEventListener('click', event => { if (event.target.closest('[data-admin-theme]')) themeSheet(); });

(function adminMobileSheets() {
  const box = $('#sheet'); let previousFocus = null, panel = null, start = null;
  const viewport = () => {
    const v = window.visualViewport;
    document.body.style.setProperty('--admin-keyboard', `${v ? Math.max(0, innerHeight - v.height - v.offsetTop) : 0}px`);
    document.body.style.setProperty('--admin-visible-height', `${v ? v.height : innerHeight}px`);
  };
  window.visualViewport?.addEventListener('resize', viewport);
  window.visualViewport?.addEventListener('scroll', viewport); window.addEventListener('resize', viewport); viewport();
  new MutationObserver(() => {
    const shown = !box.hidden && !!box.firstElementChild;
    document.body.classList.toggle('sheet-open', shown);
    if (!shown) { panel = null; if (previousFocus?.isConnected) previousFocus.focus({preventScroll: true}); previousFocus = null; return; }
    const next = box.firstElementChild;
    if (next === panel) return;
    panel = next; previousFocus ||= document.activeElement;
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', panel.querySelector('h3')?.textContent || 'Действия');
    const grip = document.createElement('button'); grip.className = 'sheet-grip'; grip.type = 'button';
    grip.setAttribute('aria-label', 'Закрыть окно'); grip.innerHTML = '<i></i>'; grip.onclick = adminCloseSheet; panel.prepend(grip);
    panel.querySelector(':scope > .actions:last-child')?.classList.add('sheet-actions');
    if (!panel.contains(document.activeElement)) (panel.querySelector('input:not([type=checkbox]), textarea, button') || panel).focus({preventScroll: true});
  }).observe(box, {attributes: true, attributeFilter: ['hidden'], childList: true});
  box.addEventListener('pointerdown', event => {
    if (event.target.closest('.sheet-grip, .sheet > h3')) start = {x: event.clientX, y: event.clientY};
  });
  box.addEventListener('pointerup', event => {
    if (start && event.clientY - start.y > 70 && Math.abs(event.clientX - start.x) < 60) adminCloseSheet();
    start = null;
  });
  box.addEventListener('pointercancel', () => { start = null; });
  document.addEventListener('keydown', event => {
    if (box.hidden) return;
    if (event.key === 'Escape') { event.preventDefault(); adminCloseSheet(); }
    if (event.key !== 'Tab') return;
    const nodes = [...box.querySelectorAll('button, input, select, textarea, a[href], [tabindex="0"]')].filter(n => !n.disabled && n.getClientRects().length);
    const first = nodes[0], last = nodes.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  });
  document.addEventListener('focusin', event => {
    if (box.contains(event.target)) setTimeout(() => { if (event.target.isConnected) event.target.scrollIntoView({block: 'nearest'}); }, 100);
  });
  const reserve = () => {
    const host = $('#undobar');
    document.body.style.setProperty('--admin-undo-height', `${host ? host.getBoundingClientRect().height : 0}px`);
  };
  const size = new ResizeObserver(reserve);
  new MutationObserver(() => { const host = $('#undobar'); if (host) size.observe(host); reserve(); }).observe(document.body, {childList: true});
})();
