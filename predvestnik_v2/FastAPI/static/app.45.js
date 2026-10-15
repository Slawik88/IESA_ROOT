// ── Промокоды · ввести код, забрать доступные, история ─────────────────────────────────────
// GET /promo-v2/me: «Доступно сейчас» (публичные коды из админки и именные коды игрока) и история активаций; забирают тем же POST /promo-v2/redeem, что и ввод руками.
// Награда показывается тем же тостом, что у подарка от Администрации (v3GiftToast, app.28.js). Правила вида: docs/MINIAPP_DESIGN_RULES.md. Стили: promo-v3.css.
let _promo = { me: null, bad: '', busy: '', seq: 0 };

// Старое имя оставлено: на него ведут профиль, «Ещё», настройки и «Что нового»
function openPromoSheet() {
  switchPage('promo');
  const root = el('pg-promo'); if (!root) return Promise.resolve();
  if (!_promo.me) { _promo.bad = ''; _promoRender(); }
  const mine = ++_promo.seq;
  return api('/promo-v2/me').then(me => { if (mine === _promo.seq) { _promo.me = me; _promo.bad = ''; } })
    .catch(e => { if (mine === _promo.seq) _promo.bad = String(e?.message || e || 'Ошибка').replace(/^Error:\s*/, ''); })
    .finally(() => { if (mine === _promo.seq) _promoRender(); });
}
function promoBack() { if (typeof _navStack !== 'undefined' && _navStack.length) navBack(); else switchPage('profile'); }

const _promoDate = iso => { const d = iso ? new Date(iso) : null; return d && !isNaN(d) ? d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) : ''; };
function _promoOffer(o) {
  const facts = [o.personal ? 'личный' : '', o.until ? `до ${_promoDate(o.until)}` : '', o.left != null ? `осталось ${fmt(o.left)}` : ''].filter(Boolean);
  const busy = _promo.busy === o.code;
  return `<li class="pm-row"><span class="pm-tx"><b>${_profileEsc(o.rewards.join(' · '))}</b><small><span class="pm-code">${_profileEsc(o.code)}</span>${facts.length ? ` · ${_profileEsc(facts.join(' · '))}` : ''}</small></span>`
    + `<button type="button" class="v3-pill v3-pill--sm v3-pill--ghost" data-code="${_profileEsc(o.code)}" onclick="promoTake(this.dataset.code)" ${_promo.busy ? 'disabled' : ''}>${busy ? '…' : 'Забрать'}</button></li>`;
}
function _promoPast(h) {
  return `<li class="pm-row pm-row--past"><span class="pm-tx"><b>${_profileEsc(h.granted.join(' · ') || h.code)}</b><small><span class="pm-code">${_profileEsc(h.code)}</span>${h.in_chat ? ' · в чате' : ''}</small></span><time>${_profileEsc(_promoDate(h.at))}</time></li>`;
}
function _promoLists() {
  if (_promo.bad) return `<div class="v3-empty" role="alert"><b>Список не загрузился</b><span>${_profileEsc(_promo.bad)}</span> <button type="button" class="v3-link" onclick="openPromoSheet()">Повторить</button></div>`;
  if (!_promo.me) return '<div class="sk" style="height:120px;border-radius:14px;margin-top:18px"></div>';
  const { available, history } = _promo.me;
  const offers = available.length ? `<ul class="pm-list">${available.map(_promoOffer).join('')}</ul>`
    : '<p class="v3-empty">Сейчас открытых кодов нет. Новые появляются здесь сами.</p>';
  const past = history.length ? `<ul class="pm-list">${history.map(_promoPast).join('')}</ul>` : '<p class="v3-empty">Активированные коды появятся здесь.</p>';
  return `<div class="v3-sec"><span class="v3-eyebrow">Доступно сейчас${available.length ? ` · ${available.length}` : ''}</span></div>${offers}`
    + `<div class="v3-sec"><span class="v3-eyebrow">История</span></div>${past}`;
}
function _promoRender() {
  const root = el('pg-promo'); if (!root) return;
  const typed = String(el('promo-in')?.value || ''), focused = document.activeElement?.id === 'promo-in';
  root.innerHTML = `${v3Head('Промокоды', { back: 'promoBack()' })}
    <form class="pm-form" onsubmit="event.preventDefault();promoTake()" novalidate>
      <label class="sr-only" for="promo-in">Код</label>
      <input id="promo-in" class="v3-field" autocomplete="off" autocapitalize="characters" spellcheck="false" maxlength="64" placeholder="Введите код" oninput="_promoTyped()">
      <button type="submit" id="promo-go" class="v3-pill" ${_promo.busy ? 'disabled' : ''}>${_promo.busy === '*' ? '…' : 'Активировать'}</button>
    </form>
    <p class="v3-err" id="promo-err" role="alert" hidden></p>
    ${_promoLists()}`;
  const inp = el('promo-in'); if (inp) { inp.value = typed; if (focused) inp.focus(); }
  _promoTyped();
  v3EnterSync(root);
}
// Кнопка «Активировать» залита акцентом, только когда код набран: иначе акцент экрана пустой кнопке не нужен (docs/MINIAPP_DESIGN_RULES.md, п. 1)
function _promoTyped() {
  const go = el('promo-go'), has = !!String(el('promo-in')?.value || '').trim();
  go?.classList.toggle('v3-pill--ghost', !has);
  const err = el('promo-err'); if (err && !_promo.busy) err.hidden = true;
}

// Один запрос за раз: и ручной ввод (code не передан), и «Забрать» у строки идут через redeem, сервер повторно проверяет всё
function promoTake(code) {
  const manual = !code, err = el('promo-err');
  code = String(code || el('promo-in')?.value || '').trim();
  if (_promo.busy) return;
  if (!code) { if (err) { err.textContent = 'Введите код.'; err.hidden = false; } return; }
  _promo.busy = manual ? '*' : code; _promoRender();
  api('/promo-v2/redeem', { method: 'POST', body: JSON.stringify({ code }) }).then(r => {
    if (manual && el('promo-in')) el('promo-in').value = '';
    _haptic('success');
    const gifts = (r.granted || []).map(text => {
      const m = /^(\p{Extended_Pictographic}[️‍\p{Extended_Pictographic}]*)\s+(\d[\d ]*)\s+(.+)$/u.exec(String(text).trim());
      return m ? { label: `${m[1]} ${m[3]}`, amount: Number(m[2].replace(/\s/g, '')) } : { label: String(text) };
    });
    v3GiftToast([{ title: 'Промокод', from: r.code, glyph: '🎟', gifts }]);
    return true;
  }).catch(e => { _haptic('error'); return String(e?.message || e || 'Не получилось.').replace(/^Error:\s*/, ''); })
    .then(result => {
      _promo.busy = '';
      if (result === true) return openPromoSheet();   // код уходит из «Доступно» в «Историю»
      _promoRender();
      const box = el('promo-err'); if (box) { box.textContent = result; box.hidden = false; }
    });
}
