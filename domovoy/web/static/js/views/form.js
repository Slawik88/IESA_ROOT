// Форма расхода и взноса: сумма, источник, категория, описание, дата. Черновики живут только в памяти.
import { locale, t } from '../i18n.js';
import { addDays, decimalString, formatMonth, sanitizeAmount, shiftMonth } from '../format.js';
import { app, money } from '../state.js';
import { redraw, refresh } from '../data.js';
import { telegram } from '../telegram.js';
import { button, chip, errorText, fail, h, nextId, openSheet, segmented, setChip, toast } from '../ui.js';
import { openReceipts } from './receipts.js';

const DESCRIPTION_LIMIT = 200;
const MIN_AMOUNT_WIDTH_CH = 4;
const AMOUNT_ERROR = /сумм|копе|точк|запят/i;
const FIELDS = ['amount', 'date', 'month', 'mode', 'category_id', 'description'];

export const hasDrafts = () => app.drafts.size > 0;
const syncGuard = () => telegram.guardClosing(app.drafts.size > 0);

export function discardDraft(draft) {
  app.drafts.delete(draft.request_id);
  syncGuard();
  redraw();
}

export const resumeDraft = draft => openForm({ kind: draft.kind, resume: draft });

function blankDraft(kind) {
  const { today } = app.data;
  return { request_id: crypto.randomUUID(), house: app.houseId, kind, amount: '', date: today, month: today.slice(0, 7),
    mode: 'house', category_id: null, description: '', editId: null, version: null };
}

function startingDraft({ kind, seed, edit, resume, carry }) {
  const found = resume ?? [...app.drafts.values()].find(item => item.house === app.houseId
    && (edit ? item.editId === seed.id : !seed && !item.editId && item.kind === kind));
  const blank = blankDraft(kind);
  if (found) return { draft: { ...found }, baseline: { ...blank, request_id: found.request_id } };
  const draft = { ...blank, ...(seed ? { amount: decimalString(seed.amount_kop), mode: seed.mode || 'house',
    category_id: seed.category_id || null, description: seed.description || '' } : {}),
  ...(edit ? { date: seed.date, month: seed.month, editId: seed.id, version: seed.version } : {}), ...carry };
  return { draft, baseline: { ...draft } };
}

export function openForm({ kind, seed = null, edit = false, resume = null, carry = null }) {
  const { today } = app.data;
  const expense = kind === 'expense';
  const { draft, baseline } = startingDraft({ kind, seed, edit, resume, carry });
  const signature = source => JSON.stringify(FIELDS.map(key => source[key]));
  const isDirty = () => signature(draft) !== signature(baseline);
  let saving = false;
  let saved = false;
  const change = () => {
    telegram.guardClosing(isDirty() || app.drafts.size > 0);
    errorBox.textContent = '';
  };

  // ── Сумма ──
  const amountId = nextId('amount');
  const amountError = h('p', { class: 'field-error', id: `${amountId}-error`, role: 'alert' });
  const amountInput = h('input', { id: amountId, class: 'amount-input', inputmode: 'decimal', autocomplete: 'off', enterkeyhint: 'done',
    placeholder: '0,00', value: draft.amount, 'aria-describedby': `${amountId}-error` });
  const fitAmount = () => { amountInput.style.width = `${Math.max(MIN_AMOUNT_WIDTH_CH, amountInput.value.length + 1)}ch`; };
  const showAmountError = text => {
    amountError.textContent = text;
    amountInput.setAttribute('aria-invalid', 'true');
    amountInput.focus();
  };
  amountInput.addEventListener('input', () => {
    amountInput.value = sanitizeAmount(amountInput.value);
    draft.amount = amountInput.value;
    amountError.textContent = '';
    amountInput.removeAttribute('aria-invalid');
    fitAmount();
    change();
  });
  fitAmount();

  // ── Расход: источник, категория, описание ──
  const hint = h('p', { class: 'field-hint', hidden: draft.mode !== 'personal' }, t("Дом будет должен вам эту сумму."));
  const source = segmented({
    label: t("Откуда деньги"), value: draft.mode,
    options: [{ value: 'house', label: t("Из котла"), icon: 'wallet' }, { value: 'personal', label: t("За свои"), icon: 'people' }],
    onChange: value => { draft.mode = value; hint.hidden = value !== 'personal'; change(); },
  });
  const categoryChips = app.data.categories.map(category => ({ id: category.id, node: chip({ label: category.name,
    pressed: draft.category_id === category.id, onClick: () => {
      draft.category_id = draft.category_id === category.id ? null : category.id;
      paintCategories();
      change();
    } }) }));
  const paintCategories = () => categoryChips.forEach(item => setChip(item.node, draft.category_id === item.id));
  const descriptionId = nextId('description');
  const description = h('textarea', { id: descriptionId, class: 'input', rows: 2, maxlength: DESCRIPTION_LIMIT, autocomplete: 'off',
    placeholder: t("Например, продукты к ужину"), value: draft.description });
  description.addEventListener('input', () => { draft.description = description.value; change(); });

  // ── Дата и месяц ──
  const yesterday = addDays(today, -1);
  let customDate = draft.date !== today && draft.date !== yesterday;
  const dateInput = h('input', { type: 'date', class: 'input', max: today, value: draft.date, required: true, 'aria-label': t("Когда была операция") });
  const dateChips = [['today', t("Сегодня"), today], ['yesterday', t("Вчера"), yesterday]].map(([key, label, value]) => ({
    key, value, node: chip({ label, onClick: () => { customDate = false; draft.date = value; dateInput.value = value; paintDate(); change(); } }) }));
  const customDateChip = chip({ label: t("Другая дата"), onClick: () => { customDate = true; paintDate(); dateInput.focus(); } });
  dateInput.addEventListener('change', () => { draft.date = dateInput.value; change(); });
  const paintDate = () => {
    dateChips.forEach(item => setChip(item.node, !customDate && draft.date === item.value));
    setChip(customDateChip, customDate);
    dateInput.hidden = !customDate;
  };

  const thisMonth = today.slice(0, 7);
  const lastMonth = shiftMonth(thisMonth, -1);
  let customMonth = draft.month !== thisMonth && draft.month !== lastMonth;
  const monthInput = h('input', { type: 'month', class: 'input', max: thisMonth, value: draft.month, required: true, 'aria-label': t("За какой месяц взнос") });
  const monthChips = [thisMonth, lastMonth].map(value => ({ value, node: chip({ label: formatMonth(value, locale, { month: 'long' }),
    onClick: () => { customMonth = false; draft.month = value; monthInput.value = value; paintMonth(); change(); } }) }));
  const customMonthChip = chip({ label: t("Другой месяц"), onClick: () => { customMonth = true; paintMonth(); monthInput.focus(); } });
  monthInput.addEventListener('change', () => { draft.month = monthInput.value; change(); });
  const paintMonth = () => {
    monthChips.forEach(item => setChip(item.node, !customMonth && draft.month === item.value));
    setChip(customMonthChip, customMonth);
    monthInput.hidden = !customMonth;
  };

  // ── Недавнее ──
  const templates = edit ? [] : app.data.templates.filter(item => item.kind === kind);
  const applyTemplate = item => {
    Object.assign(draft, { amount: decimalString(item.amount_kop), mode: item.mode || 'house',
      category_id: item.category_id || null, description: item.description || '' });
    amountInput.value = draft.amount;
    description.value = draft.description;
    source.set(draft.mode);
    hint.hidden = draft.mode !== 'personal';
    fitAmount();
    paintCategories();
    change();
  };

  const group = (title, ...content) => h('div', { class: 'form-group' }, h('p', { class: 'form-label' }, title), ...content);
  const errorBox = h('p', { class: 'form-error', role: 'alert' });
  const fields = h('fieldset', { class: 'tx-fields' },
    templates.length ? group(t("Недавнее"), h('div', { class: 'chips' }, templates.map(item => chip({
      label: expense ? `${item.category || t("Расход")} · ${money(item.amount_kop)}` : money(item.amount_kop), onClick: () => applyTemplate(item) })))) : null,
    h('div', { class: 'amount-box' },
      h('label', { for: amountId, class: 'form-label' }, t("Сумма")),
      h('div', { class: 'amount-row' }, amountInput, h('span', { class: 'amount-currency' }, app.data.currency)), amountError),
    expense ? group(t("Откуда деньги"), source.el, hint) : null,
    expense ? group(t("Категория"), h('div', { class: 'chips-wrap' }, categoryChips.map(item => item.node))) : null,
    expense ? h('div', { class: 'form-group' }, h('label', { for: descriptionId, class: 'form-label' }, t("На что"), h('span', { class: 'form-optional' }, t("необязательно"))), description) : null,
    group(t("Когда была операция"), h('div', { class: 'chips-wrap' }, dateChips.map(item => item.node), customDateChip), dateInput),
    expense ? null : group(t("За какой месяц взнос"), h('div', { class: 'chips-wrap' }, monthChips.map(item => item.node), customMonthChip), monthInput),
    errorBox);
  const formId = nextId('tx-form');
  const form = h('form', { id: formId, class: 'tx-form', novalidate: true, onSubmit: event => { event.preventDefault(); submit('close'); } }, fields);

  const label = edit ? t("Сохранить изменения") : expense ? t("Записать расход") : t("Внести деньги");
  const primary = button({ label, type: 'submit', block: true });
  primary.setAttribute('form', formId);
  const again = button({ label: t("Записать и добавить ещё"), variant: 'ghost', size: 'sm', onClick: () => submit('another') });
  const withReceipt = button({ label: t("Записать и добавить чек"), variant: 'ghost', size: 'sm', onClick: () => submit('receipt') });
  const actions = [primary, ...(edit ? [] : [again]), ...(edit || !expense ? [] : [withReceipt])];
  const footer = [primary, edit ? null : h('div', { class: 'button-row' }, again, expense ? withReceipt : null)];
  const lock = on => {
    fields.disabled = on;
    actions.forEach(control => { control.disabled = on; });
    primary.querySelector('span').textContent = on ? t("Сохраняю…") : label;
  };

  const sheet = openSheet({
    title: edit ? t("Изменить расход") : expense ? t("Записать расход") : t("Внести деньги"), body: form, footer, focus: amountInput,
    onClose: () => {
      if (!saved && isDirty()) app.drafts.set(draft.request_id, { ...draft });
      else app.drafts.delete(draft.request_id);
      syncGuard();
      redraw();
    },
  });
  paintDate();
  paintMonth();
  paintCategories();

  async function submit(after) {
    if (saving) return;
    errorBox.textContent = '';
    if (!draft.amount.trim()) {
      showAmountError(t("Введите сумму"));
      return;
    }
    saving = true;
    lock(true);
    const payload = { request_id: draft.request_id, kind, amount: draft.amount, date: draft.date,
      month: expense ? draft.date.slice(0, 7) : draft.month, category_id: expense ? draft.category_id : null,
      mode: expense ? draft.mode : 'house', description: expense ? draft.description : '',
      ...(draft.editId ? { version: draft.version } : {}) };
    try {
      const path = draft.editId ? `houses/${draft.house}/expenses/${draft.editId}/edit` : `houses/${draft.house}/transactions`;
      const result = await app.api.post(path, payload);
      saved = true;
      app.drafts.delete(draft.request_id);
      syncGuard();
      telegram.haptic.success();
      sheet.close();
      let refreshed = true;
      try { await refresh(); } catch { refreshed = false; }
      toast(refreshed ? (draft.editId ? t("Изменения сохранены") : result.status === 'declared' ? t("Взнос ждёт подтверждения") : t("Запись сохранена"))
        : t("Запись сохранена. Список пока не обновился — нажмите «Обновить»."));
      if (after === 'another' && app.houseId === draft.house) {
        openForm({ kind, carry: { mode: draft.mode, category_id: draft.category_id, description: draft.description } });
      } else if (after === 'receipt' && expense && result.id && app.houseId === draft.house) {
        openReceipts({ id: result.id, description: draft.description }).catch(fail);
      }
    } catch (error) {
      const text = errorText(error);
      if (error.kind === 'session') fail(error);
      else if (AMOUNT_ERROR.test(text)) showAmountError(text);
      else errorBox.textContent = text;
      telegram.haptic.error();
    } finally {
      saving = false;
      lock(false);
    }
  }
}
