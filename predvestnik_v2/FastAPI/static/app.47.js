// ── «Объяснялки» v1: вызываемая шпаргалка + совет «что сейчас делать» ──────────────────────────
// Файл подключается ПОСЛЕ app.40–46 (см. main.py): простые функции хаба «Тропы» уже известны.
// Гайд открывается из шапки в любой момент (v3GuideBtn); формат — шпаргалка: сетка иконок,
// у каждой темы ровно одна строка. Стену текста игрок не читает — учимся делом и картинкой.
// Тексты без копий чисел правил: живые значения игрок видит на своём экране. Плитки могут быть
// адаптивными (функция) для текущего состояния; если данных на клиенте нет, book.refresh
// дозапрашивает их у сервера и перерисовывает открытый лист.

// ── Реестр гайдов и лист ──────────────────────────────────────────────────────────────────────
const _GUIDE_BOOK = {};
let _guideOpener = null, _guideKeys = null, _guideCurrent = null;
function guideDefine(id, book) { _GUIDE_BOOK[id] = book; }
function _guideClose(now) {
  const host = document.getElementById('g-sheet'); if (!host) return;
  if (_guideKeys) { document.removeEventListener('keydown', _guideKeys, true); _guideKeys = null; }
  _guideCurrent = null;
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
function _guideTilesHtml(tiles) {
  return tiles.map(t =>
    `<div class="g-tile"><span class="g-ic" aria-hidden="true">${t.icon}</span><b>${_trE(t.title)}</b><small>${_trE(t.text)}</small></div>`).join('');
}
function _guideApply(id, tiles) {   // тихая перерисовка открытого листа (дозапрос пришёл после показа)
  if (_guideCurrent !== id) return;
  const grid = document.querySelector('#g-sheet .g-grid'); if (!grid) return;
  grid.innerHTML = _guideTilesHtml(tiles);
}
function v3Guide(id) {
  const book = _GUIDE_BOOK[id]; if (!book) return;
  _haptic('select');
  const rows = typeof book.tiles === 'function' ? (book.tiles() || []) : (book.tiles || []);
  const lead = book.lead ? `<p class="g-lead">${_trE(book.lead)}</p>` : '';
  const act = book.action ? `<button type="button" class="v3-pill v3-pill--full" onclick="_guideGo()">${_trE(book.action.label)}</button>` : '';
  const body = `<div class="tr-sbody"><div class="tr-shead"><h2 id="g-sheet-t">${_trE(book.title)}</h2><button type="button" class="v3-link" onclick="_guideClose()">Закрыть</button></div>${lead}<div class="g-grid">${_guideTilesHtml(rows)}</div></div>`;
  _guideSheet(`${body}<div class="tr-foot">${act}<button type="button" class="v3-pill v3-pill--full" onclick="_guideClose()">Готово</button></div>`);
  _guideCurrent = id;
  if (typeof book.refresh === 'function') (window.requestAnimationFrame || (job => setTimeout(job, 40)))(() => book.refresh());
}
// Кнопка действия листа: закрывает шпаргалку и ведёт туда, где действие живёт.
function _guideGo() {
  const book = _guideCurrent && _GUIDE_BOOK[_guideCurrent];
  const go = book && book.action && book.action.go;
  _guideClose(true);
  if (typeof go === 'function') go();
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

// ── Шпаргалка «Сундуки»: плитка «Награда ждёт» и живые остатки приходят дозапросом ─────────────
// Пока вкладка не открыта, данных на клиенте нет: сначала общий набор, после ответа сервера
// плитки перерисовываются (v3Guide → refresh). Открытый лист перерисовывается на месте.
const _chestsTilesStatic = [
  { icon: '🗝', title: 'Ключи', text: 'ключи дают задания и полные дни' },
  { icon: '✦', title: 'Открытие', text: 'награда выбирается до показа' },
  { icon: '⭐', title: 'Звёзды', text: 'выше звёзды — жирнее награда' },
  { icon: '🐾', title: 'Добыча', text: 'питомцы, карты и еда' },
];
function _chestsRefresh() {
  api('/chests-v1/me').then(d => _guideApply('chests', _chestsTilesLive(d))).catch(() => {});
}
function _chestsTilesLive(d) {
  const paid = d.funding || {}, rem = Number(paid.remaining_today) || 0;
  const ties = Object.entries(d.key_balances || {}).map(([t, b]) => ({ t: Number(t), b: Number(b) })).sort((a, b) => a.t - b.t);
  const primary = ties.length ? ties[0].b : Number(d.key_balance || 0);
  const higher = ties.filter(k => k.t > 1 && k.b > 0);
  const tiles = [];
  if (d.pending_open) tiles.push({ icon: '✦', title: 'Награда ждёт', text: 'сервер уже выбрал её — коснись' });
  tiles.push({ icon: '🗝', title: 'Ключи', text: primary > 0
    ? `${fmt(primary)} обычных${higher.length ? ` · выше уровнем: ${higher.map(k => fmt(k.b)).join(' + ')}` : ''}`
    : 'ключи дают задания и полные дни' });
  tiles.push({ icon: '✨', title: 'Ещё ключ', text: Number(paid.paid) !== false && rem > 0
    ? `докупка за ${fmt(Number(paid.price_zarniki) || 0)} ✨ · осталось: ${rem}` : 'сегодня без докупок' });
  tiles.push({ icon: '⭐', title: 'Звёзды', text: higher.length ? 'ключ уровнем выше поднимает звёзды' : 'звёздность решает награду' });
  const owned = Object.keys((d.inventory || {}).unlocked_pets || {}).length;
  tiles.push({ icon: '🐾', title: 'Добыча', text: `${owned} питомцев · карты и еда` });
  return tiles;
}
guideDefine('chests', { title: 'Сундуки — что внутри', lead: 'Ключи дают задания; шансы открыты на экране.', tiles: () => _chestsTilesStatic, refresh: _chestsRefresh });

// ── Шпаргалки «Справки»: тема — лист с плитками и кнопкой действия ─────────────────────────────
// На самой справке остаются только строки тем; вводные абзацы живут здесь, по строке на плитку.
function _helpGameTiles() {
  const on = k => _sysFlags[k] === true;
  const t = [];
  if (on('game_rhythm_v2')) t.push({ icon: '🎵', title: 'Ритм', text: 'реакция: жмите руны точно' });
  if (on('game_minesweeper_v2')) t.push({ icon: '💣', title: 'Сапёр', text: 'логика: клетки и флаги' });
  if (on('game_mafia_v1')) t.push({ icon: '🕵️', title: 'Мафия', text: 'в чате: напишите «бот мафия»' });
  if (on('season_pass_v1')) t.push({ icon: '🎫', title: 'Пропуск сезона', text: 'очки за игры — награды' });
  if (!t.length) t.push({ icon: '🎮', title: 'Игры', text: 'скоро откроются' });
  return t;
}
function _helpPetTiles() {
  if (_sysFlags.pets_v2 === true) return [
    { icon: '🐾', title: 'Тропа', text: 'питомцы растут в пути' },
    { icon: '🪙', title: 'Следы', text: 'дневной прогресс роста' },
    { icon: '👫', title: 'Спутник', text: 'второй питомец в поход' },
    { icon: '🏕️', title: 'Лагерь', text: 'стройки дают бонусы' },
  ];
  return [
    { icon: '🐾', title: 'Активный питомец', text: 'ходит в поход один' },
    { icon: '⚡', title: 'Выносливость', text: 'тратится в пути, еда возвращает' },
    { icon: '🥚', title: 'Питомцы', text: 'карточки выпадают из сундуков' },
    { icon: '🧭', title: 'Поход и экспедиция', text: 'ключи и находки' },
  ];
}
guideDefine('help-games', { title: 'Игры — шпаргалка', lead: 'Выбирайте формат под настроение.', tiles: () => _helpGameTiles(), action: { label: 'Открыть игры', go: () => goTo('arena', 'game') } });
guideDefine('help-profile', { title: 'Профиль — шпаргалка', lead: 'Всё ваше — на одном экране.', tiles: [
  { icon: '✅', title: 'Квесты дня', text: 'награда забирается одним тапом' },
  { icon: '🏆', title: 'Достижения', text: 'растут от игр и активных недель' },
  { icon: '⭐', title: 'VIP', text: 'образ видят все, наград больше' },
  { icon: '🎒', title: 'Разделы', text: 'образы · питомцы · инвентарь' },
], action: { label: 'Открыть профиль', go: () => goTo('profile') } });
guideDefine('help-pets', { title: 'Питомцы — шпаргалка', lead: 'Питомцы приносят ключи и находки.', tiles: () => _helpPetTiles(), action: { label: 'Открыть питомцев', go: () => openPetsV1() } });
guideDefine('help-inventory', { title: 'Инвентарь — шпаргалка', lead: 'Экран показывает; надеть и покормить — на своих экранах.', tiles: [
  { icon: '👆', title: 'Нажмите плитку', text: 'перейдёте туда, где это используют' },
  { icon: '🖼️', title: 'Образы', text: 'надеть — в «Образах»' },
  { icon: '🗝', title: 'Ключи и еда', text: 'расходуются на своих экранах' },
  { icon: '📦', title: 'Вещи прежней игры', text: 'сохранены за вами' },
], action: { label: 'Открыть инвентарь', go: () => openInventory() } });
guideDefine('help-wallet', { title: 'Зарники и образы — шпаргалка', lead: 'Косметика меняет вид, а не игру.', tiles: [
  { icon: '🪙', title: 'Зарники', text: 'донат-валюта: обмен и магазин' },
  { icon: '✨', title: 'Эссенция', text: 'растит образы по тирам' },
  { icon: '⭐', title: 'VIP', text: 'образ видят все, наград больше' },
  { icon: '🖼️', title: 'Образы', text: 'меняют только внешний вид' },
], action: { label: 'Открыть образы', go: () => openLooksModal() } });
