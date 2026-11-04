// Тема до первой отрисовки: классический скрипт в <head>, иначе светлая тема мелькала бы тёмной, пока грузятся модули.
// Дальше тему ведёт js/theme.js по тому же правилу: сохранённый выбор, затем тема Telegram, затем системная.
(() => {
  let theme = '';
  try {
    const saved = localStorage.getItem('domovoy.theme');
    if (saved === 'light' || saved === 'dark') theme = saved;
  } catch { /* Без хранилища — как в Telegram. */ }
  if (!theme) {
    // Telegram передаёт свои цвета в адресе; тёмная тема — тёмный bg_color (та же формула, что у Telegram).
    try {
      const params = JSON.parse(new URLSearchParams(location.hash.slice(1)).get('tgWebAppThemeParams') || '{}');
      const hex = /^#([0-9a-f]{6})$/i.exec(params.bg_color || '');
      if (hex) {
        const value = parseInt(hex[1], 16);
        const [r, g, b] = [value >> 16, (value >> 8) & 255, value & 255];
        theme = Math.sqrt(0.299 * r * r + 0.587 * g * g + 0.114 * b * b) < 120 ? 'dark' : 'light';
      }
    } catch { /* Нет параметров Telegram — решит система. */ }
  }
  document.documentElement.dataset.theme = theme || (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
})();
