// ── Уведомления-тосты ──────────────────────────────────────────────────────────────
// Один тост на экране, замена предыдущему. Вид берётся из надетого образа (свой образ виден всегда, VIP не нужен):
// форма из рамки, значок из «частиц», цвет из палитры, насыщенность из тира, фирменная нить у S и выше.
// Без образа тост нейтральный и красится акцентом приложения. Стили: toast-v3.css.
// Вызов прежний: toast(текст, ok = true), третий необязательный аргумент {title, kind: 'reward', icon}.
function _tvGlyph(pt) {
  return { leaf: '❧', ember: '✺', petal: '✿', snow: '❄', spark: '✦', glint: '✧', dot: '●', ring: '◌', sand: '∴' }[pt] || '✦';
}
function _tvLook() {
  try { return typeof apFromLook === 'function' ? apFromLook(_profileData?.look) : null; } catch (_) { return null; }   // профиль мог ещё не загрузиться
}
function toast(msg, ok = true, opts) {
  const t = el('toast'); if (!t) return;
  const o = opts || {}, text = String(msg?.message ?? msg ?? '').replace(/^Error:\s*/, '').trim(); if (!text) return;
  const dlg = el('modal');                      // showModal() кладёт диалог выше любых z-index, поэтому тост переезжает внутрь открытого диалога
  if (dlg && dlg.open) { if (t.parentElement !== dlg) dlg.appendChild(t); } else if (t.parentElement !== document.body) document.body.appendChild(t);
  const kind = ok === false ? 'err' : o.kind === 'reward' ? 'reward' : 'ok', ap = _tvLook();
  if (kind === 'err' && typeof _haptic === 'function') _haptic('error');
  const glyph = kind === 'err' ? '!' : o.icon || (ap ? _tvGlyph(ap.k.pt) : '✦');
  t.className = `toast tv-${kind} tv-t${ap ? ap.ti : 0}${o.title || text.length > 40 ? ' tv-long' : ''}${ap ? ` tv-fr-${ap.k.frame} tv-pt-${ap.k.pt}${ap.sig ? ' tv-sig' : ''}` : ''}`;
  t.setAttribute('style', ap ? ap.vars : '');
  t.setAttribute('role', kind === 'err' ? 'alert' : 'status');
  const ms = Math.min(6500, 2400 + text.length * 35);
  t.style.setProperty('--tv-ms', `${ms}ms`);
  t.innerHTML = `<span class="tv-ic" aria-hidden="true">${_profileEsc(glyph)}</span><span class="tv-body">${o.title ? `<b class="tv-title">${_profileEsc(o.title)}</b>` : ''}<span class="tv-tx">${_profileEsc(text)}</span></span><i class="tv-time" aria-hidden="true"></i>`;
  t.classList.remove('show'); void t.offsetWidth; t.classList.add('show');
  clearTimeout(t._tid); t._tid = setTimeout(() => t.classList.remove('show'), ms);
}
el('toast')?.addEventListener('click', () => { const t = el('toast'); clearTimeout(t._tid); t.classList.remove('show'); });   // тап убирает тост
