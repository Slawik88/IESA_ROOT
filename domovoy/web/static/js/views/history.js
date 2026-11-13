// История: месяц, поиск, быстрые фильтры, итоги и список записей по дням.
import { locale, t } from '../i18n.js';
import { formatMonth, monthNames, shiftMonth } from '../format.js';
import { advancedFilterCount, app, dayLabel, money } from '../state.js';
import { applySelection, loadMore, resetSelection } from '../data.js';
import { busy, button, chip, emptyState, fail, h, icon, iconButton, openSheet, setChip, toast } from '../ui.js';
import { entryRow } from './entries.js';
import { openEntry } from './entry.js';
import { openFiles } from './files.js';
import { openForm } from './form.js';

const SEARCH_DELAY_MS = 250;
const SEARCH_LIMIT = 80;

async function apply(patch) {
  try { await applySelection(patch); }
  catch (error) { fail(error); }
}

const withFilters = patch => ({ filters: { ...app.filters, ...patch } });

function openMonths() {
  let year = Number((app.month || app.data.today.slice(0, 7)).slice(0, 4));
  const names = monthNames(locale);
  const yearLabel = h('span', { class: 'year-label' });
  const grid = h('div', { class: 'month-grid' });
  const sheet = openSheet({ title: t("Выберите месяц"), size: 'sm', body: [
    h('div', { class: 'year-bar' },
      iconButton({ icon: 'chevron-left', label: t("Предыдущий год"), onClick: () => { year -= 1; paint(); } }), yearLabel,
      iconButton({ icon: 'chevron-right', label: t("Следующий год"), onClick: () => { year += 1; paint(); } })),
    grid,
  ], footer: button({ label: t("За всё время"), variant: 'secondary', block: true, onClick: () => { sheet.close(); apply({ allMonths: true }); } }) });
  function paint() {
    yearLabel.textContent = String(year);
    grid.replaceChildren(...names.map((name, index) => {
      const value = `${String(year).padStart(4, '0')}-${String(index + 1).padStart(2, '0')}`;
      return chip({ label: name, pressed: !app.allMonths && app.month === value, onClick: () => { sheet.close(); apply({ month: value, allMonths: false }); } });
    }));
  }
  paint();
}

function openFilters() {
  const draft = { ...app.filters };
  const people = new Map(app.data.members.map(member => [member.tg_id, member.display_name]));
  for (const person of app.data.filter_members ?? []) people.set(person.id, person.name);
  const groups = [
    ['member', t("Кто"), [['', t("Все жильцы")], ...[...people].map(([id, name]) => [String(id), name])]],
    ['category', t("Категория"), [['', t("Все категории")], ...app.data.categories.map(category => [String(category.id), category.name])]],
    ['mode', t("Откуда деньги"), [['all', t("Любой источник")], ['house', t("Из общего котла")], ['personal', t("За свои")], ['waiting_return', t("Ждёт возврата")]]],
    ['sort', t("Порядок"), [['newest', t("Сначала новые")], ['oldest', t("Сначала старые")], ['largest', t("Сначала крупные")], ['smallest', t("Сначала небольшие")]]],
  ];
  const sheet = openSheet({
    title: t("Фильтры"),
    body: groups.map(([key, title, options]) => {
      const nodes = options.map(([value, label]) => chip({ label, pressed: String(draft[key]) === value, onClick: () => {
        draft[key] = value;
        nodes.forEach((node, index) => setChip(node, options[index][0] === value));
      } }));
      return h('fieldset', { class: 'filter-group' }, h('legend', {}, title), h('div', { class: 'chips-wrap' }, nodes));
    }),
    footer: [
      button({ label: t("Показать записи"), block: true, onClick: () => { sheet.close(); apply({ filters: { ...app.filters, ...draft } }); } }),
      button({ label: t("Сбросить"), variant: 'ghost', block: true, onClick: () => {
        sheet.close();
        apply({ filters: { ...app.filters, member: '', category: '', mode: 'all', sort: 'newest' } });
      } }),
    ],
  });
}

function openTotals() {
  const { summary, analytics } = app.data;
  const total = summary.expenses;
  const stats = [[t("Траты"), summary.expenses], [t("Зачтённые взносы"), summary.contributions],
    [t("Ждут подтверждения"), summary.pending], [t("Ждут возврата"), summary.waiting_return]];
  openSheet({
    title: t("Итоги выбранного"),
    body: [
      h('dl', { class: 'facts facts-grid' }, stats.map(([label, value]) => h('div', {}, h('dt', {}, label), h('dd', {}, money(value))))),
      h('h3', { class: 'sheet-subtitle' }, t("На что потратили")),
      h('p', { class: 'row-meta' }, t("По всей выборке, включая покупки за свои. Возврат не считается второй покупкой.")),
      analytics.categories.length ? analytics.categories.map(category => {
        const bar = h('meter', { min: 0, max: total, value: category.amount_kop,
          'aria-label': t("{0}: {1} из {2}", [category.name, money(category.amount_kop), money(total)]) });
        return h('div', { class: 'breakdown' }, h('div', { class: 'breakdown-line' }, h('span', {}, category.name), h('strong', {}, money(category.amount_kop))), bar);
      }) : h('p', { class: 'panel-note' }, t("В выбранных записях нет расходов.")),
      h('h3', { class: 'sheet-subtitle' }, t("По жильцам")),
      analytics.members.length ? analytics.members.map(person => h('div', { class: 'breakdown' },
        h('div', { class: 'breakdown-line' }, h('strong', {}, person.name)),
        [['contributions', t("Внёс")], ['expenses', t("Записал расходов")], ['waiting_return', t("Ждёт возврата")]].map(([key, label]) =>
          h('div', { class: 'breakdown-line' }, h('span', { class: 'row-meta' }, label), h('span', { class: 'amt' }, money(person[key])))),
      )) : h('p', { class: 'panel-note' }, t("Нет записей по выбранным условиям.")),
    ],
  });
}

function dayGroups(rows) {
  const grouped = ['newest', 'oldest'].includes(app.filters.sort);
  const out = [];
  let previous = '';
  for (const entry of rows) {
    if (grouped && entry.date !== previous) {
      out.push(h('h2', { class: 'day-heading' }, dayLabel(entry.date, { day: 'numeric', month: 'long', year: 'numeric' })));
      previous = entry.date;
    }
    out.push(entryRow(entry, openEntry));
  }
  return out;
}

export function createHistory(root) {
  let timer = null;
  const eyebrow = h('p', { class: 'eyebrow' });
  const previous = iconButton({ icon: 'chevron-left', label: t("Предыдущий месяц"), onClick: () => shift(-1) });
  const next = iconButton({ icon: 'chevron-right', label: t("Следующий месяц"), onClick: () => shift(1) });
  const monthLabel = h('span', { class: 'month-label' });
  const monthButton = h('button', { type: 'button', class: 'month-btn', 'aria-haspopup': 'dialog', onClick: openMonths },
    monthLabel, icon('chevron-down'));
  const search = h('input', { type: 'search', class: 'input search-input', maxlength: SEARCH_LIMIT, enterkeyhint: 'search',
    placeholder: t("Покупка, имя или дата"), 'aria-label': t("Поиск операций"), autocomplete: 'off' });
  const clear = iconButton({ icon: 'x', label: t("Очистить поиск"), className: 'search-clear', onClick: () => {
    search.value = '';
    queryChanged();
    search.focus();
  } });
  const kindChips = [['all', t("Все записи")], ['expense', t("Расходы")], ['contribution', t("Взносы")]]
    .map(([value, label]) => ({ value, node: chip({ label, onClick: () => apply(withFilters({ kind: app.filters.kind === value ? 'all' : value })) }) }));
  const mine = chip({ label: t("Мои записи"), onClick: () => apply(withFilters({
    member: String(app.filters.member) === String(app.data.actor) ? '' : String(app.data.actor) })) });
  const waiting = chip({ label: t("Ждут возврата"), onClick: () => {
    const on = app.filters.mode === 'waiting_return' && app.allMonths;
    apply(on ? { ...withFilters({ mode: 'all' }), allMonths: false } : { ...withFilters({ mode: 'waiting_return', kind: 'expense' }), allMonths: true });
  } });
  const filterLabel = h('span', {});
  const filterButton = h('button', { type: 'button', class: 'chip chip-filter', 'aria-haspopup': 'dialog', onClick: openFilters },
    icon('sliders'), filterLabel);
  const summary = h('div', { class: 'summary-line' });
  const list = h('div', { class: 'list' });
  const more = h('div', { class: 'load-more' });

  root.replaceChildren(
    h('header', { class: 'page-head page-head-row' },
      h('div', {}, eyebrow, h('h1', { id: 'history-title', tabindex: '-1' }, t("История"))),
      h('div', { class: 'head-actions' },
        button({ label: t("Файлы"), icon: 'file', size: 'sm', variant: 'secondary', onClick: openFiles }),
        button({ label: t("Расход"), icon: 'plus', size: 'sm', onClick: () => openForm({ kind: 'expense' }) }))),
    h('div', { class: 'month-bar' }, previous, monthButton, next),
    h('div', { class: 'search' }, icon('search', 'search-icon'), search, clear),
    h('div', { class: 'chips', role: 'group', 'aria-label': t("Быстрые фильтры") }, ...kindChips.map(item => item.node), mine, waiting, filterButton),
    summary, list, more);

  function queryChanged() {
    clearTimeout(timer);
    timer = setTimeout(() => apply({ query: search.value }), SEARCH_DELAY_MS);
  }
  search.addEventListener('input', queryChanged);

  async function shift(delta) {
    const month = shiftMonth(app.month || app.data.today.slice(0, 7), delta);
    if (month) await apply({ month, allMonths: false });
    else toast(t("Выберите месяц от 0001 до 9999 года"), { kind: 'error' });
  }

  function update() {
    const { data } = app;
    eyebrow.textContent = data.house.name;
    monthLabel.textContent = app.allMonths ? t("За всё время") : formatMonth(app.month, locale);
    previous.disabled = app.allMonths;
    next.disabled = app.allMonths || app.month >= data.today.slice(0, 7);
    clear.hidden = !search.value;
    kindChips.forEach(item => setChip(item.node, app.filters.kind === item.value));
    setChip(mine, String(app.filters.member) === String(data.actor));
    setChip(waiting, app.filters.mode === 'waiting_return' && app.allMonths);
    const count = advancedFilterCount();
    filterLabel.textContent = t("Фильтры{0}", [count ? ` · ${count}` : '']);
    setChip(filterButton, count > 0);
    summary.replaceChildren(
      h('span', { class: 'row-meta' }, t("Записей: {0}{1}", [data.total, app.allMonths ? t(" · за всё время") : ''])),
      h('span', { class: 'summary-stat' }, h('span', { class: 'row-meta' }, t("Расходы")), h('strong', {}, money(data.summary.expenses))),
      h('span', { class: 'summary-stat' }, h('span', { class: 'row-meta' }, t("Взносы")), h('strong', {}, money(data.summary.contributions))),
      h('button', { type: 'button', class: 'link-btn', 'aria-haspopup': 'dialog', onClick: openTotals }, t("Подробнее"), icon('chevron-right')));
    list.replaceChildren(...(app.rows.length ? dayGroups(app.rows) : [emptyView()]));
    const control = button({ label: t("Показать ещё"), variant: 'secondary', block: true });
    control.onclick = () => busy(control, loadMore);
    more.replaceChildren(...(data.total > app.rows.length ? [control] : []));
  }

  function emptyView() {
    if (!app.data.recent.length) {
      return emptyState({ icon: 'wallet', title: t("Пока нет записей"), text: t("Запишите расход или внесите деньги в общий котёл."),
        action: button({ label: t("Записать расход"), icon: 'plus', onClick: () => openForm({ kind: 'expense' }) }) });
    }
    return emptyState({
      icon: 'search', title: t("Нет совпадений"), text: t("Измените фильтры или выберите другой месяц."),
      action: h('div', { class: 'stack' },
        app.allMonths ? null : button({ label: t("Искать за всё время"), variant: 'secondary', onClick: () => apply({ allMonths: true }) }),
        button({ label: t("Сбросить фильтры"), variant: 'ghost', onClick: () => {
          search.value = '';
          resetSelection();
          apply({});
        } })),
    });
  }

  return { update };
}
