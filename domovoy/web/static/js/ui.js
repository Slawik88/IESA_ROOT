// Базовые компоненты интерфейса: сборка DOM, значки, кнопки, чипы, поля, листы, подтверждения, уведомления.
// Весь пользовательский текст попадает в страницу только через textContent — разметка из данных не строится.
import { t } from './i18n.js';
import { telegram } from './telegram.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const PROPERTIES = new Set(['value', 'checked', 'disabled', 'hidden', 'selected', 'readOnly', 'required', 'multiple']);
const AVATAR_HUES = 8;
const DRAG_CLOSE_PX = 90;
const TOAST_MS = 4500;
const TOAST_LIMIT = 3;

const hooks = { sessionExpired: () => {}, sheetsChanged: () => {} };
export const configureUi = overrides => Object.assign(hooks, overrides);

let counter = 0;
export const nextId = prefix => `${prefix}-${++counter}`;

function place(element, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') element.className = value;
    else if (key === 'text') element.textContent = value;
    else if (key === 'dataset') Object.assign(element.dataset, value);
    else if (key.startsWith('on')) element.addEventListener(key.slice(2).toLowerCase(), value);
    else if (PROPERTIES.has(key)) element[key] = value;
    else element.setAttribute(key, value === true ? '' : value);
  }
  place(element, children);
  return element;
}

export function icon(name, className = '') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', `icon ${className}`.trim());
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

// ── Кнопки и действия ───────────────────────────────────────────────────────────────────────────

export function button({ label, icon: iconName, variant = 'primary', size = 'md', block = false, onClick,
  type = 'button', ariaLabel, className = '' }) {
  return h('button', {
    type, class: `btn btn-${variant} btn-${size}${block ? ' btn-block' : ''} ${className}`.trim(),
    'aria-label': ariaLabel, onClick,
  }, iconName && icon(iconName), label && h('span', {}, label));
}

export function iconButton({ icon: iconName, label, onClick, className = '' }) {
  return h('button', { type: 'button', class: `icon-btn ${className}`.trim(), 'aria-label': label, title: label, onClick },
    icon(iconName));
}

// Единый обработчик отказа: устаревший вход — отдельный экран, остальное — понятное уведомление.
export const GENERIC_ERROR = () => t("Не удалось выполнить действие. Попробуйте ещё раз.");

// Сообщения сервера и сети (ApiError с kind) показываются как есть; неожиданный сбой — общим текстом, подробности в консоль.
export const errorText = error => {
  if (error?.kind) return error.message;
  console.error(error);
  return GENERIC_ERROR();
};

export function fail(error) {
  if (error?.kind === 'session') return hooks.sessionExpired();
  telegram.haptic.error();
  return toast(errorText(error), { kind: 'error' });
}

// Кнопка на время работы блокируется: двойное нажатие не повторяет операцию.
export async function busy(control, work) {
  if (control.disabled) return undefined;
  control.disabled = true;
  control.setAttribute('aria-busy', 'true');
  try { return await work(); }
  catch (error) { fail(error); return undefined; }
  finally {
    control.disabled = false;
    control.removeAttribute('aria-busy');
  }
}

export function badge(text, kind = 'neutral') {
  return h('span', { class: `badge badge-${kind}` }, text);
}

export function avatar(name, id, size = 'md') {
  const initial = [...String(name || '?').trim()][0]?.toLocaleUpperCase() || '?';
  return h('span', { class: `avatar avatar-${size} hue-${Math.abs(Number(id) || 0) % AVATAR_HUES}`, 'aria-hidden': 'true' }, initial);
}

export function emptyState({ icon: name, title, text, action }) {
  return h('div', { class: 'empty' }, icon(name, 'empty-icon'), h('h3', {}, title), text && h('p', {}, text), action);
}

export function skeleton(className = '') {
  return h('div', { class: `skeleton ${className}`.trim(), 'aria-hidden': 'true' });
}

// ── Выбор: чипы, сегменты, переключатель ─────────────────────────────────────────────────────────

export function chip({ label, pressed = false, onClick, count }) {
  return h('button', { type: 'button', class: 'chip', 'aria-pressed': String(pressed), onClick },
    h('span', { class: 'chip-check' }, icon('check')), label, count ? h('span', { class: 'chip-count' }, count) : null);
}

export function setChip(node, pressed) {
  node.setAttribute('aria-pressed', String(pressed));
}

// Группа взаимоисключающих вариантов; options: [{ value, label }].
export function segmented({ options, value, onChange, label }) {
  let current = value;
  const items = new Map();
  const paint = () => items.forEach((node, key) => node.setAttribute('aria-checked', String(key === current)));
  const root = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': label });
  for (const option of options) {
    const node = h('button', {
      type: 'button', role: 'radio', class: 'seg-item', 'aria-checked': String(option.value === current),
      onClick: () => {
        if (option.value === current) return;
        current = option.value;
        paint();
        telegram.haptic.select();
        onChange?.(current);
      },
    }, option.icon && icon(option.icon), h('span', {}, option.label));
    items.set(option.value, node);
    root.append(node);
  }
  return { el: root, get value() { return current; }, set(next) { current = next; paint(); } };
}

// Переключатель с мгновенным сохранением: при отказе возвращается в прежнее положение.
export function switchRow({ title, hint, checked, onChange }) {
  const titleId = nextId('switch');
  const control = h('button', { type: 'button', role: 'switch', class: 'switch', 'aria-checked': String(checked), 'aria-labelledby': titleId },
    h('span', { class: 'switch-thumb' }));
  const paint = value => control.setAttribute('aria-checked', String(value));
  control.addEventListener('click', async () => {
    if (control.disabled) return;
    const next = control.getAttribute('aria-checked') !== 'true';
    paint(next);
    control.disabled = true;
    telegram.haptic.select();
    try { await onChange(next); }
    catch (error) {
      paint(!next);
      fail(error);
    } finally { control.disabled = false; }
  });
  const row = h('div', { class: 'setting-row' },
    h('div', { class: 'row-main' }, h('div', { class: 'row-title', id: titleId }, title), hint && h('div', { class: 'row-meta' }, hint)),
    control);
  row.addEventListener('click', event => { if (!control.contains(event.target)) control.click(); });
  return row;
}

// ── Поля ввода ───────────────────────────────────────────────────────────────────────────────────

export function textField({ label, value = '', type = 'text', maxLength, placeholder = '', inputMode, autocomplete = 'off',
  required = false, hint, multiline = false, rows = 2, enterKeyHint }) {
  const id = nextId('field');
  const errorId = `${id}-error`;
  const control = h(multiline ? 'textarea' : 'input', {
    id, class: 'input', value, type: multiline ? undefined : type, maxlength: maxLength, placeholder, inputmode: inputMode,
    autocomplete, required, rows: multiline ? rows : undefined, enterkeyhint: enterKeyHint, 'aria-describedby': errorId,
  });
  const error = h('p', { class: 'field-error', id: errorId, role: 'alert' });
  const el = h('div', { class: 'field' }, h('label', { for: id }, label), control,
    hint && h('p', { class: 'field-hint' }, hint), error);
  return {
    el, input: control,
    setError(text) {
      error.textContent = text;
      control.setAttribute('aria-invalid', 'true');
    },
    clearError() {
      error.textContent = '';
      control.removeAttribute('aria-invalid');
    },
  };
}

export function selectField({ label, options, value, onChange }) {
  const id = nextId('select');
  const control = h('select', { id, class: 'input select-input' },
    options.map(option => h('option', { value: String(option.value), selected: String(option.value) === String(value) }, option.label)));
  if (onChange) control.addEventListener('change', () => onChange(control.value));
  return { el: h('div', { class: 'field' }, h('label', { for: id }, label), h('div', { class: 'select' }, control, icon('chevron-down', 'select-chevron'))), input: control };
}

// ── Уведомления ──────────────────────────────────────────────────────────────────────────────────

function toastHost() {
  const dialog = [...document.querySelectorAll('dialog[open]')].pop();
  if (!dialog) return document.getElementById('toasts');
  return dialog.querySelector(':scope > .toasts') ?? dialog.appendChild(h('div', { class: 'toasts', 'aria-live': 'polite' }));
}

// Над открытым листом уведомление живёт внутри него: только так оно остаётся поверх.
export function toast(text, { kind = 'info', ms = TOAST_MS } = {}) {
  const host = toastHost();
  while (host.children.length >= TOAST_LIMIT) host.firstElementChild.remove();
  const node = h('div', { class: `toast toast-${kind}`, role: kind === 'error' ? 'alert' : undefined },
    icon(kind === 'error' ? 'alert' : 'check'), h('span', {}, text));
  host.append(node);
  setTimeout(() => node.remove(), ms);
}

// ── Листы и подтверждения ────────────────────────────────────────────────────────────────────────

const stack = [];
export const openSheetCount = () => stack.length;
export const closeTopSheet = () => stack.at(-1)?.close();

function syncSheets() {
  document.documentElement.classList.toggle('has-sheet', stack.length > 0);
  telegram.allowSwipeClose(stack.length === 0);
  hooks.sheetsChanged(stack.length);
}

// Тянущий жест за ручку закрывает лист на телефоне; на широком экране лист — окно по центру.
function enableDrag(dialog, handles, close) {
  let startY = 0;
  let shift = 0;
  let active = false;
  const move = event => {
    shift = Math.max(0, event.clientY - startY);
    dialog.style.transform = `translateY(${shift}px)`;
  };
  const end = () => {
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', end);
    window.removeEventListener('pointercancel', end);
    if (!active) return;
    active = false;
    if (shift > DRAG_CLOSE_PX) close();
    dialog.style.transform = '';
    shift = 0;
  };
  for (const handle of handles) {
    handle.addEventListener('pointerdown', event => {
      if (event.button || !window.matchMedia('(max-width: 599px)').matches) return;
      active = true;
      startY = event.clientY;
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', end);
      window.addEventListener('pointercancel', end);
    });
  }
}

export function openSheet({ title, body, footer, onClose, size = 'md', focus }) {
  const titleId = nextId('sheet');
  let closed = false;
  const grip = h('div', { class: 'sheet-grip', 'aria-hidden': 'true' });
  const heading = h('h2', { id: titleId, tabindex: '-1' }, title);
  const head = h('header', { class: 'sheet-head' }, heading, iconButton({ icon: 'x', label: t("Закрыть"), onClick: () => api.close() }));
  const content = h('div', { class: 'sheet-body' }, body);
  const dialog = h('dialog', { class: `sheet sheet-${size}`, 'aria-labelledby': titleId },
    grip, head, content, footer ? h('footer', { class: 'sheet-foot' }, footer) : null);
  const api = {
    el: dialog, body: content,
    setTitle(text) { heading.textContent = text; },
    close() {
      if (closed) return;
      closed = true;
      dialog.close();
    },
  };
  dialog.addEventListener('close', () => {
    dialog.remove();
    stack.splice(stack.indexOf(api), 1);
    syncSheets();
    onClose?.();
  });
  dialog.addEventListener('cancel', event => {
    event.preventDefault();
    api.close();
  });
  dialog.addEventListener('click', event => { if (event.target === dialog) api.close(); });
  enableDrag(dialog, [grip, head], () => api.close());
  document.body.append(dialog);
  dialog.showModal();
  stack.push(api);
  syncSheets();
  (focus ?? heading).focus({ preventScroll: true });
  return api;
}

// Вопрос перед необратимым действием; возвращает true только по явному «да».
export function confirmSheet({ title, text, confirmLabel, danger = false }) {
  return new Promise(resolve => {
    let answer = false;
    const sheet = openSheet({
      title, size: 'sm', onClose: () => resolve(answer), body: h('p', { class: 'sheet-text' }, text),
      footer: [
        button({ label: confirmLabel, variant: danger ? 'danger' : 'primary', block: true, onClick: () => { answer = true; sheet.close(); } }),
        button({ label: t("Отмена"), variant: 'ghost', block: true, onClick: () => sheet.close() }),
      ],
    });
  });
}
