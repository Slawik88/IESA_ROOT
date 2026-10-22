// ── Мягкое напоминание о питомцах (core/pet_nudge_v1.py) ───────────────────────────────────────
// Сервер сам решает, пора ли: несколько дней подряд игрок заходит, но не открывает питомцев.
// Показ редкий (не чаще раза в две недели, максимум трижды), лист тихий: без звука и вибрации,
// закрывается тапом мимо, «Назад» и кнопкой «Не сейчас». Не мешаем: ждём, пока игрок осмотрится,
// и молчим, если он пришёл по ссылке, уже в питомцах или перед ним другое окно.
let _petNudgeAsked = false;
function _petNudgeBusy() {
  return _activePage === 'pets' || document.hidden || !!document.querySelector('[role="dialog"][aria-modal="true"], #g-sheet');
}
function _petNudgeCheck() {
  if (_petNudgeAsked || _petNudgeBusy()) return;
  try { if (new URLSearchParams(location.search).get('startapp') || (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param)) return; } catch (_) { }
  _petNudgeAsked = true;
  api('/pet-nudge/visit', { method: 'POST' }).then(card => {
    if (!card || !card.show) return;
    // игрок мог уйти в другое место, пока шёл ответ: подождём, пока освободится главный экран
    const show = tries => _petNudgeBusy() ? (tries > 0 && setTimeout(() => show(tries - 1), 5000)) : _petNudgeSheet(card);
    show(12);
  }).catch(() => { });
}
function _petNudgeSheet(card) {
  const tiles = (card.tiles || []).map(t =>
    `<li class="pn-row"><span class="pn-ic" aria-hidden="true">${_trE(t.icon)}</span><span><b>${_trE(t.title)}</b><small>${_trE(t.text)}</small></span></li>`).join('');
  _guideSheet(`<div class="tr-sbody pn-body">
      <div class="pn-hero"><span class="pn-pet" aria-hidden="true">${_trE(card.icon)}</span></div>
      <h2 id="g-sheet-t" class="pn-title">${_trE(card.title)}</h2>
      <p class="g-lead pn-lead">${_trE(card.lead)}</p>
      <ul class="pn-list">${tiles}</ul>
    </div>
    <div class="tr-foot">
      <button type="button" class="v3-pill v3-pill--full" onclick="_petNudgeAnswer('open')">${_trE(card.action)}</button>
      <button type="button" class="v3-pill v3-pill--ghost v3-pill--full" onclick="_petNudgeAnswer('later')">Не сейчас</button>
    </div>`);
}
function _petNudgeAnswer(choice) {
  _guideClose(choice === 'open');
  api('/pet-nudge/answer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ choice }) }).catch(() => { });
  if (choice === 'open') openPetsV1();
}
if (INIT_DATA || sess() || LOCAL_PREPROD_TEST) setTimeout(_petNudgeCheck, 3500);
