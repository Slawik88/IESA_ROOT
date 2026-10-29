// ── Хозяин экрана Путеводителя в админке (страница bot-admin/guide, слой поверх админки: admin-guide.js) ──
// Экран тот же, что у игрока: app.20.js (шапка v3Head) и app.57.js (Путеводитель) подключаются как есть, без копий.
// Здесь только то, что в Mini App дают другие части приложения: помощники, вход (заголовки админки), отклик Telegram
// и выход: «Назад» с первой темы закрывает слой, кнопка темы «Открыть …» ведёт в раздел админки.
// Грузится до app.57.js (ему при загрузке нужен _backHooks), обработчики выхода ставятся после (DOMContentLoaded).
const ADM = window.parent !== window ? window.parent : null;
const tg = (ADM && ADM.Telegram && ADM.Telegram.WebApp) || (window.Telegram && window.Telegram.WebApp) || null;
const el = id => document.getElementById(id);
function esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
const _profileEsc = s => esc(s).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
const hdrs = () => (ADM && typeof ADM.agHeaders === 'function' ? ADM.agHeaders() : {'x-init-data': (tg && tg.initData) || ''});
const _backHooks = [];
const _activePage = 'help';   // экран один: Путеводитель
function _haptic(kind) {
  const h = tg && tg.HapticFeedback; if (!h) return;
  try { kind === 'select' ? h.selectionChanged() : h.impactOccurred('light'); } catch (_) {}
}
function v3EnterSync() {}
function switchPage() {}
function navBack() { if (!gvBack()) agHostClose(); }
function agHostClose() { if (ADM && typeof ADM.agClose === 'function') ADM.agClose(); }
// Слой уже открыт, админка просит другую тему (значок «?», «Что это значит?»): та же книга, история заново.
function agHostOpen(topic) { return openAdminGuide(topic || '', 'host'); }

addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); navBack(); } });
addEventListener('DOMContentLoaded', () => {
  // Кнопки «Открыть …» тем игрока ведут по экранам Mini App, которых здесь нет: в админке темы игрока читаются без них.
  Object.keys(_GV_GO).forEach(key => { _GV_GO[key] = null; });   // ключи остаются: по ним проверяются данные книги
  // «Назад» с первой темы и кнопка темы «Открыть раздел»: закрыть слой или открыть раздел админки под ним.
  window.gvAdmin = section => {
    if (section !== 'host' && ADM && typeof ADM.agOpenSection === 'function') ADM.agOpenSection(section);
    else agHostClose();
  };
  const wanted = ADM && typeof ADM.agWanted === 'function' ? ADM.agWanted() : decodeURIComponent(location.hash.replace(/^#t=/, ''));
  agHostOpen(wanted);
});
