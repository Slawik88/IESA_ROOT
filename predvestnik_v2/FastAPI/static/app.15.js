// ── Shell V3: профиль-главная, плашка разработки, общие SVG-иконки ─────────────
// Разметка использует только классы из shell-v3.css; цвета приходят из скина.
const _V3_PATHS = {
  hanger: '<path d="M12 8a2.4 2.4 0 1 0-2.4-2.4M12 8v2l8 5.2c.8.5.4 1.8-.6 1.8H4.6c-1 0-1.4-1.3-.6-1.8L12 10"/>',
  paw: '<circle cx="6.5" cy="11" r="1.7"/><circle cx="10" cy="6.5" r="1.7"/><circle cx="14" cy="6.5" r="1.7"/><circle cx="17.5" cy="11" r="1.7"/><path d="M12 12.5c-3 0-5 2.7-4 4.6.8 1.5 2.4 1.2 4 1.2s3.2.3 4-1.2c1-1.9-1-4.6-4-4.6z"/>',
  flag: '<path d="M6 21V4M6 5h11l-2.5 3.5L17 12H6"/>',
  chest: '<path d="M4 10h16v9H4zM4 10a8 5 0 0 1 16 0M12 13v3"/>',
  trophy: '<path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H5v1a3 3 0 0 0 3 3M16 6h3v1a3 3 0 0 1-3 3M12 13v4M9 20h6"/>',
  chat: '<path d="M5 18l-2 3v-5.5A8 8 0 1 1 6 19z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8"/>',
  chart: '<path d="M4 17l5-5 3.5 3.5L20 7M15 7h5v5"/>',
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.8 9.2a2.4 2.4 0 1 1 3.3 2.2c-.8.4-1.1.9-1.1 1.8M12 17h.01"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14-4.5L4 9M4 4v5h5M4 13a8 8 0 0 0 14 4.5L20 15M20 20v-5h-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  play: '<path d="M8 5.5v13l10.5-6.5z"/>',
  chev: '<path d="M9 6l6 6-6 6"/>',
  manage: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6"/>'
};
function _v3Icon(name) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${_V3_PATHS[name] || ''}</svg>`;
}
function _v3Row(icon, label, action, hint) {
  return `<button type="button" class="v3-row" onclick="${action}">${_v3Icon(icon)}<span>${label}${hint ? `<small>${hint}</small>` : ''}</span><span class="v3-end">${_v3Icon('chev')}</span></button>`;
}
// Кольцо прогресса вокруг аватара: длина окружности r=35 ≈ 220
function _v3Ring(percent) {
  const offset = Math.round(220 * (1 - Math.min(100, Math.max(0, percent)) / 100));
  return `<svg viewBox="0 0 76 76" aria-hidden="true"><circle cx="38" cy="38" r="35" stroke="var(--v3-faint)"/><circle cx="38" cy="38" r="35" stroke="var(--v3-acc)" stroke-dasharray="220" stroke-dashoffset="${offset}"/></svg>`;
}
function _v3Avatar(d) {
  const img = typeof d.avatar === 'string' && /^data:image\/(?:png|jpe?g|webp);base64,/i.test(d.avatar)
    ? `<img src="${_profileEsc(d.avatar)}" alt="" decoding="async">` : null;
  const initial = String(d.display_name || d.username || 'И').replace(/^@+/, '').trim().charAt(0).toUpperCase() || 'И';
  return img || (d.is_vip ? (d.vip?.badge || '✦') : _profileEsc(initial));
}
function renderProfileHome(data) {
  const d = data || {};
  const wallet = (d.balances && typeof d.balances === 'object') ? d.balances : d;
  const level = Math.max(1, Number(d.account_level) || 1);
  const xp = Math.max(0, Number(d.xp_into) || 0);
  const xpNeed = Math.max(1, Number(d.xp_to_next) || Number(d.xp_per_level) || 1);
  const left = Math.max(0, xpNeed - xp);
  const publicName = String(d.display_name || '').trim();
  const rawName = publicName || String(d.username || 'Игрок').replace(/^@*/, '@');
  const title = typeof d.cosmetics?.title === 'object' ? (d.cosmetics.title.text || d.cosmetics.title.name) : d.cosmetics?.title;
  const chests = (typeof _sysFlags !== 'undefined' && _sysFlags.content_chests_v1)
    ? _v3Row('chest', 'Сундуки', 'openChestsV1()') : '';
  return `<section class="v3-id" aria-label="Профиль игрока">
      <div class="v3-ring">${_v3Ring(xp / xpNeed * 100)}<div class="v3-ava" id="pro-showcase-ava">${_v3Avatar(d)}</div><span class="v3-lv" aria-label="Уровень ${level}">${level}</span></div>
      <div style="min-width:0"><div class="v3-name">${_profileEsc(vipName(rawName, d.is_vip, d.vip?.badge || '✦', d.vip?.badge_position || 'left'))}</div>
      <div class="v3-sub">${_profileEsc([d.rank, title].filter(Boolean).join(' · ') || 'Игрок')}</div>
      <div class="v3-sub" style="margin-top:2px">${fmt(left)} XP до ${level + 1} уровня</div></div>
    </section>
    <section class="v3-bal" aria-label="Баланс"><div class="v3-eyebrow">Мора</div><div class="v3-num">${fmt(wallet.mora || 0)}</div>
      <div class="v3-acts"><button type="button" class="v3-pill" onclick="openZarnikiTopup()" aria-label="Пополнить Зарники. Баланс ${fmt(wallet.zarniki || 0)}">${_v3Icon('plus')}Зарники ${fmt(wallet.zarniki || 0)}</button>
      <button type="button" class="v3-link" onclick="showCurrModal()">Кошелёк</button></div></section>
    <section class="v3-stats" aria-label="Достижения игрока"><div><b>${fmt(d.streak || 0)}</b><span>дней подряд</span></div><div><b>${fmt(d.achievements || 0)}</b><span>достижений</span></div></section>
    <nav class="v3-list" aria-label="Разделы профиля">
      ${_v3Row('hanger', 'Примерочная', 'openLooksModal()', 'Рамки, титулы, образы')}
      ${_v3Row('paw', 'Питомцы', 'openPetsV1()')}
      ${_v3Row('flag', 'Квесты', 'openQuestsV1()')}
      ${chests}
      ${_v3Row('trophy', 'Достижения', 'openAchievementsV1()')}
    </nav>`;
}

// Плашка разработки закрывается на сессию; текст остаётся в разметке для публичного контракта.
function dismissDevNotice() {
  const note = el('dev-notice'); if (note) note.hidden = true;
  try { sessionStorage.setItem('v3_dev_notice_closed', '1'); } catch (_) { /* приватный режим: просто скрыто до перезагрузки */ }
}
(function restoreDevNotice() {
  try { if (sessionStorage.getItem('v3_dev_notice_closed') === '1') { const note = el('dev-notice'); if (note) note.hidden = true; } } catch (_) { /* хранилище недоступно */ }
})();

// ── Telegram Mini App: haptics, цвета оболочки, жесты ──────────────────────────
// До этого _haptic() нигде не был объявлен: проверки typeof в app.01.js молча ничего не делали.
function _haptic(kind) {
  const h = tg?.HapticFeedback; if (!h) return;
  try {
    if (kind === 'success' || kind === 'warning' || kind === 'error') h.notificationOccurred(kind);
    else if (kind === 'select') h.selectionChanged();
    else h.impactOccurred(kind || 'light');
  } catch (err) { console.error('haptic', err); }
}
// Один делегированный слушатель на все элементы нового каркаса
document.addEventListener('click', e => {
  const t = e.target.closest('.nb, .v3-pill, .v3-row, .v3-game, .v3-link, .v3-more > summary');
  if (!t || t.disabled) return;
  _haptic(t.classList.contains('nb') ? 'select' : t.classList.contains('v3-pill') ? 'medium' : 'light');
}, true);

// Шапка, фон и нижняя панель Telegram берут цвет скина: никаких чужих полос по краям
(function initTmaShell() {
  if (!tg) return;
  try { if (tg.disableVerticalSwipes) tg.disableVerticalSwipes(); } catch (err) { console.error('swipes', err); }
  const syncChrome = () => {
    const bg = getComputedStyle(document.body).getPropertyValue('--v3-bg').trim();
    if (!bg) return;
    try { tg.setHeaderColor?.(bg); tg.setBackgroundColor?.(bg); tg.setBottomBarColor?.(bg); } catch (err) { console.error('chrome', err); }
  };
  syncChrome();
  new MutationObserver(syncChrome).observe(document.body, { attributes: true, attributeFilter: ['class'] });
})();

// Момент награды: тактильный отклик + россыпь частиц из центра (или из переданного элемента)
function v3Reward(anchor) {
  _haptic('success');
  if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const r = anchor?.getBoundingClientRect?.();
  const x = r ? r.left + r.width / 2 : innerWidth / 2, y = r ? r.top + r.height / 2 : innerHeight * 0.4;
  for (let i = 0; i < 14; i++) {
    const p = document.createElement('i'); p.className = 'v3-burst'; document.body.appendChild(p);
    const a = (Math.PI * 2 * i) / 14 + Math.random() * 0.4, d = 70 + Math.random() * 70;
    const run = p.animate([
      { transform: `translate(${x}px,${y}px) scale(1)`, opacity: 1 },
      { transform: `translate(${x + Math.cos(a) * d}px,${y + Math.sin(a) * d}px) scale(.2)`, opacity: 0 }
    ], { duration: 650 + Math.random() * 250, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'forwards' });
    run.onfinish = () => p.remove();
  }
}
