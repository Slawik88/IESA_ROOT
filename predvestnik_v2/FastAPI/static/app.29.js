// ── Метки игроков ──────────────────────────────────────────────────────────────────
// Метки приходят с сервера готовыми (/profile/me, /public-profile-v3, строки топа, /marks-v1/me): штатные идут вместе с рангом бота,
// особые выдают разработчики, заслуженные считаются по данным игрока. Здесь только показ: три метки в шапке, «+N», лист со всем списком.
// Стили: marks-v3.css. Всё, что пришло, проверяется перед тем, как попасть в разметку.
const _MK_TONES = new Set(['dev', 'staff', 'gold', 'green', 'pink', 'orange', 'violet', 'acc']);
const _MK_HERO = 3;
let _mkSheet = null;

function _mkSafe(m) {
  return !!m && typeof m.id === 'string' && /^[a-z0-9_]{2,24}$/.test(m.id) && typeof m.title === 'string' && typeof m.glyph === 'string' && _MK_TONES.has(m.tone);
}
function _mkChip(m) { return `<span class="v3-mark" data-tone="${m.tone}"><i aria-hidden="true">${_profileEsc(m.glyph)}</i><b>${_profileEsc(m.title)}</b></span>`; }

// Ряд меток под рангом. own: свой профиль, где даже пустой ряд ведёт к списку «что можно получить»
function v3MarksHtml(marks, opts) {
  const list = (Array.isArray(marks) ? marks : []).filter(_mkSafe), own = !!opts?.own;
  if (!list.length && !own) return '';
  const shown = list.slice(0, _MK_HERO), more = list.length - shown.length;
  const label = list.length ? `Метки: ${list.map(m => m.title).join(', ')}. Открыть список` : 'Метки. Как их получить';
  const action = own ? 'v3MarksOpenOwn()' : `v3MarksOpenList(${JSON.stringify(list.map(m => m.id))})`;
  window.__mkKnown = { ...(window.__mkKnown || {}), ...Object.fromEntries(list.map(m => [m.id, m])) };
  return `<button type="button" class="v3-marks" onclick="${_profileEsc(action)}" aria-label="${_profileEsc(label)}">${shown.map(_mkChip).join('')}${more > 0 ? `<span class="v3-mark v3-mark--more">+${more}</span>` : ''}${list.length ? '' : '<span class="v3-mark v3-mark--more"><b>Метки ›</b></span>'}</button>`;
}

// Один значок рядом с ником в списках (штатная или выданная метка)
function v3MarkDot(mark) {
  return _mkSafe(mark) ? `<span class="v3-markdot" data-tone="${mark.tone}" role="img" aria-label="${_profileEsc(mark.title)}" title="${_profileEsc(mark.title)}">${_profileEsc(mark.glyph)}</span>` : '';
}

// ── Лист меток ─────────────────────────────────────────────────────────────────────
function _mkKeys(e) {
  if (e.key === 'Escape') { e.preventDefault(); v3MarksClose(); return; }
  if (e.key !== 'Tab') return;
  const items = [...document.querySelectorAll('#mk-sheet button')]; if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}
function v3MarksClose() {
  document.getElementById('mk-sheet')?.remove(); document.removeEventListener('keydown', _mkKeys, true);
  if (_mkSheet?.opener && document.contains(_mkSheet.opener)) _mkSheet.opener.focus({ preventScroll: true });
  _mkSheet = null;
}
function _mkRow(m) { return `<li class="mk-row">${_mkChip(m)}<small>${_profileEsc(m.desc || '')}</small></li>`; }
function _mkAhead(a) {
  const pct = a.need > 1 ? Math.round(100 * a.have / a.need) : 0;
  return `<li class="mk-row mk-row--ahead">${_mkChip(a)}<small>${_profileEsc(a.how || a.desc || '')}</small>${a.need > 1 ? `<div class="mk-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${a.need}" aria-valuenow="${a.have}"><i style="width:${pct}%"></i></div><span class="mk-num">${fmt(a.have)} из ${fmt(a.need)}</span>` : ''}</li>`;
}
function _mkShow(worn, ahead, note) {
  v3MarksClose();
  _mkSheet = { opener: document.activeElement };
  const host = document.createElement('div'); host.id = 'mk-sheet'; host.className = 'lk-sheet-back';
  host.addEventListener('click', e => { if (e.target === host) v3MarksClose(); });
  host.innerHTML = `<section class="lk-sheet mk-sheet" role="dialog" aria-modal="true" aria-labelledby="mk-title"><h2 id="mk-title">Метки</h2>
    ${worn.length ? `<ul class="mk-list">${worn.map(_mkRow).join('')}</ul>` : '<p>Пока ни одной метки.</p>'}
    ${ahead && ahead.length ? `<h3 class="mk-sub">Впереди</h3><ul class="mk-list">${ahead.map(_mkAhead).join('')}</ul>` : ''}
    ${note ? `<p class="mk-note">${_profileEsc(note)}</p>` : ''}<button type="button" class="v3-pill v3-pill--ghost" onclick="v3MarksClose()">Закрыть</button></section>`;
  document.body.appendChild(host); document.addEventListener('keydown', _mkKeys, true);
  host.querySelector('button')?.focus({ preventScroll: true });
}
function v3MarksOpenList(ids) {   // чужой профиль: показываем то, что уже пришло с карточкой
  _haptic('select');
  _mkShow((ids || []).map(id => window.__mkKnown?.[id]).filter(_mkSafe), null, '');
}
function v3MarksOpenOwn() {
  _haptic('select');
  api('/marks-v1/me').then(d => _mkShow((d.marks || []).filter(_mkSafe), (d.ahead || []).filter(_mkSafe), d.special || ''))
    .catch(e => toast(e, false));
}
