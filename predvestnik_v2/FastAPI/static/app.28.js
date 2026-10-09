// ── Уведомления-тосты ──────────────────────────────────────────────────────────────
// Один тост на экране, замена предыдущему. Вид берётся из надетого образа (свой образ виден всегда, VIP не нужен):
// форма из рамки, значок из «частиц», цвет из палитры, насыщенность из тира, фирменная нить у S и выше.
// Без образа тост нейтральный и красится акцентом приложения. Стили: toast-v3.css.
// Вызов прежний: toast(текст, ok = true), третий необязательный аргумент {title, kind: 'reward', icon}.
function _tvGlyph(pt) {
  return { leaf: '❧', ember: '✺', petal: '✿', snow: '❄', spark: '✦', glint: '✧', dot: '●', ring: '◌', sand: '∴', star: '☆', drop: '●' }[pt] || '✦';
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

// ── Подарок от администрации ───────────────────────────────────────────────────────
// Тот же вид, что у тоста (форма из рамки, цвет и значок из образа, насыщенность из тира, нить у S и выше), но крупнее и дольше любого другого уведомления:
// карточка опускается сверху, вспыхивает значок, разлетаются частицы образа, строки подарка выезжают по очереди, числа набегают, образ без VIP тоже свой.
// Таймер стоит, пока палец на карточке; «Забрать» закрывает сразу. Несколько подарков, накопившихся офлайн, складываются в одну карточку. Стили: toast-gift-v3.css.
// payloads: [{reason, gifts: [{label, amount, unit?, kind?: 'skin' | 'mark' | 'vip', glyph?, skin_id?}]}]; onDone вызывается, когда карточка ушла.
const _TG_BURST = [6, 6, 6, 8, 10, 12, 14, 16];
let _tgTimer = null, _tgDone = null;
function _tgSplit(label) {
  const m = /^(\p{Extended_Pictographic}[️‍\p{Extended_Pictographic}]*)\s*(.*)$/u.exec(String(label || '').trim());
  return m ? [m[1], m[2] || m[1]] : ['', String(label || 'Награда')];
}
function v3GiftClose(now) {
  clearTimeout(_tgTimer);
  const host = document.getElementById('gift-toast'), after = _tgDone; _tgDone = null;
  if (host) { if (now || !_v3Moves()) host.remove(); else { host.classList.add('is-out'); setTimeout(() => host.remove(), 300); } }
  if (after) after();
}
function v3GiftToast(payloads, onDone) {
  const gifts = [], reasons = [];
  (payloads || []).forEach(p => { (p?.gifts || []).forEach(g => gifts.push(g)); const r = String(p?.reason || '').trim(); if (r && !reasons.includes(r)) reasons.push(r); });
  if (!gifts.length) { if (onDone) onDone(); return; }
  v3GiftClose(true); _tgDone = onDone || null;
  const head = (payloads || []).find(p => p?.title) || {};      // заголовок по умолчанию «Подарок от Администрации»; промокод задаёт свой (title, from, glyph)
  const ap = _tvLook(), moves = _v3Moves(), ti = ap ? ap.ti : 0, shown = gifts.slice(0, 5), more = gifts.length - shown.length;
  const skin = gifts.find(g => g.kind === 'skin' && /^[a-z_]{2,24}$/.test(String(g.skin_id || '')));
  const rows = shown.map((g, i) => {
    const [em, name] = _tgSplit(g.label), n = Number(g.amount), glyph = g.kind === 'mark' ? g.glyph || '🏷' : em || (g.kind === 'skin' ? '🎀' : '✦');
    const val = g.kind === 'skin' || g.kind === 'mark' ? '<em>новое</em>' : Number.isFinite(n) ? `+<span data-to="${n}">${fmt(n)}</span>${g.unit ? ` ${_profileEsc(g.unit)}` : ''}` : '';
    return `<li style="--i:${i}"><span class="tg-g" aria-hidden="true">${_profileEsc(glyph)}</span><span class="tg-l">${_profileEsc(name)}</span><b class="tg-n">${val}</b></li>`;
  }).join('') + (more > 0 ? `<li class="tg-more" style="--i:${shown.length}"><span></span><span class="tg-l">и ещё ${more}</span><b></b></li>` : '');
  const mark = ap ? _tvGlyph(ap.k.pt) : '✦', count = moves ? _TG_BURST[ti] : 0;
  const burst = Array.from({ length: count }, (_, i) => `<i style="--a:${Math.round(i / count * 360 + (i % 2 ? 11 : -11))}deg;--d:${66 + (i * 37) % 74}px;--x:${Math.round((i + .5) / count * 100)}%;--s:${(.8 + (i * 53 % 7) / 10).toFixed(1)}">${_profileEsc(mark)}</i>`).join('');
  const host = document.createElement('div'); host.id = 'gift-toast';
  host.className = `tv-gift tv-t${ti}${ap ? ` tv-fr-${ap.k.frame} tv-pt-${ap.k.pt}${ap.sig ? ' tv-sig' : ''}` : ''}`;
  host.setAttribute('style', ap ? ap.vars : ''); host.setAttribute('role', 'status');
  const ms = Math.min(15000, 8000 + shown.length * 1200 + (reasons.length ? 1500 : 0)); host.style.setProperty('--tv-ms', `${ms}ms`);
  host.innerHTML = `<i class="tg-sheen" aria-hidden="true"></i><div class="tg-burst" aria-hidden="true">${burst}</div>
    <header class="tg-head"><span class="tg-ic" aria-hidden="true"><u></u>${_profileEsc(head.glyph || '🎁')}</span><span class="tg-hd"><small>${_profileEsc(head.title || 'Подарок')}</small><b>${_profileEsc(head.from || 'От Администрации')}</b></span></header>
    <ul class="tg-rows">${rows}</ul>${reasons.length ? `<p class="tg-why"><small>Причина</small>${reasons.map(_profileEsc).join(' · ')}</p>` : ''}
    <div class="tg-act">${skin ? '<button type="button" class="tg-see">Смотреть образ</button>' : ''}<button type="button" class="tg-take">Забрать</button></div><i class="tg-time" aria-hidden="true"></i>`;
  const dlg = el('modal'); (dlg && dlg.open ? dlg : document.body).appendChild(host);
  let left = ms, since = Date.now();
  const arm = () => { since = Date.now(); clearTimeout(_tgTimer); _tgTimer = setTimeout(() => v3GiftClose(), left); host.classList.remove('is-held'); };
  host.addEventListener('pointerdown', () => { clearTimeout(_tgTimer); left -= Date.now() - since; host.classList.add('is-held'); });
  ['pointerup', 'pointercancel', 'pointerleave'].forEach(ev => host.addEventListener(ev, () => { if (host.classList.contains('is-held')) arm(); }));
  host.querySelector('.tg-take').addEventListener('click', () => v3GiftClose());
  host.querySelector('.tg-see')?.addEventListener('click', () => { _lk.sel = skin.skin_id; v3GiftClose(); openLooksModal(); });
  if (moves) host.querySelectorAll('[data-to]').forEach((node, i) => {
    const to = Number(node.dataset.to), t0 = performance.now() + 380 + i * 110; node.innerHTML = fmt(0);
    const tick = at => { const k = Math.min(1, Math.max(0, (at - t0) / 900)); node.innerHTML = fmt(Math.round(to * (1 - Math.pow(1 - k, 3)))); if (k < 1 && node.isConnected) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  });
  if (typeof _haptic === 'function') _haptic('success');
  arm();
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
