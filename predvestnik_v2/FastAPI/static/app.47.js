// ── «Объяснялки» v1: вызываемый гайд, вводная «Тропы», совет «что сейчас делать» ───────────────
// Файл подключается ПОСЛЕ app.40–46 (см. main.py): простые функции хаба «Тропы» уже известны.
// Гайд открывается из шапки РАЗОМ (v3GuideBtn) и из вводной карточки — на любой вкладке.
// «Прочитано» вводной живёт на сервере (users.trail_intro_done через POST /pets-v2/intro-seen):
// урок what's-new — Telegram WebView не сохраняет localStorage надёжно.
// Тексты гайда — формулировки механик без копий чисел правил; значения игрок видит на своём экране.

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
  const secs = (book.sections || []).map(s =>
    `<div class="g-sec"><span class="v3-eyebrow">${_trE(s.eyebrow)}</span><h3>${_trE(s.title)}</h3><p class="g-tx">${_trE(s.text)}</p></div>`).join('');
  const lead = book.lead ? `<p class="g-lead">${_trE(book.lead)}</p>` : '';
  const body = `<div class="tr-sbody"><div class="tr-shead"><h2 id="g-sheet-t">${_trE(book.title)}</h2><button type="button" class="v3-link" onclick="_guideClose()">Закрыть</button></div>${lead}${secs}</div>`;
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

// ── Гайд «Тропа» ───────────────────────────────────────────────────────────────────────────────
guideDefine('trail', {
  title: 'Тропа питомцев',
  lead: 'Тропа — это то, чем питомцы заняты, пока вы не в приложении.',
  sections: [
    { eyebrow: 'Главное', title: 'Отправьте питомца в путь', text: 'Поход, экспедиция или дозор: питомец уходит на несколько часов и приносит Следы и находки. Вернулся — заберите награду и решайте, куда дальше.' },
    { eyebrow: 'Следы', title: 'Дневная планка', text: 'Следы — общий прогресс за все занятия в день. После отметки упора они засчитываются медленнее, но награды не уменьшаются. К новому дню планка отрастает заново.' },
    { eyebrow: 'Занятия', title: 'Поход, экспедиция, дозор', text: 'Одновременных занятий три. Поход — вернулся, значит награда ваша. Экспедиция — на возврате выбор из трёх путей: рискованный путь даёт больше Следов, а при неудаче часть награды всё равно остаётся. Дозор — целый день, для тех, кто заходит раз в сутки.' },
    { eyebrow: 'Спутник', title: 'Пара', text: 'Несколько питомцев могут ходить вместе: один ведёт, второй — спутник, он тратит немного сил и получает часть Следов. Пара открывается, когда у вас пять разных видов питомцев.' },
    { eyebrow: 'Лагерь', title: 'Свои постройки', text: 'Постройки до пятого уровня, стройка идёт сама. Лежанка — силы восстанавливаются быстрее. Указатели — повтор одного маршрута выгоднее. Мастерская — талисманы перековываются в тиры повыше.' },
    { eyebrow: 'Мини-игры', title: 'Выслеживание', text: 'Поле 3×3, пара попыток в день. Сначала открыты дармовые подсказки («тепло» — рядом, «холодно» — дальше); остальные клетки открываются за очки внимания — их больше, выше уровень питомца. Найдёте — заберите находку.' },
    { eyebrow: 'Мини-игры', title: 'Испытание недели', text: 'Подберите питомца под набор тегов недели: назначение, черты и талисманы. Сдача — раз в неделю; сложность зависит от того, сколько тегов сошлось.' },
  ],
});

// ── Вводная карточка: один раз, отметка «Понятно» уходит на сервер ─────────────────────────────
function trailIntro(me) {
  if (me.intro_done === true || !(me.pets || []).length) return '';
  return `<section class="tr-sec tr-intro">${_trSec('Как здесь устроено')}<ul class="tr-intro-list">` +
    '<li><b>Отправляйте питомцев в путь</b><span>поход, экспедиция или дозор: время идёт, растут Следы, идут находки.</span></li>' +
    '<li><b>Растите и собирайте</b><span>карточка питомца: кормление, назначение, черты и талисманы меняют награду.</span></li>' +
    '<li><b>Заглядывайте в Лагерь и мини-игры</b><span>постройки-бонусы, пара попыток Выслеживания в день и Испытание недели.</span></li>' +
    `</ul><div class="tr-intro-btns"><button type="button" class="v3-pill v3-pill--sm" onclick="trailIntroDone(this)">Понятно</button>` +
    `<button type="button" class="v3-link" onclick="v3Guide('trail')">Подробнее ›</button></div></section>`;
}
async function trailIntroDone(button) {
  if (button) button.disabled = true;
  try {
    await api('/pets-v2/intro-seen', { method: 'POST', body: JSON.stringify({ seen: true }) });
    if (_tr.me) { _tr.me.intro_done = true; _trRender(); }
  } catch (error) {
    console.error('intro-seen failed', error);
    _haptic('error');
    if (button) button.disabled = false;
    toast(typeof error === 'string' ? error : 'Не сохранилось. Попробуйте ещё раз.', false);
  }
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
