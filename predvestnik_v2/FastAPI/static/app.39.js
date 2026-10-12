// ── Инвентарь · всё, что есть у игрока ───────────────────────────────────────────────
// Образы, регалии, питомцы, ключи, еда, карты, джокеры и вещи прежней системы на одном экране. Образы приходят из /skins-v3/me (тот же ответ, что у витрины, личные
// образы среди них), склад из /inventory-v1/me (только чтение). Здесь только показ: действия живут на своих экранах, плитка ведёт туда. Стили: inventory-v3.css.
let _inv = { skins: null, stock: undefined, archive: null, bad: { skins: '', stock: '' }, seq: 0 };   // stock: undefined = ещё не пришёл, null = сундуки выключены
const _INV_RANK = ['SSS', 'SS', 'S', 'A', 'B', 'C', 'D'];
const _invWord = (n, one, few, many) => { const m = Math.abs(n) % 100, d = m % 10; return m > 10 && m < 20 ? many : d === 1 ? one : d > 1 && d < 5 ? few : many; };
const _invSettle = p => p.then(value => ({ ok: true, value }), error => ({ ok: false, error }));

function openInventory() {
  switchPage('inventory');
  const root = el('pg-inventory'); if (!root) return Promise.resolve();
  if (!_inv.skins && _inv.stock === undefined) {
    root.innerHTML = '<div class="eyebrow-row"><button type="button" class="v3-link" onclick="switchPage(\'profile\')" aria-label="Назад в профиль">‹ Профиль</button></div><div class="sk" style="height:96px;border-radius:18px;margin-top:12px"></div><div class="sk" style="height:220px;border-radius:18px;margin-top:18px"></div><div class="sk" style="height:140px;border-radius:18px;margin-top:18px"></div>';
    v3EnterSync(root);
  }
  const mine = ++_inv.seq;
  return Promise.all([_invSettle(api('/skins-v3/me')), _invSettle(api('/inventory-v1/me'))]).then(([skins, stock]) => {
    if (mine !== _inv.seq) return;
    _inv.bad = { skins: skins.ok ? '' : String(skins.error || 'Ошибка'), stock: stock.ok ? '' : String(stock.error || 'Ошибка') };
    if (skins.ok) _inv.skins = skins.value;
    if (stock.ok) { _inv.stock = stock.value.stock; _inv.archive = stock.value.archive; }
    _invRender();
  });
}

// Образы игрока: надетый первым, дальше по тиру, на котором они сейчас, и по имени. Личные (выданные вручную) среди них, у них своя пометка.
function _invOwned(st) {
  const rank = tier => { const n = _INV_RANK.indexOf(tier); return n < 0 ? 99 : n; };
  return (st?.items || []).filter(i => i.owned).sort((a, b) => (b.equipped - a.equipped) || (rank(a.level) - rank(b.level)) || String(a.name).localeCompare(String(b.name), 'ru'));
}
function _invSec(title, link) { return `<div class="v3-sec"><span class="v3-eyebrow">${title}</span>${link || ''}</div>`; }
function _invFail(text, retry) {
  return `<div class="v3-empty" role="alert"><b>${_profileEsc(text)}</b><span>${_profileEsc(retry)}</span> <button type="button" class="v3-link" onclick="openInventory()">Повторить</button></div>`;
}
function _invRow(icon, name, hint, n) {
  return `<li class="inv-item"><span class="inv-ic" aria-hidden="true">${icon}</span><span class="inv-nm"><b>${name}</b>${hint ? `<small>${hint}</small>` : ''}</span><span class="inv-n">${fmt(n)}</span></li>`;
}

function _invLookTile(i) {
  const where = i.equipped ? '<i class="lk-dot is-on" title="Надет"></i>' : '';
  const kind = i.exclusive ? 'личный · ' : i.season ? 'сезон · ' : '';
  const say = `${i.name}, тир ${i.level}${i.exclusive ? ', личный образ' : ''}${i.equipped ? ', надет' : ''}`;
  return `<button type="button" class="lk-pick" onclick="invOpenLook('${i.id}')" aria-label="${_profileEsc(say)}">${_lkMini(i)}<b>${_profileEsc(i.name)}</b><small>${where}${kind}тир ${_profileEsc(i.level)}</small></button>`;
}
function _invLooks(st) {
  if (!st) return `<section class="inv-sec" id="inv-looks">${_invSec('Мои образы')}${_invFail('Образы не загрузились', _inv.bad.skins)}</section>`;
  const mine = _invOwned(st), personal = mine.filter(i => i.exclusive).length, c = st.collection;
  const facts = [c ? `в коллекции ${c.owned} из ${c.total}` : '', personal ? `личных ${personal}` : ''].filter(Boolean).join(' · ');
  const body = mine.length ? `<div class="inv-looks">${mine.map(_invLookTile).join('')}</div>`
    : `<div class="v3-empty">Образов пока нет. Первый купленный появится здесь. <button type="button" class="v3-link" onclick="openLooksModal()">Открыть образы ›</button></div>`;
  return `<section class="inv-sec" id="inv-looks">${_invSec(`Мои образы · ${mine.length}`, '<button type="button" class="v3-link" onclick="openLooksModal()">Все образы ›</button>')}${mine.length ? `<p class="inv-note">${facts ? `${_profileEsc(facts)}. ` : ''}Нажмите на образ: он откроется там, где его надевают и растят.</p>` : ''}${body}</section>`;
}
function _invMarks() {
  const marks = typeof _profileData !== 'undefined' && Array.isArray(_profileData?.marks) ? _profileData.marks : [];
  return `<section class="inv-sec" id="inv-marks">${_invSec('Регалии')}${typeof v3MarksHtml === 'function' ? v3MarksHtml(marks, { own: true }) : ''}</section>`;
}

function _invPets(stock) {
  const pets = stock.pets || [];
  const tile = p => `<button type="button" class="inv-pet${p.active ? ' is-on' : ''}" onclick="openPetsV1()"><span class="inv-pet-ic" aria-hidden="true">${_profileEsc(p.icon)}</span><span class="inv-nm"><b>${_profileEsc(p.name)}</b><small>${_profileEsc(rarLabel(p.rarity))} · ур.\u00a0${_profileEsc(p.level)}${p.active ? ' · с\u00a0вами' : ''}</small></span></button>`;
  const body = pets.length ? `<div class="inv-pets">${pets.map(tile).join('')}</div>` : '<div class="v3-empty">Питомцев пока нет. Первую карточку можно найти в сундуке.</div>';
  return `<section class="inv-sec" id="inv-pets">${_invSec(`Питомцы · ${pets.length} из ${stock.species_total}`, '<button type="button" class="v3-link" onclick="openPetsV1()">К питомцам ›</button>')}${body}</section>`;
}
function _invStuff(stock) {
  const group = (title, rows, note) => `<h3 class="inv-sub">${title}</h3>${note ? `<p class="inv-note">${note}</p>` : ''}<ul class="inv-list">${rows.join('')}</ul>`;
  const parts = [group('Ключи', [_invRow('🗝', 'Ключи', 'Один ключ открывает один сундук', stock.keys)])];
  if (stock.foods.length) parts.push(group('Еда питомцев', stock.foods.map(f => _invRow(_profileEsc(f.icon), _profileEsc(f.name), `Выносливость питомца +${_profileEsc(f.restore)}`, f.quantity))));
  if (stock.pet_cards.length) parts.push(group('Карты питомцев', stock.pet_cards.map(c => _invRow(_profileEsc(c.icon), _profileEsc(c.name), _profileEsc(rarLabel(c.rarity)), c.quantity))));
  if (stock.jokers.length) parts.push(group('Джокеры', stock.jokers.map(j => _invRow('🃏', `Джокер · ${_profileEsc(rarLabel(j.rarity).toLowerCase())}`, '', j.quantity)), 'Джокер заменяет карту любого питомца своей редкости.'));
  return `<section class="inv-sec" id="inv-stuff">${_invSec('Ключи и предметы', '<button type="button" class="v3-link" onclick="openChestsV1()">К сундукам ›</button>')}${parts.join('')}</section>`;
}
function _invArchive(archive) {
  if (!archive || !archive.kinds) return '';
  const group = g => `<details class="inv-grp"><summary><span aria-hidden="true">${_profileEsc(g.icon)}</span><b>${_profileEsc(g.title)}</b><em>${fmt(g.pieces)}</em></summary><ul class="inv-list">${g.items.map(i => _invRow(_profileEsc(i.icon || '▫'), _profileEsc(i.name), _profileEsc(i.note), i.quantity)).join('')}</ul></details>`;
  return `<section class="inv-sec" id="inv-archive">${_invSec(`Архив прежней системы · ${archive.kinds}`)}<p class="inv-note">Вещи прежней игры сохранены за вами. Большинство из них сейчас нигде не расходуется.</p>${archive.groups.map(group).join('')}</section>`;
}

function _invChips(owned, stock, archive) {
  const chip = (id, n, label, extra) => `<button type="button" class="inv-chip" onclick="invJump('${id}')"><b>${fmt(n)}</b><span>${label}</span>${extra || ''}</button>`;
  const list = [chip('looks', owned, _invWord(owned, 'образ', 'образа', 'образов'))];
  if (stock) {
    list.push(chip('pets', (stock.pets || []).length, _invWord((stock.pets || []).length, 'питомец', 'питомца', 'питомцев')));
    list.push(chip('stuff', stock.keys, _invWord(stock.keys, 'ключ', 'ключа', 'ключей')));
  }
  if (archive?.kinds) list.push(chip('archive', archive.kinds, 'в архиве'));
  return `<nav class="inv-chips" aria-label="Разделы инвентаря">${list.join('')}</nav>`;
}

function _invRender() {
  const root = el('pg-inventory'); if (!root) return;
  const st = _inv.skins, stock = _inv.stock, owned = _invOwned(st).length;
  const stockBlock = stock === undefined ? `<section class="inv-sec">${_invFail('Склад не загрузился', _inv.bad.stock)}</section>` : stock ? `${_invPets(stock)}${_invStuff(stock)}` : '';
  root.innerHTML = `<div class="eyebrow-row"><button type="button" class="v3-link" onclick="switchPage('profile')" aria-label="Назад в профиль">‹ Профиль</button></div>
    <header class="v3-screen-head"><span class="v3-eyebrow">Всё ваше</span><h1 class="v3-title">Инвентарь${v3GlintMark('Инвентарь')}</h1><p class="v3-sub">Образы, питомцы, ключи и вещи в одном месте.</p></header>
    ${_invChips(owned, stock, _inv.archive)}${_invLooks(st)}${_invMarks()}${stockBlock}${_invArchive(_inv.archive)}`;
  v3EnterSync(root);
}

function invJump(id) {
  _haptic('select');
  const still = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.getElementById(`inv-${id}`)?.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' });
}
// Образ из инвентаря открывается там, где его надевают, растят и покупают следующий
function invOpenLook(id) {
  _haptic('select');
  _lk.view = 'shop';
  if (_lk.st) _lkPick(id); else _lk.sel = id;   // выбранный образ остаётся и после свежего ответа (openLooksModal берёт _lk.sel)
  openLooksModal();
}
