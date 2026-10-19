// ── «Объяснялки» v1: вызываемые подсказки + совет «что сейчас делать» ─────────────────────────
// Файл подключается ПОСЛЕ app.40–46 (см. main.py): простые функции хаба «Тропы» уже известны.
// Подсказки открываются из шапки в любой момент (v3GuideBtn); формат — плитки: сетка иконок,
// у каждой темы ровно одна строка. Стену текста игрок не читает — учимся делом и картинкой.
// Тексты — для новичка: целая короткая фраза, без внутренних слов и обрывков. Без копий чисел
// правил: живые значения игрок видит на своём экране. Плитки могут быть адаптивными (функция)
// для текущего состояния; если данных на клиенте нет, book.refresh дозапрашивает их у сервера
// и перерисовывает открытый лист.

// ── Реестр подсказок и лист ───────────────────────────────────────────────────────────────────
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
  _guideSheet(`${body}<div class="tr-foot">${act}<button type="button" class="v3-pill${act ? ' v3-pill--ghost' : ''} v3-pill--full" onclick="_guideClose()">Готово</button></div>`);
  _guideCurrent = id;
  if (typeof book.refresh === 'function') (window.requestAnimationFrame || (job => setTimeout(job, 40)))(() => book.refresh());
}
// Кнопка действия листа: закрывает подсказки и ведёт туда, где действие живёт.
function _guideGo() {
  const book = _guideCurrent && _GUIDE_BOOK[_guideCurrent];
  const go = book && book.action && book.action.go;
  _guideClose(true);
  if (typeof go === 'function') go();
}
// Слепок кнопки для шапки вкладки: v3Head(..., { end: v3GuideBtn('trail') })
// «Подсказки» — не «гайд»: слово понятно и тем, кто впервые открыл бота.
function v3GuideBtn(id, label = 'Подсказки') {
  return `<button type="button" class="v3-pill v3-pill--sm" onclick="v3Guide('${_trE(id)}')">${_trE(label)} 💡</button>`;
}

// Системный «Назад» сначала закрывает открытые подсказки (лист — самая верхняя поверхность)
_backHooks.push(() => {
  if (!document.getElementById('g-sheet')) return false;
  _guideClose();
  return true;
});

// ── Подсказки «Тропа»: плитки собираются заново при каждом открытии, из живого ответа сервера ───
// Адаптивность по ресурсам игрока: нет питомцев → свой набор; есть готовый к призыву/награде,
// Спутник ещё закрыт, стройка идёт, попытки/день кончились, еда кончилась — плитки честно это пишут.
// Числа берём из ответа (pair.need, daily/track/trial), копий правил клиент не хранит.
guideDefine('trail', { title: 'Тропа — подсказки', lead: 'Отправляйте питомцев в путь: они растут и приносят находки.', tiles: _trailTiles });

function _trailTiles() {
  const me = _tr.me;
  const pets = me ? me.pets || [] : [], acts = me ? me.activities || [] : [];
  if (!pets.length) return [
    { icon: '🐾', title: 'Питомцы', text: 'выпадают из сундуков' },
    { icon: '🪙', title: 'Следы', text: 'опыт питомцев — копится в занятиях' },
  ];
  const ready = acts.filter(a => a.ready).length;
  const min = _trMinCost(me);
  const free = pets.filter(p => !p.run_id && p.energy >= min).length;
  const slotsFree = Math.max(0, (Number(me.slots) || 3) - acts.length);
  const tiles = [];
  // карточка «В путь» говорит тем же языком, что и экран: что прямо сейчас происходит
  tiles.push({ icon: '🐾', title: 'В путь', text: ready
    ? _trWord(ready, 'вернулся — заберите награду', 'вернулись — заберите награды', 'вернулись — заберите награды')
    : free && slotsFree ? 'можно отправить в путь' : acts.length ? 'питомцы в пути — скоро вернутся' : 'нужны силы — покормите питомца' });
  const daily = me.daily || {}, max = Number(daily.max) || 0, cur = Number(daily.credited) || 0;
  tiles.push({ icon: '🪙', title: 'Следы', text: cur >= max - 0.5 ? 'на сегодня норма набрана' : 'опыт питомцев — копится в занятиях' });
  tiles.push({ icon: '🎒', title: 'Занятия', text: 'поход · экспедиция · дозор' });
  const pair = me.pair || {};
  tiles.push({ icon: '👫', title: 'Спутник', text: pair.unlocked ? 'в путь можно отправить вдвоём' : `откроется, когда соберёте ${Number(pair.need) || 5} видов` });
  const camp = me.camp || {}, lv = camp.levels || {}, job = camp.job;
  tiles.push({ icon: '🏕️', title: 'Лагерь', text: job ? (job.done ? 'стройка завершена' : 'стройка идёт сама')
    : Object.values(lv).some(v => v > 0) ? 'постройки уже помогают в пути' : 'постройки помогают в пути' });
  const track = me.track || {};
  tiles.push({ icon: '🔍', title: 'Выслеживание', text: track.open ? 'вернитесь к поиску' : Number(track.attempts_left) > 0 ? 'раз в день: ищите находки' : 'на сегодня поиск окончен' });
  const trial = me.trial || {};
  tiles.push({ icon: '🏆', title: 'Испытание', text: trial.done ? 'сдано — до следующей недели' : 'раз в неделю — испытание питомца' });
  const food = (me.foods || []).some(f => Number(f.quantity) > 0), tired = pets.some(p => p.energy < min);
  tiles.push({ icon: '⏰', title: 'Силы', text: tired && !food ? 'силы кончились — нужна еда из сундуков' : tired ? 'покормите — силы восстановятся быстрее' : 'восстанавливаются сами' });
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

// ── Подсказки «Сундуки»: плитка «Награда ждёт» и живые остатки приходят дозапросом ─────────────
// Пока вкладка не открыта, данных на клиенте нет: сначала общий набор, после ответа сервера
// плитки перерисовываются (v3Guide → refresh). Открытый лист перерисовывается на месте.
const _chestsTilesStatic = [
  { icon: '🗝', title: 'Ключи', text: 'дают за полный день и неделю заданий' },
  { icon: '✦', title: 'Открытие', text: 'один тап открывает одну звезду; награда выбрана заранее — нажимайте спокойно' },
  { icon: '⭐', title: 'Звёзды', text: 'чем больше звёзд, тем лучше награда' },
  { icon: '🐾', title: 'Что внутри', text: 'питомцы, их карты и еда' },
];
function _chestsRefresh() {
  api('/chests-v1/me').then(d => _guideApply('chests', _chestsTilesLive(d))).catch(() => {});
}
function _chestsTilesLive(d) {
  const paid = d.funding || {}, rem = Number(paid.remaining_today) || 0;
  const canBuy = Number(paid.paid) !== false;
  const ties = Object.entries(d.key_balances || {}).map(([t, b]) => ({ t: Number(t), b: Number(b) })).sort((a, b) => a.t - b.t);
  const primary = ties.length ? ties[0].b : Number(d.key_balance || 0);
  const higher = ties.filter(k => k.t > 1 && k.b > 0);
  const tiles = [];
  if (d.pending_open) tiles.push({ icon: '✦', title: 'Награда ждёт', text: 'она уже выбрана — откройте сундук' });
  tiles.push({ icon: '🗝', title: 'Ключи', text: primary > 0
    ? `${fmt(primary)} обычных${higher.length ? ` · выше уровнем: ${higher.map(k => fmt(k.b)).join(' + ')}` : ''}`
    : 'дают за полный день и неделю заданий' });
  tiles.push({ icon: '✨', title: 'Докупить ключ', text: canBuy && rem > 0
    ? `за ${fmt(Number(paid.price_zarniki) || 0)} ✨ · осталось сегодня: ${rem}` : canBuy ? 'на сегодня покупки закончились' : 'покупка сейчас недоступна' });
  tiles.push({ icon: '⭐', title: 'Звёзды', text: higher.length ? 'лучший ключ поднимает звёзды выше' : 'чем больше звёзд, тем лучше награда' });
  const owned = Object.keys((d.inventory || {}).unlocked_pets || {}).length;
  tiles.push({ icon: '🐾', title: 'Что внутри', text: `${owned} питомцев · карты и еда` });
  return tiles;
}
guideDefine('chests', { title: 'Сундуки — подсказки', lead: 'Ключи открывают сундуки, а шансы на награды честно показаны на экране.', tiles: () => _chestsTilesStatic, refresh: _chestsRefresh });

// ── Подсказки «Задания» и «Достижения»: правила экранов — плитками; абзацы под списками убраны ──
guideDefine('quests', { title: 'Задания — подсказки', lead: 'Выполняйте задания из списка — за них дают награды.', tiles: [
  { icon: '🎯', title: 'Как выполнять', text: 'делайте то, что написано в задании' },
  { icon: '↻', title: 'Можно заменить', text: 'не подошло — откройте задание и замените' },
  { icon: '🎁', title: 'Награды', text: 'за день, за неделю и за весь список целиком' },
], action: { label: 'К играм', go: () => goTo('arena', 'game') } });
guideDefine('ach', { title: 'Достижения — подсказки', lead: 'Игры, забота, развитие и общение.', tiles: [
  { icon: '🏁', title: 'Завершения', text: 'это игры, которые вы довели до конца' },
  { icon: '📅', title: 'Активные недели', text: 'это недели, когда вы играли' },
  { icon: '⚖️', title: 'Развитие', text: 'забота, лагерь, образы и дневные квесты — без требования недель' },
  { icon: '🧾', title: 'История', text: 'прошлые улучшения учитываются по подтверждённым операциям' },
  { icon: '🪙', title: 'Награда', text: 'Мора за каждый уровень — приходит сама' },
  { icon: '💬', title: 'Достижения чата', text: 'за общение с ботом; каждые 10 уровней — Эссенция' },
], action: { label: 'К играм', go: () => goTo('arena', 'game') } });

// ── Подсказки «Справки»: тема — лист с плитками и кнопкой действия ─────────────────────────────
// На самой справке остаются только строки тем; вводные абзацы живут здесь, по строке на плитку.
function _helpGameTiles() {
  const on = k => _sysFlags[k] === true;
  const t = [];
  if (on('game_rhythm_v2')) t.push({ icon: '🎵', title: 'Ритм', text: 'нажимайте руны в такт музыке' });
  if (on('game_minesweeper_v2')) t.push({ icon: '💣', title: 'Сапёр', text: 'открывайте клетки и не попадите на мину' });
  if (on('game_mafia_v1')) t.push({ icon: '🕵️', title: 'Мафия', text: 'игра в чате: напишите боту «бот мафия»' });
  if (on('season_pass_v1')) t.push({ icon: '🎫', title: 'Пропуск сезона', text: 'играйте — копите очки и получайте награды' });
  if (!t.length) t.push({ icon: '🎮', title: 'Игры', text: 'скоро откроются' });
  return t;
}
function _helpPetTiles() {
  if (_sysFlags.pets_v2 === true) return [
    { icon: '🐾', title: 'Тропа', text: 'отправляйте питомцев в походы и экспедиции' },
    { icon: '🪙', title: 'Следы', text: 'опыт питомцев — копится в походах' },
    { icon: '👫', title: 'Спутник', text: 'в путь можно отправить второго питомца' },
    { icon: '🏕️', title: 'Лагерь', text: 'постройки помогают в пути' },
  ];
  return [
    { icon: '🐾', title: 'Активный питомец', text: 'в поход ходит один питомец' },
    { icon: '⚡', title: 'Выносливость', text: 'тратится в походе; еда её восполняет' },
    { icon: '🥚', title: 'Питомцы', text: 'карточки выпадают из сундуков' },
    { icon: '🧭', title: 'Поход и экспедиция', text: 'приносят ключи и находки' },
  ];
}
guideDefine('help-games', { title: 'Игры — подсказки', lead: 'Выбирайте формат под настроение.', tiles: () => _helpGameTiles(), action: { label: 'Открыть игры', go: () => goTo('arena', 'game') } });
guideDefine('help-profile', { title: 'Профиль — подсказки', lead: 'Прогресс, награды и разделы — на одном экране.', tiles: [
  { icon: '✅', title: 'Квесты дня', text: 'сделайте задания дня — заберите награду' },
  { icon: '🏆', title: 'Достижения', text: 'растут, пока вы играете; награда — Мора' },
  { icon: '⭐', title: 'VIP', text: 'образ видят все, наград больше' },
  { icon: '🎒', title: 'Разделы', text: 'образы · питомцы · инвентарь' },
], action: { label: 'Открыть профиль', go: () => goTo('profile') } });
guideDefine('help-pets', { title: 'Питомцы — подсказки', lead: 'Питомцы приносят ключи и находки.', tiles: () => _helpPetTiles(), action: { label: 'Открыть питомцев', go: () => openPetsV1() } });
guideDefine('help-inventory', { title: 'Инвентарь — подсказки', lead: 'Здесь лежит всё, что у вас есть.', tiles: [
  { icon: '👆', title: 'Плитки нажимаются', text: 'нажмите — откроется место, где вещь пригодится' },
  { icon: '🖼️', title: 'Образы', text: 'меняют ваш вид; надеть — в «Образах»' },
  { icon: '🗝', title: 'Ключи и еда', text: 'открывают сундуки и кормят питомцев' },
  { icon: '📦', title: 'Вещи прежней игры', text: 'сохранены за вами' },
], action: { label: 'Открыть инвентарь', go: () => openInventory() } });
guideDefine('help-wallet', { title: 'Зарники и образы — подсказки', lead: 'Образы меняют вид, а не игру.', tiles: [
  { icon: '🪙', title: 'Зарники', text: 'покупаются за деньги; меняются на Мору и Алмазы' },
  { icon: '✨', title: 'Эссенция', text: 'тратится на образы' },
  { icon: '⭐', title: 'VIP', text: 'образ видят все, наград больше' },
  { icon: '🖼️', title: 'Образы', text: 'меняют только внешний вид' },
], action: { label: 'Открыть образы', go: () => openLooksModal() } });
