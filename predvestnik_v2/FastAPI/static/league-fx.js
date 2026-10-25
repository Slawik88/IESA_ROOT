// Движение Лиги (docs/MOTION_V3.md): анимация сообщает о событии. Только transform/opacity, всё одноразовое.
// Бюджет как в приложении: слабый телефон (low), «Спокойный режим» (body.no-fx) и prefers-reduced-motion получают мгновенные состояния,
// смысл (звёзды, «+очки», полученное) всегда виден текстом. Лист и тост работают и без движения.
(() => {
  try { if (localStorage.getItem('pv_no_fx') === '1') document.body.classList.add('no-fx'); } catch (_) { /* без памяти: режим по умолчанию */ }
  // Класс устройства — как _v3HardwareCap/_v3Class в app.18.js: сама страница Лиги приложение не грузит
  function tier() {
    try {
      const nav = navigator, mem = nav.deviceMemory, cores = nav.hardwareConcurrency;
      if (nav.connection?.saveData || (mem && mem <= 2) || (cores && cores <= 3)) return 'low';
      if ((mem && mem <= 4) || (!mem && cores && cores <= 4)) return 'mid';
    } catch (_) { /* свойств нет: полный класс */ }
    return 'high';
  }
  const TIER = tier();
  const calm = () => document.body.classList.contains('no-fx') || !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const moves = () => TIER !== 'low' && !calm() && !document.hidden && typeof document.body.animate === 'function';
  document.body.classList.add('lg-' + TIER);
  const EASE = 'cubic-bezier(.22,1,.36,1)';

  // Одна анимация через Web Animations; без движения сразу конечное состояние. Возвращает промис окончания.
  function play(el, frames, opts = {}) {
    if (!el || !moves()) return Promise.resolve();
    const a = el.animate(frames, {duration: 220, easing: EASE, fill: 'backwards', ...opts});
    return new Promise(done => { a.onfinish = a.oncancel = done; setTimeout(done, (opts.duration || 220) + (opts.delay || 0) + 400); });
  }

  // Новый экран приходит со стороны, куда ушёл игрок: dir = 1 вперёд (справа), -1 назад (слева), 0 — снизу
  const enter = (el, dir = 1) => play(el, [{transform: dir ? `translateX(${dir * 14}px)` : 'translateY(10px)', opacity: 0}, {transform: 'none', opacity: 1}], {duration: 200});

  // Числа набегают от прошлого значения; tabular-nums в стилях держит ширину
  const seen = {};
  function count(root) {
    root.querySelectorAll('[data-count]').forEach(el => {
      const key = el.dataset.count, to = Number(el.textContent.replace(/\s/g, '')), from = seen[key] ?? 0;
      seen[key] = to;
      if (!Number.isFinite(to) || from === to || !moves()) return;
      const t0 = performance.now(), ms = Math.min(900, 300 + Math.abs(to - from) * 8);
      const step = now => {
        const k = Math.min(1, (now - t0) / ms), e = 1 - (1 - k) ** 3;
        el.textContent = String(Math.round(from + (to - from) * e));
        if (k < 1 && el.isConnected) requestAnimationFrame(step); else el.textContent = String(to);
      };
      el.textContent = String(from);
      requestAnimationFrame(step);
    });
  }

  // Всплывающая надпись над точкой («+120», «Идеально!»): поднимается и гаснет
  function float(host, text, cls = '') {
    if (!host || !moves()) return;
    const tag = document.createElement('i');
    tag.className = 'lg-float ' + cls; tag.setAttribute('aria-hidden', 'true'); tag.textContent = text;
    host.appendChild(tag);
    play(tag, [{transform: 'translate(-50%, 6px) scale(.8)', opacity: 0}, {transform: 'translate(-50%, -8px) scale(1.05)', opacity: 1, offset: .25},
      {transform: 'translate(-50%, -34px) scale(1)', opacity: 0}], {duration: 700, fill: 'forwards'}).then(() => tag.remove());
  }

  // Кольцо-всплеск из центра элемента
  function ring(host, cls = '') {
    if (!host || !moves()) return;
    const r = document.createElement('i');
    r.className = 'lg-ring ' + cls; r.setAttribute('aria-hidden', 'true'); host.appendChild(r);
    play(r, [{transform: 'translate(-50%,-50%) scale(.5)', opacity: .9}, {transform: 'translate(-50%,-50%) scale(1.7)', opacity: 0}], {duration: 460, fill: 'forwards'}).then(() => r.remove());
  }

  const shake = el => play(el, [{transform: 'none'}, {transform: 'translateX(-6px)'}, {transform: 'translateX(5px)'}, {transform: 'translateX(-3px)'}, {transform: 'none'}], {duration: 250, easing: 'ease-out'});
  const bump = (el, k = 1.18) => play(el, [{transform: `scale(${k})`}, {transform: 'scale(1)'}], {duration: 260});

  // Награда летит по дуге из одного элемента в другой (как v3Fly), html — что летит
  function fly(from, to, html, delay = 0) {
    if (!from || !to || !moves()) return Promise.resolve();
    const a = from.getBoundingClientRect(), b = to.getBoundingClientRect();
    if (!a.width || !b.width) return Promise.resolve();
    const x0 = a.left + a.width / 2, y0 = a.top + a.height / 2, x1 = b.left + b.width / 2, y1 = b.top + b.height / 2;
    const node = document.createElement('i');
    node.className = 'lg-fly'; node.setAttribute('aria-hidden', 'true'); node.innerHTML = html;
    document.body.appendChild(node);
    const bend = (x0 < x1 ? -1 : 1) * 30;
    return play(node, [
      {transform: `translate(${x0}px, ${y0}px) scale(.6)`, opacity: 0},
      {transform: `translate(${(x0 + x1) / 2 + bend}px, ${Math.min(y0, y1) - 48}px) scale(1.15)`, opacity: 1, offset: .45},
      {transform: `translate(${x1}px, ${y1}px) scale(.55)`, opacity: .2},
    ], {duration: 640, delay, easing: 'cubic-bezier(.3,.1,.2,1)', fill: 'both'}).then(() => node.remove());
  }

  // Лист снизу (без alert/confirm): заголовок, содержимое, кнопки [{l, f, ghost, arm}]. Esc и подложка закрывают, фокус возвращается.
  // onDismiss — лист закрыт без выбора (Esc, подложка): так игра, вставшая на паузу ради вопроса, узнаёт, что можно продолжать.
  // arm — кнопка включается через столько мс после показа: двойной тап по «Заново» не должен пролететь через лист насквозь.
  function sheet(title, html, buttons = [{l: 'Закрыть'}], onDismiss = null) {
    const back = document.activeElement, host = document.createElement('div');
    host.className = 'lg-sheet-bg';
    host.innerHTML = `<div class="lg-sheet" role="dialog" aria-modal="true" aria-labelledby="lg-sheet-t"><i class="lg-sheet-grip" aria-hidden="true"></i>
      <h2 id="lg-sheet-t">${title}</h2><div class="lg-sheet-body">${html}</div>
      <div class="lg-sheet-btns">${buttons.map((b, i) => `<button type="button" class="${b.ghost ? 'secondary' : ''}" data-i="${i}">${b.l}</button>`).join('')}</div></div>`;
    document.body.appendChild(host);
    let closed = false, chosen = false;
    const close = () => {
      if (closed) return; closed = true;
      document.removeEventListener('keydown', key);
      if (!chosen) onDismiss?.();
      const end = () => { host.remove(); back?.focus?.(); };
      if (!moves()) return end();
      play(host, [{opacity: 1}, {opacity: 0}], {duration: 170, fill: 'forwards'});
      play(host.firstElementChild, [{transform: 'none'}, {transform: 'translateY(28px)'}], {duration: 170, fill: 'forwards'}).then(end);
    };
    const key = e => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', key);
    host.addEventListener('click', e => { if (e.target === host) close(); });
    host.querySelectorAll('[data-i]').forEach(b => {
      const spec = buttons[Number(b.dataset.i)];
      if (spec.arm) { b.disabled = true; setTimeout(() => { b.disabled = false; }, spec.arm); }
      b.onclick = () => { chosen = true; close(); spec.f?.(); };
    });
    play(host, [{opacity: 0}, {opacity: 1}], {duration: 180});
    play(host.firstElementChild, [{transform: 'translateY(40px)', opacity: 0}, {transform: 'none', opacity: 1}], {duration: 260});
    host.querySelector('[data-i]')?.focus();
    return {host, close};
  }

  // Короткий тост сверху: aria-live, сам исчезает
  function toast(html, cls = '') {
    const t = document.createElement('div');
    t.className = 'lg-toast ' + cls; t.setAttribute('role', 'status'); t.innerHTML = html;
    document.body.appendChild(t);
    play(t, [{transform: 'translate(-50%, -16px) scale(.96)', opacity: 0}, {transform: 'translate(-50%, 0)', opacity: 1}], {duration: 260});
    setTimeout(() => play(t, [{opacity: 1}, {opacity: 0}], {duration: 220, fill: 'forwards'}).then(() => t.remove()), 2600);
  }

  window.LeagueFx = {TIER, moves, calm, play, enter, count, float, ring, shake, bump, fly, sheet, toast, EASE};
})();
