// Ритм Лиги — только вид: сцена уровня (сердца SVG, очки, комбо, круговой таймер окна, руны), отсчёт, веер даров, отклики.
// Правила и счёт — класс Engine в league-rhythm.js (паритет с сервером); этот файл ничего не считает, а только показывает.
(() => {
  const L = () => window.League, A = () => window.LeagueArt, Fx = () => window.LeagueFx;
  const $ = id => document.getElementById(id);
  const C = 2 * Math.PI * 54;   // длина дуги таймера (r = 54)
  let arc = null, shownHearts = null;

  // restart — функция, которая делает кнопку «Заново» (game-shell-v3.js): она стоит в верхнем углу сцены, подальше от рун
  function stage(run, glyphs, onRune, restart = null) {
    if ($('lgr-stage')) return false;
    L().show(`<div id="lgr-stage" class="lgr-stage" data-mode="count"><i class="lgr-tempo" id="lgr-tempo" aria-hidden="true"></i>
      <div class="lg-bar"><span class="lg-bar-t">Ритм · уровень ${run.level}</span><span id="lgr-restart"></span></div>
      <div class="lgr-hud"><span class="lgr-hearts" id="lgr-hearts" role="img"></span>
        <span class="lgr-score"><b id="lgr-score">0</b><small>очки</small></span><span class="lgr-sig"><b id="lgr-sig"></b><small>нажатий</small></span></div>
      <div class="lgr-progress" id="lgr-progress" role="progressbar" aria-label="Пройдено нажатий уровня" aria-valuemin="0" aria-valuemax="${run.signals}" aria-valuenow="0"><i id="lgr-progress-fill"></i></div><small class="lgr-remaining" id="lgr-remaining"></small>
      <div class="lgr-owned" id="lgr-owned" aria-label="Взятые дары"></div>
      <div class="lgr-arena" id="lgr-arena">
        <svg class="lgr-timer" viewBox="0 0 120 120" aria-hidden="true"><circle class="lgr-timer-bg" r="54" cx="60" cy="60"/><circle class="lgr-timer-arc" id="lgr-arc" r="54" cx="60" cy="60" stroke-dasharray="${C.toFixed(2)}" stroke-dashoffset="0"/></svg>
        <div class="lgr-target" id="lgr-target"></div><i class="lgr-flash" id="lgr-flash" aria-hidden="true"></i>
        <span class="lgr-combo" id="lgr-combo" aria-hidden="true"></span><span class="lgr-judge" id="lgr-judge" aria-live="polite"></span></div>
      <div class="lgr-draft" id="lgr-draft"></div>
      <div class="lg-runes" role="group" aria-label="Руны">${Object.entries(glyphs).map(([r, g]) => `<button type="button" data-rune="${r}" aria-label="Руна ${g}">${A().icon('frame', 'lgr-rune-frame')}<b>${g}</b></button>`).join('')}</div></div>`, 1);
    document.querySelectorAll('[data-rune]').forEach(b => b.addEventListener('pointerdown', e => { e.preventDefault(); onRune(b.dataset.rune); }));
    if (restart) $('lgr-restart').append(restart());
    shownHearts = null;
    return true;
  }

  const mode = m => { const s = $('lgr-stage'); if (s) s.dataset.mode = m; };

  // Сердца: потерянное «трескается» (половинки разлетаются), вылеченное наполняется
  function hearts(health, base) {
    const host = $('lgr-hearts'); if (!host) return;
    if (shownHearts === health && host.children.length) return;   // не перерисовывать посреди «трещины»
    const was = shownHearts ?? health;
    shownHearts = health;
    host.setAttribute('aria-label', `Сердец: ${Math.max(0, health)}`);
    const slots = Math.max(base, health, was);   // начальные сердца; вылеченные сверх них добавляют место
    host.innerHTML = Array.from({length: slots}, (_, i) => A().heart(i < Math.max(health, was) ? 'full' : 'empty')).join('');
    const nodes = host.children;
    for (let i = Math.max(0, health); i < was; i++) {
      const h = nodes[i], l = h.querySelector('.lga-hl'), r = h.querySelector('.lga-hr');
      const swap = () => { if (h.isConnected) h.outerHTML = A().heart('empty'); };
      if (!Fx().moves()) { swap(); continue; }
      Fx().play(l, [{transform: 'none'}, {transform: 'translate(-3px, 4px) rotate(-24deg)', opacity: 0}], {duration: 420, fill: 'forwards'});
      Fx().play(r, [{transform: 'none'}, {transform: 'translate(3px, 4px) rotate(24deg)', opacity: 0}], {duration: 420, fill: 'forwards'}).then(swap);
    }
    for (let i = Math.max(0, was); i < health; i++) Fx().play(nodes[i], [{transform: 'scale(.3)', opacity: 0}, {transform: 'scale(1.25)', opacity: 1, offset: .6}, {transform: 'none'}], {duration: 380});
  }

  function hud(engine, run) {
    const s = engine.s;
    hearts(s.health, run.hearts);
    const score = $('lgr-score'); if (score) score.textContent = s.score;
    const done = Math.min(run.signals, Math.max(0, s.signal - 1));
    const sig = $('lgr-sig'); if (sig) sig.textContent = `${done}/${run.signals}`;
    const progress = $('lgr-progress'); if (progress) progress.setAttribute('aria-valuenow', done);
    const fill = $('lgr-progress-fill'); if (fill) fill.style.transform = `scaleX(${done / run.signals})`;
    const remaining = $('lgr-remaining'); if (remaining) remaining.textContent = done === run.signals ? 'Уровень пройден' : `До конца уровня: ${run.signals - done} нажатий`;
    const tempo = $('lgr-tempo'); if (tempo) tempo.style.opacity = String(Math.min(1, (engine.pace() - 100) / 80));
    const owned = $('lgr-owned');
    if (owned) owned.innerHTML = Object.entries(s.perks.owned).map(([id, n]) => `<span class="lgr-chip is-${engine.cat[id].kind}">${L().esc(engine.cat[id].name)}${n > 1 ? ` ×${n}` : ''}</span>`).join('');
  }

  // Руна читается сразу: появление 90 мс (scale .92→1, прозрачность от 0,35) — меньше 120 мс; shownAt ставит игра, анимация его не сдвигает
  function rune(glyph) {
    mode('play');
    const t = $('lgr-target'); if (!t) return;
    t.className = 'lgr-target'; t.textContent = glyph; t.setAttribute('aria-label', `Нажми руну ${glyph}`);
    $('lgr-judge').textContent = '';
    Fx().play(t, [{transform: 'scale(.92)', opacity: .35}, {transform: 'none', opacity: 1}], {duration: 90, easing: 'ease-out'});
  }

  // Таймер окна — одна дуга (stroke-dashoffset, как кольцо опыта в MOTION_V3). Это часть правил, а не украшение: идёт при любом бюджете.
  function timer(ms) {
    const el = $('lgr-arc'); if (!el) return;
    arc?.cancel();
    arc = el.animate ? el.animate([{strokeDashoffset: 0}, {strokeDashoffset: C}], {duration: ms, easing: 'linear', fill: 'forwards'}) : null;
  }
  const freeze = () => { arc?.pause(); };

  // Отклик на нажатие: верно — кольцо и «+очки», быстрое — «Идеально», ошибка — красная вспышка; комбо растёт ×N
  function feedback({ok, perfect, gained, combo}) {
    freeze();
    const arena = $('lgr-arena'), t = $('lgr-target'), judge = $('lgr-judge'), cmb = $('lgr-combo');
    if (!arena) return;
    judge.textContent = ok ? (perfect ? 'Идеально' : 'Верно') : 'Мимо';
    judge.className = 'lgr-judge ' + (ok ? (perfect ? 'is-perfect' : 'is-ok') : 'is-miss');
    if (ok) {
      Fx().ring(arena, perfect ? 'is-gold' : '');
      Fx().float(arena, `+${gained}`, perfect ? 'is-gold' : '');
      Fx().play(t, [{transform: 'scale(1.12)'}, {transform: 'none'}], {duration: 200});
    } else {
      t.classList.add('is-miss');
      Fx().play($('lgr-flash'), [{opacity: 0}, {opacity: .85, offset: .3}, {opacity: 0}], {duration: 280});
      Fx().shake(t);
    }
    cmb.textContent = combo >= 2 ? `×${combo}` : '';
    cmb.classList.toggle('is-hot', combo >= 10);
    if (combo >= 2) Fx().bump(cmb, combo >= 10 ? 1.35 : 1.2);
  }

  // Отсчёт 3-2-1: крупная цифра с ударом
  function count(n) {
    mode('count');
    const t = $('lgr-target'); if (!t) return;
    arc?.cancel(); arc = null;
    t.className = 'lgr-target is-count'; t.textContent = n || ''; t.setAttribute('aria-label', n ? `Старт через ${n}` : 'Старт');
    $('lgr-judge').textContent = ''; $('lgr-combo').textContent = '';
    if (n) Fx().play(t, [{transform: 'scale(1.6)', opacity: 0}, {transform: 'scale(.94)', opacity: 1, offset: .55}, {transform: 'none', opacity: 1}], {duration: 360});
  }

  // Веер из трёх даров: рамка по виду (надёжный, усиление, риск); выбранный увеличивается и улетает в ряд даров
  function draft(engine, offers, onPick) {
    mode('draft');
    const host = $('lgr-draft'); if (!host) return;
    const KIND = {safe: 'надёжный', boost: 'усиление', risk: 'риск'};
    host.innerHTML = `<p class="lg-rules">Дар уровня — одинаковый у всех игроков. Можно пропустить.</p><div class="lgr-fan">${offers.map((id, i) => {
      const g = engine.cat[id], ok = engine.allowed(id);
      return `<button type="button" class="lgr-card is-${g.kind}" data-gift="${id}" style="--i:${i - 1}" ${ok ? '' : 'disabled'}><small>${KIND[g.kind] || ''}</small><b>${L().esc(g.name)}</b>
        <span class="g-plus">＋ ${L().esc(g.bonus)}</span><span class="g-minus">− ${L().esc(g.cost)}</span>${ok ? '' : '<em>сейчас нельзя</em>'}</button>`;
    }).join('')}</div><button type="button" class="lg-link" data-gift="">Пропустить дар</button>`;
    const cards = [...host.querySelectorAll('.lgr-card')];
    cards.forEach((c, i) => Fx().play(c, [{transform: `translateY(48px) rotate(${(i - 1) * 9}deg)`, opacity: 0}, {transform: 'none', opacity: 1}], {duration: 320, delay: i * 80}));
    let picked = false;
    host.querySelectorAll('[data-gift]').forEach(b => { b.onclick = async () => {
      if (picked) return; picked = true;
      const id = b.dataset.gift || null;
      if (id && Fx().moves()) {
        await Fx().play(b, [{transform: 'none'}, {transform: 'scale(1.08)'}], {duration: 160, fill: 'forwards'});
        await Fx().fly(b, $('lgr-owned'), `<span class="lgr-chip is-${engine.cat[id].kind}">${L().esc(engine.cat[id].name)}</span>`);
      }
      host.innerHTML = '';
      onPick(id);
    }; });
  }

  window.LeagueRhythmView = {stage, hud, rune, timer, freeze, feedback, count, draft, mode};
})();
