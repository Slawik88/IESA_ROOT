// Файлы. Записи и шаблон отправляются в чат с ботом: на телефоне Telegram не сохраняет файлы из страницы, а чат работает везде.
// Скачивание на устройство остаётся для компьютера. Загрузка идёт по шагам: шаблон, заполнение, выбор файла, проверка, подтверждение.
import { locale, t, translateError } from '../i18n.js';
import { formatMonth, toBase64 } from '../format.js';
import { app, money } from '../state.js';
import { refresh, selectionParams } from '../data.js';
import { telegram } from '../telegram.js';
import { busy, button, chip, errorText, h, icon, openSheet, segmented, setChip, toast } from '../ui.js';

const MAX_BYTES = 2 * 1024 * 1024;
const DOWNLOAD_REVOKE_MS = 10000;
const FORMATS = [
  { value: 'xlsx', label: 'Excel', hint: () => t("Excel — таблица, откроется на телефоне и компьютере.") },
  { value: 'csv', label: 'CSV', hint: () => t("CSV — простой текст, подойдёт любой программе.") },
  { value: 'tsv', label: 'TSV', hint: () => t("TSV — простой текст с табуляцией.") },
  { value: 'json', label: 'JSON', hint: () => t("JSON — для программ и обмена данными.") },
];

let importPayload = null;
export const hasPendingImport = () => importPayload !== null;

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = h('a', { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_REVOKE_MS);
  toast(app.data.can_send_files ? t("Файл подготовлен. Не появился — отправьте его в чат.") : t("Файл подготовлен"));
}

function sentCard(result) {
  return h('div', { class: 'sent-card', role: 'status' },
    h('span', { class: 'sent-mark' }, icon('check')),
    h('div', { class: 'row-main' },
      h('p', { class: 'row-title' }, t("Файл отправлен в чат с ботом")),
      h('p', { class: 'row-meta' }, t("Он пришёл последним сообщением: откройте его там, сохраните или перешлите."))),
    button({ label: t("Открыть чат"), icon: 'send', size: 'sm', variant: 'secondary', onClick: () => telegram.openChat(result.link) }));
}

// Две дороги к файлу: в чат (работает везде) и на устройство (там, где приложение умеет сохранять файлы).
function delivery({ sendLabel, saveLabel, sendPath, savePath, filename }) {
  const slot = h('div', { class: 'sent-slot' });
  const controls = [];
  const chat = app.data.can_send_files;
  if (chat) {
    const send = button({ label: sendLabel, icon: 'send', block: true });
    send.onclick = () => busy(send, async () => {
      const result = await app.api.post(sendPath());
      slot.replaceChildren(sentCard(result)); // карточка появляется заново при каждой отправке, поэтому повтор тоже заметен
      telegram.haptic.success();
    });
    controls.push(send);
  }
  if (!chat || !telegram.isPhone) {
    const save = button({ label: saveLabel, icon: 'download', variant: chat ? 'secondary' : 'primary', block: true });
    save.onclick = () => busy(save, async () => saveBlob(await app.api.blob(savePath()), filename()));
    controls.push(save);
  }
  return h('div', { class: 'delivery' }, controls, slot);
}

function formatPicker(state) {
  const hint = h('p', { class: 'row-meta' });
  const nodes = FORMATS.map(format => chip({ label: format.label, pressed: format.value === state.format, onClick: () => {
    state.format = format.value;
    nodes.forEach((node, index) => setChip(node, FORMATS[index].value === state.format));
    hint.textContent = format.hint();
  } }));
  hint.textContent = FORMATS.find(format => format.value === state.format).hint();
  return h('section', { class: 'sheet-section' },
    h('p', { class: 'form-label' }, t("Формат файла")), h('div', { class: 'chips-wrap' }, nodes), hint);
}

function exportSection(state) {
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
  const query = () => {
    const params = period === 'selection' ? selectionParams() : new URLSearchParams();
    if (period === 'month') params.set('month', app.month);
    return params;
  };
  paint();
  return h('section', { class: 'sheet-section' },
    h('h3', { class: 'sheet-subtitle' }, t("Скачать записи")), choice.el, context,
    delivery({
      sendLabel: t("Отправить в чат с ботом"), saveLabel: t("Скачать на устройство"),
      sendPath: () => `houses/${app.houseId}/export/${state.format}/send?${query()}`,
      savePath: () => `houses/${app.houseId}/export/${state.format}?${query()}`,
      filename: () => `operations-${period === 'all' || (period === 'selection' && app.allMonths) ? 'all' : app.month}.${state.format}`,
    }));
}

function fillingHelp() {
  return h('details', { class: 'disclosure' }, h('summary', {}, t("Как заполнять таблицу")),
    h('div', { class: 'stack-tight' },
      h('p', { class: 'row-meta' }, t("Скачайте шаблон или используйте свой экспорт. Excel: один лист «Операции», значения без формул; ID и суммы в шаблоне — текст. Даты — YYYY-MM-DD, суммы — с точкой или запятой. Для каждой новой строки нужен свой source_key.")),
      h('p', { class: 'row-meta' }, t("Авторы записей · member_tg_id")),
      h('ul', { class: 'plain-list' }, app.data.members.map(member => h('li', {}, `${member.display_name}: ${member.tg_id}`))),
      h('p', { class: 'row-meta' }, t("kind: expense — расход, contribution — взнос. mode: house — из котла, personal — за свои. Валюта должна совпадать с валютой дома."))));
}

function importSection(state) {
  const house = app.houseId;
  let version = 0;
  const fileName = h('p', { class: 'row-meta' });
  const summary = h('p', { class: 'sheet-text' });
  const errors = h('pre', { class: 'import-errors' });
  const confirm = button({ label: t("Добавить записи"), block: true });
  const cancel = button({ label: t("Отмена"), variant: 'ghost', block: true });
  const preview = h('div', { class: 'import-preview', hidden: true }, fileName, summary, errors, confirm, cancel);
  const picker = h('input', { type: 'file', accept: '.xlsx,.csv,.tsv,.json', class: 'sr-only' });
  const choose = h('label', { class: 'btn btn-secondary btn-md btn-block' }, icon('file'), h('span', {}, t("Выбрать файл")), picker);
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
    if (!FORMATS.some(format => format.value === extension)) { toast(t("Выберите Excel, CSV, TSV или JSON"), { kind: 'error' }); return; }
    try {
      const payload = { extension, content: toBase64(new Uint8Array(await file.arrayBuffer())) };
      const result = await app.api.post(`houses/${house}/import/preview`, payload);
      if (house !== app.houseId || current !== version) return;
      fileName.textContent = t("Файл: {0}", [file.name]);
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
  const step = (title, ...content) => h('li', { class: 'step' }, h('p', { class: 'step-title' }, title), ...content);
  return h('section', { class: 'sheet-section' },
    h('h3', { class: 'sheet-subtitle' }, t("Загрузить из файла")),
    h('p', { class: 'row-meta' }, t("Так можно сразу добавить много записей, например историю из своей таблицы. До 2 МБ и 1000 строк.")),
    h('ol', { class: 'steps' },
      step(t("Возьмите шаблон"), delivery({
        sendLabel: t("Отправить шаблон в чат"), saveLabel: t("Скачать шаблон"),
        sendPath: () => `houses/${house}/template/${state.format}/send`,
        savePath: () => `houses/${house}/template/${state.format}`,
        filename: () => `template.${state.format}`,
      }), fillingHelp()),
      step(t("Заполните и сохраните"), h('p', { class: 'row-meta' }, t("Откройте шаблон в Excel или другой таблице, впишите записи и сохраните файл на устройстве."))),
      step(t("Выберите готовый файл"), choose, preview, h('p', { class: 'row-meta' }, t("Сначала мы проверим файл. Записи добавятся только после вашего подтверждения.")))));
}

export function openFiles() {
  const state = { format: 'xlsx' };
  openSheet({
    title: t("Записи и файлы"),
    body: [formatPicker(state), exportSection(state), app.data.permissions.import_transactions ? importSection(state) : null],
    onClose: () => { importPayload = null; },
  });
}
