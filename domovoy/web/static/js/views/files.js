// Файлы: скачать записи (Excel, CSV, TSV, JSON) и загрузить из файла с предварительной проверкой.
import { locale, t, translateError } from '../i18n.js';
import { formatMonth, toBase64 } from '../format.js';
import { app, money } from '../state.js';
import { refresh, selectionParams } from '../data.js';
import { busy, button, errorText, h, openSheet, segmented, toast } from '../ui.js';

const MAX_BYTES = 2 * 1024 * 1024;
const FORMATS = ['xlsx', 'csv', 'tsv', 'json'];
const DOWNLOAD_REVOKE_MS = 10000;

let importPayload = null;
export const hasPendingImport = () => importPayload !== null;

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = h('a', { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_REVOKE_MS);
  toast(t("Файл подготовлен"));
}

function exportSection() {
  let period = 'selection';
  const context = h('p', { class: 'row-meta' });
  const paint = () => {
    const month = formatMonth(app.month, locale);
    context.textContent = period === 'all' ? t("Вся история дома. Фильтры не применяются.")
      : period === 'month' ? t("{0} · все записи месяца без фильтров.", [month])
      : t("{0} · записей с текущими фильтрами: {1}", [app.allMonths ? t("Всё время") : month, app.data.total]);
  };
  const choice = segmented({ label: t("Какие записи"), value: period, onChange: value => { period = value; paint(); }, options: [
    { value: 'selection', label: t("Как в истории") }, { value: 'month', label: t("Месяц") }, { value: 'all', label: t("Всё время") }] });
  const download = format => {
    const control = button({ label: format === 'xlsx' ? 'Excel' : format.toUpperCase(), variant: format === 'xlsx' ? 'primary' : 'secondary', block: true });
    control.onclick = () => busy(control, async () => {
      const params = period === 'selection' ? selectionParams() : new URLSearchParams();
      if (period === 'month') params.set('month', app.month);
      const blob = await app.api.blob(`houses/${app.houseId}/export/${format}?${params}`);
      saveBlob(blob, `operations-${period === 'all' || (period === 'selection' && app.allMonths) ? 'all' : app.month}.${format}`);
    });
    return control;
  };
  paint();
  return h('section', { class: 'sheet-section' },
    h('h3', { class: 'sheet-subtitle' }, t("Скачать записи")), choice.el, context,
    h('div', { class: 'button-row' }, download('xlsx'), download('csv')),
    h('details', { class: 'disclosure' }, h('summary', {}, t("Другие форматы")), h('div', { class: 'button-row' }, download('tsv'), download('json'))));
}

function templateButton(format) {
  const control = button({ label: format === 'xlsx' ? 'Excel' : format.toUpperCase(), variant: 'secondary', size: 'sm', block: true });
  control.onclick = () => busy(control, async () => saveBlob(await app.api.blob(`houses/${app.houseId}/template/${format}`), `template.${format}`));
  return control;
}

function importSection() {
  const house = app.houseId;
  let version = 0;
  const summary = h('p', { class: 'sheet-text' });
  const errors = h('pre', { class: 'import-errors' });
  const confirm = button({ label: t("Добавить записи"), block: true });
  const cancel = button({ label: t("Отмена"), variant: 'ghost', block: true });
  const preview = h('div', { class: 'import-preview', hidden: true }, summary, errors, confirm, cancel);
  const picker = h('input', { type: 'file', accept: '.xlsx,.csv,.tsv,.json', class: 'sr-only' });
  const choose = h('label', { class: 'btn btn-secondary btn-md btn-block' }, h('span', {}, t("Выбрать файл")), picker);
  const reset = () => {
    version += 1;
    importPayload = null;
    preview.hidden = true;
    picker.value = '';
  };
  cancel.onclick = reset;
  picker.onchange = async () => {
    const current = ++version;
    importPayload = null;
    preview.hidden = true;
    const file = picker.files[0];
    if (!file) return;
    if (file.size > MAX_BYTES) { toast(t("Максимальный размер — 2 МБ"), { kind: 'error' }); return; }
    const extension = file.name.split('.').pop().toLowerCase();
    if (!FORMATS.includes(extension)) { toast(t("Выберите Excel, CSV, TSV или JSON"), { kind: 'error' }); return; }
    try {
      const payload = { extension, content: toBase64(new Uint8Array(await file.arrayBuffer())) };
      const result = await app.api.post(`houses/${house}/import/preview`, payload);
      if (house !== app.houseId || current !== version) return;
      summary.textContent = t("Новых: {0} · дублей: {1} · ошибок: {2}. Изменение котла: {3}",
        [result.new, result.duplicates, result.error_count, money(result.balance_delta)]);
      errors.textContent = translateError(result.errors.join('\n'));
      confirm.disabled = result.error_count > 0 || result.new === 0;
      preview.hidden = false;
      if (!result.error_count && result.new) importPayload = payload;
    } catch (error) {
      if (current === version) toast(errorText(error), { kind: 'error' });
    }
  };
  confirm.onclick = () => busy(confirm, async () => {
    if (!importPayload) return;
    const result = await app.api.post(`houses/${house}/import/confirm`, importPayload);
    reset();
    await refresh();
    toast(t("Добавлено: {0}, дублей: {1}", [result.added, result.duplicates]));
  });
  return h('section', { class: 'sheet-section' },
    h('h3', { class: 'sheet-subtitle' }, t("Загрузить из файла")),
    h('p', { class: 'row-meta' }, t("До 2 МБ и 1000 строк. Сначала проверим файл; добавим записи после вашего подтверждения.")),
    choose, preview,
    h('details', { class: 'disclosure' }, h('summary', {}, t("Шаблоны и заполнение")),
      h('p', { class: 'row-meta' }, t("Скачайте шаблон или используйте свой экспорт. Excel: один лист «Операции», значения без формул; ID и суммы в шаблоне — текст. Даты — YYYY-MM-DD, суммы — с точкой или запятой. Для каждой новой строки нужен свой source_key.")),
      h('div', { class: 'button-row' }, FORMATS.map(templateButton)),
      h('p', { class: 'row-meta' }, t("Авторы записей · member_tg_id")),
      h('ul', { class: 'plain-list' }, app.data.members.map(member => h('li', {}, `${member.display_name}: ${member.tg_id}`))),
      h('p', { class: 'row-meta' }, t("kind: expense — расход, contribution — взнос. mode: house — из котла, personal — за свои. Валюта должна совпадать с валютой дома."))));
}

export function openFiles() {
  openSheet({
    title: t("Записи и файлы"),
    body: [exportSection(), app.data.permissions.import_transactions ? importSection() : null],
    onClose: () => { importPayload = null; },
  });
}
