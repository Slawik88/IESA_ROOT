// Чеки к расходу: просмотр и загрузка фото. Выбранное фото хранится только в памяти и переживает повтор после сбоя связи.
import { t } from '../i18n.js';
import { toBase64 } from '../format.js';
import { app } from '../state.js';
import { refresh } from '../data.js';
import { busy, button, errorText, fail, h, icon, openSheet, toast } from '../ui.js';

const BYTES_IN_MB = 1024 * 1024;
const IMAGE_TYPES = ['image/jpeg', 'image/png'];
const pending = new Map();

export const hasPendingReceipts = () => pending.size > 0;

export async function openReceipts(expense) {
  const house = app.houseId;
  const path = `houses/${house}/expenses/${expense.id}/receipts`;
  const key = `${house}:${expense.id}`;
  const urls = new Set();
  const body = h('div', { class: 'receipts' }, h('p', { class: 'row-meta' }, t("Открываем чеки…")));
  const sheet = openSheet({ title: t("Чеки к расходу"), body, onClose: () => urls.forEach(url => URL.revokeObjectURL(url)) });
  const isOpen = () => sheet.el.isConnected;

  function preview(receipt, index, cell) {
    const load = async () => {
      cell.replaceChildren(h('p', { class: 'row-meta' }, t("Открываем чек {0}…", [index + 1])));
      try {
        const url = URL.createObjectURL(await app.api.blob(`${path}/${receipt.id}`));
        if (!isOpen()) {
          URL.revokeObjectURL(url);
          return;
        }
        urls.add(url);
        const zoom = h('button', { type: 'button', class: 'receipt-preview', 'aria-expanded': 'false', 'aria-label': t("Увеличить чек {0}", [index + 1]) },
          h('img', { src: url, alt: t("Чек {0}", [index + 1]) }));
        zoom.onclick = () => {
          const expanded = cell.classList.toggle('expanded');
          zoom.setAttribute('aria-expanded', String(expanded));
          zoom.setAttribute('aria-label', t("{0} чек {1}", [expanded ? t("Уменьшить") : t("Увеличить"), index + 1]));
        };
        cell.replaceChildren(zoom);
      } catch (error) {
        if (!isOpen()) return;
        cell.replaceChildren(h('p', { class: 'field-error' }, errorText(error)),
          button({ label: t("Открыть ещё раз"), variant: 'ghost', size: 'sm', onClick: load }));
      }
    };
    load();
  }

  function uploader(data) {
    const info = h('p', { class: 'row-meta' });
    const error = h('p', { class: 'field-error', role: 'alert' });
    const picker = h('input', { type: 'file', accept: IMAGE_TYPES.join(','), class: 'sr-only' });
    const choose = h('label', { class: 'btn btn-secondary btn-md btn-block' }, icon('camera'), h('span', {}, t("Выбрать фото")), picker);
    const send = button({ label: pending.has(key) ? t("Повторить загрузку чека") : t("Прикрепить чек"), block: true });
    const discard = button({ label: t("Убрать выбранное фото"), variant: 'ghost', block: true });
    const paint = () => {
      send.disabled = !pending.has(key);
      discard.hidden = !pending.has(key);
    };
    paint();
    discard.onclick = () => {
      pending.delete(key);
      picker.value = '';
      info.textContent = '';
      error.textContent = '';
      paint();
    };
    picker.onchange = async () => {
      const file = picker.files[0];
      if (!file) return;
      pending.delete(key);
      error.textContent = '';
      paint();
      if (file.size > data.max_bytes) { error.textContent = t("Выберите фото не больше 2 МБ"); return; }
      if (file.type && !IMAGE_TYPES.includes(file.type)) { error.textContent = t("Подойдёт фото JPEG или PNG"); return; }
      const bytes = new Uint8Array(await file.arrayBuffer());
      if (!isOpen() || picker.files[0] !== file) return;
      pending.set(key, { request_id: crypto.randomUUID(), content: toBase64(bytes) });
      info.textContent = file.name;
      send.querySelector('span').textContent = t("Прикрепить чек");
      paint();
    };
    send.onclick = () => busy(send, async () => {
      const intent = pending.get(key);
      if (!intent) return;
      error.textContent = '';
      try {
        await app.api.post(path, intent);
      } catch (failure) {
        error.textContent = failure.kind === 'network' ? t("Связь прервалась. Расход сохранён. Можно повторить только загрузку этого чека.") : errorText(failure);
        send.querySelector('span').textContent = t("Повторить загрузку чека");
        return;
      }
      if (pending.get(key) === intent) pending.delete(key);
      toast(t("Чек прикреплён"));
      try { await refresh(); } catch { /* Фото уже сохранено; повтор денежной записи не нужен. */ }
      if (isOpen()) { sheet.close(); openReceipts(expense); }
    });
    return h('div', { class: 'receipt-upload' },
      h('p', { class: 'form-label' }, t("Фото JPEG или PNG · до {0} МБ", [data.max_bytes / BYTES_IN_MB])),
      choose, info,
      h('p', { class: 'row-meta' }, t("{0}. Фото доступны только участникам дома.", [t(data.upload_notice)])),
      send, discard, error);
  }

  try {
    const data = await app.api.get(path);
    if (!isOpen()) return;
    const grid = h('div', { class: 'receipt-grid' });
    body.replaceChildren(h('p', { class: 'row-meta' }, expense.description || expense.category || t("Расход")));
    if (!data.available) {
      body.append(h('p', { class: 'panel-note' }, t("Хранилище чеков временно недоступно. Сам расход сохранён.")));
      return;
    }
    if (!data.receipts.length) body.append(h('p', { class: 'panel-note' }, t("Чеков пока нет. Можно добавить фото.")));
    body.append(grid);
    data.receipts.forEach((receipt, index) => {
      const cell = h('div', { class: 'receipt-cell' });
      grid.append(cell);
      preview(receipt, index, cell);
    });
    if (data.can_upload) body.append(uploader(data));
  } catch (error) {
    if (isOpen()) body.replaceChildren(h('p', { class: 'field-error' }, errorText(error)));
    if (error.kind === 'session') fail(error);
  }
}
