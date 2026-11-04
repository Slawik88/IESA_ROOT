// Тема оформления: по умолчанию — как в Telegram (без него — как в системе); выбор «светлая/тёмная» помнит только это устройство.
// До загрузки модулей тему уже поставил js/theme-boot.js; здесь — смена темы на лету и цвета Telegram.
import { telegram } from './telegram.js';

const STORAGE_KEY = 'domovoy.theme';
export const THEME_CHOICES = ['auto', 'light', 'dark'];
const systemDark = () => Boolean(window.matchMedia?.('(prefers-color-scheme: dark)').matches);

export let themeChoice = 'auto';

export function resolveTheme(choice, telegramScheme, prefersDark) {
  if (choice === 'light' || choice === 'dark') return choice;
  if (telegramScheme === 'light' || telegramScheme === 'dark') return telegramScheme;
  return prefersDark ? 'dark' : 'light';
}

function savedChoice() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return THEME_CHOICES.includes(saved) ? saved : 'auto';
  } catch { return 'auto'; } // Без хранилища тема просто следует Telegram.
}

function apply() {
  const root = document.documentElement;
  root.dataset.theme = resolveTheme(themeChoice, telegram.colorScheme, systemDark());
  // Шапка и панели Telegram — цвета фона темы (--bg в app.css), чтобы не было чужой полосы.
  const background = getComputedStyle(root).getPropertyValue('--bg').trim();
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', background);
  telegram.paint(background);
}

export function initTheme() {
  themeChoice = savedChoice();
  apply();
  telegram.onThemeChanged(apply);
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', apply);
}

export function setTheme(choice) {
  themeChoice = THEME_CHOICES.includes(choice) ? choice : 'auto';
  try { localStorage.setItem(STORAGE_KEY, themeChoice); }
  catch { /* Тема меняется и без хранилища, но после перезапуска вернётся к Telegram. */ }
  apply();
}
