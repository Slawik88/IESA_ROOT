// Языки интерфейса: русский — исходный текст в коде, остальные берутся из js/i18n/<язык>.js.
// Ключ перевода — русская строка; {0}, {1} — подставляемые значения.
const LANGUAGES = { ru: 'ru-RU', uk: 'uk-UA', fr: 'fr-CH', de: 'de-CH' };
export const LANGUAGE_NAMES = { ru: 'Русский', uk: 'Українська', fr: 'Français', de: 'Deutsch' };
const STORAGE_KEY = 'domovoy.locale';
const DEFAULT_LANGUAGE = 'ru';

let dictionary = {};
export let language = DEFAULT_LANGUAGE;
export let locale = LANGUAGES[DEFAULT_LANGUAGE];

const isSupported = value => Object.hasOwn(LANGUAGES, value);

function savedLanguage() {
  try { return localStorage.getItem(STORAGE_KEY) || ''; }
  catch { return ''; } // Хранилище браузера может быть выключено — тогда язык берётся из адреса.
}

// Порядок выбора: параметр запуска → сохранённый → язык Telegram → язык браузера → русский.
export function pickLanguage({ fragment, saved, telegram, browser }) {
  return [fragment, saved, telegram, browser?.split('-')[0], DEFAULT_LANGUAGE].find(isSupported);
}

export async function initI18n(telegramLanguage) {
  const fragment = new URLSearchParams(location.hash.slice(1)).get('lang');
  language = pickLanguage({
    fragment, saved: savedLanguage(), telegram: telegramLanguage?.split('-')[0], browser: navigator.language,
  });
  locale = LANGUAGES[language];
  document.documentElement.lang = language;
  dictionary = language === DEFAULT_LANGUAGE ? {} : (await import(`./i18n/${language}.js`)).default;
}

export function t(source, values = []) {
  if (source === undefined || source === null) return '';
  const text = String(source);
  const translated = dictionary[text] ?? text;
  return translated.replace(/\{(\d+)\}/g, (match, index) => (index < values.length ? String(values[index]) : match));
}

// Тексты ошибок сервера приходят по-русски: известные переводятся, остальные показываются как есть.
export function translateError(source) {
  return String(source || '').split('\n').map(line => {
    const row = /^Строка (\d+): (.*)$/.exec(line);
    return row ? t('Строка {0}: {1}', [row[1], t(row[2])]) : t(line);
  }).join('\n');
}

// Смена языка перезагружает страницу; параметры запуска Telegram в адресе сохраняются.
export function applyLanguage(next) {
  window.dispatchEvent(new Event('domovoy:languagechanging'));
  const parameters = new URLSearchParams(location.hash.slice(1));
  try {
    localStorage.setItem(STORAGE_KEY, next);
    if (parameters.has('lang')) {
      parameters.delete('lang');
      location.hash = parameters.toString();
    }
  } catch {
    parameters.set('lang', next);
    location.hash = parameters.toString();
  }
  location.reload();
}
