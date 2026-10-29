// ── Сезонный пропуск игр ─────────────────────────────────────────────────────────────
// Страница «Пропуск сезона» (#pg-pass), строка в хабе «Игры» (passHubRow зовётся из app.04.js) и точка на вкладке «Игры», пока есть что забрать (passCheck зовётся
// из загрузки профиля, app.02.js). Всё за флагом season_pass_v1: пока он выключен, строки и точки нет, а страница отвечает «пока закрыт».
// Числа правил приходят от сервера (GET /season-pass/me): уровни, очки, награда за уровень, предел в сутки, возраст аккаунта. Клиент не считает награды за сервер:
// при получении показывает то, что вернул POST /season-pass/claim. Одно действие за раз; после обрыва связи данные перечитываются и, если уровни уже выданы, это видно.
// Формат ответа и правила: docs/SEASON_PASS_UI.md. Стили: pass-v3.css.
const _SP_MONTH_OPTS = { day: 'numeric', month: 'long', timeZone: 'UTC' };
const _SP_CACHE_MS = 60000;   // хаб и точка на вкладке не дёргают сервер чаще раза в минуту; страница всегда читает заново
const _SP_RHYTHM_TAPS = 20;   // подсказка «от 20 верных нажатий»; правило сервера: core/season_pass.py, RHYTHM_MIN_CORRECT_TAPS (сверяет тест)
const _SP_OFFLINE = 'Нет связи. Проверьте интернет и попробуйте ещё раз.';
const _SP_ARROW = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>';
const _SP_CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
const _SP_LV_NAME = { got: 'получен', ready: 'можно забрать', next: 'следующий', lock: 'впереди' };

let _sp = { me: null, at: 0, busy: false, loading: false, checking: false, refreshNotice: '', readSeq: 0 };

const _spWord = (n, one, few, many) => { const m = Math.abs(n) % 100, d = m % 10; return m > 10 && m < 20 ? many : d === 1 ? one : d > 1 && d < 5 ? few : many; };
const _spLevels = n => `${fmt(n)} ${_spWord(n, 'уровень', 'уровня', 'уровней')}`;
const _spPoints = n => `${fmt(n)} ${_spWord(n, 'очко', 'очка', 'очков')}`;
// Дата по UTC, как считает сервер («до 11 мая»); год добавляется, когда он не нынешний
function _spDate(iso) {
  const at = iso ? new Date(iso) : null; if (!at || isNaN(at)) return '';
  const text = at.toLocaleDateString('ru-RU', _SP_MONTH_OPTS);
  return at.getUTCFullYear() === new Date().getUTCFullYear() ? text : `${text} ${at.getUTCFullYear()}`;
}
// Награда строкой: «120 🪙 Моры и 30 💧 Эссенции». Нулевые части не пишутся.
function _spGain(g) {
  const parts = [];
  if (Number(g && g.mora) > 0) parts.push(`${fmt(g.mora)} 🪙 Моры`);
  if (Number(g && g.essence) > 0) parts.push(`${fmt(g.essence)} 💧 Эссенции`);
  return parts.join(' и ');
}
// Текущий и прошлый сезон из ответа сервера (прошлый приходит, пока его награды можно забрать)
function _spSeasons(me) {
  const list = (me && me.seasons) || [];
  return { cur: list.find(s => s.current) || null, prev: list.find(s => !s.current) || null };
}
const _spAccount = me => (me && me.account) || { eligible: true };
const _spCanClaim = me => _spAccount(me).eligible !== false;
// Что игрок может забрать прямо сейчас (для точки на вкладке и строки в хабе): число уровней по всем сезонам
const _spReady = me => me && me.enabled ? ((me.seasons || []).reduce((n, s) => n + Math.max(0, Number(s.claimable_levels) || 0), 0)) : 0;

function _spLoad(force) {
  if (!force && _sp.me && Date.now() - _sp.at < _SP_CACHE_MS) return Promise.resolve(_sp.me);
  const seq = ++_sp.readSeq;
  return api('/season-pass/me').then(me => {
    if (seq !== _sp.readSeq) return _sp.me || me;
    _sp.me = me; _sp.at = Date.now(); _sp.refreshNotice = ''; return me;
  });
}

// ── Точка на вкладке «Игры»: есть уровни к получению и аккаунт может их забрать ──────
function _spDock(on) {
  const btn = document.querySelector('.nb[data-page="arena"]'); if (!btn) return;
  if (on) { btn.dataset.sp = '1'; if (!btn.querySelector('.sp-sr')) btn.insertAdjacentHTML('beforeend', '<i class="sr-only sp-sr">, есть награда пропуска</i>'); }
  else { delete btn.dataset.sp; const note = btn.querySelector('.sp-sr'); if (note) note.remove(); }
}
function _spDockSync(me) { _spDock(!_sp.refreshNotice && !!(me && me.enabled) && _spReady(me) > 0 && _spCanClaim(me)); }
function passCheck() {
  if (_sysFlags.season_pass_v1 !== true) { _spDock(false); return; }
  if (_sp.checking) return;
  _sp.checking = true;
  _spLoad(false).then(_spDockSync).catch(() => {}).then(() => { _sp.checking = false; });
}

// ── Строка в хабе «Игры» ─────────────────────────────────────────────────────────────
function _spHubHtml() {
  const me = _sp.me, ready = _spReady(me), cur = _spSeasons(me).cur;
  let small = me ? 'Откройте, чтобы посмотреть уровни' : 'Загружаем пропуск…', go = 'Открыть', hot = false;
  if (me && me.enabled && cur && cur.closed && !(Number(cur.claimable_levels) > 0)) return '';   // сезон 1 закрыт и забрать нечего: строку убирает новый Пропуск Лиги
  if (me && me.enabled && cur) {
    if (ready && _spCanClaim(me)) { small = `К получению: ${_spLevels(ready)}${cur.closed ? ` · до ${_spDate(cur.claim_until)}` : ''}`; go = 'Забрать'; hot = true; }
    else small = cur.level >= cur.levels ? 'Весь путь пройден' : `Уровень ${fmt(cur.level)} из ${fmt(cur.levels)} · до следующего ${_spPoints(cur.points_to_next)}`;
  } else if (me && !me.enabled) return '';
  return `<button type="button" class="v3-game sp-hub${hot ? ' is-hot' : ''}" data-pass onclick="openSeasonPass()"><span><b>${cur && cur.closed ? `Пропуск сезона ${fmt(cur.season)}` : 'Пропуск сезона'}</b><small>${_profileEsc(small)}</small></span><span class="v3-game-go">${go}</span>${_SP_ARROW}</button>`;
}
// Строка встаёт в конец списка игр, пока идёт чтение; сбой чтения оставляет строку со входом на страницу
function passHubRow(host) {
  if (_sysFlags.season_pass_v1 !== true || !host) return;
  const paint = () => {
    const list = host.querySelector('.v3-games--hub'), now = host.querySelector('.sp-hub'), html = _spHubHtml();
    if (!html) { if (now) now.remove(); return; }
    if (now) now.outerHTML = html; else if (list) list.insertAdjacentHTML('beforeend', html);
  };
  paint();
  _spLoad(false).then(me => { _spDockSync(me); paint(); }).catch(() => { const small = host.querySelector('.sp-hub small'); if (small) small.textContent = 'Откройте, чтобы посмотреть уровни'; });
}

// ── Страница ─────────────────────────────────────────────────────────────────────────
function _spHead(cur) {
  const season = cur ? `Сезон ${fmt(cur.season)} до ${_spDate(cur.ends_at)}. ` : '';
  return v3Head('Пропуск сезона', { sub: `${season}Очки дают Ритм и Сапёр, Пропуск бесплатный.`, back: 'spBack()' });
}
function _spHero(s) {
  const done = s.level >= s.levels, inLevel = done ? s.points_per_level : s.points_per_level - s.points_to_next, p = Math.max(0, Math.min(1, inLevel / s.points_per_level));
  return `<section class="sp-sec sp-hero" aria-label="${_profileEsc(`Уровень ${fmt(s.level)} из ${fmt(s.levels)}`)}">
    <div class="sp-big"><b>${fmt(s.level)}</b><span>из ${fmt(s.levels)} уровней</span></div>
    <div class="sp-meter" role="progressbar" aria-label="Очки до следующего уровня" aria-valuemin="0" aria-valuemax="${Number(s.points_per_level)}" aria-valuenow="${Number(inLevel)}"><span><i style="--p:${p.toFixed(4)}"></i></span></div>
    <p class="sp-line"><span>${done ? 'Весь путь пройден' : `До ${fmt(s.level + 1)} уровня: <b>${_profileEsc(_spPoints(s.points_to_next))}</b>`}</span><span>Всего ${_profileEsc(_spPoints(s.points))}</span></p>
  </section>`;
}
// Блок «Забрать»: кнопка, что придёт, почему нельзя. prev: прошлый сезон со своим сроком
function _spClaimBlock(s, me, prev) {
  if (_sp.refreshNotice) return '';
  const n = Number(s.claimable_levels) || 0, acc = _spAccount(me), can = acc.eligible !== false, claimTill = Date.parse(s.claim_until), from = Date.parse(acc.eligible_from || '');
  if (n <= 0) return '';
  const lost = !can && prev && from && claimTill && from > claimTill;   // аккаунту исполнится нужный возраст уже после срока выдачи
  const note = can ? '' : lost ? 'Этот сезон забрать уже не получится: срок выдачи закончится раньше, чем аккаунту исполнится нужный возраст.'
    : `Награды выдаются аккаунтам, которые ${Number(acc.min_days) > 0 ? `в боте не меньше ${fmt(acc.min_days)} ${_spWord(Number(acc.min_days), 'дня', 'дней', 'дней')}` : 'уже достаточно давно в боте'}. Очки копятся${acc.eligible_from ? `, забрать можно с ${_spDate(acc.eligible_from)}` : ', забрать можно позже'}.`;
  const label = `Забрать ${_spLevels(n)}`, season = Number(s.season);
  return `<div class="sp-claim" data-season="${season}">
    <button type="button" class="v3-pill v3-pill--full" onclick="spClaim(${season})" ${can ? '' : 'disabled aria-disabled="true"'}>${_profileEsc(label)}</button>
    <p class="sp-gain">${_profileEsc(_spGain(s.claimable))}</p>
    ${note ? `<p class="sp-note">${_profileEsc(note)}</p>` : ''}
    <p class="v3-err sp-err" role="alert" hidden></p>
  </div>`;
}
// Сетка уровней: получен, можно забрать, следующий, впереди. Награда у всех одинаковая, поэтому уровни не подписаны наградами
function _spTrack(s) {
  const dots = Array.from({ length: s.levels }, (_, i) => {
    const n = i + 1, st = n <= s.claimed_level ? 'got' : n <= s.level ? 'ready' : n === s.level + 1 ? 'next' : 'lock';
    return `<li class="sp-lv is-${st}"><span class="sr-only">Уровень ${n}, ${_SP_LV_NAME[st]}</span><span aria-hidden="true">${st === 'got' ? _SP_CHECK : n}</span></li>`;
  }).join('');
  return `<section class="sp-sec" aria-labelledby="sp-h-track">
    <div class="v3-sec"><span class="v3-eyebrow" id="sp-h-track">Путь · ${_profileEsc(_spLevels(s.levels))}</span></div>
    <ol class="sp-track" role="list" aria-label="Уровни пропуска">${dots}</ol>
    <p class="sp-note">Каждый уровень: ${_profileEsc(_spGain(s.per_level))}. Весь путь: ${_profileEsc(_spGain(s.full_track))}.</p>
  </section>`;
}
function _spHow() {
  return `<section class="sp-sec" aria-labelledby="sp-h-how">
    <div class="v3-sec"><span class="v3-eyebrow" id="sp-h-how">Как копить очки</span></div>
    <p class="sp-rule">Очки приходят за зачётные игры: чем лучше игра, тем больше очков.</p>
    <ul class="sp-rules">
      <li><b>Ритм:</b> чистый забег, от ${_SP_RHYTHM_TAPS} верных нажатий.</li>
      <li><b>Сапёр:</b> победа.</li>
      <li>Награды за места в таблице сезона платятся отдельно и в пропуск не входят.</li>
    </ul>
  </section>`;
}
function _spNext(s) {
  if (s.level >= s.levels) return s.claimed_level >= s.levels ? '<p class="sp-note sp-next">Все награды сезона получены.</p>' : '';
  if (s.claimable_levels > 0) return '';
  return `<p class="sp-note sp-next">Следующая награда: ${_profileEsc(_spGain(s.per_level))} на ${fmt(s.level + 1)} уровне.</p>`;
}
function _spPrev(s, me) {
  if (!s || !(s.level > 0)) return '';   // прошлый сезон, в котором не играли, не показываем
  const open = s.claimable_levels > 0, till = _spDate(s.claim_until);
  const line = open ? `Не забранные награды лежат до ${till}. Пройдено ${_spLevels(s.level)} из ${fmt(s.levels)}.` : `Пройдено ${_spLevels(s.level)} из ${fmt(s.levels)}, все награды получены.`;
  return `<section class="sp-sec sp-prev" aria-labelledby="sp-h-prev">
    <div class="v3-sec"><span class="v3-eyebrow" id="sp-h-prev">Сезон ${fmt(s.season)} закончился</span></div>
    <p class="sp-rule">${_profileEsc(line)}</p>
    ${_spClaimBlock(s, me, true)}
  </section>`;
}
function _spRender() {
  const root = el('pg-pass'); if (!root) return;
  const me = _sp.me, { cur, prev } = _spSeasons(me);
  if (!me || !me.enabled || !cur) {
    root.innerHTML = `${_spHead(null)}<div class="v3-empty"><b>Пропуск пока закрыт</b>Загляните позже: как только он откроется, очки пойдут за каждую зачётную игру.</div>`;
    v3EnterSync(root); return;
  }
  // Прошлый сезон с наградами, которые скоро сгорят, стоит сразу под текущим «Забрать»; без наград это справка в конце страницы
  const old = _spPrev(prev, me), oldOpen = !!old && Number(prev.claimable_levels) > 0;
  root.innerHTML = v3CurIn(`${_spHead(cur)}${_sp.refreshNotice ? `<section class="sp-sec" role="status"><p>${_profileEsc(_sp.refreshNotice)}</p><button type="button" class="v3-pill v3-pill--full" onclick="loadSeasonPass()">Обновить данные</button></section>` : ''}${_spHero(cur)}<section class="sp-sec sp-take">${_spClaimBlock(cur, me, false)}${_spNext(cur)}</section>${oldOpen ? old : ''}${_spTrack(cur)}${_spHow()}${oldOpen ? '' : old}`);
  v3EnterSync(root);
}
// Всё, что рисуется из ответа: страница, строка в хабе, точка. Зовётся после каждого чтения
function _spRepaint() {
  _spDockSync(_sp.me);
  if (_loaded.has('pass')) _spRender();   // страница открывалась в этой сессии: перерисовываем, даже если игрок успел уйти (иначе вернётся к скелету)
  const host = el('game-hub'), row = host && host.querySelector('.sp-hub');
  if (row) { const html = _spHubHtml(); if (html) row.outerHTML = html; else row.remove(); }
}

function spBack() { if (_navStack.length) navBack(); else switchPage('arena'); }
// Страница читается заново при каждом открытии; возврат кнопкой «Назад» из другого экрана её не трогает
function openSeasonPass() { _loaded.delete('pass'); switchPage('pass'); }
function loadSeasonPass() {
  const box = el('pg-pass'); if (!box || _sp.loading) return;
  _sp.loading = true;
  box.innerHTML = '<div class="eyebrow-row"><button type="button" class="v3-link" onclick="spBack()" aria-label="Назад">‹ Назад</button></div><div class="sk" style="height:92px;border-radius:18px;margin-top:12px"></div><div class="sk" style="height:150px;border-radius:18px;margin-top:18px"></div><div class="sk" style="height:110px;border-radius:18px;margin-top:18px"></div>';
  v3EnterSync(box);
  _spLoad(true).then(() => { _sp.loading = false; _spRepaint(); }).catch(err => {
    _sp.loading = false;
    box.innerHTML = v3CurIn(`<div class="eyebrow-row"><button type="button" class="v3-link" onclick="spBack()" aria-label="Назад">‹ Назад</button></div><div class="v3-empty" role="alert"><b>Пропуск не загрузился</b><span>${_profileEsc(typeof err === 'string' && err ? err : _SP_OFFLINE)}</span> <button type="button" class="v3-link" onclick="loadSeasonPass()">Повторить</button></div>`);
  });
}

// ── Получение наград ─────────────────────────────────────────────────────────────────
function _spShowError(season, text) {
  const err = document.querySelector(`.sp-claim[data-season="${Number(season)}"] .sp-err`);
  if (err) { err.textContent = text; err.hidden = false; }
  else toast(text, false);
}
function _spCelebrate(levels, mora, essence) {
  const gifts = [];
  if (mora > 0) gifts.push({ label: '🪙 Мора', amount: mora });
  if (essence > 0) gifts.push({ label: '💧 Эссенция', amount: essence });
  if (gifts.length) v3GiftToast([{ title: 'Пропуск сезона', from: levels ? `Уровни ${levels}` : 'Награды уровней', glyph: '🏁', gifts }]);
}
const _spSeason = (me, season) => ((me && me.seasons) || []).find(s => Number(s.season) === Number(season)) || null;
function spClaim(season) {
  season = Number(season);
  if (_sp.busy || _sp.refreshNotice || !season) return;
  const before = _spSeason(_sp.me, season), was = before ? Number(before.claimed_level) : 0, button = document.querySelector(`.sp-claim[data-season="${season}"] button`);
  _sp.busy = true; ++_sp.readSeq; if (button) button.disabled = true;
  const done = () => { _sp.busy = false; };
  api('/season-pass/claim', { method: 'POST', body: JSON.stringify({ season }) }).then(r => {
    _spCelebrate(r.claimed_levels, Number(r.mora) || 0, Number(r.essence) || 0);
    // The write is confirmed. A failed refresh must only offer another read.
    const confirmed = _spSeason(_sp.me, season);
    if (confirmed && Number(r.claimed_level) >= Number(confirmed.claimed_level)) {
      confirmed.claimed_level = Number(r.claimed_level);
      confirmed.claimable_levels = Math.max(0, Number(confirmed.level) - confirmed.claimed_level);
    }
    return _spLoad(true).then(_spRepaint).catch(() => {
      _sp.refreshNotice = 'Награды получены. Не удалось обновить данные пропуска.';
      _sp.at = 0; _spDock(false); _spRepaint();
    });
  }, err => {
    // Отказ сервера (строка) показываем как есть. Обрыв связи: ответ мог потеряться по дороге, поэтому данные перечитываются, и если уровни уже выданы, игрок видит их, а не ошибку
    const said = typeof err === 'string' && err ? err : '', text = said || _SP_OFFLINE;
    return _spLoad(true).then(me => {
      const now = _spSeason(me, season), got = now ? Number(now.claimed_level) - was : 0;
      if (!said && got > 0) { _spCelebrate('', got * Number(now.per_level.mora), got * Number(now.per_level.essence)); _spRepaint(); return; }
      _spRepaint(); _spShowError(season, text); _haptic('error');
    }, () => { if (button) button.disabled = false; _spShowError(season, text); _haptic('error'); });
  }).then(done, done);
}
