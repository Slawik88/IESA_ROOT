'use strict';

window.createReceiptWorkspace = ({ api, post, notice, refresh }) => {
  const $ = id => document.getElementById(id);
  let generation = 0;
  const urls = new Set(), pending = new Map();
  const node = (tag, text, cls) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (cls) item.className = cls;
    return item;
  };
  function clearImages() { for (const url of urls) URL.revokeObjectURL(url); urls.clear(); }
  $('receipt-dialog').addEventListener('close', () => { generation++; clearImages(); });

  async function open(house, expense) {
    const version = ++generation, path = `houses/${house}/expenses/${expense.id}/receipts`, key = `${house}:${expense.id}`;
    clearImages();
    const container = $('receipt-content');
    container.replaceChildren(node('p', 'Открываем чеки…', 'subtle'));
    if (!$('receipt-dialog').open) $('receipt-dialog').showModal();
    try {
      const data = await api(path);
      if (version !== generation) return;
      container.replaceChildren(node('p', expense.description || expense.category || 'Расход', 'subtle'));
      if (!data.available) {
        container.append(node('p', 'Хранилище чеков временно недоступно. Сам расход сохранён.', 'panel-note'));
        return;
      }
      if (!data.receipts.length) container.append(node('p', 'Чеков пока нет. Можно добавить фото.', 'panel-note'));
      const grid = node('div', undefined, 'receipt-grid');
      container.append(grid);
      data.receipts.forEach((receipt, index) => {
        const box = node('div'), status = node('p', `Открываем чек ${index + 1}…`, 'subtle');
        box.append(status);
        grid.append(box);
        const loadPreview = async () => { try {
          const response = await api(`${path}/${receipt.id}`, { raw: true });
          const url = URL.createObjectURL(await response.blob());
          if (version !== generation) { URL.revokeObjectURL(url); return; }
          urls.add(url);
          const image = node('img');
          image.src = url;
          image.alt = `Чек ${index + 1}`;
          const zoom = node('button', undefined, 'receipt-preview');
          zoom.type = 'button';
          zoom.setAttribute('aria-label', `Увеличить чек ${index + 1}`);
          zoom.setAttribute('aria-expanded', 'false');
          zoom.onclick = () => {
            const expanded = box.classList.toggle('expanded');
            zoom.setAttribute('aria-expanded', String(expanded));
            zoom.setAttribute('aria-label', `${expanded ? 'Уменьшить' : 'Увеличить'} чек ${index + 1}`);
          };
          zoom.append(image);
          box.replaceChildren(zoom);
        } catch (error) {
          if (version === generation) {
            const retry = node('button', 'Открыть ещё раз', 'text-button');
            retry.type = 'button';
            retry.onclick = () => { box.replaceChildren(status); loadPreview(); };
            box.replaceChildren(node('p', error.message || 'Чек не открылся', 'error'), retry);
          }
        } };
        loadPreview();
      });
      if (!data.can_upload) return;
      const form = node('form', undefined, 'receipt-upload'), group = node('fieldset');
      const label = node('label', `Фото JPEG или PNG · до ${data.max_bytes / 1024 / 1024} МБ`), input = node('input');
      input.type = 'file';
      input.accept = 'image/jpeg,image/png';
      label.append(input);
      const explanation = node('p', `${data.upload_notice}. Фото доступны только участникам дома.`, 'subtle');
      const error = node('p', '', 'error');
      error.role = 'alert';
      error.tabIndex = -1;
      const submit = node('button', pending.has(key) ? 'Повторить загрузку чека' : 'Прикрепить чек', 'full');
      submit.type = 'submit';
      submit.disabled = !pending.has(key);
      const discard = node('button', 'Убрать выбранное фото', 'text-button');
      discard.type = 'button';
      discard.hidden = !pending.has(key);
      discard.onclick = () => { pending.delete(key); input.value = ''; submit.disabled = true; discard.hidden = true; error.textContent = ''; };
      input.onchange = async () => {
        const file = input.files[0];
        if (!file) return;
        pending.delete(key);
        submit.disabled = true;
        error.textContent = '';
        if (file.size > data.max_bytes) { error.textContent = 'Выберите фото не больше 2 МБ'; return; }
        if (file.type && !['image/jpeg', 'image/png'].includes(file.type)) { error.textContent = 'Подойдёт фото JPEG или PNG'; return; }
        const bytes = new Uint8Array(await file.arrayBuffer());
        if (version !== generation || input.files[0] !== file) return;
        let binary = '';
        for (let offset = 0; offset < bytes.length; offset += 16384) binary += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
        pending.set(key, { request_id: crypto.randomUUID(), content: btoa(binary) });
        submit.textContent = 'Прикрепить чек';
        submit.disabled = false;
        discard.hidden = false;
      };
      form.onsubmit = async event => {
        event.preventDefault();
        if (group.disabled || !pending.has(key)) return;
        group.disabled = true;
        const intent = pending.get(key);
        submit.setAttribute('aria-busy', 'true');
        error.textContent = '';
        try {
          await post(path, intent);
          if (pending.get(key) === intent) pending.delete(key);
          notice('Чек прикреплён');
          try { await refresh(); } catch { /* Фото уже сохранено; повтор денежной записи не нужен. */ }
          if (version === generation) await open(house, expense);
        } catch (failure) {
          error.textContent = failure.message || 'Связь прервалась. Расход сохранён. Можно повторить только загрузку этого чека.';
          submit.textContent = 'Повторить загрузку чека';
          if (error.isConnected) error.focus();
        } finally { group.disabled = false; submit.removeAttribute('aria-busy'); }
      };
      group.append(label, explanation, submit, discard);
      form.append(group, error);
      container.append(form);
    } catch (error) {
      if (version === generation) container.replaceChildren(node('p', error.message || 'Чеки пока не открылись', 'error'));
    }
  }
  return { open };
};
