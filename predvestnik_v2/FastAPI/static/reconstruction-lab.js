(() => {
  'use strict';

  const API = '/__reconstruction';
  const FRAME_MS = 100;
  const SESSION_STORAGE_KEY = 'reconstruction-preview-session';
  let previewSession = sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (!previewSession) {
    previewSession = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    sessionStorage.setItem(SESSION_STORAGE_KEY, previewSession);
  }
  const stage = document.getElementById('tapStage');
  const core = document.getElementById('tapCore');
  const orbit = document.getElementById('runeOrbit');
  const impactLayer = document.getElementById('impactLayer');
  const choiceLayer = document.getElementById('choiceLayer');
  const resultLayer = document.getElementById('resultLayer');
  const toast = document.getElementById('statusToast');
  let state = null;
  let busy = false;
  let pendingStrike = null;
  let lastFrameAt = performance.now();
  let lastEventId = 0;
  let toastTimer = null;

  const esc = (value) => String(value ?? '').replace(/[&<>\"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;',
  })[char]);
  const number = (value) => Math.max(0, Math.round(Number(value) || 0)).toLocaleString('ru-RU');

  async function jsonFetch(path, options = {}) {
    const response = await fetch(API + path, {
      ...options,
      headers: {
        'content-type': 'application/json',
        'x-reconstruction-session': previewSession,
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
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
    if (!event?.id || event.id === lastEventId) return;
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

  function renderRunes() {
    const challenge = state.challenge;
    const options = new Map((challenge?.options || []).map((option) => [option.slot, option.symbol]));
    orbit.querySelectorAll('[data-target-slot]').forEach((button) => {
      const symbol = options.get(button.dataset.targetSlot) || '·';
      button.textContent = symbol;
      button.disabled = !challenge?.active || Boolean(pendingStrike);
      button.setAttribute('aria-label', `${button.dataset.targetSlot}: руна ${symbol}`);
    });
  }

  function renderChoice() {
    if (state.status !== 'reward') {
      choiceLayer.hidden = true;
      return;
    }
    document.getElementById('upgradeList').innerHTML = state.reward_options.map((upgrade) => `
      <button class="upgrade-card" type="button" data-upgrade-id="${esc(upgrade.id)}">
        <span>${esc(upgrade.emoji)}</span>
        <span><strong>${esc(upgrade.name)}</strong><small>${esc(upgrade.description)}</small></span>
        <b>›</b>
      </button>`).join('');
    choiceLayer.hidden = false;
  }

  function renderResult() {
    if (!['won', 'lost'].includes(state.status)) {
      resultLayer.hidden = true;
      return;
    }
    const won = state.status === 'won';
    document.getElementById('resultMark').textContent = won ? '✦' : '◌';
    document.getElementById('resultTitle').textContent = won ? 'Колокол отвечает тебе' : 'Эхо погасло';
    document.getElementById('resultCopy').textContent = won
      ? 'Три волны пройдены точностью, а не скоростью. Обычный спам здесь только ломает серию.'
      : 'Смотри на знак в центре и выбирай его отражение. Частота нажатий не заменяет точность.';
    document.getElementById('resultStats').innerHTML = [
      [state.mastery.correct_taps, 'точных'],
      [`${number(state.accuracy)}%`, 'точность'],
      [state.combo.max, 'макс. серия'],
      [state.mastery.discharges, 'разрядов'],
      [state.mastery.mistakes, 'ошибок'],
      [`${Math.round(state.mastery.elapsed_ms / 1000)}с`, 'время'],
    ].map(([value, label]) => `<span><strong>${esc(value)}</strong>${esc(label)}</span>`).join('');
    resultLayer.hidden = false;
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
    document.getElementById('bossHealthFill').style.width = `${hpPercent}%`;
    document.getElementById('bossHealthValue').textContent = `${number(wave.hp)} / ${number(wave.hp_max)}`;
    document.getElementById('bossHealth').setAttribute('aria-valuemax', String(Math.round(wave.hp_max)));
    document.getElementById('bossHealth').setAttribute('aria-valuenow', String(Math.round(wave.hp)));
    core.style.setProperty('--charge', `${Math.min(360, chargePercent * 3.6)}deg`);
    document.getElementById('comboValue').textContent = `×${state.combo.count}`;
    document.getElementById('accuracyValue').textContent = `${number(state.accuracy)}%`;
    document.getElementById('tapPowerValue').textContent = number(state.team.tap_power);
    document.getElementById('chargeValue').textContent = `${Math.floor(chargePercent)}%`;
    document.getElementById('lastLog').textContent = state.log[state.log.length - 1] || state.last_event.label;
    document.getElementById('windowProgress').style.width = `${state.signal_progress * 100}%`;
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
    renderChoice();
    renderResult();
    animateEvent(state.last_event);
  }

  function queueStrike(slot, event) {
    if (!state?.challenge?.active || pendingStrike) return;
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
    if (busy || !state || state.status !== 'active') return;
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
      choiceLayer.hidden = true;
      render();
      haptic('medium');
    } catch (error) {
      notify(error.message, true);
    } finally {
      busy = false;
    }
  }

  async function reset() {
    if (busy) return;
    busy = true;
    try {
      state = await jsonFetch('/reset', { method: 'POST', body: '{}' });
      pendingStrike = null;
      lastFrameAt = performance.now();
      lastEventId = 0;
      choiceLayer.hidden = true;
      resultLayer.hidden = true;
      renderSquad();
      render();
    } catch (error) {
      notify(error.message, true);
    } finally {
      busy = false;
    }
  }

  orbit.addEventListener('pointerdown', (event) => {
    const button = event.target.closest('[data-target-slot]');
    if (button) queueStrike(button.dataset.targetSlot, event);
  });
  document.addEventListener('keydown', (event) => {
    const slots = { Digit1: 'left', Digit2: 'center', Digit3: 'right' };
    if (slots[event.code] && !event.repeat) queueStrike(slots[event.code], event);
  });
  document.getElementById('upgradeList').addEventListener('click', (event) => {
    const card = event.target.closest('[data-upgrade-id]');
    if (card) chooseUpgrade(card.dataset.upgradeId);
  });
  document.getElementById('resetButton').addEventListener('click', reset);
  document.getElementById('resultReset').addEventListener('click', reset);

  Promise.all([jsonFetch('/manifest'), jsonFetch('/state')])
    .then(([, stateData]) => {
      state = stateData;
      lastEventId = state.last_event?.id || 0;
      renderSquad();
      render();
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
