// Обёртка над Telegram WebApp. Любой вызов безопасен для старых клиентов и для обычного браузера.
const webApp = window.Telegram?.WebApp;

// Старые клиенты Telegram не знают новых методов или отвечают ошибкой на неподдерживаемые цвета —
// внешний вид от этого не должен ломаться, поэтому вызовы изолированы.
function call(action) {
  try { return action(); } catch { return undefined; }
}

// Ссылки t.me Telegram открывает у себя (окно «Поделиться», чат с ботом); без Telegram — обычная новая вкладка.
function openLink(link) {
  const opened = call(() => { webApp.openTelegramLink(link); return true; });
  if (!opened) window.open(link, '_blank', 'noopener');
}

let backHandler = null;
let backWired = false;

export const telegram = {
  initData: webApp?.initData || '',
  platform: webApp?.platform || '',
  // Телефоны Telegram не сохраняют файлы из страницы: файл надёжнее отправить в чат.
  get isPhone() { return ['ios', 'android', 'android_x'].includes(webApp?.platform); },
  user: webApp?.initDataUnsafe?.user || null,
  get available() { return Boolean(webApp?.initData); },

  start() {
    call(() => webApp.ready());
    call(() => webApp.expand());
  },

  // Шапка, фон и нижняя панель Telegram получают цвет приложения — без «чужой» полосы сверху.
  paint(color) {
    call(() => webApp.setHeaderColor(color));
    call(() => webApp.setBackgroundColor(color));
    call(() => webApp.setBottomBarColor(color));
  },

  // Подписка на Telegram одна на всё время жизни страницы; обработчик можно заменить.
  setBackHandler(handler) {
    backHandler = handler;
    if (backWired) return;
    backWired = true;
    call(() => webApp.BackButton.onClick(() => backHandler?.()));
  },
  showBack(visible) {
    call(() => (visible ? webApp.BackButton.show() : webApp.BackButton.hide()));
  },

  // Пока есть несохранённый ввод, Telegram спрашивает подтверждение перед закрытием.
  guardClosing(enabled) {
    call(() => (enabled ? webApp.enableClosingConfirmation() : webApp.disableClosingConfirmation()));
  },
  // Свайп вниз закрывал бы приложение посреди ввода — на время листов он выключен.
  allowSwipeClose(allowed) {
    call(() => (allowed ? webApp.enableVerticalSwipes() : webApp.disableVerticalSwipes()));
  },

  haptic: {
    tap: () => call(() => webApp.HapticFeedback.impactOccurred('light')),
    select: () => call(() => webApp.HapticFeedback.selectionChanged()),
    success: () => call(() => webApp.HapticFeedback.notificationOccurred('success')),
    error: () => call(() => webApp.HapticFeedback.notificationOccurred('error')),
  },

  share(url, text) {
    openLink(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`);
  },
  openChat: openLink,

  close() { call(() => webApp.close()); },
};
