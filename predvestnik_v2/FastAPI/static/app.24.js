// ── Пополнение Зарников: шторка поверх любого экрана ────────────────────────────
// Оплата идёт через Telegram Stars (/payments/zarniki/*). Баланс растёт на сервере, здесь только показ.
let _zt = null, _ztBusy = false, _ztOpener = null;
function _ztClose() {
  document.getElementById('zt-sheet')?.remove(); _zt = null; document.removeEventListener('keydown', _ztKeys, true);
  if (_ztOpener && document.contains(_ztOpener)) _ztOpener.focus({ preventScroll: true });
  _ztOpener = null;
}
function _ztKeys(e) {
  if (e.key === 'Escape') { e.preventDefault(); _ztClose(); return; }
  if (e.key !== 'Tab') return;
  const items = [...document.querySelectorAll('#zt-sheet button:not(:disabled)')]; if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}
function _ztRender() {
  let host = document.getElementById('zt-sheet');
  if (!_zt) { host?.remove(); return; }
  if (!host) {
    host = document.createElement('div'); host.id = 'zt-sheet'; host.className = 'lk-sheet-back';
    host.addEventListener('click', e => { if (e.target === host) _ztClose(); });
    document.body.appendChild(host); document.addEventListener('keydown', _ztKeys, true);
  }
  const packs = Array.isArray(_zt.packages) ? _zt.packages : [], pick = packs.find(p => Number(p.stars) === _zt.selected) || null;
  const off = _zt.purchase_disabled_reason === 'preprod' ? 'На тестовом стенде платежи отключены. В продакшене пополнение работает.' : 'Пополнение временно недоступно.';
  const bal = fmt(Number(_profileData?.zarniki || _lk?.st?.zarniki || 0));
  let body;
  if (_zt.loading) body = '<div class="sk" style="height:180px;border-radius:14px;margin-top:16px"></div>';
  else if (_zt.error) body = `<p>${_profileEsc(_zt.error)}</p><button type="button" class="v3-pill" onclick="openZarnikiTopup()">Повторить</button>`;
  else if (_zt.purchase_enabled === false) body = `<p>${off}</p>`;
  else body = `<div role="radiogroup" aria-label="Количество Зарников" style="margin-top:10px">${packs.map(p => {
      const on = Number(p.stars) === _zt.selected;
      return `<button type="button" role="radio" aria-checked="${on}" class="lk-pack${on ? ' is-on' : ''}" onclick="_ztSelect(${Number(p.stars)})" ${_ztBusy ? 'disabled' : ''}><span><b>${fmt(Number(p.total))} ✨</b><small>${p.popular ? 'Популярный набор' : 'Зарников на баланс'}</small></span><span>${Number(p.stars)} ⭐</span></button>`;
    }).join('')}</div>
    ${pick ? `<button type="button" class="v3-pill${_ztBusy ? ' is-busy' : ''}" ${_ztBusy ? 'disabled aria-busy="true"' : ''} onclick="_ztPay(${Number(pick.stars)})">${_ztBusy ? 'Открываем оплату…' : `Купить ${fmt(Number(pick.total))} за ${Number(pick.stars)} Stars`}</button>` : '<p>Выберите набор.</p>'}
    <p style="text-align:center">Оплата откроется внутри Telegram, баланс обновится сам.</p>`;
  host.innerHTML = `<section class="lk-sheet" role="dialog" aria-modal="true" aria-labelledby="zt-title"><h2 id="zt-title">Пополнить Зарники</h2><p>Сейчас на балансе ${bal} ✨</p>${body}<button type="button" class="v3-link" style="display:block;margin:10px auto 0" onclick="_ztClose()">Закрыть</button></section>`;
  if (!_zt.focused) { _zt.focused = true; host.querySelector('.lk-pack.is-on, .lk-pack, .v3-pill, .v3-link')?.focus({ preventScroll: true }); }
}
function _ztSelect(stars) { if (_zt && !_ztBusy) { _zt.selected = stars; _haptic('select'); _ztRender(); } }
function openZarnikiTopup() {
  if (!_zt) _ztOpener = document.activeElement;
  _zt = { loading: true }; _ztRender();
  return api('/payments/zarniki/packages').then(d => {
    const list = Array.isArray(d.packages) ? d.packages : [], first = list.find(p => p.popular) || list[0];
    _zt = { ...d, selected: first ? Number(first.stars) : null }; _ztRender();
  }).catch(e => { _zt = { error: String(e) }; _ztRender(); });
}
async function _ztPay(stars) {
  if (_ztBusy || !Number.isInteger(stars) || stars < 1) return;
  _ztBusy = true; _ztRender();
  try {
    const invoice = await api('/payments/zarniki/invoice', { method: 'POST', body: JSON.stringify({ stars }) });
    if (!invoice?.link) throw new Error('Счёт не создан.');
    if (typeof tg?.openInvoice === 'function') {
      tg.openInvoice(invoice.link, status => {
        if (status !== 'paid') return;
        _ztClose(); toast('Зарники начислены'); _haptic('success'); _v3RefreshBalance();
        if (_activePage === 'looks') openLooksModal();
      });
    } else location.assign(invoice.link);
  } catch (e) { toast(e, false); }
  finally { _ztBusy = false; _ztRender(); }
}
