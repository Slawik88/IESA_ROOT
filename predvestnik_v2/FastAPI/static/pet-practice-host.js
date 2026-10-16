// Opaque sandbox: receives a display label and practice checkpoint, never credentials.
(() => {
  'use strict';
  let token = '', ready = false, sequence = 0, resizeTimer = 0;
  const notice = document.getElementById('practice-notice');
  const send = message => parent.postMessage({ channel: 'pv-practice-v1', token, ...message }, '*');
  const glyphs = { cat: '🐾', dog: '🐺', shield: '🛡', heart: '♥', zap: 'ϟ', flame: '✦',
    swords: '⚔', wind: '➜', 'scan-eye': '◎', 'paw-print': '🐾', x: '×', 'arrow-right': '→',
    archive: '▣', 'archive-restore': '✓', 'tree-pine': '🌲', 'tree-deciduous': '🌳',
    'scroll-text': '≋', mountain: '⛰', 'tower-control': '♜', tent: '⛺',
    'door-open': '↔', droplets: '💧', 'audio-lines': '♪', 'book-open': '📖',
    construction: '▤', gem: '◆', sparkles: '✧', check: '✓', sun: '☀', leaf: '❧', moon: '☾' };
  window.lucide = { createIcons() {
    document.querySelectorAll('i[data-lucide]').forEach(icon => {
      const name = icon.dataset.lucide;
      icon.textContent = name === 'cat' ? glyphs.cat : glyphs[name] || '✦';
      icon.classList.add('practice-icon');
      icon.setAttribute('aria-hidden', 'true');
      icon.removeAttribute('data-lucide');
    });
  } };
  const resize = () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => send({ type: 'height', height: Math.ceil(document.body.scrollHeight) + 8 }), 30);
  };
  window.addEventListener('message', event => {
    const message = event.data;
    if (event.source !== parent || event.origin !== new URL(document.URL).origin || !message || message.channel !== 'pv-practice-v1') return;
    if (message.type === 'storage-error' && message.token === token) {
      notice.hidden = false;
      notice.textContent = 'Сохранение в браузере недоступно. После перезагрузки прогресс может пропасть.';
      resize(); return;
    }
    if (message.type !== 'init' || ready || typeof message.token !== 'string' || message.token.length < 16 || message.token.length > 100) return;
    ready = true; token = message.token;
    document.documentElement.style.colorScheme = message.dark ? 'dark' : 'light';
    glyphs.cat = typeof message.pet?.icon === 'string' ? message.pet.icon.slice(0, 24) : '🐾';
    const label = typeof message.pet?.name === 'string' ? message.pet.name.slice(0, 80) : 'Питомец';
    document.querySelector('.lh-prototype').textContent = label + ' · тренировка без наград';
    notice.hidden = true;
    if (message.storageFailed) { notice.hidden = false; notice.textContent = 'Сохранение в браузере недоступно. После перезагрузки прогресс может пропасть.'; }
    document.getElementById('practice-content').hidden = false;
    window.PetPractice = {
      widgetState: message.snapshot || null,
      async setWidgetState(snapshot) {
        const copy = JSON.parse(JSON.stringify(snapshot));
        if (JSON.stringify(copy).length > 16384) return;
        this.widgetState = copy;
        send({ type: 'save', sequence: ++sequence, snapshot: copy });
      }
    };
    const script = document.createElement('script');
    script.src = document.body.dataset.gameScript;
    script.onload = () => { window.lucide.createIcons(); resize(); };
    script.onerror = () => { notice.hidden = false; notice.textContent = 'Вылазка не загрузилась. Вернитесь к питомцам и повторите.'; resize(); };
    document.body.append(script);
    new ResizeObserver(resize).observe(document.body);
  });
  if (parent !== window) parent.postMessage({ channel: 'pv-practice-v1', type: 'ready' }, '*');
})();
