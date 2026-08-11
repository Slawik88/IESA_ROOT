(() => {
  'use strict';

  const API = '/__reconstruction';
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
  let lastFrameAt = performance.now();
  let lastEventId = 0;
  let toastTimer = null;

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
  const runKey = () => state ? `${state.game_version}:${state.seed}` : '';
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function saveCareer() {
    career.startedRunKeys = [...new Set(career.startedRunKeys)].slice(-40);
    career.completedRunKeys = [...new Set(career.completedRunKeys)].slice(-40);
    try { localStorage.setItem(STATS_STORAGE_KEY, JSON.stringify(career)); } catch (_) { /* optional */ }
  }

  function savedUiState() {
    try {
      const value = JSON.parse(sessionStorage.getItem(UI_STORAGE_KEY) || '{}');
      return {
        view: ['menu', 'battle', 'pause', 'choice', 'result'].includes(value.view) ? value.view : null,
        tab: ['play', 'stats', 'help'].includes(value.tab) ? value.tab : 'play',
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
    const key = runKey();
    if (!key || career.startedRunKeys.includes(key)) return;
    career.startedRunKeys.push(key);
    career.runsStarted += 1;
    saveCareer();
  }

  function recordRunCompleted() {
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
          'x-reconstruction-session': previewSession,
          ...(options.headers || {}),
        },
      });
      data = await response.json().catch(() => ({}));
      if (response.status !== 503 || attempt === 2) break;
      await wait(180 * (attempt + 1));
    }
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    return data;
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
    container.hidden = false;
    container.innerHTML = selected.length ? selected.map((upgrade) => `
      <span><i>${esc(upgrade.emoji)}</i><b>${esc(upgrade.name)}</b><small>${esc(upgrade.archetype)}</small></span>`).join('')
      : '<span class="empty-build"><i>＋</i><b>Сборка</b><small>усиление после волны</small></span>';
  }

  function renderRunes() {
    const challenge = state.challenge;
    const options = new Map((challenge?.options || []).map((option) => [option.slot, option.symbol]));
    orbit.querySelectorAll('[data-target-slot]').forEach((button) => {
      const symbol = options.get(button.dataset.targetSlot) || '·';
      button.textContent = symbol;
      button.disabled = !playing || !challenge?.active || Boolean(pendingStrike);
      button.setAttribute('aria-label', `${button.dataset.targetSlot}: руна ${symbol}`);
    });
  }

  function renderChoice() {
    if (state.status !== 'reward' || ['menu', 'pause', 'result'].includes(currentView)) return;
    playing = false;
    document.getElementById('upgradeList').innerHTML = state.reward_options.map((upgrade) => `
      <button class="upgrade-card" type="button" data-upgrade-id="${esc(upgrade.id)}">
        <span>${esc(upgrade.emoji)}</span>
        <span class="upgrade-copy"><em>${esc(upgrade.archetype)}</em><strong>${esc(upgrade.name)}</strong><small>${esc(upgrade.description)}</small><small class="tradeoff">− ${esc(upgrade.tradeoff)}</small></span>
        <b>›</b>
      </button>`).join('');
    showOnly('choice');
  }

  function resultSummary() {
    const outcome = state.status === 'won' ? 'Победа' : 'Поражение';
    return `${outcome} в «Разломе колокола»: точность ${percent(state.accuracy)}, серия ${state.combo.max}, ошибок ${state.mastery.mistakes}, время ${Math.round(state.mastery.elapsed_ms / 1000)} с.`;
  }

  function renderResult() {
    if (!['won', 'lost'].includes(state.status) || ['menu', 'pause'].includes(currentView)) return;
    playing = false;
    recordRunCompleted();
    const won = state.status === 'won';
    document.getElementById('resultMark').textContent = won ? '✦' : '◌';
    document.getElementById('resultTitle').textContent = won ? 'Колокол отвечает тебе' : 'Эхо погасло';
    document.getElementById('resultCopy').textContent = won
      ? 'Три волны пройдены точностью, а выбранные усиления сложились в полноценную сборку.'
      : 'Посмотри на знак в центре и выбирай его отражение. Частота нажатий не заменяет точность.';
    document.getElementById('resultStats').innerHTML = [
      [state.mastery.correct_taps, 'точных'],
      [percent(state.accuracy), 'точность'],
      [state.combo.max, 'макс. серия'],
      [state.mastery.discharges, 'разрядов'],
      [state.mastery.mistakes, 'ошибок'],
      [`${Math.round(state.mastery.elapsed_ms / 1000)}с`, 'время'],
    ].map(([value, label]) => `<span><strong>${esc(value)}</strong>${esc(label)}</span>`).join('');
    showOnly('result');
  }

  function renderCareer() {
    const attempts = (Number(career.correctTaps) || 0) + (Number(career.mistakes) || 0) + (Number(career.missedSignals) || 0);
    const accuracy = attempts ? Math.round(career.correctTaps / attempts * 1000) / 10 : null;
    const fastest = career.fastestWinMs === null ? '—' : `${Math.round(career.fastestWinMs / 1000)}с`;
    document.getElementById('careerStats').innerHTML = [
      [career.runsStarted, 'забегов'],
      [career.runsWon, 'побед'],
      [percent(accuracy), 'точность'],
      [career.bestCombo, 'лучшая серия'],
      [fastest, 'быстрая победа'],
      [career.mistakes, 'ошибок'],
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

  function refreshMenu() {
    if (!state) return;
    const resumable = state.status === 'reward' || (state.status === 'active' && state.wave.elapsed_ms > 0);
    const startButton = document.getElementById('startRunButton');
    startButton.innerHTML = `${resumable ? 'Продолжить забег' : state.status === 'active' ? 'Начать забег' : 'Новый забег'} <span>›</span>`;
    document.getElementById('newRunButton').hidden = !resumable;
    document.getElementById('versionBadge').textContent = manifest?.game_version?.replace('3.0.0-', '') || 'MVP';
    renderCareer();
  }

  function render() {
    if (!state) return;
    const wave = state.wave;
    const challenge = state.challenge;
    const hpPercent = wave.hp_max ? wave.hp / wave.hp_max * 100 : 0;
    const chargePercent = state.team.charge / state.team.charge_max * 100;
    const seconds = Math.max(0, wave.time_left_ms / 1000).toFixed(1).replace('.', ',');
    const signalActive = Boolean(challenge?.active);
    document.getElementById('waveLabel').textContent = `ВОЛНА ${state.round} ИЗ ${state.waves_total}`;
    document.getElementById('bossName').textContent = wave.name;
    document.getElementById('bossSubtitle').textContent = wave.subtitle;
    document.getElementById('bossGlyph').textContent = signalActive ? challenge.target_symbol : wave.emoji;
    document.getElementById('roundClock').innerHTML = `<strong>${seconds}</strong><span>сек</span>`;
    document.getElementById('roundClock').classList.toggle('urgent', wave.time_left_ms <= 5000);
    document.getElementById('bossHealthFill').style.transform = `scaleX(${Math.max(0, Math.min(1, hpPercent / 100))})`;
    document.getElementById('bossHealthValue').textContent = `${number(wave.hp)} / ${number(wave.hp_max)}`;
    document.getElementById('bossHealth').setAttribute('aria-valuemax', String(Math.round(wave.hp_max)));
    document.getElementById('bossHealth').setAttribute('aria-valuenow', String(Math.round(wave.hp)));
    core.style.setProperty('--charge', `${Math.min(360, chargePercent * 3.6)}deg`);
    document.getElementById('comboValue').textContent = `×${state.combo.count}`;
    document.getElementById('accuracyValue').textContent = percent(state.accuracy);
    document.getElementById('tapPowerValue').textContent = number(state.team.tap_power);
    document.getElementById('chargeValue').textContent = `${Math.floor(chargePercent)}%`;
    document.getElementById('lastLog').textContent = state.log[state.log.length - 1] || state.last_event.label;
    document.getElementById('windowProgress').style.transform = `scaleX(${Math.max(0, Math.min(1, state.signal_progress))})`;
    stage.classList.toggle('signal', signalActive);
    stage.classList.toggle('golden', state.critical_active);
    const indicator = document.getElementById('windowIndicator').querySelector('span');
    indicator.textContent = state.critical_active
      ? '✦ ЗОЛОТОЕ ОКНО · БОНУС ЗА МОМЕНТ'
      : signalActive ? 'Выбери совпадающую руну' : 'Сигнал приближается';
    document.getElementById('corePrompt').textContent = signalActive ? 'НАЙДИ ЗНАК' : 'СЛУШАЙ';
    document.getElementById('coreHint').textContent = signalActive ? 'одна попытка на сигнал' : 'затем найди такой же знак';
    core.setAttribute('aria-label', signalActive ? `Найди руну ${challenge.target_symbol}` : 'Ожидание следующей руны');
    renderRunes();
    renderRail();
    renderSquad();
    renderBuild();
    renderChoice();
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
      const data = await jsonFetch('/action', { method: 'POST', body: JSON.stringify(payload) });
      state = data.state;
      if (data.rejected) pendingStrike = null;
      render();
    } catch (error) {
      if (strike) pendingStrike = strike;
      notify(error.message, true);
    } finally {
      busy = false;
    }
  }

  async function chooseUpgrade(upgradeId) {
    if (busy) return;
    busy = true;
    try {
      const data = await jsonFetch('/action', {
        method: 'POST', body: JSON.stringify({ type: 'choose_upgrade', upgrade_id: upgradeId }),
      });
      state = data.state;
      pendingStrike = null;
      lastFrameAt = performance.now();
      showOnly('battle');
      playing = true;
      render();
      haptic('medium');
    } catch (error) {
      notify(error.message, true);
    } finally {
      busy = false;
    }
  }

  async function reset(playAfter = true) {
    if (busy) return;
    busy = true;
    playing = false;
    try {
      state = await jsonFetch('/reset', { method: 'POST', body: '{}' });
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
    if (['won', 'lost'].includes(state.status)) {
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
    const card = event.target.closest('[data-upgrade-id]');
    if (card) chooseUpgrade(card.dataset.upgradeId);
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
  document.getElementById('resultReset').addEventListener('click', () => reset(true));
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

  Promise.all([jsonFetch('/manifest'), jsonFetch('/state')])
    .then(([manifestData, stateData]) => {
      manifest = manifestData;
      state = stateData;
      lastEventId = state.last_event?.id || 0;
      const desired = savedUiState();
      if (state.status === 'reward') {
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
    })
    .catch((error) => notify(error.message, true));

  const source = new EventSource('/__preview/live');
  let connected = false;
  source.addEventListener('open', () => {
    if (connected) location.reload();
    connected = true;
  });
  source.addEventListener('reload', () => location.reload());
})();
