// ── Инвентарь · всё, что есть у игрока ───────────────────────────────────────────────
// Образы, регалии, питомцы, ключи, еда, карты, джокеры и вещи прежней системы на одном экране. Образы приходят из /skins-v3/me (тот же ответ, что у витрины, личные
// образы среди них), склад из /inventory-v1/me (только чтение). Здесь только показ: действия живут на своих экранах, плитка ведёт туда. Стили: inventory-v3.css.
let _inv = { skins: null, stock: undefined, archive: null, bad: { skins: '', stock: '' }, seq: 0, tab: '' };   // stock: undefined = ещё не пришёл, null = сундуки выключены
const _INV_RANK = ['SSS', 'SS', 'S', 'A', 'B', 'C', 'D'];
const _invSettle = p => p.then(value => ({ ok: true, value }), error => ({ ok: false, error }));

function openInventory() {
  switchPage('inventory');
  const root = el('pg-inventory'); if (!root) return Promise.resolve();
  if (!_inv.skins && _inv.stock === undefined) {
    root.innerHTML = v3Head('Инвентарь', { back: 'invBack()', end: v3GuideIcon('inventory') }) + '<div class="sk" style="height:44px;border-radius:12px"></div><div class="sk" style="height:220px;border-radius:18px;margin-top:18px"></div><div class="sk" style="height:140px;border-radius:18px;margin-top:18px"></div>';
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
// Предмет — плитка сетки: значок, число в углу, короткое имя. Подробности и переход — в листе по нажатию (invItem). Ноль показан приглушённо, а не скрыт: ключ нужен всегда
// tier: ступень талисмана (одна вещь, а не стопка) — тогда в углу и в листе ступень, а не количество
function _invTile(icon, name, hint, n, sheet, tier) {
  const say = tier ? `${name}: ступень ${tier}` : `${name}: ${fmt(n)}`, mark = tier || fmt(n);
  // ключ — тот же рисунок, что на полке Сундуков (app.47.js), остальное — свой значок
  const art = sheet === 'keys' && typeof _CH_KEY_SVG !== 'undefined' ? `<span class="inv-key ch-m-iron">${_CH_KEY_SVG}</span>` : icon;
  return `<button type="button" class="inv-tile${Number(n) ? '' : ' is-zero'}" onclick="invItem('${sheet}', this)" data-name="${name}" data-hint="${hint || ''}" data-n="${Number(n)}" data-tier="${tier || ''}" data-ic="${icon}" aria-label="${say}"><span class="inv-ic" aria-hidden="true">${art}</span><b class="inv-n">${mark}</b><small>${name}</small></button>`;
}
// Лист предмета: ключи, еда, карты, джокеры и талисманы. Ничего не списывает: кнопка ведёт на экран, где предмет нужен.
const _INV_SHEET = { keys: ['К сундукам', 'openChestsV1()'], food: ['К питомцам', 'openPetsV1()'], card: ['К питомцам', 'openPetsV1()'], joker: ['К питомцам', 'openPetsV1()'], tal: ['К питомцам', 'openPetsV1()'] };
function invItem(kind, node) {
  _haptic('select');
  const go = _INV_SHEET[kind]; if (!go) return;
  const d = node.dataset;
  OM(`${d.ic} ${d.name}`, `<p class="v3-stat-line">${d.tier ? `Ступень <b>${_profileEsc(d.tier)}</b>` : `<b>${fmt(Number(d.n))}</b> в запасе`}</p>${d.hint ? `<p class="inv-note">${_profileEsc(d.hint)}</p>` : ''}`,
    [{ l: go[0], c: 'primary', f: `CM();${go[1]}` }, { l: 'Закрыть', c: 'ghost', f: 'CM()' }]);
}

function _invLookTile(i) {
  const where = i.equipped ? '<i class="lk-dot is-on" title="Надет"></i>' : '';
  const kind = i.exclusive ? 'личный · ' : i.season ? 'сезон · ' : '';
  const say = `${i.name}, тир ${i.level}${i.exclusive ? ', личный образ' : ''}${i.equipped ? ', надет' : ''}`;
  return `<button type="button" class="lk-pick" onclick="invOpenLook('${i.id}')" aria-label="${_profileEsc(say)}">${_lkMini(i)}<b>${_profileEsc(i.name)}</b><small>${where}${kind}тир ${_profileEsc(i.level)}</small></button>`;
}
function _invLooks(st) {
  if (!st) return _invFail('Образы не загрузились', _inv.bad.skins) + _invMarks();   // регалии из профиля, не из ответа образов
  const mine = _invOwned(st), c = st.collection;
  const body = mine.length ? `<div class="inv-looks">${mine.map(_invLookTile).join('')}</div>`
    : `<div class="v3-empty">Образов пока нет. <button type="button" class="v3-link" onclick="openLooksModal()">Открыть образы ›</button></div>`;
  return `${_invSec(c ? `Образы · ${c.owned} из ${c.total}` : 'Образы', '<button type="button" class="v3-link" onclick="openLooksModal()">Все образы ›</button>')}${body}${_invMarks()}`;
}
function _invMarks() {
  const marks = typeof _profileData !== 'undefined' && Array.isArray(_profileData?.marks) ? _profileData.marks : [];
  return marks.length && typeof v3MarksHtml === 'function' ? `${_invSec('Регалии')}${v3MarksHtml(marks, { own: true })}` : '';
}

function _invPets(stock) {
  const pets = stock.pets || [];
  const tile = p => `<button type="button" class="inv-pet${p.active ? ' is-on' : ''}" onclick="openPetsV1()" aria-label="${_profileEsc(`${p.name}, ${rarLabel(p.rarity)}, уровень ${p.level}${p.active ? ', с вами' : ''}`)}"><span class="inv-ic" aria-hidden="true">${_profileEsc(p.icon)}</span><b>${_profileEsc(p.name)}</b><small>${_profileEsc(rarLabel(p.rarity))} · ур. ${_profileEsc(p.level)}${p.active ? '<br>с\u00a0вами' : ''}</small></button>`;
  const body = pets.length ? `<div class="inv-pets">${pets.map(tile).join('')}</div>` : '<div class="v3-empty">Питомцев пока нет. Первую карточку можно найти в сундуке.</div>';
  return `${_invSec(`Виды · ${pets.length} из ${stock.species_total}`, '<button type="button" class="v3-link" onclick="openPetsV1()">К питомцам ›</button>')}${body}`;
}
// Талисман питомцев: одна вещь, а не стопка, поэтому в углу его ступень; имя и значок те же, что на экранах Тропы (app.41.js), на ком надет берём из списка питомцев склада
function _invTal(t, stock) {
  const known = typeof _TR_TAL !== 'undefined' && _TR_TAL[t.kind], tier = ['', 'I', 'II', 'III'][Number(t.tier)] || String(t.tier);
  const pet = t.pet_id ? (stock.pets || []).find(p => p.id === t.pet_id) : null;
  const e = t.effects, route = id => typeof _TR_ROUTE !== 'undefined' && _TR_ROUTE[id] ? _TR_ROUTE[id][1] : id;
  const effect = e ? `${route(e.route)}: +${e.plus_percent}% Следов. ${route(e.opposite)}: −${e.minus_percent}% Следов. Два одной темы: ещё +${e.set_percent}% на своём маршруте. Эффекты перемножаются. ` : '';
  const holder = pet ? `Носит ${pet.name}` : 'Свободен';
  return _invTile(known ? known[0] : '🧿', _profileEsc(known ? known[1] : t.name), _profileEsc(effect + holder), 1, 'tal', tier);
}
function _invStuff(stock) {
  const grid = (title, tiles, link) => tiles.length ? `${_invSec(title, link)}<div class="inv-grid">${tiles.join('')}</div>` : '';
  // ключи — в сводке сверху (одно число не показывается дважды); их лист открывает клетка сводки
  const use = [...stock.foods.map(f => _invTile(_profileEsc(f.icon), _profileEsc(f.name), `${stock.pets_version === 2 ? 'Силы' : 'Выносливость'} питомца +${_profileEsc(f.restore)}`, f.quantity, 'food'))];
  const keptCards = stock.pets_version === 2 ? 'Сохранено из прежней системы. В Тропе не расходуется.' : '';
  const cards = [...stock.pet_cards.map(c => _invTile(_profileEsc(c.icon), _profileEsc(c.name), keptCards || _profileEsc(rarLabel(c.rarity)), c.quantity, 'card')),
    ...stock.jokers.map(j => _invTile('🃏', `Джокер · ${_profileEsc(rarLabel(j.rarity).toLowerCase())}`, keptCards || 'Заменяет карту любого питомца своей редкости', j.quantity, 'joker'))];
  // Сводка запаса крупными числами с картинками: сколько ключей, еды, карт и талисманов — до списков
  const sumN = list => list.reduce((n, x) => n + Number(x.quantity || 0), 0);
  const cell = (art, n, label) => `<div class="inv-sum-c"><span class="inv-sum-art" aria-hidden="true">${art}</span><b>${fmt(n)}</b><small>${label}</small></div>`;
  const keyArt = typeof _CH_KEY_SVG !== 'undefined' ? `<span class="inv-key">${_CH_KEY_SVG}</span>` : '🗝';
  const keyCell = `<button type="button" class="inv-sum-c" onclick="invItem('keys', this)" data-name="Ключи" data-hint="Один ключ открывает один сундук" data-n="${Number(stock.keys)}" data-tier="" data-ic="🗝" aria-label="Ключи: ${fmt(stock.keys)}"><span class="inv-sum-art" aria-hidden="true">${keyArt}</span><b>${fmt(stock.keys)}</b><small>ключей</small></button>`;
  const summary = `<div class="inv-sum" aria-label="Запас">${keyCell}${cell(_profileEsc(stock.foods[0]?.icon || '🍲'), sumN(stock.foods), 'еды')}${cell(_profileEsc(stock.pet_cards[0]?.icon || '🃏'), sumN(stock.pet_cards) + sumN(stock.jokers), 'карт')}${cell('🧿', (stock.talismans || []).length, 'талисманов')}</div>`;
  return summary + grid('Еда', use, '<button type="button" class="v3-link" onclick="openChestsV1()">К сундукам ›</button>')
    + grid('Карты и джокеры', cards) + grid('Талисманы', (stock.talismans || []).map(t => _invTal(t, stock)));
}
function _invArchive(archive) {
  const row = i => `<li class="inv-item"><span class="inv-ic" aria-hidden="true">${_profileEsc(i.icon || '▫')}</span><span class="inv-nm"><b>${_profileEsc(i.name)}</b>${i.note ? `<small>${_profileEsc(i.note)}</small>` : ''}</span><span class="inv-n">${fmt(i.quantity)}</span></li>`;
  const group = g => `<details class="inv-grp"><summary><span aria-hidden="true">${_profileEsc(g.icon)}</span><b>${_profileEsc(g.title)}</b><em>${fmt(g.pieces)}</em></summary><ul class="inv-list">${g.items.map(row).join('')}</ul></details>`;
  return `<p class="inv-note">Вещи прежней игры сохранены за вами. Большинство из них сейчас нигде не расходуется.</p>${archive.groups.map(group).join('')}`;
}

// Вкладки вместо длинной ленты: предметы (то, что применяют), питомцы, образы, архив. Итог раздела — в подзаголовке раздела, на вкладке числа нет (одно число — одно место)
const _INV_TABS = [['stuff', 'Предметы'], ['pets', 'Питомцы'], ['looks', 'Образы'], ['archive', 'Архив']];
function _invTabs(shown) {
  const tabs = _INV_TABS.filter(([id]) => shown[id]);
  return `<nav class="v3-tabs v3-tabs--wide inv-tabs" role="tablist" aria-label="Разделы инвентаря" onkeydown="invTabKey(event)">${tabs.map(([id, label]) =>
    `<button type="button" id="inv-tab-${id}" class="v3-tab${_inv.tab === id ? ' on' : ''}" role="tab" aria-selected="${_inv.tab === id}" aria-controls="inv-panel" tabindex="${_inv.tab === id ? 0 : -1}" onclick="invTab('${id}')">${label}</button>`).join('')}</nav>`;
}
function invTab(id) {
  if (_inv.tab === id) return;
  _haptic('select'); _inv.tab = id; _invRender();
}
function invTabKey(e) {
  const tabs = [...e.currentTarget.querySelectorAll('[role="tab"]')], at = tabs.indexOf(document.activeElement);
  const to = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: tabs.length - 1 }[e.key];
  if (at < 0 || to === undefined) return;
  const tab = tabs[(to + tabs.length) % tabs.length];
  e.preventDefault(); tab.click();
  el(tab.id)?.focus();   // перерисовка заменяет кнопки: фокус клавиатуры возвращается на выбранную вкладку
}

function _invRender() {
  const root = el('pg-inventory'); if (!root) return;
  const st = _inv.skins, stock = _inv.stock, archive = _inv.archive?.kinds ? _inv.archive : null;
  const shown = { stuff: stock !== null, pets: stock !== null, looks: true, archive: !!archive };   // stock === null: сундуки выключены, склада нет
  if (!shown[_inv.tab]) _inv.tab = stock === null ? 'looks' : 'stuff';
  const need = stock === undefined && _inv.tab !== 'looks' ? _invFail('Склад не загрузился', _inv.bad.stock) : '';
  const body = need || { stuff: () => _invStuff(stock), pets: () => _invPets(stock), looks: () => _invLooks(st), archive: () => _invArchive(archive) }[_inv.tab]();
  root.innerHTML = `${v3Head('Инвентарь', { back: 'invBack()', end: v3GuideIcon('inventory') })}${_invTabs(shown)}<div class="inv-body" id="inv-panel" role="tabpanel" aria-labelledby="inv-tab-${_inv.tab}">${body}</div>`;
  v3EnterSync(root);
}

// Кнопка-рюкзак в верхней панели (она же прежний колокол): короткое меню из двух строк, точка «есть новое» остаётся на кнопке
function openBarMenu() {
  _haptic('select');
  const row = (go, name, hint, icon) => `<button type="button" class="v3-row" onclick="CM();${go}">${icon}<span>${name}<small>${hint}</small></span><span class="v3-end"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg></span></button>`;
  const bag = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5.2V4.5a3 3 0 0 1 6 0v.7"/><path d="M6.5 5.2h11A2.5 2.5 0 0 1 20 7.7v10.8a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 18.5V7.7a2.5 2.5 0 0 1 2.5-2.5z"/><path d="M4 11.5h16M10.5 11.5v2.5h3v-2.5"/></svg>';
  const bell = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15zM10 20a2 2 0 0 0 4 0"/></svg>';
  const fresh = document.querySelector('[data-wn-btn].has-new') ? ' · есть новое' : '';
  OM('Меню', row('openInventory()', 'Инвентарь', 'Образы, питомцы, ключи и вещи', bag) + row('openWhatsNew()', 'Что нового', `Обновления Предвестника${fresh}`, bell), [{ l: 'Закрыть', c: 'ghost', f: 'CM()' }]);
}
// Рюкзак открывается с любого экрана: «‹» возвращает туда, откуда пришли, а без истории ведёт в профиль
function invBack() { if (typeof _navStack !== 'undefined' && _navStack.length) navBack(); else switchPage('profile'); }
// Образ из инвентаря открывается там, где его надевают, растят и покупают следующий
function invOpenLook(id) {
  _haptic('select');
  _lk.view = 'shop';
  if (_lk.st) _lkPick(id); else _lk.sel = id;   // выбранный образ остаётся и после свежего ответа (openLooksModal берёт _lk.sel)
  openLooksModal();
}
