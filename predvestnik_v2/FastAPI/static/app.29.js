// ── Регалии игроков (внутри проекта «метки») ───────────────────────────────────────
// Регалии приходят с сервера готовыми (/profile/me, /public-profile-v3, строки топа, /marks-v1/me): штатные и особые выдают разработчики вручную,
// заслуженные сервер выдаёт сам и навсегда. Здесь только показ: две самые весомые чипами, остальные маленькими значками в ту же строку (видно все),
// лист со всем списком и одно тихое сообщение о новых. Стили: marks-v3.css. Всё, что пришло, проверяется перед тем, как попасть в разметку.
const _MK_TONES = new Set(['dev', 'staff', 'gold', 'green', 'pink', 'orange', 'violet', 'acc']);
const _MK_FULL = 2, _MK_ICONS = 18, _MK_SEEN = 'pv_marks_seen';
let _mkSheet = null;

function _mkSafe(m) {
  return !!m && typeof m.id === 'string' && /^[a-z0-9_]{2,24}$/.test(m.id) && typeof m.title === 'string' && typeof m.glyph === 'string' && _MK_TONES.has(m.tone);
}
function _mkChip(m) { return `<span class="v3-mark" data-tone="${m.tone}"><i aria-hidden="true">${_profileEsc(m.glyph)}</i><b>${_profileEsc(m.title)}</b></span>`; }
function _mkIcon(m) { return `<span class="v3-mark v3-mark--ico" data-tone="${m.tone}"><i aria-hidden="true">${_profileEsc(m.glyph)}</i></span>`; }

// Ряд регалий под рангом: сначала самые весомые чипами, дальше только значки, поэтому ряд не растёт вширь и помещаются все.
// own: свой профиль, где даже пустой ряд ведёт к списку «что можно получить»
function v3MarksHtml(marks, opts) {
  const list = (Array.isArray(marks) ? marks : []).filter(_mkSafe), own = !!opts?.own;
  if (!list.length && !own) return '';
  const full = list.slice(0, _MK_FULL), icons = list.slice(_MK_FULL, _MK_FULL + _MK_ICONS), more = list.length - full.length - icons.length;
  const label = list.length ? `Регалии: ${list.map(m => m.title).join(', ')}. Открыть список` : 'Регалии. Как их получить';
  const action = own ? 'v3MarksOpenOwn()' : `v3MarksOpenList(${JSON.stringify(list.map(m => m.id))})`;
  window.__mkKnown = { ...(window.__mkKnown || {}), ...Object.fromEntries(list.map(m => [m.id, m])) };
  return `<button type="button" class="v3-marks" onclick="${_profileEsc(action)}" aria-label="${_profileEsc(label)}">${full.map(_mkChip).join('')}${icons.map(_mkIcon).join('')}${more > 0 ? `<span class="v3-mark v3-mark--ico v3-mark--more">+${more}</span>` : ''}${list.length ? '' : '<span class="v3-mark v3-mark--more"><b>Регалии ›</b></span>'}</button>`;
}

// Один значок рядом с ником в списках (самая весомая регалия)
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
  const host = document.getElementById('mk-sheet'), opener = _mkSheet?.opener; _mkSheet = null;
  document.removeEventListener('keydown', _mkKeys, true);
  const back = () => { if (opener && document.contains(opener)) opener.focus({ preventScroll: true }); };
  if (typeof v3Dismiss === 'function') v3Dismiss(host, back); else { host?.remove(); back(); }   // лист уезжает вниз (app.31.js)
}
// Строка листа: плитка со значком в цвете тона, название и описание полностью (лист для того и открывается: прочитать, за что каждая)
function _mkTile(m) { return `<span class="mk-tile" data-tone="${m.tone}" aria-hidden="true">${_profileEsc(m.glyph)}</span>`; }
function _mkRow(m) {
  const fresh = window.__mkFresh?.has(m.id);
  return `<li class="mk-row${fresh ? ' mk-row--new' : ''}">${_mkTile(m)}<div class="mk-tx"><b>${_profileEsc(m.title)}${fresh ? '<em class="mk-new">новая</em>' : ''}${m.kind === 'live' ? '<em class="mk-live">динамическая</em>' : ''}</b><small>${_profileEsc(m.desc || '')}</small></div></li>`;
}
function _mkAhead(a) {
  const pct = a.need > 1 ? Math.round(100 * a.have / a.need) : 0;
  return `<li class="mk-row mk-row--ahead">${_mkTile(a)}<div class="mk-tx"><b>${_profileEsc(a.title)}</b><small>${_profileEsc(a.how || a.desc || '')}</small>${a.need > 1 ? `<div class="mk-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${a.need}" aria-valuenow="${a.have}"><i style="width:${pct}%"></i></div><span class="mk-num">${fmt(a.have)} из ${fmt(a.need)}</span>` : ''}</div></li>`;
}
function _mkGroup(title, list, row) { return list.length ? `${title ? `<h3 class="mk-sub">${title}</h3>` : ''}<ul class="mk-list">${list.map(row).join('')}</ul>` : ''; }
function _mkBody(worn, ahead, note) {
  const live = worn.filter(m => m.kind === 'live'), earned = worn.filter(m => m.kind === 'earned'), special = worn.filter(m => m.kind !== 'earned' && m.kind !== 'live');
  const groups = [['Особые', special], ['Заслуженные', earned], ['Пока держите темп', live]].filter(g => g[1].length);
  const lists = !worn.length ? '<p>Пока ни одной регалии.</p>' : groups.length > 1 ? groups.map(g => _mkGroup(g[0], g[1], _mkRow)).join('') : _mkGroup('', worn, _mkRow);
  return `${lists}${ahead && ahead.length ? _mkGroup('Впереди', ahead, _mkAhead) : ''}${note ? `<p class="mk-note">${_profileEsc(note)}</p>` : ''}`;
}
// Лист открывается сразу с тем, что уже пришло с профилем; «Впереди» и пояснение подтягиваются следом на то же место
function _mkShow(worn, ahead, note, own) {
  const prev = _mkSheet?.opener; document.getElementById('mk-sheet')?.remove(); document.removeEventListener('keydown', _mkKeys, true);   // прежний лист убираем сразу, без анимации
  _mkSheet = { opener: prev || document.activeElement };
  const host = document.createElement('div'); host.id = 'mk-sheet'; host.className = 'lk-sheet-back';
  host.addEventListener('click', e => { if (e.target === host) v3MarksClose(); });
  host.innerHTML = `<section class="lk-sheet mk-sheet" role="dialog" aria-modal="true" aria-labelledby="mk-title"><header class="mk-head"><div><h2 id="mk-title">Регалии</h2><span class="mk-count">${own ? 'Получено' : 'У игрока'}: ${worn.length}</span></div>
      <button type="button" class="mk-x" onclick="v3MarksClose()" aria-label="Закрыть">✕</button></header><div id="mk-body">${_mkBody(worn, ahead, note)}</div></section>`;
  document.body.appendChild(host); document.addEventListener('keydown', _mkKeys, true);
  host.querySelector('.mk-x')?.focus({ preventScroll: true });
}
function v3MarksOpenList(ids) {   // чужой профиль: показываем то, что уже пришло с карточкой
  _haptic('select');
  _mkShow((ids || []).map(id => window.__mkKnown?.[id]).filter(_mkSafe), null, '', false);
}
function v3MarksOpenOwn() {
  _haptic('select');
  const known = (typeof _profileData !== 'undefined' && Array.isArray(_profileData?.marks) ? _profileData.marks : []).filter(_mkSafe);
  _mkShow(known, null, '', true);
  api('/marks-v1/me').then(d => {
    const body = document.getElementById('mk-body'); if (!body) return;   // лист уже закрыли
    const worn = (d.marks || []).filter(_mkSafe); body.innerHTML = _mkBody(worn, (d.ahead || []).filter(_mkSafe), d.special || '');
    const count = document.querySelector('#mk-sheet .mk-count'); if (count) count.innerHTML = `Получено: ${worn.length}`;   // число, не чужой текст
  }).catch(e => toast(e, false));
}

// Новые регалии: одно тихое сообщение за запуск. Что игрок уже видел, помнит это устройство; на новом устройстве покажется всё имеющееся один раз.
function v3MarksNotice(marks) {
  const list = (Array.isArray(marks) ? marks : []).filter(_mkSafe); if (!list.length) return;
  let seen = []; try { const raw = JSON.parse(_lsGet(_MK_SEEN) || '[]'); if (Array.isArray(raw)) seen = raw; } catch (_) { /* битая запись: считаем, что ничего не видели */ }
  const fresh = list.filter(m => !seen.includes(m.id)); if (!fresh.length) return;
  _lsSet(_MK_SEEN, JSON.stringify([...new Set([...seen, ...list.map(m => m.id)])]));
  window.__mkFresh = new Set(fresh.length < list.length ? fresh.map(m => m.id) : []);   // всё сразу «новое» (новое устройство): плашки в листе только шум
  if (fresh.length === 1) toast(fresh[0].title, true, { title: 'Новая регалия', kind: 'reward', icon: fresh[0].glyph });
  else toast(`${fresh.slice(0, 3).map(m => m.title).join(', ')}${fresh.length > 3 ? ` и ещё ${fresh.length - 3}` : ''}`, true, { title: `Новых регалий: ${fresh.length}`, kind: 'reward', icon: '✦' });
}
