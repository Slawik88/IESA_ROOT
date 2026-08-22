(() => {
  'use strict';

  const runtime = document.body.dataset.runtime || 'preview';
  const production = runtime === 'production';
  const appBase = (document.body.dataset.appBase || '').replace(/\/$/, '');
  const API = production
    ? `${appBase}/reconstruction`
    : (document.body.dataset.apiBase || '/__reconstruction');
  const FRAME_MS = 100;
  const SESSION_STORAGE_KEY = 'reconstruction-preview-session';
  const STATS_STORAGE_KEY = 'reconstruction-mvp-career-v1';
  const UI_STORAGE_KEY = 'reconstruction-mvp-ui-v1';
  let previewSession = sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (!previewSession) {
    previewSession = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    sessionStorage.setItem(SESSION_STORAGE_KEY, previewSession);
  }

  const stage = document.getElementById('tapStage');
  const core = document.getElementById('tapCore');
  const orbit = document.getElementById('runeOrbit');
  const impactLayer = document.getElementById('impactLayer');
  const menuLayer = document.getElementById('menuLayer');
  const pauseLayer = document.getElementById('pauseLayer');
  const choiceLayer = document.getElementById('choiceLayer');
  const resultLayer = document.getElementById('resultLayer');
  const toast = document.getElementById('statusToast');
  let manifest = null;
  let state = null;
  let currentView = 'menu';
  let currentMenuTab = 'play';
  let playing = false;
  let busy = false;
  let pendingStrike = null;
  let pendingBranchAction = null;
  let branchActionInFlight = false;
  let lastFrameAt = performance.now();
  let lastEventId = 0;
  let toastTimer = null;
  let runId = null;
  let progress = null;
  let units = [];
  let companionState = null;
  let pendingMemory = null;
  let actionSequence = 0;

  document.getElementById('homeLink').href = `${appBase}/` || '/';
  if (production) {
    document.getElementById('runtimeEyebrow').textContent = 'БОЕВАЯ СИСТЕМА';
    document.getElementById('profileKind').textContent = 'ПРОФИЛЬ ИГРОКА';
    document.getElementById('statsEyebrow').textContent = 'ПРОФИЛЬ РАЗЛОМА';
    document.getElementById('statsCopy').textContent =
      'Серверная статистика завершённых забегов. Пропуски входят в расчёт точности.';
    document.getElementById('runtimeFooter').textContent =
      'MVP · прогресс и статистика сохраняются в профиле';
  }

  const emptyCareer = () => ({
    runsStarted: 0,
    runsWon: 0,
    runsLost: 0,
    correctTaps: 0,
    totalTaps: 0,
    mistakes: 0,
    missedSignals: 0,
    bestCombo: 0,
    fastestWinMs: null,
    totalPlayMs: 0,
    upgrades: {},
    startedRunKeys: [],
    completedRunKeys: [],
  });

  function loadCareer() {
    if (production) return emptyCareer();
    try {
      const value = JSON.parse(localStorage.getItem(STATS_STORAGE_KEY) || '{}');
      return { ...emptyCareer(), ...(value && typeof value === 'object' ? value : {}) };
    } catch (_) {
      return emptyCareer();
    }
  }

  let career = loadCareer();
  const esc = (value) => String(value ?? '').replace(/[&<>"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;',
  })[char]);
  const number = (value) => Math.max(0, Math.round(Number(value) || 0)).toLocaleString('ru-RU');
  const percent = (value) => value === null || value === undefined ? '—' : `${number(value)}%`;
  const shortTime = (seconds) => {
    const value = Math.max(0, Math.round(Number(seconds) || 0));
    if (value >= 3600) return `${Math.floor(value / 3600)}ч ${Math.floor(value % 3600 / 60)}м`;
    if (value >= 60) return `${Math.floor(value / 60)}м ${value % 60}с`;
    return `${value}с`;
  };
  const encounterById = (id) => (manifest?.encounters || []).find((item) => item.id === id);
  const activeEncounter = () => encounterById(state?.encounter_id);
  const runKey = () => state
    ? (production ? String(runId || '') : `${state.game_version}:${state.seed}`)
    : '';
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function saveCareer() {
    if (production) return;
    career.startedRunKeys = [...new Set(career.startedRunKeys)].slice(-40);
    career.completedRunKeys = [...new Set(career.completedRunKeys)].slice(-40);
    try { localStorage.setItem(STATS_STORAGE_KEY, JSON.stringify(career)); } catch (_) { /* optional */ }
  }

  function savedUiState() {
    try {
      const value = JSON.parse(sessionStorage.getItem(UI_STORAGE_KEY) || '{}');
      return {
        view: ['menu', 'battle', 'pause', 'choice', 'result'].includes(value.view) ? value.view : null,
        tab: ['play', 'companion', 'stats', 'help'].includes(value.tab) ? value.tab : 'play',
      };
    } catch (_) {
      return { view: null, tab: 'play' };
    }
  }

  function saveUiState() {
    try {
      sessionStorage.setItem(UI_STORAGE_KEY, JSON.stringify({ view: currentView, tab: currentMenuTab }));
    } catch (_) { /* optional */ }
  }

  function showOnly(view, tab = currentMenuTab, persist = true) {
    currentView = view;
    currentMenuTab = tab;
    menuLayer.hidden = view !== 'menu';
    pauseLayer.hidden = view !== 'pause';
    choiceLayer.hidden = view !== 'choice';
    resultLayer.hidden = view !== 'result';
    document.getElementById('menuButton').setAttribute(
      'aria-expanded', String(['menu', 'pause'].includes(view)),
    );
    if (view === 'menu') selectMenuTab(tab, false);
    if (persist) saveUiState();
  }

  function recordRunStarted() {
    if (production) return;
    const key = runKey();
    if (!key || career.startedRunKeys.includes(key)) return;
    career.startedRunKeys.push(key);
    career.runsStarted += 1;
    saveCareer();
  }

  function recordRunCompleted() {
    if (production) return;
    const key = runKey();
    if (!key || !['won', 'lost'].includes(state?.status) || career.completedRunKeys.includes(key)) return;
    recordRunStarted();
    career.completedRunKeys.push(key);
    career.runsWon += Number(state.status === 'won');
    career.runsLost += Number(state.status === 'lost');
    career.correctTaps += Number(state.mastery.correct_taps) || 0;
    career.totalTaps += Number(state.mastery.total_taps) || 0;
    career.mistakes += Number(state.mastery.mistakes) || 0;
    career.missedSignals += Number(state.mastery.missed_signals) || 0;
    career.bestCombo = Math.max(career.bestCombo, Number(state.combo.max) || 0);
    career.totalPlayMs += Number(state.mastery.elapsed_ms) || 0;
    if (state.status === 'won') {
      const elapsed = Number(state.mastery.elapsed_ms) || 0;
      career.fastestWinMs = career.fastestWinMs === null ? elapsed : Math.min(career.fastestWinMs, elapsed);
    }
    for (const upgradeId of state.upgrades || []) {
      career.upgrades[upgradeId] = (career.upgrades[upgradeId] || 0) + 1;
    }
    saveCareer();
  }

  async function jsonFetch(path, options = {}) {
    let response;
    let data = {};
    for (let attempt = 0; attempt < 3; attempt += 1) {
      response = await fetch(API + path, {
        ...options,
        headers: {
          'content-type': 'application/json',
          ...(production ? {
            ...(window.Telegram?.WebApp?.initData
              ? { 'x-init-data': window.Telegram.WebApp.initData }
              : {}),
            ...(localStorage.getItem('pv_sess')
              ? { 'x-session-token': localStorage.getItem('pv_sess') }
              : {}),
          } : { 'x-reconstruction-session': previewSession }),
          ...(options.headers || {}),
        },
      });
      data = await response.json().catch(() => ({}));
      if (response.status !== 503 || attempt === 2) break;
      await wait(180 * (attempt + 1));
    }
    if (!response.ok) {
      const error = new Error(data.detail || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function applyCareerStats(stats) {
    if (!stats || !production) return;
    career = {
      ...emptyCareer(),
      runsStarted: Number(stats.runs_started) || 0,
      runsWon: Number(stats.runs_won) || 0,
      runsLost: Number(stats.runs_lost) || 0,
      correctTaps: Number(stats.correct_taps) || 0,
      totalTaps: Number(stats.total_taps) || 0,
      mistakes: Number(stats.mistakes) || 0,
      missedSignals: Number(stats.missed_signals) || 0,
      bestCombo: Number(stats.best_combo) || 0,
      fastestWinMs: stats.fastest_win_ms == null ? null : Number(stats.fastest_win_ms),
      totalPlayMs: Number(stats.total_play_ms) || 0,
      upgrades: stats.upgrades || {},
    };
  }

  async function resyncAfterConflict(message) {
    if (!production) return;
    const overview = await jsonFetch('');
    manifest = overview.content;
    progress = overview.progress;
    units = overview.units || [];
    pendingMemory = overview.progress?.pending_memory || null;
    state = overview.active_run || null;
    runId = state?.run_id || null;
    applyCareerStats(overview.stats);
    pendingStrike = null;
    playing = false;
    if (pendingMemory && !state) showMemoryChoice();
    else if (!state) openMenu('play');
    else if (state.status === 'reward') showOnly('choice');
    else showOnly('pause');
    render();
    notify(message || 'Забег обновлён из серверного состояния.');
  }

  function notify(message, error = false) {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.className = `status-toast show${error ? ' error' : ''}`;
    toastTimer = setTimeout(() => { toast.className = 'status-toast'; }, 2200);
  }

  function haptic(kind = 'light') {
    try { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred(kind); } catch (_) { /* optional */ }
  }

  function hapticError() {
    try { window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('error'); } catch (_) { /* optional */ }
  }

  function setTesterIdentity() {
    const user = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (!user) return;
    const name = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username || 'Игрок';
    document.getElementById('testerName').textContent = name;
    document.getElementById('testerAvatar').textContent = name.trim().slice(0, 1).toUpperCase() || '◉';
  }

  function spawnImpact(x, y, label, critical = false) {
    const bounds = stage.getBoundingClientRect();
    const node = document.createElement('span');
    node.className = `impact${critical ? ' critical' : ''}`;
    node.textContent = label;
    node.style.left = `${Math.min(bounds.width - 24, Math.max(24, x - bounds.left))}px`;
    node.style.top = `${Math.min(bounds.height - 30, Math.max(50, y - bounds.top))}px`;
    impactLayer.appendChild(node);
    setTimeout(() => node.remove(), 560);
  }

  function animateEvent(event) {
    if (!playing || !event?.id || event.id === lastEventId) return;
    lastEventId = event.id;
    const pulse = document.getElementById('eventPulse');
    pulse.textContent = event.kind === 'discharge' ? '⚡' : event.kind === 'critical' ? '✦' : event.kind === 'miss' ? '×' : '·';
    if (event.kind === 'discharge') {
      stage.classList.remove('discharge');
      void stage.offsetWidth;
      stage.classList.add('discharge');
      setTimeout(() => stage.classList.remove('discharge'), 460);
      haptic('heavy');
    } else if (event.kind === 'critical' || event.kind === 'hit') {
      haptic(event.kind === 'critical' ? 'medium' : 'light');
    } else if (event.kind === 'miss') {
      stage.classList.add('miss');
      setTimeout(() => stage.classList.remove('miss'), 320);
      hapticError();
    }
  }

  function renderRail() {
    document.querySelectorAll('[data-wave-node]').forEach((node) => {
      const wave = Number(node.dataset.waveNode);
      const label = node.querySelector('small');
      if (label && state.wave_labels?.[wave - 1]) label.textContent = state.wave_labels[wave - 1];
      node.classList.toggle('complete', wave < state.round || state.status === 'won');
      node.classList.toggle('current', wave === state.round && state.status !== 'won');
    });
  }

  function renderSquad() {
    const labels = ['Пассивный урон', 'Усиление серии ×5', 'Заряд Разряда'];
    document.getElementById('squadStrip').innerHTML = state.team.units.map((unit, index) => `
      <div class="squad-member"><i>${esc(unit.emoji)}</i><span><strong>${esc(unit.name)}</strong><small>${labels[index]}</small></span></div>`).join('');
  }

  function renderBuild() {
    const container = document.getElementById('activeBuild');
    const catalog = new Map((manifest?.clicker_upgrades || []).map((item) => [item.id, item]));
    const selected = (state.upgrades || []).map((id) => catalog.get(id)).filter(Boolean);
    const role = (manifest?.companions?.roles || []).find((item) => item.id === state.companion_role_id);
    container.hidden = false;
    const roleChip = role ? `<span class="companion-build"><i>${esc(role.emoji)}</i><b>${esc(role.name)}</b><small>роль спутника</small></span>` : '';
    container.innerHTML = roleChip + (selected.length ? selected.map((upgrade) => `
      <span><i>${esc(upgrade.emoji)}</i><b>${esc(upgrade.name)}</b><small>${esc(upgrade.archetype)}</small></span>`).join('')
      : '<span class="empty-build"><i>＋</i><b>Сборка</b><small>усиление после волны</small></span>');
  }

  function renderRunes() {
    if (!state) return;
    const challenge = state.challenge;
    const options = new Map((challenge?.options || []).map((option) => [option.slot, option]));
    orbit.querySelectorAll('[data-target-slot]').forEach((button) => {
      const option = options.get(button.dataset.targetSlot);
      const symbol = option?.symbol || '·';
      button.textContent = symbol;
      button.disabled = !playing || !challenge?.active || Boolean(pendingStrike);
      button.setAttribute('aria-label', `${button.dataset.targetSlot}: руна ${symbol}`);
      button.classList.toggle('seam-stored', state.branch_state?.stored_seam_slot === button.dataset.targetSlot);
      button.classList.toggle('forbidden', state.branch_state?.forbidden_slot === button.dataset.targetSlot);
      const objective = state.objective_state || {};
      const blockedSlot = objective.kind === 'mirror_rule' ? objective.forbidden_slot
        : objective.kind === 'archivist_boss' && objective.phase === 'record'
          ? objective.recorded_slot : null;
      button.classList.toggle('mirror-forbidden', blockedSlot === button.dataset.targetSlot);
      button.classList.toggle('companion-decoy', option?.companion_hint === 'decoy');
    });
  }

  function renderBranchDecision() {
    const decision = state.branch_state?.decision;
    if (!decision || ['menu', 'pause', 'result'].includes(currentView)) return;
    playing = false;
    document.getElementById('choiceEyebrow').textContent = 'НАРУШЕННАЯ КЛЯТВА';
    document.getElementById('choiceTitle').textContent = 'Что сделать с Импульсом?';
    document.getElementById('choiceCopy').textContent =
      'Сохранение помогает Разряду, но следующее окно станет короче. Отказ безопаснее.';
    document.getElementById('upgradeList').innerHTML = `
      <button class="upgrade-card" type="button" data-combat-command="vow_keep" data-decision-id="${esc(decision.id)}">
        <span>🔔</span><span class="upgrade-copy"><em>РИСК</em><strong>Сохранить половину</strong><small>Вернуть 50% Импульса до ошибки.</small><small class="tradeoff">− Следующее окно короче на 0,18 с.</small></span><b>›</b>
      </button>
      <button class="upgrade-card" type="button" data-combat-command="vow_release" data-decision-id="${esc(decision.id)}">
        <span>◌</span><span class="upgrade-copy"><em>СТАБИЛЬНОСТЬ</em><strong>Отпустить заряд</strong><small>Следующий сигнал останется полным.</small><small class="tradeoff">− Импульс обнулится.</small></span><b>›</b>
      </button>`;
    showOnly('choice');
  }

  function renderBranchControls() {
    const container = document.getElementById('branchControls');
    const branch = state.branch_state || {};
    const selected = new Set(Object.values(state.unit_branches || {}).flatMap(
      (value) => Array.isArray(value) ? value : [value],
    ));
    const controls = [];
    if (selected.has('bell_silent_release') && branch.manual_discharge && state.challenge?.active) {
      controls.push('<button type="button" data-combat-command="manual_discharge">⚡ Выпустить Разряд</button>');
    }
    if (selected.has('seam_forbidden_repeat')) {
      controls.push(`<button type="button" class="${branch.forbidden_mode ? 'risk-on' : ''}" data-combat-command="forbidden_toggle" data-enabled="${branch.forbidden_mode ? 'false' : 'true'}">🪡 Риск ${branch.forbidden_mode ? 'вкл' : 'выкл'}</button>`);
    }
    if (selected.has('tide_hidden_swap') && state.challenge?.active && !branch.tide_swap_used) {
      controls.push('<button type="button" data-combat-command="tide_swap">🌊 Сдвинуть руны</button>');
    }
    const guardianUsed = state.companion_state?.guardian_used_rounds || [];
    if (state.companion_role_id === 'guardian' && state.challenge?.active && !guardianUsed.includes(state.round)) {
      controls.push('<button type="button" data-combat-command="companion_guardian_window">⬡ Расширить это окно</button>');
    }
    container.innerHTML = controls.join('');
    container.hidden = !controls.length;
  }

  function renderChoice() {
    if (state.status !== 'reward' || ['menu', 'pause', 'result'].includes(currentView)) return;
    playing = false;
    document.getElementById('choiceEyebrow').textContent = 'ВОЛНА ПРОЙДЕНА';
    document.getElementById('choiceTitle').textContent = 'Выбери направление сборки';
    document.getElementById('choiceCopy').textContent =
      'У каждого усиления есть преимущество и цена. Выбор действует только в этом забеге.';
    document.getElementById('upgradeList').innerHTML = state.reward_options.map((upgrade) => `
      <button class="upgrade-card" type="button" data-upgrade-id="${esc(upgrade.id)}">
        <span>${esc(upgrade.emoji)}</span>
        <span class="upgrade-copy"><em>${esc(upgrade.archetype)}</em><strong>${esc(upgrade.name)}</strong><small>${esc(upgrade.description)}</small><small class="tradeoff">− ${esc(upgrade.tradeoff)}</small></span>
        <b>›</b>
      </button>`).join('');
    showOnly('choice');
  }

  function showMemoryChoice() {
    const choices = pendingMemory?.choices || [];
    if (!choices.length) return false;
    playing = false;
    document.getElementById('choiceEyebrow').textContent = 'ПЕРВАЯ ПОБЕДА';
    document.getElementById('choiceTitle').textContent = 'Сохрани одну Память';
    document.getElementById('choiceCopy').textContent =
      'Это постоянный выбор профиля. Он не тратит валюту и останется после забега.';
    document.getElementById('upgradeList').innerHTML = choices.map((memory) => {
      const unit = (manifest?.starter_units || []).find((item) => item.id === memory.unit_id);
      return `
      <button class="upgrade-card" type="button" data-memory-id="${esc(memory.id)}">
        <span>${esc(unit?.emoji || '◌')}</span>
        <span class="upgrade-copy"><em>ПОСТОЯННАЯ ПАМЯТЬ</em><strong>${esc(memory.name)}</strong><small>${esc(memory.effect)}</small><small class="tradeoff">− ${esc(memory.tradeoff)}</small></span>
        <b>›</b>
      </button>`;
    }).join('');
    showOnly('choice');
    return true;
  }

  function showChroniclePathChoice() {
    const next = progress?.next_step;
    if (next?.type !== 'choose_chronicle_path' || !(next.choices || []).length) return false;
    playing = false;
    document.getElementById('choiceEyebrow').textContent = 'ХРОНИКА · РАЗВИЛКА';
    document.getElementById('choiceTitle').textContent = 'Куда понесёшь Память?';
    document.getElementById('choiceCopy').textContent =
      'Обе тропы остаются в истории, но первая выбранная меняет обучение этой главы.';
    document.getElementById('upgradeList').innerHTML = next.choices.map((choice) => `
      <button class="upgrade-card" type="button" data-chronicle-path="${esc(choice.id)}">
        <span>${choice.id === 'ink' ? '◆' : '🔥'}</span>
        <span class="upgrade-copy"><em>${choice.id === 'ink' ? 'ЧТЕНИЕ' : 'ТЕМП'}</em><strong>${esc(choice.name)}</strong><small>${esc(choice.description)}</small><small class="mastery">Мастерство: ${esc(choice.mastery)}</small></span>
        <b>›</b>
      </button>`).join('');
    showOnly('choice');
    return true;
  }

  function unitBranches(unitId) {
    return manifest?.unit_progression?.branches?.[unitId]?.['5'] || [];
  }

  function showUnitBranchChoice(unitId) {
    const unit = units.find((item) => item.unit_id === unitId);
    if (!unit) return;
    if (Number(unit.level) < 5) {
      notify(`Ветвь откроется на 5 уровне. Сейчас ${number(unit.level)}.`);
      return;
    }
    const selected = unit.branch_choices?.['5'];
    if (selected) {
      const branch = unitBranches(unitId).find((item) => item.id === selected);
      notify(`Уже выбрана ветвь «${branch?.name || selected}».`);
      return;
    }
    playing = false;
    document.getElementById('choiceEyebrow').textContent = `${unit.short_name} · УРОВЕНЬ 5`;
    document.getElementById('choiceTitle').textContent = 'Выбери ветвь мастерства';
    document.getElementById('choiceCopy').textContent =
      'Обе ветви меняют решение в бою и имеют цену. Первый выбор бесплатный и постоянный.';
    const proven = new Set(unit.proven_challenges || []);
    document.getElementById('upgradeList').innerHTML = unitBranches(unitId).map((branch) => {
      const unlocked = proven.has(branch.mastery_challenge);
      return `
      <button class="upgrade-card" type="button" data-unit-id="${esc(unitId)}" data-unit-branch="${esc(branch.id)}" ${unlocked ? '' : 'disabled'}>
        <span>${esc(unit.emoji)}</span>
        <span class="upgrade-copy"><em>${unlocked ? 'ИСПЫТАНИЕ ПРОЙДЕНО' : 'НУЖНО ИСПЫТАНИЕ'}</em><strong>${esc(branch.name)}</strong><small>${esc(branch.decision)}</small><small class="tradeoff">− ${esc(branch.tradeoff)}</small><small class="mastery">${esc(branch.mastery_requirement)}</small></span>
        <b>›</b>
      </button>`;
    }).join('');
    showOnly('choice');
  }

  function renderUnitProgress() {
    const container = document.getElementById('unitProgress');
    if (!units.length) {
      container.hidden = true;
      return;
    }
    container.hidden = false;
    container.innerHTML = units.map((unit) => {
      const selected = unit.branch_choices?.['5'];
      const selectedBranch = unitBranches(unit.unit_id).find((branch) => branch.id === selected);
      const ready = Number(unit.level) >= 5 && !selected;
      const detail = selectedBranch?.name || (ready ? 'выбрать ветвь' : `ветвь на ${unit.next_branch_level || 30} ур.`);
      return `<button class="unit-progress-card${ready ? ' ready' : ''}" type="button" data-unit-progress="${esc(unit.unit_id)}"><i>${esc(unit.emoji)}</i><strong>${esc(unit.short_name)}</strong><small>ур. ${number(unit.level)} · ${esc(detail)}</small></button>`;
    }).join('');
  }

  function resultSummary() {
    const outcome = state.status === 'won' ? 'Победа' : 'Поражение';
    const name = activeEncounter()?.name || 'Разлом колокола';
    return `${outcome} во встрече «${name}»: точность ${percent(state.accuracy)}, серия ${state.combo.max}, ошибок ${state.mastery.mistakes}, время ${Math.round(state.mastery.elapsed_ms / 1000)} с.`;
  }

  function renderResult() {
    if (!['won', 'lost'].includes(state.status) || ['menu', 'pause'].includes(currentView)) return;
    playing = false;
    recordRunCompleted();
    const won = state.status === 'won';
    const objectiveKind = state.objective_state?.kind;
    const lantern = objectiveKind === 'lantern_escort';
    const ink = objectiveKind === 'ink_decipher';
    const ash = objectiveKind === 'ash_fire';
    const sequence = objectiveKind === 'drowned_sequence';
    const mirror = objectiveKind === 'mirror_rule';
    const archivist = objectiveKind === 'archivist_boss';
    const next = progress?.next_step;
    document.getElementById('resultMark').textContent = won ? '✦' : '◌';
    document.getElementById('resultEyebrow').textContent = won ? 'ВСТРЕЧА ПРОЙДЕНА' : 'ВСТРЕЧА НЕ ПРОЙДЕНА';
    document.getElementById('resultTitle').textContent = archivist
      ? (won ? 'Архивариус отпустил имя' : 'Запись не разорвана')
      : mirror
      ? (won ? 'Переписчик отступил' : 'Зеркала сомкнулись')
      : sequence
      ? (won ? 'Имена освобождены' : 'Цепочка утрачена')
      : ink
      ? (won ? 'Настоящие имена прочитаны' : 'Отражения победили')
      : ash ? (won ? 'Огонь сохранён' : 'Костёр погас')
      : lantern
      ? (won ? 'Фонарь достиг ворот' : 'Фонарь не дошёл')
      : (won ? 'Колокол отвечает тебе' : 'Эхо погасло');
    document.getElementById('resultCopy').textContent = archivist
      ? (won
        ? 'Ты прочитал Запись, адаптировался к Приливу и вернул Последнее имя без подсказки.'
        : 'Каждая фаза требует другого решения: меняй позицию, читай длину окна и удерживай короткую цепочку.')
      : mirror
      ? (won
        ? 'Ты читал перестановку и каждый раз менял позицию, не превращая бой в привычный ритм.'
        : 'После ответа выбранная позиция временно запрещена. Ищи тот же знак в новом месте.')
      : sequence
      ? (won
        ? 'Ты удержал порядок без подсказки и разорвал все три якоря.'
        : 'Сначала смотри всю цепочку. Во время ответа важен порядок, а не скорость нажатий.')
      : ink
      ? (won
        ? 'Ты дождался настоящих сигналов и не позволил ранним отражениям управлять выбором.'
        : 'Ранний символ — только отражение. Решение принимается после открытия трёх рун.')
      : ash ? (won
        ? 'Ты удержал темп и сохранил жар. Золотые ответы помогли, но не были обязательным ритм-экзаменом.'
        : 'Огонь гаснет со временем и от ошибок. Точные ответы поддерживают его, золотые возвращают больше.')
      : lantern
      ? (won
        ? 'Точная серия сохранила свет до конца тракта. Ошибки можно было исправить, но не заменить скоростью.'
        : state.outcome_reason === 'lantern_accuracy_failed'
          ? 'Фонарь дошёл, но точность оказалась ниже 75%. Собирай серию осознанно и не угадывай.'
          : 'Ошибки гасят Фонарь, а каждые пять точных знаков возвращают часть его света.')
      : (won
        ? 'Ты точно прошёл три волны, а выбранные усиления сложились в полноценную сборку.'
        : 'Посмотри на знак в центре и выбирай его отражение. Частота нажатий не заменяет точность.');
    const stats = [
      [state.mastery.correct_taps, 'точных'],
      [percent(state.accuracy), 'точность'],
      [state.combo.max, 'макс. серия'],
      [state.mastery.mistakes, 'ошибок'],
      [state.mastery.missed_signals, 'пропущено'],
      [`${Math.round(state.mastery.elapsed_ms / 1000)}с`, 'время'],
    ];
    if (lantern) stats.splice(0, 1, [`${number(state.objective_state.lantern_integrity)}%`, 'свет Фонаря']);
    if (ink) stats.splice(0, 1, [`${number(state.objective_state.clarity)}%`, 'ясность']);
    if (ash) stats.splice(0, 1, [`${number(state.objective_state.fire_integrity)}%`, 'огонь']);
    if (sequence) stats.splice(0, 1, [`${number(state.objective_state.anchors_broken)}/${number(state.objective_state.anchors_total)}`, 'якоря']);
    if (mirror) stats.splice(0, 1, [`${number(state.objective_state.wards)}/${number(state.objective_state.wards_max)}`, 'печати']);
    if (archivist) stats.splice(0, 1, [`${number(state.objective_state.phases_completed)}/${number(state.objective_state.phases_total)}`, 'фазы']);
    document.getElementById('resultStats').innerHTML = stats
      .map(([value, label]) => `<span><strong>${esc(value)}</strong>${esc(label)}</span>`).join('');
    const previewContinues = !production && won && state.encounter_id === 'e01_two_bells';
    const actionLabel = pendingMemory ? 'Выбрать Память'
      : next?.type === 'choose_chronicle_path' ? 'Выбрать тропу'
      : won && next?.type === 'play_encounter' ? 'Продолжить Хронику'
        : previewContinues ? 'Продолжить Хронику'
        : next?.type === 'development_gate' ? 'Тренировка'
          : 'Попробовать снова';
    document.getElementById('resultReset').innerHTML = `${actionLabel} <span>›</span>`;
    showOnly('result');
  }

  function renderCareer() {
    const attempts = (Number(career.correctTaps) || 0) + (Number(career.mistakes) || 0) + (Number(career.missedSignals) || 0);
    const accuracy = attempts ? Math.round(career.correctTaps / attempts * 1000) / 10 : null;
    document.getElementById('careerStats').innerHTML = [
      [career.runsStarted, 'забегов'],
      [career.runsWon, 'побед'],
      [percent(accuracy), 'точность'],
      [career.bestCombo, 'лучшая серия'],
      [career.mistakes, 'ошибок'],
      [career.missedSignals, 'пропущено'],
    ].map(([value, label]) => `<span><strong>${esc(value)}</strong>${esc(label)}</span>`).join('');
    const catalog = new Map((manifest?.clicker_upgrades || []).map((item) => [item.id, item]));
    const favorites = Object.entries(career.upgrades || {}).sort((a, b) => b[1] - a[1]);
    document.getElementById('buildHistory').innerHTML = favorites.length
      ? `<span>Чаще выбираешь</span>${favorites.slice(0, 2).map(([id, count]) => {
        const item = catalog.get(id);
        return `<b>${esc(item?.emoji || '·')} ${esc(item?.name || id)} <small>×${number(count)}</small></b>`;
      }).join('')}`
      : '<span>История сборок появится после первого завершённого забега.</span>';
  }

  function renderCompanions() {
    const container = document.getElementById('companionContent');
    if (!container) return;
    if (!companionState) {
      container.innerHTML = '<div class="companion-empty">Загружаю профиль спутника…</div>';
      return;
    }
    const species = {
      fox: '🦊', owl: '🦉', dragon: '🐉', dog: '🐕', squirrel: '🐿️', hamster: '🐹',
      turtle: '🐢', falcon: '🦅', wolf: '🐺', unicorn: '🦄',
    };
    const rarityNames = {
      common: 'обычный', rare: 'редкий', epic: 'эпический', legendary: 'легендарный',
    };
    const discoveryNames = {
      bell_fragment: 'осколок колокола', salt_map: 'соляная карта', ink_trace: 'чернильный след',
      ash_seed: 'семя пепла', drowned_name: 'утонувшее имя', mirror_shard: 'осколок зеркала',
      tide_formula: 'формула прилива', quiet_key: 'тихий ключ', archive_thread: 'нить архива',
      lantern_glass: 'стекло Фонаря', garden_mark: 'метка сада', sealed_route: 'запечатанный путь',
    };
    const pets = companionState.pets || [];
    const active = pets.find((pet) => pet.active_companion) || pets[0];
    if (!active) {
      container.innerHTML = '<div class="companion-empty">Питомцев пока нет. Первый спутник появится в onboarding Хроники.</div>';
      return;
    }
    const roles = companionState.policy?.roles || [];
    const unlocked = new Set(companionState.unlocked_roles || []);
    const selected = companionState.selected_role_id;
    const progress = active.bond || {};
    const nextBond = progress.next_milestone == null ? 'все основные сцены открыты'
      : `${number(progress.points)} / ${number(progress.next_milestone)}`;
    const petRail = pets.map((pet) => `
      <button type="button" class="pet-chip${pet.active_companion ? ' active' : ''}" data-companion-pet="${pet.id}">
        <i>${species[pet.species_id] || '◌'}</i><span><strong>${esc(pet.name)}</strong><small>стар. ур. ${number(pet.legacy.level)} · Bond ${number(pet.bond.points)}</small></span>
      </button>`).join('');
    const roleCards = roles.map((role) => {
      const owned = unlocked.has(role.id);
      const current = selected === role.id;
      const implemented = role.implemented === true;
      const canUnlock = implemented && (owned || unlocked.size < Number(companionState.role_slots || 1));
      return `<button type="button" class="role-card${current ? ' selected' : ''}${owned ? ' unlocked' : ''}" data-companion-role="${esc(role.id)}" ${canUnlock ? '' : 'disabled'}>
        <i>${esc(role.emoji)}</i><span><strong>${esc(role.name)}</strong><small>${esc(role.decision)}</small><em>− ${esc(role.tradeoff)}</em></span><b>${!implemented ? 'в разработке' : current ? 'выбрано' : owned ? 'сменить' : canUnlock ? 'открыть' : `день ${number(companionState.next_role_day)}`}</b>
      </button>`;
    }).join('');
    const careButtons = (companionState.care_actions || []).map((action) => `
      <button type="button" data-care-action="${esc(action.id)}" ${Number(active.care_bank) > 0 ? '' : 'disabled'}>${esc(action.name)}</button>`).join('');
    const expeditions = (companionState.expeditions?.options || []).map((option) => `
      <button type="button" data-expedition-hours="${number(option.duration_hours)}" ${companionState.expeditions?.start_enabled ? '' : 'disabled'}><i>${number(option.duration_hours)}ч</i><strong>${number(option.projected_mora)} Моры</strong><small>${esc(option.route_name)}</small></button>`).join('');
    const activePetName = new Map(pets.map((pet) => [pet.id, pet.name]));
    const contracts = (companionState.expeditions?.contracts || []).filter((item) => item.status !== 'claimed').map((item) => {
      const status = item.status === 'ready' ? 'Готово' : `ещё ${shortTime(item.remaining_sec)}`;
      return `<span><i>${esc(activePetName.get(item.pet_id) || 'Спутник')}</i><strong>${number(item.duration_hours)}ч · ${esc(status)}</strong><small>${number(item.fixed_mora)} Моры · ${esc(discoveryNames[item.discovery_id] || 'находка')}</small></span>`;
    }).join('');
    container.innerHTML = `
      <section class="companion-hero">
        <div class="companion-mark">${species[active.species_id] || '◌'}</div>
        <div><span>АКТИВНЫЙ СПУТНИК</span><strong>${esc(active.name)}</strong><small>${esc(rarityNames[active.rarity] || active.rarity || 'обычный')} · старый уровень ${number(active.legacy.level)} сохранён</small></div>
        <b>Bond ${nextBond}</b>
      </section>
      <div class="bond-line"><span><b style="width:${Math.min(100, Number(progress.points || 0) / 78 * 100)}%"></b></span><small>открыто сцен: ${number(progress.milestones_reached)}</small></div>
      <div class="pet-rail">${petRail}</div>
      <section class="care-block"><header><span><strong>Забота</strong><small>короткий ритуал без штрафа за пропуск</small></span><b>${number(active.care_bank)} / 7</b></header><div>${careButtons}</div></section>
      <section class="companion-section"><header><span><strong>Атлас ролей</strong><small>${number(unlocked.size)} открыто · ${number(companionState.role_slots)} доступно сейчас</small></span><b>след. ${companionState.next_role_day == null ? 'все' : `${number(companionState.next_role_day)} день`}</b></header><div class="role-list">${roleCards}</div></section>
      <section class="companion-section expedition-preview"><header><span><strong>Поход-разведка</strong><small>${number(companionState.expeditions?.open_slots)} из ${number(companionState.expeditions?.slots)} слотов свободно</small></span><b>тень ${number(companionState.expeditions?.weekly_reserved_mora)} / 600</b></header><div class="expedition-grid">${expeditions}</div>${contracts ? `<div class="expedition-contracts">${contracts}</div>` : ''}${Number(companionState.expeditions?.ready_count) > 0 ? '<button class="claim-expeditions" type="button" data-expedition-claim>Забрать готовые результаты</button>' : ''}<p>${esc(companionState.expeditions?.reason || '')}</p></section>`;
  }

  function refreshMenu() {
    const startButton = document.getElementById('startRunButton');
    const next = progress?.next_step;
    const nextEncounter = encounterById(next?.encounter_id || progress?.current_encounter || state?.encounter_id);
    const resumable = Boolean(
      state && (state.status === 'reward' || (state.status === 'active' && state.wave.elapsed_ms > 0))
    );
    const label = pendingMemory
      ? 'Выбрать Память'
      : next?.type === 'choose_chronicle_path' ? 'Выбрать тропу'
      : resumable ? 'Продолжить забег'
        : state?.status === 'active' ? 'Начать забег'
          : next?.type === 'development_gate' ? 'Тренировка'
            : next?.type === 'play_encounter' && next.encounter_id !== 'e01_two_bells' ? 'Начать встречу'
              : state ? 'Новый забег' : 'Начать первый забег';
    startButton.innerHTML = `${label} <span>›</span>`;
    const menu = pendingMemory ? {
      eyebrow: 'ПОСЛЕ ПЕРВОЙ ПОБЕДЫ', title: 'Сохрани одну Память',
      copy: 'Выбери постоянный стиль игры. Валюта не тратится, второй вариант выбрать нельзя.',
      waves: '1', time: 'выбор', goal: 'навсегда', note: 'Решение',
      noteCopy: 'У каждой Памяти есть преимущество и честное ограничение.',
    } : next?.type === 'choose_chronicle_path' ? {
      eyebrow: 'ХРОНИКА · РАЗВИЛКА', title: next.title,
      copy: next.description, waves: '2', time: 'тропы', goal: '1', note: 'Навсегда',
      noteCopy: 'Выбранная тропа меняет порядок обучения, но не продаёт силу и не закрывает историю.',
    } : next?.type === 'development_gate' ? {
      eyebrow: 'ГРАНИЦА ТЕКУЩЕГО MVP', title: next.title,
      copy: next.description, waves: '2', time: 'пройдено', goal: '0', note: 'Без наград',
      noteCopy: 'Тренировка не меняет экономику и нужна для проверки сборок.',
    } : nextEncounter?.id === 'e02_shattered_causeway' ? {
      eyebrow: 'ХРОНИКА · ВСТРЕЧА 2', title: nextEncounter.name,
      copy: nextEncounter.objective.description, waves: '3', time: '≈ 2 мин', goal: '≥ 75%',
      note: 'Фонарь', noteCopy: 'Ошибка гасит свет. Серия из пяти точных знаков восстанавливает его.',
    } : nextEncounter?.id === 'e03_ink_path' ? {
      eyebrow: 'ХРОНИКА · ТРОПА ЧЕРНИЛ', title: nextEncounter.name,
      copy: nextEncounter.objective.description, waves: '3', time: '≈ 3 мин', goal: 'ясность',
      note: 'Отражение', noteCopy: 'Ложный знак появляется раньше. Нажимай только после открытия настоящего.',
    } : nextEncounter?.id === 'e03_ash_path' ? {
      eyebrow: 'ХРОНИКА · ТРОПА ПЕПЛА', title: nextEncounter.name,
      copy: nextEncounter.objective.description, waves: '3', time: '≈ 3 мин', goal: 'огонь',
      note: 'Костёр', noteCopy: 'Огонь медленно гаснет. Поздний золотой ответ возвращает больше жара.',
    } : nextEncounter?.id === 'e04_drowned_names' ? {
      eyebrow: 'ХРОНИКА · ВСТРЕЧА 4', title: nextEncounter.name,
      copy: nextEncounter.objective.description, waves: '3', time: '≈ 2 мин', goal: 'память',
      note: 'Порядок', noteCopy: 'Сначала запомни всю цепочку. Во время ответа центральная подсказка исчезает.',
    } : nextEncounter?.id === 'e05_mirror_courtyard' ? {
      eyebrow: 'ХРОНИКА · ВСТРЕЧА 5', title: nextEncounter.name,
      copy: nextEncounter.objective.description, waves: '3', time: '≈ 2 мин', goal: 'позиции',
      note: 'Запрет', noteCopy: 'Последняя точная позиция отмечается. Правильный знак всегда будет в другом месте.',
    } : nextEncounter?.id === 'e06_archivist' ? {
      eyebrow: 'ХРОНИКА · ФИНАЛ ГЛАВЫ', title: nextEncounter.name,
      copy: nextEncounter.objective.description, waves: '3', time: '≈ 3 мин', goal: '3 правила',
      note: 'Босс', noteCopy: 'Запись, Прилив и Последнее имя проверяют разные навыки в одном забеге.',
    } : {
      eyebrow: 'ХРОНИКА · ВСТРЕЧА 1', title: nextEncounter?.name || 'Разлом колокола',
      copy: nextEncounter?.objective?.description || 'Три короткие волны. Смотри на знак в центре и находи такой же среди трёх рун.',
      waves: '3', time: '≈ 1 мин', goal: '1', note: 'Важно',
      noteCopy: 'Скорость кликов не даёт преимущество. Побеждает правильный выбор руны.',
    };
    document.getElementById('menuEyebrow').textContent = menu.eyebrow;
    document.getElementById('menuTitle').textContent = menu.title;
    document.getElementById('menuCopy').textContent = menu.copy;
    document.getElementById('menuFactWaves').textContent = menu.waves;
    document.getElementById('menuFactTime').textContent = menu.time;
    document.getElementById('menuFactGoal').textContent = menu.goal;
    document.getElementById('menuNoteLabel').textContent = menu.note;
    document.getElementById('menuNoteCopy').textContent = menu.noteCopy;
    document.getElementById('newRunButton').hidden = !resumable;
    document.getElementById('versionBadge').textContent = manifest?.game_version?.replace('3.0.0-', '') || 'MVP';
    renderCareer();
    renderUnitProgress();
  }

  function render() {
    if (!state) return;
    const wave = state.wave;
    const challenge = state.challenge;
    const objective = state.objective_state || {};
    const hpPercent = wave.hp_max ? wave.hp / wave.hp_max * 100 : 0;
    const chargePercent = state.team.charge / state.team.charge_max * 100;
    const seconds = Math.max(0, wave.time_left_ms / 1000).toFixed(1).replace('.', ',');
    const signalActive = Boolean(challenge?.active);
    document.getElementById('waveLabel').textContent = `ВОЛНА ${state.round} ИЗ ${state.waves_total}`;
    document.getElementById('bossName').textContent = wave.name;
    document.getElementById('bossSubtitle').textContent = wave.subtitle;
    const reflection = objective.kind === 'ink_decipher' ? objective.reflection_cue : null;
    const sequence = objective.kind === 'drowned_sequence';
    const archivist = objective.kind === 'archivist_boss';
    const sequenceMode = sequence || (archivist && ['preview', 'recall'].includes(objective.phase));
    const sequencePreview = sequenceMode && objective.phase === 'preview';
    document.getElementById('bossGlyph').textContent = sequencePreview
      ? (objective.preview_symbol || '·')
      : signalActive ? (sequenceMode ? '⌁' : challenge.target_symbol)
        : reflection?.symbol || wave.emoji;
    document.getElementById('roundClock').innerHTML = `<strong>${seconds}</strong><span>сек</span>`;
    document.getElementById('roundClock').classList.toggle('urgent', wave.time_left_ms <= 5000);
    document.getElementById('bossHealthFill').style.transform = `scaleX(${Math.max(0, Math.min(1, hpPercent / 100))})`;
    document.getElementById('bossHealthValue').textContent = `${number(wave.hp)} / ${number(wave.hp_max)}`;
    document.getElementById('bossHealth').setAttribute('aria-valuemax', String(Math.round(wave.hp_max)));
    document.getElementById('bossHealth').setAttribute('aria-valuenow', String(Math.round(wave.hp)));
    const objectiveMeter = document.getElementById('objectiveMeter');
    const objectiveConfig = {
      lantern_escort: ['ФОНАРЬ', 'lantern_integrity', 'lantern_integrity_max', '', 'percent'],
      ink_decipher: ['ЯСНОСТЬ', 'clarity', 'clarity_max', 'ink', 'percent'],
      ash_fire: ['ОГОНЬ', 'fire_integrity', 'fire_integrity_max', 'ash', 'percent'],
      drowned_sequence: ['ЯКОРИ', 'anchors_broken', 'anchors_total', 'memory', 'fraction'],
      mirror_rule: ['ПЕЧАТИ', 'wards', 'wards_max', 'mirror', 'fraction'],
      archivist_boss: ['ФАЗЫ', 'phases_completed', 'phases_total', 'boss', 'fraction'],
    }[objective.kind];
    objectiveMeter.hidden = !objectiveConfig;
    objectiveMeter.className = `objective-meter${objectiveConfig?.[3] ? ` ${objectiveConfig[3]}` : ''}`;
    if (objectiveConfig) {
      const [label, valueKey, maxKey, , format] = objectiveConfig;
      const max = Math.max(1, Number(objective[maxKey]) || 100);
      const value = Math.max(0, Math.min(max, Number(objective[valueKey]) || 0));
      document.getElementById('objectiveLabel').textContent = label;
      document.getElementById('objectiveValue').textContent = format === 'fraction'
        ? `${number(value)}/${number(max)}` : `${number(value)}%`;
      document.getElementById('objectiveFill').style.transform = `scaleX(${value / max})`;
      objectiveMeter.setAttribute('aria-label', format === 'fraction'
        ? `${label} ${number(value)} из ${number(max)}` : `${label} ${number(value)} процентов`);
    }
    core.style.setProperty('--charge', `${Math.min(360, chargePercent * 3.6)}deg`);
    document.getElementById('comboValue').textContent = `×${state.combo.count}`;
    document.getElementById('accuracyValue').textContent = percent(state.accuracy);
    document.getElementById('tapPowerValue').textContent = number(state.team.tap_power);
    document.getElementById('chargeValue').textContent = `${Math.floor(chargePercent)}%`;
    document.getElementById('lastLog').textContent = state.log[state.log.length - 1] || state.last_event.label;
    document.getElementById('windowProgress').style.transform = `scaleX(${Math.max(0, Math.min(1, state.signal_progress))})`;
    stage.classList.toggle('signal', signalActive);
    stage.classList.toggle('golden', state.critical_active);
    stage.classList.toggle('memory-preview', sequencePreview);
    const indicator = document.getElementById('windowIndicator').querySelector('span');
    const timerHidden = Boolean(state.branch_state?.hide_signal_timer && signalActive);
    document.getElementById('windowIndicator').classList.toggle('timer-hidden', timerHidden);
    const mirror = objective.kind === 'mirror_rule';
    const forbiddenSlot = mirror ? objective.forbidden_slot
      : archivist && objective.phase === 'record' ? objective.recorded_slot : null;
    const tideWindow = archivist && objective.phase === 'tide' ? objective.tide_window : null;
    const slotNames = {left: 'левая',center: 'средняя',right: 'правая'};
    indicator.textContent = sequencePreview
      ? `Запомни · ${Math.max(1, Number(objective.preview_index) + 1)} из ${number(objective.sequence_length)}`
      : sequenceMode && signalActive
        ? `Повтори · знак ${number(Number(objective.answer_index) + 1)} из ${number(objective.sequence_length)}`
      : (mirror || archivist) && signalActive && forbiddenSlot
        ? `Запрет: ${slotNames[forbiddenSlot] || forbiddenSlot} позиция`
      : tideWindow
        ? `${tideWindow === 'short' ? 'Короткое' : 'Длинное'} окно объявлено заранее`
      : timerHidden ? 'Течение скрывает остаток окна'
      : state.critical_active
      ? '✦ ЗОЛОТОЕ ОКНО · БОНУС ЗА МОМЕНТ'
      : signalActive ? 'Выбери совпадающую руну' : 'Сигнал приближается';
    const family = state.branch_state?.family_preview;
    document.getElementById('corePrompt').textContent = sequencePreview ? 'ЗАПОМНИ'
      : sequenceMode && signalActive ? 'ПОВТОРИ'
      : (mirror || archivist) && signalActive && forbiddenSlot ? 'СМЕНИ ПОЗИЦИЮ'
      : tideWindow && signalActive ? (tideWindow === 'short' ? 'КОРОТКО' : 'ДЛИННО')
      : reflection ? 'ОТРАЖЕНИЕ' : family ? 'КАРТА' : signalActive ? 'НАЙДИ ЗНАК' : 'СЛУШАЙ';
    document.getElementById('coreHint').textContent = sequencePreview ? 'ответ появится после всей цепочки'
      : sequenceMode && signalActive ? 'центральной подсказки больше нет'
      : (mirror || archivist) && signalActive && forbiddenSlot ? 'запрет отмечен на рунах'
      : tideWindow && signalActive ? 'длина окна известна до сигнала'
      : reflection ? 'не нажимай · дождись настоящего' : family ? `семейство: ${family}` : signalActive ? 'одна попытка на сигнал' : 'затем найди такой же знак';
    core.setAttribute('aria-label', sequencePreview && objective.preview_symbol
      ? `Запомни руну ${objective.preview_symbol}`
      : sequenceMode && signalActive ? `Повтори знак ${Number(objective.answer_index) + 1}`
        : signalActive ? `Найди руну ${challenge.target_symbol}` : 'Ожидание следующей руны');
    renderRunes();
    renderBranchControls();
    renderRail();
    renderSquad();
    renderBuild();
    renderChoice();
    renderBranchDecision();
    renderResult();
    animateEvent(state.last_event);
    refreshMenu();
  }

  function selectMenuTab(tab, persist = true) {
    currentMenuTab = tab;
    document.querySelectorAll('[data-menu-tab]').forEach((button) => {
      button.classList.toggle('active', button.dataset.menuTab === tab);
    });
    document.querySelectorAll('[data-menu-panel]').forEach((panel) => {
      const active = panel.dataset.menuPanel === tab;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
    });
    if (tab === 'stats') renderCareer();
    if (tab === 'companion') renderCompanions();
    if (persist && currentView === 'menu') saveUiState();
  }

  function openMenu(tab = 'play') {
    playing = false;
    pendingStrike = null;
    showOnly('menu', tab);
    refreshMenu();
    renderRunes();
  }

  function closeMenuAndPlay() {
    showOnly('battle');
    if (state.status === 'reward') {
      playing = false;
      render();
      return;
    }
    playing = state.status === 'active';
    if (playing) {
      recordRunStarted();
      lastFrameAt = performance.now();
    }
    render();
  }

  function openPause() {
    if (!state || ['won', 'lost'].includes(state.status)) {
      openMenu('play');
      return;
    }
    playing = false;
    pendingStrike = null;
    showOnly('pause');
    renderRunes();
  }

  function continueRun() {
    showOnly('battle');
    if (state.status === 'reward') {
      render();
      return;
    }
    playing = state.status === 'active';
    lastFrameAt = performance.now();
    render();
  }

  function queueStrike(slot, event) {
    if (!playing || !state?.challenge?.active || pendingStrike) return;
    event?.preventDefault?.();
    const button = orbit.querySelector(`[data-target-slot="${slot}"]`);
    const bounds = button?.getBoundingClientRect();
    pendingStrike = { slot, challengeId: state.challenge.id };
    spawnImpact(
      event?.clientX || (bounds ? bounds.left + bounds.width / 2 : window.innerWidth / 2),
      event?.clientY || (bounds ? bounds.top + bounds.height / 2 : window.innerHeight / 2),
      button?.textContent || '·', state.critical_active,
    );
    renderRunes();
    haptic('light');
  }

  function nextActionId() {
    actionSequence += 1;
    const nonce = globalThis.crypto?.randomUUID?.()
      || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    return `web:${actionSequence}:${nonce}`.slice(0, 96);
  }

  async function submitAction(payload) {
    if (!production) {
      return jsonFetch('/action', {
        method: 'POST', body: JSON.stringify(payload),
      });
    }
    if (!runId) throw new Error('Нет активного забега.');
    const expectedRevision = Number(state?.revision);
    if (!Number.isInteger(expectedRevision) || expectedRevision < 0) {
      throw new Error('Серверная версия забега недоступна. Обнови игру.');
    }
    let data;
    try {
      data = await jsonFetch(`/runs/${runId}/actions`, {
        method: 'POST',
        body: JSON.stringify({
          action_id: nextActionId(),
          expected_revision: expectedRevision,
          ...payload,
        }),
      });
    } catch (error) {
      if (error.status === 409) {
        await resyncAfterConflict(error.message);
        error.resynced = true;
      }
      throw error;
    }
    if (data.career_stats) applyCareerStats(data.career_stats);
    if (data.pending_memory) {
      pendingMemory = data.pending_memory;
      progress = {
        ...(progress || {}),
        completed: [...new Set([
          ...(progress?.completed || []),
          data.pending_memory.encounter_id,
        ])],
      };
    }
    if (data.next_step) progress = { ...(progress || {}), next_step: data.next_step };
    if (Array.isArray(data.mastery_proofs)) {
      const proofs = new Set(data.mastery_proofs);
      units = units.map((unit) => ({
        ...unit,
        proven_challenges: [...new Set([
          ...(unit.proven_challenges || []),
          ...unitBranches(unit.unit_id)
            .map((branch) => branch.mastery_challenge)
            .filter((challenge) => proofs.has(challenge)),
        ])],
      }));
    }
    return { state: data, turn: data.turn, rejected: false };
  }

  async function startRun() {
    if (!production) {
      const encounterId = state?.status === 'won' && state.encounter_id === 'e01_two_bells'
        ? 'e02_shattered_causeway'
        : state?.encounter_id || 'e01_two_bells';
      return jsonFetch('/reset', {
        method: 'POST', body: JSON.stringify({
          encounter_id: encounterId,
          unit_branches: state?.unit_branches || {},
          companion_role_id: companionState?.selected_role_id || null,
        }),
      });
    }
    const next = progress?.next_step;
    const gate = next?.type === 'development_gate';
    const encounterId = gate
      ? next.practice_encounter_id
      : next?.encounter_id || progress?.current_encounter || 'e01_two_bells';
    const practice = Boolean(gate || next?.practice);
    const data = await jsonFetch('/start', {
      method: 'POST',
      body: JSON.stringify({ encounter_id: encounterId, practice }),
    });
    runId = data.run_id;
    if (data.career_stats) applyCareerStats(data.career_stats);
    return data;
  }

  async function cancelRunIfActive() {
    if (!production || !runId || ['won', 'lost'].includes(state?.status)) return;
    await jsonFetch(`/runs/${runId}/cancel`, { method: 'POST', body: '{}' });
    runId = null;
    state = null;
  }

  async function chooseMemory(memoryId) {
    if (!production || busy) return;
    busy = true;
    try {
      const chosen = await jsonFetch('/memory', {
        method: 'POST', body: JSON.stringify({ memory_id: memoryId }),
      });
      pendingMemory = null;
      progress = {
        ...(progress || {}),
        memories: [...new Set([...(progress?.memories || []), memoryId])],
        next_step: chosen.next_step || progress?.next_step,
      };
      haptic('medium');
      notify('Память сохранена в профиле');
      if (state && ['won', 'lost'].includes(state.status)) {
        showOnly('result');
        renderResult();
      }
      else showOnly('menu', 'play');
      refreshMenu();
    } catch (error) {
      notify(error.message, true);
    } finally {
      busy = false;
    }
  }

  async function chooseUnitBranch(unitId, branchId) {
    if (!production || busy) return;
    busy = true;
    try {
      const selected = await jsonFetch('/units/branch', {
        method: 'POST', body: JSON.stringify({ unit_id: unitId, branch_id: branchId }),
      });
      units = units.map((unit) => unit.unit_id === unitId
        ? { ...unit, ...selected.progress }
        : unit);
      haptic('medium');
      notify('Ветвь мастерства сохранена');
      showOnly('menu', 'play');
      refreshMenu();
    } catch (error) {
      notify(error.message, true);
    } finally {
      busy = false;
    }
  }

  async function chooseChroniclePath(pathId) {
    if (!production || busy) return;
    busy = true;
    try {
      const selected = await jsonFetch('/chronicle/path', {
        method: 'POST', body: JSON.stringify({ path_id: pathId }),
      });
      progress = {
        ...(progress || {}),
        current_encounter: selected.encounter_id,
        route_choices: { ...(progress?.route_choices || {}), chapter_1: pathId },
        next_step: selected.next_step,
      };
      haptic('medium');
      notify('Тропа Хроники сохранена');
      if (state && ['won', 'lost'].includes(state.status)) {
        showOnly('result');
        renderResult();
      } else {
        showOnly('menu', 'play');
        refreshMenu();
      }
    } catch (error) {
      notify(error.message, true);
    } finally {
      busy = false;
    }
  }

  async function sendCombatBranchAction(command, extra = {}) {
    if (!state) return;
    if (busy) {
      if (!branchActionInFlight && !pendingBranchAction) pendingBranchAction = { command, extra };
      return;
    }
    busy = true;
    branchActionInFlight = true;
    const resolvingDecision = Boolean(state.branch_state?.decision);
    try {
      const data = await submitAction({ type: 'branch_action', command, ...extra });
      state = data.state;
      pendingStrike = null;
      if (resolvingDecision) {
        showOnly('battle');
        playing = state.status === 'active';
        lastFrameAt = performance.now();
      }
      render();
      haptic('medium');
    } catch (error) {
      if (!error.resynced) notify(error.message, true);
    } finally {
      branchActionInFlight = false;
      busy = false;
      flushPendingBranchAction();
    }
  }

  function flushPendingBranchAction() {
    if (busy || !pendingBranchAction) return;
    const queued = pendingBranchAction;
    pendingBranchAction = null;
    sendCombatBranchAction(queued.command, queued.extra);
  }

  async function sendFrame() {
    if (busy || !playing || !state || state.status !== 'active') return;
    const now = performance.now();
    const delta = Math.max(40, Math.min(250, Math.round(now - lastFrameAt)));
    lastFrameAt = now;
    const strike = pendingStrike;
    pendingStrike = null;
    const payload = { type: 'frame', delta_ms: delta };
    if (strike) {
      payload.target_slot = strike.slot;
      payload.challenge_id = strike.challengeId;
    }
    busy = true;
    try {
      const data = await submitAction(payload);
      state = data.state;
      if (data.rejected) pendingStrike = null;
      // Ответ уже отправленного кадра может прийти после нажатия «Пауза».
      // Состояние сервера принимаем, но замороженный экран не перерисовываем
      // до явного продолжения — иначе таймер визуально дёргается под модалкой.
      if (playing) render();
    } catch (error) {
      if (strike && !error.resynced) pendingStrike = strike;
      if (!error.resynced) notify(error.message, true);
    } finally {
      busy = false;
      flushPendingBranchAction();
    }
  }

  async function chooseUpgrade(upgradeId) {
    if (busy) return;
    busy = true;
    try {
      const data = await submitAction({ type: 'choose_upgrade', upgrade_id: upgradeId });
      state = data.state;
      pendingStrike = null;
      lastFrameAt = performance.now();
      showOnly('battle');
      playing = true;
      render();
      haptic('medium');
    } catch (error) {
      if (!error.resynced) notify(error.message, true);
    } finally {
      busy = false;
    }
  }

  async function reset(playAfter = true) {
    if (busy) return;
    busy = true;
    playing = false;
    try {
      await cancelRunIfActive();
      state = await startRun();
      pendingStrike = null;
      lastFrameAt = performance.now();
      lastEventId = state.last_event?.id || 0;
      if (playAfter) {
        showOnly('battle');
        recordRunStarted();
        playing = true;
      } else {
        showOnly('menu', 'play');
      }
      render();
    } catch (error) {
      notify(error.message, true);
    } finally {
      busy = false;
    }
  }

  async function startFromMenu() {
    if (pendingMemory && showMemoryChoice()) return;
    if (progress?.next_step?.type === 'choose_chronicle_path' && showChroniclePathChoice()) return;
    const selectedCompanion = companionState?.selected_role_id || null;
    const untouchedRun = state?.status === 'active' && Number(state?.wave?.elapsed_ms || 0) === 0;
    const companionChanged = !production && untouchedRun
      && (state?.companion_role_id || null) !== selectedCompanion;
    if (!state || ['won', 'lost'].includes(state.status) || companionChanged) {
      await reset(true);
      return;
    }
    closeMenuAndPlay();
  }

  orbit.addEventListener('pointerdown', (event) => {
    const button = event.target.closest('[data-target-slot]');
    if (button) queueStrike(button.dataset.targetSlot, event);
  });
  document.addEventListener('keydown', (event) => {
    const slots = { Digit1: 'left', Digit2: 'center', Digit3: 'right' };
    if (slots[event.code] && !event.repeat) queueStrike(slots[event.code], event);
    if (event.code === 'Escape' && !event.repeat) {
      if (!pauseLayer.hidden) continueRun();
      else if (menuLayer.hidden && resultLayer.hidden) openPause();
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && playing) openPause();
  });
  document.getElementById('upgradeList').addEventListener('click', (event) => {
    const chroniclePath = event.target.closest('[data-chronicle-path]');
    if (chroniclePath) {
      chooseChroniclePath(chroniclePath.dataset.chroniclePath);
      return;
    }
    const combatBranch = event.target.closest('[data-combat-command]');
    if (combatBranch) {
      sendCombatBranchAction(combatBranch.dataset.combatCommand, {
        decision_id: combatBranch.dataset.decisionId,
      });
      return;
    }
    const branch = event.target.closest('[data-unit-branch]');
    if (branch) {
      chooseUnitBranch(branch.dataset.unitId, branch.dataset.unitBranch);
      return;
    }
    const memory = event.target.closest('[data-memory-id]');
    if (memory) {
      chooseMemory(memory.dataset.memoryId);
      return;
    }
    const card = event.target.closest('[data-upgrade-id]');
    if (card) chooseUpgrade(card.dataset.upgradeId);
  });
  document.getElementById('unitProgress').addEventListener('click', (event) => {
    const card = event.target.closest('[data-unit-progress]');
    if (card) showUnitBranchChoice(card.dataset.unitProgress);
  });
  document.getElementById('companionPanel').addEventListener('click', async (event) => {
    const pet = event.target.closest('[data-companion-pet]');
    const role = event.target.closest('[data-companion-role]');
    const care = event.target.closest('[data-care-action]');
    const expedition = event.target.closest('[data-expedition-hours]');
    const claim = event.target.closest('[data-expedition-claim]');
    if (!pet && !role && !care && !expedition && !claim) return;
    try {
      if (pet) companionState = await jsonFetch('/companions/active', {
        method: 'POST', body: JSON.stringify({ pet_id: Number(pet.dataset.companionPet) }),
      });
      if (role) companionState = await jsonFetch('/companions/role', {
        method: 'POST', body: JSON.stringify({ role_id: role.dataset.companionRole }),
      });
      if (care) {
        const active = companionState?.pets?.find((item) => item.active_companion);
        await jsonFetch('/companions/care', {
          method: 'POST', body: JSON.stringify({
            pet_id: Number(active?.id), action: care.dataset.careAction,
            action_id: globalThis.crypto?.randomUUID?.() || `care-${Date.now()}`,
          }),
        });
        companionState = await jsonFetch('/companions');
        notify('Bond вырос. Валюта и сила не изменились.');
      }
      if (expedition) {
        const active = companionState?.pets?.find((item) => item.active_companion);
        await jsonFetch('/companions/expeditions/start', {
          method: 'POST', body: JSON.stringify({
            pet_id: Number(active?.id), duration_hours: Number(expedition.dataset.expeditionHours),
            action_id: globalThis.crypto?.randomUUID?.() || `expedition-${Date.now()}`,
          }),
        });
        companionState = await jsonFetch('/companions');
        notify('Результат похода зафиксирован. В DEV часы сжаты до секунд.');
      }
      if (claim) {
        const result = await jsonFetch('/companions/expeditions/claim', {
          method: 'POST', body: JSON.stringify({
            action_id: globalThis.crypto?.randomUUID?.() || `claim-${Date.now()}`,
          }),
        });
        companionState = await jsonFetch('/companions');
        notify(`Теневой итог: ${number(result.projected_mora_total)} Моры. Кошелёк не изменён.`);
      }
      renderCompanions();
    } catch (error) {
      notify(error.message, true);
    }
  });
  document.getElementById('branchControls').addEventListener('click', (event) => {
    const control = event.target.closest('[data-combat-command]');
    if (!control) return;
    const extra = control.dataset.enabled === undefined
      ? {}
      : { enabled: control.dataset.enabled === 'true' };
    sendCombatBranchAction(control.dataset.combatCommand, extra);
  });
  document.querySelector('.menu-tabs').addEventListener('click', (event) => {
    const button = event.target.closest('[data-menu-tab]');
    if (button) selectMenuTab(button.dataset.menuTab);
  });
  document.getElementById('menuButton').addEventListener('click', openPause);
  document.getElementById('startRunButton').addEventListener('click', startFromMenu);
  document.getElementById('newRunButton').addEventListener('click', () => reset(true));
  document.getElementById('continueButton').addEventListener('click', continueRun);
  document.getElementById('pauseMenuButton').addEventListener('click', () => openMenu('play'));
  document.getElementById('restartButton').addEventListener('click', () => reset(true));
  document.getElementById('resultReset').addEventListener('click', () => {
    if (pendingMemory && showMemoryChoice()) return;
    if (progress?.next_step?.type === 'choose_chronicle_path' && showChroniclePathChoice()) return;
    reset(true);
  });
  document.getElementById('resultMenu').addEventListener('click', () => openMenu('stats'));
  document.getElementById('copyResult').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(resultSummary());
      notify('Итог забега скопирован');
    } catch (_) {
      notify('Не удалось открыть буфер обмена', true);
    }
  });

  try {
    window.Telegram?.WebApp?.ready?.();
    window.Telegram?.WebApp?.expand?.();
  } catch (_) { /* optional */ }
  setTesterIdentity();

  const bootstrap = production
    ? Promise.all([jsonFetch(''), jsonFetch('/companions')]).then(([overview, companionData]) => {
      manifest = overview.content;
      progress = overview.progress;
      units = overview.units || [];
      pendingMemory = overview.progress?.pending_memory || null;
      state = overview.active_run || null;
      runId = state?.run_id || null;
      applyCareerStats(overview.stats);
      companionState = companionData;
    })
    : Promise.all([jsonFetch('/manifest'), jsonFetch('/state'), jsonFetch('/companions')]).then(([manifestData, stateData, companionData]) => {
      manifest = manifestData;
      state = stateData;
      companionState = companionData;
      units = (manifest.starter_units || []).map((unit) => ({
        unit_id: unit.id, short_name: unit.short_name, name: unit.name, emoji: unit.emoji,
        level: 1, total_xp: 0, xp_in_level: 0, xp_to_next: 120,
        branch_choices: {}, next_branch_level: 5, proven_challenges: [],
      }));
    });

  bootstrap
    .then(() => {
      lastEventId = state?.last_event?.id || 0;
      const desired = savedUiState();
      if (pendingMemory && !state) {
        showMemoryChoice();
      } else if (!state) {
        showOnly('menu', desired.tab, false);
      } else if (state.status === 'reward') {
        showOnly(desired.view === 'menu' ? 'menu' : 'choice', desired.tab, false);
      } else if (['won', 'lost'].includes(state.status)) {
        showOnly(desired.view === 'menu' ? 'menu' : 'result', desired.tab, false);
      } else if (desired.view === 'battle' && state.wave.elapsed_ms > 0) {
        showOnly('battle', desired.tab, false);
        playing = true;
      } else if (desired.view === 'pause' && state.wave.elapsed_ms > 0) {
        showOnly('pause', desired.tab, false);
      } else {
        showOnly('menu', desired.tab, false);
      }
      render();
      refreshMenu();
      saveUiState();
      lastFrameAt = performance.now();
      setInterval(sendFrame, FRAME_MS);
      setInterval(async () => {
        if (currentView !== 'menu' || currentMenuTab !== 'companion') return;
        try {
          companionState = await jsonFetch('/companions');
          renderCompanions();
        } catch (_) { /* следующий ручной запрос покажет ошибку */ }
      }, 2000);
    })
    .catch((error) => notify(error.message, true));

  if (!production) {
    const source = new EventSource('/__preview/live');
    let connected = false;
    source.addEventListener('open', () => {
      if (connected) location.reload();
      connected = true;
    });
    source.addEventListener('reload', () => location.reload());
  }
})();
