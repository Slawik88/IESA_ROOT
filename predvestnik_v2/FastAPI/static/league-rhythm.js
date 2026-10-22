// Ритм Лиги: уровень играется на телефоне без сети (никаких фризов), журнал уходит на сервер в паузе после уровня.
// Движок повторяет серверные правила (services/league_rhythm.py, core/league_v1.py); итог и звёзды всё равно считает сервер.
(() => {
  const L = () => window.League;
  const GLYPH = {left: 'ᚠ', center: 'ᚱ', right: 'ᚦ'};
  const GAP_MS = 350, COUNTDOWN = 3;
  const floor = Math.floor;

  class Engine {
    constructor(packet) {
      this.p = packet;
      this.cat = Object.fromEntries(packet.catalog.map(g => [g.id, g]));
      this.s = {health: packet.hearts, perks: {owned: {}, shield: 0, ebb: 0, bloody: 0, miss_debt: 0, recovery: 0},
        score: 0, combo: 0, streak: 0, signal: 1, selected: [], journal: []};
    }
    total(field, p = this.s.perks) { return Object.entries(p.owned).reduce((n, [id, c]) => n + (this.cat[id][field] || 0) * c, 0); }
    any(field, p = this.s.perks) { return Object.keys(p.owned).some(id => this.cat[id][field]); }
    pace(p = this.s.perks) {
      const c = BigInt(floor((this.s.signal - 1) / this.p.chunk)), g = BigInt(100 + this.p.growth_pct);
      return Math.max(100, Number(100n * g ** c / 100n ** c) + this.total('pace_pct', p));
    }
    window(p = this.s.perks) {
      const raw = floor(this.p.base_window_ms * 100 / this.pace(p));
      const pct = Math.max(-45, this.total('window_pct', p) + (p.ebb > 0 ? 40 : 0) + (p.recovery > 0 ? 25 : 0));
      return Math.max(this.p.floor_ms, floor(raw * (100 + pct) / 100));
    }
    score(elapsed) {
      const s = this.s, p = s.perks, w = this.window(), tier = elapsed * 3 <= w ? 0 : elapsed * 3 <= 2 * w ? 1 : 2;
      let timing = [100, 70, 45][tier];
      if (this.any('sharp_eye')) timing = tier === 0 ? floor(timing * 3 / 2) : tier === 2 ? floor(timing / 2) : timing;
      const raw = (timing + Math.min(80 + this.total('combo_cap'), s.combo * (4 + this.total('combo_step')))) * (p.bloody > 0 ? 3 : 1);
      let bonus = 0;
      for (const [id, c] of Object.entries(p.owned)) { const g = this.cat[id]; if (g.cadence_every && (s.combo + 1) % g.cadence_every === 0) bonus += c * g.cadence_bonus_pct; }
      if (s.health <= 2) bonus += this.total('low_health_bonus_pct');
      return Math.max(1, floor(raw * (100 + Math.min(this.p.max_bonus_pct, Math.max(-60, this.total('score_pct') + bonus))) / 100));
    }
    allowed(id) {
      const g = this.cat[id], s = this.s;
      return !((s.perks.owned[id] || 0) >= g.max_stack || g.sacrifice && s.health <= g.sacrifice || g.recovery_signals && s.health <= 1
        || g.heal && s.health >= this.p.max_health || id === 'blood_price' && s.health < 3 || g.cap_health && s.health <= g.cap_health);
    }
    draftDue() { const d = floor((this.s.signal - 1) / this.p.chunk); return d > this.s.selected.length ? this.p.drafts[d - 1] : null; }
    pick(id) {
      this.s.journal.push({kind: 'pick', perk_id: id});
      this.s.selected.push(id);
      if (id === null) return;
      const g = this.cat[id], p = this.s.perks;
      p.owned[id] = (p.owned[id] || 0) + 1; p.shield += g.shield; p.ebb = Math.max(p.ebb, g.ebb); p.bloody = Math.max(p.bloody, g.bloody);
      let h = Math.min(this.p.max_health, this.s.health + g.heal) - g.sacrifice;
      if (g.cap_health) h = Math.min(h, g.cap_health);
      if (id === 'blood_price') h--;
      this.s.health = h;
    }
    tap(rune, elapsed) {
      const s = this.s, p = s.perks, w = this.window(), expected = this.p.runes[s.signal - 1];
      const correct = rune === expected && elapsed <= w, timeout = rune === null || elapsed > w;
      s.journal.push({kind: 'tap', signal_no: s.signal, rune, elapsed_ms: elapsed});
      if (correct) {
        s.score += this.score(elapsed); s.combo++; s.streak++;
        p.bloody = Math.max(0, p.bloody - 1);
        const every = Object.keys(p.owned).map(id => this.cat[id].regen_every).filter(Boolean);
        if (every.length && s.streak % Math.min(...every) === 0) s.health = Math.min(this.p.max_health, s.health + 1);
      } else { s.combo = s.streak = 0; }
      p.ebb = Math.max(0, p.ebb - 1); p.recovery = Math.max(0, p.recovery - 1);
      if (!correct) {
        if (p.shield > 0) p.shield--;
        else if (!(timeout && this.any('timeout_free') && ++p.miss_debt % 2 === 1)) {
          s.health = Math.max(0, s.health - 1 - this.total('damage_extra') - (timeout ? 0 : this.total('wrong_extra')));
          if (s.health > 0) p.recovery = Math.max(p.recovery, ...Object.keys(p.owned).map(id => this.cat[id].recovery_signals || 0));
        }
      }
      s.signal++;
      return correct;
    }
    over() { return this.s.health <= 0 || this.s.signal > this.p.signals; }
  }

  let engine = null, run = null, shownAt = 0, timeout = null, live = false, hiddenPause = false;

  async function start(level) {
    run = await L().api('/runs', {method: 'POST', body: JSON.stringify({game: 'rhythm', level})});
    engine = new Engine(run);
    L().show(`<h2>Ритм · уровень ${run.level}</h2>
      <p class="lg-rules">${run.signals} тактов, ${run.hearts} сердца, окно в начале ${run.base_window_ms} мс. Дойди до конца, сохранив сердце.
      ★★ — от ${Math.ceil(run.reference * run.star_pct[0] / 100)} очков, ★★★ — от ${Math.ceil(run.reference * run.star_pct[1] / 100)}.</p>
      <div class="lg-row"><button type="button" id="lgr-go">Старт</button><button type="button" class="secondary" id="lgr-exit">К уровням</button></div>`);
    L().$('lgr-go').onclick = () => countdown(COUNTDOWN);
    L().$('lgr-exit').onclick = () => L().back();
  }

  function hud() {
    const s = engine.s;
    return `<div class="lg-stats"><div><b>${'❤'.repeat(Math.max(0, s.health))}</b><small>сердца</small></div><div><b>${s.score}</b><small>очки</small></div><div><b>${Math.min(s.signal, run.signals)}/${run.signals}</b><small>такт</small></div></div>`;
  }

  function countdown(n) {
    live = false;
    L().show(`<h2>Уровень ${run.level}</h2>${hud()}<div class="lg-target" aria-live="assertive">${n}</div>`);
    if (n > 0) setTimeout(() => countdown(n - 1), 1000); else next();
  }

  function next() {
    if (engine.over()) return finish();
    const offers = engine.draftDue();
    if (offers) return draft(offers);
    const rune = run.runes[engine.s.signal - 1];
    L().show(`<h2>Уровень ${run.level}</h2>${hud()}<div class="lg-target" aria-label="Нажми руну">${GLYPH[rune]}</div>
      <div class="lg-bar"><i id="lgr-bar"></i></div>
      <div class="lg-runes" role="group" aria-label="Руны">${Object.keys(GLYPH).map(r => `<button type="button" data-rune="${r}">${GLYPH[r]}</button>`).join('')}</div>`);
    const w = engine.window(), bar = L().$('lgr-bar');
    requestAnimationFrame(() => {
      shownAt = performance.now(); live = true;
      bar.style.transition = `transform ${w}ms linear`; bar.style.transform = 'scaleX(0)';
    });
    document.querySelectorAll('[data-rune]').forEach(b => b.addEventListener('pointerdown', e => { e.preventDefault(); answer(b.dataset.rune); }));
    timeout = setTimeout(() => answer(null), w + 1);
  }

  function answer(rune) {
    if (!live) return;
    live = false; clearTimeout(timeout);
    const elapsed = rune === null ? engine.window() + 1 : Math.max(0, Math.round(performance.now() - shownAt));
    const ok = engine.tap(rune, elapsed);
    L().haptic(ok ? 'light' : 'heavy');
    setTimeout(next, GAP_MS);
  }

  function draft(offers) {
    const card = id => { const g = engine.cat[id], ok = engine.allowed(id);
      return `<button type="button" class="lg-gift ${g.kind === 'risk' ? 'risk' : ''}" data-gift="${id}" ${ok ? '' : 'disabled'}>${L().esc(g.name)}
        <small>＋ ${L().esc(g.bonus)} · − ${L().esc(g.cost)}${ok ? '' : ' · сейчас нельзя'}</small></button>`; };
    L().show(`<h2>Дар уровня</h2><p class="lg-rules">Эти три дара одинаковые у всех игроков этого уровня. Можно пропустить.</p>${hud()}
      <div class="lg-gifts">${offers.map(card).join('')}<button type="button" class="secondary" data-gift="">Пропустить дар</button></div>`);
    document.querySelectorAll('[data-gift]').forEach(b => { b.onclick = () => { engine.pick(b.dataset.gift || null); countdown(COUNTDOWN); }; });
  }

  async function finish(retry = false) {
    L().show(`<h2>Уровень ${run.level}</h2>${hud()}<p class="lg-rules">Проверяем уровень…</p>`);
    try {
      const r = await L().api(`/runs/${encodeURIComponent(run.run_id)}/rhythm`, {method: 'POST', body: JSON.stringify({actions: engine.s.journal})});
      const d = r.detail || {};
      L().show(`<h2>Уровень ${run.level}</h2><div class="lg-stars" aria-label="Звёзд: ${r.stars} из 3">${L().stars(r.stars)}</div>
        <p class="lg-rules">${r.stars ? 'Уровень пройден!' : 'Сердца кончились.'} Очки: ${d.score}, верных: ${d.correct}, ошибок: ${d.mistakes}.${r.xp ? ` +${r.xp} опыта Пропуска (демо).` : ''}</p>
        <div class="lg-row">${r.stars ? `<button type="button" id="lgr-next">Уровень ${run.level + 1}</button>` : ''}<button type="button" class="${r.stars ? 'secondary' : ''}" id="lgr-again">Ещё раз</button><button type="button" class="secondary" id="lgr-exit">К уровням</button></div>`);
      L().$('lgr-again').onclick = () => start(run.level).catch(e => alert(e.message));
      if (L().$('lgr-next')) L().$('lgr-next').onclick = () => start(run.level + 1).catch(e => alert(e.message));
      L().$('lgr-exit').onclick = () => L().back();
    } catch (error) {
      L().show(`<h2>Уровень ${run.level}</h2><p class="lg-error" role="alert">${L().esc(error.message)}</p>
        <div class="lg-row">${error.status === 409 ? '' : '<button type="button" id="lgr-send">Отправить ещё раз</button>'}<button type="button" class="secondary" id="lgr-exit">К уровням</button></div>`);
      if (L().$('lgr-send')) L().$('lgr-send').onclick = () => finish(true);
      L().$('lgr-exit').onclick = () => L().back();
    }
  }

  // Свернул приложение посреди такта — такт не сгорает: после возвращения тот же такт начинается заново с отсчётом.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && live) { live = false; clearTimeout(timeout); hiddenPause = true; }
    else if (!document.hidden && hiddenPause) { hiddenPause = false; countdown(COUNTDOWN); }
  });

  window.LeagueRhythmEngine = Engine;   // тест паритета с сервером (tools/test_league_v1_parity.js)
  window.LeagueGames = {...(window.LeagueGames || {}), rhythm: {start}};
})();
