// Pet practice: local checkpoints only. Never calls activity/reward writers.
let _ppContext = null, _ppGeneration = 0, _ppLoading = false, _ppError = '';
const _ppMemory = new Map();
const _ppCredentials = () => JSON.stringify(hdrs()); // retained only in parent memory
const _ppLoginVisible = () => { const node = el('login-ov'); return !!node && !node.classList.contains('hidden'); };
function _ppDetach() {
  ++_ppGeneration;
  if (_ppContext?.frame) _ppContext.frame.remove();
  _ppContext = null; _ppLoading = false;
}
function _ppInvalidate() {
  if (!_ppContext && !_ppLoading) return;
  _ppDetach(); _tr.me = null;
  if (_activePage === 'pets' && _tr.view === 'practice') {
    el('pg-pets').innerHTML = `${v3Head('Вылазка')}<div class="v3-empty" role="status"><b>Нужно проверить питомца</b><span>Аккаунт или доступ к питомцу изменился. Откройте раздел заново.</span><button type="button" class="v3-link" onclick="openTrail()">К питомцам</button></div>`;
  }
}
function _ppValid(context) {
  return context === _ppContext && context.generation === _ppGeneration &&
    _activePage === 'pets' && _tr.view === 'practice' &&
    _sysFlags.pets_v2 === true && !_ppLoginVisible() &&
    Number(_uid) === context.owner && _ppCredentials() === context.credentials &&
    !!_tr.me?.pets?.some(p => Number(p.id) === context.pet.id);
}
function trailPracticePreserve(root) {
  if (!_ppContext || !root.contains(_ppContext.frame)) return false;
  if (!_ppValid(_ppContext)) { _ppInvalidate(); return true; }
  return true; // periodic pet refresh must not replace a live game frame
}
function trailPracticeMounted(root) {
  if (_tr.view !== 'practice' || !_ppContext || !_ppValid(_ppContext)) return;
  const frame = root.querySelector('#tr-practice-frame');
  if (!frame || _ppContext.frame === frame) return;
  _ppContext.frame = frame;
  frame.src = BASE + '/pet-practice';
}
async function trailPractice(petId) {
  if (_ppLoading || _sysFlags.pets_v2 !== true) return;
  _ppDetach(); _ppLoading = true; _ppError = '';
  const generation = _ppGeneration, credentials = _ppCredentials();
  trailGo('practice', petId);
  try {
    // Both authenticated reads belong to the same credential generation.
    const [profile, me] = await Promise.all([api('/profile/me'), api('/pets-v2/me')]);
    if (generation !== _ppGeneration || credentials !== _ppCredentials() || _ppLoginVisible() ||
        _activePage !== 'pets' || _tr.view !== 'practice') return;
    const owner = Number(profile?.user_id), pet = me?.pets?.find(p => Number(p.id) === Number(petId));
    if (!Number.isSafeInteger(owner) || owner <= 0 || owner !== Number(_uid) || !pet) {
      throw new Error('Аккаунт или питомец изменился. Откройте раздел питомцев заново.');
    }
    const key = `pv:pet-practice:v1:${owner}:${Number(pet.id)}`;
    let snapshot = _ppMemory.get(key) || null, storageFailed = false;
    try {
      const raw = localStorage.getItem(key);
      if (raw && raw.length <= 16384) snapshot = JSON.parse(raw);
    } catch (_) { storageFailed = true; }
    _tr.me = me;
    _ppContext = { owner, credentials, key, generation, pet: { id: Number(pet.id),
      name: String(pet.name || 'Питомец').slice(0, 80), icon: String(pet.icon || '🐾').slice(0, 24) },
      snapshot, storageFailed, token: '', sequence: 0, frame: null };
  } catch (error) {
    if (generation !== _ppGeneration) return;
    _ppError = typeof error === 'string' ? error : error.message || 'Не удалось загрузить вылазку.';
  } finally {
    if (generation === _ppGeneration) { _ppLoading = false; if (_activePage === 'pets' && _tr.view === 'practice') _trRender(); }
  }
}
_TR_VIEWS.practice = me => {
  const head = v3Head('Вылазка', { back: 'trailBack()' });
  if (_ppLoading) return `${head}<p class="tr-sub" role="status">Проверяем питомца…</p>`;
  if (_ppContext) return `${head}<p class="tr-sub">Без наград и расхода сил. Ходы сохраняются на этом устройстве.</p><iframe id="tr-practice-frame" title="Вылазка: ${_trE(_ppContext.pet.name)}" sandbox="allow-scripts" referrerpolicy="same-origin" style="display:block;width:100%;min-height:360px;border:0" loading="eager"></iframe>`;
  const pets = me?.pets || [];
  return `${head}${_ppError ? `<p role="alert">${_trE(_ppError)}</p>` : ''}<p class="tr-sub">Выберите питомца. Можно играть, даже если он в походе или устал. Наград и зачёта квестов здесь нет.</p>${pets.map(p => `<button type="button" class="tr-practice-pet" onclick="trailPractice(${Number(p.id)})">${_trE(p.icon || '🐾')} ${_trE(p.name || 'Питомец')}<span>Начать или продолжить</span></button>`).join('') || '<p class="tr-sub">Сначала получите питомца в сундуках.</p>'}`;
};
window.addEventListener('message', event => {
  const context = _ppContext, message = event.data;
  if (!context || event.source !== context.frame?.contentWindow || event.origin !== 'null' ||
      !message || message.channel !== 'pv-practice-v1') return;
  if (!_ppValid(context)) { _ppInvalidate(); return; }
  if (message.type === 'ready') {
    context.token = crypto.randomUUID(); context.sequence = 0;
    context.frame.contentWindow.postMessage({ channel: 'pv-practice-v1', type: 'init',
      token: context.token, pet: { name: context.pet.name, icon: context.pet.icon },
      snapshot: context.snapshot, storageFailed: context.storageFailed,
      dark: getComputedStyle(document.documentElement).colorScheme.includes('dark') || matchMedia('(prefers-color-scheme: dark)').matches }, '*');
    return;
  }
  if (message.token !== context.token || !context.token) return;
  if (message.type === 'height') {
    if (Number.isInteger(message.height) && message.height >= 200 && message.height <= 10000) context.frame.style.height = message.height + 'px';
  } else if (message.type === 'save') {
    if (!Number.isSafeInteger(message.sequence) || message.sequence <= context.sequence ||
        !message.snapshot || typeof message.snapshot !== 'object') return;
    let raw;
    try { raw = JSON.stringify(message.snapshot); } catch (_) { return; }
    if (raw.length > 16384 || message.snapshot.privateContent?.v !== 4) return;
    context.sequence = message.sequence;
    context.snapshot = JSON.parse(raw); // completed-boundary copy; no transient frame state
    _ppMemory.delete(context.key); _ppMemory.set(context.key, context.snapshot);
    if (_ppMemory.size > 12) _ppMemory.delete(_ppMemory.keys().next().value);
    try { localStorage.setItem(context.key, raw); }
    catch (_) {
      context.storageFailed = true;
      context.frame.contentWindow.postMessage({ channel: 'pv-practice-v1', type: 'storage-error', token: context.token }, '*');
    }
  }
});
window.addEventListener('storage', event => { if (event.key === SK || event.key === UK || event.key === null) _ppInvalidate(); });
const _ppLoginNode = el('login-ov');
if (_ppLoginNode) new MutationObserver(() => { if (_ppLoginVisible()) _ppInvalidate(); }).observe(_ppLoginNode, { attributes: true, attributeFilter: ['class'] });
setInterval(() => {
  if (!_ppContext && !_ppLoading) return;
  if (_activePage !== 'pets' || _tr.view !== 'practice') { _ppDetach(); return; }
  if (_ppContext && !_ppValid(_ppContext)) _ppInvalidate();
}, 300);
