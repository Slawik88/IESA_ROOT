// Строка записи (расход или взнос): одинакова на главной и в истории.
import { t } from '../i18n.js';
import { badge, h, icon } from '../ui.js';
import { dayLabel, money } from '../state.js';

export function categoryIcon(name) {
  const text = (name ?? '').toLowerCase(); // у расхода без категории сервер присылает null
  if (!name) return 'receipt';
  if (text.includes('продукт')) return 'bag';
  if (text.includes('хими') || text.includes('уборк')) return 'spark';
  if (text.includes('коммун')) return 'bulb';
  if (text.includes('ремонт')) return 'tool';
  return 'tag';
}

export const entryIconName = entry => (entry.kind === 'contribution' ? 'wallet' : categoryIcon(entry.category));
export const entryTitle = entry => (entry.kind === 'contribution' ? t("Взнос") : entry.description || entry.category || t("Расход"));
export const entryMeta = entry => `${entry.display_name || t("Жилец")} · ${dayLabel(entry.date)}`;

export function entryBadge(entry) {
  if (entry.kind === 'contribution') {
    if (entry.status === 'declared') return badge(t("Ждёт подтверждения"), 'warn');
    if (entry.status === 'rejected') return badge(t("Отклонён"), 'bad');
    return null;
  }
  if (entry.mode !== 'personal') return null;
  return entry.reimbursed ? badge(t("Возвращено"), 'ok') : badge(t("Ждёт возврата"), 'warn');
}

// Сумма со знаком: взнос — «+», расход — «−»; решённость взноса видна по цвету и по бейджу.
export function entryAmount(entry) {
  if (entry.kind === 'expense') return { text: money(-entry.amount_kop), className: 'amt' };
  const className = entry.status === 'confirmed' ? 'amt amt-in' : entry.status === 'rejected' ? 'amt amt-off' : 'amt amt-wait';
  return { text: money(entry.amount_kop, { plus: true }), className };
}

export function entryRow(entry, onOpen) {
  const amount = entryAmount(entry);
  return h('button', { type: 'button', class: `row entry${entry.kind === 'contribution' ? ' is-in' : ''}`, onClick: () => onOpen(entry) },
    h('span', { class: 'row-icon' }, icon(entryIconName(entry))),
    h('span', { class: 'row-main' },
      h('span', { class: 'row-title' }, entryTitle(entry)),
      h('span', { class: 'row-meta' }, entryMeta(entry)),
      entryBadge(entry)),
    h('span', { class: 'row-end' }, h('span', { class: amount.className }, amount.text), icon('chevron-right', 'row-chevron')));
}
