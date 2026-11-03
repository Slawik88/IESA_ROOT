// Главная: баланс, быстрые действия, что нужно сделать сейчас (взносы, черновик, уборка), последние записи.
import { locale, t } from '../i18n.js';
import { moneyParts } from '../format.js';
import { app, day, DEFAULT_FILTERS, houseDrafts, money, nav } from '../state.js';
import { applySelection, refresh } from '../data.js';
import { avatar, badge, busy, button, emptyState, fail, h, icon, iconButton, openSheet, toast } from '../ui.js';
import { entryRow } from './entries.js';
import { openEntry } from './entry.js';
import { discardDraft, openForm, resumeDraft } from './form.js';

const LONG_AMOUNT = 9;
const XLONG_AMOUNT = 12;
let showOverdue = false;

function openBalanceInfo() {
  const { balance } = app.data;
  openSheet({
    title: t("Остаток в котле"), size: 'sm',
    body: [
      h('p', { class: 'sheet-text' }, t("Подтверждённые взносы за всё время за вычетом общих трат и возвратов. Личные покупки уменьшают котёл только после возврата.")),
      h('dl', { class: 'facts facts-list' },
        h('div', {}, h('dt', {}, t("Внесено")), h('dd', {}, money(balance.confirmed_total))),
        h('div', {}, h('dt', {}, t("Потрачено")), h('dd', {}, money(balance.house_spent + balance.reimbursed)))),
    ],
  });
}

function hero() {
  const { balance, currency } = app.data;
  const parts = moneyParts(balance.balance, locale);
  const digits = `${parts.whole}${parts.decimal}${parts.cents}`;
  const size = digits.length > XLONG_AMOUNT ? ' is-xlong' : digits.length > LONG_AMOUNT ? ' is-long' : '';
  return h('section', { class: `hero${balance.balance < 0 ? ' is-negative' : ''}`, 'aria-label': t("Деньги дома") },
    h('div', { class: 'hero-top' },
      h('p', { class: 'hero-label' }, t("Общий котёл")),
      iconButton({ icon: 'info', label: t("Как рассчитан остаток"), onClick: openBalanceInfo, className: 'hero-info' })),
    h('p', { class: `hero-amount${size}` }, `${parts.negative ? '−' : ''}${digits}`, h('span', { class: 'hero-currency' }, currency)),
    balance.balance < 0 ? h('p', { class: 'hero-note' }, t("В котле не хватает денег. Нужны новые взносы.")) : null,
    h('dl', { class: 'hero-split' },
      h('div', {}, h('dt', {}, t("Внесено")), h('dd', {}, money(balance.confirmed_total))),
      h('div', {}, h('dt', {}, t("Потрачено")), h('dd', {}, money(balance.house_spent + balance.reimbursed)))));
}

// Личные траты, по которым дом ещё не рассчитался: сколько должен дом и сколько из этого — вам.
function waitingCard() {
  const waiting = app.data.waiting;
  if (!waiting?.total) return null;
  const open = async () => {
    try {
      await applySelection({ filters: { ...DEFAULT_FILTERS, mode: 'waiting_return', kind: 'expense' }, allMonths: true });
      nav.go('history');
    } catch (error) { fail(error); }
  };
  return h('div', { class: 'group' }, h('button', { type: 'button', class: 'group-row', onClick: open },
    h('span', { class: 'row-icon' }, icon('wallet')),
    h('span', { class: 'row-main' },
      h('span', { class: 'row-title' }, t("Дом должен жильцам")),
      h('span', { class: 'row-meta' }, waiting.mine ? t("Из них вам: {0}", [money(waiting.mine)]) : t("Личные траты без возврата"))),
    h('span', { class: 'row-end' }, h('span', { class: 'amt' }, money(waiting.total)), icon('chevron-right', 'row-chevron'))));
}

function quickAction(iconName, label, onClick, primary = false) {
  return h('button', { type: 'button', class: `quick-item${primary ? ' is-primary' : ''}`, onClick },
    h('span', { class: 'quick-icon' }, icon(iconName)), h('span', {}, label));
}

function quickActions() {
  return h('nav', { class: 'quick', 'aria-label': t("Действия с деньгами") },
    quickAction('plus', t("Расход"), () => openForm({ kind: 'expense' }), true),
    quickAction('wallet', t("Взнос"), () => openForm({ kind: 'contribution' })),
    quickAction('clock', t("История"), () => nav.go('history')));
}

// Пока в доме нет записей, главная подсказывает три первых шага.
function setupCard() {
  if ((app.data.recent ?? []).length) return null;
  const step = (iconName, title, onClick) => h('button', { type: 'button', class: 'group-row', onClick },
    h('span', { class: 'row-icon' }, icon(iconName)), h('span', { class: 'row-main' }, h('span', { class: 'row-title' }, title)), icon('chevron-right', 'row-chevron'));
  return h('section', { class: 'card', 'aria-labelledby': 'setup-title' },
    h('div', { class: 'card-head' }, h('h2', { id: 'setup-title' }, t("С чего начать"))),
    h('div', { class: 'group' },
      step('people', t("Пригласить соседей"), () => nav.go('house', 'people')),
      step('calendar', t("График уборки"), () => nav.go('house', 'schedule')),
      step('plus', t("Записать расход"), () => openForm({ kind: 'expense' }))));
}

function pendingCard() {
  const list = app.data.pending;
  if (!list.length) return null;
  const decide = (entry, confirm) => async () => {
    await app.api.post(`houses/${app.houseId}/contributions/${entry.id}`, { confirm });
    await refresh();
    toast(confirm ? t("Взнос принят") : t("Взнос отклонён"));
  };
  return h('section', { class: 'card card-attention', 'aria-labelledby': 'pending-title' },
    h('div', { class: 'card-head' }, h('h2', { id: 'pending-title' }, t("Нужно подтвердить")), badge(String(list.length), 'warn')),
    list.map(entry => {
      const accept = button({ label: t("Принять"), size: 'sm' });
      const reject = button({ label: t("Отклонить"), size: 'sm', variant: 'secondary' });
      accept.onclick = () => busy(accept, decide(entry, true));
      reject.onclick = () => busy(reject, decide(entry, false));
      return h('div', { class: 'pending-row' },
        avatar(entry.display_name, entry.tg_id ?? entry.id),
        h('div', { class: 'row-main' },
          h('div', { class: 'row-title' }, entry.display_name),
          h('div', { class: 'row-meta' }, t("За {0}", [day(`${entry.month}-01`, { month: 'long', year: 'numeric' })]))),
        h('div', { class: 'row-end' }, h('span', { class: 'amt' }, money(entry.amount_kop))),
        h('div', { class: 'pending-actions' }, accept, reject));
    }));
}

function draftTitle(draft) {
  const edited = draft.kind === 'expense' ? t("Правка расхода") : t("Правка взноса");
  const kind = draft.editId ? edited : draft.kind === 'expense' ? t("Расход") : t("Взнос");
  return draft.amount ? `${kind} · ${draft.amount} ${app.data.currency}` : kind;
}

function draftsCard() {
  const drafts = houseDrafts();
  if (!drafts.length) return null;
  return h('section', { class: 'card card-draft', 'aria-label': t("Незаконченные записи") },
    drafts.map(draft => h('div', { class: 'draft-row' },
      icon('edit', 'draft-icon'),
      h('div', { class: 'row-main' },
        h('div', { class: 'row-title' }, draftTitle(draft)),
        h('div', { class: 'row-meta' }, t("Вы не закончили запись"))),
      button({ label: t("Продолжить"), size: 'sm', variant: 'secondary', onClick: () => resumeDraft(draft) }),
      iconButton({ icon: 'trash', label: t("Удалить черновик"), onClick: () => discardDraft(draft) }))));
}

function choreRow({ iconName, title, meta, action }) {
  return h('div', { class: 'chore-row' },
    h('span', { class: 'row-icon' }, icon(iconName)),
    h('div', { class: 'row-main' }, h('div', { class: 'row-title' }, title), meta ? h('div', { class: 'row-meta' }, meta) : null),
    action);
}

function doneButton(entry) {
  const control = button({ label: t("Готово"), size: 'sm', variant: 'secondary' });
  control.onclick = () => busy(control, async () => {
    await app.api.post(`houses/${app.houseId}/clean/${entry.id}`);
    await refresh();
    toast(t("Уборка отмечена"));
  });
  return control;
}

function choresCard() {
  const { today, actor, cleaning, upcoming } = app.data;
  const mine = cleaning.filter(entry => entry.tg_id === actor);
  const todays = mine.filter(entry => entry.planned_date === today);
  const overdue = mine.filter(entry => entry.planned_date < today);
  const others = cleaning.filter(entry => entry.planned_date === today && entry.tg_id !== actor);
  const rows = [];
  for (const entry of todays) {
    rows.push(choreRow({ iconName: 'spark', title: t("Сегодня ваша очередь"), meta: t("Когда закончите — отметьте здесь"), action: doneButton(entry) }));
  }
  if (!todays.length && others.length) {
    rows.push(choreRow({ iconName: 'people', title: t("Сегодня убирает {0}", [others.map(entry => entry.display_name).join(', ')]) }));
  }
  if (!todays.length && !others.length && !overdue.length) {
    const next = upcoming[0];
    rows.push(choreRow({
      iconName: 'calendar', title: t("На сегодня уборки нет"),
      meta: next ? t("Дальше: {0} · {1}", [next.display_name, day(next.planned_date, { weekday: 'short', day: 'numeric', month: 'short' })]) : t("График пока не настроен"),
    }));
  }
  if (overdue.length) {
    const toggle = h('button', { type: 'button', class: 'chore-overdue', 'aria-expanded': String(showOverdue),
      onClick: () => { showOverdue = !showOverdue; nav.redraw(); } },
      icon('alert'), h('span', {}, t("Пропущено: {0}", [overdue.length])), icon(showOverdue ? 'chevron-up' : 'chevron-down', 'row-chevron'));
    rows.push(toggle);
    if (showOverdue) {
      for (const entry of overdue) {
        rows.push(choreRow({ iconName: 'clock', title: t("За {0}", [day(entry.planned_date)]), meta: t("Ещё не отмечено"), action: doneButton(entry) }));
      }
    }
  }
  return h('section', { class: 'card', 'aria-labelledby': 'chores-title' },
    h('div', { class: 'card-head' }, h('h2', { id: 'chores-title' }, t("Уборка"))), rows);
}

function feedCard() {
  const recent = app.data.recent ?? [];
  return h('section', { class: 'card card-feed', 'aria-labelledby': 'feed-title' },
    h('div', { class: 'card-head' },
      h('h2', { id: 'feed-title' }, t("Последние записи")),
      recent.length ? h('button', { type: 'button', class: 'link-btn', onClick: () => nav.go('history') }, t("Вся история"), icon('chevron-right')) : null),
    recent.length
      ? h('div', { class: 'list' }, recent.map(entry => entryRow(entry, openEntry)))
      : emptyState({
        icon: 'wallet', title: t("Пока нет записей"), text: t("Запишите расход или внесите деньги в общий котёл."),
        action: button({ label: t("Записать расход"), icon: 'plus', onClick: () => openForm({ kind: 'expense' }) }),
      }));
}

export function renderHome(root) {
  const { today, house } = app.data;
  root.replaceChildren(
    h('header', { class: 'page-head' },
      h('div', {},
        h('p', { class: 'eyebrow' }, day(today, { weekday: 'long', day: 'numeric', month: 'long' })),
        h('h1', { id: 'home-title', tabindex: '-1' }, house.name))),
    h('div', { class: 'home-grid' },
      h('div', { class: 'home-top' }, hero(), quickActions(), waitingCard()),
      h('div', { class: 'home-tasks' }, setupCard(), pendingCard(), draftsCard(), choresCard()),
      h('div', { class: 'home-feed' }, feedCard())));
}
