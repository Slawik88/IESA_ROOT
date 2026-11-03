// Общее состояние открытого приложения. Черновики, суммы и фото живут только здесь — не в хранилище браузера.
import { formatDay, formatMoney, relativeDay } from './format.js';
import { locale, t } from './i18n.js';

export const DEFAULT_FILTERS = { kind: 'all', member: '', category: '', mode: 'all', sort: 'newest' };

export const app = {
  api: null,
  houses: [], houseId: null, data: null,
  view: 'home', sub: null,
  month: '', allMonths: false, query: '', filters: { ...DEFAULT_FILTERS },
  rows: [], pages: 1,
  drafts: new Map(),
};

// Переходы между экранами задаёт main.js; экраны вызывают их, не зная друг о друге.
export const nav = { go() {}, redraw() {} };

export const money = (kop, options) => formatMoney(kop, locale, app.data?.currency ?? '', options);
export const day = (iso, options) => formatDay(iso, locale, options);
export const dayLabel = (iso, options) => relativeDay(iso, app.data.today, locale,
  { today: t("Сегодня"), yesterday: t("Вчера") }, options);

// Сколько условий кроме типа записи и поиска сейчас сужает список (для счётчика на кнопке «Фильтры»).
export function advancedFilterCount() {
  const { member, category, mode, sort } = app.filters;
  return [member, category, mode !== 'all', sort !== 'newest'].filter(Boolean).length;
}

export const houseDrafts = () => [...app.drafts.values()].filter(draft => draft.house === app.houseId);
