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

// ── Подтверждение траты ────────────────────────────────────────────────────────────
// Любая трата (образ, тир, Эссенция, Зарники, VIP, обмен, лавка, подарок) идёт через один лист: что берём, сколько стоит, сколько на счёте и сколько
// останется. Подтверждение это второе нажатие; отмена, Esc и касание подложки ничего не делают. Возвращает Promise<boolean>.
// spec: {title, visual (наша разметка или эмодзи), name, sub, rows: [[подпись, значение, главное?]], price, icon, have, cta, note}
// Если строки не заданы, они собираются из price, icon и have. Внутри открытого диалога (старые окна) лист рисуется внутри него.
let _cfKeys = null;
function v3Confirm(spec) {
  const s = spec || {}, icon = s.icon || '✨', cash = n => `${fmt(n)} ${icon}`;
  const price = Number(s.price), have = Number(s.have);
  const rows = s.rows || (Number.isFinite(price) ? [['Цена', cash(price)], ...(Number.isFinite(have) ? [['На счёте', cash(have)], ['Останется', cash(Math.max(0, have - price)), true]] : [])] : []);
  return new Promise(resolve => {
    document.getElementById('cf-sheet')?.remove(); if (_cfKeys) document.removeEventListener('keydown', _cfKeys, true);
    const host = document.createElement('div'); host.id = 'cf-sheet'; host.className = 'lk-sheet-back';
    const visual = /^[<]/.test(String(s.visual || '')) ? s.visual : `<span class="cf-ico" aria-hidden="true">${_profileEsc(s.visual || '✨')}</span>`;
    host.innerHTML = `<section class="lk-sheet cf-sheet" role="alertdialog" aria-modal="true" aria-labelledby="cf-title" tabindex="-1">
      <h2 id="cf-title" class="cf-title">${_profileEsc(s.title || 'Подтвердите покупку')}</h2>
      <div class="cf-item">${visual}<div><b>${_profileEsc(s.name || '')}</b>${s.sub ? `<small>${_profileEsc(s.sub)}</small>` : ''}</div></div>
      <dl class="cf-rows">${rows.map(([k, v, strong]) => `<div${strong ? ' class="is-total"' : ''}><dt>${_profileEsc(k)}</dt><dd>${_profileEsc(v)}</dd></div>`).join('')}</dl>
      ${s.note ? `<p class="cf-note">${_profileEsc(s.note)}</p>` : ''}
      <div class="cf-actions"><button type="button" class="v3-pill cf-ok">${_profileEsc(s.cta || 'Подтвердить')}</button><button type="button" class="v3-pill v3-pill--ghost cf-no">Отмена</button></div></section>`;
    let settled = false;
    const opener = document.activeElement, parent = (typeof el === 'function' && el('modal')?.open) ? el('modal') : document.body;
    const done = ok => {
      if (settled) return; settled = true;
      document.removeEventListener('keydown', _cfKeys, true); _cfKeys = null;
      if (ok && typeof _haptic === 'function') _haptic('medium');
      resolve(ok);                                   // действие начинается сразу, лист уезжает параллельно
      if (typeof v3Dismiss === 'function') v3Dismiss(host, () => { if (opener && document.contains(opener)) opener.focus({ preventScroll: true }); }); else host.remove();
    };
    host.addEventListener('click', e => { if (e.target === host) done(false); });
    host.querySelector('.cf-ok').addEventListener('click', () => done(true));
    host.querySelector('.cf-no').addEventListener('click', () => done(false));
    _cfKeys = e => {
      if (e.key === 'Escape') { e.preventDefault(); done(false); return; }
      if (e.key !== 'Tab') return;
      const items = [...host.querySelectorAll('button')], first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', _cfKeys, true);
    parent.appendChild(host); host.querySelector('.cf-sheet').focus({ preventScroll: true });   // фокус на листе, а не на кнопке: без кольца вокруг «Подтвердить»
  });
}
