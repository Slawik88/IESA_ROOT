// Сетевой слой: один способ ходить в API, понятные ошибки, таймаут на весь запрос.
import { t, translateError } from './i18n.js';

const TIMEOUT_MS = 25000;
const SERVER_DOWN = [502, 503, 504];

// kind: domain — отказ правил дома; session — вход устарел; server — сервис недоступен; network — нет связи.
export class ApiError extends Error {
  constructor(message, kind) {
    super(message);
    this.kind = kind;
  }
}

async function failure(response) {
  let text = t("Не удалось выполнить действие. Попробуйте ещё раз.");
  let kind = 'domain';
  try {
    const data = await response.json();
    if (typeof data.detail === 'string') text = translateError(data.detail);
  } catch { /* Прокси может вернуть не JSON — остаётся общий текст. */ }
  if (response.status === 404) {
    kind = 'session';
    text = t("Вход недоступен. Откройте приложение заново из личного чата.");
  } else if (SERVER_DOWN.includes(response.status)) {
    kind = 'server';
    text = t("Сервис временно недоступен. Введённые поля сохранены — попробуйте ещё раз чуть позже.");
  } else if (response.status === 413) {
    text = t("Файл слишком большой. Выберите файл до 2 МБ.");
  }
  return new ApiError(text, kind);
}

export function createApi(initData) {
  async function request(path, { method = 'GET', body, read = 'json' } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      let response;
      try {
        response = await fetch(`./api/${path}`, {
          method, credentials: 'omit', cache: 'no-store', signal: controller.signal,
          headers: { Authorization: `tma ${initData}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
          body: body === undefined ? undefined : JSON.stringify(body),
        });
      } catch (error) {
        throw new ApiError(error.name === 'AbortError'
          ? t("Сервер долго не отвечает. Ввод сохранён — попробуйте ещё раз.")
          : t("Нет соединения. Ввод сохранён — повторите, когда сеть вернётся."), 'network');
      }
      if (!response.ok) throw await failure(response);
      return await response[read]();
    } finally {
      clearTimeout(timer);
    }
  }
  return {
    get: path => request(path),
    post: (path, body) => request(path, { method: 'POST', body: body ?? {} }),
    blob: path => request(path, { read: 'blob' }),
  };
}
