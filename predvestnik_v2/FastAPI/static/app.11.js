// ═══ app.11.js — shared item descriptions ═══
//
// The former grid-combat client deliberately does not ship in the active
// bundle. Reconstruction is the only combat entry point. This small shared
// surface remains because craft/inventory cards use itemLink() while their
// catalog is migrated independently.

const ITEM_INFO = Object.freeze({
  _fallback: Object.freeze({
    emoji: '🎁',
    name: 'Предмет',
    type: '',
    what: 'Предмет из твоего инвентаря.',
    why: 'Назначение указано в рецепте или экране, где он используется.',
    where_get: 'Открой источник в карточке предмета.',
    where_use: 'Доступные действия показаны рядом с предметом.',
  }),
});

function itemLink(key, label) {
  const value = esc(label != null ? label : key);
  if (!Object.prototype.hasOwnProperty.call(ITEM_INFO, key)) return value;
  return `<span class="tlink" onclick="event.stopPropagation();showItemDetail('${key}')">${value}</span>`;
}

function tabLink(label, page, tab) {
  const targetTab = tab ? `,'${tab}'` : '';
  return `<span class="tlink tlink--go" onclick="event.stopPropagation();goTo('${page}'${targetTab})">${esc(label)}</span>`;
}

function showItemDetail(key, override) {
  const info = Object.assign({}, ITEM_INFO[key] || ITEM_INFO._fallback, override || {});
  OM(`${info.emoji} ${esc(info.name)}`, `
    ${info.type ? `<div class="ii-chip">${esc(info.type)}</div>` : ''}
    <div class="looks-slot-t">Что это</div>
    <div class="cx-dim" style="font-size:12px;line-height:1.45">${esc(info.what)}</div>
    <div class="looks-slot-t" style="margin-top:8px">Зачем нужно</div>
    <div class="cx-dim" style="font-size:12px;line-height:1.45">${esc(info.why)}</div>
    <div class="looks-slot-t" style="margin-top:8px">Где взять</div>
    <div class="cx-dim" style="font-size:12px;line-height:1.45">${esc(info.where_get)}</div>
    <div class="looks-slot-t" style="margin-top:8px">Где применить</div>
    <div class="cx-dim" style="font-size:12px;line-height:1.45">${esc(info.where_use)}</div>
  `, [{ l: 'Закрыть', c: 'btn-ghost', f: 'CM()' }]);
}
