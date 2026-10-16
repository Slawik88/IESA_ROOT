// ── «Объяснялки» v1: вызываемая шпаргалка + совет «что сейчас делать» ──────────────────────────
// Файл подключается ПОСЛЕ app.40–46 (см. main.py): простые функции хаба «Тропы» уже известны.
// Гайд открывается из шапки в любой момент (v3GuideBtn); формат — шпаргалка: сетка иконок,
// у каждой темы ровно одна строка. Стену текста игрок не читает — учимся делом и картинкой.
// Тексты без копий чисел правил: живые значения игрок видит на своём экране.

// ── Реестр гайдов и лист ──────────────────────────────────────────────────────────────────────
const _GUIDE_BOOK = {};
let _guideOpener = null, _guideKeys = null;
function guideDefine(id, book) { _GUIDE_BOOK[id] = book; }
function _guideClose(now) {
  const host = document.getElementById('g-sheet'); if (!host) return;
  if (_guideKeys) { document.removeEventListener('keydown', _guideKeys, true); _guideKeys = null; }
  const opener = _guideOpener; _guideOpener = null;
  const back = () => { if (opener && document.contains(opener)) opener.focus({ preventScroll: true }); };
  if (now || typeof v3Dismiss !== 'function') { host.remove(); back(); } else v3Dismiss(host, back);
}
function _guideSheet(html) {
  _guideOpener = document.activeElement;
  _guideClose(true);
  const host = document.createElement('div'); host.id = 'g-sheet'; host.className = 'lk-sheet-back';
  host.innerHTML = `<section class="lk-sheet tr-sheet" role="dialog" aria-modal="true" aria-labelledby="g-sheet-t" tabindex="-1">${html}</section>`;
  host.addEventListener('click', e => { if (e.target === host) _guideClose(); });
  _guideKeys = e => {
    if (e.key === 'Escape') { e.preventDefault(); _guideClose(); return; }
    if (e.key !== 'Tab') return;
    const items = [...host.querySelectorAll('button:not([disabled])')], first = items[0], last = items[items.length - 1];
    if (!first) return;
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  document.addEventListener('keydown', _guideKeys, true);
  document.body.appendChild(host); host.firstElementChild.focus({ preventScroll: true });
}
function v3Guide(id) {
  const book = _GUIDE_BOOK[id]; if (!book) return;
  _haptic('select');
  const rows = typeof book.tiles === 'function' ? book.tiles() : (book.tiles || []);
  const tiles = rows.map(t =>
    `<div class="g-tile"><span class="g-ic" aria-hidden="true">${t.icon}</span><b>${_trE(t.title)}</b><small>${_trE(t.text)}</small></div>`).join('');
  const lead = book.lead ? `<p class="g-lead">${_trE(book.lead)}</p>` : '';
  const body = `<div class="tr-sbody"><div class="tr-shead"><h2 id="g-sheet-t">${_trE(book.title)}</h2><button type="button" class="v3-link" onclick="_guideClose()">Закрыть</button></div>${lead}<div class="g-grid">${tiles}</div></div>`;
  _guideSheet(`${body}<div class="tr-foot"><button type="button" class="v3-pill v3-pill--full" onclick="_guideClose()">Готово</button></div>`);
}
// Слепок кнопки для шапки вкладки: v3Head(..., { end: v3GuideBtn('trail') })
function v3GuideBtn(id, label = 'Гайд') {
  return `<button type="button" class="v3-pill v3-pill--sm" onclick="v3Guide('${_trE(id)}')">${_trE(label)} 📖</button>`;
}

// Системный «Назад» сначала закрывает открытый гайд (лист — самая верхняя поверхность)
_backHooks.push(() => {
  if (!document.getElementById('g-sheet')) return false;
  _guideClose();
  return true;
});

// ── Шпаргалка «Тропа»: плитки собираются заново при каждом открытии, из живого ответа сервера ──
// Адаптивность по ресурсам игрока: нет питомцев → свой набор; есть готовый к призыву/награде,
// Спутник ещё закрыт, стройка идёт, попытки/день кончились, еда кончилась — плитки честно это пишут.
// Числа берём из ответа (pair.need, daily/track/trial), копий правил клиент не хранит.
guideDefine('trail', { title: 'Тропа — шпаргалка', lead: 'Питомцы растут в пути. Остальное — по желанию.', tiles: _trailTiles });

function _trailTiles() {
  const me = _tr.me;
  const pets = me ? me.pets || [] : [], acts = me ? me.activities || [] : [];
  if (!pets.length) return [
    { icon: '🐾', title: 'Питомцы', text: 'получите в сундуках' },
    { icon: '🪙', title: 'Следы', text: 'дневной прогресс роста' },
  ];
  const ready = acts.filter(a => a.ready).length;
  const min = _trMinCost(me);
  const free = pets.filter(p => !p.run_id && p.energy >= min).length;
  const slotsFree = Math.max(0, (Number(me.slots) || 3) - acts.length);
  const tiles = [];
  // карточка «В путь» говорит тем же языком, что и экран: что прямо сейчас происходит
  tiles.push({ icon: '🐾', title: 'В путь', text: ready
    ? _trWord(ready, 'питомец ждёт награды', 'питомца ждут награды', 'питомцев ждут награды')
    : free && slotsFree ? 'есть свободный питомец' : acts.length ? 'питомцы в пути' : 'дождитесь сил и отправьте' });
  const daily = me.daily || {}, max = Number(daily.max) || 0, cur = Number(daily.credited) || 0;
  tiles.push({ icon: '🪙', title: 'Следы', text: cur >= max - 0.5 ? 'на сегодня планка набрана' : 'дневной прогресс роста' });
  tiles.push({ icon: '🎒', title: 'Занятия', text: 'поход · экспедиция · дозор' });
  const pair = me.pair || {};
  tiles.push({ icon: '👫', title: 'Спутник', text: pair.unlocked ? 'доступен: возьмите второго' : `откроется с ${Number(pair.need) || 5} видами` });
  const camp = me.camp || {}, lv = camp.levels || {}, job = camp.job;
  tiles.push({ icon: '🏕️', title: 'Лагерь', text: job ? (job.done ? 'стройка завершена' : 'стройка идёт сама')
    : Object.values(lv).some(v => v > 0) ? 'уже простроен — бонусы' : 'постройки дают бонусы' });
  const track = me.track || {};
  tiles.push({ icon: '🔍', title: 'Выслеживание', text: track.open ? 'игра не закончена' : Number(track.attempts_left) > 0 ? 'ежедневная мини-игра' : 'приходите завтра' });
  const trial = me.trial || {};
  tiles.push({ icon: '🏆', title: 'Испытание', text: trial.done ? 'сдано — до следующей недели' : 'недельная мини-игра' });
  const food = (me.foods || []).some(f => Number(f.quantity) > 0), tired = pets.some(p => p.energy < min);
  tiles.push({ icon: '⏰', title: 'Силы', text: tired && !food ? 'нужна еда — сундуки' : tired ? 'покормите: вырастут быстрее' : 'растут сами' });
  return tiles;
}

// ── Совет «что сейчас делать»: одно главное действие экрана ────────────────────────────────────
// Приоритет: забрать награду → отправить свободного → питомцы в пути → восстановление сил.
function trailAdvice(me) {
  const pets = me.pets || [], acts = me.activities || [];
  if (!pets.length) return '';
  const ready = acts.filter(a => a.ready);
  if (ready.length) {
    const act = ready[0], pet = pets.find(p => p.id === act.pet_id);
    const who = pet ? `${_trE(pet.name)} вернулся — ` : '';
    return `<section class="tr-sec tr-now"><p class="tr-now-t">${who}${act.kind === 'expedition' ? 'выберите путь' : 'заберите награду'}</p>` +
      `<button type="button" class="v3-pill v3-pill--sm" data-run="${_trE(act.id)}" onclick="trailRun(this)">${act.kind === 'expedition' ? 'Выбрать путь' : 'Забрать'}</button></section>`;
  }
  const min = _trMinCost(me), slotsFree = Math.max(0, (Number(me.slots) || 3) - acts.length);
  const sendable = pets.filter(p => !p.run_id && p.energy >= min);
  if (sendable.length && slotsFree) {
    const one = sendable.length === 1 ?
      `${_trE(sendable[0].name)} готов к пути — на ходу приносит Следы` :
      `Свободных питомцев с силами: ${sendable.length} — отправьте в путь`;
    return `<section class="tr-sec tr-now"><p class="tr-now-t">${one}</p>` +
      `<button type="button" class="v3-pill v3-pill--sm" onclick="trailSend()">Отправить ›</button></section>`;
  }
  if (acts.length) {
    const soon = Math.min(...acts.filter(a => !a.ready).map(_trLeft));
    const left = Number.isFinite(soon) ? ` Вернутся примерно через ${_trDur(soon)}.` : '';
    return `<section class="tr-sec tr-now"><p class="tr-now-t">Питомцы в пути — за время приносят Следы.${left}</p></section>`;
  }
  return '<section class="tr-sec tr-now"><p class="tr-now-t">Силы восстанавливаются сами — кормление ускорит.</p></section>';
}
