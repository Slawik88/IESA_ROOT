// ── Движение с назначением ───────────────────────────────────────────────────────
// Анимация здесь сообщает о событии, а не украшает: деньги пришли или ушли, образ сменился, лист закрыт, новый уровень дорисовал звезду.
// Всё одноразовое и только transform/opacity (стили: motion-v3.css). Объём решает класс устройства (_v3Class, app.18.js): слабому телефону
// остаются мгновенные состояния, «Спокойному режиму» и prefers-reduced-motion не достаётся ничего.
const _V3_CHIP_IDS = { mora: 'vb-mora', diamonds: 'vb-dia', essence: 'vb-ess', zarniki: 'vb-zar' };
function _v3Moves() { return typeof _v3Calm === 'function' && !_v3Calm() && typeof _v3Class === 'function' && _v3Class() !== 'low'; }

// Лист закрывается: уезжает вниз на ширину пальца, подложка гаснет. host: подложка листа, done: что сделать после (вернуть фокус)
function v3Dismiss(host, done) {
  if (!host || host.dataset.leaving) return;
  let finished = false;
  const end = () => { if (finished) return; finished = true; host.remove(); if (done) done(); };
  const sheet = host.firstElementChild;
  if (!sheet || !host.animate || !_v3Moves()) { end(); return; }
  host.dataset.leaving = '1'; host.style.pointerEvents = 'none';
  host.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 170, easing: 'ease-out', fill: 'forwards' });
  sheet.animate([{ transform: 'translateY(0)' }, { transform: 'translateY(28px)' }], { duration: 170, easing: 'cubic-bezier(.4, 0, 1, 1)', fill: 'forwards' }).onfinish = end;
  setTimeout(end, 450);   // страховка: вкладка в фоне не присылает onfinish
}

// Баланс изменился: число в чипе пульсирует, под ним на секунду всплывает «+120» или «−300». Не при открытии приложения (кэш и свежие данные
// различаются), а только когда игрок уже в нём и деньги пришли или ушли на его глазах.
function v3BalanceFx(prev, next, since) {
  if (!prev || !next || Date.now() - since < 2500 || document.hidden || !_v3Moves()) return;
  Object.entries(_V3_CHIP_IDS).forEach(([key, id], n) => {
    const was = Number(prev[key]), now = Number(next[key]);
    if (!Number.isFinite(was) || !Number.isFinite(now) || was === now) return;
    const chip = el(id)?.closest('.v3-chip'), box = chip?.getBoundingClientRect(); if (!box || !box.width) return;
    chip.classList.remove('is-tick'); void chip.offsetWidth; chip.classList.add('is-tick');
    const tag = document.createElement('i'), gain = now > was;
    tag.className = `v3-delta ${gain ? 'is-up' : 'is-down'}`; tag.setAttribute('aria-hidden', 'true'); tag.textContent = `${gain ? '+' : '−'}${_v3Short(Math.abs(now - was), 1e3)}`;
    tag.style.cssText = `left:${Math.round(box.left + box.width / 2)}px;top:${Math.round(box.bottom - 6)}px;animation-delay:${n * 80}ms`;
    document.body.appendChild(tag); setTimeout(() => tag.remove(), 1700);
  });
}

// Награда летит туда, где будет лежать: из кнопки (элемент или точка {x, y}) в чип валюты. Пять искр по веерным дугам, и чип пульсирует по прилёту.
function v3Fly(from, currency, glyph = '✦', count = 5) {
  const chip = el(_V3_CHIP_IDS[currency])?.closest('.v3-chip'); if (!chip || !from || !_v3Moves() || !document.body.animate) return;
  const a = from.getBoundingClientRect ? from.getBoundingClientRect() : { left: from.x, top: from.y, width: 0, height: 0 }, b = chip.getBoundingClientRect();
  if (!b.width || (from.getBoundingClientRect && !a.width)) return;
  const x0 = a.left + a.width / 2, y0 = a.top + a.height / 2, x1 = b.left + b.width / 2, y1 = b.top + b.height / 2;
  for (let i = 0; i < count; i++) {
    const spark = document.createElement('i'); spark.className = 'v3-fly'; spark.setAttribute('aria-hidden', 'true'); spark.textContent = glyph; document.body.appendChild(spark);
    const bend = (i - (count - 1) / 2) * 34;
    spark.animate([
      { transform: `translate(${x0}px, ${y0}px) scale(.4)`, opacity: 0 },
      { transform: `translate(${(x0 + x1) / 2 + bend}px, ${Math.min(y0, y1) - 36 + Math.abs(bend) * .35}px) scale(1)`, opacity: 1, offset: .45 },
      { transform: `translate(${x1}px, ${y1}px) scale(.5)`, opacity: .15 },
    ], { duration: 760, delay: i * 70, easing: 'cubic-bezier(.3, .1, .2, 1)', fill: 'both' }).onfinish = () => spark.remove();
  }
  setTimeout(() => { chip.classList.remove('is-tick'); void chip.offsetWidth; chip.classList.add('is-tick'); }, 760 + (count - 1) * 70);
}

// Смена образа: палитра приложения перетекает, а не щёлкает. Только там, где устройство тянет снимок страницы (потолок 5 и выше).
function v3Morph(update) {
  if (typeof document.startViewTransition !== 'function' || !_v3Moves() || _v3DeviceCap() < 5) { update(); return; }
  try { document.startViewTransition(update); } catch (_) { update(); }
}

// Квест выполнен на глазах у игрока: значок задания подпрыгивает один раз. Квесты, которые уже были выполнены при открытии вкладки, не трогаются.
const _questDone = { seen: new Set(), ready: new Set() };
function v3QuestsDone(root) {
  const cards = [...root.querySelectorAll('.quest-card[data-q]')];
  cards.forEach(card => {
    const id = card.dataset.q, period = id.split('-')[0];
    if (card.classList.contains('is-done')) {
      if (_questDone.ready.has(period) && !_questDone.seen.has(id) && _v3Moves()) card.classList.add('is-fresh');
      _questDone.seen.add(id);
    }
  });
  cards.forEach(card => _questDone.ready.add(card.dataset.q.split('-')[0]));   // первая отрисовка периода тихая
}

// Кольцо опыта в шапке профиля: рисуется от того, что игрок видел в прошлый раз, до нового значения (при первом запуске с нуля)
function v3RingIn(root, prevAll, seen) {
  const ring = root.querySelector('.v3-id .v3-ring > svg circle:last-child'); if (!ring || !_v3Moves()) return;
  const target = Number(ring.getAttribute('stroke-dashoffset')); if (!Number.isFinite(target)) return;
  const percent = 100 * (1 - target / 220), from = Number(prevAll.ring_xp);
  seen.ring_xp = percent;
  const start = 220 * (1 - (Number.isFinite(from) ? from : 0) / 100);
  if (Math.abs(start - target) < 2) return;
  ring.style.strokeDashoffset = start; void ring.getBoundingClientRect();
  ring.style.transition = 'stroke-dashoffset .9s cubic-bezier(.22, 1, .36, 1)'; ring.style.strokeDashoffset = target;
}
